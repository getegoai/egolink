"""Run the bounded Ego Link data-flywheel handoff pipeline.

This command composes the existing candidate-store, status, and dataset
manifest builders into one repeatable post-run entry point. It only ingests
recording directories explicitly named with ``--recording-dir``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import training_candidate_store


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "pc_simulator" / "runtime" / "training_candidates" / "training_candidates.db"
DEFAULT_PIPELINE_ROOT = REPO_ROOT / "reports" / "data_flywheel_pipeline"
DEFAULT_DATA_FLYWHEEL_ROOT = REPO_ROOT / "reports" / "data_flywheel"
DEFAULT_DATASET_ROOT = REPO_ROOT / "reports" / "training_datasets"
PIPELINE_SCHEMA_VERSION = "egolink.data_flywheel_pipeline_run.v0.1"
PIPELINE_BUILDER_VERSION = "data-006.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace("+0000", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("T", "-")
    )


def default_run_id(generated_at: str) -> str:
    return f"data-flywheel-pipeline-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def bounded_store_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    recording_dir = summary.get("recording_dir")
    recording_ref = Path(str(recording_dir)).name if recording_dir else None
    return {
        "ok": bool(summary.get("ok")),
        "schema_version": summary.get("schema_version"),
        "recording_ref": recording_ref,
        "session_id": summary.get("session_id"),
        "quality_gate": summary.get("quality_gate"),
        "quality_score": summary.get("quality_score"),
        "annotations": int(summary.get("annotations") or 0),
        "records_written": int(summary.get("records_written") or 0),
        "state_counts": as_dict(summary.get("state_counts")),
        "training_allowed_records": int(summary.get("training_allowed_records") or 0),
        "warnings": list(summary.get("warnings") or []),
    }


def ingest_recordings(
    recording_dirs: list[Path],
    *,
    db_path: Path,
    generated_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ingested: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for recording_dir in recording_dirs:
        try:
            summary = training_candidate_store.store_recording(
                recording_dir,
                db_path,
                generated_at=generated_at,
            )
        except training_candidate_store.CandidateStoreError as exc:
            failed.append(
                {
                    "ok": False,
                    "recording_ref": recording_dir.name,
                    "reason": "recording_ingest_failed",
                    "error_type": type(exc).__name__,
                }
            )
        else:
            ingested.append(bounded_store_summary(summary))
    return ingested, failed


def bounded_data_flywheel_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    candidate_store = dict(as_dict(summary.get("candidate_store")))
    candidate_store.pop("db_path", None)
    review_queue = as_dict(summary.get("review_queue"))
    return {
        "schema_version": summary.get("schema_version"),
        "builder_version": summary.get("builder_version"),
        "run_id": summary.get("run_id"),
        "generated_at": summary.get("generated_at"),
        "status": summary.get("status"),
        "pipeline_stage": summary.get("pipeline_stage"),
        "candidate_store": candidate_store,
        "counts": as_dict(summary.get("counts")),
        "review": as_dict(summary.get("review")),
        "review_queue": {
            "schema_version": review_queue.get("schema_version"),
            "available": bool(review_queue.get("available")),
            "reason": review_queue.get("reason"),
            "pending_records": int(review_queue.get("pending_records") or 0),
            "sample_records": list(review_queue.get("sample_records") or []),
            "available_actions": list(review_queue.get("available_actions") or []),
        },
        "readiness": as_dict(summary.get("readiness")),
        "warnings": list(summary.get("warnings") or []),
        "blockers": list(summary.get("blockers") or []),
        "next_step": summary.get("next_step"),
        "paths": as_dict(summary.get("paths")),
    }


def bounded_manifest_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    records = manifest.get("records") if isinstance(manifest.get("records"), list) else []
    return {
        "schema_version": manifest.get("schema_version"),
        "builder_version": manifest.get("builder_version"),
        "dataset_id": manifest.get("dataset_id"),
        "generated_at": manifest.get("generated_at"),
        "status": manifest.get("status"),
        "reason": manifest.get("reason"),
        "counts": as_dict(manifest.get("counts")),
        "split_counts": as_dict(manifest.get("split_counts")),
        "record_sample": [
            {
                "record_id": record.get("record_id"),
                "session_id": record.get("session_id"),
                "label": record.get("label"),
                "split_name": record.get("split_name"),
                "source_manifest_hash": record.get("source_manifest_hash"),
            }
            for record in records[:5]
            if isinstance(record, dict)
        ],
        "training_server": as_dict(manifest.get("training_server")),
        "paths": as_dict(manifest.get("paths")),
    }


def derive_pipeline_status(
    *,
    recordings_requested: int,
    ingest_failures: list[dict[str, Any]],
    data_flywheel: Mapping[str, Any],
    dataset_manifest: Mapping[str, Any],
) -> str:
    if ingest_failures:
        return "ingest_failed"
    if dataset_manifest.get("status") == "ready_for_training_handoff":
        return "ready_for_training_handoff"

    counts = as_dict(data_flywheel.get("counts"))
    records_total = int(counts.get("records_total") or 0)
    pipeline_stage = str(data_flywheel.get("pipeline_stage") or "")
    if recordings_requested == 0 and records_total == 0 and pipeline_stage in {
        "candidate_store_missing",
        "candidate_store_uninitialized",
    }:
        return "needs_recordings"
    if records_total == 0:
        return "needs_labels"
    review_queue = as_dict(data_flywheel.get("review_queue"))
    if int(review_queue.get("pending_records") or 0) > 0:
        return "needs_review"
    if data_flywheel.get("status") == "needs_review":
        return "needs_review"
    return str(data_flywheel.get("status") or "needs_review")


def next_pipeline_step(status: str) -> str:
    if status == "needs_recordings":
        return "Run a field/session recording, then pass each named recording directory with --recording-dir."
    if status == "needs_labels":
        return "Add annotations to the recorded sessions, then rerun this pipeline."
    if status == "needs_review":
        return "Review pending candidates with scripts/review_training_candidates.py, then rerun this pipeline."
    if status == "ready_for_training_handoff":
        return "Hand the training_dataset_manifest.json to the offline training runner or training-server bridge task."
    if status == "ingest_failed":
        return "Fix the named recording ingest failure and rerun this pipeline."
    return "Continue the next DATA/TRAIN task from the generated status report."


def render_pipeline_markdown(payload: Mapping[str, Any]) -> str:
    data_flywheel = as_dict(payload.get("data_flywheel"))
    dataset = as_dict(payload.get("dataset_manifest"))
    counts = as_dict(data_flywheel.get("counts"))
    dataset_counts = as_dict(dataset.get("counts"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Data Flywheel Pipeline Run",
        "",
        f"- Run ID: {payload.get('run_id', 'unknown')}",
        f"- Generated at: {payload.get('generated_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Recordings requested: {payload.get('recordings_requested', 0)}",
        f"- Recordings ingested: {len(payload.get('recordings_ingested', []) or [])}",
        f"- Candidate records: {counts.get('records_total', 0)}",
        f"- Review queue: {as_dict(data_flywheel.get('review_queue')).get('pending_records', 0)}",
        f"- Dataset manifest: {dataset.get('status', 'unknown')} ({dataset.get('reason', 'unknown')})",
        f"- Eligible records: {dataset_counts.get('eligible_records', 0)}",
        "",
        "## Next Step",
        "",
        str(payload.get("next_step") or "Continue the next data flywheel task."),
        "",
        "## Artifacts",
        "",
        f"- Pipeline JSON: {paths.get('data_flywheel_pipeline_json', 'unknown')}",
        f"- Pipeline Markdown: {paths.get('data_flywheel_pipeline_markdown', 'unknown')}",
        f"- Data flywheel status JSON: {as_dict(data_flywheel.get('paths')).get('data_flywheel_status_json', 'unknown')}",
        f"- Dataset manifest JSON: {as_dict(dataset.get('paths')).get('training_dataset_manifest_json', 'unknown')}",
        "",
        "## Ingested Recordings",
        "",
    ]
    for item in payload.get("recordings_ingested", []) or []:
        lines.append(
            f"- {item.get('recording_ref', 'unknown')}: session {item.get('session_id', 'unknown')}, "
            f"records {item.get('records_written', 0)}, quality {item.get('quality_gate', 'unknown')}"
        )
    if not payload.get("recordings_ingested"):
        lines.append("- none")
    if payload.get("recordings_failed"):
        lines += ["", "## Failed Recordings", ""]
        for item in payload.get("recordings_failed", []) or []:
            lines.append(f"- {item.get('recording_ref', 'unknown')}: {item.get('reason', 'unknown')}")
    lines += ["", "## Non-Claims", ""]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This pipeline report contains bounded counts, review state, lineage summaries, and artifact paths only. It does not contain raw candidate records, raw payload bytes, private coordinates, candidate DB files, or runtime JSONL logs.",
        "",
    ]
    return "\n".join(lines)


def write_pipeline_report(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "data_flywheel_pipeline_run.json"
    markdown_path = output_dir / "data_flywheel_pipeline_run.md"
    written = dict(payload)
    written["paths"] = {
        "data_flywheel_pipeline_json": str(json_path),
        "data_flywheel_pipeline_markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_pipeline_markdown(written), encoding="utf-8")
    return written


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated_at)
    dataset_id = args.dataset_id or f"{run_id}-dataset"
    recording_dirs = list(args.recording_dir or [])

    ingested, ingest_failures = ingest_recordings(
        recording_dirs,
        db_path=args.db,
        generated_at=generated_at,
    )

    flywheel_run_id = f"{run_id}-data-flywheel"
    data_flywheel = training_candidate_store.summarize_candidate_store(
        args.db,
        generated_at=generated_at,
    )
    data_flywheel["run_id"] = flywheel_run_id
    data_flywheel_written = training_candidate_store.write_data_flywheel_status_report(
        data_flywheel,
        args.data_flywheel_output_root / flywheel_run_id,
    )

    manifest = training_candidate_store.build_training_dataset_manifest(
        args.db,
        dataset_id=dataset_id,
        generated_at=generated_at,
    )
    manifest_written = training_candidate_store.write_training_dataset_manifest(
        manifest,
        args.dataset_output_root / str(manifest["dataset_id"]),
    )

    bounded_data_flywheel = bounded_data_flywheel_summary(data_flywheel_written)
    bounded_dataset = bounded_manifest_summary(manifest_written)
    status = derive_pipeline_status(
        recordings_requested=len(recording_dirs),
        ingest_failures=ingest_failures,
        data_flywheel=bounded_data_flywheel,
        dataset_manifest=bounded_dataset,
    )
    payload = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "builder_version": PIPELINE_BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "recordings_requested": len(recording_dirs),
        "recordings_ingested": ingested,
        "recordings_failed": ingest_failures,
        "data_flywheel": bounded_data_flywheel,
        "dataset_manifest": bounded_dataset,
        "next_step": next_pipeline_step(status),
        "non_claims": [
            "No model training has run.",
            "No model has been evaluated or deployed.",
            "No firmware, Message Hub protocol, or on-device inference behavior changed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
        ],
    }
    return write_pipeline_report(payload, args.output_root / run_id)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the bounded Ego Link data-flywheel pipeline.")
    parser.add_argument(
        "--recording-dir",
        action="append",
        type=Path,
        help="Session recording directory to ingest. Can be passed more than once.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Training-candidate SQLite DB.")
    parser.add_argument("--run-id", help="Stable pipeline report directory name.")
    parser.add_argument("--dataset-id", help="Stable dataset manifest ID.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_PIPELINE_ROOT)
    parser.add_argument("--data-flywheel-output-root", type=Path, default=DEFAULT_DATA_FLYWHEEL_ROOT)
    parser.add_argument("--dataset-output-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until dataset handoff is ready.")
    parser.add_argument("--json", action="store_true", help="Print the bounded pipeline JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_pipeline(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Data flywheel pipeline: {payload['status']}")
        print(f"Report: {payload['paths']['data_flywheel_pipeline_markdown']}")
        print(f"Next: {payload['next_step']}")
    if payload.get("recordings_failed"):
        return 1
    if args.require_ready and payload.get("status") != "ready_for_training_handoff":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
