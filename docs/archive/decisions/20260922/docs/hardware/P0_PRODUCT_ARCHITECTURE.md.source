---
document_status: authoritative_interface_baseline
last_verified: 2026-08-23
verified_by: founder/codex
source_task: HW-020
---

# EgoLink P0 Product Architecture Baseline

## Decision Boundary

This document freezes the P0 block ownership and interface questions needed to
build `Reliable Location + Ego Call + SOS`. It is not a production schematic,
PCB, antenna, enclosure, part-number, BOM, sourcing or certification freeze.
Unknown and unverified fields remain explicit until named evidence closes them.

The development boards are evidence vehicles only:

- `wearable-node-001` has an unaccepted board-audio path and no cellular;
- `connectivity-node-001` has observed LTE data/GNSS engineering evidence but
  no accepted application audio path;
- the PC bridge is development infrastructure, never a product dependency.

## Target Product Blocks

```text
                         +----------------------+
physical SOS ----------> |                      | ---> local feedback
IMU -------------------> |                      | ---> persistent priority outbox
GNSS <-----------------> |  product MCU / RTOS  | ---> Location Engine + Policy v0
mic -> audio frontend -->|                      |<--> encoded RTC media
speaker/amp <------------|                      |<--> secure update/debug boundary
                         +----------+-----------+
                                    |
                                    | controlled data/control interface
                                    v
                         +----------------------+
LTE/GNSS antennas <----> | Cat.1 data + GNSS    | <--> SIM/eSIM
                         | modem                | <--> Guardian RTC/service
                         +----------------------+

battery -> protection/charger/fuel gauge/rails -> every block above
optional hard-powered camera interface ----------> experimental capture only
```

The primary call route is LTE data plus a controlled RTC service. Native VoLTE
is a separate reserve and cannot borrow evidence from the RTC path. Camera AI,
continuous media capture and learned policy are not P0 dependencies.

## Interface Ownership Matrix

| Interface | Owner / direction | Minimum contract | Current evidence | Freeze blocker |
|---|---|---|---|---|
| SOS key | always-on MCU input | debounce, long press, local durable event, local feedback | safety contracts and PC ordering fixture exist; physical integrated loop unverified | SOS-010 + priority outbox evidence |
| IMU | MCU sensor domain | motion evidence only; never coordinates | real bounded QMI8658 engineering windows observed | exact product part/mount/calibration/power unknown |
| GNSS | modem or GNSS domain -> MCU | fix/no-fix/error, source event time, reported quality | SIM7670G engineering fix/no-fix observed | product module/antenna/enclosure/field metrics unknown |
| LTE cell/data | modem <-> MCU | bounded secure transport, cell observation, reconnect state | Message Hub data slices observed on development board | sustained RTC bearer, TLS ingress, three-operator and power evidence unknown |
| microphone input | audio frontend -> MCU | explicit format/rate/channels, DMA bounds, privacy power state | BSP/dependency clues only; application and measurement unverified | CALL-010 and product acoustic topology |
| speaker output | MCU -> codec/DAC/amp | explicit format/rate, mute/PA fail-safe, volume bound | BSP/dependency clues only; application and measurement unverified | CALL-010 and product acoustic topology |
| RTC media | MCU <-> modem data | authenticated/encrypted full-duplex state, bounded reconnect/failure | CALL-001 control/replay is PC-side only | CALL-020 bridge metrics then CALL-021 embedded evidence |
| storage/outbox | MCU persistent domain | stable identity, write-before-send, ACK deletion, reboot recovery, finite overflow behavior | general contract direction accepted; product path unverified | OUTBOX-010/SOS-010 |
| battery/power | charger/protection/gauge -> MCU | rail budgets, source/SOC status, emergency override, brownout safety | development-board facts only | PWR-001 plus A0 rail/current measurement |
| camera reserve | separately switchable rail -> MCU | manual command, one still, trigger reason/time, privacy-visible power | development smoke only | not required for P0; no AI path |
| debug/update | physical/debug + secure boot/update owner | production lock state, recovery, signed update, no secret logging | unverified for product | A0 security design and manufacturing plan |

Exact voltage, pins, clocks, bus bandwidth, wake sources and power domains are
TBD until candidate parts are selected from official documentation and bench
evidence. Pin assignments must not be inferred from either development board.

## Must-Have vs Reserve

| Class | P0 must-have | Reserve / later | Status |
|---|---|---|---|
| Compute | deterministic Location Engine, Sensor Policy, SOS kernel, audio/RTC handoff, persistent queue | learned GNSS reliability and mobility estimators | MCU exact part `unknown` |
| Cellular/location | Cat.1 data, GNSS, SIM, LTE/GNSS RF paths | Native VoLTE, Wi-Fi/BLE anchors | exact modem/RF topology `unknown` |
| Sensors | IMU | camera interface and future sensors only if separately approved | product IMU `unknown` |
| Audio/interaction | microphone, speaker, frontend/codec/amp as needed, SOS key, haptic/status feedback | richer UI, recording, AI voice | topology frozen; exact parts/acoustics `unverified` |
| Power/mechanical | battery, protection, charging, gauge or validated SOC method, USB-C service/charge, carry/enclosure constraints | alternate cradle variants | size/capacity/enclosure `unknown` |

No new sensor may enter the P0 critical path without a founder-reviewed scope
change. Optional interfaces cannot consume RF, power, memory or schedule margin
needed by the three launch Gates.

## Audio Migration Path

```text
CALL-010: wearable board local capture/playback evidence
  -> CALL-020: explicitly PC-bridged LTE-data RTC metrics
  -> HW-021: exact part/bearer/audio/power design and engineering pack
  -> HW-022: built integrated prototype with bounded bring-up evidence
  -> CALL-021: independent power, no USB/PC media or control path
  -> P0-CALL representative product evidence
```

The bridge exists because current boards split audio and LTE. Its success may
select codecs, frame sizes and jitter budgets, but cannot pass P0-CALL or prove
the embedded interface.

## RF, Power, Mechanical and Privacy Constraints

- LTE and GNSS antenna keep-outs, ground, matching, coexistence, body loading,
  SAR/exposure and intended carry orientations must be reviewed before PCB and
  enclosure freeze.
- Microphone inlet, speaker outlet, SOS reachability, waterproofing and antenna
  placement are one coupled mechanical/acoustic/RF problem.
- Representative guard, moving, uncertain-location, SOS and sustained-call
  duty cycles must each be measured; an emergency/call run cannot borrow a
  low-duty battery claim.
- Camera and microphone power state must be visible and controllable. Ordinary
  voice is not retained by default; credentials, raw voice and exact private
  locations do not enter ordinary logs.
- Brownout, modem burst current, amplifier load, charging/thermal behavior and
  emergency override must have explicit rail/current evidence.

## A0 to A1 Re-Test Matrix

| Evidence item | A0 entry criterion | A1/EVT re-test trigger |
|---|---|---|
| GNSS/location | exact candidate/module/antenna plus LOC config identity | PCB, antenna, enclosure, carry form, modem firmware or policy parameter change |
| LTE/RTC | measured CALL-020 traffic profile and candidate bearer design | modem/SIM/operator/antenna/RTC/codec/bitrate/security change |
| Audio | CALL-010 metrics plus candidate codec/amp/mic/speaker path | PCB/layout, enclosure/ports, codec gain, speaker, mic, waterproof membrane or DSP change |
| SOS/outbox | durable event semantics and bounded storage design | key/mechanics, storage medium, firmware scheduler, ACK or retention change |
| Power | rail budget and measured mode currents | battery/charger/PMIC/modem/amp/antenna/firmware duty-cycle change |
| RF/compliance | COMPLIANCE-010 assumptions tied to this concept version | radio, antenna, enclosure, user/carry form, battery/charger or applicant change |
| Privacy/security | threat/retention/update/debug design | service provider, credential, logging, media or ownership-model change |

## Open Decisions

- exact MCU, modem, product IMU, audio frontend, storage, battery/charger/PMIC,
  antennas and enclosure: `unknown`;
- integrated MCU-to-modem RTC bearer and sustained throughput: `unverified`;
- microphone/speaker acoustics, AEC/AGC/noise, SPL and waterproofing: `unverified`;
- representative-day location, call, SOS and 48-hour power results:
  `NOT_RUN`;
- China classification/SRRC/进网/CCC/SAR/child-product path: pending a named
  qualified COMPLIANCE-010 opinion.
