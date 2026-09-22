"""Execute the shipped renderer and controller in Node with a minimal DOM."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HARNESS = r"""
import fs from 'node:fs';
import vm from 'node:vm';
const root = process.argv[1];
const moduleText = fs.readFileSync(root + '/server/web/scripts/ego_state.js', 'utf8');
const { renderEgoState } = await import('data:text/javascript;base64,' + Buffer.from(moduleText).toString('base64'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const dom = new Proxy({}, {get(target, key) {
  if (!(key in target)) target[key] = {textContent: '', innerHTML: '', className: '', style: {}, attrs: {},
    setAttribute(k, v) {this.attrs[k] = v;}, removeAttribute(k) {delete this.attrs[k];}};
  return target[key];
}});
let app;
if (input.summary) {
  const controller = fs.readFileSync(root + '/server/web/scripts/main.js', 'utf8').replace(/^import .*;\r?$/gm, '');
  const context = {renderEgoState, document: {addEventListener() {}}, console};
  vm.createContext(context);
  vm.runInContext(controller + '\nglobalThis.TestApp = DevBenchApp;', context);
  app = new context.TestApp();
  app.dom = dom;
}
const snapshots = [];
for (const item of input.cases) {
  if (app) app.renderCollectionSummary(item);
  else renderEgoState(dom, item.view, item.diagnostic);
  snapshots.push(JSON.parse(JSON.stringify(dom)));
}
process.stdout.write(JSON.stringify(snapshots));
"""


def sample_view() -> dict:
    return {
        "contract_version": "egolink.ego_state_view.v0.1",
        "state": {
            "contract_version": "egolink.ego_state_estimation.v0.1", "estimation_id": "est-1",
            "device_id": "ego-test", "boot_count": 2, "timestamp_monotonic_ns": 1_000_000_000,
            "timestamp_utc": None, "spatial_mobility": "pedestrian_walking", "posture_anomaly": "normal",
            "device_wear_state": "wearable_or_bag", "confidence": 0.83, "is_mock": False,
            "reason_codes": ["imu_motion"], "primary_evidence_digest": "a" * 64, "window_duration_ms": 2000,
        },
        "provenance": {"sequence_id": 3, "identity_source": "device"},
        "receipt": {"server_received_at": "2026-09-22T03:00:00Z"},
        "evidence_summary": {"motion_rms_m_s2": 2.3, "battery_soc_percent": 80},
    }


@unittest.skipUnless(NODE, "Node is required to execute the browser rendering logic")
class EgoStateWebRenderingTests(unittest.TestCase):
    def render(self, cases: list[dict], *, summary: bool = False) -> list[dict]:
        result = subprocess.run([NODE, "--input-type=module", "-e", HARNESS, str(ROOT)],
                                input=json.dumps({"cases": cases, "summary": summary}), text=True,
                                encoding="utf-8", capture_output=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_missing_or_invalid_view_never_displays_normal_and_clears_prior_data(self) -> None:
        good = sample_view()
        invalid = deepcopy(good)
        invalid["state"]["posture_anomaly"] = "fall_suspected"
        snapshots = self.render([{"view": good}, {"view": None}, {"view": invalid}, {"view": good["state"]}])
        self.assertIn("NORMAL", snapshots[0]["egoPostureBadge"]["textContent"])
        self.assertEqual(snapshots[0]["egoDigestHex"]["attrs"]["data-full-digest"], "a" * 64)
        for dom in snapshots[1:]:
            for key in ("egoSpatialMobilityBadge", "egoPostureBadge", "egoWearBadge"):
                self.assertEqual(dom[key]["textContent"], "UNKNOWN")
                self.assertNotIn("badge-ok", dom[key]["className"])
            self.assertEqual(dom["egoDigestHex"]["attrs"], {})
            self.assertEqual(dom["egoImuRms"]["textContent"], "—")
            self.assertEqual(dom["egoConfidenceVal"]["textContent"], "—")

    def test_all_contract_enums_are_rendered_and_score_is_not_accuracy(self) -> None:
        schema = json.loads((ROOT / "shared/contracts/ego_state_estimation_v0.schema.json").read_text("utf-8"))
        keys = {"spatial_mobility": "egoSpatialMobilityBadge", "posture_anomaly": "egoPostureBadge", "device_wear_state": "egoWearBadge"}
        cases, expected = [], []
        for field, dom_key in keys.items():
            for value in schema["properties"][field]["enum"]:
                view = sample_view()
                view["state"][field] = value
                cases.append({"view": view})
                expected.append((dom_key, value))
        snapshots = self.render(cases)
        for dom, (key, value) in zip(snapshots, expected):
            if value == "unknown":
                self.assertEqual(dom[key]["textContent"], "UNKNOWN")
            else:
                self.assertNotEqual(dom[key]["textContent"], "UNKNOWN")
            self.assertIn("0.83 / 1", dom["egoConfidenceVal"]["textContent"])
            self.assertNotIn("%", dom["egoConfidenceVal"]["textContent"])
            self.assertIn("源 UTC 未知", dom["egoStateTime"]["textContent"])
            self.assertIn("历史估计", dom["egoStateTime"]["textContent"])
            self.assertIn("不代表当前健康", dom["egoStateTime"]["textContent"])
            self.assertIn("服务器收到: 2026-09-22T03:00:00Z（不是采样时间）", dom["egoStateTime"]["textContent"])

    def test_mock_legacy_and_quarantine_diagnostics_are_visible_and_reasons_escaped(self) -> None:
        view = sample_view()
        view["state"]["is_mock"] = True
        view["state"]["reason_codes"] = ['<img src=x onerror="bad()">']
        view["provenance"]["identity_source"] = "legacy_derived_from_collection_envelope"
        dom = self.render([{"view": view, "diagnostic": {"status": "invalid", "reason_code": "ego_state_invalid_enum"}}])[0]
        self.assertIn("MOCK", dom["egoStateTime"]["textContent"])
        self.assertIn("旧帧", dom["egoStateTime"]["textContent"])
        self.assertIn("非实时确认", dom["egoStateTime"]["textContent"])
        self.assertIn("ego_state_invalid_enum", dom["egoStateTime"]["textContent"])
        self.assertNotIn("<img", dom["egoReasonCodes"]["innerHTML"])
        self.assertIn("&lt;img", dom["egoReasonCodes"]["innerHTML"])

    def test_actual_controller_does_not_bypass_projection_with_raw_payload(self) -> None:
        raw = sample_view()["state"]
        raw["ready"] = True
        source = {"source": "device", "latest": {"envelope": {"payload": {"ego_state": raw}}, "preview": {"ego_state_projection": {"status": "invalid", "reason_code": "ego_state_invalid_enum"}}}}
        missing, good = self.render([
            {"latest_ego_state": None, "sources": [source]},
            {"latest_ego_state": sample_view(), "sources": [source]},
        ], summary=True)
        self.assertEqual(missing["egoPostureBadge"]["textContent"], "UNKNOWN")
        self.assertIn("NORMAL", good["egoPostureBadge"]["textContent"])
        self.assertIn("ego_state_invalid_enum", good["egoStateTime"]["textContent"])

    def test_initial_html_does_not_claim_normal_or_tamperproof(self) -> None:
        html = (ROOT / "server/web/index.html").read_text("utf-8")
        self.assertIn('id="egoPostureBadge" class="badge badge-warn">UNKNOWN', html)
        self.assertNotIn("SHA-256 不可篡改", html)
        self.assertIn("规则分数（非准确率）", html)

    def test_split_health_absence_preserves_history_and_quarantine_notice(self) -> None:
        health = {"source": "device", "latest": {"envelope": {"payload": {"heap_free": 12345}},
                  "preview": {"ego_state_projection": {"status": "absent", "reason_code": "ego_state_missing"}}}}
        cases = [{"sources": [health], "latest_ego_state": sample_view()}]
        for status in ("invalid", "unavailable"):
            cases.append({"sources": [health], "latest_ego_state": sample_view(),
                          "latest_ego_state_projection": {"status": status, "reason_code": "state_packet_diagnostic"}})
        snapshots = self.render(cases, summary=True)
        for dom in snapshots:
            self.assertIn("历史估计", dom["egoStateTime"]["textContent"])
            self.assertNotIn("ego_state_missing", dom["egoStateTime"]["textContent"])
            self.assertIn("NORMAL", dom["egoPostureBadge"]["textContent"])
        for dom, status in zip(snapshots[1:], ("invalid", "unavailable")):
            self.assertIn(status, dom["egoStateTime"]["textContent"])
            self.assertIn("state_packet_diagnostic", dom["egoStateTime"]["textContent"])
