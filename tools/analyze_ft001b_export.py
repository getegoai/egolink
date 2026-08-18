"""Read-only analysis of the saved FT-001B field export (boot/timeline/IMU)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

EXPORT = Path("reports/field_validation/FT-001B-DRY/recent_field_export.json")


def main() -> None:
    data = json.loads(EXPORT.read_text(encoding="utf-8"))
    msgs = data["messages"]
    print("event_types:", dict(Counter(m.get("event_type") for m in msgs)))

    boot_rows = [
        (m.get("server_received_at"), m.get("boot_count"), m.get("event_type"), m.get("seq"))
        for m in msgs
        if m.get("boot_count") is not None
    ]
    print("boot_rows:", len(boot_rows))
    prev = None
    transitions = []
    for row in boot_rows:
        if prev is not None and row[1] != prev[1]:
            transitions.append({"from": list(prev), "to": list(row)})
        prev = row
    print("boot_transitions:", json.dumps(transitions, ensure_ascii=False, indent=2))

    # Time range of each boot
    boots = {}
    for t, b, e, s in boot_rows:
        boots.setdefault(b, []).append(t)
    for b in sorted(boots):
        ts = sorted(boots[b])
        print(f"boot {b}: first={ts[0]} last={ts[-1]} rows={len(ts)}")

    # location_report rows: do they carry boot_count / uptime?
    lr = [m for m in msgs if m.get("event_type") == "location_report"]
    print(
        "location_report boot_count_present:",
        sum(1 for m in lr if m.get("boot_count") is not None),
        "/", len(lr),
    )
    print(
        "location_report uptime_ts_present:",
        sum(1 for m in lr if isinstance(m.get("ts"), str) and m["ts"].startswith("uptime_ms:")),
        "/", len(lr),
    )
    # sample one location_report with fix
    for m in lr:
        if m.get("fix") is True:
            keys = sorted(m.keys())
            print("fix_row_keys:", keys)
            print(
                "fix_row_sample:",
                json.dumps(
                    {k: m.get(k) for k in ("seq", "server_received_at", "ts", "boot_count", "lat", "lon", "fix", "gnss_state", "fw_version", "test_run_id")},
                    ensure_ascii=False,
                ),
            )
            break


if __name__ == "__main__":
    main()
