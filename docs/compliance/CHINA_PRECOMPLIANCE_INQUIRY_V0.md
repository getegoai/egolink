---
document_status: draft_not_sent
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
source_task: COMPLIANCE-010
concept_id: egolink-p0-native-cellular-local-first-20260922
---

# EgoLink China Pre-Compliance Inquiry v0

## Status and Use

`NOT_SENT`. This is a bounded draft for founder authorization and a named
qualified China laboratory or product-classification consultant. It is not a
legal conclusion, certification application, purchase request or product
claim. Private contact details, quotations and credentials stay outside the
repository.

This draft incorporates
[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md):
native cellular primary, optional RTC, a private Base endpoint and bounded
cloud relay. It replaces this draft's old RTC-primary/native-reserve concept;
no inquiry has been sent and no qualified opinion is implied.

The inquiry intentionally starts before final BOM/PCB freeze. Please answer
conditionally where applicability depends on an exact modem, antenna,
enclosure, charger, carry form, applicant or sales channel, and list the input
needed to close each condition.

## Concept Submitted for Classification

- Market: mainland China first launch.
- Product: screenless, battery-powered, body-carried safety locator and
  bidirectional voice device for children and older adults; adult use is
  compatible. Exact launch carry form is pending founder selection.
- Required P0 loop: Reliable Location + Ego Call + physical SOS.
- Radios: Cat.1 LTE data and GNSS are required. Wi-Fi/BLE are optional reserves
  and must be assessed both absent and present until A0 decides.
- Voice: native cellular dialing and answering with complete microphone/speaker
  full-duplex audio to authorized ordinary phone contacts. Exact supported
  voice mode (including VoLTE where supported), firmware, SIM and operator
  remain unverified; no CS fallback is assumed. LTE-data RTC to a Guardian App
  is optional. No self-operated public PSTN/SIP gateway, SMS emergency dispatch
  or public emergency-service integration is included in the first launch.
- Interaction: physical SOS key, local light/haptic/audio feedback and USB-C
  charging/service.
- Sensors: GNSS and six-axis IMU required. Product Camera population is not
  frozen; please assess the concept without Camera and state the delta for an
  authorized single-still option. Current development capture is not a product
  SKU selection or continuous-recording feature.
- Data: authorized location, device state, SOS and call outcome/context may be
  viewed by Guardian roles. The product target is a user-controlled private
  Base endpoint, with cloud reachability/signaling/relay and purpose-, access-,
  quota- and time-bounded temporary storage. Current VPS engineering collection
  is not a product local-first or encryption claim. Ordinary call media and
  raw audio/image persistence are off by default; exceptional capture requires
  purpose/event policy, consent, retention and deletion/withdrawal controls.
- Architecture maturity: HW-020 interface baseline only. Exact MCU, modem,
  antennas, battery/charger, enclosure, applicant and manufacturer are not yet
  frozen.

## Written Opinion Requested

For the concept above, please provide applicability, rationale, dependencies,
required documents/samples and recommended decision timing for:

1. SRRC/model approval for the final radio combination and antenna/enclosure;
2. telecom network access / product classification and carrier onboarding;
3. CCC applicability for device, battery, charger and package configuration;
4. SAR or other human RF/EM exposure assessment for each intended carry form;
5. lithium battery, charging, USB-C, transport, thermal and electrical safety;
6. child-oriented wearable/product standards, labeling and age-related duties;
7. ingress/waterproof claims and their interaction with acoustic openings;
8. app/account/location/audio privacy, guardian/minor roles, consent, deletion
   and cybersecurity obligations that should affect A0 architecture;
9. obligations of native cellular primary voice and the deltas of optional
   LTE-data RTC, including exact firmware/operator and audio-path assumptions;
10. deltas caused by adding Wi-Fi/BLE or a later event-still camera.

Please separate module-carried evidence from final-device obligations and state
which changes force re-test: module/SKU/firmware, antenna, PCB, enclosure,
battery/charger, applicant/manufacturer, channel, intended user or carry form.

## Response Evidence Format

Each conclusion should record organization, responsible role, response date,
document/version, concept/configuration scope, source basis, conclusion,
conditions, unresolved inputs, required samples/documents, estimated sequence
and retest triggers. Mark unanswered items `unknown`; do not infer a final SKU
from the development SIM7670G board.

## Minimum Founder Authorization Inputs

The inquiry can be sent without a final BOM after these minimum values are
confirmed outside or in the founder decision sheet:

- authorized recipient/lab and permission to send this concept;
- intended initial carry form(s): wrist, pendant, clip or hybrid;
- expected sales/channel and whether a carrier/ODM partner is assumed;
- intended certificate applicant/manufacturer model and charger-in-box choice;
- whether Wi-Fi/BLE are assessed as an A0 option or excluded from the first
  classification quote.

All other unknowns may remain explicit conditional questions. Authorization to
send this inquiry does not authorize certification submission, contracting,
payment, procurement or disclosure of confidential design files.
