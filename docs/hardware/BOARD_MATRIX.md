---
document_status: authoritative
last_verified: 2026-09-16
verified_by: codex
---

# Board Matrix

All unknown fields must remain explicit. Do not infer hardware capability from product names.

## 2026-09-16 current empty-spool LTE throughput checkpoint

`connectivity-node-001` currently has app-only image
`0.1.0-camera-lte-trial-017`, run
`camera-lte-trial-20260916-017`. The 1,204,416-byte application has SHA-256
`07CF1EF3FEA13548FB9B7F5EF8F5C965FE6B6BF53EBD6AE9369F2E8CF0223529`;
ELF SHA-256 is
`F9D47609BEB820803B2919B1F01B70D3B82E62FF8928F84CCD1ABB294919854A`.
The app-only write at `0x200000` and an independent verification both matched.

Before that write, the complete post-run016 1 MiB `ego_collection` partition
was backed up. Only `[0x500000,0x600000)` was then erased under the existing
authorization, and its complete readback was all `0xFF`; the application, NVS,
`ego_media` and `ego_outbox` partitions were not targeted. Run017 therefore
started with an empty ordinary-observation spool.

The 620-second serial capture around the 600-second firmware bound used USB for
power and serial while the ESP32-managed SIM7670G PPP interface carried data.
It retained 248 ordinary uploads, all HTTP 200, exact-identity matched and
locally acknowledged, with 65 TLS handshakes. The initial queued-byte peak of
55,842 cleared by about 124 seconds; the steady range was 0-6,658 bytes and the
final queue was zero. Evictions, RAM-pending records, errors, stale/busy status,
link-down, panic and Camera events were all zero, and the bounded run completed
once. Camera command polling was increased from 2 to 15 seconds while sensor
rates remained unchanged. This closes the immediate ordinary-observation
throughput blocker for one 10-minute empty-spool bench condition only; it does
not prove historical-backlog recovery, endurance or FIELD-020. The tracked
FIELD-020 overlay now carries the 15-second polling setting.

No photo command was issued, so run015 remains the real-LTE Camera proof. USB
power/serial means run017 is not independent-power evidence. Browser preview,
timed/offline/reboot photo behavior, a controlled route transition, endurance,
FIELD-020 and every P0 Gate remain unverified/`NOT_RUN`.

## 2026-09-16 prior LTE concurrency checkpoint

Before run017, `connectivity-node-001` executed app-only image
`0.1.0-camera-lte-trial-016`, run
`camera-lte-trial-20260916-016`. The 1,204,416-byte application has SHA-256
`A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`;
ELF SHA-256 is
`1E09F4AF1279BC08CCA0C36DF642B25ECFEC8638B8693EE4CDDFBEDD26FF7FAD`.
The app-only write at `0x200000` and an independent verification both matched;
no other partition was erased or written.

Its 180-second USB-powered/serial-observed run brought up the ESP32-managed
SIM7670G PPP path and retained 25 ordinary LTE HTTP-200 uploads plus nine fresh
healthy LTE status snapshots. It recorded no stale/busy status, link-down,
panic or Camera event. Queued bytes still rose from 502,511 to 605,143 while
persisted records rose from 3 to 66 and acknowledgements from 0 to 21, so the
run also confirms a remaining sustained-throughput blocker. No photo command
was sent; this is a focused
status/PPP-concurrency regression, not a repeat Camera closure, independent-
power run or field result. The private log SHA-256 is
`45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.

## 2026-09-16 real-LTE manual Camera checkpoint

Before that regression, `connectivity-node-001` executed app-only image
`0.1.0-camera-lte-trial-015`, run
`camera-lte-trial-20260916-015`, application SHA-256
`281C060625DC5F99EA37C7CAD01C419B65CF7D005ACC98334FFDB6090ED58B26`.
The combined collector's second bounded modem attempt established the
ESP32-managed SIM7670G PPP interface. Exactly one authenticated manual command
then produced a current 320 x 240 OV5640 JPEG, saved it locally, uploaded its
metadata and 3,957 content bytes over LTE, received exact VPS command/content
ACKs and permitted an authorized private Guardian API download whose SHA-256
matched device and server state.

The retained 300-second window also contains continuing GNSS/no-fix, external
QMI8658A, LTE and available-power observations after capture, 43 ordinary LTE
HTTP-200 uploads, and no panic, USB enumeration failure or unexpected reboot.
USB still supplied power/serial/flash, so this is not USB-free or
independent-power evidence. Browser rendering, timed/outage/restart capture,
controlled route transition, endurance, FIELD-020, product Camera selection
and every P0 Gate remain unverified/`NOT_RUN`. The post-run spool backup used
`--after no_reset` and left the board in ROM bootloader at that checkpoint.
See
[CAMERA-LTE-MANUAL-20260916-001](CAMERA_LTE_MANUAL_CLOSURE_20260916.md).

## 2026-09-09 bounded cleanup checkpoint

`connectivity-node-001` was reidentified as ESP32-S3 rev v0.2, MAC
`02:00:00:00:00:03`, 16 MiB physical flash, through CH343 `COM3` serial
`5B91047400`. Its `ego_collection` partition was backed up, selectively erased
and fully read back empty under the founder's cleanup authorization. The
application, NVS and `ego_outbox` were not targeted. The board is deliberately
left in the ROM bootloader at that checkpoint; the later run006 app-only flash
superseded this transient state. This cleanup operation itself adds no Camera,
LTE, GNSS or IMU capability evidence. AMOLED is not part of the current A-line
setup. See
[PRIVACY_WIFI_SPOOL_PURGE_20260909](PRIVACY_WIFI_SPOOL_PURGE_20260909.md).

## 2026-09-09 Camera media-range preflight

The same identified board's proposed `[0x600000,0xF00000)` `ego_media` range
was read in full to a private ignored backup. All 9,437,184 bytes were `0xFF`,
and a subsequent `verify_flash` comparison matched the saved digest. This
passes storage ownership only: no write occurred, the board remains in ROM
bootloader at that checkpoint, and Camera/shared-I2C/runtime/LTE evidence was
unchanged by the read. See
[CAMERA-MEDIA-001](CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md).

## 2026-09-09 prior Camera trial checkpoint

At that checkpoint the board contained the app-only run006 Camera trial image
from commit
`80c5e86fd`, application SHA-256
`EE2FA5A3D2B65186B3A80597C1C574CAA66CBEB66DA5A5EE2125B3086C299D0D`.
It is an explicit `UNVERIFIED_TRIAL`, Wi-Fi/no-SIM profile with LTE PPP
disabled. In bounded joint-firmware boots it identified OV5640, captured real
320 x 240 JPEGs, recovered an older durable photo across reboot, and completed
a fresh run006b exact command/content ACK with byte-for-byte VPS storage while
GNSS and external-IMU collection continued. No panic, brownout, watchdog,
stack overflow or unexpected reboot was observed in those windows.

This is historical manual Wi-Fi bench evidence only. It does not verify LTE,
timed/offline capture, Web visual preview, independent power, FIELD-020,
endurance, product power or Camera product selection. Exact identities and
honest failure/pass boundaries are in
[CAMERA-SHARED-I2C-TRIAL-20260909-001](CAMERA_SHARED_I2C_TRIAL_20260909.md).

## Current Camera integration constraints

The candidate places OV5640 `0x3C`, MAX17048 `0x36` and QMI8658A `0x6A` on
I2C0 GPIO15/16 at 100 kHz. Bounded Camera/IMU coexistence was observed in
run006 and again around the run015 real-LTE manual capture, but the Camera
profile remains `trial_unverified` and no electrical endurance or product Gate
follows from it. The candidate uses an internal-DRAM
framebuffer and legacy shared-I2C0. Camera PCLK and the board's TF
card-detect path both use GPIO46, so the first joint test requires the TF card
physically removed and its driver disabled. GPIO39-42 must also remain free of
external JTAG. Runtime resource watermarks and QMI8658A/MAX17048 continuity are
acceptance evidence, not facts inferred from the successful isolated smoke.

## 2026-09-06 previous collector state

At that checkpoint the connectivity node retained collector app 985,984 B,
SHA-256
`1d67d2319f30d89ce794f0b7e1b3051130163a3d7b8ce92764f8c0bcc9ab6f25`.
Run 006 stopped normally at 07:32:47 UTC and COM3 closed. This is a Wi-Fi-only,
300-second USB bench profile with real QMI8658 and MAX17048 collection; it is
not field, LTE or product evidence. FW-007 remains the verified rollback
fallback and is not the current image. Evidence:
`reports/board_validation/COLLECTION-20260906-006/README.md`.

## 2026-09-05 bounded connectivity boot and recovery

[Convergence run 001](../development/RUNTIME_CONVERGENCE_20260905_RUN001.md)
actually identified connectivity MCU MAC `02:00:00:00:00:03`, ESP32-S3 rev v0.2,
16 MiB physical flash, through CH343 COM3 (`VID_1A86&PID_55D3`, serial
`5B91047400`). Firmware still declares the retained 2 MiB geometry.
The operator removed the SIM while powered off. One live candidate boot reached
Wi-Fi/UTC anchoring, then stopped at outbox initialization before modem start.
That initial boot established no GNSS fix or secure device upload.
Subsequent runs 005–007 on the same node delivered 16 real no-fix states over
authenticated certificate-verified Wi-Fi HTTPS, with matched durable ACKs and
bound Guardian API evidence. Run 007 completed four 30-second powered dwells;
no coordinate fix was observed and antenna/sky placement remains unconfirmed.
FW-007 was restored at 10:48:12 UTC with three verified transfers and 30.166 s
descriptor smoke, COM3 closed. Exact source/image/board/time evidence:
`reports/board_validation/P0-CONVERGENCE-20260905-007/integration_result.json`.
This is USB-powered bench evidence; fresh LTE, CALL, physical SOS, field accuracy
and product acceptance remain unverified. Historical capability dates stay intact.

The single preflash readback proved the actual FW-007 app is **985,168 B** with
SHA-256 `a9894a86834aa6517e5947f011b50a8af223656d74fcfb68f911ee39efa36c7d`,
matching the existing local FW-007 artifact exactly. This differs from the old
984,912 B / `8f3508...3799` historical claim retained below. After operator
acceptance of that specific correction, the actual three-region set was restored
with transfer hashes verified and a 30.17-second startup smoke on COM3 completed
at 07:26:32 UTC. Descriptor `fw007-e9ca7a4` was observed; NVS was not erased.
Evidence: `reports/board_validation/P0-CONVERGENCE-20260905-001/`;
`actual_fw007_restore_result.json` supplies exact images, path, MAC and times.
Wearable UI-001 was not touched. Existing capability dates below remain intact.

The long accumulated cells below retain each dated experiment. For
`connectivity-node-001`, the 2026-09-16 checkpoints above supersede only the
older run006 phrases that call the Wi-Fi trial the current image or say that no
real-LTE Camera closure exists. Run015 supplies that one bounded manual
LTE/API-integrity slice, run016 retains its negative queue-growth result, and
run017 is the current flashed empty-spool LTE-throughput checkpoint; every
other unverified limitation in the row remains.

| board_id | role | full model | MCU/SoC | IMU | microphone | GNSS | cellular | camera | storage | validation status |
|---|---|---|---|---|---|---|---|---|---|---|
| wearable-node-001 | `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | ESP32-S3 | QMI8658 observed | basic input/output endpoints accepted for transition: operator-confirmed speech correlated with an approximately tenfold logical-channel RMS rise in run 007, and run 008 output was clear/normal overall; physical channel mapping, full duplex and product acoustics remain unverified | no onboard GNSS used in P0 | no cellular | no product camera path | unknown | CALL-010 development-board endpoint evidence only; no raw audio retained, 4G board untouched, UI-001 restored; not `P0-CALL` or product acceptance |
| connectivity-node-001 | `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | ESP32-S3 + SIM7670G | external ATK-NB018 V1.0 QMI8658A observed at I2C `0x6A` on GPIO15/16; D2-006 captured 100 real non-mock samples; D2-007 again observed `WHO_AM_I=0x05` and confirmed idle stop but did not capture because LTE was not ready; D2-008 uploaded 26/26 real non-mock six-axis `sensor_sample` messages over Wi-Fi; D2-009 uploaded one bounded 100-sample window over Wi-Fi; D5-002 uploaded three further independently commanded 100-sample windows in one boot with zero read/mock/deadline failures and all three cadence qualified; FIELD-011 uploaded one bounded 100-sample window over LTE with zero read/mock/deadline failures and cadence qualified; FW-006 again observed QMI identity, idle-stop and a later real `mock=false` sample; run006 observed external-IMU work continuing around bounded joint-firmware OV5640 capture/upload; mounting/calibration/accuracy and other activity labels remain unverified; evidence `reports/board_validation/20260810-qmi8658-probe/`, `reports/board_validation/20260810-d2007-imu-lte/`, `reports/board_validation/20260811-d2008-wifi-imu/`, `reports/board_validation/20260811-d2009-wifi-imu-window/`, `reports/board_validation/20260811-d5002-imu-seed/`, `reports/field_validation/FIELD-011-20260811-001/`, `reports/firmware_validation/FW-006-20260812-001/`, and `docs/hardware/CAMERA_SHARED_I2C_TRIAL_20260909.md` | SIM7670G PC-side AT no-fix evidence; firmware `request_location` scaffold observed as `driver_not_integrated` no-fix; FW-002B fix1 firmware-side SIM7670G UART/AT no-fix evidence observed with USB disconnected; FW-002C fix3 firmware-side SIM7670G UART/AT `fix=true` evidence observed with USB disconnected and `source_status=observed`; FIELD-011 same-image periodic location reported indoor `fix=false` / `no_fix`; FW-006 contains the corrected parser but its bounded startup observed no fixed response, so that parser remains hardware-unverified | SIM7670G LTE/AT evidence; LTE-001B fix1 firmware-side LTE status observability observed with USB disconnected as `LTE_READY`, registered, PDP active, assigned IP present, RAT `LTE`, and cell/signal metrics; FW-003/LTE-004/LOC-004A/LOC-005A/LTE-006 fix1/LTE-007/LTE-008 fix1 raw LTE command/report/observation/ACK slices observed with USB disconnected; D2-007 did not reach LTE command polling because this run reported `LTE_SIM_NOT_READY`; D2-008, D2-009, D5-002 and Camera run006 intentionally bypassed cellular and used Wi-Fi; FIELD-011 completed one real QMI8658 window over LTE with ten chunks, one manifest and one matching `ok` ACK; FW-006 startup reached `LTE_READY` and posted periodic location/observation events; Wi-Fi Message Hub heartbeat/ACK, request_location scaffold, FW-002B SIM7670G UART/AT no-fix report, FW-002C resetdiag fix2 short stability observation, and FW-002C fix3 GNSS real-fix report observed with USB disconnected | OV5640 isolated smoke plus bounded run006 joint-firmware manual QVGA capture, reboot recovery, exact command/content ACK and byte-for-byte VPS storage over Wi-Fi; current image remains `UNVERIFIED_TRIAL`; real LTE, timed/offline, Web visual preview, product Camera and endurance remain unverified | TF/SD not product-verified | USB-Free Message Hub communication observed; request_location scaffold observed; FW-002B fix1 flashed and runtime-validated for no-fix AT diagnostics; FW-002B stability observer saw a seq regression/reboot; FW-002C resetdiag fix1 reproduced repeated `panic` resets; FW-002C resetdiag fix2 passed a 120-second USB-Free VPS stability observation with `seq_regressions=0`; FW-002C fix3 passed USB-Free firmware-side SIM7670G real-fix validation; LTE-001B fix1 passed USB-Free firmware-side LTE status observability; KR-005 passed one USB-Free LTE-006 fix1 reliability explainability slice; LTE-008 fix1 passed one USB-Free bounded retry visibility slice without exercising a failed retry; QMI8658 identity and bounded static sampling passed D2-006; D2-007 startup identity/idle-stop passed but bounded LTE window capture failed before sampling with zero raw frames; D2-008 low-rate real six-axis Wi-Fi telemetry passed with 26 samples; D2-009 bounded 100 x 50 ms Wi-Fi window and explicit export passed with one cadence-qualified training-disabled window; D5-002 passed three independent 100 x 50 ms Wi-Fi windows, 300 samples, 30 chunks, three manifests/ACKs, and a three-window explicit export; FIELD-011 passed one operator-confirmed stationary joint-image LTE/QMI bench window and same-image periodic LTE location observation after a full power cycle; FW-006 replaced FIELD-011 once and passed a bounded USB-attached startup identity/QMI idle-stop/real-sample/LTE-ready check, but did not observe a fixed GNSS response; Camera run006 passed bounded USB-attached Wi-Fi manual capture/recovery and exact VPS storage without an unexpected reset; outdoor GNSS fix, true-LTE Camera closure, USB-free joint Camera operation, timed outage/restart, LTE long-run stability, reconnect recovery, camera/GNSS/LTE product capability, IMU calibration/accuracy/mounting, activity diversity beyond stationary, battery accuracy, product power behavior, and final enclosure/mounting GNSS acceptance remain bounded by named tests |
| pc-bridge | development bridge | Windows PC | host CPU | n/a | n/a | PC-side SIM7670G AT probe | PC-side USB/RNDIS/AT observation | n/a | local JSONL/session files | development-only, not product dependency |

## FW-007 rollback baseline (historical runs)

- The verified connectivity-node fallback is FW-007
  `0.1.0-fw007-lte-wifi-failover` (application descriptor
  `fw007-e9ca7a4`; app SHA-256
  `8F3508C62CA96C54628B3C3FB0A64B5BB14EAF7BBB8188DA54FAEE0739283799`).
  It was flashed exactly once on COM3 on 2026-08-15 with all three normal
  regions hash-verified; the flash operation did not target or erase the NVS
  partition, while normal boot diagnostics retained/updated `boot_count`.
  Read-only identity matched ESP32-S3 QFN56 revision v0.2 and MAC
  `02:00:00:00:00:03`.
- In the operator-authorized SIM-absent run, modem USB AT and firmware state
  both reported the missing/not-ready SIM condition. The LTE readiness counter
  reached 120 at about 286 seconds device uptime, then the firmware moved once
  from `lte_primary` through `wifi_connecting` to `wifi_active`; Wi-Fi became
  active about 4.5 seconds after the transition and Message Hub registration
  returned HTTP 200. The approximately 4 minute 50 second boot-to-takeover
  wall time is longer than the configured 120-second delay counter because
  bounded modem status-query time is additional.
- Fresh VPS heartbeats and location reports continued over
  `link_type=wifi_failover`; one bounded `request_location` command produced a
  linked report and an `ok` ACK with `transport_type=wifi`. The recorded
  post-takeover windows contained no LTE command-poll round, offline
  transition, panic, brownout, or reset marker.
- A second operator-authorized run on 2026-08-16 reused the same image without
  another flash. After LTE readiness and consecutive healthy polls were
  established, the operator physically removed the SIM and USB AT confirmed
  `SIM_NOT_INSERTED`. COM3 retained threshold count three and the one-way
  transition to `wifi_active` with reason `lte_http_poll_failures`; threshold
  counts one and two occurred before serial reacquisition and were not
  individually retained. The VPS last received LTE at 13:40:03.490 CST and
  first received `wifi_failover` at 13:40:51.837, with one unchanged boot and
  forward sequence continuity. A following 205.9-second VPS window retained
  12 heartbeats, six sensor samples, and four location reports, with no
  LTE-linked message or device error. The matching serial window retained no
  LTE command poll after `wifi_active`, offline transition, panic, brownout,
  or reset. This is observed bounded engineering failover evidence, not
  production or long-run radio evidence. No command was issued, so the second
  run did not re-test Wi-Fi ACK behavior.
- Automatic Wi-Fi-to-LTE failback and a durable offline queue are not
  implemented in this first slice; LTE recovery, USB-free endurance, and
  long-run reliability remain unverified. Evidence:
  `docs/tasks/active/FW-007_LTE_WIFI_FAILOVER.md` and
  `firmware/mqtt_heartbeat/build_fw007_hw_20260815/`.

## Prior FW-006 Hardware Update

- The prior FW-006 image was `0.1.0-fw005-gnss-correctness`
  (`v0.1.0-45-g6ba36c2`; app SHA-256
  `D52CA34099BE41AFC5F2D9CDF49C22962ECE3A61CFB7083C6189CD69BEBEB827`),
  flashed exactly once on COM3 on 2026-08-12 with all three normal regions
  hash-verified and no NVS write.
- The one 20-second USB-attached startup capture observed QMI identity,
  idle-stop and a later `mock=false` sample, SIM7670 UART readiness,
  `LTE_READY`, and successful periodic location/observation uploads without
  fatal/reset-loop evidence. It contains no real GNSS fix/fixed-coordinate
  response; corrected coordinate parsing, outdoor/occluded GNSS behavior,
  USB-free operation, and product acceptance remain unverified. Evidence:
  `reports/firmware_validation/FW-006-20260812-001/`.

## Prior FIELD-011 Combined Attempt

- The prior connectivity-node image was FIELD-011
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
  pending**. The operator subsequently confirmed that the board remained
  stationary throughout the complete capture window, so its activity label is
  operator-confirmed `stationary`; pose/orientation, outdoor GNSS fix, fixed
  carry orientation, independent field power, calibration, and three walking
  windows remain unverified. Evidence:
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
