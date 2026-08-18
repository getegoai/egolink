#!/usr/bin/env bash
# Bounded read-only IMU window export runner for the Ego Link VPS Message Hub.
#
# Usage (remote): bash vps_export_imu_runner.sh <device_id> <test_run_id> [max_frames]
#
# This script:
#   - opens the Message Hub SQLite database in read-only mode (mode=ro +
#     PRAGMA query_only); it never writes the database, restarts the service,
#     or sends device commands;
#   - runs the repository's existing scripts/export_imu_windows.py logic
#     (transferred separately) against the named device/test-run only;
#   - writes the resulting imu_windows.jsonl and manifest under a bounded
#     /tmp directory so an operator can scp them back.
#
# It does NOT modify the deployed Message Hub application.
set -euo pipefail

DEVICE_ID="${1:?device_id required}"
TEST_RUN_ID="${2:?test_run_id required}"
MAX_FRAMES="${3:-1000}"
APP="/opt/egolink-message-hub"
DB="/var/lib/egolink-message-hub/message_hub.db"
EXPORT_TOOL="/tmp/bounded_export_imu_windows.py"
OUT_ROOT="/tmp/egolink-imu-export/${TEST_RUN_ID}"

if [ ! -f "$EXPORT_TOOL" ]; then
  echo "ERROR: $EXPORT_TOOL not found; scp scripts/export_imu_windows.py first" >&2
  exit 2
fi
if [ ! -d "$APP/server" ]; then
  echo "ERROR: $APP/server not found; is the Message Hub deployed?" >&2
  exit 2
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

cd "$APP"
PYTHONPATH="$APP" python3 "$EXPORT_TOOL" \
  --db "$DB" \
  --device-id "$DEVICE_ID" \
  --test-run-id "$TEST_RUN_ID" \
  --output-dir "$OUT_ROOT" \
  --max-frames "$MAX_FRAMES"

echo "EXPORT_OUTPUT_DIR=$OUT_ROOT"
ls -la "$OUT_ROOT"
echo "RUNNER_DONE"