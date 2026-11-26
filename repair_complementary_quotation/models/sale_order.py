# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    complement_of_id = fields.Many2one(
        comodel_name="sale.order",
        string="Complementary of",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Main sale order of the repair order this order complements.",
    )
    complement_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="complement_of_id",
        string="Complementary Orders",
        copy=False,
    )

    def copy(self, default=None):
        if any(order.repair_role == "complement" for order in self):
            raise UserError(
                _(
                    "A complementary order cannot be duplicated: generate a new "
                    "one from the repair order."
                )
            )
        return super().copy(default=default)

    def _prepare_complementary_order_vals(self, repair):
        """Values of the complementary order of ``self`` (the main order).

        Extension point: other modules add what a complementary order inherits.
        """
        self.ensure_one()
        vals = {
            "partner_id": self.partner_id.id,
            "partner_invoice_id": self.partner_invoice_id.id,
            "partner_shipping_id": self.partner_shipping_id.id,
            "pricelist_id": self.pricelist_id.id,
            "payment_term_id": self.payment_term_id.id,
            "fiscal_position_id": self.fiscal_position_id.id,
            "company_id": self.company_id.id,
            "warehouse_id": self.warehouse_id.id,
            "type_id": self.type_id.id,
            "user_id": self.user_id.id,
            "team_id": self.team_id.id,
            "client_order_ref": self.client_order_ref,
            "origin": self.name,
            "repair_id": repair.id,
            "repair_role": "complement",
            "complement_of_id": self.id,
        }
        if "opportunity_id" in self._fields:  # sale_crm, when installed
            vals["opportunity_id"] = self.opportunity_id.id
        return vals

    def _get_complement_items(self):
        """Items linked to the lines of this order: [moves, services]."""
        self.ensure_one()
        moves = self.order_line.move_ids.sudo().filtered("repair_id")
        services = (
            self.env["repair.service"]
            .sudo()
            .search([("sale_line_id", "in", self.order_line.ids)])
        )
        return [moves, services]

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self.filtered(lambda o: o.repair_role == "complement"):
            items = [
                group.filtered(lambda i: i.approval_state == "pending")
                for group in order._get_complement_items()
            ]
            if not any(items):
                continue
            for group in items:
                group._approve_item("customer")
            who = order.signed_by or self.env.user.name
            order.repair_id.message_post(
                body=Markup("<p>%s</p>%s")
                % (
                    _("Complementary order %(order)s confirmed by %(who)s:")
                    % {"order": order.name, "who": who},
                    self.env["repair.item.approval.mixin"]._items_message(items),
                )
            )
        return res

    def _action_cancel(self):
        for order in self.filtered(lambda o: o.repair_role != "complement"):
            confirmed = order.complement_ids.filtered(
                lambda o: o.state in ("sale", "done")
            )
            if confirmed:
                raise UserError(
                    _(
                        "%(order)s has confirmed complementary orders (%(names)s): "
                        "they are part of the repair.",
                        order=order.display_name,
                        names=", ".join(confirmed.mapped("name")),
                    )
                )
        main = self.filtered(lambda o: o.repair_role != "complement")
        open_complements = main.complement_ids.filtered(
            lambda o: o.state in ("draft", "sent")
        )
        if open_complements:
            open_complements._action_cancel()
        complements = self.filtered(lambda o: o.repair_role == "complement")
        items_by_order = {o: o._get_complement_items() for o in complements}
        res = super()._action_cancel()
        for order, items in items_by_order.items():
            pending = [
                group.filtered(lambda i: i.approval_state == "pending")
                for group in items
            ]
            if any(pending):
                for group in pending:
                    group._reject_item(
                        note=_("Complementary order %s cancelled", order.name),
                        force=True,
                    )
                order.repair_id.message_post(
                    body=Markup("<p>%s</p>%s")
                    % (
                        _("Complementary order %s was refused or cancelled:")
                        % order.name,
                        self.env["repair.item.approval.mixin"]._items_message(pending),
                    )
                )
        return res
