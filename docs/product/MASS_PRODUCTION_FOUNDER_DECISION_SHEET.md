---
document_status: worksheet_pending_founder_input
last_verified: 2026-08-23
verified_by: codex
source_task: COMPLIANCE-010
legacy_source_task: PROD-002
---

# Mass-Production Founder Decision Sheet

This worksheet collects the founder-owned decisions needed to approve
`MASS_PRODUCTION_REQUIREMENTS.md` and unblock later module/MCU selection ADRs.
It must not contain confidential supplier quotes, private contacts, passwords,
or unreleased vendor terms.

ADR-0011 fixes the screenless first-launch loop as Reliable Location + Ego Call
+ SOS. ADR-0012 freezes `P0-LOC`, `P0-CALL` and `P0-SOS`; all three are
currently `NOT_RUN`. Ego Call uses LTE data, a controlled RTC service, and the
bound Guardian App. Native VoLTE and event-camera/advanced-awareness paths are
parallel reserves, not first-launch software gates; AI is data/replay first.
This worksheet collects the product, privacy, accessibility, compliance,
sourcing and release parameters needed to decide and implement each path
honestly. `COMPLIANCE-010` is the current owner; PROD-002 is retained as legacy
intake only.

Use this sheet as a fill-in surface. Keep detailed vendor pricing and private
business correspondence outside the repository; record only non-confidential
summaries or decision outcomes here.

## Required Founder Decisions

| Decision | Needed value | Why it matters | Blocks |
|---|---|---|---|
| Launch market and channel | China-market channel, carrier path, whether a carrier partner is assumed. | Certification scope, module bands, data plan, guardian setup, and service ops differ by channel. | Module certification matrix, V1-M4 selection ADRs. |
| Full device BOM ceiling | Target and hard ceiling for full system BOM at 1k, 10k, and 50k tiers. | Module/MCU cannot be judged by chip price alone. | Module/MCU scorecard, EVT BOM freeze. |
| MOQ and lead-time tolerance | Maximum acceptable MOQ, sample lead time, EVT/DVT lead time, and allocation risk. | A technically good part can still be disqualified by sourcing risk. | Procurement gate, supplier shortlist. |
| Battery and charging implementation envelope | Target cell capacity and maximum thickness/volume; capless USB-C implementation, charging fixture, service and wet-port recovery details. The capless USB-C product requirement is already fixed by ADR-0008. | Power targets require a real cell and enclosure envelope without reopening the required connector class. | PWR-001 interpretation, enclosure, battery, USB implementation and production fixture. |
| Public battery claim wording | Whether 48h guard mode is a public launch claim; whether 7d light-use is internal, stretch, or public. | Engineering can measure several profiles, but product copy decides claim risk. | PWR-001 release wording, V1-M1 exit language. |
| Usage cadence assumptions | Heartbeat interval, location refresh interval, prompts per day, status-light/haptic/audio interaction duty cycles, and sensor wake budgets. | Average current depends on behavior profile, not only hardware. | Power measurements, scheduler budgets, product requirements approval. |
| Wearing form factor | Wrist, pendant, clip, hybrid, or other; target dimensions and maximum weight. | Affects antenna, GNSS, microphone, IMU orientation, SOS reachability, and battery size. | FT-1 assembly, enclosure/GNSS gate, IMU acceptance. |
| Environmental target | IP rating, sweat/rain assumptions, operating/storage temperature range. | Certification and enclosure design need a target before EVT. | EVT requirements, test plan, sourcing. |
| Ego Call and guardian policy | Authorized guardians, inbound/outbound rules, Guardian alert/escalation, callback UX, multi-guardian behavior, account recovery, accessibility and weak-network expectations. Sprint 1 excludes PSTN, SMS and public emergency dispatch. | Determines reachability, privacy, Guardian App/RTC scope, audio validation and safety UX. | `P0-CALL` (legacy `G0-EGOCALL`), Guardian App, mic/speaker path, interaction and compliance tests. |
| Native VoLTE reserve policy | Whether and when native VoLTE is promoted from migration reserve to fallback/product capability; allowed contacts, operator scope and acceptance threshold if promoted. | Prevents a useful hardware option from silently becoming either a launch blocker or an unsupported product claim. | `G0V-VOLTE-RESERVE`, modem/audio/RF reserve routing and later release ADR. |
| Microphone policy | Mic count and Ego Call routing; separately decide any always-listen, wake word, push-to-talk or raw-audio policy. | ADR-0012 requires the real call path; AI audio is non-blocking growth, and the privacy boundary blocks raw audio by default. | P0-CALL mic hardware/acoustics; optional AI audio, DATA-002 consent and model footprint remain separate. |
| Event-camera priority and policy | Sprint 1 keeps camera outside the launch-critical SKU path. Decide whether to retain it as a later L3 option; any promotion needs a later accepted ADR plus resolution/FOV, permitted trigger, visible indicator, ring-buffer, persistence/upload, deletion and caregiver rules. | Camera value must be bounded against privacy, power, MCU, enclosure and certification cost without delaying `P0-LOC`/`P0-CALL`/`P0-SOS`. | Camera/interface reserve, optional experimental-still UX, privacy and later release tests. |
| Certificate applicant and manufacturer model | Intended certificate applicant, manufacturer/ODM relationship, sales entity, charger-in-box decision and carrier-cooperation owner. | Applicability, sample ownership, documentation and lead time depend on the exact commercial configuration. | Qualified pre-compliance opinion, China certification plan and A0-to-A1 evidence matrix. |
| Privacy retention policy | Retention windows for exact location, hashed Wi-Fi, IMU windows, user confirmations, and training candidates. | PRIVACY-001 defines default blocks; founder/legal must approve product policy. | DATA-002, guardian MVP, training data use. |
| Consent and deletion UX | Who consents, how guardian/user roles work, deletion/export SLA. | Minor/elder wearable data needs explicit role and deletion rules. | DATA-002, V1-M2 guardian MVP, legal review. |
| AI learning presentation | Whether users see "AI learning progress" or model improvement status. | Product UX can expose or hide the data flywheel. | Guardian MVP copy, DATA-002 user-facing language. |

## Candidate Decision Defaults

These defaults keep engineering moving until founder approval. They are not
final product commitments.

| Topic | Conservative working default |
|---|---|
| Event camera | Optional experimental still only with explicit authorization, event time and trigger reason; no continuous recording, default raw persistence/upload, or P0 decision authority. |
| Raw audio | Disabled by default; derived audio or raw capture requires explicit consent and separate task. |
| Exact coordinates in docs | Redacted from current docs and generated summaries; bounded evidence/export only. |
| Wi-Fi identifiers | Raw BSSID/SSID retention disabled; hashed fingerprints need salt/rotation and retention rule. |
| Production module | SIM7670G remains development baseline only. |
| Production MCU | No MCU selected until MODEL-001 footprint and channel quotes are available. |
| Battery claim | Measure 24h first; do not claim 48h/7d until representative battery/enclosure/network evidence exists. |
| Ego Call | Managed RTC over LTE data with one bound guardian is the minimum engineering route; no PSTN/SIP gateway and no production-provider claim before measured comparison. |
| Native VoLTE | Preserve/evaluate practical module, audio, power and RF options as `G0V-VOLTE-RESERVE`; do not make it a first-launch gate or claim. |

## Approval Checklist

- [ ] Founder filled all required product/business values above.
- [ ] No confidential supplier pricing or private correspondence was added to
      this repository.
- [ ] `MASS_PRODUCTION_REQUIREMENTS.md` was updated where its
      `TBD(founder)` placeholders are now resolved.
- [ ] Exact candidate modem datasheet/EVB identity and a three-operator LTE-data
      evidence plan are available; native VoLTE reserve evidence is tracked
      separately where the exact SKU supports it.
- [ ] MCU channel quote summaries are available outside the repository and
      non-confidential decision outcomes are recorded.
- [ ] Privacy/legal review approved retention, consent, deletion, and audio
      policy before any DATA-002 training use.
- [ ] A later ADR records the selected cellular module and MCU with evidence.

## Open Evidence Paths

Fill these when the evidence exists:

| Evidence | Path or source |
|---|---|
| Exact candidate modem official-document summary and three-operator LTE-data evidence plan | TBD(founder/vendor) |
| Native VoLTE reserve official-document/sample evidence | TBD(founder/vendor) |
| Qualified China pre-compliance/product-classification response | TBD(COMPLIANCE-010/qualified external professional; PROD-002 legacy intake retained) |
| Cellular module quote summary location | TBD(founder/vendor, non-confidential only) |
| ESP32-S3 quote summary location | TBD(founder/vendor, non-confidential only) |
| STM32U5A5 quote summary location | TBD(founder/vendor, non-confidential only) |
| Apollo4 quote summary location | TBD(founder/vendor, non-confidential only) |
| MODEL-001 footprint report | TBD(MODEL-001) |
| PWR-001 24h battery report | TBD(PWR-001) |
| FIELD-003 outdoor GNSS report | TBD(FIELD-003) |
