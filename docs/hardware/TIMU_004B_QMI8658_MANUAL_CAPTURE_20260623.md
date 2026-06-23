# TIMU-004B QMI8658 Manual Pose/Motion Capture Report

Status: capture flow ready and single-pose live preflight passed; multi-pose or
motion evidence is still incomplete.

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

The capture tooling is now live-tested. The single-pose preflight confirms that
the helper can capture QMI8658 JSONL, run the pose analyzer, and complete the M1
recording/quality/replay loop. It does not complete TIMU-004 multi-pose or
motion evidence, because the board was not manually moved through additional
poses during this non-interactive preflight.
