# TIMU-006 QMI8658 Long Window Report

Status: continuous long-window timing/jitter/drop evidence passed; formal IMU
acceptance remains false.

## Scope

TIMU-006 extends the ESP32-S3-Touch-AMOLED-2.06 QMI8658 bridge path from a
120-sample validation window to a configurable 600-sample long window.

This task does not switch product firmware to a real `platform_imu` backend and
does not claim fall, impact, wear-state, activity, or MotionNet training
readiness.

## Firmware Change

`firmware/amoled_bridge` now exposes two ESP-IDF project configuration values:

```text
CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT=600
CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS=50
```

The current default window is therefore about 30 seconds at 20 Hz.

Additional firmware output:

- `amoled_bridge_done.payload.samples_requested`
- `amoled_bridge_done.payload.samples_emitted`
- `amoled_bridge_done.payload.requested_window_ms`
- `amoled_bridge_done.payload.missed_deadlines`
- `amoled_bridge_done.payload.max_sample_work_ms`

The source boundary remains:

```text
source_availability=bridge_uplink
source_status=unverified
```

## Build And Flash

Firmware build:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1
idf.py build
```

Result:

- PASS
- App binary: `build/egolink_amoled_bridge.bin`
- Binary size: `0x38650`

Firmware flash:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1
idf.py -p COM9 flash
```

Result:

- PASS
- Chip: ESP32-S3
- PSRAM: 8 MB
- MAC: `02:00:00:00:00:01`
- Port: `COM9`

## Capture

The live long window was captured with:

```powershell
.\scripts\capture_amoled_qmi8658_pose_set.ps1 -MotionOnly -NoPrompt -RunM1Loop -SessionId timu006-qmi8658-long-window-live-20260624-0001 -OutputDir pc_simulator\runtime\timu006 -TimeoutSeconds 75 -SettleSeconds 0 -M1Limit 1000
```

Captured file:

```text
pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl
```

Capture summary:

- JSONL lines: `603`
- `imu_sample` records: `600`
- `imu_whoami` seen: `true`
- `amoled_bridge_done` seen: `true`
- Skipped non-JSON boot/log lines: `4`
- Source boundary: `bridge_uplink/unverified`

Completion payload:

- `samples_requested=600`
- `samples_emitted=600`
- `requested_window_ms=30000`
- `read_errors=0`
- `not_ready_count=0`
- `missed_deadlines=0`
- `max_sample_work_ms=42`

## Long-Window Analyzer

The long-window gate was run with:

```powershell
python scripts\analyze_imu_quality.py pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl --long-window --min-samples 500 --max-interval-jitter-ms 10 --json --markdown pc_simulator\runtime\timu006\timu006-qmi8658-long-window-live-20260624-0001.long_window_quality.md --title "# TIMU-006 QMI8658 Long Window Quality Report"
```

Result:

- Analysis mode: `long_window_timing`
- `quality_gates_passed=true`
- `formal_imu_acceptance=false`
- Formal acceptance reason: `source_status_unverified`
- Identity gate: PASS
- Completeness gate: PASS
- Completion gate: PASS
- Device timing gate: PASS
- Device jitter gate: PASS
- QMI timestamp gate: PASS
- Source boundary gate: PASS

Timing:

- Expected interval: `50 ms`
- Observed interval min/max: `49.0 / 50.0 ms`
- Observed mean interval: `49.9983305509182 ms`
- Observed sample rate: `20.000667801929946 Hz`
- Max interval deviation: `1.0 ms`
- Jitter limit used: `10.0 ms`
- QMI timestamp delta min/max/mean:
  `44.0 / 46.0 / 45.115191986644405`

The board was stationary during this capture, so static orientation and static
gyro also passed. TIMU-006 does not depend on those static gates; its acceptance
gate is the long-window timing/jitter/drop path.

## M1 Loop

The capture helper ran PC Bridge, session recording, quality gate, and replay.

PC Bridge:

- Stored events: `603`
- Skipped lines: `0`
- Generated commands: `0`

Session recorder:

- Source events: `603`
- Sensor frames: `600`
- Frame type: `imu_motion`

Quality gate:

- PASS
- `quality_score=0.94`
- `errors=0`
- `warnings=2`
- Warnings: `firmware_version_unknown`, `annotations_empty`

Replay:

- PASS
- Timeline records: `600`
- Replayed inputs: `600`
- Risk types: `none=600`
- Safety events: `0`
- Base commands: `0`

## Boundary

TIMU-006 proves that the current QMI8658 bridge path can sustain a 30-second,
600-sample, 20 Hz bounded capture with no missing sample indices, no read/not
ready errors, no missed deadlines, and very low device timestamp jitter.

It is still not product IMU acceptance. Remaining gates include:

- real `platform_imu` backend integration
- source promotion away from `bridge_uplink/unverified`
- product mounting direction and coordinate convention
- FIFO/interrupt behavior
- power-state and current-waveform validation
- repeated long-window capture under movement and worn-like mounting
