---
document_status: proposed
last_verified: 2026-09-03
verified_by: codex
---

# ADR-0013: CALL-020 Uses One USB Handle With Strict Phase Handoff

- Status: proposed
- Date: 2026-09-03
- Decision owner: founder
- Scope: CALL-020 development-board control and media handoff only

## Context

CALL-020G retains a default-dormant device runner, while CALL-020H/K/L/M
provide the host media and lifecycle seams. CALL-020M initially required an
externally attested control connector that was physically out-of-band from the
USB media stream.

That interim requirement does not match the exact wearable board now in use.
The board has one verified application-visible USB Serial/JTAG byte path. The
dedicated CALL image must disable console and logging so that path can carry
EGLM media. No second independently verified control endpoint exists.

The following alternatives are not suitable for the first engineering PoC:

- interleaving control records with EGLM media would violate the strict media
  parser and create two concurrent owners of one ordered byte stream;
- closing a control port and racing a new media open risks losing initial
  frames during re-enumeration or driver buffering;
- autorun or a local button cannot reliably return the runtime-generated
  session descriptor before the host prepares TLS and relay admission;
- OpenOCD/JTAG memory calls are not a product-relevant or safely bounded
  operator-control path.

## Proposed Decision

For `CALL-020` only, use one exact USB Serial/JTAG connection and one owner at
each instant, with an explicit irreversible phase transition:

```text
CONTROL
  PREPARE -> runtime descriptor -> host TLS/admission ready -> START/ACK
       |
       +-- same open handle; no close/reopen and no enumeration
       v
MEDIA
  EGLM-only uplink/downlink; no control bytes and no console/log bytes
       |
       +-- bounded completion, terminal failure, or runtime deadline
       v
RESULT (optional for the first bounded run)
  redacted counters and cleanup state; never media or credentials
```

The implementation must satisfy all of these rules:

1. A fixed-size/versioned control envelope uses explicit type, payload length,
   operation identity and integrity check. All reads, writes and waits are
   bounded. Integrity framing is not authentication.
2. The device USB driver has one lifetime owner. The control bootstrap may
   lend the already-installed driver to the media endpoint, but the endpoint
   must not install or uninstall a second driver.
3. The Windows side opens one caller-selected exact port once. Ownership moves
   from the control parser to the media adapter without closing or reopening
   the OS handle.
4. Before the first PREPARE request, the CONTROL owner performs one bounded
   receive drain on that same already-open handle to remove only printable
   ASCII/tab/CR/LF ROM or early-boot residue. A zero-progress read establishes
   quiescence. Complete or trailing-partial control magic, unknown/partial
   progress, disallowed bytes, or byte/call/total-time overflow fails before
   the first request write. The drain is not repeated for retries and is not a
   general control-frame resynchronizer.
5. `START/ACK` is the last control exchange. After it is fully transmitted and
   accepted, both sides switch to EGLM-only parsing. Unknown or partial
   transition progress is terminal; neither side guesses a phase.
6. The device owns a hard maximum runtime and independent mute/PA-safe cleanup.
   During MEDIA the first PoC does not promise remote `cancel/join/close`
   acknowledgements over that same stream. Host cancellation closes/cancels
   local I/O; device safety cannot depend on receiving another control frame.
7. Before a later RESULT phase is enabled, the implementation must prove that
   all media workers are quiescent and no EGLM or control bytes remain
   ambiguously buffered. Otherwise completion remains cleanup-unconfirmed.
8. Control payloads contain no bearer token, TLS private material, raw audio or
   location data. Runtime routing labels are non-secret but remain in memory
   and are excluded from logs/results.

CALL-020M's interim attestation requirement should therefore change from
`out_of_band_from_media` to
`logically_separate_and_not_interleaved_with_media`, together with exact
single-handle phase-handoff evidence. A physically separate channel remains a
valid future implementation, but it is not required for this board-level PoC.

## Boundaries

This proposal does not authorize flashing, opening a port, capturing audio,
using a SIM, contacting a relay or changing a VPS. Those actions still require
a fresh, bounded operator authorization and named evidence run.

It also does not change the product requirement. `CALL-020` remains a
PC/USB-bridged engineering proof and can produce at most `pc_side_verified`
evidence. `CALL-021` must still remove the PC and USB media/control path on the
integrated independently powered prototype before `P0-CALL` can pass.

CRC/framing, possession of the development board and a dedicated image are not
substitutes for Guardian/device authentication or TLS peer verification. The
media relay, external authorization decision, source-bound LTE route and
independent Guardian endpoint remain separate required evidence.

## Consequences

- The shortest executable CALL-020 path matches the hardware that actually
  exists and no longer waits for an imaginary second endpoint.
- USB endpoint ownership, runner arming/start, and host serial ownership need
  explicit borrow/transfer APIs and transition tests.
- Media-phase remote cleanup is deliberately weaker than the former abstract
  M lifecycle. The device runtime deadline and PA-safe self-cleanup become
  mandatory before a live run, and unconfirmed cleanup cannot be reported as
  closed.
- A later dual-interface board may restore a true out-of-band control channel
  without changing EGLM media framing.

## Acceptance Before Live Use

- default-off build and plan-only host entry remain intact;
- malformed, oversized, duplicate, wrong-operation and partial-transition
  control frames fail closed;
- bounded pre-control drain accepts only the permitted boot-text prefix and
  rejects complete/partial control magic or ambiguous progress before writing;
- one installed device driver and one exact host handle are proven across the
  CONTROL-to-MEDIA handoff;
- media accepts only EGLM after handoff and control accepts no EGLM before it;
- bounded runtime, worker quiescence, final mute and PA-off paths compile and
  are exercised first with process-local/native fakes;
- fresh operator authorization names the exact image, port, duration, volume,
  no-recording boundary and network route before hardware execution.

## Related Documents

- [Productization Sprint 1](ADR-0012-p0-productization-sprint-1.md)
- [Current execution](../../current/FIRST_LAUNCH_EXECUTION.md)
- [Ego Call](../../development/EGO_CALL.md)
- [CALL-020 task](../../tasks/active/CALL-020_LTE_DATA_VOICE_POC.md)
