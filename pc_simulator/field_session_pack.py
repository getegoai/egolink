"""Pack one explicitly named four-source field capture into A0-003 v0.1.

This is a deliberately narrow adapter for FIELD-AI-001.  It consumes four
immutable local inputs and never fetches runtime state, changes firmware, or
upgrades an evidence Gate.  Missing source clocks remain receive-only or
estimated with explicit uncertainty.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sys
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from pc_simulator import field_session
from pc_simulator import sensor_time_lineage as time_lineage
from pc_simulator.imu_six_face_calibration import (
    ARTIFACT_SCHEMA_PATH as CALIBRATION_SCHEMA_PATH,
    ARTIFACT_SCHEMA_VERSION as CALIBRATION_CONTRACT_VERSION,
    MDPS_TO_RAD_S,
    MG_TO_M_S2,
    artifact_payload_sha256,
    encode_source_samples,
)


PACKER_VERSION = "egolink.field_session_pack.v0.1"
CAMERA_INDEX_VERSION = "egolink.camera_sidecar_index.v0.1"
MESSAGE_HUB_GNSS_VERSION = "egolink.message_hub_gnss_stream.v0.1"
MESSAGE_HUB_LTE_VERSION = "egolink.message_hub_lte_stream.v0.1"
SIDECAR_VERSION = "egolink.field_sidecar_bundle.v0.1"
REQUIRED_EVENTS = {
    "START_WALKING",
    "PUT_IN_BAG",
    "ENTER_BUILDING",
    "EXIT_BUILDING",
    "STOP",
}
REQUIRED_EVENT_SEQUENCE = (
    "START_WALKING",
    "PUT_IN_BAG",
    "ENTER_BUILDING",
    "EXIT_BUILDING",
    "STOP",
)
HEX40_OR_64 = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UPTIME_MS = re.compile(r"^uptime_ms:(?P<value>[0-9]+)$")
JPEG_PREFIX = b"\xff\xd8"
JPEG_SUFFIX = b"\xff\xd9"


class FieldSessionPackError(ValueError):
    """An explicit packer input is absent, inconsistent, or unverifiable."""


def _fail(message: str) -> None:
    raise FieldSessionPackError(message)


def _require_file(path: Path, name: str) -> bytes:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FieldSessionPackError(f"{name} is unavailable: {path}: {error}") from error
    if not resolved.is_file():
        _fail(f"{name} must be a regular file: {path}")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise FieldSessionPackError(f"cannot read {name}: {path}: {error}") from error
    if not payload:
        _fail(f"{name} must not be empty: {path}")
    return payload


def _load_json_bytes(payload: bytes, name: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FieldSessionPackError(f"{name} must be UTF-8 JSON: {error}") from error
    try:
        value = json.loads(
            text,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise FieldSessionPackError(f"{name} is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        _fail(f"{name} must contain one JSON object")
    return value


def _load_jsonl_bytes(payload: bytes, name: str) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise FieldSessionPackError(f"{name} must be UTF-8 JSONL: {error}") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {item}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise FieldSessionPackError(
                f"{name} line {line_number} is invalid JSON: {error}"
            ) from error
        if not isinstance(row, dict):
            _fail(f"{name} line {line_number} must contain one JSON object")
        rows.append(row)
    if not rows:
        _fail(f"{name} must contain at least one JSONL record")
    return rows


def _utc_ns(value: Any, name: str) -> int:
    try:
        return time_lineage.parse_utc_ns(value, name)
    except time_lineage.SensorTimeLineageError as error:
        raise FieldSessionPackError(str(error)) from error


def _utc_text(value_ns: int) -> str:
    return time_lineage.format_utc_ns(value_ns)


def _require_safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        _fail(f"{name} must match {SAFE_ID.pattern}")
    return value


def _require_commit(value: str, name: str) -> str:
    normalized = str(value).lower()
    if HEX40_OR_64.fullmatch(normalized) is None:
        _fail(f"{name} must be a lowercase 40- or 64-character Git hash")
    return normalized


def _require_sha256(value: str, name: str) -> str:
    normalized = str(value).lower()
    if HEX64.fullmatch(normalized) is None:
        _fail(f"{name} must be a lowercase SHA-256")
    return normalized


def _stable_jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(field_session.stable_json_bytes(row) + b"\n" for row in rows)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n")


def _artifact(
    root: Path,
    *,
    artifact_id: str,
    relative_path: str,
    role: str,
    format_name: str,
    media_type: str,
    contract: str | None,
    privacy_class: str,
    record_count: int | None,
) -> dict[str, Any]:
    _require_safe_id(artifact_id, "artifact_id")
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    return {
        "artifact_id": artifact_id,
        "path": relative_path,
        "role": role,
        "format": format_name,
        "sha256": field_session.sha256_file(path),
        "size_bytes": path.stat().st_size,
        "record_count": record_count,
        "media_type": media_type,
        "content_contract_version": contract,
        "privacy_class": privacy_class,
        "part_group": None,
        "part_index": None,
        "part_count": None,
    }


def _schema_validate(value: Any, schema_path: Path, name: str) -> None:
    schema = field_session.load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path)
        _fail(f"{name}{'.' + location if location else ''}: {error.message}")


def _validate_calibration(
    artifact: dict[str, Any],
    *,
    firmware_commit: str,
    firmware_image_sha256: str,
) -> None:
    _schema_validate(artifact, CALIBRATION_SCHEMA_PATH, "calibration artifact")
    try:
        expected_identity = field_session._imu_calibration_identity_sha256(artifact)
        expected_payload = artifact_payload_sha256(copy.deepcopy(artifact))
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise FieldSessionPackError(f"calibration artifact cannot be verified: {error}") from error
    if artifact["identity_sha256"].lower() != expected_identity:
        _fail("calibration identity_sha256 does not match its canonical identity")
    if artifact["calibration_id"] != f"imucal-{expected_identity[:24]}":
        _fail("calibration_id does not derive from identity_sha256")
    if artifact["payload_sha256"].lower() != expected_payload:
        _fail("calibration payload_sha256 does not match its canonical payload")
    if artifact["firmware"]["firmware_commit"].lower() != firmware_commit:
        _fail("CLI firmware commit conflicts with the calibration artifact")
    if artifact["firmware"]["firmware_image_sha256"].lower() != firmware_image_sha256:
        _fail("CLI firmware image SHA-256 conflicts with the calibration artifact")
    if artifact["sensor"]["uncalibrated_accel_unit"] != "mg" or artifact["sensor"]["uncalibrated_gyro_unit"] != "mdps":
        _fail("calibration artifact engineering units must be mg/mdps")
    for name, values in (
        ("accelerometer.bias_mg_xyz", artifact["accelerometer"]["bias_mg_xyz"]),
        ("accelerometer.correction_gain_xyz", artifact["accelerometer"]["correction_gain_xyz"]),
        ("gyroscope.bias_mdps_xyz", artifact["gyroscope"]["bias_mdps_xyz"]),
    ):
        if len(values) != 3 or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values):
            _fail(f"calibration {name} must contain three finite axis values")


def _commit_values(value: Any, keys: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item.strip():
                found.add(item.lower())
            elif isinstance(item, (Mapping, list)):
                found.update(_commit_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.update(_commit_values(item, keys))
    return found


def _check_input_provenance(
    value: Any,
    *,
    name: str,
    firmware_commit: str,
    firmware_image_sha256: str,
    repository_commit: str,
) -> None:
    firmware_commits = _commit_values(value, {"firmware_commit"})
    image_hashes = _commit_values(value, {"firmware_image_sha256", "image_sha256"})
    repository_commits = _commit_values(value, {"repository_commit", "repo_commit"})
    if firmware_commits and firmware_commits != {firmware_commit}:
        _fail(f"{name} firmware_commit conflicts with the CLI provenance: {sorted(firmware_commits)}")
    if image_hashes and image_hashes != {firmware_image_sha256}:
        _fail(f"{name} firmware image hash conflicts with the CLI provenance: {sorted(image_hashes)}")
    if repository_commits and repository_commits != {repository_commit}:
        _fail(f"{name} repository_commit conflicts with the CLI provenance: {sorted(repository_commits)}")


def _validate_field_export(value: dict[str, Any]) -> tuple[str, int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    window = value.get("window")
    messages = value.get("messages")
    commands = value.get("commands")
    raw_frames = value.get("raw_frames")
    if not isinstance(window, Mapping) or not isinstance(messages, list) or not messages:
        _fail("Message Hub field export requires a non-empty messages array and window object")
    if not isinstance(commands, list) or not isinstance(raw_frames, list):
        _fail("Message Hub field export commands/messages/raw_frames must all be arrays")
    device_id = _require_safe_id(window.get("device_id"), "field export window.device_id")
    start_ns = _utc_ns(window.get("started_at"), "field export window.started_at")
    end_ns = _utc_ns(window.get("ended_at"), "field export window.ended_at")
    if end_ns <= start_ns:
        _fail("field export window must have positive duration")
    if window.get("complete") is not True:
        _fail("field export window must be complete")
    truncated = window.get("truncated")
    collection_names = {"messages", "commands", "raw_frames"}
    if (
        not isinstance(truncated, Mapping)
        or set(truncated) != collection_names
        or any(truncated[name] is not False for name in collection_names)
    ):
        _fail("field export truncated must contain exactly commands/messages/raw_frames=false")
    returned = window.get("returned")
    expected_counts = {
        "messages": len(messages),
        "commands": len(commands),
        "raw_frames": len(raw_frames),
    }
    if (
        not isinstance(returned, Mapping)
        or set(returned) != collection_names
        or any(isinstance(returned[name], bool) or not isinstance(returned[name], int) for name in collection_names)
        or dict(returned) != expected_counts
    ):
        _fail("field export returned counts must exactly match commands/messages/raw_frames")

    gnss: list[dict[str, Any]] = []
    lte: list[dict[str, Any]] = []
    for index, row in enumerate(messages):
        if not isinstance(row, dict):
            _fail(f"field export messages[{index}] must be an object")
        event_type = row.get("event_type")
        if event_type not in {"location_report", "location_observation"}:
            continue
        if row.get("message_type") != "event":
            _fail(f"field export messages[{index}] has a location event with unknown message_type")
        if row.get("device_id") != device_id:
            _fail(f"field export messages[{index}] device_id conflicts with window.device_id")
        sequence = row.get("seq")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            _fail(f"field export messages[{index}].seq must be a non-negative integer")
        receive_ns = _utc_ns(row.get("server_received_at"), f"field export messages[{index}].server_received_at")
        if receive_ns < start_ns or receive_ns > end_ns:
            _fail(f"field export messages[{index}] falls outside its declared window")
        encoded = json.dumps(row, ensure_ascii=False).lower()
        if '"mock"' in encoded and any(
            row.get(key) is True or str(row.get(key, "")).lower().startswith("mock")
            for key in ("mock", "is_mock", "source_status", "gnss_state")
        ):
            _fail(f"field export messages[{index}] is mock evidence")
        (gnss if event_type == "location_report" else lte).append(row)
    if not gnss:
        _fail("field export contains no GNSS location_report observations")
    if not lte:
        _fail("field export contains no LTE location_observation observations")
    for source, rows in (("GNSS", gnss), ("LTE", lte)):
        sequences = [row["seq"] for row in rows]
        if len(set(sequences)) != len(sequences) or any(right <= left for left, right in zip(sequences, sequences[1:])):
            _fail(f"{source} sequence IDs must be unique and increase in field-export order")
    return device_id, start_ns, end_ns, gnss, lte


def _field_boot_count(field_export: Mapping[str, Any], imu_rows: list[dict[str, Any]]) -> int:
    imu_boots = {row.get("boot_count") for row in imu_rows}
    if len(imu_boots) != 1 or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in imu_boots):
        _fail("IMU windows must belong to exactly one non-negative boot_count")
    boot = next(iter(imu_boots))
    observed_boots: set[int] = set()
    for index, row in enumerate(field_export.get("messages", [])):
        if not isinstance(row, Mapping) or "boot_count" not in row:
            continue
        observed_boot = row["boot_count"]
        if isinstance(observed_boot, bool) or not isinstance(observed_boot, int) or observed_boot < 0:
            _fail(f"field export messages[{index}].boot_count must be a non-negative integer")
        observed_boots.add(observed_boot)
    if not observed_boots:
        _fail("field export contains no explicit boot_count evidence for this capture window")
    if observed_boots != {boot}:
        _fail(f"field export boot_count conflicts with IMU windows: {sorted(observed_boots)} vs {boot}")
    return boot


def _validate_imu_rows(
    rows: list[dict[str, Any]],
    *,
    calibration: Mapping[str, Any],
    device_id: str,
    boot_count: int,
    start_ns: int,
    end_ns: int,
) -> None:
    window_ids: set[str] = set()
    test_run_ids: set[str] = set()
    for index, row in enumerate(rows):
        if row.get("contract_version") != "egolink.imu_window.v1":
            _fail(f"IMU row {index} has an unknown contract/type")
        if row.get("device_id") != device_id or row.get("boot_count") != boot_count:
            _fail(f"IMU row {index} device/boot conflicts with the Field Session")
        if row.get("fw_version") != calibration["firmware"]["fw_version"]:
            _fail(f"IMU row {index} firmware version conflicts with the calibration artifact")
        if row.get("source") != "qmi8658_i2c" or row.get("source_status") != "observed":
            _fail(f"IMU row {index} is not observed QMI8658 evidence")
        sensor = row.get("sensor")
        if not isinstance(sensor, Mapping) or (
            sensor.get("model") != calibration["sensor"]["imu_model"]
            or sensor.get("i2c_address") != calibration["sensor"]["sensor_i2c_address"]
            or sensor.get("accel_unit") != "mg"
            or sensor.get("gyro_unit") != "mdps"
        ):
            _fail(f"IMU row {index} model/address/units conflict with the calibration artifact")
        window_id = _require_safe_id(row.get("window_id"), f"IMU row {index}.window_id")
        _require_safe_id(row.get("capture_cmd_id"), f"IMU row {index}.capture_cmd_id")
        if row.get("transport_type") not in {"lte", "wifi"}:
            _fail(f"IMU row {index}.transport_type must be lte or wifi")
        if row.get("capture_time_basis") != "device_monotonic_uptime_only":
            _fail(f"IMU row {index}.capture_time_basis must be device_monotonic_uptime_only")
        if window_id in window_ids:
            _fail(f"duplicate IMU window_id: {window_id}")
        window_ids.add(window_id)
        test_run_ids.add(_require_safe_id(row.get("test_run_id"), f"IMU row {index}.test_run_id"))
        capture = row.get("capture")
        samples = row.get("samples")
        if not isinstance(capture, Mapping) or not isinstance(samples, list) or len(samples) != 100:
            _fail(f"IMU row {index} must preserve exactly 100 samples")
        if capture.get("sample_count") != len(samples) or capture.get("requested_interval_us") != 50_000:
            _fail(f"IMU row {index} sample count/rate conflicts with imu_window.v1")
        capture_start = capture.get("capture_start_uptime_us")
        capture_end = capture.get("capture_end_uptime_us")
        if (
            isinstance(capture_start, bool)
            or not isinstance(capture_start, int)
            or capture_start < 0
            or isinstance(capture_end, bool)
            or not isinstance(capture_end, int)
            or capture_end <= capture_start
        ):
            _fail(f"IMU row {index} capture uptime bounds are invalid")
        try:
            digest = hashlib.sha256(encode_source_samples(samples, window_id=window_id)).hexdigest()
        except Exception as error:
            raise FieldSessionPackError(f"IMU row {index} samples are invalid: {error}") from error
        if digest != str(row.get("samples_sha256", "")).lower():
            _fail(f"IMU row {index} samples_sha256 mismatch")
        first_ns = _utc_ns(row.get("server_received_at_first"), f"IMU row {index}.server_received_at_first")
        last_ns = _utc_ns(row.get("server_received_at_last"), f"IMU row {index}.server_received_at_last")
        if not (start_ns <= first_ns <= last_ns <= end_ns):
            _fail(f"IMU row {index} server receive interval falls outside the field export")
    if len(test_run_ids) != 1:
        _fail("IMU windows must come from exactly one test_run_id")


def _validate_sidecar(
    bundle: dict[str, Any],
    *,
    start_ns: int,
    end_ns: int,
) -> tuple[str, str, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes]]:
    if bundle.get("format_version") != SIDECAR_VERSION or bundle.get("bundle_role") != "a0_003_adapter_input":
        _fail("sidecar bundle has an unknown format/type")
    if bundle.get("gate_status") != "unverified" or bundle.get("status") != "stopped":
        _fail("sidecar bundle must be stopped and must retain gate_status=unverified")
    session = bundle.get("session")
    producer = bundle.get("producer")
    clock = bundle.get("clock")
    privacy = bundle.get("privacy")
    records = bundle.get("records")
    media = bundle.get("media")
    if not all(isinstance(item, Mapping) for item in (session, producer, clock, privacy)):
        _fail("sidecar bundle is missing session/producer/clock/privacy objects")
    if not isinstance(records, list) or not records or not isinstance(media, list) or not media:
        _fail("sidecar bundle must contain non-empty records and media")
    session_id = _require_safe_id(session.get("session_id"), "sidecar session_id")
    if re.fullmatch(r"FS-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", session_id) is None:
        _fail("sidecar session_id is not an egolink Field Session ID")
    operator_ref = _require_safe_id(session.get("operator_ref"), "sidecar operator_ref")
    sidecar_start = _utc_ns(session.get("capture_start_utc"), "sidecar capture_start_utc")
    sidecar_end = _utc_ns(session.get("capture_end_utc"), "sidecar capture_end_utc")
    if not (start_ns <= sidecar_start < sidecar_end <= end_ns):
        _fail("sidecar capture interval must be contained in the Message Hub field window")
    phone_id = _require_safe_id(producer.get("device_id"), "sidecar producer.device_id")
    producer_run_id = _require_safe_id(producer.get("device_run_id"), "sidecar producer.device_run_id")
    clock_domain = _require_safe_id(producer.get("clock_domain_id"), "sidecar producer.clock_domain_id")
    if producer.get("source") != "test_phone" or producer.get("clock_kind") != "browser_performance":
        _fail("sidecar producer has an unknown source or clock type")
    if producer_run_id != f"{session_id}:sidecar:0":
        _fail("sidecar producer.device_run_id does not derive from session_id")
    if clock.get("alignment_status") != "estimated_unverified" or clock.get("discontinuity") is not None:
        _fail("sidecar clock must be continuous and estimated_unverified")
    samples = clock.get("samples")
    if not isinstance(samples, list) or not samples:
        _fail("sidecar clock samples are missing")
    sample_ids: set[str] = set()
    sample_by_id: dict[str, Mapping[str, Any]] = {}
    prior_index = -1
    prior_mono = -1
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            _fail(f"sidecar clock.samples[{index}] must be an object")
        sample_id = _require_safe_id(sample.get("sample_id"), f"sidecar clock.samples[{index}].sample_id")
        sample_index = sample.get("sample_index")
        monotonic = sample.get("timestamp_monotonic_ns")
        pairing = sample.get("pairing_span_ns")
        if sample_id in sample_ids or sample_index != prior_index + 1:
            _fail("sidecar clock sample IDs/indexes must be unique and contiguous")
        if isinstance(monotonic, bool) or not isinstance(monotonic, int) or monotonic <= prior_mono:
            _fail("sidecar clock monotonic timestamps must strictly increase")
        if isinstance(pairing, bool) or not isinstance(pairing, int) or pairing < 0:
            _fail("sidecar clock pairing_span_ns must be non-negative")
        _utc_ns(sample.get("timestamp_utc"), f"sidecar clock.samples[{index}].timestamp_utc")
        if sample.get("alignment_status") != "estimated_unverified":
            _fail("sidecar clock sample makes an unsupported alignment claim")
        sample_ids.add(sample_id)
        sample_by_id[sample_id] = sample
        prior_index = sample_index
        prior_mono = monotonic
    if clock.get("first_sample_id") != samples[0]["sample_id"] or clock.get("last_sample_id") != samples[-1]["sample_id"]:
        _fail("sidecar first/last clock sample IDs do not match the samples")
    consent = privacy.get("consent_acknowledgement")
    retention = privacy.get("retention_acknowledgement")
    if (
        privacy.get("local_only") is not True
        or privacy.get("network_upload") is not False
        or privacy.get("raw_image_allowed") is not True
        or privacy.get("raw_image_capture_acknowledged") is not True
        or privacy.get("training_allowed") is not False
        or privacy.get("control_plane_approval") is not False
        or privacy.get("gate_approval") is not False
        or not isinstance(consent, Mapping)
        or not isinstance(retention, Mapping)
        or consent.get("acknowledged") is not True
        or retention.get("acknowledged") is not True
        or consent.get("operator_ref") != operator_ref
        or retention.get("operator_ref") != operator_ref
        or retention.get("status") != "post_experiment_review_required"
    ):
        _fail("sidecar raw JPEG privacy/consent/retention acknowledgement is incomplete")
    _utc_ns(consent.get("acknowledged_at_utc"), "sidecar consent acknowledged_at_utc")
    _utc_ns(retention.get("acknowledged_at_utc"), "sidecar retention acknowledged_at_utc")

    media_by_path: dict[str, Mapping[str, Any]] = {}
    decoded_media: dict[str, bytes] = {}
    for index, item in enumerate(media):
        if not isinstance(item, Mapping) or item.get("media_type") != "image/jpeg":
            _fail(f"sidecar media[{index}] has an unknown type")
        relative = item.get("path")
        if not isinstance(relative, str):
            _fail(f"sidecar media[{index}].path is missing")
        pure = PurePosixPath(relative)
        if (
            "\\" in relative
            or ":" in relative
            or pure.is_absolute()
            or len(pure.parts) != 2
            or pure.parts[0] != "camera"
            or pure.suffix.lower() != ".jpg"
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            _fail(f"sidecar media[{index}].path is unsafe")
        if relative in media_by_path:
            _fail(f"duplicate sidecar media path: {relative}")
        try:
            decoded = base64.b64decode(item.get("data_base64"), validate=True)
        except (TypeError, ValueError, binascii.Error) as error:
            raise FieldSessionPackError(f"sidecar media[{index}] has invalid base64: {error}") from error
        if len(decoded) != item.get("size_bytes"):
            _fail(f"sidecar media[{index}] decoded size mismatch")
        digest = hashlib.sha256(decoded).hexdigest()
        if digest != str(item.get("sha256", "")).lower():
            _fail(f"sidecar media[{index}] SHA-256 mismatch")
        if len(decoded) < 4 or not decoded.startswith(JPEG_PREFIX) or not decoded.endswith(JPEG_SUFFIX):
            _fail(f"sidecar media[{index}] is not a complete JPEG byte stream")
        media_by_path[relative] = item
        decoded_media[relative] = decoded

    manual_rows: list[dict[str, Any]] = []
    camera_rows: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    seen_media: set[str] = set()
    observed_events: list[str] = []
    prior_sequence = -1
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            _fail(f"sidecar records[{index}] must be an object")
        record_type = record.get("record_type")
        if record_type not in {"manual_event", "camera"}:
            _fail(f"sidecar records[{index}] has unknown record_type {record_type!r}")
        sequence = record.get("sequence_id")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0 or sequence in seen_sequences or sequence <= prior_sequence:
            _fail("sidecar record sequence IDs must be unique and strictly increasing")
        monotonic = record.get("timestamp_monotonic_ns")
        if isinstance(monotonic, bool) or not isinstance(monotonic, int) or monotonic < 0:
            _fail(f"sidecar records[{index}] has invalid monotonic time")
        record_utc = _utc_ns(record.get("timestamp_utc"), f"sidecar records[{index}].timestamp_utc")
        if not (sidecar_start <= record_utc <= sidecar_end):
            _fail(f"sidecar records[{index}] falls outside the sidecar capture interval")
        clock_sample_id = record.get("clock_sample_id")
        if record.get("clock_domain_id") != clock_domain or clock_sample_id not in sample_ids or record.get("alignment_status") != "estimated_unverified":
            _fail(f"sidecar records[{index}] clock lineage is inconsistent")
        sample = sample_by_id[str(clock_sample_id)]
        expected_sample_type = "manual_event" if record_type == "manual_event" else "camera_capture_return"
        if (
            record["timestamp_monotonic_ns"] != sample["timestamp_monotonic_ns"]
            or record_utc != _utc_ns(sample["timestamp_utc"], f"sidecar clock sample {clock_sample_id}.timestamp_utc")
            or sample.get("sample_type") != expected_sample_type
        ):
            _fail(f"sidecar records[{index}] does not exactly match its clock sample")
        if (
            isinstance(record.get("timestamp_uncertainty_ns"), bool)
            or not isinstance(record.get("timestamp_uncertainty_ns"), int)
            or record["timestamp_uncertainty_ns"] < sample["pairing_span_ns"]
        ):
            _fail(f"sidecar records[{index}] timestamp uncertainty is invalid")
        if record_type == "manual_event":
            if record.get("source") != "manual_event" or record.get("event_type") not in REQUIRED_EVENTS:
                _fail(f"sidecar records[{index}] has an unsupported manual event")
            _require_safe_id(record.get("event_id"), f"sidecar records[{index}].event_id")
            if record["event_id"] != f"{session_id}:event:{sequence:06d}":
                _fail(f"sidecar records[{index}] event_id does not derive from session/sequence")
            if record.get("operator_ref") != operator_ref or record.get("capture_method") != "test_phone" or record.get("label_semantics") != "weak_operator_event":
                _fail(f"sidecar records[{index}] manual-event identity/provenance is inconsistent")
            observed_events.append(record["event_type"])
            manual_rows.append(record)
        else:
            if record.get("source") != "camera" or record.get("timestamp_semantics") != "capture_return":
                _fail(f"sidecar records[{index}] has unsupported Camera semantics")
            _require_safe_id(record.get("observation_id"), f"sidecar records[{index}].observation_id")
            if record["observation_id"] != f"{session_id}:camera:{sequence:06d}" or record.get("capture_method") != "test_phone":
                _fail(f"sidecar records[{index}] Camera identity/provenance is inconsistent")
            media_path = record.get("media_path")
            item = media_by_path.get(media_path)
            if item is None or media_path in seen_media:
                _fail(f"sidecar Camera record {index} does not map one-to-one to media")
            if record.get("media_sha256") != item.get("sha256") or record.get("media_size_bytes") != item.get("size_bytes"):
                _fail(f"sidecar Camera record {index} conflicts with its media index")
            seen_media.add(media_path)
            camera_rows.append(record)
        seen_sequences.add(sequence)
        prior_sequence = sequence
    if tuple(observed_events) != REQUIRED_EVENT_SEQUENCE:
        _fail(
            "sidecar manual events must occur exactly once in order: "
            + ",".join(REQUIRED_EVENT_SEQUENCE)
        )
    if set(media_by_path) != seen_media:
        _fail("sidecar media and Camera records are not an exact one-to-one set")
    return session_id, operator_ref, phone_id, manual_rows, camera_rows, decoded_media


def _parse_uptime_ms(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = UPTIME_MS.fullmatch(value)
    if match is None:
        return None
    return int(match.group("value"))


def _gnss_source_utc(message: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for path in (
        ("gnss_timestamp_utc",),
        ("source_timestamp_utc",),
        ("payload", "gnss", "timestamp_utc"),
    ):
        value: Any = message
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if isinstance(value, str):
            try:
                return _utc_text(_utc_ns(value, ".".join(path))), "message." + ".".join(path)
            except FieldSessionPackError:
                _fail(f"GNSS source UTC field {'.'.join(path)} is malformed")
    date_value = message.get("utc_date")
    time_value = message.get("utc_time")
    if date_value in {None, ""} and time_value in {None, ""}:
        return None, None
    date_digits = re.sub(r"[^0-9]", "", str(date_value))
    match = re.fullmatch(r"(?P<hour>[0-9]{2})(?P<minute>[0-9]{2})(?P<second>[0-9]{2})(?:[.](?P<fraction>[0-9]{1,6}))?", str(time_value))
    if match is None:
        _fail("GNSS utc_time is malformed")
    if len(date_digits) == 6:
        day, month, year = int(date_digits[:2]), int(date_digits[2:4]), 2000 + int(date_digits[4:])
    elif len(date_digits) == 8:
        year, month, day = int(date_digits[:4]), int(date_digits[4:6]), int(date_digits[6:])
    else:
        _fail("GNSS utc_date must be DDMMYY or YYYYMMDD")
    microsecond = int((match.group("fraction") or "").ljust(6, "0"))
    try:
        instant = datetime(
            year,
            month,
            day,
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            microsecond,
            tzinfo=timezone.utc,
        )
    except ValueError as error:
        raise FieldSessionPackError(f"GNSS source UTC is invalid: {error}") from error
    return instant.isoformat().replace("+00:00", "Z"), "message.utc_date+utc_time"


def _mapping(
    *,
    mapping_id: str,
    device_id: str,
    clock_domain_id: str,
    boot_count: int,
    anchors: list[dict[str, Any]],
    uncertainty_floor_ns: int,
    anchor_method: str,
    session_id: str,
    firmware_commit: str,
    created_at: str,
) -> dict[str, Any]:
    if not anchors:
        _fail(f"estimated mapping {mapping_id} requires at least one complete anchor")
    ordered = sorted(anchors, key=lambda item: item["timestamp_monotonic_ns"])
    if len({item["timestamp_monotonic_ns"] for item in ordered}) != len(ordered):
        _fail(f"estimated mapping {mapping_id} has duplicate monotonic anchors")
    origin_mono = ordered[0]["timestamp_monotonic_ns"]
    origin_utc = ordered[0]["timestamp_utc"]
    origin_utc_ns = _utc_ns(origin_utc, f"{mapping_id}.utc_origin")
    residuals = [
        abs(
            _utc_ns(anchor["timestamp_utc"], f"{mapping_id}.{anchor['anchor_id']}")
            - (origin_utc_ns + anchor["timestamp_monotonic_ns"] - origin_mono)
        )
        for anchor in ordered
    ]
    fit_max = max(residuals)
    fit_rms = math.sqrt(sum(item * item for item in residuals) / len(residuals))
    uncertainty = max(
        uncertainty_floor_ns,
        fit_max,
        *(int(anchor["uncertainty_ns"]) for anchor in ordered),
    )
    return {
        "contract_version": time_lineage.CLOCK_MAPPING_VERSION,
        "mapping_id": mapping_id,
        "device_id": device_id,
        "monotonic_clock_domain_id": clock_domain_id,
        "boot_count": boot_count,
        "monotonic_origin_ns": origin_mono,
        "utc_origin": origin_utc,
        "utc_rate_correction_ppm": 0,
        "valid_from_monotonic_ns": ordered[0]["timestamp_monotonic_ns"],
        "valid_through_monotonic_ns": ordered[-1]["timestamp_monotonic_ns"],
        "anchor_method": anchor_method,
        "anchors": ordered,
        "anchor_count": len(ordered),
        "fit_rms_error_ns": fit_rms,
        "fit_max_error_ns": fit_max,
        "uncertainty_ns": uncertainty,
        "status": "estimated",
        "created_at": created_at,
        "lineage": {
            "evidence_scope": "field_session",
            "source_status": "observed",
            "field_session_id": session_id,
            "firmware_commit": firmware_commit,
        },
    }


def _time_record(
    *,
    observation_id: str,
    device_id: str,
    source: str,
    stream_id: str,
    sequence_id: int,
    clock_domain_id: str | None,
    boot_count: int | None,
    timestamp_monotonic_ns: int | None,
    timestamp_utc: str | None,
    source_timestamp: dict[str, Any],
    receive_timestamp_utc: str | None,
    ingest_timestamp_utc: str | None,
    alignment_status: str,
    monotonic_origin: str,
    monotonic_source_field: str | None,
    utc_origin: str,
    mapping_id: str | None,
    uncertainty_ns: int | None,
    reason_codes: list[str],
    session_id: str,
    test_run_id: str | None,
    firmware_version: str | None,
    firmware_commit: str | None,
    source_artifact: Mapping[str, Any],
    imu_derivation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": time_lineage.TIME_LINEAGE_VERSION,
        "observation_id": observation_id,
        "device_id": device_id,
        "source": source,
        "stream_id": stream_id,
        "sequence_id": sequence_id,
        "monotonic_clock_domain_id": clock_domain_id,
        "boot_count": boot_count,
        "timestamp_monotonic_ns": timestamp_monotonic_ns,
        "timestamp_utc": timestamp_utc,
        "source_timestamp": source_timestamp,
        "receive_timestamp_utc": receive_timestamp_utc,
        "ingest_timestamp_utc": ingest_timestamp_utc,
        "alignment": {
            "status": alignment_status,
            "timestamp_monotonic_origin": monotonic_origin,
            "monotonic_source_field": monotonic_source_field,
            "timestamp_utc_origin": utc_origin,
            "mapping_id": mapping_id,
            "anchor": None,
            "uncertainty_ns": uncertainty_ns,
            "reason_codes": reason_codes,
        },
        "lineage": {
            "evidence_scope": "field_session",
            "source_status": "observed",
            "field_session_id": session_id,
            "test_run_id": test_run_id,
            "firmware_version": firmware_version,
            "firmware_commit": firmware_commit,
            "source_record_ref": source_artifact["path"],
            "source_record_sha256": source_artifact["sha256"],
        },
        "imu_sample_derivation": imu_derivation,
    }


def _set_stream(
    manifest: dict[str, Any],
    *,
    stream_id: str,
    source: str,
    artifact: Mapping[str, Any],
    contract: str,
    observation_count: int,
    bounds: Mapping[str, Any],
    device_run_id: str,
    clock_domain_id: str | None,
    variant: str = "normalized_observation",
) -> dict[str, Any]:
    stream = next(item for item in manifest["streams"] if item["source"] == source)
    stream.update(
        {
            "stream_id": stream_id,
            "variant": variant,
            "status": "captured",
            "format": "jsonl",
            "record_contract_version": contract,
            "artifact_id": artifact["artifact_id"],
            "observation_count": observation_count,
            "device_run_id": device_run_id,
            "clock_domain_id": clock_domain_id,
            "bounds": dict(bounds),
            "raw_preserved": True,
            "calibration_id": None,
            "source_stream_id": None,
            "generator": None,
            "reason_codes": [],
        }
    )
    return stream


def _unrequested_streams(manifest: dict[str, Any]) -> None:
    for stream in manifest["streams"]:
        if stream["source"] in {"audio", "device", "label"}:
            stream["status"] = "not_requested"
            stream["reason_codes"] = ["not_required_for_field_ai_001"]


def _calibrated_rows(
    raw_rows: list[dict[str, Any]],
    calibration: Mapping[str, Any],
    *,
    session_id: str,
    raw_artifact_sha256: str,
) -> list[dict[str, Any]]:
    accel_bias = calibration["accelerometer"]["bias_mg_xyz"]
    accel_gain = calibration["accelerometer"]["correction_gain_xyz"]
    gyro_bias = calibration["gyroscope"]["bias_mdps_xyz"]
    output: list[dict[str, Any]] = []
    for row in raw_rows:
        samples: list[dict[str, Any]] = []
        for sample in row["samples"]:
            raw_accel = sample["accel_mg"]
            raw_gyro = sample["gyro_mdps"]
            accel = [
                field_session._round_physical((raw_accel[axis] - accel_bias[axis]) * accel_gain[axis])
                for axis in range(3)
            ]
            gyro = [
                field_session._round_physical(raw_gyro[axis] - gyro_bias[axis])
                for axis in range(3)
            ]
            samples.append(
                {
                    "index": sample["index"],
                    "offset_us": sample["offset_us"],
                    "uncalibrated": {"accel_mg": raw_accel, "gyro_mdps": raw_gyro},
                    "calibrated": {
                        "accel_mg": accel,
                        "gyro_mdps": gyro,
                        "accel_m_s2": [field_session._round_physical(item * MG_TO_M_S2) for item in accel],
                        "gyro_rad_s": [field_session._round_physical(item * MDPS_TO_RAD_S) for item in gyro],
                    },
                }
            )
        if len(samples) != len(row["samples"]):
            _fail(f"raw/calibrated sample count mismatch for {row['window_id']}")
        output.append(
            {
                "schema_version": field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
                "field_session_id": session_id,
                "calibration_id": calibration["calibration_id"],
                "calibration_identity_sha256": calibration["identity_sha256"],
                "source_window": {
                    "contract_version": row["contract_version"],
                    "window_id": row["window_id"],
                    "capture_cmd_id": row["capture_cmd_id"],
                    "test_run_id": row["test_run_id"],
                    "transport_type": row["transport_type"],
                    "samples_sha256": row["samples_sha256"],
                    "source_artifact_sha256": raw_artifact_sha256,
                    "time_basis": row["capture_time_basis"],
                },
                "sample_count": len(samples),
                "requested_interval_us": row["capture"]["requested_interval_us"],
                "training_allowed": False,
                "production_ready": False,
                "availability": {
                    "adc_counts": "unavailable_in_imu_window_v1",
                    "temperature": "unavailable_in_imu_window_v1",
                    "sample_utc": "external_a0_002_time_lineage",
                },
                "samples": samples,
            }
        )
    if len(output) != len(raw_rows):
        _fail("raw/calibrated IMU window counts differ")
    return output


def _input_test_run_ids(field_export: Mapping[str, Any], imu_rows: list[Mapping[str, Any]]) -> list[str]:
    values: set[str] = set()
    root_run = field_export.get("test_run")
    if isinstance(root_run, Mapping) and root_run.get("test_run_id") is not None:
        values.add(_require_safe_id(root_run.get("test_run_id"), "field export test_run_id"))
    for row in field_export.get("messages", []):
        if isinstance(row, Mapping) and row.get("test_run_id") is not None:
            values.add(_require_safe_id(row.get("test_run_id"), "message test_run_id"))
    for row in imu_rows:
        values.add(_require_safe_id(row.get("test_run_id"), "IMU test_run_id"))
    return sorted(values)


def pack_field_session(
    *,
    field_export_path: Path,
    imu_windows_path: Path,
    calibration_artifact_path: Path,
    sidecar_bundle_path: Path,
    output_dir: Path,
    test_scenario: str,
    firmware_commit: str,
    firmware_image_sha256: str,
    repository_commit: str,
) -> dict[str, Any]:
    """Create one sealed package and return its honest structural report."""
    firmware_commit = _require_commit(firmware_commit, "firmware_commit")
    firmware_image_sha256 = _require_sha256(firmware_image_sha256, "firmware_image_sha256")
    repository_commit = _require_commit(repository_commit, "repository_commit")
    if not isinstance(test_scenario, str) or not test_scenario.strip() or len(test_scenario) > 256:
        _fail("test_scenario must be a non-empty string of at most 256 characters")

    input_paths = [
        field_export_path,
        imu_windows_path,
        calibration_artifact_path,
        sidecar_bundle_path,
    ]
    resolved_inputs = [path.resolve(strict=False) for path in input_paths]
    if len(set(resolved_inputs)) != len(resolved_inputs):
        _fail("all four packer inputs must be distinct files")
    output = output_dir.resolve(strict=False)
    if output.exists():
        _fail(f"output_dir already exists; refusing to overwrite: {output}")
    if any(output == path or output in path.parents for path in resolved_inputs):
        _fail("output_dir must not contain an explicit input")

    field_bytes = _require_file(field_export_path, "Message Hub field export")
    imu_bytes = _require_file(imu_windows_path, "IMU windows JSONL")
    calibration_bytes = _require_file(calibration_artifact_path, "A0-001 calibration artifact")
    sidecar_bytes = _require_file(sidecar_bundle_path, "sidecar bundle")
    field_export = _load_json_bytes(field_bytes, "Message Hub field export")
    imu_rows = _load_jsonl_bytes(imu_bytes, "IMU windows JSONL")
    calibration = _load_json_bytes(calibration_bytes, "A0-001 calibration artifact")
    sidecar = _load_json_bytes(sidecar_bytes, "sidecar bundle")

    _validate_calibration(
        calibration,
        firmware_commit=firmware_commit,
        firmware_image_sha256=firmware_image_sha256,
    )
    for name, value in (
        ("Message Hub field export", field_export),
        ("IMU windows", imu_rows),
        ("sidecar bundle", sidecar),
    ):
        _check_input_provenance(
            value,
            name=name,
            firmware_commit=firmware_commit,
            firmware_image_sha256=firmware_image_sha256,
            repository_commit=repository_commit,
        )

    device_id, start_ns, end_ns, gnss_rows, lte_rows = _validate_field_export(field_export)
    if calibration["device"]["device_id"] != device_id:
        _fail("field export device_id conflicts with the calibration artifact")
    boot_count = _field_boot_count(field_export, imu_rows)
    _validate_imu_rows(
        imu_rows,
        calibration=calibration,
        device_id=device_id,
        boot_count=boot_count,
        start_ns=start_ns,
        end_ns=end_ns,
    )
    session_id, operator_ref, phone_id, sidecar_manual, sidecar_camera, decoded_media = _validate_sidecar(
        sidecar,
        start_ns=start_ns,
        end_ns=end_ns,
    )

    staging = output.parent / f".{output.name}.pack-{secrets.token_hex(6)}"
    if staging.exists():
        _fail(f"temporary output collision: {staging}")
    staging.mkdir(parents=True)
    try:
        artifacts: list[dict[str, Any]] = []
        _write_bytes(staging / "inputs/message-hub-field-export.json", field_bytes)
        field_input_artifact = _artifact(
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
        artifacts.append(field_input_artifact)
        _write_bytes(staging / "inputs/sidecar-bundle.json", sidecar_bytes)
        sidecar_artifact = _artifact(
            staging,
            artifact_id="input-sidecar-bundle",
            relative_path="inputs/sidecar-bundle.json",
            role="legacy_attachment",
            format_name="json",
            media_type="application/json",
            contract=SIDECAR_VERSION,
            privacy_class="unknown",
            record_count=None,
        )
        artifacts.append(sidecar_artifact)

        _write_bytes(staging / "calibration/imu-calibration.json", calibration_bytes)
        calibration_artifact = _artifact(
            staging,
            artifact_id="imu-calibration-artifact",
            relative_path="calibration/imu-calibration.json",
            role="calibration",
            format_name="json",
            media_type="application/json",
            contract=CALIBRATION_CONTRACT_VERSION,
            privacy_class="structured_sensor",
            record_count=None,
        )
        artifacts.append(calibration_artifact)

        _write_bytes(staging / "streams/gnss.jsonl", _stable_jsonl(gnss_rows))
        gnss_artifact = _artifact(
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
        _write_bytes(staging / "streams/lte.jsonl", _stable_jsonl(lte_rows))
        lte_artifact = _artifact(
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
        _write_bytes(staging / "streams/imu-raw.jsonl", imu_bytes)
        raw_imu_artifact = _artifact(
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

        calibrated_rows = _calibrated_rows(
            imu_rows,
            calibration,
            session_id=session_id,
            raw_artifact_sha256=raw_imu_artifact["sha256"],
        )
        _write_bytes(staging / "streams/imu-calibrated.jsonl", _stable_jsonl(calibrated_rows))
        calibrated_artifact = _artifact(
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

        camera_index: list[dict[str, Any]] = []
        media_root = (staging / "media").resolve(strict=False)
        for record in sidecar_camera:
            output_media_path = f"media/{record['media_path']}"
            payload = decoded_media[record["media_path"]]
            media_target = staging.joinpath(*PurePosixPath(output_media_path).parts).resolve(strict=False)
            try:
                media_target.relative_to(media_root)
            except ValueError as error:
                raise FieldSessionPackError(
                    f"sidecar media target escapes staging/media: {record['media_path']}"
                ) from error
            _write_bytes(media_target, payload)
            media_artifact = _artifact(
                staging,
                artifact_id=f"camera-media-{record['sequence_id']:06d}",
                relative_path=output_media_path,
                role="raw_media",
                format_name="jpeg",
                media_type="image/jpeg",
                contract=None,
                privacy_class="private_media",
                record_count=None,
            )
            artifacts.append(media_artifact)
            camera_index.append(
                {
                    "contract_version": CAMERA_INDEX_VERSION,
                    "observation_id": record["observation_id"],
                    "session_id": session_id,
                    "sequence_id": record["sequence_id"],
                    "source": "camera",
                    "capture_method": "test_phone",
                    "timestamp_monotonic_ns": record["timestamp_monotonic_ns"],
                    "source_timestamp_utc": record["timestamp_utc"],
                    "timestamp_semantics": "capture_return",
                    "clock_domain_id": record["clock_domain_id"],
                    "clock_sample_id": record["clock_sample_id"],
                    "alignment_status": "estimated_unverified",
                    "timestamp_uncertainty_ns": record["timestamp_uncertainty_ns"],
                    "media_artifact_id": media_artifact["artifact_id"],
                    "media_path": media_artifact["path"],
                    "media_sha256": media_artifact["sha256"],
                    "media_size_bytes": media_artifact["size_bytes"],
                    "reason_codes": list(record.get("reason_codes") or []),
                }
            )
        _write_bytes(staging / "streams/camera-index.jsonl", _stable_jsonl(camera_index))
        camera_artifact = _artifact(
            staging,
            artifact_id="stream-camera-index",
            relative_path="streams/camera-index.jsonl",
            role="stream_data",
            format_name="jsonl",
            media_type="application/x-ndjson",
            contract=CAMERA_INDEX_VERSION,
            privacy_class="structured_sensor",
            record_count=len(camera_index),
        )
        artifacts.append(camera_artifact)

        uncertainty_floor_ns = end_ns - start_ns
        created_at = _utc_text(end_ns)
        primary_clock = f"{device_id}:boot:{boot_count}:uptime"
        sidecar_clock = sidecar["producer"]["clock_domain_id"]
        primary_run_id = f"{device_id}:boot:{boot_count}"
        receive_only_run_id = f"{device_id}:receive-only"
        sidecar_run_id = sidecar["producer"]["device_run_id"]
        mappings: list[dict[str, Any]] = []

        imu_anchors: list[dict[str, Any]] = []
        for index, row in enumerate(imu_rows):
            for edge, uptime_key, receive_key in (
                ("start", "capture_start_uptime_us", "server_received_at_first"),
                ("end", "capture_end_uptime_us", "server_received_at_last"),
            ):
                imu_anchors.append(
                    {
                        "anchor_id": f"imu-server-anchor-{index:06d}-{edge}",
                        "source": "host_clock",
                        "timestamp_monotonic_ns": row["capture"][uptime_key] * 1_000,
                        "timestamp_utc": _utc_text(_utc_ns(row[receive_key], f"IMU server receive {edge}")),
                        "uncertainty_ns": uncertainty_floor_ns,
                        "source_record_ref": raw_imu_artifact["path"],
                        "source_record_sha256": raw_imu_artifact["sha256"],
                    }
                )
        imu_mapping = _mapping(
            mapping_id="map-imu-server-estimated",
            device_id=device_id,
            clock_domain_id=primary_clock,
            boot_count=boot_count,
            anchors=imu_anchors,
            uncertainty_floor_ns=uncertainty_floor_ns,
            anchor_method="server_receive_window_estimate",
            session_id=session_id,
            firmware_commit=firmware_commit,
            created_at=created_at,
        )
        mappings.append(imu_mapping)

        gnss_source_values = [_gnss_source_utc(row) for row in gnss_rows]
        gnss_source_times = [value for value, _field in gnss_source_values]
        gnss_source_fields = [field for _value, field in gnss_source_values]
        gnss_uptimes = [_parse_uptime_ms(row.get("ts")) for row in gnss_rows]
        gnss_mapping: dict[str, Any] | None = None
        gnss_mode = "receive_only"
        if all(item is not None for item in gnss_source_times) and all(item is not None for item in gnss_uptimes):
            gnss_anchors = [
                {
                    "anchor_id": f"gnss-source-anchor-{index:06d}",
                    "source": "gnss",
                    "timestamp_monotonic_ns": int(gnss_uptimes[index]) * 1_000_000,
                    "timestamp_utc": str(gnss_source_times[index]),
                    "uncertainty_ns": uncertainty_floor_ns,
                    "source_record_ref": gnss_artifact["path"],
                    "source_record_sha256": gnss_artifact["sha256"],
                }
                for index in range(len(gnss_rows))
            ]
            gnss_mapping = _mapping(
                mapping_id="map-gnss-source-estimated",
                device_id=device_id,
                clock_domain_id=primary_clock,
                boot_count=boot_count,
                anchors=gnss_anchors,
                uncertainty_floor_ns=uncertainty_floor_ns,
                anchor_method="gnss_source_utc_to_device_uptime_estimate",
                session_id=session_id,
                firmware_commit=firmware_commit,
                created_at=created_at,
            )
            mappings.append(gnss_mapping)
            gnss_mode = "estimated_source_utc"
        elif any(item is not None for item in gnss_source_times):
            gnss_mode = (
                "direct_source_utc_unaligned"
                if all(item is not None for item in gnss_source_times)
                else "mixed_direct_source_utc_and_receive_only"
            )

        clock_samples = sidecar["clock"]["samples"]
        sidecar_anchors = [
            {
                "anchor_id": f"sidecar-clock-anchor-{index:06d}",
                "source": "host_clock",
                "timestamp_monotonic_ns": sample["timestamp_monotonic_ns"],
                "timestamp_utc": _utc_text(_utc_ns(sample["timestamp_utc"], "sidecar clock UTC")),
                "uncertainty_ns": max(uncertainty_floor_ns, sample["pairing_span_ns"]),
                "source_record_ref": sidecar_artifact["path"],
                "source_record_sha256": sidecar_artifact["sha256"],
            }
            for index, sample in enumerate(clock_samples)
        ]
        sidecar_mapping = _mapping(
            mapping_id="map-sidecar-clock-estimated",
            device_id=phone_id,
            clock_domain_id=sidecar_clock,
            boot_count=0,
            anchors=sidecar_anchors,
            uncertainty_floor_ns=uncertainty_floor_ns,
            anchor_method="browser_performance_date_pair_estimate",
            session_id=session_id,
            firmware_commit=repository_commit,
            created_at=created_at,
        )
        mappings.append(sidecar_mapping)

        records: list[dict[str, Any]] = []
        fw_version = calibration["firmware"]["fw_version"]
        for index, row in enumerate(gnss_rows):
            receive = _utc_text(_utc_ns(row["server_received_at"], "GNSS receive time"))
            if gnss_mapping is not None:
                monotonic_ns = int(gnss_uptimes[index]) * 1_000_000
                mapped_utc = _utc_text(time_lineage.apply_clock_mapping(gnss_mapping, monotonic_ns))
                record = _time_record(
                    observation_id=f"gnss-{row['seq']}",
                    device_id=device_id,
                    source="gnss",
                    stream_id="gnss-primary",
                    sequence_id=row["seq"],
                    clock_domain_id=primary_clock,
                    boot_count=boot_count,
                    timestamp_monotonic_ns=monotonic_ns,
                    timestamp_utc=mapped_utc,
                    source_timestamp={
                        "raw_value": gnss_source_times[index],
                        "unit": "iso8601",
                        "clock_domain_id": "gnss-utc",
                        "semantics": "fix_time",
                        "source_field": gnss_source_fields[index],
                    },
                    receive_timestamp_utc=receive,
                    ingest_timestamp_utc=receive,
                    alignment_status="estimated",
                    monotonic_origin="device_capture",
                    monotonic_source_field="message.ts",
                    utc_origin="clock_mapping",
                    mapping_id=gnss_mapping["mapping_id"],
                    uncertainty_ns=gnss_mapping["uncertainty_ns"],
                    reason_codes=["gnss_source_utc_mapping_estimated"],
                    session_id=session_id,
                    test_run_id=row.get("test_run_id"),
                    firmware_version=row.get("fw_version") or fw_version,
                    firmware_commit=firmware_commit,
                    source_artifact=gnss_artifact,
                )
            elif gnss_source_times[index] is not None:
                direct_source_utc = str(gnss_source_times[index])
                record = _time_record(
                    observation_id=f"gnss-{row['seq']}",
                    device_id=device_id,
                    source="gnss",
                    stream_id="gnss-primary",
                    sequence_id=row["seq"],
                    clock_domain_id=None,
                    boot_count=None,
                    timestamp_monotonic_ns=None,
                    timestamp_utc=direct_source_utc,
                    source_timestamp={
                        "raw_value": direct_source_utc,
                        "unit": "iso8601",
                        "clock_domain_id": "gnss-utc",
                        "semantics": "fix_time",
                        "source_field": gnss_source_fields[index],
                    },
                    receive_timestamp_utc=receive,
                    ingest_timestamp_utc=receive,
                    alignment_status="unavailable",
                    monotonic_origin="unavailable",
                    monotonic_source_field=None,
                    utc_origin="source_timestamp",
                    mapping_id=None,
                    uncertainty_ns=None,
                    reason_codes=["gnss_monotonic_unavailable_direct_source_utc_only"],
                    session_id=session_id,
                    test_run_id=row.get("test_run_id"),
                    firmware_version=row.get("fw_version") or fw_version,
                    firmware_commit=firmware_commit,
                    source_artifact=gnss_artifact,
                )
            else:
                raw_time = row.get("ts")
                record = _time_record(
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
                    ingest_timestamp_utc=receive,
                    alignment_status="receive_only",
                    monotonic_origin="unavailable",
                    monotonic_source_field=None,
                    utc_origin="unavailable",
                    mapping_id=None,
                    uncertainty_ns=None,
                    reason_codes=["gnss_source_utc_unavailable"],
                    session_id=session_id,
                    test_run_id=row.get("test_run_id"),
                    firmware_version=row.get("fw_version") or fw_version,
                    firmware_commit=firmware_commit,
                    source_artifact=gnss_artifact,
                )
            records.append(record)

        for row in lte_rows:
            receive = _utc_text(_utc_ns(row["server_received_at"], "LTE receive time"))
            raw_time = row.get("ts")
            records.append(
                _time_record(
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
                    ingest_timestamp_utc=receive,
                    alignment_status="receive_only",
                    monotonic_origin="unavailable",
                    monotonic_source_field=None,
                    utc_origin="unavailable",
                    mapping_id=None,
                    uncertainty_ns=None,
                    reason_codes=["lte_device_time_unavailable_receive_only"],
                    session_id=session_id,
                    test_run_id=row.get("test_run_id"),
                    firmware_version=row.get("fw_version") or fw_version,
                    firmware_commit=firmware_commit,
                    source_artifact=lte_artifact,
                )
            )

        for sequence, row in enumerate(sorted(imu_rows, key=lambda item: item["capture"]["capture_start_uptime_us"])):
            monotonic_ns = row["capture"]["capture_start_uptime_us"] * 1_000
            receive = _utc_text(_utc_ns(row["server_received_at_first"], "IMU receive start"))
            ingest = _utc_text(_utc_ns(row["server_received_at_last"], "IMU receive end"))
            records.append(
                _time_record(
                    observation_id=f"imu-{sequence:06d}",
                    device_id=device_id,
                    source="imu",
                    stream_id="imu-primary",
                    sequence_id=sequence,
                    clock_domain_id=primary_clock,
                    boot_count=boot_count,
                    timestamp_monotonic_ns=monotonic_ns,
                    timestamp_utc=_utc_text(time_lineage.apply_clock_mapping(imu_mapping, monotonic_ns)),
                    source_timestamp={
                        "raw_value": row["capture"]["capture_start_uptime_us"],
                        "unit": "us",
                        "clock_domain_id": primary_clock,
                        "semantics": "sample_time",
                        "source_field": "capture.capture_start_uptime_us",
                    },
                    receive_timestamp_utc=receive,
                    ingest_timestamp_utc=ingest,
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

        for row in camera_index:
            monotonic_ns = row["timestamp_monotonic_ns"]
            records.append(
                _time_record(
                    observation_id=row["observation_id"],
                    device_id=phone_id,
                    source="camera",
                    stream_id="camera-primary",
                    sequence_id=row["sequence_id"],
                    clock_domain_id=sidecar_clock,
                    boot_count=0,
                    timestamp_monotonic_ns=monotonic_ns,
                    timestamp_utc=_utc_text(time_lineage.apply_clock_mapping(sidecar_mapping, monotonic_ns)),
                    source_timestamp={
                        "raw_value": monotonic_ns,
                        "unit": "ns",
                        "clock_domain_id": sidecar_clock,
                        "semantics": "unknown",
                        "source_field": "sidecar.records.timestamp_monotonic_ns",
                    },
                    receive_timestamp_utc=None,
                    ingest_timestamp_utc=None,
                    alignment_status="estimated",
                    monotonic_origin="source_timestamp",
                    monotonic_source_field="sidecar.records.timestamp_monotonic_ns",
                    utc_origin="clock_mapping",
                    mapping_id=sidecar_mapping["mapping_id"],
                    uncertainty_ns=sidecar_mapping["uncertainty_ns"],
                    reason_codes=["camera_capture_return_not_exposure", "sidecar_clock_estimated"],
                    session_id=session_id,
                    test_run_id=None,
                    firmware_version=SIDECAR_VERSION,
                    firmware_commit=repository_commit,
                    source_artifact=camera_artifact,
                )
            )

        manual_events: list[dict[str, Any]] = []
        for row in sidecar_manual:
            monotonic_ns = row["timestamp_monotonic_ns"]
            manual_events.append(
                {
                    "contract_version": field_session.MANUAL_EVENT_CONTRACT_VERSION,
                    "event_id": row["event_id"],
                    "session_id": session_id,
                    "sequence_id": row["sequence_id"],
                    "event_type": row["event_type"],
                    "capture_method": "test_phone",
                    "device_run_id": sidecar_run_id,
                    "timestamp_monotonic_ns": monotonic_ns,
                    "timestamp_utc": _utc_text(time_lineage.apply_clock_mapping(sidecar_mapping, monotonic_ns)),
                    "source_timestamp": {
                        "raw_value": monotonic_ns,
                        "unit": "ns",
                        "clock_domain_id": sidecar_clock,
                        "source_field": "sidecar.records.timestamp_monotonic_ns",
                    },
                    "monotonic_clock_domain_id": sidecar_clock,
                    "boot_count": 0,
                    "mapping_id": sidecar_mapping["mapping_id"],
                    "timestamp_uncertainty_ns": sidecar_mapping["uncertainty_ns"],
                    "receive_timestamp_utc": None,
                    "ingest_timestamp_utc": None,
                    "alignment_status": "estimated",
                    "timestamp_monotonic_origin": "producer_clock",
                    "timestamp_utc_origin": "clock_mapping",
                    "operator_ref": operator_ref,
                    "note": row.get("note"),
                    "label_semantics": "weak_operator_event",
                    "reason_codes": ["sidecar_clock_estimated_unverified"],
                }
            )
        _write_bytes(staging / "events/manual-events.jsonl", _stable_jsonl(manual_events))
        manual_artifact = _artifact(
            staging,
            artifact_id="stream-manual-events",
            relative_path="events/manual-events.jsonl",
            role="stream_data",
            format_name="jsonl",
            media_type="application/x-ndjson",
            contract=field_session.MANUAL_EVENT_CONTRACT_VERSION,
            privacy_class="structured_sensor",
            record_count=len(manual_events),
        )
        artifacts.append(manual_artifact)

        consent_payload = {
            "contract_version": "egolink.field_collection_consent.v0.1",
            "session_id": session_id,
            "source_bundle_sha256": sidecar_artifact["sha256"],
            "operator_acknowledgement": sidecar["privacy"]["consent_acknowledgement"],
            "scope": "local_engineering_private_jpeg_and_location_package",
            "training_allowed": False,
            "control_plane_approval": False,
            "gate_approval": False,
        }
        retention_payload = {
            "contract_version": "egolink.field_retention_policy.v0.1",
            "session_id": session_id,
            "source_bundle_sha256": sidecar_artifact["sha256"],
            "operator_acknowledgement": sidecar["privacy"]["retention_acknowledgement"],
            "policy": "retain locally through EXP-A1-000 review, then perform explicit post-experiment review",
            "must_not_commit_private_data_to_git": True,
            "training_allowed": False,
            "control_plane_approval": False,
            "gate_approval": False,
        }
        _write_json(staging / "privacy/consent.json", consent_payload)
        consent_artifact = _artifact(
            staging,
            artifact_id="field-consent",
            relative_path="privacy/consent.json",
            role="consent",
            format_name="json",
            media_type="application/json",
            contract="egolink.field_collection_consent.v0.1",
            privacy_class="policy_metadata",
            record_count=None,
        )
        artifacts.append(consent_artifact)
        _write_json(staging / "privacy/retention-policy.json", retention_payload)
        retention_artifact = _artifact(
            staging,
            artifact_id="field-retention-policy",
            relative_path="privacy/retention-policy.json",
            role="retention_policy",
            format_name="json",
            media_type="application/json",
            contract="egolink.field_retention_policy.v0.1",
            privacy_class="policy_metadata",
            record_count=None,
        )
        artifacts.append(retention_artifact)

        _write_bytes(staging / "time/clock-mappings.jsonl", _stable_jsonl(mappings))
        mapping_artifact = _artifact(
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
        artifacts.append(mapping_artifact)
        ordered_records = sorted(records, key=lambda item: (item["source"], item["sequence_id"]))
        _write_bytes(staging / "time/time-records.jsonl", _stable_jsonl(ordered_records))
        time_artifact = _artifact(
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
        artifacts.append(time_artifact)
        time_report = time_lineage.validate_time_lineage(
            ordered_records,
            mappings,
            generated_at=created_at,
        )
        if not time_report["valid"]:
            _fail(f"generated A0-002 lineage is invalid: {time_report['errors'][:3]}")
        _write_json(staging / "time/a0-002-validation-report.json", time_report)
        time_report_artifact = _artifact(
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
        artifacts.append(time_report_artifact)

        manifest = field_session.build_draft_manifest(
            device_id=device_id,
            operator_ref=operator_ref,
            protocol_id="FIELD-AI-001",
            test_scenario=test_scenario.strip(),
            created_at_utc=created_at,
            session_id=session_id,
        )
        manifest["lifecycle_state"] = "complete"
        manifest["capture_interval"] = {
            "start_utc": _utc_text(start_ns),
            "end_utc": _utc_text(end_ns),
            "timezone": "Asia/Shanghai",
        }
        manifest["device_runs"] = [
            {
                "device_run_id": primary_run_id,
                "device_id": device_id,
                "role": "primary",
                "board_id": calibration["device"]["board_id"],
                "hardware_revision": calibration["device"]["hardware_revision"],
                "firmware_version": fw_version,
                "firmware_commit": firmware_commit,
                "firmware_image_sha256": firmware_image_sha256,
                "boot_count": boot_count,
                "monotonic_clock_domain_ids": [primary_clock],
                "source_status": "observed",
            },
            {
                "device_run_id": receive_only_run_id,
                "device_id": device_id,
                "role": "connectivity",
                "board_id": calibration["device"]["board_id"],
                "hardware_revision": calibration["device"]["hardware_revision"],
                "firmware_version": fw_version,
                "firmware_commit": firmware_commit,
                "firmware_image_sha256": firmware_image_sha256,
                "boot_count": None,
                "monotonic_clock_domain_ids": [],
                "source_status": "observed",
            },
            {
                "device_run_id": sidecar_run_id,
                "device_id": phone_id,
                "role": "camera",
                "board_id": "test-phone-sidecar",
                "hardware_revision": "unrecorded",
                "firmware_version": SIDECAR_VERSION,
                "firmware_commit": repository_commit,
                "firmware_image_sha256": None,
                "boot_count": 0,
                "monotonic_clock_domain_ids": [sidecar_clock],
                "source_status": "observed",
            },
        ]
        manifest["software"] = {
            "repository": "egolink",
            "repository_commit": repository_commit,
            "capture_tool": "pc_simulator.field_session_pack",
            "capture_tool_version": PACKER_VERSION,
        }
        manifest["scenario"].update(
            {
                "declared_carry_conditions": ["bag"],
                "declared_motion_conditions": ["stationary", "walking"],
                "declared_environments": ["outdoor", "indoor", "transition"],
                "notes": "FIELD-AI-001 engineering smoke package; scenario declarations and operator events are not ground truth.",
            }
        )
        manifest["capture_profile"]["protocol_version"] = "FIELD-AI-001-v0.1"
        manifest["sensor_policies"].update(
            {
                "imu": {"mode": "event_triggered", "policy_id": "bounded-imu-window-v1", "requested_rate_hz": 20.0, "config_artifact_id": None},
                "gnss": {"mode": "scheduled", "policy_id": "fw007-field-policy", "requested_rate_hz": None, "config_artifact_id": None},
                "lte": {"mode": "scheduled", "policy_id": "fw007-field-policy", "requested_rate_hz": None, "config_artifact_id": None},
                "camera": {"mode": "event_triggered", "policy_id": "test-phone-manual-jpeg", "requested_rate_hz": None, "config_artifact_id": None},
                "audio": {"mode": "disabled", "policy_id": None, "requested_rate_hz": None, "config_artifact_id": None},
            }
        )
        manifest["privacy"].update(
            {
                "consent_status": "allowed",
                "privacy_review_status": "approved",
                "location_privacy_class": "engineering_private",
                "raw_image_allowed": True,
                "retention_status": "approved",
                "consent_artifact_id": consent_artifact["artifact_id"],
                "retention_policy_artifact_id": retention_artifact["artifact_id"],
                "reviewed_by": operator_ref,
                "reviewed_at_utc": sidecar["privacy"]["acknowledged_at_utc"],
            }
        )
        manifest["provenance"]["message_hub_test_run_ids"] = _input_test_run_ids(field_export, imu_rows)
        manifest["artifacts"] = artifacts
        _unrequested_streams(manifest)

        records_by_source = {
            source: [row for row in ordered_records if row["source"] == source]
            for source in time_lineage.SOURCES
        }
        gnss_run = primary_run_id if gnss_mode == "estimated_source_utc" else receive_only_run_id
        _set_stream(
            manifest,
            stream_id="gnss-primary",
            source="gnss",
            artifact=gnss_artifact,
            contract=MESSAGE_HUB_GNSS_VERSION,
            observation_count=len(gnss_rows),
            bounds=field_session._observed_bounds(records_by_source["gnss"]),
            device_run_id=gnss_run,
            clock_domain_id=primary_clock if gnss_mode == "estimated_source_utc" else None,
        )
        _set_stream(
            manifest,
            stream_id="lte-primary",
            source="lte",
            artifact=lte_artifact,
            contract=MESSAGE_HUB_LTE_VERSION,
            observation_count=len(lte_rows),
            bounds=field_session._observed_bounds(records_by_source["lte"]),
            device_run_id=receive_only_run_id,
            clock_domain_id=None,
        )
        raw_stream = _set_stream(
            manifest,
            stream_id="imu-primary",
            source="imu",
            artifact=raw_imu_artifact,
            contract="egolink.imu_window.v1",
            observation_count=len(imu_rows),
            bounds=field_session._observed_bounds(records_by_source["imu"]),
            device_run_id=primary_run_id,
            clock_domain_id=primary_clock,
            variant="uncalibrated_engineering",
        )
        _set_stream(
            manifest,
            stream_id="camera-primary",
            source="camera",
            artifact=camera_artifact,
            contract=CAMERA_INDEX_VERSION,
            observation_count=len(camera_index),
            bounds=field_session._observed_bounds(records_by_source["camera"]),
            device_run_id=sidecar_run_id,
            clock_domain_id=sidecar_clock,
        )
        _set_stream(
            manifest,
            stream_id="manual-event-primary",
            source="manual_event",
            artifact=manual_artifact,
            contract=field_session.MANUAL_EVENT_CONTRACT_VERSION,
            observation_count=len(manual_events),
            bounds=field_session._observed_bounds(manual_events),
            device_run_id=sidecar_run_id,
            clock_domain_id=sidecar_clock,
            variant="manual_event",
        )
        manifest["streams"].append(
            {
                "stream_id": "imu-calibrated",
                "source": "imu",
                "variant": "calibrated",
                "status": "captured",
                "format": "jsonl",
                "record_contract_version": field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
                "artifact_id": calibrated_artifact["artifact_id"],
                "observation_count": len(calibrated_rows),
                "device_run_id": primary_run_id,
                "clock_domain_id": primary_clock,
                "bounds": copy.deepcopy(raw_stream["bounds"]),
                "raw_preserved": True,
                "calibration_id": calibration["calibration_id"],
                "source_stream_id": raw_stream["stream_id"],
                "generator": {
                    "name": "pc_simulator.field_session_pack",
                    "version": PACKER_VERSION,
                    "commit": repository_commit,
                    "source_stream_ids": [raw_stream["stream_id"]],
                    "config_artifact_id": calibration_artifact["artifact_id"],
                },
                "reason_codes": [],
            }
        )
        manifest["calibrations"] = [
            {
                "calibration_id": calibration["calibration_id"],
                "sensor": "imu",
                "device_id": device_id,
                "status": "engineering",
                "artifact_id": calibration_artifact["artifact_id"],
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
        manifest["limitations"] = [
            "Evidence scope is engineering_smoke_only; A0-002, A0-003, and A-R0 remain unverified.",
            "LTE is receive-only; server receive timestamps are never promoted to source time.",
            "IMU-to-UTC and phone-to-UTC mappings are estimated with the full capture-window duration as conservative uncertainty.",
            "Camera timestamps are browser capture-return times, not exposure timestamps, and Camera is a test-phone sidecar rather than the Ego Link onboard Camera.",
            "Operator scenario declarations and manual events are weak labels, not ground truth.",
            "Raw private location and JPEG evidence must not be committed to Git; post-experiment retention review remains required.",
        ]
        sealed = field_session.seal_manifest(
            manifest,
            sealed_by=operator_ref,
            sealed_at_utc=created_at,
        )
        manifest_path = staging / "manifest.json"
        _write_json(manifest_path, sealed)
        validation = field_session.validate_field_session(
            sealed,
            session_root=staging,
            manifest_path=manifest_path,
            generated_at=created_at,
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
            sealed,
            session_root=output,
            manifest_path=final_manifest_path,
            generated_at=created_at,
        )
        if not final_validation["valid"]:
            _fail(f"finalized Field Session failed validation: {final_validation['errors'][:5]}")
        return {
            "pack_version": PACKER_VERSION,
            "ok": True,
            "evidence_scope": "engineering_smoke_only",
            "gate_status": "unverified",
            "session_id": session_id,
            "output_dir": str(output),
            "manifest": str(final_manifest_path),
            "manifest_sha256": field_session.sha256_file(final_manifest_path),
            "source_counts": {
                "gnss": len(gnss_rows),
                "lte": len(lte_rows),
                "imu_windows_raw": len(imu_rows),
                "imu_windows_calibrated": len(calibrated_rows),
                "camera": len(camera_index),
                "manual_event": len(manual_events),
            },
            "time_status": {
                "gnss": gnss_mode,
                "lte": "receive_only",
                "imu": "estimated_server_anchor",
                "camera": "estimated_sidecar_clock",
                "a0_002_field_eligible": final_validation["a0_002_time_lineage"]["field_eligible"],
            },
            "validation": final_validation,
        }
    except Exception:
        if staging.exists() and staging.parent == output.parent:
            shutil.rmtree(staging)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-export", required=True, type=Path)
    parser.add_argument("--imu-windows", required=True, type=Path)
    parser.add_argument("--calibration-artifact", required=True, type=Path)
    parser.add_argument("--sidecar-bundle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--test-scenario", required=True)
    parser.add_argument("--firmware-commit", required=True)
    parser.add_argument("--firmware-image-sha256", required=True)
    parser.add_argument("--repository-commit", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = pack_field_session(
            field_export_path=args.field_export,
            imu_windows_path=args.imu_windows,
            calibration_artifact_path=args.calibration_artifact,
            sidecar_bundle_path=args.sidecar_bundle,
            output_dir=args.output_dir,
            test_scenario=args.test_scenario,
            firmware_commit=args.firmware_commit,
            firmware_image_sha256=args.firmware_image_sha256,
            repository_commit=args.repository_commit,
        )
    except (FieldSessionPackError, field_session.FieldSessionError, time_lineage.SensorTimeLineageError, OSError) as error:
        print(f"FIELD-AI-001 pack error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
