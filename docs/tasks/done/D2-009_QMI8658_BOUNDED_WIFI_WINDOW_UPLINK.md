---
id: D2-009
title: QMI8658 bounded Wi-Fi window uplink
status: completed
priority: high
requires_hardware: true
serves_demo: D2-D5
created: 2026-08-11
last_updated: 2026-08-11
completed: 2026-08-11

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/CONTEXT_INDEX.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/tasks/done/D2-007_QMI8658_BOUNDED_LTE_WINDOW_UPLINK.md
  - docs/tasks/done/D2-008_WIFI_QMI8658_SENSOR_SMOKE.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
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
  - quality_tests/test_imu_window_export.py

allowed_paths:
  - docs/tasks/done/D2-009_QMI8658_BOUNDED_WIFI_WINDOW_UPLINK.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - scripts/prepare_fw001_hw_config.ps1
  - scripts/export_imu_windows.py
  - server/message_hub.py
  - shared/contracts/README.md
  - shared/contracts/imu_window_chunk.schema.json
  - shared/contracts/imu_window_manifest.schema.json
  - quality_tests/test_fw001_hw_config.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_imu_window_export.py
  - reports/board_validation/

out_of_scope:
  - changing the verified QMI8658 address, GPIO15/GPIO16 wiring, or mounting
  - continuous IMU streaming, arbitrary window sizes, labels, or calibration
  - model training, model claims, or edge deployment
  - SIM7670, LTE, GNSS, AMOLED, EgoBase, MAX17048, or battery work
  - v0.4 appearance, PCB, chip-selection, enclosure, or production work
  - Wi-Fi scanning, BSSID collection, dashboard sample exposure, or broad protocol redesign
---

# Goal

Run one complete real-QMI8658 data window through the already verified indoor
Wi-Fi path: an operator command requests exactly 100 samples at 50 ms, firmware
captures and stops the sensor before networking, Message Hub receives ten raw
chunks plus one manifest, and the explicit exporter reconstructs one bounded
engineering window with training disabled.

# Expected Result

Generalize only the existing D2-007 raw command and IMU window publisher from
LTE-only to `lte` or `wifi`. The Wi-Fi profile reuses `EGLK/1`,
`capture_imu_window`, the same fixed window shape, validation, authorization,
redaction, and exporter. Its dedicated task runs no periodic heartbeat or
single-sample telemetry, so sampling and application network traffic do not
overlap.

# Acceptance Criteria

- [x] A dedicated opt-in Wi-Fi window profile reuses the raw command parser;
      normal Wi-Fi telemetry and LTE profiles retain their existing behavior.
- [x] The capture implementation and chunk/manifest builder remain one shared
      code path with an explicit `lte` or `wifi` transport, not two copies.
- [x] Sampling completes and the QMI8658 stop is readback-confirmed before the
      first Wi-Fi upload or ACK; mock/unavailable input fails closed.
- [x] Message Hub accepts only `lte` or `wifi`, rejects mixed-transport parts,
      retains raw evidence first, and does not expose sample bytes in normal APIs.
- [x] One command yields exactly 100 real samples, ten chunks, one manifest,
      one matching ACK, and one structurally valid offline-export window.
- [x] The exported record preserves `transport_type=wifi`, reports cadence
      separately from completeness, and keeps `training_allowed=false` plus
      the existing privacy/consent/mounting/split blockers.
- [x] Focused tests, full verification, context lint, diff check, and an
      ESP-IDF 5.4.2 build pass before hardware execution.
- [x] Implementation/static validation and hardware evidence are separate Git
      commits; v0.4 product-design assets and all secrets remain uncommitted.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_fw001_hw_config quality_tests.test_message_hub_server quality_tests.test_imu_window_export -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check

powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 `
  -HostName 203.0.113.10 -Port 8790 -Scheme http `
  -TokenFile server\runtime\vps_message_hub_token.txt `
  -DeviceId ego-link-r1-connectivity-001 `
  -FwVersion 0.1.0-d2009-wifi-imu-window `
  -TestRunId D2-009-HW-20260811-001 `
  -SourceSdkconfig firmware\mqtt_heartbeat\sdkconfig.d2008-wifi-imu.local `
  -ConfigPath firmware\mqtt_heartbeat\sdkconfig.d2009-wifi-imu-window.local `
  -BuildDir build_d2009_wifi_imu_window `
  -IdfExport C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1 `
  -EnableWifiImuWindowCommand -WifiImuWindowPollMaxAttempts 12 `
  -EnableQmi8658Imu -Qmi8658I2CPort 0 -Qmi8658SdaGpio 15 `
  -Qmi8658SclGpio 16 -Qmi8658I2CAddress 106 `
  -Qmi8658I2CTimeoutMs 20 -Qmi8658SampleIntervalMs 50 `
  -Qmi8658BootSampleCount 0 -Build -Json
```

# Hardware Validation

- Board: Waveshare ESP32-S3 + SIM7670G-4G connectivity node on `COM3`; formal
  PCB revision remains unverified. No SIM is installed for this task.
- Sensor: fixed ATK-NB018 V1.0 / QMI8658A at `0x6A`; `VCC->3V3`, `GND->GND`,
  `SDA->GPIO15`, `SCL->GPIO16`, `INT` disconnected.
- Network: operator-provided indoor Wi-Fi and the existing Message Hub at
  `203.0.113.10:8790`; credentials stay only in ignored local configuration.
- Bounds: one COM3 flash without NVS erase, one bounded startup log, one exact
  `100 x 50 ms` command, at most ten minutes of serial/API observation, and one
  read-only database export. Do not retry physical capture in this task.
- Abort on panic, watchdog, brownout/reset loop, QMI identity failure, mock
  data, unconfirmed measurement stop, semantic rejection, conflicting parts,
  unexpected heating, odor, or USB instability.
- Success requires 100/100 real samples, zero mock substitutions/read failures,
  stop confirmation, ten chunks plus manifest and matching ACK over Wi-Fi, and
  one valid export record. Cadence qualification is reported but is not a
  product-accuracy or training-readiness claim.
- Hardware result: **PASS**. Test run `D2-009-HW-20260811-001` and command
  `wifi-imu-001` produced 100 real samples, ten chunks, one manifest, and one
  `ok` ACK over Wi-Fi. The final export contains one complete cadence-qualified
  window, zero invalid windows, and `training_allowed=false`. Evidence:
  `reports/board_validation/20260811-d2009-wifi-imu-window/d2_009_wifi_imu_window_report.md`.

# Decisions

- Wi-Fi is the present bench transport because no SIM is installed. LTE remains
  a parallel field path and D2-007 evidence is not overwritten.
- Keep the wire contract at `EGLK/1` and IMU window v1; transport is additive
  metadata and command authorization does not select the network.
- Reuse the existing raw command endpoint and capture/validation/export logic.
  Do not build a second JSON-only capture protocol.
- Capture is local and bounded; all networking starts only after confirmed
  sensor stop.
- The current development-board path and v0.4 sales-hardware design are parallel
  workstreams. This task changes only the former.
- 2026-08-11: after the bounded Wi-Fi window step and two-commit rhythm were
  proposed, the operator confirmed that current-board development should
  continue in parallel with v0.4 and directed us to continue the next step.

# Completion Evidence

- Implementation/static phase completed on 2026-08-11 without a flash, device
  command, or VPS mutation. The dedicated profile reuses one raw parser and one
  capture/build/publish core for `wifi` and `lte`; the Wi-Fi command task is
  bounded and exits after attempting one selected command.
- Focused validation: 92 tests passed in 36.639 seconds. Full
  `scripts/verify.ps1`: 592 tests passed in 77.971 seconds. Context lint and
  `git diff --check` passed.
- ESP-IDF v5.4.2 Wi-Fi/QMI build-only check passed: 926912-byte application,
  SHA-256 `20C356199D7C8D68C53FBD42FA78F573D30D77E3A83F86D721315986DBF177DD`,
  about 12% application-partition headroom. Its map contains no LTE readiness
  or LTE command-loop symbol.
- ESP-IDF v5.4.2 LTE/QMI regression build also passed: 592032-byte application,
  SHA-256 `1C2606089D384D80EBF1AEADE7C9764DFF27393AC4E6841AE075E567C6864321`.
- Both build-only images identify source `b4a11de-dirty`; neither is the final
  hardware image. The exact clean committed Wi-Fi image was subsequently
  rebuilt and hashed before the one authorized COM3 flash.
- Implementation was committed as `56edaf8`; the exact hardware image reports
  `v0.1.0-24-g56edaf8`, is 926960 bytes, and has SHA-256
  `16C839CAD20C527C772ED84B69C649F7D092F716FD3F57174D0DCBDBEE95F685`.
  Message Hub was backed up, deployed, health-checked, and matched the local
  server source hash before the one physical COM3 flash. NVS was not erased.
- The command closed `ok` with 13 raw run frames: one command, ten chunks, one
  manifest, and one ACK. All eleven IMU parts parsed successfully and remained
  redacted through normal APIs. Raw-frame count stayed stable after completion.
- Final export: one valid window, zero invalid windows, 100 samples, 98 distinct
  six-axis tuples, zero read failures/mock substitutions/deadline misses,
  intervals 49749/49999/50292 us minimum/mean/maximum, cadence `qualified`, and
  `training_allowed=false`.
- The first exporter attempt exposed a tooling bug: the same-run raw command
  and ACK were counted as invalid IMU frames despite one valid window. Commit
  `ae2a4c4` makes the exporter ignore non-IMU frames; its focused 23-test and
  full 593-test validations passed. The final read-only export returned
  `ok=true` without any reflash or recapture.
- The single serial observation started after the short device command had
  already completed and captured zero bytes. It did not reset the board.
  Server/raw/export evidence is authoritative for this run; this limitation is
  retained in the hardware report rather than represented as startup-log proof.

# Builder Prompt

```text
Read docs/tasks/active/D2-009_QMI8658_BOUNDED_WIFI_WINDOW_UPLINK.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, firmware/AGENTS.md,
quality_tests/AGENTS.md, this packet, and its context entries. Implement the
smallest transport-neutral reuse of the existing bounded raw-command IMU window
for a dedicated Wi-Fi profile. Obey allowed_paths and out_of_scope. Run the
declared validations, commit implementation/static evidence separately, then
perform only the bounded authorized COM3/VPS hardware loop and record its
result in a second commit. Never print or commit Wi-Fi, token, SSH, or private
product-design data.
```
