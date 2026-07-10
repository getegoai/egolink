from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from pc_simulator import event_store
from scripts import sim7670_gnss_probe as gnss


class Sim7670GnssProbeTests(unittest.TestCase):
    def test_parse_cgpsinfo_ddmm_coordinates(self) -> None:
        fix = gnss.parse_cgpsinfo(
            "+CGPSINFO:3113.343286,N,12121.234064,E,250311,072809.33,44.1,0.0,0"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, 31.222388)
        self.assertEqual(fix.lon, 121.353901)
        self.assertEqual(fix.altitude_m, 44.1)
        self.assertEqual(fix.speed_mps, 0.0)

    def test_parse_cgnssinfo_fix_and_satellites(self) -> None:
        fix = gnss.parse_cgnssinfo(
            "+CGNSSINFO:2,09,05,00,00,3113.330650,N,12121.262554,E,131117,091918.00,32.9,0.0,255.0,1.1,0.8,0.7,14"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, 31.222177)
        self.assertEqual(fix.lon, 121.354376)
        self.assertEqual(fix.satellites, 14)
        self.assertEqual(fix.hdop, 0.8)

    def test_parse_cgnssinfo_no_fix(self) -> None:
        fix = gnss.parse_cgnssinfo("+CGNSSINFO:,,,,,,,,,,,,,,,,,")

        self.assertFalse(fix.fix)
        self.assertIsNone(fix.lat)
        self.assertIsNone(fix.lon)

    def test_location_event_from_no_fix(self) -> None:
        event = gnss.location_event_from_parsed(
            {
                "port": "COM6",
                "gnss_power_state": "1",
                "fix": {
                    "fix": False,
                    "source_command": "AT+CGNSSINFO",
                    "raw_line": "+CGNSSINFO:,,,,,,,,,,,,,,,,,",
                },
            },
            device_id="ego-link-001",
            seq=12,
        )

        self.assertEqual(event["event_type"], "location_report")
        self.assertEqual(event["source"], "sim7670g_gnss")
        self.assertFalse(event["fix"])
        self.assertEqual(event["gnss_state"], "no_fix")
        self.assertNotIn("lat", event)

    def test_next_seq_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            event_store.append_jsonl(log_path, {"seq": 4})
            event_store.append_jsonl(log_path, {"seq": 9})

            self.assertEqual(gnss.next_seq_from_event_log(log_path), 10)

    def test_parse_gnss_probe_uses_latest_power_state(self) -> None:
        parsed = gnss.parse_gnss_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"command": "AT", "response": "OK\r\n"},
                    {"command": "AT+CGNSSPWR?", "response": "+CGNSSPWR: 0\r\nOK\r\n"},
                    {"command": "AT+CGNSSPWR=1", "response": "OK\r\n"},
                    {"command": "AT+CGNSSPWR?", "response": "+CGNSSPWR: 1\r\nOK\r\n"},
                    {"command": "AT+CGNSSINFO", "response": "+CGNSSINFO: ,,,,,,,,\r\nOK\r\n"},
                ],
            }
        )

        self.assertEqual(parsed["gnss_power_state"], "1")


if __name__ == "__main__":
    unittest.main()
