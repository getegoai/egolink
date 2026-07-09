---
document_status: authoritative
last_verified: 2026-07-09
verified_by: codex
---

## Latest Deployment Note

2026-07-09: D5-001 location-data flywheel plumbing is now implemented
locally. `scripts/summarize_location_data_flywheel.py` converts a bounded D2
`location_accuracy_report.json` into Dashboard-compatible
`reports/data_flywheel/<run-id>/data_flywheel_status.json`, plus a location
review packet and dataset-manifest gate. It supports reference-point,
known-place, no-fix, and bad-fix review formats, keeps raw private coordinates
out of summaries, and the Web Data Flywheel card shows D2 baseline counts,
reference points, fixed/no-fix attempts, source report, review packet, and
manifest gate paths. Model training/deployment remains blocked until explicit
reviewed selection plus founder approval. First real D2 baseline ingestion
remains pending field data.

2026-07-09: D2-001 location accuracy baseline toolchain is now implemented
locally. `scripts/analyze_location_accuracy_baseline.py` converts a FIELD-003
VPS export plus field manifest into `reports/location_accuracy/<run-id>/`
JSON/Markdown with fix rate, TTFF median/p90, median error, p90 error,
per-point breakdown, and EALE-P0 radius comparison. The report is an
engineering baseline only and omits raw private coordinates from Dashboard
summaries. First real D2 outdoor baseline analysis remains pending field data.

2026-07-09: MAP-001 no-key evidence map baseline is implemented locally. The
Dashboard D1 map surface now explicitly shows local no-key mode, provider
status, track/current/reference legend, privacy policy, and no accuracy claim.
Field Test Results now has evidence lanes for D2 Baseline, D1 Regression,
Power, and D5 Flywheel. D2 location accuracy summaries under
`reports/location_accuracy/` can appear without exposing raw private
coordinates.

2026-07-09: Founder direction update: D1 continuous outdoor testing is now a
regression loop, not an endless transition blocker. D1 has reached the
link-through transition standard because the 4G board -> LTE -> VPS ->
Dashboard loop is visible, repeatable, and reportable with explicit
non-claims. FIELD/PWR runs continue, but active development now moves to the
D2 -> D5 mainline: D2 location-accuracy baseline, map/evidence visibility, and
D5 location-data flywheel. Tiny Safety/safety-classification assets remain
reusable later, but immediate AI/data work must serve location accuracy.

2026-07-09: D1 field evidence from `FIELD-004-outdoor-20260709-0900`
is now bound into a power report and one-page demo report. Web/API passed,
with 24 trajectory points and 237/237 raw POST success in the post-run view;
the observer-derived power report has 126 measured samples over 2.192 h but
is WARN because it is below the 3 h field threshold and no battery-capacity
estimate was supplied. D1 demo remains WARN and not founder-review-ready:
`reports/d1_demo/FIELD-004-outdoor-20260709-0900/d1_demo_report.md`.
`collect_d1_postrun.py` schema v0.12 can now derive the power export from
`d1_field_samples.jsonl` when no Message Hub test-run export is available.
The VPS Field Test Results panel now shows 7 bounded D1 cards, including
post-run, D1 demo, and power curve summaries.

2026-07-08: Director reset applied from `docs/product/NORTH_STAR.md`. This
D1-only freeze is superseded by the 2026-07-09 founder transition update above.
At the time, active work was narrowed to D1 acceptance only: 3-4h outdoor
link-through run, Dashboard map point plus trajectory view, Web/API freshness
gate, measured power curve, one-page D1 report, founder acceptance, and tag
`v0.1.0`. Existing Tiny Safety and data-chain assets were retained for later
D5 reuse. The D1 field kit v17 is generated at
`reports/d1_field/FIELD-004-d1-acceptance-20260708-4h/`.

2026-07-08: D1 Dashboard now exposes a first-screen `D1 Acceptance Gate`.
It shows ready/blocked state, current vs required track points, blockers,
warnings, and next action from `/api/state.d1_link.acceptance_gate`. This is
D1 preflight/post-run review only and does not claim location accuracy or
battery life.

2026-07-08: D1 Dashboard/Web API now explains coordinate blockers. The
`map_surface.coordinate_diagnostics` and acceptance gate show location uploads
vs coordinate-bearing uploads, missing count, latest missing reason, and the
operator hint; live no-fix uploads remain a D1 blocker until at least two
coordinate-bearing points arrive.

2026-07-07: MODEL-DEVICE-009 Tiny Safety hard-case review packet is
implemented locally. The exporter consumes the MODEL-DEVICE-008 synthetic
stress report and writes a bounded synthetic review packet under
`model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/label_review/`.
The current packet exports 24 hard-case review records; all 24 are
synthetic-only, unreviewed, training-disallowed, low-confidence, low-margin,
and synthetic-oracle disagreements. The records preserve model prediction,
synthetic oracle label, priority reasons, bounded synthetic features, and an
empty human-review slot. This is a labeling workflow fixture only: no
field/private samples, candidate DBs, model training, firmware/hardware
contact, real-world accuracy, runtime, power, SMS/call/escalation, or release
readiness is claimed.

2026-07-07: MODEL-DEVICE-008 Tiny Safety synthetic stress evaluation is
implemented locally. The evaluator runs the existing MODEL-DEVICE-001 artifact
against a deterministic 540-case synthetic boundary matrix and writes
JSON/Markdown under
`model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/evaluation/`.
The current synthetic agreement is 365/540 (`0.675926`), with 523
low-confidence and 331 low-margin cases; `uncertain` is the top labeling
priority with 141 synthetic disagreements. This is model-iteration triage
only: no field/private samples are read, no model behavior is changed, and no
real-world accuracy, runtime, power, SMS/call/escalation, or release-readiness
claim is made.

2026-07-07: MODEL-DEVICE-007 Tiny Safety static footprint report is
implemented locally. The new evaluator reads the existing MODEL-DEVICE-001
artifact/export files and, when present, the MODEL-DEVICE-006 local firmware
build binary, then writes a bounded static footprint report under
`model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/assessment/`.
Current Tiny Safety v0 static evidence is `L2_build_verified_static_partial`:
60 parameters, 834 estimated C constant bytes, 56 score multiplies/adds, 4
confidence `expf` calls, and local app binary size 321248 bytes. Runtime RAM,
latency, energy, model delta, MotionNet acceptance, PROD-001 budget updates,
real-world accuracy, real SMS/call/escalation, and release readiness remain
unclaimed.

2026-07-07: MODEL-DEVICE-006 Tiny Safety hardware flash validation is done.
The connectivity node was identified on CH343 `COM4` with SIM7670G AT ports
visible, then flashed with Tiny Safety D1 firmware
`0.1.0-model-device-006-tiny-safety-hw` / test run
`MODEL-DEVICE-006-hw-20260707-d1`; boot log observed app commit `cf5b4a6`.
Bounded serial CLI validation passed on `COM4`, and post-reset Web/API
observation passed with fresh LTE uploads, firmware/test-run IDs matching the
new image, raw D1 periodic `location_report`/`location_observation` frames, max
freshness 67 s, raw POST success delta `2`, and raw POST failure delta `0`.
Evidence is under
`reports/tiny_safety_firmware_cli/MODEL-DEVICE-006-hw-20260707-serial-cli-transcript2/`,
`reports/board_validation/20260707-model-device-006-reset-log/`, and
`reports/d1_field_observation/MODEL-DEVICE-006-hw-20260707-after-reset-observer/`.
This is still a bounded hardware/model-loop validation only: no real-world
model accuracy, GNSS accuracy, battery-life, long LTE stability, call/SMS,
external escalation, or release-readiness claim is made.

2026-07-07: MODEL-DEVICE-005 Tiny Safety device-loop runner is implemented
locally. `scripts/prepare_tiny_safety_device_loop.py` writes an offline
JSON/Markdown run plan that stitches together the D1 periodic-location firmware
build, optional guarded flash, guarded `safety tiny ...` serial validation, and
post-flash USB-Free D1 Web/API observer checks. A sample plan was generated at
`reports/tiny_safety_device_loop/MODEL-DEVICE-005-plan-20260707/`. This does
not run the generated commands, flash firmware, open serial ports, contact
hardware, contact the VPS, read token values, change model or Safety Kernel
behavior, map model output to SMS/calls/dispatch/external escalation, train on
field/private data, or claim real-world model accuracy, latency, RAM, flash,
power, or release readiness.

2026-07-07: MODEL-DEVICE-004 Tiny Safety firmware CLI validator is
implemented locally. `scripts/validate_tiny_safety_firmware_cli.py` can write a
default no-hardware dry-run report, parse fixture logs, or, only with an
explicit `--port` plus `--i-understand-serial-hardware`, run a bounded serial
validation of `safety tiny status/selftest/demo ...` marker lines and produce
JSON/Markdown evidence under `reports/tiny_safety_firmware_cli/`. This does
not flash firmware, change model or Safety Kernel behavior, map model output to
SMS/calls/dispatch/external escalation, contact hardware by default, train on
field/private data, deploy to the VPS, or claim real-world model accuracy,
latency, RAM, flash, power, or release readiness.

2026-07-07: MODEL-DEVICE-003 Tiny Safety firmware CLI closed loop is
implemented locally. The `mqtt_heartbeat` firmware safety CLI now exposes
`safety tiny status`, `safety tiny selftest`, and `safety tiny demo ...`
commands so a flashed image can report the MODEL-DEVICE-001 model ID/version,
run exported synthetic test-vector self-checks, and show dry-run candidate
predictions for `normal`, `uncertain`, `needs_check`, `possible_risk`, SOS,
and cancel paths. This does not flash or run on hardware yet, change
deterministic Safety Kernel behavior, map model output to SMS/calls/dispatch/
external escalation, measure latency/RAM/flash/power, deploy to the VPS, train
on field/private data, or claim real-world model accuracy or release readiness.

2026-07-07: MODEL-DEVICE-002 Tiny Safety firmware dry-run harness is
implemented locally. The existing `firmware/mqtt_heartbeat/components/
safety_model` component now includes `tiny_safety_harness.c`, which reads the
MODEL-DEVICE-001 generated C constants, extracts the 14-feature vector from
`ego_sc_model_input_t`, predicts the dry-run state label, and self-checks the
exported synthetic test vectors. This does not change the existing
`safety_model_evaluate()` deterministic mock/rule behavior, map model output
to calls/SMS/dispatch/external escalation, flash or deploy a device, measure
latency/RAM/flash/power, train on field/private samples, deploy to the VPS, or
claim real-world model accuracy or release readiness.

2026-07-07: MODEL-DEVICE-001 Tiny Safety Model v0 local train/export loop is
implemented locally. `model_lab/safety_companion/src/tiny_safety_model.py`
defines a dependency-free four-state classifier (`normal`, `uncertain`,
`needs_check`, `possible_risk`) over the existing `model_input` contract;
`model_lab/safety_companion/training/train_tiny_safety_model.py` writes a
synthetic-only `tiny_safety_model.json` artifact, model card, and eval JSONL
under `model_artifacts/`; and
`model_lab/safety_companion/export/export_tiny_safety_model.py` exports
firmware-friendly C constants and test vectors for a future firmware task.
This does not replace Safety Kernel SOS/cancel/privacy/power rules, train on
private field samples, integrate firmware, flash or deploy a device, measure
latency/RAM/flash/power, deploy to the VPS, or claim real-world model accuracy
or release readiness.

2026-07-07: DATA-032 D1 labeling decision-template validation is implemented
locally. `scripts/validate_d1_labeling_decision_template.py` validates filled
`d1_labeling_decision_template` selected values, reports missing/invalid
decisions, and identifies items ready for a future explicit candidate-store
promotion task. `scripts/collect_d1_postrun.py` is now schema
`egolink.d1_postrun_collection.v0.11` and includes
`labeling_decision_validation`; field kit v16 expects the
`d1_labeling_decision_validation` artifact. This does not read sample JSONL,
expose exact coordinates/raw payloads/private operator notes/feature rows/
targets/candidate DBs, apply decisions, write candidate records, create
training samples, train/evaluate a model, write model artifacts, deploy
inference, measure model footprint/power, deploy to the VPS, or allow release
claims.

2026-07-06: DATA-031 D1 labeling decision-template Web/API visibility is
implemented locally. The Message Hub can load the latest bounded
`reports/d1_labeling_decisions/**/d1_labeling_decision_template.json`, expose it
as `d1_labeling_decision_template` in `/api/state`, serve it at
`/api/v1/d1-labeling-decision-template/latest`, and render a Dashboard panel
for pending decision-template work. Field kit v15 includes the explicit
`-IncludeD1LabelingDecisionSummaries` sync switch. This does not read sample
JSONL, expose exact coordinates/raw payloads/feature rows/targets/candidate
DBs/private operator notes, mark items reviewed, apply decisions, write
candidate records, train/evaluate a model, write model artifacts, deploy
inference, measure model footprint/power, deploy to the VPS, or allow release
claims.

2026-07-06: DATA-030 D1 labeling decision-template and post-run binding is
implemented locally. `scripts/build_d1_labeling_decision_template.py` turns a
bounded `d1_labeling_review_packet` summary into a fillable decision template
with operator label, privacy review, training consent, split plan, and
candidate decision fields; `scripts/collect_d1_postrun.py` is now schema
`egolink.d1_postrun_collection.v0.10` and includes this as
`labeling_decision_template`; field kit v14 expects the
`d1_labeling_decision_template` artifact. This does not read sample JSONL,
expose exact coordinates/raw payloads/feature rows/targets/candidate DBs,
mark items reviewed, apply decisions, write candidate records, train/evaluate
a model, write model artifacts, deploy inference, measure model
footprint/power, deploy to the VPS, or allow release claims.

2026-07-06: DATA-029 D1 labeling review-packet Web/API visibility is
implemented locally. The Message Hub can load the latest bounded
`reports/d1_labeling_reviews/**/d1_labeling_review_packet.json`, expose it as
`d1_labeling_review_packet` in `/api/state`, serve it at
`/api/v1/d1-labeling-review-packet/latest`, and render a Dashboard panel for
pending D1 review work. Field kit v13 includes the explicit
`-IncludeD1LabelingReviewSummaries` sync switch. This does not read sample
JSONL, expose exact coordinates/raw payloads/feature rows/targets/candidate
DBs, mark items reviewed, write candidate records, train/evaluate a model,
write model artifacts, deploy inference, measure model footprint/power, deploy
to the VPS, or allow release claims.

2026-07-06: DATA-028 D1 labeling review-packet and post-run binding is
implemented locally. `scripts/build_d1_labeling_review_packet.py` turns a
bounded `d1_labeling_queue` summary into a human-review work packet with
decision slots for operator label, privacy review, training consent, split
plan, and candidate decision; `scripts/collect_d1_postrun.py` is now schema
`egolink.d1_postrun_collection.v0.9` and includes this as
`labeling_review_packet`; field kit v12 expects the
`d1_labeling_review_packet` artifact. This does not read sample JSONL, expose
exact coordinates/raw payloads/feature rows/targets/candidate DBs, mark items
reviewed, write candidate records, train/evaluate a model, write model
artifacts, deploy inference, measure model footprint/power, deploy to the VPS,
or allow release claims.

2026-07-06: DATA-027 D1 labeling-queue Web/API visibility is implemented
locally. The Message Hub can load the latest bounded
`reports/d1_labeling_queue/**/d1_labeling_queue.json`, expose it as
`d1_labeling_queue` in authenticated `/api/state`, serve
`/api/v1/d1-labeling-queue/latest`, and render a Dashboard
`D1 Labeling Queue` panel. `scripts/deploy_message_hub_vps.ps1` has a new
explicit `-IncludeD1LabelingQueueSummaries` switch that copies only
`d1_labeling_queue.json/.md`; field kit v11 includes that switch in the
post-run sync command. This was not deployed to the VPS in this run and does
not read sample JSONL, expose exact coordinates/raw payloads/feature rows/
targets/candidate DBs, write training samples, train/evaluate a model, write
model artifacts, deploy inference, measure model footprint/power, or allow
release claims.

2026-07-06: DATA-026 D1 labeling-queue index and post-run binding is
implemented locally. `scripts/summarize_d1_labeling_queue.py` scans bounded
`d1_labeling_intake` summaries and writes a compact queue of D1 runs pending
labels, privacy review, consent decision, and split planning; the D1 post-run
collector now includes this as `labeling_queue` and field kit v10 expects the
`d1_labeling_queue` artifact. This does not read sample JSONL, write candidate
DBs, expose exact coordinates/raw payloads, contact hardware, deploy to the
VPS, train/evaluate a model, write model artifacts, or make release claims.

2026-07-06: FIELD-009 D1 3-4h field-kit v9 readiness/intake closure is
implemented locally. `scripts/prepare_d1_field_kit.py` now emits D1
training-readiness and labeling-intake expected outputs, adds them to
operator notes/runbook/checklist, and includes the curated VPS sync switches
for those bounded summaries. This prepares the next 3-4h D1 outdoor run but
does not contact hardware, flash firmware, deploy to the VPS, read raw sample
JSONL, expose private payloads, train/evaluate a model, or make accuracy,
battery-life, GNSS, calling/SMS, or product-readiness claims.

2026-07-06: DATA-025 D1 post-run labeling-intake binding is implemented
locally. `scripts/collect_d1_postrun.py` is now schema
`egolink.d1_postrun_collection.v0.7`; when a post-run collection generates or
receives D1 training readiness, it also writes a bounded `labeling_intake`
component plus a `d1_labeling_intake` artifact path. This remains post-run
summary plumbing only: no sample JSONL read, candidate DB write, raw payload or
coordinate exposure, hardware contact, firmware change, model training,
artifact write, device deployment, or release claim is performed.

2026-07-06: DATA-024 D1 labeling/privacy intake is implemented locally.
`scripts/build_d1_labeling_intake.py` turns a DATA-022
`d1_training_readiness.json` into a bounded `d1_labeling_intake` report and the
Message Hub Dashboard/API can surface the latest intake queue. The intake
stops at human review: it does not read sample JSONL contents, write
candidate DBs, create training samples, expose exact coordinates/raw payloads/
feature rows/targets, contact hardware, change firmware, train/evaluate a
model, deploy inference, or make release claims.

2026-07-06: DATA-023 D1 post-run training-readiness binding is implemented
locally. `scripts/collect_d1_postrun.py` is now schema
`egolink.d1_postrun_collection.v0.6`; when a D1 field-observation report or
status summary is present, it runs the DATA-022 readiness assessment and
includes a bounded `training_readiness` component plus a
`d1_training_readiness` artifact path in the post-run summary. This does not
read sample JSONL contents, contact hardware, send commands, change firmware
or protocol behavior, deploy to the VPS, train/evaluate a model, write model
artifacts, expose exact coordinates/raw payloads/feature rows/targets, or
allow release claims.

2026-07-06: DATA-022 D1 real-data training-readiness assessment is
implemented locally. `scripts/assess_d1_training_readiness.py` reads bounded
D1 field-observation report/status summaries and writes
`reports/d1_training_readiness/**/d1_training_readiness.json/.md` showing
whether the real D1 capture can enter labeling/privacy review before any
training handoff. The Message Hub can expose the latest summary as
`d1_training_readiness` in authenticated `/api/state`, serve
`/api/v1/d1-training-readiness/latest`, and render a Dashboard
`D1 Training Readiness` panel. `scripts/deploy_message_hub_vps.ps1` has a new
explicit `-IncludeD1TrainingReadinessSummaries` switch that copies only
`d1_training_readiness.json/.md`. This was not deployed to the VPS in this run
and does not read sample JSONL, expose exact coordinates/raw payloads/feature
rows/targets/candidate DBs, train/evaluate a model, write model artifacts,
measure model footprint/power, deploy to a device, or allow release claims.

2026-07-06: DATA-021 synthetic training-chain visibility is implemented
locally. The Message Hub can now load the latest bounded
`reports/synthetic_training_chain/**/synthetic_training_chain.json`, expose it
as `synthetic_training_chain` in authenticated `/api/state`, serve
`/api/v1/synthetic-training-chains/latest`, and render a Dashboard
`Synthetic Training Chain` panel. `scripts/deploy_message_hub_vps.ps1` has a
new explicit `-IncludeSyntheticTrainingChainSummaries` switch that copies only
`synthetic_training_chain.json/.md`. This was not deployed to the VPS in this
run and does not expose raw recordings, candidate DB paths, feature-row
contents, private endpoints, model artifacts, measured footprint/power data,
device deployment results, or release claims.

2026-07-06: DATA-020 synthetic training-chain smoke runner is implemented
locally. `scripts/run_synthetic_training_chain.py` generates synthetic-only
sessions, performs the explicit synthetic review dry-run, runs the
data-flywheel pipeline, and continues through TRAIN-003..008 to a bounded
synthetic job plan from one no-hardware command. This does not contact
hardware or the Message Hub, expose candidate DB paths or feature-row
contents, train/evaluate a real model, produce model artifacts/cards, measure
footprint/power, deploy to devices, or allow release claims.

2026-07-06: FIELD-008 local D1 field-observation index is implemented locally.
`scripts/summarize_d1_field_observations.py` scans bounded
`reports/d1_field_observation/**/d1_field_observation_status.json` and final
reports, then writes a local JSON/Markdown index of running/completed observer
runs without reading `d1_field_samples.jsonl`, calling the Message Hub,
contacting hardware, sending commands, deploying code, or making accuracy,
power, GNSS/LTE, model, or product-readiness claims.

2026-07-06: FIELD-007 D1 field-observation visibility is implemented locally.
The Message Hub Field Test Results loader can now include the latest
`reports/d1_field_observation/**/d1_field_observation_report.json` or live
`d1_field_observation_status.json` as a bounded `D1 Field Observation` card in
`/api/state`, `/api/v1/field-results/latest`, and the Dashboard. The curated
VPS deploy switch `-IncludeFieldReportSummaries` can copy
`d1_field_observation_report.json/.md` and
`d1_field_observation_status.json`, but still does not copy
`d1_field_samples.jsonl`. This was not deployed to the VPS in this run and
does not expose local absolute paths, sample JSONL contents, raw payloads,
private coordinates, hardware commands, firmware changes, or location/power/
GNSS/LTE/product-readiness claims.

2026-07-06: DATA-019 post-run field-observation binding is implemented
locally. The D1 post-run collector schema is now
`egolink.d1_postrun_collection.v0.5`; it can bind an explicit or same-run
local `d1_field_observation_report.json` or live
`d1_field_observation_status.json` into the bounded post-run summary as a
`field_observation` component. The D1 field kit recommended post-run command
passes the expected observation report/status paths. This does not read sample
JSONL contents into the summary, contact hardware, send commands, change
firmware/protocol/API behavior, deploy to the VPS, or add location, power,
LTE, GNSS, battery-life, model, or product-readiness claims.

2026-07-06: FIELD-006 D1 observer live status snapshot is implemented
locally. Future `scripts/observe_d1_field_run.py` runs now write
`d1_field_observation_status.json` at startup, after each sample, and at
completion, with running/completed state, sample counts, latest successful
sample metadata, latest seq/freshness, and final report paths. The D1 field
kit expected outputs now include this status file. This affects future
observer runs only; it does not modify any already-running observer process,
contact hardware, send commands, change firmware/protocol/API behavior, or add
location, power, LTE, GNSS, battery-life, or product-readiness claims.

2026-07-06: DATA-018 post-run job-plan collector is implemented locally. The
D1 post-run collector schema is now `egolink.d1_postrun_collection.v0.4` and
continues through TRAIN-008 when the DATA-006 pipeline returns
`ready_for_training_handoff`: TRAIN-003 preflight, TRAIN-004 feature export,
TRAIN-005 runner dry-run, TRAIN-006 baseline eval, TRAIN-007 handoff bundle,
and TRAIN-008 training job plan. The post-run `training_chain.status` now
reports the job-plan status, with bounded `handoff_bundle` and `job_plan`
components. The D1 field kit is updated to v8 with expected
`training_job_plan.json` output and the curated
`-IncludeTrainingJobSummaries` sync switch. This does not train a model, call
or configure a training endpoint, copy feature-row JSONL to the Dashboard,
deploy to devices, produce model artifacts/cards, measure footprint/power, or
allow release claims.

2026-07-06: DATA-017 training job visibility is implemented locally. The
Message Hub can now load the latest bounded
`reports/training_jobs/**/training_job_plan.json`, expose it as
`training_job_plan` in authenticated `/api/state`, serve
`/api/v1/training-jobs/latest`, and render a Dashboard `Training Job Plan`
panel with job status, source handoff hash, dataset/feature summaries, model
plan, runner queue state, planned metrics, gates, next step, and report paths.
`scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingJobSummaries` switch that copies only
`training_job_plan.json/.md`. This was not deployed to the VPS in this run and
does not expose feature-row contents, private endpoints, raw records,
candidate DBs, model artifacts, model cards, measured footprint/power data,
device deployment results, or release claims.

2026-07-06: TRAIN-008 training job plan dry-run is implemented locally. The
new `scripts/create_training_job_plan.py` command consumes an explicitly named
TRAIN-007 `training_handoff_bundle.json` and writes
`reports/training_jobs/<job-id>/training_job_plan.json/.md` with source-handoff
hash, dataset/feature row summaries, model track, candidate/baseline model
names, runner profile, planned metrics, gates, next step, and non-claims.
Ready reviewed handoffs become `ready_for_runner_queue`; synthetic handoffs
require `--allow-synthetic` and remain dry-run only. This does not call or
configure a training endpoint, train/evaluate a model, copy feature-row JSONL
contents, produce model artifacts/cards, measure footprint/power, deploy to
devices, or allow release claims.

2026-07-06: DATA-016 post-run handoff collector is implemented locally. The
D1 post-run collector schema is now `egolink.d1_postrun_collection.v0.3` and
continues through TRAIN-007 when the DATA-006 pipeline returns
`ready_for_training_handoff`: TRAIN-003 preflight, TRAIN-004 feature export,
TRAIN-005 runner dry-run, TRAIN-006 baseline eval, and TRAIN-007 handoff
bundle. The post-run `training_chain.status` now reports the handoff-bundle
status. The D1 field kit is updated to v7 with expected
`training_handoff_bundle.json` output and the curated
`-IncludeTrainingHandoffSummaries` sync switch. This does not train a model,
call or configure a training endpoint, copy feature-row JSONL to the Dashboard,
deploy to devices, produce model artifacts/cards, measure footprint/power, or
allow release claims.

2026-07-06: DATA-015 training handoff visibility is implemented locally. The
Message Hub can now load the latest bounded
`reports/training_handoffs/**/training_handoff_bundle.json`, expose it as
`training_handoff_bundle` in authenticated `/api/state`, serve
`/api/v1/training-handoffs/latest`, and render a Dashboard `Training Handoff
Bundle` panel with handoff status, dataset/preflight/feature/runner/baseline
links, row-count and source-ref summaries, synthetic policy, training-server
integration state, gates, next step, and report paths.
`scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingHandoffSummaries` switch that copies only
`training_handoff_bundle.json/.md`. This was not deployed to the VPS in this
run and does not expose feature-row contents, private endpoints, raw records,
candidate DBs, model artifacts, model cards, measured footprint/power data,
device deployment results, or release claims.

2026-07-06: TRAIN-007 training handoff bundle is implemented locally as the
next D5 bridge after DATA-014. The new
`scripts/build_training_handoff_bundle.py` command consumes explicitly named
DATA/ TRAIN reports: dataset manifest, TRAIN-003 preflight, TRAIN-004 feature
manifest and feature rows, TRAIN-005 runner dry-run, and TRAIN-006 baseline
eval. It writes a bounded `training_handoff_bundle.json/.md` with refs, file
hashes, row counts, readiness gates, training-server integration status, next
step, and non-claims. It does not copy feature-row contents, call or configure
a training endpoint, train or evaluate a real model, produce model weights,
model cards, model artifacts, footprint/power measurements, device deployment,
or release claims.

2026-07-06: FIELD-005 D1 observer incremental samples is implemented locally.
Future `scripts/observe_d1_field_run.py` runs now initialize
`d1_field_samples.jsonl` at start and append each sample immediately after it
is collected, so an unattended field observation can be inspected while it is
still running. Final reports still write `d1_field_observation_report.json/.md`
and now record `sample_write_mode=incremental_jsonl`. This does not affect any
observer process that was already running before the change, does not contact
hardware, send commands, change firmware/protocol/API behavior, or add
location, power, LTE, GNSS, battery-life, or product-readiness claims.

2026-07-06: DATA-014 post-run training-chain collector is implemented locally.
`scripts/collect_d1_postrun.py` now keeps the normal D1 after-run path as one
command and, when the DATA-006 pipeline returns `ready_for_training_handoff`,
continues through TRAIN-003 preflight, TRAIN-004 feature manifest/rows,
TRAIN-005 runner dry-run, and TRAIN-006 baseline eval. When the dataset is not
ready, the new `training_chain` component is skipped with an explainable
reason. The D1 field kit is updated to v6 with expected TRAIN-003..006 outputs
and explicit curated-summary sync switches. This was not deployed to the VPS
and still does not train/evaluate a real model, copy feature-row JSONL to the
Dashboard, produce model artifacts/cards, integrate a runner/server/registry/
OTA path, measure footprint/latency/power, or allow release claims.

2026-07-06: DATA-013 training baseline eval visibility is implemented locally.
The Message Hub can now load the latest bounded
`reports/training_baseline_evals/**/training_baseline_eval.json`, expose it as
`training_baseline_eval` in authenticated `/api/state`, serve
`/api/v1/training-baseline-evals/latest`, and render a Dashboard `Training
Baseline Eval` panel with eval status, feature-set/runner dry-run linkage,
row-count and label/risk/candidate summaries, synthetic policy, aggregate
baseline metrics, non-claim gates, next step, and report paths.
`scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingBaselineEvalSummaries` switch that copies only
`training_baseline_eval.json/.md`. This was not deployed to the VPS in this
run and does not expose JSONL row contents, private case rows, private
endpoints, raw records, model artifacts, model cards, measured footprint,
measured latency, measured power, or release claims.

2026-07-06: TRAIN-006 synthetic baseline evaluation is implemented locally as
the next bounded bridge after TRAIN-005. The new
`scripts/run_training_baseline_eval.py` command reads an explicitly named
TRAIN-004 `training_feature_manifest.json`, TRAIN-004
`training_feature_rows.jsonl`, and TRAIN-005 `training_runner_dry_run.json`;
with explicit `--allow-synthetic`, local smoke evidence under
`reports/training_baseline_evals/train006-local-smoke-20260706/` produced
`status=synthetic_baseline_eval_complete`. Metrics are synthetic integration
checks only: no model training, model weights, model card, model artifact,
training server, model registry, device deployment, footprint, latency, power,
release metric, or product performance claim is produced.

2026-07-05: DATA-012 training runner dry-run visibility is implemented
locally. The Message Hub can now load the latest bounded
`reports/training_runner_dry_runs/**/training_runner_dry_run.json`, expose it
as `training_runner_dry_run` in authenticated `/api/state`, serve
`/api/v1/training-runner-dry-runs/latest`, and render a Dashboard `Training
Runner Dry-Run` panel with runner-input status, feature-set status, row count,
split/label summaries, synthetic policy, target-leakage guard, required-row
checks, `not_run` measured metrics, gates, next step, and report paths.
`scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingRunnerDryRunSummaries` switch that copies only
`training_runner_dry_run.json/.md`. Focused Web/API tests passed locally. This
was not deployed to the VPS in this run, does not expose JSONL row contents,
candidate DBs, raw records, runtime logs, private endpoints, raw tensors, model
artifacts, or measured model metrics, and does not train/evaluate/deploy a
model.

2026-07-05: TRAIN-005 local training runner dry-run is implemented locally as
the next bounded bridge after TRAIN-004 and before any real local/GPU training
runner integration. The new `scripts/run_training_runner_dry_run.py` command
reads an explicitly named `training_feature_manifest.json` plus
`training_feature_rows.jsonl`, checks manifest readiness, row count and feature
set matching, required bounded row fields, target-label leakage, and
synthetic-row policy, then writes
`reports/training_runner_dry_runs/<run-id>/training_runner_dry_run.json/.md`.
Local smoke evidence:
`reports/training_runner_dry_runs/train005-local-smoke-20260705/` consumed the
TRAIN-004 synthetic feature set with explicit `--allow-synthetic`, producing
`status=synthetic_runner_dry_run_complete` for 4 rows. This validates runner
input shape and bounded counts only. It does not train/evaluate a model,
integrate a GPU runner or training server, produce model weights/artifacts,
deploy on-device inference, change firmware/protocol behavior, or claim model
accuracy, latency, footprint, or power impact.

2026-07-05: DATA-011 training feature manifest visibility is implemented
locally. The Message Hub can now load the latest bounded
`reports/training_features/**/training_feature_manifest.json`, expose it as
`training_feature_manifest` in authenticated `/api/state`, serve
`/api/v1/training-features/latest`, and render a Dashboard `Training Feature
Manifest` panel with feature-set status, dataset/preflight source match,
feature-row count/scope, target-boundary guard, synthetic policy, required
field checks, `not_run` measured metrics, gates, next step, and report paths.
`scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingFeatureSummaries` switch that copies only
`training_feature_manifest.json/.md`; it does not copy
`training_feature_rows.jsonl`. Focused Web/API tests passed locally. This was
not deployed to the VPS in this run, does not expose JSONL row contents,
candidate DBs, raw records, runtime logs, private endpoints, raw tensors, model
artifacts, or measured model metrics, and does not train/evaluate/deploy a
model.

2026-07-05: TRAIN-004 training feature manifest export is implemented
locally as the next bounded bridge after TRAIN-003 and before any real training
runner/server integration. The new
`scripts/export_training_feature_manifest.py` command reads an explicitly
named `training_dataset_manifest.json` plus `training_run_preflight.json`,
requires the preflight to be runner-ready, checks dataset/source matching,
required bounded row fields, and synthetic-record policy, then writes
`reports/training_features/<feature-set-id>/training_feature_manifest.json`,
`training_feature_rows.jsonl`, and `training_feature_manifest.md`. Local smoke
evidence: `reports/training_features/train004-local-smoke-20260705/` consumed
the DATA-009 reviewed synthetic dataset and TRAIN-003 preflight with explicit
`--allow-synthetic`, producing 4 manifest-summary feature rows with target
labels separated from feature fields and `status=ready_for_synthetic_feature_dry_run`.
This does not train/evaluate a model, integrate a GPU runner or training
server, generate raw IMU tensors, produce model weights/artifacts, deploy
on-device inference, change firmware/protocol behavior, or claim model
accuracy, latency, footprint, or power impact.

2026-07-05: DATA-010 training-run preflight visibility is implemented locally.
The Message Hub can now load the latest bounded
`reports/training_runs/**/training_run_preflight.json`, expose it as
`training_run_preflight` in authenticated `/api/state`, serve
`/api/v1/training-runs/latest`, and render a Dashboard `Training Run Preflight`
panel with experiment/dataset readiness, synthetic gate, required-field
checks, runner readiness, `not_run` measured metrics, gates, next step, and
report paths. `scripts/deploy_message_hub_vps.ps1` has a new explicit
`-IncludeTrainingRunSummaries` switch that copies only
`training_run_preflight.json/.md`. Focused Web/API tests passed locally. This
was not deployed to the VPS in this run, does not train/evaluate a model,
integrate a GPU runner or training server, expose private endpoints/raw
records/candidate DBs/runtime logs/model artifacts, deploy on-device inference,
or claim model metrics, latency, footprint, or power impact.

2026-07-05: TRAIN-003 training-run preflight is implemented locally as the
bounded bridge after TRAIN-002 and before any real training runner/server
integration. The new `scripts/run_training_experiment_preflight.py` command
reads an explicitly named `training_experiment_plan.json` plus
`training_dataset_manifest.json`, verifies experiment readiness, dataset
readiness, required bounded record fields, split/label/source counts, and
synthetic-record policy, then writes
`reports/training_runs/<run-id>/training_run_preflight.json/.md`. Local smoke
evidence: `reports/training_runs/train003-local-smoke-20260705/` consumed the
DATA-009 reviewed synthetic dataset/experiment, required explicit
`--allow-synthetic`, and produced `status=ready_for_training_runner` with 4
eligible synthetic dry-run records while all measured metrics remained
`not_run`. This does not train/evaluate a model, integrate a GPU runner or
training server, produce model weights/artifacts, deploy on-device inference,
change firmware/protocol behavior, or claim model accuracy, latency, footprint,
or power impact.

2026-07-05: DATA-009 synthetic scenario generator is implemented locally for
D5 data-flywheel dry-runs while field evidence is sparse. The new
`scripts/generate_synthetic_scenarios.py` command writes deterministic
synthetic-only session recordings under
`reports/synthetic_scenarios/<run-id>/`, annotates them with structured-only
privacy and training requests, and can optionally run DATA-006. By default the
pipeline reports `needs_review`; with explicit `--review-synthetic` it reviews
only the generated synthetic candidates and reruns the handoff path to produce
a dry-run `ready_for_training_handoff` dataset manifest and TRAIN-002
`ready_for_runner` experiment plan. Local smoke evidence:
`reports/synthetic_scenarios/data009-local-smoke-20260705/` generated 4
synthetic scenarios, 4 reviewed synthetic records, and a reviewed pipeline
status of `ready_for_training_handoff`. This does not contact hardware, deploy
to the VPS, train/evaluate a model, produce model artifacts, change firmware or
protocol behavior, or claim field evidence, product readiness, model metrics,
latency, footprint, or power impact.

2026-07-05: DATA-008 D1 post-run collector is implemented locally. The new
`scripts/collect_d1_postrun.py` command reads the Message Hub, writes the D1
Web/API gate, optional PWR-001 power curve, D1 demo evidence report,
DATA-006/ TRAIN-002 data-flywheel outputs, and one bounded
`reports/d1_postrun/<run-id>/d1_postrun_collection_summary.json/.md`. The D1
field kit is updated to v5 so FIELD-004 after-run work defaults to this single
collector plus the existing explicit curated-summary VPS sync. This does not
contact hardware, flash firmware, send commands, deploy, train/evaluate a
model, or claim location accuracy, battery life, product readiness, or model
metrics.

2026-07-05: FIELD-004 unattended read-only D1 observation completed with a
useful stale-link finding, not a field pass. Evidence is under
`reports/d1_field_observation/FIELD-004-d1-outdoor-unattended-20260705-140133/`:
`d1_field_observation_report.json/.md` plus `d1_field_samples.jsonl`. Result was
`WARN`: 181/181 VPS API samples succeeded over roughly 3 hours and all 181 had
coordinate samples, but the latest D1 upload stayed at
`2026-07-05T06:00:21.377132+00:00`, upload freshness reached `10934.0 s`,
location event delta was `0`, raw POST delta was `0 ok / 0 fail`, and power
sample delta was `0`. A parallel post-deploy Message Hub stability observation
under
`reports/message_hub_stability/DATA-007-post-deploy-stability-20260705-1430/`
returned `FAIL`: it saw `0` new telemetry-history messages for
`ego-link-r1-connectivity-001`, and final last-seen age was `10737.3 s`. A final
read-only API check at 2026-07-05T17:06+08:00 showed
`last_seen_at=2026-07-05T06:01:03.386419+00:00`,
`field_readiness.reason=periodic_upload_too_old`, and upload freshness about
`11214 s`. The VPS/Dashboard is running, but the D1 device should be treated as
stale until a new fresh upload appears before departure.

2026-07-05: DATA-007 training experiment visibility is implemented locally.
The Message Hub can now load the latest bounded
`reports/training_experiments/**/training_experiment_plan.json`, expose it as
`training_experiment` in authenticated `/api/state`, serve
`/api/v1/training-experiments/latest`, and render a Dashboard `Training
Experiments` panel with dataset readiness, runner handoff, planned metrics,
gates, next step, and report paths. `scripts/deploy_message_hub_vps.ps1` has a
new explicit `-IncludeTrainingExperimentSummaries` switch that copies only
`training_experiment_plan.json/.md`, and the D1 field kit post-run sync command
now includes that switch. Focused Web/API/D1 field-kit tests passed (43 tests);
Python compile and PowerShell parser checks passed; context lint and diff
checks passed; full repository validation passed (418 tests). The update was
deployed to the public VPS Message Hub on `203.0.113.10:8790` with
`-IncludeFieldReportSummaries -IncludeDataFlywheelSummaries
-IncludeTrainingExperimentSummaries` and restarted
`egolink-message-hub.service` without touching GitLab. Smoke after deploy:
`/health` returned `ok=true`, unauthenticated `/api/state` returned `401`,
authenticated `/api/state` included `training_experiment.status=
blocked_dataset_not_ready`, `reason=candidate_store_missing`, and Dashboard
HTML contained `Training Experiments` plus `trainingExperimentPanel`. This does
not copy candidate DBs or runtime JSONL logs, and does not train/evaluate a
model, integrate a runner, or claim model metrics.

2026-07-05: TRAIN-002 training experiment registry is implemented as the next
bounded step after DATA-006. The new `scripts/register_training_experiment.py`
command consumes a TRAIN-001 `training_dataset_manifest.json` and writes
`reports/training_experiments/<experiment-id>/training_experiment_plan.json/.md`
with explicit statuses (`blocked_dataset_not_ready`,
`blocked_no_eligible_records`, or `ready_for_runner`), model-track metadata,
runner handoff state, inherited gates, `planned_not_measured` metrics, and
non-claims. `scripts/run_data_flywheel_pipeline.py` now writes and summarizes
this experiment plan after every dataset manifest, and the D1 field kit records
the expected post-run experiment-plan artifact. Focused tests cover blocked,
ready, require-ready, no-runtime-scan, needs-review, and ready-handoff paths.
Focused validation passed (24 tests), context lint and diff checks passed, and
full repository validation passed (415 tests). This does not train/evaluate a
model, integrate a GPU/training server, produce model weights, deploy on-device
inference, change firmware/protocol behavior, or claim model accuracy,
false-positive rate, latency, footprint, or power impact.

2026-07-05: DATA-006 data-flywheel pipeline runner is implemented for
unattended/post-field operation. The new
`scripts/run_data_flywheel_pipeline.py` command composes the existing
candidate-store ingest, data-flywheel status, and TRAIN-001 dataset-manifest
export into one bounded run: it ingests only `--recording-dir` paths explicitly
named by the operator, writes
`reports/data_flywheel_pipeline/<run-id>/data_flywheel_pipeline_run.json/.md`,
refreshes the corresponding bounded `reports/data_flywheel/<run-id>-data-flywheel/`
status report, and writes a dataset handoff manifest under
`reports/training_datasets/<dataset-id>/`. The D1 field kit is updated to
v4 so the post-run data step records pipeline, status, and dataset handoff
readiness from one command. Focused tests cover empty/no-runtime-scan,
needs-review, and ready-for-training-handoff paths; full repository validation
passed with 412 tests. This does not scan runtime folders by default, copy raw
candidate records, copy candidate DBs, export private coordinates/raw
payloads/JSONL logs, train or evaluate a model, integrate a training server,
change firmware/protocol behavior, deploy on-device inference, or claim model
accuracy, latency, footprint, or power impact.

2026-07-04: TRAIN-001 dataset/experiment handoff manifest is implemented. The
candidate-store module can now export only `reviewed_training_candidate`
records with `training_allowed=true` into a bounded
`egolink.training_dataset_manifest.v0.1` manifest containing label, split,
privacy, quality, feature-group, device, and lineage-hash summaries. The CLI
`scripts/export_training_dataset_manifest.py` writes JSON/Markdown manifests
under `reports/training_datasets/<dataset-id>/`, supports `--require-ready`,
and reports `not_ready` rather than silently producing a training dataset when
no reviewed candidates exist. Local evidence:
`reports/training_datasets/train001-local-handoff-20260704/` currently shows
`status=not_ready`, `reason=candidate_store_missing`, and `eligible_records=0`,
which is expected until reviewed recordings are ingested. Focused
candidate-store tests passed (14 tests), and `python -m py_compile` passed with
a temporary pycache directory after Windows locked the default `__pycache__`.
This does not train/evaluate a model, integrate a GPU/training server, deploy
on-device inference, export raw candidate records, copy DB files, expose private
coordinates/raw payloads, or claim model metrics, footprint, or power impact.

2026-07-04: DATA-005 candidate review queue is implemented. The local
training-candidate store now has bounded review-queue listing plus audited
review actions through `pc_simulator/training_candidate_store.py` and
`scripts/review_training_candidates.py`. `approve_for_training` can promote an
eligible candidate to `reviewed_training_candidate` and set
`training_allowed=true` only after label review, consent/training request,
privacy review, quality review, split assignment, and split-leakage confirmation
all pass. `reject` and `needs_changes` never enable training. Data-flywheel
status reports now include a bounded `review_queue` sample, and the Message Hub
Dashboard/API can surface pending review samples/actions without exposing raw
candidate records, DB files, private coordinates, runtime JSONL logs, or raw
payload bytes. A bounded status report was generated as
`reports/data_flywheel/data005-review-queue-status-20260704/` and synced to the
VPS Dashboard; authenticated `/api/state` returned
`run_id=data005-review-queue-status-20260704`,
`status=needs_capture`, `pipeline_stage=candidate_store_missing`,
`review_queue.pending_records=0`, and actions
`approve_for_training,reject,needs_changes`. Deployment used
`scripts/deploy_message_hub_vps.ps1 -Public -IncludeFieldReportSummaries
-IncludeDataFlywheelSummaries`, restarted `egolink-message-hub.service`, and
did not modify GitLab. Validation passed: focused candidate-store/dashboard
tests (24 tests), `python scripts/context_lint.py`, `python -m py_compile
pc_simulator\training_candidate_store.py scripts\review_training_candidates.py
scripts\summarize_data_flywheel.py server\message_hub.py`, `git diff
--check`, and full `scripts\verify.ps1` (406 tests). This does not train a
model, export a dataset manifest, integrate a training server, change
firmware/protocol ingest, deploy on-device inference, or claim model
accuracy/power impact.

2026-07-04: FIELD-006 always-on D1 field readiness is implemented and
VPS-deployed. `/api/state` now includes `d1_link.field_readiness`, and the Web
Dashboard shows a first-glance `Field Ready` badge/card with readiness reason,
operator action, and freshness thresholds. The intended normal preflight for
the 2026-07-05 outdoor run is now: open `http://203.0.113.10:8790/`, confirm
`Field Ready ready` plus fresh `Upload Freshness`, then go test; companion
scripts remain optional for AMOLED sidecar recording/debug and post-run
evidence. Deployment used `scripts/deploy_message_hub_vps.ps1 -Public
-IncludeFieldReportSummaries -IncludeDataFlywheelSummaries`, restarted
`egolink-message-hub.service`, left the service systemd `enabled`, and did not
modify GitLab. Public checks passed: `/health` returned `ok=true`,
unauthenticated `/api/state` returned `401`, Dashboard HTML contained `Field
Ready`, `d1FieldReadyBadge`, and `field_readiness`, and authenticated
`/api/state` showed `ego-link-r1-connectivity-001` as
`field_readiness.state=ready`, `reason=fresh_periodic_upload`,
`freshness_s=16`, `operator_action=go_test`, latest upload at
`2026-07-04T13:18:41.428617+00:00`. Validation passed: focused dashboard tests
(13 tests), `python scripts/context_lint.py`, `python -m py_compile
server\message_hub.py`, `git diff --check`, and full `scripts\verify.ps1`
(401 tests). This does not change firmware/protocol/model behavior or claim
GNSS accuracy, battery life, calling/SMS, model readiness, or product
readiness.

2026-07-04: FIELD-005 D1 field-day post-run automation is implemented for the
planned 2026-07-05 outdoor/long-run shakedown. `scripts/prepare_d1_field_kit.py`
now emits `D1.field_kit.v3` kits with post-run Data Flywheel status generation
and Dashboard summary sync using both `-IncludeFieldReportSummaries` and
`-IncludeDataFlywheelSummaries`. FIELD-004 post-run commands now include D1 demo
report composition, data-flywheel status generation, and curated summary sync.
A concrete local kit was generated at
`reports/d1_field/FIELD-004-d1-outdoor-20260705/` with runbook, checklist,
notes template, and manifest. This does not contact hardware, flash firmware,
send Message Hub commands, train a model, or claim GNSS accuracy, battery life,
24h PWR-001 completion, calling/SMS, or product readiness.

2026-07-04: DATA-004 data flywheel control-plane baseline is implemented and
VPS-deployed.
Candidate-store status can now be summarized into bounded JSON/Markdown reports
with `scripts/summarize_data_flywheel.py`, and the Message Hub Dashboard/API can
surface the latest curated `reports/data_flywheel/**/data_flywheel_status.json`
summary through `/api/state` and `/api/v1/data-flywheel/latest`. The panel shows
candidate sessions/records, review queues, split-leakage pending counts,
training-readiness blockers, and the next data task without exposing raw
candidate records, DB files, runtime JSONL logs, raw payload bytes, or private
coordinates. `scripts/deploy_message_hub_vps.ps1 -IncludeDataFlywheelSummaries`
can sync only `data_flywheel_status.json/.md` summaries. This does not train a
model, mark records training-ready, change firmware/protocol ingest, integrate a
training server, deploy on-device inference, or claim model accuracy/power
impact. Deployment used `scripts/deploy_message_hub_vps.ps1 -Public
-IncludeFieldReportSummaries -IncludeDataFlywheelSummaries`, restarted
`egolink-message-hub.service` on `203.0.113.10:8790`, copied only curated field
and data-flywheel summaries, and did not modify GitLab. Public checks passed:
`/health` returned `ok=true`, unauthenticated `/api/state` returned `401`,
Dashboard HTML contained `Data Flywheel`, `dataFlywheelPanel`, and `D1 Link
Through`, authenticated `/api/state` included `data_flywheel`, and
`/api/v1/data-flywheel/latest` returned `available=true`,
`status=needs_capture`, `pipeline_stage=candidate_store_missing`,
`records_total=0`. Validation passed: focused candidate-store/dashboard tests
(16 tests), `python scripts/context_lint.py`, `python -m py_compile
pc_simulator\training_candidate_store.py scripts\summarize_data_flywheel.py
server\message_hub.py`, `git diff --check`, and full `scripts\verify.ps1`
(398 tests).

2026-07-04: DATA-003 training candidate store baseline is implemented. The
project now has a local SQLite candidate-store path from existing session
recordings plus annotations into bounded training-candidate records. The new
store lives behind `pc_simulator/training_candidate_store.py` and
`scripts/build_training_candidate_store.py`; it records source refs, labels,
privacy, consent, quality, split, and lineage fields, while keeping
`training_allowed=false` until a later review promotes records to
`reviewed_training_candidate`. The on-device AI/data flywheel route is now
documented in `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md` and linked
from the P0/V1 roadmaps. This does not train a model, change firmware, change
public contracts, retain raw private payload bytes, deploy on-device
inference, or claim model accuracy or battery impact. Validation passed:
focused candidate-store tests (4 tests), `python scripts/context_lint.py`,
`python -m py_compile` for the candidate-store module and CLI, and
`git diff --check`; full `scripts\verify.ps1` also passed (394 tests).

2026-07-04: UI-002 field-test result visibility is implemented and deployed.
The VPS Web Dashboard now has a `Field Test Results` panel after the D1 live
view, sourced from bounded report summary files rather than raw JSONL logs.
Authenticated `/api/state` includes `field_results`, and
`/api/v1/field-results/latest` exposes the latest curated report summaries for
current evidence review. Deployment used
`scripts/deploy_message_hub_vps.ps1 -Public -IncludeFieldReportSummaries`,
restarted `egolink-message-hub.service` on `203.0.113.10:8790`, copied only
curated D1 Web/API, D1 field companion, and AMOLED status summary/Markdown
files, and did not modify GitLab. Public checks passed: `/health` returned
`ok=true`, unauthenticated `/api/state` returned `401`, Dashboard HTML
contained the `Field Test Results`, `fieldResults`, `fieldResultsPanel`, and
`D1 Link Through` markers, and authenticated `/api/v1/field-results/latest`
returned `available=true`, `status=pass`, `report_count=3` for
`ui001-web-vps-20260704`,
`amoled004-companion-visible-vps-smoke-20260704`, and
`ui001-amoled-friendly-smoke-20260704`. Planning was updated with FIELD-004 as
the next 2-3 hour outdoor D1 run, followed by longer power baseline work and a
future optional map provider. This does not claim map-provider integration,
location accuracy, battery life, calling/SMS, or product readiness. Validation
passed: focused dashboard unit tests (8 tests), `python scripts/context_lint.py`,
`python -m py_compile server\message_hub.py`, and full `scripts\verify.ps1`
(390 tests).

2026-07-04: UI-001 field-friendly Web/AMOLED UI is implemented, VPS-deployed,
flashed, and smoke-tested. The Web Dashboard now puts `D1 Link Through` first
with a `Field live view`, `d1FieldOverview`, `d1StatusStrip`,
`d1FreshnessBadge`, and grouped location/uplink/power/evidence cards while
keeping the existing D1 markers and `/api/state` contract. The updated Message
Hub was deployed to `203.0.113.10:8790` with
`scripts/deploy_message_hub_vps.ps1`, restarted `egolink-message-hub.service`
on `0.0.0.0:8790`, and did not modify GitLab. Public checks passed:
`/health` returned `ok=true`, unauthenticated `/api/state` returned `401`,
Dashboard HTML contained the new UI markers, and read-only D1 Web/API gate
`ui001-web-vps-20260704` passed. Evidence:
`reports/d1_web_api/ui001-web-vps-20260704/d1_web_api_report.md`.
The AMOLED `display_status` page now renders `D1 FIELD` with `LINK`, `LOC`,
`PWR`, and `POST` rows; the sidecar payload is shortened for the small screen
and remains read-only against the Message Hub. ESP-IDF v5.4.2 build passed
(`egolink_amoled_safety_demo.bin` size `0xa0eb0`), flashing to `COM9` passed
for ESP32-S3 MAC `02:00:00:00:00:01`, and smoke
`ui001-amoled-friendly-smoke-20260704` passed with
`command_ack_count=1` and `status_rendered_count=1`. Evidence:
`reports/amoled_visible_status/ui001-amoled-friendly-smoke-20260704/ui001-amoled-friendly-smoke-20260704.summary.json`.
Validation passed: focused UI/AMOLED tests (17 tests), `python
scripts/context_lint.py`, `python -m py_compile server/message_hub.py`,
`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` (387 tests), and
the AMOLED ESP-IDF build. The Codex in-app browser was unavailable in this
session, so no screenshot evidence was captured. This does not claim GNSS
accuracy, battery life, USB-Free display acceptance, calling/SMS, or product
readiness.

2026-07-04: D1-002 outdoor field kit is updated for visible AMOLED companion
runs. `scripts/prepare_d1_field_kit.py` now generates a v2 offline kit with
read-only Web/API preflight, AMOLED `display_status` preflight, the preferred
`scripts/run_d1_field_companion.ps1` long-run command, and post-run Web/API,
power-curve, and D1 evidence report commands. A current kit was generated at
`reports/d1_field/d1-outdoor-kit-20260704/`; its manifest keeps the generator
offline-only and records voice calling and SMS as `unverified_not_implemented`.
The token value was not found in the generated kit. This does not contact
hardware, send commands, flash firmware, or claim GNSS fix, location accuracy,
battery life, calling, SMS, or product readiness.

2026-07-04: AMOLED-004 visible D1 status display fix is built, flashed, and
smoke-tested on the ESP32-S3-Touch-AMOLED-2.06 board. The sidecar runner now
sends `display_status` for field visibility, while the firmware keeps
`status_update` as a non-disruptive prompt status update and treats
`display_status` as a full-screen D1 status page switch. The serial command
buffer was raised to 1024 bytes to avoid truncating long field run IDs. ESP-IDF
v5.4.2 build passed (`egolink_amoled_safety_demo.bin` size `0x9cea0`), flashing
to `COM9` passed for ESP32-S3 MAC `02:00:00:00:00:01`, and smoke
`amoled004-companion-visible-vps-smoke-20260704` passed with AMOLED
`cmd=display_status`, `command_ack_count=1`, and `status_rendered_count=1`.
Evidence:
`reports/d1_field_companion/amoled004-companion-visible-vps-smoke-20260704/d1_field_companion_summary.json`.
This fixes the visible sidecar path only; it does not claim GNSS fix, location
accuracy, battery life, USB-Free display acceptance, or product readiness.

2026-07-04: AMOLED-003 D1 field companion runner is added and smoke-tested.
`scripts/run_d1_field_companion.ps1` starts the read-only D1 field observer and
the AMOLED D1 status sidecar with one shared run ID, sample count, and poll
interval, redirects child stdout/stderr to evidence files, waits for both
children, and writes one JSON/Markdown companion summary. VPS smoke
`amoled003-companion-vps-smoke5-20260704` passed on `COM9`: the observer child
reported one successful sample from `ego-link-r1-connectivity-001`, LTE
`registered_home/active`, raw POST `121 ok / 0 fail`, battery `100% / 4276mV`,
and `d1_coordinate_not_observed`; the AMOLED child returned `command_ack` and
`status_rendered` with the same D1 state. Evidence:
`reports/d1_field_companion/amoled003-companion-vps-smoke5-20260704/d1_field_companion_summary.json`.
This is a PC-connected field companion for live display while walking; it does
not claim USB-Free display acceptance, GNSS fix, location accuracy, battery
life, or product readiness.

2026-07-04: AMOLED-002 D1 status sidecar runner is added and smoke-tested.
`scripts/run_amoled_d1_status_sidecar.ps1` reads the Message Hub `/api/state`,
extracts the selected device `d1_link`, and sends a compact sidecar-only
`status_update` to the AMOLED USB Serial/JTAG port. It auto-detects the
Espressif VID/PID port, reads the token from `EGOLINK_MESSAGE_HUB_TOKEN` or the
local runtime token file without printing it, writes bounded JSONL/summary
evidence, and does not send Message Hub commands or contact the 4G board
serial port. VPS smoke `amoled002-d1-status-vps-smoke2-20260704` passed on
`COM9`: AMOLED returned `command_ack` and `status_rendered`; the rendered
payload summarized current D1 state as `estimate_visible`, LTE
`registered_home/active`, map `estimate_without_coordinate/no_fix`, battery
`87% / 4275mV`, and raw POST `99 ok / 0 fail / loc 21`. Evidence:
`pc_simulator/runtime/amoled_d1_status_sidecar/amoled002-d1-status-vps-smoke2-20260704.summary.json`.
This remains a PC-connected display sidecar and does not claim USB-Free field
acceptance, GNSS fix, location accuracy, or battery-life acceptance.

2026-07-04: AMOLED-001 screen interaction sidecar is flashed and smoke-tested
on the ESP32-S3-Touch-AMOLED-2.06 board. `firmware/amoled_safety_demo` now uses
the ESP-IDF `json`/cJSON component for serial downlink parsing, accepts
payload-driven `ask_user` prompts, and adds a sidecar-only `status_update` /
`display_status` screen for PC Bridge D1 status summaries without changing the
public Message Hub or 4G-board firmware contracts. The runner
`scripts/run_amoled_ask_user_demo.ps1 -SendStatusUpdate` can send a status page
before the safety prompt and records `status_rendered` in its summary. ESP-IDF
v5.4.2 build passed and produced
`firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin`, binary size
`0x9ce30`; flashing to AMOLED `COM9` passed, esptool detected ESP32-S3
USB-Serial/JTAG, PSRAM 8MB, MAC `02:00:00:00:00:01`, and verified hashes. The
bounded smoke `amoled001-sidecar-smoke2-20260704` passed over `COM9`:
`status_update -> command_ack/status_rendered` and
`ask_user -> command_ack/ask_user_rendered`. Evidence:
`pc_simulator/runtime/demo_v0_2/amoled001-sidecar-smoke2-20260704.summary.json`.
This is a screen/downlink render pass; it does not claim new touch acceptance,
formal IMU acceptance, D1 location accuracy, or battery-life acceptance.

2026-07-04: D1 live field observer is added for multi-hour outdoor shakedowns.
`scripts/observe_d1_field_run.py` polls the VPS Message Hub read-only, writes
JSONL samples plus JSON/Markdown summaries, and tracks freshness, raw POST
progress, LTE/cell state, GNSS coordinate visibility, and MAX17048 power
evidence without touching hardware or sending commands. Live smoke
`d1-live-observer-interval-smoke2-20260704` observed two samples over 70s:
freshness stayed below 180s, raw POST advanced `+2 ok / +0 fail`, and the only
warning was `d1_coordinate_not_observed`.

2026-07-04: D1 live LTE periodic upload is verified after SIM insertion and
cold boot. Read-only VPS checks against `203.0.113.10:8790` showed fresh
device data for `ego-link-r1-connectivity-001`: D1 gate
`d1-live-after-sim-coldboot-20260704` PASS, later poll at
`2026-07-04T08:43:03Z` saw `last_location_upload_at=2026-07-04T08:43:02Z`,
`freshness_s=1`, `raw_post_success_count=9`, `raw_post_failure_count=0`,
`location_event_count=13`, and `power_sample_count=6`. LTE was registered with
PDP active and MAX17048 power evidence was measured (`4276mV`, `92%` in the
gate report). GNSS still had no coordinate (`lat/lon=null`,
`map_surface.mode=estimate_without_coordinate`), and IMU evidence remains
mock/unverified on the 4G board. Evidence:
`reports/d1_web_api/d1-live-after-sim-coldboot-20260704/d1_web_api_report.md`.

2026-07-04: D1 periodic location firmware is prepared and flashed. The opt-in
`0.1.0-d1-periodic-location` mode keeps the LTE command-loop task alive and
periodically uploads a raw `location_report` plus `location_observation` pair
so the deployed Dashboard can refresh field data without manual
`request_location` commands. The local ESP-IDF build passed and produced
`firmware/mqtt_heartbeat/build_d1_periodic_verify/egolink_mqtt_heartbeat.bin`;
after explicit operator approval, flashing on `COM4` passed for ESP32-S3 MAC
`02:00:00:00:00:03` with bootloader/app/partition-table hashes verified and
hard reset completed. A read-only VPS D1 Web/API check after flashing still
showed the old 2026-07-02 location evidence and no latitude/longitude, so this
is a flash/build pass, not yet a live LTE upload pass, GNSS accuracy pass,
battery-life pass, or long LTE stability pass. Evidence:
`reports/d1_web_api/d1-live-after-flash-check-20260704/d1_web_api_report.md`.
Validation before flashing passed: focused D1 firmware/tool tests,
`context_lint`, progress-board generation, `git diff --check`, and full
`scripts\verify.ps1` (371 tests).

2026-07-04: D1 Dashboard/Web is deployed to the public VPS Message Hub at
`203.0.113.10:8790` without modifying GitLab. The read-only D1 Web/API gate
`d1-live-after-deploy-20260704` passed: Dashboard contains the
`D1 Link Through` panel markers and authenticated `/api/state` exposes
per-device `d1_link`, upload metrics, power curve, and GNSS/Cell-LTE/IMU/Power
component states. Current visible device data is still stale from
`2026-07-02T10:49:07Z`, has `map_surface.mode=estimate_without_coordinate`,
and has no latitude/longitude coordinate yet. This deploy did not contact
hardware, flash firmware, send device commands, or claim location accuracy or
battery life. Evidence:
`reports/d1_web_api/d1-live-after-deploy-20260704/d1_web_api_report.md`.

2026-07-04: D1 Web/API gate added. `scripts/validate_d1_web_api.py` performs
a read-only check of `/health`, `/api/state`, and Dashboard D1 markers for
location estimate, map surface, upload metrics, power curve, evidence
components, and non-claim boundaries. It writes JSON/Markdown reports and does
not contact hardware or send commands. Validation passed: focused D1
gate/message-hub tests, `context_lint`, progress-board generation,
`git diff --check`, and full `scripts\verify.ps1` (359 tests).

2026-07-04: D1 Dashboard metrics are extended. Per-device `d1_link` now
derives `uplink_metrics` and `power_curve` from recent Message Hub data:
server-received location uploads, raw POST success/failure counters when
present, power sample count, and voltage/SoC deltas. Dashboard shows Upload
Success, Location Uploads, Power Curve, and Power Delta without claiming
battery life. Validation passed: focused message-hub tests, `context_lint`,
progress-board generation, `git diff --check`, and full `scripts\verify.ps1`
(356 tests).

2026-07-04: D1 Web/API baseline is implemented. `/api/state` now returns
per-device `d1_link` from latest location evidence, and Dashboard shows
`D1 Link Through` with map surface, upload freshness, and GNSS/cell-LTE/IMU/
power evidence. Synthetic no-hardware fixture covers the API path; D1 operator
runbook is in the active task. No hardware, firmware, protocol, or VPS
behavior changed; no accuracy or battery-life pass is claimed. Validation
passed: focused message-hub tests, `context_lint`, progress-board generation,
`git diff --check`, and full `scripts\verify.ps1` (356 tests).

2026-07-04: NORTH_STAR is now the top project direction and current execution
is realigned to D1 link-through: 4G board + battery, periodic GNSS/cell/IMU/
power collection, LTE upload, server location estimate, Dashboard map visible.
Opened `D1-001`, kept `PWR-001` D1-critical, and paused `FIELD-003` until D2,
`MODEL-001` until D4-D5, and `PROD-001` until D1/founder inputs. No hardware,
firmware, protocol, or VPS behavior changed in this alignment slice.
Validation passed: `context_lint`, focused progress-board/model-doc tests, and
full `scripts\verify.ps1` (355 tests).

2026-07-04: MODEL-001 is opened as an active V1-M3 model footprint assessment
task, with the protocol baseline completed. `docs/modeling/MODEL_FOOTPRINT_ASSESSMENT.md`
now defines evidence levels from `protocol_defined` through
`candidate_compared`, minimum report fields for RAM, flash, latency, energy,
artifact identity, source status, known gaps, and evidence paths, plus the
rule that `TBD(MODEL-001)` production values must not be replaced until
reviewed measured evidence exists. `docs/generated/PROGRESS_BOARD.md` was
regenerated and now reports 4 active tasks and 76 completed tasks. This did
not train a model, add a model artifact, benchmark ESP32-S3, measure power,
select an MCU, change firmware/model behavior, change protocols/contracts, or
replace any PROD-001 `TBD(MODEL-001)` value. Validation passed: focused
MODEL-001 doc tests, `python scripts/context_lint.py`, `python
scripts/build_progress_board.py`, `git diff --check`, and full
`scripts\verify.ps1` (355 tests).

2026-07-04: DATA-002 is completed as a V1-M3 data-flywheel pipeline
specification. `docs/development/DATA_FLYWHEEL_PIPELINE.md` now defines the
path from session/test-run evidence to consented, privacy-reviewed
training-candidate records with consent, privacy class, retention/deletion,
lineage, labels, quality, and split-leakage fields. The default boundary stays
`training_allowed=false`, `raw_audio_allowed=false`, and
`raw_image_allowed=false`; Dashboard state is not a training source by itself.
This is a planning/contract slice only: no private data collection, model
training, training-candidate store, model registry, server rollout, device OTA,
firmware behavior, protocol behavior, or legal compliance certification changed.
Validation passed: focused DATA-002 doc tests, `python scripts/context_lint.py`,
`python scripts/build_progress_board.py`, `git diff --check`, and full
`scripts\verify.ps1` (351 tests). Current active V1 Wave 1 packets remain
`PWR-001`, `FIELD-003`, and `PROD-001`.

2026-07-03: PRIVACY-001 is completed as an engineering privacy boundary for
KR-008/V1 demos. `docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md` defines data
classes and default retention/export/training rules for GNSS coordinates,
cell/LTE signatures, Wi-Fi identifiers, IMU windows, user confirmations,
audio, image, guardian/contact data, VPS logs, and training/export artifacts.
`scripts/build_product_demo_report.py` now includes a
`privacy_boundary_review` gate. Raw audio/image retention remains disabled by
default, raw Wi-Fi identifiers are blocked, private coordinates remain
bounded evidence/export data, and product-demo training remains
`training_allowed=false` unless a future consent/privacy review explicitly
allows it. This is not a legal compliance certification. Validation passed:
focused product-demo report tests, `python scripts/context_lint.py`,
`git diff --check`, and full `scripts\verify.ps1` (347 tests). Current active
V1 Wave 1 packets are `PWR-001`, `FIELD-003`, and `PROD-001`.

2026-07-03: PWR-002 is completed as a design decision. ADR-0003 adopts
L0-L4 as an internal location power scheduler while keeping EALE-P0 public
location beliefs (`Fine`, `Coarse`, `Predicted`, `Unknown`) unchanged. The
decision adds required scheduler telemetry and safety boundaries, but makes
no firmware, protocol, battery-life, power-saving, or location-accuracy claim.
The task packet moved to `docs/tasks/done/`. Root-level review and research
inputs were archived under `docs/archive/reviews/` and
`docs/archive/research/` as historical input, not authority.

2026-07-03: OPS-001 VPS production hardening is completed directly on the
production host (root@203.0.113.10, SSH key auth, founder-authorized).
Installed: daily sqlite-consistent backup with 14-day retention
(`/usr/local/bin/egolink-backup.sh`, first archive
`egolink-20260703-194401.tar.gz`), 5-minute liveness check
(`/usr/local/bin/egolink-healthcheck.sh`; success freshness file + FAIL log
both verified, failure simulated against a dead port without touching the
service), journald capped at 500M (vacuumed 641M -> 496M). Restore drill
passed: `PRAGMA integrity_check=ok`, all 8 tables present. Runbook added at
`docs/operations/VPS_RUNBOOK.md`; scripts committed under `scripts/ops/`;
evidence under `reports/ops/OPS-001-20260703-001/`. The Message Hub service
itself was not modified, restarted, or redeployed. Remaining gaps recorded:
off-host backup copy, outbound alerting, TLS, root password rotation
(operator action). Same day, ENG-008 added the founder progress board
(`scripts/build_progress_board.py` -> `docs/generated/PROGRESS_BOARD.md`),
and PROD-001's requirements draft was delivered by the codex builder and
accepted by director review
(`docs/product/MASS_PRODUCTION_REQUIREMENTS.md`, awaiting founder
`TBD(founder)` values).

2026-07-03: ENG-007 governance re-baseline is applied. ADR-0002
(`ADR-0002-v1-ondevice-ai-companion-core.md`) records the founder decision
that on-device AI companion capability — real-time interaction and proactive
AI service — is a V1 core differentiator, with an edge-cloud hybrid
intelligence split and the on-device model track (M1 data foundation, formal
IMU acceptance, MotionNet v0.1, model footprint assessment) on the V1
critical path. A same-day earlier draft that deferred on-device ML to V2 was
explicitly retracted by the founder before commit and is recorded only in the
ADR's correction history. `docs/roadmap/V1_PRODUCT_PLAN.md` is now the
authoritative product sequencing document, and
`docs/development/DIRECTOR_WORKFLOW.md` replaces the retired
AutoDev/Dual-Codex workflows (documents archived under
`docs/archive/autodev/`). LTE-003 is closed as superseded by the FW-003
raw-frame path. V1 Wave 1 packets are active: OPS-001, PWR-001, FIELD-003,
PROD-001 (ENG-007 done). No firmware, protocol, server, or hardware behavior
changed; validation passed with `python scripts/context_lint.py` and
`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.

2026-07-03: DEMO-011 Product Demo Report Web Review Binding is implemented
after DEMO-010. `scripts/build_product_demo_report.py` now accepts
`--web-review-report`, binds a passing DEMO-010 Web/API review report into the
`web_console_replay_review` flow gate, records the evidence under
`source.web_review` and `evidence_summary.web_review`, and keeps
`ready_for_kr008_release=false` when release blockers remain. New tests in
`quality_tests/test_product_demo_report.py` verify both the old pending Web
behavior and the bound Web Review `pass` behavior. A DEMO-011 report was
generated under
`reports/product_demo/kr008-demo011-web-reviewed-20260703-001/` from the
existing LTE-011 fix1 export, the existing full demo safety summary, and
`reports/product_demo_web_review/demo010-vps-20260703-001/product_demo_web_review_report.json`.
The report has `flow_status_counts.pass=8`, Web Review `pass`, status `warn`,
and release readiness `false` because evidence is still composite, DATA-001
training readiness is false, location belief remains `Unknown`, and no KR-008
manifest has been created/promoted. The report directory was copied to the VPS
Message Hub report store only; no Message Hub code was deployed, no hardware
was contacted, no firmware was flashed, no device command was sent, and GitLab
was not modified. Follow-up read-only Web review gate
`demo011-vps-20260703-001` passed against `203.0.113.10:8790`, confirming the
Dashboard/API now show the DEMO-011 report path and Web Review `pass`.
Validation passed: focused product-demo/report/Web review tests,
`python scripts/context_lint.py`, `git diff --check`, and
`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` (334 tests).

2026-07-03: DEMO-010 Product Demo Web Review Gate is implemented as the
repeatable no-hardware gate after DEMO-009. New script
`scripts/validate_product_demo_web_review.py` checks `/health`,
`/api/v1/product-demo/latest`, `/api/state` Product Demo consistency,
Dashboard Product Demo markers, and the explicit KR-008 release boundary, then
writes `product_demo_web_review_report.json` / `.md`. New tests are in
`quality_tests/test_product_demo_web_review.py`. A read-only run against the
public VPS Message Hub at `203.0.113.10:8790` passed as
`demo010-vps-20260703-001`; it confirmed the current Product Demo report is
available through Web/API and Dashboard HTML, with status `warn`,
`evidence_mode=composite_existing_evidence`, and KR-008 release readiness
`false`. Evidence is under
`reports/product_demo_web_review/demo010-vps-20260703-001/`. This gate did
not send device commands, contact hardware, flash firmware, deploy to the VPS,
modify GitLab, regenerate same-run field evidence, create/promote a KR-008
manifest, or claim product readiness. Validation passed: `python -m unittest
quality_tests.test_product_demo_web_review -v`, `python -m unittest
quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server
quality_tests.test_product_demo_report -v`, `python scripts/context_lint.py`,
`git diff --check`, and `powershell -ExecutionPolicy Bypass -File
scripts\verify.ps1` (332 tests).

2026-07-02: DEMO-009 Product Demo Dashboard Review Baseline is implemented
locally after DEMO-008. Message Hub now summarizes the latest
`reports/product_demo/**/product_demo_report.json`; `/api/state` includes a
bounded `product_demo` summary; `/api/v1/product-demo/latest` returns the same
summary; and the Dashboard renders a Product Demo panel with KR-008/DEMO-008
candidate, result, release-readiness, evidence mode, test run, safety session,
location belief, GNSS state, flow-gate counts, Web Review status, raw/derived
evidence counts, dataset training readiness, report path, and warnings.
Missing reports are surfaced as explicit `not_available` state. Validation
passed: `python -m unittest quality_tests.test_message_hub_dashboard
quality_tests.test_message_hub_server quality_tests.test_product_demo_report
-v`, `python scripts/context_lint.py`, `git diff --check`, and
`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` (329 tests).
This is Web/API review support for the existing composite report only; it does
not contact hardware, modify GitLab, flash firmware, create/promote a KR-008
manifest, generate same-run field evidence, or claim product readiness, GNSS
acceptance, long LTE stability, real reconnect, durable store-forward,
battery/power behavior, enclosure behavior, learned model behavior, calling,
SMS, or dispatch.

2026-07-02: DEMO-009 was then deployed to the VPS Message Hub at
`203.0.113.10:8790` after commit `4145b84`. The deployment used the existing
message-hub deployment script and SSH key, restarted
`egolink-message-hub.service`, and copied the DEMO-008 report directory to
`/opt/egolink-message-hub/reports/product_demo/`. GitLab was not modified.
Public smoke checks passed: `/health` returned `ok=true`;
`/api/v1/product-demo/latest` returned `available=true`, `status=warn`,
candidate `KR-008 / DEMO-008 Product Demo Closed Loop`,
`evidence_mode=composite_existing_evidence`, and Web Review gate `not_run`;
`/api/state` returned `product_demo.status=warn`; and `/` returned HTTP 200
with Dashboard HTML containing the Product Demo panel. This makes the current
composite DEMO-008 report visible on the Web Dashboard, but it still is not a
KR-008 release or a same-run product demo.

2026-07-02: DEMO-008 Product Demo Closed Loop Report Baseline is implemented
as the first KR-008 product-demo composition artifact. New script
`scripts/build_product_demo_report.py` consumes an existing Message Hub
test-run export plus an optional full safety-demo summary and writes
`product_demo_report.json` / `.md` with supporting DATA-001 samples, DATA-001
manifest, and EALE-P0 evaluation reports. The first local report was generated
under `reports/product_demo/kr008-demo008-composite-20260702-001/` from the
KR-007/LTE-011 fix1 export and the existing full Demo v0.5 safety summary.
It is intentionally `WARN`, not a KR-008 release: seven flow gates pass, Web
console replay/review is pending, the evidence is composite rather than a
same-run product scenario, the location belief remains `Unknown` /
`gnss_no_fix`, and model training is not ready. Validation passed:
`python -m unittest quality_tests.test_product_demo_report
quality_tests.test_location_fusion_dataset_export
quality_tests.test_eale_p0_dataset_evaluation -v`, `python
scripts/context_lint.py`, `git diff --check`, and
`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` (326 tests).
This did not contact hardware, deploy to the VPS, modify GitLab, flash
firmware, create/promote a KR-008 manifest, or claim product readiness, Web
console completion, GNSS acceptance, long LTE stability, real reconnect,
durable store-forward, battery/power behavior, enclosure behavior, learned
model behavior, calling, SMS, or dispatch.

2026-07-02: KR-007 Reconnect Store-Forward Evidence Baseline is promoted to
released engineering key version `0.1.0-key-release-007`. The release binds
LTE-011 fix1 build/flash/runtime evidence, command `cmd-000033`, raw LTE
`location_report`, raw LTE `location_observation`, ACK, reconnect evidence,
store-forward evidence, the LTE-010 offline PASS report, and the KR-007
manifest gate. Promotion did not contact hardware or the VPS and does not
change the test-mode evidence boundary: no real modem reconnect recovery,
durable local storage, queue replay, long LTE stability, GNSS acceptance,
battery/power behavior, enclosure behavior, learned model behavior, or product
readiness is claimed.

2026-07-02: KR-007 Reconnect Store-Forward Evidence Baseline is created as
release candidate `0.1.0-key-release-007-rc1`. The manifest
`docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json`
binds the LTE-011 fix1 build/flash/runtime evidence, command `cmd-000033`, raw
LTE `location_report`, raw LTE `location_observation`, ACK, reconnect evidence,
store-forward evidence, and the LTE-010 offline PASS report. The release gate
passed using existing evidence only and did not contact hardware or the VPS;
the report is under `reports/key_releases/KR-007/`. KR-007 is a test-mode
evidence baseline; it does not prove real modem reconnect recovery, durable
local storage, queue replay, long LTE stability, GNSS acceptance, battery/power
behavior, enclosure behavior, learned model behavior, or product readiness.

2026-07-02: LTE-011 fix1 passed USB-Free runtime validation and the LTE-010
offline reconnect/store-forward evidence gate. The operator connected
independent power and disconnected USB, then validator run
`lte011-reconnect-store-forward-test-fix1-20260702-001` created
`request_location` command `cmd-000033`. The device returned raw LTE
`location_report` frame `loc-cmd-000033` (`seq=28`, `fix=false`,
`gnss_state=no_fix`), raw LTE `location_observation` frame `obs-cmd-000033`
(`seq=29`, `cell.cell_id=180571649`, `lte.reason_code=LTE_READY`, assigned IP
`10.55.187.235`, `transport.type=lte`), and raw LTE ACK `seq=30`
(`status=ok`, `LTE_HTTP_OK` / HTTP `200`). The observation carried LTE-011
test-mode reliability evidence: `network_reconnect_count=1`,
`network_last_reconnect_reason=pdp_reactivate`, network
`last_error=LTE_HTTP_ACTION_FAILED`, `cache_state=store_forward`,
`cache_queued_message_count=1`, `cache_oldest_message_age_ms=12000`, and
`cache_dropped_message_count=0`; the ACK reported post-reconnect
`network_state=ready_after_reconnect`, raw POST counters `2/2/0`, and cache
queue drained to `0`. Runtime evidence is under
`reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/`.
The offline LTE-010 gate over that export returned PASS for all five gates:
LTE runtime chain, reconnect attempt visibility, failure reason visibility,
post-reconnect ACK, and store-forward evidence. Gate report is under
`reports/lte_reconnect_store_forward/lte011-fix1-20260702-001/`. This is a
test-mode evidence pass and does not prove real modem reconnect recovery,
durable local storage, queue replay, long LTE stability, GNSS acceptance,
battery/power behavior, enclosure behavior, learned model behavior, or product
readiness.

2026-07-02: LTE-011 fix1 Observation Payload Margin was flashed on the
connectivity node through `COM4` after explicit operator confirmation. The
flash used firmware `0.1.0-lte011-reconnect-store-forward-test-fix1`, test run
`lte011-reconnect-store-forward-test-fix1-20260702-001`, commit/app version
`c110a5e`, binary
`firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test_fix1/egolink_mqtt_heartbeat.bin`
(`302528` bytes), and `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST=y`.
`esptool.py` detected ESP32-S3 QFN56 rev v0.2 on `COM4`, MAC
`02:00:00:00:00:03`, wrote bootloader/app/partition table, verified all
hashes, and hard-reset the board. Flash evidence is under
`reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/flash_report.md`.
USB-Free runtime validation later passed as recorded above; the flash evidence
itself does not prove real modem reconnect recovery, durable local storage,
queue replay, long LTE stability, GNSS acceptance, battery/power behavior,
enclosure behavior, learned model behavior, or product readiness.

2026-07-02: LTE-011 first USB-Free runtime validation produced an explainable
FAIL instead of a silent link failure. Validator command `cmd-000032` was
created for `lte011-reconnect-store-forward-test-20260702-001`; after an
operator-confirmed independent-power reboot with USB disconnected, the device
processed the command and uploaded raw LTE `location_report` frame
`loc-cmd-000032` (`seq=2`, `fix=false`, `gnss_state=no_fix`) plus raw LTE ACK
`seq=4`. The ACK reached the VPS over LTE HTTP with `LTE_HTTP_OK` / HTTP
`200`, but command status was `error` because the firmware-side
`location_observation` frame was never posted:
`cache_last_drop_reason=location_observation_payload_truncated`. Evidence is
under
`reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/`.
LTE-011 fix1 is build-verified as
`0.1.0-lte011-reconnect-store-forward-test-fix1` /
`lte011-reconnect-store-forward-test-fix1-20260702-001`; it only increases the
local raw LTE `location_observation` payload/frame buffers from `1750`/`2100`
bytes to `2050`/`2400` bytes. Focused firmware tests passed with 13 tests, and
the guarded ESP-IDF build produced
`firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test_fix1/egolink_mqtt_heartbeat.bin`
(`302528` bytes) with `flash_intentionally_not_run=true`. The fix1 image was
later flashed and USB-Free runtime validated as recorded above, but this still
does not prove real modem reconnect recovery, durable local storage, queue
replay, long LTE stability, GNSS acceptance, battery/power behavior, enclosure
behavior, learned model behavior, or product readiness.

2026-07-02: LTE-011 Reconnect Store-Forward Evidence Test Mode was flashed on
the connectivity node through `COM4` after explicit operator confirmation.
The flash used firmware `0.1.0-lte011-reconnect-store-forward-test`, test run
`lte011-reconnect-store-forward-test-20260702-001`, commit/app version
`3b3151d`, binary
`firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test/egolink_mqtt_heartbeat.bin`
(`302496` bytes), and `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST=y`.
`esptool.py` detected ESP32-S3 QFN56 rev v0.2 on `COM4`, MAC
`02:00:00:00:00:03`, wrote bootloader/app/partition table, verified all
hashes, and hard-reset the board. Flash evidence is under
`reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/flash_report.md`.
USB-Free runtime validation has not been run yet, so this does not prove the
LTE-010 gate, real modem reconnect recovery, durable local storage, queue
replay, long LTE stability, GNSS acceptance, battery/power behavior, enclosure
behavior, learned model behavior, or product readiness.

2026-07-02: LTE-011 Reconnect Store-Forward Evidence Test Mode is implemented
and build-verified as the next no-hardware slice after LTE-010. Firmware adds
default-off `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST`; when
enabled, raw LTE `location_observation` and ACK payloads can emit
reconnect/store-forward-shaped evidence fields including
`network_reconnect_count`, `network_last_reconnect_reason`,
`cache_state=store_forward`, and `cache_flush_*` counters. Build/runner
scripts expose `-EnableReconnectStoreForwardTest`. Message Hub raw KV
derivation now preserves `cache_flush_*` in `reliability.cache`, and the
Dashboard exposes Cache Flush. Focused firmware/script/server/dashboard tests
passed with 51 tests. Guarded ESP-IDF build passed with firmware
`0.1.0-lte011-reconnect-store-forward-test`, test run
`lte011-reconnect-store-forward-test-20260702-001`, binary
`firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test/egolink_mqtt_heartbeat.bin`
(`302496` bytes), and `flash_intentionally_not_run=true`. No firmware flash,
USB-Free runtime validation, VPS deployment, GitLab change, real modem
reconnect recovery, durable local storage, queue replay, long LTE stability,
GNSS acceptance, battery/power behavior, enclosure behavior, learned model
behavior, or product-readiness claim is changed.

2026-07-01: LTE-010 Reconnect Store-Forward Gate Baseline is implemented as a
non-hardware offline gate after KR-006. New script:
`scripts/validate_lte_reconnect_store_forward_gate.py`. The gate reads an
existing Message Hub `test_run_export.json` and requires LTE runtime/raw
evidence, reconnect attempt count and reason, concrete network/LTE/HTTP
failure reason, a later successful LTE ACK after reconnect evidence, and
observed store-forward queue/drop/age counters before returning PASS. Missing
reconnect/store-forward exercise returns WARN; claiming reconnect or
store-forward without enough evidence returns FAIL. Focused tests passed with
5 tests. Running the gate over
`reports/field_validation/lte009-raw-post-retry-fault-20260701-001/test_run_export.json`
returned expected `WARN`: LTE runtime evidence passed, reconnect gates were
`NOT_OBSERVED`, and store-forward remained WARN because current evidence is
`volatile_outbox`, not durable store-forward. Report is under
`reports/lte_reconnect_store_forward/lte009-raw-post-retry-fault-20260701-001/`.
This does not flash firmware, contact hardware, deploy to the VPS, implement
modem reconnect recovery, implement durable local storage, prove long LTE
stability, or change product-readiness.

2026-07-01: REL-008 promotes KR-006 Raw POST Retry Fault Injection Baseline
to released engineering key version `0.1.0-key-release-006`. KR-006 binds the
LTE-009 build, VPS fail-once smoke, COM4 flash, USB-Free runtime evidence, and
raw-frame export into a reusable release gate:
`docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json`.
The gate verifies that the LTE-009 runtime used independent power with USB
disconnected, created command `cmd-000031`, retained the first raw LTE
`location_report` frame `loc-cmd-000031` as
`parse_result.status=injected_failure` /
`RAW_POST_FAIL_ONCE_INJECTED`, accepted the same raw frame on retry as a
derived `location_report seq=27`, received raw LTE
`location_observation seq=28`, and completed raw LTE ACK `seq=29` with HTTP
`LTE_HTTP_OK` / `200`.
Local KR-006 report is under `reports/key_releases/KR-006/`. Validation
passed: `python scripts\run_key_release_gate.py --manifest
docs/current/key_releases/KR-006_RAW_POST_RETRY_FAULT_INJECTION.json --json`,
`python scripts/context_lint.py`, and `git diff --check`. This release does
not perform new flashing or runtime validation beyond the already recorded
LTE-009 evidence, and does not prove reconnect recovery, durable offline cache,
long LTE stability, GNSS acceptance, battery/power behavior, enclosure
behavior, learned model behavior, or product-readiness.

2026-07-01: LTE-009 Raw POST Retry Fault Injection was flashed on `COM4` and
passed the USB-Free hardware runtime gate after the operator connected
independent power and disconnected USB. The flash used firmware
`0.1.0-lte009-raw-post-retry-fault`, test run
`lte009-raw-post-retry-fault-20260701-001`, binary
`firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
(`301776` bytes), and the flash-time app version was `88945b9` because CMake
reran at current HEAD. Flash evidence is under
`reports/field_validation/lte009-raw-post-retry-fault-20260701-001/flash_report.md`.
The USB-Free validator created `cmd-000031` (`request_location`) at
`2026-07-01T13:37:05Z` and passed from `2026-07-01T13:37:04Z` to
`2026-07-01T13:37:19Z`. Runtime evidence is under
`reports/field_validation/lte009-raw-post-retry-fault-20260701-001/`,
including `lte_command_loop_report.json`, `lte_command_loop_report.md`,
`device_state.json`, `commands.json`, and `test_run_export.json`. The first raw
LTE `location_report` frame `loc-cmd-000031` was retained with
`parse_result.status=injected_failure` / `RAW_POST_FAIL_ONCE_INJECTED`; the
same frame then retried successfully and derived `location_report seq=27`.
The follow-up raw LTE `location_observation seq=28` reached the VPS with
`cell.cell_id=180571649`, LTE `reason_code=LTE_READY`, assigned IP
`10.13.10.229`, `location_belief.state=Unknown`,
`cache_retry_policy=single_retry_current_boot`, retry counters `1/1/0`, and
raw POST counters `2/1/1`. Raw LTE ACK `seq=29` completed `cmd-000031` as
`ok` with `transport.type=lte`, poll HTTP `LTE_HTTP_OK` / `200`, retry counters
`1/1/0`, and raw POST counters `3/2/1`. This validates the bounded current-boot
raw POST retry path for one injected first-POST failure. It does not prove
durable offline cache, reconnect recovery, long LTE stability, GNSS acceptance,
battery/power behavior, enclosure behavior, learned model behavior, or
product-readiness.

2026-07-01: LTE-009 release-gate tooling now has a reusable raw retry
validator. `scripts/validate_lte_command_loop.py` accepts
`--require-raw-post-fail-once`, which implies a command-scoped LTE
`location_report` and verifies the test-run raw-frame export contains a
retained `injected_failure` / `RAW_POST_FAIL_ONCE_INJECTED` frame followed by
a later `ok` retry-derived `location_report` for the same command.
`scripts/run_fw001_hw_r1.ps1` exposes the hardware-runner switch
`-RequireRawPostFailOnce`, so the eventual LTE-009 USB-Free hardware run can
be executed as a fixed gate rather than a manual Web inspection. Focused
validator/runner tests passed with 16 tests, and full `scripts\verify.ps1`
passed with 319 tests. The LTE-009 guarded ESP-IDF build was rerun after this
commit, producing the same binary path and size with app version `85d799a` and
`flash_intentionally_not_run=true`. This tooling-only update itself did not
perform firmware flash or hardware runtime validation; the later LTE-009 flash
and runtime pass are recorded above.

2026-07-01: LTE-009 Raw POST Retry Fault Injection is implemented and
build-verified as the next slice after LTE-008 fix1. Message Hub now supports
a test-only raw-ingest fail-once path: when a raw KV frame contains
`test_inject_raw_post_fail_once=true`, the first matching raw frame is
retained with `parse_result.status=injected_failure` and HTTP 503 is returned
without deriving a Web/API message; a repeated POST of the same frame is then
accepted and derived normally. Firmware adds default-off
`CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST`, and test builds add
the injection marker only to raw LTE `location_report` payloads so the
subsequent raw LTE `location_observation` can carry retry counters after the
first POST fails and retry succeeds. Build/runner scripts expose the explicit
`-EnableRawPostFailOnceTest` flag. Focused server/firmware/script tests passed
with 47 tests; `python scripts/context_lint.py` passed; `git diff --check`
passed with only Windows line-ending warnings. Guarded ESP-IDF build passed
with firmware `0.1.0-lte009-raw-post-retry-fault`, test run
`lte009-raw-post-retry-fault-20260701-001`, binary
`firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
(`301776` bytes), and `flash_intentionally_not_run=true`. The build enabled
SIM7670G GNSS, LTE status, raw LTE command loop, location observation,
`CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX=1`, and
`CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST=y`. After commit
`10e28fe`, the Message Hub was deployed to the VPS at `203.0.113.10:8790`
without touching GitLab. Public checks passed: `/health` returned OK,
unauthenticated `/api/state` returned `401`, and authenticated `/api/state`
returned current state. A VPS-local in-memory smoke using the deployed code
verified first POST HTTP `503` / `raw_post_fail_once_injected`, retained raw
status `injected_failure`, zero derived messages after the failed attempt, then
second POST success with one derived `location_report`; exported raw statuses
were `injected_failure` and `ok`. At that point LTE-009 firmware had not been
flashed or USB-Free runtime validated yet; the later flash and runtime pass are
recorded above. This build/deploy step did not prove durable offline cache,
reconnect recovery, long LTE stability, GNSS acceptance, battery/power
behavior, enclosure behavior, learned model behavior, or product-readiness.

2026-07-01: LTE-008 fix1 USB-Free runtime validation passed after the
operator connected independent power and disconnected USB. Validator command
`cmd-000030` (`request_location`) was created at
`2026-07-01T11:57:20Z`, selected by firmware, and completed `ok`. Raw LTE
`location_report seq=15` reached the VPS with
`fw_version=0.1.0-lte008-bounded-raw-retry-fix1`,
`test_run_id=lte008-bounded-raw-retry-fix1-20260701-001`,
`transport.type=lte`, `source=sim7670g_firmware_gnss`,
`gnss_state=no_fix`, and `fix=false`. Raw LTE
`location_observation seq=16` also reached the VPS with
`cell.cell_id=180571649`, `lte.reason_code=LTE_READY`, assigned IP
`10.13.10.229`, `location_belief.state=Unknown`,
`cache_state=volatile_outbox`, `cache_retry_policy=single_retry_current_boot`,
retry counters `0/0/0`, and raw POST counters `1/1/0`. Raw LTE ACK `seq=17`
reported `status=ok`, HTTP `LTE_HTTP_OK` / `200`, and ACK raw POST counters
`2/2/0`. Evidence is under
`reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/`,
including `lte_command_loop_report.json` and `lte_command_loop_report.md`.
This promotes LTE-008 fix1 to the current USB-Free runtime-validated
reliability visibility slice. It does not prove an actual retry-after-failure
case, durable offline cache, reconnect recovery, long LTE stability, GNSS
acceptance, battery/power behavior, enclosure behavior, learned model
behavior, or product-readiness.

2026-07-01: LTE-008 USB-Free runtime validation attempt 1 produced an
explainable FAIL after the operator connected independent power and
disconnected USB. Validator command `cmd-000029` was received and selected by
the device; raw LTE `location_report seq=4` reached the VPS, and raw LTE ACK
`seq=6` also reached the VPS with `transport.type=lte`, poll HTTP
`LTE_HTTP_OK` / HTTP `200`, and `command.parse_status=raw_command_selected`.
The command correctly ended as `error` because firmware reported
`lte raw location_observation upload failed`; ACK reliability showed
`cache_state=volatile_outbox`, `cache_retry_policy=single_retry_current_boot`,
raw POST `1/1/0`, `cache_dropped_message_count=1`, and
`cache_last_drop_reason=location_observation_payload_truncated`. Evidence is
under
`reports/field_validation/lte008-bounded-raw-retry-20260701-001/`. LTE-008
fix1 was then implemented as a firmware payload compaction: optional long
Wi-Fi/IMU/power reason lines were removed from raw LTE
`location_observation` while preserving source/evidence status, belief,
network, cache, and retry fields. Focused firmware/LTE tests passed with 20
tests, `python scripts/context_lint.py` passed, `git diff --check` passed, and
full `scripts/verify.ps1` passed with 316 tests. Guarded ESP-IDF build passed
with firmware
`0.1.0-lte008-bounded-raw-retry-fix1`, test run
`lte008-bounded-raw-retry-fix1-20260701-001`, binary
`firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry_fix1/egolink_mqtt_heartbeat.bin`
(`301680` bytes), and `flash_intentionally_not_run=true`. LTE-008 fix1 was
then flashed on `COM4` after explicit operator confirmation. `esptool.py`
detected ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, wrote bootloader,
app (`301680` bytes), and partition table, verified hashes, and hard-reset the
board. Flash evidence is under
`reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/flash_report.md`.
LTE-008 fix1 was later USB-Free runtime validated as recorded above. No GitLab
change, durable offline cache, reconnect recovery, long LTE stability, GNSS
acceptance, battery/power behavior, enclosure behavior, learned model
behavior, or product-readiness claim is changed.

2026-07-01: LTE-008 Bounded Raw POST Retry Observability is implemented as a
firmware/server-Web build-verified increment after LTE-007. Firmware raw LTE
`location_report`, `location_observation`, and ACK uploads now share a bounded
raw POST helper with default
`CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX=1`, so one failed
raw-frame LTE HTTP POST is retried once within the current boot before final
drop accounting. Raw POST attempt/success/failure counters now count individual
HTTP attempts, while `cache_dropped_message_count` increments only after frame
build failure or after the bounded retry policy is exhausted. Raw LTE
`location_observation` and raw LTE ACK payloads now include
`cache_retry_policy=single_retry_current_boot`,
`cache_retry_attempt_count`, `cache_retry_success_count`, and
`cache_retry_failure_count`. Message Hub derives these raw KV fields into
`reliability.cache`, and the Dashboard exposes Cache Retry in current-run and
latest-field-state views. Focused firmware/server/dashboard/LTE tests passed
with 42 tests. Guarded ESP-IDF build passed with firmware
`0.1.0-lte008-bounded-raw-retry`, test run
`lte008-bounded-raw-retry-20260701-001`, binary
`firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry/egolink_mqtt_heartbeat.bin`
(`301824` bytes), and `flash_intentionally_not_run=true`. Message Hub/Web was
redeployed to `203.0.113.10:8790` without modifying GitLab; public `/health`
returned `ok=true`, unauthenticated `/api/state` returned HTTP 401, the public
Dashboard HTML contained `Cache Retry`, `egolink-message-hub.service` remained
`active`, and the existing GitLab service remained `active`. LTE-008 was then
flashed on `COM4` after explicit operator confirmation. `esptool.py` detected
ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, wrote bootloader, app
(`301824` bytes), and partition table, verified all hashes, and completed
hard reset. Local flash evidence is under
`reports/field_validation/lte008-bounded-raw-retry-20260701-001/flash_report.md`.
USB-Free runtime validation remains pending. No GitLab change, durable offline
cache, reconnect recovery, long LTE stability, GNSS acceptance,
battery/power behavior, enclosure behavior, learned model behavior, or
product-readiness claim is changed.

2026-07-01: LTE-007 USB-Free runtime validation passed after the operator
rebooted the connectivity node on independent power with USB disconnected.
The first LTE-007 runtime command `cmd-000027` passed the raw LTE
`request_location -> location_report -> location_observation -> ACK` loop.
The Message Hub/Web was then updated and redeployed to `203.0.113.10:8790`
without modifying GitLab so raw KV fields
`network_raw_post_attempt_count`, `network_raw_post_success_count`,
`network_raw_post_failure_count`, and `cache_*` derive into
`reliability.network/cache` and Dashboard `Raw POST` visibility. Public
`/health` returned `ok=true`, unauthenticated `/api/state` returned HTTP 401,
and the existing GitLab service remained `active`. After a second
independent-power reboot, existing command `cmd-000028` reconciled PASS with
raw LTE `location_report seq=2`, raw LTE `location_observation seq=3`, and
raw LTE ACK `seq=4`. Runtime observation showed LTE `LTE_READY`, cell ID
`180571649`, assigned IP `10.7.108.215`, `location_belief.state=Unknown`,
`reliability.network.raw_post_attempt_count=1`,
`raw_post_success_count=1`, `raw_post_failure_count=0`,
`reliability.cache.state=volatile_outbox`,
`cache_source_status=observed`, `cache_queued_message_count=0`,
`cache_dropped_message_count=0`, and `cache_last_drop_reason=none`; ACK
reported raw POST `2/2/0`. LTE-005 over the LTE-007 export now has G6
`PASS` and overall expected `WARN` only because sequence reset/duplicate
visibility remains visible across the reboot/retry window. Validation passed:
focused Message Hub/Dashboard/LTE tests passed with 29 tests; LTE-007
USB-Free runtime validation passed; LTE-005 gate returned expected `WARN`
with no errors; `python scripts/context_lint.py` passed; `scripts\verify.ps1`
passed with 316 tests; and `git diff --check` passed. No durable offline
cache, reconnect recovery, long LTE stability, GNSS acceptance, battery/power
behavior, enclosure behavior, learned model behavior, or product-readiness
claim is changed.

2026-07-01: LTE-007 was flashed on `COM4` after explicit operator
confirmation. The flashed image is
`0.1.0-lte007-volatile-cache-observe` /
`lte007-volatile-cache-20260701-001`, built from commit `e6f70cf`, with binary
`firmware/mqtt_heartbeat/build_lte007_volatile_cache_observe/egolink_mqtt_heartbeat.bin`
(`301056` bytes). `esptool.py` detected ESP32-S3 QFN56 rev v0.2, MAC
`02:00:00:00:00:03`, wrote bootloader, app, and partition table, verified all
hashes, and completed hard reset. Local flash evidence is under
`reports/field_validation/lte007-volatile-cache-20260701-001/flash_report.md`.
USB-Free runtime validation is still pending operator independent-power and
USB-disconnect confirmation. No VPS deployment, GitLab change, durable offline
cache, reconnect recovery, long LTE stability, GNSS acceptance, battery/power
behavior, enclosure behavior, learned model behavior, or product-readiness
claim is changed.

2026-07-01: LTE-007 Volatile Cache Drop Observability is implemented as a
firmware/static-build increment after KR-005. The raw LTE
`location_observation` and raw LTE ACK payloads now report current-boot raw
outbox counters: `network_raw_post_attempt_count`,
`network_raw_post_success_count`, `network_raw_post_failure_count`,
`cache_state=volatile_outbox`, `cache_source_status=observed`,
`cache_queued_message_count=0`, `cache_dropped_message_count`,
`cache_oldest_message_age_ms=0`, and `cache_last_drop_reason`. LTE-005 now
recognizes observed volatile queue/drop counters as cache/drop observability
evidence without treating them as durable store-forward or reconnect recovery.
Focused firmware/LTE-gate tests passed with 19 tests; guarded ESP-IDF build
passed with firmware `0.1.0-lte007-volatile-cache-observe`, test run
`lte007-volatile-cache-20260701-001`, and binary
`firmware/mqtt_heartbeat/build_lte007_volatile_cache_observe/egolink_mqtt_heartbeat.bin`
(`301056` bytes); `scripts\verify.ps1` passed with 315 tests; and
`git diff --check` passed. No firmware flash, USB-Free runtime validation, VPS
deployment, GitLab change, durable offline cache, reconnect recovery, long LTE
stability, GNSS acceptance, battery/power behavior, enclosure behavior,
learned model behavior, or product-readiness claim is changed.

2026-07-01: REL-007 promotes KR-005 Reliability Explainability Preflight
Baseline to released engineering key version `0.1.0-key-release-005` after
LTE-006 fix1 USB-Free runtime validation. LTE-006 fix1 compacts the raw LTE
`location_observation` payload while preserving cell/LTE evidence, Wi-Fi/IMU/
power source-state labels, `reliability.network` fields, and explicit cache
non-claim fields. Build passed with firmware
`0.1.0-lte006-reliability-nonclaim-fix1`, test run
`lte006-reliability-nonclaim-fix1-20260701-001`, and binary
`firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim_fix1/egolink_mqtt_heartbeat.bin`
(`299824` bytes). COM4 flash passed after explicit operator confirmation.
USB-Free runtime validation passed after the operator connected independent
power and disconnected USB: command `cmd-000026` produced raw LTE
`location_report seq=60`, raw LTE `location_observation seq=61`, and raw LTE
ACK `seq=62`, all under the fix1 test run. The observation showed
`LTE_READY`, cell ID `180571649`, assigned IP `10.141.88.185`, Wi-Fi
`disabled` / `missing`, IMU `unverified` / `mock`, power `mock`, and
`location_belief.state=Unknown`. LTE-005 over the fix1 export returned
expected `WARN` because concrete cache/drop-message evidence remains absent.
KR-005 manifest now has all gates `PASS`; local report is under
`reports/key_releases/KR-005/`. Validation passed: focused KR/LTE/firmware
tests passed with 25 tests; `python scripts/context_lint.py` passed; guarded
ESP-IDF build passed; USB-Free runtime validation passed; LTE-005 fix1 runtime
gate returned expected `WARN`; `scripts\verify.ps1` passed with 314 tests; and
KR-005 release gate passed with no warnings; `git diff --check` passed. No VPS
deployment, GitLab change, durable offline cache, reconnect recovery, long LTE
stability, GNSS acceptance, battery/power behavior, enclosure behavior,
learned model behavior, or product-readiness claim is changed.

2026-07-01: REL-006 creates KR-005 Reliability Explainability Preflight
Baseline as a release-candidate gate after LTE-005, OBS-004, and LTE-006. New
manifest:
`docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json`.
KR-005 binds the LTE-005 offline reliability gate, OBS-004
`reliability.network/cache` observability surface, LTE-006 firmware-side raw
LTE `location_observation` network/cache non-claim fields, the local LTE-006
ESP-IDF build output, and the LTE-005 smoke report over the existing LOC-005A
export. The manifest intentionally marks LTE-006 USB-Free runtime as
`NOT_RUN` until explicit operator hardware confirmation. KR-005 is therefore a
release candidate, not a released engineering key version and not a runtime
reliability acceptance. Validation passed: focused KR/LTE/firmware tests
passed with 25 tests; `python scripts/context_lint.py` passed; LTE-005 smoke
over the existing LOC-005A export returned expected `WARN`; KR-005 gate passed
with one expected warning, `gate G5-LTE006-USB-FREE-RUNTIME is NOT_RUN`, and
wrote `reports/key_releases/KR-005/release_gate_report.json` plus
`reports/key_releases/KR-005/release_gate_report.md`;
`scripts\verify.ps1` passed with 314 tests; and `git diff --check` passed. No
firmware flash, USB-Free runtime validation, VPS deployment, GitLab change,
durable offline cache, reconnect recovery, long LTE stability, GNSS
acceptance, battery/power behavior, enclosure behavior, or product-readiness
claim is changed.

2026-06-30: LTE-006 Firmware-Side Reliability Non-Claim Observability is
implemented as a firmware/static-build increment after OBS-004. The raw LTE
`location_observation` KV payload now reports LTE network observability fields
(`network_mode=LTE`, `network_rssi`, `network_state`, and
`network_last_error`) plus explicit cache non-claim fields
(`cache_state=not_enabled`, `cache_source_status=unverified`, and
`cache_last_drop_reason=cache_not_enabled`). LTE-005 now distinguishes this
non-claim from concrete cache/drop-message evidence: `cache_state=not_enabled`
produces `cache_capability_not_enabled` and keeps
`G6_RECONNECT_CACHE_OBSERVABILITY` at `WARN` until real queue/drop counters or
store-forward state are observed. Focused firmware/LTE-gate tests passed with
18 tests; `python scripts/context_lint.py` passed; ESP-IDF build passed with
firmware version `0.1.0-lte006-reliability-nonclaim`, test run ID
`lte006-reliability-nonclaim-20260630-001`, binary
`firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim/egolink_mqtt_heartbeat.bin`
(`300496` bytes), and `flash_intentionally_not_run=true`; LTE-005 smoke over
the existing LOC-005A export wrote
`reports/lte_reliability/loc005a-source-states-20260630-001-lte006-smoke/`
and returned expected `WARN`; `scripts\verify.ps1` passed with 313 tests; and
`git diff --check` passed. No firmware flash, USB-Free runtime validation, VPS
deployment, raw-frame framing change, required protocol-field change, durable
offline cache, reconnect recovery, long LTE stability, GNSS acceptance,
battery/power behavior, enclosure behavior, or product-readiness claim is
changed.

2026-06-30: OBS-004 Reliability Observability Baseline is implemented as a
Server-Web/contract visibility increment after LTE-005. Message Hub now accepts
additive `reliability.network` and `reliability.cache` groups on JSON status,
event, and raw-frame-derived rows, and derives them into
`observability.reliability`, `run_context.reliability`, and the Dashboard. Raw
KV payloads can use normalized fields such as `network_reconnect_count`,
`network_last_error`, `network_last_reconnect_reason`,
`cache_queued_message_count`, `cache_dropped_message_count`,
`cache_last_drop_reason`, and `cache_oldest_message_age_ms`. Status/event
schemas now allow the optional `reliability` object. The Dashboard exposes
Network Reconnect, Network Error, Cache Queue, and Cache Drops rows in Run
Context and Latest Field State. Focused Message Hub/Dashboard/LTE gate/schema
tests passed with 31 tests; `python scripts/context_lint.py` passed;
`scripts\verify.ps1` passed with 312 tests; and `git diff --check` passed.
Running LTE-005 against the existing LOC-005A export still returns expected
`WARN` because real cache/drop-message evidence is not present in that export;
this task does not synthesize false cache evidence. No firmware, hardware, VPS
runtime, raw-frame framing, required protocol fields, DATA-001 schema, learned
model behavior, long LTE stability, reconnect recovery, cache durability, GNSS
acceptance, battery/power behavior, enclosure behavior, or product-readiness
claim is changed.

2026-06-30: LTE-005 LTE Reliability Gate Baseline is implemented as a
non-hardware offline release-gate/tooling increment after KR-004. New gate:
`scripts/validate_lte_reliability_gate.py`; focused tests:
`quality_tests/test_lte_reliability_gate.py`. The gate reads an existing
Message Hub `test_run_export.json` and checks command lifecycle visibility,
stale/pending command explanation, duplicate local execution guard fields, LTE
transport and LTE/HTTP reason-code evidence, failure/no-fix explanation,
reconnect/reset and cache/drop-message observability, raw-frame
hash/length/CRC retention, and sequence reset/duplicate visibility. Running it
against the current LOC-005A export wrote reports under
`reports/lte_reliability/loc005a-source-states-20260630-001/` and returned
`WARN`: command lifecycle, LTE transport, LTE/HTTP reason codes, duplicate
guard fields, no-fix explanation, and raw-frame retention are visible; stale
pending was not exercised; cache/drop-message observability is not present;
message sequence reset/duplicate behavior is visible and should be planned
into the later long-run gate. Focused LTE reliability/command-loop tests
passed with 13 tests, `python scripts/context_lint.py` passed,
`scripts\verify.ps1` passed with 311 tests, and `git diff --check` passed.
This is an offline preflight gate only: no firmware, hardware, VPS runtime,
protocol, raw-frame profile, DATA-001 schema, learned model behavior, long LTE
stability, reconnect recovery, GNSS acceptance, battery/power behavior,
enclosure behavior, or product-readiness claim is changed.

2026-06-30: REL-005 promotes KR-004 Multi-Source Explainable Location
Evidence Baseline from `release_candidate` to released engineering key version
`0.1.0-key-release-004`. The promotion uses the existing LOC-005A USB-Free
runtime evidence, KR-004 release gate, authenticated current-run EALE-P0
snapshot, and the ALG-002 offline DATA-001 coverage report. The KR-004
manifest now has `status=released`, includes ALG-002 evidence/report checks,
and keeps all non-claims intact. Promotion review result: LOC-005A remains
`Unknown` / `no_precise_fix`; DATA-001/ALG-002 report remains `warn` with one
retained `failure_window`, one `gnss_no_fix`, zero Fine candidates, and
`model_training_ready=false`; this is acceptable release-review evidence but
not a learned-model, positioning-accuracy, GNSS acceptance, LTE stability,
battery/power, or product-readiness claim. No firmware, hardware, raw-frame
profile, DATA-001 schema, Message Hub runtime behavior, or model behavior is
changed by this promotion.
The updated Message Hub/Web manifest was deployed to `203.0.113.10:8790`
without modifying GitLab. Public `/health` returned `ok=true`,
unauthenticated `/api/state` returned HTTP 401, authenticated
`/api/state.current_run.key_release` returned `KR-004` / `released` /
`0.1.0-key-release-004`, and authenticated
`/api/state.current_run.eale_p0` still reported `Unknown` /
`no_precise_fix`, dataset window `failure_window`, and
`training_allowed=false`. The existing GitLab service remained active.
Promotion validation passed: focused release/Web/ALG-002 tests passed with 30
tests, `python scripts/context_lint.py` passed, `scripts\verify.ps1` passed
with 307 tests, `git diff --check` passed, and the KR-004 release gate passed
with 7 gates and 18 JSON checks.

2026-06-30: ALG-002 EALE-P0 Dataset Coverage Evaluation is implemented as
an offline DATA-001 release-review increment after REL-004. New evaluator:
`scripts/evaluate_eale_p0_dataset.py`; focused tests:
`quality_tests/test_eale_p0_dataset_evaluation.py`. It reads DATA-001
`samples.jsonl` plus `manifest.json` and writes JSON/Markdown coverage reports
under ignored runtime/report storage `reports/location_fusion_eale/`. The
current LOC-005A export was converted to DATA-001 under
`reports/location_fusion_datasets/loc005a-source-states-20260630-001/` and
evaluated under
`reports/location_fusion_eale/loc005a-source-states-20260630-001/`. Result:
`warn`, with one retained `failure_window`, one `gnss_no_fix` failure mode,
one `Unknown` label state, raw-frame and derived-event lineage present,
cell/LTE/Wi-Fi/IMU/power feature groups present, zero Fine candidates, and
`model_training_ready=false`. Focused DATA-001/ALG-002 tests passed with 8
tests, `python scripts/context_lint.py` passed, `scripts\verify.ps1` passed
with 307 tests, `git diff --check` passed, and the KR-004 release gate still
passed after updating the next-gate review text. This is useful release-review
evidence, not a positioning-accuracy or model-training claim. No firmware,
hardware, VPS, raw-frame profile, DATA-001 schema, Message Hub runtime
behavior, learned model behavior, GNSS acceptance, LTE stability,
battery/power behavior, or product readiness claim is changed.

2026-06-30: REL-004 created the KR-004 Multi-Source Explainable Location
Evidence release-candidate gate. New manifest:
`docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json`.
The gate extends `scripts/run_key_release_gate.py` with JSON evidence
assertions, then checks LOC-005A runtime evidence and an authenticated VPS
`/api/state.current_run` EALE-P0 snapshot. The KR-004 gate passed with 6
manifest gates and 13 JSON checks; focused release/Web tests passed with 27
tests, `python scripts/context_lint.py` passed, `scripts\verify.ps1` passed
with 304 tests, and `git diff --check` passed. Report paths are
`reports/key_releases/KR-004/release_gate_report.json` and
`reports/key_releases/KR-004/release_gate_report.md`. The VPS Message Hub was
redeployed with the KR-004 manifest, and authenticated `/api/state.current_run`
now identifies `loc005a-source-states-20260630-001` as `KR-004` /
`release_candidate` by `firmware_test_run_id`; EALE-P0 remains `Unknown` /
`no_precise_fix`, dataset window remains `failure_window` /
`candidate_with_warnings`, and `training_allowed=false`. Public `/health`
returned `ok=true`, unauthenticated `/api/state` returned HTTP 401, and the
existing GitLab service remained active. This is a release-candidate gate only:
no firmware, hardware, raw-frame profile, DATA-001 schema, model behavior,
GNSS acceptance, LTE stability, reconnect recovery, battery/power behavior,
positioning accuracy, or product readiness claim is changed.

2026-06-30: ALG-001 Server Derived EALE-P0 Location Belief is implemented as
a Server-Web/report visibility increment after OBS-003 and LOC-005A.
`/api/state.current_run.eale_p0`, test-run export `run_context.eale_p0`, and
`observability_summary.eale_p0` now expose a conservative derived
`location_belief`, normalized source evidence, and dataset-window readiness.
The Dashboard Run Context now shows EALE-P0 state/substate/confidence bucket,
EALE reason, EALE failure reason, DATA-001 window type/status, training flag,
and quality flags. For the current LOC-005A shape, GNSS no-fix plus real
cell/LTE evidence remains `Unknown` with reason
`gnss_no_fix_cell_lte_observed_no_position_memory`; cell/LTE is not promoted
to a precise position, and Wi-Fi/IMU/power source states remain explicit
evidence/quality flags such as `wifi_disabled`, `imu_unverified`, and
`power_mock`. Focused Message Hub server/dashboard tests passed with 21 tests,
`python scripts/context_lint.py` passed, `scripts\verify.ps1` passed with 301
tests, and `git diff --check` passed. The updated Message Hub/Web was deployed
to `203.0.113.10:8790`; public `/health` returned `ok=true`, unauthenticated
`/api/state` returned HTTP 401, public `/` contained `EALE-P0`,
`EALE Reason`, `Dataset Window`, and `Quality Flags`, and authenticated
`/api/state.current_run.eale_p0` reported current run
`loc005a-source-states-20260630-001` as `Unknown` / `no_precise_fix`,
dataset window `failure_window` / `candidate_with_warnings`, and
`training_allowed=false`. Existing GitLab service remained active. This task
does not change firmware, device wire protocol, raw-frame profile, DATA-001
schema, key-release status, learned model behavior, LTE stability, GNSS
behavior, battery/power behavior, or product readiness.

2026-06-30: OBS-003 Current Run / Key Release / Failure Visibility is
implemented as a Server-Web/report observability increment after LOC-005A.
`/api/state` now includes top-level `current_run` with the current test-run ID,
device, firmware, key-release match or `unreleased` state, latest released
baseline, command/ACK summary, raw-frame summary, derived location summary,
failure state/reason, reason codes, and evidence counts. Test-run export now
includes top-level `run_context`, and `observability_summary` includes
`failure_summary` so report consumers and dataset tooling can reuse the same
classification as the Dashboard. The Dashboard now renders a `Run Context`
panel with Current Run, Key Release, Baseline, Firmware, Command Chain, Raw
Evidence, Derived Location, Failure State, Failure Reason, and Evidence
Counts. The deploy package now copies `docs/current/key_releases` so the VPS
service can derive key-release/baseline context without touching GitLab or
runtime secrets. Focused Message Hub server/dashboard tests passed with 20
tests, `python scripts/context_lint.py` passed, `git diff --check` passed with
only the existing PowerShell line-ending warning, and full
`scripts\verify.ps1` passed with 300 tests. The updated Message Hub/Web was
deployed to `203.0.113.10:8790` with the existing remote token preserved;
public `/health` returned `ok=true`, unauthenticated `/api/state` returned
HTTP 401, `/` returned HTTP 200 and contained the Run Context fields, and
authenticated `/api/state.current_run` reported
`loc005a-source-states-20260630-001` as `unreleased` against baseline
`KR-003`, command/ACK `cmd-000024` as `ok`, raw-frame parse status `ok`, and
failure reason `GNSS_NO_FIX`. Existing GitLab service remained active. This
task does not change firmware, device wire protocol, hardware state, GNSS
behavior, LTE stability, battery/power behavior, enclosure behavior, or
product readiness.

2026-06-30: LOC-005A Firmware-Side Observation Source States is implemented
as a static firmware/server/Web contract increment after KR-003. Raw LTE
`location_observation` now carries compact Wi-Fi, IMU, and power source-state
slots in KV/raw-frame form: Wi-Fi is explicitly `disabled` / `missing` in the
current LTE path, IMU is surfaced through `platform_imu` status including
mock/unverified labels, and power is surfaced through `platform_power` source
labels instead of a battery-accuracy claim. Message Hub derives these raw
fields into structured `wifi`, `imu`, and `power` groups, `/api/state`
observability exposes their `source_status` and `evidence_status`, and the
Dashboard displays those states in the latest field view. Focused
firmware/server/dashboard tests passed with 32 tests; full
`scripts\verify.ps1` passed with 299 tests; and the LOC-005A guarded ESP-IDF
build produced
`firmware/mqtt_heartbeat/build_loc005a_source_states/egolink_mqtt_heartbeat.bin`
(`300448` bytes) with `flash_intentionally_not_run=true`. The updated Message
Hub/Web code was deployed by copying `server/message_hub.py` to
`203.0.113.10:/opt/egolink-message-hub/server/message_hub.py` and restarting
`egolink-message-hub.service`; local and public `/health` checks returned
`ok=true`, and the existing GitLab service remained `active`. LOC-005A was
then flashed on `COM4` after explicit operator confirmation. Flash evidence is
recorded at
`reports/field_validation/loc005a-source-states-20260630-001/flash_report.md`:
`esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote bootloader, app
(`300448` bytes), and partition table, verified all hashes, and completed a
hard reset. After the operator rebooted the board on independent power with
USB disconnected, the reboot-aware validator reconciled existing
`cmd-000024` as PASS. Evidence is under
`reports/field_validation/loc005a-source-states-20260630-001/`, including
`lte_command_loop_report.md`, `lte_command_loop_report.json`,
`device_state.json`, `commands.json`, and `test_run_export.json`. Runtime
evidence: downlink raw command frame `cmd-000024`, raw LTE
`location_report` frame `loc-cmd-000024` (`seq=2`, `fix=false`,
`gnss_state=no_fix`, `gnss_query_ok=true`, `transport.type=lte`), raw LTE
`location_observation` frame `obs-cmd-000024` (`seq=3`,
`cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-96`,
`lte.reason_code=LTE_READY`, `location_belief.source=cell,lte,wifi,imu,power`,
`wifi.source_status=disabled`, `wifi.evidence_status=missing`,
`imu.source_status=unverified`, `imu.evidence_status=mock`,
`power.source_status=mock`, `power.evidence_status=mock`,
`transport.type=lte`), and raw LTE ACK frame `cmd-000024` (`seq=4`,
ACK status `ok`, command parse status `raw_command_selected`,
`LTE_HTTP_OK` / HTTP `200`, `poll_action_elapsed_ms=460`). No real Wi-Fi
fingerprinting, product-topology IMU validation, battery accuracy, long LTE
stability, enclosure behavior, or product readiness is claimed by this entry.

2026-06-30: KR-003 USB-Free Explainable LTE Location Observation Walking
Skeleton is released as engineering key version `0.1.0-key-release-003`.
The release freezes the LOC-004A raw LTE
`request_location -> location_report -> location_observation -> ACK` loop plus
the FIELD-002 reboot-aware arm/reboot/reconcile validator workflow. Manifest:
`docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json`.
Gate command
`python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json --json`
passed with 7 gates, 19 evidence items, 4 required commits, no errors, and no
warnings; report is under `reports/key_releases/KR-003/`. This is an
engineering key release only: no GNSS fix, cell-only positioning, learned
location fusion, long LTE stability, reconnect recovery, battery/power,
enclosure behavior, or product readiness is claimed.

2026-06-30: FIELD-002A reboot-aware validator USB-Free smoke passed on the
real LOC-004A connectivity-node firmware after the operator rebooted the board
on independent power with USB disconnected. The new FIELD-002 flow first
armed `cmd-000023` (`request_location`) under test run
`loc004a-reboot-aware-20260630-001`, then reconciled that same command with
`--existing-command-id cmd-000023`, `--evidence-since command-created`,
`--expected-ack-test-run-id loc004a-cell-observation-20260630-001`, and
`--expected-message-test-run-id loc004a-cell-observation-20260630-001`.
Result: PASS. Evidence is under
`reports/field_validation/loc004a-reboot-aware-20260630-001/`, including
`lte_command_loop_report.md`, `lte_command_loop_report.json`,
`device_state.json`, `commands.json`, and `test_run_export.json`.
Runtime evidence: raw `location_report` frame `loc-cmd-000023` (`seq=2`,
`fix=false`, `gnss_state=no_fix`, `gnss_query_ok=true`,
`transport.type=lte`), raw `location_observation` frame `obs-cmd-000023`
(`seq=3`, `cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-97`,
`lte.reason_code=LTE_READY`, assigned IP `10.31.138.19`,
`location_belief.state=Unknown`, `transport.type=lte`), and raw ACK frame
`cmd-000023` (`seq=4`, command/ACK status `ok`, `LTE_HTTP_OK` / HTTP `200`,
`poll_action_elapsed_ms=530`). This validates the reboot-aware validator
workflow on one real USB-Free command; it does not validate GNSS fix,
cell-only positioning, long LTE stability, reconnect recovery, battery/power,
enclosure behavior, or product readiness.

2026-06-30: FIELD-002 USB-Free Reboot-Aware Command Validator is implemented
as tooling for one-command-per-boot field slices. `scripts/validate_lte_command_loop.py`
now supports `--arm-only`, which creates or selects a command and writes an
`ARMED` report without waiting for runtime evidence, and
`--evidence-since command-created|validator-start|test-run-created`, defaulting
to `command-created` so an existing-command reconciliation can include raw
`location_report` / `location_observation` frames uploaded during a manual
USB-Free reboot before the validator process restarted. The validator also
adds `--expected-message-test-run-id` for cases where required
`location_report` / `location_observation` messages use the firmware image
test-run ID rather than the command batch ID. `scripts/run_fw001_hw_r1.ps1`
passes these through as `-ArmLteCommandOnly`, `-LteEvidenceSince`, and
`-ExpectedMessageTestRunId`.
Documentation in `docs/development/FIELD_TEST.md` and
`firmware/mqtt_heartbeat/README.md` now records the arm/reboot/reconcile flow.
Focused tests passed with 14 tests, `context_lint` passed, full
`scripts\verify.ps1` passed with 294 tests, and `git diff --check` passed
with only the existing PowerShell line-ending normalization warning. This is
tooling only: no firmware flash, real VPS command enqueue, hardware runtime
pass, long LTE stability, reconnect, battery/power, enclosure behavior, or
product readiness is claimed.

2026-06-30: LOC-004A USB-Free runtime evidence is reconciled as PASS after the
operator rebooted the connectivity node on independent power with USB
disconnected. The first validator-created command `cmd-000021` was still
pending when the reboot happened; after reboot the LOC-004A firmware consumed
that command and produced the full raw LTE chain: raw `location_report`
`loc-cmd-000021` (`seq=2`, `fix=false`, `gnss_state=no_fix`,
`gnss_query_ok=true`, `transport.type=lte`, `lte_http.phase=location_report`),
raw `location_observation` `obs-cmd-000021` (`seq=3`, `cell.rat=LTE`,
`cell.cell_id=180571649`, `cell.rsrp=-98`,
`lte.reason_code=LTE_READY`, assigned IP `10.91.147.246`,
`location_belief.state=Unknown`, `transport.type=lte`,
`lte_http.phase=location_observation`), and raw ACK `cmd-000021` (`seq=4`,
ACK status `ok`, message `firmware uploaded SIM7670G GNSS location_report and
cell location_observation`, `LTE_HTTP_OK` / HTTP `200`). Evidence is under
`reports/field_validation/loc004a-cell-observation-runtime-20260630-001/`,
including `validation_reconciliation.md`,
`validation_reconciliation.json`, and refreshed test-run export. A second
automatic validator attempt queued `cmd-000022` after the one-command-per-boot
firmware loop had already stopped; that stale command was server-side
cancelled as queue hygiene and is not counted as hardware evidence. This
validates the bounded USB-Free raw LTE
`request_location -> location_report -> location_observation -> ACK` slice;
it does not validate long LTE stability, reconnect recovery, cell-only
positioning, Wi-Fi/IMU/power fusion, battery/power behavior, enclosure
behavior, or product readiness.

2026-06-30: LOC-004A firmware was flashed on the connectivity node through
`COM4` after explicit operator confirmation. Flash used firmware version
`0.1.0-loc004a-cell-observation`, test run
`loc004a-cell-observation-20260630-001`, source/app commit `d9e4389`, and
binary
`firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`
(`298416` bytes, SHA256
`9D6E94A2DB1EAC435BAE4B65B88B8F7D7431EEECAA42C0008D271097ED1E68A9`).
`esptool.py` detected an ESP32-S3 QFN56 rev v0.2 on `COM4`, wrote bootloader,
app, and partition table, verified hashes, and completed hard reset. Flash
evidence is recorded at
`reports/field_validation/loc004a-cell-observation-20260630-001/flash_report.md`.
This entry records flash evidence only; USB-Free runtime validation for
`request_location -> location_report -> location_observation -> ACK` was
performed afterward and is recorded above.

2026-06-30: LOC-004A Real Cell Location Observation is implemented,
VPS-deployed, and build-verified as the next explainability increment after
KR-002. The Message Hub on `203.0.113.10:8790` was redeployed without touching
GitLab and now derives raw key/value `event_type=location_observation` frames
into structured `cell`, `lte`, `transport`, `lte_http`, and
`location_belief` fields after storing the original raw frame. Unknown
observations now preserve existing useful `location_memory` and can derive an
active `Predicted` belief with reason
`last_known_after_unknown_location_observation`. VPS synthetic smoke
`loc004a-vps-cell-observation-smoke-20260630-012442` passed with raw parse
status `ok`, derived `event_type=location_observation`, `cell.rat=LTE`,
`cell.cell_id=01AF23`, `lte.reason_code=LTE_READY`, `transport.type=lte`,
`location_belief.state=Unknown`, and redacted raw payload in export; evidence
is under
`reports/location_observation/loc004a-vps-cell-observation-smoke-20260630-012442/`.
Firmware version `0.1.0-loc004a-cell-observation` with test run
`loc004a-cell-observation-20260630-001` was guarded-build verified with
`CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y`,
`CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y`,
`CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y`, and
`CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y`; binary is
`firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`
(`298416` bytes). Focused firmware/server/validator/runner tests passed with
50 tests, `context_lint` passed, full `verify.ps1` passed with 292 tests,
`git diff --check` passed, and the guarded ESP-IDF prepare/build passed.
Flash and USB-Free runtime validation were performed afterward and are recorded
above. This does not claim cell-only positioning, learned known-place matching,
Wi-Fi/IMU/power fusion, long LTE stability, reconnect recovery,
battery/power behavior, enclosure behavior, or product readiness.

2026-06-30: KR-002 Location Memory And Explainable No-Fix Gate is implemented
as a release candidate and deployed to the VPS Message Hub at
`203.0.113.10:8790` without touching GitLab. The server now persists
`location_memory`, exposes `location_memory` and
`observability.location_memory` in `/api/state`, derives active
`observability.location_belief=Predicted` when the latest GNSS report is
no-fix but prior memory exists, and keeps the prior memory instead of erasing
it. VPS synthetic gate `location-memory-gate-kr002-20260630` passed with latest
report `fix=false` / `gnss_state=no_fix`, active belief `Predicted` /
`last_known_after_gnss_no_fix`, and memory `Fine`; report is under
`reports/location_memory/location-memory-gate-kr002-20260630/`. Focused
Message Hub/Dashboard/location-memory tests passed, `context_lint` passed,
full `scripts\verify.ps1` passed with 287 tests, `git diff --check` passed,
and the KR-002 release gate passed. This is a server/Web/API gate only; it does
not validate firmware-side multi-source collection, outdoor GNSS acceptance,
long LTE stability, reconnect recovery, battery/power behavior, enclosure
behavior, or product readiness.

2026-06-30: LTE-004 USB-Free runtime validation passed after the operator connected independent power and disconnected USB. Validator run `lte004-raw-lte-location-20260629-213717` ran from `2026-06-29T23:54:57.128649+00:00` to `2026-06-29T23:55:02.666656+00:00`, created `cmd-000020` (`request_location`), required a matching LTE `location_report`, and passed. Raw derived location evidence: `location_report seq=30`, raw frame `loc-cmd-000020`, `fw_version=0.1.0-lte004-raw-lte-location`, `transport.type=lte`, `lte_http.phase=location_report`, `source=sim7670g_firmware_gnss`, `source_status=unverified`, `gnss_query_ok=true`, `gnss_state=no_fix`, `fix=false`, and `location_request_cmd_id=cmd-000020`. Raw ACK evidence: `seq=31`, `transport.type=lte`, `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`, HTTP status `200`, `poll_action_elapsed_ms=560`, `command.parse_status=raw_command_selected`, command status `ok`, ACK status `ok`, and message `firmware uploaded SIM7670G GNSS location_report`. Evidence is under `reports/field_validation/lte004-raw-lte-location-20260629-213717/`, including `lte_command_loop_report.json`, `lte_command_loop_report.md`, `device_state.json`, `commands.json`, and `test_run_export.json`. This validates the bounded USB-Free raw LTE `request_location -> location_report -> ACK` thin slice; it does not validate real GNSS fix, long LTE stability, reconnect recovery, battery/power behavior, enclosure behavior, or product readiness.

2026-06-30: LTE-004 raw LTE request-location firmware was flashed on the connectivity node through `COM4` after explicit operator confirmation. Board probe evidence `reports/board_validation/20260630-075007/probe.md` identified `COM4` as the ESP32-S3 CH343 console for the Waveshare ESP32-S3-SIM7670G-4G connectivity node, with SIM7670G AT candidates `COM6` and `COM7` registered/attached. Flash used firmware version `0.1.0-lte004-raw-lte-location`, test run `lte004-raw-lte-location-20260629-213717`, source/app commit `1b1fd3a`, and binary `firmware/mqtt_heartbeat/build_lte004_raw_lte_location/egolink_mqtt_heartbeat.bin` (`296112` bytes). `esptool.py` detected ESP32-S3, wrote bootloader, app, and partition table, verified hashes, and completed hard reset. Flash evidence is recorded at `reports/field_validation/lte004-raw-lte-location-20260629-213717/flash_report.md`. Runtime validation was later performed and is recorded above.

2026-06-29: LTE-004 raw LTE request-location thin slice was implemented, VPS-deployed, and build-verified. The Message Hub on `203.0.113.10` was redeployed without touching GitLab and now derives `location_report` from stored raw `EGLK/1 type=event` key/value frames. VPS smoke `lte004-vps-raw-location-smoke-20260629-133701` posted a synthetic no-fix raw `location_report` for `ego-link-r0-lte004-raw-location-smoke`; parse status was `ok`, derived `event_type=location_report`, `fix=false`, `gnss_state=no_fix`, `transport.type=lte`, and `location_request_cmd_id=cmd-smoke-000001`. Firmware version `0.1.0-lte004-raw-lte-location` with test run `lte004-raw-lte-location-20260629-213717` was guarded-build verified with `CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y`, `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y`, and `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y`; binary is `firmware/mqtt_heartbeat/build_lte004_raw_lte_location/egolink_mqtt_heartbeat.bin` (`296112` bytes). Focused firmware/server/validator/runner tests passed with 36 tests, `context_lint` passed, full `verify.ps1` passed with 282 tests, `git diff --check` passed, and the guarded ESP-IDF prepare/build passed. Flash and runtime validation were performed afterward and are recorded above.

2026-06-29: RAW-LTE-REPEAT-001 is satisfied after a second operator-confirmed independent-power cold boot with USB disconnected. Attempt 2 used test run `raw-lte-repeat-001-a2-20260629-210939`, created `cmd-000019`, and passed from `2026-06-29T13:09:42.505682+00:00` to `2026-06-29T13:09:57.120125+00:00`. Evidence is under `reports/field_validation/raw-lte-repeat-001-a2-20260629-210939/`, including `lte_command_loop_report.json`, `lte_command_loop_report.md`, `device_state.json`, `commands.json`, and `test_run_export.json`. ACK evidence: `fw_version=0.1.0-fw003-raw-command-loop`, ACK `test_run_id=fw003-raw-command-loop-20260629-175608`, `cmd_id=cmd-000019`, `seq=7`, `transport.type=lte`, `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`, `lte_http.poll_status_code=200`, `lte_http.poll_action_elapsed_ms=680`, `command.parse_status=raw_command_selected`, `command.command_count=1`, command status `ok`, and ACK status `ok`. No firmware flash or USB runtime data path was used. Together with attempt 1 `raw-lte-repeat-001-a1-20260629-190720` / `cmd-000018`, this completes the short USB-Free raw LTE repeat gate; it still does not validate long LTE stability, reconnect recovery, battery/power behavior, enclosure behavior, or GNSS-over-LTE acceptance.

2026-06-29: RAW-LTE-REPEAT-001 attempt 1 passed as a short USB-Free raw LTE repeat after the operator cold-booted the connectivity node on independent power with USB disconnected. The initial validator run created `cmd-000018` and the raw ACK succeeded, but the run returned a false-negative FAIL because the validator compared the repeat attempt `test_run_id` (`raw-lte-repeat-001-a1-20260629-190720`) with the firmware build-time ACK `test_run_id` (`fw003-raw-command-loop-20260629-175608`). The validator was updated to support an explicit expected ACK `test_run_id`, then the same existing `cmd-000018` was rechecked without queueing a new command and passed. Evidence is under `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/`, including `validation_reconciliation.md`, `lte_command_loop_report.json`, and `lte_command_loop_report.md`. Reconciled ACK evidence: `fw_version=0.1.0-fw003-raw-command-loop`, `transport.type=lte`, `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`, `lte_http.poll_status_code=200`, `lte_http.poll_action_elapsed_ms=460`, `command.parse_status=raw_command_selected`, `command.command_count=1`, command status `ok`, and ACK status `ok`. No firmware flash or USB runtime data path was used for this repeat.

2026-06-29: OBS-002 deployed a raw-frame observability update to the VPS Dashboard. The Message Hub now renders a `Raw Frames` panel showing recent raw-frame direction/type, parse status, derived message type, frame ID, receive time, payload length, CRC, and parse reason while keeping raw payload bytes redacted. VPS deploy restarted `egolink-message-hub.service` on `0.0.0.0:8790` without touching GitLab. Smoke results: `/` returned HTTP 200 and included the Raw Frames panel; unauthenticated `/api/state` returned `401`; authenticated `/api/state` returned HTTP 200 with 8 redacted raw-frame records, latest frame `cmd-000017`, `parse_result.status=ok`, `derived_message_type=ack`, and `raw_payload.data_redacted=true`. Focused dashboard/server tests passed with 15 tests, full `verify.ps1` passed with 279 tests, `context_lint` passed, and `git diff --check` passed.

2026-06-29: FW-003 raw-frame LTE command-loop USB-Free runtime validation passed after the operator cold-booted on independent power with USB disconnected. Validator test run `fw003-raw-command-loop-20260629-175608` ran from `2026-06-29T10:08:20.082526+00:00` to `2026-06-29T10:08:25.462245+00:00`, created `cmd-000017` (`set_report_interval`), and observed the command become `ok`. The ACK was derived from raw-frame `ack.raw`: `fw_version=0.1.0-fw003-raw-command-loop`, `seq=5`, `transport.type=lte`, `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`, `lte_http.poll_status_code=200`, `lte_http.poll_action_elapsed_ms=450`, `command.parse_status=raw_command_selected`, `command.command_count=1`, and `duplicate_local_execution_prevented=false`. Evidence is under `reports/field_validation/fw003-raw-command-loop-20260629-175608/`, including `lte_command_loop_report.json`, `lte_command_loop_report.md`, `device_state.json`, `commands.json`, and `test_run_export.json`. This validates the USB-Free Message-First raw command/ACK loop; it does not validate long LTE stability, reconnect recovery, battery, power, enclosure, or GNSS-over-LTE behavior.

2026-06-29: FW-003 raw-frame LTE command-loop firmware was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-fw003-raw-command-loop`, test run ID is `fw003-raw-command-loop-20260629-175608`, source/app commit is `719c195`, and binary is `firmware/mqtt_heartbeat/build_fw003_raw_command_loop/egolink_mqtt_heartbeat.bin` (`286176` bytes). Flash evidence is under `reports/field_validation/fw003-raw-command-loop-20260629-175608/flash_report.md`. This is flash evidence only; runtime validation is recorded separately above.

2026-06-29: FW-003 raw-frame LTE command-loop firmware is implemented and build-verified. Firmware version is `0.1.0-fw003-raw-command-loop`, test run ID is `fw003-raw-command-loop-20260629-175608`, and binary is `firmware/mqtt_heartbeat/build_fw003_raw_command_loop/egolink_mqtt_heartbeat.bin` (`286176` bytes). The command-loop image now polls `GET /commands/poll.raw`, reads raw HTTP bodies without JSON brace extraction, verifies `EGLK/1` frame `len` and `crc32`, parses key/value command payloads, and posts raw ACK frames to `POST /commands/{cmd_id}/ack.raw`. The Message Hub was redeployed to the VPS at `203.0.113.10` after adding derived LTE evidence from raw ACK key/value fields; service restart succeeded without touching GitLab. Public smoke `fw003-raw-derived-smoke-20260629-175946` created `cmd-000016`, fetched it as `EGLK/1 type=command`, posted a raw ACK with `parse_result.status=ok`, updated the command to `ok`, and derived `ack.transport.type=lte`, `ack.lte_http.phase=command_ack`, and `ack.lte_http.poll_status_code=200`. Focused firmware/server tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 278 tests, `git diff --check` passed, and the guarded ESP-IDF prepare/build passed with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`. This build record was followed by the explicit `COM4` flash and USB-Free PASS recorded above.

2026-06-29: DEPLOY-002 deployed the SERVER-002 raw-frame Message Hub build to the VPS at `203.0.113.10` without modifying GitLab. `egolink-message-hub.service` restarted successfully, listens on `0.0.0.0:8790`, `/health` returned OK, unauthenticated `/api/state` returned `401`, and authenticated `/api/state` includes `raw_frames`. A public raw-frame smoke for device `ego-link-r0-raw-vps-smoke` and test run `raw-frame-vps-smoke-20260629-174047` created a harmless `set_report_interval` command, fetched it through `GET /commands/poll.raw` as an `EGLK/1` frame, posted `POST /commands/{cmd_id}/ack.raw`, stored two raw frame records with parse status `ok`, and updated the command status to `ok`. No token value, VPS password, private key, or private device log was committed or printed.

2026-06-29: SERVER-002 raw-frame ingest/storage is implemented locally and test-verified. The Message Hub now has a separate SQLite `raw_frames` table, `POST /api/v1/devices/{device_id}/raw-ingest`, `GET /api/v1/devices/{device_id}/raw-frames`, `GET /api/v1/devices/{device_id}/commands/poll.raw`, and `POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack.raw`. Raw frames are inserted first with `parse_result.status=not_attempted`, then parsed into status/command/ACK/error derived views where possible; checksum-failed and malformed frames remain stored with redacted API output. Focused server/contract tests passed locally. This is a server implementation baseline; VPS deployment is recorded separately in DEPLOY-002, and no firmware raw-frame slice or hardware validation has been performed yet.

2026-06-29: Protocol direction changed to raw-frame-first transport for the device/server runtime path. LTE-003 fix7/fix8 evidence showed that SIM7670G LTE HTTP can reach the VPS and receive a valid command-poll body, but device-side JSON body extraction/parsing remains too brittle for the product link. Task `PROTO-002 Raw Frame Transport Contract` defined `raw-frame.p0.v1`: the VPS stores original frame bytes before parsing, incomplete or malformed frames remain durable evidence, and existing `egolink.p0.v1` JSON status/event/command/ACK objects become derived Web/API compatibility views. LTE-003 is paused on the JSON command-poll path; the raw-frame ingest/storage plus raw command poll/ACK path later passed through SERVER-002, DEPLOY-002, and FW-003.

2026-06-29: LTE-003 fix8 is implemented and build-verified, but not flashed yet. Source/build app commit is `a87a754`, firmware version is `0.1.0-lte003-command-loop-fix8`, test run ID is `lte003-command-loop-fix8-20260629-170628`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix8/egolink_mqtt_heartbeat.bin` (`293216` bytes). Fix8 changes the SIM7670G HTTPREAD body extractor to wait for a complete brace-balanced JSON object, with string/escape awareness, before returning a JSON body; this targets fix7's `command.parse_status=json_parse_failed` failure where the valid 592-byte Message Hub response was likely truncated at an inner `payload` brace pair. Focused LTE/firmware tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 274 tests, `git diff --check` passed, and the guarded ESP-IDF prepare/build passed with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`. The physical board is still running fix7; fix8 remains available as legacy JSON diagnostic evidence, but it is no longer the default next step after the raw-frame protocol decision.

2026-06-29: LTE-003 fix7 USB-Free validation failed, but it made the command extraction blocker explicit. With independent power and USB disconnected, the validator reused pending `cmd-000013` for `lte003-command-loop-fix7-20260629-164429` from `2026-06-29T08:54:55Z` to `2026-06-29T09:00:56Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix7-20260629-164429/`. The test-run export contained 66 `lte_http_command_diag` messages from `2026-06-29T08:51:43Z` to `2026-06-29T09:00:55Z`: one `phase=ready` / `command.parse_status=not_polled`, then 65 `phase=poll_no_ack` with `command.parse_status=json_parse_failed`. The latest diagnostic showed `fw_version=0.1.0-lte003-command-loop-fix7`, `seq=66`, LTE `reason_code=LTE_READY`, registration `registered_home`, assigned IP `10.75.55.162`, HTTP poll status `200`, poll body length `592`, `lte_http.poll_reason_code=LTE_HTTP_OK`, `command.command_count=0`, and empty `command.last_cmd_id`. A PC-side Message Hub fetch confirmed the `/commands/poll` response is valid 592-byte JSON, so the next increment should make the firmware HTTPREAD body extractor wait for a complete JSON object instead of accepting the first partial brace pair.

2026-06-29: LTE-003 fix7 was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix7`, test run ID is `lte003-command-loop-fix7-20260629-164429`, source fix commit is `33b8503`, flashed repo/app version is `766f0d8`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix7/egolink_mqtt_heartbeat.bin` (`293104` bytes). Flash evidence is under `reports/field_validation/lte003-command-loop-fix7-20260629-164429/flash_report.md`. This is flash evidence only; USB-Free runtime validation has not been performed yet. Next step is independent power plus USB disconnected, followed by the LTE-003 validator.

2026-06-29: LTE-003 fix6 USB-Free validation failed, but it advanced the blocker from HTTPREAD body capture to command extraction/ACK. With independent power and USB disconnected, the validator reused pending `cmd-000013` for `lte003-command-loop-fix6-20260629-160859` from `2026-06-29T08:31:32Z` to `2026-06-29T08:37:33Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix6-20260629-160859/`. The test-run export contained 37 `lte_http_command_diag` messages from `2026-06-29T08:18:30Z` to `2026-06-29T08:23:32Z`: one `phase=ready` and 36 `phase=poll_no_ack`. The latest diagnostic showed `fw_version=0.1.0-lte003-command-loop-fix6`, `seq=37`, LTE `reason_code=LTE_READY`, registration `registered_home`, assigned IP `10.75.55.162`, HTTP poll status `200`, poll body length `592`, `lte_http.poll_reason_code=LTE_HTTP_OK`, and empty `command.last_cmd_id`. This means LTE, VPS, HTTPACTION, and HTTPREAD body capture are now healthy, but firmware still does not extract and ACK a command from the polled body. The next increment should add command parser diagnostics and a longer bounded poll window so validation is not dependent on catching the boot-time window.

2026-06-29: LTE-003 fix6 was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix6`, test run ID is `lte003-command-loop-fix6-20260629-160859`, source fix commit is `c1a90a0`, flashed repo/app version is `8d7395f`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/egolink_mqtt_heartbeat.bin` (`292512` bytes). Flash evidence is under `reports/field_validation/lte003-command-loop-fix6-20260629-160859/flash_report.md`. This is flash evidence only; USB-Free runtime validation has not been performed yet. Next step is independent power plus USB disconnected, followed by the LTE-003 validator.

2026-06-29: LTE-003 fix5 USB-Free validation failed with the same body-extraction blocker as fix4. With independent power and USB disconnected, the validator reused pending `cmd-000013` for `lte003-command-loop-fix5-20260629-154839` from `2026-06-29T07:58:34Z` to `2026-06-29T08:04:36Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix5-20260629-154839/`. The test-run export contained 37 `lte_http_command_diag` messages from `2026-06-29T07:54:20Z` to `2026-06-29T07:59:29Z`: one `phase=ready` and 36 `phase=poll_no_ack`. The latest diagnostic message showed `fw_version=0.1.0-lte003-command-loop-fix5`, `seq=37`, LTE `reason_code=LTE_READY`, registration `registered_home`, assigned IP `10.75.55.162`, HTTP poll status `200`, poll body length `592`, and `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. This means LTE, VPS, command poll HTTPACTION, and HTTPREAD AT-level acceptance remain healthy, but firmware still does not capture an extractable JSON body. The next increment should change HTTPREAD collection itself so it waits for the body content rather than relying on the generic AT helper's first `OK` match.

2026-06-29: LTE-003 fix5 was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix5`, test run ID is `lte003-command-loop-fix5-20260629-154839`, fix5 source commit is `729c78b`, flashed build app version/repo HEAD at flash is `efc9848`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin` (`291872` bytes). Flash evidence is under `reports/field_validation/lte003-command-loop-fix5-20260629-154839/flash_report.md`. This is flash evidence only; USB-Free runtime validation has not been performed yet. Next step is independent power plus USB disconnected, followed by the LTE-003 validator.

2026-06-29: LTE-003 fix5 is implemented and build-verified, but not flashed yet. Source/build app commit is `729c78b`, firmware version is `0.1.0-lte003-command-loop-fix5`, test run ID is `lte003-command-loop-fix5-20260629-154839`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin` (`291872` bytes). Fix5 keeps the fix4 positional `AT+HTTPREAD=0,<data_len>` attempt, but if that command returns `OK` without an extractable JSON body it continues to the bare `AT+HTTPREAD` fallback before reporting `LTE_HTTP_READ_BODY_PARSE_FAILED`. Focused LTE/firmware tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 274 tests, `git diff --check` passed, and the guarded ESP-IDF prepare/build passed with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`. The physical board is still running fix4; next step is reconnect USB and explicitly confirm COM4 flash for LTE-003 fix5.

2026-06-29: LTE-003 fix4 USB-Free validation failed, but it moved the blocker from AT-read failure to body extraction. With independent power and USB disconnected, the validator reused pending `cmd-000013` for `lte003-command-loop-fix4-20260629-084350` from `2026-06-29T07:38:00Z` to `2026-06-29T07:44:00Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix4-20260629-084350/`. The test-run export contained 37 `lte_http_command_diag` messages from `2026-06-29T07:33:18Z` to `2026-06-29T07:38:27Z`: one `phase=ready` and 36 `phase=poll_no_ack`. The latest diagnostic message showed `fw_version=0.1.0-lte003-command-loop-fix4`, `seq=37`, LTE `reason_code=LTE_READY`, registration `registered_home`, assigned IP `10.75.55.162`, HTTP poll status `200`, poll body length `592`, and `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. This confirms fix4 did not pass LTE-003 command ACK, but it proved the positional `AT+HTTPREAD=0,<data_len>` path can return at the AT layer. The next firmware increment should not change LTE registration or VPS behavior; it should fall back to bare `AT+HTTPREAD` when positional HTTPREAD returns `OK` without an extractable JSON body, or add bounded raw-read diagnostics if that still fails.

2026-06-29: LTE-003 fix4 was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix4`, test run ID is `lte003-command-loop-fix4-20260629-084350`, fix4 source commit is `c8e1f59`, flashed build app version/repo HEAD at flash is `b4eaa44`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin` (`291872` bytes). Flash evidence is under `reports/field_validation/lte003-command-loop-fix4-20260629-084350/flash_report.md`. This is flash evidence only; USB-Free runtime validation has not been performed yet. Next step is independent power plus USB disconnected, followed by the LTE-003 validator.

2026-06-29: LTE-003 fix4 is implemented and build-verified, but not flashed yet. Source/build app commit is `c8e1f59`, firmware version is `0.1.0-lte003-command-loop-fix4`, test run ID is `lte003-command-loop-fix4-20260629-084350`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin` (`291872` bytes). Fix4 changes command-poll GET body retrieval to try bounded positional `AT+HTTPREAD=0,<data_len>` first, fall back to bare `AT+HTTPREAD`, and split failed AT reads into `LTE_HTTP_READ_AT_ERROR` versus `LTE_HTTP_READ_AT_TIMEOUT` while preserving `LTE_HTTP_READ_BODY_PARSE_FAILED`. Focused LTE/firmware tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 274 tests before the compile-order amend, post-amend focused tests and `context_lint` passed again, `git diff --check` passed, and the guarded ESP-IDF prepare/build passed with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`. The physical board is not yet flashed with fix4; next step is reconnect USB and explicitly confirm COM4 flash.

2026-06-29: LTE-003 fix3 USB-Free validation failed, but it narrowed the blocker to the SIM7670G `AT+HTTPREAD` command path. With independent power and USB disconnected, the validator reused pending `cmd-000013` for `lte003-command-loop-fix3-20260629-081529` from `2026-06-29T00:26:51Z` to `2026-06-29T00:32:53Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix3-20260629-081529/`. The test-run export contained 59 `lte_http_command_diag` messages from `2026-06-29T00:22:45Z` to `2026-06-29T00:31:02Z`: two `phase=ready` and 57 `phase=poll_no_ack`. The latest diagnostic message showed `fw_version=0.1.0-lte003-command-loop-fix3`, `seq=37`, HTTP poll status `200`, poll body length `592`, and `lte_http.poll_reason_code=LTE_HTTP_READ_AT_FAILED`. This confirms fix3 did not pass LTE-003 command ACK, but it made the failure more specific: the firmware reaches LTE, reaches the VPS, and gets a 200 poll body length, then fails to get a usable `AT+HTTPREAD` response. The next useful step is not another timeout-only retry; it should change the HTTPREAD strategy, likely by trying a bounded `AT+HTTPREAD=0,<data_len>` form or adding raw read-result diagnostics.

2026-06-29: LTE-003 fix3 was flashed on `COM4` after explicit operator confirmation. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix3`, test run ID is `lte003-command-loop-fix3-20260629-081529`, fix3 code-change commit is `e79e4de`, flashed build app version/repo HEAD at flash is `79a12c8`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin` (`291488` bytes). Flash evidence is under `reports/field_validation/lte003-command-loop-fix3-20260629-081529/flash_report.md`. This is flash evidence only; USB-Free runtime validation has not been performed yet. Next step is independent power plus USB disconnected, followed by the LTE-003 validator.

2026-06-29: LTE-003 fix3 diagnostic firmware was committed and build-verified before flash. Source code-change commit is `e79e4de`, firmware version is `0.1.0-lte003-command-loop-fix3`, test run ID is `lte003-command-loop-fix3-20260629-081529`, and binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin` (`291488` bytes). The guarded prepare/build passed with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=1`; focused LTE/firmware tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 274 tests, and `git diff --check` passed.

2026-06-29: LTE-003 fix2 USB-Free validation failed in an explainable way after the operator cold-booted the independently powered board with USB disconnected. The validator reused pending `cmd-000013` for `lte003-command-loop-fix2-20260629-074709` from `2026-06-28T23:58:07Z` to `2026-06-29T00:04:07Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix2-20260629-074709/`. The test-run export contained 51 `lte_http_command_diag` messages from `2026-06-28T23:55:12Z` to `2026-06-29T00:02:30Z`: two `phase=ready` and 49 `phase=poll_no_ack`. The latest diagnostic message showed `fw_version=0.1.0-lte003-command-loop-fix2`, `seq=37`, HTTP poll status `200`, poll body length `592`, and `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`. This means LTE, the VPS path, and the command-poll HTTP action are working, but firmware still fails to retrieve or parse the SIM7670G `HTTPREAD` body. Fix3 was build-verified to use the longer HTTP action timeout for `AT+HTTPREAD` and split the failure into `LTE_HTTP_READ_AT_FAILED` versus `LTE_HTTP_READ_BODY_PARSE_FAILED`.

2026-06-29: LTE-003 fix2 was rebuilt after commit so the build app version is `43f5f55`, then flashed on `COM4`. ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Firmware version is `0.1.0-lte003-command-loop-fix2`, test run ID is `lte003-command-loop-fix2-20260629-074709`, and flash evidence is under `reports/field_validation/lte003-command-loop-fix2-20260629-074709/flash_report.md`. The later USB-Free runtime validation failed as recorded above.

2026-06-29: LTE-003 fix1 runtime validation failed, but produced useful diagnostics. The validator reused pending `cmd-000013` for `lte003-command-loop-fix1-20260628-223454` from `2026-06-28T23:38:11Z` to `2026-06-28T23:44:13Z`; the command remained `pending` and no ACK was received. Evidence is under `reports/field_validation/lte003-command-loop-fix1-20260628-223454/`. The test-run export also contained 37 earlier `lte_http_command_diag` messages from `2026-06-28T23:25:04Z` to `2026-06-28T23:30:02Z`, before the validator wait window: one `phase=ready` and 36 `phase=poll_no_ack`. The latest diagnostic message showed `fw_version=0.1.0-lte003-command-loop-fix1`, `lte.reason_code=LTE_READY`, `transport.type=lte`, HTTP poll status `200`, poll body length `592`, and `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`. This points to firmware failing to read/parse the SIM7670G `HTTPREAD` response, likely because the component AT response buffer was still `512` bytes. Fix2 increases `AT_RESPONSE_BUFFER_SIZE` to `1536`; focused LTE/firmware tests passed with 24 tests, `context_lint` passed, full `verify.ps1` passed with 274 tests, and the guarded prepare/build passed for `0.1.0-lte003-command-loop-fix2` / `lte003-command-loop-fix2-20260629-074709`; binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix2/egolink_mqtt_heartbeat.bin`. Fix2 is not flashed yet and still requires explicit operator confirmation for `COM4`.

2026-06-29: LTE-003 fix1 is implemented, build-verified, and flashed on `COM4`, but not USB-Free runtime validated yet. Fix1 adds compact `lte_http_command_diag` telemetry over SIM7670G LTE HTTP POST before/after command polling and increases `lte_http_command_task` stack from `12288` to `16384`, while keeping ACK acceptance unchanged. Focused tests passed with 29 tests, `context_lint` passed, full `verify.ps1` passed with 273 tests, and the guarded prepare/build passed for `0.1.0-lte003-command-loop-fix1` / `lte003-command-loop-fix1-20260628-223454`; binary is `firmware/mqtt_heartbeat/build_lte003_command_loop_fix1/egolink_mqtt_heartbeat.bin`. The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte003-command-loop-fix1-20260628-223454/flash_report.md`. USB-Free runtime validation has not been performed yet.

2026-06-28: LTE-003 USB-Free validation attempt 2 also failed after the operator performed an independent-power cold reboot with USB still disconnected. The validator reused the existing pending `cmd-000013` with `--existing-command-id cmd-000013` and waited from `2026-06-28T14:21:51Z` to `2026-06-28T14:27:53Z`; the command remained `pending`, no ACK was received, and the test-run export again contained zero messages. VPS device state still showed the prior LTE-002 fix5 `lte_http_probe` as latest telemetry with `server_received_at=2026-06-28T12:37:04Z` and `fw_version=0.1.0-lte002-lte-http-probe-fix5`. Evidence is under `reports/field_validation/lte003-command-loop-20260628-210214/`, including `lte_command_loop_report_attempt2_existing_cmd.json`. LTE-003 runtime command polling/ACK remains unverified; next step is USB-attached bounded firmware console diagnosis on `COM4` to determine whether the flashed image boots and where the LTE HTTP command path stops.

2026-06-28: LTE-003 USB-Free validation attempt 1 failed after the operator connected independent power and disconnected USB. `scripts/validate_lte_command_loop.py` created `cmd-000013` (`set_report_interval`) for `lte003-command-loop-20260628-210214` and waited from `2026-06-28T13:52:07Z` to `2026-06-28T13:58:13Z`; the command remained `pending`, no ACK was received, and the test-run export contained zero messages. VPS device state still showed the prior LTE-002 fix5 `lte_http_probe` as latest telemetry. Evidence is under `reports/field_validation/lte003-command-loop-20260628-210214/`. LTE-003 runtime command polling/ACK remains unverified. The validator now supports `--existing-command-id` so the pending command can be reused after an independent-power reboot without enqueueing another command; after this validator update, `context_lint`, the focused validator tests, `verify.ps1` with 273 tests, and `git diff --check` passed.

2026-06-28: LTE-003 command-loop firmware is implemented, build-verified, and flashed on the connectivity node, but not USB-Free runtime validated yet. The new opt-in mode `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED` skips Wi-Fi for that image, waits for SIM7670G LTE readiness, polls the existing Message Hub command queue through SIM7670G AT HTTP GET, and ACKs one harmless `set_report_interval` command through SIM7670G AT HTTP POST. ACK payloads carry additive `transport.type=lte`, `lte_http.phase=command_ack`, and poll HTTP status/reason fields so the VPS validator can prove the ACK did not use the earlier Wi-Fi path. Focused tests passed, `context_lint` passed, full `verify.ps1` passed with 272 tests, and the ESP-IDF prepare/build run passed for `0.1.0-lte003-command-loop` / `lte003-command-loop-20260628-210214`; binary is `firmware/mqtt_heartbeat/build_lte003_command_loop/egolink_mqtt_heartbeat.bin`. The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte003-command-loop-20260628-210214/flash_report.md`. USB-Free runtime validation has not been performed yet.

2026-06-28: LTE-002 passed the USB-Free SIM7670G LTE HTTP uplink thin-slice on fix5. After the operator disconnected USB, ran the board on independent power, and power-cycled it, the VPS Message Hub received a fresh `lte_http_probe` result for `0.1.0-lte002-lte-http-probe-fix5` / `lte002-lte-http-probe-fix5-20260628-193815`: `boot_count=26006`, `server_received_at=2026-06-28T12:37:04.490795Z`, `transport.type=lte`, `lte_http.reason_code=LTE_HTTP_OK`, HTTP status `200`, action elapsed `1570 ms`, LTE `reason_code=LTE_READY`, registration `registered_home`, PDP `active`, assigned IP `10.160.15.113`, RAT `LTE`, cell ID `180571649`, RSSI `-91`, RSRP `-95`, RSRQ `-4`, and SINR `24`. Evidence is under `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/`. `scripts/validate_lte_http_probe.py` now has an explicit `--allow-existing-message-sec` option for one-shot boot probes and selects the latest matching `server_received_at`; local validation tests passed. This closes LTE-002 only: LTE command polling/ACK, reconnect behavior, long-run LTE stability, battery/power, and product LTE acceptance remain unverified.

2026-06-28: LTE-002 fix4 USB-attached firmware console diagnosis explained the zero-message USB-Free failure. A bounded `COM4` capture from `2026-06-28T11:33:16Z` to `2026-06-28T11:36:16Z` observed 340 repeated boots, 340 `LTE_HTTP_PROBE_ROUND_START attempt=1 max_attempts=6` lines, and 340 `***ERROR*** A stack overflow in task main has been detected.` panics. No `LTE_HTTP_PROBE_READY_CHECK`, payload byte, `HTTPDATA`, or `HTTPACTION` logs appeared, so fix4 never reached LTE readiness or SIMCom HTTP commands. Evidence is under `reports/field_validation/lte002-fix4-console-diag-20260628/`. Fix5 moves the LTE HTTP probe from synchronous `app_main` execution into a dedicated `lte_http_probe_task` with `LTE_HTTP_PROBE_TASK_STACK_SIZE=12288`. Focused tests passed, and the HTTP + SIM7670G LTE HTTP probe build passed for `0.1.0-lte002-lte-http-probe-fix5` / `lte002-lte-http-probe-fix5-20260628-193815`; binary is `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix5/egolink_mqtt_heartbeat.bin`. The fix5 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/flash_report.md`. USB-Free runtime validation has not been run yet.

2026-06-28: LTE-002 fix4 USB-Free validation failed after the operator connected independent power and disconnected USB. `scripts/validate_lte_http_probe.py` waited from `2026-06-28T11:00:01Z` to `2026-06-28T11:07:03Z` and observed no fresh `lte_http_probe` telemetry reaching the VPS Message Hub. `/health` returned `ok=true`, the LTE-002 fix4 test-run export contained zero messages, and `/api/state` still reported the prior LTE-001B fix1 Wi-Fi message lineage with `observability.transport.type=mock_4g_over_wifi` and no `lte_http_probe`. Evidence is under `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/`. LTE HTTP runtime transport remains unverified. Because USB-attached SIM7670G AT diagnosis already proved compact GET/POST LTE HTTP can reach the VPS, the next useful step is USB-attached firmware console diagnosis of the fix4 run path: capture payload byte logs, LTE readiness, `HTTPDATA`, `HTTPACTION`, and UART AT result codes from the ESP32-S3 firmware path.

2026-06-28: USB-attached LTE HTTP AT diagnosis found the LTE-002 blocker. SIM7670G USB AT ports `COM6` and `COM7` were reachable, SIM was ready, LTE was registered/attached, PDP was active, and the module had assigned IP `10.63.36.116`. A public `/health` GET through SIM7670G HTTP returned `+HTTPACTION: 0,200,98`, and a bearer-auth telemetry POST with a compact 211-byte payload returned `+HTTPACTION: 1,200,468`; token value was redacted from reports. Larger authenticated POST bodies reproduced the failure: 1232 bytes passed, while 2237 and 3230 bytes returned `+HTTPACTION: 1,706,0`. Evidence is under `reports/field_validation/lte002-atdiag-port-scan/20260628-182344/`, `reports/field_validation/lte002-atdiag-http-20260628/20260628-182752/`, `reports/field_validation/lte002-atdiag-authpost-20260628/20260628-183650/`, `reports/field_validation/lte002-atdiag-authpost-pad1000-20260628/20260628-184002/`, `reports/field_validation/lte002-atdiag-authpost-pad2000-com7-20260628/20260628-184258/`, and `reports/field_validation/lte002-atdiag-authpost-large-20260628/20260628-183924/`. Fix4 compacts the LTE HTTP probe payload by using a small LTE/cell fragment and removing raw AT fields from the `lte_http_probe` event while preserving `transport.type=lte`, `lte_http.reason_code`, HTTP status, action elapsed time, and LTE/cell readiness fields. Focused tests passed, and the HTTP + SIM7670G LTE HTTP probe build passed for `0.1.0-lte002-lte-http-probe-fix4` / `lte002-lte-http-probe-fix4-20260628-184644`; binary is `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix4/egolink_mqtt_heartbeat.bin`. The fix4 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/flash_report.md`. USB-Free runtime validation has not been run yet.

2026-06-28: LTE-002 fix3 USB-Free validation failed after the operator connected independent power and disconnected USB. `scripts/validate_lte_http_probe.py` waited from `2026-06-28T09:51:18Z` to `2026-06-28T09:58:22Z` and observed no fresh `lte_http_probe` telemetry reaching the VPS Message Hub; `/api/state` still reported the prior LTE-001B fix1 Wi-Fi message lineage with `observability.transport.type=mock_4g_over_wifi`. Evidence is under `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/`. This is the fourth LTE-002 USB-Free failure with no device-originated LTE HTTP telemetry reaching the VPS after readiness wait, bounded retries, and skipping default `AT+HTTPPARA="CID",1`. LTE HTTP runtime transport remains unverified. The next useful step is USB-attached bounded SIM7670G AT/serial diagnosis of the HTTP command path, not another blind USB-Free retry.

2026-06-28: LTE-002 fix2 USB-Free validation failed after the operator connected independent power and disconnected USB. `scripts/validate_lte_http_probe.py` waited from `2026-06-28T08:55:08Z` to `2026-06-28T09:02:11Z` and observed no fresh `lte_http_probe` telemetry reaching the VPS Message Hub; `/api/state` still reported the prior LTE-001B fix1 Wi-Fi message lineage with `observability.transport.type=mock_4g_over_wifi`. Evidence is under `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/`. LTE-002 fix3 is build-verified as `0.1.0-lte002-lte-http-probe-fix3` / `lte002-lte-http-probe-fix3-20260628-170508`; it keeps Wi-Fi disabled and preserves bounded retries, but skips `AT+HTTPPARA="CID",1` by default with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM=n`. The fix3 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/flash_report.md`. A later USB-Free validation also failed with no fresh LTE HTTP telemetry; LTE HTTP runtime transport remains unverified.

2026-06-28: LTE-002 fix1 USB-Free validation failed after the operator connected independent power and disconnected USB. `scripts/validate_lte_http_probe.py` waited from `2026-06-28T08:12:31Z` to `2026-06-28T08:16:34Z` and observed no fresh `lte_http_probe` telemetry reaching the VPS Message Hub; `/api/state` still reported the prior LTE-001B fix1 Wi-Fi message lineage with `observability.transport.type=mock_4g_over_wifi`. Evidence is under `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/`. LTE-002 fix2 is build-verified as `0.1.0-lte002-lte-http-probe-fix2` / `lte002-lte-http-probe-fix2-20260628-161844`; it keeps Wi-Fi disabled and retries the LTE HTTP probe up to `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_MAX_ATTEMPTS=6`, with `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC=20` seconds between failed rounds. The fix2 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/flash_report.md`. A later USB-Free validation also failed with no fresh LTE HTTP telemetry; LTE HTTP runtime transport remains unverified.

2026-06-28: LTE-002 USB-Free validation attempt 1 failed in an explainable way. With independent power and USB disconnected, `scripts/validate_lte_http_probe.py` waited from `2026-06-28T06:30:38Z` to `2026-06-28T06:34:41Z` and observed no fresh `lte_http_probe` telemetry reaching the VPS Message Hub; `/api/state` remained on the prior LTE-001B fix1 Wi-Fi message lineage with `observability.transport.type=mock_4g_over_wifi`. Evidence is under `reports/field_validation/lte002-lte-http-probe-20260628-141656/`. The likely first blocker is that the LTE HTTP probe attempted too soon after independent-power boot, before SIM7670G registration/PDP was ready.

2026-06-28: LTE-002 fix1 adds a bounded readiness wait before HTTP: up to `CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC=120`, polling every `CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_POLL_SEC=5`, for `LTE_READY` before AT HTTP POST. Focused tests passed, ESP-IDF prepare/build passed for `0.1.0-lte002-lte-http-probe-fix1` / `lte002-lte-http-probe-fix1-20260628-143631`, and the fix1 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/flash_report.md`. The later USB-Free validation failed with no fresh LTE HTTP telemetry; LTE HTTP runtime transport remains unverified.

2026-06-28: LTE-002 LTE HTTP uplink thin-slice is implemented, build-verified, and flashed on the connectivity node, but not USB-Free runtime validated yet. The new opt-in firmware mode `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED` skips Wi-Fi runtime tasks, uses SIM7670G AT HTTP commands to POST `event_type=lte_http_probe` telemetry to the existing VPS Message Hub, and emits `phase=attempt` followed by `phase=result` so the result event can report the first LTE POST's HTTP status. `scripts/validate_lte_http_probe.py` validates the VPS-side result by requiring fresh LTE telemetry, expected firmware/test-run IDs, `transport.type=lte`, `LTE_HTTP_OK`, and a 2xx HTTP status. Focused tests, `context_lint`, full `verify.ps1`, and an ESP-IDF prepare/build run passed for firmware `0.1.0-lte002-lte-http-probe` / test run `lte002-lte-http-probe-20260628-141656`, producing `firmware/mqtt_heartbeat/build_lte002_lte_http_probe/egolink_mqtt_heartbeat.bin`. The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition table were written, hashes verified, and hard reset completed. Flash evidence is under `reports/field_validation/lte002-lte-http-probe-20260628-141656/flash_report.md`. LTE HTTP runtime transport remains unverified until independent-power USB-Free validation passes.

2026-06-28: LTE-001B passed USB-Free LTE status observability on the connectivity node. With independent power and USB disconnected, `scripts/validate_lte_observability.py` passed for `0.1.0-lte001b-observe-fix1` / `lte001b-observe-fix1-20260628-131739` against the VPS Message Hub: fresh status matched the expected firmware and test-run ID, `observability.lte.reason_code=LTE_READY`, `driver=sim7670g_uart_at`, `query_ok=true`, `uart_ready=true`, `at_ok=true`, `sim_state=READY`, `registration_state=registered_home`, `apn_state=configured`, `pdp_state=active`, assigned IP present, RAT `LTE`, cell ID `180571649`, RSSI `-90`, RSRP `-97`, RSRQ `-7`, and SINR `28`. Evidence is under `reports/field_validation/lte001b-observe-fix1-20260628-131739/`. LTE-001B is accepted for LTE status observability only; it does not prove LTE HTTP transport, Wi-Fi-disable behavior, command polling over LTE, battery, power, or long-run stability.

2026-06-28: LTE-001B fix1 build/flash step completed for the connectivity node. The image `0.1.0-lte001b-observe-fix1` was rebuilt from the stack-margin fix, flashed on `COM4`, and reset successfully; test run ID is `lte001b-observe-fix1-20260628-131739`, with binary at `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/egolink_mqtt_heartbeat.bin`. USB-Free runtime validation has not been run for fix1 yet. This flash does not prove LTE status observability, LTE HTTP transport, Wi-Fi-disable behavior, command polling over LTE, battery, power, or long-run stability.

2026-06-28: LTE-001B USB-Free validation attempt 1 failed in an explainable way. With independent power and USB disconnected, `scripts/validate_lte_observability.py` observed that the flashed `0.1.0-lte001b-observe` firmware updated the device registration on the VPS, but no fresh `status` heartbeat arrived for test run `lte001b-observe-20260628-130400`; the last stored status remained from `fw002c-resetdiag-fix3-20260628-093000`, and `observability.lte.reason_code` remained `unknown`. Evidence is under `reports/field_validation/lte001b-observe-20260628-130400/`. A fix1 candidate moved LTE observation fragments out of heartbeat/sensor task stack, raised heartbeat/sensor task stacks to 12288 bytes, and build-verified `0.1.0-lte001b-observe-fix1` / `lte001b-observe-fix1-20260628-131739` at `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/egolink_mqtt_heartbeat.bin`. At that point, fix1 had not been flashed or USB-Free validated; LTE HTTP transport remained unverified.

2026-06-28: LTE-001B build/flash step completed for the connectivity node. The image `0.1.0-lte001b-observe` was built with SIM7670G GNSS and LTE-status observability enabled, flashed on `COM4`, and reset successfully; test run ID is `lte001b-observe-20260628-130400`, with binary at `firmware/mqtt_heartbeat/build_lte001b_observe/egolink_mqtt_heartbeat.bin`. USB-Free runtime validation has not been run yet; the next operator step is independent power plus USB disconnected before `scripts/validate_lte_observability.py` checks fresh VPS Message Hub status and `observability.lte.reason_code`. This flash does not prove LTE HTTP transport, Wi-Fi-disable behavior, command polling over LTE, battery, power, or long-run stability.

2026-06-28: LTE-001B was opened as the next active USB-Free LTE status observation task. `scripts/validate_lte_observability.py` can now validate a real flashed device from the VPS side by requiring the expected firmware version, expected `test_run_id`, fresh status, and a known `observability.lte.reason_code`; non-ready LTE reason codes remain valid diagnosability evidence for this task. At task opening, no firmware flash, USB-Free validation, Wi-Fi-disable run, `transport.type=lte`, or LTE HTTP transport validation had been performed for LTE-001B yet.

2026-06-28: LTE-001A added a build-verified SIM7670G LTE registration and cell observability baseline. The firmware now has an opt-in `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED` path that queries SIM, operator/RAT, registration, APN/PDP, assigned IP, cell fingerprint, signal metrics, bounded raw AT evidence, and LTE reason codes over the shared SIM7670G UART AT backend. Status and `sensor_sample` messages can include optional `cell` and `lte` objects; Message Hub schemas, `/api/state` observability, test-run explainability, and Dashboard rendering now expose LTE registration/PDP/SIM/reason state. Focused tests, `context_lint`, full `verify.ps1`, and an HTTP + SIM7670G GNSS + LTE-status opt-in ESP-IDF build passed for `0.1.0-lte001a-observe` at `firmware/mqtt_heartbeat/build_lte001a_observe/egolink_mqtt_heartbeat.bin`. The updated Message Hub was redeployed to the VPS without touching GitLab; `/health` returned `ok=true`, authenticated `/api/state` returned four devices, and the current connectivity node row had `observability.lte`. This step did not flash hardware, run USB-Free validation, disable Wi-Fi, set `transport.type=lte`, or prove SIM7670G LTE HTTP transport.

2026-06-27: DEPLOY-001 deployed the Message Hub to the operator-provided VPS as `egolink-message-hub.service`. The service listens on the field-test port, `/health` is reachable, `/api/*` requires a bearer token, the PC Simulator VPS loop passed with `ego-link-r0-vps-auth-smoke`, existing GitLab on the VPS was not modified, and no real VPS password or bearer token is stored in the repository.

2026-06-27: FW-001 added an opt-in HTTP Message Hub client to `firmware/mqtt_heartbeat` while keeping local MQTT as the default. The firmware can build in both default MQTT mode and HTTP Message Hub mode; HTTP mode covers register, heartbeat/status, telemetry, command polling, and ACK over `egolink.p0.v1`. No flash or real hardware runtime validation was performed in FW-001; `FW-001-HW` remains the next operator hardware step.

2026-06-27: FW-001-HW-PREP completed the R1 USB-Free validation kit. The Message Hub test-run export route now matches `/api/v1/test-runs/{test_run_id}/export` and includes matching command history; firmware HTTP mode can optionally attach `CONFIG_EGOLINK_TEST_RUN_ID` to status, telemetry, and ACK messages; `scripts/validate_fw001_hw_loop.py` can create a test run, wait for a fresh heartbeat, queue `set_report_interval`, wait for ACK, and write JSON/Markdown evidence under ignored `reports/field_validation/`. The updated Message Hub was redeployed to the VPS, `/health` returned `ok=true`, and a temporary `deploy-route-smoke-*` test run exported successfully. No firmware flash, USB-disconnected hardware run, GNSS, LTE, battery, camera, audio, or power validation was performed in this prep task.

2026-06-27: FW-001-HW-CONFIG generated the local ignored R1 HTTP firmware config `firmware/mqtt_heartbeat/sdkconfig.vps.local` from operator runtime values and built `firmware/mqtt_heartbeat/build_fw001_hw/egolink_mqtt_heartbeat.bin` with `sdkconfig.defaults;sdkconfig.vps.local`. The prep script `scripts/prepare_fw001_hw_config.ps1` does not flash hardware and does not print runtime secrets; tests cover config shape and ignored-file boundaries. No firmware flash, USB-disconnected hardware run, serial capture, GNSS, LTE, battery, camera, audio, or power validation was performed.

2026-06-27: FW-001-HW-RUNNER added `scripts/run_fw001_hw_r1.ps1` as a guarded operator entry point for R1. Default execution is plan-only; flash requires `-Flash`, `-FlashPort`, and `-IUnderstandFlashWritesFirmware`; validation requires `-Validate`, `-OperatorConfirmedIndependentPower`, and `-OperatorConfirmedUsbDisconnected`. Plan-only smoke passed, and no firmware flash, USB-disconnected hardware run, serial capture, Message Hub validation command, GNSS, LTE, battery, camera, audio, or power validation was performed.

2026-06-27: FW-001-HW completed the first real R1 USB-Free Message Hub validation. The connectivity node was flashed on `COM4` with firmware `0.1.0-fw001-hw-r1`, the operator then confirmed independent power and USB disconnected, and `scripts/run_fw001_hw_r1.ps1 -Validate` passed against the operator VPS Message Hub. Evidence was written under ignored `reports/field_validation/fw001-hw-r1-20260627-133813/`: heartbeat `seq=7`, command `cmd-000003` (`set_report_interval`), ACK `seq=8`, connection path `independent_power_usb_disconnected`. This validates the Wi-Fi HTTP Message Hub skeleton path only; GNSS fix, SIM7670G LTE control, battery/charging accuracy, camera, audio, storage, and product power behavior remain unverified by this task.

2026-06-27: FW-002A added the GNSS command/telemetry scaffold for the USB-Free path. HTTP Message Hub firmware now recognizes `request_location`, uploads an explicit `location_report` with `fix=false`, `source_status=unverified`, and `gnss_state=driver_not_integrated`, then ACKs the command. `scripts/validate_fw002_location_loop.py` can queue the command, wait for `location_report`, wait for ACK, and export field evidence; Dashboard field state now shows fix, satellites, HDOP, and source status. Default MQTT and HTTP Message Hub ESP-IDF builds passed, the updated Message Hub was redeployed to the VPS and `/health` returned `ok=true`; the deploy script now excludes local `server/runtime` and the remote app runtime directory was removed while the service database remains under `/var/lib/egolink-message-hub/`. No FW-002A flash or real hardware runtime validation was performed; the currently running R1 device remains on `0.1.0-fw001-hw-r1`.

2026-06-27: FIELD-001A completed the real-device USB-Free validation for FW-002A. The connectivity node was flashed on `COM4` with `0.1.0-fw002-location-scaffold`, the operator confirmed independent power and USB disconnected, and `scripts/validate_fw002_location_loop.py` passed against the VPS Message Hub. Evidence was written under ignored `reports/field_validation/fw002-location-build-smoke/`: heartbeat `seq=3`, `request_location` command `cmd-000004`, `location_report seq=4` with `fix=false`, `gnss_state=driver_not_integrated`, `source_status=unverified`, and ACK `seq=5`. This proves the location command/telemetry scaffold only; real GNSS fix and SIM7670G GNSS/LTE firmware control remain unverified. During the run a stale ESP-IDF build-dir `sdkconfig` issue was found and fixed in `scripts/prepare_fw001_hw_config.ps1`.

2026-06-27: WEB-002A fixed the Message Hub Dashboard observation gap found after FIELD-001A. `/api/state` device rows now include `latest_location`, derived from the most recent `location_report`, so newer `sensor_sample` telemetry no longer hides the latest location evidence. The Dashboard field state prefers `latest_location` for GNSS/fix/source fields and shows an explicit auth-required state when `/api/state` returns 401. The updated Message Hub was redeployed to the VPS; `/health` returned `ok=true`, unauthenticated `/api/state` returned HTTP 401, and authenticated `/api/state` returned `ego-link-r1-connectivity-001` with firmware `0.1.0-fw002-location-scaffold`, latest generic telemetry `sensor_sample`, and latest location `location_report seq=4` (`fix=false`, `gnss_state=driver_not_integrated`, `source_status=unverified`). No bearer token or VPS secret is stored in the repository.

2026-06-27: FW-002B added a build-verified, opt-in SIM7670G firmware GNSS UART/AT backend behind the existing `request_location -> location_report -> ACK` Message Hub envelope. The backend defaults off, uses the Waveshare ESP-IDF example UART convention (UART1, RX GPIO17, TX GPIO18, 115200 baud), sends bounded `AT`, `AT+CGNSSPWR=1`, `AT+CGNSSINFO`, and `AT+CGPSINFO` queries, parses common no-fix/fix responses, and reports `source=sim7670g_firmware_gnss`, `gnss_driver=uart_at`, `gnss_query_ok`, and bounded raw AT evidence. The default MQTT ESP-IDF build passed, and the HTTP + SIM7670G GNSS opt-in build produced `firmware/mqtt_heartbeat/build_fw002b_gnss/egolink_mqtt_heartbeat.bin` with firmware version `0.1.0-fw002b-sim7670-gnss`. No FW-002B flash, USB-Free hardware validation, outdoor GNSS fix, or SIM7670G LTE data transport validation was performed; the currently running connectivity-node firmware remains the previously flashed FW-002A image until an explicit flash task.

2026-06-27: FIELD-001B completed the real-device USB-Free validation for FW-002B after one hardware-discovered firmware fix. The first FW-002B image was flashed on `COM4` as `0.1.0-fw002b-sim7670-gnss` with test run `fw002b-gnss-r1-20260627-155211`; the device reached the VPS and uploaded status/sensor messages, but `request_location` command `cmd-000005` stayed `pending` and no `location_report` appeared. The command-poll task stack was increased to `COMMAND_POLL_TASK_STACK_SIZE=12288`, covered by `quality_tests/test_fw002b_sim7670_gnss_firmware.py`, then FW-002B fix1 was built and flashed as `0.1.0-fw002b-sim7670-gnss-fix1`. With independent power and USB disconnected, `scripts/validate_fw002_location_loop.py` passed against the VPS: fresh heartbeat `seq=57`, `request_location` command `cmd-000006`, `location_report seq=58` (`source=sim7670g_firmware_gnss`, `gnss_source=sim7670g_uart_at`, `gnss_driver=uart_at`, `gnss_query_ok=true`, `fix=false`, `gnss_state=no_fix`, raw response `+CGPSINFO: ,,,,,,,, OK`), and ACK `seq=59`. Evidence is under ignored `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/`. This proves the USB-Free Message Hub loop with firmware-side SIM7670G GNSS AT no-fix diagnostics only; outdoor real GNSS fix and SIM7670G LTE data transport remain unverified.

2026-06-27: RELIABILITY-001A started the R3 diagnosability track. New observation-only script `scripts/validate_message_hub_stability.py` can monitor the VPS Message Hub for continuous device messages, last-seen age, message gaps, and sequence regressions without opening serial ports, flashing firmware, or enqueueing commands. A 90-second live USB-Free observation of the current FW-002B fix1 device failed with one sequence regression: messages advanced to `seq=125` / `uptime_ms=919403`, then reset to `seq=1` / `uptime_ms=1988` at `2026-06-27T09:08:26Z`; evidence is under ignored `reports/field_validation/stability-fw002b-fix1-20260627-170758/`. Firmware now adds additive reset diagnostics (`reset_reason`, `boot_count`, `boot_uptime_ms`) to status and `sensor_sample` messages, the Message Hub schemas and protocol docs list these fields, and an HTTP + SIM7670G GNSS opt-in build passed for `0.1.0-fw002c-resetdiag` at `firmware/mqtt_heartbeat/build_fw002c_resetdiag/egolink_mqtt_heartbeat.bin`. The diagnostic image has not yet been flashed or runtime-validated.

2026-06-27: RELIABILITY-001B completed the FW-002C reset-diagnostics USB-Free runtime validation. `0.1.0-fw002c-resetdiag-fix1` was flashed to the connectivity node and observed over the VPS with USB disconnected; the 120-second run failed with 10 sequence regressions and reset diagnostics showed repeated `reset_reason=panic` with `boot_count` increasing from 41 to 81. The likely stack-pressure cause was fixed by moving the 1280-byte heartbeat status payload off the heartbeat task stack and increasing the heartbeat task stack to 6144 bytes. `0.1.0-fw002c-resetdiag-fix2` was built and flashed, then a 120-second USB-Free observation passed with 15 messages, `seq` 11 to 25, `seq_regressions=0`, max gap 11.547434 seconds, final last-seen age 6.563391 seconds, and reset diagnostics reporting `reset_reason=poweron` / `boot_count=171`; evidence is under ignored `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/`. This validates the Wi-Fi HTTP Message Hub stability gate for the reset-diagnostics image only; outdoor GNSS fix, SIM7670G LTE data transport, battery accuracy, and product power behavior remain unverified.

2026-06-27: FIELD-001C attempted a window-side real GNSS fix through the FW-002C resetdiag fix2 USB-Free Message Hub path. The operator placed the independently powered board near a window with USB disconnected, then `scripts/validate_fw002_location_loop.py --require-fix` queued `request_location` over the VPS. The device returned `location_report seq=601` and ACK `seq=602` for command `cmd-000008`, proving the command/report/ACK path remained live, but real fix failed: `fix=false`, `gnss_state=no_fix`, no satellites/HDOP/coordinates, and raw AT response `+CGPSINFO: ,,,,,,,, OK`. Evidence is under ignored `reports/field_validation/fw002c-fix2-window-gnss-retry1-20260627-195000/`. The validation script now preserves failure evidence for `--require-fix` no-fix runs and can reuse an existing firmware `CONFIG_EGOLINK_TEST_RUN_ID` for repeated field attempts.

2026-06-28: FIELD-001C continued the window-side GNSS attempt and captured the first firmware-side SIM7670G `fix=true` report over the USB-Free VPS path. The current flashed firmware `0.1.0-fw002c-resetdiag-fix2` received `request_location` command `cmd-000010`, uploaded `location_report seq=6920`, and ACKed with `seq=6921`; the report had `fix=true`, `gnss_state=fix`, and latitude/longitude fields present. The validation result is still FAIL because fix2 reports `source_status=unverified`, while the acceptance gate requires fixed coordinates to be `observed` or `verified`. Evidence is under ignored `reports/field_validation/fw002c-fix2-window-gnss-fix-unverified-20260628-092703/`. Firmware has been patched so parsed SIM7670G coordinates report `source_status=observed`, and an HTTP + SIM7670G GNSS opt-in build passed for `0.1.0-fw002c-resetdiag-fix3` with test run `fw002c-resetdiag-fix3-20260628-093000`; this image has not yet been flashed or USB-Free validated.

2026-06-28: FIELD-001C passed the first USB-Free firmware-side SIM7670G real GNSS fix validation. The connectivity node was flashed on `COM4` with `0.1.0-fw002c-resetdiag-fix3`, then the operator confirmed independent power and USB disconnected near the window test position. The first fix3 request saw `gnss_state=at_unreachable` while the SIM7670G AT path was not ready; after a one-minute wait, `scripts/validate_fw002_location_loop.py --require-fix` passed against the VPS Message Hub: fresh heartbeat `seq=30`, command `cmd-000012`, `location_report seq=31` (`fix=true`, `gnss_state=fix`, `source=sim7670g_firmware_gnss`, `source_status=observed`, `gnss_source=sim7670g_uart_at`, `gnss_driver=uart_at`, `gnss_query_ok=true`, latitude/longitude fields present), and ACK `seq=33`. Evidence is under ignored `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/`. This validates the USB-Free Wi-Fi HTTP Message Hub command/report/ACK path with firmware-side SIM7670G GNSS real-fix evidence; SIM7670G LTE data transport, battery accuracy, product power behavior, and product enclosure/mounting GNSS acceptance remain unverified.

2026-06-28: The next route was corrected to "observable first" instead of a blind long stability run. The roadmap now sequences R2.1 observability completion, R2.2 short USB-Free baseline stability, R2.3 SIM7670G LTE HTTP thin-slice, R2.4 LTE command loop, R2.5 multi-source location observation and memory, then R3 product gates for LTE long-run, power/battery, and enclosure GNSS. OBS-001 added an additive server-side observability view to `/api/state` and test-run exports, covering transport, runtime, command, power, GNSS, cell, and reason-code fields while keeping `egolink.p0.v1` compatible. The updated Message Hub was redeployed to the VPS without touching GitLab; `/health` returned `ok=true`, authenticated `/api/state` returned three devices, and the current connectivity node row included `observability` with a GNSS reason code. No long stability run, LTE data transport run, firmware flash, or hardware action was performed by this update.

2026-06-28: LOC-002 added the first multi-source `location_observation` baseline. The event remains inside the existing `egolink.p0.v1` `message_type=event` envelope and does not replace `location_report`. `message_hub_event.schema.json` now lists optional `wifi`, `imu`, and `location_belief`; PC Simulator uploads a mock observation with GNSS, cell, hashed Wi-Fi AP identifiers, IMU, power, and belief fields; Message Hub treats `location_observation` as latest location evidence, exposes `latest_location_observation`, and derives `observability.location_belief`; Dashboard now shows location state, belief confidence/radius/source/reason, Wi-Fi, and IMU fields. The updated Message Hub was redeployed to the VPS without touching GitLab; a PC Simulator public smoke device `ego-link-r0-loc002-smoke` uploaded both `location_report` and `location_observation`, and authenticated `/api/state` showed `latest_location_event=location_observation`, `belief_state=Fine`, hashed Wi-Fi AP count, and IMU motion without printing tokens or exact coordinates. This is a protocol/server/web/simulator baseline only; no firmware-side cell/Wi-Fi/IMU fusion, location-memory table, rule engine, LTE transport, hardware flash, or hardware validation was performed.

2026-06-28: STAB-001A prepared the short baseline gate tooling without claiming a physical stability pass. PC Simulator can now bind heartbeat, `location_report`, `location_observation`, ACK, and test-run export evidence to one `test_run_id`. `scripts/validate_message_hub_stability.py` remains passive by default, but can now require minimum `location_observation` count, final `observability`, `location_belief`, command ACK, and test-run export availability for a strict short-baseline gate. Local HTTP tests passed for the strict gate path. No firmware flash, serial capture, hardware command enqueue from the observer, long stability run, LTE data transport validation, or physical USB-Free STAB-001 acceptance was performed.

# Ego Link 状态记录

更新时间：2026-06-27

## 当前阶段

Stage 0：单智能体、单任务、低风险迭代开发模式。2026-06-24 起，P0 执行策略调整为 **Demo-first / 最小功能原型优先**：先跑通核心产品体验，再逐步补硬件真实化、质量门和稳定性。

产品锚点：AI 主动守护定位器。近期 v0.1 目标聚焦设备联网、MQTT 上报、网页看板、SOS / 唤醒 / 定位事件闭环，并为后续 AI 主动提醒打基础。

2026-06-27 工程控制面快照已生成：`docs/current/PROJECT_SNAPSHOT.md` 和 `docs/tasks/TASK_TREE.md`。事实状态是：Demo v0.5 runner 已完成并通过 quality/replay；`DEMO-001` 和 `DEMO-004` 已从 `docs/tasks/active/` 移动到 `docs/tasks/done/`；当前没有 `status: active` 的任务包；Git 工作区仍包含待确认的上下文迁移/文档改动。

2026-06-27 开发流程基线调整为 **USB-Free / VPS Message-First / Demo-Driven / Contract-First Walking Skeleton**。新增 `ENG-005 P0 Dev Flow Baseline` 文档基线：后续先建立设备或模拟器到公网 VPS 消息中枢再到 Web Dashboard 的可演示闭环，再按 Firmware、Server-Web、Protocol 三条轨道版本化增强；USB 仅用于烧录、临时调试和失败后日志导出，不作为正式外场运行或验收链路。

同日完成 `PROTO-001 Message Hub Contract Baseline`：新增 `shared/contracts/message_hub_status.schema.json`、`message_hub_event.schema.json`、`message_hub_command.schema.json`、`message_hub_ack.schema.json` 和 `message_hub_error.schema.json`，把既有 `egolink.p0.v1` 的 `status` / `event` / `command` / `ack` 行为冻结为 VPS message hub 的最小契约；下一步推荐执行 `SERVER-001` 与 `SIM-001` 建立 R0 纯模拟 VPS 闭环。

同日完成 `SERVER-001 VPS Message Service Minimal Loop` 本地可部署基线：新增标准库 HTTP + SQLite 服务 `server/message_hub.py` 和入口 `scripts/run_message_hub.py`，支持设备注册、heartbeat/status、telemetry/event、command queue、ACK、error、设备列表、telemetry 查询、test-run 记录和极简浏览器 Dashboard；验证仍是本地服务基线，尚未部署到 VPS，且未修改 VPS 上既有 GitLab。

同日完成 `SIM-001 PC Simulator Message Hub Loop` 本地 R0 客户端：新增 `pc_simulator/message_hub_client.py` 和 `scripts/run_message_hub_simulator.py`，可向 Message Hub 注册虚拟设备、上报 heartbeat 和 mock GNSS `location_report`、轮询 command 并回传 ACK；下一步推荐扩展 `WEB-001` Dashboard 或通过安全凭据流程部署 SERVER-001 到 VPS。

同日新增 Message Hub VPS 部署脚本 `scripts/deploy_message_hub_vps.ps1` 和 `server/.env.example`：脚本会打包标准库服务并安装为 `egolink-message-hub.service`，默认不触碰 VPS 上既有 GitLab；公开监听需要本地环境变量 `EGOLINK_MESSAGE_HUB_TOKEN`，仓库不保存真实 token 或密码。

同日完成 `WEB-001 Message Hub Dashboard Baseline`：`server/message_hub.py` 内置 Dashboard 现在显示在线/过期/离线状态、最新 GNSS/位置摘要、网络/电量摘要、命令状态、最近错误和消息流；`/api/state` 同步返回 recent commands，作为后续 R1/R2 外场观察台的最小 Web 基线。

同日完成 `WEB-002A Dashboard Latest Location And Auth Visibility`：Web 观察台已能区分 API token 缺失与无设备数据，并将最新 `location_report` 作为单独的 `latest_location` 状态展示，避免后续普通 `sensor_sample` 覆盖定位证据。

同日完成 `FW-002B SIM7670G Firmware GNSS AT Backend` 构建基线：固件侧已具备可选 SIM7670G UART/AT 查询后端。随后 `FIELD-001B` 将 FW-002B fix1 刷写到连接节点，并在独立电源、USB 断开的条件下通过 `request_location -> location_report -> ACK` 验证；本次是 SIM7670G firmware GNSS AT no-fix 诊断闭环，不代表户外真实 fix 或 LTE 数据链路验收。`RELIABILITY-001A` 的 90 秒观察发现 FW-002B fix1 发生一次重启/seq 回退；`RELIABILITY-001B` 随后刷写 FW-002C reset diagnostics，先用 fix1 复现 `panic` 重启，再用 fix2 通过 120 秒 USB-Free VPS 稳定性观测。

## 已完成

- DEMO-004：完整 Demo v0.5 编排器完成。新增 `pc_simulator/full_safety_demo.py` 与 `scripts/run_full_safety_demo.py`，可从实机或既有证据文件生成完整 P0 安全闭环：AMOLED IMU/touch、SIM7670G GNSS/AT、mock-only 结构化音频、session recording、quality gate 和 replay。使用 2026-06-26 AMOLED 实机 `motion_event + user_confirmation=safe` 证据并现场探测 SIM7670G GNSS AT 口 `COM6`，生成 `pc_simulator/runtime/demo_full_v0_5/demo-full-v05-20260626-live-gnss.summary.json`；v0.1-v0.5 阶段门全部通过，quality score `0.94`，replay PASS。音频仍明确为 mock-only，未声明真实麦克风验收。
- DEMO-002A：AMOLED 安全询问屏幕花屏缓解。用户实机反馈 DEMO-002 初版屏幕出现彩色噪声/横条花屏；修复将 `firmware/amoled_safety_demo` 的显示依赖锁回 Waveshare 官方 ESP-IDF v5.4.2 LVGL 示例组合：`waveshare/esp32_s3_touch_amoled_2_06=1.0.3`、`waveshare/esp_lcd_sh8601=1.0.2`、`espressif/esp_lvgl_port=2.6.0`、`lvgl/lvgl=9.2.0`，并启用 `CONFIG_IDF_EXPERIMENTAL_FEATURES=y`。`ESP-IDF v5.4.2` build 通过，生成 `egolink_amoled_safety_demo.bin`，app binary size `0x9b240`；已刷写到 `COM9`，识别 ESP32-S3、PSRAM 8MB、MAC `02:00:00:00:00:01`，hard reset 成功。复位后串口确认 `sh8601` 版本 `1.0.2`、`hello` 和 `ask_user_rendered` 输出正常；视觉恢复仍需用户现场确认。
- DEMO-002：AMOLED 安全询问屏幕 Demo 固件完成。新增 `firmware/amoled_safety_demo`，基于 Waveshare `ESP32-S3-Touch-AMOLED-2.06` BSP + LVGL 显示 `Impact detected / Are you safe? / SAFE / HELP`，按钮回调会通过 USB 串口输出 `user_confirmation` JSON。`ESP-IDF v5.4.2` build 通过，生成 `egolink_amoled_safety_demo.bin`，app binary size `0x9a370`；已刷写到自动识别出的 Espressif USB-Serial/JTAG 口 `COM9`，识别 ESP32-S3、PSRAM 8MB、MAC `02:00:00:00:00:01`，hard reset 成功。复位后有限串口读取已捕获 `hello` 和 `ask_user_rendered`；后续有限串口读取已捕获多条 `user_confirmation`，覆盖 `safe` 和 `help` 触摸回传。当前仍是启动即显示的最小屏幕 Demo，尚未接入 PC Bridge `ask_user` 下行命令。
- T001：补齐可重复验证入口 `scripts/verify.ps1`。
- T002：定义 PC Simulator 事件/命令协议模型。
- T003：实现 PC Simulator 本地事件存储。
- T004：打通 PC Simulator 的事件生成、存储与命令记录。
- T005：更新 Stage 0 任务与状态记录。
- T011：摄像头拍照 smoke test 通过。ESP32-S3 已烧录过 `firmware/camera_smoke`，摄像头初始化成功并采集到一张 JPEG。
- T012：本机 Mosquitto broker 基线通过。Windows 版 Mosquitto 已安装，本机服务运行，用户态 LAN broker 可供开发板连接。
- T013：ESP32-S3 MQTT 心跳 smoke test 通过。开发板已烧录 `firmware/mqtt_heartbeat`，通过 Wi-Fi 连接本机 Mosquitto 并发布 status JSON。
- T014：项目目录清理与版本化迭代模式完成。已删除可再生构建产物和运行缓存，新增 `.gitignore`、`docs/DEVELOPMENT_WORKFLOW.md`、`scripts/start_mosquitto_lan.ps1`，并明确采用 GitHub Flow。
- T015：SIM 卡与 4G 数据链路基础验证通过。SIM7670G 可识别 SIM，注册 LTE，分组数据附着成功，并可通过模块 AT TCP/IP 栈访问公网 IP。
- T016：PC Simulator MQTT worker 完成。`pc_simulator/mqtt_worker.py` 可订阅 `ego/link/+/status`，接收开发板 status JSON，并写入 `pc_simulator/runtime/events.jsonl`。
- T017：PC Simulator Dashboard 读取 MQTT 事件日志完成。`/api/state` 可合并 JSONL 事件日志，并用最新 MQTT status 更新设备状态；网页看板展示 RSSI、最后在线时间和来源。
- T018：MQTT event / ack 闭环完成。worker 默认订阅 `status` / `event` / `ack` 三类 topic，Dashboard 事件流可展示 `mqtt_ack`、`wake_detected` 等上报与确认事件。
- T019：固件传感器数据上报完成。`firmware/mqtt_heartbeat` 已新增 `sensor_sample` / `device_health` event，上报 uptime、Wi-Fi RSSI、free heap、minimum free heap 等 ESP32 设备健康数据；已刷写 ESP32-S3 `COM4`，PC Simulator 收到真实 `sensor_sample`，Dashboard 可展示 sensor sample 的 RSSI/heap 详情。
- T020：板级探测 CH343 / RNDIS 识别修复完成。`egolink_board_probe.py` 已合并 Windows CIM 与 PnP 设备发现，真实探测可识别 ESP32-S3 `COM4`、SIM7670G 串口和 Remote NDIS 网卡。
- T021：SIM7670G GNSS 探测与 `location_report` 写入完成。新增 `scripts/sim7670_gnss_probe.py`，可自动探测 SIM7670G AT 口，打开/查询 GNSS，解析 `CGNSSINFO` / `CGPSINFO`，并写入 PC Simulator 事件日志；当前室内无 fix，但 `location_report` 已进入 Dashboard/API 闭环。
- T022：Safety Companion M0 契约基线完成。已将 `模型架构.md` 的“版本化模型包 + 明确接口契约”路线整合为 `docs/modeling/` 文档、`shared/contracts/` JSON Schema 和 `quality_tests/model_contract/` 契约测试；当前只做契约和边界，不引入训练代码或推理运行时。
- T023：PC Simulator Safety Companion adapter 完成。新增 `pc_simulator/safety_companion.py`，可将最近事件和设备状态转换为 `model_input`，并返回确定性 mock `model_output`；`/api/state` 和 Dashboard 已展示 Safety Companion 风险、分数、建议动作和 reason codes。
- T024：Safety Companion M0 PC Simulator adapter 完成。`pc_simulator/safety_companion.py` 已从本地 mock router 切换为调用模型包 `RuleRouter` / `build_model_input`；新增 `POST /api/safety/evaluate`，支持标准 `sensor_frame` / `model_input` 评估，并可将非 `none` 输出转换为 `safety_event`。
- T025：Safety Companion M0 固件模型接口完成。新增 `firmware/mqtt_heartbeat/components/safety_model`，围绕 `shared/embedded/safety_model_contract.h` 暴露 `safety_model_init/evaluate/version`，当前为明确标识的 deterministic mock；SOS 路径固定输出 `MANUAL_SOS + URGENT_ESCALATION`，并提供 mock 状态 adapter 与串口测试命令。
- T026：Safety Companion M0 模拟端到端闭环完成。新增 `POST /api/safety/replay`，可重放 `normal_walk`、`manual_sos`、`post_impact_inactivity`、`privacy_restricted_impact` 四个场景；非 `none` 输出生成 `safety_event`，`ask_user` / `urgent_escalation` 生成无副作用的模拟 `base_command`，Dashboard 事件详情可展示 risk/action/evidence/privacy。
- T027：真实/半真实设备事件接入 Safety Companion 流程完成。新增 `evaluate_event` 和 `POST /api/safety/process-events`，可将 MQTT `sensor_sample`、SOS/模拟 SOS、GNSS no-fix 等事件转换为标准 `sensor_frame` 并记录 `safety_evaluation`；非 `none` 输出继续生成 `safety_event` 和无副作用模拟 command。
- T028：live MQTT 监督式 Safety 处理完成。`pc_simulator/mqtt_worker.py` 新增 `--process-safety` / `--safety-process-limit`，可在真实 MQTT 消息入库后立即触发 Safety flow；默认入库行为保持不变，Safety 处理异常只写诊断、不阻断 MQTT 采集。
- T029：本地监督会话入口完成。新增 `scripts/start_local_supervised_session.ps1` 和 `scripts/local_session_summary.py`，可一条命令建立 session 目录，启动或复用 broker / Dashboard / live MQTT Safety worker，并输出 `session.log`、`session_summary.json`、`session_summary.md`。
- T030：AutoDev 与设备状态统一监控完成。`scripts/autodev.py watch` 和 `scripts/watch_autodev.ps1` 已同屏显示 AutoDev 任务进度与本地设备 / Safety session 摘要；`status` 也会显示本地 Safety 快照。
- T031：M1-001 硬件传感器矩阵完成。新增 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，把当前开发板、SIM7670G、Wi-Fi/MQTT、摄像头、SD、IMU、麦克风、物理 SOS、电源/电量和 PC 侧探测链路按 `verified` / `semi_verified` / `pc_side_verified` / `mock_only` / `not_verified` / `missing_or_unknown` 标明边界，并明确 M1-002 recorder 的最小字段和阻塞项。
- T032：M1-002 session recorder 骨架完成。新增 `pc_simulator/session_recorder.py` 和 `scripts/session_recorder.py`，可从 PC Simulator `events.jsonl` 派生 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和 `session_recording.md`；本地监督会话脚本默认生成 `recording/`，且 manifest 显式标注未验证传感器不可用。
- T033：M1-004-pre PC session inspector / quality gate 完成。新增 `pc_simulator/session_inspector.py` 和 `scripts/inspect_session_recording.py`，可校验 T032 `recording/` 目录的必需文件、manifest、JSONL、record counts、privacy、sensor source 边界、source key 唯一性和 seq/timestamp warning，并输出 `session_quality_report.json` / `.md`。
- T034：M1-004-pre quality gate 监控接入完成。`scripts/start_local_supervised_session.ps1` 在 recorder 后自动运行 session inspector，写入 quality report 并在会话日志显示 PASS/FAIL；`scripts/autodev.py watch/status` 已在本地设备区块显示 Quality 和 Report。
- T035：M1-004-pre session 文件完整性完成。Recorder 现在生成 `file_manifest.json`，记录 session manifest、sensor frames、events、annotations 和 summary 的 SHA-256；quality gate 会校验必需条目、文件大小和哈希，发现静默修改时失败。
- T036：M1-004 PC session import / replay 完成。新增 `pc_simulator/session_replay.py` 和 `scripts/replay_session_recording.py`，可对完整性校验通过的 recording 重建 sensor frames / events 时间线，调用现有 RuleRouter，并输出 `session_replay_report.json` / `.md`；质量门失败时默认拒绝回放。
- HCTX-001：硬件上下文包 v0.3 评估与硬件矩阵更新完成。新增 `docs/hardware/**` 和 `HARDWARE_CONTEXT_PACKAGE_README.md`，验证硬件包 manifest 与采购清单 Excel 结构，修正 P0 上下文路径为 `docs/EGO_LINK_P0_CONTEXT.md`，并把 `docs/modeling/HARDWARE_SENSOR_MATRIX.md` 更新为 HCTX-001 版，补齐接口、驱动、数据能力、功耗控制、真实/Mock 边界、M1 阻塞项和 HARCH-001 审计重点。
- T038：硬件可用性 smoke 验证完成。新增 `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`，确认 ESP32-S3 `COM4`、SIM7670G `COM6/COM7`、RNDIS、SIM inserted、LTE registered/attached、LAN MQTT 上报、PC 侧 GNSS no-fix `location_report`、recording quality gate 和 replay 均可用；同时明确 GNSS fix、SD、IMU、麦克风、物理 SOS、真实电量和 ESP32 侧 SIM7670G 控制仍未验证。
- T037：M1-005 最小 session annotation CLI 完成。新增 `pc_simulator/session_annotations.py` 和 `scripts/annotate_session_recording.py`，可列出可标注 target，并向 `annotations.jsonl` 追加 `safe`、`needs_help`、`false_alarm`、`cancelled`、`no_response` 标签；追加后自动刷新 manifest count、summary 和 file manifest 哈希，quality gate / replay report 均可读取 annotation 摘要。
- HARCH-001：平台耦合审计完成。新增 `docs/hardware/PLATFORM_COUPLING_AUDIT.md`，盘点 ESP32-S3、SIM7670G、GNSS、摄像头、IMU、麦克风、SD、电池/电量计、功耗标记和 M1 PC 闭环的真实/Mock 边界，并明确 HARCH-002A 建议从 `platform_power` 开始。
- HARCH-002A：最小 `platform_power` 接口完成。新增 `firmware/mqtt_heartbeat/components/platform_power` log/mock 后端，主固件通过 snapshot 输出 mock battery/charging source 和 `power_state`，并输出串口 power marker；未实现真实电池、电量计、睡眠、GPIO marker 或 SIM7670G 电源控制。
- HPWR-001：功耗状态事件和测量标记完成。`platform_power` 现在输出结构化 `PLATFORM_POWER_EVENT` 日志、状态累计时长、`POWER_MARKER_<seq>` 串口 marker，并在 MQTT status / sensor payload 中带出 power elapsed/cumulative/marker 字段；GPIO marker 仍显式为 disabled，未声明任何真实电流、续航或电池数据。
- HDATA-001：HPWR 固件 live 数据采集闭环完成。已刷写 `firmware/mqtt_heartbeat` 到 ESP32-S3 `COM4`，用独立 event log 收到 4 条 `mqtt_status`、2 条真实 `sensor_sample/device_health` 和 1 条 PC 侧 SIM7670G `location_report no_fix`；clean recording 质量门 PASS `quality_score=0.94`，replay PASS，7 个输入均为 `risk_type=none`。证据摘要见 `docs/hardware/HDATA_001_LIVE_CAPTURE_20260623.md`。
- T039：IMU mock/driver interface 和 ring buffer 骨架完成。新增 `firmware/mqtt_heartbeat/components/platform_imu`，提供 32 样本 ring buffer、mock stationary accel/gyro sample、snapshot 和 recent-read API；`sensor_sample/device_health` 现在可带出 `imu_source`、ring count、latest seq、mock accel/gyro 字段。真实 IMU 料号、总线、引脚、方向、ODR、FIFO、中断和采样质量仍未验证。
- T039-live：IMU mock payload 真板采集完成。首次 T039 烧录暴露 `sensor_task` 栈溢出，已通过静态 sensor JSON buffer 和 `sensor_task` 6144 stack 修复；随后 ESP32-S3 `COM4` 烧录成功，live MQTT 收到 7 条 `mqtt_status` 和 3 条 `sensor_sample/device_health`，样本带出 `imu_source=mock_stationary`、`imu_hardware_present=false`、`imu_driver_enabled=false`、`imu_sample_mock=true`、ring count 和 accel/gyro mock 数值；quality gate PASS `0.94`，replay PASS。证据摘要见 `docs/hardware/T039_IMU_MOCK_LIVE_CAPTURE_20260623.md`。
- TIMU-001：真实 IMU bring-up 证据门完成。新增 `docs/hardware/TIMU_001_REAL_IMU_BRINGUP_PLAN.md`，确认当前 Waveshare ESP32-S3-SIM7670G-4G P0 setup 没有仓库证据证明真实 IMU 已存在/接线/采样；采购清单候选为 `ST STEVAL-MKI227KA（LSM6DSV16X）` 和 `SensorTile.box PRO`，但二者仍是候选/数据采集路径，不是已验证产品 BOM；文档定义了后续设置 `imu_hardware_present=true`、`imu_driver_enabled=true`、`imu_sample_mock=false` 前必须满足的身份探测、接线、ODR、FIFO/中断、样本率、quality gate 和 replay 门槛。
- TCAM-001：摄像头 smoke live capture 完成。`firmware/camera_smoke` 已改为启动后延迟 5 秒并连续采集 3 帧，ESP32-S3 `COM4` 实机刷写通过；UART 证据显示摄像头识别为 OV5640，采集到 3 张 QVGA JPEG，bytes 分别为 `2893/3708/3700`，checksum 分别为 `a5db84d7/94301dec/7a151b26`，SOI/EOI 均为 `ffd8/ffd9`。证据摘要见 `docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`。
- HDBRIDGE-001：双板 PC Bridge PoC 完成。新增 `pc_simulator/board_bridge.py` 和 `scripts/board_bridge.py`，支持 JSONL/stdin 形式的 `wearable_node` / `connectivity_node` `hello` 绑定、`motion_event` 归一化、撞击/跌倒阈值下的 `ask_user` / `request_location` 下行命令记录，以及 M1 recorder 的 `imu_motion` frame；该 frame 显式标为 `source_availability=bridge_uplink`、`source_status=unverified`，不声明 AMOLED 板 QMI8658 已真实验证。证据摘要见 `docs/hardware/HDBRIDGE_001_DUAL_BOARD_PC_BRIDGE_POC_20260623.md`。
- HDBRIDGE-002：AMOLED 板 USB CDC + QMI8658 最小样本窗口完成。新增 `firmware/amoled_bridge`，ESP32-S3-Touch-AMOLED-2.06 `COM9` 实机刷写通过，USB JSONL 捕获 1 条 `hello`、1 条 `imu_whoami`、40 条 `imu_sample` 和 1 条 `amoled_bridge_done`；AXP2101 chip id `0x4A`，QMI8658 WHOAMI `0x05`，`read_errors=0`，`not_ready_count=0`。PC Bridge 存储 43 条事件，recording 生成 40 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。证据摘要见 `docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md`；IMU 仍标记 `bridge_uplink/unverified`，不是正式 IMU 验收。
- TIMU-002：QMI8658 样本质量与方向验收门完成。新增 `pc_simulator/imu_quality.py` 和 `scripts/analyze_imu_quality.py`，对 HDBRIDGE-002 live JSONL 进行身份、完整性、时序、QMI timestamp、静置 1g 方向、gyro 静置 sanity 和 source 边界分析；WHOAMI、完整性、静置方向、gyro sanity 均 PASS，但 device timing FAIL：目标 `50 ms / 20 Hz`，实测均值约 `82.31 ms / 12.15 Hz`。证据摘要见 `docs/hardware/TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md`；formal IMU acceptance 仍为 false。
- TIMU-003：QMI8658 采样时序修复与更长窗口复测完成。`firmware/amoled_bridge` 改为 `vTaskDelayUntil` 固定周期采样，样本时间戳改为采样开始时刻，窗口扩展到 120 样本；ESP32-S3-Touch-AMOLED-2.06 `COM9` 刷写和 live capture 通过。TIMU-003 报告显示 120 条 `imu_sample`，`missed_deadlines=0`，`max_sample_work_ms=42`，目标 `50 ms / 20 Hz`，实测均值约 `49.99 ms / 20.00 Hz`，所有 analyzer quality gates PASS。PC Bridge 存储 123 条事件，recording 生成 120 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。证据摘要见 `docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md`；formal IMU acceptance 仍为 false，因为 source 仍保持 `bridge_uplink/unverified`。
- TIMU-004A：QMI8658 姿态/校准分析器和单姿态实测完成。新增 `pc_simulator/imu_pose_quality.py` 和 `scripts/analyze_imu_pose_quality.py`，支持 `LABEL=JSONL` 多姿态输入、axis/sign 标签匹配、静置 1g 检查、保守校准 offset、motion sanity 和 source 边界；`COM9` 实机复测捕获 120 条 `imu_sample`，单姿态 `z_negative` 静置通过，平均轴约 `[56.63, 22.98, -1030.48] mg`，offset 约 `[56.6, 23.0, -30.5] mg`。PC Bridge 存储 123 条事件、0 skipped，recording 生成 120 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。证据摘要见 `docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md`；TIMU-004 总验收仍未通过，因为未采集多姿态或手动旋转/轻敲 motion window。
- TIMU-004B：QMI8658 人工三姿态实采完成。新增并使用 `scripts/capture_amoled_qmi8658_pose_set.ps1`，在 `COM9` 上完成 `z_negative`、`x_positive`、`y_positive` 三个静态姿态窗口，每个窗口 120 条 `imu_sample`，timing 约 `20.00 Hz`。三姿态 analyzer 中 `pose_static_quality`、`pose_count`、`axis_coverage`、`pose_label_match`、`calibration_offset`、`pose_or_motion_evidence` 和 `source_boundary` 均 PASS，`quality_gates_passed=true`；M1 合并闭环 PC Bridge 存储 369 条事件、0 skipped，recording 生成 360 条 `imu_motion` frame，quality gate PASS `0.91`，replay PASS，360 条输出均为 `risk_type=none`。证据摘要见 `docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md`；formal IMU acceptance 仍为 false，因为 source 仍是 `bridge_uplink/unverified`，且 motion window、安装/FIFO/中断/功耗/真实后端仍待后续任务。
- TIMU-005：QMI8658 motion window 实采完成。`scripts/capture_amoled_qmi8658_pose_set.ps1` 新增 `-MotionOnly` 和 `-ExistingPose LABEL=PATH`，复用 TIMU-004B 三姿态证据并在 `COM9` 捕获 1 个旋转/轻敲 motion window；motion 文件为 `pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`，包含 123 条 JSONL、120 条 `imu_sample`，timing 约 `49.99 ms / 20.00 Hz`，`missed_deadlines=0`。pose/motion analyzer 中 `motion_sanity` PASS，accel magnitude range 约 `490.04 mg`，gyro peak 约 `201921 mdps`，总体 `quality_gates_passed=true`；M1 合并闭环 PC Bridge 存储 492 条事件、0 skipped，recording 生成 480 条 `imu_motion` frame，quality gate PASS `0.91`，replay PASS，480 条输出均为 `risk_type=none`。证据摘要见 `docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md`；formal IMU acceptance 仍为 false，因为 source 仍是 `bridge_uplink/unverified`，且连续长窗口、安装/FIFO/中断/功耗/真实后端仍待后续任务。
- TIMU-006：QMI8658 连续长窗口实采完成。`firmware/amoled_bridge` 新增 ESP-IDF 配置项 `CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT=600` 和 `CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS=50`，并输出 `requested_window_ms`；`pc_simulator/imu_quality.py` 新增 `--long-window` 和 `device_jitter` gate；`scripts/capture_amoled_qmi8658_pose_set.ps1` 新增 `-M1Limit`。固件 build PASS，`COM9` flash PASS；live capture 文件为 `pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl`，包含 603 条 JSONL、600 条 `imu_sample`，`samples_emitted=600`，`read_errors=0`，`not_ready_count=0`，`missed_deadlines=0`，`max_sample_work_ms=42`。长窗口 analyzer PASS，observed mean interval 约 `49.9983 ms`，observed sample rate 约 `20.0007 Hz`，max interval deviation `1.0 ms`，jitter limit `10.0 ms`；M1 recording 生成 600 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS，600 条输出均为 `risk_type=none`。证据摘要见 `docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md`；formal IMU acceptance 仍为 false，因为 source 仍是 `bridge_uplink/unverified`，且真实后端、安装/FIFO/中断/功耗仍待后续任务。
- TIMU-007：`platform_imu` real backend PoC 边界完成。`firmware/mqtt_heartbeat/components/platform_imu` 现在新增 `platform_imu_sample()` 后端中立入口、`platform_imu_backend_t`、后端元数据 snapshot、ESP-IDF Kconfig 后端选择，以及显式 opt-in 的 QMI8658 I2C WHOAMI/read sample 路径；默认 `sdkconfig.defaults` 仍为 `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y`，`app_main.c` 不再直接调用 `platform_imu_sample_mock()`。默认 P0 主固件 build PASS，仍发布 `imu_source=mock_stationary`、`imu_hardware_present=false`、`imu_driver_enabled=false`、`imu_sample_mock=true`；另用 `sdkconfig.qmi8658.defaults` 完成 QMI8658 后端 compile-only build PASS。证据摘要见 `docs/hardware/TIMU_007_PLATFORM_IMU_REAL_BACKEND_POC_20260624.md`；formal IMU acceptance 仍为 false，因为尚未完成显式 QMI8658 后端 live capture、产品安装、FIFO/中断、校准和功耗门。
- TIMU-008：`platform_imu` QMI8658 后端 live capture 完成。`sdkconfig.qmi8658.defaults` 现在使用独立 `device_id=ego-link-amoled-qmi8658` 和独立 status/event topic，并启用 40 条 boot sample 窗口；`COM9` 实机刷写 `firmware/mqtt_heartbeat` QMI profile 通过，UART 证据显示 AXP2101 chip id `0x4a`、QMI8658 WHOAMI `0x05`、40 条 `PLATFORM_IMU_BOOT_CAPTURE_SAMPLE` 且 `source=qmi8658_i2c`、`hardware_present=true`、`driver_enabled=true`、`mock=false`。LAN MQTT broker `192.168.31.250:1883` 收到 8 条 PC-side 消息，其中 4 条 `sensor_sample/device_health` 均为 `imu_sample_mock=false`；M1 recording 生成 8 条 sensor frame，quality gate PASS `0.94`，replay PASS，8 条输出均为 `risk_type=none`。证据摘要见 `docs/hardware/TIMU_008_PLATFORM_IMU_QMI_BACKEND_LIVE_CAPTURE_20260624.md`；formal IMU acceptance 仍为 false，因为产品安装、最终校准、FIFO/DRDY 中断、低功耗唤醒和功耗波形仍未验收。
- TIMU-009A：IMU engineering calibration boundary 完成。新增 `pc_simulator/imu_calibration.py` 和 `scripts/generate_imu_calibration_profile.py`，复用 TIMU-004B 三姿态 QMI8658 live captures 生成工程校准 profile；当前轴向映射为 x/y/z 同轴同号，临时 accel offset 估计约 `[48.0, -10.3, -24.0] mg`，gyro signed bias 未估计。证据 profile 见 `docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md` / `.json`；该 profile 明确 `stage=engineering`、`production_ready=false`、`formal_imu_acceptance=false`，并列出硬件、安装、外壳、ODR/FIFO/中断、电源轨、后端和夹具变化后的 recalibration triggers。它可用于工程 bring-up 和回归检查，但不可用于量产校准、MotionNet 训练、跌倒/碰撞产品声明或电池/功耗声明。
- TIMU-009B：IMU product acceptance preflight gate 完成。新增 `pc_simulator/imu_acceptance.py` 和 `scripts/check_imu_acceptance.py`，把正式 IMU 验收拆成 10 个硬件证据 gate：安装方向冻结、夹具定义、最终 accel 校准、signed gyro bias、温漂、FIFO/DRDY、真实电流波形、后端 quality gate、M1 recording/replay 和 recalibration trigger review。当前报告 `docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md` / `.json` 预期 FAIL：`formal_imu_acceptance=false`、`motionnet_training_enabled=false`，全部 gate 因缺少 hardware-observed artifact 而失败，且 TIMU-009A profile 仍为 engineering stage。
- TIMU-009C-A：QMI8658 backend readiness capture 完成。未重新刷写固件，复用 TIMU-008 已在 AMOLED 板 `COM9` 上运行的 QMI8658 MQTT backend profile，通过 LAN broker `192.168.31.250:1883` 有限捕获 8 条消息：4 条 `sensor_sample/device_health` 和 4 条 `mqtt_status`，`seq=11062..11069`。4 条 IMU 样本均带 `imu_source=qmi8658_i2c`、`imu_hardware_present=true`、`imu_driver_enabled=true`、`imu_sample_mock=false`；示例 `seq=11062` accel `[46,-29,-1027] mg`、gyro `[-218,1656,-234] mdps`，`seq=11068` accel `[46,-30,-1026] mg`、gyro `[-187,1546,-78] mdps`。M1 recording 生成 8 条 sensor frame，quality gate PASS `0.94`，replay PASS，8 条输出均为 `risk_type=none`。证据摘要见 `docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md`；formal IMU acceptance 仍为 false，因为安装方向、最终校准、FIFO/DRDY、低功耗唤醒和功耗波形仍未验收。
- TIMU-009C-B0：IMU product mounting evidence template 完成。`pc_simulator/imu_acceptance.py` 现在可生成 operator evidence manifest template；新增模板 `docs/hardware/TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.json` / `.md`，覆盖 TIMU-009B 的 10 个 gate，并把每个 gate 默认保持为 `status=pending`、`artifact=null`、`observed_on_hardware=false`。模板引用 TIMU-009C-A 后端 readiness 报告作为参考 artifact，但不把它升级成正式产品安装/校准/FIFO/功耗证据；`formal_imu_acceptance=false`、`motionnet_training_enabled=false` 继续保持。
- TIMU-009C-B1：QMI8658 temporary fixture static capture 完成。用户已将 AMOLED/QMI8658 板用双面胶固定到纸盒临时夹具；通过 LAN broker `192.168.31.250:1883` 捕获 16 条 MQTT 消息，其中 8 条 `sensor_sample/device_health` 为真实 QMI8658 样本，`imu_source=qmi8658_i2c`、`imu_sample_mock=false`，`seq=11728..11743`。静态窗口 accel 均值约 `[25.38,92.25,-1020.50] mg`，accel magnitude 均值 `1024.98 mg`、span `1.18 mg`；M1 recording 生成 16 条 sensor frame，quality gate PASS `0.94`，replay PASS，16 条输出均为 `risk_type=none`。新增证据摘要、manifest 和 preflight：`docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md`、`docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_EVIDENCE_20260624.json`、`docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_PREFLIGHT_20260624.md` / `.json`；preflight 仍预期 FAIL，`formal_imu_acceptance=false`，因为这是临时夹具 partial evidence，不是最终产品安装/校准/FIFO/功耗验收。
- TIMU-009C-B2：QMI8658 labeled fixture repeatability capture 完成。用户已在纸盒临时夹具上标出 `TOP`、`OUT`、`USB/CABLE`；通过 LAN broker `192.168.31.250:1883` 捕获 20 条 MQTT 消息，其中 10 条 `sensor_sample/device_health` 为真实 QMI8658 样本，`imu_source=qmi8658_i2c`、`imu_sample_mock=false`，`seq=11976..11995`。静态窗口 accel 均值约 `[48.60,94.10,-1020.40] mg`，accel magnitude 均值 `1025.88 mg`、span `2.03 mg`；相对 B1，accel magnitude 均值只差 `0.90 mg`，Z 均值只差 `0.10 mg`，主重力轴保持 negative Z。M1 recording 生成 20 条 sensor frame，quality gate PASS `0.94`，replay PASS，20 条输出均为 `risk_type=none`。新增证据摘要、manifest 和 preflight：`docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE_20260624.md`、`docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_EVIDENCE_20260624.json`、`docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_PREFLIGHT_20260624.md` / `.json`；preflight 仍预期 FAIL，`formal_imu_acceptance=false`，因为这是标记后临时夹具 repeatability partial evidence，不是最终产品安装/校准/FIFO/功耗验收。
- DEMO-001：Demo-first 最小安全循环完成。新增 `pc_simulator/minimal_safety_demo.py` 和 `scripts/run_minimal_safety_demo.py`，可在没有 AMOLED 触摸和真实 GNSS 的情况下先跑通核心产品闭环：`motion_event -> ask_user -> user_confirmation -> request_location -> command_ack -> location_report -> safety_event`。Demo 会写入 event log、session recording 和 quality report；`user_confirmation` / `command_ack` 已进入 session recorder，`imu_motion` 可被 session replay 重新喂给规则路由。该 Demo 是产品体验原型，不声明真实报警、真实拨号、AMOLED 屏幕触摸或 SIM7670G 板载 GNSS ACK 已完成。
- 模型上下文 v0.2 已纳入：新增 `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md` 和 `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`，明确 M0 是规则基线，下一阶段先做 M1 数据基础，不直接训练神经网络。

## 当前建议任务

当前没有 `status: active` 的任务包。`DEMO-001` 和 `DEMO-004` 已移动到 `docs/tasks/done/`。下一步先完成 control-plane baseline 的提交/远端/分支策略确认；完成后再进入 DEMO-005 real GNSS fix evidence。上一条指向 DEMO-002 AMOLED 屏幕/触摸确认的建议已被后续 DEMO-004 完成状态取代。

## 后续任务路线

- T035：session 文件哈希与完整性校验，补齐 manifest / quality gate 的数据不可篡改基础。已完成。
- T036：PC session import / replay，按 recording 重建事件流并调用现有 RuleRouter，验证可回放。已完成。
- T037：最小 annotation CLI 或本地页面，写入 `safe`、`needs_help`、`false_alarm`、`cancelled`、`no_response`。已完成 CLI。
- T038：硬件可用性 smoke / 决策门。已完成当前最小闭环验证；IMU、麦克风、物理 SOS GPIO、SD、真实电量路径和 ESP32 侧 SIM7670G 控制仍保持未验证声明。
- HARCH-001：审计 ESP32/SIM7670G 平台耦合。已完成。
- HARCH-002：每次只抽象一个硬件接口。首个切片 HARCH-002A `platform_power` 已完成。
- HPWR-001：加入功耗状态和测量标记。已完成 log/mock 事件、累计时长、串口 marker 和场景模板；真实 GPIO marker、电流、续航仍未验证。
- HDATA-001：继续 M1 真实数据采集闭环。已完成 HPWR 固件刷写后的 clean live capture、GNSS no-fix probe、T039 IMU mock live payload capture、recording quality gate 和 replay；后续可扩展户外 GNSS fix、真实 IMU、麦克风、SD 和功耗仪器采集。
- T039：IMU mock/driver interface 和 ring buffer 骨架。已完成并完成 mock payload 真板 MQTT 采集；真实 IMU 确认后再接入采样。
- TIMU-001：真实 IMU bring-up 证据门。已完成；HDBRIDGE-002 已确认 AMOLED 板 QMI8658 身份和短窗口样本，TIMU-002 已完成首轮质量分析并发现 timing gate 失败。
- TIMU-002：QMI8658 样本质量与安装方向验证。已完成分析工具和 HDBRIDGE-002 live capture 报告；身份/完整性/静置方向通过，但设备采样时序未达目标，formal IMU acceptance=false。
- TIMU-003：QMI8658 采样时序修复与更长窗口复测。已完成 `vTaskDelayUntil` 固定周期采样、120 样本 live capture、analyzer quality gates、PC Bridge、recording、quality gate 和 replay；formal IMU acceptance=false。
- TIMU-004A：QMI8658 姿态/校准分析器和单姿态复测。已完成 pose/motion analyzer、Windows UTF-8 BOM JSONL 容错、`COM9` 单姿态 `z_negative` live capture、timing cross-check、PC Bridge、recording、quality gate 和 replay；multi-pose/motion evidence 仍失败，formal IMU acceptance=false。
- TIMU-004B：QMI8658 人工三姿态采集。已完成 `z_negative`、`x_positive`、`y_positive` 三姿态证据和 M1 闭环；formal IMU acceptance=false。
- TIMU-005：QMI8658 motion window / real backend 前置。已完成 `-MotionOnly` 旋转/轻敲窗口实采、pose/motion analyzer、PC Bridge、recording、quality gate 和 replay；formal IMU acceptance=false。
- TIMU-006：QMI8658 连续长窗口 / `platform_imu` real backend PoC 前置。已完成 600 样本长窗口、long-window timing/jitter gate、PC Bridge、recording、quality gate 和 replay；formal IMU acceptance=false。
- TIMU-007：`platform_imu` real backend PoC。已完成；默认 mock 后端保持不变，QMI8658 I2C 后端仅通过 Kconfig 显式 opt-in，formal IMU acceptance=false。
- TIMU-008：`platform_imu` QMI8658 后端 live capture。已完成；AMOLED 板 `COM9` 上的 QMI profile 已捕获 boot sample、MQTT `sensor_sample/device_health`、M1 recording、quality gate 和 replay；formal IMU acceptance=false。
- TIMU-009A：IMU engineering calibration boundary。已完成；profile 由 TIMU-004B 三姿态实采生成，`production_ready=false`，用于工程 bring-up，不作为量产校准或正式 IMU acceptance。
- TIMU-009B：IMU product acceptance preflight gate。已完成；当前报告预期 FAIL，列出所有缺失硬件证据并保持 `formal_imu_acceptance=false`。
- TIMU-009C-A：QMI8658 backend readiness capture。已完成；当前 QMI profile 未重刷即可收到 4 条真实 QMI8658 sensor sample 并通过 M1 quality/replay；formal IMU acceptance=false。
- TIMU-009C-B0：IMU product mounting evidence template。已完成；10 个正式验收 gate 全部以 `pending` 模板固化，等待硬件 artifact。
- TIMU-009C-B1：QMI8658 temporary fixture static capture。已完成；纸盒临时夹具下捕获 8 条真实 QMI8658 样本并通过 M1 quality/replay；formal IMU acceptance=false。
- TIMU-009C-B2：QMI8658 labeled fixture repeatability capture。已完成；标记后纸盒夹具下捕获 10 条真实 QMI8658 样本并通过 M1 quality/replay；formal IMU acceptance=false。
- TIMU-009C-B3：IMU 标记夹具等效校准 pose set 或 FIFO/DRDY 前置验证。建议下一步；重点是在保持标签可追溯的前提下补更多姿态或中断路径证据。
- TCAM-001：摄像头 smoke live capture。已完成 3 帧真实 JPEG UART 证据；后续如要进入产品路径，需要单独做 `platform_camera`、隐私授权、hash/retention、功耗状态和按需采集。
- HDBRIDGE-001：双板 PC Bridge PoC。已完成 PC-only 消息桥、命令记录和 `imu_motion` recording 入口。
- HDBRIDGE-002：AMOLED USB CDC + QMI8658 最小样本窗口。已完成 live `hello`、QMI8658 WHOAMI、40 条真实 I2C 样本、PC Bridge、recording、quality gate 和 replay；TIMU-002 已确认首轮样本 timing 未达目标，TIMU-003 已修复到约 `49.99 ms / 20.00 Hz`，剩余安装方向、校准、FIFO/中断和功耗验收转入 TIMU-004 之后。
- TIMU-004：QMI8658 多姿态方向/校准与真实后端准备。TIMU-004A 已完成单姿态工具和 live evidence，TIMU-004B 已完成三姿态静态证据门；但 formal IMU acceptance 仍为 false，真实 `platform_imu` 后端、motion window、FIFO/中断、功耗和安装验收仍需后续任务，不进入 MotionNet 数据采集声明。

## 最近验证

- `python -m unittest quality_tests.test_amoled_pose_capture_script -v`：通过，4 个测试全部成功；覆盖 TIMU-005 采集脚本的 `-MotionOnly`、`-ExistingPose LABEL=PATH`、UTF-8 no BOM analyzer log 和 PowerShell 重定向回归。
- TIMU-005 motion-only live capture：通过。复用 TIMU-004B `z_negative` / `x_positive` / `y_positive` 三姿态文件，在 `COM9` 捕获 `pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`，123 条 JSONL、120 条 `imu_sample`，`imu_whoami=true`，`amoled_bridge_done=true`。
- TIMU-005 pose/motion analyzer：通过。三姿态质量门保持 PASS，motion window `motion_sanity` PASS；accel magnitude range 约 `490.04 mg`，gyro peak 约 `201921 mdps`，`quality_gates_passed=true`，`formal_imu_acceptance=false`，reason 为 `source_status_unverified`。
- TIMU-005 M1 闭环：通过。`board_bridge` 存储 492 条事件、0 skipped；`session_recorder` 生成 480 条 `imu_motion` frame；`inspect_session_recording` PASS `quality_score=0.91`；`replay_session_recording` PASS，480 条输出全部 `risk_type=none`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-005 脚本、硬件矩阵和文档同步后通过，155 个测试全部成功。
- `python -m unittest quality_tests.test_amoled_bridge_firmware quality_tests.test_amoled_pose_capture_script quality_tests.test_imu_quality -v`：通过，15 个测试全部成功；覆盖 TIMU-006 firmware 配置、采集脚本 `-M1Limit` 和 long-window timing/jitter gate。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`：TIMU-006 通过，生成 `firmware/amoled_bridge/build/egolink_amoled_bridge.bin`，binary size `0x38650`。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash`：TIMU-006 通过，识别 ESP32-S3、PSRAM 8MB、MAC `02:00:00:00:00:01`，写入并 hard reset 成功。
- TIMU-006 long-window live capture：通过。`pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl` 包含 603 条 JSONL、600 条 `imu_sample`，`samples_emitted=600`，`read_errors=0`，`not_ready_count=0`，`missed_deadlines=0`，`max_sample_work_ms=42`。
- TIMU-006 long-window analyzer：通过。`--long-window --min-samples 500 --max-interval-jitter-ms 10` 下 `quality_gates_passed=true`；observed mean interval 约 `49.9983 ms`，observed sample rate 约 `20.0007 Hz`，max interval deviation `1.0 ms`，QMI timestamp monotonic，source boundary PASS。
- TIMU-006 M1 闭环：通过。`board_bridge` 存储 603 条事件、0 skipped；`session_recorder` 生成 600 条 `imu_motion` frame；`inspect_session_recording` PASS `quality_score=0.94`；`replay_session_recording` PASS，600 条输出全部 `risk_type=none`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-006 长窗口固件、analyzer、硬件矩阵和文档同步后通过，157 个测试全部成功。
- `python -m unittest quality_tests.test_platform_imu_firmware -v`：TIMU-007 通过，7 个测试全部成功；覆盖默认 mock 后端、显式 QMI8658 opt-in、后端中立 `platform_imu_sample()`、ring buffer、payload 字段和 README 边界声明。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`：TIMU-007 默认 mock 配置通过，生成 `firmware/mqtt_heartbeat/build/egolink_mqtt_heartbeat.bin`，binary size `0xd9170`。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/qmi -D SDKCONFIG=build/qmi/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build`：TIMU-007 QMI8658 opt-in compile-only build 通过，binary size `0xde340`；未 flash，未声明 live QMI8658 backend 可用。
- `python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_hardware_sensor_matrix -v`：TIMU-007 targeted 验证通过，15 个测试全部成功。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-007 后端边界、文档和硬件矩阵同步后通过，158 个测试全部成功。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build`：TIMU-008 QMI backend profile build 通过，binary size `0xde6d0`。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" -p COM9 flash`：TIMU-008 刷写 ESP32-S3-Touch-AMOLED-2.06 通过。
- UART capture `pc_simulator/runtime/timu008/timu008-platform-imu-qmi-boot-window-uart.log`：TIMU-008 通过；313 行日志，AXP2101 `0x4a`、QMI8658 WHOAMI `0x05`，40 条 boot sample 均为 `mock=false`，并观察到 `MQTT_SENSOR_PUBLISH_OK` payload。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu008\timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl --max-messages 8 --wait-seconds 45`：TIMU-008 PC-side MQTT capture 通过，收到 8 条消息，其中 4 条 `sensor_sample/device_health` 为 `imu_sample_mock=false`。
- `python scripts\session_recorder.py ...` / `python scripts\inspect_session_recording.py ...` / `python scripts\replay_session_recording.py ...`：TIMU-008 M1 闭环通过，8 条 sensor frame，quality gate PASS `0.94`，replay PASS，8 条输出均为 `risk_type=none`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-008 代码、文档和硬件矩阵同步后通过，158 个测试全部成功。
- `python -m unittest quality_tests.test_imu_calibration quality_tests.test_imu_pose_quality quality_tests.test_hardware_sensor_matrix -v`：TIMU-009A focused verification 通过，14 个测试全部成功，覆盖工程校准 profile、pose quality 和硬件矩阵证据路径。
- `python scripts\generate_imu_calibration_profile.py --pose z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --pose x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --pose y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --profile-id timu009a-qmi8658-engineering-20260624 --hardware-profile esp32-s3-touch-amoled-2.06-qmi8658 --output-json docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --markdown docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md`：TIMU-009A profile 重新生成通过。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009A 工具、profile、文档和硬件矩阵同步后通过，162 个测试全部成功。
- `python scripts\check_imu_acceptance.py --calibration-profile docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --report-id timu009b-qmi8658-product-acceptance-preflight-20260624 --output-json docs\hardware\TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.json --markdown docs\hardware\TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md`：TIMU-009B preflight report 生成通过，当前预期 FAIL，`formal_imu_acceptance=false`，全部硬件证据 gate 为 `evidence_missing`。
- `python -m unittest quality_tests.test_imu_acceptance quality_tests.test_imu_calibration quality_tests.test_hardware_sensor_matrix -v`：TIMU-009B focused verification 通过，14 个测试全部成功，覆盖 missing evidence、hardware-observed requirement、engineering profile blocker 和未来 all-evidence-pass contract。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009B 工具、preflight report、文档和硬件矩阵同步后通过，167 个测试全部成功。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c\timu009c-qmi-backend-readiness-20260624-1710.events.jsonl --max-messages 8 --wait-seconds 45`：TIMU-009C-A live MQTT capture 通过，收到 8 条消息，其中 4 条 `sensor_sample/device_health` 为 `imu_sample_mock=false`。
- `python scripts\session_recorder.py ...` / `python scripts\inspect_session_recording.py ...` / `python scripts\replay_session_recording.py ...`：TIMU-009C-A M1 闭环通过，8 条 sensor frame，quality gate PASS `0.94`，replay PASS，8 条输出均为 `risk_type=none`。
- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：TIMU-009C-A focused verification 通过，5 个测试全部成功，覆盖新增后端 readiness 报告路径和硬件矩阵同步。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009C-A 文档、状态和硬件矩阵同步后通过，167 个测试全部成功。
- `python scripts\check_imu_acceptance.py --calibration-profile docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --report-id timu009c-b0-qmi8658-product-mounting-evidence-template-20260624 --evidence-template-json docs\hardware\TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.json --evidence-template-markdown docs\hardware\TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.md --manifest-id timu009c-b0-qmi8658-product-mounting-evidence-template-20260624 --target-mounting-direction pending-final-wearable-orientation --reference-artifact docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md`：TIMU-009C-B0 evidence template 生成通过，10 个 gate 全部保持 `pending`。
- `python -m unittest quality_tests.test_imu_acceptance -v`：TIMU-009C-B0 focused verification 通过，7 个测试全部成功，覆盖 template builder、CLI 写出、hardware-observed requirement 和既有 preflight 行为。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009C-B0 工具、模板 artifact、文档和硬件矩阵同步后通过，169 个测试全部成功。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c_b1\timu009c-b1-temporary-fixture-static-20260624-1735.events.jsonl --max-messages 16 --wait-seconds 90`：TIMU-009C-B1 live MQTT capture 通过，收到 16 条消息，其中 8 条 `sensor_sample/device_health` 为真实 QMI8658 样本。
- `python scripts\session_recorder.py ...` / `python scripts\inspect_session_recording.py ...` / `python scripts\replay_session_recording.py ...`：TIMU-009C-B1 M1 闭环通过，16 条 sensor frame，quality gate PASS `0.94`，replay PASS，16 条输出均为 `risk_type=none`。
- `python scripts\check_imu_acceptance.py --calibration-profile docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --evidence-manifest docs\hardware\TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_EVIDENCE_20260624.json --report-id timu009c-b1-qmi8658-temporary-fixture-preflight-20260624 --output-json docs\hardware\TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_PREFLIGHT_20260624.json --markdown docs\hardware\TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_PREFLIGHT_20260624.md --title "# TIMU-009C-B1 QMI8658 Temporary Fixture Preflight"`：TIMU-009C-B1 preflight 生成通过，当前预期 FAIL，partial/pending gates 不提升为 formal acceptance。
- `python -m unittest quality_tests.test_hardware_sensor_matrix quality_tests.test_imu_acceptance -v`：TIMU-009C-B1 focused verification 通过，12 个测试全部成功，覆盖新增 B1 evidence paths 和既有 IMU acceptance gate 行为。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009C-B1 文档、证据 artifact 和硬件矩阵同步后通过，169 个测试全部成功。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c_b2\timu009c-b2-labeled-temporary-fixture-static-20260624-1805.events.jsonl --max-messages 20 --wait-seconds 120`：TIMU-009C-B2 live MQTT capture 通过，收到 20 条消息，其中 10 条 `sensor_sample/device_health` 为真实 QMI8658 样本。
- `python scripts\session_recorder.py ...` / `python scripts\inspect_session_recording.py ...` / `python scripts\replay_session_recording.py ...`：TIMU-009C-B2 M1 闭环通过，20 条 sensor frame，quality gate PASS `0.94`，replay PASS，20 条输出均为 `risk_type=none`。
- `python scripts\check_imu_acceptance.py --calibration-profile docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --evidence-manifest docs\hardware\TIMU_009C_B2_QMI8658_LABELED_FIXTURE_EVIDENCE_20260624.json --report-id timu009c-b2-qmi8658-labeled-fixture-preflight-20260624 --output-json docs\hardware\TIMU_009C_B2_QMI8658_LABELED_FIXTURE_PREFLIGHT_20260624.json --markdown docs\hardware\TIMU_009C_B2_QMI8658_LABELED_FIXTURE_PREFLIGHT_20260624.md --title "# TIMU-009C-B2 QMI8658 Labeled Fixture Preflight"`：TIMU-009C-B2 preflight 生成通过，当前预期 FAIL，partial/pending gates 不提升为 formal acceptance。
- `python -m unittest quality_tests.test_hardware_sensor_matrix quality_tests.test_imu_acceptance -v`：TIMU-009C-B2 focused verification 通过，12 个测试全部成功，覆盖新增 B2 evidence paths 和既有 IMU acceptance gate 行为。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-009C-B2 文档、证据 artifact 和硬件矩阵同步后通过，169 个测试全部成功。
- `python -m unittest quality_tests.test_amoled_pose_capture_script quality_tests.test_hardware_sensor_matrix -v`：通过，8 个测试全部成功；覆盖 TIMU-004B 采集脚本静态契约和硬件矩阵证据路径。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -Help`：通过，帮助入口可用。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative -NoPrompt -Analyze -RunM1Loop -SessionId timu004b-qmi8658-preflight-live-20260623-205520 -TimeoutSeconds 35`：通过，捕获 `pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`，123 条 JSONL、120 条 `imu_sample`，`imu_whoami=true`，`amoled_bridge_done=true`，非 JSON 行跳过数为 0；pose analyzer 对 `z_negative` 静态质量、标签匹配、offset 和 source boundary 判定 PASS，但总体 pose/motion quality 因缺少多姿态/运动窗口仍 FAIL；M1 quality gate PASS `0.94`，replay PASS，120 条输出均为 `risk_type=none`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels x_positive -NoPrompt -Analyze -SessionId timu004b-qmi8658-manual-pose1-20260623-2100 -TimeoutSeconds 35`：通过，捕获额外人工姿态 `x_positive`，120 条 `imu_sample`，平均轴约 `[1043.12, -59.83, -49.36] mg`，静态质量/标签/offset/source boundary PASS。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels y_positive -NoPrompt -Analyze -SessionId timu004b-qmi8658-manual-pose2-20260623-2108 -TimeoutSeconds 35`：通过，捕获额外人工姿态 `y_positive`，120 条 `imu_sample`，平均轴约 `[43.92, 1005.44, 7.69] mg`，静态质量/标签/offset/source boundary PASS。
- `python scripts\analyze_imu_pose_quality.py --pose z_negative=... --pose x_positive=... --pose y_positive=... --json --markdown pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.pose_quality.md`：通过，三姿态 quality gates PASS，formal IMU acceptance=false。
- 三姿态 M1 闭环：`board_bridge` 存储 369 条事件、0 skipped；`session_recorder` 生成 360 条 `imu_motion` frame；`inspect_session_recording` PASS `quality_score=0.91`；`replay_session_recording` PASS，360 条输出全部 `risk_type=none`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-004B 三姿态实采文档同步后通过，154 个测试全部成功。
- `python -m unittest quality_tests.test_imu_pose_quality quality_tests.test_imu_quality -v`：通过，10 个测试全部成功；覆盖 TIMU-004 pose/motion analyzer、多姿态通过、单姿态覆盖失败、错标姿态失败、motion sanity 和 UTF-8 BOM JSONL 解析。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash`：TIMU-004A 通过，重新刷写当前 AMOLED bridge，识别 ESP32-S3 USB-Serial/JTAG、PSRAM 8MB、MAC `02:00:00:00:00:01`，hard reset 成功。
- 读取 `COM9` 45 秒：通过，日志写入 `pc_simulator/runtime/timu004-qmi8658-single-pose-live-20260623-203238.jsonl`；捕获 123 条 JSONL，其中 120 条 `imu_sample`，完成记录为 `samples_emitted=120`、`read_errors=0`、`not_ready_count=0`、`timing_mode=vTaskDelayUntil`、`missed_deadlines=0`、`max_sample_work_ms=42`。
- `python scripts\analyze_imu_quality.py pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --json --min-samples 100 --title "# TIMU-004 QMI8658 Single Pose Timing Check"`：通过，120 条样本，observed mean interval `49.99 ms`，observed sample Hz `20.00`，所有 timing analyzer gates PASS，formal IMU acceptance=false。
- `python scripts\analyze_imu_pose_quality.py --pose z_negative=pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --json --markdown docs\hardware\TIMU_004_QMI8658_POSE_QUALITY_20260623.md --title "# TIMU-004 QMI8658 Pose Quality Report"`：运行成功；单姿态 `z_negative` 静置、label match 和 calibration offset gates PASS，但 `pose_count`、`axis_coverage`、`motion_sanity` 和 `pose_or_motion_evidence` FAIL，TIMU-004 总质量门未通过。
- `python scripts\board_bridge.py --source wearable=pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --event-log pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.events-fixed.jsonl --json`：通过，PC Bridge 存储 123 条事件、跳过 0 行；同时修复 JSONL UTF-8 BOM 首行容错。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.events-fixed.jsonl --session-id timu004-qmi8658-single-pose-live-20260623-203238 --output-dir pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json`：通过，生成 120 条 `imu_motion` sensor frames。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json`：通过，quality gate PASS，`quality_score=0.94`、`errors=0`、`warnings=2`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json`：通过，replay PASS，120 条输入全部为 `risk_type=none`，未生成 `safety_event` 或 `base_command`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-004A 后通过，151 个测试全部成功。
- `python -m unittest quality_tests.test_amoled_bridge_firmware quality_tests.test_imu_quality -v`：通过，8 个测试全部成功；覆盖 TIMU-003 固定周期采样契约、120 样本窗口、timing metadata 和 IMU quality analyzer。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`：TIMU-003 通过，生成更新后的 `egolink_amoled_bridge.bin`，app binary size `0x38620`。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash`：TIMU-003 通过，识别 ESP32-S3 USB-Serial/JTAG，写入并校验 AMOLED bridge 固件，hard reset 成功。
- 读取 `COM9` 35 秒：通过，日志写入 `pc_simulator/runtime/timu003-qmi8658-live-20260623-201436.jsonl`；捕获 123 条 JSONL，其中 120 条 `imu_sample`，完成记录为 `samples_emitted=120`、`read_errors=0`、`not_ready_count=0`、`timing_mode=vTaskDelayUntil`、`missed_deadlines=0`、`max_sample_work_ms=42`。
- `python scripts\analyze_imu_quality.py pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.jsonl --json --min-samples 100 --title "# TIMU-003 QMI8658 Timing Retest Report" --markdown docs\hardware\TIMU_003_QMI8658_TIMING_RETEST_20260623.md`：通过，120 条样本，observed mean interval `49.99 ms`，observed sample Hz `20.00`，所有 quality gates PASS，formal IMU acceptance=false。
- `python scripts\board_bridge.py --source wearable=pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.jsonl --event-log pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.events.jsonl --json`：通过，PC Bridge 存储 123 条事件、跳过 0 行。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.events.jsonl --session-id timu003-qmi8658-live-20260623-201436 --output-dir pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json`：通过，生成 120 条 `imu_motion` sensor frames。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json`：通过，quality gate PASS，`quality_score=0.94`、`errors=0`、`warnings=2`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json`：通过，replay PASS，120 条输入全部为 `risk_type=none`，未生成 `safety_event` 或 `base_command`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：TIMU-003 收口后通过，144 个测试全部成功。
- `python -m unittest quality_tests.test_imu_quality -v`：通过，4 个测试全部成功；覆盖稳定静置样本 gate、82ms 时序偏移 fail、提前 `source_status=verified` 拒绝，以及 JSONL/Markdown report 生成。
- `python scripts\analyze_imu_quality.py pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl --json --markdown docs\hardware\TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md`：通过，报告 43 条消息、40 条 `imu_sample`；identity/completeness/completion/qmi_timestamp/static_orientation/static_gyro/source_boundary 通过，device_timing 失败；formal IMU acceptance=false。
- `python -m unittest quality_tests.test_amoled_bridge_firmware -v`：通过，4 个测试全部成功；覆盖 AMOLED I2C pin map、AXP2101/QMI8658 地址和 WHOAMI、JSONL 输出契约、短窗口边界、`bridge_uplink/unverified` 标记和保守 AXP2101 上电策略。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`：HDBRIDGE-002 通过，生成 `egolink_amoled_bridge.bin`。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash`：HDBRIDGE-002 通过，识别 ESP32-S3 `USB-Serial/JTAG`、PSRAM 8MB、MAC `02:00:00:00:00:01`，写入并校验 AMOLED bridge 固件，hard reset 成功。
- 读取 `COM9` 30 秒：通过，日志写入 `pc_simulator/runtime/hdb002-amoled-live-20260623-194454.jsonl`；捕获 43 条 JSONL，其中 QMI8658 WHOAMI `0x05`，40 条 `imu_sample`，`samples_emitted=40`、`read_errors=0`、`not_ready_count=0`。
- `python scripts\board_bridge.py --source wearable=pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --json`：通过，PC Bridge 存储 43 条事件、跳过 0 行。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --session-id hdb002-amoled-live-20260623-194454 --output-dir pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json`：通过，生成 40 条 `imu_motion` sensor frames。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json`：通过，quality gate PASS，`quality_score=0.94`、`errors=0`、`warnings=2`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json`：通过，replay PASS，40 条输入全部为 `risk_type=none`，未生成 `safety_event` 或 `base_command`。
- `python -m unittest quality_tests.test_board_bridge quality_tests.test_session_recorder quality_tests.test_session_inspector -v`：通过，12 个测试全部成功；覆盖双板 `hello` 角色绑定、`motion_event` 路由命令、`imu_motion` bridge frame、recorder 和 quality gate。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：HDBRIDGE-001 后通过，136 个测试全部成功；包含新增双板 PC Bridge、既有摄像头 smoke、PC/Firmware/Safety/M1 质量门测试。
- `python -m unittest quality_tests.test_camera_smoke_firmware -v`：通过，4 个测试全部成功；覆盖 Waveshare 摄像头 pin map、启动延迟/3 帧采样序列、JPEG 可核验日志字段和 README pass criteria。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash`：TCAM-001 通过，识别 ESP32-S3，写入并校验 `egolink_camera_smoke.bin`，app binary size `0xdce40`，hard reset 成功。
- `esptool.py --chip esp32s3 -p COM4 run` 后读取 COM4 25 秒：通过，日志写入 `pc_simulator/runtime/camera-smoke-live-20260623-1842-uart.log`；识别 OV5640，`CAMERA_SMOKE_INIT_OK`，并采集 3 帧 QVGA JPEG，bytes `2893/3708/3700`、checksum `a5db84d7/94301dec/7a151b26`、SOI/EOI `ffd8/ffd9`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，133 个测试全部成功；包含新增 TCAM-001 摄像头 smoke 固件/文档合同测试和既有 PC/Firmware/Safety/M1 质量门测试。
- `python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_platform_power_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_safety_model_firmware -v`：通过，20 个测试全部成功；覆盖 `platform_imu` API、ring buffer、mock 边界、主固件 payload 字段、sensor payload 栈保护、README caveat，以及既有 power/MQTT/Safety 固件静态契约。
- `python -m unittest quality_tests.test_imu_bringup_plan -v`：通过，覆盖 TIMU-001 文档、当前真实 IMU 不可用边界、`ST STEVAL-MKI227KA（LSM6DSV16X）` / `SensorTile.box PRO` 候选路径，以及 `imu_hardware_present=true` / `imu_sample_mock=false` 前置门槛。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash`：T039-live 修复后通过，识别 ESP32-S3，写入并校验 `egolink_mqtt_heartbeat.bin`，app binary size `0xd8ff0`，hard reset 成功。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --max-messages 10 --wait-seconds 180 --process-safety --safety-process-limit 20`：通过，收到 10 条真实设备 MQTT 消息；其中 3 条 `sensor_sample/device_health seq=13/17/21` 带出 RSSI、heap、mock battery、HPWR marker 和 `imu_*` mock/ring 字段，Safety 处理 3 条样本且均为 `risk_type=none`。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --session-id hdata-001-imu-mock-live-20260623-0926 --output-dir pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json`：通过，生成 clean recording：13 条 source events、10 条 sensor frames、3 条 events。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json`：通过，quality gate PASS，`quality_score=0.94`、`errors=0`、`warnings=2`，frame types 为 `device_health=3`、`device_status=7`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json`：通过，replay PASS，10 条 replayed inputs 全部为 `risk_type=none`，未生成 `safety_event` 或 `base_command`。
- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：通过，5 个测试全部成功；覆盖硬件矩阵中的 mock/unknown 边界、证据路径和 M1 阻塞项。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash`：通过，识别 ESP32-S3，写入并校验 `egolink_mqtt_heartbeat.bin`，hard reset 成功。
- `python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports`：通过，报告为 `reports/board_validation/20260623-090047/probe.md`；ESP32-S3 CH343 为 `COM4`，SIM7670G AT 身份在 `COM6/COM7` 可达，SIM ready，CSQ `18,0`，LTE registered/attached 为 true，RNDIS 可见。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --max-messages 6 --wait-seconds 120 --process-safety --safety-process-limit 20`：通过，收到 6 条真实设备 MQTT 消息；其中 `sensor_sample/device_health seq=25/29` 带出 RSSI、heap、mock battery 和 HPWR marker 字段，Safety 处理 2 条样本且均为 `risk_type=none`。
- `python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2 --device-id ego-link-001 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl`：通过，报告为 `reports/gnss_validation/20260623-090637/gnss_probe.md`；`COM6/COM7` AT 可达，`gnss_power_state=1`，室内 no-fix，并写入 `location_report seq=31 fix=false`。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --session-id hdata-001-hpwr-live-20260623-0906 --output-dir pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json`：通过，生成 clean recording：9 条 source events、7 条 sensor frames、2 条 events。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json`：通过，quality gate PASS，`quality_score=0.94`、`errors=0`、`warnings=2`，frame types 为 `device_health=2`、`device_status=4`、`gnss_report=1`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json`：通过，replay PASS，7 条 replayed inputs 全部为 `risk_type=none`，未生成 `safety_event` 或 `base_command`。
- `python -m unittest quality_tests.test_platform_power_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_safety_model_firmware -v`：通过，14 个测试全部成功；覆盖 `platform_power` 组件、HPWR marker、mock battery 边界、主固件接入、README 边界声明和既有 MQTT/Safety 固件静态契约。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，127 个测试全部成功。
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`：通过，`firmware/mqtt_heartbeat` 生成包含 `platform_imu` 的 ESP32-S3 固件镜像，app binary size `0xd8fe0`。
- `python -m unittest quality_tests.test_session_annotations quality_tests.test_session_inspector quality_tests.test_session_replay -v`：通过，13 个测试全部成功；覆盖 annotation 追加后 manifest/hash 刷新、quality gate 摘要、CLI target index、replay annotation 摘要和既有 inspector/replay 行为。
- `python scripts\annotate_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --list-targets --json`：通过，只读列出真实 T038 recording 的 12 个可标注 target；其中 index 4 是当前硬件 `sensor_sample/device_health seq=21548`。本次未写入真实用户标签。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，111 个测试全部成功。
- `python scripts\egolink_board_probe.py --probe-all-sim-ports --esp-listen-seconds 8`：通过，报告为 `reports/board_validation/20260622-181619/probe.md`；ESP32-S3 CH343 为 `COM4`，SIM7670G AT 口 `COM6/COM7` 识别为 `SIM7670G-MNGV`，RNDIS 可见，SIM 已插入，LTE registered/attached 为 true，ESP32 日志观察到 `MQTT_HEARTBEAT_PUBLISH_OK`。
- `python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2`：通过，报告为 `reports/gnss_validation/20260622-181804/gnss_probe.md`；`COM6/COM7` AT 可达，`gnss_power_state=1`，室内 no-fix，已写入 `location_report fix=false`。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --wait-seconds 90 --process-safety --safety-process-limit 30`：通过，收到 3 条开发板 MQTT 消息，包括 `mqtt_status` 和真实固件 `sensor_sample/device_health seq=21548`；Safety 处理写入 `risk_type=none` 的 evaluation。注意开发板连接 LAN broker `192.168.31.250:1883`，不是 loopback broker。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t038-hardware-usability-smoke --output-dir pc_simulator\runtime\recordings\t038-hardware-usability-smoke --limit 12 --json`：通过，生成 12 条 source events、5 条 sensor frames、7 条 events。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json`：通过，quality gate PASS，`quality_score=0.91`、`errors=0`、`warnings=3`。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json`：通过，replay PASS，12 条 timeline records、6 条 replayed inputs、1 条 `manual_sos`、5 条 `none`、1 条模拟 `base_command`。
- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：通过，5 个测试全部成功；覆盖 HCTX-001 / T038 范围、关键传感器状态、Mock/未知边界、证据路径、M1 阻塞项和 HARCH-001 审计重点。
- 硬件包 manifest 校验：通过，`PACKAGE_MANIFEST.json` 中 10 个文件的 bytes / SHA-256 全部匹配；采购清单 Excel 可作为 `.xlsx` 打开，包含“概览、采购总表、已有物料、平台对比、到货验收”5 个 sheet。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，108 个测试全部成功。
- `python -m unittest quality_tests.test_session_replay -v`：通过，4 个测试全部成功；覆盖成功回放、质量门失败拒绝回放、replay report 写入和 CLI。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，返回 `PASS replayed_inputs=37 safety_events=9 skipped=23`，生成 `session_replay_report.json` / `.md`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，107 个测试全部成功。
- `python -m unittest quality_tests.test_session_recorder quality_tests.test_session_inspector -v`：通过，9 个测试全部成功；覆盖 file manifest 生成、hash manifest CLI 输出、manifest 篡改、JSONL 篡改和 hash mismatch。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t035-integrity-smoke --output-dir pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，生成带 `file_manifest.json` 的 smoke recording。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，quality gate PASS；`quality_score=0.85`、`errors=0`、`warnings=5`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，103 个测试全部成功。
- `python -m unittest autodev.tests.test_supervisor quality_tests.test_local_session_summary -v`：通过，19 个测试全部成功；覆盖 AutoDev 读取 quality gate 摘要和本地监督会话脚本契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-211742/recording/session_quality_report.md`，quality gate 为 PASS，`quality_score=0.85`、`errors=0`、`warnings=5`。
- `python scripts\autodev.py watch --once --no-clear --events 4`：通过，`LOCAL DEVICE / SAFETY SESSION` 显示 `Quality   : PASS score=0.85 errors=0 warnings=5 frames=11 events=27` 和 quality report 路径。
- `python scripts\autodev.py status`：通过，显示相同 Quality/Report 摘要。
- `python -m unittest quality_tests.test_session_inspector quality_tests.test_session_recorder -v`：通过，8 个测试全部成功；覆盖 quality gate pass/fail、record count mismatch、未验证 source 标记 real、重复 source key、报告写入和 CLI。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t033-quality-smoke --output-dir pc_simulator\runtime\recordings\t033-quality-smoke`：通过，生成 smoke recording，包含 19 条 sensor frames、41 条关键 events、0 条 annotations。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t033-quality-smoke`：通过，质量门 PASS；`quality_score=0.85`、`errors=0`、`warnings=5`，warning 暴露 firmware version unknown、annotations empty 和历史 Safety 派生事件 seq 回退。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，102 个测试全部成功。
- `python -m unittest quality_tests.test_session_recorder quality_tests.test_local_session_summary -v`：通过，6 个测试全部成功；覆盖 recorder manifest、sensor frame/event 输出、CLI 写入和本地监督会话脚本契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-201911/recording/session_recording.md`，最近 40 条 event log 派生出 11 条 sensor frames、27 条关键事件、0 条 annotations，未启动新的后台进程。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，97 个测试全部成功。
- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：通过，4 个硬件传感器矩阵测试全部成功；覆盖 M1 范围、关键传感器状态、Mock/未知边界和证据路径。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，94 个测试全部成功。
- `python -m unittest autodev.tests.test_supervisor -v`：通过，15 个 AutoDev supervisor 测试全部成功；覆盖本地 session summary 读取、event-log fallback 和既有监控行为。
- `python scripts\autodev.py watch --once --no-clear --events 4`：通过，同屏显示 AutoDev 最近任务状态和 `LOCAL DEVICE / SAFETY SESSION`，其中最新 Safety 风险为 `manual_sos`，动作为 `urgent_escalation`。
- `powershell -ExecutionPolicy Bypass -File scripts\watch_autodev.ps1 -Once -NoClear -RecentEvents 4`：通过，PowerShell wrapper 可显示统一监控。
- 新增模型上下文文档静态检查：通过，M1 下一步明确为硬件与传感器矩阵，不训练 MotionNet/AudioGate/VisionGate。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，90 个测试全部成功。
- `python -m unittest quality_tests.test_local_session_summary -v`：通过，3 个本地监督会话测试全部成功；覆盖事件摘要统计、JSON/Markdown 文件输出和 PowerShell 启动脚本关键契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-174427/`，写入 `session.log`、`session_summary.json` 和 `session_summary.md`，未启动新的后台进程。
- `python scripts\local_session_summary.py --event-log pc_simulator\runtime\events.jsonl --limit 8 --markdown`：通过，摘要显示最新 Safety 风险为 `manual_sos`，建议动作为 `urgent_escalation`，最近 8 条事件中包含 3 条 `safety_evaluation`、1 条 `safety_event` 和 1 条模拟 command。
- `python -m unittest quality_tests.test_mqtt_worker -v`：通过，12 个 MQTT worker 测试全部成功；覆盖 `--process-safety` 参数、after-store hook、坏行跳过、Safety 失败隔离和进度输出。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v`：通过，26 个 PC Simulator / Safety Companion adapter 测试全部成功；覆盖 `POST /api/safety/replay`、`POST /api/safety/process-events`、真实 `sensor_sample` 映射、事件日志幂等处理、派生 safety 记录过滤、隐私证据过滤和无副作用命令。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90 --process-safety --safety-process-limit 20`：通过，收到真实固件 `sensor_sample seq=9064`，并立即写入 1 条 `safety_evaluation`；`risk_type=none`，未生成 `safety_event` 或 command。
- Dashboard API live worker 幂等验证：通过，`POST /api/safety/process-events` 对已处理 live `sensor_sample` 返回 `processed=0`、`safety_evaluations=0`、`safety_events=0`、`base_commands=0`。
- `python scripts\sim7670_gnss_probe.py --no-power-on --warmup-seconds 0 --poll-count 1 --poll-interval-seconds 0`：通过，报告见 `reports/gnss_validation/20260621-161721/gnss_probe.md`；`COM6/COM7` AT 可达，`gnss_power_state=1`，当前 no-fix，事件已写入 `pc_simulator/runtime/events.jsonl`。
- GNSS no-fix + 模拟 SOS Safety process：通过，`POST /api/safety/process-events` 处理 2 个源事件，写入 2 条 `safety_evaluation`、1 条 `safety_event`、1 条无副作用模拟 command。
- 真实/半真实日志 Safety process：通过，最近 20 条事件中处理 12 条可评估事件，写入 12 条 `safety_evaluation`、3 条 `safety_event`、3 条模拟 command。
- `python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_mqtt_heartbeat_firmware -v`：通过，8 个固件侧静态测试全部成功。
- `python scripts\verify_safety_companion_m0.py`：通过，模型包自检、12 个合成场景、契约测试、包内测试和 C threshold header 比对全部成功。
- `python -m unittest quality_tests.model_contract.test_contract_schemas -v`：通过，5 个 Safety Companion M0 契约测试全部成功。
- `python -m unittest quality_tests.test_repository_contract -v`：通过，3 个仓库结构契约测试全部成功。
- `python -m unittest quality_tests.test_sim7670_gnss_probe -v`：通过，6 个 GNSS probe 测试全部成功。
- PC Simulator safety endpoint：通过，`POST /api/safety/evaluate` 可接收标准 `model_input` 并返回 M0 `model_output`；测试覆盖 `manual_sos -> urgent_escalation`。
- `python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2`：通过，首次报告见 `reports/gnss_validation/20260621-100651/gnss_probe.md`；`COM6/COM7` AT 可达，型号 `SIM7670G-MNGV`。
- `python scripts\sim7670_gnss_probe.py --no-power-on --warmup-seconds 0 --poll-count 1 --poll-interval-seconds 0`：通过，最终报告见 `reports/gnss_validation/20260621-101143/gnss_probe.md`；`gnss_power_state=1`，当前返回 no-fix，事件已写入 `pc_simulator/runtime/events.jsonl`。
- Dashboard API：通过，`http://127.0.0.1:8787/api/state` 最新事件为 `event_type=location_report`、`source=sim7670g_gnss`、`fix=false`、`gnss_power_state=1`、`device.gnss_state=no_fix`。
- `python -m unittest quality_tests.test_board_probe -v`：通过，8 个 board probe 测试全部成功。
- `python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports`：通过，报告见 `reports/board_validation/20260621-091239/probe.md`；`COM4` CH343、SIM7670G 串口、Remote NDIS 和 AT 身份质量门均通过，ESP32 日志与 SD 状态因本次跳过日志读取仍为 WARN。
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v`：通过，3 个固件静态测试全部成功。
- `idf.py -p COM4 flash`：通过，识别芯片 `ESP32-S3`，写入 `egolink_mqtt_heartbeat.bin` 并 hard reset。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90`：通过，收到真实固件 `sensor_sample`。
- 本机 Dashboard 当前运行在 `http://127.0.0.1:8787`，进程 PID `44568`。

## 已知限制

- 当前 GNSS 在室内未获得卫星 fix，`location_report` 已可上报 no-fix 状态；后续需要户外或靠窗长时间冷启动验证真实经纬度。
- Safety Companion M0 官方规则包当前不把 GNSS no-fix 作为模型风险；PC Simulator adapter 只保留 `fix_valid=false` 输入，不再沿用旧 mock 的 `device_risk/upload_summary` 输出。
- 当前 shell 未加载 ESP-IDF，`idf.py --version` 不可用；T025 只完成固件接口和主机侧静态测试，尚未进行 ESP-IDF build、flash 或真实串口 CLI 验证。
- T026 是纯模拟 replay 闭环，只验证协议、记录、展示和无副作用命令，不验证真实事故/跌倒/呼救识别准确率。
- T030 的统一监控仍是只读观察入口，不负责启动、停止、重启或修复设备侧进程；长期运行守护、日志轮转和自动恢复仍未实现。
- M1 数据基础已开始于硬件传感器矩阵；当前没有真实 MotionNet、AudioGate、VisionGate，也没有可用于训练的正式 session 数据集。
- T032 recorder 是 PC event-log 派生骨架，不是固件内 `safety_recorder`；它尚未实现掉电恢复、窗口完整率或采样率统计。
- T033/T034/T035/T036 已提供 PC 侧质量门、文件完整性和 replay/model-input rebuild；但固件 recorder、用户标注和可训练正式 session 数据集仍未实现。
- 当前 P0 4G 主控板 IMU、AMOLED QMI8658 正式验收、麦克风、真实物理 SOS GPIO、SD 挂载、真实电量/充电和 ESP32 侧 SIM7670G 控制链路仍未验证，不能作为 M1 recorder 的正式真实传感源声明。
- 当前 T021 是 PC 侧通过 USB AT 口探测 SIM7670G GNSS，尚未把 ESP32 固件切换为直接控制 SIM7670G GNSS。
- SD 卡挂载曾失败，需要单独确认格式、接线、引脚、供电和固件挂载参数。
- 用户已确认当前 Wi-Fi 凭据可以在本机项目中明文保存，固件 `sdkconfig` 可保留 SSID/password。
- 当前 shell 不是管理员权限，无法修改 `C:\Program Files\mosquitto\mosquitto.conf`；因此系统服务仍只监听本机回环地址，局域网访问由用户态 Mosquitto 进程提供。
- 当前开发板已从 MQTT heartbeat 固件切换为 camera smoke 固件（指 Waveshare ESP32-S3-SIM7670G-4G）；如需恢复 MQTT 心跳、M1 live worker 或 IMU mock payload，需要重新烧录 `firmware/mqtt_heartbeat`。
- 当前 ESP32-S3-Touch-AMOLED-2.06 开发板已从出厂/示例固件切换过 `firmware/amoled_bridge`，随后 TIMU-008 切换为 `firmware/mqtt_heartbeat` QMI8658 profile；HDBRIDGE-002/TIMU-006 已验证 USB CDC JSONL、QMI8658 WHOAMI、20Hz 120 样本窗口、三姿态静态证据、一次 motion sanity 和 600 样本连续长窗口 timing/jitter/drop；TIMU-008/TIMU-009C-A 已验证 MQTT QMI backend sample payload，TIMU-009C-B1 已验证纸盒临时夹具静置窗口，TIMU-009C-B2 已验证标记后临时夹具复现性窗口；但尚未验证最终产品安装方向、最终校准、FIFO/中断、麦克风音频、屏幕触摸下行命令、TF/SD、功耗或两板直连 UART。
- Windows 侧 SIM7670G RNDIS 网卡可获得 `192.168.0.100/24` 和默认网关 `192.168.0.1`，但从电脑指定该源地址 ping/curl 外网仍超时；当前 4G 可用性以模块 AT TCP/IP 栈验证为准。
