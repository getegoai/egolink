# CURRENT_TASK: TIMU-009C-B0 / IMU Product Mounting Evidence Template

## Goal

Create a repeatable evidence manifest template for TIMU-009C product mounting
and final IMU acceptance work, so the next hardware run can fill concrete
artifacts without weakening the existing TIMU-009B gate semantics.

## Scope

- Extend `pc_simulator/imu_acceptance.py` to generate an operator evidence
  manifest template.
- Keep all gates defaulted to `pending`, `artifact=null`, and
  `observed_on_hardware=false`.
- Document the required artifact shape for mounting, fixture, calibration,
  gyro bias, temperature drift, FIFO/DRDY, power waveform, backend quality,
  M1 replay, and recalibration review.
- Generate TIMU-009C-B0 `.json` and `.md` template artifacts.
- Update status, matrix, and integration documentation.
- Keep physical mounting, new hardware capture, FIFO/DRDY implementation,
  PPK2/Otii measurement, and MotionNet training out of scope for this run.

## Result

- Added evidence template helpers to `pc_simulator/imu_acceptance.py`.
- Added tests in `quality_tests/test_imu_acceptance.py`.
- Generated:
  - `docs/hardware/TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.json`
  - `docs/hardware/TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.md`
- Current template result:
  - `formal_imu_acceptance=false`
  - `motionnet_training_enabled=false`
  - all evidence gates remain `pending`
  - all gates require hardware-observed artifacts before they can pass

## Boundary

- This task creates the checklist and manifest shape only.
- It does not validate product mounting, final calibration, FIFO/DRDY,
  low-power wake, current waveform, or MotionNet data readiness.
- TIMU-009C-A remains the latest real QMI backend data capture.

## Done When

- [x] Evidence template includes every TIMU-009B required gate.
- [x] Template gates default to pending and not hardware-observed.
- [x] CLI writes JSON and Markdown template artifacts.
- [x] Focused tests cover template generation.
- [x] Status, matrix, and integration report are updated.

Formal IMU acceptance remains false. The next hardware step needs the operator
to place the AMOLED QMI8658 board in the intended product orientation or a
repeatable fixture so final mounting/calibration evidence can be captured.
