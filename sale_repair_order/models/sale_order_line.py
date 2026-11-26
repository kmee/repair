# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_single_repair_line(self):
        """Line of a sale order served by one repair order."""
        self.ensure_one()
        return (
            self.order_id.repair_mode == "single"
            and bool(self.product_id)
            and not self.display_type
        )

    def _create_repair_order(self):
        # One repair order per sale order replaces one repair order per line
        lines = self.filtered(lambda line: line.order_id.repair_mode != "single")
        return super(SaleOrderLine, lines)._create_repair_order()

    def _cancel_repair_order(self):
        lines = self.filtered(lambda line: line.order_id.repair_mode != "single")
        return super(SaleOrderLine, lines)._cancel_repair_order()

    def _action_launch_stock_rule(self, *args, **kwargs):
        # sale_stock launches the delivery BEFORE the repair module creates its
        # repair orders: the repair order and its moves must be born here.
        if self.env.context.get("skip_procurement"):
            return super()._action_launch_stock_rule(*args, **kwargs)
        single = self.filtered(
            lambda line: line.state == "sale"
            and not line.order_id.locked
            and line._is_single_repair_line()
        )
        single._sync_repair_order()
        return super(SaleOrderLine, self - single)._action_launch_stock_rule(
            *args, **kwargs
        )

    # ------------------------------------------------------------------
    # Sale order -> repair order
    # ------------------------------------------------------------------
    def _sync_repair_order(self):
        """Idempotent: bring the repair order in line with these sale lines."""
        if self.env.context.get("skip_repair_order_sync"):
            return
        for order, lines in self.grouped("order_id").items():
            repair = order._get_repair_order_to_sync(lines)
            if not repair:
                continue
            for line in lines:
                if line.product_id.type == "service":
                    line._sync_repair_service(repair)
                elif line.product_id.type == "consu":
                    line._sync_repair_move(repair)

    def _check_repair_open(self, repair):
        if repair.state in ("done", "cancel"):
            raise UserError(
                _(
                    "The repair order %(repair)s is %(state)s: create a new sale "
                    "order for this change.",
                    repair=repair.display_name,
                    state=dict(repair._fields["state"].selection)[repair.state],
                )
            )

    def _prepare_repair_move_vals(self, repair):
        self.ensure_one()
        return {
            "repair_id": repair.id,
            "repair_line_type": "add",
            "sale_line_id": self.id,
            "product_id": self.product_id.id,
            "product_uom": self.product_uom.id,
            "product_uom_qty": self.product_uom_qty,
            "company_id": repair.company_id.id,
        }

    def _sync_repair_move(self, repair):
        self.ensure_one()
        moves = self.move_ids.sudo().filtered(
            lambda m: m.repair_id == repair and m.repair_line_type == "add"
        )
        active = moves.filtered(lambda m: m.state != "cancel")
        rounding = self.product_uom.rounding
        qty = self.product_uom_qty
        if not active:
            if float_compare(qty, 0, precision_rounding=rounding) <= 0:
                return
            self._check_repair_open(repair)
            self.env["stock.move"].sudo().create(self._prepare_repair_move_vals(repair))
            return
        current = sum(active.mapped("product_uom_qty"))
        if float_compare(current, qty, precision_rounding=rounding) == 0:
            return
        self._check_repair_open(repair)
        if float_compare(qty, 0, precision_rounding=rounding) <= 0:
            active.with_context(skip_repair_order_sync=True)._action_cancel()
        elif len(active) == 1:
            active.with_context(skip_repair_order_sync=True).write(
                {"product_uom_qty": qty}
            )
        else:
            raise UserError(
                _(
                    "The line %s has several moves in the repair order: change "
                    "them in the repair order.",
                    self.display_name,
                )
            )

    def _sync_repair_service(self, repair):
        self.ensure_one()
        Service = self.env["repair.service"].sudo()
        services = Service.search([("sale_line_id", "=", self.id)])
        rounding = self.product_uom.rounding
        qty = self.product_uom_qty
        if not services:
            if float_compare(qty, 0, precision_rounding=rounding) <= 0:
                return
            self._check_repair_open(repair)
            Service.with_context(skip_repair_order_sync=True).create(
                self._prepare_repair_service_vals(repair)
            )
            return
        current = sum(services.mapped("product_uom_qty"))
        if float_compare(current, qty, precision_rounding=rounding) == 0:
            return
        self._check_repair_open(repair)
        services = services.with_context(skip_repair_order_sync=True)
        if float_compare(qty, 0, precision_rounding=rounding) <= 0:
            services.unlink()
        else:
            services[:1].write({"product_uom_qty": qty})

    def _prepare_repair_service_vals(self, repair):
        self.ensure_one()
        return {
            "repair_id": repair.id,
            "sale_line_id": self.id,
            "product_id": self.product_id.id,
            "product_uom": self.product_uom.id,
            "product_uom_qty": self.product_uom_qty,
        }

    # ------------------------------------------------------------------
    # Delivered quantity
    # ------------------------------------------------------------------
    def _compute_qty_delivered(self):
        # Core repair only accepts ONE done repair move per line.
        remaining = self
        for line in self:
            moves = line.move_ids.sudo().filtered(
                lambda m: m.repair_id
                and m.repair_line_type == "add"
                and m.state == "done"
            )
            if not moves:
                continue
            remaining -= line
            line.qty_delivered = sum(
                move.product_uom._compute_quantity(move.quantity, line.product_uom)
                for move in moves
            )
        return super(SaleOrderLine, remaining)._compute_qty_delivered()

    def _mark_repair_services_delivered(self):
        for line in self:
            if line.qty_delivered_method == "manual" and not float_is_zero(
                line.product_uom_qty, precision_rounding=line.product_uom.rounding
            ):
                line.qty_delivered = line.product_uom_qty
