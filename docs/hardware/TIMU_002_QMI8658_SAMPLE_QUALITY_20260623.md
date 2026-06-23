# TIMU-002 QMI8658 Sample Quality Report

- Source: `pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl`
- QMI8658 WHOAMI: `5` expected `5`
- Sample count: `40`
- Expected interval: `50` ms
- Observed mean interval: `82.3076923076923` ms
- Observed sample Hz: `12.149532710280374`
- Dominant accel axis: `z` `negative`
- Mean accel magnitude: `1031.4334730467212` mg
- Formal IMU acceptance: `False`
- Formal acceptance reasons: `source_status_unverified, device_timing_gate_failed, quality_gates_not_all_passed`

## Gates

| Gate | Result | Meaning |
|---|---:|---|
| `identity` | PASS | QMI8658 WHOAMI and AXP2101 identity |
| `completeness` | PASS | sample indices and event seq are contiguous |
| `completion` | PASS | firmware completion record reports no read/not-ready errors |
| `device_timing` | FAIL | observed device interval matches requested sample interval |
| `qmi_timestamp` | PASS | QMI timestamp is monotonic across samples |
| `static_orientation` | PASS | stationary accel vector is plausibly one dominant 1g axis |
| `static_gyro` | PASS | warm stationary gyro mean absolute rate is below sanity threshold |
| `source_boundary` | PASS | source remains bridge_uplink/unverified until formal acceptance |

## Boundary

This report is a measurement gate, not a product IMU acceptance. The source
must remain `bridge_uplink/unverified` until ODR, jitter/drop, mounting
direction, orientation, calibration, FIFO/interrupt behavior, and a longer
M1 recording quality gate pass together.
