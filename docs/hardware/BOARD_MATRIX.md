---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# Board Matrix

All unknown fields must remain explicit. Do not infer hardware capability from product names.

| board_id | role | full model | MCU/SoC | IMU | microphone | GNSS | cellular | camera | storage | validation status |
|---|---|---|---|---|---|---|---|---|---|---|
| wearable-node-001 | `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | ESP32-S3 | QMI8658 observed | dual microphone path not yet accepted | no onboard GNSS used in P0 | no cellular | no product camera path | unknown | engineering evidence, not product acceptance |
| connectivity-node-001 | `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | ESP32-S3 + SIM7670G | none verified | unknown | SIM7670G GNSS AT reachable, indoor no-fix | SIM7670G LTE/AT evidence | OV5640 smoke evidence | TF/SD not product-verified | communication/camera/GNSS capability evidence |
| pc-bridge | development bridge | Windows PC | host CPU | n/a | n/a | PC-side SIM7670G AT probe | PC-side USB/RNDIS/AT observation | n/a | local JSONL/session files | development-only, not product dependency |

## Rules

- `unknown` means not proven in this repository.
- `observed` means hardware evidence exists, but may still be engineering-only.
- `verified` must be backed by a named evidence file and acceptance gate.
- PC-side probe evidence must not be described as firmware-side product behavior.
