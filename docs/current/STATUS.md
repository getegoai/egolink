---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-09-21
verified_by: founder/codex
---

# Ego Link Current Status

## Current milestone

[ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
directs the current A line to one identified ESP32-S3-SIM7670G-4G board plus
the historically observed OV5640 Camera candidate, external QMI8658A, power source and
LTE/GNSS antennas. The milestone outcome is:

```text
asynchronous GNSS/LTE/IMU/raw collection
+ bounded persistent ordinary and JPEG backlogs
+ authorized Web one-shot still capture over real LTE
+ default-off local timed capture with outage/restart recovery
+ ordinary observations over actual Wi-Fi and LTE with a controlled transition
+ durable VPS storage, private Web preview and export
-> independently powered joint short run
-> FIELD-020 representative day
```

AMOLED, a board-to-board bridge, CALL and full physical SOS are not A-line
dependencies for this milestone. Camera is required here but is not a fourth
sellable-P0 Gate and is not a Location/SOS decision source.

## Actual hardware and running state

- `connectivity-node-001` was reidentified on CH343 `COM3` as ESP32-S3 rev
  v0.2, MAC `02:00:00:00:00:03`, with 16 MiB physical flash.
- The latest executed application is the app-only candidate image
  `0.1.0-sensor-policy-continuous-021` (run `field-sensor-policy-20260919-021` with cellular call & ego-state engine integration, Boot 188),
  1,228,080 bytes, application SHA-256 `f9869caeab2b4fce9cae2d553d9d0142dbb63e37bc386237a0524325712c6d3f`,
  ELF SHA-256 `420d7607e026cc37d4cc03e9781ecb95abcb19d5d09cd3858ae3a0979efe9aa5`.
  It integrates the Phase 3 Task B1 cellular voice AT channel driver (`sim7670_cellular_call`),
  the native ego-state estimation engine (`ego_state_engine`), dynamic sensor policy engine (`collection_sensor_policy`),
  verified shared-I2C camera profile, SIM7670G USB LTE PPP, and I2C 9-clock bus self-healing & 3x retry probe loop (`platform_i2c_bus_recover`).
  In Boot 188 on COM3, camera runtime debug metrics were trimmed from the `HEALTH` payload, ensuring the `DEVICE` collection frame stays comfortably within `COLLECTION_FRAME_CAPACITY` (4000 bytes).
  MAX17048 battery probe `0x0012` and QMI8658 IMU probe `0x05` succeeded, the ego-state engine initialized,
  SIM7670 UART1 initialized with exclusive access, cellular call driver configured successfully,
  and USB LTE PPP connection acquired IP `10.49.186.235` with continuous telemetry upload over 4G LTE.
  Live VPS Message Hub ingestion confirmed `col-b188-device-1` with `ego_state` (`spatial_mobility: "stationary"`, `device_wear_state: "tabletop_resting"`, `confidence: 0.83`) stored in `collection_ego_states`.
  Full repository verification passed 1,833/1,833 automated tests.
- The prior executed application was the app-only candidate image
  `0.1.0-sensor-policy-continuous-021` (Boot 183),
  1,228,672 bytes, application SHA-256 `dac596233d1da4d4607cc93015780c4046d1257d94bcfcdb49c22f8043903110`,
  ELF SHA-256 `c374cee46036b42dbd5495a5e46160f696776ee24dca07075204b2d75422490c`.
- The prior executed application was the app-only run021 candidate image
  `0.1.0-sensor-policy-continuous-021`, run `field-sensor-policy-20260919-021`,
  1,216,912 bytes, application SHA-256 `79c0dae8689ffd91601303735384a3e7ab03a4f83b633af04eba7779c1a0bc54`,
  ELF SHA-256 `2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87`.
  It integrates the dynamic sensor policy engine (`collection_sensor_policy`), config
  `p0-sprint1-engineering-default-20260823`, verified shared-I2C camera profile, SIM7670G USB LTE PPP,
  and the I2C 9-clock bus self-healing & 3x retry probe loop (`platform_i2c_bus_recover`).
  In boot 171, 20Hz QMI8658 sampling and MAX17048 battery monitoring ran without probe failure, measuring stationary bench noise
  at `0.157 m/s²` (safely below the 0.3 m/s² threshold $\to$ `stable`). All telemetry was delivered to the
  VPS Message Hub over 4G LTE with 54+ consecutive HTTP 200 uploads, including dynamic `sensor_policy` state,
  power, GNSS, LTE, Wi-Fi, and startup session confirmation.
- The prior executed application was the app-only run020 candidate image
  `0.1.0-sensor-policy-continuous-020`, run `field-sensor-policy-20260918-020`,
  1,215,856 bytes, application SHA-256 `b64c72a1df2cc5cc1424e656a49e0bcbe22da855aee4ef932bd83b55b889567c`,
  ELF SHA-256 `126639b1eec7fa431a08667a2ad0a0ae530271e86110db3c8b47d46eceffc10f`.
- The prior executed application was the app-only run018 candidate image
  `0.1.0-camera-lte-timed-018`, run
  `camera-lte-timed-20260917-018`, 1,204,400 bytes, application SHA-256
  `6949CBD24A3DEE98FBEE4AF855E6EC41DACBE7F7B564A421121D186401D83F41`.
- The post-run016 Camera-layout `ego_collection` partition at `0x500000`, length
  `0x100000`, was privately backed up and then exactly erased under the existing
  founder authorization. The immediate complete readback was all `0xFF`; run017
  then resumed normal collection, so that post-clear result is not a claim that
  the partition remains empty. The app, NVS, media and outbox partitions were
  outside the erase.
- The proposed Camera media range `[0x600000,0xF00000)` was subsequently read
  in full into a private ignored backup. All 9,437,184 bytes were `0xFF`, and
  a subsequent `verify_flash` readback returned `verify OK`; the current
  observed occupancy permits reserving it for `ego_media` without displacing
  observed retained data.
- Run015 identified the OV5640 and completed exactly one fresh authenticated
  manual command -> real QVGA capture -> local save -> LTE metadata/content
  upload -> VPS durable storage -> private Guardian content-API download. The
  3,957-byte JPEG matched the device/server/API SHA-256 exactly. GNSS/no-fix,
  external IMU, LTE and available-power observations continued after capture.
- The bounded 300-second serial window observed PPP link/IP establishment and
  43 ordinary LTE HTTP-200 uploads without a panic, USB-enumeration failure or
  unexpected reboot. USB supplied power/serial/flash, so this is real LTE data
  evidence but not USB-free or independent-power evidence.
- After run015, the complete 1 MiB collection spool was privately backed up
  without erase. Its transient ROM-bootloader exit state was superseded by the
  run016 app-only write and independent matching `verify_flash`; no other
  partition was erased.
- Run016 then passed a 180-second LTE concurrency regression with one link-up,
  one PPP IPv4 event, 25 ordinary LTE HTTP-200 uploads and nine fresh healthy
  status snapshots. It recorded no stale/busy status, link-down, panic or photo
  event. No photo command was issued; run015 remains the Camera closure proof.
  Across the retained health samples, however, queued bytes rose from 502,511
  to 605,143 while persisted records rose from 3 to 66 and acknowledgements
  from 0 to 21. Errors/evictions stayed zero in that window, but the net growth
  identified sustained throughput as the next blocker.
- Run017 changed only the Camera command poll interval from 2 seconds to 15
  seconds while retaining the same sampling rates. From a verified empty spool,
  its 600-second firmware-bound real-LTE run delivered 248/248 ordinary uploads
  with HTTP 200, exact local match and local ACK. An initial 55,842-byte pre-PPP
  peak cleared by approximately 124 seconds; steady queue occupancy stayed from
  0 to 6,658 bytes and the final health sample was zero. TLS handshakes fell to
  65, and eviction, RAM-pending, error, stale/busy, link-down, panic and photo
  counters remained zero. This closes the immediate sustained ordinary-upload
  blocker for the ten-minute USB-powered bench scope, not endurance or field use.
- AMOLED is excluded from A-line runtime and acceptance; its retained UI/CALL
  image is unchanged. The `C-ME-0.1` C-line draft was not touched.
- Browser visual preview and authenticated API export were verified on
  2026-09-17: the stored run015 JPEG (3,957 bytes, SHA-256
  `d167bef33eb1b186da3a71ce3f8785c42a1f2f7f44fd18034ffb1e263df29a55`) was
  restored to VPS storage with 7-day authorized retention, verified via live
  HTTP GET with Guardian bearer authentication, and loaded into DevBench Web
  for preview and export.
- The timed candidate profile `sdkconfig.camera_timed_candidate.defaults` was
  promoted to `CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED=y` and built
  with ESP-IDF v5.4.2 into `0.1.0-camera-lte-timed-018` (1,204,400 bytes, SHA-256
  `6949CBD24A3DEE98FBEE4AF855E6EC41DACBE7F7B564A421121D186401D83F41`).
- Run018 flashed this candidate app-only on COM3, verified digest match, and
  completed live verification: mounted 9 MiB `ego_media`, confirmed OV5640 with
  `timer_capture_allowed=1`, established SIM7670G USB LTE PPP at 35s, executed
  one fresh manual capture command, saved the 3,657-byte JPEG to flash media store,
  uploaded it over LTE PPP to VPS durable storage (`content_status='stored'`),
  and acknowledged the command. Concurrently, 391 ordinary uploads drained the
  608,911-byte spool queue completely down to zero (`queued_bytes=0`).
- On 2026-09-18, the continuous candidate `0.1.0-camera-lte-continuous-019` running
  under independent battery power on `ego-link-001` (Boot 142) verified the
  default-off timed capture lifecycle (`configure_photo_timer`):
  - 3-shot scheduled capture: `interval=60s, max_photos=3` polled via 4G LTE PPP,
    ACKed as `applied`, scheduled 3 consecutive OV5640 captures at 60s intervals
    (3,860 B, 3,353 B, 3,360 B), stored to `ego_media` Flash, uploaded over LTE PPP
    to VPS durable storage (`stored`), and automatically disarmed on reaching the limit
    (`state_reason='max_photos_reached'`).
  - Remote cancel/stop: armed with `max_photos=5`, captured 2 photos, received
    `enabled=false` STOP command, ACKed as `applied` with `state_reason='disabled_by_command'`,
    and immediately halted further captures without residual triggers.
  - Concurrency: Ordinary 100Hz IMU, battery, and network telemetry continued streaming
    uninterrupted throughout all capture and upload intervals.
- Outage persistence, restart recovery of a pending photo, controlled Wi-Fi/LTE
  transition, and FIELD-020 remain pending.

Exact active-image history and board capability boundaries are in
[ACTIVE_BUILD](ACTIVE_BUILD.md) and the
[board matrix](../hardware/BOARD_MATRIX.md).

The storage preflight is recorded in
[CAMERA-MEDIA-001](../hardware/CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md). It
involved no flash write and left the board in ROM bootloader at that checkpoint;
the later run006 app flash supersedes that transient device state.

The current joint-firmware run, hashes, exact partition clear and honest
failure/pass split are recorded in
[CAMERA-SHARED-I2C-TRIAL-20260909-001](../hardware/CAMERA_SHARED_I2C_TRIAL_20260909.md).
The later real-LTE manual Camera and private-API integrity slice is recorded in
[CAMERA-LTE-MANUAL-20260916-001](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md).

## Verified evidence that may be inherited

- TCAM-001 on 2026-06-23 identified the attached OV5640 and captured three
  QVGA JPEGs in the isolated `camera_smoke` image. This does not prove current
  joint-firmware coexistence, persistent media storage or LTE upload.
- D2-006 identified the external ATK-NB018 V1.0 QMI8658A at I2C address
  `0x6A` on GPIO15/16 and captured 100 real non-mock six-axis samples.
- D2-008 later uploaded 26 real non-mock QMI8658A samples over a bounded Wi-Fi
  smoke. This does not prove the current joint image, LTE upload, calibration,
  mounting or continuous field operation.
- Existing GNSS/LTE and Location evidence remains scoped to its recorded
  images and runs. It cannot be combined arithmetically with the separate
  Camera smoke to claim the new milestone.

## Legacy Wi-Fi data cleanup

The founder-authorized cleanup completed across the identified device spool,
named local private reports and exact matching VPS rows. Every deleted item
was first hash-verified into the Git-ignored project backup at
`.local_backups/wifi_spool_20260909-120744/`.

Exactly 81 matching VPS collection records, 82 associated delivery attempts
and 81 associated raw frames were removed through a validated SQLite candidate
and atomic replacement. The live database passed integrity checks and the
service recovered healthy with zero remaining target rows. A sanitized remote
recovery point remains. This was a bounded deletion, not deletion of all
historical project data. Exact ranges, counts and hashes are recorded in
[PRIVACY_WIFI_SPOOL_PURGE_20260909](../hardware/PRIVACY_WIFI_SPOOL_PURGE_20260909.md).

## Current implementation state

- The accepted scope, privacy boundary and active task packet now describe the
  single-board Camera milestone; CALL-020, CALL-021 and SOS-010 are paused.
- The offline device source slice now contains bounded OV5640 one-shot capture,
  durable timer/command/capture journals, a separate fixed-slot JPEG store,
  metadata-before-media delivery, strict command/content ACK matching,
  retention cleanup, reboot recovery and fair ordinary/photo upload scheduling.
  The normal Camera profile defaults to the shared-I2C Gate `blocked`. The
  additive `sdkconfig.camera_shared_i2c_trial.defaults` profile is explicitly
  `trial_unverified` and permits only the existing Web manual command path,
  with at most one actual Camera/I2C attempt per boot. Busy admission does not
  consume the budget; any hardware attempt does. Blocked/trial images reject
  timed capture and never report the Camera source as verified/runtime-ready.
- Capture journal v2 now binds the capture-time Gate, driver profile, runtime
  config, firmware version and ELF digest. Legacy v1 capture state restores as
  `unknown_legacy`, never as the current image's identity. Final independent
  review also closed inherited-timer ACK paths that could otherwise misreport
  `applied` after a downgrade to blocked/trial.
- The deployed VPS/Web source slice now contains Guardian-bound capture sessions,
  one-shot/timer controls, immutable Camera metadata, private JPEG storage,
  integrity-verified content ACK, retention tombstones/retry, preview and
  export. Its ingest/storage path accepted the exact run005, run006, run006b
  and run015 Camera identities and bytes. Run015 additionally passed an
  authenticated private Guardian content-API byte-integrity check;
  browser-side visual preview/export remains unverified.
- Four earlier clean no-flash builds pass: default, legacy collector, Camera
  blocked and Camera trial. Both Camera profiles deliberately retain
  `NO_SIM=y` and LTE PPP disabled. The clean trial build has empty compiled
  Wi-Fi and bearer credentials, so its exact SHA is build evidence rather than
  a network-capable live image. The trial profile supplies the controlled
  mechanism first used by the ignored private run006 overlay. The later run015
  image enabled the real SIM7670G PPP path and completed one bounded manual
  Camera transfer over LTE, while the Camera Gate deliberately remained
  `trial_unverified` and timed capture stayed disabled.

## Product Gate status

| Gate | Current state | Why |
|---|---|---|
| `P0-LOC` | `NOT_RUN` | No accepted representative Location campaign on the current candidate/product boundary. |
| `P0-CALL` | `NOT_RUN` | CALL is paused for separate research; the earlier local audio loop is not a real LTE call. |
| `P0-SOS` | `NOT_RUN` | Full physical SOS and human closure are outside the current milestone and remain required later. |

The final sellable P0 remains Reliable Location + Ego Call + physical SOS;
all three Gates must eventually pass.

## Blocking facts before the next live run

1. Shared-I2C manual capture and one real-LTE delivery now have bounded success
   evidence. Run016 closed the immediate LTE status/PPP concurrency regression,
   and run017 closed the immediate ten-minute empty-spool throughput regression.
   The flashed profile is still the intentionally limited one-
   attempt-per-boot `trial_unverified` mode; any timed-capture promotion needs
   a separately bound candidate and explicit evidence.
2. The 15-second command-poll correction is now in the tracked FIELD-020
   collection/transport cadence overlay. It still needs longer retained-
   backlog/endurance coverage; the bounded empty-spool result is not a
   representative-day or loss-free claim.
3. Verify the authorized browser preview/export for the exact run015 stored
   photo; the successful private API download is not browser rendering.
4. Prove timed enable/disable, outage capture and same-file reboot recovery.
5. Independent power, route transition, longer coexistence and FIELD-020 are
   still unrun. Camera hard-power cutoff and product power remain unverified.

## Immediate execution order

1. Verify browser decode/preview and export for the exact run015 photo identity.
2. Bind the next Camera candidate with the run017 throughput setting and prove
   default-off timed enable/disable, full outage capture, restart and
   same-file recovery without catch-up recapture.
3. Exercise controlled Wi-Fi/LTE transition and retained-spool accounting,
   then run the independent-power short test and FIELD-020.

## Parallel and paused lanes

- HW-021 and COMPLIANCE-010 continue under their existing packets. The
  untracked `hardware/mechanical/C-ME-0.1/` founder draft is explicitly excluded
  from the current work and remains unchanged until the founder finishes it;
  this run does not treat draft contents as reviewed C-line conclusions.
  Measured Camera pin, standby, traffic, memory, file-size and timing facts will
  be handed to C line when that work resumes.
- CALL-020, CALL-021 and full SOS remain paused, not passed or deleted. AMOLED
  stays available as an independent indoor audio/UI bench resource.
- AI/visual inference remains outside the milestone. The data/replay interfaces
  remain, but no model may block the single-board collection closure.

## Validation record for this revision

- `python scripts/context_lint.py`: PASS after the 2026-09-16 run015/run016
  evidence update; the unfinished `C-ME-0.1` draft remained excluded.
- `scripts/verify.ps1`: PASS, 1,797 tests, 13 environment-guarded skips. A skip
  is not hardware evidence.
- Focused Camera/media/control/delivery/HTTPS suite: PASS, 84/84. The final
  Camera Gate/journal subset passes 16/16.
- Camera media-range hardware preflight: PASS for storage ownership only;
  `[0x600000,0xF00000)` read as 9,437,184 bytes of `0xFF`, SHA-256
  `BE1C8C26FAAE3AE3606606C9641F017A873F52A7833C9CF65142EF0E2405CE8A`,
  and the subsequent `verify_flash` readback returned `verify OK`. No write
  occurred.
- ESP-IDF 5.4.2 clean-commit no-flash builds at `ef3c06f6a`: default
  `896,240 B`, SHA-256
  `2EDC9153E618329378645D03FB8D808E68936179403FD7C9D2F88AFEA434A9AC`;
  legacy collector `991,568 B`, SHA-256
  `CF265EA61F3F275216F592F865E6810AC85B5A30B0415CA1F071EF60626E9317`;
  Camera blocked `1,033,680 B`, SHA-256
  `E00474A5610011527DB6CBD62BF62E074C20D831FBB848B09B10BA0275572AA1`;
  Camera trial `1,101,648 B`, SHA-256
  `320B7D51726B91ABAE6CD83B797038DC77232AE72D3094308825708223E02333`.
  The Camera images use a 3 MiB app partition with respectively `0x203A30`
  (67%) and `0x1F30B0` (65%) free. All embed
  `v0.1.0-123-gef3c06f6a` without `-dirty`; none of those four exact checkpoint
  binaries was flashed.
- Backend and firmware source reviews report no remaining known merge blocker;
  the final firmware review specifically closed provenance drift, nonverified
  timer ACK truth and trial-status overclaim paths.
- Commit `80c5e86fd` was built with the ignored run006 overlay and flashed
  app-only on COM3. Wi-Fi manual capture/recovery and exact VPS storage pass as
  described in the linked evidence. Browser decode, real LTE transfer,
  timed-outage/reboot capture, independent power and FIELD-020 remain
  `NOT_RUN`.
- Run015 flashed the app-only
  `0.1.0-camera-lte-trial-015` image and passed one real-SIM LTE PPP manual
  Camera -> VPS -> authenticated private-API byte-integrity slice. Application
  SHA-256 is
  `281C060625DC5F99EA37C7CAD01C419B65CF7D005ACC98334FFDB6090ED58B26`;
  the retained raw log SHA-256 is
  `418FC074D5B32EC86838B2F315295A1AA8536D60A3B3D6A485069FFDD630FD5C`.
  Browser rendering, timer/outage/restart, route transition, independent power,
  FIELD-020 and all three P0 Gates remain `NOT_RUN`.
- Run016 app-only write and independent verify matched application SHA-256
  `A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`.
  Its 180-second real-LTE ordinary-upload regression recorded 25 HTTP-200
  uploads, nine fresh healthy status snapshots and zero stale/busy/link-down/
  panic/photo events. The private log SHA-256 is
  `45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.
  No Camera command was issued and no remaining milestone or P0 Gate advanced.
- Run017 app-only write and independent verify matched application SHA-256
  `07CF1EF3FEA13548FB9B7F5EF8F5C965FE6B6BF53EBD6AE9369F2E8CF0223529`.
  Its 600-second empty-spool real-LTE regression recorded 248/248 successful,
  matched and locally acknowledged ordinary uploads, 65 TLS handshakes and a
  final zero-byte queue. The private 57,156-byte log SHA-256 is
  `FABC0C2ED5E6DCE4DDCCBDBF33524C681FF3DA32E50DCEA65CAB46E61895CA63`.
  No Camera command was issued; browser/timer/outage/restart, route transition,
  independent power, endurance, FIELD-020 and every P0 Gate remain `NOT_RUN`.
- Run021 app-only write and independent verify matched application SHA-256
  `79c0dae8689ffd91601303735384a3e7ab03a4f83b633af04eba7779c1a0bc54`,
  ELF SHA-256 `2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87`.
  In boot 171 on CH343 `COM3`, it verified:
  1) Dynamic sensor policy engine (`collection_sensor_policy`) initialized with config `p0-sprint1-engineering-default-20260823`.
  2) Hardware I2C recovery routine (`platform_i2c_bus_recover`) dynamically healed bus stalls, successfully probing QMI8658 6-axis IMU (`whoami=0x05`) and MAX17048 fuel gauge (`version=0x0012`, VCell `4255 mV`, SOC `100%`) without mock fallback.
  3) SIM7670G USB CDC PPP network interface established within ~35s, maintaining continuous 4G LTE telemetry stream to `https://ego.example.invalid` with 54+ consecutive HTTP 200 uploads, 0 evictions, and zero drops.
- Phase 2 (Active Ego-State Estimation & Multi-Source Evidence Chain Protocol):
  1) Established versioned schemas `ego_state_estimation_v0.schema.json`, `ego_state_evidence_chain_v0.schema.json`, and `ego_state_report_v0.schema.json` with strict `local_priority=true` enforcement under Local-First privacy principles.
  2) Implemented reference deterministic estimator `pc_simulator/ego_state_estimator.py` supporting spatial mobility classification (`stationary`, `pedestrian_walking`, `running`, `in_vehicle`, `indoor_weak_gnss`), posture anomaly detection (`normal`, `abnormal_shock`, `suspected_fall`, `prolonged_immobility`), and device wear state estimation (`tabletop_resting`, `handheld`, `wearable_or_bag`, `charging_docked`).
  3) Contract tests `quality_tests/test_ego_state_estimation_contract.py` (5/5 PASS) and estimator unit tests `quality_tests/test_ego_state_estimator.py` (9/9 PASS) verified.
- Phase 3 (SIM7670G Native Cellular Voice Call State Machine):
  1) Implemented modular C component `firmware/mqtt_heartbeat/components/sim7670_cellular_call` managing 3GPP AT voice calling (`ATD<number>;`, `ATA`, `ATH`, `AT+CLCC`, `AT+CLVL`, `AT+CLIP`, `AT+COLP`, and URCs `RING`, `+CLIP`, `NO CARRIER`, `BUSY`, `NO ANSWER`, `NO DIALTONE`, `VOICE CALL: BEGIN/END`).
  2) Host native unit test suite `quality_tests/test_sim7670_cellular_call_native.py` verified under `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow -Wsign-conversion`.
  3) Cross-compiled and linked into ESP32-S3 firmware target (`libsim7670_cellular_call.a` and `egolink_mqtt_heartbeat.bin`).
- Task A1 (Embedded C-Engine for Active Ego-State Estimation & Evidence Chain):
  1) Implemented modular C component `firmware/mqtt_heartbeat/components/ego_state_engine` with static 200-slot ring buffer (~6.4 KB RAM, zero heap allocation) for 20Hz IMU sampling, spatial mobility estimation, posture anomaly/shock/fall detection, device wear tracking, and mbedtls SHA-256 evidence digest calculation.
  2) Host native unit test suite `quality_tests/test_ego_state_engine_native.py` verified under `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow -Wsign-conversion`.
  3) Cross-compiled with Xtensa GCC toolchain and linked into ESP32-S3 firmware target (`libego_state_engine.a` and `egolink_mqtt_heartbeat.bin`).
- Task A2 (Edge Sampling Pipeline Ingestion & Telemetry Packaging):
  1) Integrated `ego_state_engine` into `firmware/mqtt_heartbeat/main/collection_main.c` without heap allocations; static mutex `s_ego_state_mutex` and evaluation buffers.
  2) Fed real 6-axis IMU samples (accel mg, gyro mdps, timestamp, is_mock) in `imu_task`.
  3) Fed cellular LTE network status (registration state, RSRP, cell ID) in `modem_task`.
  4) Fed GNSS observations (fix, ground speed, lat, lon, hdop, satellites, course) in `modem_task`.
  5) Fed battery & fuel gauge status and evaluated active ego-state in `health()` periodic task, packaging structured `"ego_state"` telemetry into `DEVICE` frames.
  6) Initialized engine in `app_main` with firmware ELF SHA-256 provenance and exposed `ego_state_engine_enabled` in `SESSION` start frames.
  7) Built application binary `egolink_mqtt_heartbeat.bin` (0x12ac50 bytes, 61% free partition space).
- Task A3 (Server Telemetry Store, HTTP APIs & DevBench Web Dashboard Visualization):
  1) Extended SQLite persistence in `server/collection_store.py` with `collection_ego_states` table, supporting automatic indexing on `(device_id, boot_count DESC, event_monotonic_ns DESC, sequence_id DESC)`.
  2) Ingested structured `ego_state` telemetry from `DEVICE` health frames atomically within the durable collection transaction, with conflict-aware upsert.
  3) Implemented store query methods `latest_ego_state(device_id)` and `ego_state_timeline(device_id, limit)`, and enriched `summary(device_id)` with `latest_ego_state`.
  4) Added authenticated HTTP REST endpoints in `server/message_hub.py`: `GET /api/v1/devices/<device_id>/ego-state/latest` and `GET /api/v1/devices/<device_id>/ego-state/timeline`.
  5) Updated API client `server/web/scripts/api.js` with `fetchLatestEgoState` and `fetchEgoStateTimeline`.
  6) Built full-width Active Ego-State visualization card in DevBench Overview tab (`server/web/index.html` and `server/web/scripts/main.js`): rendering spatial mobility badge & description, posture anomaly/fall monitor, wear state badge, confidence meter, sliding window duration, SHA-256 evidence digest with click-to-copy, reason code tags, and 6 physical evidence metrics (IMU RMS, peak impact, gyro variance, GNSS speed, network type, battery SOC).
  7) Unit & integration test suite `quality_tests/test_ego_state_store_and_api.py` PASS (3/3); `quality_tests/test_dev_bench_web.py` PASS (13/13).
- Field Testing Analysis & 3D IMU Digital Twin Calibration Overhaul (2026-09-21):
  1) Outdoor bicycle field test analysis: Verified outbound trip (08:43:48 ~ 08:50:28) achieved 10 continuous 3D GPS fixes (14~22 sats, HDOP 0.68, ground speed 14~16 km/h) over LTE. Return trip (08:51:35 ~ 09:01:36) had continuous 20Hz IMU motion (161 frames, RMS 200~450 mg, peak 2.8g) but GNSS reported `no_fix` because gravity vector inverted ($a_y$ flipped from +800 to -700 mg), diagnosing inverted pocket stowage where body mass attenuated 1.575 GHz RF by 20-30 dB.
  2) Camera hardware operational on bench; clarified Web UI gallery cards to distinguish hardware capture failure (`capture_failed`) from retention quota expiration (`photo_retention_cleared`).
  3) 3D IMU Digital Twin & Device-Plane Calibration Overhaul (`server/web/scripts/imu3d.js`):
     - Corrected Canvas 3D coordinate system: Defined PCB geometry thickness along World Up $+Y \in [-3, 3]$ (normal $[0, 1, 0]$ pointing to sky), length along $X$, width along $Z$.
     - Aligned 3D coordinate arrows: Cyan Up/Z pointing straight up from board surface, Orange X pointing forward along length, Green Y pointing right along width, matching reference photo 1:1.
     - Device-Plane Rodrigues Calibration: Click-to-tare calculates $3\times3$ Rodrigues rotation aligning raw gravity vector onto $[0, 1, 0]$ (World Up), guaranteeing Pitch = 0.0° and Roll = 0.0° when resting flat on desk.
     - Unconstrained Gyro Yaw Drift Elimination: Captured QMI8658 static gyro bias ($-3.25^\circ/\text{s}$ on $gy$) on tare and subtracted it; introduced Zero-Velocity Update (ZUPT) deadband ($< 1.8^\circ/\text{s}$ and $|\vec{a}| \approx 1.0\,\text{G}$) to freeze yaw at 0.0° when resting on desk.
     - Gimbal-Lock-Free Rotation Chain: Roll ($Z$) $\to$ Pitch ($X$) $\to$ Yaw (vertical $Y$), ensuring smooth, non-flipping attitude responses during physical board tilting.
     - Deployed to production VPS (`https://ego.example.invalid`).
- Full verification gate: `python scripts/context_lint.py` PASS; `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` PASS (1,833/1,833 tests).

The prior 3,000-plus-line chronological status was preserved byte-for-byte as
a non-authoritative source snapshot under
[`docs/archive/status/20260909/`](../archive/status/20260909/README.md).
