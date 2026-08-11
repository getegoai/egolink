"""Explicit local export for complete bounded IMU windows retained by Message Hub.

This tool intentionally reads a named SQLite database and requires both a
device ID and test-run ID. Normal Message Hub APIs remain sample-redacted.
Every exported window keeps ``training_allowed=false``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server import message_hub


EXPORT_SCHEMA_VERSION = "egolink.imu_window_export.v1"
DEFAULT_MAX_FRAMES = 1000
HARD_MAX_FRAMES = 5000


def stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def decode_samples(sample_bytes: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    record_bytes = message_hub.IMU_WINDOW_RECORD_BYTES
    if len(sample_bytes) % record_bytes != 0:
        raise ValueError("sample byte length is not divisible by record size")
    for index in range(len(sample_bytes) // record_bytes):
        record = sample_bytes[index * record_bytes : (index + 1) * record_bytes]
        offset_us = int.from_bytes(record[0:4], "little", signed=False)
        axes = [int.from_bytes(record[pos : pos + 4], "little", signed=True) for pos in range(4, 28, 4)]
        records.append(
            {
                "index": index,
                "offset_us": offset_us,
                "accel_mg": axes[:3],
                "gyro_mdps": axes[3:],
            }
        )
    return records


def load_raw_frames(
    db_path: Path,
    *,
    device_id: str,
    test_run_id: str,
    max_frames: int,
) -> tuple[list[sqlite3.Row], bool, dict[str, dict[str, Any]]]:
    if max_frames < 1 or max_frames > HARD_MAX_FRAMES:
        raise ValueError(f"max_frames must be between 1 and {HARD_MAX_FRAMES}")
    if not db_path.is_file():
        raise FileNotFoundError(f"Message Hub database does not exist: {db_path}")
    database_uri = db_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT id, frame_id, seq, raw_payload_sha256, raw_payload_b64,
                   server_received_at, record_json
            FROM raw_frames
            WHERE device_id = ? AND test_run_id = ?
            ORDER BY id
            LIMIT ?
            """,
            (device_id, test_run_id, max_frames + 1),
        ).fetchall()
        command_rows = connection.execute(
            """
            SELECT cmd_id, created_at, payload_json
            FROM commands
            WHERE device_id = ?
            ORDER BY id
            """,
            (device_id,),
        ).fetchall()
    finally:
        connection.close()
    commands: dict[str, dict[str, Any]] = {}
    for row in command_rows:
        try:
            command = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            command = {}
        if isinstance(command, dict):
            command["_db_created_at"] = str(row["created_at"])
        commands[str(row["cmd_id"])] = command if isinstance(command, dict) else {}
    return list(rows[:max_frames]), len(rows) > max_frames, commands


def raw_kv_event(
    row: sqlite3.Row,
    *,
    device_id: str,
) -> tuple[str, dict[str, str], bytes, dict[str, Any], str] | None:
    stored_b64 = str(row["raw_payload_b64"])
    raw_body = base64.b64decode(stored_b64, validate=True)
    actual_sha256 = sha256_hex(raw_body)
    if str(row["raw_payload_sha256"]).lower() != actual_sha256:
        raise ValueError("raw frame integrity metadata mismatch")
    try:
        stored_record = json.loads(str(row["record_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("raw frame record_json is invalid") from error
    stored_raw = message_hub.as_dict(stored_record.get("raw_payload"))
    stored_parse = message_hub.as_dict(stored_record.get("parse_result"))
    stored_payload_validation = message_hub.as_dict(stored_parse.get("payload_validation"))
    if stored_parse.get("status") != "ok" or stored_payload_validation.get("status") != "valid":
        raise ValueError("raw frame was not authorized and accepted at ingress")
    try:
        record_raw_body = base64.b64decode(str(stored_raw.get("data") or ""), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("raw frame record_json payload is invalid") from error
    if (
        str(stored_raw.get("sha256") or "").lower() != actual_sha256
        or type(stored_raw.get("byte_len")) is not int
        or stored_raw.get("byte_len") != len(raw_body)
        or record_raw_body != raw_body
        or stored_record.get("frame_id") != row["frame_id"]
        or stored_record.get("seq") != row["seq"]
        or stored_record.get("server_received_at") != row["server_received_at"]
    ):
        raise ValueError("raw frame record_json integrity mismatch")
    initial = message_hub.initial_raw_frame_record(device_id, raw_body, "uplink", "offline_export")
    record = message_hub.parse_raw_frame_record(initial, raw_body)
    _, payload, has_separator = message_hub.split_raw_frame_bytes(raw_body)
    if not has_separator:
        return None
    kv_payload = message_hub.parse_imu_window_kv_payload(payload)
    event_type = str(kv_payload.get("event-type") or "")
    if event_type not in {"imu_window_chunk", "imu_window_manifest"}:
        return None
    parse_result = message_hub.as_dict(record.get("parse_result"))
    if parse_result.get("status") != "ok":
        raise ValueError(
            f"retained IMU raw frame is not valid: {parse_result.get('error_code') or parse_result.get('status')}"
        )
    metadata = message_hub.validate_imu_window_wire(
        event_type,
        kv_payload,
        raw_body=raw_body,
        frame_id=str(row["frame_id"]),
        frame_seq=row["seq"],
    )
    return event_type, kv_payload, raw_body, metadata, actual_sha256


def assemble_imu_windows(
    rows: list[sqlite3.Row],
    *,
    device_id: str,
    test_run_id: str,
    commands: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, Any]] = []
    for row in rows:
        try:
            parsed = raw_kv_event(row, device_id=device_id)
        except Exception as error:  # Preserve the row reference without exposing raw bytes.
            invalid.append(
                {
                    "window_id": None,
                    "reason": "raw_frame_validation_failed",
                    "raw_frame_id": row["frame_id"],
                    "raw_frame_sha256_claimed": row["raw_payload_sha256"],
                    "detail": str(error),
                }
            )
            continue
        if parsed is None:
            continue
        event_type, kv_payload, _, metadata, actual_sha256 = parsed
        window_id = str(metadata["window_id"])
        candidate = candidates.setdefault(
            window_id,
            {
                "chunks": {},
                "manifest": None,
                "raw_frame_refs": [],
                "conflicts": [],
            },
        )
        candidate["raw_frame_refs"].append(
            {
                "frame_id": str(row["frame_id"]),
                "sha256": actual_sha256,
                "event_type": event_type,
                "chunk_index": metadata.get("chunk_index"),
                "seq": metadata["seq"],
                "server_received_at": str(row["server_received_at"]),
            }
        )
        if event_type == "imu_window_chunk":
            sample_bytes = base64.b64decode(kv_payload["samples-b64"], validate=True)
            chunk_index = int(metadata["chunk_index"])
            existing = candidate["chunks"].get(chunk_index)
            chunk = {"metadata": metadata, "sample_bytes": sample_bytes}
            if existing is None:
                candidate["chunks"][chunk_index] = chunk
            elif existing["sample_bytes"] != sample_bytes or existing["metadata"] != metadata:
                candidate["conflicts"].append(f"conflicting duplicate chunk {chunk_index}")
        else:
            existing_manifest = candidate["manifest"]
            if existing_manifest is None:
                candidate["manifest"] = metadata
            elif existing_manifest != metadata:
                candidate["conflicts"].append("conflicting duplicate manifest")

    windows: list[dict[str, Any]] = []
    for window_id in sorted(candidates):
        candidate = candidates[window_id]
        reasons = list(candidate["conflicts"])
        manifest = candidate["manifest"]
        if manifest is None:
            reasons.append("manifest missing")
        expected_indices = set(range(message_hub.IMU_WINDOW_CHUNK_COUNT))
        actual_indices = set(candidate["chunks"])
        if actual_indices != expected_indices:
            reasons.append(f"chunk set mismatch: expected {sorted(expected_indices)}, got {sorted(actual_indices)}")
        if manifest is not None:
            for chunk_index in sorted(actual_indices):
                chunk_metadata = candidate["chunks"][chunk_index]["metadata"]
                for field in (
                    "contract_version",
                    "capture_cmd_id",
                    "boot_count",
                    "fw_version",
                    "test_run_id",
                    "source",
                    "source_status",
                    "transport_type",
                ):
                    if chunk_metadata[field] != manifest[field]:
                        reasons.append(f"chunk {chunk_index} {field} lineage mismatch")
            if actual_indices == expected_indices:
                chunk_seqs = [candidate["chunks"][index]["metadata"]["seq"] for index in sorted(actual_indices)]
                if any(right <= left for left, right in zip(chunk_seqs, chunk_seqs[1:])) or manifest["seq"] <= chunk_seqs[-1]:
                    reasons.append("chunk and manifest sequence ordering invalid")
        if manifest is not None:
            command = commands.get(str(manifest["capture_cmd_id"]))
            parameters = command.get("payload") if isinstance(command, dict) else None
            if (
                not isinstance(command, dict)
                or command.get("cmd") != "capture_imu_window"
                or command.get("device_id") != device_id
                or command.get("test_run_id") != test_run_id
                or not isinstance(parameters, dict)
                or set(parameters) != {"sample_count", "interval_ms"}
                or type(parameters.get("sample_count")) is not int
                or type(parameters.get("interval_ms")) is not int
                or parameters.get("sample_count") != message_hub.IMU_WINDOW_SAMPLE_COUNT
                or parameters.get("interval_ms") != message_hub.IMU_WINDOW_INTERVAL_US // 1000
            ):
                reasons.append("authorized capture command missing or mismatched")
            else:
                try:
                    command_created_at = datetime.fromisoformat(str(command["_db_created_at"]).replace("Z", "+00:00"))
                    part_received_times = [
                        datetime.fromisoformat(str(ref["server_received_at"]).replace("Z", "+00:00"))
                        for ref in candidate["raw_frame_refs"]
                    ]
                except (KeyError, TypeError, ValueError):
                    reasons.append("capture command or raw receive timestamp invalid")
                else:
                    if any(command_created_at > received_at for received_at in part_received_times):
                        reasons.append("capture command was created after retained IMU evidence")
        if reasons:
            invalid.append({"window_id": window_id, "reason": "; ".join(reasons)})
            continue

        assert manifest is not None
        sample_bytes = b"".join(candidate["chunks"][index]["sample_bytes"] for index in sorted(actual_indices))
        if message_hub.crc32_hex(sample_bytes) != manifest["samples_crc32"]:
            invalid.append({"window_id": window_id, "reason": "window samples_crc32 mismatch"})
            continue
        samples = decode_samples(sample_bytes)
        offsets = [int(sample["offset_us"]) for sample in samples]
        if len(samples) != message_hub.IMU_WINDOW_SAMPLE_COUNT or any(
            right <= left for left, right in zip(offsets, offsets[1:])
        ):
            invalid.append({"window_id": window_id, "reason": "sample count or global offsets invalid"})
            continue
        intervals = [right - left for left, right in zip(offsets, offsets[1:])]
        capture_duration_us = manifest["capture_end_uptime_us"] - manifest["capture_start_uptime_us"]
        if offsets[0] > capture_duration_us or offsets[-1] > capture_duration_us:
            invalid.append({"window_id": window_id, "reason": "sample offsets exceed manifest capture bounds"})
            continue
        observed = {
            "min_interval_us": min(intervals),
            "mean_interval_us": sum(intervals) // len(intervals),
            "max_interval_us": max(intervals),
        }
        if any(observed[key] != manifest[key] for key in observed):
            invalid.append({"window_id": window_id, "reason": "manifest cadence statistics mismatch"})
            continue
        if manifest["test_run_id"] != test_run_id:
            invalid.append({"window_id": window_id, "reason": "test_run_id lineage mismatch"})
            continue

        cadence_qualified = (
            40_000 <= observed["min_interval_us"]
            and observed["max_interval_us"] <= 60_000
            and 45_000 <= observed["mean_interval_us"] <= 55_000
            and manifest["deadline_miss_count"] <= 5
        )
        training_blockers = [
            "operator_training_authorization_missing",
            "consent_unreviewed",
            "mounting_axis_calibration_unrecorded",
            "dataset_split_unassigned",
            "quality_review_pending",
        ]
        if not cadence_qualified:
            training_blockers.append("cadence_not_qualified")

        windows.append(
            {
                "contract_version": message_hub.IMU_WINDOW_CONTRACT_VERSION,
                "window_id": window_id,
                "capture_cmd_id": manifest["capture_cmd_id"],
                "boot_count": manifest["boot_count"],
                "device_id": device_id,
                "fw_version": manifest["fw_version"],
                "test_run_id": test_run_id,
                "source": "qmi8658_i2c",
                "source_status": "observed",
                "transport_type": "lte",
                "sensor": {
                    "model": manifest["sensor_model"],
                    "i2c_address": manifest["sensor_i2c_address"],
                    "accel_unit": manifest["accel_unit"],
                    "gyro_unit": manifest["gyro_unit"],
                },
                "capture": {
                    "sample_count": manifest["sample_count"],
                    "requested_interval_us": manifest["requested_interval_us"],
                    "capture_start_uptime_us": manifest["capture_start_uptime_us"],
                    "capture_end_uptime_us": manifest["capture_end_uptime_us"],
                    **observed,
                    "deadline_miss_count": manifest["deadline_miss_count"],
                    "read_failure_count": 0,
                    "mock_sample_count": 0,
                    "warmup_sample_count": manifest["warmup_sample_count"],
                    "warmup_interval_us": manifest["warmup_interval_us"],
                    "cadence_quality_status": "qualified" if cadence_qualified else "needs_review",
                },
                "mounting_profile_id": "unrecorded",
                "axis_mapping_status": "unrecorded",
                "calibration_profile_id": "unrecorded",
                "activity_label": "unknown",
                "label_source": "none",
                "collection_authorization": "operator_command",
                "training_allowed": False,
                "privacy_class": "engineering",
                "consent_status": "unreviewed_required",
                "consent_evidence_ref": None,
                "redaction_state": "raw_imu_explicit_local_export",
                "retention_policy_status": "unrecorded",
                "deletion_status": "unrecorded",
                "split_name": "unassigned",
                "split_leakage_checked": False,
                "training_blockers": training_blockers,
                "command_ref": {
                    "cmd_id": manifest["capture_cmd_id"],
                    "test_run_id": test_run_id,
                    "sample_count": message_hub.IMU_WINDOW_SAMPLE_COUNT,
                    "interval_ms": message_hub.IMU_WINDOW_INTERVAL_US // 1000,
                },
                "raw_frame_refs": candidate["raw_frame_refs"],
                "server_received_at_first": candidate["raw_frame_refs"][0]["server_received_at"],
                "server_received_at_last": candidate["raw_frame_refs"][-1]["server_received_at"],
                "capture_time_basis": "device_monotonic_uptime_only",
                "samples_sha256": sha256_hex(sample_bytes),
                "samples": samples,
            }
        )
    return windows, invalid


def export_imu_windows(
    db_path: Path,
    output_dir: Path,
    *,
    device_id: str,
    test_run_id: str,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> dict[str, Any]:
    rows, truncated, commands = load_raw_frames(
        db_path,
        device_id=device_id,
        test_run_id=test_run_id,
        max_frames=max_frames,
    )
    windows, invalid = assemble_imu_windows(
        rows,
        device_id=device_id,
        test_run_id=test_run_id,
        commands=commands,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_bytes = b"".join((stable_json(window) + "\n").encode("utf-8") for window in windows)
    jsonl_path = output_dir / "imu_windows.jsonl"
    jsonl_path.write_bytes(jsonl_bytes)
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "selectors": {
            "database_name": db_path.name,
            "device_id": device_id,
            "test_run_id": test_run_id,
            "max_frames": max_frames,
        },
        "privacy": {
            "explicit_local_export": True,
            "normal_api_sample_export": False,
            "training_allowed": False,
            "privacy_class": "engineering",
            "consent_status": "unreviewed_required",
            "redaction_state": "raw_imu_explicit_local_export",
            "retention_policy_status": "unrecorded",
            "deletion_status": "unrecorded",
            "split_name": "unassigned",
            "split_leakage_checked": False,
            "training_blockers": [
                "operator_training_authorization_missing",
                "consent_unreviewed",
                "mounting_axis_calibration_unrecorded",
                "dataset_split_unassigned",
                "quality_review_pending",
            ],
        },
        "summary": {
            "raw_frames_scanned": len(rows),
            "truncated": truncated,
            "valid_windows": len(windows),
            "invalid_windows": len(invalid),
            "cadence_qualified_windows": sum(
                1 for window in windows if window["capture"]["cadence_quality_status"] == "qualified"
            ),
        },
        "invalid": invalid,
        "outputs": {
            "imu_windows_jsonl": jsonl_path.name,
            "imu_windows_jsonl_sha256": sha256_hex(jsonl_bytes),
        },
    }
    manifest_path = output_dir / "imu_window_export_manifest.json"
    manifest["outputs"]["manifest"] = manifest_path.name
    manifest["ok"] = bool(windows) and not invalid and not truncated
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Explicit Message Hub SQLite database")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = export_imu_windows(
        args.db,
        args.output_dir,
        device_id=args.device_id,
        test_run_id=args.test_run_id,
        max_frames=args.max_frames,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
