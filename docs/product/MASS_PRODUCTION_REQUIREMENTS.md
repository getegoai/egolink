---
document_status: draft_pending_founder_approval
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
source_task: PROD-001
---

## Current Decision Boundary — 2026-09-22

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
partially supersedes ADR-0011/0012's RTC-primary/native-reserve route. The first
commercial loop remains **Reliable Location + Ego Call + SOS**; P0-CALL now
requires supported native cellular dialing/answering and complete two-way
audio. RTC is optional and CALL-020/021 remain paused. The product does not
operate a public PSTN/SIP gateway. Exact voice mode, firmware and operator
coverage require evidence; the old three-operator native-voice gate is not
automatically restored. Existing three-operator LTE-data requirements below
remain in force.

China certification, 48-hour power, RF, acoustic, privacy, manufacturing,
sourcing and evidence requirements remain active. The deterministic local
safety/location kernel and honest rule-state are required; advanced learned
L2/L3, Camera AI and a complete Base AI system are not new launch Gates.
Minimum private Base receiving/storage/replay/lifecycle work proceeds in
parallel, with cloud services limited by a declared relay lifecycle. Present
VPS collection is a bounded engineering transition, not local-first acceptance.

| Capability Gate | Current state |
|---|---|
| `P0-LOC` | `NOT_RUN` |
| `P0-CALL` | `NOT_RUN` |
| `P0-SOS` | `NOT_RUN` |

The device owns minimum operational Location Engine v0/Sensor Policy v0 state;
server fusion is derived evidence/replay. Product selection must support that
split and source event-time lineage. Legacy `G0-EGOCALL` maps to `P0-CALL`.
`COMPLIANCE-010` is the active China pre-compliance successor; PROD-002 is a
retained intake only. Self-operated public PSTN/SIP gateways, SMS emergency
dispatch and public emergency-service integration remain outside this launch.
Native cellular primary is required; Camera and advanced learned fusion remain
separately measured growth paths, with AI work data/replay first.

## 2026-08-14 Product-Direction Rebase

ADR-0008 and [EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md) supersede the
2026-07-12/13 V1 Pro platform, OLED/watch form, no-camera, and no-ordinary-call
selection overrides below. No production MCU, cellular module, final IMU,
audio chain, camera part, power path, battery, PCB outline, or enclosure is
currently frozen for the new EgoLink Core route. The old component tables are
historical evaluation inputs only.

The general gates in this document remain active: measured 48-hour guard
target, full-system BOM and sourcing evidence, China certification mapping,
privacy/consent, model footprint, RF/acoustic/power/ingress validation, and
founder approval of open product values. A new A0 candidate/BOM baseline must
be issued separately before schematic freeze or purchasing.

## Historical 2026-07-13 Selection Override (superseded by ADR-0008)

Founder decision ADR-0005 previously froze the V1 Pro production platform as
`nRF54LM20B + Air780EGH` and the named sensor, audio, storage, display, and
power-path baseline. Statements below that said no MCU or cellular module had
been selected, and the open candidate comparison tables, were retained as the
pre-decision record. ADR-0008 now supersedes that selection; these paragraphs
are history and do not control current procurement.

Founder direction on 2026-07-12 also froze the V1 Pro wrist-worn exterior
envelope, interaction layout, PCB maximum outline and battery bay in
`V1_PRO_FORM_FACTOR_BASELINE.md`. Matching TBD rows below remain historical
inputs where they conflict with that baseline; supplier-specific battery,
antenna tuning, certification and measured gates remain unresolved.

ADR-0006 (2026-07-13) then superseded conflicting ADR-0005 peripheral clauses:
that route was data-first with no ordinary PSTN dialer, targeted a nominal
900 mAh cell, added MAX30101/MAX30208/BMP390 sensing, used a 1.3-inch SH1106G
OLED, and adopted an IP68-oriented USB-C enclosure. ADR-0008 supersedes those
product selections; their evidence discipline remains historical input.

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
acceptable MOQ and lead-time risk, target price bands, Cradle/carry-form and
size/weight envelopes, usage-profile cadence, launch battery claims, controlled
contact/Ego Call policy, privacy-retention policy, and final market/channel
assumptions. The screenless modular core and first-launch Reliable Location +
Ego Call + SOS loop remain fixed, with native cellular primary required by
ADR-0016. Advanced L3 inference and event-camera productization remain
parallel decisions and must not silently become new first-launch blockers.
Use `MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md` as the founder-facing fill-in
surface for those values before replacing placeholders in this requirements
document.

Use other explicit markers for evidence that must come from engineering,
vendors, or later task output:

- TBD(datasheet): awaiting supplier datasheet or official module manual.
- TBD(quote): awaiting channel quote, MOQ, or lead-time response.
- TBD(MODEL-001): awaiting model footprint assessment.
- unverified: not proven in the loaded current context.

## 3. V1 Requirement Matrix

| Requirement area | Target value | Hard floor | Rationale and evidence basis | Founder confirmation |
|---|---|---|---|---|
| Product market | China-market V1 wearable safety companion, led by Reliable Location + Ego Call + SOS and designed to grow into an on-device AI companion. | Do not evaluate overseas SKU requirements in V1 selection. | ADR-0012 freezes the three P0 capability Gates while preserving the longer-term EgoLink intelligence direction. | Final launch channel and operator assumptions: TBD(founder). |
| Full device BOM ceiling | Complete production BOM ceiling at 1k, 10k, and 50k volume tiers: TBD(founder). Include MCU, cellular module, GNSS path, antennas, sensors, audio/camera/interaction parts, battery, charger, PMIC, enclosure, assembly, test, and certification amortization. | No candidate can be selected without a quote path and comparison against the founder-approved full-system BOM ceiling: TBD(founder). | Hardware evaluation plan forbids selecting by chip price alone; full system BOM is the cost gate. | BOM ceiling, acceptable margin model, and confidential price handling: TBD(founder). |
| Typical guard-mode battery life | >= 48 hours measured on representative battery, enclosure, antenna, firmware configuration, and network profile. | 48 hours typical guard mode is the hard target; below 48 hours is a launch blocker unless the founder changes the product requirement. | Product and power documents set 48 hours as the minimum typical safety-guard target. | Battery capacity, heartbeat/location cadence, indicator/audio/camera duty cycle, and normal-signal definition: TBD(founder). |
| Light-use stretch battery life | 7-day light-use stretch target. | 5 days is the lower bound of the current 5-7 day stretch goal; whether 7 days is a hard launch gate is TBD(founder). | Power target document defines 5-7 days as the advanced light-use objective; task packet asks for a 7-day stretch definition. | Final light-use claim wording and allowed daily interaction budget: TBD(founder). |
| Emergency and weak-signal battery behavior | Emergency, high-frequency location, sustained voice, camera use, and weak-signal retry are measured separately and not allowed to borrow the 48-hour or 7-day claim. | Do not claim guard-mode or light-use battery life for emergency or weak-signal scenarios unless measured separately. | Power document says emergency, high-frequency location, calls, and weak signal do not promise the same endurance. | Which emergency-use claim, if any, appears in product copy: TBD(founder). |
| Size and weight envelope | Target dimensions, thickness, mass, battery capacity, and enclosure volume: TBD(founder). | Maximum wearable envelope and maximum mass: TBD(founder). No final PCB/module/battery choice should exceed the founder-approved envelope. | Wearability, child/elder comfort, antenna clearance, battery size, and microphone acoustics constrain the production design. | Target form-factor envelope and comfort threshold: TBD(founder). |
| Cradle and carry form | EgoCore remains the fixed modular core; Cradle/carry variants such as wrist, pendant, clip or hybrid remain TBD(founder). Each must keep SOS reachable, IMU orientation controlled, microphone inlet exposed, antenna/GNSS path viable and charging usable. | No Cradle passes if it blocks SOS access, prevents interpretable IMU orientation, covers microphone input or makes LTE/GNSS antenna placement unworkable. | The modular product direction is fixed, while each carry interface still needs mechanical, RF, acoustic and usability evidence. | Launch Cradle set, attachment method, removal alert requirement and charging ergonomics: TBD(founder). |
| Environmental rating | Target ingress rating and operating/storage temperature range: TBD(founder). | Minimum IP rating and temperature floor/ceiling: TBD(founder). No environmental claim may be made before test evidence exists. | Daily safety wear needs sweat/rain/dust and seasonal temperature resilience; current context does not freeze values. | IP rating, sweat/rain exposure assumptions, temperature range, and test standard choice: TBD(founder). |
| China certification set | Plan for SRRC, China Network Access License / 进网许可, carrier IoT requirements, and CCC if applicable. Battery, charger, and radio certification obligations must be mapped before EVT freeze. | No pilot-production release without an applicability matrix and evidence that the selected module/SKU can complete required China certifications. | Task packet requires China market certification coverage; final applicability depends on SKU and sales channel. | Sales channel, charger-in-box decision, carrier cooperation path, and regulatory counsel owner: TBD(founder). |
| Data privacy baseline for minor/elder wearable | Consent-first data handling, guardian/user role model, privacy class on every session, data minimization, encrypted transport/storage where applicable, and no private real user logs committed to the repo. Retention windows: TBD(founder). | No data flywheel, audio capture, guardian sharing, or model-training export without explicit consent and privacy classification. Continuous raw audio upload must not be default. | ADR-0002 requires consented, privacy-classed sessions for the data flywheel; minor/elder wearable context raises privacy risk. | Consent flow, data retention, deletion/export SLA, guardian access rules, and audio retention policy: TBD(founder). |
| Local decision and AI growth budget | First-launch hardware must run Location Engine v0, Sensor Policy v0 and the deterministic Safety Kernel, while leaving a measurable growth path for MotionNet/context candidates. RAM, flash, latency, and per-inference energy budgets: TBD(MODEL-001). | The operational location/Safety Kernel must work locally and degrade honestly without LTE. Advanced MotionNet/vector/NPU fit is scored and measured, but is not a first-launch disqualifier unless a later ADR promotes it. | ADR-0012 separates the device operational kernel from non-blocking L2/L3 data/replay work without abandoning long-term intelligence. | Feature mix that drives model size, always-on audio policy, and acceptable latency/power tradeoff: TBD(founder). |
| Microphone and interaction path | The screenless product must include a validated Ego Call microphone/speaker path plus button, haptic and status-light interaction. An AI audio path is measured growth capacity, not a Sprint 1 Gate. Mic count, acoustic placement, codec/interface, and voice UX remain engineering decisions. | No EVT hardware freeze without microphone/audio routing and evidence for SOS, call, local feedback, failure and privacy flows in the intended carry forms. AI wake/listen or AudioGate capability cannot disqualify an otherwise acceptable P0 unless a later ADR promotes it. | ADR-0012 makes real P0 call/SOS interaction mandatory while moving advanced AI audio to non-blocking data/replay work; exact wire enums remain owned by `shared/contracts` and require explicit adapters. | Mic count, wake/listen policy, acoustic limits and accessibility acceptance: TBD(founder/engineering). |

## 4. Usage Profile Definitions

Battery claims must be measured against named profiles. These definitions are
fillable because exact cadences are founder/product decisions.

| Profile | Included behavior | Excluded behavior | Values still to fill |
|---|---|---|---|
| Typical guard mode | Physical SOS wake source enabled; low-power IMU sensing; Ego Call audio path idle/power-gated but able to enter the declared call setup budget; scheduled heartbeat/location refresh; physical-SOS local feedback/upload; indicators normally off; representative conditions for each target mainland China operator. No proactive check-in or always-listen/AudioGate duty cycle is assumed for P0. | Sustained voice call, camera capture, repeated weak-signal retries, emergency high-rate tracking, developer logging, and bench USB power. | Battery capacity, heartbeat/location intervals, SOS feedback, indicator/haptic/call-audio duty cycles, network-signal floor: TBD(founder). |
| Light-use stretch | Lower-interaction daily use, no emergency escalation, reduced location/heartbeat cadence, minimal indicators/audio, no sustained call or camera use. | Emergency, weak-signal stress, continuous companion conversation, frequent GNSS fixes, and high-rate data capture. | Daily interaction budget, reduced cadence, allowed check-ins, and whether 7 days is a hard public claim: TBD(founder). |
| Emergency mode | SOS flow, high-priority event upload, higher location cadence, guardian alert path, and independent native cellular Ego Call attempt; RTC is optional. Data or storage failure cannot silently block the available primary call. | Not used to support normal 48-hour or 7-day claim. | Emergency duration target, call reachability/latency, contact policy, and location cadence: TBD(founder). |
| Measurement baseline | Representative battery, enclosure, antenna, SIM/operator, firmware image, model version, and environment recorded with raw power evidence. | Development-board USB-powered runs are not production battery evidence. | Production battery capacity and accepted test lab or bench procedure: TBD(founder). |

## 5. Cellular Module Evaluation Checklist

### 5.1 Decision Rule

A cellular module must pass every disqualifying gate before it can be scored.
Scored criteria are used only after all gates pass. Final selection requires an
ADR that records the evidence, tradeoffs, and founder-approved cost thresholds.

Disqualifying gates:

- RAT/band support, certification and LTE-data evidence for all three target
  mainland China operators are documented by official supplier evidence and
  representative testing.
- Data transport, registration, reconnect, and low-power states can support
  the 48-hour guard-mode power budget.
- GNSS strategy is documented: integrated module GNSS or external GNSS, with
  constellation support, cold/warm TTFF, power, antenna, and coexistence data.
- Native cellular dialing/answering, microphone/speaker routing and weak-network
  behavior must support P0-CALL on the exact module/firmware/operator. Missing
  native voice or two-way audio cannot be waived by LTE-data/RTC evidence.
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
| RAT, band and three-operator support | Gate | Official RAT/band table plus exact-SKU China Mobile, China Unicom and China Telecom LTE-data support evidence. | TBD(datasheet/test) | [ ] Pass [ ] Fail | Registration, data reachability and weak-network recovery must be tested per target operator; one operator passing cannot stand in for the other two. |
| China certification path | Gate | SRRC, Network Access License / 进网许可, carrier IoT requirement status, CCC applicability note. | TBD(datasheet) | [ ] Pass [ ] Fail | Record which certifications are carried by the module versus required at final SKU. |
| Data transport and weak-network recovery | Gate | AT/SDK docs, reconnect behavior, field-test plan, error reporting. | TBD(datasheet) | [ ] Pass [ ] Fail | Must support event upload and heartbeat reliability. |
| GNSS integration strategy | Gate plus score | Integrated/external GNSS decision data, constellations, cold TTFF, warm TTFF, sensitivity, antenna requirements, and current draw. | TBD(datasheet) | Score 0-3 | Integrated GNSS is not automatically better; power and antenna coupling decide. |
| Low-power states | Gate plus score | PSM/eDRX or equivalent modes, sleep current, wake latency, network retention behavior, measured EVB current. | TBD(datasheet) | Score 0-3 | Must be compatible with 48-hour guard profile. |
| AT command and SDK maturity | Score; gate if documentation is unusable | AT manual, SDK, examples, diagnostics, recovery commands, offline install evidence. | TBD(datasheet) | Score 0-3 | Prefer mature logs and deterministic failure recovery. |
| Optional RTC data/media capability | Separate optional-path score | LTE data stability, RTC reachability/latency/loss plan, media interface options and recovery behavior. | Optional under ADR-0016; module/system capability TBD(datasheet/test). | Score 0-3 | RTC media stays separate from Message Hub telemetry; paused CALL-020/021 evidence cannot pass native P0-CALL. |
| Native cellular voice | `P0-CALL` support Gate plus score | Exact-SKU voice/AT/audio docs, firmware/SIM/operator coverage, dial/answer/hang-up/cancel and two-way acoustic evidence. | Primary route under ADR-0016; TBD(datasheet/test). | [ ] Pass [ ] Fail; Score 0-3 | CALL-030 feasibility feeds HW-022 and CALL-031 product acceptance. Historical `G0V-VOLTE-RESERVE` is insufficient; no CS fallback or three-operator voice coverage is assumed. |
| Voice audio and microphone routing impact | `P0-CALL` support Gate | PCM/I2S/analog audio interface docs, mic/speaker routing diagram, echo/noise constraints, MCU handoff behavior. | TBD(datasheet) | [ ] Pass [ ] Fail | Must support the measured Ego Call path; AI audio reuse remains a separately scored growth decision. |
| Module unit cost and full BOM impact | Score; gate against approved ceiling | Quote at sample, 1k, 10k, and 50k if available; total system BOM delta. | TBD(quote); ceiling TBD(founder). | Score 0-3 | Do not commit confidential supplier pricing. |
| MOQ, lead time, allocation, PCN/EOL | Score; gate if sourcing cannot support EVT/DVT | Channel quote, authorized distributor response, lifecycle statement. | TBD(quote) | Score 0-3 | Founder MOQ and lead-time tolerance: TBD(founder). |
| Module-carried certification | Score | Certificate list, certificate regions, expiration, final-SKU limitations. | TBD(datasheet) | Score 0-3 | Carried certification reduces but does not eliminate final SKU work. |
| FAE and vendor support | Score; gate if no recovery path | FAE contact, escalation SLA, China support path, errata access. | TBD(vendor) | Score 0-3 | Weak support increases bring-up and certification risk. |

### 5.3 Module Candidate Summary

| Candidate | Role | RAT/bands | GNSS | Power states | AT/SDK maturity | Voice and microphone path | Cost, MOQ, lead time | Certification status | FAE/support | Decision notes |
|---|---|---|---|---|---|---|---|---|---|---|
| SIM7670G | Development comparison baseline only; current connectivity-node test module, not production-selected. | 4G module in current development context; exact RAT/band table TBD(datasheet). | Current context says SIM7670G is used for 4G data, GNSS, and development-link testing; constellations and TTFF TBD(datasheet). | Low-power modes and currents TBD(datasheet) and measurement. | Development link is in use; production AT/SDK maturity unverified. | Native voice, complete two-way audio and product-suitable mic routing remain unverified; LTE-data or initialized AT driver is insufficient. | No production quote in current context: TBD(quote); founder ceiling TBD(founder). | Not accepted as final SKU; carried certifications TBD(datasheet/vendor). | TBD(vendor). | Baseline for comparison only. |
| China operator candidate module | Pending official documents/business contact; production candidate cannot be evaluated until exact SKU/revision data arrive. | TBD(datasheet). | TBD(datasheet). | TBD(datasheet). | TBD(datasheet). | Must support ADR-0016 native P0-CALL and complete audio, with separate reliable LTE-data evidence. | TBD(quote); founder ceiling and MOQ tolerance TBD(founder). | TBD(datasheet/vendor). | TBD(vendor). | Awaiting official datasheet, exact SKU, sample and quote. |

## 6. MCU Evaluation Checklist

### 6.1 Decision Rule

An MCU must pass every disqualifying gate before cost or convenience can decide
selection. Deterministic Safety Kernel execution is a first-launch gate;
advanced inference budget is a first-class scored growth criterion, not an
unconditional first-launch blocker. Final MCU selection requires an ADR
informed by channel quotes and the V1-M3 model footprint assessment.

Disqualifying gates:

- Active, sleep, wake, and guard-mode power can plausibly support the 48-hour
  guard profile and can be measured on the evaluation board.
- The deterministic Safety Kernel and its local state/feedback loop have
  measured RAM/flash/latency/power headroom.
- Required peripherals are available for IMU, cellular module, buttons/status/haptics,
  battery telemetry, SOS, storage, and the microphone path. Camera and advanced
  inference interfaces are evaluated as parallel growth capabilities.
- The microphone/speaker path can support Ego Call, SOS feedback and the
  declared accessibility interaction under the intended wearing form.
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

Advanced inference headroom, optimized kernels and event-camera interfaces
remain important scores and architectural reserves. They may become hard gates
only through a later explicit product/ADR decision with measured evidence.

### 6.2 Fillable MCU Checklist

| Criterion | Role | Required evidence | Candidate value | Pass/score | Notes |
|---|---|---|---|---|---|
| Exact MCU, package, memory, and lifecycle | Gate | Datasheet, ordering code, silicon revision, lifecycle/PCN/EOL statement. | TBD(datasheet) | [ ] Pass [ ] Fail | Sample and production ordering codes must be separated. |
| Active and sleep power | Gate plus score | Active current, deep sleep/standby current, wake time, RTC/SOS/IMU wake behavior, measured EVB current. | TBD(datasheet) and measurement | Score 0-3 | Must support 48-hour guard-mode budget at system level. |
| Sleep-vs-inference power | Growth score | Single MotionNet inference energy, AudioGate 1-minute current if enabled, wake-to-infer latency, model version. | TBD(MODEL-001) | Score 0-3 | First-class long-term criterion; measured Safety Kernel power remains a launch gate. |
| RAM headroom for on-device AI | Growth score | Peak RAM for MotionNet-class model, AudioGate if enabled, sensor buffers, protocol buffers, logs, OTA, and app runtime. | Budget TBD(MODEL-001) | Score 0-3 | Do not count unavailable or unstable memory as production headroom; Safety Kernel RAM remains a gate. |
| Flash headroom for on-device AI | Growth score | Firmware image size, model weights, rollback/OTA slots, logs/config, filesystem needs. | Budget TBD(MODEL-001) | Score 0-3 | Final margin target is TBD(founder) if feature set changes; Safety Kernel and recovery space remain gates. |
| Vector, DSP, NPU, or optimized kernel support | Growth score | Vendor NN library, CMSIS-NN/TFLite Micro support, vector/DSP/NPU docs, benchmark logs. | TBD(datasheet) and benchmark | Score 0-3 | NPU is not mandatory; promote this to a gate only with an explicit later ADR. |
| IMU and sensor peripherals | Gate | I2C/SPI, interrupt wake, FIFO/DRDY support, timestamping capability. | TBD(datasheet) | [ ] Pass [ ] Fail | Required first for P0 mobility evidence and Sensor Policy power/location control; learned mobility is later growth. |
| Cellular-module interface | Gate | UART/USB/SPI availability as required by module, flow control, power control GPIOs, wake pins. | TBD(datasheet) | [ ] Pass [ ] Fail | Must support selected module recovery and low-power transitions. |
| Microphone path | `P0-CALL` support Gate plus AI growth score | PDM/I2S/ADC/codec path, DMA, mic bias/power control and acoustic placement constraints; separately measure low-power AudioGate support. | Product mic target TBD(founder); MCU capability TBD(datasheet). | [ ] Call path Pass [ ] Fail; AI score 0-3 | Ego Call support is mandatory under ADR-0012; AI audio inference is non-blocking growth evidence. |
| Screenless interaction, speaker, haptic and SOS | Gate | GPIO/interrupt wake, PWM/I2S/audio output, status-light and haptic control, privacy power controls. | TBD(datasheet/UX test) | [ ] Pass [ ] Fail | Physical SOS, answer/hang-up/cancel, call state and local feedback must work without a screen and degrade honestly without LTE; proactive check-in outcome enums are later scope. |
| Event-camera interface | Growth score; future gate only if promoted by ADR | DVP/MIPI/SPI camera path, DMA, memory bandwidth, hard power control and privacy-visible state. | Optional experimental/L3 capability under ADR-0012; exact camera TBD(datasheet/test). | Score 0-3 | Continuous recording and default raw retention remain prohibited; missing camera evidence does not block the first Reliable Location + Ego Call + SOS loop. |
| Battery and power telemetry | Gate | ADC/fuel-gauge interface, charger status input, reset reason, GPIO measurement markers. | TBD(datasheet) | [ ] Pass [ ] Fail | Needed for power evidence and device-health alerts. |
| Toolchain and production workflow | Gate plus score | SDK, compiler, debugger, flashing, secure boot, OTA/recovery, CI feasibility, offline install. | TBD(datasheet) and evaluation | Score 0-3 | Production bring-up risk matters as much as benchmark speed. |
| Firmware portability cost from ESP32-S3 | Score; gate if impractical | Driver delta, RTOS/runtime delta, model runtime delta, board support work estimate. | TBD(engineering) | Score 0-3 | Current ESP32-S3 work remains the development baseline. |
| Unit price, 1k price, MOQ, lead time | Score; gate against approved ceiling | Authorized-channel quote, sample price, 1k price, MOQ, lead time, allocation note. | TBD(quote); ceiling TBD(founder). | Score 0-3 | No selection without channel quotes. |
| Second-source and supply risk | Score; gate if unacceptable | Alternate package/vendor path, lifecycle, PCN/EOL policy, China availability, FAE path. | TBD(vendor) | Score 0-3 | Founder tolerance for single-source risk: TBD(founder). |

### 6.3 MCU Candidate Summary

| Candidate | Current role | AI inference budget status | Power status | Peripheral and microphone status | Toolchain and portability | Cost and sourcing | Decision notes |
|---|---|---|---|---|---|---|---|
| ESP32-S3 | Current P0 development and A0 engineering starting point. | Firmware/toolchain evidence exists, but MotionNet, AudioGate and VisionGate production fit, accuracy, latency, memory and energy remain unverified until model-footprint and hardware benchmarks pass. | Active/sleep and inference power require measurement. | Development assets provide partial IMU/display/speaker/camera evidence; a production dual-microphone path and the complete screenless interaction chain remain unverified. | Lowest portability cost because current firmware base is ESP32-S3. | Channel quote, 1k price, MOQ, and lead time TBD(quote); founder ceiling TBD(founder). | A0 baseline, not production-selected. |
| STM32U5A5 | Engineering implementation candidate. | Candidate for larger SRAM, camera/audio interfaces, low power, safety, and mature tooling; model benchmark TBD(MODEL-001). | Active/sleep and inference power require board measurement. | Context identifies camera and audio interface strength; exact mic path TBD(datasheet). | Not current firmware target; portability cost from ESP32-S3 TBD(engineering). | Channel quote, 1k price, MOQ, and lead time TBD(quote); founder ceiling TBD(founder). | Candidate, not selected. |
| Apollo4 Blue Lite/Plus | Ultra-low-power candidate. | Running the current micro-models within accuracy, latency, memory and energy budgets is an unverified hypothesis pending MODEL-001 and board benchmarks; no sufficiency claim is made. | Intended to test the low-power sensing/inference energy ceiling; measurement required. | Camera and microphone paths remain TBD(datasheet/test). | Portability cost from ESP32-S3 TBD(engineering). | Channel quote, 1k price, MOQ, lead time, FAE, and lifecycle TBD(quote)/TBD(vendor); founder ceiling TBD(founder). | Candidate, not selected. |

## 7. Open Items

- `COMPLIANCE-010` is queued after the HW-020 concept boundary; no qualified
  China applicability opinion or submission is currently recorded. PROD-002
  remains legacy intake only.
- Awaiting the exact candidate modem datasheet, official EVB/module identity,
  and formal evidence plan for China Mobile, China Unicom and China Telecom.
- Awaiting cellular module quote, MOQ, lead time, certification status, and FAE
  path.
- Awaiting MCU channel quotes for ESP32-S3, STM32U5A5, and Apollo4.
- Awaiting MODEL-001 model footprint assessment for RAM, flash, latency, and
  power budgets on ESP32-S3 and candidate production MCUs.
- Awaiting founder confirmation for BOM ceiling, acceptable MOQ/lead time,
  size and weight envelope, IP and temperature targets, usage cadences,
  microphone/listen policy, privacy retention, and launch claim wording. The
  screenless modular form and first-launch Reliable Location + Ego Call + SOS
  loop and native cellular primary are accepted under ADR-0016; implementation
  remains unverified. Exact voice mode and operator coverage require evidence.
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
