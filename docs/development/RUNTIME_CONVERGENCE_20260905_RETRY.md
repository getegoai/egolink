---
document_status: experiment_proposal
source_task: P0-CONVERGENCE-20260905
created: 2026-09-05
execution_state: historical_requests_superseded_by_operator_continuation_authorization
---

# One corrected Location run

The original proposal below was subsequently approved and executed as run 002;
the separately approved stack batch was executed as run 003. See the appended
[actual results](RUNTIME_CONVERGENCE_20260905_RUN001.md#subsequent-authorized-runs-002-and-003--actual-bench-results).
The proposals below are historical. The operator subsequently said
`你继续，不用我批准`, authorizing continuous necessary fixes and bounded
same-scope no-SIM bench runs without per-image or per-batch confirmation.
Run 005 exercised real no-fix delivery; run 006 verified the resulting identity
and telemetry corrections; run 007 verified powered GNSS acquisition dwell.
Exact limits and recovery remain recorded in each
run's `operator_authorization.json` and `batch_bounds.json`. These old requests
must not restart an approval loop. Audio, physical SOS, SIM traffic and external
notifications remain outside the current Location experiment.

The first approved live boot failed before modem startup and FW-007 is restored.
[Run 001](RUNTIME_CONVERGENCE_20260905_RUN001.md) retains the failure, exact
readback, restore and native diagnosis. The corrected image and tests are ready.
This proposal requests **one additional candidate flash/boot and its restoration**,
with a new outbox write range; it is not an automatic retry of the consumed scope.

## Concrete change and artifacts

Only the live profile moves the 48 KiB outbox from occupied
`0x110000..0x11c000` to `0x1f4000..0x200000`, entirely erased in the already saved
2 MiB readback. Unknown old bytes are preserved. NVS/PHY/factory geometry stays
the same. The real partition/core replay against that dump passes at the new
address in RAM; this does not claim a hardware pass. Logs now identify exact
partition/core/slot outcomes and write counts. Source/image/test identities are
in `tmp/convergence_partition_fix_manifest.json`.

Candidate directory: `tmp/convergence_live_partition_fix_build/`.

| Region | Offset | Bytes | SHA-256 |
|---|---|---:|---|
| bootloader | `0x0` | 20,928 | `61a1b78dc34a8e75dda5c5de8a1f24d16551a57951dd9e785e85419344a5a18b` |
| partition table | `0x8000` | 3,072 | `561cc491c9bbf9ce11460824f53b1dff8ecc04f045a46c631bada3a987b171bc` |
| application | `0x10000` | 990,224 | `97af7f2fdee31d5fb8fb9efcd6da856e9ce9c7e4f843acb3e90e99cb5a1713d1` |

Legacy and live build passed. Full regression: 1,630 passed / five explained
skips; S generated-build rerun 9/9. Firmware protocol, TLS trust/hostname checks,
exact ACK rules, modem owner, GNSS and runtime limits retain the first image's
behavior. Boot storage corruption remains an explicit stop; runtime queue/write
failure still advances local state with persistence degradation.

## Device, endpoint and budgets

- Connectivity node only: COM3 CH343 serial `5B91047400`, MCU MAC
  `02:00:00:00:00:03`, ESP32-S3 rev v0.2. Keep the operator-confirmed SIM absent.
  Reidentify USB/MCU once before flashing; no additional full flash readback.
- Recheck the deployed source/service and verified HTTPS health through wired
  interface 19, source `192.168.31.99`; pin/read back the per-socket interface.
  Origin remains `https://ego.example.invalid`, with existing separate device and
  bound test-Guardian credentials. No server redeploy or global route change.
- One candidate flash of the three listed regions; one application boot.
  Owner runtime 180 s, at most four GNSS operations of 12 s each, six HTTPS
  attempts of 12 s each, at most 32 durable slot-write callbacks, and one NVS
  boot-epoch commit/readback. Absolute host capture/stop boundary 300 s.
- At most 256 KiB serial bytes seen; retain only source/quality/state/ACK/error
  metadata. Use the two remaining authorized Guardian current queries after
  real input; no fabricated ingestion. No audio, raw Location payload log,
  recording, physical SOS or external notification.
- The existing connector caps each request body at 4 KiB and response including
  HTTP headers at 16 KiB, with six attempts. These application limits are
  enforceable. **Whole-link Wi-Fi bytes, TLS handshake and retransmission bytes
  are not metered**; the earlier 2 MiB link ceiling cannot be claimed verified.
  This revised proposal uses finite request/time bounds for the no-SIM Wi-Fi
  run, not an invented measured link-byte result.

## Stop, restore and acceptance

Stop immediately for wrong device/image, failed auth/TLS identity, unexpected
reset/brownout/thermal problem, duplicate modem ownership, exceeded limits,
storage initialization failure, or incomplete cleanup. GNSS no-fix/error is an
honest source result and may still be uploaded; it is not a precise-location pass.
Do not restart the candidate after a failure. Ask the operator to remove power
only if normal bounded stop/restore cannot establish the intended safe state.

Restore once after evidence collection or a runtime failure, using the actual
FW-007 three-region set already verified and accepted in run 001:
bootloader `1eddd94a293c483af64afa6c1eed83efa24d6fd7746a5d07afeefc189364b66e`,
partition `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820`,
app `a9894a86834aa6517e5947f011b50a8af223656d74fcfb68f911ee39efa36c7d`.
Verify transfer hashes and take a 30 s metadata startup smoke, then close COM3.
No raw-dump restore or NVS erase. Retain the new outbox range after restoration;
do not erase evidence to make a later boot appear fresh. No extra image or
erase retry is authorized if restore fails.

The run succeeds only if real source state is processed by the sole owner,
the exact event receives a matched secure ACK, the bound Guardian projection
shows honest source/age/quality, and bounded cleanup is observed. Missing UTC
mapping, device TLS evidence, correct ACK or cleanup is reported explicitly.
P0-LOC/P0-CALL/P0-SOS remain NOT_RUN until their respective broader acceptance.
CALL and its original post-stop/concurrent recovery obligations remain separate;
this request adds no CALL, SIM or physical SOS run.

## Completed request — one startup-diagnostic image

Run 003 established Wi-Fi/SNTP, persistent mirrors and adequate main-stack
headroom, but failed GNSS-off confirmation. Its network-conditioned second boot
was inapplicable. The prepared fix calls Q's existing bounded stop on that failure
and logs the exact owner/driver outcome before and after cleanup. Native behavior
and legacy/live builds pass; it is not yet hardware evidence.

Request one flash and one boot on the same no-SIM COM3/MAC node, using
`tmp/convergence_live_stop_fix_build/` and the exact identities in
`tmp/convergence_live_stop_fix_manifest.json`: application 991,456 B /
`139cdbc98f57ca07405ed989b9b6dabbf7217fcceda9de4789570d4f94f8c4fd`;
bootloader `fae638e74a0a85af9aa94d03b5fa8459fc011b6eae808065f2faa5d9dfa6bc37`;
partition `561cc491c9bbf9ce11460824f53b1dff8ecc04f045a46c631bada3a987b171bc`.
Only the normal three image regions are flashed; outbox stays at `0x1f4000`.

Retain the finite bounds above: 300 s host capture, 256 KiB serial bytes,
180 s owner runtime, four location acquisitions, six HTTPS attempts, 32 outbox
slot writes and one boot-epoch update. Power-off uses Q's existing bounded
commands; after stop, at most three cleanup attempts. Application body/response
caps remain enforced; total Wi-Fi link bytes are unmetered. No SIM insertion,
audio, physical SOS or notifications. Wired HTTPS/source/service preflight must
pass first; currently both HTTPS and SSH connects time out from this PC.

On STOP, panic, unexpected reboot, TLS/auth failure or limit, capture metadata
and hold ROM if quiescence is unconfirmed; do not automatically start again.
Restore the already approved actual FW-007 three-region set above, verify transfer
hashes, observe its descriptor for 30 s and close COM3. If ROM entry/restoration
cannot finish, stop and request operator power removal. This request requires
one combined approval because the prior specific image/conditional-start budget
does not authorize this new image; it does not reopen routine command approvals.

## Pending request — continue after confirmed startup recovery

The diagnostic batch above was approved by `你继续` and completed as run 004.
It proved that the first terminal ERROR can be followed by confirmed GNSS off
on the same owner; the application nevertheless exited before requesting a
sensor. The prepared live-only fix now waits at most 10 s for Q's existing
recovery to ACTIVE and otherwise uses the proven stop path. It does not restart
Q or accept ERROR as success. Guardian's tested page fix is now deployed.

Request one flash of this prepared image and **at most two live startups** on
the same no-SIM COM3/MAC node. The second startup is only for a remaining
network/GNSS retry after the first has confirmed quiescence with no fatal,
authentication or certificate error; there is no automatic repeat on unsafe
failure. Each startup retains the 300 s host / 180 s owner limit, four location
acquisitions, six HTTPS attempts, 32 slot writes and 256 KiB serial cap: batch
maximum 600 s live capture, eight acquisitions, 12 HTTPS attempts, 64 slot writes,
two boot-epoch updates and 512 KiB serial. Use at most the two remaining Guardian
current queries after real input. Whole-link Wi-Fi bytes remain unmetered.

Directory `tmp/convergence_live_recovery_wait_build/`; exact source/config/image
identities: `tmp/convergence_live_recovery_wait_manifest.json`. App 991,872 B /
`aabff0890cbacd1526411ec785276114a2547af607711320a88781db17d92e24`;
bootloader `de3fa86e41f42f7d2b1a397857d8592fce21b92d5582e117d00786ccda4d3b99`;
partition `561cc491c9bbf9ce11460824f53b1dff8ecc04f045a46c631bada3a987b171bc`.
Flash only the same three regions; preserve outbox/NVS geometry and prior bytes.

Reidentify the device and verify wired HTTPS/source/service before starting.
All existing wrong-device/image, TLS/auth, fatal/reboot and budget stops remain.
On unconfirmed cleanup hold ROM, then restore the approved actual FW-007 three
regions; verify transfers and perform the 30 s descriptor smoke before closing
COM3. Stop for operator power removal if ROM entry/restoration fails. No SIM,
CALL/audio, physical SOS, notifications, new firmware variant or extra readback
is included. This is a new prepared image after the consumed diagnostic startup;
one batch approval covers its execution without per-command questions.
