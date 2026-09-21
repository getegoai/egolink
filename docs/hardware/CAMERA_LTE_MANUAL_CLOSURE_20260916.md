---
document_status: hardware_evidence
evidence_date: 2026-09-16
hardware_observed: true
write_performed: true
network_route: sim7670g_lte_ppp
verified_by: founder/codex
---

# CAMERA-LTE-MANUAL-20260916-001 — real-LTE manual Camera and private-API integrity closure

## Outcome

`PASS` for one bounded engineering slice on `connectivity-node-001`: an
authenticated, expiring manual capture command reached the combined collector
over the SIM7670G LTE-data path; the attached OV5640 captured one current QVGA
JPEG; the device recorded separate command, capture, local-save and upload
states; the VPS verified and durably stored the same bytes; and an authorized
private Guardian content-API download matched the device/server byte count and
SHA-256.

The host USB connection supplied board power, serial evidence and the earlier
application flash. The observed data route was the ESP32-managed SIM7670G PPP
interface, not host forwarding or Wi-Fi. This result therefore passes the
bounded **real-LTE manual Camera -> VPS -> private API integrity** slice, but it
is not USB-free or independent-power evidence.

This result does **not** pass browser visual preview/export, default-off timed
capture, complete-outage capture, restart recovery of a pending photo,
controlled Wi-Fi/LTE transition, independent-power operation, endurance,
FIELD-020, Camera product selection or any P0 product Gate. `P0-LOC`,
`P0-CALL` and `P0-SOS` remain `NOT_RUN`.

## Bound image and hardware

- Board: the identified Waveshare ESP32-S3-SIM7670G-4G
  `connectivity-node-001`, connected through CH343 `COM3` for flash, power and
  serial observation. AMOLED and the CALL lane were not part of the run.
- Firmware identity: `0.1.0-camera-lte-trial-015`; test-run identity:
  `camera-lte-trial-20260916-015`.
- ESP-IDF application descriptor: `v0.1.0-135-g114632695-dirty`. Because this
  was a deliberately bound working-tree experiment, the immutable image
  digests below, not the Git suffix alone, identify the executed binary.
- Application SHA-256:
  `281C060625DC5F99EA37C7CAD01C419B65CF7D005ACC98334FFDB6090ED58B26`.
- ELF SHA-256:
  `F3B49C55755F38A4046F433DE4718BFDEEF1E2AA077D87F4C6AD3F24AA7904CB`.
- Runtime profile: SIM present, ESP32 USB-hosted SIM7670G PPP enabled, Wi-Fi
  credentials empty, 600-second firmware bound, Camera still in the explicit
  manual-only `trial_unverified` profile, one hardware Camera attempt per boot,
  and timed capture disabled.
- Camera observed by the joint collector: OV5640. The successful frame was a
  320 x 240 JPEG. GNSS/no-fix, external QMI8658A, LTE and available-power
  observations continued after the photo in the retained window.

The application was written app-only at `0x200000`; that flash did not target
the bootloader, partition table, NVS, collection spool, Camera media store or
outbox. The exact recovery image remains the previously recorded fallback;
this experiment does not relabel the trial profile as a production candidate.

## LTE establishment and bounded runtime

The first USB-modem AT negotiation attempt timed out before dial and was
cleaned up as a retryable pre-dial failure. The second attempt in the same boot
completed `AT`/`ATE0`/dial/`CONNECT`, brought up the `pp2` data interface and
received PPP IPv4 plus IPv6 events. The retained 300-second serial window
contains:

- one LTE link-up event and three PPP IP events;
- 45 ordinary LTE upload result lines, 43 with HTTP 200;
- no USB enumeration failure, PPP user interrupt, panic, brownout, watchdog or
  unexpected reboot marker; and
- continued ordinary uploads with `route=lte` after Camera completion.

This is a bounded coexistence observation, not weak-network reconnect,
loss-free throughput or day-scale stability evidence. By the last retained
health sample, the persistent collection queue had grown to 230,047 bytes with
zero recorded eviction and two recorded errors; backlog growth and the two
non-200 results still require diagnosis before representative field use.

## Manual command, capture and durable upload

Exactly one new manual Camera command was issued for this run:

- capture session: `run015-photo-20260916T043314Z`;
- command: `run015-capture-20260916T043314Z`;
- trigger: `web_manual`;
- validity: two minutes;
- training use: `training_allowed=false`.

The device reported an exact HTTP 200 terminal command ACK with
`status=ok`, `matched=1` and `duplicate=0`. The capture and upload identities
were:

- photo: `manual-9df82b52af19ae3683f61a7e80b793b8-n0`;
- dimensions/format: 320 x 240 JPEG;
- bytes: 3,957;
- SHA-256:
  `D167BEF33EB1B186DA3A71CE3F8785C42A1F2F7F44FD18034FFDB1E263DF29A55`.

The server-side state kept command acknowledgement, capture, local save,
metadata delivery and content delivery separate. It recorded capture
`captured`, local save `saved`, LTE for both metadata and content, and content
`stored`; expected and stored byte counts matched. The VPS returned success
only after matching the content identity and integrity value, after which the
device released the delivered media slot.

An authenticated private Guardian content-API request then downloaded the
same 3,957-byte object. Its local SHA-256, server expected/content SHA-256 and
response integrity header all matched the value above. The JPEG was not opened
through the browser UI, so this proves private API retrieval and byte
integrity—not browser rendering, Web preview controls or human visual review.

## Persistence and post-run state

After the bounded firmware run, the complete 1 MiB `ego_collection` spool was
read without erasing it:

- file:
  `reports/board_validation/CAMERA-SHARED-I2C-TRIAL-20260909-001/private/ego_collection_run015_posttest.bin`;
- bytes: 1,048,576;
- SHA-256:
  `FE8947B9F669F47B577E55E6B634B062F56B184B643500830BB1E143A1A28876`.

The read used `--after no_reset`, so the board was left in the ROM bootloader
at that checkpoint. The already acknowledged run015 JPEG had been released;
this backup therefore does not prove reboot recovery of a pending Camera file.
No erase was performed. The later run016 app-only flash below superseded that
transient bootloader state.

## Post-closure run016 LTE concurrency regression

The concurrency-hardened app-only image
`0.1.0-camera-lte-trial-016`, run
`camera-lte-trial-20260916-016`, was subsequently written and independently
verified at `0x200000`; both operations reported matching digests. No erase was
issued and the bootloader, partition table, NVS, collection spool, Camera media
store and outbox were not targeted.

- Application: 1,204,416 bytes, SHA-256
  `A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`.
- ELF SHA-256:
  `1E09F4AF1279BC08CCA0C36DF642B25ECFEC8638B8693EE4CDDFBEDD26FF7FAD`.
- Retained serial window: 180 seconds, 17,442 bytes; log SHA-256
  `45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.
- Observed counts: one matching START, one LTE link-up, one PPP IPv4 event,
  25 ordinary `route=lte` HTTP-200 uploads and nine fresh healthy LTE status
  snapshots. No stale status snapshot, gate-busy result, link-down, panic or
  Camera event was recorded.
- Between the first and last retained health samples, queued bytes rose from
  502,511 to 605,143, persisted records from 3 to 66 and acknowledgements from
  0 to 21. Errors and evictions remained zero, but the 102,632-byte net growth
  confirms that the current generation/upload rate is not field-sustainable.

No photo command was issued in run016. It is a bounded regression for the LTE
status/PPP upload concurrency changes, not a repeat Camera closure and not
evidence for timed capture, Camera restart recovery, weak-network reconnect or
long-run throughput. USB again supplied power and serial access; SIM7670G PPP
carried data, so independent power remains unverified. The serial window ended
after the required 180-second observation; later power/runtime state is not
inferred from the closed monitor.

## Authorized post-run016 spool preservation and precise clear

Before the next throughput run, the actual partition table and the complete
post-run016 `ego_collection` partition were read back privately. The partition
table readback was 4,096 bytes with SHA-256
`821CCD8D98853D897F401D965694856959FEE9A02C16ADC895A5772D0FBC618A`.
It confirmed `ego_collection` at `0x500000`, length `0x100000`. The complete
1,048,576-byte collection-spool backup has SHA-256
`ECBF85D49344670893C9579F956B937D0990F8AA4A711D512E959CF15238033E`.

Under the founder's explicit authorization to back up and clear the old
Wi-Fi/spool data, only the exact range `0x500000` plus `0x100000` bytes was
erased. A complete immediate readback contained zero non-`0xFF` bytes and has
SHA-256
`F5FB04AA5B882706B9309E885F19477261336EF76A150C3B4D3489DFAC3953EC`.
The operation did not target the application, bootloader, partition table,
NVS, Camera media store or outbox. The board was intentionally held in the ROM
bootloader until the subsequent app-only run017 flash, preventing an
intermediate boot from refilling the cleared collection partition. Run017 then
used that verified empty-spool starting point; its normal observations mean
this paragraph must not be read as a claim that the partition is still blank.

## Post-clear run017 empty-spool throughput regression

The app-only run017 image `0.1.0-camera-lte-trial-017`, run
`camera-lte-trial-20260916-017`, was written at `0x200000` and passed a
separate `verify_flash`. Its 1,204,416-byte application SHA-256 is
`07CF1EF3FEA13548FB9B7F5EF8F5C965FE6B6BF53EBD6AE9369F2E8CF0223529`;
its ELF SHA-256 is
`F9D47609BEB820803B2919B1F01B70D3B82E62FF8928F84CCD1ABB294919854A`.
The app flash did not target any data partition. The only throughput-oriented
profile change from run016 was extending the Camera command poll interval from
2 seconds to 15 seconds; sensor sampling remained unchanged.

The retained capture covered 620 seconds around a firmware-bounded 600-second
run and ended with one bounded-complete marker. Its 57,156-byte private log has
SHA-256
`FABC0C2ED5E6DCE4DDCCBDBF33524C681FF3DA32E50DCEA65CAB46E61895CA63`.
The first USB-modem probe timed out at approximately 9.7 seconds, completed its
bounded quiesce/backoff path, and the next attempt established PPP at about
34.9 seconds. The log then contains one LTE link-up, one PPP IP event and 248
ordinary LTE upload results. All 248 returned HTTP 200, matched a local pending
record, were accepted durably and were locally acknowledged. Sixty-five TLS
handshakes were observed. Across 20 health samples, the queue reached an initial
55,842-byte pre-PPP peak, cleared by approximately the 124-second sample, then
stayed between 0 and 6,658 bytes and ended at 0. The steady segment's endpoint
net slope is zero; an ordinary least-squares fit over the phase-shifted sawtooth
samples is slightly positive at about 3.28 bytes/second, so this evidence is a
bounded no-net-growth result rather than a claim that every fitted slope metric
is non-positive. Evictions, RAM-pending records, recorded errors, stale-status
snapshots, gate-busy results, link-down events, panics and Camera events all
remained zero.

No photo command was issued in run017. USB supplied power and serial/flash
access while SIM7670G PPP carried the data. This closes the immediate sustained
ordinary-observation throughput blocker for this empty-spool, ten-minute,
USB-powered bench scope. It does not prove browser preview, timed Camera
capture, complete-outage or restart photo recovery, Wi-Fi/LTE transition,
independent power, endurance, FIELD-020 or any P0 Gate.

## Evidence handling

Private raw serial data, the spool readback and the authorized test JPEG remain
only under the Git-ignored directory:

`reports/board_validation/CAMERA-SHARED-I2C-TRIAL-20260909-001/private/`

The manual Camera closure log is `run015_lte_ppp_tx_wait.raw.log`, SHA-256
`418FC074D5B32EC86838B2F315295A1AA8536D60A3B3D6A485069FFDD630FD5C`.
The post-closure regression log is
`run016_lte_concurrency_regression.raw.log`, SHA-256
`45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.
The post-run016 preservation files are
`partition_table_run016_posttest.bin`,
`ego_collection_run016_posttest.bin` and
`ego_collection_run016_postclear.bin`; their digests and bounded meanings are
recorded above. The empty-spool throughput log is
`run017_empty_spool_throughput.raw.log`, SHA-256
`FABC0C2ED5E6DCE4DDCCBDBF33524C681FF3DA32E50DCEA65CAB46E61895CA63`.
The private API download is
`run015-manual-9df82b52af19ae3683f61a7e80b793b8-n0.jpg`, whose digest is
recorded above. This document intentionally omits credentials, precise
coordinates, cell identifiers, raw payloads and scene bytes. No image or raw
log is committed, publicly served or approved for training.

## Remaining milestone work

1. Verify the same stored-photo identity through the authorized browser UI,
   including actual JPEG decode/preview and export controls.
2. Promote only the evidence-backed Camera/LTE behavior into a separately
   identified candidate; prove default-off timed enable/disable, expiry,
   complete-outage local capture and same-file restart recovery without
   catch-up recapture.
3. Carry the run017 15-second command-poll result into the separately validated
   field candidate, then extend throughput evidence beyond the ten-minute
   empty-spool bench scope while accounting for every error, retry, eviction,
   duplicate and loss.
4. Prove a controlled Wi-Fi/LTE transition without identity/time drift, then
   run the independently powered single-board coexistence short test.
5. Dispatch FIELD-020 only after those blockers close. CALL, complete SOS and
   the three sellable-P0 Gates remain separate later obligations.
