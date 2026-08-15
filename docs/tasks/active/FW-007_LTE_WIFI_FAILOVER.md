---
id: FW-007
title: Bounded LTE to Wi-Fi engineering failover
status: active
priority: high
requires_hardware: true
serves_demo: D2-D5
created: 2026-08-15
last_updated: 2026-08-15

context:
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - firmware/mqtt_heartbeat/sdkconfig
  - quality_tests/AGENTS.md
  - quality_tests/test_mqtt_heartbeat_firmware.py

allowed_paths:
  - docs/tasks/active/FW-007_LTE_WIFI_FAILOVER.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - firmware/mqtt_heartbeat/sdkconfig
  - quality_tests/test_mqtt_heartbeat_firmware.py

out_of_scope:
  - protocol/schema changes, pin changes, APN changes, or modem firmware changes
  - plaintext Wi-Fi credentials, bearer tokens, SIM identifiers, or private logs in Git
  - durable offline queues, production radio claims, or Wi-Fi as a required safety link
  - automatic Wi-Fi-to-LTE failback, modem power cycling, or unbounded reconnect loops
  - firmware flashing, hardware commands, or long serial capture without a later explicit operator instruction
---

# Goal

Add an opt-in engineering failover path to the current combined firmware so a
bounded LTE attach failure or consecutive LTE transport failures can start the
already-proven ESP32 Wi-Fi Message Hub path instead of leaving the device
offline. The first slice is deliberately one-way until reboot.

# Acceptance Criteria

- [x] The feature is disabled by default and requires non-empty Wi-Fi runtime
      configuration when enabled.
- [x] LTE remains the only initial upload owner. Attach failure or a configurable
      consecutive transport-failure threshold triggers Wi-Fi once; command,
      heartbeat, sensor, and periodic location work have only one active owner.
- [x] A successful LTE poll resets the consecutive failure count. A parsed empty
      command response is transport health, not a failure merely because no ACK
      was produced.
- [x] The transition is explicit in bounded logs/status and does not expose Wi-Fi
      credentials, bearer tokens, SIM identifiers, or coordinates.
- [x] Wi-Fi connection failure ends in an explicit offline/fail-closed state; it
      does not reboot, loop forever, or alternate transports.
- [x] Focused source/state tests, an ESP-IDF build of the enabled combined profile,
      full repository verification, context lint, and diff checks pass.
- [x] Hardware behavior remains unverified until a later authorized run removes
      the SIM, observes LTE failure, Wi-Fi connection, fresh uploads, and no
      duplicate transport owner or reset loop.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

- Not authorized in this slice. Build/static verification may run; flashing,
  SIM removal, Wi-Fi connection, and serial capture require a later explicit
  operator instruction.

# Completion Evidence

- Software implementation and static/build validation completed on 2026-08-15;
  task remains active because the authorized hardware validation has not run.
- Changed paths are limited to this task packet, `app_main.c`,
  `Kconfig.projbuild`, the tracked MQTT heartbeat `sdkconfig`, and its focused
  firmware test.
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v`: 17 tests,
  PASS.
- Enabled combined-profile ESP-IDF 5.4.2 build: PASS in
  `firmware/mqtt_heartbeat/build_fw007_failover` using two ignored local
  sdkconfig overlays. Build identity was repository HEAD
  `c2ac2a7a47c9389d400aad98c91d92eb82b51ea4` plus the five uncommitted FW-007
  scoped files (`git describe`: `v0.1.0-68-gc2ac2a7-dirty`); HTTP, LTE command
  loop, FW-007 failover, threshold 3, and D1 periodic location were enabled. The
  generated sdkconfig is 74,455 bytes with
  SHA-256 `33604A8EAE9253536AAE68C053721DC49E82D5B5E9B2D3C30D956EEC3541DC76`.
- Build artifacts: app image 984,912 bytes, SHA-256
  `0C3B61AC20FF3978690F155ED28CA1779DE8B4F9F1E702FB93F763D2C23C19E6`;
  bootloader 20,928 bytes, SHA-256
  `0C6EFF1CD80A87C2F5EFF8FE753280F3585854D882C26E127D8E8C7E95A70EAF`;
  partition table 3,072 bytes, SHA-256
  `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: 659 tests,
  PASS in 74.6 seconds wall time (74.019 seconds reported by unittest).
- `python scripts\context_lint.py`: PASS. `git diff --check`: PASS.
- Independent source review found and then verified the fix for one takeover
  blocker: Wi-Fi now polls and ACKs raw commands with the same parser and
  executed-command cache used before takeover. `set_report_interval`,
  `request_location`, and `capture_imu_window` no longer fall through the legacy
  generic JSON ACK path, and Wi-Fi-active heartbeat/sensor status no longer
  claims mock 4G or a mock GNSS fix.
- No firmware flash, SIM manipulation, device command, or serial capture was
  performed. LTE-to-Wi-Fi takeover, fresh uploads, duplicate-owner absence, and
  reset-loop absence remain unverified on hardware.
- Remaining risks: the image leaves about 6% of the smallest app partition free;
  a separate tracked `camera_smoke/sdkconfig` still has non-empty
  `CONFIG_EGOLINK_WIFI_SSID` and `CONFIG_EGOLINK_WIFI_PASSWORD` entries and is
  outside this task's allowed paths. No values were copied or emitted.
