---
document_status: authoritative
last_verified: 2026-08-23
verified_by: founder/codex
---

# ADR-0011: First Launch Focuses on Reliable Location, Ego Call, and SOS

- Status: accepted
- Date: 2026-08-23
- Decision owner: founder
- Scope: first-launch capability priorities, communications route, and parallel execution

## Subsequent decision — 2026-09-22

[ADR-0016](ADR-0016-local-first-ego-state-cellular-primary.md) records the founder's 2026-09-19 decision and
2026-09-22 migration instruction. It partially supersedes RTC-primary/native-
reserve wording, defers no longer the minimal private Base endpoint, and admits
bounded rule-state truth work. Three P0 Gate names, evidence obligations,
local safety, source time, exact ACK and the current single-board field scope
remain; CALL-020/021 and full SOS are not automatically resumed. The text
below is the original dated decision, not a new current-state report.

## Context

The founder supplied `docs/archive/product/EGO_LINK_MEMORY_20260818.md` as the latest stage summary
and directed the project to move quickly on multiple independent lines rather
than serialize all work behind one experiment. Most of that brief reinforces
the current product baseline: explainable resilient location, asynchronous
sensing, low-power sensor policy, honest degradation, real-data learning,
screenless SOS, and a custom waterproof EgoCore.

One decision materially changes ADR-0008 and the current Master Context.
ADR-0008 made native three-operator VoLTE a first-generation launch gate. The
new brief makes an application-level, full-duplex `Ego Call` over LTE data the
first-launch communications path and retains native VoLTE as a hardware-ready
future fallback. The brief also separates launch-critical Rule Policy/Safety
Kernel behavior from advanced context understanding that must learn from real
post-launch data.

The change must be explicit. It must not silently rewrite prior hardware
evidence, relax offline SOS behavior, or turn an unbuilt RTC service into a
verified capability.

## Decision

1. The first-launch product value loop is:

   ```text
   Reliable Location + Ego Call + physical SOS
   ```

   Release control uses three exact P0 capability Gate IDs. A sellable P0 may
   be declared only when all three are `PASS`:

   | Gate | Capability | Launch rule |
   | --- | --- | --- |
   | `P0-LOC` | Reliable Location | mandatory `PASS` |
   | `P0-CALL` | Ego Call | mandatory `PASS` |
   | `P0-SOS` | physical-SOS product loop | mandatory `PASS` |

   `L2-AI` is best effort and cannot block a P0 that otherwise passes. `L3`
   context/event understanding remains outside the first-launch critical path.

2. Product capabilities use three priority layers (not assurance Gates):
   - `L1 Location` / `P0-LOC`: launch mandatory. Maintain an explainable
     `location_belief` from GNSS, cellular evidence, IMU/mobility, history,
     time, and measured uncertainty.
   - `L2 Intelligence`: best effort before launch and continuously updatable.
     Initial targets are GNSS reliability, mobility classification, and
     energy-aware location policy. L2 cannot delay an otherwise acceptable L1
     launch.
   - `L3 Awareness`: advanced context, multimodal event understanding, and
     learned active-sensing policy are post-launch evolution. Their data and
     architecture interfaces must be preserved from the first generation.

3. The first-launch communications path is `Ego Call`:

   ```text
   EgoLink <-> LTE data <-> controlled RTC service <-> Guardian app
   ```

   Its release evidence must cover device-to-guardian and guardian-to-device
   calls, full-duplex audio, weak-network recovery, bounded retries, multiple
   guardians/contact escalation, call state visibility, and simultaneous
   location/battery/confidence context.

4. The first generation does not build or operate its own public PSTN/SIP
   gateway. Interoperation with the public telephone network, if later needed,
   uses a licensed communications partner.

5. A0 hardware continues to reserve and evaluate a native VoLTE-capable modem,
   microphone, speaker, amplifier/codec, power, and antenna path. Native VoLTE
   is no longer a first-launch software release blocker. It remains an
   independent `G0V-VOLTE-RESERVE` hardware/migration gate and a candidate
   V1.x/V2 fallback.

6. Physical SOS, local feedback, a location attempt, and durable local event
   recording remain deterministic safety behavior. AI cannot veto them. When
   the network or RTC service is unavailable, remote delivery/call state is
   explicitly `pending` or `failed` and retried by bounded policy; it is never
   shown as delivered.

7. `Rule Policy v0` and the minimum deterministic Safety Kernel remain on the
   launch path. Learned fall/risk/context models, advanced camera/audio
   understanding, and autonomous sensor-policy takeover do not block launch
   unless a later accepted decision promotes a measured capability.

8. Event camera/audio paths may proceed in parallel for A0 evidence and future
   compatibility. They do not outrank Reliable Location, Ego Call, SOS,
   reliability, power, privacy, or compliance, and no unmeasured AI capability
   may become a launch claim.

9. The existing 48-hour representative guard-mode gate, persistent critical
   event handling, waterproof/acoustic, RF/body coexistence, privacy/security,
   certification, and NPI ownership gates remain mandatory. This ADR changes
   capability priority, not product assurance.

10. People-first launch remains the acceptance scenario. Children and older
    adults are primary personas; adult use is compatible. Pet use remains a
    later product variant sharing the platform.

11. Engineering runs in parallel lanes with one bounded integration-ready
    slice per lane. A blocked hardware or external-decision step blocks only
    its dependent lane; other lanes continue. Contract-first changes, hardware
    evidence rules, and operator intent for flashing/commands remain in force.

12. China pre-compliance/product-classification work starts alongside A0
    architecture instead of waiting for a frozen PCB or enclosure.

13. Productization Sprint 1 does not add new sensors, learned multi-source
    fusion, camera understanding, general anomaly models, a polished complete
    app, PSTN, or native VoLTE. It preserves their interfaces/evidence hooks
    only. The active software scope is rule-driven Location Engine v0, fully
    configurable Sensor Policy v0, deterministic replay, the minimum real
    audio/LTE voice chain, and their SOS composition.

## Supersession

This ADR partially supersedes ADR-0008 clauses that make native
three-operator VoLTE and advanced on-device AI/camera capability first-launch
release blockers. It also partially supersedes ADR-0002 clauses 1 and 3 only
where they make MotionNet-class learned inference, the complete M1 training
foundation, formal model/IMU acceptance, or model-footprint completion an
unconditional first-launch blocker. ADR-0002's minimum local deterministic
interaction/safety behavior, edge/private-tier direction, privacy-classed data
flywheel, long-term on-device intelligence goal, and generative-AI safety
boundary remain accepted.

This ADR does not supersede ADR-0008's screenless modular EgoCore,
people-first, A0-to-A1, privacy, honest-location, measured-power, or design-
ownership decisions. ADR-0010's asynchronous event-time and persistent
Store-and-Forward architecture remains accepted.

## Consequences

- RTC/Ego Call architecture, Guardian experience, and SOS orchestration can
  start now in parallel with L1 field evidence.
- Native VoLTE research still protects the PCB migration path but cannot hold
  all software/product work hostage.
- The team must measure RTC reachability, latency, audio quality, reconnect,
  power, privacy, and operating cost; `Ego Call` is currently planned, not
  verified.
- L2/L3 prototypes are welcome when they consume real observations and do not
  displace L1 exit work.
- Existing contracts and D1/D2/D5 evidence remain valid. No Gate advances from
  this decision document alone.

## Related Documents

- [Founder stage summary (historical)](../../archive/product/EGO_LINK_MEMORY_20260818.md)
- [North Star](../../product/NORTH_STAR.md)
- [Master product context](../../product/EGO_MASTER_CONTEXT.md)
- [Current first-launch execution](../../current/FIRST_LAUNCH_EXECUTION.md)
- [Asynchronous acquisition and Store-and-Forward](ADR-0010-asynchronous-observation-timeline-and-store-forward.md)
- [Screenless modular EgoCore decision](ADR-0008-egolink-core-product-direction-reset.md)
