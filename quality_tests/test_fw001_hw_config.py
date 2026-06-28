from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class FW001HardwareConfigScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script = self.repo_root / "scripts" / "prepare_fw001_hw_config.ps1"

    def test_script_writes_ignored_local_config_without_printing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            source_sdkconfig = firmware_dir / "sdkconfig"
            source_sdkconfig.write_text(
                '\n'.join(
                    [
                        'CONFIG_EGOLINK_WIFI_SSID="lab-wifi"',
                        'CONFIG_EGOLINK_WIFI_PASSWORD="lab-secret"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")
            config_path = firmware_dir / "sdkconfig.vps.local"

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(config_path),
                    "-SourceSdkconfig",
                    str(source_sdkconfig),
                    "-TestRunId",
                    "field-r1-unit",
                    "-Json",
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            config = config_path.read_text(encoding="utf-8-sig")
            config_bytes = config_path.read_bytes()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["flash_intentionally_not_run"])
        self.assertEqual(payload["token_source"], "token_file")
        self.assertEqual(payload["test_run_id"], "field-r1-unit")
        self.assertFalse(payload["sim7670_gnss_enabled"])
        self.assertFalse(payload["sim7670_lte_status_enabled"])
        self.assertFalse(payload["sim7670_lte_http_probe_enabled"])
        self.assertFalse(payload["sim7670_lte_http_command_loop_enabled"])
        self.assertNotIn("unit-secret-token", result.stdout)
        self.assertIn('CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED=y', config)
        self.assertIn('CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL="http://example.invalid:8790"', config)
        self.assertIn('CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN="unit-secret-token"', config)
        self.assertIn('CONFIG_EGOLINK_TEST_RUN_ID="field-r1-unit"', config)
        self.assertIn('CONFIG_EGOLINK_WIFI_SSID="lab-wifi"', config)
        self.assertIn('CONFIG_EGOLINK_WIFI_PASSWORD="lab-secret"', config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_GNSS_ENABLED is not set", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED is not set", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED is not set", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED is not set", config)
        self.assertIn("SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.vps.local", payload["build_command"])
        self.assertNotIn("flash", payload["build_command"].lower())
        self.assertFalse(config_bytes.startswith(b"\xef\xbb\xbf"))

    def test_script_can_enable_fw002b_sim7670_gnss_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            source_sdkconfig = firmware_dir / "sdkconfig"
            source_sdkconfig.write_text('CONFIG_EGOLINK_WIFI_SSID="lab-wifi"\n', encoding="utf-8")
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")
            config_path = firmware_dir / "sdkconfig.vps.local"

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(config_path),
                    "-SourceSdkconfig",
                    str(source_sdkconfig),
                    "-EnableSim7670Gnss",
                    "-Json",
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            config = config_path.read_text(encoding="utf-8-sig")

        self.assertTrue(payload["sim7670_gnss_enabled"])
        self.assertNotIn("unit-secret-token", result.stdout)
        self.assertIn("CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_NUM=1", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_BAUD=115200", config)

    def test_script_can_enable_lte_status_config_without_gnss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            source_sdkconfig = firmware_dir / "sdkconfig"
            source_sdkconfig.write_text('CONFIG_EGOLINK_WIFI_SSID="lab-wifi"\n', encoding="utf-8")
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")
            config_path = firmware_dir / "sdkconfig.vps.local"

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(config_path),
                    "-SourceSdkconfig",
                    str(source_sdkconfig),
                    "-EnableSim7670LteStatus",
                    "-Json",
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            config = config_path.read_text(encoding="utf-8-sig")

        self.assertFalse(payload["sim7670_gnss_enabled"])
        self.assertTrue(payload["sim7670_lte_status_enabled"])
        self.assertFalse(payload["sim7670_lte_http_probe_enabled"])
        self.assertFalse(payload["sim7670_lte_http_command_loop_enabled"])
        self.assertIn("# CONFIG_EGOLINK_SIM7670_GNSS_ENABLED is not set", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED is not set", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED is not set", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_NUM=1", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_BAUD=115200", config)

    def test_script_can_enable_lte_http_probe_and_implies_lte_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            source_sdkconfig = firmware_dir / "sdkconfig"
            source_sdkconfig.write_text('CONFIG_EGOLINK_WIFI_SSID="lab-wifi"\n', encoding="utf-8")
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")
            config_path = firmware_dir / "sdkconfig.vps.local"

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(config_path),
                    "-SourceSdkconfig",
                    str(source_sdkconfig),
                    "-EnableSim7670LteHttpProbe",
                    "-Json",
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            config = config_path.read_text(encoding="utf-8-sig")

        self.assertFalse(payload["sim7670_gnss_enabled"])
        self.assertTrue(payload["sim7670_lte_status_enabled"])
        self.assertTrue(payload["sim7670_lte_http_probe_enabled"])
        self.assertFalse(payload["sim7670_lte_http_command_loop_enabled"])
        self.assertNotIn("unit-secret-token", result.stdout)
        self.assertIn("CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED=y", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_NUM=1", config)

    def test_script_can_enable_lte_http_command_loop_and_implies_lte_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            source_sdkconfig = firmware_dir / "sdkconfig"
            source_sdkconfig.write_text('CONFIG_EGOLINK_WIFI_SSID="lab-wifi"\n', encoding="utf-8")
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")
            config_path = firmware_dir / "sdkconfig.vps.local"

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(config_path),
                    "-SourceSdkconfig",
                    str(source_sdkconfig),
                    "-EnableSim7670LteHttpCommandLoop",
                    "-Json",
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            config = config_path.read_text(encoding="utf-8-sig")

        self.assertFalse(payload["sim7670_gnss_enabled"])
        self.assertTrue(payload["sim7670_lte_status_enabled"])
        self.assertFalse(payload["sim7670_lte_http_probe_enabled"])
        self.assertTrue(payload["sim7670_lte_http_command_loop_enabled"])
        self.assertNotIn("unit-secret-token", result.stdout)
        self.assertIn("CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y", config)
        self.assertIn("# CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED is not set", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y", config)
        self.assertIn("CONFIG_EGOLINK_SIM7670_UART_NUM=1", config)

    def test_script_rejects_tracked_config_path_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            firmware_dir = tmp_path / "firmware"
            firmware_dir.mkdir()
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-secret-token\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script),
                    "-HostName",
                    "example.invalid",
                    "-TokenFile",
                    str(token_file),
                    "-FirmwareDir",
                    str(firmware_dir),
                    "-ConfigPath",
                    str(firmware_dir / "sdkconfig.vps"),
                    "-Json",
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sdkconfig.vps.local", result.stderr)

    def test_build_phase_removes_stale_build_sdkconfig_before_idf_build(self) -> None:
        script_text = self.script.read_text(encoding="utf-8")

        self.assertIn('$buildSdkconfig = Join-Path $BuildDir "sdkconfig"', script_text)
        self.assertIn("Remove-Item -LiteralPath $buildSdkconfig -Force", script_text)
        self.assertIn("[switch]$EnableSim7670Gnss", script_text)
        self.assertIn("[switch]$EnableSim7670LteStatus", script_text)
        self.assertIn("[switch]$EnableSim7670LteHttpProbe", script_text)
        self.assertIn("[switch]$EnableSim7670LteHttpCommandLoop", script_text)

    def test_gitignore_keeps_local_vps_config_and_build_output_untracked(self) -> None:
        gitignore = (self.repo_root / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/**/sdkconfig.*.local", gitignore)
        self.assertIn("firmware/**/build_*/", gitignore)


if __name__ == "__main__":
    unittest.main()
