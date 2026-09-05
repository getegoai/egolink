from __future__ import annotations

from pathlib import Path
import re
import unittest


class SafetyModelFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.component_dir = self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "safety_model"
        self.header = (self.component_dir / "include" / "safety_model.h").read_text(encoding="utf-8")
        self.source = (self.component_dir / "safety_model.c").read_text(encoding="utf-8")
        self.component_cmake = (self.component_dir / "CMakeLists.txt").read_text(encoding="utf-8")
        self.main_cmake = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.app_main = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
        ).read_text(encoding="utf-8")

    def test_component_wraps_shared_contract_header(self) -> None:
        self.assertIn('#include "safety_model_contract.h"', self.header)
        self.assertIn('../../../../shared/embedded', self.component_cmake)
        requirements = re.search(
            r"set\(EGOLINK_MAIN_REQUIREMENTS\s+(?P<body>[\s\S]+?)\s+\)",
            self.main_cmake,
        )
        self.assertIsNotNone(requirements)
        self.assertRegex(
            requirements.group("body"), r"(?m)^\s*safety_model\s*$"
        )
        self.assertIn("REQUIRES ${EGOLINK_MAIN_REQUIREMENTS}", self.main_cmake)

    def test_required_public_api_is_exposed(self) -> None:
        self.assertIn('bool safety_model_init(void);', self.header)
        self.assertIn('bool safety_model_evaluate(', self.header)
        self.assertIn('const char *safety_model_version(void);', self.header)
        self.assertIn('safety_model_input_from_mock_state', self.header)
        self.assertIn('safety_model_tiny_predict_input', self.header)
        self.assertIn('safety_model_tiny_self_test', self.header)

    def test_mock_is_explicit_and_sos_is_deterministic(self) -> None:
        self.assertIn('SAFETY_MODEL_MOCK_VERSION "safety-model-mock-0.1.0"', self.source)
        self.assertIn('input->sos_pressed', self.source)
        self.assertIn('EGO_SC_RISK_MANUAL_SOS', self.source)
        self.assertIn('EGO_SC_ACTION_URGENT_ESCALATION', self.source)
        self.assertIn('SAFETY_MODEL_REASON_SAFETY_OVERRIDE', self.source)

    def test_mock_state_adapter_covers_current_device_signals(self) -> None:
        for field in [
            'wake_detected',
            'impact_detected',
            'gnss_fix_valid',
            'base_online',
            'upload_available',
            'signal_level',
            'battery_percent',
            'privacy_mode',
        ]:
            with self.subTest(field=field):
                self.assertIn(field, self.header)
                self.assertIn(field, self.source)

    def test_serial_cli_commands_are_registered(self) -> None:
        self.assertIn('safety_model_init', self.app_main)
        self.assertIn('safety_cli_task', self.app_main)
        self.assertIn('safety status', self.app_main)
        self.assertIn('safety demo normal', self.app_main)
        self.assertIn('safety demo sos', self.app_main)
        self.assertIn('safety demo impact', self.app_main)
        self.assertIn('safety tiny status', self.app_main)
        self.assertIn('safety tiny selftest', self.app_main)
        self.assertIn('safety tiny demo ', self.app_main)
        self.assertIn('safety_model_tiny_predict_input', self.app_main)
        self.assertIn('safety_model_tiny_self_test', self.app_main)


if __name__ == "__main__":
    unittest.main()
