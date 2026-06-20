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
uptime, Wi-Fi RSSI, free heap, minimum free heap, mock battery, mock modem
state, and mock GNSS state. Later firmware tasks can add real GNSS, power, IMU,
or button values to the same event channel.
