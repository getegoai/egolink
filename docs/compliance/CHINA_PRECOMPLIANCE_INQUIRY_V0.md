---
document_status: draft_not_sent
last_verified: 2026-08-23
verified_by: codex
source_task: COMPLIANCE-010
concept_id: egolink-p0-architecture-20260823
---

# EgoLink China Pre-Compliance Inquiry v0

## Status and Use

`NOT_SENT`. This is a bounded draft for founder authorization and a named
qualified China laboratory or product-classification consultant. It is not a
legal conclusion, certification application, purchase request or product
claim. Private contact details, quotations and credentials stay outside the
repository.

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
- Voice: microphone/speaker full-duplex Ego Call over LTE data to a controlled
  RTC service and Guardian App. No PSTN/SIP gateway, SMS emergency dispatch or
  public emergency-service integration in the first launch.
- Native VoLTE: hardware migration reserve only, not a first-launch feature or
  claim. Please identify whether merely retaining a capable module/interface
  changes classification or test scope.
- Interaction: physical SOS key, local light/haptic/audio feedback and USB-C
  charging/service.
- Sensors: GNSS and six-axis IMU required. Camera is outside the launch SKU
  baseline; please state the delta if a later authorized single-still camera
  option is added.
- Data: location, device state, SOS events and RTC session state are sent to a
  Guardian service. Continuous raw audio/image recording is disabled by
  default; ordinary call media is not retained by default.
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
9. whether LTE-data RTC voice versus a native VoLTE reserve changes any item;
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
