# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    removed_by_transfer = fields.Boolean(
        string="Removed Parts by Transfer",
        help="Checked: a part removed from the aircraft stops in the staging "
        "location and, when the repair order ends, one transfer per destination "
        "takes it to Quarantine, To be recovered or Condemned (the stock "
        "operator validates it). Unchecked: it goes straight to its destination.",
    )
    removed_staging_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Removed Parts Staging Location",
        check_company=True,
        help="Workshop location where the removed parts wait for the transfer.",
    )
