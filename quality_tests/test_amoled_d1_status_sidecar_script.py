from __future__ import annotations

from pathlib import Path
import unittest


class AmoledD1StatusSidecarScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script = (self.repo_root / "scripts" / "run_amoled_d1_status_sidecar.ps1").read_text(encoding="utf-8")

    def test_script_auto_detects_amoled_without_hardcoded_com9(self) -> None:
        required_terms = [
            "Find-AmoledPort",
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

    def test_script_reads_api_state_with_secret_hygiene(self) -> None:
        required_terms = [
            "Invoke-HubState",
            '"/api/state"',
            "Invoke-RestMethod",
            "EGOLINK_MESSAGE_HUB_TOKEN",
            "server\\runtime\\vps_message_hub_token.txt",
            "Authorization",
            "Bearer $Token",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)
        self.assertNotIn("Write-Host $token", self.script)
        self.assertNotIn("Write-Output $token", self.script)

    def test_script_converts_d1_link_to_status_update_payload(self) -> None:
        required_terms = [
            "New-D1StatusPayload",
            "New-D1StatusUpdateCommandJson",
            "d1_link",
            "upload_freshness",
            "freshness_s",
            "map_surface",
            "lat",
            "lon",
            "uplink_metrics",
            "raw_post_success_count",
            "raw_post_failure_count",
            "location_event_count",
            "power_curve",
            "cell_lte",
            "statusLabel",
            '"LIVE"',
            '"WAIT"',
            'Limit-Text "$statusLabel fresh $freshText / $lteText" 44',
            "display_status",
            'type = "display_status"',
            "pc-bridge-d1-status-sidecar",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_is_bounded_and_writes_evidence(self) -> None:
        required_terms = [
            "SampleCount",
            "PollIntervalSec",
            "ReadWindowSeconds",
            "status_rendered",
            "command_ack",
            "Write-Utf8NoBomLines",
            "Write-Utf8NoBomText",
            "pc_simulator\\runtime\\amoled_d1_status_sidecar",
            "summary.json",
            "jsonl_path",
            "exit 2",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_does_not_send_4g_or_message_hub_commands(self) -> None:
        forbidden_terms = [
            "/api/commands",
            "request_location",
            "COM4",
            "VID_1A86&PID_55D3",
            "contacts_4g_board_serial = $true",
            "sends_message_hub_commands = $true",
        ]
        for term in forbidden_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, self.script)
        self.assertIn("sends_message_hub_commands = $false", self.script)
        self.assertIn("contacts_4g_board_serial = $false", self.script)


if __name__ == "__main__":
    unittest.main()
