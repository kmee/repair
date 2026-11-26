# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RepairOrder(models.Model):
    _inherit = "repair.order"

    parts_picking_ids = fields.One2many(
        comodel_name="stock.picking",
        compute="_compute_parts_picking_ids",
        string="Parts Transfers",
    )
    parts_picking_count = fields.Integer(compute="_compute_parts_picking_ids")

    @api.depends("procurement_group_id")
    def _compute_parts_picking_ids(self):
        for repair in self:
            pickings = self.env["stock.picking"]
            if repair.procurement_group_id and repair.id:
                pickings = pickings.search(
                    [("group_id", "=", repair.procurement_group_id.id)]
                )
            repair.parts_picking_ids = pickings
            repair.parts_picking_count = len(pickings)

    def action_view_parts_pickings(self):
        self.ensure_one()
        self.invalidate_recordset(["parts_picking_ids", "parts_picking_count"])
        action = {
            "name": _("Parts Transfers"),
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", self.parts_picking_ids.ids)],
        }
        if len(self.parts_picking_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.parts_picking_ids.id})
        return action

    def _get_parts_workshop_location(self):
        """Where the parts wait for the repair (source of the Add lines)."""
        self.ensure_one()
        return self.picking_type_id.default_add_location_src_id

    @api.model
    def _lot_quantities(self, move_lines):
        """{(product, lot): quantity in the product unit} of the move lines."""
        result = defaultdict(float)
        for line in move_lines:
            product = line.product_id
            result[(product, line.lot_id)] += line.product_uom_id._compute_quantity(
                line.quantity, product.uom_id
            )
        return result

    def _get_parts_leftovers(self):
        """Parts separated to the workshop and neither used nor already returned.

        Return ``{(product, lot): quantity}`` (lot may be empty) and
        ``{product: origin location}``.
        """
        self.ensure_one()
        workshop = self._get_parts_workshop_location()
        group = self.procurement_group_id
        if not workshop or not group:
            return {}, {}
        Move = self.env["stock.move"]
        incoming = Move.search(
            [
                ("group_id", "=", group.id),
                ("repair_id", "=", False),
                ("state", "=", "done"),
                ("location_dest_id", "=", workshop.id),
            ]
        )
        if not incoming:
            return {}, {}
        outgoing = Move.search(
            [
                ("group_id", "=", group.id),
                ("repair_id", "=", False),
                ("state", "not in", ("cancel", "draft")),
                ("location_id", "=", workshop.id),
            ]
        )
        # parts already used (done) or still reserved by the Add lines
        used = self.move_ids.filtered(
            lambda m: m.repair_line_type == "add" and m.state != "cancel"
        )
        left = defaultdict(float)
        for key, qty in self._lot_quantities(incoming.move_line_ids).items():
            left[key] += qty
        for key, qty in self._lot_quantities(used.move_line_ids).items():
            left[key] -= qty
        for key, qty in self._lot_quantities(outgoing.move_line_ids).items():
            left[key] -= qty
        origins = {m.product_id: m.location_id for m in incoming}
        leftovers = {
            key: qty for key, qty in left.items() if qty > key[0].uom_id.rounding / 2
        }
        return leftovers, origins

    def _prepare_leftover_return_picking(self, workshop, destination):
        self.ensure_one()
        picking_type = (
            workshop.warehouse_id.int_type_id
            or self.picking_type_id.warehouse_id.int_type_id
        )
        return {
            "picking_type_id": picking_type.id,
            "location_id": workshop.id,
            "location_dest_id": destination.id,
            "origin": _("Leftover parts of %s", self.name),
            "group_id": self.procurement_group_id.id,
            "company_id": self.company_id.id,
        }

    def _create_leftover_return(self):
        """Create (and reserve) the transfers that bring the leftovers back."""
        pickings = self.env["stock.picking"]
        for repair in self:
            leftovers, origins = repair._get_parts_leftovers()
            if not leftovers:
                continue
            workshop = repair._get_parts_workshop_location()
            by_destination = defaultdict(lambda: defaultdict(dict))
            for (product, lot), qty in leftovers.items():
                by_destination[origins[product]][product][lot] = qty
            for destination, products in by_destination.items():
                picking = self.env["stock.picking"].create(
                    repair._prepare_leftover_return_picking(workshop, destination)
                )
                for product, lots in products.items():
                    self.env["stock.move"].create(
                        {
                            "name": product.display_name,
                            "picking_id": picking.id,
                            "product_id": product.id,
                            "product_uom": product.uom_id.id,
                            "product_uom_qty": sum(lots.values()),
                            "location_id": workshop.id,
                            "location_dest_id": destination.id,
                            "picking_type_id": picking.picking_type_id.id,
                            "group_id": repair.procurement_group_id.id,
                            "company_id": repair.company_id.id,
                        }
                    )
                picking.action_confirm()
                for move in picking.move_ids:
                    lots = products[move.product_id]
                    if any(lots):
                        for lot, qty in lots.items():
                            move._update_reserved_quantity(
                                qty, workshop, lot_id=lot or None, strict=True
                            )
                        move._recompute_state()
                    else:
                        move._action_assign()
                pickings |= picking
            repair.message_post(
                body=_("Return of the leftover parts generated: %s")
                % ", ".join(pickings.mapped("name"))
            )
        return pickings

    def action_return_leftovers(self):
        self.ensure_one()
        pickings = self._create_leftover_return()
        if not pickings:
            raise UserError(_("There are no leftover parts to return."))
        return self.action_view_parts_pickings()

    def action_repair_done(self):
        res = super().action_repair_done()
        self._create_leftover_return()
        return res
