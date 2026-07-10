"""Create a bounded training job plan from a TRAIN-007 handoff bundle.

This command is the next dry-run bridge toward a future local/GPU runner or
training server. It reads one explicit training_handoff_bundle.json and writes
a job plan with refs, gates, and planned metrics. It does not call a server,
train a model, copy feature rows, or produce model artifacts.
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

from scripts import build_training_handoff_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_jobs"
JOB_SCHEMA_VERSION = "egolink.training_job_plan.v0.1"
JOB_BUILDER_VERSION = "train-008.0"
READY_JOB_STATUS = "ready_for_runner_queue"
SYNTHETIC_JOB_STATUS = "synthetic_runner_queue_dry_run_only"


class TrainingJobPlanError(RuntimeError):
    """Raised when a training job input cannot be read safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def bounded_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TrainingJobPlanError(f"cannot hash input file: {path}") from exc
    return digest.hexdigest()


def input_ref(path: Path) -> dict[str, Any]:
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise TrainingJobPlanError(f"cannot stat input file: {path}") from exc
    return {
        "ref": bounded_path(path),
        "sha256": sha256_file(path),
        "bytes": size_bytes,
        "content_copied": False,
    }


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrainingJobPlanError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingJobPlanError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingJobPlanError(f"{label} JSON must be an object")
    return payload


def job_id_for(handoff: Mapping[str, Any], created_at: str) -> str:
    handoff_id = slug_id(handoff.get("handoff_id") or "handoff")
    digest = hashlib.sha1(f"{handoff_id}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{handoff_id}-job-{digest}"


def synthetic_handoff_seen(handoff: Mapping[str, Any]) -> bool:
    checks = as_dict(handoff.get("checks"))
    return (
        handoff.get("status") == build_training_handoff_bundle.SYNTHETIC_HANDOFF_STATUS
        or checks.get("synthetic_input_seen") is True
        or checks.get("synthetic_policy") == "acknowledged"
    )


def derive_status(handoff: Mapping[str, Any], *, allow_synthetic: bool) -> str:
    status = handoff.get("status")
    synthetic = synthetic_handoff_seen(handoff)
    if synthetic:
        return SYNTHETIC_JOB_STATUS if allow_synthetic else "blocked_synthetic_without_ack"
    if status != build_training_handoff_bundle.READY_HANDOFF_STATUS:
        return "blocked_handoff_not_ready"
    return READY_JOB_STATUS


def status_reason(status: str) -> str:
    return {
        READY_JOB_STATUS: "reviewed_handoff_ready_for_future_runner_queue",
        SYNTHETIC_JOB_STATUS: "synthetic_handoff_bound_for_runner_queue_dry_run_only",
        "blocked_synthetic_without_ack": "synthetic_handoff_requires_explicit_allow_synthetic",
        "blocked_handoff_not_ready": "handoff_bundle_is_not_ready_for_training_server_handoff",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == READY_JOB_STATUS:
        return "Implement a real local/GPU runner that consumes this job plan and writes reviewed metrics plus artifact refs."
    if status == SYNTHETIC_JOB_STATUS:
        return "Use this plan only to dry-run runner queue wiring, then rebuild from reviewed real field/session rows."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for dry-run integration, or provide a reviewed real handoff bundle."
    return "Fix the handoff blocker, then recreate the training job plan."


def build_job_plan(
    handoff: Mapping[str, Any],
    *,
    handoff_ref: Mapping[str, Any],
    job_id: str,
    created_at: str,
    allow_synthetic: bool,
    model_track: str,
    candidate_model: str,
    baseline_model: str,
    runner_profile: str,
) -> dict[str, Any]:
    status = derive_status(handoff, allow_synthetic=allow_synthetic)
    dataset = as_dict(handoff.get("dataset"))
    feature_manifest = as_dict(handoff.get("feature_manifest"))
    feature_rows = as_dict(handoff.get("feature_rows"))
    baseline = as_dict(handoff.get("baseline_eval"))
    training_server = as_dict(handoff.get("training_server"))
    gates = as_dict(handoff.get("gates"))
    synthetic = synthetic_handoff_seen(handoff)
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "builder_version": JOB_BUILDER_VERSION,
        "job_id": job_id,
        "created_at": created_at,
        "status": status,
        "reason": status_reason(status),
        "source_handoff": {
            "handoff_id": handoff.get("handoff_id"),
            "status": handoff.get("status"),
            "ref": dict(handoff_ref),
        },
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "eligible_records": as_int(dataset.get("eligible_records")),
            "split_counts": as_dict(dataset.get("split_counts")),
        },
        "feature_input": {
            "feature_set_id": feature_manifest.get("feature_set_id"),
            "feature_manifest_status": feature_manifest.get("status"),
            "feature_scope": feature_manifest.get("feature_scope"),
            "row_count": as_int(feature_rows.get("row_count")),
            "row_contents_copied": False,
            "raw_rows_exposed": False,
            "target_separated_from_features": feature_manifest.get("target_separated_from_features", False),
        },
        "model_plan": {
            "model_track": model_track,
            "candidate_model": candidate_model,
            "baseline_model": baseline_model,
            "task_type": "classification",
            "baseline_eval_id": baseline.get("eval_id"),
            "baseline_metric_scope": baseline.get("metric_scope"),
            "product_performance_claim": False,
        },
        "runner_plan": {
            "runner_profile": runner_profile,
            "queue_state": "plan_only",
            "training_server_integration": "not_configured",
            "training_server_endpoint": None,
            "inherits_handoff_training_server_state": training_server.get("integration", "not_configured"),
            "bundle_ready_for_future_runner": status == READY_JOB_STATUS,
            "dry_run_only": status == SYNTHETIC_JOB_STATUS,
            "uses_feature_row_refs_only": True,
        },
        "metrics_plan": {
            "classification": {
                "accuracy": "planned_not_measured",
                "false_positive_rate": "planned_not_measured",
                "recall": "planned_not_measured",
            },
            "operations": {
                "latency_ms": "planned_not_measured",
                "ram_bytes": "planned_not_measured",
                "flash_bytes": "planned_not_measured",
            },
            "power": {
                "energy_per_inference": "planned_not_measured",
                "sleep_vs_inference_delta": "planned_not_measured",
            },
        },
        "checks": {
            "handoff_ready": handoff.get("status") == build_training_handoff_bundle.READY_HANDOFF_STATUS,
            "handoff_gate": gates.get("training_handoff"),
            "synthetic_input_seen": synthetic,
            "synthetic_policy": "acknowledged" if synthetic and allow_synthetic else (
                "blocked" if synthetic else "not_present"
            ),
            "row_contents_copied": False,
            "private_endpoint_exposed": False,
        },
        "gates": {
            "training_job": "pass" if status == READY_JOB_STATUS else (
                "dry_run_only" if status == SYNTHETIC_JOB_STATUS else "blocked"
            ),
            "model_training": "not_run",
            "model_artifact": "not_produced",
            "model_card": "not_produced",
            "training_server": "not_integrated",
            "model_registry": "not_integrated",
            "device_deployment": "not_started",
            "release_claim": "not_allowed",
        },
        "next_step": next_step(status),
        "non_claims": [
            "No model training has run.",
            "No training server, private endpoint, model registry, or OTA path is integrated.",
            "No model weights, model card, or model artifacts are produced.",
            "Feature-row JSONL contents are not copied into this job plan.",
            "No real-world model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
            "No firmware, public protocol, Message Hub ingest, OTA, or on-device inference behavior changed.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    paths = as_dict(payload.get("paths"))
    dataset = as_dict(payload.get("dataset"))
    feature_input = as_dict(payload.get("feature_input"))
    runner = as_dict(payload.get("runner_plan"))
    lines = [
        "# Ego Link Training Job Plan",
        "",
        f"- Job ID: {payload.get('job_id', 'unknown')}",
        f"- Created at: {payload.get('created_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Dataset: {dataset.get('dataset_id', 'unknown')}",
        f"- Feature rows: {feature_input.get('row_count', 0)}",
        f"- Runner profile: {runner.get('runner_profile', 'unknown')}",
        f"- Next step: {payload.get('next_step', 'unknown')}",
        "",
        "## Gates",
        "",
    ]
    for key, value in sorted(as_dict(payload.get("gates")).items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Non-Claims", ""]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        f"- Job JSON: {paths.get('training_job_plan_json', 'unknown')}",
        f"- Job Markdown: {paths.get('training_job_plan_markdown', 'unknown')}",
        "",
    ]
    return "\n".join(lines)


def write_job_plan(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_job_plan.json"
    markdown_path = output_dir / "training_job_plan.md"
    written = dict(payload)
    written["paths"] = {
        "training_job_plan_json": bounded_path(json_path),
        "training_job_plan_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a bounded Ego Link training job plan.")
    parser.add_argument("--handoff-bundle", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--job-id")
    parser.add_argument("--created-at")
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument(
        "--model-track",
        default="motionnet",
        choices=("motionnet", "context_router", "audiogate", "visiongate"),
    )
    parser.add_argument("--candidate-model", default="motionnet_v0_candidate")
    parser.add_argument("--baseline-model", default="rule_router_baseline")
    parser.add_argument(
        "--runner-profile",
        default="local_runner_planned",
        choices=("local_runner_planned", "gpu_server_planned", "ci_dry_run"),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        handoff = load_json(args.handoff_bundle, label="training handoff bundle")
        created_at = args.created_at or utc_now()
        job_id = args.job_id or job_id_for(handoff, created_at)
        payload = build_job_plan(
            handoff,
            handoff_ref=input_ref(args.handoff_bundle),
            job_id=job_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic,
            model_track=args.model_track,
            candidate_model=args.candidate_model,
            baseline_model=args.baseline_model,
            runner_profile=args.runner_profile,
        )
        written = write_job_plan(payload, args.output_root / job_id)
    except TrainingJobPlanError as exc:
        print(f"FAIL training job plan: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training job plan: {written['status']}")
        print(f"Plan: {written['paths']['training_job_plan_markdown']}")
        print(f"Next: {written['next_step']}")
    if args.require_ready and written.get("status") != READY_JOB_STATUS:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
