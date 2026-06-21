"""Create an Ego Link M1 session recording from a PC Simulator event log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import session_recorder


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LOG = REPO_ROOT / "pc_simulator" / "runtime" / "events.jsonl"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "pc_simulator" / "runtime" / "recordings"


def default_session_id() -> str:
    return "session-" + session_recorder.utc_now().replace(":", "").replace("+", "Z")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write an Ego Link M1 session recording.")
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--json", action="store_true", help="Print output paths and counts as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_id = args.session_id or default_session_id()
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / session_id)
    recording = session_recorder.build_recording_from_log(
        args.event_log,
        session_id=session_id,
        limit=args.limit,
    )
    paths = session_recorder.write_recording(recording, output_dir)
    payload = {
        "ok": True,
        "session_id": session_id,
        "output_dir": str(output_dir),
        "paths": {name: str(path) for name, path in paths.items()},
        "record_counts": recording["manifest"]["record_counts"],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Session recording: {paths['summary']}")
        print(f"Manifest: {paths['manifest']}")
        print(f"Sensor frames: {recording['manifest']['record_counts']['sensor_frames']}")
        print(f"Events: {recording['manifest']['record_counts']['events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
