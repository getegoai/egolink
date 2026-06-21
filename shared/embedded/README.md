# Embedded contract

`safety_model_contract.h` is the stable C representation of
`model_input.schema.json` and `model_output.schema.json` for firmware adapters.

Rules:

- Do not change field meaning, units, enum ordering, or contract version in a firmware-only change.
- Firmware may wrap this header in its own component API.
- JSON transport IDs and timestamps remain outside the compact inference struct.
- A future neural model must accept the same normalized values or publish a new contract version.
