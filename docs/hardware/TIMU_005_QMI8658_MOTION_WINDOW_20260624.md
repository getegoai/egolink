# TIMU-005 QMI8658 Motion Window Report

Status: motion sanity evidence passed; formal IMU acceptance remains false.

## Scope

TIMU-005 extends the TIMU-004B manual three-pose evidence with one operator
motion window on the ESP32-S3-Touch-AMOLED-2.06 QMI8658 path.

This task does not switch to a real product `platform_imu` backend and does not
claim fall, impact, wear-state, activity, or MotionNet training readiness.

## Capture

The existing three-pose evidence set was reused:

- `z_negative`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`
- `x_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl`
- `y_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl`

The live motion window was captured with:

```powershell
$poses = @(
  'z_negative=pc_simulator\runtime\timu004b\timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl',
  'x_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl',
  'y_positive=pc_simulator\runtime\timu004b\timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl'
)
.\scripts\capture_amoled_qmi8658_pose_set.ps1 -MotionOnly -NoPrompt -Analyze -RunM1Loop -SessionId timu005-qmi8658-motion-live-20260624-0001 -OutputDir pc_simulator\runtime\timu005 -TimeoutSeconds 35 -ExistingPose $poses
```

Captured motion window:

- Path:
  `pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`
- JSONL lines: `123`
- `imu_sample` records: `120`
- `imu_whoami` seen: `true`
- `amoled_bridge_done` seen: `true`
- Skipped non-JSON boot/log lines: `4`
- Source boundary: `bridge_uplink/unverified`

Timing cross-check:

- Expected interval: `50 ms`
- Observed mean interval: `49.99 ms`
- Observed sample rate: `20.00 Hz`
- QMI timestamp monotonicity: PASS
- Completion record: `samples_emitted=120`, `read_errors=0`,
  `not_ready_count=0`, `missed_deadlines=0`, `max_sample_work_ms=43`

## Analyzer Result

The TIMU-004B three poses stayed PASS and the new motion window passed motion
sanity:

- Motion analyzer samples after warmup discard: `115`
- Accel magnitude min/max: `848.25 / 1338.28 mg`
- Accel magnitude range: `490.04 mg`
- Accel magnitude mean/stddev: `1035.36 / 82.23 mg`
- Gyro peak: `201921 mdps`
- Gyro absolute mean/stddev: `38799.60 / 40385.07 mdps`
- `motion_sanity`: PASS
- `pose_or_motion_evidence`: PASS
- `source_boundary`: PASS
- Overall pose/motion quality: PASS
- Formal IMU acceptance: `False`
- Formal acceptance reason: `source_status_unverified`

The motion window intentionally fails the static-orientation and static-gyro
checks in `scripts/analyze_imu_quality.py`; those checks are for stationary
pose windows and are not the TIMU-005 motion gate.

## M1 Loop

The capture helper ran PC Bridge, session recording, quality gate, and replay:

- PC Bridge stored events: `492`
- PC Bridge skipped lines: `0`
- Recorder sensor frames: `480`, all `imu_motion`
- Quality gate: PASS, `quality_score=0.91`, `errors=0`, `warnings=3`
- Replay: PASS
- Replayed inputs: `480`
- Replay risk types: `none=480`
- Generated safety events: `0`
- Generated base commands: `0`

The `seq_decrease` quality warning is expected for this evidence set because it
combines several bounded capture windows, each starting after an independent
bridge reset. This remains a boundary for future continuous-session validation.

## Boundary

TIMU-005 proves that the current QMI8658 bridge path can produce plausible
dynamic motion evidence in addition to static three-pose evidence. It is still
not product IMU acceptance. Remaining gates include:

- real `platform_imu` backend integration
- continuous long-window ODR/jitter/drop validation
- mounting direction and product coordinate convention
- FIFO/interrupt behavior
- power-state and current-waveform validation
- source promotion away from `bridge_uplink/unverified`
