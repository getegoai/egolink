---
id: WEB-003
title: Founder Dashboard clarity and field-first hierarchy
status: done
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-11
last_updated: 2026-08-11

context:
  - docs/AGENTS.md
  - docs/product/NORTH_STAR.md
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/progress_board_config.json
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/done/WEB-001_MESSAGE_HUB_DASHBOARD_BASELINE.md
  - docs/tasks/done/OBS-005_PROGRESS_BOARD_DASHBOARD.md
  - docs/tasks/done/UI-002_FIELD_TEST_RESULTS_VISIBILITY_AND_PLAN.md
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - scripts/build_progress_board.py
  - quality_tests/AGENTS.md
  - quality_tests/test_message_hub_dashboard.py

allowed_paths:
  - docs/tasks/done/WEB-003_FOUNDER_DASHBOARD_CLARITY.md
  - docs/current/STATUS.md
  - docs/current/progress_board_config.json
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py

out_of_scope:
  - device firmware, hardware control, command creation, or data collection
  - Message Hub API, protocol, schema, storage, authentication, or retention changes
  - raw private coordinates, tokens, device payloads, or logs in Git
  - GitLab, firewall, port, SSH, token rotation, or database restoration
  - frontend framework migration, map provider integration, or visual feature expansion
---

# Goal

Make the existing VPS Dashboard field-first and founder-readable without
changing its data contracts: show live device/location/command state first,
keep current progress and field evidence easy to reach, and collapse model and
raw diagnostic detail until requested.

# Acceptance Criteria

- [x] The first viewport presents the D1 live view and a compact field-operations
      area before project, model, labeling, or raw diagnostic detail.
- [x] A stable explicit device selector drives D1 and latest-field panels,
      preferring the current run's device and then the newest device.
- [x] Field results and the data flywheel remain prominent; model/labeling and
      raw diagnostics are grouped behind clear collapsed disclosure controls.
- [x] Existing Dashboard element IDs and D1/Product Demo validation markers are
      preserved, and tables remain usable on narrow screens.
- [x] Refresh requests do not overlap; transient failures preserve the last
      successful view and expose an understandable refresh state.
- [x] The sanitized generated progress board is refreshed before deployment.
- [x] Focused tests, full verification, context lint, and diff check pass.
- [x] The committed build is deployed through the existing self-hosted VPS path;
      service health, auth boundary, target HTML markers, and GitLab isolation pass.

# Validation Commands

```powershell
python scripts\build_progress_board.py
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m py_compile server\message_hub.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Deployment Boundary

- Deploy only from a clean committed HEAD after a read-only VPS preflight.
- Before replacement, take a consistent database/reports backup plus a code
  and systemd-unit snapshot. Do not copy secrets into the repository.
- Perform one deployment/restart and one bounded read-only smoke. If the new
  service or health gate fails, restore only the code/unit snapshot and restart;
  do not restore the live database unless a separate database-corruption task
  explicitly authorizes it.

# Completion Evidence

- Local implementation phase: the existing inline Dashboard was reordered into
  D1 live view, Field Operations, Field Evidence, Project Progress, and collapsed
  model/diagnostic disclosures. D1 secondary evidence is also collapsed; on
  narrow screens the decision summary precedes the map.
- The device selector persists an explicit valid choice, otherwise prefers the
  current run device and then the newest device. D1, Latest Field State, and the
  browser-local D2 reference check use that same selection.
- Refresh is guarded against overlap and retains the last successful DOM on
  authentication, HTTP, JSON, or network errors while showing refresh status.
- Validation: Dashboard `42/42` PASS, Message Hub server `39/39` PASS,
  repository verification `615/615` PASS, `py_compile`, `context_lint`, and
  `git diff --check` PASS.
- Sanitized progress artifacts were regenerated at `2026-08-11 08:55 UTC`
  from implementation commit `27e5ec4`; they show the current FIELD-011
  stationary bench result and the next outdoor walking/GNSS work.
- Deployment source was clean committed HEAD `2c64659`; implementation source
  `server/message_hub.py` deployed with SHA-256
  `ec6c1cc01f7b3440b9e19f388395ccb6f612ca97795c99ee088d659b6f299ef6`.
- Before deployment, the VPS stored an SQLite-consistent database copy plus
  reports, code, and systemd-unit snapshots at
  `/var/backups/egolink-message-hub/WEB-003-20260811T085834Z`; all recorded
  hashes verified and the backup database passed `PRAGMA quick_check`.
- One deployment/restart completed at `2026-08-11 16:59 CST`. Bounded live
  smoke passed: `/health=200/ok`, unauthenticated `/api/state=401`, authenticated
  `/api/state=200`, Dashboard `200`, all eight field-first hierarchy markers in
  order, current FIELD-011 stationary focus visible, service `active/running`,
  `NRestarts=0`, `ExecMainStatus=0`, and zero error-priority journal lines in
  the following ten-minute window.
- No rollback was needed. The deployment path was scoped to the Message Hub
  package and systemd unit; GitLab, firewall, ports, token value, database
  contents, firmware, and hardware were not changed.

# Builder Prompt

```text
Read docs/tasks/done/WEB-003_FOUNDER_DASHBOARD_CLARITY.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md,
quality_tests/AGENTS.md, this packet, and its context entries. Reorder and
clarify only the existing built-in Dashboard. Preserve all public API/data
contracts and required DOM markers. Obey allowed_paths/out_of_scope, validate
the committed source, and return changed files, test results, deployment
evidence, and remaining risks. Do not touch firmware, secrets, GitLab, or the
live database contents.
```
