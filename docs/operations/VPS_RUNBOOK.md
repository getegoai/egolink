---
document_status: authoritative
last_verified: 2026-08-12
verified_by: codex
source_task: OPS-002
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
  action; consider automating in a future operations task).

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
- Escalation to push/SMS notification is a future operations task.

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

## 8. Domain And HTTPS

The official browser entry is `https://ego.example.invalid/`. Nginx owns ports 80
and 443 and proxies only this virtual host to `127.0.0.1:8790`; direct port
`8790` remains available for current device compatibility. Certificate private
keys stay under `/etc/letsencrypt` and are never copied into Git or evidence.

### Preflight And Snapshot

Before changing the VPS, confirm public DNS points only to the intended host,
Nginx owns the public ports, and no existing virtual host claims the name:

```bash
getent ahostsv4 ego.example.invalid
ss -lntp | grep -E ':(80|443|8790)[[:space:]]'
nginx -T 2>&1 | grep -n 'ego.example.invalid\|listen 80\|listen 443'
systemctl is-active nginx egolink-message-hub
```

Create a change-local snapshot without copying secrets into terminal output:

```bash
stamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot=/var/backups/egolink/ops002-$stamp
install -d -m 700 "$snapshot"
nginx -T >"$snapshot/nginx.rendered.conf" 2>"$snapshot/nginx.test.stderr"
if test -e /etc/nginx/conf.d/ego.example.invalid.conf; then
  cp -a /etc/nginx/conf.d/ego.example.invalid.conf "$snapshot/"
  touch "$snapshot/had-existing-vhost"
fi
cp -a /opt/egolink-message-hub/server/message_hub.py "$snapshot/"
cp -a /etc/systemd/system/egolink-message-hub.service "$snapshot/"
systemctl show egolink-message-hub nginx \
  -p ActiveState -p SubState -p MainPID -p NRestarts >"$snapshot/service-state.txt"
printf '%s\n' "$snapshot"
```

### First Certificate And Virtual Host

Copy only the tracked bootstrap file, validate, and reload. Then issue one
certificate through the bounded webroot and replace the bootstrap with the
tracked HTTPS file:

```bash
install -d -o root -g root -m 755 /var/www/letsencrypt/.well-known/acme-challenge
install -o root -g root -m 644 \
  /tmp/ego.example.invalid.bootstrap.conf \
  /etc/nginx/conf.d/ego.example.invalid.conf
nginx -t
systemctl reload nginx
certbot certonly --webroot -w /var/www/letsencrypt \
  --cert-name ego.example.invalid -d ego.example.invalid \
  --key-type ecdsa --non-interactive --agree-tos
install -o root -g root -m 644 \
  /tmp/ego.example.invalid.conf \
  /etc/nginx/conf.d/ego.example.invalid.conf
install -o root -g root -m 755 \
  /tmp/10-egolink-nginx-reload.sh \
  /etc/letsencrypt/renewal-hooks/deploy/10-egolink-nginx-reload.sh
nginx -t
systemctl reload nginx
```

This host reuses its existing Certbot account; never place the account contact
address or account files in the repository. The tracked final virtual host references the
standard `/etc/letsencrypt/live/ego.example.invalid/` symlinks, so renewals do not
require a config rewrite. The tracked deploy hook validates Nginx before every
post-renewal reload.

### Acceptance And Renewal

Run these after the reload. Supply the bearer token only through the shell
environment and do not echo it:

```bash
curl -fsSI http://ego.example.invalid/ | grep -i '^location: https://ego.example.invalid/'
curl -fsS https://ego.example.invalid/health
test "$(curl -sS -o /dev/null -w '%{http_code}' https://ego.example.invalid/api/state)" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $EGOLINK_MESSAGE_HUB_TOKEN" \
  https://ego.example.invalid/api/state)" = 200
openssl s_client -connect ego.example.invalid:443 -servername ego.example.invalid \
  </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
systemctl is-active nginx egolink-message-hub
systemctl is-enabled certbot-renew.timer
systemctl list-timers certbot-renew.timer --no-pager
certbot renew --dry-run
journalctl -u nginx --since '-10 minutes' --no-pager
tail -n 50 /var/log/nginx/error.log
```

Also use an authenticated browser session to confirm the AMap canvas visibly
loads from the HTTPS origin. With no trusted GNSS fix, the canvas must contain
no device marker and must keep the no-fix or pre-correction warning.

### Rollback

If Nginx validation or a post-change gate fails, restore only the EgoLink
virtual host from the snapshot. Do not restore or modify the live SQLite DB:

```bash
if test -e "$snapshot/had-existing-vhost"; then
  cp -a "$snapshot/ego.example.invalid.conf" /etc/nginx/conf.d/ego.example.invalid.conf
else
  rm -f /etc/nginx/conf.d/ego.example.invalid.conf
fi
nginx -t
systemctl reload nginx
```

If the application deployment also needs rollback, restore only
`message_hub.py` and its unit snapshot, run `systemctl daemon-reload`, and
restart `egolink-message-hub`. An issued certificate may remain safely in
place for later reuse; deleting it is not part of routine rollback.

## 9. Known Gaps (tracked, not hidden)

- No off-host backup copy yet.
- No outbound alerting (log-file detection only).
- The device compatibility endpoint on public port `8790` remains HTTP until
  firmware migration to the HTTPS domain is explicitly planned and validated.
