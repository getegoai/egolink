from __future__ import annotations

import base64
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib import error, request

from jsonschema import Draft202012Validator

from server import message_hub
from server.collection_store import CONTENT_TYPE
from server.guardian_device_authorization import (
    GuardianDeviceAuthorizer,
    token_sha256,
)


DEVICE = "photo-test-001"
OTHER_DEVICE = "photo-test-002"
GUARDIAN_TOKEN = "photo-guardian-token-not-a-real-secret"
OTHER_GUARDIAN_TOKEN = "other-guardian-token-not-a-secret"
UPLOAD_TOKEN = "photo-device-token-not-a-real-secret"
JPEG = base64.b64decode(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/wAALCADwAUABAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/9k="
)
JPEG_ALTERNATE = base64.b64decode(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/wAALCADwAUABAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAA/AKQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2Q=="
)


def utc_after(*, seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def camera_envelope(
    sequence: int = 1,
    *,
    photo_id: str | None = None,
    jpeg: bytes = JPEG,
    retention_expires_at: str | None = None,
    **payload_changes,
):
    photo_id = photo_id or f"photo-{sequence:03d}"
    session_id = "authorized-photo-session"
    payload = {
        "photo_id": photo_id,
        "trigger_reason": "web_manual",
        "command_id": f"capture-{sequence:03d}",
        "config_version": "camera-config-v1",
        "capture_result": "captured",
        "local_save_status": "saved",
        "device_upload_status": "pending",
        "media_type": "image/jpeg",
        "width": 320,
        "height": 240,
        "byte_length": len(jpeg),
        "sha256": hashlib.sha256(jpeg).hexdigest(),
        "storage_kind": "persistent",
        "camera_model": "OV5640",
        "driver_profile": "qvga-jpeg-q12-v1",
        "location_ref": None,
        "authorization_session_id": session_id,
        "retention_expires_at": retention_expires_at or utc_after(seconds=3600),
        "training_allowed": False,
    }
    payload.update(payload_changes)
    return {
        "contract_version": "egolink.collection.v1",
        "observation_id": f"camera-observation-{sequence:03d}",
        "device_id": DEVICE,
        "source": "camera",
        "stream_id": "camera-test",
        "sequence_id": sequence,
        "boot_count": 1,
        "monotonic_clock_domain_id": "photo-test-boot-1",
        "timestamp_monotonic_ns": sequence * 1_000_000_000,
        "timestamp_utc": utc_after(seconds=-1),
        "timestamp_source": "gnss",
        "timestamp_quality": "gnss_synchronized",
        "fw_version": "photo-fixture",
        "config_id": "collection-config-v1",
        "session_id": session_id,
        "status": "captured",
        "payload": payload,
        "missing_reason": None,
    }


def gnss_envelope(
    sequence: int,
    *,
    observation_id: str,
    event_utc: str,
    fix: bool = True,
):
    return {
        "contract_version": "egolink.collection.v1",
        "observation_id": observation_id,
        "device_id": DEVICE,
        "source": "gnss",
        "stream_id": "gnss-test",
        "sequence_id": sequence,
        "boot_count": 1,
        "monotonic_clock_domain_id": "photo-test-boot-1",
        "timestamp_monotonic_ns": sequence * 1_000_000_000,
        "timestamp_utc": event_utc,
        "timestamp_source": "gnss",
        "timestamp_quality": "gnss_synchronized",
        "fw_version": "photo-fixture",
        "config_id": "collection-config-v1",
        "session_id": "location-test-session",
        "status": "fix" if fix else "no_fix",
        "payload": {
            "at": [],
            "fix": fix,
            "latitude": 22.543096 if fix else None,
            "longitude": 114.057865 if fix else None,
        },
        "missing_reason": None if fix else "indoor_no_fix",
    }


def camera_source_status_envelope(
    sequence: int,
    *,
    command_id: str | None,
    authorization_session_id: str | None,
    timer_state: dict,
):
    event_utc = utc_after(seconds=0)
    return {
        "contract_version": "egolink.collection.v1",
        "observation_id": f"camera-source-status-{sequence:03d}",
        "device_id": DEVICE,
        "source": "source_status",
        "stream_id": "camera-status-test",
        "sequence_id": sequence,
        "boot_count": 7,
        "monotonic_clock_domain_id": "photo-test-boot-7",
        "timestamp_monotonic_ns": sequence * 1_000_000_000,
        "timestamp_utc": event_utc,
        "timestamp_source": "sntp",
        "timestamp_quality": "network_time_unverified_accuracy",
        "fw_version": "photo-fixture",
        "config_id": "camera-runtime-v1",
        "session_id": "authorized-photo-session",
        "status": "observed",
        "payload": {
            "source": "camera",
            "component": "photo_control",
            "camera_runtime_compiled": True,
            "driver_preflight_ready": True,
            "capture_trigger_wired": True,
            "media_store_ready": True,
            "command_id": command_id,
            "authorization_session_id": authorization_session_id,
            "source_event_utc": event_utc,
            "source_event_monotonic_ms": sequence * 1000,
            "event_reason": "periodic_state",
            "timer_state": timer_state,
        },
        "missing_reason": None,
    }


def frame(envelope):
    return message_hub.build_raw_frame(
        "event",
        envelope["observation_id"],
        json.dumps(envelope, separators=(",", ":")).encode(),
        seq=envelope["sequence_id"],
        content_type=CONTENT_TYPE,
    )


def authorizer() -> GuardianDeviceAuthorizer:
    return GuardianDeviceAuthorizer(
        {
            "contract_version": "egolink.guardian_device_bindings.v0.1",
            "bindings": [
                {
                    "guardian_id": "photo-guardian",
                    "token_sha256": token_sha256(GUARDIAN_TOKEN),
                    "device_ids": [DEVICE],
                },
                {
                    "guardian_id": "other-guardian",
                    "token_sha256": token_sha256(OTHER_GUARDIAN_TOKEN),
                    "device_ids": [OTHER_DEVICE],
                },
            ],
        }
    )


@contextmanager
def running_hub(store, *, upload_token=UPLOAD_TOKEN):
    handler = message_hub.make_handler(
        store, token=upload_token, guardian_authorizer=authorizer()
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def http(base, path, *, body=None, token=None, headers=None, method=None):
    values = dict(headers or {})
    if token is not None:
        values["Authorization"] = "Bearer " + token
    req = request.Request(
        base + path,
        data=body,
        headers=values,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        response = request.urlopen(req, timeout=5)
    except error.HTTPError as failure:
        response = failure
    with response:
        return response.status, response.read(), dict(response.headers)


class PhotoStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = message_hub.MessageHubStore(
            self.root / "hub.db", photo_root=self.root / "private-photos"
        )
        self.authorization_expiry = utc_after(seconds=86_400)
        self.store.photos.authorize_session(
            DEVICE,
            {
                "authorization_session_id": "authorized-photo-session",
                "retention_expires_at": self.authorization_expiry,
                "training_allowed": False,
            },
            guardian_id="photo-guardian",
        )

    def create_matching_photo_command(self, envelope):
        payload = envelope["payload"]
        with self.store.connection() as db:
            existing = db.execute(
                "SELECT cmd_id FROM commands WHERE device_id=? AND cmd_id=?",
                (envelope["device_id"], payload["command_id"]),
            ).fetchone()
        if existing is not None:
            return
        now_ms = int(time.time() * 1000)
        if payload["trigger_reason"] == "web_manual":
            command = {
                "cmd": "capture_photo_once",
                "cmd_id": payload["command_id"],
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": payload[
                        "authorization_session_id"
                    ],
                    "retention_expires_at": payload["retention_expires_at"],
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            }
        else:
            retention_ms = int(
                datetime.fromisoformat(
                    payload["retention_expires_at"][:-1] + "+00:00"
                ).timestamp()
                * 1000
            )
            command = {
                "cmd": "configure_photo_timer",
                "cmd_id": payload["command_id"],
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": payload[
                        "authorization_session_id"
                    ],
                    "config_version": payload["config_version"],
                    "enabled": True,
                    "interval_seconds": 300,
                    "session_expires_at_unix_ms": min(
                        retention_ms, now_ms + 30 * 60_000
                    ),
                    "retention_expires_at": payload["retention_expires_at"],
                    "max_photos": 288,
                    "training_allowed": False,
                },
            }
        self.store.create_command(
            envelope["device_id"],
            command,
            photo_control_guardian_id="photo-guardian",
        )

    def ingest_collection(self, envelope, *, transport="lte"):
        raw = frame(envelope)
        record = message_hub.parse_raw_frame_record(
            message_hub.initial_raw_frame_record(
                envelope["device_id"], raw, "uplink", message_hub.utc_now()
            ),
            raw,
            expected_frame_type="event",
        )
        return self.store.collection.ingest(raw, record, transport=transport)

    def ingest_metadata(self, envelope, *, seed_causality=True):
        if seed_causality:
            self.create_matching_photo_command(envelope)
        return self.ingest_collection(envelope)

    def ack_command(
        self,
        command_id: str,
        status: str,
        *,
        sequence: int,
        timer_state=None,
    ):
        payload = {
            "protocol_version": "egolink.p0.v1",
            "device_id": DEVICE,
            "ts": utc_after(seconds=0),
            "seq": sequence,
            "message_type": "ack",
            "cmd_id": command_id,
            "status": status,
        }
        if timer_state is not None:
            payload["timer_state"] = timer_state
        return self.store.ingest(
            DEVICE,
            "ack",
            payload,
        )

    def test_camera_metadata_and_durable_content_are_separate_and_idempotent(self):
        envelope = camera_envelope()
        result = self.ingest_metadata(envelope)
        self.assertEqual(result["result"], "accepted")
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photo_records").fetchone()[0], 1)
            row = db.execute("SELECT * FROM photo_records").fetchone()
            self.assertEqual(row["content_status"], "pending")
            self.assertEqual(row["training_allowed"], 0)

        stored = self.store.photos.store_content(
            DEVICE,
            envelope["payload"]["photo_id"],
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        self.assertEqual(stored["result"], "accepted")
        self.assertEqual(stored["delivery_ack"]["status"], "server_verified")
        self.assertEqual(
            stored["delivery_ack"]["verification_scope"],
            "sha256_length_geometry_baseline_structure_v1",
        )
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM photo_records").fetchone()
            relative = row["content_relative_path"]
            self.assertFalse(Path(relative).is_absolute())
            self.assertEqual(row["stored_transport"], "lte")
            raw_record = db.execute("SELECT raw_payload_b64 FROM raw_frames").fetchone()[0]
            self.assertNotIn(JPEG.hex(), raw_record)
        path = self.store.photos.root / relative
        self.assertEqual(path.read_bytes(), JPEG)
        self.assertEqual(list(path.parent.glob(".photo-upload-*.tmp")), [])

        duplicate = self.store.photos.store_content(
            DEVICE,
            envelope["payload"]["photo_id"],
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        self.assertEqual(duplicate["result"], "duplicate")
        other = JPEG_ALTERNATE
        with self.assertRaises(message_hub.PhotoStoreError) as conflict:
            self.store.photos.store_content(
                DEVICE,
                envelope["payload"]["photo_id"],
                other,
                claimed_sha256=hashlib.sha256(other).hexdigest(),
                transport="lte",
            )
        self.assertEqual((conflict.exception.code, conflict.exception.status), ("photo_content_conflict", 409))

    def test_only_structural_jpeg_with_matching_geometry_is_server_verified(self):
        valid = camera_envelope(20, photo_id="valid-geometry")
        self.ingest_metadata(valid)
        accepted = self.store.photos.store_content(
            DEVICE,
            "valid-geometry",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        self.assertEqual(accepted["delivery_ack"]["status"], "server_verified")

        soi_eoi_only = b"\xff\xd8" + b"not-a-jpeg-marker-stream" + b"\xff\xd9"
        malformed = camera_envelope(
            21,
            photo_id="soi-eoi-only",
            jpeg=soi_eoi_only,
        )
        self.ingest_metadata(malformed)
        with self.assertRaises(message_hub.PhotoStoreError) as invalid:
            self.store.photos.store_content(
                DEVICE,
                "soi-eoi-only",
                soi_eoi_only,
                claimed_sha256=hashlib.sha256(soi_eoi_only).hexdigest(),
                transport="lte",
            )
        self.assertEqual((invalid.exception.code, invalid.exception.status), ("invalid_jpeg", 422))

        wrong_geometry = camera_envelope(
            22,
            photo_id="wrong-geometry",
            width=319,
        )
        self.ingest_metadata(wrong_geometry)
        with self.assertRaises(message_hub.PhotoStoreError) as mismatch:
            self.store.photos.store_content(
                DEVICE,
                "wrong-geometry",
                JPEG,
                claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
                transport="lte",
            )
        self.assertEqual(
            (mismatch.exception.code, mismatch.exception.status),
            ("photo_geometry_mismatch", 409),
        )
        with self.store.connection() as db:
            statuses = {
                row["photo_id"]: row["content_status"]
                for row in db.execute(
                    "SELECT photo_id,content_status FROM photo_records"
                )
            }
        self.assertEqual(
            statuses,
            {
                "valid-geometry": "stored",
                "soi-eoi-only": "pending",
                "wrong-geometry": "pending",
            },
        )

    def test_unavailable_capture_results_are_not_expected_or_pending(self):
        unavailable = []
        for sequence, status, capture_result, local_save_status, reason in (
            (30, "capture_failed", "capture_failed", "not_attempted", "camera_capture_unavailable"),
            (31, "not_attempted", "not_attempted", "not_attempted", "camera_capture_unavailable"),
            (32, "save_failed", "captured", "save_failed", "camera_capture_unavailable"),
            (
                33,
                "outcome_unknown",
                "outcome_unknown",
                "unknown",
                "capture_outcome_unknown_after_reboot",
            ),
        ):
            envelope = camera_envelope(
                sequence,
                capture_result=capture_result,
                local_save_status=local_save_status,
                device_upload_status="not_ready",
                media_type=None,
                width=None,
                height=None,
                byte_length=None,
                sha256=None,
                storage_kind="none",
            )
            envelope["status"] = status
            envelope["missing_reason"] = reason
            self.assertEqual(
                list(
                    Draft202012Validator(
                        json.loads(
                            (
                                Path(__file__).resolve().parents[1]
                                / "shared/contracts/collection_observation.schema.json"
                            ).read_text(encoding="utf-8")
                        )
                    ).iter_errors(envelope)
                ),
                [],
            )
            self.ingest_metadata(envelope)
            unavailable.append(envelope["payload"]["photo_id"])

        listing = self.store.photos.list(DEVICE, {"limit": ["1"]})
        self.assertEqual(listing["aggregate"]["record_count"], 4)
        self.assertEqual(listing["aggregate"]["not_expected_count"], 4)
        self.assertEqual(listing["aggregate"]["pending_content_count"], 0)
        self.assertEqual(listing["aggregate"]["pending_content_bytes"], 0)
        for photo_id in unavailable:
            record = self.store.photos.metadata(DEVICE, photo_id)
            self.assertEqual(record["content"]["status"], "not_expected")
            self.assertIsNone(record["content"]["url"])

    def test_camera_contract_and_store_reject_incoherent_result_states(self):
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/collection_observation.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        invalid = camera_envelope(
            33,
            capture_result="capture_failed",
            local_save_status="save_failed",
            device_upload_status="not_ready",
            media_type=None,
            width=None,
            height=None,
            byte_length=None,
            sha256=None,
            storage_kind="none",
        )
        invalid["status"] = "capture_failed"
        invalid["missing_reason"] = "camera_capture_failed"
        self.assertNotEqual(list(validator.iter_errors(invalid)), [])
        with self.assertRaises(message_hub.PhotoStoreError) as rejected:
            self.store.photos.validate_metadata(invalid)
        self.assertEqual(rejected.exception.code, "invalid_camera_metadata")

        mismatched_status = camera_envelope(34)
        mismatched_status["status"] = "save_failed"
        mismatched_status["missing_reason"] = "claimed_save_failure"
        self.assertNotEqual(list(validator.iter_errors(mismatched_status)), [])
        with self.assertRaises(message_hub.PhotoStoreError) as rejected_status:
            self.store.photos.validate_metadata(mismatched_status)
        self.assertEqual(rejected_status.exception.code, "invalid_camera_metadata")

        ambiguous_recovery = camera_envelope(
            35,
            capture_result="outcome_unknown",
            local_save_status="unknown",
            device_upload_status="not_ready",
            media_type=None,
            width=None,
            height=None,
            byte_length=None,
            sha256=None,
            storage_kind="none",
        )
        ambiguous_recovery["status"] = "outcome_unknown"
        ambiguous_recovery["missing_reason"] = "camera_capture_unavailable"
        self.assertTrue(list(validator.iter_errors(ambiguous_recovery)))
        with self.assertRaises(message_hub.PhotoStoreError) as recovered_rejected:
            self.store.photos.validate_metadata(ambiguous_recovery)
        self.assertEqual(
            recovered_rejected.exception.code, "invalid_camera_metadata"
        )

    def test_guardian_bound_list_metadata_and_private_preview(self):
        envelope = camera_envelope()
        self.ingest_metadata(envelope)
        self.store.photos.store_content(
            DEVICE,
            envelope["payload"]["photo_id"],
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        photo_path = f"/api/v1/devices/{DEVICE}/photos/{envelope['payload']['photo_id']}"
        with running_hub(self.store) as base:
            unauthenticated = http(base, f"/api/v1/devices/{DEVICE}/photos")
            forbidden = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos",
                token=OTHER_GUARDIAN_TOKEN,
            )
            listed = http(
                base, f"/api/v1/devices/{DEVICE}/photos", token=GUARDIAN_TOKEN
            )
            exported = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/export.json?session_id=authorized-photo-session",
                token=GUARDIAN_TOKEN,
            )
            metadata = http(base, photo_path, token=GUARDIAN_TOKEN)
            preview = http(base, photo_path + "/content", token=GUARDIAN_TOKEN)
            session_body = json.dumps(
                {
                    "authorization_session_id": "second-photo-session",
                    "retention_expires_at": utc_after(seconds=7200),
                    "training_allowed": False,
                }
            ).encode()
            session_unauthorized = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/sessions",
                body=session_body,
                headers={"Content-Type": "application/json"},
                token=UPLOAD_TOKEN,
            )
            session_authorized = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/sessions",
                body=session_body,
                headers={"Content-Type": "application/json"},
                token=GUARDIAN_TOKEN,
            )
            direct_static_probe = http(
                base,
                "/server/runtime/photos/private-photo.jpg",
            )
        self.assertEqual(unauthenticated[0], 401)
        self.assertEqual(forbidden[0], 403)
        for response in (unauthenticated, forbidden, listed, exported, metadata, preview):
            self.assertEqual(response[2]["Cache-Control"], "no-store")
            self.assertEqual(response[2]["X-Content-Type-Options"], "nosniff")
        listing = json.loads(listed[1])
        self.assertEqual(listing["photos"][0]["content"]["status"], "stored")
        self.assertFalse(listing["photos"][0]["training_allowed"])
        self.assertNotIn(str(self.store.photos.root), listed[1].decode())
        export_payload = json.loads(exported[1])
        self.assertEqual(
            export_payload["scope"],
            "private_photo_metadata_and_collection_observation",
        )
        self.assertEqual(
            exported[2]["Content-Disposition"],
            'attachment; filename="egolink-photo-observations.json"',
        )
        self.assertEqual(json.loads(metadata[1])["photo"]["photo_id"], "photo-001")
        self.assertEqual(preview[1], JPEG)
        self.assertEqual(preview[2]["Content-Type"], "image/jpeg")
        self.assertEqual(preview[2]["X-Content-SHA256"], hashlib.sha256(JPEG).hexdigest())
        self.assertEqual(session_unauthorized[0], 401)
        self.assertEqual(session_authorized[0], 200)
        self.assertFalse(
            json.loads(session_authorized[1])["authorization_session"][
                "training_allowed"
            ]
        )
        self.assertEqual(direct_static_probe[0], 404)
        self.assertNotEqual(direct_static_probe[1], JPEG)

    def test_http_upload_requires_device_auth_and_returns_server_verified(self):
        envelope = camera_envelope()
        self.ingest_metadata(envelope)
        path = f"/api/v1/devices/{DEVICE}/photos/photo-001/content"
        headers = {
            "Content-Type": "image/jpeg",
            "X-Content-SHA256": hashlib.sha256(JPEG).hexdigest(),
            "X-EgoLink-Transport": "lte",
        }
        with self.store.connection() as db:
            raw_before = db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0]
        with running_hub(self.store) as base:
            unauthorized = http(base, path, body=JPEG, headers=headers)
        with self.store.connection() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], raw_before
            )
            self.assertEqual(
                db.execute("SELECT content_status FROM photo_records").fetchone()[0],
                "pending",
            )
        self.assertEqual(list(self.store.photos.root.rglob("*.jpg")), [])
        with running_hub(self.store) as base:
            rejected_type = http(
                base,
                path,
                body=b"nope",
                headers={
                    **headers,
                    "Content-Type": "application/octet-stream",
                    "X-Content-SHA256": hashlib.sha256(b"nope").hexdigest(),
                },
                token=UPLOAD_TOKEN,
            )
            rejected_state = self.store.photos.metadata(DEVICE, "photo-001")
            accepted = http(
                base, path, body=JPEG, headers=headers, token=UPLOAD_TOKEN
            )
        with running_hub(self.store, upload_token=None) as base:
            auth_not_configured = http(base, path, body=JPEG, headers=headers)
        self.assertEqual(unauthorized[0], 401)
        self.assertEqual(rejected_type[0], 415)
        self.assertEqual(rejected_state["upload_attempts"]["count"], 1)
        self.assertEqual(
            rejected_state["upload_attempts"]["last_error_code"],
            "photo_content_type_required",
        )
        self.assertEqual(accepted[0], 200, accepted[1])
        self.assertEqual(auth_not_configured[0], 503)
        self.assertEqual(
            json.loads(accepted[1])["delivery_ack"]["status"], "server_verified"
        )
        self.assertEqual(accepted[2]["Cache-Control"], "no-store")
        self.assertEqual(accepted[2]["X-Content-Type-Options"], "nosniff")

    def test_contract_rejects_missing_authorization_and_training_opt_in_before_write(self):
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/collection_observation.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(camera_envelope())), [])
        invalid_values = (
            camera_envelope(2, authorization_session_id="another-session"),
            camera_envelope(3, training_allowed=True),
        )
        for value in invalid_values:
            with self.subTest(sequence=value["sequence_id"]):
                with self.assertRaises(message_hub.CollectionError) as raised:
                    self.ingest_metadata(value, seed_causality=False)
                self.assertEqual(raised.exception.code, "invalid_camera_metadata")
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photo_records").fetchone()[0], 0)

        unauthorized_store = message_hub.MessageHubStore(
            self.root / "unauthorized.db",
            photo_root=self.root / "unauthorized-photos",
        )
        original_store = self.store
        self.store = unauthorized_store
        try:
            with self.assertRaises(message_hub.CollectionError) as unauthorized:
                self.ingest_metadata(camera_envelope(4), seed_causality=False)
        finally:
            self.store = original_store
        self.assertEqual(unauthorized.exception.code, "photo_session_not_authorized")
        with unauthorized_store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], 0)

        raw = frame(camera_envelope(5))
        with running_hub(unauthorized_store) as base:
            code, body, _ = http(
                base,
                f"/api/v1/devices/{DEVICE}/raw-ingest",
                body=raw,
                token=UPLOAD_TOKEN,
                headers={"X-EgoLink-Transport": "lte"},
            )
        self.assertEqual(code, 403, body)
        self.assertEqual(json.loads(body)["error"], "photo_session_not_authorized")
        with unauthorized_store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_records").fetchone()[0], 0)

    def test_expired_retention_deletes_bytes_but_keeps_audit_metadata(self):
        envelope = camera_envelope()
        self.ingest_metadata(envelope)
        self.store.photos.store_content(
            DEVICE,
            "photo-001",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        with self.store.connection() as db:
            row = db.execute("SELECT content_relative_path FROM photo_records").fetchone()
            path = self.store.photos.root / row["content_relative_path"]
            db.execute(
                "UPDATE photo_records SET retention_expires_at=?",
                (utc_after(seconds=-1),),
            )
        self.assertTrue(path.exists())
        metadata = self.store.photos.metadata(DEVICE, "photo-001")
        self.assertEqual(metadata["content"]["status"], "expired")
        self.assertFalse(path.exists())
        with self.assertRaises(message_hub.PhotoStoreError) as expired:
            self.store.photos.content(DEVICE, "photo-001")
        self.assertEqual(expired.exception.code, "photo_retention_expired")

        orphan_envelope = camera_envelope(2, photo_id="photo-orphan")
        self.ingest_metadata(orphan_envelope)
        orphan_path, _ = self.store.photos._target(
            DEVICE,
            "photo-orphan",
            hashlib.sha256(JPEG).hexdigest(),
        )
        orphan_path.write_bytes(JPEG)
        with self.store.connection() as db:
            db.execute(
                "UPDATE photo_records SET retention_expires_at=? WHERE photo_id=?",
                (utc_after(seconds=-1), "photo-orphan"),
            )
        self.store.photos.purge_expired()
        self.assertFalse(orphan_path.exists())

    def test_periodic_retention_expires_content_without_a_photo_api_request(self):
        envelope = camera_envelope(6, photo_id="periodic-expiry")
        self.ingest_metadata(envelope)
        self.store.photos.store_content(
            DEVICE,
            "periodic-expiry",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        with self.store.connection() as db:
            row = db.execute(
                "SELECT id,content_relative_path FROM photo_records "
                "WHERE device_id=? AND photo_id=?",
                (DEVICE, "periodic-expiry"),
            ).fetchone()
            content_path = self.store.photos.root / row["content_relative_path"]
            db.execute(
                "UPDATE photo_records SET retention_expires_at=? WHERE id=?",
                (utc_after(seconds=-1), row["id"]),
            )
        self.assertTrue(content_path.exists())

        self.store.photos.start_retention_maintenance(interval_seconds=0.02)
        try:
            deadline = time.monotonic() + 1.0
            while content_path.exists() and time.monotonic() < deadline:
                threading.Event().wait(0.01)
        finally:
            self.store.photos.stop_retention_maintenance()

        self.assertFalse(content_path.exists())
        with self.store.connection() as db:
            expired = db.execute(
                "SELECT content_status,content_relative_path FROM photo_records "
                "WHERE id=?",
                (row["id"],),
            ).fetchone()
        self.assertEqual(expired["content_status"], "expired")
        self.assertIsNone(expired["content_relative_path"])

    def test_retention_unlink_failure_never_claims_completed_purge(self):
        envelope = camera_envelope(11, photo_id="purge-permission-failure")
        self.ingest_metadata(envelope)
        self.store.photos.store_content(
            DEVICE,
            "purge-permission-failure",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        with self.store.connection() as db:
            row = db.execute(
                "SELECT id,content_relative_path FROM photo_records "
                "WHERE photo_id='purge-permission-failure'"
            ).fetchone()
            path = self.store.photos.root / row["content_relative_path"]
            db.execute(
                "UPDATE photo_records SET retention_expires_at=? WHERE id=?",
                (utc_after(seconds=-1), row["id"]),
            )

        with mock.patch.object(
            Path, "unlink", side_effect=PermissionError("test denied")
        ):
            self.assertEqual(self.store.photos.purge_expired(), 0)

        self.assertTrue(path.exists())
        with self.store.connection() as db:
            expired = db.execute(
                "SELECT content_status,content_purge_state,content_purge_error,"
                "content_relative_path FROM photo_records WHERE id=?",
                (row["id"],),
            ).fetchone()
        self.assertEqual(expired["content_status"], "expired")
        self.assertEqual(expired["content_purge_state"], "failed")
        self.assertEqual(expired["content_purge_error"], "PermissionError")
        self.assertEqual(expired["content_relative_path"], row["content_relative_path"])

    def test_retention_corrupt_path_isolated_and_canonical_bytes_are_purged(self):
        paths = {}
        for sequence, photo_id in ((7, "purge-good"), (8, "purge-bad-path")):
            envelope = camera_envelope(sequence, photo_id=photo_id)
            self.ingest_metadata(envelope)
            self.store.photos.store_content(
                DEVICE,
                photo_id,
                JPEG,
                claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
                transport="lte",
            )
        with self.store.connection() as db:
            for row in db.execute(
                "SELECT photo_id,content_relative_path FROM photo_records ORDER BY id"
            ):
                paths[row["photo_id"]] = self.store.photos.root / row[
                    "content_relative_path"
                ]
            db.execute(
                "UPDATE photo_records SET retention_expires_at=?",
                (utc_after(seconds=-1),),
            )
            db.execute(
                "UPDATE photo_records SET content_relative_path='../escape.jpg' "
                "WHERE photo_id='purge-bad-path'"
            )

        self.assertEqual(self.store.photos.purge_expired(), 1)
        with self.store.connection() as db:
            rows = {
                row["photo_id"]: dict(row)
                for row in db.execute(
                    "SELECT photo_id,content_status,content_purge_state,"
                    "content_purge_error FROM photo_records"
                )
            }
        self.assertEqual(rows["purge-good"]["content_status"], "expired")
        self.assertEqual(rows["purge-good"]["content_purge_state"], "complete")
        self.assertFalse(paths["purge-good"].exists())
        self.assertEqual(rows["purge-bad-path"]["content_status"], "expired")
        self.assertEqual(rows["purge-bad-path"]["content_purge_state"], "failed")
        self.assertEqual(
            rows["purge-bad-path"]["content_purge_error"],
            "invalid_recorded_path_ignored",
        )
        self.assertFalse(paths["purge-bad-path"].exists())

    def test_retention_never_follows_a_recorded_path_to_another_photo(self):
        paths = {}
        for sequence, photo_id in ((9, "purge-source"), (10, "purge-neighbor")):
            envelope = camera_envelope(sequence, photo_id=photo_id)
            self.ingest_metadata(envelope)
            self.store.photos.store_content(
                DEVICE,
                photo_id,
                JPEG,
                claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
                transport="lte",
            )
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT photo_id,content_relative_path FROM photo_records"
            ).fetchall()
            paths = {row["photo_id"]: row["content_relative_path"] for row in rows}
            db.execute(
                "UPDATE photo_records SET retention_expires_at=?,"
                "content_relative_path=? WHERE photo_id='purge-source'",
                (utc_after(seconds=-1), paths["purge-neighbor"]),
            )

        self.store.photos.purge_expired()
        source_canonical, _ = self.store.photos._target(
            DEVICE,
            "purge-source",
            hashlib.sha256(JPEG).hexdigest(),
            create_directory=False,
        )
        neighbor_path = self.store.photos.root / paths["purge-neighbor"]
        self.assertFalse(source_canonical.exists())
        self.assertTrue(neighbor_path.exists())
        with self.store.connection() as db:
            source = db.execute(
                "SELECT content_status,content_purge_state,content_purge_error "
                "FROM photo_records WHERE photo_id='purge-source'"
            ).fetchone()
            neighbor = db.execute(
                "SELECT content_status FROM photo_records "
                "WHERE photo_id='purge-neighbor'"
            ).fetchone()
        self.assertEqual(source["content_status"], "expired")
        self.assertEqual(source["content_purge_state"], "failed")
        self.assertEqual(
            source["content_purge_error"], "mismatched_recorded_path_ignored"
        )
        self.assertEqual(neighbor["content_status"], "stored")

    def test_startup_removes_only_abandoned_partial_photo_files(self):
        photo_root = self.root / "restart-private-photos"
        nested = photo_root / "device" / "aa"
        nested.mkdir(parents=True)
        partial = nested / ".photo-upload-abandoned.tmp"
        unrelated = nested / "keep-me.bin"
        partial.write_bytes(b"partial-private-content")
        unrelated.write_bytes(b"not-a-photo-upload-temp")

        message_hub.MessageHubStore(
            self.root / "restart.db",
            photo_root=photo_root,
        )

        self.assertFalse(partial.exists())
        self.assertEqual(unrelated.read_bytes(), b"not-a-photo-upload-temp")

    def test_integrity_errors_and_per_device_quota_fail_closed(self):
        max_jpeg_bytes = max(len(JPEG), len(JPEG_ALTERNATE))
        small_store = message_hub.MessageHubStore(
            self.root / "small.db",
            photo_root=self.root / "small-photos",
            photo_max_bytes=max_jpeg_bytes,
            photo_device_quota_bytes=max_jpeg_bytes,
        )
        small_store.photos.authorize_session(
            DEVICE,
            {
                "authorization_session_id": "authorized-photo-session",
                "retention_expires_at": utc_after(seconds=86_400),
                "training_allowed": False,
            },
            guardian_id="photo-guardian",
        )
        first = JPEG
        second = JPEG_ALTERNATE
        original_store = self.store
        self.store = small_store
        try:
            self.ingest_metadata(camera_envelope(10, photo_id="quota-1", jpeg=first))
            self.ingest_metadata(camera_envelope(11, photo_id="quota-2", jpeg=second))
        finally:
            self.store = original_store
        small_store.photos.store_content(
            DEVICE,
            "quota-1",
            first,
            claimed_sha256=hashlib.sha256(first).hexdigest(),
            transport="lte",
        )
        with self.assertRaises(message_hub.PhotoStoreError) as quota:
            small_store.photos.store_content(
                DEVICE,
                "quota-2",
                second,
                claimed_sha256=hashlib.sha256(second).hexdigest(),
                transport="lte",
            )
        self.assertEqual((quota.exception.code, quota.exception.status), ("photo_quota_exceeded", 507))
        with self.assertRaises(message_hub.PhotoStoreError) as invalid:
            small_store.photos.store_content(
                DEVICE,
                "quota-2",
                second[:-2] + b"xx",
                claimed_sha256=hashlib.sha256(second[:-2] + b"xx").hexdigest(),
                transport="lte",
            )
        self.assertEqual(invalid.exception.code, "invalid_jpeg")

    def test_failed_corrupt_repair_cannot_restore_a_false_stored_state(self):
        envelope = camera_envelope(25, photo_id="corrupt-repair-atomicity")
        self.ingest_metadata(envelope)
        stored = self.store.photos.store_content(
            DEVICE,
            "corrupt-repair-atomicity",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        with self.store.connection() as db:
            relative_path = db.execute(
                "SELECT content_relative_path FROM photo_records WHERE photo_id=?",
                ("corrupt-repair-atomicity",),
            ).fetchone()["content_relative_path"]
        path = self.store.photos.root / relative_path
        path.write_bytes(b"corrupt")
        self.store.photos.device_quota_bytes = 4

        with self.assertRaises(message_hub.PhotoStoreError) as failed_repair:
            self.store.photos.store_content(
                DEVICE,
                "corrupt-repair-atomicity",
                JPEG,
                claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
                transport="lte",
            )
        self.assertEqual(failed_repair.exception.code, "photo_quota_exceeded")
        with self.store.connection() as db:
            row = db.execute(
                "SELECT content_status FROM photo_records WHERE photo_id=?",
                ("corrupt-repair-atomicity",),
            ).fetchone()
        self.assertEqual(row["content_status"], "corrupt")
        self.assertEqual(path.read_bytes(), b"corrupt")

    def test_command_idempotency_and_ttl_use_existing_command_channel(self):
        expires_at_unix_ms = int(time.time() * 1000) + 60_000
        payload = {
            "cmd": "capture_photo_once",
            "cmd_id": "photo-command-1",
            "expires_at_unix_ms": expires_at_unix_ms,
            "payload": {
                "authorization_session_id": "authorized-photo-session",
                "retention_expires_at": self.authorization_expiry,
                "training_allowed": False,
                "trigger_reason": "web_manual",
            },
        }
        with self.assertRaises(message_hub.MessageHubError) as generic_route:
            self.store.create_command(DEVICE, payload)
        self.assertEqual(
            (generic_route.exception.code, generic_route.exception.status),
            ("photo_control_requires_guardian_binding", 403),
        )
        first = self.store.create_command(
            DEVICE, payload, photo_control_guardian_id="photo-guardian"
        )
        duplicate = self.store.create_command(
            DEVICE, payload, photo_control_guardian_id="photo-guardian"
        )
        self.assertEqual(first["cmd_id"], duplicate["cmd_id"])
        command_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/message_hub_command.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            list(Draft202012Validator(command_schema).iter_errors(first)), []
        )
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 1)
        with self.assertRaises(message_hub.MessageHubError) as conflict:
            self.store.create_command(
                DEVICE,
                {
                    **payload,
                    "payload": {
                        **payload["payload"],
                        "retention_expires_at": utc_after(seconds=120),
                    },
                },
                photo_control_guardian_id="photo-guardian",
            )
        self.assertEqual(
            (conflict.exception.code, conflict.exception.status),
            ("command_identity_conflict", 409),
        )
        raw, _ = self.store.poll_commands_raw(DEVICE)
        self.assertIn(
            f"expires_at_unix_ms={payload['expires_at_unix_ms']}".encode(), raw
        )

        expiring_at = int(time.time() * 1000) + 250
        expiring_payload = {
            "cmd": "capture_photo_once",
            "cmd_id": "photo-command-expired",
            "expires_at_unix_ms": expiring_at,
            "payload": payload["payload"],
        }
        expired = self.store.create_command(
            DEVICE,
            expiring_payload,
            photo_control_guardian_id="photo-guardian",
        )
        self.assertEqual(expired["status"], "pending")
        time.sleep(0.30)
        self.assertNotIn(
            "photo-command-expired",
            {command["cmd_id"] for command in self.store.poll_commands(DEVICE)},
        )
        statuses = {
            command["cmd_id"]: command["status"]
            for command in self.store.list_commands(DEVICE)
        }
        self.assertEqual(statuses["photo-command-expired"], "expired")
        expired_retry = self.store.create_command(
            DEVICE,
            expiring_payload,
            photo_control_guardian_id="photo-guardian",
        )
        self.assertEqual(expired_retry["status"], "expired")

    def test_raw_photo_timer_commands_are_strict_fifo_until_ack(self):
        now_ms = int(time.time() * 1000)
        session_expiry_ms = int(
            datetime.fromisoformat(
                self.authorization_expiry[:-1] + "+00:00"
            ).timestamp()
            * 1000
        )

        def timer_command(command_id, config_version, enabled):
            return {
                "cmd": "configure_photo_timer",
                "cmd_id": command_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "config_version": config_version,
                    "enabled": enabled,
                    "interval_seconds": 300,
                    "session_expires_at_unix_ms": session_expiry_ms,
                    "retention_expires_at": self.authorization_expiry,
                    "max_photos": 12,
                    "training_allowed": False,
                },
            }

        self.store.create_command(
            DEVICE,
            timer_command("timer-enable", "timer-config-enable", True),
            photo_control_guardian_id="photo-guardian",
        )
        self.store.create_command(
            DEVICE,
            timer_command("timer-stop", "timer-config-stop", False),
            photo_control_guardian_id="photo-guardian",
        )

        first, _ = self.store.poll_commands_raw(DEVICE)
        self.assertIn(b"id=timer-enable", first)
        self.assertIn(b"enabled=true", first)
        self.assertNotIn(b"timer-stop", first)
        self.ack_command(
            "timer-enable",
            "applied",
            sequence=100,
            timer_state={
                "config_version": "timer-config-enable",
                "enabled": True,
                "interval_seconds": 300,
                "session_expires_at_unix_ms": session_expiry_ms,
                "max_photos": 12,
                "captured_count": 0,
                "state_reason": "configured",
                "trusted_utc": True,
            },
        )

        second, _ = self.store.poll_commands_raw(DEVICE)
        self.assertIn(b"id=timer-stop", second)
        self.assertIn(b"enabled=false", second)
        self.assertNotIn(b"timer-enable", second)

    def test_late_ack_cannot_revive_expired_or_regress_terminal_command(self):
        expiring = self.store.create_command(
            DEVICE,
            {
                "cmd": "set_report_interval",
                "cmd_id": "terminal-expired",
                "expires_at_unix_ms": int(time.time() * 1000) + 100,
                "payload": {"interval_ms": 5000},
            },
        )
        self.assertEqual(expiring["status"], "pending")
        time.sleep(0.15)
        self.assertEqual(self.store.poll_commands(DEVICE), [])
        self.ack_command("terminal-expired", "applied", sequence=110)
        expired = {
            item["cmd_id"]: item for item in self.store.list_commands(DEVICE)
        }["terminal-expired"]
        self.assertEqual(expired["status"], "expired")

        self.store.create_command(
            DEVICE,
            {
                "cmd": "set_report_interval",
                "cmd_id": "terminal-applied",
                "payload": {"interval_ms": 5000},
            },
        )
        self.ack_command("terminal-applied", "applied", sequence=111)
        self.ack_command("terminal-applied", "pending", sequence=112)
        applied = {
            item["cmd_id"]: item for item in self.store.list_commands(DEVICE)
        }["terminal-applied"]
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["ack"]["status"], "applied")

    def test_list_aggregate_crosses_pages_and_separates_capture_from_receive_time(self):
        corrupt = camera_envelope(119, photo_id="aggregate-corrupt")
        self.ingest_metadata(corrupt)
        self.store.photos.store_content(
            DEVICE,
            "aggregate-corrupt",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )
        with self.store.connection() as db:
            corrupt_relative = db.execute(
                "SELECT content_relative_path FROM photo_records WHERE photo_id=?",
                ("aggregate-corrupt",),
            ).fetchone()["content_relative_path"]
        (self.store.photos.root / corrupt_relative).write_bytes(b"corrupt")
        with self.assertRaises(message_hub.PhotoStoreError):
            self.store.photos.content(DEVICE, "aggregate-corrupt")

        backfill = camera_envelope(120, photo_id="aggregate-backfill")
        backfill["timestamp_utc"] = utc_after(seconds=-90)
        self.ingest_metadata(backfill)

        stored = camera_envelope(121, photo_id="aggregate-stored")
        self.ingest_metadata(stored)
        self.store.photos.store_content(
            DEVICE,
            "aggregate-stored",
            JPEG,
            claimed_sha256=hashlib.sha256(JPEG).hexdigest(),
            transport="lte",
        )

        for sequence, result in ((122, "capture_failed"), (123, "not_attempted")):
            unavailable = camera_envelope(
                sequence,
                photo_id=f"aggregate-{result}",
                capture_result=result,
                local_save_status="not_attempted",
                device_upload_status="not_ready",
                media_type=None,
                width=None,
                height=None,
                byte_length=None,
                sha256=None,
                storage_kind="none",
            )
            unavailable["status"] = result
            unavailable["missing_reason"] = "camera_capture_unavailable"
            self.ingest_metadata(unavailable)

        expired = camera_envelope(124, photo_id="aggregate-expired")
        self.ingest_metadata(expired)
        with self.store.connection() as db:
            db.execute(
                "UPDATE photo_records SET retention_expires_at=? WHERE photo_id=?",
                (utc_after(seconds=-1), "aggregate-expired"),
            )

        first_page = self.store.photos.list(DEVICE, {"limit": ["2"]})
        self.assertEqual(len(first_page["photos"]), 2)
        self.assertFalse(first_page["page"]["exhausted"])
        self.assertEqual(
            first_page["aggregate"],
            {
                "record_count": 6,
                "pending_content_count": 1,
                "stored_content_count": 1,
                "corrupt_content_count": 1,
                "not_expected_count": 2,
                "expired_content_count": 1,
                "pending_content_bytes": len(JPEG),
                "stored_content_bytes": len(JPEG),
                "corrupt_content_bytes": len(JPEG),
            },
        )
        self.assertEqual(
            first_page["ordering"],
            {
                "key": "durable_record_id",
                "direction": "descending",
                "historical_backfill_can_arrive_later": True,
            },
        )

        all_records = self.store.photos.list(DEVICE, {"limit": ["10"]})["photos"]
        by_id = {record["photo_id"]: record for record in all_records}
        self.assertEqual(by_id["aggregate-corrupt"]["content"]["status"], "corrupt")
        delayed = by_id["aggregate-backfill"]
        self.assertEqual(delayed["event_utc"], backfill["timestamp_utc"])
        self.assertNotEqual(delayed["event_utc"], delayed["server_received_at"])
        self.assertTrue(delayed["backfill"]["is_backfill"])
        self.assertGreaterEqual(
            delayed["backfill"]["age_seconds"],
            delayed["backfill"]["threshold_seconds"],
        )
        immediate = by_id["aggregate-stored"]
        self.assertFalse(immediate["backfill"]["is_backfill"])
        self.assertEqual(immediate["timestamp_quality"], "gnss_synchronized")
        self.assertTrue(all(record["server_received_at"] for record in all_records))
        self.assertEqual(
            [record["row_id"] for record in all_records],
            sorted((record["row_id"] for record in all_records), reverse=True),
        )

    def test_export_is_complete_beyond_the_interactive_page_limit(self):
        retention = utc_after(seconds=3600)
        for sequence in range(200, 305):
            envelope = camera_envelope(
                sequence,
                photo_id=f"export-{sequence:03d}",
                retention_expires_at=retention,
                trigger_reason="device_timer",
                command_id="export-timer-command",
                config_version="export-timer-config-v1",
            )
            self.ingest_metadata(envelope)

        with running_hub(self.store) as base:
            code, body, _ = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/export.json"
                "?session_id=authorized-photo-session",
                token=GUARDIAN_TOKEN,
            )
        self.assertEqual(code, 200, body)
        exported = json.loads(body)
        self.assertTrue(exported["complete"])
        self.assertEqual(exported["record_count"], 105)
        self.assertEqual(len(exported["photos"]), 105)
        self.assertEqual(exported["photos"][0]["photo_id"], "export-200")
        self.assertEqual(exported["photos"][-1]["photo_id"], "export-304")
        self.assertEqual(exported["ordering"]["key"], "durable_record_id")
        self.assertEqual(exported["ordering"]["direction"], "ascending")

    def test_raw_timer_ack_response_is_identity_bound_and_first_apply_time_is_immutable(self):
        now_ms = int(time.time() * 1000)
        expiry_ms = now_ms + 30 * 60_000
        command_id = "timer-ack-wire-identity"
        command_payload = {
            "authorization_session_id": "authorized-photo-session",
            "config_version": "timer-wire-v1",
            "enabled": True,
            "interval_seconds": 300,
            "session_expires_at_unix_ms": expiry_ms,
            "retention_expires_at": self.authorization_expiry,
            "max_photos": 12,
            "training_allowed": False,
        }
        self.store.create_command(
            DEVICE,
            {
                "cmd": "configure_photo_timer",
                "cmd_id": command_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": command_payload,
            },
            photo_control_guardian_id="photo-guardian",
        )

        def raw_ack(*, sequence, captured_count, message):
            payload = (
                f"cmd_id={command_id}\n"
                "status=applied\n"
                f"message={message}\n"
                "boot-count=7\n"
                f"seq={sequence}\n"
                f"ts={utc_after(seconds=0)}\n"
                "timer-config-version=timer-wire-v1\n"
                "timer-enabled=true\n"
                "timer-interval-seconds=300\n"
                f"timer-session-expires-at-unix-ms={expiry_ms}\n"
                "timer-max-photos=12\n"
                f"timer-captured-count={captured_count}\n"
                "timer-state-reason=configured\n"
                "timer-trusted-utc=true\n"
            ).encode()
            return message_hub.build_raw_frame(
                "ack", command_id, payload, seq=sequence
            )

        initial = raw_ack(sequence=1, captured_count=0, message="initial")
        initial_sha = hashlib.sha256(initial).hexdigest()
        path = f"/api/v1/devices/{DEVICE}/commands/{command_id}/ack.raw"
        headers = {
            "Content-Type": "text/x-egolink-frame; profile=raw-frame.p0.v1"
        }
        with running_hub(self.store) as base:
            first = http(
                base,
                path,
                body=initial,
                token=UPLOAD_TOKEN,
                headers=headers,
            )
            with self.store.connection() as db:
                first_ack_at = db.execute(
                    "SELECT ack_at FROM commands WHERE cmd_id=?", (command_id,)
                ).fetchone()[0]

            duplicate = http(
                base,
                path,
                body=initial,
                token=UPLOAD_TOKEN,
                headers=headers,
            )
            refresh = raw_ack(sequence=2, captured_count=1, message="refresh")
            refresh_sha = hashlib.sha256(refresh).hexdigest()
            refreshed = http(
                base,
                path,
                body=refresh,
                token=UPLOAD_TOKEN,
                headers=headers,
            )
            conflict = raw_ack(sequence=1, captured_count=0, message="conflict")
            conflicted = http(
                base,
                path,
                body=conflict,
                token=UPLOAD_TOKEN,
                headers=headers,
            )
            with self.store.connection() as db:
                final_row = db.execute(
                    "SELECT ack_at,ack_json FROM commands WHERE cmd_id=?",
                    (command_id,),
                ).fetchone()

        first_body = json.loads(first[1])
        response_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/message_hub_ack_raw_response.schema.json"
            ).read_text(encoding="utf-8")
        )
        response_validator = Draft202012Validator(response_schema)
        for response in (first, duplicate, refreshed, conflicted):
            self.assertEqual(
                list(response_validator.iter_errors(json.loads(response[1]))), []
            )
        self.assertEqual(first[0], 200, first[1])
        self.assertEqual(first_body["command_ack"]["disposition"], "newly_applied")
        self.assertEqual(first_body["command_ack"]["command_status"], "applied")
        self.assertEqual(first_body["command_ack"]["posted_ack_sha256"], initial_sha)
        self.assertEqual(first_body["command_ack"]["accepted_ack_sha256"], initial_sha)
        self.assertEqual(first[2]["Cache-Control"], "no-store")

        duplicate_outcome = json.loads(duplicate[1])["command_ack"]
        self.assertEqual(
            duplicate_outcome["disposition"], "idempotent_already_applied"
        )
        self.assertEqual(duplicate_outcome["accepted_ack_sha256"], initial_sha)

        refresh_outcome = json.loads(refreshed[1])["command_ack"]
        self.assertEqual(refresh_outcome["disposition"], "refresh_applied")
        self.assertEqual(refresh_outcome["accepted_ack_sha256"], refresh_sha)
        conflict_outcome = json.loads(conflicted[1])["command_ack"]
        self.assertEqual(conflict_outcome["disposition"], "conflict_ignored")
        self.assertEqual(conflict_outcome["accepted_ack_sha256"], refresh_sha)
        self.assertNotEqual(
            conflict_outcome["posted_ack_sha256"],
            conflict_outcome["accepted_ack_sha256"],
        )
        self.assertEqual(final_row["ack_at"], first_ack_at)
        final_ack = json.loads(final_row["ack_json"])
        self.assertEqual(final_ack["accepted_ack_sha256"], refresh_sha)

    def test_device_ack_cannot_spoof_server_owned_outcome_fields(self):
        command = self.store.create_command(
            DEVICE,
            {"cmd": "set_report_interval", "payload": {"interval_ms": 5000}},
        )
        spoofed = {
            "protocol_version": "egolink.p0.v1",
            "device_id": DEVICE,
            "ts": utc_after(seconds=0),
            "seq": 1,
            "message_type": "ack",
            "cmd_id": command["cmd_id"],
            "status": "ok",
            "server_disposition": "terminal_ack_applied",
        }
        ack_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/message_hub_ack.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(list(Draft202012Validator(ack_schema).iter_errors(spoofed)))
        with self.assertRaises(message_hub.MessageHubError) as raised:
            self.store.ingest(
                DEVICE,
                "ack",
                spoofed,
            )
        self.assertEqual(raised.exception.code, "ack_reserved_field")

    def test_camera_source_status_is_indexed_only_when_strict_and_bound(self):
        now_ms = int(time.time() * 1000)
        expiry_ms = now_ms + 30 * 60_000
        command_id = "timer-source-status-bound"
        timer_state = {
            "config_version": "timer-status-v1",
            "enabled": True,
            "interval_seconds": 300,
            "session_expires_at_unix_ms": expiry_ms,
            "max_photos": 12,
            "captured_count": 0,
            "state_reason": "configured",
            "trusted_utc": True,
        }
        self.store.create_command(
            DEVICE,
            {
                "cmd": "configure_photo_timer",
                "cmd_id": command_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "config_version": timer_state["config_version"],
                    "enabled": timer_state["enabled"],
                    "interval_seconds": timer_state["interval_seconds"],
                    "session_expires_at_unix_ms": timer_state[
                        "session_expires_at_unix_ms"
                    ],
                    "retention_expires_at": self.authorization_expiry,
                    "max_photos": timer_state["max_photos"],
                    "training_allowed": False,
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        self.ack_command(
            command_id,
            "applied",
            sequence=1,
            timer_state=timer_state,
        )

        malformed = camera_source_status_envelope(
            610,
            command_id=command_id,
            authorization_session_id="authorized-photo-session",
            timer_state=dict(timer_state),
        )
        malformed["payload"]["capture_trigger_wired"] = "true"
        malformed_result = self.ingest_collection(malformed)
        self.assertEqual(malformed_result["parse_status"], "parse_error")
        self.assertIsNone(self.store.collection.latest_source_state(DEVICE, "camera"))

        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/collection_observation.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(
            list(Draft202012Validator(schema).iter_errors(malformed)),
            "the shared schema must reject string booleans too",
        )

        valid = camera_source_status_envelope(
            611,
            command_id=command_id,
            authorization_session_id="authorized-photo-session",
            timer_state=dict(timer_state),
        )
        valid_result = self.ingest_collection(valid)
        self.assertEqual(valid_result["parse_status"], "ok")
        latest = self.store.collection.latest_source_state(DEVICE, "camera")
        self.assertEqual(
            latest["envelope"]["observation_id"], valid["observation_id"]
        )

        stale = camera_source_status_envelope(
            612,
            command_id="unknown-timer-command",
            authorization_session_id="authorized-photo-session",
            timer_state=dict(timer_state),
        )
        stale_result = self.ingest_collection(stale)
        self.assertEqual(stale_result["parse_status"], "parse_error")
        self.assertEqual(
            self.store.collection.latest_source_state(DEVICE, "camera")[
                "envelope"
            ]["observation_id"],
            valid["observation_id"],
        )

    def test_one_shot_identity_and_timer_max_photos_are_server_enforced(self):
        now_ms = int(time.time() * 1000)
        one_shot_id = "server-bound-one-shot"
        self.store.create_command(
            DEVICE,
            {
                "cmd": "capture_photo_once",
                "cmd_id": one_shot_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "retention_expires_at": self.authorization_expiry,
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        first = camera_envelope(
            620,
            photo_id="one-shot-first",
            command_id=one_shot_id,
            retention_expires_at=self.authorization_expiry,
        )
        second = camera_envelope(
            621,
            photo_id="one-shot-second",
            command_id=one_shot_id,
            retention_expires_at=self.authorization_expiry,
        )
        self.ingest_collection(first)
        with self.assertRaises(message_hub.CollectionError) as one_shot_rejected:
            self.ingest_collection(second)
        self.assertEqual(
            (one_shot_rejected.exception.code, one_shot_rejected.exception.status),
            ("photo_command_already_bound", 409),
        )

        timer_id = "server-bounded-timer"
        timer_config = "server-bounded-timer-v1"
        self.store.create_command(
            DEVICE,
            {
                "cmd": "configure_photo_timer",
                "cmd_id": timer_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "config_version": timer_config,
                    "enabled": True,
                    "interval_seconds": 300,
                    "session_expires_at_unix_ms": now_ms + 30 * 60_000,
                    "retention_expires_at": self.authorization_expiry,
                    "max_photos": 1,
                    "training_allowed": False,
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        timer_first = camera_envelope(
            622,
            photo_id="timer-first",
            trigger_reason="device_timer",
            command_id=timer_id,
            config_version=timer_config,
            retention_expires_at=self.authorization_expiry,
        )
        timer_second = camera_envelope(
            623,
            photo_id="timer-second",
            trigger_reason="device_timer",
            command_id=timer_id,
            config_version=timer_config,
            retention_expires_at=self.authorization_expiry,
        )
        self.ingest_collection(timer_first)
        with self.assertRaises(message_hub.CollectionError) as timer_rejected:
            self.ingest_collection(timer_second)
        self.assertEqual(
            (timer_rejected.exception.code, timer_rejected.exception.status),
            ("photo_timer_limit_reached", 409),
        )

        with self.store.connection() as db:
            counts = {
                row["command_id"]: row["count"]
                for row in db.execute(
                    "SELECT command_id,COUNT(*) count FROM photo_records "
                    "WHERE command_id IN (?,?) GROUP BY command_id",
                    (one_shot_id, timer_id),
                )
            }
        self.assertEqual(counts, {one_shot_id: 1, timer_id: 1})

        contradictory_id = "terminal-error-cannot-save"
        self.store.create_command(
            DEVICE,
            {
                "cmd": "capture_photo_once",
                "cmd_id": contradictory_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "retention_expires_at": self.authorization_expiry,
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        self.ack_command(contradictory_id, "error", sequence=20)
        contradictory = camera_envelope(
            624,
            photo_id="contradictory-saved-photo",
            command_id=contradictory_id,
            retention_expires_at=self.authorization_expiry,
        )
        with self.assertRaises(message_hub.CollectionError) as contradicted:
            self.ingest_collection(contradictory)
        self.assertEqual(
            (contradicted.exception.code, contradicted.exception.status),
            ("photo_command_terminal_conflict", 409),
        )

        failed_id = "terminal-error-with-failure-result"
        self.store.create_command(
            DEVICE,
            {
                "cmd": "capture_photo_once",
                "cmd_id": failed_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "retention_expires_at": self.authorization_expiry,
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        self.ack_command(failed_id, "error", sequence=21)
        failed = camera_envelope(
            625,
            photo_id="truthful-failed-photo",
            command_id=failed_id,
            retention_expires_at=self.authorization_expiry,
            capture_result="capture_failed",
            local_save_status="not_attempted",
            device_upload_status="not_ready",
            media_type=None,
            width=None,
            height=None,
            byte_length=None,
            sha256=None,
            storage_kind="none",
        )
        failed["status"] = "capture_failed"
        failed["missing_reason"] = "camera_capture_failed"
        self.assertEqual(self.ingest_collection(failed)["parse_status"], "ok")

    def test_concurrent_one_shot_outcomes_commit_only_one_identity(self):
        now_ms = int(time.time() * 1000)
        command_id = "concurrent-one-shot"
        self.store.create_command(
            DEVICE,
            {
                "cmd": "capture_photo_once",
                "cmd_id": command_id,
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": {
                    "authorization_session_id": "authorized-photo-session",
                    "retention_expires_at": self.authorization_expiry,
                    "training_allowed": False,
                    "trigger_reason": "web_manual",
                },
            },
            photo_control_guardian_id="photo-guardian",
        )
        envelopes = [
            camera_envelope(
                sequence,
                photo_id=f"concurrent-photo-{sequence}",
                command_id=command_id,
                retention_expires_at=self.authorization_expiry,
            )
            for sequence in (630, 631)
        ]
        barrier = threading.Barrier(3)
        outcomes = []
        outcome_lock = threading.Lock()

        def submit(envelope):
            barrier.wait()
            try:
                result = ("accepted", self.ingest_collection(envelope)["result"])
            except message_hub.CollectionError as failure:
                result = ("rejected", failure.code)
            with outcome_lock:
                outcomes.append(result)

        workers = [threading.Thread(target=submit, args=(value,)) for value in envelopes]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

        self.assertEqual(
            sorted(outcomes),
            [
                ("accepted", "accepted"),
                ("rejected", "photo_command_already_bound"),
            ],
        )
        with self.store.connection() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM photo_records WHERE command_id=?",
                    (command_id,),
                ).fetchone()[0],
                1,
            )

    def test_late_terminal_ack_must_match_already_persisted_photo_outcome(self):
        now_ms = int(time.time() * 1000)

        def create_one_shot(command_id):
            self.store.create_command(
                DEVICE,
                {
                    "cmd": "capture_photo_once",
                    "cmd_id": command_id,
                    "expires_at_unix_ms": now_ms + 60_000,
                    "payload": {
                        "authorization_session_id": "authorized-photo-session",
                        "retention_expires_at": self.authorization_expiry,
                        "training_allowed": False,
                        "trigger_reason": "web_manual",
                    },
                },
                photo_control_guardian_id="photo-guardian",
            )

        saved_id = "late-ack-saved"
        create_one_shot(saved_id)
        saved = camera_envelope(
            640,
            photo_id="late-ack-saved-photo",
            command_id=saved_id,
            retention_expires_at=self.authorization_expiry,
        )
        self.ingest_collection(saved)
        with self.assertRaises(message_hub.MessageHubError) as wrong_error:
            self.ack_command(saved_id, "error", sequence=30)
        self.assertEqual(wrong_error.exception.code, "photo_command_ack_conflict")
        self.ack_command(saved_id, "ok", sequence=31)

        failed_id = "late-ack-failed"
        create_one_shot(failed_id)
        failed = camera_envelope(
            641,
            photo_id="late-ack-failed-photo",
            command_id=failed_id,
            retention_expires_at=self.authorization_expiry,
            capture_result="capture_failed",
            local_save_status="not_attempted",
            device_upload_status="not_ready",
            media_type=None,
            width=None,
            height=None,
            byte_length=None,
            sha256=None,
            storage_kind="none",
        )
        failed["status"] = "capture_failed"
        failed["missing_reason"] = "camera_capture_failed"
        self.ingest_collection(failed)
        with self.assertRaises(message_hub.MessageHubError) as wrong_ok:
            self.ack_command(failed_id, "ok", sequence=32)
        self.assertEqual(wrong_ok.exception.code, "photo_command_ack_conflict")
        self.ack_command(failed_id, "error", sequence=33)

        invalid_kind_id = "manual-applied-is-never-valid"
        create_one_shot(invalid_kind_id)
        with self.assertRaises(message_hub.MessageHubError) as applied_first:
            self.ack_command(invalid_kind_id, "applied", sequence=34)
        self.assertEqual(
            applied_first.exception.code, "photo_command_ack_status_invalid"
        )
        applied_first_photo = camera_envelope(
            642,
            photo_id="manual-applied-invalid-photo",
            command_id=invalid_kind_id,
            retention_expires_at=self.authorization_expiry,
        )
        self.ingest_collection(applied_first_photo)
        with self.assertRaises(message_hub.MessageHubError) as applied_after:
            self.ack_command(invalid_kind_id, "applied", sequence=35)
        self.assertEqual(
            applied_after.exception.code, "photo_command_ack_status_invalid"
        )
        self.ack_command(invalid_kind_id, "ok", sequence=36)

        commands = {
            command["cmd_id"]: command
            for command in self.store.list_commands(DEVICE)
        }
        self.assertEqual(commands[saved_id]["status"], "ok")
        self.assertEqual(commands[failed_id]["status"], "error")
        self.assertEqual(commands[invalid_kind_id]["status"], "ok")

    def test_camera_metadata_rejects_false_command_session_config_and_location_causality(self):
        def assert_camera_rejected(envelope, code, status):
            with self.store.connection() as db:
                before = tuple(
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("raw_frames", "collection_records", "photo_records")
                )
            with self.assertRaises(message_hub.CollectionError) as raised:
                self.ingest_metadata(envelope, seed_causality=False)
            self.assertEqual((raised.exception.code, raised.exception.status), (code, status))
            with self.store.connection() as db:
                after = tuple(
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("raw_frames", "collection_records", "photo_records")
                )
            self.assertEqual(after, before)

        location_time = utc_after(seconds=-2)
        good_location = gnss_envelope(
            400,
            observation_id="causal-location-good",
            event_utc=location_time,
        )
        self.ingest_collection(good_location)
        causal = camera_envelope(401, photo_id="causal-good")
        causal["timestamp_utc"] = utc_after(seconds=-1)
        causal["payload"]["location_ref"] = {
            "observation_id": "causal-location-good",
            "event_utc": location_time,
            "timestamp_quality": "gnss_synchronized",
        }
        self.ingest_metadata(causal)
        resolved = self.store.photos.metadata(DEVICE, "causal-good")[
            "resolved_location_ref"
        ]
        self.assertEqual(resolved["observation_id"], "causal-location-good")
        self.assertGreaterEqual(resolved["age_at_capture_seconds"], 0)

        missing_command = camera_envelope(410, photo_id="missing-command")
        assert_camera_rejected(
            missing_command, "photo_command_not_found", 403
        )

        wrong_command = camera_envelope(411, photo_id="wrong-command")
        self.store.create_command(
            DEVICE,
            {
                "cmd": "set_report_interval",
                "cmd_id": wrong_command["payload"]["command_id"],
                "expires_at_unix_ms": int(time.time() * 1000) + 60_000,
                "payload": {"interval_ms": 5000},
            },
        )
        assert_camera_rejected(wrong_command, "photo_command_mismatch", 403)

        session_mismatch = camera_envelope(412, photo_id="session-mismatch")
        self.create_matching_photo_command(session_mismatch)
        second_retention = session_mismatch["payload"]["retention_expires_at"]
        self.store.photos.authorize_session(
            DEVICE,
            {
                "authorization_session_id": "second-causal-session",
                "retention_expires_at": self.authorization_expiry,
                "training_allowed": False,
            },
            guardian_id="photo-guardian",
        )
        session_mismatch["session_id"] = "second-causal-session"
        session_mismatch["payload"][
            "authorization_session_id"
        ] = "second-causal-session"
        session_mismatch["payload"]["retention_expires_at"] = second_retention
        assert_camera_rejected(
            session_mismatch, "photo_command_mismatch", 403
        )

        timer_config_mismatch = camera_envelope(
            413,
            photo_id="timer-config-mismatch",
            trigger_reason="device_timer",
            config_version="timer-config-issued",
        )
        self.create_matching_photo_command(timer_config_mismatch)
        timer_config_mismatch["payload"]["config_version"] = "timer-config-other"
        assert_camera_rejected(
            timer_config_mismatch, "photo_timer_config_mismatch", 403
        )

        untrusted_timer = camera_envelope(
            414,
            photo_id="timer-time-untrusted",
            trigger_reason="device_timer",
            config_version="timer-config-untrusted",
        )
        untrusted_timer["timestamp_utc"] = None
        untrusted_timer["timestamp_source"] = "unavailable"
        untrusted_timer["timestamp_quality"] = "unknown"
        self.create_matching_photo_command(untrusted_timer)
        assert_camera_rejected(untrusted_timer, "photo_time_untrusted", 403)

        asserted_but_untrusted_timer = camera_envelope(
            419,
            photo_id="timer-time-asserted-but-untrusted",
            trigger_reason="device_timer",
            config_version="timer-config-asserted-untrusted",
        )
        asserted_but_untrusted_timer["timestamp_source"] = "unavailable"
        asserted_but_untrusted_timer["timestamp_quality"] = "unknown"
        self.create_matching_photo_command(asserted_but_untrusted_timer)
        assert_camera_rejected(
            asserted_but_untrusted_timer, "photo_time_untrusted", 403
        )

        future_timer = camera_envelope(
            424,
            photo_id="timer-time-too-far-in-future",
            trigger_reason="device_timer",
            config_version="timer-config-future",
        )
        future_timer["timestamp_utc"] = utc_after(seconds=300)
        self.create_matching_photo_command(future_timer)
        assert_camera_rejected(
            future_timer, "photo_time_outside_authorization", 403
        )

        outside_window = camera_envelope(415, photo_id="outside-command-window")
        outside_window["timestamp_utc"] = utc_after(seconds=300)
        self.create_matching_photo_command(outside_window)
        assert_camera_rejected(
            outside_window, "photo_time_outside_authorization", 403
        )

        missing_location = camera_envelope(416, photo_id="missing-location")
        missing_location["payload"]["location_ref"] = {
            "observation_id": "location-does-not-exist",
            "event_utc": utc_after(seconds=-2),
            "timestamp_quality": "gnss_synchronized",
        }
        self.create_matching_photo_command(missing_location)
        assert_camera_rejected(
            missing_location, "photo_location_not_found", 422
        )

        no_fix_time = utc_after(seconds=-2)
        self.ingest_collection(
            gnss_envelope(
                417,
                observation_id="causal-location-no-fix",
                event_utc=no_fix_time,
                fix=False,
            )
        )
        mismatched_location = camera_envelope(418, photo_id="location-not-fix")
        mismatched_location["payload"]["location_ref"] = {
            "observation_id": "causal-location-no-fix",
            "event_utc": no_fix_time,
            "timestamp_quality": "gnss_synchronized",
        }
        self.create_matching_photo_command(mismatched_location)
        assert_camera_rejected(
            mismatched_location, "photo_location_mismatch", 422
        )

        future_location_time = utc_after(seconds=-1)
        self.ingest_collection(
            gnss_envelope(
                419,
                observation_id="causal-location-after-photo",
                event_utc=future_location_time,
            )
        )
        location_after_capture = camera_envelope(
            420, photo_id="location-after-capture"
        )
        location_after_capture["timestamp_utc"] = utc_after(seconds=-10)
        location_after_capture["payload"]["location_ref"] = {
            "observation_id": "causal-location-after-photo",
            "event_utc": future_location_time,
            "timestamp_quality": "gnss_synchronized",
        }
        self.create_matching_photo_command(location_after_capture)
        assert_camera_rejected(
            location_after_capture, "photo_location_after_capture", 422
        )

    def test_photo_control_routes_are_guardian_bound_and_timer_state_is_truthful(self):
        capture_request = {
            "cmd_id": "web-photo-capture-001",
            "expires_at_unix_ms": int(time.time() * 1000) + 60_000,
            "payload": {
                "authorization_session_id": "authorized-photo-session",
                "retention_expires_at": self.authorization_expiry,
                "training_allowed": False,
                "trigger_reason": "web_manual",
            },
        }
        timer_request = {
            "cmd_id": "web-photo-timer-001",
            "expires_at_unix_ms": int(time.time() * 1000) + 60_000,
            "payload": {
                "authorization_session_id": "authorized-photo-session",
                "config_version": "photo-control-v0.1-test",
                "enabled": True,
                "interval_seconds": 300,
                "session_expires_at_unix_ms": int(
                    datetime.fromisoformat(
                        self.authorization_expiry[:-1] + "+00:00"
                    ).timestamp()
                    * 1000
                ),
                "retention_expires_at": self.authorization_expiry,
                "max_photos": 12,
                "training_allowed": False,
            },
        }
        headers = {"Content-Type": "application/json"}
        capture_path = f"/api/v1/devices/{DEVICE}/photos/commands/capture"
        timer_path = f"/api/v1/devices/{DEVICE}/photos/commands/timer"
        with running_hub(self.store) as base:
            device_token_rejected = http(
                base,
                capture_path,
                body=json.dumps(capture_request).encode(),
                headers=headers,
                token=UPLOAD_TOKEN,
            )
            wrong_binding_rejected = http(
                base,
                capture_path,
                body=json.dumps(capture_request).encode(),
                headers=headers,
                token=OTHER_GUARDIAN_TOKEN,
            )
            generic_rejected = http(
                base,
                f"/api/v1/devices/{DEVICE}/commands",
                body=json.dumps({"cmd": "capture_photo_once", **capture_request}).encode(),
                headers=headers,
                token=UPLOAD_TOKEN,
            )
            with self.store.connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 0)
            accepted = http(
                base,
                capture_path,
                body=json.dumps(capture_request).encode(),
                headers=headers,
                token=GUARDIAN_TOKEN,
            )
            duplicate = http(
                base,
                capture_path,
                body=json.dumps(capture_request).encode(),
                headers=headers,
                token=GUARDIAN_TOKEN,
            )
            timer = http(
                base,
                timer_path,
                body=json.dumps(timer_request).encode(),
                headers=headers,
                token=GUARDIAN_TOKEN,
            )
            command_state = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/commands",
                token=GUARDIAN_TOKEN,
            )
            timer_ack = http(
                base,
                f"/api/v1/devices/{DEVICE}/commands/web-photo-timer-001/ack",
                body=json.dumps(
                    {
                        "protocol_version": "egolink.p0.v1",
                        "device_id": DEVICE,
                        "ts": utc_after(seconds=1),
                        "seq": 1,
                        "message_type": "ack",
                        "cmd_id": "web-photo-timer-001",
                        "status": "applied",
                        "timer_state": {
                            "config_version": "photo-control-v0.1-test",
                            "enabled": True,
                            "interval_seconds": 300,
                            "session_expires_at_unix_ms": timer_request["payload"][
                                "session_expires_at_unix_ms"
                            ],
                            "max_photos": 12,
                            "captured_count": 0,
                            "state_reason": "configured",
                            "trusted_utc": True,
                        },
                    }
                ).encode(),
                headers=headers,
                token=UPLOAD_TOKEN,
            )
            applied_state = http(
                base,
                f"/api/v1/devices/{DEVICE}/photos/commands",
                token=GUARDIAN_TOKEN,
            )
        self.assertEqual(device_token_rejected[0], 401)
        self.assertEqual(wrong_binding_rejected[0], 403)
        self.assertEqual(generic_rejected[0], 403)
        self.assertEqual(accepted[0], 200, accepted[1])
        self.assertEqual(duplicate[0], 200, duplicate[1])
        self.assertEqual(timer[0], 200, timer[1])
        self.assertEqual(timer_ack[0], 200, timer_ack[1])
        self.assertEqual(json.loads(accepted[1])["command"]["status"], "pending")
        self.assertEqual(
            json.loads(duplicate[1])["command"]["cmd_id"],
            "web-photo-capture-001",
        )
        commands = json.loads(command_state[1])["commands"]
        command_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/message_hub_command.schema.json"
            ).read_text(encoding="utf-8")
        )
        timer_command = json.loads(timer[1])["command"]
        self.assertEqual(
            list(Draft202012Validator(command_schema).iter_errors(timer_command)), []
        )
        ack_schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared/contracts/message_hub_ack.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            list(
                Draft202012Validator(ack_schema).iter_errors(
                    {
                        "protocol_version": "egolink.p0.v1",
                        "device_id": DEVICE,
                        "ts": utc_after(seconds=1),
                        "seq": 1,
                        "message_type": "ack",
                        "cmd_id": "web-photo-timer-001",
                        "status": "applied",
                        "timer_state": {
                            "config_version": "photo-control-v0.1-test",
                            "enabled": True,
                            "interval_seconds": 300,
                            "session_expires_at_unix_ms": timer_request["payload"][
                                "session_expires_at_unix_ms"
                            ],
                            "max_photos": 12,
                            "captured_count": 0,
                            "state_reason": "configured",
                            "trusted_utc": True,
                        },
                    }
                )
            ),
            [],
        )
        self.assertEqual(
            {command["cmd"] for command in commands},
            {"capture_photo_once", "configure_photo_timer"},
        )
        self.assertTrue(all(command["status"] == "pending" for command in commands))
        applied_commands = {
            command["cmd_id"]: command
            for command in json.loads(applied_state[1])["commands"]
        }
        self.assertEqual(applied_commands["web-photo-timer-001"]["status"], "applied")
        self.assertEqual(
            applied_commands["web-photo-timer-001"]["ack"]["status"], "applied"
        )
        self.assertEqual(command_state[2]["Cache-Control"], "no-store")
        raw, _ = self.store.poll_commands_raw(DEVICE)
        self.assertIn(b"training_allowed=false", raw)

    def test_applied_timer_control_supersedes_only_later_capture_events(self):
        before_stop = camera_envelope(
            421,
            photo_id="timer-before-stop",
            trigger_reason="device_timer",
            command_id="timer-enable-before-stop",
            config_version="timer-config-before-stop",
        )
        before_stop["timestamp_utc"] = utc_after(seconds=-2)
        self.create_matching_photo_command(before_stop)

        now_ms = int(time.time() * 1000)
        retention_ms = int(
            datetime.fromisoformat(
                self.authorization_expiry[:-1] + "+00:00"
            ).timestamp()
            * 1000
        )
        stop_payload = {
            "authorization_session_id": "authorized-photo-session",
            "config_version": "timer-config-stopped",
            "enabled": False,
            "interval_seconds": 300,
            "session_expires_at_unix_ms": min(retention_ms, now_ms + 1_800_000),
            "retention_expires_at": self.authorization_expiry,
            "max_photos": 288,
            "training_allowed": False,
        }
        self.store.create_command(
            DEVICE,
            {
                "cmd": "configure_photo_timer",
                "cmd_id": "timer-stop-applied",
                "expires_at_unix_ms": now_ms + 60_000,
                "payload": stop_payload,
            },
            photo_control_guardian_id="photo-guardian",
        )
        self.ack_command(
            "timer-stop-applied",
            "applied",
            sequence=421,
            timer_state={
                "config_version": stop_payload["config_version"],
                "enabled": False,
                "interval_seconds": stop_payload["interval_seconds"],
                "session_expires_at_unix_ms": stop_payload[
                    "session_expires_at_unix_ms"
                ],
                "max_photos": stop_payload["max_photos"],
                "captured_count": 0,
                "state_reason": "stopped",
                "trusted_utc": True,
            },
        )

        accepted_backfill = self.ingest_metadata(before_stop, seed_causality=False)
        self.assertEqual(accepted_backfill["result"], "accepted")

        after_stop = camera_envelope(
            422,
            photo_id="timer-after-stop",
            trigger_reason="device_timer",
            command_id="timer-enable-before-stop",
            config_version="timer-config-before-stop",
            retention_expires_at=before_stop["payload"]["retention_expires_at"],
        )
        after_stop["timestamp_utc"] = utc_after(seconds=1)
        with self.assertRaises(message_hub.CollectionError) as superseded:
            self.ingest_metadata(after_stop, seed_causality=False)
        self.assertEqual(superseded.exception.code, "photo_timer_superseded")

    def test_non_applied_timer_ack_cannot_report_effective_timer_state(self):
        envelope = camera_envelope(
            423,
            photo_id="timer-error-ack",
            trigger_reason="device_timer",
            command_id="timer-error-command",
            config_version="timer-error-config",
        )
        self.create_matching_photo_command(envelope)
        with self.assertRaises(message_hub.MessageHubError) as invalid_ack:
            self.ack_command(
                "timer-error-command",
                "error",
                sequence=423,
                timer_state={
                    "config_version": "bogus",
                    "enabled": False,
                    "interval_seconds": 300,
                    "session_expires_at_unix_ms": int(time.time() * 1000) + 60_000,
                    "max_photos": 1,
                    "captured_count": 0,
                    "state_reason": "error",
                    "trusted_utc": False,
                },
            )
        self.assertEqual(invalid_ack.exception.code, "photo_timer_ack_state_invalid")
        command = {
            item["cmd_id"]: item for item in self.store.list_commands(DEVICE)
        }["timer-error-command"]
        self.assertEqual(command["status"], "pending")
        self.assertIsNone(command.get("ack"))

    def test_dashboard_photo_controls_use_separate_guardian_session_token(self):
        html = message_hub.render_dashboard()
        for required in (
            'id="capturePhotoOnce"',
            'id="photoTimerEnabled"',
            'id="photoTimerInterval"',
            'id="photoRetentionDeadline"',
            'id="photoSessionFilter"',
            'id="photoPreview"',
            'id="exportPhotos"',
            "capture_photo_once",
            "configure_photo_timer",
            "runtimeMatchesApplied",
            "latestAppliedTimerCommand",
            "在设备 ACK 前，上述已验证实际配置仍然有效",
            "reportedTimer.session_expires_at_unix_ms",
            "授权会话截止已过；等待设备状态确认",
            "terminal_ack_applied",
            "corrupt_content_count",
            "await image.decode()",
            "previewGeneration !== photoPreviewGeneration",
            "content.verification_scope",
            "sessionStorage.getItem('egolinkPhotoGuardianToken')",
            "设备实际配置仍为未报告",
            "待设备执行；尚未 ACK",
        ):
            self.assertIn(required, html)
        self.assertIn("headers: {...photoAuthHeaders()", html)

    def test_general_backup_excludes_private_jpegs_to_preserve_item_retention(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts/ops/egolink_backup.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("umask 077", script)
        tar_inputs = script[script.index("TAR_INPUTS=") : script.index("tar ")]
        self.assertNotIn("${PHOTOS#/}", tar_inputs)
        self.assertNotIn('TAR_INPUTS+=(-C / "${PHOTOS#/}")', script)
        self.assertIn("private jpeg", script.lower())
        self.assertIn("retention", script.lower())

    def test_existing_runtime_database_copy_migrates_without_losing_rows(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "server/runtime/message_hub.db"
        )
        if not source.exists():
            self.skipTest("repository-local legacy runtime database is unavailable")
        migrated = self.root / "legacy-copy.db"
        shutil.copy2(source, migrated)
        with closing(sqlite3.connect(migrated)) as db:
            before = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("devices", "messages", "commands")
            }
        reopened = message_hub.MessageHubStore(
            migrated, photo_root=self.root / "legacy-copy-photos"
        )
        with reopened.connection() as db:
            after = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("devices", "messages", "commands")
            }
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertEqual(after, before)
        self.assertIn("photo_records", tables)
        self.assertIn("photo_capture_sessions", tables)
        self.assertEqual(reopened.photos.root, (self.root / "legacy-copy-photos").resolve())


if __name__ == "__main__":
    unittest.main()
