"""Build a bounded index of D1 labeling/privacy intake reports.

This command scans local D1 labeling-intake summaries and writes one compact
queue index for the DATA/D5 flywheel. It does not read sample JSONL contents,
write the candidate SQLite store, contact hardware, train/evaluate a model, or
expose exact coordinates.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTAKE_ROOT = REPO_ROOT / "reports" / "d1_labeling_intake"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_labeling_queue"
SCHEMA_VERSION = "egolink.d1_labeling_queue.v0.1"
BUILDER_VERSION = "data-026.0"
SUMMARY_JSON = "d1_labeling_queue.json"
SUMMARY_MARKDOWN = "d1_labeling_queue.md"


class D1LabelingQueueError(RuntimeError):
    """Raised when a D1 labeling queue cannot be built safely."""


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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def bool_value(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise D1LabelingQueueError(f"intake report not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise D1LabelingQueueError(f"intake report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise D1LabelingQueueError(f"intake report must be a JSON object: {path}")
    return payload


def relative_path(path: Path | None, *, root: Path | None = None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    for base in (REPO_ROOT.resolve(), root.resolve() if root else None):
        if base is None:
            continue
        try:
            return resolved.relative_to(base).as_posix()
        except (OSError, ValueError):
            continue
    return path.name


def mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def default_run_id(generated_at: str) -> str:
    return f"d1-labeling-queue-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def find_intake_reports(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    reports = [path for path in root.glob("**/d1_labeling_intake.json") if path.is_file()]
    return sorted(reports, key=lambda path: path.stat().st_mtime, reverse=True)


def summarize_review_item(
    item: Mapping[str, Any],
    *,
    intake: Mapping[str, Any],
    intake_path: Path,
    intake_root: Path,
    blockers: list[str],
) -> dict[str, Any]:
    review_state = as_dict(item.get("review_state"))
    evidence = as_dict(item.get("evidence_summary"))
    return {
        "intake_id": item.get("intake_id"),
        "intake_run_id": intake.get("run_id"),
        "source_run_id": item.get("source_run_id") or as_dict(intake.get("source_observation")).get("run_id"),
        "readiness_run_id": item.get("readiness_run_id") or as_dict(intake.get("source_readiness")).get("run_id"),
        "device_id": item.get("device_id") or as_dict(intake.get("source_observation")).get("device_id"),
        "status": item.get("status") or "unknown",
        "review_state": {
            "operator_label": review_state.get("operator_label") or "missing",
            "privacy_review": review_state.get("privacy_review") or "required",
            "training_consent": review_state.get("training_consent") or "not_reviewed",
            "split_plan": review_state.get("split_plan") or "missing",
            "quality_gaps": unique_text(as_list(review_state.get("quality_gaps"))),
        },
        "evidence_summary": {
            "samples": int_or_zero(evidence.get("samples")),
            "latest_seq": evidence.get("latest_seq"),
            "raw_post_success_delta": int_or_zero(evidence.get("raw_post_success_delta")),
            "raw_post_failure_delta": int_or_zero(evidence.get("raw_post_failure_delta")),
            "coordinate_sample_count": int_or_zero(evidence.get("coordinate_sample_count")),
            "gnss_fix_seen": bool_value(evidence.get("gnss_fix_seen")),
            "imu_evidence_statuses": unique_text(as_list(evidence.get("imu_evidence_statuses"))),
            "power_evidence_statuses": unique_text(as_list(evidence.get("power_evidence_statuses"))),
            "coordinate_values_copied": False,
        },
        "requested_actions": unique_text(as_list(item.get("requested_actions"))),
        "available_decisions": unique_text(as_list(item.get("available_decisions"))),
        "blockers": blockers,
        "training_allowed": False,
        "candidate_record_written": False,
        "intake_report_path": relative_path(intake_path, root=intake_root),
    }


def summarize_intake_report(path: Path, *, intake_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_json(path)
    queue = as_dict(payload.get("intake_queue"))
    source_readiness = as_dict(payload.get("source_readiness"))
    source_observation = as_dict(payload.get("source_observation"))
    blockers = unique_text(as_list(payload.get("blockers")))
    item_payloads = [as_dict(item) for item in as_list(queue.get("items"))]
    items = [
        summarize_review_item(
            item,
            intake=payload,
            intake_path=path,
            intake_root=intake_root,
            blockers=blockers,
        )
        for item in item_payloads
        if item
    ]
    report_summary = {
        "run_id": payload.get("run_id") or path.parent.name,
        "status": payload.get("status") or "unknown",
        "reason": payload.get("reason"),
        "generated_at": payload.get("generated_at"),
        "updated_at": mtime_iso(path),
        "source_run_id": source_observation.get("run_id"),
        "source_readiness_run_id": source_readiness.get("run_id"),
        "pending_items": int_or_zero(queue.get("pending_items") if queue else len(items)),
        "items_indexed": len(items),
        "candidate_store_gate": as_dict(payload.get("review_gates")).get("candidate_store"),
        "model_training_gate": as_dict(payload.get("review_gates")).get("model_training"),
        "training_allowed": False,
        "candidate_record_written": False,
        "report_path": relative_path(path, root=intake_root),
        "markdown_report_path": relative_path(path.with_suffix(".md"), root=intake_root)
        if path.with_suffix(".md").exists()
        else None,
        "blockers": blockers,
    }
    return report_summary, items


def queue_status(*, pending_items: int, report_count: int) -> str:
    if pending_items > 0:
        return "pending_human_review"
    if report_count > 0:
        return "empty_or_not_ready"
    return "no_intake_reports"


def next_step(status: str) -> str:
    if status == "pending_human_review":
        return "Review the pending D1 items, attach labels/privacy/consent/split decisions, then write reviewed candidates through the candidate-store path."
    if status == "empty_or_not_ready":
        return "Run or rerun D1 training-readiness and labeling-intake after a completed field observation."
    return "Generate D1 labeling-intake reports from post-run collection before opening the queue."


def build_queue_index(
    *,
    intake_root: Path,
    generated_at: str,
    run_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise D1LabelingQueueError("--limit must be positive")
    intake_reports: list[dict[str, Any]] = []
    queue_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    paths = find_intake_reports(intake_root)
    if limit is not None:
        paths = paths[:limit]
    for path in paths:
        try:
            report, items = summarize_intake_report(path, intake_root=intake_root)
            intake_reports.append(report)
            queue_items.extend(items)
        except Exception as exc:  # noqa: BLE001 - keep the index writeable.
            errors.append(
                {
                    "status": "error",
                    "reason": "d1_labeling_intake_read_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "path": relative_path(path, root=intake_root),
                }
            )

    pending_items = len([item for item in queue_items if item.get("status") == "pending_label_privacy_split"])
    not_ready_reports = len([report for report in intake_reports if report.get("status") == "not_ready_for_labeling_intake"])
    status = queue_status(pending_items=pending_items, report_count=len(intake_reports))
    return {
        "tool": "summarize_d1_labeling_queue",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": status,
        "summary": {
            "intake_report_count": len(intake_reports),
            "pending_item_count": pending_items,
            "not_ready_report_count": not_ready_reports,
            "error_count": len(errors),
            "training_allowed_count": 0,
            "candidate_record_written_count": 0,
        },
        "queue": {
            "items": queue_items,
            "next_queue": "training_candidate_store_after_review",
        },
        "intake_reports": intake_reports,
        "errors": errors,
        "scope": {
            "intake_summaries_read": True,
            "sample_jsonl_read": False,
            "message_hub_contacted": False,
            "hardware_contacted": False,
            "commands_sent": False,
            "firmware_changed": False,
            "candidate_db_written": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "exact_coordinates_copied": False,
            "raw_sensor_payload_copied": False,
            "release_claim_allowed": False,
        },
        "next_step": next_step(status),
        "non_claims": [
            "This queue index reads D1 labeling-intake summaries only.",
            "It does not contain raw sample JSONL, raw payload bytes, exact coordinates, candidate DBs, feature rows, targets, or model artifacts.",
            "It does not write candidate records, train/evaluate a model, deploy on-device inference, measure model footprint or power, or permit release claims.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    items = [as_dict(item) for item in as_list(as_dict(payload.get("queue")).get("items"))]
    reports = [as_dict(report) for report in as_list(payload.get("intake_reports"))]
    lines = [
        "# D1 Labeling Queue",
        "",
        f"- Status: {payload.get('status')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Generated: {payload.get('generated_at')}",
        f"- Intake reports: {summary.get('intake_report_count', 0)}",
        f"- Pending items: {summary.get('pending_item_count', 0)}",
        f"- Not ready reports: {summary.get('not_ready_report_count', 0)}",
        "",
        "## Pending Items",
        "",
        "| Source Run | Intake ID | Label | Privacy | Consent | Split | Samples | GNSS Fix |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    if items:
        for item in items:
            review = as_dict(item.get("review_state"))
            evidence = as_dict(item.get("evidence_summary"))
            lines.append(
                "| {source} | {intake} | {label} | {privacy} | {consent} | {split} | {samples} | {gnss} |".format(
                    source=item.get("source_run_id") or "",
                    intake=item.get("intake_id") or "",
                    label=review.get("operator_label") or "",
                    privacy=review.get("privacy_review") or "",
                    consent=review.get("training_consent") or "",
                    split=review.get("split_plan") or "",
                    samples=evidence.get("samples", 0),
                    gnss=evidence.get("gnss_fix_seen", False),
                )
            )
    else:
        lines.append("| none |  |  |  |  |  |  |  |")

    lines += [
        "",
        "## Intake Reports",
        "",
        "| Run | Status | Pending | Source Run | Report |",
        "|---|---|---:|---|---|",
    ]
    if reports:
        for report in reports:
            lines.append(
                "| {run} | {status} | {pending} | {source} | {path} |".format(
                    run=report.get("run_id") or "",
                    status=report.get("status") or "",
                    pending=report.get("pending_items", 0),
                    source=report.get("source_run_id") or "",
                    path=report.get("report_path") or "",
                )
            )
    else:
        lines.append("| none |  |  |  |  |")

    lines += [
        "",
        "## Next Step",
        "",
        f"- {payload.get('next_step')}",
        "",
        "## Boundaries",
        "",
        "- This queue index reads local D1 labeling-intake summaries only.",
        "- It does not read sample JSONL contents, exact coordinates, raw payloads, feature rows, targets, candidate DBs, or model artifacts.",
        "- It does not contact hardware, call the Message Hub, send commands, change firmware, train/evaluate a model, deploy inference, or make release claims.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / SUMMARY_JSON
    markdown_path = output_dir / SUMMARY_MARKDOWN
    payload["paths"] = {
        "d1_labeling_queue_json": relative_path(json_path),
        "d1_labeling_queue_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_queue_index(
        intake_root=args.intake_root,
        generated_at=generated_at,
        run_id=run_id,
        limit=args.limit,
    )
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded D1 labeling queue index.")
    parser.add_argument("--intake-root", type=Path, default=DEFAULT_INTAKE_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_from_args(args)
    except D1LabelingQueueError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['status']} D1 labeling queue: {as_dict(payload.get('paths')).get('d1_labeling_queue_markdown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
