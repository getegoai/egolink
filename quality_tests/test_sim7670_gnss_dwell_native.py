"""Execute the complete SIM7670 C driver; UART/clock responses are injected."""
import json
import unittest

from quality_tests.native_convergence import COMP, run_c
from quality_tests.native_gnss_driver_shim import DEFINES, HARNESS, HEADERS


class Sim7670GnssDwellNativeTests(unittest.TestCase):
    def test_complete_driver_wait_parse_cancel_deadline_and_exclusive_owner(self):
        output = run_c(
            HARNESS,
            ["sim7670_gnss"],
            extra_sources=[COMP / "sim7670_gnss/sim7670_http_exact_parser.c"],
            headers=HEADERS,
            defines=DEFINES,
        )
        evidence = {item["case"]: item for item in map(json.loads, output.splitlines())}
        self.assertEqual(set(evidence), {
            "default_status", "settled_fix", "settled_no_fix", "cancel_wait",
            "deadline_wait", "clock_regression", "remaining_budget", "invalid_budget",
            "malformed_after_wait", "legacy_unchanged", "power_on_error", "exclusive_owner",
            "clock_before_request",
            "session_query_and_raw_trace", "raw_error_not_nofix",
            "cell_partial_after_no_sim_error",
            "power_off_trace_one_command",
        })
        self.assertEqual(evidence["settled_fix"]["delay_ms"], 300)
        self.assertEqual(evidence["settled_no_fix"]["delay_ms"], 300)
        self.assertEqual(evidence["cancel_wait"]["outcome"], 2)
        self.assertEqual(evidence["deadline_wait"]["outcome"], 3)
        self.assertEqual(evidence["clock_regression"]["outcome"], 3)
        self.assertEqual(evidence["exclusive_owner"], {
            "case": "exclusive_owner", "tasks": 1, "uart_installs": 1, "foreign_io": 0,
        })


if __name__ == "__main__":
    unittest.main()
