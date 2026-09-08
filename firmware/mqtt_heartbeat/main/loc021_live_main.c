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
#include "esp_p0_https.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "esp_app_desc.h"
#include "esp_mac.h"
#include <sys/time.h>

#if !CONFIG_EGOLINK_LOC021_LIVE_PROFILE
#error "LOC-021 live source must only be compiled by its dedicated profile"
#endif

#if CONFIG_ESP_MAIN_TASK_STACK_SIZE < 8192
#error "LOC-021 live initialization requires its reviewed 8192-byte main stack"
#endif

#if !CONFIG_EGOLINK_SIM7670_GNSS_ENABLED || \
    !CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED || \
    !CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED
#error "LOC-021 live requires the reviewed GNSS/LTE/Q owner branches"
#endif

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || \
    CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || \
    CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED || \
    CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED || \
    CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED || \
    CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED || \
    CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED
#error "LOC-021 live forbids every legacy modem/network/IMU application mode"
#endif

#define LOC021_LIVE_NVS_NAMESPACE "ego_loc021_live"
#define LOC021_LIVE_NVS_BOOT_EPOCH_KEY "boot_epoch"
#define LOC021_LIVE_STREAM_ID "location"
#define LOC021_LIVE_OWNER_CORE_ID INT32_C(0)
#define LOC021_LIVE_OUTBOX_BASE_RETRY_MS UINT64_C(1000)
#define LOC021_LIVE_OUTBOX_MAX_RETRY_MS UINT64_C(60000)
#define LOC021_LIVE_METADATA_POLL_MS UINT32_C(100)

static const char *const TAG = "loc021_live_profile";

/* Storage remains alive after cooperative quiescence; UART is never force-deleted. */
static egolink_outbox_partition_t s_outbox_partition;
static egolink_outbox_storage_t s_outbox_storage;
static egolink_outbox_storage_t s_partition_storage;
static unsigned s_slot_writes;
static uint64_t s_utc_epoch_at_boot_ms;
static egolink_outbox_t s_shared_outbox;
static egolink_location_outbox_adapter_t s_location_adapter;
static egolink_sos_outbox_adapter_t s_sos_adapter;
static egolink_p0_outbox_dispatcher_t s_dispatcher;
static egolink_p0_delivery_runtime_t s_delivery_runtime;
static egolink_sim7670_location_modem_owner_t s_modem_owner;
static char s_session_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
static char s_clock_domain_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];

static bool loc021_live_now_ms(uint64_t *now_ms)
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
static bool loc021_live_advance_boot_epoch(uint64_t *boot_epoch)
{
    if (boot_epoch == NULL || nvs_flash_init() != ESP_OK) {
        return false;
    }

    nvs_handle_t handle = 0;
    esp_err_t status = nvs_open(
        LOC021_LIVE_NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (status != ESP_OK) {
        return false;
    }

    uint64_t previous = UINT64_C(0);
    status = nvs_get_u64(handle, LOC021_LIVE_NVS_BOOT_EPOCH_KEY, &previous);
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
    status = nvs_set_u64(handle, LOC021_LIVE_NVS_BOOT_EPOCH_KEY, next);
    if (status == ESP_OK) {
        status = nvs_commit(handle);
    }
    uint64_t confirmed = UINT64_C(0);
    if (status == ESP_OK) {
        status = nvs_get_u64(
            handle, LOC021_LIVE_NVS_BOOT_EPOCH_KEY, &confirmed);
    }
    nvs_close(handle);
    if (status != ESP_OK || confirmed != next) {
        return false;
    }
    *boot_epoch = next;
    return true;
}

static egolink_location_runtime_text_t loc021_live_text(const char *value)
{
    const egolink_location_runtime_text_t result = {
        .data = value,
        .length = value == NULL ? 0U : strlen(value),
    };
    return result;
}

static bool loc021_live_build_boot_identity(uint64_t boot_epoch)
{
    const int session_length = snprintf(
        s_session_id, sizeof(s_session_id), "loclive-b%" PRIu64,
        boot_epoch);
    const int clock_length = snprintf(
        s_clock_domain_id, sizeof(s_clock_domain_id),
        "esp-timer-b%" PRIu64, boot_epoch);
    return session_length > 0 && clock_length > 0 &&
        (size_t)session_length < sizeof(s_session_id) &&
        (size_t)clock_length < sizeof(s_clock_domain_id);
}

static egolink_esp_p0_https_t s_https = {
    .origin = CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL,
    .expected_host = CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST,
    .bearer = CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
    .max_attempts = 6U, .transaction_timeout_ms = 12000U,
};
static EventGroupHandle_t s_network_events;
static esp_netif_t *s_netif;
static void network_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP)
        xEventGroupSetBits(s_network_events, BIT0);
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED)
        xEventGroupClearBits(s_network_events, BIT0);
}

static bool network_start(void)
{
    if (!egolink_esp_p0_https_config_valid(&s_https) ||
        strlen(CONFIG_EGOLINK_WIFI_SSID) == 0U ||
        strlen(CONFIG_EGOLINK_WIFI_SSID) > 32U ||
        strlen(CONFIG_EGOLINK_WIFI_PASSWORD) < 8U ||
        strlen(CONFIG_EGOLINK_WIFI_PASSWORD) > 63U) return false;
    s_network_events = xEventGroupCreate();
    if (!s_network_events || esp_netif_init() != ESP_OK ||
        esp_event_loop_create_default() != ESP_OK) return false;
    s_netif = esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (!s_netif || esp_wifi_init(&init) != ESP_OK ||
        esp_wifi_set_storage(WIFI_STORAGE_RAM) != ESP_OK ||
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, network_event, NULL) != ESP_OK ||
        esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, network_event, NULL) != ESP_OK)
        return false;
    wifi_config_t wifi = {0};
    memcpy(wifi.sta.ssid, CONFIG_EGOLINK_WIFI_SSID, strlen(CONFIG_EGOLINK_WIFI_SSID));
    memcpy(wifi.sta.password, CONFIG_EGOLINK_WIFI_PASSWORD, strlen(CONFIG_EGOLINK_WIFI_PASSWORD));
    wifi.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    if (esp_wifi_set_mode(WIFI_MODE_STA) != ESP_OK ||
        esp_wifi_set_config(WIFI_IF_STA, &wifi) != ESP_OK ||
        esp_wifi_start() != ESP_OK || esp_wifi_connect() != ESP_OK) return false;
    if (!(xEventGroupWaitBits(s_network_events, BIT0, pdFALSE, pdTRUE,
                            pdMS_TO_TICKS(20000)) & BIT0)) {
        ESP_LOGW(TAG, "NETWORK stage=wifi_ip timeout_ms=20000");
        return false;
    }
    ESP_LOGI(TAG, "NETWORK stage=wifi_ip ready=true");
    esp_sntp_config_t clock = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    const esp_err_t sntp_init_status = esp_netif_sntp_init(&clock);
    if (sntp_init_status != ESP_OK) {
        ESP_LOGW(TAG, "NETWORK stage=sntp_init status=%d", (int)sntp_init_status);
        return false;
    }
    const esp_err_t sntp_status = esp_netif_sntp_sync_wait(pdMS_TO_TICKS(30000));
    bool synced = sntp_status == ESP_OK;
    ESP_LOGI(TAG, "NETWORK stage=sntp_sync status=%d timeout_ms=30000", (int)sntp_status);
    esp_netif_sntp_deinit();
    if (synced) {
        struct timeval utc;
        uint64_t mono;
        if (gettimeofday(&utc, NULL) == 0 && loc021_live_now_ms(&mono) &&
            utc.tv_sec >= 1767225600 && utc.tv_sec < 4102444800LL) {
            uint64_t utc_ms = (uint64_t)utc.tv_sec * 1000U + (uint64_t)utc.tv_usec / 1000U;
            if (utc_ms >= mono) s_utc_epoch_at_boot_ms = utc_ms - mono;
        }
    }
    return synced && s_utc_epoch_at_boot_ms != 0U;
}

static egolink_outbox_storage_result_t budget_read(void *context, uint8_t slot,
    void *destination, size_t capacity, size_t *length)
{
    (void)context;
    return s_partition_storage.read_slot(s_partition_storage.context, slot, destination, capacity, length);
}
static egolink_outbox_storage_result_t budget_write(void *context, uint8_t slot,
    const void *source, size_t length)
{
    (void)context;
    if (s_slot_writes >= 32U) return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    ++s_slot_writes;
    return s_partition_storage.write_slot(s_partition_storage.context, slot, source, length);
}

static bool loc021_live_initialize_outbox(
    uint64_t boot_epoch,
    uint64_t now_ms)
{
    esp_err_t partition_status = egolink_outbox_partition_init(&s_outbox_partition);
    if (partition_status == ESP_OK) {
        partition_status = egolink_outbox_partition_storage(
            &s_outbox_partition, &s_partition_storage);
    }
    if (partition_status != ESP_OK) {
        ESP_LOGE(TAG, "OUTBOX partition_status=%d stored=false delivered=false", (int)partition_status);
        return false;
    }

    s_outbox_storage = (egolink_outbox_storage_t){ .read_slot=budget_read, .write_slot=budget_write };
    const egolink_outbox_config_t outbox_config = {
        .device_id = CONFIG_EGOLINK_DEVICE_ID,
        .max_records = EGOLINK_OUTBOX_MAX_RECORDS,
        .reserved_critical_records = UINT16_C(1),
        .max_total_payload_bytes =
            EGOLINK_OUTBOX_MAX_RECORDS * EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
        .max_payload_bytes = EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
        .base_retry_ms = LOC021_LIVE_OUTBOX_BASE_RETRY_MS,
        .max_retry_ms = LOC021_LIVE_OUTBOX_MAX_RETRY_MS,
        .tombstone_capacity = EGOLINK_OUTBOX_MAX_TOMBSTONES,
    };
    egolink_outbox_init_report_t report;
    const egolink_outbox_status_t status = egolink_location_outbox_adapter_init(
               &s_location_adapter,
               &s_shared_outbox,
               &outbox_config,
               &s_outbox_storage,
               boot_epoch,
               now_ms,
               &report);
    ESP_LOGI(TAG, "OUTBOX status=%s slot0=%s slot1=%s offset=0x%" PRIx32
        " slot_writes=%u recovery=%d",
        egolink_outbox_status_name(status),
        egolink_outbox_slot_state_name(report.slot_state[0]),
        egolink_outbox_slot_state_name(report.slot_state[1]),
        s_outbox_partition.partition->address, s_slot_writes, (int)report.recovery_state);
    return status == EGOLINK_OUTBOX_OK;
}

static bool loc021_live_initialize_delivery(void)
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
    delivery_config.http_post = egolink_esp_p0_https_post;
    delivery_config.max_post_duration_ms = 15000U;
    delivery_config.http_context = &s_https;
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

static bool loc021_live_initialize_owner(uint64_t boot_epoch)
{
    egolink_sim7670_location_modem_owner_config_t owner_config;
    egolink_sim7670_location_modem_owner_default_config(&owner_config);
    owner_config.enabled = true;
    owner_config.utc_epoch_at_boot_ms = s_utc_epoch_at_boot_ms;
    owner_config.run_duration_ms = 180000U;
    owner_config.max_commands_per_wake = 1U;
    owner_config.max_sensor_commands = 4U;
    owner_config.gnss_power_on_settle_ms = 30000U;
    owner_config.default_gnss_status_timeout_ms = 42000U;
    owner_config.pipeline_owner.local_progress_on_publish_failure = true;
    owner_config.owner_core_id = LOC021_LIVE_OWNER_CORE_ID;
    owner_config.first_sequence_id = UINT64_C(1);
    owner_config.pipeline_owner.device_id =
        loc021_live_text(CONFIG_EGOLINK_DEVICE_ID);
    owner_config.pipeline_owner.boot_count = boot_epoch;
    owner_config.pipeline_owner.session_id = loc021_live_text(s_session_id);
    owner_config.pipeline_owner.stream_id = loc021_live_text(LOC021_LIVE_STREAM_ID);
    owner_config.pipeline_owner.clock_domain =
        EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC;
    owner_config.pipeline_owner.monotonic_clock_domain_id =
        loc021_live_text(s_clock_domain_id);
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

static void loc021_live_log_owner(const char *phase)
{
    egolink_sim7670_location_modem_owner_snapshot_t state;
    const egolink_sim7670_modem_owner_status_t status =
        egolink_sim7670_location_modem_owner_current_status(&s_modem_owner, &state);
    if (status != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        ESP_LOGE(TAG, "OWNER phase=%s snapshot_status=%d", phase, (int)status);
        return;
    }
    ESP_LOGI(TAG, "OWNER phase=%s lifecycle=%d status=%d uart=%d exclusive=%d executing=%d"
        " gnss_off=%d cleanup=%d fatal=%d stop_requested=%d quiesced=%d",
        phase, (int)state.lifecycle, (int)state.last_status, state.uart_initialized,
        state.exclusive_owner_confirmed, state.execution_active, state.gnss_off_confirmed,
        state.cleanup_recovery_required, state.fatal_recovery_required,
        state.stop_requested, state.quiesced);
    ESP_LOGI(TAG, "POWER_OFF phase=%s attempts=%" PRIu64 " confirmed=%" PRIu64
        " unconfirmed=%" PRIu64 " recovery_attempts=%" PRIu64 " outcome=%d reason=%d",
        phase, state.power_off_attempts, state.power_off_confirmed,
        state.power_off_unconfirmed, state.recovery_attempts,
        (int)state.last_power_off_outcome, (int)state.last_power_off_reason);
}

static bool loc021_live_wait_for_owner_recovery(void)
{
    /* Q already retries a failed startup power-off on its sole owner task.
     * Observe that recovery; never start another task or treat ERROR as off. */
    uint64_t started_ms = 0U;
    if (!loc021_live_now_ms(&started_ms)) return false;
    loc021_live_log_owner("startup_recovery_wait");
    for (;;) {
        uint64_t now_ms = 0U;
        if (!loc021_live_now_ms(&now_ms) || now_ms < started_ms ||
            now_ms - started_ms >= 10000U) break;
        egolink_sim7670_location_modem_owner_snapshot_t state;
        if (egolink_sim7670_location_modem_owner_current_status(&s_modem_owner, &state) !=
                EGOLINK_SIM7670_MODEM_OWNER_OK || state.fatal_recovery_required ||
            state.stop_requested || state.quiesced) break;
        if (state.lifecycle == EGOLINK_SIM7670_MODEM_OWNER_ACTIVE &&
            state.uart_initialized && state.exclusive_owner_confirmed &&
            state.gnss_off_confirmed && !state.cleanup_recovery_required) {
            ESP_LOGI(TAG, "STARTUP_RECOVERED elapsed_ms=%" PRIu64 " same_owner=true",
                now_ms - started_ms);
            loc021_live_log_owner("startup_recovered");
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(LOC021_LIVE_METADATA_POLL_MS));
    }
    ESP_LOGW(TAG, "STARTUP_RECOVERY_NOT_ACTIVE timeout_ms=10000");
    return false;
}

static void loc021_live_stop_owner(const char *reason)
{
    /* A failed synchronous start can leave the boot-long Q task recovering.
     * Use its existing cooperative stop before returning from app_main; never
     * tear down the UART or report quiescence without confirmed GNSS off. */
    loc021_live_log_owner("before_stop");
    const egolink_sim7670_modem_owner_status_t stop_status =
        egolink_sim7670_location_modem_owner_request_stop(&s_modem_owner);
    bool stopped = false;
    for (unsigned second = 0U; second <= 30U; ++second) {
        egolink_sim7670_location_modem_owner_snapshot_t state;
        if (egolink_sim7670_location_modem_owner_current_status(&s_modem_owner, &state) ==
                EGOLINK_SIM7670_MODEM_OWNER_OK && state.quiesced) {
            stopped = true;
            break;
        }
        if (second < 30U) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    loc021_live_log_owner("after_stop");
    if (stopped) (void)esp_wifi_stop();
    ESP_LOGI(TAG, "STOP quiesced=%d reason=%s request_status=%d slot_writes=%u"
        " main_stack_min_free_bytes=%u dependencies_retained=true",
        stopped, reason, (int)stop_status, s_slot_writes,
        (unsigned)(uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t)));
}

void app_main(void)
{
    uint8_t mac[6];
    const uint8_t expected_mac[6] = {0xa0,0xf2,0x62,0xe3,0xb2,0x10};
    if (esp_efuse_mac_get_default(mac) != ESP_OK || memcmp(mac,expected_mac,sizeof(mac)) != 0 ||
        !egolink_esp_p0_https_config_valid(&s_https) || strlen(CONFIG_EGOLINK_WIFI_SSID) == 0U) {
        ESP_LOGE(TAG, "BOARD_OR_CREDENTIAL_CONFIG_INVALID no_io=true");
        return;
    }
    uint64_t boot_epoch = UINT64_C(0);
    uint64_t now_ms = UINT64_C(0);
    if (!loc021_live_advance_boot_epoch(&boot_epoch) ||
        !loc021_live_build_boot_identity(boot_epoch) ||
        !loc021_live_now_ms(&now_ms)) {
        ESP_LOGE(TAG, "LOC021_LIVE_BOOT_IDENTITY_FAILED modem_started=false");
        return;
    }
    ESP_LOGI(TAG, "BOOT epoch=%" PRIu64 " run=%s transport=wifi_https duration_ms=180000 max_gnss=4 max_posts=6 max_slot_writes=32 image=%s",
        boot_epoch, s_session_id, esp_app_get_description()->version);
    if (!network_start()) {
        (void)esp_wifi_stop();
        ESP_LOGW(TAG, "NETWORK_PREFLIGHT_FAILED local_location_continues=true");
    }
    ESP_LOGI(TAG, "CLOCK utc_epoch_at_boot_ms=%" PRIu64 " source=sntp_anchor_or_unmapped clock_uncertainty_unmeasured=true",
        s_utc_epoch_at_boot_ms);
    (void)loc021_live_now_ms(&now_ms);
    s_https.deadline_ms = now_ms + 180000U;
    if (!loc021_live_initialize_outbox(boot_epoch, now_ms)) {
        (void)esp_wifi_stop();
        ESP_LOGE(TAG, "LOC021_LIVE_OUTBOX_INIT_FAILED modem_started=false");
        return;
    }
    if (!loc021_live_initialize_delivery()) {
        (void)esp_wifi_stop();
        ESP_LOGE(TAG, "LOC021_LIVE_DELIVERY_INIT_FAILED modem_started=false");
        return;
    }
    if (!loc021_live_initialize_owner(boot_epoch)) {
        (void)esp_wifi_stop();
        ESP_LOGE(TAG, "LOC021_LIVE_OWNER_INIT_FAILED modem_started=false");
        return;
    }
    ESP_LOGI(TAG, "INIT owner_ready=true main_stack_min_free_bytes=%u",
        (unsigned)(uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t)));

    const egolink_sim7670_modem_owner_status_t start_status =
        egolink_sim7670_location_modem_owner_start(&s_modem_owner);
    bool owner_active = start_status == EGOLINK_SIM7670_MODEM_OWNER_STARTED;
    if (start_status == EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED) {
        owner_active = loc021_live_wait_for_owner_recovery();
    }
    if (!owner_active) {
        ESP_LOGE(
            TAG,
            "LOC021_LIVE_OWNER_START_NOT_ACTIVE status=%d dependencies_retained=true",
            (int)start_status);
        loc021_live_stop_owner("owner_start_failed");
        return;
    }

    ESP_LOGI(TAG, "GNSS_ACQUISITION powered_settle_ms=30000 request_timeout_ms=42000 cancel_on_stop=true");
    for (unsigned second = 0U; second < 185U; ++second) {
        egolink_sim7670_location_modem_owner_snapshot_t state;
        if (egolink_sim7670_location_modem_owner_current_status(&s_modem_owner, &state) !=
            EGOLINK_SIM7670_MODEM_OWNER_OK) break;
        if (state.quiesced || state.fatal_recovery_required) break;
        if (second % 45U == 0U && state.sensor_commands < 4U) {
            egolink_location_modem_enqueue_result_t result;
            (void)egolink_sim7670_location_modem_owner_request_gnss_status(&s_modem_owner, 42000U, &result);
        }
        if (second % 5U == 0U) {
            uint64_t sample_now = 0U;
            bool clock_valid = loc021_live_now_ms(&sample_now);
            sample_now += s_utc_epoch_at_boot_ms;
            bool age_valid = clock_valid && state.quality.trusted_present &&
                sample_now >= state.quality.trusted_time_ms;
            ESP_LOGI(TAG,
            "LOCAL seq=%" PRIu64 " source_ms=%" PRIu64 " gnss=%d belief=%d persistence_failures=%" PRIu64
            " server_ack_deletes=%" PRIu64 " sensors=%" PRIu32 " gnss_off=%d",
            state.local_sequence, state.source_event_time_ms, (int)state.gnss_state,
            (int)state.location_belief, state.persistence_failures, state.matched_ack_deletes,
            state.sensor_commands, state.gnss_off_confirmed);
            ESP_LOGI(TAG, "QUALITY trusted=%d trusted_seq=%" PRIu64 " trusted_ms=%" PRIu64
                " age_valid=%d age_ms=%" PRIu64 " source=%d accuracy_present=%d accuracy_m=%.1f uncertainty_present=%d uncertainty_at_event_m=%.1f basis=%d",
                state.quality.trusted_present, state.quality.trusted_sequence,
                state.quality.trusted_time_ms, age_valid,
                age_valid ? sample_now - state.quality.trusted_time_ms : 0U,
                (int)state.quality.source, state.quality.accuracy_present, state.quality.accuracy_m,
                state.quality.uncertainty_present, state.quality.uncertainty_m, (int)state.quality.uncertainty_basis);
            ESP_LOGI(TAG, "DELIVERY attempts=%" PRIu64 " last_settle_mono_ms=%" PRIu64
                " status=%d enqueue=%d storage=%d",
                state.delivery_attempts, state.last_delivery_time_ms, (int)state.last_delivery_status,
                (int)state.last_enqueue_status, (int)state.last_storage_status);
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    loc021_live_stop_owner("run_complete");
}
