"""One-shot read-only device state check (no polling loop)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402


def main() -> int:
    token = (REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt").read_text(encoding="utf-8").strip()
    client = HubClient("http://203.0.113.10:8790", token=token, timeout=30.0)
    state = client.get("/api/state")
    devs = [d for d in state.get("devices", []) if d.get("device_id") == "ego-link-r1-connectivity-001"]
    d = devs[0] if devs else {}
    hist = client.get("/api/v1/devices/ego-link-r1-connectivity-001/telemetry/history").get("telemetry") or []
    rows = [r for r in hist if isinstance(r, dict)]
    recent = rows[-60:]
    boots = Counter(r.get("boot_count") for r in recent if r.get("boot_count") is not None)
    loc = [r for r in recent if r.get("event_type") in ("location_report", "location_observation")]
    fixes = [r for r in loc if r.get("fix") is True]
    last = recent[-1] if recent else {}
    out = {
        "device_last_seen_at": d.get("last_seen_at"),
        "device_last_seq": d.get("last_seq"),
        "recent_rows": len(recent),
        "recent_boots": dict(boots),
        "recent_loc_events": len(loc),
        "recent_fixes": len(fixes),
        "last_row": {k: last.get(k) for k in ("event_type", "server_received_at", "seq", "boot_count", "ts", "fix", "gnss_state")},
        "last_fix": (
            {k: fixes[-1].get(k) for k in ("server_received_at", "seq", "lat", "lon", "ts")}
            if fixes else None
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
