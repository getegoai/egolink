from __future__ import annotations

from pathlib import Path
import unittest


class D1FieldCompanionScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script = (self.repo_root / "scripts" / "run_d1_field_companion.ps1").read_text(encoding="utf-8")

    def test_companion_launches_observer_and_amoled_sidecar(self) -> None:
        required_terms = [
            "scripts\\observe_d1_field_run.py",
            "scripts\\run_amoled_d1_status_sidecar.ps1",
            "Start-LoggedProcess",
            "Start-Process",
            "-WindowStyle Hidden",
            "WaitForExit()",
            ".Refresh()",
            "observer.stdout.log",
            "observer.stderr.log",
            "amoled.stdout.log",
            "amoled.stderr.log",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_companion_shares_run_id_sample_count_and_poll_interval(self) -> None:
        required_terms = [
            "RunId",
            "Resolve-SampleCount",
            "--run-id",
            "-SessionId",
            "--sample-count",
            "-SampleCount",
            "--poll-interval-sec",
            "-PollIntervalSec",
            "DurationMinutes",
            "MaxStaleSec",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_companion_writes_summary_and_markdown(self) -> None:
        required_terms = [
            "d1_field_companion_summary.json",
            "d1_field_companion_summary.md",
            "Write-CompanionMarkdown",
            "children",
            "exit_code",
            "effective_exit_code",
            "exit_code_source",
            "Get-EffectiveChildExit",
            "observer_summary_result",
            "amoled_summary_ok",
            "summary_path",
            "markdown_summary_path",
            "reports\\d1_field_companion",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_companion_supports_focused_children(self) -> None:
        required_terms = [
            "NoAmoled",
            "NoObserver",
            "At least one child runner must be enabled",
            "enabled = $false",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_companion_preserves_sidecar_and_non_claim_boundaries(self) -> None:
        required_terms = [
            "sends_message_hub_commands = $false",
            "contacts_4g_board_serial = $false",
            "flashes_firmware = $false",
            "modifies_gitlab = $false",
            "claims_location_accuracy = $false",
            "claims_gnss_acceptance = $false",
            "claims_battery_life = $false",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

        forbidden_terms = [
            "/api/commands",
            "request_location",
            "COM4",
            "VID_1A86&PID_55D3",
        ]
        for term in forbidden_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, self.script)


if __name__ == "__main__":
    unittest.main()
