from __future__ import annotations

import unittest

from pc_simulator import safety_companion


class SafetyCompanionTests(unittest.TestCase):
    def test_sos_event_routes_to_emergency_output(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "sos_pressed",
                    "ts": "2026-06-21T02:00:00+00:00",
                    "priority": "critical",
                    "battery": 87,
                }
            ],
            {
                "online": True,
                "battery": 87,
                "rssi": -55,
                "guard_mode": "child_safety",
                "lat": 22.5,
                "lon": 114.0,
            },
        )

        self.assertEqual(result["model_input"]["contract_version"], safety_companion.CONTRACT_VERSION)
        self.assertEqual(result["model_input"]["active_event"], "sos_pressed")
        self.assertEqual(result["model_output"]["risk_type"], "manual_sos")
        self.assertEqual(result["model_output"]["recommended_action"], "escalate_emergency")
        self.assertIn("manual_sos", result["model_output"]["reason_codes"])

    def test_gnss_no_fix_routes_to_device_risk(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "location_report",
                    "ts": "2026-06-21T02:11:43+00:00",
                    "source": "sim7670g_gnss",
                    "fix": False,
                    "gnss_state": "no_fix",
                }
            ],
            {
                "online": True,
                "battery": 87,
                "rssi": -61,
                "guard_mode": "child_safety",
            },
        )

        self.assertFalse(result["model_input"]["location"]["fix"])
        self.assertEqual(result["model_input"]["network"]["signal_level"], 4)
        self.assertEqual(result["model_output"]["risk_type"], "device_risk")
        self.assertEqual(result["model_output"]["recommended_action"], "upload_summary")
        self.assertIn("gnss_no_fix", result["model_output"]["reason_codes"])

    def test_wake_event_asks_user_without_emergency_risk(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "wake_detected",
                    "ts": "2026-06-21T02:12:00+00:00",
                    "confidence": 0.92,
                }
            ],
            {
                "online": True,
                "battery": 80,
                "rssi": -70,
                "guard_mode": "child_safety",
            },
        )

        self.assertEqual(result["model_input"]["audio"]["event_scores"]["speech"], 0.92)
        self.assertEqual(result["model_output"]["risk_type"], "none")
        self.assertEqual(result["model_output"]["recommended_action"], "ask_user")

    def test_low_battery_sensor_sample_routes_to_device_risk(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "sensor_sample",
                    "ts": "2026-06-21T02:13:00+00:00",
                    "battery": 18,
                }
            ],
            {
                "online": True,
                "battery": 50,
                "rssi": -90,
                "guard_mode": "child_safety",
            },
        )

        self.assertEqual(result["model_input"]["device"]["battery_percent"], 18)
        self.assertEqual(result["model_output"]["risk_type"], "device_risk")
        self.assertIn("low_battery", result["model_output"]["reason_codes"])

    def test_model_input_uses_event_timestamp_ms(self) -> None:
        result = safety_companion.evaluate(
            [{"event_type": "wake_detected", "ts": "2026-06-21T00:00:00+00:00"}],
            {"online": True, "battery": 90, "rssi": -55},
        )

        self.assertEqual(result["model_input"]["timestamp_ms"], 1782000000000)


if __name__ == "__main__":
    unittest.main()
