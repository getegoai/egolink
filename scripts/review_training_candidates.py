"""List or review Ego Link training-candidate records.

This is DATA-005's bounded review surface. It does not export raw candidate
records, raw payload bytes, private coordinates, DB files, or runtime JSONL logs.
"""

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
    parser = argparse.ArgumentParser(description="List or review Ego Link training-candidate records.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Training-candidate SQLite DB.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum queue items to print.")
    parser.add_argument("--record-id", help="Candidate record ID to review. Omit to list the queue.")
    parser.add_argument(
        "--decision",
        choices=training_candidate_store.REVIEW_ACTIONS,
        help="Review decision for --record-id.",
    )
    parser.add_argument("--reviewer", default="codex", help="Reviewer identifier for audit history.")
    parser.add_argument("--split-name", default="unassigned", help="Dataset split for approve_for_training.")
    parser.add_argument("--split-leakage-checked", action="store_true", help="Confirm session/time/device split review.")
    parser.add_argument("--privacy-reviewed", action="store_true", help="Confirm privacy and consent review.")
    parser.add_argument("--quality-reviewed", action="store_true", help="Confirm quality review.")
    parser.add_argument("--reviewed-at", help="UTC ISO timestamp for deterministic tests.")
    parser.add_argument("--notes", default="", help="Short review note.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.record_id:
        if not args.decision:
            raise SystemExit("--decision is required with --record-id")
        payload = training_candidate_store.review_candidate_record(
            args.db,
            record_id=args.record_id,
            decision=args.decision,
            reviewer=args.reviewer,
            split_name=args.split_name,
            split_leakage_checked=args.split_leakage_checked,
            privacy_reviewed=args.privacy_reviewed,
            quality_reviewed=args.quality_reviewed,
            reviewed_at=args.reviewed_at,
            notes=args.notes,
        )
    else:
        payload = training_candidate_store.candidate_review_queue(args.db, limit=args.limit)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.record_id:
        record = payload["record"]
        print(f"Review: {payload['decision']} {record['record_id']} -> {record['state']}")
        print(f"Training allowed: {record['training_allowed']}")
    else:
        print(f"Review queue: {payload.get('pending_records', 0)} pending")
        for record in payload.get("records", []):
            print(
                f"- {record['record_id']} {record['state']} "
                f"label={record.get('label')} split={record.get('split_name')} "
                f"label_review={record.get('label_review_state')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
