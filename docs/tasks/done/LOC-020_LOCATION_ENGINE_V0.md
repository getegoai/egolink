---
id: LOC-020
title: Location Engine v0
status: accepted_for_transition
priority: critical
lane: A
execution_state: completed
depends_on: []
serves_gate: P0-LOC
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/development/LOCATION_ENGINE.md
  - docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md

allowed_paths:
  - docs/tasks/done/LOC-020_LOCATION_ENGINE_V0.md
  - docs/development/LOCATION_ENGINE.md
  - pc_simulator/location_engine_v0.py
  - shared/contracts/location_engine_v0.schema.json
  - shared/contracts/README.md
  - quality_tests/test_location_engine_v0.py

out_of_scope:
  - firmware or live wire-protocol changes
  - learned fusion, dead reckoning, camera, anomaly or context models
  - claiming P0-LOC or hardware acceptance
---

# Goal

Implement the smallest deterministic, event-time-ordered reference Location
Engine v0 that preserves last trusted location and emits explainable belief
state without inventing coordinates.

# Acceptance

- [x] State includes mobility, GNSS, LTE, last-trusted location/time, belief,
      accuracy, confidence, source, uncertainty, battery and policy context.
- [x] Belief remains `Fine/Coarse/Predicted/Unknown`; no-fix preserves a
      bounded last-trusted belief or becomes `Unknown` honestly.
- [x] Input time cannot move backward; receive time never replaces event time.
- [x] Cell/IMU/battery and untrusted/mock GNSS input cannot fabricate a precise
      coordinate or promote a belief to `Fine`.
- [x] Output validates against one versioned schema and is deterministic.

# Validation Commands

```powershell
python -m unittest quality_tests.test_location_engine_v0 -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Boundary

This is a PC-side contract/reference core for firmware and VPS integration. It
does not pass `P0-LOC`; FIELD-020 and representative-product gates remain.

# Current Evidence

- Reference reducer: `pc_simulator/location_engine_v0.py`.
- Contract: `shared/contracts/location_engine_v0.schema.json`.
- Focused validation: `18/18` tests PASS on 2026-08-23; coupled LOC/POLICY
  validation is `36/36` PASS and REPLAY compatibility is `14/14` PASS.
- Integration boundary: no firmware or Message Hub adapter changed; server
  event-time ownership and device runtime integration remain follow-up work.

# Completion Evidence

- Changed files: reference reducer, schema, focused tests and documentation are
  present in the packet's allowed paths and passed independent semantic review.
- Test result: `18/18` focused, `36/36` coupled LOC/POLICY and `14/14` REPLAY
  compatibility tests PASS on 2026-08-23; repository verification passed
  `875/875`, `context_lint` passed and targeted `git diff --check` passed.
- Hardware result: not required for this PC reference packet and not run.
- Remaining boundary: capture-time division and same-lane ordering are enforced
  by the reducer rather than expressible as JSON Schema cross-field arithmetic;
  LOC-021 must port the same validation and preserve its evidence fields. This
  accepted PC reference does not pass `P0-LOC`.

# Builder Prompt

```text
Read docs/tasks/done/LOC-020_LOCATION_ENGINE_V0.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. Work only
inside allowed_paths. Independently review capture-time/boot lineage binding,
transactional rejection, GNSS quality conflicts, schema-valid evidence output,
no-fix preservation and deterministic replay. Add focused regressions for any
new defect without inventing coordinates, changing firmware/wire protocol, or
claiming P0-LOC. Run every validation command and report changed files, exact
output and remaining risks; leave execution_state in_review until that review
and full-suite validation accept it.
```
