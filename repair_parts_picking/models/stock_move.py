# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_removed_staging_location(self):
        self.ensure_one()
        if not self._is_removed_part():
            return self.env["stock.location"]
        picking_type = self.repair_id.picking_type_id
        if picking_type.removed_by_transfer:
            return picking_type.removed_staging_location_id
        return self.env["stock.location"]

    @api.depends(
        "removed_destination",
        "repair_id.picking_type_id.removed_by_transfer",
        "repair_id.picking_type_id.removed_staging_location_id",
    )
    def _compute_location_dest_id(self):
        res = super()._compute_location_dest_id()
        for move in self:
            staging = move._get_removed_staging_location()
            if staging:
                move.location_dest_id = staging
        return res

    def _set_repair_locations(self):
        res = super()._set_repair_locations()
        for move in self:
            staging = move._get_removed_staging_location()
            if staging:
                move.location_dest_id = staging
        return res

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            staging = move._get_removed_staging_location()
            if staging and move.location_dest_id != staging:
                move.location_dest_id = staging
        return moves
