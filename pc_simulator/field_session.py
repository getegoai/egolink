"""A0-003 Field Session manifest creation and offline validation.

The contract is additive.  It does not change firmware, Message Hub storage,
the existing wire protocol, or the legacy ``session_recording.v0.1`` format.
Only one explicitly named session root is inspected; no repository-wide or
runtime-directory discovery is performed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import secrets
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from pc_simulator.imu_six_face_calibration import (
    ARTIFACT_SCHEMA_PATH as IMU_CALIBRATION_SCHEMA_PATH,
    ARTIFACT_SCHEMA_VERSION as IMU_CALIBRATION_CONTRACT_VERSION,
    ESTIMATOR_VERSION as IMU_CALIBRATION_ESTIMATOR_VERSION,
    ImuCalibrationError,
    MDPS_TO_RAD_S,
    METADATA_SCHEMA_VERSION as IMU_CALIBRATION_METADATA_VERSION,
    MG_TO_M_S2,
    SOURCE_CONTRACT_VERSION as IMU_WINDOW_CONTRACT_VERSION,
    artifact_payload_sha256,
    encode_source_samples,
)
from pc_simulator.sensor_time_lineage import (
    SensorTimeLineageError,
    apply_clock_mapping,
    parse_utc_ns,
    source_value_monotonic_ns,
    validate_time_lineage,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "field_session_manifest.schema.json"
MANUAL_EVENT_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "field_manual_event.schema.json"
IMU_FIELD_CALIBRATED_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "imu_field_calibrated_window.schema.json"

CONTRACT_VERSION = "egolink.field_session.v0.1"
MANUAL_EVENT_CONTRACT_VERSION = "egolink.field_manual_event.v0.1"
REPORT_VERSION = "egolink.field_session_validation_report.v0.1"
TIME_RECORD_CONTRACT_VERSION = "egolink.sensor_time_lineage.v0.1"
TIME_MAPPING_CONTRACT_VERSION = "egolink.clock_mapping_segment.v0.1"
IMU_FIELD_CALIBRATED_CONTRACT_VERSION = "egolink.imu_field_calibrated_window.v0.1"

SOURCE_TYPES = ("gnss", "lte", "imu", "camera", "audio", "device", "manual_event", "label")
TIME_LINEAGE_SOURCES = ("gnss", "lte", "imu", "camera")
FIELD_PROFILE_SOURCES = ("gnss", "lte", "imu", "camera", "manual_event")
PHYSICAL_FIELD_SOURCE_STATUSES = {"verified", "observed"}
PRECALIBRATION_VARIANTS = {"raw_counts", "uncalibrated_engineering"}


class FieldSessionError(ValueError):
    """The input cannot be read or interpreted deterministically."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonfinite(item) for item in value)
    return False


def _round_physical(value: float, digits: int = 12) -> float:
    """Match the canonical A0-001 materialization rounding without importing a private helper."""
    if not math.isfinite(value):
        raise FieldSessionError("calibration transform produced a non-finite number")
    rounded = round(value, digits)
    return 0.0 if rounded == -0.0 else rounded


def _imu_calibration_identity_sha256(payload: Mapping[str, Any]) -> str:
    """Rebuild the canonical A0-001 identity from its published artifact fields."""
    source_windows = payload["source_windows"]
    metadata = {
        "schema_version": IMU_CALIBRATION_METADATA_VERSION,
        "calibration_run_id": payload["calibration_run_id"],
        "calibration_time_utc": payload["calibration_time_utc"],
        "calibration_time_source": payload["calibration_time_source"],
        "device_id": payload["device"]["device_id"],
        "board_id": payload["device"]["board_id"],
        "hardware_revision": payload["device"]["hardware_revision"],
        "hardware_profile": payload["device"]["hardware_profile"],
        "mounting_profile_id": payload["mounting"]["mounting_profile_id"],
        "body_axis_mapping_status": payload["mounting"]["body_axis_mapping_status"],
        "imu_model": payload["sensor"]["imu_model"],
        "imu_module": payload["sensor"]["imu_module"],
        "sensor_i2c_address": payload["sensor"]["sensor_i2c_address"],
        "test_run_id": payload["capture_profile"]["test_run_id"],
        "firmware": dict(payload["firmware"]),
        "calibration_software_commit": payload["software"]["calibration_software_commit"],
        "temperature_status": payload["availability"]["temperature"],
        "source_windows": {
            row["role"]: row["window_id"]
            for row in source_windows
        },
    }
    identity_core = {
        "schema_version": IMU_CALIBRATION_CONTRACT_VERSION,
        "estimator_version": IMU_CALIBRATION_ESTIMATOR_VERSION,
        "metadata": metadata,
        "source_windows": source_windows,
        "accelerometer": payload["accelerometer"],
        "gyroscope": payload["gyroscope"],
    }
    return hashlib.sha256(stable_json_bytes(identity_core)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise FieldSessionError(f"cannot read {path}: {error}") from error
    try:
        value = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise FieldSessionError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise FieldSessionError(f"expected a JSON object in {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise FieldSessionError(f"cannot read {path}: {error}") from error
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise FieldSessionError(f"invalid JSONL in {path} at line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise FieldSessionError(f"expected a JSON object in {path} at line {line_number}")
        values.append(value)
    return values


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise FieldSessionError(f"cannot write JSON output {path}: {error}") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_session_id(*, created_at_utc: str | None = None, random_suffix: str | None = None) -> str:
    created = created_at_utc or utc_now()
    instant_ns = parse_utc_ns(created, "created_at_utc")
    stamp = datetime.fromtimestamp(instant_ns / 1_000_000_000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = random_suffix or secrets.token_hex(6)
    if len(suffix) != 12 or any(character not in "0123456789abcdefABCDEF" for character in suffix):
        raise FieldSessionError("random_suffix must be exactly 12 hexadecimal characters")
    return f"FS-{stamp}-{suffix.lower()}"


def _empty_bounds() -> dict[str, None]:
    return {
        "sequence_first": None,
        "sequence_last": None,
        "monotonic_start_ns": None,
        "monotonic_end_ns": None,
        "utc_start": None,
        "utc_end": None,
    }


def _observed_bounds(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)

    def extrema(field: str) -> tuple[Any, Any]:
        observed = [row[field] for row in values if row.get(field) is not None]
        return (min(observed), max(observed)) if observed else (None, None)

    sequence_first, sequence_last = extrema("sequence_id")
    monotonic_start, monotonic_end = extrema("timestamp_monotonic_ns")
    utc_values: list[tuple[int, str]] = []
    for row in values:
        if row.get("timestamp_utc") is not None:
            utc_values.append(
                (parse_utc_ns(row["timestamp_utc"], "stream.timestamp_utc"), row["timestamp_utc"])
            )
    return {
        "sequence_first": sequence_first,
        "sequence_last": sequence_last,
        "monotonic_start_ns": monotonic_start,
        "monotonic_end_ns": monotonic_end,
        "utc_start": min(utc_values)[1] if utc_values else None,
        "utc_end": max(utc_values)[1] if utc_values else None,
    }


def _compare_stream_bounds(
    declared: Mapping[str, Any],
    observed: Mapping[str, Any],
    *,
    stream_id: str,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for field in (
        "sequence_first",
        "sequence_last",
        "monotonic_start_ns",
        "monotonic_end_ns",
    ):
        if declared[field] != observed[field]:
            errors.append(
                _issue(
                    "stream_bounds_mismatch",
                    f"declared {field} differs from the exact observation bounds",
                    stream_id=stream_id,
                )
            )
    for field in ("utc_start", "utc_end"):
        declared_value = declared[field]
        observed_value = observed[field]
        if (declared_value is None) != (observed_value is None):
            errors.append(
                _issue(
                    "stream_bounds_mismatch",
                    f"declared {field} differs from the exact observation bounds",
                    stream_id=stream_id,
                )
            )
        elif declared_value is not None and observed_value is not None:
            try:
                equal = parse_utc_ns(declared_value, field) == parse_utc_ns(observed_value, field)
            except SensorTimeLineageError:
                equal = False
            if not equal:
                errors.append(
                    _issue(
                        "stream_bounds_mismatch",
                        f"declared {field} differs from the exact observation bounds",
                        stream_id=stream_id,
                    )
                )
    return errors


def _draft_stream(source: str) -> dict[str, Any]:
    variants = {
        "imu": "uncalibrated_engineering",
        "manual_event": "manual_event",
        "device": "device_telemetry",
        "label": "label",
    }
    return {
        "stream_id": f"{source}-primary",
        "source": source,
        "variant": variants.get(source, "normalized_observation"),
        "status": "declared_unavailable",
        "format": None,
        "record_contract_version": None,
        "artifact_id": None,
        "observation_count": None,
        "device_run_id": None,
        "clock_domain_id": None,
        "bounds": _empty_bounds(),
        "raw_preserved": None,
        "calibration_id": None,
        "source_stream_id": None,
        "generator": None,
        "reason_codes": ["capture_not_started"],
    }


def build_draft_manifest(
    *,
    device_id: str,
    operator_ref: str,
    protocol_id: str,
    test_scenario: str,
    route_id: str | None = None,
    timezone_name: str = "Asia/Shanghai",
    created_at_utc: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    parse_utc_ns(created, "created_at_utc")
    identifier = session_id or generate_session_id(created_at_utc=created)
    return {
        "contract_version": CONTRACT_VERSION,
        "session_id": identifier,
        "session_type": "field",
        "lifecycle_state": "planned",
        "seal": {
            "status": "unsealed",
            "method": "canonical_json_with_manifest_core_sha256_null",
            "sealed_at_utc": None,
            "sealed_by": None,
            "manifest_core_sha256": None,
            "artifact_set_sha256": None,
        },
        "created_at_utc": created,
        "capture_interval": {
            "start_utc": None,
            "end_utc": None,
            "timezone": timezone_name,
        },
        "primary_device_id": device_id,
        "device_runs": [
            {
                "device_run_id": f"{device_id}-run-001",
                "device_id": device_id,
                "role": "primary",
                "board_id": "unrecorded",
                "hardware_revision": "unrecorded",
                "firmware_version": None,
                "firmware_commit": None,
                "firmware_image_sha256": None,
                "boot_count": None,
                "monotonic_clock_domain_ids": [],
                "source_status": "unverified",
            }
        ],
        "software": {
            "repository": "egolink",
            "repository_commit": None,
            "capture_tool": "unassigned",
            "capture_tool_version": "unassigned",
        },
        "artifacts": [],
        "calibrations": [],
        "scenario": {
            "protocol_id": protocol_id,
            "test_scenario": test_scenario,
            "route_id": route_id,
            "operator_ref": operator_ref,
            "repeat_index": 1,
            "declared_carry_conditions": [],
            "declared_motion_conditions": [],
            "declared_environments": [],
            "notes": None,
        },
        "capture_profile": {
            "profile_id": "a-r0-four-source-v0.1",
            "protocol_version": "unfrozen",
            "required_sources": list(FIELD_PROFILE_SOURCES),
            "optional_sources": ["audio", "device", "label"],
        },
        "sensor_policies": {
            source: {
                "mode": "unknown",
                "policy_id": None,
                "requested_rate_hz": None,
                "config_artifact_id": None,
            }
            for source in ("imu", "gnss", "lte", "camera", "audio")
        },
        "battery": {
            position: {
                "value": None,
                "unit": "unavailable",
                "source_status": "unavailable",
                "source_ref": None,
            }
            for position in ("start", "end")
        },
        "privacy": {
            "consent_status": "not_reviewed",
            "privacy_review_status": "not_reviewed",
            "location_privacy_class": "unknown",
            "raw_image_allowed": False,
            "raw_audio_allowed": False,
            "training_allowed": False,
            "retention_status": "not_reviewed",
            "consent_artifact_id": None,
            "retention_policy_artifact_id": None,
            "reviewed_by": None,
            "reviewed_at_utc": None,
        },
        "split": {
            "name": "unassigned",
            "strategy": "session_route_device_blocked",
            "group_keys": [identifier, device_id] + ([route_id] if route_id else []),
            "leakage_review_status": "pending",
            "reviewed_by": None,
            "reviewed_at_utc": None,
        },
        "provenance": {
            "message_hub_test_run_ids": [],
            "field_run_ids": [],
            "legacy_session_ids": [],
        },
        "streams": [_draft_stream(source) for source in SOURCE_TYPES],
        "time_lineage": {
            "record_contract_version": TIME_RECORD_CONTRACT_VERSION,
            "mapping_contract_version": TIME_MAPPING_CONTRACT_VERSION,
            "record_artifact_ids": [],
            "mapping_artifact_ids": [],
            "validation_report_artifact_id": None,
        },
        "limitations": [
            "Draft only: no sensor source, time lineage, privacy review, or field evidence has been recorded."
        ],
    }


def _load_schema(path: Path) -> dict[str, Any]:
    return load_json(path)


def _issue(code: str, message: str, **context: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"code": code, "message": message}
    value.update({key: item for key, item in context.items() if item is not None})
    return value


def _schema_issues(value: Any, schema: Mapping[str, Any], item_name: str) -> list[dict[str, Any]]:
    if _contains_nonfinite(value):
        return [_issue("nonfinite_number", f"{item_name} contains NaN or Infinity")]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[dict[str, Any]] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path)
        location = f"{item_name}.{path}" if path else item_name
        issues.append(_issue("schema_invalid", f"{location}: {error.message}"))
    return issues


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return duplicate


def _safe_artifact_path(session_root: Path, reference: str) -> Path:
    if "\\" in reference or ":" in reference:
        raise ValueError("artifact ref must be a relative POSIX path without a URI scheme or drive")
    pure = PurePosixPath(reference)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("artifact ref must be a normalized relative POSIX path")
    root = session_root.resolve()
    candidate = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("artifact path must not contain symlinks")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("artifact path escapes the session root") from error
    return resolved


def _artifact_descriptors(manifest: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    return [
        (f"artifact:{artifact['artifact_id']}", artifact)
        for artifact in manifest["artifacts"]
    ]


def artifact_set_sha256(manifest: Mapping[str, Any]) -> str:
    descriptors = sorted(
        (dict(artifact) for artifact in manifest["artifacts"]),
        key=lambda artifact: artifact["artifact_id"],
    )
    return hashlib.sha256(stable_json_bytes(descriptors)).hexdigest()


def manifest_core_sha256(manifest: Mapping[str, Any]) -> str:
    value = json.loads(stable_json_bytes(manifest).decode("utf-8"))
    value["seal"]["manifest_core_sha256"] = None
    return hashlib.sha256(stable_json_bytes(value)).hexdigest()


def seal_manifest(
    manifest: Mapping[str, Any],
    *,
    sealed_by: str,
    sealed_at_utc: str | None = None,
) -> dict[str, Any]:
    if manifest.get("lifecycle_state") != "complete":
        raise FieldSessionError("only a complete session may be sealed")
    if not isinstance(sealed_by, str) or not sealed_by.strip():
        raise FieldSessionError("sealed_by must identify a non-empty actor/ref")
    sealed_at = sealed_at_utc or utc_now()
    sealed_at_ns = parse_utc_ns(sealed_at, "sealed_at_utc")
    created_at = manifest.get("created_at_utc")
    if created_at is not None and sealed_at_ns < parse_utc_ns(created_at, "created_at_utc"):
        raise FieldSessionError("sealed_at_utc cannot precede manifest creation")
    capture_interval = manifest.get("capture_interval")
    capture_end = capture_interval.get("end_utc") if isinstance(capture_interval, Mapping) else None
    if capture_end is not None and sealed_at_ns < parse_utc_ns(capture_end, "capture_interval.end_utc"):
        raise FieldSessionError("sealed_at_utc cannot precede capture end")
    value = json.loads(stable_json_bytes(manifest).decode("utf-8"))
    value["seal"] = {
        "status": "sealed",
        "method": "canonical_json_with_manifest_core_sha256_null",
        "sealed_at_utc": sealed_at,
        "sealed_by": sealed_by,
        "manifest_core_sha256": None,
        "artifact_set_sha256": artifact_set_sha256(value),
    }
    value["seal"]["manifest_core_sha256"] = manifest_core_sha256(value)
    return value


def _verify_artifact(
    *,
    label: str,
    artifact: Mapping[str, Any],
    session_root: Path,
) -> tuple[Path | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    reference = artifact["path"]
    try:
        path = _safe_artifact_path(session_root, reference)
    except ValueError as error:
        return None, [_issue("artifact_ref_unsafe", str(error), artifact_ref=reference, artifact_label=label)]
    if not path.exists():
        return path, [_issue("artifact_missing", "referenced artifact does not exist", artifact_ref=reference, artifact_label=label)]
    if not path.is_file():
        return path, [_issue("artifact_not_file", "referenced artifact is not a regular file", artifact_ref=reference, artifact_label=label)]
    try:
        size = path.stat().st_size
        digest = sha256_file(path)
    except OSError as error:
        raise FieldSessionError(f"cannot inspect artifact {path}: {error}") from error
    if size != artifact["size_bytes"]:
        errors.append(_issue("artifact_size_mismatch", f"declared {artifact['size_bytes']}, observed {size}", artifact_ref=reference, artifact_label=label))
    if digest.lower() != artifact["sha256"].lower():
        errors.append(_issue("artifact_hash_mismatch", "SHA-256 does not match the manifest", artifact_ref=reference, artifact_label=label))
    if artifact["format"] == "jsonl":
        try:
            rows = load_jsonl(path)
        except FieldSessionError as error:
            errors.append(_issue("artifact_content_invalid", str(error), artifact_ref=reference, artifact_label=label))
        else:
            count = len(rows)
            if count != artifact["record_count"]:
                errors.append(_issue("artifact_record_count_mismatch", f"declared {artifact['record_count']}, observed {count}", artifact_ref=reference, artifact_label=label))
    elif artifact["format"] == "json":
        try:
            load_json(path)
        except FieldSessionError as error:
            errors.append(_issue("artifact_content_invalid", str(error), artifact_ref=reference, artifact_label=label))
    return path, errors


def _verify_package_closure(
    *,
    session_root: Path,
    declared_paths: Iterable[str],
    manifest_path: Path | None,
) -> list[dict[str, Any]]:
    root = session_root.resolve()
    allowed = set(declared_paths)
    if manifest_path is not None:
        resolved_manifest = manifest_path.resolve()
        try:
            allowed.add(resolved_manifest.relative_to(root).as_posix())
        except ValueError:
            return [_issue("manifest_outside_session_root", "manifest must be inside the explicit session root")]
    errors: list[dict[str, Any]] = []
    try:
        entries = list(root.rglob("*"))
    except OSError as error:
        raise FieldSessionError(f"cannot enumerate explicit session root {root}: {error}") from error
    observed_files: set[str] = set()
    for entry in entries:
        is_junction = bool(getattr(entry, "is_junction", lambda: False)())
        if entry.is_symlink() or is_junction:
            errors.append(_issue("package_link_forbidden", "sealed package cannot contain symlinks or junctions", artifact_ref=entry.relative_to(root).as_posix()))
            continue
        if entry.is_file():
            observed_files.add(entry.relative_to(root).as_posix())
        elif not entry.is_dir():
            errors.append(_issue("package_special_file_forbidden", "sealed package may contain only directories and regular files", artifact_ref=entry.relative_to(root).as_posix()))
    for extra in sorted(observed_files - allowed):
        errors.append(_issue("package_extra_file", "file is not declared by the manifest", artifact_ref=extra))
    return errors


def _validate_imu_window_rows(
    rows: list[Mapping[str, Any]],
    *,
    stream: Mapping[str, Any],
    device_run: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    errors: list[dict[str, Any]] = []
    windows: dict[str, Mapping[str, Any]] = {}
    seen_window_ids: set[str] = set()
    for index, row in enumerate(rows):
        row_error_start = len(errors)
        label = f"imu_window[{index}]"
        window_id = row.get("window_id")
        if not isinstance(window_id, str) or not window_id:
            errors.append(_issue("imu_window_id_invalid", f"{label} has no valid window_id", stream_id=stream["stream_id"]))
            continue
        if window_id in seen_window_ids:
            errors.append(_issue("imu_window_id_duplicate", "IMU window_id must be unique", stream_id=stream["stream_id"], window_id=window_id))
        seen_window_ids.add(window_id)
        if row.get("contract_version") != IMU_WINDOW_CONTRACT_VERSION:
            errors.append(_issue("imu_window_contract_invalid", f"{label} is not {IMU_WINDOW_CONTRACT_VERSION}", stream_id=stream["stream_id"]))
        if row.get("device_id") != device_run["device_id"] or row.get("boot_count") != device_run["boot_count"]:
            errors.append(_issue("imu_window_device_scope_mismatch", f"{label} differs from its device run", stream_id=stream["stream_id"]))
        if row.get("fw_version") != device_run["firmware_version"]:
            errors.append(_issue("imu_window_firmware_mismatch", f"{label} firmware version differs from its device run", stream_id=stream["stream_id"]))
        if row.get("source") != "qmi8658_i2c" or row.get("source_status") != "observed":
            errors.append(_issue("imu_window_source_unverified", f"{label} is not observed QMI8658 evidence", stream_id=stream["stream_id"]))
        if row.get("training_allowed") is not False:
            errors.append(_issue("imu_window_training_flag_invalid", f"{label} must preserve training_allowed=false", stream_id=stream["stream_id"]))
        if row.get("capture_time_basis") != "device_monotonic_uptime_only":
            errors.append(_issue("imu_window_time_basis_invalid", f"{label} has an unsupported time basis", stream_id=stream["stream_id"]))
        sensor = row.get("sensor") if isinstance(row.get("sensor"), Mapping) else {}
        if sensor.get("accel_unit") != "mg" or sensor.get("gyro_unit") != "mdps" or not sensor.get("model"):
            errors.append(_issue("imu_window_sensor_contract_invalid", f"{label} lacks QMI engineering-unit identity", stream_id=stream["stream_id"]))
        capture = row.get("capture") if isinstance(row.get("capture"), Mapping) else {}
        samples = row.get("samples")
        if not isinstance(samples, list):
            errors.append(_issue("imu_window_samples_invalid", f"{label} samples are missing", stream_id=stream["stream_id"]))
            continue
        if capture.get("sample_count") != len(samples):
            errors.append(_issue("imu_window_sample_count_mismatch", f"{label} sample_count differs from samples", stream_id=stream["stream_id"]))
        try:
            sample_bytes = encode_source_samples(samples, window_id=window_id)
        except (ImuCalibrationError, KeyError, TypeError, ValueError) as error:
            errors.append(_issue("imu_window_samples_invalid", f"{label}: {error}", stream_id=stream["stream_id"]))
            continue
        declared_sample_hash = row.get("samples_sha256")
        if not isinstance(declared_sample_hash, str) or hashlib.sha256(sample_bytes).hexdigest() != declared_sample_hash.lower():
            errors.append(_issue("imu_window_samples_hash_mismatch", f"{label} samples_sha256 does not match source values", stream_id=stream["stream_id"]))
        capture_start = capture.get("capture_start_uptime_us")
        capture_end = capture.get("capture_end_uptime_us")
        if (
            not isinstance(capture_start, int)
            or isinstance(capture_start, bool)
            or not isinstance(capture_end, int)
            or isinstance(capture_end, bool)
            or capture_end <= capture_start
            or (samples and samples[-1].get("offset_us", capture_end) > capture_end - capture_start)
        ):
            errors.append(_issue("imu_window_capture_bounds_invalid", f"{label} capture bounds do not contain its samples", stream_id=stream["stream_id"]))
        if len(errors) == row_error_start:
            windows[window_id] = row
    if stream["observation_count"] != len(rows):
        errors.append(_issue("imu_window_observation_count_mismatch", "IMU observation_count must equal physical window rows", stream_id=stream["stream_id"]))
    return errors, windows


def _validate_imu_contracts(
    manifest: Mapping[str, Any],
    *,
    artifact_index: Mapping[str, Mapping[str, Any]],
    artifact_paths: Mapping[str, Path],
) -> tuple[list[dict[str, Any]], bool]:
    errors: list[dict[str, Any]] = []
    device_run_index = {run["device_run_id"]: run for run in manifest["device_runs"]}
    calibration_schema = _load_schema(IMU_CALIBRATION_SCHEMA_PATH)
    calibrated_schema = _load_schema(IMU_FIELD_CALIBRATED_SCHEMA_PATH)
    calibration_payloads: dict[str, Mapping[str, Any]] = {}
    raw_windows_by_stream: dict[str, dict[str, Mapping[str, Any]]] = {}
    calibrated_rows_by_stream: dict[str, list[Mapping[str, Any]]] = {}

    for calibration in manifest["calibrations"]:
        if calibration["sensor"] != "imu":
            continue
        artifact = artifact_index.get(calibration["artifact_id"])
        path = artifact_paths.get(calibration["artifact_id"])
        if artifact is None or path is None:
            continue
        if (
            artifact["format"] != "json"
            or artifact["content_contract_version"] != IMU_CALIBRATION_CONTRACT_VERSION
        ):
            errors.append(_issue("imu_calibration_contract_invalid", "IMU calibration must use the A0-001 artifact v0.1 contract", calibration_id=calibration["calibration_id"]))
            continue
        try:
            payload = load_json(path)
        except FieldSessionError as error:
            errors.append(_issue("imu_calibration_content_invalid", str(error), calibration_id=calibration["calibration_id"]))
            continue
        payload_issues = _schema_issues(payload, calibration_schema, f"calibration[{calibration['calibration_id']}]")
        errors.extend(payload_issues)
        if payload_issues:
            continue
        calibration_error_start = len(errors)
        if payload["calibration_id"] != calibration["calibration_id"] or payload["device"]["device_id"] != calibration["device_id"]:
            errors.append(_issue("imu_calibration_identity_mismatch", "calibration manifest and artifact identity differ", calibration_id=calibration["calibration_id"]))
        expected_identity = _imu_calibration_identity_sha256(payload)
        if payload["identity_sha256"].lower() != expected_identity:
            errors.append(_issue("imu_calibration_identity_hash_mismatch", "calibration identity_sha256 does not match the canonical A0-001 identity", calibration_id=calibration["calibration_id"]))
        if payload["calibration_id"] != f"imucal-{payload['identity_sha256'][:24].lower()}":
            errors.append(_issue("imu_calibration_id_hash_mismatch", "calibration_id does not derive from identity_sha256", calibration_id=calibration["calibration_id"]))
        if payload["payload_sha256"].lower() != artifact_payload_sha256(dict(payload)):
            errors.append(_issue("imu_calibration_payload_hash_mismatch", "calibration payload_sha256 does not match its canonical payload", calibration_id=calibration["calibration_id"]))
        if len(errors) == calibration_error_start:
            calibration_payloads[calibration["calibration_id"]] = payload

    for stream in manifest["streams"]:
        if stream["status"] != "captured" or stream["source"] != "imu":
            continue
        artifact = artifact_index.get(stream["artifact_id"])
        path = artifact_paths.get(stream["artifact_id"])
        device_run = device_run_index.get(stream["device_run_id"])
        if artifact is None or path is None or device_run is None:
            continue
        if stream["variant"] in PRECALIBRATION_VARIANTS:
            if stream["variant"] != "uncalibrated_engineering" or stream["record_contract_version"] != IMU_WINDOW_CONTRACT_VERSION:
                errors.append(_issue("imu_precalibration_contract_invalid", "current A0-003 field review accepts only honest imu_window.v1 uncalibrated mg/mdps", stream_id=stream["stream_id"]))
                continue
            try:
                rows = load_jsonl(path)
            except FieldSessionError as error:
                errors.append(_issue("imu_window_content_invalid", str(error), stream_id=stream["stream_id"]))
                continue
            row_errors, windows = _validate_imu_window_rows(rows, stream=stream, device_run=device_run)
            errors.extend(row_errors)
            raw_windows_by_stream[stream["stream_id"]] = windows
        elif stream["variant"] == "calibrated":
            if stream["record_contract_version"] != IMU_FIELD_CALIBRATED_CONTRACT_VERSION:
                errors.append(_issue("imu_calibrated_contract_invalid", "calibrated field IMU stream must use the A0-003 field calibrated-window v0.1 contract", stream_id=stream["stream_id"]))
                continue
            try:
                rows = load_jsonl(path)
            except FieldSessionError as error:
                errors.append(_issue("imu_calibrated_content_invalid", str(error), stream_id=stream["stream_id"]))
                continue
            valid_rows: list[Mapping[str, Any]] = []
            for index, row in enumerate(rows):
                row_issues = _schema_issues(row, calibrated_schema, f"calibrated[{stream['stream_id']}][{index}]")
                errors.extend(row_issues)
                if not row_issues:
                    valid_rows.append(row)
            if stream["observation_count"] != len(rows):
                errors.append(_issue("imu_calibrated_observation_count_mismatch", "calibrated observation_count must equal physical window rows", stream_id=stream["stream_id"]))
            calibrated_rows_by_stream[stream["stream_id"]] = valid_rows

    verified_chain_count = 0
    stream_index = {stream["stream_id"]: stream for stream in manifest["streams"]}
    for stream in manifest["streams"]:
        if stream["status"] != "captured" or stream["source"] != "imu" or stream["variant"] != "calibrated":
            continue
        chain_error_start = len(errors)
        source_stream = stream_index.get(stream["source_stream_id"])
        raw_windows = raw_windows_by_stream.get(stream["source_stream_id"], {})
        calibrated_rows = calibrated_rows_by_stream.get(stream["stream_id"], [])
        calibration_payload = calibration_payloads.get(stream["calibration_id"])
        device_run = device_run_index.get(stream["device_run_id"])
        if source_stream is None or not raw_windows:
            errors.append(_issue("imu_chain_raw_unverified", "calibrated IMU stream has no verified imu_window.v1 source", stream_id=stream["stream_id"]))
        if calibration_payload is None:
            errors.append(_issue("imu_chain_calibration_unverified", "calibrated IMU stream has no verified A0-001 artifact", stream_id=stream["stream_id"]))
        elif device_run is None:
            errors.append(_issue("imu_calibration_device_run_missing", "calibrated stream has no known device run", stream_id=stream["stream_id"]))
        else:
            payload_device = calibration_payload["device"]
            if (
                payload_device["device_id"] != device_run["device_id"]
                or payload_device["board_id"] != device_run["board_id"]
                or payload_device["hardware_revision"] != device_run["hardware_revision"]
            ):
                errors.append(_issue("imu_calibration_hardware_mismatch", "calibration device/board/hardware differs from the field device run", stream_id=stream["stream_id"]))
            if (
                calibration_payload["firmware"]["firmware_commit"] != device_run["firmware_commit"]
                or calibration_payload["firmware"]["fw_version"] != device_run["firmware_version"]
            ):
                errors.append(_issue("imu_calibration_firmware_mismatch", "calibration firmware differs from the field device run", stream_id=stream["stream_id"]))
        if source_stream is not None and raw_windows:
            source_artifact = artifact_index.get(source_stream["artifact_id"])
            calibrated_window_ids: set[str] = set()
            for row in calibrated_rows:
                source_window = row["source_window"]
                window_id = source_window["window_id"]
                raw_window = raw_windows.get(window_id)
                if raw_window is None:
                    errors.append(_issue("imu_calibrated_source_window_missing", "calibrated row references no preserved raw window", stream_id=stream["stream_id"], window_id=window_id))
                    continue
                if window_id in calibrated_window_ids:
                    errors.append(_issue("imu_calibrated_source_window_duplicate", "calibrated source window is duplicated", stream_id=stream["stream_id"], window_id=window_id))
                calibrated_window_ids.add(window_id)
                expected_source = {
                    "contract_version": IMU_WINDOW_CONTRACT_VERSION,
                    "window_id": raw_window.get("window_id"),
                    "capture_cmd_id": raw_window.get("capture_cmd_id"),
                    "test_run_id": raw_window.get("test_run_id"),
                    "transport_type": raw_window.get("transport_type"),
                    "samples_sha256": str(raw_window.get("samples_sha256", "")).lower(),
                    "source_artifact_sha256": source_artifact["sha256"].lower() if source_artifact is not None else None,
                    "time_basis": raw_window.get("capture_time_basis"),
                }
                if {
                    **source_window,
                    "samples_sha256": source_window["samples_sha256"].lower(),
                    "source_artifact_sha256": source_window["source_artifact_sha256"].lower(),
                } != expected_source:
                    errors.append(_issue("imu_calibrated_source_hash_mismatch", "calibrated row does not bind the exact preserved uncalibrated window/export", stream_id=stream["stream_id"], window_id=window_id))
                if calibration_payload is not None and (
                    row["calibration_id"] != calibration_payload["calibration_id"]
                    or row["calibration_identity_sha256"].lower() != calibration_payload["identity_sha256"].lower()
                ):
                    errors.append(_issue("imu_calibrated_identity_mismatch", "calibrated row does not bind the named calibration identity", stream_id=stream["stream_id"], window_id=window_id))
                if row["field_session_id"] != manifest["session_id"]:
                    errors.append(_issue("imu_calibrated_session_mismatch", "calibrated row belongs to another Field Session", stream_id=stream["stream_id"], window_id=window_id))
                if calibration_payload is not None:
                    accel_bias = calibration_payload["accelerometer"]["bias_mg_xyz"]
                    accel_gain = calibration_payload["accelerometer"]["correction_gain_xyz"]
                    gyro_bias = calibration_payload["gyroscope"]["bias_mdps_xyz"]
                    raw_samples = raw_window.get("samples") if isinstance(raw_window.get("samples"), list) else []
                    if len(row["samples"]) != len(raw_samples):
                        errors.append(_issue("imu_calibrated_sample_count_mismatch", "calibrated and uncalibrated sample counts differ", stream_id=stream["stream_id"], window_id=window_id))
                    for sample_index, (calibrated_sample, raw_sample) in enumerate(zip(row["samples"], raw_samples)):
                        raw_accel = raw_sample.get("accel_mg")
                        raw_gyro = raw_sample.get("gyro_mdps")
                        expected_accel = [
                            _round_physical((raw_accel[axis] - accel_bias[axis]) * accel_gain[axis])
                            for axis in range(3)
                        ]
                        expected_gyro = [
                            _round_physical(raw_gyro[axis] - gyro_bias[axis])
                            for axis in range(3)
                        ]
                        expected_calibrated = {
                            "accel_mg": expected_accel,
                            "gyro_mdps": expected_gyro,
                            "accel_m_s2": [_round_physical(value * MG_TO_M_S2) for value in expected_accel],
                            "gyro_rad_s": [_round_physical(value * MDPS_TO_RAD_S) for value in expected_gyro],
                        }
                        if (
                            calibrated_sample["index"] != raw_sample.get("index")
                            or calibrated_sample["offset_us"] != raw_sample.get("offset_us")
                            or calibrated_sample["uncalibrated"] != {"accel_mg": raw_accel, "gyro_mdps": raw_gyro}
                            or calibrated_sample["calibrated"] != expected_calibrated
                        ):
                            errors.append(_issue("imu_calibrated_sample_mismatch", "calibrated sample is not a deterministic transform of preserved source values", stream_id=stream["stream_id"], window_id=window_id, sample_index=sample_index))
                            break
            if set(raw_windows) != calibrated_window_ids:
                errors.append(_issue("imu_calibrated_window_set_mismatch", "calibrated rows must cover exactly the preserved uncalibrated windows", stream_id=stream["stream_id"]))
        calibration = next((item for item in manifest["calibrations"] if item["calibration_id"] == stream["calibration_id"]), None)
        generator = stream["generator"]
        if (
            generator is None
            or calibration is None
            or generator["config_artifact_id"] != calibration["artifact_id"]
            or generator["source_stream_ids"] != [stream["source_stream_id"]]
        ):
            errors.append(_issue("imu_generator_calibration_binding_missing", "field calibration generator must cite the exact A0-001 artifact", stream_id=stream["stream_id"]))
        elif generator["commit"] is None:
            errors.append(_issue("imu_generator_commit_missing", "field calibration generator must record its implementation commit", stream_id=stream["stream_id"]))
        if len(errors) == chain_error_start:
            verified_chain_count += 1
    return errors, verified_chain_count > 0 and not errors


def _validate_manual_events(
    rows: list[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    stream: Mapping[str, Any],
    mappings: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[Mapping[str, Any]]]:
    schema = _load_schema(MANUAL_EVENT_SCHEMA_PATH)
    errors: list[dict[str, Any]] = []
    valid_rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        issues = _schema_issues(row, schema, f"manual_event[{index}]")
        errors.extend(issues)
        if not issues:
            valid_rows.append(row)
    for event_id in sorted(_duplicates(str(row["event_id"]) for row in valid_rows)):
        errors.append(_issue("manual_event_id_duplicate", "event_id must be unique", event_id=event_id))
    for sequence_id in sorted(_duplicates(str(row["sequence_id"]) for row in valid_rows)):
        errors.append(_issue("manual_event_sequence_duplicate", "manual event sequence_id must be unique", sequence_id=sequence_id))

    capture_start = manifest["capture_interval"]["start_utc"]
    capture_end = manifest["capture_interval"]["end_utc"]
    capture_start_ns = parse_utc_ns(capture_start, "capture.start_utc") if capture_start else None
    capture_end_ns = parse_utc_ns(capture_end, "capture.end_utc") if capture_end else None
    device_run_index = {run["device_run_id"]: run for run in manifest["device_runs"]}
    last_sequence: int | None = None
    for row in valid_rows:
        event_id = row["event_id"]
        if row["session_id"] != manifest["session_id"]:
            errors.append(_issue("manual_event_session_mismatch", "manual event belongs to another session", event_id=event_id))
        if row["operator_ref"] != manifest["scenario"]["operator_ref"]:
            errors.append(_issue("manual_event_operator_mismatch", "manual event operator_ref differs from the manifest", event_id=event_id))
        device_run = device_run_index.get(row["device_run_id"]) if row["device_run_id"] is not None else None
        if device_run is None:
            errors.append(_issue("manual_event_device_run_missing", "captured manual event requires a known producer device run", event_id=event_id))
        elif row["device_run_id"] != stream["device_run_id"]:
            errors.append(_issue("manual_event_stream_device_mismatch", "manual event producer differs from its single stream segment", event_id=event_id, stream_id=stream["stream_id"]))
        if stream["clock_domain_id"] is not None and row["monotonic_clock_domain_id"] != stream["clock_domain_id"]:
            errors.append(_issue("manual_event_stream_clock_mismatch", "manual event clock differs from its single stream segment", event_id=event_id, stream_id=stream["stream_id"]))
        source_timestamp = row["source_timestamp"]
        if source_timestamp["unit"] == "unavailable":
            if any(source_timestamp[key] is not None for key in ("raw_value", "clock_domain_id", "source_field")):
                errors.append(_issue("manual_event_unavailable_source_populated", "unavailable source timestamp must keep value/domain/field null", event_id=event_id))
        elif source_timestamp["raw_value"] is None or source_timestamp["clock_domain_id"] is None or source_timestamp["source_field"] is None:
            errors.append(_issue("manual_event_source_timestamp_incomplete", "available source timestamp requires value, clock domain, and field provenance", event_id=event_id))
        if row["timestamp_monotonic_ns"] is not None:
            if row["monotonic_clock_domain_id"] is None or row["boot_count"] is None or device_run is None:
                errors.append(_issue("manual_event_monotonic_lineage_missing", "monotonic time requires device run, clock domain, and boot_count", event_id=event_id))
            elif row["boot_count"] != device_run["boot_count"] or row["monotonic_clock_domain_id"] not in device_run["monotonic_clock_domain_ids"]:
                errors.append(_issue("manual_event_monotonic_lineage_mismatch", "manual event clock/boot differs from its device run", event_id=event_id))
            if row["timestamp_monotonic_origin"] != "producer_clock":
                errors.append(_issue("manual_event_monotonic_origin_invalid", "monotonic event time must originate from the producer clock", event_id=event_id))
            try:
                expected_monotonic = source_value_monotonic_ns(source_timestamp)
            except SensorTimeLineageError as error:
                errors.append(_issue("manual_event_source_timestamp_invalid", str(error), event_id=event_id))
            else:
                if expected_monotonic != row["timestamp_monotonic_ns"]:
                    errors.append(_issue("manual_event_monotonic_source_mismatch", "event monotonic time differs from source timestamp", event_id=event_id))
                if source_timestamp["clock_domain_id"] != row["monotonic_clock_domain_id"]:
                    errors.append(_issue("manual_event_source_clock_mismatch", "source timestamp clock differs from event monotonic clock", event_id=event_id))
        elif "monotonic_unavailable" not in row["reason_codes"]:
            errors.append(_issue("manual_event_monotonic_reason_missing", "missing monotonic time requires monotonic_unavailable", event_id=event_id))
        elif row["timestamp_monotonic_origin"] != "unavailable":
            errors.append(_issue("manual_event_monotonic_origin_invalid", "missing monotonic time requires unavailable origin", event_id=event_id))
        if row["timestamp_utc"] is not None:
            try:
                event_utc_ns = parse_utc_ns(row["timestamp_utc"], f"manual_event[{event_id}].timestamp_utc")
            except SensorTimeLineageError as error:
                errors.append(_issue("manual_event_utc_invalid", str(error), event_id=event_id))
            else:
                if row["timestamp_uncertainty_ns"] is None:
                    errors.append(_issue("manual_event_uncertainty_missing", "UTC event time requires uncertainty", event_id=event_id))
                if capture_start_ns is not None and event_utc_ns < capture_start_ns:
                    errors.append(_issue("manual_event_outside_session", "event precedes capture interval", event_id=event_id))
                if capture_end_ns is not None and event_utc_ns > capture_end_ns:
                    errors.append(_issue("manual_event_outside_session", "event follows capture interval", event_id=event_id))
                if row["timestamp_utc_origin"] == "source_timestamp":
                    if source_timestamp["unit"] != "iso8601" or source_timestamp["raw_value"] is None:
                        errors.append(_issue("manual_event_direct_utc_source_invalid", "direct UTC requires an ISO-8601 source timestamp", event_id=event_id))
                    else:
                        try:
                            source_utc_ns = parse_utc_ns(source_timestamp["raw_value"], "manual_event.source_timestamp")
                        except SensorTimeLineageError as error:
                            errors.append(_issue("manual_event_direct_utc_source_invalid", str(error), event_id=event_id))
                        else:
                            if source_utc_ns != event_utc_ns:
                                errors.append(_issue("manual_event_direct_utc_mismatch", "event UTC differs from source timestamp", event_id=event_id))
                elif row["timestamp_utc_origin"] == "clock_mapping":
                    mapping = mappings.get(row["mapping_id"])
                    if mapping is None or row["timestamp_monotonic_ns"] is None:
                        errors.append(_issue("manual_event_mapping_missing", "mapped event UTC requires mapping and monotonic time", event_id=event_id))
                    else:
                        mapping_lineage = mapping.get("lineage") if isinstance(mapping.get("lineage"), Mapping) else {}
                        if (
                            mapping.get("device_id") != (device_run["device_id"] if device_run is not None else None)
                            or mapping.get("boot_count") != row["boot_count"]
                            or mapping.get("monotonic_clock_domain_id") != row["monotonic_clock_domain_id"]
                            or mapping_lineage.get("field_session_id") != manifest["session_id"]
                        ):
                            errors.append(_issue("manual_event_mapping_scope_mismatch", "event mapping differs from session/device/boot/clock scope", event_id=event_id))
                        try:
                            mapped_utc_ns = apply_clock_mapping(mapping, row["timestamp_monotonic_ns"])
                        except (SensorTimeLineageError, KeyError, TypeError, ValueError, ArithmeticError) as error:
                            errors.append(_issue("manual_event_mapping_invalid", str(error), event_id=event_id))
                        else:
                            if mapped_utc_ns != event_utc_ns:
                                errors.append(_issue("manual_event_mapped_utc_mismatch", "event UTC differs from the named mapping", event_id=event_id))
                        mapping_uncertainty = mapping.get("uncertainty_ns")
                        if not isinstance(mapping_uncertainty, int) or isinstance(mapping_uncertainty, bool):
                            errors.append(_issue("manual_event_mapping_invalid", "mapping uncertainty is not a non-negative integer", event_id=event_id))
                        elif row["timestamp_uncertainty_ns"] is not None and row["timestamp_uncertainty_ns"] < mapping_uncertainty:
                            errors.append(_issue("manual_event_uncertainty_too_small", "event uncertainty is below its clock mapping uncertainty", event_id=event_id))
                else:
                    errors.append(_issue("manual_event_utc_origin_invalid", "present UTC requires source_timestamp or clock_mapping origin", event_id=event_id))
        elif "utc_unavailable" not in row["reason_codes"]:
            errors.append(_issue("manual_event_utc_reason_missing", "missing UTC requires utc_unavailable", event_id=event_id))
        elif row["timestamp_utc_origin"] != "unavailable":
            errors.append(_issue("manual_event_utc_origin_invalid", "missing UTC requires unavailable origin", event_id=event_id))
        receive_ns: int | None = None
        ingest_ns: int | None = None
        for field_name in ("receive_timestamp_utc", "ingest_timestamp_utc"):
            if row[field_name] is None:
                continue
            try:
                parsed = parse_utc_ns(row[field_name], f"manual_event[{event_id}].{field_name}")
            except SensorTimeLineageError as error:
                errors.append(_issue("manual_event_transport_utc_invalid", str(error), event_id=event_id))
            else:
                if field_name == "receive_timestamp_utc":
                    receive_ns = parsed
                else:
                    ingest_ns = parsed
        if receive_ns is not None and ingest_ns is not None and ingest_ns < receive_ns:
            errors.append(_issue("manual_event_ingest_before_receive", "ingest time precedes receive time", event_id=event_id))
        if row["alignment_status"] == "verified":
            if row["timestamp_monotonic_ns"] is None or row["timestamp_utc"] is None or row["mapping_id"] is None:
                errors.append(_issue("manual_event_verified_alignment_incomplete", "verified event alignment requires monotonic, UTC, and mapping_id", event_id=event_id))
            elif row["mapping_id"] not in mappings:
                errors.append(_issue("manual_event_mapping_missing", "manual event mapping_id is absent from the session mappings", event_id=event_id))
            elif mappings[row["mapping_id"]].get("status") != "verified":
                errors.append(_issue("manual_event_mapping_not_verified", "verified event requires a verified clock mapping", event_id=event_id))
        elif row["alignment_status"] != "estimated" and row["mapping_id"] is not None:
            errors.append(_issue("manual_event_unverified_mapping_claim", "only verified manual-event alignment may cite mapping_id", event_id=event_id))
        if row["alignment_status"] in {"estimated", "verified"} and row["timestamp_uncertainty_ns"] is None:
            errors.append(_issue("manual_event_alignment_uncertainty_missing", "estimated/verified alignment requires uncertainty", event_id=event_id))
        if row["alignment_status"] == "receive_only":
            if row["receive_timestamp_utc"] is None:
                errors.append(_issue("manual_event_receive_time_missing", "receive_only event requires receive_timestamp_utc", event_id=event_id))
            if row["timestamp_monotonic_ns"] is not None or row["timestamp_utc"] is not None or row["mapping_id"] is not None:
                errors.append(_issue("manual_event_receive_time_promoted", "receive-only time cannot populate event source timestamps", event_id=event_id))
        if row["alignment_status"] == "unavailable" and row["receive_timestamp_utc"] is None:
            errors.append(_issue("manual_event_time_unavailable", "manual event must preserve source or receive time", event_id=event_id))
        if row["event_type"] == "OTHER" and not str(row["note"] or "").strip():
            errors.append(_issue("manual_event_other_note_missing", "OTHER event requires a note", event_id=event_id))
        if last_sequence is not None and row["sequence_id"] <= last_sequence:
            errors.append(_issue("manual_event_sequence_regression", "manual event sequence must increase in file order", event_id=event_id))
        last_sequence = row["sequence_id"]
    return errors, valid_rows


def _manifest_semantics(manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    session_id = manifest["session_id"]

    try:
        created_ns = parse_utc_ns(manifest["created_at_utc"], "created_at_utc")
    except SensorTimeLineageError as error:
        errors.append(_issue("created_at_invalid", str(error)))
        created_ns = None
    interval = manifest["capture_interval"]
    start_ns: int | None = None
    end_ns: int | None = None
    for key in ("start_utc", "end_utc"):
        if interval[key] is not None:
            try:
                parsed = parse_utc_ns(interval[key], f"capture_interval.{key}")
            except SensorTimeLineageError as error:
                errors.append(_issue("capture_time_invalid", str(error)))
            else:
                if key == "start_utc":
                    start_ns = parsed
                else:
                    end_ns = parsed
    if (interval["start_utc"] is None) != (interval["end_utc"] is None):
        errors.append(_issue("capture_interval_partial", "capture start and end must be set together"))
    if start_ns is not None and end_ns is not None and end_ns < start_ns:
        errors.append(_issue("capture_interval_inverted", "capture end precedes capture start"))
    if manifest["lifecycle_state"] == "complete" and (start_ns is None or end_ns is None):
        errors.append(_issue("complete_capture_interval_missing", "complete session requires capture start and end"))
    if created_ns is None:
        warnings.append(_issue("created_at_unavailable", "manifest creation time could not be evaluated"))

    seal = manifest["seal"]
    if seal["status"] == "unsealed":
        if any(
            seal[key] is not None
            for key in ("sealed_at_utc", "sealed_by", "manifest_core_sha256", "artifact_set_sha256")
        ):
            errors.append(_issue("unsealed_manifest_has_seal_values", "unsealed manifest must keep all seal values null"))
    else:
        if manifest["lifecycle_state"] != "complete":
            errors.append(_issue("sealed_session_not_complete", "only a complete session may be sealed"))
        if any(
            seal[key] is None
            for key in ("sealed_at_utc", "sealed_by", "manifest_core_sha256", "artifact_set_sha256")
        ):
            errors.append(_issue("sealed_manifest_incomplete", "sealed manifest requires time, actor, manifest hash, and artifact-set hash"))
        else:
            try:
                sealed_at_ns = parse_utc_ns(seal["sealed_at_utc"], "seal.sealed_at_utc")
            except SensorTimeLineageError as error:
                errors.append(_issue("seal_time_invalid", str(error)))
            else:
                if created_ns is not None and sealed_at_ns < created_ns:
                    errors.append(_issue("seal_before_manifest_created", "seal time precedes manifest creation"))
                if end_ns is not None and sealed_at_ns < end_ns:
                    errors.append(_issue("seal_before_capture_end", "seal time precedes capture end"))
            if not str(seal["sealed_by"]).strip():
                errors.append(_issue("seal_actor_missing", "sealed_by must identify a non-empty actor/ref"))
            expected_artifact_set = artifact_set_sha256(manifest)
            if seal["artifact_set_sha256"].lower() != expected_artifact_set:
                errors.append(_issue("artifact_set_seal_mismatch", "artifact inventory differs from the sealed artifact-set hash"))
            expected_manifest = manifest_core_sha256(manifest)
            if seal["manifest_core_sha256"].lower() != expected_manifest:
                errors.append(_issue("manifest_seal_mismatch", "manifest content differs from the sealed core hash"))

    artifacts = manifest["artifacts"]
    for duplicate in sorted(_duplicates(str(item["artifact_id"]) for item in artifacts)):
        errors.append(_issue("artifact_id_duplicate", "artifact_id must be unique", artifact_id=duplicate))
    for duplicate in sorted(_duplicates(str(item["path"]) for item in artifacts)):
        errors.append(_issue("artifact_path_duplicate", "artifact path must be unique", artifact_ref=duplicate))
    artifact_index = {item["artifact_id"]: item for item in artifacts}
    hash_paths: dict[str, str] = {}
    part_groups: dict[str, list[Mapping[str, Any]]] = {}
    for artifact in artifacts:
        digest = artifact["sha256"].lower()
        prior_path = hash_paths.get(digest)
        if prior_path is not None and prior_path != artifact["path"]:
            errors.append(_issue("artifact_hash_reused", "one content hash is declared under multiple paths", artifact_id=artifact["artifact_id"], prior_artifact_ref=prior_path))
        else:
            hash_paths[digest] = artifact["path"]
        part_values = (artifact["part_group"], artifact["part_index"], artifact["part_count"])
        if any(value is not None for value in part_values) and any(value is None for value in part_values):
            errors.append(_issue("artifact_part_metadata_partial", "part_group, part_index, and part_count must be set together", artifact_id=artifact["artifact_id"]))
        if all(value is not None for value in part_values):
            part_groups.setdefault(artifact["part_group"], []).append(artifact)
        if artifact["format"] == "jsonl" and artifact["media_type"] != "application/x-ndjson":
            errors.append(_issue("artifact_media_type_mismatch", "jsonl artifact must use application/x-ndjson", artifact_id=artifact["artifact_id"]))
        if artifact["format"] == "json" and artifact["media_type"] != "application/json":
            errors.append(_issue("artifact_media_type_mismatch", "json artifact must use application/json", artifact_id=artifact["artifact_id"]))
        if artifact["format"] != "jsonl" and artifact["record_count"] is not None:
            errors.append(_issue("unsupported_physical_record_count", "v0.1 verifies record_count only for JSONL artifacts", artifact_id=artifact["artifact_id"]))
        if artifact["role"] == "raw_media":
            if (
                artifact["format"] != "jpeg"
                or artifact["media_type"] != "image/jpeg"
                or artifact["privacy_class"] != "private_media"
            ):
                errors.append(_issue("raw_media_contract_invalid", "v0.1 raw media is limited to private JPEG camera evidence", artifact_id=artifact["artifact_id"]))
        if artifact["privacy_class"] == "private_media" and artifact["role"] != "raw_media":
            errors.append(_issue("private_media_role_invalid", "private media must use role=raw_media", artifact_id=artifact["artifact_id"]))
        if (
            (artifact["media_type"].startswith("image/") or artifact["media_type"].startswith("audio/"))
            and artifact["role"] != "raw_media"
        ):
            errors.append(_issue("media_role_mismatch", "image/audio media cannot be disguised under a non-media role", artifact_id=artifact["artifact_id"]))
        if artifact["format"] == "binary" and artifact["media_type"] != "application/octet-stream":
            errors.append(_issue("binary_media_type_invalid", "binary attachments must use application/octet-stream", artifact_id=artifact["artifact_id"]))
    for group, parts in part_groups.items():
        declared_counts = {part["part_count"] for part in parts}
        indexes = sorted(part["part_index"] for part in parts)
        if len(declared_counts) != 1 or indexes != list(range(next(iter(declared_counts)))):
            errors.append(_issue("artifact_part_set_incomplete", "part group must contain each zero-based part exactly once", part_group=group))

    device_runs = manifest["device_runs"]
    for duplicate in sorted(_duplicates(str(item["device_run_id"]) for item in device_runs)):
        errors.append(_issue("device_run_id_duplicate", "device_run_id must be unique", device_run_id=duplicate))
    device_run_index = {item["device_run_id"]: item for item in device_runs}
    device_ids = {item["device_id"] for item in device_runs}
    if manifest["primary_device_id"] not in device_ids:
        errors.append(_issue("primary_device_missing", "primary_device_id is not present in device_runs"))
    for run in device_runs:
        if run["boot_count"] is None and run["monotonic_clock_domain_ids"]:
            errors.append(_issue("device_boot_missing", "clock domains require a boot_count", device_run_id=run["device_run_id"]))
        if run["boot_count"] is not None and not run["monotonic_clock_domain_ids"]:
            warnings.append(_issue("device_clock_domain_missing", "boot_count is present but no monotonic clock domain is declared", device_run_id=run["device_run_id"]))
    clock_scope_owners: dict[tuple[str, int, str], str] = {}
    device_boot_owners: dict[tuple[str, int], str] = {}
    for run in device_runs:
        if run["boot_count"] is None:
            continue
        boot_scope = (run["device_id"], run["boot_count"])
        prior_run = device_boot_owners.get(boot_scope)
        if prior_run is not None and prior_run != run["device_run_id"]:
            errors.append(_issue("device_boot_scope_duplicate", "one device boot must be represented by exactly one device run", device_run_id=run["device_run_id"]))
        device_boot_owners[boot_scope] = run["device_run_id"]
        for domain_id in run["monotonic_clock_domain_ids"]:
            scope = (run["device_id"], run["boot_count"], domain_id)
            prior = clock_scope_owners.get(scope)
            if prior is not None and prior != run["device_run_id"]:
                errors.append(_issue("device_clock_scope_duplicate", "device/boot/clock scope belongs to more than one device run", device_run_id=run["device_run_id"], clock_domain_id=domain_id))
            clock_scope_owners[scope] = run["device_run_id"]

    calibrations = manifest["calibrations"]
    for duplicate in sorted(_duplicates(str(item["calibration_id"]) for item in calibrations)):
        errors.append(_issue("calibration_id_duplicate", "calibration_id must be unique", calibration_id=duplicate))
    calibration_index = {item["calibration_id"]: item for item in calibrations}
    for calibration in calibrations:
        if calibration["device_id"] not in device_ids:
            errors.append(_issue("calibration_device_missing", "calibration references an unknown device", calibration_id=calibration["calibration_id"]))
        artifact = artifact_index.get(calibration["artifact_id"])
        if artifact is None:
            errors.append(_issue("calibration_artifact_missing", "calibration references an unknown artifact", calibration_id=calibration["calibration_id"]))
        elif artifact["role"] != "calibration":
            errors.append(_issue("calibration_artifact_role_invalid", "calibration artifact must use role=calibration", calibration_id=calibration["calibration_id"]))

    streams = manifest["streams"]
    for duplicate in sorted(_duplicates(str(item["stream_id"]) for item in streams)):
        errors.append(_issue("stream_id_duplicate", "stream_id must be unique", stream_id=duplicate))
    stream_index = {item["stream_id"]: item for item in streams}
    declared_sources = {item["source"] for item in streams}
    for source in SOURCE_TYPES:
        if source not in declared_sources:
            errors.append(_issue("source_not_declared", "source must be explicitly captured, unavailable, or not requested", source=source))

    profile = manifest["capture_profile"]
    overlap = sorted(set(profile["required_sources"]) & set(profile["optional_sources"]))
    if overlap:
        errors.append(_issue("capture_profile_source_overlap", f"sources cannot be both required and optional: {overlap}"))

    stream_artifact_ids: dict[str, str] = {}
    for stream in streams:
        stream_id = stream["stream_id"]
        status = stream["status"]
        artifact_id = stream["artifact_id"]
        artifact = artifact_index.get(artifact_id) if artifact_id is not None else None
        bounds = stream["bounds"]
        if status == "captured":
            if artifact is None or stream["format"] is None or stream["record_contract_version"] is None:
                errors.append(_issue("captured_stream_artifact_missing", "captured stream requires format, contract, and artifact", stream_id=stream_id))
            elif artifact["record_count"] is None or artifact["record_count"] < 1:
                errors.append(_issue("captured_stream_empty", "captured stream requires a positive record_count", stream_id=stream_id))
            if stream["observation_count"] is None or stream["observation_count"] < 1:
                errors.append(_issue("captured_stream_observations_missing", "captured stream requires a positive observation_count", stream_id=stream_id))
            if artifact is not None:
                if artifact["role"] != "stream_data":
                    errors.append(_issue("stream_artifact_role_invalid", "captured stream artifact must use role=stream_data", stream_id=stream_id))
                if artifact["format"] != "jsonl" or stream["format"] != "jsonl":
                    errors.append(_issue("stream_format_unsupported", "A0-003 v0.1 captured streams must use verifiable JSONL", stream_id=stream_id))
                if artifact["content_contract_version"] != stream["record_contract_version"]:
                    errors.append(_issue("stream_artifact_contract_mismatch", "stream and artifact record contracts differ", stream_id=stream_id))
                previous = stream_artifact_ids.get(artifact["artifact_id"])
                if previous is not None and previous != stream_id:
                    errors.append(_issue("stream_artifact_reused", "one source artifact cannot back multiple streams", stream_id=stream_id, artifact_id=artifact["artifact_id"]))
                stream_artifact_ids[artifact["artifact_id"]] = stream_id
            if stream["source"] not in {"manual_event", "label"} and stream["device_run_id"] is None:
                errors.append(_issue("captured_stream_device_missing", "captured sensor stream requires one device_run_id", stream_id=stream_id))
            if bounds["sequence_first"] is None or bounds["sequence_last"] is None:
                errors.append(_issue("captured_stream_sequence_bounds_missing", "captured stream requires exact sequence bounds", stream_id=stream_id))
        else:
            if artifact_id is not None:
                errors.append(_issue("unavailable_stream_has_artifact", "unavailable/not-requested stream cannot claim an artifact", stream_id=stream_id))
            if not stream["reason_codes"]:
                errors.append(_issue("unavailable_stream_reason_missing", "unavailable/not-requested stream requires a reason", stream_id=stream_id))
            if any(value is not None for value in bounds.values()):
                errors.append(_issue("unavailable_stream_has_bounds", "unavailable/not-requested stream cannot claim time or sequence bounds", stream_id=stream_id))
            if stream["observation_count"] is not None:
                errors.append(_issue("unavailable_stream_has_observations", "unavailable/not-requested stream cannot claim observations", stream_id=stream_id))

        device_run_id = stream["device_run_id"]
        device_run = device_run_index.get(device_run_id) if device_run_id is not None else None
        if device_run_id is not None and device_run is None:
            errors.append(_issue("stream_device_run_missing", "stream references an unknown device_run_id", stream_id=stream_id, device_run_id=device_run_id))
        clock_domain_id = stream["clock_domain_id"]
        if clock_domain_id is not None and (device_run is None or clock_domain_id not in device_run["monotonic_clock_domain_ids"]):
            errors.append(_issue("stream_clock_domain_missing", "stream clock domain is absent from its single device run", stream_id=stream_id, clock_domain_id=clock_domain_id))

        for first_key, last_key, code in (
            ("sequence_first", "sequence_last", "stream_sequence_bounds_inverted"),
            ("monotonic_start_ns", "monotonic_end_ns", "stream_monotonic_bounds_inverted"),
        ):
            first = bounds[first_key]
            last = bounds[last_key]
            if first is not None and last is not None and last < first:
                errors.append(_issue(code, f"{last_key} precedes {first_key}", stream_id=stream_id))
        if (bounds["utc_start"] is None) != (bounds["utc_end"] is None):
            errors.append(_issue("stream_utc_bounds_partial", "stream UTC start and end must be set together", stream_id=stream_id))
        if bounds["utc_start"] is not None and bounds["utc_end"] is not None:
            try:
                stream_start_ns = parse_utc_ns(bounds["utc_start"], f"stream[{stream_id}].utc_start")
                stream_end_ns = parse_utc_ns(bounds["utc_end"], f"stream[{stream_id}].utc_end")
            except SensorTimeLineageError as error:
                errors.append(_issue("stream_utc_invalid", str(error), stream_id=stream_id))
            else:
                if stream_end_ns < stream_start_ns:
                    errors.append(_issue("stream_utc_bounds_inverted", "stream UTC end precedes start", stream_id=stream_id))
                if start_ns is not None and stream_start_ns < start_ns:
                    errors.append(_issue("stream_outside_session", "stream starts before capture interval", stream_id=stream_id))
                if end_ns is not None and stream_end_ns > end_ns:
                    errors.append(_issue("stream_outside_session", "stream ends after capture interval", stream_id=stream_id))

        if stream["variant"] == "calibrated":
            if stream["calibration_id"] is None or stream["source_stream_id"] is None or stream["raw_preserved"] is not True:
                errors.append(_issue("calibrated_stream_lineage_missing", "calibrated stream requires calibration_id, source_stream_id, and raw_preserved=true", stream_id=stream_id))
            if stream["generator"] is None:
                errors.append(_issue("calibrated_stream_generator_missing", "calibrated stream requires generator provenance", stream_id=stream_id))
        elif stream["calibration_id"] is not None or stream["source_stream_id"] is not None:
            errors.append(_issue("noncalibrated_stream_has_calibration_lineage", "only calibrated streams use calibration_id/source_stream_id", stream_id=stream_id))
        if stream["variant"] == "derived":
            if stream["generator"] is None or not stream["generator"]["source_stream_ids"]:
                errors.append(_issue("derived_stream_generator_missing", "derived stream requires generator and source streams", stream_id=stream_id))
        elif stream["variant"] != "calibrated" and stream["generator"] is not None:
            errors.append(_issue("nonderived_stream_has_generator", "generator is reserved for calibrated or derived streams", stream_id=stream_id))
        if stream["generator"] is not None:
            for parent_id in stream["generator"]["source_stream_ids"]:
                if parent_id not in stream_index:
                    errors.append(_issue("generator_source_stream_missing", "generator references an unknown source stream", stream_id=stream_id, source_stream_id=parent_id))
            config_artifact_id = stream["generator"]["config_artifact_id"]
            if config_artifact_id is not None:
                config_artifact = artifact_index.get(config_artifact_id)
                if config_artifact is None:
                    errors.append(_issue("generator_config_artifact_missing", "generator references an unknown config artifact", stream_id=stream_id, artifact_id=config_artifact_id))
                elif stream["variant"] == "calibrated":
                    calibration = calibration_index.get(stream["calibration_id"])
                    if (
                        config_artifact["role"] != "calibration"
                        or calibration is None
                        or calibration["artifact_id"] != config_artifact_id
                    ):
                        errors.append(_issue("generator_config_artifact_role_invalid", "calibrated generator must cite its calibration artifact", stream_id=stream_id, artifact_id=config_artifact_id))
                elif config_artifact["role"] != "policy":
                    errors.append(_issue("generator_config_artifact_role_invalid", "derived generator config artifact must use role=policy", stream_id=stream_id, artifact_id=config_artifact_id))

    for stream in streams:
        if stream["variant"] != "calibrated" or stream["calibration_id"] is None or stream["source_stream_id"] is None:
            continue
        source_stream = stream_index.get(stream["source_stream_id"])
        calibration = calibration_index.get(stream["calibration_id"])
        if source_stream is None:
            errors.append(_issue("calibrated_source_stream_missing", "calibrated stream references an unknown source stream", stream_id=stream["stream_id"]))
        elif (
            source_stream["status"] != "captured"
            or source_stream["artifact_id"] is None
            or source_stream["source"] != stream["source"]
            or source_stream["variant"] not in PRECALIBRATION_VARIANTS
        ):
            errors.append(_issue("calibrated_source_stream_invalid", "calibrated stream must reference a pre-calibration stream of the same source", stream_id=stream["stream_id"]))
        elif (
            source_stream["device_run_id"] != stream["device_run_id"]
            or source_stream["clock_domain_id"] != stream["clock_domain_id"]
        ):
            errors.append(_issue("calibrated_source_scope_mismatch", "pre-calibration and calibrated streams must share device run and clock domain", stream_id=stream["stream_id"]))
        if calibration is None:
            errors.append(_issue("calibration_binding_missing", "calibrated stream references an unknown calibration", stream_id=stream["stream_id"]))
        elif stream["stream_id"] not in calibration["applies_to_stream_ids"]:
            errors.append(_issue("calibration_application_missing", "calibration does not list the calibrated stream", stream_id=stream["stream_id"]))
        else:
            device_run = device_run_index.get(stream["device_run_id"])
            if device_run is None or calibration["device_id"] != device_run["device_id"]:
                errors.append(_issue("calibration_stream_device_mismatch", "calibration device differs from the calibrated stream device", stream_id=stream["stream_id"]))
        if stream["generator"] is not None and set(stream["generator"]["source_stream_ids"]) != {stream["source_stream_id"]}:
            errors.append(_issue("calibrated_generator_source_mismatch", "calibrated generator must name exactly its source_stream_id", stream_id=stream["stream_id"]))

    for calibration in calibrations:
        for stream_id in calibration["applies_to_stream_ids"]:
            if stream_id not in stream_index:
                errors.append(_issue("calibration_stream_missing", "calibration references an unknown stream", calibration_id=calibration["calibration_id"], stream_id=stream_id))

    for policy_name, policy in manifest["sensor_policies"].items():
        artifact_id = policy["config_artifact_id"]
        if artifact_id is not None:
            artifact = artifact_index.get(artifact_id)
            if artifact is None:
                errors.append(_issue("policy_artifact_missing", "policy references an unknown artifact", policy=policy_name, artifact_id=artifact_id))
            elif artifact["role"] != "policy":
                errors.append(_issue("policy_artifact_role_invalid", "policy artifact must use role=policy", policy=policy_name, artifact_id=artifact_id))
    for position, measurement in manifest["battery"].items():
        if measurement["value"] is None and measurement["unit"] != "unavailable":
            errors.append(_issue("battery_unit_without_value", "missing battery value must use unavailable unit", position=position))
        if measurement["value"] is not None and measurement["unit"] == "unavailable":
            errors.append(_issue("battery_value_unit_missing", "battery value requires a physical unit", position=position))

    privacy = manifest["privacy"]
    review_fields = (privacy["reviewed_by"], privacy["reviewed_at_utc"])
    if privacy["privacy_review_status"] == "approved" and any(value is None for value in review_fields):
        errors.append(_issue("privacy_review_provenance_missing", "approved privacy review requires reviewer and time"))
    if privacy["reviewed_at_utc"] is not None:
        try:
            parse_utc_ns(privacy["reviewed_at_utc"], "privacy.reviewed_at_utc")
        except SensorTimeLineageError as error:
            errors.append(_issue("privacy_review_time_invalid", str(error)))
    consent_artifact_id = privacy["consent_artifact_id"]
    consent_artifact = artifact_index.get(consent_artifact_id) if consent_artifact_id is not None else None
    if privacy["consent_status"] == "allowed":
        if consent_artifact is None:
            errors.append(_issue("consent_evidence_missing", "allowed collection requires an immutable consent artifact"))
        elif consent_artifact["role"] != "consent":
            errors.append(_issue("consent_artifact_role_invalid", "consent evidence must use role=consent"))
    retention_artifact_id = privacy["retention_policy_artifact_id"]
    retention_artifact = artifact_index.get(retention_artifact_id) if retention_artifact_id is not None else None
    if privacy["retention_status"] == "approved" and retention_artifact is None:
        errors.append(_issue("retention_policy_missing", "approved retention requires a policy reference"))
    elif retention_artifact is not None and retention_artifact["role"] != "retention_policy":
        errors.append(_issue("retention_artifact_role_invalid", "retention policy artifact must use role=retention_policy"))
    if (privacy["raw_image_allowed"] or privacy["raw_audio_allowed"]) and (
        privacy["consent_status"] != "allowed"
        or privacy["privacy_review_status"] != "approved"
        or privacy["retention_status"] != "approved"
    ):
        errors.append(_issue("raw_media_permission_inconsistent", "raw media permission requires consent, privacy review, and retention approval"))
    raw_media_artifacts = [artifact for artifact in artifacts if artifact["role"] == "raw_media"]
    if raw_media_artifacts and not privacy["raw_image_allowed"]:
        errors.append(_issue("raw_media_not_allowed", "package contains raw camera media but raw_image_allowed is false"))
    if privacy["consent_status"] == "denied" and any(
        stream["status"] == "captured" and stream["source"] in {"gnss", "lte", "camera", "audio"}
        for stream in streams
    ):
        errors.append(_issue("captured_private_data_without_consent", "private field data cannot be captured when consent is denied"))
    split = manifest["split"]
    if session_id not in split["group_keys"]:
        errors.append(_issue("split_session_group_missing", "raw session split grouping must include session_id"))

    time_lineage = manifest["time_lineage"]
    role_record_ids = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "time_lineage_records"}
    role_mapping_ids = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "clock_mapping"}
    role_report_ids = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "time_validation_report"}
    if role_record_ids != set(time_lineage["record_artifact_ids"]):
        errors.append(_issue("time_record_role_set_mismatch", "all and only time-lineage record artifacts must appear in record_artifact_ids"))
    if role_mapping_ids != set(time_lineage["mapping_artifact_ids"]):
        errors.append(_issue("time_mapping_role_set_mismatch", "all and only clock-mapping artifacts must appear in mapping_artifact_ids"))
    for artifact_id in time_lineage["record_artifact_ids"]:
        artifact = artifact_index.get(artifact_id)
        if artifact is None:
            errors.append(_issue("time_record_artifact_missing", "time lineage references an unknown record artifact", artifact_id=artifact_id))
        elif artifact["role"] != "time_lineage_records" or artifact["content_contract_version"] != TIME_RECORD_CONTRACT_VERSION:
            errors.append(_issue("time_record_artifact_contract_invalid", "time record artifact role/contract is invalid", artifact_id=artifact_id))
        elif artifact["format"] != "jsonl" or artifact["media_type"] != "application/x-ndjson":
            errors.append(_issue("time_record_artifact_format_invalid", "time record artifact must be JSONL", artifact_id=artifact_id))
    for artifact_id in time_lineage["mapping_artifact_ids"]:
        artifact = artifact_index.get(artifact_id)
        if artifact is None:
            errors.append(_issue("time_mapping_artifact_missing", "time lineage references an unknown mapping artifact", artifact_id=artifact_id))
        elif artifact["role"] != "clock_mapping" or artifact["content_contract_version"] != TIME_MAPPING_CONTRACT_VERSION:
            errors.append(_issue("time_mapping_artifact_contract_invalid", "time mapping artifact role/contract is invalid", artifact_id=artifact_id))
        elif artifact["format"] != "jsonl" or artifact["media_type"] != "application/x-ndjson":
            errors.append(_issue("time_mapping_artifact_format_invalid", "clock mapping artifact must be JSONL", artifact_id=artifact_id))
    report_artifact_id = time_lineage["validation_report_artifact_id"]
    expected_report_ids = {report_artifact_id} if report_artifact_id is not None else set()
    if role_report_ids != expected_report_ids:
        errors.append(_issue("time_report_role_set_mismatch", "exactly the referenced A0-002 report artifact may use role=time_validation_report"))
    if report_artifact_id is not None:
        report_artifact = artifact_index.get(report_artifact_id)
        if report_artifact is None:
            errors.append(_issue("time_report_artifact_missing", "time lineage references an unknown validation report", artifact_id=report_artifact_id))
        elif report_artifact["role"] != "time_validation_report":
            errors.append(_issue("time_report_artifact_role_invalid", "time validation report artifact has the wrong role", artifact_id=report_artifact_id))
        elif (
            report_artifact["format"] != "json"
            or report_artifact["media_type"] != "application/json"
            or report_artifact["content_contract_version"] != "egolink.sensor_time_validation_report.v0.1"
        ):
            errors.append(_issue("time_report_artifact_contract_invalid", "time validation report artifact format/contract is invalid", artifact_id=report_artifact_id))

    referenced_stream_artifacts = {
        stream["artifact_id"]
        for stream in streams
        if stream["status"] == "captured" and stream["artifact_id"] is not None
    }
    role_stream_artifacts = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "stream_data"}
    if role_stream_artifacts != referenced_stream_artifacts:
        errors.append(_issue("stream_artifact_role_set_mismatch", "all and only captured stream artifacts may use role=stream_data"))
    referenced_calibration_artifacts = {calibration["artifact_id"] for calibration in calibrations}
    role_calibration_artifacts = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "calibration"}
    if role_calibration_artifacts != referenced_calibration_artifacts:
        errors.append(_issue("calibration_artifact_role_set_mismatch", "all and only referenced calibration artifacts may use role=calibration"))
    expected_consent_artifacts = {privacy["consent_artifact_id"]} if privacy["consent_artifact_id"] is not None else set()
    role_consent_artifacts = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "consent"}
    if role_consent_artifacts != expected_consent_artifacts:
        errors.append(_issue("consent_artifact_role_set_mismatch", "all and only the referenced consent artifact may use role=consent"))
    expected_retention_artifacts = {privacy["retention_policy_artifact_id"]} if privacy["retention_policy_artifact_id"] is not None else set()
    role_retention_artifacts = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "retention_policy"}
    if role_retention_artifacts != expected_retention_artifacts:
        errors.append(_issue("retention_artifact_role_set_mismatch", "all and only the referenced retention artifact may use role=retention_policy"))
    referenced_policy_artifacts = {
        policy["config_artifact_id"]
        for policy in manifest["sensor_policies"].values()
        if policy["config_artifact_id"] is not None
    }
    referenced_policy_artifacts.update(
        stream["generator"]["config_artifact_id"]
        for stream in streams
        if stream["generator"] is not None
        and stream["variant"] != "calibrated"
        and stream["generator"]["config_artifact_id"] is not None
    )
    role_policy_artifacts = {artifact["artifact_id"] for artifact in artifacts if artifact["role"] == "policy"}
    if role_policy_artifacts != referenced_policy_artifacts:
        errors.append(_issue("policy_artifact_role_set_mismatch", "all and only referenced policy artifacts may use role=policy"))

    return errors, warnings


def validate_field_session(
    manifest: Mapping[str, Any],
    *,
    session_root: Path,
    manifest_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    try:
        parse_utc_ns(generated, "generated_at")
    except SensorTimeLineageError as error:
        raise FieldSessionError(str(error)) from error
    manifest_schema = _load_schema(MANIFEST_SCHEMA_PATH)
    schema_errors = _schema_issues(manifest, manifest_schema, "manifest")
    errors = list(schema_errors)
    warnings: list[dict[str, Any]] = []
    manifest_file_binding_verified = False
    if manifest_path is not None:
        manifest_from_disk = load_json(manifest_path)
        if stable_json_bytes(manifest_from_disk) != stable_json_bytes(manifest):
            errors.append(_issue("manifest_file_binding_mismatch", "manifest object differs from the explicitly named manifest file"))
        else:
            manifest_file_binding_verified = True
    artifact_paths: dict[str, Path] = {}
    artifact_integrity_verified = False
    package_closure_verified = False
    time_report_binding_verified = False
    time_report: dict[str, Any] | None = None
    manual_event_count = 0
    imu_chain_verified = False

    if not schema_errors:
        semantic_errors, semantic_warnings = _manifest_semantics(manifest)
        errors.extend(semantic_errors)
        warnings.extend(semantic_warnings)

        descriptors = _artifact_descriptors(manifest)
        artifact_index = {artifact["artifact_id"]: artifact for _, artifact in descriptors}
        artifact_error_start = len(errors)
        for label, artifact in descriptors:
            path, artifact_errors = _verify_artifact(
                label=label,
                artifact=artifact,
                session_root=session_root,
            )
            errors.extend(artifact_errors)
            if path is not None:
                artifact_paths.setdefault(artifact["artifact_id"], path)
        artifact_integrity_verified = bool(descriptors) and not any(
            issue["code"].startswith("artifact_")
            for issue in errors[artifact_error_start:]
        )

        closure_errors = _verify_package_closure(
            session_root=session_root,
            declared_paths=[artifact["path"] for _, artifact in descriptors],
            manifest_path=manifest_path,
        )
        errors.extend(closure_errors)
        package_closure_verified = not closure_errors

        record_artifact_ids = manifest["time_lineage"]["record_artifact_ids"]
        mapping_artifact_ids = manifest["time_lineage"]["mapping_artifact_ids"]
        time_records: list[dict[str, Any]] = []
        time_mappings: list[dict[str, Any]] = []
        for artifact_id in record_artifact_ids:
            path = artifact_paths.get(artifact_id)
            if path is not None:
                try:
                    time_records.extend(load_jsonl(path))
                except FieldSessionError as error:
                    errors.append(_issue("artifact_content_invalid", str(error), artifact_id=artifact_id))
        for artifact_id in mapping_artifact_ids:
            path = artifact_paths.get(artifact_id)
            if path is not None:
                try:
                    time_mappings.extend(load_jsonl(path))
                except FieldSessionError as error:
                    errors.append(_issue("artifact_content_invalid", str(error), artifact_id=artifact_id))
        mapping_index = {
            str(mapping.get("mapping_id")): mapping
            for mapping in time_mappings
            if mapping.get("mapping_id") is not None
        }

        event_streams = [
            stream
            for stream in manifest["streams"]
            if stream["source"] == "manual_event" and stream["status"] == "captured"
        ]
        manual_event_rows_by_stream: dict[str, list[Mapping[str, Any]]] = {}
        for stream in event_streams:
            artifact_id = stream["artifact_id"]
            artifact = artifact_index.get(artifact_id) if artifact_id is not None else None
            path = artifact_paths.get(artifact_id) if artifact_id is not None else None
            if artifact is None or path is None:
                continue
            if stream["variant"] != "manual_event" or stream["record_contract_version"] != MANUAL_EVENT_CONTRACT_VERSION:
                errors.append(_issue("manual_event_stream_contract_invalid", "manual event stream must use the v0.1 manual-event contract", stream_id=stream["stream_id"]))
                continue
            try:
                rows = load_jsonl(path)
            except FieldSessionError as error:
                errors.append(_issue("artifact_content_invalid", str(error), artifact_id=artifact_id))
                continue
            manual_event_count += len(rows)
            event_errors, valid_event_rows = _validate_manual_events(
                rows,
                manifest=manifest,
                stream=stream,
                mappings=mapping_index,
            )
            errors.extend(event_errors)
            manual_event_rows_by_stream[stream["stream_id"]] = valid_event_rows
            if stream["observation_count"] != len(rows):
                errors.append(_issue("manual_event_count_mismatch", "manual event observation_count differs from its JSONL rows", stream_id=stream["stream_id"]))
            if len(valid_event_rows) == len(rows):
                try:
                    observed_event_bounds = _observed_bounds(valid_event_rows)
                except SensorTimeLineageError as error:
                    errors.append(_issue("manual_event_bounds_invalid", str(error), stream_id=stream["stream_id"]))
                else:
                    errors.extend(
                        _compare_stream_bounds(
                            stream["bounds"],
                            observed_event_bounds,
                            stream_id=stream["stream_id"],
                        )
                    )
        all_valid_manual_rows = [
            row
            for rows in manual_event_rows_by_stream.values()
            for row in rows
        ]
        for event_id in sorted(_duplicates(str(row["event_id"]) for row in all_valid_manual_rows)):
            errors.append(_issue("manual_event_id_duplicate_across_streams", "manual event_id must be unique across the whole session", event_id=event_id))

        bundled_report: dict[str, Any] | None = None
        report_artifact_id = manifest["time_lineage"]["validation_report_artifact_id"]
        if report_artifact_id is not None:
            report_path = artifact_paths.get(report_artifact_id)
            if report_path is not None:
                try:
                    bundled_report = load_json(report_path)
                except FieldSessionError as error:
                    errors.append(_issue("artifact_content_invalid", str(error), artifact_id=report_artifact_id))
        report_exact_match = False
        if bundled_report is not None and (
            bundled_report.get("report_version") != "egolink.sensor_time_validation_report.v0.1"
            or not isinstance(bundled_report.get("generated_at"), str)
        ):
            errors.append(_issue("time_report_contract_invalid", "bundled A0-002 report version/generated_at is invalid"))
        report_generated_at = (
            bundled_report.get("generated_at")
            if isinstance(bundled_report, Mapping) and isinstance(bundled_report.get("generated_at"), str)
            else generated
        )
        if time_records or time_mappings:
            binding_error_start = len(errors)
            try:
                time_report = validate_time_lineage(
                    time_records,
                    time_mappings,
                    generated_at=report_generated_at,
                )
            except SensorTimeLineageError as error:
                errors.append(_issue("time_lineage_indeterminate", str(error)))
            else:
                if not time_report["valid"]:
                    errors.append(_issue("time_lineage_invalid", "A0-002 time-lineage validation failed"))
                if bundled_report is not None:
                    if stable_json_bytes(bundled_report) != stable_json_bytes(time_report):
                        errors.append(_issue("time_report_recompute_mismatch", "bundled A0-002 report differs from exact-input recomputation"))
                    else:
                        report_exact_match = True
                if time_report["input"]["record_count"] != time_report["input"]["unique_record_count"]:
                    errors.append(_issue("time_record_duplicate", "Field Session time-lineage records must be physically unique"))
                if time_report["input"]["mapping_count"] != time_report["input"]["unique_mapping_count"]:
                    errors.append(_issue("time_mapping_duplicate", "Field Session clock mappings must be physically unique"))
                session_ids = {
                    row.get("lineage", {}).get("field_session_id")
                    for row in time_records
                    if isinstance(row.get("lineage"), Mapping)
                }
                if session_ids != {manifest["session_id"]}:
                    errors.append(_issue("time_lineage_session_mismatch", f"time-lineage session IDs do not equal {manifest['session_id']}"))
                stream_index = {stream["stream_id"]: stream for stream in manifest["streams"]}
                device_run_index = {run["device_run_id"]: run for run in manifest["device_runs"]}
                path_hash_index = {
                    (artifact["path"], artifact["sha256"].lower())
                    for artifact in artifact_index.values()
                }
                for row in time_records:
                    stream = stream_index.get(row.get("stream_id"))
                    if stream is None:
                        errors.append(_issue("time_lineage_stream_missing", "time record references an unknown stream", observation_id=row.get("observation_id")))
                        continue
                    if row.get("source") != stream["source"]:
                        errors.append(_issue("time_lineage_source_mismatch", "time record source differs from its stream", observation_id=row.get("observation_id"), stream_id=stream["stream_id"]))
                    device_run = device_run_index.get(stream.get("device_run_id"))
                    if device_run is None:
                        errors.append(_issue("time_lineage_device_run_missing", "time record stream has no valid device run", observation_id=row.get("observation_id"), stream_id=stream["stream_id"]))
                    else:
                        if row.get("device_id") != device_run["device_id"]:
                            errors.append(_issue("time_lineage_device_mismatch", "time record device differs from its device run", observation_id=row.get("observation_id")))
                        if row.get("boot_count") != device_run["boot_count"]:
                            errors.append(_issue("time_lineage_boot_mismatch", "time record boot differs from its device run", observation_id=row.get("observation_id")))
                        if row.get("monotonic_clock_domain_id") != stream["clock_domain_id"]:
                            errors.append(_issue("time_lineage_clock_mismatch", "time record clock differs from its stream segment", observation_id=row.get("observation_id")))
                        row_commit = row.get("lineage", {}).get("firmware_commit") if isinstance(row.get("lineage"), Mapping) else None
                        if row_commit != device_run["firmware_commit"]:
                            errors.append(_issue("time_lineage_firmware_mismatch", "time record firmware differs from its device run", observation_id=row.get("observation_id")))
                    artifact = artifact_index.get(stream.get("artifact_id"))
                    lineage = row.get("lineage") if isinstance(row.get("lineage"), Mapping) else {}
                    if artifact is None or lineage.get("source_record_ref") != artifact["path"] or str(lineage.get("source_record_sha256") or "").lower() != artifact["sha256"].lower():
                        errors.append(_issue("time_lineage_source_artifact_mismatch", "time record does not bind the stream artifact path/hash", observation_id=row.get("observation_id"), stream_id=stream["stream_id"]))
                    if (lineage.get("source_record_ref"), str(lineage.get("source_record_sha256") or "").lower()) not in path_hash_index:
                        errors.append(_issue("time_source_evidence_not_in_package", "time record source evidence is not in the sealed artifact inventory", observation_id=row.get("observation_id")))
                    alignment = row.get("alignment") if isinstance(row.get("alignment"), Mapping) else {}
                    alignment_anchor = alignment.get("anchor")
                    if isinstance(alignment_anchor, Mapping):
                        anchor_key = (
                            alignment_anchor.get("evidence_ref"),
                            str(alignment_anchor.get("evidence_sha256") or "").lower(),
                        )
                        if anchor_key not in path_hash_index:
                            errors.append(_issue("time_alignment_anchor_not_in_package", "observation alignment anchor evidence is not in the sealed artifact inventory", observation_id=row.get("observation_id")))
                for mapping in time_mappings:
                    matching_runs = [
                        run
                        for run in manifest["device_runs"]
                        if mapping.get("device_id") == run["device_id"]
                        and mapping.get("boot_count") == run["boot_count"]
                        and mapping.get("monotonic_clock_domain_id") in run["monotonic_clock_domain_ids"]
                    ]
                    if len(matching_runs) != 1:
                        errors.append(_issue("time_mapping_device_run_mismatch", "clock mapping must resolve to exactly one device run", mapping_id=mapping.get("mapping_id")))
                    mapping_lineage = mapping.get("lineage") if isinstance(mapping.get("lineage"), Mapping) else {}
                    if mapping_lineage.get("field_session_id") != manifest["session_id"]:
                        errors.append(_issue("time_mapping_session_mismatch", "clock mapping belongs to another session", mapping_id=mapping.get("mapping_id")))
                    if len(matching_runs) == 1 and mapping_lineage.get("firmware_commit") != matching_runs[0]["firmware_commit"]:
                        errors.append(_issue("time_mapping_firmware_mismatch", "clock mapping firmware differs from its device run", mapping_id=mapping.get("mapping_id")))
                    for anchor in mapping.get("anchors", []) if isinstance(mapping.get("anchors"), list) else []:
                        if not isinstance(anchor, Mapping):
                            continue
                        anchor_key = (
                            anchor.get("source_record_ref"),
                            str(anchor.get("source_record_sha256") or "").lower(),
                        )
                        if anchor_key not in path_hash_index:
                            errors.append(_issue("time_anchor_evidence_not_in_package", "clock anchor evidence is not in the sealed artifact inventory", mapping_id=mapping.get("mapping_id"), anchor_id=anchor.get("anchor_id")))

                records_by_stream: dict[str, list[Mapping[str, Any]]] = {}
                for row in time_records:
                    if isinstance(row.get("stream_id"), str):
                        records_by_stream.setdefault(row["stream_id"], []).append(row)
                for stream in manifest["streams"]:
                    if (
                        stream["status"] != "captured"
                        or stream["source"] not in TIME_LINEAGE_SOURCES
                        or stream["variant"] in {"calibrated", "derived"}
                    ):
                        continue
                    rows = records_by_stream.get(stream["stream_id"], [])
                    artifact = artifact_index.get(stream["artifact_id"])
                    if not rows:
                        errors.append(_issue("stream_time_lineage_missing", "captured sensor stream has no A0-002 records", stream_id=stream["stream_id"]))
                        continue
                    if stream["observation_count"] != len(rows):
                        errors.append(_issue("stream_time_record_count_mismatch", "stream observation_count differs from A0-002 record count", stream_id=stream["stream_id"]))
                    try:
                        observed = _observed_bounds(rows)
                    except (KeyError, SensorTimeLineageError) as error:
                        errors.append(_issue("stream_time_bounds_invalid", str(error), stream_id=stream["stream_id"]))
                    else:
                        errors.extend(_compare_stream_bounds(stream["bounds"], observed, stream_id=stream["stream_id"]))

                for stream in manifest["streams"]:
                    if stream["status"] != "captured" or stream["variant"] not in {"calibrated", "derived"}:
                        continue
                    source_stream = stream_index.get(stream.get("source_stream_id"))
                    artifact = artifact_index.get(stream.get("artifact_id"))
                    source_artifact = artifact_index.get(source_stream.get("artifact_id")) if source_stream is not None else None
                    if source_stream is None or artifact is None or source_artifact is None:
                        continue
                    if (
                        stream["observation_count"] != source_stream["observation_count"]
                        or artifact["record_count"] != source_artifact["record_count"]
                        or stream["bounds"] != source_stream["bounds"]
                    ):
                        errors.append(_issue("derived_stream_extent_mismatch", "calibrated/derived stream must preserve source count and bounds in v0.1", stream_id=stream["stream_id"]))

                time_report_binding_verified = report_exact_match and len(errors) == binding_error_start

        imu_errors, imu_chain_verified = _validate_imu_contracts(
            manifest,
            artifact_index=artifact_index,
            artifact_paths=artifact_paths,
        )
        errors.extend(imu_errors)

    coverage: dict[str, Any] = {}
    if not schema_errors:
        for source in SOURCE_TYPES:
            streams = [stream for stream in manifest["streams"] if stream["source"] == source]
            captured = [stream for stream in streams if stream["status"] == "captured"]
            coverage[source] = {
                "declared_stream_count": len(streams),
                "captured_stream_count": len(captured),
                "record_count": sum(
                    int(stream["observation_count"] or 0)
                    for stream in captured
                    if stream["artifact_id"] in artifact_index
                ),
            }

    field_reasons: list[str] = []
    if errors:
        field_reasons.append("validation_errors_present")
    if schema_errors:
        field_reasons.append("manifest_schema_invalid")
    else:
        if manifest["session_type"] != "field":
            field_reasons.append("session_type_not_field")
        if manifest["lifecycle_state"] != "complete":
            field_reasons.append("session_not_complete")
        if manifest["seal"]["status"] != "sealed":
            field_reasons.append("session_not_sealed")
        required_sources = set(manifest["capture_profile"]["required_sources"])
        for source in FIELD_PROFILE_SOURCES:
            if source not in required_sources:
                field_reasons.append(f"a_r0_required_source_not_in_profile:{source}")
            captured = [
                stream
                for stream in manifest["streams"]
                if stream["source"] == source and stream["status"] == "captured"
            ]
            if not captured:
                field_reasons.append(f"required_source_not_captured:{source}")
            elif not any(
                stream["artifact_id"] in artifact_index
                and int(stream["observation_count"] or 0) > 0
                for stream in captured
            ):
                field_reasons.append(f"required_source_empty:{source}")
        if not artifact_integrity_verified:
            field_reasons.append("artifact_integrity_not_verified")
        if not package_closure_verified:
            field_reasons.append("package_closure_not_verified")
        if not manifest_file_binding_verified:
            field_reasons.append("manifest_file_binding_not_verified")
        if any(artifact["format"] == "binary" for artifact in manifest["artifacts"]):
            field_reasons.append("binary_attachment_requires_external_review")
        if manifest["software"]["repository_commit"] is None:
            field_reasons.append("software_commit_missing")
        if manifest["software"]["capture_tool"] == "unassigned" or manifest["software"]["capture_tool_version"] == "unassigned":
            field_reasons.append("capture_tool_identity_missing")
        for source in TIME_LINEAGE_SOURCES:
            policy = manifest["sensor_policies"][source]
            if policy["mode"] in {"unknown", "disabled"}:
                field_reasons.append(f"required_sensor_policy_unknown:{source}")
        for run in manifest["device_runs"]:
            allowed_run_statuses = (
                {"verified", "observed", "pc_side_verified"}
                if run["role"] == "host_bridge"
                else PHYSICAL_FIELD_SOURCE_STATUSES
            )
            if run["source_status"] not in allowed_run_statuses:
                field_reasons.append(f"device_run_not_field_verified:{run['device_run_id']}")
            if run["firmware_commit"] is None and run["firmware_image_sha256"] is None:
                field_reasons.append(f"firmware_identity_missing:{run['device_run_id']}")
        required_stream_runs = {
            stream["device_run_id"]
            for stream in manifest["streams"]
            if stream["status"] == "captured"
            and stream["source"] in TIME_LINEAGE_SOURCES
            and stream["variant"] not in {"calibrated", "derived"}
            and stream["device_run_id"] is not None
        }
        run_index = {run["device_run_id"]: run for run in manifest["device_runs"]}
        for run_id in sorted(required_stream_runs):
            run = run_index.get(run_id)
            if run is None or run["firmware_commit"] is None:
                field_reasons.append(f"time_lineage_firmware_commit_missing:{run_id}")
        for stream in manifest["streams"]:
            if stream["status"] != "captured" or stream["source"] not in TIME_LINEAGE_SOURCES:
                continue
            artifact = artifact_index.get(stream["artifact_id"])
            if artifact is None or artifact["privacy_class"] == "unknown":
                field_reasons.append(f"required_source_privacy_unclassified:{stream['stream_id']}")
            run = run_index.get(stream["device_run_id"])
            if stream["source"] in {"gnss", "lte", "imu", "camera"} and (
                run is None or run["source_status"] not in {"observed", "verified"}
            ):
                field_reasons.append(f"physical_source_not_observed:{stream['stream_id']}")
            if stream["variant"] == "calibrated" and (
                stream["generator"] is None or stream["generator"]["commit"] is None
            ):
                field_reasons.append(f"calibrated_generator_commit_missing:{stream['stream_id']}")
        privacy = manifest["privacy"]
        if privacy["consent_status"] != "allowed":
            field_reasons.append("collection_consent_not_allowed")
        if privacy["privacy_review_status"] != "approved":
            field_reasons.append("privacy_review_not_approved")
        if privacy["retention_status"] != "approved":
            field_reasons.append("retention_not_approved")
        if privacy["location_privacy_class"] == "unknown":
            field_reasons.append("location_privacy_class_unknown")
        if manual_event_count < 1:
            field_reasons.append("manual_event_missing")
        imu_streams = [stream for stream in manifest["streams"] if stream["source"] == "imu" and stream["status"] == "captured"]
        if not any(stream["variant"] in PRECALIBRATION_VARIANTS for stream in imu_streams):
            field_reasons.append("imu_precalibration_stream_missing")
        if not any(stream["variant"] == "calibrated" for stream in imu_streams):
            field_reasons.append("imu_calibrated_stream_missing")
        if not imu_chain_verified:
            field_reasons.append("imu_raw_calibrated_chain_not_verified")
        if time_report is None:
            field_reasons.append("a0_002_time_lineage_report_missing")
        elif not time_report.get("field_eligible"):
            field_reasons.append("a0_002_time_lineage_not_field_eligible")
        if not time_report_binding_verified:
            field_reasons.append("a0_002_report_binding_not_verified")

    training_reasons = ["requires_a0_004_dataset_level_split_leakage_review"]
    privacy_value = manifest.get("privacy") if isinstance(manifest, Mapping) else None
    privacy_for_report = privacy_value if isinstance(privacy_value, Mapping) else {}
    split_value = manifest.get("split") if isinstance(manifest, Mapping) else None
    split_for_report = split_value if isinstance(split_value, Mapping) else {}
    if not privacy_for_report.get("training_allowed", False):
        training_reasons.append("training_consent_not_allowed")
    if split_for_report.get("name") in {None, "unassigned", "excluded"}:
        training_reasons.append("training_split_not_assigned")
    if split_for_report.get("leakage_review_status") != "passed":
        training_reasons.append("split_leakage_review_not_passed")

    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated,
        "session_id": manifest.get("session_id"),
        "valid": not errors,
        "manifest_file_binding_verified": manifest_file_binding_verified,
        "artifact_integrity_verified": artifact_integrity_verified,
        "package_closure_verified": package_closure_verified,
        "coverage": coverage,
        "a0_002_time_lineage": time_report,
        "a0_002_report_binding_verified": time_report_binding_verified,
        "imu_raw_calibrated_chain_verified": imu_chain_verified,
        "field_eligibility_scope": "structural_review_only",
        "field_eligible": not field_reasons,
        "field_eligibility_reasons": list(dict.fromkeys(field_reasons)),
        "training_status": "not_evaluated",
        "training_eligible": False,
        "training_eligibility_reasons": list(dict.fromkeys(training_reasons)),
        "gate_status": "unverified",
        "gate_reason": "requires a reviewed real four-source Field Session; static fixtures and code do not pass A0-003 or A-R0",
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or validate an Ego Link A0-003 Field Session manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="write a fail-closed planned manifest")
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.add_argument("--device-id", required=True)
    init_parser.add_argument("--operator-ref", required=True)
    init_parser.add_argument("--protocol-id", required=True)
    init_parser.add_argument("--test-scenario", required=True)
    init_parser.add_argument("--route-id")
    init_parser.add_argument("--timezone", default="Asia/Shanghai")
    init_parser.add_argument("--created-at-utc")
    init_parser.add_argument("--session-id")

    validate_parser = subparsers.add_parser("validate", help="verify one explicit session bundle")
    validate_parser.add_argument("--manifest", type=Path, required=True)
    validate_parser.add_argument("--session-root", type=Path)
    validate_parser.add_argument("--report", type=Path)
    validate_parser.add_argument("--fail-if-ineligible", action="store_true")

    seal_parser = subparsers.add_parser("seal", help="write a sealed manifest copy after integrity validation")
    seal_parser.add_argument("--manifest", type=Path, required=True)
    seal_parser.add_argument("--session-root", type=Path)
    seal_parser.add_argument("--output", type=Path, required=True)
    seal_parser.add_argument("--sealed-by", required=True)
    seal_parser.add_argument("--sealed-at-utc")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "init":
            if args.output.exists():
                raise FieldSessionError(f"refusing to overwrite existing manifest: {args.output}")
            manifest = build_draft_manifest(
                device_id=args.device_id,
                operator_ref=args.operator_ref,
                protocol_id=args.protocol_id,
                test_scenario=args.test_scenario,
                route_id=args.route_id,
                timezone_name=args.timezone,
                created_at_utc=args.created_at_utc,
                session_id=args.session_id,
            )
            schema_errors = _schema_issues(manifest, _load_schema(MANIFEST_SCHEMA_PATH), "manifest")
            if schema_errors:
                raise FieldSessionError(f"generated manifest failed its schema: {schema_errors}")
            write_json(args.output, manifest)
            print(json.dumps({"session_id": manifest["session_id"], "manifest": str(args.output), "field_eligible": False}, ensure_ascii=False))
            return 0

        manifest = load_json(args.manifest)
        session_root = (args.session_root or args.manifest.parent).resolve()
        manifest_path = args.manifest.resolve()

        if args.command == "seal":
            if args.output.exists():
                raise FieldSessionError(f"refusing to overwrite existing sealed manifest: {args.output}")
            try:
                args.output.resolve().relative_to(session_root)
            except ValueError:
                pass
            else:
                raise FieldSessionError("sealed output must be outside the session root until it replaces the source manifest")
            preflight = validate_field_session(
                manifest,
                session_root=session_root,
                manifest_path=manifest_path,
            )
            if not preflight["valid"] or not preflight["artifact_integrity_verified"] or not preflight["package_closure_verified"]:
                print(json.dumps(preflight, ensure_ascii=False, indent=2))
                return 1
            if manifest["seal"]["status"] != "unsealed":
                raise FieldSessionError("input manifest is already sealed")
            sealed = seal_manifest(
                manifest,
                sealed_by=args.sealed_by,
                sealed_at_utc=args.sealed_at_utc,
            )
            schema_errors = _schema_issues(sealed, _load_schema(MANIFEST_SCHEMA_PATH), "manifest")
            if schema_errors:
                raise FieldSessionError(f"sealed manifest failed its schema: {schema_errors}")
            write_json(args.output, sealed)
            print(json.dumps({"session_id": sealed["session_id"], "sealed_manifest": str(args.output)}, ensure_ascii=False))
            return 0

        if args.report is not None:
            try:
                args.report.resolve().relative_to(session_root)
            except ValueError:
                pass
            else:
                raise FieldSessionError("validation report output must be outside the sealed session root")
        report = validate_field_session(
            manifest,
            session_root=session_root,
            manifest_path=manifest_path,
        )
        if args.report is not None:
            write_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["valid"]:
            return 1
        if args.fail_if_ineligible and not report["field_eligible"]:
            return 1
        return 0
    except (FieldSessionError, SensorTimeLineageError) as error:
        print(json.dumps({"error": str(error), "exit_class": "indeterminate_input"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
