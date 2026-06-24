# Safety Companion M0 integration report

## Repository baseline

- Commit: `0bce67b`
- Firmware framework/version: ESP-IDF v5.4.2 is available through
  `C:\Espressif\v5.4.2\esp-idf\export.ps1`; `firmware/mqtt_heartbeat` built
  successfully for ESP32-S3 during HPWR-001 and was flashed to `COM4` during
  HDATA-001. The same firmware also built successfully after T039 added
  `platform_imu`. `firmware/camera_smoke` was flashed to `COM4` during
  TCAM-001 to collect current camera UART evidence. HDBRIDGE-001 added a
  PC-only dual-board bridge PoC without live serial hardware I/O. HDBRIDGE-002
  flashed `firmware/amoled_bridge` to ESP32-S3-Touch-AMOLED-2.06 `COM9` and
  captured live QMI8658 WHOAMI plus a bounded sample window over USB JSONL.
  TIMU-002 analyzed that window and found identity/orientation sane but sample
  timing below the requested 20 Hz target. TIMU-003 fixed the AMOLED bridge
  scheduler with `vTaskDelayUntil`, captured a 120-sample live QMI8658 window,
  and measured about `49.99 ms / 20.00 Hz`. TIMU-004A added a pose/motion
  analyzer and captured a single live `z_negative` static pose window; pose
  quality passed for that pose. TIMU-004B added a bounded COM9 capture helper
  and completed manual `z_negative` / `x_positive` / `y_positive` three-pose
  evidence with M1 quality/replay closure. TIMU-005 extended the helper with
  `-MotionOnly` and `-ExistingPose`, captured a live rotation/light-tap motion
  window, passed motion sanity, and closed the merged M1 quality/replay loop
  with 480 `imu_motion` frames. TIMU-006 made the AMOLED bridge window
  configurable, captured a 600-sample long window, passed timing and jitter
  gates, and closed the M1 loop with 600 `imu_motion` frames. TIMU-007 added a
  default-mock, opt-in QMI8658 `platform_imu` backend boundary and kept the P0
  firmware default on mock IMU metadata; the opt-in QMI8658 backend also passed
  compile-only validation. TIMU-008 flashed that opt-in QMI8658 backend profile
  to the ESP32-S3-Touch-AMOLED-2.06 board on `COM9`, verified AXP2101 rail
  enable and QMI8658 WHOAMI, captured boot samples plus MQTT payloads with
  `imu_sample_mock=false`, and closed an 8-frame M1 recording/quality/replay
  loop. TIMU-009A then generated an engineering-only calibration profile from
  the existing TIMU-004B three-pose captures, with same-axis/same-sign x/y/z
  mapping and a temporary accel offset estimate of about
  `[48.0, -10.3, -24.0] mg`; it explicitly remains
  `production_ready=false`. TIMU-009B added a product acceptance preflight
  gate ledger; the generated report is expected to fail today because no
  hardware-observed artifacts exist for final mounting, production calibration,
  FIFO/DRDY, backend replay, or current-waveform gates. Formal IMU acceptance
  still remains false because product mounting, FIFO/interrupt, final
  calibration, and power gates are pending.
- PC Simulator entry point: `python pc_simulator/app.py --host 127.0.0.1 --port 8787`
- Python version: `Python 3.13.13`
- Hardware tested: M0-INT-001 itself performed no hardware validation. Later
  hardware tasks in this report exercised the Waveshare ESP32-S3-SIM7670G-4G
  board, standalone camera smoke firmware on `COM4`, and the
  ESP32-S3-Touch-AMOLED-2.06 QMI8658 path on `COM9`.

## Completed tasks

- [x] M0-INT-001 package verification
- [x] M0-INT-002 PC Simulator adapter
- [x] M0-INT-003 firmware model interface
- [x] M0-INT-004 simulated end-to-end flow
- [x] M1-001 hardware sensor matrix
- [x] M1-002 session recorder skeleton
- [x] M1-004-pre session inspector quality gate
- [x] M1-004-pre quality gate monitor integration
- [x] M1-004-pre session file integrity
- [x] M1-004 PC session import / replay
- [x] HCTX-001 hardware context sensor matrix update
- [x] T038 hardware usability smoke validation
- [x] T037 M1-005 minimal session annotation CLI
- [x] HARCH-001 platform coupling audit
- [x] HARCH-002A minimal platform_power interface
- [x] HPWR-001 power state events and measurement markers
- [x] HDATA-001 live HPWR data capture loop
- [x] T039 IMU mock driver interface and ring buffer
- [x] T039 IMU mock live MQTT capture and `sensor_task` stack fix
- [x] TIMU-001 real IMU bring-up evidence gate
- [x] TCAM-001 camera smoke live capture evidence
- [x] HDBRIDGE-001 dual-board PC bridge PoC
- [x] HDBRIDGE-002 AMOLED USB CDC QMI8658 live window
- [x] TIMU-002 QMI8658 sample quality gate
- [x] TIMU-003 QMI8658 timing retest
- [x] TIMU-004A QMI8658 single-pose quality gate
- [x] TIMU-004B QMI8658 manual three-pose capture
- [x] TIMU-005 QMI8658 motion window capture
- [x] TIMU-006 QMI8658 long-window capture
- [x] TIMU-007 platform_imu backend-boundary PoC
- [x] TIMU-008 platform_imu QMI8658 backend live capture
- [x] TIMU-009A IMU engineering calibration boundary
- [x] TIMU-009B IMU product acceptance preflight gate

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

T030 unified AutoDev and device monitor updates:

- `scripts/autodev.py`
- `scripts/watch_autodev.ps1`
- `autodev/tests/test_supervisor.py`
- `docs/AUTODEV_MONITORING.md`
- `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
- `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`
- `README.md`

T031 M1 hardware sensor matrix updates:

- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T032 M1 session recorder skeleton updates:

- `pc_simulator/session_recorder.py`
- `scripts/session_recorder.py`
- `scripts/start_local_supervised_session.ps1`
- `quality_tests/test_session_recorder.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T033 M1 session inspector quality gate updates:

- `pc_simulator/session_inspector.py`
- `pc_simulator/session_recorder.py`
- `scripts/inspect_session_recording.py`
- `quality_tests/test_session_inspector.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T034 quality gate monitor integration updates:

- `scripts/start_local_supervised_session.ps1`
- `scripts/autodev.py`
- `autodev/tests/test_supervisor.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T035 session file integrity updates:

- `pc_simulator/session_recorder.py`
- `pc_simulator/session_inspector.py`
- `quality_tests/test_session_recorder.py`
- `quality_tests/test_session_inspector.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T036 PC session import / replay updates:

- `pc_simulator/session_replay.py`
- `scripts/replay_session_recording.py`
- `quality_tests/test_session_replay.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

HCTX-001 hardware context updates:

- `HARDWARE_CONTEXT_PACKAGE_README.md`
- `PACKAGE_MANIFEST.json`
- `docs/hardware/**`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T038 hardware usability smoke updates:

- `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

T037 M1-005 session annotation updates:

- `pc_simulator/session_annotations.py`
- `pc_simulator/session_inspector.py`
- `pc_simulator/session_replay.py`
- `scripts/annotate_session_recording.py`
- `quality_tests/test_session_annotations.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

HARCH-001 platform coupling audit updates:

- `docs/hardware/PLATFORM_COUPLING_AUDIT.md`

HARCH-002A minimal platform_power updates:

- `firmware/mqtt_heartbeat/components/platform_power/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/platform_power/include/platform_power.h`
- `firmware/mqtt_heartbeat/components/platform_power/platform_power.c`
- `firmware/mqtt_heartbeat/main/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_power_firmware.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

HPWR-001 power marker updates:

- `firmware/mqtt_heartbeat/components/platform_power/include/platform_power.h`
- `firmware/mqtt_heartbeat/components/platform_power/platform_power.c`
- `firmware/mqtt_heartbeat/main/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_power_firmware.py`
- `docs/hardware/POWER_MEASUREMENT_SCENARIO_TEMPLATE.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

HDATA-001 live capture updates:

- `docs/hardware/HDATA_001_LIVE_CAPTURE_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`
- `pc_simulator/runtime/hdata-001-hpwr-live-20260623-0906-events.jsonl`
- `pc_simulator/runtime/recordings/hdata-001-hpwr-live-20260623-0906/`
- `reports/board_validation/20260623-090047/probe.md`
- `reports/gnss_validation/20260623-090637/gnss_probe.md`

T039 IMU mock/ring updates:

- `firmware/mqtt_heartbeat/components/platform_imu/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/platform_imu/include/platform_imu.h`
- `firmware/mqtt_heartbeat/components/platform_imu/platform_imu.c`
- `firmware/mqtt_heartbeat/main/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_imu_firmware.py`
- `docs/hardware/T039_IMU_MOCK_LIVE_CAPTURE_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`
- `pc_simulator/runtime/hdata-001-imu-mock-live-20260623-0926-events.jsonl`
- `pc_simulator/runtime/recordings/hdata-001-imu-mock-live-20260623-0926/`
- `reports/board_validation/20260623-092315/probe.md`

TIMU-001 real IMU bring-up evidence gate updates:

- `docs/hardware/TIMU_001_REAL_IMU_BRINGUP_PLAN.md`
- `quality_tests/test_imu_bringup_plan.py`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TCAM-001 camera smoke live capture updates:

- `firmware/camera_smoke/main/app_main.c`
- `firmware/camera_smoke/README.md`
- `quality_tests/test_camera_smoke_firmware.py`
- `docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`
- `pc_simulator/runtime/camera-smoke-live-20260623-1842-uart.log`

HDBRIDGE-001 dual-board PC bridge PoC updates:

- `pc_simulator/board_bridge.py`
- `scripts/board_bridge.py`
- `quality_tests/test_board_bridge.py`
- `pc_simulator/session_recorder.py`
- `pc_simulator/session_inspector.py`
- `docs/hardware/HDBRIDGE_001_DUAL_BOARD_PC_BRIDGE_POC_20260623.md`
- `docs/hardware/双板开发架构.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

HDBRIDGE-002 AMOLED USB CDC QMI8658 live window updates:

- `firmware/amoled_bridge/CMakeLists.txt`
- `firmware/amoled_bridge/main/CMakeLists.txt`
- `firmware/amoled_bridge/main/app_main.c`
- `firmware/amoled_bridge/sdkconfig.defaults`
- `firmware/amoled_bridge/README.md`
- `quality_tests/test_amoled_bridge_firmware.py`
- `docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-002 QMI8658 sample quality gate updates:

- `pc_simulator/imu_quality.py`
- `scripts/analyze_imu_quality.py`
- `quality_tests/test_imu_quality.py`
- `docs/hardware/TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-003 QMI8658 timing retest updates:

- `firmware/amoled_bridge/main/app_main.c`
- `firmware/amoled_bridge/README.md`
- `pc_simulator/imu_quality.py`
- `quality_tests/test_amoled_bridge_firmware.py`
- `quality_tests/test_imu_quality.py`
- `docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-004A QMI8658 single-pose quality gate updates:

- `pc_simulator/imu_pose_quality.py`
- `scripts/analyze_imu_pose_quality.py`
- `quality_tests/test_imu_pose_quality.py`
- `pc_simulator/imu_quality.py`
- `pc_simulator/board_bridge.py`
- `quality_tests/test_imu_quality.py`
- `quality_tests/test_board_bridge.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-004B QMI8658 manual three-pose capture updates:

- `scripts/capture_amoled_qmi8658_pose_set.ps1`
- `quality_tests/test_amoled_pose_capture_script.py`
- `docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-005 QMI8658 motion window capture updates:

- `scripts/capture_amoled_qmi8658_pose_set.ps1`
- `quality_tests/test_amoled_pose_capture_script.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-006 QMI8658 long-window capture updates:

- `firmware/amoled_bridge/main/Kconfig.projbuild`
- `firmware/amoled_bridge/main/app_main.c`
- `firmware/amoled_bridge/sdkconfig`
- `firmware/amoled_bridge/sdkconfig.defaults`
- `firmware/amoled_bridge/README.md`
- `pc_simulator/imu_quality.py`
- `scripts/capture_amoled_qmi8658_pose_set.ps1`
- `quality_tests/test_amoled_bridge_firmware.py`
- `quality_tests/test_amoled_pose_capture_script.py`
- `quality_tests/test_imu_quality.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-007 platform_imu backend-boundary updates:

- `firmware/mqtt_heartbeat/components/platform_imu/include/platform_imu.h`
- `firmware/mqtt_heartbeat/components/platform_imu/platform_imu.c`
- `firmware/mqtt_heartbeat/components/platform_imu/Kconfig.projbuild`
- `firmware/mqtt_heartbeat/components/platform_imu/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/sdkconfig.defaults`
- `firmware/mqtt_heartbeat/sdkconfig.qmi8658.defaults`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_imu_firmware.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_007_PLATFORM_IMU_REAL_BACKEND_POC_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-008 platform_imu QMI8658 backend live-capture updates:

- `firmware/mqtt_heartbeat/components/platform_imu/platform_imu.c`
- `firmware/mqtt_heartbeat/components/platform_imu/Kconfig.projbuild`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/sdkconfig.qmi8658.defaults`
- `firmware/mqtt_heartbeat/README.md`
- `quality_tests/test_platform_imu_firmware.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_008_PLATFORM_IMU_QMI_BACKEND_LIVE_CAPTURE_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-009A IMU engineering calibration boundary updates:

- `pc_simulator/imu_calibration.py`
- `scripts/generate_imu_calibration_profile.py`
- `quality_tests/test_imu_calibration.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json`
- `docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

TIMU-009B IMU product acceptance preflight updates:

- `pc_simulator/imu_acceptance.py`
- `scripts/check_imu_acceptance.py`
- `quality_tests/test_imu_acceptance.py`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.json`
- `docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## Verification commands and results

```powershell
python -m unittest quality_tests.test_platform_power_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_safety_model_firmware -v
```

Result: passed for HPWR-001. The platform-power, MQTT heartbeat, and firmware
Safety static tests ran 14 tests successfully. Coverage includes the
`platform_power` component API, HPWR state vocabulary, structured power-event
markers, explicit mock battery/charging boundary, main firmware payload
integration, README caveats, and existing MQTT/Safety firmware contracts.

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_platform_power_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_safety_model_firmware -v
```

Result: passed for T039 after the live stack fix. The platform-IMU,
platform-power, MQTT heartbeat, and firmware Safety static tests ran 20 tests
successfully. Coverage includes the `platform_imu` API, 32-sample ring buffer
skeleton, explicit mock boundary, main firmware IMU payload fields, sensor
payload stack protection, README caveats, and existing power/MQTT/Safety
contracts.

```powershell
python -m unittest quality_tests.test_hardware_sensor_matrix -v
```

Result: passed after T039. The hardware matrix tests ran 5 tests successfully,
including the updated IMU mock/ring boundary and the still-unverified real IMU
hardware path.

```powershell
python -m unittest quality_tests.test_imu_bringup_plan -v
```

Result: passed for TIMU-001. The test covers the real IMU evidence gate,
candidate IMU paths from local procurement materials, the current mock-only
T039 payload boundary, and the required conditions before
`imu_hardware_present=true` or `imu_sample_mock=false` may appear in live data.

```powershell
python -m unittest quality_tests.test_camera_smoke_firmware -v
```

Result: passed for TCAM-001. The camera smoke firmware tests ran 4 tests
successfully. Coverage includes the Waveshare camera pin profile, bounded
startup capture sequence, JPEG verification fields, and README pass criteria.

```powershell
python -m unittest quality_tests.test_board_bridge quality_tests.test_session_recorder quality_tests.test_session_inspector -v
```

Result: passed for HDBRIDGE-001. The bridge, recorder, and inspector tests ran
12 tests successfully. Coverage includes board `hello` role binding,
`motion_event` normalization, deterministic `ask_user` / `request_location`
command records, `imu_motion` frames with `bridge_uplink` availability, and
quality-gate compatibility.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after HDBRIDGE-001. The repository test suite ran 136 tests
successfully, including the new dual-board PC bridge tests and the existing
camera smoke firmware/documentation contract tests.

```powershell
python -m unittest quality_tests.test_amoled_bridge_firmware -v
```

Result: passed for HDBRIDGE-002. The AMOLED bridge firmware tests ran 4 tests
successfully. Coverage includes the vendor I2C pin map, AXP2101/QMI8658
addresses, QMI8658 WHOAMI expectation, JSONL output contract, bounded sample
window, `bridge_uplink/unverified` source status, and conservative AXP2101
rail bring-up.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

Result: passed for HDBRIDGE-002. The build generated
`egolink_amoled_bridge.bin` for ESP32-S3.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash
```

Result: passed for HDBRIDGE-002. esptool identified ESP32-S3 USB-Serial/JTAG,
8 MB PSRAM, MAC `02:00:00:00:00:01`, wrote the image, verified hashes, and
hard-reset the board.

```powershell
python scripts\board_bridge.py --source wearable=pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --session-id hdb002-amoled-live-20260623-194454 --output-dir pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
```

Result: passed for HDBRIDGE-002 live data. The serial capture contained 43 JSONL
records: `hello`, `imu_whoami`, 40 `imu_sample` records, and
`amoled_bridge_done`. PC Bridge stored 43 events with 0 skipped lines, recorder
created 40 `imu_motion` frames, quality gate passed with score `0.94`, and
replay passed with 40 `risk_type=none` outputs.

```powershell
python -m unittest quality_tests.test_imu_quality -v
```

Result: passed for TIMU-002. The IMU quality tests ran 4 tests successfully.
Coverage includes stable static capture gates, observed-period drift failure,
source-boundary rejection when a capture claims `source_status=verified`, and
JSONL/Markdown report generation.

```powershell
python scripts\analyze_imu_quality.py pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl --json --markdown docs\hardware\TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md
```

Result: completed for TIMU-002. The HDBRIDGE-002 capture passed identity,
completeness, completion, QMI timestamp monotonicity, static orientation, static
gyro, and source-boundary gates. Device timing failed: requested `50 ms / 20 Hz`,
observed mean interval `82.31 ms` and observed sample rate about `12.15 Hz`.
Formal IMU acceptance remains false.

```powershell
python -m unittest quality_tests.test_amoled_bridge_firmware quality_tests.test_imu_quality -v
```

Result: passed for TIMU-003. The AMOLED bridge firmware and IMU analyzer tests
ran 8 tests successfully. Coverage includes fixed-period `vTaskDelayUntil`
sampling, the 120-sample live window contract, timing metadata in the completion
record, configurable analyzer report titles, and the existing IMU quality gates.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

Result: passed for TIMU-003 from `firmware/amoled_bridge`. The build generated
the updated `egolink_amoled_bridge.bin`; the app binary size was `0x38620`.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash
```

Result: passed for TIMU-003. esptool identified ESP32-S3 USB-Serial/JTAG,
8 MB PSRAM, MAC `02:00:00:00:00:01`, wrote the image, verified hashes, and
hard-reset the ESP32-S3-Touch-AMOLED-2.06 board.

```powershell
python scripts\analyze_imu_quality.py pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.jsonl --json --min-samples 100 --title "# TIMU-003 QMI8658 Timing Retest Report" --markdown docs\hardware\TIMU_003_QMI8658_TIMING_RETEST_20260623.md
```

Result: passed for TIMU-003 live data. The capture contained 123 JSONL records:
`hello`, `imu_whoami`, 120 `imu_sample` records, and `amoled_bridge_done`.
The completion record reported `samples_emitted=120`, `timing_mode`
`vTaskDelayUntil`, `missed_deadlines=0`, and `max_sample_work_ms=42`. The
analyzer measured a mean device interval of about `49.99 ms`, an observed sample
rate of about `20.00 Hz`, and all quality gates passed. Formal IMU acceptance
remains false because source status is still intentionally `unverified`.

```powershell
python scripts\board_bridge.py --source wearable=pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.jsonl --event-log pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.events.jsonl --session-id timu003-qmi8658-live-20260623-201436 --output-dir pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu003-qmi8658-live-20260623-201436 --json
```

Result: passed for the TIMU-003 M1 loop. PC Bridge stored 123 events with
0 skipped lines, the recorder created 120 `imu_motion` frames, the quality gate
passed with score `0.94`, and replay passed with 120 `risk_type=none` outputs.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-003. The repository test suite ran 144 tests
successfully, including the timing-fixed AMOLED bridge firmware contract,
IMU quality analyzer, updated hardware matrix, and the existing PC/Firmware/M1
quality gates.

```powershell
python -m unittest quality_tests.test_imu_pose_quality quality_tests.test_imu_quality -v
```

Result: passed for TIMU-004A. The pose/motion analyzer and existing IMU quality
tests ran 10 tests successfully. Coverage includes three-pose quality success,
single-pose coverage failure, mislabeled pose rejection, motion sanity, report
generation, and Windows UTF-8 BOM JSONL handling.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash
```

Result: passed for TIMU-004A. The current AMOLED bridge firmware was rebuilt
and flashed to `COM9`; esptool identified ESP32-S3 USB-Serial/JTAG, 8 MB PSRAM,
MAC `02:00:00:00:00:01`, wrote and verified the image, and hard-reset the
ESP32-S3-Touch-AMOLED-2.06 board.

```powershell
python scripts\analyze_imu_quality.py pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --json --min-samples 100 --title "# TIMU-004 QMI8658 Single Pose Timing Check"
python scripts\analyze_imu_pose_quality.py --pose z_negative=pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --json --markdown docs\hardware\TIMU_004_QMI8658_POSE_QUALITY_20260623.md --title "# TIMU-004 QMI8658 Pose Quality Report"
```

Result: mixed by design for TIMU-004A. The new capture contained 123 JSONL
records with 120 `imu_sample` records and `amoled_bridge_done`. Timing
cross-check passed at about `49.99 ms / 20.00 Hz` with `missed_deadlines=0`.
The single static pose was labeled `z_negative`, measured dominant axis
`z negative`, mean axes about `[56.63, 22.98, -1030.48] mg`, and conservative
offset about `[56.6, 23.0, -30.5] mg`. TIMU-004 total quality remains false:
`pose_count`, `axis_coverage`, `motion_sanity`, and `pose_or_motion_evidence`
failed because no additional physical pose or rotation/tap window was captured.

```powershell
python scripts\board_bridge.py --source wearable=pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl --event-log pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.events-fixed.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.events-fixed.jsonl --session-id timu004-qmi8658-single-pose-live-20260623-203238 --output-dir pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu004-qmi8658-single-pose-live-20260623-203238 --json
```

Result: passed for the TIMU-004A M1 loop. PC Bridge stored 123 events with
0 skipped lines after UTF-8 BOM tolerance was added, the recorder created 120
`imu_motion` frames, the quality gate passed with score `0.94`, and replay
passed with 120 `risk_type=none` outputs.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-004A. The repository test suite ran 151 tests
successfully, including the new QMI8658 pose/motion analyzer, UTF-8 BOM JSONL
tolerance, updated hardware matrix, and the existing PC/Firmware/M1 quality
gates.

```powershell
python -m unittest quality_tests.test_amoled_pose_capture_script quality_tests.test_hardware_sensor_matrix -v
```

Result: passed for TIMU-004B-Prep. The new AMOLED pose capture helper static
contract and hardware matrix evidence-path tests ran 8 tests successfully.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -Help
```

Result: passed for TIMU-004B-Prep. The bounded capture helper help entry is
available and documents static pose, motion, analyzer, and M1-loop usage.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative -NoPrompt -Analyze -RunM1Loop -SessionId timu004b-qmi8658-preflight-live-20260623-205520 -TimeoutSeconds 35
```

Result: passed for TIMU-004B-Prep live preflight. COM9 produced
`pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`
with 123 JSONL records, including 120 `imu_sample` records, `imu_whoami`, and
`amoled_bridge_done`. The single `z_negative` pose measured dominant axis
`z negative`, mean axes about `[56.93, 23.39, -1030.24] mg`, and conservative
offset about `[56.93, 23.39, -30.24] mg`. Static quality, label match,
calibration offset, and source-boundary gates passed. Overall TIMU-004
pose/motion quality still failed by design because this was only one static
pose with no motion window. PC Bridge/M1 recording/quality/replay completed:
120 `imu_motion` frames, quality gate PASS `0.94`, replay PASS, and 120
`risk_type=none` outputs.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels x_positive -NoPrompt -Analyze -SessionId timu004b-qmi8658-manual-pose1-20260623-2100 -TimeoutSeconds 35
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels y_positive -NoPrompt -Analyze -SessionId timu004b-qmi8658-manual-pose2-20260623-2108 -TimeoutSeconds 35
```

Result: passed for TIMU-004B manual additional poses. The first manually moved
window captured `x_positive` with 120 `imu_sample` records, measured dominant
axis `x positive`, mean axes about `[1043.12, -59.83, -49.36] mg`, and passed
static quality, label match, calibration offset, timing, and source-boundary
checks. The second manually moved window captured `y_positive` with 120
`imu_sample` records, measured dominant axis `y positive`, mean axes about
`[43.92, 1005.44, 7.69] mg`, and passed the same checks.

```powershell
python scripts\analyze_imu_pose_quality.py --pose z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --pose x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --pose y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --json --markdown pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.pose_quality.md --title "# TIMU-004B QMI8658 Manual Three-Pose Quality Report"
```

Result: passed for TIMU-004B manual three-pose quality. The analyzer accepted
`z_negative`, `x_positive`, and `y_positive`; `pose_static_quality`,
`pose_count`, `axis_coverage`, `pose_label_match`, `calibration_offset`,
`pose_or_motion_evidence`, and `source_boundary` all passed. `motion_sanity`
remained false because no optional motion window was supplied. Overall
`quality_gates_passed=true`, while `formal_imu_acceptance=false` with reason
`source_status_unverified`.

```powershell
python scripts\board_bridge.py --source z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --source x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --source y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --event-log pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.events.jsonl --session-id timu004b-qmi8658-manual-3pose-20260623-2108 --output-dir pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --limit 500 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --json
```

Result: passed for the TIMU-004B three-pose M1 loop. PC Bridge stored 369
events with 0 skipped lines. The recorder produced 360 `imu_motion` frames.
The quality gate passed with score `0.91`, 0 errors, and 3 warnings
(`firmware_version_unknown`, `annotations_empty`, and expected `seq_decrease`
because each bounded capture window reset device sequence). Replay passed with
360 inputs, all `risk_type=none`, and no generated safety events or base
commands.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-004B three-pose documentation sync. The repository
test suite ran 154 tests successfully, including the AMOLED pose capture helper
contract, hardware matrix updates, existing pose analyzer, PC Bridge, M1
recording, quality gate, and replay tests.

```powershell
python -m unittest quality_tests.test_amoled_pose_capture_script -v
```

Result: passed for TIMU-005 script updates. The AMOLED pose capture helper tests
ran 4 tests successfully, covering `-MotionOnly`, `-ExistingPose LABEL=PATH`,
the no-capture guard, UTF-8 no-BOM analyzer logs, and the regression guard
against PowerShell `*> $LogPath` redirection.

```powershell
$poses = @(
  'z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl',
  'x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl',
  'y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl'
)
.\scripts\capture_amoled_qmi8658_pose_set.ps1 -MotionOnly -NoPrompt -Analyze -RunM1Loop -SessionId timu005-qmi8658-motion-live-20260624-0001 -OutputDir pc_simulator\runtime\timu005 -TimeoutSeconds 35 -ExistingPose $poses
```

Result: passed for TIMU-005 live motion capture. COM9 produced
`pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`
with 123 JSONL records, including 120 `imu_sample` records, `imu_whoami`, and
`amoled_bridge_done`. The motion window stayed near `49.99 ms / 20.00 Hz` with
`missed_deadlines=0` and `max_sample_work_ms=43`.

```powershell
python scripts\analyze_imu_pose_quality.py --pose z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --pose x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --pose y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --motion pc_simulator\runtime\timu005\timu005-qmi8658-motion-live-20260624-0001-motion.jsonl --json
python scripts\analyze_imu_quality.py pc_simulator\runtime\timu005\timu005-qmi8658-motion-live-20260624-0001-motion.jsonl --json
```

Result: passed for the TIMU-005 motion gate. The pose/motion analyzer kept the
three static poses passing and reported `motion_sanity=PASS`,
`quality_gates_passed=true`, accel magnitude range about `490.04 mg`, and gyro
peak about `201921 mdps`. `formal_imu_acceptance=false` remains correct because
the source is still `bridge_uplink/unverified`. The stationary sample-quality
analyzer was used only as a timing cross-check for the motion file; timing,
QMI timestamp, completion, and source-boundary checks passed, while the
static-orientation and static-gyro gates failed by design for a moving window.

```powershell
python scripts\board_bridge.py --source z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --source x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --source y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --source motion=pc_simulator\runtime\timu005\timu005-qmi8658-motion-live-20260624-0001-motion.jsonl --event-log pc_simulator\runtime\timu005\timu005-qmi8658-motion-live-20260624-0001.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu005\timu005-qmi8658-motion-live-20260624-0001.events.jsonl --session-id timu005-qmi8658-motion-live-20260624-0001 --output-dir pc_simulator\runtime\recordings\timu005-qmi8658-motion-live-20260624-0001 --limit 600 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu005-qmi8658-motion-live-20260624-0001 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu005-qmi8658-motion-live-20260624-0001 --json
```

Result: passed for the TIMU-005 merged M1 loop. PC Bridge stored 492 events
with 0 skipped lines. The recorder produced 480 `imu_motion` frames. The
quality gate passed with score `0.91`, 0 errors, and 3 warnings
(`firmware_version_unknown`, `annotations_empty`, and expected `seq_decrease`
from independent bounded capture resets). Replay passed with 480 inputs, all
`risk_type=none`, and no generated safety events or base commands.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-005 script and documentation sync. The repository test
suite ran 155 tests successfully, including the AMOLED motion-only capture
helper contract, hardware matrix updates, existing pose/motion analyzer, PC
Bridge, M1 recording, quality gate, and replay tests.

```powershell
python -m unittest quality_tests.test_amoled_bridge_firmware quality_tests.test_amoled_pose_capture_script quality_tests.test_imu_quality -v
```

Result: passed for TIMU-006 static changes. The AMOLED bridge firmware tests,
capture-helper tests, and IMU quality analyzer tests ran 15 tests successfully.
Coverage includes configurable 600-sample firmware windows, `-M1Limit`, the
`long_window_timing` analyzer mode, and the `device_jitter` gate.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1
idf.py build
```

Result: passed for TIMU-006. ESP-IDF generated
`firmware/amoled_bridge/build/egolink_amoled_bridge.bin`; binary size was
`0x38650`.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1
idf.py -p COM9 flash
```

Result: passed for TIMU-006. esptool identified ESP32-S3 USB-Serial/JTAG,
8 MB PSRAM, MAC `02:00:00:00:00:01`, wrote the image, verified hashes, and
hard-reset the board.

```powershell
.\scripts\capture_amoled_qmi8658_pose_set.ps1 -MotionOnly -NoPrompt -RunM1Loop -SessionId timu006-qmi8658-long-window-live-20260624-0001 -OutputDir pc_simulator\runtime\timu006 -TimeoutSeconds 75 -SettleSeconds 0 -M1Limit 1000
```

Result: passed for TIMU-006 live long-window capture. COM9 produced
`pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl`
with 603 JSONL records, including 600 `imu_sample` records, `imu_whoami`, and
`amoled_bridge_done`. The completion payload reported `samples_emitted=600`,
`read_errors=0`, `not_ready_count=0`, `missed_deadlines=0`, and
`max_sample_work_ms=42`.

```powershell
python scripts\analyze_imu_quality.py pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl --long-window --min-samples 500 --max-interval-jitter-ms 10 --json --markdown pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001.long_window_quality.md --title "# TIMU-006 QMI8658 Long Window Quality Report"
```

Result: passed for the TIMU-006 long-window gate. The analyzer reported
`analysis_mode=long_window_timing`, `quality_gates_passed=true`, observed mean
interval about `49.9983 ms`, observed sample rate about `20.0007 Hz`, max
interval deviation `1.0 ms`, jitter limit `10.0 ms`, monotonic QMI timestamps,
and `source_boundary=PASS`. `formal_imu_acceptance=false` remains correct
because the source is still `bridge_uplink/unverified`.

```powershell
python scripts\board_bridge.py --source motion=pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl --event-log pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001.events.jsonl --session-id timu006-qmi8658-long-window-live-20260624-0001 --output-dir pc_simulator\runtime\recordings\timu006-qmi8658-long-window-live-20260624-0001 --limit 1000 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu006-qmi8658-long-window-live-20260624-0001 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu006-qmi8658-long-window-live-20260624-0001 --json
```

Result: passed for the TIMU-006 M1 loop. PC Bridge stored 603 events with 0
skipped lines. The recorder produced 600 `imu_motion` frames. The quality gate
passed with score `0.94`, 0 errors, and 2 warnings (`firmware_version_unknown`
and `annotations_empty`). Replay passed with 600 inputs, all `risk_type=none`,
and no generated safety events or base commands.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-006 firmware, analyzer, hardware matrix, and
documentation sync. The repository test suite ran 157 tests successfully.

```powershell
python -m unittest quality_tests.test_platform_imu_firmware -v
```

Result: passed for TIMU-007. The platform-IMU firmware tests ran 7 tests
successfully, covering the default mock backend, opt-in QMI8658 Kconfig
boundary, backend-neutral `platform_imu_sample()`, ring buffer behavior, main
payload integration, stack-buffer guard, and README caveats.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

Result: passed for TIMU-007 from `firmware/mqtt_heartbeat` with the default
mock backend. ESP-IDF generated `build\egolink_mqtt_heartbeat.bin`; the app
binary size was `0xd9170`. No flash or serial runtime validation was performed
by this command.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/qmi -D SDKCONFIG=build/qmi/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build
```

Result: passed for TIMU-007 opt-in QMI8658 compile validation. ESP-IDF
generated `build\qmi\egolink_mqtt_heartbeat.bin`; the app binary size was
`0xde340`. This was not flashed and does not validate live QMI8658 sampling.

```powershell
python -m unittest quality_tests.test_platform_imu_firmware quality_tests.test_mqtt_heartbeat_firmware quality_tests.test_hardware_sensor_matrix -v
```

Result: passed for TIMU-007 targeted verification. The platform-IMU, MQTT
heartbeat, and hardware sensor matrix tests ran 15 tests successfully.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-007 backend-boundary, documentation, and hardware
matrix sync. The repository test suite ran 158 tests successfully.

```powershell
python -m unittest quality_tests.test_platform_imu_firmware -v
```

Result: passed for TIMU-008 before hardware flash. The platform-IMU firmware
tests ran 7 tests successfully, including the QMI live profile device/topic,
AXP2101 rail bring-up symbols, and boot-capture Kconfig/window checks.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" build
```

Result: passed for the TIMU-008 QMI live profile. ESP-IDF generated
`build\timu008\egolink_mqtt_heartbeat.bin`; the app binary size was `0xde6d0`.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -B build/timu008 -D SDKCONFIG=build/timu008/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qmi8658.defaults" -p COM9 flash
```

Result: passed on ESP32-S3-Touch-AMOLED-2.06 `COM9`.

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu008\timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl --max-messages 8 --wait-seconds 45
```

Result: passed for TIMU-008 PC-side MQTT capture through the LAN broker. The
worker stored 8 messages: 4 `mqtt_status` and 4 `sensor_sample/device_health`
rows. Each sensor sample contained `imu_source=qmi8658_i2c`,
`imu_hardware_present=true`, `imu_driver_enabled=true`, and
`imu_sample_mock=false`.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu008\timu008-platform-imu-qmi-backend-live-20260624-0900.events.jsonl --session-id timu008-platform-imu-qmi-backend-live-20260624-0900 --output-dir pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --limit 50 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu008-platform-imu-qmi-backend-live-20260624-0900 --json
```

Result: passed for the TIMU-008 M1 loop. The recorder produced 8 sensor frames,
quality gate passed with score `0.94`, and replay passed with 8 inputs, all
`risk_type=none`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-008 code, documentation, and hardware matrix sync.
The repository test suite ran 158 tests successfully.

```powershell
python -m unittest quality_tests.test_imu_calibration quality_tests.test_imu_pose_quality quality_tests.test_hardware_sensor_matrix -v
```

Result: passed for TIMU-009A focused verification. The calibration, pose
quality, and hardware matrix tests ran 14 tests successfully, covering the
engineering-vs-production boundary, raw pose JSONL generation path, axis map,
conservative accel offset estimate, and evidence path tracking.

```powershell
python scripts\generate_imu_calibration_profile.py --pose z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --pose x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --pose y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --profile-id timu009a-qmi8658-engineering-20260624 --hardware-profile esp32-s3-touch-amoled-2.06-qmi8658 --output-json docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --markdown docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md
```

Result: passed for TIMU-009A profile generation. The generated profile records
`stage=engineering`, `production_ready=false`, `formal_imu_acceptance=false`,
x/y/z same-axis same-sign mapping, and accel offset estimate
`[48.0, -10.3, -24.0] mg`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-009A code, profile, documentation, and hardware
matrix sync. The repository test suite ran 162 tests successfully.

```powershell
python scripts\check_imu_acceptance.py --calibration-profile docs\hardware\TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json --report-id timu009b-qmi8658-product-acceptance-preflight-20260624 --output-json docs\hardware\TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.json --markdown docs\hardware\TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md
```

Result: passed for TIMU-009B preflight generation. The generated report keeps
`formal_imu_acceptance=false` and `motionnet_training_enabled=false`; every
product acceptance evidence gate is currently `evidence_missing`, as expected.

```powershell
python -m unittest quality_tests.test_imu_acceptance quality_tests.test_imu_calibration quality_tests.test_hardware_sensor_matrix -v
```

Result: passed for TIMU-009B focused verification. The IMU acceptance,
calibration, and hardware matrix tests ran 14 tests successfully, covering
missing evidence, hardware-observed evidence requirements, engineering-profile
blockers, and the synthetic all-evidence-pass contract.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed after TIMU-009B code, preflight report, documentation, and
hardware matrix sync. The repository test suite ran 167 tests successfully.

```powershell
idf.py --version
```

Result: passed after loading `C:\Espressif\v5.4.2\esp-idf\export.ps1`.
`idf.py` reported `ESP-IDF v5.4.2`.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build
```

Result: passed from `firmware/mqtt_heartbeat`. The ESP32-S3 firmware build
generated `build\egolink_mqtt_heartbeat.bin`; the app binary size was
`0xd89d0`, leaving `0x27630` bytes (15%) free in the smallest app partition.
No flash or serial runtime validation was performed by this command.

T039 rerun result: passed from `firmware/mqtt_heartbeat`. The ESP32-S3 firmware
build included `platform_imu`, generated `build\egolink_mqtt_heartbeat.bin`,
and reported app binary size `0xd8fe0`, leaving `0x27020` bytes (15%) free in
the smallest app partition. A later T039-live flash after the stack fix reported
app binary size `0xd8ff0`, leaving `0x27010` bytes (15%) free in the smallest
app partition.

```powershell
python scripts\egolink_board_probe.py --probe-all-sim-ports --esp-listen-seconds 12
```

Initial T039 live result: the probe wrote
`reports/board_validation/20260623-092315/probe.md` and exposed a runtime
failure before the stack fix. The ESP32 serial log showed `PLATFORM_IMU_SAMPLE`
followed by `***ERROR*** A stack overflow in task sensor_task has been
detected.` The fix moved the 1536-byte sensor JSON payload buffer to static
storage and raised `sensor_task` stack to 6144 bytes.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
```

T039-live result after the stack fix: passed. The ESP32-S3 was detected on
`COM4`, the bootloader, partition table, and `egolink_mqtt_heartbeat.bin` were
written and hash-verified, app binary size was `0xd8ff0`, and the board
hard-reset successfully.

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --max-messages 10 --wait-seconds 180 --process-safety --safety-process-limit 20
```

T039-live result: passed. The worker stored 10 live device MQTT messages:
7 `mqtt_status` frames and 3 `sensor_sample/device_health` frames. The live
`device_health` samples were `seq=13/17/21` and included RSSI, heap, mock
battery, HPWR marker fields, and explicit IMU mock metadata:
`imu_source=mock_stationary`, `imu_hardware_present=false`,
`imu_driver_enabled=false`, `imu_sample_mock=true`, ring count, and accel/gyro
mock values. Safety processing evaluated 3 samples as `risk_type=none`.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-imu-mock-live-20260623-0926-events.jsonl --session-id hdata-001-imu-mock-live-20260623-0926 --output-dir pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-imu-mock-live-20260623-0926 --json
```

T039-live recording result: passed. The clean recorder wrote 13 source events,
10 sensor frames, and 3 events. The quality gate passed with
`quality_score=0.94`, `errors=0`, and `warnings=2`; frame types were
`device_health=3` and `device_status=7`. Replay passed with 10 replayed inputs,
all `risk_type=none`, and no generated safety events or base commands.

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
```

TCAM-001 flash result: passed from `firmware/camera_smoke`. The ESP32-S3 was
detected on `COM4`, the bootloader, partition table, and
`egolink_camera_smoke.bin` were written and hash-verified, app binary size was
`0xdce40`, and the board hard-reset successfully.

```powershell
esptool.py --chip esp32s3 -p COM4 run
```

TCAM-001 UART result: passed. The log was saved to
`pc_simulator/runtime/camera-smoke-live-20260623-1842-uart.log`. The camera was
identified as OV5640, `CAMERA_SMOKE_INIT_OK` was logged, and the bounded startup
sequence captured three QVGA JPEG frames:

| Capture | Bytes | Checksum | JPEG SOI | JPEG EOI |
|---:|---:|---|---|---|
| 1 | 2893 | `a5db84d7` | `ffd8` | `ffd9` |
| 2 | 3708 | `94301dec` | `ffd8` | `ffd9` |
| 3 | 3700 | `7a151b26` | `ffd8` | `ffd9` |

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
```

Result: passed for HDATA-001. The ESP32-S3 was detected on `COM4`, the
bootloader, partition table, and `egolink_mqtt_heartbeat.bin` were written and
hash-verified, and the board hard-reset successfully.

```powershell
python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports
```

Result: passed. The report was written to
`reports/board_validation/20260623-090047/probe.md`. ESP32-S3 CH343 was visible
as `COM4`; SIM7670G AT identity was reachable on `COM6` and `COM7`; SIM was
ready; CSQ was `18,0`; LTE registration and packet attachment were true; and
RNDIS was visible.

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --max-messages 6 --wait-seconds 120 --process-safety --safety-process-limit 20
```

Result: passed. The worker stored 6 live device MQTT messages into the clean
HDATA event log: 4 `mqtt_status` frames and 2 `sensor_sample/device_health`
frames. The live `device_health` samples included RSSI, heap, mock battery
source fields, and HPWR marker fields such as `POWER_MARKER_000102` and
`POWER_MARKER_000118`. Safety processing evaluated 2 samples as
`risk_type=none` and produced no safety events or base commands.

```powershell
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2 --device-id ego-link-001 --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl
```

Result: passed. The report was written to
`reports/gnss_validation/20260623-090637/gnss_probe.md`. `COM6` and `COM7`
were AT-reachable, `gnss_power_state=1`, and the indoor query returned no GNSS
fix. The probe wrote `location_report seq=31 fix=false` into the clean HDATA
event log.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdata-001-hpwr-live-20260623-0906-events.jsonl --session-id hdata-001-hpwr-live-20260623-0906 --output-dir pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdata-001-hpwr-live-20260623-0906 --json
```

Result: passed. The clean recorder wrote 9 source events, 7 sensor frames, and
2 events. The quality gate passed with `quality_score=0.94`, `errors=0`, and
`warnings=2`. Frame types were `device_health=2`, `device_status=4`, and
`gnss_report=1`. Replay passed with 7 replayed inputs, all `risk_type=none`,
and no generated safety events or base commands.

```powershell
python -m unittest quality_tests.test_session_annotations quality_tests.test_session_inspector quality_tests.test_session_replay -v
```

Result: passed. The annotation, inspector, and replay tests ran 13 tests
successfully. Coverage includes listing annotation targets, appending by
`source_event_key` or target index, refreshing `session_manifest.json`,
`session_recording.md`, and `file_manifest.json`, preserving quality-gate file
integrity, removing the empty-annotations warning once a label exists, and
surfacing annotation summaries in replay reports.

```powershell
python scripts\annotate_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --list-targets --json
```

Result: passed. The command listed 12 annotatable targets from the real T038
recording in read-only mode. Index 4 is the current hardware
`sensor_sample/device_health seq=21548`. No real user annotation was written by
Codex during this smoke validation.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 111 tests successfully.

```powershell
python scripts\egolink_board_probe.py --probe-all-sim-ports --esp-listen-seconds 8
```

Result: passed. The report was written to
`reports/board_validation/20260622-181619/probe.md`. ESP32-S3 CH343 was visible
as `COM4`; SIM7670G AT identity was reachable on `COM6` and `COM7`; RNDIS was
visible; SIM was inserted; LTE registration and packet attachment were true;
and the ESP32 log showed `MQTT_HEARTBEAT_PUBLISH_OK`.

```powershell
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2
```

Result: passed. The report was written to
`reports/gnss_validation/20260622-181804/gnss_probe.md`. `COM6` and `COM7`
were AT-reachable, `gnss_power_state=1`, and the indoor query returned no GNSS
fix. The probe wrote a `location_report` event with `fix=false`.

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --wait-seconds 90 --process-safety --safety-process-limit 30
```

Result: passed. The worker connected to the LAN broker, not the loopback
broker, and stored 3 device MQTT messages including `mqtt_status` and real
firmware `sensor_sample/device_health seq=21548`. Safety processing wrote
`risk_type=none` evaluations and produced no real external side effects.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t038-hardware-usability-smoke --output-dir pc_simulator\runtime\recordings\t038-hardware-usability-smoke --limit 12 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
```

Result: passed. The recorder wrote 12 source events, 5 sensor frames, and 7
events. The quality gate passed with `quality_score=0.91`, `errors=0`, and
`warnings=3`. Replay passed with 12 timeline records, 6 replayed inputs, 1
`manual_sos`, 5 `none`, and 1 simulated base command.

```powershell
python -m unittest quality_tests.test_hardware_sensor_matrix -v
```

Result: passed. The updated matrix tests ran 5 tests successfully, covering
HCTX-001 scope, explicit key sensor statuses, unknown/mock boundaries,
traceable evidence paths, M1 blockers, and HARCH-001 audit targets.

Hardware package validation: passed. `PACKAGE_MANIFEST.json` matched 10 files
by SHA-256 and byte size. The procurement workbook opened as a valid `.xlsx`
container with sheets `概览`, `采购总表`, `已有物料`, `平台对比`, and `到货验收`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 108 tests successfully.

```powershell
python -m unittest quality_tests.test_session_replay -v
```

Result: passed. The session replay tests ran 4 tests successfully, covering
successful recording replay, quality-gate failure refusal, report writing, and
CLI behavior.

```powershell
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke
```

Result: passed. The replay command generated `session_replay_report.json` and
`session_replay_report.md` for the integrity-checked smoke recording. It
reported `PASS replayed_inputs=37 safety_events=9 skipped=23`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 107 tests successfully.

```powershell
python -m unittest quality_tests.test_session_recorder quality_tests.test_session_inspector -v
```

Result: passed. The recorder and inspector tests ran 9 tests successfully,
including file manifest generation, CLI output, manifest tampering, JSONL
tampering, size mismatch, and hash mismatch checks.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t035-integrity-smoke --output-dir pc_simulator\runtime\recordings\t035-integrity-smoke
```

Result: passed. The smoke recording wrote `file_manifest.json` with SHA-256
entries for `session_manifest.json`, `sensor_frames.jsonl`, `events.jsonl`,
`annotations.jsonl`, and `session_recording.md`.

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke
```

Result: passed. The quality gate returned PASS with `quality_score=0.85`,
`errors=0`, and `warnings=5`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 103 tests successfully.

```powershell
python -m unittest autodev.tests.test_supervisor quality_tests.test_local_session_summary -v
```

Result: passed. The AutoDev monitor and local session tests ran 19 tests
successfully, including quality-gate summary loading and the PowerShell session
runner contract.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
```

Result: passed. The no-start session command generated
`pc_simulator/runtime/sessions/20260621-211742/recording/session_quality_report.md`
and logged `Quality gate: PASS score=0.85 errors=0 warnings=5` without starting
broker, Dashboard, worker, modem, camera, or firmware operations.

```powershell
python scripts\autodev.py watch --once --no-clear --events 4
python scripts\autodev.py status
```

Result: passed. Both monitor views displayed the local session Quality line
with PASS, score, errors, warnings, frame/event counts, and the quality report
path.

```powershell
python -m unittest quality_tests.test_session_inspector quality_tests.test_session_recorder -v
```

Result: passed. The session inspector and recorder tests ran 8 tests
successfully, covering pass/fail quality gates, manifest count mismatches,
unverified sensor sources marked real, duplicate source keys, report writing,
CLI behavior, and the recorder source-event key format.

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t033-quality-smoke --output-dir pc_simulator\runtime\recordings\t033-quality-smoke
```

Result: passed. The smoke recording wrote 19 sensor frames, 41 key events, and
0 annotations into `pc_simulator/runtime/recordings/t033-quality-smoke/`.

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t033-quality-smoke
```

Result: passed. The quality gate returned PASS with `quality_score=0.85`,
`errors=0`, and `warnings=5`. Current warnings are expected for this M1 stage:
unknown firmware version, empty annotations, and seq resets in historical
Safety-derived event streams.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 102 tests successfully.

```powershell
python -m unittest quality_tests.test_session_recorder quality_tests.test_local_session_summary -v
```

Result: passed. The recorder and local session tests ran 6 tests successfully,
covering manifest availability flags, sensor frame extraction, key event
extraction, JSONL/annotation/summary writing, CLI output, and the PowerShell
session runner contract.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
```

Result: passed. The no-start session command created
`pc_simulator/runtime/sessions/20260621-201911/`, wrote the existing session
summary files, and generated
`pc_simulator/runtime/sessions/20260621-201911/recording/session_recording.md`.
The derived recording scanned the latest 40 event-log entries and wrote 11
sensor frames, 27 key events, and 0 annotations without starting broker,
Dashboard, worker, modem, camera, or firmware operations.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 97 tests successfully.

```powershell
python -m unittest quality_tests.test_hardware_sensor_matrix -v
```

Result: passed. The hardware sensor matrix tests ran 4 tests successfully,
covering the M1 scope, key sensor statuses, explicit unknown/mock boundaries,
and traceable evidence paths.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: passed. The repository test suite ran 94 tests successfully.

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
python -m unittest autodev.tests.test_supervisor -v
```

Result: passed. The AutoDev supervisor tests ran 15 tests successfully,
including local session summary loading, event-log fallback summary generation,
and existing monitor behavior.

```powershell
python scripts\autodev.py watch --once --no-clear --events 4
```

Result: passed. The monitor displayed the AutoDev run section and the
`LOCAL DEVICE / SAFETY SESSION` section in one snapshot.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\watch_autodev.ps1 -Once -NoClear -RecentEvents 4
```

Result: passed. The PowerShell wrapper displayed the same unified monitor
snapshot.

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

T030 did not perform new hardware I/O. It connects AutoDev monitoring to the
latest local session summary or, when no session summary exists, to a read-only
event-log fallback. The observed local session summary reported recent
`manual_sos` / `urgent_escalation` rule-baseline activity from prior simulated
and semi-real events.

T031 did not perform new hardware I/O. It consolidated existing hardware,
firmware, runtime, and report evidence into `HARDWARE_SENSOR_MATRIX.md`. The
matrix marks ESP32-S3 MQTT health samples and Wi-Fi RSSI as verified, the
SIM7670G LTE/GNSS evidence as PC-side verified, camera single-frame capture as
semi-verified, and IMU, microphone, physical SOS GPIO, SD, battery, and
ESP32-side SIM7670G control gaps as not verified, mock-only, or unknown.

T032 did not perform new hardware I/O. It added a PC-side session recorder that
derives M1 recording files from the existing `pc_simulator/runtime/events.jsonl`.
The recorder writes a manifest, structure-only sensor frames, key safety/events,
an empty annotations file, and a Markdown summary. It does not start raw audio,
camera capture, modem dialing, serial probing, firmware flashing, or any new
device process.

T033 did not perform new hardware I/O. It added a PC-side quality gate for T032
recordings and fixed recorder source-event keys to include timestamps so seq
resets across MQTT, Dashboard, and Safety-derived streams do not collide. The
quality gate only reads local recording files and writes report files.

T034 did not perform new hardware I/O. It runs the existing local session
inspector after the PC-side recorder and exposes the resulting quality summary
through the AutoDev/local monitor. It only reads and writes local runtime files.

T035 did not perform new hardware I/O. It adds a local SHA-256 file manifest for
recording artifacts and makes the inspector fail when any hashed recording file
is missing, resized, or changed.

T036 did not perform new hardware I/O. It reads integrity-checked local
recording artifacts, rebuilds replay/model-input flow on the PC, calls the
existing RuleRouter, and writes local replay reports. It does not start
hardware, network, audio, camera, modem, firmware, or external side effects.

HCTX-001 did not perform new hardware I/O. It adds and validates the hardware
context package, verifies package file hashes and the procurement workbook
container, corrects local documentation paths, and updates the sensor matrix
from existing repo evidence. It does not start hardware, network, serial, audio,
camera, modem, firmware, or external side effects.

T038 performed bounded hardware I/O. It read ESP32 serial logs, queried the
SIM7670G over PC-side USB AT ports, subscribed to the LAN MQTT broker, wrote
local PC Simulator events, and generated local recording/quality/replay
reports. It did not flash firmware, dial, send SMS, place calls, capture
camera frames, record audio, or access external business services. Current
usable hardware path: ESP32-S3 enumeration, SIM inserted, LTE
registered/attached, RNDIS visible, ESP32 MQTT status and device-health samples
received by the PC, PC-side SIM7670G GNSS no-fix report, and replayable M1
session artifacts.

HARCH-001, HARCH-002A, and HPWR-001 did not perform new hardware I/O. HARCH-001
added a read-only platform-coupling audit. HARCH-002A added a minimal firmware
`platform_power` abstraction. HPWR-001 added structured power-state events,
cumulative durations, and serial measurement marker IDs. The backend remains
log/mock-only: `battery=87` and `charging=false` are explicitly mock, GPIO
markers remain disabled, and no real battery, charger, fuel gauge, sleep mode,
current measurement, runtime claim, or SIM7670G power control was implemented.

HDATA-001 performed bounded hardware I/O. It flashed the HPWR-001
`mqtt_heartbeat` firmware to the ESP32-S3, queried SIM7670G AT ports from the
PC side, subscribed to the LAN MQTT broker, wrote a clean local event log, and
generated local recording/quality/replay reports. Current live data confirmed
ESP32 MQTT status frames, ESP32 `sensor_sample/device_health` frames, HPWR
marker fields in live payloads, and SIM7670G GNSS no-fix reports through the
PC-side AT probe. It did not capture audio, images, IMU, SD storage, true
battery telemetry, real current waveforms, calls, SMS, cloud services, or
ESP32-side SIM7670G control.

T039 performed bounded hardware I/O after the mock/ring implementation: it
flashed the firmware to ESP32-S3 `COM4`, subscribed to the LAN MQTT broker,
captured live `sensor_sample/device_health` frames, and generated local
recording/quality/replay reports. It also exposed and fixed a `sensor_task`
stack overflow in the first live attempt. The live samples prove only that
IMU-shaped mock metadata moves through the firmware and M1 PC-side pipeline;
they do not prove a real IMU is present, wired, oriented, sampled, calibrated,
interrupting, or power-managed.

TIMU-001 did not perform hardware I/O. It reviewed local hardware context,
procurement workbook entries, T039 live evidence, and the sensor matrix, then
created a real IMU bring-up evidence gate. It names `ST STEVAL-MKI227KA
（LSM6DSV16X）` and `SensorTile.box PRO` as candidate paths, while keeping them
classified as candidates rather than verified hardware.

TCAM-001 performed bounded hardware I/O. It flashed the standalone
`camera_smoke` firmware to ESP32-S3 `COM4`, reset the board, and captured UART
logs for 25 seconds. Current camera evidence confirms OV5640 detection,
camera init, and three valid QVGA JPEG frame summaries with non-zero byte
counts, distinct checksums, and `ffd8`/`ffd9` JPEG boundaries. It did not add
camera capture to `mqtt_heartbeat`, fetch HTTP `/capture`, upload images,
record images into M1 sessions, or implement privacy, retention, hash, power,
or VisionGate behavior.

HDBRIDGE-001 did not perform hardware I/O. It added a PC-only dual-board bridge
for JSONL/stdin sources, normalized `hello` and `motion_event` payloads into the
existing PC Simulator event log, generated deterministic `command_sent` route
records, and extended M1 recording with `imu_motion` frames marked
`source_availability=bridge_uplink` and `source_status=unverified`. It did not
open live USB CDC serial ports, flash the AMOLED board, probe QMI8658, record
microphone audio, drive the display/touch UI, validate board-to-board UART, or
measure dual-board power.

HDBRIDGE-002 performed bounded hardware I/O on the
ESP32-S3-Touch-AMOLED-2.06 board. It flashed `firmware/amoled_bridge` to
`COM9`, captured live USB JSONL, verified AXP2101 chip id `0x4A`, verified
QMI8658 WHOAMI `0x05`, emitted 40 short-window `imu_sample` records with
`read_errors=0`, and passed PC Bridge, session recording, quality gate, and
replay. It still marks all IMU data as `bridge_uplink/unverified` and does not
claim ODR, jitter/drop, orientation, calibration, FIFO/interrupt, microphone,
display/touch, TF/SD, board-to-board UART, or power validation.

TIMU-002 did not change firmware. It added a PC-side sample-quality analyzer
for AMOLED QMI8658 JSONL captures and applied it to the HDBRIDGE-002 capture.
The result is intentionally mixed: identity, completeness, completion,
monotonic QMI timestamp, static orientation, and static gyro gates passed, but
device timing failed because the requested `50 ms / 20 Hz` stream was observed
at about `82.31 ms / 12.15 Hz`. This confirms the QMI8658 path is real enough
to continue, but not acceptable as formal M1 IMU data yet.

TIMU-003 changed the AMOLED bridge scheduler to fixed-period
`vTaskDelayUntil`, timestamped samples at sample start, and extended the live
window to 120 samples. The ESP32-S3-Touch-AMOLED-2.06 board on `COM9` produced
120 live QMI8658 samples at about `49.99 ms / 20.00 Hz` with
`missed_deadlines=0`; PC Bridge, session recording, quality gate, and replay
all passed. This fixes the timing blocker found in TIMU-002, but the source
remains `bridge_uplink/unverified` until mounting direction, calibration,
FIFO/interrupt behavior, power behavior, and a real `platform_imu` backend are
validated in later tasks.

TIMU-004A added a PC-side pose/motion quality analyzer for QMI8658 captures and
ran a fresh live single-pose window on `COM9`. The `z_negative` static pose
passed static quality, label matching, and conservative offset checks with mean
axes about `[56.63, 22.98, -1030.48] mg`; timing remained about
`49.99 ms / 20.00 Hz`. TIMU-004 total quality remains false because no operator
moved the board into additional poses or a rotation/tap window during this run.
The task also made JSONL consumers tolerant of Windows UTF-8 BOM captures so PC
Bridge no longer skips the first `hello` line from PowerShell-generated logs.

TIMU-004B performed bounded hardware I/O on the ESP32-S3-Touch-AMOLED-2.06
board. The operator moved the board through `x_positive` and `y_positive`
poses, reusing the prior `z_negative` preflight pose. Each pose produced 120
QMI8658 samples at about 20 Hz. The three-pose analyzer passed static quality,
pose count, axis coverage, label matching, calibration offset, pose evidence,
and source-boundary gates. The merged PC Bridge/M1 path produced 360
`imu_motion` frames, passed quality gate with score `0.91`, and replayed 360
`risk_type=none` outputs. This was still not formal IMU acceptance because no
motion window, product backend, FIFO/interrupt, mounting, or power validation
had passed yet.

TIMU-005 performed bounded hardware I/O on the same AMOLED QMI8658 bridge path.
It reused the TIMU-004B three-pose evidence and captured one live
rotation/light-tap motion window on `COM9`. The motion window produced 120
`imu_sample` records at about `49.99 ms / 20.00 Hz`, passed motion sanity with
accel magnitude range about `490.04 mg` and gyro peak about `201921 mdps`, and
kept the merged pose/motion quality gate passing. The PC Bridge/M1 loop
produced 480 `imu_motion` frames, passed quality gate with score `0.91`, and
replayed 480 `risk_type=none` outputs. Formal IMU acceptance remains false:
the source is still `bridge_uplink/unverified`, and continuous-window,
product-backend, FIFO/interrupt, mounting, and power validation remain pending.

TIMU-006 performed bounded hardware I/O on the same AMOLED QMI8658 bridge path.
It changed the bridge firmware to a configurable 600-sample, 50 ms window,
built and flashed the firmware to `COM9`, then captured a stationary long
window. The capture produced 600 `imu_sample` records with `read_errors=0`,
`not_ready_count=0`, `missed_deadlines=0`, and `max_sample_work_ms=42`.
The long-window analyzer passed identity, completeness, completion, timing,
jitter, QMI timestamp, and source-boundary gates; observed mean interval was
about `49.9983 ms`, observed sample rate about `20.0007 Hz`, and max interval
deviation `1.0 ms` under a `10.0 ms` jitter limit. The PC Bridge/M1 loop
produced 600 `imu_motion` frames, passed quality gate with score `0.94`, and
replayed 600 `risk_type=none` outputs. Formal IMU acceptance remains false:
the source is still `bridge_uplink/unverified`, and real backend, product
mounting, FIFO/interrupt, and power validation remain pending.

TIMU-007 performed no new hardware I/O. It changed `platform_imu` from a
mock-only skeleton into a backend boundary: `app_main.c` now calls
`platform_imu_sample()`, the default config remains
`CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y`, and QMI8658 WHOAMI/read sample
support exists only behind `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`.
The default `mqtt_heartbeat` build passed, and an opt-in QMI8658 build also
compiled successfully without flashing. The P0 product path still reports mock
IMU metadata until a later task performs explicit real-backend live capture and
acceptance.

TIMU-008 performed bounded hardware I/O on the ESP32-S3-Touch-AMOLED-2.06
board. It built the opt-in QMI8658 `mqtt_heartbeat` profile, flashed it to
`COM9`, reset the board, captured UART logs, and subscribed to the LAN broker
at `192.168.31.250:1883`. The live evidence confirmed AXP2101 chip id `0x4a`,
QMI8658 WHOAMI `0x05`, 40 boot samples with `mock=false`, and MQTT
`sensor_sample/device_health` payloads with `imu_source=qmi8658_i2c`,
`imu_hardware_present=true`, `imu_driver_enabled=true`, and
`imu_sample_mock=false`. The PC-side M1 loop recorded 8 sensor frames, passed
quality gate with score `0.94`, and replayed 8 `risk_type=none` outputs. This
closes the real-backend live capture gap, but formal IMU acceptance remains
false because product mounting, final calibration, FIFO/DRDY interrupt,
low-power wake, and power/current waveform evidence are still pending.

TIMU-009A performed no new hardware I/O. It consumed the previously captured
TIMU-004B `z_negative`, `x_positive`, and `y_positive` QMI8658 JSONL windows
and generated an engineering calibration profile. The generated profile maps
x/y/z to same-axis same-sign for the current board orientation and estimates a
temporary accel offset of about `[48.0, -10.3, -24.0] mg`. It intentionally
sets `stage=engineering`, `production_ready=false`, and
`formal_imu_acceptance=false`; it also lists recalibration triggers for PCB,
IMU lot, mounting, enclosure, axis orientation, ODR/filter/FIFO/interrupt,
power-rail, backend/conversion, and fixture changes.

TIMU-009B performed no new hardware I/O. It consumed the TIMU-009A engineering
calibration profile and generated a product acceptance preflight report. The
report intentionally keeps `formal_imu_acceptance=false` and
`motionnet_training_enabled=false` because every product acceptance gate lacks a
hardware-observed artifact: mounting direction, fixture, final accel
calibration, signed gyro bias, temperature drift, FIFO/DRDY, power/current
waveform, backend quality gate, M1 recording/replay, and recalibration trigger
review.

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
- T030 adds a unified read-only monitor, but it does not start, stop, restart,
  or repair device-side processes. The local supervised session runner is still
  an explicitly launched CLI script rather than a Windows service.
- T031 is a documentation and quality-gate step. It does not add a recorder,
  firmware driver, data importer, or training dataset.
- IMU, microphone, physical SOS GPIO, SD mount, true battery/charging telemetry,
  and ESP32-side SIM7670G GNSS/LTE control remain unverified. M1-002 must keep
  these sources explicitly disabled or marked `not_available` until validated.
- T032 recorder is a PC event-log derived skeleton, not an ESP32 firmware
  `safety_recorder`. It does not yet provide power-loss recovery,
  sampling-rate statistics, or event-window completeness.
- T037 adds the minimal PC-side annotation CLI and report summaries, but real
  user-confirmed labels are still not present until a user or operator applies
  them to selected sessions.
- T033/T034/T035/T036/T037 now provide a PC-side quality gate, file integrity,
  replay/model-input rebuild path, and append-only annotation entry point.
  Firmware recorder behavior and a formal trainable session dataset are still
  pending.
- HCTX-001 identifies M1 data blockers but does not solve them: IMU,
  microphone, physical SOS GPIO, SD storage, true battery/charging telemetry,
  power-state instrumentation, and ESP32-side SIM7670G modem/GNSS control remain
  unverified or missing.
- T038 confirms the current board is usable for continued development, but it
  does not solve GNSS fix, SD mounting, camera integration in the current
  firmware, IMU, microphone, physical SOS GPIO, true battery telemetry, power
  instrumentation, or ESP32-side SIM7670G modem/GNSS control.
- HARCH-002A/HPWR-001 now build with ESP-IDF v5.4.2, but the power backend is
  still log/mock-only. Real battery telemetry, charger/fuel-gauge reads, sleep
  current, GPIO marker waveform alignment, runtime, and battery-life evidence
  remain pending until instrumented hardware capture is saved.
- HDATA-001 provides a clean live recording after HPWR flashing, but the
  available real sensor data is still limited to ESP32 health/status, Wi-Fi
  RSSI/heap, and PC-side SIM7670G GNSS no-fix. IMU, microphone, physical SOS
  GPIO, SD persistence, real battery telemetry, camera in the active firmware,
  and ESP32-side modem/GNSS control remain pending.
- T039 provides only a mock IMU interface, ring buffer, and live mock payload
  capture. Real IMU part selection, bus/pin confirmation, orientation, ODR,
  FIFO, interrupts, calibration, sample-rate statistics, jitter, missing-frame
  accounting, and power behavior remain pending before any MotionNet or
  fall/impact claim.
- TIMU-001 defines the real IMU evidence gate but does not fully satisfy it.
  HDBRIDGE-002 now provides a live AMOLED QMI8658 identity probe and short
  sample window. TIMU-002 measured that window and found the static orientation
  plausible, but sample timing was too slow for the requested 20 Hz stream.
  TIMU-003 fixed the sample timing and passed a 120-sample 20 Hz retest, but
  formal IMU acceptance is still false. TIMU-004A passed a single `z_negative`
  pose, TIMU-004B added three static poses, TIMU-005 added rotation/light-tap
  motion, TIMU-006 added a 600-sample long window, TIMU-007 added the
  backend boundary, TIMU-008 added real-backend live capture, TIMU-009A added
  an engineering-only calibration profile, and TIMU-009B added a product
  acceptance preflight gate ledger. Mounting direction, final production
  calibration, FIFO/interrupt behavior, and power behavior remain pending.
- TCAM-001 confirms the standalone camera smoke path, but product firmware
  camera integration remains pending. `platform_camera`, privacy authorization,
  retention/hash manifests, camera power-state control, M1 image recording, and
  VisionGate must stay unavailable until separate tasks verify them.
- HDBRIDGE-002 confirms AMOLED live USB JSONL, QMI8658 identity, and a bounded
  40-sample accel/gyro window through the PC Bridge loop. Formal IMU acceptance
  remains pending: timing/ODR, jitter/drop, mounting direction, calibration,
  FIFO/interrupt behavior, microphone, display/touch downlink, board-to-board
  UART, standalone operation, TF/SD, and dual-board power behavior all require
  later hardware tasks.
- TIMU-002 through TIMU-009B show the current IMU boundary: the bridge now emits
  real QMI8658 sample windows at about `20 Hz`, manual `z_negative`,
  `x_positive`, and `y_positive` static poses pass the pose quality gate, and a
  rotation/light-tap window passes motion sanity. TIMU-006 adds a 600-sample
  long-window timing/jitter/drop pass, and TIMU-007 adds the default-mock,
  opt-in QMI8658 `platform_imu` backend boundary. TIMU-008 validates that
  opt-in backend through UART, MQTT, M1 recording, quality gate, and replay with
  `imu_sample_mock=false`. TIMU-009A adds a repeatable engineering calibration
  profile with `production_ready=false`. TIMU-009B adds a preflight report that
  currently fails every product acceptance gate due missing hardware-observed
  artifacts. It is still not a formal product IMU source because
  FIFO/interrupt, power, final production calibration, and mounting acceptance
  remain incomplete.
- M0 rules are only a deterministic baseline and synthetic scenario check; they
  do not prove real-world fall, accident, distress, or child-safety accuracy.
- The new M1 context requires data foundations before any MotionNet, AudioGate,
  VisionGate, or learning-based ContextRouter claims. The next implementation
  step should be the hardware/sensor matrix, not model training.
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

Next, run TIMU-009C against the ESP32-S3-Touch-AMOLED-2.06 QMI8658 path: fix
the target mounting orientation, record the final calibration procedure,
validate FIFO/DRDY or interrupt behavior, and align firmware power markers with
real current waveforms. Keep MotionNet training and formal IMU claims disabled
until mounting, FIFO/interrupt, power, production calibration, and backend
quality gates pass.
