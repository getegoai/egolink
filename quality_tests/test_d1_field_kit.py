from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import prepare_d1_field_kit as field_kit


FIXED_CREATED_AT = "2026-07-04T12:00:00+00:00"


class D1FieldKitTests(unittest.TestCase):
    def test_default_cli_writes_offline_field_kit_without_secret_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-super-secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "kit"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = field_kit.main(
                    [
                        "--run-id",
                        "D1-FIELD-unit",
                        "--hub-url",
                        "http://example.test:8790",
                        "--token-file",
                        str(token_file),
                        "--output-dir",
                        str(output_dir),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary["ok"])
            manifest = json.loads((output_dir / field_kit.MANIFEST_JSON).read_text(encoding="utf-8"))
            runbook = (output_dir / field_kit.RUNBOOK_MD).read_text(encoding="utf-8")
            checklist = (output_dir / field_kit.CHECKLIST_MD).read_text(encoding="utf-8")
            notes = (output_dir / field_kit.NOTES_MD).read_text(encoding="utf-8")

            self.assertEqual(manifest["kit_version"], field_kit.KIT_VERSION)
            self.assertEqual(manifest["power"]["max17048_sda_gpio"], 15)
            self.assertEqual(manifest["power"]["max17048_scl_gpio"], 16)
            self.assertFalse(manifest["scope"]["hardware_contacted"])
            self.assertFalse(manifest["scope"]["message_hub_contacted"])
            self.assertFalse(manifest["scope"]["firmware_flashed"])
            self.assertFalse(manifest["secrets"]["token_value_read"])
            self.assertIn("-PrepareBuild", manifest["commands"]["prepare_build"]["argv"])
            self.assertNotIn("-Flash", manifest["commands"]["prepare_build"]["argv"])
            self.assertTrue(manifest["commands"]["flash_explicit_operator_action"]["hardware_action"])
            self.assertTrue(manifest["commands"]["short_usb_free_link_check"]["sends_message_hub_command"])

            combined = json.dumps(manifest) + runbook + checklist + notes + stdout.getvalue()
            self.assertNotIn("unit-super-secret-token", combined)
            self.assertIn("D1 Outdoor Field Runbook", runbook)
            self.assertIn("Before Leaving", checklist)
            self.assertIn("D1 Field Operator Notes", notes)

    def test_v1_board_uses_recorded_v1_max17048_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = field_kit.prepare_field_kit(
                run_id="D1-FIELD-v1",
                output_dir=Path(tmp),
                hub_url="",
                host_name="hub.example",
                port=8790,
                scheme="http",
                device_id="ego-link-r1-connectivity-001",
                board_id="connectivity-node-001",
                fw_version="0.1.0-fw001-hw-r1",
                token_file="server/runtime/vps_message_hub_token.txt",
                duration_hours=3.5,
                board_revision="V1",
                max17048_sda_gpio=None,
                max17048_scl_gpio=None,
                battery_capacity_mah=1200,
                created_at=FIXED_CREATED_AT,
            )

            self.assertEqual(manifest["created_at"], FIXED_CREATED_AT)
            self.assertEqual(manifest["hub"]["hub_url"], "http://hub.example:8790")
            self.assertEqual(manifest["power"]["max17048_sda_gpio"], 3)
            self.assertEqual(manifest["power"]["max17048_scl_gpio"], 2)
            power_argv = manifest["commands"]["post_run_power_curve"]["argv"]
            self.assertIn("--min-duration-hours", power_argv)
            self.assertIn("3.5", power_argv)
            self.assertIn("--battery-capacity-mah", power_argv)
            self.assertIn("1200", power_argv)

    def test_partial_pin_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(field_kit.D1FieldKitError):
                field_kit.prepare_field_kit(
                    run_id="D1-FIELD-bad-pins",
                    output_dir=Path(tmp),
                    hub_url="",
                    host_name="hub.example",
                    port=8790,
                    scheme="http",
                    device_id="ego-link-r1-connectivity-001",
                    board_id="connectivity-node-001",
                    fw_version="0.1.0-fw001-hw-r1",
                    token_file="server/runtime/vps_message_hub_token.txt",
                    duration_hours=4,
                    board_revision="V2",
                    max17048_sda_gpio=15,
                    max17048_scl_gpio=None,
                    battery_capacity_mah=None,
                    created_at=FIXED_CREATED_AT,
                )


if __name__ == "__main__":
    unittest.main()
