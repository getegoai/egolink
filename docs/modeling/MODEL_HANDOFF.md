# Safety Companion M0 Handoff

## Package

- Name: Safety Companion M0
- Contract version: `safety-companion.contract.v0.1`
- Purpose: define the first stable model/data boundary before real model
  training begins.

## What This Handoff Contains

- Architecture summary: `docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md`
- Integration tasks: `docs/modeling/INTEGRATION_TASKS.md`
- Integration issue log: `docs/modeling/INTEGRATION_ISSUES.md`
- JSON contracts:
  - `shared/contracts/sensor_frame.schema.json`
  - `shared/contracts/safety_event.schema.json`
  - `shared/contracts/model_input.schema.json`
  - `shared/contracts/model_output.schema.json`
  - `shared/contracts/base_command.schema.json`
- Contract tests: `quality_tests/model_contract/test_contract_schemas.py`

## Rules For Codex Integration

- Do not modify `model_lab/` or `model_artifacts/` when those directories are
  later delivered by model packages.
- Do not change `shared/contracts/` fields, units, enum meaning, or feature
  order as part of a firmware/dashboard integration task.
- Add adapters in firmware or PC Simulator code when existing data needs to be
  mapped into model inputs.
- Keep every model call switchable between mock and real implementations.
- Hardware-dependent behavior must be reported as unverified unless the hardware
  was actually exercised.
- Passing unit tests or builds is not evidence of model accuracy.

## Current Scope

This M0 handoff does not include a neural network. The first useful milestone is
to route existing Ego Link events into a stable model input, return a
deterministic mock model output, and let PC Simulator display or act on that
structured result.

