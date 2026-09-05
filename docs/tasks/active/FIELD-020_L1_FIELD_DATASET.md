---
id: FIELD-020
title: P0-LOC representative field dataset
status: active
priority: critical
lane: A
execution_state: queued
depends_on:
  - LOC-021
serves_gate: P0-LOC
requires_hardware: true
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/development/FIELD_TEST.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md

allowed_paths:
  - docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md

out_of_scope:
  - flashing or sending commands without explicit operator intent
  - training models, collecting default raw media or hiding failed observations
  - duplicating FT-001B/FIELD-003/PWR-001 tooling
---

# Goal

Run one representative-day campaign across outdoor, indoor, mall,
underground, vehicle/bus, walking, stationary and bag-carried conditions while
reusing existing capture, accuracy, session and power tools.

# Acceptance

- [ ] One immutable device/firmware/config identity and complete Session
      lineage cover all declared scenarios and attempted/failed observations.
- [ ] Report includes location availability/continuity, GNSS fix rate/TTFF,
      median/P90 reference error where ground truth exists, update latency,
      cell change, mobility evidence, no-fix/backoff, disconnects and power.
- [ ] Camera, if manually enabled as an experiment, records only authorized
      still references with event time and `manual_field_test` or
      `gnss_no_fix_experiment`; it does not affect a P0 decision.
- [ ] Dataset remains training-disabled until consent/review explicitly allows.

# Hardware Boundary

The operator must authorize the exact build/flash/campaign and evidence path.
Amend `allowed_paths` with that explicit path at dispatch rather than creating
an empty or guessed evidence directory now.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

The reviewed field kit must name all additional static checks and bounded
operator commands before execution.

# Completion Evidence

- Changed files: pending field-kit dispatch.
- Test/hardware/evidence: `NOT_RUN`.
- Remaining risks: integrated config identity, independent power, ground
  truth, scenario coverage, privacy and battery evidence.

# Builder Prompt

```text
Read docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. Begin only
after LOC-021 is accepted. Reuse the existing field/session/accuracy/power
tooling and prepare one immutable device/firmware/config campaign manifest.
Before collection, amend allowed_paths with the reviewed private evidence path
and obtain explicit operator intent for the exact flash/run/campaign. Cover all
declared scenarios, retain attempts/failures and ground-truth limits, and keep
camera stills manual, consented and non-decisional. Run every validation command
and the bounded field plan; return exact identity, metrics, evidence paths and
coverage/privacy/power risks. Do not authorize training or claim P0-LOC from
partial scenario evidence.
```
