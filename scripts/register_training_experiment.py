"""Register a bounded training experiment plan from a dataset manifest.

This command is the first training-runner bridge. It does not train, evaluate,
upload, or deploy a model. It records whether a reviewed dataset manifest is
ready for a future runner and which gates still need evidence.
"""

from __future__ import annotations

import argparse
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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_experiments"
TRAINING_EXPERIMENT_PLAN_SCHEMA_VERSION = "egolink.training_experiment_plan.v0.1"
TRAINING_EXPERIMENT_PLAN_BUILDER_VERSION = "train-002.0"
DEFAULT_MODEL_TRACK = "motionnet"
DEFAULT_CANDIDATE_MODEL = "motionnet-v0.1-planned"
DEFAULT_BASELINE_MODEL = "m0_rule_router"


class TrainingExperimentError(RuntimeError):
    """Raised when an experiment plan cannot be built from the input."""


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


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrainingExperimentError(f"cannot read dataset manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingExperimentError(f"dataset manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingExperimentError("dataset manifest JSON must be an object")
    return payload


def experiment_id_for(manifest: Mapping[str, Any], created_at: str) -> str:
    dataset_id = slug_id(manifest.get("dataset_id") or "dataset")
    digest = hashlib.sha1(f"{dataset_id}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{dataset_id}-experiment-{digest}"


def derive_experiment_status(manifest: Mapping[str, Any]) -> tuple[str, str]:
    counts = as_dict(manifest.get("counts"))
    eligible_records = as_int(counts.get("eligible_records"))
    manifest_status = str(manifest.get("status") or "unknown")
    manifest_reason = str(manifest.get("reason") or "dataset_manifest_not_ready")
    if manifest_status != "ready_for_training_handoff":
        return "blocked_dataset_not_ready", manifest_reason
    if eligible_records <= 0:
        return "blocked_no_eligible_records", "ready_manifest_has_no_eligible_records"
    return "ready_for_runner", "reviewed_dataset_manifest_available"


def bounded_record_sample(manifest: Mapping[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for record in as_list(manifest.get("records"))[:limit]:
        if not isinstance(record, dict):
            continue
        sample.append(
            {
                "record_id": record.get("record_id"),
                "session_id": record.get("session_id"),
                "candidate_type": record.get("candidate_type"),
                "label": record.get("label"),
                "split_name": record.get("split_name"),
                "source_manifest_hash": record.get("source_manifest_hash"),
            }
        )
    return sample


def runner_next_command(status: str) -> str:
    if status == "ready_for_runner":
        return (
            "Integrate a local or GPU training runner that consumes this plan and "
            "writes measured metrics, model-card, footprint, and rollback artifacts."
        )
    if status == "blocked_no_eligible_records":
        return "Rebuild the dataset manifest after reviewed training candidates are available."
    return "Complete DATA-005 review gates, then rebuild the dataset manifest and experiment plan."


def build_training_experiment_plan(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
    experiment_id: str | None,
    created_at: str | None,
    model_track: str,
    candidate_model: str,
    baseline_model: str,
) -> dict[str, Any]:
    created = created_at or utc_now()
    resolved_experiment_id = experiment_id or experiment_id_for(manifest, created)
    status, reason = derive_experiment_status(manifest)
    counts = as_dict(manifest.get("counts"))
    ready = status == "ready_for_runner"
    return {
        "schema_version": TRAINING_EXPERIMENT_PLAN_SCHEMA_VERSION,
        "builder_version": TRAINING_EXPERIMENT_PLAN_BUILDER_VERSION,
        "experiment_id": resolved_experiment_id,
        "created_at": created,
        "status": status,
        "reason": reason,
        "dataset": {
            "dataset_id": manifest.get("dataset_id"),
            "manifest_status": manifest.get("status"),
            "manifest_reason": manifest.get("reason"),
            "manifest_ref": manifest_path.name,
            "records_total": as_int(counts.get("records_total")),
            "eligible_records": as_int(counts.get("eligible_records")),
            "reviewed_training_candidate_records": as_int(counts.get("reviewed_training_candidate_records")),
            "split_counts": as_dict(manifest.get("split_counts")),
            "record_sample": bounded_record_sample(manifest),
        },
        "model_track": {
            "track": model_track,
            "candidate_model": candidate_model,
            "baseline_model": baseline_model,
        },
        "runner": {
            "integration": "not_integrated",
            "ready_for_handoff": ready,
            "training_server_endpoint": None,
            "next_command": runner_next_command(status),
        },
        "metrics_plan": {
            "classification": {
                "accuracy": "planned_not_measured",
                "precision": "planned_not_measured",
                "recall": "planned_not_measured",
                "false_positive_rate": "planned_not_measured",
                "confusion_matrix": "planned_not_measured",
            },
            "operations": {
                "latency_ms": "planned_not_measured",
                "ram_bytes": "planned_not_measured",
                "flash_bytes": "planned_not_measured",
                "energy_per_inference": "planned_not_measured",
            },
        },
        "gates": {
            "dataset_ready": ready,
            "privacy_review": "inherited_from_dataset_manifest",
            "consent_review": "inherited_from_dataset_manifest",
            "split_leakage": "inherited_from_dataset_manifest",
            "baseline_comparison": "planned_not_run",
            "footprint": "planned_not_measured",
            "power": "planned_not_measured",
            "rollback_plan": "planned_not_written",
        },
        "non_claims": [
            "No model training has run.",
            "No model has been evaluated or deployed.",
            "No training server or GPU runner is integrated.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
        ],
    }


def render_training_experiment_plan_markdown(plan: Mapping[str, Any]) -> str:
    dataset = as_dict(plan.get("dataset"))
    runner = as_dict(plan.get("runner"))
    model_track = as_dict(plan.get("model_track"))
    metrics_plan = as_dict(plan.get("metrics_plan"))
    gates = as_dict(plan.get("gates"))
    paths = as_dict(plan.get("paths"))
    lines = [
        "# Ego Link Training Experiment Plan",
        "",
        f"- Experiment ID: {plan.get('experiment_id', 'unknown')}",
        f"- Created at: {plan.get('created_at', 'unknown')}",
        f"- Status: {plan.get('status', 'unknown')}",
        f"- Reason: {plan.get('reason', 'unknown')}",
        f"- Dataset: {dataset.get('dataset_id', 'unknown')}",
        f"- Eligible records: {dataset.get('eligible_records', 0)}",
        f"- Model track: {model_track.get('track', 'unknown')}",
        f"- Candidate model: {model_track.get('candidate_model', 'unknown')}",
        f"- Baseline model: {model_track.get('baseline_model', 'unknown')}",
        "",
        "## Runner",
        "",
        f"- Integration: {runner.get('integration', 'unknown')}",
        f"- Ready for handoff: {runner.get('ready_for_handoff', False)}",
        f"- Next command: {runner.get('next_command', 'unknown')}",
        "",
        "## Metrics Plan",
        "",
        f"- Classification: {json.dumps(as_dict(metrics_plan.get('classification')), ensure_ascii=False, sort_keys=True)}",
        f"- Operations: {json.dumps(as_dict(metrics_plan.get('operations')), ensure_ascii=False, sort_keys=True)}",
        "",
        "## Gates",
        "",
    ]
    for name, value in sorted(gates.items()):
        lines.append(f"- {name}: {value}")
    lines += [
        "",
        "## Record Sample",
        "",
    ]
    for record in dataset.get("record_sample", []) or []:
        if isinstance(record, dict):
            lines.append(
                f"- {record.get('record_id', 'unknown')}: {record.get('label', 'unknown')} / "
                f"split {record.get('split_name', 'unknown')}"
            )
    if not dataset.get("record_sample"):
        lines.append("- none")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- Plan JSON: {paths.get('training_experiment_plan_json', 'unknown')}",
        f"- Plan Markdown: {paths.get('training_experiment_plan_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in plan.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This plan contains dataset readiness, bounded record samples, planned metrics, and gate status only. It does not contain raw candidate records, raw payload bytes, private coordinates, candidate DB files, runtime JSONL logs, model weights, or measured model metrics.",
        "",
    ]
    return "\n".join(lines)


def write_training_experiment_plan(plan: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_experiment_plan.json"
    markdown_path = output_dir / "training_experiment_plan.md"
    payload = dict(plan)
    payload["paths"] = {
        "training_experiment_plan_json": str(json_path),
        "training_experiment_plan_markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_training_experiment_plan_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a bounded Ego Link training experiment plan.")
    parser.add_argument("--manifest", type=Path, required=True, help="Training dataset manifest JSON.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--experiment-id", help="Stable experiment ID. Defaults to dataset-derived ID.")
    parser.add_argument("--created-at", help="UTC ISO timestamp for deterministic plans.")
    parser.add_argument("--model-track", default=DEFAULT_MODEL_TRACK, choices=("motionnet", "context_router", "audiogate", "visiongate"))
    parser.add_argument("--candidate-model", default=DEFAULT_CANDIDATE_MODEL)
    parser.add_argument("--baseline-model", default=DEFAULT_BASELINE_MODEL)
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until the experiment is runner-ready.")
    parser.add_argument("--json", action="store_true", help="Print the bounded experiment-plan JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        created_at = args.created_at or utc_now()
        plan = build_training_experiment_plan(
            manifest,
            manifest_path=args.manifest,
            experiment_id=args.experiment_id,
            created_at=created_at,
            model_track=args.model_track,
            candidate_model=args.candidate_model,
            baseline_model=args.baseline_model,
        )
        output_dir = args.output_root / str(plan["experiment_id"])
        written = write_training_experiment_plan(plan, output_dir)
    except TrainingExperimentError as exc:
        print(f"FAIL training experiment plan: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training experiment plan: {written['status']}")
        print(f"Plan: {written['paths']['training_experiment_plan_markdown']}")
        print(f"Reason: {written.get('reason', 'unknown')}")
    if args.require_ready and written.get("status") != "ready_for_runner":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
