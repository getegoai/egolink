"""Export bounded feature rows for a future Ego Link training runner.

This command consumes a reviewed TRAIN-001 dataset manifest and a TRAIN-003
training-run preflight report. It writes manifest-level feature rows only; it
does not read raw recordings, train a model, evaluate a model, or produce model
artifacts.
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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "training_features"
FEATURE_MANIFEST_SCHEMA_VERSION = "egolink.training_feature_manifest.v0.1"
FEATURE_ROW_SCHEMA_VERSION = "egolink.training_feature_row.v0.1"
FEATURE_BUILDER_VERSION = "train-004.0"
READY_STATUSES = {"ready_for_feature_runner", "ready_for_synthetic_feature_dry_run"}


class TrainingFeatureManifestError(RuntimeError):
    """Raised when a feature-manifest input cannot be read safely."""


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


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def slug_id(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "unknown"


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrainingFeatureManifestError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingFeatureManifestError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TrainingFeatureManifestError(f"{label} JSON must be an object")
    return payload


def bounded_path(path: Path) -> str:
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(REPO_ROOT.resolve())
        return str(rel)
    except (OSError, ValueError):
        return path.name


def feature_set_id_for(dataset: Mapping[str, Any], preflight: Mapping[str, Any], generated_at: str) -> str:
    dataset_id = slug_id(dataset.get("dataset_id") or "dataset")
    preflight_id = slug_id(preflight.get("run_id") or "preflight")
    digest = hashlib.sha1(f"{dataset_id}|{preflight_id}|{generated_at}".encode("utf-8")).hexdigest()[:8]
    return f"{dataset_id}-features-{digest}"


def count_by(records: list[Any], key: str) -> dict[str, int]:
    values: Counter[str] = Counter()
    for record in records:
        if isinstance(record, dict):
            values[str(record.get(key) or "unknown")] += 1
    return dict(sorted(values.items()))


def normalize_feature_groups(value: Any) -> list[str]:
    groups: list[str] = []
    for item in as_list(value):
        group = slug_id(item)
        if group and group != "unknown" and group not in groups:
            groups.append(group)
    return groups


def is_synthetic_record(record: Mapping[str, Any]) -> bool:
    source_status = str(record.get("source_status") or "").lower()
    candidate_type = str(record.get("candidate_type") or "").lower()
    return "synthetic" in source_status or "synthetic" in candidate_type


def synthetic_record_count(records: list[Any]) -> int:
    count = 0
    for record in records:
        if isinstance(record, dict) and is_synthetic_record(record):
            count += 1
    return count


def missing_required_record_fields(records: list[Any]) -> dict[str, int]:
    required = ("record_id", "session_id", "window_id", "label", "split_name", "source_manifest_hash")
    missing: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            missing["invalid_record_object"] += 1
            continue
        for field in required:
            if not record.get(field):
                missing[field] += 1
    return dict(sorted(missing.items()))


def preflight_is_ready(preflight: Mapping[str, Any]) -> bool:
    runner = as_dict(preflight.get("runner"))
    gates = as_dict(preflight.get("gates"))
    return (
        preflight.get("status") == "ready_for_training_runner"
        and bool(runner.get("ready_for_training_runner"))
        and bool(gates.get("preflight_ready"))
    )


def dataset_matches_preflight(dataset: Mapping[str, Any], preflight: Mapping[str, Any]) -> bool:
    dataset_id = dataset.get("dataset_id")
    preflight_dataset_id = as_dict(preflight.get("dataset")).get("dataset_id")
    if not dataset_id or not preflight_dataset_id:
        return True
    return dataset_id == preflight_dataset_id


def derive_status(
    *,
    dataset: Mapping[str, Any],
    preflight: Mapping[str, Any],
    records: list[Any],
    missing_fields: Mapping[str, int],
    synthetic_records: int,
    allow_synthetic: bool,
) -> str:
    if not preflight_is_ready(preflight):
        return "blocked_preflight_not_ready"
    if dataset.get("status") != "ready_for_training_handoff":
        return "blocked_dataset_not_ready"
    if not dataset_matches_preflight(dataset, preflight):
        return "blocked_source_mismatch"
    counts = as_dict(dataset.get("counts"))
    if as_int(counts.get("eligible_records")) <= 0 or not records:
        return "blocked_no_records"
    if missing_fields:
        return "blocked_incomplete_records"
    if synthetic_records and not allow_synthetic:
        return "blocked_synthetic_without_ack"
    if synthetic_records:
        return "ready_for_synthetic_feature_dry_run"
    return "ready_for_feature_runner"


def status_reason(status: str) -> str:
    return {
        "blocked_preflight_not_ready": "training_run_preflight_is_not_ready_for_runner",
        "blocked_dataset_not_ready": "dataset_manifest_status_is_not_ready_for_training_handoff",
        "blocked_source_mismatch": "dataset_manifest_does_not_match_preflight_dataset",
        "blocked_no_records": "dataset_manifest_has_no_eligible_records",
        "blocked_incomplete_records": "dataset_records_missing_required_bounded_feature_fields",
        "blocked_synthetic_without_ack": "synthetic_records_require_explicit_allow_synthetic",
        "ready_for_synthetic_feature_dry_run": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
        "ready_for_feature_runner": "bounded_feature_rows_ready_for_training_runner",
    }.get(status, "unknown")


def next_step(status: str) -> str:
    if status == "ready_for_feature_runner":
        return "Connect a training runner that consumes training_feature_rows.jsonl and writes measured metrics plus reviewed artifact refs."
    if status == "ready_for_synthetic_feature_dry_run":
        return "Use this only to dry-run runner integration, then repeat with reviewed real field/session records before model claims."
    if status == "blocked_synthetic_without_ack":
        return "Rerun with --allow-synthetic only for dry-run integration, or use reviewed real field/session data."
    if status == "blocked_incomplete_records":
        return "Rebuild the dataset manifest from reviewed candidates with complete bounded row fields."
    if status == "blocked_source_mismatch":
        return "Rerun with the dataset manifest that was used to create the named training-run preflight."
    if status == "blocked_dataset_not_ready":
        return "Complete candidate review gates and rebuild the training dataset manifest."
    if status == "blocked_preflight_not_ready":
        return "Rerun TRAIN-003 until the experiment and dataset handoff are ready for the future runner."
    return "Fix the named blocker, then rerun the feature manifest export."


def firmware_family(firmware_version: object) -> str:
    text = slug_id(firmware_version)
    if "." in text:
        return text.rsplit(".", 1)[0] or text
    return text


def feature_group_flags(groups: list[str]) -> dict[str, bool]:
    group_set = set(groups)
    return {
        "has_device_health": "device_health" in group_set,
        "has_device_status": "device_status" in group_set,
        "has_gnss_report": "gnss_report" in group_set or "location_observation" in group_set,
        "has_imu_motion": "imu_motion" in group_set or "motion" in group_set,
        "has_power": "power" in group_set or "device_power" in group_set,
    }


def build_feature_row(record: Mapping[str, Any], *, dataset_id: str, preflight_run_id: str, feature_set_id: str) -> dict[str, Any]:
    groups = normalize_feature_groups(record.get("feature_groups"))
    quality_gate = str(record.get("quality_gate") or "unknown").lower()
    source_status = str(record.get("source_status") or "unknown")
    return {
        "schema_version": FEATURE_ROW_SCHEMA_VERSION,
        "feature_set_id": feature_set_id,
        "row_id": record.get("record_id"),
        "record_id": record.get("record_id"),
        "session_id": record.get("session_id"),
        "window_id": record.get("window_id"),
        "split_name": record.get("split_name"),
        "split_group_key": record.get("split_group_key"),
        "target": {
            "label": record.get("label"),
            "label_review_state": record.get("label_review_state"),
            "model_labels": as_dict(record.get("model_labels")),
        },
        "source": {
            "candidate_type": record.get("candidate_type"),
            "device_id": record.get("device_id"),
            "feature_groups": groups,
            "source_event_type": record.get("source_event_type"),
            "source_manifest_hash": record.get("source_manifest_hash"),
            "source_status": source_status,
            "synthetic": is_synthetic_record(record),
        },
        "lineage": {
            "dataset_id": dataset_id,
            "feature_builder_version": FEATURE_BUILDER_VERSION,
            "preflight_run_id": preflight_run_id,
        },
        "features": {
            "candidate_type": record.get("candidate_type") or "unknown",
            "feature_generator_available": record.get("feature_generator_version") not in (None, "", "not_generated"),
            "feature_group_flags": feature_group_flags(groups),
            "firmware_family": firmware_family(record.get("firmware_version")),
            "label_reviewed": record.get("label_review_state") == "reviewed",
            "privacy_class": record.get("privacy_class") or "unknown",
            "quality_gate_pass": quality_gate == "pass",
            "quality_score": as_float(record.get("quality_score")),
            "source_event_type": record.get("source_event_type") or "unknown",
            "source_status": source_status,
        },
    }


def build_feature_rows(
    records: list[Any],
    *,
    dataset_id: str,
    preflight_run_id: str,
    feature_set_id: str,
    status: str,
) -> list[dict[str, Any]]:
    if status not in READY_STATUSES:
        return []
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, dict):
            rows.append(
                build_feature_row(
                    record,
                    dataset_id=dataset_id,
                    preflight_run_id=preflight_run_id,
                    feature_set_id=feature_set_id,
                )
            )
    return rows


def build_feature_manifest(
    dataset: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    dataset_manifest_ref: str,
    preflight_ref: str,
    feature_set_id: str,
    generated_at: str,
    allow_synthetic: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = as_list(dataset.get("records"))
    missing_fields = missing_required_record_fields(records)
    synthetic_records = synthetic_record_count(records)
    status = derive_status(
        dataset=dataset,
        preflight=preflight,
        records=records,
        missing_fields=missing_fields,
        synthetic_records=synthetic_records,
        allow_synthetic=allow_synthetic,
    )
    dataset_counts = as_dict(dataset.get("counts"))
    split_counts = as_dict(dataset.get("split_counts"))
    preflight_dataset = as_dict(preflight.get("dataset"))
    dataset_id = str(dataset.get("dataset_id") or "unknown")
    preflight_run_id = str(preflight.get("run_id") or "unknown")
    rows = build_feature_rows(
        records,
        dataset_id=dataset_id,
        preflight_run_id=preflight_run_id,
        feature_set_id=feature_set_id,
        status=status,
    )
    feature_groups = sorted(
        {
            group
            for record in records
            if isinstance(record, dict)
            for group in normalize_feature_groups(record.get("feature_groups"))
        }
    )
    manifest = {
        "schema_version": FEATURE_MANIFEST_SCHEMA_VERSION,
        "builder_version": FEATURE_BUILDER_VERSION,
        "feature_set_id": feature_set_id,
        "generated_at": generated_at,
        "status": status,
        "reason": status_reason(status),
        "source_refs": {
            "dataset_manifest_ref": dataset_manifest_ref,
            "preflight_ref": preflight_ref,
        },
        "dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "status": dataset.get("status"),
            "reason": dataset.get("reason"),
            "records_total": as_int(dataset_counts.get("records_total")),
            "eligible_records": as_int(dataset_counts.get("eligible_records")),
            "reviewed_training_candidate_records": as_int(
                dataset_counts.get("reviewed_training_candidate_records")
            ),
            "split_counts": split_counts,
            "label_counts": count_by(records, "label"),
            "source_status_counts": count_by(records, "source_status"),
            "synthetic_records": synthetic_records,
            "synthetic_allowed_for_dry_run": bool(allow_synthetic),
        },
        "preflight": {
            "run_id": preflight.get("run_id"),
            "status": preflight.get("status"),
            "reason": preflight.get("reason"),
            "dataset_id": preflight_dataset.get("dataset_id"),
            "runner_ready": preflight_is_ready(preflight),
            "metrics_measured": as_dict(as_dict(preflight.get("metrics_plan")).get("measured")),
        },
        "feature_rows": {
            "row_schema_version": FEATURE_ROW_SCHEMA_VERSION,
            "row_count": len(rows),
            "rows_ref": "training_feature_rows.jsonl",
            "feature_groups": feature_groups,
            "feature_scope": "manifest_summary_features",
            "target_separated_from_features": True,
        },
        "checks": {
            "dataset_ready": dataset.get("status") == "ready_for_training_handoff",
            "preflight_ready": preflight_is_ready(preflight),
            "source_match": dataset_matches_preflight(dataset, preflight),
            "has_records": bool(records) and as_int(dataset_counts.get("eligible_records")) > 0,
            "required_record_fields": "pass" if not missing_fields else "fail",
            "missing_record_fields": dict(missing_fields),
            "synthetic_record_policy": "acknowledged" if synthetic_records and allow_synthetic else (
                "blocked" if synthetic_records else "not_present"
            ),
            "label_leakage_guard": "target_separated_from_features",
        },
        "gates": {
            "feature_export": "pass" if status in READY_STATUSES else "blocked",
            "training_runner": "not_integrated",
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
            "Feature rows contain bounded manifest-summary features only, not raw IMU windows or MotionNet tensors.",
            "Synthetic feature rows are for dry-run integration only and are not release metrics.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
        ],
    }
    return manifest, rows


def render_markdown(payload: Mapping[str, Any]) -> str:
    dataset = as_dict(payload.get("dataset"))
    preflight = as_dict(payload.get("preflight"))
    checks = as_dict(payload.get("checks"))
    feature_rows = as_dict(payload.get("feature_rows"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Training Feature Manifest",
        "",
        f"- Feature set: {payload.get('feature_set_id', 'unknown')}",
        f"- Generated at: {payload.get('generated_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Reason: {payload.get('reason', 'unknown')}",
        f"- Dataset: {dataset.get('dataset_id', 'unknown')} ({dataset.get('status', 'unknown')})",
        f"- Preflight: {preflight.get('run_id', 'unknown')} ({preflight.get('status', 'unknown')})",
        f"- Rows: {feature_rows.get('row_count', 0)}",
        f"- Feature scope: {feature_rows.get('feature_scope', 'unknown')}",
        "",
        "## Checks",
        "",
    ]
    for key, value in sorted(checks.items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines += [
        "",
        "## Gates",
        "",
    ]
    for key, value in sorted(as_dict(payload.get("gates")).items()):
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- Feature manifest JSON: {paths.get('training_feature_manifest_json', 'unknown')}",
        f"- Feature rows JSONL: {paths.get('training_feature_rows_jsonl', 'unknown')}",
        f"- Feature manifest Markdown: {paths.get('training_feature_manifest_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This export contains bounded feature rows only. It does not contain raw recordings, raw candidate records, candidate DB files, runtime JSONL logs, private coordinates, private training endpoints, model weights, measured metrics, or model artifacts.",
        "",
    ]
    return "\n".join(lines)


def write_feature_manifest(payload: Mapping[str, Any], rows: list[Mapping[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_feature_manifest.json"
    rows_path = output_dir / "training_feature_rows.jsonl"
    markdown_path = output_dir / "training_feature_manifest.md"
    written = dict(payload)
    written["paths"] = {
        "training_feature_manifest_json": bounded_path(json_path),
        "training_feature_rows_jsonl": bounded_path(rows_path),
        "training_feature_manifest_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows_text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    rows_path.write_text(rows_text, encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export bounded Ego Link training feature rows.")
    parser.add_argument("--dataset-manifest", type=Path, required=True, help="TRAIN-001 training_dataset_manifest.json.")
    parser.add_argument("--preflight", type=Path, required=True, help="TRAIN-003 training_run_preflight.json.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--feature-set-id", help="Stable feature-set ID.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic-only records for dry-run integration.")
    parser.add_argument("--require-ready", action="store_true", help="Return non-zero until feature rows are ready.")
    parser.add_argument("--json", action="store_true", help="Print the bounded feature manifest JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dataset = load_json(args.dataset_manifest, label="dataset manifest")
        preflight = load_json(args.preflight, label="training run preflight")
        generated_at = args.generated_at or utc_now()
        feature_set_id = args.feature_set_id or feature_set_id_for(dataset, preflight, generated_at)
        payload, rows = build_feature_manifest(
            dataset,
            preflight,
            dataset_manifest_ref=args.dataset_manifest.name,
            preflight_ref=args.preflight.name,
            feature_set_id=feature_set_id,
            generated_at=generated_at,
            allow_synthetic=args.allow_synthetic,
        )
        written = write_feature_manifest(payload, rows, args.output_root / feature_set_id)
    except TrainingFeatureManifestError as exc:
        print(f"FAIL training feature manifest: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Training feature manifest: {written['status']}")
        print(f"Manifest: {written['paths']['training_feature_manifest_markdown']}")
        print(f"Rows: {written['paths']['training_feature_rows_jsonl']}")
        print(f"Next: {written.get('next_step', 'unknown')}")
    if args.require_ready and written.get("status") not in READY_STATUSES:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
