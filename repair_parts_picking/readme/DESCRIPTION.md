Closes the stock cycle of the parts of a repair order that takes its parts from a
workshop location:

- The separation (warehouse to workshop) needs no code: set the repair operation
  type with the workshop as source of the parts (module `repair_type`) and a pull
  route that brings the parts from the warehouse to the workshop. The transfer
  is generated when the repair order confirms its parts.
- When the repair order ends, the parts separated to the workshop and not used
  return to the warehouse (lot and serial number preserved) by a transfer linked
  to the repair order. The button *Return leftover parts* does the same at any
  time. The parts removed from the aircraft go to their own destinations (see
  `repair_remove_destination`).

- Removed parts (lines Remove and Recycle): with the operation type option
  *Removed Parts by Transfer*, the part stops in a staging location of the
  workshop and, when the repair order ends, one transfer per destination
  (Quarantine, To be recovered, Condemned) is generated for the stock operator to
  validate, so nothing disappears. Without the option, the part goes straight to
  its destination.
