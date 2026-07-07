from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import validate_tiny_safety_firmware_cli as validator


MODEL_ID = "MODEL-DEVICE-001-tiny-safety-v0-20260707"
MODEL_VERSION = "0.1.0-synthetic-dry-run"
HARNESS = "tiny-safety-fw-harness-0.1.0"


class TinySafetyFirmwareCliValidatorTests(unittest.TestCase):
    def run_cli(self, args: list[str]) -> int:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return validator.main(args)

    def load_report(self, root: Path, run_id: str) -> dict:
        return json.loads(
            (root / run_id / "tiny_safety_cli_report.json").read_text(encoding="utf-8")
        )

    def test_default_dry_run_writes_no_hardware_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            code = self.run_cli(["--output-dir", str(output_root), "--run-id", "dry"])
            payload = self.load_report(output_root, "dry")

        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "dry_run")
        self.assertFalse(payload["hardware_contacted"])
        self.assertFalse(payload["serial_port_opened"])
        self.assertFalse(payload["firmware_flashed"])
        self.assertEqual(payload["commands_sent"], [])
        self.assertEqual(len(payload["commands_planned"]), len(validator.COMMANDS))
        self.assertEqual(payload["result"], "not_run")
        self.assertFalse(any(check["status"] == "FAIL" for check in payload["checks"]))

    def test_serial_port_requires_explicit_hardware_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            code = self.run_cli(
                ["--output-dir", str(output_root), "--run-id", "guard", "--port", "TESTPORT"]
            )

            self.assertEqual(code, 2)
            self.assertFalse((output_root / "guard").exists())

    def test_passing_fixture_log_validates_all_tiny_safety_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            fixture = output_root / "passing.log"
            fixture.write_text(passing_fixture_log(), encoding="utf-8")

            code = self.run_cli(
                [
                    "--output-dir",
                    str(output_root),
                    "--run-id",
                    "fixture-pass",
                    "--fixture-log",
                    str(fixture),
                ]
            )
            payload = self.load_report(output_root, "fixture-pass")

        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual(payload["result"], "pass")
        self.assertFalse(payload["hardware_contacted"])
        self.assertEqual(len(payload["observations"]), 8)
        self.assertTrue(all(check["status"] == "PASS" for check in payload["checks"]))

    def test_failing_fixture_log_returns_nonzero_and_records_failed_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            fixture = output_root / "bad.log"
            fixture.write_text(
                passing_fixture_log().replace("label=possible_risk", "label=needs_check", 1),
                encoding="utf-8",
            )

            code = self.run_cli(
                [
                    "--output-dir",
                    str(output_root),
                    "--run-id",
                    "fixture-fail",
                    "--fixture-log",
                    str(fixture),
                ]
            )
            payload = self.load_report(output_root, "fixture-fail")

        self.assertEqual(code, 2)
        failed = {check["check"] for check in payload["checks"] if check["status"] == "FAIL"}
        self.assertIn("demo_labels", failed)
        self.assertEqual(payload["result"], "fail")

    def test_parser_ignores_prefix_variants_and_non_marker_fail_lines(self) -> None:
        self.assertIsNone(validator.parse_marker_line("TINY_SAFETY_DEMO_INPUT_FAIL name=normal"))
        parsed = validator.parse_marker_line(
            "I (123) egolink: TINY_SAFETY_DEMO name=normal "
            f"model_id={MODEL_ID} model_version={MODEL_VERSION} harness={HARNESS} "
            "label=normal class=0 confidence=0.900 raw=1.000 margin=0.500 "
            "synthetic_only=true safety_rule_required=false dry_run=true"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["marker"], "TINY_SAFETY_DEMO")
        self.assertEqual(parsed["fields"]["label"], "normal")

    def test_script_boundary_is_guarded_and_non_flashing(self) -> None:
        script_source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "validate_tiny_safety_firmware_cli.py"
        ).read_text(encoding="utf-8")

        self.assertIn("System.IO.Ports.SerialPort", script_source)
        self.assertIn("--i-understand-serial-hardware", script_source)
        self.assertNotIn("COM4", script_source)
        self.assertNotIn("ATD", script_source)
        self.assertNotIn("CMGS", script_source)
        self.assertNotIn("write_flash", script_source)
        self.assertNotIn("idf.py -p", script_source)


def passing_fixture_log() -> str:
    common = f"model_id={MODEL_ID} model_version={MODEL_VERSION} harness={HARNESS}"
    lines = [
        (
            "I (10) egolink: TINY_SAFETY_STATUS "
            f"{common} features=14 classes=4 synthetic_only=true dry_run=true external_actions=false"
        ),
        (
            "I (20) egolink: TINY_SAFETY_SELFTEST "
            f"{common} vectors=4 passed=4 failed=0 first_failed=255 synthetic_only=true dry_run=true result=pass"
        ),
    ]
    demo_rows = [
        ("normal", "normal", "0", "false"),
        ("uncertain", "uncertain", "1", "false"),
        ("needs_check", "needs_check", "2", "false"),
        ("possible_risk", "possible_risk", "3", "false"),
        ("sos", "safety_rule_required", "255", "true"),
        ("cancel", "safety_rule_required", "255", "true"),
    ]
    for name, label, class_index, safety_rule_required in demo_rows:
        lines.append(
            "I (30) egolink: TINY_SAFETY_DEMO "
            f"name={name} {common} label={label} class={class_index} confidence=0.900 "
            "raw=1.000 margin=0.500 synthetic_only=true "
            f"safety_rule_required={safety_rule_required} dry_run=true"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    unittest.main()
