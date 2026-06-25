# Ego Link AMOLED Safety Demo

This is `DEMO-002`: the first visible wearable-node safety prompt for
ESP32-S3-Touch-AMOLED-2.06.

It is intentionally small and user-facing:

1. Boot the AMOLED board.
2. Initialize the Waveshare ESP-IDF BSP display/touch stack.
3. Show an idle screen:

```text
Ego Link
Waiting for PC Bridge
```

4. Receive a PC Bridge `ask_user` JSON command over USB Serial/JTAG.
5. Show an on-device prompt:

```text
Impact detected
Are you safe?
[SAFE] [HELP]
```

6. Touching either button prints a USB serial JSON event:

```json
{"type":"user_confirmation","device_id":"wearable-node-001","role":"wearable_node","protocol_version":"0.2","cmd_id":"demo-v0-2-001","response":"safe"}
```

This demo does not yet run MotionNet, real fall detection, GNSS, calling, or
4G. It proves the product interaction can be seen and tapped on the wearable
node from the PC Bridge `ask_user` command. The next step is to merge this UI with the QMI8658 IMU bridge.

The UI uses English labels for now because the minimal LVGL config does not
ship a CJK font. The final product can replace the text with Chinese once a
proper font asset is added.

## Build

This project uses the official Waveshare ESP-IDF component for
`ESP32-S3-Touch-AMOLED-2.06` and LVGL 9.2.0. Display dependencies are pinned to
the official Waveshare ESP-IDF v5.4.2 LVGL demo set:

- `waveshare/esp32_s3_touch_amoled_2_06` 1.0.3
- `waveshare/esp_lcd_sh8601` 1.0.2
- `espressif/esp_lvgl_port` 2.6.0

Earlier registry resolution selected a newer BSP/display stack combination that
compiled and emitted touch events but rendered corrupt frames on the panel.

```powershell
cd firmware/amoled_safety_demo
idf.py set-target esp32s3
idf.py build
```

## Flash

Use the native USB COM port for the AMOLED board:

```powershell
idf.py -p <AMOLED_COM_PORT> flash monitor
```

Expected serial events:

```text
{"type":"hello",...,"role":"wearable_node",...}
{"type":"display_ready",...,"response":"waiting"}
```

## Run Demo v0.2

After flashing, send one bounded PC Bridge command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1
```

For the full tap loop, keep the board connected and tap `SAFE` or `HELP`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1 -RequireConfirmation -WaitSeconds 45
```

Expected serial events:

```text
{"type":"command_ack",...,"cmd":"ask_user",...}
{"type":"ask_user_rendered",...,"response":"pending"}
{"type":"user_confirmation",...,"response":"safe"}
```
