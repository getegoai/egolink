"""Static/spec coverage for the dormant SOS-010C device orchestrator.

The executable Python fixtures validate the shared safety-event schema and
branch invariants but do not execute the target C object. A cross-compile is
not flash, persistence, GPIO, location, call, Guardian, or P0-SOS evidence.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "sos_orchestrator"
)
SOURCE = COMPONENT / "sos_orchestrator.c"
HEADER = COMPONENT / "include" / "sos_orchestrator.h"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
SCHEMA_PATH = ROOT / "shared" / "contracts" / "safety_event.schema.json"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"


def _event_id(*, boot_count: int, sequence: int, edge_time_ms: int) -> str:
    return f"sos-b{boot_count}-q{sequence}-t{edge_time_ms}"


def _payload(
    *,
    device_id: str = "wearable-1",
    boot_count: int = 7,
    session_id: str = "boot-session-7",
    sequence: int = 41,
    edge_time_ms: int = 1_800_000_002_160,
    battery_percent: float | None = None,
    base_online: bool = False,
    upload_available: bool = False,
) -> tuple[str, bytes, dict]:
    if battery_percent is not None and (
        isinstance(battery_percent, bool)
        or not isinstance(battery_percent, (int, float))
        or not math.isfinite(float(battery_percent))
        or not 0 <= float(battery_percent) <= 100
    ):
        raise ValueError("invalid battery")
    event_id = _event_id(
        boot_count=boot_count, sequence=sequence, edge_time_ms=edge_time_ms
    )
    event = {
        "contract_version": "1.0.0",
        "event_id": event_id,
        "device_id": device_id,
        "timestamp_ms": edge_time_ms,
        "sequence": sequence,
        "event_type": "manual_sos",
        "priority": "critical",
        "source": "device_rule",
        "model_result": {
            "manual_input": True,
            "qualified_long_press": True,
            "time_source": "boot_monotonic_ms",
            "boot_count": boot_count,
            "session_id": session_id,
            "source_sequence": sequence,
        },
        "context": {
            "mode": "manual_sos",
            "battery_percent": (
                None if battery_percent is None else float(battery_percent)
            ),
            "base_online": base_online,
            "upload_available": upload_available,
        },
        "evidence": {
            "audio_clip_ref": None,
            "image_ref": None,
            "imu_window_ref": None,
            "location_fresh": False,
        },
        "privacy": {
            "privacy_mode": True,
            "raw_evidence_allowed": False,
            "retention_seconds": 86_400,
        },
    }
    encoded = json.dumps(event, separators=(",", ":")).encode("ascii")
    return event_id, encoded, event


def _contains_coordinate_key(value) -> bool:
    coordinate_keys = {
        "lat",
        "latitude",
        "latitude_deg",
        "lon",
        "lng",
        "longitude",
        "longitude_deg",
        "coordinates",
    }
    if isinstance(value, dict):
        return any(
            key.casefold() in coordinate_keys or _contains_coordinate_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_coordinate_key(child) for child in value)
    return False


def _branch_spec(*, persistence: bool, policy: bool, feedback: bool,
                 location: bool, call: bool) -> dict:
    """Order/failure oracle only; it is not another firmware runtime."""

    order = ["persistence"]
    results = {"persistence": persistence}
    for name, succeeded in (
        ("feedback", feedback),
        ("policy", policy),
        ("location", location),
        ("call", call),
    ):
        order.append(name)
        results[name] = succeeded
    return {"order": order, "results": results}


class SosOrchestratorFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.packet = PACKET.read_text(encoding="utf-8")

    def orchestrate_body(self) -> str:
        start = self.source.index(
            "egolink_sos_orchestration_status_t egolink_sos_orchestrate_edge("
        )
        end = self.source.index(
            "const char *egolink_sos_orchestration_status_name(", start
        )
        return self.source[start:end]

    def test_component_is_isolated_dormant_and_strict(self) -> None:
        self.assertIn('SRCS "sos_orchestrator.c"', self.cmake)
        self.assertIn(
            "REQUIRES sos_input persistent_priority_outbox location_policy_core",
            self.cmake,
        )
        for flag in (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
        ):
            self.assertIn(flag, self.cmake)
        for forbidden in (
            "app_main",
            "driver/gpio",
            "gpio_",
            "esp_http",
            "esp_wifi",
            "mqtt_client",
            "sim7670",
            "freertos/",
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("sos_orchestrator", APP_MAIN.read_text(encoding="utf-8"))

    def test_schema_relaxation_is_only_nullable_bounded_battery(self) -> None:
        battery = self.schema["properties"]["context"]["properties"][
            "battery_percent"
        ]
        self.assertEqual(["number", "null"], battery["type"])
        self.assertEqual(0, battery["minimum"])
        self.assertEqual(100, battery["maximum"])
        _, _, unknown = _payload(battery_percent=None)
        _, _, known = _payload(battery_percent=12.5)
        validator = Draft202012Validator(self.schema)
        validator.validate(unknown)
        validator.validate(known)
        self.assertIsNone(unknown["context"]["battery_percent"])
        with self.assertRaises(ValueError):
            _payload(battery_percent=float("nan"))
        with self.assertRaises(ValueError):
            _payload(battery_percent=101)

    def test_bounded_payload_is_contract_valid_coordinate_free_and_no_media(self) -> None:
        _, encoded, event = _payload(
            device_id="d" * 128,
            session_id="s" * 128,
            boot_count=(1 << 64) - 1,
            sequence=(1 << 64) - 1,
            edge_time_ms=(1 << 64) - 1,
            battery_percent=100,
            base_online=True,
            upload_available=True,
        )
        Draft202012Validator(self.schema).validate(event)
        self.assertLessEqual(len(encoded), 1024)
        self.assertFalse(_contains_coordinate_key(event))
        self.assertIsNone(event["evidence"]["audio_clip_ref"])
        self.assertIsNone(event["evidence"]["image_ref"])
        self.assertFalse(event["privacy"]["raw_evidence_allowed"])
        for forbidden in (b"secret", b"token", b"password"):
            self.assertNotIn(forbidden, encoded.lower())

    def test_identity_is_replay_stable_and_distinct_edges_are_distinct(self) -> None:
        first, first_payload, _ = _payload()
        replay, replay_payload, _ = _payload()
        second, _, _ = _payload(sequence=42, edge_time_ms=1_800_000_007_160)
        self.assertEqual(first, replay)
        self.assertEqual(first_payload, replay_payload)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^sos-b[0-9]+-q[0-9]+-t[0-9]+$")
        self.assertIn(
            '"sos-b%" PRIu64 "-q%" PRIu64 "-t%" PRIu64', self.source
        )

    def test_device_identity_is_frozen_at_init_and_used_by_payload_and_branches(self) -> None:
        init_start = self.source.index(
            "egolink_sos_orchestration_status_t egolink_sos_orchestrator_init("
        )
        init_end = self.source.index(
            "egolink_sos_orchestration_status_t egolink_sos_orchestrate_edge(",
            init_start,
        )
        init = self.source[init_start:init_end]
        self.assertIn("!safe_identifier(device_id)", init)
        self.assertIn("orchestrator->device_id, device_id", init)
        self.assertIn("orchestrator->device_id,\n        event_context", self.source)
        self.assertIn(".device_id = orchestrator->device_id", self.source)
        normalized = " ".join(self.header.replace("*", "").split()).casefold()
        for concept in (
            "payload identity",
            "injected outbox",
            "integration invariant",
            "no read api",
        ):
            self.assertIn(concept, normalized)

    def test_critical_enqueue_precedes_every_branch(self) -> None:
        body = self.orchestrate_body()
        enqueue_at = body.index("egolink_outbox_enqueue(")
        durable_at = body.index("orchestrator->callbacks.durable_ready(")
        feedback_at = body.index("result->local_feedback = attempt_feedback(")
        policy_at = body.index("attempt_policy(")
        location_at = body.index(
            "result->location_enqueue = attempt_location_enqueue("
        )
        call_at = body.index("attempt_call(orchestrator, &identity)")
        self.assertLess(enqueue_at, feedback_at)
        self.assertLess(enqueue_at, durable_at)
        self.assertLess(durable_at, feedback_at)
        self.assertIn(
            "if (persistence_succeeded(result->persistence_state))",
            body,
        )
        self.assertLess(feedback_at, policy_at)
        self.assertLess(policy_at, location_at)
        self.assertLess(location_at, call_at)
        for marker in (
            ".event_type = EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE",
            ".priority = EGOLINK_OUTBOX_PRIORITY_CRITICAL",
            ".payload_kind = EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON",
            "EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS",
            ".source_event_time_ms = edge->sos_edge_time_ms",
            ".source_sequence = event_context->source_sequence",
        ):
            self.assertIn(marker, body)

    def test_configured_durable_ready_failure_makes_result_partial(self) -> None:
        body = self.orchestrate_body()
        complete = body[body.index("const bool complete =") :]
        self.assertIn(
            "result->durable_ready == EGOLINK_SOS_BRANCH_SUCCEEDED",
            complete,
        )
        self.assertIn(
            "result->durable_ready == EGOLINK_SOS_BRANCH_NOT_CONFIGURED",
            complete,
        )
        # Configured false maps to FAILED and is intentionally absent from
        # the two accepted completeness states.
        self.assertNotIn(
            "result->durable_ready == EGOLINK_SOS_BRANCH_FAILED",
            complete,
        )

    def test_persistence_and_policy_failure_do_not_veto_other_branches(self) -> None:
        for failure in ("persistence", "policy"):
            values = dict(
                persistence=True,
                policy=True,
                feedback=True,
                location=True,
                call=True,
            )
            values[failure] = False
            result = _branch_spec(**values)
            self.assertEqual(
                ["persistence", "feedback", "policy", "location", "call"],
                result["order"],
            )
            self.assertTrue(result["results"]["feedback"])
            self.assertTrue(result["results"]["location"])
            self.assertTrue(result["results"]["call"])

        body = self.orchestrate_body()
        enqueue_at = body.index("egolink_outbox_enqueue(")
        branch_at = body.index("result->local_feedback = attempt_feedback(")
        self.assertNotIn("return", body[enqueue_at:branch_at])
        self.assertIn("EGOLINK_SOS_PERSISTENCE_OUTBOX_FAILED", body)
        self.assertIn("EGOLINK_SOS_ORCHESTRATION_PARTIAL_FAILURE", body)

    def test_policy_is_forced_to_sos_but_never_gates_location_or_call(self) -> None:
        policy_start = self.source.index("static void attempt_policy(")
        policy_end = self.source.index("static bool persistence_succeeded(")
        policy = self.source[policy_start:policy_end]
        self.assertIn("sos_snapshot.sos_active = true", policy)
        self.assertIn(".type = EGOLINK_LOCATION_POLICY_EVENT_SOS", policy)
        self.assertIn("egolink_location_policy_evaluate(", policy)

        body = self.orchestrate_body()
        branch_section = body[body.index("const egolink_sos_branch_identity_t"):]
        self.assertIn("attempt_location_enqueue(", branch_section)
        self.assertIn("attempt_call(", branch_section)
        self.assertNotRegex(
            branch_section,
            r"if\s*\([^)]*policy[^)]*\)\s*\{[^}]*attempt_(?:location|call)",
        )

    def test_location_and_call_requests_are_urgent_coordinate_free_metadata(self) -> None:
        for marker in (
            ".urgent = true",
            ".request_last_trusted = true",
            ".request_current = true",
            ".safety_event_ref = identity->event_id",
            ".manual_sos = true",
        ):
            self.assertIn(marker, self.source)
        for forbidden in ("latitude", "longitude", "coordinate"):
            self.assertNotIn(forbidden, self.source.casefold())
        result_definition = self.header[
            self.header.index("typedef struct {\n    char event_id"):
            self.header.index("} egolink_sos_orchestration_result_t;")
        ]
        self.assertNotIn("payload[", result_definition)
        self.assertNotIn("audio", result_definition.casefold())
        self.assertNotIn("image", result_definition.casefold())

    def test_low_battery_camera_and_ai_have_no_veto_surface(self) -> None:
        _, _, low = _payload(battery_percent=0)
        Draft202012Validator(self.schema).validate(low)
        spec = _branch_spec(
            persistence=True,
            policy=True,
            feedback=True,
            location=True,
            call=True,
        )
        self.assertTrue(all(spec["results"].values()))
        orchestrate_signature = self.header[
            self.header.index("egolink_sos_orchestrate_edge("):
            self.header.index(");", self.header.index("egolink_sos_orchestrate_edge("))
        ]
        self.assertNotIn("camera", orchestrate_signature.casefold())
        self.assertNotIn("ai", orchestrate_signature.casefold())
        body = self.orchestrate_body()
        self.assertNotIn("battery_percent <=", body)
        self.assertNotIn("battery_percent >=", body)

    def test_scratch_is_bounded_wiped_and_component_does_not_allocate(self) -> None:
        self.assertIn("volatile uint8_t *cursor", self.source)
        self.assertGreaterEqual(self.orchestrate_body().count("wipe_scratch("), 2)
        self.assertIn("PAYLOAD_MAX_BYTES + 1U", self.source)
        self.assertIn("EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES", self.source)
        self.assertIsNone(
            re.search(r"\b(?:malloc|calloc|realloc|free)\s*\(", self.source)
        )
        self.assertNotIn("cJSON", self.source)

    def test_single_owner_and_nonclaims_are_explicit(self) -> None:
        normalized = " ".join((self.header + self.packet).split()).casefold()
        for phrase in (
            "caller owns and serializes",
            "must not recursively enter",
            "at-least-once",
            "not exactly-once",
            "does not flash or execute",
            "cannot establish physical-button",
        ):
            self.assertIn(phrase, normalized)

    def test_actual_c_cross_compiles_for_esp32s3_with_warnings_as_errors(self) -> None:
        compiler_candidates = [
            shutil.which("xtensa-esp32s3-elf-gcc"),
            Path(
                "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
                "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
            ),
        ]
        compiler = next(
            (
                Path(candidate)
                for candidate in compiler_candidates
                if candidate and Path(candidate).is_file()
            ),
            None,
        )
        if compiler is None:
            self.skipTest("ESP32-S3 cross compiler unavailable")

        include_paths = (
            COMPONENT / "include",
            COMPONENT.parent / "sos_input" / "include",
            COMPONENT.parent / "persistent_priority_outbox" / "include",
            COMPONENT.parent / "location_policy_core" / "include",
        )
        with tempfile.TemporaryDirectory(prefix="egolink-sos-orchestrator-") as temp:
            output = Path(temp) / "sos_orchestrator.o"
            result = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-Wconversion",
                    "-Wformat=2",
                    "-Wshadow",
                    "-Wsign-conversion",
                    *(f"-I{path}" for path in include_paths),
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
