# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class RepairService(models.Model):
    _name = "repair.service"
    _inherit = ["repair.service", "repair.item.approval.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        self._approval_apply_on_create(vals_list)
        services = super().create(vals_list)
        pending = services.filtered(
            lambda s: s.approval_state == "pending" and not s.approval_origin
        )
        if pending and not self.env.context.get("repair_approval_internal"):
            for repair, items in pending.grouped("repair_id").items():
                repair._notify_pending_items(items)
        return services

    def write(self, vals):
        self._check_approval_write(vals)
        return super().write(vals)

    def _create_repair_sale_order_line(self):
        approved = self.filtered(lambda s: s.approval_state == "approved")
        return super(RepairService, approved)._create_repair_sale_order_line()

    def _after_item_approved(self):
        res = super()._after_item_approved()
        self._create_repair_sale_order_line()
        return res
