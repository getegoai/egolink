---
document_status: authoritative
last_verified: 2026-08-11
verified_by: codex
---

# Board Matrix

All unknown fields must remain explicit. Do not infer hardware capability from product names.

| board_id | role | full model | MCU/SoC | IMU | microphone | GNSS | cellular | camera | storage | validation status |
|---|---|---|---|---|---|---|---|---|---|---|
| wearable-node-001 | `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | ESP32-S3 | QMI8658 observed | dual microphone path not yet accepted | no onboard GNSS used in P0 | no cellular | no product camera path | unknown | engineering evidence, not product acceptance |
| connectivity-node-001 | `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | ESP32-S3 + SIM7670G | external ATK-NB018 V1.0 QMI8658A observed at I2C `0x6A` on GPIO15/16; D2-006 captured 100 real non-mock samples; D2-007 again observed `WHO_AM_I=0x05` and confirmed idle stop but did not capture because LTE was not ready; D2-008 uploaded 26/26 real non-mock six-axis `sensor_sample` messages over Wi-Fi; D2-009 uploaded one bounded 100-sample window over Wi-Fi; D5-002 uploaded three further independently commanded 100-sample windows in one boot with zero read/mock/deadline failures and all three cadence qualified; FIELD-011 uploaded one bounded 100-sample window over LTE with zero read/mock/deadline failures and cadence qualified; mounting/calibration/accuracy and labels beyond one operator-confirmed flat-on-table stationary session remain unverified; evidence `reports/board_validation/20260810-qmi8658-probe/`, `reports/board_validation/20260810-d2007-imu-lte/`, `reports/board_validation/20260811-d2008-wifi-imu/`, `reports/board_validation/20260811-d2009-wifi-imu-window/`, `reports/board_validation/20260811-d5002-imu-seed/`, and `reports/field_validation/FIELD-011-20260811-001/` | SIM7670G PC-side AT no-fix evidence; firmware `request_location` scaffold observed as `driver_not_integrated` no-fix; FW-002B fix1 firmware-side SIM7670G UART/AT no-fix evidence observed with USB disconnected; FW-002C fix3 firmware-side SIM7670G UART/AT `fix=true` evidence observed with USB disconnected and `source_status=observed`; FIELD-011 same-image periodic location reported indoor `fix=false` / `no_fix` after LTE readiness | SIM7670G LTE/AT evidence; LTE-001B fix1 firmware-side LTE status observability observed with USB disconnected as `LTE_READY`, registered, PDP active, assigned IP present, RAT `LTE`, and cell/signal metrics; FW-003/LTE-004/LOC-004A/LOC-005A/LTE-006 fix1/LTE-007/LTE-008 fix1 raw LTE command/report/observation/ACK slices observed with USB disconnected; D2-007 did not reach LTE command polling because this run reported `LTE_SIM_NOT_READY`; D2-008, D2-009, and D5-002 intentionally bypassed cellular and used Wi-Fi; FIELD-011 completed one real QMI8658 window over LTE with ten chunks, one manifest and one matching `ok` ACK, and its periodic location reported `LTE_READY`, YOUR_WIFI_SSID registration, active PDP, assigned IP and RAT `LTE`; Wi-Fi Message Hub heartbeat/ACK, request_location scaffold, FW-002B SIM7670G UART/AT no-fix report, FW-002C resetdiag fix2 short stability observation, and FW-002C fix3 GNSS real-fix report observed with USB disconnected | OV5640 smoke evidence | TF/SD not product-verified | USB-Free Message Hub communication observed; request_location scaffold observed; FW-002B fix1 flashed and runtime-validated for no-fix AT diagnostics; FW-002B stability observer saw a seq regression/reboot; FW-002C resetdiag fix1 reproduced repeated `panic` resets; FW-002C resetdiag fix2 passed a 120-second USB-Free VPS stability observation with `seq_regressions=0`; FW-002C fix3 passed USB-Free firmware-side SIM7670G real-fix validation; LTE-001B fix1 passed USB-Free firmware-side LTE status observability; KR-005 passed one USB-Free LTE-006 fix1 reliability explainability slice; LTE-008 fix1 passed one USB-Free bounded retry visibility slice without exercising a failed retry; QMI8658 identity and bounded static sampling passed D2-006; D2-007 startup identity/idle-stop passed but bounded LTE window capture failed before sampling with zero raw frames; D2-008 low-rate real six-axis Wi-Fi telemetry passed with 26 samples; D2-009 bounded 100 x 50 ms Wi-Fi window and explicit export passed with one cadence-qualified training-disabled window; D5-002 passed three independent 100 x 50 ms Wi-Fi windows, 300 samples, 30 chunks, three manifests/ACKs, and a three-window explicit export; FIELD-011 passed one joint-image LTE/QMI bench window and same-image periodic LTE location observation after a full power cycle; outdoor GNSS fix, USB-free FIELD-011 operation, three walking windows, LTE long-run stability, reconnect recovery, camera/GNSS/LTE product capability, IMU calibration/accuracy/mounting, activity diversity beyond one stationary session, battery accuracy, product power behavior, and final enclosure/mounting GNSS acceptance remain bounded by named tests |
| pc-bridge | development bridge | Windows PC | host CPU | n/a | n/a | PC-side SIM7670G AT probe | PC-side USB/RNDIS/AT observation | n/a | local JSONL/session files | development-only, not product dependency |

## Latest FIELD-011 Combined Attempt

- The current connectivity-node image is FIELD-011
  `0.1.0-field011-gnss-imu` (`v0.1.0-30-g3f97cf7`, app SHA-256
  `388FFEAA...E7D0AB`). Its 2026-08-11 startup gate observed the external
  QMI8658A at `0x6A` and confirmed idle measurement stop.
- The first inserted-SIM readiness loop stayed `not_registered` with PDP
  unknown. A separately authorized read-only COM4 query returned
  `AT+CPIN? -> +CME ERROR: SIM not inserted`; this remains the initial failure
  evidence, not an APN diagnosis.
- After the operator's full power cycle, with no second flash or new command,
  the existing command completed over LTE. The retained evidence contains 100
  real samples after ten warm-ups, ten chunks, one manifest, one matching
  `ok` ACK, and zero read/mock/deadline failures. The explicit exporter scanned
  13 matching retained frames and reconstructed the ten chunks plus manifest.
  Observed cadence was 49,985/49,999/50,000 us minimum/mean/maximum, and the
  explicit export returned one valid cadence-qualified window. Periodic
  location from the same image reported LTE ready, home registration, active
  PDP, assigned IP and RAT `LTE`; indoor GNSS remained `fix=false` / `no_fix`.
  Validation status is therefore **joint-image bench pass / outdoor field
  pending**. The window remains activity-label `unknown`, and outdoor GNSS
  fix, fixed carry orientation, independent field power, calibration, and
  three walking windows remain unverified. Evidence:
  `reports/field_validation/FIELD-011-20260811-001/field011_bench_report.md`.

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
- The active physical board has no visible `VER2.0` silkscreen, so its formal
  revision remains unknown. D2-006 did observe the external QMI8658A on
  GPIO15/GPIO16, but that does not by itself identify the board revision or
  verify the onboard MAX17048 path. PWR-001 must retain explicit pin evidence.
- Current repository state remains: battery accuracy, charging state, 24h
  runtime, 48h target, and product power behavior are unverified until a named
  PWR-001 USB-Free run and report are recorded.
