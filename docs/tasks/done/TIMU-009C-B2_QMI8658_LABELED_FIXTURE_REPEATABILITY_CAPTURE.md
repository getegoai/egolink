# CURRENT_TASK: TIMU-009C-B2 / QMI8658 Labeled Fixture Repeatability Capture

## Goal

Capture a second hardware-observed IMU static window after the operator added
visible `TOP`, `OUT`, and `USB/CABLE` labels to the paper-box temporary fixture,
then compare it with TIMU-009C-B1 without weakening the formal acceptance gates.

## Scope

- Use the existing ESP32-S3-Touch-AMOLED-2.06 `firmware/mqtt_heartbeat`
  QMI8658 backend profile already running on the board.
- Capture bounded MQTT status/event traffic through the LAN broker.
- Summarize static accel/gyro stability for the labeled paper-box fixture.
- Compare the labeled fixture window against TIMU-009C-B1.
- Generate an evidence manifest and preflight report using the existing
  TIMU-009B/TIMU-009C gate semantics.
- Derive an M1 recording, run quality inspection, and replay the recording.
- Update status, matrix, integration, and current-task documentation.

Out of scope: final product enclosure acceptance, six-face or equivalent final
calibration, FIFO/DRDY interrupt validation, current waveform measurement,
low-power wake, microphone/TF/touch validation, MotionNet training, and formal
IMU product acceptance.

## Result

- User added `TOP`, `OUT`, and `USB/CABLE` labels to the paper-box temporary
  fixture.
- Captured `20` MQTT events from `ego-link-amoled-qmi8658`:
  - `10` QMI8658 `sensor_sample/device_health` events.
  - `10` `mqtt_status` events.
  - Sequence range `11976..11995`.
  - `imu_source=qmi8658_i2c`.
  - `imu_sample_mock=false`.
- Static accel magnitude stayed stable:
  - mean `1025.88 mg`;
  - min `1024.50 mg`;
  - max `1026.53 mg`;
  - span `2.03 mg`.
- Main gravity direction remained negative Z:
  - accel mean `[48.60, 94.10, -1020.40] mg`.
- Repeatability against B1:
  - accel magnitude mean delta `0.90 mg`;
  - Z mean delta `0.10 mg`;
  - gravity axis stayed negative Z;
  - X mean shifted `23.22 mg`, acceptable for temporary taped fixture evidence
    but not a production calibration result.
- M1 closure passed:
  - recording produced `20` sensor frames;
  - quality gate PASS, `quality_score=0.94`, `errors=0`, `warnings=2`;
  - replay PASS, `20` outputs all `risk_type=none`.
- Generated:
  - `docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE_20260624.md`
  - `docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_EVIDENCE_20260624.json`
  - `docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_PREFLIGHT_20260624.json`
  - `docs/hardware/TIMU_009C_B2_QMI8658_LABELED_FIXTURE_PREFLIGHT_20260624.md`

## Boundary

- This is hardware-observed partial evidence for a labeled repeatable temporary
  fixture.
- It is not final product mounting evidence because the target enclosure and
  wearable orientation are not frozen.
- The preflight remains expected FAIL:
  - partial gates do not pass formal acceptance;
  - six-face/equivalent accel calibration is pending;
  - signed production gyro bias is pending;
  - temperature drift is pending;
  - FIFO/DRDY is pending;
  - power current waveform is pending;
  - TIMU-009A calibration profile is still `stage=engineering`.
- `formal_imu_acceptance=false`.
- `motionnet_training_enabled=false`.

## Done When

- [x] Bounded live MQTT data captured from the labeled QMI8658 fixture.
- [x] Static accel/gyro summary written.
- [x] B1/B2 repeatability comparison recorded.
- [x] Evidence manifest records labeled fixture gates as partial or pending.
- [x] Preflight report preserves formal acceptance failure.
- [x] M1 recording, quality gate, and replay pass for the labeled fixture data.
- [x] Status, matrix, integration report, and task record are updated.

Next hardware step: keep the labeled fixture intact. A useful follow-up is
TIMU-009C-B3, a bounded equivalent-calibration pose set using the `TOP`, `OUT`,
and `USB/CABLE` labels, or FIFO/DRDY validation if the interrupt path is wired.
