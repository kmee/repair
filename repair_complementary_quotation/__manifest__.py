# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Repair Complementary Quotation",
    "summary": "Quote the pending items of a repair order in a complementary "
    "sale order",
    "version": "18.0.1.0.0",
    "category": "Repair",
    "website": "https://github.com/OCA/repair",
    "author": "KMEE, Odoo Community Association (OCA)",
    "maintainers": ["mileo"],
    "license": "AGPL-3",
    "depends": ["repair_item_approval", "sale_management"],
    "data": [
        "security/repair_complementary_quotation_security.xml",
        "views/repair_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
}
