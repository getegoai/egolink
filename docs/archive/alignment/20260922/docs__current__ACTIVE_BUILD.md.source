---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-09-21
verified_by: codex
---

# Active Build

## 2026-09-21 current hardware state — run022 cellular call driver & ego-state engine field candidate live flash (Boot 188)

The identified connectivity board on CH343 `COM3` executes the candidate image (`0.1.0-sensor-policy-continuous-021`, run `field-sensor-policy-20260919-021`) integrating the Phase 3 Task B1 cellular voice AT channel driver (`sim7670_cellular_call`), the native ego-state estimation engine (`ego_state_engine`), dynamic sensor policy continuous collection (`collection_sensor_policy`), SIM7670G USB LTE PPP, and I2C 9-clock bus self-healing (`platform_i2c_bus_recover`).
Its 1,228,080-byte application SHA-256 is `f9869caeab2b4fce9cae2d553d9d0142dbb63e37bc386237a0524325712c6d3f`; its ELF SHA-256 is `420d7607e026cc37d4cc03e9781ecb95abcb19d5d09cd3858ae3a0979efe9aa5`.
It was written app-only at `0x200000`; `verify_flash` confirmed exact digest match (`verify OK (digest matched)`).
In Boot 188, camera runtime debug heap/stack metrics were trimmed from the `HEALTH` sub-record, sizing the overall `DEVICE` frame well within `COLLECTION_FRAME_CAPACITY` (4000 bytes) and eliminating flash spool drop risks. Boot 188 booted with `lte_ppp_opt_in=1`, GPIO 15/16 9-clock clearing, MAX17048 probe `0x0012`, QMI8658 probe `0x05`, ego-state engine initialized (`EGO_STATE_ENGINE initialized successfully`), SIM7670 UART1 exclusive AT ownership (`SIM7670_EXCLUSIVE_UART_READY uart=1 tx_gpio=18 rx_gpio=17 baud=115200`), cellular call driver initialized and configured (`SIM7670_CELLULAR_CALL initialized and configured successfully`), USB LTE PPP connection and IP acquisition (`ETHIP:10.49.186.235`), and continuous telemetry upload over 4G LTE. Live VPS ingestion confirmed `col-b188-device-1` with `ego_state` (`spatial_mobility: "stationary"`, `device_wear_state: "tabletop_resting"`, `confidence: 0.83`) stored durably in `collection_ego_states`. Full repository verification passed 1,833/1,833 automated tests.

## 2026-09-19 prior hardware state (run021)

The identified connectivity board on CH343 `COM3` executes the dynamic sensor policy continuous running candidate image (`0.1.0-sensor-policy-continuous-021`, run `field-sensor-policy-20260919-021`) with `run_seconds=0` (continuous collection session), verified shared-I2C camera profile, SIM7670G USB LTE PPP, I2C 9-clock bus clearing & 3x retry probe loop (`platform_i2c_bus_recover`), and the native dynamic sensor policy engine (`collection_sensor_policy`).
Its 1,216,912-byte application SHA-256 is `79c0dae8689ffd91601303735384a3e7ab03a4f83b633af04eba7779c1a0bc54`; its ELF SHA-256 is `2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87`.
It was written app-only at `0x200000`; `verify_flash` confirmed exact digest match.
Boot 171 booted with `run_seconds=0`, `lte_ppp_opt_in=1`, GPIO 15/16 9-clock clearing, MAX17048 probe `0x0012`, QMI8658 probe `0x05`, dynamic policy config `p0-sprint1-engineering-default-20260823`, USB LTE PPP IP acquisition (`ETHIP:10.45.175.95`), TLS certificate validation, and continuous telemetry uploads returning HTTP 200 with zero evictions.
Real hardware stationary accelerometer RMS was measured on bench at `0.157 m/s²` (well below `0.3 m/s²` stationary threshold, correctly classified as `stable`).
Live VPS Message Hub (`https://ego.example.invalid`) received verified telemetry across all sources (`session`, `device`, `imu`, `power`, `gnss`, `lte`, `wifi`) containing the full `sensor_policy` payload (`motion_rms_m_s2`, `mobility_state`, `gnss_interval_ms`, `cell_interval_ms`) and startup session records.

## 2026-09-18 prior hardware state (run020)

The identified connectivity board on CH343 `COM3` executes the dynamic sensor policy continuous running candidate image (`0.1.0-sensor-policy-continuous-020`, run `field-sensor-policy-20260918-020`) with `run_seconds=0` (continuous collection session), verified shared-I2C camera profile, SIM7670G USB LTE PPP, and the native dynamic sensor policy engine (`collection_sensor_policy`).
Its 1,215,856-byte application SHA-256 is `b64c72a1df2cc5cc1424e656a49e0bcbe22da855aee4ef932bd83b55b889567c`; its ELF SHA-256 is `126639b1eec7fa431a08667a2ad0a0ae530271e86110db3c8b47d46eceffc10f`.
It was written app-only at `0x200000`; `verify_flash` confirmed exact digest match.
Boots 152 and 153 booted with `run_seconds=0`, `sensor_policy_enabled=true`, QMI8658 probe `0x05`, MAX17048 probe `0x0012`, dynamic policy config `p0-sprint1-engineering-default-20260823`, USB LTE PPP IP acquisition, TLS cert validation, and continuous telemetry uploads returning HTTP 200 with zero evictions.
Real hardware stationary accelerometer RMS was measured on bench at `0.0220 m/s²` (well below `0.3 m/s²` stationary threshold, correctly classified as `stable`).
Live VPS Message Hub (`https://ego.example.invalid`) received verified telemetry containing the full `sensor_policy` payload (`motion_rms_m_s2`, `mobility_state`, `gnss_interval_ms`, `cell_interval_ms`) and startup session records with `sensor_policy_enabled=true`.

## 2026-09-17 prior hardware state (run019)

The identified connectivity board on CH343 `COM3` executes the continuous running candidate
image (`0.1.0-camera-lte-continuous-019`, run `field-continuous-20260917-019`) with
`run_seconds=0` (continuous collection session), verified shared-I2C camera profile,
and SIM7670G USB LTE PPP.
Its 1,204,352-byte application SHA-256 is
`a67601c4001490eddf983e6f62ff00334dc0c9c22874b5229ff332f08d7f7481`; its ELF
SHA-256 is
`f3f3e5989103cb23068dc851948bf390863ae4e636d37b717e90d295e817814d`.
It was written app-only at `0x200000`; `verify_flash` confirmed exact digest match.
Boot 142 booted with `run_seconds=0`, `stop_method=hold_BOOT_1_second_or_configured_deadline`,
QMI8658 probe `0x05`, SIM7670G UART ready, USB LTE PPP IP `10.65.88.136`, established TLS,
and active telemetry delivery to the VPS message hub.

## 2026-09-17 prior hardware state (run018)

In run018 (`run018_timed_candidate_full.raw.log`, 73,648 bytes, SHA-256
`B860E339EFE279465835253336EAF41011ABB99B078B48AB74FAF6A85C9D5737`), the board
booted with `shared_i2c_state=verified` and `timer_capture_allowed=1`, mounted
the 9 MiB `ego_media` partition, established SIM7670G USB LTE PPP at 35 seconds,
polled capture command `cmd-capture-1789620168691`, triggered the OV5640,
persisted the 3,657-byte JPEG `manual-1400e20507f538839dec32a6b93ddcc5-n0`
(SHA-256 `911a8ab6c60ae819e3749f55daa9ba4be72adc3b01ebfd25a648cd1da1168232`)
to flash media store, and uploaded it over LTE PPP to the VPS. The VPS durably
stored the image on disk and marked `content_status='stored'`. The device
acknowledged the command (`PHOTO_COMMAND_ACK status=ok http=200`).
Concurrently, 391 ordinary observation uploads were delivered and acknowledged
with HTTP 200, completely draining the 608,911-byte queue to zero
(`queued_bytes=0`). Evictions, RAM-pending records, panics, and link drops were
zero.

AMOLED is excluded from this A-line milestone and its UI/CALL image is
unchanged. The untracked `hardware/mechanical/C-ME-0.1/` founder draft is also
excluded and unchanged.

## 2026-09-16 prior hardware state (run017)

The connectivity board previously executed the run017 app-only image
`0.1.0-camera-lte-trial-017` (SHA-256
`07CF1EF3FEA13548FB9B7F5EF8F5C965FE6B6BF53EBD6AE9369F2E8CF0223529`).

## 2026-09-17 camera timed candidate build & browser export verification

1. **Browser visual preview and export verification**:
   The exact stored run015 JPEG `manual-9df82b52af19ae3683f61a7e80b793b8-n0`
   (3,957 bytes, SHA-256 `d167bef33eb1b186da3a71ce3f8785c42a1f2f7f44fd18034ffb1e263df29a55`)
   was restored into the VPS private photo storage with an authorized 7-day retention
   (`2026-09-24T00:00:00.000Z`). An authenticated HTTP GET request to
   `/api/v1/devices/ego-link-001/photos/manual-9df82b52af19ae3683f61a7e80b793b8-n0/content`
   with Guardian bearer authentication confirmed HTTP 200 `image/jpeg` with
   matching byte count and SHA-256. Web DevBench (`/dev`) provides authenticated
   thumbnail display, full-resolution dialog, and direct JPEG download.

2. **Timed candidate promotion build**:
   The shared-I2C camera profile was promoted from `UNVERIFIED_TRIAL` to
   `VERIFIED` via `sdkconfig.camera_timed_candidate.defaults`
   (`CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED=y`).
   Clean ESP-IDF v5.4.2 build:
   - Application binary: `1,104,960` bytes (0x10DC40), 65% partition free space.
   - Application SHA-256: `0450DED50949CD496CD4BD610956F89F4F32C8F74CB6F667CE677AE1D48C4A2F`.
   - ELF binary: `11,211,372` bytes, SHA-256: `1FCEAA51B30697E9F3DF9F21267526F82FE1A32C16B3107AD049B8E612E2EE20`.
   - Profile unlocks `platform_camera_timed_capture_allowed()`, admitting
     `configure_photo_timer` commands, local interval scheduling, and reboot recovery.
   - Unflashed build evidence only; live execution awaits operator authorization.

## 2026-09-16 empty-spool LTE throughput regression — current flashed image

Before run017, the actual 4,096-byte partition table was read back with
SHA-256
`821CCD8D98853D897F401D965694856959FEE9A02C16ADC895A5772D0FBC618A`.
It confirmed the `ego_collection` partition at `0x500000`, length `0x100000`.
The complete post-run016 1,048,576-byte spool was preserved privately with
SHA-256
`ECBF85D49344670893C9579F956B937D0990F8AA4A711D512E959CF15238033E`.
Under the founder-authorized old-Wi-Fi/spool clear, only that exact range was
erased. The immediate complete readback was all `0xFF` (`nonFF=0`), SHA-256
`F5FB04AA5B882706B9309E885F19477261336EF76A150C3B4D3489DFAC3953EC`.
The application, bootloader, partition table, NVS, Camera media store and
outbox were not targeted. The board remained in the ROM bootloader until the
run017 app-only flash, so run017 began from the verified empty spool; normal
run017 observations subsequently repopulated the partition.

Run017 changed the Camera command poll interval from 2 seconds to 15 seconds
without changing sensor sampling. Its 620-second private serial capture around
the 600-second firmware bound records one bounded first-probe timeout and clean
quiesce/backoff before PPP established at about 34.9 seconds. It then contains
one LTE link-up, one PPP IP event, 248 ordinary LTE uploads and one bounded-
complete marker. All 248 uploads returned HTTP 200, matched local pending
records, were accepted durably and were locally acknowledged; 65 TLS handshakes
were observed. Across 20 health samples, an initial 55,842-byte
pre-PPP queue peak cleared by approximately 124 seconds. Thereafter the queue
stayed between 0 and 6,658 bytes and the final health sample reported zero.
Evictions, RAM-pending records, errors, stale-status snapshots, gate-busy
results, link-down events, panics and Camera events were all zero.

No photo command was sent. USB supplied power and serial/flash access while
SIM7670G PPP carried data. This closes the immediate sustained
ordinary-observation throughput blocker for this ten-minute empty-spool bench
scope only; it does not establish independent-power, endurance, route-change,
Camera outage/restart, FIELD-020 or P0 evidence. The 57,156-byte private log is
`run017_empty_spool_throughput.raw.log`, SHA-256
`FABC0C2ED5E6DCE4DDCCBDBF33524C681FF3DA32E50DCEA65CAB46E61895CA63`.

## 2026-09-16 LTE concurrency regression — prior run016 image

The prior run016 image preserves the descriptor suffix
`v0.1.0-135-g114632695-dirty`. Its 1,204,416-byte application SHA-256 is
`A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`;
its ELF SHA-256 is
`1E09F4AF1279BC08CCA0C36DF642B25ECFEC8638B8693EE4CDDFBEDD26FF7FAD`.
These immutable digests bind the distinct run016 build. The 180-second private
serial capture contains one matching START, one LTE link-up, one PPP IPv4
event, 25 ordinary `route=lte` HTTP-200 uploads and nine fresh healthy
LTE-status snapshots.
There was no stale status snapshot, gate-busy result, link-down, panic or
Camera event.

The retained health samples also show `queued_bytes` rising from 502,511 to
605,143 between the first and last sample while persisted records rose from 3
to 66 and acknowledgements from 0 to 21. Errors and evictions remained zero in
that window, but the positive net backlog proves the current source rate and
single-record HTTPS path are not yet sustainable for field use.

No photo command was sent during run016. This is a focused regression for the
LTE status/PPP concurrency fix and continued ordinary data delivery, not a
second Camera test. USB supplied power and serial access; the data path was
SIM7670G PPP, so this remains neither independent-power nor FIELD-020 evidence.
The 17,442-byte private log is
`run016_lte_concurrency_regression.raw.log`, SHA-256
`45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.
The app write and independent verification matched without erasing any other
partition.

## 2026-09-16 real-LTE manual Camera and private-API checkpoint

The bound run015 image advertises application descriptor
`v0.1.0-135-g114632695-dirty`. Its application SHA-256 is
`281C060625DC5F99EA37C7CAD01C419B65CF7D005ACC98334FFDB6090ED58B26` and its
ELF SHA-256 is
`F3B49C55755F38A4046F433DE4718BFDEEF1E2AA077D87F4C6AD3F24AA7904CB`;
these immutable digests, not the shared dirty descriptor suffix, identify the
executed run015 build. Its Wi-Fi credentials were empty, LTE PPP was selected,
the runtime limit was 600 seconds, timed Camera capture was disabled and at
most one actual manual Camera attempt was allowed in the boot.

The first USB-modem negotiation failed before dial and was cleaned up for a
same-boot retry. Attempt two completed `CONNECT`, brought up `pp2`, obtained PPP
IP events and carried ordinary uploads with `route=lte`. The retained
300-second serial window contains one link-up, three PPP IP events, 45 LTE
ordinary-upload results, 43 HTTP-200 results, and no enumeration failure, PPP
user interrupt, panic, brownout, watchdog or unexpected reboot marker.

One new authenticated command was issued: session
`run015-photo-20260916T043314Z`, command
`run015-capture-20260916T043314Z`, two-minute TTL,
`trigger_reason=web_manual`, `training_allowed=false`. The device returned an
exact HTTP 200 `ok` command ACK (`matched=1`, `duplicate=0`), identified the
OV5640 and produced photo
`manual-9df82b52af19ae3683f61a7e80b793b8-n0`, a 3,957-byte 320 x 240 JPEG.
The VPS verified and durably stored the content before exact ACK; an authorized
private Guardian content-API download matched the device/server byte count and
SHA-256
`D167BEF33EB1B186DA3A71CE3F8785C42A1F2F7F44FD18034FFDB1E263DF29A55`.
GNSS/no-fix, external IMU, LTE and available-power observations continued after
the photo in the retained window.

USB supplied power, serial observation and flash access, but the observed data
route was ESP32-managed SIM7670G PPP rather than host forwarding. This passes
one bounded real-LTE manual Camera -> VPS -> private-API byte-integrity slice;
it does not pass browser preview/export, timed/outage/restart behavior,
controlled Wi-Fi/LTE transition, independent power, endurance, FIELD-020 or a
P0 Gate. Details and private evidence handling are in
[CAMERA-LTE-MANUAL-20260916-001](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md).

## 2026-09-09 Camera shared-I2C trial — flashed Wi-Fi checkpoint

The ignored run006 overlay bound firmware
`0.1.0-camera-trial-80c5e86-006`, run
`camera-trial-20260909-006`, a 300-second runtime bound, manual-only Camera,
`NO_SIM=y` and LTE PPP disabled. The 1,104,464-byte app has SHA-256
`EE2FA5A3D2B65186B3A80597C1C574CAA66CBEB66DA5A5EE2125B3086C299D0D`;
the ELF SHA-256 is
`6686F8E8BC1CECC19AEE4F89F01F2161DF3108847357BD9E64515DE9B3DD42EA`.

The joint collector recovered the existing run005 metadata and 5,448-byte
JPEG across reboot with exact server hash
`19ca7a584d4d44bd1f874fce36233ae5d194a1011a2778a9fada2bf41224c369`.
The first fresh run006 command captured and eventually stored a distinct
2,665-byte JPEG with exact hash, but old collection backlog/server `422`
responses delayed metadata until the two-minute command expired; it therefore
did not earn a command ACK pass.

Under the existing founder spool-clear authorization, the complete 1 MiB
Camera-layout collection partition was saved privately with SHA-256
`ABEC92241968E7B5C23677FDE0A5A0F4B2DD8FB9DBDF083B2A218B3FCBDEEFB1`,
then only `0x500000..0x600000` was erased. The immediate complete readback was
all `0xFF`, SHA-256
`F5FB04AA5B882706B9309E885F19477261336EF76A150C3B4D3489DFAC3953EC`.
Later bounded boots repopulated that partition.

The clean run006b command returned an exact matched HTTP 200 `ok` ACK. OV5640
photo `manual-990f9579033d6372637b0da53c99f0dd-n0` was a 320 x 240 JPEG,
2,707 bytes, SHA-256
`f556e97da859083ae6a67f64fee3f1dc05d1cea29928611d52b1a45fa9314c2e`;
the VPS stored the same bytes before exact content ACK. GNSS, external IMU and
Wi-Fi work continued in the observed windows without panic, brownout,
watchdog, stack overflow or unexpected reboot. Boots 87 through 89 reached the
normal bounded stop sequence; the shorter final boot-90 evidence window does
not claim its later terminal stop line.

This is a manual Wi-Fi bench checkpoint, not real LTE, timed/offline capture,
independent power, Web visual-preview or FIELD-020 evidence. Details and
private-evidence handling are in
[CAMERA-SHARED-I2C-TRIAL-20260909-001](../hardware/CAMERA_SHARED_I2C_TRIAL_20260909.md).

## 2026-09-09 Camera shared-I2C trial — clean offline build checkpoint

The normal Camera collector remains fail-closed with the shared-I2C Gate at
`BLOCKED`. A separate tracked engineering overlay now selects
`UNVERIFIED_TRIAL`: it permits at most one actual Camera/I2C attempt per boot,
only through the existing authenticated `capture_photo_once` command path.
Failure to acquire the capture lock does not consume the attempt; once hardware
access begins, success or failure consumes it. Timed capture is rejected in
this mode, including inherited or in-flight enable state from an older verified
image. A genuine disable command remains valid.

The strict Camera `source_status` stays unavailable until the Gate is actually
`VERIFIED`; manual-trial readiness, Gate state and remaining attempt are
reported separately. Capture journal v2 persists the capture-time Gate, driver
profile, runtime config, firmware version and ELF digest. A recovered v1 entry
is labelled `unknown_legacy` and cannot borrow the current image's provenance.
This closes the circular offline implementation blocker; it does not verify
shared-I2C electrical or runtime coexistence.

Four ESP-IDF 5.4.2 no-flash profiles were rebuilt from clean commit
`ef3c06f6a9fd33ab604363ef9f6622dfbd02c1bb` and size-checked:

| Profile | Defaults / Gate | App bytes / partition | Free | SHA-256 |
|---|---|---:|---:|---|
| default | `sdkconfig.defaults`; Camera off | 896,240 / 1 MiB | `0x25310` (15%) | `2EDC9153E618329378645D03FB8D808E68936179403FD7C9D2F88AFEA434A9AC` |
| legacy collector | `sdkconfig.defaults;sdkconfig.collection.defaults`; Camera off | 991,568 / 1 MiB | `0xDEB0` (5%) | `CF265EA61F3F275216F592F865E6810AC85B5A30B0415CA1F071EF60626E9317` |
| Camera blocked | `...;sdkconfig.camera_collection.defaults`; `BLOCKED=y` | 1,033,680 / 3 MiB | `0x203A30` (67%) | `E00474A5610011527DB6CBD62BF62E074C20D831FBB848B09B10BA0275572AA1` |
| Camera trial | Camera blocked defaults plus `sdkconfig.camera_shared_i2c_trial.defaults`; `UNVERIFIED_TRIAL=y` | 1,101,648 / 3 MiB | `0x1F30B0` (65%) | `320B7D51726B91ABAE6CD83B797038DC77232AE72D3094308825708223E02333` |

All four checkpoint binaries embed application version
`v0.1.0-123-gef3c06f6a` without `-dirty`; the worktree was clean before and
after the matrix. They are no-flash review artifacts, not flashed images or
live evidence.

The Camera partition profile places `factory` at `0x200000..0x500000`,
`ego_collection` at `0x500000..0x600000`, `ego_media` at
`0x600000..0xF00000`, and `ego_outbox` at `0xF00000..0xF0C000`. This is build
geometry, not permission to erase or flash. The full future media range was
privately read on 2026-09-09: all 9,437,184 bytes were `0xFF`, SHA-256
`BE1C8C26FAAE3AE3606606C9641F017A873F52A7833C9CF65142EF0E2405CE8A`,
and a subsequent `verify_flash` readback returned `verify OK`. The current
observed-occupancy check therefore passes; initialization will still
deliberately scrub non-valid slots only inside that exact partition after an
authorized flash. See
[CAMERA-MEDIA-001](../hardware/CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md).

Both Camera profiles retain `NO_SIM=y` and LTE PPP disabled. The blocked image
cannot capture. The clean trial image proves the build/size boundary only: its
compiled Wi-Fi SSID, Wi-Fi password and bearer token are empty, so its exact
SHA cannot connect to the current Web command path and must not be flashed as a
live candidate. The later authorized run006 checkpoint used an ignored named
private overlay, a new rebuild and the separately bound SHA recorded above.
Neither clean checkpoint image, nor the run006 Wi-Fi image, is the required
real-LTE Camera candidate.
Camera deinit is only a software standby boundary because the present pin map
has no PWDN; the raw JPEG partition is not encrypted. The four tabled clean
checkpoint images were not flashed; the separately rebuilt run006 image was.

The current static map puts OV5640 `0x3C`, MAX17048 `0x36` and QMI8658A `0x6A`
on I2C0 GPIO15/16 at 100 kHz. The run006 series now observes bounded Camera and
IMU coexistence on the joint image, but the image deliberately remains
`UNVERIFIED_TRIAL`; this is not a product electrical/endurance result. This
candidate uses an internal-DRAM frame buffer and legacy shared-I2C0. Camera
PCLK and TF card-detect both use GPIO46: remove the TF card,
keep the TF driver disabled, and do not attach external GPIO JTAG on GPIO39-42
during the joint test. Static ELF headroom is not runtime memory evidence; live
acceptance must retain pre/during/post capture internal/DMA heap, largest DMA
block, task-stack watermarks, sensor continuity and reset/UART/watchdog status.

## Previous actual collector image - 2026-09-06

COM3 / CH343 `5B91047400`, connectivity MAC `02:00:00:00:00:03`: collector app
985,984 B / `1d67d2319f30d89ce794f0b7e1b3051130163a3d7b8ce92764f8c0bcc9ab6f25`.
Run 006 stopped normally at 07:32:47 UTC, COM3 closed; new image/cache retained.
Wi-Fi-only 300-second bench profile, real QMI8658 and MAX17048, no media; no field claim.
Evidence index: `reports/board_validation/COLLECTION-20260906-006/README.md`.

## Previous bench state - 2026-09-05

**At the end of 2026-09-05: actual FW-007 restored at 10:48:12 UTC**, app 985,168 B /
`a9894a86834aa6517e5947f011b50a8af223656d74fcfb68f911ee39efa36c7d`;
all three transfer hashes verified, 30.166 s descriptor smoke, COM3 closed.
Connectivity MAC `02:00:00:00:00:03`, CH343 `5B91047400`, no SIM; wearable untouched.
Run 007 actually flashed app 992,784 B /
`99d51d25f0e0ed21dd12c20fee7f80463dd40a2540504a19a2314a34bc52bc0b`
from `tmp/convergence_live_gnss_dwell_build/`: one epoch-11 boot, four 30-second
powered dwells/no-fix states, four HTTPS attempts/matched ACKs, 16 slot writes,
confirmed off/quiescence. Source/build/run/restore identities are under
`reports/board_validation/P0-CONVERGENCE-20260905-007/`. Legacy remains 896,240 B /
`523e2d86a1c665200e18b6ad098d55be601ae27c4c31798425d9fe01a751eb05`.
Runs 005-007 total 16 verified real no-fix timeline rows; bound Guardian API
shows unavailable position and correct state identity/age. No field/product Gate.

## 2026-09-05 Runtime-Convergence Direction

[ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md) and the
[active packet](../tasks/active/P0-CONVERGENCE-20260905.md) select a separate
bounded live Location profile using existing LOC-021 A-S components and a real
authenticated, certificate-verified transport. Legacy and original offline S
remain distinct build selections. The integrator records new source/config/
image identities only after actual builds; no candidate is a flashed image.

The FW-007 hardware identity below has a 2026-09-05 readback correction;
UI-001 remains untouched. Ports must be reidentified within an authorized run.
This direction edit changes no hardware `last_verified` date, deployment or
P0 Gate. T0/T1 are scoped to their concurrent/recovery commitments and do not
block a finite single-source live profile or independent S smoke.

2026-09-05 candidate builds now actually pass on IDF 5.4.2: legacy 896,240 B,
full live 988,992 B (59,584 B / 5.7% factory space free), original S 385,856 B,
CALL 15-second owner 284,976 B. The original live artifact was subsequently
flashed once and failed initialization as recorded below; the other artifacts
remain build evidence. [Delivery/experiment report](../development/RUNTIME_CONVERGENCE_20260905.md)
records source/config/image identities and native evidence separately.
The initial FW-007 historical-hash discrepancy was resolved through one actual
readback and an operator-approved recovery amendment, detailed below. The older
recorded hash is retained as a conflicting historical claim, not silently replaced.

At 2026-09-05 06:15:54 UTC, the subsequently authorized
[run 001](../development/RUNTIME_CONVERGENCE_20260905_RUN001.md) deployed the
current Location/Guardian server bytes to `ego.example.invalid`, with exact per-file
hashes in its evidence manifest. The service now binds `127.0.0.1:8790` and
public access uses verified HTTPS; the test Guardian is bound to `ego-link-001`.
SOS public routes remain closed. At that deployment the Location timeline had zero rows; runs 005-007
subsequently verified 16 real no-fix records. Later per-socket interface-19 pinning passed verified TLS health and SSH
source/service checks at 07:07/07:13 UTC; it does not repair the earlier incomplete
stability window. PnP/SetupAPI identify CH343 COM3 despite its WMI omission.

At 07:19:45 UTC the authorized original live image (988,992 B, SHA-256
`8a0e6eff29868a1f9ba22e74026b42de3656e64ad5710c69f88342ac03601a87`)
booted on connectivity MAC `02:00:00:00:00:03`, without SIM. Wi-Fi/UTC succeeded;
outbox initialization failed before modem start. At 07:26:32 UTC restoration
completed: actual FW-007 application 985,168 B, SHA-256
`a9894a86834aa6517e5947f011b50a8af223656d74fcfb68f911ee39efa36c7d`,
descriptor `fw007-e9ca7a4`, with bootloader/partition bytes from the same verified
readback. All three writes verified; 30.17 s startup smoke observed the expected
descriptor and no captured fatal marker. COM3 is closed; NVS was not erased.

The partition correction (subsequently flashed in run 002) at `tmp/convergence_live_partition_fix_build/`
is 990,224 B, SHA-256
`97af7f2fdee31d5fb8fb9efcd6da856e9ce9c7e4f843acb3e90e99cb5a1713d1`.
Its live-only `partitions_loc021_live.csv` moves the outbox to
`0x1f4000..0x200000`, proven erased in the single preflash readback, preserving
the occupied `0x110000..0x11c000` region. Factory/NVS/PHY geometry stays the same;
legacy and original S retain their layouts. Native execution of the actual
partition/core against the saved flash reproduces corruption at the old address
without writes and succeeds at the new address in RAM only. Legacy rebuild
also passes. This is no new GNSS, delivery, recovery-endurance or product Gate.

Run 002 subsequently flashed the partition correction once on COM3. At
07:54:36 UTC both slots were valid, with two writes at `0x1f4000`; a real
StackOverflowHook then stopped progress after failed network preflight.
The actual FW-007 restore completed at 07:55:46 UTC with transfer hashes and
30.175-second descriptor smoke verified. No new GNSS/POST/ACK is established.
The stack correction (subsequently flashed in run 003) at `tmp/convergence_live_stack_fix_build/` is
990,752 B, SHA-256 `52816255ab96b99831d03129c2a49a9128949de33884f61452742c27ee3fe913`.
It selects an 8192-byte live main stack, records actual stack watermarks and
network stages, and allows one 30-second SNTP wait inside the 300-second host
boundary. The partition and normal legacy profile are unchanged. Exact run-002
results and decoded backtrace are in
`reports/board_validation/P0-CONVERGENCE-20260905-002/`.

Run 003 used the explicitly approved stack image once on COM3, without SIM.
At 08:10:35 UTC Wi-Fi/SNTP, both outbox mirrors and Q initialization passed;
minimum free main stack was 4424 bytes. Startup then returned 23, GNSS power-off
unconfirmed. No sensor/POST/ACK acceptance followed. At the 300-second host
deadline the MCU was held in ROM; the approved conditional second boot was not
used because networking had succeeded. **Run-003 recovery: actual FW-007 restored
at 08:18:11 UTC**, all three writes verified and 30.176 s descriptor smoke passed;
COM3 closed. Evidence: `reports/board_validation/P0-CONVERGENCE-20260905-003/`.

The diagnostic image (subsequently flashed in run 004) at `tmp/convergence_live_stop_fix_build/` is
991,456 B, SHA-256 `139cdbc98f57ca07405ed989b9b6dabbf7217fcceda9de4789570d4f94f8c4fd`.
It calls Q's existing bounded cooperative stop on startup failure and logs the
power-off outcome/reason before and after cleanup. It does not accept an
unconfirmed shutdown as quiesced. Legacy and live builds pass; source/config/
image identities are in `tmp/convergence_live_stop_fix_manifest.json`.
Guardian page source `9a1ab2d5ce488c880c47f0e680a890c867ee9bac19c71900e91ddfabe3147c1a`
was subsequently **deployed at 09:13:07 UTC** after network recovery. External
certificate-verified HTTPS returned its exact tested JavaScript bytes with
`Cache-Control: no-store`; source/service/health preflight passed at 09:13:47 UTC.

Run 004 captured epoch 7 on the same no-SIM COM3 node: first power-off failed
with outcome 3/reason 11 (AT_TERMINAL_ERROR); the second confirmed off. Q reported
exclusive UART ownership and `quiesced=1`; capture ended at 11.125 s / 7112 bytes.
No sensor input was requested by this diagnostic startup-failure path.
**Run-004 recovery: actual FW-007 restored at 09:15:47 UTC**, all three writes
verified, 30.182 s descriptor smoke passed, COM3 closed. Evidence root:
`reports/board_validation/P0-CONVERGENCE-20260905-004/`.

The recovery-wait image (subsequently flashed in run 005) at `tmp/convergence_live_recovery_wait_build/` is
991,872 B, SHA-256 `aabff0890cbacd1526411ec785276114a2547af607711320a88781db17d92e24`.
Live main now observes Q's existing same-owner startup recovery for at most
10 s, requires ACTIVE plus confirmed GNSS off, and otherwise stops as before.
It does not restart Q or reinterpret AT ERROR as success. Legacy/live builds
pass; run 005 subsequently verified this recovery and four real no-fix uploads.

## 2026-09-04 LOC-021Q/R/S / CALL-020R Offline Owner Checkpoint

The active offline Location candidate now extends through `LOC-021Q/R/S`.
Q supplies the exact sole, pinned boot-long modem owner and makes GNSS cleanup,
power-off recovery and owner status explicit. R connects durable SOS urgency
and deferred Cell work to that owner without creating a second modem caller.
S adds a separately selected, default-off modem-only composition: it obtains a
read-back-verified NVS boot epoch before durable storage initialization, starts
the Q owner once, and injects an offline no-I/O transport-failure result. It
does not wire external SOS/IMU ingress, a command loop or a live network path.
The Q/R/P/O selection passes `54/54`, S+Q passes `21/21`, and the combined
critical selection passes `110/110`.

Two fresh ESP-IDF v5.4.2 ESP32-S3 builds passed. The S profile at
`tmp/loc021s_profile_clean_20260904_c/` produces a `0x5DC90`-byte application
with `0xA2370` bytes (63%) free in the factory partition and application
SHA-256
`1D9466776D4A388CB4EBE4E853ECFCAD28DDB966460CA3652FB4084099815F5A`.
The final clean default profile at `tmp/loc021s_default_clean_20260904_b/`
produces a `0xDACF0`-byte application with `0x25310` bytes (15%) free and
application SHA-256
`A3D300A60E60031A441826659362B25CB956B534D1C3677795571800BE6B5807`.
Compile, map and symbol checks show the S profile selects only the S entry and
the default profile selects only the legacy entry.

The active CALL candidate now extends through `CALL-020R`. Its single pinned
owner task drives the Q responder and G media runner, treats worker termination
as an immediate cancellation trigger, and recovers incomplete join, runner
close, lease return and physical uninstall through phase-idempotent cleanup.
The post-MEDIA deadline/clock race is closed: once MEDIA has started, even an
exact deadline or invalid clock goes through cancellation and the media
finalizer rather than the pre-media abort path. R/Q focused validation passes
`33/33`.

Fresh CALL builds also passed. The default image at
`firmware/audio_loop/build_call020r_fix_default/` is `0x2FB70` bytes with 81%
of the smallest app partition free and SHA-256
`47E4574BE34AD70507193F56F753E7CD4C3DA97B4E9563EB9FCB56A2A33A519D`.
The owner-profile image at `firmware/audio_loop/build_call020r_fix_owner/` is
`0x45930` bytes with 73% free and SHA-256
`8EF932C6F5A9E794FBBAEDEB26E9B20B42D85C437DB432940709DA6A5275EA05`.

The final repository-wide `scripts/verify.ps1` run passes `1614` tests with
`12` environment-guarded skips. No image in this checkpoint was flashed or
booted, and no board, UART, USB-media, SIM, TLS, network or other external I/O
ran. All three product Gates remain `P0-LOC=NOT_RUN`, `P0-CALL=NOT_RUN` and
`P0-SOS=NOT_RUN`.

At this 2026-09-04 checkpoint, the queued next Location slice was LOC-021T0.
ADR-0014 now prioritizes bounded single-source secure runtime delivery.
LOC-021T1 concurrent product ingress still requires the persistent K checkpoint,
outbox-tombstone and no-output-replay guarantees or a reviewed proven equivalent. CALL still requires authentication, a
real verified TLS/SIM route, RESULT/post-stop telemetry, live media evidence
and measured heap/stack behavior.

## 2026-09-03 LOC-021M-P / CALL-020N-Q Offline Integration Checkpoint

The active offline mainline now includes LOC-021M/N/O/P: a fixed-capacity
priority modem arbiter, an owner-free executor and a bounded SIM7670 GNSS/LTE
adapter. They preserve a single modem owner, allow critical SOS to preempt or
retarget Location work without fabricating transport settlement, and expose
bounded report truth to the existing Location pipeline. LOC-021P passes
`13/13` focused tests, the root related selection `61/61`, and independent
review `79/79`.

A clean ESP-IDF v5.4.2 build at `tmp/loc021p_idf_clean_20260903/` produces an
application of `0xDACF0` bytes with `0x25310` bytes (15%) free in the
`0x100000` factory partition. Its application SHA-256 is
`70C2BEF5A332F3BA966C40159D926731609A5026E4647CCD469FECAFC361AAC5`.
This build was not flashed. Product composition of the sole modem owner, UART
initialization and GNSS-stop compensation remain open.

CALL-020N/O/P/P.1/Q now provides the proposed single-USB phase boundary, the
strict host CONTROL-to-MEDIA connector with bounded boot-prefix drain, and a
default-off device EGLC responder. Root's H-Q selection passes `173/173`, and
Q's focused source-contract suite passes `20/20`. The clean dedicated build at
`tmp/call020q_final3_dedicated_clean_20260903/` produces an application of
`0x44A50` bytes with `0xBB5B0` bytes (73%) free; its application SHA-256 is
`898F1D692472BAE659188433608E1B6FDCC2BB126316F7499471BE7F152D36D7`.
Q's independent final audit passes with no offline implementation blocker;
this remains source-contract/build evidence only.

The new CALL and Location paths are default-off, add no `app_main`, and ran no
real sensor, UART, USB media, SIM, TLS or network I/O. Call authentication,
real TLS/route establishment, RESULT/post-stop telemetry, the owner task and a
live run remain unconnected. The final repository-wide `scripts/verify.ps1`
run passes `1564` tests with `11` environment-guarded skips. `CALL-010`
remains `accepted_for_transition`; ADR-0013 remains `proposed`; `P0-LOC`,
`P0-CALL` and `P0-SOS` all remain `NOT_RUN`.

## 2026-09-03 LOC-021L / CALL-020M Dormant Integration Checkpoint

The active offline candidate now includes the independently audited
`location_hardware_adapter` and CALL host-control lifecycle. LOC-021L converts
only caller-captured, boot-monotonic typed reports. It conservatively rejects
ambiguous GNSS no-fix truth, partial LTE conclusions and mock/unknown IMU
provenance; its device-scoped Cell reference is a stable pseudonym, not
anonymization. Every current actuator is explicitly unsupported and no
synchronous multi-AT query runs under the shared Location/SOS owner.

CALL-020M is default-off and its command line can only render an inert plan.
The injectable execution API owns prepare/preflight/open/start/stop/close,
one-shot token clearing, stable cleanup identities, thread quiescence and
retryable local/remote ownership. The repository still supplies neither the
host-to-CALL-020G control connector nor a real verified TLS connector; their
callbacks must prove hard bounds and cancellation before enablement.

A fresh final-source ESP-IDF v5.4.2 ESP32-S3 build at
`tmp/p0_mainline_final_clean_20260903/` passes. It produces an application of
`0xDACF0` bytes with `0x25310` bytes (15%) free and a bootloader of `0x51C0`
bytes with `0x2E40` bytes (36%) free. This build was not flashed. LOC selected
regression is `244 PASS / 3 skips`, CALL is `237/237`, outbox is `76/76` and
SOS is `118 PASS / 4 skips`; the final repository-wide validation passes
`1433` tests with `10` environment-guarded skips. No real sensor, UART, SIM,
TLS, media, network or physical SOS was exercised; all three product Gates
remain `NOT_RUN`.

## 2026-09-03 G/H/J Offline Delivery Checkpoint

The active offline candidate now includes the G exact-byte SIM7670 adapter,
the H split-phase delivery runtime and the I/J SOS delivery composition. G is
bounded to an 8 KiB response and exposes cooperative cancellation, but remains
fail-closed until the exact board's TLS/UART path proves complete,
non-truncated response bytes. H separates shared-owner `prepare` and `settle`
from owner-free transport execution. A durable SOS can request cooperative
preemption of Location; cancellation retains Location for retry and preserves
CRITICAL SOS priority, while a result that wins the race remains authoritative
and non-cooperative transport acceptance may be unknown.

I/J keep the local SOS journal/enqueue, feedback, urgent-Location and Ego Call
request path outside the HTTP owner. They remain default-off and inject the
real transport, Location and Call effects. No native concurrent run, physical
button, TLS/UART exchange, Guardian notification or connected call is current
build evidence. The newer LOC-021L/CALL-020M checkpoint above advances only the
offline shadow-mapping and host-lifecycle boundaries; real modem ownership,
connectors and separately authorized live work remain. `P0-LOC`, `P0-CALL` and
`P0-SOS` all remain `NOT_RUN`.

## 2026-09-02 Mainline Offline Integration Checkpoint

The active repository candidate now has separate, dormant device components
for Location Engine v0, Sensor Policy v0, Location State emission, exact-byte
persistent outbox delivery, SOS long-press input and ordered SOS orchestration.
The `LOC-021J` single-owner runtime pipeline composes Engine, Policy, emitter
and outbox without transport or background tasks and does not commit staged
state until its required state envelope is durably enqueued.
`LOC-021K` then wraps that pipeline in a default-off single-owner lifecycle and
exposes only injected, observable GNSS/Cell/IMU/LTE/upload actuator requests;
it still has no real driver or `app_main` integration.
The server candidate has durable location ingest/ACK, hashed Guardian-to-device
authorization, a hardened minimum Guardian page, and strict durable manual-SOS
ingest/latest-alert/human-ack routes. Root verification of the combined
Message Hub/location/Guardian/SOS boundary passes `194/194`.
These components have not been composed into the currently flashed firmware,
deployed to the VPS, or exercised through reboot/reconnect/field conditions.

The persistent partition adapter is intentionally limited to field testing:
each state mutation rewrites a complete `22,240`-byte slot. Product use still
requires a journaled or wear-levelled backend with measured retention,
endurance, recovery and confidentiality behavior.

The manual-SOS server accepts `retention_seconds=86400` as event metadata but
does not yet expire timeline rows, propagate deletion to backups, verify
erasure, or encrypt the database under a product key lifecycle. Those are
explicit pre-production privacy blockers.

`SOS-010E` validates the exact persisted manual-SOS payload and deletes it only
after an accepted/duplicate ACK matches device, event, payload hash, derived
ACK ID and durable-ingest scope. `SOS-010F/G` add a default-off sampled-input
composition and a fixed 320-byte pending-edge journal so a qualified edge is
stored before sequence consumption/orchestration and can replay with its exact
identity. `SOS-010H` supplies a build-only NVS backend fixed to partition
`nvs`, namespace `ego_sos_pend`, key `edge_v1`; init is RAM-only and load is
read-only. H focused validation is `8 PASS / 1 native-host skip`, the H/G/F set
is `27 PASS / 3 native-host skips`, and a clean ESP32-S3 build passes. No NVS
callback, reboot, power loss or physical button ran, and NVS atomicity,
endurance, encryption and secure erase remain unverified.

The default-off `p0_delivery_runtime` now owns the single dispatcher drive
boundary for both `manual_sos` and `location_state`: at most one selector, one
injected bounded POST and one finish occur per ready attempt. Wrong 2xx bodies,
transport failures and uncertain durable settlement retain the record and use
explicit recovery without another POST. Focused validation is
`9 PASS / 1 native-host skip`; all outbox regressions pass `76/76`, and a clean
ESP32-S3 build passes. It still has no real HTTP implementation, credential,
task or `app_main` wiring.

CALL-020G now retains a non-autorun operator API and the complete four-worker
codec/I2S-to-USB D/E/F chain in a clean dedicated ELF. Its image is `254,592`
bytes, its global runner context is `44,216` bytes of BSS, and the linker
reports `251,057` bytes remaining in shared D/IRAM. The separate clean default
image is `195,440` bytes and contains no CALL-020 symbols. This closes the
dead-link question. The first IRAM window's one-byte report remains a future
layout-pressure warning because later executable text is already accounted in
shared D/IRAM; it is not by itself a runtime failure. This does not provide
runtime memory or media evidence. The
dedicated boot stub is intentionally inert, and four `4,096`-byte stacks plus
TCBs, USB rings, I2S DMA and codec allocations still need measured heap and
watermark evidence after a separately authorized control seam exists.

CALL-020H provides a caller-injected, bounded host serial resynchronizer for
ROM/boot prefixes and fragmented EGLM media. CALL-020I supplies strict
process-local authenticated relay admission, CALL-020J wraps a caller-injected
already-connected TLS socket after frozen external verification, and CALL-020K
adds a default-off exact-port OS serial owner with optional lazy pyserial import
but no enumeration, guessing or reconnect. `CALL-020L` now composes K/H and J
into the existing four-worker bridge behind explicit, single-use `open/start`.
L passes `15/15`; validation through L is `181/181`, and the CALL contracts
plus CALL-010 static set is `213/213`. Every serial driver/socket was a
process-local fake. The next boundary is a separately reviewed device control
trigger and real connector/TLS/PKI path, followed by a verified SIM route and
measured runtime memory/media behavior.

All three product capability Gates remain `NOT_RUN`. No current offline result
authorizes flashing, device control, SIM traffic, VPS deployment or capture.

## 2026-09-02 CALL-010 Runs And UI-001 Restoration

The wearable node completed operator-authorized, bounded CALL-010
logical-runtime runs and one staged output-only diagnostic over USB
Serial/JTAG `COM8`. The identified
target was ESP32-S3 QFN56 revision v0.2, MAC `02:00:00:00:00:01`; the 4G
connectivity node was not changed. Operator image
`firmware/audio_loop/build_operator_static/egolink_call010_audio_loop.bin`
was `278800` bytes with SHA-256
`327485660B436ABCEBE166586581C184C5164EAF7A1EC1B030EC4D20701976BB`.
Run `CALL-010-20260902-006` completed the configured `30/30/120`-second
output/input/attenuated-loop sequence with all `1500/1500`, `1500/1500` and
`6000/6000` logical frames, with phase metrics reporting `read_errors=0`,
`write_errors=0` and `frame_seq_gaps=0`, no captured fatal marker, and a final
verified PA-off state. It retained no raw audio. The two logical input
channels had low nonzero PCM metrics, which may be noise floor and do not
prove physical microphone pickup. Initialization
also emitted two error-level `i2s_channel_disable ... channel has not been
enabled yet` diagnostics; these remain unresolved even though phase-metric
read/write error counters were zero.

Follow-up run `CALL-010-20260902-007` repeated the same controlled-start
`30/30/120`-second sequence with the same operator image. The operator later
confirmed that no sound was heard during the entire run, so run 007's acoustic
output result is `FAIL` even though all logical phases and final-safe checks
passed. The operator has now confirmed speaking during the 30-second input
window; both logical-channel RMS values were approximately ten times the low
run-006 baseline and their peaks were higher. This known spoken stimulus and
correlated digital metric change strengthens input-path evidence, but does not
establish physical microphone/channel mapping, calibrated sensitivity, audio
quality or a concurrent acoustic loop. Run 007 retained no raw audio and
showed the same two unresolved initialization-time I2S disable diagnostics.

Output-only diagnostic run `CALL-010-20260902-008` then used a separate
`278960`-byte image with SHA-256
`014207FD036987A4DD3FA1EE26CFD51944FE3C5EEF04B40BEDD7A983E97F0B0A`.
After a 15-second PA-off/muted countdown, it emitted a 1 kHz, PCM-peak-5000
reference for two seconds each at volume `55`, `70`, and `85`, with two-second
muted/PA-off gaps. Each stage completed `100/100` frames and
`128000/128000` requested/actual bytes; ES8311 register readback matched
`0x99`, `0xa8`, and `0xb7`. No microphone was constructed or read, no raw
audio was retained, no fatal/deadline marker occurred, and the final PA-off
marker passed. The stage-level result is `PASS_ALL_STAGES_AND_FINAL_SAFE`, but
the strict runner result is `FAIL_OR_INCOMPLETE` solely because one upstream
initialization-time `i2s_channel_disable ... channel has not been enabled yet`
error-level line was captured. The operator subsequently confirmed that the
bounded high-volume sequence sounded clear and normal overall, with no painful
or distorted result reported; the three stages were not individually
identified. Run 008 therefore passes the bounded qualitative
speaker-output acoustic check; this does not waive the strict runner diagnostic
or constitute an SPL or product-acoustics measurement.

After run 008, an offline output-diagnostic-only change pre-arms TX while PA
is forced low before codec open, removing the known first-open blind-disable
cause without enabling RX. Focused tests passed `8/8`, and ESP-IDF `v5.4.2`
built a new `279280`-byte image with SHA-256
`B79C6E0B5B5EF76165DF5FA2DF3DDE82786E7C8EC20D5B4C5D97E8427FF3DAC8`.
This image has **not** been flashed or run, does not alter run 008's strict
result, and has no hardware evidence. No further hardware run is authorized.

Post-run source review also shows that this was an exceptionally weak audible
stimulus rather than a decisive speaker-health test. Volume `12` produced the
verified ES8311 value `0x6e`, approximately `-40.5 dB`, while the generated
chirp peak was only `1800/32767` (approximately `-25.2 dBFS`). Their nominal
combined level was about `-65.7 dB` below the corresponding full-scale codec
path before the external amplifier; local-loop playback was attenuated by a
further factor of `16` (approximately `-24.1 dB`). For comparison, the
official Arduino `08_ES8311` example selects volume `85`. The operator
confirmed the unit is in a complete enclosure, and external photos show
visible acoustic openings. The product assembly is documented with an internal
speaker, but the V1.0 main-board schematic ends the NS4150B output at `P5/P6`
contacts marked `SPK`; the photos do not verify the internal speaker assembly
or `P5/P6` contact.

Logical runtime is complete for the earlier bounded sequences, and run 008's
staged output is now operator-confirmed clear and normal. This resolves the
active speaker-output audibility debug branch for the development board. It
does not establish physical microphone/channel mapping, calibrated SPL,
AEC/AGC, acoustic echo, DMA underrun/overrun behavior, application-level
concurrent RX/TX, or a measured local-loop delay. Physical PCB revision remains
unknown, and run 008 retains its initialization diagnostic even though an
unflashed offline candidate addresses its identified cause. Together with run
007's spoken-stimulus/input-metric response, the basic development-board audio
endpoints leave CALL-010 `accepted_for_transition`; CALL-020 and the broader
CALL lane are paused under the 2026-09-09 scope decision. Simultaneous I/O and
measurable local-loop delay remain unresolved, non-transition-blocking closure
work. `P0-CALL` and all other P0 capability Gates remain `NOT_RUN`.
Detailed evidence is under
`reports/board_validation/CALL-010-20260902-006/` and
`reports/board_validation/CALL-010-20260902-007/`, with the staged output and
latest restore evidence under
`reports/board_validation/CALL-010-20260902-008/`.

The temporary CALL-010 override has been reversed. UI-001 is again the
current wearable image. Its application is `659120` bytes with SHA-256
`11D72868A956E86F7B91D1B9D6008404FBD02B61299D566399DDC90F50A23139`;
the `22208`-byte bootloader and `3072`-byte partition table have SHA-256
`2248730A914CA30FDEC279FE065EB3CB7F1E3C5CBB3F49BE33E6F1C358A9AD63`
and `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`.
All three flash writes passed hash verification. The run-006 15-second reboot
capture observed UI-001 `hello` and `display_ready`; UI-001 was restored again
after runs 007 and 008. The latest run-008 bounded boot observed `hello` and
`display_ready`, and smoke `UI001-RESTORE-20260902-008` passed
`status_rendered` and `ask_user_rendered`. The latest restoration evidence is
under `reports/board_validation/CALL-010-20260902-008/restore_ui001_*` and
`reports/board_validation/CALL-010-20260902-008/ui001_smoke/`.

## 2026-09-02 Offline P0 Integration Candidates (Not Deployed)

The current working tree advances the three P0 lanes as independent offline
host slices while retaining the physical and network evidence boundaries:

- LOC-021 A/B/C now includes a standard-library Location State runtime, a
  SQLite append-only timeline plus derived current-state store, authenticated
  bounded Message Hub HTTP ingest and a default-redacted current-location
  response. Root
  verification passes `41/41` LOC-focused tests. The existing Message Hub
  suite is agent-reported `61/61` pending a root rerun. No device emission,
  device outbox wiring, real Guardian-device binding, VPS deployment or field
  run is part of this result.
- CALL-020A's bounded in-memory media runtime passes `11/11` focused tests;
  CALL-020B's framed I/O/preflight and deterministic fake duplex pump passes
  `21/21`; the combined CALL-focused offline suite passes `65/65`. There is no
  real concurrent 20 ms pump, continuous wearable USB CDC media path, matching
  TLS relay, verified LTE route or real media run yet. Current RNDIS evidence
  is enumeration only; the historical source-bound ping/curl through
  `192.168.0.100` timed out.
- SOS-010A's isolated host composition passes `8/8` focused tests. It does not
  connect the location upload adapter, prove Guardian human delivery, establish
  a remote call or exercise a physical button.

These candidates are deliberately parallel: the next LOC slice is device
emission plus persistent-outbox wiring; the next CALL slice is continuous USB
media plus a genuinely concurrent bridge and matching relay; and the next SOS
slice is the server/device adapter boundary. No candidate was flashed,
deployed, sent over the SIM, or run on hardware. Those actions require fresh
explicit operator authorization. `P0-LOC`, `P0-CALL` and `P0-SOS` all remain
`NOT_RUN`.

## 2026-08-23 Validated Working-Tree Candidates (Not Flashed)

This section is the preserved 2026-08-23 baseline. Its CALL-010 "not
flashed" statement is superseded by the 2026-09-02 section above.

The working tree contains distinct, deliberately non-promoted candidates:

- the main connectivity source candidate restores the public bounded IMU
  command to exact 100 x 50 ms, preserves boot/time lineage for raw LTE
  location derivation, and fixes Dashboard history selection; it has not been
  rebuilt with ESP-IDF in this Sprint 1 integration run;
- the isolated CALL-010 target has two successful ESP-IDF 5.4.2 builds: dormant
  `195280` bytes (SHA-256 `22A28843...C01086`) and operator-test `277408` bytes
  (`16A8936E...3D758F`); neither image was flashed or run; and
- PC references now cover Location Engine/Sensor Policy/Replay, the additive
  Location State Envelope and server mirror seam, persistent priority outbox,
  Ego Call control/media-trace preparation, and static audio safety.

The merged repository suite passes `929/929`; the P0-focused integration set
passes `132/132`; `context_lint` and `git diff --check` pass. These results do
not replace the `current board` entries below and are not evidence for IMU
continuous capture, GNSS fix/accuracy, RTC media, device audio, TLS modem
transport, battery, or product behavior. At this 2026-08-23 checkpoint the
connectivity node still ran FW-007; the 2026-09-06 current-image section above
supersedes that historical mirror. All three P0 capability Gates remain
`NOT_RUN`.

## Host

- Workspace: `D:\pywork\egolink`
- Primary shell: Windows PowerShell
- ESP-IDF used in recent builds: `C:\Espressif\v5.4.2\esp-idf`

## Connected Development Boards

| role | current board | observed ports | current use |
|---|---|---|---|
| `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | Espressif USB Serial/JTAG `COM8` observed 2026-09-02; MAC `02:00:00:00:00:01` | UI-001 field-friendly D1 status sidecar is currently flashed after the bounded CALL-010 override was reversed. The `659120`-byte application has SHA-256 `11D72868...A23139`; the latest run-008 bounded restore observed `hello`, `display_ready`, `status_rendered` and `ask_user_rendered`. It retains the cJSON serial downlink parser, `display_status` full-screen `D1 FIELD` page with `LINK`/`LOC`/`PWR`/`POST` rows, non-disruptive `status_update`, payload-driven `ask_user` prompt and QMI8658 engineering sampler. |
| `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | CH343 ESP32 console `COM3`; historical direct-to-host SIM7670G ports `COM4`/`COM5`/`COM6`/`COM7` observed 2026-08-16 | Latest executed app is run017 `0.1.0-camera-lte-trial-017`, application SHA-256 `07CF1EF3...F0223529`. Its empty-spool, 600-second USB-powered/serial-observed SIM7670G PPP regression delivered 248/248 ordinary uploads with HTTP 200, local match and local ACK; after pre-PPP buildup the queue drained and final health reported zero. This closes only the immediate ten-minute bench throughput blocker. Run015 separately passed one real-LTE manual Camera -> VPS -> private-API integrity slice. Timer/outage/restart, browser preview, route transition, independent power, endurance and field use remain unverified. FW-007 remains the recorded rollback fallback. |

Port numbers are observations, not stable configuration. Tooling must identify devices by USB identity and/or versioned `hello`.

## Recently Verified Capabilities

- CALL-010 runs `CALL-010-20260902-006` and `-007` completed controlled-start
  `30/30/120`-second logical output/input/attenuated-loop sequences on the
  wearable board. Run 006 established a low logical-channel baseline; during
  the run-007 input window, the operator confirms speaking, input RMS rose
  approximately tenfold and peaks increased. This is correlated input-path
  evidence, but does not establish physical microphone/channel mapping,
  calibrated sensitivity, audio quality or a concurrent acoustic loop. Run 007
  passed its logical/final-safe checks but failed acoustic output because the operator
  heard no sound throughout. Two initialization-time I2S disable diagnostics
  also remain unresolved. Concurrent RX/TX queues, DMA underrun/overrun and
  acoustic delay remain unverified. Output-only run `-008` completed all
  volume `55/70/85` stage writes, matching register readbacks and final PA-off
  checks without constructing or reading a microphone. Its stage-level result
  is `PASS_ALL_STAGES_AND_FINAL_SAFE`, while its strict result remains
  `FAIL_OR_INCOMPLETE` solely because one upstream initialization I2S-disable
  diagnostic was captured. The operator confirmed the overall output sequence
  sounded clear and normal, giving this bounded speaker-output
  slice an acoustic PASS; individual stages were not separately identified.
  The basic endpoints unlock CALL-020, but full-duplex/acoustic-loop and LTE/RTC
  acceptance remain unverified, so this does not advance `P0-CALL`.
- Full Demo v0.5 runner can produce one complete summary from real AMOLED IMU/touch evidence, SIM7670G GNSS AT evidence, mock-only structured audio evidence, session recording, quality gate, and replay.
- Same-run AMOLED IMU/touch confirmation evidence has been captured: `motion_event`, `ask_user_rendered`, `user_confirmation=safe`, and final PC `safety_event`.
- AMOLED-001 sidecar display smoke has been captured on `COM9`: `status_update`
  rendered a D1 status page and a payload-driven `ask_user` rendered the safety
  prompt; this did not re-test physical tap confirmation.
- AMOLED-002 sidecar runner can mirror current VPS `/api/state` D1 status to
  the AMOLED screen over `COM9`; smoke `amoled002-d1-status-vps-smoke2-20260704`
  rendered `estimate_visible`, LTE registered/PDP active, no-fix map mode,
  battery, and raw POST counters without sending 4G-board commands.
- AMOLED-003 field companion runner can start the D1 field observer and AMOLED
  sidecar together with one run ID; smoke
  `amoled003-companion-vps-smoke5-20260704` passed on `COM9` with one observer
  sample and one AMOLED `status_rendered` event.
- AMOLED-004 visible sidecar fix is flashed on `COM9`: `display_status` now
  forces the full-screen D1 status page and passed companion smoke
  `amoled004-companion-visible-vps-smoke-20260704`.
- UI-001 field-friendly AMOLED screen is flashed on `COM9`: `display_status`
  renders `D1 FIELD` with `LINK`, `LOC`, `PWR`, and `POST` rows and passed
  smoke `ui001-amoled-friendly-smoke-20260704`.
- MODEL-DEVICE-006 Tiny Safety D1 firmware historically passed the bounded
  hardware short loop on the 4G connectivity node: serial
  `safety tiny status/selftest/demo ...` validation on `COM4`, reset-log LTE
  HTTP POST observation, and a read-only D1 Web/API observer pass with fresh
  `MODEL-DEVICE-006-hw-20260707-d1` uploads. D2-006 replaced that image on
  2026-08-10, D2-007 subsequently replaced D2-006, D2-008 replaced D2-007,
  D2-009 replaced D2-008, D5-002 replaced D2-009, and FIELD-011 replaced
  D5-002 with the joint LTE/GNSS/QMI8658 field-seed image on 2026-08-11;
  FW-006 replaced FIELD-011 on 2026-08-12, and FW-007 replaced FW-006 on
  2026-08-15.
- AMOLED `ask_user` command path rendered and returned `user_confirmation=safe` in Demo v0.2 evidence.
- Demo v0.3 generated a complete safety record using Demo v0.2 real AMOLED confirmation evidence plus live SIM7670G GNSS AT probe.
- SIM7670G GNSS AT probe was reachable indoors, selected `COM6`, and produced `fix=false`.
- QMI8658 live data has been captured from the AMOLED board in an engineering fixture context.
- D2-006 captured the external ATK-NB018 V1.0 QMI8658A candidate directly on
  the 4G connectivity node: address `0x6A`, `WHO_AM_I=0x05`, reset result
  `0x80`, and 100/100 real non-mock six-axis samples. The 100-sample window
  used 70 ms observed intervals despite a configured 50 ms delay; mounting,
  calibration, accuracy, shared-bus operation, and LTE upload remain
  unverified. Evidence:
  `reports/board_validation/20260810-qmi8658-probe/qmi8658_probe_report.md`.
- D2-007 flashed the bounded QMI8658/LTE image once and passed its 20-second
  startup identity and idle-stop safety gates. Its only capture command was not
  executed because the SIM7670 path stayed `LTE_SIM_NOT_READY` through the
  120-second readiness gate. The bounded observation produced zero raw frames,
  zero messages, no ACK, and an empty explicit export; this is a safe failed
  run, not an LTE IMU-window capability. Evidence:
  `reports/board_validation/20260810-d2007-imu-lte/d2_007_hardware_report.md`.
- D2-008 reused the existing Wi-Fi JSON telemetry path with no source/server/
  protocol changes. Test run `D2-008-WIFI-IMU-20260811-001` retained 26/26
  real non-mock QMI8658 `sensor_sample` messages and 26 distinct six-axis
  tuples; serial also observed QMI identity, Wi-Fi connection, registration,
  and successful telemetry POSTs. The app was then stopped in ROM download
  mode. This passes a low-rate data-path smoke only, not the 100 x 50 ms window
  or dataset gate. Evidence:
  `reports/board_validation/20260811-d2008-wifi-imu/d2_008_wifi_imu_report.md`.
- D2-009 reused the D2-007 bounded capture contract over the already-proven
  Wi-Fi path. Test run `D2-009-HW-20260811-001` completed command
  `wifi-imu-001` with 100/100 real samples, ten chunks, one manifest, zero read
  failures/mock substitutions/deadline misses, and observed intervals
  49749/49999/50292 us minimum/mean/maximum. The explicit export returned one
  valid cadence-qualified window, zero invalid windows, and
  `training_allowed=false`. Evidence:
  `reports/board_validation/20260811-d2009-wifi-imu-window/d2_009_wifi_imu_window_report.md`.
- D5-002 extended the dedicated Wi-Fi profile to stop after three successful
  commands in one boot while retaining the D2-009 one-command default. Test
  run `D5-002-SEED-20260811-001` completed `d5002-s1` through `d5002-s3` in
  47 seconds with 300/300 real QMI8658 samples, 30 chunks, three manifests,
  three `ok` ACKs, zero read/mock/deadline failures, and mean cadence exactly
  50,000 us in every window. One read-only export returned three valid
  cadence-qualified windows, zero invalid windows, and
  `training_allowed=false`. Evidence:
  `reports/board_validation/20260811-d5002-imu-seed/d5_002_hardware_report.md`.
  The operator subsequently confirmed that the board stayed flat and
  stationary on the table throughout all three windows. A one-session
  labelled seed now binds the three windows and 300 samples through explicit
  sidecar hashes; it remains split `unassigned`, `training_allowed=false`,
  and `training_ready=false`.
- FIELD-011 flashed the clean joint LTE/GNSS/QMI8658 image once on 2026-08-11.
  The 20-second startup gate observed `WHO_AM_I=0x05`, revision `0x7c`, reset
  result `0x80`, real hardware present, and confirmed idle measurement stop.
  The first LTE readiness attempt failed with `SIM not inserted`; after the
  operator's full power cycle, the already-pending command `f011-bench-1`
  completed without another flash or command creation. The explicit exporter
  scanned 13 matching retained frames and reconstructed ten QMI8658 chunks plus
  one manifest; the command has one matching LTE `ok` ACK. The window contains
  100 real samples after ten
  warm-ups, with zero read/mock/deadline failures and observed cadence
  49,985/49,999/50,000 us minimum/mean/maximum. One explicit export returned
  one valid cadence-qualified window and zero invalid windows with
  `training_allowed=false`. Periodic location then reported `LTE_READY`, home
  registration, active PDP, assigned IP, RAT `LTE`, and indoor GNSS
  `fix=false` / `no_fix`. The operator subsequently confirmed that the board
  remained stationary throughout the complete window, so its activity label
  is operator-confirmed `stationary`; pose/orientation remains unrecorded.
  Evidence:
  `reports/field_validation/FIELD-011-20260811-001/field011_bench_report.md`.
- FW-006 replaced FIELD-011 once on 2026-08-12 with the clean
  GNSS-correctness image. All three normal flash regions were hash-verified
  without an NVS write. Its sole 20-second USB-attached startup capture
  observed the expected app identity, QMI8658 identity, one real `mock=false`
  sample, confirmed idle stop, SIM7670 UART readiness, `LTE_READY`, and
  successful periodic location/observation posts, with no fatal or reset-loop
  marker. It did not observe a real GNSS fix/fixed-coordinate response, so the
  corrected coordinate parser is not yet hardware-verified. Evidence:
  `reports/firmware_validation/FW-006-20260812-001/`.
- FW-007 replaced FW-006 once on 2026-08-15 with the opt-in combined
  LTE-to-Wi-Fi failover image `0.1.0-fw007-lte-wifi-failover`
  (`fw007-e9ca7a4`; app SHA-256
  `8F3508C62CA96C54628B3C3FB0A64B5BB14EAF7BBB8188DA54FAEE0739283799`).
  The COM3 three-region flash was hash-verified without targeting or erasing
  the NVS partition; normal boot diagnostics retained/updated `boot_count`. The
  SIM-absent startup reached the configured LTE readiness counter of 120 at
  about 286 seconds device uptime, changed once from `lte_primary` through
  `wifi_connecting` to `wifi_active`, connected Wi-Fi in about 4.5 seconds,
  and registered with Message Hub HTTP 200. VPS evidence then retained fresh
  Wi-Fi failover heartbeats/location reports and a Wi-Fi `request_location`
  ACK; bounded post-takeover windows contained no LTE command-poll round,
  offline transition, panic, brownout, or reset marker.
- On 2026-08-16 the same image, without another flash, first established stable
  LTE and then underwent an operator-confirmed physical SIM removal. USB AT
  confirmed the SIM was absent. COM3 retained threshold count three and the
  one-way `lte_primary -> wifi_connecting -> wifi_active` transition with
  reason `lte_http_poll_failures`; counts one and two occurred before serial
  reacquisition and were not individually retained. The VPS received its last
  LTE message at 13:40:03.490 CST and first `wifi_failover` message at
  13:40:51.837, in the same boot with forward sequence continuity. About 206
  seconds of VPS observation retained 12 heartbeats, six sensor samples, and
  four location reports with no LTE-linked message, device error, or service
  restart. No command was created, so this second run did not re-test ACK.
  Automatic failback, durable offline queueing, LTE recovery, USB-free
  endurance, and long-run reliability remain unverified or outside these
  bounded runs. Evidence:
  `docs/tasks/active/FW-007_LTE_WIFI_FAILOVER.md` and
  `firmware/mqtt_heartbeat/build_fw007_hw_20260815/`.
- Camera smoke capture on the SIM7670G board has produced bounded JPEG evidence.
- R1 connectivity-node firmware `0.1.0-fw001-hw-r1` has passed USB-Free
  Message Hub validation on independent power with USB disconnected:
  test run `fw001-hw-r1-20260627-133813`, heartbeat `seq=7`, command ACK
  `seq=8`, evidence under
  `reports/field_validation/fw001-hw-r1-20260627-133813/`.
- FW-002A connectivity-node firmware `0.1.0-fw002-location-scaffold` has passed
  USB-Free request-location scaffold validation on independent power with USB
  disconnected: test run `fw002-location-build-smoke`, heartbeat `seq=3`,
  `request_location` command `cmd-000004`, `location_report seq=4`
  (`fix=false`, `gnss_state=driver_not_integrated`,
  `source_status=unverified`), ACK `seq=5`, evidence under
  `reports/field_validation/fw002-location-build-smoke/`.
- FW-002B fix1 connectivity-node firmware
  `0.1.0-fw002b-sim7670-gnss-fix1` has passed USB-Free SIM7670G
  firmware GNSS AT validation on independent power with USB disconnected:
  test run `fw002b-fix1-gnss-r1-20260627-163246`, heartbeat `seq=57`,
  `request_location` command `cmd-000006`, `location_report seq=58`
  (`source=sim7670g_firmware_gnss`, `gnss_source=sim7670g_uart_at`,
  `gnss_driver=uart_at`, `gnss_query_ok=true`, `fix=false`,
  `gnss_state=no_fix`), ACK `seq=59`, evidence under
  `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/`.
- The R3 preflight stability observer exists and first detected a FW-002B fix1
  reset/sequence regression under USB-Free operation:
  `reports/field_validation/stability-fw002b-fix1-20260627-170758/`.
- FW-002C reset-diagnostics firmware was flashed and runtime-observed on the
  connectivity node. Fix1 (`0.1.0-fw002c-resetdiag-fix1`) reproduced repeated
  `panic` resets during a 120-second USB-Free observation:
  `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/`.
  Fix2 (`0.1.0-fw002c-resetdiag-fix2`) moved the heartbeat status payload off
  the task stack, increased heartbeat stack margin, and passed a 120-second
  USB-Free VPS stability observation with 15 messages, `seq_regressions=0`,
  max message gap 11.547434 seconds, and final last-seen age 6.563391 seconds:
  `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/`.
- FW-002C resetdiag fix2 was also used for a window-side real-fix attempt over
  the USB-Free Message Hub path. The device received `request_location`
  command `cmd-000008`, returned `location_report seq=601`, and ACKed with
  `seq=602`, but the GNSS result remained `fix=false`, `gnss_state=no_fix`,
  no satellites/HDOP/coordinates, and raw response `+CGPSINFO: ,,,,,,,, OK`.
  Evidence is under
  `reports/field_validation/fw002c-fix2-window-gnss-retry1-20260627-195000/`.
- A later window-side attempt with the same FW-002C resetdiag fix2 image
  produced the first firmware-side SIM7670G `fix=true` report over the
  USB-Free VPS path: command `cmd-000010`, `location_report seq=6920`, ACK
  `seq=6921`, and latitude/longitude fields present. The run is still an
  acceptance FAIL because fix2 labels fixed coordinates as
  `source_status=unverified`; the gate requires `observed` or `verified`.
  Evidence is under
  `reports/field_validation/fw002c-fix2-window-gnss-fix-unverified-20260628-092703/`.
- FW-002C resetdiag fix3 has been build-verified as
  `0.1.0-fw002c-resetdiag-fix3` / `fw002c-resetdiag-fix3-20260628-093000`.
  It changes parsed SIM7670G fixed coordinates to `source_status=observed`.
  The image was flashed on `COM4` and USB-Free validated after the operator
  connected independent power and disconnected USB. The first request saw
  `gnss_state=at_unreachable` while AT was not ready; a retry after one minute
  passed with command `cmd-000012`, `location_report seq=31`, ACK `seq=33`,
  `fix=true`, `gnss_state=fix`, `source_status=observed`, and latitude/
  longitude fields present. Evidence is under
  `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/`.
- LTE-001B status observability firmware has been build/flashed as
  `0.1.0-lte001b-observe` / `lte001b-observe-20260628-130400`. The image was
  built with SIM7670G GNSS and LTE-status observability enabled, flashed on
  `COM4`, and hard-reset successfully. The binary is
  `firmware/mqtt_heartbeat/build_lte001b_observe/egolink_mqtt_heartbeat.bin`.
  USB-Free runtime validation attempt 1 failed because the VPS saw new firmware
  registration but no fresh LTE-001B status heartbeat; evidence is under
  `reports/field_validation/lte001b-observe-20260628-130400/`.
- LTE-001B fix1 has been build-verified as
  `0.1.0-lte001b-observe-fix1` / `lte001b-observe-fix1-20260628-131739`.
  It moves LTE observation fragments out of heartbeat/sensor task stack and
  raises both task stacks to 12288 bytes. The binary is
  `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`, hard-reset successfully, and passed
  USB-Free LTE status observability validation through the VPS Message Hub:
  `reason_code=LTE_READY`, `registration_state=registered_home`,
  `pdp_state=active`, assigned IP present, RAT `LTE`, cell ID `180571649`, RSSI
  `-90`, RSRP `-97`, RSRQ `-7`, SINR `28`. Evidence is under
  `reports/field_validation/lte001b-observe-fix1-20260628-131739/`.
- LTE-002 LTE HTTP probe firmware has been build-verified as
  `0.1.0-lte002-lte-http-probe` /
  `lte002-lte-http-probe-20260628-141656`. The image enables SIM7670G GNSS,
  LTE status, and LTE HTTP probe mode, skips Wi-Fi runtime tasks in that mode,
  and builds to
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe/egolink_mqtt_heartbeat.bin`.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/flash_report.md`.
  USB-Free LTE HTTP runtime validation attempt 1 failed as recorded below.
- LTE-002 validation attempt 1 failed after the operator connected independent
  power and disconnected USB. `scripts/validate_lte_http_probe.py` observed no
  fresh `lte_http_probe` telemetry through the VPS Message Hub between
  `2026-06-28T06:30:38Z` and `2026-06-28T06:34:41Z`; `/api/state` remained on
  the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/`.
- LTE-002 fix1 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix1` /
  `lte002-lte-http-probe-fix1-20260628-143631`. It waits up to 120 seconds for
  SIM7670G LTE status to report `LTE_READY` before attempting AT HTTP POST.
  The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/flash_report.md`.
  USB-Free runtime validation attempt 2 failed as recorded below.
- LTE-002 fix1 validation attempt 2 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T08:12:31Z` and `2026-06-28T08:16:34Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/`.
- LTE-002 fix2 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix2` /
  `lte002-lte-http-probe-fix2-20260628-161844`. It keeps Wi-Fi disabled for the
  LTE HTTP probe path and changes the probe from one round to a bounded retry:
  up to `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_MAX_ATTEMPTS=6`, waiting
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC=20` seconds
  between failed rounds. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix2/egolink_mqtt_heartbeat.bin`.
  The fix2 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/flash_report.md`.
  USB-Free runtime validation attempt 3 failed as recorded below.
- LTE-002 fix2 validation attempt 3 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T08:55:08Z` and `2026-06-28T09:02:11Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/`.
- LTE-002 fix3 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix3` /
  `lte002-lte-http-probe-fix3-20260628-170508`. It keeps Wi-Fi disabled and
  keeps the fix2 bounded retry behavior, but skips `AT+HTTPPARA="CID",1` by
  default through `CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM=n`, matching
  the A7600/A7670-style SIMCom HTTP flow more closely. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix3/egolink_mqtt_heartbeat.bin`.
  The fix3 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/flash_report.md`.
  USB-Free runtime validation attempt 4 failed as recorded below.
- LTE-002 fix3 validation attempt 4 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T09:51:18Z` and `2026-06-28T09:58:22Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/`.
- USB-attached LTE HTTP AT diagnosis then proved that the SIM7670G module and
  VPS path are capable of HTTP over LTE for compact payloads: `/health` GET
  returned HTTP 200, and a bearer-auth telemetry POST with a compact 211-byte
  payload returned HTTP 200. The same diagnostic reproduced `+HTTPACTION:
  1,706,0` once authenticated POST bodies reached 2237 and 3230 bytes, while a
  1232-byte POST still passed. Evidence is under
  `reports/field_validation/lte002-atdiag-http-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-pad1000-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-pad2000-com7-20260628/`,
  and `reports/field_validation/lte002-atdiag-authpost-large-20260628/`.
- LTE-002 fix4 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix4` /
  `lte002-lte-http-probe-fix4-20260628-184644`. It compacts the
  `lte_http_probe` payload to stay near the PC-side passing payload range while
  preserving `transport.type=lte`, HTTP status/reason, and LTE/cell readiness
  context. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix4/egolink_mqtt_heartbeat.bin`.
  The fix4 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/flash_report.md`.
  USB-Free runtime validation failed with no fresh `lte_http_probe` telemetry
  reaching the VPS Message Hub; evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/`.

## Current Known Limits

- The prior FIELD-011 image passed its inserted-SIM joint bench gate only
  after a full power cycle cleared the initial `SIM not inserted` condition.
  The single authorized command is complete, not pending. One real QMI8658
  window reached the VPS over LTE and reconstructed cleanly, while periodic
  LTE location reached the VPS with an explainable indoor no-fix result. This
  does not yet prove outdoor GNSS fix, USB-free independent-power operation,
  fixed carry orientation, walking windows, reconnect behavior, or long-run
  stability.
- D5-002 proves three independent bounded 100 x 50 ms real six-axis windows
  can reach the VPS over Wi-Fi in one boot and be reconstructed as
  cadence-qualified engineering evidence with one operator-confirmed
  flat-on-table stationary label session. It does not prove fixed axis
  mapping, calibration, other activities or poses, training suitability,
  continuous operation, or product accuracy. FIELD-011 separately proves one
  operator-confirmed stationary LTE window, but its pose/orientation remains
  unrecorded. The D5-002 labelled seed is explicitly training-blocked, and its
  dedicated command task exits after three successes. FIELD-011 likewise uses
  bounded command captures; neither run proves continuous sampling or
  uploading.
- The historical D2-007 combined image identified and stopped the external
  QMI8658A at startup, but that run did not reach capture because LTE was not
  ready. FIELD-011 now supersedes that negative integration result with one
  successful 100 x 50 ms LTE window; it does not retroactively make D2-007 a
  passing run.
- GNSS indoor no-fix is expected and is not a P0 failure by itself.
- SIM7670G GNSS refresh has PC-side USB AT no-fix evidence and FW-002B
  firmware-side UART/AT no-fix evidence through the USB-Free Message Hub loop.
  FW-002C fix3 later observed a real firmware-side SIM7670G GNSS fix, but final
  enclosure/mounting GNSS acceptance remains unverified.
- The early USB-Free R1 validation used Wi-Fi HTTP to the Message Hub; it did
  not prove SIM7670G LTE transport, GNSS fix, battery/charging accuracy, or
  product power behavior. LTE-002 fix5 later proved one SIM7670G LTE HTTP
  telemetry uplink thin-slice only.
- Earlier LTE-002 fix5
  `0.1.0-lte002-lte-http-probe-fix5` proved one LTE HTTP uplink thin-slice.
  The first LTE-002 image and fix1 failed
  USB-Free LTE HTTP validation with no fresh LTE HTTP telemetry reaching the
  VPS; fix2 also failed with no fresh LTE HTTP telemetry reaching the VPS.
  Fix3 also failed with no fresh LTE HTTP telemetry reaching the VPS. The prior
  LTE-001B fix1 image passed USB-Free LTE status observation. USB-attached AT
  diagnosis indicates compact LTE HTTP payloads can reach the VPS, while larger
  POST bodies trigger SIM7670G `HTTPACTION` 706. Fix4 was flashed but failed USB-Free
  validation with zero test-run messages. USB-attached firmware console
  diagnosis then observed repeated `main` task stack overflows before any LTE
  readiness or HTTP AT command log appeared:
  `reports/field_validation/lte002-fix4-console-diag-20260628/`.
- LTE-002 fix5 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix5` /
  `lte002-lte-http-probe-fix5-20260628-193815`. It moves LTE HTTP probe
  execution out of the ESP-IDF `main` task and into a dedicated
  `lte_http_probe_task` with `LTE_HTTP_PROBE_TASK_STACK_SIZE=12288`. The
  binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix5/egolink_mqtt_heartbeat.bin`.
  The fix5 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/flash_report.md`.
  USB-Free runtime validation passed after the operator disconnected USB and
  power-cycled the independent-power board: result `lte_http_probe` had
  `transport.type=lte`, `lte_http.reason_code=LTE_HTTP_OK`, HTTP status `200`,
  action elapsed `1570 ms`, LTE `reason_code=LTE_READY`, assigned IP
  `10.160.15.113`, and cell ID `180571649`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/`.
- LTE-003 command-loop firmware has been build-verified as
  `0.1.0-lte003-command-loop` /
  `lte003-command-loop-20260628-210214`. It enables
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`, skips Wi-Fi as the
  runtime data path for that image, polls the existing Message Hub command
  queue through SIM7670G AT HTTP GET, and ACKs one harmless
  `set_report_interval` command through SIM7670G AT HTTP POST with
  `transport.type=lte` evidence on the ACK. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop/egolink_mqtt_heartbeat.bin`.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-20260628-210214/flash_report.md`.
  USB-Free runtime validation attempts 1 and 2 failed: `cmd-000013`
  (`set_report_interval`) remained pending, no ACK was received, the test-run
  export contained zero messages, and VPS state still showed the prior LTE-002
  fix5 telemetry as latest. Attempt 2 reused the pending command after an
  independent-power cold reboot with USB still disconnected. Runtime evidence
  is under `reports/field_validation/lte003-command-loop-20260628-210214/`,
  including `lte_command_loop_report_attempt2_existing_cmd.json`.
- LTE-003 fix1 has been build-verified as
  `0.1.0-lte003-command-loop-fix1` /
  `lte003-command-loop-fix1-20260628-223454`. It adds
  `lte_http_command_diag` telemetry over SIM7670G LTE HTTP POST around command
  polling and increases `lte_http_command_task` stack to `16384`. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/flash_report.md`.
  Runtime validation failed with `cmd-000013` still pending and no ACK. The
  test-run export contained 37 earlier `lte_http_command_diag` messages: fix1
  reached LTE readiness and posted diagnostics, but command poll ended with
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`, HTTP status `200`, and
  `poll_data_len=592`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/`.
- LTE-003 fix2 has been build-verified as
  `0.1.0-lte003-command-loop-fix2` /
  `lte003-command-loop-fix2-20260629-074709`. It increases the SIM7670 AT
  response buffer from `512` to `1536` bytes so command-poll `HTTPREAD` can
  hold the observed response body plus SIMCom framing. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix2/egolink_mqtt_heartbeat.bin`.
  It was rebuilt after commit so the build app version is `43f5f55`. The fix2
  image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition
  table were written, hashes verified, and hard reset completed. Flash evidence
  is under
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/flash_report.md`.
  USB-Free runtime validation failed after the operator cold-booted the board
  on independent power with USB disconnected. The validator reused
  `cmd-000013` from `2026-06-28T23:58:07Z` to `2026-06-29T00:04:07Z`; the
  command remained pending and no ACK was received. The test-run export
  contained 51 LTE diagnostic messages, with the latest reporting HTTP poll
  status `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/`.
- LTE-003 fix3 has been build-verified as
  `0.1.0-lte003-command-loop-fix3` /
  `lte003-command-loop-fix3-20260629-081529`. It keeps LTE-003 acceptance
  unchanged, but makes command-poll `AT+HTTPREAD` use the longer LTE HTTP
  action timeout and splits the prior `LTE_HTTP_READ_FAILED` condition into
  `LTE_HTTP_READ_AT_FAILED` and `LTE_HTTP_READ_BODY_PARSE_FAILED`. The fix3
  code-change commit is `e79e4de`; the flashed build app version is `79a12c8`
  because the guarded flash re-ran CMake at the documentation commit. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin`,
  and its size is `291488` bytes. Focused tests, `context_lint`,
  `verify.ps1`, `git diff --check`, and the guarded prepare/build passed.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T00:26:51Z` to
  `2026-06-29T00:32:53Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 59 LTE
  diagnostic messages, with the latest reporting HTTP poll status `200`,
  `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_AT_FAILED`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/`.
- LTE-003 fix4 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix4` /
  `lte003-command-loop-fix4-20260629-084350`. It tries positional
  `AT+HTTPREAD=0,<data_len>` before falling back to bare `AT+HTTPREAD`, and
  separates HTTPREAD `ERROR` from timeout diagnostics with
  `LTE_HTTP_READ_AT_ERROR` and `LTE_HTTP_READ_AT_TIMEOUT`. The source/build
  app commit is `c8e1f59`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin`,
  and its size is `291872` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. The image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 was detected, bootloader/app/partition table
  were written, hashes verified, and hard reset completed. The flashed
  repo/app version is `b4eaa44` because the guarded flash re-ran CMake at the
  documentation commit. Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix4-20260629-084350/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T07:38:00Z` to
  `2026-06-29T07:44:00Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 37 LTE
  diagnostic messages, with the latest reporting LTE ready, HTTP poll status
  `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. Evidence is
  under `reports/field_validation/lte003-command-loop-fix4-20260629-084350/`.
- LTE command polling/ACK, reconnect behavior, long-run LTE stability, product
  battery/charging accuracy, product power behavior, and final
  enclosure/mounting GNSS acceptance remain unverified. LTE-003 currently has
  fix4 build/flash evidence and failed runtime attempts through fix4; it does
  not prove LTE command polling/ACK until the USB-Free Message Hub validator
  passes.
- LTE-003 fix5 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix5` /
  `lte003-command-loop-fix5-20260629-154839`. It keeps the positional
  `AT+HTTPREAD=0,<data_len>` attempt, but falls through to bare `AT+HTTPREAD`
  when the positional command returns `OK` without an extractable JSON body.
  The source/build app commit is `729c78b`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin`,
  and its size is `291872` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. The image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 was detected, bootloader/app/partition table
  were written, hashes verified, and hard reset completed. The flashed
  repo/app version is `efc9848` because the guarded flash re-ran CMake at the
  documentation commit. Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix5-20260629-154839/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T07:58:34Z` to
  `2026-06-29T08:04:36Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 37 LTE
  diagnostic messages, with the latest reporting LTE ready, HTTP poll status
  `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. Evidence is
  under `reports/field_validation/lte003-command-loop-fix5-20260629-154839/`.
- LTE-003 fix6 has been implemented, build-verified, and flashed as
  `0.1.0-lte003-command-loop-fix6` /
  `lte003-command-loop-fix6-20260629-160859`. It adds an HTTPREAD-specific
  UART collection path that keeps reading past the generic AT `OK` match until
  a JSON body is captured, an error appears, or the bounded timeout/quiet
  window expires. The source/build app commit is `c1a90a0`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/egolink_mqtt_heartbeat.bin`,
  and its size is `292512` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Flash on `COM4` passed after explicit operator
  confirmation; flashed repo/app version is `8d7395f`, and flash evidence is
  under
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/flash_report.md`.
  USB-Free runtime validation failed: the validator reused pending `cmd-000013`
  from `2026-06-29T08:31:32Z` to `2026-06-29T08:37:33Z`, the command remained
  `pending`, and no ACK was received. The test-run export contained 37 fix6
  diagnostics from `2026-06-29T08:18:30Z` to `2026-06-29T08:23:32Z`, with the
  latest showing LTE ready, HTTP poll status `200`, body length `592`,
  `LTE_HTTP_OK`, and empty `command.last_cmd_id`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/`.
  Fix7 should add command parser diagnostics and a longer bounded poll window.
- LTE-003 fix7 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix7` /
  `lte003-command-loop-fix7-20260629-164429`. It adds command poll parser
  observability (`command.parse_status` and `command.command_count`) to both
  LTE command diagnostics and ACK payloads, and increases the bounded command
  poll window to
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS=120` at
  5-second intervals. The source/build app commit is `33b8503`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix7/egolink_mqtt_heartbeat.bin`,
  and its size is `293104` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Flash on `COM4` passed after explicit operator
  confirmation; flashed repo/app version is `766f0d8`, and flash evidence is
  under
  `reports/field_validation/lte003-command-loop-fix7-20260629-164429/flash_report.md`.
  USB-Free runtime validation failed: the validator reused pending `cmd-000013`
  from `2026-06-29T08:54:55Z` to `2026-06-29T09:00:56Z`, the command remained
  `pending`, and no ACK was received. The test-run export contained 66 fix7
  diagnostics from `2026-06-29T08:51:43Z` to `2026-06-29T09:00:55Z`: one
  `phase=ready` / `command.parse_status=not_polled`, then 65
  `phase=poll_no_ack` with `command.parse_status=json_parse_failed`. Latest
  diagnostics showed LTE ready, HTTP poll status `200`, body length `592`,
  `LTE_HTTP_OK`, `command.command_count=0`, and empty `command.last_cmd_id`.
  Evidence is under
  `reports/field_validation/lte003-command-loop-fix7-20260629-164429/`.
  Fix8 should make HTTPREAD body extraction wait for a complete JSON object.
- LTE-003 fix8 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix8` /
  `lte003-command-loop-fix8-20260629-170628`. It changes the SIM7670G HTTPREAD
  body extractor to wait for a complete brace-balanced JSON object, with
  string/escape awareness, before returning a JSON body. The source/build app
  commit is `a87a754`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix8/egolink_mqtt_heartbeat.bin`,
  and its size is `293216` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Fix8 has not been flashed or USB-Free runtime
  validated yet.
- FW-003 raw-frame LTE command-loop firmware has been implemented and
  build-verified as `0.1.0-fw003-raw-command-loop` /
  `fw003-raw-command-loop-20260629-175608`. It keeps
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`, skips Wi-Fi for that
  image, polls `GET /commands/poll.raw`, verifies the `EGLK/1` raw-frame
  length and CRC32, parses compact key/value commands, and posts raw ACK frames
  to `POST /commands/{cmd_id}/ack.raw`. The binary is
  `firmware/mqtt_heartbeat/build_fw003_raw_command_loop/egolink_mqtt_heartbeat.bin`,
  and its size is `286176` bytes. Focused firmware/server tests passed with
  24 tests, `context_lint` passed, full `verify.ps1` passed with 278 tests,
  `git diff --check` passed, and the guarded ESP-IDF prepare/build passed. The
  VPS Message Hub was redeployed after adding raw ACK derived LTE evidence; the
  public smoke `fw003-raw-derived-smoke-20260629-175946` ACKed `cmd-000016`
  through raw frames and derived `transport.type=lte` plus
  `lte_http.phase=command_ack`. FW-003 was then flashed on `COM4` after
  explicit operator confirmation; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/flash_report.md`.
  USB-Free runtime validation passed after an independent-power cold boot with
  USB disconnected: validator created `cmd-000017`, observed raw-frame ACK
  `seq=5`, `transport.type=lte`, `lte_http.phase=command_ack`,
  `lte_http.poll_reason_code=LTE_HTTP_OK`, HTTP status `200`, action elapsed
  `450 ms`, `command.parse_status=raw_command_selected`, and command status
  `ok`. Runtime evidence is under
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/`.
- RAW-LTE-REPEAT-001 attempt 1 then passed as a short USB-Free repeat after an
  operator-confirmed independent-power cold boot with USB disconnected. The
  first validator invocation created `cmd-000018` and saw a healthy raw LTE
  ACK, then returned a false-negative due to ACK `test_run_id` comparison
  semantics. Reconciliation reused existing `cmd-000018` without queueing a new
  command and passed with `transport.type=lte`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `command.parse_status=raw_command_selected`, and command/ACK status `ok`.
  Evidence is under
  `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/`.
- RAW-LTE-REPEAT-001 attempt 2 passed after a separate operator-confirmed
  independent-power cold boot with USB disconnected. Validator test run
  `raw-lte-repeat-001-a2-20260629-210939` created `cmd-000019` and observed a
  raw LTE ACK with `seq=7`, `transport.type=lte`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `poll_action_elapsed_ms=680`, `command.parse_status=raw_command_selected`,
  `command.command_count=1`, and command/ACK status `ok`. Evidence is under
  `reports/field_validation/raw-lte-repeat-001-a2-20260629-210939/`. With
  attempts 1 and 2 both passed, the short USB-Free raw LTE repeat gate is
  satisfied; long LTE stability, reconnect recovery, GNSS-over-LTE, battery,
  power, and enclosure behavior remain unverified.
- LTE-004 raw LTE request-location thin slice is implemented, VPS-deployed, and
  build-verified as `0.1.0-lte004-raw-lte-location` /
  `lte004-raw-lte-location-20260629-213717`. Firmware now accepts
  `request_location` in the raw LTE command loop, uploads an `EGLK/1
  type=event` key/value `location_report` to `/raw-ingest`, and then posts the
  raw ACK. Message Hub derives Web/API `location_report` fields only after
  storing the raw frame. VPS smoke
  `lte004-vps-raw-location-smoke-20260629-133701` derived
  `event_type=location_report`, `fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`, and `location_request_cmd_id=cmd-smoke-000001` from a
  synthetic raw event without touching GitLab. The binary is
  `firmware/mqtt_heartbeat/build_lte004_raw_lte_location/egolink_mqtt_heartbeat.bin`,
  and its size is `296112` bytes. Focused tests passed with 36 tests,
  `context_lint`, full `verify.ps1` with 282 tests, `git diff --check`, and
  guarded ESP-IDF prepare/build all passed. This build record was followed by
  the flash and USB-Free runtime evidence below.
- LTE-004 was flashed on `COM4` after explicit operator confirmation. Board
  probe evidence `reports/board_validation/20260630-075007/probe.md`
  identified `COM4` as the ESP32-S3 CH343 console and SIM7670G AT candidates
  `COM6` / `COM7` as registered/attached. Flash evidence is at
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/flash_report.md`.
  `esptool.py` detected ESP32-S3, wrote bootloader, app, and partition table,
  verified hashes, and hard reset the board.
- LTE-004 USB-Free runtime validation passed after the operator connected
  independent power and disconnected USB. Validator run
  `lte004-raw-lte-location-20260629-213717` created `cmd-000020`
  (`request_location`), required a matching LTE `location_report`, and passed.
  Derived raw location evidence: `seq=30`, raw frame `loc-cmd-000020`,
  `transport.type=lte`, `lte_http.phase=location_report`,
  `source=sim7670g_firmware_gnss`, `source_status=unverified`,
  `gnss_query_ok=true`, `gnss_state=no_fix`, `fix=false`, and
  `location_request_cmd_id=cmd-000020`. Raw ACK evidence: `seq=31`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `poll_action_elapsed_ms=560`, `command.parse_status=raw_command_selected`,
  and command/ACK status `ok`. Evidence is under
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/`. This
  proves the bounded raw LTE `request_location -> location_report -> ACK`
  slice only; real GNSS fix, long LTE stability, reconnect recovery, battery,
  power, and enclosure behavior remain unverified.
- LOC-004A real cell location observation is implemented, VPS-deployed,
  build-verified as `0.1.0-loc004a-cell-observation` /
  `loc004a-cell-observation-20260630-001`, flashed on `COM4` after explicit
  operator confirmation, and reconciled as a bounded USB-Free runtime PASS
  after an independent-power reboot with USB disconnected. Message Hub derives
  raw
  `event_type=location_observation` key/value frames into `cell`, `lte`,
  `transport`, `lte_http`, and `location_belief` fields after raw storage.
  Unknown observations preserve existing useful `location_memory` and can
  derive active belief `Predicted` with reason
  `last_known_after_unknown_location_observation`. VPS smoke
  `loc004a-vps-cell-observation-smoke-20260630-012442` passed with
  `cell.rat=LTE`, `cell.cell_id=01AF23`,
  `lte.reason_code=LTE_READY`, `transport.type=lte`, and
  `location_belief.state=Unknown`; evidence is under
  `reports/location_observation/loc004a-vps-cell-observation-smoke-20260630-012442/`.
  The build used `CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y`,
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y`,
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y`, and
  `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y`; binary is
  `firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`
  (`298416` bytes). Focused tests passed with 50 tests, `context_lint` passed,
  full `verify.ps1` passed with 292 tests, `git diff --check` passed, and the
  guarded ESP-IDF prepare/build passed.
- LOC-004A flash evidence is recorded at
  `reports/field_validation/loc004a-cell-observation-20260630-001/flash_report.md`.
  `esptool.py` detected ESP32-S3 QFN56 rev v0.2 on `COM4`, wrote bootloader,
  app, and partition table, verified hashes, and completed hard reset.
- LOC-004A USB-Free runtime evidence is reconciled as PASS after the operator
  rebooted the connectivity node on independent power with USB disconnected.
  The device consumed pending command `cmd-000021` and produced raw
  `location_report` frame `loc-cmd-000021` (`seq=2`, `fix=false`,
  `gnss_state=no_fix`, `gnss_query_ok=true`, `transport.type=lte`), raw
  `location_observation` frame `obs-cmd-000021` (`seq=3`,
  `cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-98`,
  `lte.reason_code=LTE_READY`, assigned IP `10.91.147.246`,
  `location_belief.state=Unknown`, `transport.type=lte`), and raw ACK
  `cmd-000021` (`seq=4`, status `ok`, `LTE_HTTP_OK` / HTTP `200`). Evidence
  is under
  `reports/field_validation/loc004a-cell-observation-runtime-20260630-001/`.
  A later stale `cmd-000022` from the second validator attempt was cancelled
  server-side and is not hardware evidence. This validates only the bounded
  raw LTE `request_location -> location_report -> location_observation -> ACK`
  slice; long LTE stability, reconnect recovery, cell-only positioning,
  battery/power, and product readiness remain unverified.
- FIELD-002A then passed a reboot-aware USB-Free validator smoke against the
  same LOC-004A firmware without flashing. The validator armed `cmd-000023`
  under `loc004a-reboot-aware-20260630-001`, the operator rebooted on
  independent power with USB disconnected, and reconciliation reused
  `cmd-000023` with command-created evidence anchoring. The run produced raw
  `location_report` frame `loc-cmd-000023` (`seq=2`, `fix=false`,
  `gnss_state=no_fix`, `transport.type=lte`), raw `location_observation`
  frame `obs-cmd-000023` (`seq=3`, `cell.rat=LTE`,
  `cell.cell_id=180571649`, `cell.rsrp=-97`, `lte.reason_code=LTE_READY`,
  assigned IP `10.31.138.19`, `location_belief.state=Unknown`), and raw ACK
  `cmd-000023` (`seq=4`, status `ok`, `LTE_HTTP_OK` / HTTP `200`). Evidence
  is under `reports/field_validation/loc004a-reboot-aware-20260630-001/`.
  This validates the FIELD-002 arm/reboot/reconcile workflow on one real
  USB-Free command; it is not a long LTE stability or product readiness claim.
- LOC-005A source-state firmware has been build-verified, VPS-deployed, and
  flashed on `COM4` as `0.1.0-loc005a-source-states` /
  `loc005a-source-states-20260630-001`. It adds explicit Wi-Fi/IMU/power
  source-state slots to raw LTE `location_observation` while preserving
  raw-frame/KV transport. Flash evidence is under
  `reports/field_validation/loc005a-source-states-20260630-001/flash_report.md`.
  `esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote bootloader, app
  (`300448` bytes), and partition table, verified hashes, and hard-reset the
  board. USB-Free runtime validation passed after the operator rebooted the
  board on independent power with USB disconnected and the validator
  reconciled existing `cmd-000024`. Evidence is under
  `reports/field_validation/loc005a-source-states-20260630-001/`:
  raw LTE `location_report seq=2` (`fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`), raw LTE `location_observation seq=3`
  (`cell.cell_id=180571649`, `lte.reason_code=LTE_READY`,
  `wifi.source_status=disabled`, `imu.source_status=unverified`,
  `power.source_status=mock`, `transport.type=lte`), and raw LTE ACK `seq=4`
  (`cmd_id=cmd-000024`, status `ok`, `LTE_HTTP_OK` / HTTP `200`).
- LTE-006 fix1 reliability non-claim firmware has been implemented,
  build-verified, flashed on `COM4`, and USB-Free runtime validated as
  `0.1.0-lte006-reliability-nonclaim-fix1` /
  `lte006-reliability-nonclaim-fix1-20260701-001`. It compacts the raw LTE
  `location_observation` payload to stay below the known SIM7670G large HTTP
  payload risk range while preserving network state, cache non-claim, source
  state, transport, and belief explanation fields. Flash on `COM4` passed
  after explicit operator confirmation; `esptool.py` detected ESP32-S3 QFN56
  rev v0.2, wrote bootloader, app (`299824` bytes), and partition table, and
  verified hashes. USB-Free runtime validation passed after the operator
  connected independent power and disconnected USB. Evidence is under
  `reports/field_validation/lte006-reliability-nonclaim-fix1-20260701-001/`:
  raw LTE `location_report seq=60` (`fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`), raw LTE `location_observation seq=61`
  (`cell.cell_id=180571649`, `lte.reason_code=LTE_READY`, assigned IP
  `10.141.88.185`, `wifi.source_status=disabled`,
  `imu.source_status=unverified`, `power.source_status=mock`,
  `location_belief.state=Unknown`, `transport.type=lte`), and raw LTE ACK
  `seq=62` (`cmd_id=cmd-000026`, status `ok`, `LTE_HTTP_OK` / HTTP `200`).
  LTE-005 over the fix1 export returns expected `WARN` because real cache/drop
  evidence remains absent; this is not a long LTE stability, reconnect
  recovery, durable cache, or product-readiness claim.
- LTE-007 volatile cache/drop observability firmware has been implemented,
  build-verified, flashed on `COM4`, and USB-Free runtime validated. Firmware
  version `0.1.0-lte007-volatile-cache-observe` / test run
  `lte007-volatile-cache-20260701-001` builds to
  `firmware/mqtt_heartbeat/build_lte007_volatile_cache_observe/egolink_mqtt_heartbeat.bin`
  (`301056` bytes). Flash on `COM4` passed after explicit operator
  confirmation; `esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote
  bootloader, app, and partition table, and verified hashes. Local flash
  evidence is under
  `reports/field_validation/lte007-volatile-cache-20260701-001/flash_report.md`.
  USB-Free runtime validation passed after independent-power/USB-disconnected
  reboot using existing command `cmd-000028`: raw LTE `location_report seq=2`,
  raw LTE `location_observation seq=3`, and raw LTE ACK `seq=4` all arrived
  with LTE transport and matching test run ID. The VPS/Web deployment now
  derives `reliability.network/cache` from LTE-007 raw KV fields; the
  observation reported `cache_state=volatile_outbox`, zero queued/dropped
  messages, `cache_last_drop_reason=none`, and raw POST `1/1/0`, while ACK
  reported raw POST `2/2/0`. This is not durable offline cache, reconnect
  recovery, long LTE stability, or product-readiness evidence.
- LTE-008 bounded raw POST retry observability has been implemented,
  build-verified, flashed on `COM4`, failed once in an explainable way, and
  passed USB-Free runtime after the fix1 payload compaction.
  Firmware
  version `0.1.0-lte008-bounded-raw-retry` / test run
  `lte008-bounded-raw-retry-20260701-001` builds to
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry/egolink_mqtt_heartbeat.bin`
  (`301824` bytes) with
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX=1`,
  SIM7670G GNSS enabled, LTE status enabled, raw LTE command loop enabled, and
  location observation enabled. The image retries one failed raw-frame LTE HTTP
  POST within the current boot before final drop accounting, and reports
  `cache_retry_policy=single_retry_current_boot` plus retry attempt/success/
  failure counters in raw LTE `location_observation` and ACK payloads. Flash
  evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/flash_report.md`.
  The first USB-Free runtime validation attempt failed in an explainable way:
  command `cmd-000029` produced raw LTE `location_report seq=4` and raw LTE
  ACK `seq=6`, but ACK status was `error` with message
  `lte raw location_observation upload failed`, cache drop reason
  `location_observation_payload_truncated`, and evidence under
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/`.
  LTE-008 fix1 is build-verified as
  `0.1.0-lte008-bounded-raw-retry-fix1` /
  `lte008-bounded-raw-retry-fix1-20260701-001`, binary
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry_fix1/egolink_mqtt_heartbeat.bin`
  (`301680` bytes). The fix1 image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 QFN56 rev v0.2 was detected, app size was
  `301680` bytes, hashes were verified, and flash evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/flash_report.md`.
  USB-Free runtime validation then passed with command `cmd-000030`: raw LTE
  `location_report seq=15`, raw LTE `location_observation seq=16`, and raw
  LTE ACK `seq=17` reached the VPS with matching firmware/test-run IDs,
  `transport.type=lte`, `cache_retry_policy=single_retry_current_boot`,
  retry counters `0/0/0`, and ACK status `ok`. Evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/`.
  This is not actual retry-after-failure, durable offline cache, reconnect
  recovery, long LTE stability, or product-readiness evidence.
- LTE-009 raw POST retry fault injection has been implemented, VPS-deployed,
  flashed on `COM4`, and USB-Free runtime validated as
  `0.1.0-lte009-raw-post-retry-fault` /
  `lte009-raw-post-retry-fault-20260701-001`. It adds a default-off firmware
  test switch, `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST`, and
  a Message Hub fail-once raw-ingest path that retains the first marked raw
  frame as `injected_failure` before returning HTTP 503. The binary is
  `firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
  (`301776` bytes). It was rebuilt during the flash with app version `88945b9`.
  The updated Message Hub was deployed to the VPS after commit
  `10e28fe`; `/health`, unauthenticated `/api/state` = `401`,
  authenticated `/api/state`, and a VPS-local in-memory fail-once smoke all
  passed. Flash evidence is under
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/flash_report.md`.
  USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB: validator command `cmd-000031` produced retained
  raw LTE `location_report` frame `loc-cmd-000031` first as
  `injected_failure`, then as retry `ok`, followed by raw LTE
  `location_observation seq=28` and raw LTE ACK `seq=29`. Retry evidence showed
  `cache_retry_policy=single_retry_current_boot`, retry counters `1/1/0`, and
  final raw POST counters `3/2/1`. Evidence is under
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/`.
- LTE-011 reconnect/store-forward evidence test mode has been build-verified
  and flashed on `COM4` as `0.1.0-lte011-reconnect-store-forward-test` /
  `lte011-reconnect-store-forward-test-20260702-001`. It adds default-off
  `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST`, script support
  for `-EnableReconnectStoreForwardTest`, raw LTE
  `network_reconnect_*` / `cache_flush_*` evidence fields, and Message Hub /
  Dashboard derivation for Cache Flush. Focused firmware/script/server/
  dashboard tests passed with 51 tests. Guarded ESP-IDF build passed and
  produced
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test/egolink_mqtt_heartbeat.bin`
  (`302496` bytes). Flash on `COM4` passed after explicit operator
  confirmation; ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, was
  detected and bootloader/app/partition-table hashes were verified. Flash
  evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/flash_report.md`.
  USB-Free runtime validation then failed in an explainable way. After an
  independent-power reboot with USB disconnected, command `cmd-000032`
  produced raw LTE `location_report` frame `loc-cmd-000032` (`seq=2`,
  `fix=false`, `gnss_state=no_fix`) and raw LTE ACK `seq=4`, but command
  status was `error` because the raw LTE `location_observation` frame was
  dropped before POST with
  `cache_last_drop_reason=location_observation_payload_truncated`. Evidence is
  under
  `reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/`.
  LTE-011 fix1 is build-verified as
  `0.1.0-lte011-reconnect-store-forward-test-fix1` /
  `lte011-reconnect-store-forward-test-fix1-20260702-001`. It increases only
  the raw LTE `location_observation` local payload/frame buffers to
  `2050`/`2400` bytes; focused firmware tests passed with 13 tests, and the
  guarded ESP-IDF build produced
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test_fix1/egolink_mqtt_heartbeat.bin`
  (`302528` bytes). Fix1 was then flashed on `COM4` after explicit operator
  confirmation; ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, was
  detected and bootloader/app/partition-table hashes were verified. Flash
  evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/flash_report.md`.
  USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB: command `cmd-000033` produced raw LTE
  `location_report` frame `loc-cmd-000033` (`seq=28`, `fix=false`,
  `gnss_state=no_fix`), raw LTE `location_observation` frame
  `obs-cmd-000033` (`seq=29`, `cell.cell_id=180571649`,
  `lte.reason_code=LTE_READY`, assigned IP `10.55.187.235`), and raw LTE ACK
  `seq=30` (`status=ok`, `LTE_HTTP_OK` / HTTP `200`). LTE-011 test-mode
  reliability evidence showed reconnect count `1`, reason `pdp_reactivate`,
  network failure reason `LTE_HTTP_ACTION_FAILED`, store-forward queue count
  `1`, oldest age `12000 ms`, and then ACK-side cache queue drained to `0`.
  Evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/`.
  The LTE-010 offline reconnect/store-forward evidence gate then returned
  PASS over the export, with report under
  `reports/lte_reconnect_store_forward/lte011-fix1-20260702-001/`. This is a
  test-mode evidence pass and does not prove real modem reconnect recovery,
  durable local storage, queue replay, long LTE stability, GNSS acceptance,
  power behavior, enclosure behavior, or product readiness.
- Full Demo v0.5 audio evidence is structured mock-only; real microphone capture and audio acceptance remain unverified.
- The latest Demo v0.3/v0.5 motion candidate can use real AMOLED QMI8658 `motion_event` evidence, but it is still a demo-only heuristic, not MotionNet output.
- Formal IMU product acceptance remains false until final mounting/calibration gates are met.
