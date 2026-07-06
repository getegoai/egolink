---
id: FIELD-007
title: D1 field-observation visibility
status: done
priority: medium
requires_hardware: false
serves_demo: D1
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/development/FIELD_TEST.md
  - docs/tasks/done/FIELD-006_D1_OBSERVER_LIVE_STATUS.md
  - docs/tasks/done/DATA-019_POSTRUN_FIELD_OBSERVATION_BINDING.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-007_D1_FIELD_OBSERVATION_VISIBILITY.md

out_of_scope:
  - deploying to the VPS unless explicitly requested
  - copying `d1_field_samples.jsonl`, raw payloads, candidate DBs, private coordinates, or runtime JSONL logs
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - changing firmware, Message Hub ingest, public contracts, OTA, or on-device inference
  - making location accuracy, battery life, GNSS, LTE stability, model, or product-readiness claims
---

# Goal

Serve D1: show bounded D1 field-observation summaries in the existing Web
Dashboard Field Test Results surface.

# Acceptance Criteria

- [x] `load_latest_field_results()` includes the latest
      `d1_field_observation_report.json` when present.
- [x] If only `d1_field_observation_status.json` is present, the Field Test
      Results summary can show the live running/completed state.
- [x] Dashboard/API summaries expose sample counts, latest seq/freshness,
      delta metrics, warnings/errors, and report/status refs without exposing
      sample JSONL contents or local absolute paths.
- [x] `-IncludeFieldReportSummaries` can copy only
      `d1_field_observation_report.json/.md` and
      `d1_field_observation_status.json`; it still does not copy
      `d1_field_samples.jsonl`.
- [x] Focused Web/API tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py
$errors=$null; [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw scripts\deploy_message_hub_vps.ps1), [ref]$errors) | Out-Null; if ($errors -and $errors.Count) { exit 1 }
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`,
  `quality_tests/test_message_hub_dashboard.py`, `docs/development/FIELD_TEST.md`,
  `docs/current/STATUS.md`, and this packet.
- Focused validation passed: the field-results loader test now includes a
  `d1_field_observation` card and verifies `d1_field_samples.jsonl` plus local
  absolute paths are not exposed.
- Remaining risks: FIELD-007 was not deployed to the VPS in this run. It is
  visibility only; final field acceptance still depends on reviewed outdoor
  GNSS/LTE/power evidence.
