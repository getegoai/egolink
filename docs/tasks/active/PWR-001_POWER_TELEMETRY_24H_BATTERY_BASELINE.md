---
id: PWR-001
title: Real power telemetry and first 24h battery baseline run
status: active
priority: high
requires_hardware: true
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
  - docs/hardware/POWER_MEASUREMENT_SCENARIO_TEMPLATE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/PROTOCOL.md

allowed_paths:
  - firmware/
  - server/
  - scripts/
  - docs/hardware/
  - quality_tests/

out_of_scope:
  - claiming 48h/7d product battery life from this run
  - changing the observation envelope beyond additive power fields
  - enclosure or charging-circuit work
  - GNSS/LTE behavior changes
---

# Problem

All power fields in current observations are mock (`battery=87`,
`link_type=mock_4g_over_wifi` era defaults; power `source_status=mock`
throughout LOC/OBS tasks). POWER_AND_BATTERY_ENGINEERING_TARGETS.md sets 48h/7d
targets but zero long-duration measurements exist. Power is the product's
lifeline and currently entirely paper-based. V1-M1 requires a first honest
baseline.

# Expected Result

Step 1 (builder): firmware reads real battery voltage on the active board
(audit what the Waveshare ESP32-S3-SIM7670G exposes: ADC pin / fuel gauge /
none — record the finding in BOARD_MATRIX.md) and reports it as additive
power fields with `source_status=measured` (or documents why measurement is
impossible on this board). Step 2 (operator + builder tooling): one
unattended >= 24h battery-powered run, with the power curve reconstructed
from VPS-side data and exported as a report.

# Acceptance Criteria

- [ ] Audit note in `docs/hardware/BOARD_MATRIX.md`: what battery sensing the
      active board actually provides, with schematic/datasheet reference.
- [ ] If measurable: firmware reports periodic battery voltage (and charging
      state if available) as additive fields; `source_status` transitions
      from `mock` to `measured`; unit test covers the new field parsing.
- [ ] If not measurable on this board: a written fallback plan (external
      logging multimeter / PPK2 / USB power meter protocol) recorded in
      `docs/hardware/`, and the run below uses the fallback.
- [ ] One >= 24h unattended run on battery power, USB-Free, with evidence
      per hardware rules (board, firmware commit, timestamps, evidence path).
- [ ] Export script produces a power-curve report (voltage/SoC vs time,
      transport events overlaid) under `reports/power/` from VPS data.
- [ ] Report explicitly states measured average consumption estimate and the
      gap vs the 48h target — as engineering record, not product claim.
- [ ] `scripts/verify.ps1` passes.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Board: connectivity-node (Waveshare ESP32-S3-SIM7670G), battery-powered
- Firmware commit: record at flash time
- Connection: USB-Free; evidence via VPS Message Hub only
- Expected output: >= 24h of periodic power samples in event store
- Evidence path: reports/power/PWR-001-<date>/

# Decisions

- Development-board numbers do not represent production hardware; the report
  must carry this caveat (per POWER_AND_BATTERY_ENGINEERING_TARGETS.md rule 6).

# Completion Evidence

- Changed files:
- Test result:
- Hardware result:
- Evidence path:
- Remaining risks:

# Builder Prompt

```text
Read docs/tasks/active/PWR-001_POWER_TELEMETRY_24H_BATTERY_BASELINE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Implement the audit + firmware/telemetry/tooling parts;
flashing and the 24h battery run are operator actions — prepare exact
step-by-step operator instructions instead of executing them. Run the
validation commands before finishing. If any acceptance criterion cannot be
met, stop and report the blocker. Return: changed files, validation output,
evidence paths. Do not update docs/current/STATUS.md and do not move this
packet to done/.
```
