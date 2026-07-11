from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts import prepare_d2_field_kit as field_kit


class D2FieldKitTests(unittest.TestCase):
    def test_prepare_kit_writes_strict_manifest_and_read_only_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = field_kit.prepare_kit(
                output_root=root,
                run_id="D2-001-unit-field",
                hub_url="http://example.test:8790",
                device_id="device-unit",
                board_id="board-unit",
                fw_version="fw-unit",
                firmware_ref="git:abc123",
                message_test_run_id="message-run-unit",
                token_file="runtime/token.txt",
                generated_at="2026-07-11T00:00:00+00:00",
            )
            output_dir = root / "D2-001-unit-field"
            manifest = json.loads((output_dir / field_kit.FIELD_MANIFEST).read_text(encoding="utf-8"))
            runbook = (output_dir / field_kit.RUNBOOK).read_text(encoding="utf-8")
            checklist = (output_dir / field_kit.CHECKLIST).read_text(encoding="utf-8")

        self.assertEqual(kit["schema_version"], "D2.reference_field_kit.v1")
        self.assertEqual(len(manifest["reference_points"]), 3)
        self.assertEqual(len(manifest["attempts"]), 30)
        self.assertEqual({row["mode"] for row in manifest["attempts"]}, {"cold", "warm"})
        self.assertEqual(manifest["test_run_id"], "message-run-unit")
        self.assertFalse(manifest["runtime_usb_connected"])
        self.assertTrue(all(command["read_only"] for command in kit["commands"].values()))
        self.assertFalse(any(kit["scope"].values()))
        self.assertIn("--device-id", kit["commands"]["postrun"]["argv"])
        self.assertNotIn("--test-run-id", kit["commands"]["postrun"]["argv"])
        self.assertIn("run_location_d2_d5_pipeline.py", runbook)
        self.assertIn("partial/failed gate", runbook)
        self.assertIn("Exact coordinates were not copied", checklist)
        serialized = json.dumps(kit, ensure_ascii=False)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("Bearer", serialized)

    def test_invalid_run_id_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(field_kit.D2FieldKitError):
                field_kit.prepare_kit(
                    output_root=root,
                    run_id="../outside",
                    hub_url="http://example.test:8790",
                    device_id="device-unit",
                    board_id="board-unit",
                    fw_version="fw-unit",
                    firmware_ref="git:abc123",
                    message_test_run_id="message-run-unit",
                    token_file="runtime/token.txt",
                )
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
