from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts import run_key_release_gate


class KeyReleaseGateTests(unittest.TestCase):
    def test_release_gate_passes_with_required_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs/current").mkdir(parents=True)
            (repo / "docs/current/STATUS.md").write_text("ok\n", encoding="utf-8")
            (repo / "reports/key").mkdir(parents=True)
            (repo / "reports/key/evidence.json").write_text("{}\n", encoding="utf-8")
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "released",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [
                    {"path": "docs/current/STATUS.md", "kind": "status", "required": True},
                    {
                        "path": "reports/key/evidence.json",
                        "kind": "runtime",
                        "required": True,
                        "local_only": True,
                    },
                ],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(manifest, repo_root=repo)

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["gate_count"], 1)
            self.assertEqual(report["non_claim_count"], 1)
            self.assertEqual(report["errors"], [])

    def test_release_gate_fails_when_required_evidence_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "released",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [{"path": "missing.md", "kind": "status", "required": True}],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(manifest, repo_root=repo)

            self.assertEqual(report["result"], "FAIL")
            self.assertIn("required evidence missing: missing.md", report["errors"])

    def test_release_gate_can_warn_for_missing_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "released",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [
                    {
                        "path": "reports/local-only.json",
                        "kind": "runtime",
                        "required": True,
                        "local_only": True,
                    }
                ],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(
                manifest,
                repo_root=repo,
                allow_missing_local_evidence=True,
            )

            self.assertEqual(report["result"], "PASS")
            self.assertIn("local evidence missing but allowed: reports/local-only.json", report["warnings"])

    def test_release_gate_passes_json_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "reports/key").mkdir(parents=True)
            (repo / "reports/key/evidence.json").write_text(
                '{"current_run":{"eale_p0":{"location_belief":{"state":"Unknown","quality_flags":["gnss_no_fix"]}}}}\n',
                encoding="utf-8",
            )
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "release_candidate",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [{"path": "reports/key/evidence.json", "kind": "runtime", "required": True}],
                "json_checks": [
                    {
                        "id": "JC1",
                        "path": "reports/key/evidence.json",
                        "json_path": "$.current_run.eale_p0.location_belief.state",
                        "operator": "equals",
                        "expected": "Unknown",
                    },
                    {
                        "id": "JC2",
                        "path": "reports/key/evidence.json",
                        "json_path": "$.current_run.eale_p0.location_belief.quality_flags",
                        "operator": "contains",
                        "expected": "gnss_no_fix",
                    },
                ],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(manifest, repo_root=repo)

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["json_checks"][0]["status"], "PASS")
            self.assertEqual(report["json_checks"][1]["status"], "PASS")

    def test_release_gate_fails_json_check_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "reports/key").mkdir(parents=True)
            (repo / "reports/key/evidence.json").write_text('{"state":"Fine"}\n', encoding="utf-8")
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "release_candidate",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [{"path": "reports/key/evidence.json", "kind": "runtime", "required": True}],
                "json_checks": [
                    {
                        "id": "JC1",
                        "path": "reports/key/evidence.json",
                        "json_path": "$.state",
                        "operator": "equals",
                        "expected": "Unknown",
                    }
                ],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(manifest, repo_root=repo)

            self.assertEqual(report["result"], "FAIL")
            self.assertEqual(report["json_checks"][0]["status"], "FAIL")
            self.assertTrue(any("json_check JC1 failed" in error for error in report["errors"]))

    def test_release_gate_can_skip_missing_local_json_check_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            manifest = {
                "release_id": "KR-UNIT",
                "release_name": "Unit Release",
                "release_version": "0.0.1",
                "status": "release_candidate",
                "gates": [{"id": "G1", "status": "PASS", "summary": "unit gate"}],
                "evidence": [],
                "json_checks": [
                    {
                        "id": "JC1",
                        "path": "reports/key/local.json",
                        "json_path": "$.state",
                        "operator": "equals",
                        "expected": "Unknown",
                        "local_only": True,
                    }
                ],
                "non_claims": ["not product acceptance"],
            }

            report = run_key_release_gate.evaluate_release_gate(
                manifest,
                repo_root=repo,
                allow_missing_local_evidence=True,
            )

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["json_checks"][0]["status"], "SKIPPED")
            self.assertIn(
                "local json check evidence missing but allowed: reports/key/local.json",
                report["warnings"],
            )


if __name__ == "__main__":
    unittest.main()
