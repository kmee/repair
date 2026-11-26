# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class RepairService(models.Model):
    _inherit = "repair.service"

    def _after_item_rejected(self):
        res = super()._after_item_rejected()
        # the quoted line leaves the complementary order (moves do it already)
        lines = self.sale_line_id.filtered(
            lambda line: line.order_id.repair_role == "complement"
            and line.product_uom_qty
        )
        lines.with_context(skip_repair_order_sync=True).write({"product_uom_qty": 0.0})
        return res
