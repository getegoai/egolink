# TIMU-009C-B2 QMI8658 Labeled Fixture Repeatability Capture

Date: 2026-06-24

## Purpose

TIMU-009C-B2 records the first repeatability capture after the operator added
visible orientation labels to the paper-box temporary fixture used in
TIMU-009C-B1. The requested labels were `TOP`, `OUT`, and `USB/CABLE`.

This is repeatable temporary fixture evidence. It is not final product mounting
acceptance because the target wearable enclosure and final production fixture
are still not frozen.

Formal IMU acceptance remains false. MotionNet training remains disabled.

## Operator Fixture Note

- Operator report: orientation labels were added after TIMU-009C-B1.
- Label set: `TOP`, `OUT`, `USB/CABLE`.
- Fixture status: labeled paper-box temporary fixture.
- Capture instruction: keep the labeled paper box and USB cable still during
  the MQTT capture window.
- Evidence classification: hardware-observed partial repeatability evidence.

## Command

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/ego-link-amoled-qmi8658/status --topic ego/link/ego-link-amoled-qmi8658/event --event-log pc_simulator\runtime\timu009c_b2\timu009c-b2-labeled-temporary-fixture-static-20260624-1805.events.jsonl --max-messages 20 --wait-seconds 120
```

Result: PASS, stored 20 MQTT events.

## Raw Evidence

- Event log:
  `pc_simulator/runtime/timu009c_b2/timu009c-b2-labeled-temporary-fixture-static-20260624-1805.events.jsonl`
- Summary:
  `pc_simulator/runtime/timu009c_b2/timu009c-b2-labeled-temporary-fixture-static-20260624-1805.summary.json`
- M1 recording:
  `pc_simulator/runtime/recordings/timu009c-b2-labeled-temporary-fixture-static-20260624-1805/`
- Prior comparison:
  `pc_simulator/runtime/timu009c_b1/timu009c-b1-temporary-fixture-static-20260624-1735.summary.json`

## Capture Summary

- Total MQTT events: 20.
- QMI8658 `sensor_sample/device_health` events: 10.
- `mqtt_status` events: 10.
- Sequence range: `11976..11995`.
- Device id: `ego-link-amoled-qmi8658`.
- IMU source: `qmi8658_i2c`.
- IMU mock flag: `imu_sample_mock=false`.

Static accel/gyro summary:

| Axis | Accel mean mg | Accel min mg | Accel max mg | Accel span mg | Gyro mean mdps | Gyro min mdps | Gyro max mdps | Gyro span mdps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| x | 48.60 | 48 | 49 | 1 | -359.00 | -453 | -296 | 157 |
| y | 94.10 | 93 | 95 | 2 | 1865.20 | 1796 | 1968 | 172 |
| z | -1020.40 | -1021 | -1019 | 2 | -165.40 | -312 | 171 | 483 |

Accel magnitude:

- Mean: `1025.88 mg`.
- Min: `1024.50 mg`.
- Max: `1026.53 mg`.
- Span: `2.03 mg`.

B1 repeatability comparison:

| Metric | B1 | B2 | Delta |
|---|---:|---:|---:|
| Accel mean x mg | 25.38 | 48.60 | 23.22 |
| Accel mean y mg | 92.25 | 94.10 | 1.85 |
| Accel mean z mg | -1020.50 | -1020.40 | 0.10 |
| Accel magnitude mean mg | 1024.98 | 1025.88 | 0.90 |

The gravity-dominant axis stayed negative Z across B1 and B2. The small
accel-magnitude delta and stable Z axis support repeatability for this labeled
temporary fixture. The X mean shifted by about `23.22 mg`, which is acceptable
for a taped paper-box fixture but should not be treated as a production
calibration result.

Example samples:

| seq | accel mg x | accel mg y | accel mg z | gyro mdps x | gyro mdps y | gyro mdps z | dropped samples |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 11976 | 49 | 94 | -1021 | -453 | 1796 | -156 | 5996 |
| 11994 | 48 | 94 | -1021 | -406 | 1968 | -93 | 6005 |

## M1 Closure

Recording command:

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu009c_b2\timu009c-b2-labeled-temporary-fixture-static-20260624-1805.events.jsonl --session-id timu009c-b2-labeled-temporary-fixture-static-20260624-1805 --output-dir pc_simulator\runtime\recordings\timu009c-b2-labeled-temporary-fixture-static-20260624-1805 --limit 60 --json
```

Result:

- `source_events=20`.
- `sensor_frames=20`.
- `events=0`.
- `annotations=0`.

Quality gate:

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu009c-b2-labeled-temporary-fixture-static-20260624-1805 --json
```

Result: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.

Replay:

```powershell
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu009c-b2-labeled-temporary-fixture-static-20260624-1805 --json
```

Result: PASS, 20 replayed inputs, 20 `risk_type=none` outputs, 0 safety events,
0 base commands.

## Product Acceptance Boundary

This report may be referenced as partial evidence for:

- labeled temporary fixture orientation;
- repeatability of the temporary fixture static direction;
- backend static capture quality;
- M1 recording/replay closure for the labeled temporary fixture.

It must not be used as pass evidence for final IMU acceptance because the
mechanical stack is not final and the calibration profile is still engineering
stage.

Next hardware step: keep the labeled fixture intact. The next useful IMU step is
either a bounded equivalent-calibration pose set using the same labels or a
FIFO/DRDY interrupt validation task once the selected signal path is wired.
