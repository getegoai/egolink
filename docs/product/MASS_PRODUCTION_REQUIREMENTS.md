---
document_status: draft_pending_founder_approval
last_verified: 2026-07-03
verified_by: codex
source_task: PROD-001
---

# EgoLink V1 Mass-Production Requirements

This document defines the V1 hardware requirements and the fillable selection
checklists for production cellular module and MCU evaluation. It is
authoritative for the requirement structure, evidence gates, and non-decisions.
Any row containing TBD(founder) still requires founder confirmation before a
final module or MCU selection ADR can be written.

## 1. Scope And Non-Decisions

- China-market V1 only; overseas compliance is out of scope for this document.
- No production cellular module is selected here.
- No production MCU is selected here.
- SIM7670G remains the development comparison baseline, not a frozen BOM item.
- Confidential supplier pricing must be recorded outside the repository.
- Firmware logic, model behavior, pin assignments, protocol contracts, and
  hardware configuration are unchanged by this document.

## 2. Founder Confirmation Rule

Use TBD(founder) for values owned by founder/product approval: BOM ceiling,
acceptable MOQ and lead-time risk, target price bands, product form factor,
size and weight envelope, usage-profile cadence, launch battery claims, voice
calling scope, privacy-retention policy, and final market/channel assumptions.

Use other explicit markers for evidence that must come from engineering,
vendors, or later task output:

- TBD(datasheet): awaiting supplier datasheet or official module manual.
- TBD(quote): awaiting channel quote, MOQ, or lead-time response.
- TBD(MODEL-001): awaiting model footprint assessment.
- unverified: not proven in the loaded current context.

## 3. V1 Requirement Matrix

| Requirement area | Target value | Hard floor | Rationale and evidence basis | Founder confirmation |
|---|---|---|---|---|
| Product market | China-market V1 wearable safety companion with on-device AI companion capability. | Do not evaluate overseas SKU requirements in V1 selection. | V1 product plan scopes China market only and ADR-0002 makes on-device AI a V1 core requirement. | Final launch channel and operator assumptions: TBD(founder). |
| Full device BOM ceiling | Complete production BOM ceiling at 1k, 10k, and 50k volume tiers: TBD(founder). Include MCU, cellular module, GNSS path, antennas, sensors, display/touch/audio, battery, charger, PMIC, enclosure, assembly, test, and certification amortization. | No candidate can be selected without a quote path and comparison against the founder-approved full-system BOM ceiling: TBD(founder). | Hardware evaluation plan forbids selecting by chip price alone; full system BOM is the cost gate. | BOM ceiling, acceptable margin model, and confidential price handling: TBD(founder). |
| Typical guard-mode battery life | >= 48 hours measured on representative battery, enclosure, antenna, firmware configuration, and network profile. | 48 hours typical guard mode is the hard target; below 48 hours is a launch blocker unless the founder changes the product requirement. | Product and power documents set 48 hours as the minimum typical safety-guard target. | Battery capacity, heartbeat cadence, location cadence, screen-on allowance, and normal-signal definition: TBD(founder). |
| Light-use stretch battery life | 7-day light-use stretch target. | 5 days is the lower bound of the current 5-7 day stretch goal; whether 7 days is a hard launch gate is TBD(founder). | Power target document defines 5-7 days as the advanced light-use objective; task packet asks for a 7-day stretch definition. | Final light-use claim wording and allowed daily interaction budget: TBD(founder). |
| Emergency and weak-signal battery behavior | Emergency, high-frequency location, sustained voice, camera use, and weak-signal retry are measured separately and not allowed to borrow the 48-hour or 7-day claim. | Do not claim guard-mode or light-use battery life for emergency or weak-signal scenarios unless measured separately. | Power document says emergency, high-frequency location, calls, and weak signal do not promise the same endurance. | Which emergency-use claim, if any, appears in product copy: TBD(founder). |
| Size and weight envelope | Target dimensions, thickness, mass, battery capacity, and enclosure volume: TBD(founder). | Maximum wearable envelope and maximum mass: TBD(founder). No final PCB/module/battery choice should exceed the founder-approved envelope. | Wearability, child/elder comfort, antenna clearance, battery size, and microphone acoustics constrain the production design. | Target form-factor envelope and comfort threshold: TBD(founder). |
| Wearing and mounting form | Wearing form: TBD(founder) such as wrist, pendant, clip, or hybrid. Mount must keep SOS reachable, IMU orientation stable, microphone inlet exposed, antenna/GNSS path viable, and charging usable. | No form passes if it blocks SOS access, prevents reliable IMU orientation, covers microphone input, or makes LTE/GNSS antenna placement unworkable. | V1 safety loop depends on reliable interaction, motion data, audio path, and connectivity. | Final wearing mode, attachment method, removal alert requirement, and charging ergonomics: TBD(founder). |
| Environmental rating | Target ingress rating and operating/storage temperature range: TBD(founder). | Minimum IP rating and temperature floor/ceiling: TBD(founder). No environmental claim may be made before test evidence exists. | Daily safety wear needs sweat/rain/dust and seasonal temperature resilience; current context does not freeze values. | IP rating, sweat/rain exposure assumptions, temperature range, and test standard choice: TBD(founder). |
| China certification set | Plan for SRRC, China Network Access License / 进网许可, carrier IoT requirements, and CCC if applicable. Battery, charger, and radio certification obligations must be mapped before EVT freeze. | No pilot-production release without an applicability matrix and evidence that the selected module/SKU can complete required China certifications. | Task packet requires China market certification coverage; final applicability depends on SKU and sales channel. | Sales channel, charger-in-box decision, carrier cooperation path, and regulatory counsel owner: TBD(founder). |
| Data privacy baseline for minor/elder wearable | Consent-first data handling, guardian/user role model, privacy class on every session, data minimization, encrypted transport/storage where applicable, and no private real user logs committed to the repo. Retention windows: TBD(founder). | No data flywheel, audio capture, guardian sharing, or model-training export without explicit consent and privacy classification. Continuous raw audio upload must not be default. | ADR-0002 requires consented, privacy-classed sessions for the data flywheel; minor/elder wearable context raises privacy risk. | Consent flow, data retention, deletion/export SLA, guardian access rules, and audio retention policy: TBD(founder). |
| On-device AI companion budget | Production MCU must support local MotionNet-class candidate detection, real-time interaction loop, proactive check-in behavior, and graceful no-LTE degradation. RAM, flash, latency, and per-inference energy budgets: TBD(MODEL-001). | Do not select an MCU that lacks measurable RAM/flash headroom, a credible vector/NPU/DSP or optimized-kernel path, or a sleep-vs-inference power profile compatible with 48-hour guard mode. | ADR-0002 states on-device AI is V1 core and production hardware selection must budget for inference capability. | Feature mix that drives model size, always-on audio policy, and acceptable latency/power tradeoff: TBD(founder). |
| Microphone and interaction path | V1 hardware must include a validated microphone path for the companion interaction loop, plus display/touch/audio output path as required by the product interaction design. Mic count, acoustic placement, codec/interface, and voice UX: TBD(founder). | No EVT hardware freeze without a microphone routing decision and evidence that MCU/module/audio circuitry can capture the required audio signal under the intended wearing form. | ADR-0002 makes microphone and interaction gaps V1-relevant procurement and validation items. | Mic count, voice feature scope, wake/listen policy, and acoustic design target: TBD(founder). |

## 4. Usage Profile Definitions

Battery claims must be measured against named profiles. These definitions are
fillable because exact cadences are founder/product decisions.

| Profile | Included behavior | Excluded behavior | Values still to fill |
|---|---|---|---|
| Typical guard mode | SOS wake source enabled; low-power IMU sensing; required audio gate if enabled for V1; scheduled heartbeat; scheduled location refresh; event-triggered local prompt and upload; display mostly off; normal China Mobile network conditions. | Sustained voice call, camera capture, repeated weak-signal retries, emergency high-rate tracking, developer logging, and bench USB power. | Battery capacity, heartbeat interval, location interval, allowed prompts per day, screen-on seconds per day, audio-gate duty cycle, network-signal floor: TBD(founder). |
| Light-use stretch | Lower-interaction daily use, no emergency escalation, reduced location/heartbeat cadence, minimal display use, no sustained call or camera use. | Emergency, weak-signal stress, continuous companion conversation, frequent GNSS fixes, and high-rate data capture. | Daily interaction budget, reduced cadence, allowed check-ins, and whether 7 days is a hard public claim: TBD(founder). |
| Emergency mode | SOS flow, high-priority event upload, higher location cadence, guardian alert path, optional voice decision if approved. | Not used to support normal 48-hour or 7-day claim. | Emergency duration target, voice requirement, and location cadence: TBD(founder). |
| Measurement baseline | Representative battery, enclosure, antenna, SIM/operator, firmware image, model version, and environment recorded with raw power evidence. | Development-board USB-powered runs are not production battery evidence. | Production battery capacity and accepted test lab or bench procedure: TBD(founder). |

## 5. Cellular Module Evaluation Checklist

### 5.1 Decision Rule

A cellular module must pass every disqualifying gate before it can be scored.
Scored criteria are used only after all gates pass. Final selection requires an
ADR that records the evidence, tradeoffs, and founder-approved cost thresholds.

Disqualifying gates:

- China Mobile-focused RAT/band support and China certification path are
  documented by official supplier evidence.
- Data transport, registration, reconnect, and low-power states can support
  the 48-hour guard-mode power budget.
- GNSS strategy is documented: integrated module GNSS or external GNSS, with
  constellation support, cold/warm TTFF, power, antenna, and coexistence data.
- Voice capability and audio routing are documented enough to answer the V1
  voice question. If V1 voice is founder-approved, lack of a viable voice path
  becomes disqualifying.
- Microphone and audio interaction routing do not block the V1 companion loop.
- Production availability, lifecycle status, MOQ, lead time, and FAE/support
  path are known enough for EVT sourcing.

Scored criteria after gates pass:

- Lower sleep current and better PSM/eDRX behavior.
- Better GNSS TTFF/power/coexistence.
- Better AT/SDK maturity, diagnostics, and recovery tooling.
- Lower full-system BOM impact versus founder ceiling.
- Lower MOQ, shorter lead time, stronger certification inheritance, and better
  China-based FAE support.

### 5.2 Fillable Module Checklist

| Criterion | Role | Required evidence | Candidate value | Pass/score | Notes |
|---|---|---|---|---|---|
| Exact part number, revision, and lifecycle | Gate | Vendor datasheet, ordering code, lifecycle statement, EVB identity. | TBD(datasheet) | [ ] Pass [ ] Fail | Confirm sample and production ordering codes match. |
| RAT and band support, China Mobile focus | Gate | Official RAT/band table and operator support note. | TBD(datasheet) | [ ] Pass [ ] Fail | Must cover intended China Mobile deployment; exact band floor is TBD(founder) if carrier strategy changes. |
| China certification path | Gate | SRRC, Network Access License / 进网许可, carrier IoT requirement status, CCC applicability note. | TBD(datasheet) | [ ] Pass [ ] Fail | Record which certifications are carried by the module versus required at final SKU. |
| Data transport and weak-network recovery | Gate | AT/SDK docs, reconnect behavior, field-test plan, error reporting. | TBD(datasheet) | [ ] Pass [ ] Fail | Must support event upload and heartbeat reliability. |
| GNSS integration strategy | Gate plus score | Integrated/external GNSS decision data, constellations, cold TTFF, warm TTFF, sensitivity, antenna requirements, and current draw. | TBD(datasheet) | Score 0-3 | Integrated GNSS is not automatically better; power and antenna coupling decide. |
| Low-power states | Gate plus score | PSM/eDRX or equivalent modes, sleep current, wake latency, network retention behavior, measured EVB current. | TBD(datasheet) | Score 0-3 | Must be compatible with 48-hour guard profile. |
| AT command and SDK maturity | Score; gate if documentation is unusable | AT manual, SDK, examples, diagnostics, recovery commands, offline install evidence. | TBD(datasheet) | Score 0-3 | Prefer mature logs and deterministic failure recovery. |
| Voice capability | Conditional gate plus score | VoLTE/SMS/voice docs, carrier requirement notes, audio interface options. | V1 voice decision: TBD(founder); module capability: TBD(datasheet). | [ ] Pass [ ] Fail [ ] N/A | If founder approves voice as V1 launch scope, lack of voice path is disqualifying. |
| Voice audio and microphone routing impact | Gate | PCM/I2S/analog audio interface docs, mic/speaker routing diagram, echo/noise constraints, MCU handoff behavior. | TBD(datasheet) | [ ] Pass [ ] Fail | Must not block microphone capture needed by the companion interaction loop. |
| Module unit cost and full BOM impact | Score; gate against approved ceiling | Quote at sample, 1k, 10k, and 50k if available; total system BOM delta. | TBD(quote); ceiling TBD(founder). | Score 0-3 | Do not commit confidential supplier pricing. |
| MOQ, lead time, allocation, PCN/EOL | Score; gate if sourcing cannot support EVT/DVT | Channel quote, authorized distributor response, lifecycle statement. | TBD(quote) | Score 0-3 | Founder MOQ and lead-time tolerance: TBD(founder). |
| Module-carried certification | Score | Certificate list, certificate regions, expiration, final-SKU limitations. | TBD(datasheet) | Score 0-3 | Carried certification reduces but does not eliminate final SKU work. |
| FAE and vendor support | Score; gate if no recovery path | FAE contact, escalation SLA, China support path, errata access. | TBD(vendor) | Score 0-3 | Weak support increases bring-up and certification risk. |

### 5.3 Module Candidate Summary

| Candidate | Role | RAT/bands | GNSS | Power states | AT/SDK maturity | Voice and microphone path | Cost, MOQ, lead time | Certification status | FAE/support | Decision notes |
|---|---|---|---|---|---|---|---|---|---|---|
| SIM7670G | Development comparison baseline only; current connectivity-node test module, not production-selected. | 4G module in current development context; exact RAT/band table TBD(datasheet). | Current context says SIM7670G is used for 4G data, GNSS, and development-link testing; constellations and TTFF TBD(datasheet). | Low-power modes and currents TBD(datasheet) and measurement. | Development link is in use; production AT/SDK maturity unverified. | Voice capability and mic routing unverified; V1 voice decision TBD(founder). | No production quote in current context: TBD(quote); founder ceiling TBD(founder). | Not accepted as final SKU; carried certifications TBD(datasheet/vendor). | TBD(vendor). | Baseline for comparison only. |
| China Mobile candidate module | Pending business contact; production candidate cannot be evaluated until documents arrive. | TBD(datasheet). | TBD(datasheet). | TBD(datasheet). | TBD(datasheet). | TBD(datasheet) plus V1 voice decision TBD(founder). | TBD(quote); founder ceiling and MOQ tolerance TBD(founder). | TBD(datasheet/vendor). | TBD(vendor). | Awaiting datasheet and quote. |

## 6. MCU Evaluation Checklist

### 6.1 Decision Rule

An MCU must pass every disqualifying gate before cost or convenience can decide
selection. On-device AI inference budget is a first-class gate, not a later
optimization. Final MCU selection requires an ADR informed by channel quotes and
the V1-M3 model footprint assessment.

Disqualifying gates:

- Active, sleep, wake, and guard-mode power can plausibly support the 48-hour
  guard profile and can be measured on the evaluation board.
- MotionNet-class local inference has RAM/flash headroom, acceptable latency,
  and a measured sleep-vs-inference energy profile. Exact budgets are
  TBD(MODEL-001).
- The MCU provides a credible optimized inference path: vector, DSP, NPU, or
  vendor/standard optimized kernels sufficient for the measured model.
- Required peripherals are available for IMU, cellular module, display/touch,
  battery telemetry, SOS, storage if needed, camera if retained, and the
  microphone path.
- The microphone path can support the companion interaction loop under the
  intended wearing form.
- Toolchain, debug, production flashing, recovery, and OTA path are viable.
- Unit price, 1k price, MOQ, lead time, lifecycle, and second-source risk are
  known enough for founder approval.

Scored criteria after gates pass:

- Lower active/sleep/inference energy at equal functionality.
- Larger practical RAM/flash margin after model, buffers, OTA, logs, and app
  code are included.
- Better audio, camera, power-measurement, and production-debug support.
- Lower firmware portability cost from the current ESP32-S3 development base.
- Lower BOM impact, stronger supply continuity, and stronger local FAE support.

### 6.2 Fillable MCU Checklist

| Criterion | Role | Required evidence | Candidate value | Pass/score | Notes |
|---|---|---|---|---|---|
| Exact MCU, package, memory, and lifecycle | Gate | Datasheet, ordering code, silicon revision, lifecycle/PCN/EOL statement. | TBD(datasheet) | [ ] Pass [ ] Fail | Sample and production ordering codes must be separated. |
| Active and sleep power | Gate plus score | Active current, deep sleep/standby current, wake time, RTC/SOS/IMU wake behavior, measured EVB current. | TBD(datasheet) and measurement | Score 0-3 | Must support 48-hour guard-mode budget at system level. |
| Sleep-vs-inference power | Gate plus score | Single MotionNet inference energy, AudioGate 1-minute current if enabled, wake-to-infer latency, model version. | TBD(MODEL-001) | Score 0-3 | First-class ADR-0002 criterion. |
| RAM headroom for on-device AI | Gate | Peak RAM for MotionNet-class model, AudioGate if enabled, sensor buffers, protocol buffers, logs, OTA, and app runtime. | Budget TBD(MODEL-001) | [ ] Pass [ ] Fail | Do not count unavailable or unstable memory as production headroom. |
| Flash headroom for on-device AI | Gate | Firmware image size, model weights, rollback/OTA slots, logs/config, filesystem needs. | Budget TBD(MODEL-001) | [ ] Pass [ ] Fail | Final margin target is TBD(founder) if feature set changes. |
| Vector, DSP, NPU, or optimized kernel support | Gate plus score | Vendor NN library, CMSIS-NN/TFLite Micro support, vector/DSP/NPU docs, benchmark logs. | TBD(datasheet) and benchmark | Score 0-3 | NPU is not mandatory if measured performance and power pass. |
| IMU and sensor peripherals | Gate | I2C/SPI, interrupt wake, FIFO/DRDY support, timestamping capability. | TBD(datasheet) | [ ] Pass [ ] Fail | Required for MotionNet data quality. |
| Cellular-module interface | Gate | UART/USB/SPI availability as required by module, flow control, power control GPIOs, wake pins. | TBD(datasheet) | [ ] Pass [ ] Fail | Must support selected module recovery and low-power transitions. |
| Microphone path | Gate | PDM/I2S/ADC/codec path, DMA, low-power audio gate support, mic bias/power control, acoustic placement constraints. | Product mic target TBD(founder); MCU capability TBD(datasheet). | [ ] Pass [ ] Fail | Required for the companion interaction loop per ADR-0002. |
| Display, touch, speaker, and SOS interaction | Gate | Display/touch interface, GPIO, PWM/I2S/audio output, interrupt wake. | TBD(datasheet) | [ ] Pass [ ] Fail | Interaction loop must work without LTE. |
| Camera interface if retained | Conditional gate | DVP/MIPI/SPI camera path, DMA, memory bandwidth, power control. | Camera retention decision TBD(founder); capability TBD(datasheet). | [ ] Pass [ ] Fail [ ] N/A | V1 plan says no camera-based features unless founder requires them. |
| Battery and power telemetry | Gate | ADC/fuel-gauge interface, charger status input, reset reason, GPIO measurement markers. | TBD(datasheet) | [ ] Pass [ ] Fail | Needed for power evidence and device-health alerts. |
| Toolchain and production workflow | Gate plus score | SDK, compiler, debugger, flashing, secure boot, OTA/recovery, CI feasibility, offline install. | TBD(datasheet) and evaluation | Score 0-3 | Production bring-up risk matters as much as benchmark speed. |
| Firmware portability cost from ESP32-S3 | Score; gate if impractical | Driver delta, RTOS/runtime delta, model runtime delta, board support work estimate. | TBD(engineering) | Score 0-3 | Current ESP32-S3 work remains the development baseline. |
| Unit price, 1k price, MOQ, lead time | Score; gate against approved ceiling | Authorized-channel quote, sample price, 1k price, MOQ, lead time, allocation note. | TBD(quote); ceiling TBD(founder). | Score 0-3 | No selection without channel quotes. |
| Second-source and supply risk | Score; gate if unacceptable | Alternate package/vendor path, lifecycle, PCN/EOL policy, China availability, FAE path. | TBD(vendor) | Score 0-3 | Founder tolerance for single-source risk: TBD(founder). |

### 6.3 MCU Candidate Summary

| Candidate | Current role | AI inference budget status | Power status | Peripheral and microphone status | Toolchain and portability | Cost and sourcing | Decision notes |
|---|---|---|---|---|---|---|---|
| ESP32-S3 | Current P0 development and cost baseline. | Current context says it can carry MotionNet, rules ContextRouter, small AudioGate, and simple event-triggered VisionGate; production sufficiency remains unverified until TBD(MODEL-001). | Active/sleep and inference power require measurement. | Current wearable board has IMU, display/touch, speaker, and dual microphones; final production microphone and module interfaces remain unverified. | Lowest portability cost because current firmware base is ESP32-S3. | Channel quote, 1k price, MOQ, and lead time TBD(quote); founder ceiling TBD(founder). | Baseline, not selected. |
| STM32U5A5 | Engineering implementation candidate. | Candidate for larger SRAM, camera/audio interfaces, low power, safety, and mature tooling; model benchmark TBD(MODEL-001). | Active/sleep and inference power require board measurement. | Context identifies camera and audio interface strength; exact mic path TBD(datasheet). | Not current firmware target; portability cost from ESP32-S3 TBD(engineering). | Channel quote, 1k price, MOQ, and lead time TBD(quote); founder ceiling TBD(founder). | Candidate, not selected. |
| Apollo4 Blue Lite/Plus | Ultra-low-power candidate. | Context says Apollo4 has no independent NPU but can run current micro-models; benchmark TBD(MODEL-001). | Intended to test wearable always-on sensing energy ceiling; measurement required. | Camera path is less convenient than STM32U5/ESP32; microphone path TBD(datasheet). | Portability cost from ESP32-S3 TBD(engineering). | Channel quote, 1k price, MOQ, lead time, FAE, and lifecycle TBD(quote)/TBD(vendor); founder ceiling TBD(founder). | Candidate, not selected. |

## 7. Open Items

- Awaiting China Mobile 4G module datasheet and official EVB/module identity.
- Awaiting cellular module quote, MOQ, lead time, certification status, and FAE
  path.
- Awaiting MCU channel quotes for ESP32-S3, STM32U5A5, and Apollo4.
- Awaiting MODEL-001 model footprint assessment for RAM, flash, latency, and
  power budgets on ESP32-S3 and candidate production MCUs.
- Awaiting founder confirmation for BOM ceiling, acceptable MOQ/lead time,
  product form, size and weight envelope, IP and temperature targets, usage
  cadences, V1 voice scope, microphone/listen policy, privacy retention, and
  launch claim wording.
- Awaiting final microphone/interaction hardware decision required by ADR-0002.

## 8. Evidence Required Before Selection ADRs

Before any module or MCU ADR is written, attach evidence for:

- Official datasheets and ordering codes.
- Authorized channel quote summaries without confidential price disclosure in
  the repository.
- Power measurements for guard, low-power, GNSS, LTE, audio, and inference
  states.
- Model footprint logs for RAM, flash, latency, and per-inference energy.
- Certification applicability matrix for the final China-market SKU.
- Microphone path validation under the intended wearing form.
