"""Export a bounded dataset/experiment handoff manifest from reviewed candidates."""

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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_datasets"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an Ego Link training dataset handoff manifest.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Training-candidate SQLite DB.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dataset-id", help="Stable dataset ID. Defaults to a timestamp-derived ID.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic manifests.")
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero if no eligible records exist.")
    parser.add_argument("--json", action="store_true", help="Print JSON manifest.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    manifest = training_candidate_store.build_training_dataset_manifest(
        args.db,
        dataset_id=args.dataset_id,
        generated_at=generated_at,
    )
    output_dir = args.output_root / str(manifest["dataset_id"])
    written = training_candidate_store.write_training_dataset_manifest(manifest, output_dir)
    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = written.get("counts", {})
        print(f"Dataset manifest: {written['status']}")
        print(f"Manifest: {written['paths']['training_dataset_manifest_markdown']}")
        print(f"Eligible records: {counts.get('eligible_records', 0)}")
        print(f"Reason: {written.get('reason', 'unknown')}")
    if args.require_ready and written.get("status") != "ready_for_training_handoff":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
