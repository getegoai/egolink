from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import event_store
from scripts import local_session_summary


class LocalSessionSummaryTests(unittest.TestCase):
    def test_build_report_counts_recent_events_and_safety_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "events.jsonl"
            event_store.append_jsonl(
                event_log,
                {
                    "event_type": "sensor_sample",
                    "device_id": "ego-link-001",
                    "seq": 10,
                    "wifi_rssi": -44,
                },
            )
            event_store.append_jsonl(
                event_log,
                {
                    "event_type": "safety_evaluation",
                    "device_id": "ego-link-001",
                    "seq": 11,
                    "risk_type": "none",
                    "recommended_action": "ignore",
                },
            )
            event_store.append_jsonl(
                event_log,
                {
                    "event_type": "safety_event",
                    "device_id": "ego-link-001",
                    "seq": 12,
                    "risk_type": "manual_sos",
                    "recommended_action": "urgent_escalation",
                },
            )

            report = local_session_summary.build_report_from_log(
                event_log,
                limit=10,
                dashboard_url="http://127.0.0.1:8787",
                broker="192.168.31.250:1883",
                dashboard_pid=123,
                worker_pid=456,
            )

        self.assertEqual(report["event_count"], 3)
        self.assertEqual(report["counts"]["sensor_sample"], 1)
        self.assertEqual(report["counts"]["safety_evaluation"], 1)
        self.assertEqual(report["counts"]["safety_event"], 1)
        self.assertEqual(report["safety"]["evaluations"], 1)
        self.assertEqual(report["safety"]["safety_events"], 1)
        self.assertEqual(report["safety"]["latest_risk_type"], "none")
        self.assertEqual(report["endpoints"]["dashboard_url"], "http://127.0.0.1:8787")
        self.assertEqual(report["processes"]["worker_pid"], 456)

    def test_write_report_files_outputs_json_and_markdown(self) -> None:
        report = local_session_summary.summarize_events(
            [
                {
                    "event_type": "safety_evaluation",
                    "seq": 1,
                    "risk_type": "manual_sos",
                    "recommended_action": "urgent_escalation",
                }
            ],
            event_log=Path("events.jsonl"),
            dashboard_url="http://127.0.0.1:8787",
            broker="192.168.31.250:1883",
        )

        with tempfile.TemporaryDirectory() as tmp:
            json_path, markdown_path = local_session_summary.write_report_files(report, Path(tmp))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(payload["safety"]["latest_action"], "urgent_escalation")
        self.assertIn("Ego Link Local Session Summary", markdown)
        self.assertIn("manual_sos", markdown)
        self.assertIn("urgent_escalation", markdown)

    def test_supervised_session_script_declares_required_processes_and_logs(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "start_local_supervised_session.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts\\start_mosquitto_lan.ps1", script)
        self.assertIn("pc_simulator\\app.py", script)
        self.assertIn("pc_simulator\\mqtt_worker.py", script)
        self.assertIn("--process-safety", script)
        self.assertIn("--safety-process-limit", script)
        self.assertIn("scripts\\local_session_summary.py", script)
        self.assertIn("scripts\\session_recorder.py", script)
        self.assertIn("scripts\\inspect_session_recording.py", script)
        self.assertIn("recording\\session_recording.md", script)
        self.assertIn("recording\\session_quality_report.md", script)
        self.assertIn("NoRecorder", script)
        self.assertIn("NoQualityGate", script)
        self.assertIn("session_summary.md", script)
        self.assertIn("mqtt_safety_worker.stderr.log", script)


if __name__ == "__main__":
    unittest.main()
