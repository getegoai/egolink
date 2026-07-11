"""Run the D2 -> D5 location evidence pipeline from one bounded input pair.

Input is a FIELD-003 field manifest plus either an existing Message Hub export,
a legacy named test-run export, or a read-only device/time-window export. The
command writes:

- D2 location accuracy baseline report under `reports/location_accuracy/`;
- D5 location data-flywheel status under `reports/data_flywheel/`;
- a small pipeline summary under `reports/location_pipeline/`.

It does not contact hardware, send device commands, train a model, deploy a
model, or copy raw private coordinates into the pipeline summary.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib import error as urlerror
from urllib import request
from urllib.parse import quote, urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPELINE_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_pipeline"
DEFAULT_GNSS_OUTPUT_ROOT = REPO_ROOT / "reports" / "gnss"
DEFAULT_TOKEN_FILE = REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"
SUMMARY_JSON = "location_d2_d5_pipeline.json"
SUMMARY_MARKDOWN = "location_d2_d5_pipeline.md"
GENERATOR_NAME = "D2_D5.location_pipeline"
GENERATOR_VERSION = "0.2.0"
SCHEMA_VERSION = "egolink.location_d2_d5_pipeline.v0.2"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import analyze_location_accuracy_baseline as baseline  # noqa: E402
from scripts import summarize_location_data_flywheel as flywheel  # noqa: E402


class LocationD2D5PipelineError(RuntimeError):
    """Raised when the post-field input cannot be resolved safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_path_ref(path: Path | None) -> str | None:
    return flywheel.safe_path_ref(path)


def default_run_id(generated_at: str) -> str:
    return "location-d2-d5-" + flywheel.slugify(generated_at.replace("+00:00", "Z"))


def read_token(token_file: Path | None) -> str | None:
    env_token = os.environ.get("EGOLINK_MESSAGE_HUB_TOKEN", "").strip()
    if env_token:
        return env_token
    if token_file and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        return token or None
    return None


def fetch_message_hub_export(
    *,
    hub_url: str,
    test_run_id: str,
    token: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    url = f"{hub_url.rstrip('/')}/api/v1/test-runs/{test_run_id}/export"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with request.urlopen(request.Request(url, headers=headers), timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        raise LocationD2D5PipelineError(
            f"Message Hub export failed with HTTP {exc.code} for test run {test_run_id}"
        ) from exc
    except (urlerror.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise LocationD2D5PipelineError(
            f"Message Hub export failed for test run {test_run_id}: {type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise LocationD2D5PipelineError("Message Hub test-run export must be a JSON object")
    return payload


def fetch_device_window_export(
    *,
    hub_url: str,
    device_id: str,
    started_at: str,
    ended_at: str,
    max_records: int,
    token: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    query = urlencode(
        {
            "started_at": started_at,
            "ended_at": ended_at,
            "max_records": max_records,
        }
    )
    url = f"{hub_url.rstrip('/')}/api/v1/devices/{quote(device_id, safe='')}/field-export?{query}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with request.urlopen(request.Request(url, headers=headers), timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        raise LocationD2D5PipelineError(
            f"Message Hub field export failed with HTTP {exc.code} for device {device_id}"
        ) from exc
    except (urlerror.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise LocationD2D5PipelineError(
            f"Message Hub field export failed for device {device_id}: {type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise LocationD2D5PipelineError("Message Hub field export must be a JSON object")
    window = as_dict(payload.get("window"))
    if window.get("complete") is not True or any(as_dict(window.get("truncated")).values()):
        raise LocationD2D5PipelineError(
            "Message Hub field export was truncated; narrow the manifest time window before analysis"
        )
    return payload


def write_export(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def read_manifest_window(manifest_path: Path, *, device_id: str) -> tuple[str, str]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocationD2D5PipelineError(f"cannot read FIELD-003 manifest: {type(exc).__name__}") from exc
    if not isinstance(manifest, dict):
        raise LocationD2D5PipelineError("FIELD-003 manifest must be a JSON object")
    manifest_device_id = str(manifest.get("device_id") or "").strip()
    if manifest_device_id and manifest_device_id != device_id:
        raise LocationD2D5PipelineError(
            f"manifest device_id {manifest_device_id} does not match --device-id {device_id}"
        )
    started_at = str(manifest.get("started_at") or "").strip()
    ended_at = str(manifest.get("ended_at") or "").strip()
    if not started_at or not ended_at or started_at.startswith("<") or ended_at.startswith("<"):
        raise LocationD2D5PipelineError(
            "manifest started_at and ended_at must be completed before a device-window export"
        )
    return started_at, ended_at


def resolve_input_path(args: argparse.Namespace, *, run_id: str) -> Path:
    if args.input_path:
        if args.hub or args.test_run_id or args.device_id:
            raise LocationD2D5PipelineError(
                "--input cannot be combined with --hub, --test-run-id, or --device-id"
            )
        return args.input_path
    if not args.hub:
        raise LocationD2D5PipelineError(
            "provide --input, --hub with --device-id, or --hub with legacy --test-run-id"
        )
    if bool(args.test_run_id) == bool(args.device_id):
        raise LocationD2D5PipelineError("choose exactly one of --device-id or --test-run-id with --hub")
    token = read_token(args.token_file)
    if args.device_id:
        started_at, ended_at = read_manifest_window(args.manifest, device_id=args.device_id)
        export = fetch_device_window_export(
            hub_url=args.hub,
            device_id=args.device_id,
            started_at=started_at,
            ended_at=ended_at,
            max_records=args.max_records,
            token=token,
            timeout_sec=args.request_timeout_sec,
        )
    else:
        export = fetch_message_hub_export(
            hub_url=args.hub,
            test_run_id=args.test_run_id,
            token=token,
            timeout_sec=args.request_timeout_sec,
        )
    return write_export(args.gnss_output_root / run_id / "test_run_export.json", export)


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
            "No hardware command, model training, model evaluation, model artifact, or on-device deployment is performed.",
            "Remote input mode performs only an authenticated read-only Message Hub export.",
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
    parser.add_argument("--input", "--export", dest="input_path", type=Path)
    parser.add_argument("--hub", help="Message Hub base URL for a read-only evidence export.")
    parser.add_argument("--device-id", help="Device to export over the manifest's started_at/ended_at window.")
    parser.add_argument("--test-run-id", help="Legacy Message Hub test_run_id to export.")
    parser.add_argument("--max-records", type=int, default=5000, help="Maximum rows per exported collection.")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--request-timeout-sec", type=float, default=120.0)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--selection", type=Path, help="Optional D5 explicit selection file.")
    parser.add_argument("--run-id", help="Stable run directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--location-output-root", type=Path, default=baseline.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--flywheel-output-root", type=Path, default=flywheel.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pipeline-output-root", type=Path, default=DEFAULT_PIPELINE_OUTPUT_ROOT)
    parser.add_argument("--gnss-output-root", type=Path, default=DEFAULT_GNSS_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true", help="Print the pipeline summary JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated)
    try:
        input_path = resolve_input_path(args, run_id=run_id)
        d2_report = baseline.analyze_location_accuracy_baseline(
            input_path=input_path,
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
            input_path=input_path,
            manifest_path=args.manifest,
            d2_report=d2_report,
            d5_written=d5_written,
        )
        written = write_summary(summary, args.pipeline_output_root / run_id)
    except (
        LocationD2D5PipelineError,
        baseline.LocationAccuracyBaselineError,
        flywheel.LocationDataFlywheelError,
    ) as exc:
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
