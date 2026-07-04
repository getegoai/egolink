---
document_status: authoritative
last_verified: 2026-07-03
verified_by: codex
---

# Board Matrix

All unknown fields must remain explicit. Do not infer hardware capability from product names.

| board_id | role | full model | MCU/SoC | IMU | microphone | GNSS | cellular | camera | storage | validation status |
|---|---|---|---|---|---|---|---|---|---|---|
| wearable-node-001 | `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | ESP32-S3 | QMI8658 observed | dual microphone path not yet accepted | no onboard GNSS used in P0 | no cellular | no product camera path | unknown | engineering evidence, not product acceptance |
| connectivity-node-001 | `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | ESP32-S3 + SIM7670G | none verified | SIM7670G PC-side AT no-fix evidence; firmware `request_location` scaffold observed as `driver_not_integrated` no-fix; FW-002B fix1 firmware-side SIM7670G UART/AT no-fix evidence observed with USB disconnected; FW-002C fix3 firmware-side SIM7670G UART/AT `fix=true` evidence observed with USB disconnected and `source_status=observed` | SIM7670G LTE/AT evidence; LTE-001B fix1 firmware-side LTE status observability observed with USB disconnected as `LTE_READY`, registered, PDP active, assigned IP present, RAT `LTE`, and cell/signal metrics; FW-003/LTE-004/LOC-004A/LOC-005A/LTE-006 fix1/LTE-007/LTE-008 fix1 raw LTE command/report/observation/ACK slices observed with USB disconnected; Wi-Fi Message Hub heartbeat/ACK, request_location scaffold, FW-002B SIM7670G UART/AT no-fix report, FW-002C resetdiag fix2 short stability observation, and FW-002C fix3 GNSS real-fix report observed with USB disconnected | OV5640 smoke evidence | TF/SD not product-verified | USB-Free Message Hub communication observed; request_location scaffold observed; FW-002B fix1 flashed and runtime-validated for no-fix AT diagnostics; FW-002B stability observer saw a seq regression/reboot; FW-002C resetdiag fix1 reproduced repeated `panic` resets; FW-002C resetdiag fix2 passed a 120-second USB-Free VPS stability observation with `seq_regressions=0`; FW-002C fix3 passed USB-Free firmware-side SIM7670G real-fix validation; LTE-001B fix1 passed USB-Free firmware-side LTE status observability; KR-005 passed one USB-Free LTE-006 fix1 reliability explainability slice; LTE-008 fix1 passed one USB-Free bounded retry visibility slice without exercising a failed retry; LTE long-run stability, reconnect recovery, camera/GNSS/LTE product capability, battery accuracy, product power behavior, and final enclosure/mounting GNSS acceptance remain bounded by named tests |
| pc-bridge | development bridge | Windows PC | host CPU | n/a | n/a | PC-side SIM7670G AT probe | PC-side USB/RNDIS/AT observation | n/a | local JSONL/session files | development-only, not product dependency |

## Rules

- `unknown` means not proven in this repository.
- `observed` means hardware evidence exists, but may still be engineering-only.
- `verified` must be backed by a named evidence file and acceptance gate.
- PC-side probe evidence must not be described as firmware-side product behavior.

## Cellular Calling/SMS Boundary

- `connectivity-node-001` has observed LTE data transport for Message Hub D1
  uploads, command polling, raw POST retries, and location/power telemetry.
- Voice calling and SMS are `unverified`: this repository has no implemented
  call/SMS firmware path, no accepted ATD/ATA/CMGS evidence, and no product
  emergency calling/SMS/dispatch claim.
- Any future live dialing or SMS probe must be a separate operator-approved
  hardware task with redacted destination data and explicit cost/privacy
  handling.

## PWR-001 Battery Sensing Audit

- connectivity-node-001 vendor reference:
  https://docs.waveshare.com/ESP32-S3-SIM7670G-4G documents the onboard
  battery management path as MAX17048G fuel gauge plus ETA6098 charger and
  CN3791 solar charger.
- The same vendor page documents battery I2C pins by board revision:
  V2 uses SDA GPIO15 / SCL GPIO16; V1 uses SDA GPIO3 / SCL GPIO2.
- The active physical board revision is not yet recorded in repo evidence.
  PWR-001 firmware therefore keeps the MAX17048 backend as explicit opt-in and
  defaults the opt-in pin map to the documented V2 pins. Operators must confirm
  the board revision or override pins before flash/runtime evidence can be
  trusted.
- Current repository state remains: battery accuracy, charging state, 24h
  runtime, 48h target, and product power behavior are unverified until a named
  PWR-001 USB-Free run and report are recorded.
