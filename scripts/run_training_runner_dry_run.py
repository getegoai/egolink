"""Run a bounded dry-run over Ego Link training feature rows.

This command checks whether a TRAIN-004 feature manifest and JSONL row file can
be consumed by a future local/GPU training runner. It does not train, evaluate,
upload, or deploy a model, and it does not produce model artifacts.
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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_runner_dry_runs"
RUNNER_DRY_RUN_SCHEMA_VERSION = "egolink.training_runner_dry_run.v0.1"
RUNNER_DRY_RUN_BUILDER_VERSION = "train-005.0"
READY_FEATURE_STATUSES = {"ready_for_feature_runner", "ready_for_synthetic_feature_dry_run"}
READY_STATUSES = {"ready_for_runner_execution", "synthetic_runner_dry_run_complete"}


class TrainingRunnerDryRunError(RuntimeError):
    """Raised when a runner dry-run input cannot be read safely."""


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
        raise TrainingRunnerDryRunError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingRunnerDryRunError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingRunnerDryRunError(f"{label} JSON must be an object")
    return payload


def load_jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], "feature_rows_unreadable"
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return [], f"feature_rows_invalid_jsonl_line_{line_no}"
        if not isinstance(row, dict):
            return [], f"feature_rows_invalid_object_line_{line_no}"
        rows.append(row)
    return rows, None


def bounded_path(path: Path) -> str:
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(REPO_ROOT.resolve())
        return str(rel)
    except (OSError, ValueError):
        return path.name


def run_id_for(manifest: Mapping[str, Any], created_at: str) -> str:
    feature_set_id = slug_id(manifest.get("feature_set_id") or "feature-set")
    digest = hashlib.sha1(f"{feature_set_id}|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{feature_set_id}-runner-dry-run-{digest}"


def row_label(row: Mapping[str, Any]) -> str:
    return str(as_dict(row.get("target")).get("label") or "unknown")


def row_source_status(row: Mapping[str, Any]) -> str:
    return str(as_dict(row.get("source")).get("source_status") or as_dict(row.get("features")).get("source_status") or "unknown")


def is_synthetic_row(row: Mapping[str, Any]) -> bool:
    source = as_dict(row.get("source"))
    if source.get("synthetic") is True:
        return True
    return "synthetic" in row_source_status(row).lower()


def count_by(rows: list[Mapping[str, Any]], getter: str | None = None) -> dict[str, int]:
    values: Counter[str] = Counter()
    for row in rows:
        if getter == "label":
            values[row_label(row)] += 1
        elif getter == "source_status":
            values[row_source_status(row)] += 1
        elif getter == "split_name":
            values[str(row.get("split_name") or "unknown")] += 1
    return dict(sorted(values.items()))


def feature_group_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    values: Counter[str] = Counter()
    for row in rows:
        for group in as_list(as_dict(row.get("source")).get("feature_groups")):
            values[str(group or "unknown")] += 1
    return dict(sorted(values.items()))


def synthetic_row_count(rows: list[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if is_synthetic_row(row))


def missing_required_row_fields(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    missing: Counter[str] = Counter()
    for row in rows:
        target = as_dict(row.get("target"))
        features = row.get("features")
        source = as_dict(row.get("source"))
        for field in ("row_id", "record_id", "session_id", "window_id", "split_name"):
            if not row.get(field):
                missing[field] += 1
        if not target.get("label"):
            missing["target.label"] += 1
        if not isinstance(features, dict) or not features:
            missing["features"] += 1
        if "synthetic" not in source:
            missing["source.synthetic"] += 1
    return dict(sorted(missing.items()))


def target_leakage_violations(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    violations: Counter[str] = Counter()
    for row in rows:
        features = as_dict(row.get("features"))
        if "label" in features:
            violations["features.label"] += 1
        if "model_labels" in features:
            violations["features.model_labels"] += 1
        if "target" in features:
            violations["features.target"] += 1
    return dict(sorted(violations.items()))


def feature_set_mismatch_count(rows: list[Mapping[str, Any]], feature_set_id: str) -> int:
    return sum(1 for row in rows if row.get("feature_set_id") != feature_set_id)


def derive_status(
    *,
    manifest: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    row_error: str | None,
    missing_fields: Mapping[str, int],
    leakage: Mapping[str, int],
    synthetic_rows: int,
    allow_synthetic: bool,
) -> str:
    if manifest.get("status") not in READY_FEATURE_STATUSES:
        return "blocked_feature_manifest_not_ready"
    if row_error:
        return "blocked_feature_rows_unreadable"
    feature_rows = as_dict(manifest.get("feature_rows"))
    expected_rows = as_int(feature_rows.get("row_count"))
    feature_set_id = str(manifest.get("feature_set_id") or "")
    if not rows or expected_rows <= 0:
        return "blocked_no_feature_rows"
    if len(rows) != expected_rows or feature_set_mismatch_count(rows, feature_set_id):
        return "blocked_feature_rows_mismatch"
    if missing_fields:
        return "blocked_incomplete_feature_rows"
    if leakage:
        return "blocked_target_leakage_guard"
    if synthetic_rows and not allow_synthetic:
        return "blocked_synthetic_without_ack"
    if synthetic_rows:
        return "synthetic_runner_dry_run_complete"
    return "ready_for_runner_execution"


def status_reason(status: str) -> str:
    return {
        "blocked_feature_manifest_not_ready": "feature_manifest_status_is_not_ready",
        "blocked_feature_rows_unreadable": "feature_rows_jsonl_cannot_be_read_or_parsed",
        "blocked_no_feature_rows": "feature_manifest_has_no_rows",
        "blocked_feature_rows_mismatch": "feature_rows_do_not_match_manifest_feature_set_or_count",
        "blocked_incomplete_feature_rows": "feature_rows_missing_required_bounded_fields",
        "blocked_target_leakage_guard": "target_labels_must_not_be_inside_feature_fields",
        "blocked_synthetic_without_ack": "synthetic_rows_require_explicit_allow_synthetic",
        "synthetic_runner_dry_run_complete": "runner_input_contract_validated_with_synthetic_dry_run_rows",
        "ready_for_runner_execution": "runner_input_contract_validated_for_real_training_runner",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == "ready_for_runner_execution":
        return "Connect a local/GPU runner that trains from the validated rows and writes measured metrics plus reviewed artifact refs."
    if status == "synthetic_runner_dry_run_complete":
        return "Use this only to verify runner wiring, then repeat with reviewed real field/session rows before model claims."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for dry-run integration, or provide reviewed real field/session rows."
    if status == "blocked_target_leakage_guard":
        return "Regenerate feature rows so target labels stay under target and outside features."
    if status == "blocked_incomplete_feature_rows":
        return "Regenerate TRAIN-004 feature rows with complete bounded row fields."
    if status == "blocked_feature_rows_mismatch":
        return "Rerun with the JSONL rows produced beside the named feature manifest."
    if status == "blocked_feature_manifest_not_ready":
        return "Rerun TRAIN-004 until the feature manifest is ready."
    return "Fix the named blocker, then rerun the runner dry-run."


def build_runner_dry_run_report(
    manifest: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    row_error: str | None,
    feature_manifest_ref: str,
    feature_rows_ref: str,
    run_id: str,
    created_at: str,
    allow_synthetic: bool,
) -> dict[str, Any]:
    missing_fields = missing_required_row_fields(rows)
    leakage = target_leakage_violations(rows)
    synthetic_rows = synthetic_row_count(rows)
    status = derive_status(
        manifest=manifest,
        rows=rows,
        row_error=row_error,
        missing_fields=missing_fields,
        leakage=leakage,
        synthetic_rows=synthetic_rows,
        allow_synthetic=allow_synthetic,
    )
    feature_rows = as_dict(manifest.get("feature_rows"))
    dataset = as_dict(manifest.get("dataset"))
    preflight = as_dict(manifest.get("preflight"))
    gates = as_dict(manifest.get("gates"))
    expected_rows = as_int(feature_rows.get("row_count"))
    feature_set_id = str(manifest.get("feature_set_id") or "unknown")
    mismatch_count = feature_set_mismatch_count(rows, feature_set_id)
    return {
        "schema_version": RUNNER_DRY_RUN_SCHEMA_VERSION,
        "builder_version": RUNNER_DRY_RUN_BUILDER_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "reason": status_reason(status),
        "source_refs": {
            "feature_manifest_ref": feature_manifest_ref,
            "feature_rows_ref": feature_rows_ref,
        },
        "feature_manifest": {
            "feature_set_id": feature_set_id,
            "status": manifest.get("status"),
            "reason": manifest.get("reason"),
            "feature_scope": feature_rows.get("feature_scope"),
            "target_separated_from_features": feature_rows.get("target_separated_from_features", False),
        },
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "eligible_records": dataset.get("eligible_records", 0),
            "synthetic_records": dataset.get("synthetic_records", 0),
        },
        "preflight": {
            "run_id": preflight.get("run_id"),
            "status": preflight.get("status"),
            "runner_ready": preflight.get("runner_ready", False),
            "metrics_measured": as_dict(preflight.get("metrics_measured")),
        },
        "feature_rows": {
            "expected_row_count": expected_rows,
            "actual_row_count": len(rows),
            "row_count_matches": len(rows) == expected_rows,
            "feature_set_mismatch_count": mismatch_count,
            "split_counts": count_by(rows, "split_name"),
            "label_counts": count_by(rows, "label"),
            "source_status_counts": count_by(rows, "source_status"),
            "feature_group_counts": feature_group_counts(rows),
            "synthetic_rows": synthetic_rows,
            "synthetic_allowed_for_dry_run": bool(allow_synthetic),
        },
        "checks": {
            "feature_manifest_ready": manifest.get("status") in READY_FEATURE_STATUSES,
            "feature_rows_readable": row_error is None,
            "feature_rows_error": row_error,
            "row_count_matches": len(rows) == expected_rows and not mismatch_count,
            "required_row_fields": "pass" if not missing_fields else "fail",
            "missing_row_fields": dict(missing_fields),
            "target_leakage_guard": "pass" if not leakage else "fail",
            "target_leakage_violations": dict(leakage),
            "synthetic_row_policy": "acknowledged" if synthetic_rows and allow_synthetic else (
                "blocked" if synthetic_rows else "not_present"
            ),
            "manifest_feature_export_gate": gates.get("feature_export"),
        },
        "runner": {
            "integration": "local_runner_dry_run",
            "ready_for_real_runner": status == "ready_for_runner_execution",
            "dry_run_only": status == "synthetic_runner_dry_run_complete",
            "training_server_endpoint": None,
            "next_step": next_step(status),
        },
        "metrics_plan": {
            "measured": {
                "classification": "not_run",
                "operations": "not_run",
                "footprint": "not_run",
                "power": "not_run",
            },
            "dry_run_summary": {
                "labels": count_by(rows, "label"),
                "splits": count_by(rows, "split_name"),
                "feature_groups": feature_group_counts(rows),
            },
        },
        "gates": {
            "runner_input": "pass" if status in READY_STATUSES else "blocked",
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
            "The runner dry-run validates input shape and bounded counts only.",
            "Synthetic dry-run results are not model metrics and are not release evidence.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    manifest = as_dict(payload.get("feature_manifest"))
    feature_rows = as_dict(payload.get("feature_rows"))
    runner = as_dict(payload.get("runner"))
    checks = as_dict(payload.get("checks"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Training Runner Dry-Run",
        "",
        f"- Run ID: {payload.get('run_id', 'unknown')}",
        f"- Created at: {payload.get('created_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Feature set: {manifest.get('feature_set_id', 'unknown')} ({manifest.get('status', 'unknown')})",
        f"- Rows: {feature_rows.get('actual_row_count', 0)} / expected {feature_rows.get('expected_row_count', 0)}",
        f"- Synthetic rows: {feature_rows.get('synthetic_rows', 0)}",
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
        f"- Ready for real runner: {runner.get('ready_for_real_runner', False)}",
        f"- Dry-run only: {runner.get('dry_run_only', False)}",
        f"- Next step: {runner.get('next_step', 'unknown')}",
        "",
        "## Artifacts",
        "",
        f"- Runner dry-run JSON: {paths.get('training_runner_dry_run_json', 'unknown')}",
        f"- Runner dry-run Markdown: {paths.get('training_runner_dry_run_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This dry-run contains bounded runner-input checks only. It does not contain raw recordings, raw candidate records, candidate DB files, runtime JSONL logs, private coordinates, private training endpoints, model weights, measured metrics, or model artifacts.",
        "",
    ]
    return "\n".join(lines)


def write_runner_dry_run_report(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_runner_dry_run.json"
    markdown_path = output_dir / "training_runner_dry_run.md"
    written = dict(payload)
    written["paths"] = {
        "training_runner_dry_run_json": bounded_path(json_path),
        "training_runner_dry_run_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded Ego Link training runner dry-run.")
    parser.add_argument("--feature-manifest", type=Path, required=True, help="TRAIN-004 training_feature_manifest.json.")
    parser.add_argument("--feature-rows", type=Path, required=True, help="TRAIN-004 training_feature_rows.jsonl.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Stable runner dry-run ID.")
    parser.add_argument("--created-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic-only rows for dry-run integration.")
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until the dry-run passes.")
    parser.add_argument("--json", action="store_true", help="Print the bounded dry-run JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_json(args.feature_manifest, label="feature manifest")
        rows, row_error = load_jsonl_rows(args.feature_rows)
        created_at = args.created_at or utc_now()
        run_id = args.run_id or run_id_for(manifest, created_at)
        payload = build_runner_dry_run_report(
            manifest,
            rows,
            row_error=row_error,
            feature_manifest_ref=args.feature_manifest.name,
            feature_rows_ref=args.feature_rows.name,
            run_id=run_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic,
        )
        written = write_runner_dry_run_report(payload, args.output_root / run_id)
    except TrainingRunnerDryRunError as exc:
        print(f"FAIL training runner dry-run: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training runner dry-run: {written['status']}")
        print(f"Report: {written['paths']['training_runner_dry_run_markdown']}")
        print(f"Next: {written.get('next_step', 'unknown')}")
    if args.require_ready and written.get("status") not in READY_STATUSES:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
