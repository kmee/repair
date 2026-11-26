# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class RepairPendingItemWizard(models.TransientModel):
    _name = "repair.pending.item.wizard"
    _description = "Approve or refuse the pending items of a repair order"

    repair_id = fields.Many2one("repair.order", required=True, readonly=True)
    decision = fields.Selection(
        selection=[("approve", "Approve"), ("refuse", "Refuse")],
        required=True,
        readonly=True,
    )
    note = fields.Text()
    item_count = fields.Integer(compute="_compute_item_count")
    finish = fields.Boolean(
        string="Finish the repair order afterwards",
        help="Refuse the pending items and finish the repair order in one step.",
    )

    @api.depends("repair_id")
    def _compute_item_count(self):
        for wizard in self:
            wizard.item_count = wizard.repair_id.pending_item_count

    def action_confirm(self):
        self.ensure_one()
        if self.decision == "approve":
            self.repair_id.action_approve_pending_items(note=self.note)
        else:
            self.repair_id.action_refuse_pending_items(note=self.note)
            if self.finish:
                self.repair_id.action_repair_end()
        return {"type": "ir.actions.act_window_close"}
