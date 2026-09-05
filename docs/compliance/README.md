---
document_status: working_evidence_intake
last_verified: 2026-08-23
verified_by: codex
source_task: COMPLIANCE-010
supersedes_task: PROD-002
---

# China Pre-Compliance Evidence Intake

This directory is the evidence intake for a qualified China-market product
classification/pre-compliance opinion. It contains no legal conclusion and no
claim that SRRC, network access, CCC, SAR, child-product, privacy, battery,
charger, or radio requirements have been satisfied.

## Required External Response

The named lab/consultant response must record:

- organization, contact role, response date, scope, and document/version;
- exact product description: screenless wearable EgoCore, LTE data, GNSS,
  Bluetooth/Wi-Fi if retained, Guardian App RTC voice, microphone/speaker,
  SOS, battery/charger, intended users and carry form;
- product classification and applicability rationale for SRRC, network access
  / 进网许可, CCC, SAR/RF exposure, battery/charger transport and safety,
  child-oriented product questions, app/privacy obligations, and carrier
  onboarding;
- applicant/manufacturer/importer assumptions, required samples, lead-time and
  prerequisite design documents;
- which conclusions depend on final modem, antenna, enclosure, charger,
  channel, applicant, voice route, or intended-user decisions;
- unresolved questions explicitly marked `unknown`.

## Evidence Rules

Every imported statement must carry `source`, `source_date`, `retrieved_date`,
`exact_sku_or_configuration`, and one status: `official`, `professional_opinion`,
`vendor_claim`, `measured`, or `unverified`. Web research may prepare questions
but cannot replace the qualified response or laboratory evidence.

Confidential quotes, personal contact details, credentials, and private device
logs stay outside the repository. A bounded summary may link to the controlled
evidence owner and record a hash/version without copying restricted material.

## Immediate Parallel Work

While the external opinion is pending, engineering continues with reversible
inputs: RTC/LTE duty-cycle assumptions, microphone/speaker routing options,
antenna/RF keep-outs, battery/charger architecture, debug and secure-update
paths, data-retention decisions, and an A0-to-A1 retest matrix. No item becomes
a frozen BOM or compliance claim until its named gate is closed.

`CHINA_PRECOMPLIANCE_INQUIRY_V0.md` is the current concept-bound draft. It is
deliberately conditional so the qualified opinion can start before final BOM,
PCB and enclosure freeze. Its `NOT_SENT` state must not change without founder
authorization; sending it does not authorize contracting or certification.
