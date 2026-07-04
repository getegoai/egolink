---
document_status: working_plan
last_verified: 2026-07-04
verified_by: codex
---

# On-Device AI Data Flywheel Roadmap

This working plan connects the live D1 link to the V1 on-device AI track. It
does not replace `docs/roadmap/V1_PRODUCT_PLAN.md`, train a model, change
firmware behavior, or declare any safety-model accuracy.

## Direction

The model path should advance in parallel with D1 field and power work, but it
must consume only reviewed evidence:

1. D1/D3 field runs generate reliable device, power, location, and interaction
   evidence.
2. M1 session recordings package bounded sensor frames, events, annotations,
   quality reports, hashes, and privacy state.
3. DATA-003 stores session annotations as training-candidate records in a
   local SQLite candidate store, with review still pending.
4. M1-005/M1-006 add labeling and collection protocols for normal negative
   samples and controlled simulated positives.
5. DATA-004 keeps the flywheel visible through bounded status summaries and a
   Dashboard/API panel without exposing raw records.
6. DATA-005 adds a bounded candidate review queue and conservative promotion
   gate before any record can become `reviewed_training_candidate`.
7. TRAIN-001 exports reviewed candidates to a dataset/experiment handoff
   manifest for offline model work.
8. MotionNet v0.1 starts with a statistical baseline and small model
   candidates only after candidate data passes quality, privacy, consent, and
   split-leakage checks.
9. Device deployment begins in shadow mode: model output is recorded alongside
   the deterministic Safety Kernel and RuleRouter; it does not replace safety
   behavior until later acceptance gates pass.

## Execution Order

| Stage | Purpose | First concrete task |
|---|---|---|
| Capture | Keep every D1/D3 run evidence-rich and replayable. | FIELD-004 and PWR-001 continue. |
| Candidate store | Turn session recordings plus annotations into bounded records. | DATA-003. |
| Labeling | Add human/user labels with consent and privacy state. | M1-005. |
| Collection protocol | Collect normal negatives and safe controlled positives. | M1-006. |
| Dataset readiness | Summarize review queues, split leakage blockers, and training readiness. | DATA-004. |
| Candidate review | Approve, reject, or return bounded candidates without exposing raw records. | DATA-005. |
| Dataset manifest | Export reviewed candidates to a training-server handoff manifest. | TRAIN-001 planned. |
| Model baseline | Compare thresholds, feature baselines, 1D-CNN, and TCN. | MotionNet v0.1 planned. |
| Footprint | Measure RAM, flash, latency, and per-inference power. | MODEL-001 resumes after an artifact exists. |
| Device shadow mode | Run model beside rules and record deltas. | MODEL-002 planned. |
| Product gate | Review false positives, power delta, rollback, and update path. | D4/D5 release gate planned. |

## Candidate Store Rules

- Dashboard live state is not training data by itself.
- Raw JSONL/private payloads are not copied into docs, dashboard summaries, or
  committed artifacts.
- Candidate records keep refs, hashes, source labels, privacy state, consent
  state, labels, quality status, split state, and release-review placeholders.
- `training_allowed` remains false until a later review promotes a record to
  `reviewed_training_candidate`.
- Session splits are blocked by complete sessions first; random row splitting
  is not allowed.
- DATA-004 status summaries and Dashboard panels are control-plane visibility
  only; they are not dataset manifests and do not contain raw records.
- DATA-005 review actions may promote a record only after label, consent,
  privacy, quality, and split-leakage review pass; rejected and needs-changes
  records never become training allowed.

## Model And Power Gates

The first deployable model should be MotionNet-class and small enough to test
on ESP32-S3, but deployment is staged:

1. PC reference result.
2. Firmware-compatible test vectors.
3. ESP32-S3 build footprint.
4. ESP32-S3 runtime RAM and latency.
5. Sleep-vs-inference power measurement.
6. Shadow-mode field run.
7. Review against rule baseline, false positives, and rollback plan.

Any on-device model must report the extra power cost it introduces. A model
that improves event quality but breaks the product power budget cannot pass a
D4/D5 release gate.
