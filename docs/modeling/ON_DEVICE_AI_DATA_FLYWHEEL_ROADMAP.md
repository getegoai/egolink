---
document_status: working_plan
last_verified: 2026-07-05
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
8. DATA-006 runs the post-capture pipeline as one bounded command: ingest
   named recordings, refresh flywheel status, and export the dataset handoff
   manifest.
9. TRAIN-002 registers a bounded training experiment plan from the dataset
   handoff manifest, recording runner readiness and planned metrics without
   starting a training job.
10. DATA-007 surfaces the latest bounded experiment plan in Web/API and
    deployment summaries so runner readiness is visible without exposing raw
    records.
11. DATA-008 binds each D1 post-run collection to the Web/API report, power
    curve, D1 demo report, data-flywheel pipeline, dataset manifest, and
    training-experiment plan from one local summary.
12. DATA-009 generates explicit synthetic-only scenario recordings for
    no-hardware pipeline dry-runs. These may exercise annotation, review,
    dataset handoff, and experiment readiness, but they are not field evidence
    or release metrics.
13. TRAIN-003 runs a bounded training-run preflight from the TRAIN-002 plan and
    TRAIN-001 manifest, producing a runner handoff check without training,
    evaluating, uploading, or deploying a model.
14. DATA-010 surfaces the latest bounded TRAIN-003 preflight in Web/API and
    curated deploy summaries, keeping runner status visible without exposing
    private endpoints, raw records, or model artifacts.
15. TRAIN-004 exports bounded training feature manifests and JSONL feature rows
    from ready dataset/preflight inputs, keeping target labels separate from
    manifest-summary features and still producing no model artifact.
16. DATA-011 surfaces the latest TRAIN-004 feature manifest in Web/API and
    curated deployment summaries without exposing JSONL row contents or model
    artifacts.
17. TRAIN-005 validates local runner-input shape from the TRAIN-004 manifest
    and JSONL rows, producing a dry-run report while keeping model training and
    measured metrics at `not_run`.
18. DATA-012 surfaces the latest TRAIN-005 runner dry-run in Web/API and
    curated deployment summaries without exposing JSONL row contents or model
    artifacts.
19. TRAIN-006 runs aggregate baseline evaluation from TRAIN-004/005 inputs so
    metrics plumbing can be exercised. Synthetic metrics remain integration
    checks only and are not product performance evidence.
20. DATA-013 surfaces the latest TRAIN-006 baseline-eval status in Web/API and
    curated deployment summaries without exposing raw rows or model artifacts.
21. DATA-014 lets the D1 post-run collector continue through TRAIN-003..006
    when the dataset handoff is ready, while skipped/not-ready cases remain
    explainable in the same post-run summary.
22. TRAIN-007 builds one bounded handoff bundle from the dataset, preflight,
    feature, runner dry-run, and baseline-eval reports so a future training
    server can consume explicit refs and hashes without row contents.
23. DATA-015 surfaces the latest TRAIN-007 handoff bundle in Web/API and
    curated deployment summaries without exposing row contents, private
    endpoints, or model artifacts.
24. DATA-016 lets the D1 post-run collector continue through TRAIN-007 and
    records the handoff-bundle status in the post-run summary and field kit.
25. TRAIN-008 creates a bounded training job plan from a TRAIN-007 handoff
    bundle, recording runner queue intent and planned metrics without starting
    model training.
26. DATA-017 surfaces the latest TRAIN-008 job plan in Web/API and curated
    deployment summaries without exposing row contents, private endpoints, or
    model artifacts.
27. DATA-018 lets the D1 post-run collector continue through TRAIN-008 and
    records the job-plan status in the post-run summary and field kit.
28. MotionNet v0.1 starts with a statistical baseline and small model
    candidates only after candidate data passes quality, privacy, consent, and
    split-leakage checks.
29. Device deployment begins in shadow mode: model output is recorded alongside
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
| Dataset manifest | Export reviewed candidates to a training-server handoff manifest. | TRAIN-001. |
| Pipeline runner | Run capture-to-handoff status from one repeatable post-run command. | DATA-006. |
| Experiment registry | Register dataset readiness, runner handoff status, planned metrics, and non-claims for a future trainer. | TRAIN-002. |
| Experiment visibility | Surface latest bounded experiment-plan readiness in Web/API and curated deploy summaries. | DATA-007. |
| Post-run collection | Bind D1 Web/API, power, demo, data-flywheel, dataset, and experiment artifacts into one post-field summary. | DATA-008. |
| Synthetic dry-run | Exercise the data flywheel without hardware while keeping synthetic records out of release claims. | DATA-009. |
| Runner preflight | Check experiment/dataset handoff readiness before a real training runner exists. | TRAIN-003. |
| Runner visibility | Surface latest runner preflight readiness in Web/API and curated deploy summaries. | DATA-010. |
| Feature manifest | Export bounded feature rows for a future runner without raw tensors or training. | TRAIN-004. |
| Feature visibility | Surface latest feature manifest readiness without row contents or model artifacts. | DATA-011. |
| Runner dry-run | Validate runner input shape before real training/evaluation integration. | TRAIN-005. |
| Runner visibility | Surface latest runner dry-run readiness without row contents or model artifacts. | DATA-012. |
| Baseline evaluation | Exercise aggregate metrics plumbing without model artifacts or release claims. | TRAIN-006. |
| Baseline visibility | Surface latest baseline-eval readiness without raw rows or model artifacts. | DATA-013. |
| Post-run training chain | Run TRAIN-003..006 from the D1 post-run collector when a reviewed dataset handoff is ready. | DATA-014. |
| Training handoff bundle | Bind dataset, preflight, feature, runner dry-run, and baseline-eval refs and hashes for a future training runner/server without copying rows. | TRAIN-007. |
| Handoff visibility | Surface latest handoff-bundle readiness without row contents, private endpoints, or model artifacts. | DATA-015. |
| Post-run handoff bundle | Extend the D1 post-run collector and field kit through TRAIN-007. | DATA-016. |
| Training job plan | Create a bounded runner/server queue plan from a handoff bundle without starting training. | TRAIN-008. |
| Training job visibility | Surface latest job-plan readiness without row contents, private endpoints, or model artifacts. | DATA-017. |
| Post-run job plan | Extend the D1 post-run collector and field kit through TRAIN-008. | DATA-018. |
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
- TRAIN-001 manifests include only reviewed, training-allowed candidates and
  bounded lineage/label/split summaries; they are not model training runs.
- DATA-006 pipeline runs only ingest recording directories explicitly named by
  the operator; it does not scan runtime folders by default or copy DB files,
  raw candidate records, raw payloads, private coordinates, or JSONL logs.
- TRAIN-002 experiment plans are runner handoff records only; metrics remain
  `planned_not_measured` until a later training/evaluation task writes measured
  evidence.
- DATA-007 Dashboard/API summaries may show experiment status and planned
  metrics only; they do not expose raw records, candidate DB paths, runtime
  JSONL logs, or private training-server endpoints.
- DATA-008 post-run summaries contain artifact paths and bounded component
  statuses only; they do not copy raw exports, candidate DBs, private payloads,
  runtime JSONL logs, or model artifacts.
- DATA-009 synthetic scenarios must carry `synthetic_only=true`, remain
  separate from field evidence, and may only support pipeline dry-runs or
  runner integration tests. Synthetic review approval is not product release
  acceptance and cannot be used for real-world model metrics.
- TRAIN-003 preflight reports may verify runner handoff readiness and synthetic
  dry-run acknowledgement, but measured metrics remain `not_run` until a real
  training/evaluation runner writes reviewed evidence.
- DATA-010 Web/API summaries may show TRAIN-003 status, checks, gates, and
  `not_run` measured-metric placeholders only; they do not expose raw records,
  candidate DB paths, runtime JSONL logs, private training-server endpoints, or
  model artifacts.
- TRAIN-004 feature manifests may export bounded manifest-summary feature rows
  from a ready dataset/preflight pair. Target labels stay under `target`, not
  under `features`; rows do not contain raw recordings, raw IMU windows,
  MotionNet tensors, candidate DB paths, runtime JSONL logs, private training
  endpoints, model artifacts, or measured model metrics.
- DATA-011 Web/API summaries may show TRAIN-004 status, row count, feature
  scope, dataset/preflight source matching, target-boundary guard, gates, and
  `not_run` measured-metric placeholders only; they do not expose JSONL row
  contents, raw records, candidate DB paths, runtime JSONL logs, private
  training-server endpoints, raw tensors, model artifacts, or measured model
  metrics.
- TRAIN-005 runner dry-run reports may validate manifest/row matching,
  required row fields, target-leakage guard, split/label/source counts, and
  synthetic acknowledgement. They do not train, evaluate, upload, or deploy a
  model, and they do not produce model artifacts or measured model metrics.
- DATA-012 Web/API summaries may show TRAIN-005 status, runner-input gate,
  row-count matching, split/label/source counts, target-leakage guard,
  synthetic policy, gates, and `not_run` measured-metric placeholders only;
  they do not expose JSONL row contents, raw records, candidate DB paths,
  runtime JSONL logs, private training-server endpoints, raw tensors, model
  artifacts, or measured model metrics.
- TRAIN-006 baseline-evaluation reports may show aggregate baseline metrics
  from TRAIN-004/005 inputs. Synthetic rows require explicit acknowledgement
  and produce synthetic integration metrics only. Reports do not contain raw
  rows, model weights, model cards, training-server endpoints, footprint,
  latency, power measurements, device deployment results, or release claims.
- DATA-013 Web/API summaries may show TRAIN-006 status, aggregate baseline
  metrics, row counts, synthetic policy, gates, and report paths only; they do
  not expose JSONL row contents, raw records, private case rows, private
  endpoints, model artifacts, model cards, footprint, latency, power
  measurements, device deployment results, or release claims.
- DATA-014 post-run summaries may show TRAIN-003..006 component statuses,
  row counts, metric scope, gates, next step, and report paths after a ready
  dataset handoff. They do not expose feature-row JSONL contents, raw records,
  candidate DB paths, private training endpoints, model artifacts, model cards,
  footprint, latency, power measurements, device deployment results, or release
  claims.
- TRAIN-007 handoff bundles may show input refs, file hashes, row counts,
  component readiness, training-server integration status, gates, and next
  steps. They do not copy JSONL row contents, raw records, candidate DBs,
  runtime JSONL logs, private training endpoints, model artifacts, model cards,
  footprint, latency, power measurements, device deployment results, or release
  claims.
- DATA-015 Web/API summaries may show TRAIN-007 status, bounded source refs,
  file hashes, row counts, synthetic policy, training-server integration state,
  gates, and report paths only; they do not expose JSONL row contents, raw
  records, candidate DB paths, runtime JSONL logs, private endpoints, model
  artifacts, model cards, footprint, latency, power measurements, device
  deployment results, or release claims.
- DATA-016 post-run summaries may show TRAIN-003..007 component statuses,
  handoff-bundle status, row counts, source-ref hashes, gates, next step, and
  report paths after a ready dataset handoff. They do not expose feature-row
  JSONL contents, raw records, candidate DB paths, private endpoints, model
  artifacts, model cards, footprint, latency, power measurements, device
  deployment results, or release claims.
- TRAIN-008 job plans may show model track, candidate/baseline model names,
  feature row counts, runner profile, planned metrics, gates, source handoff
  hash, and next step. They do not copy feature-row JSONL contents, call
  private endpoints, train/evaluate a model, produce model artifacts/cards,
  measure footprint/power, deploy to devices, or support release claims.
- DATA-017 Web/API summaries may show TRAIN-008 status, source handoff hash,
  dataset/feature summaries, model plan, runner queue state, planned metrics,
  gates, and report paths only. They do not expose JSONL row contents, raw
  records, candidate DB paths, runtime JSONL logs, private endpoints, model
  artifacts, model cards, footprint, latency, power measurements, device
  deployment results, or release claims.
- DATA-018 post-run summaries may show TRAIN-003..008 component statuses,
  job-plan status, handoff refs, row counts, planned metrics, gates, next
  step, and report paths after a ready dataset handoff. They do not expose
  feature-row JSONL contents, raw records, candidate DB paths, private
  endpoints, model artifacts, model cards, footprint, latency, power
  measurements, device deployment results, or release claims.

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
