# Legacy Wi-Fi private-data and collection-spool purge

Date: 2026-09-09
Operator authority: founder instruction in the current session to back up the
old Wi-Fi data and spool inside the project, then clear them.

## Board operation

- Board: `connectivity-node-001`, ESP32-S3 rev v0.2, MAC
  `02:00:00:00:00:03`, CH343 serial `5B91047400` on the observed `COM3` path.
- Physical flash reported by the chip: 16 MiB.
- The partition table read from the device identified `ego_collection` at
  `0x122000`, size `0xD2000` (860,160 bytes), ending immediately before
  `ego_outbox` at `0x1F4000`.
- A final pre-clear readback was stored at the private, Git-ignored path
  `.local_backups/wifi_spool_20260909-120744/`; it is 860,160 bytes with
  SHA-256
  `60DDF6B171B7C1D282AC501CED00CAD66C2C434B1923B7C509B307E3E724E33C`.
- Only `erase_region 0x122000 0xD2000` was issued. NVS, the application image,
  and `ego_outbox` were outside that range and were not targeted.
- The complete post-clear readback is 860,160 bytes of `0xFF`, with SHA-256
  `A1D8E738601EB1FF6B5DE4B6944F95ED9C3A1E5DA9A3448BA367F46B96ADF580`.
- The device was deliberately left in the ROM bootloader after verification,
  so the retained legacy collector cannot immediately recreate old-format
  Wi-Fi records. No firmware image was flashed and no SIM traffic was used.

## Project-local private collection files

The 23 `private_*` files under collection runs 002 through 006 were copied to
the same ignored backup tree with their relative paths, byte lengths, and
individual SHA-256 hashes. All source/destination hashes matched. Their total
size was 25,939,498 bytes. The originals were then removed from `reports/`.
Public run metadata, audit material, and summaries were retained; the retained
files contain no `ssid` or `bssid` field names under a case-insensitive scan.

The private backup manifest is
`.local_backups/wifi_spool_20260909-120744/manifest.json`. It is intentionally
excluded from Git and contains no Message Hub token, `.env`, SSH key, or new
photo. Recovery remains possible from this local backup.

## VPS database and historical backups

The project SSH key was subsequently located and matched the running VPS. The
authoritative database was `/var/lib/egolink-message-hub/message_hub.db`; its
pre-operation SQLite `quick_check` was `ok`. Before deletion, a consistent
SQLite backup and the three daily archives that could contain the affected
records were copied into the same private, Git-ignored project backup tree:

- `message_hub_before_purge.db.gz`: 65,122,185 bytes, SHA-256
  `5D04453C2D586616207E45CA4C36A7B53A3BD2BB73D93D8F6D42CC52B0CAFAD4`;
  its decompressed stream was 1,129,299,968 bytes and matched the remote
  pre-purge SQLite backup SHA-256
  `BBD3B981CD1CCF62DDE4A0495A384770E08E68835FE74BB9C28F72C0F98A441E`.
- `egolink-20260907-033001.tar.gz`: 63,273,694 bytes, SHA-256
  `4A362701BE19DB0B814FDE20D5741D205E30C1B76223A1686455FA6F87349874`.
- `egolink-20260908-033001.tar.gz`: 63,849,309 bytes, SHA-256
  `CDF83E6E063C36AF5687E1ECAA4DCF037F82FA30D804E9B13B8E39FD0AA0081E`.
- `egolink-20260909-033001.tar.gz`: 64,415,445 bytes, SHA-256
  `EC2523F0D5FE6F89380586314FE6F2B1BFDD594529553C47D423B66A1F88F2F8`.

With the service stopped, the target was frozen and fail-closed at exactly 81
`collection_records` rows for device `ego-link-001`, source `wifi`, firmware
`0.1.0-collection-v1`, and config
`collector-v1-20hz-gnss5s-cell10s`. The sanitized candidate removed those 81
records, 82 associated delivery attempts and 81 associated raw frames. It then
passed zero-target, zero-structured-`ssid`/`bssid`, foreign-key and SQLite
integrity checks and was vacuumed before atomically replacing the live file.
No other device or collection source was selected for deletion.

The service restarted successfully and `/health` returned `ok=true`. The live
database then reported 3,912 collection records, 61,713 raw frames and 3,914
delivery attempts, with zero remaining target Wi-Fi records and
`quick_check=ok`. A sanitized remote recovery point is retained at
`/var/backups/egolink/privacy-clean-20260909-123808/`; its compressed database
is 46,736,345 bytes with SHA-256
`4CA540EB094652572F948BB9E4D0801F05E99E489D6DE9063B40B3A96F3DFC86`.

After the local hashes were rechecked, the remote pre-purge database copies and
the three named daily archives were removed. The purge report was copied into
the ignored local backup and retained beside the sanitized remote recovery
point. No wildcard or broad database deletion was used.
