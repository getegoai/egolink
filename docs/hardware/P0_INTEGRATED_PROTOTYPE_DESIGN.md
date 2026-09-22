---
document_status: current_design_intake
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
source_task: HW-021
---

# P0 Integrated Prototype Design Intake

## Boundary

This is the HW-021 buildable-design intake, not a selected BOM, schematic,
PCB, procurement instruction or hardware claim. HW-020 owns the interface
baseline; this document will bind each exact candidate and design revision to
official or measured evidence before HW-022 may build it.

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
migrates current voice requirements to native cellular primary, with CALL-030
feasibility feeding HW-021/HW-022 and CALL-031 product acceptance. The C0.1
candidate pack remains conditional historical design input; its RTC-era audio
assumptions cannot select the native path. CALL-020/021 remain paused.

## C0.1 Slice Result

`HW021-C0.1` is now a conditional candidate pack. It records exact order codes
where public first-party evidence supports them, separates document revision
from sample/module/firmware revision, and supplies conditional interface
worksheets. It deliberately stops before final down-select or schematic
capture.

| Block | C0.1 candidate intake | Source/evidence state |
| --- | --- | --- |
| MCU/RTOS | `ESP32-S3-WROOM-1-N16R8`; temperature-margin alternative `ESP32-S3-WROOM-1-N16R2` | exact official module identities checked; silicon/sample revision and product suitability `unverified` |
| Cat.1/GNSS modem | `SIM7670G` family/module marking | `identity_incomplete`: GNSS-enabled order suffix, HW/KDL revision, firmware and exact hardware-design manual `unknown` |
| IMU | `QMI8658C`, 14-pin LGA | official function/package checked; exact order suffix/lifecycle and product-mount evidence `unknown` |
| Camera / image media | no production candidate; one development setup reported OV5640 sensor identity and QVGA JPEG framing | module/lens/FPC/connector and product media-storage identities `unknown`; current A-line evidence is an input experiment only |
| audio | `TLV320AIC3204IRHBR`, `MMICT3902-00-012`, `TPA2011D1YFFR`, `AS01508MS-SP15-WP-R`, `TPS22919DCKR` | official candidates only; electrical/acoustic/full-duplex product evidence `unverified` |
| persistent storage | `CY15B104Q-LHXI` | official 4-Mbit SPI F-RAM candidate; allocation, authenticated ACK and failure semantics still open |
| charger/protection/gauge/logic rail | `BQ25185DLHR`, `BQ29700DSET` + `CSD83325L`, `BQ27441DRZR-G1A`, `TPS63802DLAR` | official candidates only; system calculations and representative power evidence absent |
| battery | `EEMB LP103042` bare-cell envelope probe | pack identity, NTC/protection/connector, pulse/impedance and product evidence `unknown` |
| SIM/USB/debug | `G85D1171312HHR`, `2036150003`, ESP32-S3 USB Serial/JTAG plus `TC2030-IDC` fixture concept | candidate interfaces documented; ESD/CC/lock/recovery and bearer arbitration open |
| LTE/GNSS RF | `FXP40.07.0085A`, `FXP611.07.0092C`, `20441-001E-01` | evaluation candidates only; enclosure fit, body loading, matching and representative RF evidence absent |

SIMCom first-party material conflicts on SIM7670G sleep current (`800 uA` on
the current product table versus `230 uA` in its 2024 certification news).
Neither value enters the product budget pending exact revision/firmware/network
conditions, vendor clarification and measurement.

## Conditional Architecture Inputs

- Embedded data bearer: reserve MCU UART TX/RX plus RTS/CTS as the continuity
  hypothesis; keep modem USB ECM/RNDIS as a conditional alternative. Neither
  is selected. Measured product event/image traffic plus a no-PC embedded run must prove
  throughput, latency, recovery and USB/debug arbitration.
- Native Ego Call: CALL-030 must identify the exact modem/firmware's analog,
  PCM/I2S or other supported full-duplex route, clock/control ownership and
  compatible microphone/codec/amp topology. C0.1's MCU-master I2S/PDM proposal
  is conditional, not a native-audio selection. Preserve default-off audio
  rail/mute/PA enables and a speaker-power bound. The 16-kHz/16-bit/20-ms
  worksheet is arithmetic only, not measured audio evidence.
- Persistent storage: reserve an SPI F-RAM path and a capacity equation for
  critical outbox records, redundant metadata and authenticated ACK/tombstone
  state. Exact record sizing and outage retention remain `unknown`.
- Camera/image media: keep the production Camera population, sensor/module,
  DVP/MIPI/SPI interface, lens/FOV/FPC and storage part unresolved. A populated
  variant requires default-off hard power, truthful privacy state, optical
  window/sealing and an image-media store independent of the priority outbox.
  The current 9-MiB/288-slot unencrypted engineering layout has exactly zero
  count margin at five minutes per image for 24 hours, can concentrate wear on
  low-numbered released slots, scans the full range at boot, and has no A/B OTA
  layout; none of those properties is a product baseline.
- Power: keep modem on a protected-cell-compatible conditional rail and logic
  on a separate 3.3-V buck-boost domain; audio is switched safe-off. Vendor
  maxima and nominal battery capacity are not system budgets.
- SIM/debug/RF: reserve removable nano-SIM detect, charge/service USB-C,
  connectorless recovery, separate LTE/GNSS 50-ohm paths, tuning footprints
  and conducted-test access. Production lock, privacy, antenna placement and
  final fixture topology require independent review.

## Versioned Pack

- [C0.1 pack boundary](../../hardware/p0_a0/README.md)
- [official-source candidate matrix](../../hardware/p0_a0/HW021_C0_1_SOURCE_MATRIX.md)
- [conditional interface and budget worksheet](../../hardware/p0_a0/HW021_C0_1_INTERFACE_BUDGETS.md)
- [independent review and release checklist](../../hardware/p0_a0/HW021_C0_1_REVIEW_CHECKLIST.md)

## Decisions Blocking Down-Select and HW-022

| ID | Required decision/evidence | Why it blocks release |
| --- | --- | --- |
| `B0` | exact GNSS-enabled modem order code, HW/KDL revision, firmware, hardware manual and errata | bearer IO levels/timing, reset/wake, power bursts, bands and GNSS cannot be frozen |
| `B1` | CALL-030 native control/audio evidence plus measured product data and embedded no-PC UART/USB proof | native audio ownership, bearer, buffers, memory, traffic and recovery budgets are still conditional |
| `B2` | founder carry form/envelope/battery target plus exact battery-pack evidence | battery, antennas, speaker chamber, thermal and rail calculations are coupled |
| `B3` | reviewed audio clock/register/gain/limiter/acoustic plan | full duplex, privacy-safe state, intelligibility and speaker protection are unproven |
| `B4` | product OUTBOX mapping, record sizing, authenticated ACK and retention bounds | 512-KiB candidate capacity cannot yet be allocated honestly |
| `B5` | qualified COMPLIANCE-010 response and exact operator/band/antenna assumptions | RF/layout/test/certification constraints remain open |
| `B6` | exact missing support parts, lifecycle/authorized-channel check and independent EE/RF/audio review | no final BOM/AVL, schematic or release review exists |
| `B7` | explicit PICO-versus-WROOM A0 MCU decision against the Master Context baseline | the C0.1 WROOM candidates cannot silently replace the named PICO engineering starting point |
| `B8` | comparable first-party evidence and an explicit SIM7670G-versus-China-market modem decision, including the Master Context's unverified `ML307A-GSLN` lead | SIM7670G continuity evidence cannot silently become the product modem selection |
| `B9` | explicit Camera population decision plus exact module/lens/FPC, bus/pin, hard-power/privacy, optical/sealing, image-media/endurance/encryption and OTA-capacity evidence | the current OV5640 development smoke and 16-MiB engineering flash layout cannot freeze a product Camera or storage path |

## Current Gate State

`P0-LOC`, `P0-CALL` and `P0-SOS` remain `NOT_RUN` for integrated hardware.
CALL-010 static build evidence and CALL-020 host/VPS evidence must not be
converted into board-level audio, traffic, power, RF or reliability claims.

## Parallel Inputs

- CALL-030 supplies native call/control/audio feasibility; measured data
  traffic supplies separate bearer budgets. CALL-031 consumes the integrated
  prototype for product acceptance. Missing numbers stay conditional.
- COMPLIANCE-010 supplies qualified constraints; the internal inquiry is still
  `NOT_SENT`.
- LOC-021 and OUTBOX-010 supply versioned state/event/storage semantics.
- Native cellular voice and its complete two-way audio path are required for
  P0-CALL; exact network mode remains evidence-bound. Production Camera
  population remains a separate growth decision. Camera is still
  a required measured input to the current ADR-0015 A-line milestone and to
  this conditional design review; the two scopes must not be conflated.

## Release-to-HW-022 Checklist

- exact orderable part/revision and official source for every must-have block;
- MCU/modem/audio/storage/power/RF ownership and timing/bandwidth budgets;
- schematic/ERC, BOM/AVL, layout/stack-up/impedance and test-point review;
- independent EE/RF/audio review with unresolved risks and re-test triggers;
- CALL-030 native control/audio, product data and pre-compliance assumptions
  traced or explicitly blocked; no automatic resumption of CALL-020/021;
- explicit founder authorization before procurement or fabrication.

No checklist row is currently complete.
