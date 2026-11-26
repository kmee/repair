# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.sale_repair_order.tests.common import SaleRepairCommon


@tagged("post_install", "-at_install")
class TestRepairItemApproval(SaleRepairCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "repair_approval_currency_id": cls.company.currency_id.id,
                "repair_approval_limit": 100.0,
                "repair_approval_base": "line",
                "repair_approval_inclusive": False,
                "repair_approval_cumulative": False,
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Approval manager",
                "login": "sr_approval_manager",
                "email": "sr_approval_manager@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "repair_item_approval.group_repair_item_manager"
                            ).id,
                            cls.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        cls.order = cls._make_order(lines=[(cls.part_a, 2.0), (cls.service, 1.0)])
        cls.repair = cls.order.repair_id

    def _move(self, product=None, qty=1.0, repair=None, **extra):
        return self.env["stock.move"].create(
            {
                "repair_id": (repair or self.repair).id,
                "repair_line_type": "add",
                "product_id": (product or self.part_a).id,
                "product_uom_qty": qty,
                **extra,
            }
        )

    # ------------------------------------------------------------------
    def test_01_order_items_are_born_approved(self):
        moves = self.repair.move_ids
        self.assertTrue(moves)
        self.assertTrue(all(m.approval_state == "approved" for m in moves))
        self.assertEqual(set(moves.mapped("approval_origin")), {"order"})
        service = self.repair.repair_service_ids
        self.assertEqual(service.approval_state, "approved")
        self.assertEqual(service.approval_origin, "order")
        self.assertFalse(self.repair.pending_item_count)

    def test_02_below_limit_is_applied_above_is_pending(self):
        lines_before = len(self.order.order_line)
        cheap = self._move(self.part_a, 8.0)  # 80.00
        self.assertEqual(cheap.approval_state, "approved")
        self.assertEqual(cheap.approval_origin, "limit")
        self.assertEqual(cheap.approval_amount, 80.0)
        self.assertTrue(cheap.sale_line_id)
        self.assertEqual(len(self.order.order_line), lines_before + 1)
        self.assertIn(cheap.state, ("assigned", "confirmed"))
        expensive = self._move(self.part_b, 25.0)  # 500.00
        self.assertEqual(expensive.approval_state, "pending")
        self.assertEqual(expensive.approval_amount, 500.0)
        self.assertEqual(expensive.state, "draft", "does not reserve")
        self.assertFalse(expensive.sale_line_id, "does not reach the sale order")
        self.assertEqual(len(self.order.order_line), lines_before + 1)
        self.assertFalse(expensive.move_line_ids)
        self.assertEqual(self.repair.pending_item_count, 1)
        self.assertTrue(self.repair.customer_wait_since)
        self.assertFalse(self.order.picking_ids)

    def test_03_limit_is_strict_or_inclusive(self):
        exact = self._move(self.part_a, 10.0)  # 100.00
        self.assertEqual(exact.approval_state, "pending", "below means strict")
        self.company.repair_approval_inclusive = True
        exact_2 = self._move(self.part_a, 10.0)
        self.assertEqual(exact_2.approval_state, "approved")
        over = self._move(self.part_a, 11.0)
        self.assertEqual(over.approval_state, "pending")

    def test_04_base_unit(self):
        self.company.repair_approval_base = "unit"
        big_qty = self._move(self.part_b, 100.0)  # unit 20.00, line 2000.00
        self.assertEqual(big_qty.approval_state, "approved")
        self.company.repair_approval_limit = 15.0
        self.assertEqual(self._move(self.part_b, 1.0).approval_state, "pending")

    def test_05_cumulative_by_product(self):
        self.company.repair_approval_cumulative = True
        first = self._move(self.part_a, 6.0)  # 60.00
        self.assertEqual(first.approval_state, "approved")
        second = self._move(self.part_a, 6.0)  # 60 + 60 > 100
        self.assertEqual(second.approval_state, "pending")
        other_product = self._move(self.part_b, 3.0)  # 60.00 alone
        self.assertEqual(other_product.approval_state, "approved")

    def test_06_customer_approves_everything(self):
        self.partner.repair_approve_all = True
        tiny = self._move(self.part_a, 1.0)
        self.assertEqual(tiny.approval_state, "pending")
        service = self.env["repair.service"].create(
            {
                "repair_id": self.repair.id,
                "product_id": self.service_b.id,
                "product_uom_qty": 1.0,
            }
        )
        self.assertEqual(service.approval_state, "pending")
        self.assertFalse(service.sale_line_id)
        self.assertEqual(self.repair.pending_item_count, 2)
        # items of the order itself are not affected
        line = self._add_line(self.order, self.part_b, 1.0)
        self.assertEqual(line.move_ids.approval_state, "approved")
        self.assertEqual(line.move_ids.approval_origin, "order")

    def test_07_zero_limit_asks_for_everything(self):
        self.company.repair_approval_limit = 0.0
        self.assertEqual(self._move(self.part_a, 1.0).approval_state, "pending")

    def test_08_currency_conversion(self):
        eur = self.env.ref("base.EUR")
        eur.active = True
        if eur == self.company.currency_id:
            self.skipTest("company currency is EUR")
        self.env["res.currency.rate"].create(
            {
                "currency_id": eur.id,
                "rate": 0.5,
                "name": fields.Date.context_today(self.env.user) or "2020-01-01",
                "company_id": self.company.id,
            }
        )
        pricelist = self.env["product.pricelist"].create(
            {"name": "EUR list", "currency_id": eur.id}
        )
        order = self._make_order(lines=[(self.part_a, 1.0)], pricelist_id=pricelist.id)
        # 10.00 in company currency is 5.00 EUR; the limit (100) is 50.00 EUR
        low = self._move(self.part_a, 9.0, repair=order.repair_id)  # 45.00 EUR
        self.assertEqual(low.approval_state, "approved")
        high = self._move(self.part_a, 11.0, repair=order.repair_id)  # 55.00 EUR
        self.assertEqual(high.approval_state, "pending")
        self.assertEqual(high.approval_currency_id, eur)

    def test_09_warranty_is_always_approved(self):
        self.repair.under_warranty = True
        item = self._move(self.part_b, 25.0)
        self.assertEqual(item.approval_state, "approved")
        self.assertEqual(item.approval_origin, "limit")
        self.assertEqual(item.approval_amount, 0.0)

    def test_10_repair_without_order_keeps_core_behaviour(self):
        repair = self.env["repair.order"].create({"partner_id": self.partner.id})
        move = self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "add",
                "product_id": self.part_b.id,
                "product_uom_qty": 50.0,
            }
        )
        self.assertEqual(move.approval_state, "approved")

    def test_11_pending_blocks_finishing(self):
        self._move(self.part_b, 25.0)
        self.repair.action_repair_start()
        with self.assertRaises(UserError):
            self.repair.action_repair_end()
        self.assertEqual(self.repair.state, "under_repair")

    def test_12_refuse_pending_and_finish(self):
        pending = self._move(self.part_b, 25.0)
        service = self.env["repair.service"].create(
            {
                "repair_id": self.repair.id,
                "product_id": self.service_b.id,
                "product_uom_qty": 500.0,
            }
        )
        self.assertEqual(service.approval_state, "pending")
        self.repair.action_repair_start()
        wizard = self.env["repair.pending.item.wizard"].create(
            {
                "repair_id": self.repair.id,
                "decision": "refuse",
                "finish": True,
                "note": "customer declined",
            }
        )
        wizard.action_confirm()
        self.assertEqual(pending.approval_state, "rejected")
        self.assertEqual(pending.state, "cancel")
        self.assertEqual(service.approval_state, "rejected")
        self.assertEqual(service.refusal_note, "customer declined")
        self.assertEqual(self.repair.state, "done")
        self.assertFalse(self.repair.customer_wait_since)

    def test_13_mandatory_refusal_needs_note(self):
        item = self._move(self.part_b, 25.0, item_class="mandatory")
        self.assertEqual(item.approval_state, "pending")
        with self.assertRaises(UserError):
            self.repair.action_refuse_pending_items()
        self.repair.action_refuse_pending_items(note="not authorised by the owner")
        self.assertEqual(item.approval_state, "rejected")
        recommended = self._move(self.part_b, 25.0, item_class="recommended")
        self.repair.action_refuse_pending_items()
        self.assertEqual(recommended.approval_state, "rejected")

    def test_14_internal_approval_joins_the_repair(self):
        item = self._move(self.part_b, 25.0)
        service = self.env["repair.service"].create(
            {
                "repair_id": self.repair.id,
                "product_id": self.service_b.id,
                "product_uom_qty": 500.0,
            }
        )
        with self.assertRaises(UserError):
            self.repair.action_approve_pending_items(note="ok")  # not a manager
        repair = self.repair.with_user(self.manager)
        with self.assertRaises(UserError):
            repair.action_approve_pending_items()  # no note
        repair.action_approve_pending_items(note="called the owner")
        self.assertEqual(item.approval_state, "approved")
        self.assertEqual(item.approval_origin, "manager")
        self.assertIn(item.state, ("assigned", "confirmed"))
        self.assertTrue(item.sale_line_id)
        self.assertEqual(service.approval_state, "approved")
        self.assertTrue(service.sale_line_id)
        self.assertEqual(self.repair.pending_item_count, 0)

    def test_15_direct_write_of_approval_is_refused(self):
        item = self._move(self.part_b, 25.0)
        with self.assertRaises(UserError):
            item.write({"approval_state": "approved"})
        with self.assertRaises(UserError):
            item.write({"approval_origin": "manager"})
        # the client cannot create an item already approved either
        forged = self._move(self.part_b, 25.0, approval_state="approved")
        self.assertEqual(forged.approval_state, "pending")

    def test_16_quantity_increase_over_the_limit_is_refused(self):
        item = self._move(self.part_a, 8.0)  # 80.00 approved
        item.product_uom_qty = 9.0  # 90.00 still fine
        with self.assertRaises(UserError):
            item.product_uom_qty = 20.0
        self.assertEqual(item.product_uom_qty, 9.0)

    def test_17_activity_for_the_salesperson(self):
        salesperson = self.env["res.users"].create(
            {
                "name": "Salesperson",
                "login": "sr_salesperson",
                "email": "sr_salesperson@example.com",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        self.order.user_id = salesperson
        self._move(self.part_b, 25.0)
        self._move(self.part_b, 30.0)
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", self.order.id)]
        )
        self.assertEqual(len(activities), 1, "one activity per repair and day")
        self.assertEqual(activities.user_id, salesperson)
        messages = self.repair.message_ids.filtered(
            lambda m: "awaiting approval" in (m.body or "")
        )
        self.assertTrue(messages)

    def test_18_mandatory_class_locks_price_and_discount(self):
        draft = self._make_order(
            lines=[(self.part_a, 1.0)], confirm=False, user_id=self.manager.id
        )
        draft.order_line.repair_item_class = "mandatory"
        salesman = self.env["res.users"].create(
            {
                "name": "Salesman 2",
                "login": "sr_salesman2",
                "email": "sr_salesman2@example.com",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        draft.user_id = salesman
        with self.assertRaises(UserError):
            draft.order_line.with_user(salesman).write({"discount": 10.0})
        draft.order_line.with_user(self.manager).write({"discount": 10.0})
        self.assertEqual(draft.order_line.discount, 10.0)
        draft.order_line.write({"repair_item_class": "mandatory"})
        draft.action_confirm()
        self.assertEqual(draft.repair_id.move_ids.item_class, "mandatory")

    def test_19_cancel_repair_refuses_pending(self):
        item = self._move(self.part_b, 25.0)
        self.repair.action_repair_cancel()
        self.assertEqual(item.approval_state, "rejected")
        self.assertEqual(self.repair.pending_item_count, 0)

    def test_20_form_in_the_repair_order(self):
        with Form(self.repair) as form:
            with form.move_ids.new() as line:
                line.product_id = self.part_b
                line.product_uom_qty = 25.0
        item = self.repair.move_ids.filtered(
            lambda m: m.product_id == self.part_b and m.approval_state == "pending"
        )
        self.assertEqual(len(item), 1)
        self.assertEqual(item.state, "draft")
