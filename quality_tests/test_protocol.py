from __future__ import annotations

import unittest

from pc_simulator import protocol


class ProtocolTests(unittest.TestCase):
    def test_status_message_has_required_fields(self) -> None:
        msg = protocol.status_message(
            "ego-link-001",
            "2026-06-19T00:00:00Z",
            1,
            battery=87,
            link_type="mock_4g_over_wifi",
            guard_mode="child_safety",
            queue_size=0,
        )

        self.assertEqual(msg["message_type"], "status")
        self.assertEqual(msg["protocol_version"], protocol.PROTOCOL_VERSION)

    def test_event_message_requires_priority(self) -> None:
        msg = protocol.event_message(
            "ego-link-001",
            "2026-06-19T00:00:01Z",
            2,
            "sos_pressed",
            "critical",
            source="unit_test",
        )

        self.assertEqual(msg["message_type"], "event")
        self.assertEqual(msg["priority"], "critical")

    def test_missing_status_field_fails(self) -> None:
        with self.assertRaises(ValueError):
            protocol.status_message("ego-link-001", "now", 1, battery=80)


if __name__ == "__main__":
    unittest.main()
