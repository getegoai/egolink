# HW021-C0.1 Official-Source Candidate Matrix

Checked: 2026-08-23

Evidence boundary: public manufacturer material only

Decision state: `candidate_only`; no row is a product selection

## State Vocabulary

- `official_source_checked`: the linked manufacturer source names the part or
  family and supports only the facts copied here.
- `identity_incomplete`: a family or marketing identity exists, but an exact
  production ordering suffix, hardware revision or firmware identity is not
  public/loaded.
- `source_conflict`: two first-party sources disagree; no value is selected.
- `unverified`: suitability has not been proven by calculation, review or
  representative hardware.

Document revision is not silicon, module or lot revision. Sample marking,
module KDL/hardware revision, modem firmware, battery lot and antenna cable
assembly must be captured from received material before HW-022.

## Compute, Cellular and Motion

| Ref | Exact candidate identity | Official source and revision | Source state | HW-021 use and unresolved condition |
| --- | --- | --- | --- | --- |
| `MCU-C1` | `ESP32-S3-WROOM-1-N16R8` | [Espressif module datasheet v1.8, 2026-03-02](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) and [official module catalogue](https://www.espressif.com/en/products/modules/esp32-s3/esp32-s3-wroom-1) | `official_source_checked`; sample hardware/silicon revision `unknown` | Continuity candidate: 16 MB flash and 8 MB PSRAM. The official table gives the R8 variant a normal ambient ceiling of 65 C; ECC/temperature behavior, memory headroom, radio/compliance choice and representative power are `unverified`. |
| `MCU-C2` | `ESP32-S3-WROOM-1-N16R2` | Same Espressif module datasheet v1.8 | `official_source_checked`; sample hardware/silicon revision `unknown` | Temperature-margin alternative: 16 MB flash, 2 MB PSRAM and -40 to 85 C table entry. Audio/RTC/OTA memory headroom is `unverified`. It is not selected over `MCU-C1`. |
| `MODEM-C1` | `SIM7670G`, LCC+LGA, 24.0 x 24.0 x 2.4 mm | [SIMCom SIM7670X official product page](https://cn.simcom.com/product/SIM7670X.html), currently listing `SIM7670X` Chinese specification `251205` and AT manual v2.05 | `identity_incomplete` | Cat.1 bis family candidate with UART, USB, PCM, 1.8/3.0 V SIM, optional GNSS and official RNDIS/ECM feature rows. Exact GNSS-enabled ordering suffix, module HW/KDL revision, firmware build, public hardware-design revision, China operator status and embedded bearer interoperability are `unknown`. The same page says VoLTE `NA`; that is non-blocking for P0 but makes this candidate's native-VoLTE reserve unavailable unless SIMCom supplies different exact evidence. |
| `IMU-C1` | `QMI8658C`, 14-pin LGA | [QST QMI8658C product page](https://www.qstcorp.com/en_imu_prod/QMI8658) and [QMI8658C datasheet Rev A](https://www.qstcorp.com/upload/pdf/202210/13-52-27%20QMI8658C%20Datasheet%20Rev%20A%20%281%29.pdf) | `official_source_checked` for function/package; exact orderable suffix/lifecycle `unknown` | I2C/SPI candidate aligned with existing engineering observations. Product mount, interrupt behavior, calibration, low-power current and current-lot identity remain `unverified`; development-board results do not transfer. |

Governance note: the current Master Context names `ESP32-S3-PICO-1-N8R8` only
as the A0 engineering starting point. `MCU-C1/C2` are conditional WROOM
alternatives, not a silent replacement of that baseline. HW-021 must compare
PICO versus WROOM package/envelope, memory, antenna, temperature, sourcing and
portability implications and record an explicit down-select before schematic
freeze.

### SIMCom First-Party Power Conflict

The current SIM7670X product table reports `800 uA @ Sleep, DRX=0.64 s`, while
SIMCom's own [2024 SIM7670G certification news](https://cn.simcom.com/news_view-608.html)
reports `230 uA` under a DRX 0.64 s description. Neither number is used in the
A0 power budget. Exact module revision, firmware, network state and a vendor
clarification plus bench measurement are required.

The Master Context also carries `ML307A-GSLN` as a preferred but unverified
China-market candidate. C0.1 does not have enough first-party exact-SKU,
hardware/audio/GNSS/firmware evidence to add it as a checked row. `MODEM-C1`
is therefore a development-continuity candidate only, not a down-select; the
two paths require an explicit comparable-evidence decision.

## Camera And Image-Media Identity Gap

No production `CAM-C1` or Camera-media-storage candidate is created in C0.1.
The 2026-06-23 development-board run identified the attached sensor as an
OV5640 and produced three bounded QVGA JPEG frames. That local observation
does not identify the Camera module manufacturer, orderable part number,
module revision, lens, FPC, connector, production lifecycle or optical
performance. It also does not constitute a manufacturer source for any such
fact.

| Required identity | Current evidence state | What is known | Evidence required before a candidate row may be added |
| --- | --- | --- | --- |
| Camera sensor/module | `identity_incomplete` / `unverified` | One development setup reported OV5640 sensor identity and valid JPEG framing. | Physical module front/back markings, exact module OPN and revision, FPC/connector identity, received-sample marking/lot, and matching primary manufacturer documentation. |
| Lens/optical stack | `unknown` | No retained TCAM-001 image was reviewed for field of view or image quality. | Exact lens OPN, focal length/focus range, FOV, chief-ray/window constraints, IR/filter stack, mounting direction and primary lens/module documentation. |
| Image-media storage | `unknown` | The current Camera-collection build profile reserves a 9 MiB internal-flash image range; its initial on-board audit found that range empty. | Exact product storage OPN, interface, capacity, endurance, retention/security behavior, lifecycle and primary manufacturer evidence. The 512-KiB F-RAM outbox candidate is not an image store. |

The current A-line Camera result is therefore a design-input experiment, not a
production part selection. Camera remains outside the three P0 capability
Gates, and whether it is populated in the first sales configuration remains a
founder decision. Its optional population still requires a buildable,
default-safe interface and an independently reviewed enclosure variant.

## Audio Chain

| Ref | Exact candidate identity | Official source and revision | Source state | HW-021 use and unresolved condition |
| --- | --- | --- | --- | --- |
| `AUD-CODEC-C1` | `TLV320AIC3204IRHBR` | [TI orderable part page](https://www.ti.com/product/TLV320AIC3204/part-details/TLV320AIC3204IRHBR), datasheet Rev E | `official_source_checked`, TI status `ACTIVE` | Full-duplex I2S/TDM codec candidate with digital-mic input. Exact PDM-clock/register plan, analog rails, clock tree, AEC partition and ESP-IDF driver work are `unverified`. |
| `AUD-MIC-C1` | `MMICT3902-00-012` (`T3902`) | [TDK InvenSense product page](https://www.invensense.tdk.com/en-us/products/t3902) and [DS-000357 Rev 1.0](https://invensense.tdk.com/wp-content/uploads/2020/05/DS-000357-T3902-v1.0.pdf) | `official_source_checked`, TDK status `Production` | Bottom-port PDM microphone candidate. Acoustic port, membrane, PDM compatibility, clock mode, RF immunity in the integrated enclosure and privacy power state are `unverified`. |
| `AUD-AMP-C1` | `TPA2011D1YFFR` | [TI orderable part page](https://www.ti.com/product/TPA2011D1/part-details/TPA2011D1YFFR), datasheet Rev B | `official_source_checked`, TI status `ACTIVE` | Mono class-D candidate. It can exceed the candidate speaker's continuous rating, so hardware/software gain limiting, default-off enable and pop/click behavior are release blockers. DSBGA manufacturability review is pending. |
| `AUD-SPK-C1` | `AS01508MS-SP15-WP-R` | [PUI Audio official product page](https://puiaudio.com/product/speakers-and-receivers/as01508ms-sp15-wp-r) | `official_source_checked`; lifecycle/availability `unknown` | 15 x 11 x 2.5 mm, 8 ohm, 0.7 W candidate whose face is specified IP67. Enclosure IP, chamber volume, SPL, intelligibility, body loading and waterproof membrane performance are `unverified`. |
| `AUD-SW-C1` | `TPS22919DCKR` | [TI product page](https://www.ti.com/product/TPS22919), datasheet Rev B and active orderable listing | `official_source_checked`, TI status `ACTIVE` | Candidate hard power switch for microphone/codec subrail with default pull-down and output discharge. Rail partition, current and audible transient behavior remain `unverified`. |

CALL-010 static builds are not used as acoustic, power or current evidence.
CALL-020 must replace the provisional media fields in the interface-budget
worksheet with measured bitrate, packet cadence, jitter, blackout and recovery
inputs before this chain can be down-selected.

## Persistent Storage

| Ref | Exact candidate identity | Official source and revision | Source state | HW-021 use and unresolved condition |
| --- | --- | --- | --- | --- |
| `STORE-C1` | `CY15B104Q-LHXI` | [Infineon orderable part page](https://www.infineon.com/part/CY15B104Q-LHXI) and [CY15B104Q datasheet 001-94240 Rev *E](https://www.infineon.com/assets/row/public/documents/10/49/infineon-cy15b104q-4-mbit-512-k-8-serial-spi-f-ram-datasheet-en.pdf) | `official_source_checked`, Infineon status `active and preferred`, availability commitment shown to at least 2033 | 4-Mbit/512-KiB SPI F-RAM candidate for the priority outbox. Capacity allocation, authenticated ACK/tombstone retention, corruption model, secure deletion and product firmware driver are `unverified`. Host JSON evidence does not transfer. |

## Battery, Charging and Rails

| Ref | Exact candidate identity | Official source and revision | Source state | HW-021 use and unresolved condition |
| --- | --- | --- | --- | --- |
| `PWR-CHG-C1` | `BQ25185DLHR` | [TI orderable part page](https://www.ti.com/product/BQ25185/part-details/BQ25185DLHR), datasheet Rev A | `official_source_checked`, TI status `ACTIVE/Production` | 1-cell, 1-A linear charger/power-path candidate. Charge current must be thermally derated; its 4.5-V SYS behavior is not used as the SIM7670G supply. USB source advertisement, NTC network and charge-state UX remain unresolved. |
| `PWR-PROT-C1` | `BQ29700DSET` + `CSD83325L` | [TI BQ2970 family page](https://www.ti.com/product/BQ2970), BQ297x datasheet Rev I; [TI CSD83325L product page](https://www.ti.com/product/CSD83325L), datasheet Rev C | `official_source_checked`, both TI status `ACTIVE` | Candidate cell-protection controller plus dual common-drain FET. The `DSET` order code/threshold variant, actual FET losses, pack wiring and pulse/current limits must be recalculated against the chosen cell and measured modem/audio peaks; no protection adequacy is claimed. |
| `PWR-GAUGE-C1` | `BQ27441DRZR-G1A` | [TI orderable part page](https://www.ti.com/product/BQ27441-G1/part-details/BQ27441DRZR-G1A), datasheet Rev C | `official_source_checked`, TI status `ACTIVE/Production` | 4.2-V LiCoO2-profile system-side gauge candidate. Chemistry ID, sense resistor, learning cycle, temperature source and fit to the final cell are `unverified`. |
| `PWR-3V3-C1` | `TPS63802DLAR` | [TI TPS63802 product page](https://www.ti.com/product/TPS63802), datasheet Rev D | `official_source_checked`, TI status `ACTIVE` | 3.3-V buck-boost candidate for MCU/sensor/storage logic. The vendor 2-A capability is not a board budget; inductor, thermal, EMI and transient derating remain unknown. |
| `BAT-C1` | `EEMB LP103042` bare cell | [EEMB official product page](https://www.eemb.com/product-206) | `official_source_checked` for a 3.7-V, 1250-mAh, 30.5 x 44.0 x 10.3 mm bare-cell listing; exact pack revision/lot `unknown` | Envelope and energy-budget probe only. Official pulse-current/impedance, NTC, protection, connector, swelling allowance, aging, China pack evidence and intended carry-form fit are missing, so this cell cannot be selected or purchased from this row. |

## SIM, USB/Debug and RF

| Ref | Exact candidate identity | Official source and revision | Source state | HW-021 use and unresolved condition |
| --- | --- | --- | --- | --- |
| `SIM-CONN-C1` | `G85D1171312HHR` | [Amphenol CS official product page](https://www.amphenol-cs.com/product/g85d1171312hhr.html), product drawing Rev A | `official_source_checked`, Amphenol status `Active` | 4FF nano-SIM push-push connector with card detect. ESD parts, tray access/IP sealing, hot-plug policy and carrier SIM/eSIM decision remain `unverified`. |
| `USB-C1` | `2036150003` | [Molex official series page](https://www.molex.com/en-us/products/series-chart/203615) and [product specification](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/productspecificationpdf/203/203615/2036150002-000.pdf) | `official_source_checked`; exact stock/lifecycle `unknown` | 16-circuit waterproof USB 2.0 Type-C receptacle candidate. Connector IPx8 does not establish enclosure IP. Sink-only CC network, ESD, shield/chassis strategy and USB/modem arbitration remain unresolved. |
| `DBG-C1` | ESP32-S3 built-in USB Serial/JTAG plus `TC2030-IDC` recovery cable footprint | [Espressif USB Serial/JTAG guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/jtag-debugging/configure-builtin-jtag.html) and [Tag-Connect official cable page](https://www.tag-connect.com/product/tc2030-idc-6-pin-tag-connect-plug-of-nails-spring-pin-cable-with-legs) | `official_source_checked` | USB D-/D+ are GPIO19/GPIO20 for the Espressif path. Production lock, UART0/EN/BOOT pad mapping, fixture adapter and the conflict with a possible modem USB host bearer remain `unverified`; the cable is tooling, not a fitted BOM item. |
| `RF-LTE-C1` | `FXP40.07.0085A` | [Taoglas official product page](https://www.taoglas.com/product/fxp40-2g3g-flexible-antenna-2/) | `official_source_checked`; lifecycle/stock `unknown` | 698-2690-MHz flex evaluation antenna candidate, 42.6 x 12.1 mm with 85-mm MHF-I-compatible cable. It is not tuned for EgoLink enclosure/body loading and does not prove SIM7670G band/operator performance. |
| `RF-GNSS-C1` | `FXP611.07.0092C` | [Taoglas official product page](https://www.taoglas.com/product/cloud-fxp611-gps-glonass-compass-flexible-pcb-2/) | `official_source_checked`; lifecycle/stock `unknown` | Passive 1559-1610-MHz flex evaluation antenna candidate, 38 x 37 mm with 92-mm MHF-I-compatible cable. Size may be incompatible with the final Core; enclosure/body/hand detuning and GNSS-no-fix scenarios are `unverified`. |
| `RF-CONN-C1` | `20441-001E-01` | [I-PEX MHF I 4-pad official catalogue](https://www.i-pex.com/sites/default/files/downloads/pdf/CATALOG_MHF_I_E.pdf), catalogue Rev 9 | `official_source_checked` | 50-ohm MHF I board receptacle candidate for both evaluation antennas. Vibration retention, cable routing, mating-cycle/manufacturing process and final antenna topology require EE/RF/mechanical review. |

## Must-Have Identities Still Missing

These gaps prevent an exact schematic/BOM release even though a candidate row
exists above:

- SIM7670G GNSS-enabled orderable suffix, module HW/KDL revision, firmware and
  public hardware-design manual revision;
- QMI8658C orderable suffix/lifecycle confirmation;
- battery pack revision including cell, NTC, protection, connector, pulse and
  certification evidence;
- modem UART/USB voltage levels, PWRKEY/reset/wake timing and burst-current
  limits from the exact module hardware design;
- exact level translators, codec rail regulators, USB ESD/CC parts, RF matching
  values, SOS switch, haptic/status parts and production fixture adapter;
- exact Camera module/sensor/lens/FPC/connector identity and lifecycle, if the
  launch or an A0 evaluation configuration populates Camera;
- exact image-media storage part and its capacity, endurance, encryption,
  secure-retention and OTA-partition coexistence evidence;
- official vendor clarification of the SIM7670G sleep-current conflict;
- authorized-channel lifecycle/MOQ/lead-time evidence for every candidate.
