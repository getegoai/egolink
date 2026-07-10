"""Summarize D1 field-observer samples into bounded D5 location evidence.

This is an offline, no-hardware intake path for real field observations that
are useful for the location data flywheel but are not yet a D2 accuracy
baseline. It reads `d1_field_samples.jsonl`, writes a bounded
`location_field_evidence` report, and can also create a Dashboard-compatible
D5 `data_flywheel_status`.

It does not expose raw private coordinates, train a model, claim location
accuracy, contact the VPS, or issue hardware commands.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_OBSERVATION_ROOT = REPO_ROOT / "reports" / "d1_field_observation"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_field_evidence"
FIELD_EVIDENCE_JSON = "location_field_evidence.json"
FIELD_EVIDENCE_MARKDOWN = "location_field_evidence.md"
SAMPLES_JSONL = "d1_field_samples.jsonl"
D1_OBSERVATION_REPORT_JSON = "d1_field_observation_report.json"
GENERATOR_NAME = "D5.location_field_evidence"
GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = "egolink.location_field_evidence.v0.1"
SOURCE_TYPE = "d1_location_field_evidence"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import summarize_location_data_flywheel as flywheel  # noqa: E402


class LocationFieldEvidenceError(RuntimeError):
    """Raised when a field-evidence report cannot be produced."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def bool_flag(value: object) -> bool:
    return value is True or str(value).strip().lower() == "true"


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def safe_path_ref(path: Path | None) -> str | None:
    return flywheel.safe_path_ref(path)


def stable_hash(value: str, length: int = 16) -> str:
    return flywheel.stable_hash(value, length)


def slugify(value: object) -> str:
    return flywheel.slugify(value)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LocationFieldEvidenceError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LocationFieldEvidenceError(f"Invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise LocationFieldEvidenceError(f"Expected JSON object in {path}")
    return payload


def latest_samples_path(root: Path) -> Path | None:
    candidates = [path for path in root.glob(f"**/{SAMPLES_JSONL}") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def default_run_id(samples_path: Path | None, generated_at: str) -> str:
    if samples_path is not None and samples_path.parent.name:
        return "location-field-" + slugify(samples_path.parent.name)
    return "location-field-" + slugify(generated_at.replace("+00:00", "Z"))


def load_samples(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise LocationFieldEvidenceError(f"Missing samples JSONL file: {path}") from exc
    samples: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise LocationFieldEvidenceError(f"Invalid JSONL at {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise LocationFieldEvidenceError(f"Expected JSON object at {path}:{line_number}")
        samples.append(payload)
    if not samples:
        raise LocationFieldEvidenceError(f"No samples found in {path}")
    return samples


def first_value(samples: list[Mapping[str, Any]], key: str) -> object:
    for sample in samples:
        value = sample.get(key)
        if value is not None and value != "":
            return value
    return None


def last_value(samples: list[Mapping[str, Any]], key: str) -> object:
    for sample in reversed(samples):
        value = sample.get(key)
        if value is not None and value != "":
            return value
    return None


def count_values(samples: Iterable[Mapping[str, Any]], key: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for sample in samples:
        value = sample.get(key)
        if value is None or value == "":
            continue
        counts[str(value)] += 1
    return counts


def value_delta(samples: list[Mapping[str, Any]], key: str) -> int | None:
    first = number_or_none(first_value(samples, key))
    last = number_or_none(last_value(samples, key))
    if first is None or last is None:
        return None
    return int(last - first)


def min_max_numbers(samples: list[Mapping[str, Any]], key: str) -> dict[str, Any]:
    values = [value for value in (number_or_none(sample.get(key)) for sample in samples) if value is not None]
    if not values:
        return {"first": None, "last": None, "min": None, "max": None, "delta": None}
    first = number_or_none(first_value(samples, key))
    last = number_or_none(last_value(samples, key))
    return {
        "first": first,
        "last": last,
        "min": min(values),
        "max": max(values),
        "delta": None if first is None or last is None else last - first,
    }


def gnss_state(sample: Mapping[str, Any]) -> str:
    state = str(sample.get("gnss_state") or "").strip().lower()
    if state:
        return state
    if sample.get("gnss_fix") is True:
        return "fix"
    if sample.get("gnss_fix") is False:
        return "no_fix"
    if sample.get("gnss_seen") is True:
        return "unknown"
    return "not_seen"


def first_last_sample_time(samples: list[Mapping[str, Any]], *, predicate: str | None = None) -> dict[str, Any]:
    selected = samples
    if predicate == "coordinate_seen":
        selected = [sample for sample in samples if bool_flag(sample.get("coordinate_seen"))]
    elif predicate == "gnss_fix":
        selected = [sample for sample in samples if gnss_state(sample) == "fix"]
    if not selected:
        return {"first": None, "last": None}
    return {
        "first": selected[0].get("collected_at"),
        "last": selected[-1].get("collected_at"),
    }


def source_report_ref(
    *,
    samples_path: Path,
    d1_report_path: Path | None,
    d1_report: Mapping[str, Any] | None,
    run_id: str,
    device_id: object,
) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "type": SOURCE_TYPE,
        "available": True,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "device_id": device_id,
        "samples_path": safe_path_ref(samples_path),
        "samples_sha256": flywheel.sha256_file(samples_path),
    }
    if d1_report_path is not None and d1_report is not None:
        ref.update(
            {
                "d1_observation_run_id": d1_report.get("run_id"),
                "result_status": d1_report.get("result"),
                "d1_observation_report_path": safe_path_ref(d1_report_path),
                "d1_observation_report_sha256": flywheel.sha256_file(d1_report_path),
            }
        )
    else:
        ref.update({"result_status": "unknown", "d1_observation_report_path": None})
    return ref


def build_summary(samples: list[Mapping[str, Any]], d1_report: Mapping[str, Any] | None) -> dict[str, Any]:
    successful_samples = [sample for sample in samples if sample.get("ok") is True]
    coordinate_samples = [sample for sample in samples if bool_flag(sample.get("coordinate_seen"))]
    gnss_counts = count_values(({"gnss_state": gnss_state(sample)} for sample in samples), "gnss_state")
    cell_id_counts = count_values(samples, "cell_id")
    map_mode_counts = count_values(samples, "map_mode")
    d1_gate_counts = count_values(samples, "d1_gate_status")
    latest_missing_reasons = sorted(count_values(samples, "latest_missing_coordinate_reason").keys())
    battery = min_max_numbers(samples, "battery_mv")
    soc = min_max_numbers(samples, "soc_pct")
    report_summary = as_dict(d1_report.get("summary") if d1_report else {})
    raw_success_delta = value_delta(samples, "raw_post_success_count")
    raw_failure_delta = value_delta(samples, "raw_post_failure_count")
    coordinate_event_delta = value_delta(samples, "coordinate_event_count")
    track_point_delta = value_delta(samples, "track_point_count")
    location_event_delta = value_delta(samples, "location_event_count")
    power_sample_delta = value_delta(samples, "power_sample_count")
    return {
        "samples_total": len(samples),
        "successful_samples": len(successful_samples),
        "coordinate_samples": len(coordinate_samples),
        "fetch_error_samples": len([sample for sample in samples if sample.get("ok") is False]),
        "gnss_fix_samples": int(gnss_counts.get("fix", 0)),
        "gnss_no_fix_samples": int(gnss_counts.get("no_fix", 0)),
        "gnss_unknown_samples": int(gnss_counts.get("unknown", 0)),
        "gnss_not_seen_samples": int(gnss_counts.get("not_seen", 0)),
        "cell_unique_count": len(cell_id_counts),
        "map_mode_counts": dict(sorted(map_mode_counts.items())),
        "d1_gate_status_counts": dict(sorted(d1_gate_counts.items())),
        "latest_missing_coordinate_reasons": latest_missing_reasons,
        "raw_post_success_delta": raw_success_delta,
        "raw_post_failure_delta": raw_failure_delta,
        "raw_post_success_rate_last": last_value(samples, "raw_post_success_rate"),
        "coordinate_event_delta": coordinate_event_delta,
        "track_point_delta": track_point_delta,
        "location_event_delta": location_event_delta,
        "power_sample_count_delta": power_sample_delta,
        "battery_mv": battery,
        "soc_pct": soc,
        "first_seq": first_value(samples, "last_seq"),
        "last_seq": last_value(samples, "last_seq"),
        "seq_delta": value_delta(samples, "last_seq"),
        "source_report_summary_available": bool(report_summary),
        "source_report_result": d1_report.get("result") if d1_report else None,
    }


def build_time_window(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "sample_window": first_last_sample_time(samples),
        "coordinate_sample_window": first_last_sample_time(samples, predicate="coordinate_seen"),
        "gnss_fix_sample_window": first_last_sample_time(samples, predicate="gnss_fix"),
        "device_upload_window": {
            "first": first_value(samples, "last_device_upload_at"),
            "last": last_value(samples, "last_device_upload_at"),
        },
        "location_upload_window": {
            "first": first_value(samples, "last_location_upload_at"),
            "last": last_value(samples, "last_location_upload_at"),
        },
    }


def field_review_record(
    *,
    run_id: str,
    source_ref: Mapping[str, Any],
    candidate_type: str,
    label: str,
    window_id: str,
    feature_groups: list[str],
    metrics_summary: Mapping[str, Any],
    review_reason: str,
) -> dict[str, Any]:
    return {
        "record_id": "locfield-" + stable_hash(f"{run_id}|{candidate_type}|{window_id}"),
        "session_id": run_id,
        "window_id": window_id,
        "state": "candidate",
        "candidate_type": candidate_type,
        "label": label,
        "label_review_state": "pending",
        "split_name": "unassigned",
        "split_leakage_checked": False,
        "privacy_class": "private_location_bounded_summary",
        "training_allowed": False,
        "quality_gate": "needs_review",
        "source_status": "d1_field_observation_summary",
        "device_id": source_ref.get("device_id"),
        "feature_groups": feature_groups,
        "metrics_summary": dict(metrics_summary),
        "source_report": {
            "type": source_ref.get("type"),
            "run_id": source_ref.get("run_id"),
            "samples_sha256": source_ref.get("samples_sha256"),
            "d1_observation_report_sha256": source_ref.get("d1_observation_report_sha256"),
        },
        "available_actions": list(flywheel.LOCATION_REVIEW_ACTIONS),
        "review_required": True,
        "review_reason": review_reason,
    }


def build_review_records(
    *,
    run_id: str,
    source_ref: Mapping[str, Any],
    summary: Mapping[str, Any],
    time_window: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records = [
        field_review_record(
            run_id=run_id,
            source_ref=source_ref,
            candidate_type="location_field_session",
            label="field_session_needs_review",
            window_id="field-session",
            feature_groups=["transport", "gnss", "cell_lte", "power", "map_surface"],
            metrics_summary={
                "samples_total": summary.get("samples_total"),
                "successful_samples": summary.get("successful_samples"),
                "raw_post_success_delta": summary.get("raw_post_success_delta"),
                "coordinate_samples": summary.get("coordinate_samples"),
                "sample_window": as_dict(time_window.get("sample_window")),
            },
            review_reason="real_field_session_requires_context_quality_and_privacy_review",
        )
    ]
    if int_or_zero(summary.get("gnss_fix_samples")) > 0:
        records.append(
            field_review_record(
                run_id=run_id,
                source_ref=source_ref,
                candidate_type="location_gnss_fix_window",
                label="gnss_fix_window",
                window_id="gnss-fix-window",
                feature_groups=["gnss", "transport", "field_context"],
                metrics_summary={
                    "gnss_fix_samples": summary.get("gnss_fix_samples"),
                    "gnss_fix_sample_window": as_dict(time_window.get("gnss_fix_sample_window")),
                },
                review_reason="gnss_fix_window_can_seed_d2_reference_or_quality_review_but_not_accuracy_claim",
            )
        )
    if int_or_zero(summary.get("gnss_no_fix_samples")) > 0:
        records.append(
            field_review_record(
                run_id=run_id,
                source_ref=source_ref,
                candidate_type="location_no_fix_window",
                label="no_fix_window",
                window_id="gnss-no-fix-window",
                feature_groups=["gnss", "cell_lte", "failure_reason"],
                metrics_summary={
                    "gnss_no_fix_samples": summary.get("gnss_no_fix_samples"),
                    "latest_missing_coordinate_reasons": summary.get("latest_missing_coordinate_reasons") or [],
                },
                review_reason="no_fix_windows_need_failure_reason_and_environment_label_review",
            )
        )
    if int_or_zero(summary.get("cell_unique_count")) > 1:
        records.append(
            field_review_record(
                run_id=run_id,
                source_ref=source_ref,
                candidate_type="location_cell_transition_window",
                label="cell_transition_window",
                window_id="cell-transition-window",
                feature_groups=["cell_lte", "transport", "movement_context"],
                metrics_summary={
                    "cell_unique_count": summary.get("cell_unique_count"),
                    "cell_ids_redacted": True,
                },
                review_reason="cell_transition_evidence_needs_retention_and_area_context_review",
            )
        )
    if summary.get("power_sample_count_delta") is not None or as_dict(summary.get("battery_mv")).get("first") is not None:
        records.append(
            field_review_record(
                run_id=run_id,
                source_ref=source_ref,
                candidate_type="location_power_window",
                label="field_power_window",
                window_id="power-window",
                feature_groups=["power", "transport", "field_duration"],
                metrics_summary={
                    "power_sample_count_delta": summary.get("power_sample_count_delta"),
                    "battery_mv": as_dict(summary.get("battery_mv")),
                    "soc_pct": as_dict(summary.get("soc_pct")),
                },
                review_reason="field_power_window_needs_duration_capacity_and_test_context_review",
            )
        )
    if int_or_zero(summary.get("coordinate_samples")) > 0:
        records.append(
            field_review_record(
                run_id=run_id,
                source_ref=source_ref,
                candidate_type="location_memory_coordinate_window",
                label="memory_coordinate_window",
                window_id="memory-coordinate-window",
                feature_groups=["map_surface", "gnss", "coordinate_redaction"],
                metrics_summary={
                    "coordinate_samples": summary.get("coordinate_samples"),
                    "coordinate_event_delta": summary.get("coordinate_event_delta"),
                    "track_point_delta": summary.get("track_point_delta"),
                    "coordinate_sample_window": as_dict(time_window.get("coordinate_sample_window")),
                    "raw_coordinates_exposed": False,
                },
                review_reason="coordinate_bearing_samples_are_redacted_and_need_reference_context_before_training",
            )
        )
    return records


def build_location_field_evidence(
    *,
    samples_path: Path,
    d1_report_path: Path | None = None,
    generated_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    samples = load_samples(samples_path)
    report_path = d1_report_path
    if report_path is None:
        candidate = samples_path.with_name(D1_OBSERVATION_REPORT_JSON)
        report_path = candidate if candidate.exists() else None
    d1_report = load_json(report_path)
    actual_run_id = run_id or default_run_id(samples_path, generated)
    device_id = first_value(samples, "device_id") or (d1_report or {}).get("device_id")
    source_ref = source_report_ref(
        samples_path=samples_path,
        d1_report_path=report_path,
        d1_report=d1_report,
        run_id=actual_run_id,
        device_id=device_id,
    )
    summary = build_summary(samples, d1_report)
    time_window = build_time_window(samples)
    review_records = build_review_records(
        run_id=actual_run_id,
        source_ref=source_ref,
        summary=summary,
        time_window=time_window,
    )
    warnings: list[str] = []
    if int_or_zero(summary.get("gnss_fix_samples")) == 0:
        warnings.append("gnss_fix_not_seen_in_field_samples")
    if int_or_zero(summary.get("coordinate_samples")) == 0:
        warnings.append("coordinate_samples_not_seen")
    if int_or_zero(summary.get("raw_post_failure_delta")) > 0:
        warnings.append("raw_post_failures_seen")
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "run_id": actual_run_id,
        "generated_at": generated,
        "status": "needs_review",
        "source": source_ref,
        "summary": summary,
        "time_window": time_window,
        "review_records": review_records,
        "candidate_type_counts": dict(
            sorted(Counter(str(record.get("candidate_type") or "unknown") for record in review_records).items())
        ),
        "privacy": {
            "raw_coordinates_exposed": False,
            "exact_coordinates_copied": False,
            "cell_ids_listed": False,
            "samples_payload_copied": False,
        },
        "readiness": {
            "d2_accuracy_baseline_ready": False,
            "dataset_manifest_ready": False,
            "model_training_ready": False,
            "reason": "reference_manifest_and_reviewed_labels_missing",
        },
        "warnings": warnings,
        "blockers": [
            "reference_manifest_missing_for_d2_accuracy",
            "label_review_pending",
            "privacy_review_pending",
            "split_leakage_review_pending",
            "founder_model_task_approval_required",
        ],
        "next_step": (
            "Use this as D5 review evidence, or pair the next field run with a FIELD-003 reference manifest "
            "to produce a D2 accuracy baseline."
        ),
        "non_claims": [
            "This report is field evidence intake only.",
            "No D2 location accuracy baseline, median error, fix-rate claim, or TTFF claim is produced.",
            "No raw private coordinates, raw payload bytes, or cell-ID lists are copied into this report.",
            "No model training, evaluation, artifact export, or on-device deployment has run.",
        ],
    }


def source_ref_from_field_report(report: Mapping[str, Any]) -> dict[str, Any]:
    source = as_dict(report.get("source"))
    return {
        "type": SOURCE_TYPE,
        "available": True,
        "schema_version": report.get("schema_version"),
        "run_id": report.get("run_id"),
        "result_status": report.get("status"),
        "device_id": source.get("device_id"),
        "samples_path": source.get("samples_path"),
        "samples_sha256": source.get("samples_sha256"),
        "d1_observation_run_id": source.get("d1_observation_run_id"),
        "d1_observation_report_path": source.get("d1_observation_report_path"),
        "d1_observation_report_sha256": source.get("d1_observation_report_sha256"),
    }


def build_field_data_flywheel(
    *,
    field_report: Mapping[str, Any],
    generated_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or str(field_report.get("generated_at") or utc_now())
    actual_run_id = run_id or f"{field_report.get('run_id', 'location-field')}-data-flywheel"
    source_ref = source_ref_from_field_report(field_report)
    review_records = [record for record in field_report.get("review_records", []) or [] if isinstance(record, dict)]
    dataset_manifest = flywheel.build_dataset_manifest(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        review_records=review_records,
        selections=[],
    )
    review_packet = flywheel.build_review_packet(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        review_records=review_records,
    )
    status = field_status_from_artifacts(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        field_report=field_report,
        review_records=review_records,
        dataset_manifest=dataset_manifest,
    )
    return {
        "data_flywheel_status": status,
        "review_packet": review_packet,
        "dataset_manifest": dataset_manifest,
    }


def field_status_from_artifacts(
    *,
    generated_at: str,
    run_id: str,
    source_ref: Mapping[str, Any],
    field_report: Mapping[str, Any],
    review_records: list[dict[str, Any]],
    dataset_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    summary = as_dict(field_report.get("summary"))
    pending_records = len([record for record in review_records if record.get("label_review_state") == "pending"])
    type_counts = Counter(str(record.get("candidate_type") or "unknown") for record in review_records)
    state_counts = Counter(str(record.get("state") or "unknown") for record in review_records)
    quality_gate_counts = Counter(str(record.get("quality_gate") or "unknown") for record in review_records)
    label_counts = Counter(str(record.get("label_review_state") or "unknown") for record in review_records)
    dataset_ready = dataset_manifest.get("status") == "ready_for_evaluation_handoff"
    blockers = [
        "reference_manifest_missing_for_d2_accuracy",
        "label_review_pending",
        "privacy_review_pending",
        "split_leakage_review_pending",
        str(dataset_manifest.get("reason") or "dataset_manifest_not_ready"),
        "founder_model_task_approval_required",
    ]
    return {
        "schema_version": flywheel.STATUS_SCHEMA_VERSION,
        "builder_version": "d5-location-field.0",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "needs_review",
        "pipeline_stage": "field_evidence_review_packet_pending",
        "source_reports": [dict(source_ref)],
        "candidate_store": {
            "available": False,
            "reason": "location_field_file_review_packet_only",
            "schema_version": flywheel.REVIEW_PACKET_SCHEMA_VERSION,
            "latest_updated_at": generated_at,
        },
        "counts": {
            "sessions_total": 1,
            "records_total": len(review_records),
            "needs_review_records": pending_records,
            "training_allowed_records": 0,
            "reviewed_training_candidate_records": 0,
            "experiment_input_records": 0,
            "location_baseline_reports": 0,
            "reference_points": 0,
            "location_attempts": 0,
            "fixed_attempts": 0,
            "no_fix_attempts": 0,
            "location_field_evidence_reports": 1,
            "field_samples": int_or_zero(summary.get("samples_total")),
            "field_successful_samples": int_or_zero(summary.get("successful_samples")),
            "field_coordinate_samples": int_or_zero(summary.get("coordinate_samples")),
            "field_gnss_fix_samples": int_or_zero(summary.get("gnss_fix_samples")),
            "field_gnss_no_fix_samples": int_or_zero(summary.get("gnss_no_fix_samples")),
            "field_gnss_unknown_samples": int_or_zero(summary.get("gnss_unknown_samples")),
            "field_unique_cell_count": int_or_zero(summary.get("cell_unique_count")),
            "field_raw_post_success_delta": summary.get("raw_post_success_delta"),
            "field_raw_post_failure_delta": summary.get("raw_post_failure_delta"),
            "field_track_point_delta": summary.get("track_point_delta"),
            "field_power_sample_count_delta": summary.get("power_sample_count_delta"),
        },
        "state_counts": dict(sorted(state_counts.items())),
        "candidate_type_counts": dict(sorted(type_counts.items())),
        "quality_gate_counts": dict(sorted(quality_gate_counts.items())),
        "label_review_state_counts": dict(sorted(label_counts.items())),
        "review": {
            "label_review_pending_records": pending_records,
            "split_leakage_unchecked_records": pending_records,
            "privacy_or_consent_blocked_records": pending_records,
            "quality_blocked_records": 0,
        },
        "review_queue": {
            "schema_version": flywheel.REVIEW_QUEUE_SCHEMA_VERSION,
            "available": True,
            "pending_records": pending_records,
            "sample_records": review_records[:5],
            "available_actions": list(flywheel.LOCATION_REVIEW_ACTIONS),
        },
        "readiness": {
            "model_training_ready": False,
            "reason": "field_evidence_requires_reference_manifest_label_and_founder_review",
            "dataset_manifest_ready": dataset_ready,
            "training_server_ready": False,
            "on_device_deployment_ready": False,
        },
        "warnings": sorted(set(field_report.get("warnings", []) or [])),
        "blockers": sorted(set(blockers)),
        "next_step": (
            "Review the field evidence packet, then collect a D2 run with FIELD-003 reference points for "
            "accuracy metrics when possible."
        ),
        "non_claims": [
            "No location accuracy baseline or AI location model training has run.",
            "No on-device model has been deployed.",
            "No raw private coordinates, cell-ID lists, or raw payload bytes are exposed in the Dashboard summary.",
            "Field evidence remains training-disallowed until explicit label, privacy, quality, split, and founder review.",
        ],
    }


def render_field_evidence_markdown(report: Mapping[str, Any]) -> str:
    summary = as_dict(report.get("summary"))
    time_window = as_dict(report.get("time_window"))
    battery = as_dict(summary.get("battery_mv"))
    soc = as_dict(summary.get("soc_pct"))
    lines = [
        "# D5 Location Field Evidence",
        "",
        f"- Run ID: {report.get('run_id', 'unknown')}",
        f"- Generated at: {report.get('generated_at', 'unknown')}",
        f"- Status: {report.get('status', 'unknown')}",
        f"- Samples: {summary.get('samples_total', 0)} total / {summary.get('successful_samples', 0)} ok",
        f"- Coordinates: {summary.get('coordinate_samples', 0)} coordinate-bearing samples (redacted)",
        f"- GNSS: {summary.get('gnss_fix_samples', 0)} fix / {summary.get('gnss_no_fix_samples', 0)} no-fix / {summary.get('gnss_unknown_samples', 0)} unknown",
        f"- LTE cells: {summary.get('cell_unique_count', 0)} unique IDs (IDs redacted)",
        f"- Raw POST delta: {summary.get('raw_post_success_delta', 'unknown')} ok / {summary.get('raw_post_failure_delta', 'unknown')} fail",
        f"- Track delta: {summary.get('track_point_delta', 'unknown')}",
        f"- Power samples delta: {summary.get('power_sample_count_delta', 'unknown')}",
        f"- Battery mV: {battery.get('first', 'unknown')} -> {battery.get('last', 'unknown')} (min {battery.get('min', 'unknown')}, max {battery.get('max', 'unknown')})",
        f"- SoC: {soc.get('first', 'unknown')} -> {soc.get('last', 'unknown')}",
        "",
        "## Windows",
        "",
        f"- Samples: {as_dict(time_window.get('sample_window')).get('first')} -> {as_dict(time_window.get('sample_window')).get('last')}",
        f"- Coordinate samples: {as_dict(time_window.get('coordinate_sample_window')).get('first')} -> {as_dict(time_window.get('coordinate_sample_window')).get('last')}",
        f"- GNSS fixes: {as_dict(time_window.get('gnss_fix_sample_window')).get('first')} -> {as_dict(time_window.get('gnss_fix_sample_window')).get('last')}",
        "",
        "## Review Records",
        "",
    ]
    for item in report.get("review_records", []) or []:
        lines.append(
            f"- {item.get('record_id', 'unknown')}: {item.get('candidate_type', 'unknown')} / "
            f"{item.get('label', 'unknown')} / {item.get('label_review_state', 'unknown')}"
        )
    if not report.get("review_records"):
        lines.append("- none")
    lines += [
        "",
        "## Next Step",
        "",
        str(report.get("next_step") or "Review the field evidence packet."),
        "",
        "## Non-Claims",
        "",
    ]
    for item in report.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This report contains bounded counts and review records only. It intentionally omits raw coordinates, raw JSONL rows, cell-ID lists, raw payload bytes, and private logs.",
        "",
    ]
    return "\n".join(lines)


def write_location_field_evidence(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / FIELD_EVIDENCE_JSON
    markdown_path = output_dir / FIELD_EVIDENCE_MARKDOWN
    payload = dict(report)
    payload["paths"] = {
        "location_field_evidence_json": safe_path_ref(json_path),
        "location_field_evidence_markdown": safe_path_ref(markdown_path),
    }
    flywheel.write_json(json_path, payload)
    markdown_path.write_text(render_field_evidence_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, help="Path to d1_field_samples.jsonl.")
    parser.add_argument(
        "--field-observation-root",
        type=Path,
        default=DEFAULT_FIELD_OBSERVATION_ROOT,
        help="Root searched for the latest d1_field_samples.jsonl when --samples is omitted.",
    )
    parser.add_argument("--d1-report", type=Path, help="Optional matching d1_field_observation_report.json.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--flywheel-output-root", type=Path, default=flywheel.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Stable field evidence report directory name.")
    parser.add_argument("--flywheel-run-id", help="Stable D5 data-flywheel report directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--skip-flywheel", action="store_true", help="Only write the location_field_evidence report.")
    parser.add_argument("--json", action="store_true", help="Print the field evidence JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    samples_path = args.samples or latest_samples_path(args.field_observation_root)
    if samples_path is None:
        print(f"FAIL D5 location field evidence: no {SAMPLES_JSONL} found", file=sys.stderr)
        return 1
    try:
        generated = args.generated_at or utc_now()
        run_id = args.run_id or default_run_id(samples_path, generated)
        field_report = build_location_field_evidence(
            samples_path=samples_path,
            d1_report_path=args.d1_report,
            generated_at=generated,
            run_id=run_id,
        )
        written = write_location_field_evidence(field_report, args.output_root / run_id)
        if not args.skip_flywheel:
            flywheel_run_id = args.flywheel_run_id or f"{run_id}-data-flywheel"
            d5_bundle = build_field_data_flywheel(
                field_report=written,
                generated_at=generated,
                run_id=flywheel_run_id,
            )
            d5_written = flywheel.write_location_data_flywheel_report(
                d5_bundle,
                args.flywheel_output_root / flywheel_run_id,
            )
            written["data_flywheel"] = {
                "run_id": flywheel_run_id,
                "status": as_dict(d5_written.get("data_flywheel_status")).get("status"),
                "status_report": as_dict(as_dict(d5_written.get("data_flywheel_status")).get("paths")).get(
                    "data_flywheel_status_markdown"
                ),
                "review_packet": as_dict(as_dict(d5_written.get("data_flywheel_status")).get("paths")).get(
                    "location_review_packet_markdown"
                ),
                "dataset_manifest": as_dict(as_dict(d5_written.get("data_flywheel_status")).get("paths")).get(
                    "location_dataset_manifest_markdown"
                ),
            }
            written = write_location_field_evidence(written, args.output_root / run_id)
    except (LocationFieldEvidenceError, flywheel.LocationDataFlywheelError) as exc:
        print(f"FAIL D5 location field evidence: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = as_dict(written.get("summary"))
        paths = as_dict(written.get("paths"))
        print(f"D5 location field evidence: {written.get('status')} run_id={written.get('run_id')}")
        print(f"Report: {paths.get('location_field_evidence_markdown')}")
        print(f"Samples: {summary.get('samples_total', 0)}")
        print(f"Review records: {len(written.get('review_records', []) or [])}")
        if written.get("data_flywheel"):
            fly = as_dict(written.get("data_flywheel"))
            print(f"D5 status: {fly.get('status')} report={fly.get('status_report')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
