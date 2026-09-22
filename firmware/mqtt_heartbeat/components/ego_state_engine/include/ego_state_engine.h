#ifndef EGO_STATE_ENGINE_H
#define EGO_STATE_ENGINE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGO_STATE_MAX_IMU_SAMPLES 200
#define EGO_STATE_DIGEST_HEX_LEN 65
#define EGO_STATE_REASON_CODE_MAX_LEN 48
#define EGO_STATE_MAX_REASON_CODES 8

/* Engineering freshness bounds, not product accuracy or detection guarantees. */
#define EGO_STATE_IMU_MAX_AGE_NS INT64_C(1000000000)
#define EGO_STATE_SOURCE_MAX_AGE_NS INT64_C(30000000000)
#define EGO_STATE_MAX_WINDOW_MS 10000U

#define EGO_STATE_ESTIMATION_CONTRACT_VERSION "egolink.ego_state_estimation.v0.1"
#define EGO_STATE_EVIDENCE_CONTRACT_VERSION   "egolink.ego_state_evidence_chain.v0.1"
#define EGO_STATE_REPORT_CONTRACT_VERSION     "egolink.ego_state_report.v0.1"

typedef enum {
    EGO_SPATIAL_MOBILITY_UNKNOWN = 0,
    EGO_SPATIAL_MOBILITY_STATIONARY,
    EGO_SPATIAL_MOBILITY_PEDESTRIAN_WALKING,
    EGO_SPATIAL_MOBILITY_RUNNING,
    EGO_SPATIAL_MOBILITY_IN_VEHICLE,
    EGO_SPATIAL_MOBILITY_INDOOR_WEAK_GNSS,
} ego_spatial_mobility_t;

typedef enum {
    EGO_POSTURE_ANOMALY_UNKNOWN = 0,
    EGO_POSTURE_ANOMALY_NORMAL,
    EGO_POSTURE_ANOMALY_ABNORMAL_SHOCK,
    EGO_POSTURE_ANOMALY_SUSPECTED_FALL,
    EGO_POSTURE_ANOMALY_PROLONGED_IMMOBILITY,
} ego_posture_anomaly_t;

typedef enum {
    EGO_DEVICE_WEAR_UNKNOWN = 0,
    EGO_DEVICE_WEAR_TABLETOP_RESTING,
    EGO_DEVICE_WEAR_HANDHELD,
    EGO_DEVICE_WEAR_WEARABLE_OR_BAG,
    EGO_DEVICE_WEAR_CHARGING_DOCKED,
} ego_device_wear_state_t;

typedef enum {
    EGO_NETWORK_OFFLINE = 0,
    EGO_NETWORK_WIFI,
    EGO_NETWORK_LTE,
    EGO_NETWORK_MULTI,
} ego_network_type_t;

typedef struct {
    float ax_m_s2;
    float ay_m_s2;
    float az_m_s2;
    float gx_dps;
    float gy_dps;
    float gz_dps;
    int64_t timestamp_ns;
    bool is_mock;
} ego_imu_raw_sample_t;

typedef struct {
    uint32_t sample_count;
    float sample_rate_hz;
    float motion_rms_m_s2;
    float peak_accel_m_s2;
    float gyro_variance_dps2;
    bool is_mock;
    int64_t latest_sample_ns;
    int64_t latest_shock_ns;
    bool valid; /* Fresh, real, sufficient samples at this evaluation time. */
} ego_imu_features_t;

typedef struct {
    bool fix_valid;
    double latitude_deg;
    double longitude_deg;
    float hdop;
    float ground_speed_m_s;
    uint16_t satellites_in_use;
    float course_over_ground_deg;
    int64_t last_update_ns;
    bool valid;
    bool is_mock;
    bool future_rejected;
} ego_location_snapshot_t;

typedef struct {
    ego_network_type_t network_type;
    float lte_rsrp_dbm;
    char lte_cell_id[32];
    uint16_t wifi_ap_count;
    char wifi_fingerprint_hash[EGO_STATE_DIGEST_HEX_LEN];
    int64_t last_update_ns;
    bool valid;
    bool is_mock;
    bool future_rejected;
} ego_network_snapshot_t;

typedef struct {
    float battery_soc_percent;
    int32_t battery_voltage_mv;
    bool is_charging;
    bool charging_valid;
    bool valid;
    int64_t last_update_ns;
    bool is_mock;
    bool future_rejected;
} ego_power_snapshot_t;

typedef struct {
    char source_driver_backend[48];
    char firmware_version[48];
    char firmware_elf_sha256[EGO_STATE_DIGEST_HEX_LEN];
} ego_provenance_info_t;

typedef struct {
    char evidence_id[48];
    char evidence_digest[EGO_STATE_DIGEST_HEX_LEN];
    char device_id[32];
    uint32_t boot_count;
    int64_t timestamp_monotonic_ns;
    uint32_t window_duration_ms;
    ego_imu_features_t imu_evidence;
    ego_location_snapshot_t location_evidence;
    ego_network_snapshot_t network_evidence;
    ego_power_snapshot_t power_evidence;
    ego_provenance_info_t provenance;
} ego_evidence_chain_t;

typedef struct {
    char estimation_id[48];
    char device_id[32];
    uint32_t boot_count;
    int64_t timestamp_monotonic_ns;
    ego_spatial_mobility_t spatial_mobility;
    ego_posture_anomaly_t posture_anomaly;
    ego_device_wear_state_t device_wear_state;
    float confidence;
    uint32_t window_duration_ms;
    char reason_codes[EGO_STATE_MAX_REASON_CODES][EGO_STATE_REASON_CODE_MAX_LEN];
    uint8_t reason_code_count;
    char primary_evidence_digest[EGO_STATE_DIGEST_HEX_LEN];
    bool is_mock;
} ego_state_estimation_t;

typedef struct {
    ego_imu_raw_sample_t imu_ring[EGO_STATE_MAX_IMU_SAMPLES];
    uint16_t ring_head;
    uint16_t ring_count;

    ego_location_snapshot_t location;
    ego_network_snapshot_t network;
    ego_power_snapshot_t power;
    ego_provenance_info_t provenance;

    int64_t last_shock_time_ns;
    int64_t immobility_start_ns;
    int64_t last_imu_input_ns;
    int64_t last_evaluation_ns;
    bool imu_invalid;
    bool imu_invalid_is_mock;
    bool imu_future_rejected;
    bool last_imu_is_mock;
    uint32_t estimation_sequence;

    char device_id[32];
    uint32_t boot_count;
    bool initialized;
} ego_state_engine_ctx_t;

/**
 * @brief Initialize the embedded ego-state engine context.
 */
esp_err_t ego_state_engine_init(
    ego_state_engine_ctx_t *ctx,
    const char *device_id,
    uint32_t boot_count,
    const char *firmware_version,
    const char *elf_sha256
);

/**
 * @brief Ingest a single 6-axis IMU measurement (accel in mg, gyro in mdps).
 */
esp_err_t ego_state_engine_feed_imu(
    ego_state_engine_ctx_t *ctx,
    float ax_mg,
    float ay_mg,
    float az_mg,
    float gx_mdps,
    float gy_mdps,
    float gz_mdps,
    int64_t timestamp_ns,
    bool is_mock
);

/**
 * @brief Ingest latest GNSS observation.
 */
esp_err_t ego_state_engine_feed_location(
    ego_state_engine_ctx_t *ctx,
    bool fix_valid,
    float ground_speed_m_s,
    double lat_deg,
    double lon_deg,
    float hdop,
    uint16_t sats,
    float course_deg,
    int64_t timestamp_ns,
    bool is_mock
);

/**
 * @brief Ingest latest cellular/Wi-Fi network observation.
 */
esp_err_t ego_state_engine_feed_network(
    ego_state_engine_ctx_t *ctx,
    ego_network_type_t net_type,
    float lte_rsrp_dbm,
    const char *lte_cell_id,
    uint16_t wifi_ap_count,
    const char *wifi_hash,
    int64_t timestamp_ns,
    bool is_mock
);

/**
 * @brief Ingest latest battery and power status.
 */
esp_err_t ego_state_engine_feed_power(
    ego_state_engine_ctx_t *ctx,
    float battery_soc_percent,
    int32_t battery_voltage_mv,
    bool is_charging,
    bool charging_valid,
    int64_t timestamp_ns,
    bool is_mock
);

/**
 * @brief Evaluate active ego-state across the rolling time window and compute evidence digest.
 */
esp_err_t ego_state_engine_evaluate(
    ego_state_engine_ctx_t *ctx,
    int64_t now_monotonic_ns,
    uint32_t window_duration_ms,
    ego_state_estimation_t *out_state,
    ego_evidence_chain_t *out_evidence
);

/**
 * @brief String conversion helpers.
 */
const char *ego_spatial_mobility_to_str(ego_spatial_mobility_t mobility);
const char *ego_posture_anomaly_to_str(ego_posture_anomaly_t anomaly);
const char *ego_device_wear_to_str(ego_device_wear_state_t wear);
const char *ego_network_type_to_str(ego_network_type_t net);

#ifdef __cplusplus
}
#endif

#endif /* EGO_STATE_ENGINE_H */
