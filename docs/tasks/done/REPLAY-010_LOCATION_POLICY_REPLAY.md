---
id: REPLAY-010
title: Location and Sensor Policy Replay
status: accepted_for_transition
priority: high
lane: A
execution_state: completed
depends_on:
  - LOC-020
  - POLICY-010
serves_gate: P0-LOC
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/development/LOCATION_DATASET.md
  - docs/tasks/done/LOC-020_LOCATION_ENGINE_V0.md
  - docs/tasks/done/POLICY-010_SENSOR_POLICY_V0.md

allowed_paths:
  - docs/tasks/done/REPLAY-010_LOCATION_POLICY_REPLAY.md
  - pc_simulator/location_policy_replay.py
  - tools/run_location_policy_replay.py
  - quality_tests/test_location_policy_replay.py
  - docs/development/LOCATION_DATASET.md

out_of_scope:
  - creating a second field-session timeline or copying private coordinates
  - model training, automatic policy promotion or hardware commands
---

# Goal

Reuse the accepted Field Session timeline to rerun Location Engine/Sensor
Policy deterministically under one or more configurations and compare effects.

# Acceptance

- [x] Normalized observations retain event-time, source, attempt/result and
      lineage; unavailable cross-source order stays unavailable.
- [x] Replay emits state/action timeline plus location availability,
      uncertainty, GNSS attempt, cell observation and policy-state metrics.
- [x] Two configurations can be compared without rewriting source evidence.
- [x] Replayed output cannot claim measured battery savings or accuracy that
      the source Session does not contain.

# Validation Commands

```powershell
python -m unittest quality_tests.test_location_policy_replay -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Current Evidence

- Replay delegates sealed-package validation and timeline construction to the
  existing A0 Field Session implementation; it does not create another raw
  evidence format.
- Ambiguous/unavailable cross-source ordering, mock inputs and camera rows are
  counted and excluded rather than guessed.
- The real FT-001B fixture now retains 2 GNSS policy observations and 100
  evidence annotations from 103 input rows; a zero-observation replay cannot
  report completion. Both fixes remain honestly rejected because the source
  fixture has no reported accuracy or HDOP.
- Real FIELD-020 evidence remains pending and all hardware claims stay
  `unverified`.

# Completion Evidence

- Changed files: replay/CLI/tests/documentation are present in allowed paths
  and passed independent integration review with LOC/POLICY.
- Test result: `14/14` focused and `50/50` combined LOC/POLICY/REPLAY tests
  PASS on 2026-08-23; repository verification passed `875/875`, `context_lint`
  passed and targeted `git diff --check` passed.
- Hardware result: not required and not run; source field evidence is reused.
- Remaining boundary: completion means the replay ran with at least one
  external location observation; it is not a claim that a fix was usable or
  that battery savings/accuracy were measured. FIELD-020 and `P0-LOC` remain.

# Builder Prompt

```text
Read docs/tasks/done/REPLAY-010_LOCATION_POLICY_REPLAY.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. Work only inside allowed_paths. Correct the real FT-001B coverage
failure, prevent replay/policy output from copying or inventing coordinates,
model required timer events, and make CLI error, closure and multi-config
comparison behavior fail honestly. Reuse the accepted Field Session loader and
preserve event-time/lineage; do not create another evidence format or make
measured battery/accuracy claims. Add regression tests, run every validation
command, and report exact output and remaining risks. Keep execution_state
in_progress until implementation is complete, then request independent review.
```
