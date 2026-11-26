Adds an approval step to the items (parts and services) that the technician
adds in a repair order served by a sale order in repair mode (see
`sale_repair_order`).

- An item below the limit is applied directly. The limit is an amount in a
  configurable currency, set on the company (default USD 100), compared with
  the line total ("below", strict, by default) and converted with the rate of
  the day.
- A customer flagged "approves every repair item" gets every added item
  waiting for approval.
- A pending item does not reserve stock, is not consumed and does not reach the
  sale order. The salesperson of the order receives an activity.
- The repair order cannot be finished with pending items.
- Items have a class: standard, mandatory by the regulation (price and discount
  locked, refusal needs a note) or recommended.
