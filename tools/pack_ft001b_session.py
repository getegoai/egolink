"""FT-001B async Field Session packer with A0-002 time lineage.

Narrow FT-001B variant of the A0-003 packer:
- Consumes a bounded Message Hub field-export (GNSS/LTE messages) and the
  bounded VPS IMU windows JSONL, plus the A0-001 calibration artifact.
- Does NOT require a sidecar bundle; camera and manual_event streams are
  marked not_requested. LTE is opportunistic (may be empty).
- Builds A0-002 time lineage: IMU via server-receive-anchored estimated
  mapping; GNSS via direct source UTC (or receive-only when unavailable);
  LTE receive-only. GNSS is mapped onto the device monotonic clock only when
  every observation carries the same explicit boot_count, uptime and source
  UTC. Server receive time remains transport metadata; absent ingest time is
  left null.
- Produces a sealed package that the replay loader accepts. field_eligible
  will be False (camera/manual_event absent) — that is an honest A-R0 review
  signal, not a replay blocker.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import secrets
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator import field_session
from pc_simulator import field_session_pack as fsp
from pc_simulator import sensor_time_lineage as time_lineage

PACKER_VERSION = "egolink.ft001b_async_pack.v0.2"
MESSAGE_HUB_GNSS_VERSION = "egolink.message_hub_gnss_stream.v0.1"
MESSAGE_HUB_LTE_VERSION = "egolink.message_hub_lte_stream.v0.1"


class FT001BPackError(ValueError):
    pass


def _fail(msg: str) -> None:
    raise FT001BPackError(msg)


def _imu_coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    intervals = sorted(
        (
            int(row["capture"]["capture_start_uptime_us"]),
            int(row["capture"]["capture_end_uptime_us"]),
        )
        for row in rows
    )
    gaps_us = [
        max(0, current_start - previous_end)
        for (_previous_start, previous_end), (current_start, _current_end)
        in zip(intervals, intervals[1:])
    ]
    return {
        "window_count": len(intervals),
        "capture_interval_duration_s": round(
            sum(end - start for start, end in intervals) / 1_000_000,
            6,
        ),
        "wall_span_s": round((intervals[-1][1] - intervals[0][0]) / 1_000_000, 6),
        "inter_window_gap_count": sum(gap > 0 for gap in gaps_us),
        "max_inter_window_gap_s": round(max(gaps_us, default=0) / 1_000_000, 6),
        "continuous_120s_status": "not_evaluated_by_packer",
    }


def _validate_field_export_ft001b(
    value: Mapping[str, Any],
) -> tuple[str, int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    window = value.get("window")
    messages = value.get("messages")
    commands = value.get("commands")
    raw_frames = value.get("raw_frames")
    if not isinstance(window, Mapping) or not isinstance(messages, list) or not messages:
        _fail("field export requires non-empty messages and window object")
    if not isinstance(commands, list) or not isinstance(raw_frames, list):
        _fail("field export commands/messages/raw_frames must all be arrays")
    device_id = fsp._require_safe_id(window.get("device_id"), "field export window.device_id")
    start_ns = fsp._utc_ns(window.get("started_at"), "field export window.started_at")
    end_ns = fsp._utc_ns(window.get("ended_at"), "field export window.ended_at")
    if end_ns <= start_ns:
        _fail("field export window must have positive duration")
    if window.get("complete") is not True:
        _fail("field export window must be complete")
    truncated = window.get("truncated")
    names = {"messages", "commands", "raw_frames"}
    if (
        not isinstance(truncated, Mapping)
        or set(truncated) != names
        or any(truncated[n] is not False for n in names)
    ):
        _fail("field export truncated must be exactly messages/commands/raw_frames=false")
    returned = window.get("returned")
    expected = {
        "messages": len(messages),
        "commands": len(commands),
        "raw_frames": len(raw_frames),
    }
    if (
        not isinstance(returned, Mapping)
        or set(returned) != names
        or any(isinstance(returned[n], bool) or not isinstance(returned[n], int) for n in names)
        or dict(returned) != expected
    ):
        _fail("field export returned counts must exactly match collections")

    gnss: list[dict[str, Any]] = []
    lte: list[dict[str, Any]] = []
    for index, row in enumerate(messages):
        if not isinstance(row, dict):
            _fail(f"field export messages[{index}] must be an object")
        event_type = row.get("event_type")
        if event_type not in ("location_report", "location_observation"):
            continue
        if row.get("message_type") != "event":
            _fail(f"field export messages[{index}] has a location event with unknown message_type")
        if row.get("device_id") != device_id:
            _fail(f"field export messages[{index}] device_id mismatch")
        seq = row.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            _fail(f"field export messages[{index}].seq invalid")
        receive_ns = fsp._utc_ns(row.get("server_received_at"), f"messages[{index}].server_received_at")
        if receive_ns < start_ns or receive_ns > end_ns:
            _fail(f"field export messages[{index}] outside declared window")
        encoded = json.dumps(row, ensure_ascii=False).lower()
        if '"mock"' in encoded and any(
            row.get(k) is True or str(row.get(k, "")).lower().startswith("mock")
            for k in ("mock", "is_mock", "source_status", "gnss_state")
        ):
            _fail(f"field export messages[{index}] is mock evidence")
        if event_type == "location_report":
            if row.get("source_status") not in ("observed", "verified"):
                _fail(
                    f"field export messages[{index}] GNSS source_status must be observed or verified"
                )
            if not isinstance(row.get("fix"), bool):
                _fail(f"field export messages[{index}].fix must be boolean")
            if row["fix"]:
                latitude = row.get("lat")
                longitude = row.get("lon")
                if (
                    isinstance(latitude, bool)
                    or not isinstance(latitude, (int, float))
                    or not math.isfinite(latitude)
                    or not -90 <= latitude <= 90
                    or isinstance(longitude, bool)
                    or not isinstance(longitude, (int, float))
                    or not math.isfinite(longitude)
                    or not -180 <= longitude <= 180
                ):
                    _fail(f"field export messages[{index}] fixed GNSS requires valid coordinates")
        elif row.get("source_status") is not None and row.get("source_status") not in (
            "observed",
            "verified",
        ):
            _fail(
                f"field export messages[{index}] LTE source_status must be observed or verified when present"
            )
        (gnss if event_type == "location_report" else lte).append(row)
    if not gnss:
        _fail("field export contains no GNSS location_report observations")
    for source, rows in (("GNSS", gnss), ("LTE", lte)):
        seqs = [r["seq"] for r in rows]
        if len(set(seqs)) != len(seqs) or any(b <= a for a, b in zip(seqs, seqs[1:])):
            _fail(f"{source} sequence IDs must be unique and increase")
    return device_id, start_ns, end_ns, gnss, lte


def build_time_lineage(
    *,
    gnss_rows: list[dict[str, Any]],
    lte_rows: list[dict[str, Any]],
    imu_rows: list[dict[str, Any]],
    imu_mapping: dict[str, Any],
    session_id: str,
    firmware_commit: str,
    gnss_artifact: Mapping[str, Any],
    lte_artifact: Mapping[str, Any] | None,
    raw_imu_artifact: Mapping[str, Any],
    primary_clock: str,
    boot_count: int,
    device_id: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    """Build A0-002 time records and an optional GNSS clock mapping."""
    records: list[dict[str, Any]] = []

    gnss_source_values = [fsp._gnss_source_utc(row) for row in gnss_rows]
    gnss_source_times = [v for v, _f in gnss_source_values]
    gnss_source_fields = [f for _v, f in gnss_source_values]
    gnss_uptimes = [fsp._parse_uptime_ms(row.get("ts")) for row in gnss_rows]
    gnss_boots = [row.get("boot_count") for row in gnss_rows]
    all_boot_scoped_monotonic = all(
        uptime is not None and row_boot == boot_count
        for uptime, row_boot in zip(gnss_uptimes, gnss_boots)
    )
    gnss_mapping: dict[str, Any] | None = None
    if (
        all(t is not None for t in gnss_source_times)
        and all_boot_scoped_monotonic
    ):
        gnss_mode = "estimated_source_utc"
        gnss_anchors = [
            {
                "anchor_id": f"gnss-source-anchor-{index:06d}",
                "source": "gnss",
                "timestamp_monotonic_ns": int(gnss_uptimes[index]) * 1_000_000,
                "timestamp_utc": str(gnss_source_times[index]),
                "uncertainty_ns": int(imu_mapping["uncertainty_ns"]),
                "source_record_ref": gnss_artifact["path"],
                "source_record_sha256": gnss_artifact["sha256"],
            }
            for index in range(len(gnss_rows))
        ]
        gnss_mapping = fsp._mapping(
            mapping_id="map-gnss-source-estimated",
            device_id=device_id,
            clock_domain_id=primary_clock,
            boot_count=boot_count,
            anchors=gnss_anchors,
            uncertainty_floor_ns=int(imu_mapping["uncertainty_ns"]),
            anchor_method="gnss_source_utc_to_device_uptime_estimate",
            session_id=session_id,
            firmware_commit=firmware_commit,
            created_at=imu_mapping["created_at"],
        )
    elif all_boot_scoped_monotonic:
        gnss_mode = (
            "device_monotonic_with_partial_source_utc"
            if any(t is not None for t in gnss_source_times)
            else "device_monotonic_only"
        )
    elif any(t is not None for t in gnss_source_times):
        gnss_mode = (
            "direct_source_utc_unaligned"
            if all(t is not None for t in gnss_source_times)
            else "mixed_direct_source_utc_and_receive_only"
        )
    else:
        gnss_mode = "receive_only"

    for index, row in enumerate(gnss_rows):
        receive = fsp._utc_text(fsp._utc_ns(row["server_received_at"], "GNSS receive time"))
        source_utc = gnss_source_times[index]
        if gnss_mapping is not None:
            monotonic_ns = int(gnss_uptimes[index]) * 1_000_000
            record = fsp._time_record(
                observation_id=f"gnss-{row['seq']}",
                device_id=device_id,
                source="gnss",
                stream_id="gnss-primary",
                sequence_id=row["seq"],
                clock_domain_id=primary_clock,
                boot_count=boot_count,
                timestamp_monotonic_ns=monotonic_ns,
                timestamp_utc=fsp._utc_text(
                    time_lineage.apply_clock_mapping(gnss_mapping, monotonic_ns)
                ),
                source_timestamp={
                    "raw_value": source_utc,
                    "unit": "iso8601",
                    "clock_domain_id": "gnss-utc",
                    "semantics": "fix_time",
                    "source_field": gnss_source_fields[index],
                },
                receive_timestamp_utc=receive,
                ingest_timestamp_utc=None,
                alignment_status="estimated",
                monotonic_origin="device_capture",
                monotonic_source_field="message.ts",
                utc_origin="clock_mapping",
                mapping_id=gnss_mapping["mapping_id"],
                uncertainty_ns=gnss_mapping["uncertainty_ns"],
                reason_codes=["gnss_source_utc_mapping_estimated"],
                session_id=session_id,
                test_run_id=row.get("test_run_id"),
                firmware_version=row.get("fw_version"),
                firmware_commit=firmware_commit,
                source_artifact=gnss_artifact,
            )
        elif all_boot_scoped_monotonic:
            monotonic_ns = int(gnss_uptimes[index]) * 1_000_000
            if source_utc is not None:
                source_timestamp = {
                    "raw_value": source_utc,
                    "unit": "iso8601",
                    "clock_domain_id": "gnss-utc",
                    "semantics": "fix_time",
                    "source_field": gnss_source_fields[index],
                }
                timestamp_utc = source_utc
                monotonic_origin = "device_capture"
                utc_origin = "source_timestamp"
                reason_codes = ["gnss_direct_utc_and_device_monotonic_unaligned"]
            else:
                source_timestamp = {
                    "raw_value": int(gnss_uptimes[index]),
                    "unit": "ms",
                    "clock_domain_id": primary_clock,
                    "semantics": "fix_time",
                    "source_field": "message.ts",
                }
                timestamp_utc = None
                monotonic_origin = "source_timestamp"
                utc_origin = "unavailable"
                reason_codes = ["gnss_utc_unavailable_device_monotonic_preserved"]
            record = fsp._time_record(
                observation_id=f"gnss-{row['seq']}",
                device_id=device_id,
                source="gnss",
                stream_id="gnss-primary",
                sequence_id=row["seq"],
                clock_domain_id=primary_clock,
                boot_count=boot_count,
                timestamp_monotonic_ns=monotonic_ns,
                timestamp_utc=timestamp_utc,
                source_timestamp=source_timestamp,
                receive_timestamp_utc=receive,
                ingest_timestamp_utc=None,
                alignment_status="unavailable",
                monotonic_origin=monotonic_origin,
                monotonic_source_field="message.ts",
                utc_origin=utc_origin,
                mapping_id=None,
                uncertainty_ns=None,
                reason_codes=reason_codes,
                session_id=session_id,
                test_run_id=row.get("test_run_id"),
                firmware_version=row.get("fw_version"),
                firmware_commit=firmware_commit,
                source_artifact=gnss_artifact,
            )
        elif source_utc is not None:
            record = fsp._time_record(
                observation_id=f"gnss-{row['seq']}",
                device_id=device_id,
                source="gnss",
                stream_id="gnss-primary",
                sequence_id=row["seq"],
                clock_domain_id=None,
                boot_count=None,
                timestamp_monotonic_ns=None,
                timestamp_utc=source_utc,
                source_timestamp={
                    "raw_value": source_utc,
                    "unit": "iso8601",
                    "clock_domain_id": "gnss-utc",
                    "semantics": "fix_time",
                    "source_field": gnss_source_fields[index],
                },
                receive_timestamp_utc=receive,
                ingest_timestamp_utc=None,
                alignment_status="unavailable",
                monotonic_origin="unavailable",
                monotonic_source_field=None,
                utc_origin="source_timestamp",
                mapping_id=None,
                uncertainty_ns=None,
                reason_codes=["gnss_monotonic_unavailable_direct_source_utc_only"],
                session_id=session_id,
                test_run_id=row.get("test_run_id"),
                firmware_version=row.get("fw_version"),
                firmware_commit=firmware_commit,
                source_artifact=gnss_artifact,
            )
        else:
            raw_time = row.get("ts")
            record = fsp._time_record(
                observation_id=f"gnss-{row['seq']}",
                device_id=device_id,
                source="gnss",
                stream_id="gnss-primary",
                sequence_id=row["seq"],
                clock_domain_id=None,
                boot_count=None,
                timestamp_monotonic_ns=None,
                timestamp_utc=None,
                source_timestamp={
                    "raw_value": raw_time if raw_time is not None else None,
                    "unit": "opaque" if raw_time is not None else "unavailable",
                    "clock_domain_id": None,
                    "semantics": "unknown",
                    "source_field": "message.ts" if raw_time is not None else None,
                },
                receive_timestamp_utc=receive,
                ingest_timestamp_utc=None,
                alignment_status="receive_only",
                monotonic_origin="unavailable",
                monotonic_source_field=None,
                utc_origin="unavailable",
                mapping_id=None,
                uncertainty_ns=None,
                reason_codes=["gnss_source_utc_unavailable"],
                session_id=session_id,
                test_run_id=row.get("test_run_id"),
                firmware_version=row.get("fw_version"),
                firmware_commit=firmware_commit,
                source_artifact=gnss_artifact,
            )
        record["lineage"]["source_status"] = str(row["source_status"])
        records.append(record)

    _append_lte_and_imu_records(
        records,
        lte_rows=lte_rows,
        imu_rows=imu_rows,
        imu_mapping=imu_mapping,
        session_id=session_id,
        firmware_commit=firmware_commit,
        lte_artifact=lte_artifact,
        raw_imu_artifact=raw_imu_artifact,
        primary_clock=primary_clock,
        boot_count=boot_count,
        device_id=device_id,
    )
    return records, gnss_mode, gnss_mapping


def _append_lte_and_imu_records(
    records: list[dict[str, Any]],
    *,
    lte_rows: list[dict[str, Any]],
    imu_rows: list[dict[str, Any]],
    imu_mapping: dict[str, Any],
    session_id: str,
    firmware_commit: str,
    lte_artifact: Mapping[str, Any] | None,
    raw_imu_artifact: Mapping[str, Any],
    primary_clock: str,
    boot_count: int,
    device_id: str,
) -> None:
    if lte_rows and lte_artifact is None:
        _fail("LTE rows require a source artifact")
    for row in lte_rows:
        receive = fsp._utc_text(fsp._utc_ns(row["server_received_at"], "LTE receive time"))
        raw_time = row.get("ts")
        record = fsp._time_record(
                observation_id=f"lte-{row['seq']}",
                device_id=device_id,
                source="lte",
                stream_id="lte-primary",
                sequence_id=row["seq"],
                clock_domain_id=None,
                boot_count=None,
                timestamp_monotonic_ns=None,
                timestamp_utc=None,
                source_timestamp={
                    "raw_value": raw_time if raw_time is not None else None,
                    "unit": "opaque" if raw_time is not None else "unavailable",
                    "clock_domain_id": None,
                    "semantics": "modem_event_time" if raw_time is not None else "unknown",
                    "source_field": "message.ts" if raw_time is not None else None,
                },
                receive_timestamp_utc=receive,
                ingest_timestamp_utc=None,
                alignment_status="receive_only",
                monotonic_origin="unavailable",
                monotonic_source_field=None,
                utc_origin="unavailable",
                mapping_id=None,
                uncertainty_ns=None,
                reason_codes=["lte_device_time_unavailable_receive_only"],
                session_id=session_id,
                test_run_id=row.get("test_run_id"),
                firmware_version=row.get("fw_version"),
                firmware_commit=firmware_commit,
                source_artifact=lte_artifact,
            )
        record["lineage"]["source_status"] = str(row.get("source_status") or "unknown")
        records.append(record)

    ordered_imu = sorted(imu_rows, key=lambda item: item["capture"]["capture_start_uptime_us"])
    for sequence, row in enumerate(ordered_imu):
        monotonic_ns = row["capture"]["capture_start_uptime_us"] * 1_000
        records.append(
            fsp._time_record(
                observation_id=f"imu-{sequence:06d}",
                device_id=device_id,
                source="imu",
                stream_id="imu-primary",
                sequence_id=sequence,
                clock_domain_id=primary_clock,
                boot_count=boot_count,
                timestamp_monotonic_ns=monotonic_ns,
                timestamp_utc=fsp._utc_text(
                    time_lineage.apply_clock_mapping(imu_mapping, monotonic_ns)
                ),
                source_timestamp={
                    "raw_value": row["capture"]["capture_start_uptime_us"],
                    "unit": "us",
                    "clock_domain_id": primary_clock,
                    "semantics": "sample_time",
                    "source_field": "capture.capture_start_uptime_us",
                },
                receive_timestamp_utc=fsp._utc_text(
                    fsp._utc_ns(row["server_received_at_first"], "IMU receive start")
                ),
                ingest_timestamp_utc=None,
                alignment_status="estimated",
                monotonic_origin="source_timestamp",
                monotonic_source_field="capture.capture_start_uptime_us",
                utc_origin="clock_mapping",
                mapping_id=imu_mapping["mapping_id"],
                uncertainty_ns=imu_mapping["uncertainty_ns"],
                reason_codes=["server_receive_anchor_estimated"],
                session_id=session_id,
                test_run_id=row["test_run_id"],
                firmware_version=row["fw_version"],
                firmware_commit=firmware_commit,
                source_artifact=raw_imu_artifact,
                imu_derivation={
                    "method": "capture_start_uptime_us_plus_offset_us",
                    "window_id": row["window_id"],
                    "capture_start_uptime_us": row["capture"]["capture_start_uptime_us"],
                    "capture_end_uptime_us": row["capture"]["capture_end_uptime_us"],
                    "offset_us": 0,
                },
            )
        )

def pack_ft001b(
    *,
    field_export_path: Path,
    imu_windows_path: Path,
    calibration_artifact_path: Path,
    output_dir: Path,
    test_scenario: str,
    firmware_commit: str,
    firmware_image_sha256: str,
    repository_commit: str,
    session_id: str | None = None,
    operator_ref: str = "ft001b-operator",
) -> dict[str, Any]:
    firmware_commit = fsp._require_commit(firmware_commit, "firmware_commit")
    firmware_image_sha256 = fsp._require_sha256(firmware_image_sha256, "firmware_image_sha256")
    repository_commit = fsp._require_commit(repository_commit, "repository_commit")
    if not isinstance(test_scenario, str) or not test_scenario.strip() or len(test_scenario) > 256:
        _fail("test_scenario must be a non-empty string of at most 256 characters")

    inputs = [field_export_path, imu_windows_path, calibration_artifact_path]
    resolved = [p.resolve(strict=False) for p in inputs]
    if len(set(resolved)) != len(resolved):
        _fail("all packer inputs must be distinct files")
    output = output_dir.resolve(strict=False)
    if output.exists():
        _fail(f"output_dir already exists; refusing to overwrite: {output}")
    if any(output == p or output in p.parents for p in resolved):
        _fail("output_dir must not contain an explicit input")

    field_bytes = fsp._require_file(field_export_path, "Message Hub field export")
    imu_bytes = fsp._require_file(imu_windows_path, "IMU windows JSONL")
    calibration_bytes = fsp._require_file(calibration_artifact_path, "A0-001 calibration artifact")
    field_export = fsp._load_json_bytes(field_bytes, "Message Hub field export")
    imu_rows = fsp._load_jsonl_bytes(imu_bytes, "IMU windows JSONL")
    calibration = fsp._load_json_bytes(calibration_bytes, "A0-001 calibration artifact")

    fsp._validate_calibration(
        calibration,
        firmware_commit=firmware_commit,
        firmware_image_sha256=firmware_image_sha256,
    )
    for name, value in (("Message Hub field export", field_export), ("IMU windows", {"rows": imu_rows})):
        fsp._check_input_provenance(
            value,
            name=name,
            firmware_commit=firmware_commit,
            firmware_image_sha256=firmware_image_sha256,
            repository_commit=repository_commit,
        )

    device_id, start_ns, end_ns, gnss_rows, lte_rows = _validate_field_export_ft001b(field_export)
    if calibration["device"]["device_id"] != device_id:
        _fail("field export device_id conflicts with the calibration artifact")
    boot_count = fsp._field_boot_count(field_export, imu_rows)
    fsp._validate_imu_rows(
        imu_rows,
        calibration=calibration,
        device_id=device_id,
        boot_count=boot_count,
        start_ns=start_ns,
        end_ns=end_ns,
    )

    sid = session_id or field_session.generate_session_id()
    if not isinstance(sid, str) or not fsp.SAFE_ID.fullmatch(sid):
        _fail("session_id must be a safe identifier")

    staging = output.parent / f".{output.name}.pack-{secrets.token_hex(6)}"
    if staging.exists():
        _fail(f"temporary output collision: {staging}")
    staging.mkdir(parents=True)
    try:
        return _pack_stage(
            staging=staging,
            output=output,
            field_bytes=field_bytes,
            imu_bytes=imu_bytes,
            calibration_bytes=calibration_bytes,
            calibration=calibration,
            field_export=field_export,
            gnss_rows=gnss_rows,
            lte_rows=lte_rows,
            imu_rows=imu_rows,
            device_id=device_id,
            boot_count=boot_count,
            start_ns=start_ns,
            end_ns=end_ns,
            session_id=sid,
            operator_ref=operator_ref,
            test_scenario=test_scenario,
            firmware_commit=firmware_commit,
            firmware_image_sha256=firmware_image_sha256,
            repository_commit=repository_commit,
        )
    except Exception:
        if staging.exists() and staging.parent == output.parent:
            shutil.rmtree(staging)
        raise


def _pack_stage(
    *,
    staging: Path,
    output: Path,
    field_bytes: bytes,
    imu_bytes: bytes,
    calibration_bytes: bytes,
    calibration: Mapping[str, Any],
    field_export: Mapping[str, Any],
    gnss_rows: list[dict[str, Any]],
    lte_rows: list[dict[str, Any]],
    imu_rows: list[dict[str, Any]],
    device_id: str,
    boot_count: int,
    start_ns: int,
    end_ns: int,
    session_id: str,
    operator_ref: str,
    test_scenario: str,
    firmware_commit: str,
    firmware_image_sha256: str,
    repository_commit: str,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    fsp._write_bytes(staging / "inputs/message-hub-field-export.json", field_bytes)
    artifacts.append(
        fsp._artifact(
            staging,
            artifact_id="input-message-hub-field-export",
            relative_path="inputs/message-hub-field-export.json",
            role="legacy_attachment",
            format_name="json",
            media_type="application/json",
            contract="egolink.message_hub_field_export.v0.1",
            privacy_class="private_location",
            record_count=None,
        )
    )
    fsp._write_bytes(staging / "calibration/imu-calibration.json", calibration_bytes)
    calibration_artifact = fsp._artifact(
        staging,
        artifact_id="imu-calibration-artifact",
        relative_path="calibration/imu-calibration.json",
        role="calibration",
        format_name="json",
        media_type="application/json",
        contract=fsp.CALIBRATION_CONTRACT_VERSION,
        privacy_class="structured_sensor",
        record_count=None,
    )
    artifacts.append(calibration_artifact)

    fsp._write_bytes(staging / "streams/gnss.jsonl", fsp._stable_jsonl(gnss_rows))
    gnss_artifact = fsp._artifact(
        staging,
        artifact_id="stream-gnss",
        relative_path="streams/gnss.jsonl",
        role="stream_data",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=MESSAGE_HUB_GNSS_VERSION,
        privacy_class="private_location",
        record_count=len(gnss_rows),
    )
    artifacts.append(gnss_artifact)
    lte_artifact = None
    if lte_rows:
        fsp._write_bytes(staging / "streams/lte.jsonl", fsp._stable_jsonl(lte_rows))
        lte_artifact = fsp._artifact(
            staging,
            artifact_id="stream-lte",
            relative_path="streams/lte.jsonl",
            role="stream_data",
            format_name="jsonl",
            media_type="application/x-ndjson",
            contract=MESSAGE_HUB_LTE_VERSION,
            privacy_class="private_location",
            record_count=len(lte_rows),
        )
        artifacts.append(lte_artifact)
    fsp._write_bytes(staging / "streams/imu-raw.jsonl", imu_bytes)
    raw_imu_artifact = fsp._artifact(
        staging,
        artifact_id="stream-imu-raw",
        relative_path="streams/imu-raw.jsonl",
        role="stream_data",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract="egolink.imu_window.v1",
        privacy_class="structured_sensor",
        record_count=len(imu_rows),
    )
    artifacts.append(raw_imu_artifact)

    calibrated_rows = fsp._calibrated_rows(
        imu_rows, calibration, session_id=session_id, raw_artifact_sha256=raw_imu_artifact["sha256"]
    )
    fsp._write_bytes(staging / "streams/imu-calibrated.jsonl", fsp._stable_jsonl(calibrated_rows))
    calibrated_artifact = fsp._artifact(
        staging,
        artifact_id="stream-imu-calibrated",
        relative_path="streams/imu-calibrated.jsonl",
        role="stream_data",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
        privacy_class="structured_sensor",
        record_count=len(calibrated_rows),
    )
    artifacts.append(calibrated_artifact)

    ctx = dict(
        staging=staging,
        output=output,
        artifacts=artifacts,
        calibration=calibration,
        calibration_artifact=calibration_artifact,
        gnss_artifact=gnss_artifact,
        lte_artifact=lte_artifact,
        raw_imu_artifact=raw_imu_artifact,
        calibrated_artifact=calibrated_artifact,
        calibrated_rows=calibrated_rows,
        field_export=field_export,
        imu_rows=imu_rows,
        gnss_rows=gnss_rows,
        lte_rows=lte_rows,
        device_id=device_id,
        boot_count=boot_count,
        start_ns=start_ns,
        end_ns=end_ns,
        session_id=session_id,
        operator_ref=operator_ref,
        test_scenario=test_scenario,
        firmware_commit=firmware_commit,
        firmware_image_sha256=firmware_image_sha256,
        repository_commit=repository_commit,
    )
    return _pack_stage_time_and_finalize(**ctx)


def _pack_stage_time_and_finalize(**ctx: Any) -> dict[str, Any]:
    staging: Path = ctx["staging"]
    uncertainty_floor_ns = ctx["end_ns"] - ctx["start_ns"]
    created_at = fsp._utc_text(ctx["end_ns"])
    primary_clock = f"{ctx['device_id']}:boot:{ctx['boot_count']}:uptime"
    primary_run_id = f"{ctx['device_id']}:boot:{ctx['boot_count']}"
    receive_only_run_id = f"{ctx['device_id']}:receive-only"

    imu_anchors = []
    for index, row in enumerate(ctx["imu_rows"]):
        for edge, uptime_key, receive_key in (
            ("start", "capture_start_uptime_us", "server_received_at_first"),
            ("end", "capture_end_uptime_us", "server_received_at_last"),
        ):
            imu_anchors.append(
                {
                    "anchor_id": f"imu-server-anchor-{index:06d}-{edge}",
                    "source": "host_clock",
                    "timestamp_monotonic_ns": row["capture"][uptime_key] * 1_000,
                    "timestamp_utc": fsp._utc_text(
                        fsp._utc_ns(row[receive_key], f"IMU server receive {edge}")
                    ),
                    "uncertainty_ns": uncertainty_floor_ns,
                    "source_record_ref": ctx["raw_imu_artifact"]["path"],
                    "source_record_sha256": ctx["raw_imu_artifact"]["sha256"],
                }
            )
    imu_mapping = fsp._mapping(
        mapping_id="map-imu-server-estimated",
        device_id=ctx["device_id"],
        clock_domain_id=primary_clock,
        boot_count=ctx["boot_count"],
        anchors=imu_anchors,
        uncertainty_floor_ns=uncertainty_floor_ns,
        anchor_method="server_receive_window_estimate",
        session_id=ctx["session_id"],
        firmware_commit=ctx["firmware_commit"],
        created_at=created_at,
    )
    mappings = [imu_mapping]

    records, gnss_mode, gnss_mapping = build_time_lineage(
        gnss_rows=ctx["gnss_rows"],
        lte_rows=ctx["lte_rows"],
        imu_rows=ctx["imu_rows"],
        imu_mapping=imu_mapping,
        session_id=ctx["session_id"],
        firmware_commit=ctx["firmware_commit"],
        gnss_artifact=ctx["gnss_artifact"],
        lte_artifact=ctx["lte_artifact"],
        raw_imu_artifact=ctx["raw_imu_artifact"],
        primary_clock=primary_clock,
        boot_count=ctx["boot_count"],
        device_id=ctx["device_id"],
    )
    if gnss_mapping is not None:
        mappings.append(gnss_mapping)

    ordered_records = sorted(records, key=lambda item: (item["source"], item["sequence_id"]))
    fsp._write_bytes(staging / "time/clock-mappings.jsonl", fsp._stable_jsonl(mappings))
    mapping_artifact = fsp._artifact(
        staging,
        artifact_id="clock-mappings",
        relative_path="time/clock-mappings.jsonl",
        role="clock_mapping",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=time_lineage.CLOCK_MAPPING_VERSION,
        privacy_class="private_location",
        record_count=len(mappings),
    )
    ctx["artifacts"].append(mapping_artifact)
    fsp._write_bytes(staging / "time/time-records.jsonl", fsp._stable_jsonl(ordered_records))
    time_artifact = fsp._artifact(
        staging,
        artifact_id="time-records",
        relative_path="time/time-records.jsonl",
        role="time_lineage_records",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=time_lineage.TIME_LINEAGE_VERSION,
        privacy_class="private_location",
        record_count=len(ordered_records),
    )
    ctx["artifacts"].append(time_artifact)
    time_report = time_lineage.validate_time_lineage(
        ordered_records, mappings, generated_at=created_at
    )
    if not time_report["valid"]:
        _fail(f"generated A0-002 lineage is invalid: {time_report['errors'][:3]}")
    fsp._write_json(staging / "time/a0-002-validation-report.json", time_report)
    time_report_artifact = fsp._artifact(
        staging,
        artifact_id="a0-002-validation-report",
        relative_path="time/a0-002-validation-report.json",
        role="time_validation_report",
        format_name="json",
        media_type="application/json",
        contract=time_lineage.REPORT_VERSION,
        privacy_class="private_location",
        record_count=None,
    )
    ctx["artifacts"].append(time_report_artifact)

    return _build_and_seal_manifest(
        ctx=ctx,
        ordered_records=ordered_records,
        mappings=mappings,
        mapping_artifact=mapping_artifact,
        time_artifact=time_artifact,
        time_report_artifact=time_report_artifact,
        gnss_mode=gnss_mode,
        primary_clock=primary_clock,
        primary_run_id=primary_run_id,
        receive_only_run_id=receive_only_run_id,
        created_at=created_at,
    )


def _build_and_seal_manifest(
    *,
    ctx: dict[str, Any],
    ordered_records: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    mapping_artifact: Mapping[str, Any],
    time_artifact: Mapping[str, Any],
    time_report_artifact: Mapping[str, Any],
    gnss_mode: str,
    primary_clock: str,
    primary_run_id: str,
    receive_only_run_id: str,
    created_at: str,
) -> dict[str, Any]:
    staging: Path = ctx["staging"]
    output: Path = ctx["output"]
    fw_version = ctx["calibration"]["firmware"]["fw_version"]

    manifest = field_session.build_draft_manifest(
        device_id=ctx["device_id"],
        operator_ref=ctx["operator_ref"],
        protocol_id="FT-001B",
        test_scenario=ctx["test_scenario"],
        created_at_utc=created_at,
        session_id=ctx["session_id"],
    )
    manifest["lifecycle_state"] = "complete"
    event_time_values = [
        fsp._utc_ns(row["timestamp_utc"], f"{row['observation_id']}.timestamp_utc")
        for row in ordered_records
        if row["timestamp_utc"] is not None
        and row["alignment"]["timestamp_utc_origin"] in ("source_timestamp", "clock_mapping")
    ]
    mapping_index = {row["mapping_id"]: row for row in mappings}
    for row in ordered_records:
        derivation = row.get("imu_sample_derivation")
        mapping_id = row["alignment"].get("mapping_id")
        if (
            row["source"] == "imu"
            and isinstance(derivation, Mapping)
            and mapping_id in mapping_index
        ):
            event_time_values.append(
                time_lineage.apply_clock_mapping(
                    mapping_index[mapping_id],
                    int(derivation["capture_end_uptime_us"]) * 1_000,
                )
            )
    if len(event_time_values) < 2 or max(event_time_values) <= min(event_time_values):
        _fail("cannot derive a positive capture interval from source or mapped event time")
    manifest["capture_interval"] = {
        "start_utc": fsp._utc_text(min(event_time_values)),
        "end_utc": fsp._utc_text(max(event_time_values)),
        "timezone": "Asia/Shanghai",
    }
    manifest["device_runs"] = [
        {
            "device_run_id": primary_run_id,
            "device_id": ctx["device_id"],
            "role": "primary",
            "board_id": ctx["calibration"]["device"]["board_id"],
            "hardware_revision": ctx["calibration"]["device"]["hardware_revision"],
            "firmware_version": fw_version,
            "firmware_commit": ctx["firmware_commit"],
            "firmware_image_sha256": ctx["firmware_image_sha256"],
            "boot_count": ctx["boot_count"],
            "monotonic_clock_domain_ids": [primary_clock],
            "source_status": "observed",
        },
        {
            "device_run_id": receive_only_run_id,
            "device_id": ctx["device_id"],
            "role": "connectivity",
            "board_id": ctx["calibration"]["device"]["board_id"],
            "hardware_revision": ctx["calibration"]["device"]["hardware_revision"],
            "firmware_version": fw_version,
            "firmware_commit": ctx["firmware_commit"],
            "firmware_image_sha256": ctx["firmware_image_sha256"],
            "boot_count": None,
            "monotonic_clock_domain_ids": [],
            "source_status": "unverified",
        },
    ]
    manifest["software"] = {
        "repository": "egolink",
        "repository_commit": ctx["repository_commit"],
        "capture_tool": "tools.pack_ft001b_session",
        "capture_tool_version": PACKER_VERSION,
    }
    manifest["scenario"].update(
        {
            "declared_carry_conditions": [],
            "declared_motion_conditions": [],
            "declared_environments": [],
            "notes": (
                "FT-001B async session. Operator-supplied test_scenario is preserved; "
                "no carry, motion, or environment labels are inferred. Camera/manual_event "
                "were not requested; IMU windows retain their real gaps."
            ),
        }
    )
    manifest["capture_profile"]["protocol_version"] = "FT-001B-v0.1"
    manifest["capture_profile"]["required_sources"] = ["gnss", "imu"]
    manifest["capture_profile"]["optional_sources"] = ["lte", "camera", "audio", "device", "label", "manual_event"]
    manifest["sensor_policies"].update(
        {
            "imu": {"mode": "event_triggered", "policy_id": "bounded-imu-window-v1", "requested_rate_hz": 20.0, "config_artifact_id": None},
            "gnss": {"mode": "scheduled", "policy_id": "fw007-field-policy", "requested_rate_hz": None, "config_artifact_id": None},
            "lte": {"mode": "scheduled", "policy_id": "fw007-field-policy", "requested_rate_hz": None, "config_artifact_id": None},
            "camera": {"mode": "disabled", "policy_id": None, "requested_rate_hz": None, "config_artifact_id": None},
            "audio": {"mode": "disabled", "policy_id": None, "requested_rate_hz": None, "config_artifact_id": None},
        }
    )
    manifest["privacy"].update(
        {
            "consent_status": "not_reviewed",
            "privacy_review_status": "not_reviewed",
            "location_privacy_class": "engineering_private",
            "raw_image_allowed": False,
            "retention_status": "not_reviewed",
            "consent_artifact_id": None,
            "retention_policy_artifact_id": None,
            "reviewed_by": None,
            "reviewed_at_utc": None,
        }
    )
    manifest["provenance"]["message_hub_test_run_ids"] = fsp._input_test_run_ids(
        ctx["field_export"], ctx["imu_rows"]
    )
    manifest["artifacts"] = ctx["artifacts"]
    return _finalize_streams_and_seal(
        ctx=ctx,
        manifest=manifest,
        staging=staging,
        output=output,
        ordered_records=ordered_records,
        mapping_artifact=mapping_artifact,
        time_artifact=time_artifact,
        time_report_artifact=time_report_artifact,
        gnss_mode=gnss_mode,
        primary_clock=primary_clock,
        primary_run_id=primary_run_id,
        receive_only_run_id=receive_only_run_id,
        created_at=created_at,
    )


def _finalize_streams_and_seal(
    *,
    ctx: dict[str, Any],
    manifest: dict[str, Any],
    staging: Path,
    output: Path,
    ordered_records: list[dict[str, Any]],
    mapping_artifact: Mapping[str, Any],
    time_artifact: Mapping[str, Any],
    time_report_artifact: Mapping[str, Any],
    gnss_mode: str,
    primary_clock: str,
    primary_run_id: str,
    receive_only_run_id: str,
    created_at: str,
) -> dict[str, Any]:
    records_by_source: dict[str, list[dict[str, Any]]] = {
        source: [row for row in ordered_records if row["source"] == source]
        for source in time_lineage.SOURCES
    }
    for stream in manifest["streams"]:
        if stream["source"] in ("camera", "manual_event", "audio", "device", "label"):
            stream["status"] = "not_requested"
            stream["reason_codes"] = ["not_required_for_ft001b"]

    gnss_uses_primary_clock = (
        gnss_mode == "estimated_source_utc" or gnss_mode.startswith("device_monotonic")
    )
    gnss_run = primary_run_id if gnss_uses_primary_clock else receive_only_run_id
    fsp._set_stream(
        manifest,
        stream_id="gnss-primary",
        source="gnss",
        artifact=ctx["gnss_artifact"],
        contract=MESSAGE_HUB_GNSS_VERSION,
        observation_count=len(ctx["gnss_rows"]),
        bounds=field_session._observed_bounds(records_by_source["gnss"]),
        device_run_id=gnss_run,
        clock_domain_id=primary_clock if gnss_uses_primary_clock else None,
    )
    if ctx["lte_rows"]:
        fsp._set_stream(
            manifest,
            stream_id="lte-primary",
            source="lte",
            artifact=ctx["lte_artifact"],
            contract=MESSAGE_HUB_LTE_VERSION,
            observation_count=len(ctx["lte_rows"]),
            bounds=field_session._observed_bounds(records_by_source["lte"]),
            device_run_id=receive_only_run_id,
            clock_domain_id=None,
        )
    else:
        lte_stream = next(item for item in manifest["streams"] if item["source"] == "lte")
        lte_stream["status"] = "declared_unavailable"
        lte_stream["reason_codes"] = ["no_lte_observation_in_bounded_export"]
    raw_stream = fsp._set_stream(
        manifest,
        stream_id="imu-primary",
        source="imu",
        artifact=ctx["raw_imu_artifact"],
        contract="egolink.imu_window.v1",
        observation_count=len(ctx["imu_rows"]),
        bounds=field_session._observed_bounds(records_by_source["imu"]),
        device_run_id=primary_run_id,
        clock_domain_id=primary_clock,
        variant="uncalibrated_engineering",
    )
    manifest["streams"].append(
        {
            "stream_id": "imu-calibrated",
            "source": "imu",
            "variant": "calibrated",
            "status": "captured",
            "format": "jsonl",
            "record_contract_version": field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
            "artifact_id": ctx["calibrated_artifact"]["artifact_id"],
            "observation_count": len(ctx["calibrated_rows"]),
            "device_run_id": primary_run_id,
            "clock_domain_id": primary_clock,
            "bounds": copy.deepcopy(raw_stream["bounds"]),
            "raw_preserved": True,
            "calibration_id": ctx["calibration"]["calibration_id"],
            "source_stream_id": raw_stream["stream_id"],
            "generator": {
                "name": "tools.pack_ft001b_session",
                "version": PACKER_VERSION,
                "commit": ctx["repository_commit"],
                "source_stream_ids": ["imu-primary"],
                "config_artifact_id": ctx["calibration_artifact"]["artifact_id"],
            },
            "reason_codes": [],
        }
    )
    manifest["calibrations"] = [
        {
            "calibration_id": ctx["calibration"]["calibration_id"],
            "sensor": "imu",
            "device_id": ctx["device_id"],
            "status": "engineering",
            "artifact_id": ctx["calibration_artifact"]["artifact_id"],
            "applies_to_stream_ids": ["imu-calibrated"],
        }
    ]
    manifest["time_lineage"] = {
        "record_contract_version": time_lineage.TIME_LINEAGE_VERSION,
        "mapping_contract_version": time_lineage.CLOCK_MAPPING_VERSION,
        "record_artifact_ids": [time_artifact["artifact_id"]],
        "mapping_artifact_ids": [mapping_artifact["artifact_id"]],
        "validation_report_artifact_id": time_report_artifact["artifact_id"],
    }
    manifest["limitations"].extend(
        [
            "FT-001B uses independent asynchronous capture; cross-source ordering follows capture/event time only when source provenance exists.",
            "Camera and manual events are optional for this first replayable GNSS+IMU session.",
            "A-R0 remains unverified; this package must not be treated as a Gate PASS.",
        ]
    )
    return _seal_and_finish(
        ctx=ctx,
        manifest=manifest,
        staging=staging,
        output=output,
        created_at=created_at,
    )


def _seal_and_finish(
    *,
    ctx: dict[str, Any],
    manifest: dict[str, Any],
    staging: Path,
    output: Path,
    created_at: str,
) -> dict[str, Any]:
    gnss_fix_count = sum(
        row.get("fix") is True and row.get("lat") is not None and row.get("lon") is not None
        for row in ctx["gnss_rows"]
    )
    imu_coverage = _imu_coverage_summary(ctx["imu_rows"])
    if gnss_fix_count >= 2:
        gnss_trajectory_status = "candidate_for_replay_not_quality_accepted"
    elif gnss_fix_count == 1:
        gnss_trajectory_status = "unavailable_single_valid_fix"
    else:
        gnss_trajectory_status = "unavailable_no_valid_fix"
    sealed = field_session.seal_manifest(
        manifest, sealed_by=ctx["operator_ref"], sealed_at_utc=created_at
    )
    manifest_path = staging / "manifest.json"
    fsp._write_json(manifest_path, sealed)
    validation = field_session.validate_field_session(
        sealed, session_root=staging, manifest_path=manifest_path, generated_at=created_at
    )
    if not validation["valid"]:
        _fail(f"generated Field Session is invalid: {validation['errors'][:5]}")
    required_flags = (
        "manifest_file_binding_verified",
        "artifact_integrity_verified",
        "package_closure_verified",
        "imu_raw_calibrated_chain_verified",
        "a0_002_report_binding_verified",
    )
    missing_flags = [name for name in required_flags if validation.get(name) is not True]
    if missing_flags:
        _fail(f"generated Field Session lacks structural proof: {missing_flags}")
    staging.replace(output)
    final_manifest_path = output / "manifest.json"
    final_validation = field_session.validate_field_session(
        sealed, session_root=output, manifest_path=final_manifest_path, generated_at=created_at
    )
    if not final_validation["valid"]:
        _fail(f"finalized Field Session failed validation: {final_validation['errors'][:5]}")
    return {
        "pack_version": PACKER_VERSION,
        "ok": True,
        "evidence_scope": "engineering_smoke_only",
        "gate_status": "unverified",
        "session_id": ctx["session_id"],
        "output_dir": str(output),
        "manifest": str(final_manifest_path),
        "manifest_sha256": field_session.sha256_file(final_manifest_path),
        "source_counts": {
            "gnss": len(ctx["gnss_rows"]),
            "gnss_valid_fix_with_coordinate": gnss_fix_count,
            "lte": len(ctx["lte_rows"]),
            "imu_windows_raw": len(ctx["imu_rows"]),
            "imu_windows_calibrated": len(ctx["calibrated_rows"]),
            "camera": 0,
            "manual_event": 0,
        },
        "time_status": {
            "gnss": "see_manifest_time_lineage",
            "lte": "receive_only",
            "imu": "estimated_server_anchor",
            "camera": "not_requested",
            "a0_002_field_eligible": final_validation["a0_002_time_lineage"]["field_eligible"],
        },
        "not_requested": ["camera", "manual_event", "audio", "device", "label"],
        "honesty": {
            "gnss_trajectory": gnss_trajectory_status,
            "continuous_imu_120s": "not_evaluated_by_packer",
            "imu_coverage": imu_coverage,
            "camera": "not_requested",
            "lte_cell_coarse_location_mapping": "unavailable",
        },
        "field_eligible": final_validation["field_eligible"],
        "field_eligibility_reasons": final_validation["field_eligibility_reasons"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-export", required=True, type=Path)
    parser.add_argument("--imu-windows", required=True, type=Path)
    parser.add_argument("--calibration-artifact", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--test-scenario", required=True)
    parser.add_argument("--firmware-commit", required=True)
    parser.add_argument("--firmware-image-sha256", required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--operator-ref", default="ft001b-operator")
    args = parser.parse_args(argv)
    try:
        result = pack_ft001b(
            field_export_path=args.field_export,
            imu_windows_path=args.imu_windows,
            calibration_artifact_path=args.calibration_artifact,
            output_dir=args.output_dir,
            test_scenario=args.test_scenario,
            firmware_commit=args.firmware_commit,
            firmware_image_sha256=args.firmware_image_sha256,
            repository_commit=args.repository_commit,
            session_id=args.session_id,
            operator_ref=args.operator_ref,
        )
    except (
        FT001BPackError,
        field_session.FieldSessionError,
        time_lineage.SensorTimeLineageError,
        OSError,
    ) as error:
        print(f"FT-001B pack error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
