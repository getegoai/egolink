# TIMU-004 QMI8658 Pose Quality Report

- Pose `z_negative`: `pc_simulator\runtime\timu004-qmi8658-single-pose-live-20260623-203238.jsonl`
- Pose windows: `1`
- Quality gates passed: `False`
- Formal IMU acceptance: `False`
- Formal acceptance reasons: `source_status_unverified, multi_pose_or_motion_evidence_missing, multi_pose_coverage_incomplete, axis_sign_coverage_incomplete, motion_window_missing, quality_gates_not_all_passed`

## Pose Windows

| Pose | Expected | Measured | Samples | Mean | Gyro abs mean | Calibration offset mg | Result |
|---|---|---|---:|---:|---:|---|---:|
| `z_negative` | `z` `negative` | `z` `negative` | 115 | 1032.3 | 489.5 | `[56.6, 23.0, -30.5]` | PASS |

## Motion Window

- Motion source: not supplied
- Motion sanity: `False`

## Gates

| Gate | Result | Meaning |
|---|---:|---|
| `pose_static_quality` | PASS | each supplied static pose is stable and plausibly near 1g |
| `pose_count` | FAIL | at least the requested number of static pose windows passed |
| `axis_coverage` | FAIL | static pose labels cover enough distinct axis/sign orientations |
| `pose_label_match` | PASS | dominant measured axis/sign matches each pose label |
| `calibration_offset` | PASS | pose mean vectors stay within conservative offset bounds |
| `motion_sanity` | FAIL | optional rotation/tap window shows measurable movement |
| `pose_or_motion_evidence` | FAIL | TIMU-004 has either multi-pose coverage or a motion sanity window |
| `source_boundary` | PASS | source remains bridge_uplink/unverified until formal acceptance |

## Boundary

This is a TIMU-004 pose/motion evidence gate, not product IMU acceptance.
Formal acceptance stays false while the source is `bridge_uplink/unverified`
and until mounting direction, calibration, FIFO/interrupt behavior, power
behavior, and a real `platform_imu` backend pass separate hardware gates.

## Timing Cross-Check

The same live capture was also checked with the TIMU-003 sample-quality
analyzer:

- JSONL lines: 123.
- `imu_sample` count: 120.
- QMI8658 WHOAMI: `0x05`.
- `samples_emitted=120`, `read_errors=0`, `not_ready_count=0`.
- `timing_mode=vTaskDelayUntil`, `missed_deadlines=0`, `max_sample_work_ms=42`.
- Expected interval: `50 ms`.
- Observed mean interval: `49.99 ms`.
- Observed sample rate: `20.00 Hz`.
- Device timing gate: PASS.

This preserves the TIMU-003 20Hz timing result in the new TIMU-004 capture.

## PC Bridge And M1 Loop

The live capture was fed through the existing PC Bridge and M1 data loop after
adding UTF-8 BOM tolerance to the JSONL consumers:

- PC Bridge stored 123 events with 0 skipped lines.
- Session recorder produced 120 `imu_motion` sensor frames.
- Quality gate PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.
- Replay PASS, 120 replayed inputs, all `risk_type=none`.

## Current Conclusion

TIMU-004 is partially complete. The current board position is a valid static
`z_negative` pose window with conservative calibration offset estimates
`[56.6, 23.0, -30.5] mg`. However, this run did not include manual board
rotation, tapping, or multiple static orientations. Therefore multi-pose
coverage, axis/sign coverage, motion sanity, and formal IMU acceptance remain
false.
