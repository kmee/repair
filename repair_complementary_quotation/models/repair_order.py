# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError


class RepairOrder(models.Model):
    _inherit = "repair.order"

    complement_count = fields.Integer(compute="_compute_complement_count")
    has_unquoted_pending_items = fields.Boolean(
        compute="_compute_has_unquoted_pending_items"
    )

    @api.depends("sale_order_ids.repair_role")
    def _compute_complement_count(self):
        for repair in self:
            repair.complement_count = len(
                repair.sale_order_ids.filtered(lambda o: o.repair_role == "complement")
            )

    @api.depends(
        "move_ids.approval_state",
        "move_ids.sale_line_id",
        "repair_service_ids.approval_state",
        "repair_service_ids.sale_line_id",
    )
    def _compute_has_unquoted_pending_items(self):
        for repair in self:
            repair.has_unquoted_pending_items = any(repair._get_unquoted_items())

    def _get_unquoted_items(self):
        self.ensure_one()
        return [
            items.filtered(lambda i: not i.sale_line_id)
            for items in self._get_pending_items()
        ]

    def action_view_complements(self):
        self.ensure_one()
        orders = self.sale_order_ids.filtered(lambda o: o.repair_role == "complement")
        action = {
            "name": _("Complementary Orders"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "domain": [("id", "in", orders.ids)],
            "view_mode": "list,form",
        }
        if len(orders) == 1:
            action.update({"view_mode": "form", "res_id": orders.id})
        return action

    def _prepare_complementary_line_vals(self, order, item):
        """Sale line of a pending item (the price comes from the pricelist)."""
        name = item.product_id.get_product_multiline_description_sale()
        if item.item_class == "mandatory":
            name = "\n".join([name, _("Mandatory by the regulation")])
        return {
            "order_id": order.id,
            "product_id": item.product_id.id,
            "product_uom_qty": item.product_uom_qty,
            "product_uom": item.product_uom.id,
            "name": name,
            "repair_item_class": item.item_class,
        }

    def action_create_complementary_order(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "repair_complementary_quotation.group_repair_quote"
        ):
            raise AccessError(_("Only quotation users generate complementary orders."))
        main = self.sale_order_id
        if not main or main.state not in ("sale", "done"):
            raise UserError(
                _("The main sale order of %s must be confirmed.", self.display_name)
            )
        if main.repair_mode != "single":
            raise UserError(_("The sale order type is not in repair mode."))
        items = self._get_unquoted_items()
        if not any(items):
            raise UserError(_("There are no pending items to quote."))
        order = (
            self.env["sale.order"]
            .create(main._prepare_complementary_order_vals(self))
            .with_context(skip_repair_order_sync=True)
        )
        order.write(
            {
                "order_line": [
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": _("Complementary of %s", self.display_name),
                        }
                    )
                ]
            }
        )
        for group in items:
            for item in group:
                line = self.env["sale.order.line"].create(
                    self._prepare_complementary_line_vals(order, item)
                )
                item.sudo().sale_line_id = line
        self.message_post(
            body=_("Complementary order %s generated.", order.display_name)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "views": [[False, "form"]],
            "res_id": order.id,
        }
