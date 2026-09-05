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

from pc_simulator.location_engine_v0 import LocationEngineV0
from pc_simulator.sensor_policy_v0 import SensorPolicyV0, load_sensor_policy_config


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "location_policy_core"
)
SOURCE = COMPONENT / "location_policy_core.c"
HEADER = COMPONENT / "include" / "location_policy_core.h"
CMAKE = COMPONENT / "CMakeLists.txt"
CONFIG_PATH = ROOT / "shared" / "config" / "sensor_policy_v0.json"

CONFIG_VERSION = "egolink.sensor_policy_config.v0.1"
SEMANTIC_VERSION = "egolink.sensor_policy.semantic.v0.1"
CONFIG_ID = "p0-sprint1-engineering-default-20260823"
CONFIG_HASH = "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"


def _lineage(event_time_ms: int) -> dict:
    return {
        "observation_id": f"loc021e-{event_time_ms}",
        "source_status": "observed",
        "stream_id": "loc021e-golden",
        "sequence_id": event_time_ms,
        "device_run_id": "loc021e-spec-side",
        "boot_count": 1,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
        "event_time_source": "capture_event",
    }


class _HostGoldenTrace:
    """Frozen host oracle driver; this never executes the firmware C core."""

    def __init__(self) -> None:
        self.config = load_sensor_policy_config(CONFIG_PATH)
        self.engine = LocationEngineV0(self.config.location_engine_config())
        self.policy = SensorPolicyV0(self.config)

    def apply(self, observation: dict) -> dict:
        item = deepcopy(observation)
        if item["event_type"] in {
            "gnss_started",
            "gnss_stopped",
            "gnss_fix",
            "gnss_no_fix",
            "gnss_error",
            "mobility",
            "coarse_location",
        }:
            item.setdefault("evidence", _lineage(item["event_time_ms"]))
        state = self.engine.process(item)
        decision = self.policy.evaluate(
            state,
            event_type=item["event_type"],
            observation=item,
        )
        self.engine.set_policy_context(decision["policy_mode"])
        return decision


def _spec_side_projection(decision: dict) -> dict:
    """Map host output to the public C shape; it is not C runtime evidence."""

    gnss_names = {
        "start": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_START",
        "continue": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_CONTINUE",
        "stop_timeout": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT",
        "wait_backoff": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_BACKOFF",
        "wait_interval": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_INTERVAL",
    }
    cell_names = {
        "observe": "EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE",
        "continue": "EGOLINK_LOCATION_POLICY_CELL_ACTION_CONTINUE",
        "timeout": "EGOLINK_LOCATION_POLICY_CELL_ACTION_TIMEOUT",
        "wait_backoff": "EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_BACKOFF",
        "wait_interval": "EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_INTERVAL",
    }
    actions = decision["actions"]
    runtime = decision["runtime"]
    return {
        "mode": f"EGOLINK_LOCATION_POLICY_{decision['policy_mode']}",
        "mobility": decision["derived_mobility_state"],
        "conditions": decision["conditions"],
        "imu_rate_hz": actions["imu"]["rate_hz"],
        "lte_keep_connected": actions["lte"]["keep_connected"],
        "gnss_action": gnss_names[actions["gnss"]["action"]],
        "gnss_timeout_ms": int(actions["gnss"]["acquisition_timeout_s"] * 1000),
        "gnss_retry_ms": actions["gnss"]["retry_not_before_ms"],
        "cell_action": cell_names[actions["cell"]["action"]],
        "cell_observe_now": actions["cell"]["observe_now"],
        "cell_interval_ms": int(actions["cell"]["interval_s"] * 1000),
        "cell_timeout_ms": int(actions["cell"]["request_timeout_s"] * 1000),
        "cell_retry_ms": actions["cell"]["retry_not_before_ms"],
        "upload_now": actions["location"]["upload_now"],
        "start_call": actions["ego_call"]["start_now"],
        "camera_requested": actions["camera"]["requested"],
        "next_evaluation_ms": decision["next_evaluation_ms"],
        "consecutive_no_fix": runtime["consecutive_no_fix"],
        "consecutive_cell_timeouts": runtime["consecutive_cell_timeouts"],
    }


def _native_c_compiler() -> Path | None:
    """Return a runnable host GCC/Clang, never the ESP cross compiler."""

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
        if not path.is_file() or not ("gcc" in lowered or "clang" in lowered):
            continue
        if "xtensa" in lowered or "riscv" in lowered:
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


def _native_harness_source() -> str:
    return textwrap.dedent(
        r"""
        #include "location_policy_core.h"

        #include <stdint.h>
        #include <stdio.h>
        #include <string.h>

        #define REQUIRE(condition)                                             \
            do {                                                               \
                if (!(condition)) {                                            \
                    (void)fprintf(stderr, "requirement failed at line %d\n",  \
                                  __LINE__);                                   \
                    return 1;                                                  \
                }                                                              \
            } while (0)

        static egolink_location_policy_snapshot_t base_snapshot(uint64_t now)
        {
            const egolink_location_policy_snapshot_t snapshot = {
                .event_time_ms = now,
                .mobility_state = EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN,
                .gnss_state = EGOLINK_LOCATION_POLICY_GNSS_IDLE,
                .battery_state = EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN,
                .location_belief = EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN,
            };
            return snapshot;
        }

        static egolink_location_policy_event_t make_event(
            egolink_location_policy_event_type_t type,
            uint64_t now,
            bool attributable_lineage)
        {
            const egolink_location_policy_event_t event = {
                .type = type,
                .event_time_ms = now,
                .attributable_lineage = attributable_lineage,
            };
            return event;
        }

        static int initialize(egolink_location_policy_core_t *core)
        {
            egolink_location_policy_config_t config;
            egolink_location_policy_default_config(&config);
            return egolink_location_policy_init(core, &config) ==
                           EGOLINK_LOCATION_POLICY_OK
                       ? 0
                       : 1;
        }

        int main(void)
        {
            egolink_location_policy_core_t core = {0};
            egolink_location_policy_core_t before = {0};
            egolink_location_policy_decision_t decision = {0};
            egolink_location_policy_snapshot_t snapshot = base_snapshot(0U);
            egolink_location_policy_event_t event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, 0U, false);
            egolink_location_policy_result_t result;

            /* Initial UNKNOWN belief selects UNCERTAIN and starts both paths. */
            REQUIRE(initialize(&core) == 0);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.policy_mode ==
                    EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN);
            REQUIRE(decision.gnss_action ==
                    EGOLINK_LOCATION_POLICY_GNSS_ACTION_START);
            REQUIRE(decision.cell_action ==
                    EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE);
            REQUIRE(decision.next_evaluation_available);
            REQUIRE(decision.next_evaluation_ms == UINT64_C(10000));

            /* Normal GNSS acquisition times out into bounded backoff. */
            snapshot = base_snapshot(UINT64_C(45000));
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, UINT64_C(45000), false);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.gnss_action ==
                    EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT);
            REQUIRE(decision.gnss_retry_not_before_available);
            REQUIRE(decision.gnss_retry_not_before_ms == UINT64_C(105000));
            snapshot = base_snapshot(UINT64_C(65000));
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, UINT64_C(65000), false);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.gnss_action ==
                    EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_BACKOFF);

            /* Equal-time duplicates are stateful; the caller must dedupe. */
            REQUIRE(initialize(&core) == 0);
            snapshot = base_snapshot(0U);
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, 0U, false);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            snapshot = base_snapshot(UINT64_C(1000));
            snapshot.gnss_state = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX,
                UINT64_C(1000),
                true);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.runtime.consecutive_no_fix == 1U);
            REQUIRE(decision.gnss_retry_not_before_ms == UINT64_C(61000));
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.runtime.consecutive_no_fix == 2U);
            REQUIRE(decision.gnss_retry_not_before_ms == UINT64_C(121000));

            /*
             * A GNSS failure and SOS appearing in the same normalized snapshot
             * applies the failure under the previous committed mode, exactly
             * like the host. SOS priority then starts GNSS immediately and is
             * not suppressed by the simultaneously latched critical battery.
             */
            REQUIRE(initialize(&core) == 0);
            snapshot = base_snapshot(0U);
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, 0U, false);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            snapshot = base_snapshot(UINT64_C(1000));
            snapshot.gnss_state = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
            snapshot.sos_active = true;
            snapshot.battery_state = EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL;
            snapshot.battery_percent_available = true;
            snapshot.battery_percent = 9.0;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX,
                UINT64_C(1000),
                true);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.transition_from ==
                    EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN);
            REQUIRE(decision.policy_mode == EGOLINK_LOCATION_POLICY_SOS);
            REQUIRE(decision.conditions.low_battery);
            REQUIRE(decision.conditions.critical_battery);
            REQUIRE(decision.gnss_action ==
                    EGOLINK_LOCATION_POLICY_GNSS_ACTION_START);
            REQUIRE(!decision.gnss_retry_not_before_available);
            REQUIRE(decision.runtime.consecutive_no_fix == 1U);
            REQUIRE(decision.upload_last_trusted_now);
            REQUIRE(decision.start_ego_call_now);

            /* Once SOS is committed, every failure uses the fixed 30 s retry. */
            snapshot = base_snapshot(UINT64_C(61000));
            snapshot.gnss_state = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
            snapshot.sos_active = true;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX,
                UINT64_C(61000),
                true);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.gnss_retry_not_before_ms == UINT64_C(91000));
            snapshot = base_snapshot(UINT64_C(91000));
            snapshot.sos_active = true;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, UINT64_C(91000), false);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.gnss_action ==
                    EGOLINK_LOCATION_POLICY_GNSS_ACTION_START);
            snapshot = base_snapshot(UINT64_C(151000));
            snapshot.gnss_state = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
            snapshot.sos_active = true;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX,
                UINT64_C(151000),
                true);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.gnss_retry_not_before_ms == UINT64_C(181000));

            /* Low-battery latch enters at 20, holds at 23, exits at 25. */
            REQUIRE(initialize(&core) == 0);
            snapshot = base_snapshot(1U);
            snapshot.location_belief = EGOLINK_LOCATION_POLICY_BELIEF_FINE;
            snapshot.battery_state = EGOLINK_LOCATION_POLICY_BATTERY_NORMAL;
            snapshot.battery_percent_available = true;
            snapshot.battery_percent = 20.0;
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_BATTERY, 1U, false);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.policy_mode == EGOLINK_LOCATION_POLICY_LOW_BATTERY);
            snapshot.event_time_ms = 2U;
            snapshot.battery_percent = 23.0;
            event.event_time_ms = 2U;
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(decision.conditions.low_battery);
            snapshot.event_time_ms = 3U;
            snapshot.battery_percent = 25.0;
            event.event_time_ms = 3U;
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            REQUIRE(!decision.conditions.low_battery);
            REQUIRE(decision.policy_mode == EGOLINK_LOCATION_POLICY_STABLE);

            /* Regression and overflow both leave the complete core untouched. */
            before = core;
            snapshot.event_time_ms = 2U;
            event.event_time_ms = 2U;
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_TIME_REGRESSION);
            REQUIRE(memcmp(&core, &before, sizeof(core)) == 0);

            REQUIRE(initialize(&core) == 0);
            snapshot = base_snapshot(0U);
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK, 0U, false);
            REQUIRE(egolink_location_policy_evaluate(
                        &core, &snapshot, &event, &decision) ==
                    EGOLINK_LOCATION_POLICY_OK);
            before = core;
            snapshot = base_snapshot(UINT64_MAX - UINT64_C(1000));
            event = make_event(
                EGOLINK_LOCATION_POLICY_EVENT_TICK,
                UINT64_MAX - UINT64_C(1000),
                false);
            result = egolink_location_policy_evaluate(
                &core, &snapshot, &event, &decision);
            REQUIRE(result == EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW);
            REQUIRE(memcmp(&core, &before, sizeof(core)) == 0);

            (void)puts("loc021e-native-runtime-ok");
            return 0;
        }
        """
    )
class LocationPolicyCoreFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.raw_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_component_is_dormant_transport_and_hardware_free(self) -> None:
        self.assertEqual(
            'idf_component_register(\n    SRCS "location_policy_core.c"\n'
            '    INCLUDE_DIRS "include"\n)\n',
            self.cmake,
        )
        combined = self.source + self.header
        for forbidden in (
            "app_main",
            "esp_http_client",
            "esp_wifi",
            "mqtt_client",
            "sim7670",
            "gpio_",
            "nvs_",
            "freertos/",
            "ESP_LOG",
            "latitude_deg",
            "longitude_deg",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_exact_accepted_identity_and_default_are_bound(self) -> None:
        canonical = json.dumps(
            self.raw_config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(CONFIG_HASH, hashlib.sha256(canonical).hexdigest())
        for value in (CONFIG_VERSION, SEMANTIC_VERSION, CONFIG_ID, CONFIG_HASH):
            self.assertIn(value, self.header)
        self.assertIn("accepted_default_config", self.source)
        self.assertIn("semantic_config_valid(config)", self.source)
        self.assertIn("exact_accepted_config(config)", self.source)
        self.assertIn("build-time frozen profile", self.header)
        self.assertIn("not a runtime JSON/config loader", self.header)

        expected_default_tokens = {
            ".gnss_interval_ms = 600000U": self.raw_config["stationary"]["gnss_interval_s"],
            ".cell_interval_ms = 300000U": self.raw_config["stationary"]["cell_interval_s"],
            ".acquisition_timeout_ms = 45000U": self.raw_config["gnss"]["acquisition_timeout_s"],
            ".request_timeout_ms = 10000U": self.raw_config["cell"]["request_timeout_s"],
            ".evidence_stale_after_ms = 10000U": self.raw_config["movement"]["evidence_stale_after_s"],
            ".prediction_horizon_ms = 900000U": self.raw_config["location"]["prediction_horizon_s"],
            ".gnss_retry_interval_ms = 30000U": self.raw_config["sos"]["gnss_retry_interval_s"],
        }
        for token, seconds in expected_default_tokens.items():
            with self.subTest(token=token):
                self.assertIn(token, self.source)
                self.assertGreaterEqual(float(seconds), 0.0)

    def test_public_api_covers_five_modes_actions_and_normalized_events(self) -> None:
        for token in (
            "EGOLINK_LOCATION_POLICY_STABLE",
            "EGOLINK_LOCATION_POLICY_MOVING",
            "EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN",
            "EGOLINK_LOCATION_POLICY_SOS",
            "EGOLINK_LOCATION_POLICY_LOW_BATTERY",
            "EGOLINK_LOCATION_POLICY_EVENT_GNSS_STARTED",
            "EGOLINK_LOCATION_POLICY_EVENT_GNSS_STOPPED",
            "EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX",
            "EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX",
            "EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR",
            "EGOLINK_LOCATION_POLICY_CELL_ACTION_TIMEOUT",
            "upload_last_trusted_now",
            "start_ego_call_now",
            "camera_requested",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.header)
        self.assertIn("Raw IMU samples are intentionally outside", self.header)

    def test_host_golden_initial_uncertain_actions_match_c_shape(self) -> None:
        trace = _HostGoldenTrace()
        projected = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 0})
        )
        self.assertEqual(
            {
                "mode": "EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN",
                "mobility": "unknown",
                "conditions": {
                    "sos_active": False,
                    "low_battery": False,
                    "critical_battery": False,
                    "location_uncertain": True,
                    "moving": False,
                },
                "imu_rate_hz": 10.0,
                "lte_keep_connected": True,
                "gnss_action": "EGOLINK_LOCATION_POLICY_GNSS_ACTION_START",
                "gnss_timeout_ms": 45_000,
                "gnss_retry_ms": None,
                "cell_action": "EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE",
                "cell_observe_now": True,
                "cell_interval_ms": 30_000,
                "cell_timeout_ms": 10_000,
                "cell_retry_ms": None,
                "upload_now": False,
                "start_call": False,
                "camera_requested": False,
                "next_evaluation_ms": 10_000,
                "consecutive_no_fix": 0,
                "consecutive_cell_timeouts": 0,
            },
            projected,
        )

    def test_host_golden_gnss_and_cell_timeout_backoff_recovery(self) -> None:
        trace = _HostGoldenTrace()
        initial = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 0})
        )
        cell_timeout = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 10_000})
        )
        cell_retry = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 30_000})
        )
        both_timeout = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 45_000})
        )
        waiting = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 65_000})
        )
        recovered = _spec_side_projection(
            trace.apply({"event_type": "tick", "event_time_ms": 105_000})
        )

        self.assertEqual("EGOLINK_LOCATION_POLICY_GNSS_ACTION_START", initial["gnss_action"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_CELL_ACTION_TIMEOUT", cell_timeout["cell_action"])
        self.assertEqual(30_000, cell_timeout["cell_retry_ms"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE", cell_retry["cell_action"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT", both_timeout["gnss_action"])
        self.assertEqual(105_000, both_timeout["gnss_retry_ms"])
        self.assertEqual(1, both_timeout["consecutive_no_fix"])
        self.assertEqual(2, both_timeout["consecutive_cell_timeouts"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_BACKOFF", waiting["gnss_action"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_BACKOFF", waiting["cell_action"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_GNSS_ACTION_START", recovered["gnss_action"])

    def test_host_golden_normal_no_fix_backoff_is_exponential_and_bounded(self) -> None:
        trace = _HostGoldenTrace()
        trace.apply({"event_type": "tick", "event_time_ms": 0})
        failures: list[tuple[int, int]] = []
        event_time_ms = 1_000
        for failure_index in range(1, 7):
            decision = trace.apply(
                {"event_type": "gnss_no_fix", "event_time_ms": event_time_ms}
            )
            retry_ms = decision["runtime"]["retry_not_before_ms"]
            self.assertIsInstance(retry_ms, int)
            failures.append((failure_index, retry_ms - event_time_ms))
            trace.apply({"event_type": "tick", "event_time_ms": retry_ms})
            event_time_ms = retry_ms + 1
        self.assertEqual(
            [60_000, 120_000, 240_000, 480_000, 900_000, 900_000],
            [delay for _, delay in failures],
        )

    def test_host_golden_low_battery_hysteresis_and_sos_priority(self) -> None:
        trace = _HostGoldenTrace()
        entered = trace.apply(
            {
                "event_type": "battery",
                "event_time_ms": 1,
                "battery_state": "normal",
                "battery_percent": 20,
            }
        )
        held = trace.apply(
            {
                "event_type": "battery",
                "event_time_ms": 2,
                "battery_state": "normal",
                "battery_percent": 23,
            }
        )
        exited = trace.apply(
            {
                "event_type": "battery",
                "event_time_ms": 3,
                "battery_state": "normal",
                "battery_percent": 25,
            }
        )
        trace.apply(
            {
                "event_type": "mobility",
                "event_time_ms": 4,
                "mobility_state": "moving",
            }
        )
        trace.apply(
            {
                "event_type": "battery",
                "event_time_ms": 5,
                "battery_state": "critical",
                "battery_percent": 9,
            }
        )
        sos = _spec_side_projection(
            trace.apply({"event_type": "sos", "event_time_ms": 6, "active": True})
        )

        self.assertEqual("LOW_BATTERY", entered["policy_mode"])
        self.assertTrue(held["conditions"]["low_battery"])
        self.assertFalse(exited["conditions"]["low_battery"])
        self.assertEqual("EGOLINK_LOCATION_POLICY_SOS", sos["mode"])
        self.assertTrue(sos["conditions"]["low_battery"])
        self.assertTrue(sos["conditions"]["critical_battery"])
        self.assertTrue(sos["conditions"]["moving"])
        self.assertEqual(20.0, sos["imu_rate_hz"])
        self.assertTrue(sos["lte_keep_connected"])
        self.assertTrue(sos["upload_now"])
        self.assertTrue(sos["start_call"])
        # The frozen host keeps an already-running acquisition alive on SOS
        # entry; immediate start applies only when GNSS is idle/backing off.
        self.assertEqual("EGOLINK_LOCATION_POLICY_GNSS_ACTION_CONTINUE", sos["gnss_action"])

    def test_host_golden_sos_retry_is_fixed_not_exponential(self) -> None:
        trace = _HostGoldenTrace()
        trace.apply({"event_type": "sos", "event_time_ms": 0, "active": True})
        first = trace.apply({"event_type": "gnss_no_fix", "event_time_ms": 60_000})
        trace.apply({"event_type": "tick", "event_time_ms": 90_000})
        second = trace.apply({"event_type": "gnss_no_fix", "event_time_ms": 150_000})
        self.assertEqual(90_000, first["runtime"]["retry_not_before_ms"])
        self.assertEqual(180_000, second["runtime"]["retry_not_before_ms"])
        self.assertEqual(2, second["runtime"]["consecutive_no_fix"])
        self.assertTrue(first["actions"]["location"]["upload_now"])
        self.assertFalse(first["actions"]["ego_call"]["start_now"])

    def test_host_golden_same_event_sos_failure_uses_previous_mode_ordering(self) -> None:
        trace = _HostGoldenTrace()
        trace.apply({"event_type": "tick", "event_time_ms": 0})
        observation = {
            "event_type": "gnss_no_fix",
            "event_time_ms": 1_000,
            "evidence": _lineage(1_000),
        }
        state = trace.engine.process(observation)
        # Model the device caller's normalized snapshot already carrying SOS
        # while the result event in that same snapshot is a GNSS failure.
        state["sos_active"] = True
        decision = trace.policy.evaluate(
            state,
            event_type="gnss_no_fix",
            observation=observation,
        )

        self.assertEqual("LOCATION_UNCERTAIN", decision["transition"]["from"])
        self.assertEqual("SOS", decision["policy_mode"])
        self.assertEqual("start", decision["actions"]["gnss"]["action"])
        self.assertIsNone(decision["runtime"]["retry_not_before_ms"])
        self.assertEqual(1, decision["runtime"]["consecutive_no_fix"])
        self.assertTrue(decision["actions"]["ego_call"]["start_now"])
        self.assertIn("previous) mode", self.source)
        self.assertIn(
            "runtime, config, event_time_ms, runtime->mode",
            self.source,
        )

    def test_duplicate_event_identity_is_explicitly_an_upstream_boundary(self) -> None:
        trace = _HostGoldenTrace()
        trace.apply({"event_type": "tick", "event_time_ms": 0})
        observation = {
            "event_type": "gnss_no_fix",
            "event_time_ms": 1_000,
            "evidence": _lineage(1_000),
        }
        state = trace.engine.process(observation)
        first = trace.policy.evaluate(
            state,
            event_type="gnss_no_fix",
            observation=observation,
        )
        second = trace.policy.evaluate(
            state,
            event_type="gnss_no_fix",
            observation=observation,
        )

        self.assertEqual(1, first["runtime"]["consecutive_no_fix"])
        self.assertEqual(2, second["runtime"]["consecutive_no_fix"])
        self.assertEqual(61_000, first["runtime"]["retry_not_before_ms"])
        self.assertEqual(121_000, second["runtime"]["retry_not_before_ms"])
        for contract_text in (
            "caller must",
            "serialize evaluations",
            "deduplicate reconnect/replay input",
            "boot/session/stream/sequence lineage",
            "does not provide exactly-once processing",
        ):
            with self.subTest(contract_text=contract_text):
                self.assertIn(contract_text, self.header)

    def test_host_golden_mobility_expires_at_configured_deadline(self) -> None:
        trace = _HostGoldenTrace()
        moving = trace.apply(
            {"event_type": "mobility", "event_time_ms": 0, "mobility_state": "moving"}
        )
        boundary = trace.apply({"event_type": "tick", "event_time_ms": 10_000})
        expired = trace.apply({"event_type": "tick", "event_time_ms": 10_001})
        self.assertEqual("moving", moving["derived_mobility_state"])
        # The outstanding first Cell observation times out before mobility
        # evidence expires, so it owns this particular wakeup.
        self.assertEqual(10_000, moving["next_evaluation_ms"])
        self.assertEqual("moving", boundary["derived_mobility_state"])
        self.assertEqual("unknown", expired["derived_mobility_state"])
        self.assertNotIn("accel_m_s2", self.header)

    def test_failure_paths_are_fail_closed_and_core_commit_is_last(self) -> None:
        self.assertIn("EGOLINK_LOCATION_POLICY_TIME_REGRESSION", self.source)
        self.assertIn("EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW", self.source)
        self.assertIn("add_u64_checked", self.source)
        self.assertIn("egolink_location_policy_core_t candidate = *core;", self.source)
        self.assertIn("memset(decision, 0, sizeof(*decision));", self.source)
        commit = self.source.rindex("*core = candidate;")
        next_evaluation = self.source.rindex("derive_next_evaluation(")
        self.assertGreater(commit, next_evaluation)
        self.assertRegex(
            self.source[commit : commit + 100],
            re.compile(r"\*core = candidate;\s+\*decision = staged;"),
        )

    def test_native_runtime_harness_executes_critical_behavior(self) -> None:
        compiler = _native_c_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable; C runtime not executed")

        with tempfile.TemporaryDirectory(prefix="egolink-loc-policy-native-") as temp_dir:
            temp = Path(temp_dir)
            harness_path = temp / "loc021e_native_harness.c"
            executable = temp / (
                "loc021e_native_harness.exe"
                if os.name == "nt"
                else "loc021e_native_harness"
            )
            harness_path.write_text(_native_harness_source(), encoding="utf-8")
            compile_result = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{COMPONENT / 'include'}",
                    str(SOURCE),
                    str(harness_path),
                    "-o",
                    str(executable),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, compile_result.returncode, compile_result.stderr)
            run_result = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, run_result.returncode, run_result.stderr)
            self.assertEqual("loc021e-native-runtime-ok", run_result.stdout.strip())

    def test_component_and_api_harness_cross_compile_with_warnings_as_errors(self) -> None:
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

        harness = _native_harness_source()
        with tempfile.TemporaryDirectory(prefix="egolink-loc-policy-") as temp_dir:
            temp = Path(temp_dir)
            harness_path = temp / "loc021e_api_harness.c"
            harness_path.write_text(harness, encoding="utf-8")
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
                    str(temp / "location_policy_core.o"),
                ],
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{COMPONENT / 'include'}",
                    "-c",
                    str(harness_path),
                    "-o",
                    str(temp / "loc021e_api_harness.o"),
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
