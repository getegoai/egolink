---
id: FIELD-008
title: D1 field-observation local index
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
  - docs/tasks/done/FIELD-007_D1_FIELD_OBSERVATION_VISIBILITY.md

allowed_paths:
  - scripts/summarize_d1_field_observations.py
  - quality_tests/test_d1_field_observation_index.py
  - docs/development/FIELD_TEST.md
  - docs/current/STATUS.md
  - docs/tasks/done/FIELD-008_D1_FIELD_OBSERVATION_INDEX.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, sending Message Hub commands, or deploying to the VPS
  - reading or exposing `d1_field_samples.jsonl` contents, raw payloads, private coordinates, candidate DBs, or model artifacts
  - changing firmware, protocol, public APIs, model behavior, training behavior, or field acceptance gates
  - making location accuracy, battery life, GNSS, LTE stability, model, or product-readiness claims
---

# Goal

Serve D1: make active and completed D1 long-run observer outputs easy to audit
locally during unattended field testing.

# Acceptance Criteria

- [x] A local command scans `reports/d1_field_observation/**/` status/report
      summaries and writes a bounded JSON/Markdown index.
- [x] Running live status entries are surfaced with sample counts, latest
      sequence, freshness, and latest location-upload timestamp.
- [x] Completed final reports are surfaced with result, sample counts, deltas,
      warnings/errors, and report/status references.
- [x] The index does not read or expose `d1_field_samples.jsonl` contents or
      local absolute private paths.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_d1_field_observation_index -v
python -m py_compile scripts\summarize_d1_field_observations.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/summarize_d1_field_observations.py`,
  `quality_tests/test_d1_field_observation_index.py`,
  `docs/development/FIELD_TEST.md`, `docs/current/STATUS.md`, and this packet.
- Focused validation covers a mixed completed/running local observation tree
  and verifies the bounded index excludes `d1_field_samples.jsonl` and private
  local paths.
- Remaining risks: this is a local indexing tool only. The VPS Dashboard will
  see these summaries only after a later explicit curated sync/deploy step.
