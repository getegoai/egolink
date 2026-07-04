from __future__ import annotations

from pathlib import Path
import unittest


class AmoledAskUserDemoScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script = (self.repo_root / "scripts" / "run_amoled_ask_user_demo.ps1").read_text(encoding="utf-8")

    def test_script_auto_detects_amoled_usb_serial_jtag_without_hardcoded_com(self) -> None:
        required_terms = [
            "Get-CimInstance Win32_SerialPort",
            "Get-CimInstance Win32_PnPEntity",
            "VID_303A&PID_1001",
            '[string]$Port = ""',
            "[System.IO.Ports.SerialPort]::new",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)
        self.assertNotIn('[string]$Port = "COM9"', self.script)

    def test_script_supports_wait_for_motion_event(self) -> None:
        required_terms = [
            "WaitForMotionEvent",
            "motionSeen",
            "motion_event_seen",
            "motion_event",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_sends_versioned_ask_user_and_waits_for_reply(self) -> None:
        required_terms = [
            'protocol_version = "0.2"',
            'source = "pc-bridge"',
            'target = "wearable-node-001"',
            'type = "ask_user"',
            'cmd = "ask_user"',
            "cmd_id",
            "timestamp_ms",
            "session_id",
            "ask_user_rendered",
            "user_confirmation",
            "RequireConfirmation",
            "WaitSeconds",
            "ReadTimeout",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_can_send_sidecar_status_update(self) -> None:
        required_terms = [
            "SendStatusUpdate",
            "New-StatusUpdateCommandJson",
            'source = "pc-bridge-display"',
            'type = "status_update"',
            'cmd = "status_update"',
            "StatusLte",
            "StatusLocation",
            "StatusBattery",
            "status_rendered",
            "status_update_sent",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_writes_bounded_jsonl_evidence(self) -> None:
        required_terms = [
            "pc_simulator\\runtime\\demo_v0_2",
            "Write-Utf8NoBomLines",
            "summary.json",
            "skipped_non_json_lines",
            "exit 2",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)


if __name__ == "__main__":
    unittest.main()
