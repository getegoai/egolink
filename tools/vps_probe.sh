#!/usr/bin/env bash
# Read-only VPS probe for the bounded IMU export slice (FT-001B / A-line).
# It does NOT write to the Message Hub DB, does NOT restart the service, and
# does NOT send any device command. It only inspects layout, python, the
# deployed server module, and counts the named test run's raw frames.
set -euo pipefail

DB="/var/lib/egolink-message-hub/message_hub.db"
APP="/opt/egolink-message-hub"
DEVICE_ID="${1:-ego-link-r1-connectivity-001}"
TEST_RUN_ID="${2:-FT001-FW-20260817-001}"

echo "=== python ==="
python3 --version

echo "=== app layout ==="
ls -la "$APP" || true
echo "=== server module ==="
ls -la "$APP/server" || true

echo "=== db file ==="
ls -la "$DB" || true

echo "=== service ==="
systemctl is-active egolink-message-hub.service || true

echo "=== server module symbols (read-only import) ==="
cd "$APP"
python3 - <<'PY'
import importlib
m = importlib.import_module("server.message_hub")
for name in (
    "IMU_WINDOW_RECORD_BYTES",
    "IMU_WINDOW_SAMPLE_COUNT",
    "IMU_WINDOW_INTERVAL_US",
    "IMU_WINDOW_CHUNK_COUNT",
    "IMU_WINDOW_CONTRACT_VERSION",
    "crc32_hex",
    "initial_raw_frame_record",
    "parse_raw_frame_record",
    "split_raw_frame_bytes",
    "parse_imu_window_kv_payload",
    "validate_imu_window_wire",
):
    print(name, "present=", hasattr(m, name))
PY

echo "=== db counts (read-only) ==="
python3 - "$DB" "$DEVICE_ID" "$TEST_RUN_ID" <<'PY'
import sqlite3, sys
db, device_id, test_run_id = sys.argv[1], sys.argv[2], sys.argv[3]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only = ON")
print("raw_frames_total", con.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0])
print("test_run_raw_frames", con.execute(
    "SELECT COUNT(*) FROM raw_frames WHERE test_run_id = ?", (test_run_id,)
).fetchone()[0])
print("test_run_exists", con.execute(
    "SELECT COUNT(*) FROM test_runs WHERE test_run_id = ?", (test_run_id,)
).fetchone()[0])
print("device_messages_total", con.execute(
    "SELECT COUNT(*) FROM messages WHERE device_id = ?", (device_id,)
).fetchone()[0])
con.close()
PY

echo "PROBE_DONE"