# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Repair Parts Picking",
    "summary": "Return the parts left over in the workshop when a repair order ends",
    "version": "18.0.1.0.0",
    "category": "Repair",
    "website": "https://github.com/OCA/repair",
    "author": "KMEE, Odoo Community Association (OCA)",
    "maintainers": ["mileo"],
    "license": "AGPL-3",
    "depends": ["repair_type", "repair_remove_destination"],
    "data": ["views/repair_views.xml"],
    "installable": True,
}
