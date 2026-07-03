---
id: DEMO-011
title: Product Demo Report Web Review Binding
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
  - docs/tasks/done/DEMO-010_PRODUCT_DEMO_WEB_REVIEW_GATE.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DEMO-011_PRODUCT_DEMO_REPORT_WEB_REVIEW_BINDING.md
  - scripts/build_product_demo_report.py
  - quality_tests/test_product_demo_report.py

out_of_scope:
  - firmware changes or flashing
  - hardware runtime validation
  - sending device commands
  - changing live device wire protocol or raw-frame format
  - changing Message Hub API contracts
  - creating or promoting a KR-008 release manifest
  - generating new field evidence
  - deploying Message Hub code
  - modifying GitLab or unrelated VPS services
  - claiming product readiness, emergency dispatch, fall-detection accuracy,
    learned-model readiness, GNSS acceptance, battery/power acceptance,
    enclosure acceptance, long LTE stability, real reconnect recovery, or
    durable store-forward
---

# DEMO-011 Product Demo Report Web Review Binding

## Goal

Bind the DEMO-010 Web/API review gate evidence back into the product-demo
report generator, so a regenerated product-demo report can show:

```text
DEMO-010 product_demo_web_review_report.json
-> build_product_demo_report.py --web-review-report ...
-> product_demo_report.json flow.web_console_replay_review = pass
-> Web Dashboard Product Demo panel shows Web Review = pass
```

## Result

- `scripts/build_product_demo_report.py` now accepts `--web-review-report`.
- When a valid DEMO-010 report is supplied:
  - `flow.web_console_replay_review.status` becomes `pass`;
  - flow status counts become `pass=8`;
  - Web review evidence is recorded under `source.web_review`,
    `evidence_summary.web_review`, and the Web Review flow gate;
  - `web_console_product_demo_review_pending` is removed from release blockers.
- The report still returns `WARN` and `ready_for_kr008_release=false` when
  release blockers remain, including:
  - composite evidence is not a same-run product demo;
  - DATA-001/model-training readiness is false;
  - location belief remains `Unknown`, not `Fine`;
  - no KR-008 manifest has been created or promoted.

## Generated Report

The DEMO-011 report was generated from existing evidence only:

- Test-run export:
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/test_run_export.json`
- Safety summary:
  `pc_simulator/runtime/demo_full_v0_5/demo-full-v05-20260626-live-gnss.summary.json`
- Web review gate:
  `reports/product_demo_web_review/demo010-vps-20260703-001/product_demo_web_review_report.json`
- Output:
  `reports/product_demo/kr008-demo011-web-reviewed-20260703-001/product_demo_report.json`

Result summary:

- Product report status: `warn`
- Flow gates: `pass=8`
- Web Review: `pass`
- KR-008 release ready: `false`
- Release blockers:
  `same_run_product_demo_evidence_missing`,
  `dataset_not_ready_for_model_training`,
  `location_belief_not_fine:Unknown`,
  `kr008_manifest_not_created_or_promoted`

## VPS Report Copy

The generated report directory was copied to the VPS Message Hub report store:

```text
/opt/egolink-message-hub/reports/product_demo/kr008-demo011-web-reviewed-20260703-001/
```

No Message Hub code was deployed, no firmware was flashed, no device command
was sent, and GitLab was not modified. A read-only follow-up Web review gate
passed against `http://203.0.113.10:8790`:

- Review ID: `demo011-vps-20260703-001`
- Report:
  `reports/product_demo_web_review/demo011-vps-20260703-001/product_demo_web_review_report.json`
- Web/API result: `PASS`
- Dashboard-visible Product Demo report path:
  `reports/product_demo/kr008-demo011-web-reviewed-20260703-001/product_demo_report.json`
- Dashboard-visible Web Review status: `pass`

## Acceptance

- [x] Product report generator keeps old pending behavior without a Web review
      report.
- [x] Product report generator binds a valid DEMO-010 report as Web Review
      `pass`.
- [x] Bound report does not claim KR-008 readiness.
- [x] CLI can write a bound JSON/Markdown product-demo report.
- [x] VPS Dashboard can display the bound report as the latest Product Demo
      report.

## Validation

```powershell
python -m unittest quality_tests.test_product_demo_report quality_tests.test_product_demo_web_review -v
python scripts/build_product_demo_report.py --test-run-export reports\field_validation\lte011-reconnect-store-forward-test-fix1-20260702-001\test_run_export.json --safety-demo-summary pc_simulator\runtime\demo_full_v0_5\demo-full-v05-20260626-live-gnss.summary.json --web-review-report reports\product_demo_web_review\demo010-vps-20260703-001\product_demo_web_review_report.json --output-dir reports\product_demo\kr008-demo011-web-reviewed-20260703-001 --json
python scripts/validate_product_demo_web_review.py --hub-url http://203.0.113.10:8790 --review-id demo011-vps-20260703-001 --output-dir reports/product_demo_web_review/demo011-vps-20260703-001 --json
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

All checks passed. The full verify run passed 334 tests.

## Boundary

DEMO-011 binds Web review evidence into the report chain. It does not create a
same-run product-demo field scenario, does not produce a GNSS/product
acceptance claim, does not create or promote KR-008, and does not relax the
USB-Free, Message-First, Demo-Driven release discipline.
