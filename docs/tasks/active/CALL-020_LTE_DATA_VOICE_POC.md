---
id: CALL-020
title: PC-bridged LTE-data RTC media PoC
status: active
priority: critical
lane: B
execution_state: in_progress
depends_on:
  - CALL-010
serves_gate: P0-CALL
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-04

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/EGO_CALL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/CALL-010_AUDIO_HARDWARE_LOOP.md

allowed_paths:
  - docs/architecture/adr/ADR-0013-call020-single-usb-phase-handoff.md
  - docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md
  - pc_simulator/ego_call_media_probe.py
  - pc_simulator/ego_call_media_runtime.py
  - pc_simulator/ego_call_media_io.py
  - pc_simulator/ego_call_concurrent_bridge.py
  - pc_simulator/ego_call_serial_adapter.py
  - pc_simulator/ego_call_authenticated_relay.py
  - pc_simulator/ego_call_tls_stream_adapter.py
  - pc_simulator/ego_call_os_serial_wrapper.py
  - pc_simulator/ego_call_pc_endpoint_composition.py
  - pc_simulator/ego_call_operator_control.py
  - pc_simulator/ego_call_single_usb_phase_connector.py
  - firmware/audio_loop/main/CMakeLists.txt
  - firmware/audio_loop/main/Kconfig.projbuild
  - firmware/audio_loop/main/call020_media_adapter_core.c
  - firmware/audio_loop/main/call020_media_adapter_core.h
  - firmware/audio_loop/main/call020_usb_serial_jtag_endpoint.c
  - firmware/audio_loop/main/call020_usb_serial_jtag_endpoint.h
  - firmware/audio_loop/main/call020_wearable_composition.c
  - firmware/audio_loop/main/call020_wearable_composition.h
  - firmware/audio_loop/main/call020_operator_runner.c
  - firmware/audio_loop/main/call020_operator_runner.h
  - firmware/audio_loop/main/call020_operator_runner_boot_stub.c
  - firmware/audio_loop/main/call020_device_control_wire.c
  - firmware/audio_loop/main/call020_device_control_wire.h
  - firmware/audio_loop/main/call020_device_control_responder.c
  - firmware/audio_loop/main/call020_device_control_responder.h
  - firmware/audio_loop/main/call020_device_control_owner.c
  - firmware/audio_loop/main/call020_device_control_owner.h
  - firmware/audio_loop/main/call020_device_control_owner_boot.c
  - firmware/audio_loop/sdkconfig.call020_usb_endpoint.defaults
  - firmware/audio_loop/sdkconfig.call020_wearable.defaults
  - firmware/audio_loop/sdkconfig.call020_operator_runner.defaults
  - firmware/audio_loop/sdkconfig.call020_device_owner.defaults
  - firmware/audio_loop/README.md
  - quality_tests/test_ego_call_media_probe.py
  - quality_tests/test_ego_call_media_runtime.py
  - quality_tests/test_ego_call_media_io.py
  - quality_tests/test_ego_call_concurrent_bridge.py
  - quality_tests/test_ego_call_serial_adapter.py
  - quality_tests/test_ego_call_authenticated_relay.py
  - quality_tests/test_ego_call_tls_stream_adapter.py
  - quality_tests/test_ego_call_os_serial_wrapper.py
  - quality_tests/test_ego_call_pc_endpoint_composition.py
  - quality_tests/test_ego_call_operator_control.py
  - quality_tests/test_ego_call_single_usb_phase_connector.py
  - quality_tests/test_call020_media_adapter_core.py
  - quality_tests/test_call020_usb_serial_jtag_endpoint.py
  - quality_tests/test_call020_wearable_composition.py
  - quality_tests/test_call020_operator_runner.py
  - quality_tests/test_call020_device_control_responder.py
  - quality_tests/test_call020_device_control_owner.py
  - reports/board_validation/CALL-020-20260902-001/

out_of_scope:
  - Message Hub as a media proxy
  - final RTC-provider selection, browser-grade WebRTC on ESP32, PSTN or VoLTE
  - polished contacts/call UI, multi-party calling, recording or AI voice
  - claiming a USB-free, PC-free or product-embedded media path
---

# Honest PoC Topology

```text
wearable-node-001 audio
<-> USB Serial/JTAG ordered media bytes (dedicated no-console profile)
<-> explicit Windows PC development bridge
<-> planned/unverified SIM7670G RNDIS/ECM LTE data
<-> controlled RTC test service
<-> Guardian browser/phone on an independent network
```

The current boards split audio and cellular capability and have no verified
real-time board-to-board link. This task therefore proves LTE-data media and
weak-network behavior without pretending the bridge is the product.

# Goal

Prove bounded two-way real-time audio through the exact PC-bridged topology.
`CALL-021` must later remove USB/PC from the media path before P0-CALL can pass.

# Offline Parallel Slice

The offline seams proceeded while `CALL-010` waited for operator-approved
hardware evidence. CALL-010 is now `accepted_for_transition`, but that does not
turn any process-local result below into microphone, speaker, LTE or RTC
evidence.

`pc_simulator/ego_call_media_probe.py` evaluates a bounded JSON trace using one
explicit session, one PC-bridge monotonic clock, direction-bound source clocks,
strict endpoint roles, packet identity and per-direction sequence. It:

- keeps uplink and downlink loss, reorder, duplicate, jitter and gap metrics
  independent;
- distinguishes idempotent observation replay from duplicate media packets;
- reconstructs `probing -> connected -> reconnecting -> connected/failed`
  from packet metadata, blackout thresholds and recovery budgets;
- requires both directions within the declared duplex window before deriving
  `connected`; one-way media can never synthesize a connected result;
- rejects unknown record/config fields, so PCM, Opus frames, credentials,
  provider fields and other media/signaling content cannot enter this trace;
- emits explicit non-claims for device audio, SIM/LTE media, VPS/RTC, provider
  selection and `P0-CALL`.

All thresholds are fixture inputs. A passing offline trace means only that the
evaluator applies those declared inputs deterministically. It is not evidence
that any board, SIM, carrier route, RTC service or acoustic path produced the
trace. No new public contract is introduced by this slice.

`pc_simulator/ego_call_media_runtime.py` now provides the executable seam ahead
of real transport integration. It fixes the engineering profile at PCM S16LE,
16 kHz, mono, 20 ms (`320` samples / `640` bytes), and declares an
`in_process_memory_datagram` transport with `in_process_fixture` signaling and
`not_applicable_process_local` encryption. The same boundary explicitly keeps
managed encrypted RTC as the production requirement.

The runtime generates deterministic bidirectional frames with direction-bound
source clocks and one strictly monotonic PC-bridge clock. Uplink and downlink
use independent bounded queues with visible backpressure, blackout, delay,
reorder and deadline-drop accounting. Every accepted `bytearray` is zeroed in
`finally` after delivery or drop. Only packet metadata enters the existing
trace evaluator; the returned result and CLI output contain summaries, never
packet identifiers or media bytes. Execution is bounded to at most ten minutes
of 20 ms source frames plus an explicit finite flush budget. This seam opens no
socket, serial port, audio device, network connection or hardware interface.
It cannot prevent a caller-supplied source or sink from making an independent
media copy; real adapters must enforce and test that no-copy/no-persistence
policy rather than inheriting a false claim from this local seam.

## CALL-020B Gap Audit And Private I/O Seam

The shortest path from the process-local runtime to the declared PC bridge is
now explicit, but it is not yet an actual media run:

- `firmware/audio_loop` is 16 kHz and uses 20 ms capture units, but its current
  application buffer is two-channel/interleaved (`1280` bytes), and the
  bounded diagnostic performs capture then playback sequentially. It has no
  application-level 640-byte mono USB CDC framing, independent uplink/downlink
  queues, or continuous full-duplex media pump.
- `pc_simulator/board_bridge.py` is a newline-JSON control/event metadata bridge
  that can persist JSONL. It is deliberately not reused for binary media; the
  Message Hub and `egolink.p0.v1` remain outside the media plane.
- The current wearable image remains the UI-001 operator build rather than a
  USB media-streaming image. CALL-010 endpoint evidence does not imply a
  continuous media transport.
- The Windows RNDIS interface was enumerated with `192.168.0.100/24` and gateway
  `192.168.0.1`, but the authoritative current status also records that prior
  probes explicitly bound to that source address timed out. Interface `Up` is
  therefore not LTE/PDP/data-plane evidence.

`pc_simulator/ego_call_media_io.py` implements a private, reversible CALL-020B
I/O boundary without changing a public contract. It provides:

- CRC-delimited binary frames with strict session, direction, endpoint role,
  endpoint identity, direction source clock, sequence and source-monotonic
  timestamp validation; every frame is exactly 640 media bytes;
- an identity isolation check on both bridge endpoints before the first I/O,
  plus independent bounded uplink/downlink queues, timeout/retry budgets,
  backpressure accounting and bridge-monotonic metadata timestamps;
- a bounded ordered in-memory byte-stream pair used as both fake serial and
  fake relay endpoint, with healthy, one-way, timeout recovery/exhaustion and
  backpressure scenarios feeding only metadata into the existing evaluator;
- safe retry only when a stream proves zero-byte progress. A timeout after a
  consumed header, or a real ordered-stream timeout with partial/unknown
  progress, closes/fails the stream instead of risking duplicate bytes or lost
  framing;
- a stdlib TLS 1.2-or-newer client seam whose real call requires an explicit
  API authorization flag, binds the configured source IPv4 before connect,
  verifies the server hostname/CA, and loads tokens only from an environment
  variable or file. The offline CLI exposes no network-execution switch and
  emits neither token/certificate paths nor media/packet identity.

The local CALL-020B pump remains a sequential deterministic fake-step harness.
Its `SocketByteStream.timeout_steps` is not a real per-frame deadline and the
socket retains its configured connection timeout. CALL-020C below provides the
separate concurrent orchestration structure; it does not turn these existing
stream adapters into deadline-aware USB/TLS implementations. The connector
currently binds only `source_ipv4`; the offline seam does not prove the OS
mapping from the recorded interface name to that address. No TLS socket, DNS,
serial port, audio device, board, modem, or network was used in this slice.

## CALL-020C Concurrent Bridge Structure

`pc_simulator/ego_call_concurrent_bridge.py` removes one orchestration gap
without constructing or executing real I/O. It accepts only the strict
CALL-020B `FramedEndpoint` pair after a pre-I/O session/direction/identity
check, then runs four daemon workers: one reader and one writer for each of
uplink and downlink. Each direction has its own condition-backed bounded queue,
so a blocking uplink operation cannot consume the downlink worker.

Writers use an absolute `time.monotonic_ns` schedule with a fixed 20 ms frame
cadence, an explicit per-frame deadline, and post-send deadline verification.
The coordinator separately bounds total runtime and worker join, requests
stream close on failure/cancellation, drains both queues, and fails with
metadata instead of reporting a connected state. Existing `FramedEndpoint`
semantics remain authoritative: only a proven zero-progress timeout may retry;
unknown/partial progress and a tail timeout after a consumed header are
terminal.

The bridge owns every mutable `MediaFrame` accepted from a reader until final
disposition. Successful send, queue overflow, pre/post-send deadline miss,
worker error, cancellation and coordinator cleanup all zero the same mutable
payload. Results and failure metadata contain no media bytes or exception
message. External stream, OS, TLS and future adapter copies remain outside
this ownership boundary.

The test clock can be advanced only behind explicit barriers for deadline
cases. This keeps failure tests stable while preserving the honest
determinism boundary: per-direction sequence/source cadence and evaluation of
one captured trace are deterministic, but thread interleaving and wall-clock
timestamps are not promised to be bitwise replay-identical.

This is still an offline structure test. It does not implement wearable USB
CDC firmware/adapter I/O, a matching TLS relay service, a verified RNDIS route,
real socket deadlines, audio capture/playback, RTC signaling or a production
provider. It never reports an actual endpoint connection and cannot advance
`P0-CALL`.

## CALL-020D Wearable Media Framing Adapter Core

This slice is deliberately named a **media framing adapter core**, not a USB
CDC endpoint. The current wearable target selects the ESP32-S3 USB
Serial/JTAG console (`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`) while the USB CDC
console is disabled. Repository evidence does not establish that the board's
exposed connector is also routed for an independently owned USB-OTG/TinyUSB
CDC data function, nor how binary media would coexist with the operator log
and recovery console. USB CDC ownership and routing therefore remain
`unverified`; the CALL-020D core itself must not include or initialize a
USB/TinyUSB driver. CALL-020E below is the separate USB Serial/JTAG adapter.
The unresolved USB integration choice is explicit: this adapter is the
shortest operator-only development path, not a product USB architecture freeze.

The permitted implementation is a compiled, default-disabled component under
`firmware/audio_loop/main/` plus one new focused static test. It may provide
the following pre-integration behavior without changing `app_main`, codec,
pins, gain, volume or the CALL-010 operator paths:

- the exact CALL-020B `EGLM` v1 header/identifier/CRC32 mapping, device uplink
  and guardian downlink roles, direction-bound clock IDs and contiguous
  per-direction sequence starting at zero; both direction source timestamps
  are signed-63-bit bounded and strictly increasing;
- fixed PCM S16LE, 16 kHz, mono, 320-sample / 640-byte frames on a 20 ms
  monotonic cadence, with an explicit arithmetic-mean stereo-to-mono and
  mono-to-dual-channel compatibility mapping for the existing 1280-byte
  two-channel audio frame;
- independent, statically bounded uplink and downlink queues, bounded runtime,
  per-frame deadlines and fail-closed overflow/protocol/error handling;
- terminal handling for ordered-stream partial or unknown-progress timeouts;
  only a proven zero-progress timeout may leave a queued frame retryable;
- a mandatory PA-off callback on initialization, stop and every terminal path,
  and volatile clearing of owned PCM, wire scratch and queued media on every
  success, rejection, timeout, cancellation and cleanup branch; and
- metadata counters only. No API result, log or test artifact may contain raw
  PCM or a complete encoded media frame.

`CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE` remains `default n`, and the
existing application must not instantiate the component. The component's
state permits only `READY -> RUNNING`; after stop, deinit/reinit with a fresh
session identity is required before sequence zero may be used again. Its
callbacks are integration seams only: CALL-020E adds a separately dormant
USB Serial/JTAG endpoint, while worker/task ownership, complete stream
reassembly, verified PA callback binding and audio-device lifecycle remain
required. Compiling this core is not wearable media, full-duplex, USB CDC
runtime, LTE, RTC or `P0-CALL` evidence.

## CALL-020E Dormant USB Serial/JTAG Ordered-Byte Endpoint

The shortest reversible wearable transport slice now wraps the ESP-IDF 5.4.2
USB Serial/JTAG driver rather than claiming a separate USB-OTG route. This is
an **exclusive operator-profile choice**: the currently flashed UI-001 image
and ordinary CALL-010 builds use USB Serial/JTAG as their console, so they
cannot enable the media endpoint. `CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT`
is `default n` and depends on the CALL-020D core, no primary/secondary console,
no application logging and no bootloader logging. Source guards repeat every
dependency, driver install rejects a pre-existing driver owner, and `app_main`
does not reference or instantiate the endpoint.

The endpoint context and lifecycle are caller-owned. Install validates bounded
driver buffers and records the CPU core required by ESP-IDF for uninstall, but
the synchronous ESP-IDF install function has no timeout parameter and therefore
has no claimed hard wall-clock bound. One
read and one write may be active independently; transfer length is capped at
the CALL-020D maximum wire length, each underlying wait is capped at 20 ms,
and each operation/close-wait budget is capped at one second. The higher layer
still owns 20 ms / 640-byte media timing, EGLM encoding/validation and the
complete expected downlink wire size. It must request a whole downlink wire in
one `read_exact` call rather than split header/body progress across calls.

Ordered-stream outcomes are fail-closed. Only a timeout before any byte is
consumed/enqueued is zero progress. A read deadline/cancel after consumption or
an unexpected short write is partial and terminal. Once ESP-IDF accepts a
complete write into its ring buffer, a flush timeout/cancel is unknown progress
and terminal because host receipt cannot be proven. Non-OK reads clear the
bounded destination. The adapter stores and reports only state/counters and
never logs or persists media bytes. Driver ring buffers, controller/FIFO state
and host copies remain outside its erasure boundary.

Cancel is non-blocking; active calls observe it after a bounded driver wait
slice. Close waits a configured bound and never uninstalls underneath an active
operation. ESP-IDF's final uninstall function has no timeout parameter, so the
source can bound cancellation observation and pre-uninstall quiescence but
cannot honestly claim a hard deadline for either ESP-IDF lifecycle call.
Exact-board
connector/controller routing, preceding ROM output, host-open/reconnect
behavior, scheduling latency and sustained ordered transfer remain unverified
until a separately authorized operator build/run. No device, USB, serial,
audio, modem or network action is part of this slice.

The broader USB architecture choice remains open for the product: CALL-020E
temporarily sacrifices the operator console for one development media stream.
A later design may instead verify a separately routed USB-OTG path or a TinyUSB
composite/recovery design with distinct interfaces. No physical routing or
runtime behavior is inferred from the ESP32-S3 peripheral list or a build.

## CALL-020F Build-only wearable composition

CALL-020F now compiles the shortest honest wearable composition of the actual
`safe_audio_initializer_v1` codec/shared-I2S path, two CALL-020D core
instances, and the exclusive CALL-020E USB Serial/JTAG endpoint. It remains
`default n`, cannot coexist with CALL-010 autorun or any primary/secondary
console or application/bootloader logging, and is not referenced by the
existing `app_main`. The dedicated defaults overlay therefore proves the
enabled branch compiles under the console-free configuration; it does not
produce a runnable operator session or authorize hardware access.

The composition uses four separately blocking workers and two static bounded
handoff queues. Audio capture owns exact 20 ms / 1280-byte stereo I2S reads;
USB uplink alone owns the uplink framing core and endpoint writer; USB
downlink reassembles one identity-derived complete EGLM wire across driver
chunks; audio output alone owns the downlink framing core and exact 1280-byte
I2S writes after validated 640-byte mono expansion. No shared core mutex spans
USB or audio I/O. This avoids claiming the single-threaded CALL-020D context is
safe for concurrent direction ownership.

All media/queue/USB waits have finite slices and absolute monotonic deadlines,
and the whole session has a bounded run limit. Only a proven zero-progress
ordered-stream timeout is retryable; partial/unknown progress, protocol,
deadline, overflow, audio and endpoint failures propagate to one terminal
composition state and request cancellation. Close requests cancel, joins every
created worker within a configured bound, verifies codec mute and PA low, and
only then closes the endpoint and audio resources. A join/endpoint-close
failure intentionally leaves resources installed for a later cleanup attempt
rather than uninstalling beneath a task. Owned queue/scratch/core buffers are
cleared; DMA, driver rings, task stacks, controller state and host copies are
outside the erasure boundary. The code reports a terminal safety failure if
mute/PA readback fails rather than claiming physical silence.

CALL-020 uses a separate volume setting, default 55 and hard-capped at 85,
instead of reusing the enclosed-device-inaudible CALL-010 default 12. Level 55
is the lowest step already reported clear/normal in the bounded 55/70/85
diagnostic. The register is read back while muted and PA-off before output;
actual call loudness, SPL, clipping and echo remain operator-test questions.

All session, device, guardian and directional clock identifiers are explicit
caller inputs. Install accepts only operator-supplied provenance. The strings
in `sdkconfig.call020_wearable.defaults` are comments labelled non-production,
are not embedded Kconfig values, and their fixture provenance is rejected.
No relay credential, token, CA, hostname or production identity is committed.

CALL-020F Python tests are source/static contract assertions only and do not
execute C. Separate ESP-IDF default and dedicated builds are the compile
evidence. No firmware was flashed and no device, USB, serial, codec, I2S,
microphone, speaker, modem or network interface was opened. CALL-020G has since
added the dedicated non-autorun runner with runtime ephemeral routing labels
and bounded cancel/close lifecycle, but it has not been executed. Before an
operator run, an independently reviewed control trigger must invoke that API;
exact connector/controller and host open/reconnect behavior must be verified;
CALL-020H now provides an offline caller-injected adapter that drains/resyncs
preceding ROM bytes and preserves complete EGLM framing, but the matching real
OS serial wrapper has not opened the exact connector; and the PC still needs an
actual TLS transport/authenticator wrapper around the CALL-020I offline relay
core plus an RTC path over the verified SIM7670G source interface.
Those remaining items, actual concurrent scheduling/deadline behavior,
acoustic duplex and LTE remain unverified and cannot advance `P0-CALL`.

## CALL-020G Retained non-autorun operator runner ownership

CALL-020G owns only this packet, the new
`call020_operator_runner.c/.h`, its inert dedicated-profile boot stub, its
dedicated defaults overlay and static test, the minimum audio-loop
CMake/Kconfig/README and composition safety-API changes, and evidence under the
existing `CALL-020-20260902-001` directory. It may not edit the ordinary
`app_main`, board pins/codecs, CALL wire contract, 4G
firmware, host serial/relay, server or network paths. This is an offline
link/map slice: flashing, opening USB/audio, starting a task/session, modem or
network access remain prohibited.

The runner is retained in a dedicated final ELF without automatic boot
execution. It owns one long-lived global composition rather than placing the
large context on an ordinary task stack, and creates correlated non-secret
routing labels from one `esp_fill_random` nonce only on an explicit `prepare`
call. The nonce is 128 bits wide, but RF entropy-source state and entropy
quality are unverified; these labels are not authentication credentials. The
runner exposes serialized same-core `prepare/start/cancel/join/close` control.
Merely linking it must have no codec, GPIO, I2S or USB-driver side effect. Any
path after resources have
been installed must request cancellation and force verified mute/PA-safe
cleanup. The ordinary/default build and `app_main` behavior remain unchanged.
Final evidence uses ELF symbols/map and size output rather than treating a
compiled-but-dead object as executable composition evidence.

## CALL-020H Offline host serial transport/resynchronization ownership

CALL-020H owns only this packet,
`pc_simulator/ego_call_serial_adapter.py`, and
`quality_tests/test_ego_call_serial_adapter.py`. It must not enumerate or open
a port, add a pyserial dependency, send control bytes, contact a device/SIM/
network/VPS, or change the private EGLM wire contract. The caller injects an
already-created full-duplex ordered serial object and retains ownership of its
OS handle. The future start/cancel operator trigger remains a separate,
unimplemented control seam; `cancel_pending_io` is only an out-of-band local
transport-lifecycle callback and may not write into the media stream.

The adapter scans a bounded prefix for EGLM magic, retains possible magic
suffixes across arbitrary read fragmentation, and validates a complete bounded
wire candidate before handing bytes to the existing CALL-020B `FrameCodec` and
`FramedEndpoint`. Bad-length/false-magic and bad-CRC candidates may be skipped
within explicit discard/candidate/deadline/callback budgets. Once CRC proves a
candidate is a real frame, a version, direction, session, endpoint-role,
identity or source-clock mismatch is terminal rather than silently joining a
different stream. Read and write have independent ownership locks so the
existing CALL-020C four-worker bridge can use the adapter without serializing
full duplex behind one shared I/O lock.

Returning zero from the injected callback is retry-safe only before the exact
operation has consumed or emitted any byte. Timeout after partial progress,
explicitly unknown progress, invalid progress counts, deadline/callback-budget
exhaustion after progress, and monotonic-clock regression close the adapter
terminally. Writes validate and emit exactly one complete bounded EGLM frame.
All adapter-owned mutable scan/candidate/validation/write buffers are cleared;
copies owned by CALL-020B or the injected OS/driver wrapper remain outside its
erasure control. Audit output is metadata-only and excludes routing identities
and raw media.

`close()` first requests the caller-injected out-of-band cancellation hook,
then waits to acquire both direction locks before it returns. This guarantees
that an in-flight adapter-owned write buffer has reached its `finally` clearing
path. The bound still depends on the injected callback honoring its declared
timeout/cancellation contract; the adapter does not claim it can preempt a
callback that violates that contract.

## CALL-020I Offline matching authenticated relay admission core

CALL-020I owns only this packet,
`pc_simulator/ego_call_authenticated_relay.py`, the minimum H close fix, and
their focused tests. It is a process-local admission and forwarding core: the
caller injects two already-created TLS-shaped ordered streams plus two distinct
endpoint-specific external authentication decisions. It does not listen,
connect, resolve DNS, load credentials/certificates, select a provider, or
contact a device, SIM, VPS or network.

Before any media I/O, each decision must be current and authenticated and must
match the configured session, role, endpoint, peer endpoint, direction clock
and the `connection_id` exposed by that exact injected stream wrapper. Swapped
or mismatched streams, duplicate decisions/connections, repeated session
admission, hijack attempts and cross-session reuse fail closed and close the
new pair without forwarding media. The core does not verify TLS itself or
model separate authenticator implementations; both the injected stream
security and authenticator security remain explicitly unverified.

After admission, the core reuses the existing CALL-020B strict complete-EGLM
framing and CALL-020C four-worker bridge. Thus each direction retains an
independent bounded queue/reader/writer, backpressure, frame deadline, total
runtime, cancellation and join handling without duplicating the media pump.
An unauthenticated, disconnected, cancelled or failed pair never reports
connected. Audit/result/failure objects remain metadata-only and never expose
raw media or routing identifiers. The bounded process registry intentionally
retains raw session/connection/decision routing IDs in memory as non-evicting
duplicate guards; it does not log, persist or expose those values and makes no
claim that they are authentication credentials.

## CALL-020J Default-off connected TLS ordered-stream adapter

CALL-020J owns only this packet,
`pc_simulator/ego_call_tls_stream_adapter.py`, and its focused tests. It accepts
only a caller-injected, already-connected TLS socket-shaped wrapper and adapts
it to the `read_exact` / `write_all` ordered stream consumed by CALL-020I. It
contains no connector, listener, DNS, socket construction, certificate parser,
credential, provider selection or automatic runner. Its configuration is
disabled by default. Passing a connected socket into the constructor transfers
close responsibility; disabled, invalid-config and attestation rejections make
no media call and best-effort cancel/close the submitted socket.

Python does not expose a trustworthy post-construction certificate-verification
result from an arbitrary `ssl.SSLSocket`, so this seam does not infer one. The
caller must inject a frozen attestation stating handshake completion, certificate
chain verification, peer-identity verification, peer identity, selected ALPN,
TLS version and connection ID. Before media, the adapter requires all verified
flags, validates the external authentication decision's current window and
exact configured session/role/endpoint/peer/clock binding, and requires one
connection ID across the decision, attestation and actual injected wrapper. It
also queries that wrapper's selected ALPN/TLS version and requires exact matches.
These checks validate consistency, not the security of the unimplemented
handshake/PKI/authenticator that produced the attestation.

The injected socket must already have a positive finite timeout no greater than
the configured per-call slice and provide a prompt out-of-band cancellation
hook. Reads and writes have independent locks and bounded transfer, monotonic
deadline and callback budgets. Short reads/writes are completed exactly; EOF,
invalid counts, clock regression and connection-ID mutation are terminal. A
receive timeout before plaintext progress, or an explicitly proven zero-byte
send timeout, is retry-safe. Partial/unknown progress and ordinary send timeout
are terminal. The adapter cannot preempt a wrapper that violates its declared
timeout/cancel contract.

`close()` first requests cancellation, then obtains both direction locks before
closing the injected socket and clearing its socket/config/routing references.
Every owned write copy and failed-read buffer is cleared; a successful read
buffer transfers to CALL-020B ownership. External TLS/library/kernel/caller
copies remain outside this boundary. Audit is metadata-only and contains no
certificate material, identity, connection ID or media. CALL-020J ran only against fake
process-local sockets: real TLS handshake/listener/PKI, connected-socket wrapper,
network route, control trigger and P0-CALL evidence remain absent.

## CALL-020K Default-off explicit OS serial wrapper

CALL-020K owns only this packet,
`pc_simulator/ego_call_os_serial_wrapper.py`, and its focused tests. It is the
minimal host-OS opening seam beneath CALL-020H: the caller must explicitly
supply one exact port name, a new process connection identity, baud rate,
finite read/write timeout bounds and exclusive ownership. Configuration is
disabled by default. The module never enumerates, guesses or probes ports,
never interprets ROM bytes or EGLM media, and never places control bytes in the
media stream.

Tests inject a factory. For an eventual real call, `LazyPySerialFactory`
performs an optional lazy `serial` import only after explicit enable/open,
constructs one closed `Serial` instance, applies the exact caller values, and
opens that instance. The repository does not declare pyserial as a mandatory
dependency; an unavailable or malformed optional dependency fails with a
fixed redacted reason and triggers no installation or environment change. No
real factory call was made in this slice. Factory ownership covers any
partially created handle until it either cleans up after raising or returns an
open driver. After successful validation, ownership transfers completely to
the wrapper, which never reopens it; the original caller must not mutate,
close or reopen the transferred driver.

A bounded process registry permits only one active wrapper per exact port and
never reuses a connection identity, including after failed open or close.
Before and after each I/O callback the wrapper checks observable open state,
port, baud rate and exclusive-mode invariants. Mutation is terminal and a
reconnect requires a new identity. A malicious or broken injected driver that
closes and reopens itself between observations while restoring every field
cannot be detected generically; this remains an explicit driver-contract trust
boundary rather than an authentication claim.

Read and write have independent ownership locks, strict one-byte contiguous
views and bounded per-call lengths/timeouts. Short counts pass losslessly to H.
Only an explicit zero-progress timeout is retry-safe; partial or unknown
progress is terminal. `close()` requests out-of-band read/write cancellation,
waits for both direction locks, closes the owned driver, releases the active
port and clears driver/config/identity references. As with H and J, quiescence
depends on the injected driver honoring its timeout/cancel contract. K owns no
media/wire buffer; caller/driver/OS copies remain outside its erasure boundary.
Audit and admission errors expose only fixed metadata, never port, connection
identity, raw factory/OS errors or media. CALL-020H still exclusively owns ROM
prefix/EGLM resynchronization, and the operator control trigger remains a
separate unimplemented seam.

CALL-020K ran only with fake factories/drivers, including the lazy factory via
a fake imported module. One offline integration passes fragmented ROM-prefixed
wire through K into H and the existing strict frame endpoint. Existing J/I
tests separately cover the authenticated TLS relay leg; K does not conflate
the serial leg with J's externally attested TLS leg. No COM/USB/device, SIM,
socket, network, VPS or audio interface was enumerated, opened or contacted.

## CALL-020L Default-off PC endpoint composition

CALL-020L owns only this packet,
`pc_simulator/ego_call_pc_endpoint_composition.py`, and its focused tests. It
is the shortest explicit PC media composition: the wearable leg is K's exact
OS-serial connection through H's ROM-prefix-resynchronizing ordered stream and
strict `FramedEndpoint`; the relay leg is J's caller-supplied, already-connected
and externally attested TLS stream through a second strict `FramedEndpoint`.
Both endpoints are then passed to the existing CALL-020C
`ConcurrentDuplexMediaBridge`; this slice does not copy or replace its four
workers, direction queues, frame timing or complete-wire validation.

Construction validates and stores only immutable configuration and performs no
transport action. `open()` is a separate, explicit call that requires the
serial factory, already-connected TLS socket, frozen attestation and current
external authentication decision from the caller. Only that call can ask K to
open the one exact configured port. The same device/session/role/source-clock
identity is required across H, J and C before media. The OS serial handle and
TLS socket have separate connection identities because they are different
transport lifetimes; each identity is exact and immutable inside its own K or
J leg and neither is treated as an authentication credential. Control remains
an independent unimplemented seam and no control bytes enter either media
stream.

Admission creates J first, then K/H, then C. Any rejection or later leg failure
best-effort cancels/closes every resource whose ownership has transferred,
including the caller's unadmitted TLS socket. `start()` is single-use and
synchronously invokes the actual concurrent bridge. External cancellation
requests bridge stop and both transports' out-of-band cancellation hooks;
`close()` waits for the serialized open/start operation and both child closes.
Quiescence cannot preempt a broken factory, driver or socket callback that
violates its declared finite-timeout/cancellation contract.

Successful output retains only bounded direction counters. It says that the
bridge completed full duplex while explicitly stating that this composition
layer did not evaluate transport provenance and proved no real serial or TLS
connection. Results, fixed failures and audit expose neither routing identity
nor media. The layer has no CLI/autorun, port discovery, socket construction,
DNS, TLS handshake, PKI, credential, listener, log or persistence path.
CALL-020L tests use only process-local fake serial/TLS resources; the healthy
case spies on and executes the real `ConcurrentDuplexMediaBridge.run` rather
than substituting a fake forwarding result. No COM/USB/device, SIM, OS socket,
network, VPS or audio action occurred.

## CALL-020M Default-off host control entry and plan

CALL-020M owns only this packet,
`pc_simulator/ego_call_operator_control.py`, its focused test and its evidence
note under the existing CALL-020 report directory. It adds the independently
reviewable host lifecycle above CALL-020K/L without adding a real transport or
running a device. Construction and the CLI are inert; the CLI has only a
required `--plan-only` path and exposes no start/execute option. Plan output
contains only redacted metadata and states that the repository is not yet
launchable by itself.

The executable Python API is default-disabled and single-run. Its exact phase
order is `prepare -> preflight -> open -> start -> stop -> close`. `prepare`
requires both `enabled=true`/`plan_only=false`, a fresh process-local run ID,
an explicit operator-intent boolean and a mutable one-shot token checked by a
caller-injected verifier. Token ownership transfers only when consumption
begins; before then the caller remains responsible for clearing an abandoned
authorization through its explicit `zeroize` lifecycle. It is cleared on every
consumed path, and host `prepare`
automatically clears it on disabled or plan-only rejection. Neither token nor
run ID appears in results. This is an intent/authentication integration seam,
not a new credential scheme or cross-process freshness proof.

`preflight` performs no connector callback. It requires one exact port, an
exact caller-supplied serial factory for K, an externally attested connected-
TLS connector for J/L, and a separately attested connector for the exact G
`prepare/start/cancel/join/close` API. The wearable-control attestation accepts
the legacy physically out-of-band topology or a logically separated,
non-interleaved phase topology. It never
enumerates or guesses ports, constructs a socket, performs TLS/PKI, installs a
dependency or places control bytes in EGLM media. A missing connector remains
the fixed `wearable_control_connector_missing` preflight blocker before serial,
TLS, device or media I/O; M does not misrepresent K's media path as a remote
control path. CALL-020P now supplies the offline host half of a same-handle
connector. Logical preflight requires that exact object to serve both the
wearable-control and serial-factory roles and expose explicit phase/cleanup
operations. The matching device wire counterpart and runtime behavior remain
unimplemented/unverified, so this is not exact-board evidence.

Only explicit `open` may invoke injected connectors. The G prepare result must
carry the runtime-generated descriptor and exact G version/API, then that
identity configures the existing L composition. Entry into the external
prepare callback makes remote acceptance unknown, so an exception or malformed
reply still triggers the same idempotency-bound `cancel -> join -> close`
cleanup. Normal progress issues each control action once. Cleanup uses a
stable run-scoped operation ID for at most two bounded attempts, allowing a
remote idempotency implementation to recognize a retry. On the legacy OOB
path, `stop`/`close` becomes locally idempotent only after media-thread
quiescence and a confirmed wearable `CLOSED` acknowledgement; otherwise M
remains failed, retains the references needed for a later cleanup attempt, and
does not claim closure. Local endpoint
ownership is tracked independently: an endpoint `close` exception retains the
same endpoint and fails closed until a later call confirms its cleanup; stop
telemetry failure is not treated as endpoint-cleanup proof. The TLS
connector must return an already-connected socket, frozen J attestation and
current authentication decision with an exact identity/connection binding.
If it raises after allocating anything, its attestation contract must either
confirm cancel/close before raising or retain the same resource behind a
bounded cleanup retry. A retained-resource contract is rejected without that
retry operation, and M cannot report `closed` while such cleanup is pending.
Connector timeout limits are checked after return but are not a hard Python
preemption claim. In the logical same-handle path, M orders `prepare -> TLS
ready -> START/ACK -> one-shot handle transfer -> L open`. START/ACK is the
last CONTROL exchange. From that point until K/L returns the quiescent facade,
M never invokes wearable cancel, join, close or telemetry; early stop can prove
only local media cancellation/join and host-handle cleanup. RESULT remains
disabled, remote cleanup and device runtime termination remain unconfirmed,
and a final M `closed` state is explicitly scoped to host resources.
Enabling either real external connector remains blocked pending separate
review of its own hard deadline, cancellation and partial-resource cleanup.

The optional executable path retains all existing L per-direction safe
counters: expected/received/forwarded frames, receive/send retry counts,
backpressure drops and before/after-send deadline misses. It adds only a host
monotonic elapsed duration and fixed termination reason, not invented jitter
or transport provenance. Pre-start internal-heap and post-stop internal-heap
plus all four G worker stack-watermark snapshots are caller-injected,
validated metadata contracts on the legacy OOB path. The logical path carries
only the pre-start snapshot because CALL-020P has no RESULT phase; it never
invents a post-stop snapshot. M did not measure either and labels their source
accordingly. All results, errors, plans and audits exclude port values,
routing IDs, credentials and binary data; raw audio is never an accepted
control input and is neither logged nor persisted.

Focused tests execute only process-local fake verifier/connectors and a fake L
endpoint factory. They cover inert plan/CLI, disabled prepare, token erasure,
run-ID nonreuse, exact-port rejection, zero-callback preflight, missing-G
fail-closed behavior, descriptor-to-L wiring, phase/idempotency order, bounded
cancel/join, malformed or lost prepare replies, staged-open cleanup, concurrent
`open`/`start` versus `close`, transient cleanup recovery, permanent unconfirmed
wearable or local-endpoint close failure, telemetry, complete safe-counter
preservation, legacy/logically-separated wearable topology validation,
same-handle connector-shape gating and redaction. CALL-020P adds focused
same-handle lifecycle tests below. No real port, serial driver, TLS
socket, network, board, audio device, SIM, VPS or RTC service was used.

## CALL-020N Default-off exact-route host TLS connector

CALL-020N adds a thin standard-library connector in the existing M module; it
does not duplicate B framing, I authentication-decision types, J connected-
socket admission or L media composition. Construction remains inert and the
existing command line remains plan-only. Only an explicit Python
`open_verified` call on an `enabled=true` connector may create a socket; no
CALL-020N test invokes the real socket/context defaults.

The connector accepts exactly one canonical numeric IPv4 peer, one numeric
source IPv4 to bind before connect, one canonical lower-case TLS hostname used
unchanged for certificate verification and SNI, one port, and exactly one
caller-provided CA source (bounded PEM material or an exact absolute path). It
creates `AF_INET/SOCK_STREAM` directly and never calls address resolution or a
hostname-based connection helper. Its private trust context has
`CERT_REQUIRED`, hostname checking, common-name fallback disabled when the
runtime exposes that control, TLS minimum 1.2 / maximum 1.3, compression off,
and the exact CALL-020 ALPN. After numeric connect it verifies the actual
`getsockname()` source address and `getpeername()` peer address/port against the
configured route before TLS wrapping. One overall open deadline covers context
setup, TCP connect, handshake and application authentication; each stage uses
only its smaller configured cap or the remaining overall budget. A remaining
sub-millisecond interval is not rounded up for the integer-millisecond
authentication callback. Steady-state read/write timeouts are finite; the
socket uses the stricter of the declared read/write limits so concurrent J
calls never race by mutating a shared socket timeout.

A successful TLS handshake is not permission to invent CALL endpoint
authentication. N passes a private, non-logged certificate digest plus exact
route/session/connection evidence to a caller-injected session authenticator.
That callback must return the existing I `ExternalAuthenticationDecision` with
the exact session, device role, device/Guardian IDs, uplink clock and generated
connection ID. A missing, malformed, rejected, expired or mismatched decision
fails closed and the connector never creates a substitute. The returned J
attestation separately retains the verified TLS server hostname while its
endpoint identity comes only from that external decision. The repository does
not yet implement the real session authenticator; fake decisions in N tests are
process-local contract fixtures only. Its callback timeout is checked after
return, not hard-preempted, so production enablement remains blocked until the
authenticator has its own reviewed hard deadline/cancellation behavior.

Every failure after socket creation runs bounded shutdown/close cleanup. If
close cannot yet be confirmed, the exact partial transport remains retained
behind a cleanup-only retry operation; the error explicitly reports cleanup as
unconfirmed. M retries that same object and refuses `CLOSED` while cleanup is
pending. M's attestation remains backward compatible: a connector must attest
either completed cleanup before raise or retained ownership with bounded retry.
The latter requires a callable retry operation, and M requires that truthful
retained-resource contract specifically for N. M also takes ownership of any
valid returned bundle before its
post-return overall-deadline and binding checks, so a late rejected bundle is
cancelled and closed. The connector raises a redacted metadata-only error, and
ownership transfers to M/J only after route, TLS metadata, peer certificate,
external decision and exact binding all validate. Audit/error output contains
no IP, hostname, path, CA, certificate digest, run/session/connection identity,
decision, credential or media. Raw audio is never accepted, logged or
persisted.

N is independent of wearable control topology. It neither assumes nor opens a
second control endpoint and remains compatible with the proposed ADR-0013
engineering handoff that serializes `CONTROL -> MEDIA -> RESULT` ownership on
one wearable USB handle; ADR-0013 is not an accepted architecture decision.
CALL-020P supplies that offline host handoff seam without changing N or
assuming a second control endpoint.
No real socket, DNS, TLS handshake, network, serial port, device, SIM, VPS or
audio path ran, and N does not advance `P0-CALL`.

## CALL-020P Same-USB CONTROL-to-MEDIA host phase connector

CALL-020P adds
`pc_simulator/ego_call_single_usb_phase_connector.py` as a default-disabled,
API-only host seam. Construction retains one caller-injected, already-open
exact driver but does not claim it; the first explicit `prepare` validates the
exact port/baud/timeouts/exclusive shape and claims its object identity in a
bounded authoritative registry instance. Its default instance is process-wide;
injected isolated registries are a test/trust boundary and do not detect
malicious cross-registry aliases. Registry entries combine the exact Python
object pointer with a monotonically increasing non-reused generation and one
owner state. Neither pointer, generation, port nor identity is emitted in
audit/error results. P has no opener, enumeration, guessing, reconnect, CLI or
autorun path. If activation fails before the claim, M records
`lease_never_acquired/caller_retains_handle`; it may release its own references
but never reports that still-open caller resource as locally closed.

The private engineering CONTROL envelope is named `EGLC` v1. It carries a
fixed magic/version/type/big-endian payload length, at most 2048 bytes of
canonical ASCII JSON and a CRC32 over header plus payload. JSON rejects unknown
top-level response fields, duplicate keys, noncanonical encodings, excessive
depth/count/string/integer bounds and mismatched run/operation/action fields.
CRC is framing integrity only, **not authentication**; a matching authenticated
device control protocol and authorization/session binding remain launch
blockers. `prepare/start/cancel/join/close/telemetry` bind the operation ID to
the complete immutable request including timeout. Completed operations are
locally cached; a wire retry is allowed only after proven zero progress and
must receive an explicit duplicate acknowledgement. Partial/unknown progress
is terminal. A lost or malformed START reply becomes `START_UNCERTAIN`, after
which P sends no further CONTROL byte and permits only local handle cleanup.
Timeouts are finite at the injected-driver boundary but Python callback timing
is still only checked after return, not hard-preempted.

Before the first PREPARE request write, and only while CONTROL owns the same
already-open handle, P performs one bounded RX drain/quiescence check for ROM
or early-boot residue. It discards only printable ASCII plus tab/CR/LF, with
independent byte, read-call and total-time bounds. A zero-byte return or a
driver timeout explicitly reporting zero progress establishes the quiet point.
Unknown/partial timeout progress, disallowed bytes, any complete `EGLC` magic,
a trailing partial magic, or any bound violation fails before the first
CONTROL write. Drain buffers are cleared and the drain is never repeated on an
idempotent PREPARE retry. Once CONTROL framing begins, all response reads stay
exact-frame; this is not a general resynchronizer.

A complete START acknowledgement moves the registry to `HANDOFF_READY`. Only
then may L ask K's existing exact factory seam for media. P constructs a
one-shot borrowed-driver facade before atomically moving the same object and
generation from CONTROL to MEDIA; it never closes/reopens or substitutes a
driver. K/L close returns that facade to P without physically closing the
underlying handle. M orders `prepare -> externally verified TLS ready ->
START/ACK -> handle transfer -> L open -> media`. From START acknowledgement
through media quiescence and facade return, M/P forbid control bytes. Early
stop therefore proves only local media cancellation/join; it cannot promise a
remote cleanup acknowledgement, device task termination or PA mute.

After the media worker is joined and L/K close has returned, M may use P's
local recovery seam to retry a failed facade return and then physically close
the exact returned driver. A close callback is not treated as proof: P must
observe `is_open is False`, and retains the same `CLOSING` lease for bounded
retry otherwise. Before START is definitely accepted, M may still use the
normal stable-ID `cancel -> join -> close` control cleanup; after acceptance or
uncertainty it uses local cleanup only. RESULT reclaim/wire is deliberately
disabled in this slice, so post-stop device telemetry, remote CLOSED and device
runtime termination remain `UNCONFIRMED`. M's terminal `closed` means host
resources only.

Focused P tests use only an in-memory fake already-open driver, fake TLS bundle
and fake L endpoint. They cover default-off zero I/O, strict frame/CRC/JSON
rejection, fragmented and partial transfers, lost/duplicate acknowledgements,
full-request idempotency conflicts, START uncertainty, START-versus-transfer
serialization, exact one-shot ownership transfer/return, cancel rejection
after transfer, transient unconfirmed physical close, M phase ordering, early
stop and post-transfer failure cleanup. They do not execute the Q device
counterpart below, run a real port/socket/network/audio path, or advance
`P0-CALL`.

## CALL-020Q Default-off device CONTROL responder

CALL-020Q adds the compile-only matching device `EGLC` v1 parser/responder over
one registry-backed USB Serial/JTAG lease. It validates the complete fixed
header before reading a bounded canonical JSON remainder, binds the full
`(run_id, operation_id, action, timeout_ms)` fingerprint, and permits only the
immediately latest operation to replay after proven zero response progress.
Older cached operations become stale as soon as a newer operation is accepted.
CRC remains framing integrity only, not authentication.

One caller-serialized CPU core owns `PREPARE -> descriptor/pre-start telemetry
ACK -> START ACK -> lease handoff -> G runner start`. Frame acquisition has an
independent wait deadline; only after a complete frame passes decode and
maximum-timeout validation is a fresh device operation deadline anchored, so
idle waiting cannot erode the request's device-side budget. The host retains
its independent end-to-end deadline. Tick waits round down, sub-tick waits
poll, and every CONTROL read/write/TX-drain return is checked against its
applicable monotonic deadline. The synchronous ESP-IDF driver install/uninstall
APIs have no timeout parameter and no claimed hard wall-clock bound. An expired
accepted request has no authority to invoke a runner callback; a callback that
returns after deadline becomes terminal and cannot emit a success response.
START ACK is the final CONTROL byte and must be fully written and drained
inside the deadline before handoff. A later handoff, start or deadline failure
is `START_UNKNOWN`, with local best-effort cleanup only and no corrective
CONTROL/RESULT or remote-cleanup claim.

Install failure does not imply no ownership: if the lease API leaves an
initialized terminal lease after a rollback failure, Q retains it and attempts
same-core cleanup. Likewise, successful runner prepare is recorded before
telemetry so a telemetry failure closes the global runner. The dedicated build
uses the inert boot stub, disables application/bootloader console and logs, and
does not instantiate or call Q from `app_main`.

Post-stop four-worker watermarks are unavailable. A telemetry request therefore
receives `accepted=false` with an empty worker set and then fails closed; this is
not successful telemetry. RESULT, post-media CONTROL, automatic runtime join,
remote cleanup proof and physical-board behavior remain disabled/unverified.
Q tests are source-contract/boundary-model checks plus ESP32-S3 compile/link;
the USB pump has not executed and no board, port, network or audio path ran.

## CALL-020R Default-off device lifecycle owner

CALL-020R closes the smallest device-side lifecycle gap without adding a new
wire phase. The ordinary build and the existing G/Q retained profile remain
boot-inert. Only the separate `sdkconfig.call020_device_owner.defaults` profile
selects an `app_main` that creates exactly one pinned owner task. Task creation
failure returns before any owner API or hardware boundary runs. A successful
task owns every Q/G/lease mutation on its pinned core; there is no second task,
timer callback or cross-core cleanup path.

The owner anchors one total CONTROL deadline before the synchronous driver-open
call. It starts another `serve_once` only while the complete configured frame
plus maximum operation budget remains, and checks the absolute deadline again
after every call. The
ESP-IDF install/uninstall functions still have no cancellation parameter, so
this is a fail-closed total authorization deadline with a post-return check,
not a claim that an in-flight vendor callback can be hard-preempted.

After `MEDIA_STARTED`, no Q serve or wire-write function is reachable. START
ACK remains the final CONTROL byte and RESULT remains disabled. The existing F
runtime deadline remains the hard media limit. On that deadline, a runner/F
terminal state, or observation that all four workers already finished, R calls
G cancel (which first forces codec mute/PA safe), then waits at most the
configured quiescence grace for exactly `workers_created=workers_finished=4`.
It then invokes Q's phase-idempotent local-only finalizer. Each retry resumes at
the first unproven step: cancel and bounded join, four-worker/mute/PA proof,
runner close, exact borrowed-lease return, and physical USB driver close.
Join, runner-close, lease-return, or uninstall failure keeps the unique pinned
owner in a fail-closed recovery loop with exponential delay capped at five
seconds; the owner task is never deleted while any cleanup proof is missing.
`call020_device_control_owner_run()` therefore does not return on that recovery
path. Only complete worker/runner/lease/physical-close proof permits `CLOSED`
and task deletion. This is a resource-retention safety contract, not a bounded
recovery-time claim; the ESP-IDF uninstall callback remains synchronous and not
hard-preemptible.

`device_runtime_termination_proven=true` requires every local observation. A
historical media timeout may remain in metadata even when cleanup is proven;
the exact responder `first_error` and first terminal reason are retained in
owner diagnostics instead of being replaced by a generic close error. Only
F's explicit `TERMINAL_RUNTIME` plus `run_limit_reached` combination is treated
as a normal bounded end; every other non-OK runner or composition `first_error`
remains the owner result after cleanup. Singleton initialization claims the
owner before clearing context and rejects every repeated initialization, so an
active owner cannot be reset. Total-deadline comparisons consistently use the
end-exclusive `now >= deadline` boundary. Invalid post-START clock/deadline
arithmetic enters the same persistent local finalizer. No remote cleanup
acknowledgement is claimed.

R does not add authentication, TLS, owner authorization, production session
binding, LTE, SIM or relay logic. EGLC CRC remains framing integrity only.
ADR-0013 remains `proposed`, and no RESULT/post-stop telemetry design is
approved by this slice. Focused tests include source/boundary checks and an
actual-owner-C failure-injection harness. The harness is compiled, linked and
executed as a freestanding native Windows test when the pinned Espressif LLVM
x86 target is available; otherwise it is ESP32-S3 cross-compiled without an
execution claim. Fresh ESP-IDF 5.4.2 default and R-profile builds compile/link
the final source but do not boot it. No USB, audio, board, modem or network path
was accessed.

Offline slice acceptance:

- [x] Source/session/endpoint/sequence and clock lineage fail closed.
- [x] Uplink and downlink metrics cover loss, reorder, media duplicate,
      jitter, gap, blackout and bounded recovery independently.
- [x] Exact replay is deterministic and one-way media cannot become
      `connected`.
- [x] Trace/output retain no media content, credential or RTC-provider choice.
- [x] The executable process-local seam uses the exact 20 ms / 640-byte PCM
      profile, independent bounded direction queues and deterministic faults.
- [x] Delivery, blackout, backpressure and deadline paths zero accepted mutable
      buffers; API/CLI output is metadata-only and deterministic.
- [x] Private 640-byte framing and fake serial/relay endpoints enforce session,
      role, source, clock and contiguous sequence identity before forwarding.
- [x] Ordered-stream retries are bounded and permitted only for proven
      zero-progress timeouts; partial/unknown progress fails terminally.
- [x] The offline TLS preflight requires an explicit source IP and interface
      identity, reports the prior source-bound egress timeout, and remains
      blocked without an authorized handshake/auth acknowledgement.
- [x] Runtime-owned media/wire/transport buffers are zeroed; the boundary does
      not claim control of independent copies made by external sinks, OS/TLS or
      future adapters.
- [x] Concurrent uplink/downlink reader and writer workers use independent
      bounded queues, monotonic 20 ms scheduling, per-frame deadlines and
      bounded stop/join without opening real I/O.
- [x] Blocking/delay/error fixtures prove direction isolation, terminal
      partial/unknown timeout handling, backpressure/deadline failure,
      exception propagation, cancellation cleanup and metadata-only truth.
- [x] The wearable target compiles a default-uninstantiated CALL-020D framing
      adapter core with exact 640-byte CALL-020B wire mapping, independent
      bounded direction queues, monotonic deadlines, one-run-per-session
      sequence state, mandatory PA-off callback and owned-buffer clearing.
- [x] CALL-020D source/static assertions cover the intended state transitions
      and fail-closed branches. They do not execute the C core and therefore
      are not runtime, task-scheduling, USB CDC or audio evidence.
- [x] CALL-020E compiles an uninstantiated, default-disabled USB Serial/JTAG
      byte endpoint with explicit console/log ownership guards, bounded caller
      lifecycle and terminal partial/unknown-progress handling.
- [x] CALL-020E source/static assertions cover ownership, bounds, cancellation,
      zero/partial/unknown progress, destination clearing and non-persistence.
      They do not execute C or access a USB controller/host.
- [x] CALL-020F compiles a default-dormant composition using the actual safe
      codec/I2S initializer, four direction-isolated workers, two single-owner
      framing cores, complete-wire USB reads, bounded deadlines/run/join and
      fail-closed mute/PA cleanup; ordinary `app_main` remains unmodified.
- [x] CALL-020F source/static assertions cover configuration guards, identity,
      directional ownership, exact frame sizes, terminal progress semantics,
      cancel/join ordering, owned-buffer clearing and non-persistence. They do
      not execute C or prove any device, USB, audio, LTE or network behavior.
- [x] CALL-020G retains the runner and D/E/F dependency chain in a final ELF,
      keeps the ordinary build unchanged and uses an inert dedicated boot
      entry that performs no I/O until a future explicit `start` call.
- [x] CALL-020G exposes serialized same-core prepare/start/cancel/join/close,
      generates non-secret correlated routing labels only at runtime with
      unverified random quality, caps each USB ring at 4096 bytes, forces
      mute/PA-safe disposition after installed failures, and clears owned
      buffers without logging or storing media.
- [x] CALL-020G source/static assertions and separate ESP-IDF default/dedicated
      builds verify default-off guards, inert boot wiring, final ELF retention,
      resolved console/log exclusivity and bounded resource sizing. This is
      build evidence only and executes neither the C API nor any device I/O.
- [x] CALL-020H provides a caller-injected, dependency-free host ordered-byte
      adapter that performs bounded ROM-prefix/false-magic/CRC resynchronization
      and hands a validated stream to the existing strict framing and
      concurrent bridge without opening a real port.
- [x] CALL-020H focused tests cover arbitrary fragmentation, magic split across
      chunks, exact/overflow prefix bounds, bad length/CRC recovery, CRC-valid
      session/role/clock rejection, exact writes, zero-progress retry versus
      terminal partial/unknown progress, buffer clearing and metadata-only
      audit. These tests use process-local doubles and are not serial/device
      evidence.
- [x] CALL-020H close requests cancellation and then quiesces both direction
      locks before returning, so an in-flight adapter-owned write copy reaches
      its clearing path when the injected callback honors its timeout contract.
- [x] CALL-020I requires two distinct endpoint decisions and exact binding of
      each decision's connection ID to the corresponding injected stream before
      any media, and rejects duplicate/hijack/cross-session admission closed.
- [x] CALL-020I cancellation before the first run closes and clears both new
      streams without validating decisions or consuming a registry session;
      cancellation racing after admission remains terminal and never reports
      connected.
- [x] CALL-020I reuses the strict complete-frame endpoint and existing bounded
      four-worker bridge; focused process-local tests cover healthy duplex,
      admission isolation, disconnect/cancel, concurrent single-use state,
      buffer clearing and metadata-only/redacted audit. This is not real TLS,
      network, relay-service, device or P0-CALL evidence.
- [x] CALL-020J supplies a default-off adapter from a caller-injected connected
      TLS socket shape to the CALL-020I ordered-stream API without creating or
      opening any connection, listener, DNS, hardware or network interface.
- [x] CALL-020J requires frozen externally supplied certificate/peer attestation,
      exact actual-socket ALPN/version/connection binding and the matching current
      CALL-020I session decision before media; construction rejections perform
      best-effort cancel/close without reporting a verified TLS connection.
- [x] CALL-020J fake-socket tests cover short exact reads/writes, EOF, finite
      timeout/callback/size bounds, zero versus partial/unknown progress,
      single-byte memoryview enforcement, connection-ID mutation, concurrent
      close/quiescence, buffer/reference clearing and end-to-end handoff through
      CALL-020I. They perform no real TLS, socket, network or hardware action.
- [x] CALL-020K supplies a default-off exact-port wrapper beneath CALL-020H,
      with a caller-injected factory plus an optional lazy pyserial opener; it
      never enumerates/guesses ports, auto-connects, installs a dependency or
      emits in-band control.
- [x] CALL-020K fake-driver tests cover disabled/invalid no-open behavior,
      exact open arguments, optional-dependency failure, partial-open cleanup,
      single active ownership, non-reusable reconnect identity, observable
      driver mutation, short I/O, zero/partial/unknown timeout progress,
      concurrent cancel/close quiescence, redacted errors/audit and K-to-H ROM
      prefix resynchronization. They open no real OS port or hardware path.
- [x] CALL-020L composes K-to-H and J into the actual existing CALL-020C bridge
      behind inert construction plus explicit single-use open/start calls; all
      session, role, endpoint, source-clock and per-leg connection bindings
      fail closed before media.
- [x] CALL-020L rolls back both legs on staged-open or run failure, supports
      out-of-band cancellation and quiescent close, and returns only redacted
      counters with neutral transport-provenance non-claims.
- [x] CALL-020L focused tests use fake transports while actually invoking the
      concurrent bridge and cover dormant/default-disabled behavior, no-media
      admission, healthy duplex, identity/bounds rejection, staged rollback,
      single use, concurrent cancel, cleanup, redaction and no autorun/I/O
      discovery. They are not real serial, TLS, network, device or audio
      evidence.
- [x] CALL-020M supplies a default-off host phase owner and plan-only CLI over
      G intent plus K/L, with one-shot authorization, exact-port-only input,
      externally injected TLS/control connectors and metadata-only telemetry.
- [x] CALL-020M fails closed before every connector callback when the missing
      repository host-to-G control connector is not injected; no in-band media
      control or false wearable-control claim is substituted.
- [x] CALL-020M keeps the legacy out-of-band attestation valid while accepting
      a logically separated non-interleaved alternative; logical preflight now
      requires one concrete dual-role P connector object rather than claiming
      a second/OOB control endpoint.
- [x] CALL-020M focused fakes cover token clearing/nonreuse, strict phase and
      idempotency order, lost-prepare cleanup, partial-TLS ownership contract,
      bounded cancellation/quiescence, concurrent lifecycle close, recoverable
      wearable and local-endpoint cleanup failures, safe L counters, runtime
      telemetry and zero-I/O plan/preflight paths. They provide no hardware/
      network evidence.
- [x] CALL-020N supplies a default-off exact-numeric-peer/source-bound TLS
      connector while reusing I/J/M types; the CLI still cannot execute it.
- [x] CALL-020N requires exact hostname/SNI, one caller CA source, TLS 1.2/1.3,
      ALPN, actual connected source/peer route verification and one finite
      overall deadline with remaining connect/handshake/authentication bounds.
- [x] CALL-020N retains the exact partial transport when bounded close attempts
      cannot confirm cleanup; M retries it and cannot report `closed` while it
      remains pending. The legacy clean-before-raise attestation remains valid,
      while N requires the new retain-for-retry alternative and retry shape.
      Late returned bundles are owned before rejection and cleaned.
- [x] CALL-020N never fabricates the external session decision and remains
      blocked without the missing real authenticator; fake tests cover exact
      route/trust configuration, failure cleanup, J admission and M injection
      without opening a real socket or assuming a second control endpoint.
- [x] CALL-020P supplies a default-off, API-only host single-USB phase connector
      over one caller-injected already-open exact driver; it has no opener,
      discovery, reconnect, executable CLI or construction-time I/O.
- [x] CALL-020P uses bounded strict `EGLC` v1 CONTROL frames, full-request
      stable operation IDs, explicit duplicate acknowledgements and terminal
      partial/unknown progress; CRC is explicitly framing-only, not auth.
- [x] CALL-020P transfers the same pointer/generation through a one-shot
      borrowed K facade only after START/ACK. K close returns rather than
      physically closes it; M emits no post-START CONTROL and keeps RESULT,
      remote cleanup and device termination unconfirmed.
- [x] CALL-020P fake-only tests cover phase races, CRC/identity rejection,
      partial I/O, lost/duplicate ACK, ownership/cleanup recovery and M/L/K
      ordering without opening serial/network/audio/hardware I/O.
- [x] CALL-020P.1 drains only a bounded text ROM/early-boot prefix before the
      first PREPARE write; fragmented/partial EGLC, unknown progress and
      byte/call/deadline overflow fail closed without an extra write.
- [x] CALL-020Q supplies a default-off, app-main-dormant device `EGLC` parser
      and same-core lease-backed responder with bounded frames, strict latest-
      operation replay and terminal partial/unknown progress.
- [x] CALL-020Q transmits and drains START ACK before its irreversible lease
      handoff, emits no later CONTROL/RESULT byte, retains failed-install lease
      cleanup, closes a prepared runner if telemetry capture fails, and keeps
      frame acquisition time separate from the accepted operation budget.
- [x] CALL-020Q focused source/boundary checks and dedicated ESP32-S3
      compile/link are offline evidence only; device USB execution, authenticated
      control binding, post-stop telemetry/result and P0-CALL remain unverified.
- [x] CALL-020R adds a separately selected, default-off, single-pinned-task
      device owner with one CONTROL deadline and local post-MEDIA
      force-safe/cancel/four-worker/bounded-join/runner-close/lease-return/
      physical-close proof. It emits no post-START byte and adds no auth,
      RESULT, LTE or product-certification claim.
- [x] CALL-020R cleanup is phase-idempotent: incomplete join, runner-close,
      lease-return or uninstall proof retains the sole owner in a fail-closed
      retry loop with bounded backoff. Reinitialization is rejected before any
      context clear, and exact responder error/reason diagnostics survive
      eventual cleanup.

# Acceptance

- [ ] The selected configurable engineering codec and bounded transport/relay
      baseline, signaling/encryption boundary, frame timing and PC bridge are
      explicit. PCM/ADPCM/Opus plus UDP/WebSocket or a WebRTC-compatible
      candidate may be compared; browser-grade WebRTC is not a prerequisite.
- [ ] At least ten setup attempts and one ten-minute two-way media run prove
      microphone uplink and speaker downlink over the actual SIM7670G network
      interface, with observable RTT/loss/jitter/gaps/reconnect state.
- [ ] Auth, encryption limitation, retry bound and failure state are explicit.
- [ ] A controlled loss/jitter/media-blackout scenario recovers within its
      declared budget or terminates honestly as `failed`.
- [ ] The result is labelled engineering PoC, not final RTC or `P0-CALL PASS`.

# Validation Commands

```powershell
python -m unittest quality_tests.test_ego_call_serial_adapter -v
python -m unittest quality_tests.test_ego_call_authenticated_relay -v
python -m unittest quality_tests.test_ego_call_tls_stream_adapter -v
python -m unittest quality_tests.test_ego_call_os_serial_wrapper -v
python -m unittest quality_tests.test_ego_call_pc_endpoint_composition -v
python -m unittest quality_tests.test_ego_call_operator_control -v
python -m unittest quality_tests.test_ego_call_single_usb_phase_connector -v
python -m unittest quality_tests.test_ego_call_media_probe quality_tests.test_ego_call_media_runtime quality_tests.test_ego_call_media_io quality_tests.test_ego_call_concurrent_bridge quality_tests.test_call020_media_adapter_core quality_tests.test_call020_usb_serial_jtag_endpoint quality_tests.test_call020_wearable_composition quality_tests.test_call020_operator_runner quality_tests.test_ego_call_serial_adapter quality_tests.test_ego_call_authenticated_relay quality_tests.test_ego_call_tls_stream_adapter quality_tests.test_ego_call_os_serial_wrapper quality_tests.test_ego_call_pc_endpoint_composition quality_tests.test_ego_call_operator_control quality_tests.test_ego_call_single_usb_phase_connector -v
python -m unittest quality_tests.test_ego_call_contract quality_tests.test_ego_call_fixture quality_tests.test_ego_call_media_probe quality_tests.test_ego_call_media_runtime quality_tests.test_ego_call_media_io quality_tests.test_ego_call_concurrent_bridge quality_tests.test_call020_media_adapter_core quality_tests.test_call020_usb_serial_jtag_endpoint quality_tests.test_call020_wearable_composition quality_tests.test_call020_operator_runner quality_tests.test_ego_call_serial_adapter quality_tests.test_ego_call_authenticated_relay quality_tests.test_ego_call_tls_stream_adapter quality_tests.test_ego_call_os_serial_wrapper quality_tests.test_ego_call_pc_endpoint_composition quality_tests.test_ego_call_operator_control quality_tests.test_ego_call_single_usb_phase_connector quality_tests.test_audio_loop_firmware
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

The Python endpoint tests above are source/static contract assertions; the test
named `test_static_wiring_is_default_disabled_and_uninstantiated` does not
compile or execute C. Actual ESP32-S3 C compilation is a separate ESP-IDF
build-only check (after loading the repository-pinned ESP-IDF 5.4.2 profile):

```powershell
Push-Location firmware/audio_loop
idf.py -B build_call020e_default -D "SDKCONFIG=$PWD/build_call020e_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020e_dedicated -D "SDKCONFIG=$PWD/build_call020e_dedicated/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_usb_endpoint.defaults" build
Pop-Location
```

The CALL-020F Python tests are likewise static assertions; despite its name,
`test_static_wiring_is_default_disabled_and_app_main_uninstantiated` does not
compile or execute C. Actual CALL-020F compilation uses fresh ESP-IDF builds:

```powershell
Push-Location firmware/audio_loop
idf.py -B build_call020f_default -D "SDKCONFIG=$PWD/build_call020f_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020f_dedicated -D "SDKCONFIG=$PWD/build_call020f_dedicated/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_wearable.defaults" build
Pop-Location
```

The CALL-020G Python tests are also source/static wiring assertions and do not
compile or execute C. Actual final-ELF retention and sizing use fresh builds:

```powershell
Push-Location firmware/audio_loop
idf.py -B build_call020g_default_final -D "SDKCONFIG=$PWD/build_call020g_default_final/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020g_runner_final -D "SDKCONFIG=$PWD/build_call020g_runner_final/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_operator_runner.defaults" build
Pop-Location
```

The CALL-020R focused checks and build-only profiles are:

```powershell
python -m unittest quality_tests.test_call020_device_control_owner quality_tests.test_call020_device_control_responder -v
Push-Location firmware/audio_loop
idf.py -B build_call020r_default -D "SDKCONFIG=$PWD/build_call020r_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020r_owner -D "SDKCONFIG=$PWD/build_call020r_owner/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_device_owner.defaults" build
Pop-Location
```

The focused command is authorized for the offline slice. Full repository
verification remains a task-integration command. Operator-approved hardware,
SIM, carrier, VPS/RTC and audio commands must be added before runtime dispatch;
no production credentials may enter the repository.

# Completion Evidence

- Changed files: this packet, `pc_simulator/ego_call_media_probe.py`,
  `pc_simulator/ego_call_media_runtime.py`,
  `pc_simulator/ego_call_media_io.py`,
  `pc_simulator/ego_call_concurrent_bridge.py`,
  `pc_simulator/ego_call_serial_adapter.py`,
  `pc_simulator/ego_call_authenticated_relay.py`,
  `pc_simulator/ego_call_tls_stream_adapter.py`,
  `pc_simulator/ego_call_os_serial_wrapper.py`,
  `pc_simulator/ego_call_pc_endpoint_composition.py`,
  `firmware/audio_loop/main/CMakeLists.txt`,
  `firmware/audio_loop/main/Kconfig.projbuild`,
  `firmware/audio_loop/main/call020_media_adapter_core.c`,
  `firmware/audio_loop/main/call020_media_adapter_core.h`,
  `firmware/audio_loop/main/call020_usb_serial_jtag_endpoint.c`,
  `firmware/audio_loop/main/call020_usb_serial_jtag_endpoint.h`,
  `firmware/audio_loop/main/call020_wearable_composition.c`,
  `firmware/audio_loop/main/call020_wearable_composition.h`,
  `firmware/audio_loop/main/call020_device_control_responder.c`,
  `firmware/audio_loop/main/call020_device_control_responder.h`,
  `firmware/audio_loop/main/call020_device_control_owner.c`,
  `firmware/audio_loop/main/call020_device_control_owner.h`,
  `firmware/audio_loop/main/call020_device_control_owner_boot.c`,
  `firmware/audio_loop/sdkconfig.call020_usb_endpoint.defaults`,
  `firmware/audio_loop/sdkconfig.call020_wearable.defaults`,
  `firmware/audio_loop/sdkconfig.call020_device_owner.defaults`,
  `firmware/audio_loop/README.md`,
  `quality_tests/test_ego_call_media_probe.py`, and
  `quality_tests/test_ego_call_media_runtime.py`, and
  `quality_tests/test_ego_call_media_io.py`, and
  `quality_tests/test_ego_call_concurrent_bridge.py`, and
  `quality_tests/test_ego_call_serial_adapter.py`, and
  `quality_tests/test_ego_call_authenticated_relay.py`, and
  `quality_tests/test_ego_call_tls_stream_adapter.py`, and
  `quality_tests/test_ego_call_os_serial_wrapper.py`, and
  `quality_tests/test_ego_call_pc_endpoint_composition.py`, and
  `pc_simulator/ego_call_operator_control.py`, and
  `quality_tests/test_ego_call_operator_control.py`, and
  `pc_simulator/ego_call_single_usb_phase_connector.py`, and
  `quality_tests/test_ego_call_single_usb_phase_connector.py`, and
  `quality_tests/test_call020_media_adapter_core.py`, and
  `quality_tests/test_call020_usb_serial_jtag_endpoint.py`, and
  `quality_tests/test_call020_wearable_composition.py`,
  `quality_tests/test_call020_device_control_owner.py`,
  `reports/board_validation/CALL-020-20260902-001/call020e_build_evidence.md`,
  and
  `reports/board_validation/CALL-020-20260902-001/call020f_build_evidence.md`,
  and
  `reports/board_validation/CALL-020-20260902-001/call020m_host_control_entry_evidence.md`,
  and
  `reports/board_validation/CALL-020-20260902-001/call020p_single_usb_phase_connector_evidence.md`.
- Retained operator-runner result: CALL-020G adds a default-off singleton
  lifecycle API and a dedicated five-byte inert boot entry; the ordinary
  `app_main.c` remains unmodified. G source/static tests passed `15/15`, D/E/F/G
  passed `48/48`, the focused CALL set passed `99/99`, and the combined CALL,
  contract and CALL-010 static set passed `131/131`. The tests do not execute
  C. Fresh ESP-IDF 5.4.2 default and dedicated builds passed; all local main
  sources compiled under generated commands containing `-Wall -Werror=all`.
  One deprecation warning remains in the pinned external `esp_lvgl_port`
  dependency, not in a CALL source. The default binary stayed `0x2fb70`
  (195,440) bytes, retained the ordinary 206-byte `app_main`, enabled the USB
  Serial/JTAG console and linked no CALL symbol. The dedicated binary is
  `0x3e280` (254,592) bytes with hash
  `7464667C9A313B135B5AF7AF2EE5D2136CE904C9F537A09BED969E487B3A4072`.
  Its generated config enables D/E/F/G and output volume 55, disables autorun,
  both consoles and app/bootloader logging, and moves only selected non-ISR
  FreeRTOS/ring-buffer functions to flash. `nm`/map show the five-byte inert
  `app_main`, all D/E/F/G APIs and `.bss.s_runner` at 44,216 bytes, proving the
  chain is in the final ELF rather than link-dead. IDF reports 90,703/341,760
  bytes shared D/IRAM used and 251,057 free. `.iram0.text` is 49,923 bytes;
  16,383 bytes occupy the first IRAM window and 34,567 bytes occupy executable
  D/IRAM, so its displayed one-byte first-window margin is not alone a runtime
  blocker. Known maximum requested runtime payload is 37,456 bytes before heap
  metadata, driver control objects, DMA descriptors/events and codec/BSP heap;
  actual free/min-free internal heap and four task watermarks remain mandatory
  run evidence. Exact build, symbols, budgets and non-claims are recorded in
  `reports/board_validation/CALL-020-20260902-001/call020g_retained_runner_evidence.md`.
  No image was flashed or booted and no USB/audio/modem/network path was opened.
- Final-source repository verification passed `1207/1207` tests with two
  documented skips (`scripts/verify.ps1`, exit 0). The formerly missing
  concurrent SOS-010E paths have since landed; final CALL-020I
  `context_lint.py`, Python compile and diff/whitespace checks passed.
- Offline host serial result: CALL-020H focused tests passed `15/15`, including
  a blocking-write cancellation fixture proving `close()` waits for direction
  quiescence and adapter-owned buffer clearing; the prior CALL-020 focused
  regression passed `113/113`, and the prior combined CALL contracts/fixtures
  plus CALL-010 static regression passed `145/145` on
  2026-09-02. Tests use only caller-injected process-local doubles. They prove
  bounded stream-state behavior and one healthy handoff through the existing
  concurrent bridge, not an OS serial wrapper, connector, USB controller or
  device. No port was enumerated/opened and no device, SIM, network, VPS or
  audio action occurred.
- Offline authenticated-relay result: CALL-020I focused tests passed `15/15`;
  the updated CALL-020 focused regression passed `129/129`, and the combined
  CALL contracts/fixtures plus CALL-010 firmware-static regression passed
  `161/161` on 2026-09-02. Coverage includes pre-run cancellation without a
  registry reservation, both externally injected decisions
  required before media, exact session/role/endpoint/peer/clock and actual
  stream-connection binding, swapped streams, expiration, duplicate/hijack/
  cross-session rejection, bounded non-evicting registry capacity, healthy
  complete-frame duplex through the existing four-worker bridge, disconnect,
  external cancellation, concurrent single-use state preservation, buffer
  clearing and redacted metadata. The registry truthfully reports that raw
  routing IDs remain in bounded process memory for duplicate guards while no
  result/audit exposes, logs or persists them. Tests use injected in-memory
  streams and decisions; no authenticator, TLS handshake, listener, socket,
  provider, device, SIM, network, VPS or audio path was executed.
- Offline connected-TLS adapter result: CALL-020J focused fake-socket tests
  passed `18/18`; the updated CALL-020 focused regression passed `147/147`, and
  the combined CALL contracts/fixtures plus CALL-010 firmware-static regression
  passed `179/179` on 2026-09-02. Coverage includes default-disabled and invalid
  construction cleanup, frozen external verification attestation, exact peer/
  ALPN/TLS-version/connection/session binding, bounded fragmented reads/writes,
  EOF and timeout progress semantics, callback/size bounds, rejection of
  multibyte memoryviews before copying, mutable connection-ID rejection,
  concurrent read/write cancellation and quiescent close, redacted audit, and
  two adapters handing complete traffic to CALL-020I. All socket objects were
  process-local fakes; no TLS handshake, certificate verification, listener,
  connector, DNS, OS socket, serial/device, SIM, network, VPS or audio action
  occurred. The injected attestation remains a consistency input, not proof of
  PKI or authenticator security.
- Offline explicit-OS-serial result: CALL-020K focused fake-driver tests passed
  `19/19`; the updated CALL-020 focused regression passed `166/166`, and the
  combined CALL contracts/fixtures plus CALL-010 firmware-static regression
  passed `198/198` on 2026-09-02. Coverage includes default-disabled and invalid
  no-open behavior, exact port/baud/finite-timeout/exclusive arguments, falsey
  dependency injection, optional lazy pyserial import/open via a fake module,
  partial-open cleanup, redacted factory/registry failure causes, one active
  process owner, non-reusable connection identities, observable driver
  port/open/baud/exclusive mutation, short reads/writes, proven zero-progress
  versus terminal partial/unknown progress, strict byte views, concurrent
  cancellation/close quiescence, safe callback lookup, reference clearing and
  ROM-prefix/EGLM handoff into CALL-020H. Python compile and scoped whitespace
  checks passed. `context_lint.py` was blocked only by two declared but not yet
  created concurrent SOS-010 paths (`sos_pending_edge_journal_nvs/` and its
  focused test); neither is a CALL-020K path. No port enumeration or real
  pyserial/COM/USB/device, SIM, TLS/socket, network, VPS or audio action
  occurred. The OS/driver's actual exclusive-open and cancellation behavior,
  connector identity and live K/H-plus-J bridge remain unverified.
- Offline PC endpoint-composition result: CALL-020L focused tests passed
  `15/15`; the updated CALL-020 focused regression passed `181/181`, and the
  combined CALL contracts/fixtures plus CALL-010 firmware-static regression
  passed `213/213` on 2026-09-02. Coverage includes inert/default-disabled
  construction, explicit no-media open, one exact identity across H/J/C,
  separate internally exact serial/TLS connection lifetimes, transport bounds,
  staged rollback, single-use open/start, concurrent cancellation, quiescent
  close, reference/buffer cleanup and redacted metadata. The healthy case
  executes the existing four-worker `ConcurrentDuplexMediaBridge.run` over
  fake K-to-H and J legs in both directions. Its result says only that the
  bridge completed full duplex; this layer did not evaluate transport
  provenance and proves no real serial/TLS connection or `P0-CALL`. Python
  compile and scoped whitespace checks passed. No port enumeration, real
  pyserial/COM/USB/device, OS socket/TLS handshake, SIM, network, VPS or audio
  action occurred. Real connector/driver behavior and a caller-supplied TLS
  handshake/PKI/authentication path remain unverified. Global `git diff
  --check` passed with only existing line-ending conversion warnings.
  `context_lint.py` was blocked by the concurrently declared but not yet
  created `quality_tests/test_sos_delivery_composition.py`; that path is owned
  by SOS-010 and is outside CALL-020L.
- Offline host-control result: CALL-020M focused tests passed `24/24` on
  2026-09-03. Construction, plan-only CLI and preflight executed zero
  connector callbacks. The missing host-to-G wearable connector failed closed
  before TLS/serial/media, and accepted-then-lost or malformed prepare replies
  exercised stable-operation-ID bounded-retry cancel/join/close cleanup. Race
  fixtures prove `close` rechecks in-flight `open`/`start`, and M refuses to
  report `closed` until the media worker is quiescent and wearable closure is
  confirmed; transient closure failure remains recoverable. Local endpoint
  closure is tracked separately from stop/telemetry errors; its exact reference
  is retained for retry after an exception, and permanent failure never reports
  `closed`. The fake
  executable path verified descriptor-to-L configuration, strict phases,
  one-shot token clearing, run-ID nonreuse, safe counter retention, host
  elapsed/termination metadata and injected heap/four-worker stack snapshots.
  The TLS partial-open self-cleanup requirement and post-return timeout (not
  hard-preemption) boundary are explicit; real connector enablement remains
  blocked pending its own bounded deadline/cancellation review. Python compile,
  focused regression, context lint and
  scoped diff checks are recorded in
  `reports/board_validation/CALL-020-20260902-001/call020m_host_control_entry_evidence.md`.
  Root's final CALL selection through M passes `237/237`.
  CALL-020P later adds only the offline host same-handle connector; its matching
  device control wire/runtime remains absent. CALL-020N adds the default-off
  host TLS implementation below. No COM/USB/device, TLS socket, network, SIM,
  VPS, audio, flash or
  hardware action occurred, and `P0-CALL` remains `NOT_RUN`.
- Offline exact-route host TLS result: CALL-020N focused tests passed `44/44`
  on 2026-09-03; the J/L/M/N combined regression passed `77/77`. Process-local
  socket/context/authenticator fakes prove exact `AF_INET` numeric peer and
  source bind plus actual connected-route checks, unchanged hostname/SNI,
  single caller CA loading, TLS 1.2/1.3, ALPN, one overall open deadline,
  finite I/O timeout, retained/retried partial-failure cleanup, late-bundle
  cleanup, exact external decision binding, J admission and injection into M.
  The connector is default-off,
  single-use, exposes no executable CLI path, calls no resolver and does not
  manufacture an authentication decision. A real application/session
  authenticator is absent, and its callback timeout currently has only a
  post-return check; runtime enablement therefore remains blocked pending that
  independently reviewed implementation and hard cancellation bound. N does
  not depend on a second wearable control endpoint and is compatible with a
  same-USB-handle `CONTROL -> MEDIA -> RESULT` contract. P now supplies the
  default-off host CONTROL-to-MEDIA handoff, while its device counterpart,
  RESULT and runtime integration remain blocked and unverified. Exact
  results and non-claims are recorded in
  `reports/board_validation/CALL-020-20260902-001/call020n_host_tls_connector_evidence.md`.
  No OS socket, DNS, TLS handshake, network, COM/USB/device, SIM, VPS, media,
  audio, flash or hardware action occurred; `P0-CALL` remains `NOT_RUN`.
- Offline same-USB host phase result: CALL-020P/P.1 focused fake-driver tests
  passed `27/27` on 2026-09-03; K/L/M/P passed `105/105`. The tests prove strict
  `EGLC`
  framing/CRC/JSON bounds, complete-request idempotency, lost/duplicate ACK
  handling, terminal partial progress, START uncertainty, serialized
  pointer/generation ownership, one-shot borrowed-facade transfer/return and
  retryable physical-close confirmation, plus bounded ROM-prefix drain,
  fragmented/partial-magic rejection, byte/call/deadline limits and
  zero/partial/unknown drain progress. M fake integration proves the order
  `prepare -> TLS ready -> START/ACK -> same-handle transfer -> L open`, early
  local cancellation, and post-transfer cleanup without any wearable
  cancel/join/close/telemetry or RESULT claim. Exact results and non-claims are
  recorded in
  `reports/board_validation/CALL-020-20260902-001/call020p_single_usb_phase_connector_evidence.md`.
  The connector is default-off and has no CLI/opener/discovery/reconnect path.
  Q now supplies a compile-only device `EGLC` counterpart; authenticated
  control/session binding, callback hard preemption, RESULT wire, post-stop
  telemetry, device runtime/PA-safe termination, exact-board behavior and
  actual media remain unimplemented or unverified. No real port/socket/network/
  device/audio/SIM/VPS/flash action occurred and `P0-CALL` remains `NOT_RUN`.
- Offline device CONTROL responder result: CALL-020Q focused checks passed
  `20/20` on 2026-09-03. P/Q integration checks passed `47/47` after the
  blocking install-rollback, prepared-runner cleanup and deadline audit fixes.
  Frame acquisition and the device operation budget are separate: the latter
  begins only after a complete frame passes bounded wire validation, while the
  host retains its independent end-to-end deadline. A clean dedicated ESP-IDF
  v5.4.2 ESP32-S3 build retained Q with
  console/app/bootloader logs disabled and an inert boot stub; final exact
  size/hash are recorded in
  `reports/board_validation/CALL-020-20260902-001/call020q_device_control_responder_evidence.md`.
  These checks do not execute the device USB pump. No firmware, serial, board,
  modem, network or audio action occurred; `P0-CALL` remains `NOT_RUN`.
- Offline device lifecycle-owner result: CALL-020R and Q focused checks passed
  `33/33` on 2026-09-04. Fresh ESP-IDF 5.4.2 default and dedicated R builds
  passed against ESP32-S3. The default binary remained `0x2fb70` bytes with
  `81%` of the smallest app partition free and SHA-256
  `47E4574BE34AD70507193F56F753E7CD4C3DA97B4E9563EB9FCB56A2A33A519D`;
  the R-profile binary is `0x45930` bytes with `73%` free and SHA-256
  `8EF932C6F5A9E794FBBAEDEB26E9B20B42D85C437DB432940709DA6A5275EA05`.
  The dedicated build selects console/log NONE and the
  one-task owner boot entry; the default and retained G/Q profiles do not.
  Source checks cover total CONTROL deadline placement, same-core ownership,
  four-worker termination as an immediate cancel trigger, bounded quiescence,
  phase-idempotent cleanup recovery with bounded backoff, singleton-init guard,
  exact responder diagnostics, consistent deadline boundaries,
  runner-close/lease-return/physical-close order, task-create failure and
  absence of RESULT/post-START writes. Four actual-owner C harness variants
  inject first-attempt join, runner-close, lease-return and uninstall failures;
  they cross-compiled for ESP32-S3 here but were not executed because no native
  target toolchain was available. This is source and compile/link evidence
  only. Neither image was flashed or booted; no
  serial, USB, audio, board, SIM, modem, TLS or network action occurred, and
  `P0-CALL` remains `NOT_RUN`.
- Post-fix independent review on 2026-09-04 found and closed the
  CONTROL-to-MEDIA return-boundary race: `MEDIA_STARTED` now takes ownership
  precedence over the owner's post-serve CONTROL deadline/clock check. An exact
  total-deadline hit or invalid clock after successful handoff/start forces
  local cancel and the media finalizer; it cannot enter the pre-media abort
  loop. The focused R/Q set passed `33/33`. Its six actual-owner-C harness
  variants compiled, linked and executed with pinned Espressif LLVM's native
  Windows x86 target: four first-attempt cleanup failures plus exact-deadline
  and invalid-clock post-MEDIA boundaries. Both boundary variants asserted zero
  `abort_local` calls and complete runner/lease/physical-close cleanup. This was
  offline host execution only; no firmware, serial, USB, audio, board, SIM,
  modem, TLS or network path was accessed.
- Focused test result: `9/9` passed on 2026-08-23; the combined CALL-001/CALL-020
  regression set passed `33/33` at that baseline. On 2026-09-02 the current
  CALL contract/session/evaluator/runtime set passed `44/44`. One full
  `scripts/verify.ps1` run passed `943/943`; a later shared-worktree rerun found
  `18` errors among `946` tests in concurrent location-state runtime work,
  outside this packet's paths. Final integration verification is therefore
  pending after that independent work stabilizes; the CALL-focused set stayed
  green after the final runtime change.
- CALL-020B local I/O result: `21/21` focused media-I/O tests passed on
  2026-09-02; the current CALL contract/fixture/evaluator/runtime/I/O set passed
  `65/65`. Coverage includes exact framing, CRC/identity/sequence rejection,
  pre-I/O cross-session isolation, healthy duplex, one-way rejection,
  independent queue backpressure, safe retry, terminal partial/unknown-progress
  timeout handling, deterministic replay, fake transport and media-buffer
  zeroing, `recv_into` socket-buffer handling, explicit source binding under
  socket/TLS fakes, authorization-before-socket gating, offline preflight
  redaction, bounded oversized-token rejection/zeroing, and metadata-only CLI
  output. No actual network or hardware I/O occurred. The shared worktree full
  suite passed `985/985` immediately before the final bounded token-read change;
  the final CALL-focused set and context/diff checks passed afterward.
- Executable-seam result: runtime tests passed `11/11` on 2026-09-02; the
  evaluator plus runtime focused set passed `20/20`. Tests cover healthy duplex,
  one-way rejection, bounded blackout recovery/failure, independent queue
  backpressure, delay/reorder, identity/profile/boundary rejection,
  deterministic replay, buffer zeroing and metadata-only CLI output. No socket,
  network, board, modem or audio-device action occurred.
- Concurrent-bridge result: CALL-020C tests passed `10/10` on 2026-09-02.
  Coverage uses only process-local ordered-stream doubles and explicit
  barriers: healthy four-worker duplex, one-direction blocking isolation,
  deadline and queue-backpressure failure, terminal unknown-progress and
  post-header timeout, propagated worker failure with redacted metadata,
  bounded external stop/join, pre-I/O identity rejection, deterministic source
  cadence and complete mutable-media zeroing. No real I/O occurred.
  The CALL contract/fixture/evaluator/runtime/I/O/concurrent regression set
  passed `75/75`; `py_compile`, `context_lint` and scoped diff checks passed.
- Wearable framing-core result: CALL-020D added a compiled but
  default-uninstantiated `call020_media_adapter_core`; its new focused
  **source/static** assertions passed `11/11` on 2026-09-02. The complete
  CALL contract/fixture/evaluator/runtime/I/O/concurrent/core plus existing
  CALL-010 firmware-static regression passed `94/94`. A clean ESP-IDF 5.4.2
  ESP32-S3 default build and a post-change incremental rebuild passed; the
  adapter source compiled under the generated `-Wall -Werror=all` command.
  The application binary was `0x2fb70` bytes with `0xd0490` bytes free in the
  smallest app partition. `py_compile` and the seven-file scoped diff check
  passed. The focused Python tests inspect source/contracts and execute the
  existing Python reference encoder; they do not execute the C core. No
  firmware was flashed and no serial, USB media, audio, modem or network I/O
  occurred. An initial integration-wide `context_lint` attempt observed a
  transient missing file in concurrent SOS work; after that work landed, the
  final `context_lint` rerun passed. The final repository verification passed
  `1051/1051` tests.
- Wearable ordered-byte endpoint result: CALL-020E added a caller-owned,
  default-disabled and uninstantiated USB Serial/JTAG driver adapter. Its
  endpoint-only Python source/static assertions passed `11/11`; the focused
  CALL evaluator/runtime/I/O/concurrent/core/endpoint set passed `73/73`, and
  the CALL contract/fixture plus CALL-010 static combination passed `105/105`.
  These Python endpoint tests do not execute C. Separate clean ESP-IDF 5.4.2
  ESP32-S3 default and dedicated-profile builds plus final-source incremental
  rebuilds passed on 2026-09-02; both compiled
  `call020_usb_serial_jtag_endpoint.c` under the
  generated `-Wall -Werror=all` command. The default generated configuration
  did not enable either CALL-020 symbol and retained the USB Serial/JTAG
  console; its
  application binary was `0x2fb70` bytes with `0xd0490` bytes free. The
  dedicated generated configuration enabled both CALL-020 symbols and
  resolved `ESP_CONSOLE_NONE`, `ESP_CONSOLE_SECONDARY_NONE`,
  `LOG_DEFAULT_LEVEL_NONE` and `BOOTLOADER_LOG_LEVEL_NONE`, with both USB
  Serial/JTAG console choices unset; its application binary was `0x2a300`
  bytes with `0xd5d00` bytes free. These were build-only operations: no
  firmware was flashed and no device, USB, serial, audio, modem or network
  interface was opened. `context_lint` passed, and the final repository
  verification passed `1103/1103` tests with one unrelated native-host-compiler
  test skipped; its ESP cross-compile counterpart passed. Exact commands and
  generated-symbol evidence are in
  `reports/board_validation/CALL-020-20260902-001/call020e_build_evidence.md`.
- Wearable composition result: CALL-020F added a default-disabled,
  `app_main`-uninstantiated composition of the actual safe codec/I2S path,
  four direction-isolated workers, two single-owner framing cores and the
  exclusive USB endpoint. Its focused **source/static** assertions passed
  `11/11`; the D/E/F static set passed `33/33`. Those Python tests do not
  execute C. Separate ESP-IDF 5.4.2 default and console-free dedicated builds
  passed and compiled the final composition source under a generated command
  containing `-Wall -Werror=all`. Default output was `0x2fb70`; dedicated
  output was `0x2a300`. Generated configuration proved the ordinary CALL core
  disabled and USB console retained, while the dedicated profile enabled
  D/E/F, selected CALL volume 55, disabled CALL-010 autorun, selected no
  primary/secondary console and no app/bootloader logging, and unset both USB
  Serial/JTAG console choices. No device or I/O action occurred. Exact commands,
  hashes and non-claims are in
  `reports/board_validation/CALL-020-20260902-001/call020f_build_evidence.md`.
  Final validation passed F `11/11`, D/E/F `33/33`, the CALL focused set
  `84/84`, and the combined CALL/contracts/CALL-010 set `116/116`.
  `context_lint` passed at that validation point, as did `py_compile` and
  scoped whitespace/diff checks. The latest shared-worktree lint rerun then
  found four declared-but-not-yet-created paths in concurrent SOS work; no
  CALL path was implicated. A repository-wide rerun
  executed `1165` tests and retained one unrelated concurrent SOS static-text
  assertion failure; no CALL test failed, so repository verification is
  truthfully pending rather than recorded as PASS.
  Target DWARF gives a 43,736-byte caller-owned composition context and four
  configured 4,096-byte task stacks (16,384 bytes before TCB/driver/DMA
  allocations). The dedicated image is 172,654 bytes unpadded / 172,800 bytes
  padded, with 47,039 bytes static D/IRAM and 16,383 of 16,384 bytes static
  IRAM used. Because `app_main` still does not reference the component, it is
  link-dead: that image size is not executable composition evidence. The
  one-byte static-IRAM margin and absent runner/final map are explicit blockers
  before an operator image.
- Read-only interface preflight: evidence
  `reports/board_validation/CALL-020-20260902-001/` records Windows enumeration
  of connectivity-node-001 as an up/configured SIM7670G RNDIS interface. This
  was operating-system inspection only: no intentional traffic, modem/serial
  command, network change or board change occurred. LTE registration, PDP or
  Internet reachability, carrier route, RTC/media and `P0-CALL` remain
  `not_tested` / `NOT_RUN`. This does not supersede the recorded source-bound
  ping/curl timeout; actual egress remains a fail-closed blocker.
- Hardware/VPS result: PC-side RNDIS enumeration is `observed`; actual
  LTE/PDP reachability, sustained RTC and two-way media are `NOT_RUN` /
  `unverified`. No board, SIM, network, VPS, RTC, microphone or speaker action
  was performed by the executable offline slice.
- Gate result: `P0-CALL NOT_RUN`. Offline fixture PASS cannot advance it.
- Remaining risks: live PC bridge, carrier route, RTC selection, security,
  real packet capture, weak-network recovery, device audio dependency and
  product applicability. A dormant USB Serial/JTAG driver adapter now exists,
  but its exact connector/controller path, host-open/reconnect behavior,
  sustained concurrent transfer, driver lifecycle latency and console-free
  recovery path remain unverified. Worker/audio/PA composition, complete stream
  reassembly and the dedicated same-core operator runner now link but have not
  run. The separate control trigger, real K-backed OS-port/connector proof,
  matching deployed TLS listener/connector and handshake, PKI/external
  authenticator, a real connected socket satisfying J's finite-timeout and
  prompt-cancel contract, plus the verified interface-name/source-IP route,
  are not implemented/proved. CALL-020H provides bounded ROM-prefix/EGLM
  resynchronization behind a caller-injected offline serial seam, but has not
  opened or proven the physical path. CALL-020I now provides the process-local
  matching admission/forwarding core, but has not performed a TLS handshake or
  connected any real endpoint. CALL-020J now validates and adapts a fake,
  caller-injected already-connected TLS socket shape; it does not create the
  real handshake, trust decision, connection or cancellation wrapper. The final driver
  install/uninstall APIs have no timeout parameters, so runtime measurement is
  still required. CALL-020C verifies PC-side concurrent orchestration,
  CALL-020D compiles framing/queue semantics, and CALL-020E compiles the
  ordered-byte endpoint seam only.
  CALL-020G has now resolved F's link-dead blocker and bounded the endpoint
  rings to 4096 bytes per direction. It has not executed the runner. CALL-020H
  closes the offline host-resynchronizer gap. CALL-020K adds the default-off,
  exact-port optional pyserial opening seam beneath H, but its real factory,
  OS exclusivity/cancellation, connector and physical path were not run.
  CALL-020L now supplies the default-off K-to-H plus J-to-C composition and
  executes the real concurrent bridge under process-local fakes, but has not
  opened or proven either live transport and deliberately has no control
  trigger, socket connector or TLS handshake.
  A reviewed trigger/control seam, connector/reconnect proof, deployed TLS
  transport plus external authenticator, verified SIM route and runtime
  heap/stack watermarks remain mandatory
  before hardware execution. The first IRAM window
  is nearly full, but IDF places the rest of `.iram0.text` in shared executable
  D/IRAM and reports 251,057 bytes remaining; therefore the single displayed
  byte is a future-layout warning, not a standalone runtime blocker.

The only remaining **operator-owned** action for the next real run is explicit
authorization of one bounded source-bound RNDIS plus wearable microphone/speaker
probe after those engineering prerequisites exist. That authorization must not
be inferred from the read-only enumeration. Engineering work listed above is
still outstanding and is not reclassified as operator work.

# Builder Prompt

```text
Read docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. Keep the
topology explicitly PC/USB bridged. The metadata-only evaluator, bounded
process-local runtime, private 640-byte framing/fake-endpoint/TLS-preflight seam
and four-worker concurrent orchestration are implemented. A default-dormant
wearable framing/queue core and dedicated-profile USB Serial/JTAG endpoint seam
now compose with the actual codec/I2S path and four continuous direction-owned
workers. A same-core non-autorun operator runner with runtime ephemeral routing
labels is retained in a dedicated inert-boot ELF; it is not yet wired to a
trigger and none of these slices proves actual I/O or selects a production
provider. The offline caller-injected host adapter now performs bounded ROM-
prefix/EGLM resynchronization and hands healthy traffic to the existing
concurrent bridge. Default-off CALL-020K now sits beneath H and requires an
exact caller-selected port plus a fresh connection identity; it uses an
injected factory or optional lazy pyserial import and never enumerates or
guesses. Its tests are fake-only and no actual port or connector has opened.
The matching offline relay core now pairs two caller-injected TLS-shaped
streams only after distinct external endpoint decisions match the exact
session/role/endpoint/peer/clock/stream-connection binding, then reuses the
same strict framing and concurrent bridge. It has no listener, TLS handshake,
credential verifier, provider or real connection.
The default-off CALL-020J seam now turns a caller-injected already-connected
TLS socket wrapper into I's ordered stream only after a frozen external
certificate/peer attestation, actual ALPN/TLS-version/connection ID and the
current I session decision match. Its fake tests cover strict I/O and close,
but it neither performs nor proves the handshake, PKI, listener, OS socket or
external authenticator.
Default-off CALL-020L now composes K-to-H and J into the actual four-worker C
bridge behind explicit single-use open/start calls. Its process-local fake
tests cover staged rollback, bidirectional forwarding, cancellation,
quiescence and redacted results. Construction is inert, transport provenance
is not evaluated by this layer, and no real serial/TLS connection or media run
has been proved.
Next, freeze and implement the matching authenticated device `EGLC` control
counterpart on O's same-driver lease, with START/ACK as the final pre-media
exchange and a reviewed hard runtime/PA-safe terminal bound. RESULT and
post-stop telemetry must remain disabled until their wire format and a real
media-quiescence proof are separately reviewed. Then review/invoke the exact
already-open driver path under fresh operator authorization. In parallel,
supply J from a controlled TLS listener/connector, verified PKI/external
authenticator and concrete finite-timeout/cancellable socket wrapper without
placing credentials in this repository. Keep
USB-OTG/TinyUSB as an alternative until physical routing is verified.
Keep Message Hub out of media, keep raw media out of logs/results, and preserve
immediate mutable-buffer zeroing without claiming control over external copies.
Do not make browser-grade WebRTC a prerequisite. Request explicit operator
intent for SIM traffic, board commands, VPS/RTC changes and audio capture.
CALL-010 is `accepted_for_transition`; after separately authorizing the actual
run, verify the interface-name/source-IP mapping and source-bound TLS egress,
then execute ten setup attempts, one ten-minute full-duplex run and a bounded
impairment case with observable RTT/loss/jitter/gaps/reconnect state.
Run every validation command and report credentials/redaction boundary, exact
hardware/network identity, outputs and evidence paths. Label success PC-side
engineering PoC; do not claim embedded media, final RTC selection or
P0-CALL PASS.
```
