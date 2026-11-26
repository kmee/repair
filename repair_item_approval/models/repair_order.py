# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RepairOrder(models.Model):
    _inherit = "repair.order"

    pending_item_count = fields.Integer(
        compute="_compute_pending_item_count", string="Items Awaiting Approval"
    )
    customer_wait_since = fields.Datetime(
        compute="_compute_pending_item_count",
        store=True,
        string="Waiting for the customer since",
    )

    @api.depends(
        "move_ids.approval_state",
        "move_ids.create_date",
        "repair_service_ids.approval_state",
        "repair_service_ids.create_date",
    )
    def _compute_pending_item_count(self):
        for repair in self:
            pending = repair._get_pending_items()
            repair.pending_item_count = sum(len(items) for items in pending)
            dates = [d for items in pending for d in items.mapped("create_date") if d]
            repair.customer_wait_since = min(dates) if dates else False

    def _get_pending_items(self):
        """Pending items, as a list of recordsets (moves, then services)."""
        self.ensure_one()
        return [
            self.move_ids.filtered(lambda m: m.approval_state == "pending"),
            self.repair_service_ids.filtered(lambda s: s.approval_state == "pending"),
        ]

    def _get_approval_amount_same_product(self, product, exclude=None):
        self.ensure_one()
        moves = self.move_ids.filtered(
            lambda m: m.repair_line_type == "add"
            and m.product_id == product
            and m.state != "cancel"
        )
        services = self.repair_service_ids.filtered(lambda s: s.product_id == product)
        total = 0.0
        for items in (moves, services):
            items = items.filtered(
                lambda i: i.approval_state != "rejected"
                and i.approval_origin != "order"
            )
            if exclude and exclude in items:
                items -= exclude
            total += sum(items.mapped("approval_amount"))
        return total

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def _notify_pending_items(self, items):
        """Tell the salesperson that items wait for the customer."""
        self.ensure_one()
        order = self.sale_order_id
        body = Markup("<p>%s</p>%s") % (
            _("Items awaiting approval were added:"),
            self.env["repair.item.approval.mixin"]._items_message([items]),
        )
        self.message_post(body=body)
        if not order:
            return
        order.message_post(body=body)
        user = order.user_id
        if not user:
            return
        summary = _("Repair items awaiting approval: %s", self.display_name)
        activity_model = self.env["mail.activity"].sudo()
        existing = activity_model.search(
            [
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
                ("summary", "=", summary),
                ("date_deadline", "=", fields.Date.context_today(self)),
            ],
            limit=1,
        )
        if not existing:
            order.sudo().activity_schedule(
                "mail.mail_activity_data_todo", summary=summary, user_id=user.id
            )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def action_approve_pending_items(self, note=False):
        """Internal approval, without the customer."""
        if not self.env.user.has_group(
            "repair_item_approval.group_repair_item_manager"
        ):
            raise UserError(_("Only the approval managers approve items internally."))
        if not (note or "").strip():
            raise UserError(_("A note is required to approve items internally."))
        for repair in self:
            items = repair._get_pending_items()
            for group in items:
                group._approve_item("manager", note=note)
            repair.message_post(
                body=Markup("<p>%s</p>%s<p>%s</p>")
                % (
                    _("Items approved internally:"),
                    self.env["repair.item.approval.mixin"]._items_message(items),
                    note,
                )
            )

    def action_refuse_pending_items(self, note=False):
        for repair in self:
            items = repair._get_pending_items()
            for group in items:
                group._reject_item(note=note)
            if any(items):
                repair.message_post(
                    body=Markup("<p>%s</p>%s")
                    % (
                        _("Items refused:"),
                        self.env["repair.item.approval.mixin"]._items_message(items),
                    )
                )

    def _check_no_pending_items(self):
        for repair in self:
            if repair.pending_item_count:
                raise UserError(
                    _(
                        "%(repair)s has %(count)s item(s) awaiting approval: "
                        "approve or refuse them before finishing the repair.",
                        repair=repair.display_name,
                        count=repair.pending_item_count,
                    )
                )

    def action_repair_end(self):
        self._check_no_pending_items()
        return super().action_repair_end()

    def action_repair_done(self):
        self._check_no_pending_items()
        return super().action_repair_done()

    def action_repair_cancel(self):
        res = super().action_repair_cancel()
        for repair in self:
            for group in repair._get_pending_items():
                group._reject_item(note=_("Repair order cancelled"), force=True)
        return res
