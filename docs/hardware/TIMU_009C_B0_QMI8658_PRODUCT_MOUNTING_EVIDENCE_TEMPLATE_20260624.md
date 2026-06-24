# TIMU-009C-B0 IMU Product Mounting Evidence Template

- Manifest id: `timu009c-b0-qmi8658-product-mounting-evidence-template-20260624`
- Hardware profile: `esp32-s3-touch-amoled-2.06-qmi8658`
- Calibration profile id: `timu009a-qmi8658-engineering-20260624`
- Target mounting direction: `pending-final-wearable-orientation`
- Formal IMU acceptance: `False`
- MotionNet training enabled: `False`

## Operator Rule

This is an operator evidence template. It does not validate hardware by itself; it becomes acceptance evidence only after each gate points to hardware-observed artifacts.

Do not set a gate to `pass` until the artifact is a durable report or file from the final hardware configuration and `observed_on_hardware` is `true`.

## Evidence Gates

| Gate | Status | Hardware observed | Expected artifact | Operator action |
|---|---|---:|---|---|
| `product_mounting_direction_frozen` | `pending` | `False` | Mounting-direction note with board/enclosure photos or fixture drawing, axis convention, and operator confirmation. | Freeze the IMU board orientation in the target enclosure or wearable fixture. |
| `production_fixture_defined` | `pending` | `False` | Fixture description with repeatable board placement, orientation marks, and calibration operator steps. | Define the production or lab fixture used for repeatable IMU calibration. |
| `six_face_or_equivalent_accel_calibration_complete` | `pending` | `False` | Final six-face or equivalent accel calibration JSON/Markdown generated after the mounting stack is frozen. | Capture the final accel calibration after the mechanical stack is frozen. |
| `signed_static_gyro_bias_complete` | `pending` | `False` | Static gyro bias capture from the final mounting orientation, with signed x/y/z bias values and capture duration. | Capture signed static gyro bias with the final mounting orientation. |
| `temperature_drift_characterized` | `pending` | `False` | Temperature sweep or bounded engineering drift note covering the expected operating range and recalibration limits. | Characterize accel/gyro drift across the expected operating temperature range. |
| `fifo_drdy_interrupt_validated` | `pending` | `False` | Hardware log/report proving the selected FIFO or DRDY interrupt path fires and is consumed by firmware. | Validate the selected FIFO or DRDY interrupt path on hardware. |
| `power_current_waveform_validated` | `pending` | `False` | PPK2/Otii or equivalent current waveform aligned to firmware POWER_MARKER records. | Align firmware power markers with PPK2/Otii or equivalent current waveforms. |
| `backend_quality_gate_passed` | `pending` | `False` | Final backend live capture, quality report, and source-boundary report from the accepted configuration. | Repeat backend live capture, quality gate, and replay with the final configuration. |
| `m1_recording_replay_passed` | `pending` | `False` | M1 recording directory plus quality and replay reports generated from accepted backend evidence. | Record and replay an M1 session using the accepted IMU backend evidence. |
| `recalibration_triggers_reviewed` | `pending` | `False` | Review note covering PCB, IMU lot, mounting, enclosure, ODR/filter/FIFO, power rail, firmware conversion, and fixture changes. | Review hardware, mounting, firmware, power, and fixture changes against recalibration triggers. |

## Reference Artifacts

- `docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md`

## Next Hardware Step

Fix the QMI8658 board in the target wearable orientation or a repeatable temporary fixture, then capture the final mounting/static calibration evidence before promoting any gate to `pass`.
