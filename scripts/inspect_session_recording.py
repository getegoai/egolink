"""Inspect an Ego Link M1 session recording directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import session_inspector


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an Ego Link M1 session recording.")
    parser.add_argument("recording_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print the quality report as JSON.")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write session_quality_report.json/.md files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = session_inspector.inspect_recording(args.recording_dir)
    if not args.no_write:
        session_inspector.write_report(report, args.output_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        summary = report["summary"]
        print(
            f"{status} quality_score={report['quality_score']} "
            f"errors={summary['errors']} warnings={summary['warnings']}"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
