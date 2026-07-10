# Tiny Safety Synthetic Stress Evaluation

- Model ID: `MODEL-DEVICE-001-tiny-safety-v0-20260707`
- Model version: `0.1.0-synthetic-dry-run`
- Cases: `540`
- Synthetic agreement: `365 / 540`
- Synthetic agreement rate: `0.675926`
- Low-confidence cases: `523`
- Low-margin cases: `331`

## Labeling Priorities

- `uncertain`: disagreements `141`, low confidence `237`, low margin `202`
- `possible_risk`: disagreements `19`, low confidence `37`, low margin `28`
- `needs_check`: disagreements `15`, low confidence `240`, low margin `100`
- `normal`: disagreements `0`, low confidence `9`, low margin `1`

## Hard Case Examples

- `stress-i040-f020-s095-d000` expected `uncertain` predicted `needs_check` confidence `0.304743` margin `0.003113`
- `stress-i060-f000-s095-d000` expected `uncertain` predicted `needs_check` confidence `0.307396` margin `0.006917`
- `stress-i040-f040-s045-d000` expected `uncertain` predicted `needs_check` confidence `0.310328` margin `0.002838`
- `stress-i060-f000-s070-d035` expected `uncertain` predicted `needs_check` confidence `0.310541` margin `0.00131`
- `stress-i000-f060-s045-d000` expected `uncertain` predicted `needs_check` confidence `0.310603` margin `0.009646`
- `stress-i000-f040-s070-d070` expected `uncertain` predicted `needs_check` confidence `0.311487` margin `0.001651`
- `stress-i020-f040-s095-d000` expected `uncertain` predicted `needs_check` confidence `0.312795` margin `0.018017`
- `stress-i060-f000-s095-d035` expected `uncertain` predicted `needs_check` confidence `0.315081` margin `0.021688`
- `stress-i060-f020-s045-d000` expected `uncertain` predicted `needs_check` confidence `0.315194` margin `0.006758`
- `stress-i020-f060-s000-d000` expected `uncertain` predicted `normal` confidence `0.315309` margin `0.007704`

## Known Gaps

- Synthetic oracle agreement is not real-world accuracy.
- No field samples, private data, or candidate DB records are read.
- Low-confidence cases need labeling review before training use.
- Runtime RAM, latency, power, and product readiness are not evaluated.

## Non-Claims

- No real-world fall detection, distress detection, or proactive safety accuracy is claimed.
- No model behavior, thresholds, labels, contracts, or firmware are changed.
- No real SMS, call, dispatch, or external escalation action is enabled.
