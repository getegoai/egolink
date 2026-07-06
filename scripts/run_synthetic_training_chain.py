"""Run a no-hardware synthetic data-to-training dry-run chain.

This command is a bounded D5 smoke runner. It generates explicit
synthetic-only session recordings, promotes them through the existing
synthetic review dry-run, then continues through TRAIN-003..008. It does not
read hardware, contact the Message Hub, call a training server, train a model,
copy feature-row contents into the summary, or produce model artifacts.
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

from scripts import build_training_handoff_bundle
from scripts import create_training_job_plan
from scripts import export_training_feature_manifest
from scripts import generate_synthetic_scenarios
from scripts import register_training_experiment
from scripts import run_training_baseline_eval
from scripts import run_training_experiment_preflight
from scripts import run_training_runner_dry_run


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "synthetic_training_chain"
CHAIN_SCHEMA_VERSION = "egolink.synthetic_training_chain.v0.1"
CHAIN_BUILDER_VERSION = "data-020.0"
COMPLETE_STATUS = "synthetic_training_chain_complete"


class SyntheticTrainingChainError(RuntimeError):
    """Raised when the synthetic training chain cannot continue safely."""


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
    return f"synthetic-training-chain-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def bounded_ref(path: Path, *, base: Path | None = None) -> str:
    resolved = path.resolve()
    for root in (base, REPO_ROOT):
        if root is None:
            continue
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
    return path.name


def nested_path(payload: Mapping[str, Any], *keys: str, run_dir: Path) -> Path:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            raise SyntheticTrainingChainError(f"missing artifact path: {'.'.join(keys)}")
        current = current.get(key)
    if current in (None, ""):
        raise SyntheticTrainingChainError(f"missing artifact path: {'.'.join(keys)}")
    path = Path(str(current))
    if path.is_absolute():
        return path
    for candidate in (run_dir / path, REPO_ROOT / path):
        if candidate.exists():
            return candidate
    return path


def component_path(path: Path, *, run_dir: Path) -> dict[str, Any]:
    return {
        "ref": bounded_ref(path, base=run_dir),
        "content_copied": False,
    }


def summarize_pipeline(payload: Mapping[str, Any] | None, *, run_dir: Path) -> dict[str, Any]:
    if not payload:
        return {"status": "not_run"}
    data_flywheel = as_dict(payload.get("data_flywheel"))
    dataset = as_dict(payload.get("dataset_manifest"))
    experiment = as_dict(payload.get("training_experiment"))
    counts = as_dict(data_flywheel.get("counts"))
    dataset_counts = as_dict(dataset.get("counts"))
    paths = as_dict(payload.get("paths"))
    summary: dict[str, Any] = {
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "recordings_requested": payload.get("recordings_requested"),
        "recordings_ingested": len(as_list(payload.get("recordings_ingested"))),
        "candidate_records": counts.get("records_total"),
        "pending_review": as_dict(data_flywheel.get("review_queue")).get("pending_records"),
        "dataset_status": dataset.get("status"),
        "eligible_records": dataset_counts.get("eligible_records"),
        "experiment_status": experiment.get("status"),
        "runner_ready": as_dict(experiment.get("runner")).get("ready_for_handoff"),
    }
    pipeline_json = paths.get("data_flywheel_pipeline_json")
    if pipeline_json:
        summary["report"] = component_path(Path(str(pipeline_json)), run_dir=run_dir)
    return summary


def run_synthetic_data_pipeline(args: argparse.Namespace, *, run_dir: Path) -> dict[str, Any]:
    synthetic_args = argparse.Namespace(
        run_id=args.run_id,
        generated_at=args.generated_at,
        output_root=args.output_root,
        db=run_dir / "candidate_store.sqlite3",
        device_id=args.device_id,
        seed=args.seed,
        samples_per_scenario=args.samples_per_scenario,
        scenario=list(args.scenario or generate_synthetic_scenarios.DEFAULT_SCENARIOS),
        no_training_request=False,
        run_pipeline=True,
        review_synthetic=True,
        model_track=args.model_track,
        candidate_model=args.candidate_model,
        baseline_model=args.baseline_model,
        json=False,
    )
    recordings = generate_synthetic_scenarios.generate_recordings(
        synthetic_args,
        run_dir=run_dir,
        generated_at=args.generated_at,
    )
    recording_dirs = [run_dir / str(item["recording_ref"]) for item in recordings]
    initial_pipeline = generate_synthetic_scenarios.run_pipeline(
        args=synthetic_args,
        run_dir=run_dir,
        db_path=synthetic_args.db,
        run_id=args.run_id,
        generated_at=args.generated_at,
        recording_dirs=recording_dirs,
        suffix="initial",
    )
    reviewed_records, failed_reviews = generate_synthetic_scenarios.review_generated_candidates(
        synthetic_args.db,
        session_ids={str(item["session_id"]) for item in recordings},
        reviewed_at=args.generated_at,
    )
    reviewed_pipeline: dict[str, Any] | None = None
    if not failed_reviews:
        reviewed_pipeline = generate_synthetic_scenarios.run_pipeline(
            args=synthetic_args,
            run_dir=run_dir,
            db_path=synthetic_args.db,
            run_id=args.run_id,
            generated_at=args.generated_at,
            recording_dirs=[],
            suffix="reviewed",
        )

    scenario_payload = {
        "schema_version": generate_synthetic_scenarios.SYNTHETIC_SCHEMA_VERSION,
        "builder_version": generate_synthetic_scenarios.SYNTHETIC_BUILDER_VERSION,
        "run_id": args.run_id,
        "generated_at": args.generated_at,
        "status": generate_synthetic_scenarios.derive_status(
            initial_pipeline=initial_pipeline,
            reviewed_pipeline=reviewed_pipeline,
            review_failures=failed_reviews,
        ),
        "synthetic_only": True,
        "seed": args.seed,
        "scenarios": sorted({str(item["scenario"]) for item in recordings}),
        "counts": {
            "recordings": len(recordings),
            "training_requested": sum(1 for item in recordings if item.get("training_requested")),
            "reviewed_records": len(reviewed_records),
        },
        "recordings": recordings,
        "candidate_store": {
            "written": bool(initial_pipeline),
            "db_path_exported": False,
        },
        "pipelines": {
            "initial": generate_synthetic_scenarios.summarize_pipeline(initial_pipeline),
            "reviewed": generate_synthetic_scenarios.summarize_pipeline(reviewed_pipeline),
        },
        "synthetic_review": {
            "explicit_review_requested": True,
            "reviewed_records": reviewed_records,
            "failed_reviews": failed_reviews,
        },
        "non_claims": [
            "Synthetic scenarios are not hardware, field, or user evidence.",
            "Synthetic review is a dry-run gate exercise, not release acceptance.",
            "No model training has run.",
            "No model has been evaluated or deployed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
        ],
    }
    scenario_written = generate_synthetic_scenarios.write_report(scenario_payload, run_dir)
    return {
        "recordings": recordings,
        "reviewed_records": reviewed_records,
        "failed_reviews": failed_reviews,
        "initial_pipeline": initial_pipeline,
        "reviewed_pipeline": reviewed_pipeline,
        "synthetic_report": scenario_written,
    }


def run_training_chain(
    args: argparse.Namespace,
    *,
    run_dir: Path,
    reviewed_pipeline: Mapping[str, Any],
) -> dict[str, Any]:
    dataset_manifest_path = nested_path(
        reviewed_pipeline,
        "dataset_manifest",
        "paths",
        "training_dataset_manifest_json",
        run_dir=run_dir,
    )
    experiment_plan_path = nested_path(
        reviewed_pipeline,
        "training_experiment",
        "paths",
        "training_experiment_plan_json",
        run_dir=run_dir,
    )

    preflight_run_id = f"{args.run_id}-training-preflight"
    experiment = run_training_experiment_preflight.load_json(experiment_plan_path, label="experiment plan")
    dataset = run_training_experiment_preflight.load_json(dataset_manifest_path, label="dataset manifest")
    preflight_payload = run_training_experiment_preflight.build_preflight_report(
        experiment,
        dataset,
        experiment_plan_ref=experiment_plan_path.name,
        dataset_manifest_ref=dataset_manifest_path.name,
        run_id=preflight_run_id,
        created_at=args.generated_at,
        allow_synthetic=True,
    )
    preflight_dir = run_dir / "training_runs" / preflight_run_id
    preflight_written = run_training_experiment_preflight.write_preflight_report(preflight_payload, preflight_dir)
    preflight_path = preflight_dir / "training_run_preflight.json"

    feature_set_id = f"{args.run_id}-features"
    feature_dataset = export_training_feature_manifest.load_json(dataset_manifest_path, label="dataset manifest")
    feature_preflight = export_training_feature_manifest.load_json(preflight_path, label="training run preflight")
    feature_payload, feature_rows = export_training_feature_manifest.build_feature_manifest(
        feature_dataset,
        feature_preflight,
        dataset_manifest_ref=dataset_manifest_path.name,
        preflight_ref=preflight_path.name,
        feature_set_id=feature_set_id,
        generated_at=args.generated_at,
        allow_synthetic=True,
    )
    feature_dir = run_dir / "training_features" / feature_set_id
    feature_written = export_training_feature_manifest.write_feature_manifest(
        feature_payload,
        feature_rows,
        feature_dir,
    )
    feature_manifest_path = feature_dir / "training_feature_manifest.json"
    feature_rows_path = feature_dir / "training_feature_rows.jsonl"

    runner_run_id = f"{args.run_id}-runner-dry-run"
    runner_manifest = run_training_runner_dry_run.load_json(feature_manifest_path, label="feature manifest")
    runner_rows, runner_row_error = run_training_runner_dry_run.load_jsonl_rows(feature_rows_path)
    runner_payload = run_training_runner_dry_run.build_runner_dry_run_report(
        runner_manifest,
        runner_rows,
        row_error=runner_row_error,
        feature_manifest_ref=feature_manifest_path.name,
        feature_rows_ref=feature_rows_path.name,
        run_id=runner_run_id,
        created_at=args.generated_at,
        allow_synthetic=True,
    )
    runner_dir = run_dir / "training_runner_dry_runs" / runner_run_id
    runner_written = run_training_runner_dry_run.write_runner_dry_run_report(runner_payload, runner_dir)
    runner_path = runner_dir / "training_runner_dry_run.json"

    baseline_eval_id = f"{args.run_id}-baseline-eval"
    baseline_manifest = run_training_baseline_eval.load_json(feature_manifest_path, label="feature manifest")
    baseline_runner = run_training_baseline_eval.load_json(runner_path, label="runner dry-run")
    baseline_rows, baseline_row_error = run_training_baseline_eval.load_jsonl_rows(feature_rows_path)
    baseline_payload = run_training_baseline_eval.build_baseline_eval_report(
        baseline_manifest,
        baseline_runner,
        baseline_rows,
        row_error=baseline_row_error,
        feature_manifest_ref=feature_manifest_path.name,
        feature_rows_ref=feature_rows_path.name,
        runner_dry_run_ref=runner_path.name,
        eval_id=baseline_eval_id,
        created_at=args.generated_at,
        allow_synthetic=True,
    )
    baseline_dir = run_dir / "training_baseline_evals" / baseline_eval_id
    baseline_written = run_training_baseline_eval.write_baseline_eval_report(baseline_payload, baseline_dir)
    baseline_path = baseline_dir / "training_baseline_eval.json"

    handoff_id = f"{args.run_id}-training-handoff"
    handoff_dataset = build_training_handoff_bundle.load_json(dataset_manifest_path, label="dataset manifest")
    handoff_preflight = build_training_handoff_bundle.load_json(preflight_path, label="training run preflight")
    handoff_feature = build_training_handoff_bundle.load_json(feature_manifest_path, label="feature manifest")
    handoff_runner = build_training_handoff_bundle.load_json(runner_path, label="runner dry-run")
    handoff_baseline = build_training_handoff_bundle.load_json(baseline_path, label="baseline eval")
    feature_row_count = build_training_handoff_bundle.count_jsonl_rows(feature_rows_path)
    handoff_payload = build_training_handoff_bundle.build_handoff_bundle(
        dataset=handoff_dataset,
        preflight=handoff_preflight,
        feature_manifest=handoff_feature,
        feature_row_count=feature_row_count,
        runner_dry_run=handoff_runner,
        baseline_eval=handoff_baseline,
        source_refs={
            "dataset_manifest": build_training_handoff_bundle.input_ref(dataset_manifest_path),
            "training_run_preflight": build_training_handoff_bundle.input_ref(preflight_path),
            "training_feature_manifest": build_training_handoff_bundle.input_ref(feature_manifest_path),
            "training_feature_rows": build_training_handoff_bundle.input_ref(feature_rows_path),
            "training_runner_dry_run": build_training_handoff_bundle.input_ref(runner_path),
            "training_baseline_eval": build_training_handoff_bundle.input_ref(baseline_path),
        },
        handoff_id=handoff_id,
        created_at=args.generated_at,
        allow_synthetic=True,
    )
    handoff_dir = run_dir / "training_handoffs" / handoff_id
    handoff_written = build_training_handoff_bundle.write_handoff_bundle(handoff_payload, handoff_dir)
    handoff_path = handoff_dir / "training_handoff_bundle.json"

    job_id = f"{args.run_id}-training-job"
    job_payload = create_training_job_plan.build_job_plan(
        handoff_written,
        handoff_ref=create_training_job_plan.input_ref(handoff_path),
        job_id=job_id,
        created_at=args.generated_at,
        allow_synthetic=True,
        model_track=args.model_track,
        candidate_model=args.candidate_model,
        baseline_model=args.baseline_model,
        runner_profile=args.runner_profile,
    )
    job_dir = run_dir / "training_jobs" / job_id
    job_written = create_training_job_plan.write_job_plan(job_payload, job_dir)
    job_path = job_dir / "training_job_plan.json"

    return {
        "status": job_written.get("status"),
        "reason": job_written.get("reason"),
        "synthetic_allowed_for_dry_run": True,
        "components": {
            "preflight": {
                "status": preflight_written.get("status"),
                "reason": preflight_written.get("reason"),
                "run_id": preflight_written.get("run_id"),
                "report": component_path(preflight_path, run_dir=run_dir),
            },
            "feature_manifest": {
                "status": feature_written.get("status"),
                "reason": feature_written.get("reason"),
                "feature_set_id": feature_written.get("feature_set_id"),
                "row_count": as_dict(feature_written.get("feature_rows")).get("row_count"),
                "feature_scope": as_dict(feature_written.get("feature_rows")).get("feature_scope"),
                "report": component_path(feature_manifest_path, run_dir=run_dir),
            },
            "runner_dry_run": {
                "status": runner_written.get("status"),
                "reason": runner_written.get("reason"),
                "run_id": runner_written.get("run_id"),
                "row_count": as_dict(runner_written.get("feature_rows")).get("actual_row_count"),
                "report": component_path(runner_path, run_dir=run_dir),
            },
            "baseline_eval": {
                "status": baseline_written.get("status"),
                "reason": baseline_written.get("reason"),
                "eval_id": baseline_written.get("eval_id"),
                "metric_scope": as_dict(baseline_written.get("metrics")).get("scope"),
                "product_performance_claim": as_dict(
                    as_dict(baseline_written.get("metrics")).get("classification")
                ).get("product_performance_claim"),
                "report": component_path(baseline_path, run_dir=run_dir),
            },
            "handoff_bundle": {
                "status": handoff_written.get("status"),
                "reason": handoff_written.get("reason"),
                "handoff_id": handoff_written.get("handoff_id"),
                "training_server": as_dict(handoff_written.get("training_server")).get("integration"),
                "dry_run_only": as_dict(handoff_written.get("training_server")).get("dry_run_only", False),
                "report": component_path(handoff_path, run_dir=run_dir),
            },
            "job_plan": {
                "status": job_written.get("status"),
                "reason": job_written.get("reason"),
                "job_id": job_written.get("job_id"),
                "runner_profile": as_dict(job_written.get("runner_plan")).get("runner_profile"),
                "queue_state": as_dict(job_written.get("runner_plan")).get("queue_state"),
                "dry_run_only": as_dict(job_written.get("runner_plan")).get("dry_run_only", False),
                "report": component_path(job_path, run_dir=run_dir),
            },
        },
        "paths": {
            "dataset_manifest": component_path(dataset_manifest_path, run_dir=run_dir),
            "training_experiment_plan": component_path(experiment_plan_path, run_dir=run_dir),
            "training_job_plan": component_path(job_path, run_dir=run_dir),
        },
        "next_step": job_written.get("next_step"),
    }


def derive_status(
    *,
    data_chain: Mapping[str, Any],
    training_chain: Mapping[str, Any] | None,
) -> str:
    if as_list(data_chain.get("failed_reviews")):
        return "synthetic_review_failed"
    reviewed_pipeline = as_dict(data_chain.get("reviewed_pipeline"))
    if reviewed_pipeline.get("status") != "ready_for_training_handoff":
        return str(reviewed_pipeline.get("status") or "synthetic_data_pipeline_blocked")
    if not training_chain:
        return "training_chain_not_run"
    if training_chain.get("status") == create_training_job_plan.SYNTHETIC_JOB_STATUS:
        return COMPLETE_STATUS
    return "training_chain_blocked"


def next_step(status: str, training_chain: Mapping[str, Any] | None) -> str:
    if status == COMPLETE_STATUS:
        return (
            "Use this as the no-hardware smoke for the data/model plumbing, then repeat "
            "the chain with reviewed real field or session records before any model claim."
        )
    if training_chain and training_chain.get("next_step"):
        return str(training_chain["next_step"])
    return "Fix the named synthetic chain blocker, then rerun this command."


def build_summary(args: argparse.Namespace, *, run_dir: Path) -> dict[str, Any]:
    data_chain = run_synthetic_data_pipeline(args, run_dir=run_dir)
    reviewed_pipeline = as_dict(data_chain.get("reviewed_pipeline"))
    training_chain: dict[str, Any] | None = None
    if reviewed_pipeline.get("status") == "ready_for_training_handoff":
        training_chain = run_training_chain(args, run_dir=run_dir, reviewed_pipeline=reviewed_pipeline)

    status = derive_status(data_chain=data_chain, training_chain=training_chain)
    synthetic_report = as_dict(data_chain.get("synthetic_report"))
    counts = {
        "recordings": len(as_list(data_chain.get("recordings"))),
        "reviewed_records": len(as_list(data_chain.get("reviewed_records"))),
        "review_failures": len(as_list(data_chain.get("failed_reviews"))),
        "feature_rows": as_dict(as_dict(training_chain or {}).get("components"))
        .get("feature_manifest", {})
        .get("row_count"),
    }
    return {
        "schema_version": CHAIN_SCHEMA_VERSION,
        "builder_version": CHAIN_BUILDER_VERSION,
        "run_id": args.run_id,
        "generated_at": args.generated_at,
        "serves_demo": "D5",
        "status": status,
        "synthetic_only": True,
        "scenarios": sorted({str(item.get("scenario")) for item in as_list(data_chain.get("recordings"))}),
        "counts": counts,
        "components": {
            "synthetic_scenarios": {
                "status": synthetic_report.get("status"),
                "seed": args.seed,
                "recordings": counts["recordings"],
                "reviewed_records": counts["reviewed_records"],
                "failed_reviews": counts["review_failures"],
                "report": component_path(run_dir / "synthetic_scenario_run.json", run_dir=run_dir),
            },
            "data_flywheel": {
                "initial": summarize_pipeline(as_dict(data_chain.get("initial_pipeline")), run_dir=run_dir),
                "reviewed": summarize_pipeline(as_dict(data_chain.get("reviewed_pipeline")), run_dir=run_dir),
            },
            "training_chain": training_chain or {"status": "not_run"},
        },
        "scope": {
            "hardware_contacted": False,
            "message_hub_contacted": False,
            "model_training_started": False,
            "model_evaluation_real_world": False,
            "model_artifact_written": False,
            "device_deployment_started": False,
            "power_or_footprint_measured": False,
            "release_claim_allowed": False,
        },
        "next_step": next_step(status, training_chain),
        "non_claims": [
            "Synthetic records are not hardware, field, user, GNSS/LTE, or power evidence.",
            "Synthetic review approval is a dry-run gate exercise, not release acceptance.",
            "No real model training, real-world evaluation, model artifact, model card, or device deployment has run.",
            "No model accuracy, false-positive rate, latency, footprint, power, battery-life, or product-readiness claim is made.",
            "No firmware, public protocol, Message Hub ingest, VPS deployment, OTA, or on-device inference behavior changed.",
            "The summary contains bounded status, counts, and refs only; it does not copy raw recordings, candidate records, candidate DB paths, private coordinates, feature-row contents, private endpoints, or model artifacts.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    counts = as_dict(payload.get("counts"))
    components = as_dict(payload.get("components"))
    data_flywheel = as_dict(components.get("data_flywheel"))
    training = as_dict(components.get("training_chain"))
    training_components = as_dict(training.get("components"))
    lines = [
        "# Ego Link Synthetic Training Chain",
        "",
        f"- Run ID: {payload.get('run_id', 'unknown')}",
        f"- Generated at: {payload.get('generated_at', 'unknown')}",
        f"- Serves demo: {payload.get('serves_demo', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Synthetic only: {payload.get('synthetic_only', True)}",
        f"- Scenarios: {', '.join(payload.get('scenarios', []) or [])}",
        f"- Recordings: {counts.get('recordings', 0)}",
        f"- Reviewed records: {counts.get('reviewed_records', 0)}",
        f"- Feature rows: {counts.get('feature_rows', 0)}",
        "",
        "## Chain",
        "",
        "| Step | Status | Notes |",
        "|---|---|---|",
    ]
    initial = as_dict(data_flywheel.get("initial"))
    reviewed = as_dict(data_flywheel.get("reviewed"))
    lines.append(
        f"| Synthetic scenarios | {as_dict(components.get('synthetic_scenarios')).get('status', 'unknown')} | "
        f"{counts.get('recordings', 0)} recordings |"
    )
    lines.append(
        f"| Data pipeline initial | {initial.get('status', 'unknown')} | "
        f"pending review {initial.get('pending_review', 'unknown')} |"
    )
    lines.append(
        f"| Data pipeline reviewed | {reviewed.get('status', 'unknown')} | "
        f"eligible {reviewed.get('eligible_records', 'unknown')} |"
    )
    for name, label in [
        ("preflight", "TRAIN-003 preflight"),
        ("feature_manifest", "TRAIN-004 features"),
        ("runner_dry_run", "TRAIN-005 dry-run"),
        ("baseline_eval", "TRAIN-006 baseline"),
        ("handoff_bundle", "TRAIN-007 handoff"),
        ("job_plan", "TRAIN-008 job plan"),
    ]:
        item = as_dict(training_components.get(name))
        lines.append(f"| {label} | {item.get('status', 'not_run')} | {item.get('reason', '')} |")
    lines += [
        "",
        "## Scope",
        "",
    ]
    for key, value in sorted(as_dict(payload.get("scope")).items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
    lines += [
        "",
        "## Next Step",
        "",
        str(payload.get("next_step") or "Continue the next data/model task."),
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_summary(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "synthetic_training_chain.json"
    markdown_path = output_dir / "synthetic_training_chain.md"
    written = dict(payload)
    written["paths"] = {
        "synthetic_training_chain_json": component_path(json_path, run_dir=output_dir),
        "synthetic_training_chain_markdown": component_path(markdown_path, run_dir=output_dir),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a synthetic-only DATA/TRAIN dry-run chain.")
    parser.add_argument("--run-id", help="Stable output run directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device-id", default="ego-link-synth-001")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples-per-scenario", type=int, default=1)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=tuple(generate_synthetic_scenarios.SCENARIO_SPECS),
        help="Synthetic scenario to generate. Can be passed more than once.",
    )
    parser.add_argument(
        "--model-track",
        default=register_training_experiment.DEFAULT_MODEL_TRACK,
        choices=("motionnet", "context_router", "audiogate", "visiongate"),
    )
    parser.add_argument("--candidate-model", default=register_training_experiment.DEFAULT_CANDIDATE_MODEL)
    parser.add_argument("--baseline-model", default=register_training_experiment.DEFAULT_BASELINE_MODEL)
    parser.add_argument(
        "--runner-profile",
        default="ci_dry_run",
        choices=("local_runner_planned", "gpu_server_planned", "ci_dry_run"),
    )
    parser.add_argument("--json", action="store_true", help="Print the bounded chain JSON.")
    args = parser.parse_args(argv)
    if args.samples_per_scenario < 1:
        parser.error("--samples-per-scenario must be >= 1")
    args.generated_at = args.generated_at or utc_now()
    args.run_id = args.run_id or default_run_id(args.generated_at)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.output_root / args.run_id
    try:
        payload = build_summary(args, run_dir=run_dir)
        written = write_summary(payload, run_dir)
    except Exception as exc:
        print(f"FAIL synthetic training chain: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Synthetic training chain: {written['status']}")
        print(f"Report: {run_dir / 'synthetic_training_chain.md'}")
        print(f"Next: {written.get('next_step', 'unknown')}")
    return 0 if written.get("status") == COMPLETE_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
