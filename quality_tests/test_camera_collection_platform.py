import csv
import io
import re
import unittest
from pathlib import Path

from quality_tests.native_convergence import ROOT, run_c


FIRMWARE = ROOT / "firmware" / "mqtt_heartbeat"


def _check_platform_camera_disabled_build_fails_closed_without_driver_symbols():
    harness = r'''
#include "platform_camera.h"
#include <assert.h>
#include <string.h>
int main(void){
    const char *reason=0;
    assert(platform_camera_preflight(&reason)==PLATFORM_CAMERA_DISABLED);
    assert(reason&&strcmp(reason,"camera_profile_disabled")==0);
    platform_camera_capture_result_t result;
    assert(platform_camera_capture_single(0,0,&result)==PLATFORM_CAMERA_DISABLED);
    assert(!result.attempted&&!result.frame_acquired&&!result.framebuffer_returned);
    assert(strcmp(platform_camera_status_name(result.status),"disabled")==0);
    return 0;
}
'''
    run_c(
        harness,
        components=("platform_camera",),
        headers={"sdkconfig.h": "/* camera remains default-off */\n"},
    )


def _check_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame():
    source = (FIRMWARE / "components" / "platform_camera" / "platform_camera.c").read_text(encoding="utf-8")
    header = (FIRMWARE / "components" / "platform_camera" / "include" / "platform_camera.h").read_text(encoding="utf-8")
    kconfig = (FIRMWARE / "components" / "platform_camera" / "Kconfig.projbuild").read_text(encoding="utf-8")
    defaults = (FIRMWARE / "sdkconfig.camera_collection.defaults").read_text(encoding="utf-8")
    assert 'default n' in kconfig
    assert "CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED is not set" in defaults
    assert "blocked_shared_i2c_hardware_coexistence_unverified_gpio15_16_i2c0" in source
    for pin in (
        "CAMERA_PIN_D0 7", "CAMERA_PIN_D1 8", "CAMERA_PIN_D2 9", "CAMERA_PIN_D3 10",
        "CAMERA_PIN_D4 11", "CAMERA_PIN_D5 12", "CAMERA_PIN_D6 13", "CAMERA_PIN_D7 14",
        "CAMERA_PIN_SDA 15", "CAMERA_PIN_SCL 16", "CAMERA_PIN_XCLK 39",
        "CAMERA_PIN_HREF 41", "CAMERA_PIN_VSYNC 42", "CAMERA_PIN_PCLK 46",
    ):
        assert pin in source
    assert ".frame_size=FRAMESIZE_QVGA" in source
    assert ".pixel_format=PIXFORMAT_JPEG" in source
    assert ".fb_count=1" in source
    assert ".fb_location=CAMERA_FB_IN_DRAM" in source
    assert ".pin_sccb_sda=-1" in source and ".pin_sccb_scl=-1" in source
    assert ".sccb_i2c_port=CAMERA_I2C_PORT" in source
    assert "platform_i2c_bus_ensure(CAMERA_I2C_PORT,&bus)" in source
    assert source.index("platform_i2c_bus_ensure(CAMERA_I2C_PORT,&bus)") < source.index("esp_camera_init(&config)")
    assert "CONFIG_SCCB_HARDWARE_I2C_DRIVER_LEGACY=y" in defaults
    assert "CONFIG_SCCB_HARDWARE_I2C_PORT0=y" in defaults
    assert "CONFIG_SCCB_CLK_FREQ=100000" in defaults
    assert "PHOTO_MEDIA_STORE_MAX_SLOTS" in (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert "# CONFIG_SPIRAM is not set" in defaults
    assert source.count("esp_camera_fb_get()") == 1
    assert "esp_camera_fb_return(frame)" in source
    assert "esp_camera_deinit()" in source
    assert "sensor->id.PID!=OV5640_PID" in source
    assert "PLATFORM_CAMERA_UNSUPPORTED_SENSOR" in source
    assert "s_lifecycle_blocked=true" in source
    assert "mbedtls_sha256(frame->buf,frame->len" in source
    assert "low-level capture seam" in header.lower()
    assert "capture_photo_once/configure_photo_timer" in header
    assert "training_allowed=false" in header


def _check_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate():
    path = FIRMWARE / "partitions_camera_collection_16mb.csv"
    rows = []
    for row in csv.reader(io.StringIO(path.read_text(encoding="utf-8"))):
        if not row or row[0].lstrip().startswith("#"):
            continue
        name, kind, subtype, offset, size = [field.strip() for field in row[:5]]
        rows.append((name, kind, subtype, int(offset, 0), int(size, 0)))
    assert [row[0] for row in rows] == ["nvs", "phy_init", "factory", "ego_collection", "ego_media", "ego_outbox"]
    ordered = sorted(rows, key=lambda row: row[3])
    for left, right in zip(ordered, ordered[1:]):
        assert left[3] + left[4] <= right[3]
    assert max(offset + size for _, _, _, offset, size in rows) <= 16 * 1024 * 1024
    media = next(row for row in rows if row[0] == "ego_media")
    collection = next(row for row in rows if row[0] == "ego_collection")
    factory = next(row for row in rows if row[0] == "factory")
    outbox = next(row for row in rows if row[0] == "ego_outbox")
    assert factory[3:] == (0x200000, 0x300000)
    assert collection[2:] == ("0x41", 0x500000, 0x100000)
    assert media[2:] == ("0x42", 0x600000, 0x900000)
    assert outbox[2:] == ("0x40", 0xF00000, 0xC000)
    # Preserve the entire legacy app/data range. Future flashing still needs a
    # readback/decision because this layout does not itself back up old bytes.
    assert all(offset >= 0x200000 for name, _, _, offset, _ in rows if name not in {"nvs", "phy_init"})
    defaults = (FIRMWARE / "sdkconfig.camera_collection.defaults").read_text(encoding="utf-8")
    assert 'CONFIG_ESPTOOLPY_FLASHSIZE="16MB"' in defaults
    assert 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_camera_collection_16mb.csv"' in defaults
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert "#define COLLECTION_PARTITION_ADDRESS 0x500000U" in source
    assert "#define COLLECTION_PARTITION_SIZE 0x100000U" in source
    assert "#define MEDIA_PARTITION_ADDRESS 0x600000U" in source
    assert "#define MEDIA_PARTITION_SIZE 0x900000U" in source


def _check_legacy_collection_profile_and_4k_record_spool_remain_unchanged():
    legacy = (FIRMWARE / "sdkconfig.collection.defaults").read_text(encoding="utf-8")
    partition = (FIRMWARE / "partitions_collection.csv").read_text(encoding="utf-8")
    record = (FIRMWARE / "components" / "collection_record" / "include" / "collection_record.h").read_text(encoding="utf-8")
    assert 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_collection.csv"' in legacy
    assert "ego_collection, data, 0x41, 0x122000, 0xD2000" in partition
    assert "COLLECTION_FRAME_CAPACITY 4000" in record
    assert "EGOLINK_COLLECTION_CAMERA_PROFILE=y" not in legacy


def _check_runtime_delivery_is_metadata_gated_fair_and_release_safe():
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert 'PHOTO_METADATA_ACK_NVS_KEY "photo_meta_ack_v1"' in source
    assert "photo_record_metadata_acked(record.source_seq)" in source
    assert "metadata_identity>photo_metadata_ack_watermark" in source
    assert "PHOTO_ORDINARY_UPLOAD_BUDGET 8U" in source
    assert "PHOTO_FAIR_UPLOAD_INTERVAL_US 30000000LL" in source
    assert "photo_schedule_upload_retry(server_verified" in source
    assert "photo_control_capture_journal_allows_new_command(&pending_capture)" in source
    assert "photo_content_permanently_rejected" not in source
    assert "photo_append_media_terminal_status" not in source
    # The only ordinary upload release is inside the exact content-ACK branch;
    # the other release sites are local trusted-UTC retention paths.
    upload = source[source.index("static bool photo_upload_one"):source.index(
        "static void photo_schedule_upload_retry"
    )]
    assert upload.count("photo_media_release_locked(&record)") == 2
    assert upload.index("if(server_verified)") < upload.rindex(
        "photo_media_release_locked(&record)"
    )
    assert "posted.http_status_code>=200U&&posted.http_status_code<300U&&" in upload
    assert "photo_delivery_content_ack_response_matches" in upload
    assert "const bool success=" not in source


def _check_media_store_access_is_single_mutex_serialized_and_observable():
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    wrapper_names = (
        "photo_media_init_locked",
        "photo_media_stats_locked",
        "photo_media_find_locked",
        "photo_media_peek_locked",
        "photo_media_read_locked",
        "photo_media_release_locked",
        "photo_media_capture_store_locked",
    )
    wrapper_start = source.index("static photo_media_store_result_t photo_media_init_locked")
    wrapper_end = source.index("static void photo_stack_hwm_observe")
    raw_calls = tuple(re.finditer(
        r"\bphoto_media_store_(?:init|get_stats|find|peek_committed|read|release|"
        r"prepare_with_expiry|write|commit)\s*\(",
        source,
    ))
    assert raw_calls
    assert all(wrapper_start <= call.start() < wrapper_end for call in raw_calls)

    for index, name in enumerate(wrapper_names):
        start = source.index(f"{name}(", wrapper_start)
        end = (source.index(f"{wrapper_names[index + 1]}(", start)
               if index + 1 < len(wrapper_names) else wrapper_end)
        body = source[start:end]
        assert body.count("photo_media_lock()") == 1
        assert body.count("photo_media_unlock()") == 1
        wrapped_calls = tuple(re.finditer(
            r"\bphoto_media_store_(?:init|get_stats|find|peek_committed|read|release|"
            r"prepare_with_expiry|write|commit)\s*\(",
            body,
        ))
        assert wrapped_calls
        assert body.index("photo_media_lock()") < wrapped_calls[0].start()
        assert wrapped_calls[-1].end() < body.index("photo_media_unlock()")

    assert "static SemaphoreHandle_t media_store_mutex;" in source
    assert "media_store_mutex=xSemaphoreCreateMutex();" in source
    assert "allocation_failed=allocation_failed||!media_store_mutex;" in source
    assert "vSemaphoreDelete(media_store_mutex);media_store_mutex=NULL;" in source
    assert "media_stats_valid=photo_media_stats_locked(&media);" in source
    assert "outcome->store_result=photo_media_capture_store_locked" in source
    assert source.count("outcome->store_result=photo_media_find_locked") == 2
    assert source.count("photo_media_peek_locked(*scan_cursor") == 2
    assert "store=photo_media_read_locked(&record,0U,jpeg,record.payload_bytes);" in source

    for api, field in (
        ("heap_caps_get_free_size(MALLOC_CAP_INTERNAL)", "internal_free_bytes"),
        ("heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL)", "internal_min_free_bytes"),
        ("heap_caps_get_free_size(MALLOC_CAP_DMA)", "dma_free_bytes"),
        ("heap_caps_get_largest_free_block(MALLOC_CAP_DMA)", "dma_largest_free_block_bytes"),
    ):
        assert api in source
        assert f'"{field}"' in source
    assert "uxTaskGetStackHighWaterMark2(NULL)" in source
    assert "sizeof(StackType_t)" in source
    assert '"task_stack_high_watermark_bytes"' in source
    for task in ("main", "store", "imu", "modem", "upload", "wifi"):
        assert f'photo_add_stack_hwm(stack_hwm,"{task}"' in source


class CameraCollectionPlatformTests(unittest.TestCase):
    def test_platform_camera_disabled_build_fails_closed_without_driver_symbols(self):
        _check_platform_camera_disabled_build_fails_closed_without_driver_symbols()

    def test_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame(self):
        _check_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame()

    def test_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate(self):
        _check_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate()

    def test_legacy_collection_profile_and_4k_record_spool_remain_unchanged(self):
        _check_legacy_collection_profile_and_4k_record_spool_remain_unchanged()

    def test_runtime_delivery_is_metadata_gated_fair_and_release_safe(self):
        _check_runtime_delivery_is_metadata_gated_fair_and_release_safe()

    def test_media_store_access_is_single_mutex_serialized_and_observable(self):
        _check_media_store_access_is_single_mutex_serialized_and_observable()
