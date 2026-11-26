# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _check_complement_sent_change(self):
        for line in self:
            order = line.order_id
            if order.repair_role == "complement" and order.state == "sent":
                raise UserError(
                    _(
                        "%s was already sent to the customer: cancel it before "
                        "changing its items.",
                        order.display_name,
                    )
                )

    def unlink(self):
        self.filtered(
            lambda line: not line.display_type
        )._check_complement_sent_change()
        return super().unlink()

    def write(self, vals):
        if "product_uom_qty" in vals:
            self.filtered(
                lambda line: not line.display_type
                and float_compare(
                    vals["product_uom_qty"],
                    line.product_uom_qty,
                    precision_rounding=line.product_uom.rounding,
                )
                < 0
            )._check_complement_sent_change()
        return super().write(vals)
