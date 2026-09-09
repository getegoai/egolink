---
document_status: accepted_decision
decision_updated: 2026-09-09
reviewed_at: 2026-09-09
authority_basis: founder_directed_single_board_camera_milestone
implementation_status: in_progress
---

# ADR-0015: Single-4G-Board Field and Camera Collection Milestone

- Status: accepted
- Date: 2026-09-09
- Decision owner: founder
- Scope: current A-line evidence vehicle, Camera collection closure, and temporary lane scheduling

## Context

The current collector has real Wi-Fi bench evidence for asynchronous GNSS,
Cell, external QMI8658 IMU, available power and durable backlog behavior. A
historical test on the same identified connectivity node also initialized an
OV5640 and captured three QVGA JPEG frames. Those separate runs do not prove
that Camera, Location, IMU, storage and LTE coexist in one firmware or one
independently powered field unit.

The prior execution plan advanced CALL beside Location and retained a dual-
development-board evidence architecture. The founder has now narrowed the
immediate milestone: finish one portable, independently operating 4G-board
collection system, including a real still-image path, before FIELD-020. The
AMOLED board remains useful for later Ego Call bench research but is not part
of this A-line run.

This is an execution and evidence-architecture decision. It does not remove a
sellable-product capability Gate or turn the development board or Camera into
a production-frozen product.

## Decision

### 1. Current A-line evidence vehicle

The current A-line field vehicle is one identified Waveshare ESP32-S3-
SIM7670G-4G connectivity node with only the necessary attached Camera, existing
external IMU, power source and LTE/GNSS antennas. It must operate without an
AMOLED node, board-to-board bridge or PC runtime/forwarding dependency.

The AMOLED node does not participate in A-line power, acquisition, forwarding,
storage or acceptance. Existing AMOLED, CALL and dual-board code and evidence
remain valid historical engineering assets and are not deleted.

### 2. Current milestone outcome

The current implementation order is:

```text
exact single-board audit
-> combined Location/raw-collection/Camera firmware
-> real Wi-Fi and LTE ordinary-observation upload + controlled route transition
-> authorized Web one-shot capture over real LTE
-> bounded local timed capture and persistent recovery
-> independently powered joint short carry test
-> FIELD-020 representative day
```

Camera is a required delivery for this milestone, not a fourth P0 product Gate.
`P0-LOC`, `P0-CALL` and `P0-SOS` retain their accepted definitions and all
remain evidence-bound. Camera failure cannot create, improve, veto or delay a
Location or SOS decision.

### 3. Acquisition and time

GNSS, Cell/LTE, IMU, power and Camera remain independent asynchronous sources
under ADR-0010. Every source retains its actual capture/event time, clock
quality, identity and failure state. GNSS acquisition or no-fix does not block
an otherwise available Camera or sensor observation.

A photo may reference a last-trusted location only with that location's source,
capture time, age and quality. Historical coordinates are never relabelled as
the current position.

### 4. Camera control and truthful states

The existing authenticated command/ACK path is reused. No parallel control bus
is introduced. The two permitted entry points are:

- one authorized, expiring Web capture request; and
- a default-off device-local timed configuration with an interval and bounded
  session end condition.

Both use one capture implementation. Browser disconnect does not cancel an
already delivered local timed session. A configuration not yet received by the
device remains pending. Restart continuation or stop behavior must be explicit;
missed intervals are not replayed as a burst of replacement captures.

Command accepted, device received, capture attempted, JPEG saved, upload
pending, VPS verified/persisted and Web-visible are separate facts. A stable
command ID and observation/photo ID bind retries. Duplicate delivery must not
cause unbounded recapture. An ambiguous power-loss window remains ambiguous
rather than being reported as exactly-once execution.

### 5. Binary persistence and recovery

JPEG bytes are stored separately from lightweight observation metadata and
ordinary telemetry. A successful local photo requires a complete file,
metadata and integrity value on an actually persistent medium; RAM is not
restart recovery. The VPS acknowledges upload completion only after verifying
and durably storing the complete file and metadata.

Photo storage has an explicit byte/count quota, bounded concurrency, full-
capacity behavior and loss/corruption accounting. It cannot consume the entire
ordinary observation reserve. Restart recovery uploads the same complete file
with the same source time and photo ID; it does not recapture the past. Partial
or corrupt files never become successful photos.

Capture and upload are bounded so Location, modem ownership and sensor work can
continue. Capture completion or failure releases the acquired software
resources. Standby, PWDN and physical power-off are reported according to the
actual board capability and are not treated as synonyms.

The same candidate must report ordinary observations over both an actual Wi-Fi
route and an actual LTE route. A controlled Wi-Fi/LTE transition retains source
event time and stable record identity, never deletes a pending item without its
exact durable ACK, and exposes any duplicate, loss, retry or unavailable route.
The first Web one-shot photo proof still uses real LTE; historical Wi-Fi bench
evidence cannot substitute for this joint-candidate route test.

### 6. Privacy and field boundary

Timed capture is off by default. Raw image persistence and viewing require a
named authorized test session, permitted environment, access control, retention
limit and deletion path under the existing Product Demo Privacy Boundary.
Images stay out of public paths, ordinary Git commits and unrelated logs;
`training_allowed=false` remains the default. This milestone does not authorize
continuous video, audio recording, visual inference or public sharing.

### 7. Lane scheduling

CALL-020 and CALL-021 are paused for separate research. Full physical SOS is
also outside this A-line milestone and SOS-010 is paused without deleting its
implementation or evidence. CALL and SOS remain mandatory for a sellable P0.

HW-021 and COMPLIANCE-010 continue independently. HW-021 must accept Camera
interface/pin, power-control, storage/upload budget, lens/FOV/orientation,
optical-window and sealing facts as conditional design inputs. The development
OV5640 is not thereby selected for production.

## Supersession

For the current engineering milestone only, this ADR replaces ADR-0014's
Location-plus-parallel-CALL execution order and its immediate physical-SOS
follow-up. It refines ADR-0012 section 5, section 7 and the Immediate Task Chain
only as scheduling statements; it does not alter the three sellable P0 Gates.

It refines ADR-0010's Camera-optional current experiment profile for this newer
milestone while retaining asynchronous acquisition, event-time lineage and
bounded persistent Store-and-Forward. It does not retroactively change the
scope or evidence result of FT-001B.

ADR-0011's first-launch product, privacy, product assurance and eventual CALL/
SOS obligations remain accepted. ADR-0012's prohibition on Camera-to-AI
decisions and visual understanding remains accepted.

## Evidence boundary

This decision creates no new build, flash, boot, SIM, LTE, Camera, persistence,
VPS, Web or field evidence. The 2026-06-23 OV5640 capture and 2026-09-06
collector run remain separate historical observations until current hardware,
pin/bus ownership, persistent storage and one combined candidate are verified.
No current combined-candidate Wi-Fi/LTE transition evidence exists either.

No P0 Gate advances from this ADR. Hardware control, SIM traffic, deployment
and real-scene image capture continue to require the applicable bounded
operator and privacy scope.

## Related documents

- [North Star](../../product/NORTH_STAR.md)
- [P0 Scope](../../product/P0_SCOPE.md)
- [Current execution](../../current/FIRST_LAUNCH_EXECUTION.md)
- [A-line execution context](../../current/EGO_LINK_AI_CURRENT_CONTEXT.md)
- [Current convergence packet](../../tasks/active/P0-CONVERGENCE-20260905.md)
- [FIELD-020](../../tasks/active/FIELD-020_L1_FIELD_DATASET.md)
- [Historical TCAM-001 evidence](../../hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md)
