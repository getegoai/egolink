"""CLI wrapper for the Ego Link dual-board PC bridge PoC."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import board_bridge


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LOG = REPO_ROOT / "pc_simulator" / "runtime" / "events.jsonl"


def parse_source(value: str) -> tuple[str, Path | str]:
    label, separator, path = value.partition("=")
    if not separator or not label or not path:
        raise argparse.ArgumentTypeError("source must use LABEL=PATH, for example wearable=wearable.jsonl")
    return label, path if path == "-" else Path(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize dual-board JSONL messages into the PC Simulator event log.")
    parser.add_argument(
        "--source",
        action="append",
        type=parse_source,
        required=True,
        help="Input source as LABEL=PATH. Use '-' for stdin. May be repeated.",
    )
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--json", action="store_true", help="Print result summary as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = {
        label: board_bridge.read_source_lines(path)
        for label, path in args.source
    }
    result = board_bridge.consume_named_sources(sources, args.event_log, errors=sys.stderr)
    payload = {
        "ok": True,
        "event_log": str(args.event_log),
        "stored_events": result.stored_events,
        "generated_commands": result.generated_commands,
        "skipped_lines": result.skipped_lines,
        "devices": result.devices,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Board bridge wrote {result.stored_events} event(s) to {args.event_log}")
        print(f"Generated commands: {result.generated_commands}")
        if result.devices:
            for role, device_id in result.devices.items():
                print(f"{role}: {device_id}")
    return 0 if result.skipped_lines == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
