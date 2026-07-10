"""Run the Ego Link P0 minimal safety loop demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import minimal_safety_demo


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = REPO_ROOT / "pc_simulator" / "runtime" / "demo_v0_1"


def default_session_id() -> str:
    return "demo-v0-1-" + minimal_safety_demo.utc_now().replace(":", "").replace("+", "Z")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a demo-first Ego Link safety loop.")
    parser.add_argument("--source", type=Path, default=None, help="Optional board JSONL capture to seed the motion event.")
    parser.add_argument(
        "--response",
        choices=sorted(minimal_safety_demo.VALID_RESPONSES),
        default="safe",
        help="Simulated user response until AMOLED touch confirmation is wired in.",
    )
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--event-log", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_id = args.session_id or default_session_id()
    event_log = args.event_log or (DEFAULT_RUNTIME / f"{session_id}.events.jsonl")
    output_dir = args.output_dir or (DEFAULT_RUNTIME / "recordings" / session_id)
    result = minimal_safety_demo.run_demo(
        source_path=args.source,
        event_log=event_log,
        recording_dir=output_dir,
        session_id=session_id,
        user_response=args.response,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(f"{status} minimal safety demo session={session_id}")
        print(f"Event log: {result['event_log']}")
        print(f"Recording: {result['recording_dir']}")
        print(f"Quality: {result['quality_report']['path']}")
        print(f"Response: {result['response']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
