# TIMU-004B QMI8658 Manual Pose/Motion Capture Report

Status: manual three-pose evidence passed; formal IMU acceptance remains false.

## Scope

TIMU-004B continues the ESP32-S3-Touch-AMOLED-2.06 QMI8658 path from
TIMU-004A. The goal is to make multi-pose or motion capture repeatable without
promoting the IMU source to product-ready status.

This task adds a bounded local capture helper:

- `scripts/capture_amoled_qmi8658_pose_set.ps1`
- Default port: `COM9`
- Default pose windows: `z_negative`, `x_positive`, `y_positive`
- Optional motion window: `-CaptureMotion`
- Optional analyzer: `-Analyze`
- Optional PC Bridge/M1 loop: `-RunM1Loop`

The helper writes finite JSONL windows, filters non-JSON boot logs, waits for
`amoled_bridge_done`, stores UTF-8 without BOM, and can run the existing pose
analyzer plus PC Bridge, session recorder, quality gate, and replay commands.
By default, analysis markdown is written beside the session runtime files; pass
`-MarkdownReport docs\hardware\TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md`
only when intentionally refreshing this report.

## Operator Protocol

1. Confirm `firmware/amoled_bridge` is already flashed on the AMOLED board.
2. Keep the board connected as the ESP32-S3 native USB serial device, currently
   observed as `COM9`.
3. Run the default multi-pose capture:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -Analyze -RunM1Loop
```

4. For each prompt, physically place the board in the requested pose and keep it
   still until the capture completes.
5. For a motion sanity window, add `-CaptureMotion` and rotate or lightly tap the
   board during the motion prompt:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -CaptureMotion -Analyze -RunM1Loop
```

6. For a non-interactive single-pose preflight:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative -NoPrompt -Analyze -RunM1Loop
```

## Live Preflight

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative -NoPrompt -Analyze -RunM1Loop -SessionId timu004b-qmi8658-preflight-live-20260623-205520 -TimeoutSeconds 35
```

Result:

- Capture path:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`
- JSONL lines: `123`
- `imu_sample` records: `120`
- `imu_whoami` seen: `true`
- `amoled_bridge_done` seen: `true`
- Skipped non-JSON boot/log lines: `0`
- Source boundary: `bridge_uplink/unverified`

Pose analyzer result:

- Pose windows: `1`
- Static pose: `z_negative`
- Analyzer sample count after warmup discard: `115`
- Measured dominant axis: `z negative`
- Mean axes: `[56.93, 23.39, -1030.24] mg`
- Mean accel magnitude: `1032.08 mg`
- Gyro absolute mean: `531.90 mdps`
- Conservative calibration offset: `[56.93, 23.39, -30.24] mg`
- Static quality: PASS
- Pose label match: PASS
- Calibration offset: PASS
- Source boundary: PASS
- Overall pose/motion quality: FAIL by design, because only one static pose was
  captured and no motion window was supplied.

M1 loop result:

- Event log:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520.events.jsonl`
- Recording:
  `pc_simulator/runtime/recordings/timu004b-qmi8658-preflight-live-20260623-205520/`
- Session quality gate: PASS, `quality_score=0.94`, `errors=0`, `warnings=2`
- Sensor frames: `120`, all `imu_motion`
- Replay: PASS, `replayed_inputs=120`
- Replay risk types: `none=120`
- Generated safety events: `0`
- Generated base commands: `0`

## Manual Three-Pose Capture

After the preflight, the operator manually moved the AMOLED board through two
additional stable orientations. The three-pose evidence set is:

- `z_negative`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`
- `x_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl`
- `y_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl`

Timing cross-checks for each pose window passed at about `20.00 Hz`, with 120
`imu_sample` records per window and `missed_deadlines=0`.

Pose analyzer command:

```powershell
python scripts\analyze_imu_pose_quality.py --pose z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --pose x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --pose y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --json --markdown pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.pose_quality.md --title "# TIMU-004B QMI8658 Manual Three-Pose Quality Report"
```

Pose analyzer result:

| Pose | Measured Dominant Axis | Samples After Warmup | Mean Axes mg | Mean Magnitude mg | Calibration Offset mg | Result |
|---|---|---:|---|---:|---|---:|
| `z_negative` | `z negative` | 115 | `[56.93, 23.39, -1030.24]` | 1032.08 | `[56.93, 23.39, -30.24]` | PASS |
| `x_positive` | `x positive` | 115 | `[1043.12, -59.83, -49.36]` | 1046.01 | `[43.12, -59.83, -49.36]` | PASS |
| `y_positive` | `y positive` | 115 | `[43.92, 1005.44, 7.69]` | 1006.44 | `[43.92, 5.44, 7.69]` | PASS |

Quality gates:

- `pose_static_quality`: PASS
- `pose_count`: PASS
- `axis_coverage`: PASS
- `pose_label_match`: PASS
- `calibration_offset`: PASS
- `pose_or_motion_evidence`: PASS
- `source_boundary`: PASS
- `motion_sanity`: FAIL only because no optional motion window was supplied.
- Overall pose/motion quality: PASS
- Formal IMU acceptance: `False`
- Formal acceptance reason: `source_status_unverified`

M1 loop:

```powershell
python scripts\board_bridge.py --source z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl --source x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl --source y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl --event-log pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.events.jsonl --json
python scripts\session_recorder.py --event-log pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-3pose-20260623-2108.events.jsonl --session-id timu004b-qmi8658-manual-3pose-20260623-2108 --output-dir pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --limit 500 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\timu004b-qmi8658-manual-3pose-20260623-2108 --json
```

M1 result:

- PC Bridge stored events: `369`
- PC Bridge skipped lines: `0`
- Recorder source events: `369`
- Recorder sensor frames: `360`, all `imu_motion`
- Quality gate: PASS, `quality_score=0.91`, `errors=0`, `warnings=3`
- Replay: PASS
- Replayed inputs: `360`
- Replay risk types: `none=360`
- Generated safety events: `0`
- Generated base commands: `0`

The quality gate warning `seq_decrease` is expected for this manual evidence set
because the three bounded capture windows were independent bridge resets, so
device `seq` restarted in each window. This is acceptable for the TIMU-004B pose
evidence gate but remains a boundary to solve before long continuous IMU
sessions.

## Acceptance Boundary

TIMU-004 total pose/motion quality can pass only when the analyzer sees either:

- at least three static pose windows with distinct axis/sign labels, or
- a supplied motion window that passes motion sanity.

Even if the TIMU-004 pose/motion quality gate passes, formal IMU acceptance
remains false until separate tasks verify mounting direction, calibration,
FIFO/interrupt behavior, power behavior, and a real `platform_imu` backend.

The source must remain:

- `source_availability=bridge_uplink`
- `source_status=unverified`

## Current Result

The capture tooling is now live-tested, and the manual three-pose evidence gate
passes for `z_negative`, `x_positive`, and `y_positive`. This is enough to close
the TIMU-004B pose/motion evidence gate, but it is not product IMU acceptance:
source status remains `bridge_uplink/unverified`, no optional motion window was
supplied, and mounting, FIFO/interrupt, power, and real `platform_imu` backend
validation still require separate tasks.
