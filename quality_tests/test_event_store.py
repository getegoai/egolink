from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pc_simulator import event_store


class EventStoreTests(unittest.TestCase):
    def test_append_and_load_recent_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            event_store.append_jsonl(path, {"seq": 1, "event_type": "heartbeat"})
            event_store.append_jsonl(path, {"seq": 2, "event_type": "sos_pressed"})

            rows = event_store.load_recent(path, limit=1)

        self.assertEqual(rows, [{"seq": 2, "event_type": "sos_pressed"}])


if __name__ == "__main__":
    unittest.main()
