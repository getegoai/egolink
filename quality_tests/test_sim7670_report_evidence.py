"""Focused LOC-021M checks for modem query/parse evidence.

These tests are offline. They never open UART, start a task, contact a modem or
send network traffic. The enabled SIM7670 implementation is strictly
cross-compiled for ESP32-S3 from an existing generated IDF compile context.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SIM_COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "sim7670_gnss"
)
SIM_HEADER = SIM_COMPONENT / "include" / "sim7670_gnss.h"
SIM_SOURCE = SIM_COMPONENT / "sim7670_gnss.c"
ADAPTER = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "components"
    / "location_hardware_adapter"
    / "location_hardware_adapter.c"
)
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"


def _function(source: str, name: str, next_name: str) -> str:
    start = source.index(name)
    return source[start : source.index(next_name, start)]


def _compile_entry() -> tuple[dict[str, str], Path] | None:
    candidates = sorted(
        (ROOT / "tmp").glob("*/compile_commands.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    wanted = SIM_SOURCE.resolve()
    for database in candidates:
        try:
            entries = json.loads(database.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in entries:
            try:
                if Path(entry["file"]).resolve() == wanted and entry.get("command"):
                    return entry, database.parent
            except (KeyError, OSError):
                continue
    return None


class Sim7670ReportEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = SIM_HEADER.read_text(encoding="utf-8")
        cls.source = SIM_SOURCE.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")

    def test_evidence_contract_is_additive_and_zero_init_is_no_evidence(self) -> None:
        gnss = self.header.split("} sim7670_gnss_report_t;", 1)[0]
        lte = self.header.split("} sim7670_gnss_report_t;", 1)[1].split(
            "} sim7670_lte_report_t;", 1
        )[0]
        self.assertGreater(gnss.index("location_result_valid"), gnss.index("utc_time"))
        self.assertGreater(lte.index("cell_identity_valid"), lte.index("raw_response"))
        for field in ("attempted", "response_observed", "parse_valid"):
            self.assertIn(field, self.header)
        for field in ("fix_observed", "no_fix_observed"):
            self.assertIn(field, self.header)
        for query in (
            "cpin_query",
            "cops_query",
            "cereg_query",
            "cgatt_query",
            "cgdcont_query",
            "cgact_query",
            "cgpaddr_query",
            "csq_query",
            "cpsi_query",
        ):
            self.assertIn(query, lte)
        for initializer in ("sim7670_gnss_report_init", "sim7670_lte_report_init"):
            body = _function(self.source, f"void {initializer}(", "const char *")
            self.assertIn("memset(report, 0, sizeof(*report))", body)

    def test_gnss_parser_has_three_outcomes_and_strict_empty_no_fix_grammar(self) -> None:
        parser = _function(
            self.source,
            "typedef enum {\n    GNSS_PARSE_INVALID",
            "static void strip_quotes(",
        )
        for outcome in ("GNSS_PARSE_INVALID", "GNSS_PARSE_FIX", "GNSS_PARSE_NO_FIX"):
            self.assertIn(outcome, parser)
        self.assertIn(
            'prefixed_fields_are_all_empty(line, "+CGPSINFO:", 9, 9)', parser
        )
        self.assertIn(
            'prefixed_fields_are_all_empty(line, "+CGNSSINFO:", 9, 18)', parser
        )
        self.assertIn(
            'prefixed_field_count(line, "+CGPSINFO:") != 9', parser
        )
        self.assertIn(
            'prefixed_field_count(line, "+CGNSSINFO:") != tail_index + 9',
            parser,
        )
        self.assertLess(parser.index("if (!lat_ok || !lon_ok)"), parser.index("report->lat = lat"))

    def test_gnss_query_evidence_and_fallback_have_terminal_semantics(self) -> None:
        request = _function(
            self.source,
            "bool sim7670_gnss_request_location(",
            "bool sim7670_lte_query_status(",
        )
        self.assertGreaterEqual(request.count("sim7670_send_at_complete("), 2)
        for query in ("cgnssinfo_query", "cgpsinfo_query"):
            self.assertIn(f"report->{query}.attempted = true", request)
            self.assertIn(f"report->{query}.response_observed", request)
        self.assertIn("record_gnss_query_outcome", request)
        self.assertIn("!report->fix &&", request)
        self.assertIn('set_status(report, "fix", "observed")', request)
        self.assertIn('set_status(report, "no_fix", "observed")', request)
        self.assertIn('set_status(report, "query_unverified", "unverified")', request)

    def test_lte_parsers_return_validity_and_query_reader_requires_complete_response(self) -> None:
        for parser in (
            "parse_cpin",
            "parse_cops",
            "parse_cereg",
            "parse_cgatt",
            "parse_cgdcont",
            "parse_cgact",
            "parse_cgpaddr",
            "parse_csq",
            "parse_cpsi",
        ):
            self.assertIn(f"static bool {parser}(", self.source)
        runner = _function(
            self.source, "static void run_lte_status_query(",
            "bool sim7670_gnss_request_location(",
        )
        self.assertIn("sim7670_send_at_complete(", runner)
        self.assertIn("evidence->attempted = true", runner)
        self.assertIn("evidence->parse_valid = parser(response, report)", runner)

    def test_lte_query_grammar_does_not_guess_cereg_or_wrong_cid(self) -> None:
        cereg = _function(self.source, "static bool parse_cereg(", "static bool parse_cgatt(")
        self.assertIn('prefixed_field_count(line, "+CEREG:") < 2', cereg)
        self.assertIn("const char *stat = field1", cereg)
        cgact = _function(self.source, "static bool parse_cgact(", "static bool parse_cgpaddr(")
        cgdcont = _function(self.source, "static bool parse_cgdcont(", "static bool parse_cgact(")
        self.assertIn("while ((line = find_line(cursor", cgact)
        self.assertIn("cid == 1", cgact)
        self.assertIn("while ((line = find_line(cursor", cgdcont)
        self.assertIn("cid == 1", cgdcont)
        cgpaddr = _function(self.source, "static bool parse_cgpaddr(", "static bool parse_csq(")
        self.assertIn("cid != 1", cgpaddr)

    def test_driver_classification_checks_each_matching_core_validity(self) -> None:
        classify = _function(
            self.source, "static void classify_lte_status(",
            "static void record_gnss_query_outcome(",
        )
        ordered = (
            "cpin_query.parse_valid",
            "LTE_SIM_NOT_READY",
            "cereg_query.parse_valid",
            "LTE_NOT_REGISTERED",
            "cgatt_query.parse_valid",
            "LTE_NOT_ATTACHED",
            "cgact_query.parse_valid",
            "LTE_PDP_INACTIVE",
            "LTE_READY",
        )
        offsets = [classify.index(token) for token in ordered]
        self.assertEqual(offsets, sorted(offsets))
        self.assertGreaterEqual(classify.count("LTE_STATUS_UNKNOWN"), 4)

    def test_adapter_is_backward_compatible_but_legacy_evidence_fails_closed(self) -> None:
        gnss_evidence = _function(
            self.adapter, "static bool valid_gnss_evidence(",
            "static bool no_gnss_measurement_is_marked_valid(",
        )
        self.assertIn("return report->at_ok ||", gnss_evidence)
        gnss_map = _function(
            self.adapter, "egolink_location_hardware_map_gnss(",
            "static const char *expected_lte_reason(",
        )
        self.assertIn('"no_fix"', gnss_map)
        self.assertIn('"unverified"', gnss_map)
        self.assertIn("EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR", gnss_map)
        lte_validation = _function(
            self.adapter, "static bool valid_lte_report(",
            "static egolink_location_engine_lte_state_t lte_state(",
        )
        self.assertIn("legacy_lte_reason(report)", lte_validation)
        self.assertNotIn("all_lte_queries_were_attempted", lte_validation)
        lte_map = _function(
            self.adapter, "static egolink_location_engine_lte_state_t lte_state(",
            "egolink_location_hardware_map_status_t\negolink_location_hardware_map_lte_state(",
        )
        self.assertLess(
            lte_map.index("!report->cpin_query.parse_valid"),
            lte_map.index("EGOLINK_LOCATION_ENGINE_LTE_ONLINE"),
        )

    def test_adapter_maps_only_proven_negative_and_positive_lte_states(self) -> None:
        lte = _function(
            self.adapter, "static egolink_location_engine_lte_state_t lte_state(",
            "egolink_location_hardware_map_status_t\negolink_location_hardware_map_lte_state(",
        )
        for token in (
            "EGOLINK_LOCATION_ENGINE_LTE_UNAVAILABLE",
            "EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN",
            "EGOLINK_LOCATION_ENGINE_LTE_OFFLINE",
            "EGOLINK_LOCATION_ENGINE_LTE_LIMITED",
            "EGOLINK_LOCATION_ENGINE_LTE_ONLINE",
        ):
            self.assertIn(token, lte)
        for proof, fact in (
            ("cpin_query.parse_valid", "!report->sim_ready"),
            ("cereg_query.parse_valid", "!report->registered"),
            ("cgatt_query.parse_valid", "!report->attached"),
            ("cgact_query.parse_valid", "report->pdp_active ?"),
        ):
            self.assertLess(lte.index(proof), lte.index(fact))

    def test_cell_requires_one_complete_cpsi_identity_without_app_wiring(self) -> None:
        cell = _function(
            self.adapter, "egolink_location_hardware_map_cell(",
            "egolink_location_hardware_map_imu(",
        )
        for proof in (
            "cpsi_query.response_observed",
            "cpsi_query.parse_valid",
            "cell_identity_valid",
        ):
            self.assertIn(proof, cell)
        self.assertNotIn("location_hardware_adapter", APP_MAIN.read_text(encoding="utf-8"))

    def test_enabled_driver_strictly_cross_compiles_for_esp32s3(self) -> None:
        found = _compile_entry()
        if found is None:
            self.skipTest("generated ESP32-S3 compile database unavailable")
        entry, directory = found
        defines = (
            "-DCONFIG_EGOLINK_SIM7670_GNSS_ENABLED=1 "
            "-DCONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=1 "
            "-DCONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED=1 "
            "-DCONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=0 "
            "-DCONFIG_EGOLINK_SIM7670_GNSS_POWER_ON_BEFORE_QUERY=0 "
            "-DCONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS=1000 "
            "-DCONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS=1000 "
            "-DCONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM=0 "
            "-DCONFIG_EGOLINK_SIM7670_UART_BAUD=115200 "
            "-DCONFIG_EGOLINK_SIM7670_UART_NUM=1 "
            "-DCONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17 "
            "-DCONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18 "
        )
        idf_path = Path(os.environ.get("IDF_PATH", "C:/Espressif/v5.4.2/esp-idf"))
        esp_timer_include = idf_path / "components" / "esp_timer" / "include"
        self.assertTrue(esp_timer_include.is_dir())
        defines += f'-I"{esp_timer_include}" '
        strict = (
            "-Wall -Wextra -Werror -Werror=conversion -Werror=format "
            "-Werror=shadow -Werror=sign-conversion "
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc021m-") as temporary:
            output = Path(temporary) / "sim7670_gnss.o"
            replacement = f' {defines}{strict}-o "{output}" -c '
            command, substitutions = re.subn(
                r"\s-o\s+(?:\"[^\"]+\"|\S+)\s+-c\s+",
                lambda _match: replacement,
                entry["command"],
                count=1,
            )
            self.assertEqual(1, substitutions)
            result = subprocess.run(
                command,
                cwd=directory,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=os.environ.copy(),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(output.is_file())

    def test_packet_records_loc021m_scope_and_nonclaim(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        self.assertIn("LOC-021M", packet)
        self.assertIn("P0-LOC", packet)
        self.assertIn("NOT_RUN", packet)


if __name__ == "__main__":
    unittest.main()
