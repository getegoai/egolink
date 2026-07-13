---
document_status: authoritative
last_verified: 2026-07-13
verified_by: codex
---

# EgoLink V1 Product Plan

Authoritative V1 sequencing per ADR-0002
(`docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md`). V1 ships
a reliable locator base **plus the product's core differentiator: on-device
AI companion capability** (real-time interaction, proactive AI service), with
an edge-cloud hybrid intelligence split and a data flywheel that keeps
improving the models after launch.

Near-term engineering gates (R2.x/R3.x) remain in
`docs/current/ROADMAP_EGOLINK_P0.md` and feed milestone V1-M1 below.

Hardware update: ADR-0005 (2026-07-12) freezes V1 Pro around nRF54LM20B,
Air780EGH, QMI8658A, and T5838. Platform comparison remains historical input;
EVT schematic, sourcing, measured power and validation are still open work.
`docs/product/V1_PRO_FORM_FACTOR_BASELINE.md` additionally freezes the final
wrist-worn envelope before schematic capture so EVT starts at product size.
ADR-0006 (2026-07-13) revises the product peripherals without reopening that
platform: data-first guardian communication, nominal 900 mAh battery,
QMI8658A/T5838/MAX30101/MAX30208/BMP390 sensing, a 1.3-inch monochrome OLED,
and an IP68-oriented USB-C enclosure.

## 1. V1 Feature Set (in scope)

| # | Feature | Base already built | Remaining work |
|---|---|---|---|
| 1 | Real-time location: GNSS primary; cell as area-level assist (never cell-only coordinates); Wi-Fi known-place labels | EALE-P0 design, `location_observation` contract, KR-003/KR-004 | Outdoor GNSS acceptance (FIELD-003), belief rendering for guardians |
| 2 | SOS: button -> event -> VPS -> guardian notification | Event loop, command ACK, store-forward (KR-007) | Notification channel (push/SMS decision), guardian UI |
| 3 | History track + geofence enter/exit alerts | Location memory table (LOC-003) | Track storage/query API, geofence engine on VPS, alert rules |
| 4 | Device health: battery %, low-battery / power-off / removal alerts, heartbeat | Heartbeat + observability envelope (OBS-001..004) | Real power telemetry (PWR-001), alert thresholds |
| 5 | **On-device AI companion (core differentiator)**: motion anomaly candidate detection on the wearable (MotionNet), real-time confirmation/interaction loop (display/touch/audio), proactive check-in behavior; degrades gracefully without LTE | M0 contracts + RuleRouter baseline, DEMO-001 AMOLED/IMU confirmation loop, IMU capture chain (TIMU-009 series) | M1 data foundation (M1-002/005/006), formal IMU acceptance, MotionNet v0.1, model footprint assessment, interaction loop hardening, mic decision |
| 6 | Cloud AI services over LTE: heavier reasoning, language-level companion functions, fleet learning | VPS Message Hub in production, raw-frame ingest (SERVER-002) | Companion service design (V1-M3), model registry/update path |
| 7 | Explainable location confidence shown to guardians ("why we believe TA is here") | EALE-P0 confidence buckets + evidence refs | Human-readable rendering (WEB-003) |
| 8 | Data flywheel: consent + privacy classes, session ingest, confirmation-derived labels, retrain-and-ship loop (server update + device OTA) | M0 contracts, DATA-001 export, DATA-002 pipeline spec, DATA-003 candidate store, DATA-004 control-plane visibility, DATA-005 review queue, TRAIN-001 handoff manifest, DATA-006 post-run pipeline runner, TRAIN-002 experiment registry, DATA-007 experiment visibility, DATA-009 synthetic dry-run, TRAIN-003 runner preflight, DATA-010 runner-preflight visibility, TRAIN-004 feature manifest export, DATA-011 feature-manifest visibility, TRAIN-005 runner dry-run, DATA-012 runner dry-run visibility, TRAIN-006 synthetic baseline eval, DATA-013 baseline-eval visibility, DATA-014 post-run training-chain collector, TRAIN-007 training handoff bundle, DATA-015 handoff visibility, DATA-016 post-run handoff collector, TRAIN-008 training job plan, DATA-017 job visibility, DATA-018 post-run job-plan collector | M1 recorder/labeling/collection implementation, real training runner integration, model registry, OTA model path |

## 2. V1 Non-Goals

- No camera-based features (privacy + power; hardware capability retained) —
  TBD(founder) if the interaction design requires it.
- No ordinary PSTN dialer or public incoming-call UI. V1 uses data messages,
  voice messages and retains hardware for later guardian-authorized IP audio.
- No overseas compliance; China market only.
- No unmeasured safety claims: fall detection and proactive alerts ship
  labeled experimental until false-positive rates are measured on real data
  (non-claim evidence rules stay in force).
- Whether the AI learning progress is user-visible is a product presentation
  choice, TBD(founder).

## 3. Milestones

### V1-M1 Reliability Closeout (extends R3.0-R3.2)

The foundation carrying the AI track. Exit criteria:

- Device runs unattended on battery >= 24h with power curve exported via VPS
  (PWR-001); 48h target measured, not claimed.
- Outdoor GNSS acceptance protocol executed with recorded fix rate, TTFF, and
  error radius at reference points (FIELD-003).
- LTE long-run/reconnect gate (R3.0) passed.
- VPS hardened as production: monitoring, backup+restore test, log rotation,
  token rotation runbook (OPS-001).
- **FT-1 (first wearable field-test build)** assembled: battery + mounting +
  SOS key mapping; doubles as the M1 data-collection vehicle.

### V1-M2 Guardian-Facing MVP

Exit criteria:

- Guardian web view: live location + confidence, history track, geofence
  alerts, SOS notification end-to-end (WEB-003 wave).
- A non-developer family member completes setup->daily use->SOS drill without
  developer help.

### V1-M3 On-Device AI Track (starts alongside M1; the critical path)

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

- ADR-0005/ADR-0006-approved V1 Pro MCU, cellular, sensor, audio, display,
  storage and power-path baseline; unresolved cost, size, certification and measured
  acceptance gates remain controlled by
  `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`.
- Air780EGH and nRF54LM20B development hardware acquired through authorized
  channels; T5838 and ES8311 microphone/audio paths bench-validated.
- EVT BOM frozen.

### V1-M5 EVT -> DVT -> Certification -> Pilot Production

Defined after V1-M4 freeze; includes enclosure/mounting GNSS gate (R3.2)
re-run and on-device model acceptance re-run on EVT hardware.

### Post-Launch Track

- Flywheel retraining cadence; model updates via server + device OTA.
- Companion capability expansion (richer proactive services) on measured
  false-positive/latency budgets.

## 4. Task Backlog Mapping

| Wave | Task | Milestone | Status |
|---|---|---|---|
| 1 | ENG-007 AutoDev deprecation + Director workflow adoption | governance | done (2026-07-03) |
| 1 | OPS-001 VPS production hardening | V1-M1 | done (2026-07-03) |
| 1 | PWR-001 power telemetry + 24h battery baseline | V1-M1 | active |
| 1 | PWR-002 low-power location state-machine decision | V1-M1 | done (2026-07-03) |
| 1 | FIELD-003 outdoor GNSS acceptance | V1-M1 | active |
| 1 | PRIVACY-001 product demo privacy/data boundary gate | V1-M3 | done (2026-07-03) |
| 1 | PROD-001 mass-production requirements (incl. AI compute criteria) | V1-M4 | core platform selected by ADR-0005, peripherals revised by ADR-0006; schematic/supplier/measurement gates active |
| 2 | STAB-002 LTE long-run/reconnect gate (R3.0) | V1-M1 | planned |
| 2 | FT-1 assembly: SOS key mapping + mounting + release gate | V1-M1 | planned |
| 2 | M1-002 on-device session recorder | V1-M3 | planned |
| 2 | MODEL-001 model footprint assessment (ESP32-S3 first) | V1-M3 | paused for D1 (protocol baseline 2026-07-04; measurements pending) |
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

## 5. Operating Notes

- Existing ESP32-S3 + SIM7670G boards remain the current evidence and data
  vehicle while the ADR-0005/ADR-0006 V1 Pro target is brought up. New production
  firmware work targets nRF54LM20B + Air780EGH without invalidating prior
  engineering evidence.
- Every milestone exit produces a KR manifest (existing KR mechanism).
- Task execution follows `docs/development/DIRECTOR_WORKFLOW.md`.
