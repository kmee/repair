# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.sale_repair_order.tests.common import SaleRepairCommon


@tagged("post_install", "-at_install")
class TestRepairComplementaryQuotation(SaleRepairCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.write(
            {
                "repair_approval_currency_id": company.currency_id.id,
                "repair_approval_limit": 100.0,
                "repair_approval_inclusive": False,
            }
        )
        cls.team = cls.env["crm.team"].create({"name": "Maintenance team"})
        cls.term = cls.env.ref("account.account_payment_term_30days")
        cls.quoter = cls.env["res.users"].create(
            {
                "name": "Quoter",
                "login": "sr_quoter",
                "email": "sr_quoter@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "repair_complementary_quotation.group_repair_quote"
                            ).id,
                            cls.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        cls.salesperson = cls.env["res.users"].create(
            {
                "name": "Seller",
                "login": "sr_seller",
                "email": "sr_seller@example.com",
                "groups_id": [
                    (6, 0, [cls.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        cls.order = cls._make_order(
            lines=[(cls.part_a, 2.0), (cls.service, 1.0)],
            payment_term_id=cls.term.id,
            team_id=cls.team.id,
            user_id=cls.salesperson.id,
            client_order_ref="PO-77",
        )
        cls.repair = cls.order.repair_id

    def _pending(self, product=None, qty=25.0, **extra):
        return self.env["stock.move"].create(
            {
                "repair_id": self.repair.id,
                "repair_line_type": "add",
                "product_id": (product or self.part_b).id,
                "product_uom_qty": qty,
                **extra,
            }
        )

    def _pending_service(self, qty=500.0):
        return self.env["repair.service"].create(
            {
                "repair_id": self.repair.id,
                "product_id": self.service_b.id,
                "product_uom_qty": qty,
            }
        )

    def _complement(self, user=None):
        repair = self.repair.with_user(user or self.quoter)
        action = repair.action_create_complementary_order()
        return self.env["sale.order"].browse(action["res_id"])

    # ------------------------------------------------------------------
    def test_01_generate_inherits_and_links(self):
        move = self._pending()
        service = self._pending_service()
        self.assertTrue(self.repair.has_unquoted_pending_items)
        complement = self._complement()
        self.assertEqual(complement.repair_id, self.repair)
        self.assertEqual(complement.repair_role, "complement")
        self.assertEqual(complement.complement_of_id, self.order)
        self.assertEqual(complement.state, "draft")
        for fname in (
            "partner_id",
            "partner_invoice_id",
            "partner_shipping_id",
            "pricelist_id",
            "payment_term_id",
            "fiscal_position_id",
            "company_id",
            "warehouse_id",
            "type_id",
            "user_id",
            "team_id",
            "client_order_ref",
        ):
            self.assertEqual(complement[fname], self.order[fname], fname)
        self.assertEqual(complement.origin, self.order.name)
        lines = complement.order_line.filtered(lambda line: not line.display_type)
        self.assertEqual(len(lines), 2)
        self.assertTrue(complement.order_line.filtered("display_type"))
        self.assertEqual(move.sale_line_id.order_id, complement)
        self.assertEqual(service.sale_line_id.order_id, complement)
        self.assertEqual(move.sale_line_id.product_uom_qty, 25.0)
        self.assertEqual(move.sale_line_id.price_unit, 20.0, "priced by the list")
        self.assertEqual(move.approval_state, "pending")
        self.assertEqual(move.state, "draft")
        self.assertEqual(len(self.order.order_line), 2, "main order untouched")
        self.assertEqual(self.repair.complement_count, 1)
        self.assertFalse(self.repair.has_unquoted_pending_items)
        self.assertEqual(self.repair.pending_item_count, 2)
        self.assertEqual(self.repair.sale_order_id, self.order)
        self.assertEqual(self.repair.sale_order_ids, self.order | complement)
        self.assertEqual(self.order.complement_ids, complement)
        self.assertEqual(complement.repair_count, 1)
        with self.assertRaises(UserError):
            self._complement()  # nothing left to quote

    def test_02_confirm_approves_and_reserves(self):
        move = self._pending()
        service = self._pending_service()
        complement = self._complement()
        complement.signed_by = "Customer Rep"
        complement.action_confirm()
        self.assertEqual(complement.state, "sale")
        self.assertEqual(move.approval_state, "approved")
        self.assertEqual(move.approval_origin, "customer")
        self.assertEqual(move.state, "assigned", "reserved")
        self.assertEqual(service.approval_state, "approved")
        self.assertFalse(complement.picking_ids, "no delivery")
        self.assertEqual(
            len(self.repair.move_ids.filtered(lambda m: m.state != "cancel")), 2
        )
        self.assertEqual(len(move.sale_line_id), 1)
        self.assertEqual(self.repair.pending_item_count, 0)
        self.assertTrue(
            self.repair.message_ids.filtered(lambda m: "Customer Rep" in (m.body or ""))
        )
        self.assertEqual(len(self.repair.repair_service_ids), 2)
        # the repair order still has a single repair
        self.assertEqual(
            len(
                self.env["repair.order"].search(
                    [("sale_order_ids", "in", complement.ids)]
                )
            ),
            1,
        )
        self.repair.action_repair_start()
        self.repair.action_repair_end()
        self.assertEqual(self.repair.state, "done")
        self.assertEqual(move.sale_line_id.qty_delivered, 25.0)
        self.assertEqual(service.sale_line_id.qty_delivered, 500.0)

    def test_03_cancel_refuses_and_unblocks(self):
        move = self._pending()
        service = self._pending_service()
        complement = self._complement()
        self.repair.action_repair_start()
        with self.assertRaises(UserError):
            self.repair.action_repair_end()
        complement._action_cancel()
        self.assertEqual(complement.state, "cancel")
        self.assertEqual(move.approval_state, "rejected")
        self.assertEqual(move.state, "cancel")
        self.assertEqual(service.approval_state, "rejected")
        self.assertEqual(self.repair.pending_item_count, 0)
        self.assertEqual(self.order.state, "sale", "main order untouched")
        self.assertNotEqual(self.repair.state, "cancel")
        self.repair.action_repair_end()
        self.assertEqual(self.repair.state, "done")
        self.assertFalse(
            complement.order_line.filtered("product_uom_qty").filtered(
                lambda line: not line.display_type
            )
        )

    def test_04_second_complement(self):
        first = self._pending()
        complement_1 = self._complement()
        second = self._pending(self.part_a, 30.0)
        self.assertTrue(self.repair.has_unquoted_pending_items)
        complement_2 = self._complement()
        self.assertNotEqual(complement_1, complement_2)
        self.assertEqual(first.sale_line_id.order_id, complement_1)
        self.assertEqual(second.sale_line_id.order_id, complement_2)
        complement_1.action_confirm()
        complement_2._action_cancel()
        self.assertEqual(first.approval_state, "approved")
        self.assertEqual(second.approval_state, "rejected")
        self.assertEqual(self.repair.complement_count, 2)

    def test_05_sent_complement_blocks_item_changes(self):
        move = self._pending()
        self._pending_service()
        complement = self._complement()
        line = move.sale_line_id
        complement.state = "sent"
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            line.product_uom_qty = 1.0
        line.product_uom_qty = 30.0  # increasing is fine
        complement.state = "draft"
        line.unlink()
        self.assertFalse(move.sale_line_id, "the item can be quoted again")
        self.assertTrue(self.repair.has_unquoted_pending_items)

    def test_06_cancel_main_order(self):
        self._pending()
        draft_complement = self._complement()
        self.order._action_cancel()
        self.assertEqual(draft_complement.state, "cancel")
        self.assertEqual(self.order.state, "cancel")
        self.assertEqual(self.repair.state, "cancel")

    def test_07_cancel_main_order_with_confirmed_complement_is_blocked(self):
        self._pending()
        complement = self._complement()
        complement.action_confirm()
        with self.assertRaises(UserError):
            self.order._action_cancel()
        self.assertEqual(self.order.state, "sale")

    def test_08_button_needs_the_quote_group(self):
        self._pending()
        with self.assertRaises(AccessError):
            self.repair.with_user(self.salesperson).action_create_complementary_order()

    def test_09_complement_cannot_be_duplicated(self):
        self._pending()
        complement = self._complement()
        with self.assertRaises(UserError):
            complement.copy()
        self.assertTrue(self.order.copy())

    def test_10_mandatory_label_and_class(self):
        move = self._pending(item_class="mandatory")
        self._complement()
        line = move.sale_line_id
        self.assertEqual(line.repair_item_class, "mandatory")
        self.assertIn("Mandatory by the regulation", line.name)
        with self.assertRaises(UserError):
            line.with_user(self.salesperson).write({"discount": 5.0})

    def test_11_cancel_repair_with_open_complement(self):
        move = self._pending()
        complement = self._complement()
        self.repair.action_repair_cancel()
        self.assertEqual(move.approval_state, "rejected")
        self.assertEqual(self.repair.pending_item_count, 0)
        self.assertTrue(complement)

    def test_12_complement_requires_repair_mode(self):
        self._pending()
        self.order.type_id = self.normal_type
        with self.assertRaises(UserError):
            self._complement()
