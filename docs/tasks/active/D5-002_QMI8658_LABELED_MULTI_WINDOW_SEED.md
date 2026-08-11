---
id: D5-002
title: QMI8658 labelled multi-window dataset seed
status: active
priority: high
requires_hardware: true
serves_demo: D5
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
  - docs/development/LOCATION_DATASET.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md
  - docs/tasks/done/D2-009_QMI8658_BOUNDED_WIFI_WINDOW_UPLINK.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/export_imu_windows.py
  - scripts/run_imu_capture_session.py
  - scripts/build_labeled_imu_dataset.py
  - quality_tests/AGENTS.md
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_imu_window_export.py
  - quality_tests/test_imu_capture_session.py
  - quality_tests/test_labeled_imu_dataset.py

allowed_paths:
  - docs/tasks/active/D5-002_QMI8658_LABELED_MULTI_WINDOW_SEED.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/STATUS.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_imu_window_export.py
  - quality_tests/
  - reports/

out_of_scope:
  - model training, learned-model metrics, model deployment, or device control from a model
  - batch wire commands, continuous sampling, changed sample shape, server changes, or VPS deployment
  - falls, impacts, dangerous driving, children, elders, audio, images, GNSS, LTE, or private location data
  - final axis calibration, product mounting acceptance, battery claims, or v0.4 product-design work
---

# Goal

Turn the D2-009 single-window proof into the smallest replayable D5 data seed:
one boot can execute up to three independent Wi-Fi IMU commands, an operator
plan supplies safe activity/session labels outside the device evidence, and a
local builder produces a quality-checked, session-grouped dataset artifact
that remains explicitly blocked from training.

# Expected Result

- Keep `EGLK/1`, `capture_imu_window`, 100 x 50 ms sampling, ten chunks, and
  the existing exporter unchanged.
- Add an opt-in successful-command limit to the dedicated Wi-Fi profile. The
  default remains one for D2-009 compatibility; this task uses three. Every
  command has its own `cmd_id`, window, manifest, and ACK. The first failed,
  rejected, duplicate, upload, ACK, or stop-confirmation result ends the task.
- Keep device/export evidence immutable with `activity_label=unknown` and
  `training_allowed=false`. The pre-capture plan records only planned actions.
  After capture, the operator confirms a separate label sidecar whose rows are
  joined one-to-one by `cmd_id`, `window_id`, and `samples_sha256`.
- Check that every session belongs to only one split group, duplicate windows
  cannot cross splits, and source/cadence/quality lineage is complete.
- This first three-window run is a pipeline seed, not a trainable corpus.

# Acceptance Criteria

- [x] The dedicated Wi-Fi profile supports `1..4` successful commands per
      boot, defaults to one, and uses three for this task.
- [x] A command continues to the next only after real capture, confirmed IMU
      stop, all chunks, manifest, and `ok` ACK succeed; the first abnormal
      result stops the service without an automatic reset or recapture.
- [x] A dry-run-first session runner validates a strict local plan, creates
      exactly one test run and three commands one at a time only under an
      explicit execute flag, redacts its token, and writes replayable partial
      or complete command/result metadata.
- [x] A local dataset builder joins explicit exporter output to human label
      sidecars without deriving confirmed labels from the pre-capture plan or
      modifying the source export, rejects missing/extra/duplicate bindings and
      exporter-manifest/lineage/hash/quality/split conflicts, and emits labelled
      rows plus a manifest.
- [x] Labels and consent stay separate. Every output remains
      `training_allowed=false`; no CLI boolean can promote a record.
- [x] Focused tests cover three successful windows, failure-before-next,
      duplicate/ACK failure stop, invalid labels, duplicate hashes, and one
      session crossing splits.
- [x] Focused tests, full verification, context lint, diff check, and an
      ESP-IDF 5.4.2 build pass before any hardware action.
- [x] Implementation/static evidence and hardware/data evidence use separate
      Git commits; all product-design archives and secrets stay uncommitted.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_imu_window_export quality_tests.test_imu_capture_session quality_tests.test_labeled_imu_dataset -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

Build-only profile (reads credentials only from ignored local files and does
not flash):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName 203.0.113.10 -Port 8790 -Scheme http `
  -TokenFile server\runtime\vps_message_hub_token.txt `
  -SourceSdkconfig firmware\mqtt_heartbeat\sdkconfig.d2009-wifi-imu-window.local `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.d5002-wifi-seed.local `
  -BuildDir build_d5002_wifi_seed `
  -IdfExport C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1 `
  -DeviceId ego-link-r1-connectivity-001 `
  -FwVersion 0.1.0-d5002-wifi-seed -TestRunId D5-002-BUILD-20260811 `
  -EnableWifiImuWindowCommand -WifiImuWindowPollMaxAttempts 120 `
  -WifiImuWindowMaxSuccessfulCommands 3 `
  -EnableQmi8658Imu -Qmi8658I2CPort 0 -Qmi8658SdaGpio 15 `
  -Qmi8658SclGpio 16 -Qmi8658I2CAddress 106 -Qmi8658I2CTimeoutMs 20 `
  -Qmi8658SampleIntervalMs 50 -Qmi8658BootSampleCount 0 -Build -Json
```

# Hardware Validation

- Board: current Waveshare ESP32-S3 + SIM7670G-4G connectivity node on COM3;
  no SIM is required. Sensor remains the fixed ATK-NB018/QMI8658A at `0x6A`,
  GPIO15/GPIO16, 3.3 V, with INT disconnected.
- Planned seed: one firmware flash without NVS erase, one bounded serial/API
  observation, and exactly three independently authorized 100 x 50 ms windows
  over indoor Wi-Fi. No automatic retry or second flash.
- Safe labels only: stationary or normal indoor walking/handling. No fall,
  impact, running, vehicle, or hazardous action is part of this task.
- Expected evidence: three `ok` commands, 30 chunks, three manifests, three
  ACKs, 300 real samples, confirmed stop after every window, three valid
  exporter windows, a label sidecar, and a dataset manifest with
  `training_allowed=false`.
- The operator authorized one COM3 flash, one 20-second startup capture, three
  100 x 50 ms Wi-Fi windows, at most five minutes of observation, and one
  read-only export. The run used one unassigned session with three planned
  stationary windows. Hardware capture/export passed; post-capture observed
  label confirmation remains pending.

# Decisions

- This task serves D5 by establishing real IMU capture/session/label/split
  plumbing. It supports the future motion-aware location path approved in
  `LOCATION_DATASET.md`; it does not replace the active D5 location baseline.
- Use multiple existing independent commands, not a new batch command.
- Keep labels outside the wire evidence. Device claims remain `unknown/none`;
  the post-capture operator-confirmed sidecar is the label authority. A planned
  action is not automatically treated as an observed label.
- Reuse the existing explicit IMU exporter. Do not introduce a second ingest
  path, candidate-store promotion, or training-row contract in this seed.
- A meaningful three-class baseline (`stationary`, `walking`, `vehicle`) needs
  substantially more independent sessions. This task intentionally stops at
  a three-window pipeline seed.
- The operator directed the current-board development path to continue while
  v0.4 appearance/PCB/chip/enclosure work remains parallel and separate.

# Completion Evidence

- Changed files: this packet; the Wi-Fi firmware/Kconfig/config generator;
  focused firmware/config tests; `run_imu_capture_session.py` and its tests;
  `build_labeled_imu_dataset.py` and its tests.
- Static validation: focused tests pass (68/68), including a real server transition
  from `pending` through `in_progress` to `ok`; full `verify.ps1` passes
  (607/607), and context
  lint, Python compile, and diff check pass. A temporary local Message Hub
  contract exercise verified test-run creation, command/ACK normalization,
  13 redacted raw-frame records for one window, and runner evidence parsing.
  ESP-IDF 5.4.2 build-only passes for the three-command profile (927,312-byte
  app; pre-commit SHA-256
  `2331878B9674B4118E1C877DD3FE67E9730BAF678B132EB77A4D6DD6E4ED170B`)
  and for the existing ordinary Wi-Fi IMU profile. The clean post-commit app
  is `v0.1.0-27-gab218af`, 927,312 bytes, SHA-256
  `930A4C4F21C34A738FA19F31A42B323D88BD6B650C15B8CED5BFE617483C815A`.
- Hardware/data result: PASS for capture/export. The one flash and 20-second
  startup gate passed. Test run `D5-002-SEED-20260811-001` completed three
  commands in 47 seconds with 300 real samples, 30 chunks, three manifests,
  three `ok` ACKs, and zero read/mock/deadline failures. The one read-only
  exporter invocation returned three valid cadence-qualified windows, zero
  invalid windows, and no truncation. Evidence:
  `reports/board_validation/20260811-d5002-imu-seed/d5_002_hardware_report.md`.
  The planned stationary action has not yet been promoted to an observed
  label, so the label sidecar and labelled dataset artifact remain pending.
- Remaining risks: concurrent external capture commands must be absent during
  the bounded run; the executed-command cache is RAM-only; activity labels,
  axis calibration, data sufficiency, consent, and training remain unverified
  or explicitly blocked.

# Builder Prompt

```text
Read docs/tasks/active/D5-002_QMI8658_LABELED_MULTI_WINDOW_SEED.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, firmware/AGENTS.md,
quality_tests/AGENTS.md, this packet, and its context entries. Implement the
smallest three-command Wi-Fi IMU sequence plus dry-run-first session/labelled
dataset tooling. Obey allowed_paths and out_of_scope. Do not modify the wire
contract, server, exporter, samples, or source training flags. Run all declared
validations and commit the implementation/static phase. Stop before flashing or
sending commands until the operator confirms the exact bounded hardware run.
Never print or commit Wi-Fi credentials, tokens, private runtime data, or the
untracked product-design archives.
```
