"""Focused LOC-021J checks for the dormant device location pipeline.

The ESP32-S3 compiler checks the actual C source and a full behavioral harness,
but this host cannot execute Xtensa objects. Python fixtures are contract/spec
oracles only: they are not target runtime, flash, reboot, storage durability,
network, Guardian-delivery, field, or P0-LOC evidence.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from jsonschema import Draft202012Validator

from pc_simulator.location_engine_v0 import LocationEngineV0
from pc_simulator.sensor_policy_v0 import SensorPolicyV0, load_sensor_policy_config
from quality_tests.test_location_state_device_emitter import _emit_fixture
from server.location_state_runtime import LocationStateRuntimeMirror


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "location_runtime_pipeline"
SOURCE = COMPONENT / "location_runtime_pipeline.c"
HEADER = COMPONENT / "include" / "location_runtime_pipeline.h"
CMAKE = COMPONENT / "CMakeLists.txt"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"
CONFIG = ROOT / "shared" / "config" / "sensor_policy_v0.json"
ENGINE_SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "location_engine_v0.schema.json").read_text(
        encoding="utf-8"
    )
)

INT64_MAX = (1 << 63) - 1
MAX_EVENT_TIME_MS = INT64_MAX // 1_000_000
MAX_EVENT_TIME_NS = MAX_EVENT_TIME_MS * 1_000_000
MAX_ID = "Z" * 48
MAX_REASONS = [
    "imu_observed_without_coordinate_derivation",
    "cell_observed_without_coordinate_derivation",
    "gnss_fix_rejected_invalid_measurement",
    "gnss_fix_rejected_reported_accuracy",
    "gnss_fix_rejected_untrusted_lineage",
    "last_trusted_retained_as_memory_only",
    "gnss_no_fix_preserved_last_trusted",
    "gnss_error_preserved_last_trusted",
]


def _constant(source: str, name: str) -> int:
    match = re.search(rf"#define\s+{re.escape(name)}\s+(\d+)U", source)
    if match is None:
        raise AssertionError(f"missing integer constant {name}")
    return int(match.group(1))


def _maximum_legal_state() -> dict:
    """Largest structured fixture used at the narrowed pipeline boundary."""

    return {
        "contract_version": "egolink.location_engine.v0.1",
        "event_time_ms": MAX_EVENT_TIME_MS,
        "last_event_type": "coarse_location",
        "mobility_state": "unknown",
        "gnss_state": "fix_rejected",
        "lte_state": "unavailable",
        "last_trusted_location": {
            "latitude_deg": -89.12345678901235,
            "longitude_deg": -179.12345678901235,
            "accuracy_m": 4999.999999999999,
            "uncertainty_at_fix_m": 4999.999999999999,
            "uncertainty_basis": "reference_bound",
            "source": "cell_reference",
            "evidence_ref": {
                "observation_id": MAX_ID,
                "source_status": "verified",
                "stream_id": MAX_ID,
                "sequence_id": INT64_MAX,
                "device_run_id": MAX_ID,
                "boot_count": INT64_MAX,
                "event_time_ms": MAX_EVENT_TIME_MS,
                "event_time_source": "timestamp_monotonic_ns",
                "capture_time_ns": MAX_EVENT_TIME_NS,
                "monotonic_clock_domain_id": MAX_ID,
                "reference_id": MAX_ID,
            },
        },
        "last_trusted_time_ms": MAX_EVENT_TIME_MS,
        "location_belief": "Coarse",
        "location_accuracy_m": 4999.999999999999,
        "location_accuracy_status": "source_reported",
        "location_confidence": 0.65,
        "location_confidence_basis": "rule_heuristic_v0",
        "location_confidence_calibrated": False,
        "location_source": "cell_reference",
        "location_uncertainty_m": 4999.999999999999,
        "location_uncertainty_basis": "reference_bound",
        "battery_state": "critical",
        "battery_percent": 99.99999999999999,
        "sensor_policy_state": "LOCATION_UNCERTAIN",
        "sos_active": True,
        "reason_codes": list(MAX_REASONS),
    }


def _native_serializer_lexical_upper_bound() -> bytes:
    """Mirror the C writer's lexical ceilings, deliberately over-validating.

    It includes every optional field simultaneously, five 48-byte trusted
    identity strings, eight 128-byte reason strings, 20-byte uint64s and
    31-byte doubles. Some combinations are mutually exclusive in a valid
    state, which makes this an upper bound rather than a representative state.
    """

    integer = "9" * 20
    number = "9" * 31
    identifier = "X" * 48
    reason = "R" * 128
    value = '{"contract_version":"egolink.location_engine.v0.1"'
    value += ',"event_time_ms":' + integer
    value += ',"last_event_type":"cell_observation"'
    value += ',"mobility_state":"unknown"'
    value += ',"gnss_state":"fix_rejected"'
    value += ',"lte_state":"unavailable"'
    value += ',"last_trusted_location":{"latitude_deg":' + number
    value += ',"longitude_deg":' + number
    value += ',"accuracy_m":' + number
    value += ',"uncertainty_at_fix_m":' + number
    value += ',"uncertainty_basis":"source_reported_accuracy"'
    value += ',"source":"cell_reference","evidence_ref":{'
    value += '"observation_id":"' + identifier + '"'
    value += ',"source_status":"verified","stream_id":"' + identifier + '"'
    value += ',"sequence_id":' + integer
    value += ',"device_run_id":"' + identifier + '"'
    value += ',"boot_count":' + integer
    value += ',"event_time_ms":' + integer
    value += ',"event_time_source":"timestamp_monotonic_ns"'
    value += ',"capture_time_ns":' + integer
    value += ',"monotonic_clock_domain_id":"' + identifier + '"'
    value += ',"reference_id":"' + identifier + '"}}'
    value += ',"last_trusted_time_ms":' + integer
    value += ',"location_belief":"Predicted"'
    value += ',"location_accuracy_m":' + number
    value += ',"location_accuracy_status":"source_reported"'
    value += ',"location_confidence":' + number
    value += ',"location_confidence_basis":"rule_heuristic_v0"'
    value += ',"location_confidence_calibrated":false'
    value += ',"location_source":"cell_reference"'
    value += ',"location_uncertainty_m":' + number
    value += ',"location_uncertainty_basis":"last_trusted_age_growth_rule_v0"'
    value += ',"battery_state":"critical","battery_percent":' + number
    value += ',"sensor_policy_state":"LOCATION_UNCERTAIN"'
    value += ',"sos_active":true,"reason_codes":['
    value += ",".join('"' + reason + '"' for _ in range(8)) + "]}"
    return value.encode("ascii")


def _capture(event_time_ms: int, observation_id: str) -> dict:
    return {
        "observation_id": observation_id,
        "source_status": "observed",
        "stream_id": "loc021j-host-stream",
        "sequence_id": event_time_ms,
        "device_run_id": "loc021j-host-run",
        "boot_count": 4,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
    }


class _TransactionOracle:
    """Tiny test-only oracle for the documented ordering/backpressure rule."""

    def __init__(self) -> None:
        self.last: tuple | None = None
        self.retry: tuple | None = None
        self.engine_commits = 0
        self.policy_commits = 0
        self.outbox_attempts = 0

    @staticmethod
    def _key(item: dict) -> tuple:
        identity = item["identity"]
        fingerprint = hashlib.sha256(
            json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
        ).digest()
        return (
            identity["sequence_id"],
            identity["observation_id"],
            identity["event_time_ms"],
            fingerprint,
        )

    def process(self, item: dict, *, publish: bool, enqueue: str = "ok") -> str:
        key = self._key(item)
        if self.retry is not None and key != self.retry:
            return "blocked_retry_required"
        if self.last is not None:
            if key[0] == self.last[0]:
                return "duplicate" if key == self.last else "identity_conflict"
            if key[0] < self.last[0]:
                return "sequence_regression"
            if key[1] == self.last[1]:
                return "identity_conflict"
        if publish:
            self.outbox_attempts += 1
            if enqueue not in {"ok", "duplicate"}:
                self.retry = key
                return "retry_required"
        self.last = key
        self.retry = None
        self.engine_commits += 1
        if item["event_type"] != "imu_sample":
            self.policy_commits += 1
        return "published" if publish else "no_publish"


def _oracle_item(sequence: int, event_type: str = "tick") -> dict:
    return {
        "identity": {
            "device_id": "loc021j-device",
            "boot_count": 1,
            "session_id": "loc021j-session",
            "stream_id": "loc021j-stream",
            "sequence_id": sequence,
            "observation_id": f"loc021j-{sequence}",
            "event_time_ms": sequence,
            "event_time_ns": sequence * 1_000_000,
        },
        "event_type": event_type,
        "value": sequence,
    }


def _esp_toolchain() -> tuple[Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (
            Path(candidate)
            for candidate in compiler_candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next(
        (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
        None,
    )
    if compiler is None or idf is None:
        return None
    return compiler, idf


def _include_paths(idf: Path) -> tuple[Path, ...]:
    return (
        COMPONENT / "include",
        COMPONENTS / "location_engine_core" / "include",
        COMPONENTS / "location_policy_core" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        idf / "components" / "json" / "cJSON",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
    )


def _cross_harness_source() -> str:
    return textwrap.dedent(
        r"""
        #include "location_runtime_pipeline.h"

        #include <stdint.h>
        #include <string.h>

        #define REQUIRE(condition) do { if (!(condition)) { return __LINE__; } } while (0)
        #define RUNTIME_TEXT(value) \
            (egolink_location_runtime_text_t){(value), sizeof(value) - 1U}
        #define ENGINE_TEXT(value) \
            (egolink_location_engine_text_t){(value), sizeof(value) - 1U}

        static const char ID48[] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        static egolink_outbox_t outbox;
        static egolink_location_outbox_adapter_t adapter;
        static egolink_location_runtime_pipeline_t pipeline;
        static egolink_location_runtime_scratch_t scratch;
        static egolink_location_runtime_result_t result;

        static egolink_location_runtime_input_t make_input(
            egolink_location_engine_event_type_t type,
            uint64_t sequence,
            uint64_t event_time_ms)
        {
            egolink_location_runtime_input_t item = {0};
            item.identity.device_id = RUNTIME_TEXT(ID48);
            item.identity.boot_count = UINT64_C(7);
            item.identity.session_id = RUNTIME_TEXT(ID48);
            item.identity.stream_id = RUNTIME_TEXT(ID48);
            item.identity.sequence_id = sequence;
            item.identity.observation_id = RUNTIME_TEXT(ID48);
            item.identity.event_time_ms = event_time_ms;
            item.identity.event_time_source =
                EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS;
            item.identity.event_time_ns = event_time_ms * UINT64_C(1000000);
            item.identity.monotonic_clock_domain_id = RUNTIME_TEXT(ID48);
            item.observation.type = type;
            item.observation.event_time_ms = event_time_ms;
            return item;
        }

        static void add_trusted_lineage(
            egolink_location_runtime_input_t *item)
        {
            item->observation.lineage.present = true;
            item->observation.lineage.observation_id = ENGINE_TEXT(ID48);
            item->observation.lineage.source_status =
                EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_VERIFIED;
            item->observation.lineage.stream_id_present = true;
            item->observation.lineage.stream_id = ENGINE_TEXT(ID48);
            item->observation.lineage.sequence_id_present = true;
            item->observation.lineage.sequence_id = item->identity.sequence_id;
            item->observation.lineage.device_run_id_present = true;
            item->observation.lineage.device_run_id = ENGINE_TEXT(ID48);
            item->observation.lineage.boot_count_present = true;
            item->observation.lineage.boot_count = item->identity.boot_count;
            item->observation.lineage.timestamp_monotonic_ns_present = true;
            item->observation.lineage.timestamp_monotonic_ns =
                item->identity.event_time_ns;
            item->observation.lineage.monotonic_clock_domain_id_present = true;
            item->observation.lineage.monotonic_clock_domain_id =
                ENGINE_TEXT(ID48);
        }

        static int maximum_serializer_shape_compiles(void)
        {
            egolink_location_engine_snapshot_t state = {0};
            char json[EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES + 1U];
            size_t length = 0U;
            state.event_time_ms = UINT64_C(9223372036854);
            state.last_event_initialized = true;
            state.last_event_type = EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION;
            state.mobility_state = EGOLINK_LOCATION_ENGINE_MOBILITY_UNKNOWN;
            state.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED;
            state.lte_state = EGOLINK_LOCATION_ENGINE_LTE_UNAVAILABLE;
            state.last_trusted_location_present = true;
            state.last_trusted_time_present = true;
            state.last_trusted_time_ms = state.event_time_ms;
            state.location_belief = EGOLINK_LOCATION_ENGINE_BELIEF_COARSE;
            state.location_accuracy_m_present = true;
            state.location_accuracy_source_reported = true;
            state.location_accuracy_m = 4999.999999999999;
            state.location_confidence = 0.65;
            state.location_source = EGOLINK_LOCATION_ENGINE_SOURCE_CELL_REFERENCE;
            state.location_uncertainty_m_present = true;
            state.location_uncertainty_m = 4999.999999999999;
            state.location_uncertainty_basis =
                EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND;
            state.battery_state = EGOLINK_LOCATION_ENGINE_BATTERY_CRITICAL;
            state.battery_percent_present = true;
            state.battery_percent = 99.99999999999999;
            state.sensor_policy_state =
                EGOLINK_LOCATION_ENGINE_POLICY_LOCATION_UNCERTAIN;
            state.sos_active = true;
            state.last_trusted_location.latitude_deg = -89.12345678901235;
            state.last_trusted_location.longitude_deg = -179.12345678901235;
            state.last_trusted_location.accuracy_m_present = true;
            state.last_trusted_location.accuracy_m = 4999.999999999999;
            state.last_trusted_location.uncertainty_at_fix_m = 4999.999999999999;
            state.last_trusted_location.uncertainty_basis =
                EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND;
            state.last_trusted_location.source =
                EGOLINK_LOCATION_ENGINE_SOURCE_CELL_REFERENCE;
            state.last_trusted_location.evidence_ref.source_status =
                EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_VERIFIED;
            state.last_trusted_location.evidence_ref.stream_id_present = true;
            state.last_trusted_location.evidence_ref.sequence_id_present = true;
            state.last_trusted_location.evidence_ref.sequence_id =
                UINT64_C(9223372036854775807);
            state.last_trusted_location.evidence_ref.device_run_id_present = true;
            state.last_trusted_location.evidence_ref.boot_count_present = true;
            state.last_trusted_location.evidence_ref.boot_count =
                UINT64_C(9223372036854775807);
            state.last_trusted_location.evidence_ref.event_time_ms =
                state.event_time_ms;
            state.last_trusted_location.evidence_ref.event_time_source =
                EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS;
            state.last_trusted_location.evidence_ref.capture_time_ns =
                UINT64_C(9223372036854000000);
            state.last_trusted_location.evidence_ref.monotonic_clock_domain_id_present = true;
            state.last_trusted_location.evidence_ref.reference_id_present = true;
            (void)memcpy(state.last_trusted_location.evidence_ref.observation_id.data,
                         ID48, sizeof(ID48) - 1U);
            state.last_trusted_location.evidence_ref.observation_id.length = sizeof(ID48) - 1U;
            (void)memcpy(state.last_trusted_location.evidence_ref.stream_id.data,
                         ID48, sizeof(ID48) - 1U);
            state.last_trusted_location.evidence_ref.stream_id.length = sizeof(ID48) - 1U;
            (void)memcpy(state.last_trusted_location.evidence_ref.device_run_id.data,
                         ID48, sizeof(ID48) - 1U);
            state.last_trusted_location.evidence_ref.device_run_id.length = sizeof(ID48) - 1U;
            (void)memcpy(state.last_trusted_location.evidence_ref.monotonic_clock_domain_id.data,
                         ID48, sizeof(ID48) - 1U);
            state.last_trusted_location.evidence_ref.monotonic_clock_domain_id.length = sizeof(ID48) - 1U;
            (void)memcpy(state.last_trusted_location.evidence_ref.reference_id.data,
                         ID48, sizeof(ID48) - 1U);
            state.last_trusted_location.evidence_ref.reference_id.length = sizeof(ID48) - 1U;
            state.reason_codes.count = EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT;
            state.reason_codes.values[0] = EGOLINK_LOCATION_ENGINE_REASON_IMU_NO_COORDINATE_DERIVATION;
            state.reason_codes.values[1] = EGOLINK_LOCATION_ENGINE_REASON_CELL_NO_COORDINATE_DERIVATION;
            state.reason_codes.values[2] = EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_INVALID_MEASUREMENT;
            state.reason_codes.values[3] = EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_REPORTED_ACCURACY;
            state.reason_codes.values[4] = EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_UNTRUSTED_LINEAGE;
            state.reason_codes.values[5] = EGOLINK_LOCATION_ENGINE_REASON_LAST_TRUSTED_MEMORY_ONLY;
            state.reason_codes.values[6] = EGOLINK_LOCATION_ENGINE_REASON_GNSS_NO_FIX_PRESERVED;
            state.reason_codes.values[7] = EGOLINK_LOCATION_ENGINE_REASON_GNSS_ERROR_PRESERVED;
            return egolink_location_engine_serialize_snapshot(
                       &state, json, sizeof(json), &length) ==
                           EGOLINK_LOCATION_ENGINE_OK &&
                       length <= EGOLINK_LOCATION_RUNTIME_STATE_JSON_PROVEN_MAX_BYTES
                       ? 0
                       : 1;
        }

        int main(void)
        {
            egolink_location_runtime_owner_t owner = {0};
            egolink_location_runtime_input_t item;
            egolink_location_runtime_status_t status;
            (void)memset(&adapter, 0, sizeof(adapter));
            adapter.outbox = &outbox;
            adapter.initialized = true;
            (void)memcpy(adapter.device_id, ID48, sizeof(ID48));
            owner.device_id = RUNTIME_TEXT(ID48);
            owner.boot_count = UINT64_C(7);
            owner.session_id = RUNTIME_TEXT(ID48);
            owner.stream_id = RUNTIME_TEXT(ID48);
            owner.clock_domain = EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC;
            owner.monotonic_clock_domain_id = RUNTIME_TEXT(ID48);
            REQUIRE(egolink_location_runtime_pipeline_init(
                        &pipeline, &adapter, &owner) ==
                    EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH);

            item = make_input(EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE,
                              UINT64_C(1), UINT64_C(1));
            status = egolink_location_runtime_pipeline_process(
                &pipeline, &item, UINT64_C(1), &scratch, &result);
            REQUIRE(status == EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH);
            REQUIRE(!result.policy_evaluated && !result.publish_required);
            REQUIRE(egolink_location_runtime_pipeline_process(
                        &pipeline, &item, UINT64_C(2), &scratch, &result) ==
                    EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT);

            item = make_input(EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX,
                              UINT64_C(2), UINT64_C(2));
            add_trusted_lineage(&item);
            item.observation.latitude_deg_present = true;
            item.observation.latitude_deg = 22.5;
            item.observation.longitude_deg_present = true;
            item.observation.longitude_deg = 114.0;
            item.observation.accuracy_m_present = true;
            item.observation.accuracy_m = 12.0;
            (void)egolink_location_runtime_pipeline_process(
                &pipeline, &item, UINT64_C(3), &scratch, &result);
            REQUIRE(maximum_serializer_shape_compiles() == 0);
            return 0;
        }
        """
    )


class LocationRuntimePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_component_is_dormant_single_owner_and_transport_free(self) -> None:
        self.assertIn('SRCS "location_runtime_pipeline.c"', self.cmake)
        for dependency in (
            "location_engine_core",
            "location_policy_core",
            "location_state_emitter",
            "location_outbox_adapter",
            "mbedtls",
        ):
            self.assertIn(dependency, self.cmake)
        for option in (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
        ):
            self.assertIn(option, self.cmake)
        for forbidden in (
            "esp_http",
            "esp_partition",
            "nvs_",
            "gpio_",
            "freertos/",
            "xtask",
            "esp_log",
            "socket(",
            "printf(",
            "latitude_deg\"",
            "longitude_deg\"",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("egolink_location_outbox_adapter_init(", self.source)
        self.assertNotIn("egolink_location_outbox_adapter_deinit(", self.source)
        self.assertNotIn("location_runtime_pipeline", (
            ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
        ).read_text(encoding="utf-8"))

    def test_complete_identity_precedes_reducers_and_adjacent_dedupe(self) -> None:
        body = self.source[self.source.index(
            "egolink_location_runtime_status_t egolink_location_runtime_pipeline_process("
        ):self.source.index(
            "const char *egolink_location_runtime_status_name(",
            self.source.index("egolink_location_runtime_status_t egolink_location_runtime_pipeline_process("),
        )]
        self.assertLess(body.index("validate_input(internal, input)"),
                        body.index("egolink_location_engine_process("))
        self.assertLess(body.index("input_fingerprint(input, fingerprint)"),
                        body.index("egolink_location_engine_process("))
        self.assertLess(body.index("EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT"),
                        body.index("egolink_location_engine_process("))
        for marker in (
            "device_id",
            "boot_count",
            "session_id",
            "stream_id",
            "sequence_id",
            "observation_id",
            "event_time_ms",
            "event_time_source",
            "event_time_ns",
            "monotonic_clock_domain_id",
        ):
            self.assertIn(marker, self.header)
        normalized = " ".join(self.header.split())
        self.assertIn("exactly one owner", normalized)
        self.assertIn("immediately adjacent exact replay", normalized)
        self.assertIn("persistent observation", normalized)
        self.assertIn("journal. Restart recovery/replay", normalized)
        self.assertIn("reboot equivalence is not claimed", normalized)

    def test_staged_reducers_imu_boundary_and_publish_rule_are_fixed(self) -> None:
        body = self.source[self.source.index(
            "egolink_location_runtime_status_t egolink_location_runtime_pipeline_process("
        ):]
        engine_at = body.index("&internal->staged_engine")
        policy_at = body.index("&internal->staged_policy")
        writeback_at = body.index("egolink_location_engine_set_policy_context(")
        resnapshot_at = body.index("egolink_location_engine_snapshot(")
        enqueue_at = body.index("egolink_location_outbox_emit_and_enqueue(")
        commit_at = body.index("commit_identity(internal, &candidate_identity")
        reducer_commit_at = body.index("internal->engine = internal->staged_engine")
        self.assertLess(engine_at, policy_at)
        self.assertLess(policy_at, writeback_at)
        self.assertLess(writeback_at, resnapshot_at)
        self.assertLess(resnapshot_at, enqueue_at)
        self.assertLess(enqueue_at, commit_at)
        self.assertLess(commit_at, reducer_commit_at)
        self.assertIn(
            "input->observation.type !=\n        EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE",
            body,
        )
        event_mapper = self.source[
            self.source.index("static bool policy_event_from_engine("):
            self.source.index("static bool engine_policy_mode(")
        ]
        self.assertIn("case EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE:\n        return false;", event_mapper)
        publish = self.source[
            self.source.index("static uint32_t publish_reasons("):
            self.source.index("static void clear_staging(")
        ]
        for marker in (
            "upload_location_now",
            "trusted_update_accepted",
            "EGOLINK_LOCATION_ENGINE_EVENT_SOS",
            "EGOLINK_LOCATION_RUNTIME_PUBLISH_INITIAL_CURRENT",
            "EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT",
        ):
            self.assertIn(marker, publish)

    def test_retry_barrier_rolls_back_and_exact_retry_eventually_commits(self) -> None:
        oracle = _TransactionOracle()
        first = _oracle_item(1, "gnss_fix")
        self.assertEqual(
            "retry_required", oracle.process(first, publish=True, enqueue="full")
        )
        self.assertEqual((0, 0, 1), (
            oracle.engine_commits, oracle.policy_commits, oracle.outbox_attempts
        ))
        self.assertEqual(
            "blocked_retry_required", oracle.process(_oracle_item(2), publish=False)
        )
        self.assertEqual(
            "published", oracle.process(deepcopy(first), publish=True, enqueue="ok")
        )
        self.assertEqual((1, 1, 2), (
            oracle.engine_commits, oracle.policy_commits, oracle.outbox_attempts
        ))
        self.assertEqual(
            "duplicate", oracle.process(deepcopy(first), publish=True, enqueue="ok")
        )
        self.assertEqual((1, 1, 2), (
            oracle.engine_commits, oracle.policy_commits, oracle.outbox_attempts
        ))

        second_oracle = _TransactionOracle()
        self.assertEqual(
            "published",
            second_oracle.process(first, publish=True, enqueue="duplicate"),
        )
        self.assertEqual(1, second_oracle.engine_commits)

        source = " ".join(self.source.split())
        self.assertIn("Materialize the already-validated commit identity", source)
        self.assertIn("before either reducer", source)
        self.assertIn("any durable enqueue", source)
        self.assertIn("static void commit_identity(", self.source)
        self.assertNotIn("if (!commit_identity(", self.source)

    def test_conflicting_or_old_identity_and_imu_are_not_reapplied(self) -> None:
        oracle = _TransactionOracle()
        imu = _oracle_item(10, "imu_sample")
        self.assertEqual("no_publish", oracle.process(imu, publish=False))
        self.assertEqual((1, 0, 0), (
            oracle.engine_commits, oracle.policy_commits, oracle.outbox_attempts
        ))
        conflict = deepcopy(imu)
        conflict["value"] = 999
        self.assertEqual("identity_conflict", oracle.process(conflict, publish=False))
        self.assertEqual("sequence_regression", oracle.process(_oracle_item(9), publish=False))
        self.assertEqual((1, 0, 0), (
            oracle.engine_commits, oracle.policy_commits, oracle.outbox_attempts
        ))

    def test_frozen_host_policy_only_requests_sparse_product_uploads(self) -> None:
        engine = LocationEngineV0()
        policy = SensorPolicyV0(load_sensor_policy_config(CONFIG))

        tick = {"event_type": "tick", "event_time_ms": 0}
        state = engine.process(tick)
        decision = policy.evaluate(state, event_type="tick", observation=tick)
        engine.set_policy_context(decision["policy_mode"])
        self.assertFalse(decision["actions"]["location"]["upload_now"])

        imu = {"event_type": "imu_sample", "event_time_ms": 1}
        engine.process(imu)
        # Firmware pipeline intentionally does not evaluate the policy here.

        fix = {
            "event_type": "gnss_fix",
            "event_time_ms": 2,
            "latitude_deg": 22.543096,
            "longitude_deg": 114.057865,
            "accuracy_m": 12.0,
            "evidence": _capture(2, "loc021j-host-fix"),
        }
        state = engine.process(fix)
        decision = policy.evaluate(state, event_type="gnss_fix", observation=fix)
        engine.set_policy_context(decision["policy_mode"])
        self.assertTrue(decision["actions"]["location"]["upload_now"])

        later_tick = {"event_type": "tick", "event_time_ms": 3}
        state = engine.process(later_tick)
        decision = policy.evaluate(state, event_type="tick", observation=later_tick)
        self.assertFalse(decision["actions"]["location"]["upload_now"])

    def test_maximum_ids_reasons_and_trusted_evidence_fit_outbox(self) -> None:
        state = _maximum_legal_state()
        self.assertEqual(8, len(state["reason_codes"]))
        self.assertTrue(all(len(value) == 48 for value in (
            state["last_trusted_location"]["evidence_ref"]["observation_id"],
            state["last_trusted_location"]["evidence_ref"]["stream_id"],
            state["last_trusted_location"]["evidence_ref"]["device_run_id"],
            state["last_trusted_location"]["evidence_ref"]["monotonic_clock_domain_id"],
            state["last_trusted_location"]["evidence_ref"]["reference_id"],
        )))
        Draft202012Validator(ENGINE_SCHEMA).validate(state)
        state_json = json.dumps(state, separators=(",", ":"))
        status, emitted = _emit_fixture(
            state_json=state_json,
            event_time_ms=MAX_EVENT_TIME_MS,
            event_time_ns=MAX_EVENT_TIME_NS,
            event_time_source="timestamp_monotonic_ns",
            monotonic_clock_domain_id=MAX_ID,
            device_id=MAX_ID,
            boot_count=INT64_MAX,
            session_id=MAX_ID,
            sequence_id=INT64_MAX,
            observation_id=MAX_ID,
            capacity=4097,
        )
        self.assertEqual("ok", status)
        payload = emitted[:-1]
        self.assertEqual(
            "accepted", LocationStateRuntimeMirror().ingest(json.loads(payload))["status"]
        )

        state_ceiling = _constant(
            self.header, "EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES"
        )
        proven_ceiling = _constant(
            self.header, "EGOLINK_LOCATION_RUNTIME_STATE_JSON_PROVEN_MAX_BYTES"
        )
        overhead = _constant(
            self.header, "EGOLINK_LOCATION_RUNTIME_ENVELOPE_OVERHEAD_MAX_BYTES"
        )
        lexical_bound = _native_serializer_lexical_upper_bound()
        self.assertEqual(2749, len(lexical_bound))
        self.assertLessEqual(len(lexical_bound), proven_ceiling)
        self.assertLessEqual(proven_ceiling, state_ceiling)
        self.assertLessEqual(state_ceiling + overhead, 4096)
        self.assertLessEqual(len(state_json.encode()), proven_ceiling)
        self.assertLessEqual(len(payload), 4096)

    def test_actual_source_and_behavioral_harness_cross_compile_for_esp32s3(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF headers unavailable")
        compiler, idf = toolchain
        flags = [
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            *(f"-I{path}" for path in _include_paths(idf)),
        ]
        with tempfile.TemporaryDirectory(prefix="egolink-loc021j-") as temporary:
            temp = Path(temporary)
            harness = temp / "location_runtime_pipeline_harness.c"
            harness.write_text(_cross_harness_source(), encoding="utf-8")
            commands = (
                [*flags, "-fstack-usage", "-c", str(SOURCE), "-o", str(temp / "pipeline.o")],
                [*flags, "-c", str(harness), "-o", str(temp / "harness.o")],
            )
            for command in commands:
                result = subprocess.run(
                    [str(compiler), *command],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
            stack = (temp / "pipeline.su").read_text(encoding="utf-8")
        process = re.search(
            r"egolink_location_runtime_pipeline_process\t(\d+)\t", stack
        )
        initialize = re.search(
            r"egolink_location_runtime_pipeline_init\t(\d+)\t", stack
        )
        self.assertIsNotNone(process)
        self.assertIsNotNone(initialize)
        self.assertLessEqual(int(process.group(1)), 640)
        self.assertLessEqual(int(initialize.group(1)), 640)

    def test_public_context_core_and_scratch_sizes_are_bounded_on_target(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF headers unavailable")
        compiler, idf = toolchain
        nm = compiler.with_name("xtensa-esp32s3-elf-nm.exe")
        if not nm.is_file():
            self.skipTest("ESP32-S3 nm unavailable")
        probe_source = textwrap.dedent(
            """
            #include "location_runtime_pipeline.h"
            unsigned char size_pipeline_context[sizeof(egolink_location_runtime_pipeline_t)];
            unsigned char size_pipeline_scratch[sizeof(egolink_location_runtime_scratch_t)];
            unsigned char size_engine_core[sizeof(egolink_location_engine_core_t)];
            unsigned char size_policy_core[sizeof(egolink_location_policy_core_t)];
            unsigned char size_pipeline_result[sizeof(egolink_location_runtime_result_t)];
            """
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc021j-size-") as temporary:
            temp = Path(temporary)
            probe = temp / "size_probe.c"
            object_path = temp / "size_probe.o"
            probe.write_text(probe_source, encoding="utf-8")
            compile_result = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    *(f"-I{path}" for path in _include_paths(idf)),
                    "-c",
                    str(probe),
                    "-o",
                    str(object_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, compile_result.returncode, compile_result.stderr)
            nm_result = subprocess.run(
                [str(nm), "-S", "--size-sort", str(object_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, nm_result.returncode, nm_result.stderr)
        sizes = {
            match.group(2): int(match.group(1), 16)
            for match in re.finditer(
                r"^[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+[A-Za-z]\s+(size_[A-Za-z0-9_]+)$",
                nm_result.stdout,
                re.MULTILINE,
            )
        }
        self.assertEqual(8192, sizes["size_pipeline_context"])
        self.assertEqual(3073 + 4097, sizes["size_pipeline_scratch"])
        self.assertLess(sizes["size_engine_core"], 4096)
        self.assertLess(sizes["size_policy_core"], 2048)
        self.assertLess(sizes["size_pipeline_result"], 2048)


if __name__ == "__main__":
    unittest.main()
