# CURRENT_TASK: TIMU-009B / IMU Product Acceptance Preflight Gate

## Goal

Create a repeatable preflight gate for product IMU acceptance so the project can
track final mounting, production calibration, FIFO/DRDY, backend quality, M1
replay, and power waveform evidence without accidentally treating engineering
calibration as formal acceptance.

## Scope

- Consume the TIMU-009A engineering calibration profile.
- Define required evidence gates for formal IMU acceptance.
- Require hardware-observed artifacts for each acceptance gate.
- Generate a TIMU-009B preflight report that is expected to fail today.
- Keep firmware FIFO/DRDY implementation, product mechanical mounting,
  production calibration capture, PPK2/Otii measurement, and MotionNet training
  out of scope for this run.

## Result

- Added `pc_simulator/imu_acceptance.py`.
- Added `scripts/check_imu_acceptance.py`.
- Added `quality_tests/test_imu_acceptance.py`.
- Generated:
  - `docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.json`
  - `docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md`
- Current preflight result:
  - `formal_imu_acceptance=false`
  - `motionnet_training_enabled=false`
  - all acceptance evidence gates are missing
  - current calibration profile is still `stage=engineering`

## Required Evidence Gates

- Product mounting direction frozen.
- Production or lab calibration fixture defined.
- Six-face or equivalent final accel calibration complete.
- Signed static gyro bias complete.
- Temperature drift characterized.
- FIFO/DRDY interrupt validated.
- Power/current waveform validated with an instrument.
- Backend live capture quality gate passed on final configuration.
- M1 recording and replay passed with accepted backend evidence.
- Recalibration triggers reviewed.

## Done When

- [x] Preflight report can be generated from an IMU calibration profile.
- [x] Missing hardware evidence keeps every acceptance gate failed.
- [x] Engineering calibration profile blocks formal acceptance.
- [x] Synthetic tests cover the future all-evidence-pass path.
- [x] MotionNet training remains disabled in the report.
- [x] Status, matrix, and integration report are updated.

Formal IMU acceptance remains false. The next hardware step needs final mounting
orientation, real calibration evidence, FIFO/DRDY validation, and current
waveform capture.
