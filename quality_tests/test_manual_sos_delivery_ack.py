from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request
from urllib.parse import urlparse

from quality_tests.test_manual_sos_store import (
    DEVICE_ID,
    manual_sos_document,
    manual_sos_raw,
)
from server import message_hub
from server.guardian_device_authorization import (
    CONTRACT_VERSION,
    GuardianDeviceAuthorizer,
    token_sha256,
)
from server.manual_sos_delivery_ack import (
    ACK_CONTRACT_VERSION,
    DELIVERY_SCOPE,
    ManualSosDeliveryAckError,
    build_manual_sos_delivery_ack,
)
from server.guardian_location_page import (
    GUARDIAN_LOCATION_HTML,
    GUARDIAN_LOCATION_JS,
)


DEVICE_TOKEN = "device-ingest-token"
GUARDIAN_TOKEN = "guardian-test-token-0001"
OTHER_DEVICE = "wearable-node-002"


def guardian_authorizer() -> GuardianDeviceAuthorizer:
    return GuardianDeviceAuthorizer(
        {
            "contract_version": CONTRACT_VERSION,
            "bindings": [
                {
                    "guardian_id": "guardian-001",
                    "token_sha256": token_sha256(GUARDIAN_TOKEN),
                    "device_ids": [DEVICE_ID],
                }
            ],
        }
    )


@contextmanager
def running_hub(
    db_path: Path,
    *,
    token: str | None = DEVICE_TOKEN,
    authorizer: GuardianDeviceAuthorizer | None = None,
):
    store = message_hub.MessageHubStore(db_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        message_hub.make_handler(
            store,
            token=token,
            guardian_authorizer=authorizer,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def post_raw(
    base_url: str,
    path: str,
    body: bytes,
    *,
    token: str | None = DEVICE_TOKEN,
    content_type: str = "application/json",
) -> tuple[dict[str, object], str | None]:
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        base_url + path,
        data=body,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return (
            json.loads(response.read().decode("utf-8")),
            response.headers.get("Cache-Control"),
        )


def guardian_get(base_url: str, path: str, token: str = GUARDIAN_TOKEN):
    req = request.Request(
        base_url + path,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with request.urlopen(req, timeout=5) as response:
        return (
            json.loads(response.read().decode("utf-8")),
            response.headers.get("Cache-Control"),
        )


def guardian_ack(base_url: str, event_id: str, *, body: bytes = b""):
    req = request.Request(
        base_url
        + f"/api/v1/devices/{DEVICE_ID}/safety-events/manual-sos/"
        + f"{event_id}/guardian-ack",
        data=body,
        headers={"Authorization": f"Bearer {GUARDIAN_TOKEN}"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return (
            json.loads(response.read().decode("utf-8")),
            response.headers.get("Cache-Control"),
        )


class ManualSosDeliveryAckTests(unittest.TestCase):
    def test_guardian_page_queries_both_views_without_persisting_or_interpolating_data(self) -> None:
        self.assertIn('id="sos-alert-title"', GUARDIAN_LOCATION_HTML)
        self.assertIn("/safety-events/manual-sos/latest", GUARDIAN_LOCATION_JS)
        self.assertIn("Promise.all", GUARDIAN_LOCATION_JS)
        self.assertIn("renderSosAlert", GUARDIAN_LOCATION_JS)
        self.assertIn("textContent", GUARDIAN_LOCATION_JS)
        self.assertIn("guardian-token').value = ''", GUARDIAN_LOCATION_JS)
        self.assertNotIn("localStorage", GUARDIAN_LOCATION_JS)
        self.assertNotIn("sessionStorage", GUARDIAN_LOCATION_JS)
        self.assertNotIn("innerHTML", GUARDIAN_LOCATION_JS)
        self.assertNotIn("console.", GUARDIAN_LOCATION_JS)

    def test_ack_binds_exact_bytes_and_only_durable_positive_results(self) -> None:
        raw = manual_sos_raw()
        digest = hashlib.sha256(raw).hexdigest()
        result = {
            "status": "accepted",
            "identity": {
                "device_id": DEVICE_ID,
                "event_id": "sos-b7-q11-t42050",
            },
            "payload_sha256": digest,
        }
        ack = build_manual_sos_delivery_ack(raw, result, ack_time_ms=123)
        self.assertEqual(
            {
                "contract_version": ACK_CONTRACT_VERSION,
                "ack_id": "ack-" + digest,
                "device_id": DEVICE_ID,
                "event_id": "sos-b7-q11-t42050",
                "payload_sha256": digest,
                "status": "accepted",
                "ack_time_ms": 123,
            },
            ack,
        )
        for bad in (
            {**result, "status": "pending"},
            {**result, "payload_sha256": "0" * 64},
            {**result, "identity": {**result["identity"], "event_id": "bad id"}},
            {
                **result,
                "identity": {
                    **result["identity"],
                    "event_id": "sos-b7-q12-t42050",
                },
            },
        ):
            with self.assertRaises(ManualSosDeliveryAckError):
                build_manual_sos_delivery_ack(raw, bad, ack_time_ms=123)
        with self.assertRaises(ManualSosDeliveryAckError):
            build_manual_sos_delivery_ack(
                raw + b" ", result, ack_time_ms=123
            )

    def test_authenticated_ingest_returns_exact_ack_and_bound_latest_survives_restart(self) -> None:
        path = "/api/v1/safety-events/manual-sos"
        latest_path = (
            f"/api/v1/devices/{DEVICE_ID}/safety-events/manual-sos/latest"
        )
        raw = manual_sos_raw(battery_percent=None)
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(
                db_path, authorizer=guardian_authorizer()
            ) as base:
                accepted, accepted_cache = post_raw(base, path, raw)
                duplicate, duplicate_cache = post_raw(base, path, raw)
                latest, latest_cache = guardian_get(base, latest_path)

            with running_hub(
                db_path, authorizer=guardian_authorizer()
            ) as base:
                restarted, restarted_cache = guardian_get(base, latest_path)

        for response in (accepted, duplicate):
            ack = response["delivery_ack"]
            self.assertEqual("ack-" + digest, ack["ack_id"])
            self.assertEqual(digest, ack["payload_sha256"])
            self.assertEqual(DEVICE_ID, ack["device_id"])
            self.assertEqual("sos-b7-q11-t42050", ack["event_id"])
            self.assertEqual("accepted", ack["status"])
            self.assertEqual(DELIVERY_SCOPE, response["delivery_scope"])
        self.assertEqual("accepted", accepted["result"]["status"])
        self.assertEqual("duplicate", duplicate["result"]["status"])
        self.assertEqual("no-store", accepted_cache)
        self.assertEqual("no-store", duplicate_cache)
        self.assertEqual("no-store", latest_cache)
        self.assertEqual("no-store", restarted_cache)
        self.assertEqual(latest, restarted)
        alert = latest["manual_sos_alert"]
        self.assertTrue(alert["available"])
        self.assertIsNone(alert["battery"]["percent"])
        self.assertEqual("not_acknowledged", alert["guardian_ack_state"])
        self.assertEqual("not_reported", alert["call_state"])
        serialized = json.dumps(alert, sort_keys=True)
        for forbidden in (
            "raw_payload",
            "audio_clip_ref",
            "image_ref",
            "latitude",
            "longitude",
            "coordinate",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_ingest_auth_and_parser_fail_before_mutation_and_errors_are_no_store(self) -> None:
        path = "/api/v1/safety-events/manual-sos"
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(db_path, authorizer=guardian_authorizer()) as base:
                failures: list[tuple[bytes, str | None, str, int]] = [
                    (b"{}", None, "application/json", 401),
                    (b"{}", "wrong-device-token", "application/json", 401),
                    (b"{}", DEVICE_TOKEN, "text/plain", 415),
                    (b"{" + b" " * 1024, DEVICE_TOKEN, "application/json", 413),
                    (
                        manual_sos_raw().replace(
                            b'"priority":"critical"',
                            b'"priority":"critical","priority":"critical"',
                        ),
                        DEVICE_TOKEN,
                        "application/json",
                        422,
                    ),
                ]
                for body, token, content_type, expected in failures:
                    with self.subTest(expected=expected, content_type=content_type):
                        with self.assertRaises(error.HTTPError) as rejected:
                            post_raw(
                                base,
                                path,
                                body,
                                token=token,
                                content_type=content_type,
                            )
                        response_body = json.loads(
                            rejected.exception.read().decode("utf-8")
                        )
                        self.assertEqual(expected, rejected.exception.code)
                        self.assertEqual(
                            "no-store",
                            rejected.exception.headers.get("Cache-Control"),
                        )
                        self.assertNotIn("priority", response_body.get("detail", ""))
                        rejected.exception.close()

                with self.assertRaises(error.HTTPError) as query_rejected:
                    post_raw(base, path + "?token=must-not-echo", manual_sos_raw())
                query_body = json.loads(
                    query_rejected.exception.read().decode("utf-8")
                )
                self.assertEqual(400, query_rejected.exception.code)
                self.assertNotIn("must-not-echo", json.dumps(query_body))
                query_rejected.exception.close()

            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(
                    0,
                    db.execute(
                        "SELECT COUNT(*) FROM manual_sos_timeline"
                    ).fetchone()[0],
                )

    def test_unconfigured_device_and_guardian_auth_fail_closed_without_fallback(self) -> None:
        ingest_path = "/api/v1/safety-events/manual-sos"
        latest_path = (
            f"/api/v1/devices/{DEVICE_ID}/safety-events/manual-sos/latest"
        )
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(db_path, token=None) as base:
                parsed = urlparse(base)
                connection = HTTPConnection(
                    parsed.hostname, parsed.port, timeout=5
                )
                connection.request(
                    "POST",
                    ingest_path,
                    body=None,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": "2",
                    },
                )
                ingest_rejected = connection.getresponse()
                ingest_rejected.read()
                self.assertEqual(503, ingest_rejected.status)
                self.assertEqual(
                    "no-store",
                    ingest_rejected.headers.get("Cache-Control"),
                )
                connection.close()

            with running_hub(db_path, authorizer=None) as base:
                with self.assertRaises(error.HTTPError) as guardian_rejected:
                    guardian_get(base, latest_path, token=DEVICE_TOKEN)
                body = json.loads(
                    guardian_rejected.exception.read().decode("utf-8")
                )
                self.assertEqual(503, guardian_rejected.exception.code)
                self.assertEqual(
                    "guardian_authorization_not_configured", body["error"]
                )
                self.assertEqual(
                    "no-store",
                    guardian_rejected.exception.headers.get("Cache-Control"),
                )
                guardian_rejected.exception.close()

    def test_guardian_auth_binding_ack_and_call_state_remain_independent(self) -> None:
        ingest_path = "/api/v1/safety-events/manual-sos"
        latest_path = (
            f"/api/v1/devices/{DEVICE_ID}/safety-events/manual-sos/latest"
        )
        raw = manual_sos_raw()
        event_id = "sos-b7-q11-t42050"
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(
                db_path, authorizer=guardian_authorizer()
            ) as base:
                delivery_before, _ = post_raw(base, ingest_path, raw)
                for path, token, expected in (
                    (latest_path, "wrong-guardian-token", 401),
                    (
                        f"/api/v1/devices/{OTHER_DEVICE}/safety-events/manual-sos/latest",
                        GUARDIAN_TOKEN,
                        403,
                    ),
                ):
                    with self.subTest(expected=expected):
                        with self.assertRaises(error.HTTPError) as rejected:
                            guardian_get(base, path, token=token)
                        self.assertEqual(expected, rejected.exception.code)
                        self.assertEqual(
                            "no-store",
                            rejected.exception.headers.get("Cache-Control"),
                        )
                        rejected.exception.close()

                first_ack, first_cache = guardian_ack(base, event_id)
                duplicate_ack, duplicate_cache = guardian_ack(base, event_id)
                latest, _ = guardian_get(base, latest_path)
                delivery_after, _ = post_raw(base, ingest_path, raw)

                with self.assertRaises(error.HTTPError) as body_rejected:
                    guardian_ack(base, event_id, body=b"not-allowed")
                self.assertEqual(400, body_rejected.exception.code)
                body_rejected.exception.close()

                with self.assertRaises(error.HTTPError) as missing:
                    guardian_ack(base, "sos-b7-q99-t99999")
                self.assertEqual(404, missing.exception.code)
                missing.exception.close()

            with closing(sqlite3.connect(db_path)) as db:
                timeline_count = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_timeline"
                ).fetchone()[0]
                ack_count = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_guardian_ack"
                ).fetchone()[0]

        self.assertEqual("accepted", first_ack["guardian_ack"]["status"])
        self.assertEqual(
            "duplicate", duplicate_ack["guardian_ack"]["status"]
        )
        self.assertEqual("no-store", first_cache)
        self.assertEqual("no-store", duplicate_cache)
        self.assertEqual(
            "acknowledged",
            latest["manual_sos_alert"]["guardian_ack_state"],
        )
        self.assertEqual(
            "not_reported", latest["manual_sos_alert"]["call_state"]
        )
        for field in (
            "contract_version",
            "ack_id",
            "device_id",
            "event_id",
            "payload_sha256",
            "status",
        ):
            self.assertEqual(
                delivery_before["delivery_ack"][field],
                delivery_after["delivery_ack"][field],
            )
        self.assertEqual(1, timeline_count)
        self.assertEqual(1, ack_count)

    def test_missing_latest_is_honest_and_no_store(self) -> None:
        latest_path = (
            f"/api/v1/devices/{DEVICE_ID}/safety-events/manual-sos/latest"
        )
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", authorizer=guardian_authorizer()
        ) as base:
            payload, cache = guardian_get(base, latest_path)
        alert = payload["manual_sos_alert"]
        self.assertFalse(alert["available"])
        self.assertEqual("no_durable_manual_sos", alert["reason"])
        self.assertEqual("not_reported", alert["call_state"])
        self.assertEqual("no-store", cache)

    def test_oversized_declared_ingest_is_rejected_before_body_read(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", authorizer=guardian_authorizer()
        ) as base:
            parsed = urlparse(base)
            connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
            connection.request(
                "POST",
                "/api/v1/safety-events/manual-sos",
                body=None,
                headers={
                    "Authorization": f"Bearer {DEVICE_TOKEN}",
                    "Content-Type": "application/json",
                    "Content-Length": "1025",
                },
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            connection.close()
        self.assertEqual(413, response.status)
        self.assertEqual("manual_sos_body_too_large", body["error"])
        self.assertEqual("no-store", response.headers.get("Cache-Control"))


if __name__ == "__main__":
    unittest.main()
