#include "platform_imu.h"

#include <inttypes.h>

#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "egolink_platform_imu";
static const char *PLATFORM_IMU_SOURCE_MOCK = "mock_stationary";

static bool s_initialized;
static platform_imu_sample_t s_ring[PLATFORM_IMU_RING_CAPACITY];
static size_t s_write_index;
static size_t s_count;
static uint32_t s_next_seq;
static uint32_t s_dropped_samples;
static platform_imu_sample_t s_latest;

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static const char *safe_source(const char *source)
{
    return source ? source : "unknown";
}

bool platform_imu_init(void)
{
    if (!s_initialized) {
        s_write_index = 0;
        s_count = 0;
        s_next_seq = 0;
        s_dropped_samples = 0;
        s_latest = (platform_imu_sample_t){
            .seq = 0,
            .uptime_ms = uptime_ms(),
            .accel_mg_x = 0,
            .accel_mg_y = 0,
            .accel_mg_z = 1000,
            .gyro_mdps_x = 0,
            .gyro_mdps_y = 0,
            .gyro_mdps_z = 0,
            .sample_is_mock = true,
            .source = PLATFORM_IMU_SOURCE_MOCK,
        };
        s_initialized = true;
        ESP_LOGI(
            TAG,
            "PLATFORM_IMU_INIT source=%s ring_capacity=%d hardware_present=false driver_enabled=false mock=true",
            PLATFORM_IMU_SOURCE_MOCK,
            PLATFORM_IMU_RING_CAPACITY);
    }
    return true;
}

bool platform_imu_push_sample(const platform_imu_sample_t *sample)
{
    if (!sample) {
        return false;
    }
    if (!s_initialized) {
        platform_imu_init();
    }

    platform_imu_sample_t stored = *sample;
    if (stored.seq == 0) {
        stored.seq = ++s_next_seq;
    } else if (stored.seq > s_next_seq) {
        s_next_seq = stored.seq;
    }
    if (stored.uptime_ms <= 0) {
        stored.uptime_ms = uptime_ms();
    }
    if (!stored.source) {
        stored.source = "unspecified";
    }

    if (s_count == PLATFORM_IMU_RING_CAPACITY) {
        s_dropped_samples++;
    } else {
        s_count++;
    }

    s_ring[s_write_index] = stored;
    s_write_index = (s_write_index + 1) % PLATFORM_IMU_RING_CAPACITY;
    s_latest = stored;

    ESP_LOGI(
        TAG,
        "PLATFORM_IMU_SAMPLE seq=%" PRIu32 " source=%s mock=%s ring_count=%u dropped=%" PRIu32
        " accel_mg=%d,%d,%d gyro_mdps=%d,%d,%d",
        stored.seq,
        safe_source(stored.source),
        stored.sample_is_mock ? "true" : "false",
        (unsigned)s_count,
        s_dropped_samples,
        stored.accel_mg_x,
        stored.accel_mg_y,
        stored.accel_mg_z,
        stored.gyro_mdps_x,
        stored.gyro_mdps_y,
        stored.gyro_mdps_z);
    return true;
}

bool platform_imu_sample_mock(void)
{
    if (!s_initialized) {
        platform_imu_init();
    }
    uint32_t next_seq = s_next_seq + 1;
    int wobble_mg = (int)(next_seq % 5) - 2;
    platform_imu_sample_t sample = {
        .seq = 0,
        .uptime_ms = uptime_ms(),
        .accel_mg_x = wobble_mg,
        .accel_mg_y = -wobble_mg,
        .accel_mg_z = 1000 + wobble_mg,
        .gyro_mdps_x = 0,
        .gyro_mdps_y = 0,
        .gyro_mdps_z = 0,
        .sample_is_mock = true,
        .source = PLATFORM_IMU_SOURCE_MOCK,
    };
    return platform_imu_push_sample(&sample);
}

void platform_imu_get_snapshot(platform_imu_snapshot_t *snapshot)
{
    if (!snapshot) {
        return;
    }
    if (!s_initialized) {
        platform_imu_init();
    }
    *snapshot = (platform_imu_snapshot_t){
        .initialized = s_initialized,
        .hardware_present = false,
        .driver_enabled = false,
        .data_is_mock = true,
        .source = PLATFORM_IMU_SOURCE_MOCK,
        .ring_capacity = PLATFORM_IMU_RING_CAPACITY,
        .ring_count = s_count,
        .dropped_samples = s_dropped_samples,
        .latest = s_latest,
    };
}

size_t platform_imu_read_recent(platform_imu_sample_t *samples, size_t max_samples)
{
    if (!samples || max_samples == 0) {
        return 0;
    }
    if (!s_initialized) {
        platform_imu_init();
    }

    size_t read_count = s_count < max_samples ? s_count : max_samples;
    size_t oldest_index = (s_write_index + PLATFORM_IMU_RING_CAPACITY - s_count) % PLATFORM_IMU_RING_CAPACITY;
    size_t start_offset = s_count - read_count;

    for (size_t i = 0; i < read_count; ++i) {
        size_t ring_index = (oldest_index + start_offset + i) % PLATFORM_IMU_RING_CAPACITY;
        samples[i] = s_ring[ring_index];
    }
    return read_count;
}
