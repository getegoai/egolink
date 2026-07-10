from __future__ import annotations

from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest

from scripts import validate_location_memory_gate
from server import message_hub


class LocationMemoryGateTests(unittest.TestCase):
    def test_gate_seeds_synthetic_sequence_and_preserves_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                report = validate_location_memory_gate.run_gate(
                    hub_url=f"http://127.0.0.1:{server.server_port}",
                    device_id="ego-link-r0-location-memory-gate",
                    test_run_id="location-memory-gate-unit",
                    output_dir=Path(tmp) / "report",
                    token=None,
                    seed_synthetic=True,
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["latest_location"]["fix"], False)
            self.assertEqual(report["location_belief"]["state"], "Predicted")
            self.assertEqual(report["location_memory"]["state"], "Fine")
            self.assertTrue(report["location_memory"]["last_known_location_present"])
            self.assertNotIn("last_known_location", report["location_memory"])
            self.assertTrue((Path(tmp) / "report" / "location_memory_gate_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "location_memory_gate_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
