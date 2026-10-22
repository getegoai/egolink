/**
 * @file ego_outbox_sync.h
 * @brief Local-First Offline Telemetry Cache & Cloud Breakpoint Resumption Engine
 *
 * Implements persistent outbox queueing on TF Card (with RAM/Flash fallback)
 * to ensure zero telemetry loss during 4G network outages, with automatic
 * FIFO resumption and rate-controlled backfilling upon carrier reconnection.
 */

#ifndef EGO_OUTBOX_SYNC_H
#define EGO_OUTBOX_SYNC_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef esp_err_t (*ego_outbox_post_fn)(const char *path, const char *json_payload, int *out_http_status);

typedef struct {
    const char *storage_dir;        /* e.g. "/sdcard/ego_blackbox/outbox" */
    ego_outbox_post_fn post_fn;     /* Function to send HTTP POST to Web platform */
    size_t max_queue_bytes;         /* Rotation/safety limit (default 10MB) */
} ego_outbox_sync_config_t;

typedef struct {
    bool is_initialized;
    uint32_t pending_count;         /* Number of records currently awaiting sync */
    uint32_t total_enqueued;        /* Cumulative records enqueued */
    uint32_t total_acked;           /* Cumulative records confirmed sent */
    uint32_t total_failed;          /* Send failures */
    bool is_draining;               /* Currently backfilling / syncing queue */
    bool sim_offline_mode;          /* Software-simulated offline mode for test */
    size_t queue_file_bytes;        /* Size of queue.jsonl in bytes */
    long read_offset;               /* Current uncommitted read offset */
} ego_outbox_sync_status_t;

/**
 * @brief Initialize the Outbox sync engine and recover previous state.
 */
esp_err_t ego_outbox_sync_init(const ego_outbox_sync_config_t *cfg);

/**
 * @brief Enqueue a telemetry payload directly to the offline outbox cache.
 */
esp_err_t ego_outbox_sync_enqueue(const char *path, const char *json_payload);

/**
 * @brief Submit telemetry: sends immediately if online & idle, or enqueues if offline/error.
 *
 * @param path API endpoint path (e.g. "/api/v1/devices/ego-link-001/telemetry")
 * @param json_payload JSON string
 * @param is_network_online True if 4G network is registered and has valid IP
 * @param out_sent_direct Set to true if sent immediately, false if enqueued
 * @return esp_err_t ESP_OK if either sent or safely cached
 */
esp_err_t ego_outbox_sync_submit(
    const char *path,
    const char *json_payload,
    bool is_network_online,
    bool *out_sent_direct);

/**
 * @brief Execute one incremental resumption/drain step.
 * Reads next record from read_offset, posts it, and if 200 OK advances pointer.
 *
 * @param is_network_online True if 4G network is registered and ready
 * @param can_use_modem True if modem is not busy (e.g. no voice call active)
 * @return int 1 if a record was synced, 0 if queue empty or paused, -1 on network/post error
 */
int ego_outbox_sync_step(bool is_network_online, bool can_use_modem);

/**
 * @brief Query current outbox sync status.
 */
esp_err_t ego_outbox_sync_get_status(ego_outbox_sync_status_t *out_status);

/**
 * @brief Set simulation offline mode (forces all submissions to cache in outbox for testing).
 */
void ego_outbox_sync_set_sim_offline(bool enable);

/**
 * @brief Clear all pending records in the outbox queue and reset pointers.
 */
esp_err_t ego_outbox_sync_clear(void);

#ifdef __cplusplus
}
#endif

#endif /* EGO_OUTBOX_SYNC_H */
