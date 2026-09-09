"""Execute the production spool C against NOR write/erase and power-cut faults."""
import json
import unittest

from quality_tests.native_convergence import ROOT, run_c


class CollectionSpoolNativeTests(unittest.TestCase):
    def test_durable_fifo_recovery_eviction_protection_and_write_amplification(self):
        harness = (ROOT / "quality_tests/collection_spool_native_harness.c").read_text(encoding="utf-8")
        output = run_c(harness, ["collection_spool"], timeout=60)
        cases = {row["case"]: row for row in map(json.loads, output.splitlines())}
        self.assertEqual(set(cases), {
            "roundtrip", "exact_ack", "append_power_cuts", "header_ack_power_cuts",
            "durable_eviction", "eviction_power_cuts", "protected_full", "inflight_pin",
            "foreign_and_corrupt", "large_geometry", "multisource_loss",
            "concurrent_uploader_producer",
            "acked_recycle_power_cuts",
            "filtered_claim", "filtered_claim_ack_power_cuts",
            "filtered_claim_pinned_eviction",
            "excluding_claim", "excluding_claim_includes_loss",
            "excluding_claim_pinned_eviction",
        })
        self.assertLess(cases["roundtrip"]["write_bytes"] / cases["roundtrip"]["payload_bytes"], 1.3)
        self.assertEqual(cases["append_power_cuts"]["cuts"], 180)
        self.assertEqual(cases["eviction_power_cuts"]["cuts"], 105)
        self.assertEqual(cases["filtered_claim_ack_power_cuts"]["cuts"], 5)
        self.assertEqual(cases["large_geometry"]["capacity_bytes"], 860160)
        self.assertEqual(cases["concurrent_uploader_producer"]["producer_records_during_io"], 20)


if __name__ == "__main__":
    unittest.main()
