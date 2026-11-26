# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRepairRemoveDestination(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.picking_type = cls.warehouse.repair_type_id
        Location = cls.env["stock.location"]
        parent = cls.warehouse.view_location_id
        cls.quarantine, cls.recoverable, cls.condemned = (
            Location.create({"name": name, "location_id": parent.id})
            for name in ("Quarantine", "To recover", "Condemned")
        )
        cls.picking_type.write(
            {
                "removed_quarantine_location_id": cls.quarantine.id,
                "removed_recoverable_location_id": cls.recoverable.id,
                "removed_condemned_location_id": cls.condemned.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Customer"})
        cls.part = cls.env["product.product"].create(
            {"name": "Old part", "type": "consu", "is_storable": True}
        )
        cls.serial_part = cls.env["product.product"].create(
            {
                "name": "Old serial part",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
            }
        )

    def _repair(self):
        return self.env["repair.order"].create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.picking_type.id,
                "state": "confirmed",
            }
        )

    def _remove(self, repair, line_type="remove", destination=None, product=None):
        vals = {
            "repair_id": repair.id,
            "repair_line_type": line_type,
            "product_id": (product or self.part).id,
            "product_uom_qty": 1.0,
        }
        if destination:
            vals["removed_destination"] = destination
        return self.env["stock.move"].create(vals)

    def test_01_default_is_quarantine(self):
        move = self._remove(self._repair())
        self.assertEqual(move.removed_destination, "quarantine")
        self.assertEqual(move.location_dest_id, self.quarantine)

    def test_02_each_destination(self):
        repair = self._repair()
        for destination, location in (
            ("quarantine", self.quarantine),
            ("recoverable", self.recoverable),
            ("condemned", self.condemned),
        ):
            move = self._remove(repair, destination=destination)
            self.assertEqual(move.location_dest_id, location, destination)

    def test_03_recycle_and_change_of_destination(self):
        repair = self._repair()
        move = self._remove(repair, line_type="recycle")
        self.assertEqual(move.location_dest_id, self.quarantine)
        move.removed_destination = "condemned"
        self.assertEqual(move.location_dest_id, self.condemned)

    def test_04_add_line_has_no_destination(self):
        repair = self._repair()
        move = self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "add",
                "product_id": self.part.id,
                "product_uom_qty": 1.0,
            }
        )
        self.assertFalse(move.removed_destination)
        self.assertNotIn(
            move.location_dest_id,
            (self.quarantine, self.recoverable, self.condemned),
        )

    def test_05_without_configuration_keeps_core_location(self):
        self.picking_type.write(
            {
                "removed_quarantine_location_id": False,
                "removed_recoverable_location_id": False,
                "removed_condemned_location_id": False,
            }
        )
        move = self._remove(self._repair())
        self.assertFalse(move.removed_destination)
        self.assertEqual(
            move.location_dest_id, self.picking_type.default_remove_location_dest_id
        )

    def test_06_finish_puts_stock_in_the_destination(self):
        repair = self._repair()
        move_q = self._remove(repair, destination="quarantine")
        move_c = self._remove(repair, destination="condemned")
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")
        for move, location in ((move_q, self.quarantine), (move_c, self.condemned)):
            self.assertEqual(move.state, "done")
            quant = self.env["stock.quant"].search(
                [("product_id", "=", self.part.id), ("location_id", "=", location.id)]
            )
            self.assertEqual(quant.quantity, 1.0)

    def test_07_serial_removed_needs_the_number_and_lands_in_the_destination(self):
        repair = self._repair()
        move = self._remove(repair, destination="recoverable", product=self.serial_part)
        repair.action_repair_start()
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.serial_part.id,
                "quantity": 1.0,
                "lot_name": "SN-OLD-1",
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "company_id": move.company_id.id,
            }
        )
        repair.action_repair_end()
        lot = self.env["stock.lot"].search([("name", "=", "SN-OLD-1")])
        self.assertTrue(lot)
        quant = self.env["stock.quant"].search(
            [("lot_id", "=", lot.id), ("location_id", "=", self.recoverable.id)]
        )
        self.assertEqual(quant.quantity, 1.0)
