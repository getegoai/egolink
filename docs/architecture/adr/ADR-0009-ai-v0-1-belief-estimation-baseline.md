---
document_status: authoritative
last_verified: 2026-08-16
verified_by: codex
owner: founder
---

# ADR-0009: Freeze the Ego Link AI v0.1 Belief-Estimation Baseline

- Status: accepted
- Date: 2026-08-16
- Decision owner: founder
- Scope: A-line AI architecture and sequencing; no current-board capability claim

## Context

The 4G-board-to-LTE-to-VPS-to-map walking skeleton now produces useful field
evidence, but map visibility is not location-accuracy or AI evidence. The next
milestone is a replayable and synchronized real Field Session whose
Location Belief degradation can be measured when a source is removed.

Two failure modes must be avoided: spending indefinitely on infrastructure
without shaping the AI system, and training increasingly complex models before
calibration, time alignment, validation and repeatable evaluation exist.

## Decision

### Two parallel layers

- A0 Data & Evaluation Platform is the execution mainline.
- A1/A2 architecture, data contracts and baseline design proceed in parallel.
- Model training and benchmark claims require the named A0 data/evaluation
  prerequisites and real eligible sessions; design work alone never advances
  an A-R0 Gate.

### AI v0.1 information flow

```text
Sensors
  GNSS / LTE / IMU / event-triggered Camera
        |
Sensor Quality
        |
Modality Estimators
        |
Probabilistic Fusion
        |
Temporal Memory
        |
Location Belief / State Belief / Safety Belief
        |
Active Sensing
        |
Product Action
```

The existing GNSS/LTE/VPS/map path remains intact. New estimators add quality,
uncertainty, provenance and replayable observations around it; they do not
replace it wholesale.

### M0 — GNSS Reliability

The first baseline is rule/statistics based, not machine learned. Inputs include
fix type, satellite count, HDOP/DOP, speed, course, position jump, fix age and
history consistency. It emits `gnss_quality` in `[0,1]`, position covariance
and reason codes. A later real-data benchmark may justify GBDT or another
lightweight model.

### M1 — IMU Shared Encoder

One shared temporal encoder feeds motion and carry heads in the first trained
version. Impact, embedding and uncertainty interfaces are reserved, but
fall/danger/health claims are out of the initial training scope. DS-CNN, TCN or
a compact 1D CNN is preferred before Transformer-class models. `50 Hz` and
`2-4 s` windows are engineering starting hypotheses for dataset/energy study;
the current bounded QMI8658 upload is 20 Hz and does not prove them.

### M2 — LTE Fingerprint

The progression is cell centroid, weighted KNN, GBDT, small MLP, then a
sequence model only if evidence supports it. Cell transition sequences are
retained from the beginning. Available modem fields govern the contract; no
unsupported neighbor-cell or radio metric is assumed.

### Fusion F0 and Location Belief

AI models provide versioned observations and uncertainty to a classical
probabilistic estimator. The device baseline is a lightweight EKF or equivalent
state filter; server replay may use a factor graph/smoother. End-to-end opaque
neural fusion is not the v0.1 baseline.

Location Belief is implemented from the first baseline and includes position
or hypothesis, uncertainty radius/covariance, confidence, source contributions,
age, degradation state and reason codes. Missing evidence must produce coarse,
predicted or unknown state rather than invented precise coordinates.

### A3 and A4 initial policy

- A3 begins with explicit events and a `Detector -> Evidence Request ->
  Verifier` flow. It does not train a broad `dangerous/safe` classifier yet.
- A4 begins with a rule policy, then a measured power model, then
  confidence-gated policy, and only later considers a learned policy. Unknown
  or unstable context falls back to a conservative sensing envelope; initial
  work does not use reinforcement learning.
- Camera is a synchronized research-time teacher and event-triggered product
  evidence source, never an always-on product dependency.

### A-R0 numbering and experiment trigger

Founder direction on 2026-08-16 fixes the A-R0 task order as:

1. A0-001 IMU Calibration
2. A0-002 Unified Timestamp
3. A0-003 Field Session Schema
4. A0-004 Dataset Validator
5. A0-005 Label Schema
6. A0-006 Replay Engine
7. A0-007 Evaluation Framework
8. A0-008 Field Dataset Protocol

This order supersedes the illustrative A0-005/A0-006 numbering in section 22
of the initial A-line context; it does not change the eight unverified A-R0
exit criteria. After A0-001 through A0-004 and a first valid real session,
`EXP-A1-001 GNSS Blackout Baseline` may start with deterministic 30/60/180/300
second source masking. No performance threshold or result is predeclared.

## Consequences

- A-R0 remains `0/8` until each criterion has the required real and automated
  evidence; implementation commits alone are insufficient.
- A0-001 is the first implementation task. Raw available sensor values,
  calibration provenance and exact time lineage become long-lived data assets.
- Carry state is a first-class IMU task because it changes the sensor
  distribution and localization value of motion observations.
- Research directions F1 Physical SSL, F2 Camera-to-IMU distillation and F3
  Active Perception may guide data readiness, but papers and prototypes are not
  product evidence.

## Research Provenance (Not Gate Evidence)

- [Physical Self-Supervised Learning](https://arxiv.org/abs/2607.18361)
  motivates retaining unlabelled IMU, placement and synchronized anchor data
  for explicit physics-informed representation learning. It does not define or
  validate Ego Link's six-face calibration procedure.
- [DINS-IO](https://arxiv.org/abs/2607.20232) motivates accurate sample timing,
  attitude provenance and raw inertial retention for differentiable INS
  consistency. Its metric scale still uses a small amount of labelled velocity
  data, so it is not evidence that unlabeled IMU alone yields an absolute
  metric trajectory.
- [COMODO](https://arxiv.org/abs/2503.07259) supports synchronized video/IMU
  research sessions with a video teacher and an IMU-only runtime student. It
  evaluates activity representation, not localization or personal safety.
- [Viveka](https://arxiv.org/abs/2608.05572) motivates confidence/stability
  gating and conservative fallback for adaptive sensing. It is an arXiv
  wearable-classification/energy preprint, not an Ego Link power result or a
  personal-safety certification.

These sources are research provenance only. They cannot satisfy an A-R0 exit
criterion, replace a real Field Session, or justify model, localization,
safety or energy claims for Ego Link.

## Reconsideration Triggers

- Replay benchmarks show the classical estimator cannot meet the defined
  uncertainty-calibration or compute envelope after observation models mature.
- Measured device constraints make the proposed sampling/window baseline
  infeasible.
- Real sessions show the motion/carry shared representation causes a material,
  repeatable regression relative to separate lightweight baselines.
- Privacy, power or synchronization gates make Camera teacher sessions
  unacceptable.

## Related Documents

- `docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md`
- `docs/product/NORTH_STAR.md`
- `docs/product/EGO_MASTER_CONTEXT.md`
- `docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md`
