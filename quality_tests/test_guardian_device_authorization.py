from __future__ import annotations

from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import error
from urllib import request

from jsonschema import Draft202012Validator

from quality_tests.test_location_state_mirror import envelope, location_state
from quality_tests.test_message_hub_server import get_json, post_json
from server import message_hub
from server.guardian_device_authorization import (
    CONTRACT_VERSION,
    GuardianAuthorizationConfigError,
    GuardianDeviceAuthorizer,
    token_sha256,
)
from server.location_state_runtime import LocationStateRuntimeMirror


DEVICE = "wearable-node-001"
OTHER_DEVICE = "wearable-node-002"
GUARDIAN_TOKEN = "guardian-test-token-0001"


def authorizer() -> GuardianDeviceAuthorizer:
    return GuardianDeviceAuthorizer(
        {
            "contract_version": CONTRACT_VERSION,
            "bindings": [
                {
                    "guardian_id": "guardian-001",
                    "token_sha256": token_sha256(GUARDIAN_TOKEN),
                    "device_ids": [DEVICE],
                }
            ],
        }
    )


@contextmanager
def running_hub(db_path: Path, *, guardian_authorizer=None):
    store = message_hub.MessageHubStore(db_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        message_hub.make_handler(
            store,
            token="device-ingest-token",
            guardian_authorizer=guardian_authorizer,
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


class GuardianDeviceAuthorizationTests(unittest.TestCase):
    def test_guardian_location_shell_has_no_secret_and_is_hardened(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", guardian_authorizer=authorizer()
        ) as base:
            with request.urlopen(f"{base}/guardian-location", timeout=5) as response:
                html = response.read().decode("utf-8")
                self.assertEqual("no-store", response.headers["Cache-Control"])
                self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
                self.assertEqual("no-referrer", response.headers["Referrer-Policy"])
            self.assertNotIn(GUARDIAN_TOKEN, html)
            self.assertNotIn("<script>", html)
            self.assertIn('type="password"', html)

            with request.urlopen(f"{base}/guardian-location.js", timeout=5) as response:
                script = response.read().decode("utf-8")
                self.assertEqual(
                    "application/javascript; charset=utf-8",
                    response.headers["Content-Type"],
                )
            self.assertIn("encodeURIComponent(device)", script)
            self.assertIn("textContent", script)
            self.assertIn("guardian-token').value = ''", script)
            self.assertNotIn("localStorage", script)
            self.assertNotIn("sessionStorage", script)

    def test_machine_contract_matches_runtime_document(self) -> None:
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared"
                / "contracts"
                / "guardian_device_bindings_v0.schema.json"
            ).read_text(encoding="utf-8")
        )
        document = {
            "contract_version": CONTRACT_VERSION,
            "bindings": [
                {
                    "guardian_id": "guardian-001",
                    "token_sha256": token_sha256(GUARDIAN_TOKEN),
                    "device_ids": [DEVICE],
                }
            ],
        }
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(document)))
        GuardianDeviceAuthorizer(document)

    def test_config_keeps_only_hashes_and_fails_closed_on_ambiguity(self) -> None:
        instance = authorizer()
        self.assertNotIn(GUARDIAN_TOKEN, repr(instance))
        base = {
            "contract_version": CONTRACT_VERSION,
            "bindings": [
                {
                    "guardian_id": "guardian-001",
                    "token_sha256": token_sha256(GUARDIAN_TOKEN),
                    "device_ids": [DEVICE],
                }
            ],
        }
        for bad in (
            {**base, "extra": True},
            {**base, "contract_version": "unknown"},
            {**base, "bindings": []},
            {
                **base,
                "bindings": [base["bindings"][0], base["bindings"][0]],
            },
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(GuardianAuthorizationConfigError):
                    GuardianDeviceAuthorizer(bad)

    def test_file_loader_is_bounded_and_rejects_plaintext_shape(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "bindings.json"
            path.write_text(
                json.dumps(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "bindings": [
                            {
                                "guardian_id": "guardian-001",
                                "token": GUARDIAN_TOKEN,
                                "device_ids": [DEVICE],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(GuardianAuthorizationConfigError):
                GuardianDeviceAuthorizer.from_file(path)
            path.write_text(
                '{"contract_version":"%s","contract_version":"%s",'
                '"bindings":[]}' % (CONTRACT_VERSION, CONTRACT_VERSION),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GuardianAuthorizationConfigError, "duplicate member"
            ):
                GuardianDeviceAuthorizer.from_file(path)

    def test_authentication_and_device_binding_are_distinct(self) -> None:
        instance = authorizer()
        self.assertEqual(
            "unauthenticated", instance.authorize(None, DEVICE).status
        )
        self.assertEqual(
            "unauthenticated",
            instance.authorize("Bearer wrong-token-value", DEVICE).status,
        )
        self.assertEqual(
            "forbidden",
            instance.authorize(f"Bearer {GUARDIAN_TOKEN}", OTHER_DEVICE).status,
        )
        decision = instance.authorize(f"Bearer {GUARDIAN_TOKEN}", DEVICE)
        self.assertTrue(decision.authorized)
        self.assertEqual("guardian-001", decision.guardian_id)

    def test_bound_guardian_gets_exact_position_but_not_other_apis(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", guardian_authorizer=authorizer()
        ) as base:
            seed = LocationStateRuntimeMirror()
            item = envelope(seed, location_state(1_000))
            item["device_id"] = DEVICE
            item["location_state"]["last_trusted_location"]["evidence_ref"][
                "observation_id"
            ] = item["observation_id"]
            post_json(
                base,
                "/api/v1/location-states",
                item,
                {"Authorization": "Bearer device-ingest-token"},
            )

            headers = {"Authorization": f"Bearer {GUARDIAN_TOKEN}"}
            current = get_json(
                base,
                f"/api/v1/devices/{DEVICE}/location-state/current",
                headers,
            )["location_state"]
            self.assertEqual("binding_file", current["authorization_scope"])
            self.assertEqual("guardian-001", current["authorization_subject"])
            self.assertTrue(current["location_access_authorized"])
            self.assertIsNotNone(current["position"])
            self.assertIn("latitude_deg", current["position"])

            with self.assertRaises(error.HTTPError) as unrelated:
                get_json(base, "/api/v1/devices", headers)
            self.assertEqual(401, unrelated.exception.code)
            unrelated.exception.close()

    def test_wrong_or_unbound_guardian_never_receives_location(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", guardian_authorizer=authorizer()
        ) as base:
            for header, expected in (
                (None, 401),
                ({"Authorization": "Bearer wrong-token-value"}, 401),
                ({"Authorization": f"Bearer {GUARDIAN_TOKEN}"}, 403),
            ):
                path = (
                    f"/api/v1/devices/{DEVICE}/location-state/current"
                    if expected == 401
                    else f"/api/v1/devices/{OTHER_DEVICE}/location-state/current"
                )
                with self.subTest(expected=expected):
                    with self.assertRaises(error.HTTPError) as rejected:
                        get_json(base, path, header)
                    body = json.loads(rejected.exception.read().decode("utf-8"))
                    self.assertEqual(expected, rejected.exception.code)
                    self.assertEqual(
                        "no-store", rejected.exception.headers["Cache-Control"]
                    )
                    self.assertNotIn("position", json.dumps(body))
                    rejected.exception.close()

    def test_bound_monotonic_position_does_not_fabricate_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as root, running_hub(
            Path(root) / "hub.db", guardian_authorizer=authorizer()
        ) as base:
            seed = LocationStateRuntimeMirror()
            state = location_state(
                1_000,
                clock_source="timestamp_monotonic_ns",
                clock_domain="boot-1",
            )
            item = envelope(
                seed,
                state,
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id="boot-1",
            )
            item["device_id"] = DEVICE
            item["location_state"]["last_trusted_location"]["evidence_ref"][
                "observation_id"
            ] = item["observation_id"]
            post_json(
                base,
                "/api/v1/location-states",
                item,
                {"Authorization": "Bearer device-ingest-token"},
            )
            current = get_json(
                base,
                f"/api/v1/devices/{DEVICE}/location-state/current",
                {"Authorization": f"Bearer {GUARDIAN_TOKEN}"},
            )["location_state"]
            self.assertIsNotNone(current["position"])
            self.assertEqual("unavailable", current["freshness"])
            self.assertIsNone(current["state_age_ms"])
            self.assertIsNone(current["location_age_ms"])
            self.assertIn(
                "receive_time_not_used_as_event_time", current["non_claims"]
            )


if __name__ == "__main__":
    unittest.main()
