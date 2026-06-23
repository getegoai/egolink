# Ego Link AMOLED Bridge Smoke

This ESP-IDF firmware is the bounded live smoke for the
Waveshare ESP32-S3-Touch-AMOLED-2.06 wearable-node candidate.

It prints newline-delimited JSON to the ESP32-S3 native USB serial/JTAG console:

1. `hello` for PC Bridge role binding.
2. `imu_whoami` with AXP2101 and QMI8658 probe metadata.
3. A short `imu_sample` window from the QMI8658 accelerometer and gyroscope.
4. `amoled_bridge_done` with sample/drop counters.

The firmware intentionally keeps every IMU frame marked:

```text
source_availability=bridge_uplink
source_status=unverified
```

This smoke proves only that the board can emit bridge-shaped QMI8658 samples.
It is not yet an ODR, jitter, drop-rate, orientation, calibration, interrupt,
FIFO, power, or product MotionNet validation.

## Board Mapping

The pin map follows the vendor example for ESP32-S3-Touch-AMOLED-2.06:

```text
I2C SDA = GPIO15
I2C SCL = GPIO14
AXP2101 = 0x34
QMI8658 = 0x6B
QMI8658 WHOAMI expected = 0x05
```

The AXP2101 bring-up is conservative: it reads chip ID and enables only the
two 3.3 V rails used by the vendor ESP-IDF example, DC1 and ALDO1. It does not
disable any rail.

## Build

```powershell
cd firmware/amoled_bridge
idf.py set-target esp32s3
idf.py build
```

## Flash And Capture

Use the current native USB COM port for the AMOLED board. On the first live
bring-up it was detected as `COM9` with `VID_303A&PID_1001`.

```powershell
idf.py -p COM9 flash
```

Then capture the JSONL output from the same port. Pass criteria:

```text
{"type":"hello",...,"role":"wearable_node",...}
{"type":"imu_whoami",...,"whoami":5,...}
{"type":"imu_sample",...,"sensor_model":"QMI8658",...}
{"type":"amoled_bridge_done",...,"samples_emitted":40,...}
```

After capture, feed the JSONL file to the existing PC Bridge:

```powershell
python scripts\board_bridge.py --source wearable=path\to\amoled.jsonl --event-log path\to\events.jsonl --json
python scripts\session_recorder.py --event-log path\to\events.jsonl --session-id hdb002 --output-dir pc_simulator\runtime\recordings\hdb002 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\hdb002 --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\hdb002 --json
```
