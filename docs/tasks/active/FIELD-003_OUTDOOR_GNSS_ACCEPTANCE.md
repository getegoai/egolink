---
id: FIELD-003
title: Outdoor GNSS acceptance protocol and first measured run
status: active
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-07-03
last_updated: 2026-07-11

context:
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/FIELD_TEST.md
  - docs/hardware/BOARD_MATRIX.md

allowed_paths:
  - scripts/
  - docs/hardware/
  - docs/development/FIELD_TEST.md
  - quality_tests/
  - reports/gnss/

out_of_scope:
  - firmware GNSS driver changes
  - EALE-P0 algorithm/threshold changes
  - product accuracy claims
  - indoor testing (already covered; indoor is no-fix by design)
execution_state: queued
owner: gemini
reviewed_at: 2026-09-22
---

# Problem

All GNSS evidence so far is indoor no-fix or a single opportunistic
`fix=true` observation marked unverified (FW-002C fix3). EALE-P0 assigns
GNSS the dominant weight and derives a 25 m Fine radius from `hdop*8`, but no
measured outdoor fix rate, time-to-first-fix (TTFF), or position error exists.
V1's core feature (reliable real-time location) rests on unmeasured
assumptions.

# Expected Result

A written, repeatable outdoor GNSS acceptance protocol plus the first executed
run: N reference points with known coordinates, M repetitions each, recording
fix rate, TTFF, reported hdop, and error radius vs reference — producing a
report that either supports or corrects the EALE-P0 engineering defaults.

# Acceptance Criteria

- [ ] Protocol document `docs/hardware/FIELD_GNSS_ACCEPTANCE_PROTOCOL.md`:
      at least 3 reference point types (open sky, street between buildings,
      under tree cover), >= 5 cold/warm attempts per point, reference
      coordinates sourced from a stated method (phone GNSS averaged or map
      pick, with method recorded), USB-Free evidence via VPS only.
- [ ] Analysis script computes per-point fix rate, TTFF distribution, error
      distance (haversine vs reference), and hdop-vs-error correlation from
      exported VPS observations; unit test with synthetic fixture.
- [ ] First protocol run executed by the operator; raw evidence and generated
      report stored under `reports/gnss/FIELD-003-<date>/`.
- [ ] Report compares measured error radii against the EALE-P0 `hdop*8`
      Fine-radius assumption and states whether defaults need revision (the
      revision itself is a separate ALG task).
- [ ] `docs/hardware/BOARD_MATRIX.md` GNSS row updated from
      "real-fix observed (unverified)" to a measured statement with evidence
      link.
- [ ] `scripts/verify.ps1` passes.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Board: connectivity-node (Waveshare ESP32-S3-SIM7670G), battery or power
  bank, USB-Free
- Firmware commit: record at flash time
- Connection: VPS Message Hub only
- Expected output: per-attempt GNSS observations with fix/no-fix, hdop,
  coordinates, timestamps
- Evidence path: reports/gnss/FIELD-003-<date>/

# Decisions

- Results are engineering acceptance records, not product accuracy claims
  (consistent with EALE-P0 non-claim policy).
- 2026-07-04: Paused by NORTH_STAR alignment. D1 only requires a visible
  location estimate, not outdoor accuracy acceptance; resume for D2.
- 2026-07-09: Resumed by founder direction. D1 outdoor testing continues as
  regression, while D2 now needs measured fix rate, TTFF, and error evidence.

# Completion Evidence

- Changed files:
- Test result:
- Hardware result:
- Evidence path:
- Remaining risks:

# Progress

- 2026-07-11: `scripts/prepare_d2_field_kit.py` now generates the full strict
  manifest, operator runbook, checklist, preflight observer, and one-command
  post-run path. `run_location_d2_d5_pipeline.py` can fetch the named VPS
  test-run export read-only and run the existing D2/D5 processors. The real
  outdoor reference-point measurements remain pending.
- 2026-07-11 VPS smoke: registered the already firmware-emitted
  `MODEL-DEVICE-006-hw-20260707-d1` test-run ID in Message Hub metadata, then
  confirmed its read-only export endpoint. No device command or firmware
  action was performed.

# Builder Prompt

```text
Read docs/tasks/active/FIELD-003_OUTDOOR_GNSS_ACCEPTANCE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Write the protocol document and analysis tooling with tests;
the outdoor run itself is an operator action — produce exact field
instructions and a fillable evidence checklist for it. Run the validation
commands before finishing. If any acceptance criterion cannot be met, stop
and report the blocker. Return: changed files, validation output, evidence
paths. Do not update docs/current/STATUS.md and do not move this packet to
done/.
```
