---
id: FT-001B
title: First replayable asynchronous L1 GNSS and IMU field session
status: active
priority: critical
requires_hardware: true
created: 2026-08-18
last_updated: 2026-08-23
serves_priority: L1 Location

context:
  - docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/development/IMU_CALIBRATION.md
  - docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/tasks/active/L2-001_CONTINUOUS_IMU_MOBILITY_CAPTURE.md

allowed_paths:
  - docs/tasks/active/FT-001B_FIRST_REPLAYABLE_ASYNC_GNSS_IMU_SESSION.md
  - tools/pack_ft001b_session.py
  - pc_simulator/field_session_replay.py
  - scripts/replay_field_session.py
  - quality_tests/test_field_session_pack.py
  - quality_tests/test_ft001b_session_pack.py

out_of_scope:
  - requiring simultaneous or hard-synchronized sensor capture
  - requiring 120-180 seconds of continuous IMU capture for FT-001B completion
  - claiming discrete bounded IMU windows are continuous acquisition
  - IMU dead reckoning, motion-to-position inference or an IMU position baseline
  - requiring LTE, Camera or manual events for FT-001B completion
  - firmware refactoring for Camera, production IMU calibration or new AI models
  - expanding the public schema or Control Plane
  - claiming durable Store-and-Forward before reboot/recovery evidence exists
  - marking A0-001/A0-002/A0-003 or A-R0 passed from this engineering Session
  - flashing, commands or other hardware control without explicit operator intent
---

# Problem

The repository has real GNSS and bounded high-rate IMU acquisition paths but
does not yet have one real, replayable asynchronous L1 Session with enough
honest event-time evidence for a 60-second GNSS blackout smoke. The superseded
four-source task made Camera, manual events and simultaneous synchronization
unnecessary blockers. Continuous high-rate IMU collection is useful L2 work,
but it is not required to evaluate the first last-known-position baseline.

# Expected Result

Capture and seal one real outdoor GNSS+IMU Session with one continuous GNSS
trajectory and at least three separate real `100 x 50 ms` IMU windows in the
same device boot and Session. Reconstruct every usable observation from its
capture/event-time evidence, preserve every IMU inter-window gap, regenerate
the GNSS trajectory, and run exactly one `EXP-A1-000` 60-second last-known-
position blackout. LTE is included when naturally observed. Camera and manual
events are optional.

# Acceptance Criteria

- [ ] One outdoor run records a genuine continuous GNSS trajectory with valid
  fixes, one device identity, one boot scope and one `FS-...` Session identity.
- [ ] The same boot and Session contain at least three separately authorized,
  real, non-mock IMU windows. Each window uses the frozen
  `egolink.imu_window.v1` shape of exactly 100 samples at 50 ms; all chunks and
  manifests are complete and retain their capture-command lineage.
- [ ] Sampled duration, cadence, drops, discontinuities and every inter-window
  gap are measured and reported. The package and report explicitly state that
  these discrete windows are not continuous IMU capture and do not satisfy the
  separate L2 continuous-mobility evidence task.
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
- [ ] `EXP-A1-000` masks exactly one 60-second middle interval and evaluates
  only the last-known-position baseline. It emits a trajectory,
  error-vs-time output, endpoint error and machine-readable result bound to
  Session/input/code hashes.
- [ ] The experiment reports `IMU position baseline = unavailable`; discrete
  motion windows are not converted into coordinates. LTE coarse location is
  retained as source evidence when naturally present but is not evaluated as
  a position baseline in this first L1 smoke. No temporary position algorithm
  is invented.
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
  last-known-only `EXP-A1-000` reports outside Git. The report includes all
  IMU window gaps and the explicit continuous-capture non-claim.
- Evidence path: unavailable until the real run completes.

# Decisions

- This task implements the current milestone in ADR-0010 and supersedes
  `FIELD-AI-001` as the active first-session packet.
- Continuous 120-180 second IMU acquisition no longer precedes this task. It
  is the parallel `L2-001` capture -> persistent spool -> upload/replay task.
  FT-001B neither advances nor waits for that L2-001 evidence.
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
  trustworthy common UTC mapping; continuous IMU mobility capture, durable
  Store-and-Forward and automatic Camera capture are not currently verified.
