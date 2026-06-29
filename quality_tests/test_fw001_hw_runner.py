from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


class FW001HardwareRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script = self.repo_root / "scripts" / "run_fw001_hw_r1.ps1"
        self.script_text = self.script.read_text(encoding="utf-8")

    def run_runner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script),
                *args,
            ],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )

    def test_default_execution_is_plan_only(self) -> None:
        result = self.run_runner("-HostName", "example.invalid", "-TestRunId", "field-r1-unit", "-Json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "plan")
        self.assertEqual(payload["test_run_id"], "field-r1-unit")
        self.assertFalse(payload["prepare_build_ran"])
        self.assertFalse(payload["flash_ran"])
        self.assertFalse(payload["validate_ran"])
        self.assertFalse(payload["sim7670_gnss_enabled"])
        self.assertFalse(payload["sim7670_lte_status_enabled"])
        self.assertFalse(payload["sim7670_lte_http_probe_enabled"])
        self.assertFalse(payload["sim7670_lte_http_command_loop_enabled"])
        self.assertEqual(payload["existing_command_id"], "")
        self.assertEqual(payload["expected_ack_test_run_id"], "")
        self.assertEqual(payload["lte_command_name"], "set_report_interval")
        self.assertFalse(payload["require_lte_location_report"])
        self.assertFalse(payload["require_location_fix"])
        self.assertIn("IUnderstandFlashWritesFirmware", payload["flash_guard"])

    def test_flash_requires_explicit_confirmation_and_port(self) -> None:
        result = self.run_runner("-HostName", "example.invalid", "-Flash", "-Json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IUnderstandFlashWritesFirmware", result.stderr)

    def test_flash_requires_port_even_with_confirmation(self) -> None:
        result = self.run_runner(
            "-HostName",
            "example.invalid",
            "-Flash",
            "-IUnderstandFlashWritesFirmware",
            "-Json",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FlashPort", result.stderr)

    def test_validation_requires_usb_free_operator_confirmations(self) -> None:
        result = self.run_runner("-HostName", "example.invalid", "-Validate", "-Json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OperatorConfirmedIndependentPower", result.stderr)

    def test_runner_reuses_existing_prepare_and_validation_scripts(self) -> None:
        self.assertIn("prepare_fw001_hw_config.ps1", self.script_text)
        self.assertIn("validate_fw001_hw_loop.py", self.script_text)
        self.assertIn("idf.py -B $BuildDir -p $FlashPort flash", self.script_text)
        self.assertIn("Flash requires -IUnderstandFlashWritesFirmware", self.script_text)
        self.assertIn("Validation requires -OperatorConfirmedUsbDisconnected", self.script_text)
        self.assertIn("[switch]$EnableSim7670Gnss", self.script_text)
        self.assertIn("[switch]$EnableSim7670LteStatus", self.script_text)
        self.assertIn("[switch]$EnableSim7670LteHttpProbe", self.script_text)
        self.assertIn("[switch]$EnableSim7670LteHttpCommandLoop", self.script_text)
        self.assertIn("[string]$ExistingCommandId", self.script_text)
        self.assertIn("[string]$ExpectedAckTestRunId", self.script_text)
        self.assertIn("[string]$LteCommandName", self.script_text)
        self.assertIn("[switch]$RequireLteLocationReport", self.script_text)
        self.assertIn("[switch]$RequireLocationFix", self.script_text)
        self.assertIn('Add-If $prepareArgs $EnableSim7670Gnss "-EnableSim7670Gnss"', self.script_text)
        self.assertIn('Add-If $prepareArgs $EnableSim7670LteStatus "-EnableSim7670LteStatus"', self.script_text)
        self.assertIn('Add-If $prepareArgs $EnableSim7670LteHttpProbe "-EnableSim7670LteHttpProbe"', self.script_text)
        self.assertIn(
            'Add-If $prepareArgs $EnableSim7670LteHttpCommandLoop "-EnableSim7670LteHttpCommandLoop"',
            self.script_text,
        )
        self.assertIn("validate_lte_http_probe.py", self.script_text)
        self.assertIn("validate_lte_command_loop.py", self.script_text)
        self.assertIn("--expected-fw-version", self.script_text)
        self.assertIn("--existing-command-id", self.script_text)
        self.assertIn("--expected-ack-test-run-id", self.script_text)
        self.assertIn("--command", self.script_text)
        self.assertIn("--require-location-report", self.script_text)
        self.assertIn("--require-fix", self.script_text)
        self.assertIn("ForEach-Object { $prepareArgs.Add([string]$_) }", self.script_text)
        self.assertNotIn("$prepareArgs.AddRange(@(", self.script_text)
        self.assertIn("function ConvertFrom-LastJsonObject", self.script_text)
        self.assertIn("ConvertFrom-LastJsonObject $prepareOutput", self.script_text)


if __name__ == "__main__":
    unittest.main()
