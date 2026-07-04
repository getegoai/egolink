---
id: UI-002
title: Field test results visibility and next-run plan
status: done
priority: high
requires_hardware: false
serves_demo: D1
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_dashboard.py
  - docs/current/
  - docs/tasks/done/UI-002_FIELD_TEST_RESULTS_VISIBILITY_AND_PLAN.md

out_of_scope:
  - changing Message Hub device ingest protocol
  - changing 4G or AMOLED firmware
  - copying raw JSONL logs or secrets into deploy packages
  - claiming GNSS accuracy, battery life, or product readiness
---

# Goal

Make recent D1 field-test result reports visible on the Web Dashboard and record
the next/out-year task plan for D1 -> D2/D3.

# Acceptance Criteria

- [x] Dashboard has a `Field Test Results` panel sourced from bounded report
      summary files.
- [x] `/api/state` and a focused API route expose latest field-test result
      summaries without raw logs.
- [x] VPS deploy can optionally include curated field-report summaries, not raw
      JSONL logs or secrets.
- [x] Current UI-001 evidence is visible after VPS deployment.
- [x] Planning docs state the next outdoor run and later map/track/report tasks.
- [x] Focused tests, `context_lint`, and full verify pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_message_hub_dashboard.py`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/current/ACTIVE_BUILD.md`,
  `docs/current/STATUS.md`,
  `docs/tasks/done/UI-002_FIELD_TEST_RESULTS_VISIBILITY_AND_PLAN.md`, and
  `docs/tasks/active/FIELD-004_D1_OUTDOOR_MULTI_HOUR_RUN.md`.
- Validation: `python -m unittest quality_tests.test_message_hub_dashboard -v`
  passed (8 tests); `python scripts/context_lint.py` passed; `python -m
  py_compile server\message_hub.py` passed; `powershell -ExecutionPolicy
  Bypass -File scripts\verify.ps1` passed (390 tests).
- Deployment: `scripts/deploy_message_hub_vps.ps1 -Public
  -IncludeFieldReportSummaries` deployed to `203.0.113.10:8790`, restarted
  `egolink-message-hub.service`, and did not modify GitLab.
- Evidence: `/health` returned `ok=true`; unauthenticated `/api/state` returned
  `401`; Dashboard HTML contained `Field Test Results`, `fieldResults`,
  `fieldResultsPanel`, and `D1 Link Through`; authenticated
  `/api/v1/field-results/latest` returned `available=true`, `status=pass`, and
  `report_count=3`.
- Remaining risks: report summaries are not a live map provider, do not expose
  raw JSONL logs, and do not claim location accuracy, battery life, calling/SMS,
  or product readiness. FIELD-004 remains active for the real outdoor 2-3 hour
  D1 run.
