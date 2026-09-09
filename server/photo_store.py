"""Private, durable JPEG persistence for camera collection observations.

Camera metadata remains an immutable ``egolink.collection.v1`` observation.
JPEG bytes are intentionally stored outside raw_frames and outside the public
web root.  A content acknowledgement is returned only after the file has been
fsynced, atomically renamed, and the SQLite row has committed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
from typing import Any

if os.name != "nt":  # pragma: no cover - exercised by the Linux service.
    import fcntl


DEFAULT_MAX_PHOTO_BYTES = 64 * 1024
DEFAULT_DEVICE_QUOTA_BYTES = 32 * 1024 * 1024
MAX_PAGE_SIZE = 100
MAX_EXPORT_RECORDS = 5_000
BACKFILL_THRESHOLD_SECONDS = 60
CAMERA_CLOCK_SKEW_SECONDS = 120
MAX_PHOTO_RETENTION_SECONDS = 7 * 24 * 60 * 60
AUTHORIZABLE_CAMERA_CLOCKS = frozenset(
    {
        ("gnss", "gnss_synchronized"),
        ("sntp_anchor", "network_time_unverified_accuracy"),
    }
)
PHOTO_CONTROL_COMMANDS = frozenset({"capture_photo_once", "configure_photo_timer"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)
CAMERA_PAYLOAD_FIELDS = frozenset(
    {
        "photo_id",
        "trigger_reason",
        "command_id",
        "config_version",
        "capture_result",
        "local_save_status",
        "device_upload_status",
        "media_type",
        "width",
        "height",
        "byte_length",
        "sha256",
        "storage_kind",
        "camera_model",
        "driver_profile",
        "location_ref",
        "authorization_session_id",
        "retention_expires_at",
        "training_allowed",
    }
)
LOGGER = logging.getLogger(__name__)


class PhotoStoreError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 422):
        super().__init__(detail)
        self.code = code
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _safe_id(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise PhotoStoreError(
            "invalid_camera_metadata", f"{name} must be a bounded identifier"
        )
    return value


def _bounded_text(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or any(ord(character) < 0x20 for character in value)
    ):
        raise PhotoStoreError(
            "invalid_camera_metadata", f"{name} must be bounded text"
        )
    return value


def _nullable_integer(
    value: Any, name: str, *, minimum: int, maximum: int
) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise PhotoStoreError(
            "invalid_camera_metadata", f"{name} is outside its integer range"
        )
    return value


def _validate_location_ref(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    expected = {"observation_id", "event_utc", "timestamp_quality"}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhotoStoreError(
            "invalid_camera_metadata", "location_ref has an unsupported shape"
        )
    _safe_id(value["observation_id"], "location_ref.observation_id")
    if value["event_utc"] is not None:
        event_utc = value["event_utc"]
        if not isinstance(event_utc, str) or not event_utc.endswith("Z"):
            raise PhotoStoreError(
                "invalid_camera_metadata", "location_ref.event_utc is invalid"
            )
        try:
            datetime.fromisoformat(event_utc[:-1] + "+00:00")
        except ValueError as error:
            raise PhotoStoreError(
                "invalid_camera_metadata", "location_ref.event_utc is invalid"
            ) from error
    _bounded_text(value["timestamp_quality"], "location_ref.timestamp_quality")
    return value


def _utc(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 40:
        raise PhotoStoreError(
            "invalid_camera_metadata", f"{name} must be an explicit UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PhotoStoreError(
            "invalid_camera_metadata", f"{name} must be an explicit UTC timestamp"
        ) from error
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _age_seconds(later: str, earlier: str | None) -> float | None:
    if earlier is None:
        return None
    try:
        later_value = datetime.fromisoformat(later.replace("Z", "+00:00"))
        earlier_value = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return max(0.0, round((later_value - earlier_value).total_seconds(), 3))


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _jpeg_geometry(content: bytes) -> tuple[int, int]:
    """Validate the bounded baseline JPEG profile used by the OV5640 path.

    The VPS remains stdlib-only, so this is deliberately a baseline structure
    verifier rather than a pixel decoder.  It validates table definitions and
    references, component identity, the single sequential scan, entropy byte
    stuffing/restart ordering, geometry, and an exact terminal EOI.  A browser
    decode is still a separate live acceptance fact.
    """

    if len(content) < 12 or content[:2] != b"\xff\xd8":
        raise PhotoStoreError("invalid_jpeg", "photo content is not a complete JPEG")
    offset = 2
    width: int | None = None
    height: int | None = None
    saw_scan = False
    saw_entropy_data = False
    in_scan = False
    quantization_tables: set[int] = set()
    huffman_tables: set[tuple[int, int]] = set()
    frame_components: dict[int, tuple[int, int, int]] = {}
    restart_interval: int | None = None
    expected_restart = 0
    entropy_since_restart = False
    while offset < len(content):
        if in_scan:
            marker_start = content.find(b"\xff", offset)
            if marker_start < 0:
                break
            if marker_start > offset:
                saw_entropy_data = True
                entropy_since_restart = True
            marker_value = marker_start + 1
            while marker_value < len(content) and content[marker_value] == 0xFF:
                marker_value += 1
            if marker_value >= len(content):
                break
            marker = content[marker_value]
            if marker == 0x00:
                saw_entropy_data = True
                entropy_since_restart = True
                offset = marker_value + 1
                continue
            if 0xD0 <= marker <= 0xD7:
                if (
                    restart_interval is None
                    or marker != 0xD0 + expected_restart
                    or not entropy_since_restart
                ):
                    raise PhotoStoreError(
                        "invalid_jpeg", "JPEG restart marker sequence is invalid"
                    )
                expected_restart = (expected_restart + 1) % 8
                entropy_since_restart = False
                offset = marker_value + 1
                continue
            offset = marker_start
            in_scan = False
            continue

        if content[offset] != 0xFF:
            raise PhotoStoreError(
                "invalid_jpeg", "JPEG marker stream contains unframed bytes"
            )
        marker_value = offset + 1
        while marker_value < len(content) and content[marker_value] == 0xFF:
            marker_value += 1
        if marker_value >= len(content):
            break
        marker = content[marker_value]
        offset = marker_value + 1
        if marker == 0xD9:
            if (
                offset != len(content)
                or width is None
                or height is None
                or not saw_scan
                or not saw_entropy_data
                or not quantization_tables
                or not huffman_tables
            ):
                raise PhotoStoreError(
                    "invalid_jpeg", "JPEG is missing geometry, scan data, or final EOI"
                )
            return width, height
        if saw_scan:
            raise PhotoStoreError(
                "invalid_jpeg", "baseline JPEG has data after its single scan"
            )
        if marker == 0xD8 or marker == 0x00 or 0xD0 <= marker <= 0xD7:
            raise PhotoStoreError("invalid_jpeg", "JPEG marker ordering is invalid")
        if marker == 0x01:  # TEM is the only standalone marker outside a scan.
            continue
        if offset + 2 > len(content):
            break
        segment_length = int.from_bytes(content[offset : offset + 2], "big")
        if segment_length < 2:
            raise PhotoStoreError("invalid_jpeg", "JPEG segment length is invalid")
        segment_end = offset + segment_length
        if segment_end > len(content):
            break
        if marker in JPEG_SOF_MARKERS:
            if marker != 0xC0 or frame_components:
                raise PhotoStoreError(
                    "invalid_jpeg", "only one 8-bit baseline SOF0 is supported"
                )
            if segment_length < 8:
                raise PhotoStoreError("invalid_jpeg", "JPEG SOF segment is truncated")
            precision = content[offset + 2]
            candidate_height = int.from_bytes(content[offset + 3 : offset + 5], "big")
            candidate_width = int.from_bytes(content[offset + 5 : offset + 7], "big")
            components = content[offset + 7]
            if (
                precision != 8
                or candidate_width <= 0
                or candidate_height <= 0
                or candidate_width > 8192
                or candidate_height > 8192
                or not 1 <= components <= 4
                or segment_length != 8 + 3 * components
            ):
                raise PhotoStoreError("invalid_jpeg", "JPEG SOF geometry is invalid")
            for index in range(components):
                component_offset = offset + 8 + 3 * index
                component_id = content[component_offset]
                sampling = content[component_offset + 1]
                horizontal, vertical = sampling >> 4, sampling & 0x0F
                quantization_id = content[component_offset + 2]
                if (
                    component_id in frame_components
                    or not 1 <= horizontal <= 4
                    or not 1 <= vertical <= 4
                    or quantization_id > 3
                ):
                    raise PhotoStoreError(
                        "invalid_jpeg", "JPEG SOF component definition is invalid"
                    )
                frame_components[component_id] = (
                    horizontal,
                    vertical,
                    quantization_id,
                )
            if sum(horizontal * vertical for horizontal, vertical, _ in frame_components.values()) > 10:
                raise PhotoStoreError(
                    "invalid_jpeg", "JPEG baseline MCU sampling exceeds its limit"
                )
            width, height = candidate_width, candidate_height
        if marker == 0xDB:
            cursor = offset + 2
            while cursor < segment_end:
                table_info = content[cursor]
                cursor += 1
                precision, table_id = table_info >> 4, table_info & 0x0F
                table_bytes = 64
                if precision != 0 or table_id > 3 or cursor + table_bytes > segment_end:
                    raise PhotoStoreError(
                        "invalid_jpeg", "JPEG quantization table is invalid"
                    )
                if any(
                    content[pos] == 0
                    for pos in range(cursor, cursor + table_bytes)
                ):
                    raise PhotoStoreError(
                        "invalid_jpeg", "JPEG quantization table contains zero"
                    )
                quantization_tables.add(table_id)
                cursor += table_bytes
            if cursor != segment_end:
                raise PhotoStoreError(
                    "invalid_jpeg", "JPEG quantization table is truncated"
                )
        if marker == 0xC4:
            cursor = offset + 2
            while cursor < segment_end:
                table_info = content[cursor]
                cursor += 1
                table_class, table_id = table_info >> 4, table_info & 0x0F
                if table_class not in {0, 1} or table_id > 3 or cursor + 16 > segment_end:
                    raise PhotoStoreError("invalid_jpeg", "JPEG Huffman table is invalid")
                counts = content[cursor : cursor + 16]
                cursor += 16
                symbol_count = sum(counts)
                if symbol_count <= 0 or cursor + symbol_count > segment_end:
                    raise PhotoStoreError("invalid_jpeg", "JPEG Huffman symbols are invalid")
                code_space = 1
                for count in counts:
                    code_space = code_space * 2 - count
                    if code_space < 0:
                        raise PhotoStoreError(
                            "invalid_jpeg", "JPEG Huffman code lengths are oversubscribed"
                        )
                symbols = content[cursor : cursor + symbol_count]
                if table_class == 0 and any(symbol > 11 for symbol in symbols):
                    raise PhotoStoreError("invalid_jpeg", "JPEG DC symbols are invalid")
                if table_class == 1 and any(
                    (symbol & 0x0F) > 10
                    or ((symbol & 0x0F) == 0 and symbol not in {0x00, 0xF0})
                    for symbol in symbols
                ):
                    raise PhotoStoreError("invalid_jpeg", "JPEG AC symbols are invalid")
                huffman_tables.add((table_class, table_id))
                cursor += symbol_count
            if cursor != segment_end:
                raise PhotoStoreError("invalid_jpeg", "JPEG Huffman table is truncated")
        if marker == 0xDD:
            if segment_length != 4 or restart_interval is not None:
                raise PhotoStoreError("invalid_jpeg", "JPEG restart interval is invalid")
            restart_interval = int.from_bytes(content[offset + 2 : offset + 4], "big")
            if restart_interval <= 0:
                raise PhotoStoreError("invalid_jpeg", "JPEG restart interval is invalid")
        if marker == 0xDA:
            if width is None or height is None:
                raise PhotoStoreError("invalid_jpeg", "JPEG scan precedes its SOF")
            scan_components = content[offset + 2] if segment_length >= 3 else 0
            if (
                saw_scan
                or scan_components != len(frame_components)
                or segment_length != 6 + 2 * scan_components
            ):
                raise PhotoStoreError("invalid_jpeg", "JPEG SOS segment is invalid")
            scan_ids: set[int] = set()
            for index in range(scan_components):
                component_offset = offset + 3 + 2 * index
                component_id = content[component_offset]
                selector = content[component_offset + 1]
                dc_table, ac_table = selector >> 4, selector & 0x0F
                if (
                    component_id not in frame_components
                    or component_id in scan_ids
                    or (0, dc_table) not in huffman_tables
                    or (1, ac_table) not in huffman_tables
                ):
                    raise PhotoStoreError(
                        "invalid_jpeg", "JPEG scan component/table reference is invalid"
                    )
                scan_ids.add(component_id)
            spectral_offset = offset + 3 + 2 * scan_components
            if (
                scan_ids != set(frame_components)
                or any(values[2] not in quantization_tables for values in frame_components.values())
                or content[spectral_offset : spectral_offset + 3] != b"\x00\x3f\x00"
            ):
                raise PhotoStoreError(
                    "invalid_jpeg", "JPEG baseline scan parameters are invalid"
                )
            saw_scan = True
            in_scan = True
        offset = segment_end
    raise PhotoStoreError("invalid_jpeg", "photo content is a truncated JPEG")


class PhotoStore:
    def __init__(
        self,
        hub: Any,
        root: Path,
        *,
        max_photo_bytes: int = DEFAULT_MAX_PHOTO_BYTES,
        device_quota_bytes: int = DEFAULT_DEVICE_QUOTA_BYTES,
    ) -> None:
        if max_photo_bytes < 4 or device_quota_bytes < max_photo_bytes:
            raise ValueError("photo limits are inconsistent")
        self.hub = hub
        self.root = Path(root).resolve()
        self.max_photo_bytes = max_photo_bytes
        self.device_quota_bytes = device_quota_bytes
        self._write_lock = threading.Lock()
        self._maintenance_lock = threading.Lock()
        self._maintenance_stop: threading.Event | None = None
        self._maintenance_thread: threading.Thread | None = None
        self._private_directory(self.root)
        self._lock_path = self.root / ".photo-store.lock"
        self._lock_path.touch(mode=0o600, exist_ok=True)
        if os.name != "nt":
            os.chmod(self._lock_path, 0o600)
        with hub.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS photo_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    photo_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    collection_record_id INTEGER NOT NULL,
                    session_id TEXT,
                    trigger_reason TEXT NOT NULL,
                    command_id TEXT,
                    config_version TEXT NOT NULL,
                    capture_result TEXT NOT NULL,
                    local_save_status TEXT NOT NULL,
                    device_upload_status TEXT NOT NULL,
                    event_monotonic_ns INTEGER NOT NULL,
                    event_utc TEXT,
                    timestamp_source TEXT NOT NULL,
                    timestamp_quality TEXT NOT NULL,
                    authorization_session_id TEXT NOT NULL,
                    retention_expires_at TEXT NOT NULL,
                    training_allowed INTEGER NOT NULL,
                    location_observation_id TEXT,
                    location_source TEXT,
                    location_event_utc TEXT,
                    location_timestamp_quality TEXT,
                    location_age_seconds REAL,
                    collection_received_at TEXT,
                    collection_persisted_at TEXT,
                    collection_claimed_transport TEXT,
                    collection_delivery_result TEXT,
                    expected_media_type TEXT,
                    expected_width INTEGER,
                    expected_height INTEGER,
                    expected_bytes INTEGER,
                    expected_sha256 TEXT,
                    metadata_sha256 TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    content_status TEXT NOT NULL,
                    content_relative_path TEXT,
                    stored_bytes INTEGER,
                    stored_sha256 TEXT,
                    stored_transport TEXT,
                    stored_at TEXT,
                    content_purge_state TEXT NOT NULL DEFAULT 'not_due',
                    content_purge_error TEXT,
                    content_purged_at TEXT,
                    upload_attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_upload_attempt_at TEXT,
                    last_upload_result TEXT,
                    last_upload_error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(device_id, photo_id),
                    UNIQUE(device_id, observation_id)
                );
                CREATE INDEX IF NOT EXISTS photo_records_device_id
                    ON photo_records(device_id, id DESC);
                CREATE INDEX IF NOT EXISTS photo_records_device_session
                    ON photo_records(device_id, session_id, id DESC);
                CREATE INDEX IF NOT EXISTS photo_records_device_command
                    ON photo_records(device_id, command_id, id);
                CREATE TABLE IF NOT EXISTS photo_capture_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    authorization_session_id TEXT NOT NULL,
                    guardian_id TEXT NOT NULL,
                    retention_expires_at TEXT NOT NULL,
                    training_allowed INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(device_id, authorization_session_id)
                );
                CREATE INDEX IF NOT EXISTS photo_capture_sessions_device
                    ON photo_capture_sessions(device_id, id DESC);
                """
            )
            existing_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(photo_records)")
            }
            migrations = {
                "location_observation_id": "TEXT",
                "timestamp_source": "TEXT NOT NULL DEFAULT 'legacy_unknown'",
                "location_source": "TEXT",
                "location_event_utc": "TEXT",
                "location_timestamp_quality": "TEXT",
                "location_age_seconds": "REAL",
                "collection_received_at": "TEXT",
                "collection_persisted_at": "TEXT",
                "collection_claimed_transport": "TEXT",
                "collection_delivery_result": "TEXT",
                "content_purge_state": "TEXT NOT NULL DEFAULT 'not_due'",
                "content_purge_error": "TEXT",
                "content_purged_at": "TEXT",
                "upload_attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "last_upload_attempt_at": "TEXT",
                "last_upload_result": "TEXT",
                "last_upload_error_code": "TEXT",
            }
            for column, declaration in migrations.items():
                if column not in existing_columns:
                    db.execute(
                        f"ALTER TABLE photo_records ADD COLUMN {column} {declaration}"
                    )
        self._cleanup_temporary_files()
        self.purge_expired()

    @staticmethod
    def _private_directory(path: Path) -> None:
        missing: list[Path] = []
        cursor = path
        while not cursor.exists():
            missing.append(cursor)
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(path, 0o700)
            for created in reversed(missing):
                os.chmod(created, 0o700)
                PhotoStore._fsync_directory(created.parent)

    @contextmanager
    def _exclusive_write(self):
        """Serialize bytes/DB transitions with this process and backups."""

        with self._write_lock:
            with self._lock_path.open("a+b") as lock_file:
                if os.name != "nt":
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if os.name != "nt":
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _cleanup_temporary_files(self) -> int:
        removed = 0
        with self._exclusive_write():
            for path in self.root.rglob(".photo-upload-*.tmp"):
                if not path.is_file():
                    continue
                path.unlink(missing_ok=True)
                self._fsync_directory(path.parent)
                removed += 1
        return removed

    def start_retention_maintenance(self, *, interval_seconds: float = 30.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("photo retention interval must be positive")
        with self._maintenance_lock:
            if self._maintenance_thread is not None:
                if self._maintenance_thread.is_alive():
                    return
                self._maintenance_thread = None
                self._maintenance_stop = None
            stop_event = threading.Event()
            self._maintenance_stop = stop_event

            def sweep() -> None:
                try:
                    while not stop_event.wait(interval_seconds):
                        try:
                            self.purge_expired()
                        except PhotoStoreError:
                            LOGGER.exception("private photo retention sweep failed")
                finally:
                    with self._maintenance_lock:
                        if self._maintenance_thread is threading.current_thread():
                            self._maintenance_thread = None
                            self._maintenance_stop = None

            self._maintenance_thread = threading.Thread(
                target=sweep,
                name="egolink-photo-retention",
                daemon=True,
            )
            self._maintenance_thread.start()

    def stop_retention_maintenance(self) -> None:
        with self._maintenance_lock:
            thread = self._maintenance_thread
            if thread is None:
                return
            stop_event = self._maintenance_stop
            if stop_event is not None:
                stop_event.set()
        thread.join(timeout=5)
        with self._maintenance_lock:
            if self._maintenance_thread is thread and not thread.is_alive():
                self._maintenance_thread = None
                self._maintenance_stop = None

    def validate_metadata(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("source") != "camera":
            raise PhotoStoreError(
                "invalid_camera_metadata", "camera metadata requires source=camera"
            )
        payload = envelope.get("payload")
        if not isinstance(payload, dict) or set(payload) != CAMERA_PAYLOAD_FIELDS:
            raise PhotoStoreError(
                "invalid_camera_metadata", "camera payload has an unsupported shape"
            )
        photo_id = _safe_id(payload["photo_id"], "photo_id")
        command_id = _safe_id(payload["command_id"], "command_id")
        config_version = _safe_id(payload["config_version"], "config_version")
        authorization_session_id = _safe_id(
            payload["authorization_session_id"], "authorization_session_id"
        )
        if envelope.get("session_id") is None or authorization_session_id != envelope.get(
            "session_id"
        ):
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "camera content requires its explicit authorized collection session",
            )
        retention_expires_at = _utc(
            payload["retention_expires_at"], "retention_expires_at"
        )
        if payload["training_allowed"] is not False:
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "camera content is not admitted for training by default",
            )
        if payload["trigger_reason"] not in {"web_manual", "device_timer"}:
            raise PhotoStoreError(
                "invalid_camera_metadata", "trigger_reason is unsupported"
            )
        if payload["capture_result"] not in {
            "captured",
            "capture_failed",
            "not_attempted",
            "outcome_unknown",
        }:
            raise PhotoStoreError(
                "invalid_camera_metadata", "capture_result is unsupported"
            )
        if payload["local_save_status"] not in {
            "saved",
            "save_failed",
            "not_attempted",
            "unknown",
        }:
            raise PhotoStoreError(
                "invalid_camera_metadata", "local_save_status is unsupported"
            )
        if payload["device_upload_status"] not in {
            "pending",
            "uploading",
            "uploaded",
            "not_ready",
        }:
            raise PhotoStoreError(
                "invalid_camera_metadata", "device_upload_status is unsupported"
            )
        result_pair = (
            payload["capture_result"],
            payload["local_save_status"],
        )
        expected_status = {
            ("captured", "saved"): "captured",
            ("captured", "save_failed"): "save_failed",
            ("capture_failed", "not_attempted"): "capture_failed",
            ("not_attempted", "not_attempted"): "not_attempted",
            ("outcome_unknown", "unknown"): "outcome_unknown",
        }.get(result_pair)
        if expected_status is None or envelope.get("status") != expected_status:
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "camera result, local save state, and observation status disagree",
            )
        if (expected_status == "captured") != (envelope.get("missing_reason") is None):
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "camera success must not report a missing reason and failures must explain one",
            )
        if expected_status != "captured":
            _bounded_text(envelope["missing_reason"], "missing_reason")
        if (
            expected_status == "outcome_unknown"
            and envelope["missing_reason"]
            != "capture_outcome_unknown_after_reboot"
        ):
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "recovered unknown capture outcome requires its exact reason",
            )
        _bounded_text(payload["camera_model"], "camera_model")
        _bounded_text(payload["driver_profile"], "driver_profile")
        location_ref = _validate_location_ref(payload["location_ref"])
        width = _nullable_integer(payload["width"], "width", minimum=1, maximum=8192)
        height = _nullable_integer(payload["height"], "height", minimum=1, maximum=8192)
        byte_length = _nullable_integer(
            payload["byte_length"],
            "byte_length",
            minimum=4,
            maximum=self.max_photo_bytes,
        )
        digest = payload["sha256"]
        if digest is not None and (
            not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        ):
            raise PhotoStoreError(
                "invalid_camera_metadata", "sha256 must be lowercase hexadecimal"
            )
        has_durable_content = (
            payload["capture_result"] == "captured"
            and payload["local_save_status"] == "saved"
        )
        content_fields = (
            payload["media_type"],
            width,
            height,
            byte_length,
            digest,
        )
        if has_durable_content:
            if (
                payload["media_type"] != "image/jpeg"
                or any(value is None for value in content_fields[1:])
                or payload["storage_kind"] != "persistent"
                or payload["device_upload_status"] == "not_ready"
            ):
                raise PhotoStoreError(
                    "invalid_camera_metadata",
                    "saved camera content requires complete persistent JPEG metadata",
                )
        elif (
            any(value is not None for value in content_fields)
            or payload["storage_kind"] != "none"
            or payload["device_upload_status"] != "not_ready"
        ):
            raise PhotoStoreError(
                "invalid_camera_metadata",
                "unavailable camera content must not claim saved JPEG metadata",
            )
        normalized = {
            "device_id": envelope["device_id"],
            "photo_id": photo_id,
            "observation_id": envelope["observation_id"],
            "session_id": envelope["session_id"],
            "trigger_reason": payload["trigger_reason"],
            "command_id": command_id,
            "config_version": config_version,
            "capture_result": payload["capture_result"],
            "local_save_status": payload["local_save_status"],
            "device_upload_status": payload["device_upload_status"],
            "authorization_session_id": authorization_session_id,
            "retention_expires_at": retention_expires_at,
            "training_allowed": False,
            "event_monotonic_ns": envelope["timestamp_monotonic_ns"],
            "event_utc": envelope["timestamp_utc"],
            "timestamp_source": envelope["timestamp_source"],
            "timestamp_quality": envelope["timestamp_quality"],
            "expected_media_type": payload["media_type"],
            "expected_width": width,
            "expected_height": height,
            "expected_bytes": byte_length,
            "expected_sha256": digest,
            "location_ref": location_ref,
            "metadata_json": _json(envelope),
        }
        normalized["metadata_sha256"] = hashlib.sha256(
            normalized["metadata_json"].encode("utf-8")
        ).hexdigest()
        return normalized

    def authorize_session(
        self, device_id: str, payload: dict[str, Any], *, guardian_id: str
    ) -> dict[str, Any]:
        expected = {
            "authorization_session_id",
            "retention_expires_at",
            "training_allowed",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise PhotoStoreError(
                "invalid_photo_session",
                "photo authorization session has an unsupported shape",
            )
        _safe_id(device_id, "device_id")
        session_id = _safe_id(
            payload["authorization_session_id"], "authorization_session_id"
        )
        _safe_id(guardian_id, "guardian_id")
        retention_expires_at = _utc(
            payload["retention_expires_at"], "retention_expires_at"
        )
        now_value = datetime.now(timezone.utc)
        retention_value = _timestamp(retention_expires_at)
        if (
            retention_value <= now_value
            or (retention_value - now_value).total_seconds()
            > MAX_PHOTO_RETENTION_SECONDS
        ):
            raise PhotoStoreError(
                "invalid_photo_session",
                "photo authorization retention must be within the next 7 days",
            )
        if payload["training_allowed"] is not False:
            raise PhotoStoreError(
                "invalid_photo_session",
                "photo authorization does not enable training by default",
            )
        now = _now()
        db = self.hub.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM photo_capture_sessions "
                "WHERE device_id=? AND authorization_session_id=?",
                (device_id, session_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["guardian_id"] != guardian_id
                    or existing["retention_expires_at"] != retention_expires_at
                    or existing["training_allowed"] != 0
                    or existing["status"] != "active"
                ):
                    raise PhotoStoreError(
                        "photo_session_identity_conflict",
                        "photo authorization identity already has different content",
                        409,
                    )
                db.commit()
                return self._session_view(existing, "duplicate")
            db.execute(
                """INSERT INTO photo_capture_sessions (
                   device_id,authorization_session_id,guardian_id,
                   retention_expires_at,training_allowed,status,created_at,updated_at
                   ) VALUES (?,?,?,?,0,'active',?,?)""",
                (device_id, session_id, guardian_id, retention_expires_at, now, now),
            )
            db.commit()
            row = db.execute(
                "SELECT * FROM photo_capture_sessions "
                "WHERE device_id=? AND authorization_session_id=?",
                (device_id, session_id),
            ).fetchone()
            return self._session_view(row, "accepted")
        except PhotoStoreError:
            db.rollback()
            raise
        except sqlite3.Error as error:
            db.rollback()
            raise PhotoStoreError(
                "photo_store_error", "photo authorization persistence failed", 500
            ) from error
        finally:
            db.close()

    def validate_control_command(
        self,
        device_id: str,
        command: dict[str, Any],
        *,
        guardian_id: str,
    ) -> None:
        """Validate a Guardian-bound photo command before it enters commands.

        This deliberately does not create another command channel.  The result
        is still persisted and delivered by MessageHubStore.commands.
        """

        _safe_id(device_id, "device_id")
        _safe_id(guardian_id, "guardian_id")
        cmd = command.get("cmd")
        if cmd not in PHOTO_CONTROL_COMMANDS:
            raise PhotoStoreError(
                "invalid_photo_command", "photo command type is unsupported"
            )
        expected_top_level = {"cmd", "cmd_id", "expires_at_unix_ms", "payload"}
        if set(command) != expected_top_level:
            raise PhotoStoreError(
                "invalid_photo_command", "photo command has an unsupported shape"
            )
        payload = command.get("payload")
        capture_fields = {
            "authorization_session_id",
            "retention_expires_at",
            "training_allowed",
            "trigger_reason",
        }
        timer_fields = {
            "authorization_session_id",
            "config_version",
            "enabled",
            "interval_seconds",
            "session_expires_at_unix_ms",
            "retention_expires_at",
            "max_photos",
            "training_allowed",
        }
        expected_payload = capture_fields if cmd == "capture_photo_once" else timer_fields
        if not isinstance(payload, dict) or set(payload) != expected_payload:
            raise PhotoStoreError(
                "invalid_photo_command",
                f"{cmd} payload has an unsupported shape",
            )
        session_id = _safe_id(
            payload.get("authorization_session_id"), "authorization_session_id"
        )
        retention_expires_at = _utc(
            payload.get("retention_expires_at"), "retention_expires_at"
        )
        payload["retention_expires_at"] = retention_expires_at
        retention_ms = int(
            datetime.fromisoformat(
                retention_expires_at[:-1] + "+00:00"
            ).timestamp()
            * 1000
        )
        if payload.get("training_allowed") is not False:
            raise PhotoStoreError(
                "invalid_photo_command", "photo commands cannot enable training"
            )
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        command_expiry = command.get("expires_at_unix_ms")
        if (
            type(command_expiry) is not int
            or command_expiry <= 0
            or command_expiry > now_ms + 10 * 60 * 1000
            or command_expiry > retention_ms
        ):
            raise PhotoStoreError(
                "invalid_photo_command",
                "photo command delivery expiry must not exceed the next 10 minutes",
            )
        command_is_live = command_expiry > now_ms
        require_active = command_is_live
        if cmd == "capture_photo_once":
            if payload.get("trigger_reason") != "web_manual":
                raise PhotoStoreError(
                    "invalid_photo_command",
                    "capture_photo_once requires trigger_reason=web_manual",
                )
        else:
            _safe_id(payload.get("config_version"), "config_version")
            enabled = payload.get("enabled")
            interval_seconds = payload.get("interval_seconds")
            session_expiry = payload.get("session_expires_at_unix_ms")
            max_photos = payload.get("max_photos")
            if type(enabled) is not bool:
                raise PhotoStoreError(
                    "invalid_photo_command", "enabled must be a boolean"
                )
            if (
                type(interval_seconds) is not int
                or not 60 <= interval_seconds <= 86_400
            ):
                raise PhotoStoreError(
                    "invalid_photo_command",
                    "interval_seconds must be between 60 and 86400",
                )
            if type(max_photos) is not int or not 1 <= max_photos <= 1000:
                raise PhotoStoreError(
                    "invalid_photo_command", "max_photos must be between 1 and 1000"
                )
            if (
                type(session_expiry) is not int
                or session_expiry > retention_ms
                or command_expiry > session_expiry
                or (enabled and command_is_live and session_expiry <= now_ms)
            ):
                raise PhotoStoreError(
                    "invalid_photo_command",
                    "timer session expiry must be bounded by photo retention",
                )
            require_active = enabled and command_is_live

        with self.hub.connection() as db:
            session = db.execute(
                "SELECT * FROM photo_capture_sessions "
                "WHERE device_id=? AND authorization_session_id=?",
                (device_id, session_id),
            ).fetchone()
        if (
            session is None
            or session["guardian_id"] != guardian_id
            or session["status"] != "active"
            or session["training_allowed"] != 0
            or retention_expires_at > session["retention_expires_at"]
            or (require_active and session["retention_expires_at"] <= _now())
        ):
            raise PhotoStoreError(
                "photo_session_not_authorized",
                "photo command is outside its Guardian-authorized session",
                403,
            )

    @staticmethod
    def _session_view(row: sqlite3.Row, result: str) -> dict[str, Any]:
        return {
            "ok": True,
            "result": result,
            "authorization_session": {
                "device_id": row["device_id"],
                "authorization_session_id": row["authorization_session_id"],
                "guardian_id": row["guardian_id"],
                "retention_expires_at": row["retention_expires_at"],
                "training_allowed": bool(row["training_allowed"]),
                "status": row["status"],
                "created_at": row["created_at"],
            },
        }

    @staticmethod
    def assert_authorized_session(
        db: sqlite3.Connection, metadata: dict[str, Any]
    ) -> None:
        session = db.execute(
            "SELECT * FROM photo_capture_sessions "
            "WHERE device_id=? AND authorization_session_id=?",
            (metadata["device_id"], metadata["authorization_session_id"]),
        ).fetchone()
        if (
            session is None
            or session["status"] != "active"
            or session["training_allowed"] != 0
            or session["retention_expires_at"] <= _now()
            or metadata["retention_expires_at"] > session["retention_expires_at"]
        ):
            raise PhotoStoreError(
                "photo_session_not_authorized",
                "camera metadata is outside an active authorized photo session",
                403,
            )

        command_row = db.execute(
            "SELECT * FROM commands WHERE device_id=? AND cmd_id=?",
            (metadata["device_id"], metadata["command_id"]),
        ).fetchone()
        if command_row is None:
            raise PhotoStoreError(
                "photo_command_not_found",
                "camera metadata is not linked to a delivered photo command",
                403,
            )
        try:
            command = json.loads(command_row["payload_json"])
            command_payload = command["payload"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PhotoStoreError(
                "photo_command_invalid", "linked photo command is invalid", 500
            ) from error

        expected_command = (
            "capture_photo_once"
            if metadata["trigger_reason"] == "web_manual"
            else "configure_photo_timer"
        )
        if (
            command.get("cmd") != expected_command
            or command.get("device_id") != metadata["device_id"]
            or command_payload.get("authorization_session_id")
            != metadata["authorization_session_id"]
            or _utc(
                command_payload.get("retention_expires_at"),
                "retention_expires_at",
            )
            != metadata["retention_expires_at"]
            or command_payload.get("training_allowed") is not False
        ):
            raise PhotoStoreError(
                "photo_command_mismatch",
                "camera metadata does not match its authorized photo command",
                403,
            )
        if expected_command == "configure_photo_timer" and (
            command_payload.get("enabled") is not True
            or command_payload.get("config_version") != metadata["config_version"]
        ):
            raise PhotoStoreError(
                "photo_timer_config_mismatch",
                "timed camera metadata does not match an enabled timer configuration",
                403,
            )
        command_status = str(command_row["status"] or "")
        durable_outcome = (
            metadata["capture_result"] == "captured"
            and metadata["local_save_status"] == "saved"
        )
        terminal_rejection = command_status in {
            "rejected",
            "timeout",
            "mock_only",
        }
        terminal_execution_conflict = (
            command_status == "error"
            and (expected_command == "configure_photo_timer" or durable_outcome)
        )
        one_shot_success_conflict = (
            expected_command == "capture_photo_once"
            and command_status == "ok"
            and not durable_outcome
        )
        timer_terminal_conflict = (
            expected_command == "configure_photo_timer"
            and command_status in {"ok", "error"}
        )
        one_shot_terminal_kind_conflict = (
            expected_command == "capture_photo_once"
            and command_status
            not in {"pending", "in_progress", "expired", "ok", "error"}
        )
        if (
            terminal_rejection
            or terminal_execution_conflict
            or one_shot_success_conflict
            or one_shot_terminal_kind_conflict
            or timer_terminal_conflict
        ):
            raise PhotoStoreError(
                "photo_command_terminal_conflict",
                "camera metadata contradicts the command's terminal state",
                409,
            )

        try:
            command_created = _timestamp(str(command["created_at"]))
            command_expires = datetime.fromtimestamp(
                command["expires_at_unix_ms"] / 1000, timezone.utc
            )
            session_created = _timestamp(session["created_at"])
            retention_expires = _timestamp(metadata["retention_expires_at"])
            received_at = _timestamp(metadata["server_received_at"])
            reported_event_at = (
                _timestamp(_utc(metadata["event_utc"], "event_utc"))
                if metadata["event_utc"] is not None
                else None
            )
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise PhotoStoreError(
                "photo_time_invalid", "camera authorization time cannot be verified", 403
            ) from error
        clock_is_authorizable = (
            metadata["timestamp_source"], metadata["timestamp_quality"]
        ) in AUTHORIZABLE_CAMERA_CLOCKS
        event_at = reported_event_at if clock_is_authorizable else None
        if expected_command == "configure_photo_timer" and event_at is None:
            raise PhotoStoreError(
                "photo_time_untrusted",
                "timed capture requires an explicit supported UTC clock source",
                403,
            )
        if expected_command == "configure_photo_timer":
            later_applied_controls = db.execute(
                """SELECT id,ack_at FROM commands
                   WHERE device_id=? AND cmd='configure_photo_timer'
                     AND id>? AND status='applied' AND ack_at IS NOT NULL
                   ORDER BY id ASC""",
                (metadata["device_id"], command_row["id"]),
            ).fetchall()
            for later_control in later_applied_controls:
                try:
                    superseded_at = _timestamp(str(later_control["ack_at"]))
                except (TypeError, ValueError) as error:
                    raise PhotoStoreError(
                        "photo_command_invalid",
                        "a later applied photo timer command is invalid",
                        500,
                    ) from error
                if event_at >= superseded_at:
                    raise PhotoStoreError(
                        "photo_timer_superseded",
                        "timed capture occurred after a later timer control took effect",
                        403,
                    )
        causal_time = event_at if event_at is not None else received_at
        timer_expires = None
        if expected_command == "configure_photo_timer":
            timer_expires = datetime.fromtimestamp(
                command_payload["session_expires_at_unix_ms"] / 1000,
                timezone.utc,
            )
        capture_window_end = timer_expires or command_expires
        skew = CAMERA_CLOCK_SKEW_SECONDS
        if (
            causal_time.timestamp() < command_created.timestamp() - skew
            or causal_time.timestamp() < session_created.timestamp() - skew
            or causal_time.timestamp() > received_at.timestamp() + skew
            or causal_time > capture_window_end
            or causal_time > retention_expires
        ):
            raise PhotoStoreError(
                "photo_time_outside_authorization",
                "camera capture time is outside its command/session authorization window",
                403,
            )

        if expected_command == "capture_photo_once":
            prior_outcome = db.execute(
                "SELECT photo_id FROM photo_records "
                "WHERE device_id=? AND command_id=? ORDER BY id LIMIT 1",
                (metadata["device_id"], metadata["command_id"]),
            ).fetchone()
            if prior_outcome is not None:
                raise PhotoStoreError(
                    "photo_command_already_bound",
                    "one-shot photo command is already bound to another outcome",
                    409,
                )
        else:
            maximum = command_payload.get("max_photos")
            if type(maximum) is not int or not 1 <= maximum <= 1000:
                raise PhotoStoreError(
                    "photo_command_invalid",
                    "timer photo limit is invalid",
                    500,
                )
            if durable_outcome:
                successful = int(
                    db.execute(
                        "SELECT COUNT(*) FROM photo_records "
                        "WHERE device_id=? AND command_id=? "
                        "AND capture_result='captured' "
                        "AND local_save_status='saved'",
                        (metadata["device_id"], metadata["command_id"]),
                    ).fetchone()[0]
                )
                if successful >= maximum:
                    raise PhotoStoreError(
                        "photo_timer_limit_reached",
                        "timer photo limit has already been reached",
                        409,
                    )
        metadata.update(
            location_observation_id=None,
            location_source=None,
            location_event_utc=None,
            location_timestamp_quality=None,
            location_age_seconds=None,
        )
        location_ref = metadata["location_ref"]
        if location_ref is None:
            return
        location_row = db.execute(
            "SELECT source,event_utc,envelope_json FROM collection_records "
            "WHERE device_id=? AND observation_id=?",
            (metadata["device_id"], location_ref["observation_id"]),
        ).fetchone()
        if location_row is None:
            raise PhotoStoreError(
                "photo_location_not_found",
                "camera location reference does not identify a received observation",
                422,
            )
        try:
            location_envelope = json.loads(location_row["envelope_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise PhotoStoreError(
                "photo_location_invalid", "referenced location record is invalid", 500
            ) from error
        location_payload = location_envelope.get("payload")
        if (
            location_row["source"] != "gnss"
            or not isinstance(location_payload, dict)
            or location_payload.get("fix") is not True
            or type(location_payload.get("latitude")) not in {int, float}
            or type(location_payload.get("longitude")) not in {int, float}
            or not math.isfinite(location_payload["latitude"])
            or not math.isfinite(location_payload["longitude"])
            or not -90 <= location_payload["latitude"] <= 90
            or not -180 <= location_payload["longitude"] <= 180
            or location_ref["event_utc"] != location_envelope.get("timestamp_utc")
            or location_ref["timestamp_quality"]
            != location_envelope.get("timestamp_quality")
        ):
            raise PhotoStoreError(
                "photo_location_mismatch",
                "camera location reference is not the identified GNSS fix",
                422,
            )
        location_time = (
            _timestamp(_utc(location_ref["event_utc"], "location_ref.event_utc"))
            if location_ref["event_utc"] is not None
            else None
        )
        if location_time is None or location_time > causal_time:
            raise PhotoStoreError(
                "photo_location_after_capture",
                "camera location reference occurs after the capture evidence",
                422,
            )
        metadata.update(
            location_observation_id=location_ref["observation_id"],
            location_source=location_row["source"],
            location_event_utc=location_ref["event_utc"],
            location_timestamp_quality=location_ref["timestamp_quality"],
            location_age_seconds=(
                round((event_at - location_time).total_seconds(), 3)
                if event_at is not None and location_time is not None
                else None
            ),
        )

    @staticmethod
    def assert_metadata_identity(
        db: sqlite3.Connection, metadata: dict[str, Any]
    ) -> sqlite3.Row | None:
        existing = db.execute(
            "SELECT * FROM photo_records WHERE device_id=? AND photo_id=?",
            (metadata["device_id"], metadata["photo_id"]),
        ).fetchone()
        if existing is not None and (
            existing["observation_id"] != metadata["observation_id"]
            or existing["metadata_sha256"] != metadata["metadata_sha256"]
        ):
            raise PhotoStoreError(
                "photo_identity_conflict",
                "photo identity already has different immutable metadata",
                409,
            )
        return existing

    @staticmethod
    def insert_metadata(
        db: sqlite3.Connection,
        metadata: dict[str, Any],
        collection_record_id: int,
    ) -> None:
        now = _now()
        db.execute(
            """INSERT INTO photo_records (
                device_id,photo_id,observation_id,collection_record_id,session_id,
                trigger_reason,command_id,config_version,capture_result,
                local_save_status,device_upload_status,event_monotonic_ns,event_utc,
                timestamp_source,timestamp_quality,authorization_session_id,retention_expires_at,
                training_allowed,location_observation_id,location_source,
                location_event_utc,location_timestamp_quality,location_age_seconds,
                collection_received_at,collection_persisted_at,
                collection_claimed_transport,collection_delivery_result,
                expected_media_type,expected_width,expected_height,expected_bytes,
                expected_sha256,metadata_sha256,metadata_json,
                content_status,created_at,updated_at
            ) VALUES (
                :device_id,:photo_id,:observation_id,:collection_record_id,:session_id,
                :trigger_reason,:command_id,:config_version,:capture_result,
                :local_save_status,:device_upload_status,:event_monotonic_ns,:event_utc,
                :timestamp_source,:timestamp_quality,:authorization_session_id,:retention_expires_at,
                0,:location_observation_id,:location_source,:location_event_utc,
                :location_timestamp_quality,:location_age_seconds,
                :server_received_at,:server_persisted_at,
                :collection_claimed_transport,:collection_delivery_result,
                :expected_media_type,:expected_width,:expected_height,
                :expected_bytes,:expected_sha256,:metadata_sha256,:metadata_json,
                CASE
                    WHEN :capture_result != 'captured' OR :local_save_status != 'saved'
                        THEN 'not_expected'
                    WHEN :retention_expires_at <= :now THEN 'expired'
                    ELSE 'pending'
                END,
                :now,:now
            )""",
            {**metadata, "collection_record_id": collection_record_id, "now": now},
        )

    @staticmethod
    def _row_view(row: sqlite3.Row) -> dict[str, Any]:
        content_status = row["content_status"]
        server_received_at = row["collection_received_at"] or row["created_at"]
        receive_age = _age_seconds(server_received_at, row["event_utc"])
        return {
            "row_id": row["id"],
            "collection_record_id": row["collection_record_id"],
            "device_id": row["device_id"],
            "photo_id": row["photo_id"],
            "observation_id": row["observation_id"],
            "session_id": row["session_id"],
            "trigger_reason": row["trigger_reason"],
            "command_id": row["command_id"],
            "config_version": row["config_version"],
            "capture_result": row["capture_result"],
            "local_save_status": row["local_save_status"],
            "device_upload_status": row["device_upload_status"],
            "event_monotonic_ns": row["event_monotonic_ns"],
            "event_utc": row["event_utc"],
            "timestamp_source": row["timestamp_source"],
            "timestamp_quality": row["timestamp_quality"],
            "server_received_at": server_received_at,
            "server_persisted_at": row["collection_persisted_at"] or row["created_at"],
            "collection_delivery": {
                "result": row["collection_delivery_result"],
                "claimed_transport": row["collection_claimed_transport"],
                "evidence_semantics": "authenticated_device_report_not_independent_path_proof",
            },
            "backfill": {
                "age_seconds": receive_age,
                "is_backfill": (
                    receive_age is not None
                    and receive_age >= BACKFILL_THRESHOLD_SECONDS
                ),
                "threshold_seconds": BACKFILL_THRESHOLD_SECONDS,
            },
            "authorization_session_id": row["authorization_session_id"],
            "retention_expires_at": row["retention_expires_at"],
            "training_allowed": bool(row["training_allowed"]),
            "resolved_location_ref": (
                {
                    "observation_id": row["location_observation_id"],
                    "source": row["location_source"],
                    "event_utc": row["location_event_utc"],
                    "timestamp_quality": row["location_timestamp_quality"],
                    "age_at_capture_seconds": row["location_age_seconds"],
                }
                if row["location_observation_id"] is not None
                else None
            ),
            "expected": {
                "media_type": row["expected_media_type"],
                "width": row["expected_width"],
                "height": row["expected_height"],
                "bytes": row["expected_bytes"],
                "sha256": row["expected_sha256"],
            },
            "content": {
                "status": content_status,
                "verification_scope": (
                    "sha256_length_geometry_baseline_structure_v1"
                    if content_status == "stored"
                    else None
                ),
                "purge_state": row["content_purge_state"],
                "purge_error": row["content_purge_error"],
                "purged_at": row["content_purged_at"],
                "bytes": row["stored_bytes"],
                "sha256": row["stored_sha256"],
                "claimed_transport": row["stored_transport"],
                "stored_at": row["stored_at"],
                "url": (
                    f"/api/v1/devices/{row['device_id']}/photos/{row['photo_id']}/content"
                    if content_status == "stored"
                    else None
                ),
            },
            "upload_attempts": {
                "count": row["upload_attempt_count"],
                "last_attempt_at": row["last_upload_attempt_at"],
                "last_result": row["last_upload_result"],
                "last_error_code": row["last_upload_error_code"],
            },
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self, device_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        self.purge_expired()
        allowed = {"limit", "before_id", "session_id"}
        if set(query) - allowed or any(len(values) != 1 for values in query.values()):
            raise PhotoStoreError(
                "invalid_photo_query", "unknown or repeated photo query", 400
            )
        try:
            limit = int((query.get("limit") or ["50"])[0])
            before_id = int((query.get("before_id") or [str(2**63 - 1)])[0])
        except ValueError as error:
            raise PhotoStoreError(
                "invalid_photo_query", "photo pagination values must be integers", 400
            ) from error
        if not 1 <= limit <= MAX_PAGE_SIZE or before_id <= 0:
            raise PhotoStoreError(
                "invalid_photo_query", "photo pagination is outside its range", 400
            )
        session_id = (query.get("session_id") or [None])[0]
        if session_id is not None:
            _safe_id(session_id, "session_id")
        base_sql = " FROM photo_records WHERE device_id=?"
        base_args: list[Any] = [device_id]
        if session_id is not None:
            base_sql += " AND session_id=?"
            base_args.append(session_id)
        sql = "SELECT *" + base_sql + " AND id<? ORDER BY id DESC LIMIT ?"
        args = [*base_args, before_id]
        args.append(limit + 1)
        with self.hub.connection() as db:
            # Keep the page and its aggregate on one SQLite snapshot.  A
            # concurrent upload must appear in both views or neither view.
            db.execute("BEGIN")
            rows = db.execute(sql, args).fetchall()
            aggregate = db.execute(
                "SELECT COUNT(*) record_count,"
                "COALESCE(SUM(content_status='pending'),0) pending_content_count,"
                "COALESCE(SUM(content_status='stored'),0) stored_content_count,"
                "COALESCE(SUM(content_status='corrupt'),0) corrupt_content_count,"
                "COALESCE(SUM(content_status='not_expected'),0) not_expected_count,"
                "COALESCE(SUM(content_status='expired'),0) expired_content_count,"
                "COALESCE(SUM(CASE WHEN content_status='pending' "
                "THEN expected_bytes ELSE 0 END),0) pending_content_bytes,"
                "COALESCE(SUM(CASE WHEN content_status='stored' "
                "THEN stored_bytes ELSE 0 END),0) stored_content_bytes,"
                "COALESCE(SUM(CASE WHEN content_status='corrupt' "
                "THEN COALESCE(stored_bytes,expected_bytes,0) ELSE 0 END),0) "
                "corrupt_content_bytes"
                + base_sql,
                base_args,
            ).fetchone()
        records = [self._row_view(row) for row in rows[:limit]]
        return {
            "device_id": device_id,
            "photos": records,
            "aggregate": dict(aggregate),
            "ordering": {
                "key": "durable_record_id",
                "direction": "descending",
                "historical_backfill_can_arrive_later": True,
            },
            "page": {
                "limit": limit,
                "next_before_id": records[-1]["row_id"] if len(rows) > limit else None,
                "exhausted": len(rows) <= limit,
            },
        }

    def export_all(
        self, device_id: str, query: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Export a complete bounded metadata set or fail without truncation."""

        self.purge_expired()
        if set(query) - {"session_id"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise PhotoStoreError(
                "invalid_photo_export_query",
                "photo export accepts only one optional session_id",
                400,
            )
        session_id = (query.get("session_id") or [None])[0]
        sql = "SELECT * FROM photo_records WHERE device_id=?"
        args: list[Any] = [device_id]
        if session_id is not None:
            _safe_id(session_id, "session_id")
            sql += " AND session_id=?"
            args.append(session_id)
        with self.hub.connection() as db:
            # COUNT and rows must describe the same complete export snapshot.
            db.execute("BEGIN")
            total = int(
                db.execute("SELECT COUNT(*) FROM (" + sql + ")", args).fetchone()[0]
            )
            if total > MAX_EXPORT_RECORDS:
                raise PhotoStoreError(
                    "photo_export_too_large",
                    "photo export exceeds 5000 records; select one capture session",
                    413,
                )
            rows = db.execute(sql + " ORDER BY id ASC", args).fetchall()
        return {
            "device_id": device_id,
            "session_id": session_id,
            "photos": [self._row_view(row) for row in rows],
            "record_count": total,
            "complete": True,
            "ordering": {
                "key": "durable_record_id",
                "direction": "ascending",
                "historical_backfill_can_arrive_later": True,
            },
        }

    def metadata(self, device_id: str, photo_id: str) -> dict[str, Any]:
        self.purge_expired()
        _safe_id(photo_id, "photo_id")
        with self.hub.connection() as db:
            row = db.execute(
                "SELECT * FROM photo_records WHERE device_id=? AND photo_id=?",
                (device_id, photo_id),
            ).fetchone()
        if row is None:
            raise PhotoStoreError("photo_not_found", "photo was not found", 404)
        return self._row_view(row)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _verify_file(
        path: Path,
        expected_bytes: int,
        expected_sha256: str,
        expected_width: int,
        expected_height: int,
    ) -> None:
        content = path.read_bytes()
        if len(content) != expected_bytes or hashlib.sha256(content).hexdigest() != expected_sha256:
            raise PhotoStoreError(
                "photo_content_corrupt", "stored photo content failed verification", 500
            )
        try:
            width, height = _jpeg_geometry(content)
        except PhotoStoreError as error:
            raise PhotoStoreError(
                "photo_content_corrupt", "stored photo content failed JPEG verification", 500
            ) from error
        if (width, height) != (expected_width, expected_height):
            raise PhotoStoreError(
                "photo_content_corrupt", "stored photo geometry differs from metadata", 500
            )

    def _target(
        self,
        device_id: str,
        photo_id: str,
        digest: str,
        *,
        create_directory: bool = True,
    ) -> tuple[Path, str]:
        device_key = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:32]
        photo_key = hashlib.sha256(photo_id.encode("utf-8")).hexdigest()[:32]
        directory = self.root / device_key / digest[:2]
        if create_directory:
            self._private_directory(directory)
        target = directory / f"{photo_key}-{digest}.jpg"
        relative = target.relative_to(self.root).as_posix()
        return target, relative

    def _device_file_bytes(self, device_id: str) -> int:
        device_key = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:32]
        directory = self.root / device_key
        if not directory.exists():
            return 0
        try:
            return sum(
                path.stat().st_size
                for path in directory.rglob("*.jpg")
                if path.is_file()
            )
        except OSError as error:
            raise PhotoStoreError(
                "photo_store_error", "private photo quota cannot be verified", 500
            ) from error

    def purge_expired(self) -> int:
        """Delete expired JPEG bytes while retaining their immutable audit metadata."""

        with self._exclusive_write():
            db = self.hub.connect()
            try:
                db.execute("PRAGMA synchronous=FULL")
                rows = db.execute(
                    "SELECT * FROM photo_records WHERE retention_expires_at<=? "
                    "AND (content_status IN ('pending','stored','corrupt') "
                    "OR (content_status='expired' "
                    "AND content_purge_state!='complete')) ORDER BY id ASC",
                    (_now(),),
                ).fetchall()
                completed = 0
                for row in rows:
                    # First durably revoke access.  Filesystem deletion cannot
                    # be rolled back with SQLite, so each object gets its own
                    # tombstone before any unlink is attempted.
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        """UPDATE photo_records SET content_status='expired',
                           content_purge_state='pending',content_purge_error=NULL,
                           updated_at=? WHERE id=?""",
                        (_now(), row["id"]),
                    )
                    db.commit()

                    try:
                        relative = row["content_relative_path"]
                        paths: set[Path] = set()
                        purge_warning = None
                        canonical_path = None
                        if row["expected_sha256"]:
                            # A crash after atomic rename but before the SQLite
                            # commit, or a corrupt recorded path, can leave a
                            # deterministic orphan. Retention must erase it.
                            canonical_path, _ = self._target(
                                row["device_id"],
                                row["photo_id"],
                                row["expected_sha256"],
                                create_directory=False,
                            )
                            paths.add(canonical_path)
                        if relative:
                            try:
                                recorded_path = self._resolved_content_path(relative)
                            except PhotoStoreError:
                                purge_warning = "invalid_recorded_path_ignored"
                            else:
                                # A row must never be allowed to delete another
                                # photo merely because its recorded path was
                                # corrupted to a different in-root JPEG.
                                if canonical_path is None or recorded_path != canonical_path:
                                    purge_warning = "mismatched_recorded_path_ignored"
                        if purge_warning is not None and not paths:
                            raise PhotoStoreError(
                                "photo_retention_path_invalid",
                                "expired photo has no safe deletion target",
                                500,
                            )
                        for path in paths:
                            try:
                                path.unlink()
                            except FileNotFoundError:
                                # Already absent is the only safe no-op.  Do
                                # not use exists(): stat/permission failures
                                # can be reported as False and must never be
                                # promoted to a completed privacy purge.
                                pass
                            else:
                                self._fsync_directory(path.parent)
                    except (OSError, PhotoStoreError) as error:
                        db.execute("BEGIN IMMEDIATE")
                        db.execute(
                            """UPDATE photo_records SET
                               content_purge_state='failed',content_purge_error=?,
                               updated_at=? WHERE id=? AND content_status='expired'""",
                            (type(error).__name__, _now(), row["id"]),
                        )
                        db.commit()
                        LOGGER.error(
                            "expired photo purge failed for row %s: %s",
                            row["id"],
                            type(error).__name__,
                        )
                        continue

                    if purge_warning is not None:
                        # The deterministic canonical object is gone, but a
                        # corrupt recorded path means we cannot prove that no
                        # private bytes remain elsewhere.  Keep the tombstone
                        # failed and retain the recorded path for explicit
                        # reconciliation; never claim physical deletion was
                        # complete and never follow the suspect path.
                        db.execute("BEGIN IMMEDIATE")
                        db.execute(
                            """UPDATE photo_records SET
                               content_purge_state='failed',content_purge_error=?,
                               updated_at=? WHERE id=? AND content_status='expired'""",
                            (purge_warning, _now(), row["id"]),
                        )
                        db.commit()
                        continue

                    purged_at = _now()
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        """UPDATE photo_records SET content_status='expired',
                           content_relative_path=NULL,stored_bytes=NULL,
                           stored_sha256=NULL,stored_transport=NULL,stored_at=NULL,
                           content_purge_state='complete',content_purge_error=?,
                           content_purged_at=?,updated_at=? WHERE id=?""",
                        (purge_warning, purged_at, purged_at, row["id"]),
                    )
                    db.commit()
                    completed += 1
                return completed
            except (OSError, sqlite3.Error) as error:
                db.rollback()
                raise PhotoStoreError(
                    "photo_retention_error",
                    "expired private photo content could not be purged",
                    500,
                ) from error
            finally:
                db.close()

    def _record_upload_attempt(
        self,
        device_id: str,
        photo_id: str,
        *,
        result: str,
        error_code: str | None,
    ) -> None:
        try:
            with self.hub.connection() as db:
                db.execute(
                    """UPDATE photo_records SET
                       upload_attempt_count=upload_attempt_count+1,
                       last_upload_attempt_at=?,last_upload_result=?,
                       last_upload_error_code=?,updated_at=?
                       WHERE device_id=? AND photo_id=?""",
                    (
                        _now(),
                        result,
                        error_code,
                        _now(),
                        device_id,
                        photo_id,
                    ),
                )
        except sqlite3.Error:
            LOGGER.exception("photo upload attempt could not be recorded")

    def record_rejected_upload(
        self, device_id: str, photo_id: str, *, error_code: str
    ) -> None:
        """Record an authenticated upload rejected before body persistence."""

        self._record_upload_attempt(
            device_id,
            photo_id,
            result="failed",
            error_code=error_code,
        )

    def store_content(
        self,
        device_id: str,
        photo_id: str,
        content: bytes,
        *,
        claimed_sha256: str,
        transport: str,
    ) -> dict[str, Any]:
        try:
            result = self._store_content(
                device_id,
                photo_id,
                content,
                claimed_sha256=claimed_sha256,
                transport=transport,
            )
        except PhotoStoreError as error:
            self._record_upload_attempt(
                device_id,
                photo_id,
                result="failed",
                error_code=error.code,
            )
            raise
        self._record_upload_attempt(
            device_id,
            photo_id,
            result=str(result.get("result") or "accepted"),
            error_code=None,
        )
        return result

    def _store_content(
        self,
        device_id: str,
        photo_id: str,
        content: bytes,
        *,
        claimed_sha256: str,
        transport: str,
    ) -> dict[str, Any]:
        _safe_id(device_id, "device_id")
        _safe_id(photo_id, "photo_id")
        if transport not in {"wifi", "lte"}:
            raise PhotoStoreError(
                "invalid_photo_transport",
                "X-EgoLink-Transport must identify the actual sending interface",
            )
        if not isinstance(content, bytes) or not 4 <= len(content) <= self.max_photo_bytes:
            raise PhotoStoreError(
                "invalid_photo_length", "photo content length is outside its bound", 413
            )
        if not isinstance(claimed_sha256, str) or SHA256.fullmatch(claimed_sha256) is None:
            raise PhotoStoreError(
                "invalid_photo_sha256", "X-Content-SHA256 must be lowercase hexadecimal"
            )
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != claimed_sha256:
            raise PhotoStoreError(
                "photo_sha256_mismatch", "photo content SHA-256 does not match"
            )
        actual_width, actual_height = _jpeg_geometry(content)

        self.purge_expired()
        with self._exclusive_write():
            db = self.hub.connect()
            temporary_path: Path | None = None
            result_name = "accepted"
            try:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM photo_records WHERE device_id=? AND photo_id=?",
                    (device_id, photo_id),
                ).fetchone()
                if row is None:
                    raise PhotoStoreError(
                        "photo_metadata_not_found",
                        "camera metadata must be accepted before JPEG content",
                        404,
                    )
                if row["retention_expires_at"] <= _now() or row[
                    "content_status"
                ] == "expired":
                    raise PhotoStoreError(
                        "photo_retention_expired",
                        "photo retention authorization has expired",
                        410,
                    )
                if row["expected_sha256"] != actual_sha256 or row["expected_bytes"] != len(
                    content
                ):
                    raise PhotoStoreError(
                        "photo_content_conflict",
                        "photo content differs from its immutable metadata",
                        409,
                    )
                if (row["expected_width"], row["expected_height"]) != (
                    actual_width,
                    actual_height,
                ):
                    raise PhotoStoreError(
                        "photo_geometry_mismatch",
                        "photo geometry differs from its immutable metadata",
                        409,
                    )
                if (
                    row["capture_result"] != "captured"
                    or row["local_save_status"] != "saved"
                    or row["expected_media_type"] != "image/jpeg"
                ):
                    raise PhotoStoreError(
                        "photo_content_not_ready",
                        "camera metadata does not describe durable JPEG content",
                        409,
                    )
                if row["content_status"] not in {"pending", "stored", "corrupt"}:
                    raise PhotoStoreError(
                        "photo_content_not_ready",
                        "camera metadata is not in an uploadable content state",
                        409,
                    )
                if row["content_status"] == "stored":
                    if (
                        row["stored_sha256"] != actual_sha256
                        or row["stored_bytes"] != len(content)
                    ):
                        raise PhotoStoreError(
                            "photo_content_conflict",
                            "photo identity already has different stored content",
                            409,
                        )
                    path = self._resolved_content_path(row["content_relative_path"])
                    try:
                        self._verify_file(
                            path,
                            len(content),
                            actual_sha256,
                            actual_width,
                            actual_height,
                        )
                    except (OSError, PhotoStoreError):
                        db.execute(
                            """UPDATE photo_records SET content_status='corrupt',
                               updated_at=? WHERE id=?""",
                            (_now(), row["id"]),
                        )
                        # Commit the detected corruption before attempting any
                        # replacement.  A later quota, disk, or rename failure
                        # must never roll the database back to the false
                        # assertion that the missing/corrupt file is stored.
                        db.commit()
                        db.execute("BEGIN IMMEDIATE")
                        row = db.execute(
                            "SELECT * FROM photo_records WHERE id=?", (row["id"],)
                        ).fetchone()
                        result_name = "repaired"
                    else:
                        db.commit()
                        return self._content_result(row, "duplicate")

                target, relative = self._target(device_id, photo_id, actual_sha256)
                used = self._device_file_bytes(device_id)
                target_bytes = target.stat().st_size if target.exists() else 0
                projected_bytes = used - target_bytes + len(content)
                if projected_bytes > self.device_quota_bytes:
                    raise PhotoStoreError(
                        "photo_quota_exceeded",
                        "private photo quota for this device is full",
                        507,
                    )
                target_is_valid = False
                if target.exists():
                    try:
                        self._verify_file(
                            target,
                            len(content),
                            actual_sha256,
                            actual_width,
                            actual_height,
                        )
                        target_is_valid = True
                        if result_name == "accepted":
                            result_name = "recovered"
                    except (OSError, PhotoStoreError):
                        result_name = "repaired"
                if not target_is_valid:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        prefix=".photo-upload-",
                        suffix=".tmp",
                        dir=target.parent,
                        delete=False,
                    ) as temporary:
                        temporary_path = Path(temporary.name)
                        temporary.write(content)
                        temporary.flush()
                        os.fsync(temporary.fileno())
                    os.replace(temporary_path, target)
                    temporary_path = None
                    if os.name != "nt":
                        os.chmod(target, 0o600)
                    self._fsync_directory(target.parent)
                self._verify_file(
                    target,
                    len(content),
                    actual_sha256,
                    actual_width,
                    actual_height,
                )
                stored_at = _now()
                db.execute(
                    """UPDATE photo_records SET
                       content_status='stored',content_relative_path=?,stored_bytes=?,
                       stored_sha256=?,stored_transport=?,stored_at=?,updated_at=?
                       ,content_purge_state='not_due',content_purge_error=NULL,
                       content_purged_at=NULL
                       WHERE id=? AND content_status IN ('pending','corrupt')""",
                    (
                        relative,
                        len(content),
                        actual_sha256,
                        transport,
                        stored_at,
                        stored_at,
                        row["id"],
                    ),
                )
                db.commit()
                stored = db.execute(
                    "SELECT * FROM photo_records WHERE id=?", (row["id"],)
                ).fetchone()
                return self._content_result(stored, result_name)
            except PhotoStoreError:
                db.rollback()
                raise
            except (OSError, sqlite3.Error) as error:
                db.rollback()
                raise PhotoStoreError(
                    "photo_store_error", "private photo persistence failed", 500
                ) from error
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                db.close()

    @staticmethod
    def _content_result(row: sqlite3.Row, result: str) -> dict[str, Any]:
        return {
            "ok": True,
            "result": result,
            "delivery_ack": {
                "contract_version": "egolink.photo.content.ack.v0.1",
                "device_id": row["device_id"],
                "photo_id": row["photo_id"],
                "payload_sha256": row["stored_sha256"],
                "payload_bytes": row["stored_bytes"],
                "status": "server_verified",
                "verification_scope": "sha256_length_geometry_baseline_structure_v1",
                "stored_at": row["stored_at"],
            },
        }

    def _resolved_content_path(self, relative: Any) -> Path:
        if not isinstance(relative, str) or not relative:
            raise PhotoStoreError(
                "photo_content_corrupt", "stored photo path is unavailable", 500
            )
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise PhotoStoreError(
                "photo_content_corrupt", "stored photo path is invalid", 500
            ) from error
        return path

    def content(self, device_id: str, photo_id: str) -> tuple[bytes, dict[str, Any]]:
        self.purge_expired()
        _safe_id(photo_id, "photo_id")
        with self._exclusive_write():
            with self.hub.connection() as db:
                row = db.execute(
                    "SELECT * FROM photo_records WHERE device_id=? AND photo_id=?",
                    (device_id, photo_id),
                ).fetchone()
            if row is None:
                raise PhotoStoreError("photo_not_found", "photo was not found", 404)
            if row["retention_expires_at"] <= _now():
                raise PhotoStoreError(
                    "photo_retention_expired", "photo retention has expired", 410
                )
            if row["content_status"] != "stored":
                raise PhotoStoreError(
                    "photo_content_not_stored", "photo content is not stored", 404
                )
            path = self._resolved_content_path(row["content_relative_path"])
            try:
                self._verify_file(
                    path,
                    row["stored_bytes"],
                    row["stored_sha256"],
                    row["expected_width"],
                    row["expected_height"],
                )
                body = path.read_bytes()
            except (OSError, PhotoStoreError) as error:
                with self.hub.connection() as db:
                    db.execute(
                        """UPDATE photo_records SET content_status='corrupt',
                           last_upload_result='stored_content_corrupt',
                           last_upload_error_code='photo_content_corrupt',updated_at=?
                           WHERE id=? AND content_status='stored'""",
                        (_now(), row["id"]),
                    )
                raise PhotoStoreError(
                    "photo_content_unavailable",
                    "stored photo content is unavailable",
                    500,
                ) from error
        return body, self._row_view(row)


__all__ = [
    "DEFAULT_DEVICE_QUOTA_BYTES",
    "DEFAULT_MAX_PHOTO_BYTES",
    "PHOTO_CONTROL_COMMANDS",
    "PhotoStore",
    "PhotoStoreError",
]
