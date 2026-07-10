"""Run a bounded preflight for an Ego Link training experiment handoff.

This command checks whether a TRAIN-002 experiment plan plus its TRAIN-001
dataset manifest are ready for a future local/GPU training runner. It does not
train, evaluate, upload, or deploy a model.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_runs"
PREFLIGHT_SCHEMA_VERSION = "egolink.training_run_preflight.v0.1"
PREFLIGHT_BUILDER_VERSION = "train-003.0"


class TrainingRunPreflightError(RuntimeError):
    """Raised when a preflight input cannot be read safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def slug_id(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "unknown"


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrainingRunPreflightError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingRunPreflightError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingRunPreflightError(f"{label} JSON must be an object")
    return payload


def run_id_for(experiment: Mapping[str, Any], dataset: Mapping[str, Any], created_at: str) -> str:
    experiment_id = slug_id(experiment.get("experiment_id") or "experiment")
    dataset_id = slug_id(dataset.get("dataset_id") or "dataset")
    digest = hashlib.sha1(f"{experiment_id}|{dataset_id}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{experiment_id}-preflight-{digest}"


def record_sample(records: list[Any], *, limit: int = 5) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for record in records[:limit]:
        if not isinstance(record, dict):
            continue
        sample.append(
            {
                "record_id": record.get("record_id"),
                "session_id": record.get("session_id"),
                "candidate_type": record.get("candidate_type"),
                "label": record.get("label"),
                "split_name": record.get("split_name"),
                "source_status": record.get("source_status"),
                "source_manifest_hash": record.get("source_manifest_hash"),
            }
        )
    return sample


def count_by(records: list[Any], key: str) -> dict[str, int]:
    values: Counter[str] = Counter()
    for record in records:
        if isinstance(record, dict):
            values[str(record.get(key) or "unknown")] += 1
    return dict(sorted(values.items()))


def synthetic_record_count(records: list[Any]) -> int:
    count = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        source_status = str(record.get("source_status") or "").lower()
        candidate_type = str(record.get("candidate_type") or "").lower()
        if "synthetic" in source_status or "synthetic" in candidate_type:
            count += 1
    return count


def missing_required_record_fields(records: list[Any]) -> dict[str, int]:
    required = ("record_id", "session_id", "label", "split_name", "source_manifest_hash")
    missing: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            missing["invalid_record_object"] += 1
            continue
        for field in required:
            if not record.get(field):
                missing[field] += 1
    return dict(sorted(missing.items()))


def derive_status(
    *,
    experiment: Mapping[str, Any],
    dataset: Mapping[str, Any],
    records: list[Any],
    missing_fields: Mapping[str, int],
    synthetic_records: int,
    allow_synthetic: bool,
) -> str:
    if experiment.get("status") != "ready_for_runner":
        return "blocked_experiment_not_ready"
    if dataset.get("status") != "ready_for_training_handoff":
        return "blocked_dataset_not_ready"
    counts = as_dict(dataset.get("counts"))
    eligible_records = as_int(counts.get("eligible_records"))
    if eligible_records <= 0 or not records:
        return "blocked_no_eligible_records"
    if missing_fields:
        return "blocked_incomplete_dataset_records"
    if synthetic_records and not allow_synthetic:
        return "blocked_synthetic_without_ack"
    return "ready_for_training_runner"


def status_reason(status: str) -> str:
    return {
        "blocked_experiment_not_ready": "experiment_plan_status_is_not_ready_for_runner",
        "blocked_dataset_not_ready": "dataset_manifest_status_is_not_ready_for_training_handoff",
        "blocked_no_eligible_records": "dataset_manifest_has_no_eligible_records",
        "blocked_incomplete_dataset_records": "dataset_records_missing_required_bounded_fields",
        "blocked_synthetic_without_ack": "synthetic_records_require_explicit_allow_synthetic",
        "ready_for_training_runner": "bounded_dataset_and_experiment_handoff_ready",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == "ready_for_training_runner":
        return "Connect a local/GPU runner that consumes this preflight report and writes measured model metrics plus artifact refs."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for dry-run integration, or use reviewed real field/session data."
    if status == "blocked_incomplete_dataset_records":
        return "Rebuild the dataset manifest from reviewed candidates with complete bounded record fields."
    if status == "blocked_dataset_not_ready":
        return "Complete candidate review gates and rebuild the dataset manifest."
    if status == "blocked_experiment_not_ready":
        return "Register a TRAIN-002 experiment plan from a ready dataset manifest."
    return "Fix the named blocker, then rerun the preflight."


def build_preflight_report(
    experiment: Mapping[str, Any],
    dataset: Mapping[str, Any],
    *,
    experiment_plan_ref: str,
    dataset_manifest_ref: str,
    run_id: str,
    created_at: str,
    allow_synthetic: bool,
) -> dict[str, Any]:
    records = as_list(dataset.get("records"))
    missing_fields = missing_required_record_fields(records)
    synthetic_records = synthetic_record_count(records)
    status = derive_status(
        experiment=experiment,
        dataset=dataset,
        records=records,
        missing_fields=missing_fields,
        synthetic_records=synthetic_records,
        allow_synthetic=allow_synthetic,
    )
    split_counts = as_dict(dataset.get("split_counts"))
    label_counts = count_by(records, "label")
    source_status_counts = count_by(records, "source_status")
    dataset_counts = as_dict(dataset.get("counts"))
    experiment_dataset = as_dict(experiment.get("dataset"))
    metrics_plan = as_dict(experiment.get("metrics_plan"))
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "builder_version": PREFLIGHT_BUILDER_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "reason": status_reason(status),
        "experiment": {
            "experiment_id": experiment.get("experiment_id"),
            "status": experiment.get("status"),
            "reason": experiment.get("reason"),
            "model_track": as_dict(experiment.get("model_track")),
            "plan_ref": experiment_plan_ref,
        },
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "reason": dataset.get("reason"),
            "manifest_ref": dataset_manifest_ref,
            "records_total": as_int(dataset_counts.get("records_total")),
            "eligible_records": as_int(dataset_counts.get("eligible_records")),
            "reviewed_training_candidate_records": as_int(
                dataset_counts.get("reviewed_training_candidate_records")
            ),
            "experiment_records_total": as_int(experiment_dataset.get("records_total")),
            "split_counts": split_counts,
            "label_counts": label_counts,
            "source_status_counts": source_status_counts,
            "synthetic_records": synthetic_records,
            "synthetic_allowed_for_dry_run": bool(allow_synthetic),
            "record_sample": record_sample(records),
        },
        "checks": {
            "experiment_ready": experiment.get("status") == "ready_for_runner",
            "dataset_ready": dataset.get("status") == "ready_for_training_handoff",
            "has_eligible_records": as_int(dataset_counts.get("eligible_records")) > 0 and bool(records),
            "required_record_fields": "pass" if not missing_fields else "fail",
            "missing_record_fields": dict(missing_fields),
            "split_counts": split_counts,
            "synthetic_record_policy": "acknowledged" if synthetic_records and allow_synthetic else (
                "blocked" if synthetic_records else "not_present"
            ),
        },
        "runner": {
            "integration": "local_preflight_only",
            "ready_for_training_runner": status == "ready_for_training_runner",
            "training_server_endpoint": None,
            "next_step": next_step(status),
        },
        "metrics_plan": {
            "planned": metrics_plan,
            "measured": {
                "classification": "not_run",
                "operations": "not_run",
                "footprint": "not_run",
                "power": "not_run",
            },
        },
        "gates": {
            "preflight_ready": status == "ready_for_training_runner",
            "dataset_gate": dataset.get("status") or "unknown",
            "experiment_gate": experiment.get("status") or "unknown",
            "synthetic_gate": "acknowledged" if synthetic_records and allow_synthetic else (
                "blocked" if synthetic_records else "not_present"
            ),
            "model_training": "not_run",
            "model_evaluation": "not_run",
            "model_artifact": "not_produced",
            "training_server": "not_integrated",
            "device_deployment": "not_started",
        },
        "next_step": next_step(status),
        "non_claims": [
            "No model training has run.",
            "No model has been evaluated or deployed.",
            "No model weights, model card, or model artifacts are produced.",
            "No training server, GPU runner, private endpoint, or OTA path is integrated.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    dataset = as_dict(payload.get("dataset"))
    experiment = as_dict(payload.get("experiment"))
    runner = as_dict(payload.get("runner"))
    checks = as_dict(payload.get("checks"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Training Run Preflight",
        "",
        f"- Run ID: {payload.get('run_id', 'unknown')}",
        f"- Created at: {payload.get('created_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Experiment: {experiment.get('experiment_id', 'unknown')} ({experiment.get('status', 'unknown')})",
        f"- Dataset: {dataset.get('dataset_id', 'unknown')} ({dataset.get('status', 'unknown')})",
        f"- Eligible records: {dataset.get('eligible_records', 0)}",
        f"- Synthetic records: {dataset.get('synthetic_records', 0)}",
        "",
        "## Checks",
        "",
    ]
    for key, value in sorted(checks.items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines += [
        "",
        "## Runner",
        "",
        f"- Integration: {runner.get('integration', 'unknown')}",
        f"- Ready: {runner.get('ready_for_training_runner', False)}",
        f"- Next step: {runner.get('next_step', 'unknown')}",
        "",
        "## Record Sample",
        "",
    ]
    for record in dataset.get("record_sample", []) or []:
        if isinstance(record, dict):
            lines.append(
                f"- {record.get('record_id', 'unknown')}: {record.get('label', 'unknown')} / "
                f"split {record.get('split_name', 'unknown')} / source {record.get('source_status', 'unknown')}"
            )
    if not dataset.get("record_sample"):
        lines.append("- none")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- Preflight JSON: {paths.get('training_run_preflight_json', 'unknown')}",
        f"- Preflight Markdown: {paths.get('training_run_preflight_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This preflight contains bounded handoff checks only. It does not contain raw candidate records, raw payload bytes, private coordinates, candidate DB files, runtime JSONL logs, private training endpoints, model weights, or measured model metrics.",
        "",
    ]
    return "\n".join(lines)


def write_preflight_report(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_run_preflight.json"
    markdown_path = output_dir / "training_run_preflight.md"
    written = dict(payload)
    written["paths"] = {
        "training_run_preflight_json": str(json_path),
        "training_run_preflight_markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded Ego Link training runner preflight.")
    parser.add_argument("--experiment-plan", type=Path, required=True, help="TRAIN-002 training_experiment_plan.json.")
    parser.add_argument("--dataset-manifest", type=Path, required=True, help="TRAIN-001 training_dataset_manifest.json.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Stable preflight run ID.")
    parser.add_argument("--created-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic-only records for dry-run integration.")
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until preflight is ready.")
    parser.add_argument("--json", action="store_true", help="Print the bounded preflight JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        experiment = load_json(args.experiment_plan, label="experiment plan")
        dataset = load_json(args.dataset_manifest, label="dataset manifest")
        created_at = args.created_at or utc_now()
        run_id = args.run_id or run_id_for(experiment, dataset, created_at)
        payload = build_preflight_report(
            experiment,
            dataset,
            experiment_plan_ref=args.experiment_plan.name,
            dataset_manifest_ref=args.dataset_manifest.name,
            run_id=run_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic,
        )
        written = write_preflight_report(payload, args.output_root / run_id)
    except TrainingRunPreflightError as exc:
        print(f"FAIL training run preflight: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training run preflight: {written['status']}")
        print(f"Report: {written['paths']['training_run_preflight_markdown']}")
        print(f"Next: {written.get('next_step', 'unknown')}")
    if args.require_ready and written.get("status") != "ready_for_training_runner":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
