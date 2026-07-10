# HDBRIDGE-002 AMOLED QMI8658 Live Capture - 2026-06-23

## Scope

HDBRIDGE-002 verifies the first live USB serial bridge from the
`ESP32-S3-Touch-AMOLED-2.06` board into the existing PC Bridge and M1 recording
loop.

This task proves:

- the AMOLED board can be flashed over native ESP32-S3 USB Serial/JTAG;
- the board can emit newline-delimited JSON over `COM9`;
- the onboard PMU and QMI8658 are reachable over I2C using the vendor pin map;
- QMI8658 WHOAMI returns the expected value `0x05`;
- a bounded 40-sample accel/gyro window can pass through PC Bridge, session
  recording, quality gate, and replay.

This task does not prove full IMU acceptance. The data remains marked
`source_availability=bridge_uplink` and `source_status=unverified` until a later
task validates ODR, jitter, drop rate, orientation, calibration, FIFO/interrupt
behavior, mounting, and model suitability.

## Vendor Evidence Used

- Waveshare repository:
  `https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.06`
- Waveshare wiki:
  `https://www.waveshare.com/wiki/ESP32-S3-Touch-AMOLED-2.06`
- Vendor Arduino pin map:
  `examples/Arduino-v3.2.0/libraries/Mylibrary/pin_config.h`
- Vendor QMI8658 Arduino example:
  `examples/Arduino-v3.2.0/examples/04_LVGL_QMI8658_ui/04_LVGL_QMI8658_ui.ino`
- Vendor ESP-IDF AXP2101 example:
  `examples/ESP-IDF-v5.4.2/01_AXP2101/`

Relevant vendor-derived hardware constants used by the firmware:

| Item | Value |
|---|---:|
| I2C SDA | GPIO15 |
| I2C SCL | GPIO14 |
| AXP2101 address | `0x34` |
| AXP2101 expected chip id | `0x4A` |
| QMI8658 low address | `0x6B` |
| QMI8658 WHOAMI expected | `0x05` |

## Firmware Added

- `firmware/amoled_bridge/`
- `firmware/amoled_bridge/main/app_main.c`
- `firmware/amoled_bridge/README.md`
- `quality_tests/test_amoled_bridge_firmware.py`

The firmware prints:

1. `hello`
2. `imu_whoami`
3. 40 bounded `imu_sample` records at a requested 50 ms interval
4. `amoled_bridge_done`

AXP2101 bring-up is intentionally conservative. It enables only DC1 and ALDO1
at 3.3 V and does not disable other rails.

## Live Board Evidence

Windows identified the AMOLED board as native ESP32-S3 USB:

- `USB 串行设备 (COM9)`
- `USB JTAG/serial debug unit`
- `USB\VID_303A&PID_1001`

Flash command:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1
idf.py -p COM9 flash
```

Flash result:

- chip: `ESP32-S3 (QFN56) revision v0.2`
- USB mode: `USB-Serial/JTAG`
- PSRAM: `8MB`
- MAC: `02:00:00:00:00:01`
- app image: `egolink_amoled_bridge.bin`
- hard reset: successful

Captured JSONL:

- `pc_simulator/runtime/hdb002-amoled-live-20260623-194454.jsonl`
- line count: 43
- `hello`: 1
- `imu_whoami`: 1
- `imu_sample`: 40
- `amoled_bridge_done`: 1

WHOAMI probe summary:

```json
{
  "type": "imu_whoami",
  "sensor_model": "QMI8658",
  "source_availability": "bridge_uplink",
  "source_status": "unverified",
  "payload": {
    "axp2101_present": true,
    "axp2101_chip_id": 74,
    "qmi8658_addr": 107,
    "whoami": 5,
    "whoami_expected": 5,
    "revision": 124,
    "reset_result": 128,
    "validation_boundary": "identity_and_short_window_only"
  }
}
```

Completion summary:

```json
{
  "type": "amoled_bridge_done",
  "payload": {
    "samples_requested": 40,
    "samples_emitted": 40,
    "read_errors": 0,
    "not_ready_count": 0,
    "sample_interval_ms": 50
  }
}
```

Example sample:

```json
{
  "type": "imu_sample",
  "seq": 42,
  "device_monotonic_ms": 8409,
  "sensor_model": "QMI8658",
  "source_availability": "bridge_uplink",
  "source_status": "unverified",
  "payload": {
    "sample_index": 39,
    "qmi_timestamp": 2941,
    "accel_mg": [56, 27, -1029],
    "gyro_mdps": [-93, 1359, -140]
  }
}
```

The near-static acceleration vector is plausible for a board resting roughly
face-up or face-down, but HDBRIDGE-002 does not treat this as an orientation
calibration result.

## PC Bridge And M1 Loop

PC Bridge command:

```powershell
python scripts\board_bridge.py --source wearable=pc_simulator\runtime\hdb002-amoled-live-20260623-194454.jsonl --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --json
```

Result:

- `ok=true`
- stored events: 43
- skipped lines: 0
- devices: `wearable_node -> wearable-node-001`

Session recording command:

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\hdb002-amoled-live-20260623-194454.events.jsonl --session-id hdb002-amoled-live-20260623-194454 --output-dir pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
```

Result:

- source events: 43
- sensor frames: 40
- events: 0
- annotations: 0

Quality gate command:

```powershell
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
```

Result:

- passed: true
- quality score: `0.94`
- errors: 0
- warnings: 2
- frame types: `imu_motion=40`

Replay command:

```powershell
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdb002-amoled-live-20260623-194454 --json
```

Result:

- passed: true
- timeline records: 40
- replayed inputs: 40
- skipped records: 0
- model outputs: 40
- safety events: 0
- base commands: 0
- risk types: `none=40`

## Verification

- `python -m unittest quality_tests.test_amoled_bridge_firmware -v`: PASS, 4 tests.
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py build`: PASS.
- `. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM9 flash`: PASS.
- PC Bridge, recorder, quality gate, and replay: PASS as listed above.

## Boundaries

- This validates live QMI8658 identity and a short sample window only.
- It does not validate exact ODR, host-side timing jitter, sensor drop rate,
  FIFO, interrupts, orientation, calibration, mounting, or fall-detection
  usefulness.
- It does not validate AMOLED microphone capture, TF/SD, touch input, display
  UI, board-to-board UART, battery, fuel gauge, charger, or power consumption.
- It does not change the product P0 connectivity node. The original
  Waveshare ESP32-S3-SIM7670G-4G board remains the P0 cellular/GNSS board.
