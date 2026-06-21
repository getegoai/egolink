# Safety Companion M0 integration report

## Repository baseline

- Commit: `0bce67b`
- Firmware framework/version: ESP-IDF firmware directories are present under
  `firmware/mqtt_heartbeat` and `firmware/camera_smoke`; this shell does not
  currently have `idf.py` on `PATH`, so no firmware build was executed in this
  task.
- PC Simulator entry point: `python pc_simulator/app.py --host 127.0.0.1 --port 8787`
- Python version: `Python 3.13.13`
- Hardware tested: no new hardware validation in M0-INT-001. This task only
  verified the Safety Companion M0 overlay package and existing automated tests.

## Completed tasks

- [x] M0-INT-001 package verification
- [ ] M0-INT-002 PC Simulator adapter
- [ ] M0-INT-003 firmware model interface
- [ ] M0-INT-004 simulated end-to-end flow

## Changed files

Installed and validated the Safety Companion M0 overlay:

- `MODEL_PACKAGE_README.md`
- `CHANGELOG_SAFETY_COMPANION.md`
- `PACKAGE_MANIFEST.json`
- `docs/modeling/AGENTS_MODELING_APPEND.md`
- `docs/modeling/CODEX_INTEGRATION_PROMPT.md`
- `docs/modeling/DATA_COLLECTION_SPEC.md`
- `docs/modeling/INTEGRATION_REPORT_TEMPLATE.md`
- `docs/modeling/INTEGRATION_TASKS.md`
- `docs/modeling/MODEL_HANDOFF.md`
- `docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md`
- `model_lab/safety_companion/**`
- `model_artifacts/safety_companion/**`
- `shared/contracts/**`
- `shared/embedded/**`
- `quality_tests/model_contract/**`
- `scripts/verify_safety_companion_m0.py`
- `scripts/run_safety_companion_tests.ps1`
- `scripts/run_safety_companion_tests.sh`

Integration compatibility updates made during verification:

- `quality_tests/model_contract/test_contract_schemas.py`
- `model_lab/safety_companion/export/generate_c_header.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/modeling/INTEGRATION_ISSUES.md`

## Verification commands and results

```powershell
python scripts\verify_safety_companion_m0.py
```

Result: passed. The package self-check ran contract tests, package unit tests,
the 12-scenario demo, baseline evaluation, and generated C threshold header
comparison successfully.

```powershell
python -m model_lab.safety_companion.src.cli demo
```

Result: passed. All 12 synthetic scenarios returned the expected baseline
decision.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 66 tests successfully.

Manifest validation:

- Result: passed. `PACKAGE_MANIFEST.json` matched 55 files by SHA-256 and byte
  size after the integration notes were updated.

## Hardware validation status

No new firmware flashing, GNSS probing, camera capture, MQTT broker test, or SIM
test was performed for M0-INT-001.

Existing hardware status remains unchanged from the previous project state:
ESP32-S3 MQTT heartbeat, SIM7670G LTE data attachment, and GNSS no-fix reporting
had already been validated before this overlay package verification.

## Known gaps

- `pc_simulator/safety_companion.py` is still the earlier T023 deterministic
  mock adapter and uses the old local contract shape/actions. It has not yet
  been replaced with an adapter that calls
  `model_lab.safety_companion.RuleRouter` and `build_model_input`.
- `POST /api/safety/evaluate` is not implemented yet.
- Firmware does not yet expose the `shared/embedded/safety_model_contract.h`
  model boundary.
- M0 rules are only a deterministic baseline and synthetic scenario check; they
  do not prove real-world fall, accident, distress, or child-safety accuracy.

## Contract issues

- The pre-existing repository contract test targeted the earlier
  `safety-companion.contract.v0.1` shape. It was updated to validate the
  official M0 `contract_version = 1.0.0` schemas instead. No model contract
  fields or enum meanings were changed.
- On Windows, generated C header comparison can become sensitive to CRLF vs LF
  line endings. `generate_c_header.py` now writes LF explicitly so the generated
  threshold header remains byte-stable across platforms. No threshold values or
  model semantics were changed.
- The T023 PC Simulator mock adapter is intentionally not treated as compliant
  with the new M0 package. It should be replaced in M0-INT-002 rather than
  silently mapped through renamed fields.

## Recommended next step

Start M0-INT-002 only: implement the PC Simulator adapter that calls
`RuleRouter` and `build_model_input`, add a testable `/api/safety/evaluate`
entry point, verify it against `scenario_suite.json`, and rerun
`python scripts\verify_safety_companion_m0.py`.
