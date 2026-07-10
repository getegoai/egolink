---
id: PWR-002
title: Low-power location state-machine decision record
status: completed
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/archive/research/location_technology_discussion_20260703.md
  - docs/archive/research/fusion_algorithm_discussion_20260703.md

allowed_paths:
  - docs/development/
  - docs/hardware/
  - docs/architecture/adr/
  - docs/tasks/

out_of_scope:
  - firmware scheduler or sensor-control implementation
  - changing the live device wire protocol
  - changing EALE-P0 public location states without an ADR
  - claiming measured power savings or battery life
  - running hardware, flashing firmware, or collecting long power data
---

# Problem

Claude's review identifies a real design gap: the research notes propose an
L0-L4 low-power location state machine, while the authoritative
`LOCATION_ENGINE.md` and `LOCATION_FUSION_ALGORITHM.md` already define EALE-P0
location belief states but do not freeze a power/location scheduling decision.

PWR-001 measures battery telemetry and the first 24h baseline. It does not
decide how GNSS, Wi-Fi, IMU, LTE, and reporting cadence should be scheduled by
risk, uncertainty, and power state.

# Expected Result

Create a decision record that either adopts, rejects, or defers the L0-L4
low-power location state-machine concept, with clear reasons and follow-up
tasks. If adopted, update the authoritative location/power docs with a
non-implementation design boundary.

# Acceptance Criteria

- [x] A decision record or ADR states one of: adopt, reject, or defer L0-L4
      low-power location states, with rationale.
- [x] The decision maps proposed states such as Deep Sleep, Low Power Watch,
      Moving Normal, Uncertain Locate, and Emergency Track to existing EALE-P0
      concepts without replacing public location states (`Fine`, `Coarse`,
      `Predicted`, `Unknown`).
- [x] Required telemetry is defined before implementation: state entry/exit
      timestamps, transition reason, GNSS attempt budget, power source/status,
      battery voltage or SoC when available, and emergency override reason.
- [x] Safety boundaries are explicit: emergency tracking can spend more power,
      but normal power optimization must not disable required SOS, location
      evidence, or communication behavior.
- [x] The design remains a scheduling/power policy, not a positioning-accuracy
      claim and not evidence that 48h/7d targets are met.
- [x] Follow-up task IDs are proposed for firmware implementation and
      validation only after PWR-001 and FIELD-003 evidence are available.
- [x] `python scripts/context_lint.py` passes.

# Validation Commands

```powershell
python scripts/context_lint.py
```

# Hardware Validation

- Not applicable. This task is a design decision and documentation update.

# Decisions

- The research notes are useful inputs, not authoritative sources. The final
  decision must land in `docs/architecture/adr/` or current authoritative
  docs before implementation work begins.

# Completion Evidence

- review1 (2026-07-03, codex): adopted the L0-L4 concept as a low-power
  location scheduler, not as a replacement for EALE-P0 public location states.
  Decision recorded in
  `docs/architecture/adr/ADR-0003-low-power-location-state-machine.md`; short
  boundaries added to `docs/development/LOCATION_ENGINE.md` and
  `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`.
- Changed files:
  - `docs/architecture/adr/ADR-0003-low-power-location-state-machine.md`
  - `docs/development/LOCATION_ENGINE.md`
  - `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`
  - `docs/tasks/active/PWR-002_LOW_POWER_LOCATION_STATE_MACHINE_DECISION.md`
- Test result: `python scripts/context_lint.py` PASS; `git diff --check`
  reported no whitespace errors, only existing CRLF normalization warnings for
  PowerShell scripts outside this documentation change.
- Hardware result: not applicable
- Remaining risks: firmware scheduler implementation is deferred until
  PWR-001 battery evidence and FIELD-003 outdoor GNSS evidence are available.
- review2 (2026-07-03, codex): during workspace organization, moved the
  research-note context from repository-root Chinese filenames into
  `docs/archive/research/` as historical input and updated this packet's
  `context` paths. No design decision changed.

# Builder Prompt

```text
Read docs/tasks/active/PWR-002_LOW_POWER_LOCATION_STATE_MACHINE_DECISION.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Decide whether to adopt, reject, or defer the L0-L4
low-power location state machine. If adopted, update only authoritative docs
or an ADR with the design boundary and telemetry requirements. Do not
implement firmware scheduling. Run the validation command before finishing.
Return changed files, validation output, and remaining decisions. Do not
update docs/current/STATUS.md and do not move this packet to done/.
```
