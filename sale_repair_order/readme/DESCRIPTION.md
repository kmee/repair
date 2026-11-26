Adds a "repair mode" to the sale order type. For the types set to "One repair
order per sale order", confirming a sale order opens a single repair order
(instead of one per line) carrying:

- the goods of the order as "Add" parts, linked to their sale line and without
  any delivery (the repair order reserves and consumes them);
- the services of the order in the "Services" tab, linked to their sale line.

Lines added or changed later in the confirmed sale order are synchronised to the
repair order, and parts and services added in the repair order reach the sale
order. Cancelling, copying, delivered quantities and the access of salespeople
to the repair order are handled.
