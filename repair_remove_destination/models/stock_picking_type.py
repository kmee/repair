# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    removed_quarantine_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Quarantine Location",
        check_company=True,
        help="Destination of the removed parts that wait for an evaluation.",
    )
    removed_recoverable_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="To Be Recovered Location",
        check_company=True,
        help="Destination of the removed parts that can be repaired.",
    )
    removed_condemned_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Condemned Location",
        check_company=True,
        help="Destination of the removed parts that are scrapped.",
    )

    def _get_removed_location(self, destination):
        self.ensure_one()
        return {
            "quarantine": self.removed_quarantine_location_id,
            "recoverable": self.removed_recoverable_location_id,
            "condemned": self.removed_condemned_location_id,
        }.get(destination, self.env["stock.location"])
