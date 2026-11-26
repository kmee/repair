# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class SaleOrderType(models.Model):
    _inherit = "sale.order.type"

    repair_mode = fields.Selection(
        selection=[
            ("none", "No repair order"),
            ("single", "One repair order per sale order"),
        ],
        default="none",
        required=True,
        help="With 'One repair order per sale order', confirming a sale order of "
        "this type opens a single repair order carrying the goods as parts and "
        "the services of the order, instead of delivering the goods.",
    )
    repair_picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Repair Operation Type",
        domain="[('code', '=', 'repair_operation')]",
        check_company=True,
        help="Operation type of the repair order. Empty: the repair operation "
        "type of the warehouse of the sale order.",
    )
