"""Whole ESP HTTPS C implementation, real server ACK, only SDK I/O replaced."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.collection_https_native_shim import HARNESS, HEADERS
from quality_tests.native_convergence import COMP, IDF, run_c
from quality_tests.test_collection_ingest import envelope, frame, raw_record
from server.message_hub import MessageHubStore


class CollectionHttpsNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        device = "collector_test-001"
        value = envelope(device_id=device)
        raw = frame(value)
        with tempfile.TemporaryDirectory() as root:
            store = MessageHubStore(Path(root) / "hub.db")
            ack = store.collection.ingest(raw, raw_record(raw, device), transport="wifi")
        response = json.dumps(ack, separators=(",", ":")).encode()
        harness = HARNESS.replace("__REQUEST_FRAME_BYTES__", ",".join(map(str, raw))).replace("__SERVER_ACK_BYTES__", ",".join(map(str, response)))
        output = run_c(harness, ["esp_p0_https", "collection_record"], extra_sources=[
            COMP / "sim7670_gnss/sim7670_http_exact_parser.c",
            IDF / "components/json/cJSON/cJSON.c",
            IDF / "components/mbedtls/mbedtls/library/sha256.c",
            IDF / "components/mbedtls/mbedtls/library/platform_util.c",
        ], headers=HEADERS)
        cls.result = json.loads(output)

    def test_fixed_device_route_headers_and_actual_sdk_interface_binding(self):
        self.assertTrue(self.result["fixed_route_headers_interface"])
        self.assertTrue(self.result["ppp_interface_binding"])

    def test_complete_real_server_ack_round_trips_through_the_native_matcher(self):
        self.assertTrue(self.result["complete_server_ack"])

    def test_interrupted_body_cancel_timeout_headers_certificate_failure_and_wrong_ack(self):
        self.assertEqual(self.result["fault_cases"], 15)

    def test_certificate_verification_flags_are_tls_but_disconnection_is_io(self):
        self.assertTrue(self.result["tls_failure_classification"])

    def test_ascii_identifier_and_path_injection_rejected_before_network(self):
        self.assertEqual(self.result["ascii_id_rejections"], 14)

    def test_unsynchronized_clock_rejected_without_skipping_tls_validation(self):
        self.assertTrue(self.result["clock_tls_guard"])
        self.assertTrue(self.result["tls_origin_and_hostname_guards"])

    def test_empty_interface_cannot_fall_back_to_a_default_route(self):
        self.assertTrue(self.result["empty_interface_rejected"])
        self.assertEqual(self.result["interface_rejections"], 8)
        self.assertTrue(self.result["early_rejection_clears_result"])

    def test_optional_reuse_sends_two_complete_requests_with_one_verified_tls_connect(self):
        self.assertTrue(self.result["reuse_two_requests_one_tls"])

    def test_reused_connection_resets_request_bounds_and_retains_no_stack_request(self):
        self.assertTrue(self.result["reuse_request_bounds_and_lifetimes"])

    def test_uncertain_partial_write_retires_connection_and_retries_exact_record_bytes(self):
        self.assertTrue(self.result["reuse_uncertain_write_exact_retry"])

    def test_cancel_deadline_incomplete_non_success_and_close_events_retire_cache(self):
        self.assertEqual(self.result["reuse_fault_retirements"], 10)

    def test_origin_host_bearer_fixed_route_or_wifi_interface_change_rebuilds(self):
        self.assertEqual(self.result["reuse_identity_changes"], 5)

    def test_periodic_certificate_revalidation_limits_and_idempotent_close(self):
        self.assertTrue(self.result["reuse_age_and_count_limits"])

    def test_preflight_rejection_also_closes_a_previously_authenticated_connection(self):
        self.assertEqual(self.result["reuse_preflight_retirements"], 7)


if __name__ == "__main__":
    unittest.main()
