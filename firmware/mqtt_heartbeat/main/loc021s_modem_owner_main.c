#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "location_outbox_adapter.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "p0_delivery_runtime.h"
#include "p0_outbox_dispatcher.h"
#include "persistent_priority_outbox.h"
#include "persistent_priority_outbox_partition.h"
#include "sdkconfig.h"
#include "sim7670_location_modem_owner.h"
#include "sos_outbox_adapter.h"

#if !CONFIG_EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE
#error "LOC-021S source must only be compiled by its dedicated profile"
#endif

#if !CONFIG_EGOLINK_SIM7670_GNSS_ENABLED || \
    !CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED || \
    !CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED
#error "LOC-021S requires the reviewed GNSS/LTE/Q owner branches"
#endif

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || \
    CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || \
    CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED || \
    CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED || \
    CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED || \
    CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED || \
    CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED
#error "LOC-021S forbids every legacy modem/network/IMU application mode"
#endif

#define LOC021S_NVS_NAMESPACE "ego_loc021s"
#define LOC021S_NVS_BOOT_EPOCH_KEY "boot_epoch"
#define LOC021S_STREAM_ID "location"
#define LOC021S_OWNER_CORE_ID INT32_C(0)
#define LOC021S_OUTBOX_BASE_RETRY_MS UINT64_C(1000)
#define LOC021S_OUTBOX_MAX_RETRY_MS UINT64_C(60000)
#define LOC021S_METADATA_POLL_MS UINT32_C(100)

static const char *const TAG = "loc021s_profile";

/* Every object below is boot-long. Q has no shutdown/deinit contract. */
static egolink_outbox_partition_t s_outbox_partition;
static egolink_outbox_storage_t s_outbox_storage;
static egolink_outbox_t s_shared_outbox;
static egolink_location_outbox_adapter_t s_location_adapter;
static egolink_sos_outbox_adapter_t s_sos_adapter;
static egolink_p0_outbox_dispatcher_t s_dispatcher;
static egolink_p0_delivery_runtime_t s_delivery_runtime;
static egolink_sim7670_location_modem_owner_t s_modem_owner;
static char s_session_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
static char s_clock_domain_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];

static bool loc021s_now_ms(uint64_t *now_ms)
{
    if (now_ms == NULL) {
        return false;
    }
    const int64_t now_us = esp_timer_get_time();
    if (now_us < INT64_C(0)) {
        return false;
    }
    *now_ms = (uint64_t)now_us / UINT64_C(1000);
    return true;
}

/*
 * This profile never formats or erases NVS. A missing/incompatible/full NVS,
 * failed write, failed commit or failed readback stops before Q start.
 */
static bool loc021s_advance_boot_epoch(uint64_t *boot_epoch)
{
    if (boot_epoch == NULL || nvs_flash_init() != ESP_OK) {
        return false;
    }

    nvs_handle_t handle = 0;
    esp_err_t status = nvs_open(
        LOC021S_NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (status != ESP_OK) {
        return false;
    }

    uint64_t previous = UINT64_C(0);
    status = nvs_get_u64(handle, LOC021S_NVS_BOOT_EPOCH_KEY, &previous);
    if (status == ESP_ERR_NVS_NOT_FOUND) {
        previous = UINT64_C(0);
    } else if (status != ESP_OK) {
        nvs_close(handle);
        return false;
    }
    if (previous >= EGOLINK_LOCATION_OUTBOX_JSON_SAFE_INTEGER_MAX) {
        nvs_close(handle);
        return false;
    }

    const uint64_t next = previous + UINT64_C(1);
    status = nvs_set_u64(handle, LOC021S_NVS_BOOT_EPOCH_KEY, next);
    if (status == ESP_OK) {
        status = nvs_commit(handle);
    }
    uint64_t confirmed = UINT64_C(0);
    if (status == ESP_OK) {
        status = nvs_get_u64(
            handle, LOC021S_NVS_BOOT_EPOCH_KEY, &confirmed);
    }
    nvs_close(handle);
    if (status != ESP_OK || confirmed != next) {
        return false;
    }
    *boot_epoch = next;
    return true;
}

static egolink_location_runtime_text_t loc021s_text(const char *value)
{
    const egolink_location_runtime_text_t result = {
        .data = value,
        .length = value == NULL ? 0U : strlen(value),
    };
    return result;
}

static bool loc021s_build_boot_identity(uint64_t boot_epoch)
{
    const int session_length = snprintf(
        s_session_id, sizeof(s_session_id), "loc021s-b%" PRIu64,
        boot_epoch);
    const int clock_length = snprintf(
        s_clock_domain_id, sizeof(s_clock_domain_id),
        "esp-timer-b%" PRIu64, boot_epoch);
    return session_length > 0 && clock_length > 0 &&
        (size_t)session_length < sizeof(s_session_id) &&
        (size_t)clock_length < sizeof(s_clock_domain_id);
}

/*
 * S intentionally has no network path. This synchronous callback is the
 * honest P0-delivery dependency needed by O/Q and always retains the record.
 */
static egolink_p0_delivery_post_outcome_t loc021s_offline_post(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result)
{
    (void)context;
    (void)request;
    if (result == NULL) {
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    (void)memset(result, 0, sizeof(*result));
    if (!loc021s_now_ms(&result->completion_time_ms)) {
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE;
    return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
}

static bool loc021s_initialize_outbox(
    uint64_t boot_epoch,
    uint64_t now_ms)
{
    if (egolink_outbox_partition_init(&s_outbox_partition) != ESP_OK ||
        egolink_outbox_partition_storage(
            &s_outbox_partition, &s_outbox_storage) != ESP_OK) {
        return false;
    }

    const egolink_outbox_config_t outbox_config = {
        .device_id = CONFIG_EGOLINK_DEVICE_ID,
        .max_records = EGOLINK_OUTBOX_MAX_RECORDS,
        .reserved_critical_records = UINT16_C(1),
        .max_total_payload_bytes =
            EGOLINK_OUTBOX_MAX_RECORDS * EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
        .max_payload_bytes = EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
        .base_retry_ms = LOC021S_OUTBOX_BASE_RETRY_MS,
        .max_retry_ms = LOC021S_OUTBOX_MAX_RETRY_MS,
        .tombstone_capacity = EGOLINK_OUTBOX_MAX_TOMBSTONES,
    };
    egolink_outbox_init_report_t report;
    return egolink_location_outbox_adapter_init(
               &s_location_adapter,
               &s_shared_outbox,
               &outbox_config,
               &s_outbox_storage,
               boot_epoch,
               now_ms,
               &report) == EGOLINK_OUTBOX_OK;
}

static bool loc021s_initialize_delivery(void)
{
    if (egolink_sos_outbox_adapter_bind(
            &s_sos_adapter,
            &s_shared_outbox,
            CONFIG_EGOLINK_DEVICE_ID) != EGOLINK_OUTBOX_OK) {
        return false;
    }

    egolink_p0_outbox_dispatcher_config_t dispatcher_config;
    egolink_p0_outbox_dispatcher_default_config(&dispatcher_config);
    dispatcher_config.enabled = true;
    if (egolink_p0_outbox_dispatcher_init(
            &s_dispatcher,
            &dispatcher_config,
            &s_shared_outbox,
            &s_location_adapter,
            &s_sos_adapter) != EGOLINK_P0_OUTBOX_OK) {
        return false;
    }

    egolink_p0_delivery_runtime_config_t delivery_config;
    egolink_p0_delivery_runtime_default_config(&delivery_config);
    delivery_config.enabled = true;
    delivery_config.http_post = loc021s_offline_post;
    delivery_config.http_context = NULL;
    if (egolink_p0_delivery_runtime_init(
            &s_delivery_runtime,
            &delivery_config,
            &s_dispatcher) != EGOLINK_P0_DELIVERY_OK) {
        return false;
    }

    egolink_p0_delivery_runtime_snapshot_t snapshot;
    return egolink_p0_delivery_runtime_current_status(
               &s_delivery_runtime, &snapshot) == EGOLINK_P0_DELIVERY_OK &&
        snapshot.lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE &&
        snapshot.phase == EGOLINK_P0_DELIVERY_PHASE_IDLE &&
        snapshot.dispatcher_bound && !snapshot.busy;
}

static bool loc021s_initialize_owner(uint64_t boot_epoch)
{
    egolink_sim7670_location_modem_owner_config_t owner_config;
    egolink_sim7670_location_modem_owner_default_config(&owner_config);
    owner_config.enabled = true;
    owner_config.owner_core_id = LOC021S_OWNER_CORE_ID;
    owner_config.first_sequence_id = UINT64_C(1);
    owner_config.pipeline_owner.device_id =
        loc021s_text(CONFIG_EGOLINK_DEVICE_ID);
    owner_config.pipeline_owner.boot_count = boot_epoch;
    owner_config.pipeline_owner.session_id = loc021s_text(s_session_id);
    owner_config.pipeline_owner.stream_id = loc021s_text(LOC021S_STREAM_ID);
    owner_config.pipeline_owner.clock_domain =
        EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC;
    owner_config.pipeline_owner.monotonic_clock_domain_id =
        loc021s_text(s_clock_domain_id);
    owner_config.sensor_publish_intent =
        EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;

    return egolink_sim7670_location_modem_owner_init(
               &s_modem_owner,
               &owner_config,
               &s_shared_outbox,
               &s_location_adapter,
               &s_delivery_runtime) ==
        EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS;
}

/* Q does not expose a request-specific completion token in this slice. */
static void loc021s_observe_owner_progress(uint64_t settled_before_request)
{
    uint64_t begin_ms = UINT64_C(0);
    if (!loc021s_now_ms(&begin_ms) ||
        begin_ms > UINT64_MAX -
            (uint64_t)CONFIG_EGOLINK_LOC021S_OBSERVE_TIMEOUT_MS) {
        ESP_LOGE(TAG, "LOC021S_OBSERVE_CLOCK_INVALID");
        return;
    }
    const uint64_t deadline_ms = begin_ms +
        (uint64_t)CONFIG_EGOLINK_LOC021S_OBSERVE_TIMEOUT_MS;

    for (;;) {
        egolink_sim7670_location_modem_owner_snapshot_t snapshot;
        const egolink_sim7670_modem_owner_status_t status =
            egolink_sim7670_location_modem_owner_current_status(
                &s_modem_owner, &snapshot);
        if (status != EGOLINK_SIM7670_MODEM_OWNER_OK) {
            ESP_LOGE(TAG, "LOC021S_SNAPSHOT_FAILED status=%d", (int)status);
            return;
        }
        if (snapshot.settled_commands > settled_before_request ||
            snapshot.fatal_recovery_required) {
            ESP_LOGI(
                TAG,
                "LOC021S_OWNER_PROGRESS_OBSERVED request_specific=false "
                "lifecycle=%d settled_before=%" PRIu64 " settled_now=%" PRIu64
                " gnss_off_confirmed=%s cleanup_recovery=%s fatal=%s",
                (int)snapshot.lifecycle,
                settled_before_request,
                snapshot.settled_commands,
                snapshot.gnss_off_confirmed ? "true" : "false",
                snapshot.cleanup_recovery_required ? "true" : "false",
                snapshot.fatal_recovery_required ? "true" : "false");
            return;
        }
        uint64_t now_ms = UINT64_C(0);
        if (!loc021s_now_ms(&now_ms) || now_ms >= deadline_ms) {
            ESP_LOGW(
                TAG,
                "LOC021S_ONE_SHOT_OBSERVE_TIMEOUT execution_active=%s "
                "cleanup_recovery=%s",
                snapshot.execution_active ? "true" : "false",
                snapshot.cleanup_recovery_required ? "true" : "false");
            return;
        }
        vTaskDelay(pdMS_TO_TICKS(LOC021S_METADATA_POLL_MS));
    }
}

void app_main(void)
{
    uint64_t boot_epoch = UINT64_C(0);
    uint64_t now_ms = UINT64_C(0);
    if (!loc021s_advance_boot_epoch(&boot_epoch) ||
        !loc021s_build_boot_identity(boot_epoch) ||
        !loc021s_now_ms(&now_ms)) {
        ESP_LOGE(TAG, "LOC021S_BOOT_IDENTITY_FAILED modem_started=false");
        return;
    }
    if (!loc021s_initialize_outbox(boot_epoch, now_ms)) {
        ESP_LOGE(TAG, "LOC021S_OUTBOX_INIT_FAILED modem_started=false");
        return;
    }
    if (!loc021s_initialize_delivery()) {
        ESP_LOGE(TAG, "LOC021S_DELIVERY_INIT_FAILED modem_started=false");
        return;
    }
    if (!loc021s_initialize_owner(boot_epoch)) {
        ESP_LOGE(TAG, "LOC021S_OWNER_INIT_FAILED modem_started=false");
        return;
    }

    const egolink_sim7670_modem_owner_status_t start_status =
        egolink_sim7670_location_modem_owner_start(&s_modem_owner);
    if (start_status != EGOLINK_SIM7670_MODEM_OWNER_STARTED) {
        ESP_LOGE(
            TAG,
            "LOC021S_OWNER_START_NOT_ACTIVE status=%d dependencies_retained=true",
            (int)start_status);
        return;
    }

    egolink_sim7670_location_modem_owner_snapshot_t before_request;
    if (egolink_sim7670_location_modem_owner_current_status(
            &s_modem_owner, &before_request) !=
        EGOLINK_SIM7670_MODEM_OWNER_OK) {
        ESP_LOGE(TAG, "LOC021S_BASELINE_SNAPSHOT_FAILED request_sent=false");
        return;
    }

    egolink_location_modem_enqueue_result_t request_result;
    const egolink_sim7670_modem_owner_status_t request_status =
        egolink_sim7670_location_modem_owner_request_gnss_status(
            &s_modem_owner,
            (uint64_t)CONFIG_EGOLINK_LOC021S_GNSS_STATUS_TIMEOUT_MS,
            &request_result);
    if (request_status != EGOLINK_SIM7670_MODEM_OWNER_QUEUED) {
        ESP_LOGE(
            TAG,
            "LOC021S_ONE_SHOT_REJECTED status=%d no_retry=true",
            (int)request_status);
        return;
    }
    ESP_LOGI(TAG, "LOC021S_ONE_SHOT_QUEUED no_network=true");
    loc021s_observe_owner_progress(before_request.settled_commands);
}
