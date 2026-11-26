# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    repair_approve_all = fields.Boolean(
        string="Approves Every Repair Item",
        help="Every item added in the repair orders of this customer waits for "
        "its approval, whatever the amount.",
    )
