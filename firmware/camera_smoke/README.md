# Ego Link Camera Smoke Test

This ESP-IDF test firmware validates the camera on the Waveshare
ESP32-S3-SIM7670G-4G board.

It does three things:

1. Initializes the Waveshare ESP32-S3-SIM7670G-4G camera connector pin map.
2. Waits 5 seconds, captures 3 JPEG frames at 3-second intervals, and prints
   `CAMERA_SMOKE_CAPTURE_OK` with capture index, size, checksum, frame geometry,
   and JPEG SOI/EOI bytes.
3. If Wi-Fi SSID/password are configured, starts a tiny HTTP server:

```text
http://<device-ip>/
http://<device-ip>/capture
```

## Hardware Checks

- CAM DIP switch: ON.
- USB HUB DIP switch: ON if you need the CH343 USB serial and SIM7670G USB
  composite interfaces.
- SD card is not required for this test.

## Build

```powershell
cd firmware/camera_smoke
idf.py set-target esp32s3
idf.py build
```

Optional Wi-Fi configuration:

```powershell
idf.py menuconfig
```

Set:

```text
Ego Link Camera Smoke -> Wi-Fi SSID
Ego Link Camera Smoke -> Wi-Fi password
```

`sdkconfig` is generated locally and must not be committed. Keep credentials
in the local generated config only; the tracked `sdkconfig.defaults` contains
no SSID or password.

## Flash And Monitor

```powershell
idf.py -p COM4 flash monitor
```

Pass criteria:

```text
CAMERA_SMOKE_INIT_OK profile=waveshare_esp32s3_sim7670g_4g
CAMERA_SMOKE_CAPTURE_SEQUENCE delay_ms=5000 count=3 interval_ms=3000
CAMERA_SMOKE_CAPTURE_OK capture_index=1 profile=waveshare_esp32s3_sim7670g_4g bytes=<non-zero> checksum=<hex> ... jpeg_soi=ffd8 jpeg_eoi=ffd9
CAMERA_SMOKE_CAPTURE_OK capture_index=2 profile=waveshare_esp32s3_sim7670g_4g bytes=<non-zero> checksum=<hex> ... jpeg_soi=ffd8 jpeg_eoi=ffd9
CAMERA_SMOKE_CAPTURE_OK capture_index=3 profile=waveshare_esp32s3_sim7670g_4g bytes=<non-zero> checksum=<hex> ... jpeg_soi=ffd8 jpeg_eoi=ffd9
```

The pin map follows the Waveshare board pinout: Y2-Y9 = GPIO7-GPIO14, PCLK = GPIO46, VSYNC = GPIO42, HREF = GPIO41, XCLK = GPIO39, SIO_D = GPIO15, SIO_C = GPIO16.
