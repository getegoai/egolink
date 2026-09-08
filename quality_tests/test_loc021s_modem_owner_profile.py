"""Offline/static checks for the default-off LOC-021S composition profile.

No test in this module starts a task, opens a UART, touches a modem/SIM/flash,
or performs network I/O.  When EGOLINK_LOC021S_BUILD_DIR is provided, the
suite additionally verifies the final ESP-IDF build graph and sdkconfig.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "firmware" / "mqtt_heartbeat"
MAIN = PROJECT / "main"
CMAKE = MAIN / "CMakeLists.txt"
KCONFIG = MAIN / "Kconfig.projbuild"
SOURCE = MAIN / "loc021s_modem_owner_main.c"
DEFAULTS = PROJECT / "sdkconfig.loc021s_modem_owner.defaults"


def _function(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


class Loc021sModemOwnerProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")

    def test_profile_is_default_off_and_selects_one_main_source(self) -> None:
        self.assertRegex(
            self.kconfig,
            r"config EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE\s+"
            r"bool[\s\S]+?default n",
        )
        profile_branch = _function(
            self.cmake,
            "if(CONFIG_EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE)",
            "else()",
        )
        default_branch = _function(self.cmake, "else()", "endif()")
        self.assertIn('set(EGOLINK_MAIN_SOURCES "loc021s_modem_owner_main.c")', profile_branch)
        self.assertNotIn('"app_main.c"', profile_branch)
        self.assertIn('set(EGOLINK_MAIN_SOURCES "app_main.c")', default_branch)
        self.assertNotIn("loc021s_modem_owner_main.c", default_branch)
        self.assertEqual(1, self.cmake.count("idf_component_register("))
        self.assertIn("SRCS ${EGOLINK_MAIN_SOURCES}", self.cmake)

    def test_two_pass_dependency_union_is_explicit_and_exact(self) -> None:
        expected = {
            "collection_network_policy",
            "collection_record",
            "collection_spool",
            "collection_usb_lte",
            "esp_common",
            "esp_p0_https",
            "esp_app_format",
            "esp_event",
            "esp_http_client",
            "esp_netif",
            "esp_system",
            "esp_timer",
            "esp_wifi",
            "freertos",
            "json",
            "location_outbox_adapter",
            "log",
            "mqtt",
            "nvs_flash",
            "p0_delivery_runtime",
            "p0_outbox_dispatcher",
            "persistent_priority_outbox",
            "persistent_priority_outbox_partition",
            "platform_imu",
            "platform_power",
            "safety_model",
            "sim7670_gnss",
            "sim7670_location_modem_owner",
            "sos_outbox_adapter",
        }
        match = re.search(
            r"set\(EGOLINK_MAIN_REQUIREMENTS\s+([\s\S]+?)\s+\)",
            self.cmake,
        )
        self.assertIsNotNone(match)
        self.assertEqual(expected, set(match.group(1).split()))
        self.assertIn("dependency graph before project Kconfig", self.cmake)

    def test_profile_defaults_disable_every_legacy_or_test_driver_path(self) -> None:
        enabled = (
            "MESSAGE_HUB_HTTP_ENABLED",
            "SIM7670_GNSS_ENABLED",
            "SIM7670_LTE_STATUS_ENABLED",
            "SIM7670_LOCATION_MODEM_OWNER_ENABLED",
            "LOC021S_MODEM_OWNER_SMOKE_PROFILE",
        )
        disabled = (
            "GNSS_LOCATION_SCAFFOLD_ENABLED",
            "SIM7670_LTE_HTTP_PROBE_ENABLED",
            "SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED",
            "SIM7670_LOCATION_OBSERVATION_ENABLED",
            "SIM7670_D1_PERIODIC_LOCATION_ENABLED",
            "LTE_WIFI_FAILOVER_ENABLED",
            "WIFI_IMU_WINDOW_COMMAND_ENABLED",
            "SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED",
        )
        for name in enabled:
            self.assertIn(f"CONFIG_EGOLINK_{name}=y", self.defaults)
        for name in disabled:
            self.assertIn(f"# CONFIG_EGOLINK_{name} is not set", self.defaults)

    def test_source_guards_profile_and_all_legacy_application_modes(self) -> None:
        for symbol in (
            "CONFIG_EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE",
            "CONFIG_EGOLINK_SIM7670_GNSS_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED",
            "CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED",
            "CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED",
            "CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED",
            "CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED",
        ):
            self.assertIn(symbol, self.source)

    def test_boot_epoch_is_durable_and_fails_closed_without_erasing_nvs(self) -> None:
        function = _function(
            self.source,
            "static bool loc021s_advance_boot_epoch",
            "static egolink_location_runtime_text_t",
        )
        ordered = (
            "nvs_flash_init()",
            "nvs_open(",
            "nvs_get_u64(",
            "nvs_set_u64(",
            "nvs_commit(",
            "nvs_get_u64(",
            "nvs_close(",
        )
        cursor = 0
        for needle in ordered:
            cursor = function.index(needle, cursor) + len(needle)
        for forbidden in (
            "nvs_flash_erase",
            "nvs_erase_",
            "esp_partition_erase_range",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("confirmed != next", function)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_JSON_SAFE_INTEGER_MAX", function)
        app = _function(self.source, "void app_main(void)", "\n}")
        self.assertLess(app.index("loc021s_advance_boot_epoch"), app.index("loc021s_initialize_outbox"))

    def test_boot_long_composition_has_the_required_initialization_order(self) -> None:
        for declaration in (
            "static egolink_outbox_partition_t s_outbox_partition;",
            "static egolink_outbox_storage_t s_outbox_storage;",
            "static egolink_outbox_t s_shared_outbox;",
            "static egolink_location_outbox_adapter_t s_location_adapter;",
            "static egolink_sos_outbox_adapter_t s_sos_adapter;",
            "static egolink_p0_outbox_dispatcher_t s_dispatcher;",
            "static egolink_p0_delivery_runtime_t s_delivery_runtime;",
            "static egolink_sim7670_location_modem_owner_t s_modem_owner;",
        ):
            self.assertIn(declaration, self.source)
        cursor = 0
        for needle in (
            "egolink_outbox_partition_init(",
            "egolink_outbox_partition_storage(",
            "egolink_location_outbox_adapter_init(",
            "egolink_sos_outbox_adapter_bind(",
            "egolink_p0_outbox_dispatcher_init(",
            "egolink_p0_delivery_runtime_init(",
            "egolink_sim7670_location_modem_owner_init(",
            "egolink_sim7670_location_modem_owner_start(",
            "egolink_sim7670_location_modem_owner_request_gnss_status(",
        ):
            cursor = self.source.index(needle, cursor) + len(needle)
        for forbidden in ("_deinit(", "vTaskDelete(", "nvs_flash_deinit("):
            self.assertNotIn(forbidden, self.source)
        app = _function(self.source, "void app_main(void)", "\n}")
        cursor = 0
        for needle in (
            "loc021s_advance_boot_epoch(",
            "loc021s_build_boot_identity(",
            "loc021s_now_ms(",
            "loc021s_initialize_outbox(",
            "loc021s_initialize_delivery(",
            "loc021s_initialize_owner(",
            "egolink_sim7670_location_modem_owner_start(",
            "egolink_sim7670_location_modem_owner_current_status(",
            "egolink_sim7670_location_modem_owner_request_gnss_status(",
        ):
            cursor = app.index(needle, cursor) + len(needle)

    def test_delivery_callback_is_explicit_offline_transport_failure(self) -> None:
        function = _function(
            self.source,
            "static egolink_p0_delivery_post_outcome_t loc021s_offline_post",
            "static bool loc021s_initialize_outbox",
        )
        self.assertIn("EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE", function)
        self.assertIn("EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED", function)
        self.assertIsNone(
            re.search(r"http|socket|wifi|mqtt|uart", function, re.IGNORECASE)
        )
        delivery = _function(
            self.source,
            "static bool loc021s_initialize_delivery",
            "static bool loc021s_initialize_owner",
        )
        self.assertIn("delivery_config.http_post = loc021s_offline_post", delivery)

    def test_profile_only_uses_q_public_owner_for_modem_and_one_shot(self) -> None:
        for forbidden in (
            "sim7670_gnss_request_location",
            "sim7670_lte_query_status",
            "sim7670_lte_http_",
            "sim7670_at_backend_",
            "uart_",
            "process_mapped_input",
            "process_durable_sos",
            "signal_durable_sos",
            "platform_imu",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertEqual(
            1,
            self.source.count("egolink_sim7670_location_modem_owner_request_gnss_status("),
        )
        app = _function(self.source, "void app_main(void)", "\n}")
        self.assertLess(
            app.index("egolink_sim7670_location_modem_owner_start("),
            app.index("egolink_sim7670_location_modem_owner_request_gnss_status("),
        )
        self.assertIn("no_retry=true", app)

    def test_generated_build_excludes_legacy_main_when_requested(self) -> None:
        configured = os.environ.get("EGOLINK_LOC021S_BUILD_DIR")
        if not configured:
            self.skipTest("set EGOLINK_LOC021S_BUILD_DIR for generated-build proof")
        build = Path(configured).resolve()
        compile_database = json.loads(
            (build / "compile_commands.json").read_text(encoding="utf-8")
        )
        compiled = {Path(entry["file"]).resolve() for entry in compile_database}
        self.assertIn(SOURCE.resolve(), compiled)
        self.assertNotIn((MAIN / "app_main.c").resolve(), compiled)

        sdkconfig = json.loads(
            (build / "config" / "sdkconfig.json").read_text(encoding="utf-8")
        )
        self.assertIs(sdkconfig["EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE"], True)
        for name in (
            "SIM7670_GNSS_ENABLED",
            "SIM7670_LTE_STATUS_ENABLED",
            "SIM7670_LOCATION_MODEM_OWNER_ENABLED",
        ):
            self.assertIs(sdkconfig[f"EGOLINK_{name}"], True)
        for name in (
            "GNSS_LOCATION_SCAFFOLD_ENABLED",
            "SIM7670_LTE_HTTP_PROBE_ENABLED",
            "SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED",
            "SIM7670_LOCATION_OBSERVATION_ENABLED",
            "SIM7670_D1_PERIODIC_LOCATION_ENABLED",
            "SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED",
            "LTE_WIFI_FAILOVER_ENABLED",
            "WIFI_IMU_WINDOW_COMMAND_ENABLED",
        ):
            self.assertIs(sdkconfig.get(f"EGOLINK_{name}", False), False)
        self.assertIs(sdkconfig["PARTITION_TABLE_CUSTOM"], True)
        self.assertEqual("partitions_outbox.csv", sdkconfig["PARTITION_TABLE_CUSTOM_FILENAME"])
        self.assertIn("ego_outbox", (PROJECT / "partitions_outbox.csv").read_text(encoding="utf-8"))

        ninja = (build / "build.ninja").read_text(encoding="utf-8", errors="replace")
        self.assertIn("loc021s_modem_owner_main.c.obj", ninja)
        self.assertNotIn("__idf_main.dir/app_main.c.obj", ninja)
        maps = list(build.glob("*.map"))
        self.assertEqual(1, len(maps), "expected one final linker map")
        linker_map = maps[0].read_text(encoding="utf-8", errors="replace")
        self.assertIn("loc021s_modem_owner_main.c.obj", linker_map)
        self.assertNotIn("__idf_main.dir/app_main.c.obj", linker_map)
        self.assertGreater((build / "egolink_mqtt_heartbeat.elf").stat().st_size, 0)
        self.assertGreater((build / "egolink_mqtt_heartbeat.bin").stat().st_size, 0)
        self.assertGreater((build / "partition_table" / "partition-table.bin").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
