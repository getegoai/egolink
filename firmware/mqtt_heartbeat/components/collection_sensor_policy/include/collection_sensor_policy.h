#ifndef EGOLINK_COLLECTION_SENSOR_POLICY_H
#define EGOLINK_COLLECTION_SENSOR_POLICY_H

#include <stdbool.h>
#include <stdint.h>
#include "location_policy_core.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    egolink_location_policy_mode_t policy_mode;
    egolink_location_policy_mobility_t mobility_state;
    double current_rms_m_s2;
    uint64_t gnss_interval_ms;
    uint64_t cell_interval_ms;
    double imu_rate_hz;
    bool low_battery_latched;
    bool transition_changed;
    egolink_location_policy_mode_t transition_from;
    egolink_location_policy_mode_t transition_to;
    bool immediate_gnss_trigger;
    const char *config_id;
    const char *config_hash;
} collection_sensor_policy_snapshot_t;

typedef struct {
    bool initialized;

    /* Movement detector state (20Hz IMU samples) */
    uint64_t window_start_ms;
    uint32_t sample_count;
    double sum_dev_sq;
    double latest_rms;
    uint32_t enter_windows;
    uint32_t exit_windows;
    egolink_location_policy_mobility_t detected_mobility;
    uint64_t last_mobility_observation_ms;

    /* Sensor & environmental facts */
    egolink_location_policy_gnss_state_t gnss_state;
    uint64_t last_gnss_fix_ms;
    bool battery_percent_available;
    double battery_percent;
    egolink_location_policy_battery_state_t battery_state;
    bool sos_active;

    /* Location policy core */
    egolink_location_policy_core_t core;
    egolink_location_policy_config_t config;

    /* Cached latest decision and snapshot */
    collection_sensor_policy_snapshot_t snapshot;
} collection_sensor_policy_t;

bool collection_sensor_policy_init(collection_sensor_policy_t *policy);

/* Feed 20Hz QMI8658 accelerometer reading (in mg) */
void collection_sensor_policy_feed_imu_sample(
    collection_sensor_policy_t *policy,
    int accel_mg_x,
    int accel_mg_y,
    int accel_mg_z,
    uint64_t now_ms);

/* Feed battery telemetry (fuel gauge SOC percent) */
void collection_sensor_policy_feed_battery(
    collection_sensor_policy_t *policy,
    double soc_percent,
    bool battery_is_mock,
    bool charging,
    uint64_t now_ms);

/* Feed GNSS acquisition outcome */
void collection_sensor_policy_feed_gnss_result(
    collection_sensor_policy_t *policy,
    bool fix,
    bool no_fix,
    uint64_t now_ms);

/* Feed Cell/LTE query outcome */
void collection_sensor_policy_feed_cell_result(
    collection_sensor_policy_t *policy,
    bool observed,
    uint64_t now_ms);

/* Periodic tick to allow policy state evaluation if needed */
void collection_sensor_policy_tick(
    collection_sensor_policy_t *policy,
    uint64_t now_ms);

/* Get current snapshot */
collection_sensor_policy_snapshot_t collection_sensor_policy_snapshot(
    const collection_sensor_policy_t *policy);

/* Query and consume the immediate GNSS trigger flag */
bool collection_sensor_policy_consume_immediate_gnss(
    collection_sensor_policy_t *policy);

/* String conversion helpers */
const char *collection_sensor_policy_mode_name(egolink_location_policy_mode_t mode);
const char *collection_sensor_policy_mobility_name(egolink_location_policy_mobility_t mobility);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_COLLECTION_SENSOR_POLICY_H */
