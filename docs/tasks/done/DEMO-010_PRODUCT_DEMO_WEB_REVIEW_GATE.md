---
id: DEMO-010
title: Product Demo Web Review Gate
status: completed
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03
completed: 2026-07-03

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/done/DEMO-008_PRODUCT_DEMO_REPORT_BASELINE.md
  - docs/tasks/done/DEMO-009_PRODUCT_DEMO_DASHBOARD_REVIEW.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DEMO-010_PRODUCT_DEMO_WEB_REVIEW_GATE.md
  - scripts/validate_product_demo_web_review.py
  - quality_tests/test_product_demo_web_review.py

out_of_scope:
  - firmware changes or flashing
  - hardware runtime validation
  - sending device commands
  - changing live device wire protocol or raw-frame format
  - creating or promoting a KR-008 release manifest
  - generating new field evidence
  - deploying or modifying VPS services
  - modifying GitLab or unrelated VPS services
  - claiming product readiness, emergency dispatch, fall-detection accuracy,
    learned-model readiness, GNSS acceptance, battery/power acceptance,
    enclosure acceptance, long LTE stability, real reconnect recovery, or
    durable store-forward
---

# DEMO-010 Product Demo Web Review Gate

## Goal

Turn the DEMO-009 Web visibility baseline into a repeatable no-hardware gate:

```text
Message Hub /health
-> /api/v1/product-demo/latest
-> /api/state product_demo consistency
-> Dashboard Product Demo panel markers
-> explicit KR-008 release boundary
-> product_demo_web_review_report.json / .md
```

## Result

- Added `scripts/validate_product_demo_web_review.py`.
- Added `quality_tests/test_product_demo_web_review.py`.
- The gate checks:
  - Message Hub health;
  - dedicated Product Demo API availability;
  - `/api/state` consistency with the dedicated API;
  - Dashboard HTML markers for the Product Demo panel;
  - release-readiness boundary so a WARN/composite report cannot be mistaken
    for KR-008 readiness.
- A PASS means the latest product-demo report is reviewable through Web/API.
  It does not mean the current report is product-ready.

## VPS Read-Only Gate

The gate was run against the public VPS Message Hub without sending device
commands, modifying GitLab, deploying code, or touching hardware:

- Review ID: `demo010-vps-20260703-001`
- Hub: `http://203.0.113.10:8790`
- Result: `PASS`
- Candidate: `KR-008 / DEMO-008 Product Demo Closed Loop`
- Product report status: `warn`
- Evidence mode: `composite_existing_evidence`
- Test run: `lte011-reconnect-store-forward-test-fix1-20260702-001`
- Web/API gate report:
  `reports/product_demo_web_review/demo010-vps-20260703-001/product_demo_web_review_report.json`
- Markdown report:
  `reports/product_demo_web_review/demo010-vps-20260703-001/product_demo_web_review_report.md`

The current DEMO-008 report remains a WARN composite artifact. Its internal
`web_console_replay_review` field still says `not_run` because that report was
generated before this gate existed. DEMO-010 records the external Web/API
reviewability gate; a later DEMO/KR step should regenerate or produce a same-run
report with that evidence bound into the product-demo report itself.

## Acceptance

- [x] Gate can run against a token-protected Message Hub.
- [x] Gate writes machine-readable JSON and Markdown reports.
- [x] Gate distinguishes Web/API reviewability from KR-008 release readiness.
- [x] Missing Dashboard markers fail with an explicit reason.
- [x] Tests cover pure evaluation and local token-protected HTTP execution.

## Validation

```powershell
python -m unittest quality_tests.test_product_demo_web_review -v
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_product_demo_report -v
python scripts/validate_product_demo_web_review.py --hub-url http://203.0.113.10:8790 --review-id demo010-vps-20260703-001 --output-dir reports/product_demo_web_review/demo010-vps-20260703-001 --json
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

All validation commands passed. Full `scripts\verify.ps1` passed with 332
tests.

## Boundary

DEMO-010 makes the Web review gate repeatable. It does not create same-run
product-demo evidence, does not regenerate the DEMO-008 report, does not create
or promote a KR-008 manifest, and does not make product-readiness claims.
