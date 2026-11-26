# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    repair_mode = fields.Selection(related="type_id.repair_mode", string="Repair Mode")
    repair_id = fields.Many2one(
        comodel_name="repair.order",
        string="Repair Order",
        copy=False,
        index="btree_not_null",
        readonly=True,
        help="Repair order served by this sale order (main or complementary).",
    )
    repair_role = fields.Selection(
        selection=[("main", "Main"), ("complement", "Complementary")],
        copy=False,
        readonly=True,
    )

    @api.depends("repair_order_ids", "repair_id")
    def _compute_repair_count(self):
        for order in self:
            order.repair_count = len(order.repair_order_ids | order.repair_id)

    def action_show_repair(self):
        self.ensure_one()
        repairs = self.repair_order_ids | self.repair_id
        if len(repairs) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "repair.order",
                "views": [[False, "form"]],
                "res_id": repairs.id,
            }
        if repairs:
            return {
                "name": _("Repair Orders"),
                "type": "ir.actions.act_window",
                "res_model": "repair.order",
                "view_mode": "list,form",
                "domain": [("id", "in", repairs.ids)],
            }
        return super().action_show_repair()

    def _get_repair_picking_type(self):
        self.ensure_one()
        return self.type_id.repair_picking_type_id or self.warehouse_id.repair_type_id

    def _prepare_repair_order_vals(self):
        self.ensure_one()
        vals = {
            "state": "confirmed",
            "partner_id": self.partner_id.id,
            "sale_order_id": self.id,
            "company_id": self.company_id.id,
            "user_id": self.user_id.id or self.env.user.id,
        }
        picking_type = self._get_repair_picking_type()
        if picking_type:
            vals["picking_type_id"] = picking_type.id
        return vals

    def _create_single_repair_order(self):
        """Create the repair order that serves this sale order."""
        self.ensure_one()
        repair = (
            self.env["repair.order"].sudo().create(self._prepare_repair_order_vals())
        )
        self.sudo().write({"repair_id": repair.id, "repair_role": "main"})
        return repair

    def _get_repair_order_to_sync(self, lines):
        """Return the repair order that must receive ``lines`` (or empty)."""
        self.ensure_one()
        repair = self.repair_id
        if repair:
            if repair.state == "cancel" and self.repair_role != "complement":
                # Sale order set back to draft and confirmed again
                repair.sudo().action_repair_cancel_draft()
                repair.sudo()._action_repair_confirm()
            return repair
        if not any(line.product_uom_qty > 0 for line in lines):
            return repair
        return self._create_single_repair_order()

    def _action_cancel(self):
        for order in self:
            repair = order.repair_id
            if repair and order.repair_role != "complement" and repair.state == "done":
                raise UserError(
                    _(
                        "The repair order %(repair)s is already done: the sale "
                        "order %(order)s cannot be cancelled.",
                        repair=repair.display_name,
                        order=order.display_name,
                    )
                )
        res = super()._action_cancel()
        for order in self:
            repair = order.repair_id
            if (
                repair
                and order.repair_role != "complement"
                and repair.state not in ("done", "cancel")
            ):
                repair.sudo().action_repair_cancel()
        return res
