"""Raw collection indexing in the existing Message Hub SQLite database.

The immutable EGLK frame remains in raw_frames.  This module only adds its
search index and separate receipt attempts; it does not run Location Engine.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import time
from typing import Any

from server.photo_store import PhotoStoreError


CONTRACT_VERSION = "egolink.collection.v1"
CONTENT_TYPE = "application/json;profile=" + CONTRACT_VERSION
MAX_FRAME_BYTES = 65_536
MAX_PAGE_RECORDS = 100
MAX_PAGE_BYTES = 2_000_000
SOURCES = frozenset({"gnss", "lte", "imu", "wifi", "camera", "power", "device", "time_anchor", "source_status", "session", "loss", "delivery"})
CONTEXT_SOURCES = frozenset({"time_anchor", "source_status", "session", "loss"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
INT64_MAX = 9_223_372_036_854_775_807
COLLECTION_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "shared" / "contracts" / "collection_observation.schema.json"
COLLECTION_PRIVACY_REJECTION_DETAIL = "Wi-Fi collection payload violates the privacy admission policy"
_WIFI_RAW_IDENTIFIER_KEYS = frozenset({"ssid", "bssid", "mac"})
_WIFI_AP_STRUCTURE_KEYS = frozenset({"ap", "aps", "accesspoint", "accesspoints", "network", "networks", "station", "stations", "scanresults"})
_WIFI_LINK_EVENT_FIELDS = frozenset({"phase", "connected"})
_WIFI_SCAN_SUMMARY_FIELDS = frozenset({"channel_summary", "scan_result", "total_seen", "truncated", "sampled_ap_count", "identifiers_retained", "privacy_reason", "connected", "disconnect_reason"})
_WIFI_CHANNEL_SUMMARY_FIELDS = frozenset({"channel", "ap_count", "strongest_rssi"})
COLLECTION_ENVELOPE_FIELDS = frozenset({"contract_version", "observation_id", "device_id", "source", "stream_id", "sequence_id", "boot_count", "monotonic_clock_domain_id", "timestamp_monotonic_ns", "timestamp_utc", "timestamp_source", "timestamp_quality", "fw_version", "config_id", "session_id", "status", "payload", "missing_reason"})
COLLECTION_OPTIONAL_PROVENANCE_FIELDS = frozenset({"firmware_elf_sha256", "test_run_id"})
COLLECTION_WIFI_ENVELOPE_FIELDS = COLLECTION_ENVELOPE_FIELDS | COLLECTION_OPTIONAL_PROVENANCE_FIELDS
FIRMWARE_ELF_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CAMERA_SOURCE_STATUS_FIELDS = frozenset({
    "source", "component", "camera_runtime_compiled", "driver_preflight_ready",
    "capture_trigger_wired", "media_store_ready", "command_id",
    "authorization_session_id", "source_event_utc", "source_event_monotonic_ms",
    "event_reason", "timer_state",
})
CAMERA_TIMER_STATE_FIELDS = frozenset({
    "config_version", "enabled", "interval_seconds",
    "session_expires_at_unix_ms", "max_photos", "captured_count",
    "state_reason", "trusted_utc",
})

# Keep the deployed collector stdlib-only. The focused contract tests compare
# this bounded adapter against the unchanged JSON-Schema estimation oracle.
EGO_STATE_VERSION = "egolink.ego_state_estimation.v0.1"
EGO_VIEW_VERSION = "egolink.ego_state_view.v0.1"
EGO_IDENTITY_FIELDS = frozenset({
    "contract_version", "estimation_id", "device_id", "boot_count",
    "timestamp_monotonic_ns", "timestamp_utc",
})
EGO_VALUE_FIELDS = frozenset({
    "spatial_mobility", "posture_anomaly", "device_wear_state", "confidence",
    "window_duration_ms", "reason_codes", "primary_evidence_digest", "is_mock",
})
EGO_ENUMS = {
    "spatial_mobility": {"stationary", "pedestrian_walking", "running", "in_vehicle", "indoor_weak_gnss", "unknown"},
    "posture_anomaly": {"normal", "abnormal_shock", "suspected_fall", "prolonged_immobility", "unknown"},
    "device_wear_state": {"tabletop_resting", "handheld", "wearable_or_bag", "charging_docked", "unknown"},
}


def _ego_state_projection(envelope: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Adapt only valid DEVICE states; a failed projection never rejects raw data.

    Legacy firmware omitted *all* canonical identity/time fields. Only that
    exact shape inherits collection source identity/time, never receive time.
    Partially upgraded or conflicting identities are quarantined, not repaired.
    """
    payload = envelope.get("payload", {})
    if envelope.get("source") != "device" or "ego_state" not in payload:
        return None, {"status": "absent", "reason_code": "ego_state_missing"}
    raw = payload["ego_state"]
    if isinstance(raw, dict) and raw.get("ready") is False:
        return None, {"status": "unavailable", "reason_code": "ego_state_not_ready"}

    def invalid(reason: str) -> tuple[None, dict[str, Any]]:
        return None, {"status": "invalid", "reason_code": reason}

    if not isinstance(raw, dict) or raw.get("ready") is not True:
        return invalid("ego_state_invalid_readiness")
    if set(raw) - (EGO_IDENTITY_FIELDS | EGO_VALUE_FIELDS | {"ready", "evidence_summary"}):
        return invalid("ego_state_unknown_fields")
    if not EGO_VALUE_FIELDS <= raw.keys():
        return invalid("ego_state_missing_values")
    supplied_identity = EGO_IDENTITY_FIELDS & raw.keys()
    if supplied_identity and supplied_identity != EGO_IDENTITY_FIELDS:
        return invalid("ego_state_partial_identity")
    identity_source = "device" if supplied_identity else "legacy_derived_from_collection_envelope"
    state = {key: raw[key] for key in EGO_VALUE_FIELDS}
    if supplied_identity:
        state.update({key: raw[key] for key in EGO_IDENTITY_FIELDS})
    else:
        state.update({
            "contract_version": EGO_STATE_VERSION,
            "estimation_id": envelope["observation_id"],
            "device_id": envelope["device_id"], "boot_count": envelope["boot_count"],
            "timestamp_monotonic_ns": envelope["timestamp_monotonic_ns"],
            "timestamp_utc": envelope["timestamp_utc"],
        })
    if state["contract_version"] != EGO_STATE_VERSION:
        return invalid("ego_state_unsupported_version")
    for key in ("estimation_id", "device_id"):
        if not isinstance(state[key], str) or SAFE_ID.fullmatch(state[key]) is None:
            return invalid("ego_state_invalid_identity")
    for key, minimum in (("boot_count", 0), ("timestamp_monotonic_ns", 0), ("window_duration_ms", 100)):
        if type(state[key]) is not int or not minimum <= state[key] <= INT64_MAX:
            return invalid("ego_state_invalid_integer")
    if state["device_id"] != envelope["device_id"] or state["boot_count"] != envelope["boot_count"]:
        return invalid("ego_state_envelope_identity_mismatch")
    if state["timestamp_monotonic_ns"] > envelope["timestamp_monotonic_ns"]:
        return invalid("ego_state_future_source_time")
    utc = state["timestamp_utc"]
    if utc is not None:
        try:
            if not isinstance(utc, str) or len(utc) > 40 or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", utc) is None:
                raise ValueError("invalid date-time")
            parsed_utc = datetime.fromisoformat(utc.replace("Z", "+00:00"))
            if parsed_utc.tzinfo is None:
                raise ValueError("missing timezone")
            if envelope["timestamp_utc"] is not None and parsed_utc > datetime.fromisoformat(envelope["timestamp_utc"].replace("Z", "+00:00")):
                return invalid("ego_state_future_source_time")
        except (ValueError, TypeError):
            return invalid("ego_state_invalid_utc")
    for key, values in EGO_ENUMS.items():
        if not isinstance(state[key], str) or state[key] not in values:
            return invalid("ego_state_invalid_enum")
    confidence = state["confidence"]
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1 or not math.isfinite(confidence):
        return invalid("ego_state_invalid_confidence")
    if type(state["is_mock"]) is not bool:
        return invalid("ego_state_invalid_mock_flag")
    if (envelope.get("is_mock") is True or payload.get("is_mock") is True) and not state["is_mock"]:
        return invalid("ego_state_mock_lineage_mismatch")
    digest = state["primary_evidence_digest"]
    if not isinstance(digest, str) or FIRMWARE_ELF_SHA256.fullmatch(digest) is None:
        return invalid("ego_state_invalid_digest")
    reasons = state["reason_codes"]
    if not isinstance(reasons, list) or not reasons or any(not isinstance(code, str) or not 1 <= len(code) <= 128 for code in reasons):
        return invalid("ego_state_invalid_reasons")
    if len(set(reasons)) != len(reasons):
        return invalid("ego_state_duplicate_reasons")
    if not isinstance(raw.get("evidence_summary", {}), dict):
        return invalid("ego_state_invalid_evidence_summary")
    return state, {"status": "valid", "reason_code": "ego_state_schema_valid", "identity_source": identity_source}


class CollectionError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 422):
        super().__init__(detail)
        self.code, self.status = code, status


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _integer(value: Any, name: str, minimum: int = 0, maximum: int = INT64_MAX) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CollectionError("invalid_collection_envelope", f"{name} is outside its integer range")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise CollectionError("invalid_collection_envelope", f"{name} is not a bounded identifier")
    return value


def _utc(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40 or not value.endswith("Z"):
        raise CollectionError("invalid_collection_envelope", f"{name} must be UTC with a Z suffix or null")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CollectionError("invalid_collection_envelope", f"{name} is not a timestamp") from error
    return value


def _utc_index(value: str | None) -> str | None:
    """Normalize only the index, keeping the source timestamp bytes unchanged."""
    if value is None:
        return None
    return datetime.fromisoformat(value[:-1] + "+00:00").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CollectionError("invalid_collection_envelope", "duplicate JSON member")
        result[key] = value
    return result


def is_collection_content_type(value: Any) -> bool:
    return isinstance(value, str) and value.replace(" ", "").lower() == CONTENT_TYPE


def export_schema() -> dict[str, Any]:
    try:
        raw = COLLECTION_SCHEMA_PATH.read_bytes()
        if not 0 < len(raw) <= 65_536:
            raise ValueError("schema size")
        schema = json.loads(raw.decode("utf-8"))
        if schema["properties"]["contract_version"]["const"] != CONTRACT_VERSION:
            raise ValueError("schema version")
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as error:
        raise CollectionError("collection_schema_unavailable", "the deployed collection schema is unavailable or incompatible", 503) from error
    return {"path": "shared/contracts/collection_observation.schema.json", "sha256": hashlib.sha256(raw).hexdigest(), "document": schema}


def decode_envelope(payload: bytes, record: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CollectionError("invalid_collection_envelope", "collection payload must be bounded valid UTF-8 JSON") from error
    if not isinstance(value, dict) or not COLLECTION_ENVELOPE_FIELDS <= value.keys():
        raise CollectionError("invalid_collection_envelope", "collection envelope is missing required fields")
    if value["contract_version"] != CONTRACT_VERSION:
        raise CollectionError("invalid_collection_envelope", "unsupported collection contract")
    for field in ("observation_id", "device_id", "stream_id", "monotonic_clock_domain_id", "config_id"):
        _identifier(value[field], field)
    if value["session_id"] is not None:
        _identifier(value["session_id"], "session_id")
    if value.get("test_run_id") is not None:
        _identifier(value["test_run_id"], "test_run_id")
    for field in ("sequence_id", "boot_count"):
        _integer(value[field], field, maximum=4_294_967_295)
    _integer(value["timestamp_monotonic_ns"], "timestamp_monotonic_ns", maximum=9_007_199_254_740_991)
    _utc(value["timestamp_utc"], "timestamp_utc")
    if not isinstance(value["source"], str) or value["source"] not in SOURCES:
        raise CollectionError("invalid_collection_envelope", "unsupported collection source")
    for field in ("timestamp_source", "timestamp_quality", "status", "fw_version"):
        if not isinstance(value[field], str) or not 1 <= len(value[field]) <= 128:
            raise CollectionError("invalid_collection_envelope", f"{field} must be a bounded string")
    if "firmware_elf_sha256" in value:
        firmware_elf_sha256 = value["firmware_elf_sha256"]
        if (
            not isinstance(firmware_elf_sha256, str)
            or FIRMWARE_ELF_SHA256.fullmatch(firmware_elf_sha256) is None
        ):
            raise CollectionError(
                "invalid_collection_envelope",
                "firmware_elf_sha256 must be a lowercase SHA-256 hex digest",
            )
    if value["missing_reason"] is not None and (not isinstance(value["missing_reason"], str) or len(value["missing_reason"]) > 512):
        raise CollectionError("invalid_collection_envelope", "missing_reason must be bounded text or null")
    if not isinstance(value["payload"], dict):
        raise CollectionError("invalid_collection_envelope", "payload must be an object")
    if value["device_id"] != record["device_id"] or value["observation_id"] != record["frame_id"] or value["sequence_id"] != record["seq"]:
        raise CollectionError("collection_identity_mismatch", "route, frame and envelope identity must agree")
    return value


def enforce_collection_privacy(envelope: dict[str, Any]) -> None:
    """Reject raw Wi-Fi identifiers before opening the durable store transaction."""
    if envelope["source"] != "wifi":
        return

    def reject() -> None:
        # The response deliberately does not identify the rejected key or value.
        raise CollectionError("collection_privacy_policy_rejected", COLLECTION_PRIVACY_REJECTION_DETAIL)

    # Additive envelope fields remain available to other sources.  Wi-Fi is
    # intentionally fail-closed so an identifier cannot bypass the payload
    # shape by moving into a renamed top-level extension field.
    if not envelope.keys() <= COLLECTION_WIFI_ENVELOPE_FIELDS:
        reject()
    pending: list[Any] = [envelope]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                folded = key.casefold()
                compact = re.sub(r"[_-]", "", folded)
                if folded in _WIFI_RAW_IDENTIFIER_KEYS or folded.startswith(("raw_", "raw-")) or compact in _WIFI_AP_STRUCTURE_KEYS:
                    reject()
                pending.append(nested)
        elif isinstance(value, list):
            pending.extend(value)
    payload = envelope["payload"]
    if payload.get("phase") == "link_event":
        expected = _WIFI_LINK_EVENT_FIELDS | ({"disconnect_reason"} if payload.get("connected") is False else set())
        if payload.keys() != expected or type(payload["connected"]) is not bool:
            reject()
        if "disconnect_reason" in payload and (type(payload["disconnect_reason"]) is not int or not 0 <= payload["disconnect_reason"] <= 65_535):
            reject()
        return

    if payload.keys() != _WIFI_SCAN_SUMMARY_FIELDS:
        reject()
    if (type(payload["scan_result"]) is not int or not -2_147_483_648 <= payload["scan_result"] <= 2_147_483_647
            or type(payload["total_seen"]) is not int or not 0 <= payload["total_seen"] <= 65_535
            or type(payload["truncated"]) is not bool
            or type(payload["sampled_ap_count"]) is not int or not 0 <= payload["sampled_ap_count"] <= 16
            or payload["identifiers_retained"] is not False
            or payload["privacy_reason"] != "raw_wifi_identifiers_disabled"
            or type(payload["connected"]) is not bool
            or type(payload["disconnect_reason"]) is not int or not 0 <= payload["disconnect_reason"] <= 65_535):
        reject()
    channels = payload["channel_summary"]
    if not isinstance(channels, list) or len(channels) > 14:
        reject()
    seen_channels: set[int] = set()
    sampled = 0
    for channel in channels:
        if (not isinstance(channel, dict) or channel.keys() != _WIFI_CHANNEL_SUMMARY_FIELDS
                or type(channel["channel"]) is not int or not 1 <= channel["channel"] <= 14
                or type(channel["ap_count"]) is not int or not 1 <= channel["ap_count"] <= 16
                or type(channel["strongest_rssi"]) is not int or not -127 <= channel["strongest_rssi"] <= 0
                or channel["channel"] in seen_channels):
            reject()
        seen_channels.add(channel["channel"])
        sampled += channel["ap_count"]
    if sampled != payload["sampled_ap_count"] or sampled > payload["total_seen"]:
        reject()


def validate_camera_source_status(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate the exact camera runtime-state shape before it can be indexed."""

    payload = envelope["payload"]
    if set(payload) != CAMERA_SOURCE_STATUS_FIELDS:
        raise ValueError("camera source_status payload shape is invalid")
    if payload["source"] != "camera" or payload["component"] != "photo_control":
        raise ValueError("camera source_status identity is invalid")
    for field in (
        "camera_runtime_compiled",
        "driver_preflight_ready",
        "capture_trigger_wired",
        "media_store_ready",
    ):
        if type(payload[field]) is not bool:
            raise ValueError(f"camera source_status {field} must be boolean")
    if envelope["status"] not in {"observed", "unavailable"}:
        raise ValueError("camera source_status top-level status is invalid")
    if (envelope["status"] == "observed") != (envelope["missing_reason"] is None):
        raise ValueError("camera source_status availability and reason disagree")
    _utc(payload["source_event_utc"], "source_event_utc")
    _integer(
        payload["source_event_monotonic_ms"],
        "source_event_monotonic_ms",
        maximum=9_007_199_254_740_991,
    )
    if (
        not isinstance(payload["event_reason"], str)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", payload["event_reason"]) is None
    ):
        raise ValueError("camera source_status event_reason is invalid")
    timer = payload["timer_state"]
    if not isinstance(timer, dict) or set(timer) != CAMERA_TIMER_STATE_FIELDS:
        raise ValueError("camera source_status timer_state shape is invalid")
    if type(timer["enabled"]) is not bool or type(timer["trusted_utc"]) is not bool:
        raise ValueError("camera source_status timer booleans are invalid")
    if timer["trusted_utc"] != (payload["source_event_utc"] is not None):
        raise ValueError("camera source_status UTC trust fields disagree")
    if (
        not isinstance(timer["state_reason"], str)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", timer["state_reason"]) is None
    ):
        raise ValueError("camera source_status timer state_reason is invalid")
    _integer(timer["interval_seconds"], "camera timer interval_seconds", 0, 86_400)
    _integer(
        timer["session_expires_at_unix_ms"],
        "camera timer session_expires_at_unix_ms",
        0,
        9_007_199_254_740_991,
    )
    _integer(timer["max_photos"], "camera timer max_photos", 0, 1000)
    _integer(timer["captured_count"], "camera timer captured_count", 0, 1000)
    config_version = timer["config_version"]
    if config_version is None:
        if (
            payload["command_id"] is not None
            or payload["authorization_session_id"] is not None
            or timer["enabled"]
            or timer["interval_seconds"] != 0
            or timer["session_expires_at_unix_ms"] != 0
            or timer["max_photos"] != 0
            or timer["captured_count"] != 0
        ):
            raise ValueError("unconfigured camera timer state is inconsistent")
        return timer
    _identifier(config_version, "camera timer config_version")
    _identifier(payload["command_id"], "camera source_status command_id")
    _identifier(
        payload["authorization_session_id"],
        "camera source_status authorization_session_id",
    )
    _integer(timer["interval_seconds"], "camera timer interval_seconds", 60, 86_400)
    _integer(
        timer["session_expires_at_unix_ms"],
        "camera timer session_expires_at_unix_ms",
        1,
        9_007_199_254_740_991,
    )
    _integer(timer["max_photos"], "camera timer max_photos", 1, 1000)
    _integer(
        timer["captured_count"],
        "camera timer captured_count",
        0,
        timer["max_photos"],
    )
    return timer


def inspect_source(envelope: dict[str, Any]) -> dict[str, Any]:
    """Versioned, disposable preview.  Failure never deletes authenticated raw."""
    source, payload = envelope["source"], envelope["payload"]
    result: dict[str, Any] = {"parser_version": "collection-preview.v1", "status": "ok", "sample_count": 0}
    try:
        if source == "imu" and ("samples_b64" in payload or envelope["status"] in {"ok", "observed", "collected", "partial"}):
            count = _integer(payload.get("sample_count"), "sample_count", 0, 200)
            if count == 0 and envelope["status"] not in {"partial", "error", "timeout"}:
                raise ValueError("an observed IMU block has no samples")
            if payload.get("encoding") != "offset_us+six_i16le+base64-v1" or payload.get("sample_record_bytes") != 16:
                raise ValueError("unsupported IMU sample encoding")
            raw = base64.b64decode(payload["samples_b64"], validate=True)
            if len(raw) != count * 16:
                raise ValueError("IMU chunk length mismatch")
            offsets = [item[0] for item in struct.iter_unpack("<I6h", raw)]
            if any(right <= left for left, right in zip(offsets, offsets[1:])):
                raise ValueError("IMU sample offsets are not increasing")
            if "samples_crc32" in payload and str(payload["samples_crc32"]).upper() != f"{binascii.crc32(raw) & 0xffffffff:08X}":
                raise ValueError("IMU chunk checksum mismatch")
            result.update(sample_count=count, first_offset_us=offsets[0] if offsets else None, last_offset_us=offsets[-1] if offsets else None)
        elif source in {"gnss", "lte"}:
            attempts = payload.get("at")
            if not isinstance(attempts, list) or len(attempts) > 12:
                raise ValueError("modem AT attempts are missing or over limit")
            for attempt in attempts:
                if not isinstance(attempt, dict) or not isinstance(attempt.get("command"), str) or len(attempt["command"]) > 80 or not isinstance(attempt.get("response"), str) or len(attempt["response"].encode("utf-8")) > 1024:
                    raise ValueError("modem raw attempt is malformed")
                _integer(attempt.get("elapsed_ms"), "elapsed_ms", 0, 300_000)
                outcome = attempt.get("outcome")
                if type(outcome) is int:
                    _integer(outcome, "AT outcome", 0, 255)
                elif not isinstance(outcome, str) or not 1 <= len(outcome) <= 80:
                    raise ValueError("modem attempt outcome is missing")
            result["attempt_count"] = len(attempts)
        elif source == "camera":
            result.update(
                sample_count=1 if payload.get("capture_result") == "captured" else 0,
                photo_id=payload.get("photo_id"),
                capture_result=payload.get("capture_result"),
                local_save_status=payload.get("local_save_status"),
                device_upload_status=payload.get("device_upload_status"),
                byte_length=payload.get("byte_length"),
            )
    except (ValueError, KeyError, TypeError, binascii.Error) as error:
        result.update(status="parse_error", error_code="SOURCE_PAYLOAD_PARSE_ERROR", reason=str(error), sample_count=0)
    return result


class CollectionStore:
    def __init__(self, hub: Any):
        self.hub = hub
        with hub.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS collection_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, observation_id TEXT NOT NULL,
                    raw_frame_id INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
                    source TEXT NOT NULL, stream_id TEXT NOT NULL,
                    sequence_id INTEGER NOT NULL, boot_count INTEGER NOT NULL,
                    clock_domain TEXT NOT NULL, event_monotonic_ns INTEGER NOT NULL,
                    event_utc TEXT, session_id TEXT, fw_version TEXT NOT NULL,
                    config_id TEXT NOT NULL, acquisition_status TEXT NOT NULL,
                    parse_status TEXT NOT NULL, sample_count INTEGER NOT NULL,
                    frame_bytes INTEGER NOT NULL, received_at TEXT NOT NULL,
                    persisted_at TEXT NOT NULL, envelope_json TEXT NOT NULL,
                    preview_json TEXT NOT NULL,
                    UNIQUE(device_id, observation_id)
                );
                CREATE INDEX IF NOT EXISTS collection_device_source_time
                    ON collection_records(device_id, source, boot_count DESC, event_monotonic_ns DESC);
                CREATE INDEX IF NOT EXISTS collection_device_record ON collection_records(device_id, id);
                CREATE TABLE IF NOT EXISTS collection_delivery_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, observation_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
                    claimed_actual_transport TEXT NOT NULL, result TEXT NOT NULL,
                    conflict_raw_frame_id INTEGER
                );
                CREATE INDEX IF NOT EXISTS collection_delivery_record
                    ON collection_delivery_attempts(device_id, observation_id, id);
                CREATE TABLE IF NOT EXISTS collection_source_states (
                    device_id TEXT NOT NULL, target_source TEXT NOT NULL,
                    record_id INTEGER NOT NULL, boot_count INTEGER NOT NULL,
                    event_monotonic_ns INTEGER NOT NULL, sequence_id INTEGER NOT NULL,
                    PRIMARY KEY(device_id, target_source)
                );
                CREATE TABLE IF NOT EXISTS collection_annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, annotation_id TEXT NOT NULL,
                    session_id TEXT, created_at TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, annotation_json TEXT NOT NULL,
                    UNIQUE(device_id, annotation_id)
                );
                CREATE INDEX IF NOT EXISTS collection_annotations_device
                    ON collection_annotations(device_id, id);
                CREATE TABLE IF NOT EXISTS collection_ego_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, observation_id TEXT NOT NULL,
                    record_id INTEGER NOT NULL, boot_count INTEGER NOT NULL,
                    event_monotonic_ns INTEGER NOT NULL, sequence_id INTEGER NOT NULL,
                    event_utc TEXT, received_at TEXT NOT NULL,
                    spatial_mobility TEXT NOT NULL, posture_anomaly TEXT NOT NULL,
                    device_wear_state TEXT NOT NULL, confidence REAL NOT NULL,
                    window_duration_ms INTEGER NOT NULL, primary_evidence_digest TEXT NOT NULL,
                    is_mock INTEGER NOT NULL, reason_codes_json TEXT NOT NULL,
                    evidence_summary_json TEXT NOT NULL, ego_state_json TEXT NOT NULL,
                    UNIQUE(device_id, observation_id)
                );
                CREATE INDEX IF NOT EXISTS collection_ego_state_device_time
                    ON collection_ego_states(device_id, boot_count DESC, event_monotonic_ns DESC, sequence_id DESC);
            """)

    @staticmethod
    def _insert_raw(db: sqlite3.Connection, record: dict[str, Any]) -> int:
        raw, framing, parsed = record["raw_payload"], record.get("framing", {}), record["parse_result"]
        cursor = db.execute("""INSERT INTO raw_frames
            (frame_id,device_id,direction,frame_type,seq,test_run_id,fw_version,content_type,
             payload_len,payload_crc32,raw_payload_sha256,raw_payload_b64,server_received_at,
             parse_status,parse_error_code,parse_reason,derived_message_type,derived_message_json,record_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["frame_id"],record["device_id"],"uplink",framing.get("frame_type"),record.get("seq"),
             record.get("test_run_id"),record.get("fw_version"),framing.get("content_type"),
             framing.get("payload_len"),framing.get("payload_crc32"),raw["sha256"],raw["data"],
             record["server_received_at"],parsed["status"],parsed.get("error_code"),parsed.get("reason"),
             "collection",None,_json(record)))
        return int(cursor.lastrowid)

    @staticmethod
    def _assert_camera_source_status_binding(
        db: sqlite3.Connection,
        envelope: dict[str, Any],
        timer: dict[str, Any],
    ) -> None:
        """Bind a configured camera runtime state to the latest applied timer."""

        if timer["config_version"] is None:
            return
        payload = envelope["payload"]
        command_row = db.execute(
            "SELECT * FROM commands WHERE device_id=? AND cmd_id=?",
            (envelope["device_id"], payload["command_id"]),
        ).fetchone()
        latest_applied = db.execute(
            """SELECT id,cmd_id FROM commands
               WHERE device_id=? AND cmd='configure_photo_timer' AND status='applied'
               ORDER BY id DESC LIMIT 1""",
            (envelope["device_id"],),
        ).fetchone()
        if (
            command_row is None
            or latest_applied is None
            or command_row["id"] != latest_applied["id"]
            or command_row["status"] != "applied"
            or command_row["cmd"] != "configure_photo_timer"
            or not command_row["ack_json"]
        ):
            raise ValueError("camera source_status is not bound to the latest applied timer")
        try:
            command = json.loads(command_row["payload_json"])
            command_payload = command["payload"]
            ack = json.loads(command_row["ack_json"])
            ack_timer = ack["timer_state"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("camera source_status timer evidence is unreadable") from error
        immutable = {
            "config_version": command_payload.get("config_version"),
            "interval_seconds": command_payload.get("interval_seconds"),
            "session_expires_at_unix_ms": command_payload.get(
                "session_expires_at_unix_ms"
            ),
            "max_photos": command_payload.get("max_photos"),
        }
        if (
            ack.get("status") != "applied"
            or ack.get("server_disposition")
            not in {"terminal_ack_applied", "terminal_state_refresh_applied"}
            or not isinstance(ack_timer, dict)
            or any(timer[field] != value for field, value in immutable.items())
            or payload["authorization_session_id"]
            != command_payload.get("authorization_session_id")
            or any(ack_timer.get(field) != value for field, value in immutable.items())
            or type(ack_timer.get("enabled")) is not bool
            or type(ack_timer.get("captured_count")) is not int
            or timer["captured_count"] < ack_timer["captured_count"]
            or (ack_timer["enabled"] is False and timer["enabled"] is True)
            or (command_payload.get("enabled") is False and timer["enabled"] is True)
        ):
            raise ValueError("camera source_status conflicts with verified timer state")

    def ingest(self, raw_body: bytes, record: dict[str, Any], *, transport: str) -> dict[str, Any]:
        if len(raw_body) > MAX_FRAME_BYTES:
            raise CollectionError("collection_body_too_large", "collection frame exceeds 64 KiB", 413)
        if transport not in {"wifi", "lte"}:
            raise CollectionError("invalid_collection_transport", "X-EgoLink-Transport must identify the actual sending interface")
        if record["parse_result"].get("status") != "ok":
            raise CollectionError("invalid_collection_frame", "collection EGLK frame did not pass length and checksum validation")
        # Framing has already been checked by Message Hub's existing parser.
        separator = b"\r\n\r\n" if b"\r\n\r\n" in raw_body else b"\n\n"
        payload_bytes = raw_body.split(separator, 1)[1]
        envelope = decode_envelope(payload_bytes, record)
        enforce_collection_privacy(envelope)
        camera_metadata = None
        if envelope["source"] == "camera":
            try:
                camera_metadata = self.hub.photos.validate_metadata(envelope)
            except PhotoStoreError as error:
                raise CollectionError(error.code, str(error), error.status) from error
        camera_status_timer = None
        camera_status_shape_error = None
        if (
            envelope["source"] == "source_status"
            and envelope["payload"].get("source") == "camera"
        ):
            try:
                camera_status_timer = validate_camera_source_status(envelope)
            except (ValueError, CollectionError) as error:
                camera_status_shape_error = str(error)
        preview = inspect_source(envelope)
        ego_state, ego_projection = _ego_state_projection(envelope)
        if envelope["source"] == "device":
            # This describes only the optional projection. Raw collection and
            # its durable ACK remain truthful even for old/invalid state data.
            preview["ego_state_projection"] = ego_projection
        if camera_status_shape_error is not None:
            preview.update(
                status="parse_error",
                error_code="CAMERA_SOURCE_STATUS_INVALID",
                reason=camera_status_shape_error,
                sample_count=0,
            )
        record["parse_result"] = {"status": "ok" if preview["status"] == "ok" else "malformed", "derived_message_type": "collection", "collection_parse_status": preview["status"], "parser_version": preview["parser_version"]}
        record["retention"] = {
            "privacy_class": (
                "private_image_metadata"
                if envelope["source"] == "camera"
                else "private_location"
            ),
            "redacted": False,
        }
        record["fw_version"] = envelope["fw_version"]
        record["test_run_id"] = envelope.get("test_run_id") or envelope["session_id"]
        digest = hashlib.sha256(raw_body).hexdigest()
        received = record["server_received_at"]
        if camera_metadata is not None:
            camera_metadata["server_received_at"] = received
            camera_metadata["collection_claimed_transport"] = transport
            camera_metadata["collection_delivery_result"] = "accepted"
        conflict = False
        with self.hub.connection() as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            # This is the persistence-transaction timestamp, taken only after
            # SQLite grants the write lock.  It must never predate an arbitrary
            # lock wait while being presented as persistence evidence.
            persisted = _now()
            if camera_metadata is not None:
                camera_metadata["server_persisted_at"] = persisted
            if camera_status_timer is not None and camera_status_shape_error is None:
                try:
                    self._assert_camera_source_status_binding(
                        db, envelope, camera_status_timer
                    )
                except (ValueError, sqlite3.Error) as error:
                    preview.update(
                        status="parse_error",
                        error_code="CAMERA_SOURCE_STATUS_UNBOUND",
                        reason=str(error),
                        sample_count=0,
                    )
                    record["parse_result"] = {
                        "status": "malformed",
                        "derived_message_type": "collection",
                        "collection_parse_status": preview["status"],
                        "parser_version": preview["parser_version"],
                    }
            existing = db.execute("SELECT * FROM collection_records WHERE device_id=? AND observation_id=?", (envelope["device_id"], envelope["observation_id"])).fetchone()
            existing_photo = None
            if camera_metadata is not None:
                try:
                    existing_photo = self.hub.photos.assert_metadata_identity(db, camera_metadata)
                    if existing_photo is None:
                        self.hub.photos.assert_authorized_session(db, camera_metadata)
                except PhotoStoreError as error:
                    raise CollectionError(error.code, str(error), error.status) from error
            if existing is not None:
                conflict = existing["payload_sha256"] != digest
                result = "conflict" if conflict else "duplicate"
                raw_id = self._insert_raw(db, record) if conflict else None
                persisted = existing["persisted_at"]
            else:
                result = "accepted"
                raw_id = self._insert_raw(db, record)
                inserted = db.execute("""INSERT INTO collection_records
                    (device_id,observation_id,raw_frame_id,payload_sha256,source,stream_id,sequence_id,boot_count,
                    clock_domain,event_monotonic_ns,event_utc,session_id,fw_version,config_id,acquisition_status,
                    parse_status,sample_count,frame_bytes,received_at,persisted_at,envelope_json,preview_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (envelope["device_id"],envelope["observation_id"],raw_id,digest,envelope["source"],envelope["stream_id"],
                     envelope["sequence_id"],envelope["boot_count"],envelope["monotonic_clock_domain_id"],envelope["timestamp_monotonic_ns"],
                     _utc_index(envelope["timestamp_utc"]),envelope["session_id"],envelope["fw_version"],envelope["config_id"],envelope["status"],
                     preview["status"],preview["sample_count"],len(raw_body),received,persisted,_json(envelope),_json(preview)))
                target = envelope["payload"].get("source")
                if (
                    envelope["source"] == "source_status"
                    and preview["status"] == "ok"
                    and isinstance(target, str)
                    and target in SOURCES | {"camera", "audio"}
                ):
                    db.execute("""INSERT INTO collection_source_states
                        (device_id,target_source,record_id,boot_count,event_monotonic_ns,sequence_id) VALUES(?,?,?,?,?,?)
                        ON CONFLICT(device_id,target_source) DO UPDATE SET
                        record_id=excluded.record_id,boot_count=excluded.boot_count,
                        event_monotonic_ns=excluded.event_monotonic_ns,sequence_id=excluded.sequence_id
                        WHERE (excluded.boot_count,excluded.event_monotonic_ns,excluded.sequence_id) >
                        (collection_source_states.boot_count,collection_source_states.event_monotonic_ns,collection_source_states.sequence_id)""",
                        (envelope["device_id"], target, inserted.lastrowid, envelope["boot_count"], envelope["timestamp_monotonic_ns"], envelope["sequence_id"]))
                if ego_state is not None:
                    rec_id = int(inserted.lastrowid)
                    db.execute("""INSERT INTO collection_ego_states
                        (device_id,observation_id,record_id,boot_count,event_monotonic_ns,sequence_id,
                         event_utc,received_at,spatial_mobility,posture_anomaly,device_wear_state,
                         confidence,window_duration_ms,primary_evidence_digest,is_mock,
                         reason_codes_json,evidence_summary_json,ego_state_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (envelope["device_id"],envelope["observation_id"],rec_id,
                         ego_state["boot_count"],ego_state["timestamp_monotonic_ns"],envelope["sequence_id"],
                         ego_state["timestamp_utc"],received,
                         ego_state["spatial_mobility"],ego_state["posture_anomaly"],ego_state["device_wear_state"],
                         ego_state["confidence"],ego_state["window_duration_ms"],ego_state["primary_evidence_digest"],
                         1 if ego_state["is_mock"] else 0,_json(ego_state["reason_codes"]),
                         _json(envelope["payload"]["ego_state"].get("evidence_summary", {})),
                         _json(envelope["payload"]["ego_state"])))
            if camera_metadata is not None and existing_photo is None and not conflict:
                collection_record_id = int(existing["id"] if existing is not None else inserted.lastrowid)
                self.hub.photos.insert_metadata(db, camera_metadata, collection_record_id)
            db.execute("""INSERT INTO collection_delivery_attempts
                (device_id,observation_id,payload_sha256,received_at,claimed_actual_transport,result,conflict_raw_frame_id)
                VALUES(?,?,?,?,?,?,?)""", (envelope["device_id"],envelope["observation_id"],digest,received,transport,result,raw_id if conflict else None))
        # This line is reached only after the raw frame AND index transaction committed.
        if conflict:
            raise CollectionError("collection_identity_conflict", "record identity already has different immutable bytes", 409)
        ack_ms = int(time.time() * 1000)
        return {"ok": True, "result": result, "parse_status": preview["status"], "persisted_at": persisted,
                "delivery_ack": {"contract_version": "egolink.persistent_priority_outbox.ack.v0.1", "ack_id": "ack-" + digest,
                "device_id": envelope["device_id"], "event_id": envelope["observation_id"], "payload_sha256": digest,
                "status": "accepted", "ack_time_ms": ack_ms}}

    def summary(self, device_id: str) -> dict[str, Any]:
        with self.hub.connection() as db:
            aggregates = db.execute("""SELECT source,COUNT(*) records,SUM(frame_bytes) bytes,SUM(sample_count) samples,
                SUM(acquisition_status='no_fix') no_fix,SUM(parse_status='parse_error' OR acquisition_status IN ('error','timeout','parse_error','partial')) errors,
                MAX(received_at) last_server_received_at FROM collection_records WHERE device_id=? GROUP BY source""", (device_id,)).fetchall()
            sources = []
            for aggregate in aggregates:
                latest = db.execute("""SELECT * FROM collection_records WHERE device_id=? AND source=?
                    ORDER BY boot_count DESC,event_monotonic_ns DESC,sequence_id DESC,id DESC LIMIT 1""", (device_id,aggregate["source"])).fetchone()
                sources.append({**dict(aggregate), "latest": self._record_view(latest)})
            delivery = db.execute("SELECT * FROM collection_delivery_attempts WHERE device_id=? ORDER BY id DESC LIMIT 1", (device_id,)).fetchone()
            deliveries = db.execute("SELECT result,COUNT(*) count FROM collection_delivery_attempts WHERE device_id=? GROUP BY result", (device_id,)).fetchall()
            state_rows = db.execute("SELECT s.target_source,c.* FROM collection_source_states s JOIN collection_records c ON c.id=s.record_id WHERE s.device_id=?", (device_id,)).fetchall()
            sessions = db.execute("""SELECT session_id,MAX(boot_count) boot_count,COUNT(*) records
                FROM collection_records WHERE device_id=? AND session_id IS NOT NULL
                GROUP BY session_id ORDER BY MAX(id) DESC LIMIT 100""", (device_id,)).fetchall()
            annotations = db.execute("SELECT annotation_json FROM collection_annotations WHERE device_id=? ORDER BY id DESC LIMIT 20", (device_id,)).fetchall()
        return {"device_id": device_id, "server_now": _now(), "sources": sources,
                "source_states": {row["target_source"]: self._record_view(row) for row in state_rows},
                "latest_ego_state": self.latest_ego_state(device_id),
                "latest_ego_state_projection": self.latest_ego_state_projection(device_id),
                "last_contact": dict(delivery) if delivery else None,
                "sessions": [dict(row) for row in sessions],
                "recent_annotations": [json.loads(row["annotation_json"]) for row in annotations],
                "delivery_counts": {row["result"]: row["count"] for row in deliveries},
                "state_semantics": "last_known_by_source_event_time; current offline cache is unknown",
                "transport_evidence": "authenticated device report; not independent network-path proof"}

    def latest_source_state(
        self, device_id: str, target_source: str
    ) -> dict[str, Any] | None:
        if target_source not in SOURCES | {"camera", "audio"}:
            raise CollectionError("invalid_collection_source", "unknown source", 400)
        with self.hub.connection() as db:
            row = db.execute(
                """SELECT c.* FROM collection_source_states s
                   JOIN collection_records c ON c.id=s.record_id
                   WHERE s.device_id=? AND s.target_source=?""",
                (device_id, target_source),
            ).fetchone()
        return self._record_view(row) if row is not None else None

    def latest_records(
        self,
        device_id: str,
        *,
        source: str | None = None,
        status: str | None = None,
        limit: int = 10,
        since_id: int | None = None,
    ) -> dict[str, Any]:
        if source is not None and source not in SOURCES:
            raise CollectionError("invalid_collection_source", "unknown source", 400)
        bound_limit = max(1, min(limit, 100))
        with self.hub.connection() as db:
            if since_id is not None:
                where = ["device_id=?", "id>?"]
                args: list[Any] = [device_id, since_id]
                if source is not None:
                    where.append("source=?")
                    args.append(source)
                if status is not None:
                    where.append("acquisition_status=?")
                    args.append(status)
                sql = f"SELECT * FROM collection_records WHERE {' AND '.join(where)} ORDER BY id ASC LIMIT ?"
                rows = db.execute(sql, (*args, bound_limit)).fetchall()
            else:
                where = ["device_id=?"]
                args = [device_id]
                if source is not None:
                    where.append("source=?")
                    args.append(source)
                if status is not None:
                    where.append("acquisition_status=?")
                    args.append(status)
                sql = f"SELECT * FROM collection_records WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?"
                rows = db.execute(sql, (*args, bound_limit)).fetchall()
            records = [self._record_view(r) for r in rows]
            latest_id = max((r["row_id"] for r in records), default=(since_id or 0))
            return {
                "ok": True,
                "device_id": device_id,
                "source": source,
                "status": status,
                "count": len(records),
                "latest_id": latest_id,
                "records": records,
            }

    def annotate(self, device_id: str, raw_body: bytes, *, operator_id: str) -> dict[str, Any]:
        if len(raw_body) > 8192:
            raise CollectionError("annotation_body_too_large", "annotation must be at most 8 KiB", 413)
        try:
            value = json.loads(raw_body.decode("utf-8"), object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise CollectionError("invalid_annotation", "annotation must be valid UTF-8 JSON") from error
        fields = {"annotation_id", "session_id", "scene", "wearing", "note", "boot_count", "timestamp_monotonic_ns"}
        if not isinstance(value, dict) or set(value) != fields:
            raise CollectionError("invalid_annotation", "annotation fields do not match the supported form")
        _identifier(value["annotation_id"], "annotation_id")
        if value["session_id"] is not None:
            _identifier(value["session_id"], "session_id")
        for field, bound in (("scene", 160), ("wearing", 160), ("note", 1024)):
            if not isinstance(value[field], str) or len(value[field]) > bound:
                raise CollectionError("invalid_annotation", f"{field} is not bounded text")
        if not any(value[field].strip() for field in ("scene", "wearing", "note")):
            raise CollectionError("invalid_annotation", "at least one annotation field must contain text")
        if value["boot_count"] is not None:
            _integer(value["boot_count"], "boot_count", maximum=4_294_967_295)
        if value["timestamp_monotonic_ns"] is not None:
            _integer(value["timestamp_monotonic_ns"], "timestamp_monotonic_ns", maximum=9_007_199_254_740_991)
        if value["timestamp_monotonic_ns"] is not None and value["boot_count"] is None:
            raise CollectionError("invalid_annotation", "a monotonic reference requires its boot reference")
        digest = hashlib.sha256(_json(value).encode()).hexdigest()
        annotation = {**value, "device_id": device_id, "source": "operator_annotation", "server_annotation_time": _now(),
                      "operator_id": operator_id, "time_reference_quality": "operator_entered_unsynchronized" if value["boot_count"] is not None else "no_device_clock_reference"}
        with self.hub.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM collection_annotations WHERE device_id=? AND annotation_id=?", (device_id, value["annotation_id"])).fetchone()
            if prior:
                if prior["payload_sha256"] != digest:
                    raise CollectionError("annotation_identity_conflict", "annotation identity already contains different text", 409)
                return {"ok": True, "result": "duplicate", "annotation": json.loads(prior["annotation_json"])}
            if value["session_id"] is not None and not db.execute("SELECT 1 FROM collection_records WHERE device_id=? AND session_id=? LIMIT 1", (device_id, value["session_id"])).fetchone():
                raise CollectionError("annotation_session_unknown", "the selected session has no received device record")
            db.execute("INSERT INTO collection_annotations(device_id,annotation_id,session_id,created_at,payload_sha256,annotation_json) VALUES(?,?,?,?,?,?)", (device_id, value["annotation_id"], value["session_id"], annotation["server_annotation_time"], digest, _json(annotation)))
        return {"ok": True, "result": "accepted", "annotation": annotation}

    @staticmethod
    def _record_view(row: sqlite3.Row) -> dict[str, Any]:
        envelope = json.loads(row["envelope_json"])
        preview = json.loads(row["preview_json"])
        if envelope.get("source") == "device":
            _, preview["ego_state_projection"] = _ego_state_projection(envelope)
        return {"row_id": row["id"], "envelope": envelope,
                "preview": preview, "frame_bytes": row["frame_bytes"],
                "payload_sha256": row["payload_sha256"], "server_received_at": row["received_at"], "persisted_at": row["persisted_at"]}

    @staticmethod
    def _ego_state_row_view(row: sqlite3.Row) -> dict[str, Any] | None:
        # Validate the immutable source again, including rows indexed before
        # this adapter existed. No migration/deletion or trusting coerced SQL
        # columns is needed to hide an invalid historical projection.
        try:
            envelope = json.loads(row["envelope_json"])
            state, projection = _ego_state_projection(envelope)
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
        if state is None or envelope["device_id"] != row["device_id"] or envelope["observation_id"] != row["observation_id"]:
            return None
        return {
            "contract_version": EGO_VIEW_VERSION,
            "state": state,
            "evidence_summary": envelope["payload"]["ego_state"].get("evidence_summary", {}),
            "provenance": {
                "identity_source": projection["identity_source"],
                "digest_verification": "not_performed",
                "observation_id": envelope["observation_id"], "record_id": row["record_id"],
                "sequence_id": envelope["sequence_id"],
                "monotonic_clock_domain_id": envelope["monotonic_clock_domain_id"],
                "fw_version": envelope["fw_version"], "config_id": envelope["config_id"],
                "session_id": envelope["session_id"],
                "timestamp_source": envelope["timestamp_source"],
                "timestamp_quality": envelope["timestamp_quality"],
            },
            "receipt": {"server_received_at": row["received_at"], "persisted_at": row["persisted_at"]},
            "storage": {
                "backend": "message_hub_sqlite",
                "encrypted_at_rest": False,
                "automatic_expiry": False,
                "user_private_endpoint_verified": False,
            },
        }

    def latest_ego_state(self, device_id: str) -> dict[str, Any] | None:
        states = self.ego_state_timeline(device_id, limit=1)
        return states[0] if states else None

    def latest_ego_state_projection(self, device_id: str) -> dict[str, Any] | None:
        """Diagnose the newest state-bearing DEVICE packet, including quarantine.

        A following health-only DEVICE packet is expected after split emission;
        it must not hide an invalid/unavailable state or report false absence.
        Stream the existing source index, stopping at the first state payload.
        Older firmware can require scanning its complete DEVICE history.
        """
        with self.hub.connection() as db:
            rows = db.execute(
                """SELECT envelope_json,received_at,id FROM collection_records
                   WHERE device_id=? AND source='device'
                   ORDER BY boot_count DESC,event_monotonic_ns DESC,sequence_id DESC,id DESC""",
                (device_id,),
            )
            for row in rows:
                envelope = json.loads(row["envelope_json"])
                payload = envelope.get("payload")
                if not isinstance(payload, dict) or "ego_state" not in payload:
                    continue
                _, projection = _ego_state_projection(envelope)
                return {**projection, "observation_id": envelope["observation_id"],
                        "record_id": row["id"], "boot_count": envelope["boot_count"],
                        "sequence_id": envelope["sequence_id"],
                        "timestamp_monotonic_ns": envelope["timestamp_monotonic_ns"],
                        "server_received_at": row["received_at"]}
        return None

    def ego_state_timeline(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        bound_limit = max(1, min(limit, 200))
        candidates: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
        with self.hub.connection() as db:
            rows = db.execute(
                """SELECT e.*, c.envelope_json, c.persisted_at,
                          c.boot_count source_boot_count, c.event_monotonic_ns source_monotonic_ns,
                          c.sequence_id source_sequence_id
                   FROM collection_ego_states e JOIN collection_records c ON c.id=e.record_id
                   WHERE e.device_id=? AND c.device_id=e.device_id
                   ORDER BY c.boot_count DESC, c.event_monotonic_ns DESC, c.sequence_id DESC, e.id DESC""",
                (device_id,),
            )
            for row in rows:
                # A legacy index may contain envelope time instead of the
                # earlier evaluation time. Canonical time never exceeds its
                # source envelope (checked by the adapter), so that envelope
                # supplies a safe upper bound for lazy scanning. Keep at most
                # limit valid views in memory; invalid/very delayed historical
                # data may still require scanning the complete device history.
                upper_bound = (row["source_boot_count"], row["source_monotonic_ns"], row["source_sequence_id"], row["id"])
                if len(candidates) == bound_limit and upper_bound <= candidates[-1][0]:
                    break
                view = self._ego_state_row_view(row)
                if view is not None:
                    state = view["state"]
                    key = (state["boot_count"], state["timestamp_monotonic_ns"], view["provenance"]["sequence_id"], row["id"])
                    candidates.append((key, view))
                    candidates.sort(key=lambda item: item[0], reverse=True)
                    del candidates[bound_limit:]
        return [view for _, view in candidates]

    def page(self, device_id: str, query: dict[str, list[str]], *, raw: bool = False) -> dict[str, Any]:
        schema = export_schema() if raw else None
        allowed = {"source", "session_id", "from_utc", "to_utc", "page_size", "cursor"}
        if set(query) - allowed or any(len(values) != 1 for values in query.values()):
            raise CollectionError("invalid_collection_query", "unknown or repeated collection query", 400)
        options = {key: values[0] for key, values in query.items()}
        try:
            page_size = int(options.get("page_size", "50"))
        except ValueError as error:
            raise CollectionError("invalid_collection_query", "page_size must be an integer", 400) from error
        if not 1 <= page_size <= MAX_PAGE_RECORDS:
            raise CollectionError("invalid_collection_query", "page_size must be 1-100", 400)
        filters = {key: options.get(key) or None for key in ("source", "session_id", "from_utc", "to_utc")}
        if filters["source"] is not None and filters["source"] not in SOURCES:
            raise CollectionError("invalid_collection_query", "unknown source", 400)
        if filters["session_id"] is not None:
            _identifier(filters["session_id"], "session_id")
        for key in ("from_utc", "to_utc"):
            _utc(filters[key], key)
        if filters["from_utc"] is not None and filters["to_utc"] is not None and _utc_index(filters["from_utc"]) > _utc_index(filters["to_utc"]):
            raise CollectionError("invalid_collection_query", "from_utc is after to_utc", 400)
        query_hash = hashlib.sha256(_json([device_id, filters, raw, schema["sha256"] if schema else None]).encode()).hexdigest()
        after, snapshot = 0, None
        annotation_after, annotation_snapshot, delivery_after, delivery_snapshot = 0, None, 0, None
        if options.get("cursor"):
            try:
                if len(options["cursor"]) > 1024:
                    raise ValueError("cursor over limit")
                cursor = json.loads(base64.urlsafe_b64decode(options["cursor"]).decode())
                if cursor["q"] != query_hash:
                    raise ValueError("cursor filters changed")
                after, snapshot = _integer(cursor["a"], "cursor after"), _integer(cursor["s"], "cursor snapshot")
                if raw:
                    annotation_after = _integer(cursor["an"], "annotation after")
                    annotation_snapshot = _integer(cursor["sn"], "annotation snapshot")
                    delivery_after = _integer(cursor["ad"], "delivery after")
                    delivery_snapshot = _integer(cursor["sd"], "delivery snapshot")
                    if annotation_after > annotation_snapshot or delivery_after > delivery_snapshot:
                        raise ValueError("metadata cursor outside snapshot")
                if after > snapshot:
                    raise ValueError("cursor outside snapshot")
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                raise CollectionError("invalid_collection_cursor", "cursor does not match this export", 400) from error
        with self.hub.connection() as db:
            if snapshot is None:
                snapshot = db.execute("SELECT COALESCE(MAX(id),0) FROM collection_records WHERE device_id=?", (device_id,)).fetchone()[0]
                annotation_snapshot = db.execute("SELECT COALESCE(MAX(id),0) FROM collection_annotations WHERE device_id=?", (device_id,)).fetchone()[0]
                delivery_snapshot = db.execute("SELECT COALESCE(MAX(id),0) FROM collection_delivery_attempts WHERE device_id=?", (device_id,)).fetchone()[0]
            where, args = ["c.device_id=?", "c.id>?", "c.id<=?"], [device_id, after, snapshot]
            normal, normal_args = [], []
            for field, column, operator in (("source", "source", "="), ("session_id", "session_id", "="), ("from_utc", "event_utc", ">="), ("to_utc", "event_utc", "<=")):
                if filters[field] is not None:
                    normal.append(f"c.{column}{operator}?")
                    normal_args.append(_utc_index(filters[field]) if field in {"from_utc", "to_utc"} else filters[field])
            if normal:
                expression = " AND ".join(normal)
                if raw:
                    # Context survives source/time filtering; raw export never loses its anchors/config/loss summaries.
                    expression = "(" + expression + ") OR c.source IN ('time_anchor','source_status','session','loss')"
                where.append("(" + expression + ")")
                args.extend(normal_args)
            rows = db.execute("SELECT c.*,r.record_json raw_record_json FROM collection_records c JOIN raw_frames r ON r.id=c.raw_frame_id WHERE " + " AND ".join(where) + " ORDER BY c.id LIMIT ?", (*args, page_size + 1)).fetchall()
            records, byte_count = [], 0
            for row in rows[:page_size]:
                view = self._record_view(row)
                if raw:
                    view["raw_frame"] = json.loads(row["raw_record_json"])
                size = len(_json(view).encode())
                if records and byte_count + size > MAX_PAGE_BYTES:
                    break
                records.append(view)
                byte_count += size
            observations_done = len(records) == len(rows)
            if records:
                after = records[-1]["row_id"]
            annotations, attempts = [], []
            annotations_done = deliveries_done = not raw
            if raw and observations_done:
                room = page_size - len(records)
                annotation_where = "device_id=? AND id>? AND id<=?"
                annotation_args: list[Any] = [device_id, annotation_after, annotation_snapshot]
                if filters["session_id"] is not None:
                    annotation_where += " AND (session_id=? OR session_id IS NULL)"
                    annotation_args.append(filters["session_id"])
                annotation_rows = db.execute("SELECT * FROM collection_annotations WHERE " + annotation_where + " ORDER BY id LIMIT ?", (*annotation_args, room + 1)).fetchall()
                for row in annotation_rows[:room]:
                    item = json.loads(row["annotation_json"])
                    size = len(_json(item).encode())
                    if records or annotations:
                        if byte_count + size > MAX_PAGE_BYTES:
                            break
                    annotations.append(item)
                    annotation_after = row["id"]
                    byte_count += size
                annotations_done = len(annotations) == len(annotation_rows)
                if annotations_done:
                    room -= len(annotations)
                    # Receipt attempts are exported separately from their immutable observation.
                    delivery_where = ["d.device_id=?", "d.id>?", "d.id<=?", "c.id<=?"]
                    delivery_args: list[Any] = [device_id, delivery_after, delivery_snapshot, snapshot]
                    if normal:
                        delivery_where.append("(" + expression + ")")
                        delivery_args.extend(normal_args)
                    delivery_rows = db.execute("SELECT d.* FROM collection_delivery_attempts d JOIN collection_records c ON c.device_id=d.device_id AND c.observation_id=d.observation_id WHERE " + " AND ".join(delivery_where) + " ORDER BY d.id LIMIT ?", (*delivery_args, room + 1)).fetchall()
                    for row in delivery_rows[:room]:
                        item = dict(row)
                        item["transport_evidence"] = "device_reported_interface"
                        if row["conflict_raw_frame_id"] is not None:
                            conflict = db.execute("SELECT record_json FROM raw_frames WHERE id=?", (row["conflict_raw_frame_id"],)).fetchone()
                            item["conflict_raw_frame"] = json.loads(conflict["record_json"])
                        size = len(_json(item).encode())
                        if records or annotations or attempts:
                            if byte_count + size > MAX_PAGE_BYTES:
                                break
                        attempts.append(item)
                        delivery_after = row["id"]
                        byte_count += size
                    deliveries_done = len(attempts) == len(delivery_rows)
            exhausted = observations_done and annotations_done and deliveries_done
            next_cursor = None if exhausted else base64.urlsafe_b64encode(_json({"q": query_hash, "a": after, "s": snapshot, "an": annotation_after, "sn": annotation_snapshot, "ad": delivery_after, "sd": delivery_snapshot}).encode()).decode()
        return {"contract_version": CONTRACT_VERSION, "device_id": device_id, "filters": filters, "records": records,
                "schema": schema,
                "annotations": annotations, "delivery_attempts": attempts,
                "page": {"snapshot_max_id": snapshot, "annotation_snapshot_max_id": annotation_snapshot if raw else None, "delivery_snapshot_max_id": delivery_snapshot if raw else None, "snapshot_frozen": True, "exhausted": exhausted, "next_cursor": next_cursor, "record_count": len(records), "annotation_count": len(annotations), "delivery_attempt_count": len(attempts), "bytes": byte_count},
                "export_semantics": {"raw_unchanged": raw, "order": "durable_receive_id; event times remain in envelope", "context_included": raw, "absolute_time_unknown_records": "included unless UTC filter is specified"}}


def jsonl_page(page: dict[str, Any]) -> bytes:
    manifest = {"kind": "collection_export_manifest", **{key: value for key, value in page.items() if key not in {"records", "annotations", "delivery_attempts"}}}
    lines = [_json(manifest)]
    lines.extend(_json({"kind": "collection_record", **record}) for record in page["records"])
    lines.extend(_json({"kind": "operator_annotation", **annotation}) for annotation in page["annotations"])
    lines.extend(_json({"kind": "delivery_attempt", **attempt}) for attempt in page["delivery_attempts"])
    return ("\n".join(lines) + "\n").encode("utf-8")
