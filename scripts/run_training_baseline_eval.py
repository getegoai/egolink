"""Run bounded baseline evaluation over Ego Link training feature rows.

This command is the first local evaluation bridge after TRAIN-005. It consumes
an explicit TRAIN-004 feature manifest, TRAIN-004 feature-row JSONL, and
TRAIN-005 runner dry-run report, then writes aggregate baseline metrics. It
does not train a model, produce model artifacts, call a training server, or
change on-device behavior.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_baseline_evals"
BASELINE_EVAL_SCHEMA_VERSION = "egolink.training_baseline_eval.v0.1"
BASELINE_EVAL_BUILDER_VERSION = "train-006.0"
READY_FEATURE_STATUSES = {"ready_for_feature_runner", "ready_for_synthetic_feature_dry_run"}
READY_RUNNER_DRY_RUN_STATUSES = {"ready_for_runner_execution", "synthetic_runner_dry_run_complete"}
READY_STATUSES = {"baseline_eval_complete", "synthetic_baseline_eval_complete"}


class TrainingBaselineEvalError(RuntimeError):
    """Raised when a baseline evaluation input cannot be read safely."""


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
        raise TrainingBaselineEvalError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingBaselineEvalError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingBaselineEvalError(f"{label} JSON must be an object")
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


def eval_id_for(manifest: Mapping[str, Any], created_at: str) -> str:
    feature_set_id = slug_id(manifest.get("feature_set_id") or "feature-set")
    digest = hashlib.sha1(f"{feature_set_id}|baseline|{created_at}".encode("utf-8")).hexdigest()[:8]
    return f"{feature_set_id}-baseline-eval-{digest}"


def row_label(row: Mapping[str, Any]) -> str:
    return str(as_dict(row.get("target")).get("label") or "unknown")


def row_risk_type(row: Mapping[str, Any]) -> str:
    return str(as_dict(as_dict(row.get("target")).get("model_labels")).get("risk_type") or "unknown")


def row_candidate_type(row: Mapping[str, Any]) -> str:
    return str(as_dict(row.get("features")).get("candidate_type") or as_dict(row.get("source")).get("candidate_type") or "unknown")


def row_source_status(row: Mapping[str, Any]) -> str:
    return str(as_dict(row.get("source")).get("source_status") or as_dict(row.get("features")).get("source_status") or "unknown")


def is_synthetic_row(row: Mapping[str, Any]) -> bool:
    source = as_dict(row.get("source"))
    if source.get("synthetic") is True:
        return True
    return "synthetic" in row_source_status(row).lower()


def count_by(rows: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    values: Counter[str] = Counter()
    for row in rows:
        if field == "label":
            values[row_label(row)] += 1
        elif field == "risk_type":
            values[row_risk_type(row)] += 1
        elif field == "candidate_type":
            values[row_candidate_type(row)] += 1
        elif field == "source_status":
            values[row_source_status(row)] += 1
        elif field == "split_name":
            values[str(row.get("split_name") or "unknown")] += 1
    return dict(sorted(values.items()))


def rows_by_split(rows: list[Mapping[str, Any]], split_name: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if str(row.get("split_name") or "unknown") == split_name]


def synthetic_row_count(rows: list[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if is_synthetic_row(row))


def feature_set_mismatch_count(rows: list[Mapping[str, Any]], feature_set_id: str) -> int:
    return sum(1 for row in rows if row.get("feature_set_id") != feature_set_id)


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
        if not as_dict(target.get("model_labels")).get("risk_type"):
            missing["target.model_labels.risk_type"] += 1
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


def majority_value(values: list[str]) -> str:
    counts = Counter(values)
    if not counts:
        return "unknown"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def accuracy_summary(total: int, correct: int) -> dict[str, Any]:
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 6) if total else None,
    }


def candidate_type_risk_baseline(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row_candidate_type(row) == row_risk_type(row))
    by_split: dict[str, Any] = {}
    for split in sorted({str(row.get("split_name") or "unknown") for row in rows}):
        split_rows = rows_by_split(rows, split)
        split_correct = sum(1 for row in split_rows if row_candidate_type(row) == row_risk_type(row))
        by_split[split] = accuracy_summary(len(split_rows), split_correct)
    return {
        "name": "candidate_type_risk_baseline",
        "prediction_rule": "predict target.model_labels.risk_type from features.candidate_type",
        "scope": "integration_check_only",
        "overall": accuracy_summary(total, correct),
        "by_split": by_split,
    }


def majority_label_baseline(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    train_rows = rows_by_split(rows, "train")
    fallback_scope = "train_split" if train_rows else "all_rows_fallback"
    source_rows = train_rows or rows
    predicted = majority_value([row_label(row) for row in source_rows])
    total = len(rows)
    correct = sum(1 for row in rows if row_label(row) == predicted)
    by_split: dict[str, Any] = {}
    for split in sorted({str(row.get("split_name") or "unknown") for row in rows}):
        split_rows = rows_by_split(rows, split)
        split_correct = sum(1 for row in split_rows if row_label(row) == predicted)
        by_split[split] = accuracy_summary(len(split_rows), split_correct)
    return {
        "name": "majority_label_baseline",
        "prediction_rule": "predict one majority target.label learned from train split only",
        "training_scope": fallback_scope,
        "predicted_label": predicted,
        "overall": accuracy_summary(total, correct),
        "by_split": by_split,
    }


def derive_status(
    *,
    manifest: Mapping[str, Any],
    runner_dry_run: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    row_error: str | None,
    missing_fields: Mapping[str, int],
    leakage: Mapping[str, int],
    synthetic_rows: int,
    allow_synthetic: bool,
) -> str:
    if manifest.get("status") not in READY_FEATURE_STATUSES:
        return "blocked_feature_manifest_not_ready"
    if runner_dry_run.get("status") not in READY_RUNNER_DRY_RUN_STATUSES:
        return "blocked_runner_dry_run_not_ready"
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
        return "synthetic_baseline_eval_complete"
    return "baseline_eval_complete"


def status_reason(status: str) -> str:
    return {
        "blocked_feature_manifest_not_ready": "feature_manifest_status_is_not_ready",
        "blocked_runner_dry_run_not_ready": "train005_runner_dry_run_is_not_ready",
        "blocked_feature_rows_unreadable": "feature_rows_jsonl_cannot_be_read_or_parsed",
        "blocked_no_feature_rows": "feature_manifest_has_no_rows",
        "blocked_feature_rows_mismatch": "feature_rows_do_not_match_manifest_feature_set_or_count",
        "blocked_incomplete_feature_rows": "feature_rows_missing_required_bounded_fields",
        "blocked_target_leakage_guard": "target_labels_must_not_be_inside_feature_fields",
        "blocked_synthetic_without_ack": "synthetic_rows_require_explicit_allow_synthetic",
        "synthetic_baseline_eval_complete": "synthetic_rows_evaluated_for_runner_integration_only",
        "baseline_eval_complete": "baseline_metrics_written_from_reviewed_feature_rows",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == "baseline_eval_complete":
        return "Compare against a real local training runner, then write artifact refs and footprint evidence in later tasks."
    if status == "synthetic_baseline_eval_complete":
        return "Use this only to exercise metrics plumbing, then repeat with reviewed real field/session rows before model claims."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for integration testing, or provide reviewed real field/session rows."
    if status == "blocked_runner_dry_run_not_ready":
        return "Rerun TRAIN-005 until the runner-input dry-run passes."
    if status == "blocked_target_leakage_guard":
        return "Regenerate feature rows so target labels stay under target and outside features."
    if status == "blocked_incomplete_feature_rows":
        return "Regenerate TRAIN-004 feature rows with complete bounded row fields."
    if status == "blocked_feature_rows_mismatch":
        return "Rerun with the JSONL rows produced beside the named feature manifest."
    if status == "blocked_feature_manifest_not_ready":
        return "Rerun TRAIN-004 until the feature manifest is ready."
    return "Fix the named blocker, then rerun TRAIN-006."


def build_baseline_eval_report(
    manifest: Mapping[str, Any],
    runner_dry_run: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    row_error: str | None,
    feature_manifest_ref: str,
    feature_rows_ref: str,
    runner_dry_run_ref: str,
    eval_id: str,
    created_at: str,
    allow_synthetic: bool,
) -> dict[str, Any]:
    missing_fields = missing_required_row_fields(rows)
    leakage = target_leakage_violations(rows)
    synthetic_rows = synthetic_row_count(rows)
    status = derive_status(
        manifest=manifest,
        runner_dry_run=runner_dry_run,
        rows=rows,
        row_error=row_error,
        missing_fields=missing_fields,
        leakage=leakage,
        synthetic_rows=synthetic_rows,
        allow_synthetic=allow_synthetic,
    )
    feature_rows = as_dict(manifest.get("feature_rows"))
    dataset = as_dict(manifest.get("dataset"))
    runner_rows = as_dict(runner_dry_run.get("feature_rows"))
    expected_rows = as_int(feature_rows.get("row_count"))
    feature_set_id = str(manifest.get("feature_set_id") or "unknown")
    ready = status in READY_STATUSES
    baselines = [candidate_type_risk_baseline(rows), majority_label_baseline(rows)] if ready else []
    metric_scope = "synthetic_integration_only" if synthetic_rows else "reviewed_engineering_dataset"
    return {
        "schema_version": BASELINE_EVAL_SCHEMA_VERSION,
        "builder_version": BASELINE_EVAL_BUILDER_VERSION,
        "eval_id": eval_id,
        "created_at": created_at,
        "status": status,
        "reason": status_reason(status),
        "source_refs": {
            "feature_manifest_ref": feature_manifest_ref,
            "feature_rows_ref": feature_rows_ref,
            "runner_dry_run_ref": runner_dry_run_ref,
        },
        "feature_manifest": {
            "feature_set_id": feature_set_id,
            "status": manifest.get("status"),
            "reason": manifest.get("reason"),
            "feature_scope": feature_rows.get("feature_scope"),
            "target_separated_from_features": feature_rows.get("target_separated_from_features", False),
        },
        "runner_dry_run": {
            "run_id": runner_dry_run.get("run_id"),
            "status": runner_dry_run.get("status"),
            "runner_input_gate": as_dict(runner_dry_run.get("gates")).get("runner_input"),
            "dry_run_only": as_dict(runner_dry_run.get("runner")).get("dry_run_only", False),
        },
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "eligible_records": dataset.get("eligible_records", 0),
            "synthetic_records": dataset.get("synthetic_records", 0),
        },
        "feature_rows": {
            "expected_row_count": expected_rows,
            "actual_row_count": len(rows),
            "row_count_matches": len(rows) == expected_rows,
            "runner_actual_row_count": runner_rows.get("actual_row_count"),
            "runner_row_count_matches": runner_rows.get("row_count_matches"),
            "feature_set_mismatch_count": feature_set_mismatch_count(rows, feature_set_id),
            "split_counts": count_by(rows, "split_name"),
            "label_counts": count_by(rows, "label"),
            "risk_type_counts": count_by(rows, "risk_type"),
            "candidate_type_counts": count_by(rows, "candidate_type"),
            "source_status_counts": count_by(rows, "source_status"),
            "synthetic_rows": synthetic_rows,
            "synthetic_allowed_for_eval": bool(allow_synthetic),
        },
        "checks": {
            "feature_manifest_ready": manifest.get("status") in READY_FEATURE_STATUSES,
            "runner_dry_run_ready": runner_dry_run.get("status") in READY_RUNNER_DRY_RUN_STATUSES,
            "feature_rows_readable": row_error is None,
            "feature_rows_error": row_error,
            "row_count_matches": len(rows) == expected_rows,
            "required_row_fields": "pass" if not missing_fields else "fail",
            "missing_row_fields": dict(missing_fields),
            "target_leakage_guard": "pass" if not leakage else "fail",
            "target_leakage_violations": dict(leakage),
            "synthetic_row_policy": "acknowledged" if synthetic_rows and allow_synthetic else (
                "blocked" if synthetic_rows else "not_present"
            ),
        },
        "metrics": {
            "scope": metric_scope,
            "measured_from_rows": ready,
            "classification": {
                "baselines": baselines,
                "product_performance_claim": False,
                "release_metric": False,
            },
            "operations": "not_run",
            "footprint": "not_run",
            "power": "not_run",
        },
        "gates": {
            "baseline_evaluation": "pass" if ready else "blocked",
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
            "No model weights, model card, or model artifacts are produced.",
            "Synthetic baseline metrics are integration metrics only and are not product performance evidence.",
            "No real-world model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
            "No firmware, public protocol, Message Hub ingest, OTA, or on-device inference behavior changed.",
            "The report contains aggregate counts and baseline summaries only, not raw feature rows or candidate records.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    feature_rows = as_dict(payload.get("feature_rows"))
    metrics = as_dict(payload.get("metrics"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Training Baseline Evaluation",
        "",
        f"- Eval ID: {payload.get('eval_id', 'unknown')}",
        f"- Created at: {payload.get('created_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Rows: {feature_rows.get('actual_row_count', 0)} / expected {feature_rows.get('expected_row_count', 0)}",
        f"- Synthetic rows: {feature_rows.get('synthetic_rows', 0)}",
        f"- Metric scope: {metrics.get('scope', 'unknown')}",
        "",
        "## Baselines",
        "",
    ]
    baselines = as_dict(metrics.get("classification")).get("baselines") or []
    if baselines:
        for baseline in baselines:
            overall = as_dict(as_dict(baseline).get("overall"))
            lines.append(
                f"- {as_dict(baseline).get('name', 'unknown')}: "
                f"{overall.get('correct', 0)}/{overall.get('total', 0)} "
                f"accuracy={overall.get('accuracy')}"
            )
    else:
        lines.append("- none")
    lines += [
        "",
        "## Checks",
        "",
    ]
    for key, value in sorted(as_dict(payload.get("checks")).items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- Baseline eval JSON: {paths.get('training_baseline_eval_json', 'unknown')}",
        f"- Baseline eval Markdown: {paths.get('training_baseline_eval_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This report is a bounded TRAIN-006 evaluation bridge. It does not contain raw recordings, raw candidate records, candidate DB files, runtime JSONL logs, private coordinates, private training endpoints, model weights, model cards, measured footprint, measured latency, or measured power.",
        "",
    ]
    return "\n".join(lines)


def write_baseline_eval_report(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_baseline_eval.json"
    markdown_path = output_dir / "training_baseline_eval.md"
    written = dict(payload)
    written["paths"] = {
        "training_baseline_eval_json": bounded_path(json_path),
        "training_baseline_eval_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded Ego Link training baseline evaluation.")
    parser.add_argument("--feature-manifest", type=Path, required=True, help="TRAIN-004 training_feature_manifest.json.")
    parser.add_argument("--feature-rows", type=Path, required=True, help="TRAIN-004 training_feature_rows.jsonl.")
    parser.add_argument("--runner-dry-run", type=Path, required=True, help="TRAIN-005 training_runner_dry_run.json.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--eval-id", help="Stable baseline evaluation ID.")
    parser.add_argument("--created-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic rows for integration-only metrics.")
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until the baseline eval passes.")
    parser.add_argument("--json", action="store_true", help="Print the bounded baseline eval JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_json(args.feature_manifest, label="feature manifest")
        runner_dry_run = load_json(args.runner_dry_run, label="runner dry-run")
        rows, row_error = load_jsonl_rows(args.feature_rows)
        created_at = args.created_at or utc_now()
        eval_id = args.eval_id or eval_id_for(manifest, created_at)
        payload = build_baseline_eval_report(
            manifest,
            runner_dry_run,
            rows,
            row_error=row_error,
            feature_manifest_ref=args.feature_manifest.name,
            feature_rows_ref=args.feature_rows.name,
            runner_dry_run_ref=args.runner_dry_run.name,
            eval_id=eval_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic,
        )
        written = write_baseline_eval_report(payload, args.output_root / eval_id)
    except TrainingBaselineEvalError as exc:
        print(f"FAIL training baseline eval: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training baseline eval: {written['status']}")
        print(f"Report: {written['paths']['training_baseline_eval_markdown']}")
        print(f"Next: {written.get('next_step', 'unknown')}")
    if args.require_ready and written.get("status") not in READY_STATUSES:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
