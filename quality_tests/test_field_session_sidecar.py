from __future__ import annotations

import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_ROOT = REPO_ROOT / "tools" / "field_session_sidecar"
CORE_PATH = SIDECAR_ROOT / "sidecar-core.js"
APP_PATH = SIDECAR_ROOT / "sidecar-app.js"
HTML_PATH = SIDECAR_ROOT / "index.html"
README_PATH = SIDECAR_ROOT / "README.md"


class FieldSessionSidecarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("Node.js is required for sidecar JavaScript tests")

    def run_node(self, source: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.node, "-e", textwrap.dedent(source)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_javascript_syntax(self) -> None:
        for path in (CORE_PATH, APP_PATH):
            result = subprocess.run(
                [self.node, "--check", str(path)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_produces_deterministic_single_timeline_bundle(self) -> None:
        result = self.run_node(
            r"""
            const assert = require("assert");
            const core = require("./tools/field_session_sidecar/sidecar-core.js");
            const origin = 1786924800000;
            function sample(index, type, elapsedMs) {
              return core.makeClockSample({
                sample_index: index,
                sample_type: type,
                monotonic_before_ms: 100 + elapsedMs,
                monotonic_after_ms: 100.002 + elapsedMs,
                utc_ms: origin + 100 + elapsedMs,
                time_origin_utc_ms: origin,
                visibility_state: "visible",
              });
            }
            (async () => {
              const state = core.createDraft({
                session_id: "FS-20260817T080000Z-abcdef123456",
                operator_ref: "operator-01",
                device_id: "field-phone-001",
                raw_image_capture_acknowledged: true,
              }, sample(0, "start", 0));
              assert.strictEqual(core.appendManualEvent(
                state, "START_WALKING", "route start", sample(1, "manual_event", 1000), origin
              ), true);
              const jpeg = Uint8Array.from([0xff, 0xd8, 0xff]);
              const digest = await core.sha256HexBytes(jpeg, {});
              assert.strictEqual(core.appendCameraRecord(state, {
                media_type: "image/jpeg",
                size_bytes: jpeg.length,
                sha256: digest,
                data_base64: "/9j/",
              }, sample(2, "camera_capture_return", 2000), origin), true);
              assert.strictEqual(core.appendManualEvent(
                state, "STOP", null, sample(3, "manual_event", 3000), origin
              ), true);
              assert.strictEqual(state.status, "stopped");
              assert.deepStrictEqual(state.records.map((row) => row.sequence_id), [0, 1, 2]);
              assert.deepStrictEqual(state.records.map((row) => row.source), ["manual_event", "camera", "manual_event"]);
              assert.strictEqual(state.records[1].timestamp_semantics, "capture_return");
              assert.notStrictEqual(state.records[0].clock_sample_id, state.records[1].clock_sample_id);
              assert.ok(state.records.every((row) => row.alignment_status === "estimated_unverified"));
              assert.ok(state.records.every((row) => row.timestamp_uncertainty_ns >= 1000000));

              const first = core.serializeBundle(state);
              const second = core.serializeBundle(state);
              assert.strictEqual(first, second);
              assert.ok(first.endsWith("\n"));
              assert.ok(first.startsWith('{"bundle_role"'));
              const bundle = JSON.parse(first);
              assert.strictEqual(bundle.gate_status, "unverified");
              assert.strictEqual(bundle.clock.alignment_status, "estimated_unverified");
              assert.strictEqual(bundle.clock.first_sample_id, "clock-000000");
              assert.strictEqual(bundle.clock.last_sample_id, "clock-000003");
              assert.strictEqual(bundle.media[0].path, bundle.records[1].media_path);
              assert.strictEqual(bundle.media[0].sha256, bundle.records[1].media_sha256);
              assert.strictEqual(
                await core.sha256HexBytes(new TextEncoder().encode("abc"), {}),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
              );
            })().catch((error) => {
              process.stderr.write(String(error.stack || error));
              process.exit(1);
            });
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_privacy_limits_event_whitelist_and_clock_discontinuity_fail_closed(self) -> None:
        result = self.run_node(
            r"""
            const assert = require("assert");
            const core = require("./tools/field_session_sidecar/sidecar-core.js");
            const origin = 1786924800000;
            function sample(index, type, elapsedMs, sampleOrigin = origin) {
              return core.makeClockSample({
                sample_index: index,
                sample_type: type,
                monotonic_before_ms: 10 + elapsedMs,
                monotonic_after_ms: 10 + elapsedMs,
                utc_ms: origin + 10 + elapsedMs,
                time_origin_utc_ms: sampleOrigin,
                visibility_state: "visible",
              });
            }
            const state = core.createDraft({
              session_id: "FS-20260817T080000Z-abcdef123456",
              operator_ref: "operator-01",
              device_id: "field-phone-001",
              raw_image_capture_acknowledged: false,
            }, sample(0, "start", 0));
            assert.strictEqual(state.privacy.raw_image_allowed, false);
            assert.strictEqual(state.privacy.consent_acknowledgement.acknowledged, false);
            assert.strictEqual(state.privacy.retention_acknowledgement.acknowledged, false);
            assert.strictEqual(state.privacy.control_plane_approval, false);
            assert.strictEqual(state.privacy.gate_approval, false);
            assert.strictEqual(core.appendManualEvent(
              state, "ENTER_BUILDING", null, sample(1, "manual_event", 1000), origin
            ), true);
            assert.throws(() => core.appendManualEvent(
              state, "LANDMARK", null, sample(2, "manual_event", 2000), origin
            ), /unsupported manual event/);
            assert.throws(() => core.appendCameraRecord(state, {
              media_type: "image/jpeg", size_bytes: 3, sha256: "0".repeat(64), data_base64: "/9j/"
            }, sample(2, "camera_capture_return", 2000), origin), /raw_image_allowed=false/);

            const reloadSample = sample(2, "resume_check", 2000, origin + 60000);
            core.recordRestoredRunDiscontinuity(state, reloadSample);
            assert.strictEqual(state.status, "blocked_clock_discontinuity");
            assert.strictEqual(state.clock.discontinuity.reason, "document_reloaded_or_restored");

            const allowed = core.ALLOWED_EVENTS.slice().sort();
            assert.deepStrictEqual(allowed, [
              "ENTER_BUILDING", "EXIT_BUILDING", "PUT_IN_BAG", "START_WALKING", "STOP"
            ]);

            const approved = core.createDraft({
              session_id: "FS-20260817T080000Z-012345abcdef",
              operator_ref: "operator-02",
              device_id: "field-phone-002",
              raw_image_capture_acknowledged: true,
            }, sample(0, "start", 0));
            const oversized = Buffer.alloc(core.LIMITS.max_jpeg_bytes + 1).toString("base64");
            assert.throws(() => core.appendCameraRecord(approved, {
              media_type: "image/jpeg",
              size_bytes: core.LIMITS.max_jpeg_bytes + 1,
              sha256: "0".repeat(64),
              data_base64: oversized,
            }, sample(1, "camera_capture_return", 1000), origin), /exceeds/);
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_static_page_is_offline_chinese_and_documents_adapter_boundary(self) -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        app = APP_PATH.read_text(encoding="utf-8")
        core = CORE_PATH.read_text(encoding="utf-8")
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn('lang="zh-CN"', html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn('accept="image/jpeg"', html)
        self.assertIn('capture="environment"', html)
        for event in ("START_WALKING", "PUT_IN_BAG", "ENTER_BUILDING", "EXIT_BUILDING", "STOP"):
            self.assertIn(event, html)
        for network_primitive in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon"):
            self.assertNotIn(network_primitive, app)
            self.assertNotIn(network_primitive, core)

        self.assertIn('"bundle_role": "a0_003_adapter_input"', readme)
        self.assertIn('"timestamp_semantics": "capture_return"', readme)
        self.assertIn('"timestamp_uncertainty_ns": 1000000', readme)
        self.assertIn('"first_sample_id": "clock-000000"', readme)
        self.assertIn("不能把 `estimated_unverified` 提升为 `verified`", readme)
        self.assertIn("must_not_commit_to_git", readme)
        self.assertIn("不得自动转换为", readme)
        self.assertIn("不新增", readme)


if __name__ == "__main__":
    unittest.main()
