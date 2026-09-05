# P0 A0 Design-Pack Instructions

These instructions apply to `hardware/p0_a0/`.

- Every artifact here is a design input or review record until a later task
  explicitly releases fabrication data.
- Use `unknown`, `unverified`, `candidate_only`, or `official_source_checked`
  for evidence state. Never turn a vendor specification into measured product
  evidence.
- Record exact orderable identities separately from document revision,
  silicon/module revision, firmware revision, lot/date code, and lifecycle.
- Only primary manufacturer sources may support component facts. If the
  primary source is unavailable or conflicting, keep the field unresolved.
- Do not add manufacturing outputs, Gerbers, drill files, pick-and-place,
  purchase orders, private quotes, credentials, SIM identifiers, or device
  logs without an explicitly authorized task.
- A schematic, ERC/DRC result, or BOM in this folder never authorizes
  procurement, fabrication, assembly, flashing, RF transmission, or power-up.
- Preserve `P0-LOC`, `P0-CALL`, and `P0-SOS` as `NOT_RUN` until representative
  integrated-hardware evidence passes their accepted Gates.
