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
  - quality_tests/AGENTS.md
  - quality_tests/test_mqtt_heartbeat_firmware.py

allowed_paths:
  - docs/tasks/active/FW-007_LTE_WIFI_FAILOVER.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
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

- [ ] The feature is disabled by default and requires non-empty Wi-Fi runtime
      configuration when enabled.
- [ ] LTE remains the only initial upload owner. Attach failure or a configurable
      consecutive transport-failure threshold triggers Wi-Fi once; command,
      heartbeat, sensor, and periodic location work have only one active owner.
- [ ] A successful LTE poll resets the consecutive failure count. A parsed empty
      command response is transport health, not a failure merely because no ACK
      was produced.
- [ ] The transition is explicit in bounded logs/status and does not expose Wi-Fi
      credentials, bearer tokens, SIM identifiers, or coordinates.
- [ ] Wi-Fi connection failure ends in an explicit offline/fail-closed state; it
      does not reboot, loop forever, or alternate transports.
- [ ] Focused source/state tests, an ESP-IDF build of the enabled combined profile,
      full repository verification, context lint, and diff checks pass.
- [ ] Hardware behavior remains unverified until a later authorized run removes
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

- Pending implementation and static/build validation.
