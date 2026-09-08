---
id: POLICY-010
title: Configurable Sensor Policy v0
status: accepted_for_transition
priority: critical
lane: A
execution_state: completed
depends_on:
  - LOC-020
serves_gate: P0-LOC
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0003-low-power-location-state-machine.md
  - docs/development/LOCATION_ENGINE.md
  - docs/tasks/done/LOC-020_LOCATION_ENGINE_V0.md

allowed_paths:
  - docs/tasks/done/POLICY-010_SENSOR_POLICY_V0.md
  - docs/development/LOCATION_ENGINE.md
  - pc_simulator/sensor_policy_v0.py
  - shared/config/sensor_policy_v0.json
  - shared/contracts/sensor_policy_v0.schema.json
  - shared/contracts/sensor_policy_decision_v0.schema.json
  - shared/contracts/README.md
  - quality_tests/test_sensor_policy_v0.py

out_of_scope:
  - tuning parameters as product-optimal without field evidence
  - camera activation, AI decisions or learned policy
  - firmware integration before the reference contract is accepted
---

# Goal

Turn motion, belief quality, battery and SOS into bounded sensor actions using
one versioned configuration instead of hard-coded sampling guesses.

# Acceptance

- [x] Effective states support `STABLE`, `MOVING`, `LOCATION_UNCERTAIN`, `SOS`
      and `LOW_BATTERY`; SOS always overrides battery suppression.
- [x] Stationary/moving intervals, IMU rates, GNSS timeout/backoff,
      uncertainty growth, low-battery and SOS behavior are configured.
- [x] A no-fix action records failure, preserves last trusted truth, schedules
      bounded backoff and never loops immediately.
- [x] Camera remains `OFF/not_requested` in every P0 policy action.
- [x] Identical accepted state/config produces internally consistent actions,
      timers and explanation.

# Validation Commands

```powershell
python -m unittest quality_tests.test_sensor_policy_v0 -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Current Evidence

- The unverified engineering defaults live in one strict JSON configuration;
  they are replay variables, not product-optimal sampling claims.
- Config and decision contracts reject undeclared camera policy fields.
- Focused validation: `18/18` tests PASS on 2026-08-23; coupled LOC/POLICY
  validation is `36/36` PASS and REPLAY compatibility is `14/14` PASS.
- LOC-020/POLICY-010/REPLAY-010 are one coupled review candidate assembled
  sequentially; they are not three concurrent Lane A builders.

# Completion Evidence

- Changed files: configurable policy, schemas, focused tests and documentation
  are present in the packet's allowed paths and passed independent semantic
  review.
- Test result: `18/18` focused, `36/36` coupled LOC/POLICY and `14/14` REPLAY
  compatibility tests PASS on 2026-08-23; repository verification passed
  `875/875`, `context_lint` passed and targeted `git diff --check` passed.
- Hardware result: not required for this PC reference packet and not run.
- Remaining boundary: JSON Schema 2020-12 cannot express all cross-field
  arithmetic/order rules. Config now requires
  `egolink.sensor_policy.semantic.v0.1`; LOC-021 firmware/VPS consumers must port
  that named validator rather than treating structural schema PASS as semantic
  acceptance. This accepted PC reference does not pass `P0-LOC`.

# Builder Prompt

```text
Read docs/tasks/done/POLICY-010_SENSOR_POLICY_V0.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. Work only
inside allowed_paths. Independently review policy event-time atomicity,
freshness/horizon/mobility wake deadlines, bounded retry cleanup, critical
battery explanation, SOS precedence and the named semantic validator. Keep
camera OFF, do not tune defaults as product truth or claim P0-LOC. Add focused
regressions for any new defect, run every validation command, and leave
execution_state in_review until independent review and full-suite validation
accept it.
```
