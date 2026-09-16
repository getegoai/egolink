"""Static integration guards for the collector Wi-Fi/LTE route slice."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "firmware/mqtt_heartbeat/main/collection_main.c"
COORDINATOR = ROOT / "firmware/mqtt_heartbeat/components/collection_network_coordinator/collection_network_coordinator.c"
COORDINATOR_HEADER = ROOT / "firmware/mqtt_heartbeat/components/collection_network_coordinator/include/collection_network_coordinator.h"
KCONFIG = ROOT / "firmware/mqtt_heartbeat/main/Kconfig.projbuild"
DEFAULTS = ROOT / "firmware/mqtt_heartbeat/sdkconfig.collection.defaults"
USB_LTE_DEFAULTS = (
    ROOT / "firmware/mqtt_heartbeat/sdkconfig.collection_usb_lte.defaults"
)
USB_LTE_KCONFIG = (
    ROOT / "firmware/mqtt_heartbeat/components/collection_usb_lte/Kconfig"
)


def function(source: str, name: str, next_name: str) -> str:
    try:
        start = source.index(f"{name}(")
        end = source.index(f"{next_name}(", start)
    except ValueError as error:
        raise AssertionError(f"could not isolate {name}")
    return source[start:end]


class CollectionProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.coordinator = COORDINATOR.read_text(encoding="utf-8")
        cls.coordinator_header = COORDINATOR_HEADER.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")
        cls.usb_lte_defaults = USB_LTE_DEFAULTS.read_text(encoding="utf-8")
        cls.usb_lte_kconfig = USB_LTE_KCONFIG.read_text(encoding="utf-8")

    def test_lte_is_explicit_opt_in_and_default_collector_remains_no_sim(self):
        block = self.kconfig.split("config EGOLINK_COLLECTION_LTE_PPP_ENABLED", 1)[1]
        block = block.split("config EGOLINK_COLLECTION_LTE_USB_DESCRIPTOR_VERIFIED", 1)[0]
        self.assertIn("default n", block)
        self.assertIn("!EGOLINK_COLLECTION_NO_SIM", block)
        self.assertIn("EGOLINK_COLLECTION_USB_LTE", block)
        self.assertIn("CONFIG_EGOLINK_COLLECTION_NO_SIM=y", self.defaults)
        self.assertNotIn("CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED=y", self.defaults)

    def test_usb_lte_profile_sizes_composite_enumeration_without_identity(self):
        self.assertIn(
            "CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=1024",
            self.usb_lte_defaults,
        )
        self.assertNotIn("CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE", self.defaults)
        for forbidden in (
            "EGOLINK_COLLECTION_USB_LTE=y",
            "VENDOR_ID",
            "PRODUCT_ID",
            "MODEM_INTERFACE",
            "SSID",
            "PASSWORD",
            "BEARER",
            "DEVICE_ID",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.usb_lte_defaults)

    def test_usb_lte_connector_compiles_pap_used_by_pinned_modem_profile(self):
        self.assertIn("select LWIP_PPP_SUPPORT", self.usb_lte_kconfig)
        self.assertIn("select LWIP_PPP_NOTIFY_PHASE_SUPPORT", self.usb_lte_kconfig)
        self.assertIn("select LWIP_PPP_PAP_SUPPORT", self.usb_lte_kconfig)

    def test_usb_lte_gate_contention_is_retryable_and_status_is_cached(self):
        self.assertIn(
            "result==COLLECTION_USB_LTE_PENDING||result==COLLECTION_USB_LTE_BUSY",
            self.source,
        )
        self.assertIn("lte_status_cache", self.source)
        self.assertIn("lte_status_snapshot", self.source)

    def test_wifi_scan_payload_retains_only_aggregate_radio_fields(self):
        scan = function(self.source, "scan_wifi", "wifi_task")
        self.assertNotIn(".bssid", scan.lower())
        self.assertNotIn(".ssid", scan.lower())
        self.assertNotIn('"bssid"', scan.lower())
        self.assertNotIn('"ssid"', scan.lower())
        for marker in (
            '"channel_summary"',
            '"ap_count"',
            '"strongest_rssi"',
            '"identifiers_retained",false',
            '"privacy_reason","raw_wifi_identifiers_disabled"',
        ):
            self.assertIn(marker, scan)

    def test_uploader_consumes_snapshot_and_cannot_control_wifi_or_modem(self):
        uploader = self.source.split("static void uploader_task(void *unused)\n{", 1)[1]
        uploader = uploader.split("\nvoid app_main(void)", 1)[0]
        self.assertIn("network_runtime_snapshot_t route=read_network()", uploader)
        self.assertIn(".transfer_generation=route.generation", uploader)
        self.assertIn(".cancel_requested=upload_cancel", uploader)
        self.assertIn("uploader_active_generation", uploader)
        self.assertIn("uploader_retired_generation", uploader)
        self.assertIn("interface_matches_route(route.route,interface_name)", uploader)
        for forbidden in (
            "esp_wifi_connect",
            "esp_wifi_disconnect",
            "collection_usb_lte_begin",
            "collection_usb_lte_quiesce",
        ):
            self.assertNotIn(forbidden, uploader)

    def test_route_publication_is_one_snapshot_and_switch_retires_before_wifi(self):
        publish = function(self.source, "publish_network", "read_network")
        self.assertIn("network_runtime=next", publish)
        self.assertIn("atomic_store(&network_route_generation,next.generation)", publish)
        self.assertIn("portENTER_CRITICAL(&network_mux)", publish)
        self.assertIn("portEXIT_CRITICAL(&network_mux)", publish)
        self.assertIn("collection_network_retirement_ready", self.coordinator)
        self.assertIn("COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER", self.coordinator)
        self.assertIn(
            "atomic_store(&uploader_retired_generation,policy_result.route_generation)",
            self.source,
        )

    def test_cleanup_is_epoch_bound_and_failure_never_reports_quiesced(self):
        failed = function(
            self.coordinator, "cleanup_failed_observed", "cleanup_failed"
        )
        self.assertNotIn("COLLECTION_NETWORK_EVENT_LTE_QUIESCED", failed)
        self.assertIn("COLLECTION_NETWORK_COORDINATOR_DISABLED", failed)
        self.assertIn("epoch_matches(coordinator, &before)", self.coordinator)
        self.assertIn("epoch_matches(coordinator, &status)", self.coordinator)
        self.assertIn("coordinator->guard_start_ms = now_ms", self.coordinator)
        self.assertIn("coordinator->dial_submitted ||", self.coordinator)
        self.assertIn("coordinator->command_submitted = true", self.coordinator)
        self.assertIn("operation == COLLECTION_NETWORK_CONNECTOR_DIAL", self.coordinator)
        self.assertIn("coordinator->hangup_required = true", self.coordinator)
        self.assertIn("coordinator->command_in_flight", self.coordinator)
        self.assertIn("coordinator->last_started_attempt_id", self.coordinator)
        self.assertIn("!coordinator->command_submitted", self.coordinator)
        self.assertIn("COLLECTION_NETWORK_EVENT_LTE_DISABLED", self.coordinator)
        for scoped_operation in (
            "connector.cancel_poll(",
            "connector.poll(",
            "connector.quiesce(",
            "coordinator->connection_epoch",
            "COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH",
        ):
            self.assertIn(scoped_operation, self.coordinator)
        self.assertIn(
            "stage == COLLECTION_NETWORK_COORDINATOR_DISABLED &&\n"
            "         !coordinator->cleanup_confirmed",
            self.coordinator,
        )
        self.assertIn(
            "uart_cleanup_allowed=uart_cleanup_allowed&&\n"
            "        !collection_network_coordinator_blocks_uart_work(&lte_control)",
            self.source,
        )
        self.assertEqual(self.source.count("esp_netif_sntp_deinit()"), 1)

    def test_main_is_thin_owner_adapter_and_coordinator_cannot_touch_wire_or_spool(self):
        self.assertNotIn("LTE_CONTROL_", self.source)
        for api in (
            "collection_network_coordinator_init",
            "collection_network_coordinator_apply_policy",
            "collection_network_coordinator_admit",
            "collection_network_coordinator_poll",
            "collection_network_coordinator_blocks_uart_work",
            "collection_network_coordinator_cancel_setup",
        ):
            self.assertIn(api, self.source)
        for scoped_connector_api in (
            "collection_usb_lte_begin_for_epoch(",
            "collection_usb_lte_poll_for_epoch(expected_epoch)",
            "collection_usb_lte_cancel_poll_for_epoch(expected_epoch)",
            "collection_usb_lte_quiesce_for_epoch(expected_epoch)",
            "collection_usb_lte_service()",
        ):
            self.assertIn(scoped_connector_api, self.source)
        for unscoped_connector_api in (
            "collection_usb_lte_begin(",
            "collection_usb_lte_poll(",
            "collection_usb_lte_cancel(",
            "collection_usb_lte_quiesce(",
        ):
            self.assertNotIn(unscoped_connector_api, self.source)
        self.assertIn(
            "if(usb_ready)collection_network_coordinator_refresh_status(&lte_control);",
            self.source,
        )
        self.assertIn(
            "if(usb_ready) {\n"
            "        (void)collection_usb_lte_service();\n"
            "        collection_network_coordinator_refresh_status(&lte_control);",
            self.source,
        )
        for forbidden in (
            "collection_spool_",
            "collection_record_ack_matches",
            "esp_http_client",
            "esp_wifi_",
            "collection_usb_lte_",
            "sim7670_",
        ):
            self.assertNotIn(forbidden, self.coordinator)
        self.assertIn("bool initialized", self.coordinator_header)

    def test_stop_telemetry_keeps_independent_completion_facts(self):
        for key in (
            '"uploader_finished"',
            '"wifi_cleanup_confirmed"',
            '"gnss_power_off_confirmed"',
            '"lte_ppp_dead"',
            '"lte_hangup_confirmed"',
            '"lte_cleanup_confirmed"',
        ):
            self.assertIn(key, self.source)

    def test_partial_or_ownerless_wifi_lifecycle_cannot_claim_clean_stop(self):
        cleanup = function(self.source, "wifi_cleanup", "network_init")
        for marker in (
            "esp_event_handler_unregister",
            "esp_wifi_stop()",
            "esp_wifi_deinit()",
            "esp_netif_destroy_default_wifi",
        ):
            self.assertIn(marker, cleanup)
        network = function(self.source, "network_init", "scan_wifi")
        self.assertIn("goto fail", network)
        self.assertIn("wifi_cleanup_confirmed,wifi_cleanup()", network)
        self.assertIn("wifi_task_missing", self.source)
        self.assertIn("atomic_load(&wifi_cleanup_confirmed)", self.source)

    def test_wifi_route_level_tracks_ip_loss_and_late_stop_events_fail_closed(self):
        event = function(self.source, "network_event", "wifi_cleanup")
        self.assertIn("IP_EVENT_STA_GOT_IP", event)
        self.assertIn("IP_EVENT_STA_LOST_IP", event)
        self.assertIn("atomic_load(&stopping)", event)
        self.assertIn("atomic_store(&wifi_ready,false)", event)
        network = function(self.source, "network_init", "scan_wifi")
        self.assertIn("IP_EVENT_STA_LOST_IP,network_event", network)
        cleanup = function(self.source, "wifi_cleanup", "network_init")
        self.assertIn("IP_EVENT_STA_LOST_IP,network_event", cleanup)


if __name__ == "__main__":
    unittest.main()
