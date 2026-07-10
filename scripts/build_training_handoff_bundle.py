"""Build a bounded training-server handoff bundle manifest.

This command binds the existing TRAIN-001/003/004/005/006 reports into one
local manifest for a future training runner or training server. It hashes and
counts explicit input files, but it does not copy feature rows, call a server,
train a model, or produce model artifacts.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_handoffs"
HANDOFF_SCHEMA_VERSION = "egolink.training_handoff_bundle.v0.1"
HANDOFF_BUILDER_VERSION = "train-007.0"
READY_DATASET_STATUS = "ready_for_training_handoff"
READY_PREFLIGHT_STATUS = "ready_for_training_runner"
READY_FEATURE_STATUSES = {"ready_for_feature_runner", "ready_for_synthetic_feature_dry_run"}
READY_RUNNER_STATUSES = {"ready_for_runner_execution", "synthetic_runner_dry_run_complete"}
READY_BASELINE_STATUSES = {"baseline_eval_complete", "synthetic_baseline_eval_complete"}
READY_HANDOFF_STATUS = "ready_for_training_server_handoff"
SYNTHETIC_HANDOFF_STATUS = "synthetic_handoff_dry_run_only"


class TrainingHandoffBundleError(RuntimeError):
    """Raised when a handoff input cannot be read safely."""


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


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrainingHandoffBundleError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingHandoffBundleError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingHandoffBundleError(f"{label} JSON must be an object")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TrainingHandoffBundleError(f"cannot hash input file: {path}") from exc
    return digest.hexdigest()


def count_jsonl_rows(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError as exc:
        raise TrainingHandoffBundleError(f"cannot read feature rows: {path}") from exc


def bounded_path(path: Path) -> str:
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(REPO_ROOT.resolve())
        return str(rel)
    except (OSError, ValueError):
        return path.name


def input_ref(path: Path) -> dict[str, Any]:
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise TrainingHandoffBundleError(f"cannot stat input file: {path}") from exc
    return {
        "ref": bounded_path(path),
        "sha256": sha256_file(path),
        "bytes": size_bytes,
        "content_copied": False,
    }


def handoff_id_for(feature_manifest: Mapping[str, Any], baseline_eval: Mapping[str, Any], created_at: str) -> str:
    feature_set_id = slug_id(feature_manifest.get("feature_set_id") or "feature-set")
    eval_id = slug_id(baseline_eval.get("eval_id") or "baseline-eval")
    digest = hashlib.sha1(f"{feature_set_id}|{eval_id}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{feature_set_id}-handoff-{digest}"


def dataset_id_of(payload: Mapping[str, Any], *path: str) -> str | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return str(current) if current not in (None, "") else None


def source_ids_match(
    dataset: Mapping[str, Any],
    preflight: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    baseline_eval: Mapping[str, Any],
) -> bool:
    ids = [
        dataset_id_of(dataset, "dataset_id"),
        dataset_id_of(preflight, "dataset", "dataset_id"),
        dataset_id_of(feature_manifest, "dataset", "dataset_id"),
        dataset_id_of(baseline_eval, "dataset", "dataset_id"),
    ]
    present = [item for item in ids if item]
    return len(set(present)) <= 1


def synthetic_input_seen(feature_manifest: Mapping[str, Any], baseline_eval: Mapping[str, Any]) -> bool:
    feature_dataset = as_dict(feature_manifest.get("dataset"))
    baseline_rows = as_dict(baseline_eval.get("feature_rows"))
    metrics = as_dict(baseline_eval.get("metrics"))
    return (
        as_int(feature_dataset.get("synthetic_records")) > 0
        or as_int(baseline_rows.get("synthetic_rows")) > 0
        or metrics.get("scope") == "synthetic_integration_only"
        or baseline_eval.get("status") == "synthetic_baseline_eval_complete"
    )


def derive_status(
    *,
    dataset: Mapping[str, Any],
    preflight: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    feature_row_count: int,
    runner_dry_run: Mapping[str, Any],
    baseline_eval: Mapping[str, Any],
    allow_synthetic: bool,
) -> str:
    if dataset.get("status") != READY_DATASET_STATUS:
        return "blocked_dataset_not_ready"
    if preflight.get("status") != READY_PREFLIGHT_STATUS:
        return "blocked_preflight_not_ready"
    if feature_manifest.get("status") not in READY_FEATURE_STATUSES:
        return "blocked_feature_manifest_not_ready"
    if runner_dry_run.get("status") not in READY_RUNNER_STATUSES:
        return "blocked_runner_dry_run_not_ready"
    if baseline_eval.get("status") not in READY_BASELINE_STATUSES:
        return "blocked_baseline_eval_not_ready"
    if not source_ids_match(dataset, preflight, feature_manifest, baseline_eval):
        return "blocked_source_mismatch"
    expected_rows = as_int(as_dict(feature_manifest.get("feature_rows")).get("row_count"))
    if expected_rows <= 0 or feature_row_count != expected_rows:
        return "blocked_feature_rows_mismatch"
    if synthetic_input_seen(feature_manifest, baseline_eval):
        return SYNTHETIC_HANDOFF_STATUS if allow_synthetic else "blocked_synthetic_without_ack"
    return READY_HANDOFF_STATUS


def status_reason(status: str) -> str:
    return {
        "blocked_dataset_not_ready": "dataset_manifest_status_is_not_ready_for_training_handoff",
        "blocked_preflight_not_ready": "train003_preflight_is_not_ready",
        "blocked_feature_manifest_not_ready": "train004_feature_manifest_is_not_ready",
        "blocked_runner_dry_run_not_ready": "train005_runner_dry_run_is_not_ready",
        "blocked_baseline_eval_not_ready": "train006_baseline_eval_is_not_ready",
        "blocked_source_mismatch": "dataset_ids_do_not_match_across_handoff_inputs",
        "blocked_feature_rows_mismatch": "feature_rows_jsonl_count_does_not_match_manifest",
        "blocked_synthetic_without_ack": "synthetic_inputs_require_explicit_allow_synthetic",
        SYNTHETIC_HANDOFF_STATUS: "synthetic_inputs_bound_for_dry_run_only",
        READY_HANDOFF_STATUS: "reviewed_engineering_inputs_bound_for_future_training_runner",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == READY_HANDOFF_STATUS:
        return "Configure a local/GPU training runner that consumes this bundle and writes reviewed metrics plus artifact refs."
    if status == SYNTHETIC_HANDOFF_STATUS:
        return "Use this bundle only to dry-run training-server wiring, then repeat with reviewed real field/session records."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for dry-run integration, or provide reviewed real field/session rows."
    if status == "blocked_feature_rows_mismatch":
        return "Use the training_feature_rows.jsonl produced beside the named TRAIN-004 feature manifest."
    return "Fix the named blocker, then rebuild the training handoff bundle."


def build_handoff_bundle(
    *,
    dataset: Mapping[str, Any],
    preflight: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    feature_row_count: int,
    runner_dry_run: Mapping[str, Any],
    baseline_eval: Mapping[str, Any],
    source_refs: Mapping[str, Any],
    handoff_id: str,
    created_at: str,
    allow_synthetic: bool,
) -> dict[str, Any]:
    status = derive_status(
        dataset=dataset,
        preflight=preflight,
        feature_manifest=feature_manifest,
        feature_row_count=feature_row_count,
        runner_dry_run=runner_dry_run,
        baseline_eval=baseline_eval,
        allow_synthetic=allow_synthetic,
    )
    feature_rows = as_dict(feature_manifest.get("feature_rows"))
    baseline_metrics = as_dict(baseline_eval.get("metrics"))
    synthetic = synthetic_input_seen(feature_manifest, baseline_eval)
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "builder_version": HANDOFF_BUILDER_VERSION,
        "handoff_id": handoff_id,
        "created_at": created_at,
        "status": status,
        "reason": status_reason(status),
        "source_refs": dict(source_refs),
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "eligible_records": as_int(as_dict(dataset.get("counts")).get("eligible_records")),
            "split_counts": as_dict(dataset.get("split_counts")),
        },
        "training_run_preflight": {
            "run_id": preflight.get("run_id"),
            "status": preflight.get("status"),
            "runner_ready": as_dict(preflight.get("runner")).get("ready_for_training_runner"),
        },
        "feature_manifest": {
            "feature_set_id": feature_manifest.get("feature_set_id"),
            "status": feature_manifest.get("status"),
            "row_count": as_int(feature_rows.get("row_count")),
            "feature_scope": feature_rows.get("feature_scope"),
            "target_separated_from_features": feature_rows.get("target_separated_from_features"),
        },
        "feature_rows": {
            "row_count": feature_row_count,
            "content_copied": False,
            "raw_rows_exposed": False,
        },
        "runner_dry_run": {
            "run_id": runner_dry_run.get("run_id"),
            "status": runner_dry_run.get("status"),
            "runner_input_gate": as_dict(runner_dry_run.get("gates")).get("runner_input"),
        },
        "baseline_eval": {
            "eval_id": baseline_eval.get("eval_id"),
            "status": baseline_eval.get("status"),
            "metric_scope": baseline_metrics.get("scope"),
            "product_performance_claim": as_dict(baseline_metrics.get("classification")).get(
                "product_performance_claim"
            )
            is True,
        },
        "checks": {
            "source_ids_match": source_ids_match(dataset, preflight, feature_manifest, baseline_eval),
            "feature_row_count_matches": feature_row_count == as_int(feature_rows.get("row_count")),
            "synthetic_input_seen": synthetic,
            "synthetic_policy": "acknowledged" if synthetic and allow_synthetic else (
                "blocked" if synthetic else "not_present"
            ),
        },
        "training_server": {
            "integration": "not_configured",
            "endpoint": None,
            "bundle_ready_for_future_runner": status == READY_HANDOFF_STATUS,
            "dry_run_only": status == SYNTHETIC_HANDOFF_STATUS,
            "next_step": next_step(status),
        },
        "gates": {
            "training_handoff": "pass" if status == READY_HANDOFF_STATUS else (
                "dry_run_only" if status == SYNTHETIC_HANDOFF_STATUS else "blocked"
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
            "Feature-row JSONL contents are not copied into this bundle.",
            "No real-world model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
            "No firmware, public protocol, Message Hub ingest, OTA, or on-device inference behavior changed.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    paths = as_dict(payload.get("paths"))
    feature_rows = as_dict(payload.get("feature_rows"))
    training_server = as_dict(payload.get("training_server"))
    lines = [
        "# Ego Link Training Handoff Bundle",
        "",
        f"- Handoff ID: {payload.get('handoff_id', 'unknown')}",
        f"- Created at: {payload.get('created_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Feature rows: {feature_rows.get('row_count', 0)}",
        f"- Training server integration: {training_server.get('integration', 'unknown')}",
        f"- Next step: {payload.get('next_step', 'unknown')}",
        "",
        "## Source Refs",
        "",
    ]
    for name, ref in sorted(as_dict(payload.get("source_refs")).items()):
        if isinstance(ref, dict):
            lines.append(f"- {name}: {ref.get('ref', 'unknown')} sha256={ref.get('sha256', 'unknown')}")
    lines += ["", "## Gates", ""]
    for key, value in sorted(as_dict(payload.get("gates")).items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Non-Claims", ""]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        f"- Bundle JSON: {paths.get('training_handoff_bundle_json', 'unknown')}",
        f"- Bundle Markdown: {paths.get('training_handoff_bundle_markdown', 'unknown')}",
        "",
    ]
    return "\n".join(lines)


def write_handoff_bundle(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_handoff_bundle.json"
    markdown_path = output_dir / "training_handoff_bundle.md"
    written = dict(payload)
    written["paths"] = {
        "training_handoff_bundle_json": bounded_path(json_path),
        "training_handoff_bundle_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded Ego Link training handoff bundle.")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--feature-manifest", type=Path, required=True)
    parser.add_argument("--feature-rows", type=Path, required=True)
    parser.add_argument("--runner-dry-run", type=Path, required=True)
    parser.add_argument("--baseline-eval", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--handoff-id")
    parser.add_argument("--created-at")
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dataset = load_json(args.dataset_manifest, label="dataset manifest")
        preflight = load_json(args.preflight, label="training run preflight")
        feature_manifest = load_json(args.feature_manifest, label="feature manifest")
        runner_dry_run = load_json(args.runner_dry_run, label="runner dry-run")
        baseline_eval = load_json(args.baseline_eval, label="baseline eval")
        created_at = args.created_at or utc_now()
        handoff_id = args.handoff_id or handoff_id_for(feature_manifest, baseline_eval, created_at)
        feature_row_count = count_jsonl_rows(args.feature_rows)
        source_refs = {
            "dataset_manifest": input_ref(args.dataset_manifest),
            "training_run_preflight": input_ref(args.preflight),
            "training_feature_manifest": input_ref(args.feature_manifest),
            "training_feature_rows": input_ref(args.feature_rows),
            "training_runner_dry_run": input_ref(args.runner_dry_run),
            "training_baseline_eval": input_ref(args.baseline_eval),
        }
        payload = build_handoff_bundle(
            dataset=dataset,
            preflight=preflight,
            feature_manifest=feature_manifest,
            feature_row_count=feature_row_count,
            runner_dry_run=runner_dry_run,
            baseline_eval=baseline_eval,
            source_refs=source_refs,
            handoff_id=handoff_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic,
        )
        written = write_handoff_bundle(payload, args.output_root / handoff_id)
    except TrainingHandoffBundleError as exc:
        print(f"FAIL training handoff bundle: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training handoff bundle: {written['status']}")
        print(f"Bundle: {written['paths']['training_handoff_bundle_markdown']}")
        print(f"Next: {written['next_step']}")
    if args.require_ready and written.get("status") != READY_HANDOFF_STATUS:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
