---
document_status: authoritative
last_verified: 2026-07-03
verified_by: codex
---

# Product Demo Privacy Boundary

This document defines the engineering privacy boundary for KR-008 product-demo
reports, V1 field-test evidence, and DATA-002 planning. It is not a legal
compliance certification. Founder/legal review owns final policy decisions.

## Default Rule

Product-demo evidence is allowed for engineering review only. It is not
training data by default.

Unless a later task records explicit consent, retention limits, and privacy
review, every product-demo or field-test export must use:

```text
training_allowed=false
raw_audio_allowed=false
raw_image_allowed=false
private coordinates redacted from docs and generated summaries
raw Wi-Fi BSSID retention disabled
```

## Data Classes

| Class | Examples | Default storage | Export/report rule | Training rule |
|---|---|---|---|---|
| GNSS coordinates | Latitude, longitude, error radius, HDOP, TTFF | Bounded evidence/export store only | Current docs and generated summaries may show state, confidence bucket, radius, fix/no-fix, and redacted path refs; exact coordinates require explicit authorization. | `training_allowed=false` until consent and privacy review select the run. |
| Cell/LTE signatures | MCC/MNC, TAC, cell ID, RSRP/RSRQ/RSSI/SINR, PDP state | Structured Message Hub evidence; cell IDs may be hashed for long retention | May be shown as network/area evidence, never as cell-only coordinates. | `training_allowed=false` until consent and review define retention and regional risk. |
| Wi-Fi identifiers | BSSID, SSID, RSSI, AP list | Raw BSSID/SSID retention disabled by default | Product-demo reports may use hashed AP fingerprints only after salt, rotation, and retention rules are recorded. | `training_allowed=false`; hashed fingerprints need explicit consent and retention policy. |
| IMU windows | Motion state, activity label, confidence, bounded raw window refs | Structured windows and feature summaries; raw high-rate windows remain bounded evidence | Reports may show motion state and source status; no personal routine inference claim. | `training_allowed=false` until collection protocol and consent cover the session. |
| User confirmations | `safe`, `needs_help`, `no_response`, annotation labels | Structured event/annotation records | Reports may show outcome counts and evidence refs; private free text is not collected by default. | `training_allowed=false` until label source, consent, and split rules are approved. |
| Audio | Raw microphone clips, derived audio features, voice labels | Raw retention disabled by default | Product-demo reports may only say audio unavailable, mock, or disabled unless a separate task enables capture. | `training_allowed=false`; any future raw or derived audio requires explicit consent and retention limits. |
| Image/camera | Raw images, thumbnails, camera metadata | Raw retention disabled by default | Product-demo reports may only show capability state, source status, or redacted evidence refs unless a separate task enables capture. | `training_allowed=false`; camera data is excluded from current product-demo training. |
| Guardian/contact data | Names, phone numbers, addresses, accounts, relationship labels | Not collected in P0 product-demo reports | Use synthetic or redacted placeholders only. | Not training data. |
| VPS logs and raw frames | HTTP logs, raw LTE frames, parser status, hashes, command/ACK lineage | Runtime stores and bounded reports; secrets redacted | Reports may reference paths, IDs, hashes, parse status, and counts; no bearer tokens, private logs, or payload bytes. | `training_allowed=false` unless converted into a reviewed dataset artifact. |
| Training/export artifacts | DATA-001/002 samples, manifests, model artifacts | Ignored runtime/report directories unless explicitly versioned as small fixtures | Must carry privacy class, redaction state, consent/training flags, lineage, and split rule. | `training_allowed=false` unless every sample is consented, reviewed, and leakage-checked. |

## Product Demo Gate

KR-008 and V1 product-demo reports must include a privacy gate result. The gate
passes only when:

- raw audio and raw image retention are disabled;
- private coordinates are not copied into current docs or generated summaries;
- raw Wi-Fi BSSID/SSID values are absent;
- hashed Wi-Fi fingerprints, if present, include a recorded hash/salt rotation
  and retention policy before product-demo use;
- guardian/contact data is absent, synthetic, or redacted;
- training use is disabled unless explicit consent and privacy review are
  attached as evidence.

Gate blockers include:

- `raw_audio_retention_enabled`
- `raw_image_retention_enabled`
- `private_coordinates_exported_to_product_demo_summary`
- `raw_wifi_identifier_retained`
- `wifi_hash_policy_missing`
- `training_allowed_without_consent_review`
- `guardian_contact_data_unredacted`
- `runtime_secret_or_payload_exported`

## Follow-On Decisions

Open product decisions for the founder/legal review:

- consent language for family, child, elder, and guardian demos;
- retention limits for exact location and hashed Wi-Fi fingerprints;
- whether any audio-derived feature can enter M1/DATA-002;
- how users can delete location memory and training candidates;
- guardian account/contact data model for V1-M2.
