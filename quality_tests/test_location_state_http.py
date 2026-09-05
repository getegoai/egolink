from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib import error, request
from urllib.parse import urlparse

from quality_tests.test_location_state_mirror import envelope, location_state
from quality_tests.test_message_hub_server import get_json, post_json
from server import message_hub
from server.location_state_runtime import LocationStateRuntimeMirror


@contextmanager
def running_hub(db_path: Path, *, token: str | None = "secret"):
    store = message_hub.MessageHubStore(db_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token=token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


class LocationStateHttpTests(unittest.TestCase):
    def test_sqlite_integer_overflow_is_sanitized_422_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(db_path) as base:
                seed = LocationStateRuntimeMirror()
                item = envelope(seed, location_state(1_000))
                item["sequence_id"] = 1 << 63
                with self.assertRaises(error.HTTPError) as rejected:
                    post_json(
                        base,
                        "/api/v1/location-states",
                        item,
                        {"Authorization": "Bearer secret"},
                    )
                body = json.loads(rejected.exception.read().decode("utf-8"))
                rejected.exception.close()
                self.assertEqual(rejected.exception.code, 422)
                self.assertEqual(body["error"], "invalid_location_state")
                self.assertEqual(body["detail"], "location state request rejected")

            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM location_state_timeline"
                    ).fetchone()[0],
                    0,
                )

    def test_current_without_record_uses_full_redacted_api_shape(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            headers = {"Authorization": "Bearer secret"}
            current = get_json(
                base,
                "/api/v1/devices/missing-device/location-state/current",
                headers,
            )["location_state"]
            self.assertFalse(current["available"])
            self.assertEqual(current["freshness"], "unavailable")
            self.assertEqual(current["reason"], "no_accepted_location_state")
            self.assertIsNone(current["current_identity"])
            self.assertIsNone(current["state_age_ms"])
            self.assertIsNone(current["location_age_ms"])
            self.assertIsNone(current["position"])
            for field in (
                "location_belief",
                "location_source",
                "accuracy",
                "confidence",
                "uncertainty",
                "battery",
                "sensor_policy_state",
                "sos_active",
                "stale",
                "offline",
                "offline_status",
                "freshness_reason_codes",
                "non_claims",
            ):
                self.assertIn(field, current)
            self.assertNotIn("latitude", json.dumps(current))

    def test_location_routes_fail_closed_before_body_read_when_token_is_unconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(db_path, token=None) as base:
                malformed = request.Request(
                    base + "/api/v1/location-states",
                    data=b'{"latitude_deg":10',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(error.HTTPError) as post_rejected:
                    request.urlopen(malformed, timeout=5)
                post_body = json.loads(post_rejected.exception.read().decode("utf-8"))
                post_rejected.exception.close()
                self.assertEqual(post_rejected.exception.code, 503)
                self.assertEqual(
                    post_body["error"],
                    "location_state_auth_not_configured",
                )
                self.assertNotIn("latitude", json.dumps(post_body))

                with self.assertRaises(error.HTTPError) as get_rejected:
                    get_json(
                        base,
                        "/api/v1/devices/synthetic-device-001/location-state/current",
                    )
                get_body = json.loads(get_rejected.exception.read().decode("utf-8"))
                get_rejected.exception.close()
                self.assertEqual(get_rejected.exception.code, 503)
                self.assertEqual(
                    get_body["error"],
                    "location_state_auth_not_configured",
                )
                self.assertEqual(get_json(base, "/api/v1/devices"), {"devices": []})

            with closing(sqlite3.connect(db_path)) as db:
                count = db.execute(
                    "SELECT COUNT(*) FROM location_state_timeline"
                ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_authenticated_ingest_is_idempotent_and_current_is_redacted_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "hub.db"
            seed = LocationStateRuntimeMirror()
            item = envelope(seed, location_state(1_000))
            headers = {"Authorization": "Bearer secret"}
            with running_hub(db) as base:
                self.assertEqual(post_json(base, "/api/v1/location-states", item, headers)["result"]["status"], "accepted")
                self.assertEqual(post_json(base, "/api/v1/location-states", item, headers)["result"]["status"], "duplicate")
            with closing(sqlite3.connect(db)) as connection:
                persisted_json, persisted_receive_time = connection.execute(
                    """SELECT envelope_json,server_receive_time_ms
                    FROM location_state_timeline"""
                ).fetchone()
            persisted = json.loads(persisted_json)
            self.assertNotEqual(
                persisted_receive_time,
                item["server_receive_time_ms"],
            )
            self.assertEqual(
                persisted["server_receive_time_ms"],
                persisted_receive_time,
            )
            with running_hub(db) as base:
                current = get_json(base, f"/api/v1/devices/{item['device_id']}/location-state/current", headers)["location_state"]
                self.assertIsNone(current["position"])
                self.assertIn(current["freshness"], {"fresh", "stale"})
                self.assertEqual(current["reason"], "source_clock_comparable")
                self.assertIn("exact_position_authorization_unavailable", current["non_claims"])

    def test_location_ingest_reuses_bounded_body_reader_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            with running_hub(db_path) as base:
                # Send only an oversized declared length. Sending a full 1 MiB
                # body races the server's intentional early 413/close on
                # Windows and can surface a client-side connection abort before
                # the already-written response. The header-only request tests
                # the same pre-read boundary deterministically.
                parsed = urlparse(base)
                connection = HTTPConnection(
                    parsed.hostname,
                    parsed.port,
                    timeout=5,
                )
                connection.request(
                    "POST",
                    "/api/v1/location-states",
                    body=None,
                    headers={
                        "Authorization": "Bearer secret",
                        "Content-Type": "application/json",
                        "Content-Length": str(message_hub.MAX_BODY_BYTES + 1),
                    },
                )
                rejected = connection.getresponse()
                body = json.loads(rejected.read().decode("utf-8"))
                connection.close()
                self.assertEqual(rejected.status, 413)
                self.assertEqual(body["error"], "body_too_large")

            with closing(sqlite3.connect(db_path)) as db:
                count = db.execute(
                    "SELECT COUNT(*) FROM location_state_timeline"
                ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_auth_and_query_boolean_cannot_unlock_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            seed = LocationStateRuntimeMirror(); item = envelope(seed, location_state(1_000))
            with self.assertRaises(error.HTTPError) as unauthorized:
                post_json(base, "/api/v1/location-states", item)
            self.assertEqual(unauthorized.exception.code, 401); unauthorized.exception.close()
            headers = {"Authorization": "Bearer secret"}
            post_json(base, "/api/v1/location-states", item, headers)
            with self.assertRaises(error.HTTPError) as forbidden_query:
                get_json(base, f"/api/v1/devices/{item['device_id']}/location-state/current?location_access_authorized=true", headers)
            self.assertEqual(forbidden_query.exception.code, 400); forbidden_query.exception.close()

    def test_regression_and_conflict_errors_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            seed = LocationStateRuntimeMirror(); headers = {"Authorization": "Bearer secret"}
            newer = envelope(seed, location_state(2_000), sequence_id=2, observation_id="newer")
            post_json(base, "/api/v1/location-states", newer, headers)
            older = envelope(seed, location_state(1_000), sequence_id=1, observation_id="older")
            for bad in (older, {**deepcopy(newer), "location_state": {**newer["location_state"], "battery_percent": 99}}):
                with self.assertRaises(error.HTTPError) as rejected:
                    post_json(base, "/api/v1/location-states", bad, headers)
                body = json.loads(rejected.exception.read().decode("utf-8")); rejected.exception.close()
                self.assertNotIn("latitude", json.dumps(body))
                self.assertEqual(body["detail"], "location state request rejected")

    def test_invalid_current_device_id_error_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            headers = {"Authorization": "Bearer secret"}
            invalid_device_id = "x" * 257
            with self.assertRaises(error.HTTPError) as rejected:
                get_json(
                    base,
                    f"/api/v1/devices/{invalid_device_id}/location-state/current",
                    headers,
                )
            body = json.loads(rejected.exception.read().decode("utf-8"))
            rejected.exception.close()
            self.assertEqual(rejected.exception.code, 422)
            self.assertEqual(body["error"], "invalid_location_state")
            self.assertEqual(body["detail"], "location state request rejected")

    def test_monotonic_current_has_no_fabricated_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            seed = LocationStateRuntimeMirror(); headers = {"Authorization": "Bearer secret"}
            state = location_state(1_000, clock_source="timestamp_monotonic_ns", clock_domain="boot-1")
            item = envelope(seed, state, event_time_source="timestamp_monotonic_ns", monotonic_clock_domain_id="boot-1")
            post_json(base, "/api/v1/location-states", item, headers)
            current = get_json(base, f"/api/v1/devices/{item['device_id']}/location-state/current", headers)["location_state"]
            self.assertEqual(current["freshness"], "unavailable")
            self.assertIsNone(current["position"])
            self.assertIsNone(current["state_age_ms"])
            self.assertIsNone(current["location_age_ms"])
            self.assertIsNone(current["stale"])
            self.assertIsNone(current["offline"])
            self.assertEqual(current["location_belief"], item["location_state"]["location_belief"])
            self.assertEqual(current["location_source"], item["location_state"]["location_source"])
            self.assertEqual(current["battery"]["state"], item["location_state"]["battery_state"])
            self.assertIn("confidence", current)
            self.assertIn("uncertainty", current)
            self.assertIn("receive_time_not_used_as_event_time", current["non_claims"])

    def test_source_clock_ahead_returns_fail_honest_unavailable_current(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(Path(root) / "hub.db") as base:
            seed = LocationStateRuntimeMirror()
            headers = {"Authorization": "Bearer secret"}
            future_event_ms = time.time_ns() // 1_000_000 + 60_000
            item = envelope(seed, location_state(future_event_ms))
            post_json(base, "/api/v1/location-states", item, headers)

            current = get_json(
                base,
                f"/api/v1/devices/{item['device_id']}/location-state/current",
                headers,
            )["location_state"]
            self.assertTrue(current["available"])
            self.assertEqual(current["freshness"], "unavailable")
            self.assertIsNone(current["state_age_ms"])
            self.assertIsNone(current["location_age_ms"])
            self.assertIsNone(current["stale"])
            self.assertIsNone(current["offline"])
            self.assertIsNone(current["position"])
            self.assertEqual(current["reason"], "source_clock_ahead")
            self.assertEqual(current["location_belief"], item["location_state"]["location_belief"])
            self.assertEqual(current["location_source"], item["location_state"]["location_source"])
            self.assertEqual(current["battery"]["state"], item["location_state"]["battery_state"])
            self.assertIn("confidence", current)
            self.assertIn("uncertainty", current)
            self.assertIn("receive_time_not_used_as_event_time", current["non_claims"])
            self.assertNotIn("latitude", json.dumps(current))


if __name__ == "__main__": unittest.main()
