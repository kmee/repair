# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ["stock.move", "repair.item.approval.mixin"]

    def _approval_is_candidate(self, vals):
        return bool(vals.get("repair_id")) and vals.get("repair_line_type") == "add"

    @api.model_create_multi
    def create(self, vals_list):
        self._approval_apply_on_create(vals_list)
        moves = super().create(vals_list)
        pending = moves.filtered(
            lambda m: m.repair_id
            and m.approval_state == "pending"
            and not m.approval_origin
        )
        if pending and not self.env.context.get("repair_approval_internal"):
            for repair, items in pending.grouped("repair_id").items():
                repair._notify_pending_items(items)
        return moves

    def write(self, vals):
        self._check_approval_write(vals)
        return super().write(vals)

    def _action_confirm(self, *args, **kwargs):
        # A pending item neither reserves nor consumes stock until approved.
        # It is returned so that the callers of the core ``create`` still get it.
        pending = self.filtered(lambda m: m.repair_id and m.approval_state == "pending")
        res = super(StockMove, self - pending)._action_confirm(*args, **kwargs)
        return res | pending

    def _create_repair_sale_order_line(self):
        approved = self.filtered(lambda m: m.approval_state == "approved")
        return super(StockMove, approved)._create_repair_sale_order_line()

    def _after_item_approved(self):
        res = super()._after_item_approved()
        moves = self.filtered(
            lambda m: m.repair_id.state in ("confirmed", "under_repair")
            and m.state == "draft"
        )
        moves._action_confirm()
        self._create_repair_sale_order_line()
        return res

    def _after_item_rejected(self):
        res = super()._after_item_rejected()
        self.filtered(lambda m: m.state != "cancel")._action_cancel()
        return res
