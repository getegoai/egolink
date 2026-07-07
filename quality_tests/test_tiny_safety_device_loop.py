from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import prepare_tiny_safety_device_loop as device_loop


FIXED_CREATED_AT = "2026-07-07T12:00:00+00:00"


class TinySafetyDeviceLoopTests(unittest.TestCase):
    def test_default_cli_writes_offline_plan_without_hardware_or_secret_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-super-secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "plan"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = device_loop.main(
                    [
                        "--run-id",
                        "MODEL-DEVICE-005-unit",
                        "--output-dir",
                        str(output_dir),
                        "--hub-url",
                        "http://example.test:8790",
                        "--token-file",
                        str(token_file),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary["ok"])
            manifest = json.loads((output_dir / device_loop.PLAN_JSON).read_text(encoding="utf-8"))
            runbook = (output_dir / device_loop.RUNBOOK_MD).read_text(encoding="utf-8")
            notes = (output_dir / device_loop.NOTES_MD).read_text(encoding="utf-8")

            self.assertEqual(manifest["plan_version"], device_loop.PLAN_VERSION)
            self.assertEqual(manifest["task"], "MODEL-DEVICE-005")
            self.assertEqual(manifest["model"]["model_id"], device_loop.DEFAULT_MODEL_ID)
            self.assertIn("safety tiny status", manifest["model"]["firmware_cli_commands"])
            self.assertIn("safety tiny selftest", manifest["model"]["firmware_cli_commands"])
            self.assertTrue(manifest["model"]["synthetic_only"])
            self.assertFalse(manifest["model"]["external_actions"])

            scope = manifest["scope"]
            self.assertFalse(scope["commands_run"])
            self.assertFalse(scope["build_ran"])
            self.assertFalse(scope["hardware_contacted"])
            self.assertFalse(scope["serial_ports_opened"])
            self.assertFalse(scope["firmware_flashed"])
            self.assertFalse(scope["message_hub_contacted"])
            self.assertFalse(scope["message_hub_commands_sent"])
            self.assertFalse(scope["secrets_read"])
            self.assertFalse(scope["secrets_persisted"])
            self.assertFalse(scope["gitlab_modified"])

            commands = manifest["commands"]
            self.assertIn("build_d1_tiny_cli_image", commands)
            self.assertIn("flash_explicit_operator_action", commands)
            self.assertIn("serial_tiny_safety_validation", commands)
            self.assertIn("usb_free_d1_web_check_after_flash", commands)
            self.assertIn("short_usb_free_observer_after_flash", commands)

            build_argv = commands["build_d1_tiny_cli_image"]["argv"]
            self.assertIn("scripts\\run_fw001_hw_r1.ps1", build_argv)
            self.assertIn("-PrepareBuild", build_argv)
            self.assertNotIn("-Flash", build_argv)
            self.assertIn("-EnableSim7670Gnss", build_argv)
            self.assertIn("-EnableSim7670LteStatus", build_argv)
            self.assertIn("-EnableSim7670LteHttpCommandLoop", build_argv)
            self.assertIn("-EnableSim7670LocationObservation", build_argv)
            self.assertIn("-EnableD1PeriodicLocation", build_argv)
            self.assertIn("-EnableMax17048Power", build_argv)
            self.assertIn("-BuildDir", build_argv)
            self.assertIn(device_loop.DEFAULT_BUILD_DIR, build_argv)
            self.assertTrue(commands["build_d1_tiny_cli_image"]["runs_build"])
            self.assertFalse(commands["build_d1_tiny_cli_image"]["hardware_action"])

            flash = commands["flash_explicit_operator_action"]
            self.assertTrue(flash["hardware_action"])
            self.assertTrue(flash["flashes_firmware"])
            self.assertTrue(flash["requires_operator_intent"])
            self.assertIn("-Flash", flash["argv"])
            self.assertIn("-FlashPort", flash["argv"])
            self.assertIn("<COMx>", flash["argv"])
            self.assertIn("-IUnderstandFlashWritesFirmware", flash["argv"])

            serial = commands["serial_tiny_safety_validation"]
            self.assertTrue(serial["hardware_action"])
            self.assertTrue(serial["opens_serial_port"])
            self.assertTrue(serial["requires_operator_intent"])
            self.assertIn("scripts\\validate_tiny_safety_firmware_cli.py", serial["argv"])
            self.assertIn("--port", serial["argv"])
            self.assertIn("<COMx>", serial["argv"])
            self.assertIn("--i-understand-serial-hardware", serial["argv"])

            web = commands["usb_free_d1_web_check_after_flash"]
            self.assertTrue(web["contacts_message_hub"])
            self.assertFalse(web["hardware_action"])
            self.assertIn("scripts\\validate_d1_web_api.py", web["argv"])
            self.assertIn("--device-id", web["argv"])

            observer = commands["short_usb_free_observer_after_flash"]
            self.assertTrue(observer["contacts_message_hub"])
            self.assertFalse(observer["hardware_action"])
            self.assertIn("scripts\\observe_d1_field_run.py", observer["argv"])
            self.assertIn("--sample-count", observer["argv"])
            self.assertIn(str(device_loop.DEFAULT_OBSERVER_SAMPLE_COUNT), observer["argv"])
            self.assertIn("--poll-interval-sec", observer["argv"])
            self.assertIn(str(device_loop.DEFAULT_OBSERVER_POLL_INTERVAL_SEC), observer["argv"])

            self.assertIn("tiny_safety_cli_report", manifest["expected_outputs"])
            self.assertIn("post_flash_web_api_report", manifest["expected_outputs"])
            self.assertIn("post_flash_observer_report", manifest["expected_outputs"])
            self.assertIn("firmware_binary", manifest["expected_outputs"])
            self.assertIn("tiny_safety_cli", manifest["firmware"]["features"])
            self.assertIn("default_plan_does_not_flash_firmware", manifest["non_claims"])
            self.assertIn("model_output_not_mapped_to_sms_calls_dispatch_or_external_escalation", manifest["non_claims"])
            self.assertIn("no_real_world_model_accuracy_claim", manifest["non_claims"])
            self.assertIn("no_latency_ram_flash_or_power_measurement_claim", manifest["non_claims"])

            combined = json.dumps(manifest) + runbook + notes + stdout.getvalue()
            self.assertNotIn("unit-super-secret-token", combined)
            self.assertNotIn("COM4", combined)
            self.assertNotIn("COM9", combined)
            self.assertIn("<COMx>", combined)
            self.assertIn("Tiny Safety Device Loop Runbook", runbook)
            self.assertIn("safety tiny demo", runbook)
            self.assertIn("Optional Flash", runbook)
            self.assertIn("USB-Free D1 Web Check", runbook)
            self.assertIn("Tiny Safety Device Loop Operator Notes", notes)

    def test_custom_plan_preserves_build_and_observer_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = device_loop.prepare_device_loop(
                run_id="MODEL-DEVICE-005-custom",
                output_dir=Path(tmp),
                hub_url="https://hub.example:9443",
                device_id="ego-link-r1-connectivity-001",
                board_id="connectivity-node-001",
                fw_version="0.1.0-custom",
                model_id=device_loop.DEFAULT_MODEL_ID,
                model_version=device_loop.DEFAULT_MODEL_VERSION,
                test_run_id="MODEL-DEVICE-005-custom-d1",
                token_file="server/runtime/token.txt",
                build_dir="build_custom_tiny",
                location_interval_sec=120,
                observer_sample_count=5,
                observer_poll_interval_sec=7,
                max17048_sda_gpio=3,
                max17048_scl_gpio=2,
                created_at=FIXED_CREATED_AT,
                git_commit="abc1234",
            )

            self.assertEqual(manifest["created_at"], FIXED_CREATED_AT)
            self.assertEqual(manifest["git_commit"], "abc1234")
            self.assertEqual(manifest["hub"]["hub_url"], "https://hub.example:9443")
            self.assertEqual(manifest["hub"]["host_name"], "hub.example")
            self.assertEqual(manifest["hub"]["port"], 9443)
            self.assertEqual(manifest["hub"]["scheme"], "https")
            self.assertEqual(manifest["firmware"]["build_dir"], "build_custom_tiny")
            self.assertEqual(manifest["firmware"]["d1_periodic_location_interval_sec"], 120)
            self.assertEqual(manifest["firmware"]["max17048_sda_gpio"], 3)
            self.assertEqual(manifest["firmware"]["max17048_scl_gpio"], 2)
            self.assertIn(
                "firmware\\mqtt_heartbeat\\build_custom_tiny\\egolink_mqtt_heartbeat.bin",
                manifest["expected_outputs"]["firmware_binary"],
            )

            build_argv = manifest["commands"]["build_d1_tiny_cli_image"]["argv"]
            self.assertIn("-D1PeriodicLocationIntervalSec", build_argv)
            self.assertIn("120", build_argv)
            self.assertIn("-Max17048SdaGpio", build_argv)
            self.assertIn("3", build_argv)
            self.assertIn("-Max17048SclGpio", build_argv)
            self.assertIn("2", build_argv)

            observer_argv = manifest["commands"]["short_usb_free_observer_after_flash"]["argv"]
            self.assertIn("--sample-count", observer_argv)
            self.assertIn("5", observer_argv)
            self.assertIn("--poll-interval-sec", observer_argv)
            self.assertIn("7", observer_argv)
            self.assertIn("--max-stale-sec", observer_argv)
            self.assertIn("360", observer_argv)

    def test_invalid_inputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = {
                "run_id": "MODEL-DEVICE-005-invalid",
                "output_dir": Path(tmp),
                "hub_url": "http://hub.example:8790",
                "device_id": "ego-link-r1-connectivity-001",
                "board_id": "connectivity-node-001",
                "fw_version": device_loop.DEFAULT_FW_VERSION,
                "model_id": device_loop.DEFAULT_MODEL_ID,
                "model_version": device_loop.DEFAULT_MODEL_VERSION,
                "test_run_id": "MODEL-DEVICE-005-invalid-d1",
                "token_file": device_loop.DEFAULT_TOKEN_FILE,
                "build_dir": device_loop.DEFAULT_BUILD_DIR,
                "location_interval_sec": 60,
                "observer_sample_count": 3,
                "observer_poll_interval_sec": 10,
                "max17048_sda_gpio": 15,
                "max17048_scl_gpio": 16,
            }
            bad_hub = dict(base, hub_url="hub.example:8790")
            with self.assertRaises(device_loop.TinySafetyDeviceLoopError):
                device_loop.prepare_device_loop(**bad_hub)
            bad_interval = dict(base, location_interval_sec=10)
            with self.assertRaises(device_loop.TinySafetyDeviceLoopError):
                device_loop.prepare_device_loop(**bad_interval)
            bad_observer = dict(base, observer_sample_count=0)
            with self.assertRaises(device_loop.TinySafetyDeviceLoopError):
                device_loop.prepare_device_loop(**bad_observer)

    def test_planner_does_not_contain_direct_hardware_or_vps_operations(self) -> None:
        source = Path(device_loop.__file__).read_text(encoding="utf-8")
        forbidden_snippets = [
            "System.IO.Ports.SerialPort",
            "Invoke-RestMethod",
            "idf.py flash",
            "Start-Process",
            "requests.",
            "serial.Serial",
        ]
        for snippet in forbidden_snippets:
            with self.subTest(snippet=snippet):
                self.assertNotIn(snippet, source)


if __name__ == "__main__":
    unittest.main()
