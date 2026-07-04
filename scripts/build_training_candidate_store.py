"""Build a local Ego Link training-candidate SQLite store from recordings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import training_candidate_store


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "pc_simulator" / "runtime" / "training_candidates" / "training_candidates.db"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a training-candidate SQLite store from session recordings.")
    parser.add_argument(
        "--recording-dir",
        action="append",
        type=Path,
        required=True,
        help="Session recording directory. Can be passed more than once.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summaries = [
        training_candidate_store.store_recording(recording_dir, args.db)
        for recording_dir in args.recording_dir
    ]
    payload = {
        "ok": True,
        "db_path": str(args.db),
        "recordings": summaries,
        "records_written": sum(int(item["records_written"]) for item in summaries),
        "training_allowed_records": sum(int(item["training_allowed_records"]) for item in summaries),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Training candidate store: {args.db}")
        print(f"Recordings: {len(summaries)}")
        print(f"Records written: {payload['records_written']}")
        print(f"Training allowed records: {payload['training_allowed_records']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
