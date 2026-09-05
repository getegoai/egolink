from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from pc_simulator.location_engine_v0 import LocationEngineV0
from server.location_state_mirror import LocationStateMirror
from server.location_state_runtime import LocationStateRuntimeMirror


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "location_state_emitter"
)
SOURCE = COMPONENT / "location_state_emitter.c"
HEADER = COMPONENT / "include" / "location_state_emitter.h"
CMAKE = COMPONENT / "CMakeLists.txt"

ENVELOPE_VERSION = "egolink.location_state_envelope.v0.1"
STATE_VERSION = "egolink.location_engine.v0.1"
POLICY_VERSION = "egolink.sensor_policy_config.v0.1"
POLICY_SEMANTIC = "egolink.sensor_policy.semantic.v0.1"
POLICY_CONFIG_ID = "p0-sprint1-engineering-default-20260823"
POLICY_CONFIG_HASH = (
    "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"
)
OUTBOX_ID_MAX = 128
ID_MAX = 256
STATE_MAX = 4096
ENVELOPE_MAX = 12288
INT64_MAX = (1 << 63) - 1


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _outside_string_whitespace(value: str) -> bool:
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in " \t\r\n":
            return True
    return False


def _text_valid(value: object, maximum: int = ID_MAX) -> bool:
    if not isinstance(value, str):
        return False
    encoded = value.encode("utf-8")
    return 0 < len(encoded) <= maximum


def _outbox_id_valid(value: object) -> bool:
    if not _text_valid(value, OUTBOX_ID_MAX):
        return False
    assert isinstance(value, str)
    return value.isascii() and value[0].isalnum() and all(
        character.isalnum() or character in "._:@-" for character in value
    )


def _state_valid(state_json: object, event_time_ms: int) -> bool:
    if not isinstance(state_json, str):
        return False
    encoded = state_json.encode("utf-8")
    if not 0 < len(encoded) <= STATE_MAX:
        return False
    if not state_json.startswith("{") or not state_json.endswith("}"):
        return False
    if _outside_string_whitespace(state_json):
        return False
    try:
        state = json.loads(state_json)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(state, dict)
        and state.get("contract_version") == STATE_VERSION
        and type(state.get("event_time_ms")) is int
        and state["event_time_ms"] == event_time_ms
        and "server_receive_time_ms" not in state
    )


def _emit_fixture(
    *,
    state_json: str,
    event_time_ms: int,
    event_time_ns: int,
    event_time_source: str = "timestamp_utc_ns",
    monotonic_clock_domain_id: str | None = None,
    device_id: str = "synthetic-device-001",
    boot_count: int = 7,
    session_id: str = "synthetic-session-001",
    sequence_id: int = 41,
    observation_id: str = "synthetic-state-041",
    policy_identity: dict[str, str] | None = None,
    capacity: int = ENVELOPE_MAX + 1,
) -> tuple[str, bytes]:
    """Contract fixture for the C seam; it is not a second product runtime."""

    wipe = bytes(min(max(capacity, 0), ENVELOPE_MAX + 1))
    if capacity <= 0:
        return "invalid_argument", wipe
    if (
        not _outbox_id_valid(device_id)
        or not _outbox_id_valid(session_id)
        or not _text_valid(observation_id)
        or not 0 <= boot_count <= INT64_MAX
        or not 0 <= sequence_id <= INT64_MAX
    ):
        return "invalid_identity", wipe
    sources = {
        "timestamp_utc_ns",
        "gnss_source_utc_ns",
        "timestamp_monotonic_ns",
    }
    clock_valid = (
        event_time_source in sources
        and event_time_ms >= 0
        and 0 <= event_time_ns <= INT64_MAX
        and event_time_ns // 1_000_000 == event_time_ms
        and (
            _text_valid(monotonic_clock_domain_id)
            if event_time_source == "timestamp_monotonic_ns"
            else monotonic_clock_domain_id is None
        )
    )
    if not clock_valid:
        return "invalid_clock", wipe

    identity = policy_identity or LocationStateRuntimeMirror().policy_identity
    policy_valid = (
        set(identity)
        == {"contract_version", "semantic_validation", "config_id", "config_hash"}
        and identity["contract_version"] == POLICY_VERSION
        and identity["semantic_validation"] == POLICY_SEMANTIC
        and identity["config_id"] == POLICY_CONFIG_ID
        and identity["config_hash"] == POLICY_CONFIG_HASH
        and re.fullmatch(r"[0-9a-f]{64}", identity["config_hash"]) is not None
    )
    if not policy_valid:
        return "invalid_policy_identity", wipe
    if not _state_valid(state_json, event_time_ms):
        return "invalid_location_state", wipe

    envelope = {
        "envelope_contract_version": ENVELOPE_VERSION,
        "device_id": device_id,
        "boot_count": boot_count,
        "session_id": session_id,
        "event_time_ms": event_time_ms,
        "event_time_source": event_time_source,
        "event_time_ns": event_time_ns,
        "monotonic_clock_domain_id": monotonic_clock_domain_id,
        "sequence_id": sequence_id,
        "observation_id": observation_id,
        "policy_identity": identity,
        "location_state": json.loads(state_json),
    }
    emitted = _compact(envelope).encode("utf-8")
    if len(emitted) > ENVELOPE_MAX or len(emitted) + 1 > capacity:
        return "overflow", wipe
    return "ok", emitted + b"\0"


def _unknown_state(event_time_ms: int) -> dict:
    return LocationEngineV0().snapshot(event_time_ms)


def _fine_state(event_time_ms: int) -> dict:
    engine = LocationEngineV0()
    return engine.process(
        {
            "event_type": "gnss_fix",
            "event_time_ms": event_time_ms,
            "latitude_deg": 22.543096,
            "longitude_deg": 114.057865,
            "accuracy_m": 12.0,
            "lineage": {
                "observation_id": "synthetic-gnss-fix-001",
                "source_status": "observed",
                "stream_id": "synthetic-gnss-stream",
                "sequence_id": 40,
                "device_run_id": "synthetic-device-run",
                "boot_count": 7,
                "timestamp_utc_ns": event_time_ms * 1_000_000,
            },
        }
    )


class LocationStateDeviceEmitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_component_is_isolated_and_transport_free(self) -> None:
        self.assertEqual('idf_component_register(\n    SRCS "location_state_emitter.c"\n    INCLUDE_DIRS "include"\n    REQUIRES json\n)\n', self.cmake)
        for forbidden in (
            "esp_http_client",
            "esp_wifi",
            "sim7670",
            "mqtt_client",
            "ESP_LOG",
            "gpio_",
            "nvs_",
            "freertos/",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_utc_spec_fixture_is_accepted_by_both_server_oracles(self) -> None:
        state = _fine_state(1_700_000_000_123)
        status, output = _emit_fixture(
            state_json=_compact(state),
            event_time_ms=state["event_time_ms"],
            event_time_ns=state["event_time_ms"] * 1_000_000,
        )
        self.assertEqual("ok", status)
        self.assertEqual(b"\0", output[-1:])
        envelope = json.loads(output[:-1])
        self.assertNotIn("server_receive_time_ms", envelope)
        self.assertEqual("accepted", LocationStateMirror().ingest(envelope)["status"])
        self.assertEqual(
            "accepted", LocationStateRuntimeMirror().ingest(envelope)["status"]
        )

        ordered_members = (
            "envelope_contract_version",
            "device_id",
            "boot_count",
            "session_id",
            "event_time_ms",
            "event_time_source",
            "event_time_ns",
            "monotonic_clock_domain_id",
            "sequence_id",
            "observation_id",
            "policy_identity",
            "location_state",
        )
        positions = [self.source.index(f'\\"{member}\\"') for member in ordered_members]
        self.assertEqual(sorted(positions), positions)

    def test_monotonic_spec_fixture_preserves_clock_domain(self) -> None:
        state = _unknown_state(2_345)
        status, output = _emit_fixture(
            state_json=_compact(state),
            event_time_ms=2_345,
            event_time_ns=2_345_999_999,
            event_time_source="timestamp_monotonic_ns",
            monotonic_clock_domain_id="boot-7-monotonic",
        )
        self.assertEqual("ok", status)
        envelope = json.loads(output[:-1])
        self.assertEqual("timestamp_monotonic_ns", envelope["event_time_source"])
        self.assertEqual("boot-7-monotonic", envelope["monotonic_clock_domain_id"])
        self.assertEqual(
            "accepted", LocationStateRuntimeMirror().ingest(envelope)["status"]
        )

    def test_clock_domain_and_nanosecond_binding_fail_closed(self) -> None:
        state_json = _compact(_unknown_state(10))
        cases = (
            dict(event_time_ns=9_999_999),
            dict(event_time_ns=10_000_000, monotonic_clock_domain_id="unexpected"),
            dict(
                event_time_ns=10_000_000,
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=None,
            ),
        )
        for changes in cases:
            with self.subTest(changes=changes):
                status, output = _emit_fixture(
                    state_json=state_json,
                    event_time_ms=10,
                    **changes,
                )
                self.assertEqual("invalid_clock", status)
                self.assertFalse(any(output))
        self.assertIn("event_time_ns / 1000000U != input->event_time_ms", self.source)

    def test_policy_identity_is_exact_and_lowercase_hash_bounded(self) -> None:
        state_json = _compact(_unknown_state(1))
        accepted = LocationStateRuntimeMirror().policy_identity
        self.assertEqual(
            POLICY_CONFIG_HASH,
            accepted["config_hash"],
        )
        for field, replacement in (
            ("contract_version", "egolink.sensor_policy_config.v9"),
            ("semantic_validation", "missing-semantic-validator"),
            ("config_id", "format-valid-but-not-deployed"),
            ("config_hash", accepted["config_hash"].upper()),
        ):
            identity = deepcopy(accepted)
            identity[field] = replacement
            status, output = _emit_fixture(
                state_json=state_json,
                event_time_ms=1,
                event_time_ns=1_000_000,
                policy_identity=identity,
            )
            with self.subTest(field=field):
                self.assertEqual("invalid_policy_identity", status)
                self.assertFalse(any(output))

        identity = deepcopy(accepted)
        identity["config_hash"] = "0" * 64
        status, output = _emit_fixture(
            state_json=state_json,
            event_time_ms=1,
            event_time_ns=1_000_000,
            policy_identity=identity,
        )
        self.assertEqual("invalid_policy_identity", status)
        self.assertFalse(any(output))

    def test_invalid_state_root_contract_event_binding_and_receive_time_rejected(self) -> None:
        base = _unknown_state(4)
        candidates = (
            "[]",
            " " + _compact(base),
            _compact({**base, "contract_version": "egolink.location_engine.v9"}),
            _compact({**base, "event_time_ms": 5}),
            _compact(base).replace('"event_time_ms":4', '"event_time_ms":4e0'),
            _compact({**base, "server_receive_time_ms": 99}),
        )
        for state_json in candidates:
            with self.subTest(prefix=state_json[:24]):
                status, output = _emit_fixture(
                    state_json=state_json,
                    event_time_ms=4,
                    event_time_ns=4_000_000,
                )
                self.assertEqual("invalid_location_state", status)
                self.assertFalse(any(output))
        self.assertIn('object_member_count(state, "server_receive_time_ms")', self.source)
        self.assertIn('top_level_u64_member(\n        state_json, "event_time_ms"', self.source)

    def test_identifier_state_and_output_bounds_clear_partial_output(self) -> None:
        state_json = _compact(_unknown_state(8))
        for identity_changes in (
            {"device_id": "x" * 129},
            {"device_id": "设备-一"},
            {"session_id": "session with spaces"},
            {"session_id": "-cannot-start-with-punctuation"},
        ):
            with self.subTest(identity_changes=identity_changes):
                status, output = _emit_fixture(
                    state_json=state_json,
                    event_time_ms=8,
                    event_time_ns=8_000_000,
                    **identity_changes,
                )
                self.assertEqual("invalid_identity", status)
                self.assertFalse(any(output))
        self.assertIn("valid_outbox_id(input->device_id)", self.source)
        self.assertIn("valid_outbox_id(input->session_id)", self.source)

        oversized_state = "{" + ("x" * STATE_MAX) + "}"
        status, output = _emit_fixture(
            state_json=oversized_state,
            event_time_ms=8,
            event_time_ns=8_000_000,
        )
        self.assertEqual("invalid_location_state", status)
        self.assertFalse(any(output))

        status, output = _emit_fixture(
            state_json=state_json,
            event_time_ms=8,
            event_time_ns=8_000_000,
            capacity=64,
        )
        self.assertEqual("overflow", status)
        self.assertEqual(bytes(64), output)
        self.assertIn("clear_output(output, output_capacity);", self.source)

    def test_sqlite_integer_fields_stop_at_int64_boundary(self) -> None:
        state_json = _compact(_unknown_state(INT64_MAX // 1_000_000))
        status, _ = _emit_fixture(
            state_json=state_json,
            event_time_ms=INT64_MAX // 1_000_000,
            event_time_ns=INT64_MAX,
            boot_count=INT64_MAX,
            sequence_id=INT64_MAX,
        )
        self.assertEqual("ok", status)

        cases = (
            {"event_time_ns": INT64_MAX + 1},
            {"boot_count": INT64_MAX + 1},
            {"sequence_id": INT64_MAX + 1},
        )
        for changes in cases:
            arguments = dict(
                state_json=_compact(_unknown_state(1)),
                event_time_ms=1,
                event_time_ns=1_000_000,
            )
            arguments.update(changes)
            status, output = _emit_fixture(**arguments)
            with self.subTest(changes=changes):
                self.assertIn(status, {"invalid_identity", "invalid_clock"})
                self.assertFalse(any(output))
        self.assertGreaterEqual(self.source.count("(uint64_t)INT64_MAX"), 3)

    def test_unknown_state_does_not_invent_coordinates_or_receive_time(self) -> None:
        state = _unknown_state(12)
        status, output = _emit_fixture(
            state_json=_compact(state),
            event_time_ms=12,
            event_time_ns=12_000_000,
        )
        self.assertEqual("ok", status)
        envelope = json.loads(output[:-1])
        self.assertIsNone(envelope["location_state"]["last_trusted_location"])
        self.assertEqual("Unknown", envelope["location_state"]["location_belief"])
        self.assertNotIn("server_receive_time_ms", envelope)
        self.assertNotIn("latitude_deg", self.source)
        self.assertNotIn("longitude_deg", self.source)
        self.assertNotIn('writer_literal(&writer, ",\\"server_receive_time_ms\\":")', self.source)

    def test_component_cross_compiles_with_esp_toolchain_when_available(self) -> None:
        compiler_candidates = [
            shutil.which("xtensa-esp32s3-elf-gcc"),
            Path(
                "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
                "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
            ),
        ]
        compiler = next(
            (Path(candidate) for candidate in compiler_candidates if candidate and Path(candidate).is_file()),
            None,
        )
        idf_candidates = [
            Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
            Path("C:/Espressif/v5.4.2/esp-idf"),
        ]
        idf_path = next(
            (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
            None,
        )
        if compiler is None or idf_path is None:
            self.skipTest("ESP cross compiler or IDF cJSON headers unavailable")

        with tempfile.TemporaryDirectory(prefix="egolink-loc-emitter-") as temp_dir:
            result = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{COMPONENT / 'include'}",
                    f"-I{idf_path / 'components' / 'json' / 'cJSON'}",
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(Path(temp_dir) / "location_state_emitter.o"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
