---
document_status: authoritative
last_verified: 2026-07-12
verified_by: codex
owner: founder
---

# ADR-0005: Freeze the EgoLink V1 Pro Hardware Baseline

- Status: accepted
- Date: 2026-07-12
- Decision owner: founder

Peripheral revision: ADR-0006 supersedes the conflicting display, battery,
sensor-population, SIM, charging, and public voice-call clauses below. The
`nRF54LM20B + Air780EGH` platform and power-domain decision remain in force.

## Context

EgoLink V1 Pro needs a production-oriented hardware target that can run small
sensor and audio neural networks locally without giving up wearable standby
power. Repeating MCU and modem selection would delay the PCB, firmware port,
model benchmarking, enclosure, certification, and field-test schedule.

The current ESP32-S3 plus SIM7670G boards remain the validated engineering
vehicle. They are not the production BOM. The founder approved building the
performance model first and using it as the functional and data reference for
a later cost-down model.

## Decision

The following V1 Pro baseline is frozen through EVT and DVT:

| Function | Frozen part or implementation |
|---|---|
| Always-on MCU and edge AI | Nordic `nRF54LM20B-QGAA-R7`, QFN52 |
| China cellular and GNSS | OpenLuat `Air780EGH`, 8 MB RAM/Flash, external audio codec |
| Motion sensing | QST `QMI8658A` six-axis IMU |
| Always-on AI microphone | TDK InvenSense `MMICT5838-00-012` PDM microphone |
| Voice-call codec | Everest Semiconductor `ES8311` |
| Voice-call microphone | Separate analog microphone on the ES8311 input; final acoustic package is an EVT mechanical item |
| Speaker amplifier | Nsiway `NS4150B` with an 8-ohm miniature speaker |
| Model/update storage | Winbond `W25Q128JVPIQ`, 128 Mbit / 16 MB QSPI NOR |
| Charger and system power path | TI `BQ25895RTWR` |
| Battery state of charge | ADI/Maxim `MAX17048G+T10` |
| Always-on 3.0 V rail | TI `TPS62840DLCR` |
| 1.8 V microphone rail | TI `TPS7A0218PDBVR` |
| Cellular hard power switch | TI `TPS22965DSGR`, plus local low-ESR bulk capacitance |
| Display | Sharp `LS013B7DH03`, 1.28-inch 128x128 monochrome Memory LCD |
| Battery | Protected 1-cell Li-polymer, 3-wire NTC, target 700-900 mAh; exact cell dimensions freeze with the enclosure |

The product PCB exposes a nano-SIM holder and reserves an unpopulated MFF2
eSIM footprint. It provides separate LTE, GNSS, and 2.4 GHz antenna matching
networks and RF test connectors. Final antenna elements and battery dimensions
are enclosure-tuned components, not a change to this architecture.

The first V1 Pro PCB does not populate a camera, PPG sensor, touch controller,
Wi-Fi companion, Android-class application processor, or separate vision
accelerator. Camera pins may be reserved only if routing cost is negligible.

## Power Domains

```text
protected 1S Li-polymer
  -> BQ25895 power path
     -> TPS22965 -> Air780EGH + ES8311 + NS4150B (normally off)
     -> TPS62840 3.0 V -> nRF54LM20B + QMI8658A + display + QSPI flash
     -> TPS7A02 1.8 V -> T5838
  -> MAX17048 battery gauge
```

Air780EGH requires a supply capable of more than 1 A continuously and
1.5-2 A transient current. It therefore receives a dedicated high-current
switched domain with local bulk capacitance. The nRF54LM20B controls both the
load switch and Air780EGH `PWRKEY`/wake sequencing.

## Connectivity Behavior

A fully powered-off cellular modem cannot receive a remote network wake-up.
V1 therefore supports three command paths:

1. Local risk detection wakes cellular immediately.
2. The device wakes cellular on a scheduled short polling interval to fetch
   remote commands.
3. At home, BLE through EgoBase or a guardian phone can wake the cellular path.

Seconds-level remote calling from any location requires Air780EGH to remain
network-registered in its low-power mode and is a separately measured product
profile. It cannot be claimed together with the longest standby profile before
power measurements exist.

## Edge AI Boundary

The nRF54LM20B runs compact motion, acoustic-event, wake-word, sensor-fusion,
and risk-gating models. It does not run an LLM, continuous camera inference,
or full speech recognition. EgoBase or the cloud handles long context and
heavy reasoning.

## Freeze Rule

The architecture and named core parts above do not change because a newer or
cheaper chip appears. A change is allowed only when one of these disqualifying
conditions is evidenced:

- an official erratum prevents a required function;
- authorized supply cannot support EVT/DVT or the planned launch;
- measured power, RF, audio, or AI performance fails an approved hard gate;
- China certification or operator support is unavailable.

Any exception requires a new ADR approved by the founder. Passive values,
antenna tuning, battery dimensions, acoustic seals, connectors, and PCB layout
may change during EVT because they are implementation tuning, not platform
replacement.

## Consequences

- Firmware moves toward Nordic NCS/Zephyr for the always-on node while the
  Air780EGH uses LuatOS and a versioned UART contract.
- Existing QMI8658 datasets and event contracts remain reusable.
- V1 Pro is the model, power, and product reference. The CH592 cost-down board
  is deferred until V1 Pro proves the product loop.
- QFN nRF54LM20B supply is still ramping in July 2026. Development kits and
  project samples are the approved bridge; broker-market bare chips are not.

## Primary References

- Nordic nRF54LM20B: https://www.nordicsemi.com/Products/nRF54LM20B/Get-started
- Nordic nRF54LM20 DK: https://www.nordicsemi.com/Products/Development-hardware/nRF54LM20-DK/Hardware-files
- Air780EGH product information: https://docs.openluat.com/air780egh/product/
- Air780EGH power design: https://docs.openluat.com/air780egh/luatos/hardware/design/poweron/
- Air780EGH external ES8311 audio path: https://docs.openluat.com/air780epm/luatos/hardware/audio/
- TDK T5838: https://www.invensense.tdk.com/en-us/products/microphone/t5838
- TI BQ25895: https://www.ti.com/product/BQ25895
- ADI MAX17048: https://www.analog.com/en/products/max17048.html
- Sharp Memory LCD: https://global.sharp/products/device/lineup/selection/lcd/mobile/index.html
