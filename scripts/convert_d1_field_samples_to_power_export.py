"""Convert D1 field-observer samples into a PWR-001 power export.

The D1 field observer stores read-only dashboard snapshots as JSONL. This
adapter turns those snapshots into the existing Message Hub export shape so
`scripts/analyze_power_curve.py` can build the normal PWR-001 report. It does
not contact hardware, send commands, or upgrade mock/unknown power evidence to
measured.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_power_curve  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORT_JSON = "field_observer_power_export.json"
TOOL_NAME = "convert_d1_field_samples_to_power_export"
TOOL_VERSION = "D1.field_power_export.v1"


class FieldPowerExportError(RuntimeError):
    """Raised when field-observer samples cannot be converted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_known(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise FieldPowerExportError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FieldPowerExportError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FieldPowerExportError(f"JSON document must be an object: {path}")
    return payload


def load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise FieldPowerExportError(f"failed to read JSONL: {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FieldPowerExportError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise FieldPowerExportError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(payload)
    return rows


def infer_run_id(samples_path: Path, field_report: dict[str, Any] | None, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    if field_report:
        report_run_id = field_report.get("run_id")
        if isinstance(report_run_id, str) and report_run_id.strip():
            return report_run_id.strip()
    parent = samples_path.parent.name
    return parent if parent else f"D1-field-power-{datetime.now(timezone.utc):%Y%m%d}"


def timestamp_for_sample(sample: dict[str, Any]) -> str | None:
    timestamp = first_known(
        sample.get("power_latest_sample_at"),
        sample.get("last_device_upload_at"),
        sample.get("last_location_upload_at"),
        sample.get("collected_at"),
    )
    parsed = analyze_power_curve.parse_timestamp(timestamp)
    return parsed.isoformat() if parsed else None


def power_message_from_sample(sample: dict[str, Any], *, index: int, device_id: str | None) -> dict[str, Any] | None:
    if sample.get("ok") is not True:
        return None
    battery_mv = analyze_power_curve.numeric_or_none(sample.get("battery_mv"))
    soc_pct = analyze_power_curve.numeric_or_none(sample.get("soc_pct"))
    source_evidence_status = sample.get("power_evidence_status")
    has_power_hint = any(value not in (None, "") for value in (battery_mv, soc_pct, source_evidence_status))
    if not has_power_hint:
        return None
    evidence_status = first_known(source_evidence_status, "unknown")
    timestamp = timestamp_for_sample(sample)
    transport_type = "lte" if sample.get("cell_lte_seen") is True else "unknown"
    return {
        "protocol_version": "egolink.p0.v1.observer-derived",
        "device_id": first_known(sample.get("device_id"), device_id),
        "message_type": "event",
        "event_type": first_known(sample.get("last_location_event_type"), "field_observer_power_snapshot"),
        "seq": sample.get("last_seq"),
        "server_received_at": timestamp,
        "transport": {"type": transport_type},
        "power": {
            "battery_mv": battery_mv,
            "soc_pct": soc_pct,
            "charging": None,
            "source": "field_observer_dashboard_snapshot",
            "source_status": evidence_status,
            "evidence_status": evidence_status,
            "state": first_known(sample.get("d1_gate_status"), sample.get("d1_status")),
        },
        "observer": {
            "source_sample_index": index,
            "collected_at": sample.get("collected_at"),
            "power_sample_count": sample.get("power_sample_count"),
            "freshness_s": sample.get("freshness_s"),
            "d1_gate_status": sample.get("d1_gate_status"),
        },
    }


def build_power_export(
    *,
    samples_path: Path,
    field_report_path: Path | None = None,
    run_id: str | None = None,
    device_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    field_report = load_json_object(field_report_path) if field_report_path else None
    samples = load_jsonl_objects(samples_path)
    resolved_run_id = infer_run_id(samples_path, field_report, run_id)
    messages = [
        message
        for index, sample in enumerate(samples)
        for message in [power_message_from_sample(sample, index=index, device_id=device_id)]
        if message is not None
    ]
    if not messages:
        raise FieldPowerExportError("field samples contain no usable power snapshots")
    measured_messages = [
        message
        for message in messages
        if str(as_dict(message.get("power")).get("evidence_status") or "").strip().lower() == "measured"
    ]
    return {
        "test_run": {
            "id": resolved_run_id,
            "source": "d1_field_observer_samples",
            "device_id": device_id or first_known(*(message.get("device_id") for message in messages)),
        },
        "messages": messages,
        "raw_frames": [],
        "conversion": {
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "created_at": created_at or utc_now(),
            "samples_path": str(samples_path),
            "field_report_path": str(field_report_path) if field_report_path else None,
            "input_sample_count": len(samples),
            "exported_power_message_count": len(messages),
            "measured_power_message_count": len(measured_messages),
            "scope": {
                "hardware_contacted": False,
                "firmware_changed": False,
                "commands_sent": False,
                "gitlab_modified": False,
                "battery_life_claimed": False,
            },
            "boundaries": [
                "Observer-derived export from existing D1 dashboard samples.",
                "Power evidence status is preserved from the source sample.",
                "This conversion does not prove battery life or PWR-001 acceptance.",
            ],
        },
    }


def write_power_export(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-jsonl", required=True, type=Path)
    parser.add_argument("--field-report", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--device-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def resolve_output_path(args: argparse.Namespace, run_id: str) -> Path:
    if args.output and args.output_dir:
        raise FieldPowerExportError("--output and --output-dir are mutually exclusive")
    if args.output:
        return args.output
    if args.output_dir:
        return args.output_dir / EXPORT_JSON
    return REPO_ROOT / "reports" / "power" / run_id / EXPORT_JSON


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        export = build_power_export(
            samples_path=args.samples_jsonl,
            field_report_path=args.field_report,
            run_id=args.run_id,
            device_id=args.device_id,
            created_at=args.created_at,
        )
        run_id = str(as_dict(export.get("test_run")).get("id") or "unknown-run")
        output_path = resolve_output_path(args, run_id)
        write_power_export(output_path, export)
    except FieldPowerExportError as exc:
        print(f"FAIL D1 field power export: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"status": "PASS", "output_path": str(output_path), "export": export}, ensure_ascii=False, indent=2))
    else:
        conversion = as_dict(export.get("conversion"))
        print(
            "PASS D1 field power export "
            f"run_id={as_dict(export.get('test_run')).get('id')} "
            f"messages={conversion.get('exported_power_message_count')} "
            f"measured={conversion.get('measured_power_message_count')} "
            f"output={output_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
