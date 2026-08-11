---
id: FIELD-011
title: GNSS plus IMU LTE joint outdoor seed
status: active
priority: high
requires_hardware: true
serves_demo: D2-D5
created: 2026-08-11
last_updated: 2026-08-11

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/FIELD_TEST.md
  - docs/development/LTE_TRANSPORT.md
  - docs/development/LOCATION_DATASET.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/tasks/active/FIELD-003_OUTDOOR_GNSS_ACCEPTANCE.md
  - docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md
  - docs/tasks/done/D2-009_QMI8658_BOUNDED_WIFI_WINDOW_UPLINK.md
  - docs/tasks/done/D5-002_QMI8658_LABELED_MULTI_WINDOW_SEED.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/run_imu_capture_session.py
  - scripts/export_imu_windows.py
  - scripts/run_location_d2_d5_pipeline.py
  - quality_tests/AGENTS.md
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_imu_capture_session.py
  - quality_tests/test_imu_window_export.py

allowed_paths:
  - docs/tasks/active/FIELD-011_GNSS_IMU_LTE_JOINT_FIELD_SEED.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - scripts/run_imu_capture_session.py
  - quality_tests/test_imu_capture_session.py
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - reports/

out_of_scope:
  - server deployment, wire-contract changes, or new ingest/export formats
  - continuous high-rate IMU streaming or model training/deployment
  - MAX17048/battery acceptance, reconnect/store-forward claims, or power-life claims
  - dangerous motion, falls, impacts, driving, or public release of private coordinates
  - v0.4 PCB, chip-selection, enclosure, or industrial-design work
---

# Goal

Prepare and run the smallest USB-Free outdoor seed in which the current 4G
board reports periodic real GNSS/cell observations over LTE while three
independent real QMI8658 windows are captured during a normal walk and uploaded
through the existing LTE raw-frame path.

# Expected Result

- Build one existing-code profile with SIM7670G GNSS, LTE status/command loop,
  location observation, 60-second periodic location, and the observed QMI8658
  at I2C `0x6A` on GPIO15/GPIO16. Wi-Fi and MAX17048 are not runtime
  dependencies for this first joint seed.
- Generalize the existing three-window session runner only enough to accept an
  explicit expected transport of `wifi` or `lte`; default behavior remains
  Wi-Fi for D5-002 compatibility. ACK and window evidence must match the
  selected transport exactly.
- Use one bounded outdoor time window to relate periodic location evidence and
  three 100 x 50 ms walking IMU windows. Post-capture operator confirmation,
  not the plan, remains the label authority.
- Preserve the current server, protocol, exporter, sample shape, raw-first
  retention, and `training_allowed=false` gates.

# Acceptance Criteria

- [x] Read-only preflight sees CH343 `COM3` plus SIM7670G `COM4`-`COM7`; the
      current D5-002 Wi-Fi image is correctly identified as unsuitable for a
      SIM-only field run.
- [x] Session-runner tests cover unchanged default Wi-Fi behavior and an LTE
      three-window success path, plus wrong-transport fail-closed behavior.
- [x] ESP-IDF 5.4.2 builds the exact combined profile with GNSS, LTE periodic
      location, LTE raw commands, QMI8658 `0x6A`, 50 ms IMU cadence, no Wi-Fi
      window mode, no boot sample burst, and mock-labelled power.
- [x] Static validation and the build/image hash are committed before any
      flash, preserving the separate implementation/evidence commit cadence.
- [ ] After the SIM is inserted, a bounded bench gate observes SIM ready,
      registration/PDP ready, explainable GNSS state, QMI identity, confirmed
      idle stop, and fresh VPS location evidence before handoff.
- [ ] The field run uses independent power and no USB runtime path, records the
      carry position/orientation and exact start/end time, obtains three real
      LTE IMU windows during confirmed normal walking, and retains periodic
      GNSS/cell evidence in the same device/time window.
- [ ] A single read-only IMU export and bounded device/time location export are
      preserved under a named evidence directory. Labels remain separate and
      all training flags remain false.

# Validation Commands

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName 203.0.113.10 -Port 8790 -Scheme http `
  -DeviceId ego-link-r1-connectivity-001 `
  -FwVersion 0.1.0-field011-gnss-imu `
  -TestRunId F011-FW-20260811-001 `
  -TokenFile server\runtime\vps_message_hub_token.txt `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.field011-gnss-imu-lte.local `
  -SourceSdkconfig firmware\mqtt_heartbeat\sdkconfig.vps.local `
  -BuildDir build_field011_gnss_imu_lte `
  -IdfExport C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1 `
  -EnableSim7670Gnss -EnableD1PeriodicLocation `
  -D1PeriodicLocationIntervalSec 60 `
  -EnableQmi8658Imu -Qmi8658I2CPort 0 `
  -Qmi8658SdaGpio 15 -Qmi8658SclGpio 16 `
  -Qmi8658I2CAddress 106 -Qmi8658I2CTimeoutMs 20 `
  -Qmi8658SampleIntervalMs 50 -Qmi8658BootSampleCount 0 `
  -Build -Json
python scripts\run_imu_capture_session.py `
  --plan reports\field_validation\FIELD-011-20260811-001\capture_plan.json `
  --output reports\field_validation\FIELD-011-20260811-001\capture_dry_run.json `
  --json
python -m unittest quality_tests.test_imu_capture_session quality_tests.test_fw001_hw_config quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_imu_window_export -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

- Board: Waveshare ESP32-S3-SIM7670G-4G connectivity node, CH343 `COM3` for
  flash/debug only; external fixed ATK-NB018/QMI8658A at `0x6A`, GPIO15/16,
  3.3 V, INT disconnected.
- Required preflight: power off before inserting SIM; LTE main and GNSS antennas
  attached; SIM data service/APN/PIN state checked; exposed board and sensor
  protected in an insulating container with strain relief; stable independent
  power used for the field runtime.
- Runtime: five minutes stationary outdoors for GNSS acquisition, then normal
  walking with one fixed carry position through an open-sky segment and, when
  practical, ordinary street/tree-cover segments. No running, impact, vehicle,
  or deliberate network fault is required.
- Evidence: `reports/field_validation/FIELD-011-<date>/` with image hashes,
  bounded startup/bench logs, field time window, command/ACK summaries,
  redacted location export, IMU export, annotations, and remaining risks.
- Attempt on 2026-08-11: one actual COM3 flash completed with all three write
  hashes verified and NVS preserved. The 20-second startup capture passed QMI
  identity and idle-stop gates. The inserted-SIM readiness loop then ended at
  `ready=false`, registration `not_registered`, and PDP `unknown`; the sole
  stationary command was never polled or executed. Observation stopped before
  five minutes, with zero samples, messages, raw frames, GNSS events, or ACKs.
- Follow-up diagnosis: under a separate 60-second read-only authorization,
  COM4 responded normally to `AT` but `AT+CPIN?` returned
  `+CME ERROR: SIM not inserted`. The nine approved status queries completed in
  6.98 seconds with no configuration write, reset, or flash. CSQ was 21, while
  registration was `0,0`, attach was 0, and no PDP context existed. The next
  gate is physical SIM detection after a full-power-off reseat.

# Decisions

- 2026-08-11: the operator explicitly authorized one COM3 flash, one
  20-second startup capture, up to five minutes of bench observation, one
  stationary 100 x 50 ms capture command, and one read-only export. No second
  flash, reset, modem diagnostic, or capture retry is authorized by that turn.
- This is the first joint field seed, not strict FIELD-003 accuracy acceptance
  and not a long-run reliability or battery test. Reference coordinates may be
  added by the existing D2 field kit, but their absence does not erase useful
  GNSS/IMU evidence.
- Periodic GNSS/cell events and high-rate IMU windows remain separate existing
  records and are related by the bounded device/time window. Do not invent a
  new combined payload for this first run.
- Current firmware has only a volatile outbox and one immediate LTE POST retry.
  Network gaps may lose evidence; the field report must count what actually
  arrived rather than infer missing samples.
- The current static session seed established one stationary class. This run
  targets three confirmed normal-walking windows; broader activity coverage,
  calibration, consent, split assignment, and training remain future work.

# Completion Evidence

- Implementation commit: `3f97cf7` (`feat(field): prepare LTE GNSS IMU joint
  seed [D2-D5]`), containing this task packet,
  `scripts/run_imu_capture_session.py`, and
  `quality_tests/test_imu_capture_session.py` only.
- Static validation: focused FIELD-011 suite 65/65 PASS; repository verification
  610/610 PASS; context lint and diff check PASS. The capture plan dry-run is
  `dry_run_ready` for exactly three LTE windows with no external actions.
- Build: clean ESP-IDF 5.4.2 build-only PASS at implementation commit
  `3f97cf7`; project version `v0.1.0-30-g3f97cf7`, ESP32-S3 target, app size
  605,776 bytes with 42% of the 1 MiB app partition free. `flash_intentionally_not_run=true`.
- Image hashes: bootloader 20,928 bytes SHA-256
  `4DC71F42042DF0B81FE3C3C4B5AC2AC97CA5E029AC5C1EC0ABD7B052E2B295E1`;
  partition table 3,072 bytes SHA-256
  `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`;
  application 605,776 bytes SHA-256
  `388FFEAA96A15D1CAE185B82592EC406320C556C45656629AB292ACFE2E7D0AB`.
- Bench result: **PARTIAL / FAIL (LTE registration precondition)**. Flash and
  QMI startup/idle-stop passed. SIM7670 UART/AT was reachable, but LTE stayed
  `not_registered` with PDP unknown until
  `LTE_HTTP_COMMAND_READY_RESULT ready=false`. Test run
  `F011-BENCH-20260811-001` contains one pending command `f011-bench-1`, zero
  messages, and zero raw frames. No physical capture occurred.
- Outdoor result: not started; the board is not ready for handoff.
- Evidence paths: ignored local directory
  `reports/field_validation/FIELD-011-20260811-001/` contains the three-window
  capture plan, operator runbook, and no-action dry-run result. The ignored
  config/build are `sdkconfig.field011-gnss-imu-lte.local` and
  `build_field011_gnss_imu_lte/` under `firmware/mqtt_heartbeat/`.
- Remaining risks: SIM electrical/mechanical detection currently fails with
  `SIM not inserted`; PIN/APN/registration/PDP cannot yet be evaluated;
  the combined image has now passed QMI startup only, not joint runtime;
  command `f011-bench-1` remains pending and must be resolved before reboot;
  GNSS and IMU are related by a device/time window rather than synchronized
  sample timestamps; durable offline delivery and field power life remain
  unverified. Detailed evidence:
  `reports/field_validation/FIELD-011-20260811-001/field011_bench_report.md`.

# Builder Prompt

```text
Read docs/tasks/active/FIELD-011_GNSS_IMU_LTE_JOINT_FIELD_SEED.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md,
firmware/AGENTS.md, quality_tests/AGENTS.md, this packet, and its context
entries. Implement only the transport-selectable session-runner slice and
build the exact existing-code LTE+GNSS+QMI profile. Obey allowed_paths and
out_of_scope. Do not change firmware logic, server, protocol, exporter, sample
shape, or training flags. Run declared validation and commit the static phase.
Do not flash, open serial, create VPS commands, or start field observation
without fresh operator authorization. Never print or commit credentials,
private coordinates, runtime databases, or the untracked v0.x design assets.
```
