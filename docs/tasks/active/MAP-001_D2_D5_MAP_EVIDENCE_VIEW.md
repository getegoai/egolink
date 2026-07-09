---
id: MAP-001
title: D2/D5 map evidence view
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-07-09
last_updated: 2026-07-09

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

# Completion Evidence

- Changed files:
- Test result:
- Web result:
- Remaining risks:
