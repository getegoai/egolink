# TIMU-009C-B1 QMI8658 Temporary Fixture Preflight

- Report id: `timu009c-b1-qmi8658-temporary-fixture-preflight-20260624`
- Calibration profile id: `timu009a-qmi8658-engineering-20260624`
- Hardware profile: `esp32-s3-touch-amoled-2.06-qmi8658`
- Calibration profile stage: `engineering`
- Calibration profile production ready: `False`
- Calibration profile formal IMU acceptance: `False`
- All evidence gates passed: `False`
- Formal IMU acceptance: `False`
- MotionNet training enabled: `False`

## Gate Results

| Gate | Status | Passed | Hardware observed | Artifact | Reason |
|---|---|---:|---:|---|---|
| `product_mounting_direction_frozen` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |
| `production_fixture_defined` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |
| `six_face_or_equivalent_accel_calibration_complete` | `pending` | `False` | `False` | `missing` | `status_pending` |
| `signed_static_gyro_bias_complete` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |
| `temperature_drift_characterized` | `pending` | `False` | `False` | `missing` | `status_pending` |
| `fifo_drdy_interrupt_validated` | `pending` | `False` | `False` | `missing` | `status_pending` |
| `power_current_waveform_validated` | `pending` | `False` | `False` | `missing` | `status_pending` |
| `backend_quality_gate_passed` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |
| `m1_recording_replay_passed` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |
| `recalibration_triggers_reviewed` | `partial` | `False` | `True` | `docs/hardware/TIMU_009C_B1_QMI8658_TEMPORARY_FIXTURE_STATIC_CAPTURE_20260624.md` | `status_partial` |

## Profile Blockers

- `calibration_profile_not_production_stage`
- `calibration_profile_production_ready_false`
- `calibration_profile_formal_imu_acceptance_false`

## Failed Gates

- `product_mounting_direction_frozen`
- `production_fixture_defined`
- `six_face_or_equivalent_accel_calibration_complete`
- `signed_static_gyro_bias_complete`
- `temperature_drift_characterized`
- `fifo_drdy_interrupt_validated`
- `power_current_waveform_validated`
- `backend_quality_gate_passed`
- `m1_recording_replay_passed`
- `recalibration_triggers_reviewed`

## Next Actions

- Freeze the IMU board orientation in the target enclosure or wearable fixture.
- Define the production or lab fixture used for repeatable IMU calibration.
- Capture the final accel calibration after the mechanical stack is frozen.
- Capture signed static gyro bias with the final mounting orientation.
- Characterize accel/gyro drift across the expected operating temperature range.
- Validate the selected FIFO or DRDY interrupt path on hardware.
- Align firmware power markers with PPK2/Otii or equivalent current waveforms.
- Repeat backend live capture, quality gate, and replay with the final configuration.
- Record and replay an M1 session using the accepted IMU backend evidence.
- Review hardware, mounting, firmware, power, and fixture changes against recalibration triggers.
- calibration_profile_not_production_stage
- calibration_profile_production_ready_false
- calibration_profile_formal_imu_acceptance_false

## Boundary

This preflight report is a gate ledger. It does not create hardware evidence; each pass requires a hardware-observed artifact for the final mechanical and firmware configuration.
