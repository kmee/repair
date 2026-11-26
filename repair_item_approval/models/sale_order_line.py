# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    repair_item_class = fields.Selection(
        selection=[
            ("standard", "Standard"),
            ("mandatory", "Mandatory (regulation)"),
            ("recommended", "Recommended"),
        ],
        default="standard",
        help="Mandatory items (required by the regulation) are not negotiated: "
        "price and discount are locked.",
    )

    def _prepare_repair_move_vals(self, repair):
        vals = super()._prepare_repair_move_vals(repair)
        vals["item_class"] = self.repair_item_class
        return vals

    def _prepare_repair_service_vals(self, repair):
        vals = super()._prepare_repair_service_vals(repair)
        vals["item_class"] = self.repair_item_class
        return vals

    def _is_mandatory_repair_item(self):
        self.ensure_one()
        if self.repair_item_class == "mandatory":
            return True
        moves = self.move_ids.sudo().filtered(lambda m: m.repair_id)
        services = (
            self.env["repair.service"].sudo().search([("sale_line_id", "=", self.id)])
        )
        return any(i.item_class == "mandatory" for i in moves | services)

    def write(self, vals):
        if (
            ("price_unit" in vals or "discount" in vals)
            and not self.env.su
            and not self.env.user.has_group("sales_team.group_sale_manager")
            and not self.env.user.has_group(
                "repair_item_approval.group_repair_item_manager"
            )
        ):
            for line in self.filtered("order_id"):
                if line.state == "draft" and line._is_mandatory_repair_item():
                    raise UserError(
                        _(
                            "%s is mandatory by the regulation: price and "
                            "discount are not negotiated.",
                            line.product_id.display_name,
                        )
                    )
        return super().write(vals)
