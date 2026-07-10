# Tiny Safety Hard-Case Review Packet

- Review set: `MODEL-DEVICE-009-tiny-safety-hardcase-review-20260707`
- Status: `ready_for_synthetic_review`
- Model: `MODEL-DEVICE-001-tiny-safety-v0-20260707` / `0.1.0-synthetic-dry-run`
- Records exported: `24`
- Source hard-case examples: `24`
- Training allowed: `False`

## Priority Reasons

- `low_confidence`: `24`
- `low_margin`: `24`
- `synthetic_oracle_disagreement`: `24`

## First Records

- `stress-i040-f020-s095-d000` oracle `uncertain` predicted `needs_check` confidence `0.304743` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i060-f000-s070-d035` oracle `uncertain` predicted `needs_check` confidence `0.310541` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i000-f040-s070-d070` oracle `uncertain` predicted `needs_check` confidence `0.311487` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i040-f040-s045-d000` oracle `uncertain` predicted `needs_check` confidence `0.310328` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i060-f000-s095-d000` oracle `uncertain` predicted `needs_check` confidence `0.307396` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i060-f020-s020-d035` oracle `uncertain` predicted `needs_check` confidence `0.318919` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i000-f060-s045-d000` oracle `uncertain` predicted `needs_check` confidence `0.310603` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i040-f020-s045-d000` oracle `uncertain` predicted `normal` confidence `0.31999` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i060-f020-s045-d000` oracle `uncertain` predicted `needs_check` confidence `0.315194` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`
- `stress-i020-f060-s000-d000` oracle `uncertain` predicted `normal` confidence `0.315309` reasons `synthetic_oracle_disagreement, low_confidence, low_margin`

## Known Gaps

- Records are synthetic stress cases only and are not reviewed labels.
- Synthetic oracle labels are triage hints, not training targets.
- No field samples, private data, candidate DBs, hardware, or firmware are contacted.
- No real-world accuracy, latency, RAM, flash, power, or release-readiness claim is made.
