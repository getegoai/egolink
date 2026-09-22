---
document_status: authoritative_interface_baseline
decision_updated: 2026-09-22
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

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
replaces the former RTC-primary/native-reserve boundary. Native cellular voice
is the P0-CALL primary route; RTC is optional. CALL-020/021 stay paused. The
interface ownership and hardware evidence discipline below remain in force.

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
mic/speaker frontend <-->|                      |<--> optional RTC media
native modem audio <---->| controlled audio mux |<--> secure update/debug boundary
                         +----------+-----------+
                                    |
                                    | controlled data/control interface
                                    v
                         +----------------------+
LTE/GNSS antennas <----> | cellular + GNSS      | <--> physical nano-SIM
                         | native voice + data  | <--> authorized phone contact
                         +----------------------+

battery -> protection/charger/fuel gauge/rails -> every block above
optional hard-powered camera interface ----------> experimental capture only
```

The primary call route is the exact module/firmware/operator's supported native
cellular voice and complete microphone/speaker audio path. Audio may be modem
analog/PCM/I2S or a reviewed mux/codec topology; the sketch does not freeze it.
RTC evidence cannot prove native voice, and LTE does not imply CS fallback.
Camera AI, continuous capture and advanced learned policy are not P0 dependencies.

## Interface Ownership Matrix

| Interface | Owner / direction | Minimum contract | Current evidence | Freeze blocker |
|---|---|---|---|---|
| SOS key | always-on MCU input | debounce, long press, local durable event, local feedback | safety contracts and PC ordering fixture exist; physical integrated loop unverified | SOS-010 + priority outbox evidence |
| IMU | MCU sensor domain | motion evidence only; never coordinates | real bounded QMI8658 engineering windows observed | exact product part/mount/calibration/power unknown |
| GNSS | modem or GNSS domain -> MCU | fix/no-fix/error, source event time, reported quality | SIM7670G engineering fix/no-fix observed | product module/antenna/enclosure/field metrics unknown |
| LTE cell/data | modem <-> MCU | bounded secure transport, cell observation, reconnect state | Message Hub data slices observed on development board | product TLS ingress, three-operator data and power evidence unknown |
| microphone input | frontend -> selected native audio owner | documented analog/PCM/I2S format, levels/clocks, buffer bounds and privacy power state | BSP/dependency clues only; application and measurement unverified | CALL-030 interface feasibility, HW-021/022 topology, CALL-031 acoustics |
| speaker output | selected native audio owner -> codec/DAC/amp | explicit signal format, mute/PA fail-safe, volume bound | BSP/dependency clues only; application and measurement unverified | CALL-030 interface feasibility, HW-021/022 topology, CALL-031 acoustics |
| native call control/audio | single modem owner <-> authorized contact | dial/answer/hang-up/cancel, two-way audio, authorization, bounded failure/recovery | modem driver initialization is not acceptance | CALL-030 -> HW-022 -> CALL-031 |
| optional RTC media | MCU <-> modem data | authenticated/encrypted full-duplex state, bounded reconnect/failure | CALL-001 control/replay is PC-side only | legacy CALL-020/021 paused; separately accepted if resumed |
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
| Compute | deterministic Location Engine, Sensor Policy, SOS kernel, native call/audio handoff, persistent queue | RTC, learned GNSS reliability and mobility estimators | MCU exact part `unknown` |
| Cellular/location | native cellular voice, Cat.1 data, GNSS, physical nano-SIM, LTE/GNSS RF paths | Wi-Fi/BLE anchors | exact modem/RF topology `unknown` |
| Sensors | IMU | camera interface and future sensors only if separately approved | product IMU `unknown` |
| Audio/interaction | microphone, speaker, frontend/codec/amp as needed, SOS key, haptic/status feedback | richer UI, recording, AI voice | required roles defined; native topology, exact parts/acoustics `unverified` |
| Power/mechanical | battery, protection, charging, gauge or validated SOC method, USB-C service/charge, carry/enclosure constraints | alternate cradle variants | size/capacity/enclosure `unknown` |

No new sensor may enter the P0 critical path without a founder-reviewed scope
change. Optional interfaces cannot consume RF, power, memory or schedule margin
needed by the three launch Gates.

## Audio Migration Path

```text
CALL-030: exact modem/firmware/operator native call and audio feasibility
  + HW-021: exact part/bearer/audio/power design and engineering pack
  -> HW-022: built integrated prototype with bounded bring-up evidence
  -> CALL-031: independent power, no USB/PC media or control path
  -> P0-CALL representative product evidence
```

CALL-010 and the paused CALL-020/021 RTC bridge retain their measured evidence
scope. They cannot pass native P0-CALL or prove the selected native audio path.
HW-021 may prepare unrelated design inputs while CALL-030 evidence is pending.

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
| LTE/native voice | CALL-030 exact voice/control/audio feasibility and measured product data profile | modem/SIM/operator/antenna/firmware/voice-mode/security change |
| Audio | CALL-030 native interface plus candidate codec/amp/mic/speaker path; CALL-010 only within its measured scope | PCB/layout, enclosure/ports, codec gain, speaker, mic, waterproof membrane or DSP change |
| SOS/outbox | durable event semantics and bounded storage design | key/mechanics, storage medium, firmware scheduler, ACK or retention change |
| Power | rail budget and measured mode currents | battery/charger/PMIC/modem/amp/antenna/firmware duty-cycle change |
| RF/compliance | COMPLIANCE-010 assumptions tied to this concept version | radio, antenna, enclosure, user/carry form, battery/charger or applicant change |
| Privacy/security | threat/retention/update/debug design | service provider, credential, logging, media or ownership-model change |

## Open Decisions

- exact MCU, modem, product IMU, audio frontend, storage, battery/charger/PMIC,
  antennas and enclosure: `unknown`;
- exact native call control/audio, integrated MCU-to-modem data bearer and
  sustained throughput: `unverified`;
- microphone/speaker acoustics, AEC/AGC/noise, SPL and waterproofing: `unverified`;
- representative-day location, call, SOS and 48-hour power results:
  `NOT_RUN`;
- China classification/SRRC/进网/CCC/SAR/child-product path: pending a named
  qualified COMPLIANCE-010 opinion.
