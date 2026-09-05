---
id: COMPLIANCE-010
title: China P0 pre-compliance and classification
status: active
priority: critical
lane: D
execution_state: queued
depends_on:
  - HW-020
supersedes: PROD-002
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/compliance/README.md
  - docs/tasks/active/HW-020_PRODUCT_ARCHITECTURE_FREEZE.md
  - docs/tasks/active/PROD-002_CHINA_PRECOMPLIANCE_AND_A0_INPUTS.md

allowed_paths:
  - docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md
  - docs/compliance/
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md

out_of_scope:
  - making legal conclusions without qualified written opinion
  - purchasing, certifying or freezing PCB/antenna/enclosure from assumptions
---

# Goal

Obtain a named, written China product-classification/pre-compliance opinion for
the exact P0 concept and translate it into HW-020/A0 evidence requirements.

This is the sole successor to `PROD-002`; the older packet is retained only
for lineage and must not be dispatched in parallel.

# Acceptance

- [ ] Opinion covers SRRC, network access/product category, CCC applicability,
      SAR/EM exposure, LTE/GNSS/Wi-Fi/BLE combination, battery/charging,
      waterproof/safety and child-product applicability.
- [ ] Each conclusion records source, date, scope, owner and candidate identity;
      unanswered items remain open instead of inferred.
- [ ] Required antenna, enclosure, label, test-mode and sample changes feed the
      A0->A1 matrix before PCB freeze.

# Current State

HW-020 is accepted as the concept/interface baseline and a conditional inquiry
draft is ready at `docs/compliance/CHINA_PRECOMPLIANCE_INQUIRY_V0.md`. Qualified
external response and exact candidate documents are still required. No sent
inquiry is recorded in repository evidence, so this remains queued for founder
authorization rather than `waiting_external`; it does not block LOC/CALL
software. Final BOM is not a prerequisite to asking conditional questions.

# Validation Commands

```powershell
python scripts/context_lint.py
git diff --check
```

# Completion Evidence

- Changed files: internal intake plus a concept-bound `NOT_SENT` inquiry draft;
  external response pending.
- Test result: pending end-of-cycle context lint/diff check.
- Hardware result: not required.
- Evidence: no sent inquiry or qualified opinion is recorded.
- Remaining risks: exact product configuration, applicant/market assumptions
  and every formal applicability conclusion.

# Builder Prompt

```text
Read docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. This is the sole active successor to PROD-002. Prepare a bounded,
versioned evidence intake and professional inquiry tied to the HW-020 concept;
keep every unknown explicit and separate RTC launch needs from Native VoLTE
reserve. Do not treat web/vendor material as legal or lab approval, freeze a
BOM, purchase, contract, submit an application or send an external message
without explicit founder authorization. If a named qualified response is
provided, record source/date/scope/configuration and translate only supported
requirements into A0-to-A1 inputs. Run every validation command and return
changed files, evidence references, open founder decisions and remaining risk.
Keep execution_state queued until an inquiry is actually authorized and sent.
```
