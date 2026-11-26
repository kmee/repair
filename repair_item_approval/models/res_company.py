# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    repair_approval_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Repair Approval Currency",
        default=lambda self: self._default_repair_approval_currency(),
        help="Currency of the repair approval limit. The limit is converted "
        "to the currency of the sale order with the rate of the day.",
    )
    repair_approval_limit = fields.Monetary(
        currency_field="repair_approval_currency_id",
        default=100.0,
        help="Item added in a repair order below this amount is applied "
        "without approval. Zero: every added item needs approval.",
    )
    repair_approval_base = fields.Selection(
        selection=[("line", "Line total"), ("unit", "Unit price")],
        default="line",
        required=True,
    )
    repair_approval_inclusive = fields.Boolean(
        string="Repair Approval Limit Inclusive",
        help="Checked: an item equal to the limit is applied without approval. "
        "Unchecked: only items strictly below the limit are.",
    )
    repair_approval_cumulative = fields.Boolean(
        help="Sum the items of the same product of the repair order, so that "
        "nobody splits an item into small lines to stay under the limit.",
    )

    @api.model
    def _default_repair_approval_currency(self):
        return (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", "USD")], limit=1)
        )
