# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRepairPartsPicking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        Location = cls.env["stock.location"]
        parent = cls.warehouse.view_location_id
        cls.workshop = Location.create({"name": "Workshop", "location_id": parent.id})
        cls.quarantine = Location.create(
            {"name": "Quarantine", "location_id": parent.id}
        )
        cls.recoverable = Location.create(
            {"name": "To recover", "location_id": parent.id}
        )
        cls.staging = Location.create({"name": "Removed", "location_id": parent.id})
        cls.picking_type = cls.warehouse.repair_type_id
        cls.picking_type.write(
            {
                "default_add_location_src_id": cls.workshop.id,
                "removed_quarantine_location_id": cls.quarantine.id,
                "removed_recoverable_location_id": cls.recoverable.id,
                "removed_by_transfer": True,
                "removed_staging_location_id": cls.staging.id,
            }
        )
        production = cls.picking_type.default_location_dest_id
        cls.route = cls.env["stock.route"].create(
            {
                "name": "Stock to workshop",
                "product_selectable": True,
                "warehouse_selectable": True,
                "warehouse_ids": [(6, 0, cls.warehouse.ids)],
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Workshop to repair",
                            "action": "pull",
                            "picking_type_id": cls.picking_type.id,
                            "location_src_id": cls.workshop.id,
                            "location_dest_id": production.id,
                            "procure_method": "make_to_order",
                            "warehouse_id": cls.warehouse.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Stock to workshop",
                            "action": "pull",
                            "picking_type_id": cls.warehouse.int_type_id.id,
                            "location_src_id": cls.stock.id,
                            "location_dest_id": cls.workshop.id,
                            "procure_method": "make_to_stock",
                            "location_dest_from_rule": True,
                            "warehouse_id": cls.warehouse.id,
                        },
                    ),
                ],
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Customer"})
        cls.part = cls._product("Part", "none")
        cls.lot_part = cls._product("Lot part", "lot")
        cls.removed = cls.env["product.product"].create(
            {"name": "Old part", "type": "consu", "is_storable": True}
        )
        cls.serial_removed = cls.env["product.product"].create(
            {
                "name": "Old serial part",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        cls._stock(cls.part, 10.0)
        cls.lot = cls.env["stock.lot"].create(
            {
                "name": "L1",
                "product_id": cls.lot_part.id,
                "company_id": cls.env.company.id,
            }
        )
        cls._stock(cls.lot_part, 5.0, cls.lot)

    @classmethod
    def _product(cls, name, tracking):
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "tracking": tracking,
                "route_ids": [(6, 0, cls.route.ids)],
            }
        )

    @classmethod
    def _stock(cls, product, qty, lot=None):
        cls.env["stock.quant"]._update_available_quantity(
            product, cls.stock, qty, lot_id=lot
        )

    def _repair(self):
        return self.env["repair.order"].create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.picking_type.id,
                "state": "confirmed",
            }
        )

    def _add(self, repair, product, qty):
        return self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "add",
                "product_id": product.id,
                "product_uom_qty": qty,
            }
        )

    def _separation(self, repair):
        repair.invalidate_recordset(["parts_picking_ids", "parts_picking_count"])
        return repair.parts_picking_ids.filtered(
            lambda p: (
                p.location_id == self.stock and p.location_dest_id == self.workshop
            )
        )

    def _validate(self, picking):
        for move in picking.move_ids:
            move.picked = True
        picking.button_validate()

    def _use(self, move, qty):
        move.move_line_ids.quantity = qty
        move.move_line_ids.picked = True

    def _returns(self, repair):
        repair.invalidate_recordset(["parts_picking_ids", "parts_picking_count"])
        return repair.parts_picking_ids.filtered(
            lambda p: (
                p.location_id == self.workshop and p.location_dest_id == self.stock
            )
        )

    # ------------------------------------------------------------------
    def test_01_separation_generated_when_the_parts_are_confirmed(self):
        repair = self._repair()
        move = self._add(repair, self.part, 2.0)
        self.assertEqual(move.location_id, self.workshop)
        picking = self._separation(repair)
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.state, "assigned")
        self.assertEqual(picking.move_ids.product_uom_qty, 2.0)
        self.assertEqual(picking.group_id, repair.procurement_group_id)
        repair.invalidate_recordset(["parts_picking_count"])
        self.assertEqual(repair.parts_picking_count, 1)
        self.assertEqual(move.state, "waiting")
        self._validate(picking)
        self.assertEqual(move.state, "assigned")

    def test_02_leftover_returns_to_the_warehouse(self):
        repair = self._repair()
        move = self._add(repair, self.part, 3.0)
        self._validate(self._separation(repair))
        repair.action_repair_start()
        self._use(move, 2.0)
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")
        returns = self._returns(repair)
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.state, "assigned")
        self.assertEqual(returns.move_ids.product_uom_qty, 1.0)
        self.assertEqual(returns.group_id, repair.procurement_group_id)
        self._validate(returns)
        self.assertEqual(returns.state, "done")
        stock_qty = self.env["stock.quant"]._get_available_quantity(
            self.part, self.stock
        )
        self.assertEqual(stock_qty, 8.0)
        workshop_qty = self.env["stock.quant"]._get_available_quantity(
            self.part, self.workshop
        )
        self.assertEqual(workshop_qty, 0.0)

    def test_03_nothing_to_return_when_everything_was_used(self):
        repair = self._repair()
        self._add(repair, self.part, 2.0)
        self._validate(self._separation(repair))
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertFalse(self._returns(repair))
        with self.assertRaises(UserError):
            repair.action_return_leftovers()

    def test_04_button_is_idempotent(self):
        repair = self._repair()
        move = self._add(repair, self.part, 3.0)
        self._validate(self._separation(repair))
        repair.action_repair_start()
        self._use(move, 1.0)
        repair.action_return_leftovers()
        returns = self._returns(repair)
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.move_ids.product_uom_qty, 2.0)
        with self.assertRaises(UserError):
            repair.action_return_leftovers()
        repair.action_repair_end()
        self.assertEqual(len(self._returns(repair)), 1)

    def test_05_lot_is_preserved(self):
        repair = self._repair()
        move = self._add(repair, self.lot_part, 3.0)
        self._validate(self._separation(repair))
        repair.action_repair_start()
        self._use(move, 2.0)
        repair.action_repair_end()
        returns = self._returns(repair)
        self.assertEqual(len(returns), 1)
        line = returns.move_line_ids
        self.assertEqual(line.lot_id, self.lot)
        self.assertEqual(line.quantity, 1.0)
        self._validate(returns)
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.lot_part.id),
                ("location_id", "=", self.stock.id),
                ("lot_id", "=", self.lot.id),
            ]
        )
        self.assertEqual(quant.quantity, 3.0)

    def _removed_pickings(self, repair, destination):
        repair.invalidate_recordset(["parts_picking_ids", "parts_picking_count"])
        return repair.parts_picking_ids.filtered(
            lambda p: (
                p.location_id == self.staging and p.location_dest_id == destination
            )
        )

    def _remove(self, repair, product, destination, serial=None):
        move = self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "remove",
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "removed_destination": destination,
            }
        )
        if serial:
            move.move_line_ids.unlink()
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "product_id": product.id,
                    "quantity": 1.0,
                    "lot_name": serial,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "company_id": move.company_id.id,
                }
            )
        else:
            move.quantity = 1.0
        move.picked = True
        return move

    def _qty(self, product, location, lot=None):
        quants = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", location.id)]
        )
        if lot:
            quants = quants.filtered(lambda q: q.lot_id == lot)
        return sum(quants.mapped("quantity"))

    def test_06_removed_part_waits_in_staging_then_goes_by_transfer(self):
        repair = self._repair()
        move = self._add(repair, self.part, 3.0)
        self._validate(self._separation(repair))
        removed = self._remove(repair, self.removed, "quarantine")
        self.assertEqual(removed.location_dest_id, self.staging)
        repair.action_repair_start()
        self._use(move, 2.0)
        repair.action_repair_end()
        self.assertEqual(removed.state, "done")
        self.assertEqual(self._qty(self.removed, self.staging), 1.0)
        self.assertEqual(self._qty(self.removed, self.quarantine), 0.0)
        transfer = self._removed_pickings(repair, self.quarantine)
        self.assertEqual(len(transfer), 1)
        self.assertEqual(transfer.state, "assigned")
        self.assertEqual(transfer.group_id, repair.procurement_group_id)
        self._validate(transfer)
        self.assertEqual(self._qty(self.removed, self.staging), 0.0)
        self.assertEqual(self._qty(self.removed, self.quarantine), 1.0)
        returns = self._returns(repair)
        self.assertEqual(returns.move_ids.product_id, self.part)

    def test_07_one_transfer_per_destination_with_serial_number(self):
        repair = self._repair()
        self._remove(repair, self.removed, "quarantine")
        self._remove(repair, self.removed, "recoverable")
        self._remove(repair, self.serial_removed, "quarantine", serial="SN-OLD-9")
        repair.action_repair_start()
        repair.action_repair_end()
        to_quarantine = self._removed_pickings(repair, self.quarantine)
        to_recover = self._removed_pickings(repair, self.recoverable)
        self.assertEqual(len(to_quarantine), 1)
        self.assertEqual(len(to_recover), 1)
        self.assertEqual(
            sorted(to_quarantine.move_ids.product_id.ids),
            sorted((self.removed | self.serial_removed).ids),
        )
        self.assertEqual(
            to_quarantine.move_line_ids.lot_id.mapped("name"), ["SN-OLD-9"]
        )
        self.assertEqual(self._qty(self.removed, self.staging), 2.0)
        self._validate(to_quarantine)
        self._validate(to_recover)
        lot = self.env["stock.lot"].search([("name", "=", "SN-OLD-9")])
        self.assertEqual(self._qty(self.serial_removed, self.quarantine, lot), 1.0)
        self.assertEqual(self._qty(self.serial_removed, self.staging, lot), 0.0)
        self.assertEqual(self._qty(self.removed, self.quarantine), 1.0)
        self.assertEqual(self._qty(self.removed, self.recoverable), 1.0)
        self.assertEqual(self._qty(self.removed, self.staging), 0.0, "nothing is lost")
        with self.assertRaises(UserError):
            repair.action_return_leftovers()

    def test_08_option_off_goes_straight_to_the_destination(self):
        self.picking_type.removed_by_transfer = False
        repair = self._repair()
        removed = self._remove(repair, self.removed, "quarantine")
        self.assertEqual(removed.location_dest_id, self.quarantine)
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(self._qty(self.removed, self.quarantine), 1.0)
        self.assertEqual(self._qty(self.removed, self.staging), 0.0)
        self.assertFalse(self._removed_pickings(repair, self.quarantine))

    def test_09_button_generates_the_removed_transfer_once(self):
        repair = self._repair()
        self._remove(repair, self.removed, "recoverable")
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(len(self._removed_pickings(repair, self.recoverable)), 1)
        with self.assertRaises(UserError):
            repair.action_return_leftovers()
        self.assertEqual(len(self._removed_pickings(repair, self.recoverable)), 1)
