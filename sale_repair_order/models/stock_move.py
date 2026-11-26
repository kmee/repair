# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _clean_repair_sale_order_line(self):
        # Moves are the authority here: do not echo the change back to the moves
        return super(
            StockMove, self.with_context(skip_repair_order_sync=True)
        )._clean_repair_sale_order_line()

    def _create_repair_sale_order_line(self):
        # The technician (stock user) has no right on sale lines
        return super(StockMove, self.sudo())._create_repair_sale_order_line()

    def _update_repair_sale_order_line(self):
        # The core sums every move of the line, cancelled ones included.
        # Restoring a cancelled repair order (cancel to draft) needs them.
        self = self.with_context(skip_repair_order_sync=True)
        if self.env.context.get("repair_include_cancelled_moves"):
            return super()._update_repair_sale_order_line()
        moves_to_clean = self.filtered(
            lambda m: m.repair_id and m.sale_line_id and m.repair_line_type != "add"
        )
        moves_to_update = self.filtered(
            lambda m: m.repair_id and m.sale_line_id and m.repair_line_type == "add"
        )
        moves_to_clean._clean_repair_sale_order_line()
        for line in moves_to_update.sale_line_id:
            line.product_uom_qty = sum(
                line.move_ids.filtered(lambda m: m.state != "cancel").mapped(
                    "product_uom_qty"
                )
            )
