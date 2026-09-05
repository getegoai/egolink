# HW021-C0.1 Conditional Interface and Budget Worksheet

State: `design_input`; hardware `NOT_RUN`

Numeric rule: vendor maxima and arithmetic reservations are not measured
EgoLink performance.

## Conditional Block Topology

```text
USB-C 5-V sink -> charger -> protected 1-cell battery
                              |-> SIM7670G VBAT candidate rail
                              |-> 3.3-V buck-boost -> MCU / IMU / F-RAM
                              |-> switched audio power -> codec / mic / amp

SOS / IMU / gauge / outbox -> ESP32-S3 candidate
                                 |-> UART+RTS/CTS candidate bearer -> SIM7670G
                                 |-> optional USB-host bearer (not selected)
                                 |-> I2S full duplex -> codec -> mic / speaker amp

SIM7670G -> independent 50-ohm LTE and GNSS matching/connector/antenna paths
```

The topology is conditional until the exact SIM7670G hardware manual and
CALL-020 measurements exist. Net names below are ownership labels, not frozen
pins or released schematic nets.

## MCU to Modem Bearer Decision

| Candidate path | Owned interface | Design reservation | Evidence state | Release decision |
| --- | --- | --- | --- | --- |
| `BEARER-A` | MCU UART TX/RX + RTS/CTS; modem internal socket/UDP commands | provisional 921600-baud ceiling, hardware flow control mandatory, sustained line occupancy target below 50% after measured framing | UART exists on official product page; baud, socket command semantics, latency and ESP firmware path `unverified` | Preferred continuity hypothesis only. Exact AT-manual commands and a no-PC CALL-021 traffic run must pass. |
| `BEARER-B` | ESP32-S3 USB host -> modem USB ECM/RNDIS | USB full-speed MCU side; useful throughput/driver/interoperability `unknown` | modem product page lists USB/RNDIS/ECM; ESP32-S3 has USB OTG, but this pair is not proven | Select only if UART cannot meet CALL-020-derived media budget. Requires an exact USB switch/arbitration design because MCU USB debug shares the physical path. |

Both paths retain a separate low-rate command/recovery UART. The modem USB
pins may reach test pads or a DNP switching footprint in C0; they must not be
shorted to the external debug connector. No PPP, ECM/RNDIS host-driver or
socket-throughput claim is made without exact official command documentation
and representative runtime evidence.

### CALL-020 Intake Fields

| Input | Current value | Downstream rule |
| --- | --- | --- |
| codec/profile | `unknown` | select MCU codec library and media packet format only after measurement |
| encoded uplink/downlink bitrate | `unknown` | each direction must fit the selected bearer below its declared occupancy ceiling |
| packet/frame interval | `unknown` | sets UART/USB transaction cadence and wake budget |
| P50/P95/P99 jitter and maximum gap | `unknown` | sizes jitter buffer and SRAM allocation |
| reconnect blackout and retry traffic | `unknown` | sizes outbox/control isolation and power burst window |
| signaling/encryption overhead | `unknown` | counted separately from encoded media payload |

## Ego Call Audio Path

Candidate clock ownership is MCU master, subject to a codec clock worksheet:

```text
MCU MCLK/BCLK/WCLK -> TLV320AIC3204
MCU I2S_DOUT       -> codec DAC -> mono line path -> TPA2011D1 -> speaker
MCU I2S_DIN        <- codec ADC <- T3902 PDM mic/codec digital-mic input
MCU I2C            <-> codec control
MCU GPIO           -> AUDIO_PWR_EN / CODEC_RESET / PA_EN
```

Provisional PCM design intake is mono, signed 16-bit, 16 kHz, 20-ms frames.
That is exactly 320 samples and 640 bytes per direction per frame, or 32,000
bytes/s (256 kbit/s) raw PCM in each direction. These are arithmetic values,
not CALL-010/CALL-020 measurements. Sample rate, slots, MCLK, encoded bitrate
and jitter depth remain configurable.

Audio safety/ownership rules:

- `AUDIO_PWR_EN`, codec output mute and `PA_EN` must have hardware default-off
  behavior; sequence is power -> configure/mute -> validate -> unmute -> PA on.
- Any reset, watchdog, brownout, bootloader or firmware crash must return the
  amp and microphone rail to the declared safe/privacy state.
- Candidate speaker continuous input is 0.7 W. The amp can exceed it, so the
  schematic must include a reviewed gain/rail/limiter bound before release.
- Full duplex requires separate capture/playback DMA and observable underrun,
  overrun, mute and recovery state. AEC/AGC/noise partition is `unknown` until
  enclosure and CALL evidence; it cannot be inferred from codec features.
- No ordinary call audio is retained by default. Audio test points are
  electrical-only unless an operator explicitly authorizes capture.

## Persistent Priority Outbox

`CY15B104Q-LHXI` offers 524,288 addressable bytes according to the official
candidate source. The product layout is not yet assigned. The release equation
is:

```text
critical_reserved_bytes
+ noncritical_bytes
+ redundant_superblock_bytes
+ ack_tombstone_bytes
+ integrity_and_version_bytes
<= 524288
```

Required invariants:

- noncritical records cannot consume the critical byte reserve or record
  reserve;
- stable event identity, payload hash/length, priority, attempt/backoff and
  ACK/tombstone state survive reset and torn writes;
- ACK authenticity/authorization is checked before deletion;
- corruption, full-media, critical-exhaustion and version-migration behavior
  terminates honestly and is externally observable;
- exact locations or raw media are not duplicated into general diagnostic
  records; the queue carries the minimum authorized payload/reference.

Sizing inputs from OUTBOX-010 product integration, retention policy, maximum
SOS rate, ACK outage duration and record size are all `unknown`. Host
double-mirror JSON is semantics reference only.

## Power Tree and Conditional Bounds

| Rail/domain | Candidate source | Load owners | Bound/status |
| --- | --- | --- | --- |
| `VBUS_5V` | USB-C sink only, no PD claim | charger/input protection | connector rating is not input budget; BQ25185 input limit is configured no higher than 1.1 A and never above source advertisement; exact CC/ESD design `unknown` |
| `CELL_RAW` | 1-cell pack | protection controller/FET | cell must be 4.2-V-compatible if gauge G1A is retained; pulse current, impedance, NTC and cold/aged behavior `unknown` |
| `VBAT_PROTECTED` | protected cell | modem, 3.3-V converter, switched amp/audio | modem candidate requires 3.4-4.2 V per SIMCom page; brownout/burst current/capacitance `unknown` |
| `V3V3_DIG` | TPS63802 candidate | MCU, IMU, F-RAM, logic | converter vendor limit is not system allowance; load inventory, efficiency, inductor, EMI/thermal derating and transient margin pending |
| `V_AUDIO_SW` | TPS22919 candidate or reviewed alternative | codec/mic and/or amp domains | exact split and voltage `unknown`; every audio power domain must be controllable/readable and default safe |
| `V_MODEM_IO` | exact modem IO domain | UART/USB/control translation | voltage and translation topology `unknown` until exact hardware manual |

Illustrative battery arithmetic only: a nominal 1250-mAh cell with a provisional
20% usable-capacity reserve provides `1000 mAh / 48 h = 20.8 mA` average battery
current for the 48-hour guard target. This does not establish usable capacity,
conversion loss, temperature/aging allowance or product battery life.

The linear charger thermal corner is also unresolved: at 5 V input, 3.4 V cell
and 1 A charge, the simple `(VIN - VBAT) * I` term is 1.6 W before system-load
effects. Charge current must be set from a reviewed thermal/enclosure model and
measurement, not the candidate's 1-A headline.

## Reset, Wake, SOS and Local Feedback

| Function | Owner | Required conditional net behavior | Current state |
| --- | --- | --- | --- |
| physical SOS | MCU always-on domain | dedicated wake-capable input, hardware bias, debounce/ESD, long-press timing; never multiplex with debug/boot strapping | exact switch, GPIO and mechanics `unknown` |
| local SOS acknowledgement | MCU + status/haptic/audio owners | immediate feedback independent of network; truthful escalation/failure pattern | exact haptic/status components and UX `unknown` |
| modem power/recovery | MCU safety kernel | owned PWRKEY/reset/wake/status signals, timeout and observable retry budget | signal names, levels, polarity and timing `unknown` pending hardware manual |
| IMU wake | IMU -> MCU | interrupt-capable wake, FIFO/timestamp lineage, mount axis recorded | exact pin and low-power evidence `unknown` |
| battery critical | gauge/protection -> MCU | alert cannot be erased by SOS; SOS retains higher policy priority | threshold/config/interrupt mapping `unknown` |
| brownout | power/MCU | PA/mic safe-off, durable event preserved or honest loss indication | unverified |

## SIM, Debug and Service Boundary

- `G85D1171312HHR` is a removable nano-SIM connector candidate; carrier,
  production SIM profile, APN, eSIM and child-access policy remain open.
- USB-C is 5-V charge plus development/service data. Production debug lock and
  signed recovery/OTA rules must be reviewed before release.
- ESP32-S3 built-in USB Serial/JTAG owns the primary development path. Expose
  UART0/EN/BOOT/GND/reference voltage on a connectorless recovery footprint;
  exact TC2030 pin mapping is a fixture design input, not yet a net assignment.
- Secrets, SIM identifiers, audio and exact private location never enter
  ordinary debug logs. Production lock must still permit an authenticated
  recovery path.

## RF, Antenna and Mechanical Constraints

- LTE and GNSS paths are independent 50-ohm controlled-impedance routes with
  separate pi matching footprints, ground stitching, ESD only where reviewed,
  MHF-I connectors and conducted-test access.
- `FXP40.07.0085A` and `FXP611.07.0092C` are A0 evaluation candidates, not
  enclosure antennas. Their 42.6 x 12.1 mm and 38 x 37 mm bodies make the
  founder's carry-form/envelope decision an immediate blocker.
- The ESP32-S3-WROOM-1 candidate also contains a 2.4-GHz PCB antenna. Wi-Fi/BLE
  is nonessential to P0 and should default off, but physical radio presence and
  compliance applicability cannot be declared absent.
- LTE antenna, GNSS antenna, MCU antenna, battery, speaker magnet, microphone
  inlet, ground plane, USB/SIM openings and the user's body/hand are one coupled
  placement problem. No layout can release before RF and mechanical review.
- Matching values are `DNP/TUNE` placeholders until VNA/TRP/TIS/GNSS and body-
  loading work on the actual enclosure. Vendor free-space data is not product
  evidence.
- Speaker/microphone waterproof ratings do not combine into an enclosure IP
  claim. Acoustic membranes and leak paths require coupled acoustic/IP tests.

## Required Test Points

At minimum, schematic review must account for:

- ground, VBUS, cell raw/protected, charger SYS, 3.3 V, every switched audio
  rail and current-measurement insertion points;
- MCU EN/BOOT/UART0/USB, reset reason marker and selected modem bearer;
- modem UART/RTS/CTS, USB D+/D-, PWRKEY/reset/wake/status, SIM detect and SIM
  supply/clock/data through safe high-impedance access;
- I2S MCLK/BCLK/WCLK/DIN/DOUT, codec I2C/reset, mic clock/data, PA enable and
  electrical speaker output measurement pads;
- IMU bus/interrupt, F-RAM SPI/chip-select/write-protect and gauge I2C/alert;
- LTE/GNSS RF conducted paths through reviewed connector/switch topology.

RF, SIM and class-D nodes must not receive generic long stub test pads. The EE
and RF reviewers own the final access topology.
