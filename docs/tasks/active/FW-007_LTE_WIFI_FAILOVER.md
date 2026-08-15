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
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
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
- [x] An operator-authorized SIM-absent run observes LTE failure, Wi-Fi
      connection, fresh uploads, and no duplicate transport owner or reset loop
      in bounded post-takeover windows.

# Validation Commands

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

- Authorized by the operator on 2026-08-15. The run used
  `connectivity-node-001`, CH343 ESP32 console `COM3`, and the already-present
  SIM7670G USB ports `COM4`-`COM7`. Read-only chip identification matched the
  registered ESP32-S3 QFN56 revision v0.2 and MAC `02:00:00:00:00:03`.
- The image was built from repository HEAD
  `82a23306123a019c9a1b538598d5e954262808d6`; the four firmware/test source
  paths were byte-identical to implementation commit
  `e9ca7a4673f434697e0ae0e6b2faca2ba1467784`. Runtime identity was
  `0.1.0-fw007-lte-wifi-failover`, and the ESP-IDF application descriptor was
  explicitly fixed to `fw007-e9ca7a4`.
- Exactly one three-region flash was performed on `COM3`: bootloader at `0x0`,
  partition table at `0x8000`, and application at `0x10000`. All three writes
  passed esptool hash verification. The flash operation did not target or
  erase the NVS partition; normal boot diagnostics subsequently retained and
  updated their `boot_count` value through the firmware's existing NVS path.
- The bounded startup observed `reset_reason=poweron`, QMI8658
  `WHO_AM_I=0x05`, revision `0x7c`, reset result `0x80`, and confirmed idle
  measurement stop. A bounded read-only USB AT check independently returned
  `SIM_NOT_INSERTED` on the responsive modem interfaces; no SIM identifier was
  queried or retained.
- LTE readiness remained `LTE_SIM_NOT_READY` until the configured readiness
  counter reached `waited_sec=120`. Because individual modem status queries
  are bounded but take time, the transition occurred at device uptime about
  286.0 seconds rather than 120 seconds of wall time. The state then moved once
  from `lte_primary` to `wifi_connecting` for `lte_attach_timeout`, reached a
  Wi-Fi connection in about 4.47 seconds, reached `wifi_active` in about 4.51
  seconds, and registered with Message Hub HTTP 200 in about 5.09 seconds.
- Wi-Fi-owner evidence included raw command polling, HTTP-200 heartbeats, and
  successful periodic location upload. A 45-second post-takeover window saw
  four Wi-Fi raw polls, two successful heartbeats, one successful periodic
  location, zero LTE command-poll rounds, zero offline transitions, and zero
  reset, panic, or brownout markers. A following 55-second window again saw
  zero LTE poll, reset, panic, or brownout markers.
- One bounded `request_location` command (`fw007wifi001`) was intentionally
  queued as part of the authorized test. VPS state retained one linked
  `location_report` at sequence 26 followed by one `ok` ACK at sequence 27;
  the ACK reported `transport_type=wifi`, the FW-007 version, and the matching
  test-run identity.
- A final authenticated, read-only VPS check at
  `2026-08-15T18:38:53+08:00` reported sequence 39,
  `link_type=wifi_failover`, `LTE_SIM_NOT_READY`, `reset_reason=poweron`, the
  FW-007 runtime version, and the matching test-run identity. Coordinates,
  Wi-Fi credentials, bearer tokens, and SIM identifiers are omitted from this
  evidence.
- Local ignored build-artifact path:
  `firmware/mqtt_heartbeat/build_fw007_hw_20260815/`. It contains runtime
  configuration and is not a committed replay bundle. No raw private serial
  transcript or VPS export was committed; the bounded runtime claims are
  summarized here and were re-queried from the live VPS during independent
  review.

# Completion Evidence

- Software implementation, static/build validation, and the authorized
  SIM-absent hardware run completed on 2026-08-15. The packet remains active
  pending Director review and closure.
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
- The hardware-run image under
  `firmware/mqtt_heartbeat/build_fw007_hw_20260815/` was generated with ESP-IDF
  5.4.2. Its sdkconfig is 74,456 bytes, SHA-256
  `73BA7E33537223755ED183FBDBB8ECA3F73268788B9319EA16D4FA1DC1C04BF6`.
  The application is 984,912 bytes, SHA-256
  `8F3508C62CA96C54628B3C3FB0A64B5BB14EAF7BBB8188DA54FAEE0739283799`;
  the bootloader is 20,928 bytes, SHA-256
  `1EDDD94A293C483AF64AFA6C1EED83EFA24D6FD7746A5D07AFEEFC189364B66E`;
  and the partition table is 3,072 bytes, SHA-256
  `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`.
- Remaining risks: the image leaves about 6% of the smallest app partition free;
  the first slice has no automatic Wi-Fi-to-LTE failback or durable offline
  queue; the `120`-second LTE readiness setting currently measures configured
  delay time rather than end-to-end wall time, so the observed SIM-absent
  takeover took about 4 minutes 50 seconds from boot; because the SIM was
  already absent at power-on, an online LTE session followed by physical SIM
  removal and the consecutive-transport-failure threshold remains a separate
  unverified hardware path;
  a separate tracked `camera_smoke/sdkconfig` still has non-empty
  `CONFIG_EGOLINK_WIFI_SSID` and `CONFIG_EGOLINK_WIFI_PASSWORD` entries and is
  outside this task's allowed paths. No values were copied or emitted.
