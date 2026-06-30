"""Evaluate EALE-P0 coverage over a DATA-001 location-fusion dataset export.

This offline ALG-002 helper reads DATA-001 `samples.jsonl` plus
`manifest.json`, then writes an evidence/failure coverage report.

It does not contact the VPS, read serial ports, flash firmware, mutate raw
evidence, or train a learned model.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_fusion_eale"
GENERATOR_NAME = "evaluate_eale_p0_dataset"
GENERATOR_VERSION = "0.1.0-alg002"
EALE_NAME = "EALE-P0"
REPORT_JSON = "eale_p0_dataset_report.json"
REPORT_MARKDOWN = "eale_p0_dataset_report.md"
FEATURE_GROUPS = [
    "gnss",
    "cell",
    "lte",
    "transport",
    "lte_http",
    "wifi",
    "imu",
    "power",
    "location_belief",
    "command",
    "runtime",
    "observability",
]
RAW_PARSE_FAILURE_STATUSES = {"partial", "checksum_failed", "unsupported", "malformed", "raw_parse_failed"}
NO_FIX_STATES = {"no_fix", "no-fix", "none", "not_fixed", "not_fix", "unfixed", "unknown"}


class DatasetEvaluationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def stable_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def present(value: object) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return value not in (None, "")


def scalar_key(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise DatasetEvaluationError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetEvaluationError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DatasetEvaluationError(f"JSON document must be an object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DatasetEvaluationError(f"failed to read JSONL: {path}: {exc}") from exc
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetEvaluationError(f"invalid JSONL at {path}:{index}: {exc}") from exc
        if not isinstance(row, dict):
            raise DatasetEvaluationError(f"JSONL row must be an object at {path}:{index}")
        rows.append(row)
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    result = as_dict(report.get("result"))
    counts = as_dict(report.get("counts"))
    coverage = as_dict(report.get("coverage"))
    eale = as_dict(report.get("eale_p0"))
    source = as_dict(report.get("source"))
    readiness = as_dict(report.get("training_readiness"))
    lines = [
        "# EALE-P0 DATA-001 Evaluation Report",
        "",
        f"- Result: {result.get('status', 'unknown')}",
        f"- Test run: {source.get('test_run_id', 'unknown')}",
        f"- Samples: {counts.get('samples', 0)}",
        f"- Model training ready: {readiness.get('model_training_ready', False)}",
        "",
        "## Key Counters",
        "",
        f"- Sample types: {json.dumps(counts.get('sample_types', {}), sort_keys=True)}",
        f"- Label states: {json.dumps(counts.get('label_states', {}), sort_keys=True)}",
        f"- Failure modes: {json.dumps(counts.get('failure_modes', {}), sort_keys=True)}",
        f"- Quality: {json.dumps(counts.get('quality_statuses', {}), sort_keys=True)}",
        "",
        "## Coverage",
        "",
        f"- Raw frame refs: {as_dict(coverage.get('lineage')).get('raw_frame_refs_total', 0)}",
        f"- Derived event refs: {as_dict(coverage.get('lineage')).get('derived_event_refs_total', 0)}",
        f"- Feature groups: {json.dumps(coverage.get('feature_groups', {}), sort_keys=True)}",
        "",
        "## EALE-P0 Coverage",
        "",
        f"- Fine candidates: {eale.get('fine_candidates', 0)}",
        f"- Unknown/no precise fix: {eale.get('unknown_no_precise_fix', 0)}",
        f"- Failure windows retained: {eale.get('failure_window_retained', 0)}",
        f"- Cell/LTE without position: {eale.get('cell_lte_without_position', 0)}",
        "",
        "## Warnings",
        "",
    ]
    warnings = as_list(result.get("warnings"))
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    errors = as_list(result.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def feature_present(sample: dict[str, Any], group: str) -> bool:
    features = as_dict(sample.get("features"))
    return present(features.get(group))


def no_fix_evidence(sample: dict[str, Any]) -> bool:
    labels = as_dict(sample.get("labels"))
    modes = {str(mode) for mode in as_list(labels.get("failure_modes"))}
    gnss = as_dict(as_dict(sample.get("features")).get("gnss"))
    state = str(gnss.get("state") or "").strip().lower()
    return "gnss_no_fix" in modes or gnss.get("fix") is False or state in NO_FIX_STATES


def fine_candidate(sample: dict[str, Any]) -> bool:
    labels = as_dict(sample.get("labels"))
    gnss = as_dict(as_dict(sample.get("features")).get("gnss"))
    return (
        sample.get("sample_type") == "known_place_calibration_window"
        or labels.get("location_state") == "Fine"
        or gnss.get("fix") is True
    )


def evaluate_dataset(
    samples: list[dict[str, Any]],
    manifest: dict[str, Any] | None = None,
    *,
    samples_path: Path | None = None,
    manifest_path: Path | None = None,
    dataset_dir: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    created_at = created_at or utc_now()
    source = as_dict(manifest.get("source"))
    test_run_id = str(
        source.get("test_run_id")
        or (samples[0].get("test_run_id") if samples else "")
        or "unknown-test-run"
    )

    sample_type_counts: Counter[str] = Counter()
    label_state_counts: Counter[str] = Counter()
    label_source_counts: Counter[str] = Counter()
    failure_mode_counts: Counter[str] = Counter()
    quality_status_counts: Counter[str] = Counter()
    quality_warning_counts: Counter[str] = Counter()
    quality_error_counts: Counter[str] = Counter()
    privacy_class_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    raw_parse_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    source_state_counts: dict[str, Counter[str]] = {group: Counter() for group in FEATURE_GROUPS}

    samples_with_raw = 0
    samples_with_derived = 0
    raw_ref_total = 0
    derived_ref_total = 0
    training_allowed = 0
    training_blocked = 0
    failure_window_retained = 0
    fine_candidates = 0
    unknown_no_precise_fix = 0
    cell_lte_without_position = 0
    raw_parse_failures_retained = 0

    for sample in samples:
        sample_type = str(sample.get("sample_type") or "unknown")
        sample_type_counts[sample_type] += 1
        if sample_type == "failure_window":
            failure_window_retained += 1

        labels = as_dict(sample.get("labels"))
        label_state = str(labels.get("location_state") or "unknown")
        label_state_counts[label_state] += 1
        label_source_counts[str(labels.get("label_source") or "unknown")] += 1
        failure_modes = [str(mode) for mode in as_list(labels.get("failure_modes"))]
        failure_mode_counts.update(failure_modes)

        quality = as_dict(sample.get("quality"))
        quality_status_counts[str(quality.get("status") or "unknown")] += 1
        quality_warning_counts.update(str(item) for item in as_list(quality.get("warnings")))
        quality_error_counts.update(str(item) for item in as_list(quality.get("errors")))

        privacy = as_dict(sample.get("privacy"))
        privacy_class_counts[str(privacy.get("privacy_class") or "unknown")] += 1
        if privacy.get("training_allowed") is True:
            training_allowed += 1
        else:
            training_blocked += 1

        split = as_dict(sample.get("split"))
        split_counts[str(split.get("name") or "unknown")] += 1

        lineage = as_dict(sample.get("lineage"))
        raw_refs = [as_dict(ref) for ref in as_list(lineage.get("raw_frame_refs"))]
        derived_refs = [as_dict(ref) for ref in as_list(lineage.get("derived_event_refs"))]
        raw_ref_total += len(raw_refs)
        derived_ref_total += len(derived_refs)
        if raw_refs:
            samples_with_raw += 1
        if derived_refs:
            samples_with_derived += 1
        raw_statuses = [str(ref.get("parse_status") or "unknown") for ref in raw_refs]
        raw_parse_counts.update(raw_statuses)
        if any(status in RAW_PARSE_FAILURE_STATUSES for status in raw_statuses) or any(
            mode in {"raw_parse_failed", "checksum_failed"} for mode in failure_modes
        ):
            raw_parse_failures_retained += 1

        features = as_dict(sample.get("features"))
        for group in FEATURE_GROUPS:
            payload = features.get(group)
            if present(payload):
                feature_counts[group] += 1
            group_payload = as_dict(payload)
            for field in ("source_status", "evidence_status", "state", "status", "type", "reason_code"):
                value = group_payload.get(field)
                if value not in (None, ""):
                    source_state_counts[group][f"{field}:{scalar_key(value)}"] += 1

        if fine_candidate(sample):
            fine_candidates += 1
        if label_state == "Unknown" and no_fix_evidence(sample):
            unknown_no_precise_fix += 1
        if label_state == "Unknown" and feature_present(sample, "cell") and (
            feature_present(sample, "lte") or feature_present(sample, "transport")
        ):
            cell_lte_without_position += 1

    errors: list[str] = []
    warnings: list[str] = []
    if not samples:
        errors.append("no_dataset_samples")
    if samples and raw_ref_total == 0:
        errors.append("no_raw_frame_lineage")
    if samples_with_raw < len(samples):
        warnings.append("some_samples_missing_raw_frame_lineage")
    if samples and derived_ref_total == 0:
        warnings.append("no_derived_event_lineage")
    if failure_window_retained:
        warnings.append("failure_windows_retained_for_diagnosis")
    if fine_candidates == 0:
        warnings.append("no_fine_location_candidates")
    if training_blocked:
        warnings.append("some_samples_blocked_from_training_by_privacy")
    if quality_status_counts.get("warn", 0) or quality_status_counts.get("fail", 0):
        warnings.append("quality_warnings_or_errors_present")

    model_training_ready = (
        bool(samples)
        and fine_candidates > 0
        and failure_window_retained == 0
        and training_blocked == 0
        and quality_status_counts.get("warn", 0) == 0
        and quality_status_counts.get("fail", 0) == 0
    )
    if not model_training_ready:
        warnings.append("dataset_not_ready_for_model_training")

    status = "fail" if errors else ("warn" if warnings else "pass")
    return {
        "report_version": "0.1.0",
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "created_at": created_at,
        },
        "algorithm": {
            "name": EALE_NAME,
            "mode": "offline_dataset_coverage",
            "learned_model": False,
        },
        "source": {
            "dataset_dir": str(dataset_dir) if dataset_dir else None,
            "samples_path": str(samples_path) if samples_path else None,
            "manifest_path": str(manifest_path) if manifest_path else None,
            "test_run_id": test_run_id,
            "dataset_generator": as_dict(manifest.get("generator")),
            "sample_schema": as_dict(manifest.get("schema")).get("sample_schema"),
        },
        "result": {
            "status": status,
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
        },
        "counts": {
            "samples": len(samples),
            "sample_types": stable_counts(sample_type_counts),
            "label_states": stable_counts(label_state_counts),
            "label_sources": stable_counts(label_source_counts),
            "failure_modes": stable_counts(failure_mode_counts),
            "quality_statuses": stable_counts(quality_status_counts),
            "quality_warnings": stable_counts(quality_warning_counts),
            "quality_errors": stable_counts(quality_error_counts),
            "privacy_classes": stable_counts(privacy_class_counts),
            "split_names": stable_counts(split_counts),
        },
        "coverage": {
            "lineage": {
                "samples_with_raw_frame_refs": samples_with_raw,
                "samples_without_raw_frame_refs": len(samples) - samples_with_raw,
                "raw_frame_refs_total": raw_ref_total,
                "samples_with_derived_event_refs": samples_with_derived,
                "samples_without_derived_event_refs": len(samples) - samples_with_derived,
                "derived_event_refs_total": derived_ref_total,
                "raw_parse_statuses": stable_counts(raw_parse_counts),
            },
            "feature_groups": {group: feature_counts.get(group, 0) for group in FEATURE_GROUPS},
            "source_state_counts": {
                group: stable_counts(counter) for group, counter in source_state_counts.items() if counter
            },
            "privacy": {
                "training_allowed": training_allowed,
                "training_blocked": training_blocked,
            },
        },
        "eale_p0": {
            "fine_candidates": fine_candidates,
            "unknown_no_precise_fix": unknown_no_precise_fix,
            "failure_window_retained": failure_window_retained,
            "raw_parse_failures_retained": raw_parse_failures_retained,
            "cell_lte_without_position": cell_lte_without_position,
            "known_place_candidates": sample_type_counts.get("known_place_calibration_window", 0),
        },
        "training_readiness": {
            "model_training_ready": model_training_ready,
            "reason": (
                "ready_for_small_supervised_experiment"
                if model_training_ready
                else "not_ready_until_labels_privacy_quality_and_fine_candidates_are_sufficient"
            ),
        },
        "release_gate_usage": {
            "can_support_release_review": status != "fail",
            "can_support_product_accuracy_claim": False,
            "can_support_learned_model_claim": False,
        },
    }


def resolve_dataset_paths(args: argparse.Namespace) -> tuple[Path | None, Path, Path]:
    dataset_dir = args.dataset_dir
    samples_path = args.samples_path
    manifest_path = args.manifest_path
    if dataset_dir is not None:
        samples_path = samples_path or dataset_dir / "samples.jsonl"
        manifest_path = manifest_path or dataset_dir / "manifest.json"
    if samples_path is None:
        raise DatasetEvaluationError("provide --dataset-dir or --samples")
    if manifest_path is None:
        raise DatasetEvaluationError("provide --manifest or a --dataset-dir containing manifest.json")
    return dataset_dir, samples_path, manifest_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path)
    parser.add_argument("--samples", dest="samples_path", type=Path)
    parser.add_argument("--manifest", dest="manifest_path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dataset_dir, samples_path, manifest_path = resolve_dataset_paths(args)
        samples = load_jsonl(samples_path)
        manifest = load_json(manifest_path)
        source = as_dict(manifest.get("source"))
        test_run_id = str(
            source.get("test_run_id")
            or (samples[0].get("test_run_id") if samples else "")
            or "unknown-test-run"
        )
        output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / test_run_id
        report = evaluate_dataset(
            samples,
            manifest,
            samples_path=samples_path,
            manifest_path=manifest_path,
            dataset_dir=dataset_dir,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        report_json = output_dir / REPORT_JSON
        report_markdown = output_dir / REPORT_MARKDOWN
        write_json(report_json, report)
        write_markdown(report_markdown, report)
    except DatasetEvaluationError as exc:
        print(f"FAIL EALE-P0 dataset evaluation: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = as_dict(report.get("result")).get("status", "unknown")
        print(f"{status.upper()} EALE-P0 dataset evaluation report={report_json}")
    return 0 if as_dict(report.get("result")).get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
