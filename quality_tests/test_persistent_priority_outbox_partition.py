"""Static/spec checks for the OUTBOX-010C build-only raw partition adapter.

These checks and an ESP-IDF compile do not execute partition I/O and are not
power-loss, flash-encryption, endurance, erase-remanence, or hardware evidence.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "components"
    / "persistent_priority_outbox_partition"
)
HEADER = COMPONENT / "include" / "persistent_priority_outbox_partition.h"
SOURCE = COMPONENT / "persistent_priority_outbox_partition.c"
PARTITIONS = ROOT / "firmware" / "mqtt_heartbeat" / "partitions_outbox.csv"
PROFILE = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "sdkconfig.outbox_partition.defaults"
)
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"


class PersistentPriorityOutboxPartitionStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.partitions = PARTITIONS.read_text(encoding="utf-8")
        cls.profile = PROFILE.read_text(encoding="utf-8")
        cls.app_main = APP_MAIN.read_text(encoding="utf-8")

    def test_geometry_matches_two_exact_core_images(self):
        self.assertIn("EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES 22240U", (
            ROOT
            / "firmware"
            / "mqtt_heartbeat"
            / "components"
            / "persistent_priority_outbox"
            / "include"
            / "persistent_priority_outbox.h"
        ).read_text(encoding="utf-8"))
        self.assertIn("SLOT_STRIDE_BYTES UINT32_C(24576)", self.header)
        self.assertIn("PARTITION_BYTES UINT32_C(49152)", self.header)
        self.assertIn('PARTITION_LABEL "ego_outbox"', self.header)
        self.assertIn("PARTITION_SUBTYPE UINT8_C(0x40)", self.header)
        self.assertIn("EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES <=", self.source)
        self.assertIn(
            "partition->erase_size != EGOLINK_OUTBOX_PARTITION_ERASE_BYTES",
            self.source,
        )
        self.assertIn("partition->type != ESP_PARTITION_TYPE_DATA", self.source)
        self.assertIn("strcmp(partition->label, EGOLINK_OUTBOX_PARTITION_LABEL)", self.source)
        self.assertRegex(self.partitions, r"ego_outbox,\s+data,\s+0x40,\s+0x110000,\s+0xC000")

    def test_write_erases_only_target_slot_then_writes_and_reads_back(self):
        erase_at = self.source.index("esp_partition_erase_range")
        write_at = self.source.index("esp_partition_write")
        verify_at = self.source.index("while (verified < source_length)")
        self.assertLess(erase_at, write_at)
        self.assertLess(write_at, verify_at)
        self.assertIn("EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES", self.source[erase_at:write_at])
        self.assertIn("memcmp(verification, &expected[verified], chunk)", self.source)
        self.assertIn("uint8_t verification[EGOLINK_OUTBOX_PARTITION_VERIFY_CHUNK_BYTES]", self.source)
        self.assertEqual(2, self.source.count("secure_zero(verification, sizeof(verification))"))
        self.assertIn("volatile uint8_t *cursor", self.source)
        self.assertNotIn("memset(verification", self.source)
        self.assertIn("PARTITION_VERIFY_CHUNK_BYTES > 0U", self.source)
        self.assertEqual(1, self.source.count("esp_partition_erase_range("))

    def test_erased_slot_is_not_found_and_torn_slot_is_left_for_core_validation(self):
        self.assertIn("bytes[index] != UINT8_MAX", self.source)
        self.assertIn("return EGOLINK_OUTBOX_STORAGE_NOT_FOUND", self.source)
        self.assertNotIn("esp_partition_erase_range", self.source[self.source.index("egolink_outbox_partition_init"):])
        self.assertIn("read-only discovery", self.header.lower())

    def test_adapter_is_single_owner_synchronous_and_dormant(self):
        normalized = self.header.lower()
        self.assertIn("one owner task", normalized)
        self.assertIn("no internal task", normalized)
        self.assertNotIn("egolink_outbox_partition_init", self.app_main)
        self.assertNotIn("persistent_priority_outbox_partition", self.app_main)
        self.assertNotIn("ESP_LOG", self.source)

    def test_ram_only_write_amplification_metrics_are_metadata_and_saturating(self):
        normalized = self.header.lower()
        for field in (
            "slot_erase_attempts",
            "slot_erase_successes",
            "write_api_success_bytes",
            "readback_failures",
        ):
            self.assertIn(field, self.header)
        self.assertIn("ram-only, saturating write-amplification counters", normalized)
        self.assertIn("contain no payload bytes", normalized)
        self.assertIn("not persistent lifetime/endurance accounting", normalized)
        self.assertIn("static void saturating_increment", self.source)
        self.assertIn("static void saturating_add", self.source)
        self.assertIn("UINT64_MAX - *value", self.source)
        self.assertIn("egolink_outbox_partition_get_metrics", self.source)
        self.assertIn("*metrics = adapter->metrics", self.source)

    def test_partition_profile_is_additive_not_default(self):
        default_profile = (
            ROOT / "firmware" / "mqtt_heartbeat" / "sdkconfig.defaults"
        ).read_text(encoding="utf-8")
        outbox_row = next(
            line for line in self.partitions.splitlines()
            if line.strip().startswith("ego_outbox,")
        )
        self.assertIn("CONFIG_PARTITION_TABLE_CUSTOM=y", self.profile)
        self.assertIn('CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_outbox.csv"', self.profile)
        self.assertNotIn("CONFIG_PARTITION_TABLE_CUSTOM=y", default_profile)
        self.assertTrue(outbox_row.rstrip().endswith(","))
        self.assertNotIn("encrypted", outbox_row.lower())
        self.assertNotIn("FLASH_ENC", self.profile)

    def test_source_has_strict_local_build_flags_and_no_dynamic_allocation(self):
        cmake = (COMPONENT / "CMakeLists.txt").read_text(encoding="utf-8")
        for flag in ("-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow"):
            self.assertIn(flag, cmake)
        self.assertIsNone(re.search(r"\b(?:malloc|calloc|realloc|free)\s*\(", self.source))

    def test_nonclaims_are_explicit(self):
        normalized = self.header.lower()
        self.assertIn("a torn target is\n * never reported as committed", normalized)
        self.assertIn("after at least one\n * valid mirror exists", normalized)
        self.assertIn("first-ever empty-store initialization", normalized)
        self.assertIn("one torn slot and one erased slot", normalized)
        self.assertIn("fails closed with storage corruption", normalized)
        self.assertIn("explicit provisioning/format recovery", normalized)
        self.assertIn("no universal reset-", normalized)
        self.assertIn("caller-owned", normalized)
        self.assertIn("never erases", normalized)
        self.assertIn("does not enable or prove at-rest confidentiality", normalized)
        self.assertIn("flash encryption", normalized)
        self.assertIn("erase remanence", normalized)
        self.assertIn("every durable\n * core mutation erases one six-sector 24 kib slot", normalized)
        self.assertIn("not an endurance-qualified backend", normalized)


if __name__ == "__main__":
    unittest.main()
