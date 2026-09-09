---
id: FIELD-020
title: P0-LOC representative field dataset
status: active
priority: critical
lane: A
execution_state: queued
depends_on:
  - LOC-021
  - P0-CONVERGENCE-20260905
serves_gate: P0-LOC
serves_milestone: single_4g_board_camera_field
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-09

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
  - docs/development/FIELD_TEST.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md
  - docs/tasks/active/P0-CONVERGENCE-20260905.md

allowed_paths:
  - docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md

out_of_scope:
  - flashing or sending commands without explicit operator intent
  - training models, unconsented/unbounded/public raw media or hiding failed observations
  - duplicating FT-001B/FIELD-003/PWR-001 tooling
---

# Goal

Run one representative-day campaign on the single identified 4G connectivity
node plus only its necessary Camera, existing external IMU, power source and
antennas. Cover outdoor, indoor, mall, underground, vehicle/bus, walking,
stationary and bag-carried conditions while reusing existing capture, accuracy,
session and power tools. AMOLED and PC forwarding are absent from runtime.

# Acceptance

- [ ] One immutable device/firmware/config identity and complete Session
      lineage cover all declared scenarios and attempted/failed observations.
- [ ] Report includes location availability/continuity, GNSS fix rate/TTFF,
      median/P90 reference error where ground truth exists, update latency,
      cell change, mobility evidence, no-fix/backoff, Wi-Fi/LTE route changes,
      disconnects, backlog recovery and power.
- [ ] The accepted pre-field candidate has already demonstrated ordinary
      observation upload over actual Wi-Fi and LTE plus a controlled route
      transition; this campaign retains the route and failure timeline rather
      than inheriting a historical Wi-Fi smoke as current evidence.
- [ ] The same firmware retains honest GNSS/Cell/IMU/power progress while
      Camera captures/uploads run; missing sources and resource growth remain
      explicit.
- [ ] Authorized manual and default-off timed stills retain source capture time
      and quality, trigger/config/command/photo identity, format/geometry/bytes,
      integrity and separate capture/save/upload results; they do not affect a
      P0 decision.
- [ ] Offline photos obey an explicit byte/count quota and ordinary-observation
      reserve. Restart uploads the same complete file/metadata without
      recapturing missed intervals; full, loss and corruption are reported.
- [ ] VPS/Web can query, preview and export the authorized session's current
      photos and associated observations without placing raw images in Git or
      public paths.
- [ ] Dataset remains training-disabled until consent/review explicitly allows.

# Hardware Boundary

The operator must authorize the exact build/flash/campaign, real Camera scene,
viewers, retention/deletion policy and evidence path.
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
after the single-board P0-CONVERGENCE Camera/LTE short run is accepted. Reuse
the existing field/session/accuracy/power tooling and prepare one immutable
device/firmware/config campaign manifest.
Before collection, amend allowed_paths with the reviewed private evidence path
and obtain explicit operator intent for the exact flash/run/campaign. Cover all
declared scenarios, retain attempts/failures and ground-truth limits, and keep
manual/timed stills consented, bounded, training-disabled and non-decisional.
Run every validation command
and the bounded field plan; return exact identity, metrics, evidence paths and
coverage/privacy/power risks. Do not authorize training or claim P0-LOC from
partial scenario evidence.
```
