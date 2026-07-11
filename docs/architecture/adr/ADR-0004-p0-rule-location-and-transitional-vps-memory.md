---
document_status: authoritative
last_verified: 2026-07-11
verified_by: codex
---

# ADR-0004: P0 Rule Location And Transitional VPS Memory

- Status: accepted
- Date: 2026-07-11
- Deciders: founder and codex

## Context

P0 must improve location quality without turning an engineering evidence hub
into the permanent owner of personal location memory. The current EALE-P0
contract already exposes `Fine`, `Coarse`, `Predicted`, and `Unknown`, and the
available field corpus is not yet sufficient to justify a learned location
fusion model.

Cell and Wi-Fi fingerprint lookup, known-place and GNSS-bad-zone discovery,
and location-belief fusion can be implemented with nearest-neighbour lookup,
history statistics, clustering, thresholds, and explainable rules. A learned
model would add calibration and failure-analysis cost before those baselines
have been measured.

Motion state is different. A small IMU classifier can directly inform the
low-power scheduler and bounded GNSS pulse policy, provided that it first
beats a rules baseline on held-out real sessions and passes device resource
and power gates.

## Decision

1. P0 location belief remains rule/statistics based. Do not introduce a
   learned model for cell/Wi-Fi position lookup, known-place recognition,
   GNSS-bad-zone recognition, or `Fine`/`Coarse`/`Predicted`/`Unknown` fusion.
2. The only currently approved learned-model candidate is IMU motion state:
   `stationary`, `walking`, and `vehicle`. It must run in shadow mode before it
   can control GNSS policy.
3. GNSS speed can provide weak labels only. A threshold such as `speed > 2
   m/s` can support moving/not-moving candidates, but it cannot by itself
   distinguish walking from vehicle. Training labels require good-fix quality,
   temporal stability, transition exclusion, session-level splits, and
   controlled or reviewed examples.
4. Current P0 evidence is stored in Message Hub `raw_frames`, `messages`, and
   `location_memory`. The names `location_observations`, `gnss_attempts`,
   `cell_fingerprints`, `known_places`, and `gnss_bad_zones` describe future
   materialized stores or query views; they are not all current physical
   tables. Exporters should rebuild datasets from bounded existing evidence
   until scale or query cost justifies another table.
5. VPS-side `location_memory` is transitional P0 engineering storage. Product
   architecture must migrate personal known places, common routes, bad zones,
   and long-term location memory to the device or local Ego Base by default.
   A server may retain only consented, minimized, purpose-bounded data with a
   defined retention policy.

## Consequences

- D2 progress is measured by reference-point error, fix rate, and TTFF, not by
  model presence.
- Rule outputs remain replayable and explainable while the corpus matures.
- Existing dataset and training scaffolding is retained, but it does not
  authorize safety-model expansion or learned location fusion in P0.
- A future MotionNet task needs real QMI8658 data, reviewed labels, a rules
  baseline, held-out session evaluation, int8 device measurements, and
  inference power evidence before release.
- Product migration must include location-memory export/delete, consent,
  retention, and local ownership semantics.

## Links

- `../../product/NORTH_STAR.md`
- `../../development/LOCATION_ENGINE.md`
- `../../development/LOCATION_DATASET.md`
- `../../development/LOCATION_FUSION_ALGORITHM.md`
- `ADR-0003-low-power-location-state-machine.md`

