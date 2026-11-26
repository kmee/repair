# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class RepairService(models.Model):
    _inherit = "repair.service"

    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    sale_order_id = fields.Many2one(
        related="sale_line_id.order_id", string="Sale Order", store=False
    )

    def _prepare_sale_order_line_vals(self, product_qty):
        vals = super()._prepare_sale_order_line_vals(product_qty)
        if not self.repair_id.under_warranty:
            # Let the pricelist of the sale order price the service
            vals.pop("price_unit", None)
        return vals

    def _create_repair_sale_order_line(self):
        """Create the sale lines and remember which line each service made."""
        services = self.filtered(
            lambda s: s.repair_id.sale_order_id and not s.sale_line_id
        )
        if not services:
            return
        vals_list = [
            service._prepare_sale_order_line_vals(service.product_uom_qty)
            for service in services
        ]
        lines = (
            self.env["sale.order.line"]
            .sudo()
            .with_context(skip_repair_order_sync=True)
            .create(vals_list)
        )
        for service, line in zip(services, lines, strict=True):
            service.sale_line_id = line

    @api.model_create_multi
    def create(self, vals_list):
        services = super().create(vals_list)
        if not self.env.context.get("skip_repair_order_sync"):
            services._create_repair_sale_order_line()
        return services

    def write(self, vals):
        res = super().write(vals)
        if "product_uom_qty" in vals and not self.env.context.get(
            "skip_repair_order_sync"
        ):
            for service in self.filtered("sale_line_id"):
                service.sale_line_id.with_context(skip_repair_order_sync=True).write(
                    {"product_uom_qty": service.product_uom_qty}
                )
        return res

    def unlink(self):
        lines = self.sale_line_id
        res = super().unlink()
        if not self.env.context.get("skip_repair_order_sync"):
            lines.with_context(skip_repair_order_sync=True).filtered(
                lambda line: line.state != "cancel"
            ).write({"product_uom_qty": 0.0})
        return res
