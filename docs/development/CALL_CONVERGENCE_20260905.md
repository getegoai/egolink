---
document_status: engineering_notes
checked_at: 2026-09-05
runtime_state: waiting_authorization
---

# CALL runtime-convergence delivery

This serves CALL-020 / P0-CALL. It does not change `P0-CALL NOT_RUN`,
CALL-010's accepted endpoint evidence, or the CALL-020 ten-setup / ten-minute /
impairment campaign. The current change is a bounded executable supporting
slice alongside the Location mainline.

## Executable path and remaining seam

`ego_call_live_endpoints wearable` opens the exact pyserial handle once,
uses P's PREPARE, passes the runtime descriptor into N's concrete source-bound
TLS connection, then performs an actual mTLS admission exchange. Relay and
Guardian must present the configured distinct certificates. The listener checks
the CA and exact per-role certificate SHA-256 allowlist for this one run; both
roles must match the complete descriptor before either receives its ACK. Only
then M issues the final START/ACK and lends that same USB handle to K/H/L/C.

The Guardian entry opens an exact named input/output pair and host API, obtains
the descriptor over its authenticated connection, and runs PortAudio 16 kHz,
mono, S16LE, 320 samples / 20 ms. Its capture/playback queues each hold at most
8 frames. ADC source time is mapped from PortAudio's acquisition clock to host
monotonic time. Underflow, overflow and queue-full outcomes are explicit;
there is no recording, fallback audio-device selection or automatic reconnect.

The relay runs I/C's existing strict EGLM framing and four workers. It is one
bounded listener invocation and one role pair, not Message Hub or a production
RTC service. Completed invocations cannot reopen. No public protocol/schema
or shared Call reducer changed. The new private pre-media admission is bounded
to 4096 bytes and ends before any EGLM frame.

Real loopback concurrency exposed an existing N facade defect: simultaneous
blocking SSL reads/writes could fail the TLS record state. Native SSLSocket
calls now run nonblocking under one OpenSSL lock, with readiness waits outside
the lock. The finite 20 ms I/O and out-of-band shutdown contract is retained.
Send timeouts remain unknown-progress terminal failures; no ordered-stream
retry guesses that a partial send was safe.

**RESULT remains disabled.** The existing R firmware wire does not provide a
reviewed post-media RESULT/heap/stack response. M/P therefore reports local
handle cleanup separately from unconfirmed remote termination. Pre-start heap
telemetry is available; post-stop stack/heap and observed PA-safe termination
remain runtime/firmware follow-up evidence, not invented counters.

## Validation actually executed

- `python -m unittest quality_tests.test_call020_live_connector -v`: final
  **10/10 PASS, zero skips**; clean native runner transcript in
  `pc_simulator/runtime/call_convergence_20260905/native_tls_tests.log`.
- `python -m unittest discover -s quality_tests -p 'test_ego_call*.py' -q`:
  228 passed, no skips. Existing tests were not deleted or weakened.
- The new tests execute real Windows loopback TCP, OpenSSL TLS, CA/hostname
  validation, mutually authenticated certificate allowlists, Guardian descriptor
  delivery, four concurrent media workers, real pending-read cancellation,
  wrong role/cross-session/ACK rejection, truncation/oversize/duplicate JSON and
  inert CLI behavior. The duplex test sends and checks 12 synthetic frames in
  each direction. After the native TLS concurrency fix, it passed 20 consecutive
  executions. These are PC network/native behavior results, not acoustics, SIM,
  wearable USB, embedded media or external relay results.
- `py_compile` passed for both new entry modules and the changed N/M module.
- Final `python scripts/context_lint.py` and scoped `git diff --check` passed.
  Repository-wide verification belongs to the integrator's final candidate.
- The pinned embedded candidate was actually compiled; its final link failed
  as described below. This is not a test skip or a successful firmware build.
- No serial port, microphone, speaker, SIM, deployed relay or external Guardian
  was opened. No firmware was flashed. No hardware `last_verified` was advanced.

Runtime evidence directory:
`pc_simulator/runtime/call_convergence_20260905/` (ignored, metadata/build logs
only). `rtc_peer_build.log` SHA-256:
`8CAA34ABBF48A6FF09C16D5F15D31EE52A0485D901780EAF80648927715D8C28`.

## Concrete launch inputs and commands

The opt-in `--execute-authorized-run` flag expresses an already approved
operator experiment. The package itself is not that approval. Omitting the
flag is inert. Actual private files must be prepared with the approved endpoint,
ports, route, participant and image; never commit private keys or credentials.

Optional endpoint dependencies were installed only into the ignored local
`pc_simulator/runtime/call_convergence_20260905/python_deps` directory:
pyserial 3.5, sounddevice 0.5.3, cffi 2.1.1 and pycparser 3.0. No global Python
or IDF dependency was upgraded. The new test's ephemeral test PKI uses the
already-installed `cryptography` package; test private keys live only in an
automatically removed OS temporary directory.

The following commands select the local dependency directory and the three
actual entries. Start relay, then Guardian, then wearable. On the Guardian
machine install the same endpoint dependencies in that machine's isolated
environment. The relay uses Python's standard library only.

```powershell
$env:PYTHONPATH = "$PWD/pc_simulator/runtime/call_convergence_20260905/python_deps"
python -m pc_simulator.ego_call_live_connector --config <private-relay.json> --execute-authorized-run
python -m pc_simulator.ego_call_live_endpoints guardian --config <private-guardian.json> --execute-authorized-run
python -m pc_simulator.ego_call_live_endpoints wearable --config <private-wearable.json> --execute-authorized-run
```

`private-relay.json` fields correspond exactly to `RelayRunConfig`:

```json
{
  "run_id": "operator-selected-run",
  "listen_ipv4": "EXACT_LOCAL_IPV4", "port": 7443,
  "ca_file": "ABSOLUTE_CA_FILE", "cert_file": "ABSOLUTE_RELAY_CERT",
  "key_file": "ABSOLUTE_RELAY_KEY",
  "device_certificate_sha256": "64_LOWERCASE_HEX_DIGEST_OF_DEVICE_DER_CERT",
  "guardian_certificate_sha256": "64_LOWERCASE_HEX_DIGEST_OF_GUARDIAN_DER_CERT",
  "frame_count": 500, "max_runtime_ms": 15000, "setup_timeout_ms": 15000
}
```

Both endpoint files use a `tls` object with exact numeric `peer_ipv4`,
`peer_port`, exact bound `source_ipv4`, canonical DNS `tls_hostname`, and
absolute `ca_file`. Use `overall_timeout_ms: 15000`,
`tcp_connect_timeout_ms: 1000`, `handshake_timeout_ms: 2000`,
`authentication_timeout_ms: 12000`. Certificate validation and TLS 1.2/1.3
remain compulsory; no HTTP, insecure TLS switch or DNS route guessing exists.
Each endpoint additionally supplies its own absolute `cert_file` and `key_file`.

The wearable file adds:

```json
{
  "host": {
    "run_id": "operator-selected-run", "exact_port": "REIDENTIFIED_EXACT_PORT",
    "frame_count": 500, "max_runtime_ms": 15000
  },
  "verified_device_runtime_limit_seconds": 15
}
```

The Guardian file adds `run_id`, `frame_count: 500`,
`max_runtime_ms: 15000`, exact `input_device` and `output_device` names, and
`input_hostapi` / `output_hostapi` when a name occurs in several host APIs.
Exact equality and unique direction-capable matches are required; ambiguous
or partial names fail before capture. The relay session/clock/endpoint labels
are received over mTLS in memory, not copied through a plaintext file.

## Short owner image and combined experiment scope

The retained R profile allows a 600-second maximum and must not be silently
treated as a short-run authorization. Append the new 15-second override:

```powershell
# Working directory: firmware/audio_loop; pinned ESP-IDF 5.4.2 environment
idf.py -B build_call_convergence_15s -D "SDKCONFIG=$PWD/build_call_convergence_15s/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_device_owner.defaults;sdkconfig.call_convergence.defaults" build
```

The override changes only `CONFIG_EGOLINK_CALL020_DEVICE_OWNER_MEDIA_SECONDS`
to 15. The integrator records final application/bootloader/partition hashes and
the exact known recovery-image hashes; no build is boot evidence.

The CALL part of a single combined approval request is:

- One identified `wearable-node-001`, its verified 15-second candidate image,
  reidentified USB path, and the exact prior UI-001 recovery image. No board
  pins, volume (retained 55), codec or PA behavior changes are included.
- Two consenting test operators, independent Guardian network, exact selected
  audio devices, a controlled relay with the above PKI/role enrollment, no
  recordings and no non-test notification. Keep devices on a bench and do not
  use the test as a safety service.
- First run: one setup, at most 500 frames per direction (10 seconds of PCM),
  15-second host/Guardian media-coordinator ceilings and independently enforced 15-second device
  media ceiling; 15-second setup ceiling. No SIM required for this first
  acoustic check. A separately included second phase repeats this same bounded
  slice on a named SIM/RNDIS interface after source-address/interface mapping
  and source-bound TLS egress are actually checked. Interface `Up` is not LTE
  evidence. Limit each media phase to 3 MiB of interface traffic; stop before
  that cap, including TLS/TCP overhead. Two phases total at most 6 MiB.
- Stop on wrong image/port/peer/route, bad TLS/auth, one-way audio, queue-full,
  unbounded traffic, thermal/brownout/reset, unexpected media persistence, or
  uncertain concurrent device ownership. Cancel host I/O; never send control
  bytes in MEDIA. Because RESULT is absent, wait out the image's verified hard
  limit and confirm PA-safe termination physically before disconnect/recovery.
  Recovery flashing is included only for the exact approved known image.
  PortAudio abort/close latency is hardware-unverified; the coordinator bound
  does not prove a hard lifecycle wall-time limit. Stop the PC endpoint process
  if its local audio teardown does not return promptly; retain cleanup as
  unconfirmed and observe the independent device deadline.
- Preserve redacted counters and identity/image/timestamp evidence. Any further
  setup attempt, long call, audio gain change, SIM use beyond this included
  phase, or completed-run restart needs its own bounded scope. The original
  CALL-020 campaign remains open, not waived.

## Embedded RTC candidate: pinned source and actual incompatibility

Candidate examined: Espressif `esp-webrtc-solution` **v1.2.0**, exact commit
`1d4e1f0a70eb2470f8b21c003ef587d3a415a0b8`; its `esp_peer` component is
**1.2.7**, with `esp_libsrtp` **1.0.0** resolved in the scratch lockfile.
The local candidate is under
`C:/Users/binwe/AppData/Local/Temp/egolink-call-rtc-20260905/`.

| Check | Result and implication |
|---|---|
| API/transport | PeerConnection implements ICE, DTLS/SRTP and optional SCTP; G711A/U and Opus are available. Authenticated signaling and an actual lwIP-compatible bearer are still required. SIM7670G AT HTTP transactions are not such a socket bearer. A future PPP/socket integration must reuse the single modem owner. |
| Exact IDF compatibility | The upstream peer demo declares IDF >=5.0. Actual unmodified ESP32-S3 build on repository-pinned **5.4.2** compiled sources but **failed final link**: its prebuilt `libpeer_default.a` references missing `esp_log`. A README/manifest compatibility claim is insufficient. No shim or IDF upgrade was applied. |
| License/maintenance | The peer component is **Espressif Modified MIT**, restricted to Espressif products; it is not plain MIT. The default implementation is a prebuilt archive, which constrains local patch/debug freedom. Review the full dependency license set before product adoption. |
| RAM | Upstream's minimal <60 KB statement is not measured EgoLink audio/TLS/LTE RAM. The examined demo uses two 10 KiB peer task stacks and reduced 1536-byte data caches plus 1024-byte RTP pools. It sends synthetic bytes and uses SoftAP; it does not prove an acoustic LTE call. EgoLink's exact heap/PSRAM/DMA/stack coexistence remains unverified. |
| Board/codec | Current CALL-010 uses the exact Waveshare AMOLED board with pinned BSP 1.0.3 and `esp_codec_dev` 1.3.6; the candidate demo neither integrates this audio path nor verifies the connectivity board. CALL-021 product hardware remains separate. |

Primary sources: [pinned manifest](https://github.com/espressif/esp-webrtc-solution/blob/1d4e1f0a70eb2470f8b21c003ef587d3a415a0b8/components/esp_peer/examples/peer_demo/main/idf_component.yml),
[pinned peer API/resource notes](https://github.com/espressif/esp-webrtc-solution/blob/1d4e1f0a70eb2470f8b21c003ef587d3a415a0b8/components/esp_peer/README.md),
[pinned executable demo](https://github.com/espressif/esp-webrtc-solution/blob/1d4e1f0a70eb2470f8b21c003ef587d3a415a0b8/components/esp_peer/examples/peer_demo/main/peer_demo.c),
[pinned license](https://github.com/espressif/esp-webrtc-solution/blob/1d4e1f0a70eb2470f8b21c003ef587d3a415a0b8/components/esp_peer/LICENSE).

Archive SHA-256 (`libs/esp32s3/libpeer_default.a`):
`3F16A8113F95795A2B0952F2F7D024EE38CA6638AC487D5E7F9222EE5E67DD43`.
Build command actually executed in the pinned `peer_demo`:
`idf.py -B build_call_convergence_s3 -D IDF_TARGET=esp32s3 build`.
Two optional P4-only dependencies (`esp_wifi_remote`, `esp_hosted`) were skipped
by upstream target conditions; they are irrelevant to the ESP32-S3 build, not
missing S3 coverage. No native or hardware test was substituted by source text.

### Frozen-dependency ABI recheck

The subsequent bounded recheck kept the same component, SDK, source and target
configuration. The exact command below again reached the final link and failed
with `undefined reference to esp_log` (exit 1):

```powershell
# Existing upstream components/esp_peer/examples/peer_demo; IDF 5.4.2 environment
idf.py -B build_call_convergence_s3 -D IDF_TARGET=esp32s3 build
```

`xtensa-esp-elf-nm -A --undefined-only` finds `esp_log` references in eight
objects of the unchanged peer archive with the SHA-256 above.
`xtensa-esp-elf-nm -A --defined-only` on the linked SDK `esp-idf/log/liblog.a`
finds `esp_log_write` and `esp_log_writev`, but no `esp_log`. Its SHA-256 is
`C9FB6B27D392411D56A2A2E14589276F4E0F876BA3851823FEC1E96089AB9951`.
The actual link already includes this SDK log archive; adding a missing
`REQUIRES log` cannot supply the absent symbol. The pinned SDK source has no
`LOG_VERSION` selection that enables it. SDK Git identity is
`f5c3654a1c2d2a01f7f67def7a0dc48e691f63c0` (5.4.2).

Fresh evidence lives under the existing named target:
`C:/Users/binwe/AppData/Local/Temp/egolink-call-rtc-20260905/components/esp_peer/examples/peer_demo/build_call_convergence_s3/log/`.
`abi_recheck_20260905.log` is the complete repeated build failure, SHA-256
`7EE0162B3E617790594D46C6184E1EEC91ED528C2CFE843CDB3BB0CCF163B176`.
`abi_recheck_20260905.json` records UTC, exact commits/commands, object-level
symbol evidence and configuration/lock/archive hashes. The original failed
build log is retained. This incremental recheck is link evidence, not a fresh
full compile, native execution, embedded network operation, or hardware test.

There is no demonstrated configuration/link-only repair with these frozen
inputs. No SDK/component upgrade, replacement archive, fabricated `esp_log`
shim, board/pin change, or protocol change was made. CALL-021 still requires an
exact reviewed integrated hardware/data-bearer path; this upstream example is
only a candidate compatibility target. This subtask changed this engineering
note and generated named build evidence, and delivered no additional runtime
capability.

The shortest next dependency decision is an Espressif-provided build of this
peer implementation against IDF 5.4.2, with its matching ABI and security fixes
reviewed before any replacement is accepted. Then repeat this exact link probe
before integrating audio and an actual embedded socket bearer under the single
modem owner. Measured bounded DTLS/SRTP, heap/stack and acoustic behavior remain
separate work. Do not copy the demo's 120 MHz flash / octal-PSRAM defaults onto
an unverified board. No candidate is adopted here.

## Deferred RESULT proposal: reviewed, not implemented

The integrator reviewed the following read-only audit and deferred this work to
a separate protocol delivery. This change set does **not** add message type 13,
enable RESULT, or permit CONTROL bytes after MEDIA. The existing post-stop
telemetry and concurrent recovery commitments remain open. A later approved
bounded CALL experiment may use the independent 15-second device deadline while
reporting remote cleanup as **unconfirmed**; this gap does not block the Location
slice. It does not make P0-CALL, acoustic behavior, or recovery verified.

Current contracts and the missing seam:

- `pc_simulator/ego_call_single_usb_phase_connector.py` (P) already defines
  `telemetry_request=11` and `telemetry_ack=12`, but rejects
  `result_phase_enabled=True` and disallows telemetry in `MEDIA_RETURNED`.
  Its exact ACK keys are `run_id`, `operation_id`, `action`, `accepted`,
  `duplicate`, and `snapshot`. N in `ego_call_operator_control.py` provides TLS
  transport; it is not a USB RESULT implementation.
- `firmware/audio_loop/main/call020_device_control_wire.[ch]` currently emits
  telemetry-unavailable ACKs with `accepted=false`, snapshot `phase=post_stop`,
  and an empty worker watermark list. Existing heap/time samples do not supply
  the missing four-worker post-stop evidence.
- `call020_device_control_responder.c::finish_media_local` disables control
  writes permanently, cancels and joins the four workers, verifies PA-off and
  codec mute, closes the runner, returns the lease, then closes the physical
  driver and clears identities. R's `call020_device_control_owner.c` retries
  local cleanup with bounded backoff; it emits no result after START ACK.
- `call020_usb_serial_jtag_endpoint.[ch]` already offers
  `call020_usb_driver_lease_reclaim_for_result`: same core, exact generation
  and configuration, `MEDIA_RETURNED -> RESULT_OWNED`, no second install or
  second MEDIA phase. Lease ownership alone does not prove a frame boundary.

The shortest proposed implementation would retain the existing telemetry
request/ACK and add a separately reviewed private `RESULT_READY=13`. Proposed
READY fields are `run_id`, `start_operation_id`, `session_id`,
`driver_generation`, `workers_created`, `workers_finished`,
`worker_sampled_mask`, `pa_off_verified`, `codec_muted_verified`,
`uplink_frames_sent`, `downlink_wires_received`, and `rendered_frames`.
These fields and the new message number are a proposal, not an active contract.

After all device media workers stop, verified output safety and runner close
return the lease; R would reclaim it for RESULT while retaining the exact
run/session/start-operation binding. Only a proven complete EGLM stream
boundary with no partial or unknown-progress terminal could permit READY.
After its own workers stop, P would strictly drain complete trailing EGLM
frames, validating identity, sequence and CRC and erasing payloads, until the
exact READY. It would then send request 11 on the same handle. R would drain
complete trailing downlink frames until that request; the ordered request,
rather than a quiet-time guess, would establish host writer quiescence.
Neither side would scan for magic bytes or resynchronize a partial frame.
Wrong identity, CRC, half-frame, unknown progress, cleanup failure, or deadline
expiry would keep the current no-RESULT fail-closed cleanup path.

For actual measurements, add four sticky samples and a sampled mask to
`call020_wearable_composition.[ch]`. Each worker must call
`uxTaskGetStackHighWaterMark(NULL)` in `finish_worker` before publishing its done
bit and deleting itself, storing the value under the existing lock. Never read
deleted task handles after join. Convert explicitly using
`sizeof(StackType_t)` with bounds checking: the pinned ESP-IDF 5.4.2 Xtensa port
uses a one-byte `StackType_t`, not an assumed four-byte unit. Measure the heap
after worker join/output safety/runner close using
`heap_caps_get_free_size(MALLOC_CAP_INTERNAL)` and
`heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL)`; the minimum is a heap
lifetime low-water mark, not a per-call minimum. `esp_timer_get_time()` converted
with checked arithmetic supplies the real monotonic capture time. Idle-task
reclamation can still be pending, so this is a point-in-time heap sample.

Reuse the exact existing snapshot fields: `phase=post_stop`,
`captured_at_monotonic_ns`, `free_internal_heap_bytes`,
`minimum_free_internal_heap_bytes`, `worker_stack_high_watermark_bytes`, and
`externally_attested_runtime_measurement`. The fixed worker names are
`audio_capture`, `usb_uplink`, `usb_downlink`, and `audio_output`. Missing samples
must remain distinguishable from measured zero: the current host positive-only
watermark validation would need adjustment together with the sampled mask.
Do not invent a positive value. The ACK precedes physical driver uninstall,
so it cannot attest physical driver closure or complete runtime termination;
that remote evidence must remain unconfirmed.

The next delivery would touch composition and wire files, responder/owner
files and the opt-in boot configuration under `firmware/audio_loop/main/`, P's
strict terminal drain/phase logic, and M's telemetry sequencing in
`pc_simulator/ego_call_operator_control.py`. The TLS connector needs no new
wire protocol. Native tests must exercise sampling before deletion, zero versus
missing samples, worker quiescence, exact handle/operation identity, duplicate
and lost ACKs, half-frames/CRC errors, cleanup failure, and no restart of an
ended call. Existing concurrent recovery tests and commitments must remain.
None of these deferred code or test changes were performed in this delivery.
