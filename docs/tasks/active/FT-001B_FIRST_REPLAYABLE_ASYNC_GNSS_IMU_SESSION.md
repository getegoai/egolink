---
id: FT-001B
title: First replayable asynchronous GNSS and IMU field session
status: active
priority: critical
requires_hardware: true
created: 2026-08-18
last_updated: 2026-08-18

context:
  - docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/development/IMU_CALIBRATION.md
  - docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md

allowed_paths:
  - docs/tasks/active/FT-001B_FIRST_REPLAYABLE_ASYNC_GNSS_IMU_SESSION.md
  - tools/pack_ft001b_session.py
  - pc_simulator/field_session_replay.py
  - scripts/replay_field_session.py
  - quality_tests/test_field_session_pack.py
  - quality_tests/test_ft001b_session_pack.py

out_of_scope:
  - requiring simultaneous or hard-synchronized sensor capture
  - requiring LTE, Camera or manual events for FT-001B completion
  - firmware refactoring for Camera, production IMU calibration or new AI models
  - expanding the public schema or Control Plane
  - claiming durable Store-and-Forward before reboot/recovery evidence exists
  - marking A0-001/A0-002/A0-003 or A-R0 passed from this engineering Session
  - flashing, commands or other hardware control without explicit operator intent
---

# Problem

The repository has real GNSS and bounded high-rate IMU acquisition paths but
does not yet have one real, replayable asynchronous Session with enough data
for a 60-second GNSS blackout smoke. The superseded four-source task made
Camera, manual events and simultaneous synchronization unnecessary blockers.

# Expected Result

Capture and seal one real outdoor GNSS+IMU Session, reconstruct every usable
observation from its capture/event-time evidence, regenerate the GNSS
trajectory, and run exactly one `EXP-A1-000` 60-second blackout. LTE is included
when naturally observed. Camera and manual events are optional.

# Acceptance Criteria

- [ ] One outdoor run records a genuine continuous GNSS trajectory with valid
  fixes, one device identity, one boot scope and one `FS-...` Session identity.
- [ ] Real, non-mock IMU samples provide at least 120 seconds of actual
  continuous capture. Merely placing sparse windows across a 120-second wall
  span does not pass; sampled duration, every inter-window gap, cadence, drops
  and discontinuities are measured rather than hidden.
- [ ] GNSS and IMU raw evidence reaches the VPS and is returned by bounded,
  authenticated, complete and untruncated read-only exports.
- [ ] Each normalized observation preserves capture/event time and its source,
  boot, sequence, receive/ingest time, mapping provenance and uncertainty.
  Receive time is never promoted to capture time.
- [ ] Packer creates one valid, complete and sealed package with raw plus
  calibrated IMU and the actual calibration reference. Stricter A-R0
  `field_eligible=false` is allowed and must remain visible. LTE is optional:
  an export with no LTE observations must still package successfully and must
  report LTE as unavailable rather than synthesize a captured stream.
- [ ] A focused test imports `tools.pack_ft001b_session` and exercises a full
  fixture pack through validation and Replay; `py_compile` or tests of only the
  older four-source adapter are not sufficient.
- [ ] Replay rebuilds the GNSS trajectory and reports cross-source ordering as
  available, ambiguous or unavailable from actual time evidence.
- [ ] `EXP-A1-000` masks exactly one 60-second middle interval and emits a
  trajectory, error-vs-time output, endpoint error and machine-readable result
  bound to Session/input/code hashes.
- [ ] Last-known-position is evaluated. LTE coarse location and IMU position
  baselines are `unavailable` unless their already-validated prerequisites are
  present; no temporary position algorithm is invented.
- [ ] Camera absence, LTE absence and missing manual events are reported but do
  not fail this task. When Camera is not used, its sensor policy is `disabled`
  and its contract stream is `not_requested`, never `captured`. No A0 or A-R0
  Gate is advanced from code, fixture or this engineering smoke alone.

# Validation Commands

```powershell
python -m py_compile tools/pack_ft001b_session.py quality_tests/test_ft001b_session_pack.py
python -m unittest quality_tests.test_ft001b_session_pack -v
python -m unittest quality_tests.test_field_session_pack -v
python -m unittest quality_tests.test_field_session_replay -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Hardware Validation

- Board: `connectivity-node-001` / `ego-link-r1-connectivity-001`; record the
  exact identity seen in the Session.
- Firmware commit/image: record the currently flashed FW-007 identity before
  capture; do not infer it from source alone.
- Connection: independent power, LTE or observed Wi-Fi failover to VPS Message
  Hub; hardware commands require explicit operator intent.
- Expected output: one private sealed Session package plus Replay and
  `EXP-A1-000` reports outside Git.
- Evidence path: unavailable until the real run completes.

# Decisions

- This task implements the current milestone in ADR-0010 and supersedes
  `FIELD-AI-001` as the active first-session packet.
- Store-and-Forward is an accepted architecture requirement, but its current
  durable implementation/evidence is unavailable. A network-stable FT-001B run
  may proceed; any outage gap remains an observed limitation rather than being
  repaired with server receive time.
- No new unattended capture/export runner is accepted by this packet. Use only
  an already reviewed bounded path, and obtain explicit operator intent before
  sending any device command.
- Camera automatic capture is optional here. The separate Camera smoke app is
  not evidence that the currently flashed product-path firmware captures or
  uploads JPEGs automatically.

# Completion Evidence

- Changed files: unavailable until execution.
- Test result: unavailable until execution.
- Hardware result: unavailable until execution.
- Remaining risks: current raw LTE is receive-time-only; GNSS/IMU may lack a
  trustworthy common UTC mapping; durable Store-and-Forward and automatic
  Camera capture are not currently verified.
