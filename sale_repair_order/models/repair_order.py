# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models


class RepairOrder(models.Model):
    _inherit = "repair.order"

    sale_order_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="repair_id",
        string="Sale Orders",
        copy=False,
    )
    order_count = fields.Integer(
        string="Sale Orders Count", compute="_compute_order_count"
    )

    @api.depends("sale_order_ids")
    def _compute_order_count(self):
        for repair in self:
            repair.order_count = len(repair.sale_order_ids)

    def action_view_sale_orders(self):
        self.ensure_one()
        action = {
            "name": _("Sale Orders"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "domain": [("id", "in", self.sale_order_ids.ids)],
            "view_mode": "list,form",
        }
        if len(self.sale_order_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.sale_order_ids.id})
        return action

    def action_repair_cancel(self):
        # The sale lines follow the repair order, not the other way around
        res = super(
            RepairOrder, self.with_context(skip_repair_order_sync=True)
        ).action_repair_cancel()
        for repair in self:
            lines = repair.repair_service_ids.sale_line_id.filtered(
                lambda line: line.product_uom_qty
            )
            lines.with_context(skip_repair_order_sync=True).write(
                {"product_uom_qty": 0.0}
            )
        return res

    def action_repair_cancel_draft(self):
        res = super(
            RepairOrder,
            self.with_context(
                skip_repair_order_sync=True, repair_include_cancelled_moves=True
            ),
        ).action_repair_cancel_draft()
        for service in self.repair_service_ids.filtered("sale_line_id"):
            service.sale_line_id.with_context(skip_repair_order_sync=True).write(
                {"product_uom_qty": service.product_uom_qty}
            )
        return res

    def action_repair_done(self):
        res = super().action_repair_done()
        self.repair_service_ids.sale_line_id._mark_repair_services_delivered()
        return res
