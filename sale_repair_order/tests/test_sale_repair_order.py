# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import SaleRepairCommon


@tagged("post_install", "-at_install")
class TestSaleRepairOrder(SaleRepairCommon):
    def test_01_confirm_creates_single_repair_without_delivery(self):
        order = self._make_order()
        repair = order.repair_id
        self.assertTrue(repair)
        self.assertEqual(order.repair_role, "main")
        self.assertEqual(repair.sale_order_id, order)
        self.assertEqual(repair.state, "confirmed")
        self.assertEqual(len(repair.sale_order_ids), 1)
        self.assertFalse(order.picking_ids, "no delivery for repair mode orders")
        self.assertEqual(
            len(self.env["repair.order"].search([("sale_order_id", "=", order.id)])), 1
        )
        line_a = order.order_line.filtered(lambda line: line.product_id == self.part_a)
        move_a = self._repair_move(repair, self.part_a)
        self.assertEqual(len(move_a), 1)
        self.assertEqual(move_a.sale_line_id, line_a)
        self.assertEqual(move_a.repair_line_type, "add")
        self.assertEqual(move_a.product_uom_qty, 2.0)
        self.assertIn(move_a.state, ("assigned", "confirmed"))
        self.assertEqual(move_a.state, "assigned", "parts are reserved")
        self.assertEqual(len(order.order_line), 3, "no duplicated sale line")
        service = repair.repair_service_ids
        self.assertEqual(len(service), 1)
        self.assertEqual(service.sale_line_id.product_id, self.service)
        self.assertEqual(service.product_uom_qty, 3.0)
        self.assertEqual(order.repair_count, 1)

    def test_02_normal_type_keeps_core_behaviour(self):
        order = self._make_order(order_type=self.normal_type)
        self.assertFalse(order.repair_id)
        self.assertTrue(order.picking_ids, "regular orders still deliver")
        self.assertFalse(order.repair_order_ids)

    def test_03_line_added_after_confirmation_enters_repair(self):
        order = self._make_order()
        repair = order.repair_id
        line = self._add_line(order, self.part_b, 4.0)
        move = line.move_ids.filtered(lambda m: m.state != "cancel")
        self.assertEqual(len(move), 1)
        self.assertEqual(move.repair_id, repair)
        self.assertEqual(move.product_uom_qty, 4.0)
        service_line = self._add_line(order, self.service_b, 2.0)
        service = repair.repair_service_ids.filtered(
            lambda s: s.sale_line_id == service_line
        )
        self.assertEqual(len(service), 1)
        self.assertEqual(service.product_uom_qty, 2.0)
        self.assertFalse(order.picking_ids)

    def test_04_quantity_change_and_zero(self):
        order = self._make_order()
        repair = order.repair_id
        line = order.order_line.filtered(lambda line: line.product_id == self.part_a)
        line.product_uom_qty = 5.0
        move = self._repair_move(repair, self.part_a)
        self.assertEqual(len(move), 1)
        self.assertEqual(move.product_uom_qty, 5.0)
        self.assertEqual(line.product_uom_qty, 5.0)
        service_line = order.order_line.filtered(
            lambda line: line.product_id == self.service
        )
        service_line.product_uom_qty = 7.0
        self.assertEqual(repair.repair_service_ids.product_uom_qty, 7.0)
        line.product_uom_qty = 0.0
        self.assertFalse(self._repair_move(repair, self.part_a))
        service_line.product_uom_qty = 0.0
        self.assertFalse(repair.repair_service_ids)
        line.product_uom_qty = 1.0
        move = self._repair_move(repair, self.part_a)
        self.assertEqual(move.product_uom_qty, 1.0)
        move.product_uom_qty = 2.0
        self.assertEqual(
            line.product_uom_qty, 2.0, "cancelled moves are not summed back"
        )

    def test_05_part_added_in_repair_reaches_sale_order(self):
        order = self._make_order()
        repair = order.repair_id
        move = self._new_form_line(repair, self.part_b, 3.0)
        self.assertTrue(move.sale_line_id)
        self.assertEqual(move.sale_line_id.order_id, order)
        self.assertEqual(len(order.order_line), 4)
        self.assertFalse(order.picking_ids)
        self.assertEqual(len(self._repair_move(repair, self.part_b)), 2)

    def test_06_service_added_in_repair_gets_pricelist_price(self):
        pricelist = self.env["product.pricelist"].create(
            {
                "name": "Half price",
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "compute_price": "percentage",
                            "percent_price": 50,
                            "applied_on": "3_global",
                        },
                    )
                ],
            }
        )
        order = self._make_order(pricelist_id=pricelist.id)
        repair = order.repair_id
        service = self.env["repair.service"].create(
            {
                "repair_id": repair.id,
                "product_id": self.service_b.id,
                "product_uom_qty": 2.0,
            }
        )
        self.assertTrue(service.sale_line_id)
        self.assertEqual(service.sale_line_id.order_id, order)
        self.assertEqual(service.sale_line_id.product_uom_qty, 2.0)
        self.assertEqual(
            service.sale_line_id.price_unit, 25.0, "pricelist wins over list price"
        )
        service.product_uom_qty = 4.0
        self.assertEqual(service.sale_line_id.product_uom_qty, 4.0)
        line = service.sale_line_id
        service.unlink()
        self.assertEqual(line.product_uom_qty, 0.0)

    def test_07_done_repair_refuses_new_line_and_delivers_quantities(self):
        order = self._make_order()
        repair = order.repair_id
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")
        line_a = order.order_line.filtered(lambda line: line.product_id == self.part_a)
        service_line = order.order_line.filtered(
            lambda line: line.product_id == self.service
        )
        self.assertEqual(line_a.qty_delivered, 2.0)
        self.assertEqual(service_line.qty_delivered, 3.0)
        with self.assertRaises(UserError):
            self._add_line(order, self.part_b, 1.0)

    def test_08_qty_delivered_sums_several_moves(self):
        order = self._make_order()
        repair = order.repair_id
        line_a = order.order_line.filtered(lambda line: line.product_id == self.part_a)
        move = self._repair_move(repair, self.part_a)
        extra = move.copy({"repair_id": repair.id, "product_uom_qty": 1.0})
        extra.sale_line_id = line_a
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(line_a.qty_delivered, 3.0)

    def test_09_serial_tracked_part(self):
        serial = self._create_product("Serial part", 300.0, tracking="serial")
        lot = self.env["stock.lot"].create(
            {"name": "SN-1", "product_id": serial.id, "company_id": self.env.company.id}
        )
        self._set_stock(serial, 1.0, lot=lot)
        order = self._make_order(lines=[(serial, 1.0)])
        repair = order.repair_id
        move = self._repair_move(repair, serial)
        self.assertEqual(len(move), 1)
        self.assertEqual(move.move_line_ids.lot_id, lot)
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(order.order_line.qty_delivered, 1.0)

    def test_10_cancel_sale_order_cancels_repair(self):
        order = self._make_order()
        repair = order.repair_id
        order._action_cancel()
        self.assertEqual(repair.state, "cancel")
        self.assertEqual(order.state, "cancel")
        self.assertFalse(repair.move_ids.filtered(lambda m: m.state != "cancel"))

    def test_11_cancel_sale_order_with_done_repair_is_blocked(self):
        order = self._make_order()
        repair = order.repair_id
        repair.action_repair_start()
        repair.action_repair_end()
        with self.assertRaises(UserError):
            order._action_cancel()
        self.assertEqual(order.state, "sale")

    def test_12_cancel_repair_zeroes_lines_and_keeps_order(self):
        order = self._make_order()
        repair = order.repair_id
        repair.action_repair_cancel()
        self.assertEqual(repair.state, "cancel")
        self.assertEqual(order.state, "sale")
        self.assertTrue(all(line.product_uom_qty == 0 for line in order.order_line))
        repair.action_repair_cancel_draft()
        quantities = {
            line.product_id: line.product_uom_qty for line in order.order_line
        }
        self.assertEqual(quantities[self.part_a], 2.0)
        self.assertEqual(quantities[self.part_b], 1.0)
        self.assertEqual(quantities[self.service], 3.0)

    def test_13_reconfirm_cancelled_order_reopens_repair(self):
        order = self._make_order()
        repair = order.repair_id
        order._action_cancel()
        order.action_draft()
        order.action_confirm()
        self.assertEqual(order.repair_id, repair)
        self.assertEqual(repair.state, "confirmed")
        self.assertEqual(
            len(self.env["repair.order"].search([("sale_order_id", "=", order.id)])), 1
        )
        self.assertEqual(self._repair_move(repair, self.part_a).product_uom_qty, 2.0)

    def test_14_copy_sale_order_opens_its_own_repair(self):
        order = self._make_order()
        new_order = order.copy()
        self.assertFalse(new_order.repair_id)
        self.assertFalse(new_order.repair_role)
        new_order.action_confirm()
        self.assertTrue(new_order.repair_id)
        self.assertNotEqual(new_order.repair_id, order.repair_id)
        self.assertEqual(len(new_order.repair_id.move_ids), 2)

    def test_15_copy_repair_order_drops_links(self):
        order = self._make_order()
        repair = order.repair_id
        new_repair = repair.copy()
        self.assertFalse(new_repair.sale_order_id)
        self.assertEqual(len(new_repair.repair_service_ids), 1)
        self.assertFalse(new_repair.repair_service_ids.sale_line_id)
        self.assertFalse(new_repair.sale_order_ids)
        self.assertFalse(new_repair.move_ids.sale_line_id)

    def test_16_empty_order_creates_no_repair_until_a_line(self):
        order = self._make_order(lines=[], confirm=False)
        order.action_confirm()
        self.assertFalse(order.repair_id)

    def test_17_salesman_reads_repair_but_cannot_write(self):
        order = self._make_order()
        repair = order.repair_id
        salesman = self.env["res.users"].create(
            {
                "name": "Salesman",
                "login": "sr_salesman",
                "email": "sr_salesman@example.com",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        other = self.env["res.users"].create(
            {
                "name": "Other",
                "login": "sr_other",
                "email": "sr_other@example.com",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        order.user_id = salesman
        repair_as = repair.with_user(salesman)
        self.assertEqual(repair_as.name, repair.name)
        self.assertTrue(repair_as.repair_service_ids.mapped("display_name"))
        with self.assertRaises(AccessError):
            repair_as.write({"internal_notes": "x"})
        repair_other = repair.with_user(other)
        with self.assertRaises(AccessError):
            repair_other.read(["name"])
        all_users = self.env["res.users"].create(
            {
                "name": "Stock and sales",
                "login": "sr_both",
                "email": "sr_both@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("sales_team.group_sale_salesman").id,
                            self.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        self.assertEqual(repair.with_user(all_users).name, repair.name)

    def test_18_technician_adds_items_without_sales_rights(self):
        order = self._make_order()
        repair = order.repair_id
        technician = self.env["res.users"].create(
            {
                "name": "Technician",
                "login": "sr_technician",
                "email": "sr_technician@example.com",
                "groups_id": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
            }
        )
        move = (
            self.env["stock.move"]
            .with_user(technician)
            .create(
                {
                    "repair_id": repair.id,
                    "repair_line_type": "add",
                    "product_id": self.part_b.id,
                    "product_uom_qty": 2.0,
                }
            )
        )
        self.assertEqual(move.sale_line_id.order_id, order)
        service = (
            self.env["repair.service"]
            .with_user(technician)
            .create(
                {
                    "repair_id": repair.id,
                    "product_id": self.service_b.id,
                    "product_uom_qty": 1.0,
                }
            )
        )
        self.assertEqual(service.sale_line_id.order_id, order)
