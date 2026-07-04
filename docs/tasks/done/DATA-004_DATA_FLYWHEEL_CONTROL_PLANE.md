---
id: DATA-004
title: Data flywheel control plane
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/DATA-003_TRAINING_CANDIDATE_STORE_BASELINE.md

allowed_paths:
  - pc_simulator/training_candidate_store.py
  - scripts/summarize_data_flywheel.py
  - scripts/deploy_message_hub_vps.ps1
  - server/message_hub.py
  - quality_tests/test_training_candidate_store.py
  - quality_tests/test_message_hub_dashboard.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-004_DATA_FLYWHEEL_CONTROL_PLANE.md
  - docs/generated/

out_of_scope:
  - training a model
  - marking records training-ready
  - changing firmware, public contracts, or Message Hub ingest
  - copying raw private payloads, candidate DBs, or runtime JSONL logs into committed artifacts
  - integrating a real training server
---

# Goal

Serve D5: make the data flywheel visible and auditable by summarizing the
local training-candidate store and exposing a bounded status panel in the Web
Dashboard.

# Acceptance Criteria

- [x] Candidate-store status can be summarized without exposing raw records.
- [x] A CLI writes JSON/Markdown data-flywheel status reports.
- [x] Message Hub exposes the latest curated data-flywheel status through API
      and Dashboard.
- [x] Deploy script can optionally sync only curated status summaries, not DBs
      or JSONL logs.
- [x] Focused tests and project validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_candidate_store quality_tests.test_message_hub_dashboard -v
python scripts/context_lint.py
python -m py_compile pc_simulator\training_candidate_store.py scripts\summarize_data_flywheel.py server\message_hub.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `pc_simulator/training_candidate_store.py`,
  `scripts/summarize_data_flywheel.py`,
  `server/message_hub.py`, `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_training_candidate_store.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`,
  `docs/roadmap/V1_PRODUCT_PLAN.md`, `docs/current/STATUS.md`, generated
  progress board files, and this task packet.
- Validation: focused candidate-store/dashboard tests passed (16 tests);
  `python scripts/context_lint.py` passed; `python -m py_compile
  pc_simulator\training_candidate_store.py scripts\summarize_data_flywheel.py
  server\message_hub.py` passed; `git diff --check` passed; full
  `scripts\verify.ps1` passed (398 tests).
- Evidence: `scripts/summarize_data_flywheel.py --run-id
  data004-local-status-20260704 --generated-at 2026-07-04T12:30:00+00:00
  --json` wrote a bounded local status report under
  `reports/data_flywheel/data004-local-status-20260704/`, currently showing
  `needs_capture` because the default local candidate-store DB does not yet
  exist.
- Deployment: `scripts/deploy_message_hub_vps.ps1 -Public
  -IncludeFieldReportSummaries -IncludeDataFlywheelSummaries` restarted
  `egolink-message-hub.service` on `203.0.113.10:8790`; smoke checks passed
  for `/health`, unauthenticated `/api/state` = `401`, Dashboard `Data
  Flywheel` markers, authenticated `/api/state`, and
  `/api/v1/data-flywheel/latest` returning `needs_capture /
  candidate_store_missing`.
- Remaining risks: no labeling/review UI exists yet, no dataset manifest export
  exists yet, no training server is integrated, and no model has been trained,
  evaluated, deployed, or power-measured.
