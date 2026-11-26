# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests import Form
from odoo.tests.common import TransactionCase


class SaleRepairCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,
                mail_notrack=True,
                mail_create_nolog=True,
            )
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.partner = cls.env["res.partner"].create({"name": "Repair Customer"})
        # same currency as the products, whatever the default pricelist is
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "Repair list", "currency_id": cls.env.company.currency_id.id}
        )
        cls.order_type = cls.env["sale.order.type"].create(
            {"name": "Maintenance", "repair_mode": "single"}
        )
        cls.normal_type = cls.env["sale.order.type"].create({"name": "Normal Sale"})
        cls.part_a = cls._create_product("Part A", 10.0)
        cls.part_b = cls._create_product("Part B", 20.0)
        cls.service = cls.env["product.product"].create(
            {"name": "Service A", "type": "service", "list_price": 100.0}
        )
        cls.service_b = cls.env["product.product"].create(
            {"name": "Service B", "type": "service", "list_price": 50.0}
        )
        for part in (cls.part_a, cls.part_b):
            cls._set_stock(part, 100.0)

    @classmethod
    def _create_product(cls, name, price, tracking="none"):
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "tracking": tracking,
                "list_price": price,
            }
        )

    @classmethod
    def _set_stock(cls, product, qty, lot=None):
        location = cls.warehouse.lot_stock_id
        cls.env["stock.quant"]._update_available_quantity(
            product, location, qty, lot_id=lot
        )

    @classmethod
    def _make_order(
        cls, order_type=None, lines=None, confirm=True, partner=None, **extra
    ):
        order_type = order_type or cls.order_type
        order = cls.env["sale.order"].create(
            {
                "partner_id": (partner or cls.partner).id,
                "type_id": order_type.id,
                "warehouse_id": cls.warehouse.id,
                "pricelist_id": cls.pricelist.id,
                **extra,
                "order_line": [
                    (
                        0,
                        0,
                        {"product_id": product.id, "product_uom_qty": qty},
                    )
                    for product, qty in (
                        lines
                        if lines is not None
                        else [(cls.part_a, 2.0), (cls.part_b, 1.0), (cls.service, 3.0)]
                    )
                ],
            }
        )
        if confirm:
            order.action_confirm()
        return order

    @classmethod
    def _add_line(cls, order, product, qty):
        return cls.env["sale.order.line"].create(
            {"order_id": order.id, "product_id": product.id, "product_uom_qty": qty}
        )

    def _repair_move(self, repair, product):
        return repair.move_ids.filtered(
            lambda m: m.product_id == product and m.state != "cancel"
        )

    def _new_form_line(self, repair, product, qty=1.0):
        return self.env["stock.move"].create(
            {
                "repair_id": repair.id,
                "repair_line_type": "add",
                "product_id": product.id,
                "product_uom_qty": qty,
            }
        )

    @staticmethod
    def _form(record):
        return Form(record)
