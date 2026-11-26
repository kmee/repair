# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    removed_destination = fields.Selection(
        selection=[
            ("quarantine", "Quarantine"),
            ("recoverable", "To be recovered"),
            ("condemned", "Condemned"),
        ],
        compute="_compute_removed_destination",
        store=True,
        readonly=False,
        precompute=True,
        help="Where the removed part goes. Default: quarantine.",
    )

    def _is_removed_part(self):
        self.ensure_one()
        return bool(self.repair_id) and self.repair_line_type in ("remove", "recycle")

    @api.depends("repair_line_type", "repair_id.picking_type_id")
    def _compute_removed_destination(self):
        for move in self:
            if not move._is_removed_part():
                move.removed_destination = False
            elif not move.removed_destination:
                picking_type = move.repair_id.picking_type_id
                move.removed_destination = (
                    "quarantine"
                    if picking_type.removed_quarantine_location_id
                    else False
                )

    def _get_removed_destination_location(self):
        self.ensure_one()
        if not self._is_removed_part() or not self.removed_destination:
            return self.env["stock.location"]
        return self.repair_id.picking_type_id._get_removed_location(
            self.removed_destination
        )

    @api.depends("removed_destination")
    def _compute_location_dest_id(self):
        res = super()._compute_location_dest_id()
        for move in self:
            location = move._get_removed_destination_location()
            if location:
                move.location_dest_id = location
        return res

    def _set_repair_locations(self):
        res = super()._set_repair_locations()
        for move in self:
            location = move._get_removed_destination_location()
            if location:
                move.location_dest_id = location
        return res

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            location = move._get_removed_destination_location()
            if location and move.location_dest_id != location:
                move.location_dest_id = location
        return moves
