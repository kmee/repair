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
        cls.picking_type = cls.warehouse.repair_type_id
        cls.picking_type.write(
            {
                "default_add_location_src_id": cls.workshop.id,
                "removed_quarantine_location_id": cls.quarantine.id,
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

    def test_06_removed_part_goes_to_quarantine_and_leftover_to_stock(self):
        repair = self._repair()
        move = self._add(repair, self.part, 3.0)
        self._validate(self._separation(repair))
        removed = self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "remove",
                "product_id": self.removed.id,
                "product_uom_qty": 1.0,
                "removed_destination": "quarantine",
            }
        )
        removed.quantity = 1.0
        removed.picked = True
        repair.action_repair_start()
        self._use(move, 2.0)
        repair.action_repair_end()
        self.assertEqual(removed.state, "done")
        quarantined = self.env["stock.quant"]._get_available_quantity(
            self.removed, self.quarantine
        )
        self.assertEqual(quarantined, 1.0)
        returns = self._returns(repair)
        self.assertEqual(returns.move_ids.product_id, self.part)
        self.assertNotIn(self.removed, returns.move_ids.product_id)
