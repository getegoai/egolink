# TIMU-003 QMI8658 Timing Retest Report

- Source: `pc_simulator\runtime\timu003-qmi8658-live-20260623-201436.jsonl`
- QMI8658 WHOAMI: `5` expected `5`
- Sample count: `120`
- Expected interval: `50` ms
- Observed mean interval: `49.99159663865546` ms
- Observed sample Hz: `20.003361909564635`
- Dominant accel axis: `z` `negative`
- Mean accel magnitude: `1033.3724100896263` mg
- Formal IMU acceptance: `False`
- Formal acceptance reasons: `source_status_unverified`

## Gates

| Gate | Result | Meaning |
|---|---:|---|
| `identity` | PASS | QMI8658 WHOAMI and AXP2101 identity |
| `completeness` | PASS | sample indices and event seq are contiguous |
| `completion` | PASS | firmware completion record reports no read/not-ready errors |
| `device_timing` | PASS | observed device interval matches requested sample interval |
| `qmi_timestamp` | PASS | QMI timestamp is monotonic across samples |
| `static_orientation` | PASS | stationary accel vector is plausibly one dominant 1g axis |
| `static_gyro` | PASS | warm stationary gyro mean absolute rate is below sanity threshold |
| `source_boundary` | PASS | source remains bridge_uplink/unverified until formal acceptance |

## Boundary

This report is a measurement gate, not a product IMU acceptance. The source
must remain `bridge_uplink/unverified` until ODR, jitter/drop, mounting
direction, orientation, calibration, FIFO/interrupt behavior, and a longer
M1 recording quality gate pass together.

## PC Bridge And M1 Loop

The same live capture was fed through the existing PC Bridge and M1 data loop:

- PC Bridge stored 123 events with 0 skipped lines.
- Session recorder produced 120 `imu_motion` sensor frames.
- Quality gate PASS, `quality_score=0.94`, `errors=0`, `warnings=2`.
- Replay PASS, 120 replayed inputs, all `risk_type=none`.

This confirms the timing-fixed 120-sample window is compatible with the current
recording and replay path while still preserving the `bridge_uplink/unverified`
source boundary.
