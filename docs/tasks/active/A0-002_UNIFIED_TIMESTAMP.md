---
id: A0-002
title: Unified sensor timestamp and time-lineage validation
status: active
priority: critical
requires_hardware: true
created: 2026-08-17
last_updated: 2026-08-17

context:
  - docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
  - docs/current/ACTIVE_BUILD.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - shared/contracts/README.md

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/tasks/active/A0-002_UNIFIED_TIMESTAMP.md
  - pc_simulator/sensor_time_lineage.py
  - quality_tests/test_a0_unified_timestamp.py
  - scripts/validate_sensor_time_lineage.py
  - shared/contracts/README.md
  - shared/contracts/clock_mapping_segment.schema.json
  - shared/contracts/sensor_time_lineage.schema.json

out_of_scope:
  - firmware changes or device protocol/wire changes in this static slice
  - Message Hub schema, storage, ingestion or deployment changes
  - issuing hardware commands, flashing, camera capture or starting a field session
  - defining the enclosing A0-003 Field Session schema
  - replay, evaluation, model training or Location Belief behavior
  - marking A0-002 or A-R0 passed without reviewed real four-source session evidence
execution_state: queued
owner: unassigned
reviewed_at: 2026-09-22
---

# Problem

Current observations preserve useful but incompatible time evidence. `ts` may
mean ISO UTC, device `uptime_ms`, or an opaque raw-frame placeholder. IMU
windows carry precise boot-scoped device uptime and sample offsets but no UTC
anchor. Raw LTE/GNSS observations may have sequence and receive time without a
device monotonic timestamp. Camera has no structured time record. Server
receive time is affected by transport and must not be relabelled as source
time.

Without explicit clock lineage, later replay, multisource fusion and proactive
safety cannot establish ordering, causality or synchronization error.

# Expected Result

An additive v0.1 contract and one offline command represent source time,
boot-scoped device monotonic time, UTC, receive/ingest time, clock mappings,
uncertainty and immutable lineage without changing the current product wire
path. The validator fails closed on ambiguous clocks and emits a
machine-readable coverage/alignment report.

# Acceptance Criteria

- [x] A machine-readable observation contract distinguishes source,
  monotonic, UTC, receive and ingest time, with explicit clock/boot/sequence,
  alignment uncertainty, reason codes and immutable lineage.
- [x] A bounded monotonic-to-UTC mapping contract records origins, explicit
  rate-correction semantics, validity, immutable anchors, recomputable fit
  error and uncertainty without crossing a boot boundary.
- [x] The offline validator rejects clock/boot/unit/order/mapping conflicts,
  preserves idempotent duplicates, verifies IMU `start + offset`, and never
  computes a cross-source error without a common verified anchor.
- [x] Automated tests cover Grok's 14-item fail-open matrix plus independent
  clock-domain, drift-sign, adversarial anchor, malformed input, overflow and
  semantic-isolation and receive/ingest causality cases (22 focused tests
  total).
- [ ] Named producers/adapters emit lineage for GNSS, LTE, IMU and Camera
  without replacing missing source time with server receive time.
- [ ] One real Field Session contains all four sources with immutable source
  evidence, source/sequence/boot-scoped monotonic/UTC lineage, ordering and
  source-coverage checks.
- [ ] A reviewed report records a measured maximum synchronization error
  against a pre-frozen threshold and attaches automated-test plus Field Session
  evidence.

# Validation Commands

```powershell
python -m unittest quality_tests.test_a0_unified_timestamp -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Required later: yes, for the four-source Field Session and measured
  alignment error.
- Board: unverified for A0-002 Gate in this implementation slice.
- Firmware commit/image: unavailable until the producer task is authorized and
  captured.
- Connection: unavailable until the Field Session is run.
- Evidence path/hash: unavailable.
- This static slice sends no hardware command and changes no firmware.

# Decisions

- Keep the existing `egolink.p0.v1` path stable; normalize into an additive
  offline lineage record first.
- Use nanoseconds in the A0 time-lineage contract while preserving each raw
  source value and unit. Existing legacy millisecond fields remain unchanged.
- Treat receive-only LTE/GNSS records and current Camera absence as honest
  unavailable evidence, not as validation failure by themselves.
- Report structural `field_eligible` separately from `gate_status`; the latter
  remains `unverified` until real evidence and a threshold are reviewed.
- Record Grok Builder CLI's independent test-matrix contribution in Git commit
  metadata; Codex independently owns and verifies the implementation.

# Completion Evidence

- Changed files: the paths in `allowed_paths` for this task only.
- Focused static result: 22/22 tests pass.
- Full repository result: 730/730 tests pass; `context_lint` and
  `git diff --check` pass.
- Hardware result: unavailable; no hardware action performed.
- Gate result: A0-002 remains active and A-R0 remains 0/8.
- Remaining risks: current raw GNSS/LTE lack complete device-clock lineage,
  Camera lacks structured capture timing, no real four-source session exists,
  and no acceptance threshold has been frozen.
