"""Replay an Ego Link M1 session recording through Safety Companion M0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import session_replay


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay an Ego Link M1 session recording.")
    parser.add_argument("recording_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print the replay report as JSON.")
    parser.add_argument("--no-write", action="store_true", help="Do not write session_replay_report.json/.md files.")
    parser.add_argument(
        "--allow-failed-quality",
        action="store_true",
        help="Replay even when the recording quality gate fails.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = session_replay.replay_recording(
        args.recording_dir,
        require_quality=not args.allow_failed_quality,
    )
    if not args.no_write:
        session_replay.write_report(report, args.output_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        summary = report["summary"]
        print(
            f"{status} replayed_inputs={summary['replayed_inputs']} "
            f"safety_events={summary['safety_events']} skipped={summary['skipped_records']}"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
