---
id: P0-RELEASE-010
title: Saleable P0 release criteria and evidence review
status: active
priority: critical
lane: release
execution_state: queued
depends_on:
  - FIELD-020
  - CALL-031
  - SOS-010
  - OUTBOX-010
  - OPS-004
  - PWR-020
  - HW-022
  - COMPLIANCE-010
serves_gate: P0-LOC/P0-CALL/P0-SOS/product-assurance
requires_hardware: true
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md

allowed_paths:
  - docs/tasks/active/P0-RELEASE-010_SALEABLE_P0_REVIEW.md

out_of_scope:
  - changing a component result or `NOT_RUN` Gate to PASS by document review
  - choosing convenient thresholds after viewing the final acceptance run
  - treating A0 or split-board evidence as representative production evidence
---

## 2026-09-22 primary-cellular dependency alignment

ADR-0016 replaces the old RTC primary-path dependency with CALL-030 feasibility
and CALL-031 native cellular product evidence. CALL-020/021 remain paused RTC
assets. The criteria below retain their reliability/privacy/product invariants;
current references to Ego Call mean native cellular primary, with RTC auxiliary.
Historical implementation checkpoints remain dated evidence, not a new result.
No Gate or hardware state advances from this dependency update.


# Goal

Own the single release matrix that decides whether one representative product
revision is a saleable P0 rather than a collection of working components.

# Acceptance

- [ ] Before final acceptance runs, Gate Criteria v0 freezes measurement
      definitions and PASS thresholds for location availability/staleness/
      error, call setup/gaps/recovery, and SOS local/durable/upload/call timing.
      Sensor sampling intervals remain configurable and are not guessed here.
- [ ] `P0-LOC`, `P0-CALL` and `P0-SOS` each have representative hardware,
      configuration identity, scenario coverage, raw/private evidence path,
      reviewer and explicit `PASS`/`FAIL`/`NOT_RUN` state.
- [ ] G8 includes the local-first endpoint/relay retention and deletion evidence; BASE-010 is its minimal engineering input, not an advanced-AI release requirement.
- [ ] G3 power, G4 durability, G5 water/acoustic, G6 RF, G7 NPI,
      G8 security/privacy and G9 China compliance have the same accountable
      evidence rows. Missing specialist tasks are created before review.
- [ ] One integrated representative-day loop proves honest location, both call
      directions and physical SOS; the 48-hour guard result uses the same
      product revision or a documented re-test-equivalent revision.
- [ ] Any missing/failed capability or assurance row stops release. L2/L3 and
      optional RTC never compensate for a failed P0 row.

# Execution Rule

This packet may prepare the matrix and measurement definitions early, but
numeric thresholds must be frozen from declared product intent and baseline
evidence before final runs. It cannot self-approve component evidence.

# Validation

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Criteria matrix, reviewers, Gate states and evidence paths: pending.
- Current capability state: `P0-LOC=NOT_RUN`, `P0-CALL=NOT_RUN`,
  `P0-SOS=NOT_RUN`.
