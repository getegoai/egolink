"""Fetch the Aug-17 evening bounded field export and inspect FT-001B readiness."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402

OUT = Path("reports/field_validation/FT-001B-DRY/evening_field_export.json")


def main() -> int:
    token = (REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt").read_text(encoding="utf-8").strip()
    client = HubClient("http://203.0.113.10:8790", token=token, timeout=180.0)
    export = client.get(
        "/api/v1/devices/ego-link-r1-connectivity-001/field-export"
        "?started_at=2026-08-17T09:05:00Z&ended_at=2026-08-17T11:00:00Z"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    w = export["window"]
    msgs = export["messages"]
    print("window complete:", w.get("complete"), "truncated:", w.get("truncated"))
    print("returned:", w.get("returned"))
    print("event_types:", dict(Counter(m.get("event_type") for m in msgs)))
    boots = sorted({m.get("boot_count") for m in msgs if m.get("boot_count") is not None})
    print("boots:", boots)
    lr = [m for m in msgs if m.get("event_type") == "location_report"]
    lo = [m for m in msgs if m.get("event_type") == "location_observation"]
    fix = [m for m in lr if m.get("fix") is True]
    print("location_reports:", len(lr), "fixes:", len(fix), "lte_observations:", len(lo))
    if fix:
        print("first fix:", fix[0]["server_received_at"], "ts:", fix[0].get("ts"),
              "utc:", fix[0].get("utc_date"), fix[0].get("utc_time"),
              "lat:", fix[0].get("lat"), "lon:", fix[0].get("lon"))
        print("last fix:", fix[-1]["server_received_at"], "ts:", fix[-1].get("ts"),
              "utc:", fix[-1].get("utc_date"), fix[-1].get("utc_time"))
        kinds = Counter(
            "uptime" if str(m.get("ts", "")).startswith("uptime_ms:") else "other" for m in fix
        )
        print("fix ts kinds:", dict(kinds))
        sat = [m.get("satellites") for m in fix]
        hdop = [m.get("hdop") for m in fix]
        print("satellites min/max:", min(s for s in sat if s is not None), max(s for s in sat if s is not None))
        print("hdop min/max:", min(h for h in hdop if h is not None), max(h for h in hdop if h is not None))
    # IMU window frames within raw_frames
    imu = 0
    for f in export.get("raw_frames") or []:
        dm = ((f or {}).get("parse_result") or {}).get("derived_message") or {}
        if dm.get("event_type") in ("imu_window_chunk", "imu_window_manifest"):
            imu += 1
    print("imu raw frames in window:", imu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
