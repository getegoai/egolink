# CALL-010 isolated audio loop

This target is the static implementation candidate for `CALL-010`. It is
isolated from `mqtt_heartbeat`, LTE, RTC, storage and the current flashed
images. The default build is dormant: `EGOLINK_AUDIO_LOOP_AUTORUN=n`.
Dormant means no codec, I2S or audio sequence is started; it still preloads,
configures and verifies the BSP-declared PA GPIO low at boot as a fail-closed
safety action.

It also compiles the CALL-020D `call020_media_adapter_core` as a dormant
pre-integration component. The component provides the exact 640-byte mono / 20
ms CALL-020B framing and bounded queue semantics, but `app_main` never
instantiates it and `EGOLINK_CALL020_MEDIA_ADAPTER_CORE` defaults to `n`.
CALL-020E additionally compiles a default-disabled USB Serial/JTAG ordered-byte
endpoint adapter, but `app_main` does not install it and
`EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT` defaults to `n`. The current image
uses the USB Serial/JTAG console, so the endpoint cannot be enabled in that
image. The CALL-020D core is not USB CDC, and neither a compiled framing core
nor endpoint adapter is full-duplex audio, LTE or RTC evidence.
Each initialized identity may enter `RUNNING` only once: after `stop`, callers
must deinitialize and initialize with a fresh session identity before sequence
zero can be emitted again. Both direction source timestamps are bounded to the
CALL-020B signed-63-bit domain and must increase strictly within the bound
direction clock.

## CALL-020E dormant USB Serial/JTAG byte endpoint

`call020_usb_serial_jtag_endpoint` is an isolated transport adapter around the
ESP-IDF 5.4.2 USB Serial/JTAG driver. It owns no task, audio device, PCM frame,
EGLM framing decision, codec, PA, pin, log sink or persistent storage. Its
caller-owned context supports one concurrent reader and one concurrent writer,
caps every transfer at the CALL-020D maximum wire size, caps each driver wait
slice at 20 ms, and caps operation and close-wait budgets at one second. The
20 ms / 640-byte media cadence and complete EGLM wire length remain the core
and future worker's responsibility; downlink must be requested as one complete,
caller-known wire transfer so a consumed header cannot be misreported as a
new zero-progress attempt.

This endpoint can be selected only in a dedicated operator configuration with
the CALL-020D core enabled, primary and secondary consoles disabled, and both
application and bootloader logging disabled. Source guards repeat those Kconfig
dependencies. `usb_serial_jtag_driver_install()` must also find no prior driver
owner. The install and close calls must run on the same CPU core, following the
ESP-IDF driver contract. The ordinary CALL-010 and UI-001 console profiles are
therefore incompatible with endpoint ownership; console/log bytes must never
share the application-owned media byte stream.

Install bounds both requested driver buffers, but the ESP-IDF install call is
synchronous and has no per-call timeout parameter. Likewise, the final driver
uninstall call has no timeout parameter. This adapter therefore claims bounded
arguments, bounded read/write waits and bounded pre-uninstall quiescence—not a
measured hard wall-clock bound for either ESP-IDF lifecycle call.

`sdkconfig.call020_usb_endpoint.defaults` is the compile-only configuration
overlay for validating those dependencies. It enables the dormant core and
endpoint symbols while explicitly selecting no primary/secondary console and
no application/bootloader logs. It neither changes `app_main` nor authorizes a
flash or run.

Read and write APIs use absolute monotonic deadlines plus short RTOS-tick wait
slices. A zero-byte timeout is the only timeout that can remain retryable. A
read deadline after consumed bytes is partial and terminal; an unexpected
driver count is unknown and terminal. ESP-IDF currently enqueues each write as
all-or-zero, but a short positive count is still handled as partial/terminal.
Once a complete write has entered the ESP-IDF ring buffer, a flush timeout or
cancel is unknown progress and terminal because the adapter cannot prove how
many bytes reached the host. Failed reads clear the bounded caller destination.
No media bytes are logged or persisted by this adapter.

Cancel is non-blocking, and active read/write calls re-check it after driver
wait slices of at most 20 ms. Close waits only its configured budget before
leaving a still-active driver installed and reporting a terminal close timeout;
it never uninstalls underneath an active operation. ESP-IDF's final driver
uninstall API itself has no timeout parameter, so an actual operator build must
measure that final call instead of treating the source-level wait bound as a
hard runtime guarantee. ESP-IDF ring buffers, USB-controller/FIFO state, host
driver buffers and PC copies are outside the adapter's secure-erasure boundary.

This is source and compile evidence only. No endpoint instance has run, and the
exact enclosure connector/USB controller path, host-open behavior, ROM bytes
that may precede application ownership, reconnect behavior, actual deadline
latency, concurrent task scheduling and sustained ordered media are unverified.
Physical USB-OTG/TinyUSB routing remains an alternative future architecture,
not something inferred or changed by this USB Serial/JTAG adapter.

### CALL-020O single-driver lease/handoff core

The endpoint now also exposes a default-dormant caller-owned USB driver lease
for the proposed single-handle control path. This is an additive path; ordinary
`call020_usb_serial_jtag_endpoint_install()` still installs and owns its own
driver, and ordinary endpoint close still uninstalls it.

The lease path has an explicit one-generation lifecycle:

```text
CONTROL_OWNED -> HANDOFF_READY -> MEDIA_BORROWED
                                  -> MEDIA_RETURNED -> CLOSED
                                                    -> RESULT_OWNED -> CLOSED
```

`call020_usb_driver_lease_install()` is the only install in that lifecycle.
After a future control bootstrap has completely transmitted `START/ACK` and
quiesced control I/O, it must call
`call020_usb_driver_lease_begin_media_handoff()`. The media endpoint may then
adopt only the exact registered lease pointer, its nonzero monotonically
assigned generation, the complete bound driver configuration, and the same CPU
core. Public struct fields or a bare “driver already installed” flag are never
sufficient. A duplicate adopter cannot make an actively borrowed lease
closable or steal it.

An adopted endpoint performs no driver install. Its close path first quiesces
media, then returns the lease exactly once and performs no uninstall. The
original lease owner later calls `call020_usb_driver_lease_close()` on the same
core; that function refuses to uninstall while the lease is
`MEDIA_BORROWED`. Lease and endpoint metadata distinguish self-owned install,
borrowed generation, binding close/return, optional RESULT ownership, physical
driver state, and final owner uninstall. The owner may instead move exactly
once from `MEDIA_RETURNED` to `RESULT_OWNED` through the same registry,
generation, full configuration and core checks. Duplicate reclaim or media
re-adoption cannot steal or make active RESULT ownership closable.

Wrong-core handoff, adoption, reclaim and close attempts leave the registered
owner and physical driver in place. A full-configuration mismatch before an
active borrower/RESULT owner latches a terminal but owner-closable lease.
Driver-uninstall failure keeps the exact pointer/generation registry entry and
reports the physical driver as installed so the same owner can retry; the same
recovery rule covers a failed post-install registry activation rollback. If
the exact self-owned binding remains registered but the physical driver has
unexpectedly disappeared, close releases that private registry entry and
reports a terminal missing-driver state rather than leaking or claiming an
uninstall.

`call020_wearable_composition_install_with_usb_driver_lease()` and
`call020_operator_runner_start_with_usb_driver_lease()` are additive local C
seams. The old composition/runner start APIs and the retained runner v1 table
remain intact. Endpoint adoption is the composition install's last fallible
resource step, so earlier audio/core failure cannot partially consume a lease.
Composition/runner cleanup returns borrowed ownership and keeps PA/mute safety;
it does not pretend the caller-owned driver has been uninstalled.

This slice implements only driver lifetime and ownership transfer. It does not
implement the fixed-size control envelope/parser, USB control reads/writes,
`START/ACK`, a RESULT phase, host single-handle transfer, or any boot trigger.
No endpoint, driver, port, board, codec, microphone, speaker, modem or network
was opened. A mocked C lifecycle harness covers install, handoff,
duplicate/wrong-core rejection, MEDIA return, RESULT reclaim, and retryable
uninstall failure. It cross-compiles with the target toolchain; execution is
conditional on an available host C target and is not ESP32 or physical-driver
runtime evidence. A later bootstrap must still prove
bounded control I/O, exact phase transition, hard runtime watchdog cleanup and
runtime behavior before any authorized hardware run.

## CALL-020F dormant wearable composition

`call020_wearable_composition` is the shortest build-only composition of the
CALL-020D framing core, CALL-020E USB Serial/JTAG endpoint, and the actual
`call010_safe_audio_v1` ES7210/ES8311/shared-I2S path. The option is
`default n`, depends on the exclusive console-free endpoint profile and on
CALL-010 autorun being disabled, and is repeated by source-level guards. The
ordinary `app_main` neither references nor instantiates it. The dedicated
overlay enables compilation of this branch but still has no runner; therefore
the build cannot open the codec, I2S, PA GPIO, or USB driver and is not an
operator-runnable image by itself.

Four workers have independent blocking ownership:

- audio capture owns bounded `i2s_channel_read` calls and copies one exact
  20 ms / 1280-byte stereo frame into a static bounded handoff queue;
- USB uplink exclusively owns one CALL-020D core instance and the endpoint
  writer, which converts that frame to one 640-byte mono EGLM transfer;
- USB downlink owns the endpoint reader and reassembles one complete,
  identity-derived EGLM wire across driver chunks before handing it off; and
- audio output exclusively owns a second CALL-020D core instance and bounded
  `i2s_channel_write` calls after validated 640-byte mono expansion.

No mutex is held across USB or I2S I/O, and no core instance is called by two
workers. Separate framing cores avoid pretending the non-thread-safe CALL-020D
context can be shared. Static queues are bounded to four frames. Every audio,
USB and queue wait has a finite slice/deadline, the session has a monotonic
run limit, and partial or unknown ordered-stream progress becomes terminal.
Only a proven zero-progress endpoint timeout may be retried. The ESP-IDF codec
wrapper's media read/write functions use a fixed internal wait, so this layer
uses the initializer's actual I2S channel handles directly to make the caller's
bounded wait visible; codec construction, input gain and board pins stay
unchanged.

CALL-020 has a separate build-time output-volume setting because the earlier
CALL-010 default of 12 was not audible in the enclosed device. It defaults to
55, the lowest step reported clear/normal in the bounded 55/70/85 diagnostic,
and is hard-capped at 85. The codec register is read back while mute is verified
and PA is off before output can be enabled. This is a conservative build input,
not proof of call loudness, SPL, clipping, echo behavior or enclosure acoustics;
the first operator run must confirm it and may lower it if 55 is excessive.

Cancel immediately requests endpoint cancellation, wakes start waiters, and
forces the PA low. Close performs bounded worker join before endpoint close,
then verifies codec mute and PA-low state before core/audio cleanup. A normal
self-owned endpoint uninstalls; a CALL-020O borrowed endpoint returns its lease
without uninstalling the caller-owned driver.
A join or endpoint-close failure leaves the underlying resources installed so
the caller can retry cleanup; it never uninstalls beneath a live worker.
Owned scratch and static queue backing are volatile-cleared on disposition and
close. Driver DMA/ring buffers, task stacks, USB controller/FIFO state and host
copies are outside this erasure boundary. Mute and PA readback failures are
terminal and reported; source cannot guarantee physical silence if hardware
readback itself fails.

The ESP32-S3 target layout makes the next integration cost explicit. The
caller-owned composition context is 43,736 bytes (including two 14,120-byte
cores, 9,936 bytes of fixed queue backing and 4,968 bytes of named scratch),
and must be long-lived internal RAM rather than a task-stack local. The four
workers request 4,096 stack bytes each (16,384 bytes total), excluding their
TCBs and all USB/I2S/codec driver allocations. Those stack and driver costs
have not been measured at runtime. The current dedicated compile-only image
still dead-strips the unreferenced composition and reports only one byte of
free static IRAM. Therefore its smaller image size is not executable-
composition sizing; an actual non-autorun runner plus final link map, heap and
stack-watermark review is required before any operator run.

Install requires all five session/endpoint/clock identifiers explicitly and
accepts only `CALL020_WEARABLE_IDENTITY_OPERATOR_SUPPLIED`. The strings shown
as comments in `sdkconfig.call020_wearable.defaults` are documentation-only,
non-production compile fixtures: they are not Kconfig values, are not embedded
in the image, and `NONPRODUCTION_BUILD_FIXTURE` provenance is rejected. No
credential, relay token, CA, hostname or production identity is committed by
this component.

Build both dormant boundaries without flashing:

```powershell
idf.py -B build_call020f_default -D "SDKCONFIG=$PWD/build_call020f_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020f_dedicated -D "SDKCONFIG=$PWD/build_call020f_dedicated/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_wearable.defaults" build
```

The generated dedicated configuration, not merely the defaults file, must be
checked for all three CALL-020 symbols enabled, CALL-010 autorun disabled,
primary/secondary console `NONE`, application/bootloader log level `NONE`, and
both USB Serial/JTAG console selections unset.

This is source and ESP-IDF compile evidence only. No composition instance,
worker, USB controller, codec, microphone or speaker has run. Before a bounded
operator run, engineering still must add a dedicated non-autorun runner that
obtains real per-run identities without committing secrets, define a safe
cancel/close control path despite the media stream owning the console, keep
endpoint install and close on the same CPU core, verify
the exact enclosure connector and USB Serial/JTAG host path, and implement a
host serial bridge that drains/resynchronizes any ROM prefix and preserves one
complete ordered EGLM frame. The PC side also still needs an authenticated
TLS relay/RTC endpoint, verified SIM7670G source-interface routing, explicit
credentials outside the repository, independent-network guardian client, and
a bounded operator procedure. None of this proves LTE, acoustic full duplex,
schedule/deadline performance, echo control, reconnect, or `P0-CALL`.

Two build-only profiles exercise the C source without flashing or opening a
device. The first preserves the normal console and verifies that the endpoint
stays disabled; the second resolves the exclusive media-owner Kconfig choices:

```powershell
idf.py -B build_call020e_default -D "SDKCONFIG=$PWD/build_call020e_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020e_dedicated -D "SDKCONFIG=$PWD/build_call020e_dedicated/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_usb_endpoint.defaults" build
```

The dedicated generated configuration must contain the endpoint/core symbols,
`ESP_CONSOLE_NONE`, `ESP_CONSOLE_SECONDARY_NONE`, `LOG_DEFAULT_LEVEL_NONE` and
`BOOTLOADER_LOG_LEVEL_NONE`; inspecting only the defaults overlay is not proof
that Kconfig resolved those choices.

## CALL-020G retained non-autorun operator runner

`call020_operator_runner` makes the previously link-dead D/E/F composition
measurable in a final ESP32-S3 ELF without making it run at boot. The ordinary
profile still builds the existing `app_main.c` byte-for-byte. The dedicated G
profile instead links a five-byte inert `app_main` boot stub: it installs no
driver, creates no task, writes no GPIO and does not call `prepare` or `start`.
The retained API table is pulled into the ELF with an undefined-symbol linker
entry, so `nm`/map evidence covers the runner, composition, endpoint and media
core rather than a compiled but dead archive member.

The API lifecycle is explicit and caller-serialized on the CPU core captured
by `prepare`: `prepare -> start -> cancel -> join -> close`. `prepare` validates
bounded numeric inputs and requests one 16-byte nonce with `esp_fill_random`;
it performs no codec, GPIO, I2S or USB operation. The nonce width is not an
entropy claim: RF entropy-source state and cryptographic quality are
unverified. Session, device, guardian and directional-clock values are
correlated labels made from that one nonce plus distinct prefixes. They are
non-secret routing identifiers, not authentication credentials. No production
identity, relay address or credential is embedded in the profile.

`start` is the sole runner boundary that installs the F composition. Any
handled failure after installation requests cancellation and invokes the
composition's verified codec-mute/PA-off path. `close` orders cancellation,
bounded join and safe disposition before endpoint uninstall, then clears the
owned runner/composition/identity buffers. External USB rings/FIFOs, DMA,
codec-driver allocations and host copies remain outside that erasure claim.
The runner and its workers emit or persist no media bytes.

The complete current EGLM wire is 814 bytes. G requires at least two complete
wires per USB direction and caps each driver ring at 4096 bytes, so the
caller-selectable USB payload allocation is 3256--8192 bytes total rather than
inheriting E's 32 KiB two-direction maximum. Every other queue length, I/O
slice, frame deadline, session run limit, cancellation wait and join wait is
bounded by D/E/F constants. The audio profile remains exactly one 20 ms,
640-byte mono media frame per wire; CALL output volume remains 55 with hard cap
85 and still requires an authorized acoustic check.

The dedicated profile places only ESP-IDF-selected **non-ISR** FreeRTOS and
ring-buffer functions in flash. ISR ring-buffer functions used by USB
Serial/JTAG remain in internal RAM. A CALL session must not perform OTA, NVS
writes, flash erase/write or any other cache-off operation; the IDF 5.4.2 USB
Serial/JTAG default ISR is itself not installed with an IRAM-safe flag. This is
a deliberate cache-on session constraint, not a claim that all driver paths
are cache-off safe. I2S/GDMA ISR placement settings were not weakened.

Fresh ESP-IDF 5.4.2 builds are:

```powershell
idf.py -B build_call020g_default_final -D "SDKCONFIG=$PWD/build_call020g_default_final/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020g_runner_final -D "SDKCONFIG=$PWD/build_call020g_runner_final/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_operator_runner.defaults" build
```

The final dedicated link reports a 254,592-byte padded application binary and
254,446-byte unpadded image. Its retained global runner is 44,216 bytes, of
which the composition is 43,736 bytes, in `.bss.s_runner`; none is on an
ordinary task stack. IDF size accounting reports 90,703 bytes of the 341,760-
byte shared executable/data D/IRAM region used and 251,057 bytes remaining.
The `.iram0.text` output is 49,923 bytes: 15,356 bytes plus 1,027 vectors fill
16,383 of the initial 16,384-byte IRAM window and the linker places a further
34,567 bytes in executable D/IRAM. The displayed one-byte first-window margin
is therefore a layout pressure signal, not by itself a link or runtime
blocker. Moving selected non-ISR functions to flash recovered 11,872 bytes of
shared D/IRAM versus the prior retained build.

Known requested runtime payload is bounded to 37,456 bytes at the G maxima:
four 4096-byte worker stacks, four observed 340-byte FreeRTOS TCBs, 8192 bytes
of USB rings, and an estimated 11,520 bytes of I2S audio DMA payload from IDF's
six 240-frame stereo-S16 buffers in each direction. Heap headers/alignment,
USB ring control objects, I2S descriptors/event queues and codec/BSP heap are
not included. Static `D/IRAM remain` is not interchangeable with allocatable
runtime heap. An authorized run must capture free/minimum-free internal heap
before install, after install and while running, plus all four task stack high-
watermarks; source arithmetic cannot replace those measurements.

This slice was build-only. It did not flash or boot the image and opened no
device, USB, audio, modem or network path. Before an operator run the project
still needs a separately reviewed non-autorun trigger/control seam, a host
serial reader that discards/resynchronizes any ROM prefix before complete EGLM
wires, exact connector/controller and reconnect proof, an authenticated TLS
relay and verified SIM7670G source route, external credentials, runtime heap /
stack instrumentation, and explicit hardware/audio/network authorization.
Link success does not prove scheduling, deadline latency, acoustic duplex,
echo behavior, USB transfer, LTE media or `P0-CALL`.

## CALL-020Q dormant same-USB device CONTROL responder

`call020_device_control_wire` implements the dependency-free `EGLC` v1 wire
codec shared with the CALL-020P host shape: fixed 8-byte header, at most 2048
canonical JSON bytes, one CRC32 and fixed message types. The accepted request
schema is deliberately not a general JSON parser. It accepts only the exact
sorted `action`, `operation_id`, `run_id`, `timeout_ms` object emitted by P,
bounded ASCII identifiers and a 1--10000 ms timeout. CRC is framing integrity,
not authentication. No request, identifier, descriptor, payload or raw audio
is logged or persisted.

`call020_device_control_responder` is a caller-owned, API-only same-core pump.
Initialization is pure and default-disabled. A later explicit caller may open
exactly one module-registry-backed USB Serial/JTAG lease and call `serve_once`;
the API never adopts an unknown/pre-existing driver, creates a task, scans a
port or runs from `app_main`. Reads, writes and `wait_tx_done` use finite
slices, finite call counts and one monotonic deadline. Tick budgets round down;
a sub-tick remainder is a zero-tick poll, and every driver return is checked
again against the monotonic deadline. Partial or unknown ordered-stream
progress is terminal. A zero-byte response timeout alone may accept an exact
duplicate request, whose full `(run_id, operation_id, action, timeout_ms)`
fingerprint must match the bounded 16-entry cache. Only the immediately latest
operation can replay; accepting any newer operation makes every older response
cache entry stale and fail-closed.

Frame acquisition has its own `frame_wait_timeout_ms` deadline. The device
operation budget starts only after a complete frame passes wire decoding and
maximum-timeout validation, so idle frame-wait time does not consume it; the
host still enforces its independent end-to-end send/response deadline. A
request whose fresh operation budget is exhausted before a side effect cannot
call the runner. Every synchronous runner callback is checked both before and
after the call; a late return is terminal and cannot emit a success ACK.
ESP-IDF/C callbacks are not hard-preempted, so the later production bootstrap
must keep its own callback work bounded and runtime timing still requires
device evidence.

`PREPARE` calls the retained runner once, returns its runtime-generated
descriptor and a real current/minimum internal-heap snapshot with no worker
watermark claim. `START` first returns `STARTING`. Only after the entire ACK is
accepted by `usb_serial_jtag_write_bytes` and `usb_serial_jtag_wait_tx_done`
does the responder permanently disable control writes, transition the same
lease to `HANDOFF_READY`, and invoke
`call020_operator_runner_start_with_usb_driver_lease`. If handoff or local
start then fails, the state is `START_UNKNOWN`; it performs local best-effort
safe disposal but sends no corrective CONTROL or RESULT byte and does not
claim remote cleanup. A successful start leaves the existing composition's
hard runtime limit and PA-off failure behavior authoritative.

Pre-start `cancel -> join -> close` is supported without interleaving media.
The close ACK means runner/control shutdown was accepted; physical driver
uninstall necessarily follows transmission of that ACK and remains separately
observable in local metadata. Post-stop four-worker stack watermarks are not
implemented by G/F, so a telemetry request receives an honest `accepted=false`
canonical ACK with real heap values and an empty worker set, then the device
fails closed. RESULT, post-start cancel/join/close/telemetry, automatic runtime
join, remote cleanup acknowledgement and USB-driver cleanup proof remain
disabled/unverified.

A lease-install error is not treated as proof that no driver/registry ownership
remains. If the lease API leaves an initialized terminal object after a failed
activation rollback, Q retains it, immediately attempts same-core cleanup and
leaves `abort_local` available for a retry. Runner ownership is likewise
recorded immediately after a successful prepare, before telemetry capture, so
telemetry failure cannot strand the global runner in `PREPARED`.

The dedicated generated profile must resolve all five CALL-020 symbols,
including `CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER=y`, while retaining
`ESP_CONSOLE_NONE`, `ESP_CONSOLE_SECONDARY_NONE`, application log level NONE,
bootloader log level NONE and an inert boot stub. This is link/static evidence
only. It does not authorize or prove a USB, codec, microphone, speaker, SIM,
TLS, relay or Guardian run, and it cannot advance `P0-CALL`.

## CALL-020R default-off device lifecycle owner

`call020_device_control_owner` is the separately selected one-shot bootstrap
above Q/G. Ordinary builds still use `app_main.c`; the retained G/Q profile
still uses its inert stub. Only `sdkconfig.call020_device_owner.defaults`
selects a boot entry that attempts to create exactly one pinned task. If task
creation fails, no owner API or hardware boundary has run. Building this
profile is not authorization to flash or boot it.

That task is the sole same-core mutating owner from CONTROL open through final
driver close. One absolute CONTROL deadline is anchored before open; the owner
does not start another serve unless its full configured frame-wait plus maximum
operation budget remains. ESP-IDF's synchronous install/uninstall callbacks cannot be
hard-preempted, so late return fails closed but is not claimed to obey a hard
callback wall-clock limit.

START ACK remains the last CONTROL byte. After MEDIA starts, the owner calls no
serve/wire path and does not reclaim RESULT. At the existing media deadline,
on a terminal runner/composition state, or as soon as all four workers are
observed finished, it requests G cancel/force-safe and gives workers a bounded
quiescence grace. Q's local finalizer then repeats cancel, performs the bounded
join, requires exactly four created/finished workers plus codec-muted and
PA-off proof, closes G, verifies endpoint binding/lease return, and only then
physically closes the driver lease. Only that complete observation sets local
device-runtime termination proven; remote cleanup remains unacknowledged.
An F `TERMINAL_RUNTIME` timeout with its explicit run-limit flag is the normal
bounded session end. Every other non-OK runner/composition `first_error`, and
every invalid post-START clock/deadline calculation, is preserved as the owner
result after the same local finalizer completes; cleanup success cannot turn a
media failure into success.

R adds no authentication, production session binding, TLS, LTE, SIM, relay,
RESULT or post-stop telemetry semantics. CRC is still framing integrity only,
ADR-0013 remains proposed, and `P0-CALL` remains `NOT_RUN`. Build-only checks:

```powershell
python -m unittest quality_tests.test_call020_device_control_owner quality_tests.test_call020_device_control_responder -v
Push-Location firmware/audio_loop
idf.py -B build_call020r_default -D "SDKCONFIG=$PWD/build_call020r_default/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults" build
idf.py -B build_call020r_owner -D "SDKCONFIG=$PWD/build_call020r_owner/sdkconfig" -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.call020_device_owner.defaults" build
Pop-Location
```

These commands do not flash, boot, enumerate a port, access USB/audio hardware,
or contact a modem/network.

## Bound identity

- repository board identity: `wearable-node-001`
- declared development board family: ESP32-S3-Touch-AMOLED-2.06
- BSP: `waveshare/esp32_s3_touch_amoled_2_06@1.0.3`
- codec API: `espressif/esp_codec_dev@1.3.6`
- BSP-declared path: onboard microphones -> ES7210 -> I2S RX -> ESP32-S3;
  ESP32-S3 -> I2S TX -> ES8311 -> NS4150B -> main-board P5/P6 SPK contacts
  -> product/enclosure speaker
- audio-bus pins: reused from the pinned BSP's public board macros; local
  `call010-safe-audio-init-v1` constructs the shared I2S path and both codecs
- PA ownership: the local ES8311 configuration fixes `pa_pin=-1`; only this
  application controls the BSP-declared PA GPIO, beginning in the OFF state
- exact physical PCB revision: `unknown`, pending operator inspection and
  evidence; the family name and BSP version are not substitutes for it

These are design inputs, not accepted hardware evidence. In particular, the
repository still has no proof that this exact board can sustain capture and
playback concurrently.

## Bounded sequence

When a separately authorized hardware task enables autorun, the target runs:

1. 30 seconds of a low-amplitude 1 kHz known chirp;
2. 30 seconds of microphone measurement with the speaker muted;
3. 120 seconds of attenuated local loop (capture then playback per 20 ms
   frame); and
4. unconditional speaker mute, PA OFF, and bounded codec/I2S/I2C cleanup.

Durations are bounded in Kconfig. Output volume is capped at 20 and defaults
to 12. PCM exists only in one overwritten RAM frame and is never logged or
stored; the frame is explicitly zeroed on exit. Direct PA GPIO control keeps
the amplifier off before codec initialization, between output phases and on
every handled failure path. The local initializer does not call the BSP audio
constructors and never gives the PA pin to ES8311, removing the constructor-
before-mute transient from this target. Codec mute is read back because the
pinned wrapper does not propagate the underlying ES8311 mute-write result. An
RTC latch prevents panic/reset loops from replaying the sequence, and an
independent deadline forces the PA off if the normal bounded loop overruns. The
dormant image explicitly clears that latch while keeping the PA off, so it is
also the controlled disarm step before a later separately authorized run.

This is static source/build evidence only. It does not prove the physical PA
polarity, codec addresses, microphone mapping, audible level or any acoustic
behavior on the exact PCB, so hardware execution still requires a separately
authorized bounded procedure and named evidence.

## Short output-only diagnostic profile

`sdkconfig.output_diagnostic.defaults` selects a separate speaker-path debug
mode for a specifically authorized run. It does not create an I2S RX channel,
ES7210 control/codec object, or microphone device and performs no microphone
read. After the speaker codec is open and read-back muted, it holds the PA OFF
for a logged 15-second warning countdown. It then emits three 2-second, 1 kHz
tone stages at volumes 55, 70, and 85, separated by 2-second muted/PA-OFF
gaps. Volume 85 is a hard cap matching, but never exceeding, the cited vendor
example setting. PCM peak is bounded to 5000/32767 and one-frame fade-in/out
reduces switching transients.

Each stage changes volume only while PA is OFF, verifies ES8311 register
`0x32`, and uses the enabled TX channel directly so the returned
`bytes_written` can be checked against every 1280-byte frame. A successful
stage requires 100/100 frames and 128000/128000 bytes, followed by codec-mute
readback and PA-low readback. Any register mismatch, I2S error, short write,
deadline, mute failure, or PA readback failure immediately forces PA low and
prevents later stages. The complete diagnostic has an independent 30-second
deadline, retains no raw audio, and still uses the one-run RTC latch.

Build this profile without flashing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command {
  . C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1
  Push-Location firmware\audio_loop
  try {
    idf.py -B build_output_diagnostic_static `
      -D "SDKCONFIG=$PWD/build_output_diagnostic_static/sdkconfig" `
      -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.output_diagnostic.defaults" `
      build
  } finally { Pop-Location }
}
```

This profile is deliberately louder than the earlier under-drive test. Before
any separately authorized hardware run, place the closed device on a stable
surface with the speaker opening unobstructed, keep it at least one metre from
any ear, and be ready to disconnect power if sound is painful or distorted.
The build command above is not hardware authorization.

Logs contain aggregate per-channel RMS, peak, clipped/zero ratios, frame
attempts/successes/gaps, codec errors and bounded API processing-time
histograms. These are not acoustic loop-delay, DMA underrun/overrun or
application-level concurrent-queue measurements.

## Static build only

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command {
  . C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1
  Push-Location firmware\audio_loop
  try {
    idf.py -B build_static build
    idf.py -B build_operator_static `
      -D "SDKCONFIG=$PWD/build_operator_static/sdkconfig" `
      -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.operator_test.defaults" `
      build
  } finally { Pop-Location }
}
```

This command does not authorize flashing, microphone capture, speaker output
or serial hardware control. A future run must identify board/revision,
connection, image hash or commit, timestamp and evidence path. A passing build
does not pass `P0-CALL`, AEC, AGC, echo, SPL, acoustics, product power or the
integrated LTE media path.

The hardware-active branch must also be compiled without flashing by layering
`sdkconfig.operator_test.defaults` onto a fresh, ignored SDK configuration.
That profile only prevents dead-code elimination during static review; it is
not permission to run the image. After an authorized execution, flash and boot
the dormant image to clear the one-run latch while verifying that the PA stays
off. A true power-on reset also clears the latch, but it is not a substitute
for restoring the intended post-test firmware.
