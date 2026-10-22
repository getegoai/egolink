/**
 * @file ego_blackbox.h
 * @brief EgoLink Local-First SD Card Black Box Storage Module
 *
 * Implements high-reliability local storage of sensor streams, Ego-State estimations,
 * cellular network metrics, power telemetry, and emergency events on the 64GB TF card
 * via 1-bit SDMMC + FATFS VFS.
 */

#ifndef EGO_BLACKBOX_H
#define EGO_BLACKBOX_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char *mount_point;            /* e.g. "/sdcard" */
    int pin_clk;                        /* GPIO16 */
    int pin_cmd;                        /* GPIO43 */
    int pin_d0;                         /* GPIO44 */
    int pin_pwr;                        /* GPIO4 (LOW turns Q5 3.3V_SD ON) */
    bool format_if_mount_failed;        /* Auto-format unformatted/exFAT card to FAT32 */
    size_t max_file_size_bytes;         /* Rotation limit (e.g. 5MB) */
} ego_blackbox_config_t;

typedef struct {
    bool is_mounted;
    char card_name[16];
    uint64_t total_capacity_mb;
    uint64_t free_space_mb;
    uint32_t total_records_written;
    uint32_t current_file_bytes;
    char current_session_file[160];
    uint32_t write_errors;
} ego_blackbox_status_t;

typedef struct {
    int64_t timestamp_ms;
    /* Ego-State Engine */
    uint32_t cycle;
    const char *est_id;
    const char *mobility_str;
    const char *wear_str;
    const char *anomaly_str;
    float confidence;
    const char *evidence_digest;
    uint32_t outbox_crc;
    /* IMU / Motion */
    float ax_mg;
    float ay_mg;
    float az_mg;
    float motion_rms;
    float imu_rate_hz;
    /* Power */
    int vbat_mv;
    float soc_pct;
    bool is_charging;
    /* Cellular */
    int lte_rsrp;
    int csq_rssi;
    const char *network_type;
    /* GNSS */
    bool gnss_fix;
    double gnss_lat;
    double gnss_lon;
    float gnss_speed;
    float gnss_hdop;
    uint16_t gnss_sats;
    /* Call & SOS */
    const char *call_state_str;
    bool is_sos_active;
} ego_blackbox_record_t;

/**
 * @brief Initialize the SD card black box storage system.
 */
esp_err_t ego_blackbox_init(const ego_blackbox_config_t *cfg);

/**
 * @brief Append an Ego-State & telemetry record to the active session JSONL file.
 */
esp_err_t ego_blackbox_log_record(const ego_blackbox_record_t *rec);

/**
 * @brief Log an immediate high-priority event (SOS, call event, reboot, etc.).
 */
esp_err_t ego_blackbox_log_event(const char *event_type, const char *detail_json);

/**
 * @brief Flush and sync pending write buffers to SD card.
 */
esp_err_t ego_blackbox_sync(void);

/**
 * @brief Query status of black box storage system.
 */
esp_err_t ego_blackbox_get_status(ego_blackbox_status_t *out_status);

/**
 * @brief Close session file and unmount SD card cleanly.
 */
esp_err_t ego_blackbox_deinit(void);

#ifdef __cplusplus
}
#endif

#endif /* EGO_BLACKBOX_H */
