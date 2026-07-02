---
id: DEMO-009
title: Product Demo Dashboard Review Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-07-02
last_updated: 2026-07-02
completed: 2026-07-02

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

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DEMO-009_PRODUCT_DEMO_DASHBOARD_REVIEW.md
  - server/message_hub.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py

out_of_scope:
  - firmware changes or flashing
  - hardware runtime validation
  - changing live device wire protocol or raw-frame format
  - creating or promoting a KR-008 release manifest
  - generating new field evidence
  - modifying GitLab or unrelated VPS services
  - claiming product readiness, emergency dispatch, fall-detection accuracy,
    learned-model readiness, GNSS acceptance, battery/power acceptance,
    enclosure acceptance, long LTE stability, real reconnect recovery, or
    durable store-forward
---

# DEMO-009 Product Demo Dashboard Review Baseline

## Goal

Expose the DEMO-008 product-demo report through the Message Hub Web Dashboard
so the KR-008 product-demo chain has an operator-visible review surface:

```text
DEMO-008 product_demo_report.json
-> Message Hub product_demo summary
-> /api/state and /api/v1/product-demo/latest
-> Dashboard Product Demo panel
```

## Result

- `server/message_hub.py` now summarizes the latest
  `reports/product_demo/**/product_demo_report.json`.
- `/api/state` includes a `product_demo` object.
- `/api/v1/product-demo/latest` returns the same bounded summary.
- The Dashboard renders a Product Demo panel showing:
  - KR-008 / DEMO-008 candidate;
  - result and release-readiness state;
  - composite/same-run evidence mode;
  - test run and safety session;
  - location belief and GNSS state;
  - flow-gate counts and Web Review gate;
  - raw/derived evidence counts;
  - dataset training readiness;
  - report path and warnings.
- Missing reports return explicit `not_available` state rather than a server
  error.

## Acceptance

- [x] Web/API can show the DEMO-008 report state without contacting hardware.
- [x] Missing local report files remain explainable.
- [x] Dashboard text distinguishes report review from KR-008 release readiness.
- [x] API response is bounded to summary fields and does not expose raw private
      payloads.
- [x] Tests cover Dashboard HTML, report loading, `/api/state`, and
      `/api/v1/product-demo/latest`.

## Validation

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server -v
python -m unittest quality_tests.test_product_demo_report -v
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## Boundary

DEMO-009 makes the product-demo report visible through Web/API. It does not
turn the current composite report into a same-run product demo, does not create
or promote a KR-008 manifest, and does not make product-readiness claims.
