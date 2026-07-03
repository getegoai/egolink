---
document_status: authoritative
last_verified: 2026-07-03
verified_by: codex
---

# ADR-0003: Low-Power Location State Machine

- Status: accepted
- Date: 2026-07-03
- Deciders: codex director review

## Context

Ego Link's location strategy is already defined as EALE-P0: a server-side,
derived, explainable location belief system. Its public belief states are
`Fine`, `Coarse`, `Predicted`, and `Unknown`.

The location and power research notes propose a second kind of state machine:
not a location-belief model, but a low-power sensor and reporting scheduler.
That distinction matters. If these scheduler states are mixed with EALE-P0
belief states, firmware, Web UI, and reports can start treating power policy as
location accuracy. If they are kept separate, the scheduler can reduce wasted
GNSS/Wi-Fi/LTE work while preserving the evidence-first non-claim rules.

PWR-001 is preparing real battery telemetry and a first 24-hour baseline.
FIELD-003 is preparing outdoor GNSS acceptance. Until those measurements exist,
the project can adopt the state-machine shape as a design boundary, but must
not claim measured power savings, 48-hour battery life, or product GNSS
acceptance.

## Decision

Adopt a five-state **location power scheduler** for P0/V1 planning:

| State | Name | Intent | Typical sensor/reporting policy |
|---|---|---|---|
| `L0` | Deep Sleep / Safe Still | Preserve battery when the device is safely stationary. | GNSS off, screen off, low-frequency heartbeat, IMU/SOS wake sources only, optional low-rate cell status when supported. |
| `L1` | Low Power Watch | Normal guard mode when location belief is good enough and risk is low. | Cell/LTE status and heartbeat dominate; Wi-Fi scan and GNSS remain off unless uncertainty rises. |
| `L2` | Moving Normal | Device is moving but not in an emergency. | IMU and cell/LTE continue; Wi-Fi can be intermittent; GNSS uses bounded pulses only when belief confidence decays or route/geofence uncertainty rises. |
| `L3` | Uncertain Locate | Evidence is stale, conflicting, or insufficient. | Bounded GNSS pulse, concurrent cell/Wi-Fi/IMU observation, explicit no-fix/failure reporting, then exit instead of waiting indefinitely. |
| `L4` | Emergency Track | Safety need overrides normal power budget. | Higher report cadence; GNSS can be continuous or dense pulses; LTE upload/ACK gets priority; exit requires explicit safety resolution or timeout policy. |

These states are not public location beliefs. They must not replace
`Fine`, `Coarse`, `Predicted`, or `Unknown`. They are an internal policy layer
that schedules sensors, communication, and evidence collection.

## Required Telemetry

Any implementation must emit additive, source-labelled telemetry before it can
be accepted:

- scheduler state name and version;
- state entry timestamp and exit timestamp;
- transition reason;
- risk level or trigger source when available;
- GNSS attempt budget and actual attempt duration;
- GNSS outcome (`fix`, `no_fix`, `error`, or `not_attempted`);
- Wi-Fi scan state and reason when enabled or skipped;
- LTE/cell observation state and upload result;
- power source/status, battery voltage or SoC when available, and low-power
  reason when power limits suppress a scan;
- emergency override reason for `L4`;
- evidence refs linking scheduler transitions to the command/report window.

The fields must be additive to existing protocol/report shapes unless a future
protocol task explicitly changes a contract.

## Safety Boundaries

- Normal power optimization must not disable SOS, required command ACK,
  required no-fix reporting, or safety-event evidence.
- `L4` can spend more power than normal states; safety takes priority over
  battery targets during an emergency.
- Low battery may explain missing GNSS/Wi-Fi evidence, but it must not hide
  the missing evidence.
- A scheduler transition is not proof of location accuracy.
- A passing firmware build or simulator run is not evidence of 48-hour/7-day
  battery life.

## Relation To EALE-P0

EALE-P0 remains the location-belief layer:

```text
raw evidence -> observation window -> candidates -> location_belief
```

The scheduler is a policy layer:

```text
risk + motion + belief confidence + power + history
-> L0..L4 scheduler state
-> sensor/reporting budget
-> raw evidence
```

The scheduler may use EALE-P0 confidence, failure reasons, last-known age,
motion context, and power evidence as inputs. EALE-P0 may use scheduler
telemetry as quality and failure-explanation evidence. Neither layer should
silently fabricate the other layer's output.

## Follow-Up Tasks

- `PWR-001`: finish real power telemetry and the first 24-hour battery curve.
- `FIELD-003`: execute outdoor GNSS acceptance so GNSS pulse budgets can be
  calibrated against measured TTFF/fix-rate/error data.
- `PWR-003` (planned): implement additive scheduler-state telemetry only after
  PWR-001 and FIELD-003 have enough evidence to set initial budgets.
- `FW-004` (planned in V1): include capability truth in `hello` so scheduler
  policy can distinguish present, missing, mock, unverified, and measured
  sources.
- `WEB-003` (planned): render location confidence and power/scheduler
  explanation for guardian-facing views without exposing internal engineering
  scores as calibrated probabilities.

## Consequences

Adopting this state machine creates a clean boundary for future firmware and
report work. It lets the project discuss "when to turn GNSS/Wi-Fi/LTE on" with
the same discipline already used for "what location belief may be shown."

The immediate cost is documentation discipline: future tasks must keep
scheduler states, source states, and location-belief states separate. The
benefit is that power optimization becomes testable and explainable without
weakening the non-claim policy.

## Links

- `../../development/LOCATION_ENGINE.md`
- `../../development/LOCATION_FUSION_ALGORITHM.md`
- `../../hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`
- `../../tasks/active/PWR-001_POWER_TELEMETRY_24H_BATTERY_BASELINE.md`
- `../../tasks/active/FIELD-003_OUTDOOR_GNSS_ACCEPTANCE.md`
