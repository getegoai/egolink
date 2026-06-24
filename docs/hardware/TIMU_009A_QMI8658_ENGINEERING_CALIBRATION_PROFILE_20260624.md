# TIMU-009A IMU Engineering Calibration Profile

- Profile id: `timu009a-qmi8658-engineering-20260624`
- Stage: `engineering`
- Hardware profile: `esp32-s3-touch-amoled-2.06-qmi8658`
- Source report: `z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl;x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl;y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl`
- Usable for engineering: `True`
- Production ready: `False`
- Formal IMU acceptance: `False`
- Estimated accel offset mg xyz: `[48.0, -10.3, -24.0]`
- Gyro calibration: `not_estimated_requires_signed_static_gyro_capture`

## Axis Map

| Expected axis | Measured axis | Sign | Pose source |
|---|---|---:|---|
| `x` | `x` | `1` | `x_positive` |
| `y` | `y` | `1` | `y_positive` |
| `z` | `z` | `1` | `z_negative` |

## Static Pose Quality

| Pose | Samples | Mean axes mg | Static | Label | Offset |
|---|---:|---|---:|---:|---:|
| `z_negative` | 115 | [56.9, 23.4, -1030.2] | `True` | `True` | `True` |
| `x_positive` | 115 | [1043.1, -59.8, -49.4] | `True` | `True` | `True` |
| `y_positive` | 115 | [43.9, 1005.4, 7.7] | `True` | `True` | `True` |

## Recalibration Triggers

- `pcb_revision_change`
- `imu_part_or_lot_change`
- `imu_mounting_position_change`
- `enclosure_or_wearable_mechanics_change`
- `adhesive_or_fastener_change`
- `axis_orientation_change`
- `odr_filter_fifo_or_interrupt_policy_change`
- `power_rail_or_regulator_change`
- `firmware_backend_or_conversion_change`
- `production_fixture_change`

## Production Blockers

- `final_mounting_direction_not_frozen`
- `production_fixture_not_defined`
- `six_face_or_equivalent_accel_calibration_not_complete`
- `signed_gyro_bias_capture_not_complete`
- `temperature_drift_not_characterized`
- `fifo_drdy_interrupt_not_validated`
- `power_current_waveform_not_validated`

## Boundary

This profile captures an engineering calibration estimate. It must be regenerated after hardware, mounting, enclosure, firmware sampling, FIFO/interrupt, or power-path changes.

This profile is for engineering bring-up only. It must be regenerated
after the hardware and mechanical stack are frozen, and it is not valid
as production calibration or model-training evidence.
