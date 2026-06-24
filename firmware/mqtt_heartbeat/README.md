# Ego Link MQTT Heartbeat Smoke Test

This ESP-IDF firmware validates the first P0 data-link step on the
Waveshare ESP32-S3-SIM7670G-4G board:

1. Connect to Wi-Fi.
2. Connect to the local Mosquitto broker.
3. Publish status JSON to `ego/link/ego-link-001/status`.
4. Publish sensor sample events to `ego/link/ego-link-001/event`.

Default local settings:

```text
Wi-Fi SSID: YOUR_WIFI_SSID
MQTT broker: mqtt://192.168.31.250:1883
Topic: ego/link/ego-link-001/status
Event topic: ego/link/ego-link-001/event
Sensor event interval: 30 seconds
```

Build and flash:

```powershell
cd firmware/mqtt_heartbeat
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash
```

Subscribe on the PC:

```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 192.168.31.250 -p 1883 -t ego/link/ego-link-001/status -t ego/link/ego-link-001/event -v -C 2 -W 60
```

Pass criteria:

```text
MQTT_HEARTBEAT_WIFI_OK ip=<device-ip>
MQTT_HEARTBEAT_MQTT_CONNECTED broker=mqtt://192.168.31.250:1883
MQTT_HEARTBEAT_PUBLISH_OK seq=<n> ...
MQTT_SENSOR_PUBLISH_OK seq=<n> ...
```

The first sensor event is a `sensor_sample` / `device_health` payload. It
reports ESP32 runtime observations that are available without extra drivers:
uptime, Wi-Fi RSSI, free heap, minimum free heap, mock battery/charging from the
`platform_power` log backend, mock IMU metadata from the `platform_imu` ring
buffer skeleton, mock modem state, and mock GNSS state. Later firmware tasks can
add real GNSS, power, IMU, or button values to the same event channel.

`platform_power` is currently a HARCH-002A / HPWR-001 log backend. It emits
serial log markers such as `PLATFORM_POWER_ENTER`, `PLATFORM_POWER_MARK`, and
structured `PLATFORM_POWER_EVENT` lines with `state_total_ms`,
`serial_marker_id`, and `gpio_marker_id=disabled`. MQTT status and
`sensor_sample` payloads include `battery_source=mock`, `charging_source=mock`,
`power_state`, `power_state_elapsed_ms`, `power_state_cumulative_ms`,
`power_marker_seq`, and marker IDs so a later PPK2 capture can be aligned with
firmware activity.

It does not read a real battery, charger, fuel gauge, sleep state, SIM7670G
power rail, or GPIO measurement marker yet. The GPIO marker remains disabled;
no runtime, current, or battery-life claim is valid until an external power
instrument is connected and its raw capture is saved.

`platform_imu` is currently a TIMU-007 backend-boundary PoC. The default
configuration remains the deterministic `mock_stationary` path with a bounded
32-sample ring buffer, `platform_imu_sample`, `platform_imu_push_sample`, and
`platform_imu_read_recent`. A QMI8658 I2C backend exists only as an explicit
Kconfig opt-in (`CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`) and falls back to
mock data if identity probing or reads fail. The default `sensor_sample` payload
still includes `imu_source`, `imu_hardware_present=false`,
`imu_driver_enabled=false`, `imu_sample_mock=true`, ring counts, and latest mock
accel/gyro fields so the M1 recorder can preserve the future interface shape.

This does not prove a real IMU is present, wired, oriented, sampled, calibrated,
or power-managed. Real accel/gyro data remains unavailable until the IMU part,
bus, pins, orientation, ODR, FIFO behavior, interrupt strategy, and sample
quality statistics are verified on the product path. The AMOLED-board QMI8658
evidence remains bridge evidence until a separately configured real
`platform_imu` capture is flashed, captured, and accepted.
