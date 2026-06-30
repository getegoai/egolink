---
id: LOC-005A
title: Firmware-Side Observation Source States
status: completed
priority: high
requires_hardware: true
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/development/PROTOCOL.md
  - docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/README.md
  - shared/contracts/

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/PROTOCOL.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/LOC-005A_FIRMWARE_SIDE_OBSERVATION_SOURCE_STATES.md
  - firmware/mqtt_heartbeat/README.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - flashing firmware without explicit operator confirmation
  - claiming USB-Free hardware runtime pass before validation
  - claiming real Wi-Fi scan, real IMU product readiness, battery accuracy, or power behavior
  - changing raw-frame profile or public protocol version
  - learned known-place matching, model training, or server-side fusion scoring
  - long LTE stability, reconnect, enclosure, or product readiness
  - modifying GitLab or unrelated VPS services
---

# LOC-005A Firmware-Side Observation Source States

## Goal

Extend the LOC-004A raw LTE `location_observation` Walking Skeleton with
explicit firmware-side evidence slots for Wi-Fi, IMU, and power so failures
become explainable before long stability, enclosure, and model-training work.

The key distinction is that this task does not pretend those sources are
ready. It preserves the raw-frame-first path and labels each source as
`observed`, `disabled`, `missing`, `mock`, or `unverified` as appropriate.

## Acceptance

- [x] Firmware raw KV `location_observation` includes compact `wifi_*`,
      `imu_*`, and `power_*` source/evidence status fields.
- [x] LTE observation mode still uses raw-frame/KV, not JSON, and stores the
      original frame before server-side derivation.
- [x] Message Hub derives raw KV Wi-Fi, IMU, and power fields into structured
      `wifi`, `imu`, and `power` groups on `location_observation`.
- [x] `/api/state` observability exposes Wi-Fi/IMU/power `source_status` and
      `evidence_status`.
- [x] Dashboard field state shows the new evidence statuses.
- [x] Tests protect the firmware string contract and server derivation path.
- [x] Hardware flashing passes after explicit operator confirmation.
- [x] USB-Free runtime validation is explicitly left as a pending follow-up
      and is not claimed by this flash evidence.

## Evidence

- Firmware raw observation fields:
  `wifi_source_status=disabled`, `wifi_evidence_status=missing`,
  `imu_source_status`, `imu_evidence_status`, `imu_data_is_mock`,
  `power_source_status`, `power_evidence_status`, and
  `power_reason=platform_power_source_not_product_meter`.
- Server raw parser fields:
  `raw_wifi_from_kv`, `raw_imu_from_kv`, and `raw_power_from_kv`.
- Focused tests:
  `python -m unittest quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard -v`
  passed with 32 tests.
- Repository gates:
  `python scripts/context_lint.py` PASS; `git diff --check` PASS;
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS with
  299 tests.
- ESP-IDF guarded build:
  `powershell -ExecutionPolicy Bypass -File scripts\prepare_fw001_hw_config.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-loc005a-source-states -TestRunId loc005a-source-states-20260630-001 -BuildDir build_loc005a_source_states -EnableSim7670Gnss -EnableSim7670LocationObservation -Build -Json`
  passed and generated
  `firmware/mqtt_heartbeat/build_loc005a_source_states/egolink_mqtt_heartbeat.bin`
  (`300448` bytes). The script reported `flash_intentionally_not_run=true`.
- VPS deployment:
  copied the updated `server/message_hub.py` to
  `/opt/egolink-message-hub/server/message_hub.py`, restarted
  `egolink-message-hub.service`, and verified `/health` from both
  `127.0.0.1:8790` and `203.0.113.10:8790`. The existing GitLab service
  remained `active`.
- Flash:
  `powershell -ExecutionPolicy Bypass -File scripts\run_fw001_hw_r1.ps1 -HostName 203.0.113.10 -FwVersion 0.1.0-loc005a-source-states -TestRunId loc005a-source-states-20260630-001 -BuildDir build_loc005a_source_states -EnableSim7670Gnss -EnableSim7670LocationObservation -Flash -FlashPort COM4 -IUnderstandFlashWritesFirmware -Json`
  passed after explicit operator confirmation. Evidence:
  `reports/field_validation/loc005a-source-states-20260630-001/flash_report.md`.
  `esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote bootloader, app
  (`300448` bytes), and partition table, verified all hashes, and completed
  hard reset.

## Boundaries

- Wi-Fi is explicitly marked `disabled` / `missing` on the current LTE
  location-observation path because Wi-Fi runtime remains skipped in that
  mode.
- IMU is reported through `platform_imu` status. The default path is still
  mock/unverified unless a product-topology hardware backend is enabled and
  validated.
- Power is reported through `platform_power` source labels. The default source
  remains mock/log-backend evidence, not battery accuracy or product power
  validation.
- This task prepares source-state data for EALE-P0 and later datasets; it does
  not add known-place matching, model training, or a new fusion rule.

## Remaining Risks

- The new LOC-005A firmware image has been flashed, but has not yet been
  validated over independent power with USB disconnected.
- A later source-specific task must add privacy-reviewed Wi-Fi fingerprints,
  product-topology IMU validation, and real battery/power instrumentation
  before these signals can drive user-visible location confidence.
