"""Unit and integration tests for EgoLink DevBench Web routes."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from server import collection_page, message_hub


class DevBenchWebRoutesTests(unittest.TestCase):
    TEST_TOKEN = "test-token-guardian-secret-16b"

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.tmp_dir.name) / "hub.db"
        cls.store = message_hub.MessageHubStore(db_path)
        from server.guardian_device_authorization import GuardianDeviceAuthorizer, token_sha256
        guardian = GuardianDeviceAuthorizer({
            "contract_version": "egolink.guardian_device_bindings.v0.1",
            "bindings": [{
                "guardian_id": "test-guardian",
                "token_sha256": token_sha256(cls.TEST_TOKEN),
                "device_ids": ["ego-link-001"]
            }]
        })
        handler_cls = message_hub.make_handler(cls.store, token=cls.TEST_TOKEN, guardian_authorizer=guardian)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.tmp_dir.cleanup()

    def _get(self, path: str, token: str | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            body = resp.read()
            return status, resp_headers, body
        finally:
            conn.close()

    def test_dev_bench_index_served_at_dev(self) -> None:
        status, headers, body = self._get("/dev")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        self.assertEqual(headers.get("cache-control"), "no-cache")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertIn("default-src 'self'", headers.get("content-security-policy", ""))
        text = body.decode("utf-8")
        self.assertIn("EgoLink DevBench", text)
        self.assertIn("/dev/static/styles/dev_bench.css", text)
        self.assertIn("/dev/static/scripts/main.js", text)

    def test_dev_bench_index_served_at_dev_slash(self) -> None:
        status, headers, body = self._get("/dev/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        text = body.decode("utf-8")
        self.assertIn("EgoLink DevBench", text)

    def test_dev_bench_css_static_served(self) -> None:
        status, headers, body = self._get("/dev/static/styles/dev_bench.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        self.assertEqual(headers.get("cache-control"), "no-cache")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        text = body.decode("utf-8")
        self.assertIn(".devbench-header", text)

    def test_dev_bench_scripts_served(self) -> None:
        for script in ["main.js", "api.js", "state.js", "charts.js", "map.js", "imu3d.js", "ego_state.js"]:
            with self.subTest(script=script):
                status, headers, body = self._get(f"/dev/static/scripts/{script}")
                self.assertEqual(status, 200)
                self.assertIn("application/javascript", headers.get("content-type", ""))
                self.assertEqual(headers.get("x-content-type-options"), "nosniff")
                self.assertTrue(len(body) > 0)

    def test_dev_bench_static_path_traversal_denied(self) -> None:
        traversal_attempts = [
            "/dev/static/../message_hub.py",
            "/dev/static/..%2fmessage_hub.py",
            "/dev/static/../../package.json",
            "/dev/static/styles/../../message_hub.py",
        ]
        for path in traversal_attempts:
            with self.subTest(path=path):
                status, _, body = self._get(path)
                self.assertEqual(status, 404)

    def test_dev_bench_nonexistent_file_returns_404(self) -> None:
        status, _, body = self._get("/dev/static/nonexistent.xyz")
        self.assertEqual(status, 404)

    def test_dashboard_header_contains_dev_bench_link(self) -> None:
        html = message_hub.render_dashboard()
        self.assertIn('href="/dev"', html)
        self.assertIn("DevBench", html)

    def test_collection_page_nav_contains_dev_bench_link(self) -> None:
        self.assertIn('href="/dev"', collection_page.COLLECTION_HTML)
        self.assertIn("开发者工作台", collection_page.COLLECTION_HTML)

    def test_map_config_endpoint_returns_json(self) -> None:
        import json
        status, headers, body = self._get("/api/v1/map/config")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertIn("configured", data)
        self.assertIn("amap_key", data)

    def test_field_verified_trajectory_endpoint_returns_json(self) -> None:
        import json
        status, headers, body = self._get("/api/v1/trajectories/field-verified")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertIn("points", data)
        self.assertEqual(data.get("track_id"), "FW007-HW-20260815-001")

    def test_device_trajectory_endpoint_returns_json(self) -> None:
        import json
        status, headers, body = self._get("/api/v1/devices/ego-link-001/trajectory")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("device_id"), "ego-link-001")
        self.assertIn("points", data)

    def test_latest_records_endpoint_returns_json(self) -> None:
        import json
        status, headers, body = self._get(
            "/api/v1/devices/ego-link-001/collection/latest-records?source=imu&limit=5",
            token=self.TEST_TOKEN
        )
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("device_id"), "ego-link-001")
        self.assertEqual(data.get("source"), "imu")
        self.assertIsInstance(data.get("records"), list)

    def test_latest_records_incremental_filtering(self) -> None:
        import json
        # Ingest two dummy records via raw SQL for isolation
        with self.store.connection() as db:
            db.execute(
                """INSERT INTO collection_records(
                    device_id, observation_id, raw_frame_id, payload_sha256,
                    source, stream_id, sequence_id, boot_count, clock_domain,
                    event_monotonic_ns, fw_version, config_id, acquisition_status,
                    parse_status, sample_count, frame_bytes, received_at,
                    persisted_at, envelope_json, preview_json
                ) VALUES(
                    'ego-link-001', 'test-obs-1', 1, 'hash1',
                    'imu', 'imu', 1, 1, 'clk-1',
                    1000000, 'test-fw', 'test-cfg', 'ok',
                    'ok', 1, 64, '2026-09-18T12:00:00Z',
                    '2026-09-18T12:00:00Z', '{"source":"imu"}', '{"status":"ok"}'
                )"""
            )
            rec_id_1 = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            db.execute(
                """INSERT INTO collection_records(
                    device_id, observation_id, raw_frame_id, payload_sha256,
                    source, stream_id, sequence_id, boot_count, clock_domain,
                    event_monotonic_ns, fw_version, config_id, acquisition_status,
                    parse_status, sample_count, frame_bytes, received_at,
                    persisted_at, envelope_json, preview_json
                ) VALUES(
                    'ego-link-001', 'test-obs-2', 1, 'hash2',
                    'imu', 'imu', 2, 1, 'clk-1',
                    2000000, 'test-fw', 'test-cfg', 'ok',
                    'ok', 1, 64, '2026-09-18T12:00:01Z',
                    '2026-09-18T12:00:01Z', '{"source":"imu"}', '{"status":"ok"}'
                )"""
            )
            rec_id_2 = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Query all records
        status, _, body = self._get(
            "/api/v1/devices/ego-link-001/collection/latest-records?source=imu&limit=10",
            token=self.TEST_TOKEN
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertGreaterEqual(data["count"], 2)

        # Query with since_id = rec_id_1
        status, _, body = self._get(
            f"/api/v1/devices/ego-link-001/collection/latest-records?source=imu&since_id={rec_id_1}&limit=10",
            token=self.TEST_TOKEN
        )
        self.assertEqual(status, 200)
        data_since = json.loads(body.decode("utf-8"))
        self.assertEqual(data_since["count"], 1)
        self.assertEqual(data_since["records"][0]["row_id"], rec_id_2)
        self.assertEqual(data_since["latest_id"], rec_id_2)

