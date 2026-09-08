---
document_status: evidence_report
source_task: P0-CONVERGENCE-20260905
run_id: P0-CONVERGENCE-20260905-001
network_observed: 2026-09-05
hardware_status: live_boot_failed_outbox_initialization_FW007_restored
observation_status: bounded_boot_observed_no_location_ingest
---

# Runtime convergence run 001

The operator's subsequent **“同意，你继续”** approved the combined experiment
scope in [the code delivery](RUNTIME_CONVERGENCE_20260905.md). This approval
is recorded separately from physical readiness and hardware acceptance.
The unchanged approved text and its SHA-256 are preserved in
`reports/board_validation/P0-CONVERGENCE-20260905-001/approved_scope.md` and
`preflight_identity.json`. Commands within that scope need no further approval.

## Result and evidence boundary

The approved connectivity candidate was flashed and booted once after the
operator removed the SIM and accepted the actual FW-007 recovery bytes.
Wi-Fi and SNTP UTC anchoring succeeded. Outbox initialization then failed,
before the modem owner started; no GNSS observation or Location POST occurred.
The actual readback FW-007 was restored with all three write hashes verified
and a 30-second metadata startup smoke. The wearable was untouched; no CALL,
microphone/playback, SIM experiment, physical SOS or notification ran.
All three product Gates remain `NOT_RUN`.

The deployed bound Guardian API passed real HTTPS authorization checks. Its
last measured Location timeline was zero. The earlier complete stability
window remains incomplete; subsequent per-socket wired-interface pinning
restored verified TLS/SSH reachability. These are separate network samples,
not retrospective repair of the failed observation window.

HEAD remains `72c7a1ed199fa6bc522defff0d77a0aa3e77034d` on
`a0/first-real-field-session`; existing delivery changes remain uncommitted.
All **59** checked source/config/image/evidence identities matched the original
delivery manifest before the live attempt. Later partition/diagnostic and CALL
interface fixes have separate identities; that original manifest is retained.
Root AGENTS is unchanged. The prior native/full-regression/build
results and their individually explained skips remain in the code delivery;
this run did not rerun or relabel them as hardware evidence.

## Actual service deployment

- Origin: `https://ego.example.invalid`, VPS `203.0.113.10`.
- PC connections explicitly bind `192.168.31.99`, wired interface 19, gateway
  `192.168.31.1`. Source-address binding was checked, but by itself did not
  prove the selected physical interface. Default routing prefers RNDIS.
  The later WinSock interface-pin checks below establish per-socket selection;
  no network adapter/global route was changed.
- Initial public TLS validation passed, but Guardian HTML returned `404`,
  no binding was configured, and old Message Hub listened on `0.0.0.0:8790`.
- Protected VPS snapshot: `/var/backups/egolink/convergence-20260905-001`.
  It retains affected code/config, rendered Nginx, firewall inventory and a
  consistent SQLite backup whose integrity check passed. No private database,
  token or certificate key was copied into tracked evidence.
- Stage: `/opt/egolink-convergence-20260905-001`. Real Python **3.9.25** import,
  binding validation, Nginx syntax, and actual server startup using a database
  copy passed. The staged process was terminated. Device/Guardian credential
  separation and existing firmware/server credential equality were checked
  without exposing values or their hashes.
- Deployment completed at **2026-09-05 06:15:54 UTC**. Current source bytes and
  per-file hashes are in `server_package_manifest.json`; source files are the
  validated working-tree candidates, not a different remote revision. No
  live database, unrelated environment setting, GitLab unit or certificate
  was overwritten. Only Message Hub restarted; only Nginx reloaded.
- The unit now listens only on `127.0.0.1:8790`. The tracked HTTPS virtual host
  plus an experiment-specific Location-only restriction is deployed. Exact
  `/api/v1/safety-events/manual-sos` and device `/safety-events/` routes remain
  externally closed (`404`): the SOS retention/privacy rollout is not part of
  this Location experiment. The overlay and hash are in
  `location_only_nginx.conf` / `server_apply_result.json`.
- Guardian `operator-binwe-convergence-20260905` is bound only to
  `ego-link-001`. Its local secret stays in ignored `.env.guardian.local`;
  server bindings contain only its digest in a root-only file. This is a test
  credential, not a user onboarding or notification rollout.

At 06:17:03 UTC, actual external requests verified TLS 1.3, the CA chain and
exact hostname. The certificate is valid 2026-08-12 through 2026-11-10.

| Public request | Actual outcome |
|---|---|
| HTTPS health / Guardian HTML | `200` / `200` |
| Bound Guardian current Location | `200`, `no-store`; no ingested Location envelope |
| Same Guardian, unbound test device | `403`, `no-store` |
| Device credential used on Guardian route | `401`, `no-store` |
| SOS route outside this rollout | `404` |
| HTTP API, **no credential or body** | `426`; no redirect/downgrade used |

Evidence is API/network behavior, not a rendered-browser or ESP-TLS handshake.
Four of the six external current-Location queries are consumed (one initial
unauthenticated preflight plus three authorization checks). Two remain for the
single authorized device run; repeated polling must not exceed that budget.

The deployment observation is recorded in `server_observation.json` and
`server_final_bounded_check.json`. Its intended end was 06:25:54 UTC, but the
complete stability observation **did not pass**. An initial observer stopped on a systemd warning:
changing the running unit's `ExecStart` from public to loopback caused “Current
command vanished from the unit file” before the explicit restart. The exact
pre-restart warning is retained; it is not an application crash or an ignored
post-start error. A subsequent SSH management connection timed out while a
separate source-bound public HTTPS health request still returned `200`.
An additional observer encountered an HTTPS connect timeout. A short check
after the intended window again observed both services active and HTTPS `200`,
but the final bounded check at **06:29:41 UTC** returned SSH `255` and curl `28`
(connect timeouts). No route, adapter, firewall, TLS trust, credential or image
was changed to work around this. No more network retries were started. These
are intermittent connection failures, with insufficient evidence to attribute
them to the PC path, upstream network or VPS. An independent web-fetch tool
was unavailable for this origin and supplies no availability evidence.

The last detailed service sample at 06:18:30 UTC showed both services active,
zero restarts, loopback-only Hub, SQLite quick-check `ok`, zero Location rows
and no traceback. Final remote state cannot be inferred from that older sample.
No rollback was attempted: the app's initial gates passed, later direct health
checks intermittently succeeded, and management reachability is now uncertain.
Keep the protected restore snapshot; re-establish the approved wired management
path and inspect the actual service before any further deployment or device run.

## Initial hardware hold (resolved by the observations below)

The initial `Win32_SerialPort` inventory listed modem USB interfaces
`VID_05C6&PID_9330` (COM4–7) and the wearable's Espressif USB interface (COM8),
but did not list COM3. After the operator reported reconnecting the board,
at **06:51:50 UTC** both PnP and pyserial SetupAPI enumerated
`USB-Enhanced-SERIAL CH343 (COM3)`, `VID_1A86&PID_55D3`, serial `5B91047400`,
location `1-6.4:x.0`, with PnP status `OK`. `Win32_SerialPort` still omits it:
that method alone cannot establish physical absence. The earlier broad
absence claim is corrected; use the corroborated PnP/SetupAPI result.

`replug_serial_inventory.json` records enumeration only: no port was opened,
no MCU MAC/image was inferred from the USB bridge, and no reset/readback ran.
The simultaneous wired HTTPS/SSH checks again timed out, recorded separately
in `replug_https_check.json` and `replug_ssh_check.json`. The MCU console
visibility prerequisite was resolved. The operator subsequently confirmed SIM
removal after power-off. The initial recovery-hash and network holds were
resolved by the actual observations below; the unchanged approved scope keeps
the earlier stop-on-mismatch instruction as history.

CALL follows preservation of Location evidence. Its consenting participants,
named audio endpoints, mTLS relay and source-bound route still need actual
parameterization before opening audio. No CALL setup attempt was consumed.
Physical SOS and independent-power/concurrent recovery remain later work;
original recovery and post-stop telemetry commitments remain unchanged.

If service rollback becomes necessary, restore only scoped saved application
files and environment, retaining loopback-only service and working HTTPS.
Do not restore the live SQLite database or reopen plaintext ingress. Retain
the protected snapshot until device acceptance and operator handoff finish.

Evidence root: `reports/board_validation/P0-CONVERGENCE-20260905-001/`.
Actual one-run deployment/check scripts are `tmp/convergence_vps_stage.py`,
`tmp/convergence_vps_validate.py`, `tmp/convergence_vps_apply.py`,
`tmp/convergence_vps_external.py` and `tmp/convergence_vps_observe.py`.

## Actual readback, live attempt and restoration

The operator confirmed SIM removal after power-off. At 07:01:26--07:02:16 UTC,
one esptool read obtained exactly 2,097,152 bytes from connectivity COM3 in
49.671 seconds with transfer MD5 verification and local SHA-256 verification.
The MCU is ESP32-S3 rev v0.2, MAC `02:00:00:00:00:03`, flash ID `182085`
(16 MiB physical capacity). The saved private dump SHA-256 is
`ebd320bdaef0b01d5fe9c3224e07c8b55de3cfb168cb7ebf4ef0da8626f409dc`.
Only metadata, never raw NVS/Location bytes, is exposed in this report.

The actual application is 985,168 bytes, SHA-256
`a9894a86834aa6517e5947f011b50a8af223656d74fcfb68f911ee39efa36c7d`.
Its image checksum/appended digest validate and it equals the existing local
`build_fw007_hw_20260815/egolink_mqtt_heartbeat.bin` exactly. Descriptor:
`fw007-e9ca7a4`, Aug 15 2026 18:26:01, IDF 5.4.2. The older 984,912-byte /
`8f3508...3799` claim remains a historical mismatch. The operator accepted the
concrete actual-image amendment in response to the recovery question; no further
approval was requested for the authorized first flash or required restoration.

At 07:07:53 UTC, WinSock `IP_UNICAST_IF=19` set/readback verification, followed
by source bind `192.168.31.99`, yielded actual TLS 1.3 health `200` and an SSH
banner. At 07:13:15 UTC the same interface-pinned OpenSSH transport verified
deployed source hashes, active/running service, zero restarts, loopback-only Hub,
exact Nginx hash and zero Location rows. Source bind alone had been insufficient;
the kernel option fixes that concrete PC route seam without global route changes.
Both real CALL TLS consumers now accept the optional exact Windows interface
index and reject pin/readback failures before TCP connect; they retain CA,
hostname, mTLS, ALPN and exact session admission checks.

The original candidate app (988,992 B, SHA-256
`8a0e6eff29868a1f9ba22e74026b42de3656e64ad5710c69f88342ac03601a87`)
was flashed once with all three transfer hashes verified. One app reset was
requested at 07:19:45.649 UTC. Captured metadata includes:

```text
BOOT epoch=1 run=loclive-b1 ... duration_ms=180000 max_gnss=4 max_posts=6 max_slot_writes=32
CLOCK utc_epoch_at_boot_ms=1788592788960 ... clock_uncertainty_unmeasured=true
LOC021_LIVE_OUTBOX_INIT_FAILED modem_started=false
```

Capture stopped after 10.148 seconds / 5,911 serial bytes seen, preserving only
the allowed metadata. The app stopped Wi-Fi and returned before owner startup.
There was no GNSS request, event envelope, device HTTPS handshake, POST or ACK.
This is **failed initialization hardware evidence**, not a successful Location
slice or measured SNTP accuracy. The NVS boot-epoch write/readback reached epoch 1;
no NVS erase was performed. Whole-link Wi-Fi bytes were not measured, so the
original 2 MiB network ceiling is not claimed as verified metered evidence.

At 07:25:45--07:26:32 UTC the actual FW-007 three-region set was restored,
using `keep` header settings and transfer hash verification. Bootloader:
20,928 B / `1eddd94a293c483af64afa6c1eed83efa24d6fd7746a5d07afeefc189364b66e`;
partition table: 3,072 B /
`7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820`;
app: the actual hash above. A 30.17-second metadata smoke observed the expected
FW-007 descriptor and app entry with no captured fatal marker. COM3 was closed.
The restored legacy app's later autonomous behavior is outside that smoke;
it is not a new GNSS/network/endurance acceptance result.

Exact evidence files under the run root:
`connectivity_readback_result.json`, `readback_application_reconciliation.json`,
`actual_fw007_restore_set.json` (initial pending proposal),
`location_live_attempt.json`, `location_live_result.json`,
`location_flash_and_run.log`, `location_live_metadata.log`,
`actual_fw007_restore_attempt.json`, `actual_fw007_restore_result.json`,
`actual_fw007_restore_flash.log`, `actual_fw007_restore_metadata.log`,
`explicit_wired_interface_probe.json`, `pinned_ssh_server_check.json`.

## Correction and validation after the failed boot

The preflash bytes at `0x110000..0x11c000` contain two non-erased slots, neither
with a valid outbox header/digest. Executing the actual partition adapter and
core against those saved bytes on native GCC reproduces `storage_corruption`,
`slot0=corrupt`, `slot1=corrupt`, **zero erase/write calls**. Their provenance is
unknown; the correction neither formats nor discards them. The same saved dump
proves `0x1f4000..0x200000` is entirely erased (48 KiB SHA-256
`abd8e2a70d51a53287941838446e6ed141005d401faf597fd7c6de0bbc8c329d`).
Native initialization there creates two valid mirrors in a RAM copy only.
Evidence: `outbox_readback_native_diagnosis.json`.

The shortest fix is `partitions_loc021_live.csv`, selected only by the live
profile; NVS/PHY/factory and legacy/S layouts retain their geometry. Startup
now reports the actual partition/core/slot status and write count. STOP also
reports slot writes. Unknown/corrupt storage still fails closed before the
owner starts; runtime write/queue faults still permit explicit local progress,
without stored/delivered claims. No volatile fake outbox, HTTP downgrade or
relaxed recovery rule was added.

The actual post-fix IDF 5.4.2 live build passed: app 990,224 B, SHA-256
`97af7f2fdee31d5fb8fb9efcd6da856e9ce9c7e4f843acb3e90e99cb5a1713d1`;
58,352 B factory space remains. Legacy rebuild also passed. These are build
results; the corrected image has not been flashed. Native regression executes
partition bounds, untouched surrounding bytes, mirror recovery, failed first
write and readback mismatch. It does not replace real flash/power-loss testing.

`scripts/verify.ps1` with host GCC available discovered **1,635 tests: 1,630
passed, five skipped** in 168.424 s. The five skips are individually accounted for:

- Original S generated-build selector: missing `EGOLINK_LOC021S_BUILD_DIR` in
  the full-run environment. A separate actual rerun with
  `tmp/convergence_s_build` passed all **9/9**, including that check.
- Three original Espressif clang/lld selectors (exact parser, P0 adapter,
  split delivery): skipped that compiler-specific route. The unchanged native C
  harnesses also ran successfully under host GCC in the convergence suite.
- USB-Serial-JTAG device owner lifecycle: cross-compiled against IDF fakes,
  but that target's native behavioral execution remains **NOT_RUN**. Host mTLS
  duplex/thread tests and Location Q native concurrency do not substitute for it.

Full log: `tmp/convergence_partition_fix_verify.log`; S rerun:
`tmp/convergence_partition_fix_s_verify.log`; live/legacy build logs:
`tmp/convergence_live_partition_fix_build.log`,
`tmp/convergence_partition_fix_legacy_build.log`. The CALL route selection also
passed a focused **114/114** including real Windows interface set/readback and
loopback mTLS duplex/failure behavior; synthetic PCM, no device audio.
Embedded peer_demo relink still fails on `esp_log` ABI with the fixed IDF 5.4.2
dependency set; no compatibility shim or dependency upgrade was applied. See
[the CALL evidence](CALL_CONVERGENCE_20260905.md).

Source/build/native/host-network results above do not establish device Location
delivery, real CALL, physical SOS, field reliability or a P0 Gate. The original
concurrent recovery and post-stop telemetry obligations remain open.

Current post-restore identities/results are in
`reports/board_validation/P0-CONVERGENCE-20260905-001/run_manifest_post_restore.json`;
the earlier `run_manifest.json` remains the dated preflash checkpoint. A single
[corrected-run proposal](RUNTIME_CONVERGENCE_20260905_RETRY.md) contains the ready
image, changed write address, honest network budget, stop and restore conditions.
Its additional flash/boot awaits the operator's combined scope amendment.

## Subsequent authorized runs 002 and 003 — actual bench results

The preceding run-001 candidate/proposal statements are dated checkpoints.
The operator subsequently authorized run 002 and the specific run-003 stack
image/batch; neither authorization is inferred from a passing build.

Run 002 used app `97af7f2f...a1713d1` on the same COM3/CH343 connectivity
node, without SIM. At 07:54:36 UTC the new outbox initialized both mirrors at
`0x1f4000`, with two slot writes. Network preflight had failed; the captured
backtrace decodes against that exact ELF to `vApplicationStackOverflowHook`.
Compiled nested initialization frame sizes alone total at least 3856 bytes,
exceeding the configured 3584-byte main stack. FW-007 restore completed at
07:55:46 UTC, with three-region transfer verification and 30.175 s descriptor
smoke. Evidence root: `reports/board_validation/P0-CONVERGENCE-20260905-002/`,
including `decoded_backtrace.log`, `compiled_init_stack_frames.json` and
`diagnosis.json`.

**Capture limitation:** run 002 requested one startup and captured epoch 2,
but did not immediately hold ROM after the panic. Run 003 began at epoch 6:
there were three intervening live boot-epoch advances whose individual runtime
and I/O were not captured. This is not evidence of only one actual run-002
boot, nor of compliance with a total repeated-boot I/O budget. Preserve the gap;
do not infer a GNSS/POST result from it. The run-003 supervisor now enters ROM
immediately at a fatal/unconfirmed stop before restoration.

Run 003 used the expressly approved 8192-byte stack image, app 990,752 B /
`52816255ab96b99831d03129c2a49a9128949de33884f61452742c27ee3fe913`.
At 08:10:32–35 UTC the board obtained Wi-Fi IP and SNTP synchronization;
UTC-at-boot anchor was `1788595831087` ms (clock uncertainty unmeasured).
Both outbox slots were valid, with zero slot writes in this observed boot.
Q initialization reported **4424 bytes minimum free main stack**. No captured
stack fault recurred. Startup returned **23 / GNSS_POWER_OFF_UNCONFIRMED**
about 153 ms later. The image did not log the driver's precise failure reason;
it is unknown, and an AT ERROR must not be silently treated as confirmed off.
There is no captured sensor/Location event, device POST or matched ACK.

The original main returned on this error without requesting Q's existing
cooperative stop, leaving its bounded recovery task active without further
profile metadata. Capture reached the host deadline: **300.191 s / 6388 bytes**,
one requested and one observed profile boot. ROM hold then succeeded. The
approved second boot required network-not-ready plus safe exit; that condition
was not met and no second startup was requested. GNSS-off state was not proven.
FW-007 restoration completed **08:18:11 UTC**, all three transfer hashes verified,
followed by a **30.176 s** expected-descriptor smoke; COM3 closed. No NVS erase,
new full readback, SIM traffic authorization, audio or physical SOS run occurred.

Run-003 evidence root: `reports/board_validation/P0-CONVERGENCE-20260905-003/`.
`location_live_result.json`, `location_live_metadata.log`,
`actual_fw007_restore_result.json` and `integration_diagnosis.json` distinguish
observations, cleanup uncertainty, conditional budget and restored identity.

## Minimal fixes after run 003 — source/build/native only

Live main now reuses one cooperative-stop helper on both failed startup and
normal completion. It observes Q for at most 30 seconds and reports before/after
owner lifecycle, exclusive UART ownership, shutdown outcome/reason, cleanup and
quiescence. It does not tear down Q's dependencies or relax its off confirmation.
Actual Windows-thread C execution tests startup failure then successful cleanup,
and persistent failure with exactly three stop cleanup attempts; no early
quiescence, restart, duplicate owner, concurrent modem I/O, sensor or HTTP work.

Guardian JavaScript now renders successful Location independently of unavailable
SOS routes, clears stale SOS state and keeps authentication failures closed.
Seven tests execute the shipped JavaScript with Node; they do not establish a
browser/device acceptance. **Not deployed:** two apply attempts failed at SSH
TCP connect before authentication or remote mutation. A bounded follow-up at
08:26 UTC found both HTTPS 443 and SSH 22 timed out through pinned wired interface
19 / `192.168.31.99`. Last actual external TLS 1.3 health/source/service preflight
passed at 08:09 UTC. No extra Guardian current query was consumed. Whole-link
Wi-Fi/TLS/retransmission bytes were not metered; no measured 2 MiB claim is made.

Live and legacy IDF 5.4.2 builds pass. New **unflashed** live app is 991,456 B /
`139cdbc98f57ca07405ed989b9b6dabbf7217fcceda9de4789570d4f94f8c4fd`, at
`tmp/convergence_live_stop_fix_build/`; source/config/artifact identities are in
`tmp/convergence_live_stop_fix_manifest.json`. Full `scripts/verify.ps1` actually
ran **1643 tests: 1639 passed, four skipped**, in 172.660 s, log
`tmp/convergence_stop_fix_verify.log`. Each remaining skip is accounted for:

- USB-Serial-JTAG device-owner lifecycle: only its existing IDF-fake cross-build
  ran; native device-owner lifecycle and real hardware execution remain NOT_RUN.
- Original exact HTTP parser clang/lld selector: unavailable; its unchanged C
  harness ran under native GCC in the convergence suite.
- Original SIM7670 P0 delivery-adapter clang/lld selector: same compiler gap;
  its unchanged C harness ran under native GCC.
- Original split P0 delivery-runtime clang/lld selector: same compiler gap;
  its unchanged C harness ran under native GCC.

The S generated-build selector ran successfully in this full run. No tests were
deleted or replaced with source matching. CALL remains host mTLS duplex/synthetic
PCM evidence only; embedded peer archive still fails the fixed IDF log ABI.
Physical SOS and field testing were not run. P0-LOC/P0-CALL/P0-SOS remain NOT_RUN;
the original concurrent recovery and no-repeat-ended-call commitments remain.

## Run 004 — confirmed cleanup and deployed Guardian page

The operator's next `你继续` approved the prepared diagnostic-image batch.
Run root: `reports/board_validation/P0-CONVERGENCE-20260905-004/`; the approved
scope and operator reply are preserved there. No prior attempt files were reused.

PC wired HTTPS/SSH recovered. At 09:13:07 UTC the minimal Guardian page change
was deployed with the previous file backed up; service restart and loopback
health passed. External certificate-verified TLS 1.3 then returned the exact
tested 6216-byte JavaScript (SHA-256
`15d5f16b8535fea72a10d44bb5164d78d0dd01e172392608cc63bd1b61d180c6`),
with `Cache-Control: no-store`. Post-deploy source/service/HTTPS preflight passed
at 09:13:47 UTC. This proves deployment and exact served bytes, not browser or
device-Location acceptance. No Guardian current query or fabricated ingestion
was used. Original incomplete stability evidence remains incomplete.

The authorized app `139cdbc98f57ca07405ed989b9b6dabbf7217fcceda9de4789570d4f94f8c4fd`
was flashed once on COM3 / CH343 `5B91047400`, ESP32-S3 MAC
`02:00:00:00:00:03`, without SIM. One requested and observed startup reached
epoch 7, Wi-Fi/SNTP, both valid outbox slots, zero slot writes and the same
4424-byte minimum main-stack headroom. At 09:14:31 UTC initial power-off returned
**outcome 3 / reason 11, AT_TERMINAL_ERROR**. Metadata confirmed exclusive UART
ownership, no fatal recovery, and GNSS off not yet confirmed.

The existing cooperative stop then succeeded on its next power-off operation:
at 09:14:33 UTC, attempts=2, confirmed=1, unconfirmed=1, last outcome/reason=0/0,
`gnss_off=1`, `cleanup=0`, `quiesced=1`. Capture ended normally after **11.125 s /
7112 bytes**. This is actual same-owner cleanup evidence; it does not explain
the modem's first terminal ERROR. App main had not requested a sensor, so there
is still no device Location/POST/ACK evidence. FW-007 restore completed at
**09:15:47 UTC** with all three transfer hashes verified and a **30.182 s**
descriptor smoke; COM3 closed. No additional candidate boot was requested.

Inspection found the shortest remaining seam: Q already retries startup cleanup
and changes to ACTIVE only after confirmed power-off, but live main exited on
the initial status 23. Main now waits at most 10 s for that existing recovery,
polling every 100 ms and requiring ACTIVE, exclusive UART ownership, confirmed
off and no cleanup/fatal/stop/quiesced state. Other failures or the deadline use
the hardware-verified stop path. There is no second owner, changed AT protocol,
invented GNSS result or relaxed TLS/ACK check.

Windows-thread native tests execute the same Q recovery, then actual UTC
mapper/pipeline/outbox emission after ACTIVE; a persistent terminal error never
becomes ACTIVE and stops with bounded cleanup. The injected native backoff and
wait window are shortened for the test; neither proves the live main's 10-second
hardware behavior. The new live image is **unflashed**, 991,872 B /
`aabff0890cbacd1526411ec785276114a2547af607711320a88781db17d92e24`, at
`tmp/convergence_live_recovery_wait_build/`; legacy/live builds pass. Exact
source/config/artifact identities: `tmp/convergence_live_recovery_wait_manifest.json`.
CALL/physical-SOS/field scopes and all three NOT_RUN product Gates are unchanged.

Final recovery-wait regression: `scripts/verify.ps1` **1644 discovered, 1640
passed, four skipped**, 200.778 s; log `tmp/convergence_recovery_wait_verify.log`.
The four skips remain individually scoped: USB-Serial-JTAG owner lifecycle is
cross-build-only, native device-owner execution NOT_RUN; exact HTTP parser,
SIM7670 P0 adapter and split P0 delivery each skipped the unavailable clang/lld
selector but their unchanged C harnesses executed under native GCC. No deleted
tests or source-text substitute. Context lint and diff checks pass. These tests
and builds do not establish the new image's board behavior.

## Run 005 — real no-fix Location reaches Guardian

The operator authorized continuing necessary same-scope fixes and bounded bench
runs without further per-image approval. On the same no-SIM COM3/CH343 node,
app `aabff0890cbacd1526411ec785276114a2547af607711320a88781db17d92e24`
booted as epoch 8 at 10:00:48 UTC. Wi-Fi and SNTP passed. Q recovered the initial
terminal ERROR in 5110 ms using the same exclusive owner, confirmed GNSS off,
then produced four real GNSS no-fix observations. All four were persisted and
deleted only after matching authenticated HTTPS durable-ingest ACKs.

Read-only SQLite inspection verified four rows, exact device sequences 1–4 and
event times matching the board metadata. At 10:02:01 UTC, the bound Guardian
current API returned HTTP 200 over verified TLS 1.3, `Unknown`, position
`unavailable`, no coordinates and state age 18,737 ms. This is real degraded
Location delivery and authenticated API evidence; actual browser rendering,
coordinate fix, LTE transport, field accuracy and product acceptance remain
unverified. The already deployed page's seven Node behavior tests are separate.

Capture ended normally after 186.364 s / 23,293 serial bytes, with four sensor
attempts, 16 slot writes, zero persistence failures, confirmed off and quiescence.
Minimum free main stack was 4408 bytes. FW-007 restoration completed at
10:05:23 UTC: all three transfer hashes verified, 30.202 s descriptor smoke,
COM3 closed. Evidence: `reports/board_validation/P0-CONVERGENCE-20260905-005/`,
especially `integration_result.json`, `location_live_metadata.log`,
`server_location_ledger.json`, `guardian_current_first_observation.json` and
`actual_fw007_restore_result.json`.

This run exposed two small Q defects. Observation IDs used only the per-boot
sequence and would collide with the server's per-device unique key after reboot;
the correction includes the existing verified boot epoch. Delivery telemetry
incorrectly read `post_called` from settle, which does not invoke transport;
it now reads that flag from execute and records the actual settle time/status.
Run 005's zero delivery counters are defective evidence, not proof of zero POSTs.
The C source matching that flashed run is retained as
`sim7670_location_modem_owner.before_followup.c` in its evidence directory.

## Run 006 — cross-boot identities and actual delivery statistics

Same node, COM3 and no-SIM route. The corrected app was flashed once:
**991,920 B**, SHA-256
`354b5e283f6a60efb3ad3370825d2d548f1dece75cd258a6d9594bea45f32283`.
Epoch 9 ran at 10:20:11–10:23:18 UTC for 186.988 s / 23,435 serial bytes.
After confirmed quiescence and fresh verified TLS/SSH preflight, one restart
without flashing ran epoch 10 at 10:23:35–10:26:44 UTC for 188.030 s / 23,901
bytes. Each boot produced four real no-fix observations, four actual POST
attempts, four matching ACK deletions, zero persistence failures and 16 slot
writes; GNSS off and quiescence were confirmed, minimum main-stack headroom
4408 bytes. Both boots recovered the initial terminal ERROR with the same owner.

Read-only SQLite inspection at 10:27:01 UTC found all twelve campaign rows:
four original epoch-8 records preserved, then `locq-9-1..4` and `locq-10-1..4`.
Each device event time and sequence exactly matches board metadata. Guardian's
bound current query at 10:26:36 UTC returned verified TLS 1.3 / HTTP 200,
identity `locq-10-4`, state age 29,567 ms, `Unknown`, position unavailable and no
coordinates. Freshness describes the state report, not a nonexistent location.
The original six-current-query campaign budget is consumed.

Actual FW-007 restore completed at **10:27:38 UTC**, all three transfer hashes
verified, **30.166 s** descriptor smoke, COM3 closed. Evidence root:
`reports/board_validation/P0-CONVERGENCE-20260905-006/`; `integration_result.json`
joins exact live/restore identities, device metadata, ledger and Guardian result.
`source_build_validation_manifest.json` binds the tested sources and binaries;
the flashed Q source was preserved before the subsequent GNSS dwell change.

Legacy/live IDF 5.4.2 builds passed. Full regression executed **1646 tests:
1642 passed, four skipped**, 212.851 s (`tmp/convergence_identity_fix_verify.log`).
The unchanged four skips are individually bounded: USB-Serial-JTAG device-owner
lifecycle remains cross-build-only; exact HTTP parser, SIM7670 P0 adapter and
split P0 delivery skip unavailable clang/lld selectors while their unchanged C
harnesses execute under native GCC. No test deletion/source matching replaces
native concurrency. Storage/queue failures, SOS feedback separation and no-call
replay remain native evidence, not fresh hardware claims. CALL, physical SOS,
field and all three product Gates remain NOT_RUN.

Code inspection after this successful slice found that the existing GNSS path
powers on, immediately queries, then powers off. Its 12-second total request
cap is not a TTFF acquisition window. A subsequent minimal opt-in powered dwell
is being validated; these no-fix runs do not diagnose antenna or sky conditions.

## Run 007 — powered acquisition window on the actual device

The same-scope continuation authorization covered this necessary GNSS seam and
one further bounded bench run. Q and its concrete adapter now pass an optional
powered dwell to the existing driver, default zero. Live uses 30,000 ms after
successful power-on and before the actual query, inside a 42,000 ms total
request including the original 3000 ms power-off reserve. Waiting checks the
existing deadline/cancellation every at most 100 ms; insufficient budget,
clock regression or incomplete parsing cannot become no-fix evidence. Query
completion supplies event time before cleanup, with no cached observation
restamped at the end of a wait. Q's borrowed atomic stop flag joins the existing
arbiter cancellation in the adapter; power-off compensation remains uncancelled.
No O protocol, new owner or additional AT command sequence was introduced.

The complete real `sim7670_gnss.c` executes under native UART/clock injection:
13 cases cover fix/no-fix parsing after dwell, defaults and legacy zero waiting,
cancel/deadline/clock failures, initial and remaining budget, power-on error,
malformed response and a real concurrent foreign owner's refusal. A separate
real-thread Q/adapter test proves owner-stop propagation, no unfinished
observation/HTTP, confirmed power-off and quiescence. These are native failure
tests; cancellation during dwell was not separately triggered on hardware.

Legacy and live IDF 5.4.2 builds pass. Live app **992,784 B**, SHA-256
`99d51d25f0e0ed21dd12c20fee7f80463dd40a2540504a19a2314a34bc52bc0b`,
at `tmp/convergence_live_gnss_dwell_build/`, actually ran on the same COM3/CH343
connectivity MAC `02:00:00:00:00:03`, no SIM. Pinned wired TLS/SSH preflight
passed at 10:43:08–09 UTC. One flash and one epoch-11 startup ran
**10:43:34–10:46:43 UTC**, **188.889 s / 23,910 serial bytes**. The existing
same-owner startup recovery again took 5110 ms. Four powered acquisition dwells
completed, all four real queries reported no-fix, all four records received
matching durable ACKs, and delivery attempts/status/time agreed with those
calls. There were zero persistence failures, 16 slot writes, 4376 bytes minimum
free main stack, confirmed GNSS off and normal quiescence, no captured reboot.

At 10:47:35 UTC, read-only SQLite integrity and all four new event times/sequences
matched; the previous twelve rows were preserved. The 10:47:24 UTC Guardian
query returned HTTP 200 over verified TLS 1.3, exact identity `locq-11-4`, state
age **47,704 ms**, `Unknown`, location age unavailable and no position. No real
browser acceptance or coordinate fix is inferred. One current query belonged
to this follow-up batch; the prior six-query campaign is retained separately.
Whole-link transfer/retransmission bytes were not metered; there is no measured
2 MiB claim. The operator did not provide antenna/sky-placement confirmation.

Actual FW-007 recovery completed **10:48:12 UTC**, all three transfer hashes
verified, **30.166 s** descriptor smoke, COM3 closed. No new full flash readback,
NVS erase, SIM usage, recording, physical SOS or external notification ran.
Evidence: `reports/board_validation/P0-CONVERGENCE-20260905-007/`, including
`integration_result.json`, live metadata, Guardian/ledger results, restore
result and `source_build_validation_manifest.json`. HEAD remains
`72c7a1ed199fa6bc522defff0d77a0aa3e77034d` plus individually hashed worktree
changes; root AGENTS is unchanged and parallel work was preserved.

Final `scripts/verify.ps1`: **1648 discovered, 1644 passed, four skipped** in
226.258 s (`tmp/convergence_gnss_dwell_verify.log`). USB-Serial-JTAG device-owner
lifecycle remains cross-build-only; HTTP exact parser, SIM7670 P0 adapter and
split P0 delivery each skip their unavailable clang/lld selector but execute
their unchanged C harness under native GCC. S's generated-build selector ran.
No tests were deleted or replaced by source matching. Source/build/native,
no-SIM Wi-Fi hardware/API and field/product results remain distinct: CALL is
host mTLS/synthetic-duplex evidence with unresolved embedded log ABI and RESULT;
physical SOS, field accuracy, independent power and all three P0 Gates remain
NOT_RUN. Original concurrent checkpoint/recovery and no-ended-call replay
commitments remain open. Next is a real fix with confirmed antenna/sky placement.
