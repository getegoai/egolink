---
id: MAP-001
title: D2/D5 map evidence view
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-07-09
last_updated: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/development/LOCATION_ENGINE.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/tasks/active/D5-001_LOCATION_DATA_FLYWHEEL_MAINLINE.md

allowed_paths:
  - server/
  - scripts/
  - docs/current/
  - docs/tasks/
  - quality_tests/

out_of_scope:
  - committing map API keys or provider secrets
  - publishing private raw coordinates in docs/generated or public reports
  - claiming location accuracy from visual map appearance
  - blocking D1 transition on third-party map provider availability
---

This task serves D2-D5. It makes location evidence reviewable on a map-like
surface while D2 builds accuracy metrics and D5 builds the data flywheel.

# Goal

Improve the Dashboard from a placeholder coordinate grid into a practical
evidence review surface for current position, trajectory, reference points,
and D2/D5 run summaries.

# Expected Result

The Web UI supports two modes:

- no-key/local mode: current coordinate, recent trajectory, reference markers,
  and run status without third-party tiles;
- provider mode: optional map tiles only after a provider/key/privacy decision.

# Acceptance Criteria

- [ ] Dashboard clearly distinguishes no-key coordinate/trajectory mode from
      provider-backed map mode.
- [ ] D2 reference points and observed points can be reviewed together without
      exposing private raw coordinates in static docs.
- [ ] Field Test Results link D2 baseline, D1 regression, power, and data
      flywheel summaries in one review surface.
- [ ] Missing provider/API key degrades gracefully and is never a D1 blocker.
- [ ] Unit tests protect privacy redaction and no-accuracy-claim boundaries.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

Not required. This is Web/API/report visibility work over existing evidence.

# Decisions

- Until a map provider is selected, the map view remains a no-key evidence
  surface with coordinates, relative trajectory, and reference markers.
- A map is a review aid, not an accuracy claim.

# Progress

- 2026-07-09 no-key evidence map baseline:
  - Dashboard map surface now labels itself as `local_no_key`, shows provider
    status, track/current/reference-point legend, privacy policy, and no
    accuracy claim.
  - `/api/state` `d1_link.map_surface` now exposes provider, layer, privacy,
    reference-point, and accuracy-claim metadata without changing device
    protocol fields.
  - Field Test Results now has evidence lanes for D2 Baseline, D1 Regression,
    Power, and D5 Flywheel. D2 location accuracy reports under
    `reports/location_accuracy/` are summarized without copying raw private
    coordinates.
- 2026-07-11 local-only mobile reference capture:
  - Added `/d2-reference-capture` and a Dashboard header link. The responsive
    page records run metadata, three reference environments, cold/warm attempt
    windows, strict progress, and exports `field_manifest.json`.
  - Exact reference coordinates stay in browser `localStorage`; there is no
    server write API. A single phone browser fix is explicitly partial and is
    rejected by the strict FIELD-003 analyzer as an unsupported method.

# Completion Evidence

- Changed files: `server/message_hub.py`, `scripts/validate_d1_web_api.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `quality_tests/test_d1_web_api_validation.py`
- Test result: focused Dashboard/Web tests PASS; `python scripts/context_lint.py`
  PASS; `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` PASS
  with 530 tests
- Web result: local smoke on `127.0.0.1:8879` confirmed Dashboard HTML contains
  no-key map markers and evidence lanes, and `/api/state` returns Field Results
  structure. Provider-backed map remains future work after provider/key/privacy
  decision.
- Remaining risks: real D2 reference-point overlay still depends on D2 baseline
  report production and future provider selection
