---
id: L2-001
title: Continuous IMU mobility capture, persistent spool and replay
status: active
priority: medium
lane: A
execution_state: queued
depends_on:
  - LOC-021
requires_hardware: true
created: 2026-08-23
last_updated: 2026-08-23
serves_priority: L2 Intelligence

context:
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/PROTOCOL.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/IMU_CALIBRATION.md
  - docs/tasks/active/FT-001B_FIRST_REPLAYABLE_ASYNC_GNSS_IMU_SESSION.md

allowed_paths:
  - docs/tasks/active/L2-001_CONTINUOUS_IMU_MOBILITY_CAPTURE.md
  - docs/development/PROTOCOL.md
  - shared/contracts/
  - firmware/mqtt_heartbeat/
  - server/
  - pc_simulator/
  - scripts/
  - tools/
  - quality_tests/

out_of_scope:
  - changing or weakening the frozen exact-100 `egolink.imu_window.v1` primitive
  - blocking FT-001B, EXP-A1-000, FIELD-003 or another L1 release task
  - claiming bounded discrete windows are continuous acquisition
  - IMU dead reckoning, coordinate generation or a product positioning claim
  - training or deploying a learned mobility, fall or safety model
  - claiming product always-on power, endurance or production calibration
  - flashing, commands or other hardware control without explicit operator intent
---

# Goal

Create a separate, contract-first engineering path that captures 120-180
seconds of actual continuous real IMU samples, persists them locally before
upload, reconstructs the complete sample timeline after bounded export, and
replays it without hiding cadence faults, drops, reboot boundaries or network
gaps.

# Serves

L2 Intelligence priority. This task supplies mobility-model and sensor-policy data;
it is deliberately parallel to and non-blocking for the L1 first-launch path.

# Expected Result

One operator-approved run demonstrates:

```text
real QMI8658 acquisition
-> capture/event timestamp
-> bounded persistent local spool
-> upload with stable record identity
-> positive VPS acknowledgement
-> safe local acknowledgement/deletion
-> bounded complete export
-> sample-timeline Replay
```

Sampling continues independently of network upload. A slow or unavailable
uplink may delay delivery but must not be hidden as uninterrupted capture.

# Acceptance Criteria

- [ ] A reviewed capture contract is separate from, and does not mutate, the
  frozen `egolink.imu_window.v1` exact-100 command profile.
- [ ] One real device run records at least 120 seconds and targets 180 seconds
  of continuous QMI8658 acquisition in one boot and Session. The declared
  sample period, clock domain, calibration reference and mounting state are
  preserved.
- [ ] The report derives actual sampled duration from sample event time and
  reports cadence distribution, deadline misses, read failures, drops,
  discontinuities and maximum gap. Wall-clock span alone cannot pass.
- [ ] Network upload does not run in the sampling critical section or create
  an unreported acquisition gap. Capture blocks are written to a finite local
  persistent spool before transmission.
- [ ] Spool records have stable identities and retain original capture time,
  source sequence, boot and Session scope. Capacity, queued count, oldest age,
  retries, overflow and drop reasons are observable.
- [ ] A positive VPS acknowledgement is required before the only persisted
  local copy is safely acknowledged or deleted. A bounded reboot/recovery
  test proves retained records can resume upload without changing identity or
  event time.
- [ ] VPS ingest is idempotent for retried record identities, and a bounded,
  authenticated, complete, untruncated read-only export reconstructs all
  accepted samples and spool lineage.
- [ ] Replay rebuilds the sample timeline in capture-time order and reports
  coverage as `continuous`, `discontinuous` or `unavailable` from measured
  evidence. Server receive time is never promoted to capture time.
- [ ] Focused tests cover spool capacity/overflow, ACK deletion, reboot
  recovery, duplicate upload, missing/corrupt blocks, time lineage and Replay.
- [ ] Completion evidence remains engineering-only: it does not advance L1,
  claim IMU positioning, authorize training or prove product power behavior.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Hardware Validation

- Board: record the exact connectivity-node identity and IMU mounting used.
- Firmware commit/image: record the flashed descriptor and image hash; source
  code or a passing build is not capture evidence.
- Connection: independent power; network may be available, impaired or
  temporarily absent according to the reviewed bounded run plan.
- Expected output: private raw capture, spool/recovery report, bounded export
  and Replay artifacts outside Git.
- Evidence path: unavailable until an operator-approved real run completes.

# Decisions

- This task owns continuous IMU evidence formerly serialized ahead of
  FT-001B. FT-001B now uses at least three honest discrete exact-100 windows
  and does not wait for L2-001.
- Persistent spool is the smallest task-local implementation of ADR-0010
  Store-and-Forward for this high-rate stream. It must reuse existing raw-frame,
  boot identity, acknowledgement and reconnect behavior where practical; no
  broker or new general messaging infrastructure is introduced.
- The initial output is raw mobility evidence and Replay. Motion classes,
  learned encoders, energy-aware policy and any safety interpretation require
  later labelled-data and model tasks.

# Completion Evidence

- Changed files: pending implementation.
- Test result: pending implementation.
- Hardware result: pending explicit operator-approved run.
- Evidence path: unavailable until execution.
- Remaining risks: spool medium/endurance, sustained sampling power, reboot
  recovery, time alignment, mounting/calibration repeatability and production
  applicability remain unverified until measured.

# Builder Prompt

```text
Read docs/tasks/active/L2-001_CONTINUOUS_IMU_MOBILITY_CAPTURE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
listed in this packet's context. This is a non-blocking L2 packet; begin only
after LOC-021 is accepted and a frozen FT-001B image/commit boundary is
recorded. Obey allowed_paths and out_of_scope.
Create a separate continuous-capture contract and persistent spool without
changing egolink.imu_window.v1 or making IMU-position/training claims. Static
implementation and fixtures may proceed without hardware; flashing and real
commands require explicit operator intent. Run all validation commands and
return changed files, exact output, evidence paths and remaining risks. Do not
update STATUS or move this packet to done.
```
