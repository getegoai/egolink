"""Minimal Ego Link P0 HTTP message hub.

The first server path intentionally uses only the Python standard library so it
can run on a clean VPS before we introduce deployment complexity.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import protocol
from server.collection_store import (
    CollectionError, CollectionStore, is_collection_content_type, jsonl_page,
)
from server.collection_page import (
    COLLECTION_HTML, COLLECTION_JS, COLLECTION_CSS, COLLECTION_SECURITY_HEADERS,
)
from server.guardian_device_authorization import GuardianDeviceAuthorizer
from server.guardian_location_page import (
    GUARDIAN_LOCATION_CSS,
    GUARDIAN_LOCATION_CSS_PATH,
    GUARDIAN_LOCATION_HTML,
    GUARDIAN_LOCATION_JS,
    GUARDIAN_LOCATION_JS_PATH,
    GUARDIAN_LOCATION_PATH,
    GUARDIAN_LOCATION_SECURITY_HEADERS,
)
from server.location_delivery_ack import build_location_state_delivery_ack
from server.location_state_runtime import (
    LocationStateConflictError,
    LocationStateRegressionError,
    LocationStateValidationError,
)
from server.location_state_store import LocationStateStore
from server.manual_sos_delivery_ack import (
    DELIVERY_SCOPE as MANUAL_SOS_DELIVERY_SCOPE,
    ManualSosDeliveryAckError,
    build_manual_sos_delivery_ack,
)
from server.manual_sos_store import (
    MAX_MANUAL_SOS_BODY_BYTES,
    ManualSosConflictError,
    ManualSosNotFoundError,
    ManualSosStore,
    ManualSosStoreError,
    ManualSosValidationError,
)
from server.photo_store import (
    DEFAULT_DEVICE_QUOTA_BYTES,
    DEFAULT_MAX_PHOTO_BYTES,
    PHOTO_CONTROL_COMMANDS,
    PhotoStore,
    PhotoStoreError,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "server" / "runtime" / "message_hub.db"
KEY_RELEASE_DIR = REPO_ROOT / "docs" / "current" / "key_releases"
DEFAULT_PRODUCT_DEMO_REPORTS = REPO_ROOT / "reports" / "product_demo"
DEFAULT_FIELD_RESULT_REPORTS = REPO_ROOT / "reports"
DEFAULT_DATA_FLYWHEEL_REPORTS = REPO_ROOT / "reports" / "data_flywheel"
DEFAULT_TRAINING_EXPERIMENT_REPORTS = REPO_ROOT / "reports" / "training_experiments"
DEFAULT_TRAINING_RUN_REPORTS = REPO_ROOT / "reports" / "training_runs"
DEFAULT_TRAINING_FEATURE_REPORTS = REPO_ROOT / "reports" / "training_features"
DEFAULT_TRAINING_RUNNER_DRY_RUN_REPORTS = REPO_ROOT / "reports" / "training_runner_dry_runs"
DEFAULT_TRAINING_BASELINE_EVAL_REPORTS = REPO_ROOT / "reports" / "training_baseline_evals"
DEFAULT_TRAINING_HANDOFF_REPORTS = REPO_ROOT / "reports" / "training_handoffs"
DEFAULT_TRAINING_JOB_REPORTS = REPO_ROOT / "reports" / "training_jobs"
DEFAULT_SYNTHETIC_TRAINING_CHAIN_REPORTS = REPO_ROOT / "reports" / "synthetic_training_chain"
DEFAULT_D1_TRAINING_READINESS_REPORTS = REPO_ROOT / "reports" / "d1_training_readiness"
DEFAULT_D1_LABELING_INTAKE_REPORTS = REPO_ROOT / "reports" / "d1_labeling_intake"
DEFAULT_D1_LABELING_QUEUE_REPORTS = REPO_ROOT / "reports" / "d1_labeling_queue"
DEFAULT_D1_LABELING_REVIEW_REPORTS = REPO_ROOT / "reports" / "d1_labeling_reviews"
DEFAULT_D1_LABELING_DECISION_REPORTS = REPO_ROOT / "reports" / "d1_labeling_decisions"
DEFAULT_PROGRESS_BOARD = REPO_ROOT / "docs" / "generated" / "progress_board.json"
DEV_BENCH_DIR = REPO_ROOT / "server" / "web"
DEV_BENCH_SECURITY_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://webapi.amap.com https://*.amap.com; "
        "style-src 'self' 'unsafe-inline' https://webapi.amap.com https://*.amap.com; "
        "connect-src 'self' https://webapi.amap.com https://*.amap.com https://restapi.amap.com; "
        "img-src 'self' data: blob: https://webapi.amap.com https://*.amap.com https://*.is.autonavi.com; "
        "font-src 'self' data: https://*.amap.com; "
        "worker-src 'self' blob:; "
        "child-src 'self' blob:; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
DEV_BENCH_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
MAX_BODY_BYTES = 1_000_000
AMAP_JS_API_KEY_ENV = "EGOLINK_AMAP_JS_API_KEY"
AMAP_SECURITY_JS_CODE_ENV = "EGOLINK_AMAP_SECURITY_JS_CODE"
AMAP_PROXY_PREFIX = "/_AMapService"
AMAP_PROXY_TIMEOUT_S = 5.0
AMAP_PROXY_TOTAL_DEADLINE_S = 8.0
AMAP_PROXY_MAX_RESPONSE_BYTES = 4_000_000
AMAP_PROXY_MAX_QUERY_BYTES = 8192
AMAP_PROXY_READ_CHUNK_BYTES = 64 * 1024
AMAP_PROXY_MAX_CONCURRENCY = 4
AMAP_PROXY_ALLOWED_HOSTS = frozenset({"restapi.amap.com", "webapi.amap.com"})
AMAP_PROXY_ALLOWED_PATH = re.compile(
    r"^(?:/v3/assistant/coordinate/convert|/v3/log/init|/v4/map/styles)$"
)
AMAP_PROXY_JSONP_PATHS = frozenset(
    {"/v3/assistant/coordinate/convert", "/v3/log/init"}
)
AMAP_PROXY_JSONP_SOURCE_TYPES = frozenset(
    {"application/json", "application/javascript", "application/octet-stream", "text/javascript"}
)
AMAP_PROXY_CALLBACK_PATTERN = re.compile(
    r"^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$"
)
AMAP_PROXY_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/javascript",
        "application/octet-stream",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
        "image/webp",
        "text/css",
        "text/javascript",
        "text/plain",
    }
)
AMAP_PROXY_COOKIE_NAME = "egolink_amap_proxy"
AMAP_PROXY_COOKIE_TTL_S = 5 * 60
AMAP_PROXY_MAX_COOKIE_HEADER_BYTES = 8192
AMAP_CREDENTIAL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
RAW_FRAME_PROFILE = "raw-frame.p0.v1"
EALE_P0_GENERATOR_NAME = "EALE-P0"
EALE_P0_GENERATOR_VERSION = "0.1.0-alg001"
D1_FIELD_READY_FRESHNESS_S = 180
D1_FIELD_STALE_FRESHNESS_S = 600
D1_LOCATION_EVENT_TYPES = {"location_report", "location_observation"}
D1_SUMMARY_MESSAGE_LIMIT = 300
D1_COORDINATE_HISTORY_LIMIT = 48
D1_COORDINATE_MESSAGE_SCAN_LIMIT = 5000
D1_AMAP_WGS84_FW_ALLOWLIST = frozenset(
    {
        "0.1.0-fw005-gnss-correctness",
        "0.1.0-fw007-lte-wifi-failover",
    }
)
LOCATION_HISTORY_DEFAULT_PAGE_SIZE = 50
LOCATION_HISTORY_MAX_PAGE_SIZE = 100
LOCATION_HISTORY_SCAN_LIMIT = 2000
LOCATION_HISTORY_SCAN_BYTE_LIMIT = 8_000_000
LOCATION_HISTORY_MAX_INSPECT_PAYLOAD_BYTES = 65_536
SQLITE_SIGNED_INT64_MAX = 9_223_372_036_854_775_807
LOCATION_HISTORY_CURSOR_PREFIX = "lh1"
LOCATION_HISTORY_EVENT_TYPES = frozenset({"all", "location_report", "location_observation"})
LOCATION_HISTORY_TRUST_FILTERS = frozenset({"all", "selectable", "unselectable"})
FIELD_EXPORT_DEFAULT_MAX_RECORDS = 5000
FIELD_EXPORT_HARD_MAX_RECORDS = 10000
FIELD_EXPORT_MAX_DURATION_S = 48 * 60 * 60
IMU_WINDOW_CONTRACT_VERSION = "egolink.imu_window.v1"
IMU_WINDOW_SAMPLE_COUNT = 100
IMU_WINDOW_INTERVAL_US = 50_000
IMU_WINDOW_WARMUP_SAMPLE_COUNT = 10
IMU_WINDOW_WARMUP_INTERVAL_US = 50_000
IMU_WINDOW_RECORD_BYTES = 28
IMU_WINDOW_SAMPLES_PER_CHUNK = 10
IMU_WINDOW_CHUNK_COUNT = 10
IMU_WINDOW_SAMPLE_ENCODING = "offset_us+six_i32le+base64-v1"
IMU_WINDOW_RAW_FRAME_MAX_BYTES = 1200
IMU_WINDOW_CAPTURE_CMD_ID_MAX = 16
IMU_WINDOW_FW_VERSION_MAX = 32
IMU_WINDOW_TEST_RUN_ID_MAX = 32
IMU_WINDOW_TRANSPORT_TYPES = frozenset({"lte", "wifi"})
COMMAND_NONTERMINAL_STATUSES = frozenset({"pending", "in_progress"})
ACK_NONTERMINAL_STATUSES = frozenset({"pending", "in_progress"})
ACK_TERMINAL_STATUSES = frozenset(
    {"ok", "applied", "error", "rejected", "timeout", "mock_only"}
)
PHOTO_TIMER_ACK_FIELDS = frozenset(
    {
        "config_version",
        "enabled",
        "interval_seconds",
        "session_expires_at_unix_ms",
        "max_photos",
        "captured_count",
        "state_reason",
        "trusted_utc",
    }
)
IMU_WINDOW_COMMON_KEYS = {
    "event-type",
    "priority",
    "source",
    "source-status",
    "fw-version",
    "test-run-id",
    "seq",
    "transport-type",
    "boot-count",
    "contract-version",
    "window-id",
    "capture-cmd-id",
}
IMU_WINDOW_CHUNK_KEYS = IMU_WINDOW_COMMON_KEYS | {
    "chunk-index",
    "chunk-count",
    "sample-start-index",
    "sample-count",
    "total-sample-count",
    "requested-interval-us",
    "sample-record-bytes",
    "sample-encoding",
    "chunk-crc32",
    "samples-b64",
}
IMU_WINDOW_MANIFEST_KEYS = IMU_WINDOW_COMMON_KEYS | {
    "sample-count",
    "requested-interval-us",
    "capture-start-uptime-us",
    "capture-end-uptime-us",
    "min-interval-us",
    "mean-interval-us",
    "max-interval-us",
    "deadline-miss-count",
    "read-failure-count",
    "mock-sample-count",
    "warmup-sample-count",
    "warmup-interval-us",
    "chunk-count",
    "uploaded-chunk-count",
    "samples-crc32",
    "sensor-model",
    "sensor-i2c-address",
    "accel-unit",
    "gyro-unit",
    "activity-label",
    "label-source",
    "collection-authorization",
    "training-allowed",
    "mounting-profile-id",
    "axis-mapping-status",
    "calibration-profile-id",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageHubError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RawPayloadValidationError(ValueError):
    def __init__(self, code: str, message: str, *, profile: str) -> None:
        super().__init__(message)
        self.code = code
        self.profile = profile


def amap_runtime_config() -> tuple[str | None, str | None]:
    api_key = (os.environ.get(AMAP_JS_API_KEY_ENV) or "").strip()
    security_code = (os.environ.get(AMAP_SECURITY_JS_CODE_ENV) or "").strip()
    if not AMAP_CREDENTIAL_PATTERN.fullmatch(api_key):
        api_key = ""
    if not AMAP_CREDENTIAL_PATTERN.fullmatch(security_code):
        security_code = ""
    if not api_key or not security_code:
        return None, None
    return api_key, security_code


def amap_proxy_target(path: str, raw_query: str, api_key: str, security_code: str) -> tuple[str, str]:
    if not api_key or not AMAP_CREDENTIAL_PATTERN.fullmatch(api_key):
        raise MessageHubError("amap_not_configured", "map provider is not configured", status=503)
    if not security_code or not AMAP_CREDENTIAL_PATTERN.fullmatch(security_code):
        raise MessageHubError("amap_not_configured", "map provider is not configured", status=503)
    if len(raw_query.encode("utf-8")) > AMAP_PROXY_MAX_QUERY_BYTES:
        raise MessageHubError("amap_query_too_large", "map provider query is too large", status=414)
    if not path.startswith(AMAP_PROXY_PREFIX + "/"):
        raise MessageHubError("not_found", "route not found", status=404)

    upstream_path = path[len(AMAP_PROXY_PREFIX) :]
    decoded_segments = [unquote(segment) for segment in upstream_path.split("/") if segment]
    if not decoded_segments or any(
        segment in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._~-]+", segment)
        for segment in decoded_segments
    ):
        raise MessageHubError("invalid_amap_path", "invalid map provider path", status=400)
    normalized_path = "/" + "/".join(decoded_segments)
    if upstream_path != normalized_path:
        raise MessageHubError("invalid_amap_path", "non-canonical map provider path", status=404)
    if not AMAP_PROXY_ALLOWED_PATH.match(normalized_path):
        raise MessageHubError("invalid_amap_path", "unsupported map provider path", status=404)
    if normalized_path.startswith("/v4/map/styles/") or normalized_path == "/v4/map/styles":
        upstream_host = "webapi.amap.com"
    else:
        upstream_host = "restapi.amap.com"
    if upstream_host not in AMAP_PROXY_ALLOWED_HOSTS:
        raise MessageHubError("invalid_amap_upstream", "invalid map provider upstream", status=400)

    query_items = [
        (key, value)
        for key, value in parse_qsl(raw_query, keep_blank_values=True)
        if key.lower() not in {"key", "jscode"}
    ]
    query_items.append(("key", api_key))
    query_items.append(("jscode", security_code))
    query_string = urlencode(query_items, doseq=True)
    return upstream_host, normalized_path + ("?" + query_string if query_string else "")


def amap_proxy_cookie_secret(token: str | None, security_code: str) -> bytes:
    token_bytes = (token or "amap-no-bearer-token").encode("utf-8")
    return hmac.new(security_code.encode("utf-8"), token_bytes, hashlib.sha256).digest()


def issue_amap_proxy_cookie(secret: bytes, *, now: int | None = None) -> str:
    expires_at = int(time.time() if now is None else now) + AMAP_PROXY_COOKIE_TTL_S
    payload = str(expires_at)
    signature = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{AMAP_PROXY_COOKIE_NAME}={payload}.{signature}; Max-Age={AMAP_PROXY_COOKIE_TTL_S}; Path={AMAP_PROXY_PREFIX}; Secure; HttpOnly; SameSite=Strict"


def amap_proxy_cookie_valid(cookie_header: str | None, secret: bytes, *, now: int | None = None) -> bool:
    if not cookie_header or len(cookie_header.encode("utf-8")) > AMAP_PROXY_MAX_COOKIE_HEADER_BYTES:
        return False
    cookies = SimpleCookie()
    try:
        cookies.load(cookie_header)
    except CookieError:
        return False
    morsel = cookies.get(AMAP_PROXY_COOKIE_NAME)
    if morsel is None:
        return False
    try:
        expires_text, signature = morsel.value.split(".", 1)
        expires_at = int(expires_text)
    except (ValueError, TypeError):
        return False
    current_time = int(time.time() if now is None else now)
    if expires_at < current_time or expires_at > current_time + AMAP_PROXY_COOKIE_TTL_S:
        return False
    expected = hmac.new(secret, expires_text.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def safe_amap_content_type(value: str | None) -> str:
    media_type = str(value or "application/octet-stream").split(";", 1)[0].strip().lower()
    return media_type if media_type in AMAP_PROXY_ALLOWED_CONTENT_TYPES else "application/octet-stream"


def amap_proxy_content_type(upstream_target: str, value: str | None) -> str:
    """Keep provider types bounded while preserving canonical SDK JSONP calls."""

    upstream_path, separator, raw_query = upstream_target.partition("?")
    callbacks = [
        callback.strip()
        for key, callback in parse_qsl(raw_query, keep_blank_values=True)
        if key.lower() == "callback"
    ] if separator else []
    upstream_media_type = str(value or "application/octet-stream").split(";", 1)[0].strip().lower()
    has_safe_callback = (
        len(callbacks) == 1
        and len(callbacks[0]) <= 128
        and AMAP_PROXY_CALLBACK_PATTERN.fullmatch(callbacks[0]) is not None
    )
    if (
        upstream_path in AMAP_PROXY_JSONP_PATHS
        and has_safe_callback
        and upstream_media_type in AMAP_PROXY_JSONP_SOURCE_TYPES
    ):
        return "application/javascript"
    return safe_amap_content_type(value)


def amap_request_is_same_origin(headers: Mapping[str, str]) -> bool:
    fetch_site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if fetch_site:
        return fetch_site == "same-origin"
    request_host = str(headers.get("Host") or "").strip().lower()
    if not request_host:
        return False
    for header_name in ("Origin", "Referer"):
        source = str(headers.get(header_name) or "").strip()
        if not source:
            continue
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == request_host:
            return True
    return False


class MessageHubStore:
    def __init__(
        self,
        db_path: Path,
        *,
        photo_root: Path | None = None,
        photo_max_bytes: int = DEFAULT_MAX_PHOTO_BYTES,
        photo_device_quota_bytes: int = DEFAULT_DEVICE_QUOTA_BYTES,
    ) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_post_fail_once_seen: set[str] = set()
        self._raw_post_fail_once_lock = threading.Lock()
        self._init_schema()
        self.location_states = LocationStateStore(self.db_path)
        self.manual_sos = ManualSosStore(self.db_path)
        self.photos = PhotoStore(
            self,
            photo_root if photo_root is not None else self.db_path.parent / "photos",
            max_photo_bytes=photo_max_bytes,
            device_quota_bytes=photo_device_quota_bytes,
        )
        self.collection = CollectionStore(self)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self) -> Any:
        db = self.connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    fw_version TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_message_type TEXT,
                    last_seq INTEGER,
                    last_status_json TEXT,
                    latest_telemetry_json TEXT,
                    last_error_json TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    event_type TEXT,
                    seq INTEGER,
                    ts TEXT,
                    server_received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_device_time
                ON messages (device_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_device_received
                ON messages (device_id, server_received_at);

                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cmd_id TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    cmd TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ack_at TEXT,
                    payload_json TEXT NOT NULL,
                    ack_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_commands_device_status
                ON commands (device_id, status, id);

                CREATE INDEX IF NOT EXISTS idx_commands_device_created
                ON commands (device_id, created_at);

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    server_received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS test_runs (
                    test_run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raw_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    frame_type TEXT,
                    seq INTEGER,
                    test_run_id TEXT,
                    fw_version TEXT,
                    content_type TEXT,
                    payload_len INTEGER,
                    payload_crc32 TEXT,
                    raw_payload_sha256 TEXT NOT NULL,
                    raw_payload_b64 TEXT NOT NULL,
                    server_received_at TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    parse_error_code TEXT,
                    parse_reason TEXT,
                    derived_message_type TEXT,
                    derived_message_json TEXT,
                    record_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_raw_frames_device_time
                ON raw_frames (device_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_raw_frames_device_received
                ON raw_frames (device_id, server_received_at);

                CREATE INDEX IF NOT EXISTS idx_raw_frames_test_run
                ON raw_frames (test_run_id, id);

                CREATE TABLE IF NOT EXISTS location_memory (
                    device_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    radius_m REAL,
                    confidence REAL,
                    source_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    belief_updated_at TEXT,
                    last_test_run_id TEXT,
                    memory_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_location_memory_updated
                ON location_memory (updated_at DESC);
                """
            )

    def register_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = require_text(payload, "device_id")
        now = utc_now()
        fw_version = str(payload.get("fw_version") or "unknown")
        with self.connection() as db:
            existing = db.execute(
                "SELECT device_id, first_seen_at FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else now
            db.execute(
                """
                INSERT INTO devices (
                    device_id, fw_version, first_seen_at, last_seen_at,
                    last_message_type, last_seq, last_status_json,
                    latest_telemetry_json, last_error_json
                )
                VALUES (?, ?, ?, ?, 'register', NULL, NULL, NULL, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                    fw_version = excluded.fw_version,
                    last_seen_at = excluded.last_seen_at,
                    last_message_type = 'register'
                """,
                (device_id, fw_version, first_seen_at, now),
            )
        return self.get_device(device_id)

    def ingest(self, device_id: str, endpoint_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._ingest(
            device_id,
            endpoint_type,
            payload,
        )

    def _ingest(
        self,
        device_id: str,
        endpoint_type: str,
        payload: dict[str, Any],
        *,
        ack_identity_sha256: str | None = None,
        ack_outcome: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = normalize_message(self, device_id, endpoint_type, payload)
        server_received_at = utc_now()
        message["server_received_at"] = server_received_at
        message_json = dumps(message)
        message_type = str(message["message_type"])
        event_type = str(message.get("event_type") or "")
        seq = message.get("seq")
        ts = str(message.get("ts") or "")
        fw_version = str(message.get("fw_version") or "unknown")

        with self.connection() as db:
            existing = db.execute(
                "SELECT first_seen_at FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else server_received_at
            db.execute(
                """
                INSERT INTO devices (
                    device_id, fw_version, first_seen_at, last_seen_at,
                    last_message_type, last_seq, last_status_json,
                    latest_telemetry_json, last_error_json
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                    fw_version = COALESCE(NULLIF(excluded.fw_version, 'unknown'), devices.fw_version),
                    last_seen_at = excluded.last_seen_at,
                    last_message_type = excluded.last_message_type,
                    last_seq = excluded.last_seq
                """,
                (device_id, fw_version, first_seen_at, server_received_at, message_type, seq),
            )
            db.execute(
                """
                INSERT INTO messages (
                    device_id, message_type, event_type, seq, ts,
                    server_received_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, message_type, event_type, seq, ts, server_received_at, message_json),
            )
            if message_type == "status":
                db.execute(
                    "UPDATE devices SET last_status_json = ? WHERE device_id = ?",
                    (message_json, device_id),
                )
            elif message_type == "event":
                db.execute(
                    "UPDATE devices SET latest_telemetry_json = ? WHERE device_id = ?",
                    (message_json, device_id),
                )
                if event_type in {"location_report", "location_observation"}:
                    self._record_location_memory(db, device_id, message, server_received_at)
            elif message_type == "ack":
                recorded_outcome = self._record_ack(
                    db,
                    device_id,
                    message,
                    server_received_at,
                    ack_identity_sha256=ack_identity_sha256,
                )
                if ack_outcome is not None:
                    ack_outcome.update(recorded_outcome)
            elif message_type == "error":
                self._record_error(db, device_id, message, server_received_at, message_json)
        return message

    def _record_ack(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
        *,
        ack_identity_sha256: str | None = None,
    ) -> dict[str, Any]:
        reserved_ack_fields = {
            "server_disposition",
            "accepted_ack_sha256",
            "posted_ack_sha256",
            "command_ack",
        }
        if reserved_ack_fields.intersection(message):
            raise MessageHubError(
                "ack_reserved_field",
                "ACK contains a server-owned result field",
            )
        posted_ack_sha256 = (
            ack_identity_sha256
            if isinstance(ack_identity_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", ack_identity_sha256)
            else None
        )

        def outcome(
            disposition: str,
            command_status: str,
            accepted_ack_sha256: str | None = None,
        ) -> dict[str, Any]:
            return {
                "disposition": disposition,
                "command_status": command_status,
                "posted_ack_sha256": posted_ack_sha256,
                "accepted_ack_sha256": accepted_ack_sha256,
            }

        cmd_id = require_text(message, "cmd_id")
        ack_status = require_text(message, "status")
        if ack_status not in ACK_NONTERMINAL_STATUSES | ACK_TERMINAL_STATUSES:
            raise MessageHubError("invalid_ack_status", "ACK status is unsupported")
        command_row_value = db.execute(
            "SELECT status, payload_json, ack_json FROM commands "
            "WHERE device_id = ? AND cmd_id = ?",
            (device_id, cmd_id),
        ).fetchone()
        # Unknown and late ACKs remain immutable message records, but cannot
        # create or rewrite command state.  This is deliberately a no-op here:
        # ingest() inserted the message before calling _record_ack().
        if command_row_value is None:
            return outcome("unknown_command_ignored", "unknown")
        try:
            command = json.loads(str(command_row_value["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise MessageHubError("command_record_invalid", "command record is invalid") from error

        command_status = str(command_row_value["status"] or "")
        try:
            prior_ack = json.loads(str(command_row_value["ack_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            prior_ack = {}
        prior_ack_sha256 = prior_ack.get("accepted_ack_sha256")
        if not (
            isinstance(prior_ack_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", prior_ack_sha256)
        ):
            prior_ack_sha256 = None
        has_timer_state = "timer_state" in message
        if ack_status != "applied" and has_timer_state:
            raise MessageHubError(
                "photo_timer_ack_state_invalid",
                "only an applied timer ACK may report timer_state",
            )
        if command.get("cmd") != "configure_photo_timer" and has_timer_state:
            raise MessageHubError(
                "photo_timer_ack_state_invalid",
                "timer_state is only valid for configure_photo_timer",
            )
        self._assert_photo_ack_consistency(
            db,
            device_id,
            command,
            ack_status,
        )
        expires_at_unix_ms = command.get("expires_at_unix_ms")
        if (
            command_status in COMMAND_NONTERMINAL_STATUSES
            and type(expires_at_unix_ms) is int
            and expires_at_unix_ms <= int(time.time() * 1000)
        ):
            command_status = "expired"
            db.execute(
                "UPDATE commands SET status = 'expired', updated_at = ? "
                "WHERE device_id = ? AND cmd_id = ? "
                "AND status IN ('pending', 'in_progress')",
                (server_received_at, device_id, cmd_id),
            )

        if command_status not in COMMAND_NONTERMINAL_STATUSES:
            if (
                posted_ack_sha256 is not None
                and posted_ack_sha256 == prior_ack_sha256
            ):
                return outcome(
                    "idempotent_already_applied",
                    command_status,
                    prior_ack_sha256,
                )
            if (
                command_status == "applied"
                and ack_status == "applied"
                and command.get("cmd") == "configure_photo_timer"
            ):
                try:
                    validate_photo_timer_ack(
                        command,
                        message,
                        prior_timer_state=as_dict(prior_ack.get("timer_state")),
                    )
                except MessageHubError:
                    # A conflicting terminal refresh is retained in messages,
                    # while the last accepted effective state remains intact.
                    return outcome(
                        "conflict_ignored",
                        command_status,
                        prior_ack_sha256,
                    )
                if not photo_timer_ack_refresh_is_monotonic(prior_ack, message):
                    return outcome(
                        "conflict_ignored",
                        command_status,
                        prior_ack_sha256,
                    )
                stored_ack = dict(message)
                stored_ack["server_disposition"] = "terminal_state_refresh_applied"
                stored_ack["accepted_ack_sha256"] = posted_ack_sha256
                db.execute(
                    """
                    UPDATE commands
                    SET updated_at = ?, ack_json = ?
                    WHERE device_id = ? AND cmd_id = ? AND status = 'applied'
                    """,
                    (
                        server_received_at,
                        dumps(stored_ack),
                        device_id,
                        cmd_id,
                    ),
                )
                return outcome(
                    "refresh_applied",
                    command_status,
                    posted_ack_sha256,
                )
            return outcome(
                "terminal_ack_ignored",
                command_status,
                prior_ack_sha256,
            )

        if command.get("cmd") == "capture_imu_window" and message.get("test_run_id") != command.get(
            "test_run_id"
        ):
            raise MessageHubError(
                "imu_ack_test_run_mismatch",
                "capture_imu_window ACK test_run_id does not match its command",
            )
        if command.get("cmd") == "configure_photo_timer" and ack_status == "applied":
            validate_photo_timer_ack(command, message)

        next_status = (
            command_status
            if ack_status in ACK_NONTERMINAL_STATUSES
            else ack_status
        )
        stored_ack = dict(message)
        stored_ack["server_disposition"] = (
            "nonterminal_ack_recorded"
            if ack_status in ACK_NONTERMINAL_STATUSES
            else "terminal_ack_applied"
        )
        stored_ack["accepted_ack_sha256"] = posted_ack_sha256
        stored_ack_json = dumps(stored_ack)
        accepted_at = (
            server_received_at
            if ack_status in ACK_TERMINAL_STATUSES
            else None
        )
        db.execute(
            """
            UPDATE commands
            SET status = ?, updated_at = ?, ack_at = ?, ack_json = ?
            WHERE device_id = ? AND cmd_id = ?
              AND status IN ('pending', 'in_progress')
            """,
            (
                next_status,
                server_received_at,
                accepted_at,
                stored_ack_json,
                device_id,
                cmd_id,
            ),
        )
        return outcome(
            "nonterminal_recorded"
            if ack_status in ACK_NONTERMINAL_STATUSES
            else "newly_applied",
            next_status,
            posted_ack_sha256,
        )

    @staticmethod
    def _assert_photo_ack_consistency(
        db: sqlite3.Connection,
        device_id: str,
        command: dict[str, Any],
        ack_status: str,
    ) -> None:
        """Prevent cross-queue arrival order from creating terminal lies."""

        command_kind = command.get("cmd")
        if (
            command_kind not in PHOTO_CONTROL_COMMANDS
            or ack_status in ACK_NONTERMINAL_STATUSES
        ):
            return
        allowed_terminal = (
            {"ok", "error"}
            if command_kind == "capture_photo_once"
            else {"applied", "error"}
        )
        if ack_status not in allowed_terminal:
            raise MessageHubError(
                "photo_command_ack_status_invalid",
                "terminal ACK status is invalid for this photo command",
                status=409,
            )
        cmd_id = command.get("cmd_id")
        rows = db.execute(
            "SELECT capture_result,local_save_status FROM photo_records "
            "WHERE device_id=? AND command_id=? ORDER BY id",
            (device_id, cmd_id),
        ).fetchall()
        if not rows:
            return
        if command_kind == "configure_photo_timer":
            consistent = ack_status == "applied"
        else:
            durable = all(
                row["capture_result"] == "captured"
                and row["local_save_status"] == "saved"
                for row in rows
            )
            consistent = ack_status == ("ok" if durable else "error")
        if not consistent:
            raise MessageHubError(
                "photo_command_ack_conflict",
                "terminal photo ACK contradicts an already persisted outcome",
                status=409,
            )

    def _record_error(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
        message_json: str,
    ) -> None:
        error_code = require_text(message, "error_code")
        severity = require_text(message, "severity")
        db.execute(
            """
            INSERT INTO errors (device_id, error_code, severity, server_received_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, error_code, severity, server_received_at, message_json),
        )
        db.execute(
            "UPDATE devices SET last_error_json = ? WHERE device_id = ?",
            (message_json, device_id),
        )

    def _record_location_memory(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
    ) -> None:
        existing = self._location_memory(db, device_id)
        memory = build_location_memory(device_id, message, server_received_at, existing)
        if not memory:
            return
        db.execute(
            """
            INSERT INTO location_memory (
                device_id, state, radius_m, confidence, source_json, reason,
                updated_at, belief_updated_at, last_test_run_id, memory_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                state = excluded.state,
                radius_m = excluded.radius_m,
                confidence = excluded.confidence,
                source_json = excluded.source_json,
                reason = excluded.reason,
                updated_at = excluded.updated_at,
                belief_updated_at = excluded.belief_updated_at,
                last_test_run_id = excluded.last_test_run_id,
                memory_json = excluded.memory_json
            """,
            (
                device_id,
                str(memory.get("state") or "Unknown"),
                memory.get("radius_m"),
                memory.get("confidence"),
                dumps(memory.get("source") if isinstance(memory.get("source"), list) else []),
                str(memory.get("reason") or "no_location_memory"),
                str(memory.get("updated_at") or server_received_at),
                memory.get("belief_updated_at"),
                memory.get("last_test_run_id"),
                dumps(memory),
            ),
        )

    def next_seq(self, device_id: str) -> int:
        with self.connection() as db:
            row = db.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return int(row["max_seq"]) + 1

    def create_command(
        self,
        device_id: str,
        payload: dict[str, Any],
        *,
        photo_control_guardian_id: str | None = None,
    ) -> dict[str, Any]:
        cmd = str(payload.get("cmd") or payload.get("type") or "")
        if not cmd:
            raise MessageHubError("missing_command", "command must include cmd")
        if cmd in PHOTO_CONTROL_COMMANDS:
            if photo_control_guardian_id is None:
                raise MessageHubError(
                    "photo_control_requires_guardian_binding",
                    "photo control requires the Guardian-bound photo route",
                    status=403,
                )
            try:
                self.photos.validate_control_command(
                    device_id,
                    payload,
                    guardian_id=photo_control_guardian_id,
                )
            except PhotoStoreError as error:
                raise MessageHubError(error.code, str(error), status=error.status) from error
        expires_at_unix_ms = payload.get("expires_at_unix_ms")
        if expires_at_unix_ms is not None and (
            type(expires_at_unix_ms) is not int
            or not 0 < expires_at_unix_ms <= 9_007_199_254_740_991
        ):
            raise MessageHubError(
                "invalid_command_expiry",
                "expires_at_unix_ms must be a positive bounded integer",
            )
        now = utc_now()
        now_unix_ms = int(time.time() * 1000)
        requested_cmd_id = payload.get("cmd_id")
        if requested_cmd_id is not None and (
            not isinstance(requested_cmd_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}", requested_cmd_id)
            is None
        ):
            raise MessageHubError(
                "invalid_command_id", "cmd_id must be a bounded identifier"
            )
        if cmd == "capture_imu_window":
            test_run_id = str(payload.get("test_run_id") or "")
            parameters = payload.get("payload")
            if requested_cmd_id is not None and not re.fullmatch(
                rf"[A-Za-z0-9._:-]{{1,{IMU_WINDOW_CAPTURE_CMD_ID_MAX}}}",
                requested_cmd_id,
            ):
                raise MessageHubError(
                    "invalid_imu_capture_cmd_id",
                    "capture_imu_window cmd_id must contain 1-16 safe characters",
                )
            if not re.fullmatch(
                rf"[A-Za-z0-9._:-]{{1,{IMU_WINDOW_TEST_RUN_ID_MAX}}}", test_run_id
            ):
                raise MessageHubError(
                    "invalid_imu_capture_test_run",
                    "capture_imu_window requires a bounded test_run_id",
                )
            if (
                not isinstance(parameters, dict)
                or set(parameters) != {"sample_count", "interval_ms"}
                or type(parameters.get("sample_count")) is not int
                or type(parameters.get("interval_ms")) is not int
                or parameters.get("sample_count") != IMU_WINDOW_SAMPLE_COUNT
                or parameters.get("interval_ms")
                != IMU_WINDOW_INTERVAL_US // 1000
            ):
                raise MessageHubError(
                    "invalid_imu_capture_parameters",
                    "capture_imu_window requires sample_count=100 and interval_ms=50",
                )
        if cmd == "cellular_call_dial":
            call_payload = payload.get("payload")
            if not isinstance(call_payload, dict):
                raise MessageHubError("invalid_call_payload", "cellular_call_dial requires payload object")
            phone_num = call_payload.get("phone_number")
            if not isinstance(phone_num, str) or not re.fullmatch(r"^[0-9+]{3,32}$", phone_num):
                raise MessageHubError("invalid_phone_number", "cellular_call_dial requires valid phone_number (3-32 digits/+)")
        elif cmd == "cellular_call_hangup":
            pass
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if requested_cmd_id is None:
                next_id = int(
                    db.execute(
                        "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM commands"
                    ).fetchone()["next_id"]
                )
                cmd_id = f"cmd-{next_id:06d}"
            else:
                cmd_id = requested_cmd_id
            existing = db.execute(
                "SELECT * FROM commands WHERE cmd_id=?", (cmd_id,)
            ).fetchone()
            existing_command = None
            if existing is not None and existing["device_id"] == device_id:
                try:
                    existing_command = json.loads(existing["payload_json"])
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise MessageHubError(
                        "command_record_invalid", "command record is invalid"
                    ) from error
            created_at = (
                str(existing_command["created_at"])
                if existing_command is not None
                and (cmd == "capture_imu_window" or "created_at" not in payload)
                else now
                if cmd == "capture_imu_window"
                else str(payload.get("created_at") or now)
            )
            command = dict(payload)
            command.update(
                {
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "message_type": "command",
                    "device_id": device_id,
                    "cmd_id": cmd_id,
                    "cmd": cmd,
                    "created_at": created_at,
                }
            )
            command_json = dumps(command)
            if existing is not None:
                if existing["device_id"] != device_id or existing["payload_json"] != command_json:
                    raise MessageHubError(
                        "command_identity_conflict",
                        "cmd_id already has different immutable command content",
                        status=409,
                    )
                db.commit()
                return command_row(existing)
            initial_status = (
                "expired"
                if expires_at_unix_ms is not None
                and expires_at_unix_ms <= now_unix_ms
                else "pending"
            )
            db.execute(
                """
                INSERT INTO commands (
                    cmd_id, device_id, cmd, status, created_at, updated_at,
                    payload_json, ack_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    cmd_id,
                    device_id,
                    cmd,
                    initial_status,
                    command["created_at"],
                    now,
                    command_json,
                ),
            )
            db.commit()
            return command_with_status(command, initial_status)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def poll_commands(self, device_id: str) -> list[dict[str, Any]]:
        now_unix_ms = int(time.time() * 1000)
        with self.connection() as db:
            pending = db.execute(
                "SELECT * FROM commands WHERE device_id=? AND status='pending' "
                "ORDER BY id ASC",
                (device_id,),
            ).fetchall()
            available: list[dict[str, Any]] = []
            for row in pending:
                try:
                    expiry = json.loads(row["payload_json"]).get(
                        "expires_at_unix_ms"
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    expiry = None
                if type(expiry) is int and expiry <= now_unix_ms:
                    db.execute(
                        "UPDATE commands SET status='expired',updated_at=? WHERE id=?",
                        (utc_now(), row["id"]),
                    )
                    continue
                available.append(command_row(row))
        return available

    def list_commands(self, device_id: str, statuses: set[str] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM commands WHERE device_id = ?"
        args: list[Any] = [device_id]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            args.extend(sorted(statuses))
        sql += " ORDER BY id DESC"
        with self.connection() as db:
            rows = db.execute(sql, args).fetchall()
        return [command_row(row) for row in rows]

    def list_devices(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM devices ORDER BY last_seen_at DESC").fetchall()
            devices = [self._device_with_derived_state(db, row) for row in rows]
        return devices

    def get_device(self, device_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
            if row is None:
                raise MessageHubError("device_not_found", f"unknown device: {device_id}", status=404)
            device = self._device_with_derived_state(db, row)
        return device

    def _device_with_derived_state(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        device = device_row(row)
        device["latest_location"] = self._latest_location_event(db, device["device_id"])
        device["latest_location_observation"] = self._latest_event(db, device["device_id"], "location_observation")
        device["location_memory"] = self._location_memory(db, device["device_id"])
        device["last_command"] = self._latest_command(db, device["device_id"])
        device["observability"] = build_observability(device, device["last_command"])
        device["d1_link"] = build_d1_link_summary(
            device,
            self._d1_summary_messages(db, device["device_id"]),
        )
        return device

    def _location_memory(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT memory_json FROM location_memory WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        return json.loads(row["memory_json"]) if row else None

    def _latest_event(self, db: sqlite3.Connection, device_id: str, event_type: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT payload_json FROM messages
            WHERE device_id = ?
              AND message_type = 'event'
              AND event_type = ?
            ORDER BY id DESC LIMIT 1
            """,
            (device_id, event_type),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _latest_location_event(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT payload_json FROM messages
            WHERE device_id = ?
              AND message_type = 'event'
              AND event_type IN ('location_observation', 'location_report')
            ORDER BY id DESC LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _recent_device_messages(self, db: sqlite3.Connection, device_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT payload_json FROM messages
            WHERE device_id = ?
              AND message_type IN ('status', 'event', 'ack', 'error')
            ORDER BY id DESC LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def _d1_summary_messages(self, db: sqlite3.Connection, device_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, payload_json FROM messages
            WHERE device_id = ?
              AND message_type IN ('status', 'event', 'ack', 'error')
            ORDER BY id DESC LIMIT ?
            """,
            (device_id, D1_SUMMARY_MESSAGE_LIMIT),
        ).fetchall()
        messages_by_id = {int(row["id"]): json.loads(row["payload_json"]) for row in rows}

        coordinate_rows = db.execute(
            """
            SELECT id, payload_json FROM messages
            WHERE device_id = ?
              AND message_type = 'event'
              AND event_type IN ('location_observation', 'location_report')
            ORDER BY id DESC LIMIT ?
            """,
            (device_id, D1_COORDINATE_MESSAGE_SCAN_LIMIT),
        ).fetchall()
        coordinate_count = 0
        for row in coordinate_rows:
            message = json.loads(row["payload_json"])
            if d1_location_point(message, source="d1_summary_history") is None:
                continue
            messages_by_id.setdefault(int(row["id"]), message)
            coordinate_count += 1
            if coordinate_count >= D1_COORDINATE_HISTORY_LIMIT:
                break
        return [messages_by_id[key] for key in sorted(messages_by_id, reverse=True)]

    def _latest_command(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM commands
            WHERE device_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        return command_row(row) if row else None

    def latest_telemetry(self, device_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = ? AND message_type IN ('status', 'event', 'error')
                ORDER BY id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def telemetry_history(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = ? AND message_type IN ('status', 'event', 'error', 'ack')
                ORDER BY id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def field_verified_trajectory(self, limit: int = 500) -> dict[str, Any]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = 'ego-link-r1-connectivity-001'
                  AND event_type = 'location_report'
                  AND json_extract(payload_json, '$.lat') > 1.0
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            points = []
            for row in rows:
                p = json.loads(row["payload_json"])
                points.append(
                    {
                        "lat": p.get("lat"),
                        "lng": p.get("lon"),
                        "altitude": p.get("altitude_m"),
                        "speed": p.get("speed_mps"),
                        "course": p.get("course_deg"),
                        "satellites": p.get("satellites"),
                        "hdop": p.get("hdop"),
                        "time": p.get("server_received_at") or p.get("ts"),
                    }
                )
        return {
            "ok": True,
            "track_id": "FW007-HW-20260815-001",
            "device_id": "ego-link-r1-connectivity-001",
            "name": "FW007 \u6df1\u5733\u5916\u573a\u5b9e\u6d4b\u8f68\u8ff9",
            "region": "\u6df1\u5733\u9f99\u5c97",
            "point_count": len(points),
            "points": points,
        }

    def device_trajectory(self, device_id: str, limit: int = 200) -> dict[str, Any]:
        with self.connection() as db:
            gnss_rows = db.execute(
                """
                SELECT envelope_json FROM collection_records
                WHERE device_id = ? AND source = 'gnss'
                ORDER BY id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
            points = []
            latest_gnss = None
            for row in gnss_rows:
                env = json.loads(row["envelope_json"])
                payload = env.get("payload") or {}
                if latest_gnss is None:
                    latest_gnss = payload
                if payload.get("fix") and isinstance(payload.get("latitude"), (int, float)):
                    points.append(
                        {
                            "lat": payload["latitude"],
                            "lng": payload["longitude"],
                            "altitude": payload.get("altitude_m"),
                            "speed": payload.get("speed_mps"),
                            "course": payload.get("course_deg"),
                            "satellites": payload.get("satellites"),
                            "hdop": payload.get("hdop"),
                            "time": env.get("timestamp_utc"),
                        }
                    )
            cell_fallback = None
            lte_row = db.execute(
                """
                SELECT envelope_json FROM collection_records
                WHERE device_id = ? AND source = 'lte'
                ORDER BY id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            if lte_row:
                lte_env = json.loads(lte_row["envelope_json"])
                lte_payload = lte_env.get("payload") or {}
                cell_id = lte_payload.get("cell_id")
                known_towers = {
                    "180571649": (22.751718, 114.228128, "中国移动4G基站 (深圳龙岗天安)"),
                    "213661584": (22.752150, 114.229420, "中国移动4G基站 (深圳龙岗第2小区)"),
                }
                if cell_id:
                    tower_info = known_towers.get(str(cell_id), (22.751718, 114.228128, f"中国移动4G基站 ({cell_id})"))
                    cell_fallback = {
                        "lat": tower_info[0],
                        "lng": tower_info[1],
                        "uncertainty": 300,
                        "isCellTower": True,
                        "cell_id": str(cell_id),
                        "operator": lte_payload.get("operator", "46000"),
                        "name": tower_info[2],
                        "time": lte_env.get("timestamp_utc"),
                    }
            if not cell_fallback:
                mem_row = db.execute(
                    "SELECT memory_json FROM location_memory WHERE device_id = ?",
                    (device_id,),
                ).fetchone()
                if mem_row:
                    mem = json.loads(mem_row["memory_json"])
                    last_loc = mem.get("last_known_location") or {}
                    if last_loc.get("lat"):
                        cell_fallback = {
                            "lat": last_loc["lat"],
                            "lng": last_loc["lon"],
                            "uncertainty": mem.get("radius_m") or 100,
                            "isMemory": True,
                            "name": "\u5386\u53f2\u5df2\u77e5\u4f4d\u7f6e",
                            "time": last_loc.get("updated_at"),
                        }
        return {
            "ok": True,
            "device_id": device_id,
            "point_count": len(points),
            "points": list(reversed(points)),
            "latest_gnss": latest_gnss,
            "cell_fallback": cell_fallback,
        }

    def search_location_history(self, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        search = normalize_location_history_search(payload)
        filter_digest = location_history_filter_digest(device_id, search)
        with self.connection() as db:
            device = db.execute(
                "SELECT device_id FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if device is None:
                raise MessageHubError("device_not_found", f"unknown device: {device_id}", status=404)

            if search["cursor"] is None:
                snapshot_row = db.execute(
                    "SELECT COALESCE(MAX(id), 0) AS snapshot_id FROM messages WHERE device_id = ?",
                    (device_id,),
                ).fetchone()
                snapshot_id = int(snapshot_row["snapshot_id"])
                through_id = snapshot_id
            else:
                snapshot_id, through_id = decode_location_history_cursor(
                    search["cursor"],
                    filter_digest,
                )

            row_cursor = db.execute(
                """
                SELECT id, event_type,
                       CASE WHEN typeof(seq) = 'integer' THEN seq ELSE NULL END AS seq,
                       substr(CAST(ts AS TEXT), 1, 64) AS ts,
                       substr(CAST(server_received_at AS TEXT), 1, 64) AS server_received_at,
                       CASE
                           WHEN length(CAST(payload_json AS BLOB)) <= ? THEN payload_json
                           ELSE NULL
                       END AS payload_json,
                       length(CAST(payload_json AS BLOB)) AS payload_size,
                       length(CAST(payload_json AS BLOB)) > ? AS payload_oversized
                FROM messages
                WHERE device_id = ?
                  AND message_type = 'event'
                  AND event_type IN ('location_report', 'location_observation')
                  AND id <= ?
                  AND id <= ?
                ORDER BY id DESC
                """,
                (
                    LOCATION_HISTORY_MAX_INSPECT_PAYLOAD_BYTES,
                    LOCATION_HISTORY_MAX_INSPECT_PAYLOAD_BYTES,
                    device_id,
                    snapshot_id,
                    through_id,
                ),
            )

            records: list[dict[str, Any]] = []
            inspected_count = 0
            inspected_bytes = 0
            last_inspected_id: int | None = None
            exhausted = False
            received_from = parse_iso_timestamp(search["received_from"])
            received_to = parse_iso_timestamp(search["received_to"])
            while inspected_count < LOCATION_HISTORY_SCAN_LIMIT:
                row = row_cursor.fetchone()
                if row is None:
                    exhausted = True
                    break
                row_bytes = max(0, int(row["payload_size"] or 0))
                if inspected_count > 0 and inspected_bytes + row_bytes > LOCATION_HISTORY_SCAN_BYTE_LIMIT:
                    break
                inspected_count += 1
                inspected_bytes += row_bytes
                last_inspected_id = int(row["id"])
                if search["event_type"] != "all" and row["event_type"] != search["event_type"]:
                    continue
                if search["seq"] is not None and row["seq"] != search["seq"]:
                    continue
                received_at = parse_iso_timestamp(row["server_received_at"])
                if received_from is not None and (
                    received_at is None or received_at < received_from
                ):
                    continue
                if received_to is not None and (
                    received_at is None or received_at > received_to
                ):
                    continue

                record = location_history_record(row)
                if search["trust"] == "selectable" and record["selectable"] is not True:
                    continue
                if search["trust"] == "unselectable" and record["selectable"] is True:
                    continue
                records.append(record)
                if len(records) >= search["page_size"]:
                    break

        next_cursor = (
            None
            if exhausted or last_inspected_id is None
            else encode_location_history_cursor(snapshot_id, max(0, last_inspected_id - 1), filter_digest)
        )
        return {
            "ok": True,
            "device_id": device_id,
            "locations": records,
            "page": {
                "page_size": search["page_size"],
                "returned_count": len(records),
                "selectable_count": sum(1 for record in records if record["selectable"] is True),
                "inspected_count": inspected_count,
                "inspected_bytes": inspected_bytes,
                "scan_limit": LOCATION_HISTORY_SCAN_LIMIT,
                "scan_byte_limit": LOCATION_HISTORY_SCAN_BYTE_LIMIT,
                "snapshot_frozen": True,
                "exhausted": exhausted,
                "current_cursor": encode_location_history_cursor(snapshot_id, through_id, filter_digest),
                "next_cursor": next_cursor,
            },
            "filters": {
                "received_from": search["received_from"],
                "received_to": search["received_to"],
                "seq": search["seq"],
                "event_type": search["event_type"],
                "trust": search["trust"],
            },
            "privacy": {
                "coordinates_for_selectable_records_only": True,
                "query_body_only": True,
                "selection_storage": "browser_memory_only",
            },
        }

    def recent_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT payload_json FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def recent_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [command_row(row) for row in rows]

    def ingest_raw_frame(
        self,
        device_id: str,
        raw_body: bytes,
        *,
        direction: str = "uplink",
        expected_frame_type: str | None = None,
        expected_cmd_id: str | None = None,
    ) -> dict[str, Any]:
        server_received_at = utc_now()
        raw_id, initial = self._insert_raw_frame_initial(device_id, raw_body, direction, server_received_at)
        record = parse_raw_frame_record(
            initial,
            raw_body,
            expected_frame_type=expected_frame_type,
            expected_cmd_id=expected_cmd_id,
        )
        derived_message = as_dict(record["parse_result"].get("derived_message"))
        if (
            record["parse_result"].get("status") == "ok"
            and derived_message.get("event_type") in {"imu_window_chunk", "imu_window_manifest"}
        ):
            authorization_error = self._imu_window_authorization_error(device_id, derived_message)
            if authorization_error is not None:
                authorization_reason = (
                    "IMU window parts for one window must use one transport"
                    if authorization_error == "IMU_WINDOW_MIXED_TRANSPORT"
                    else "IMU window is not bound to an exact authorized capture command"
                )
                record["parse_result"].update(
                    {
                        "status": "malformed",
                        "error_code": authorization_error,
                        "reason": authorization_reason,
                        "derived_message_type": "unknown",
                        "payload_validation": {
                            "profile": IMU_WINDOW_CONTRACT_VERSION,
                            "status": "invalid",
                            "error_code": authorization_error,
                            "reason": authorization_reason,
                        },
                    }
                )
                record["parse_result"].pop("derived_message", None)
                derived_message = {}
        endpoint = derived_endpoint(derived_message.get("message_type"))
        if record["parse_result"]["status"] == "ok" and endpoint:
            try:
                ack_outcome: dict[str, Any] = {}
                self._ingest(
                    device_id,
                    endpoint,
                    derived_message,
                    ack_identity_sha256=(
                        str(as_dict(record.get("raw_payload")).get("sha256"))
                        if endpoint == "ack"
                        else None
                    ),
                    ack_outcome=ack_outcome if endpoint == "ack" else None,
                )
                if ack_outcome:
                    record["command_ack"] = ack_outcome
            except MessageHubError as error:
                record["parse_result"].update(
                    {
                        "status": "malformed",
                        "error_code": "DERIVED_MESSAGE_REJECTED",
                        "reason": str(error),
                    }
                )
        self._update_raw_frame(raw_id, record)
        return record

    def _imu_window_authorization_error(
        self,
        device_id: str,
        derived_message: dict[str, Any],
    ) -> str | None:
        imu_window = as_dict(derived_message.get("imu_window"))
        cmd_id = str(imu_window.get("capture_cmd_id") or "")
        with self.connection() as db:
            row = db.execute(
                "SELECT status, payload_json FROM commands WHERE device_id = ? AND cmd_id = ?",
                (device_id, cmd_id),
            ).fetchone()
            prior_rows = db.execute(
                """
                SELECT derived_message_json
                FROM raw_frames
                WHERE device_id = ? AND parse_status = 'ok' AND derived_message_json IS NOT NULL
                ORDER BY id
                """,
                (device_id,),
            ).fetchall()
        if row is None:
            return "IMU_WINDOW_COMMAND_NOT_FOUND"
        if row["status"] not in {"pending", "in_progress"}:
            return "IMU_WINDOW_COMMAND_NOT_PENDING"
        try:
            command = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return "IMU_WINDOW_COMMAND_INVALID"
        parameters = command.get("payload")
        if (
            command.get("cmd") != "capture_imu_window"
            or command.get("device_id") != device_id
            or command.get("test_run_id") != imu_window.get("test_run_id")
            or not isinstance(parameters, dict)
            or set(parameters) != {"sample_count", "interval_ms"}
            or type(parameters.get("sample_count")) is not int
            or type(parameters.get("interval_ms")) is not int
            or parameters.get("sample_count") != IMU_WINDOW_SAMPLE_COUNT
            or parameters.get("interval_ms") != IMU_WINDOW_INTERVAL_US // 1000
        ):
            return "IMU_WINDOW_COMMAND_MISMATCH"
        for prior_row in prior_rows:
            try:
                prior_message = json.loads(str(prior_row["derived_message_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            prior_imu = as_dict(prior_message.get("imu_window"))
            if prior_imu.get("capture_cmd_id") == cmd_id and prior_imu.get("window_id") != imu_window.get(
                "window_id"
            ):
                return "IMU_WINDOW_COMMAND_ALREADY_BOUND"
            if (
                prior_imu.get("window_id") == imu_window.get("window_id")
                and prior_imu.get("transport_type") != imu_window.get("transport_type")
            ):
                return "IMU_WINDOW_MIXED_TRANSPORT"
        if row["status"] == "pending":
            with self.connection() as db:
                db.execute(
                    """
                    UPDATE commands
                    SET status = 'in_progress', updated_at = ?
                    WHERE device_id = ? AND cmd_id = ? AND status = 'pending'
                    """,
                    (utc_now(), device_id, cmd_id),
                )
        return None

    def claim_raw_post_fail_once(self, device_id: str, raw_body: bytes) -> dict[str, Any] | None:
        probe = parse_raw_frame_probe(device_id, raw_body)
        kv_payload = as_dict(probe.get("kv_payload"))
        if parse_bool_or_text(kv_payload.get("test-inject-raw-post-fail-once")) is not True:
            return None
        frame_id = str(probe.get("frame_id") or "unknown")
        key = f"{device_id}|{frame_id}|{probe['raw_payload_sha256']}"
        with self._raw_post_fail_once_lock:
            if key in self._raw_post_fail_once_seen:
                return None
            self._raw_post_fail_once_seen.add(key)
        return {"key": key, "frame_id": frame_id, "test_run_id": probe.get("test_run_id")}

    def ingest_raw_frame_injected_failure(
        self,
        device_id: str,
        raw_body: bytes,
        *,
        injection: dict[str, Any],
        direction: str = "uplink",
        expected_frame_type: str | None = None,
        expected_cmd_id: str | None = None,
    ) -> dict[str, Any]:
        server_received_at = utc_now()
        raw_id, initial = self._insert_raw_frame_initial(device_id, raw_body, direction, server_received_at)
        record = parse_raw_frame_record(
            initial,
            raw_body,
            expected_frame_type=expected_frame_type,
            expected_cmd_id=expected_cmd_id,
        )
        original_parse = as_dict(record.get("parse_result"))
        record["parse_result"] = {
            "status": "injected_failure",
            "error_code": "RAW_POST_FAIL_ONCE_INJECTED",
            "reason": "test requested fail-once raw POST injection; raw frame retained without deriving message",
            "derived_message_type": "unknown",
            "suppressed_derived_message_type": original_parse.get("derived_message_type"),
        }
        record["injection"] = {
            "name": "raw_post_fail_once",
            "status": "injected_failure",
            "key": injection.get("key"),
        }
        self._update_raw_frame(raw_id, record)
        return record

    def _insert_raw_frame_initial(
        self,
        device_id: str,
        raw_body: bytes,
        direction: str,
        server_received_at: str,
    ) -> tuple[int, dict[str, Any]]:
        record = initial_raw_frame_record(device_id, raw_body, direction, server_received_at)
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT INTO raw_frames (
                    frame_id, device_id, direction, frame_type, seq, test_run_id,
                    fw_version, content_type, payload_len, payload_crc32,
                    raw_payload_sha256, raw_payload_b64, server_received_at,
                    parse_status, parse_error_code, parse_reason,
                    derived_message_type, derived_message_json, record_json
                )
                VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    record["frame_id"],
                    device_id,
                    direction,
                    record["raw_payload"]["sha256"],
                    record["raw_payload"]["data"],
                    server_received_at,
                    record["parse_result"]["status"],
                    dumps(record),
                ),
            )
            raw_id = int(cursor.lastrowid)
        record["raw_frame_row_id"] = raw_id
        return raw_id, record

    def _update_raw_frame(self, raw_id: int, record: dict[str, Any]) -> None:
        framing = as_dict(record.get("framing"))
        parse_result = as_dict(record.get("parse_result"))
        derived_message = as_dict(parse_result.get("derived_message"))
        with self.connection() as db:
            db.execute(
                """
                UPDATE raw_frames
                SET frame_id = ?,
                    frame_type = ?,
                    seq = ?,
                    test_run_id = ?,
                    fw_version = ?,
                    content_type = ?,
                    payload_len = ?,
                    payload_crc32 = ?,
                    parse_status = ?,
                    parse_error_code = ?,
                    parse_reason = ?,
                    derived_message_type = ?,
                    derived_message_json = ?,
                    record_json = ?
                WHERE id = ?
                """,
                (
                    record["frame_id"],
                    framing.get("frame_type"),
                    record.get("seq"),
                    record.get("test_run_id"),
                    record.get("fw_version"),
                    framing.get("content_type"),
                    framing.get("payload_len"),
                    framing.get("payload_crc32"),
                    parse_result.get("status"),
                    parse_result.get("error_code"),
                    parse_result.get("reason"),
                    parse_result.get("derived_message_type"),
                    dumps(derived_message) if derived_message else None,
                    dumps(record),
                    raw_id,
                ),
            )

    def list_raw_frames(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT record_json FROM raw_frames
                WHERE device_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [redact_raw_frame_record(json.loads(row["record_json"])) for row in rows]

    def recent_raw_frames(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT record_json FROM raw_frames ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [redact_raw_frame_record(json.loads(row["record_json"])) for row in rows]

    def poll_commands_raw(self, device_id: str) -> tuple[bytes, dict[str, Any] | None]:
        pending = self.poll_commands(device_id)
        if not pending:
            return build_raw_command_frame(device_id, None), None
        command = pending[0]
        frame = build_raw_command_frame(device_id, command)
        record = self.ingest_raw_frame(
            device_id,
            frame,
            direction="downlink",
            expected_frame_type="command",
            expected_cmd_id=str(command["cmd_id"]),
        )
        return frame, record

    def create_test_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        test_run_id = str(payload.get("test_run_id") or f"test-run-{utc_now().replace(':', '').replace('+', 'Z')}")
        now = utc_now()
        metadata = dict(payload)
        metadata["test_run_id"] = test_run_id
        metadata.setdefault("created_at", now)
        metadata.setdefault("status", "active")
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO test_runs (test_run_id, created_at, status, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (test_run_id, metadata["created_at"], metadata["status"], dumps(metadata)),
            )
        return metadata

    def list_test_runs(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT metadata_json FROM test_runs ORDER BY created_at DESC").fetchall()
        return [json.loads(row["metadata_json"]) for row in rows]

    def export_test_run(self, test_run_id: str) -> dict[str, Any]:
        with self.connection() as db:
            run = db.execute(
                "SELECT metadata_json FROM test_runs WHERE test_run_id = ?",
                (test_run_id,),
            ).fetchone()
            messages = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE payload_json LIKE ?
                ORDER BY id
                """,
                (f'%"{test_run_id}"%',),
            ).fetchall()
            commands = db.execute(
                """
                SELECT * FROM commands
                WHERE payload_json LIKE ? OR ack_json LIKE ?
                ORDER BY id
                """,
                (f'%"{test_run_id}"%', f'%"{test_run_id}"%'),
            ).fetchall()
            raw_frames = db.execute(
                """
                SELECT record_json FROM raw_frames
                WHERE test_run_id = ? OR record_json LIKE ?
                ORDER BY id
                """,
                (test_run_id, f'%"{test_run_id}"%'),
            ).fetchall()
        if run is None:
            raise MessageHubError("test_run_not_found", f"unknown test run: {test_run_id}", status=404)
        test_run = json.loads(run["metadata_json"])
        message_list = [json.loads(row["payload_json"]) for row in messages]
        command_list = [command_row(row) for row in commands]
        raw_frame_list = [redact_raw_frame_record(json.loads(row["record_json"])) for row in raw_frames]
        observability_summary = summarize_test_run_observability(message_list, command_list, raw_frame_list)
        return {
            "test_run": test_run,
            "messages": message_list,
            "commands": command_list,
            "raw_frames": raw_frame_list,
            "observability_summary": observability_summary,
            "run_context": build_run_context(
                messages=message_list,
                commands=command_list,
                raw_frames=raw_frame_list,
                test_run=test_run,
                latest_observability=as_dict(observability_summary.get("latest_observability")),
            ),
        }

    def export_device_time_window(
        self,
        device_id: str,
        *,
        started_at: str,
        ended_at: str,
        max_records: int = FIELD_EXPORT_DEFAULT_MAX_RECORDS,
    ) -> dict[str, Any]:
        start_text, end_text, duration_s, record_limit = validate_field_export_window(
            started_at,
            ended_at,
            max_records,
        )
        query_limit = record_limit + 1
        with self.connection() as db:
            device = db.execute(
                "SELECT device_id FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if device is None:
                raise MessageHubError("device_not_found", f"unknown device: {device_id}", status=404)
            messages = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = ?
                  AND server_received_at >= ?
                  AND server_received_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (device_id, start_text, end_text, query_limit),
            ).fetchall()
            commands = db.execute(
                """
                SELECT * FROM commands
                WHERE device_id = ?
                  AND (
                    (created_at >= ? AND created_at <= ?)
                    OR (updated_at >= ? AND updated_at <= ?)
                    OR (ack_at >= ? AND ack_at <= ?)
                  )
                ORDER BY id
                LIMIT ?
                """,
                (device_id, start_text, end_text, start_text, end_text, start_text, end_text, query_limit),
            ).fetchall()
            raw_frames = db.execute(
                """
                SELECT record_json FROM raw_frames
                WHERE device_id = ?
                  AND server_received_at >= ?
                  AND server_received_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (device_id, start_text, end_text, query_limit),
            ).fetchall()

        truncated = {
            "messages": len(messages) > record_limit,
            "commands": len(commands) > record_limit,
            "raw_frames": len(raw_frames) > record_limit,
        }
        message_list = [json.loads(row["payload_json"]) for row in messages[:record_limit]]
        command_list = [command_row(row) for row in commands[:record_limit]]
        raw_frame_list = [
            redact_raw_frame_record(json.loads(row["record_json"]))
            for row in raw_frames[:record_limit]
        ]
        window_key = sha256_hex(f"{device_id}|{start_text}|{end_text}".encode("utf-8"))[:16]
        test_run = {
            "test_run_id": f"field-window-{window_key}",
            "status": "bounded_export",
            "device_id": device_id,
            "started_at": start_text,
            "ended_at": end_text,
            "created_at": utc_now(),
        }
        observability_summary = summarize_test_run_observability(message_list, command_list, raw_frame_list)
        return {
            "test_run": test_run,
            "messages": message_list,
            "commands": command_list,
            "raw_frames": raw_frame_list,
            "window": {
                "mode": "device_server_received_time",
                "device_id": device_id,
                "started_at": start_text,
                "ended_at": end_text,
                "duration_s": duration_s,
                "max_records_per_collection": record_limit,
                "returned": {
                    "messages": len(message_list),
                    "commands": len(command_list),
                    "raw_frames": len(raw_frame_list),
                },
                "truncated": truncated,
                "complete": not any(truncated.values()),
                "privacy_boundary": "authenticated runtime evidence; do not publish raw coordinates",
            },
            "observability_summary": observability_summary,
            "run_context": build_run_context(
                messages=message_list,
                commands=command_list,
                raw_frames=raw_frame_list,
                test_run=test_run,
                latest_observability=as_dict(observability_summary.get("latest_observability")),
            ),
        }


def validate_photo_timer_ack(
    command: dict[str, Any],
    message: dict[str, Any],
    *,
    prior_timer_state: dict[str, Any] | None = None,
) -> None:
    """Validate the device's applied timer state against immutable command input."""

    timer_state = message.get("timer_state")
    if not isinstance(timer_state, dict) or set(timer_state) != PHOTO_TIMER_ACK_FIELDS:
        raise MessageHubError(
            "photo_timer_ack_state_invalid",
            "configure_photo_timer applied ACK requires one complete timer_state object",
        )

    config_version = timer_state.get("config_version")
    enabled = timer_state.get("enabled")
    interval_seconds = timer_state.get("interval_seconds")
    session_expires_at_unix_ms = timer_state.get("session_expires_at_unix_ms")
    max_photos = timer_state.get("max_photos")
    captured_count = timer_state.get("captured_count")
    state_reason = timer_state.get("state_reason")
    trusted_utc = timer_state.get("trusted_utc")
    if (
        not isinstance(config_version, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}", config_version)
        is None
        or type(enabled) is not bool
        or type(interval_seconds) is not int
        or not 60 <= interval_seconds <= 86_400
        or type(session_expires_at_unix_ms) is not int
        or not 0 < session_expires_at_unix_ms <= 9_007_199_254_740_991
        or type(max_photos) is not int
        or not 1 <= max_photos <= 1000
        or type(captured_count) is not int
        or not 0 <= captured_count <= max_photos
        or not isinstance(state_reason, str)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", state_reason) is None
        or type(trusted_utc) is not bool
    ):
        raise MessageHubError(
            "photo_timer_ack_state_invalid",
            "configure_photo_timer ACK timer_state has invalid types or bounds",
        )

    command_payload = command.get("payload")
    if not isinstance(command_payload, dict):
        raise MessageHubError(
            "command_record_invalid",
            "configure_photo_timer command payload is invalid",
        )
    expected = {
        "config_version": command_payload.get("config_version"),
        "interval_seconds": command_payload.get("interval_seconds"),
        "session_expires_at_unix_ms": command_payload.get(
            "session_expires_at_unix_ms"
        ),
        "max_photos": command_payload.get("max_photos"),
    }
    for field, expected_value in expected.items():
        actual_value = timer_state[field]
        if type(actual_value) is not type(expected_value) or actual_value != expected_value:
            raise MessageHubError(
                "photo_timer_ack_state_mismatch",
                f"configure_photo_timer ACK timer_state.{field} does not match its command",
                status=409,
            )

    requested_enabled = command_payload.get("enabled")
    if prior_timer_state is None:
        enabled_matches = (
            type(enabled) is type(requested_enabled) and enabled == requested_enabled
        )
    else:
        prior_enabled = prior_timer_state.get("enabled")
        enabled_matches = (
            requested_enabled is False
            and enabled is False
            or requested_enabled is True
            and type(prior_enabled) is bool
            and not (prior_enabled is False and enabled is True)
        )
    if not enabled_matches:
        raise MessageHubError(
            "photo_timer_ack_state_mismatch",
            "configure_photo_timer ACK timer_state.enabled conflicts with its command or prior effective state",
            status=409,
        )


def photo_timer_ack_refresh_is_monotonic(
    prior_ack: dict[str, Any],
    candidate_ack: dict[str, Any],
) -> bool:
    """Accept only newer, non-regressing effective timer-state refreshes."""

    prior_timer = as_dict(prior_ack.get("timer_state"))
    candidate_timer = as_dict(candidate_ack.get("timer_state"))
    prior_count = prior_timer.get("captured_count")
    candidate_count = candidate_timer.get("captured_count")
    if (
        type(prior_count) is not int
        or type(candidate_count) is not int
        or candidate_count < prior_count
    ):
        return False

    prior_boot = prior_ack.get("boot_count")
    candidate_boot = candidate_ack.get("boot_count")
    prior_seq = prior_ack.get("seq")
    candidate_seq = candidate_ack.get("seq")
    if type(prior_boot) is int and type(candidate_boot) is int:
        if candidate_boot < prior_boot:
            return False
        if candidate_boot > prior_boot:
            return True
    if type(prior_seq) is int and type(candidate_seq) is int:
        return candidate_seq > prior_seq

    prior_ts = parse_iso_timestamp(prior_ack.get("ts"))
    candidate_ts = parse_iso_timestamp(candidate_ack.get("ts"))
    return (
        prior_ts is not None
        and candidate_ts is not None
        and candidate_ts > prior_ts
    )


def normalize_message(
    store: MessageHubStore,
    device_id: str,
    endpoint_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    message = dict(payload)
    message["protocol_version"] = str(message.get("protocol_version") or protocol.PROTOCOL_VERSION)
    message["device_id"] = str(message.get("device_id") or device_id)
    if message["device_id"] != device_id:
        raise MessageHubError("device_id_mismatch", "path device_id and payload device_id differ", status=409)
    message.setdefault("ts", utc_now())
    message.setdefault("seq", store.next_seq(device_id))

    if endpoint_type == "heartbeat":
        message["message_type"] = "status"
        message.setdefault("battery", None)
        message.setdefault("link_type", "unknown")
        message.setdefault("guard_mode", "unknown")
        message.setdefault("queue_size", 0)
        protocol.require_fields(message, ["protocol_version", "device_id", "ts", "seq", "message_type"])
        return message

    if endpoint_type == "telemetry":
        message["message_type"] = "event"
        message.setdefault("event_type", "telemetry")
        message.setdefault("priority", "normal")
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "event_type", "priority"],
        )
        return message

    if endpoint_type == "ack":
        message["message_type"] = "ack"
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "cmd_id", "status"],
        )
        return message

    if endpoint_type == "error":
        message["message_type"] = "error"
        payload_obj = message.get("payload")
        if isinstance(payload_obj, dict):
            for field in ("error_code", "severity", "message", "recoverable"):
                if field in payload_obj and field not in message:
                    message[field] = payload_obj[field]
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "error_code", "severity"],
        )
        return message

    raise MessageHubError("unknown_endpoint_type", f"unknown endpoint type: {endpoint_type}", status=500)


def make_handler(
    store: MessageHubStore,
    *,
    token: str | None = None,
    guardian_authorizer: GuardianDeviceAuthorizer | None = None,
    product_demo_root: Path = DEFAULT_PRODUCT_DEMO_REPORTS,
    field_results_root: Path = DEFAULT_FIELD_RESULT_REPORTS,
    data_flywheel_root: Path = DEFAULT_DATA_FLYWHEEL_REPORTS,
    training_experiment_root: Path = DEFAULT_TRAINING_EXPERIMENT_REPORTS,
    training_run_root: Path = DEFAULT_TRAINING_RUN_REPORTS,
    training_feature_root: Path = DEFAULT_TRAINING_FEATURE_REPORTS,
    training_runner_dry_run_root: Path = DEFAULT_TRAINING_RUNNER_DRY_RUN_REPORTS,
    training_baseline_eval_root: Path = DEFAULT_TRAINING_BASELINE_EVAL_REPORTS,
    training_handoff_root: Path = DEFAULT_TRAINING_HANDOFF_REPORTS,
    training_job_root: Path = DEFAULT_TRAINING_JOB_REPORTS,
    synthetic_training_chain_root: Path = DEFAULT_SYNTHETIC_TRAINING_CHAIN_REPORTS,
    d1_training_readiness_root: Path = DEFAULT_D1_TRAINING_READINESS_REPORTS,
    d1_labeling_intake_root: Path = DEFAULT_D1_LABELING_INTAKE_REPORTS,
    d1_labeling_queue_root: Path = DEFAULT_D1_LABELING_QUEUE_REPORTS,
    d1_labeling_review_root: Path = DEFAULT_D1_LABELING_REVIEW_REPORTS,
    d1_labeling_decision_root: Path = DEFAULT_D1_LABELING_DECISION_REPORTS,
    progress_board_path: Path = DEFAULT_PROGRESS_BOARD,
) -> type[BaseHTTPRequestHandler]:
    amap_api_key, amap_security_code = amap_runtime_config()
    amap_cookie_secret = (
        amap_proxy_cookie_secret(token, amap_security_code)
        if token is not None and amap_api_key is not None and amap_security_code is not None
        else None
    )
    amap_proxy_slots = threading.BoundedSemaphore(AMAP_PROXY_MAX_CONCURRENCY)

    class MessageHubHandler(BaseHTTPRequestHandler):
        server_version = "EgoLinkMessageHub/0.1"

        def do_GET(self) -> None:
            try:
                self.route_get()
            except MessageHubError as error:
                self.respond_error(error)
            except CollectionError as error:
                self.respond_error(MessageHubError(error.code, str(error), status=error.status))
            except PhotoStoreError as error:
                self.respond_error(MessageHubError(error.code, str(error), status=error.status))
            except ManualSosValidationError:
                self.respond_error(
                    MessageHubError(
                        "invalid_manual_sos",
                        "manual SOS request rejected",
                        status=422,
                    )
                )
            except ManualSosNotFoundError:
                self.respond_error(
                    MessageHubError(
                        "manual_sos_not_found",
                        "manual SOS event was not found",
                        status=404,
                    )
                )
            except ManualSosStoreError:
                self.respond_error(
                    MessageHubError(
                        "manual_sos_store_error",
                        "manual SOS durable store is unavailable",
                        status=500,
                    )
                )
            except (
                LocationStateConflictError,
                LocationStateRegressionError,
                LocationStateValidationError,
            ) as error:
                code = (
                    "location_state_conflict"
                    if isinstance(error, LocationStateConflictError)
                    else "location_state_regression"
                    if isinstance(error, LocationStateRegressionError)
                    else "invalid_location_state"
                )
                self.respond_error(
                    MessageHubError(
                        code,
                        "location state request rejected",
                        status=409 if code != "invalid_location_state" else 422,
                    )
                )
            except Exception as error:  # pragma: no cover - defensive handler boundary.
                self.respond_error(MessageHubError("server_error", str(error), status=500))

        def do_POST(self) -> None:
            try:
                post_segments = split_path(urlparse(self.path).path)
                is_manual_sos_ingest = post_segments == [
                    "api",
                    "v1",
                    "safety-events",
                    "manual-sos",
                ]
                is_guardian_sos_ack = (
                    len(post_segments) == 8
                    and post_segments[:3] == ["api", "v1", "devices"]
                    and post_segments[4:6]
                    == ["safety-events", "manual-sos"]
                    and post_segments[7] == "guardian-ack"
                )
                is_collection_annotation = (
                    len(post_segments) == 6
                    and post_segments[:3] == ["api", "v1", "devices"]
                    and post_segments[4:] == ["collection", "annotations"]
                )
                is_photo_session_authorization = (
                    len(post_segments) == 6
                    and post_segments[:3] == ["api", "v1", "devices"]
                    and post_segments[4:] == ["photos", "sessions"]
                )
                is_photo_content_ingest = (
                    len(post_segments) == 7
                    and post_segments[:3] == ["api", "v1", "devices"]
                    and post_segments[4] == "photos"
                    and post_segments[6] == "content"
                )
                is_photo_control = (
                    len(post_segments) == 7
                    and post_segments[:3] == ["api", "v1", "devices"]
                    and post_segments[4:6] == ["photos", "commands"]
                    and post_segments[6] in {"capture", "timer"}
                )
                if (
                    (
                        post_segments == ["api", "v1", "location-states"]
                        or is_manual_sos_ingest
                        or is_photo_content_ingest
                    )
                    and not token
                ):
                    raise MessageHubError(
                        (
                        "manual_sos_ingest_auth_not_configured"
                        if is_manual_sos_ingest
                        else "photo_ingest_auth_not_configured"
                        if is_photo_content_ingest
                        else "location_state_auth_not_configured"
                    ),
                    (
                        "manual SOS ingest authentication is not configured"
                        if is_manual_sos_ingest
                        else "photo ingest authentication is not configured"
                        if is_photo_content_ingest
                        else "location state authentication is not configured"
                    ),
                        status=503,
                    )
                guardian_authorization = (
                    self.require_guardian_authorization(post_segments[3])
                    if is_guardian_sos_ack
                    or is_collection_annotation
                    or is_photo_session_authorization
                    or is_photo_control
                    else None
                )
                if (
                    not is_guardian_sos_ack
                    and not is_collection_annotation
                    and not is_photo_session_authorization
                    and not is_photo_control
                    and not authorized(self.headers.get("Authorization"), token)
                ):
                    raise MessageHubError("unauthorized", "missing or invalid bearer token", status=401)
                self.route_post(guardian_authorization=guardian_authorization)
            except MessageHubError as error:
                self.respond_error(error)
            except CollectionError as error:
                self.respond_error(MessageHubError(error.code, str(error), status=error.status))
            except PhotoStoreError as error:
                self.respond_error(MessageHubError(error.code, str(error), status=error.status))
            except ManualSosValidationError:
                self.respond_error(
                    MessageHubError(
                        "invalid_manual_sos",
                        "manual SOS request rejected",
                        status=422,
                    )
                )
            except ManualSosConflictError:
                self.respond_error(
                    MessageHubError(
                        "manual_sos_conflict",
                        "manual SOS durable identity conflicts",
                        status=409,
                    )
                )
            except ManualSosNotFoundError:
                self.respond_error(
                    MessageHubError(
                        "manual_sos_not_found",
                        "manual SOS event was not found",
                        status=404,
                    )
                )
            except (ManualSosStoreError, ManualSosDeliveryAckError):
                self.respond_error(
                    MessageHubError(
                        "manual_sos_store_error",
                        "manual SOS durable operation failed",
                        status=500,
                    )
                )
            except json.JSONDecodeError:
                self.respond_error(MessageHubError("invalid_json", "request body is not valid JSON"))
            except (LocationStateConflictError, LocationStateRegressionError, LocationStateValidationError) as error:
                code = "location_state_conflict" if isinstance(error, LocationStateConflictError) else "location_state_regression" if isinstance(error, LocationStateRegressionError) else "invalid_location_state"
                self.respond_error(MessageHubError(code, "location state request rejected", status=409 if code != "invalid_location_state" else 422))
            except Exception as error:  # pragma: no cover - defensive handler boundary.
                self.respond_error(MessageHubError("server_error", str(error), status=500))

        def require_guardian_authorization(self, device_id: str) -> Any:
            if guardian_authorizer is None:
                raise MessageHubError(
                    "guardian_authorization_not_configured",
                    "Guardian device-binding authorization is not configured",
                    status=503,
                )
            decision = guardian_authorizer.authorize(
                self.headers.get("Authorization"), device_id
            )
            if decision.status == "unauthenticated":
                raise MessageHubError(
                    "unauthorized",
                    "missing or invalid Guardian bearer token",
                    status=401,
                )
            if not decision.authorized:
                raise MessageHubError(
                    "forbidden",
                    "Guardian is not bound to the requested device",
                    status=403,
                )
            return decision

        def route_get(self) -> None:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            segments = split_path(path)
            if path in {"/", "/collection", "/collection.js", "/collection.css"}:
                if path in {"/", "/collection"}:
                    self.respond_html(COLLECTION_HTML, headers=COLLECTION_SECURITY_HEADERS)
                else:
                    content, content_type = (COLLECTION_JS, "application/javascript") if path.endswith(".js") else (COLLECTION_CSS, "text/css")
                    self.respond_bytes(content.encode("utf-8"), content_type=content_type + "; charset=utf-8", headers=COLLECTION_SECURITY_HEADERS)
                return
            if path in {"/dev", "/dev/"}:
                index_file = DEV_BENCH_DIR / "index.html"
                if not index_file.is_file():
                    raise MessageHubError("not_found", "DevBench index not found", status=404)
                dev_headers = dict(DEV_BENCH_SECURITY_HEADERS)
                if amap_cookie_secret is not None:
                    dev_headers["Set-Cookie"] = issue_amap_proxy_cookie(amap_cookie_secret)
                self.respond_bytes(
                    index_file.read_bytes(),
                    content_type="text/html; charset=utf-8",
                    headers=dev_headers,
                )
                return
            if path.startswith("/dev/static/"):
                subpath_str = path[len("/dev/static/"):]
                try:
                    unquoted = unquote(subpath_str)
                    target = (DEV_BENCH_DIR / unquoted).resolve()
                    if not target.is_file() or not target.is_relative_to(DEV_BENCH_DIR.resolve()):
                        raise MessageHubError("not_found", "static resource not found", status=404)
                except (ValueError, OSError):
                    raise MessageHubError("not_found", "static resource not found", status=404)
                ext = target.suffix.lower()
                content_type = DEV_BENCH_MIME_TYPES.get(ext, "application/octet-stream")
                self.respond_bytes(
                    target.read_bytes(),
                    content_type=content_type,
                    headers=DEV_BENCH_SECURITY_HEADERS,
                )
                return
            if path == "/api/v1/map/config":
                map_headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
                if amap_cookie_secret is not None:
                    map_headers["Set-Cookie"] = issue_amap_proxy_cookie(amap_cookie_secret)
                self.respond_json(
                    {
                        "configured": amap_api_key is not None,
                        "amap_key": amap_api_key or "",
                        "service_host": "/_AMapService" if amap_api_key else "",
                    },
                    headers=map_headers,
                )
                return
            if path == "/api/v1/trajectories/field-verified":
                self.respond_json(
                    store.field_verified_trajectory(),
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "trajectory":
                self.respond_json(
                    store.device_trajectory(segments[3]),
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "collection":
                self.require_guardian_authorization(segments[3])
                headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
                if segments[5] == "summary":
                    if query:
                        raise CollectionError("invalid_collection_query", "summary has no query parameters", 400)
                    self.respond_json(store.collection.summary(segments[3]), headers=headers)
                elif segments[5] == "records":
                    self.respond_json(store.collection.page(segments[3], query), headers=headers)
                elif segments[5] == "export.jsonl":
                    page = store.collection.page(segments[3], query, raw=True)
                    self.respond_bytes(jsonl_page(page), content_type="application/x-ndjson; charset=utf-8", headers={**headers, "Content-Disposition": 'attachment; filename="egolink-collection.jsonl"'})
                elif segments[5] == "latest-records":
                    source_val = query.get("source", [None])[0]
                    status_val = query.get("status", [None])[0]
                    try:
                        limit_val = int(query.get("limit", [10])[0])
                    except (ValueError, TypeError):
                        limit_val = 10
                    since_id_val = None
                    if "since_id" in query:
                        try:
                            since_id_val = int(query.get("since_id", [0])[0])
                        except (ValueError, TypeError):
                            since_id_val = None
                    self.respond_json(
                        store.collection.latest_records(
                            segments[3],
                            source=source_val,
                            status=status_val,
                            limit=limit_val,
                            since_id=since_id_val,
                        ),
                        headers=headers,
                    )
                elif segments[5] == "ego-state":
                    self.respond_json(
                        {"ok": True, "device_id": segments[3], "ego_state": store.collection.latest_ego_state(segments[3])},
                        headers=headers,
                    )
                else:
                    raise CollectionError("collection_not_found", "collection route does not exist", 404)
                return
            if (
                len(segments) in {5, 6}
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "ego-state"
            ):
                self.require_guardian_authorization(segments[3])
                headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
                sub = segments[5] if len(segments) == 6 else "latest"
                if sub == "latest":
                    if query:
                        raise CollectionError("invalid_collection_query", "ego-state latest has no query parameters", 400)
                    latest = store.collection.latest_ego_state(segments[3])
                    self.respond_json({"ok": True, "device_id": segments[3], "ego_state": latest}, headers=headers)
                elif sub == "timeline":
                    try:
                        limit_val = int(query.get("limit", [50])[0])
                    except (ValueError, TypeError):
                        limit_val = 50
                    timeline = store.collection.ego_state_timeline(segments[3], limit=limit_val)
                    self.respond_json({"ok": True, "device_id": segments[3], "count": len(timeline), "timeline": timeline}, headers=headers)
                else:
                    raise CollectionError("collection_not_found", "ego-state route does not exist", 404)
                return
            if len(segments) == 7 and segments[:3] == ["api", "v1", "devices"] and segments[4:6] == ["collection", "ego-state"]:
                self.require_guardian_authorization(segments[3])
                headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
                if segments[6] == "latest":
                    if query:
                        raise CollectionError("invalid_collection_query", "ego-state latest has no query parameters", 400)
                    self.respond_json({"ok": True, "device_id": segments[3], "ego_state": store.collection.latest_ego_state(segments[3])}, headers=headers)
                elif segments[6] == "timeline":
                    try:
                        limit_val = int(query.get("limit", [50])[0])
                    except (ValueError, TypeError):
                        limit_val = 50
                    timeline = store.collection.ego_state_timeline(segments[3], limit=limit_val)
                    self.respond_json({"ok": True, "device_id": segments[3], "count": len(timeline), "timeline": timeline}, headers=headers)
                else:
                    raise CollectionError("collection_not_found", "ego-state route does not exist", 404)
                return
            is_photo_route = (
                len(segments) in {5, 6, 7}
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "photos"
            )
            if is_photo_route:
                self.require_guardian_authorization(segments[3])
                headers = {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                }
                if len(segments) == 5:
                    self.respond_json(
                        store.photos.list(segments[3], query), headers=headers
                    )
                elif len(segments) == 6:
                    if segments[5] == "commands":
                        if query:
                            raise PhotoStoreError(
                                "invalid_photo_query",
                                "photo command status has no query parameters",
                                400,
                            )
                        store.poll_commands(segments[3])
                        commands = [
                            command
                            for command in store.list_commands(segments[3])
                            if command.get("cmd") in PHOTO_CONTROL_COMMANDS
                        ]
                        self.respond_json(
                            {
                                "commands": commands,
                                "camera_runtime_state": store.collection.latest_source_state(
                                    segments[3], "camera"
                                ),
                            },
                            headers=headers,
                        )
                    elif segments[5] == "export.json":
                        exported = store.photos.export_all(segments[3], query)
                        exported["exported_at"] = utc_now()
                        exported["scope"] = "private_photo_metadata_and_collection_observation"
                        self.respond_json(
                            exported,
                            headers={
                                **headers,
                                "Content-Disposition": (
                                    'attachment; filename="egolink-photo-observations.json"'
                                ),
                            },
                        )
                    elif query:
                        raise PhotoStoreError(
                            "invalid_photo_query",
                            "photo metadata has no query parameters",
                            400,
                        )
                    else:
                        self.respond_json(
                            {"photo": store.photos.metadata(segments[3], segments[5])},
                            headers=headers,
                        )
                elif segments[6] == "content":
                    if query:
                        raise PhotoStoreError(
                            "invalid_photo_query",
                            "photo content has no query parameters",
                            400,
                        )
                    body, photo = store.photos.content(segments[3], segments[5])
                    self.respond_bytes(
                        body,
                        content_type="image/jpeg",
                        headers={
                            **headers,
                            "Content-Security-Policy": "default-src 'none'; sandbox",
                            "X-Content-SHA256": str(photo["content"]["sha256"]),
                        },
                    )
                else:
                    raise PhotoStoreError(
                        "photo_not_found", "photo route does not exist", 404
                    )
                return
            is_location_state_current = (
                len(segments) == 6
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:] == ["location-state", "current"]
            )
            is_manual_sos_latest = (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:]
                == ["safety-events", "manual-sos", "latest"]
            )
            manual_sos_authorization = (
                self.require_guardian_authorization(segments[3])
                if is_manual_sos_latest
                else None
            )
            location_authorization = None
            if is_location_state_current and guardian_authorizer is not None:
                location_authorization = guardian_authorizer.authorize(
                    self.headers.get("Authorization"), segments[3]
                )
                if location_authorization.status == "unauthenticated":
                    raise MessageHubError(
                        "unauthorized",
                        "missing or invalid Guardian bearer token",
                        status=401,
                    )
                if location_authorization.status != "authorized":
                    raise MessageHubError(
                        "forbidden",
                        "Guardian is not bound to the requested device",
                        status=403,
                    )
            elif is_location_state_current and not token:
                raise MessageHubError(
                    "location_state_auth_not_configured",
                    "location state authentication is not configured",
                    status=503,
                )
            if path == "/engineering":
                self.respond_html(render_dashboard(amap_js_api_key=amap_api_key))
                return
            if path == GUARDIAN_LOCATION_PATH:
                self.respond_html(
                    GUARDIAN_LOCATION_HTML,
                    headers=GUARDIAN_LOCATION_SECURITY_HEADERS,
                )
                return
            if path == GUARDIAN_LOCATION_JS_PATH:
                self.respond_bytes(
                    GUARDIAN_LOCATION_JS.encode("utf-8"),
                    content_type="application/javascript; charset=utf-8",
                    headers=GUARDIAN_LOCATION_SECURITY_HEADERS,
                )
                return
            if path == GUARDIAN_LOCATION_CSS_PATH:
                self.respond_bytes(
                    GUARDIAN_LOCATION_CSS.encode("utf-8"),
                    content_type="text/css; charset=utf-8",
                    headers=GUARDIAN_LOCATION_SECURITY_HEADERS,
                )
                return
            if path == "/d2-reference-capture":
                self.respond_html(render_d2_reference_capture())
                return
            if path == "/health":
                self.respond_json({"ok": True, "service": "egolink-message-hub", "time": utc_now()})
                return
            if path.startswith(AMAP_PROXY_PREFIX + "/"):
                if amap_api_key is None or amap_security_code is None or amap_cookie_secret is None:
                    raise MessageHubError("amap_not_configured", "map provider is not configured", status=503)
                if not amap_proxy_cookie_valid(self.headers.get("Cookie"), amap_cookie_secret):
                    raise MessageHubError("amap_proxy_unauthorized", "map provider session required", status=403)
                if not amap_request_is_same_origin(self.headers):
                    raise MessageHubError("amap_same_origin_required", "same-origin map request required", status=403)
                self.proxy_amap(path, parsed_url.query, amap_api_key, amap_security_code)
                return
            if (
                segments
                and segments[0] == "api"
                and not (
                    is_location_state_current
                    and location_authorization is not None
                    and location_authorization.authorized
                )
                and not (
                    is_manual_sos_latest
                    and manual_sos_authorization is not None
                    and manual_sos_authorization.authorized
                )
                and not authorized(self.headers.get("Authorization"), token)
            ):
                raise MessageHubError("unauthorized", "missing or invalid bearer token", status=401)
            if path == "/api/state":
                devices = store.list_devices()
                messages = store.recent_messages(20)
                commands = store.recent_commands(20)
                raw_frames = store.recent_raw_frames(20)
                product_demo = load_latest_product_demo_report(product_demo_root)
                field_results = load_latest_field_results(field_results_root)
                data_flywheel = load_latest_data_flywheel_status(data_flywheel_root)
                training_experiment = load_latest_training_experiment_plan(training_experiment_root)
                training_run_preflight = load_latest_training_run_preflight(training_run_root)
                training_feature_manifest = load_latest_training_feature_manifest(training_feature_root)
                training_runner_dry_run = load_latest_training_runner_dry_run(training_runner_dry_run_root)
                training_baseline_eval = load_latest_training_baseline_eval(training_baseline_eval_root)
                training_handoff_bundle = load_latest_training_handoff_bundle(training_handoff_root)
                training_job_plan = load_latest_training_job_plan(training_job_root)
                synthetic_training_chain = load_latest_synthetic_training_chain(synthetic_training_chain_root)
                d1_training_readiness = load_latest_d1_training_readiness(d1_training_readiness_root)
                d1_labeling_intake = load_latest_d1_labeling_intake(d1_labeling_intake_root)
                d1_labeling_queue = load_latest_d1_labeling_queue(d1_labeling_queue_root)
                d1_labeling_review_packet = load_latest_d1_labeling_review_packet(d1_labeling_review_root)
                d1_labeling_decision_template = load_latest_d1_labeling_decision_template(
                    d1_labeling_decision_root
                )
                progress_board = load_progress_board(progress_board_path)
                response_headers = (
                    {"Set-Cookie": issue_amap_proxy_cookie(amap_cookie_secret)}
                    if amap_cookie_secret is not None
                    else None
                )
                self.respond_json(
                    {
                        "devices": devices,
                        "messages": messages,
                        "commands": commands,
                        "raw_frames": raw_frames,
                        "product_demo": product_demo,
                        "field_results": field_results,
                        "data_flywheel": data_flywheel,
                        "training_experiment": training_experiment,
                        "training_run_preflight": training_run_preflight,
                        "training_feature_manifest": training_feature_manifest,
                        "training_runner_dry_run": training_runner_dry_run,
                        "training_baseline_eval": training_baseline_eval,
                        "training_handoff_bundle": training_handoff_bundle,
                        "training_job_plan": training_job_plan,
                        "synthetic_training_chain": synthetic_training_chain,
                        "d1_training_readiness": d1_training_readiness,
                        "d1_labeling_intake": d1_labeling_intake,
                        "d1_labeling_queue": d1_labeling_queue,
                        "d1_labeling_review_packet": d1_labeling_review_packet,
                        "d1_labeling_decision_template": d1_labeling_decision_template,
                        "progress_board": progress_board,
                        "current_run": build_run_context(
                            messages=messages,
                            commands=commands,
                            raw_frames=raw_frames,
                            devices=devices,
                            test_runs=store.list_test_runs(),
                        ),
                    },
                    headers=response_headers,
                )
                return
            if segments == ["api", "v1", "devices"]:
                self.respond_json({"devices": store.list_devices()})
                return
            if len(segments) == 4 and segments[:3] == ["api", "v1", "devices"]:
                self.respond_json({"device": store.get_device(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "telemetry",
                "latest",
            ]:
                self.respond_json({"telemetry": store.latest_telemetry(segments[3])})
                return
            if is_location_state_current:
                if parsed_url.query:
                    raise MessageHubError("location_state_query_forbidden", "current location state accepts no query parameters")
                self.respond_json(
                    {
                        "location_state": store.location_states.authenticated_current(
                            segments[3],
                            utc_now_ns=time.time_ns(),
                            location_access_authorized=(
                                location_authorization is not None
                                and location_authorization.authorized
                            ),
                            authorization_subject=(
                                location_authorization.guardian_id
                                if location_authorization is not None
                                else None
                            ),
                        )
                    },
                    headers={"Cache-Control": "no-store"},
                )
                return
            if is_manual_sos_latest:
                if parsed_url.query:
                    raise MessageHubError(
                        "manual_sos_query_forbidden",
                        "latest manual SOS accepts no query parameters",
                    )
                self.respond_json(
                    {
                        "manual_sos_alert": store.manual_sos.latest_alert(
                            segments[3],
                            authorization_subject=(
                                manual_sos_authorization.guardian_id
                                if manual_sos_authorization is not None
                                else ""
                            ),
                        )
                    },
                    headers={"Cache-Control": "no-store"},
                )
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "telemetry",
                "history",
            ]:
                self.respond_json({"telemetry": store.telemetry_history(segments[3])})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "commands":
                self.respond_json({"commands": store.list_commands(segments[3])})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "raw-frames":
                self.respond_json({"raw_frames": store.list_raw_frames(segments[3])})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "field-export":
                started_at = query_text(query, "started_at")
                ended_at = query_text(query, "ended_at")
                max_records_text = query_text(query, "max_records", required=False)
                try:
                    max_records = (
                        int(max_records_text)
                        if max_records_text is not None
                        else FIELD_EXPORT_DEFAULT_MAX_RECORDS
                    )
                except ValueError as exc:
                    raise MessageHubError("invalid_max_records", "max_records must be an integer") from exc
                self.respond_json(
                    store.export_device_time_window(
                        segments[3],
                        started_at=started_at,
                        ended_at=ended_at,
                        max_records=max_records,
                    )
                )
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "commands",
                "poll",
            ]:
                self.respond_json({"commands": store.poll_commands(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "commands",
                "poll.raw",
            ]:
                frame, record = store.poll_commands_raw(segments[3])
                self.respond_bytes(
                    frame,
                    content_type="text/x-egolink-frame; profile=raw-frame.p0.v1",
                    headers={"X-Ego-Link-Raw-Frame-Id": record["frame_id"] if record else "none"},
                )
                return
            if segments == ["api", "v1", "test-runs"]:
                self.respond_json({"test_runs": store.list_test_runs()})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "test-runs"] and segments[4] == "export":
                self.respond_json(store.export_test_run(segments[3]))
                return
            if segments == ["api", "v1", "product-demo", "latest"]:
                self.respond_json({"product_demo": load_latest_product_demo_report(product_demo_root)})
                return
            if segments == ["api", "v1", "field-results", "latest"]:
                self.respond_json({"field_results": load_latest_field_results(field_results_root)})
                return
            if segments == ["api", "v1", "progress", "latest"]:
                self.respond_json({"progress_board": load_progress_board(progress_board_path)})
                return
            if segments == ["api", "v1", "data-flywheel", "latest"]:
                self.respond_json({"data_flywheel": load_latest_data_flywheel_status(data_flywheel_root)})
                return
            if segments == ["api", "v1", "training-experiments", "latest"]:
                self.respond_json(
                    {"training_experiment": load_latest_training_experiment_plan(training_experiment_root)}
                )
                return
            if segments == ["api", "v1", "training-runs", "latest"]:
                self.respond_json({"training_run_preflight": load_latest_training_run_preflight(training_run_root)})
                return
            if segments == ["api", "v1", "training-features", "latest"]:
                self.respond_json(
                    {"training_feature_manifest": load_latest_training_feature_manifest(training_feature_root)}
                )
                return
            if segments == ["api", "v1", "training-runner-dry-runs", "latest"]:
                self.respond_json(
                    {"training_runner_dry_run": load_latest_training_runner_dry_run(training_runner_dry_run_root)}
                )
                return
            if segments == ["api", "v1", "training-baseline-evals", "latest"]:
                self.respond_json(
                    {"training_baseline_eval": load_latest_training_baseline_eval(training_baseline_eval_root)}
                )
                return
            if segments == ["api", "v1", "training-handoffs", "latest"]:
                self.respond_json(
                    {"training_handoff_bundle": load_latest_training_handoff_bundle(training_handoff_root)}
                )
                return
            if segments == ["api", "v1", "training-jobs", "latest"]:
                self.respond_json({"training_job_plan": load_latest_training_job_plan(training_job_root)})
                return
            if segments == ["api", "v1", "synthetic-training-chains", "latest"]:
                self.respond_json(
                    {"synthetic_training_chain": load_latest_synthetic_training_chain(synthetic_training_chain_root)}
                )
                return
            if segments == ["api", "v1", "d1-training-readiness", "latest"]:
                self.respond_json(
                    {"d1_training_readiness": load_latest_d1_training_readiness(d1_training_readiness_root)}
                )
                return
            if segments == ["api", "v1", "d1-labeling-intake", "latest"]:
                self.respond_json({"d1_labeling_intake": load_latest_d1_labeling_intake(d1_labeling_intake_root)})
                return
            if segments == ["api", "v1", "d1-labeling-queue", "latest"]:
                self.respond_json({"d1_labeling_queue": load_latest_d1_labeling_queue(d1_labeling_queue_root)})
                return
            if segments == ["api", "v1", "d1-labeling-review-packet", "latest"]:
                self.respond_json(
                    {"d1_labeling_review_packet": load_latest_d1_labeling_review_packet(d1_labeling_review_root)}
                )
                return
            if segments == ["api", "v1", "d1-labeling-decision-template", "latest"]:
                self.respond_json(
                    {
                        "d1_labeling_decision_template": load_latest_d1_labeling_decision_template(
                            d1_labeling_decision_root
                        )
                    }
                )
                return
            raise MessageHubError("not_found", "route not found", status=404)

        def route_post(self, *, guardian_authorization: Any = None) -> None:
            parsed_url = urlparse(self.path)
            segments = split_path(parsed_url.path)
            if (
                len(segments) == 6
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:] == ["photos", "sessions"]
            ):
                if guardian_authorization is None or not guardian_authorization.authorized:
                    raise PhotoStoreError(
                        "forbidden", "Guardian device binding is required", 403
                    )
                if parsed_url.query:
                    raise PhotoStoreError(
                        "invalid_photo_query",
                        "photo authorization has no query parameters",
                        400,
                    )
                result = store.photos.authorize_session(
                    segments[3],
                    self.read_json_body(),
                    guardian_id=guardian_authorization.guardian_id,
                )
                self.respond_json(
                    result,
                    headers={
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:6] == ["photos", "commands"]
                and segments[6] in {"capture", "timer"}
            ):
                if guardian_authorization is None or not guardian_authorization.authorized:
                    raise PhotoStoreError(
                        "forbidden", "Guardian device binding is required", 403
                    )
                if parsed_url.query:
                    raise PhotoStoreError(
                        "invalid_photo_query",
                        "photo control has no query parameters",
                        400,
                    )
                requested = self.read_json_body()
                command = {
                    "cmd": (
                        "capture_photo_once"
                        if segments[6] == "capture"
                        else "configure_photo_timer"
                    ),
                    **requested,
                }
                result = store.create_command(
                    segments[3],
                    command,
                    photo_control_guardian_id=guardian_authorization.guardian_id,
                )
                self.respond_json(
                    {"ok": True, "command": result},
                    headers={
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "photos"
                and segments[6] == "content"
            ):
                if parsed_url.query:
                    raise PhotoStoreError(
                        "invalid_photo_query",
                        "photo content upload has no query parameters",
                        400,
                    )
                try:
                    body, claimed_sha256, transport = self.read_photo_body()
                except PhotoStoreError as error:
                    store.photos.record_rejected_upload(
                        segments[3], segments[5], error_code=error.code
                    )
                    raise
                result = store.photos.store_content(
                    segments[3],
                    segments[5],
                    body,
                    claimed_sha256=claimed_sha256,
                    transport=transport,
                )
                self.respond_json(
                    result,
                    headers={
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == ["collection", "annotations"]:
                if guardian_authorization is None or not guardian_authorization.authorized:
                    raise CollectionError("forbidden", "device binding is required", 403)
                if parsed_url.query:
                    raise CollectionError("invalid_annotation", "annotation is sent only in the request body", 400)
                result = store.collection.annotate(segments[3], self.read_raw_body(), operator_id=guardian_authorization.guardian_id)
                self.respond_json(result, headers={"Cache-Control": "no-store"})
                return
            is_manual_sos_ingest = segments == [
                "api",
                "v1",
                "safety-events",
                "manual-sos",
            ]
            is_guardian_sos_ack = (
                len(segments) == 8
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:6] == ["safety-events", "manual-sos"]
                and segments[7] == "guardian-ack"
            )
            is_location_history_search = (
                len(segments) == 6
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4:] == ["locations", "search"]
            )
            if is_location_history_search and parsed_url.query:
                raise MessageHubError(
                    "location_history_query_string_forbidden",
                    "location history search accepts JSON body fields only",
                )
            if (is_manual_sos_ingest or is_guardian_sos_ack) and parsed_url.query:
                raise MessageHubError(
                    "manual_sos_query_forbidden",
                    "manual SOS routes accept no query parameters",
                )
            if is_manual_sos_ingest:
                raw_body = self.read_manual_sos_body()
                ack_time_ms = int(time.time() * 1000)
                result = store.manual_sos.ingest(
                    raw_body,
                    server_receive_time_ms=ack_time_ms,
                )
                delivery_ack = build_manual_sos_delivery_ack(
                    raw_body,
                    result,
                    ack_time_ms=ack_time_ms,
                )
                self.respond_json(
                    {
                        "ok": True,
                        "result": {"status": result["status"]},
                        "delivery_ack": delivery_ack,
                        "delivery_scope": MANUAL_SOS_DELIVERY_SCOPE,
                    },
                    headers={"Cache-Control": "no-store"},
                )
                return
            if is_guardian_sos_ack:
                self.require_empty_request_body()
                if guardian_authorization is None or not guardian_authorization.authorized:
                    raise MessageHubError(
                        "forbidden",
                        "Guardian authorization is required",
                        status=403,
                    )
                result = store.manual_sos.acknowledge(
                    segments[3],
                    segments[6],
                    guardian_id=guardian_authorization.guardian_id,
                    acknowledged_at_ms=int(time.time() * 1000),
                )
                self.respond_json(
                    {"ok": True, "guardian_ack": result},
                    headers={"Cache-Control": "no-store"},
                )
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "raw-ingest":
                device_id = segments[3]
                raw_body = self.read_raw_body()
                collection_probe = parse_raw_frame_probe(device_id, raw_body)
                if is_collection_content_type(collection_probe.get("content_type")) or b"profile=egolink.collection.v1" in raw_body[:4096]:
                    if not token:
                        raise CollectionError("collection_auth_not_configured", "collection ingest authentication is not configured", 503)
                    initial = initial_raw_frame_record(device_id, raw_body, "uplink", utc_now())
                    record = parse_raw_frame_record(initial, raw_body, expected_frame_type="event")
                    if not is_collection_content_type(as_dict(record.get("framing")).get("content_type")):
                        raise CollectionError("invalid_collection_frame", "collection content type does not match its profile")
                    result = store.collection.ingest(raw_body, record, transport=str(self.headers.get("X-EgoLink-Transport") or ""))
                    self.respond_json(result, headers={"Cache-Control": "no-store"})
                    return
                injection = store.claim_raw_post_fail_once(device_id, raw_body)
                if injection:
                    record = store.ingest_raw_frame_injected_failure(device_id, raw_body, injection=injection)
                    self.respond_json(
                        {
                            "ok": False,
                            "error": "raw_post_fail_once_injected",
                            "detail": "test requested fail-once raw POST injection",
                            "raw_frame": redact_raw_frame_record(record),
                        },
                        status=503,
                    )
                    return
                record = store.ingest_raw_frame(device_id, raw_body)
                parse_result = as_dict(record.get("parse_result"))
                payload_validation = as_dict(parse_result.get("payload_validation"))
                recognizable_imu_part = b"event_type=imu_window_" in raw_body or b"event-type=imu_window_" in raw_body
                if parse_result.get("status") != "ok" and (
                    payload_validation.get("status") == "invalid" or recognizable_imu_part
                ):
                    self.respond_json(
                        {
                            "ok": False,
                            "error": payload_validation.get("error_code")
                            or parse_result.get("error_code")
                            or "raw_frame_invalid",
                            "detail": payload_validation.get("reason")
                            or parse_result.get("reason")
                            or "raw frame validation failed",
                            "raw_frame": redact_raw_frame_record(record),
                        },
                        status=422,
                    )
                    return
                self.respond_json({"ok": True, "raw_frame": redact_raw_frame_record(record)})
                return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "commands"
                and segments[6] == "ack.raw"
            ):
                device_id = segments[3]
                record = store.ingest_raw_frame(
                    device_id,
                    self.read_raw_body(),
                    expected_frame_type="ack",
                    expected_cmd_id=segments[5],
                )
                parse_result = as_dict(record.get("parse_result"))
                if parse_result.get("status") != "ok":
                    self.respond_json(
                        {
                            "ok": False,
                            "error": parse_result.get("error_code") or "raw_ack_invalid",
                            "detail": parse_result.get("reason") or "raw ACK validation failed",
                            "raw_frame": redact_raw_frame_record(record),
                        },
                        status=422,
                    )
                    return
                self.respond_json(
                    {
                        "ok": True,
                        "raw_frame": redact_raw_frame_record(record),
                        "command_ack": as_dict(record.get("command_ack")),
                    },
                    headers={"Cache-Control": "no-store"},
                )
                return
            if segments == ["api", "v1", "location-states"]:
                raw_body = self.read_raw_body()
                body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                if not isinstance(body, dict):
                    raise MessageHubError("invalid_json", "request body must be a JSON object")
                ack_time_ms = int(time.time() * 1000)
                result = store.location_states.ingest(
                    body,
                    server_receive_time_ms=ack_time_ms,
                )
                delivery_ack = build_location_state_delivery_ack(
                    raw_body,
                    body,
                    result,
                    ack_time_ms=ack_time_ms,
                )
                self.respond_json(
                    {
                        "ok": True,
                        "result": result,
                        "delivery_ack": delivery_ack,
                        "delivery_scope": "server_durable_ingest_only",
                    },
                    headers={"Cache-Control": "no-store"},
                )
                return
            body = self.read_json_body()
            if segments == ["api", "v1", "devices", "register"]:
                self.respond_json({"ok": True, "device": store.register_device(body)})
                return
            if is_location_history_search:
                self.respond_json(
                    store.search_location_history(segments[3], body),
                    headers={"Cache-Control": "no-store"},
                )
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"]:
                device_id = segments[3]
                endpoint = segments[4]
                if endpoint in {"heartbeat", "telemetry", "ack", "error"}:
                    self.respond_json({"ok": True, "message": store.ingest(device_id, endpoint, body)})
                    return
                if endpoint == "commands":
                    self.respond_json({"ok": True, "command": store.create_command(device_id, body)})
                    return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "commands"
                and segments[6] == "ack"
            ):
                device_id = segments[3]
                body.setdefault("cmd_id", segments[5])
                self.respond_json({"ok": True, "message": store.ingest(device_id, "ack", body)})
                return
            if segments == ["api", "v1", "test-runs"]:
                self.respond_json({"ok": True, "test_run": store.create_test_run(body)})
                return
            raise MessageHubError("not_found", "route not found", status=404)

        def read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            if length > MAX_BODY_BYTES:
                raise MessageHubError("body_too_large", "request body is too large", status=413)
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise MessageHubError("invalid_json", "request body must be a JSON object")
            return value

        def read_photo_body(self) -> tuple[bytes, str, str]:
            if self.headers.get("Transfer-Encoding") is not None:
                raise PhotoStoreError(
                    "invalid_photo_length",
                    "photo upload requires one bounded Content-Length",
                )
            lengths = self.headers.get_all("Content-Length") or []
            if (
                len(lengths) != 1
                or not lengths[0].strip().isdigit()
                or len(lengths[0].strip()) > len(str(store.photos.max_photo_bytes))
            ):
                raise PhotoStoreError(
                    "invalid_photo_length",
                    "photo upload requires one bounded Content-Length",
                )
            length = int(lengths[0].strip())
            if length < 4:
                raise PhotoStoreError(
                    "invalid_photo_length", "photo content is too short"
                )
            if length > store.photos.max_photo_bytes:
                raise PhotoStoreError(
                    "photo_body_too_large",
                    "photo content exceeds its configured limit",
                    413,
                )
            media_type = str(self.headers.get("Content-Type") or "").split(
                ";", 1
            )[0].strip().lower()
            if media_type != "image/jpeg":
                raise PhotoStoreError(
                    "photo_content_type_required",
                    "photo upload requires image/jpeg",
                    415,
                )
            claimed_sha256 = str(
                self.headers.get("X-Content-SHA256") or ""
            ).strip()
            transport = str(self.headers.get("X-EgoLink-Transport") or "").strip()
            body = self.rfile.read(length)
            if len(body) != length:
                raise PhotoStoreError(
                    "incomplete_photo_body",
                    "photo upload ended before Content-Length",
                )
            return body, claimed_sha256, transport

        def read_manual_sos_body(self) -> bytes:
            if self.headers.get("Transfer-Encoding") is not None:
                raise MessageHubError(
                    "invalid_manual_sos_length",
                    "manual SOS requires one bounded Content-Length",
                )
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1 or not lengths[0].strip().isdigit():
                raise MessageHubError(
                    "invalid_manual_sos_length",
                    "manual SOS requires one bounded Content-Length",
                )
            length_text = lengths[0].strip()
            if len(length_text) > len(str(MAX_MANUAL_SOS_BODY_BYTES)):
                raise MessageHubError(
                    "manual_sos_body_too_large",
                    "manual SOS request body is too large",
                    status=413,
                )
            length = int(length_text)
            if length <= 0:
                raise MessageHubError(
                    "invalid_manual_sos_length",
                    "manual SOS body must be nonempty",
                )
            if length > MAX_MANUAL_SOS_BODY_BYTES:
                raise MessageHubError(
                    "manual_sos_body_too_large",
                    "manual SOS request body is too large",
                    status=413,
                )
            raw_body = self.rfile.read(length)
            if len(raw_body) != length:
                raise MessageHubError(
                    "incomplete_manual_sos_body",
                    "manual SOS body ended before Content-Length",
                )
            media_type = str(self.headers.get("Content-Type") or "").split(
                ";", 1
            )[0].strip().lower()
            if media_type != "application/json":
                raise MessageHubError(
                    "manual_sos_content_type_required",
                    "manual SOS requires application/json",
                    status=415,
                )
            return raw_body

        def require_empty_request_body(self) -> None:
            if self.headers.get("Transfer-Encoding") is not None:
                raise MessageHubError(
                    "guardian_ack_body_forbidden",
                    "Guardian acknowledgement accepts no request body",
                )
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) > 1:
                raise MessageHubError(
                    "guardian_ack_body_forbidden",
                    "Guardian acknowledgement accepts no request body",
                )
            if lengths:
                value = lengths[0].strip()
                if (
                    not value.isdigit()
                    or len(value) > 1
                    or int(value) != 0
                ):
                    raise MessageHubError(
                        "guardian_ack_body_forbidden",
                        "Guardian acknowledgement accepts no request body",
                    )

        def read_raw_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return b""
            if length > MAX_BODY_BYTES:
                raise MessageHubError("body_too_large", "request body is too large", status=413)
            return self.rfile.read(length)

        def respond_json(
            self,
            payload: dict[str, Any],
            status: int = 200,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def respond_html(
            self,
            html: str,
            status: int = 200,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def respond_bytes(
            self,
            body: bytes,
            *,
            content_type: str,
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def respond_error(self, error: MessageHubError) -> None:
            error_path = urlparse(self.path).path
            private_headers = (
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                }
                if "/photos" in error_path
                else {"Cache-Control": "no-store"}
            )
            headers = (
                private_headers
                if error_path.endswith("/locations/search")
                or "/collection/" in error_path
                or "/photos" in error_path
                or error_path.endswith("/location-state/current")
                or "/safety-events/manual-sos" in error_path
                or error_path == "/api/v1/safety-events/manual-sos"
                else None
            )
            self.respond_json(
                {"ok": False, "error": error.code, "detail": str(error)},
                status=error.status,
                headers=headers,
            )

        def proxy_amap(self, path: str, raw_query: str, api_key: str, security_code: str) -> None:
            upstream_host, upstream_target = amap_proxy_target(path, raw_query, api_key, security_code)
            upstream_path = upstream_target.partition("?")[0]
            if not amap_proxy_slots.acquire(blocking=False):
                raise MessageHubError("amap_proxy_busy", "map provider proxy is busy", status=503)
            deadline = time.monotonic() + AMAP_PROXY_TOTAL_DEADLINE_S
            connection: http.client.HTTPSConnection | None = None
            try:
                connection = http.client.HTTPSConnection(
                    upstream_host,
                    timeout=min(AMAP_PROXY_TIMEOUT_S, AMAP_PROXY_TOTAL_DEADLINE_S),
                )
                connection.request(
                    "GET",
                    upstream_target,
                    headers={"Accept": self.headers.get("Accept", "*/*"), "User-Agent": "EgoLinkAMapProxy/1"},
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MessageHubError("amap_upstream_timeout", "map provider request timed out", status=504)
                if connection.sock is not None:
                    connection.sock.settimeout(max(0.001, min(AMAP_PROXY_TIMEOUT_S, remaining)))
                response = connection.getresponse()
                if time.monotonic() > deadline:
                    raise MessageHubError("amap_upstream_timeout", "map provider request timed out", status=504)
                declared_length = response.getheader("Content-Length")
                if declared_length:
                    try:
                        parsed_length = int(declared_length)
                    except ValueError as exc:
                        raise MessageHubError("amap_invalid_response", "map provider response is invalid", status=502) from exc
                    if parsed_length < 0 or parsed_length > AMAP_PROXY_MAX_RESPONSE_BYTES:
                        raise MessageHubError("amap_response_too_large", "map provider response is too large", status=502)
                chunks: list[bytes] = []
                total = 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MessageHubError("amap_upstream_timeout", "map provider request timed out", status=504)
                    if connection.sock is not None:
                        connection.sock.settimeout(max(0.001, min(AMAP_PROXY_TIMEOUT_S, remaining)))
                    chunk = response.read(min(AMAP_PROXY_READ_CHUNK_BYTES, AMAP_PROXY_MAX_RESPONSE_BYTES - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > AMAP_PROXY_MAX_RESPONSE_BYTES:
                        raise MessageHubError("amap_response_too_large", "map provider response is too large", status=502)
                    chunks.append(chunk)
                body = b"".join(chunks)
                content_type = amap_proxy_content_type(upstream_target, response.getheader("Content-Type"))
                cache_control = "no-store" if upstream_path in {
                    "/v3/assistant/coordinate/convert",
                    "/v3/log/init",
                } else "private, max-age=60"
                proxy_headers = {
                    "Cache-Control": cache_control,
                    "X-Content-Type-Options": "nosniff",
                }
                if amap_cookie_secret is not None:
                    proxy_headers["Set-Cookie"] = issue_amap_proxy_cookie(amap_cookie_secret)
                self.respond_bytes(
                    body,
                    content_type=content_type,
                    status=response.status,
                    headers=proxy_headers,
                )
            except MessageHubError:
                raise
            except (OSError, http.client.HTTPException, ValueError) as exc:
                raise MessageHubError("amap_upstream_error", "map provider request failed", status=502) from exc
            finally:
                if connection is not None:
                    connection.close()
                amap_proxy_slots.release()

        def log_message(self, format: str, *args: Any) -> None:
            return

    return MessageHubHandler


def split_path(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/") if segment]


def authorized(header: str | None, token: str | None) -> bool:
    if not token:
        return True
    return header == f"Bearer {token}"


def normalize_location_history_search(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {
        "page_size",
        "cursor",
        "received_from",
        "received_to",
        "seq",
        "event_type",
        "trust",
    }
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise MessageHubError(
            "location_history_unknown_field",
            "location history request contains an unsupported field",
        )

    page_size_value = payload.get("page_size", LOCATION_HISTORY_DEFAULT_PAGE_SIZE)
    if isinstance(page_size_value, bool) or not isinstance(page_size_value, int):
        raise MessageHubError("invalid_location_history_page_size", "page_size must be an integer")
    page_size = page_size_value
    if page_size < 1 or page_size > LOCATION_HISTORY_MAX_PAGE_SIZE:
        raise MessageHubError(
            "invalid_location_history_page_size",
            f"page_size must be between 1 and {LOCATION_HISTORY_MAX_PAGE_SIZE}",
        )

    cursor_value = payload.get("cursor")
    if cursor_value is None:
        cursor = None
    elif not isinstance(cursor_value, str) or len(cursor_value) > 512:
        raise MessageHubError("invalid_location_history_cursor", "cursor is invalid")
    else:
        cursor = cursor_value

    normalized_times: dict[str, str | None] = {}
    for field in ("received_from", "received_to"):
        value = payload.get(field)
        if value is None:
            normalized_times[field] = None
            continue
        if not isinstance(value, str) or len(value) > 64:
            raise MessageHubError("invalid_location_history_time", f"{field} must be an ISO-8601 timestamp")
        parsed = parse_iso_timestamp(value)
        if parsed is None:
            raise MessageHubError("invalid_location_history_time", f"{field} must be an ISO-8601 timestamp")
        normalized_times[field] = parsed.astimezone(timezone.utc).isoformat()
    received_from = normalized_times["received_from"]
    received_to = normalized_times["received_to"]
    if received_from and received_to:
        from_dt = parse_iso_timestamp(received_from)
        to_dt = parse_iso_timestamp(received_to)
        if from_dt is None or to_dt is None or from_dt > to_dt:
            raise MessageHubError(
                "invalid_location_history_time_window",
                "received_from must be before or equal to received_to",
            )

    seq_value = payload.get("seq")
    if seq_value is None:
        seq = None
    elif isinstance(seq_value, bool) or not isinstance(seq_value, int):
        raise MessageHubError("invalid_location_history_seq", "seq must be a non-negative integer")
    else:
        seq = seq_value
        if seq < 0 or seq > SQLITE_SIGNED_INT64_MAX:
            raise MessageHubError("invalid_location_history_seq", "seq must be a non-negative integer")

    event_type_value = payload.get("event_type", "all")
    if not isinstance(event_type_value, str) or event_type_value not in LOCATION_HISTORY_EVENT_TYPES:
        raise MessageHubError(
            "invalid_location_history_event_type",
            "event_type must be all, location_report, or location_observation",
        )
    event_type = event_type_value
    trust_value = payload.get("trust", "all")
    if not isinstance(trust_value, str) or trust_value not in LOCATION_HISTORY_TRUST_FILTERS:
        raise MessageHubError(
            "invalid_location_history_trust",
            "trust must be all, selectable, or unselectable",
        )
    trust = trust_value
    return {
        "page_size": page_size,
        "cursor": cursor,
        "received_from": received_from,
        "received_to": received_to,
        "seq": seq,
        "event_type": event_type,
        "trust": trust,
    }


def location_history_filter_digest(device_id: str, search: dict[str, Any]) -> str:
    canonical = dumps(
        {
            "device_id": device_id,
            "received_from": search.get("received_from"),
            "received_to": search.get("received_to"),
            "seq": search.get("seq"),
            "event_type": search.get("event_type"),
            "trust": search.get("trust"),
        }
    ).encode("utf-8")
    return sha256_hex(canonical)[:24]


def encode_location_history_cursor(snapshot_id: int, through_id: int, filter_digest: str) -> str:
    cursor_payload = dumps(
        {"snapshot_id": snapshot_id, "through_id": through_id, "filter": filter_digest}
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(cursor_payload).decode("ascii").rstrip("=")
    return f"{LOCATION_HISTORY_CURSOR_PREFIX}.{encoded}"


def decode_location_history_cursor(cursor: str, expected_filter_digest: str) -> tuple[int, int]:
    parts = cursor.split(".")
    if len(parts) != 2 or parts[0] != LOCATION_HISTORY_CURSOR_PREFIX:
        raise MessageHubError("invalid_location_history_cursor", "cursor is invalid")
    encoded = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,384}", encoded):
        raise MessageHubError("invalid_location_history_cursor", "cursor is invalid")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise MessageHubError("invalid_location_history_cursor", "cursor is invalid") from exc
    if not isinstance(value, dict) or set(value) != {"snapshot_id", "through_id", "filter"}:
        raise MessageHubError("invalid_location_history_cursor", "cursor is invalid")
    snapshot_id = value.get("snapshot_id")
    through_id = value.get("through_id")
    if (
        isinstance(snapshot_id, bool)
        or isinstance(through_id, bool)
        or not isinstance(snapshot_id, int)
        or not isinstance(through_id, int)
        or snapshot_id < 0
        or snapshot_id > SQLITE_SIGNED_INT64_MAX
        or through_id < 0
        or through_id > SQLITE_SIGNED_INT64_MAX
        or through_id > snapshot_id
        or value.get("filter") != expected_filter_digest
    ):
        raise MessageHubError("invalid_location_history_cursor", "cursor does not match this search")
    return snapshot_id, through_id


def require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None or str(value) == "":
        raise MessageHubError("missing_field", f"missing required field: {field}")
    return str(value)


def query_text(query: Mapping[str, list[str]], field: str, *, required: bool = True) -> str | None:
    values = query.get(field) or []
    value = values[0].strip() if values else ""
    if not value:
        if required:
            raise MessageHubError("missing_query_parameter", f"missing required query parameter: {field}")
        return None
    return value


def dumps(payload: Any, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":") if indent is None else None, indent=indent)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def crc32_hex(value: bytes) -> str:
    return f"{binascii.crc32(value) & 0xFFFFFFFF:08X}"


def initial_raw_frame_record(
    device_id: str,
    raw_body: bytes,
    direction: str,
    server_received_at: str,
) -> dict[str, Any]:
    digest = sha256_hex(raw_body)
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "transport_profile": RAW_FRAME_PROFILE,
        "direction": direction,
        "device_id": device_id,
        "frame_id": f"raw-{digest[:12]}",
        "server_received_at": server_received_at,
        "raw_payload": {
            "encoding": "base64",
            "data": base64.b64encode(raw_body).decode("ascii"),
            "byte_len": len(raw_body),
            "sha256": digest,
            "crc32": crc32_hex(raw_body),
        },
        "parse_result": {
            "status": "not_attempted",
            "derived_message_type": "unknown",
        },
        "retention": {
            "privacy_class": "engineering",
            "redacted": False,
        },
    }


def parse_raw_frame_record(
    initial: dict[str, Any],
    raw_body: bytes,
    *,
    expected_frame_type: str | None = None,
    expected_cmd_id: str | None = None,
) -> dict[str, Any]:
    record = json.loads(dumps(initial))
    header_bytes, payload, has_separator = split_raw_frame_bytes(raw_body)
    if not has_separator:
        record["parse_result"] = {
            "status": "partial",
            "error_code": "RAW_FRAME_HEADER_INCOMPLETE",
            "reason": "raw frame is missing a blank line before payload",
            "derived_message_type": "unknown",
        }
        return record

    header = parse_raw_header(header_bytes)
    fields = header["fields"]
    metadata = header["metadata"]
    frame_id = first_known(fields.get("id"), fields.get("frame_id"), expected_cmd_id, record["frame_id"])
    frame_type = str(fields.get("type") or "raw")
    content_type = str(first_known(fields.get("content-type"), fields.get("content_type"), metadata.get("content-type"), "application/octet-stream"))
    seq = parse_optional_int(fields.get("seq"))
    declared_len = parse_optional_int(fields.get("len"))
    declared_crc = normalize_crc32(fields.get("crc32"))
    payload_crc = crc32_hex(payload)
    kv_payload = parse_kv_payload(payload) if content_type.startswith("text/x-egolink-kv") else {}

    record.update(
        {
            "frame_id": str(frame_id),
            "seq": seq,
            "fw_version": first_known(kv_payload.get("fw-version"), fields.get("fw"), fields.get("fw-version")),
            "test_run_id": first_known(kv_payload.get("test-run-id"), fields.get("test-run-id")),
            "framing": {
                "magic": "EGLK" if header["magic_ok"] else str(header["magic"]),
                "frame_version": header["frame_version"],
                "frame_type": frame_type,
                "content_type": content_type,
                "payload_len": declared_len if declared_len is not None else len(payload),
                "payload_crc32": declared_crc or payload_crc,
                "actual_payload_len": len(payload),
                "actual_payload_crc32": payload_crc,
            },
        }
    )

    parse_result = validate_raw_frame_header(
        header,
        frame_type,
        declared_len,
        declared_crc,
        payload,
        expected_frame_type=expected_frame_type,
    )
    if parse_result["status"] == "ok":
        event_type = first_known(kv_payload.get("event-type"), kv_payload.get("event_type"))
        if frame_type == "event" and event_type in {"imu_window_chunk", "imu_window_manifest"}:
            try:
                kv_payload = parse_imu_window_kv_payload(payload)
                event_type = str(kv_payload.get("event-type") or "")
                validate_imu_window_wire(
                    event_type,
                    kv_payload,
                    raw_body=raw_body,
                    frame_id=str(frame_id),
                    frame_seq=seq,
                )
                parse_result["payload_validation"] = {
                    "profile": IMU_WINDOW_CONTRACT_VERSION,
                    "status": "valid",
                }
            except RawPayloadValidationError as error:
                parse_result.update(
                    {
                        "transport_status": "ok",
                        "status": "malformed",
                        "error_code": error.code,
                        "reason": str(error),
                        "derived_message_type": "unknown",
                        "payload_validation": {
                            "profile": error.profile,
                            "status": "invalid",
                            "error_code": error.code,
                            "reason": str(error),
                        },
                    }
                )
        if parse_result["status"] != "ok":
            record["parse_result"] = parse_result
            return record
        lineage_error = validate_raw_frame_lineage(
            kv_payload,
            header_seq_value=fields.get("seq"),
        )
        if lineage_error is not None:
            error_code, reason = lineage_error
            parse_result.update(
                {
                    "transport_status": "ok",
                    "status": "malformed",
                    "error_code": error_code,
                    "reason": reason,
                    "derived_message_type": "unknown",
                }
            )
            record["parse_result"] = parse_result
            return record
        derived = derive_raw_frame_message(record, kv_payload, expected_cmd_id=expected_cmd_id)
        parse_result.update(
            {
                "derived_message_type": str(derived.get("message_type") or "unknown"),
                "derived_message": derived,
            }
        )
        if expected_cmd_id and derived.get("cmd_id") and str(derived["cmd_id"]) != expected_cmd_id:
            parse_result.update(
                {
                    "status": "malformed",
                    "error_code": "RAW_FRAME_CMD_ID_MISMATCH",
                    "reason": "raw frame command ID does not match route command ID",
                }
            )
    record["parse_result"] = parse_result
    return record


def parse_raw_frame_probe(device_id: str, raw_body: bytes) -> dict[str, Any]:
    initial = initial_raw_frame_record(device_id, raw_body, "uplink", utc_now())
    header_bytes, payload, has_separator = split_raw_frame_bytes(raw_body)
    result: dict[str, Any] = {
        "device_id": device_id,
        "frame_id": initial["frame_id"],
        "raw_payload_sha256": initial["raw_payload"]["sha256"],
        "kv_payload": {},
        "test_run_id": None,
    }
    if not has_separator:
        return result
    header = parse_raw_header(header_bytes)
    fields = header["fields"]
    metadata = header["metadata"]
    content_type = str(
        first_known(
            fields.get("content-type"),
            fields.get("content_type"),
            metadata.get("content-type"),
            "application/octet-stream",
        )
    )
    kv_payload = parse_kv_payload(payload) if content_type.startswith("text/x-egolink-kv") else {}
    result.update(
        {
            "frame_id": str(first_known(fields.get("id"), fields.get("frame-id"), initial["frame_id"])),
            "content_type": content_type,
            "kv_payload": kv_payload,
            "test_run_id": first_known(kv_payload.get("test-run-id"), fields.get("test-run-id")),
        }
    )
    return result


def split_raw_frame_bytes(raw_body: bytes) -> tuple[bytes, bytes, bool]:
    for separator in (b"\r\n\r\n", b"\n\n"):
        index = raw_body.find(separator)
        if index >= 0:
            return raw_body[:index], raw_body[index + len(separator) :], True
    return raw_body, b"", False


def parse_raw_header(header_bytes: bytes) -> dict[str, Any]:
    text = header_bytes.decode("ascii", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else ""
    tokens = first.split()
    magic = tokens[0] if tokens else ""
    magic_match = re.fullmatch(r"EGLK/(\d+)", magic)
    fields = parse_key_tokens(tokens[1:])
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        metadata[normalize_key(key)] = value.strip()
    return {
        "magic": magic,
        "magic_ok": bool(magic_match),
        "frame_version": int(magic_match.group(1)) if magic_match else None,
        "fields": fields,
        "metadata": metadata,
    }


def parse_key_tokens(tokens: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[normalize_key(key)] = value.strip()
    return fields


def normalize_key(key: str) -> str:
    return key.strip().lower().replace("_", "-")


def normalize_crc32(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text.upper() if re.fullmatch(r"[0-9A-Fa-f]{8}", text) else text


def parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value), 10)
    except ValueError:
        return None


def validate_raw_frame_lineage(
    kv_payload: dict[str, str],
    *,
    header_seq_value: Any = None,
) -> tuple[str, str] | None:
    """Reject unusable lineage before a raw frame becomes a derived event."""

    payload_seq_value = kv_payload.get("seq")
    parsed_sequences: dict[str, int] = {}
    for source, seq_value in (
        ("payload", payload_seq_value),
        ("header", header_seq_value),
    ):
        if seq_value not in (None, ""):
            seq = parse_optional_int(seq_value)
            if seq is None or seq < 0:
                return (
                    "RAW_FRAME_INVALID_SEQUENCE",
                    f"raw frame {source} seq must be a non-negative integer",
                )
            parsed_sequences[source] = seq
    if (
        "payload" in parsed_sequences
        and "header" in parsed_sequences
        and parsed_sequences["payload"] != parsed_sequences["header"]
    ):
        return (
            "RAW_FRAME_SEQUENCE_MISMATCH",
            "raw frame EGLK header seq does not match payload seq",
        )

    boot_value = kv_payload.get("boot-count")
    if boot_value not in (None, ""):
        boot_count = parse_optional_int(boot_value)
        if boot_count is None or boot_count < 0 or boot_count > 2**32 - 1:
            return (
                "RAW_FRAME_INVALID_BOOT_COUNT",
                "raw frame boot_count must be an unsigned 32-bit integer",
            )

    timestamp = kv_payload.get("ts")
    if timestamp not in (None, ""):
        uptime_match = re.fullmatch(r"uptime_ms:([0-9]+)", timestamp)
        if uptime_match is not None:
            if int(uptime_match.group(1)) <= 2**63 - 1:
                return None
        else:
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None and parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return None
        return (
            "RAW_FRAME_INVALID_TIMESTAMP",
            "raw frame ts must be valid uptime_ms:<non-negative-int64> or timezone-aware ISO-8601",
        )
    return None


def validate_raw_frame_header(
    header: dict[str, Any],
    frame_type: str,
    declared_len: int | None,
    declared_crc: str | None,
    payload: bytes,
    *,
    expected_frame_type: str | None = None,
) -> dict[str, Any]:
    if not header["magic_ok"] or header["frame_version"] != 1:
        return {
            "status": "unsupported",
            "error_code": "RAW_FRAME_UNSUPPORTED_MAGIC",
            "reason": "raw frame magic/version is not EGLK/1",
            "derived_message_type": "unknown",
        }
    if frame_type not in {"status", "event", "command", "ack", "error", "log", "raw"}:
        return {
            "status": "unsupported",
            "error_code": "RAW_FRAME_UNSUPPORTED_TYPE",
            "reason": f"unsupported raw frame type: {frame_type}",
            "derived_message_type": "unknown",
        }
    if expected_frame_type and frame_type != expected_frame_type:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_TYPE_MISMATCH",
            "reason": f"expected {expected_frame_type} frame, got {frame_type}",
            "derived_message_type": "unknown",
        }
    if declared_len is None or declared_crc is None:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_MISSING_LENGTH_OR_CRC",
            "reason": "raw frame must include len and crc32",
            "derived_message_type": "unknown",
        }
    if len(payload) < declared_len:
        return {
            "status": "partial",
            "error_code": "RAW_FRAME_PAYLOAD_PARTIAL",
            "reason": f"payload has {len(payload)} bytes, expected {declared_len}",
            "derived_message_type": "unknown",
        }
    if len(payload) != declared_len:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_PAYLOAD_LENGTH_MISMATCH",
            "reason": f"payload has {len(payload)} bytes, expected {declared_len}",
            "derived_message_type": "unknown",
        }
    if declared_crc.upper() != crc32_hex(payload):
        return {
            "status": "checksum_failed",
            "error_code": "RAW_FRAME_PAYLOAD_CRC_MISMATCH",
            "reason": "payload CRC32 does not match frame header",
            "derived_message_type": "unknown",
        }
    return {"status": "ok", "derived_message_type": "unknown"}


def parse_kv_payload(payload: bytes) -> dict[str, str]:
    text = payload.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[normalize_key(key)] = value.strip()
    return result


def parse_imu_window_kv_payload(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RawPayloadValidationError(
            "IMU_WINDOW_INVALID_UTF8",
            "IMU window payload must be valid UTF-8",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        ) from error
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            raise RawPayloadValidationError(
                "IMU_WINDOW_INVALID_KV_STRUCTURE",
                "IMU window payload must contain only non-empty key=value lines",
                profile=IMU_WINDOW_CONTRACT_VERSION,
            )
        key, value = line.split("=", 1)
        normalized = normalize_key(key)
        if not normalized or normalized in result:
            raise RawPayloadValidationError(
                "IMU_WINDOW_DUPLICATE_OR_EMPTY_KEY",
                "IMU window payload contains a duplicate or empty key",
                profile=IMU_WINDOW_CONTRACT_VERSION,
            )
        result[normalized] = value.strip()
    return result


def imu_window_required_text(kv_payload: dict[str, str], key: str) -> str:
    value = str(kv_payload.get(key) or "").strip()
    if not value:
        raise RawPayloadValidationError(
            "IMU_WINDOW_MISSING_FIELD",
            f"IMU window payload is missing {key}",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    return value


def imu_window_required_int(
    kv_payload: dict[str, str],
    key: str,
    *,
    minimum: int = 0,
    maximum: int = 2**63 - 1,
) -> int:
    value = parse_optional_int(kv_payload.get(key))
    if value is None or value < minimum or value > maximum:
        raise RawPayloadValidationError(
            "IMU_WINDOW_INVALID_INTEGER",
            f"IMU window field {key} must be an integer in [{minimum}, {maximum}]",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    return value


def validate_imu_window_common(kv_payload: dict[str, str]) -> dict[str, Any]:
    contract_version = imu_window_required_text(kv_payload, "contract-version")
    if contract_version != IMU_WINDOW_CONTRACT_VERSION:
        raise RawPayloadValidationError(
            "IMU_WINDOW_UNSUPPORTED_CONTRACT",
            "unsupported IMU window contract version",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    source = imu_window_required_text(kv_payload, "source")
    source_status = imu_window_required_text(kv_payload, "source-status")
    if source != "qmi8658_i2c" or source_status != "observed":
        raise RawPayloadValidationError(
            "IMU_WINDOW_REAL_SOURCE_REQUIRED",
            "IMU window requires source=qmi8658_i2c and source_status=observed",
            profile=contract_version,
        )
    priority = imu_window_required_text(kv_payload, "priority")
    transport_type = imu_window_required_text(kv_payload, "transport-type")
    if priority != "normal":
        raise RawPayloadValidationError(
            "IMU_WINDOW_NORMAL_PRIORITY_REQUIRED",
            "IMU window v1 requires priority=normal",
            profile=contract_version,
        )
    if transport_type not in IMU_WINDOW_TRANSPORT_TYPES:
        raise RawPayloadValidationError(
            "IMU_WINDOW_TRANSPORT_REQUIRED",
            "IMU window v1 requires lowercase transport_type=lte or transport_type=wifi",
            profile=contract_version,
        )
    seq = imu_window_required_int(kv_payload, "seq", minimum=1, maximum=2**32 - 1)
    boot_count = imu_window_required_int(kv_payload, "boot-count", minimum=1, maximum=2**32 - 1)
    capture_cmd_id = imu_window_required_text(kv_payload, "capture-cmd-id")
    fw_version = imu_window_required_text(kv_payload, "fw-version")
    test_run_id = imu_window_required_text(kv_payload, "test-run-id")
    if not re.fullmatch(rf"[A-Za-z0-9._:-]{{1,{IMU_WINDOW_CAPTURE_CMD_ID_MAX}}}", capture_cmd_id) or not re.fullmatch(
        rf"[A-Za-z0-9._+:-]{{1,{IMU_WINDOW_FW_VERSION_MAX}}}", fw_version
    ) or not re.fullmatch(rf"[A-Za-z0-9._:-]{{1,{IMU_WINDOW_TEST_RUN_ID_MAX}}}", test_run_id):
        raise RawPayloadValidationError(
            "IMU_WINDOW_INVALID_ID",
            "IMU window lineage contains an invalid identifier",
            profile=contract_version,
        )
    window_id = imu_window_required_text(kv_payload, "window-id")
    expected_window_id = f"imuw-{capture_cmd_id}-b{boot_count}"
    if window_id != expected_window_id:
        raise RawPayloadValidationError(
            "IMU_WINDOW_ID_MISMATCH",
            "IMU window ID does not match capture command and boot count",
            profile=contract_version,
        )
    return {
        "contract_version": contract_version,
        "window_id": window_id,
        "capture_cmd_id": capture_cmd_id,
        "boot_count": boot_count,
        "seq": seq,
        "priority": priority,
        "transport_type": transport_type,
        "source": source,
        "source_status": source_status,
        "fw_version": fw_version,
        "test_run_id": test_run_id,
        "training_allowed": False,
        "activity_label": "unknown",
        "privacy_class": "engineering",
    }


def validate_imu_window_chunk(kv_payload: dict[str, str]) -> dict[str, Any]:
    result = validate_imu_window_common(kv_payload)
    chunk_index = imu_window_required_int(kv_payload, "chunk-index", maximum=IMU_WINDOW_CHUNK_COUNT - 1)
    chunk_count = imu_window_required_int(kv_payload, "chunk-count", minimum=1, maximum=32)
    sample_start_index = imu_window_required_int(
        kv_payload, "sample-start-index", maximum=IMU_WINDOW_SAMPLE_COUNT - 1
    )
    sample_count = imu_window_required_int(
        kv_payload, "sample-count", minimum=1, maximum=IMU_WINDOW_SAMPLES_PER_CHUNK
    )
    total_sample_count = imu_window_required_int(
        kv_payload, "total-sample-count", minimum=1, maximum=IMU_WINDOW_SAMPLE_COUNT
    )
    requested_interval_us = imu_window_required_int(
        kv_payload, "requested-interval-us", minimum=1, maximum=1_000_000
    )
    sample_record_bytes = imu_window_required_int(kv_payload, "sample-record-bytes", minimum=1, maximum=128)
    sample_encoding = imu_window_required_text(kv_payload, "sample-encoding")
    expected_start = chunk_index * IMU_WINDOW_SAMPLES_PER_CHUNK
    expected_count = min(IMU_WINDOW_SAMPLES_PER_CHUNK, IMU_WINDOW_SAMPLE_COUNT - expected_start)
    if (
        chunk_count != IMU_WINDOW_CHUNK_COUNT
        or total_sample_count != IMU_WINDOW_SAMPLE_COUNT
        or requested_interval_us != IMU_WINDOW_INTERVAL_US
        or sample_record_bytes != IMU_WINDOW_RECORD_BYTES
        or sample_encoding != IMU_WINDOW_SAMPLE_ENCODING
        or sample_start_index != expected_start
        or sample_count != expected_count
    ):
        raise RawPayloadValidationError(
            "IMU_WINDOW_CHUNK_SHAPE_MISMATCH",
            "IMU window chunk does not match the fixed v1 100x50ms layout",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )

    encoded = imu_window_required_text(kv_payload, "samples-b64")
    try:
        sample_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RawPayloadValidationError(
            "IMU_WINDOW_INVALID_BASE64",
            "IMU window samples_b64 is not strict Base64",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        ) from error
    if len(sample_bytes) != sample_count * IMU_WINDOW_RECORD_BYTES:
        raise RawPayloadValidationError(
            "IMU_WINDOW_SAMPLE_BYTES_MISMATCH",
            "decoded IMU sample bytes do not match sample_count * sample_record_bytes",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    declared_crc = normalize_crc32(imu_window_required_text(kv_payload, "chunk-crc32"))
    if declared_crc != crc32_hex(sample_bytes):
        raise RawPayloadValidationError(
            "IMU_WINDOW_CHUNK_CRC_MISMATCH",
            "decoded IMU sample bytes do not match chunk_crc32",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )

    offsets: list[int] = []
    for sample_index in range(sample_count):
        record = sample_bytes[
            sample_index * IMU_WINDOW_RECORD_BYTES : (sample_index + 1) * IMU_WINDOW_RECORD_BYTES
        ]
        offset_us = int.from_bytes(record[0:4], "little", signed=False)
        values = [int.from_bytes(record[pos : pos + 4], "little", signed=True) for pos in range(4, 28, 4)]
        if offsets and offset_us <= offsets[-1]:
            raise RawPayloadValidationError(
                "IMU_WINDOW_NON_MONOTONIC_OFFSET",
                "sample offsets must be strictly increasing within each chunk",
                profile=IMU_WINDOW_CONTRACT_VERSION,
            )
        if any(abs(value) > 5_000 for value in values[:3]) or any(abs(value) > 600_000 for value in values[3:]):
            raise RawPayloadValidationError(
                "IMU_WINDOW_SAMPLE_OUT_OF_RANGE",
                "sample value exceeds the declared QMI8658A engineering range",
                profile=IMU_WINDOW_CONTRACT_VERSION,
            )
        offsets.append(offset_us)

    result.update(
        {
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "sample_start_index": sample_start_index,
            "sample_count": sample_count,
            "total_sample_count": total_sample_count,
            "requested_interval_us": requested_interval_us,
            "sample_record_bytes": sample_record_bytes,
            "sample_encoding": sample_encoding,
            "chunk_crc32": declared_crc,
            "sample_payload_sha256": sha256_hex(sample_bytes),
            "first_offset_us": offsets[0],
            "last_offset_us": offsets[-1],
        }
    )
    return result


def validate_imu_window_manifest(kv_payload: dict[str, str]) -> dict[str, Any]:
    result = validate_imu_window_common(kv_payload)
    sample_count = imu_window_required_int(kv_payload, "sample-count", minimum=1, maximum=IMU_WINDOW_SAMPLE_COUNT)
    requested_interval_us = imu_window_required_int(
        kv_payload, "requested-interval-us", minimum=1, maximum=1_000_000
    )
    capture_start = imu_window_required_int(kv_payload, "capture-start-uptime-us")
    capture_end = imu_window_required_int(kv_payload, "capture-end-uptime-us")
    min_interval = imu_window_required_int(kv_payload, "min-interval-us", minimum=1, maximum=1_000_000)
    mean_interval = imu_window_required_int(kv_payload, "mean-interval-us", minimum=1, maximum=1_000_000)
    max_interval = imu_window_required_int(kv_payload, "max-interval-us", minimum=1, maximum=1_000_000)
    deadline_miss_count = imu_window_required_int(kv_payload, "deadline-miss-count", maximum=sample_count)
    read_failure_count = imu_window_required_int(kv_payload, "read-failure-count", maximum=sample_count)
    mock_sample_count = imu_window_required_int(kv_payload, "mock-sample-count", maximum=sample_count)
    warmup_sample_count = imu_window_required_int(
        kv_payload, "warmup-sample-count", maximum=IMU_WINDOW_WARMUP_SAMPLE_COUNT
    )
    warmup_interval_us = imu_window_required_int(
        kv_payload, "warmup-interval-us", minimum=1, maximum=1_000_000
    )
    chunk_count = imu_window_required_int(kv_payload, "chunk-count", minimum=1, maximum=32)
    uploaded_chunk_count = imu_window_required_int(kv_payload, "uploaded-chunk-count", maximum=32)
    samples_crc32 = normalize_crc32(imu_window_required_text(kv_payload, "samples-crc32"))
    training_allowed = parse_bool_or_text(kv_payload.get("training-allowed"))
    if (
        sample_count != IMU_WINDOW_SAMPLE_COUNT
        or requested_interval_us != IMU_WINDOW_INTERVAL_US
        or chunk_count != IMU_WINDOW_CHUNK_COUNT
        or uploaded_chunk_count != chunk_count
        or read_failure_count != 0
        or mock_sample_count != 0
        or warmup_sample_count != IMU_WINDOW_WARMUP_SAMPLE_COUNT
        or warmup_interval_us != IMU_WINDOW_WARMUP_INTERVAL_US
        or capture_end <= capture_start
        or not (min_interval <= mean_interval <= max_interval)
        or not re.fullmatch(r"[0-9A-F]{8}", str(samples_crc32 or ""))
        or training_allowed is not False
    ):
        raise RawPayloadValidationError(
            "IMU_WINDOW_MANIFEST_INCOMPLETE",
            "IMU window manifest is incomplete or violates the fixed v1 safety boundary",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    required_values = {
        "sensor_model": "QMI8658A",
        "activity_label": "unknown",
        "label_source": "none",
        "collection_authorization": "operator_command",
        "mounting_profile_id": "unrecorded",
        "axis_mapping_status": "unrecorded",
        "calibration_profile_id": "unrecorded",
    }
    for key, expected in required_values.items():
        if imu_window_required_text(kv_payload, key.replace("_", "-")) != expected:
            raise RawPayloadValidationError(
                "IMU_WINDOW_UNSAFE_METADATA",
                f"IMU window field {key} must remain {expected} in v1",
                profile=IMU_WINDOW_CONTRACT_VERSION,
            )
    sensor_i2c_address = imu_window_required_int(kv_payload, "sensor-i2c-address", maximum=127)
    if sensor_i2c_address != 106:
        raise RawPayloadValidationError(
            "IMU_WINDOW_SENSOR_IDENTITY_MISMATCH",
            "this verified connectivity-node profile requires QMI8658A at address 106 (0x6A)",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    result.update(
        {
            "sample_count": sample_count,
            "requested_interval_us": requested_interval_us,
            "capture_start_uptime_us": capture_start,
            "capture_end_uptime_us": capture_end,
            "min_interval_us": min_interval,
            "mean_interval_us": mean_interval,
            "max_interval_us": max_interval,
            "deadline_miss_count": deadline_miss_count,
            "read_failure_count": read_failure_count,
            "mock_sample_count": mock_sample_count,
            "warmup_sample_count": warmup_sample_count,
            "warmup_interval_us": warmup_interval_us,
            "chunk_count": chunk_count,
            "uploaded_chunk_count": uploaded_chunk_count,
            "samples_crc32": samples_crc32,
            "sensor_model": "QMI8658A",
            "sensor_i2c_address": sensor_i2c_address,
            "accel_unit": imu_window_required_text(kv_payload, "accel-unit"),
            "gyro_unit": imu_window_required_text(kv_payload, "gyro-unit"),
            "activity_label": "unknown",
            "label_source": "none",
            "collection_authorization": "operator_command",
            "training_allowed": False,
            "mounting_profile_id": "unrecorded",
            "axis_mapping_status": "unrecorded",
            "calibration_profile_id": "unrecorded",
        }
    )
    if result["accel_unit"] != "mg" or result["gyro_unit"] != "mdps":
        raise RawPayloadValidationError(
            "IMU_WINDOW_UNIT_MISMATCH",
            "IMU window v1 requires accel_unit=mg and gyro_unit=mdps",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    return result


def validated_imu_window_payload(event_type: str, kv_payload: dict[str, str]) -> dict[str, Any]:
    if event_type == "imu_window_chunk":
        return validate_imu_window_chunk(kv_payload)
    if event_type == "imu_window_manifest":
        return validate_imu_window_manifest(kv_payload)
    raise RawPayloadValidationError(
        "IMU_WINDOW_UNSUPPORTED_EVENT",
        f"unsupported IMU window event type: {event_type}",
        profile=IMU_WINDOW_CONTRACT_VERSION,
    )


def validate_imu_window_wire(
    event_type: str,
    kv_payload: dict[str, str],
    *,
    raw_body: bytes,
    frame_id: str,
    frame_seq: int | None,
) -> dict[str, Any]:
    if len(raw_body) > IMU_WINDOW_RAW_FRAME_MAX_BYTES:
        raise RawPayloadValidationError(
            "IMU_WINDOW_FRAME_TOO_LARGE",
            "IMU window raw frame exceeds the 1200-byte v1 ceiling",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    expected_keys = IMU_WINDOW_CHUNK_KEYS if event_type == "imu_window_chunk" else IMU_WINDOW_MANIFEST_KEYS
    if set(kv_payload) - expected_keys:
        raise RawPayloadValidationError(
            "IMU_WINDOW_UNKNOWN_FIELD",
            "IMU window payload contains a field outside the fixed v1 contract",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    if kv_payload.get("event-type") != event_type:
        raise RawPayloadValidationError(
            "IMU_WINDOW_EVENT_TYPE_MISMATCH",
            "IMU window event_type does not match the selected wire profile",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    metadata = validated_imu_window_payload(event_type, kv_payload)
    if frame_seq != metadata["seq"]:
        raise RawPayloadValidationError(
            "IMU_WINDOW_SEQUENCE_MISMATCH",
            "IMU window EGLK header seq does not match payload seq",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    if event_type == "imu_window_chunk":
        expected_frame_id = (
            f"imu-{metadata['capture_cmd_id']}-b{metadata['boot_count']}-c{metadata['chunk_index']:02d}"
        )
    else:
        expected_frame_id = f"imu-{metadata['capture_cmd_id']}-b{metadata['boot_count']}-manifest"
    if frame_id != expected_frame_id:
        raise RawPayloadValidationError(
            "IMU_WINDOW_FRAME_ID_MISMATCH",
            "IMU window frame ID does not match its command, boot, and part",
            profile=IMU_WINDOW_CONTRACT_VERSION,
        )
    return metadata


def raw_cell_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "rat": kv_payload.get("cell-rat"),
            "operator": kv_payload.get("cell-operator"),
            "mcc": kv_payload.get("cell-mcc"),
            "mnc": kv_payload.get("cell-mnc"),
            "tac": kv_payload.get("cell-tac"),
            "cell_id": kv_payload.get("cell-id"),
            "rssi": parse_raw_scalar(kv_payload.get("cell-rssi")),
            "rsrp": parse_raw_scalar(kv_payload.get("cell-rsrp")),
            "rsrq": parse_raw_scalar(kv_payload.get("cell-rsrq")),
            "sinr": parse_raw_scalar(kv_payload.get("cell-sinr")),
            "sim_state": kv_payload.get("cell-sim-state"),
            "registration_state": kv_payload.get("cell-registration-state"),
            "pdp_state": kv_payload.get("cell-pdp-state"),
            "reason_code": first_known(kv_payload.get("cell-reason-code"), kv_payload.get("lte-reason-code")),
        }
    )


def raw_lte_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "driver": first_known(kv_payload.get("lte-driver"), kv_payload.get("lte-http-driver")),
            "query_ok": parse_bool_or_text(kv_payload.get("lte-query-ok")),
            "uart_ready": parse_bool_or_text(kv_payload.get("lte-uart-ready")),
            "at_ok": parse_bool_or_text(kv_payload.get("lte-at-ok")),
            "sim_ready": parse_bool_or_text(kv_payload.get("lte-sim-ready")),
            "registered": parse_bool_or_text(kv_payload.get("lte-registered")),
            "attached": parse_bool_or_text(kv_payload.get("lte-attached")),
            "pdp_active": parse_bool_or_text(kv_payload.get("lte-pdp-active")),
            "ip_valid": parse_bool_or_text(kv_payload.get("lte-ip-valid")),
            "sim_state": kv_payload.get("lte-sim-state"),
            "registration_state": kv_payload.get("lte-registration-state"),
            "apn_state": kv_payload.get("lte-apn-state"),
            "pdp_state": kv_payload.get("lte-pdp-state"),
            "assigned_ip": kv_payload.get("lte-assigned-ip"),
            "reason_code": kv_payload.get("lte-reason-code"),
        }
    )


def raw_gnss_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "fix": parse_bool_or_text(kv_payload.get("gnss-fix")),
            "state": kv_payload.get("gnss-state"),
            "source": kv_payload.get("gnss-source"),
            "driver": kv_payload.get("gnss-driver"),
            "query_ok": parse_bool_or_text(kv_payload.get("gnss-query-ok")),
            "hdop": parse_raw_scalar(kv_payload.get("gnss-hdop")),
            "satellites": parse_raw_scalar(kv_payload.get("gnss-satellites")),
        }
    )


def raw_wifi_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("wifi-source"),
            "source_status": kv_payload.get("wifi-source-status"),
            "evidence_status": kv_payload.get("wifi-evidence-status"),
            "scan_enabled": parse_bool_or_text(kv_payload.get("wifi-scan-enabled")),
            "ap_count": parse_optional_int(kv_payload.get("wifi-ap-count")),
            "rssi": parse_raw_scalar(kv_payload.get("wifi-rssi")),
            "privacy": kv_payload.get("wifi-privacy"),
            "reason": kv_payload.get("wifi-reason"),
        }
    )


def raw_imu_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("imu-source"),
            "source_status": kv_payload.get("imu-source-status"),
            "evidence_status": kv_payload.get("imu-evidence-status"),
            "motion": kv_payload.get("imu-motion"),
            "confidence": parse_raw_scalar(kv_payload.get("imu-confidence")),
            "hardware_present": parse_bool_or_text(kv_payload.get("imu-hardware-present")),
            "driver_enabled": parse_bool_or_text(kv_payload.get("imu-driver-enabled")),
            "data_is_mock": parse_bool_or_text(kv_payload.get("imu-data-is-mock")),
            "backend_status": kv_payload.get("imu-backend-status"),
            "reason": kv_payload.get("imu-reason"),
        }
    )


def raw_power_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("power-source"),
            "source_status": kv_payload.get("power-source-status"),
            "evidence_status": kv_payload.get("power-evidence-status"),
            "battery_mv": parse_raw_scalar(kv_payload.get("power-battery-mv")),
            "soc_pct": parse_raw_scalar(kv_payload.get("power-soc-pct")),
            "charging": parse_bool_or_text(kv_payload.get("power-charging")),
            "battery_source": kv_payload.get("power-battery-source"),
            "charging_source": kv_payload.get("power-charging-source"),
            "state": kv_payload.get("power-state"),
            "marker_seq": parse_optional_int(kv_payload.get("power-marker-seq")),
            "reason": kv_payload.get("power-reason"),
        }
    )


def raw_reliability_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    network = compact_dict(
        {
            "mode": kv_payload.get("network-mode"),
            "rssi": parse_raw_scalar(kv_payload.get("network-rssi")),
            "reconnect_count": parse_optional_int(
                first_known(kv_payload.get("network-reconnect-count"), kv_payload.get("reconnect-count"))
            ),
            "last_error": first_known(kv_payload.get("network-last-error"), kv_payload.get("transport-last-error")),
            "last_reconnect_reason": kv_payload.get("network-last-reconnect-reason"),
            "state": kv_payload.get("network-state"),
            "raw_post_attempt_count": parse_optional_int(kv_payload.get("network-raw-post-attempt-count")),
            "raw_post_success_count": parse_optional_int(kv_payload.get("network-raw-post-success-count")),
            "raw_post_failure_count": parse_optional_int(kv_payload.get("network-raw-post-failure-count")),
        }
    )
    cache = compact_dict(
        {
            "queued_message_count": parse_optional_int(
                first_known(kv_payload.get("cache-queued-message-count"), kv_payload.get("queued-message-count"))
            ),
            "dropped_message_count": parse_optional_int(
                first_known(kv_payload.get("cache-dropped-message-count"), kv_payload.get("dropped-message-count"))
            ),
            "last_drop_reason": first_known(kv_payload.get("cache-last-drop-reason"), kv_payload.get("last-drop-reason")),
            "oldest_message_age_ms": parse_optional_int(kv_payload.get("cache-oldest-message-age-ms")),
            "state": kv_payload.get("cache-state"),
            "source_status": kv_payload.get("cache-source-status"),
            "retry_policy": kv_payload.get("cache-retry-policy"),
            "retry_attempt_count": parse_optional_int(kv_payload.get("cache-retry-attempt-count")),
            "retry_success_count": parse_optional_int(kv_payload.get("cache-retry-success-count")),
            "retry_failure_count": parse_optional_int(kv_payload.get("cache-retry-failure-count")),
            "flush_attempt_count": parse_optional_int(kv_payload.get("cache-flush-attempt-count")),
            "flush_success_count": parse_optional_int(kv_payload.get("cache-flush-success-count")),
            "flush_failure_count": parse_optional_int(kv_payload.get("cache-flush-failure-count")),
        }
    )
    return compact_dict({"network": network or None, "cache": cache or None})


def raw_location_belief_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    state = first_known(kv_payload.get("location-belief-state"), kv_payload.get("belief-state"))
    if state is None:
        return {}
    source_value = first_known(kv_payload.get("location-belief-source"), kv_payload.get("belief-source"))
    sources = [item.strip() for item in str(source_value or "").split(",") if item.strip()]
    return compact_dict(
        {
            "state": state,
            "radius_m": parse_raw_scalar(
                first_known(kv_payload.get("location-belief-radius-m"), kv_payload.get("belief-radius-m"))
            ),
            "confidence": parse_raw_scalar(
                first_known(kv_payload.get("location-belief-confidence"), kv_payload.get("belief-confidence"))
            ),
            "source": sources or None,
            "reason": first_known(kv_payload.get("location-belief-reason"), kv_payload.get("belief-reason")),
        }
    )


def derive_raw_frame_message(
    record: dict[str, Any],
    kv_payload: dict[str, str],
    *,
    expected_cmd_id: str | None = None,
) -> dict[str, Any]:
    framing = as_dict(record.get("framing"))
    frame_type = str(framing.get("frame_type") or "raw")
    seq = first_known(parse_optional_int(kv_payload.get("seq")), record.get("seq"), 0)
    common = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "device_id": record["device_id"],
        "fw_version": first_known(record.get("fw_version"), kv_payload.get("fw-version"), "unknown"),
        "seq": seq,
        "ts": first_known(kv_payload.get("ts"), f"raw_frame:{record['frame_id']}"),
        "boot_count": parse_optional_int(kv_payload.get("boot-count")),
        "test_run_id": record.get("test_run_id") or kv_payload.get("test-run-id"),
        "raw_frame": {
            "frame_id": record["frame_id"],
            "transport_profile": RAW_FRAME_PROFILE,
        },
    }
    if frame_type == "ack":
        cmd_id = first_known(expected_cmd_id, kv_payload.get("cmd-id"), kv_payload.get("cmd_id"), record["frame_id"])
        transport_type = kv_payload.get("transport-type")
        reliability = raw_reliability_from_kv(kv_payload)
        timer_state = raw_timer_state_from_kv(kv_payload)
        lte_http = compact_dict(
            {
                "phase": kv_payload.get("lte-http-phase"),
                "driver": kv_payload.get("lte-http-driver"),
                "poll_reason_code": kv_payload.get("lte-http-poll-reason-code"),
                "poll_status_code": parse_optional_int(kv_payload.get("lte-http-poll-status-code")),
                "poll_action_elapsed_ms": parse_optional_int(kv_payload.get("lte-http-poll-action-elapsed-ms")),
            }
        )
        command_obs = compact_dict(
            {
                "last_cmd_id": kv_payload.get("command-last-cmd-id"),
                "parse_status": kv_payload.get("command-parse-status"),
                "command_count": parse_optional_int(kv_payload.get("command-count")),
                "duplicate_local_execution_prevented": parse_bool_or_text(
                    kv_payload.get("duplicate-local-execution-prevented")
                ),
            }
        )
        return compact_dict(
            {
                **common,
                "message_type": "ack",
                "cmd_id": cmd_id,
                "status": first_known(kv_payload.get("status"), "ok"),
                "message": first_known(kv_payload.get("message"), "raw-frame ack"),
                "transport": compact_dict({"type": transport_type}) if transport_type else None,
                "lte_http": lte_http or None,
                "command": command_obs or None,
                "reliability": reliability or None,
                "timer_state": timer_state,
            }
        )
    if frame_type == "command":
        cmd_id = first_known(expected_cmd_id, kv_payload.get("cmd-id"), kv_payload.get("cmd_id"), record["frame_id"])
        return compact_dict(
            {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "message_type": "command",
                "device_id": record["device_id"],
                "cmd_id": cmd_id,
                "cmd": first_known(kv_payload.get("cmd"), "unknown"),
                "created_at": first_known(kv_payload.get("created-at"), kv_payload.get("created_at"), record["server_received_at"]),
                "test_run_id": record.get("test_run_id") or kv_payload.get("test-run-id"),
                "payload": raw_command_payload(kv_payload),
            }
        )
    if frame_type == "status":
        reliability = raw_reliability_from_kv(kv_payload)
        return compact_dict(
            {
                **common,
                "message_type": "status",
                "battery": parse_number_or_text(kv_payload.get("battery")),
                "link_type": first_known(kv_payload.get("link-type"), kv_payload.get("link_type"), "unknown"),
                "guard_mode": first_known(kv_payload.get("guard-mode"), kv_payload.get("guard_mode"), "unknown"),
                "queue_size": parse_optional_int(kv_payload.get("queue-size") or kv_payload.get("queue_size")) or 0,
                "reliability": reliability or None,
            }
        )
    if frame_type == "event":
        event_type = first_known(kv_payload.get("event-type"), kv_payload.get("event_type"), "raw_event")
        reliability = raw_reliability_from_kv(kv_payload)
        event = compact_dict(
            {
                **common,
                "message_type": "event",
                "event_type": event_type,
                "priority": first_known(kv_payload.get("priority"), "normal"),
                "source": kv_payload.get("source"),
                "source_status": kv_payload.get("source-status"),
                "reliability": reliability or None,
            }
        )
        if event_type in {"imu_window_chunk", "imu_window_manifest"}:
            imu_window = validated_imu_window_payload(event_type, kv_payload)
            event.update(
                compact_dict(
                    {
                        "capture_cmd_id": imu_window.get("capture_cmd_id"),
                        "imu_window": imu_window,
                        "transport": compact_dict({"type": kv_payload.get("transport-type")})
                        if kv_payload.get("transport-type")
                        else None,
                    }
                )
            )
        if event_type == "location_report":
            event.update(
                compact_dict(
                    {
                        "fix": parse_bool_or_text(kv_payload.get("fix")),
                        "gnss_state": kv_payload.get("gnss-state"),
                        "gnss_source": kv_payload.get("gnss-source"),
                        "gnss_driver": kv_payload.get("gnss-driver"),
                        "gnss_query_ok": parse_bool_or_text(kv_payload.get("gnss-query-ok")),
                        "lat": parse_raw_scalar(kv_payload.get("lat")),
                        "lon": parse_raw_scalar(kv_payload.get("lon")),
                        "altitude_m": parse_raw_scalar(kv_payload.get("altitude-m")),
                        "speed_mps": parse_raw_scalar(kv_payload.get("speed-mps")),
                        "course_deg": parse_raw_scalar(kv_payload.get("course-deg")),
                        "pdop": parse_raw_scalar(kv_payload.get("pdop")),
                        "hdop": parse_raw_scalar(kv_payload.get("hdop")),
                        "vdop": parse_raw_scalar(kv_payload.get("vdop")),
                        "satellites": parse_raw_scalar(kv_payload.get("satellites")),
                        "utc_date": kv_payload.get("utc-date"),
                        "utc_time": kv_payload.get("utc-time"),
                        "location_request_cmd_id": kv_payload.get("location-request-cmd-id"),
                        "transport": compact_dict({"type": kv_payload.get("transport-type")})
                        if kv_payload.get("transport-type")
                        else None,
                        "lte_http": compact_dict(
                            {
                                "phase": kv_payload.get("lte-http-phase"),
                                "driver": kv_payload.get("lte-http-driver"),
                            }
                        ),
                    }
                )
            )
        if event_type == "location_observation":
            cell = raw_cell_from_kv(kv_payload)
            lte = raw_lte_from_kv(kv_payload)
            gnss = raw_gnss_from_kv(kv_payload)
            wifi = raw_wifi_from_kv(kv_payload)
            imu = raw_imu_from_kv(kv_payload)
            power = raw_power_from_kv(kv_payload)
            location_belief = raw_location_belief_from_kv(kv_payload)
            event.update(
                compact_dict(
                    {
                        "location_request_cmd_id": kv_payload.get("location-request-cmd-id"),
                        "cell": cell or None,
                        "lte": lte or None,
                        "gnss": gnss or None,
                        "wifi": wifi or None,
                        "imu": imu or None,
                        "power": power or None,
                        "location_belief": location_belief or None,
                        "transport": compact_dict({"type": kv_payload.get("transport-type")})
                        if kv_payload.get("transport-type")
                        else None,
                        "lte_http": compact_dict(
                            {
                                "phase": kv_payload.get("lte-http-phase"),
                                "driver": kv_payload.get("lte-http-driver"),
                            }
                        ),
                    }
                )
            )
        return event
    if frame_type == "error":
        return compact_dict(
            {
                **common,
                "message_type": "error",
                "error_code": first_known(kv_payload.get("error-code"), kv_payload.get("error_code"), "RAW_FRAME_ERROR"),
                "severity": first_known(kv_payload.get("severity"), "warning"),
                "message": kv_payload.get("message"),
            }
        )
    return {}


def raw_timer_state_from_kv(kv_payload: dict[str, str]) -> dict[str, Any] | None:
    """Build a typed timer state only when at least one timer field is present.

    Invalid integer/boolean spellings are intentionally retained as strings so
    the command-aware validator rejects the ACK instead of silently coercing it.
    """

    keys = {
        "config_version": "timer-config-version",
        "enabled": "timer-enabled",
        "interval_seconds": "timer-interval-seconds",
        "session_expires_at_unix_ms": "timer-session-expires-at-unix-ms",
        "max_photos": "timer-max-photos",
        "captured_count": "timer-captured-count",
        "state_reason": "timer-state-reason",
        "trusted_utc": "timer-trusted-utc",
    }
    if not any(raw_key in kv_payload for raw_key in keys.values()):
        return None

    timer_state: dict[str, Any] = {}
    for field, raw_key in keys.items():
        if raw_key not in kv_payload:
            continue
        raw_value = kv_payload[raw_key]
        if field in {"enabled", "trusted_utc"}:
            timer_state[field] = parse_bool_or_text(raw_value)
        elif field in {
            "interval_seconds",
            "session_expires_at_unix_ms",
            "max_photos",
            "captured_count",
        }:
            text = str(raw_value).strip()
            timer_state[field] = (
                int(text, 10)
                if re.fullmatch(r"(?:0|[1-9][0-9]*)", text)
                else raw_value
            )
        else:
            timer_state[field] = raw_value
    return timer_state


def raw_command_payload(kv_payload: dict[str, str]) -> dict[str, Any]:
    reserved = {
        "cmd",
        "cmd-id",
        "cmd_id",
        "created-at",
        "created_at",
        "device-id",
        "device_id",
        "fw-version",
        "fw_version",
        "seq",
        "status",
        "test-run-id",
        "test_run_id",
        "ts",
    }
    return {key.replace("-", "_"): parse_number_or_text(value) for key, value in kv_payload.items() if key not in reserved}


def parse_number_or_text(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        return int(text, 10)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def parse_raw_scalar(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.lower() == "null":
        return None
    parsed_bool = parse_bool_or_text(text)
    if isinstance(parsed_bool, bool):
        return parsed_bool
    return parse_number_or_text(text)


def parse_bool_or_text(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return value


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def derived_endpoint(message_type: Any) -> str | None:
    return {
        "status": "heartbeat",
        "event": "telemetry",
        "ack": "ack",
        "error": "error",
    }.get(str(message_type or ""))


def redact_raw_frame_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(dumps(record))
    raw_payload = as_dict(redacted.get("raw_payload"))
    if "data" in raw_payload:
        raw_payload.pop("data", None)
        raw_payload["data_redacted"] = True
    retention = as_dict(redacted.get("retention"))
    retention["redacted"] = True
    redacted["retention"] = retention
    return redacted


def build_raw_frame(
    frame_type: str,
    frame_id: str,
    payload: bytes,
    *,
    seq: int | None = None,
    content_type: str = "text/x-egolink-kv",
    metadata: dict[str, Any] | None = None,
) -> bytes:
    header_parts = [
        "EGLK/1",
        f"type={frame_type}",
        f"id={frame_id}",
        f"len={len(payload)}",
        f"crc32={crc32_hex(payload)}",
    ]
    if seq is not None:
        header_parts.insert(3, f"seq={seq}")
    lines = [" ".join(header_parts), f"content-type={content_type}"]
    for key, value in (metadata or {}).items():
        if value not in (None, ""):
            lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n\n").encode("ascii") + payload


def build_raw_command_frame(device_id: str, command: dict[str, Any] | None) -> bytes:
    if not command:
        return build_raw_frame(
            "command",
            "cmd-none",
            b"cmd=none\n",
            metadata={"device-id": device_id},
        )
    payload_lines = [
        f"cmd={command['cmd']}",
        f"cmd_id={command['cmd_id']}",
    ]
    payload = as_dict(command.get("payload"))
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            encoded = str(value).lower() if isinstance(value, bool) else str(value)
            payload_lines.append(f"{key}={encoded}")
    if command.get("test_run_id"):
        payload_lines.append(f"test_run_id={command['test_run_id']}")
    if (
        type(command.get("expires_at_unix_ms")) is int
        and "expires_at_unix_ms" not in payload
    ):
        payload_lines.append(
            f"expires_at_unix_ms={command['expires_at_unix_ms']}"
        )
    return build_raw_frame(
        "command",
        str(command["cmd_id"]),
        ("\n".join(payload_lines) + "\n").encode("utf-8"),
        metadata={"device-id": device_id, "test-run-id": command.get("test_run_id")},
    )


def device_row(row: sqlite3.Row) -> dict[str, Any]:
    device = dict(row)
    for field in ("last_status_json", "latest_telemetry_json", "last_error_json"):
        if device.get(field):
            device[field.replace("_json", "")] = json.loads(str(device[field]))
        device.pop(field, None)
    return device


def command_row(row: sqlite3.Row) -> dict[str, Any]:
    command = json.loads(row["payload_json"])
    return command_with_status(command, row["status"], ack_json=row["ack_json"], updated_at=row["updated_at"])


def command_with_status(
    command: dict[str, Any],
    status: str,
    *,
    ack_json: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    enriched = dict(command)
    enriched["status"] = status
    if updated_at:
        enriched["updated_at"] = updated_at
    if ack_json:
        enriched["ack"] = json.loads(ack_json)
    return enriched


def dict_value(payload: dict[str, Any] | None, *path: str) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def first_known(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def normalize_location_state(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return {
        "fine": "Fine",
        "coarse": "Coarse",
        "predicted": "Predicted",
        "unknown": "Unknown",
    }.get(text)


def source_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value not in (None, ""):
        return [str(value)]
    return []


def merge_sources(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in source_list(value):
            if item not in merged:
                merged.append(item)
    return merged


def has_predictable_location_memory(memory: dict[str, Any]) -> bool:
    return memory.get("state") in {"Fine", "Coarse", "Predicted"}


def derived_gnss_radius_m(message: dict[str, Any]) -> float:
    gnss = as_dict(message.get("gnss"))
    hdop = as_number(first_known(message.get("hdop"), gnss.get("hdop")))
    if hdop and hdop > 0:
        return round(max(8.0, hdop * 10.0), 1)
    return 25.0


def location_position(message: dict[str, Any]) -> dict[str, Any]:
    lat = first_known(message.get("lat"), dict_value(message, "location", "lat"))
    lon = first_known(message.get("lon"), dict_value(message, "location", "lon"))
    if lat is None or lon is None:
        return {}
    return compact_dict(
        {
            "lat": lat,
            "lon": lon,
            "altitude_m": first_known(message.get("altitude_m"), dict_value(message, "location", "altitude_m")),
            "speed_mps": message.get("speed_mps"),
            "course_deg": message.get("course_deg"),
            "hdop": first_known(message.get("hdop"), dict_value(message, "gnss", "hdop")),
            "satellites": first_known(message.get("satellites"), dict_value(message, "gnss", "satellites")),
            "source_status": message.get("source_status"),
        }
    )


def location_evidence_summary(message: dict[str, Any], server_received_at: str) -> dict[str, Any]:
    gnss = as_dict(message.get("gnss"))
    cell = as_dict(message.get("cell"))
    lte = as_dict(message.get("lte"))
    transport = as_dict(message.get("transport"))
    lte_http = as_dict(message.get("lte_http"))
    return compact_dict(
        {
            "event_type": message.get("event_type"),
            "seq": message.get("seq"),
            "ts": message.get("ts"),
            "server_received_at": server_received_at,
            "test_run_id": message.get("test_run_id"),
            "source": message.get("source"),
            "source_status": message.get("source_status"),
            "fix": first_known(message.get("fix"), gnss.get("fix")),
            "gnss_state": first_known(message.get("gnss_state"), gnss.get("state"), gnss.get("result")),
            "gnss_query_ok": first_known(message.get("gnss_query_ok"), gnss.get("query_ok")),
            "cell_rat": cell.get("rat"),
            "cell_id": first_known(cell.get("cell_id"), cell.get("scell_id"), cell.get("scellid")),
            "cell_registration_state": cell.get("registration_state"),
            "lte_reason_code": first_known(lte.get("reason_code"), cell.get("reason_code")),
            "location_request_cmd_id": message.get("location_request_cmd_id"),
            "transport_type": transport.get("type"),
            "lte_http_phase": lte_http.get("phase"),
        }
    )


def build_location_memory(
    device_id: str,
    message: dict[str, Any],
    server_received_at: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_type = str(message.get("event_type") or "")
    if event_type not in {"location_report", "location_observation"}:
        return {}

    memory = dict(existing or {})
    memory["device_id"] = device_id
    memory["updated_at"] = server_received_at
    memory["last_test_run_id"] = first_known(message.get("test_run_id"), memory.get("last_test_run_id"))

    evidence = location_evidence_summary(message, server_received_at)
    position = location_position(message)
    gnss = as_dict(message.get("gnss"))
    payload = as_dict(message.get("payload"))
    belief = as_dict(first_known(message.get("location_belief"), payload.get("location_belief")))
    fix = first_known(message.get("fix"), gnss.get("fix"))

    if belief:
        state = normalize_location_state(belief.get("state")) or "Unknown"
        if state == "Unknown" and has_predictable_location_memory(memory):
            memory["updated_at"] = server_received_at
            memory["last_test_run_id"] = first_known(message.get("test_run_id"), memory.get("last_test_run_id"))
            memory["last_unknown_observation"] = evidence
            memory["last_evidence"] = evidence
            if fix is False:
                memory["last_no_fix"] = evidence
            return memory
        memory.update(
            compact_dict(
                {
                    "state": state,
                    "radius_m": belief.get("radius_m"),
                    "confidence": belief.get("confidence"),
                    "source": merge_sources(belief.get("source")),
                    "reason": first_known(belief.get("reason"), "location_observation_belief"),
                    "belief_updated_at": server_received_at,
                    "last_evidence": evidence,
                }
            )
        )
        if position:
            memory["last_known_location"] = {**position, "updated_at": server_received_at}
        if fix is False:
            memory["last_no_fix"] = evidence
        return memory

    if fix is True:
        source_status = str(message.get("source_status") or "unknown")
        confidence = 0.92 if source_status in {"verified", "observed", "pc_side_verified"} else 0.72
        memory.update(
            compact_dict(
                {
                    "state": "Fine",
                    "radius_m": derived_gnss_radius_m(message),
                    "confidence": confidence,
                    "source": merge_sources("gnss", message.get("source")),
                    "reason": "gnss_fix_calibration"
                    if source_status in {"verified", "observed", "pc_side_verified"}
                    else "gnss_fix_unverified",
                    "belief_updated_at": server_received_at,
                    "last_evidence": evidence,
                }
            )
        )
        if position:
            memory["last_known_location"] = {**position, "updated_at": server_received_at}
        return memory

    if fix is False:
        memory["last_no_fix"] = evidence
        memory.setdefault("state", "Unknown")
        memory.setdefault("radius_m", None)
        memory.setdefault("confidence", None)
        memory.setdefault("source", [])
        memory.setdefault("reason", "gnss_no_fix_no_location_memory")
        return memory

    if not memory:
        memory.update(
            {
                "state": "Unknown",
                "radius_m": None,
                "confidence": None,
                "source": [],
                "reason": "location_observation_without_belief",
                "last_evidence": evidence,
            }
        )
    return memory


def active_location_belief(
    field_message: dict[str, Any],
    field_payload: dict[str, Any],
    location_memory: dict[str, Any],
) -> dict[str, Any]:
    explicit = as_dict(first_known(field_message.get("location_belief"), field_payload.get("location_belief")))
    if explicit:
        state = normalize_location_state(explicit.get("state")) or first_known(explicit.get("state"), "unknown")
        if state == "Unknown" and has_predictable_location_memory(location_memory):
            confidence = as_number(location_memory.get("confidence"))
            return {
                "state": "Predicted",
                "radius_m": location_memory.get("radius_m"),
                "confidence": round(confidence * 0.75, 3) if confidence is not None else None,
                "source": merge_sources(location_memory.get("source"), "memory"),
                "reason": "last_known_after_unknown_location_observation",
                "updated_at": first_known(field_message.get("server_received_at"), location_memory.get("updated_at")),
            }
        return {
            "state": state,
            "radius_m": explicit.get("radius_m"),
            "confidence": explicit.get("confidence"),
            "source": source_list(explicit.get("source")),
            "reason": first_known(explicit.get("reason"), "location_observation_belief"),
            "updated_at": first_known(field_message.get("server_received_at"), explicit.get("updated_at")),
        }

    if not location_memory:
        return {
            "state": "unknown",
            "radius_m": None,
            "confidence": None,
            "source": [],
            "reason": "no_location_belief",
            "updated_at": field_message.get("server_received_at"),
        }

    gnss = as_dict(field_message.get("gnss"))
    fix = first_known(field_message.get("fix"), gnss.get("fix"))
    if fix is False and location_memory.get("state") in {"Fine", "Coarse", "Predicted"}:
        confidence = as_number(location_memory.get("confidence"))
        return {
            "state": "Predicted",
            "radius_m": location_memory.get("radius_m"),
            "confidence": round(confidence * 0.75, 3) if confidence is not None else None,
            "source": merge_sources(location_memory.get("source"), "memory"),
            "reason": "last_known_after_gnss_no_fix",
            "updated_at": first_known(field_message.get("server_received_at"), location_memory.get("updated_at")),
        }

    return {
        "state": first_known(location_memory.get("state"), "unknown"),
        "radius_m": location_memory.get("radius_m"),
        "confidence": location_memory.get("confidence"),
        "source": source_list(location_memory.get("source")),
        "reason": first_known(location_memory.get("reason"), "location_memory"),
        "updated_at": first_known(location_memory.get("belief_updated_at"), location_memory.get("updated_at")),
    }


def summarize_location_memory(messages: list[dict[str, Any]]) -> dict[str, Any]:
    memory: dict[str, Any] = {}
    for message in messages:
        if message.get("message_type") != "event":
            continue
        if message.get("event_type") not in {"location_report", "location_observation"}:
            continue
        memory = build_location_memory(
            str(message.get("device_id") or ""),
            message,
            str(message.get("server_received_at") or message.get("ts") or utc_now()),
            memory,
        )
    return memory


def parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_field_export_window(started_at: str, ended_at: str, max_records: int) -> tuple[str, str, int, int]:
    start_dt = parse_iso_timestamp(started_at)
    end_dt = parse_iso_timestamp(ended_at)
    if start_dt is None or end_dt is None:
        raise MessageHubError("invalid_time_window", "started_at and ended_at must be ISO-8601 timestamps")
    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)
    duration_s = int((end_utc - start_utc).total_seconds())
    if duration_s < 0:
        raise MessageHubError("invalid_time_window", "started_at must be before or equal to ended_at")
    if duration_s > FIELD_EXPORT_MAX_DURATION_S:
        raise MessageHubError("field_export_window_too_large", "field export window cannot exceed 48 hours")
    if max_records < 1 or max_records > FIELD_EXPORT_HARD_MAX_RECORDS:
        raise MessageHubError(
            "invalid_max_records",
            f"max_records must be between 1 and {FIELD_EXPORT_HARD_MAX_RECORDS}",
        )
    return start_utc.isoformat(), end_utc.isoformat(), duration_s, max_records


def elapsed_ms(start: Any, end: Any) -> int | None:
    start_dt = parse_iso_timestamp(start)
    end_dt = parse_iso_timestamp(end)
    if start_dt is None or end_dt is None:
        return None
    return int(max(0.0, (end_dt - start_dt).total_seconds()) * 1000)


def latest_message(messages: list[dict[str, Any]], *, message_type: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    for message in reversed(messages):
        if message_type and message.get("message_type") != message_type:
            continue
        if event_type and message.get("event_type") != event_type:
            continue
        return message
    return {}


def latest_location_message(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("message_type") != "event":
            continue
        if message.get("event_type") in {"location_observation", "location_report"}:
            return message
    return {}


def build_gnss_reason(fix: Any, state: Any, error_code: Any, latest_location: dict[str, Any]) -> str:
    if fix is True:
        return "GNSS_FIX"
    if error_code and "GNSS" in str(error_code):
        return str(error_code)
    if not latest_location:
        return "GNSS_NO_OBSERVATION"
    state_text = str(state or "unknown").strip().lower()
    if not state_text or state_text == "unknown":
        return "GNSS_UNKNOWN"
    return "GNSS_" + "".join(ch if ch.isalnum() else "_" for ch in state_text.upper()).strip("_")


def elapsed_seconds_since(value: Any) -> int | None:
    timestamp = parse_iso_timestamp(value)
    now = parse_iso_timestamp(utc_now())
    if timestamp is None or now is None:
        return None
    return int(max(0.0, (now - timestamp).total_seconds()))


def elapsed_seconds_between(start: Any, end: Any) -> int | None:
    start_dt = parse_iso_timestamp(start)
    end_dt = parse_iso_timestamp(end)
    if start_dt is None or end_dt is None:
        return None
    return int(max(0.0, (end_dt - start_dt).total_seconds()))


def d1_observed_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown"}
    return value not in (None, [], {})


def d1_component_seen(payload: dict[str, Any], keys: list[str]) -> bool:
    return any(d1_observed_value(payload.get(key)) for key in keys)


def d1_event_time(message: dict[str, Any]) -> Any:
    return first_known(message.get("server_received_at"), message.get("ts"))


def d1_history_chronological(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(reversed(messages))


def d1_raw_post_counters(message: dict[str, Any]) -> dict[str, int | None]:
    network = as_dict(as_dict(message.get("reliability")).get("network"))
    return {
        "attempt_count": parse_optional_int(first_known(network.get("raw_post_attempt_count"), message.get("network_raw_post_attempt_count"))),
        "success_count": parse_optional_int(first_known(network.get("raw_post_success_count"), message.get("network_raw_post_success_count"))),
        "failure_count": parse_optional_int(first_known(network.get("raw_post_failure_count"), message.get("network_raw_post_failure_count"))),
    }


def build_d1_uplink_metrics(messages: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = d1_history_chronological(messages)
    location_events = [
        message
        for message in ordered
        if message.get("message_type") == "event" and message.get("event_type") in D1_LOCATION_EVENT_TYPES
    ]
    latest_counters: dict[str, int | None] = {"attempt_count": None, "success_count": None, "failure_count": None}
    for message in ordered:
        counters = d1_raw_post_counters(message)
        if any(value is not None for value in counters.values()):
            latest_counters = counters
    attempts = latest_counters["attempt_count"]
    successes = latest_counters["success_count"]
    failures = latest_counters["failure_count"]
    success_rate = round(float(successes) / float(attempts), 3) if attempts and successes is not None else None
    first_upload_at = d1_event_time(location_events[0]) if location_events else None
    last_upload_at = d1_event_time(location_events[-1]) if location_events else None
    return {
        "basis": "device_raw_post_counters" if attempts is not None else "server_received_location_events",
        "location_event_count": len(location_events),
        "first_location_upload_at": first_upload_at,
        "last_location_upload_at": last_upload_at,
        "window_s": elapsed_seconds_between(first_upload_at, last_upload_at),
        "raw_post_attempt_count": attempts,
        "raw_post_success_count": successes,
        "raw_post_failure_count": failures,
        "raw_post_success_rate": success_rate,
        "server_received_success_count": len(location_events),
        "last_location_event_type": location_events[-1].get("event_type") if location_events else None,
    }


def d1_power_sample(message: dict[str, Any]) -> dict[str, Any] | None:
    power = as_dict(message.get("power"))
    battery_mv = first_known(power.get("battery_mv"), message.get("battery_mv"))
    soc_pct = first_known(power.get("soc_pct"), message.get("soc_pct"), message.get("battery_percent"), message.get("battery"))
    charging = first_known(power.get("charging"), message.get("charging"))
    if battery_mv is None and soc_pct is None and charging is None:
        return None
    return compact_dict(
        {
            "server_received_at": d1_event_time(message),
            "seq": message.get("seq"),
            "event_type": message.get("event_type"),
            "battery_mv": battery_mv,
            "soc_pct": soc_pct,
            "charging": charging,
            "source_status": power.get("source_status"),
            "evidence_status": power.get("evidence_status"),
            "state": power.get("state"),
        }
    )


def build_d1_power_curve(messages: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [sample for message in d1_history_chronological(messages) if (sample := d1_power_sample(message))]
    first_sample = samples[0] if samples else {}
    latest_sample = samples[-1] if samples else {}
    first_mv = as_number(first_sample.get("battery_mv"))
    latest_mv = as_number(latest_sample.get("battery_mv"))
    first_soc = as_number(first_sample.get("soc_pct"))
    latest_soc = as_number(latest_sample.get("soc_pct"))
    return {
        "sample_count": len(samples),
        "first_sample_at": first_sample.get("server_received_at"),
        "latest_sample_at": latest_sample.get("server_received_at"),
        "window_s": elapsed_seconds_between(first_sample.get("server_received_at"), latest_sample.get("server_received_at")),
        "latest": latest_sample or None,
        "delta_battery_mv": int(latest_mv - first_mv) if latest_mv is not None and first_mv is not None else None,
        "delta_soc_pct": round(latest_soc - first_soc, 3) if latest_soc is not None and first_soc is not None else None,
        "samples": samples[-8:],
        "battery_life_claim": "none",
    }


def d1_location_point(message: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    if message.get("message_type") != "event":
        return None
    if message.get("event_type") not in D1_LOCATION_EVENT_TYPES:
        return None
    position = location_position(message)
    lat = as_number(position.get("lat"))
    lon = as_number(position.get("lon"))
    if lat is None or lon is None or not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    fw_version = str(message.get("fw_version") or "unknown")
    fix = first_known(message.get("fix"), dict_value(message, "gnss", "fix"))
    amap_eligible = (
        message.get("event_type") == "location_report"
        and fix is True
        and fw_version in D1_AMAP_WGS84_FW_ALLOWLIST
    )
    if amap_eligible:
        coordinate_contract = "wgs84"
        coordinate_trust = "verified_parser_fw_allowlist"
        amap_exclusion_reason = None
    elif message.get("event_type") != "location_report":
        coordinate_contract = "unknown"
        coordinate_trust = "unverified"
        amap_exclusion_reason = "not_gnss_location_report"
    elif fix is not True:
        coordinate_contract = "unknown"
        coordinate_trust = "unverified"
        amap_exclusion_reason = "gnss_fix_not_true"
    else:
        coordinate_contract = "unknown"
        coordinate_trust = "pre_correction_or_unknown"
        amap_exclusion_reason = "firmware_parser_not_allowlisted"
    return compact_dict(
        {
            "lat": lat,
            "lon": lon,
            "server_received_at": d1_event_time(message),
            "seq": message.get("seq"),
            "event_type": message.get("event_type"),
            "source": source,
            "fix": fix,
            "fw_version": fw_version,
            "coordinate_contract": coordinate_contract,
            "coordinate_trust": coordinate_trust,
            "amap_eligible": amap_eligible,
            "amap_exclusion_reason": amap_exclusion_reason,
            "raw_frame_id": dict_value(message, "raw_frame", "frame_id"),
        }
    )


def d1_coordinate_missing_reason(message: dict[str, Any]) -> str:
    belief = as_dict(first_known(message.get("location_belief"), dict_value(message, "payload", "location_belief")))
    reason = first_known(belief.get("reason"), message.get("location_reason"))
    if reason:
        return str(reason)
    fix = first_known(message.get("fix"), dict_value(message, "gnss", "fix"))
    gnss_state = first_known(message.get("gnss_state"), dict_value(message, "gnss", "state"), dict_value(message, "gnss", "result"))
    if fix is False or str(gnss_state or "").strip().lower() in {"no_fix", "nofix", "no-fix"}:
        return "gnss_no_fix"
    if message.get("event_type") == "location_observation":
        return "observation_without_position_fix"
    return "coordinate_fields_missing"


def bounded_location_history_text(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:limit]


def bounded_location_history_seq(value: Any) -> int | None:
    if type(value) is not int:
        return None
    if value < 0 or value > SQLITE_SIGNED_INT64_MAX:
        return None
    return value


def location_history_record(row: Mapping[str, Any]) -> dict[str, Any]:
    if bool(row["payload_oversized"]):
        message = {}
        point = None
        trust_reason = "stored_payload_too_large"
    else:
        try:
            message = json.loads(str(row["payload_json"]))
            if not isinstance(message, dict):
                raise ValueError("location payload is not an object")
        except (TypeError, ValueError, json.JSONDecodeError):
            message = {}
            point = None
            trust_reason = "stored_payload_invalid"
        else:
            point = d1_location_point(message, source="location_history")
            candidate_reason = (
                "verified_wgs84_fix"
                if point and point.get("amap_eligible") is True
                else str(point.get("amap_exclusion_reason"))
                if point
                else d1_coordinate_missing_reason(message)
            )
            allowed_reasons = {
                "verified_wgs84_fix",
                "not_gnss_location_report",
                "gnss_fix_not_true",
                "firmware_parser_not_allowlisted",
                "gnss_no_fix",
                "observation_without_position_fix",
                "coordinate_fields_missing",
            }
            trust_reason = candidate_reason if candidate_reason in allowed_reasons else "coordinate_fields_missing"
    selectable = bool(point and point.get("amap_eligible") is True)
    fix_value = first_known(message.get("fix"), dict_value(message, "gnss", "fix"))
    boot_count_value = message.get("boot_count")
    if isinstance(boot_count_value, bool) or not isinstance(boot_count_value, int):
        boot_count_value = None
    record: dict[str, Any] = {
        "record_id": f"location-{int(row['id'])}",
        "event_type": str(row["event_type"] or "unknown"),
        "seq": bounded_location_history_seq(row["seq"]),
        "boot_count": boot_count_value,
        "device_ts": bounded_location_history_text(row["ts"], 64),
        "server_received_at": bounded_location_history_text(row["server_received_at"], 64),
        "fix": fix_value if isinstance(fix_value, bool) else None,
        "fw_version": bounded_location_history_text(message.get("fw_version") or "unknown", 96),
        "selectable": selectable,
        "coordinate_contract": point.get("coordinate_contract") if point else "unknown",
        "coordinate_trust": point.get("coordinate_trust") if point else "unverified",
        "trust_reason": trust_reason,
    }
    if selectable and point is not None:
        record["lat"] = point["lat"]
        record["lon"] = point["lon"]
    return record


def d1_coordinate_diagnostics(messages: list[dict[str, Any]], points: list[dict[str, Any]]) -> dict[str, Any]:
    location_events = [
        message
        for message in d1_history_chronological(messages)
        if message.get("message_type") == "event" and message.get("event_type") in D1_LOCATION_EVENT_TYPES
    ]
    coordinate_points = [
        point
        for point in points
        if point.get("source") in {"telemetry_history", "latest_location"}
    ]
    missing_events = [
        message
        for message in location_events
        if d1_location_point(message, source="diagnostics") is None
    ]
    latest_event = location_events[-1] if location_events else {}
    latest_missing = missing_events[-1] if missing_events else {}
    latest_coordinate = coordinate_points[-1] if coordinate_points else {}
    coordinate_event_count = len(coordinate_points)
    missing_count = max(0, len(location_events) - coordinate_event_count)
    if coordinate_event_count >= 2:
        operator_hint = "enough_coordinate_uploads_for_d1_map_gate"
    elif location_events:
        operator_hint = "move_outdoors_until_two_coordinate_uploads_are_seen"
    else:
        operator_hint = "wait_for_periodic_location_upload"
    return compact_dict(
        {
            "location_event_count": len(location_events),
            "coordinate_event_count": coordinate_event_count,
            "missing_coordinate_event_count": missing_count,
            "latest_event_type": latest_event.get("event_type"),
            "latest_event_seq": latest_event.get("seq"),
            "latest_coordinate_seq": latest_coordinate.get("seq"),
            "latest_missing_reason": d1_coordinate_missing_reason(latest_missing) if latest_missing else None,
            "latest_gnss_state": first_known(latest_event.get("gnss_state"), dict_value(latest_event, "gnss", "state")),
            "latest_fix": first_known(latest_event.get("fix"), dict_value(latest_event, "gnss", "fix")),
            "operator_hint": operator_hint,
        }
    )


def build_d1_map_surface(
    *,
    messages: list[dict[str, Any]],
    latest_location: dict[str, Any],
    location_memory: dict[str, Any],
    map_mode: str,
    map_lat: Any,
    map_lon: Any,
    coordinate_source: str | None,
    visible: bool,
) -> dict[str, Any]:
    points = [
        point
        for message in d1_history_chronological(messages)
        if (point := d1_location_point(message, source="telemetry_history")) is not None
    ]
    latest_point = d1_location_point(latest_location, source="latest_location") if latest_location else None
    if latest_point and not any(
        point.get("server_received_at") == latest_point.get("server_received_at")
        and point.get("seq") == latest_point.get("seq")
        for point in points
    ):
        points.append(latest_point)
    if latest_point and latest_point.get("amap_eligible") is True:
        for point in reversed(points):
            if (
                point.get("server_received_at") == latest_point.get("server_received_at")
                and point.get("seq") == latest_point.get("seq")
            ):
                point["amap_current"] = True
                break
    if not points and map_lat is not None and map_lon is not None:
        fallback_lat = as_number(map_lat)
        fallback_lon = as_number(map_lon)
        if fallback_lat is not None and fallback_lon is not None:
            points.append(
                compact_dict(
                    {
                        "lat": fallback_lat,
                        "lon": fallback_lon,
                        "server_received_at": first_known(
                            latest_location.get("server_received_at"),
                            dict_value(location_memory, "last_known_location", "updated_at"),
                            location_memory.get("updated_at"),
                        ),
                        "seq": latest_location.get("seq"),
                        "event_type": latest_location.get("event_type"),
                        "source": coordinate_source or "map_surface",
                        "fw_version": "unknown",
                        "coordinate_contract": "unknown",
                        "coordinate_trust": "unverified_location_memory",
                        "amap_eligible": False,
                        "amap_exclusion_reason": "location_memory_has_no_coordinate_provenance",
                    }
                )
            )
    trusted_points = [point for point in points if point.get("amap_eligible") is True]
    # A burst of newer untrusted coordinates must not evict the last verified
    # trajectory. When no trusted point exists, retain a bounded hidden window
    # so the dashboard can explain why location evidence is not drawable.
    visible_points = trusted_points[-24:] if trusted_points else points[-24:]
    amap_eligible_points = [point for point in visible_points if point.get("amap_eligible") is True]
    amap_eligible_point_count = len(amap_eligible_points)
    amap_hidden_point_count = len(points) - len(trusted_points)
    coordinate_diagnostics = d1_coordinate_diagnostics(messages, points)
    return {
        "visible": visible,
        "mode": map_mode,
        "review_mode": "local_no_key",
        "surface_role": "d2_d5_evidence_review",
        "lat": map_lat,
        "lon": map_lon,
        "coordinate_source": coordinate_source,
        "provider": {
            "mode": "none",
            "status": "not_configured",
            "blocking_d1": False,
            "next_step": "select_provider_key_privacy_before_tile_mode",
        },
        "layers": {
            "current_point": any(point.get("amap_current") is True for point in amap_eligible_points),
            "trajectory": amap_eligible_point_count >= 2,
            "reference_points": False,
            "provider_tiles": False,
        },
        "points": visible_points,
        "amap_eligible_point_count": amap_eligible_point_count,
        "amap_hidden_point_count": amap_hidden_point_count,
        "reference_points": [],
        "coordinate_diagnostics": coordinate_diagnostics,
        "privacy": {
            "coordinate_visibility": "authenticated_runtime_only",
            "static_report_policy": "bounded_summary_no_raw_coordinates",
            "training_allowed": False,
        },
        "accuracy_claim": "none",
        "trajectory": {
            "point_count": len(visible_points),
            "visible": len(visible_points) >= 2,
            "source": "recent_location_events",
            "non_claim": "trajectory_is_visual_evidence_not_accuracy",
        },
        "amap_trajectory": {
            "point_count": amap_eligible_point_count,
            "hidden_point_count": amap_hidden_point_count,
            "visible": amap_eligible_point_count >= 2,
            "source": "verified_parser_location_events",
        },
    }


def build_d1_field_readiness(
    status: str,
    upload_freshness: dict[str, Any],
    uplink_metrics: dict[str, Any],
) -> dict[str, Any]:
    freshness_value = as_number(upload_freshness.get("freshness_s"))
    freshness_s = int(freshness_value) if freshness_value is not None else None
    latest_upload_at = upload_freshness.get("last_location_upload_at")
    location_event_count = parse_optional_int(uplink_metrics.get("location_event_count")) or 0
    raw_successes = parse_optional_int(uplink_metrics.get("raw_post_success_count"))
    raw_failures = parse_optional_int(uplink_metrics.get("raw_post_failure_count"))
    raw_attempts = parse_optional_int(uplink_metrics.get("raw_post_attempt_count"))

    if raw_successes is None and raw_failures is None:
        raw_post_health = "unknown"
    elif raw_successes and not raw_failures:
        raw_post_health = "ok"
    elif raw_successes and raw_failures:
        raw_post_health = "warn"
    elif raw_attempts:
        raw_post_health = "fail"
    else:
        raw_post_health = "unknown"

    ready = False
    if latest_upload_at is None and location_event_count == 0:
        state = "waiting_for_data"
        reason = "no_periodic_location_upload"
        operator_action = "wait_for_new_dashboard_data"
    elif freshness_s is None:
        state = "waiting_for_data"
        reason = "freshness_unknown"
        operator_action = "wait_for_new_dashboard_data"
    elif freshness_s <= D1_FIELD_READY_FRESHNESS_S and status == "estimate_visible":
        state = "ready"
        reason = "fresh_periodic_upload"
        operator_action = "go_test"
        ready = True
    elif freshness_s <= D1_FIELD_READY_FRESHNESS_S:
        state = "waiting_for_data"
        reason = "fresh_upload_without_visible_estimate"
        operator_action = "wait_for_next_location_estimate"
    elif freshness_s <= D1_FIELD_STALE_FRESHNESS_S:
        state = "stale"
        reason = "periodic_upload_stale"
        operator_action = "wait_for_next_upload"
    else:
        state = "not_ready"
        reason = "periodic_upload_too_old"
        operator_action = "check_power_sim_lte_or_reboot"

    return {
        "state": state,
        "ready": ready,
        "reason": reason,
        "operator_action": operator_action,
        "normal_mode": "web_dashboard_preflight",
        "glance_check": "ready_when_web_shows_recent_d1_periodic_upload",
        "freshness_s": freshness_s,
        "freshness_threshold_s": D1_FIELD_READY_FRESHNESS_S,
        "stale_threshold_s": D1_FIELD_STALE_FRESHNESS_S,
        "latest_upload_at": latest_upload_at,
        "location_event_count": location_event_count,
        "raw_post_health": raw_post_health,
        "non_claims": ["location_accuracy_not_claimed", "battery_life_not_claimed"],
    }


def build_d1_acceptance_gate(
    *,
    status: str,
    field_readiness: dict[str, Any],
    location_estimate: dict[str, Any],
    map_surface: dict[str, Any],
    upload_freshness: dict[str, Any],
    uplink_metrics: dict[str, Any],
    power_curve: dict[str, Any],
    evidence: dict[str, Any],
    non_claims: list[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    required_track_points = 2
    points = as_list(map_surface.get("points"))
    trajectory = as_dict(map_surface.get("trajectory"))
    coordinate_diagnostics = as_dict(map_surface.get("coordinate_diagnostics"))
    track_points = parse_optional_int(trajectory.get("point_count")) or len(points)

    if status != "estimate_visible" or location_estimate.get("available") is not True:
        blockers.append("d1_location_estimate_missing")
    if field_readiness.get("ready") is not True:
        blockers.append(f"field_readiness_{field_readiness.get('reason') or 'not_ready'}")
    if map_surface.get("visible") is not True:
        blockers.append("d1_map_surface_not_visible")
    if track_points < required_track_points:
        blockers.append("d1_map_trajectory_needs_two_points")
    if not upload_freshness.get("last_location_upload_at"):
        blockers.append("d1_location_upload_freshness_missing")
    if (parse_optional_int(uplink_metrics.get("location_event_count")) or 0) <= 0:
        blockers.append("d1_location_upload_count_missing")
    if (parse_optional_int(uplink_metrics.get("raw_post_success_count")) or 0) <= 0:
        blockers.append("d1_raw_post_success_missing")
    if (parse_optional_int(power_curve.get("sample_count")) or 0) <= 0:
        blockers.append("d1_power_sample_count_missing")

    raw_failures = parse_optional_int(uplink_metrics.get("raw_post_failure_count")) or 0
    if raw_failures > 0:
        warnings.append("d1_raw_post_failures_seen")
    if (parse_optional_int(coordinate_diagnostics.get("missing_coordinate_event_count")) or 0) > 0:
        warnings.append("d1_location_events_without_coordinate")

    components = as_dict(evidence.get("components"))
    for component in ("gnss", "cell_lte", "imu", "power"):
        if as_dict(components.get(component)).get("seen") is not True:
            blockers.append(f"d1_{component}_evidence_missing")

    required_non_claims = {"location_accuracy_not_claimed", "battery_life_not_claimed"}
    missing_non_claims = sorted(required_non_claims.difference(set(non_claims)))
    for claim in missing_non_claims:
        blockers.append(f"{claim}_missing")

    if "d1_map_trajectory_needs_two_points" in blockers:
        next_action = str(coordinate_diagnostics.get("operator_hint") or "collect_at_least_two_coordinate_uploads_outdoors")
    elif any(item.startswith("field_readiness_") for item in blockers):
        next_action = "wait_for_fresh_periodic_upload_or_check_power_sim_lte"
    elif blockers:
        next_action = "fix_blockers_before_d1_field_acceptance"
    else:
        next_action = "run_d1_field_kit_and_postrun_collector"

    gate_status = "ready" if not blockers else "blocked"
    return {
        "status": gate_status,
        "headline": "Ready for D1 field acceptance run" if gate_status == "ready" else "Blocked for D1 acceptance",
        "track_points": track_points,
        "required_track_points": required_track_points,
        "blockers": unique_text(blockers),
        "warnings": unique_text(warnings),
        "next_action": next_action,
        "coordinate_diagnostics": coordinate_diagnostics,
        "scope": "D1 acceptance preflight and post-run review only",
        "non_claims": ["location_accuracy_not_claimed", "battery_life_not_claimed"],
    }


def build_d1_link_summary(device: dict[str, Any], messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    messages = messages or []
    latest_location = as_dict(device.get("latest_location"))
    location_memory = as_dict(device.get("location_memory"))
    observability = as_dict(device.get("observability"))
    belief = as_dict(observability.get("location_belief"))
    gnss = as_dict(observability.get("gnss"))
    cell = as_dict(observability.get("cell"))
    lte = as_dict(observability.get("lte"))
    imu = as_dict(observability.get("imu"))
    power = as_dict(observability.get("power"))
    transport = as_dict(observability.get("transport"))

    location_lat = first_known(latest_location.get("lat"), dict_value(latest_location, "location", "lat"))
    location_lon = first_known(latest_location.get("lon"), dict_value(latest_location, "location", "lon"))
    memory_lat = dict_value(location_memory, "last_known_location", "lat")
    memory_lon = dict_value(location_memory, "last_known_location", "lon")
    map_lat = first_known(location_lat, memory_lat)
    map_lon = first_known(location_lon, memory_lon)
    has_coordinate = map_lat is not None and map_lon is not None

    state = first_known(belief.get("state"), "unknown")
    estimate_available = bool(latest_location) or str(state).strip().lower() not in {"", "unknown"}
    if has_coordinate and location_lat is not None and location_lon is not None:
        map_mode = "coordinate"
    elif has_coordinate:
        map_mode = "memory_coordinate"
    elif estimate_available:
        map_mode = "estimate_without_coordinate"
    else:
        map_mode = "waiting_for_location_upload"
    if location_lat is not None and location_lon is not None:
        coordinate_source = "latest_location"
    elif has_coordinate:
        coordinate_source = "location_memory"
    else:
        coordinate_source = None

    last_location_upload_at = latest_location.get("server_received_at")
    last_device_upload_at = device.get("last_seen_at")
    freshness_anchor = first_known(last_location_upload_at, belief.get("updated_at"), last_device_upload_at)
    status = "estimate_visible" if estimate_available else "waiting_for_location_upload"
    upload_freshness = {
        "last_location_upload_at": last_location_upload_at,
        "last_device_upload_at": last_device_upload_at,
        "freshness_s": elapsed_seconds_since(freshness_anchor),
        "last_location_event_type": latest_location.get("event_type"),
        "last_seq": first_known(latest_location.get("seq"), device.get("last_seq")),
    }
    uplink_metrics = build_d1_uplink_metrics(messages)
    power_curve = build_d1_power_curve(messages)
    cell_lte_seen = d1_component_seen(
        cell,
        ["rat", "operator", "mcc", "mnc", "tac", "cell_id", "rsrp", "rsrq", "rssi", "sinr", "registration_state", "pdp_state"],
    ) or d1_component_seen(
        lte,
        ["registered", "attached", "pdp_active", "assigned_ip", "registration_state", "pdp_state", "reason_code"],
    )
    field_readiness = build_d1_field_readiness(status, upload_freshness, uplink_metrics)
    location_estimate = {
        "available": estimate_available,
        "state": state,
        "radius_m": belief.get("radius_m"),
        "confidence": belief.get("confidence"),
        "source": belief.get("source") if isinstance(belief.get("source"), list) else [],
        "reason": first_known(belief.get("reason"), "no_location_estimate"),
        "updated_at": first_known(belief.get("updated_at"), last_location_upload_at),
        "accuracy_claim": "none",
    }
    map_surface = build_d1_map_surface(
        messages=messages,
        latest_location=latest_location,
        location_memory=location_memory,
        map_mode=map_mode,
        map_lat=map_lat,
        map_lon=map_lon,
        coordinate_source=coordinate_source,
        visible=estimate_available or has_coordinate,
    )
    evidence = {
        "transport_type": first_known(transport.get("type"), "unknown"),
        "components": {
            "gnss": {
                "seen": bool(latest_location),
                "fix": first_known(latest_location.get("fix"), gnss.get("fix")),
                "state": first_known(latest_location.get("gnss_state"), gnss.get("state"), "unknown"),
                "reason_code": gnss.get("reason_code"),
            },
            "cell_lte": {
                "seen": cell_lte_seen,
                "cell_id": cell.get("cell_id"),
                "rat": cell.get("rat"),
                "registration_state": first_known(cell.get("registration_state"), lte.get("registration_state")),
                "pdp_state": first_known(cell.get("pdp_state"), lte.get("pdp_state")),
            },
            "imu": {
                "seen": d1_component_seen(imu, ["motion", "confidence", "hardware_present", "driver_enabled", "data_is_mock", "backend_status", "source_status", "evidence_status"]),
                "motion": imu.get("motion"),
                "confidence": imu.get("confidence"),
                "evidence_status": imu.get("evidence_status"),
            },
            "power": {
                "seen": d1_component_seen(power, ["battery_mv", "soc_pct", "charging", "state", "marker_seq", "source_status", "evidence_status"]),
                "battery_mv": power.get("battery_mv"),
                "soc_pct": power.get("soc_pct"),
                "evidence_status": power.get("evidence_status"),
            },
        },
    }
    non_claims = ["location_accuracy_not_claimed", "battery_life_not_claimed"]

    return {
        "demo": "D1",
        "status": status,
        "field_readiness": field_readiness,
        "acceptance_gate": build_d1_acceptance_gate(
            status=status,
            field_readiness=field_readiness,
            location_estimate=location_estimate,
            map_surface=map_surface,
            upload_freshness=upload_freshness,
            uplink_metrics=uplink_metrics,
            power_curve=power_curve,
            evidence=evidence,
            non_claims=non_claims,
        ),
        "location_estimate": location_estimate,
        "map_surface": map_surface,
        "upload_freshness": upload_freshness,
        "uplink_metrics": uplink_metrics,
        "power_curve": power_curve,
        "evidence": evidence,
        "non_claims": non_claims,
    }


def build_observability(device: dict[str, Any], latest_command: dict[str, Any] | None = None) -> dict[str, Any]:
    status = as_dict(device.get("last_status"))
    telemetry = as_dict(device.get("latest_telemetry"))
    latest_location = as_dict(device.get("latest_location"))
    latest_location_observation = as_dict(device.get("latest_location_observation"))
    location_memory = as_dict(device.get("location_memory"))
    field_message = latest_location if latest_location else telemetry
    error = as_dict(device.get("last_error"))
    latest_command = as_dict(latest_command)

    status_payload = as_dict(status.get("payload"))
    telemetry_payload = as_dict(telemetry.get("payload"))
    field_payload = as_dict(field_message.get("payload"))
    transport = as_dict(first_known(status.get("transport"), telemetry.get("transport"), field_message.get("transport")))
    runtime = as_dict(first_known(status.get("runtime"), telemetry.get("runtime")))
    power = as_dict(first_known(field_message.get("power"), telemetry.get("power"), status.get("power")))
    gnss = as_dict(first_known(field_message.get("gnss"), field_payload.get("gnss"), telemetry_payload.get("gnss")))
    cell = as_dict(first_known(field_message.get("cell"), telemetry.get("cell"), status.get("cell")))
    lte = as_dict(first_known(field_message.get("lte"), telemetry.get("lte"), status.get("lte")))
    wifi = as_dict(first_known(field_message.get("wifi"), telemetry.get("wifi"), status.get("wifi")))
    imu = as_dict(first_known(field_message.get("imu"), telemetry.get("imu"), status.get("imu")))
    location_belief = active_location_belief(field_message, field_payload, location_memory)
    ack = as_dict(latest_command.get("ack"))
    field_reliability = as_dict(field_message.get("reliability"))
    telemetry_reliability = as_dict(telemetry.get("reliability"))
    status_reliability = as_dict(status.get("reliability"))
    ack_reliability = as_dict(ack.get("reliability"))
    reliability_network = as_dict(
        first_known(
            field_reliability.get("network"),
            telemetry_reliability.get("network"),
            status_reliability.get("network"),
            ack_reliability.get("network"),
            field_message.get("network"),
            telemetry.get("network"),
            status.get("network"),
            ack.get("network"),
        )
    )
    reliability_cache = as_dict(
        first_known(
            field_reliability.get("cache"),
            telemetry_reliability.get("cache"),
            status_reliability.get("cache"),
            ack_reliability.get("cache"),
            field_message.get("cache"),
            telemetry.get("cache"),
            status.get("cache"),
            ack.get("cache"),
        )
    )

    boot_count = first_known(status.get("boot_count"), telemetry.get("boot_count"), runtime.get("boot_count"))
    boot_id = first_known(status.get("boot_id"), telemetry.get("boot_id"), runtime.get("boot_id"))
    if boot_id is None and boot_count is not None:
        boot_id = f"boot_count:{boot_count}"

    boot_uptime_ms = first_known(status.get("boot_uptime_ms"), telemetry.get("boot_uptime_ms"), runtime.get("boot_uptime_ms"))
    uptime_s = first_known(
        status.get("uptime_s"),
        status.get("uptime_sec"),
        status_payload.get("uptime_sec"),
        runtime.get("uptime_s"),
        (boot_uptime_ms / 1000.0) if isinstance(boot_uptime_ms, (int, float)) else None,
    )

    command_rtt_ms = first_known(
        latest_command.get("rtt_ms"),
        elapsed_ms(latest_command.get("created_at"), ack.get("server_received_at") or latest_command.get("updated_at")),
    )

    fix = first_known(field_message.get("fix"), gnss.get("fix"))
    gnss_state = first_known(field_message.get("gnss_state"), gnss.get("state"), gnss.get("result"))
    error_code = error.get("error_code")
    gnss_reason = build_gnss_reason(fix, gnss_state, error_code, latest_location)

    transport_last_error = first_known(transport.get("last_error"), status.get("transport_last_error"), error_code)
    lte_reason = first_known(lte.get("reason_code"), cell.get("reason_code"))
    reliability = compact_dict(
        {
            "network": compact_dict(
                {
                    "mode": first_known(
                        reliability_network.get("mode"),
                        status.get("network_mode"),
                        telemetry.get("network_mode"),
                    ),
                    "rssi": first_known(reliability_network.get("rssi"), status.get("network_rssi"), telemetry.get("network_rssi")),
                    "reconnect_count": first_known(
                        reliability_network.get("reconnect_count"),
                        status.get("network_reconnect_count"),
                        telemetry.get("network_reconnect_count"),
                        ack.get("network_reconnect_count"),
                        status.get("reconnect_count"),
                        telemetry.get("reconnect_count"),
                    ),
                    "last_error": first_known(
                        reliability_network.get("last_error"),
                        status.get("network_last_error"),
                        telemetry.get("network_last_error"),
                        ack.get("network_last_error"),
                    ),
                    "last_reconnect_reason": first_known(
                        reliability_network.get("last_reconnect_reason"),
                        status.get("network_last_reconnect_reason"),
                        telemetry.get("network_last_reconnect_reason"),
                    ),
                    "state": reliability_network.get("state"),
                    "raw_post_attempt_count": first_known(
                        reliability_network.get("raw_post_attempt_count"),
                        status.get("network_raw_post_attempt_count"),
                        telemetry.get("network_raw_post_attempt_count"),
                        ack.get("network_raw_post_attempt_count"),
                    ),
                    "raw_post_success_count": first_known(
                        reliability_network.get("raw_post_success_count"),
                        status.get("network_raw_post_success_count"),
                        telemetry.get("network_raw_post_success_count"),
                        ack.get("network_raw_post_success_count"),
                    ),
                    "raw_post_failure_count": first_known(
                        reliability_network.get("raw_post_failure_count"),
                        status.get("network_raw_post_failure_count"),
                        telemetry.get("network_raw_post_failure_count"),
                        ack.get("network_raw_post_failure_count"),
                    ),
                }
            )
            or None,
            "cache": compact_dict(
                {
                    "queued_message_count": first_known(
                        reliability_cache.get("queued_message_count"),
                        status.get("cache_queued_message_count"),
                        telemetry.get("cache_queued_message_count"),
                        ack.get("cache_queued_message_count"),
                        status.get("queued_message_count"),
                        telemetry.get("queued_message_count"),
                    ),
                    "dropped_message_count": first_known(
                        reliability_cache.get("dropped_message_count"),
                        status.get("cache_dropped_message_count"),
                        telemetry.get("cache_dropped_message_count"),
                        ack.get("cache_dropped_message_count"),
                        status.get("dropped_message_count"),
                        telemetry.get("dropped_message_count"),
                    ),
                    "last_drop_reason": first_known(
                        reliability_cache.get("last_drop_reason"),
                        status.get("cache_last_drop_reason"),
                        telemetry.get("cache_last_drop_reason"),
                    ),
                    "oldest_message_age_ms": first_known(
                        reliability_cache.get("oldest_message_age_ms"),
                        status.get("cache_oldest_message_age_ms"),
                        telemetry.get("cache_oldest_message_age_ms"),
                    ),
                    "state": reliability_cache.get("state"),
                    "source_status": reliability_cache.get("source_status"),
                    "retry_policy": first_known(
                        reliability_cache.get("retry_policy"),
                        status.get("cache_retry_policy"),
                        telemetry.get("cache_retry_policy"),
                        ack.get("cache_retry_policy"),
                    ),
                    "retry_attempt_count": first_known(
                        reliability_cache.get("retry_attempt_count"),
                        status.get("cache_retry_attempt_count"),
                        telemetry.get("cache_retry_attempt_count"),
                        ack.get("cache_retry_attempt_count"),
                    ),
                    "retry_success_count": first_known(
                        reliability_cache.get("retry_success_count"),
                        status.get("cache_retry_success_count"),
                        telemetry.get("cache_retry_success_count"),
                        ack.get("cache_retry_success_count"),
                    ),
                    "retry_failure_count": first_known(
                        reliability_cache.get("retry_failure_count"),
                        status.get("cache_retry_failure_count"),
                        telemetry.get("cache_retry_failure_count"),
                        ack.get("cache_retry_failure_count"),
                    ),
                    "flush_attempt_count": first_known(
                        reliability_cache.get("flush_attempt_count"),
                        status.get("cache_flush_attempt_count"),
                        telemetry.get("cache_flush_attempt_count"),
                        ack.get("cache_flush_attempt_count"),
                    ),
                    "flush_success_count": first_known(
                        reliability_cache.get("flush_success_count"),
                        status.get("cache_flush_success_count"),
                        telemetry.get("cache_flush_success_count"),
                        ack.get("cache_flush_success_count"),
                    ),
                    "flush_failure_count": first_known(
                        reliability_cache.get("flush_failure_count"),
                        status.get("cache_flush_failure_count"),
                        telemetry.get("cache_flush_failure_count"),
                        ack.get("cache_flush_failure_count"),
                    ),
                }
            )
            or None,
        }
    )
    reason_codes: list[str] = []
    reliability_network_error = dict_value(reliability, "network", "last_error")
    for candidate in (error_code, transport_last_error, reliability_network_error, gnss_reason, lte_reason):
        if candidate and candidate not in {"none", "unknown", "GNSS_FIX", "LTE_READY"} and candidate not in reason_codes:
            reason_codes.append(str(candidate))

    return {
        "message": {
            "seq": device.get("last_seq"),
            "last_seen_at": device.get("last_seen_at"),
            "last_message_type": device.get("last_message_type"),
            "fw_version": device.get("fw_version") or "unknown",
        },
        "transport": {
            "type": first_known(transport.get("type"), status.get("transport_type"), telemetry.get("transport_type"), status.get("link_type"), "unknown"),
            "rtt_ms": first_known(transport.get("rtt_ms"), status.get("transport_rtt_ms"), telemetry.get("transport_rtt_ms")),
            "last_error": transport_last_error,
        },
        "runtime": {
            "boot_id": boot_id or "unknown",
            "uptime_s": uptime_s,
            "free_heap": first_known(runtime.get("free_heap"), status.get("free_heap"), status_payload.get("free_heap"), telemetry.get("free_heap")),
            "last_reset_reason": first_known(runtime.get("last_reset_reason"), status.get("reset_reason"), telemetry.get("reset_reason"), "unknown"),
            "watchdog_count": first_known(runtime.get("watchdog_count"), status.get("watchdog_count"), telemetry.get("watchdog_count")),
        },
        "command": {
            "last_cmd_id": latest_command.get("cmd_id"),
            "last_cmd": latest_command.get("cmd"),
            "last_status": latest_command.get("status"),
            "last_ack_status": ack.get("status"),
            "rtt_ms": command_rtt_ms,
        },
        "reliability": reliability,
        "power": {
            "battery_mv": first_known(power.get("battery_mv"), status.get("battery_mv"), status_payload.get("battery_mv")),
            "soc_pct": first_known(power.get("soc_pct"), status.get("soc_pct"), status.get("battery_percent"), status.get("battery")),
            "charging": first_known(power.get("charging"), status.get("charging")),
            "source": first_known(power.get("source"), status.get("battery_source"), "unknown"),
            "source_status": first_known(power.get("source_status"), "unknown"),
            "evidence_status": first_known(power.get("evidence_status"), "unknown"),
            "state": power.get("state"),
            "marker_seq": power.get("marker_seq"),
            "reason": power.get("reason"),
        },
        "gnss": {
            "fix": fix,
            "state": first_known(gnss_state, "unknown"),
            "hdop": first_known(field_message.get("hdop"), gnss.get("hdop")),
            "satellites": first_known(field_message.get("satellites"), gnss.get("satellites"), gnss.get("no_sv")),
            "attempt_ms": first_known(field_message.get("attempt_ms"), field_message.get("gnss_attempt_ms"), gnss.get("attempt_ms")),
            "result": first_known(gnss.get("result"), gnss_state, "unknown"),
            "reason_code": gnss_reason,
        },
        "cell": {
            "rat": first_known(cell.get("rat"), cell.get("system_mode"), cell.get("mode")),
            "operator": cell.get("operator"),
            "mcc": cell.get("mcc"),
            "mnc": cell.get("mnc"),
            "tac": cell.get("tac"),
            "cell_id": first_known(cell.get("cell_id"), cell.get("scell_id"), cell.get("scellid")),
            "rsrp": cell.get("rsrp"),
            "rsrq": cell.get("rsrq"),
            "rssi": first_known(cell.get("rssi"), status.get("rssi"), telemetry.get("rssi")),
            "sinr": first_known(cell.get("sinr"), cell.get("rssnr")),
            "sim_state": first_known(cell.get("sim_state"), lte.get("sim_state")),
            "registration_state": first_known(cell.get("registration_state"), lte.get("registration_state")),
            "pdp_state": first_known(cell.get("pdp_state"), lte.get("pdp_state")),
            "reason_code": lte_reason,
        },
        "lte": {
            "driver": first_known(lte.get("driver"), "unknown"),
            "query_ok": lte.get("query_ok"),
            "uart_ready": lte.get("uart_ready"),
            "at_ok": lte.get("at_ok"),
            "sim_ready": lte.get("sim_ready"),
            "registered": lte.get("registered"),
            "attached": lte.get("attached"),
            "pdp_active": lte.get("pdp_active"),
            "ip_valid": lte.get("ip_valid"),
            "sim_state": first_known(lte.get("sim_state"), cell.get("sim_state"), "unknown"),
            "registration_state": first_known(lte.get("registration_state"), cell.get("registration_state"), "unknown"),
            "apn_state": first_known(lte.get("apn_state"), "unknown"),
            "pdp_state": first_known(lte.get("pdp_state"), cell.get("pdp_state"), "unknown"),
            "assigned_ip": first_known(lte.get("assigned_ip"), "unknown"),
            "reason_code": first_known(lte_reason, "unknown"),
        },
        "wifi": {
            "scan_enabled": first_known(wifi.get("scan_enabled"), False if wifi.get("aps") == [] else None),
            "ap_count": first_known(
                wifi.get("ap_count"),
                len(wifi.get("aps")) if isinstance(wifi.get("aps"), list) else None,
            ),
            "source_status": first_known(wifi.get("source_status"), "unknown"),
            "evidence_status": first_known(wifi.get("evidence_status"), "unknown"),
            "privacy": wifi.get("privacy"),
            "reason": wifi.get("reason"),
        },
        "imu": {
            "motion": first_known(imu.get("motion"), imu.get("state")),
            "confidence": imu.get("confidence"),
            "source_status": first_known(imu.get("source_status"), "unknown"),
            "evidence_status": first_known(imu.get("evidence_status"), "unknown"),
            "hardware_present": imu.get("hardware_present"),
            "driver_enabled": imu.get("driver_enabled"),
            "data_is_mock": imu.get("data_is_mock"),
            "backend_status": imu.get("backend_status"),
            "reason": imu.get("reason"),
        },
        "location_belief": {
            "state": first_known(location_belief.get("state"), "unknown"),
            "radius_m": location_belief.get("radius_m"),
            "confidence": location_belief.get("confidence"),
            "source": location_belief.get("source") if isinstance(location_belief.get("source"), list) else [],
            "reason": first_known(location_belief.get("reason"), "no_location_belief"),
            "updated_at": first_known(
                location_belief.get("updated_at"),
                field_message.get("server_received_at"),
                latest_location_observation.get("server_received_at"),
            ),
        },
        "location_memory": {
            "state": first_known(location_memory.get("state"), "unknown"),
            "radius_m": location_memory.get("radius_m"),
            "confidence": location_memory.get("confidence"),
            "source": location_memory.get("source") if isinstance(location_memory.get("source"), list) else [],
            "reason": first_known(location_memory.get("reason"), "no_location_memory"),
            "updated_at": location_memory.get("updated_at"),
            "belief_updated_at": location_memory.get("belief_updated_at"),
            "last_test_run_id": location_memory.get("last_test_run_id"),
            "last_no_fix_at": dict_value(location_memory, "last_no_fix", "server_received_at"),
        },
        "explainability": {
            "state": "warning" if reason_codes else "ok",
            "reason_codes": reason_codes,
        },
    }


def load_key_release_manifests(root: Path = KEY_RELEASE_DIR) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifest["_manifest_path"] = relative_repo_path(path)
        manifests.append(manifest)
    manifests.sort(key=lambda item: (str(item.get("release_date") or ""), str(item.get("release_id") or "")))
    return manifests


def product_demo_unavailable(reason: str = "no_product_demo_report") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "candidate": "KR-008 / DEMO-008 Product Demo Closed Loop",
        "reason": reason,
        "ready_for_kr008_release": False,
        "warnings": [reason],
        "flow": {},
        "flow_status_counts": {},
        "location": {},
        "paths": {},
        "next_step": "Generate a DEMO-008 product demo report before Web review.",
    }


def latest_product_demo_report_path(root: Path = DEFAULT_PRODUCT_DEMO_REPORTS) -> Path | None:
    if not root.exists():
        return None
    try:
        candidates = [path for path in root.glob("**/product_demo_report.json") if path.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def load_latest_product_demo_report(root: Path = DEFAULT_PRODUCT_DEMO_REPORTS) -> dict[str, Any]:
    path = latest_product_demo_report_path(root)
    if path is None:
        return product_demo_unavailable()
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return product_demo_unavailable("product_demo_report_unreadable")
    if not isinstance(report, dict):
        return product_demo_unavailable("product_demo_report_invalid")

    result = as_dict(report.get("result"))
    demo = as_dict(report.get("demo"))
    source = as_dict(report.get("source"))
    evidence = as_dict(report.get("evidence_summary"))
    paths = as_dict(report.get("paths"))
    flow = as_dict(report.get("flow"))
    summarized_flow = {
        step: compact_dict(
            {
                "status": as_dict(gate).get("status"),
                "summary": as_dict(gate).get("summary"),
                "warnings": as_dict(gate).get("warnings"),
                "next_step": as_dict(gate).get("next_step"),
            }
        )
        for step, gate in flow.items()
    }
    markdown_path = paths.get("product_demo_report_markdown")
    if not markdown_path:
        markdown_candidate = path.with_suffix(".md")
        markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": result.get("status", "unknown"),
            "candidate": demo.get("candidate", "KR-008 / DEMO-008 Product Demo Closed Loop"),
            "mode": demo.get("mode"),
            "product_ready": demo.get("product_ready", False),
            "ready_for_kr008_release": result.get("ready_for_kr008_release", False),
            "why_not_release_ready": result.get("why_not_release_ready"),
            "warnings": result.get("warnings"),
            "errors": result.get("errors"),
            "test_run_id": source.get("test_run_id"),
            "safety_session_id": source.get("safety_session_id"),
            "evidence_mode": source.get("evidence_mode"),
            "dataset_samples": source.get("dataset_samples"),
            "location": report.get("location"),
            "flow": summarized_flow,
            "flow_order": report.get("flow_order"),
            "flow_status_counts": evidence.get("flow_status_counts"),
            "feature_groups": evidence.get("feature_groups"),
            "raw_frame_refs": evidence.get("raw_frame_refs"),
            "derived_event_refs": evidence.get("derived_event_refs"),
            "training_readiness": evidence.get("training_readiness"),
            "release_gate_usage": evidence.get("release_gate_usage"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "paths": {
                key: value
                for key, value in paths.items()
                if key
                in {
                    "product_demo_report_json",
                    "product_demo_report_markdown",
                    "dataset_samples",
                    "dataset_manifest",
                    "eale_report_json",
                    "eale_report_markdown",
                }
            },
            "next_gates": report.get("next_gates"),
            "non_claims": report.get("non_claims"),
        }
    )


def field_results_unavailable(reason: str = "no_field_result_reports") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "reports": [],
        "next_step": "Run or sync a D1 field/Web/API report so it can appear here.",
    }


def latest_report_path(root: Path, patterns: list[str]) -> Path | None:
    if not root.exists():
        return None
    candidates: list[Path] = []
    try:
        for pattern in patterns:
            candidates.extend(path for path in root.glob(pattern) if path.is_file())
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def load_json_report(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_progress_board(path: Path = DEFAULT_PROGRESS_BOARD) -> dict[str, Any]:
    board = load_json_report(path)
    if board is None:
        return {
            "status": "unavailable",
            "reason": "progress_board_missing_or_invalid",
            "milestones": [],
            "operator_asks": [],
        }

    milestones: list[dict[str, Any]] = []
    for raw_milestone in as_list(board.get("milestones"))[:12]:
        milestone = as_dict(raw_milestone)
        tasks = []
        for raw_task in as_list(milestone.get("tasks"))[:24]:
            task = as_dict(raw_task)
            tasks.append(
                {
                    "id": str(task.get("id") or "")[:64],
                    "label": str(task.get("label") or "")[:160],
                    "state": str(task.get("state") or "unknown")[:32],
                }
            )
        milestones.append(
            {
                "id": str(milestone.get("id") or "")[:64],
                "title": str(milestone.get("title") or "")[:160],
                "done": max(0, int(milestone.get("done") or 0)),
                "total": max(0, int(milestone.get("total") or 0)),
                "tasks": tasks,
            }
        )

    git = as_dict(board.get("git"))
    open_tasks = as_list(board.get("active_tasks"))
    active_count = as_dict(board.get("counts")).get("active")
    if type(active_count) is not int or active_count < 0:
        # Legacy boards did not publish separate implementation/open counts.
        active_count = len(open_tasks)
    return {
        "status": "available",
        "generated_at": str(board.get("generated_at") or "unknown")[:64],
        "current_focus": str(board.get("current_focus") or "unknown")[:600],
        "git": {
            "branch": str(git.get("branch") or "unknown")[:128],
            "head": str(git.get("head") or "unknown")[:240],
        },
        "milestones": milestones,
        "operator_asks": [str(item)[:600] for item in as_list(board.get("operator_asks"))[:12]],
        "summary": {
            "active_count": active_count,
            "open_count": len(open_tasks),
            "recent_done_count": len(as_list(board.get("recent_done"))),
            "key_release_count": len(as_list(board.get("key_releases"))),
        },
        "privacy": {
            "local_paths_exposed": False,
            "task_packet_contents_exposed": False,
            "read_only": True,
        },
    }


def normalized_report_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    if status in {"pass", "passed", "ok", "true"}:
        return "pass"
    if status in {"warn", "warning"}:
        return "warn"
    if status in {"fail", "failed", "false", "error"}:
        return "fail"
    return status or "unknown"


def report_file_time(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return utc_now()


def path_if_exists(path: Path) -> str | None:
    return relative_repo_path(path) if path.exists() else None


def latest_d1_web_api_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "d1_web_api", ["**/d1_web_api_report.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    d1 = as_dict(report.get("d1"))
    freshness = as_dict(d1.get("upload_freshness"))
    uplink = as_dict(d1.get("uplink_metrics"))
    power_curve = as_dict(d1.get("power_curve"))
    status = normalized_report_status(report.get("result"))
    markdown_candidate = path.with_suffix(".md")
    return compact_dict(
        {
            "kind": "d1_web_api",
            "title": "D1 Web/API Gate",
            "status": status,
            "run_id": report.get("review_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "device_id": report.get("device_id") or d1.get("device_id"),
            "summary": f"D1 Web/API {status}: {d1.get('status', 'unknown')}",
            "metrics": {
                "upload_freshness_s": freshness.get("freshness_s"),
                "raw_post": f"{uplink.get('raw_post_success_count', 'unknown')} ok / {uplink.get('raw_post_failure_count', 'unknown')} fail",
                "location_uploads": uplink.get("location_event_count"),
                "power_curve": f"{power_curve.get('sample_count', 0)} samples / {power_curve.get('window_s', 'unknown')} s",
            },
            "warnings": report.get("warnings"),
            "errors": report.get("errors"),
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
            "scope": report.get("scope"),
        }
    )


def latest_amoled_status_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "amoled_visible_status", ["**/*.summary.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    status = normalized_report_status("pass" if report.get("ok") is True else "fail")
    payload = as_dict(report.get("last_status_payload"))
    return compact_dict(
        {
            "kind": "amoled_status",
            "title": "AMOLED Status Screen",
            "status": status,
            "run_id": report.get("session_id"),
            "created_at": report_file_time(path),
            "device_id": report.get("device_id"),
            "summary": f"AMOLED {status}: {report.get('command_ack_count', 0)} ack / {report.get('status_rendered_count', 0)} rendered",
            "metrics": {
                "commands_sent": report.get("commands_sent"),
                "command_ack_count": report.get("command_ack_count"),
                "status_rendered_count": report.get("status_rendered_count"),
                "last_screen": payload.get("summary"),
                "last_location": payload.get("location"),
                "last_power": payload.get("battery"),
            },
            "report_path": relative_repo_path(path),
            "scope": report.get("scope"),
        }
    )


def child_summary(children: list[Any], name: str) -> dict[str, Any]:
    for child in children:
        item = as_dict(child)
        if item.get("name") == name:
            return as_dict(item.get("summary"))
    return {}


def latest_d1_companion_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "d1_field_companion", ["**/d1_field_companion_summary.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    children = report.get("children") if isinstance(report.get("children"), list) else []
    observer = child_summary(children, "d1_observer")
    observer_summary = as_dict(observer.get("summary"))
    amoled = child_summary(children, "amoled_sidecar")
    status = normalized_report_status(report.get("result"))
    markdown_candidate = path.with_name("d1_field_companion_summary.md")
    return compact_dict(
        {
            "kind": "d1_field_companion",
            "title": "D1 Field Companion",
            "status": status,
            "run_id": report.get("run_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "device_id": report.get("device_id") or observer.get("device_id"),
            "summary": f"D1 companion {status}: {observer_summary.get('successful_sample_count', 0)} samples / {amoled.get('status_rendered_count', 0)} rendered",
            "metrics": {
                "sample_count": observer_summary.get("sample_count"),
                "successful_sample_count": observer_summary.get("successful_sample_count"),
                "coordinate_sample_count": observer_summary.get("coordinate_sample_count"),
                "max_freshness_s": observer_summary.get("max_freshness_s"),
                "raw_post_delta": observer_summary.get("raw_post_success_delta"),
                "battery_mv_first": observer_summary.get("battery_mv_first"),
                "battery_mv_last": observer_summary.get("battery_mv_last"),
                "status_rendered_count": amoled.get("status_rendered_count"),
            },
            "warnings": observer.get("warnings"),
            "errors": observer.get("errors"),
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
            "scope": report.get("scope") or observer.get("scope"),
        }
    )


def latest_d1_field_observation_result(root: Path) -> dict[str, Any] | None:
    report_path = latest_report_path(root / "d1_field_observation", ["**/d1_field_observation_report.json"])
    status_path = latest_report_path(root / "d1_field_observation", ["**/d1_field_observation_status.json"])
    if report_path is None and status_path is None:
        return None
    use_status = False
    if status_path is not None:
        if report_path is None:
            use_status = True
        else:
            try:
                use_status = status_path.stat().st_mtime > report_path.stat().st_mtime
            except OSError:
                use_status = False
    if report_path is not None and not use_status:
        report = load_json_report(report_path)
        if report is None:
            return None
        summary = as_dict(report.get("summary"))
        status = normalized_report_status(report.get("result"))
        markdown_candidate = report_path.with_name("d1_field_observation_report.md")
        status_candidate = report_path.with_name("d1_field_observation_status.json")
        return compact_dict(
            {
                "kind": "d1_field_observation",
                "title": "D1 Field Observation",
                "status": status,
                "run_id": report.get("run_id"),
                "created_at": report.get("created_at") or report_file_time(report_path),
                "device_id": report.get("device_id"),
                "summary": f"D1 observation {status}: {summary.get('successful_sample_count', 0)} ok / {summary.get('sample_count', 0)} samples",
                "metrics": {
                    "sample_count": summary.get("sample_count"),
                    "successful_sample_count": summary.get("successful_sample_count"),
                    "fetch_error_count": summary.get("fetch_error_count"),
                    "max_freshness_s": summary.get("max_freshness_s"),
                    "last_seq": summary.get("last_seq"),
                    "last_location_upload_at": summary.get("last_location_upload_at"),
                    "raw_post_success_delta": summary.get("raw_post_success_delta"),
                    "location_event_count_delta": summary.get("location_event_count_delta"),
                    "power_sample_count_delta": summary.get("power_sample_count_delta"),
                    "battery_mv_first": summary.get("battery_mv_first"),
                    "battery_mv_last": summary.get("battery_mv_last"),
                },
                "warnings": report.get("warnings"),
                "errors": report.get("errors"),
                "report_path": relative_repo_path(report_path),
                "markdown_path": path_if_exists(markdown_candidate),
                "status_path": path_if_exists(status_candidate),
                "scope": report.get("scope"),
            }
        )
    status_report = load_json_report(status_path) if status_path is not None else None
    if status_report is None or status_path is None:
        return None
    status = normalized_report_status(status_report.get("result") or status_report.get("status"))
    report_candidate = status_path.with_name("d1_field_observation_report.json")
    markdown_candidate = status_path.with_name("d1_field_observation_report.md")
    return compact_dict(
        {
            "kind": "d1_field_observation",
            "title": "D1 Field Observation",
            "status": status,
            "run_id": status_report.get("run_id"),
            "created_at": status_report.get("updated_at") or report_file_time(status_path),
            "device_id": status_report.get("device_id"),
            "summary": f"D1 observation {status}: {status_report.get('successful_sample_count', 0)} ok / {status_report.get('sample_count', 0)} samples",
            "metrics": {
                "planned_sample_count": status_report.get("planned_sample_count"),
                "sample_count": status_report.get("sample_count"),
                "successful_sample_count": status_report.get("successful_sample_count"),
                "fetch_error_count": status_report.get("fetch_error_count"),
                "latest_seq": status_report.get("latest_seq"),
                "latest_freshness_s": status_report.get("latest_freshness_s"),
                "latest_location_upload_at": status_report.get("latest_location_upload_at"),
                "latest_d1_status": status_report.get("latest_d1_status"),
            },
            "report_path": path_if_exists(report_candidate),
            "markdown_path": path_if_exists(markdown_candidate),
            "status_path": relative_repo_path(status_path),
            "scope": status_report.get("scope"),
        }
    )


def latest_power_curve_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "power", ["**/power_curve_report.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    result = as_dict(report.get("result"))
    counts = as_dict(report.get("counts"))
    estimate = as_dict(report.get("consumption_estimate"))
    target = as_dict(report.get("target_comparison"))
    status = normalized_report_status(result.get("status"))
    markdown_candidate = path.with_name("power_curve_report.md")
    measured = counts.get("measured_power_samples", 0)
    total = counts.get("samples", 0)
    return compact_dict(
        {
            "kind": "power_curve",
            "title": "D1 Power Curve",
            "status": status,
            "run_id": as_dict(report.get("source")).get("test_run_id"),
            "created_at": as_dict(report.get("generator")).get("created_at") or report_file_time(path),
            "summary": f"Power curve {status}: {measured} measured / {total} samples",
            "metrics": {
                "duration_hours": report.get("duration_hours"),
                "measured_power_samples": measured,
                "battery_mv_samples": counts.get("battery_mv_samples"),
                "soc_pct_samples": counts.get("soc_pct_samples"),
                "average_current_status": estimate.get("status"),
                "target_gap_status": target.get("status"),
            },
            "warnings": result.get("warnings"),
            "errors": result.get("errors"),
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
        }
    )


def latest_d1_demo_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "d1_demo", ["**/d1_demo_report.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    status = normalized_report_status(report.get("result"))
    power = as_dict(report.get("power"))
    power_counts = as_dict(power.get("counts"))
    markdown_candidate = path.with_name("d1_demo_report.md")
    return compact_dict(
        {
            "kind": "d1_demo",
            "title": "D1 Demo Report",
            "status": status,
            "run_id": report.get("report_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "summary": f"D1 demo {status}: founder ready {bool(report.get('ready_for_founder_review'))}",
            "metrics": {
                "ready_for_founder_review": bool(report.get("ready_for_founder_review")),
                "d1_status": as_dict(report.get("d1")).get("status"),
                "power_result": power.get("result"),
                "power_duration_hours": power.get("duration_hours"),
                "measured_power_samples": power_counts.get("measured_power_samples"),
            },
            "gates": [
                compact_dict(
                    {
                        "id": as_dict(gate).get("id"),
                        "status": as_dict(gate).get("status"),
                        "summary": as_dict(gate).get("summary"),
                    }
                )
                for gate in as_list(report.get("gates"))
            ],
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
            "boundaries": report.get("boundaries"),
        }
    )


def latest_d1_postrun_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(root / "d1_postrun", ["**/d1_postrun_collection_summary.json"])
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    components = as_dict(report.get("components"))
    web_api = as_dict(components.get("web_api"))
    power = as_dict(components.get("power_curve"))
    demo = as_dict(components.get("d1_demo"))
    field = as_dict(components.get("field_observation"))
    status = normalized_report_status(report.get("result"))
    markdown_candidate = path.with_name("d1_postrun_collection_summary.md")
    return compact_dict(
        {
            "kind": "d1_postrun",
            "title": "D1 Post-Run Summary",
            "status": status,
            "run_id": report.get("run_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "summary": f"D1 post-run {status}: web {web_api.get('result', web_api.get('status'))} / power {power.get('result', power.get('status'))} / demo {demo.get('result', demo.get('status'))}",
            "metrics": {
                "web_api": web_api.get("result") or web_api.get("status"),
                "field_observation": field.get("result") or field.get("status"),
                "power_curve": power.get("result") or power.get("status"),
                "d1_demo": demo.get("result") or demo.get("status"),
                "ready_for_founder_review": demo.get("ready_for_founder_review"),
            },
            "warnings": report.get("warnings"),
            "errors": report.get("errors"),
            "next_steps": as_list(report.get("next_steps"))[:3],
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
        }
    )


def latest_location_accuracy_result(root: Path) -> dict[str, Any] | None:
    path = latest_report_path(
        root / "location_accuracy",
        ["**/location_accuracy_report.json", "**/d2_location_accuracy_report.json"],
    )
    if path is None:
        return None
    report = load_json_report(path)
    if report is None:
        return None
    result = as_dict(report.get("result"))
    metrics = as_dict(first_known(report.get("metrics"), report.get("summary"), result))
    source = as_dict(report.get("source"))
    status = normalized_report_status(first_known(result.get("status"), report.get("status")))
    markdown_candidate = path.with_suffix(".md")
    fix_rate = first_known(metrics.get("fix_rate"), metrics.get("fix_rate_pct"), report.get("fix_rate"))
    median_error_m = first_known(metrics.get("median_error_m"), report.get("median_error_m"))
    p90_error_m = first_known(metrics.get("p90_error_m"), report.get("p90_error_m"))
    ttff_median_s = first_known(
        metrics.get("ttff_median_s"),
        metrics.get("median_ttff_s"),
        metrics.get("ttff_p50_s"),
        report.get("ttff_median_s"),
    )
    return compact_dict(
        {
            "kind": "d2_location_accuracy",
            "title": "D2 Location Accuracy Baseline",
            "status": status,
            "run_id": first_known(report.get("run_id"), report.get("baseline_id"), source.get("run_id")),
            "created_at": first_known(report.get("created_at"), as_dict(report.get("generator")).get("created_at"), report_file_time(path)),
            "device_id": first_known(report.get("device_id"), source.get("device_id")),
            "summary": (
                f"D2 location baseline {status}: median {median_error_m if median_error_m is not None else 'unknown'} m"
                f" / p90 {p90_error_m if p90_error_m is not None else 'unknown'} m"
                f" / fix {fix_rate if fix_rate is not None else 'unknown'}"
            ),
            "metrics": {
                "fix_rate": fix_rate,
                "ttff_median_s": ttff_median_s,
                "median_error_m": median_error_m,
                "p90_error_m": p90_error_m,
                "reference_point_count": first_known(
                    metrics.get("reference_point_count"),
                    metrics.get("reference_points"),
                    report.get("reference_point_count"),
                ),
                "sample_count": first_known(metrics.get("sample_count"), metrics.get("attempt_count")),
            },
            "warnings": first_known(report.get("warnings"), result.get("warnings")),
            "errors": first_known(report.get("errors"), result.get("errors")),
            "report_path": relative_repo_path(path),
            "markdown_path": path_if_exists(markdown_candidate),
            "privacy": {
                "raw_coordinates_exposed": False,
                "static_report_policy": "bounded_summary_no_raw_coordinates",
            },
            "scope": {
                "location_accuracy_claimed": False,
                "engineering_baseline_only": True,
            },
        }
    )


def load_latest_field_results(root: Path = DEFAULT_FIELD_RESULT_REPORTS) -> dict[str, Any]:
    reports = [
        result
        for result in (
            latest_location_accuracy_result(root),
            latest_d1_web_api_result(root),
            latest_d1_postrun_result(root),
            latest_d1_demo_result(root),
            latest_power_curve_result(root),
            latest_d1_field_observation_result(root),
            latest_d1_companion_result(root),
            latest_amoled_status_result(root),
        )
        if result is not None
    ]
    if not reports:
        return field_results_unavailable()
    status_rank = {"fail": 3, "warn": 2, "unknown": 1, "pass": 0}
    worst = max((normalized_report_status(item.get("status")) for item in reports), key=lambda item: status_rank.get(item, 1))
    latest_created = max((str(item.get("created_at", "")) for item in reports), default="")
    return {
        "available": True,
        "status": worst,
        "report_count": len(reports),
        "latest_created_at": latest_created,
        "reports": reports,
        "next_step": "Run D2 location baseline or continue D1 regression, then sync bounded report summaries.",
    }


def data_flywheel_unavailable(reason: str = "no_data_flywheel_status_report") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "counts": {},
        "review": {},
        "readiness": {"model_training_ready": False},
        "blockers": [reason],
        "warnings": [reason],
        "next_step": "Run scripts/summarize_data_flywheel.py after building or updating the candidate store.",
    }


def latest_data_flywheel_status_path(root: Path = DEFAULT_DATA_FLYWHEEL_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/data_flywheel_status.json"])


def load_latest_data_flywheel_status(root: Path = DEFAULT_DATA_FLYWHEEL_REPORTS) -> dict[str, Any]:
    path = latest_data_flywheel_status_path(root)
    if path is None:
        return data_flywheel_unavailable()
    report = load_json_report(path)
    if report is None:
        return data_flywheel_unavailable("data_flywheel_status_unreadable")
    counts = as_dict(report.get("counts"))
    review = as_dict(report.get("review"))
    review_queue = as_dict(report.get("review_queue"))
    readiness = as_dict(report.get("readiness"))
    candidate_store = as_dict(report.get("candidate_store"))
    paths = as_dict(report.get("paths"))
    markdown_path = paths.get("data_flywheel_status_markdown")
    if not markdown_path:
        markdown_candidate = path.with_suffix(".md")
        markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "pipeline_stage": report.get("pipeline_stage"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "candidate_store": {
                "available": candidate_store.get("available", False),
                "reason": candidate_store.get("reason"),
                "schema_version": candidate_store.get("schema_version"),
                "latest_updated_at": candidate_store.get("latest_updated_at"),
            },
            "counts": {
                "sessions_total": counts.get("sessions_total", 0),
                "records_total": counts.get("records_total", 0),
                "needs_review_records": counts.get("needs_review_records", 0),
                "training_allowed_records": counts.get("training_allowed_records", 0),
                "reviewed_training_candidate_records": counts.get("reviewed_training_candidate_records", 0),
                "experiment_input_records": counts.get("experiment_input_records", 0),
                "location_baseline_reports": counts.get("location_baseline_reports", 0),
                "reference_points": counts.get("reference_points", 0),
                "location_attempts": counts.get("location_attempts", 0),
                "fixed_attempts": counts.get("fixed_attempts", 0),
                "no_fix_attempts": counts.get("no_fix_attempts", 0),
                "location_field_evidence_reports": counts.get("location_field_evidence_reports", 0),
                "field_samples": counts.get("field_samples", 0),
                "field_successful_samples": counts.get("field_successful_samples", 0),
                "field_coordinate_samples": counts.get("field_coordinate_samples", 0),
                "field_gnss_fix_samples": counts.get("field_gnss_fix_samples", 0),
                "field_gnss_no_fix_samples": counts.get("field_gnss_no_fix_samples", 0),
                "field_gnss_unknown_samples": counts.get("field_gnss_unknown_samples", 0),
                "field_unique_cell_count": counts.get("field_unique_cell_count", 0),
                "field_raw_post_success_delta": counts.get("field_raw_post_success_delta", 0),
                "field_raw_post_failure_delta": counts.get("field_raw_post_failure_delta", 0),
                "field_track_point_delta": counts.get("field_track_point_delta", 0),
                "field_power_sample_count_delta": counts.get("field_power_sample_count_delta", 0),
            },
            "source_reports": report.get("source_reports"),
            "state_counts": report.get("state_counts"),
            "candidate_type_counts": report.get("candidate_type_counts"),
            "quality_gate_counts": report.get("quality_gate_counts"),
            "label_review_state_counts": report.get("label_review_state_counts"),
            "review": {
                "label_review_pending_records": review.get("label_review_pending_records", 0),
                "split_leakage_unchecked_records": review.get("split_leakage_unchecked_records", 0),
                "privacy_or_consent_blocked_records": review.get("privacy_or_consent_blocked_records", 0),
                "quality_blocked_records": review.get("quality_blocked_records", 0),
            },
            "review_queue": {
                "available": review_queue.get("available", False),
                "pending_records": review_queue.get("pending_records", 0),
                "sample_records": review_queue.get("sample_records", []),
                "available_actions": review_queue.get("available_actions", []),
            },
            "readiness": {
                "model_training_ready": readiness.get("model_training_ready", False),
                "reason": readiness.get("reason"),
                "dataset_manifest_ready": readiness.get("dataset_manifest_ready", False),
                "training_server_ready": readiness.get("training_server_ready", False),
                "on_device_deployment_ready": readiness.get("on_device_deployment_ready", False),
            },
            "warnings": report.get("warnings"),
            "blockers": report.get("blockers"),
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "review_packet_path": paths.get("location_review_packet_markdown"),
            "dataset_manifest_path": paths.get("location_dataset_manifest_markdown"),
            "non_claims": report.get("non_claims"),
        }
    )


def training_experiment_unavailable(reason: str = "no_training_experiment_plan") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "dataset": {},
        "model_track": {},
        "runner": {"ready_for_handoff": False},
        "metrics_plan": {},
        "gates": {"dataset_ready": False},
        "blockers": [reason],
        "next_step": "Run scripts/register_training_experiment.py after exporting a dataset manifest.",
    }


def latest_training_experiment_plan_path(root: Path = DEFAULT_TRAINING_EXPERIMENT_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_experiment_plan.json"])


def load_latest_training_experiment_plan(root: Path = DEFAULT_TRAINING_EXPERIMENT_REPORTS) -> dict[str, Any]:
    path = latest_training_experiment_plan_path(root)
    if path is None:
        return training_experiment_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_experiment_unavailable("training_experiment_plan_unreadable")
    dataset = as_dict(report.get("dataset"))
    runner = as_dict(report.get("runner"))
    metrics_plan = as_dict(report.get("metrics_plan"))
    model_track = as_dict(report.get("model_track"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    raw_record_sample = dataset.get("record_sample") if isinstance(dataset.get("record_sample"), list) else []
    record_sample = [
        {
            "record_id": record.get("record_id"),
            "session_id": record.get("session_id"),
            "candidate_type": record.get("candidate_type"),
            "label": record.get("label"),
            "split_name": record.get("split_name"),
            "source_manifest_hash": record.get("source_manifest_hash"),
        }
        for record in raw_record_sample[:5]
        if isinstance(record, dict)
    ]
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "experiment_id": report.get("experiment_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "manifest_status": dataset.get("manifest_status"),
                "manifest_reason": dataset.get("manifest_reason"),
                "records_total": dataset.get("records_total", 0),
                "eligible_records": dataset.get("eligible_records", 0),
                "reviewed_training_candidate_records": dataset.get("reviewed_training_candidate_records", 0),
                "split_counts": as_dict(dataset.get("split_counts")),
                "record_sample": record_sample,
            },
            "model_track": {
                "track": model_track.get("track"),
                "candidate_model": model_track.get("candidate_model"),
                "baseline_model": model_track.get("baseline_model"),
            },
            "runner": {
                "integration": runner.get("integration"),
                "ready_for_handoff": runner.get("ready_for_handoff", False),
                "next_command": runner.get("next_command"),
            },
            "metrics_plan": {
                "classification": as_dict(metrics_plan.get("classification")),
                "operations": as_dict(metrics_plan.get("operations")),
            },
            "gates": {
                "dataset_ready": gates.get("dataset_ready", False),
                "privacy_review": gates.get("privacy_review"),
                "consent_review": gates.get("consent_review"),
                "split_leakage": gates.get("split_leakage"),
                "baseline_comparison": gates.get("baseline_comparison"),
                "footprint": gates.get("footprint"),
                "power": gates.get("power"),
                "rollback_plan": gates.get("rollback_plan"),
            },
            "next_step": runner.get("next_command"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def training_run_preflight_unavailable(reason: str = "no_training_run_preflight") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "experiment": {},
        "dataset": {},
        "runner": {"ready_for_training_runner": False},
        "checks": {},
        "metrics_plan": {"measured": {}},
        "gates": {"preflight_ready": False},
        "blockers": [reason],
        "next_step": "Run scripts/run_training_experiment_preflight.py after TRAIN-002 is runner-ready.",
    }


def latest_training_run_preflight_path(root: Path = DEFAULT_TRAINING_RUN_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_run_preflight.json"])


def load_latest_training_run_preflight(root: Path = DEFAULT_TRAINING_RUN_REPORTS) -> dict[str, Any]:
    path = latest_training_run_preflight_path(root)
    if path is None:
        return training_run_preflight_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_run_preflight_unavailable("training_run_preflight_unreadable")
    experiment = as_dict(report.get("experiment"))
    dataset = as_dict(report.get("dataset"))
    runner = as_dict(report.get("runner"))
    checks = as_dict(report.get("checks"))
    metrics_plan = as_dict(report.get("metrics_plan"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    raw_record_sample = dataset.get("record_sample") if isinstance(dataset.get("record_sample"), list) else []
    record_sample = [
        {
            "record_id": record.get("record_id"),
            "session_id": record.get("session_id"),
            "candidate_type": record.get("candidate_type"),
            "label": record.get("label"),
            "split_name": record.get("split_name"),
            "source_status": record.get("source_status"),
            "source_manifest_hash": record.get("source_manifest_hash"),
        }
        for record in raw_record_sample[:5]
        if isinstance(record, dict)
    ]
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "experiment": {
                "experiment_id": experiment.get("experiment_id"),
                "status": experiment.get("status"),
                "reason": experiment.get("reason"),
                "model_track": as_dict(experiment.get("model_track")),
            },
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "status": dataset.get("status"),
                "reason": dataset.get("reason"),
                "records_total": dataset.get("records_total", 0),
                "eligible_records": dataset.get("eligible_records", 0),
                "reviewed_training_candidate_records": dataset.get("reviewed_training_candidate_records", 0),
                "experiment_records_total": dataset.get("experiment_records_total", 0),
                "split_counts": as_dict(dataset.get("split_counts")),
                "label_counts": as_dict(dataset.get("label_counts")),
                "source_status_counts": as_dict(dataset.get("source_status_counts")),
                "synthetic_records": dataset.get("synthetic_records", 0),
                "synthetic_allowed_for_dry_run": dataset.get("synthetic_allowed_for_dry_run", False),
                "record_sample": record_sample,
            },
            "checks": {
                "experiment_ready": checks.get("experiment_ready", False),
                "dataset_ready": checks.get("dataset_ready", False),
                "has_eligible_records": checks.get("has_eligible_records", False),
                "required_record_fields": checks.get("required_record_fields"),
                "missing_record_fields": as_dict(checks.get("missing_record_fields")),
                "split_counts": as_dict(checks.get("split_counts")),
                "synthetic_record_policy": checks.get("synthetic_record_policy"),
            },
            "runner": {
                "integration": runner.get("integration"),
                "ready_for_training_runner": runner.get("ready_for_training_runner", False),
                "next_step": runner.get("next_step"),
            },
            "metrics_plan": {
                "planned": as_dict(metrics_plan.get("planned")),
                "measured": as_dict(metrics_plan.get("measured")),
            },
            "gates": {
                "preflight_ready": gates.get("preflight_ready", False),
                "dataset_gate": gates.get("dataset_gate"),
                "experiment_gate": gates.get("experiment_gate"),
                "synthetic_gate": gates.get("synthetic_gate"),
                "model_training": gates.get("model_training"),
                "model_evaluation": gates.get("model_evaluation"),
                "model_artifact": gates.get("model_artifact"),
                "training_server": gates.get("training_server"),
                "device_deployment": gates.get("device_deployment"),
            },
            "next_step": report.get("next_step") or runner.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def training_feature_manifest_unavailable(reason: str = "no_training_feature_manifest") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "dataset": {},
        "preflight": {},
        "feature_rows": {"row_count": 0},
        "checks": {},
        "gates": {"feature_export": "not_available"},
        "blockers": [reason],
        "next_step": "Run scripts/export_training_feature_manifest.py after TRAIN-003 is runner-ready.",
    }


def latest_training_feature_manifest_path(root: Path = DEFAULT_TRAINING_FEATURE_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_feature_manifest.json"])


def load_latest_training_feature_manifest(root: Path = DEFAULT_TRAINING_FEATURE_REPORTS) -> dict[str, Any]:
    path = latest_training_feature_manifest_path(root)
    if path is None:
        return training_feature_manifest_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_feature_manifest_unavailable("training_feature_manifest_unreadable")
    dataset = as_dict(report.get("dataset"))
    preflight = as_dict(report.get("preflight"))
    feature_rows = as_dict(report.get("feature_rows"))
    checks = as_dict(report.get("checks"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "feature_set_id": report.get("feature_set_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "status": dataset.get("status"),
                "reason": dataset.get("reason"),
                "records_total": dataset.get("records_total", 0),
                "eligible_records": dataset.get("eligible_records", 0),
                "reviewed_training_candidate_records": dataset.get("reviewed_training_candidate_records", 0),
                "split_counts": as_dict(dataset.get("split_counts")),
                "label_counts": as_dict(dataset.get("label_counts")),
                "source_status_counts": as_dict(dataset.get("source_status_counts")),
                "synthetic_records": dataset.get("synthetic_records", 0),
                "synthetic_allowed_for_dry_run": dataset.get("synthetic_allowed_for_dry_run", False),
            },
            "preflight": {
                "run_id": preflight.get("run_id"),
                "status": preflight.get("status"),
                "reason": preflight.get("reason"),
                "dataset_id": preflight.get("dataset_id"),
                "runner_ready": preflight.get("runner_ready", False),
                "metrics_measured": as_dict(preflight.get("metrics_measured")),
            },
            "feature_rows": {
                "row_schema_version": feature_rows.get("row_schema_version"),
                "row_count": feature_rows.get("row_count", 0),
                "rows_ref": feature_rows.get("rows_ref"),
                "feature_groups": as_list(feature_rows.get("feature_groups")),
                "feature_scope": feature_rows.get("feature_scope"),
                "target_separated_from_features": feature_rows.get("target_separated_from_features", False),
            },
            "checks": {
                "dataset_ready": checks.get("dataset_ready", False),
                "preflight_ready": checks.get("preflight_ready", False),
                "source_match": checks.get("source_match", False),
                "has_records": checks.get("has_records", False),
                "required_record_fields": checks.get("required_record_fields"),
                "missing_record_fields": as_dict(checks.get("missing_record_fields")),
                "synthetic_record_policy": checks.get("synthetic_record_policy"),
                "label_leakage_guard": checks.get("label_leakage_guard"),
            },
            "gates": {
                "feature_export": gates.get("feature_export"),
                "training_runner": gates.get("training_runner"),
                "model_training": gates.get("model_training"),
                "model_evaluation": gates.get("model_evaluation"),
                "model_artifact": gates.get("model_artifact"),
                "training_server": gates.get("training_server"),
                "device_deployment": gates.get("device_deployment"),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def training_runner_dry_run_unavailable(reason: str = "no_training_runner_dry_run") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "feature_manifest": {},
        "feature_rows": {"actual_row_count": 0},
        "runner": {"dry_run_only": False, "ready_for_real_runner": False},
        "checks": {},
        "metrics_plan": {"measured": {}},
        "gates": {"runner_input": "not_available"},
        "blockers": [reason],
        "next_step": "Run scripts/run_training_runner_dry_run.py after TRAIN-004 feature rows are ready.",
    }


def latest_training_runner_dry_run_path(root: Path = DEFAULT_TRAINING_RUNNER_DRY_RUN_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_runner_dry_run.json"])


def load_latest_training_runner_dry_run(root: Path = DEFAULT_TRAINING_RUNNER_DRY_RUN_REPORTS) -> dict[str, Any]:
    path = latest_training_runner_dry_run_path(root)
    if path is None:
        return training_runner_dry_run_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_runner_dry_run_unavailable("training_runner_dry_run_unreadable")
    feature_manifest = as_dict(report.get("feature_manifest"))
    dataset = as_dict(report.get("dataset"))
    preflight = as_dict(report.get("preflight"))
    feature_rows = as_dict(report.get("feature_rows"))
    checks = as_dict(report.get("checks"))
    runner = as_dict(report.get("runner"))
    metrics_plan = as_dict(report.get("metrics_plan"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "feature_manifest": {
                "feature_set_id": feature_manifest.get("feature_set_id"),
                "status": feature_manifest.get("status"),
                "reason": feature_manifest.get("reason"),
                "feature_scope": feature_manifest.get("feature_scope"),
                "target_separated_from_features": feature_manifest.get("target_separated_from_features", False),
            },
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "status": dataset.get("status"),
                "eligible_records": dataset.get("eligible_records", 0),
                "synthetic_records": dataset.get("synthetic_records", 0),
            },
            "preflight": {
                "run_id": preflight.get("run_id"),
                "status": preflight.get("status"),
                "runner_ready": preflight.get("runner_ready", False),
                "metrics_measured": as_dict(preflight.get("metrics_measured")),
            },
            "feature_rows": {
                "expected_row_count": feature_rows.get("expected_row_count", 0),
                "actual_row_count": feature_rows.get("actual_row_count", 0),
                "row_count_matches": feature_rows.get("row_count_matches", False),
                "feature_set_mismatch_count": feature_rows.get("feature_set_mismatch_count", 0),
                "split_counts": as_dict(feature_rows.get("split_counts")),
                "label_counts": as_dict(feature_rows.get("label_counts")),
                "source_status_counts": as_dict(feature_rows.get("source_status_counts")),
                "feature_group_counts": as_dict(feature_rows.get("feature_group_counts")),
                "synthetic_rows": feature_rows.get("synthetic_rows", 0),
                "synthetic_allowed_for_dry_run": feature_rows.get("synthetic_allowed_for_dry_run", False),
            },
            "checks": {
                "feature_manifest_ready": checks.get("feature_manifest_ready", False),
                "feature_rows_readable": checks.get("feature_rows_readable", False),
                "row_count_matches": checks.get("row_count_matches", False),
                "required_row_fields": checks.get("required_row_fields"),
                "missing_row_fields": as_dict(checks.get("missing_row_fields")),
                "target_leakage_guard": checks.get("target_leakage_guard"),
                "target_leakage_violations": as_dict(checks.get("target_leakage_violations")),
                "synthetic_row_policy": checks.get("synthetic_row_policy"),
                "manifest_feature_export_gate": checks.get("manifest_feature_export_gate"),
            },
            "runner": {
                "integration": runner.get("integration"),
                "ready_for_real_runner": runner.get("ready_for_real_runner", False),
                "dry_run_only": runner.get("dry_run_only", False),
                "next_step": runner.get("next_step"),
            },
            "metrics_plan": {
                "measured": as_dict(metrics_plan.get("measured")),
                "dry_run_summary": as_dict(metrics_plan.get("dry_run_summary")),
            },
            "gates": {
                "runner_input": gates.get("runner_input"),
                "model_training": gates.get("model_training"),
                "model_evaluation": gates.get("model_evaluation"),
                "model_artifact": gates.get("model_artifact"),
                "training_server": gates.get("training_server"),
                "device_deployment": gates.get("device_deployment"),
            },
            "next_step": report.get("next_step") or runner.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def compact_training_baselines(items: list[Any]) -> list[dict[str, Any]]:
    baselines: list[dict[str, Any]] = []
    for item in items:
        baseline = as_dict(item)
        baselines.append(
            compact_dict(
                {
                    "name": baseline.get("name"),
                    "prediction_rule": baseline.get("prediction_rule"),
                    "scope": baseline.get("scope"),
                    "training_scope": baseline.get("training_scope"),
                    "predicted_label": baseline.get("predicted_label"),
                    "overall": as_dict(baseline.get("overall")),
                    "by_split": as_dict(baseline.get("by_split")),
                }
            )
        )
    return baselines


def training_baseline_eval_unavailable(reason: str = "no_training_baseline_eval") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "feature_manifest": {},
        "runner_dry_run": {},
        "feature_rows": {"actual_row_count": 0},
        "checks": {},
        "metrics": {"classification": {"baselines": []}},
        "gates": {"baseline_evaluation": "not_available"},
        "blockers": [reason],
        "next_step": "Run scripts/run_training_baseline_eval.py after TRAIN-005 runner dry-run is ready.",
    }


def latest_training_baseline_eval_path(root: Path = DEFAULT_TRAINING_BASELINE_EVAL_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_baseline_eval.json"])


def load_latest_training_baseline_eval(root: Path = DEFAULT_TRAINING_BASELINE_EVAL_REPORTS) -> dict[str, Any]:
    path = latest_training_baseline_eval_path(root)
    if path is None:
        return training_baseline_eval_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_baseline_eval_unavailable("training_baseline_eval_unreadable")
    feature_manifest = as_dict(report.get("feature_manifest"))
    runner_dry_run = as_dict(report.get("runner_dry_run"))
    dataset = as_dict(report.get("dataset"))
    feature_rows = as_dict(report.get("feature_rows"))
    checks = as_dict(report.get("checks"))
    metrics = as_dict(report.get("metrics"))
    classification = as_dict(metrics.get("classification"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "eval_id": report.get("eval_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "feature_manifest": {
                "feature_set_id": feature_manifest.get("feature_set_id"),
                "status": feature_manifest.get("status"),
                "reason": feature_manifest.get("reason"),
                "feature_scope": feature_manifest.get("feature_scope"),
                "target_separated_from_features": feature_manifest.get("target_separated_from_features", False),
            },
            "runner_dry_run": {
                "run_id": runner_dry_run.get("run_id"),
                "status": runner_dry_run.get("status"),
                "runner_input_gate": runner_dry_run.get("runner_input_gate"),
                "dry_run_only": runner_dry_run.get("dry_run_only", False),
            },
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "status": dataset.get("status"),
                "eligible_records": dataset.get("eligible_records", 0),
                "synthetic_records": dataset.get("synthetic_records", 0),
            },
            "feature_rows": {
                "expected_row_count": feature_rows.get("expected_row_count", 0),
                "actual_row_count": feature_rows.get("actual_row_count", 0),
                "row_count_matches": feature_rows.get("row_count_matches", False),
                "runner_actual_row_count": feature_rows.get("runner_actual_row_count"),
                "runner_row_count_matches": feature_rows.get("runner_row_count_matches"),
                "feature_set_mismatch_count": feature_rows.get("feature_set_mismatch_count", 0),
                "split_counts": as_dict(feature_rows.get("split_counts")),
                "label_counts": as_dict(feature_rows.get("label_counts")),
                "risk_type_counts": as_dict(feature_rows.get("risk_type_counts")),
                "candidate_type_counts": as_dict(feature_rows.get("candidate_type_counts")),
                "source_status_counts": as_dict(feature_rows.get("source_status_counts")),
                "synthetic_rows": feature_rows.get("synthetic_rows", 0),
                "synthetic_allowed_for_eval": feature_rows.get("synthetic_allowed_for_eval", False),
            },
            "checks": {
                "feature_manifest_ready": checks.get("feature_manifest_ready", False),
                "runner_dry_run_ready": checks.get("runner_dry_run_ready", False),
                "feature_rows_readable": checks.get("feature_rows_readable", False),
                "row_count_matches": checks.get("row_count_matches", False),
                "required_row_fields": checks.get("required_row_fields"),
                "missing_row_fields": as_dict(checks.get("missing_row_fields")),
                "target_leakage_guard": checks.get("target_leakage_guard"),
                "target_leakage_violations": as_dict(checks.get("target_leakage_violations")),
                "synthetic_row_policy": checks.get("synthetic_row_policy"),
            },
            "metrics": {
                "scope": metrics.get("scope"),
                "measured_from_rows": metrics.get("measured_from_rows", False),
                "classification": {
                    "baselines": compact_training_baselines(as_list(classification.get("baselines"))),
                    "product_performance_claim": classification.get("product_performance_claim", False),
                    "release_metric": classification.get("release_metric", False),
                },
                "operations": metrics.get("operations"),
                "footprint": metrics.get("footprint"),
                "power": metrics.get("power"),
            },
            "gates": {
                "baseline_evaluation": gates.get("baseline_evaluation"),
                "model_training": gates.get("model_training"),
                "model_artifact": gates.get("model_artifact"),
                "model_card": gates.get("model_card"),
                "training_server": gates.get("training_server"),
                "model_registry": gates.get("model_registry"),
                "device_deployment": gates.get("device_deployment"),
                "release_claim": gates.get("release_claim"),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def compact_source_refs(items: Mapping[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for key, value in items.items():
        ref = as_dict(value)
        refs[key] = compact_dict(
            {
                "ref": ref.get("ref"),
                "sha256": ref.get("sha256"),
                "bytes": ref.get("bytes"),
                "content_copied": ref.get("content_copied", False),
            }
        )
    return refs


def training_handoff_bundle_unavailable(reason: str = "no_training_handoff_bundle") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "dataset": {},
        "training_run_preflight": {},
        "feature_manifest": {},
        "feature_rows": {"row_count": 0, "content_copied": False, "raw_rows_exposed": False},
        "runner_dry_run": {},
        "baseline_eval": {},
        "checks": {},
        "training_server": {"integration": "not_configured"},
        "gates": {"training_handoff": "not_available"},
        "blockers": [reason],
        "next_step": "Run scripts/build_training_handoff_bundle.py after TRAIN-006 baseline eval is ready.",
    }


def latest_training_handoff_bundle_path(root: Path = DEFAULT_TRAINING_HANDOFF_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_handoff_bundle.json"])


def load_latest_training_handoff_bundle(root: Path = DEFAULT_TRAINING_HANDOFF_REPORTS) -> dict[str, Any]:
    path = latest_training_handoff_bundle_path(root)
    if path is None:
        return training_handoff_bundle_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_handoff_bundle_unavailable("training_handoff_bundle_unreadable")
    dataset = as_dict(report.get("dataset"))
    preflight = as_dict(report.get("training_run_preflight"))
    feature_manifest = as_dict(report.get("feature_manifest"))
    feature_rows = as_dict(report.get("feature_rows"))
    runner = as_dict(report.get("runner_dry_run"))
    baseline = as_dict(report.get("baseline_eval"))
    checks = as_dict(report.get("checks"))
    training_server = as_dict(report.get("training_server"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "handoff_id": report.get("handoff_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "source_refs": compact_source_refs(as_dict(report.get("source_refs"))),
            "dataset": {
                "dataset_id": dataset.get("dataset_id"),
                "status": dataset.get("status"),
                "eligible_records": dataset.get("eligible_records", 0),
                "split_counts": as_dict(dataset.get("split_counts")),
            },
            "training_run_preflight": {
                "run_id": preflight.get("run_id"),
                "status": preflight.get("status"),
                "runner_ready": preflight.get("runner_ready", False),
            },
            "feature_manifest": {
                "feature_set_id": feature_manifest.get("feature_set_id"),
                "status": feature_manifest.get("status"),
                "row_count": feature_manifest.get("row_count", 0),
                "feature_scope": feature_manifest.get("feature_scope"),
                "target_separated_from_features": feature_manifest.get("target_separated_from_features", False),
            },
            "feature_rows": {
                "row_count": feature_rows.get("row_count", 0),
                "content_copied": feature_rows.get("content_copied", False),
                "raw_rows_exposed": feature_rows.get("raw_rows_exposed", False),
            },
            "runner_dry_run": {
                "run_id": runner.get("run_id"),
                "status": runner.get("status"),
                "runner_input_gate": runner.get("runner_input_gate"),
            },
            "baseline_eval": {
                "eval_id": baseline.get("eval_id"),
                "status": baseline.get("status"),
                "metric_scope": baseline.get("metric_scope"),
                "product_performance_claim": baseline.get("product_performance_claim", False),
            },
            "checks": {
                "source_ids_match": checks.get("source_ids_match", False),
                "feature_row_count_matches": checks.get("feature_row_count_matches", False),
                "synthetic_input_seen": checks.get("synthetic_input_seen", False),
                "synthetic_policy": checks.get("synthetic_policy"),
            },
            "training_server": {
                "integration": training_server.get("integration", "not_configured"),
                "endpoint": None,
                "bundle_ready_for_future_runner": training_server.get("bundle_ready_for_future_runner", False),
                "dry_run_only": training_server.get("dry_run_only", False),
                "next_step": training_server.get("next_step"),
            },
            "gates": {
                "training_handoff": gates.get("training_handoff"),
                "model_training": gates.get("model_training"),
                "model_artifact": gates.get("model_artifact"),
                "model_card": gates.get("model_card"),
                "training_server": gates.get("training_server"),
                "model_registry": gates.get("model_registry"),
                "device_deployment": gates.get("device_deployment"),
                "release_claim": gates.get("release_claim"),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def training_job_plan_unavailable(reason: str = "no_training_job_plan") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "source_handoff": {},
        "dataset": {},
        "feature_input": {"row_count": 0, "row_contents_copied": False, "raw_rows_exposed": False},
        "model_plan": {},
        "runner_plan": {"training_server_integration": "not_configured", "training_server_endpoint": None},
        "metrics_plan": {},
        "checks": {},
        "gates": {"training_job": "not_available"},
        "blockers": [reason],
        "next_step": "Run scripts/create_training_job_plan.py after TRAIN-007 handoff bundle is ready.",
    }


def latest_training_job_plan_path(root: Path = DEFAULT_TRAINING_JOB_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/training_job_plan.json"])


def load_latest_training_job_plan(root: Path = DEFAULT_TRAINING_JOB_REPORTS) -> dict[str, Any]:
    path = latest_training_job_plan_path(root)
    if path is None:
        return training_job_plan_unavailable()
    report = load_json_report(path)
    if report is None:
        return training_job_plan_unavailable("training_job_plan_unreadable")
    source_handoff = as_dict(report.get("source_handoff"))
    source_ref = as_dict(source_handoff.get("ref"))
    feature_input = as_dict(report.get("feature_input"))
    model_plan = as_dict(report.get("model_plan"))
    runner_plan = as_dict(report.get("runner_plan"))
    checks = as_dict(report.get("checks"))
    gates = as_dict(report.get("gates"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "job_id": report.get("job_id"),
            "created_at": report.get("created_at") or report_file_time(path),
            "source_handoff": {
                "handoff_id": source_handoff.get("handoff_id"),
                "status": source_handoff.get("status"),
                "ref": compact_dict(
                    {
                        "ref": source_ref.get("ref"),
                        "sha256": source_ref.get("sha256"),
                        "bytes": source_ref.get("bytes"),
                        "content_copied": source_ref.get("content_copied", False),
                    }
                ),
            },
            "dataset": as_dict(report.get("dataset")),
            "feature_input": {
                "feature_set_id": feature_input.get("feature_set_id"),
                "feature_manifest_status": feature_input.get("feature_manifest_status"),
                "feature_scope": feature_input.get("feature_scope"),
                "row_count": feature_input.get("row_count", 0),
                "row_contents_copied": feature_input.get("row_contents_copied", False),
                "raw_rows_exposed": feature_input.get("raw_rows_exposed", False),
                "target_separated_from_features": feature_input.get("target_separated_from_features", False),
            },
            "model_plan": {
                "model_track": model_plan.get("model_track"),
                "candidate_model": model_plan.get("candidate_model"),
                "baseline_model": model_plan.get("baseline_model"),
                "task_type": model_plan.get("task_type"),
                "baseline_eval_id": model_plan.get("baseline_eval_id"),
                "baseline_metric_scope": model_plan.get("baseline_metric_scope"),
                "product_performance_claim": model_plan.get("product_performance_claim", False),
            },
            "runner_plan": {
                "runner_profile": runner_plan.get("runner_profile"),
                "queue_state": runner_plan.get("queue_state"),
                "training_server_integration": runner_plan.get("training_server_integration", "not_configured"),
                "training_server_endpoint": None,
                "bundle_ready_for_future_runner": runner_plan.get("bundle_ready_for_future_runner", False),
                "dry_run_only": runner_plan.get("dry_run_only", False),
                "uses_feature_row_refs_only": runner_plan.get("uses_feature_row_refs_only", True),
            },
            "metrics_plan": as_dict(report.get("metrics_plan")),
            "checks": {
                "handoff_ready": checks.get("handoff_ready", False),
                "handoff_gate": checks.get("handoff_gate"),
                "synthetic_input_seen": checks.get("synthetic_input_seen", False),
                "synthetic_policy": checks.get("synthetic_policy"),
                "row_contents_copied": checks.get("row_contents_copied", False),
                "private_endpoint_exposed": checks.get("private_endpoint_exposed", False),
            },
            "gates": {
                "training_job": gates.get("training_job"),
                "model_training": gates.get("model_training"),
                "model_artifact": gates.get("model_artifact"),
                "model_card": gates.get("model_card"),
                "training_server": gates.get("training_server"),
                "model_registry": gates.get("model_registry"),
                "device_deployment": gates.get("device_deployment"),
                "release_claim": gates.get("release_claim"),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def synthetic_training_chain_unavailable(reason: str = "no_synthetic_training_chain") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "synthetic_only": True,
        "counts": {"recordings": 0, "reviewed_records": 0, "review_failures": 0, "feature_rows": 0},
        "components": {},
        "scope": {
            "hardware_contacted": False,
            "message_hub_contacted": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "release_claim_allowed": False,
        },
        "blockers": [reason],
        "next_step": "Run scripts/run_synthetic_training_chain.py for a no-hardware DATA/TRAIN smoke.",
    }


def latest_synthetic_training_chain_path(root: Path = DEFAULT_SYNTHETIC_TRAINING_CHAIN_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/synthetic_training_chain.json"])


def bounded_component_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    ref = as_dict(value)
    return compact_dict(
        {
            "ref": ref.get("ref"),
            "content_copied": ref.get("content_copied", False),
        }
    )


def compact_chain_step(step: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "status": step.get("status"),
            "reason": step.get("reason"),
            "run_id": step.get("run_id"),
            "feature_set_id": step.get("feature_set_id"),
            "eval_id": step.get("eval_id"),
            "handoff_id": step.get("handoff_id"),
            "job_id": step.get("job_id"),
            "row_count": step.get("row_count"),
            "feature_scope": step.get("feature_scope"),
            "metric_scope": step.get("metric_scope"),
            "product_performance_claim": step.get("product_performance_claim"),
            "training_server": step.get("training_server"),
            "runner_profile": step.get("runner_profile"),
            "queue_state": step.get("queue_state"),
            "dry_run_only": step.get("dry_run_only"),
            "report": bounded_component_ref(step.get("report")),
        }
    )


def compact_pipeline_step(step: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "run_id": step.get("run_id"),
            "status": step.get("status"),
            "recordings_requested": step.get("recordings_requested"),
            "recordings_ingested": step.get("recordings_ingested"),
            "candidate_records": step.get("candidate_records"),
            "pending_review": step.get("pending_review"),
            "dataset_status": step.get("dataset_status"),
            "eligible_records": step.get("eligible_records"),
            "experiment_status": step.get("experiment_status"),
            "runner_ready": step.get("runner_ready"),
            "report": bounded_component_ref(step.get("report")),
        }
    )


def load_latest_synthetic_training_chain(root: Path = DEFAULT_SYNTHETIC_TRAINING_CHAIN_REPORTS) -> dict[str, Any]:
    path = latest_synthetic_training_chain_path(root)
    if path is None:
        return synthetic_training_chain_unavailable()
    report = load_json_report(path)
    if report is None:
        return synthetic_training_chain_unavailable("synthetic_training_chain_unreadable")
    components = as_dict(report.get("components"))
    synthetic = as_dict(components.get("synthetic_scenarios"))
    data_flywheel = as_dict(components.get("data_flywheel"))
    training = as_dict(components.get("training_chain"))
    training_components = as_dict(training.get("components"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "synthetic_only": report.get("synthetic_only", True),
            "scenarios": list(report.get("scenarios") or []),
            "counts": {
                "recordings": as_dict(report.get("counts")).get("recordings", 0),
                "reviewed_records": as_dict(report.get("counts")).get("reviewed_records", 0),
                "review_failures": as_dict(report.get("counts")).get("review_failures", 0),
                "feature_rows": as_dict(report.get("counts")).get("feature_rows", 0),
            },
            "components": {
                "synthetic_scenarios": {
                    "status": synthetic.get("status"),
                    "recordings": synthetic.get("recordings", 0),
                    "reviewed_records": synthetic.get("reviewed_records", 0),
                    "failed_reviews": synthetic.get("failed_reviews", 0),
                    "seed": synthetic.get("seed"),
                    "report": bounded_component_ref(synthetic.get("report")),
                },
                "data_flywheel": {
                    "initial": compact_pipeline_step(as_dict(data_flywheel.get("initial"))),
                    "reviewed": compact_pipeline_step(as_dict(data_flywheel.get("reviewed"))),
                },
                "training_chain": {
                    "status": training.get("status"),
                    "reason": training.get("reason"),
                    "synthetic_allowed_for_dry_run": training.get("synthetic_allowed_for_dry_run", True),
                    "preflight": compact_chain_step(as_dict(training_components.get("preflight"))),
                    "feature_manifest": compact_chain_step(as_dict(training_components.get("feature_manifest"))),
                    "runner_dry_run": compact_chain_step(as_dict(training_components.get("runner_dry_run"))),
                    "baseline_eval": compact_chain_step(as_dict(training_components.get("baseline_eval"))),
                    "handoff_bundle": compact_chain_step(as_dict(training_components.get("handoff_bundle"))),
                    "job_plan": compact_chain_step(as_dict(training_components.get("job_plan"))),
                    "next_step": training.get("next_step"),
                },
            },
            "scope": {
                "hardware_contacted": as_dict(report.get("scope")).get("hardware_contacted", False),
                "message_hub_contacted": as_dict(report.get("scope")).get("message_hub_contacted", False),
                "model_training_started": as_dict(report.get("scope")).get("model_training_started", False),
                "model_evaluation_real_world": as_dict(report.get("scope")).get("model_evaluation_real_world", False),
                "model_artifact_written": as_dict(report.get("scope")).get("model_artifact_written", False),
                "device_deployment_started": as_dict(report.get("scope")).get("device_deployment_started", False),
                "power_or_footprint_measured": as_dict(report.get("scope")).get("power_or_footprint_measured", False),
                "release_claim_allowed": as_dict(report.get("scope")).get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step") or training.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def d1_training_readiness_unavailable(reason: str = "no_d1_training_readiness") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "source_observation": {},
        "evidence_coverage": {},
        "readiness": {
            "ready_for_labeling_review": False,
            "ready_for_training_handoff": False,
            "training_allowed": False,
            "blockers": [reason],
        },
        "gates": {"training_readiness": "not_available"},
        "scope": {
            "sample_jsonl_read": False,
            "message_hub_contacted": False,
            "hardware_contacted": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "release_claim_allowed": False,
        },
        "next_step": "Run scripts/assess_d1_training_readiness.py after a D1 field-observation summary exists.",
    }


def latest_d1_training_readiness_path(root: Path = DEFAULT_D1_TRAINING_READINESS_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/d1_training_readiness.json"])


def compact_gate_statuses(gates: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (
        "field_observation",
        "transport",
        "freshness",
        "location_evidence",
        "sensor_quality",
        "privacy",
        "labels",
        "split_leakage",
        "model_training",
        "model_artifact",
        "release_claim",
    ):
        item = as_dict(gates.get(name))
        result[name] = compact_dict({"status": item.get("status"), "reason": item.get("reason")})
    return result


def load_latest_d1_training_readiness(root: Path = DEFAULT_D1_TRAINING_READINESS_REPORTS) -> dict[str, Any]:
    path = latest_d1_training_readiness_path(root)
    if path is None:
        return d1_training_readiness_unavailable()
    report = load_json_report(path)
    if report is None:
        return d1_training_readiness_unavailable("d1_training_readiness_unreadable")
    source = as_dict(report.get("source_observation"))
    coverage = as_dict(report.get("evidence_coverage"))
    capture = as_dict(coverage.get("capture"))
    transport = as_dict(coverage.get("transport"))
    location = as_dict(coverage.get("location"))
    sensors = as_dict(coverage.get("sensors"))
    readiness = as_dict(report.get("readiness"))
    scope = as_dict(report.get("scope"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "source_observation": {
                "run_id": source.get("run_id"),
                "source": source.get("source"),
                "status": source.get("status"),
                "result": source.get("result"),
                "device_id": source.get("device_id"),
                "sample_count": source.get("sample_count", 0),
                "successful_sample_count": source.get("successful_sample_count", 0),
                "latest_seq": source.get("latest_seq"),
                "max_freshness_s": source.get("max_freshness_s"),
                "last_location_upload_at": source.get("last_location_upload_at"),
                "report_path": source.get("report_path"),
                "status_path": source.get("status_path"),
                "samples_jsonl_read": source.get("samples_jsonl_read", False),
            },
            "evidence_coverage": {
                "capture": {
                    "sample_count": capture.get("sample_count", 0),
                    "successful_sample_count": capture.get("successful_sample_count", 0),
                    "fetch_error_count": capture.get("fetch_error_count", 0),
                    "ready_for_review": capture.get("ready_for_review", False),
                },
                "transport": {
                    "raw_post_success_delta": transport.get("raw_post_success_delta", 0),
                    "raw_post_failure_delta": transport.get("raw_post_failure_delta", 0),
                    "lte_registration_seen": transport.get("lte_registration_seen", False),
                    "pdp_active_seen": transport.get("pdp_active_seen", False),
                },
                "location": {
                    "coordinate_sample_count": location.get("coordinate_sample_count", 0),
                    "location_event_count_delta": location.get("location_event_count_delta", 0),
                    "map_modes": list(location.get("map_modes") or []),
                    "gnss_states": list(location.get("gnss_states") or []),
                    "gnss_fix_seen": location.get("gnss_fix_seen", False),
                    "coordinate_values_copied": location.get("coordinate_values_copied", False),
                    "accuracy_claimed": location.get("accuracy_claimed", False),
                },
                "sensors": {
                    "imu_evidence_statuses": list(sensors.get("imu_evidence_statuses") or []),
                    "power_evidence_statuses": list(sensors.get("power_evidence_statuses") or []),
                    "power_measured_seen": sensors.get("power_measured_seen", False),
                    "real_imu_seen": sensors.get("real_imu_seen", False),
                },
            },
            "readiness": {
                "ready_for_labeling_review": readiness.get("ready_for_labeling_review", False),
                "ready_for_training_handoff": readiness.get("ready_for_training_handoff", False),
                "training_allowed": readiness.get("training_allowed", False),
                "consent_status": readiness.get("consent_status"),
                "privacy_review": readiness.get("privacy_review"),
                "label_review_state": readiness.get("label_review_state"),
                "split_leakage_checked": readiness.get("split_leakage_checked", False),
                "quality_gaps": list(readiness.get("quality_gaps") or []),
                "blockers": list(readiness.get("blockers") or []),
            },
            "gates": compact_gate_statuses(as_dict(report.get("gates"))),
            "scope": {
                "sample_jsonl_read": scope.get("sample_jsonl_read", False),
                "message_hub_contacted": scope.get("message_hub_contacted", False),
                "hardware_contacted": scope.get("hardware_contacted", False),
                "training_samples_written": scope.get("training_samples_written", False),
                "model_training_started": scope.get("model_training_started", False),
                "model_artifact_written": scope.get("model_artifact_written", False),
                "location_accuracy_claimed": scope.get("location_accuracy_claimed", False),
                "battery_life_claimed": scope.get("battery_life_claimed", False),
                "release_claim_allowed": scope.get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def d1_labeling_intake_unavailable(reason: str = "no_d1_labeling_intake") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "intake_queue": {"available": False, "pending_items": 0, "items": []},
        "review_gates": {"labeling_intake": "not_available"},
        "scope": {
            "sample_jsonl_read": False,
            "hardware_contacted": False,
            "candidate_db_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "release_claim_allowed": False,
        },
        "next_step": "Run scripts/build_d1_labeling_intake.py after D1 training readiness is available.",
    }


def latest_d1_labeling_intake_path(root: Path = DEFAULT_D1_LABELING_INTAKE_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/d1_labeling_intake.json"])


def compact_d1_labeling_intake_items(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:5]:
        if not isinstance(item, dict):
            continue
        review_state = as_dict(item.get("review_state"))
        evidence = as_dict(item.get("evidence_summary"))
        result.append(
            compact_dict(
                {
                    "intake_id": item.get("intake_id"),
                    "source_run_id": item.get("source_run_id"),
                    "readiness_run_id": item.get("readiness_run_id"),
                    "device_id": item.get("device_id"),
                    "status": item.get("status"),
                    "training_allowed": item.get("training_allowed", False),
                    "candidate_record_written": item.get("candidate_record_written", False),
                    "review_state": {
                        "operator_label": review_state.get("operator_label"),
                        "privacy_review": review_state.get("privacy_review"),
                        "training_consent": review_state.get("training_consent"),
                        "split_plan": review_state.get("split_plan"),
                        "quality_gaps": list(review_state.get("quality_gaps") or []),
                    },
                    "evidence_summary": {
                        "samples": evidence.get("samples", 0),
                        "latest_seq": evidence.get("latest_seq"),
                        "raw_post_success_delta": evidence.get("raw_post_success_delta", 0),
                        "raw_post_failure_delta": evidence.get("raw_post_failure_delta", 0),
                        "coordinate_sample_count": evidence.get("coordinate_sample_count", 0),
                        "gnss_fix_seen": evidence.get("gnss_fix_seen", False),
                        "imu_evidence_statuses": list(evidence.get("imu_evidence_statuses") or []),
                        "power_evidence_statuses": list(evidence.get("power_evidence_statuses") or []),
                    },
                    "requested_actions": list(item.get("requested_actions") or []),
                    "available_decisions": list(item.get("available_decisions") or []),
                }
            )
        )
    return result


def load_latest_d1_labeling_intake(root: Path = DEFAULT_D1_LABELING_INTAKE_REPORTS) -> dict[str, Any]:
    path = latest_d1_labeling_intake_path(root)
    if path is None:
        return d1_labeling_intake_unavailable()
    report = load_json_report(path)
    if report is None:
        return d1_labeling_intake_unavailable("d1_labeling_intake_unreadable")
    source_readiness = as_dict(report.get("source_readiness"))
    source = as_dict(report.get("source_observation"))
    coverage = as_dict(report.get("evidence_coverage"))
    transport = as_dict(coverage.get("transport"))
    location = as_dict(coverage.get("location"))
    sensors = as_dict(coverage.get("sensors"))
    queue = as_dict(report.get("intake_queue"))
    labeling = as_dict(report.get("labeling_request"))
    scope = as_dict(report.get("scope"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "source_readiness": {
                "run_id": source_readiness.get("run_id"),
                "status": source_readiness.get("status"),
                "reason": source_readiness.get("reason"),
                "report_path": source_readiness.get("report_path"),
            },
            "source_observation": {
                "run_id": source.get("run_id"),
                "status": source.get("status"),
                "result": source.get("result"),
                "device_id": source.get("device_id"),
                "sample_count": source.get("sample_count", 0),
                "successful_sample_count": source.get("successful_sample_count", 0),
                "latest_seq": source.get("latest_seq"),
                "max_freshness_s": source.get("max_freshness_s"),
                "last_location_upload_at": source.get("last_location_upload_at"),
                "samples_jsonl_read": source.get("samples_jsonl_read", False),
                "coordinate_values_copied": source.get("coordinate_values_copied", False),
            },
            "evidence_coverage": {
                "transport": {
                    "raw_post_success_delta": transport.get("raw_post_success_delta", 0),
                    "raw_post_failure_delta": transport.get("raw_post_failure_delta", 0),
                    "lte_registration_seen": transport.get("lte_registration_seen", False),
                    "pdp_active_seen": transport.get("pdp_active_seen", False),
                },
                "location": {
                    "coordinate_sample_count": location.get("coordinate_sample_count", 0),
                    "location_event_count_delta": location.get("location_event_count_delta", 0),
                    "map_modes": list(location.get("map_modes") or []),
                    "gnss_states": list(location.get("gnss_states") or []),
                    "gnss_fix_seen": location.get("gnss_fix_seen", False),
                    "coordinate_values_copied": location.get("coordinate_values_copied", False),
                    "accuracy_claimed": location.get("accuracy_claimed", False),
                },
                "sensors": {
                    "imu_evidence_statuses": list(sensors.get("imu_evidence_statuses") or []),
                    "power_evidence_statuses": list(sensors.get("power_evidence_statuses") or []),
                    "power_measured_seen": sensors.get("power_measured_seen", False),
                    "real_imu_seen": sensors.get("real_imu_seen", False),
                },
            },
            "intake_queue": {
                "available": queue.get("available", False),
                "pending_items": queue.get("pending_items", 0),
                "next_queue": queue.get("next_queue"),
                "items": compact_d1_labeling_intake_items(queue.get("items")),
            },
            "labeling_request": {
                "taxonomy_version": labeling.get("taxonomy_version"),
                "requested_label_groups": list(labeling.get("requested_label_groups") or []),
                "free_text_policy": labeling.get("free_text_policy"),
                "exact_coordinates_visible": labeling.get("exact_coordinates_visible", False),
            },
            "review_gates": as_dict(report.get("review_gates")),
            "blockers": list(report.get("blockers") or []),
            "scope": {
                "training_readiness_report_read": scope.get("training_readiness_report_read", False),
                "sample_jsonl_read": scope.get("sample_jsonl_read", False),
                "hardware_contacted": scope.get("hardware_contacted", False),
                "commands_sent": scope.get("commands_sent", False),
                "firmware_changed": scope.get("firmware_changed", False),
                "candidate_db_written": scope.get("candidate_db_written", False),
                "training_samples_written": scope.get("training_samples_written", False),
                "model_training_started": scope.get("model_training_started", False),
                "model_artifact_written": scope.get("model_artifact_written", False),
                "exact_coordinates_copied": scope.get("exact_coordinates_copied", False),
                "release_claim_allowed": scope.get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def d1_labeling_queue_unavailable(reason: str = "no_d1_labeling_queue") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "queue": {"available": False, "pending_items": 0, "items": []},
        "review_gates": {"labeling_queue": "not_available"},
        "scope": {
            "labeling_intake_reports_read": False,
            "sample_jsonl_read": False,
            "hardware_contacted": False,
            "candidate_db_written": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "exact_coordinates_copied": False,
            "release_claim_allowed": False,
        },
        "next_step": "Run scripts/summarize_d1_labeling_queue.py after D1 labeling-intake summaries exist.",
    }


def latest_d1_labeling_queue_path(root: Path = DEFAULT_D1_LABELING_QUEUE_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/d1_labeling_queue.json"])


def compact_d1_labeling_queue_items(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:8]:
        if not isinstance(item, dict):
            continue
        review_state = as_dict(item.get("review_state"))
        evidence = as_dict(item.get("evidence_summary"))
        result.append(
            compact_dict(
                {
                    "queue_id": item.get("queue_id"),
                    "intake_id": item.get("intake_id"),
                    "source_run_id": item.get("source_run_id"),
                    "readiness_run_id": item.get("readiness_run_id"),
                    "device_id": item.get("device_id"),
                    "status": item.get("status"),
                    "training_allowed": False,
                    "candidate_record_written": False,
                    "review_state": {
                        "operator_label": review_state.get("operator_label"),
                        "privacy_review": review_state.get("privacy_review"),
                        "training_consent": review_state.get("training_consent"),
                        "split_plan": review_state.get("split_plan"),
                        "quality_gaps": list(review_state.get("quality_gaps") or []),
                    },
                    "evidence_summary": {
                        "samples": evidence.get("samples", 0),
                        "latest_seq": evidence.get("latest_seq"),
                        "raw_post_success_delta": evidence.get("raw_post_success_delta", 0),
                        "raw_post_failure_delta": evidence.get("raw_post_failure_delta", 0),
                        "coordinate_sample_count": evidence.get("coordinate_sample_count", 0),
                        "gnss_fix_seen": evidence.get("gnss_fix_seen", False),
                        "imu_evidence_statuses": list(evidence.get("imu_evidence_statuses") or []),
                        "power_evidence_statuses": list(evidence.get("power_evidence_statuses") or []),
                    },
                    "requested_actions": list(item.get("requested_actions") or []),
                    "available_decisions": list(item.get("available_decisions") or []),
                    "intake_report_path": item.get("intake_report_path") or item.get("source_report_path"),
                }
            )
        )
    return result


def compact_d1_labeling_queue_reports(reports: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for report in list(reports or [])[:8]:
        if not isinstance(report, dict):
            continue
        result.append(
            compact_dict(
                {
                    "run_id": report.get("run_id"),
                    "status": report.get("status"),
                    "reason": report.get("reason"),
                    "pending_items": report.get("pending_items", 0),
                    "report_path": report.get("report_path"),
                    "markdown_path": report.get("markdown_path") or report.get("markdown_report_path"),
                    "training_allowed": False,
                    "candidate_record_written": False,
                    "blockers": list(report.get("blockers") or []),
                }
            )
        )
    return result


def load_latest_d1_labeling_queue(root: Path = DEFAULT_D1_LABELING_QUEUE_REPORTS) -> dict[str, Any]:
    path = latest_d1_labeling_queue_path(root)
    if path is None:
        return d1_labeling_queue_unavailable()
    report = load_json_report(path)
    if report is None:
        return d1_labeling_queue_unavailable("d1_labeling_queue_unreadable")
    summary = as_dict(report.get("summary"))
    queue = as_dict(report.get("queue"))
    scope = as_dict(report.get("scope"))
    pending_items = summary.get("pending_items", summary.get("pending_item_count", 0))
    compact_items = compact_d1_labeling_queue_items(queue.get("items"))
    compact_reports = compact_d1_labeling_queue_reports(report.get("intake_reports"))
    needs_operator_label = summary.get(
        "needs_operator_label",
        len([item for item in compact_items if as_dict(item.get("review_state")).get("operator_label") == "missing"]),
    )
    needs_privacy_review = summary.get(
        "needs_privacy_review",
        len([item for item in compact_items if as_dict(item.get("review_state")).get("privacy_review") == "required"]),
    )
    needs_training_consent = summary.get(
        "needs_training_consent",
        len(
            [
                item
                for item in compact_items
                if as_dict(item.get("review_state")).get("training_consent") == "not_reviewed"
            ]
        ),
    )
    needs_split_plan = summary.get(
        "needs_split_plan",
        len([item for item in compact_items if as_dict(item.get("review_state")).get("split_plan") == "missing"]),
    )
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "summary": {
                "intake_report_count": summary.get("intake_report_count", 0),
                "pending_items": pending_items,
                "needs_operator_label": needs_operator_label,
                "needs_privacy_review": needs_privacy_review,
                "needs_training_consent": needs_training_consent,
                "needs_split_plan": needs_split_plan,
                "not_ready_reports": summary.get("not_ready_reports", summary.get("not_ready_report_count", 0)),
                "error_count": summary.get("error_count", 0),
            },
            "queue": {
                "available": queue.get("available", False),
                "pending_items": queue.get("pending_items", pending_items),
                "next_queue": queue.get("next_queue"),
                "items": compact_items,
            },
            "intake_reports": compact_reports,
            "review_gates": as_dict(report.get("review_gates")),
            "blockers": list(report.get("blockers") or []),
            "scope": {
                "labeling_intake_reports_read": scope.get(
                    "labeling_intake_reports_read", scope.get("intake_summaries_read", False)
                ),
                "sample_jsonl_read": scope.get("sample_jsonl_read", False),
                "hardware_contacted": scope.get("hardware_contacted", False),
                "commands_sent": scope.get("commands_sent", False),
                "firmware_changed": scope.get("firmware_changed", False),
                "candidate_db_written": scope.get("candidate_db_written", False),
                "training_samples_written": scope.get("training_samples_written", False),
                "model_training_started": scope.get("model_training_started", False),
                "model_artifact_written": scope.get("model_artifact_written", False),
                "exact_coordinates_copied": scope.get("exact_coordinates_copied", False),
                "release_claim_allowed": scope.get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def d1_labeling_review_packet_unavailable(reason: str = "no_d1_labeling_review_packet") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "source_queue": {"available": False},
        "review_packet": {"status": "not_available", "items": []},
        "review_gates": {"candidate_store": "not_written", "model_training": "not_run"},
        "scope": {
            "labeling_queue_summary_read": False,
            "sample_jsonl_read": False,
            "payload_bytes_copied": False,
            "exact_coordinates_copied": False,
            "feature_rows_copied": False,
            "target_labels_written": False,
            "candidate_db_written": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "release_claim_allowed": False,
        },
        "next_step": "Run scripts/build_d1_labeling_review_packet.py after a D1 labeling queue exists.",
    }


def latest_d1_labeling_review_packet_path(root: Path = DEFAULT_D1_LABELING_REVIEW_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/d1_labeling_review_packet.json"])


def compact_d1_labeling_review_slots(slots: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(slots, dict):
        return result
    for key, slot in slots.items():
        if not isinstance(slot, dict):
            continue
        result[str(key)] = compact_dict(
            {
                "required": slot.get("required", True),
                "current": slot.get("current"),
                "selected": slot.get("selected"),
                "allowed_values": list(slot.get("allowed_values") or []),
            }
        )
    return result


def compact_d1_labeling_review_items(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:8]:
        if not isinstance(item, dict):
            continue
        review_state = as_dict(item.get("current_review_state"))
        evidence = as_dict(item.get("evidence_summary"))
        result.append(
            compact_dict(
                {
                    "packet_item_id": item.get("packet_item_id"),
                    "intake_id": item.get("intake_id"),
                    "source_run_id": item.get("source_run_id"),
                    "readiness_run_id": item.get("readiness_run_id"),
                    "device_id": item.get("device_id"),
                    "queue_status": item.get("queue_status"),
                    "current_review_state": {
                        "operator_label": review_state.get("operator_label"),
                        "privacy_review": review_state.get("privacy_review"),
                        "training_consent": review_state.get("training_consent"),
                        "split_plan": review_state.get("split_plan"),
                        "quality_gaps": list(review_state.get("quality_gaps") or []),
                    },
                    "evidence_summary": {
                        "samples": evidence.get("samples", 0),
                        "latest_seq": evidence.get("latest_seq"),
                        "raw_post_success_delta": evidence.get("raw_post_success_delta", 0),
                        "raw_post_failure_delta": evidence.get("raw_post_failure_delta", 0),
                        "coordinate_sample_count": evidence.get("coordinate_sample_count", 0),
                        "gnss_fix_seen": evidence.get("gnss_fix_seen", False),
                        "imu_evidence_statuses": list(evidence.get("imu_evidence_statuses") or []),
                        "power_evidence_statuses": list(evidence.get("power_evidence_statuses") or []),
                    },
                    "requested_actions": list(item.get("requested_actions") or []),
                    "available_decisions": list(item.get("available_decisions") or []),
                    "decision_slots": compact_d1_labeling_review_slots(item.get("decision_slots")),
                    "candidate_record_written": False,
                    "training_allowed": False,
                    "candidate_write_gate": item.get("candidate_write_gate"),
                }
            )
        )
    return result


def load_latest_d1_labeling_review_packet(root: Path = DEFAULT_D1_LABELING_REVIEW_REPORTS) -> dict[str, Any]:
    path = latest_d1_labeling_review_packet_path(root)
    if path is None:
        return d1_labeling_review_packet_unavailable()
    report = load_json_report(path)
    if report is None:
        return d1_labeling_review_packet_unavailable("d1_labeling_review_packet_unreadable")
    summary = as_dict(report.get("summary"))
    review_packet = as_dict(report.get("review_packet"))
    scope = as_dict(report.get("scope"))
    compact_items = compact_d1_labeling_review_items(review_packet.get("items"))
    source_queue = as_dict(report.get("source_queue"))
    review_items = summary.get("review_packet_items", len(compact_items))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "source_queue": {
                "available": source_queue.get("available", False),
                "run_id": source_queue.get("run_id"),
                "status": source_queue.get("status"),
                "report_path": source_queue.get("report_path"),
                "pending_item_count": source_queue.get("pending_item_count", 0),
                "intake_report_count": source_queue.get("intake_report_count", 0),
            },
            "summary": {
                "queue_pending_items": summary.get("queue_pending_items", 0),
                "review_packet_items": review_items,
                "needs_operator_label": summary.get("needs_operator_label", 0),
                "needs_privacy_review": summary.get("needs_privacy_review", 0),
                "needs_training_consent": summary.get("needs_training_consent", 0),
                "needs_split_plan": summary.get("needs_split_plan", 0),
                "candidate_record_written_count": 0,
                "training_allowed_count": 0,
            },
            "review_packet": {
                "status": review_packet.get("status", "unknown"),
                "items": compact_items,
                "decision_schema": as_dict(review_packet.get("decision_schema")),
                "apply_policy": review_packet.get("apply_policy"),
            },
            "review_gates": {
                "candidate_store": "not_written",
                "model_training": "not_run",
                "release_claim": "not_allowed",
            },
            "scope": {
                "labeling_queue_summary_read": scope.get("labeling_queue_summary_read", False),
                "sample_jsonl_read": scope.get("sample_jsonl_read", False),
                "payload_bytes_copied": scope.get("payload_bytes_copied", False),
                "exact_coordinates_copied": scope.get("exact_coordinates_copied", False),
                "feature_rows_copied": scope.get("feature_rows_copied", False),
                "target_labels_written": scope.get("target_labels_written", False),
                "candidate_db_written": scope.get("candidate_db_written", False),
                "training_samples_written": scope.get("training_samples_written", False),
                "model_training_started": scope.get("model_training_started", False),
                "model_artifact_written": scope.get("model_artifact_written", False),
                "release_claim_allowed": scope.get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def d1_labeling_decision_template_unavailable(reason: str = "no_d1_labeling_decision_template") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "reason": reason,
        "serves_demo": "D5",
        "source_review_packet": {"available": False},
        "decision_template": {"status": "not_available", "items": []},
        "review_gates": {"candidate_store": "not_written", "model_training": "not_run"},
        "scope": {
            "review_packet_summary_read": False,
            "sample_jsonl_read": False,
            "payload_bytes_copied": False,
            "exact_coordinates_copied": False,
            "feature_rows_copied": False,
            "target_labels_written": False,
            "candidate_db_written": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "release_claim_allowed": False,
        },
        "next_step": "Run scripts/build_d1_labeling_decision_template.py after a D1 labeling review packet exists.",
    }


def latest_d1_labeling_decision_template_path(root: Path = DEFAULT_D1_LABELING_DECISION_REPORTS) -> Path | None:
    return latest_report_path(root, ["**/d1_labeling_decision_template.json"])


def compact_d1_labeling_decision_fields(fields: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(fields, dict):
        return result
    for key, field in fields.items():
        if not isinstance(field, dict):
            continue
        result[str(key)] = compact_dict(
            {
                "required": field.get("required", True),
                "current": field.get("current"),
                "selected": field.get("selected"),
                "allowed_values": list(field.get("allowed_values") or []),
            }
        )
    return result


def compact_d1_labeling_decision_items(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:8]:
        if not isinstance(item, dict):
            continue
        review_state = as_dict(item.get("current_review_state"))
        evidence = as_dict(item.get("evidence_summary"))
        result.append(
            compact_dict(
                {
                    "packet_item_id": item.get("packet_item_id"),
                    "intake_id": item.get("intake_id"),
                    "source_run_id": item.get("source_run_id"),
                    "readiness_run_id": item.get("readiness_run_id"),
                    "device_id": item.get("device_id"),
                    "queue_status": item.get("queue_status"),
                    "current_review_state": {
                        "operator_label": review_state.get("operator_label"),
                        "privacy_review": review_state.get("privacy_review"),
                        "training_consent": review_state.get("training_consent"),
                        "split_plan": review_state.get("split_plan"),
                        "quality_gaps": list(review_state.get("quality_gaps") or []),
                    },
                    "evidence_summary": {
                        "samples": evidence.get("samples", 0),
                        "latest_seq": evidence.get("latest_seq"),
                        "raw_post_success_delta": evidence.get("raw_post_success_delta", 0),
                        "raw_post_failure_delta": evidence.get("raw_post_failure_delta", 0),
                        "coordinate_sample_count": evidence.get("coordinate_sample_count", 0),
                        "gnss_fix_seen": evidence.get("gnss_fix_seen", False),
                        "imu_evidence_statuses": list(evidence.get("imu_evidence_statuses") or []),
                        "power_evidence_statuses": list(evidence.get("power_evidence_statuses") or []),
                    },
                    "decision_fields": compact_d1_labeling_decision_fields(item.get("decision_fields")),
                    "requested_actions": list(item.get("requested_actions") or []),
                    "available_decisions": list(item.get("available_decisions") or []),
                    "validation_state": item.get("validation_state"),
                    "candidate_record_written": False,
                    "training_allowed": False,
                }
            )
        )
    return result


def load_latest_d1_labeling_decision_template(root: Path = DEFAULT_D1_LABELING_DECISION_REPORTS) -> dict[str, Any]:
    path = latest_d1_labeling_decision_template_path(root)
    if path is None:
        return d1_labeling_decision_template_unavailable()
    report = load_json_report(path)
    if report is None:
        return d1_labeling_decision_template_unavailable("d1_labeling_decision_template_unreadable")
    summary = as_dict(report.get("summary"))
    template = as_dict(report.get("decision_template"))
    scope = as_dict(report.get("scope"))
    source_review_packet = as_dict(report.get("source_review_packet"))
    compact_items = compact_d1_labeling_decision_items(template.get("items"))
    markdown_candidate = path.with_suffix(".md")
    markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": report.get("status", "unknown"),
            "reason": report.get("reason"),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at") or report_file_time(path),
            "serves_demo": report.get("serves_demo", "D5"),
            "source_review_packet": {
                "available": source_review_packet.get("available", False),
                "run_id": source_review_packet.get("run_id"),
                "status": source_review_packet.get("status"),
                "report_path": source_review_packet.get("report_path"),
                "review_packet_items": source_review_packet.get("review_packet_items", 0),
            },
            "summary": {
                "template_items": summary.get("template_items", len(compact_items)),
                "review_packet_items": summary.get("review_packet_items", len(compact_items)),
                "queue_pending_items": summary.get("queue_pending_items", 0),
                "required_decision_fields": summary.get("required_decision_fields", 0),
                "selected_decision_fields": summary.get("selected_decision_fields", 0),
                "items_ready_for_validation": summary.get("items_ready_for_validation", 0),
                "candidate_record_written_count": 0,
                "training_allowed_count": 0,
                "ready_for_candidate_promotion": False,
            },
            "decision_template": {
                "status": template.get("status", "unknown"),
                "items": compact_items,
                "decision_schema": as_dict(template.get("decision_schema")),
                "apply_policy": template.get("apply_policy"),
            },
            "review_gates": {
                "candidate_store": "not_written",
                "model_training": "not_run",
                "release_claim": "not_allowed",
            },
            "scope": {
                "review_packet_summary_read": scope.get("review_packet_summary_read", False),
                "sample_jsonl_read": scope.get("sample_jsonl_read", False),
                "payload_bytes_copied": scope.get("payload_bytes_copied", False),
                "exact_coordinates_copied": scope.get("exact_coordinates_copied", False),
                "feature_rows_copied": scope.get("feature_rows_copied", False),
                "target_labels_written": scope.get("target_labels_written", False),
                "candidate_db_written": scope.get("candidate_db_written", False),
                "training_samples_written": scope.get("training_samples_written", False),
                "model_training_started": scope.get("model_training_started", False),
                "model_artifact_written": scope.get("model_artifact_written", False),
                "release_claim_allowed": scope.get("release_claim_allowed", False),
            },
            "next_step": report.get("next_step"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "non_claims": report.get("non_claims"),
        }
    )


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def key_release_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {}
    return compact_dict(
        {
            "release_id": manifest.get("release_id"),
            "release_name": manifest.get("release_name"),
            "release_version": manifest.get("release_version"),
            "status": manifest.get("status"),
            "release_date": manifest.get("release_date"),
            "firmware_version": manifest.get("firmware_version"),
            "firmware_test_run_id": manifest.get("firmware_test_run_id"),
            "manifest_path": manifest.get("_manifest_path"),
        }
    )


def latest_released_manifest(manifests: list[dict[str, Any]]) -> dict[str, Any] | None:
    released = [item for item in manifests if item.get("status") == "released"]
    if released:
        return released[-1]
    return manifests[-1] if manifests else None


def resolve_key_release_context(
    test_run_id: Any,
    fw_version: Any,
    *,
    manifests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest_list = manifests if manifests is not None else load_key_release_manifests()
    test_run_text = str(test_run_id or "")
    fw_text = str(fw_version or "")
    for manifest in manifest_list:
        if test_run_text and str(manifest.get("firmware_test_run_id") or "") == test_run_text:
            return {
                "match": "firmware_test_run_id",
                **key_release_summary(manifest),
            }
    for manifest in manifest_list:
        if fw_text and str(manifest.get("firmware_version") or "") == fw_text:
            return {
                "match": "firmware_version",
                **key_release_summary(manifest),
            }
    baseline = key_release_summary(latest_released_manifest(manifest_list))
    return {
        "release_id": "unreleased",
        "release_name": "Unreleased run",
        "release_version": None,
        "status": "unreleased_run" if manifest_list else "unknown",
        "match": "none" if manifest_list else "manifest_unavailable",
        "baseline": baseline,
    }


def newest_record(items: list[dict[str, Any]], *timestamp_keys: str) -> dict[str, Any]:
    newest: dict[str, Any] = {}
    newest_ts: datetime | None = None
    for index, item in enumerate(items):
        timestamp_value = first_known(*(item.get(key) for key in timestamp_keys))
        parsed = parse_iso_timestamp(timestamp_value)
        if parsed is None:
            parsed = datetime.fromtimestamp(index, tz=timezone.utc)
        if newest_ts is None or parsed >= newest_ts:
            newest = item
            newest_ts = parsed
    return newest


def command_test_run_id(command: dict[str, Any]) -> Any:
    ack = as_dict(command.get("ack"))
    return first_known(
        command.get("test_run_id"),
        dict_value(command, "payload", "test_run_id"),
        ack.get("test_run_id"),
        dict_value(ack, "payload", "test_run_id"),
    )


def command_matches_test_run(command: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    test_run_text = str(test_run_id)
    ack = as_dict(command.get("ack"))
    candidates = [
        command.get("test_run_id"),
        dict_value(command, "payload", "test_run_id"),
        ack.get("test_run_id"),
        dict_value(ack, "payload", "test_run_id"),
    ]
    return test_run_text in {str(value) for value in candidates if value not in (None, "")}


def raw_frame_test_run_id(raw_frame: dict[str, Any]) -> Any:
    derived = as_dict(dict_value(raw_frame, "parse_result", "derived_message"))
    return first_known(raw_frame.get("test_run_id"), derived.get("test_run_id"))


def raw_frame_matches_test_run(raw_frame: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    return str(raw_frame_test_run_id(raw_frame) or "") == str(test_run_id)


def message_matches_test_run(message: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    return str(message.get("test_run_id") or "") == str(test_run_id)


def raw_frame_parse_status(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "parse_result", "status"), raw_frame.get("parse_status"), "unknown"))


def raw_frame_derived_type(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "parse_result", "derived_message_type"), raw_frame.get("derived_message_type"), "unknown"))


def raw_frame_type(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "framing", "frame_type"), raw_frame.get("frame_type"), "unknown"))


def raw_frame_problem(raw_frames: list[dict[str, Any]]) -> dict[str, Any]:
    problems = [
        raw_frame
        for raw_frame in raw_frames
        if raw_frame_parse_status(raw_frame) not in {"ok", "not_attempted", "unknown"}
    ]
    return newest_record(problems, "server_received_at") if problems else {}


def unique_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in (None, "", "none", "unknown"):
            continue
        text = str(value)
        if text not in result:
            result.append(text)
    return result


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def confidence_bucket(value: Any) -> str:
    score = as_number(value)
    if score is None:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def eale_source_status(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    return text or "unknown"


def eale_evidence_status(payload: dict[str, Any], source_status: str, present: bool) -> str:
    explicit = str(payload.get("evidence_status") or "").strip().lower()
    if explicit:
        return explicit
    if not present:
        return "missing"
    if source_status in {"disabled", "missing", "unknown"}:
        return "missing"
    if source_status in {"failed", "error"}:
        return "failed"
    if source_status in {"partial"}:
        return "partial"
    return "ok"


def eale_source_evidence(
    source: str,
    payload: dict[str, Any],
    *,
    present: bool | None = None,
    source_status: Any = None,
    server_received_at: Any = None,
    raw_frame_refs: list[dict[str, Any]] | None = None,
    derived_event_refs: list[dict[str, Any]] | None = None,
    privacy_class: str = "engineering",
) -> dict[str, Any]:
    status = eale_source_status(first_known(source_status, payload.get("source_status")))
    has_payload = present if present is not None else bool(payload)
    evidence_status = eale_evidence_status(payload, status, has_payload)
    return {
        "source": source,
        "present": bool(has_payload),
        "source_status": status,
        "evidence_status": evidence_status,
        "server_received_at": server_received_at,
        "raw_frame_refs": raw_frame_refs or [],
        "derived_event_refs": derived_event_refs or [],
        "quality_flags": [],
        "privacy_class": privacy_class,
        "redaction_state": "hashed" if source == "wifi" else "none",
    }


def eale_raw_frame_ref(raw_frame: dict[str, Any]) -> dict[str, Any]:
    raw_payload = as_dict(raw_frame.get("raw_payload"))
    framing = as_dict(raw_frame.get("framing"))
    parse = as_dict(raw_frame.get("parse_result"))
    derived = as_dict(parse.get("derived_message"))
    return compact_dict(
        {
            "frame_id": raw_frame.get("frame_id"),
            "direction": raw_frame.get("direction"),
            "device_id": first_known(raw_frame.get("device_id"), derived.get("device_id")),
            "test_run_id": first_known(raw_frame.get("test_run_id"), derived.get("test_run_id")),
            "cmd_id": first_known(raw_frame.get("cmd_id"), derived.get("cmd_id"), derived.get("location_request_cmd_id")),
            "seq": first_known(raw_frame.get("seq"), derived.get("seq")),
            "fw_version": first_known(raw_frame.get("fw_version"), derived.get("fw_version")),
            "frame_type": raw_frame_type(raw_frame),
            "server_received_at": raw_frame.get("server_received_at"),
            "byte_len": raw_payload.get("byte_len"),
            "sha256": raw_payload.get("sha256"),
            "crc32": first_known(raw_payload.get("crc32"), framing.get("payload_crc32")),
            "parse_status": raw_frame_parse_status(raw_frame),
            "parser_version": parse.get("parser_version"),
            "derived_message_type": raw_frame_derived_type(raw_frame),
        }
    )


def eale_derived_event_ref(message: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "message_type": message.get("message_type"),
            "event_type": message.get("event_type"),
            "cmd_id": first_known(message.get("location_request_cmd_id"), message.get("cmd_id")),
            "frame_id": dict_value(message, "raw_frame", "frame_id"),
            "seq": message.get("seq"),
            "server_received_at": message.get("server_received_at"),
            "fw_version": message.get("fw_version"),
            "test_run_id": message.get("test_run_id"),
            "source": message.get("source"),
            "source_status": message.get("source_status"),
        }
    )


def eale_lineage_quality(raw_refs: list[dict[str, Any]], derived_refs: list[dict[str, Any]], anchor_cmd_id: Any, seq: Any) -> float:
    if raw_refs and derived_refs and anchor_cmd_id and seq is not None:
        return 1.0
    if derived_refs and anchor_cmd_id:
        return 0.7
    if raw_refs or derived_refs:
        return 0.4
    return 0.0


def eale_gnss_quality(report: dict[str, Any], lineage_quality: float, quality_flags: list[str]) -> tuple[float, float]:
    hdop = as_number(first_known(report.get("hdop"), dict_value(report, "gnss", "hdop")))
    satellites = as_number(first_known(report.get("satellites"), dict_value(report, "gnss", "satellites")))
    if hdop is None:
        hdop_score = 0.45
        quality_flags.append("gnss_hdop_missing")
    else:
        hdop_score = clamp((8.0 - hdop) / 7.0, 0.0, 1.0)
    if satellites is None:
        satellite_score = 0.45
        quality_flags.append("gnss_satellites_missing")
    else:
        satellite_score = clamp((satellites - 4.0) / 8.0, 0.0, 1.0)
    source_status = eale_source_status(report.get("source_status"))
    source_score = 1.0 if source_status in {"verified", "observed", "pc_side_verified"} else 0.5
    score = clamp(hdop_score * satellite_score * source_score * lineage_quality, 0.0, 1.0)
    radius = max(25.0, (hdop or 8.0) * 8.0)
    return round(score, 3), round(radius, 1)


def eale_latest_event(messages: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    matches = [
        message
        for message in messages
        if message.get("message_type") == "event" and message.get("event_type") == event_type
    ]
    return newest_record(matches, "server_received_at", "ts") if matches else {}


def eale_dataset_window_status(
    *,
    command: dict[str, Any],
    report: dict[str, Any],
    observation: dict[str, Any],
    raw_refs: list[dict[str, Any]],
    derived_refs: list[dict[str, Any]],
    failure_reason: Any,
    quality_flags: list[str],
) -> dict[str, Any]:
    has_location_command = command.get("cmd") == "request_location" or bool(first_known(report.get("location_request_cmd_id"), observation.get("location_request_cmd_id")))
    if report.get("fix") is True:
        sample_type = "known_place_calibration_window"
    elif failure_reason and str(failure_reason) not in {"none", "unknown"}:
        sample_type = "failure_window"
    elif has_location_command:
        sample_type = "location_request_window"
    else:
        sample_type = "passive_observation_window"

    blockers: list[str] = []
    warnings: list[str] = []
    if not raw_refs:
        warnings.append("missing_raw_frame_lineage")
    if not derived_refs:
        blockers.append("missing_derived_location_event")
    if command and command.get("status") == "pending":
        warnings.append("command_pending")
    if quality_flags:
        warnings.extend(quality_flags)
    status = "blocked" if blockers else ("candidate_with_warnings" if warnings else "candidate")
    return {
        "status": status,
        "sample_type": sample_type,
        "raw_frame_count": len(raw_refs),
        "derived_event_count": len(derived_refs),
        "training_allowed": False,
        "training_reason": "training_requires_explicit_privacy_and_label_policy",
        "blockers": unique_text(blockers),
        "warnings": unique_text(warnings),
    }


def build_eale_p0_location_belief(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    latest_observability: dict[str, Any],
    failure_summary: dict[str, Any],
) -> dict[str, Any]:
    report = eale_latest_event(messages, "location_report")
    observation = eale_latest_event(messages, "location_observation")
    anchor = observation or report
    command = newest_record(commands, "updated_at", "created_at") if commands else {}
    raw_refs = [eale_raw_frame_ref(raw_frame) for raw_frame in raw_frames]
    derived_refs = [eale_derived_event_ref(message) for message in messages if message.get("message_type") == "event" and message.get("event_type") in {"location_report", "location_observation"}]
    anchor_cmd_id = first_known(
        observation.get("location_request_cmd_id"),
        report.get("location_request_cmd_id"),
        command.get("cmd_id"),
    )
    anchor_seq = first_known(observation.get("seq"), report.get("seq"))
    lineage_quality = eale_lineage_quality(raw_refs, derived_refs, anchor_cmd_id, anchor_seq)
    location_memory = as_dict(latest_observability.get("location_memory"))

    gnss = as_dict(first_known(report.get("gnss"), {}))
    cell = as_dict(first_known(observation.get("cell"), report.get("cell")))
    lte = as_dict(first_known(observation.get("lte"), report.get("lte")))
    wifi = as_dict(first_known(observation.get("wifi"), report.get("wifi")))
    imu = as_dict(first_known(observation.get("imu"), report.get("imu")))
    power = as_dict(first_known(observation.get("power"), report.get("power")))
    transport = as_dict(first_known(observation.get("transport"), report.get("transport"), dict_value(command, "ack", "transport")))
    runtime = as_dict(first_known(observation.get("runtime"), report.get("runtime")))

    evidence = {
        "gnss": eale_source_evidence(
            "gnss",
            gnss or report,
            present=bool(report),
            source_status=report.get("source_status"),
            server_received_at=report.get("server_received_at"),
            raw_frame_refs=raw_refs,
            derived_event_refs=[ref for ref in derived_refs if ref.get("event_type") == "location_report"],
            privacy_class="private_location" if report.get("lat") is not None or report.get("lon") is not None else "engineering",
        ),
        "cell_lte": eale_source_evidence(
            "cell_lte",
            {**cell, **lte},
            present=bool(cell or lte),
            source_status=first_known(cell.get("source_status"), lte.get("source_status"), "observed" if cell or lte else None),
            server_received_at=observation.get("server_received_at"),
            raw_frame_refs=raw_refs,
            derived_event_refs=[ref for ref in derived_refs if ref.get("event_type") == "location_observation"],
        ),
        "wifi": eale_source_evidence("wifi", wifi, present=bool(wifi), server_received_at=observation.get("server_received_at")),
        "imu": eale_source_evidence("imu", imu, present=bool(imu), server_received_at=observation.get("server_received_at")),
        "power": eale_source_evidence("power", power, present=bool(power), server_received_at=observation.get("server_received_at")),
        "transport": eale_source_evidence("transport", transport, present=bool(transport), source_status=transport.get("type"), server_received_at=anchor.get("server_received_at")),
        "runtime": eale_source_evidence("runtime", runtime, present=bool(runtime), server_received_at=anchor.get("server_received_at")),
        "memory": eale_source_evidence("memory", location_memory, present=bool(location_memory), source_status=location_memory.get("state"), server_received_at=location_memory.get("updated_at")),
    }

    quality_flags: list[str] = []
    for name, payload in (("wifi", wifi), ("imu", imu), ("power", power)):
        source_status = eale_source_status(payload.get("source_status"))
        evidence_status = eale_evidence_status(payload, source_status, bool(payload))
        if evidence_status == "missing":
            quality_flags.append(f"{name}_{source_status if source_status != 'unknown' else 'missing'}")
        elif source_status in {"unverified", "mock"}:
            quality_flags.append(f"{name}_{source_status}")
        elif evidence_status in {"failed", "partial"}:
            quality_flags.append(f"{name}_{evidence_status}")
    if cell or lte:
        quality_flags.append("cell_lte_not_position_source")
    if lineage_quality < 1.0:
        quality_flags.append("partial_lineage")

    fix = first_known(report.get("fix"), gnss.get("fix"))
    source_status = eale_source_status(report.get("source_status"))
    failure_reason = failure_summary.get("reason") if failure_summary.get("state") != "ok" else None
    state = "Unknown"
    substate = "no_precise_fix"
    source: list[str] = []
    radius_m: float | None = None
    confidence: float | None = None
    reason = "no_location_evidence"

    if fix is True and report.get("lat") is not None and report.get("lon") is not None:
        if source_status in {"verified", "observed", "pc_side_verified"}:
            confidence, radius_m = eale_gnss_quality(report, lineage_quality, quality_flags)
            state = "Fine"
            substate = "gnss_fix"
            source = ["gnss"]
            reason = "gnss_fix_valid"
            failure_reason = None
        else:
            confidence = 0.2
            state = "Unknown"
            substate = "failure"
            source = ["gnss"]
            reason = "gnss_fix_untrusted_source"
            failure_reason = "gnss_fix_untrusted_source"
            quality_flags.append("gnss_source_untrusted")
    elif has_predictable_location_memory(location_memory) and fix is False:
        memory_confidence = as_number(location_memory.get("confidence"))
        confidence = round(memory_confidence * 0.55, 3) if memory_confidence is not None else 0.35
        radius_m = as_number(location_memory.get("radius_m"))
        state = "Predicted"
        substate = "last_known_hold"
        source = merge_sources(location_memory.get("source"), "memory")
        reason = "last_known_after_gnss_no_fix"
        quality_flags.append("gnss_no_fix")
    elif report and fix is False and (cell or lte):
        confidence = 0.2
        state = "Unknown"
        substate = "no_precise_fix"
        source = ["gnss", "cell_lte"]
        reason = "gnss_no_fix_cell_lte_observed_no_position_memory"
        quality_flags.append("gnss_no_fix")
    elif report and fix is False:
        confidence = 0.1
        state = "Unknown"
        substate = "failure"
        source = ["gnss"]
        reason = "gnss_no_fix"
        quality_flags.append("gnss_no_fix")
    elif command and not report:
        confidence = 0.0
        state = "Unknown"
        substate = "failure"
        source = ["runtime"]
        reason = "missing_location_report_after_command"
        failure_reason = first_known(failure_reason, "missing_location_report")
        quality_flags.append("missing_location_report")
    elif cell or lte:
        confidence = 0.15
        state = "Unknown"
        substate = "no_precise_fix"
        source = ["cell_lte"]
        reason = "cell_lte_observed_without_position_memory"
    else:
        confidence = None
        failure_reason = first_known(failure_reason, "no_runtime_evidence")

    quality_flags = unique_text(quality_flags)
    dataset_window = eale_dataset_window_status(
        command=command,
        report=report,
        observation=observation,
        raw_refs=raw_refs,
        derived_refs=derived_refs,
        failure_reason=failure_reason,
        quality_flags=quality_flags,
    )

    return {
        "location_belief": {
            "state": state,
            "substate": substate,
            "source": source,
            "lat": None,
            "lon": None,
            "place_id": None,
            "radius_m": radius_m,
            "confidence": confidence,
            "confidence_bucket": confidence_bucket(confidence),
            "freshness_s": None,
            "reason": reason,
            "failure_reason": failure_reason,
            "quality_flags": quality_flags,
            "evidence_refs": {
                "raw_frame_refs": raw_refs,
                "derived_event_refs": derived_refs,
                "anchor_cmd_id": anchor_cmd_id,
                "anchor_event_id": first_known(dict_value(observation, "raw_frame", "frame_id"), dict_value(report, "raw_frame", "frame_id")),
            },
            "privacy": {
                "privacy_class": "private_location" if report.get("lat") is not None or report.get("lon") is not None else "engineering",
                "redaction_state": "bounded_export_only" if report.get("lat") is not None or report.get("lon") is not None else "none",
                "training_allowed": False,
            },
            "generator": {
                "name": EALE_P0_GENERATOR_NAME,
                "version": EALE_P0_GENERATOR_VERSION,
                "config_hash": None,
            },
        },
        "evidence": evidence,
        "dataset_window": dataset_window,
    }


def build_failure_summary(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    latest_observability: dict[str, Any],
) -> dict[str, Any]:
    reason_codes: list[str] = []
    for message in messages:
        if message.get("error_code"):
            reason_codes = unique_text(reason_codes + [message.get("error_code")])
        if message.get("message_type") == "event" and message.get("event_type") in {"location_report", "location_observation"}:
            gnss = as_dict(message.get("gnss"))
            gnss_reason = build_gnss_reason(
                first_known(message.get("fix"), gnss.get("fix")),
                first_known(message.get("gnss_state"), gnss.get("state"), gnss.get("result")),
                message.get("error_code"),
                message,
            )
            if gnss_reason not in {"GNSS_FIX", "GNSS_UNKNOWN"}:
                reason_codes = unique_text(reason_codes + [gnss_reason])
    reason_codes = unique_text(reason_codes + list(as_dict(latest_observability.get("explainability")).get("reason_codes") or []))

    problem_frame = raw_frame_problem(raw_frames)
    if problem_frame:
        parse = as_dict(problem_frame.get("parse_result"))
        code = first_known(parse.get("error_code"), raw_frame_parse_status(problem_frame))
        return {
            "state": "failure",
            "reason": "raw_frame_parse_failed",
            "reason_codes": unique_text([code] + reason_codes),
            "evidence": {
                "frame_id": problem_frame.get("frame_id"),
                "parse_status": raw_frame_parse_status(problem_frame),
                "parse_error_code": parse.get("error_code"),
                "parse_reason": parse.get("reason"),
            },
        }

    pending = [command for command in commands if command.get("status") == "pending"]
    if pending:
        command = newest_record(pending, "updated_at", "created_at")
        return {
            "state": "pending",
            "reason": "command_pending_ack_missing",
            "reason_codes": unique_text(["COMMAND_PENDING_ACK_MISSING"] + reason_codes),
            "evidence": {
                "cmd_id": command.get("cmd_id"),
                "cmd": command.get("cmd"),
                "created_at": command.get("created_at"),
                "updated_at": command.get("updated_at"),
            },
        }

    if not messages and not raw_frames:
        return {
            "state": "unknown",
            "reason": "no_runtime_evidence",
            "reason_codes": ["NO_RUNTIME_EVIDENCE"],
            "evidence": {},
        }

    if reason_codes:
        return {
            "state": "warning",
            "reason": reason_codes[0],
            "reason_codes": reason_codes,
            "evidence": {},
        }

    return {
        "state": "ok",
        "reason": "none",
        "reason_codes": [],
        "evidence": {},
    }


def build_run_context(
    *,
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    devices: list[dict[str, Any]] | None = None,
    test_run: dict[str, Any] | None = None,
    test_runs: list[dict[str, Any]] | None = None,
    latest_observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    devices = devices or []
    test_run = test_run or {}
    test_runs = test_runs or []
    latest_device = newest_record(devices, "last_seen_at") if devices else {}
    latest_message = newest_record(messages, "server_received_at", "ts") if messages else {}
    latest_command = newest_record(commands, "updated_at", "created_at") if commands else {}
    latest_raw = newest_record(raw_frames, "server_received_at") if raw_frames else {}
    location_messages = [
        message
        for message in messages
        if message.get("message_type") == "event" and message.get("event_type") in {"location_observation", "location_report"}
    ]
    latest_location = newest_record(location_messages, "server_received_at", "ts") if location_messages else {}
    latest_observability = as_dict(latest_observability or latest_device.get("observability"))

    test_run_id = first_known(
        test_run.get("test_run_id"),
        latest_location.get("test_run_id"),
        latest_message.get("test_run_id"),
        command_test_run_id(latest_command),
        raw_frame_test_run_id(latest_raw),
        dict_value(latest_observability, "location_memory", "last_test_run_id"),
    )
    if not test_run and test_run_id:
        for candidate in test_runs:
            if str(candidate.get("test_run_id") or "") == str(test_run_id):
                test_run = candidate
                break

    context_messages = [message for message in messages if message_matches_test_run(message, test_run_id)]
    context_commands = [command for command in commands if command_matches_test_run(command, test_run_id)]
    context_raw_frames = [raw_frame for raw_frame in raw_frames if raw_frame_matches_test_run(raw_frame, test_run_id)]
    if context_messages:
        latest_message = newest_record(context_messages, "server_received_at", "ts")
        location_messages = [
            message
            for message in context_messages
            if message.get("message_type") == "event"
            and message.get("event_type") in {"location_observation", "location_report"}
        ]
        latest_location = newest_record(location_messages, "server_received_at", "ts") if location_messages else {}
    if context_commands:
        latest_command = newest_record(context_commands, "updated_at", "created_at")
    if context_raw_frames:
        latest_raw = newest_record(context_raw_frames, "server_received_at")

    fw_version = first_known(
        latest_location.get("fw_version"),
        latest_message.get("fw_version"),
        latest_raw.get("fw_version"),
        latest_device.get("fw_version"),
        dict_value(latest_command, "ack", "fw_version"),
    )
    command_ack = as_dict(latest_command.get("ack"))
    location_belief = as_dict(latest_observability.get("location_belief"))
    reliability = as_dict(latest_observability.get("reliability"))
    raw_parse = as_dict(latest_raw.get("parse_result"))
    key_release = resolve_key_release_context(test_run_id, fw_version)
    failure = build_failure_summary(context_messages, context_commands, context_raw_frames, latest_observability)
    eale_p0 = build_eale_p0_location_belief(
        context_messages,
        context_commands,
        context_raw_frames,
        latest_observability,
        failure,
    )

    return {
        "test_run_id": first_known(test_run_id, "unknown"),
        "test_run_status": first_known(test_run.get("status"), "unknown"),
        "device_id": first_known(latest_device.get("device_id"), latest_message.get("device_id"), latest_raw.get("device_id"), "unknown"),
        "fw_version": first_known(fw_version, "unknown"),
        "last_seen_at": first_known(latest_device.get("last_seen_at"), latest_message.get("server_received_at"), latest_raw.get("server_received_at")),
        "key_release": key_release,
        "command": {
            "cmd_id": latest_command.get("cmd_id"),
            "cmd": latest_command.get("cmd"),
            "status": latest_command.get("status"),
            "ack_status": command_ack.get("status"),
            "ack_transport": dict_value(command_ack, "transport", "type"),
            "ack_test_run_id": command_ack.get("test_run_id"),
        },
        "raw_frame": {
            "frame_id": latest_raw.get("frame_id"),
            "direction": latest_raw.get("direction"),
            "frame_type": raw_frame_type(latest_raw),
            "parse_status": raw_frame_parse_status(latest_raw),
            "derived_message_type": raw_frame_derived_type(latest_raw),
            "parse_reason": first_known(raw_parse.get("reason"), raw_parse.get("error_code")),
        },
        "location": {
            "event_type": latest_location.get("event_type"),
            "seq": latest_location.get("seq"),
            "fix": first_known(latest_location.get("fix"), dict_value(latest_location, "gnss", "fix")),
            "gnss_state": first_known(latest_location.get("gnss_state"), dict_value(latest_location, "gnss", "state")),
            "location_request_cmd_id": latest_location.get("location_request_cmd_id"),
            "belief_state": location_belief.get("state"),
            "belief_reason": location_belief.get("reason"),
        },
        "failure": failure,
        "reliability": reliability,
        "eale_p0": eale_p0,
        "evidence_counts": {
            "messages": len(context_messages),
            "commands": len(context_commands),
            "raw_frames": len(context_raw_frames),
        },
    }


def summarize_test_run_observability(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_frame_list = raw_frames or []
    if not messages:
        failure_summary = build_failure_summary([], commands, raw_frame_list, {})
        eale_summary = build_eale_p0_location_belief([], commands, raw_frame_list, {}, failure_summary)
        return {
            "message_count": 0,
            "latest_observability": None,
            "reason_codes": failure_summary["reason_codes"],
            "failure_summary": failure_summary,
            "eale_p0": eale_summary,
        }
    latest = messages[-1]
    device = {
        "device_id": latest.get("device_id"),
        "fw_version": latest.get("fw_version") or "unknown",
        "last_seen_at": latest.get("server_received_at"),
        "last_message_type": latest.get("message_type"),
        "last_seq": latest.get("seq"),
        "last_status": latest_message(messages, message_type="status"),
        "latest_telemetry": latest_message(messages, message_type="event"),
        "latest_location": latest_location_message(messages),
        "latest_location_observation": latest_message(messages, message_type="event", event_type="location_observation"),
        "location_memory": summarize_location_memory(messages),
        "last_error": latest_message(messages, message_type="error"),
    }
    latest_observability = build_observability(device, commands[-1] if commands else None)
    reason_codes: list[str] = []
    for message in messages:
        error_code = message.get("error_code")
        if error_code and error_code not in reason_codes:
            reason_codes.append(str(error_code))
    for code in latest_observability["explainability"]["reason_codes"]:
        if code not in reason_codes:
            reason_codes.append(code)
    failure_summary = build_failure_summary(messages, commands, raw_frame_list, latest_observability)
    return {
        "message_count": len(messages),
        "command_count": len(commands),
        "latest_observability": latest_observability,
        "reason_codes": reason_codes,
        "failure_summary": failure_summary,
        "eale_p0": build_eale_p0_location_belief(
            messages,
            commands,
            raw_frame_list,
            latest_observability,
            failure_summary,
        ),
    }


def render_d2_reference_capture() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="theme-color" content="#ffffff" />
  <title>D2 Reference Capture</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --line: #d7dde5;
      --text: #17202a;
      --muted: #667085;
      --blue: #1f6feb;
      --blue-soft: #eaf2ff;
      --green: #0f766e;
      --green-soft: #e8f5f2;
      --amber: #a85b00;
      --amber-soft: #fff5df;
      --red: #b42318;
      --red-soft: #fff0ee;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; color: var(--text); background: var(--bg); }
    header { position: sticky; top: 0; z-index: 5; background: var(--panel); border-bottom: 1px solid var(--line); }
    .header-inner { max-width: 980px; margin: 0 auto; min-height: 64px; padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .title-group { min-width: 0; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    .subtitle { margin-top: 3px; color: var(--muted); font-size: 12px; }
    .header-link { color: var(--blue); text-decoration: none; font-size: 13px; font-weight: 600; white-space: nowrap; }
    main { max-width: 980px; margin: 0 auto; padding: 16px; display: grid; gap: 14px; }
    section { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    .status-band { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .status-copy { display: flex; align-items: center; gap: 9px; min-width: 0; }
    .status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green); flex: 0 0 auto; }
    .status-title { font-weight: 700; font-size: 14px; }
    .status-note { color: var(--muted); font-size: 12px; }
    .strict-state { padding: 5px 9px; border-radius: 999px; background: var(--amber-soft); color: var(--amber); font-size: 12px; font-weight: 700; }
    .strict-state.pass { background: var(--green-soft); color: var(--green); }
    .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    h2 { margin: 0; font-size: 15px; letter-spacing: 0; }
    .section-meta { color: var(--muted); font-size: 12px; }
    .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
    .field { display: grid; gap: 5px; min-width: 0; }
    .field-wide { grid-column: 1 / -1; }
    label, .field-label { color: var(--muted); font-size: 12px; font-weight: 600; }
    input, select, textarea { width: 100%; min-height: 40px; border: 1px solid #bcc6d3; border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; font-size: 14px; }
    textarea { min-height: 72px; resize: vertical; }
    input:focus, select:focus, textarea:focus { outline: 2px solid #b8d2ff; border-color: var(--blue); }
    .segments { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
    .segments.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .segment { position: relative; }
    .segment input { position: absolute; opacity: 0; pointer-events: none; }
    .segment span { min-height: 42px; border: 1px solid #bcc6d3; border-radius: 6px; display: grid; place-items: center; padding: 7px; text-align: center; color: #344054; font-size: 13px; font-weight: 600; cursor: pointer; }
    .segment input:checked + span { border-color: var(--blue); color: var(--blue); background: var(--blue-soft); }
    .action-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 12px; }
    button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--blue); border-radius: 6px; background: var(--blue); color: #fff; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
    button.secondary { background: #fff; color: var(--blue); }
    button.warn { border-color: var(--amber); background: #fff; color: var(--amber); }
    button.danger { border-color: var(--red); background: #fff; color: var(--red); }
    button:disabled { cursor: not-allowed; opacity: 0.45; }
    .inline-status { min-height: 18px; color: var(--muted); font-size: 12px; }
    .inline-status.ok { color: var(--green); }
    .inline-status.warn { color: var(--amber); }
    .progress-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .point-progress { border: 1px solid var(--line); border-radius: 8px; padding: 10px; display: grid; gap: 7px; min-width: 0; }
    .point-name { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
    .point-counts { display: flex; gap: 6px; flex-wrap: wrap; }
    .count-chip { padding: 4px 7px; border-radius: 999px; background: #f2f4f7; color: #344054; font-size: 11px; font-weight: 700; }
    .count-chip.done { background: var(--green-soft); color: var(--green); }
    .reference-state { color: var(--muted); font-size: 11px; }
    .reference-state.ok { color: var(--green); }
    .reference-state.warn { color: var(--amber); }
    .active-attempt { border-left: 4px solid var(--blue); background: #fbfdff; }
    .active-layout { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; }
    .active-id { font-size: 16px; font-weight: 700; overflow-wrap: anywhere; }
    .active-time { margin-top: 4px; color: var(--muted); font-size: 12px; }
    .attempt-list { display: grid; gap: 7px; max-height: 360px; overflow: auto; }
    .attempt-row { border-bottom: 1px solid #edf0f4; padding: 7px 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
    .attempt-row:last-child { border-bottom: 0; }
    .attempt-name { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
    .attempt-time { color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }
    .attempt-tag { align-self: start; color: var(--green); font-size: 11px; font-weight: 700; }
    .export-bar { position: sticky; bottom: 0; z-index: 4; box-shadow: 0 -8px 24px rgba(23, 32, 42, 0.08); }
    .export-layout { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .export-summary { min-width: 0; }
    .export-title { font-size: 14px; font-weight: 700; }
    .export-note { margin-top: 3px; color: var(--muted); font-size: 11px; }
    .export-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    @media (max-width: 720px) {
      .form-grid, .progress-grid { grid-template-columns: 1fr; }
      .field-wide { grid-column: auto; }
      .header-inner, main { padding-left: 10px; padding-right: 10px; }
      .segments { grid-template-columns: 1fr; }
      .segments.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .export-layout, .export-actions { align-items: stretch; }
      .export-actions { width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .export-actions button:last-child { grid-column: 1 / -1; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="title-group">
        <h1>D2 Reference Capture</h1>
        <div class="subtitle">Field manifest · local browser storage</div>
      </div>
      <a class="header-link" href="/">Dashboard</a>
    </div>
  </header>
  <main>
    <section class="status-band">
      <div class="status-copy">
        <span class="status-dot"></span>
        <div>
          <div class="status-title">Local only</div>
          <div class="status-note">Reference coordinates are not uploaded to Message Hub</div>
        </div>
      </div>
      <span id="strictState" class="strict-state">0 / 30 attempts</span>
    </section>

    <section>
      <div class="section-head"><h2>Run Identity</h2><span class="section-meta">saved automatically</span></div>
      <div class="form-grid">
        <div class="field"><label for="fieldRunId">Field run ID</label><input id="fieldRunId" autocomplete="off" /></div>
        <div class="field"><label for="messageRunId">Message test run ID</label><input id="messageRunId" autocomplete="off" /></div>
        <div class="field"><label for="deviceId">Device ID</label><input id="deviceId" autocomplete="off" /></div>
        <div class="field"><label for="firmwareVersion">Firmware version</label><input id="firmwareVersion" autocomplete="off" /></div>
        <div class="field"><label for="boardId">Board ID</label><input id="boardId" autocomplete="off" /></div>
        <div class="field"><label for="operator">Operator initials</label><input id="operator" autocomplete="off" /></div>
      </div>
    </section>

    <section>
      <div class="section-head"><h2>Reference Point</h2><span id="pointMeta" class="section-meta"></span></div>
      <div class="segments" id="pointSegments">
        <label class="segment"><input type="radio" name="point" value="open_sky_01" checked /><span>Open sky</span></label>
        <label class="segment"><input type="radio" name="point" value="street_between_buildings_01" /><span>Between buildings</span></label>
        <label class="segment"><input type="radio" name="point" value="tree_cover_01" /><span>Tree cover</span></label>
      </div>
      <div class="form-grid" style="margin-top:12px">
        <div class="field"><label for="referenceLat">Latitude</label><input id="referenceLat" inputmode="decimal" autocomplete="off" /></div>
        <div class="field"><label for="referenceLon">Longitude</label><input id="referenceLon" inputmode="decimal" autocomplete="off" /></div>
        <div class="field">
          <label for="referenceMethod">Reference method</label>
          <select id="referenceMethod">
            <option value="phone_browser_single_fix">Phone browser fix</option>
            <option value="phone_gnss_5min_average">Phone GNSS 5 min average</option>
            <option value="map_pick_satellite_view">Satellite map pick</option>
            <option value="survey_marker">Survey marker</option>
          </select>
        </div>
        <div class="field"><label for="referenceAccuracy">Phone accuracy (m)</label><input id="referenceAccuracy" inputmode="decimal" autocomplete="off" /></div>
        <div class="field field-wide"><label for="referenceNotes">Site notes</label><textarea id="referenceNotes"></textarea></div>
      </div>
      <div class="action-row">
        <button id="capturePosition" type="button">Use phone position</button>
        <button id="saveReference" class="secondary" type="button">Save reference</button>
        <span id="positionStatus" class="inline-status"></span>
      </div>
    </section>

    <section>
      <div class="section-head"><h2>Attempt</h2><span class="section-meta">UTC timestamps</span></div>
      <div class="segments two">
        <label class="segment"><input type="radio" name="attemptMode" value="cold" checked /><span>Cold</span></label>
        <label class="segment"><input type="radio" name="attemptMode" value="warm" /><span>Warm</span></label>
      </div>
      <div class="field" style="margin-top:10px"><label for="attemptNotes">Attempt notes</label><input id="attemptNotes" autocomplete="off" /></div>
      <div class="action-row">
        <button id="startAttempt" type="button">Start attempt</button>
        <span id="attemptStatus" class="inline-status"></span>
      </div>
    </section>

    <section id="activeAttemptPanel" class="active-attempt" hidden>
      <div class="active-layout">
        <div><div id="activeAttemptId" class="active-id"></div><div id="activeAttemptTime" class="active-time"></div></div>
        <button id="stopAttempt" type="button">Stop attempt</button>
      </div>
    </section>

    <section>
      <div class="section-head"><h2>Strict Gate Progress</h2><span class="section-meta">5 cold + 5 warm per point</span></div>
      <div id="progressGrid" class="progress-grid"></div>
    </section>

    <section>
      <div class="section-head"><h2>Completed Attempts</h2><span id="attemptTotal" class="section-meta">0</span></div>
      <div id="attemptList" class="attempt-list"><span class="status-note">No completed attempts</span></div>
    </section>

    <section class="export-bar">
      <div class="export-layout">
        <div class="export-summary"><div class="export-title">field_manifest.json</div><div id="exportNote" class="export-note">Partial evidence · not acceptance</div></div>
        <div class="export-actions">
          <button id="copyManifest" class="secondary" type="button">Copy JSON</button>
          <button id="downloadManifest" type="button">Export JSON</button>
          <button id="resetCapture" class="danger" type="button">Reset</button>
        </div>
      </div>
    </section>
  </main>
  <script>
    const STORAGE_KEY = 'egolink.d2_reference_capture.v1';
    const REQUIRED_METHODS = new Set(['phone_gnss_5min_average', 'map_pick_satellite_view', 'survey_marker']);
    const POINTS = [
      { point_id: 'open_sky_01', point_type: 'open_sky', name: 'Open sky' },
      { point_id: 'street_between_buildings_01', point_type: 'street_between_buildings', name: 'Between buildings' },
      { point_id: 'tree_cover_01', point_type: 'tree_cover', name: 'Tree cover' },
    ];
    const defaults = () => ({
      schema_version: 'egolink.field003_manifest.v0.2',
      field_run_id: `D2-001-reference-${new Date().toISOString().slice(0,10).replaceAll('-', '')}`,
      test_run_id: 'MODEL-DEVICE-006-hw-20260707-d1',
      board_id: 'connectivity-node-001',
      device_id: 'ego-link-r1-connectivity-001',
      firmware_version: '0.1.0-model-device-006-tiny-safety-hw',
      firmware_commit_or_image: 'app-commit:cf5b4a6',
      connection_path: 'vps_message_hub_usb_free',
      runtime_usb_connected: false,
      operator: '',
      started_at: null,
      ended_at: null,
      reference_points: POINTS.map(point => ({ ...point, reference: {}, notes: '' })),
      attempts: [],
      active_attempt_id: null,
    });
    function loadState() {
      try {
        const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
        if (parsed && Array.isArray(parsed.reference_points) && Array.isArray(parsed.attempts)) return parsed;
      } catch (_) {}
      return defaults();
    }
    let state = loadState();
    let selectedPointId = 'open_sky_01';
    const byId = id => document.getElementById(id);
    function saveState() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }
    function selectedPoint() {
      return state.reference_points.find(point => point.point_id === selectedPointId);
    }
    function selectedMode() {
      return document.querySelector('input[name="attemptMode"]:checked').value;
    }
    function numeric(value) {
      const number = Number.parseFloat(String(value).trim());
      return Number.isFinite(number) ? number : null;
    }
    function countAttempts(pointId, mode) {
      return state.attempts.filter(row => row.point_id === pointId && row.mode === mode && row.ended_at).length;
    }
    function referenceIsSaved(point) {
      return Number.isFinite(Number(point?.reference?.lat)) && Number.isFinite(Number(point?.reference?.lon));
    }
    function referenceIsStrict(point) {
      return referenceIsSaved(point) && REQUIRED_METHODS.has(point.reference.method);
    }
    function strictReady() {
      return POINTS.every(point => {
        const saved = state.reference_points.find(item => item.point_id === point.point_id);
        return referenceIsStrict(saved) && countAttempts(point.point_id, 'cold') >= 5 && countAttempts(point.point_id, 'warm') >= 5;
      });
    }
    function activeAttempt() {
      return state.attempts.find(row => row.attempt_id === state.active_attempt_id && !row.ended_at);
    }
    function syncMetadata() {
      state.field_run_id = byId('fieldRunId').value.trim();
      state.test_run_id = byId('messageRunId').value.trim();
      state.device_id = byId('deviceId').value.trim();
      state.firmware_version = byId('firmwareVersion').value.trim();
      state.board_id = byId('boardId').value.trim();
      state.operator = byId('operator').value.trim();
      saveState();
    }
    function loadReferenceForm() {
      const point = selectedPoint();
      byId('referenceLat').value = point?.reference?.lat ?? '';
      byId('referenceLon').value = point?.reference?.lon ?? '';
      byId('referenceMethod').value = point?.reference?.method || 'phone_browser_single_fix';
      byId('referenceAccuracy').value = point?.reference?.phone_accuracy_m ?? '';
      byId('referenceNotes').value = point?.notes || '';
      byId('pointMeta').textContent = point?.point_id || '';
      byId('positionStatus').textContent = referenceIsSaved(point) ? 'Reference saved locally' : '';
      byId('positionStatus').className = referenceIsSaved(point) ? 'inline-status ok' : 'inline-status';
    }
    function renderProgress() {
      byId('progressGrid').innerHTML = POINTS.map(point => {
        const saved = state.reference_points.find(item => item.point_id === point.point_id);
        const cold = countAttempts(point.point_id, 'cold');
        const warm = countAttempts(point.point_id, 'warm');
        const refClass = referenceIsStrict(saved) ? 'ok' : (referenceIsSaved(saved) ? 'warn' : '');
        const refText = referenceIsStrict(saved) ? 'strict reference ready' : (referenceIsSaved(saved) ? 'reference needs approved method' : 'reference missing');
        return `<div class="point-progress"><div class="point-name">${point.name}</div><div class="point-counts"><span class="count-chip ${cold >= 5 ? 'done' : ''}">cold ${cold}/5</span><span class="count-chip ${warm >= 5 ? 'done' : ''}">warm ${warm}/5</span></div><div class="reference-state ${refClass}">${refText}</div></div>`;
      }).join('');
      const completed = state.attempts.filter(row => row.ended_at).length;
      byId('strictState').textContent = strictReady() ? 'Strict gate complete' : `${completed} / 30 attempts`;
      byId('strictState').className = strictReady() ? 'strict-state pass' : 'strict-state';
      byId('exportNote').textContent = strictReady() ? 'Strict manifest complete · analysis still required' : 'Partial evidence · not acceptance';
    }
    function renderAttempts() {
      const completed = state.attempts.filter(row => row.ended_at).slice().reverse();
      byId('attemptTotal').textContent = String(completed.length);
      byId('attemptList').innerHTML = completed.length ? completed.map(row => `<div class="attempt-row"><div><div class="attempt-name">${row.attempt_id}</div><div class="attempt-time">${row.started_at} → ${row.ended_at}</div></div><span class="attempt-tag">saved</span></div>`).join('') : '<span class="status-note">No completed attempts</span>';
    }
    function renderActive() {
      const row = activeAttempt();
      byId('activeAttemptPanel').hidden = !row;
      byId('startAttempt').disabled = Boolean(row);
      if (row) {
        byId('activeAttemptId').textContent = row.attempt_id;
        byId('activeAttemptTime').textContent = `Started ${row.started_at}`;
      }
    }
    function renderAll() {
      renderProgress();
      renderAttempts();
      renderActive();
    }
    function saveReference() {
      const point = selectedPoint();
      const lat = numeric(byId('referenceLat').value);
      const lon = numeric(byId('referenceLon').value);
      if (lat === null || lon === null || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
        byId('positionStatus').textContent = 'Enter a valid latitude and longitude';
        byId('positionStatus').className = 'inline-status warn';
        return;
      }
      point.reference = {
        lat,
        lon,
        method: byId('referenceMethod').value,
        recorded_at: new Date().toISOString(),
        phone_accuracy_m: numeric(byId('referenceAccuracy').value),
      };
      point.notes = byId('referenceNotes').value.trim();
      saveState();
      byId('positionStatus').textContent = REQUIRED_METHODS.has(point.reference.method) ? 'Strict reference saved locally' : 'Single phone fix saved as partial reference';
      byId('positionStatus').className = REQUIRED_METHODS.has(point.reference.method) ? 'inline-status ok' : 'inline-status warn';
      renderProgress();
    }
    function capturePosition() {
      if (!navigator.geolocation) {
        byId('positionStatus').textContent = 'Phone location unavailable; enter coordinates manually';
        byId('positionStatus').className = 'inline-status warn';
        return;
      }
      byId('capturePosition').disabled = true;
      byId('positionStatus').textContent = 'Waiting for phone location';
      navigator.geolocation.getCurrentPosition(position => {
        byId('referenceLat').value = position.coords.latitude.toFixed(7);
        byId('referenceLon').value = position.coords.longitude.toFixed(7);
        byId('referenceAccuracy').value = Math.round(position.coords.accuracy).toString();
        byId('referenceMethod').value = 'phone_browser_single_fix';
        byId('capturePosition').disabled = false;
        byId('positionStatus').textContent = 'Phone fix captured; save reference';
        byId('positionStatus').className = 'inline-status warn';
      }, () => {
        byId('capturePosition').disabled = false;
        byId('positionStatus').textContent = 'Phone location blocked; use manual coordinates or HTTPS';
        byId('positionStatus').className = 'inline-status warn';
      }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
    }
    function startAttempt() {
      syncMetadata();
      const point = selectedPoint();
      if (!referenceIsSaved(point)) {
        byId('attemptStatus').textContent = 'Save this reference point first';
        byId('attemptStatus').className = 'inline-status warn';
        return;
      }
      if (activeAttempt()) return;
      const mode = selectedMode();
      const number = countAttempts(point.point_id, mode) + 1;
      const row = {
        attempt_id: `${point.point_id}-${mode}-${String(number).padStart(2, '0')}`,
        point_id: point.point_id,
        mode,
        command_id: null,
        started_at: new Date().toISOString(),
        ended_at: null,
        operator_notes: byId('attemptNotes').value.trim(),
      };
      state.attempts.push(row);
      state.active_attempt_id = row.attempt_id;
      state.started_at ||= row.started_at;
      saveState();
      byId('attemptNotes').value = '';
      byId('attemptStatus').textContent = 'Attempt running';
      byId('attemptStatus').className = 'inline-status ok';
      renderAll();
    }
    function stopAttempt() {
      const row = activeAttempt();
      if (!row) return;
      row.ended_at = new Date().toISOString();
      state.active_attempt_id = null;
      state.ended_at = row.ended_at;
      saveState();
      byId('attemptStatus').textContent = 'Attempt saved locally';
      byId('attemptStatus').className = 'inline-status ok';
      renderAll();
    }
    function exportPayload() {
      syncMetadata();
      const payload = JSON.parse(JSON.stringify(state));
      delete payload.active_attempt_id;
      payload.attempts = payload.attempts.filter(row => row.ended_at);
      return payload;
    }
    async function copyManifest() {
      const text = JSON.stringify(exportPayload(), null, 2);
      try {
        await navigator.clipboard.writeText(text);
        byId('exportNote').textContent = 'Manifest copied';
      } catch (_) {
        const area = document.createElement('textarea');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
        byId('exportNote').textContent = 'Manifest copied';
      }
    }
    function downloadManifest() {
      const blob = new Blob([JSON.stringify(exportPayload(), null, 2) + '\\n'], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'field_manifest.json';
      link.click();
      URL.revokeObjectURL(url);
      byId('exportNote').textContent = 'field_manifest.json exported';
    }
    function resetCapture() {
      if (!window.confirm('Reset all locally stored D2 reference data?')) return;
      state = defaults();
      saveState();
      location.reload();
    }
    ['fieldRunId','messageRunId','deviceId','firmwareVersion','boardId','operator'].forEach(id => byId(id).addEventListener('change', syncMetadata));
    document.querySelectorAll('input[name="point"]').forEach(input => input.addEventListener('change', event => { selectedPointId = event.target.value; loadReferenceForm(); }));
    byId('capturePosition').addEventListener('click', capturePosition);
    byId('saveReference').addEventListener('click', saveReference);
    byId('startAttempt').addEventListener('click', startAttempt);
    byId('stopAttempt').addEventListener('click', stopAttempt);
    byId('copyManifest').addEventListener('click', copyManifest);
    byId('downloadManifest').addEventListener('click', downloadManifest);
    byId('resetCapture').addEventListener('click', resetCapture);
    byId('fieldRunId').value = state.field_run_id || '';
    byId('messageRunId').value = state.test_run_id || '';
    byId('deviceId').value = state.device_id || '';
    byId('firmwareVersion').value = state.firmware_version || '';
    byId('boardId').value = state.board_id || '';
    byId('operator').value = state.operator || '';
    loadReferenceForm();
    renderAll();
  </script>
</body>
</html>"""


def render_dashboard(*, amap_js_api_key: str | None = None) -> str:
    safe_amap_key = amap_js_api_key if amap_js_api_key and AMAP_CREDENTIAL_PATTERN.fullmatch(amap_js_api_key) else ""
    amap_bootstrap = (
        "<script>window._AMapSecurityConfig={serviceHost:window.location.origin+'/_AMapService'};</script>"
        if safe_amap_key
        else '<meta name="egolink-amap-status" content="not-configured" />'
    )
    html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EgoLink 定位看板</title>
  <style>
    :root {
      --bg: #f5f6f8;
      --panel: #ffffff;
      --line: #d9dee8;
      --muted: #667085;
      --text: #17202a;
      --blue: #1f6feb;
      --green: #0f766e;
      --amber: #b45309;
      --red: #c2410c;
      --ink-soft: #344054;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: "PingFang SC", "Microsoft YaHei", Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--text); }
    header { position: sticky; top: 0; z-index: 30; padding: 12px 20px; background: rgba(255,255,255,0.96); backdrop-filter: blur(12px); border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; box-shadow: 0 1px 8px rgba(16,24,40,0.05); }
    h1 { margin: 0; font-size: 21px; letter-spacing: 0; }
    .brand-note { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
    .header-actions, .auth { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .header-link { color: var(--blue); text-decoration: none; font-size: 13px; font-weight: 600; white-space: nowrap; }
    input, select { padding: 8px 10px; border: 1px solid #c8d0dc; border-radius: 6px; background: #fff; color: var(--text); font: inherit; }
    input { width: min(360px, 56vw); }
    select { min-width: min(320px, 46vw); max-width: 100%; }
    button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--blue); border-radius: 8px; background: var(--blue); color: #fff; font: inherit; cursor: pointer; }
    button.secondary { background: #fff; color: var(--blue); }
    button:disabled { cursor: not-allowed; opacity: 0.45; }
    button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible { outline: 3px solid rgba(31, 111, 235, 0.35); outline-offset: 2px; }
    #authStatus { min-width: 92px; color: var(--muted); font-size: 13px; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    .dashboard-shell { max-width: 1480px; margin: 0 auto; padding: 18px; display: grid; gap: 18px; }
    .dashboard-grid { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 16px; align-items: start; }
    .stack { display: grid; gap: 16px; }
    section { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px; box-shadow: 0 6px 18px rgba(16,24,40,0.04); }
    .focus-panel { padding: 0; overflow: hidden; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid #edf0f5; }
    .section-head h2 { margin: 0; }
    .section-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
    .section-actions button { min-height: 34px; padding: 6px 10px; font-size: 12px; }
    .device-picker { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .device-picker label { color: var(--muted); font-size: 12px; font-weight: 600; }
    .map-import-status { min-width: 126px; max-width: 260px; color: var(--muted); font-size: 12px; text-align: right; overflow-wrap: anywhere; }
    .section-kicker, .refresh-note, .refresh-status { color: var(--muted); font-size: 12px; }
    .refresh-status.ok { color: var(--green); }
    .refresh-status.warn { color: var(--amber); }
    .refresh-status.bad { color: var(--red); }
    h2 { margin: 0 0 10px; font-size: 16px; letter-spacing: 0; }
    h3 { margin: 0; font-size: 14px; letter-spacing: 0; }
    .metric { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 8px; padding: 7px 0; border-bottom: 1px solid #edf0f5; font-size: 14px; }
    .metric span:first-child { color: var(--muted); }
    .metric span:last-child, .metric b { min-width: 0; overflow-wrap: anywhere; }
    .ok { color: var(--green); font-weight: 600; }
    .warn { color: var(--amber); font-weight: 600; }
    .bad { color: var(--red); font-weight: 600; }
    .empty { color: var(--muted); }
    .table-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    table { width: 100%; min-width: 620px; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #edf0f5; vertical-align: top; }
    th { color: var(--muted); }
    .empty-panel { padding: 20px; color: var(--muted); }
    .field-operations-grid { padding: 16px; display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(300px, 0.75fr); gap: 12px; align-items: start; }
    .operation-stack { display: grid; gap: 12px; }
    .operation-card { min-width: 0; border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; }
    .operation-card h3 { margin-bottom: 8px; }
    .operation-card details { margin-top: 8px; }
    .operation-card details > summary { color: var(--blue); cursor: pointer; font-size: 13px; font-weight: 600; }
    .photo-grid { padding: 16px; display: grid; grid-template-columns: minmax(320px, 0.8fr) minmax(420px, 1.2fr); gap: 12px; align-items: start; }
    .photo-controls { display: grid; gap: 10px; }
    .photo-field { display: grid; gap: 5px; min-width: 0; }
    .photo-field label { color: var(--muted); font-size: 12px; font-weight: 700; }
    .photo-field input { width: 100%; min-width: 0; }
    .photo-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .photo-note { color: var(--muted); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
    .photo-status { border-left: 4px solid var(--blue); border-radius: 8px; padding: 9px 10px; background: #eef5ff; color: var(--ink-soft); font-size: 13px; overflow-wrap: anywhere; }
    .photo-status.warn { border-color: var(--amber); background: #fff8eb; }
    .photo-status.bad { border-color: var(--red); background: #fff1eb; }
    .photo-preview { margin-top: 10px; min-height: 180px; display: grid; place-items: center; overflow: hidden; border: 1px solid #d8dde6; border-radius: 10px; background: #f5f6f8; }
    .photo-preview img { display: block; max-width: 100%; max-height: 420px; object-fit: contain; }
    .photo-list { display: grid; gap: 8px; margin-top: 10px; max-height: 340px; overflow-y: auto; }
    .photo-list-item { width: 100%; min-height: 0; padding: 9px; border: 1px solid #e3e7ee; border-radius: 8px; background: #fff; color: var(--text); font-size: 12px; text-align: left; cursor: pointer; }
    .photo-list-item:hover, .photo-list-item:focus-visible { border-color: var(--blue); }
    .photo-list-item strong, .photo-list-item span { display: block; overflow-wrap: anywhere; }
    .photo-list-item span { margin-top: 3px; color: var(--muted); }
    .field-evidence-grid { padding: 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
    .evidence-panel { min-width: 0; border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; }
    .evidence-panel h3 { margin-bottom: 10px; }
    .dashboard-details { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; box-shadow: 0 6px 18px rgba(16,24,40,0.04); }
    .dashboard-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; cursor: pointer; font-size: 16px; font-weight: 700; list-style: none; }
    .dashboard-details > summary::-webkit-details-marker { display: none; }
    .dashboard-details > summary::after { content: '展开'; color: var(--blue); font-size: 12px; font-weight: 600; }
    .dashboard-details[open] > summary { border-bottom: 1px solid #edf0f5; }
    .dashboard-details[open] > summary::after { content: '收起'; }
    .details-body { padding: 16px; }
    .details-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
    .details-grid > section { min-width: 0; }
    .details-grid .wide { grid-column: 1 / -1; }
    .scroll-panel { max-height: 360px; overflow: auto; }
    .d1-overview { padding: 16px 18px 4px; display: grid; grid-template-columns: minmax(320px, 0.8fr) minmax(460px, 1.2fr); gap: 16px; align-items: stretch; }
    .d1-overview.provider-map-active { grid-template-columns: 1fr; }
    .d1-overview.provider-map-active .d1-map-pane { display: none; }
    .d1-map-pane, .d1-summary-pane { min-width: 0; }
    .d1-summary-pane { display: grid; gap: 12px; }
    .d1-status-strip { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .status-chip { display: inline-flex; align-items: center; min-height: 28px; padding: 5px 10px; border-radius: 999px; border: 1px solid #d8dde6; background: #f8fafc; color: var(--ink-soft); font-size: 13px; font-weight: 600; }
    .status-chip.ok { background: #e8f5f2; border-color: #b8ddd6; color: var(--green); }
    .status-chip.warn { background: #fff7e8; border-color: #f0d39a; color: var(--amber); }
    .status-chip.bad { background: #fff1eb; border-color: #f0b8a3; color: var(--red); }
    .d1-primary-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .d1-primary { border: 1px solid #d8dde6; border-radius: 10px; padding: 12px; display: grid; gap: 6px; background: #fbfcfe; }
    .d1-primary strong { font-size: 22px; line-height: 1.2; overflow-wrap: anywhere; }
    .d1-details { border: 1px solid #d8dde6; border-radius: 8px; background: #fff; overflow: hidden; }
    .d1-details > summary { padding: 11px 12px; color: var(--blue); cursor: pointer; font-size: 13px; font-weight: 700; }
    .d1-details[open] > summary { border-bottom: 1px solid #edf0f5; }
    .d1-details .d1-grid { padding: 12px; }
    .d1-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .d1-card { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; display: grid; gap: 6px; min-width: 0; }
    .card-label { color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; }
    .card-value { font-size: 15px; font-weight: 700; overflow-wrap: anywhere; }
    .card-note { color: var(--ink-soft); font-size: 13px; overflow-wrap: anywhere; }
    .evidence-list { display: grid; gap: 6px; }
    .evidence-pill { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 13px; }
    .evidence-pill span:last-child { overflow-wrap: anywhere; }
    .report-grid { display: grid; gap: 10px; }
    .report-card { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; display: grid; gap: 6px; min-width: 0; }
    .report-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; flex-wrap: wrap; }
    .report-title { font-size: 15px; font-weight: 700; }
    .report-meta, .report-path { color: var(--ink-soft); font-size: 13px; overflow-wrap: anywhere; }
    .report-metrics { display: grid; gap: 4px; font-size: 13px; color: var(--ink-soft); }
    .progress-layout { display: grid; grid-template-columns: minmax(260px, 0.9fr) minmax(420px, 1.4fr); gap: 18px; padding: 2px; }
    .progress-focus { font-size: 16px; font-weight: 700; line-height: 1.45; overflow-wrap: anywhere; }
    .progress-meta { margin-top: 8px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .progress-actions { margin-top: 14px; }
    .progress-actions ul { margin: 7px 0 0; padding-left: 20px; color: var(--ink-soft); font-size: 13px; }
    .progress-actions li { margin: 5px 0; overflow-wrap: anywhere; }
    .progress-milestones { display: grid; gap: 8px; }
    .progress-milestone { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid #edf0f5; }
    .progress-milestone:last-child { border-bottom: 0; }
    .progress-milestone-name { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
    .progress-milestone-count { color: var(--muted); font-size: 12px; }
    .progress-track { grid-column: 1 / -1; height: 6px; overflow: hidden; border-radius: 999px; background: #e7ebf1; }
    .progress-fill { height: 100%; background: var(--green); }
    .evidence-lanes { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 0 0 12px; }
    .evidence-lane { border: 1px solid #d8dde6; border-radius: 8px; padding: 10px; background: #fbfcfe; min-width: 0; }
    .lane-label { display: block; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; }
    .lane-value { display: block; margin-top: 4px; font-size: 14px; font-weight: 700; overflow-wrap: anywhere; }
    .lane-note { display: block; margin-top: 4px; color: var(--ink-soft); font-size: 12px; overflow-wrap: anywhere; }
    .map-surface { min-height: 260px; border: 1px solid #c8d0dc; border-radius: 8px; background: #eef2f6; position: relative; display: grid; place-items: center; overflow: hidden; }
    .location-map-grid { padding: 14px 18px 18px; display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 14px; align-items: stretch; }
    .location-map-grid.provider-map-hidden { grid-template-columns: 1fr; }
    .location-map-grid.provider-map-hidden .map-card { display: none; }
    .map-card { min-width: 0; }
    .amap-live-shell { position: relative; min-height: 0; }
    #amapLiveMap { position: relative; z-index: 1; min-height: 500px; display: none; background: #eef2f6; border: 1px solid #c8d0dc; border-radius: 12px; overflow: hidden; }
    #amapLiveMap[data-state="ready"] { visibility: visible; }
    #amapLiveStatus { position: absolute; left: 10px; top: 8px; z-index: 5; max-width: calc(100% - 20px); color: var(--ink-soft); font-size: 12px; background: rgba(255,255,255,0.94); border: 1px solid #d8dde6; border-radius: 6px; padding: 6px 8px; pointer-events: none; }
    #amapLiveStatus.ok { color: var(--green); }
    #amapLiveStatus.warn { color: var(--amber); }
    .amap-current-marker, .amap-memory-marker { width: 18px; height: 18px; border-radius: 50%; border: 3px solid #fff; box-shadow: 0 0 0 2px var(--blue); background: var(--blue); }
    .amap-memory-marker { background: var(--amber); box-shadow: 0 0 0 2px var(--amber); }
    .amap-stale-marker { width: 18px; height: 18px; border-radius: 50%; border: 3px solid #fff; background: var(--red); box-shadow: 0 0 0 2px var(--red); }
    .amap-start-marker { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; border: 2px solid #fff; background: var(--green); color: #fff; font-size: 13px; font-weight: 800; box-shadow: 0 0 0 2px var(--green); }
    .amap-history-marker { width: 9px; height: 9px; border-radius: 50%; border: 2px solid #fff; background: #475467; box-shadow: 0 0 0 1px #475467; opacity: 0.82; }
    .amap-end-marker { position: relative; display: flex; align-items: center; gap: 6px; }
    .amap-marker-label { display: block; min-width: max-content; border: 1px solid #d8dde6; border-radius: 999px; padding: 4px 8px; background: rgba(255,255,255,0.96); color: var(--ink-soft); font-size: 12px; font-weight: 700; box-shadow: 0 2px 8px rgba(16,24,40,0.12); }
    .trajectory-panel { min-width: 0; border: 1px solid #d8dde6; border-radius: 12px; background: #fbfcfe; padding: 14px; display: flex; flex-direction: column; gap: 12px; }
    .trajectory-panel h3 { font-size: 16px; }
    .trajectory-summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .trajectory-stat { border: 1px solid #e3e7ee; border-radius: 9px; padding: 10px; background: #fff; min-width: 0; }
    .trajectory-stat span { display: block; color: var(--muted); font-size: 12px; }
    .trajectory-stat strong { display: block; margin-top: 3px; font-size: 15px; overflow-wrap: anywhere; }
    .trajectory-state { border-left: 4px solid var(--blue); border-radius: 8px; padding: 10px 12px; background: #eef5ff; color: var(--ink-soft); font-size: 13px; }
    .trajectory-state.warn { border-color: var(--amber); background: #fff8eb; }
    .trajectory-note { color: var(--muted); font-size: 12px; line-height: 1.55; }
    .trajectory-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .trajectory-controls button { min-height: 36px; padding: 7px 10px; }
    .trajectory-selection-status { color: var(--ink-soft); font-size: 12px; font-weight: 700; }
    .trajectory-details { border-top: 1px solid #e3e7ee; padding-top: 10px; }
    .trajectory-details > summary { color: var(--blue); cursor: pointer; font-size: 13px; font-weight: 700; }
    .trajectory-list { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 8px; max-height: 240px; overflow-y: auto; }
    .trajectory-list li { display: grid; grid-template-columns: 24px 116px minmax(0, 1fr); gap: 8px; align-items: start; padding: 8px; border-radius: 8px; background: #fff; border: 1px solid #e6e9ef; font-size: 12px; }
    .trajectory-list input[type="checkbox"] { width: 18px; height: 18px; margin: 0; accent-color: var(--blue); }
    .trajectory-time { color: var(--ink-soft); font-weight: 700; }
    .trajectory-event { color: var(--muted); overflow-wrap: anywhere; }
    .location-history-browser { margin: 0 18px 18px; border: 1px solid #d8dde6; border-radius: 12px; background: #fbfcfe; overflow: hidden; }
    .history-browser-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 14px; border-bottom: 1px solid #e3e7ee; flex-wrap: wrap; }
    .history-browser-head h3 { font-size: 16px; }
    .history-browser-note { margin-top: 4px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .history-filter-grid { display: grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap: 10px; padding: 14px; border-bottom: 1px solid #e3e7ee; }
    .history-filter { display: grid; gap: 5px; min-width: 0; }
    .history-filter label { color: var(--muted); font-size: 12px; font-weight: 700; }
    .history-filter input, .history-filter select { width: 100%; min-width: 0; }
    .history-filter-actions { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .history-filter-actions button { min-height: 36px; }
    .history-status { color: var(--ink-soft); font-size: 12px; font-weight: 600; }
    .history-status.warn { color: var(--amber); }
    .history-status.bad { color: var(--red); }
    .history-table-wrap { overflow: auto; max-height: 520px; background: #fff; }
    .history-table { min-width: 920px; }
    .history-table input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--blue); }
    .history-record-unselectable { color: var(--muted); background: #fafafa; }
    .history-trust-ok { color: var(--green); font-weight: 700; }
    .history-trust-warn { color: var(--amber); font-weight: 700; }
    .history-pagination { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 14px; border-top: 1px solid #e3e7ee; flex-wrap: wrap; }
    .history-pagination-actions { display: flex; align-items: center; gap: 8px; }
    .history-page-label, .history-selection-label { color: var(--ink-soft); font-size: 12px; font-weight: 700; }
    .map-grid { position: absolute; inset: 0; background-image: linear-gradient(#d9e0ea 1px, transparent 1px), linear-gradient(90deg, #d9e0ea 1px, transparent 1px); background-size: 28px 28px; }
    .map-track { position: absolute; inset: 0; z-index: 1; pointer-events: none; }
    .map-provider-banner { position: absolute; left: 10px; right: 10px; top: 8px; z-index: 3; display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; color: var(--ink-soft); font-size: 12px; background: rgba(255, 255, 255, 0.9); border: 1px solid #d8dde6; border-radius: 6px; padding: 6px 8px; }
    .map-legend { position: absolute; right: 10px; top: 52px; z-index: 3; display: grid; gap: 5px; color: var(--ink-soft); font-size: 12px; background: rgba(255, 255, 255, 0.88); border: 1px solid #d8dde6; border-radius: 6px; padding: 6px 8px; }
    .map-legend-item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
    .map-legend-dot { width: 10px; height: 10px; border-radius: 50%; background: #667085; border: 2px solid #fff; box-shadow: 0 0 0 1px #667085; }
    .map-legend-current { background: var(--blue); box-shadow: 0 0 0 1px var(--blue); }
    .map-legend-reference { border-radius: 3px; background: var(--amber); box-shadow: 0 0 0 1px var(--amber); }
    .map-point { position: absolute; width: 9px; height: 9px; border-radius: 50%; background: #667085; border: 2px solid #fff; box-shadow: 0 0 0 1px #667085; transform: translate(-50%, -50%); z-index: 2; }
    .map-point-start { width: 15px; height: 15px; background: var(--green); box-shadow: 0 0 0 2px var(--green); }
    .map-point-end { width: 16px; height: 16px; background: var(--amber); box-shadow: 0 0 0 2px var(--amber); }
    .map-point-stale { width: 16px; height: 16px; background: var(--red); box-shadow: 0 0 0 2px var(--red); }
    .map-point-current { width: 16px; height: 16px; background: var(--blue); box-shadow: 0 0 0 2px var(--blue); }
    .map-point-position { transform: translate(-50%, -160%); z-index: 4; }
    .map-point-reference { width: 13px; height: 13px; border-radius: 3px; background: var(--amber); box-shadow: 0 0 0 2px var(--amber); }
    .map-waiting { z-index: 1; color: var(--muted); font-size: 13px; font-weight: 600; border: 1px solid #c8d0dc; border-radius: 999px; padding: 6px 10px; background: rgba(255,255,255,0.82); }
    .map-caption { position: absolute; left: 10px; right: 10px; bottom: 8px; z-index: 1; color: var(--ink-soft); font-size: 12px; text-align: center; background: rgba(255, 255, 255, 0.88); border: 1px solid #d8dde6; border-radius: 6px; padding: 5px 6px; }
    @media (max-width: 1080px) { .location-map-grid { grid-template-columns: 1fr; } .trajectory-panel { min-height: 0; } }
    @media (max-width: 980px) { .dashboard-grid, .d1-overview, .progress-layout, .field-operations-grid, .field-evidence-grid, .photo-grid, .details-grid { grid-template-columns: 1fr; } .details-grid .wide { grid-column: auto; } .d1-summary-pane { order: 1; } .d1-map-pane { order: 2; } .d1-primary-row { grid-template-columns: 1fr; } .history-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 760px) { .evidence-lanes { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 560px) { header { position: static; } .dashboard-shell { padding: 10px; } .d1-grid, .evidence-lanes, .trajectory-summary-grid, .history-filter-grid { grid-template-columns: 1fr; } .metric { grid-template-columns: 112px minmax(0, 1fr); } input { width: min(100%, 280px); } select { width: 100%; min-width: 0; } button, select { min-height: 44px; } #amapLiveMap { min-height: 360px; } .location-map-grid { padding: 10px; } .location-history-browser { margin: 0 10px 10px; } .map-legend { left: 10px; right: auto; } .header-actions { width: 100%; justify-content: space-between; } .section-head { align-items: flex-start; flex-direction: column; } .section-actions, .device-picker { width: 100%; justify-content: flex-start; } .map-import-status { max-width: 100%; text-align: left; } .dashboard-details > summary { align-items: flex-start; } }
  </style>
  __AMAP_BOOTSTRAP__
</head>
<body>
  <header>
    <div>
      <h1>EgoLink 定位看板</h1>
      <p><a href="/collection">进入采集：原始观测、各源状态与完整导出</a> · <a href="/guardian-location">家属定位</a> · <a href="/dev" style="color:#0ea5e9;font-weight:600;">⚡ 开发者工作台 (DevBench)</a></p>
      <span class="brand-note">设备位置、历史轨迹与外场状态</span>
    </div>
    <div class="header-actions">
      <a class="header-link" href="/d2-reference-capture">D2 参考点采集</a>
      <div class="auth">
        <label class="sr-only" for="tokenInput">访问令牌</label>
        <input id="tokenInput" type="password" autocomplete="off" placeholder="访问令牌" aria-label="访问令牌" />
        <button id="saveToken" type="button">保存连接</button>
        <span id="authStatus" role="status" aria-live="polite"></span>
      </div>
    </div>
  </header>
  <main class="dashboard-shell">
    <span hidden aria-hidden="true" data-dashboard-contract-labels="legacy-en">Ego Link Message Hub D1 Link Through Field live view Field Test Results Data Flywheel Project Progress Product Demo Latest Field State Run Context Commands Raw Frames D1 Acceptance Gate Upload Success Location Uploads Power Curve Track points No-key Local Map Provider Status D2 Reference Predicted / Last known position Pre-correction location hidden until new verified GNSS fix</span>
    <section class="focus-panel">
      <div class="section-head">
        <div>
          <h2>位置与历史轨迹</h2>
          <span class="section-kicker">最近可信定位、轨迹变化与数据新鲜度</span>
        </div>
        <div class="section-actions">
          <div class="device-picker">
            <label for="deviceSelector">当前设备</label>
            <select id="deviceSelector" aria-label="当前设备" disabled>
              <option value="">正在等待设备</option>
            </select>
          </div>
          <button id="loadD2Manifest" class="secondary" type="button">导入 D2 参考点</button>
          <button id="clearD2References" class="secondary" type="button">清除参考点</button>
          <input id="d2ManifestFile" type="file" accept="application/json,.json" hidden />
          <span id="d2ManifestStatus" class="map-import-status">暂无本地参考点</span>
          <button id="refreshDashboard" class="secondary" type="button">刷新数据</button>
          <span class="refresh-note">页面不会自动重建</span>
          <span id="refreshStatus" class="refresh-status" role="status" aria-live="polite">正在等待首次加载</span>
        </div>
      </div>
      <div id="locationMapGrid" class="location-map-grid provider-map-hidden">
        <div class="map-card">
          <div id="amapLiveShell" class="amap-live-shell" data-provider-state="waiting" data-lifecycle="idle" data-failure-stage="none" data-failure-reason="none" data-failure-elapsed-ms="0" data-callback-seen="false">
            <div id="amapLiveMap" data-state="waiting" aria-label="高德地图上的设备位置"></div>
            <div id="amapLiveStatus" class="warn" role="status" aria-live="polite">地图正在等待已认证的设备数据</div>
          </div>
        </div>
      </div>
      <section id="locationHistoryBrowser" class="location-history-browser" aria-labelledby="locationHistoryTitle">
        <div class="history-browser-head">
          <div>
            <h3 id="locationHistoryTitle">全部定位历史</h3>
            <div class="history-browser-note">按当前设备查询数据库快照；未定位或坐标合同未验证的记录也会列出，但不能勾选。查询条件和选择仅保存在当前页面内存中。地图只按定位时间顺序直线连接所选采样点，不代表实际行走路线；地图一次最多显示 200 点，高德坐标每批最多转换 40 点，优先保留显式历史选择。此处不作定位精度声明。</div>
          </div>
          <span id="historySelectionLabel" class="history-selection-label">地图已选 0 / 最多 200 点</span>
        </div>
        <form id="locationHistoryForm" class="history-filter-grid">
          <div class="history-filter">
            <label for="historyReceivedFrom">接收时间从</label>
            <input id="historyReceivedFrom" type="datetime-local" step="1" />
          </div>
          <div class="history-filter">
            <label for="historyReceivedTo">接收时间到</label>
            <input id="historyReceivedTo" type="datetime-local" step="1" />
          </div>
          <div class="history-filter">
            <label for="historySeq">精确序号</label>
            <input id="historySeq" type="number" min="0" step="1" inputmode="numeric" placeholder="全部" />
          </div>
          <div class="history-filter">
            <label for="historyEventType">记录类型</label>
            <select id="historyEventType">
              <option value="all">全部定位记录</option>
              <option value="location_report">GNSS 定位上报</option>
              <option value="location_observation">定位观测</option>
            </select>
          </div>
          <div class="history-filter">
            <label for="historyTrust">可选择状态</label>
            <select id="historyTrust">
              <option value="all">全部</option>
              <option value="selectable">仅可信可选</option>
              <option value="unselectable">仅不可选</option>
            </select>
          </div>
          <div class="history-filter">
            <label for="historyPageSize">每页记录</label>
            <select id="historyPageSize">
              <option value="25">25</option>
              <option value="50" selected>50</option>
              <option value="100">100</option>
            </select>
          </div>
          <div class="history-filter-actions">
            <button id="searchLocationHistory" type="submit">搜索历史</button>
            <button id="resetLocationHistory" class="secondary" type="button">重置条件</button>
            <button id="clearHistorySelection" class="secondary" type="button">清空地图选择</button>
            <span id="locationHistoryStatus" class="history-status" role="status" aria-live="polite">选择设备后加载全部定位历史</span>
          </div>
        </form>
        <div class="history-table-wrap" role="region" aria-label="全部定位历史记录" tabindex="0">
          <table class="history-table">
            <thead><tr><th><input type="checkbox" id="historySelectAll" aria-label="全选当前页"></th><th>服务端接收时间</th><th>类型</th><th>序号</th><th>定位状态</th><th>坐标可信度</th><th>固件</th></tr></thead>
            <tbody id="locationHistoryRows"><tr><td colspan="7" class="empty">尚未加载历史记录</td></tr></tbody>
          </table>
        </div>
        <div class="history-pagination">
          <span id="locationHistoryPageLabel" class="history-page-label">第 1 页</span>
          <div class="history-pagination-actions">
            <button id="previousLocationHistory" class="secondary" type="button" disabled>上一页</button>
            <button id="nextLocationHistory" class="secondary" type="button" disabled>下一页</button>
          </div>
        </div>
      </section>
      <div id="d1Link"></div>
    </section>

    <section id="fieldOperations" class="focus-panel" aria-labelledby="fieldOperationsTitle">
      <div class="section-head">
        <div>
          <h2 id="fieldOperationsTitle">设备概况</h2>
          <span class="section-kicker">设备、网络、定位、测试批次与指令状态</span>
        </div>
      </div>
      <div class="field-operations-grid">
        <div class="operation-card">
          <h3>设备最新状态</h3>
          <div id="fieldState"><span class="empty">正在等待设备状态</span></div>
        </div>
        <div class="operation-stack">
          <div class="operation-card">
            <h3>全部设备</h3>
            <div id="devices"><span class="empty">正在等待设备</span></div>
          </div>
          <div class="operation-card">
            <h3>最近指令（全部设备）</h3>
            <div id="commands" class="scroll-panel"><span class="empty">正在等待指令</span></div>
          </div>
          <div class="operation-card">
            <h3>当前测试批次</h3>
            <div id="runContext"><span class="empty">正在等待测试批次</span></div>
          </div>
        </div>
      </div>
    </section>

    <section id="photoOperations" class="focus-panel" aria-labelledby="photoOperationsTitle">
      <div class="section-head">
        <div>
          <h2 id="photoOperationsTitle">摄像头采集</h2>
          <span class="section-kicker">授权会话内单次拍照、私有预览与关联观测导出</span>
        </div>
        <div class="section-actions">
          <button id="refreshPhotos" class="secondary" type="button">刷新照片</button>
          <button id="exportPhotos" class="secondary" type="button" disabled>导出当前结果</button>
        </div>
      </div>
      <div class="photo-grid">
        <div class="operation-card photo-controls">
          <h3>采集控制</h3>
          <div class="photo-field">
            <label for="photoGuardianTokenInput">Guardian 照片控制令牌（仅本浏览器会话）</label>
            <input id="photoGuardianTokenInput" type="password" autocomplete="off" placeholder="不使用设备上传令牌" />
          </div>
          <div class="photo-actions">
            <button id="savePhotoGuardianToken" class="secondary" type="button">保存照片授权</button>
          </div>
          <div class="photo-field">
            <label for="photoRetentionDeadline">照片保留截止时间（必填）</label>
            <input id="photoRetentionDeadline" type="datetime-local" step="1" />
          </div>
          <div class="photo-actions">
            <button id="capturePhotoOnce" type="button">拍一张</button>
          </div>
          <div id="photoCommandStatus" class="photo-status warn" role="status" aria-live="polite">选择设备并明确保留截止时间后，可提交一次有时效的拍照请求。</div>
          <div class="photo-field">
            <label for="photoTimerEnabled">定时采集</label>
            <select id="photoTimerEnabled">
              <option value="disabled" selected>关闭</option>
              <option value="enabled">开启</option>
            </select>
          </div>
          <div class="photo-field">
            <label for="photoTimerInterval">采集间隔（秒）</label>
            <input id="photoTimerInterval" type="number" min="60" step="60" value="300" disabled />
          </div>
          <div class="photo-field">
            <label for="photoTimerMaxPhotos">本会话最多照片数</label>
            <input id="photoTimerMaxPhotos" type="number" min="1" max="1000" step="1" value="288" disabled />
          </div>
          <div class="photo-actions">
            <button id="applyPhotoTimer" class="secondary" type="button">提交定时配置</button>
          </div>
          <div id="photoTimerStatus" class="photo-status warn">实际设备状态：未报告；提交后先显示“待设备执行”，只有收到 ACK 才显示设备回执。重启后的持久化、可信 UTC 重新计时与不补拍语义只依据设备 ACK 和后续实际照片，不由页面推断。</div>
          <div class="photo-note">隐私边界：每次采集先建立绑定当前设备的授权会话；训练用途固定关闭。保留期限到期后删除 JPEG，仅保留审计元数据。</div>
        </div>
        <div class="operation-card">
          <h3>最近照片与采集结果</h3>
          <div class="photo-actions">
            <div class="photo-field" style="flex:1 1 260px">
              <label for="photoSessionFilter">采集会话（留空查看当前设备全部）</label>
              <input id="photoSessionFilter" autocomplete="off" placeholder="authorization_session_id" />
            </div>
          </div>
          <div id="photoActualStatus" class="photo-status warn">尚未查询；拍照请求已发送、设备已拍摄和服务端已保存是三个不同状态。</div>
          <div id="photoPreview" class="photo-preview"><span class="empty">暂无可预览照片</span></div>
          <div id="photoPreviewMeta" class="photo-note">尚无照片元数据</div>
          <div id="photoList" class="photo-list"><span class="empty">选择设备后加载照片</span></div>
        </div>
      </div>
    </section>

    <section id="fieldEvidence" class="focus-panel" aria-labelledby="fieldEvidenceTitle">
      <div class="section-head">
        <div>
          <h2 id="fieldEvidenceTitle">外场测试与数据</h2>
          <span class="section-kicker">D2 定位基线、D1 回归、功耗与 D5 数据复核</span>
        </div>
      </div>
      <div class="field-evidence-grid">
        <div class="evidence-panel">
          <h3>外场测试结果</h3>
          <div id="fieldResults"></div>
        </div>
        <div class="evidence-panel">
          <h3>数据闭环</h3>
          <div id="dataFlywheel"></div>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div>
          <h2>项目进度</h2>
          <span class="section-kicker">只读项目状态板</span>
        </div>
      </div>
      <div id="progressBoard" class="empty-panel">正在加载项目进度…</div>
    </section>

    <section>
      <h2>产品演示</h2>
      <div id="productDemo"></div>
    </section>

    <details id="modelDetails" class="dashboard-details">
      <summary>模型与标注详情</summary>
      <div class="details-body details-grid">
        <section>
          <h2>训练实验</h2>
          <div id="trainingExperiment"></div>
        </section>
        <section>
          <h2>训练运行预检</h2>
          <div id="trainingRunPreflight"></div>
        </section>
        <section>
          <h2>训练特征清单</h2>
          <div id="trainingFeatureManifest"></div>
        </section>
        <section>
          <h2>训练执行器试运行</h2>
          <div id="trainingRunnerDryRun"></div>
        </section>
        <section>
          <h2>训练基线评估</h2>
          <div id="trainingBaselineEval"></div>
        </section>
        <section>
          <h2>训练交接包</h2>
          <div id="trainingHandoffBundle"></div>
        </section>
        <section>
          <h2>训练任务计划</h2>
          <div id="trainingJobPlan"></div>
        </section>
        <section>
          <h2>合成训练链路</h2>
          <div id="syntheticTrainingChain"></div>
        </section>
        <section>
          <h2>D1 训练就绪度</h2>
          <div id="d1TrainingReadiness"></div>
        </section>
        <section>
          <h2>D1 标注接入</h2>
          <div id="d1LabelingIntake"></div>
        </section>
        <section>
          <h2>D1 标注队列</h2>
          <div id="d1LabelingQueue"></div>
        </section>
        <section>
          <h2>D1 标注复核包</h2>
          <div id="d1LabelingReviewPacket"></div>
        </section>
        <section>
          <h2>D1 标注决策模板</h2>
          <div id="d1LabelingDecisionTemplate"></div>
        </section>
      </div>
    </details>

    <details id="diagnosticsDetails" class="dashboard-details">
      <summary>诊断与消息历史</summary>
      <div class="details-body details-grid">
        <section>
          <h2>原始帧</h2>
          <div id="rawFrames" class="scroll-panel"></div>
        </section>
        <section>
          <h2>最近消息</h2>
          <div class="table-scroll" role="region" aria-label="最近消息表格" tabindex="0">
            <table><thead><tr><th>设备</th><th>类型</th><th>序号</th><th>详情</th><th>接收时间</th></tr></thead><tbody id="messages"></tbody></table>
          </div>
        </section>
      </div>
    </details>
  </main>
  <script>
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function detail(message) {
      return message.event_type || message.cmd_id || message.error_code || message.link_type || message.status || '';
    }
    function ageClass(lastSeen) {
      if (!lastSeen) return 'bad';
      const ageMs = Date.now() - Date.parse(lastSeen);
      if (!Number.isFinite(ageMs)) return 'warn';
      if (ageMs < 30000) return 'ok';
      if (ageMs < 120000) return 'warn';
      return 'bad';
    }
    function onlineLabel(lastSeen) {
      const cls = ageClass(lastSeen);
      if (cls === 'ok') return 'online';
      if (cls === 'warn') return 'stale';
      return 'offline';
    }
    function onlineDisplayLabel(lastSeen) {
      const state = onlineLabel(lastSeen);
      if (state === 'online') return '在线';
      if (state === 'stale') return '数据已变旧';
      return '离线';
    }
    function displayState(value) {
      const raw = String(value ?? '').trim();
      const normalized = raw.toLowerCase();
      const labels = {
        ready: '就绪', stale: '已过期', not_ready: '未就绪', waiting_for_data: '等待数据',
        fine: '精确定位', coarse: '粗略定位', predicted: '预测位置', unknown: '无可靠位置',
        no_fix: '未定位', fix: '已定位', ok: '正常', pending: '等待中', blocked: '已阻塞',
        pass: '通过', fail: '失败', observed: '已观测', unverified: '未验证',
      };
      const translated = labels[normalized];
      if (!translated) return raw || '未知';
      return raw && translated !== raw ? `${translated}（${raw}）` : translated;
    }
    function formatDashboardDateTime(value) {
      const parsed = Date.parse(value || '');
      if (!Number.isFinite(parsed)) return '时间未知';
      return new Intl.DateTimeFormat('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }).format(new Date(parsed));
    }
    function formatDashboardClock(value) {
      const parsed = Date.parse(value || '');
      if (!Number.isFinite(parsed)) return '时间未知';
      return new Intl.DateTimeFormat('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(new Date(parsed));
    }
    function formatDashboardDuration(startValue, endValue) {
      const start = Date.parse(startValue || '');
      const end = Date.parse(endValue || '');
      if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '未知';
      const totalMinutes = Math.max(0, Math.round((end - start) / 60000));
      if (totalMinutes < 60) return `${totalMinutes} 分钟`;
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`;
    }
    function gnssField(telemetry, key, fallback = 'unknown') {
      const nested = telemetry.gnss || (telemetry.payload && telemetry.payload.gnss ? telemetry.payload.gnss : {});
      const alias = key === 'gnss_state' ? (nested.state ?? nested.result) : undefined;
      const value = telemetry[key] ?? nested[key] ?? alias;
      return value === undefined || value === null || value === '' ? fallback : value;
    }
    function currentToken() {
      return localStorage.getItem('egolinkHubToken') || '';
    }
    function authHeaders() {
      const token = currentToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    }
    function photoGuardianToken() {
      return sessionStorage.getItem('egolinkPhotoGuardianToken') || '';
    }
    function photoAuthHeaders() {
      const token = photoGuardianToken();
      return token ? {Authorization: `Bearer ${token}`} : {};
    }
    const D2_MAP_REVIEW_KEY = 'egolink.d2.map_review.v1';
    const D2_MAP_REVIEW_DISABLED_KEY = 'egolink.d2.map_review.disabled.v1';
    const D2_CAPTURE_KEY = 'egolink.d2.reference_capture.v1';
    const D2_MANIFEST_MAX_BYTES = 262144;
    const D2_REFERENCE_POINT_LIMIT = 16;
    const DASHBOARD_DEVICE_KEY = 'egolink.dashboard.device.v1';
    const PHOTO_COMMAND_TTL_MS = 2 * 60 * 1000;
    const PHOTO_CONFIG_VERSION = 'photo-control-v0.1';
    const PHOTO_TIMER_DEFAULT_INTERVAL_SECONDS = 300;
    const PHOTO_TIMER_DEFAULT_MAX_PHOTOS = 288;
    const AMAP_JS_API_KEY = '__AMAP_JS_API_KEY__';
    const AMAP_JS_API_CALLBACK = '__egolinkAmapJsApiReady';
    const AMAP_JS_API_SCRIPT_ID = 'egolink-amap-js-api';
    const AMAP_SDK_LOAD_TIMEOUT_MS = 30000;
    const AMAP_MAP_READY_TIMEOUT_MS = 30000;
    const TRAJECTORY_RENDER_POINT_LIMIT = 200;
    const AMAP_CONVERT_BATCH_LIMIT = 40;
    let selectedDashboardDeviceId = localStorage.getItem(DASHBOARD_DEVICE_KEY) || '';
    let refreshInFlight = false;
    let lastSuccessfulDashboardState = null;
    let localD2MapReview = null;
    let amapNamespace = null;
    let amapInstance = null;
    let amapOverlays = [];
    let amapLoadPromise = null;
    let amapMapReady = false;
    let amapRenderGeneration = 0;
    let amapConversionCacheKey = '';
    let amapConversionCacheValue = [];
    let amapConversionInFlightKey = '';
    let amapConversionInFlightPromise = null;
    let amapOverlayCacheKey = '';
    let amapOverlayFailureKey = '';
    const trajectorySelectionByDevice = new Map();
    const locationHistoryByDevice = new Map();
    let locationHistoryActiveDeviceId = '';
    let photoRequestGeneration = 0;
    let photoPreviewGeneration = 0;
    let photoPreviewObjectUrl = '';
    let currentPhotoExport = null;
    let currentPhotoSession = null;
    function selectDashboardDevice(devices, currentRun = {}, preferredDeviceId = selectedDashboardDeviceId) {
      const available = Array.isArray(devices)
        ? devices.filter(device => device && device.device_id)
        : [];
      if (!available.length) return null;
      const preferred = available.find(device => device.device_id === preferredDeviceId);
      if (preferred) return preferred;
      const runDeviceId = currentRun && currentRun.device_id ? currentRun.device_id : '';
      const runDevice = available.find(device => device.device_id === runDeviceId);
      if (runDevice) return runDevice;
      return [...available].sort((left, right) => {
        const leftSeen = Date.parse(left.last_seen_at || '') || 0;
        const rightSeen = Date.parse(right.last_seen_at || '') || 0;
        return rightSeen - leftSeen;
      })[0];
    }
    function updateDeviceSelector(devices, currentRun = {}) {
      const available = Array.isArray(devices) ? devices : [];
      const selectedDevice = selectDashboardDevice(available, currentRun);
      deviceSelector.innerHTML = available.map(device => {
        const label = `${device.device_id} / ${onlineDisplayLabel(device.last_seen_at)}`;
        return `<option value="${escapeHtml(device.device_id)}">${escapeHtml(label)}</option>`;
      }).join('') || '<option value="">暂无可用设备</option>';
      deviceSelector.disabled = !available.length;
      deviceSelector.value = selectedDevice ? selectedDevice.device_id : '';
      return selectedDevice;
    }
    function finiteCoordinate(value, min, max, field) {
      if (value === null || value === undefined || String(value).trim() === '') {
        throw new Error(`missing ${field}`);
      }
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
        throw new Error(`invalid ${field}`);
      }
      return parsed;
    }
    function compactD2MapReview(manifest) {
      if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
        throw new Error('manifest must be a JSON object');
      }
      const sourcePoints = Array.isArray(manifest.reference_points) ? manifest.reference_points : [];
      if (!sourcePoints.length) throw new Error('manifest has no reference points');
      if (sourcePoints.length > D2_REFERENCE_POINT_LIMIT) {
        throw new Error(`reference point limit is ${D2_REFERENCE_POINT_LIMIT}`);
      }
      const referencePoints = sourcePoints.map((point, index) => {
        const reference = point && typeof point.reference === 'object' ? point.reference : point || {};
        return {
          point_id: String(point.point_id || `reference-${index + 1}`).slice(0, 96),
          label: String(point.label || point.name || point.point_id || `D2 reference ${index + 1}`).slice(0, 120),
          lat: finiteCoordinate(reference.lat, -90, 90, 'latitude'),
          lon: finiteCoordinate(reference.lon, -180, 180, 'longitude'),
          source: 'browser_local_manifest',
        };
      });
      return {
        schema_version: 'egolink.d2_map_review.v0.1',
        field_run_id: String(manifest.field_run_id || manifest.run_id || 'local-reference-review').slice(0, 120),
        device_id: String(manifest.device_id || '').slice(0, 120),
        reference_points: referencePoints,
      };
    }
    function loadLocalD2MapReview() {
      const savedReview = localStorage.getItem(D2_MAP_REVIEW_KEY);
      const keys = savedReview
        ? [D2_MAP_REVIEW_KEY]
        : localStorage.getItem(D2_MAP_REVIEW_DISABLED_KEY) ? [] : [D2_CAPTURE_KEY];
      for (const key of keys) {
        try {
          const raw = localStorage.getItem(key);
          if (!raw) continue;
          const review = compactD2MapReview(JSON.parse(raw));
          localStorage.setItem(D2_MAP_REVIEW_KEY, JSON.stringify(review));
          return review;
        } catch (_error) {
          if (key === D2_MAP_REVIEW_KEY) localStorage.removeItem(key);
        }
      }
      return null;
    }
    function setD2ManifestStatus(message, state = '') {
      d2ManifestStatus.textContent = message;
      d2ManifestStatus.className = `map-import-status ${state}`.trim();
      clearD2References.disabled = !localD2MapReview;
    }
    function updateD2ManifestStatus(deviceId = '') {
      if (!localD2MapReview) {
        setD2ManifestStatus('暂无本地参考点');
        return;
      }
      if (localD2MapReview.device_id && deviceId && localD2MapReview.device_id !== deviceId) {
        setD2ManifestStatus(`${localD2MapReview.reference_points.length} 个参考点 / 设备不匹配`, 'warn');
        return;
      }
      setD2ManifestStatus(
        `${localD2MapReview.reference_points.length} 个参考点 / ${localD2MapReview.field_run_id}`,
        'ok',
      );
    }
    function mapWithLocalReferences(map, deviceId) {
      let runtimeMap = map || {};
      if (AMAP_JS_API_KEY) {
        runtimeMap = {
          ...runtimeMap,
          review_mode: 'amap_live_with_local_fallback',
          provider: {
            ...(runtimeMap.provider || {}),
            mode: 'amap_js_api_v2',
            status: 'configured',
            blocking_d1: false,
          },
          layers: {...(runtimeMap.layers || {}), provider_tiles: true},
        };
      }
      if (!localD2MapReview) return runtimeMap;
      if (localD2MapReview.device_id && deviceId && localD2MapReview.device_id !== deviceId) {
        return runtimeMap;
      }
      const references = localD2MapReview.reference_points || [];
      return {
        ...runtimeMap,
        reference_points: references,
        reference_source: 'browser_local_manifest',
        layers: {...(runtimeMap.layers || {}), reference_points: references.length > 0},
      };
    }
    function defaultLocationHistoryFilters() {
      return {
        received_from: null,
        received_to: null,
        seq: null,
        event_type: 'all',
        trust: 'all',
        page_size: 50,
      };
    }
    function newLocationHistoryState() {
      return {
        filters: defaultLocationHistoryFilters(),
        cursor: null,
        cursorStack: [],
        pageNumber: 1,
        records: [],
        nextCursor: null,
        exhausted: false,
        inspectedCount: 0,
        loaded: false,
        loading: false,
        error: '',
        selectedRecords: new Map(),
        requestGeneration: 0,
      };
    }
    function locationHistoryStateForDevice(deviceId) {
      let state = locationHistoryByDevice.get(deviceId);
      if (!state) {
        state = newLocationHistoryState();
        locationHistoryByDevice.set(deviceId, state);
      }
      return state;
    }
    function locationHistorySelectedPoints(deviceId) {
      const state = locationHistoryByDevice.get(deviceId);
      return state && state.selectedRecords instanceof Map
        ? [...state.selectedRecords.values()]
        : [];
    }
    function clearLocationHistorySelectionForDevice(deviceId) {
      const state = locationHistoryByDevice.get(deviceId);
      if (state) state.selectedRecords = new Map();
    }
    function selectedDashboardDevice() {
      if (!lastSuccessfulDashboardState) return null;
      return selectDashboardDevice(
        lastSuccessfulDashboardState.devices || [],
        lastSuccessfulDashboardState.current_run || {},
      );
    }
    function setPhotoStatus(element, message, state = '') {
      element.textContent = message;
      element.className = `photo-status ${state}`.trim();
    }
    function photoControlId(prefix) {
      const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2, 14);
      return `${prefix}-${Date.now().toString(36)}-${random}`.slice(0, 128);
    }
    function photoRetention() {
      const raw = photoRetentionDeadline.value;
      if (!raw) throw new Error('请先明确照片保留截止时间');
      const parsed = new Date(raw);
      const expiresAtUnixMs = parsed.getTime();
      if (!Number.isFinite(expiresAtUnixMs) || expiresAtUnixMs <= Date.now() + 60_000) {
        throw new Error('照片保留截止时间必须至少在 1 分钟以后');
      }
      return {retention_expires_at: parsed.toISOString(), expires_at_unix_ms: expiresAtUnixMs};
    }
    async function photoJson(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: {...photoAuthHeaders(), ...(options.headers || {})},
        cache: 'no-store',
      });
      let body = {};
      try {
        body = await response.json();
      } catch (_error) {
        body = {};
      }
      if (!response.ok) {
        const error = new Error(body.detail || body.error || `HTTP ${response.status}`);
        error.code = body.error || `http_${response.status}`;
        throw error;
      }
      return body;
    }
    async function authorizePhotoSession(deviceId, retention) {
      const session = {
        authorization_session_id: photoControlId('photo-session'),
        retention_expires_at: retention.retention_expires_at,
        training_allowed: false,
      };
      const result = await photoJson(
        `/api/v1/devices/${encodeURIComponent(deviceId)}/photos/sessions`,
        {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(session),
        },
      );
      currentPhotoSession = result.authorization_session || session;
      photoSessionFilter.value = session.authorization_session_id;
      return session;
    }
    function photoCommandState(command) {
      if (!command) return {text: '尚无服务端照片指令', state: 'warn', applied: false};
      const status = String(command.status || 'unknown').toLowerCase();
      const ack = command.ack && typeof command.ack === 'object' ? command.ack : {};
      const ackStatus = String(ack.status || '').toLowerCase();
      if (status === 'pending') {
        return {text: `指令 ${command.cmd_id} 已持久化，待设备执行；尚未 ACK`, state: 'warn', applied: false};
      }
      if (status === 'expired') {
        return {text: `指令 ${command.cmd_id} 已过期，不能视为设备已执行`, state: 'bad', applied: false};
      }
      const verifiedApplied = status === 'applied'
        && ackStatus === 'applied'
        && ['terminal_ack_applied', 'terminal_state_refresh_applied'].includes(ack.server_disposition);
      if (verifiedApplied) {
        return {text: `指令 ${command.cmd_id} 已收到设备 ACK：applied`, state: 'ok', applied: true};
      }
      if (status === 'applied' || ackStatus === 'applied' || ack.apply_status === 'applied') {
        return {text: `指令 ${command.cmd_id} 的 applied 记录不完整，不作为已生效事实`, state: 'warn', applied: false};
      }
      if (['error', 'failed', 'rejected'].includes(status) || ['error', 'failed', 'rejected'].includes(ackStatus)) {
        return {text: `指令 ${command.cmd_id} 返回错误：${ack.error_code || ackStatus || status}`, state: 'bad', applied: false};
      }
      return {text: `指令 ${command.cmd_id} 已收到 ACK：${ackStatus || status}；回执未明确 applied`, state: 'warn', applied: false};
    }
    function clearPhotoPreview() {
      photoPreviewGeneration += 1;
      if (photoPreviewObjectUrl) {
        URL.revokeObjectURL(photoPreviewObjectUrl);
        photoPreviewObjectUrl = '';
      }
      photoPreview.innerHTML = '<span class="empty">暂无可预览照片</span>';
      photoPreviewMeta.textContent = '尚无照片元数据';
    }
    function renderPhotoList(data, commands, cameraRuntimeState) {
      const photos = Array.isArray(data.photos) ? data.photos : [];
      const captureCommand = commands.find(command => command.cmd === 'capture_photo_once');
      const latestTimerCommand = commands.find(command => command.cmd === 'configure_photo_timer');
      const latestAppliedTimerCommand = commands.find(command =>
        command.cmd === 'configure_photo_timer' && photoCommandState(command).applied
      );
      const captureState = photoCommandState(captureCommand);
      setPhotoStatus(photoCommandStatus, captureState.text, captureState.state);
      const timerState = photoCommandState(latestTimerCommand);
      const appliedTimerState = photoCommandState(latestAppliedTimerCommand);
      const runtimeEnvelope = cameraRuntimeState && cameraRuntimeState.envelope && typeof cameraRuntimeState.envelope === 'object'
        ? cameraRuntimeState.envelope : {};
      const runtimePayload = runtimeEnvelope.payload && typeof runtimeEnvelope.payload === 'object'
        ? runtimeEnvelope.payload : {};
      const runtimeTimerCandidate = runtimePayload.timer_state && typeof runtimePayload.timer_state === 'object'
        ? runtimePayload.timer_state : null;
      const runtimeTimerKeys = runtimeTimerCandidate ? Object.keys(runtimeTimerCandidate).sort() : [];
      const expectedRuntimeTimerKeys = [
        'captured_count', 'config_version', 'enabled', 'interval_seconds',
        'max_photos', 'session_expires_at_unix_ms', 'state_reason', 'trusted_utc',
      ];
      const runtimeTimer = runtimeTimerCandidate
        && JSON.stringify(runtimeTimerKeys) === JSON.stringify(expectedRuntimeTimerKeys)
        && typeof runtimeTimerCandidate.config_version === 'string'
        && /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/.test(runtimeTimerCandidate.config_version || '')
        && typeof runtimeTimerCandidate.enabled === 'boolean'
        && Number.isInteger(runtimeTimerCandidate.interval_seconds)
        && runtimeTimerCandidate.interval_seconds >= 60
        && runtimeTimerCandidate.interval_seconds <= 86400
        && Number.isSafeInteger(runtimeTimerCandidate.session_expires_at_unix_ms)
        && runtimeTimerCandidate.session_expires_at_unix_ms > 0
        && Number.isInteger(runtimeTimerCandidate.max_photos)
        && runtimeTimerCandidate.max_photos >= 1
        && runtimeTimerCandidate.max_photos <= 1000
        && Number.isInteger(runtimeTimerCandidate.captured_count)
        && runtimeTimerCandidate.captured_count >= 0
        && runtimeTimerCandidate.captured_count <= runtimeTimerCandidate.max_photos
        && typeof runtimeTimerCandidate.state_reason === 'string'
        && /^[a-z][a-z0-9_]{0,63}$/.test(runtimeTimerCandidate.state_reason)
        && typeof runtimeTimerCandidate.trusted_utc === 'boolean'
        ? runtimeTimerCandidate : null;
      const ackTimer = appliedTimerState.applied && latestAppliedTimerCommand
        && latestAppliedTimerCommand.ack
        && typeof latestAppliedTimerCommand.ack.timer_state === 'object'
        ? latestAppliedTimerCommand.ack.timer_state : null;
      const runtimeReceivedAt = cameraRuntimeState && cameraRuntimeState.server_received_at;
      const runtimeAfterAck = runtimeReceivedAt && latestAppliedTimerCommand
        && latestAppliedTimerCommand.updated_at
        && Number.isFinite(Date.parse(runtimeReceivedAt))
        && Number.isFinite(Date.parse(latestAppliedTimerCommand.updated_at))
        && Date.parse(runtimeReceivedAt) >= Date.parse(latestAppliedTimerCommand.updated_at);
      const runtimeMatchesApplied = Boolean(
        runtimeTimer && ackTimer && runtimeEnvelope.status === 'observed'
        && runtimeTimer.config_version === ackTimer.config_version
        && runtimeTimer.captured_count >= ackTimer.captured_count
        && runtimeAfterAck
      );
      const reportedTimer = runtimeMatchesApplied ? runtimeTimer : ackTimer;
      const reportedAt = runtimeMatchesApplied
        ? (runtimeEnvelope.timestamp_utc || cameraRuntimeState.server_received_at)
        : latestAppliedTimerCommand && latestAppliedTimerCommand.updated_at;
      const reportedSessionDeadlineDate = reportedTimer
        ? new Date(reportedTimer.session_expires_at_unix_ms) : null;
      const reportedSessionDeadline = reportedSessionDeadlineDate
        && Number.isFinite(reportedSessionDeadlineDate.getTime())
        ? reportedSessionDeadlineDate.toISOString() : null;
      const reportedSessionExpired = Boolean(
        reportedTimer && reportedTimer.enabled
        && Date.now() >= reportedTimer.session_expires_at_unix_ms
      );
      const staleRuntimeNote = runtimeTimer && !runtimeMatchesApplied
        ? ` 设备另有一条未绑定到最新 verified applied 指令的历史状态（配置 ${runtimeTimer.config_version || '未知'}），不作为当前生效事实。`
        : '';
      const actualTimerBase = reportedTimer
        ? `设备最近报告 ${formatDashboardDateTime(reportedAt)}：定时采集${reportedTimer.enabled ? '开启' : '关闭'}，配置 ${reportedTimer.config_version || '未知'}，间隔 ${reportedTimer.interval_seconds || '未知'} 秒，会话截止 ${formatDashboardDateTime(reportedSessionDeadline)}，已拍 ${reportedTimer.captured_count ?? '未知'} / ${reportedTimer.max_photos ?? '未知'}，原因 ${reportedTimer.state_reason || '未报告'}，可信 UTC ${reportedTimer.trusted_utc === true ? '是' : '否'}。${reportedSessionExpired ? ' 最后报告为开启，但授权会话截止已过；等待设备状态确认，不能视为当前仍在采集。' : ''}`
        : appliedTimerState.applied
          ? `设备曾 ACK applied，但未回报可核验的 timer_state；不能据请求参数推断当前仍生效。`
          : `${timerState.text}。设备实际配置仍为未报告。`;
      const pendingTimerNote = latestTimerCommand && latestAppliedTimerCommand
        && latestTimerCommand.cmd_id !== latestAppliedTimerCommand.cmd_id
        ? ` 最新定时请求：${timerState.text}。在设备 ACK 前，上述已验证实际配置仍然有效。`
        : '';
      const actualTimer = `${actualTimerBase}${staleRuntimeNote}${pendingTimerNote}`;
      const actualTimerState = reportedTimer
        ? (reportedTimer.state_reason === 'state_error' ? 'bad' :
          reportedSessionExpired ? 'warn' : reportedTimer.enabled ? 'ok' : 'warn')
        : timerState.state;
      setPhotoStatus(photoTimerStatus, actualTimer, actualTimerState);
      exportPhotos.disabled = !photos.length;
      photoList.innerHTML = photos.map(photo => {
        const content = photo.content || {};
        const backfillLabel = photo.backfill && photo.backfill.is_backfill ? ' · 延迟补传' : '';
        return `<button type="button" class="photo-list-item" data-photo-id="${escapeHtml(photo.photo_id)}">
          <strong>${escapeHtml(photo.photo_id)} · ${escapeHtml(photo.capture_result)}</strong>
          <span>拍摄 ${escapeHtml(formatDashboardDateTime(photo.event_utc))} · 接收 ${escapeHtml(formatDashboardDateTime(photo.server_received_at))}${backfillLabel} · ${escapeHtml(photo.trigger_reason)} · server ${escapeHtml(content.status || 'unknown')}</span>
        </button>`;
      }).join('') || '<span class="empty">当前设备/会话尚无照片观测</span>';
      photoList.querySelectorAll('[data-photo-id]').forEach(button => {
        button.addEventListener('click', () => void loadPhotoPreview(button.dataset.photoId));
      });
      const latest = photos[0];
      if (!latest) {
        setPhotoStatus(
          photoActualStatus,
          captureCommand && captureCommand.status === 'pending'
            ? '拍照命令待设备执行；尚未收到本会话的拍照结果。'
            : '尚无真实照片观测；不会用历史图片或静态示例代替。',
          'warn',
        );
        clearPhotoPreview();
        return;
      }
      const content = latest.content || {};
      const uploadAttempts = latest.upload_attempts || {};
      const aggregate = data.aggregate || {};
      const pendingUploads = Number(aggregate.pending_content_count || 0);
      const corruptContent = Number(aggregate.corrupt_content_count || 0);
      let statusText = `最近收到结果 ${latest.capture_result}；拍摄 ${formatDashboardDateTime(latest.event_utc)}；服务端接收 ${formatDashboardDateTime(latest.server_received_at)}；设备保存 ${latest.local_save_status}；服务端内容 ${content.status || 'unknown'}；本筛选范围待上传 ${pendingUploads}，损坏待同 ID 修复 ${corruptContent}。`;
      let statusClass = content.status === 'stored' ? 'ok' : 'warn';
      if (latest.capture_result === 'capture_failed' || latest.local_save_status === 'save_failed'
          || latest.capture_result === 'outcome_unknown' || latest.local_save_status === 'unknown') statusClass = 'bad';
      if (latest.capture_result === 'outcome_unknown') statusText += ' 设备在拍摄事务中重启，无法证明当时是否完成拍摄或保存；该结果不会伪装成未尝试或成功。';
      if (content.status === 'stored') statusText += ` JPEG 已按 ${content.verification_scope || '未报告范围'} 校验并持久保存；浏览器成功解码仍是独立实机验收事实。`;
      else if (content.status === 'pending') statusText += ' 元数据已到达，JPEG 仍待上传。';
      else if (content.status === 'not_expected') statusText += ' 本次未形成可上传 JPEG，不计入待传。';
      else if (content.status === 'expired' && content.purge_state === 'complete') statusText += ' 保留期限已到，JPEG 删除已完成。';
      else if (content.status === 'expired') {
        statusText += ` 保留期限已到且访问已撤销；物理删除状态 ${content.purge_state || '未报告'}，后台将继续重试。`;
        statusClass = 'bad';
      }
      else if (content.status === 'corrupt') {
        statusText += ' 已存内容校验失败，等待同一可信照片有界修复。';
        statusClass = 'bad';
      }
      if (uploadAttempts.last_error_code) statusText += ` 最近上传失败 ${uploadAttempts.last_error_code}（${formatDashboardDateTime(uploadAttempts.last_attempt_at)}）。`;
      if (latest.backfill && latest.backfill.is_backfill) statusText += ` 这是延迟补传，接收比拍摄晚 ${latest.backfill.age_seconds} 秒，不代表当前位置或刚刚拍摄。`;
      setPhotoStatus(photoActualStatus, statusText, statusClass);
      if (content.status === 'stored') void loadPhotoPreview(latest.photo_id);
      else clearPhotoPreview();
    }
    async function loadPhotoPreview(photoId) {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice || !photoId) return;
      const generation = photoRequestGeneration;
      const previewGeneration = ++photoPreviewGeneration;
      try {
        const response = await fetch(
          `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/photos/${encodeURIComponent(photoId)}/content`,
          {headers: photoAuthHeaders(), cache: 'no-store'},
        );
        if (!response.ok) throw new Error(`照片预览 HTTP ${response.status}`);
        const blob = await response.blob();
        if (generation !== photoRequestGeneration || previewGeneration !== photoPreviewGeneration) return;
        const objectUrl = URL.createObjectURL(blob);
        const image = document.createElement('img');
        image.src = objectUrl;
        image.alt = `照片 ${photoId}`;
        try {
          await image.decode();
        } catch (_) {
          URL.revokeObjectURL(objectUrl);
          throw new Error('照片字节已取得，但浏览器无法解码 JPEG');
        }
        if (generation !== photoRequestGeneration || previewGeneration !== photoPreviewGeneration) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        clearPhotoPreview();
        photoPreviewObjectUrl = objectUrl;
        photoPreview.innerHTML = '';
        photoPreview.appendChild(image);
        const metadata = currentPhotoExport && Array.isArray(currentPhotoExport.photos)
          ? currentPhotoExport.photos.find(photo => photo.photo_id === photoId) : null;
        photoPreviewMeta.textContent = metadata
          ? `${photoId} · 拍摄 ${formatDashboardDateTime(metadata.event_utc)} · ${metadata.trigger_reason} · ${blob.size} bytes · 浏览器已解码 · 仅授权会话内预览`
          : `${photoId} · ${blob.size} bytes · 浏览器已解码 · 仅授权会话内预览`;
      } catch (error) {
        if (generation !== photoRequestGeneration || previewGeneration !== photoPreviewGeneration) return;
        clearPhotoPreview();
        const detail = error instanceof Error ? error.message : '照片预览失败';
        photoPreviewMeta.textContent = detail;
        setPhotoStatus(photoActualStatus, `服务端照片预览失败：${detail}`, 'bad');
      }
    }
    async function loadPhotosForSelectedDevice() {
      const selectedDevice = selectedDashboardDevice();
      const generation = ++photoRequestGeneration;
      clearPhotoPreview();
      if (!selectedDevice) {
        photoList.innerHTML = '<span class="empty">请先选择设备</span>';
        setPhotoStatus(photoActualStatus, '尚未选择设备', 'warn');
        return;
      }
      const sessionId = photoSessionFilter.value.trim();
      if (sessionId && !/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/.test(sessionId)) {
        setPhotoStatus(photoActualStatus, '采集会话标识格式无效', 'bad');
        return;
      }
      setPhotoStatus(photoActualStatus, '正在查询私有照片元数据…', 'warn');
      try {
        const query = new URLSearchParams({limit: '50'});
        if (sessionId) query.set('session_id', sessionId);
        const prefix = `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/photos`;
        const [data, commandData] = await Promise.all([
          photoJson(`${prefix}?${query.toString()}`),
          photoJson(`${prefix}/commands`),
        ]);
        if (generation !== photoRequestGeneration) return;
        currentPhotoExport = data;
        renderPhotoList(
          data,
          Array.isArray(commandData.commands) ? commandData.commands : [],
          commandData.camera_runtime_state || null,
        );
      } catch (error) {
        if (generation !== photoRequestGeneration) return;
        currentPhotoExport = null;
        exportPhotos.disabled = true;
        photoList.innerHTML = '<span class="empty">照片查询失败</span>';
        setPhotoStatus(
          photoActualStatus,
          `照片查询失败：${error && error.code ? error.code : error}`,
          'bad',
        );
      }
    }
    async function submitCapturePhotoOnce() {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) {
        setPhotoStatus(photoCommandStatus, '请先选择设备', 'bad');
        return;
      }
      capturePhotoOnce.disabled = true;
      try {
        const retention = photoRetention();
        setPhotoStatus(photoCommandStatus, '正在建立本次 Guardian 授权会话…', 'warn');
        const session = await authorizePhotoSession(selectedDevice.device_id, retention);
        const issuedAt = Date.now();
        const result = await photoJson(
          `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/photos/commands/capture`,
          {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              cmd_id: photoControlId('capture-photo'),
              expires_at_unix_ms: Math.min(issuedAt + PHOTO_COMMAND_TTL_MS, retention.expires_at_unix_ms),
              payload: {
                authorization_session_id: session.authorization_session_id,
                retention_expires_at: retention.retention_expires_at,
                training_allowed: false,
                trigger_reason: 'web_manual',
              },
            }),
          },
        );
        const state = photoCommandState(result.command);
        setPhotoStatus(photoCommandStatus, state.text, state.state);
        await loadPhotosForSelectedDevice();
      } catch (error) {
        setPhotoStatus(
          photoCommandStatus,
          `拍照请求未入队：${error instanceof Error ? error.message : error}`,
          'bad',
        );
      } finally {
        capturePhotoOnce.disabled = false;
      }
    }
    async function submitPhotoTimer() {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) {
        setPhotoStatus(photoTimerStatus, '请先选择设备', 'bad');
        return;
      }
      applyPhotoTimer.disabled = true;
      try {
        const retention = photoRetention();
        const enabled = photoTimerEnabled.value === 'enabled';
        const intervalSeconds = Number(photoTimerInterval.value || PHOTO_TIMER_DEFAULT_INTERVAL_SECONDS);
        const maxPhotos = Number(photoTimerMaxPhotos.value || PHOTO_TIMER_DEFAULT_MAX_PHOTOS);
        if (!Number.isInteger(intervalSeconds) || intervalSeconds < 60 || intervalSeconds > 86400) {
          throw new Error('定时间隔必须是 60–86400 秒的整数');
        }
        if (!Number.isInteger(maxPhotos) || maxPhotos < 1 || maxPhotos > 1000) {
          throw new Error('照片上限必须是 1–1000 的整数');
        }
        setPhotoStatus(photoTimerStatus, '正在建立本次 Guardian 授权会话…', 'warn');
        const session = await authorizePhotoSession(selectedDevice.device_id, retention);
        const issuedAt = Date.now();
        const result = await photoJson(
          `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/photos/commands/timer`,
          {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              cmd_id: photoControlId('photo-timer'),
              expires_at_unix_ms: Math.min(issuedAt + PHOTO_COMMAND_TTL_MS, retention.expires_at_unix_ms),
              payload: {
                authorization_session_id: session.authorization_session_id,
                config_version: `${PHOTO_CONFIG_VERSION}-${issuedAt.toString(36)}`,
                enabled,
                interval_seconds: intervalSeconds,
                session_expires_at_unix_ms: retention.expires_at_unix_ms,
                retention_expires_at: retention.retention_expires_at,
                max_photos: maxPhotos,
                training_allowed: false,
              },
            }),
          },
        );
        const state = photoCommandState(result.command);
        const prefix = enabled ? '开启配置' : '停止配置';
        setPhotoStatus(photoTimerStatus, `${prefix}：${state.text}`, state.state);
        await loadPhotosForSelectedDevice();
      } catch (error) {
        setPhotoStatus(
          photoTimerStatus,
          `定时配置未入队：${error instanceof Error ? error.message : error}`,
          'bad',
        );
      } finally {
        applyPhotoTimer.disabled = false;
      }
    }
    async function exportCurrentPhotos() {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) return;
      exportPhotos.disabled = true;
      try {
        const query = new URLSearchParams();
        const sessionId = photoSessionFilter.value.trim();
        if (sessionId) query.set('session_id', sessionId);
        const response = await fetch(
          `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/photos/export.json?${query.toString()}`,
          {headers: photoAuthHeaders(), cache: 'no-store'},
        );
        if (!response.ok) throw new Error(`导出 HTTP ${response.status}`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `egolink-${selectedDevice.device_id}-photo-observations.json`;
        link.click();
        URL.revokeObjectURL(url);
        setPhotoStatus(photoActualStatus, '已完整导出当前设备/会话的照片元数据与关联 collection observation；不包含 JPEG。', 'ok');
      } catch (error) {
        setPhotoStatus(photoActualStatus, `照片导出失败：${error}`, 'bad');
      } finally {
        exportPhotos.disabled = !(currentPhotoExport && currentPhotoExport.photos && currentPhotoExport.photos.length);
      }
    }
    function localDateTimeValue(isoValue) {
      const parsed = new Date(isoValue || '');
      if (!Number.isFinite(parsed.getTime())) return '';
      const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
      return local.toISOString().slice(0, 19);
    }
    function syncLocationHistoryControls(filters) {
      document.getElementById('historyReceivedFrom').value = localDateTimeValue(filters.received_from);
      document.getElementById('historyReceivedTo').value = localDateTimeValue(filters.received_to);
      document.getElementById('historySeq').value = filters.seq === null ? '' : String(filters.seq);
      document.getElementById('historyEventType').value = filters.event_type;
      document.getElementById('historyTrust').value = filters.trust;
      document.getElementById('historyPageSize').value = String(filters.page_size);
    }
    function isoFromHistoryControl(controlId) {
      const raw = document.getElementById(controlId).value;
      if (!raw) return null;
      // Build the selected wall-clock time in the browser's local zone. The
      // Date constructor applies the offset for that selected date, so a
      // historical winter query is not shifted by today's summer/DST offset.
      const match = /^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2})(?::(\\d{2})(?:\\.(\\d{1,3}))?)?$/.exec(raw);
      if (!match) throw new Error('时间格式无效');
      const parts = match.slice(1, 7).map((value) => Number(value || 0));
      const milliseconds = Number((match[7] || '').padEnd(3, '0') || 0);
      const parsed = new Date(
        parts[0], parts[1] - 1, parts[2], parts[3], parts[4], parts[5], milliseconds,
      );
      if (!Number.isFinite(parsed.getTime())) throw new Error('时间格式无效');
      if (
        parsed.getFullYear() !== parts[0]
        || parsed.getMonth() !== parts[1] - 1
        || parsed.getDate() !== parts[2]
        || parsed.getHours() !== parts[3]
        || parsed.getMinutes() !== parts[4]
        || parsed.getSeconds() !== parts[5]
      ) throw new Error('时间格式无效或本地时间不存在');
      return parsed.toISOString();
    }
    function locationHistoryFiltersFromControls() {
      const seqText = document.getElementById('historySeq').value.trim();
      if (seqText && !/^[0-9]+$/.test(seqText)) throw new Error('序号必须是非负整数');
      const seq = seqText ? Number(seqText) : null;
      if (seq !== null && !Number.isSafeInteger(seq)) throw new Error('序号超出浏览器安全整数范围');
      const receivedFrom = isoFromHistoryControl('historyReceivedFrom');
      const receivedTo = isoFromHistoryControl('historyReceivedTo');
      if (receivedFrom && receivedTo && Date.parse(receivedFrom) > Date.parse(receivedTo)) {
        throw new Error('开始时间不能晚于结束时间');
      }
      return {
        received_from: receivedFrom,
        received_to: receivedTo,
        seq,
        event_type: document.getElementById('historyEventType').value,
        trust: document.getElementById('historyTrust').value,
        page_size: Number(document.getElementById('historyPageSize').value),
      };
    }
    function locationHistoryRequestBody(filters, cursor) {
      const body = {
        page_size: filters.page_size,
        event_type: filters.event_type,
        trust: filters.trust,
      };
      if (filters.received_from) body.received_from = filters.received_from;
      if (filters.received_to) body.received_to = filters.received_to;
      if (filters.seq !== null) body.seq = filters.seq;
      if (cursor) body.cursor = cursor;
      return body;
    }
    function locationHistoryPoint(record) {
      if (!record || record.selectable !== true) return null;
      try {
        return {
          lat: finiteCoordinate(record.lat, -90, 90, 'latitude'),
          lon: finiteCoordinate(record.lon, -180, 180, 'longitude'),
          server_received_at: record.server_received_at || '',
          seq: record.seq,
          event_type: record.event_type || '',
          source: 'location_history',
          fix: true,
          fw_version: record.fw_version || 'unknown',
          coordinate_contract: 'wgs84',
          coordinate_trust: 'verified_parser_fw_allowlist',
          amap_eligible: true,
          history_record_id: record.record_id,
        };
      } catch (_error) {
        return null;
      }
    }
    function locationHistoryTrustLabel(record) {
      if (record && record.selectable === true) return '可信 WGS-84，可选择';
      const labels = {
        gnss_fix_not_true: 'GNSS 未定位，不可选择',
        not_gnss_location_report: '定位观测，无可信 WGS-84 坐标',
        firmware_parser_not_allowlisted: '固件坐标解析器未列入白名单',
        coordinate_fields_missing: '没有有效坐标',
        gnss_no_fix: 'GNSS 未定位',
        observation_without_position_fix: '定位观测没有精确坐标',
        stored_payload_invalid: '存储记录无法解析',
        stored_payload_too_large: '存储记录过大，仅显示安全元数据',
      };
      return labels[String(record && record.trust_reason || '')] || '坐标合同未验证，不可选择';
    }
    function locationHistoryEventLabel(eventType) {
      if (eventType === 'location_report') return 'GNSS 定位上报';
      if (eventType === 'location_observation') return '定位观测';
      return eventType || '未知';
    }
    function setLocationHistoryStatus(message, state = '') {
      const status = document.getElementById('locationHistoryStatus');
      status.textContent = message;
      status.className = `history-status ${state}`.trim();
    }
    function renderLocationHistory(selectedDevice) {
      const rowsElement = document.getElementById('locationHistoryRows');
      const previousButton = document.getElementById('previousLocationHistory');
      const nextButton = document.getElementById('nextLocationHistory');
      const pageLabel = document.getElementById('locationHistoryPageLabel');
      const selectionLabel = document.getElementById('historySelectionLabel');
      if (!selectedDevice) {
        locationHistoryActiveDeviceId = '';
        rowsElement.innerHTML = '<tr><td colspan="7" class="empty">请先选择设备</td></tr>';
        previousButton.disabled = true;
        nextButton.disabled = true;
        pageLabel.textContent = '第 1 页';
        selectionLabel.textContent = `地图已选 0 / 最多 ${TRAJECTORY_RENDER_POINT_LIMIT} 点`;
        setLocationHistoryStatus('选择设备后加载全部定位历史');
        return;
      }
      const state = locationHistoryStateForDevice(selectedDevice.device_id);
      if (locationHistoryActiveDeviceId !== selectedDevice.device_id) {
        locationHistoryActiveDeviceId = selectedDevice.device_id;
        syncLocationHistoryControls(state.filters);
      }
      const context = trajectorySelectionContext(selectedDevice);
      selectionLabel.textContent = `地图已选 ${context.selectedPoints.length} / 最多 ${TRAJECTORY_RENDER_POINT_LIMIT} 点 · 历史勾选 ${state.selectedRecords.size} 条`;
      const selectAll = document.getElementById('historySelectAll');
      const selectableRecords = state.records.filter(record => locationHistoryPoint(record));
      const selectedOnPage = selectableRecords.filter(record => state.selectedRecords.has(record.record_id)).length;
      selectAll.disabled = selectableRecords.length === 0;
      selectAll.checked = selectableRecords.length > 0 && selectedOnPage === selectableRecords.length;
      selectAll.indeterminate = selectedOnPage > 0 && selectedOnPage < selectableRecords.length;
      const rowHtml = state.records.map(record => {
        const point = locationHistoryPoint(record);
        const checked = state.selectedRecords.has(record.record_id) ? ' checked' : '';
        const disabled = point ? '' : ' disabled';
        const rowClass = point ? '' : ' class="history-record-unselectable"';
        const checkboxLabel = point
          ? `选择定位记录 ${record.record_id}，${formatDashboardDateTime(record.server_received_at)}`
          : `定位记录 ${record.record_id} 不满足可信坐标规则，不能选择`;
        const fixLabel = record.fix === true ? '已定位' : record.fix === false ? '未定位' : '未知';
        const trustLabel = locationHistoryTrustLabel(record);
        return `<tr${rowClass}>
          <td><input type="checkbox" data-history-record-id="${escapeHtml(record.record_id)}" aria-label="${escapeHtml(checkboxLabel)}"${checked}${disabled}></td>
          <td>${escapeHtml(formatDashboardDateTime(record.server_received_at))}</td>
          <td>${escapeHtml(locationHistoryEventLabel(record.event_type))}</td>
          <td>${escapeHtml(record.seq ?? '未知')}</td>
          <td>${escapeHtml(fixLabel)}</td>
          <td class="${point ? 'history-trust-ok' : 'history-trust-warn'}">${escapeHtml(trustLabel)}</td>
          <td>${escapeHtml(record.fw_version || 'unknown')}</td>
        </tr>`;
      }).join('');
      rowsElement.innerHTML = rowHtml || '<tr><td colspan="7" class="empty">本页没有匹配记录</td></tr>';
      previousButton.disabled = state.loading || state.cursorStack.length === 0;
      nextButton.disabled = state.loading || !state.nextCursor;
      pageLabel.textContent = `第 ${state.pageNumber} 页 · 本页 ${state.records.length} 条 · 已检查 ${state.inspectedCount} 条定位记录${state.exhausted ? ' · 已到末页' : ' · 快照继续可翻页'}`;
      if (state.loading) {
        setLocationHistoryStatus('正在读取数据库历史快照…');
      } else if (state.error) {
        const errorLabels = {
          unauthorized: '访问令牌无效，请重新保存连接',
          device_not_found: '所选设备不存在',
          invalid_location_history_cursor: '历史快照游标失效，请重新搜索',
          request_failed: '历史记录请求失败，请稍后重试',
        };
        setLocationHistoryStatus(errorLabels[state.error] || '历史查询条件无效，请检查后重试', 'bad');
      } else if (!state.loaded) {
        setLocationHistoryStatus('正在准备全部定位历史');
      } else if (!state.records.length && state.nextCursor) {
        setLocationHistoryStatus('本页没有匹配记录，但快照尚未结束，可继续下一页', 'warn');
      } else if (!state.records.length) {
        setLocationHistoryStatus('当前快照中没有匹配的定位记录', 'warn');
      } else {
        const selectableCount = state.records.filter(record => record.selectable === true).length;
        setLocationHistoryStatus(`本页 ${state.records.length} 条，其中 ${selectableCount} 条可信可选；新上传数据不会插入当前翻页快照。`);
      }
      rowsElement.querySelectorAll('[data-history-record-id]').forEach(input => {
        input.addEventListener('change', () => {
          const record = state.records.find(item => item.record_id === input.dataset.historyRecordId);
          const point = locationHistoryPoint(record);
          if (!record || !point) {
            input.checked = false;
            return;
          }
          if (input.checked) {
            const projectedHistory = new Map(state.selectedRecords);
            projectedHistory.set(record.record_id, point);
            if (projectedHistory.size > TRAJECTORY_RENDER_POINT_LIMIT) {
              input.checked = false;
              setLocationHistoryStatus(`最多选择 ${TRAJECTORY_RENDER_POINT_LIMIT} 条唯一历史记录，请先取消部分记录。`, 'warn');
              return;
            }
            state.selectedRecords.set(record.record_id, point);
          } else {
            state.selectedRecords.delete(record.record_id);
          }
          rerenderTrajectorySelection(selectedDevice);
          renderLocationHistory(selectedDevice);
        });
      });
    }
    async function loadLocationHistory(
      selectedDevice,
      {filters, cursor = null, cursorStack = [], pageNumber = 1} = {},
    ) {
      if (!selectedDevice) return;
      const state = locationHistoryStateForDevice(selectedDevice.device_id);
      const requestedFilters = filters || state.filters;
      const generation = ++state.requestGeneration;
      state.loading = true;
      state.error = '';
      renderLocationHistory(selectedDevice);
      try {
        const response = await fetch(
          `/api/v1/devices/${encodeURIComponent(selectedDevice.device_id)}/locations/search`,
          {
            method: 'POST',
            headers: {...authHeaders(), 'Content-Type': 'application/json'},
            body: JSON.stringify(locationHistoryRequestBody(requestedFilters, cursor)),
            cache: 'no-store',
          },
        );
        let data = {};
        try {
          data = await response.json();
        } catch (_error) {
          data = {};
        }
        if (!response.ok) {
          const requestError = new Error('history request failed');
          requestError.code = String(data.error || (response.status === 401 ? 'unauthorized' : 'request_failed'));
          throw requestError;
        }
        const activeDevice = selectedDashboardDevice();
        if (
          generation !== state.requestGeneration
          || !activeDevice
          || activeDevice.device_id !== selectedDevice.device_id
          || data.device_id !== selectedDevice.device_id
          || !Array.isArray(data.locations)
        ) return;
        const page = data.page && typeof data.page === 'object' ? data.page : {};
        state.filters = requestedFilters;
        state.cursor = typeof page.current_cursor === 'string' && page.current_cursor
          ? page.current_cursor
          : cursor;
        state.cursorStack = [...cursorStack];
        state.pageNumber = pageNumber;
        state.records = data.locations;
        state.nextCursor = typeof page.next_cursor === 'string' && page.next_cursor ? page.next_cursor : null;
        state.exhausted = page.exhausted === true;
        state.inspectedCount = Number(page.inspected_count) || 0;
        state.loaded = true;
        state.error = '';
      } catch (error) {
        if (generation === state.requestGeneration) {
          state.error = String(error && error.code || 'request_failed');
        }
      } finally {
        if (generation === state.requestGeneration) {
          state.loading = false;
          const activeDevice = selectedDashboardDevice();
          if (activeDevice && activeDevice.device_id === selectedDevice.device_id) {
            renderLocationHistory(selectedDevice);
          }
        }
      }
    }
    function renderSelectedDevicePanels() {
      if (!lastSuccessfulDashboardState) return;
      const devices = lastSuccessfulDashboardState.devices || [];
      const selectedDevice = selectDashboardDevice(
        devices,
        lastSuccessfulDashboardState.current_run || {},
      );
      updateD2ManifestStatus(selectedDevice ? selectedDevice.device_id : '');
      d1Link.innerHTML = d1LinkPanel(selectedDevice);
      renderLocationHistory(selectedDevice);
      fieldState.innerHTML = latestFieldState(
        selectedDevice,
        lastSuccessfulDashboardState.raw_frames || [],
      );
      renderAmapForSelectedDevice(selectedDevice);
      void loadPhotosForSelectedDevice();
      if (selectedDevice) {
        const historyState = locationHistoryStateForDevice(selectedDevice.device_id);
        if (!historyState.loaded && !historyState.loading) {
          void loadLocationHistory(selectedDevice, {filters: historyState.filters});
        }
      }
    }
    function renderD1LinkFromLatestState() {
      renderSelectedDevicePanels();
    }
    tokenInput.value = currentToken();
    photoGuardianTokenInput.value = photoGuardianToken();
    saveToken.addEventListener('click', () => {
      localStorage.setItem('egolinkHubToken', tokenInput.value.trim());
      refresh();
    });
    savePhotoGuardianToken.addEventListener('click', () => {
      const value = photoGuardianTokenInput.value.trim();
      if (value) sessionStorage.setItem('egolinkPhotoGuardianToken', value);
      else sessionStorage.removeItem('egolinkPhotoGuardianToken');
      setPhotoStatus(
        photoCommandStatus,
        value
          ? 'Guardian 照片授权已保存到当前浏览器会话；尚未发送设备命令。'
          : 'Guardian 照片授权已从当前浏览器会话清除。',
        value ? 'ok' : 'warn',
      );
      void loadPhotosForSelectedDevice();
    });
    refreshDashboard.addEventListener('click', refresh);
    refreshPhotos.addEventListener('click', () => void loadPhotosForSelectedDevice());
    capturePhotoOnce.addEventListener('click', () => void submitCapturePhotoOnce());
    applyPhotoTimer.addEventListener('click', () => void submitPhotoTimer());
    exportPhotos.addEventListener('click', () => void exportCurrentPhotos());
    photoTimerEnabled.addEventListener('change', () => {
      const enabled = photoTimerEnabled.value === 'enabled';
      photoTimerInterval.disabled = !enabled;
      photoTimerMaxPhotos.disabled = !enabled;
      setPhotoStatus(
        photoTimerStatus,
        enabled
          ? '页面拟提交开启配置；设备实际状态仍为未报告，需提交并等待 ACK。'
          : '页面拟提交停止配置；在设备 ACK applied 前不能声称已经停止。',
        'warn',
      );
    });
    photoSessionFilter.addEventListener('change', () => void loadPhotosForSelectedDevice());
    deviceSelector.addEventListener('change', () => {
      selectedDashboardDeviceId = deviceSelector.value;
      photoSessionFilter.value = '';
      currentPhotoSession = null;
      if (selectedDashboardDeviceId) {
        localStorage.setItem(DASHBOARD_DEVICE_KEY, selectedDashboardDeviceId);
      } else {
        localStorage.removeItem(DASHBOARD_DEVICE_KEY);
      }
      renderSelectedDevicePanels();
    });
    document.getElementById('locationHistoryForm').addEventListener('submit', event => {
      event.preventDefault();
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) {
        setLocationHistoryStatus('请先选择设备', 'warn');
        return;
      }
      try {
        const filters = locationHistoryFiltersFromControls();
        void loadLocationHistory(selectedDevice, {
          filters,
          cursor: null,
          cursorStack: [],
          pageNumber: 1,
        });
      } catch (error) {
        setLocationHistoryStatus(error instanceof Error ? error.message : '查询条件无效', 'bad');
      }
    });
    document.getElementById('historySelectAll').addEventListener('change', (event) => {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) return;
      const state = locationHistoryStateForDevice(selectedDevice.device_id);
      const checkboxes = document.querySelectorAll('#locationHistoryRows input[type="checkbox"][data-history-record-id]');
      checkboxes.forEach(cb => {
        if (!cb.disabled) {
          cb.checked = event.target.checked;
          const recordId = cb.dataset.historyRecordId;
          const record = state.records.find(r => r.record_id === recordId);
          if (record) {
            const point = locationHistoryPoint(record);
            if (event.target.checked && point) {
              if (state.selectedRecords.size < TRAJECTORY_RENDER_POINT_LIMIT) {
                state.selectedRecords.set(record.record_id, point);
              }
            } else {
              state.selectedRecords.delete(record.record_id);
            }
          }
        }
      });
      rerenderTrajectorySelection(selectedDevice);
      renderLocationHistory(selectedDevice);
    });
    document.getElementById('resetLocationHistory').addEventListener('click', () => {
      const selectedDevice = selectedDashboardDevice();
      const filters = defaultLocationHistoryFilters();
      syncLocationHistoryControls(filters);
      if (selectedDevice) {
        void loadLocationHistory(selectedDevice, {
          filters,
          cursor: null,
          cursorStack: [],
          pageNumber: 1,
        });
      }
    });
    document.getElementById('previousLocationHistory').addEventListener('click', () => {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) return;
      const state = locationHistoryStateForDevice(selectedDevice.device_id);
      if (state.loading || !state.cursorStack.length) return;
      const cursorStack = state.cursorStack.slice(0, -1);
      const cursor = state.cursorStack[state.cursorStack.length - 1] || null;
      void loadLocationHistory(selectedDevice, {
        filters: state.filters,
        cursor,
        cursorStack,
        pageNumber: Math.max(1, state.pageNumber - 1),
      });
    });
    document.getElementById('nextLocationHistory').addEventListener('click', () => {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) return;
      const state = locationHistoryStateForDevice(selectedDevice.device_id);
      if (state.loading || !state.nextCursor) return;
      void loadLocationHistory(selectedDevice, {
        filters: state.filters,
        cursor: state.nextCursor,
        cursorStack: [...state.cursorStack, state.cursor],
        pageNumber: state.pageNumber + 1,
      });
    });
    document.getElementById('clearHistorySelection').addEventListener('click', () => {
      const selectedDevice = selectedDashboardDevice();
      if (!selectedDevice) return;
      clearLocationHistorySelectionForDevice(selectedDevice.device_id);
      trajectorySelectionByDevice.set(
        selectedDevice.device_id,
        {mode: 'manual', selectedKeys: new Set()},
      );
      rerenderTrajectorySelection(selectedDevice);
      renderLocationHistory(selectedDevice);
    });
    localD2MapReview = loadLocalD2MapReview();
    updateD2ManifestStatus();
    loadD2Manifest.addEventListener('click', () => d2ManifestFile.click());
    d2ManifestFile.addEventListener('change', async () => {
      const file = d2ManifestFile.files && d2ManifestFile.files[0];
      if (!file) return;
      try {
        if (file.size > D2_MANIFEST_MAX_BYTES) throw new Error('manifest exceeds 256 KiB');
        const review = compactD2MapReview(JSON.parse(await file.text()));
        const activeDevice = lastSuccessfulDashboardState
          ? selectDashboardDevice(
              lastSuccessfulDashboardState.devices || [],
              lastSuccessfulDashboardState.current_run || {},
            )
          : null;
        if (review.device_id && activeDevice && review.device_id !== activeDevice.device_id) {
          throw new Error('manifest device does not match active device');
        }
        localStorage.setItem(D2_MAP_REVIEW_KEY, JSON.stringify(review));
        localStorage.removeItem(D2_MAP_REVIEW_DISABLED_KEY);
        localD2MapReview = review;
        updateD2ManifestStatus();
        renderD1LinkFromLatestState();
      } catch (error) {
        setD2ManifestStatus(error instanceof Error ? error.message : 'invalid manifest', 'bad');
      } finally {
        d2ManifestFile.value = '';
      }
    });
    clearD2References.addEventListener('click', () => {
      localStorage.removeItem(D2_MAP_REVIEW_KEY);
      localStorage.setItem(D2_MAP_REVIEW_DISABLED_KEY, '1');
      localD2MapReview = null;
      updateD2ManifestStatus();
      renderD1LinkFromLatestState();
    });
    function parseResult(rawFrame) {
      return rawFrame.parse_result || {};
    }
    function framing(rawFrame) {
      return rawFrame.framing || {};
    }
    function rawFrameStatus(rawFrame) {
      return parseResult(rawFrame).status || rawFrame.parse_status || 'unknown';
    }
    function rawFrameClass(rawFrame) {
      const status = rawFrameStatus(rawFrame);
      if (status === 'ok') return 'ok';
      if (status === 'partial' || status === 'not_attempted') return 'warn';
      return 'bad';
    }
    function rawFrameSummary(rawFrame) {
      const parsed = parseResult(rawFrame);
      const frame = framing(rawFrame);
      return `${rawFrame.direction || 'unknown'} ${frame.frame_type || rawFrame.frame_type || 'raw'} / ${rawFrameStatus(rawFrame)} / ${parsed.derived_message_type || 'unknown'}`;
    }
    function latestRawFrameForDevice(rawFrames, deviceId) {
      return (rawFrames || []).find(frame => frame.device_id === deviceId) || {};
    }
    function releaseLabel(release) {
      if (!release || !release.release_id) return 'unknown';
      const version = release.release_version ? ` / ${release.release_version}` : '';
      const match = release.match ? ` / ${release.match}` : '';
      return `${release.release_id}${version}${match}`;
    }
    function runContextPanel(run) {
      const release = run.key_release || {};
      const baseline = release.baseline || {};
      const command = run.command || {};
      const rawFrame = run.raw_frame || {};
      const location = run.location || {};
      const failure = run.failure || {};
      const reliability = run.reliability || {};
      const relNetwork = reliability.network || {};
      const relCache = reliability.cache || {};
      const eale = run.eale_p0 || {};
      const ealeBelief = eale.location_belief || {};
      const ealeDataset = eale.dataset_window || {};
      const counts = run.evidence_counts || {};
      return `
        <div class="metric"><span>测试批次</span><b>${escapeHtml(run.test_run_id || 'unknown')}</b></div>
        <div class="metric"><span>关键版本</span><span>${escapeHtml(releaseLabel(release))}</span></div>
        <div class="metric"><span>固件</span><span>${escapeHtml(run.fw_version || 'unknown')}</span></div>
        <div class="metric"><span>测试设备</span><span>${escapeHtml(run.device_id || 'unknown')}</span></div>
        <div class="metric"><span>指令链路</span><span>${escapeHtml(command.cmd_id || 'none')} / ${escapeHtml(command.cmd || 'none')} / ${escapeHtml(command.status || 'unknown')} / ACK ${escapeHtml(command.ack_status || 'none')}</span></div>
        <div class="metric"><span>异常状态</span><span class="${failure.state === 'ok' ? 'ok' : failure.state === 'pending' || failure.state === 'warning' ? 'warn' : 'bad'}">${escapeHtml(displayState(failure.state || 'unknown'))}</span></div>
        <div class="metric"><span>异常原因</span><span>${escapeHtml(failure.reason || 'unknown')}</span></div>
        <details>
          <summary>展开测试诊断</summary>
          <div class="metric"><span>Baseline</span><span>${escapeHtml(baseline.release_id || 'none')} ${escapeHtml(baseline.release_version || '')}</span></div>
          <div class="metric"><span>Raw Evidence</span><span>${escapeHtml(rawFrame.frame_id || 'none')} / ${escapeHtml(rawFrame.frame_type || 'unknown')} / ${escapeHtml(rawFrame.parse_status || 'unknown')} / ${escapeHtml(rawFrame.derived_message_type || 'unknown')}</span></div>
          <div class="metric"><span>Derived Location</span><span>${escapeHtml(location.event_type || 'none')} seq ${escapeHtml(location.seq ?? 'unknown')} / fix ${escapeHtml(location.fix ?? 'unknown')} / ${escapeHtml(location.gnss_state || 'unknown')}</span></div>
          <div class="metric"><span>Network Reconnect</span><span>${escapeHtml(relNetwork.reconnect_count ?? 'unknown')} / ${escapeHtml(relNetwork.last_reconnect_reason || relNetwork.state || 'unknown')}</span></div>
          <div class="metric"><span>Network Error</span><span>${escapeHtml(relNetwork.last_error || 'none')}</span></div>
          <div class="metric"><span>Raw POST</span><span>${escapeHtml(relNetwork.raw_post_success_count ?? 'unknown')} ok / ${escapeHtml(relNetwork.raw_post_failure_count ?? 'unknown')} fail / ${escapeHtml(relNetwork.raw_post_attempt_count ?? 'unknown')} attempts</span></div>
          <div class="metric"><span>Cache Queue</span><span>${escapeHtml(relCache.queued_message_count ?? 'unknown')} queued / ${escapeHtml(relCache.oldest_message_age_ms ?? 'unknown')} ms oldest</span></div>
          <div class="metric"><span>Cache Retry</span><span>${escapeHtml(relCache.retry_success_count ?? 'unknown')} ok / ${escapeHtml(relCache.retry_failure_count ?? 'unknown')} fail / ${escapeHtml(relCache.retry_attempt_count ?? 'unknown')} attempts / ${escapeHtml(relCache.retry_policy || 'none')}</span></div>
          <div class="metric"><span>Cache Flush</span><span>${escapeHtml(relCache.flush_success_count ?? 'unknown')} ok / ${escapeHtml(relCache.flush_failure_count ?? 'unknown')} fail / ${escapeHtml(relCache.flush_attempt_count ?? 'unknown')} attempts</span></div>
          <div class="metric"><span>Cache Drops</span><span>${escapeHtml(relCache.dropped_message_count ?? 'unknown')} / ${escapeHtml(relCache.last_drop_reason || 'none')}</span></div>
          <div class="metric"><span>EALE-P0</span><span>${escapeHtml(ealeBelief.state || 'unknown')} / ${escapeHtml(ealeBelief.substate || 'unknown')} / ${escapeHtml(ealeBelief.confidence_bucket || 'unknown')}</span></div>
          <div class="metric"><span>EALE Reason</span><span>${escapeHtml(ealeBelief.reason || 'unknown')}</span></div>
          <div class="metric"><span>EALE Failure</span><span>${escapeHtml(ealeBelief.failure_reason || 'none')}</span></div>
          <div class="metric"><span>Dataset Window</span><span>${escapeHtml(ealeDataset.sample_type || 'unknown')} / ${escapeHtml(ealeDataset.status || 'unknown')}</span></div>
          <div class="metric"><span>Dataset Training</span><span>${escapeHtml(ealeDataset.training_allowed ?? false)} / ${escapeHtml(ealeDataset.training_reason || 'unknown')}</span></div>
          <div class="metric"><span>Quality Flags</span><span>${escapeHtml((ealeBelief.quality_flags || []).join(', ') || 'none')}</span></div>
          <div class="metric"><span>Evidence Counts</span><span>${escapeHtml(counts.messages ?? 0)} messages / ${escapeHtml(counts.commands ?? 0)} commands / ${escapeHtml(counts.raw_frames ?? 0)} raw_frames</span></div>
        </details>
      `;
    }
    function statusClass(status) {
      if (status === 'pass' || status === 'released' || status === 'ready_for_training_handoff' || status === 'ready_for_runner' || status === 'ready_for_training_runner' || status === 'ready_for_training_server_handoff' || status === 'ready_for_runner_queue' || status === 'synthetic_baseline_eval_complete' || status === 'baseline_eval_complete' || status === 'ready_for_synthetic_feature_dry_run' || status === 'synthetic_runner_dry_run_complete') return 'ok';
      if (status === 'ready_for_labeling_review') return 'warn';
      if (status === 'warn' || status === 'not_run' || status === 'release_candidate' || status === 'needs_review' || status === 'needs_labels' || status === 'needs_capture' || status === 'needs_human_review' || status === 'ready_for_human_input' || status === 'pending_human_review' || status === 'pending_label_privacy_split' || status === 'pending_labeling_queue_review' || status === 'synthetic_ready_for_runner' || status === 'synthetic_training_chain_complete' || status === 'synthetic_handoff_dry_run_only' || status === 'synthetic_runner_queue_dry_run_only' || status === 'blocked_dataset_not_ready' || status === 'blocked_no_eligible_records' || status === 'blocked_synthetic_without_ack' || status === 'blocked_experiment_not_ready' || status === 'blocked_incomplete_dataset_records' || status === 'blocked_runner_dry_run_not_ready' || status === 'blocked_feature_rows_mismatch' || status === 'blocked_source_mismatch' || status === 'blocked_handoff_not_ready') return 'warn';
      return status === 'not_available' || status === 'no_review_items' || status === 'no_labeling_queue' || status === 'no_decision_items' || status === 'no_labeling_review_packet' ? 'empty' : 'bad';
    }
    function productDemoPanel(demo) {
      if (!demo || !demo.available) {
        return `
          <div class="metric"><span>候选版本</span><b>KR-008 / DEMO-008</b></div>
          <div class="metric"><span>结果</span><span class="empty">${escapeHtml(demo && demo.status || 'not_available')}</span></div>
          <div class="metric"><span>下一步</span><span>${escapeHtml(demo && demo.next_step || '生成产品演示报告')}</span></div>
        `;
      }
      const location = demo.location || {};
      const training = demo.training_readiness || {};
      const webGate = (demo.flow || {}).web_console_replay_review || {};
      const counts = demo.flow_status_counts || {};
      const warnings = demo.warnings || [];
      return `
        <div class="metric"><span>候选版本</span><b>${escapeHtml(demo.candidate || 'KR-008 / DEMO-008')}</b></div>
        <div class="metric"><span>结果</span><span class="${statusClass(demo.status)}">${escapeHtml(displayState(demo.status || 'unknown'))}</span></div>
        <div class="metric"><span>发布就绪</span><span>${escapeHtml(demo.ready_for_kr008_release ?? false)}</span></div>
        <div class="metric"><span>证据模式</span><span>${escapeHtml(demo.evidence_mode || 'unknown')}</span></div>
        <div class="metric"><span>测试批次</span><span>${escapeHtml(demo.test_run_id || 'unknown')}</span></div>
        <div class="metric"><span>安全会话</span><span>${escapeHtml(demo.safety_session_id || 'none')}</span></div>
        <div class="metric"><span>位置判断</span><span>${escapeHtml(displayState(location.state || 'Unknown'))} / ${escapeHtml(location.belief_reason || (location.failure_modes || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>GNSS</span><span>fix ${escapeHtml(location.gnss_fix ?? 'unknown')} / ${escapeHtml(location.gnss_state || 'unknown')}</span></div>
        <div class="metric"><span>流程门禁</span><span>${escapeHtml(counts.pass ?? 0)} 通过 / ${escapeHtml(counts.warn ?? 0)} 警告 / ${escapeHtml(counts.not_run ?? 0)} 未运行 / ${escapeHtml(counts.fail ?? 0)} 失败</span></div>
        <div class="metric"><span>Web 复核</span><span class="${statusClass(webGate.status)}">${escapeHtml(webGate.status || 'unknown')} / ${escapeHtml(webGate.summary || 'unknown')}</span></div>
        <div class="metric"><span>原始证据</span><span>${escapeHtml(demo.raw_frame_refs ?? 0)} 个原始引用 / ${escapeHtml(demo.derived_event_refs ?? 0)} 个派生引用</span></div>
        <div class="metric"><span>训练就绪</span><span>${escapeHtml(training.model_training_ready ?? false)} / ${escapeHtml(training.reason || 'unknown')}</span></div>
        <div class="metric"><span>报告</span><span>${escapeHtml(demo.markdown_path || demo.report_path || 'unknown')}</span></div>
        <div class="metric"><span>警告</span><span>${escapeHtml(warnings.join(', ') || 'none')}</span></div>
      `;
    }
    function metricRows(metrics) {
      return Object.entries(metrics || {})
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([key, value]) => `<div><span>${escapeHtml(key)}</span>: <b>${escapeHtml(value)}</b></div>`)
        .join('') || '<div class="empty">No compact metrics</div>';
    }
    function reportWarnings(report) {
      const warnings = report.warnings || [];
      const errors = report.errors || [];
      const parts = [];
      if (warnings.length) parts.push(`warn ${warnings.join(', ')}`);
      if (errors.length) parts.push(`errors ${errors.join(', ')}`);
      return parts.join(' / ') || 'none';
    }
    function dataFlywheelPanel(flywheel) {
      if (!flywheel || !flywheel.available) {
        return `
          <div class="metric"><span>状态</span><span class="empty">${escapeHtml(flywheel && flywheel.status || 'not_available')}</span></div>
          <div class="metric"><span>原因</span><span>${escapeHtml(flywheel && flywheel.reason || 'no_data_flywheel_status_report')}</span></div>
          <div class="metric"><span>下一步</span><span>${escapeHtml(flywheel && flywheel.next_step || '生成数据闭环状态报告')}</span></div>
        `;
      }
      const counts = flywheel.counts || {};
      const review = flywheel.review || {};
      const reviewQueue = flywheel.review_queue || {};
      const readiness = flywheel.readiness || {};
      const store = flywheel.candidate_store || {};
      const blockers = flywheel.blockers || [];
      const warnings = flywheel.warnings || [];
      const locationMetrics = (counts.location_baseline_reports || counts.reference_points || counts.location_attempts) ? `
        <div class="metric"><span>D2 Baselines</span><span>${escapeHtml(counts.location_baseline_reports ?? 0)} reports / ${escapeHtml(counts.reference_points ?? 0)} refs</span></div>
        <div class="metric"><span>D2 Attempts</span><span>${escapeHtml(counts.location_attempts ?? 0)} total / ${escapeHtml(counts.fixed_attempts ?? 0)} fixed / ${escapeHtml(counts.no_fix_attempts ?? 0)} no-fix</span></div>
      ` : '';
      const fieldEvidenceMetrics = (counts.location_field_evidence_reports || counts.field_samples) ? `
        <div class="metric"><span>Field Evidence</span><span>${escapeHtml(counts.location_field_evidence_reports ?? 0)} reports / ${escapeHtml(counts.field_samples ?? 0)} samples / ${escapeHtml(counts.field_successful_samples ?? 0)} ok</span></div>
        <div class="metric"><span>Field GNSS</span><span>${escapeHtml(counts.field_gnss_fix_samples ?? 0)} fix / ${escapeHtml(counts.field_gnss_no_fix_samples ?? 0)} no-fix / ${escapeHtml(counts.field_gnss_unknown_samples ?? 0)} unknown</span></div>
        <div class="metric"><span>Field LTE/Power</span><span>${escapeHtml(counts.field_unique_cell_count ?? 0)} cells / raw ${escapeHtml(counts.field_raw_post_success_delta ?? 0)} ok ${escapeHtml(counts.field_raw_post_failure_delta ?? 0)} fail / power ${escapeHtml(counts.field_power_sample_count_delta ?? 0)}</span></div>
      ` : '';
      const sourceReports = (flywheel.source_reports || []).slice(0, 3).map(report => `
        <div class="metric"><span>${escapeHtml(report.type || 'source')}</span><span>${escapeHtml(report.run_id || 'unknown')} / ${escapeHtml(report.result_status || report.reason || 'unknown')}</span></div>
      `).join('');
      const locationArtifacts = [
        flywheel.review_packet_path ? `review ${flywheel.review_packet_path}` : '',
        flywheel.dataset_manifest_path ? `manifest ${flywheel.dataset_manifest_path}` : '',
      ].filter(Boolean).join(' / ');
      const reviewSamples = (reviewQueue.sample_records || []).slice(0, 5).map(record => `
        <div class="metric"><span>${escapeHtml(record.record_id || 'candidate')}</span><span>${escapeHtml(record.state || 'unknown')} / ${escapeHtml(record.label || 'unknown')} / split ${escapeHtml(record.split_name || 'unknown')} / ${escapeHtml(record.label_review_state || 'unknown')}</span></div>
      `).join('') || '<div class="metric"><span>Review Samples</span><span class="empty">none</span></div>';
      return `
        <div class="metric"><span>状态</span><span class="${statusClass(flywheel.status)}">${escapeHtml(flywheel.status || 'unknown')}</span></div>
        <div class="metric"><span>阶段</span><span>${escapeHtml(flywheel.pipeline_stage || 'unknown')}</span></div>
        <div class="metric"><span>候选数据存储</span><span>${escapeHtml(store.available ?? false)} / ${escapeHtml(store.schema_version || store.reason || 'unknown')}</span></div>
        <div class="metric"><span>会话</span><span>${escapeHtml(counts.sessions_total ?? 0)}</span></div>
        <div class="metric"><span>候选记录</span><span>${escapeHtml(counts.records_total ?? 0)} 条 / ${escapeHtml(counts.needs_review_records ?? 0)} 条待复核</span></div>
        ${locationMetrics}
        ${fieldEvidenceMetrics}
        <div class="metric"><span>训练门禁</span><span>${escapeHtml(readiness.model_training_ready ?? false)} / ${escapeHtml(readiness.reason || 'unknown')}</span></div>
        <div class="metric"><span>已复核候选</span><span>${escapeHtml(counts.reviewed_training_candidate_records ?? 0)} 条 / 允许训练 ${escapeHtml(counts.training_allowed_records ?? 0)} 条</span></div>
        <div class="metric"><span>复核队列</span><span>标注 ${escapeHtml(review.label_review_pending_records ?? 0)} / 切分 ${escapeHtml(review.split_leakage_unchecked_records ?? 0)} / 隐私 ${escapeHtml(review.privacy_or_consent_blocked_records ?? 0)} / 质量 ${escapeHtml(review.quality_blocked_records ?? 0)}</span></div>
        <div class="metric"><span>待处理</span><span>${escapeHtml(reviewQueue.pending_records ?? 0)} 条 / 操作 ${escapeHtml((reviewQueue.available_actions || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>训练服务</span><span>${escapeHtml(readiness.training_server_ready ?? false)} / 端侧 ${escapeHtml(readiness.on_device_deployment_ready ?? false)}</span></div>
        <div class="metric"><span>阻塞项</span><span>${escapeHtml(blockers.join(', ') || 'none')}</span></div>
        <div class="metric"><span>警告</span><span>${escapeHtml(warnings.join(', ') || 'none')}</span></div>
        <div class="metric"><span>下一步</span><span>${escapeHtml(flywheel.next_step || '创建下一项数据任务')}</span></div>
        <div class="metric"><span>报告</span><span>${escapeHtml(flywheel.markdown_path || flywheel.report_path || 'unknown')}</span></div>
        ${locationArtifacts ? `<div class="metric"><span>D5 Artifacts</span><span>${escapeHtml(locationArtifacts)}</span></div>` : ''}
        ${sourceReports}
        ${reviewSamples}
      `;
    }
    function trainingExperimentPanel(experiment) {
      if (!experiment || !experiment.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(experiment && experiment.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(experiment && experiment.reason || 'no_training_experiment_plan')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(experiment && experiment.next_step || 'Register a training experiment plan')}</span></div>
        `;
      }
      const dataset = experiment.dataset || {};
      const model = experiment.model_track || {};
      const runner = experiment.runner || {};
      const metrics = experiment.metrics_plan || {};
      const classification = metrics.classification || {};
      const operations = metrics.operations || {};
      const gates = experiment.gates || {};
      const samples = (dataset.record_sample || []).slice(0, 5).map(record => `
        <div class="metric"><span>${escapeHtml(record.record_id || 'record')}</span><span>${escapeHtml(record.label || 'unknown')} / split ${escapeHtml(record.split_name || 'unknown')} / ${escapeHtml(record.candidate_type || 'unknown')}</span></div>
      `).join('') || '<div class="metric"><span>Record Sample</span><span class="empty">none</span></div>';
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(experiment.status)}">${escapeHtml(experiment.status || 'unknown')}</span></div>
        <div class="metric"><span>Experiment</span><b>${escapeHtml(experiment.experiment_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(experiment.reason || 'unknown')}</span></div>
        <div class="metric"><span>Dataset</span><span>${escapeHtml(dataset.dataset_id || 'unknown')} / ${escapeHtml(dataset.manifest_status || 'unknown')}</span></div>
        <div class="metric"><span>Eligible Records</span><span>${escapeHtml(dataset.eligible_records ?? 0)} eligible / ${escapeHtml(dataset.records_total ?? 0)} total</span></div>
        <div class="metric"><span>Model Track</span><span>${escapeHtml(model.track || 'unknown')} / ${escapeHtml(model.candidate_model || 'unknown')}</span></div>
        <div class="metric"><span>Baseline</span><span>${escapeHtml(model.baseline_model || 'unknown')}</span></div>
        <div class="metric"><span>Runner Handoff</span><span>${escapeHtml(runner.ready_for_handoff ?? false)} / ${escapeHtml(runner.integration || 'unknown')}</span></div>
        <div class="metric"><span>Classification Metrics</span><span>accuracy ${escapeHtml(classification.accuracy || 'planned_not_measured')} / FPR ${escapeHtml(classification.false_positive_rate || 'planned_not_measured')}</span></div>
        <div class="metric"><span>Footprint Metrics</span><span>latency ${escapeHtml(operations.latency_ms || 'planned_not_measured')} / RAM ${escapeHtml(operations.ram_bytes || 'planned_not_measured')} / power ${escapeHtml(operations.energy_per_inference || 'planned_not_measured')}</span></div>
        <div class="metric"><span>Gates</span><span>dataset ${escapeHtml(gates.dataset_ready ?? false)} / baseline ${escapeHtml(gates.baseline_comparison || 'unknown')} / footprint ${escapeHtml(gates.footprint || 'unknown')} / power ${escapeHtml(gates.power || 'unknown')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(experiment.next_step || runner.next_command || 'Integrate a runner task')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(experiment.markdown_path || experiment.report_path || 'unknown')}</span></div>
        ${samples}
      `;
    }
    function trainingRunPreflightPanel(preflight) {
      if (!preflight || !preflight.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(preflight && preflight.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(preflight && preflight.reason || 'no_training_run_preflight')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(preflight && preflight.next_step || 'Run the training-run preflight')}</span></div>
        `;
      }
      const dataset = preflight.dataset || {};
      const experiment = preflight.experiment || {};
      const model = experiment.model_track || {};
      const runner = preflight.runner || {};
      const checks = preflight.checks || {};
      const measured = (preflight.metrics_plan || {}).measured || {};
      const gates = preflight.gates || {};
      const samples = (dataset.record_sample || []).slice(0, 5).map(record => `
        <div class="metric"><span>${escapeHtml(record.record_id || 'record')}</span><span>${escapeHtml(record.label || 'unknown')} / split ${escapeHtml(record.split_name || 'unknown')} / ${escapeHtml(record.source_status || 'unknown')}</span></div>
      `).join('') || '<div class="metric"><span>Record Sample</span><span class="empty">none</span></div>';
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(preflight.status)}">${escapeHtml(preflight.status || 'unknown')}</span></div>
        <div class="metric"><span>Preflight</span><b>${escapeHtml(preflight.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(preflight.reason || 'unknown')}</span></div>
        <div class="metric"><span>Experiment</span><span>${escapeHtml(experiment.experiment_id || 'unknown')} / ${escapeHtml(experiment.status || 'unknown')}</span></div>
        <div class="metric"><span>Dataset</span><span>${escapeHtml(dataset.dataset_id || 'unknown')} / ${escapeHtml(dataset.status || 'unknown')}</span></div>
        <div class="metric"><span>Eligible Records</span><span>${escapeHtml(dataset.eligible_records ?? 0)} eligible / ${escapeHtml(dataset.records_total ?? 0)} total / experiment ${escapeHtml(dataset.experiment_records_total ?? 0)}</span></div>
        <div class="metric"><span>Model Track</span><span>${escapeHtml(model.track || 'unknown')} / ${escapeHtml(model.candidate_model || 'unknown')}</span></div>
        <div class="metric"><span>Synthetic Gate</span><span>${escapeHtml(gates.synthetic_gate || checks.synthetic_record_policy || 'unknown')} / records ${escapeHtml(dataset.synthetic_records ?? 0)} / allowed ${escapeHtml(dataset.synthetic_allowed_for_dry_run ?? false)}</span></div>
        <div class="metric"><span>Required Fields</span><span>${escapeHtml(checks.required_record_fields || 'unknown')} / missing ${escapeHtml(JSON.stringify(checks.missing_record_fields || {}))}</span></div>
        <div class="metric"><span>Runner Ready</span><span>${escapeHtml(runner.ready_for_training_runner ?? false)} / ${escapeHtml(runner.integration || 'unknown')}</span></div>
        <div class="metric"><span>Measured Metrics</span><span>classification ${escapeHtml(measured.classification || 'not_run')} / operations ${escapeHtml(measured.operations || 'not_run')} / power ${escapeHtml(measured.power || 'not_run')}</span></div>
        <div class="metric"><span>Gates</span><span>preflight ${escapeHtml(gates.preflight_ready ?? false)} / training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / server ${escapeHtml(gates.training_server || 'not_integrated')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(preflight.next_step || runner.next_step || 'Connect a runner task')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(preflight.markdown_path || preflight.report_path || 'unknown')}</span></div>
        ${samples}
      `;
    }
    function trainingFeatureManifestPanel(manifest) {
      if (!manifest || !manifest.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(manifest && manifest.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(manifest && manifest.reason || 'no_training_feature_manifest')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(manifest && manifest.next_step || 'Export the training feature manifest')}</span></div>
        `;
      }
      const dataset = manifest.dataset || {};
      const preflight = manifest.preflight || {};
      const rows = manifest.feature_rows || {};
      const checks = manifest.checks || {};
      const gates = manifest.gates || {};
      const measured = preflight.metrics_measured || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(manifest.status)}">${escapeHtml(manifest.status || 'unknown')}</span></div>
        <div class="metric"><span>Feature Set</span><b>${escapeHtml(manifest.feature_set_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(manifest.reason || 'unknown')}</span></div>
        <div class="metric"><span>Dataset</span><span>${escapeHtml(dataset.dataset_id || 'unknown')} / ${escapeHtml(dataset.status || 'unknown')}</span></div>
        <div class="metric"><span>Preflight</span><span>${escapeHtml(preflight.run_id || 'unknown')} / runner ${escapeHtml(preflight.runner_ready ?? false)}</span></div>
        <div class="metric"><span>Feature Rows</span><span>${escapeHtml(rows.row_count ?? 0)} rows / ${escapeHtml(rows.feature_scope || 'unknown')} / ${escapeHtml((rows.feature_groups || []).join(', ') || 'no groups')}</span></div>
        <div class="metric"><span>Target Boundary</span><span>${escapeHtml(rows.target_separated_from_features ?? false)} / ${escapeHtml(checks.label_leakage_guard || 'unknown')}</span></div>
        <div class="metric"><span>Synthetic Gate</span><span>${escapeHtml(checks.synthetic_record_policy || 'unknown')} / records ${escapeHtml(dataset.synthetic_records ?? 0)} / allowed ${escapeHtml(dataset.synthetic_allowed_for_dry_run ?? false)}</span></div>
        <div class="metric"><span>Source Match</span><span>${escapeHtml(checks.source_match ?? false)} / dataset ${escapeHtml(checks.dataset_ready ?? false)} / preflight ${escapeHtml(checks.preflight_ready ?? false)}</span></div>
        <div class="metric"><span>Required Fields</span><span>${escapeHtml(checks.required_record_fields || 'unknown')} / missing ${escapeHtml(JSON.stringify(checks.missing_record_fields || {}))}</span></div>
        <div class="metric"><span>Measured Metrics</span><span>classification ${escapeHtml(measured.classification || 'not_run')} / operations ${escapeHtml(measured.operations || 'not_run')} / power ${escapeHtml(measured.power || 'not_run')}</span></div>
        <div class="metric"><span>Gates</span><span>feature ${escapeHtml(gates.feature_export || 'unknown')} / training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / server ${escapeHtml(gates.training_server || 'not_integrated')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(manifest.next_step || 'Connect a runner task')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(manifest.markdown_path || manifest.report_path || 'unknown')}</span></div>
      `;
    }
    function trainingRunnerDryRunPanel(dryRun) {
      if (!dryRun || !dryRun.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(dryRun && dryRun.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(dryRun && dryRun.reason || 'no_training_runner_dry_run')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(dryRun && dryRun.next_step || 'Run the training runner dry-run')}</span></div>
        `;
      }
      const manifest = dryRun.feature_manifest || {};
      const rows = dryRun.feature_rows || {};
      const checks = dryRun.checks || {};
      const runner = dryRun.runner || {};
      const gates = dryRun.gates || {};
      const measured = (dryRun.metrics_plan || {}).measured || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(dryRun.status)}">${escapeHtml(dryRun.status || 'unknown')}</span></div>
        <div class="metric"><span>Dry-Run</span><b>${escapeHtml(dryRun.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(dryRun.reason || 'unknown')}</span></div>
        <div class="metric"><span>Feature Set</span><span>${escapeHtml(manifest.feature_set_id || 'unknown')} / ${escapeHtml(manifest.status || 'unknown')}</span></div>
        <div class="metric"><span>Rows</span><span>${escapeHtml(rows.actual_row_count ?? 0)} actual / ${escapeHtml(rows.expected_row_count ?? 0)} expected / match ${escapeHtml(rows.row_count_matches ?? false)}</span></div>
        <div class="metric"><span>Splits</span><span>${escapeHtml(JSON.stringify(rows.split_counts || {}))}</span></div>
        <div class="metric"><span>Labels</span><span>${escapeHtml(JSON.stringify(rows.label_counts || {}))}</span></div>
        <div class="metric"><span>Synthetic Policy</span><span>${escapeHtml(checks.synthetic_row_policy || 'unknown')} / rows ${escapeHtml(rows.synthetic_rows ?? 0)} / allowed ${escapeHtml(rows.synthetic_allowed_for_dry_run ?? false)}</span></div>
        <div class="metric"><span>Target Guard</span><span>${escapeHtml(checks.target_leakage_guard || 'unknown')} / violations ${escapeHtml(JSON.stringify(checks.target_leakage_violations || {}))}</span></div>
        <div class="metric"><span>Required Rows</span><span>${escapeHtml(checks.required_row_fields || 'unknown')} / missing ${escapeHtml(JSON.stringify(checks.missing_row_fields || {}))}</span></div>
        <div class="metric"><span>Runner Input</span><span>${escapeHtml(gates.runner_input || 'unknown')} / dry-run ${escapeHtml(runner.dry_run_only ?? false)} / real ${escapeHtml(runner.ready_for_real_runner ?? false)}</span></div>
        <div class="metric"><span>Measured Metrics</span><span>classification ${escapeHtml(measured.classification || 'not_run')} / operations ${escapeHtml(measured.operations || 'not_run')} / power ${escapeHtml(measured.power || 'not_run')}</span></div>
        <div class="metric"><span>Gates</span><span>training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / server ${escapeHtml(gates.training_server || 'not_integrated')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(dryRun.next_step || runner.next_step || 'Connect a real runner')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(dryRun.markdown_path || dryRun.report_path || 'unknown')}</span></div>
      `;
    }
    function trainingBaselineEvalPanel(evalReport) {
      if (!evalReport || !evalReport.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(evalReport && evalReport.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(evalReport && evalReport.reason || 'no_training_baseline_eval')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(evalReport && evalReport.next_step || 'Run the training baseline eval')}</span></div>
        `;
      }
      const manifest = evalReport.feature_manifest || {};
      const runner = evalReport.runner_dry_run || {};
      const rows = evalReport.feature_rows || {};
      const checks = evalReport.checks || {};
      const metrics = evalReport.metrics || {};
      const classification = metrics.classification || {};
      const gates = evalReport.gates || {};
      const baselines = (classification.baselines || []).map(baseline => {
        const overall = baseline.overall || {};
        return `${baseline.name || 'baseline'} ${overall.correct ?? 0}/${overall.total ?? 0} acc ${overall.accuracy ?? 'unknown'}`;
      }).join(' / ') || 'none';
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(evalReport.status)}">${escapeHtml(evalReport.status || 'unknown')}</span></div>
        <div class="metric"><span>Eval</span><b>${escapeHtml(evalReport.eval_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(evalReport.reason || 'unknown')}</span></div>
        <div class="metric"><span>Feature Set</span><span>${escapeHtml(manifest.feature_set_id || 'unknown')} / ${escapeHtml(manifest.status || 'unknown')}</span></div>
        <div class="metric"><span>Runner Dry-Run</span><span>${escapeHtml(runner.run_id || 'unknown')} / ${escapeHtml(runner.status || 'unknown')} / input ${escapeHtml(runner.runner_input_gate || 'unknown')}</span></div>
        <div class="metric"><span>Rows</span><span>${escapeHtml(rows.actual_row_count ?? 0)} actual / ${escapeHtml(rows.expected_row_count ?? 0)} expected / match ${escapeHtml(rows.row_count_matches ?? false)}</span></div>
        <div class="metric"><span>Splits</span><span>${escapeHtml(JSON.stringify(rows.split_counts || {}))}</span></div>
        <div class="metric"><span>Labels</span><span>${escapeHtml(JSON.stringify(rows.label_counts || {}))}</span></div>
        <div class="metric"><span>Risk Types</span><span>${escapeHtml(JSON.stringify(rows.risk_type_counts || {}))}</span></div>
        <div class="metric"><span>Candidates</span><span>${escapeHtml(JSON.stringify(rows.candidate_type_counts || {}))}</span></div>
        <div class="metric"><span>Synthetic Policy</span><span>${escapeHtml(checks.synthetic_row_policy || 'unknown')} / rows ${escapeHtml(rows.synthetic_rows ?? 0)} / allowed ${escapeHtml(rows.synthetic_allowed_for_eval ?? false)}</span></div>
        <div class="metric"><span>Metric Scope</span><span>${escapeHtml(metrics.scope || 'unknown')} / measured ${escapeHtml(metrics.measured_from_rows ?? false)}</span></div>
        <div class="metric"><span>Baselines</span><span>${escapeHtml(baselines)}</span></div>
        <div class="metric"><span>Target Guard</span><span>${escapeHtml(checks.target_leakage_guard || 'unknown')} / violations ${escapeHtml(JSON.stringify(checks.target_leakage_violations || {}))}</span></div>
        <div class="metric"><span>Performance Claim</span><span>${escapeHtml(classification.product_performance_claim ?? false)} / release ${escapeHtml(classification.release_metric ?? false)}</span></div>
        <div class="metric"><span>Gates</span><span>eval ${escapeHtml(gates.baseline_evaluation || 'unknown')} / training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / claim ${escapeHtml(gates.release_claim || 'not_allowed')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(evalReport.next_step || 'Repeat with reviewed real rows')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(evalReport.markdown_path || evalReport.report_path || 'unknown')}</span></div>
      `;
    }
    function trainingHandoffBundlePanel(bundle) {
      if (!bundle || !bundle.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(bundle && bundle.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(bundle && bundle.reason || 'no_training_handoff_bundle')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(bundle && bundle.next_step || 'Build the training handoff bundle')}</span></div>
        `;
      }
      const dataset = bundle.dataset || {};
      const preflight = bundle.training_run_preflight || {};
      const manifest = bundle.feature_manifest || {};
      const rows = bundle.feature_rows || {};
      const runner = bundle.runner_dry_run || {};
      const baseline = bundle.baseline_eval || {};
      const checks = bundle.checks || {};
      const server = bundle.training_server || {};
      const gates = bundle.gates || {};
      const sourceRefs = bundle.source_refs || {};
      const sourceText = Object.entries(sourceRefs).map(([name, ref]) => {
        return `${name}: ${ref && ref.sha256 ? String(ref.sha256).slice(0, 10) : 'nohash'}`;
      }).join(' / ') || 'none';
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(bundle.status)}">${escapeHtml(bundle.status || 'unknown')}</span></div>
        <div class="metric"><span>Handoff</span><b>${escapeHtml(bundle.handoff_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(bundle.reason || 'unknown')}</span></div>
        <div class="metric"><span>Dataset</span><span>${escapeHtml(dataset.dataset_id || 'unknown')} / ${escapeHtml(dataset.status || 'unknown')} / ${escapeHtml(dataset.eligible_records ?? 0)} eligible</span></div>
        <div class="metric"><span>Preflight</span><span>${escapeHtml(preflight.run_id || 'unknown')} / ${escapeHtml(preflight.status || 'unknown')} / runner ${escapeHtml(preflight.runner_ready ?? false)}</span></div>
        <div class="metric"><span>Feature Set</span><span>${escapeHtml(manifest.feature_set_id || 'unknown')} / ${escapeHtml(manifest.status || 'unknown')} / ${escapeHtml(manifest.feature_scope || 'unknown')}</span></div>
        <div class="metric"><span>Rows</span><span>${escapeHtml(rows.row_count ?? 0)} rows / copied ${escapeHtml(rows.content_copied ?? false)} / exposed ${escapeHtml(rows.raw_rows_exposed ?? false)}</span></div>
        <div class="metric"><span>Runner</span><span>${escapeHtml(runner.run_id || 'unknown')} / ${escapeHtml(runner.status || 'unknown')} / input ${escapeHtml(runner.runner_input_gate || 'unknown')}</span></div>
        <div class="metric"><span>Baseline Eval</span><span>${escapeHtml(baseline.eval_id || 'unknown')} / ${escapeHtml(baseline.status || 'unknown')} / ${escapeHtml(baseline.metric_scope || 'unknown')}</span></div>
        <div class="metric"><span>Checks</span><span>source ${escapeHtml(checks.source_ids_match ?? false)} / rows ${escapeHtml(checks.feature_row_count_matches ?? false)} / synthetic ${escapeHtml(checks.synthetic_policy || 'unknown')}</span></div>
        <div class="metric"><span>Training Server</span><span>${escapeHtml(server.integration || 'not_configured')} / ready ${escapeHtml(server.bundle_ready_for_future_runner ?? false)} / dry-run ${escapeHtml(server.dry_run_only ?? false)}</span></div>
        <div class="metric"><span>Gates</span><span>handoff ${escapeHtml(gates.training_handoff || 'unknown')} / training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / claim ${escapeHtml(gates.release_claim || 'not_allowed')}</span></div>
        <div class="metric"><span>Source Refs</span><span>${escapeHtml(sourceText)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(bundle.next_step || server.next_step || 'Connect a training runner')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(bundle.markdown_path || bundle.report_path || 'unknown')}</span></div>
      `;
    }
    function trainingJobPlanPanel(plan) {
      if (!plan || !plan.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(plan && plan.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(plan && plan.reason || 'no_training_job_plan')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(plan && plan.next_step || 'Create a training job plan')}</span></div>
        `;
      }
      const source = plan.source_handoff || {};
      const sourceRef = source.ref || {};
      const dataset = plan.dataset || {};
      const input = plan.feature_input || {};
      const model = plan.model_plan || {};
      const runner = plan.runner_plan || {};
      const checks = plan.checks || {};
      const gates = plan.gates || {};
      const metrics = plan.metrics_plan || {};
      const classification = metrics.classification || {};
      const operations = metrics.operations || {};
      const power = metrics.power || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(plan.status)}">${escapeHtml(plan.status || 'unknown')}</span></div>
        <div class="metric"><span>Job</span><b>${escapeHtml(plan.job_id || 'unknown')}</b></div>
        <div class="metric"><span>Reason</span><span>${escapeHtml(plan.reason || 'unknown')}</span></div>
        <div class="metric"><span>Source Handoff</span><span>${escapeHtml(source.handoff_id || 'unknown')} / ${escapeHtml(source.status || 'unknown')} / ${escapeHtml(sourceRef.sha256 ? String(sourceRef.sha256).slice(0, 10) : 'nohash')}</span></div>
        <div class="metric"><span>Dataset</span><span>${escapeHtml(dataset.dataset_id || 'unknown')} / ${escapeHtml(dataset.status || 'unknown')} / ${escapeHtml(dataset.eligible_records ?? 0)} eligible</span></div>
        <div class="metric"><span>Feature Input</span><span>${escapeHtml(input.feature_set_id || 'unknown')} / ${escapeHtml(input.row_count ?? 0)} rows / copied ${escapeHtml(input.row_contents_copied ?? false)}</span></div>
        <div class="metric"><span>Model Plan</span><span>${escapeHtml(model.model_track || 'unknown')} / ${escapeHtml(model.candidate_model || 'unknown')} vs ${escapeHtml(model.baseline_model || 'unknown')}</span></div>
        <div class="metric"><span>Runner Queue</span><span>${escapeHtml(runner.runner_profile || 'unknown')} / ${escapeHtml(runner.queue_state || 'unknown')} / ${escapeHtml(runner.training_server_integration || 'not_configured')}</span></div>
        <div class="metric"><span>Runner Ready</span><span>${escapeHtml(runner.bundle_ready_for_future_runner ?? false)} / dry-run ${escapeHtml(runner.dry_run_only ?? false)} / refs-only ${escapeHtml(runner.uses_feature_row_refs_only ?? true)}</span></div>
        <div class="metric"><span>Planned Metrics</span><span>accuracy ${escapeHtml(classification.accuracy || 'planned_not_measured')} / latency ${escapeHtml(operations.latency_ms || 'planned_not_measured')} / power ${escapeHtml(power.energy_per_inference || 'planned_not_measured')}</span></div>
        <div class="metric"><span>Checks</span><span>handoff ${escapeHtml(checks.handoff_ready ?? false)} / synthetic ${escapeHtml(checks.synthetic_policy || 'unknown')} / endpoint ${escapeHtml(checks.private_endpoint_exposed ?? false)}</span></div>
        <div class="metric"><span>Gates</span><span>job ${escapeHtml(gates.training_job || 'unknown')} / training ${escapeHtml(gates.model_training || 'not_run')} / artifact ${escapeHtml(gates.model_artifact || 'not_produced')} / claim ${escapeHtml(gates.release_claim || 'not_allowed')}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(plan.next_step || 'Connect a real runner')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(plan.markdown_path || plan.report_path || 'unknown')}</span></div>
      `;
    }
    function syntheticTrainingChainPanel(chain) {
      if (!chain || !chain.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(chain && chain.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(chain && chain.reason || 'no_synthetic_training_chain')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(chain && chain.next_step || 'Run the synthetic training chain smoke')}</span></div>
        `;
      }
      const counts = chain.counts || {};
      const components = chain.components || {};
      const synthetic = components.synthetic_scenarios || {};
      const data = components.data_flywheel || {};
      const initial = data.initial || {};
      const reviewed = data.reviewed || {};
      const training = components.training_chain || {};
      const preflight = training.preflight || {};
      const feature = training.feature_manifest || {};
      const runner = training.runner_dry_run || {};
      const baseline = training.baseline_eval || {};
      const handoff = training.handoff_bundle || {};
      const job = training.job_plan || {};
      const scope = chain.scope || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(chain.status)}">${escapeHtml(chain.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(chain.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Demo</span><span>${escapeHtml(chain.serves_demo || 'D5')} / synthetic ${escapeHtml(chain.synthetic_only ?? true)}</span></div>
        <div class="metric"><span>Scenarios</span><span>${escapeHtml((chain.scenarios || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Counts</span><span>${escapeHtml(counts.recordings ?? 0)} recordings / ${escapeHtml(counts.reviewed_records ?? 0)} reviewed / ${escapeHtml(counts.feature_rows ?? 0)} rows</span></div>
        <div class="metric"><span>Synthetic Review</span><span>${escapeHtml(synthetic.status || 'unknown')} / failed ${escapeHtml(synthetic.failed_reviews ?? 0)} / seed ${escapeHtml(synthetic.seed ?? 'unknown')}</span></div>
        <div class="metric"><span>Data Pipeline</span><span>initial ${escapeHtml(initial.status || 'unknown')} / reviewed ${escapeHtml(reviewed.status || 'unknown')} / eligible ${escapeHtml(reviewed.eligible_records ?? 0)}</span></div>
        <div class="metric"><span>Preflight</span><span>${escapeHtml(preflight.status || 'unknown')} / ${escapeHtml(preflight.run_id || 'unknown')}</span></div>
        <div class="metric"><span>Feature Manifest</span><span>${escapeHtml(feature.status || 'unknown')} / ${escapeHtml(feature.feature_set_id || 'unknown')} / rows ${escapeHtml(feature.row_count ?? 0)}</span></div>
        <div class="metric"><span>Runner Dry-Run</span><span>${escapeHtml(runner.status || 'unknown')} / rows ${escapeHtml(runner.row_count ?? 0)}</span></div>
        <div class="metric"><span>Baseline Eval</span><span>${escapeHtml(baseline.status || 'unknown')} / ${escapeHtml(baseline.metric_scope || 'unknown')} / claim ${escapeHtml(baseline.product_performance_claim ?? false)}</span></div>
        <div class="metric"><span>Handoff</span><span>${escapeHtml(handoff.status || 'unknown')} / ${escapeHtml(handoff.training_server || 'not_configured')} / dry-run ${escapeHtml(handoff.dry_run_only ?? false)}</span></div>
        <div class="metric"><span>Job Plan</span><span>${escapeHtml(job.status || 'unknown')} / ${escapeHtml(job.queue_state || 'unknown')} / ${escapeHtml(job.runner_profile || 'unknown')}</span></div>
        <div class="metric"><span>Scope</span><span>hardware ${escapeHtml(scope.hardware_contacted ?? false)} / hub ${escapeHtml(scope.message_hub_contacted ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / artifact ${escapeHtml(scope.model_artifact_written ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(chain.next_step || training.next_step || 'Repeat with reviewed real records')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(chain.markdown_path || chain.report_path || 'unknown')}</span></div>
      `;
    }
    function d1TrainingReadinessPanel(report) {
      if (!report || !report.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(report && report.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(report && report.reason || 'no_d1_training_readiness')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(report && report.next_step || 'Run a D1 training-readiness assessment')}</span></div>
        `;
      }
      const source = report.source_observation || {};
      const coverage = report.evidence_coverage || {};
      const capture = coverage.capture || {};
      const transport = coverage.transport || {};
      const location = coverage.location || {};
      const sensors = coverage.sensors || {};
      const readiness = report.readiness || {};
      const gates = report.gates || {};
      const scope = report.scope || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(report.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Source</span><span>${escapeHtml(source.run_id || 'unknown')} / ${escapeHtml(source.status || 'unknown')} / ${escapeHtml(source.result || 'unknown')}</span></div>
        <div class="metric"><span>Capture</span><span>${escapeHtml(capture.successful_sample_count ?? 0)} ok / ${escapeHtml(capture.sample_count ?? 0)} samples / seq ${escapeHtml(source.latest_seq ?? 'unknown')}</span></div>
        <div class="metric"><span>Transport</span><span>${escapeHtml(transport.raw_post_success_delta ?? 0)} ok / ${escapeHtml(transport.raw_post_failure_delta ?? 0)} fail / LTE ${escapeHtml(transport.lte_registration_seen ?? false)} / PDP ${escapeHtml(transport.pdp_active_seen ?? false)}</span></div>
        <div class="metric"><span>Location</span><span>${escapeHtml(location.coordinate_sample_count ?? 0)} coordinate samples / GNSS fix ${escapeHtml(location.gnss_fix_seen ?? false)} / copied ${escapeHtml(location.coordinate_values_copied ?? false)}</span></div>
        <div class="metric"><span>Sensor Gaps</span><span>IMU ${escapeHtml((sensors.imu_evidence_statuses || []).join(', ') || 'unknown')} / Power ${escapeHtml((sensors.power_evidence_statuses || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>Review Ready</span><span>${escapeHtml(readiness.ready_for_labeling_review ?? false)} / training handoff ${escapeHtml(readiness.ready_for_training_handoff ?? false)} / allowed ${escapeHtml(readiness.training_allowed ?? false)}</span></div>
        <div class="metric"><span>Review State</span><span>privacy ${escapeHtml(readiness.privacy_review || 'unknown')} / labels ${escapeHtml(readiness.label_review_state || 'unknown')} / split ${escapeHtml(readiness.split_leakage_checked ?? false)}</span></div>
        <div class="metric"><span>Gates</span><span>field ${escapeHtml((gates.field_observation || {}).status || 'unknown')} / privacy ${escapeHtml((gates.privacy || {}).status || 'unknown')} / labels ${escapeHtml((gates.labels || {}).status || 'unknown')} / claim ${escapeHtml((gates.release_claim || {}).status || 'unknown')}</span></div>
        <div class="metric"><span>Blockers</span><span>${escapeHtml((readiness.blockers || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Scope</span><span>jsonl ${escapeHtml(scope.sample_jsonl_read ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / artifact ${escapeHtml(scope.model_artifact_written ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(report.next_step || 'Attach labels and privacy review')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</span></div>
      `;
    }
    function d1LabelingIntakePanel(report) {
      if (!report || !report.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(report && report.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(report && report.reason || 'no_d1_labeling_intake')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(report && report.next_step || 'Build a D1 labeling intake report')}</span></div>
        `;
      }
      const source = report.source_observation || {};
      const readiness = report.source_readiness || {};
      const coverage = report.evidence_coverage || {};
      const transport = coverage.transport || {};
      const location = coverage.location || {};
      const sensors = coverage.sensors || {};
      const queue = report.intake_queue || {};
      const labelReq = report.labeling_request || {};
      const gates = report.review_gates || {};
      const scope = report.scope || {};
      const items = queue.items || [];
      const first = items[0] || {};
      const review = first.review_state || {};
      const evidence = first.evidence_summary || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(report.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Source</span><span>${escapeHtml(readiness.run_id || 'unknown')} / ${escapeHtml(readiness.status || 'unknown')} -> ${escapeHtml(source.run_id || 'unknown')}</span></div>
        <div class="metric"><span>Queue</span><span>${escapeHtml(queue.pending_items ?? 0)} pending / next ${escapeHtml(queue.next_queue || 'unknown')}</span></div>
        <div class="metric"><span>First Intake</span><span>${escapeHtml(first.intake_id || 'none')} / ${escapeHtml(first.status || 'none')}</span></div>
        <div class="metric"><span>Review State</span><span>label ${escapeHtml(review.operator_label || 'missing')} / privacy ${escapeHtml(review.privacy_review || 'required')} / consent ${escapeHtml(review.training_consent || 'not_reviewed')} / split ${escapeHtml(review.split_plan || 'missing')}</span></div>
        <div class="metric"><span>Evidence</span><span>${escapeHtml(evidence.samples ?? source.successful_sample_count ?? 0)} samples / seq ${escapeHtml(evidence.latest_seq ?? source.latest_seq ?? 'unknown')} / POST ${escapeHtml(transport.raw_post_success_delta ?? evidence.raw_post_success_delta ?? 0)} ok</span></div>
        <div class="metric"><span>Location Scope</span><span>${escapeHtml(location.coordinate_sample_count ?? evidence.coordinate_sample_count ?? 0)} coordinate samples / copied ${escapeHtml(location.coordinate_values_copied ?? false)} / accuracy claim ${escapeHtml(location.accuracy_claimed ?? false)}</span></div>
        <div class="metric"><span>Sensor Gaps</span><span>IMU ${escapeHtml((sensors.imu_evidence_statuses || evidence.imu_evidence_statuses || []).join(', ') || 'unknown')} / Power ${escapeHtml((sensors.power_evidence_statuses || evidence.power_evidence_statuses || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>Label Groups</span><span>${escapeHtml((labelReq.requested_label_groups || []).join(', ') || 'none')} / text ${escapeHtml(labelReq.free_text_policy || 'unknown')}</span></div>
        <div class="metric"><span>Gates</span><span>readiness ${escapeHtml(gates.training_readiness || 'unknown')} / label ${escapeHtml(gates.operator_label || 'unknown')} / privacy ${escapeHtml(gates.privacy_review || 'unknown')} / candidate ${escapeHtml(gates.candidate_store || 'unknown')}</span></div>
        <div class="metric"><span>Blockers</span><span>${escapeHtml((report.blockers || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Scope</span><span>jsonl ${escapeHtml(scope.sample_jsonl_read ?? false)} / db ${escapeHtml(scope.candidate_db_written ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(report.next_step || 'Collect labels and reviews')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</span></div>
      `;
    }
    function d1LabelingQueuePanel(report) {
      if (!report || !report.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(report && report.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(report && report.reason || 'no_d1_labeling_queue')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(report && report.next_step || 'Build a D1 labeling queue index')}</span></div>
        `;
      }
      const summary = report.summary || {};
      const queue = report.queue || {};
      const items = queue.items || [];
      const first = items[0] || {};
      const review = first.review_state || {};
      const evidence = first.evidence_summary || {};
      const gates = report.review_gates || {};
      const scope = report.scope || {};
      const reports = report.intake_reports || [];
      const firstReport = reports[0] || {};
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(report.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Pending Items</span><span>${escapeHtml(queue.pending_items ?? summary.pending_items ?? 0)} pending / reports ${escapeHtml(summary.intake_report_count ?? reports.length ?? 0)}</span></div>
        <div class="metric"><span>Review Queue</span><span>label ${escapeHtml(summary.needs_operator_label ?? 0)} / privacy ${escapeHtml(summary.needs_privacy_review ?? 0)} / consent ${escapeHtml(summary.needs_training_consent ?? 0)} / split ${escapeHtml(summary.needs_split_plan ?? 0)}</span></div>
        <div class="metric"><span>First Queue Item</span><span>${escapeHtml(first.queue_id || first.intake_id || 'none')} / ${escapeHtml(first.status || 'none')} / ${escapeHtml(first.source_run_id || 'unknown')}</span></div>
        <div class="metric"><span>Review State</span><span>label ${escapeHtml(review.operator_label || 'missing')} / privacy ${escapeHtml(review.privacy_review || 'required')} / consent ${escapeHtml(review.training_consent || 'not_reviewed')} / split ${escapeHtml(review.split_plan || 'missing')}</span></div>
        <div class="metric"><span>Evidence</span><span>${escapeHtml(evidence.samples ?? 0)} samples / seq ${escapeHtml(evidence.latest_seq ?? 'unknown')} / POST ${escapeHtml(evidence.raw_post_success_delta ?? 0)} ok / ${escapeHtml(evidence.raw_post_failure_delta ?? 0)} fail</span></div>
        <div class="metric"><span>Location Scope</span><span>${escapeHtml(evidence.coordinate_sample_count ?? 0)} coordinate samples / GNSS fix ${escapeHtml(evidence.gnss_fix_seen ?? false)} / exact copied ${escapeHtml(scope.exact_coordinates_copied ?? false)}</span></div>
        <div class="metric"><span>Sensor Gaps</span><span>IMU ${escapeHtml((evidence.imu_evidence_statuses || []).join(', ') || 'unknown')} / Power ${escapeHtml((evidence.power_evidence_statuses || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>Gates</span><span>intake ${escapeHtml(gates.labeling_intake || 'unknown')} / label ${escapeHtml(gates.operator_label || 'unknown')} / privacy ${escapeHtml(gates.privacy_review || 'unknown')} / candidate ${escapeHtml(gates.candidate_store || 'unknown')}</span></div>
        <div class="metric"><span>Latest Intake</span><span>${escapeHtml(firstReport.run_id || 'none')} / ${escapeHtml(firstReport.status || 'unknown')} / ${escapeHtml(firstReport.pending_items ?? 0)} pending</span></div>
        <div class="metric"><span>Blockers</span><span>${escapeHtml((report.blockers || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Scope</span><span>jsonl ${escapeHtml(scope.sample_jsonl_read ?? false)} / db ${escapeHtml(scope.candidate_db_written ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / artifact ${escapeHtml(scope.model_artifact_written ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(report.next_step || 'Review queue items before candidate-store writes')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</span></div>
      `;
    }
    function d1LabelingReviewPacketPanel(report) {
      if (!report || !report.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(report && report.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(report && report.reason || 'no_d1_labeling_review_packet')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(report && report.next_step || 'Build a D1 labeling review packet')}</span></div>
        `;
      }
      const summary = report.summary || {};
      const sourceQueue = report.source_queue || {};
      const packet = report.review_packet || {};
      const items = packet.items || [];
      const first = items[0] || {};
      const review = first.current_review_state || {};
      const evidence = first.evidence_summary || {};
      const slots = first.decision_slots || {};
      const gates = report.review_gates || {};
      const scope = report.scope || {};
      const slotNames = Object.keys(slots);
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(report.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Source Queue</span><span>${escapeHtml(sourceQueue.run_id || 'none')} / ${escapeHtml(sourceQueue.status || 'unknown')} / ${escapeHtml(sourceQueue.pending_item_count ?? summary.queue_pending_items ?? 0)} pending</span></div>
        <div class="metric"><span>Review Packet</span><span>${escapeHtml(summary.review_packet_items ?? items.length ?? 0)} items / ${escapeHtml(packet.status || 'unknown')}</span></div>
        <div class="metric"><span>Needed Reviews</span><span>label ${escapeHtml(summary.needs_operator_label ?? 0)} / privacy ${escapeHtml(summary.needs_privacy_review ?? 0)} / consent ${escapeHtml(summary.needs_training_consent ?? 0)} / split ${escapeHtml(summary.needs_split_plan ?? 0)}</span></div>
        <div class="metric"><span>First Review Item</span><span>${escapeHtml(first.packet_item_id || first.intake_id || 'none')} / ${escapeHtml(first.queue_status || 'none')} / ${escapeHtml(first.source_run_id || 'unknown')}</span></div>
        <div class="metric"><span>Current Review</span><span>label ${escapeHtml(review.operator_label || 'missing')} / privacy ${escapeHtml(review.privacy_review || 'required')} / consent ${escapeHtml(review.training_consent || 'not_reviewed')} / split ${escapeHtml(review.split_plan || 'missing')}</span></div>
        <div class="metric"><span>Decision Slots</span><span>${escapeHtml(slotNames.join(', ') || 'none')}</span></div>
        <div class="metric"><span>Evidence</span><span>${escapeHtml(evidence.samples ?? 0)} samples / seq ${escapeHtml(evidence.latest_seq ?? 'unknown')} / POST ${escapeHtml(evidence.raw_post_success_delta ?? 0)} ok / ${escapeHtml(evidence.raw_post_failure_delta ?? 0)} fail</span></div>
        <div class="metric"><span>Location Scope</span><span>${escapeHtml(evidence.coordinate_sample_count ?? 0)} coordinate samples / GNSS fix ${escapeHtml(evidence.gnss_fix_seen ?? false)} / exact copied ${escapeHtml(scope.exact_coordinates_copied ?? false)}</span></div>
        <div class="metric"><span>Sensor Gaps</span><span>IMU ${escapeHtml((evidence.imu_evidence_statuses || []).join(', ') || 'unknown')} / Power ${escapeHtml((evidence.power_evidence_statuses || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>Gates</span><span>candidate ${escapeHtml(gates.candidate_store || 'unknown')} / training ${escapeHtml(gates.model_training || 'unknown')} / release ${escapeHtml(gates.release_claim || 'unknown')}</span></div>
        <div class="metric"><span>Scope</span><span>jsonl ${escapeHtml(scope.sample_jsonl_read ?? false)} / payload ${escapeHtml(scope.payload_bytes_copied ?? false)} / db ${escapeHtml(scope.candidate_db_written ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / artifact ${escapeHtml(scope.model_artifact_written ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(report.next_step || 'Fill review decisions before candidate-store writes')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</span></div>
      `;
    }
    function d1LabelingDecisionTemplatePanel(report) {
      if (!report || !report.available) {
        return `
          <div class="metric"><span>Status</span><span class="empty">${escapeHtml(report && report.status || 'not_available')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(report && report.reason || 'no_d1_labeling_decision_template')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(report && report.next_step || 'Build a D1 labeling decision template')}</span></div>
        `;
      }
      const summary = report.summary || {};
      const source = report.source_review_packet || {};
      const template = report.decision_template || {};
      const items = template.items || [];
      const first = items[0] || {};
      const fields = first.decision_fields || {};
      const evidence = first.evidence_summary || {};
      const gates = report.review_gates || {};
      const scope = report.scope || {};
      const fieldNames = Object.keys(fields);
      const selected = fieldNames.filter(name => {
        const field = fields[name] || {};
        return field.selected !== undefined && field.selected !== null && field.selected !== '';
      }).length;
      return `
        <div class="metric"><span>Status</span><span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span></div>
        <div class="metric"><span>Run</span><b>${escapeHtml(report.run_id || 'unknown')}</b></div>
        <div class="metric"><span>Source Review</span><span>${escapeHtml(source.run_id || 'none')} / ${escapeHtml(source.status || 'unknown')} / ${escapeHtml(source.review_packet_items ?? summary.review_packet_items ?? 0)} items</span></div>
        <div class="metric"><span>Template Items</span><span>${escapeHtml(summary.template_items ?? items.length ?? 0)} items / ${escapeHtml(template.status || 'unknown')}</span></div>
        <div class="metric"><span>Decision Progress</span><span>${escapeHtml(summary.selected_decision_fields ?? selected)} selected / ${escapeHtml(summary.required_decision_fields ?? fieldNames.length)} required / ready ${escapeHtml(summary.items_ready_for_validation ?? 0)}</span></div>
        <div class="metric"><span>First Template Item</span><span>${escapeHtml(first.packet_item_id || first.intake_id || 'none')} / ${escapeHtml(first.validation_state || 'not_submitted')} / ${escapeHtml(first.source_run_id || 'unknown')}</span></div>
        <div class="metric"><span>Decision Fields</span><span>${escapeHtml(fieldNames.join(', ') || 'none')}</span></div>
        <div class="metric"><span>Selected Values</span><span>label ${escapeHtml((fields.operator_label || {}).selected || 'TODO')} / privacy ${escapeHtml((fields.privacy_review || {}).selected || 'TODO')} / consent ${escapeHtml((fields.training_consent || {}).selected || 'TODO')} / split ${escapeHtml((fields.split_plan || {}).selected || 'TODO')} / candidate ${escapeHtml((fields.candidate_decision || {}).selected || 'TODO')}</span></div>
        <div class="metric"><span>Evidence</span><span>${escapeHtml(evidence.samples ?? 0)} samples / seq ${escapeHtml(evidence.latest_seq ?? 'unknown')} / POST ${escapeHtml(evidence.raw_post_success_delta ?? 0)} ok / ${escapeHtml(evidence.raw_post_failure_delta ?? 0)} fail</span></div>
        <div class="metric"><span>Location Scope</span><span>${escapeHtml(evidence.coordinate_sample_count ?? 0)} coordinate samples / GNSS fix ${escapeHtml(evidence.gnss_fix_seen ?? false)} / exact copied ${escapeHtml(scope.exact_coordinates_copied ?? false)}</span></div>
        <div class="metric"><span>Gates</span><span>candidate ${escapeHtml(gates.candidate_store || 'unknown')} / training ${escapeHtml(gates.model_training || 'unknown')} / release ${escapeHtml(gates.release_claim || 'unknown')}</span></div>
        <div class="metric"><span>Scope</span><span>jsonl ${escapeHtml(scope.sample_jsonl_read ?? false)} / payload ${escapeHtml(scope.payload_bytes_copied ?? false)} / db ${escapeHtml(scope.candidate_db_written ?? false)} / training ${escapeHtml(scope.model_training_started ?? false)} / artifact ${escapeHtml(scope.model_artifact_written ?? false)} / claim ${escapeHtml(scope.release_claim_allowed ?? false)}</span></div>
        <div class="metric"><span>Next Step</span><span>${escapeHtml(report.next_step || 'Fill selected values before validation')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</span></div>
      `;
    }
    function firstReportByKind(reports, kinds) {
      return (Array.isArray(reports) ? reports : []).find(report => kinds.includes(report.kind)) || {};
    }
    function evidenceLane(label, report, fallbackStatus = 'not_available', fallbackNote = 'waiting for report') {
      const status = report.status || fallbackStatus;
      const detail = report.run_id || report.summary || fallbackNote;
      return `
        <div class="evidence-lane">
          <span class="lane-label">${escapeHtml(label)}</span>
          <span class="lane-value ${statusClass(status)}">${escapeHtml(status)}</span>
          <span class="lane-note">${escapeHtml(detail)}</span>
        </div>
      `;
    }
    function fieldResultsPanel(results, flywheel = {}) {
      const reports = Array.isArray(results && results.reports) ? results.reports : [];
      const d2Baseline = firstReportByKind(reports, ['d2_location_accuracy', 'location_accuracy']);
      const d1Regression = firstReportByKind(reports, ['d1_postrun', 'd1_field_observation', 'd1_web_api']);
      const powerBaseline = firstReportByKind(reports, ['power_curve']);
      const flywheelReport = flywheel && flywheel.available ? {
        status: flywheel.status || 'unknown',
        run_id: flywheel.run_id || flywheel.dataset_id,
        summary: flywheel.next_step || 'data flywheel status available',
      } : {};
      const lanes = `
        <div id="fieldEvidenceLanes" class="evidence-lanes">
          ${evidenceLane('D2 定位基线', d2Baseline, 'not_available', 'reports/location_accuracy')}
          ${evidenceLane('D1 外场回归', d1Regression, results && results.status || 'not_available', 'field results')}
          ${evidenceLane('功耗', powerBaseline, 'not_available', 'power curve')}
          ${evidenceLane('D5 数据闭环', flywheelReport, flywheel && flywheel.status || 'not_available', flywheel && flywheel.next_step || 'data flywheel')}
        </div>
      `;
      if (!results || !results.available) {
        return `
          ${lanes}
          <div class="metric"><span>总体状态</span><span class="empty">${escapeHtml(results && results.status || 'not_available')}</span></div>
          <div class="metric"><span>原因</span><span>${escapeHtml(results && results.reason || 'no_field_result_reports')}</span></div>
          <div class="metric"><span>下一步</span><span>${escapeHtml(results && results.next_step || '生成 D1 外场报告')}</span></div>
        `;
      }
      const cards = reports.map(report => `
        <div class="report-card">
          <div class="report-head">
            <span class="report-title">${escapeHtml(report.title || report.kind || 'Report')}</span>
            <span class="${statusClass(report.status)}">${escapeHtml(report.status || 'unknown')}</span>
          </div>
          <div class="report-meta">${escapeHtml(report.run_id || 'no run id')} / ${escapeHtml(report.created_at || 'unknown')}</div>
          <div class="card-note">${escapeHtml(report.summary || 'no summary')}</div>
          <div class="report-metrics">${metricRows(report.metrics || {})}</div>
          <div class="report-path">报告：${escapeHtml(report.markdown_path || report.report_path || 'unknown')}</div>
          <div class="report-meta">警告：${escapeHtml(reportWarnings(report))}</div>
        </div>
      `).join('');
      return `
        ${lanes}
        <div class="metric"><span>总体状态</span><span class="${statusClass(results.status)}">${escapeHtml(results.status || 'unknown')}</span></div>
        <div class="metric"><span>报告</span><span>${escapeHtml(results.report_count ?? 0)} 份摘要 / 最新 ${escapeHtml(results.latest_created_at || 'unknown')}</span></div>
        <div class="metric"><span>下一步</span><span>${escapeHtml(results.next_step || '生成下一份外场报告')}</span></div>
        <div id="fieldResultsCards" class="report-grid">${cards}</div>
      `;
    }
    function d1StatusClass(status) {
      if (status === 'estimate_visible') return 'ok';
      if (status === 'waiting_for_location_upload') return 'warn';
      return 'empty';
    }
    function valueOrUnknown(value, fallback = 'unknown') {
      if (value === undefined || value === null || value === '') return fallback;
      return value;
    }
    function boolSeen(value) {
      if (value === true) return '已观测';
      if (value === false) return '未观测';
      return '未知';
    }
    function freshnessLabel(freshness) {
      const seconds = Number(freshness.freshness_s);
      if (!Number.isFinite(seconds)) return '时间未知';
      if (seconds < 60) return `${Math.max(0, Math.round(seconds))} 秒前`;
      return `${Math.round(seconds / 60)} 分钟前`;
    }
    function freshnessClass(freshness) {
      const seconds = Number(freshness.freshness_s);
      if (!Number.isFinite(seconds)) return 'warn';
      if (seconds <= 180) return 'ok';
      if (seconds <= 600) return 'warn';
      return 'bad';
    }
    function readinessClass(readiness) {
      const state = readiness.state || 'waiting_for_data';
      if (state === 'ready') return 'ok';
      if (state === 'stale' || state === 'waiting_for_data') return 'warn';
      return 'bad';
    }
    function acceptanceClass(gate) {
      if ((gate.status || '') === 'ready') return 'ok';
      if ((gate.status || '') === 'blocked') return 'bad';
      return 'warn';
    }
    function acceptanceLabel(gate) {
      if ((gate.status || '') === 'ready') return 'ready';
      if ((gate.status || '') === 'blocked') return 'blocked';
      return 'checking';
    }
    function acceptanceHeadline(gate) {
      if ((gate.status || '') === 'ready') return '可开始 D1 外场验收';
      if ((gate.status || '') === 'blocked') return 'D1 外场验收尚未就绪';
      return '正在检查 D1 外场验收条件';
    }
    function readinessLabel(readiness) {
      const state = readiness.state || 'waiting_for_data';
      if (state === 'ready') return 'ready';
      if (state === 'stale') return 'stale';
      if (state === 'not_ready') return 'not ready';
      return 'waiting';
    }
    function readinessHeadline(readiness) {
      const state = readiness.state || 'waiting_for_data';
      const freshness = Number(readiness.freshness_s);
      const age = Number.isFinite(freshness) ? `${Math.max(0, Math.round(freshness))} 秒前` : '时间未知';
      if (state === 'ready') return `就绪 / ${age}`;
      if (state === 'stale') return `数据已过期 / ${age}`;
      if (state === 'not_ready') return `未就绪 / ${age}`;
      return `等待数据 / ${age}`;
    }
    function arrayLabel(values) {
      return Array.isArray(values) && values.length ? values.join(', ') : 'none';
    }
    function coordinateLabel(lat, lon) {
      const parsedLat = Number(lat);
      const parsedLon = Number(lon);
      if (Number.isFinite(parsedLat) && Number.isFinite(parsedLon)) {
        return `${parsedLat.toFixed(6)}, ${parsedLon.toFixed(6)}`;
      }
      return 'no coordinate';
    }
    function normalizeMapPoints(points) {
      const parsed = (Array.isArray(points) ? points : [])
        .map(point => ({
          ...point,
          lat: Number(point.lat),
          lon: Number(point.lon),
        }))
        .filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon));
      if (!parsed.length) return [];
      const lats = parsed.map(point => point.lat);
      const lons = parsed.map(point => point.lon);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);
      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const latRange = Math.max(maxLat - minLat, 0.000001);
      const lonRange = Math.max(maxLon - minLon, 0.000001);
      return parsed.map(point => ({
        ...point,
        x: 8 + ((point.lon - minLon) / lonRange) * 84,
        y: 92 - ((point.lat - minLat) / latRange) * 84,
      }));
    }
    function d1MapTrack(points, referencePoints = [], positionPoint = null, positionKind = 'last-known') {
      const observedInput = (Array.isArray(points) ? points : []).map(point => ({...point, point_kind: 'selected'}));
      const referenceInput = (Array.isArray(referencePoints) ? referencePoints : []).map(point => ({...point, point_kind: 'reference'}));
      const positionInput = positionPoint ? [{...positionPoint, point_kind: 'position'}] : [];
      const normalized = normalizeMapPoints([...observedInput, ...positionInput, ...referenceInput]);
      if (!normalized.length) return '';
      const observed = normalized.filter(point => point.point_kind === 'selected');
      const position = normalized.find(point => point.point_kind === 'position') || null;
      const references = normalized.filter(point => point.point_kind === 'reference');
      const localSegments = trajectorySegments(observed).filter(segment => segment.length >= 2);
      const polyline = localSegments.length
        ? `<svg class="map-track" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${localSegments.map(segment => `<polyline points="${segment.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')}" fill="none" stroke="#1f6feb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" opacity="0.8"/>`).join('')}</svg>`
        : '';
      const markers = observed.map((point, index) => {
        const start = observed.length >= 2 && index === 0;
        const end = index === observed.length - 1;
        const label = `${start ? '所选起点' : end ? '所选终点' : '所选历史点'} / seq ${point.seq ?? '未知'} / ${formatDashboardDateTime(point.server_received_at)}`;
        const markerClass = end ? 'map-point-end' : start ? 'map-point-start' : '';
        return `<span class="map-point ${markerClass}" title="${escapeHtml(label)}" style="left:${point.x.toFixed(2)}%; top:${point.y.toFixed(2)}%;"></span>`;
      }).join('');
      const positionMarker = position ? (() => {
        const positionLabel = positionKind === 'current'
          ? '当前 GNSS 定位'
          : positionKind === 'stale'
            ? '历史位置（已过期）'
            : '最后可信位置';
        const markerClass = positionKind === 'current'
          ? 'map-point-current'
          : positionKind === 'stale'
            ? 'map-point-stale'
            : 'map-point-end';
        const label = `${positionLabel} / seq ${position.seq ?? '未知'} / ${formatDashboardDateTime(position.server_received_at)}`;
        return `<span class="map-point map-point-position ${markerClass}" title="${escapeHtml(label)}" style="left:${position.x.toFixed(2)}%; top:${position.y.toFixed(2)}%;"></span>`;
      })() : '';
      const referenceMarkers = references.map(point => {
        const label = `${point.label || point.name || 'D2 reference'} ${coordinateLabel(point.lat, point.lon)}`;
        return `<span class="map-point map-point-reference" title="${escapeHtml(label)}" style="left:${point.x.toFixed(2)}%; top:${point.y.toFixed(2)}%;"></span>`;
      }).join('');
      return polyline + markers + positionMarker + referenceMarkers;
    }
    function d1MapSurface(map, estimate, readiness = {}, deviceId = '') {
      const mode = map.mode || 'waiting_for_location_upload';
      let points = Array.isArray(map.points) ? map.points : [];
      const allTrustedPoints = points.filter(point => point && point.amap_eligible === true && point.coordinate_contract === 'wgs84');
      const selectionView = trajectorySelectionForPoints(deviceId || 'local-map', allTrustedPoints);
      const trustedPoints = boundedTrajectorySelection(
        selectionView.selectedPoints,
        locationHistorySelectedPoints(deviceId || 'local-map'),
      ).selectedPoints;
      const positionSemantics = amapPositionSemantics(map, estimate, readiness);
      const positionPoint = positionSemantics.current || null;
      const referencePoints = Array.isArray(map.reference_points) ? map.reference_points : [];
      const provider = map.provider || {};
      const privacy = map.privacy || {};
      const layers = map.layers || {};
      const trajectory = map.trajectory || {};
      const coord = map.coordinate_diagnostics || {};
      const pointCount = trajectory.point_count ?? points.length;
      const coordCount = coord.coordinate_event_count ?? pointCount;
      const eventCount = coord.location_event_count ?? pointCount;
      const providerMode = provider.mode || 'none';
      const providerStatus = provider.status || 'not_configured';
      const reviewMode = map.review_mode || 'local_no_key';
      const providerLabel = providerMode === 'none' ? '本地轨迹示意图' : `地图服务 ${providerMode}`;
      const surfaceVisible = map.visible || positionPoint || trustedPoints.length > 0 || referencePoints.length > 0;
      const latestFix = coord.latest_fix;
      const predicted = String(estimate.state || '').trim().toLowerCase() === 'predicted';
      const freshnessThreshold = Number(readiness.freshness_threshold_s ?? 180);
      const exclusionReasons = new Set(points.map(point => point && point.amap_exclusion_reason).filter(Boolean));
      const hiddenPreCorrection = !allTrustedPoints.length && exclusionReasons.has('firmware_parser_not_allowlisted');
      const hiddenNoLineage = !allTrustedPoints.length && exclusionReasons.has('location_memory_has_no_coordinate_provenance');
      const hiddenNoFix = !allTrustedPoints.length && (latestFix === false || exclusionReasons.has('gnss_fix_not_true'));
      const selectionEmpty = allTrustedPoints.length > 0 && !trustedPoints.length;
      const hiddenMessage = selectionEmpty
        ? `${positionSemantics.label}；当前未选择轨迹记录`
        : hiddenNoFix
        ? '当前 GNSS 未定位，暂无可信轨迹'
        : hiddenPreCorrection
          ? '旧版坐标已隐藏，等待修正版固件产生新的可信 GNSS 定位'
          : hiddenNoLineage
            ? '最后位置缺少可信坐标，暂不显示'
            : !allTrustedPoints.length && points.length
              ? '暂无可绘制的可信 GNSS 定位'
              : '';
      const caption = surfaceVisible
        ? hiddenMessage
          ? hiddenMessage
          : `${positionSemantics.label} / 已选 ${trustedPoints.length}/${allTrustedPoints.length} 个可信轨迹点 / ${coordCount}/${eventCount} 条定位上报`
        : '正在等待定位上报';
      points = trustedPoints.map(point => {
        let displaySemantics = 'history';
        if (point.amap_current === true && point.fix === true && !predicted && latestFix !== false) {
          const updatedAt = Date.parse(point.server_received_at || '');
          const ageSeconds = Number.isFinite(updatedAt) ? Math.max(0, Math.round((Date.now() - updatedAt) / 1000)) : null;
          displaySemantics = ageSeconds !== null && Number.isFinite(freshnessThreshold) && ageSeconds > freshnessThreshold
            ? 'stale_fix'
            : 'current_fix';
        }
        return {...point, display_semantics: displaySemantics};
      });
      const marker = surfaceVisible
        ? d1MapTrack(points, referencePoints, positionPoint, positionSemantics.kind) || `<div class="map-waiting">${hiddenMessage || '暂无可信轨迹点'}</div>`
        : '<div class="map-waiting">正在等待定位</div>';
      return `
        <div id="localMapSurface" class="map-surface" data-d1-map-mode="${escapeHtml(mode)}" data-map-review-mode="${escapeHtml(reviewMode)}" data-map-provider-mode="${escapeHtml(providerMode)}">
          <div class="map-grid"></div>
          <div class="map-provider-banner">
            <span>${escapeHtml(providerLabel)}</span>
            <span>服务状态 ${escapeHtml(providerStatus)} / D1 阻塞 ${escapeHtml(provider.blocking_d1 ?? false)}</span>
          </div>
          <div class="map-legend">
            <span class="map-legend-item"><span class="map-legend-dot map-legend-current"></span>当前 / 最后可信点</span>
            <span class="map-legend-item"><span class="map-legend-dot"></span>所选采样 ${escapeHtml(trustedPoints.length)}/${escapeHtml(allTrustedPoints.length)}</span>
            <span class="map-legend-item"><span class="map-legend-dot map-legend-reference"></span>D2 参考点 ${escapeHtml(referencePoints.length)}</span>
            <span class="map-legend-item">底图 ${escapeHtml(layers.provider_tiles ? '在线' : '关闭')}</span>
          </div>
          ${marker}
          <div class="map-caption">${escapeHtml(caption)} / 坐标可见性 ${escapeHtml(privacy.coordinate_visibility || 'bounded')} / 不作定位精度声明</div>
        </div>
      `;
    }
    function setAmapStatus(message, state = 'warn') {
      amapLiveStatus.textContent = message;
      amapLiveStatus.className = state;
      amapLiveShell.dataset.providerState = state;
    }
    function setLocalMapVisibility(visible) {
      const localMap = document.getElementById('localMapSurface');
      if (localMap) localMap.style.display = visible ? '' : 'none';
      const overview = document.getElementById('d1FieldOverview');
      if (overview) overview.classList.toggle('provider-map-active', !visible);
      const locationGrid = document.getElementById('locationMapGrid');
      if (locationGrid) locationGrid.classList.toggle('provider-map-hidden', visible);
    }
    function validMapPoint(point) {
      try {
        return {
          ...point,
          lat: finiteCoordinate(point && point.lat, -90, 90, 'latitude'),
          lon: finiteCoordinate(point && point.lon, -180, 180, 'longitude'),
        };
      } catch (_error) {
        return null;
      }
    }
    function amapEmptyViewCenter() {
      return [104, 35];
    }
    function amapDiagnosticNowMs() {
      return Date.now();
    }
    function amapDiagnosticElapsedMs(startedAt) {
      const elapsed = amapDiagnosticNowMs() - Number(startedAt || 0);
      return String(Number.isFinite(elapsed) ? Math.max(0, Math.min(60000, Math.round(elapsed))) : 0);
    }
    function amapFailureStage(stage) {
      switch (stage) {
        case 'sdk-script-error': return 'sdk-script-error';
        case 'sdk-callback-error': return 'sdk-callback-error';
        case 'sdk-timeout': return 'sdk-timeout';
        case 'sdk-global-missing': return 'sdk-global-missing';
        case 'sdk-load-conflict': return 'sdk-load-conflict';
        case 'map-constructor': return 'map-constructor';
        case 'map-ready-timeout': return 'map-ready-timeout';
        case 'overlay': return 'overlay';
        default: return 'overlay';
      }
    }
    function amapFailureReasonCode(reason) {
      switch (reason) {
        case 'timeout': return 'timeout';
        case 'load-state-conflict': return 'load-state-conflict';
        case 'script-request-failed': return 'script-request-failed';
        case 'provider-callback-error': return 'provider-callback-error';
        case 'sdk-global-missing': return 'sdk-global-missing';
        case 'map-container-missing': return 'map-container-missing';
        case 'map-lifecycle-unavailable': return 'map-lifecycle-unavailable';
        case 'coordinate-conversion-failed': return 'coordinate-conversion-failed';
        case 'provider-state-undefined': return 'provider-state-undefined';
        default: return 'unclassified';
      }
    }
    function amapFailureReason(error) {
      let message = '';
      try {
        message = error && typeof error.message === 'string' ? error.message.slice(0, 256) : '';
      } catch (_messageError) {
        return 'unclassified';
      }
      switch (true) {
        case /timeout/i.test(message): return 'timeout';
        case /load state conflict/i.test(message): return 'load-state-conflict';
        case /request failed/i.test(message): return 'script-request-failed';
        case /provider callback error/i.test(message): return 'provider-callback-error';
        case /JS API unavailable/i.test(message): return 'sdk-global-missing';
        case /map container unavailable/i.test(message): return 'map-container-missing';
        case /map lifecycle unavailable/i.test(message): return 'map-lifecycle-unavailable';
        case /coordinate conversion failed|no valid converted coordinates/i.test(message): return 'coordinate-conversion-failed';
        case /Cannot read properties of undefined/i.test(message): return 'provider-state-undefined';
        default: return 'unclassified';
      }
    }
    function recordAmapPreloadDiagnostics() {
      let windowExtensible = false;
      let defineAmd = false;
      const exportsType = typeof exports;
      const moduleType = typeof module;
      const defineType = typeof define;
      try { windowExtensible = Object.isExtensible(window); } catch (_windowError) {}
      try {
        defineAmd = defineType === 'function' && Boolean(define.amd);
      } catch (_defineError) {}
      amapLiveShell.dataset.preloadWindowExtensible = String(windowExtensible);
      amapLiveShell.dataset.preloadExportsType = exportsType;
      amapLiveShell.dataset.preloadModuleType = moduleType;
      amapLiveShell.dataset.preloadDefineType = defineType;
      amapLiveShell.dataset.preloadDefineAmd = String(defineAmd);
      amapLiveShell.dataset.callbackSeen = 'false';
      amapLiveShell.dataset.failureStage = 'none';
      amapLiveShell.dataset.failureReason = 'none';
      amapLiveShell.dataset.failureElapsedMs = '0';
    }
    function recordAmapFailure(stage, error, startedAt) {
      const safeStage = amapFailureStage(stage);
      const safeReason = amapFailureReasonCode(amapFailureReason(error));
      amapLiveShell.dataset.failureStage = safeStage;
      amapLiveShell.dataset.failureReason = safeReason;
      amapLiveShell.dataset.failureElapsedMs = amapDiagnosticElapsedMs(startedAt);
      return {stage: safeStage, reason: safeReason};
    }
    function clearAmapFailure() {
      amapLiveShell.dataset.failureStage = 'none';
      amapLiveShell.dataset.failureReason = 'none';
      amapLiveShell.dataset.failureElapsedMs = '0';
    }
    function loadAmap() {
      if (!AMAP_JS_API_KEY) return Promise.reject(new Error('provider not configured'));
      if (amapLoadPromise) return amapLoadPromise;
      if (amapMapReady && amapNamespace && amapInstance) return Promise.resolve(amapNamespace);
      amapLiveShell.dataset.lifecycle = 'sdk-loading';
      recordAmapPreloadDiagnostics();
      const sdkStartedAt = amapDiagnosticNowMs();
      amapLoadPromise = new Promise((resolve, reject) => {
        let sdkTimeout = null;
        let script = null;
        let settled = false;
        const cleanup = () => {
          if (sdkTimeout !== null) window.clearTimeout(sdkTimeout);
          if (script) script.onerror = null;
        };
        const failSdkLoad = (stage, error) => {
          if (settled) return;
          settled = true;
          cleanup();
          recordAmapFailure(stage, error, sdkStartedAt);
          // A late provider response may still call the declared callback.
          // Keep a harmless terminal callback instead of causing a new global
          // TypeError after this page has already fallen back to the local map.
          window[AMAP_JS_API_CALLBACK] = () => {};
          reject(error);
        };
        window[AMAP_JS_API_CALLBACK] = providerError => {
          if (settled) return;
          amapLiveShell.dataset.callbackSeen = 'true';
          if (providerError) {
            failSdkLoad('sdk-callback-error', new Error('AMap provider callback error'));
            return;
          }
          if (!window.AMap || typeof window.AMap.Map !== 'function') {
            failSdkLoad('sdk-global-missing', new Error('AMap JS API unavailable'));
            return;
          }
          settled = true;
          cleanup();
          const AMap = window.AMap;
          try { delete window[AMAP_JS_API_CALLBACK]; } catch (_cleanupError) {
            window[AMAP_JS_API_CALLBACK] = undefined;
          }
          resolve(AMap);
        };
        if (window.AMap || document.getElementById(AMAP_JS_API_SCRIPT_ID)) {
          failSdkLoad('sdk-load-conflict', new Error('AMap JS API load state conflict'));
          return;
        }
        try {
          script = document.createElement('script');
          script.id = AMAP_JS_API_SCRIPT_ID;
          script.async = true;
          script.charset = 'utf-8';
          script.dataset.egolinkAmapJsapi = 'v2';
          script.onerror = () => failSdkLoad('sdk-script-error', new Error('AMap JS API request failed'));
          script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(AMAP_JS_API_KEY)}&callback=${encodeURIComponent(AMAP_JS_API_CALLBACK)}`;
          sdkTimeout = window.setTimeout(
            () => failSdkLoad('sdk-timeout', new Error('AMap JS API load timeout')),
            AMAP_SDK_LOAD_TIMEOUT_MS,
          );
          document.head.appendChild(script);
        } catch (error) {
          failSdkLoad('sdk-script-error', error);
        }
      })
        .then(AMap => new Promise((resolve, reject) => {
          const mapStartedAt = amapDiagnosticNowMs();
          let instance = null;
          let readyTimeout = null;
          let settled = false;
          const cleanup = () => {
            if (readyTimeout !== null) window.clearTimeout(readyTimeout);
            if (instance && typeof instance.off === 'function') {
              try { instance.off('complete', handleComplete); } catch (_cleanupError) {}
            }
          };
          const handleComplete = () => {
            if (settled) return;
            settled = true;
            cleanup();
            amapMapReady = true;
            amapLiveShell.dataset.lifecycle = 'ready';
            clearAmapFailure();
            resolve(AMap);
          };
          const failBeforeReady = (stage, error) => {
            if (settled) return;
            settled = true;
            cleanup();
            amapMapReady = false;
            amapLiveShell.dataset.lifecycle = 'failed';
            recordAmapFailure(stage, error, mapStartedAt);
            reject(error);
          };
          try {
            amapLiveShell.dataset.lifecycle = 'map-loading';
            const mapContainer = document.getElementById('amapLiveMap');
            if (!mapContainer) {
              failBeforeReady('map-constructor', new Error('AMap map container unavailable'));
              return;
            }
            instance = new AMap.Map(mapContainer, {
              zoom: 4,
              center: amapEmptyViewCenter(),
            });
            if (!instance || typeof instance.on !== 'function') {
              failBeforeReady('map-constructor', new Error('AMap map lifecycle unavailable'));
              return;
            }
            amapNamespace = AMap;
            amapInstance = instance;
            instance.on('complete', handleComplete);
            readyTimeout = window.setTimeout(
              () => failBeforeReady('map-ready-timeout', new Error('AMap map ready timeout')),
              AMAP_MAP_READY_TIMEOUT_MS,
            );
          } catch (error) {
            failBeforeReady('map-constructor', error);
          }
        }))
        .catch(error => {
          // Keep the rejected promise sticky for this page lifetime. Repeated
          // explicit render requests must not destroy and recreate a map while
          // the provider still has asynchronous renderer work in flight.
          amapMapReady = false;
          amapLiveShell.dataset.lifecycle = 'failed';
          throw error;
        });
      return amapLoadPromise;
    }
    function convertWgs84Points(AMap, points) {
      const valid = (Array.isArray(points) ? points : []).map(validMapPoint).filter(Boolean);
      if (!valid.length) return Promise.resolve([]);
      if (valid.length > TRAJECTORY_RENDER_POINT_LIMIT + 1) {
        return Promise.reject(new Error('trajectory render point limit exceeded'));
      }
      const cacheKey = JSON.stringify(valid.map(point => [point.seq ?? null, point.server_received_at || '', point.lon, point.lat]));
      if (cacheKey === amapConversionCacheKey && amapConversionCacheValue.length === valid.length) {
        return Promise.resolve(valid.map((point, index) => ({...point, lnglat: amapConversionCacheValue[index]})));
      }
      if (cacheKey === amapConversionInFlightKey && amapConversionInFlightPromise) {
        // The same coordinate set can carry different render roles after a
        // fast checkbox change.  Reuse only the provider result, then remap it
        // onto this caller's current point objects so stale selection flags
        // cannot leak out of an earlier in-flight request.
        return amapConversionInFlightPromise.then(locations => (
          valid.map((point, index) => ({...point, lnglat: locations[index]})).filter(point => point.lnglat)
        ));
      }
      const convertBatch = batch => new Promise((resolve, reject) => {
        AMap.convertFrom(batch.map(point => [point.lon, point.lat]), 'gps', (status, result) => {
          if (status !== 'complete' || !result || result.info !== 'ok' || !Array.isArray(result.locations)) {
            reject(new Error('AMap coordinate conversion failed'));
            return;
          }
          const locations = result.locations.slice(0, batch.length);
          if (locations.length !== batch.length || !locations.every(Boolean)) {
            reject(new Error('AMap coordinate conversion returned an incomplete batch'));
            return;
          }
          resolve(locations);
        });
      });
      const conversionPromise = (async () => {
        const locations = [];
        for (let offset = 0; offset < valid.length; offset += AMAP_CONVERT_BATCH_LIMIT) {
          const batch = valid.slice(offset, offset + AMAP_CONVERT_BATCH_LIMIT);
          locations.push(...await convertBatch(batch));
        }
        amapConversionCacheKey = cacheKey;
        amapConversionCacheValue = locations;
        return locations;
      })();
      amapConversionInFlightKey = cacheKey;
      amapConversionInFlightPromise = conversionPromise;
      const remappedPromise = conversionPromise.then(locations => (
        valid.map((point, index) => ({...point, lnglat: locations[index]})).filter(point => point.lnglat)
      ));
      return remappedPromise.finally(() => {
        if (amapConversionInFlightPromise === conversionPromise) {
          amapConversionInFlightKey = '';
          amapConversionInFlightPromise = null;
        }
      });
    }
    function amapPositionSemantics(map, estimate, readiness = {}) {
      const sourcePoints = Array.isArray(map.points) ? map.points : [];
      const points = sourcePoints
        .filter(point => point && point.amap_eligible === true && point.coordinate_contract === 'wgs84')
        .map(validMapPoint)
        .filter(Boolean);
      const mode = map.mode || 'waiting_for_location_upload';
      const lastPoint = points.length ? points[points.length - 1] : null;
      const predicted = String(estimate.state || '').trim().toLowerCase() === 'predicted';
      const latestFix = map.coordinate_diagnostics && map.coordinate_diagnostics.latest_fix;
      const currentObservationHasNoFix = predicted || latestFix === false;
      const isCurrentFix = lastPoint
        && lastPoint.amap_current === true
        && lastPoint.fix === true
        && !currentObservationHasNoFix;
      if (!lastPoint) {
        const exclusionReasons = new Set(sourcePoints.map(point => point && point.amap_exclusion_reason).filter(Boolean));
        if (latestFix === false || exclusionReasons.has('gnss_fix_not_true')) {
          return {kind: 'no-fix', label: '当前 GNSS 未定位，暂无可信轨迹', points: []};
        }
        if (exclusionReasons.has('firmware_parser_not_allowlisted')) {
          return {kind: 'pre-correction-hidden', label: '旧版坐标已隐藏，等待新的可信 GNSS 定位', points: []};
        }
        if (exclusionReasons.has('location_memory_has_no_coordinate_provenance')) {
          return {kind: 'no-fix', label: '最后位置缺少可信坐标，暂不显示', points: []};
        }
        return {kind: 'no-fix', label: '暂无可信 GNSS 定位', points: []};
      }
      const updatedAt = lastPoint.server_received_at || estimate.updated_at || '';
      const ageMs = Date.parse(updatedAt);
      const ageSeconds = Number.isFinite(ageMs) ? Math.max(0, Math.round((Date.now() - ageMs) / 1000)) : null;
      const age = ageSeconds === null ? '时间未知' : ageSeconds < 60 ? `${ageSeconds} 秒前` : `${Math.round(ageSeconds / 60)} 分钟前`;
      const freshnessThreshold = Number(readiness.freshness_threshold_s ?? 180);
      const stale = isCurrentFix && ageSeconds !== null && Number.isFinite(freshnessThreshold) && ageSeconds > freshnessThreshold;
      if (isCurrentFix && !stale) {
        return {kind: 'current', label: `当前 GNSS 定位 / ${age}`, points, current: lastPoint};
      }
      if (stale) {
        return {kind: 'stale', label: `GNSS 定位已过期 / ${age}`, points, current: lastPoint};
      }
      const lastKnownLabel = currentObservationHasNoFix
        ? `当前为预测状态；地图显示最后可信位置 / ${age}`
        : `最后可信位置 / ${age}`;
      return {kind: 'last-known', label: lastKnownLabel, points, current: lastPoint};
    }
    function trajectoryPointKey(point) {
      return JSON.stringify([
        point && point.server_received_at || '',
        point && point.seq !== undefined ? point.seq : null,
        point && point.raw_frame_id || '',
      ]);
    }
    function trajectoryEvidenceKey(point) {
      return JSON.stringify([
        point && point.server_received_at || '',
        point && point.seq !== undefined ? point.seq : null,
        point && point.event_type || '',
        point && point.lat !== undefined ? point.lat : null,
        point && point.lon !== undefined ? point.lon : null,
      ]);
    }
    function mergeTrajectoryEvidencePoints(...pointGroups) {
      const mergedByEvidence = new Map();
      pointGroups.flat().filter(Boolean).forEach(point => {
        const evidenceKey = trajectoryEvidenceKey(point);
        if (!mergedByEvidence.has(evidenceKey)) mergedByEvidence.set(evidenceKey, point);
      });
      return [...mergedByEvidence.values()];
    }
    function boundedTrajectorySelection(quickSelectedPoints, historySelectedRecords) {
      const uniqueHistoryPoints = mergeTrajectoryEvidencePoints(historySelectedRecords);
      const historyPoints = uniqueHistoryPoints.slice(0, TRAJECTORY_RENDER_POINT_LIMIT);
      const historyEvidenceKeys = new Set(historyPoints.map(trajectoryEvidenceKey));
      const uniqueQuickCandidates = mergeTrajectoryEvidencePoints(quickSelectedPoints)
        .filter(point => !historyEvidenceKeys.has(trajectoryEvidenceKey(point)));
      const quickCapacity = Math.max(0, TRAJECTORY_RENDER_POINT_LIMIT - historyPoints.length);
      const quickPoints = quickCapacity > 0
        ? uniqueQuickCandidates.slice(-quickCapacity)
        : [];
      return {
        selectedPoints: chronologicalTrajectoryPoints(
          mergeTrajectoryEvidencePoints(historyPoints, quickPoints),
          false,
        ),
        quickSelectedPoints: quickPoints,
        quickSuppressedCount: Math.max(0, uniqueQuickCandidates.length - quickPoints.length),
        historySuppressedCount: Math.max(0, uniqueHistoryPoints.length - historyPoints.length),
      };
    }
    function chronologicalTrajectoryPoints(points, assignSourceIndex = true) {
      return (Array.isArray(points) ? points : [])
        .map((point, sourceOrder) => ({...point, trajectory_source_order: sourceOrder}))
        .sort((left, right) => {
          const leftTime = Date.parse(left.server_received_at || '');
          const rightTime = Date.parse(right.server_received_at || '');
          if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
            return leftTime - rightTime;
          }
          if (Number.isFinite(leftTime) !== Number.isFinite(rightTime)) {
            return Number.isFinite(leftTime) ? -1 : 1;
          }
          const leftRecordOrder = Number(String(left.history_record_id || '').replace(/^location-/, ''));
          const rightRecordOrder = Number(String(right.history_record_id || '').replace(/^location-/, ''));
          if (
            Number.isFinite(leftRecordOrder)
            && Number.isFinite(rightRecordOrder)
            && leftRecordOrder !== rightRecordOrder
          ) {
            return leftRecordOrder - rightRecordOrder;
          }
          const leftSeq = Number(left.seq);
          const rightSeq = Number(right.seq);
          if (Number.isFinite(leftSeq) && Number.isFinite(rightSeq) && leftSeq !== rightSeq) {
            return leftSeq - rightSeq;
          }
          const stableComparison = trajectoryEvidenceKey(left).localeCompare(trajectoryEvidenceKey(right));
          if (stableComparison) return stableComparison;
          return left.trajectory_source_order - right.trajectory_source_order;
        })
        .map((point, trajectorySourceIndex) => {
          const normalized = {
            ...point,
            trajectory_point_key: trajectoryPointKey(point),
          };
          delete normalized.trajectory_source_order;
          if (assignSourceIndex && !Number.isFinite(Number(point.trajectory_source_index))) {
            normalized.trajectory_source_index = trajectorySourceIndex;
          }
          return normalized;
        });
    }
    function trajectorySelectionForPoints(deviceId, points) {
      const allPoints = chronologicalTrajectoryPoints(points);
      const availableKeys = new Set(allPoints.map(point => point.trajectory_point_key));
      let selection = trajectorySelectionByDevice.get(deviceId);
      if (!selection) {
        selection = {mode: 'follow', selectedKeys: new Set(availableKeys)};
      } else if (selection.mode === 'follow') {
        selection.selectedKeys = new Set(availableKeys);
      } else {
        selection.selectedKeys = new Set(
          [...selection.selectedKeys].filter(key => availableKeys.has(key)),
        );
      }
      trajectorySelectionByDevice.set(deviceId, selection);
      return {
        allPoints,
        selectedPoints: allPoints.filter(point => selection.selectedKeys.has(point.trajectory_point_key)),
        selection,
      };
    }
    function trajectorySelectionContext(selectedDevice) {
      if (!selectedDevice) {
        return {
          semantics: {kind: 'no-fix', label: '暂无设备数据', points: []},
          allPoints: [],
          selectedPoints: [],
          selection: {mode: 'follow', selectedKeys: new Set()},
        };
      }
      const d1 = selectedDevice.d1_link || {};
      const map = mapWithLocalReferences(d1.map_surface || {}, selectedDevice.device_id);
      const baseSemantics = amapPositionSemantics(map, d1.location_estimate || {}, d1.field_readiness || {});
      const {allPoints, selectedPoints: quickSelectedPoints, selection} = trajectorySelectionForPoints(
        selectedDevice.device_id,
        baseSemantics.points,
      );
      const historySelectedRecords = locationHistorySelectedPoints(selectedDevice.device_id);
      const boundedSelection = boundedTrajectorySelection(
        quickSelectedPoints,
        historySelectedRecords,
      );
      const selectedPoints = boundedSelection.selectedPoints;
      return {
        semantics: {...baseSemantics, points: selectedPoints},
        baseSemantics,
        allPoints,
        selectedPoints,
        quickSelectedPoints: boundedSelection.quickSelectedPoints,
        requestedQuickSelectedPoints: quickSelectedPoints,
        quickSuppressedCount: boundedSelection.quickSuppressedCount,
        historySuppressedCount: boundedSelection.historySuppressedCount,
        historySelectedRecordCount: historySelectedRecords.length,
        selection,
      };
    }
    function trajectorySegments(points, maxGapMs = 10 * 60 * 1000) {
      const source = Array.isArray(points) ? points : [];
      if (!source.length) return [];
      const segments = [[source[0]]];
      for (let index = 1; index < source.length; index += 1) {
        const previous = source[index - 1];
        const current = source[index];
        const previousTime = Date.parse(previous.server_received_at || '');
        const currentTime = Date.parse(current.server_received_at || '');
        const invalidOrReversedTime = !Number.isFinite(previousTime)
          || !Number.isFinite(currentTime)
          || currentTime <= previousTime;
        const hasLongGap = !invalidOrReversedTime && currentTime - previousTime > maxGapMs;
        const previousSourceIndex = Number(previous.trajectory_source_index);
        const currentSourceIndex = Number(current.trajectory_source_index);
        const skippedSample = Number.isFinite(previousSourceIndex)
          && Number.isFinite(currentSourceIndex)
          && currentSourceIndex !== previousSourceIndex + 1;
        if (invalidOrReversedTime || hasLongGap || skippedSample) segments.push([]);
        segments[segments.length - 1].push(current);
      }
      return segments;
    }
    function recentTrajectoryPanel(selectedDevice) {
      return '';
    }
    function updateTrajectoryMaps(selectedDevice) {
      if (!selectedDevice) return;
      const d1 = selectedDevice.d1_link || {};
      const map = mapWithLocalReferences(d1.map_surface || {}, selectedDevice.device_id);
      const localMap = document.getElementById('localMapSurface');
      if (localMap) {
        localMap.outerHTML = d1MapSurface(
          map,
          d1.location_estimate || {},
          d1.field_readiness || {},
          selectedDevice.device_id,
        );
        if (amapLiveMap.style.display === 'block') setLocalMapVisibility(false);
      }
      renderAmapForSelectedDevice(selectedDevice);
    }
    function rerenderTrajectorySelection(selectedDevice, focusKey) {
      if (!selectedDevice) return;
      updateTrajectoryMaps(selectedDevice);
    }
    function bindTrajectoryPanelEvents(selectedDevice) {
      // trajectory panel removed
    }
    function amapOverlayKey(deviceId, semantics) {
      const points = Array.isArray(semantics.points) ? semantics.points : [];
      return JSON.stringify({
        device_id: deviceId || '',
        kind: semantics.kind,
        points: points.map(point => [point.seq ?? null, point.server_received_at || '', point.lon, point.lat]),
        position: semantics.positionPoint
          ? [semantics.positionPoint.seq ?? null, semantics.positionPoint.server_received_at || '', semantics.positionPoint.lon, semantics.positionPoint.lat]
          : null,
      });
    }
    function showAmapEmptyState(semantics) {
      amapInstance.clearMap();
      amapOverlays = [];
      if (typeof amapInstance.setZoomAndCenter === 'function') {
        amapInstance.setZoomAndCenter(4, amapEmptyViewCenter());
      }
      amapLiveMap.dataset.state = 'ready-empty';
      amapLiveMap.style.display = 'block';
      amapLiveMap.style.visibility = 'visible';
      setLocalMapVisibility(false);
      setAmapStatus(`${semantics.label} / 高德底图已加载 / 暂无定位标记`, 'warn');
    }
    async function renderAmapForSelectedDevice(selectedDevice) {
      const generation = ++amapRenderGeneration;
      const overlayStartedAt = amapDiagnosticNowMs();
      const d1 = selectedDevice && selectedDevice.d1_link ? selectedDevice.d1_link : {};
      const estimate = d1.location_estimate || {};
      const readiness = d1.field_readiness || {};
      const map = mapWithLocalReferences(d1.map_surface || {}, selectedDevice ? selectedDevice.device_id : '');
      const baseSemantics = amapPositionSemantics(map, estimate, readiness);
      const selectionView = trajectorySelectionContext(selectedDevice);
      const positionPoint = baseSemantics.current
        ? {...baseSemantics.current, trajectory_point_key: trajectoryPointKey(baseSemantics.current)}
        : null;
      const semantics = {
        ...baseSemantics,
        label: selectionView.selectedPoints.length && (
          baseSemantics.kind === 'no-fix'
          || baseSemantics.kind === 'pre-correction-hidden'
        )
          ? `当前无可信实时定位；正在显示 ${selectionView.selectedPoints.length} 个已选历史可信点`
          : selectionView.selectedPoints.length
            ? baseSemantics.label
            : `${baseSemantics.label} / 未选择轨迹点`,
        points: selectionView.selectedPoints,
        positionPoint,
      };
      if (!selectedDevice) {
        if (amapInstance && amapOverlayCacheKey) amapInstance.clearMap();
        amapOverlayCacheKey = '';
        amapLiveMap.dataset.state = 'waiting';
        amapLiveMap.style.display = 'none';
        setLocalMapVisibility(true);
        setAmapStatus(semantics.label, 'warn');
        return;
      }
      if (!AMAP_JS_API_KEY) {
        amapLiveMap.dataset.state = 'not-configured';
        amapLiveMap.style.display = 'none';
        setLocalMapVisibility(true);
        setAmapStatus(`${semantics.label} / 使用本地轨迹示意图`, 'warn');
        return;
      }
      const hasSelectedTrustedPoint = semantics.points.length > 0;
      const hasTrustedPositionPoint = Boolean(semantics.positionPoint)
        && semantics.kind !== 'no-fix'
        && semantics.kind !== 'pre-correction-hidden';
      const hasTrustedPoint = hasSelectedTrustedPoint || hasTrustedPositionPoint;
      const overlayKey = amapOverlayKey(selectedDevice.device_id, semantics);
      if (amapInstance && overlayKey === amapOverlayCacheKey) {
        amapLiveMap.dataset.state = hasTrustedPoint ? 'ready' : 'ready-empty';
        amapLiveMap.style.display = 'block';
        amapLiveMap.style.visibility = 'visible';
        setLocalMapVisibility(false);
        setAmapStatus(
          hasTrustedPoint
            ? `${semantics.label} / 已选 ${semantics.points.length} 个轨迹点`
            : `${semantics.label} / 高德底图已加载 / 暂无定位标记`,
          hasTrustedPoint ? 'ok' : 'warn',
        );
        return;
      }
      if (overlayKey === amapOverlayFailureKey) {
        amapLiveMap.dataset.state = 'failed';
        amapLiveMap.style.display = 'none';
        setLocalMapVisibility(true);
        const failureStage = amapFailureStage(amapLiveShell.dataset.failureStage);
        setAmapStatus(`${semantics.label} / 高德地图 ${failureStage} / 数据未变化，已暂停重复重试`, 'warn');
        return;
      }
      try {
        setAmapStatus(
          hasTrustedPoint ? '正在加载高德地图并转换可信轨迹…' : `${semantics.label} / 正在加载高德底图`,
          'warn',
        );
        amapLiveMap.style.display = 'block';
        amapLiveMap.style.visibility = 'visible';
        const AMap = await loadAmap();
        if (generation !== amapRenderGeneration) return;
        setLocalMapVisibility(false);
        if (!hasTrustedPoint) {
          showAmapEmptyState(semantics);
          amapOverlayCacheKey = overlayKey;
          amapOverlayFailureKey = '';
          return;
        }
        const positionKey = semantics.positionPoint ? semantics.positionPoint.trajectory_point_key : '';
        const conversionPoints = semantics.points.map(point => ({
          ...point,
          trajectory_selected: true,
          trajectory_position: point.trajectory_point_key === positionKey,
        }));
        if (semantics.positionPoint && !conversionPoints.some(point => point.trajectory_position)) {
          conversionPoints.push({
            ...semantics.positionPoint,
            trajectory_selected: false,
            trajectory_position: true,
          });
        }
        const converted = await convertWgs84Points(AMap, conversionPoints);
        if (generation !== amapRenderGeneration) return;
        if (!converted.length) throw new Error('no valid converted coordinates');
        const convertedSelected = converted.filter(point => point.trajectory_selected === true);
        const convertedPosition = converted.find(point => point.trajectory_position === true) || null;
        amapInstance.clearMap();
        amapOverlays = [];
        const segments = trajectorySegments(convertedSelected);
        for (const segment of segments) {
          const path = segment.map(point => point.lnglat);
          if (path.length >= 2) {
            amapOverlays.push(new AMap.Polyline({
              path,
              strokeColor: '#155eef',
              strokeWeight: 7,
              strokeOpacity: 0.9,
              outlineColor: '#ffffff',
              borderWeight: 2,
              lineJoin: 'round',
              lineCap: 'round',
            }));
          }
        }
        if (convertedSelected.length >= 2) {
          const first = convertedSelected[0];
          const startTitle = `所选起点 / ${formatDashboardDateTime(first.server_received_at)} / seq ${first.seq ?? '未知'}`;
          amapOverlays.push(new AMap.Marker({
            position: first.lnglat,
            title: startTitle,
            content: `<div class="amap-start-marker" aria-label="${escapeHtml(startTitle)}">起</div>`,
            anchor: 'center',
            zIndex: 120,
          }));
          for (const point of convertedSelected.slice(1, -1)) {
            const historyTitle = `所选历史点 / ${formatDashboardDateTime(point.server_received_at)} / seq ${point.seq ?? '未知'}`;
            amapOverlays.push(new AMap.Marker({
              position: point.lnglat,
              title: historyTitle,
              content: `<div class="amap-history-marker" aria-label="${escapeHtml(historyTitle)}"></div>`,
              anchor: 'center',
              zIndex: 100,
            }));
          }
        }
        const positionLabel = semantics.kind === 'current'
          ? '当前定位'
          : semantics.kind === 'stale'
            ? '历史位置（已过期）'
            : '最后可信位置';
        if (convertedSelected.length) {
          const latest = convertedSelected[convertedSelected.length - 1];
          const overlapsPosition = convertedPosition
            && latest.trajectory_point_key === convertedPosition.trajectory_point_key;
          const markerLabel = overlapsPosition ? `所选终点 · ${positionLabel}` : '所选终点';
          const markerTitle = `${markerLabel} / ${formatDashboardDateTime(latest.server_received_at)} / seq ${latest.seq ?? '未知'}`;
          amapOverlays.push(new AMap.Marker({
            position: latest.lnglat,
            title: markerTitle,
            content: `<div class="amap-end-marker"><div class="amap-memory-marker" aria-label="${escapeHtml(markerTitle)}"></div><span class="amap-marker-label">${escapeHtml(markerLabel)}</span></div>`,
            anchor: 'center',
            zIndex: 140,
          }));
        }
        if (convertedPosition && !convertedPosition.trajectory_selected) {
          const positionMarkerClass = semantics.kind === 'current'
            ? 'amap-current-marker'
            : semantics.kind === 'stale'
              ? 'amap-stale-marker'
              : 'amap-memory-marker';
          const positionTitle = `${positionLabel} / ${formatDashboardDateTime(convertedPosition.server_received_at)} / seq ${convertedPosition.seq ?? '未知'}`;
          amapOverlays.push(new AMap.Marker({
            position: convertedPosition.lnglat,
            title: positionTitle,
            content: `<div class="amap-end-marker"><div class="${positionMarkerClass}" aria-label="${escapeHtml(positionTitle)}"></div><span class="amap-marker-label">${escapeHtml(positionLabel)}</span></div>`,
            anchor: 'center',
            zIndex: 160,
          }));
        }
        amapInstance.add(amapOverlays);
        amapInstance.setFitView(amapOverlays, false, [44, 44, 44, 44], 16);
        amapOverlayCacheKey = overlayKey;
        amapOverlayFailureKey = '';
        clearAmapFailure();
        amapLiveMap.dataset.state = 'ready';
        amapLiveMap.style.display = 'block';
        amapLiveMap.style.visibility = 'visible';
        setLocalMapVisibility(false);
        setAmapStatus(`${semantics.label} / 已选轨迹 ${convertedSelected.length} 点 / WGS-84 已转换为 GCJ-02`, 'ok');
      } catch (error) {
        if (generation !== amapRenderGeneration) return;
        if (!amapLiveShell.dataset.failureStage || amapLiveShell.dataset.failureStage === 'none') {
          recordAmapFailure('overlay', error, overlayStartedAt);
        }
        amapOverlayCacheKey = '';
        amapOverlayFailureKey = overlayKey;
        amapLiveMap.dataset.state = 'failed';
        amapLiveMap.style.display = 'none';
        setLocalMapVisibility(true);
        const failureStage = amapFailureStage(amapLiveShell.dataset.failureStage);
        const failureReason = amapFailureReasonCode(amapLiveShell.dataset.failureReason);
        setAmapStatus(
          `${semantics.label} / 高德地图 ${failureStage} / ${failureReason} / 已切换本地示意图`,
          'warn',
        );
      }
    }
    function d1LinkPanel(selectedDevice) {
      if (!selectedDevice) return '<div class="empty-panel">暂无设备数据，请先保存访问令牌并等待设备上线。</div>';
      const d = selectedDevice;
      const d1 = d.d1_link || {};
      const readiness = d1.field_readiness || {};
      const acceptance = d1.acceptance_gate || {};
      const estimate = d1.location_estimate || {};
      const map = mapWithLocalReferences(d1.map_surface || {}, d.device_id);
      const coord = map.coordinate_diagnostics || acceptance.coordinate_diagnostics || {};
      const provider = map.provider || {};
      const privacy = map.privacy || {};
      const freshness = d1.upload_freshness || {};
      const uplink = d1.uplink_metrics || {};
      const powerCurve = d1.power_curve || {};
      const evidence = d1.evidence || {};
      const components = evidence.components || {};
      const gnss = components.gnss || {};
      const cellLte = components.cell_lte || {};
      const imu = components.imu || {};
      const power = components.power || {};
      const status = d1.status || 'unknown';
      const mapMode = map.mode || 'waiting_for_location_upload';
      const reviewMode = map.review_mode || 'local_no_key';
      const trajectory = map.trajectory || {};
      const referencePoints = Array.isArray(map.reference_points) ? map.reference_points : [];
      const trustedPoints = (Array.isArray(map.points) ? map.points : [])
        .filter(point => point && point.amap_eligible === true && point.coordinate_contract === 'wgs84');
      const latestTrustedPoint = trustedPoints.length ? trustedPoints[trustedPoints.length - 1] : null;
      const fieldCoordinateText = latestTrustedPoint
        ? coordinateLabel(latestTrustedPoint.lat, latestTrustedPoint.lon)
        : '旧版坐标已隐藏，等待新的可信 GNSS 定位';
      const locationText = `${displayState(estimate.state)} / 置信度 ${valueOrUnknown(estimate.confidence)} / 范围 ${valueOrUnknown(estimate.radius_m)} m`;
      const uploadText = `${valueOrUnknown(uplink.raw_post_success_count)} ok / ${valueOrUnknown(uplink.raw_post_failure_count)} fail / ${valueOrUnknown(uplink.raw_post_attempt_count)} attempts / rate ${valueOrUnknown(uplink.raw_post_success_rate)}`;
      const powerText = `${valueOrUnknown(powerCurve.sample_count, 0)} samples / ${valueOrUnknown(powerCurve.window_s)} s`;
      const powerDeltaText = `${valueOrUnknown(powerCurve.delta_battery_mv)} mV / ${valueOrUnknown(powerCurve.delta_soc_pct)}%`;
      const readinessGateText = `ready <= ${valueOrUnknown(readiness.freshness_threshold_s, 180)}s / stale <= ${valueOrUnknown(readiness.stale_threshold_s, 600)}s`;
      return `
        <div id="d1FieldOverview" class="d1-overview">
          <div class="d1-map-pane">
            ${d1MapSurface(map, estimate, readiness, d.device_id)}
          </div>
          <div class="d1-summary-pane">
            <div id="d1StatusStrip" class="d1-status-strip">
              <span id="d1FieldReadyBadge" class="status-chip ${readinessClass(readiness)}">外场状态 ${escapeHtml(displayState(readiness.state || 'waiting_for_data'))}</span>
              <span id="d1AcceptanceBadge" class="status-chip ${acceptanceClass(acceptance)}">D1 门禁 ${escapeHtml(displayState(acceptance.status || 'checking'))}</span>
              <span class="status-chip ${d1StatusClass(status)}">定位链路 ${escapeHtml(displayState(status))}</span>
              <span id="d1FreshnessBadge" class="status-chip ${freshnessClass(freshness)}">数据新鲜度 ${escapeHtml(freshnessLabel(freshness))}</span>
              <span class="status-chip">传输 ${escapeHtml(valueOrUnknown(evidence.transport_type))}</span>
              <span class="status-chip">地图模式 ${escapeHtml(reviewMode)}</span>
              <span class="status-chip">地图服务 ${escapeHtml(valueOrUnknown(provider.status, 'not_configured'))}</span>
              <span class="status-chip">D2 参考点 ${escapeHtml(referencePoints.length)}</span>
            </div>
            <div class="d1-primary-row">
              <div class="d1-primary">
                <span class="card-label">定位轨迹门禁</span>
                <strong>${escapeHtml(acceptanceHeadline(acceptance))}</strong>
                <span class="card-note">可信轨迹点：${escapeHtml(acceptance.track_points ?? 0)} / 最少 ${escapeHtml(acceptance.required_track_points ?? 2)}</span>
                <span class="card-note">定位上报：${escapeHtml(coord.coordinate_event_count ?? 0)} / ${escapeHtml(coord.location_event_count ?? 0)}，缺坐标 ${escapeHtml(coord.missing_coordinate_event_count ?? 0)}</span>
              </div>
              <div class="d1-primary">
                <span class="card-label">设备可用状态</span>
                <strong>${escapeHtml(readinessHeadline(readiness))}</strong>
                <span class="card-note">原因：${escapeHtml(valueOrUnknown(readiness.reason))}</span>
                <span class="card-note">新鲜度门限：${escapeHtml(readinessGateText)}</span>
              </div>
              <div class="d1-primary">
                <span class="card-label">位置判断</span>
                <strong>${escapeHtml(locationText)}</strong>
                <span class="card-note">来源：${escapeHtml(arrayLabel(estimate.source))}</span>
                <span class="card-note">原因：${escapeHtml(valueOrUnknown(estimate.reason))}</span>
              </div>
            </div>
            <details class="d1-details">
              <summary>查看定位证据详情</summary>
              <div class="d1-grid">
              <div class="d1-card">
                <span class="card-label">上行链路</span>
                <span class="card-value">上传结果：${escapeHtml(uploadText)}</span>
                <span class="card-note">定位上报：${escapeHtml(uplink.location_event_count ?? 0)} 条 / ${escapeHtml(uplink.basis || 'unknown')}</span>
                <span class="card-note">最后定位上报：${escapeHtml(freshness.last_location_upload_at || 'none')} / seq ${escapeHtml(freshness.last_seq ?? 'unknown')}</span>
              </div>
              <div class="d1-card">
                <span class="card-label">功耗</span>
                <span class="card-value">功耗曲线：${escapeHtml(powerText)}</span>
                <span class="card-note">功耗变化：${escapeHtml(powerDeltaText)}</span>
                <span class="card-note">续航声明：${escapeHtml(powerCurve.battery_life_claim || 'none')}</span>
              </div>
              <div class="d1-card">
                <span class="card-label">传感证据</span>
                <div class="evidence-list">
                  <div class="evidence-pill"><span>GNSS</span><span>${escapeHtml(boolSeen(gnss.seen))} / fix ${escapeHtml(valueOrUnknown(gnss.fix))} / ${escapeHtml(valueOrUnknown(gnss.state))}</span></div>
                  <div class="evidence-pill"><span>蜂窝 / LTE</span><span>${escapeHtml(boolSeen(cellLte.seen))} / ${escapeHtml(valueOrUnknown(cellLte.rat))} / ${escapeHtml(valueOrUnknown(cellLte.registration_state))}</span></div>
                  <div class="evidence-pill"><span>IMU</span><span>${escapeHtml(boolSeen(imu.seen))} / ${escapeHtml(valueOrUnknown(imu.motion))} / ${escapeHtml(valueOrUnknown(imu.evidence_status))}</span></div>
                  <div class="evidence-pill"><span>电源</span><span>${escapeHtml(boolSeen(power.seen))} / ${escapeHtml(valueOrUnknown(power.battery_mv))} mV / ${escapeHtml(valueOrUnknown(power.soc_pct))}%</span></div>
                </div>
              </div>
              <div class="d1-card">
                <span class="card-label">定位说明</span>
                <span class="card-value">${escapeHtml(fieldCoordinateText)}</span>
                <span class="card-note">地图模式：${escapeHtml(mapMode)} / ${escapeHtml(reviewMode)}</span>
                <span class="card-note">地图服务：${escapeHtml(valueOrUnknown(provider.status, 'not_configured'))}；D1 阻塞 ${escapeHtml(provider.blocking_d1 ?? false)}</span>
                <span class="card-note">可信地图点：${escapeHtml(map.amap_eligible_point_count ?? 0)} / 证据轨迹点 ${escapeHtml(trajectory.point_count ?? 0)}</span>
                <span class="card-note">最近缺测原因：${escapeHtml(valueOrUnknown(coord.latest_missing_reason))}</span>
                <span class="card-note">门禁阻塞：${escapeHtml(arrayLabel(acceptance.blockers))}；警告：${escapeHtml(arrayLabel(acceptance.warnings))}</span>
                <span class="card-note">操作建议：${escapeHtml(valueOrUnknown(readiness.operator_action))} / ${escapeHtml(acceptance.next_action || 'review_d1_gate')}</span>
                <span class="card-note">原始门禁信息：${escapeHtml(valueOrUnknown(acceptance.headline))}</span>
                <span class="card-note">精度声明：${escapeHtml(estimate.accuracy_claim || 'none')}；采集提示：${escapeHtml(valueOrUnknown(coord.operator_hint))}</span>
                <span class="card-note">D2 参考点：${escapeHtml(referencePoints.length)}</span>
                <span class="card-note">隐私边界：${escapeHtml(privacy.static_report_policy || 'bounded_summary_no_raw_coordinates')}</span>
                <span class="card-note">本面板不作定位精度或电池续航声明。</span>
              </div>
              </div>
            </details>
          </div>
        </div>
      `;
    }
    function latestFieldState(selectedDevice, rawFrames) {
      if (!selectedDevice) return '<span class="empty">暂无设备数据</span>';
      const d = selectedDevice;
      const latestRaw = latestRawFrameForDevice(rawFrames, d.device_id);
      const latestRawParsed = parseResult(latestRaw);
      const latestRawFraming = framing(latestRaw);
      const obs = d.observability || {};
      const obsTransport = obs.transport || {};
      const obsRuntime = obs.runtime || {};
      const obsCommand = obs.command || {};
      const obsPower = obs.power || {};
      const obsGnss = obs.gnss || {};
      const obsCell = obs.cell || {};
      const obsLte = obs.lte || {};
      const obsWifi = obs.wifi || {};
      const obsImu = obs.imu || {};
      const obsReliability = obs.reliability || {};
      const obsRelNetwork = obsReliability.network || {};
      const obsRelCache = obsReliability.cache || {};
      const obsBelief = obs.location_belief || {};
      const obsMemory = obs.location_memory || {};
      const obsExplainability = obs.explainability || {};
      const location = d.latest_location || {};
      const telemetry = d.latest_telemetry || {};
      const fieldTelemetry = ['location_report', 'location_observation'].includes(location.event_type) ? location : telemetry;
      const status = d.last_status || {};
      const error = d.last_error || {};
      const lat = gnssField(fieldTelemetry, 'lat');
      const lon = gnssField(fieldTelemetry, 'lon');
      return `
        <div class="metric"><span>当前设备</span><b>${escapeHtml(d.device_id)}</b></div>
        <div class="metric"><span>在线状态</span><span class="${ageClass(d.last_seen_at)}">${escapeHtml(onlineDisplayLabel(d.last_seen_at))}</span></div>
        <div class="metric"><span>最后通信</span><span>${escapeHtml(formatDashboardDateTime(d.last_seen_at))}</span></div>
        <div class="metric"><span>定位上报时间</span><span>${escapeHtml(formatDashboardDateTime(fieldTelemetry.server_received_at))}</span></div>
        <div class="metric"><span>最新消息类型</span><span>${escapeHtml(fieldTelemetry.event_type || fieldTelemetry.message_type || 'unknown')}</span></div>
        <div class="metric"><span>位置判断</span><span>${escapeHtml(displayState(obsBelief.state || 'unknown'))}</span></div>
        <div class="metric"><span>GNSS 状态</span><span>${escapeHtml(displayState(gnssField(fieldTelemetry, 'gnss_state', fieldTelemetry.event_type || status.gnss_state || 'unknown')))}</span></div>
        <div class="metric"><span>本次定位</span><span>${escapeHtml(gnssField(fieldTelemetry, 'fix'))}</span></div>
        <div class="metric"><span>坐标</span><span>${escapeHtml(lat)}, ${escapeHtml(lon)}</span></div>
        <div class="metric"><span>传输链路</span><span>${escapeHtml(obsTransport.type || status.link_type || 'unknown')}</span></div>
        <div class="metric"><span>最近指令</span><span>${escapeHtml(obsCommand.last_cmd_id || 'none')} / ${escapeHtml(obsCommand.last_ack_status || obsCommand.last_status || 'none')}</span></div>
        <div class="metric"><span>电源</span><span>${escapeHtml(obsPower.battery_mv ?? 'unknown')} mV / ${escapeHtml(obsPower.soc_pct ?? status.battery ?? 'unknown')}% / ${escapeHtml(obsPower.evidence_status || obsPower.source_status || obsPower.source || 'unknown')}</span></div>
        <div class="metric"><span>LTE</span><span>${escapeHtml(obsLte.registration_state || obsCell.registration_state || 'unknown')} / PDP ${escapeHtml(obsLte.pdp_state || obsCell.pdp_state || 'unknown')} / SIM ${escapeHtml(obsLte.sim_state || obsCell.sim_state || 'unknown')}</span></div>
        <div class="metric"><span>IMU</span><span>${escapeHtml(obsImu.motion || 'unknown')} ${escapeHtml(obsImu.confidence ?? '')} / ${escapeHtml(obsImu.evidence_status || obsImu.source_status || 'unknown')}</span></div>
        <div class="metric"><span>最近错误</span><span>${escapeHtml(error.error_code || 'none')}</span></div>
        <details>
          <summary>展开工程诊断</summary>
          <div class="metric"><span>Belief</span><span>${escapeHtml(obsBelief.confidence ?? 'unknown')} / ${escapeHtml(obsBelief.radius_m ?? 'unknown')} m</span></div>
          <div class="metric"><span>Belief Source</span><span>${escapeHtml((obsBelief.source || []).join(', ') || 'none')}</span></div>
          <div class="metric"><span>Belief Reason</span><span>${escapeHtml(obsBelief.reason || 'unknown')}</span></div>
          <div class="metric"><span>Memory State</span><span>${escapeHtml(obsMemory.state || 'unknown')}</span></div>
          <div class="metric"><span>Memory Updated</span><span>${escapeHtml(obsMemory.belief_updated_at || obsMemory.updated_at || 'none')}</span></div>
          <div class="metric"><span>Memory Reason</span><span>${escapeHtml(obsMemory.reason || 'unknown')}</span></div>
          <div class="metric"><span>Satellites</span><span>${escapeHtml(gnssField(fieldTelemetry, 'satellites'))}</span></div>
          <div class="metric"><span>HDOP</span><span>${escapeHtml(gnssField(fieldTelemetry, 'hdop'))}</span></div>
          <div class="metric"><span>Source Status</span><span>${escapeHtml(gnssField(fieldTelemetry, 'source_status'))}</span></div>
          <div class="metric"><span>Transport Error</span><span>${escapeHtml(obsTransport.last_error || 'none')}</span></div>
          <div class="metric"><span>Network Reconnect</span><span>${escapeHtml(obsRelNetwork.reconnect_count ?? 'unknown')} / ${escapeHtml(obsRelNetwork.last_reconnect_reason || obsRelNetwork.state || 'unknown')}</span></div>
          <div class="metric"><span>Network Error</span><span>${escapeHtml(obsRelNetwork.last_error || 'none')}</span></div>
          <div class="metric"><span>Raw POST</span><span>${escapeHtml(obsRelNetwork.raw_post_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelNetwork.raw_post_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelNetwork.raw_post_attempt_count ?? 'unknown')} attempts</span></div>
          <div class="metric"><span>Cache Queue</span><span>${escapeHtml(obsRelCache.queued_message_count ?? 'unknown')} queued / ${escapeHtml(obsRelCache.oldest_message_age_ms ?? 'unknown')} ms oldest</span></div>
          <div class="metric"><span>Cache Retry</span><span>${escapeHtml(obsRelCache.retry_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelCache.retry_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelCache.retry_attempt_count ?? 'unknown')} attempts / ${escapeHtml(obsRelCache.retry_policy || 'none')}</span></div>
          <div class="metric"><span>Cache Flush</span><span>${escapeHtml(obsRelCache.flush_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelCache.flush_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelCache.flush_attempt_count ?? 'unknown')} attempts</span></div>
          <div class="metric"><span>Cache Drops</span><span>${escapeHtml(obsRelCache.dropped_message_count ?? 'unknown')} / ${escapeHtml(obsRelCache.last_drop_reason || 'none')}</span></div>
          <div class="metric"><span>Runtime Reset</span><span>${escapeHtml(obsRuntime.last_reset_reason || 'unknown')}</span></div>
          <div class="metric"><span>Boot</span><span>${escapeHtml(obsRuntime.boot_id || 'unknown')}</span></div>
          <div class="metric"><span>Raw Frame</span><span class="${rawFrameClass(latestRaw)}">${escapeHtml(rawFrameSummary(latestRaw))}</span></div>
          <div class="metric"><span>Raw Frame ID</span><span>${escapeHtml(latestRaw.frame_id || 'none')}</span></div>
          <div class="metric"><span>Raw Derived</span><span>${escapeHtml(latestRawParsed.derived_message_type || 'unknown')} / ${escapeHtml(latestRawFraming.content_type || 'unknown')}</span></div>
          <div class="metric"><span>Cell</span><span>${escapeHtml(obsCell.rat || 'unknown')} ${escapeHtml(obsCell.cell_id || '')} RSRP ${escapeHtml(obsCell.rsrp ?? 'unknown')}</span></div>
          <div class="metric"><span>LTE Reason</span><span>${escapeHtml(obsLte.reason_code || obsCell.reason_code || 'unknown')}</span></div>
          <div class="metric"><span>Wi-Fi</span><span>${escapeHtml(obsWifi.scan_enabled ?? 'unknown')} / APs ${escapeHtml(obsWifi.ap_count ?? 'unknown')} / ${escapeHtml(obsWifi.evidence_status || obsWifi.source_status || 'unknown')}</span></div>
          <div class="metric"><span>GNSS Reason</span><span>${escapeHtml(obsGnss.reason_code || 'unknown')}</span></div>
          <div class="metric"><span>Reason Codes</span><span>${escapeHtml((obsExplainability.reason_codes || []).join(', ') || 'none')}</span></div>
        </details>
      `;
    }
    function progressBoardPanel(board) {
      if (!board || board.status !== 'available') {
        return `<div class="empty-panel">项目进度暂不可用：${escapeHtml(board && board.reason || 'not deployed')}</div>`;
      }
      const milestones = (board.milestones || []).map(item => {
        const done = Number(item.done || 0);
        const total = Number(item.total || 0);
        const percent = total > 0 ? Math.max(0, Math.min(100, (done / total) * 100)) : 0;
        return `
          <div class="progress-milestone">
            <span class="progress-milestone-name">${escapeHtml(item.id)} ${escapeHtml(item.title)}</span>
            <span class="progress-milestone-count">${escapeHtml(done)} / ${escapeHtml(total)}</span>
            <div class="progress-track"><div class="progress-fill" style="width:${percent.toFixed(1)}%"></div></div>
          </div>`;
      }).join('') || '<span class="empty">暂无里程碑</span>';
      const asks = (board.operator_asks || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
      return `
        <div class="progress-layout">
          <div>
            <span class="card-label">当前重点</span>
            <div class="progress-focus">${escapeHtml(board.current_focus || 'unknown')}</div>
            <div class="progress-meta">生成时间 ${escapeHtml(board.generated_at)} / ${escapeHtml((board.git || {}).head || 'unknown')}</div>
            <div class="progress-actions">
              <span class="card-label">等待创始人确认</span>
              ${asks ? `<ul>${asks}</ul>` : '<div class="progress-meta">当前没有待确认事项</div>'}
            </div>
          </div>
          <div class="progress-milestones">${milestones}</div>
        </div>`;
    }
    function setRefreshStatus(message, state = '') {
      refreshStatus.textContent = message;
      refreshStatus.className = `refresh-status ${state}`.trim();
    }
    function lastRefreshSuffix() {
      if (!lastSuccessfulDashboardState) return '';
      const updatedAt = lastSuccessfulDashboardState.dashboard_refreshed_at;
      return updatedAt ? ` / 当前显示 ${updatedAt} 的数据` : ' / 当前保留上次成功数据';
    }
    async function refresh() {
      if (refreshInFlight) return;
      refreshInFlight = true;
      refreshDashboard.disabled = true;
      refreshStatus.dataset.state = 'refreshing';
      setRefreshStatus('正在刷新…');
      try {
        const response = await fetch('/api/state', { headers: authHeaders() });
        if (response.status === 401) {
          authStatus.textContent = '需要访问令牌';
          setRefreshStatus(`请保存访问令牌${lastRefreshSuffix()}`, 'warn');
          return;
        }
        if (!response.ok) {
          authStatus.textContent = `HTTP ${response.status}`;
          setRefreshStatus(`接口错误 HTTP ${response.status}${lastRefreshSuffix()}`, 'warn');
          return;
        }
        const data = await response.json();
        data.dashboard_refreshed_at = new Date().toLocaleTimeString();
        lastSuccessfulDashboardState = data;
        authStatus.textContent = '已连接';
        progressBoard.className = '';
        progressBoard.innerHTML = progressBoardPanel(data.progress_board || {});
        runContext.innerHTML = runContextPanel(data.current_run || {});
        productDemo.innerHTML = productDemoPanel(data.product_demo || {});
        fieldResults.innerHTML = fieldResultsPanel(data.field_results || {}, data.data_flywheel || {});
        dataFlywheel.innerHTML = dataFlywheelPanel(data.data_flywheel || {});
        trainingExperiment.innerHTML = trainingExperimentPanel(data.training_experiment || {});
        trainingRunPreflight.innerHTML = trainingRunPreflightPanel(data.training_run_preflight || {});
        trainingFeatureManifest.innerHTML = trainingFeatureManifestPanel(data.training_feature_manifest || {});
        trainingRunnerDryRun.innerHTML = trainingRunnerDryRunPanel(data.training_runner_dry_run || {});
        trainingBaselineEval.innerHTML = trainingBaselineEvalPanel(data.training_baseline_eval || {});
        trainingHandoffBundle.innerHTML = trainingHandoffBundlePanel(data.training_handoff_bundle || {});
        trainingJobPlan.innerHTML = trainingJobPlanPanel(data.training_job_plan || {});
        syntheticTrainingChain.innerHTML = syntheticTrainingChainPanel(data.synthetic_training_chain || {});
        d1TrainingReadiness.innerHTML = d1TrainingReadinessPanel(data.d1_training_readiness || {});
        d1LabelingIntake.innerHTML = d1LabelingIntakePanel(data.d1_labeling_intake || {});
        d1LabelingQueue.innerHTML = d1LabelingQueuePanel(data.d1_labeling_queue || {});
        d1LabelingReviewPacket.innerHTML = d1LabelingReviewPacketPanel(data.d1_labeling_review_packet || {});
        d1LabelingDecisionTemplate.innerHTML = d1LabelingDecisionTemplatePanel(data.d1_labeling_decision_template || {});
        updateDeviceSelector(data.devices || [], data.current_run || {});
        renderSelectedDevicePanels();
        devices.innerHTML = (data.devices || []).map(d => `
          <div class="metric"><span>设备</span><b>${escapeHtml(d.device_id)}</b></div>
          <div class="metric"><span>状态</span><span class="${ageClass(d.last_seen_at)}">${escapeHtml(onlineDisplayLabel(d.last_seen_at))}</span></div>
          <div class="metric"><span>最后通信</span><span>${escapeHtml(formatDashboardDateTime(d.last_seen_at))}</span></div>
          <div class="metric"><span>最新类型</span><span>${escapeHtml(d.last_message_type)}</span></div>
          <div class="metric"><span>序号</span><span>${escapeHtml(d.last_seq)}</span></div>
        `).join('') || '<span class="empty">暂无设备</span>';
        commands.innerHTML = (data.commands || []).map(c => `
          <div class="metric"><span>${escapeHtml(c.cmd_id)}</span><span class="${c.status === 'ok' ? 'ok' : c.status === 'pending' ? 'warn' : 'bad'}">${escapeHtml(c.cmd)} / ${escapeHtml(c.status)}</span></div>
        `).join('') || '<span class="empty">暂无指令</span>';
        rawFrames.innerHTML = (data.raw_frames || []).map(frame => {
          const parsed = parseResult(frame);
          const frameMeta = framing(frame);
          const reason = parsed.reason || parsed.error_code || 'none';
          return `
            <div class="metric"><span>${escapeHtml(frame.frame_id || 'raw')}</span><span class="${rawFrameClass(frame)}">${escapeHtml(rawFrameSummary(frame))}</span></div>
            <div class="metric"><span>接收时间</span><span>${escapeHtml(frame.server_received_at || 'unknown')}</span></div>
            <div class="metric"><span>载荷</span><span>${escapeHtml(frameMeta.payload_len ?? 'unknown')} bytes / ${escapeHtml(frameMeta.payload_crc32 || 'unknown')}</span></div>
            <div class="metric"><span>原因</span><span>${escapeHtml(reason)}</span></div>
          `;
        }).join('') || '<span class="empty">暂无原始帧</span>';
        messages.innerHTML = (data.messages || []).map(m => `
          <tr>
            <td>${escapeHtml(m.device_id)}</td>
            <td>${escapeHtml(m.message_type)}</td>
            <td>${escapeHtml(m.seq)}</td>
            <td>${escapeHtml(detail(m))}</td>
            <td>${escapeHtml(m.server_received_at)}</td>
          </tr>
        `).join('') || '<tr><td colspan="5" class="empty">暂无消息</td></tr>';
        refreshStatus.dataset.state = 'connected';
        setRefreshStatus(`已更新 ${data.dashboard_refreshed_at}`, 'ok');
      } catch (error) {
        const reason = error instanceof Error && error.message ? error.message : '请求失败';
        const previousView = lastSuccessfulDashboardState ? lastRefreshSuffix() : '';
        refreshStatus.dataset.state = 'failed';
        setRefreshStatus(`刷新失败：${reason}${previousView}`, 'warn');
      } finally {
        refreshInFlight = false;
        refreshDashboard.disabled = false;
      }
    }
    refresh();
  </script>
</body>
</html>"""
    return html.replace("__AMAP_BOOTSTRAP__", amap_bootstrap).replace("__AMAP_JS_API_KEY__", safe_amap_key)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ego Link P0 HTTP message hub.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--photo-root",
        type=Path,
        default=(
            Path(os.environ["EGOLINK_PHOTO_ROOT"])
            if os.environ.get("EGOLINK_PHOTO_ROOT")
            else None
        ),
        help=(
            "Private photo directory (default: a non-public photos directory "
            "beside the SQLite database)."
        ),
    )
    parser.add_argument(
        "--token-env",
        default="EGOLINK_MESSAGE_HUB_TOKEN",
        help="Environment variable containing the optional bearer token.",
    )
    parser.add_argument(
        "--guardian-bindings-env",
        default="EGOLINK_GUARDIAN_BINDINGS_FILE",
        help=(
            "Environment variable containing the path to a hashed "
            "Guardian-device binding file."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = MessageHubStore(args.db, photo_root=args.photo_root)
    token = os.environ.get(args.token_env) or None
    guardian_bindings_path = os.environ.get(args.guardian_bindings_env) or None
    guardian_authorizer = (
        GuardianDeviceAuthorizer.from_file(Path(guardian_bindings_path))
        if guardian_bindings_path is not None
        else None
    )
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            store,
            token=token,
            guardian_authorizer=guardian_authorizer,
        ),
    )
    print(f"Ego Link Message Hub running at http://{args.host}:{args.port}")
    print(f"SQLite database: {args.db}")
    print(f"Private photo root: {store.photos.root}")
    if token:
        print("Bearer token authentication: enabled")
    else:
        print("Bearer token authentication: disabled")
    if guardian_authorizer is not None:
        print("Guardian-device binding authorization: enabled")
    else:
        print("Guardian-device binding authorization: disabled")
    store.photos.start_retention_maintenance()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
        store.photos.stop_retention_maintenance()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
