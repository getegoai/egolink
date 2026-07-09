"""Run the D2 -> D5 location evidence pipeline from one bounded input pair.

Input is an explicit Message Hub test-run export plus FIELD-003 field manifest.
The command writes:

- D2 location accuracy baseline report under `reports/location_accuracy/`;
- D5 location data-flywheel status under `reports/data_flywheel/`;
- a small pipeline summary under `reports/location_pipeline/`.

It does not contact hardware, query the VPS, train a model, deploy a model, or
copy raw private coordinates into the pipeline summary.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPELINE_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_pipeline"
SUMMARY_JSON = "location_d2_d5_pipeline.json"
SUMMARY_MARKDOWN = "location_d2_d5_pipeline.md"
GENERATOR_NAME = "D2_D5.location_pipeline"
GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = "egolink.location_d2_d5_pipeline.v0.1"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import analyze_location_accuracy_baseline as baseline  # noqa: E402
from scripts import summarize_location_data_flywheel as flywheel  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_path_ref(path: Path | None) -> str | None:
    return flywheel.safe_path_ref(path)


def default_run_id(generated_at: str) -> str:
    return "location-d2-d5-" + flywheel.slugify(generated_at.replace("+00:00", "Z"))


def derive_pipeline_status(d2_report: Mapping[str, Any], d5_status: Mapping[str, Any]) -> str:
    d2_status = as_dict(d2_report.get("result")).get("status")
    d5_stage = str(d5_status.get("status") or "unknown")
    if d2_status == "FAIL":
        return "d2_baseline_failed_needs_review"
    if as_dict(d5_status.get("readiness")).get("dataset_manifest_ready") is True:
        return "ready_for_founder_model_task_review"
    if d5_stage == "needs_review":
        return "needs_location_review"
    return d5_stage


def next_step_for(status: str) -> str:
    if status == "d2_baseline_failed_needs_review":
        return "Review the D2 baseline errors, then decide whether the failed run is useful as no-fix/bad-fix evidence."
    if status == "ready_for_founder_model_task_review":
        return "Founder review is required before opening any model-training task from the selected D2 samples."
    if status == "needs_location_review":
        return "Open the D5 location review packet, label/select samples, and rerun with --selection when appropriate."
    return "Review the generated D2 baseline and D5 data-flywheel reports."


def build_summary(
    *,
    run_id: str,
    generated_at: str,
    input_path: Path,
    manifest_path: Path,
    d2_report: Mapping[str, Any],
    d5_written: Mapping[str, Any],
) -> dict[str, Any]:
    d5_status = as_dict(d5_written.get("data_flywheel_status"))
    d5_manifest = as_dict(d5_written.get("dataset_manifest"))
    d2_result = as_dict(d2_report.get("result"))
    d2_metrics = as_dict(d2_report.get("metrics"))
    d5_counts = as_dict(d5_status.get("counts"))
    status = derive_pipeline_status(d2_report, d5_status)
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "input_refs": {
            "test_run_export": safe_path_ref(input_path),
            "field_manifest": safe_path_ref(manifest_path),
        },
        "d2_baseline": {
            "status": d2_result.get("status"),
            "run_id": d2_report.get("run_id"),
            "fix_rate": d2_metrics.get("fix_rate"),
            "ttff_median_s": d2_metrics.get("ttff_median_s"),
            "median_error_m": d2_metrics.get("median_error_m"),
            "p90_error_m": d2_metrics.get("p90_error_m"),
            "reference_points": d2_metrics.get("reference_point_count"),
            "attempts": d2_metrics.get("attempt_count"),
            "fixed_attempts": d2_metrics.get("fixed_attempts"),
            "no_fix_attempts": d2_metrics.get("no_fix_attempts"),
            "errors": d2_result.get("errors") or [],
            "warnings": d2_result.get("warnings") or [],
            "report_json": safe_path_ref(Path(str(d2_report.get("report_path")))) if d2_report.get("report_path") else None,
            "report_markdown": safe_path_ref(Path(str(d2_report.get("markdown_report_path"))))
            if d2_report.get("markdown_report_path")
            else None,
        },
        "d5_flywheel": {
            "status": d5_status.get("status"),
            "pipeline_stage": d5_status.get("pipeline_stage"),
            "review_records": d5_counts.get("records_total", 0),
            "needs_review_records": d5_counts.get("needs_review_records", 0),
            "dataset_manifest_status": d5_manifest.get("status"),
            "dataset_manifest_reason": d5_manifest.get("reason"),
            "model_training_ready": as_dict(d5_status.get("readiness")).get("model_training_ready", False),
            "review_packet": as_dict(d5_status.get("paths")).get("location_review_packet_markdown"),
            "dataset_manifest": as_dict(d5_status.get("paths")).get("location_dataset_manifest_markdown"),
            "status_report": as_dict(d5_status.get("paths")).get("data_flywheel_status_markdown"),
        },
        "next_step": next_step_for(status),
        "non_claims": [
            "This pipeline is offline post-field processing only.",
            "No hardware command, VPS query, model training, model evaluation, model artifact, or on-device deployment is performed.",
            "Pipeline summaries contain bounded metrics and artifact refs only, not raw private coordinates or raw payload bytes.",
        ],
    }


def render_markdown(summary: Mapping[str, Any]) -> str:
    d2 = as_dict(summary.get("d2_baseline"))
    d5 = as_dict(summary.get("d5_flywheel"))
    lines = [
        "# D2 -> D5 Location Pipeline",
        "",
        f"- Run ID: {summary.get('run_id', 'unknown')}",
        f"- Generated at: {summary.get('generated_at', 'unknown')}",
        f"- Status: {summary.get('status', 'unknown')}",
        "",
        "## D2 Baseline",
        "",
        f"- Result: {d2.get('status', 'unknown')}",
        f"- Fix rate: {d2.get('fix_rate', 'unknown')}",
        f"- TTFF median: {d2.get('ttff_median_s', 'unknown')} s",
        f"- Median / p90 error: {d2.get('median_error_m', 'unknown')} m / {d2.get('p90_error_m', 'unknown')} m",
        f"- Reference points: {d2.get('reference_points', 0)}",
        f"- Attempts: {d2.get('attempts', 0)} total / {d2.get('fixed_attempts', 0)} fixed / {d2.get('no_fix_attempts', 0)} no-fix",
        f"- Report: {d2.get('report_markdown', 'unknown')}",
        "",
        "## D5 Flywheel",
        "",
        f"- Status: {d5.get('status', 'unknown')}",
        f"- Stage: {d5.get('pipeline_stage', 'unknown')}",
        f"- Review records: {d5.get('review_records', 0)}",
        f"- Needs review: {d5.get('needs_review_records', 0)}",
        f"- Dataset manifest: {d5.get('dataset_manifest_status', 'unknown')} ({d5.get('dataset_manifest_reason', 'unknown')})",
        f"- Model training ready: {d5.get('model_training_ready', False)}",
        f"- Review packet: {d5.get('review_packet', 'unknown')}",
        f"- Manifest gate: {d5.get('dataset_manifest', 'unknown')}",
        "",
        "## Next Step",
        "",
        str(summary.get("next_step") or "Review the generated reports."),
        "",
        "## Non-Claims",
        "",
    ]
    for item in summary.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This summary intentionally omits raw coordinates, raw payload bytes, runtime JSONL contents, and private logs.",
        "",
    ]
    return "\n".join(lines)


def write_summary(summary: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    json_path = output_dir / SUMMARY_JSON
    markdown_path = output_dir / SUMMARY_MARKDOWN
    payload["paths"] = {
        "location_pipeline_json": safe_path_ref(json_path),
        "location_pipeline_markdown": safe_path_ref(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--export", dest="input_path", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", type=Path, help="Optional D5 explicit selection file.")
    parser.add_argument("--run-id", help="Stable run directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--location-output-root", type=Path, default=baseline.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--flywheel-output-root", type=Path, default=flywheel.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pipeline-output-root", type=Path, default=DEFAULT_PIPELINE_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true", help="Print the pipeline summary JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated)
    try:
        d2_report = baseline.analyze_location_accuracy_baseline(
            input_path=args.input_path,
            manifest_path=args.manifest,
            output_dir=args.location_output_root / run_id,
            created_at=generated,
        )
        d5_run_id = f"{run_id}-data-flywheel"
        d5_bundle = flywheel.build_location_data_flywheel(
            baseline_report_path=Path(str(d2_report["report_path"])),
            selection_path=args.selection,
            generated_at=generated,
            run_id=d5_run_id,
        )
        d5_written = flywheel.write_location_data_flywheel_report(
            d5_bundle,
            args.flywheel_output_root / d5_run_id,
        )
        summary = build_summary(
            run_id=run_id,
            generated_at=generated,
            input_path=args.input_path,
            manifest_path=args.manifest,
            d2_report=d2_report,
            d5_written=d5_written,
        )
        written = write_summary(summary, args.pipeline_output_root / run_id)
    except (baseline.LocationAccuracyBaselineError, flywheel.LocationDataFlywheelError) as exc:
        print(f"FAIL D2 -> D5 location pipeline: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"D2 -> D5 location pipeline: {written.get('status')} run_id={run_id}")
        print(f"Pipeline report: {as_dict(written.get('paths')).get('location_pipeline_markdown')}")
        print(f"D2 report: {as_dict(written.get('d2_baseline')).get('report_markdown')}")
        print(f"D5 report: {as_dict(written.get('d5_flywheel')).get('status_report')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
