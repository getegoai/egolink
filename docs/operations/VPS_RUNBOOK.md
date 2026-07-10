---
document_status: authoritative
last_verified: 2026-07-03
verified_by: claude
source_task: OPS-001
---

# VPS Message Hub Operations Runbook

Production host: `203.0.113.10` (Rocky Linux 9.8), service
`egolink-message-hub` on port `8790`. This VPS is a real production service:
devices post to it continuously; treat every change as a production change.

## 1. Access

- SSH: key `~/.ssh/egolink_vps_ed25519` as `root@203.0.113.10`. Key auth is
  configured and verified; do not use password login.
- Security recommendations (operator actions, not yet applied):
  1. Rotate the root password (it was shared in a chat channel on
     2026-07-03).
  2. After confirming key access from all needed machines, set
     `PasswordAuthentication no` in `/etc/ssh/sshd_config` and
     `systemctl reload sshd`.
  3. OpenSSH client warns the server is not using post-quantum key exchange;
     consider upgrading openssh-server when Rocky provides it.

## 2. Service Supervision

- Unit: `/etc/systemd/system/egolink-message-hub.service` with
  `Restart=on-failure`, `RestartSec=5`,
  `EnvironmentFile=-/etc/egolink-message-hub.env`, DB at
  `/var/lib/egolink-message-hub/message_hub.db`.
- Status: `systemctl status egolink-message-hub`
- Restart: `systemctl restart egolink-message-hub` (devices tolerate brief
  outages via store-forward/retry, KR-006/007).
- Logs: `journalctl -u egolink-message-hub -e`

## 3. Backup and Restore

- Script: `/usr/local/bin/egolink-backup.sh` (source:
  `scripts/ops/egolink_backup.sh` in the repo). Takes a consistent sqlite
  snapshot (python3 backup API; no sqlite3 CLI on this host) plus the report
  store, writes `/var/backups/egolink/egolink-<stamp>.tar.gz`, keeps 14 days.
- Schedule: cron `30 3 * * *`, output appended to
  `/var/log/egolink-backup.log`.
- Restore procedure (verified 2026-07-03, integrity ok, 8 tables):
  1. `RT=$(mktemp -d /tmp/egolink-restore-XXXX)`
  2. `tar -xzf /var/backups/egolink/egolink-<stamp>.tar.gz -C $RT`
  3. Integrity: `python3 -c "import sqlite3; c=sqlite3.connect('<RT>/message_hub.db'); print(c.execute('PRAGMA integrity_check').fetchone())"`
  4. To restore for real: stop service, copy `message_hub.db` over
     `/var/lib/egolink-message-hub/message_hub.db`, start service, check
     `/health` and Dashboard.
- Off-host copies: backups currently live on the same disk. For disaster
  recovery, periodically `scp` the latest archive to the dev PC (operator
  action; consider automating in OPS-002).

## 4. Liveness Monitoring

- Script: `/usr/local/bin/egolink-healthcheck.sh` (source:
  `scripts/ops/egolink_healthcheck.sh`), cron every 5 minutes.
- Success: refreshes `/var/lib/egolink-message-hub/last_health` (a stale
  timestamp there means the checker itself stopped).
- Failure: appends a `FAIL` line to `/var/log/egolink-health.log`
  (failure-detection path verified 2026-07-03 against a dead port).
- Interpretation: systemd already restarts crashes; repeated FAIL lines with
  an `active` service mean a hang or port problem — restart the service and
  inspect `journalctl -u egolink-message-hub`.
- Escalation to push/SMS notification is future work (OPS-002 candidate).

## 5. Logs and Disk Bounds

- journald capped: `/etc/systemd/journald.conf.d/egolink.conf` sets
  `SystemMaxUse=500M` (vacuumed to ~496M on 2026-07-03).
- Disk: 1.8T total, ~2% used. Check with `df -h /`.
- Report store growth policy: `/opt/egolink-message-hub/reports` is append
  evidence; do not auto-prune. Review manually if it exceeds 10 GB; backup
  rotation (14 days) bounds the backup dir.

## 6. Token Handling

- Runtime token lives only in `/etc/egolink-message-hub.env`
  (`EGOLINK_MESSAGE_HUB_TOKEN=...`), permissions `600 root:root`. Never
  commit it to the repository.
- Rotation: edit the env file with a new value, `systemctl restart
  egolink-message-hub`, then update the same token on the dev PC
  (`$env:EGOLINK_MESSAGE_HUB_TOKEN`) and re-provision firmware config
  (`scripts/prepare_fw001_hw_config.ps1`) before the next flash.

## 7. Deploy

- Standard deploy: `scripts/deploy_message_hub_vps.ps1` from the dev PC
  (uses `EGOLINK_VPS_HOST`, SSH key auth). Deploys server code only; the DB
  and env file are never overwritten by deploys.
- After deploy: check `/health`, Dashboard render, and one authenticated
  `/api/state` call.

## 8. Known Gaps (tracked, not hidden)

- No off-host backup copy yet (operator/OPS-002).
- No outbound alerting (log-file detection only).
- HTTP without TLS; bearer token is the only gate. TLS termination decision
  is deferred (certbot already renews certs on this host for other use —
  reuse candidate for OPS-002).
