"""Focused LOC-021L checks for the dormant hardware adaptation boundary.

No test starts a task, opens UART, calls a real sensor/modem API, contacts a
network, or mutates hardware. The actual source and an API harness are strictly
cross-compiled/relocatable-linked for ESP32-S3; target code is not executed.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "location_hardware_adapter"
HEADER = COMPONENT / "include" / "location_hardware_adapter.h"
SOURCE = COMPONENT / "location_hardware_adapter.c"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"


def _toolchain() -> tuple[Path, Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (Path(value) for value in compiler_candidates if value and Path(value).is_file()),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next(
        (value for value in idf_candidates if value and value.is_dir()), None
    )
    configs = sorted((ROOT / "tmp").glob("*/config/sdkconfig.h"))
    if compiler is None or idf is None or not configs:
        return None
    return compiler, idf, configs[-1].parent


def _include_paths(idf: Path, config: Path) -> tuple[Path, ...]:
    return (
        config,
        COMPONENT / "include",
        COMPONENTS / "device_location_runtime" / "include",
        COMPONENTS / "location_runtime_pipeline" / "include",
        COMPONENTS / "location_engine_core" / "include",
        COMPONENTS / "location_policy_core" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "platform_imu" / "include",
        COMPONENTS / "sim7670_gnss" / "include",
        idf / "components" / "esp_common" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
    )


def _function(source: str, name: str, next_name: str) -> str:
    start = source.index(name)
    end = source.index(next_name, start)
    return source[start:end]


class LocationHardwareAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_component_is_default_off_and_not_wired_into_app_main(self) -> None:
        self.assertIn('SRCS "location_hardware_adapter.c"', self.cmake)
        for dependency in (
            "device_location_runtime",
            "platform_imu",
            "sim7670_gnss",
            "mbedtls",
        ):
            self.assertIn(dependency, self.cmake)
        default = _function(
            self.source,
            "void egolink_location_hardware_actuator_default_config(",
            "bool egolink_location_hardware_actuator_init(",
        )
        self.assertIn("config->enabled = false", default)
        self.assertNotIn("location_hardware_adapter", APP_MAIN.read_text(encoding="utf-8"))

    def test_source_identity_is_explicit_monotonic_and_receive_time_is_absent(self) -> None:
        normalized = " ".join(self.header.split())
        for field in (
            "device_id",
            "boot_count",
            "session_id",
            "stream_id",
            "sequence_id",
            "observation_id",
            "source_event_time_ms",
            "source_event_time_ns",
            "monotonic_clock_domain_id",
        ):
            self.assertIn(field, normalized)
        self.assertNotIn("receive_time", self.header.casefold())
        identity = _function(self.source, "static bool valid_identity(", "static void bind_lineage_clock(")
        self.assertIn("EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS", identity)
        self.assertIn("source_event_time_ns / UINT64_C(1000000)", identity)
        self.assertNotIn("GNSS_SOURCE_UTC", identity)

    def test_gnss_requires_parse_evidence_and_never_reuses_coordinates(self) -> None:
        body = _function(
            self.source,
            "egolink_location_hardware_map_gnss(",
            "static const char *expected_lte_reason(",
        )
        self.assertIn("EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_UNVERIFIED_RESULT", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR", body)
        self.assertIn("EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_NO_FIX_OBSERVED", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX", body)
        self.assertIn("report->location_result_valid && report->no_fix_observed", body)
        self.assertIn('"query_unverified"', body)
        fix_assignment = body.index("EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_FIX_CANDIDATE")
        for token in (
            "report->lat_valid",
            "report->lon_valid",
            "isfinite(report->lat)",
            "isfinite(report->lon)",
            "report->hdop_valid",
            "report->source_status",
        ):
            self.assertLess(body.index(token), fix_assignment)
        self.assertNotIn("accuracy_m_present = true", body)

    def test_lte_negative_states_require_matching_parse_evidence(self) -> None:
        body = _function(
            self.source,
            "static egolink_location_engine_lte_state_t lte_state(",
            "egolink_location_hardware_map_status_t\negolink_location_hardware_map_lte_state(",
        )
        self.assertIn("EGOLINK_LOCATION_ENGINE_LTE_ONLINE", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_LTE_UNAVAILABLE", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_LTE_OFFLINE", body)
        self.assertIn("EGOLINK_LOCATION_ENGINE_LTE_LIMITED", body)
        for evidence, negative in (
            ("report->cpin_query.parse_valid", "!report->sim_ready"),
            ("report->cereg_query.parse_valid", "!report->registered"),
            ("report->cgatt_query.parse_valid", "!report->attached"),
            ("report->cgact_query.parse_valid", "report->pdp_active ?"),
        ):
            self.assertLess(body.index(evidence), body.index(negative))

    def test_cell_reference_is_device_scoped_pseudonym_not_anonymization(self) -> None:
        cell = _function(
            self.source,
            "static bool build_cell_reference(",
            "egolink_location_hardware_map_status_t\negolink_location_hardware_map_cell(",
        )
        self.assertIn('"egolink.cell.reference.v1"', cell)
        self.assertIn('"cell:v1:"', cell)
        self.assertIn("mbedtls_sha256_finish", cell)
        self.assertIn("20U", cell)
        self.assertIn("device_scope", cell)
        self.assertIn("canonical_lowercase", self.source)
        for field in ("mcc", "mnc", "tac", "cell_id"):
            self.assertIn(f"report->{field}", cell)
        mapped = _function(
            self.source,
            "egolink_location_hardware_map_cell(",
            "egolink_location_hardware_map_imu(",
        )
        for coordinate in ("latitude", "longitude", "accuracy", "uncertainty"):
            self.assertNotIn(coordinate, mapped.casefold())
        for private_field in ("assigned_ip", "operator_name", "raw_response"):
            self.assertNotIn(private_field, mapped)
        normalized = " ".join(self.header.split())
        for warning in (
            "device-scoped pseudonymous fingerprint",
            "not keyed, anonymous",
            "dictionary recovery",
            "location-evidence domain",
        ):
            self.assertIn(warning, normalized)

    def test_mock_imu_and_battery_are_rejected_without_mobility_fabrication(self) -> None:
        imu = _function(
            self.source,
            "egolink_location_hardware_map_imu(",
            "egolink_location_hardware_map_battery(",
        )
        self.assertIn("sample->sample_is_mock", imu)
        self.assertIn("EGOLINK_LOCATION_HARDWARE_MAP_MOCK_REJECTED", imu)
        self.assertIn('sizeof("qmi8658_i2c")', imu)
        self.assertIn('"qmi8658_i2c"', imu)
        self.assertNotIn("EGOLINK_LOCATION_RUNTIME_ID_CAPACITY", imu)
        self.assertIn("sample->uptime_ms", imu)
        self.assertIn("EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE", imu)
        self.assertNotIn("MOBILITY", imu)
        battery = _function(
            self.source,
            "egolink_location_hardware_map_battery(",
            "const char *egolink_location_hardware_map_status_name(",
        )
        self.assertIn("battery->value_is_mock", battery)
        self.assertIn("battery->percent_present", battery)
        self.assertNotIn("= 87", battery)

    def test_init_overwrites_uninitialized_pattern_before_any_read(self) -> None:
        initialize = _function(
            self.source,
            "bool egolink_location_hardware_actuator_init(",
            "bool egolink_location_hardware_actuator_callbacks(",
        )
        self.assertNotIn("valid_actuator", initialize)
        self.assertLess(
            initialize.index("memset(actuator, 0, sizeof(*actuator))"),
            initialize.index("actuator_internal(actuator)"),
        )
        normalized = " ".join(self.header.split())
        self.assertIn("without first reading caller storage", normalized)

    def test_every_current_actuator_is_explicit_failure_without_hardware_io(self) -> None:
        callbacks = _function(
            self.source,
            "static bool unsupported_gnss_start(",
            "void egolink_location_hardware_actuator_default_config(",
        )
        self.assertIn("unavailable_action(internal)", callbacks)
        self.assertGreaterEqual(callbacks.count("return false;"), 7)
        for forbidden in (
            "sim7670_lte_query_status(",
            "sim7670_gnss_request_location(",
            "platform_imu_capture_begin(",
            "xTaskCreate",
            "uart_driver_",
            "uart_write_bytes(",
        ):
            self.assertNotIn(forbidden, self.source)
        normalized = " ".join(self.header.split())
        self.assertIn("multi-AT query is", normalized)
        self.assertIn("synchronous and may not run", normalized)
        self.assertIn("later modem worker/arbiter", normalized)

    def test_actual_source_and_api_harness_strictly_compile_and_link_for_esp32s3(self) -> None:
        toolchain = _toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler/IDF/generated sdkconfig unavailable")
        compiler, idf, config = toolchain
        harness_source = textwrap.dedent(
            """
            #include "location_hardware_adapter.h"
            int api_probe(void) {
                egolink_location_hardware_identity_t identity = {0};
                sim7670_gnss_report_t gnss = {0};
                sim7670_lte_report_t lte = {0};
                platform_imu_sample_t imu = {0};
                egolink_location_hardware_battery_input_t battery = {0};
                egolink_location_hardware_mapped_input_t mapped = {0};
                egolink_location_hardware_actuator_config_t config = {0};
                egolink_location_hardware_actuator_t actuator = {0};
                egolink_device_location_runtime_callbacks_t callbacks = {0};
                egolink_location_hardware_actuator_snapshot_t snapshot = {0};
                unsigned char *actuator_bytes = (unsigned char *)(void *)&actuator;
                for (size_t index = 0U; index < sizeof(actuator); ++index) {
                    actuator_bytes[index] = 0xa5U;
                }
                imu.sample_is_mock = false;
                imu.source = "mock_stationary";
                (void)egolink_location_hardware_map_imu(&identity, &imu, &mapped);
                imu.source = "unknown";
                (void)egolink_location_hardware_map_imu(&identity, &imu, &mapped);
                (void)egolink_location_hardware_map_gnss(&identity, &gnss, &mapped);
                (void)egolink_location_hardware_map_lte_state(&identity, &lte, &mapped);
                (void)egolink_location_hardware_map_cell(&identity, &lte, &mapped);
                (void)egolink_location_hardware_map_imu(&identity, &imu, &mapped);
                (void)egolink_location_hardware_map_battery(&identity, &battery, &mapped);
                egolink_location_hardware_actuator_default_config(&config);
                (void)egolink_location_hardware_actuator_init(&actuator, &config);
                (void)egolink_location_hardware_actuator_callbacks(&actuator, &callbacks);
                (void)egolink_location_hardware_actuator_snapshot(&actuator, &snapshot);
                return (int)snapshot.action_requests;
            }
            """
        )
        flags = [
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            *(f"-I{path}" for path in _include_paths(idf, config)),
        ]
        with tempfile.TemporaryDirectory(prefix="egolink-loc021l-") as temporary:
            temp = Path(temporary)
            harness = temp / "api_harness.c"
            source_object = temp / "adapter.o"
            harness_object = temp / "harness.o"
            linked = temp / "combined.o"
            harness.write_text(harness_source, encoding="utf-8")
            for source, output in ((SOURCE, source_object), (harness, harness_object)):
                result = subprocess.run(
                    [str(compiler), *flags, "-c", str(source), "-o", str(output)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
            link = subprocess.run(
                [str(compiler), "-nostdlib", "-Wl,-r", str(source_object), str(harness_object), "-o", str(linked)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, link.returncode, link.stderr)
            self.assertTrue(linked.is_file())

    def test_packet_records_loc021l_nonclaim(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        self.assertIn("LOC-021L", packet)
        self.assertIn("P0-LOC", packet)
        self.assertIn("NOT_RUN", packet)


if __name__ == "__main__":
    unittest.main()
