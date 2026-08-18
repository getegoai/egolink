"""One-shot link/SIM state check for the current boot (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402


def main() -> int:
    token = (REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt").read_text(encoding="utf-8").strip()
    client = HubClient("http://203.0.113.10:8790", token=token, timeout=30.0)
    hist = client.get("/api/v1/devices/ego-link-r1-connectivity-001/telemetry/history").get("telemetry") or []
    rows = [r for r in hist if isinstance(r, dict)]
    # Latest sensor_sample of the newest boot
    ss = [r for r in rows if r.get("event_type") == "sensor_sample"]
    if not ss:
        print("no sensor_sample rows")
        return 1
    latest = ss[-1]
    out = {
        "boot_count": latest.get("boot_count"),
        "seq": latest.get("seq"),
        "server_received_at": latest.get("server_received_at"),
        "link_type": latest.get("link_type"),
        "cell_rat": (latest.get("cell") or {}).get("rat"),
        "cell_registration": (latest.get("cell") or {}).get("registration_state"),
        "cell_reason": (latest.get("cell") or {}).get("reason_code"),
        "sim_state": (latest.get("cell") or {}).get("sim_state"),
        "rssi": (latest.get("cell") or {}).get("rssi"),
        "battery": latest.get("battery"),
        "gnss_state": latest.get("gnss_state"),
        "imu_hw_present": latest.get("imu_hardware_present"),
        "imu_driver_enabled": latest.get("imu_driver_enabled"),
        "imu_latest_uptime_ms": latest.get("imu_latest_uptime_ms"),
        "ts": latest.get("ts"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
