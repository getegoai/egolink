from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
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

from pc_simulator.location_engine_v0 import (
    LocationEngineConfig,
    LocationEngineError,
    LocationEngineV0,
)
from pc_simulator.sensor_policy_v0 import load_sensor_policy_config
from quality_tests.test_location_state_device_emitter import _emit_fixture
from server.location_state_runtime import LocationStateRuntimeMirror


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "location_engine_core"
)
SOURCE = COMPONENT / "location_engine_core.c"
HEADER = COMPONENT / "include" / "location_engine_core.h"
CMAKE = COMPONENT / "CMakeLists.txt"
CONFIG_PATH = ROOT / "shared" / "config" / "sensor_policy_v0.json"
SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "location_engine_v0.schema.json").read_text(
        encoding="utf-8"
    )
)
CONFIG_ID = "p0-sprint1-engineering-default-20260823"
CONFIG_HASH = "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"


def _capture_lineage(event_time_ms: int, *, source_status: str = "observed") -> dict:
    return {
        "observation_id": f"loc021h-capture-{event_time_ms}",
        "source_status": source_status,
        "stream_id": "loc021h-golden-stream",
        "sequence_id": event_time_ms,
        "device_run_id": "loc021h-spec-side",
        "boot_count": 7,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
    }


def _derived_lineage(event_time_ms: int, source: str = "policy_rule_v0") -> dict:
    return {
        "observation_id": f"loc021h-rule-{event_time_ms}",
        "source_status": "rule_derived",
        "event_time_source": source,
        "basis_observation_ids": [
            f"loc021h-basis-{event_time_ms}-a",
            f"loc021h-basis-{event_time_ms}-b",
        ],
    }


def _canonical_config_hash(document: dict) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _native_compiler() -> Path | None:
    candidates = (
        os.environ.get("CC"),
        shutil.which("gcc"),
        shutil.which("clang"),
        "C:/Program Files/LLVM/bin/clang.exe",
    )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(str(candidate)) or str(candidate)
        path = Path(resolved)
        lowered = path.name.lower()
        if (
            not path.is_file()
            or not ("gcc" in lowered or "clang" in lowered)
            or "xtensa" in lowered
            or "riscv" in lowered
        ):
            continue
        probe = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode == 0:
            return path
    return None


def _behavioral_harness_source() -> str:
    return textwrap.dedent(
        r"""
        #include "location_engine_core.h"

        #include <stdint.h>
        #include <stdio.h>
        #include <string.h>

        #define REQUIRE(condition)                                           \
            do {                                                             \
                if (!(condition)) {                                          \
                    (void)fprintf(stderr, "failed at line %d\n", __LINE__); \
                    return 1;                                                \
                }                                                            \
            } while (0)

        #define TEXT(literal)                                                 \
            (egolink_location_engine_text_t) {                               \
                .data = (literal), .length = sizeof(literal) - 1U            \
            }

        static egolink_location_engine_lineage_t capture(uint64_t time_ms)
        {
            egolink_location_engine_lineage_t value = {0};
            value.present = true;
            value.observation_id = TEXT("loc021h-capture");
            value.source_status =
                EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;
            value.stream_id_present = true;
            value.stream_id = TEXT("loc021h-stream");
            value.sequence_id_present = true;
            value.sequence_id = time_ms;
            value.device_run_id_present = true;
            value.device_run_id = TEXT("loc021h-run");
            value.boot_count_present = true;
            value.boot_count = UINT64_C(7);
            value.timestamp_utc_ns_present = true;
            value.timestamp_utc_ns = time_ms * UINT64_C(1000000);
            return value;
        }

        static egolink_location_engine_lineage_t derived(void)
        {
            egolink_location_engine_lineage_t value = {0};
            value.present = true;
            value.observation_id = TEXT("loc021h-derived");
            value.source_status =
                EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_RULE_DERIVED;
            value.derived_time_source_present = true;
            value.derived_time_source =
                EGOLINK_LOCATION_ENGINE_TIME_POLICY_ACTION_V0;
            value.basis_count = 2U;
            value.basis_observation_ids[0] = TEXT("imu-window-1");
            value.basis_observation_ids[1] = TEXT("policy-decision-1");
            return value;
        }

        static egolink_location_engine_observation_t event(
            egolink_location_engine_event_type_t type, uint64_t time_ms)
        {
            egolink_location_engine_observation_t value = {0};
            value.type = type;
            value.event_time_ms = time_ms;
            return value;
        }

        int main(void)
        {
            egolink_location_engine_config_t config;
            egolink_location_engine_core_t core = {0};
            egolink_location_engine_core_t before = {0};
            egolink_location_engine_snapshot_t state = {0};
            egolink_location_engine_observation_t item;
            egolink_location_engine_result_t result;
            char json[EGOLINK_LOCATION_ENGINE_CORE_JSON_MAX_BYTES + 1U];
            size_t json_length = 0U;

            egolink_location_engine_default_config(&config);
            REQUIRE(egolink_location_engine_validate_config(&config) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(egolink_location_engine_init(&core, &config) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(egolink_location_engine_snapshot(
                        &core, false, UINT64_C(0), &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.location_belief ==
                    EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN);
            REQUIRE(!state.last_trusted_location_present);
            REQUIRE(egolink_location_engine_serialize_snapshot(
                        &state, json, sizeof(json), &json_length) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(json_length > 0U && json[json_length] == '\0');

            item = event(EGOLINK_LOCATION_ENGINE_EVENT_TICK, UINT64_C(0));
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            /* Same-time processing is deliberate; identity dedupe is upstream. */
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);

            item = event(EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE, UINT64_C(1));
            item.latitude_deg_present = true;
            item.latitude_deg = 22.0;
            item.longitude_deg_present = true;
            item.longitude_deg = 114.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(!state.last_trusted_location_present);

            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_CELL_OBSERVATION, UINT64_C(2));
            item.latitude_deg_present = true;
            item.latitude_deg = 23.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(!state.last_trusted_location_present);
            REQUIRE(state.lte_state == EGOLINK_LOCATION_ENGINE_LTE_ONLINE);

            item = event(EGOLINK_LOCATION_ENGINE_EVENT_MOBILITY, UINT64_C(3));
            item.lineage = derived();
            item.mobility_state_present = true;
            item.mobility_state = EGOLINK_LOCATION_ENGINE_MOBILITY_MOVING;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);

            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STARTED, UINT64_C(4));
            item.lineage = derived();
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STOPPED, UINT64_C(5));
            item.lineage = capture(UINT64_C(5));
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX, UINT64_C(6));
            item.lineage = derived();
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR, UINT64_C(7));
            item.lineage = capture(UINT64_C(7));
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);

            item = event(EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX, UINT64_C(8));
            item.lineage = capture(UINT64_C(8));
            item.latitude_deg_present = true;
            item.latitude_deg = 22.543096;
            item.longitude_deg_present = true;
            item.longitude_deg = 114.057865;
            item.accuracy_m_present = true;
            item.accuracy_m = 12.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.location_belief == EGOLINK_LOCATION_ENGINE_BELIEF_FINE);
            REQUIRE(state.location_accuracy_source_reported);

            /* A bad explicit accuracy never falls through to good HDOP. */
            item = event(EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX, UINT64_C(9));
            item.lineage = capture(UINT64_C(9));
            item.latitude_deg_present = true;
            item.latitude_deg = 22.5;
            item.longitude_deg_present = true;
            item.longitude_deg = 114.0;
            item.accuracy_m_present = true;
            item.accuracy_m = 101.0;
            item.hdop_present = true;
            item.hdop = 1.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.gnss_state ==
                    EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED);
            REQUIRE(state.location_belief ==
                    EGOLINK_LOCATION_ENGINE_BELIEF_PREDICTED);
            REQUIRE(state.last_trusted_location_present);

            item = event(
                EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION, UINT64_C(10));
            item.lineage = capture(UINT64_C(10));
            item.lineage.source_status =
                EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_VERIFIED;
            item.reference_id_present = true;
            item.reference_id = TEXT("cell-reference-v1:A");
            item.coarse_source_present = true;
            item.coarse_source =
                EGOLINK_LOCATION_ENGINE_SOURCE_CELL_REFERENCE;
            item.latitude_deg_present = true;
            item.latitude_deg = 22.54;
            item.longitude_deg_present = true;
            item.longitude_deg = 114.05;
            item.accuracy_m_present = true;
            item.accuracy_m = 500.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.location_belief ==
                    EGOLINK_LOCATION_ENGINE_BELIEF_COARSE);

            item = event(EGOLINK_LOCATION_ENGINE_EVENT_LTE_STATE, UINT64_C(11));
            item.lte_state_present = true;
            item.lte_state = EGOLINK_LOCATION_ENGINE_LTE_LIMITED;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            item = event(EGOLINK_LOCATION_ENGINE_EVENT_BATTERY, UINT64_C(12));
            item.battery_state_present = true;
            item.battery_state = EGOLINK_LOCATION_ENGINE_BATTERY_LOW;
            item.battery_percent_present = true;
            item.battery_percent = 18.0;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            item = event(EGOLINK_LOCATION_ENGINE_EVENT_SOS, UINT64_C(13));
            item.sos_active_present = true;
            item.sos_active = true;
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.sos_active);
            REQUIRE(egolink_location_engine_set_policy_context(
                        &core, EGOLINK_LOCATION_ENGINE_POLICY_SOS) ==
                    EGOLINK_LOCATION_ENGINE_OK);

            /* A structural rejection rolls back and clears the snapshot. */
            before = core;
            item = event(EGOLINK_LOCATION_ENGINE_EVENT_MOBILITY, UINT64_C(14));
            item.mobility_state_present = true;
            item.mobility_state = EGOLINK_LOCATION_ENGINE_MOBILITY_STABLE;
            memset(&state, 0xa5, sizeof(state));
            result = egolink_location_engine_process(&core, &item, &state);
            REQUIRE(result == EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE);
            REQUIRE(memcmp(&before, &core, sizeof(core)) == 0);
            {
                const unsigned char *bytes = (const unsigned char *)&state;
                for (size_t index = 0U; index < sizeof(state); ++index) {
                    REQUIRE(bytes[index] == 0U);
                }
            }

            /* Event-time regression also rolls back. */
            item = event(EGOLINK_LOCATION_ENGINE_EVENT_TICK, UINT64_C(12));
            REQUIRE(egolink_location_engine_process(&core, &item, &state) ==
                    EGOLINK_LOCATION_ENGINE_TIME_REGRESSION);
            REQUIRE(memcmp(&before, &core, sizeof(core)) == 0);

            REQUIRE(egolink_location_engine_snapshot(
                        &core, true, UINT64_C(900011), &state) ==
                    EGOLINK_LOCATION_ENGINE_OK);
            REQUIRE(state.location_belief ==
                    EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN);
            {
                char small[8];
                size_t small_length = 99U;
                memset(small, 0xa5, sizeof(small));
                REQUIRE(egolink_location_engine_serialize_snapshot(
                            &state, small, sizeof(small), &small_length) ==
                        EGOLINK_LOCATION_ENGINE_OUTPUT_OVERFLOW);
                REQUIRE(small_length == 0U);
                for (size_t index = 0U; index < sizeof(small); ++index) {
                    REQUIRE(small[index] == '\0');
                }
            }
            (void)puts("loc021h-native-runtime-ok");
            return 0;
        }
        """
    )


class LocationEngineCoreFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.validator = Draft202012Validator(SCHEMA)

    def assert_schema_valid(self, state: dict) -> None:
        errors = sorted(
            self.validator.iter_errors(state), key=lambda error: error.json_path
        )
        self.assertEqual(
            [], [f"{error.json_path}: {error.message}" for error in errors]
        )

    def test_component_is_isolated_transport_free_and_bounded(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertTrue(HEADER.is_file())
        self.assertIn('SRCS "location_engine_core.c"', self.cmake)
        self.assertNotIn("REQUIRES", self.cmake)
        for token in (
            "EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES 256U",
            "EGOLINK_LOCATION_ENGINE_CORE_RULE_BASIS_MAX_COUNT 16U",
            "EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT 8U",
            "EGOLINK_LOCATION_ENGINE_CORE_JSON_MAX_BYTES 4096U",
            "caller-owned",
            "cleared",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.header)
        forbidden = (
            "esp_http_client",
            "esp_wifi",
            "mqtt_client",
            "nvs_flash",
            "gpio_",
            "xTaskCreate",
            "ESP_LOG",
            "app_main",
        )
        for token in forbidden:
            with self.subTest(forbidden=token):
                self.assertNotIn(token, self.source)

    def test_public_api_covers_all_host_event_and_state_dimensions(self) -> None:
        for token in (
            "EVENT_TICK",
            "EVENT_IMU_SAMPLE",
            "EVENT_MOBILITY",
            "EVENT_GNSS_STARTED",
            "EVENT_GNSS_STOPPED",
            "EVENT_GNSS_NO_FIX",
            "EVENT_GNSS_ERROR",
            "EVENT_GNSS_FIX",
            "EVENT_COARSE_LOCATION",
            "EVENT_LTE_STATE",
            "EVENT_CELL_OBSERVATION",
            "EVENT_BATTERY",
            "EVENT_SOS",
            "SOURCE_CELL_REFERENCE",
            "SOURCE_WIFI_REFERENCE",
            "SOURCE_KNOWN_PLACE",
            "TIME_GNSS_SOURCE_UTC_NS",
            "TIME_TIMESTAMP_UTC_NS",
            "TIME_TIMESTAMP_MONOTONIC_NS",
            "SOURCE_STATUS_RULE_DERIVED",
            "basis_observation_ids",
            "last_trusted_location",
            "sensor_policy_state",
            "sos_active",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.header)

    def test_frozen_native_profile_exactly_matches_accepted_host_defaults(self) -> None:
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(CONFIG_HASH, _canonical_config_hash(document))
        host_config = load_sensor_policy_config(CONFIG_PATH).location_engine_config()
        self.assertEqual(
            {
                "fine_max_accuracy_m": 100.0,
                "fine_max_hdop": 5.0,
                "hdop_uncertainty_multiplier_m": 5.0,
                "coarse_max_uncertainty_m": 5000.0,
                "fine_freshness_ms": 30_000,
                "coarse_freshness_ms": 120_000,
                "prediction_horizon_ms": 900_000,
                "uncertainty_growth_mps": 1.5,
                "fine_initial_confidence": 0.95,
                "coarse_initial_confidence": 0.65,
                "predicted_min_confidence": 0.1,
            },
            asdict(host_config),
        )
        self.assertIn(CONFIG_ID, self.header)
        self.assertIn(CONFIG_HASH, self.header)
        for field, literal in (
            ("fine_max_accuracy_m", "100.0"),
            ("fine_max_hdop", "5.0"),
            ("hdop_uncertainty_multiplier_m", "5.0"),
            ("coarse_max_uncertainty_m", "5000.0"),
            ("fine_freshness_ms", "30000"),
            ("coarse_freshness_ms", "120000"),
            ("prediction_horizon_ms", "900000"),
            ("uncertainty_growth_mps", "1.5"),
            ("fine_initial_confidence", "0.95"),
            ("coarse_initial_confidence", "0.65"),
            ("predicted_min_confidence", "0.10"),
        ):
            with self.subTest(field=field):
                self.assertRegex(
                    self.source,
                    rf"\.{field}\s*=\s*(?:UINT64_C\()?{re.escape(literal)}",
                )
                self.assertGreaterEqual(self.source.count(f"config->{field}"), 1)

    def test_host_golden_full_event_trace_and_schema_oracle(self) -> None:
        engine = LocationEngineV0()
        states = [engine.snapshot()]
        observations = [
            {"event_type": "tick", "event_time_ms": 0},
            {
                "event_type": "imu_sample",
                "event_time_ms": 1,
                "latitude_deg": 89.0,
                "longitude_deg": 179.0,
            },
            {
                "event_type": "cell_observation",
                "event_time_ms": 2,
                "latitude_deg": 88.0,
            },
            {
                "event_type": "mobility",
                "event_time_ms": 3,
                "mobility_state": "moving",
                "evidence": _derived_lineage(3),
            },
            {"event_type": "lte_state", "event_time_ms": 4, "lte_state": "limited"},
            {
                "event_type": "battery",
                "event_time_ms": 5,
                "battery_state": "low",
                "battery_percent": 18.0,
            },
            {"event_type": "sos", "event_time_ms": 6, "active": True},
            {
                "event_type": "gnss_started",
                "event_time_ms": 7,
                "evidence": _derived_lineage(7, "policy_action_v0"),
            },
            {
                "event_type": "gnss_stopped",
                "event_time_ms": 8,
                "evidence": _capture_lineage(8),
            },
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 9,
                "evidence": _derived_lineage(9, "policy_timer_v0"),
            },
            {
                "event_type": "gnss_error",
                "event_time_ms": 10,
                "evidence": _capture_lineage(10),
            },
            {
                "event_type": "gnss_fix",
                "event_time_ms": 11,
                "latitude_deg": 22.543096,
                "longitude_deg": 114.057865,
                "hdop": 1.4,
                "evidence": _capture_lineage(11),
            },
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 12,
                "evidence": _capture_lineage(12),
            },
            {
                "event_type": "gnss_fix",
                "event_time_ms": 13,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "accuracy_m": 101.0,
                "hdop": 1.0,
                "evidence": _capture_lineage(13),
            },
            {
                "event_type": "coarse_location",
                "event_time_ms": 14,
                "source": "cell_reference",
                "reference_id": "cell-reference-v1:A",
                "latitude_deg": 22.54,
                "longitude_deg": 114.05,
                "accuracy_m": 500.0,
                "evidence": _capture_lineage(14, source_status="verified"),
            },
        ]
        for observation in observations:
            states.append(engine.process(observation))
        for state in states:
            self.assert_schema_valid(state)

        self.assertTrue(all(state["last_trusted_location"] is None for state in states[:12]))
        self.assertEqual("Fine", states[12]["location_belief"])
        self.assertIsNone(states[12]["location_accuracy_m"])
        self.assertEqual(7.0, states[12]["location_uncertainty_m"])
        self.assertEqual("Predicted", states[13]["location_belief"])
        self.assertEqual("fix_rejected", states[14]["gnss_state"])
        self.assertEqual("Predicted", states[14]["location_belief"])
        self.assertEqual("Coarse", states[15]["location_belief"])
        self.assertEqual("cell_reference", states[15]["location_source"])
        self.assertTrue(states[15]["sos_active"])

    def test_representative_snapshot_is_compact_and_accepted_across_boundaries(self) -> None:
        event_time_ms = 1_700_000_001
        long_token = "x" * 180
        engine = LocationEngineV0()
        state = engine.process(
            {
                "event_type": "gnss_fix",
                "event_time_ms": event_time_ms,
                "latitude_deg": 22.543096,
                "longitude_deg": 114.057865,
                "accuracy_m": 12.0,
                "lineage": {
                    "observation_id": f"obs-{long_token}",
                    "source_status": "observed",
                    "stream_id": f"stream-{long_token}",
                    "sequence_id": 41,
                    "device_run_id": f"run-{long_token}",
                    "boot_count": 7,
                    "timestamp_utc_ns": event_time_ms * 1_000_000,
                },
            }
        )
        self.assert_schema_valid(state)
        state_json = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        self.assertFalse(any(character in state_json for character in "\n\r\t"))
        self.assertGreaterEqual(len(state_json.encode("utf-8")), 1_600)
        self.assertLessEqual(len(state_json.encode("utf-8")), 4_096)

        status, output = _emit_fixture(
            state_json=state_json,
            event_time_ms=event_time_ms,
            event_time_ns=event_time_ms * 1_000_000,
        )
        self.assertEqual("ok", status)
        envelope = json.loads(output[:-1])
        self.assertEqual(
            "accepted", LocationStateRuntimeMirror().ingest(envelope)["status"]
        )

    def test_host_reducer_rolls_back_and_equal_time_is_not_a_dedupe_claim(self) -> None:
        engine = LocationEngineV0()
        event = {
            "event_type": "mobility",
            "event_time_ms": 5,
            "mobility_state": "moving",
            "evidence": _derived_lineage(5),
        }
        first = engine.process(deepcopy(event))
        second = engine.process(deepcopy(event))
        self.assertEqual(first, second)
        before = engine.snapshot()
        with self.assertRaises(LocationEngineError):
            engine.process(
                {
                    "event_type": "coarse_location",
                    "event_time_ms": 6,
                    "source": "cell_reference",
                    "reference_id": "unbound",
                    "latitude_deg": 22.5,
                    "longitude_deg": 114.0,
                    "accuracy_m": 500.0,
                }
            )
        self.assertEqual(before, engine.snapshot())
        for contract_text in (
            "Equal event_time_ms is accepted",
            "does not provide exactly-once processing",
            "caller must serialize calls",
            "deduplicate reconnect/replay input",
            "boot/session/stream/",
            "sequence lineage",
        ):
            with self.subTest(contract_text=contract_text):
                self.assertIn(contract_text, self.header)

    def test_transactional_commit_and_privacy_failure_contract_are_explicit(self) -> None:
        process_start = self.source.index(
            "egolink_location_engine_result_t egolink_location_engine_process("
        )
        snapshot_start = self.source.index(
            "egolink_location_engine_result_t egolink_location_engine_snapshot(",
            process_start,
        )
        body = self.source[process_start:snapshot_start]
        self.assertIn("egolink_location_engine_core_t candidate = *core;", body)
        self.assertIn("memset(output, 0, sizeof(*output));", body)
        self.assertLess(body.index("build_snapshot(&candidate"), body.index("*core = candidate;"))
        self.assertRegex(
            body,
            re.compile(
                r"build_snapshot\(&candidate, observation->event_time_ms, output\);"
                r".*?if \(result != EGOLINK_LOCATION_ENGINE_OK\) \{"
                r".*?memset\(output, 0, sizeof\(\*output\)\);"
                r".*?return result;.*?\*core = candidate;",
                re.DOTALL,
            ),
        )
        self.assertIn("clear_output(output, output_capacity);", self.source)
        self.assertNotRegex(
            self.source,
            re.compile(r"\b(?:printf|fprintf|puts)\s*\("),
        )

    def test_native_behavioral_harness_if_host_compiler_exists(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable; C runtime not executed")
        with tempfile.TemporaryDirectory(prefix="egolink-loc-engine-native-") as temp_dir:
            temp = Path(temp_dir)
            harness = temp / "loc021h_behavior.c"
            executable = temp / (
                "loc021h_behavior.exe" if os.name == "nt" else "loc021h_behavior"
            )
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            command = [
                str(compiler),
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                f"-I{COMPONENT / 'include'}",
                str(SOURCE),
                str(harness),
                "-o",
                str(executable),
            ]
            if os.name != "nt":
                command.append("-lm")
            compiled = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, compiled.returncode, compiled.stderr)
            ran = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, ran.returncode, ran.stderr)
            self.assertEqual("loc021h-native-runtime-ok", ran.stdout.strip())

    def test_full_behavioral_harness_cross_compiles_for_esp32s3_with_werror(self) -> None:
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
        with tempfile.TemporaryDirectory(prefix="egolink-loc-engine-esp-") as temp_dir:
            temp = Path(temp_dir)
            harness = temp / "loc021h_behavior.c"
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            commands = (
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{COMPONENT / 'include'}",
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(temp / "location_engine_core.o"),
                ],
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{COMPONENT / 'include'}",
                    "-c",
                    str(harness),
                    "-o",
                    str(temp / "loc021h_behavior.o"),
                ],
            )
            for command in commands:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
