#ifndef EGOLINK_PLATFORM_IMU_H
#define EGOLINK_PLATFORM_IMU_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PLATFORM_IMU_RING_CAPACITY 32

typedef enum {
    PLATFORM_IMU_BACKEND_MOCK = 0,
    PLATFORM_IMU_BACKEND_QMI8658 = 1,
} platform_imu_backend_t;

typedef struct {
    uint32_t seq;
    int64_t uptime_ms;
    int accel_mg_x;
    int accel_mg_y;
    int accel_mg_z;
    int gyro_mdps_x;
    int gyro_mdps_y;
    int gyro_mdps_z;
    bool sample_is_mock;
    const char *source;
} platform_imu_sample_t;

typedef struct {
    bool initialized;
    platform_imu_backend_t backend;
    bool hardware_present;
    bool driver_enabled;
    bool data_is_mock;
    const char *source;
    const char *backend_name;
    const char *backend_status;
    const char *sensor_model;
    uint32_t sample_interval_ms;
    int last_error;
    size_t ring_capacity;
    size_t ring_count;
    uint32_t dropped_samples;
    platform_imu_sample_t latest;
} platform_imu_snapshot_t;

bool platform_imu_init(void);
bool platform_imu_sample(void);
bool platform_imu_sample_mock(void);
bool platform_imu_push_sample(const platform_imu_sample_t *sample);
void platform_imu_get_snapshot(platform_imu_snapshot_t *snapshot);
size_t platform_imu_read_recent(platform_imu_sample_t *samples, size_t max_samples);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_PLATFORM_IMU_H */
