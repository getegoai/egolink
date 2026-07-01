---
document_status: authoritative
last_verified: 2026-07-01
verified_by: codex
---

# Board Matrix

All unknown fields must remain explicit. Do not infer hardware capability from product names.

| board_id | role | full model | MCU/SoC | IMU | microphone | GNSS | cellular | camera | storage | validation status |
|---|---|---|---|---|---|---|---|---|---|---|
| wearable-node-001 | `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | ESP32-S3 | QMI8658 observed | dual microphone path not yet accepted | no onboard GNSS used in P0 | no cellular | no product camera path | unknown | engineering evidence, not product acceptance |
| connectivity-node-001 | `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | ESP32-S3 + SIM7670G | none verified | SIM7670G PC-side AT no-fix evidence; firmware `request_location` scaffold observed as `driver_not_integrated` no-fix; FW-002B fix1 firmware-side SIM7670G UART/AT no-fix evidence observed with USB disconnected; FW-002C fix3 firmware-side SIM7670G UART/AT `fix=true` evidence observed with USB disconnected and `source_status=observed` | SIM7670G LTE/AT evidence; LTE-001B fix1 firmware-side LTE status observability observed with USB disconnected as `LTE_READY`, registered, PDP active, assigned IP present, RAT `LTE`, and cell/signal metrics; FW-003/LTE-004/LOC-004A/LOC-005A/LTE-006 fix1 raw LTE command/report/observation/ACK slices observed with USB disconnected; Wi-Fi Message Hub heartbeat/ACK, request_location scaffold, FW-002B SIM7670G UART/AT no-fix report, FW-002C resetdiag fix2 short stability observation, and FW-002C fix3 GNSS real-fix report observed with USB disconnected | OV5640 smoke evidence | TF/SD not product-verified | USB-Free Message Hub communication observed; request_location scaffold observed; FW-002B fix1 flashed and runtime-validated for no-fix AT diagnostics; FW-002B stability observer saw a seq regression/reboot; FW-002C resetdiag fix1 reproduced repeated `panic` resets; FW-002C resetdiag fix2 passed a 120-second USB-Free VPS stability observation with `seq_regressions=0`; FW-002C fix3 passed USB-Free firmware-side SIM7670G real-fix validation; LTE-001B fix1 passed USB-Free firmware-side LTE status observability; KR-005 passed one USB-Free LTE-006 fix1 reliability explainability slice; LTE long-run stability, reconnect recovery, camera/GNSS/LTE product capability, battery accuracy, product power behavior, and final enclosure/mounting GNSS acceptance remain bounded by named tests |
| pc-bridge | development bridge | Windows PC | host CPU | n/a | n/a | PC-side SIM7670G AT probe | PC-side USB/RNDIS/AT observation | n/a | local JSONL/session files | development-only, not product dependency |

## Rules

- `unknown` means not proven in this repository.
- `observed` means hardware evidence exists, but may still be engineering-only.
- `verified` must be backed by a named evidence file and acceptance gate.
- PC-side probe evidence must not be described as firmware-side product behavior.
