---
document_status: authoritative
last_verified: 2026-09-02
verified_by: codex
source_task: OPS-002, OPS-004-static-candidate
---

# VPS Message Hub Operations Runbook

Production host: `203.0.113.10` (Rocky Linux 9.8), service
`egolink-message-hub` on port `8790`. This VPS is a real production service:
devices may post to it continuously; treat every change as a production
change. The separately authorized 2026-09-05
[convergence run 001](../development/RUNTIME_CONVERGENCE_20260905_RUN001.md)
deployed the current Location/Guardian code and loopback-only `8790` listener
behind Nginx HTTPS. The deployed virtual host adds a Location-only restriction
keeping SOS routes closed. Initial external checks passed; later SSH/HTTPS
timeouts left the stability window incomplete. Reobserve the live state before
continuing; this does not grant full OPS-004 or device acceptance. The protected
change snapshot is `/var/backups/egolink/convergence-20260905-001`.

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
- Rotation is a separately authorized production action. First prove the
  intended device path validates the certificate chain and exact host, then
  install the new server value, provision the matching device secret through
  an ignored local configuration, verify bounded HTTPS traffic, and revoke the
  old value. Never rotate first and fall back to transmitting either token over
  plaintext. The present SIM7670 path is not eligible because peer verification
  remains unimplemented/unverified.

## 7. Deploy

- Standard deploy: `scripts/deploy_message_hub_vps.ps1` from the dev PC
  (uses `EGOLINK_VPS_HOST`, SSH key auth). The OPS-004 candidate accepts only
  `127.0.0.1`, `::1`, or `localhost`; `-Public` and other listen addresses
  fail before packaging or SSH. It deploys server code only; the DB and env
  file are never overwritten by deploys.
- After deploy: check `/health`, Dashboard render, and one authenticated
  `/api/state` call.

## 8. Domain And HTTPS

The official browser and target device-ingress entry is
`https://ego.example.invalid/`. Nginx owns ports 80 and 443 and proxies only this
virtual host to `127.0.0.1:8790`. In the target configuration, direct port
`8790` is loopback-only and is not a device compatibility endpoint.
Certificate private keys stay under `/etc/letsencrypt` and are never copied
into Git or evidence.

Ordinary plaintext browser requests may redirect, but `/api/`,
`/ws/dashboard`, and the exact AMap coordinate-conversion path on port 80
return `426` without proxying. This makes a mistaken plaintext device/private
location request fail closed; clients must still preflight HTTPS locally
because a credential has already crossed the network by the time a server can
reject it.

The exact AMap coordinate-conversion route disables Nginx access logging on
both the HTTP redirect and HTTPS proxy virtual hosts. Nginx exact-location
matching ignores the query string, so the coordinates still reach the same
redirect/upstream while the request line is not persisted. All other routes
continue to use normal access logging. Preserve this exact-path boundary when
editing the virtual host; do not broaden it to `/_AMapService` or the whole
Dashboard.

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

For changes to the tracked final virtual host, first stage it outside
`/etc/nginx`, include it from a temporary minimal Nginx root configuration, and
run `nginx -t` against that temporary configuration. This validates syntax
without replacing or reloading the live virtual host. Do not use real
coordinates as a smoke-test query and do not inspect or copy historical access
log request lines as part of this check.

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
test "$(curl -sS -o /dev/null -w '%{http_code}' http://ego.example.invalid/api/state)" = 426
curl -fsS https://ego.example.invalid/health
test "$(curl -sS -o /dev/null -w '%{http_code}' https://ego.example.invalid/api/state)" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $EGOLINK_MESSAGE_HUB_TOKEN" \
  https://ego.example.invalid/api/state)" = 200
openssl s_client -connect ego.example.invalid:443 -servername ego.example.invalid \
  -verify_hostname ego.example.invalid -verify_return_error </dev/null 2>/dev/null
ss -lntp | grep '127.0.0.1:8790'
if ss -lntp | grep -E '(^|[[:space:]])(0\.0\.0\.0|\[::\]):8790'; then exit 1; fi
systemctl is-active nginx egolink-message-hub
systemctl is-enabled certbot-renew.timer
systemctl list-timers certbot-renew.timer --no-pager
certbot renew --dry-run
journalctl -u nginx --since '-10 minutes' --no-pager
tail -n 50 /var/log/nginx/error.log
```

Do not include an Authorization header in the HTTP/426 check. Supply the real
token only to the HTTPS request through the environment, never the command
line, report, shell history, or Markdown. Observe for a bounded 10-minute
window: Nginx and service active, no public `8790` listener, authenticated
HTTPS `2xx`, unauthenticated HTTPS `401/403`, plaintext API `426`, and no TLS,
authentication, restart, or outbox-drain errors. Do not inspect request bodies
or copy private access logs into evidence.

### OPS-004 Migration Sequence

This sequence requires a fresh operator authorization. It is documentation,
not evidence that the static candidate has been deployed.

1. Record UTC start/end, current firmware identity, listener/firewall state,
   certificate subject/SAN/issuer/dates, service state, and an existing
   authenticated HTTPS smoke. Do not record token values, lengths, hashes, or
   location bodies.
2. Take the scoped snapshot above, plus `firewall-cmd --list-all` into its
   protected directory. Stage and syntax-check the tracked Nginx configuration
   without reloading it.
3. Deploy the Message Hub with the default loopback listener; do not pass
   `-Public` or a non-loopback `-ListenHost`.
4. Install the reviewed HTTPS virtual host, run `nginx -t`, then reload Nginx.
   Verify HTTPS, exact hostname, authentication, and plaintext `426` before
   changing any device credential.
5. Close any public `8790/tcp` firewall rule only after confirming the service
   is loopback-bound. Re-run the bounded observation commands above.
6. Provision and test an ESP-TLS device candidate separately. Keep SIM7670
   data ingress stopped until CA-chain and hostname verification are actually
   implemented and hardware-observed. Rotate credentials only after every
   allowed sender has a verified TLS path.

### Time-bounded Engineering Fallback

There is no authenticated plaintext or location-data fallback. Before public
`8790` is closed, a modem reachability comparison may issue only a body-free,
token-free `GET /health`; the diagnostic requires an explicit UTC expiry no
more than one hour ahead and labels the result non-production. When the window
ends, stop the diagnostic. Do not reopen `8790` for this check after migration.

Also use an authenticated browser session to confirm the AMap canvas visibly
loads from the HTTPS origin. With no trusted GNSS fix, the canvas must contain
no device marker and must keep the no-fix or pre-correction warning.

### Rollback

If Nginx validation or a post-change gate fails, keep the application on
loopback and restore only a previously working **HTTPS** EgoLink virtual host
from the snapshot. Do not restore or modify the live SQLite DB and do not
reopen public `8790`:

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

If a device TLS candidate fails, stop its ingress attempts and retain pending
records in the bounded outbox. Roll back to a build that leaves this transport
disabled, not to a build that sends bearer credentials or location over
plaintext. Service continuity is subordinate to this privacy boundary.

## 9. Manual SOS Server Candidate (Not Publicly Enabled)

SOS-010D adds a loopback-tested application candidate. Run 001 installed its
shared code as a dependency of the current server, but explicitly denies its
public routes in Nginx; no SOS ingest or device-to-server SOS run occurred.
Do not remove that restriction until the privacy/retention rollout below is
reviewed and authorized. Its exact candidate boundaries are:

- `POST /api/v1/safety-events/manual-sos` requires the configured device-
  ingest bearer token. It accepts at most 1024 exact UTF-8 JSON bytes and only
  the coordinate-free `manual_sos`/`critical`/`device_rule` subset emitted by
  the current device orchestrator. A positive outbox ACK is returned only
  after SQLite accepts or identifies an exact-byte duplicate. The ACK scope is
  only `server_durable_ingest_only`.
- `GET /api/v1/devices/<device-id>/safety-events/manual-sos/latest` and
  `POST /api/v1/devices/<device-id>/safety-events/manual-sos/<event-id>/guardian-ack`
  require a Guardian bearer token whose hashed binding file authorizes that
  exact device. If `EGOLINK_GUARDIAN_BINDINGS_FILE` is absent, these routes
  return unavailable; they never fall back to `EGOLINK_MESSAGE_HUB_TOKEN`.
- Guardian acknowledgement is a separate durable, idempotent fact. It does
  not delete the device outbox record, change the server-ingest ACK or imply a
  successful call. The current UI/API does not send a push notification and
  reports call state as `not_reported`.
- The SQLite timeline retains the exact request body for ACK identity. It is
  excluded from Guardian projections but remains private data in the database
  and backups. This implementation does not add at-rest encryption.

The safety-event field `privacy.retention_seconds=86400` is currently accepted
and persisted as source metadata but is **not enforced** by a deletion job,
backup expiry rule or verified erasure workflow. Do not interpret it as an
implemented 24-hour retention guarantee. Retention/backup propagation,
authorized erasure and at-rest key lifecycle are pre-production privacy
blockers. Do not deploy this candidate until those decisions and a scoped
operator rollout are reviewed.

## 10. Known Gaps (tracked, not hidden)

- No off-host backup copy yet.
- No outbound alerting (log-file detection only).
- Live public-port/firewall state has not been re-observed by OPS-004's static
  work and must be checked before migration.
- SIM7670 CA provisioning, certificate-chain verification, SNI/hostname
  behavior, modem clock prerequisites, and TLS memory/power/reconnect behavior
  remain unimplemented or hardware-unverified. The firmware stops that path.
- Manual SOS push delivery, call signaling, device sender/positive-ACK parser,
  enforced event retention and physical end-to-end SOS evidence are not
  implemented or verified.
