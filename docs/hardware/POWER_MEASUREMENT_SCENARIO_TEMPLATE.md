# Ego Link Power Measurement Scenario Template

> Status: HPWR-001 template only. Do not treat this file as measured power data.

## Scenario

- Scenario ID:
- Scenario name:
- Firmware app: `firmware/mqtt_heartbeat`
- Firmware commit:
- Build command:
- Board: Waveshare ESP32-S3-SIM7670G-4G
- Power source:
- Instrument: PPK2 / Otii / other
- Instrument sample rate:
- Raw capture path:
- Operator:
- Capture started at:

## Firmware Markers

Expected serial log markers:

| Marker | Expected state | Notes |
|---|---|---|
| `PLATFORM_POWER_EVENT kind=INIT` | `BOOT` | Firmware power backend initialized. |
| `PLATFORM_POWER_EVENT kind=ENTER state=NETWORK_ATTACH` | `NETWORK_ATTACH` | Wi-Fi attach window begins. |
| `PLATFORM_POWER_EVENT kind=LEAVE state=NETWORK_ATTACH` | `NETWORK_ATTACH` | Wi-Fi attach window ends. |
| `PLATFORM_POWER_EVENT kind=ENTER state=GUARDING` | `GUARDING` | Normal guard loop is ready. |
| `PLATFORM_POWER_EVENT kind=ENTER state=UPLOAD` | `UPLOAD` | Status or sensor publish window begins. |
| `PLATFORM_POWER_EVENT kind=MARK state=UPLOAD` | `UPLOAD` | `UPLOAD_STATUS` or `UPLOAD_SENSOR`. |
| `PLATFORM_POWER_EVENT kind=LEAVE state=UPLOAD` | `UPLOAD` | Publish window ends. |

Marker fields to preserve:

- `seq`
- `uptime_ms`
- `duration_ms`
- `state_total_ms`
- `serial_marker_id`
- `gpio_marker_id`
- `gpio_marker_enabled`

## MQTT Evidence

Save the matching MQTT payloads from:

- `ego/link/ego-link-001/status`
- `ego/link/ego-link-001/event`

Required power fields:

- `battery_source=mock`
- `charging_source=mock`
- `power_state`
- `power_state_elapsed_ms`
- `power_state_cumulative_ms`
- `power_marker_seq`
- `power_serial_marker_id`
- `power_gpio_marker_id`
- `power_gpio_marker_enabled`

## Measurement Notes

- GPIO marker is currently disabled and must not be described as a real toggled
  measurement pin.
- Battery and charging fields are mock placeholders.
- Do not claim runtime, average current, peak current, or battery life unless
  the raw instrument capture is linked above.
- Record any missing serial markers, dropped MQTT events, resets, or Wi-Fi
  reconnects.

## Result Summary

- Capture valid: yes/no
- Marker alignment valid: yes/no
- Raw waveform archived: yes/no
- Follow-up needed:
