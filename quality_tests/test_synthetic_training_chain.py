from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import run_synthetic_training_chain


class SyntheticTrainingChainTests(unittest.TestCase):
    def run_chain(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = run_synthetic_training_chain.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def test_runs_synthetic_data_to_training_chain_without_raw_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "unit-synthetic-training-chain"
            exit_code, payload, stdout_text = self.run_chain(
                [
                    "--output-root",
                    str(root),
                    "--run-id",
                    run_id,
                    "--generated-at",
                    "2026-07-06T06:30:00+00:00",
                    "--scenario",
                    "normal_walk",
                    "--scenario",
                    "no_response",
                ]
            )
            run_dir = root / run_id
            summary_json = run_dir / "synthetic_training_chain.json"
            summary_md = run_dir / "synthetic_training_chain.md"
            scenario_json = run_dir / "synthetic_scenario_run.json"
            job_json = (
                run_dir
                / "training_jobs"
                / f"{run_id}-training-job"
                / "training_job_plan.json"
            )
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            summary_json_exists = summary_json.is_file()
            summary_md_exists = summary_md.is_file()
            scenario_json_exists = scenario_json.is_file()
            job_json_exists = job_json.is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.synthetic_training_chain.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "synthetic_training_chain_complete")
        self.assertTrue(payload["synthetic_only"])
        self.assertEqual(payload["counts"]["recordings"], 2)
        self.assertEqual(payload["counts"]["reviewed_records"], 2)
        self.assertEqual(payload["counts"]["feature_rows"], 2)
        self.assertEqual(payload["components"]["synthetic_scenarios"]["status"], "synthetic_ready_for_runner")
        self.assertEqual(
            payload["components"]["data_flywheel"]["reviewed"]["status"],
            "ready_for_training_handoff",
        )
        training = payload["components"]["training_chain"]
        self.assertEqual(training["components"]["preflight"]["status"], "ready_for_training_runner")
        self.assertEqual(
            training["components"]["feature_manifest"]["status"],
            "ready_for_synthetic_feature_dry_run",
        )
        self.assertEqual(
            training["components"]["runner_dry_run"]["status"],
            "synthetic_runner_dry_run_complete",
        )
        self.assertEqual(
            training["components"]["baseline_eval"]["status"],
            "synthetic_baseline_eval_complete",
        )
        self.assertEqual(
            training["components"]["handoff_bundle"]["status"],
            "synthetic_handoff_dry_run_only",
        )
        self.assertEqual(training["components"]["job_plan"]["status"], "synthetic_runner_queue_dry_run_only")
        self.assertTrue(training["components"]["job_plan"]["dry_run_only"])
        self.assertTrue(summary_json_exists)
        self.assertTrue(summary_md_exists)
        self.assertTrue(scenario_json_exists)
        self.assertTrue(job_json_exists)
        self.assertNotIn(str(root), output_text)
        self.assertNotIn("candidate_store.sqlite3", output_text)
        self.assertNotIn("synthetic_candidates.db", output_text)
        self.assertNotIn("record_json", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn('"features":', output_text)
        self.assertNotIn('"target":', output_text)


if __name__ == "__main__":
    unittest.main()
