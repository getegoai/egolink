---
document_status: authoritative
last_verified: 2026-06-28
verified_by: codex
---

# Ego Adaptive Location Engine

Ego Adaptive Location Engine (EALE) is the P0 location direction after the
USB-Free Message Hub path and firmware-side SIM7670G real GNSS fix were proven.

EALE is not "wait for GPS". It is:

```text
low-power observation
-> bounded GNSS calibration pulse
-> location belief
-> field memory
-> explainable safety state
```

## Principles

- GNSS is a high-cost calibrator, not a permanent blocking dependency.
- No-fix is valid telemetry when it includes state, attempt budget, and reason.
- Location is represented as a belief with radius, confidence, source, and
  reason, not only a coordinate pair.
- Cell, Wi-Fi, IMU, power, and transport context are product data assets.
- Personal location memory is built from observed field evidence, not from
  unlabelled assumptions.

## P0 Location States

| State | Meaning |
|---|---|
| `Fine` | GNSS or equivalent high-confidence fix. |
| `Coarse` | Cell, Wi-Fi, or known-place estimate with bounded uncertainty. |
| `Predicted` | Last-known or route/motion-based estimate with decaying confidence. |
| `Unknown` | Not enough evidence; do not output fake coordinates. |

## Location Observation Shape

`LOC-002` should add either `event_type=location_observation` or compatible
additive fields on an existing location event. The transport envelope remains
`egolink.p0.v1`.

Recommended payload groups:

- `transport`: current path, RTT, and last transport error.
- `gnss`: enabled state, fix state, quality, attempt duration, result.
- `cell`: LTE RAT, operator, MCC/MNC, TAC, cell ID, and signal quality.
- `wifi`: scan state and privacy-preserving AP fingerprints.
- `imu`: stationary/moving/running/vehicle state and confidence.
- `power`: battery voltage, state-of-charge estimate, charging state, source.
- `location_belief`: state, radius, confidence, sources, and reason.

Exact user coordinates and Wi-Fi fingerprints must stay inside bounded evidence
or explicitly privacy-reviewed data stores. Current docs should describe the
evidence shape without copying private coordinates.

## P0 Rule Engine

Start with rules, not a complex model:

- GNSS fix with acceptable quality -> `Fine`.
- No GNSS but cell or Wi-Fi matches a known place -> `Coarse`.
- Stationary device with stable fingerprint -> keep last-known and decay
  confidence.
- Moving device with changing fingerprint -> lower confidence and request a
  bounded GNSS pulse.
- Known GNSS-bad zone -> reduce GNSS attempt duration or trigger less often.

## Data Assets

Future VPS tables should be introduced by task, not all at once:

- `location_observations`
- `gnss_attempts`
- `cell_fingerprints`
- `wifi_fingerprints`
- `known_places`
- `gnss_bad_zones`
- `route_segments`
- `location_beliefs`

## Near-Term Tasks

1. `OBS-001`: expose observability fields in state and test-run export.
2. `LOC-002`: add multi-source `location_observation` contract.
3. `STAB-001`: run the short USB-Free baseline stability gate using the
   observability and location-observation views.
4. `LTE-001`: expose SIM7670G LTE registration and cell state.
5. `LOC-003`: persist location memory tables on the VPS.
6. `LOC-004`: implement the rule-based belief engine.

## LOC-002 Baseline

LOC-002 establishes the first `location_observation` server/simulator
baseline:

- `event_type=location_observation` is accepted under `egolink.p0.v1`.
- PC Simulator can upload mock GNSS, cell, Wi-Fi, IMU, power, and
  `location_belief`.
- Message Hub treats both `location_report` and `location_observation` as
  location evidence.
- Dashboard can display location state, belief confidence/radius, belief
  source, belief reason, Wi-Fi AP count, and IMU motion.

Boundary: LOC-002 does not prove firmware-side cell fingerprint collection,
real Wi-Fi scanning, real IMU fusion, battery accuracy, location-memory tables,
or a rule engine. Those remain later tasks.

EALE does not replace the existing `request_location -> location_report -> ACK`
loop. It extends it into an explainable location system.
