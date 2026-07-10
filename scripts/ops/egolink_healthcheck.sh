#!/usr/bin/env bash
# EgoLink Message Hub liveness check; cron every 5 minutes.
# Installed at /usr/local/bin/egolink-healthcheck.sh.
# Success: refreshes /var/lib/egolink-message-hub/last_health (freshness file).
# Failure: appends a line to /var/log/egolink-health.log.
# systemd Restart=on-failure already recovers crashes; this catches hangs,
# port loss, and reverse-connectivity problems, and leaves an inspectable log.
# Evidence/task: OPS-001. Interpretation: docs/operations/VPS_RUNBOOK.md.

URL="${EGOLINK_HEALTH_URL:-http://127.0.0.1:8790/health}"
LOG=/var/log/egolink-health.log
STATE=/var/lib/egolink-message-hub/last_health

if curl -fsS -m 10 "$URL" >/dev/null 2>&1; then
  date -u +"%Y-%m-%dT%H:%M:%SZ ok" > "$STATE"
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) FAIL $URL" >> "$LOG"
fi
