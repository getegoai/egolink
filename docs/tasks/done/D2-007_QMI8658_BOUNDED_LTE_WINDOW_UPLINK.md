---
id: D2-007
title: QMI8658 bounded window capture and LTE uplink
status: superseded
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-08-10
last_updated: 2026-09-09

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/FIELD_TEST.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/tasks/done/D2-006_QMI8658_HARDWARE_IDENTITY_PROBE.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md
  - reports/board_validation/20260810-qmi8658-probe/qmi8658_probe_report.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/components/platform_imu/include/platform_imu.h
  - firmware/mqtt_heartbeat/components/platform_imu/platform_imu.c
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/export_imu_windows.py
  - server/message_hub.py
  - shared/contracts/README.md
  - shared/contracts/imu_window_chunk.schema.json
  - shared/contracts/imu_window_manifest.schema.json
  - quality_tests/AGENTS.md
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_platform_imu_firmware.py
  - quality_tests/test_imu_window_export.py

allowed_paths:
  - docs/tasks/done/D2-007_QMI8658_BOUNDED_LTE_WINDOW_UPLINK.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/components/platform_imu/
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/export_imu_windows.py
  - server/message_hub.py
  - shared/contracts/imu_window_chunk.schema.json
  - shared/contracts/imu_window_manifest.schema.json
  - shared/contracts/README.md
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_platform_imu_firmware.py
  - quality_tests/test_imu_window_export.py
  - reports/board_validation/

out_of_scope:
  - changing the verified I2C address or GPIO15/GPIO16 wiring
  - always-on IMU streaming, interrupt/FIFO integration, or concurrent sampling and LTE upload
  - durable flash outbox, arbitrary capture sizes, or unbounded command polling
  - automatic activity labels, consent inference, or enabling model training
  - model training, evaluation claims, or edge deployment
  - GNSS, MAX17048, AMOLED, calibration, accuracy, power, or product-readiness claims
  - VPS deployment, firmware flash, serial capture, or hardware control without new explicit operator intent
---

# Problem

The external QMI8658A is verified at `0x6A`, but EgoLink has no bounded path
from real high-cadence samples through SIM7670 raw-frame ingest to a controlled
offline dataset artifact. The existing 32-entry ring overwrites old samples,
the normal telemetry cadence is too slow, and one large JSON upload exceeds
the empirically reliable SIM7670 HTTP body size.

# Expected Result

Add an opt-in `capture_imu_window` command that captures exactly 100 real
samples at a nominal 50 ms period into a bounded static buffer after ten
discarded warm-up reads, readback-confirms that sampling stopped, uploads ten
versioned 10-sample chunks plus a manifest, and ACKs success only after all
parts are accepted. Message Hub retains raw bytes first, exposes only safe
metadata through normal APIs, and an explicit local exporter reconstructs and
validates selected windows with `training_allowed=false`.

# Acceptance Criteria

- [x] Additive command and event contracts are documented and versioned.
- [x] Capture rejects mock/unavailable IMU, an unpersisted boot counter,
      missing/extra/unsupported parameters, and command/test-run mismatch.
- [x] Sampling uses an absolute schedule, performs no network operation in the
      sampling loop, discards ten warm-up reads, and records monotonic offsets
      and timing/error counters.
- [x] The QMI8658 capture path is real-only; a read failure is recorded and is
      never replaced with a mock sample.
- [x] Capture uses a bounded static buffer and readback-confirms that the
      measurement engine stopped on every exit path before any LTE upload or
      ACK; an unconfirmed stop fails the command service closed.
- [x] Each raw frame is hard-limited below the verified SIM7670 reliability
      ceiling; the largest manifest is preflighted before the first upload, and
      chunks carry deterministic command/boot IDs, hashes, ordering, and
      lineage.
- [x] The server retains raw attempts before parsing, validates chunk metadata,
      binds each window to one pending operator command, prevents retroactive
      authorization, and does not expose sample bytes through normal
      Dashboard/raw APIs.
- [x] The explicit offline exporter detects missing, duplicate-conflicting, or
      malformed chunks and emits only complete window JSONL plus a manifest.
- [x] Exported windows remain `training_allowed=false`, distinguish structural
      completeness from engineering cadence quality, and carry unrecorded
      mounting/axis/calibration, consent, retention, and dataset-split status
      until operator evidence is reviewed.
- [x] Focused tests, full verification, context lint, diff check, and an
      ESP-IDF 5.4.2 build for the verified `0x6A` + LTE command profile pass.
- [x] No flash or device command occurs during the build-only phase.

# Validation Commands

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_message_hub_server quality_tests.test_imu_window_export -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check

powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName 203.0.113.10 -Port 8790 -Scheme http `
  -TokenFile server\runtime\vps_message_hub_token.txt `
  -DeviceId ego-link-r1-connectivity-001 `
  -FwVersion 0.1.0-d2007-imu-window `
  -TestRunId D2-007-BUILD-20260810 `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.d2007-imu-window.local `
  -BuildDir build_d2007_imu_window `
  -IdfExport C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1 `
  -EnableSim7670LteHttpCommandLoop `
  -EnableQmi8658Imu -Qmi8658I2CPort 0 -Qmi8658SdaGpio 15 `
  -Qmi8658SclGpio 16 -Qmi8658I2CAddress 106 `
  -Qmi8658I2CTimeoutMs 20 -Qmi8658SampleIntervalMs 50 `
  -Qmi8658BootSampleCount 0 -Build -Json
```

# Hardware Validation

- Board: Waveshare ESP32-S3 + SIM7670G-4G connectivity node; formal PCB
  revision remains unverified.
- Sensor: ATK-NB018 V1.0 / QMI8658A observed at `0x6A`; `VCC->3V3`,
  `GND->GND`, `SDA->GPIO15`, `SCL->GPIO16`, `INT` disconnected.
- Mounting: operator reports the sensor is fixed; body-axis mapping,
  calibration profile, and long-term mechanical retention remain unrecorded.
- Build-only phase: no flash, serial capture, LTE command, or VPS mutation.
- The operator authorized the hardware phase on 2026-08-10 for the exact image
  below, `COM3`, one 20-second startup capture, one `100 x 50 ms` command,
  at most 12 minutes of serial/LTE observation, one read-only export, and an
  immediate abort on any anomaly.
- Hardware test run: `D2-007-HW-20260810-001`; command: `imu-hw-001`;
  evidence path: `reports/board_validation/20260810-d2007-imu-lte/`.
- Hardware success requires 100/100 real samples, zero mock substitutions, zero
  read failures, readback-confirmed stop, engineering cadence qualification,
  all ten chunks plus manifest retained under the authorized command/test run,
  and an explicit offline export that validates as complete.
- Hardware result on 2026-08-10: **failed, fail-closed**. The exact image was
  flashed once and passed the startup identity/idle-stop gates, but SIM7670
  remained `LTE_SIM_NOT_READY` through the 120-second readiness gate. The
  device never polled or executed the capture command; zero samples and zero
  raw frames were produced. Full evidence is in
  `reports/board_validation/20260810-d2007-imu-lte/d2_007_hardware_report.md`.

# Decisions

- Use 20 Hz for the first closed-loop smoke (`100 x 50 ms`) because the current
  probe established identity but only achieved about 14.3 Hz with verbose
  logging; 50 Hz remains a later cadence qualification, not an assumption.
- Capture finishes before any LTE transaction. No per-sample POST is allowed.
- Ten warm-up reads are discarded before the 100-sample window. They are
  recorded in the manifest but are never uploaded as training samples.
- Use the existing `EGLK/1` raw-frame envelope and additive KV event types;
  do not create an incompatible transport version.
- Keep every complete frame below 1200 bytes because 1232-byte POST success and
  larger 2237/3230-byte failures are the current hardware evidence boundary.
- Use ten chunks of ten samples. The firmware validates both the largest chunk
  and manifest before uploading the first part so an oversized manifest cannot
  leave a preventable partial window.
- IDs bind the operator command and persisted device boot count. A capture is
  authorized only while the matching server command is open; delayed parts,
  post-ACK replay, and upload-before-command evidence are rejected.
- Export `ok=true` means a complete, authorized, structurally valid engineering
  window. `cadence_quality_status=qualified` additionally requires 40-60 ms
  sample intervals, a 45-55 ms mean, and at most five >5 ms deadline misses;
  neither status enables training or constitutes product accuracy evidence.
- Raw attempts remain engineering evidence. Normal APIs expose metadata and
  hashes only; reconstructing samples requires an explicit local database
  export with bounded selectors.
- `training_allowed=false`, `activity_label=unknown`, and unrecorded mount/axis
  metadata are mandatory until the privacy, quality, label, mounting, and
  dataset-split reviews are complete.
- The prior authorization applied only to D2-006. Flashing the D2-007 image and
  running the LTE capture command require new explicit operator intent.
- 2026-08-10: The operator explicitly authorized deploying D2-007 to the
  existing VPS, restarting Message Hub, flashing the recorded D2-007 image to
  `COM3` without an NVS erase, one 20-second startup log, one
  `capture_imu_window` command (`100 x 50 ms`), at most 12 minutes of bounded
  serial/LTE observation, and one read-only export. Any anomaly must stop the
  run; a second flash or second physical capture is not authorized.

# Completion Evidence

Administrative closure: moved from `active` to `done` as `superseded` on
2026-09-09. The recorded 2026-08-10 attempt remains an honest failure, while
the later FIELD-011 path supplied the bounded LTE/QMI window evidence this
packet did not obtain. Do not rerun this obsolete image or command packet.

- Build-only implementation changed the task/protocol, QMI capture lifecycle,
  LTE command firmware, Message Hub validation, IMU wire schemas/index, explicit
  exporter, configuration generator, and focused tests listed in
  `allowed_paths`.
- Focused validation: 96 tests passed in 33.479 seconds on 2026-08-10.
- Full `scripts/verify.ps1`: 587 tests passed in 70.981 seconds. Context lint
  and `git diff --check` also passed. Existing expected-error-path
  `ResourceWarning` messages and the motion-readiness warning were non-failing.
- ESP-IDF v5.4.2 build passed for ESP32-S3, QMI8658A `0x6A` on GPIO15/GPIO16,
  boot capture disabled, SIM7670 LTE status/command loop enabled, and
  GNSS/MAX17048/AXP2101-QMI-rail paths disabled. Source HEAD is
  `e7e7e85670f0`; the app descriptor is `v0.1.0-22-ge7e7e85-dirty` because
  this task's reviewed changes are not committed.
- Build image:
  `firmware/mqtt_heartbeat/build_d2007_imu_window/egolink_mqtt_heartbeat.bin`;
  318416 bytes; SHA-256
  `3A5CD78A044D535B247AE8833C1AC433F4B7F26C3F136749A60F6D7EC21B854B`.
- Supporting flash artifacts are `bootloader.bin` (20928 bytes, SHA-256
  `EB48F3CB91C3D6DE61B739DAF91672A5916A5CD2A3BD5EC33F240C9A1E7DA94F`)
  and `partition-table.bin` (3072 bytes, SHA-256
  `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`).
- Link report: application partition has 70% free; shared DIRAM has 235429
  bytes free. The separate IRAM row is alignment-packed to one byte, so future
  link-map changes still need explicit size review even though this image links.
- Hardware phase report:
  `reports/board_validation/20260810-d2007-imu-lte/d2_007_hardware_report.md`.
  The post-cleanup service/command audit is recorded in
  `reports/board_validation/20260810-d2007-imu-lte/final_state.md`.
  A dedicated SSH key was authorized through an operator-controlled credential
  prompt, a consistent VPS backup was taken, Message Hub was deployed and
  health-checked, and the exact recorded image was flashed once to `COM3`
  without erasing NVS.
- The one 20-second startup capture passed: boot count `26926`, QMI8658
  `WHO_AM_I=0x05`, reset result `0x80`, and readback-confirmed
  `IMU_WINDOW_IDLE_MEASUREMENT_STOPPED`; no fatal marker was observed.
- The single `100 x 50 ms` command remained pending because the SIM7670 path
  reported `LTE_SIM_NOT_READY`, `not_registered`, and PDP `unknown` until the
  120-second readiness gate ended `ready=false`. Of 72 server observation
  attempts, 69 succeeded and all showed zero raw frames/messages and a pending
  command; three recorded an HTTP error without a response body. The final
  consistent database snapshot also contains zero run frames/messages, so no
  physical capture, chunk, manifest, or device ACK occurred. The observation
  loop's 721.48-second wall time exceeded the 720-second bound by 1.48 seconds
  during exit/cleanup and is recorded as a run deviation.
- The stale pending command was safely marked `timeout` with no fabricated ACK.
  The one read-only exporter run scanned zero frames and returned `ok=false`,
  zero valid windows, and an empty JSONL artifact. This historical attempt did
  not meet its end-to-end acceptance; it was superseded rather than changed to
  PASS retroactively.
- Remaining risks: on-device cadence and HTTP behavior under the combined
  image, the cause of the current SIM-not-ready state, future link-map growth,
  mounting axes, calibration, durability, power, durable retry, and dataset
  suitability remain unverified. This motion-data path is a prerequisite only;
  it does not complete the D2 location baseline or the D5 location-data
  flywheel.

# Builder Prompt

```text
This builder prompt is retired. Preserve the failed evidence and use the
current active milestone packet; do not flash or rerun this obsolete image.
```
