Adds the *Generate complementary quotation* button to the repair order: the
items awaiting approval (see `repair_item_approval`) go to a new sale order
linked to the same repair order, which inherits the customer, pricelist,
payment term, fiscal position, salesperson, team and sale order type of the
main order.

Confirming the complementary order (backend or customer portal) approves its
items: they reserve stock and are consumed by the repair order. Cancelling or
refusing it refuses the items, which leave the repair order and unblock its
conclusion. The method `_prepare_complementary_order_vals` is the extension
point for other modules to make the complementary order inherit more fields.
