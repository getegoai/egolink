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
- [x] M0-INT-002 PC Simulator adapter
- [x] M0-INT-003 firmware model interface
- [x] M0-INT-004 simulated end-to-end flow

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

M0-INT-002 PC Simulator adapter updates:

- `pc_simulator/safety_companion.py`
- `pc_simulator/app.py`
- `quality_tests/test_safety_companion.py`
- `quality_tests/test_pc_simulator.py`

M0-INT-003 firmware model interface updates:

- `firmware/mqtt_heartbeat/components/safety_model/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/safety_model/include/safety_model.h`
- `firmware/mqtt_heartbeat/components/safety_model/safety_model.c`
- `firmware/mqtt_heartbeat/main/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `quality_tests/test_safety_model_firmware.py`
- `docs/tasks/CURRENT_TASK.md`
- `docs/STATUS.md`

M0-INT-004 simulated end-to-end updates:

- `pc_simulator/safety_companion.py`
- `pc_simulator/app.py`
- `quality_tests/test_safety_companion.py`
- `quality_tests/test_pc_simulator.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T027 real event safety flow updates:

- `pc_simulator/safety_companion.py`
- `pc_simulator/app.py`
- `quality_tests/test_safety_companion.py`
- `quality_tests/test_pc_simulator.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T028 supervised live MQTT safety processing updates:

- `pc_simulator/mqtt_worker.py`
- `quality_tests/test_mqtt_worker.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T029 local supervised session updates:

- `scripts/start_local_supervised_session.ps1`
- `scripts/local_session_summary.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

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

Result: passed. The repository test suite ran 90 tests successfully.

```powershell
python -m unittest quality_tests.test_local_session_summary -v
```

Result: passed. The local supervised session tests ran 3 tests successfully,
covering event summary counts, JSON/Markdown report writing, and the
PowerShell session runner contract.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
```

Result: passed. The command created a new
`pc_simulator/runtime/sessions/<timestamp>/` directory, wrote `session.log`,
`session_summary.json`, and `session_summary.md`, and did not start new
background processes.

```powershell
python scripts\local_session_summary.py --event-log pc_simulator\runtime\events.jsonl --limit 8 --markdown
```

Result: passed. The summary reported the latest Safety risk as `manual_sos`,
the latest action as `urgent_escalation`, and counted recent
`safety_evaluation`, `safety_event`, and simulated command records.

```powershell
python -m unittest quality_tests.test_mqtt_worker -v
```

Result: passed. The MQTT worker tests ran 12 tests successfully, including the
supervised `--process-safety` option, after-store hook behavior, bad-line
skipping, safety-processing failure isolation, and progress output.

```powershell
python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v
```

Result: passed. The PC Simulator adapter tests ran 26 tests successfully,
including packaged scenario inputs, sensor frame evaluation, safety event
conversion, privacy evidence filtering, `POST /api/safety/evaluate`, and
`POST /api/safety/replay`. T027 also covers real `sensor_sample` field mapping,
`POST /api/safety/process-events`, and idempotent event-log processing.

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90 --process-safety --safety-process-limit 20
```

Result: passed. The worker received a real ESP32-S3 firmware `sensor_sample`
with `seq=9064`, stored it in `pc_simulator/runtime/events.jsonl`, and
immediately processed one source event through Safety Companion. It wrote one
`safety_evaluation` with `risk_type=none` and did not generate a `safety_event`
or simulated command.

M0-INT-004 replay result:

- `normal_walk`: `risk_type=none`, no `safety_event`, no `base_command`.
- `manual_sos`: `risk_type=manual_sos`, generates `safety_event` and simulated
  `ask_user` command for `urgent_escalation`.
- `post_impact_inactivity`: generates `safety_event` and simulated `ask_user`
  command.
- `privacy_restricted_impact`: generates `safety_event` and simulated
  `ask_user` command while filtering raw audio/image evidence.

```powershell
python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_mqtt_heartbeat_firmware -v
```

Result: passed. Firmware-side static tests ran 8 tests successfully, covering
the `safety_model` component, required public API, mock SOS rule, mock-state
adapter fields, and serial CLI command registration.

```powershell
idf.py --version
```

Result: not run successfully. `idf.py` is not available in this shell, so
firmware build/flash validation was not performed in M0-INT-003.

Manifest validation:

- Result: passed. `PACKAGE_MANIFEST.json` matched 55 files by SHA-256 and byte
  size after the integration notes were updated.

## Hardware validation status

No new firmware flashing, GNSS probing, camera capture, MQTT broker test, or SIM
test was performed for M0-INT-001, M0-INT-002, or M0-INT-003.

M0-INT-004 did not use hardware and did not trigger real calls, camera capture,
audio recording, or external network actions. It only writes simulated
`safety_event` and command records into the PC Simulator event log.

T027 processed existing local runtime event logs only. The bounded validation
processed 12 evaluable recent events and wrote 12 `safety_evaluation`, 3
`safety_event`, and 3 simulated command records. It did not perform firmware
flashing, MQTT subscription, GNSS probing, calls, camera capture, audio
recording, or external network actions.

T028 performed a supervised live MQTT pass against the local LAN broker at
`192.168.31.250:1883`. The worker received one real ESP32-S3 `sensor_sample`
and wrote its paired `safety_evaluation`. A follow-up Dashboard API idempotency
check returned `processed=0` for the already processed live event.

T028 also ran a fresh SIM7670G GNSS no-fix probe:
`reports/gnss_validation/20260621-161721/gnss_probe.md`. `COM6` and `COM7`
were AT-reachable, `gnss_power_state=1`, and the probe wrote a
`location_report` with `fix=false`. Processing that no-fix event plus a
Dashboard-simulated SOS wrote 2 `safety_evaluation`, 1 `safety_event`, and 1
no-side-effect simulated command.

T029 did not perform new hardware I/O. It added a local session runner and
validated it in no-start mode so it can generate a session health summary
without changing broker, Dashboard, worker, modem, camera, or firmware state.

Existing hardware status remains unchanged from the previous project state:
ESP32-S3 MQTT heartbeat, SIM7670G LTE data attachment, and GNSS no-fix reporting
had already been validated before this overlay package verification.

## Known gaps

- `pc_simulator/safety_companion.py` now calls the packaged `RuleRouter` and
  `build_model_input`; it no longer copies local decision rules.
- Firmware now exposes a `safety_model` component boundary around
  `shared/embedded/safety_model_contract.h`, but it has only been statically
  tested in this shell.
- M0-INT-003 did not perform ESP-IDF build, flash, or serial CLI hardware
  validation because `idf.py` is not available on the current `PATH`.
- M0-INT-004 is a simulated replay flow only. It validates message shape,
  routing, logging, and display behavior, not real-world incident detection.
- T029 adds a one-command local supervised session runner, but it is still an
  explicitly launched CLI script rather than a Windows service with restart
  policy, log rotation, or long-running health supervision.
- M0 rules are only a deterministic baseline and synthetic scenario check; they
  do not prove real-world fall, accident, distress, or child-safety accuracy.
- The earlier T023 adapter treated GNSS no-fix as a device risk. The official
  M0 rule package does not include this product rule, so the M0-INT-002 adapter
  does not promote GNSS no-fix into a model risk by itself.

## Contract issues

- The pre-existing repository contract test targeted the earlier
  `safety-companion.contract.v0.1` shape. It was updated to validate the
  official M0 `contract_version = 1.0.0` schemas instead. No model contract
  fields or enum meanings were changed.
- On Windows, generated C header comparison can become sensitive to CRLF vs LF
  line endings. `generate_c_header.py` now writes LF explicitly so the generated
  threshold header remains byte-stable across platforms. No threshold values or
  model semantics were changed.
- The T023 PC Simulator mock adapter was replaced in M0-INT-002 by a thin
  adapter over the packaged model API. Old action names such as
  `escalate_emergency` and `upload_summary` are no longer produced by the
  adapter; M0 uses `urgent_escalation` and `send_summary`.

## Recommended next step

Next, connect the local supervised session summary with the AutoDev progress
monitor so development status and device/safety-flow status can be viewed in
one place.
