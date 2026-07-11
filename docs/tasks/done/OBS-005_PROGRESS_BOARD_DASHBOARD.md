---
id: OBS-005
title: Founder progress board on VPS Dashboard
status: done
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-07-11
last_updated: 2026-07-11
completed: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/tasks/done/ENG-008_PROJECT_PROGRESS_BOARD.md
  - docs/generated/progress_board.json
  - docs/development/VPS_MESSAGE_HUB.md

allowed_paths:
  - server/
  - scripts/deploy_message_hub_vps.ps1
  - quality_tests/
  - docs/current/
  - docs/development/
  - docs/tasks/
  - docs/generated/

out_of_scope:
  - task mutation or remote project control
  - private local paths or secrets in API responses
  - firmware, hardware, model, or location behavior changes
---

This task serves D2. The current lowest unfinished Demo is D2; this is its
North-Star-required founder visibility and coordination surface.

# Goal

Expose the generated progress board as a sanitized, read-only authenticated
API and a compact responsive Dashboard section.

# Acceptance

- Dashboard shows current focus, milestone progress, and founder action items.
- API excludes local task paths and fields outside the explicit allowlist.
- Missing or invalid board files degrade to an explainable unavailable state.
- VPS deployment always carries the generated JSON board.
- Focused tests, context lint, full verification, and live VPS smoke pass.

# Result

- Added sanitized `progress_board` data to `/api/state` and authenticated
  `/api/v1/progress/latest`.
- Dashboard now shows current focus, milestone completion, source revision,
  and founder action items in a responsive read-only section.
- Local task paths, packet contents, and unknown source fields are excluded.
- Deployment always carries `docs/generated/progress_board.json`.

# Validation

- Focused Message Hub/Dashboard tests: pass, 76 tests.
- `python scripts/context_lint.py`: pass.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: pass, 564
  tests.
- Live VPS smoke: pass; service health is true, progress status is available,
  five milestones and five founder action items are visible, and the sanitized
  payload contains no local drive path. HTML/DOM markers and mobile layout
  passed; screenshot review was unavailable because no in-app browser instance
  was present.
