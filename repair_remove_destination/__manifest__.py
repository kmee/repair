# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Repair Remove Destination",
    "summary": "Destination of the removed and recycled parts, line by line",
    "version": "18.0.1.0.0",
    "category": "Repair",
    "website": "https://github.com/OCA/repair",
    "author": "KMEE, Odoo Community Association (OCA)",
    "maintainers": ["mileo"],
    "license": "AGPL-3",
    "depends": ["repair_type"],
    "data": [
        "views/stock_picking_type_views.xml",
        "views/repair_views.xml",
    ],
    "installable": True,
}
