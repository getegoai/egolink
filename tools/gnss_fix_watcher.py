"""Bounded read-only GNSS-fix / session-state watcher for FT-001B.

Polls the VPS Message Hub REST API (never the device, never SQLite, never
serial). It reports, for the named device, whether recent `location_report`
observations carry a real GNSS fix and coordinates, and whether the current
boot is stable and still uploading. It is strictly read-only: it only issues
GET requests and never creates commands, test runs, or writes.

Usage:
    python tools/gnss_fix_watcher.py \
        --device-id ego-link-r1-connectivity-001 \
        --duration-sec 120 --poll-interval-sec 5 \
        [--min-fix-count 2] [--min-gap-s 30]

Output: a bounded JSON report to stdout and an optional file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402

DEFAULT_HUB = "http://203.0.113.10:8790"
DEFAULT_DEVICE = "ego-link-r1-connectivity-001"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def fetch_recent(client: HubClient, device_id: str, limit: int = 200) -> list[dict[str, Any]]:
    history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
    rows = [row for row in history if isinstance(row, dict)]
    return rows[-limit:]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gnss = [
        row for row in rows
        if row.get("event_type") in ("location_report", "location_observation")
    ]
    fixes = [row for row in gnss if row.get("fix") is True or row.get("gnss_fix") is True]
    with_coord = [
        row for row in gnss
        if (row.get("lat") is not None and row.get("lon") is not None)
        or (isinstance(row.get("gnss"), dict) and row["gnss"].get("lat") is not None)
    ]
    boots = sorted({
        row.get("boot_count") for row in gnss if isinstance(row.get("boot_count"), int)
    })
    received = [parse_ts(row.get("server_received_at")) for row in gnss]
    received = [t for t in received if t is not None]
    received.sort()
    span_s = (received[-1] - received[0]).total_seconds() if len(received) >= 2 else 0.0
    last_received = received[-1] if received else None
    age_s = None
    if last_received is not None:
        age_s = (datetime.now(timezone.utc) - last_received).total_seconds()
    latest_boot = boots[-1] if boots else None
    latest_boot_rows = [row for row in gnss if row.get("boot_count") == latest_boot]
    latest_boot_fixes = [
        row for row in latest_boot_rows if row.get("fix") is True or row.get("gnss_fix") is True
    ]
    return {
        "collected_at": utc_now(),
        "gnss_event_count": len(gnss),
        "fix_count": len(fixes),
        "with_coord_count": len(with_coord),
        "boot_counts_seen": boots,
        "latest_boot": latest_boot,
        "latest_boot_fix_count": len(latest_boot_fixes),
        "latest_boot_fix_present": bool(latest_boot_fixes),
        "server_received_span_s": round(span_s, 2),
        "latest_server_received_at": last_received.isoformat() if last_received else None,
        "latest_age_sec": round(age_s, 2) if age_s is not None else None,
        "stable_fix_in_latest_boot": len(latest_boot_fixes) >= 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE)
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--token-file", default=str(REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"))
    parser.add_argument("--duration-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--min-fix-count", type=int, default=2)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    token = os.environ.get(args.token_env) or None
    if token is None and args.token_file and Path(args.token_file).exists():
        token = Path(args.token_file).read_text(encoding="utf-8").strip() or None
    client = HubClient(args.hub, token=token, timeout=30.0)

    deadline = time.monotonic() + args.duration_sec
    samples: list[dict[str, Any]] = []
    fix_ready = False
    while True:
        try:
            rows = fetch_recent(client, args.device_id)
            summary = summarize(rows)
        except Exception as error:  # noqa: BLE001 - bounded report
            summary = {"collected_at": utc_now(), "error": str(error)}
        samples.append(summary)
        if (
            summary.get("latest_boot_fix_present")
            and summary.get("latest_boot_fix_count", 0) >= args.min_fix_count
        ):
            fix_ready = True
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(args.poll_interval_sec)

    report = {
        "schema_version": "egolink.gnss_fix_watcher.v0.1",
        "read_only": True,
        "hub_url": args.hub,
        "device_id": args.device_id,
        "fix_ready": fix_ready,
        "criteria": {"min_fix_count": args.min_fix_count},
        "sample_count": len(samples),
        "latest": samples[-1] if samples else None,
        "samples": samples,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if fix_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())