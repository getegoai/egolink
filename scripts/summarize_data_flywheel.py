"""Write a bounded Ego Link data-flywheel status report.

The report is a control-plane summary for humans and the Web Dashboard. It
does not export candidate records, raw payload bytes, runtime JSONL logs, or a
training dataset.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import training_candidate_store


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "pc_simulator" / "runtime" / "training_candidates" / "training_candidates.db"
DEFAULT_REPORT_ROOT = REPO_ROOT / "reports" / "data_flywheel"


def timestamp_slug(value: str) -> str:
    safe = (
        value.replace(":", "")
        .replace("-", "")
        .replace("+00:00", "Z")
        .replace("+0000", "Z")
        .replace(".", "")
    )
    return safe.replace("T", "-").replace("Z", "Z")


def default_run_id(generated_at: str) -> str:
    return f"data-flywheel-status-{timestamp_slug(generated_at)[:15]}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the Ego Link data-flywheel control plane.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Training-candidate SQLite DB.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Root directory for status report runs.",
    )
    parser.add_argument("--run-id", default=None, help="Stable report directory name.")
    parser.add_argument("--generated-at", default=None, help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--json", action="store_true", help="Print the status JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    run_id = args.run_id or default_run_id(generated_at)
    output_dir = args.output_root / run_id
    summary = training_candidate_store.summarize_candidate_store(
        args.db,
        generated_at=generated_at,
    )
    summary["run_id"] = run_id
    written = training_candidate_store.write_data_flywheel_status_report(summary, output_dir)
    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = written.get("counts", {})
        print(f"Data flywheel status: {written['status']}")
        print(f"Report: {written['paths']['data_flywheel_status_markdown']}")
        print(f"Sessions: {counts.get('sessions_total', 0)}")
        print(f"Candidate records: {counts.get('records_total', 0)}")
        print(f"Needs review: {counts.get('needs_review_records', 0)}")
        print(f"Model training ready: {written.get('readiness', {}).get('model_training_ready', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
