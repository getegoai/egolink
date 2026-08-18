"""Read-only scan of recent VPS field activity for FT-001B.

Fetches a bounded Message Hub field-export for a recent time window and
summarizes GNSS fix/no_fix timeline, boot continuity, LTE observations, and
any IMU window evidence. Strictly read-only: only GET requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402

DEFAULT_HUB = "http://203.0.113.10:8790"
DEFAULT_DEVICE = "ego-link-r1-connectivity-001"


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def uptime_ms_of(msg: dict[str, Any]) -> int | None:
    ts = msg.get("ts")
    if isinstance(ts, str) and ts.startswith("uptime_ms:"):
        try:
            return int(ts.split(":", 1)[1])
        except ValueError:
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE)
    parser.add_argument("--token-file", default=str(REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"))
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--ended-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    client = HubClient(args.hub, token=token, timeout=180.0)

    export = client.get(
        f"/api/v1/devices/{args.device_id}/field-export"
        f"?started_at={args.started_at}&ended_at={args.ended_at}"
    )
    window = export.get("window") or {}
    msgs = export.get("messages") or []
    cmds = export.get("commands") or []
    frames = export.get("raw_frames") or []

    loc = [
        m for m in msgs
        if isinstance(m, dict) and m.get("event_type") in ("location_report", "location_observation")
    ]
    gnss_rows = [m for m in loc if m.get("event_type") == "location_report"]
    lte_rows = [m for m in loc if m.get("event_type") == "location_observation"]
    fixes = [m for m in gnss_rows if m.get("fix") is True]
    boots = sorted({m.get("boot_count") for m in msgs if isinstance(m.get("boot_count"), int)})


    fix_timeline = []
    for m in fixes:
        fix_timeline.append({
            "seq": m.get("seq"),
            "server_received_at": m.get("server_received_at"),
            "uptime_ms": uptime_ms_of(m),
            "boot_count": m.get("boot_count"),
            "lat": m.get("lat"),
            "lon": m.get("lon"),
        })
    nofix_timeline = []
    for m in gnss_rows:
        if m.get("fix") is not True:
            nofix_timeline.append({
                "seq": m.get("seq"),
                "server_received_at": m.get("server_received_at"),
                "gnss_state": m.get("gnss_state"),
                "boot_count": m.get("boot_count"),
            })

    imu_frames = []
    for f in frames:
        if not isinstance(f, dict):
            continue
        pr = f.get("parse_result") or {}
        dm = pr.get("derived_message") or {}
        if dm.get("event_type") in ("imu_window_chunk", "imu_window_manifest"):
            imu = dm.get("imu_window") or {}
            imu_frames.append({
                "frame_id": f.get("frame_id"),
                "event_type": dm.get("event_type"),
                "window_id": imu.get("window_id"),
                "capture_cmd_id": imu.get("capture_cmd_id"),
                "test_run_id": imu.get("test_run_id"),
                "boot_count": imu.get("boot_count"),
                "server_received_at": f.get("server_received_at"),
            })
    manifests = [x for x in imu_frames if x["event_type"] == "imu_window_manifest"]

    segments = []
    cur = []
    prev_t = None
    for row in fix_timeline:
        t = parse_ts(row["server_received_at"])
        if t is None:
            continue
        if prev_t is not None and (t - prev_t).total_seconds() > 90:
            if cur:
                segments.append(cur)
            cur = []
        cur.append(row)
        prev_t = t
    if cur:
        segments.append(cur)
    seg_summaries = []
    for seg in segments:
        t0 = parse_ts(seg[0]["server_received_at"])
        t1 = parse_ts(seg[-1]["server_received_at"])
        seg_summaries.append({
            "fix_count": len(seg),
            "start": seg[0]["server_received_at"],
            "end": seg[-1]["server_received_at"],
            "duration_s": round((t1 - t0).total_seconds(), 1) if t0 and t1 else None,
            "boots": sorted({r["boot_count"] for r in seg if r["boot_count"] is not None}),
            "uptime_span_ms": (
                (seg[-1]["uptime_ms"] - seg[0]["uptime_ms"])
                if seg[0]["uptime_ms"] is not None and seg[-1]["uptime_ms"] is not None else None
            ),
        })

    summary = {
        "schema_version": "egolink.ft001b_activity_scan.v0.1",
        "read_only": True,
        "window": {
            "started_at": window.get("started_at"),
            "ended_at": window.get("ended_at"),
            "duration_s": window.get("duration_s"),
            "complete": window.get("complete"),
            "truncated": window.get("truncated"),
            "returned": window.get("returned"),
        },
        "counts": {
            "messages": len(msgs),
            "commands": len(cmds),
            "raw_frames": len(frames),
            "gnss_location_reports": len(gnss_rows),
            "lte_observations": len(lte_rows),
            "gnss_fixes": len(fixes),
            "gnss_nofix": len(nofix_timeline),
            "imu_window_frames": len(imu_frames),
            "imu_window_manifests": len(manifests),
        },
        "boot_counts_seen": boots,
        "gnss_states": dict(Counter(str(m.get("gnss_state")) for m in gnss_rows)),
        "fix_segments": seg_summaries,
        "imu_manifests": manifests[:50],
        "first_fix": fix_timeline[0] if fix_timeline else None,
        "last_fix": fix_timeline[-1] if fix_timeline else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if fixes:
        full_path = args.output.with_name("recent_field_export.json")
        full_path.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
        summary["full_export_saved_to"] = str(full_path)
    print(json.dumps({k: v for k, v in summary.items() if k != "imu_manifests"}, ensure_ascii=False, indent=2))
    return 0 if fixes else 1


if __name__ == "__main__":
    raise SystemExit(main())

    client = HubClient(args.hub, token=token, timeout=180.0)

    export = client.get(
        f"/api/v1/devices/{args.device_id}/field-export"
        f"?started_at={args.started_at}&ended_at={args.ended_at}"
    )
    window = export.get("window") or {}
    msgs = export.get("messages") or []
    cmds = export.get("commands") or []
    frames = export.get("raw_frames") or []

    loc = [m for m in msgs if isinstance(m, dict) and m.get("event_type") in ("location_report", "location_observation")]
    gnss_rows = [m for m in loc if m.get("event_type") == "location_report"]
    lte_rows = [m for m in loc if m.get("event_type") == "location_observation"]
    fixes = [m for m in gnss_rows if m.get("fix") is True]
    boots = sorted({m.get("boot_count") for m in msgs if isinstance(m.get("boot_count"), int)})
