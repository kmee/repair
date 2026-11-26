# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Repair Item Approval",
    "summary": "Approval of the items added in a repair order by amount limit",
    "version": "18.0.1.0.0",
    "category": "Repair",
    "website": "https://github.com/OCA/repair",
    "author": "KMEE, Odoo Community Association (OCA)",
    "maintainers": ["mileo"],
    "license": "AGPL-3",
    "depends": ["sale_repair_order", "mail"],
    "data": [
        "security/repair_item_approval_security.xml",
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "wizard/repair_pending_item_wizard_views.xml",
        "views/repair_views.xml",
    ],
    "installable": True,
}
