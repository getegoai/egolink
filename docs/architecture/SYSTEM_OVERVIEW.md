---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
---

# System Overview

## Product responsibility architecture

[ADR-0016](adr/ADR-0016-local-first-ego-state-cellular-primary.md) defines
native-cellular primary calling, local-first/private ownership and parallel
minimal Ego Base. This is a target responsibility map, not a deployment claim.

```text
EgoLink Core
  physical SOS + prompt local feedback + bounded durable priority events
  device Location Engine / Sensor Policy + honest deterministic ego-state
  supported modem native voice + microphone / audio / speaker path
      +-> cellular voice network <-> authorized telephone contact
      +-> authenticated data -> bounded relay -> private Ego Base endpoint
                                                    +-> history/replay/report
                                                    +-> authorized Guardian
  optional RTC data path <-> auxiliary Guardian calling
```

| Gate | Capability | Current state |
|---|---|---|
| `P0-LOC` | Reliable location with honest degradation | `NOT_RUN` |
| `P0-CALL` | Native outgoing/incoming calls and stable two-way audio | `NOT_RUN` |
| `P0-SOS` | Physical-SOS location/alert/primary-call loop | `NOT_RUN` |

Device operational state remains available offline. Base owns user-controlled
private history and heavier derived inference; its first slice is BASE-010
Session ingest/persistence/replay/report/lifecycle. Full private AI is later
work and not a fourth Gate. Neither Base, RTC nor cloud is a dependency of
local SOS recognition or a cellular call when its actual voice service works.
The Message Hub is not a call-media proxy. No self-operated public PSTN/SIP
gateway or public emergency-dispatch service is required.

Native route feasibility is CALL-030; CALL-031 validates representative
hardware after HW-022. Registration/AT ready/dial/ring/connected/two-way audible
are different facts. Exact firmware/operator/audio evidence is required; no
CS/VoLTE support is inferred from a board name. The current board's lack of an
accepted microphone/speaker path precludes acoustic acceptance from its driver.
Old CALL-020/021 remain paused RTC evidence, not primary-call predecessors.

## Cloud lifecycle and present engineering path

Target cloud duties are reachability, signaling and bounded temporary relay.
Each temporary store declares purpose, permitted data, owner/access, count/byte
quota, expiry, private destination and ACK/deletion verification. Transport
receipt, Base durable receipt and human acknowledgement remain separate.
Preserve exact original identity/bytes until the declared durable ACK; any
change in that boundary needs an explicit contract/recovery migration.

The current single-board collector still sends observations and consented
stills to an authenticated VPS collection/photo store and Web surface. That
is an authorized bounded engineering transition, not implemented private Base,
encryption-at-rest or product local-first evidence. Do not move or erase
existing private data through this document; migration requires verified
backup, reconciliation, rollback and separately scoped execution.

## Current single-board evidence and ownership

ADR-0015 retains one identified ESP32-S3-SIM7670G-4G connectivity board plus
necessary Camera, external IMU, power and antennas. Gemini owns recovery,
actual Wi-Fi/LTE transition, short independent-power carry and D2/FIELD-020.
AMOLED, board-to-board forwarding and PC runtime are absent from that field path.
Camera remains a milestone deliverable, not a Location/SOS decision source.

Codex ALIGN-STATE-010 owns decision/current-state/task alignment and existing
rule-state truth: input validity/time/mock lineage, compatible DEVICE/canonical/
API contracts, deterministic replay and actual Web rendering. Unknown, stale,
future or invalid observations must not project as confident normal/safe state.
Scores are experimental; SHA-256 and local_priority labels are not encryption
or proof of storage ownership. New source is not a new boot or live deployment.

Read [ACTIVE_BUILD](../current/ACTIVE_BUILD.md),
[BOARD_MATRIX](../hardware/BOARD_MATRIX.md) and [STATUS](../current/STATUS.md)
for exact last reported evidence; this architecture does not duplicate it.
Full physical SOS and the old RTC runtime remain paused in the field milestone.
HW-021/compliance, CALL-030 and BASE-010 have separate bounded task consumers.

## Retained invariants

- Asynchronous sources keep capture/event time, boot/clock/sequence and quality;
  ingest time cannot replace source time or reorder current truth silently.
- Device minimum Location/Sensor Policy is authoritative for offline action;
  private/server-derived replay cannot overwrite historical device decisions.
- One modem owner, bounded cancellation, secure authenticated transport and
  exact ACK remain mandatory. Capacity, failed persistence and loss are visible.
- SOS recognized-input feedback is immediate; durable record attempt and
  location/alert/native-call outcomes are independent. Storage failure cannot
  suppress local feedback or earn normal durable-event credit.
- Replay is distinct from physical action; settled alerts and ended calls do
  not resurrect. Concurrent recovery needs ADR-0014's guarantees or a reviewed
  behavioral equivalent; finite single-source proof need not wait globally.
- Learned fusion, advanced L2/L3 and Camera inference do not block/veto manual
  SOS or create release claims without separate evidence.

## Historical development topology

The AMOLED wearable + connectivity board + USB PC bridge remains a reusable
engineering fixture for discovery, relay, UI, recording/replay and audio bench
assets. It is not the product topology or proof of independent field behavior.
A PC may host a Base experiment without becoming a fixed product dependency.
See [historical dual-board architecture](DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md)
and the [pre-migration sources](../archive/decisions/20260922/README.md).
