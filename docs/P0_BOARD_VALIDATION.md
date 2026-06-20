# Ego Link P0 Board Validation

This document defines the first quality gate for the Waveshare
ESP32-S3-SIM7670G-4G development board.

## Goal

Before writing the full ESP-IDF P0 firmware, validate that the board is a usable
Ego Link portable-node target:

1. ESP32-S3 serial console is visible.
2. SIM7670G USB composite device is visible.
3. SIM7670G AT ports respond to basic identity commands.
4. RNDIS adapter is present for current board-level diagnostics.
5. Current firmware logs are captured when available.
6. SD card mount state is recorded when boot logs are visible.

The probe does not validate production 4G data, real GNSS, camera capture,
power consumption, or the final Ego Link event loop. Those belong to later P0
sprints.

## Run

```powershell
python scripts/egolink_board_probe.py
```

The command prints the Markdown report path and writes:

```text
reports/board_validation/<timestamp>/probe.json
reports/board_validation/<timestamp>/probe.md
```

If SD card status is not observed, rerun the probe and press the board reset
button during the ESP32 listen window:

```powershell
python scripts/egolink_board_probe.py --esp-listen-seconds 12
```

## Non-Destructive Boundary

The probe is read-only except for basic AT queries:

```text
AT
ATI
AT+CPIN?
AT+CSQ
AT+CEREG?
AT+CGATT?
```

It does not:

- Dial calls.
- Start PPP.
- Attach packet data.
- Change SIM7670G settings.
- Flash firmware.
- Write to the SD card.

## Quality Gates

| Gate | Expected Result |
|---|---|
| `esp32_ch343_serial_present` | PASS |
| `sim7670_usb_serial_present` | PASS |
| `sim7670_rndis_adapter_present` | PASS |
| `sim7670_at_identity` | PASS, model includes `SIM7670G` |
| `sim_card_absent_expected` | PASS while no SIM card is inserted |
| `esp32_serial_log_read` | PASS if reset/log appears, WARN if no log appears |
| `sd_card_mount` | PASS before storage-dependent firmware work; FAIL means inspect SD format, slot, wiring, or firmware SD mode |

## Current Interpretation

For P0, the board can proceed as an Ego Link主控候选 if USB enumeration and
SIM7670G AT identity pass. SD card failure is not blocking for Sprint 1
heartbeat over Wi-Fi, but it is blocking for Sprint 5 offline cache unless the
firmware uses NVS/SPIFFS first or the SD mount problem is fixed.

## Relation To The Larger EGO System

Ego Link is the portable sensing and communication node. It should upload
events, location, wake, SOS, and device health through a replaceable
`LinkTransport` abstraction.

EGO Base / Ego Data Core is the home or local station layer. It should receive,
store, interpret, and summarize events. P0 deliberately uses a PC Simulator
instead of the final EGO Base so the portable-node firmware can mature first.
