---
document_status: worksheet_pending_founder_input
last_verified: 2026-07-03
verified_by: codex
source_task: PROD-001
---

# Mass-Production Founder Decision Sheet

This worksheet collects the founder-owned decisions needed to approve
`MASS_PRODUCTION_REQUIREMENTS.md` and unblock later module/MCU selection ADRs.
It must not contain confidential supplier quotes, private contacts, passwords,
or unreleased vendor terms.

Use this sheet as a fill-in surface. Keep detailed vendor pricing and private
business correspondence outside the repository; record only non-confidential
summaries or decision outcomes here.

## Required Founder Decisions

| Decision | Needed value | Why it matters | Blocks |
|---|---|---|---|
| Launch market and channel | China-market channel, carrier path, whether a carrier partner is assumed. | Certification scope, module bands, data plan, guardian setup, and service ops differ by channel. | Module certification matrix, V1-M4 selection ADRs. |
| Full device BOM ceiling | Target and hard ceiling for full system BOM at 1k, 10k, and 50k tiers. | Module/MCU cannot be judged by chip price alone. | Module/MCU scorecard, EVT BOM freeze. |
| MOQ and lead-time tolerance | Maximum acceptable MOQ, sample lead time, EVT/DVT lead time, and allocation risk. | A technically good part can still be disqualified by sourcing risk. | Procurement gate, supplier shortlist. |
| Battery capacity envelope | Target cell capacity, maximum thickness/volume, charging connector/fixture preference. | Power targets require a real capacity and wearable enclosure envelope. | PWR-001 interpretation, enclosure and battery procurement. |
| Public battery claim wording | Whether 48h guard mode is a public launch claim; whether 7d light-use is internal, stretch, or public. | Engineering can measure several profiles, but product copy decides claim risk. | PWR-001 release wording, V1-M1 exit language. |
| Usage cadence assumptions | Heartbeat interval, location refresh interval, prompts per day, screen-on budget, audio gate duty cycle. | Average current depends on behavior profile, not only hardware. | Power measurements, scheduler budgets, product requirements approval. |
| Wearing form factor | Wrist, pendant, clip, hybrid, or other; target dimensions and maximum weight. | Affects antenna, GNSS, microphone, IMU orientation, SOS reachability, and battery size. | FT-1 assembly, enclosure/GNSS gate, IMU acceptance. |
| Environmental target | IP rating, sweat/rain assumptions, operating/storage temperature range. | Certification and enclosure design need a target before EVT. | EVT requirements, test plan, sourcing. |
| Voice calling scope | No V1 voice, emergency-only voice, guardian callback, or richer voice interaction. | Determines module voice requirements and microphone/audio path priority. | Module checklist, mic decision, interaction hardware. |
| Microphone policy | Mic count, always-listen policy, wake word or push-to-talk, raw audio retention decision. | ADR-0002 requires companion interaction; privacy boundary blocks raw audio by default. | Mic hardware selection, DATA-002 consent rules, model footprint. |
| Camera policy | Exclude camera features for V1, retain hardware only, or enable an explicit feature. | Camera affects privacy, power, MCU interface, enclosure, and certification burden. | MCU checklist, product non-goals, privacy review. |
| Privacy retention policy | Retention windows for exact location, hashed Wi-Fi, IMU windows, user confirmations, and training candidates. | PRIVACY-001 defines default blocks; founder/legal must approve product policy. | DATA-002, guardian MVP, training data use. |
| Consent and deletion UX | Who consents, how guardian/user roles work, deletion/export SLA. | Minor/elder wearable data needs explicit role and deletion rules. | DATA-002, V1-M2 guardian MVP, legal review. |
| AI learning presentation | Whether users see "AI learning progress" or model improvement status. | Product UX can expose or hide the data flywheel. | Guardian MVP copy, DATA-002 user-facing language. |

## Candidate Decision Defaults

These defaults keep engineering moving until founder approval. They are not
final product commitments.

| Topic | Conservative working default |
|---|---|
| Camera | No camera-based V1 feature; retain only as capability evidence unless founder changes scope. |
| Raw audio | Disabled by default; derived audio or raw capture requires explicit consent and separate task. |
| Exact coordinates in docs | Redacted from current docs and generated summaries; bounded evidence/export only. |
| Wi-Fi identifiers | Raw BSSID/SSID retention disabled; hashed fingerprints need salt/rotation and retention rule. |
| Production module | SIM7670G remains development baseline only. |
| Production MCU | No MCU selected until MODEL-001 footprint and channel quotes are available. |
| Battery claim | Measure 24h first; do not claim 48h/7d until representative battery/enclosure/network evidence exists. |

## Approval Checklist

- [ ] Founder filled all required product/business values above.
- [ ] No confidential supplier pricing or private correspondence was added to
      this repository.
- [ ] `MASS_PRODUCTION_REQUIREMENTS.md` was updated where its
      `TBD(founder)` placeholders are now resolved.
- [ ] China Mobile module datasheet or official summary is available for the
      module checklist.
- [ ] MCU channel quote summaries are available outside the repository and
      non-confidential decision outcomes are recorded.
- [ ] Privacy/legal review approved retention, consent, deletion, and audio
      policy before any DATA-002 training use.
- [ ] A later ADR records the selected cellular module and MCU with evidence.

## Open Evidence Paths

Fill these when the evidence exists:

| Evidence | Path or source |
|---|---|
| China Mobile module datasheet summary | TBD(founder/vendor) |
| Cellular module quote summary location | TBD(founder/vendor, non-confidential only) |
| ESP32-S3 quote summary location | TBD(founder/vendor, non-confidential only) |
| STM32U5A5 quote summary location | TBD(founder/vendor, non-confidential only) |
| Apollo4 quote summary location | TBD(founder/vendor, non-confidential only) |
| MODEL-001 footprint report | TBD(MODEL-001) |
| PWR-001 24h battery report | TBD(PWR-001) |
| FIELD-003 outdoor GNSS report | TBD(FIELD-003) |
