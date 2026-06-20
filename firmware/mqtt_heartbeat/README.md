# Ego Link MQTT Heartbeat Smoke Test

This ESP-IDF firmware validates the first P0 data-link step on the
Waveshare ESP32-S3-SIM7670G-4G board:

1. Connect to Wi-Fi.
2. Connect to the local Mosquitto broker.
3. Publish status JSON to `ego/link/ego-link-001/status`.

Default local settings:

```text
Wi-Fi SSID: YOUR_WIFI_SSID
MQTT broker: mqtt://192.168.31.250:1883
Topic: ego/link/ego-link-001/status
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
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 192.168.31.250 -p 1883 -t ego/link/ego-link-001/status -C 1 -W 45
```

Pass criteria:

```text
MQTT_HEARTBEAT_WIFI_OK ip=<device-ip>
MQTT_HEARTBEAT_MQTT_CONNECTED broker=mqtt://192.168.31.250:1883
MQTT_HEARTBEAT_PUBLISH_OK seq=<n> ...
```
