from __future__ import annotations

import base64
from contextlib import closing
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request

from jsonschema import Draft202012Validator

from pc_simulator import protocol
from scripts import export_imu_windows
from server import message_hub


DEVICE_ID = "ego-link-imu-unit"
TEST_RUN_ID = "imu-window-unit"
CMD_ID = "cmd-imu-unit"
BOOT_COUNT = 7
WINDOW_ID = f"imuw-{CMD_ID}-b{BOOT_COUNT}"


def sample_bytes(*, mutate_index: int | None = None, interval_us: int | None = None) -> bytes:
    cadence_us = interval_us or message_hub.IMU_WINDOW_INTERVAL_US
    output = bytearray()
    for index in range(message_hub.IMU_WINDOW_SAMPLE_COUNT):
        values = [50 + index % 3, 8, 974, -800, 3200, 240]
        if mutate_index == index:
            values[0] += 1
        output.extend((1000 + index * cadence_us).to_bytes(4, "little"))
        for value in values:
            output.extend(int(value).to_bytes(4, "little", signed=True))
    return bytes(output)


def encode_kv(fields: dict[str, object]) -> bytes:
    def rendered(value: object) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    return ("\n".join(f"{key}={rendered(value)}" for key, value in fields.items()) + "\n").encode("utf-8")


def chunk_fields(
    index: int,
    complete_samples: bytes,
    *,
    cmd_id: str = CMD_ID,
    boot_count: int = BOOT_COUNT,
    fw_version: str = "0.1.0-imu-unit",
    test_run_id: str = TEST_RUN_ID,
    transport_type: str = "lte",
) -> dict[str, object]:
    start = index * message_hub.IMU_WINDOW_SAMPLES_PER_CHUNK
    count = min(
        message_hub.IMU_WINDOW_SAMPLES_PER_CHUNK,
        message_hub.IMU_WINDOW_SAMPLE_COUNT - start,
    )
    chunk = complete_samples[
        start * message_hub.IMU_WINDOW_RECORD_BYTES : (start + count) * message_hub.IMU_WINDOW_RECORD_BYTES
    ]
    return {
        "event_type": "imu_window_chunk",
        "priority": "normal",
        "source": "qmi8658_i2c",
        "source_status": "observed",
        "fw_version": fw_version,
        "test_run_id": test_run_id,
        "seq": index + 1,
        "transport_type": transport_type,
        "boot_count": boot_count,
        "contract_version": message_hub.IMU_WINDOW_CONTRACT_VERSION,
        "window_id": f"imuw-{cmd_id}-b{boot_count}",
        "capture_cmd_id": cmd_id,
        "chunk_index": index,
        "chunk_count": message_hub.IMU_WINDOW_CHUNK_COUNT,
        "sample_start_index": start,
        "sample_count": count,
        "total_sample_count": message_hub.IMU_WINDOW_SAMPLE_COUNT,
        "requested_interval_us": message_hub.IMU_WINDOW_INTERVAL_US,
        "sample_record_bytes": message_hub.IMU_WINDOW_RECORD_BYTES,
        "sample_encoding": message_hub.IMU_WINDOW_SAMPLE_ENCODING,
        "chunk_crc32": message_hub.crc32_hex(chunk),
        "samples_b64": base64.b64encode(chunk).decode("ascii"),
    }


def chunk_payload(index: int, complete_samples: bytes, **kwargs: object) -> bytes:
    return encode_kv(chunk_fields(index, complete_samples, **kwargs))


def manifest_fields(
    complete_samples: bytes,
    *,
    cmd_id: str = CMD_ID,
    boot_count: int = BOOT_COUNT,
    fw_version: str = "0.1.0-imu-unit",
    test_run_id: str = TEST_RUN_ID,
    transport_type: str = "lte",
) -> dict[str, object]:
    return {
        "event_type": "imu_window_manifest",
        "priority": "normal",
        "source": "qmi8658_i2c",
        "source_status": "observed",
        "fw_version": fw_version,
        "test_run_id": test_run_id,
        "seq": message_hub.IMU_WINDOW_CHUNK_COUNT + 1,
        "transport_type": transport_type,
        "boot_count": boot_count,
        "contract_version": message_hub.IMU_WINDOW_CONTRACT_VERSION,
        "window_id": f"imuw-{cmd_id}-b{boot_count}",
        "capture_cmd_id": cmd_id,
        "sample_count": message_hub.IMU_WINDOW_SAMPLE_COUNT,
        "requested_interval_us": message_hub.IMU_WINDOW_INTERVAL_US,
        "capture_start_uptime_us": 1_000_000,
        "capture_end_uptime_us": 5_951_000,
        "min_interval_us": 50_000,
        "mean_interval_us": 50_000,
        "max_interval_us": 50_000,
        "deadline_miss_count": 0,
        "read_failure_count": 0,
        "mock_sample_count": 0,
        "warmup_sample_count": message_hub.IMU_WINDOW_WARMUP_SAMPLE_COUNT,
        "warmup_interval_us": message_hub.IMU_WINDOW_WARMUP_INTERVAL_US,
        "chunk_count": message_hub.IMU_WINDOW_CHUNK_COUNT,
        "uploaded_chunk_count": message_hub.IMU_WINDOW_CHUNK_COUNT,
        "samples_crc32": message_hub.crc32_hex(complete_samples),
        "sensor_model": "QMI8658A",
        "sensor_i2c_address": 106,
        "accel_unit": "mg",
        "gyro_unit": "mdps",
        "activity_label": "unknown",
        "label_source": "none",
        "collection_authorization": "operator_command",
        "training_allowed": False,
        "mounting_profile_id": "unrecorded",
        "axis_mapping_status": "unrecorded",
        "calibration_profile_id": "unrecorded",
    }


def manifest_payload(complete_samples: bytes, **kwargs: object) -> bytes:
    return encode_kv(manifest_fields(complete_samples, **kwargs))


def create_capture_command(
    store: message_hub.MessageHubStore,
    *,
    cmd_id: str = CMD_ID,
    test_run_id: str = TEST_RUN_ID,
) -> dict[str, object]:
    return store.create_command(
        DEVICE_ID,
        {
            "cmd": "capture_imu_window",
            "cmd_id": cmd_id,
            "test_run_id": test_run_id,
            "payload": {"sample_count": 100, "interval_ms": 50},
        },
    )


def ingest_window(
    store: message_hub.MessageHubStore,
    complete_samples: bytes,
    *,
    omit_chunk: int | None = None,
    expect_ok: bool = True,
    transport_type: str = "lte",
) -> None:
    for index in range(message_hub.IMU_WINDOW_CHUNK_COUNT):
        if index == omit_chunk:
            continue
        payload = chunk_payload(index, complete_samples, transport_type=transport_type)
        frame = message_hub.build_raw_frame(
            "event",
            f"imu-{CMD_ID}-b{BOOT_COUNT}-c{index:02d}",
            payload,
            seq=index + 1,
        )
        record = store.ingest_raw_frame(DEVICE_ID, frame)
        if expect_ok and record["parse_result"]["status"] != "ok":
            raise AssertionError(record["parse_result"])
    payload = manifest_payload(complete_samples, transport_type=transport_type)
    frame = message_hub.build_raw_frame(
        "event",
        f"imu-{CMD_ID}-b{BOOT_COUNT}-manifest",
        payload,
        seq=message_hub.IMU_WINDOW_CHUNK_COUNT + 1,
    )
    record = store.ingest_raw_frame(DEVICE_ID, frame)
    if expect_ok and record["parse_result"]["status"] != "ok":
        raise AssertionError(record["parse_result"])


class ImuWindowExportTests(unittest.TestCase):
    def test_wire_contract_schemas_lock_fixed_shape_and_training_boundary(self) -> None:
        contract_dir = Path(__file__).resolve().parents[1] / "shared" / "contracts"
        chunk_schema = json.loads((contract_dir / "imu_window_chunk.schema.json").read_text(encoding="utf-8"))
        manifest_schema = json.loads((contract_dir / "imu_window_manifest.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(chunk_schema["properties"]["contract_version"]["const"], "egolink.imu_window.v1")
        self.assertEqual(chunk_schema["properties"]["total_sample_count"]["const"], 100)
        self.assertEqual(chunk_schema["properties"]["requested_interval_us"]["const"], 50_000)
        self.assertEqual(chunk_schema["properties"]["sample_record_bytes"]["const"], 28)
        self.assertEqual(chunk_schema["properties"]["transport_type"]["enum"], ["lte", "wifi"])
        self.assertEqual(manifest_schema["properties"]["transport_type"]["enum"], ["lte", "wifi"])
        self.assertEqual(manifest_schema["properties"]["training_allowed"]["const"], False)
        self.assertEqual(manifest_schema["properties"]["sensor_i2c_address"]["const"], 106)
        self.assertEqual(manifest_schema["properties"]["axis_mapping_status"]["const"], "unrecorded")
        complete_samples = sample_bytes()
        Draft202012Validator(chunk_schema).validate(chunk_fields(0, complete_samples))
        Draft202012Validator(manifest_schema).validate(manifest_fields(complete_samples))
        Draft202012Validator(chunk_schema).validate(chunk_fields(0, complete_samples, transport_type="wifi"))
        Draft202012Validator(manifest_schema).validate(manifest_fields(complete_samples, transport_type="wifi"))
        for unsupported_transport in ("usb", "WiFi"):
            self.assertFalse(
                Draft202012Validator(chunk_schema).is_valid(
                    chunk_fields(0, complete_samples, transport_type=unsupported_transport)
                )
            )
            self.assertFalse(
                Draft202012Validator(manifest_schema).is_valid(
                    manifest_fields(complete_samples, transport_type=unsupported_transport)
                )
            )

    def test_maximum_contract_lineage_still_fits_the_1200_byte_ceiling(self) -> None:
        complete_samples = sample_bytes()
        cmd_id = "c" * message_hub.IMU_WINDOW_CAPTURE_CMD_ID_MAX
        boot_count = 4_294_967_295
        fields = chunk_fields(
            9,
            complete_samples,
            cmd_id=cmd_id,
            boot_count=boot_count,
            fw_version="f" * message_hub.IMU_WINDOW_FW_VERSION_MAX,
            test_run_id="t" * message_hub.IMU_WINDOW_TEST_RUN_ID_MAX,
        )
        payload = encode_kv(fields)
        frame = message_hub.build_raw_frame(
            "event",
            f"imu-{cmd_id}-b{boot_count}-c09",
            payload,
            seq=4_294_967_295,
        )
        manifest = manifest_fields(
            complete_samples,
            cmd_id=cmd_id,
            boot_count=boot_count,
            fw_version="f" * message_hub.IMU_WINDOW_FW_VERSION_MAX,
            test_run_id="t" * message_hub.IMU_WINDOW_TEST_RUN_ID_MAX,
        )
        manifest.update(
            {
                "seq": 4_294_967_295,
                "capture_start_uptime_us": 9_223_372_036_854_775_806,
                "capture_end_uptime_us": 9_223_372_036_854_775_807,
                "min_interval_us": 1_000_000,
                "mean_interval_us": 1_000_000,
                "max_interval_us": 1_000_000,
                "deadline_miss_count": 100,
            }
        )
        manifest_frame = message_hub.build_raw_frame(
            "event",
            f"imu-{cmd_id}-b{boot_count}-manifest",
            encode_kv(manifest),
            seq=4_294_967_295,
        )

        self.assertLessEqual(len(frame), message_hub.IMU_WINDOW_RAW_FRAME_MAX_BYTES)
        self.assertLessEqual(len(manifest_frame), message_hub.IMU_WINDOW_RAW_FRAME_MAX_BYTES)

    def test_raw_first_ingest_redacts_samples_and_explicit_export_reassembles_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            complete_samples = sample_bytes()
            ingest_window(store, complete_samples)

            telemetry = store.telemetry_history(DEVICE_ID)
            raw_frames = store.list_raw_frames(DEVICE_ID)
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )
            exported = [json.loads(line) for line in (tmp_path / "export" / "imu_windows.jsonl").read_text().splitlines()]
            export_manifest = json.loads(
                (tmp_path / "export" / "imu_window_export_manifest.json").read_text(encoding="utf-8")
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 1)
        self.assertEqual(len(exported[0]["samples"]), 100)
        self.assertFalse(exported[0]["training_allowed"])
        self.assertEqual(exported[0]["source"], "qmi8658_i2c")
        self.assertEqual(exported[0]["capture"]["mean_interval_us"], 50_000)
        self.assertEqual(exported[0]["capture"]["warmup_sample_count"], 10)
        self.assertEqual(exported[0]["transport_type"], "lte")
        self.assertEqual(len(exported[0]["raw_frame_refs"]), 11)
        self.assertEqual(exported[0]["privacy_class"], "engineering")
        self.assertEqual(exported[0]["split_name"], "unassigned")
        self.assertFalse(exported[0]["split_leakage_checked"])
        self.assertTrue(exported[0]["training_blockers"])
        self.assertTrue(export_manifest["ok"])
        self.assertEqual(export_manifest["selectors"]["database_name"], "hub.db")
        self.assertNotIn(str(db_path.parent), json.dumps(export_manifest))
        telemetry_json = json.dumps(telemetry)
        self.assertNotIn("samples_b64", telemetry_json)
        self.assertNotIn('"samples":', telemetry_json)
        self.assertTrue(all(frame["raw_payload"]["data_redacted"] for frame in raw_frames))

    def test_wifi_window_is_accepted_and_export_preserves_transport_and_training_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            ingest_window(store, sample_bytes(), transport_type="wifi")

            telemetry = store.telemetry_history(DEVICE_ID)
            raw_frames = store.list_raw_frames(DEVICE_ID)
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )
            exported = json.loads((tmp_path / "export" / "imu_windows.jsonl").read_text().splitlines()[0])

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 1)
        self.assertEqual(exported["transport_type"], "wifi")
        self.assertFalse(exported["training_allowed"])
        self.assertEqual(exported["consent_status"], "unreviewed_required")
        self.assertFalse(exported["split_leakage_checked"])
        self.assertIn("operator_training_authorization_missing", exported["training_blockers"])
        self.assertNotIn("samples_b64", json.dumps(telemetry))
        self.assertTrue(all(frame["raw_payload"]["data_redacted"] for frame in raw_frames))

    def test_export_ignores_same_run_raw_command_and_ack_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            _, command_record = store.poll_commands_raw(DEVICE_ID)
            self.assertIsNotNone(command_record)
            ingest_window(store, sample_bytes(), transport_type="wifi")
            ack_payload = encode_kv(
                {
                    "cmd_id": CMD_ID,
                    "status": "ok",
                    "message": "bounded real IMU window chunks and manifest uploaded over Wi-Fi",
                    "fw_version": "0.1.0-imu-unit",
                    "test_run_id": TEST_RUN_ID,
                    "transport_type": "wifi",
                }
            )
            ack_frame = message_hub.build_raw_frame("ack", CMD_ID, ack_payload)
            ack_record = store.ingest_raw_frame(
                DEVICE_ID,
                ack_frame,
                expected_frame_type="ack",
                expected_cmd_id=CMD_ID,
            )
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertEqual(ack_record["parse_result"]["status"], "ok")
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["raw_frames_scanned"], 13)
        self.assertEqual(result["summary"]["valid_windows"], 1)
        self.assertEqual(result["summary"]["invalid_windows"], 0)

    def test_semantically_invalid_chunk_is_retained_but_not_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            payload = chunk_payload(0, sample_bytes()).replace(b"samples_b64=", b"samples_b64=%%%")
            frame = message_hub.build_raw_frame("event", f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", payload, seq=1)
            record = store.ingest_raw_frame(DEVICE_ID, frame)
            raw_frames = store.list_raw_frames(DEVICE_ID)
            telemetry = store.telemetry_history(DEVICE_ID)

        self.assertEqual(record["parse_result"]["transport_status"], "ok")
        self.assertEqual(record["parse_result"]["status"], "malformed")
        self.assertEqual(record["parse_result"]["error_code"], "IMU_WINDOW_INVALID_BASE64")
        self.assertEqual(record["parse_result"]["payload_validation"]["status"], "invalid")
        self.assertEqual(len(raw_frames), 1)
        self.assertEqual(telemetry, [])

    def test_http_semantic_rejection_is_non_2xx_after_raw_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            payload = chunk_payload(0, sample_bytes()).replace(b"samples_b64=", b"samples_b64=%%%")
            frame = message_hub.build_raw_frame("event", f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", payload, seq=1)
            http_request = request.Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/devices/{DEVICE_ID}/raw-ingest",
                data=frame,
                method="POST",
                headers={"Content-Type": "text/x-egolink-frame; profile=raw-frame.p0.v1"},
            )
            try:
                with self.assertRaises(error.HTTPError) as raised:
                    request.urlopen(http_request, timeout=5)
                with closing(raised.exception):
                    response_status = raised.exception.code
                    response = json.loads(raised.exception.read().decode("utf-8"))
                raw_frames = store.list_raw_frames(DEVICE_ID)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(response_status, 422)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], "IMU_WINDOW_INVALID_BASE64")
        self.assertEqual(len(raw_frames), 1)
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "malformed")

    def test_http_mixed_transport_is_422_after_raw_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            create_capture_command(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            first_payload = chunk_payload(0, sample_bytes(), transport_type="wifi")
            first_frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                first_payload,
                seq=1,
            )
            mixed_payload = chunk_payload(1, sample_bytes(), transport_type="lte")
            mixed_frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c01",
                mixed_payload,
                seq=2,
            )

            def post(frame: bytes) -> dict[str, object]:
                http_request = request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/v1/devices/{DEVICE_ID}/raw-ingest",
                    data=frame,
                    method="POST",
                    headers={"Content-Type": "text/x-egolink-frame; profile=raw-frame.p0.v1"},
                )
                with closing(request.urlopen(http_request, timeout=5)) as response:
                    return json.loads(response.read().decode("utf-8"))

            try:
                first_response = post(first_frame)
                with self.assertRaises(error.HTTPError) as raised:
                    post(mixed_frame)
                with closing(raised.exception):
                    response_status = raised.exception.code
                    mixed_response = json.loads(raised.exception.read().decode("utf-8"))
                raw_frames = store.list_raw_frames(DEVICE_ID)
                telemetry = store.telemetry_history(DEVICE_ID)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(first_response["ok"])
        self.assertEqual(response_status, 422)
        self.assertEqual(mixed_response["error"], "IMU_WINDOW_MIXED_TRANSPORT")
        self.assertEqual(len(raw_frames), 2)
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "malformed")
        self.assertEqual(raw_frames[0]["parse_result"]["error_code"], "IMU_WINDOW_MIXED_TRANSPORT")
        self.assertTrue(all(frame["raw_payload"]["data_redacted"] for frame in raw_frames))
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["imu_window"]["transport_type"], "wifi")
        self.assertFalse(telemetry[0]["imu_window"]["training_allowed"])
        self.assertNotIn("samples_b64", json.dumps(telemetry))

    def test_http_bad_envelope_crc_is_non_2xx_after_raw_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            create_capture_command(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            payload = chunk_payload(0, sample_bytes())
            frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                payload,
                seq=1,
            ).replace(f"crc32={message_hub.crc32_hex(payload)}".encode(), b"crc32=00000000", 1)
            http_request = request.Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/devices/{DEVICE_ID}/raw-ingest",
                data=frame,
                method="POST",
                headers={"Content-Type": "text/x-egolink-frame; profile=raw-frame.p0.v1"},
            )
            try:
                with self.assertRaises(error.HTTPError) as raised:
                    request.urlopen(http_request, timeout=5)
                with closing(raised.exception):
                    response_status = raised.exception.code
                    response = json.loads(raised.exception.read().decode("utf-8"))
                raw_frames = store.list_raw_frames(DEVICE_ID)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(response_status, 422)
        self.assertEqual(response["error"], "RAW_FRAME_PAYLOAD_CRC_MISMATCH")
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "checksum_failed")

    def test_http_bad_raw_ack_is_non_2xx_and_command_stays_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            command = store.create_command(DEVICE_ID, {"cmd": "set_report_interval", "payload": {"interval_ms": 5000}})
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            payload = f"cmd_id={command['cmd_id']}\nstatus=ok\n".encode()
            frame = message_hub.build_raw_frame("ack", str(command["cmd_id"]), payload).replace(
                f"crc32={message_hub.crc32_hex(payload)}".encode(),
                b"crc32=00000000",
                1,
            )
            http_request = request.Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/devices/{DEVICE_ID}/commands/{command['cmd_id']}/ack.raw",
                data=frame,
                method="POST",
                headers={"Content-Type": "text/x-egolink-frame; profile=raw-frame.p0.v1"},
            )
            try:
                with self.assertRaises(error.HTTPError) as raised:
                    request.urlopen(http_request, timeout=5)
                with closing(raised.exception):
                    response_status = raised.exception.code
                commands = store.list_commands(DEVICE_ID)
                raw_frames = store.list_raw_frames(DEVICE_ID)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(response_status, 422)
        self.assertEqual(commands[0]["status"], "pending")
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "checksum_failed")

    def test_partial_chunk_telemetry_explicitly_blocks_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            create_capture_command(store)
            payload = chunk_payload(0, sample_bytes())
            frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                payload,
                seq=1,
            )
            record = store.ingest_raw_frame(DEVICE_ID, frame)
            telemetry = store.latest_telemetry(DEVICE_ID)

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertFalse(telemetry["imu_window"]["training_allowed"])
        self.assertEqual(telemetry["imu_window"]["privacy_class"], "engineering")
        self.assertNotIn("samples_b64", json.dumps(telemetry))

    def test_server_rejects_unsupported_transport_nondeterministic_or_oversized_parts(self) -> None:
        complete_samples = sample_bytes()
        cases: list[tuple[str, dict[str, object], str, int, str]] = []
        usb_fields = chunk_fields(0, complete_samples)
        usb_fields["transport_type"] = "usb"
        cases.append(("usb", usb_fields, f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", 1, "IMU_WINDOW_TRANSPORT_REQUIRED"))
        case_fields = chunk_fields(0, complete_samples, transport_type="WiFi")
        cases.append(("case", case_fields, f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", 1, "IMU_WINDOW_TRANSPORT_REQUIRED"))
        window_fields = chunk_fields(0, complete_samples)
        window_fields["window_id"] = "arbitrary-window"
        cases.append(("window", window_fields, f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", 1, "IMU_WINDOW_ID_MISMATCH"))
        frame_fields = chunk_fields(0, complete_samples)
        cases.append(("frame", frame_fields, "arbitrary-frame", 1, "IMU_WINDOW_FRAME_ID_MISMATCH"))
        seq_fields = chunk_fields(0, complete_samples)
        cases.append(("seq", seq_fields, f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", 99, "IMU_WINDOW_SEQUENCE_MISMATCH"))
        large_fields = chunk_fields(0, complete_samples)
        large_fields["filler"] = "x" * 1300
        cases.append(("large", large_fields, f"imu-{CMD_ID}-b{BOOT_COUNT}-c00", 1, "IMU_WINDOW_FRAME_TOO_LARGE"))

        for label, fields, frame_id, header_seq, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
                create_capture_command(store)
                frame = message_hub.build_raw_frame("event", frame_id, encode_kv(fields), seq=header_seq)
                record = store.ingest_raw_frame(DEVICE_ID, frame)
                self.assertEqual(record["parse_result"]["status"], "malformed")
                self.assertEqual(record["parse_result"]["error_code"], expected_error)
                self.assertEqual(store.telemetry_history(DEVICE_ID), [])

    def test_export_rejects_evidence_uploaded_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            ingest_window(store, sample_bytes(), expect_ok=False)
            create_capture_command(store)
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 0)
        self.assertIn("not authorized and accepted at ingress", json.dumps(result["invalid"]))

    def test_export_rejects_raw_integrity_metadata_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            ingest_window(store, sample_bytes())
            with closing(sqlite3.connect(db_path)) as db:
                db.execute("UPDATE raw_frames SET raw_payload_sha256 = ? WHERE id = 1", ("0" * 64,))
                db.commit()
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 0)
        self.assertIn("integrity metadata mismatch", json.dumps(result["invalid"]))

    def test_unsupported_contract_value_is_not_reflected_by_public_apis(self) -> None:
        marker = "SECRET_SAMPLE_BLOB"
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            fields = chunk_fields(0, sample_bytes())
            fields["contract_version"] = marker
            frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                encode_kv(fields),
                seq=1,
            )
            record = store.ingest_raw_frame(DEVICE_ID, frame)
            public_json = json.dumps(
                {
                    "raw_frames": store.list_raw_frames(DEVICE_ID),
                    "telemetry": store.telemetry_history(DEVICE_ID),
                }
            )

        self.assertEqual(record["parse_result"]["error_code"], "IMU_WINDOW_UNSUPPORTED_CONTRACT")
        self.assertNotIn(marker, public_json)

    def test_export_requires_an_existing_database_and_never_creates_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                export_imu_windows.export_imu_windows(
                    missing,
                    Path(tmp) / "export",
                    device_id=DEVICE_ID,
                    test_run_id=TEST_RUN_ID,
                )
            self.assertFalse(missing.exists())

    def test_export_complete_window_can_still_require_cadence_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            slow_samples = sample_bytes(interval_us=70_000)
            for index in range(message_hub.IMU_WINDOW_CHUNK_COUNT):
                payload = chunk_payload(index, slow_samples)
                frame = message_hub.build_raw_frame(
                    "event",
                    f"imu-{CMD_ID}-b{BOOT_COUNT}-c{index:02d}",
                    payload,
                    seq=index + 1,
                )
                self.assertEqual(store.ingest_raw_frame(DEVICE_ID, frame)["parse_result"]["status"], "ok")
            manifest = manifest_fields(slow_samples)
            manifest.update(
                {
                    "capture_end_uptime_us": 8_000_000,
                    "min_interval_us": 70_000,
                    "mean_interval_us": 70_000,
                    "max_interval_us": 70_000,
                    "deadline_miss_count": 99,
                }
            )
            manifest_frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-manifest",
                encode_kv(manifest),
                seq=message_hub.IMU_WINDOW_CHUNK_COUNT + 1,
            )
            self.assertEqual(store.ingest_raw_frame(DEVICE_ID, manifest_frame)["parse_result"]["status"], "ok")
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )
            exported = json.loads((tmp_path / "export" / "imu_windows.jsonl").read_text().splitlines()[0])

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["cadence_qualified_windows"], 0)
        self.assertEqual(exported["capture"]["cadence_quality_status"], "needs_review")
        self.assertIn("cadence_not_qualified", exported["training_blockers"])

    def test_export_rejects_offsets_outside_manifest_capture_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            complete_samples = sample_bytes()
            for index in range(message_hub.IMU_WINDOW_CHUNK_COUNT):
                payload = chunk_payload(index, complete_samples)
                frame = message_hub.build_raw_frame(
                    "event",
                    f"imu-{CMD_ID}-b{BOOT_COUNT}-c{index:02d}",
                    payload,
                    seq=index + 1,
                )
                self.assertEqual(store.ingest_raw_frame(DEVICE_ID, frame)["parse_result"]["status"], "ok")
            manifest = manifest_fields(complete_samples)
            manifest["capture_end_uptime_us"] = int(manifest["capture_start_uptime_us"]) + 1
            manifest_frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-manifest",
                encode_kv(manifest),
                seq=message_hub.IMU_WINDOW_CHUNK_COUNT + 1,
            )
            self.assertEqual(store.ingest_raw_frame(DEVICE_ID, manifest_frame)["parse_result"]["status"], "ok")
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertFalse(result["ok"])
        self.assertIn("sample offsets exceed manifest capture bounds", json.dumps(result["invalid"]))

    def test_export_rejects_missing_or_conflicting_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            complete_samples = sample_bytes()
            ingest_window(store, complete_samples, omit_chunk=3)
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 0)
        self.assertEqual(result["summary"]["invalid_windows"], 1)
        self.assertIn("chunk set mismatch", result["invalid"][0]["reason"])

    def test_export_rejects_conflicting_duplicate_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": TEST_RUN_ID})
            create_capture_command(store)
            complete_samples = sample_bytes()
            ingest_window(store, complete_samples)
            conflicting_payload = chunk_payload(0, sample_bytes(mutate_index=0))
            conflicting_frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                conflicting_payload,
                seq=1,
            )
            self.assertEqual(store.ingest_raw_frame(DEVICE_ID, conflicting_frame)["parse_result"]["status"], "ok")
            result = export_imu_windows.export_imu_windows(
                db_path,
                tmp_path / "export",
                device_id=DEVICE_ID,
                test_run_id=TEST_RUN_ID,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["valid_windows"], 0)
        self.assertIn("conflicting duplicate chunk 0", json.dumps(result["invalid"]))

    def test_capture_command_rejects_missing_or_extra_fixed_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            base = {
                "cmd": "capture_imu_window",
                "cmd_id": CMD_ID,
                "test_run_id": TEST_RUN_ID,
            }
            with self.assertRaises(message_hub.MessageHubError):
                store.create_command(DEVICE_ID, {**base, "payload": {"sample_count": 100}})
            with self.assertRaises(message_hub.MessageHubError):
                store.create_command(
                    DEVICE_ID,
                    {
                        **base,
                        "payload": {"sample_count": 100, "interval_ms": 50, "ignored": True},
                    },
                )

    def test_capture_ack_run_must_match_and_closed_command_cannot_authorize_new_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            command = create_capture_command(store)
            wrong_ack = protocol.ack_message(DEVICE_ID, "uptime_ms:10", 1, str(command["cmd_id"]), "ok")
            wrong_ack["test_run_id"] = "wrong-run"
            with self.assertRaises(message_hub.MessageHubError):
                store.ingest(DEVICE_ID, "ack", wrong_ack)
            self.assertEqual(store.list_commands(DEVICE_ID)[0]["status"], "pending")

            ack = protocol.ack_message(DEVICE_ID, "uptime_ms:11", 2, str(command["cmd_id"]), "ok")
            ack["test_run_id"] = TEST_RUN_ID
            store.ingest(DEVICE_ID, "ack", ack)
            fields = chunk_fields(0, sample_bytes(), boot_count=BOOT_COUNT + 1)
            frame = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT + 1}-c00",
                encode_kv(fields),
                seq=1,
            )
            record = store.ingest_raw_frame(DEVICE_ID, frame)

        self.assertEqual(record["parse_result"]["error_code"], "IMU_WINDOW_COMMAND_NOT_PENDING")

    def test_pending_capture_command_is_bound_to_its_first_boot_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            create_capture_command(store)
            first_payload = chunk_payload(0, sample_bytes())
            first = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT}-c00",
                first_payload,
                seq=1,
            )
            self.assertEqual(store.ingest_raw_frame(DEVICE_ID, first)["parse_result"]["status"], "ok")
            second_fields = chunk_fields(0, sample_bytes(), boot_count=BOOT_COUNT + 1)
            second = message_hub.build_raw_frame(
                "event",
                f"imu-{CMD_ID}-b{BOOT_COUNT + 1}-c00",
                encode_kv(second_fields),
                seq=1,
            )
            record = store.ingest_raw_frame(DEVICE_ID, second)

        self.assertEqual(record["parse_result"]["error_code"], "IMU_WINDOW_COMMAND_ALREADY_BOUND")


if __name__ == "__main__":
    unittest.main()
