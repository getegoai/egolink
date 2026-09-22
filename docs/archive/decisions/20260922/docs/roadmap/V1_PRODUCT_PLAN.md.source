---
document_status: authoritative
last_verified: 2026-08-23
verified_by: founder/codex
---

# EgoLink V1 Product Plan

## 2026-08-23 Productization Sprint 1 Rebase

[ADR-0011](../architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md)
sets the first-launch product loop to **Reliable Location + Ego Call + physical
SOS**. `Ego Call` uses LTE data, a controlled RTC service, and the bound
Guardian app. Native VoLTE is no longer a first-launch software release
blocker; A0 must still preserve and evaluate it through the independent
`G0V-VOLTE-RESERVE` hardware/migration Gate.

[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md)
freezes the exact capability Gates and implementation split:

| Gate | Current state |
|---|---|
| `P0-LOC` | `NOT_RUN` |
| `P0-CALL` | `NOT_RUN` |
| `P0-SOS` | `NOT_RUN` |

Device Location Engine v0/Sensor Policy v0 owns minimum offline operational
state; the server owns a versioned mirror, event-time replay/comparison and
richer derived fusion. `G0-EGOCALL` is retained only as a legacy evidence-family
name and maps to `P0-CALL`. `PROD-002` is a retained intake; its active successor
is `COMPLIANCE-010`.

Execution is no longer a single global wave. The four swimlanes in
[`FIRST_LAUNCH_EXECUTION.md`](../current/FIRST_LAUNCH_EXECUTION.md) run in
parallel with one integration-sized packet in progress per lane: L1
Location/field assets feeding `P0-LOC`; Ego Call/SOS;
reliability/security/power; and Product
A0/China readiness. A blocked lane does not stop the others. Shared contracts,
integration order, operator-controlled hardware actions, and evidence Gates
remain explicit.

This rebase does not relax the 48-hour representative guard-mode, persistent
critical-event, waterproof/acoustic, RF/body, privacy/security, certification,
or NPI ownership Gates. It changes first-launch capability priority and the
communications route, not product assurance.

## 2026-08-14 Product Baseline Rebase

ADR-0008 and `docs/product/EGO_MASTER_CONTEXT.md` replace the V1 Pro
watch/OLED/no-camera/data-only hardware and form assumptions with the
screenless modular EgoLink Core direction. ADR-0005/0006, the old form-factor
baseline, and the old EVT procurement list are historical only. No new
production BOM is frozen; named A0 components remain engineering candidates
except for ESP32-S3-PICO as the A0 starting point.

The sequencing below remains useful for reliable location, guardian UX,
on-device AI, privacy/data flywheel, and evidence gates. References to the old
V1 Pro hardware freeze or ordinary-call/camera non-goals are superseded and
must be re-planned under the Master Context and ADR-0008 before M4/M5 exit.

ADR-0002's local interaction, deterministic Safety Kernel, privacy boundary,
and model/data architecture remain active. Under ADR-0011, first launch ships
the reliable locator base plus Ego Call and SOS; `L2 Intelligence` proceeds in
parallel as best effort and advanced learned `L3 Awareness` evolves after
launch. The old L1-000/FT-001B/EXP-A1-000 chain is reusable non-blocking
evidence; learned-model readiness cannot delay an otherwise acceptable
P0-LOC/P0-CALL/P0-SOS launch unless a later accepted decision promotes a
measured capability.

Near-term engineering gates (R2.x/R3.x) remain in
`docs/current/ROADMAP_EGOLINK_P0.md` and feed milestone V1-M1 below.

Hardware update: ADR-0008 (2026-08-14) accepts the screenless modular EgoLink
Core product direction and a debuggable A0 before A1 product compression.
Specific modem, production MCU, IMU, audio, camera, storage, power, battery,
antenna, and enclosure decisions remain gated candidates or unknown. ADR-0011
partially supersedes ADR-0008's first-launch Native VoLTE/advanced-AI/camera
blocking clauses and ADR-0002's learned-model launch-blocker clauses; the
remaining product-direction decisions stay in force.

## 1. V1 Feature Set (in scope)

| # | Feature | Base already built | Remaining work |
|---|---|---|---|
| 1 | Resilient location: device Location Engine v0 uses GNSS as trusted calibrator, carries last-trusted/belief/uncertainty state offline and degrades honestly; server EALE provides derived replay/comparison, never cell-only or model-guessed coordinates | EALE-P0, proposed ADR-0007, `location_observation`, KR-003/KR-004 and the accepted LOC-020/POLICY-010/REPLAY-010 PC reference boundary are reusable engineering evidence | LOC-021 device/server/Guardian integration, FIELD-020 representative event-time campaign and `P0-LOC` acceptance |
| 2 | Ego Call: EgoLink <-> LTE data <-> controlled RTC service <-> bound Guardian app | Existing LTE transport, HTTPS Guardian surface and CALL-001 control/replay are reusable; CALL-010 has static unflashed images and CALL-020 has metadata-only trace tooling, while real audio/LTE media remain unverified | Operator-approved CALL-010 hardware loop -> real CALL-020 explicitly PC-bridged LTE PoC -> HW-022 integrated prototype -> CALL-021 embedded PC-free chain -> `P0-CALL` evidence |
| 3 | SOS: physical button -> durable local event -> parallel location escalation, guardian alert, and Ego Call -> guardian acknowledgement/replay | Deterministic Safety Kernel semantics, event loop, command ACK and an OUTBOX-010 host reference are reusable; physical GPIO, product persistence and the integrated loop remain unverified | OUTBOX device/server integration plus LOC-021 and CALL-021 -> physical/button UX, idempotent delivery, transport-vs-guardian ACK, bounded escalation, Guardian UI, offline/reboot drills -> `P0-SOS` evidence |
| 4 | History track + geofence enter/exit alerts | Bounded P0 VPS `location_memory` transition table (LOC-003), not a long-term product store | Device/EgoBase private-tier track storage, retention/deletion controls and geofence engine; VPS limited to authorized bounded transport/transition support |
| 5 | Device health: battery %, low-battery / power-off / removal alerts, heartbeat | Heartbeat + observability envelope (OBS-001..004) | Real power telemetry (PWR-001), alert thresholds |
| 6 | **Deterministic local safety/interaction baseline**: physical SOS, buttons/audio/haptics/status light, local feedback and graceful no-LTE degradation; proactive AI check-in is later growth | M0 contracts + RuleRouter baseline, historical DEMO-001 interaction evidence and IMU capture chain are reusable engineering assets | Launch-minimum Rule Policy/Safety Kernel and physical interaction hardening; parallel data/replay-first L2 MotionNet/GNSS reliability/mobility work and later advanced awareness do not block launch |
| 7 | Private-tier AI services: EgoBase is the intended user-controlled home for heavier reasoning, long-term personal memory, consented training and signed model delivery; the VPS remains a bounded transport/temporary-service tier | VPS Message Hub transport and raw-frame ingest (SERVER-002); no EgoBase implementation yet | EgoBase architecture and implementation, explicit temporary VPS enhancement boundary, private model registry/signing/update path |
| 8 | Explainable location confidence shown to guardians ("why we believe TA is here") | EALE-P0 confidence buckets + evidence refs | Human-readable rendering in Guardian experience and simultaneous Call/SOS context |
| 9 | Data flywheel: consent + privacy classes, session ingest, confirmation-derived labels, retrain-and-ship loop through the user-controlled private tier and signed device OTA | M0 contracts, DATA-001 export, DATA-002 pipeline spec, DATA-003 candidate store, DATA-004 control-plane visibility, DATA-005 review queue, TRAIN-001 handoff manifest, DATA-006 post-run pipeline runner, TRAIN-002 experiment registry, DATA-007 experiment visibility, DATA-009 synthetic dry-run, TRAIN-003 runner preflight, DATA-010 runner-preflight visibility, TRAIN-004 feature manifest export, DATA-011 feature-manifest visibility, TRAIN-005 runner dry-run, DATA-012 runner dry-run visibility, TRAIN-006 synthetic baseline eval, DATA-013 baseline-eval visibility, DATA-014 post-run training-chain collector, TRAIN-007 training handoff bundle, DATA-015 handoff visibility, DATA-016 post-run handoff collector, TRAIN-008 training job plan, DATA-017 job visibility, DATA-018 post-run job-plan collector | M1 recorder/labeling/collection implementation, EgoBase/private runner integration, model registry/signing, OTA model path |

## 2. V1 Non-Goals

- No continuous camera recording or default raw-image retention. Event-triggered
  camera evidence may proceed in parallel but is not a first-launch blocker;
  it remains unverified and privacy-gated.
- No screen or touch UI. First-launch voice is Ego Call between EgoLink and the
  bound Guardian app, not unrestricted public telephony and not a self-operated
  PSTN/SIP gateway. Native VoLTE remains unverified under
  `G0V-VOLTE-RESERVE`; no ordinary-phone or fallback claim is allowed until a
  later release Gate passes.
- No overseas compliance; China market only.
- No unmeasured safety claims: fall detection and proactive alerts ship
  labeled experimental until false-positive rates are measured on real data
  (non-claim evidence rules stay in force).
- Whether the AI learning progress is user-visible is a product presentation
  choice, TBD(founder).

## 3. First-Launch Parallel Execution

The current scheduler is the authoritative execution graph in
[`FIRST_LAUNCH_EXECUTION.md`](../current/FIRST_LAUNCH_EXECUTION.md). This table
summarizes the product-plan relationship; it does not replace active task
packets or advance evidence Gates.

| Lane | One current integration-sized WIP | Next bounded slices | Lane exit contribution |
|---|---|---|---|
| **A — P0-LOC / Field** | `LOC-021` device/server/Guardian integration is in progress after the accepted LOC/POLICY/REPLAY PC reference boundary | `FIELD-020`; L2 data/replay/estimators remain non-blocking | `P0-LOC`: representative event-time evidence, measured availability/accuracy/latency and honest GNSS-denied behavior |
| **B — Ego Call / SOS** | `CALL-010` remains operator-gated while `CALL-020` offline trace preparation advances without claiming media | Real `CALL-020` -> `HW-022` -> `CALL-021`; `SOS-010` starts once LOC-021, CALL-021 and OUTBOX-010 are accepted, independently of FIELD-020 | `P0-CALL` and `P0-SOS`: authorized product-path media plus durable physical-SOS composition; PoC evidence alone cannot pass either Gate |
| **C — Reliability / Security / Power** | `OUTBOX-010` host reference is in progress; product persistence and authenticated ACK remain | OUTBOX device/server integration + `OPS-004` authenticated ingress -> integrated `PWR-020` mode matrix and 48-hour guard run | Critical events survive bounded outage/reboot, ingress is protected, and representative power closes the cross-cutting release requirement |
| **D — Product A0 / China Readiness** | `HW-020` is completed only as an interface baseline; `HW-021` exact integrated design is in progress | `HW-022` physical integrated prototype; `COMPLIANCE-010` proceeds in parallel from HW-020 and converges at release review | Buildable and then measured A0 assets, named compliance assumptions and A0-to-A1 re-test matrix; `G0V-VOLTE-RESERVE` remains non-blocking |

Each lane has one WIP slot, but all four lanes may execute concurrently. A
hardware, supplier, or founder-decision wait blocks only its dependent lane.
Cross-lane contract changes have one owner and merge before consumers adopt
them; independent lanes must not create competing wire contracts.

The first integrated slices are:

1. carry device operational `location_belief` into Guardian and Call/SOS context;
2. route SOS/Call control events through authenticated TLS and the persistent
   priority outbox;
3. feed measured P0-LOC/Call/SOS duty cycles into A0 power, RF, audio, and thermal
   decisions;
4. run L2 estimators offline and then in Shadow Mode before they can influence
   Rule Policy v0.

The current integration and release convergence is:

```text
LOC-020 -> POLICY-010 -> REPLAY-010 -> LOC-021 -> FIELD-020 ----+
                                             |                  |
CALL-010 -> CALL-020 ------------------+      +-> SOS-010 -------+-> release
HW-020 -> HW-021 -> HW-022 ------------+-> CALL-021 --^
OUTBOX-010 -----------------------------------------^

HW-022 + LOC-021 + CALL-021 + SOS-010 -> PWR-020

FIELD-020 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020 + HW-022
    + COMPLIANCE-010 + acoustic/RF/water/security/privacy/NPI evidence
    -> P0-RELEASE-010
```

`HW-020 -> HW-021 -> HW-022` is the hardware path. `PWR-020` begins only on
the integrated dependency set named by its packet. `FIELD-020` and `SOS-010`
are parallel branches and neither waits for the other before the final review.

## 4. Milestone Exit Gates

M1-M4 below are evidence/exit families, not a serial permission chain. Work in
all four begins now. M5 still depends on reviewed A0 inputs and the applicable
product-assurance Gates.

### V1-M1 Reliability Closeout (extends R3.0-R3.2)

The foundation carrying the AI track. Exit criteria:

- PWR-001's development-board 24-hour baseline remains reusable input, but
  only integrated `PWR-020` can close the representative 48-hour guard target.
- FIELD-003 tooling/evidence remains reusable; `FIELD-020` owns the current
  representative P0-LOC campaign and its recorded fix rate, TTFF, accuracy and
  honest no-fix behavior.
- LTE long-run/reconnect gate (R3.0) passed.
- VPS hardened as production: monitoring, backup+restore test, log rotation,
  token rotation runbook (OPS-001).
- `HW-022` integrated prototype assembled with battery, mounting, audio and
  physical SOS path; split-board FT-1 evidence remains a development input,
  not representative-product acceptance.

### V1-M2 Guardian-Facing MVP

Exit criteria:

- `P0-CALL` (legacy `G0-EGOCALL`): device-to-guardian and
  guardian-to-device full-duplex calls,
  authorized call state, bounded weak-network recovery, one bound Guardian,
  and simultaneous location/battery/confidence context have
  replayable evidence. A PC/browser loop is an engineering slice, not final
  product-audio evidence. Multi-Guardian/contact escalation is later growth
  and cannot block the minimum P0 loop.
- Minimum Guardian experience: live location + confidence/age/uncertainty,
  call controls, SOS notification and acknowledgement end-to-end. History
  track and geofence UX may follow without blocking this Gate.
- Physical SOS is durably recorded before network delivery, composes location
  escalation and Ego Call without waiting for a fresh GNSS fix, and shows
  `pending`/`failed` honestly through outage, reboot, or RTC failure.
- GNSS-denied views distinguish an evidence-backed current/coarse result,
  stale last-known and `Unknown`, including source, age and uncertainty.
  Learned known-place/route prediction remains non-blocking L2 work.
- A non-developer family member completes setup -> daily location -> both call
  directions -> SOS drill without developer help.

### V1-M3 On-Device Intelligence Track (parallel L2/L3 path)

The deterministic Safety Kernel and Rule Policy v0 stay on the launch path.
The learned outputs below proceed in parallel and strengthen the product, but
under ADR-0012 they do not block an otherwise acceptable P0-LOC/Call/SOS launch
unless a later accepted decision promotes a measured capability.

Exit criteria:

- M1 data foundation complete: session recorder on device (M1-002), labeling
  loop (M1-005), collection protocol executed with real negative + controlled
  simulated samples (M1-006); FT-1 field runs feeding sessions.
- Formal IMU product acceptance passed (mounting orientation, FIFO/DRDY,
  calibration, power waveform — closing the TIMU-009C gap).
- MotionNet v0.1 trained and benchmarked against the statistical/threshold
  baseline; results recorded as engineering evidence.
- Model footprint assessment: RAM/flash/latency/power for MotionNet-class
  models measured on ESP32-S3 and estimated for candidate production MCUs;
  feeds PROD-001 MCU selection.
- On-device interaction loop (candidate -> local prompt -> user confirm ->
  event) running on the wearable node, with graceful no-LTE degradation.
- DATA-002 flywheel pipeline: sessions -> ingest -> training-candidate store
  with consent + privacy class on every record; confirmation-derived labels.

### V1-M4 Mass-Production Definition and Sourcing (long lead, start now)

Exit criteria:

- A0 architecture schematic/BOM/AVL issued from official candidate evidence,
  with each baseline/candidate/unknown status explicit and no inherited V1 Pro
  purchasing.
- `P0-CALL` traffic/audio requirements, ESP32-S3-PICO A0 and the core
  motion/audio/storage/power/RF paths bench-validated against applicable
  product requirements. `G0V-VOLTE-RESERVE` protects a V1.x/V2 migration path
  but is not a P0 release Gate; camera is only an optional compatibility
  interface unless a later accepted decision promotes it.
- A0 BOM frozen only after official documents, footprints, sourcing,
  deterministic Safety Kernel resource fit, power, RF, acoustic and privacy
  gates pass. Advanced learned-model/camera headroom remains measured growth
  evidence unless a later accepted ADR promotes it.

### V1-M5 EVT -> DVT -> Certification -> Pilot Production

Defined after V1-M4 freeze; includes enclosure/mounting GNSS gate (R3.2)
re-run, worn/bag occlusion acquisition and recovery tests, plus the applicable
LOC/CALL/SOS and product-assurance re-runs on representative hardware. Learned
hybrid-location and on-device model acceptance remain parallel/non-blocking
unless a later accepted decision explicitly promotes them.

### Post-Launch Track

- Flywheel retraining cadence; signed model updates from the user-controlled
  private tier through the bounded transport service to device OTA.
- Companion capability expansion (richer proactive services) on measured
  false-positive/latency budgets.

## 5. Task Backlog Mapping

`Now/A` through `Now/D` are the four current lane slots. The older numeric
waves below remain useful history/backlog grouping, but they no longer impose a
global serial order.

| Wave | Task | Milestone | Status |
|---|---|---|---|
| Done/A-ref | LOC-020/POLICY-010/REPLAY-010 PC reference boundary | `P0-LOC` | completed/accepted for transition; no hardware or Gate evidence and `P0-LOC` remains `NOT_RUN` |
| Now/A | LOC-021 device/Message Hub/Guardian integration | `P0-LOC` | in progress; host seam exists, device wire/runtime/persistence and representative evidence remain |
| Now/B | CALL-010 hardware loop + CALL-020 offline preparation | V1-M2 / `P0-CALL` | in progress; CALL-010 hardware run is operator-gated and real LTE media is `NOT_RUN` |
| Now/C | OUTBOX-010 persistent priority outbox | V1-M1 / `P0-SOS` reliability | in progress as a host reference; product NVS/server/ACK/brownout integration remains; OPS-004 is independently queued |
| Done/D-ref | HW-020 A0 interface baseline | V1-M4 / all three P0 Gates | completed/accepted for transition as interface baseline only; no exact design, built prototype or product-frozen BOM |
| Now/D | HW-021 exact integrated prototype design | V1-M4 / all three P0 Gates | in progress; HW-022 physical build remains queued and operator/procurement-gated |
| Next/A-L2 | L2-001 continuous IMU mobility capture, persistent spool and replay | V1-M3 L2 Intelligence | queued/non-blocking; starts after L1 releases shared source and an FT image boundary is frozen, but does not wait for or block FT field acceptance |
| Next/B | real CALL-020 + HW-022 -> CALL-021; LOC-021 + CALL-021 + OUTBOX-010 -> SOS-010 | V1-M2 / `P0-CALL` + `P0-SOS` | dependency-ordered; CALL-020 is explicitly PC-bridged and FIELD-020 does not block SOS |
| Next/C | OPS-004 + product OUTBOX integration -> PWR-020 | V1-M1 / cross-cutting assurance | OPS-004 and integrated power evidence are queued; PWR-001 remains development evidence only |
| Next/D | HW-022 integrated prototype + COMPLIANCE-010 | V1-M4 | HW-022 follows HW-021 and real CALL-020; compliance is independently queued after HW-020; PROD-002 is legacy intake only |
| Release | P0-RELEASE-010 | all three P0 Gates + product assurance | queued; FIELD-020 and SOS-010 meet here with OUTBOX-010, OPS-004, PWR-020, HW-022, COMPLIANCE-010 and acoustic/RF/water/security/privacy/NPI evidence; all P0 Gates remain `NOT_RUN` |
| 1 | ENG-007 AutoDev deprecation + Director workflow adoption | governance | done (2026-07-03) |
| 1 | OPS-001 VPS production hardening | V1-M1 | done (2026-07-03) |
| 1 | PWR-001 power telemetry + 24h battery baseline | V1-M1 | active |
| 1 | PWR-002 low-power location state-machine decision | V1-M1 | done (2026-07-03) |
| 1 | FIELD-003 outdoor GNSS acceptance | V1-M1 | active |
| 1 | LOC-006 GNSS-denied hybrid-location strategy and evaluation freeze | V1-M1/V1-M2 | active |
| 1 | PRIVACY-001 product demo privacy/data boundary gate | V1-M3 | done (2026-07-03) |
| 1 | PROD-001 mass-production requirements (incl. AI compute criteria) | V1-M4 | rebased by ADR-0012; general assurance gates active, new A0/production BOM not frozen |
| 2 | STAB-002 LTE long-run/reconnect gate (R3.0) | V1-M1 | planned |
| 2 | FT-1 assembly: SOS key mapping + mounting + release gate | V1-M1 | planned |
| 2 | M1-002 on-device session recorder | V1-M3 | planned |
| 2 | MODEL-001 model/codec footprint assessment (ESP32-S3 first) | V1-M3/V1-M4 | existing packet remains paused; measurements pending; re-scope a successor measurement packet into the parallel L2/Lane D path instead of waiting for D1 |
| 2 | DATA-002 data flywheel pipeline spec | V1-M3 | done (2026-07-04) |
| 2 | DATA-003 training candidate store baseline | V1-M3 | done (2026-07-04) |
| 2 | DATA-004 data flywheel control-plane visibility | V1-M3 | done (2026-07-04) |
| 2 | DATA-005 candidate review queue | V1-M3 | done (2026-07-04) |
| 2 | TRAIN-001 dataset/experiment handoff | V1-M3 | done (2026-07-04) |
| 2 | DATA-006 post-run data-flywheel pipeline runner | V1-M3 | done (2026-07-05) |
| 2 | TRAIN-002 training experiment registry | V1-M3 | done (2026-07-05) |
| 2 | DATA-007 training experiment dashboard visibility | V1-M3 | done (2026-07-05) |
| 2 | DATA-009 synthetic scenario generator | V1-M3 | done (2026-07-05) |
| 2 | TRAIN-003 training-run preflight | V1-M3 | done (2026-07-05) |
| 2 | DATA-010 training-run preflight visibility | V1-M3 | done (2026-07-05) |
| 2 | TRAIN-004 training feature manifest export | V1-M3 | done (2026-07-05) |
| 2 | DATA-011 training feature manifest visibility | V1-M3 | done (2026-07-05) |
| 2 | TRAIN-005 local training runner dry-run | V1-M3 | done (2026-07-05) |
| 2 | DATA-012 training runner dry-run visibility | V1-M3 | done (2026-07-05) |
| 2 | TRAIN-006 synthetic baseline evaluation | V1-M3 | done (2026-07-06) |
| 2 | DATA-013 training baseline eval visibility | V1-M3 | done (2026-07-06) |
| 2 | DATA-014 post-run training-chain collector | V1-M3 | done (2026-07-06) |
| 2 | TRAIN-007 training handoff bundle | V1-M3 | done (2026-07-06) |
| 2 | DATA-015 training handoff visibility | V1-M3 | done (2026-07-06) |
| 2 | DATA-016 post-run handoff collector | V1-M3 | done (2026-07-06) |
| 2 | TRAIN-008 training job plan dry-run | V1-M3 | done (2026-07-06) |
| 2 | DATA-017 training job visibility | V1-M3 | done (2026-07-06) |
| 2 | DATA-018 post-run job-plan collector | V1-M3 | done (2026-07-06) |
| 2 | WEB-003 guardian dashboard MVP (live location/track/SOS) | V1-M2 | planned |
| 3 | M1-005 labeling loop, M1-006 collection protocol runs | V1-M3 | planned |
| 3 | MotionNet v0.1 training + on-device PoC | V1-M3 | planned |
| 3 | FW-004 firmware capability truth source in `hello` | V1-M3 | planned |
| 3 | SRV-00x geofence engine + notification channel | V1-M2 | planned |
| 3 | LOC-007 personal place/route memory | V1-M2 | planned after LOC-006 evidence |
| 3 | Post-P0 source-reliability research | V1-M3+ | requires labelled real sessions and a later founder-reviewed ADR/task |
| 3 | PWR-003 additive scheduler telemetry and measured rule budgets | V1-M1 | planned after PWR-001/FIELD-003 evidence, per ADR-0003 |

## 6. Operating Notes

- Existing ESP32-S3 + SIM7670G boards remain the current evidence and data
  vehicle while the ADR-0008 EgoLink Core product path is designed. New product
  firmware starts with the ESP32-S3-PICO A0 engineering baseline without
  invalidating prior evidence; the final MCU and modem remain open gates.
- ESP32-S3 Wi-Fi remains an engineering evidence path. Production 2.4 GHz and
  Wi-Fi/BLE topology must be frozen with the A0/A1 RF architecture rather than
  inherited from the superseded V1 Pro route. Product location acceptance
  cannot depend on Wi-Fi until a capability task and accepted decision add it.
- Every milestone exit produces a KR manifest (existing KR mechanism).
- Task execution follows `docs/development/DIRECTOR_WORKFLOW.md`: one bounded
  WIP packet per lane, up to four independent lanes in parallel, with explicit
  contract ownership and integration order.
