#!/usr/bin/env bash
# EgoLink Message Hub backup: consistent sqlite snapshot + report store.
# Installed at /usr/local/bin/egolink-backup.sh; cron daily 03:30 CST.
# Evidence/task: OPS-001. Restore procedure: docs/operations/VPS_RUNBOOK.md.
set -euo pipefail
umask 077

BACKUP_ROOT=/var/backups/egolink
DB=/var/lib/egolink-message-hub/message_hub.db
REPORTS=/opt/egolink-message-hub/reports
KEEP_DAYS=14
STAMP=$(date +%Y%m%d-%H%M%S)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$BACKUP_ROOT"
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$WORK/message_hub.db'"
else
  python3 - "$DB" "$WORK/message_hub.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
fi

TAR_INPUTS=(-C "$WORK" message_hub.db -C / "${REPORTS#/}")
# private JPEG bytes deliberately stay out of this fixed 14-day archive. Each
# photo has an individual authorization deadline which the live store enforces;
# copying it here would silently extend that retention. A future photo backup
# must provide per-object lifecycle deletion before it may be enabled.
tar -czf "$BACKUP_ROOT/egolink-$STAMP.tar.gz" "${TAR_INPUTS[@]}"

find "$BACKUP_ROOT" -name 'egolink-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "backup ok: $BACKUP_ROOT/egolink-$STAMP.tar.gz"
