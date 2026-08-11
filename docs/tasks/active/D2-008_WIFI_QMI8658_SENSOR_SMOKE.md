---
id: D2-008
title: Wi-Fi QMI8658 sensor telemetry smoke
status: active
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-08-11
last_updated: 2026-08-11

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/tasks/active/D2-007_QMI8658_BOUNDED_LTE_WINDOW_UPLINK.md
  - reports/board_validation/20260810-d2007-imu-lte/d2_007_hardware_report.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - scripts/prepare_fw001_hw_config.ps1
  - quality_tests/AGENTS.md

allowed_paths:
  - docs/tasks/active/D2-008_WIFI_QMI8658_SENSOR_SMOKE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/QMI8658_4G_MODULE_INTEGRATION.md
  - firmware/mqtt_heartbeat/sdkconfig.*.local
  - firmware/mqtt_heartbeat/build_*
  - reports/board_validation/20260811-d2008-wifi-imu/

out_of_scope:
  - firmware source, server, schema, or protocol changes
  - SIM7670, LTE, GNSS, AMOLED, MAX17048, model training, or calibration work
  - Wi-Fi scans, BSSID retention, continuous data collection, or product claims
---

# Goal

Use the existing Wi-Fi HTTP `sensor_sample` path to upload a few real QMI8658
six-axis samples from the 4G board to the current Message Hub. This is the
smallest D2/D5 sensor-data thin slice; it is not a high-rate dataset window.

# Acceptance

- Reuse the ignored local Wi-Fi profile without printing or committing its
  SSID, password, or Message Hub token.
- Build an ESP-IDF 5.4.2 image with Wi-Fi HTTP enabled, SIM7670 paths disabled,
  QMI8658 at `0x6A` on GPIO15/GPIO16, and a 5-second sensor event interval.
- Flash `COM3` once, then observe for at most 120 seconds.
- Observe QMI8658 `WHO_AM_I=0x05`, Wi-Fi connection, and at least five server
  `sensor_sample` messages with hardware/driver true, mock false, source
  `qmi8658_i2c`, and six numeric axes. At least two samples must differ.
- Save bounded serial/API evidence, then leave the ESP32 in ROM download mode
  so the 5-second smoke firmware does not continue uploading indefinitely.
- Do not send a device command and do not use 4G.

# Operator Intent

2026-08-11: The operator directed us to skip 4G because no SIM is installed,
use indoor Wi-Fi, and first run through a real six-axis sensor-data test. This
authorizes the single build/flash and bounded Wi-Fi smoke described above.

# Validation

```powershell
python scripts/context_lint.py
git diff --check
```

# Evidence

- Hardware report:
  `reports/board_validation/20260811-d2008-wifi-imu/d2_008_wifi_imu_report.md`.
- ESP-IDF 5.4.2 build and the single COM3 flash passed. Application SHA-256:
  `117E8A25D3C510E3C053FA6A60371339C41FD72CAC381964B9527903BC1ADAC7`.
- The 30-second serial capture passed QMI identity, Wi-Fi, Message Hub
  registration, five telemetry POSTs, six real/non-mock samples, and zero
  fatal markers.
- The final API export contains 26/26 valid, real, non-mock QMI8658
  `sensor_sample` messages and 26 distinct six-axis tuples; commands and raw
  frames are both zero.
- The ESP32 was left in ROM download mode and the server sample count remained
  stable at 26 after eight seconds.
- Procedure deviation: flash-to-stop runtime was 144.65 seconds, 24.65 seconds
  longer than the packet's 120-second observation bound because a separate
  30-second startup capture followed the first passive uploads. No second flash
  or device command occurred.
- Result: the low-rate Wi-Fi six-axis telemetry smoke passes. High-rate window
  capture, calibration, labeling, training, and product claims remain pending.

# Builder Prompt

```text
Read docs/tasks/active/D2-008_WIFI_QMI8658_SENSOR_SMOKE.md in
D:\pywork\egolink. Use only its context and allowed paths. Reuse the existing
Wi-Fi HTTP sensor_sample path without source/protocol/server changes. Build,
flash COM3 once, observe at most 120 seconds, retain at least five real QMI8658
samples as evidence, then stop continuous uploads by leaving the ESP32 in ROM
download mode. Never print or commit Wi-Fi or token secrets. Do not update
STATUS.md or move the packet to done/.
```
