# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Sale Repair Order",
    "summary": "One repair order per sale order, driven by the sale order type",
    "version": "18.0.1.0.0",
    "category": "Repair",
    "website": "https://github.com/OCA/repair",
    "author": "KMEE, Odoo Community Association (OCA)",
    "maintainers": ["mileo"],
    "license": "AGPL-3",
    "depends": ["repair", "repair_service", "sale_stock", "sale_order_type"],
    "data": [
        "security/ir.model.access.csv",
        "security/repair_security.xml",
        "views/sale_order_type_views.xml",
        "views/sale_order_views.xml",
        "views/repair_views.xml",
    ],
    "installable": True,
}
