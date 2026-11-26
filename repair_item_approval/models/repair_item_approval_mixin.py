# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

APPROVAL_FIELDS = ("approval_state", "approval_origin", "approval_amount")


class RepairItemApprovalMixin(models.AbstractModel):
    _name = "repair.item.approval.mixin"
    _description = "Repair Item Approval Mixin"

    approval_state = fields.Selection(
        selection=[
            ("approved", "Approved"),
            ("pending", "Awaiting Approval"),
            ("rejected", "Refused"),
        ],
        default="approved",
        copy=False,
        index=True,
        readonly=True,
    )
    approval_origin = fields.Selection(
        selection=[
            ("order", "Sale order"),
            ("limit", "Below the limit"),
            ("customer", "Customer"),
            ("manager", "Internal approval"),
        ],
        copy=False,
        readonly=True,
    )
    item_class = fields.Selection(
        selection=[
            ("standard", "Standard"),
            ("mandatory", "Mandatory (regulation)"),
            ("recommended", "Recommended"),
        ],
        default="standard",
        required=True,
        copy=False,
    )
    approval_amount = fields.Monetary(
        currency_field="approval_currency_id",
        copy=False,
        readonly=True,
        help="Amount of the item when it was added, in the currency of the sale order.",
    )
    approval_currency_id = fields.Many2one(
        comodel_name="res.currency", compute="_compute_approval_currency_id"
    )
    refusal_note = fields.Text(copy=False)

    @api.depends("repair_id.sale_order_id.currency_id")
    def _compute_approval_currency_id(self):
        for item in self:
            item.approval_currency_id = (
                item.repair_id.sale_order_id.currency_id or self.env.company.currency_id
            )

    # ------------------------------------------------------------------
    # Rule
    # ------------------------------------------------------------------
    @api.model
    def _approval_unit_price(self, order, product, qty, uom):
        if order.pricelist_id:
            return order.pricelist_id._get_product_price(
                product, qty, uom=uom, date=order.date_order
            )
        return product.lst_price

    @api.model
    def _evaluate_approval(self, repair, product, qty, uom, exclude=None):
        """Decide how an item added in ``repair`` is born.

        Return ``{}`` when the rule does not apply (repair order without a
        main sale order in repair mode).
        """
        order = repair.sale_order_id
        if not order or order.repair_mode != "single":
            return {}
        company = order.company_id
        unit = (
            0.0
            if repair.under_warranty
            else self._approval_unit_price(order, product, qty, uom)
        )
        amount = unit * qty
        vals = {"approval_amount": amount}
        if repair.under_warranty:
            return {**vals, "approval_state": "approved", "approval_origin": "limit"}
        if order.partner_id.commercial_partner_id.repair_approve_all:
            return {**vals, "approval_state": "pending"}
        base = amount
        if company.repair_approval_base == "unit":
            base = unit
        elif company.repair_approval_cumulative:
            base += repair._get_approval_amount_same_product(product, exclude=exclude)
        limit = company.repair_approval_currency_id._convert(
            company.repair_approval_limit,
            order.currency_id,
            company,
            fields.Date.context_today(self),
        )
        if limit <= 0:
            return {**vals, "approval_state": "pending"}
        rounding = order.currency_id.rounding
        cmp = float_compare(base, limit, precision_rounding=rounding)
        within = cmp <= 0 if company.repair_approval_inclusive else cmp < 0
        return {
            **vals,
            "approval_state": "approved" if within else "pending",
            "approval_origin": "limit" if within else False,
        }

    def _approval_is_candidate(self, vals):
        return bool(vals.get("repair_id"))

    @api.model
    def _approval_apply_on_create(self, vals_list):
        if self.env.context.get("repair_approval_internal"):
            return
        Repair = self.env["repair.order"]
        for vals in vals_list:
            # the client never decides the approval
            for fname in APPROVAL_FIELDS:
                vals.pop(fname, None)
            if not self._approval_is_candidate(vals):
                continue
            if vals.get("sale_line_id"):
                vals.update({"approval_state": "approved", "approval_origin": "order"})
                continue
            product = self.env["product.product"].browse(vals.get("product_id"))
            if not product:
                continue
            uom = self.env["uom.uom"].browse(vals.get("product_uom")) or product.uom_id
            qty = vals.get("product_uom_qty", 1.0)
            vals.update(
                self._evaluate_approval(
                    Repair.browse(vals["repair_id"]), product, qty, uom
                )
            )

    def _check_approval_write(self, vals):
        if self.env.context.get("repair_approval_internal"):
            return
        if any(fname in vals for fname in APPROVAL_FIELDS):
            raise UserError(
                _(
                    "The approval of a repair item changes only through the "
                    "approval actions, never by editing it."
                )
            )
        if "product_uom_qty" in vals:
            for item in self.filtered(lambda i: i.approval_origin == "limit"):
                qty = vals["product_uom_qty"]
                if float_compare(qty, item.product_uom_qty, precision_digits=4) <= 0:
                    continue
                result = self._evaluate_approval(
                    item.repair_id, item.product_id, qty, item.product_uom, exclude=item
                )
                if result.get("approval_state") == "pending":
                    raise UserError(
                        _(
                            "The new quantity of %(product)s goes over the "
                            "approval limit: add a new line for the difference.",
                            product=item.product_id.display_name,
                        )
                    )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def _approval_write(self, vals):
        return self.with_context(repair_approval_internal=True).write(vals)

    def _approve_item(self, origin, note=False):
        """Pending items become approved and join the repair order."""
        items = self.filtered(lambda i: i.approval_state == "pending")
        items._approval_write({"approval_state": "approved", "approval_origin": origin})
        items._after_item_approved()
        return items

    def _reject_item(self, note=False, force=False):
        """Pending items are refused and leave the repair order."""
        items = self.filtered(lambda i: i.approval_state == "pending")
        if not force:
            mandatory = items.filtered(lambda i: i.item_class == "mandatory")
            if mandatory and not (note or "").strip():
                raise UserError(
                    _(
                        "A note is required to refuse a mandatory item: %s",
                        ", ".join(mandatory.mapped("product_id.display_name")),
                    )
                )
        items._approval_write(
            {"approval_state": "rejected", "refusal_note": note or False}
        )
        items._after_item_rejected()
        return items

    def _after_item_approved(self):
        """Hook: join the repair order (move or sale line)."""

    def _after_item_rejected(self):
        """Hook: leave the repair order."""

    @api.model
    def _items_message(self, groups):
        """HTML list of the items; ``groups`` is a list of recordsets."""
        lines = Markup("").join(
            Markup("<li>%s x %s</li>")
            % (escape(item.product_uom_qty), escape(item.product_id.display_name))
            for items in groups
            for item in items
        )
        return Markup("<ul>%s</ul>") % lines
