# CURRENT_TASK: TIMU-009A / IMU Engineering Calibration Boundary

## Goal

Create a repeatable engineering calibration artifact for the current AMOLED
QMI8658 path while explicitly preventing it from being treated as production
calibration or formal IMU acceptance.

## Scope

- Reuse existing TIMU-004B three-pose QMI8658 captures.
- Generate an engineering calibration profile with axis mapping and conservative
  accel offset estimates.
- Mark the profile as `stage=engineering`, `production_ready=false`, and
  `formal_imu_acceptance=false`.
- List hardware and firmware changes that require recalibration.
- Keep MotionNet training, production calibration, final mounting, FIFO/DRDY,
  low-power wake, and current-waveform validation out of scope.

## Result

- Added `pc_simulator/imu_calibration.py`.
- Added `scripts/generate_imu_calibration_profile.py`.
- Added `quality_tests/test_imu_calibration.py`.
- Generated:
  - `docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json`
  - `docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md`
- Current engineering estimate:
  - axis map: x/y/z measured axes match expected axes
  - accel offset estimate xyz: approximately `[48.0, -10.3, -24.0] mg`
  - gyro signed bias: not estimated
  - production ready: false

## Done When

- [x] Engineering calibration profile can be generated from existing pose
  quality JSON or raw pose JSONL sources.
- [x] Profile records axis mapping and conservative accel offset estimate.
- [x] Profile explicitly says `production_ready=false`.
- [x] Profile lists recalibration triggers after hardware, mounting, enclosure,
  ODR/FIFO/interrupt, power rail, backend, or fixture changes.
- [x] Tests cover engineering-vs-production boundary.
- [x] Status, matrix, and integration report are updated.

Formal IMU acceptance remains false. A production calibration must be redone
after the hardware and mechanical stack are frozen.
