"""Evaluate an offline LTE reliability gate from a Message Hub test-run export.

The LTE-005 gate is evidence-first and non-hardware: it reads an existing
``test_run_export.json`` and checks whether command state, duplicate handling,
LTE transport, raw-frame retention, stale/pending commands, and reconnect/cache
observability are visible enough before a long field run is attempted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_fw001_hw_loop import compact_utc_now, parse_timestamp, utc_now, write_json  # noqa: E402


DEFAULT_OUTPUT_ROOT = Path("reports") / "lte_reliability"
DEFAULT_STALE_COMMAND_SEC = 300.0
GATE_VERSION = "LTE-005.offline.v1"


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def first_present(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def nested_value(payload: object, path: str) -> object | None:
    value = payload
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def walk_json(value: object, prefix: str = "") -> Iterable[tuple[str, object]]:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, item
            yield from walk_json(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            yield path, item
            yield from walk_json(item, path)


def load_export(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("test-run export must be a JSON object")
    return payload


def runtime_records(export: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    for message in as_list(export.get("messages")):
        if isinstance(message, dict):
            records.append(("message", message))
    for command in as_list(export.get("commands")):
        if not isinstance(command, dict):
            continue
        records.append(("command", command))
        ack = as_dict(command.get("ack"))
        if ack:
            records.append(("command_ack", ack))
    for raw_frame in as_list(export.get("raw_frames")):
        if not isinstance(raw_frame, dict):
            continue
        records.append(("raw_frame", raw_frame))
        derived = as_dict(as_dict(raw_frame.get("parse_result")).get("derived_message"))
        if derived:
            records.append(("raw_frame_derived", derived))
    summary = as_dict(export.get("observability_summary"))
    if summary:
        records.append(("observability_summary", summary))
        latest = as_dict(summary.get("latest_observability"))
        if latest:
            records.append(("latest_observability", latest))
    run_context = as_dict(export.get("run_context"))
    if run_context:
        records.append(("run_context", run_context))
    return records


def collect_timestamps(export: dict[str, Any]) -> list[datetime]:
    timestamps: list[datetime] = []
    for _, record in runtime_records(export):
        for key in ("server_received_at", "updated_at", "created_at", "started_at", "completed_at", "ts"):
            parsed = parse_timestamp(record.get(key))
            if parsed is not None:
                timestamps.append(parsed)
    for key in ("created_at", "started_at", "completed_at"):
        parsed = parse_timestamp(as_dict(export.get("test_run")).get(key))
        if parsed is not None:
            timestamps.append(parsed)
    return timestamps


def latest_export_time(export: dict[str, Any]) -> datetime:
    timestamps = collect_timestamps(export)
    return max(timestamps) if timestamps else datetime.now(timezone.utc)


def command_ack(command: dict[str, Any]) -> dict[str, Any]:
    return as_dict(command.get("ack"))


def command_status_gate(export: dict[str, Any]) -> dict[str, Any]:
    commands = [item for item in as_list(export.get("commands")) if isinstance(item, dict)]
    if not commands:
        return gate("G1_COMMAND_STATE_VISIBLE", "WARN", "No command rows are present in this export.")

    errors: list[str] = []
    warnings: list[str] = []
    visible: list[dict[str, Any]] = []
    for command in commands:
        cmd_id = command.get("cmd_id")
        status = command.get("status")
        ack = command_ack(command)
        visible.append(
            {
                "cmd_id": cmd_id,
                "cmd": command.get("cmd"),
                "status": status,
                "ack_status": ack.get("status") if ack else None,
                "created_at": command.get("created_at"),
                "updated_at": command.get("updated_at"),
            }
        )
        if not cmd_id:
            errors.append("command row missing cmd_id")
        if not status:
            errors.append(f"command {cmd_id or '<unknown>'} missing status")
        if status == "ok" and not ack:
            errors.append(f"command {cmd_id} is ok but has no ACK payload")
        if status == "ok" and ack and ack.get("status") != "ok":
            warnings.append(f"command {cmd_id} status is ok but ack.status={ack.get('status')}")
        if status == "pending" and not first_present(command.get("created_at"), command.get("updated_at")):
            warnings.append(f"pending command {cmd_id} has no timestamp")
    if errors:
        return gate("G1_COMMAND_STATE_VISIBLE", "FAIL", "Command lifecycle state is not fully visible.", errors=errors, evidence={"commands": visible})
    status = "WARN" if warnings else "PASS"
    summary = "Command rows expose cmd_id, status, timestamps, and ACK state." if status == "PASS" else "Command state is visible with warnings."
    return gate("G1_COMMAND_STATE_VISIBLE", status, summary, warnings=warnings, evidence={"commands": visible})


def failure_reason_texts(export: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    interesting_suffixes = (
        "failure_summary.reason",
        "failure_reason",
        "reason",
        "reason_code",
        "reason_codes",
        "error_code",
        "gnss_state",
        "parse_status",
    )
    for path, value in walk_json(export):
        if not any(path.endswith(suffix) for suffix in interesting_suffixes):
            continue
        if isinstance(value, list):
            texts.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            texts.append(str(value))
    return unique_text(texts)


def stale_command_gate(export: dict[str, Any], *, stale_command_sec: float) -> dict[str, Any]:
    commands = [item for item in as_list(export.get("commands")) if isinstance(item, dict)]
    pending = [command for command in commands if command.get("status") == "pending"]
    if not pending:
        return gate(
            "G2_STALE_PENDING_VISIBLE",
            "NOT_OBSERVED",
            "No pending or stale command is present in this export.",
        )

    latest = latest_export_time(export)
    reasons = failure_reason_texts(export)
    stale: list[dict[str, Any]] = []
    fresh_pending: list[dict[str, Any]] = []
    for command in pending:
        created_at = parse_timestamp(command.get("created_at")) or parse_timestamp(command.get("updated_at"))
        age_sec = (latest - created_at).total_seconds() if created_at else None
        item = {
            "cmd_id": command.get("cmd_id"),
            "cmd": command.get("cmd"),
            "created_at": command.get("created_at"),
            "updated_at": command.get("updated_at"),
            "age_sec": age_sec,
        }
        if age_sec is None or age_sec >= stale_command_sec:
            stale.append(item)
        else:
            fresh_pending.append(item)

    has_pending_reason = any("pending" in reason.lower() or "ack_missing" in reason.lower() for reason in reasons)
    if stale and not has_pending_reason:
        return gate(
            "G2_STALE_PENDING_VISIBLE",
            "FAIL",
            "A stale pending command is present without an explicit pending/ACK-missing reason.",
            errors=["stale_pending_command_without_failure_reason"],
            evidence={"stale": stale, "failure_reason_texts": reasons},
        )
    if stale:
        return gate(
            "G2_STALE_PENDING_VISIBLE",
            "PASS",
            "Stale pending command state is visible and explained.",
            evidence={"stale": stale, "failure_reason_texts": reasons},
        )
    return gate(
        "G2_STALE_PENDING_VISIBLE",
        "WARN",
        "Pending command state is visible but has not crossed the stale threshold.",
        warnings=["pending_command_not_stale"],
        evidence={"pending": fresh_pending, "failure_reason_texts": reasons},
    )


def duplicate_gate(export: dict[str, Any]) -> dict[str, Any]:
    markers: list[dict[str, Any]] = []
    for source, record in runtime_records(export):
        command_obj = as_dict(record.get("command"))
        command_count = first_present(command_obj.get("command_count"), record.get("command_count"))
        duplicate = first_present(
            command_obj.get("duplicate_local_execution_prevented"),
            record.get("duplicate_local_execution_prevented"),
        )
        parsed_count = int_or_none(command_count)
        if parsed_count is None and duplicate is None:
            continue
        markers.append(
            {
                "source": source,
                "cmd_id": first_present(record.get("cmd_id"), command_obj.get("last_cmd_id")),
                "command_count": parsed_count,
                "duplicate_local_execution_prevented": duplicate,
                "parse_status": first_present(command_obj.get("parse_status"), record.get("parse_status")),
            }
        )

    if not markers:
        return gate(
            "G3_DUPLICATE_EXECUTION_GUARD",
            "WARN",
            "No command_count or duplicate_local_execution_prevented marker is visible.",
            warnings=["duplicate_guard_marker_missing"],
        )

    risky = [
        marker
        for marker in markers
        if (marker.get("command_count") or 0) > 1 and marker.get("duplicate_local_execution_prevented") is not True
    ]
    if risky:
        return gate(
            "G3_DUPLICATE_EXECUTION_GUARD",
            "FAIL",
            "A repeated command selection did not show local duplicate-execution prevention.",
            errors=["duplicate_command_execution_risk"],
            evidence={"marker_count": len(markers), "sample_markers": markers[:10], "risky_markers": risky},
        )

    exercised = any((marker.get("command_count") or 0) > 1 for marker in markers)
    summary = (
        "Duplicate command execution was exercised and prevented."
        if exercised
        else "Duplicate guard fields are visible; no repeated command execution was observed."
    )
    return gate(
        "G3_DUPLICATE_EXECUTION_GUARD",
        "PASS",
        summary,
        evidence={"marker_count": len(markers), "sample_markers": markers[:10]},
    )


def lte_transport_gate(export: dict[str, Any]) -> dict[str, Any]:
    lte_records: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    for source, record in runtime_records(export):
        if nested_value(record, "transport.type") == "lte":
            lte_records.append(
                {
                    "source": source,
                    "message_type": record.get("message_type"),
                    "event_type": record.get("event_type"),
                    "cmd_id": record.get("cmd_id"),
                    "seq": record.get("seq"),
                    "server_received_at": record.get("server_received_at"),
                    "phase": nested_value(record, "lte_http.phase"),
                }
            )
        for path in ("lte_http.poll_reason_code", "lte.reason_code", "cell.reason_code", "transport.last_error"):
            value = nested_value(record, path)
            if value not in (None, ""):
                reason_codes.append(str(value))

    if not lte_records:
        return gate(
            "G4_LTE_TRANSPORT_EVIDENCE",
            "FAIL",
            "No runtime record carries transport.type=lte.",
            errors=["lte_transport_evidence_missing"],
        )
    if not reason_codes:
        return gate(
            "G4_LTE_TRANSPORT_EVIDENCE",
            "WARN",
            "LTE transport is visible, but LTE/HTTP reason codes are absent.",
            warnings=["lte_reason_code_missing"],
            evidence={"lte_record_count": len(lte_records), "sample_records": lte_records[:5]},
        )
    return gate(
        "G4_LTE_TRANSPORT_EVIDENCE",
        "PASS",
        "LTE transport and LTE/HTTP reason-code evidence are visible.",
        evidence={
            "lte_record_count": len(lte_records),
            "reason_codes": unique_text(reason_codes),
            "sample_records": lte_records[:5],
        },
    )


def failure_visibility_gate(export: dict[str, Any]) -> dict[str, Any]:
    commands = [item for item in as_list(export.get("commands")) if isinstance(item, dict)]
    pending = [command for command in commands if command.get("status") == "pending"]
    reasons = failure_reason_texts(export)
    raw_parse_failures = []
    for raw_frame in as_list(export.get("raw_frames")):
        if not isinstance(raw_frame, dict):
            continue
        parse = as_dict(raw_frame.get("parse_result"))
        status = str(parse.get("status") or "")
        if status and status != "ok":
            raw_parse_failures.append(
                {
                    "frame_id": raw_frame.get("frame_id"),
                    "parse_status": status,
                    "error_code": parse.get("error_code"),
                    "reason": parse.get("reason"),
                }
            )

    has_location_failure = False
    location_explanations: list[str] = []
    for _, record in runtime_records(export):
        if record.get("event_type") != "location_report":
            continue
        fix = record.get("fix")
        gnss_state = record.get("gnss_state")
        if fix is False or str(gnss_state or "").lower() in {"no_fix", "unknown", "at_unreachable"}:
            has_location_failure = True
            for field in ("gnss_state", "source_status"):
                value = record.get(field)
                if value not in (None, ""):
                    location_explanations.append(str(value))

    errors: list[str] = []
    warnings: list[str] = []
    if pending and not any("pending" in reason.lower() or "ack_missing" in reason.lower() for reason in reasons):
        errors.append("pending_command_without_failure_reason")
    for failure in raw_parse_failures:
        if not first_present(failure.get("error_code"), failure.get("reason"), failure.get("parse_status")):
            errors.append(f"raw_frame_parse_failure_without_reason:{failure.get('frame_id')}")
    if has_location_failure and not location_explanations and not reasons:
        errors.append("location_failure_without_reason")
    if not commands and not as_list(export.get("messages")) and not as_list(export.get("raw_frames")):
        warnings.append("no_runtime_evidence")

    if errors:
        return gate(
            "G5_FAILURE_REASON_VISIBLE",
            "FAIL",
            "One or more failure states lack explicit reason evidence.",
            errors=errors,
            evidence={"failure_reason_texts": reasons, "raw_parse_failures": raw_parse_failures},
        )
    status = "WARN" if warnings else "PASS"
    summary = "Failure/no-fix states are either absent or explicitly explained." if status == "PASS" else "Failure visibility is partial."
    return gate(
        "G5_FAILURE_REASON_VISIBLE",
        status,
        summary,
        warnings=warnings,
        evidence={
            "failure_reason_texts": reasons[:20],
            "raw_parse_failures": raw_parse_failures,
            "location_explanations": unique_text(location_explanations),
        },
    )


def reconnect_cache_gate(export: dict[str, Any]) -> dict[str, Any]:
    reconnect_hits: list[dict[str, Any]] = []
    cache_hits: list[dict[str, Any]] = []
    for source, record in runtime_records(export):
        for path, value in walk_json(record):
            normalized = path.lower()
            if value in (None, ""):
                continue
            if (
                "reconnect" in normalized
                or normalized.endswith("last_network_error")
                or normalized.endswith("network.last_error")
                or normalized.endswith("runtime.last_reset_reason")
                or normalized.endswith("reset_reason")
                or normalized.endswith("boot_count")
                or normalized.endswith("boot_id")
            ):
                reconnect_hits.append({"source": source, "path": path, "value": value})
            if (
                "cache" in normalized
                or "queued_message" in normalized
                or "dropped_message" in normalized
                or "offline_queue" in normalized
                or "store_forward" in normalized
            ):
                cache_hits.append({"source": source, "path": path, "value": value})

    warnings: list[str] = []
    if not reconnect_hits:
        warnings.append("reconnect_or_reset_observability_not_observed")
    if not cache_hits:
        warnings.append("cache_or_dropped_message_observability_not_observed")
    if warnings:
        return gate(
            "G6_RECONNECT_CACHE_OBSERVABILITY",
            "WARN",
            "Reconnect/cache observability is incomplete in this export.",
            warnings=warnings,
            evidence={"reconnect_hits": reconnect_hits[:10], "cache_hits": cache_hits[:10]},
        )
    return gate(
        "G6_RECONNECT_CACHE_OBSERVABILITY",
        "PASS",
        "Reconnect/reset and cache/drop observability fields are visible.",
        evidence={"reconnect_hits": reconnect_hits[:10], "cache_hits": cache_hits[:10]},
    )


def raw_retention_gate(export: dict[str, Any]) -> dict[str, Any]:
    raw_frames = [item for item in as_list(export.get("raw_frames")) if isinstance(item, dict)]
    if not raw_frames:
        return gate(
            "G7_RAW_FRAME_RETENTION",
            "FAIL",
            "No raw-frame records are present; raw transport evidence is not retained.",
            errors=["raw_frame_retention_missing"],
        )
    missing: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for raw_frame in raw_frames:
        raw_payload = as_dict(raw_frame.get("raw_payload"))
        framing = as_dict(raw_frame.get("framing"))
        item = {
            "frame_id": raw_frame.get("frame_id"),
            "direction": raw_frame.get("direction"),
            "parse_status": as_dict(raw_frame.get("parse_result")).get("status"),
            "sha256": raw_payload.get("sha256"),
            "byte_len": raw_payload.get("byte_len"),
            "payload_crc32": first_present(framing.get("payload_crc32"), raw_payload.get("crc32")),
            "data_redacted": raw_payload.get("data_redacted"),
        }
        samples.append(item)
        if not item["sha256"] or item["byte_len"] is None or not item["payload_crc32"]:
            missing.append(item)
    if missing:
        return gate(
            "G7_RAW_FRAME_RETENTION",
            "FAIL",
            "Some raw-frame records lack raw payload hash/length/CRC evidence.",
            errors=["raw_frame_integrity_metadata_missing"],
            evidence={"missing": missing, "sample_frames": samples[:5]},
        )
    return gate(
        "G7_RAW_FRAME_RETENTION",
        "PASS",
        "Raw frames retain hash, length, CRC, parse status, and redaction metadata.",
        evidence={"raw_frame_count": len(raw_frames), "sample_frames": samples[:5]},
    )


def sequence_visibility(export: dict[str, Any]) -> dict[str, Any]:
    seq_rows: list[dict[str, Any]] = []
    previous: int | None = None
    regressions = 0
    duplicate_count = 0
    seen: set[int] = set()
    for message in as_list(export.get("messages")):
        if not isinstance(message, dict):
            continue
        seq = int_or_none(message.get("seq"))
        if seq is None:
            continue
        if previous is not None and seq < previous:
            regressions += 1
        if seq in seen:
            duplicate_count += 1
        seen.add(seq)
        previous = seq
        seq_rows.append(
            {
                "seq": seq,
                "message_type": message.get("message_type"),
                "event_type": message.get("event_type"),
                "server_received_at": message.get("server_received_at"),
            }
        )
    status = "PASS"
    warnings: list[str] = []
    if not seq_rows:
        status = "WARN"
        warnings.append("no_message_seq_observed")
    elif regressions or duplicate_count:
        status = "WARN"
        warnings.append("message_sequence_reset_or_duplicate_visible")
    return gate(
        "G8_SEQUENCE_VISIBILITY",
        status,
        "Message sequence behavior is visible.",
        warnings=warnings,
        evidence={
            "sequence_count": len(seq_rows),
            "regressions": regressions,
            "duplicates": duplicate_count,
            "sample": seq_rows[:5],
        },
    )


def gate(
    gate_id: str,
    status: str,
    summary: str,
    *,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": status,
        "summary": summary,
        "errors": errors or [],
        "warnings": warnings or [],
        "evidence": evidence or {},
    }


def unique_text(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def result_from_gates(gates: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in gates}
    if "FAIL" in statuses:
        return "FAIL"
    if statuses.intersection({"WARN", "NOT_OBSERVED"}):
        return "WARN"
    return "PASS"


def collect_gate_messages(gates: list[dict[str, Any]], key: str) -> list[str]:
    messages: list[str] = []
    for item in gates:
        messages.extend(str(value) for value in as_list(item.get(key)))
    return unique_text(messages)


def evaluate_lte_reliability_export(
    export: dict[str, Any],
    *,
    input_path: Path | None = None,
    stale_command_sec: float = DEFAULT_STALE_COMMAND_SEC,
) -> dict[str, Any]:
    test_run = as_dict(export.get("test_run"))
    gates = [
        command_status_gate(export),
        stale_command_gate(export, stale_command_sec=stale_command_sec),
        duplicate_gate(export),
        lte_transport_gate(export),
        failure_visibility_gate(export),
        reconnect_cache_gate(export),
        raw_retention_gate(export),
        sequence_visibility(export),
    ]
    result = result_from_gates(gates)
    messages = as_list(export.get("messages"))
    commands = as_list(export.get("commands"))
    raw_frames = as_list(export.get("raw_frames"))
    firmware_versions = unique_text(
        first_present(record.get("fw_version"), nested_value(record, "ack.fw_version"))
        for _, record in runtime_records(export)
        if first_present(record.get("fw_version"), nested_value(record, "ack.fw_version")) not in (None, "")
    )
    return {
        "tool": "validate_lte_reliability_gate",
        "gate_version": GATE_VERSION,
        "result": result,
        "created_at": utc_now(),
        "input_path": str(input_path) if input_path else None,
        "test_run_id": test_run.get("test_run_id"),
        "task_id": test_run.get("task_id"),
        "device_id": test_run.get("device_id"),
        "board_id": test_run.get("board_id"),
        "connection_path": test_run.get("connection_path"),
        "firmware_versions": firmware_versions,
        "counts": {
            "messages": len(messages),
            "commands": len(commands),
            "raw_frames": len(raw_frames),
        },
        "stale_command_sec": stale_command_sec,
        "gates": gates,
        "errors": collect_gate_messages(gates, "errors"),
        "warnings": collect_gate_messages(gates, "warnings"),
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# LTE-005 Reliability Gate Report",
        "",
        f"- Result: {report.get('result')}",
        f"- Gate version: {report.get('gate_version')}",
        f"- Test run: {report.get('test_run_id')}",
        f"- Device: {report.get('device_id')}",
        f"- Board: {report.get('board_id')}",
        f"- Connection path: {report.get('connection_path')}",
        f"- Firmware versions: {', '.join(as_list(report.get('firmware_versions'))) or 'unknown'}",
        f"- Input: {report.get('input_path')}",
        "",
        "## Counts",
        "",
    ]
    counts = as_dict(report.get("counts"))
    for key in ("messages", "commands", "raw_frames"):
        lines.append(f"- {key}: {counts.get(key, 0)}")

    lines.extend(["", "## Gates", ""])
    for item in as_list(report.get("gates")):
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('id')}: {item.get('status')} - {item.get('summary')}")
        for warning in as_list(item.get("warnings")):
            lines.append(f"  - warning: {warning}")
        for error in as_list(item.get("errors")):
            lines.append(f"  - error: {error}")

    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This report is an offline evidence gate over an existing Message Hub export.",
            "- It does not flash firmware, contact hardware, send commands, or prove long LTE stability.",
            "- WARN or NOT_OBSERVED means the next field test should explicitly exercise that behavior.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_dir(report: dict[str, Any]) -> Path:
    test_run_id = str(report.get("test_run_id") or f"lte005-{compact_utc_now()}")
    return DEFAULT_OUTPUT_ROOT / test_run_id


def validate_lte_reliability_gate(
    *,
    input_path: Path,
    output_dir: Path | None = None,
    stale_command_sec: float = DEFAULT_STALE_COMMAND_SEC,
) -> dict[str, Any]:
    export = load_export(input_path)
    report = evaluate_lte_reliability_export(export, input_path=input_path, stale_command_sec=stale_command_sec)
    target_dir = output_dir or default_output_dir(report)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / "lte_reliability_gate_report.json"
    markdown_path = target_dir / "lte_reliability_gate_report.md"
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to a Message Hub test_run_export.json file.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stale-command-sec", type=float, default=DEFAULT_STALE_COMMAND_SEC)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate_lte_reliability_gate(
            input_path=args.input,
            output_dir=args.output_dir,
            stale_command_sec=args.stale_command_sec,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL LTE-005 reliability gate: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"{report['result']} LTE-005 reliability gate "
            f"test_run={report.get('test_run_id')} report={report['markdown_report_path']}"
        )
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
