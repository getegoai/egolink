"""Executable host checks for camera metadata and strict durable ACK gates."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from quality_tests.native_convergence import IDF, run_c
from server import message_hub


EXTRA_SOURCES = [
    IDF / "components/json/cJSON/cJSON.c",
    IDF / "components/mbedtls/mbedtls/library/sha256.c",
    IDF / "components/mbedtls/mbedtls/library/platform_util.c",
]


METADATA_HARNESS = r'''
#include "photo_delivery_runtime.h"
#include <stdio.h>
int main(void) {
    char frame[4000]; size_t written = 0;
    photo_delivery_metadata_t m = {
        .device_id="camera-device-001", .photo_id="manual-abcd-n0",
        .trigger_reason="web_manual", .command_id="capture-001",
        .config_version="manual-single-v1", .capture_result="captured",
        .local_save_status="saved", .device_upload_status="pending",
        .media_type="image/jpeg", .width=320, .height=240, .byte_length=8,
        .sha256_hex="00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
        .storage_kind="persistent", .camera_model="OV5640",
        .driver_profile="qvga-jpeg-q12-v1",
        .authorization_session_id="photo-session-001",
        .retention_expires_at="2026-09-10T00:00:00.000Z",
        .capture_boot_count=7, .capture_sequence_id=11,
        .capture_monotonic_ns=123000000,
        .capture_event_utc="2026-09-09T12:00:00.123Z",
        .timestamp_source="sntp_anchor",
        .timestamp_quality="network_time_unverified_accuracy",
        .monotonic_clock_domain_id="collection-esp-timer-b7",
        .fw_version="test-fw",
        .firmware_elf_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        .runtime_config_id="collector-camera-runtime"
    };
    if (!photo_delivery_build_metadata_frame(&m, frame, sizeof(frame), &written)) return 1;
    fwrite(frame, 1, written, stdout);
    return 0;
}
'''


ACK_HARNESS = r'''
#include "photo_delivery_runtime.h"
#include <stdio.h>
#include <string.h>
#define CHECK(v) do { if (!(v)) { fprintf(stderr,"line=%d\n",__LINE__); return 1; } } while (0)
int main(void) {
    const char *digest = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const char *command = "{\"ok\":true,\"raw_frame\":{\"frame_id\":\"capture-001\",\"parse_result\":{\"status\":\"ok\",\"derived_message_type\":\"ack\"}},\"command_ack\":{\"disposition\":\"newly_applied\",\"command_status\":\"ok\",\"posted_ack_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"accepted_ack_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}";
    const char *command_extra = "{\"ok\":true,\"raw_frame\":{\"frame_id\":\"capture-001\",\"parse_result\":{\"status\":\"ok\",\"derived_message_type\":\"ack\"}},\"command_ack\":{\"disposition\":\"conflict_ignored\",\"command_status\":\"ok\",\"posted_ack_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"accepted_ack_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}";
    const char *photo = "{\"ok\":true,\"result\":\"stored\",\"delivery_ack\":{\"contract_version\":\"egolink.photo.content.ack.v0.1\",\"device_id\":\"camera-device-001\",\"photo_id\":\"manual-abcd-n0\",\"payload_sha256\":\"00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff\",\"payload_bytes\":8,\"status\":\"server_verified\",\"verification_scope\":\"sha256_length_geometry_baseline_structure_v1\",\"stored_at\":\"2026-09-09T12:00:01.000Z\"}}";
    const char *photo_extra = "{\"ok\":true,\"result\":\"stored\",\"delivery_ack\":{\"contract_version\":\"egolink.photo.content.ack.v0.1\",\"device_id\":\"camera-device-001\",\"photo_id\":\"manual-abcd-n0\",\"payload_sha256\":\"00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff\",\"payload_bytes\":8,\"status\":\"server_verified\",\"verification_scope\":\"sha256_length_geometry_baseline_structure_v1\",\"stored_at\":\"2026-09-09T12:00:01.000Z\",\"untrusted\":true}}";
    CHECK(photo_delivery_command_ack_response_matches(command, strlen(command), "capture-001", "ok", digest));
    CHECK(!photo_delivery_command_ack_response_matches(command, strlen(command)-1, "capture-001", "ok", digest));
    CHECK(!photo_delivery_command_ack_response_matches(command, strlen(command), "capture-002", "ok", digest));
    CHECK(!photo_delivery_command_ack_response_matches(command_extra, strlen(command_extra), "capture-001", "ok", digest));
    CHECK(photo_delivery_content_ack_response_matches(photo, strlen(photo), "camera-device-001", "manual-abcd-n0", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", 8));
    CHECK(!photo_delivery_content_ack_response_matches(photo, strlen(photo), "camera-device-001", "manual-abcd-n0", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", 7));
    CHECK(!photo_delivery_content_ack_response_matches(photo, strlen(photo)-1, "camera-device-001", "manual-abcd-n0", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", 8));
    CHECK(!photo_delivery_content_ack_response_matches(photo_extra, strlen(photo_extra), "camera-device-001", "manual-abcd-n0", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", 8));
    puts("ok"); return 0;
}
'''


class PhotoDeliveryRuntimeTests(unittest.TestCase):
    def test_metadata_frame_is_server_contract_valid(self):
        frame = run_c(
            METADATA_HARNESS,
            ["photo_delivery_runtime", "collection_record"],
            extra_sources=EXTRA_SOURCES,
        ).encode()
        record = message_hub.parse_raw_frame_record(
            message_hub.initial_raw_frame_record(
                "camera-device-001", frame, "uplink", message_hub.utc_now()
            ),
            frame,
            expected_frame_type="event",
        )
        self.assertEqual(record["parse_result"]["status"], "ok")
        envelope = json.loads(frame.split(b"\n\n", 1)[1])
        self.assertEqual(envelope["payload"]["command_id"], "capture-001")
        self.assertEqual(envelope["payload"]["width"], 320)
        self.assertEqual(envelope["payload"]["height"], 240)
        schema = json.loads(
            (Path(__file__).resolve().parents[1]
             / "shared/contracts/collection_observation.schema.json").read_text(
                 encoding="utf-8"
             )
        )
        errors = list(Draft202012Validator(schema).iter_errors(envelope))
        self.assertEqual(errors, [])

    def test_only_exact_command_and_server_verified_photo_acks_match(self):
        output = run_c(
            ACK_HARNESS,
            ["photo_delivery_runtime", "collection_record"],
            extra_sources=EXTRA_SOURCES,
        )
        self.assertEqual(output.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
