---
id: DEMO-008
title: Product Demo Closed Loop Report Baseline
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
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/done/DEMO-004_FULL_DEMO_ORCHESTRATOR.md
  - docs/tasks/done/REL-011_KR007_RECONNECT_STORE_FORWARD_EVIDENCE_RELEASE.md
  - scripts/export_location_fusion_dataset.py
  - scripts/evaluate_eale_p0_dataset.py

allowed_paths:
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DEMO-008_PRODUCT_DEMO_REPORT_BASELINE.md
  - scripts/build_product_demo_report.py
  - quality_tests/test_product_demo_report.py

out_of_scope:
  - firmware changes or flashing
  - hardware runtime validation
  - VPS deployment or GitLab changes
  - changing live device wire protocol or raw-frame format
  - creating or promoting a KR-008 release manifest
  - claiming product readiness, emergency dispatch, fall-detection accuracy,
    learned-model readiness, GNSS acceptance, battery/power acceptance,
    enclosure acceptance, long LTE stability, real reconnect recovery, or
    durable store-forward
---

# DEMO-008 Product Demo Closed Loop Report Baseline

## Goal

Create the first no-hardware KR-008/DEMO product-demo artifact by composing
already captured evidence into a single reviewable report:

```text
user trigger or safety event
-> device requests location/status
-> LTE raw-frame uplink
-> DATA-001 multi-source evidence window
-> EALE-P0 location_belief
-> user confirmation or safety-rule decision
-> report export
-> Web console replay/review pending
```

## Result

- Added `scripts/build_product_demo_report.py`.
- Added `quality_tests/test_product_demo_report.py`.
- The report generator consumes a Message Hub test-run export plus an optional
  full safety-demo summary.
- It writes:
  - `product_demo_report.json`
  - `product_demo_report.md`
  - supporting DATA-001 `samples.jsonl`
  - supporting DATA-001 `manifest.json`
  - supporting EALE-P0 JSON/Markdown evaluation reports.
- It does not contact hardware, serial ports, the VPS, or GitLab.

## Local Demonstration

The first local composite report was generated from:

- LTE evidence:
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/test_run_export.json`
- Safety demo evidence:
  `pc_simulator/runtime/demo_full_v0_5/demo-full-v05-20260626-live-gnss.summary.json`

Output:

- `reports/product_demo/kr008-demo008-composite-20260702-001/product_demo_report.json`
- `reports/product_demo/kr008-demo008-composite-20260702-001/product_demo_report.md`

The result is `WARN`, not `PASS`, because this is composite existing evidence
instead of a single same-run product scenario, and because the Web console
replay/review path is still pending.

## Acceptance

- [x] Compose existing safety-loop evidence with the KR-007/LTE raw evidence
      line without new hardware work.
- [x] Preserve raw-frame lineage through DATA-001 samples and EALE-P0
      evaluation.
- [x] Expose the flow gate status for every product-demo step.
- [x] Mark Web console replay/review as pending instead of pretending KR-008
      is release-ready.
- [x] Preserve no-fix and failure-window evidence as useful data.
- [x] Keep all product-readiness and accuracy claims out of the report.

## Validation

```powershell
python -m unittest quality_tests.test_product_demo_report -v
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## Boundary

DEMO-008 is a report baseline and composition gate. It proves that the existing
Walking Skeleton can be reviewed as a product-demo-shaped chain, but it does
not complete KR-008. The next gate is to expose the same report through the
Message Hub Dashboard so the demo can be reviewed from the Web console.
