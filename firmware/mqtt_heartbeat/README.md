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

## Optional FW-001 HTTP Message Hub Mode

The default firmware path remains the local MQTT smoke test above. For the
USB-Free R1 walking skeleton, enable the opt-in HTTP Message Hub transport and
post directly to the VPS service:

```text
CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED=y
CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL="http://<operator-vps>:8790"
CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN="<runtime-token>"
CONFIG_EGOLINK_DEVICE_ID="ego-link-r1-connectivity-001"
CONFIG_EGOLINK_FW_VERSION="0.1.0-fw001-http"
CONFIG_EGOLINK_TEST_RUN_ID="field-r1-<yyyymmdd>-001"
```

Use a local ignored config file such as `sdkconfig.vps.local` for real values.
Do not commit real VPS addresses, passwords, bearer tokens, or private device
logs. HTTP mode keeps the current protocol version `egolink.p0.v1`, posts
device registration and heartbeat/status messages to the Message Hub, uploads
the existing `sensor_sample` telemetry to `/telemetry`, polls
`/commands/poll`, and ACKs any pending command with `status=ok`.
`CONFIG_EGOLINK_TEST_RUN_ID` is optional; leave it empty for normal smoke
builds and set it only for a named field run so server exports can bind
status, telemetry, and ACK messages to that run.

Prepare a local ignored R1 config and build the HTTP firmware:

```powershell
powershell -ExecutionPolicy Bypass -File ..\..\scripts\prepare_fw001_hw_config.ps1 `
  -HostName <operator-vps> `
  -TokenFile ..\..\server\runtime\vps_message_hub_token.txt `
  -Build
```

After the operator flashes the connectivity node, powers it independently, and
disconnects USB for the runtime path, validate the VPS loop:

```powershell
python ..\..\scripts\validate_fw001_hw_loop.py `
  --hub http://<operator-vps>:8790 `
  --device-id ego-link-r1-connectivity-001 `
  --test-run-id <same-test-run-id>
```

The guarded R1 runner wraps those steps and refuses hardware-affecting phases
unless explicit operator flags are provided:

```powershell
# Plan only; no hardware action.
powershell -ExecutionPolicy Bypass -File ..\..\scripts\run_fw001_hw_r1.ps1 `
  -HostName <operator-vps>

# Prepare local config and build only.
powershell -ExecutionPolicy Bypass -File ..\..\scripts\run_fw001_hw_r1.ps1 `
  -HostName <operator-vps> `
  -PrepareBuild

# Flash only after choosing the actual ESP32 console port.
powershell -ExecutionPolicy Bypass -File ..\..\scripts\run_fw001_hw_r1.ps1 `
  -HostName <operator-vps> `
  -Flash `
  -FlashPort COM4 `
  -IUnderstandFlashWritesFirmware

# Validate only after independent power is connected and USB is disconnected.
powershell -ExecutionPolicy Bypass -File ..\..\scripts\run_fw001_hw_r1.ps1 `
  -HostName <operator-vps> `
  -Validate `
  -OperatorConfirmedIndependentPower `
  -OperatorConfirmedUsbDisconnected `
  -TestRunId <same-test-run-id>
```

FW-001 HTTP mode is an R1 networking and command-ACK proof. It still reports
mock GNSS and mock power fields and does not prove real GNSS, LTE module
control, battery, camera, audio, or product power behavior.

## FW-002 request_location scaffold

HTTP Message Hub mode now recognizes the downlink command
`request_location`. The first implementation is intentionally a GNSS telemetry
scaffold: when the command is received, firmware uploads one
`location_report` event to `/telemetry` and then ACKs the command. The report
uses explicit no-fix fields:

```text
event_type=location_report
source=firmware_gnss_scaffold
source_status=unverified
fix=false
gnss_state=driver_not_integrated
location_request_cmd_id=<cmd_id>
```

This proves only the USB-Free Message Hub command/telemetry path for location
requests. It does not control SIM7670G GNSS, read satellites, produce real
coordinates, prove LTE data transport, or replace the later outdoor R2 GNSS
field test.

## FW-002B SIM7670G firmware GNSS AT query

FW-002B adds an opt-in SIM7670G GNSS firmware backend behind the same
`request_location -> location_report -> ACK` envelope:

```text
CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y
CONFIG_EGOLINK_SIM7670_UART_NUM=1
CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17
CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18
CONFIG_EGOLINK_SIM7670_UART_BAUD=115200
```

The default remains disabled. When enabled, the firmware initializes UART1
using the Waveshare ESP-IDF SIM7670X example pin convention
`ESP32-S3 RX GPIO17 <- module TX` and `ESP32-S3 TX GPIO18 -> module RX`,
sends bounded AT commands (`AT`, optional `AT+CGNSSPWR=1`,
`AT+CGNSSINFO`, `AT+CGPSINFO`), parses no-fix/fix responses, and uploads one
`location_report` with:

```text
source=sim7670g_firmware_gnss
source_status=unverified for no-fix/unreachable states, observed for parsed fix=true coordinates
gnss_source=sim7670g_uart_at
gnss_driver=uart_at
gnss_query_ok=<true|false>
gnss_state=<fix|no_fix|at_unreachable|uart_init_failed>
raw_command=<bounded AT command>
raw_response=<bounded AT response summary>
```

`fix=true` requires parsed decimal coordinates from the module response.
Indoor `fix=false` / `gnss_state=no_fix` is expected and is still valid
telemetry. A fixed report with `source_status=observed` is hardware evidence,
not final product GNSS acceptance. This task does not toggle unknown modem
power GPIOs, does not use SIM7670G LTE data transport, and does not by itself
prove outdoor GNSS acceptance. Outdoor USB-Free validation remains a separate
field task.

## LTE-001A SIM7670G LTE registration and cell observability

LTE-001A adds an opt-in SIM7670G LTE status query behind the existing Wi-Fi
HTTP Message Hub uplink:

```text
CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y
CONFIG_EGOLINK_SIM7670_UART_NUM=1
CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17
CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18
CONFIG_EGOLINK_SIM7670_UART_BAUD=115200
```

The default remains disabled. When enabled, heartbeat/status and
`sensor_sample` uploads include optional `cell` and `lte` objects with SIM
state, registration state, APN/PDP state, assigned IP when available, cell
fingerprint, signal metrics, bounded raw AT evidence, and a diagnosable
`reason_code` such as `LTE_AT_UNREACHABLE`, `LTE_SIM_NOT_READY`,
`LTE_NOT_REGISTERED`, `LTE_NOT_ATTACHED`, `LTE_PDP_INACTIVE`, or `LTE_READY`.

This is observation only. It does not disable Wi-Fi, does not send Message Hub
HTTP traffic through the SIM7670G LTE data path, does not prove DNS/HTTP over
LTE, and does not replace the later LTE transport field gates.

Host-side validation for this scaffold is:

```powershell
python ..\..\scripts\validate_fw002_location_loop.py `
  --hub http://<operator-vps>:8790 `
  --device-id ego-link-r1-connectivity-001 `
  --test-run-id <same-test-run-id>
```

The first sensor event is a `sensor_sample` / `device_health` payload. It
reports ESP32 runtime observations that are available without extra drivers:
uptime, Wi-Fi RSSI, free heap, minimum free heap, reset diagnostics
(`reset_reason`, `boot_count`, and `boot_uptime_ms`), mock battery/charging
from the `platform_power` log backend, mock IMU metadata from the
`platform_imu` ring buffer skeleton, mock modem state, and mock GNSS state.
Later firmware tasks can add real GNSS, power, IMU, or button values to the
same event channel.

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

`platform_imu` is currently a TIMU-008 backend live-capture path with a
default-mock product profile. The default
configuration remains the deterministic `mock_stationary` path with a bounded
32-sample ring buffer, `platform_imu_sample`, `platform_imu_push_sample`, and
`platform_imu_read_recent`. A QMI8658 I2C backend exists only as an explicit
Kconfig opt-in (`CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658`) and falls back to
mock data if identity probing or reads fail. TIMU-008 validated that opt-in
profile on the ESP32-S3-Touch-AMOLED-2.06 board with AXP2101 rail bring-up,
QMI8658 WHOAMI `0x05`, boot-capture samples, MQTT payloads containing
`imu_sample_mock=false`, and an M1 recording/quality/replay pass. The default
`sensor_sample` payload still includes `imu_source`,
`imu_hardware_present=false`, `imu_driver_enabled=false`,
`imu_sample_mock=true`, ring counts, and latest mock accel/gyro fields so the
M1 recorder can preserve the future interface shape.

This does not prove a real IMU is present, wired, oriented, sampled, calibrated,
or power-managed on the final product path. Real accel/gyro data remains
unavailable for formal model training until mounting direction, final
calibration, ODR, FIFO behavior, interrupt strategy, power impact, and sample
quality statistics are verified in the product topology.
