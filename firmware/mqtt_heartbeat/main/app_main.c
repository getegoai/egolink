#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cJSON.h"
#include "esp_check.h"
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
#include "esp_crt_bundle.h"
#endif
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/portmacro.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "platform_imu.h"
#include "platform_power.h"
#include "safety_model.h"
#include "sim7670_gnss.h"

static const char *TAG = "egolink_mqtt_heartbeat";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define MQTT_CONNECTED_BIT BIT2
#define WIFI_MAX_RETRY 8
#define COMMAND_POLL_TASK_STACK_SIZE 12288
#define HEARTBEAT_TASK_STACK_SIZE 12288
#define SENSOR_TASK_STACK_SIZE 12288
#define LTE_HTTP_PROBE_TASK_STACK_SIZE 12288
#define LTE_HTTP_COMMAND_TASK_STACK_SIZE 16384
#if CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
#define LTE_OBSERVATION_FRAGMENT_MAX 2300
#else
#define LTE_OBSERVATION_FRAGMENT_MAX 1
#endif
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
#define UPLINK_READY_BIT WIFI_CONNECTED_BIT
#else
#define UPLINK_READY_BIT MQTT_CONNECTED_BIT
#endif
#ifndef CONFIG_EGOLINK_TEST_RUN_ID
#define CONFIG_EGOLINK_TEST_RUN_ID ""
#endif

#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
_Static_assert(sizeof(CONFIG_EGOLINK_WIFI_SSID) > 1, "FW-007 failover requires a non-empty Wi-Fi SSID");
_Static_assert(sizeof(CONFIG_EGOLINK_WIFI_PASSWORD) > 1, "FW-007 failover requires a non-empty Wi-Fi password");
#endif

static EventGroupHandle_t s_event_group;
#if !CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
static esp_mqtt_client_handle_t s_mqtt_client;
#endif
static int s_wifi_retry_count;
static bool s_wifi_initialized;
static bool s_wifi_started;
static uint32_t s_seq;
static portMUX_TYPE s_seq_mux = portMUX_INITIALIZER_UNLOCKED;
static int s_last_rssi = -127;
static const char *s_reset_reason = "unknown";
static uint32_t s_boot_count;
static bool s_boot_count_persisted;
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
typedef enum {
    LTE_WIFI_FAILOVER_LTE_PRIMARY = 0,
    LTE_WIFI_FAILOVER_WIFI_CONNECTING,
    LTE_WIFI_FAILOVER_WIFI_ACTIVE,
    LTE_WIFI_FAILOVER_OFFLINE,
} lte_wifi_failover_state_t;

static lte_wifi_failover_state_t s_lte_wifi_failover_state = LTE_WIFI_FAILOVER_LTE_PRIMARY;
static bool s_lte_wifi_failover_latched;
static int s_lte_transport_consecutive_failures;
static bool lte_wifi_failover_run_once(const char *reason);
#endif
static char s_status_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
static char s_sensor_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
static char s_lte_http_probe_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && \
    (CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED)
static char s_lte_command_last_cmd_id[64];
static char s_lte_command_parse_status[64] = "not_polled";
static char s_lte_command_diag_payload[1536];
static int s_lte_command_last_command_count;
static char s_lte_command_last_status[16] = "none";
static char s_lte_command_last_message[192] = "no command executed";
#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
#define LTE_EXECUTED_COMMAND_CACHE_SIZE CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS
#else
#define LTE_EXECUTED_COMMAND_CACHE_SIZE 4
_Static_assert(
    CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS <= LTE_EXECUTED_COMMAND_CACHE_SIZE,
    "Wi-Fi IMU executed-command cache must cover the configured successful-command limit");
#endif
typedef struct {
    bool valid;
    char cmd_id[64];
    char status[16];
    char message[192];
} lte_executed_command_result_t;
static lte_executed_command_result_t s_lte_executed_command_cache[LTE_EXECUTED_COMMAND_CACHE_SIZE];
static size_t s_lte_executed_command_cache_next;

#define IMU_WINDOW_CONTRACT_VERSION "egolink.imu_window.v1"
#define IMU_WINDOW_SAMPLE_COUNT 100u
#define IMU_WINDOW_INTERVAL_MS 50u
#define IMU_WINDOW_INTERVAL_US (IMU_WINDOW_INTERVAL_MS * 1000u)
#define IMU_WINDOW_WARMUP_SAMPLE_COUNT 10u
#define IMU_WINDOW_WARMUP_INTERVAL_MS 50u
#define IMU_WINDOW_RECORD_BYTES 28u
#define IMU_WINDOW_SAMPLES_PER_CHUNK 10u
#define IMU_WINDOW_CHUNK_COUNT \
    ((IMU_WINDOW_SAMPLE_COUNT + IMU_WINDOW_SAMPLES_PER_CHUNK - 1u) / IMU_WINDOW_SAMPLES_PER_CHUNK)
#define IMU_WINDOW_RAW_FRAME_MAX_BYTES 1200u
#define IMU_WINDOW_CAPTURE_CMD_ID_MAX 16u
#define IMU_WINDOW_CHUNK_BINARY_MAX (IMU_WINDOW_RECORD_BYTES * IMU_WINDOW_SAMPLES_PER_CHUNK)
#define IMU_WINDOW_CHUNK_BASE64_MAX ((((IMU_WINDOW_CHUNK_BINARY_MAX + 2u) / 3u) * 4u) + 1u)

typedef struct {
    uint32_t captured_samples;
    uint32_t read_failure_count;
    uint32_t mock_sample_count;
    uint32_t deadline_miss_count;
    uint32_t min_interval_us;
    uint32_t max_interval_us;
    uint32_t mean_interval_us;
    uint32_t warmup_sample_count;
    int first_read_error;
    char first_read_status[64];
    uint64_t capture_start_uptime_us;
    uint64_t capture_end_uptime_us;
    bool measurement_stop_ok;
} imu_window_capture_result_t;

static uint8_t s_imu_window_binary[IMU_WINDOW_SAMPLE_COUNT * IMU_WINDOW_RECORD_BYTES];
static char s_imu_window_chunk_base64[IMU_WINDOW_CHUNK_BASE64_MAX];
static char s_imu_window_payload[1100];
static char s_imu_window_frame[IMU_WINDOW_RAW_FRAME_MAX_BYTES + 1u];
static char s_imu_window_last_error[96] = "not_started";
static bool s_imu_window_service_failed_closed;
static bool imu_window_test_run_id_valid(const char *test_run_id);
typedef struct {
    uint32_t post_attempt_count;
    uint32_t post_success_count;
    uint32_t post_failure_count;
    uint32_t retry_attempt_count;
    uint32_t retry_success_count;
    uint32_t retry_failure_count;
    uint32_t dropped_message_count;
    char last_drop_reason[64];
    char last_error[SIM7670_LTE_HTTP_REASON_MAX];
} lte_raw_outbox_counters_t;

static lte_raw_outbox_counters_t s_lte_raw_outbox;
static portMUX_TYPE s_lte_raw_outbox_mux = portMUX_INITIALIZER_UNLOCKED;
#endif

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
typedef struct {
    char *buffer;
    size_t capacity;
    size_t length;
} http_response_buffer_t;

#define MESSAGE_HUB_BEARER_TOKEN_MAX_BYTES 160u
#endif

static const char *json_bool(bool value)
{
    return value ? "true" : "false";
}

static const char *json_number_or_null(char *buffer, size_t buffer_size, bool valid, double value, const char *format)
{
    if (!valid) {
        snprintf(buffer, buffer_size, "null");
    } else {
        snprintf(buffer, buffer_size, format, value);
    }
    return buffer;
}

static const char *json_int_or_null(char *buffer, size_t buffer_size, bool valid, int value)
{
    if (!valid) {
        snprintf(buffer, buffer_size, "null");
    } else {
        snprintf(buffer, buffer_size, "%d", value);
    }
    return buffer;
}

static void json_escape_summary(char *buffer, size_t buffer_size, const char *value)
{
    if (buffer == NULL || buffer_size == 0) {
        return;
    }
    size_t out = 0;
    const char *input = value ? value : "";
    for (size_t i = 0; input[i] != '\0' && out + 1 < buffer_size; ++i) {
        char ch = input[i];
        if (ch == '"' || ch == '\\') {
            if (out + 2 >= buffer_size) {
                break;
            }
            buffer[out++] = '\\';
            buffer[out++] = ch;
        } else if (ch == '\r' || ch == '\n' || ch == '\t') {
            buffer[out++] = ' ';
        } else if ((unsigned char)ch < 0x20) {
            buffer[out++] = ' ';
        } else {
            buffer[out++] = ch;
        }
    }
    buffer[out] = '\0';
}

static const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
    case ESP_RST_POWERON:
        return "poweron";
    case ESP_RST_EXT:
        return "external";
    case ESP_RST_SW:
        return "software";
    case ESP_RST_PANIC:
        return "panic";
    case ESP_RST_INT_WDT:
        return "interrupt_watchdog";
    case ESP_RST_TASK_WDT:
        return "task_watchdog";
    case ESP_RST_WDT:
        return "watchdog";
    case ESP_RST_DEEPSLEEP:
        return "deepsleep";
    case ESP_RST_BROWNOUT:
        return "brownout";
    case ESP_RST_SDIO:
        return "sdio";
    default:
        return "unknown";
    }
}

static void init_boot_diagnostics(void)
{
    s_boot_count = 0u;
    s_boot_count_persisted = false;
    s_reset_reason = reset_reason_name(esp_reset_reason());
    nvs_handle_t handle;
    esp_err_t err = nvs_open("egolink", NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "BOOT_DIAGNOSTICS_NVS_OPEN_FAIL err=%s reset_reason=%s", esp_err_to_name(err), s_reset_reason);
        return;
    }
    uint32_t boot_count = 0;
    err = nvs_get_u32(handle, "boot_count", &boot_count);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "BOOT_DIAGNOSTICS_NVS_READ_FAIL err=%s", esp_err_to_name(err));
        nvs_close(handle);
        return;
    }
    if (boot_count == UINT32_MAX) {
        ESP_LOGE(TAG, "BOOT_DIAGNOSTICS_NVS_COUNTER_EXHAUSTED");
        nvs_close(handle);
        return;
    }
    boot_count += 1;
    if (nvs_set_u32(handle, "boot_count", boot_count) == ESP_OK && nvs_commit(handle) == ESP_OK) {
        s_boot_count = boot_count;
        s_boot_count_persisted = true;
    } else {
        ESP_LOGW(TAG, "BOOT_DIAGNOSTICS_NVS_WRITE_FAIL");
    }
    nvs_close(handle);
    ESP_LOGI(TAG, "BOOT_DIAGNOSTICS reset_reason=%s boot_count=%" PRIu32, s_reset_reason, s_boot_count);
}

static safety_model_mock_state_t default_safety_mock_state(void)
{
    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
    return (safety_model_mock_state_t){
        .mode = EGO_SC_MODE_CHILD_SAFETY,
        .sos_pressed = false,
        .cancel_pressed = false,
        .wake_detected = false,
        .impact_detected = false,
        .gnss_fix_valid = true,
        .base_online = true,
        .upload_available = true,
        .signal_level = 3,
        .offline_seconds = 0.0f,
        .battery_percent = (float)power.battery_percent,
        .charging = power.charging,
        .privacy_mode = false,
        .camera_available = true,
        .microphone_available = true,
    };
}

static void log_safety_output(const char *label, const ego_sc_model_output_t *output)
{
    ESP_LOGI(
        TAG,
        "SAFETY_MODEL_%s version=%s risk=%s score=%.2f confidence=%.2f priority=%d action=%s evidence_mask=0x%08" PRIx32,
        label,
        safety_model_version(),
        safety_model_risk_type_name(output->risk_type),
        (double)output->risk_score,
        (double)output->confidence,
        output->priority,
        safety_model_action_name(output->recommended_action),
        output->evidence_mask);
}

static void log_tiny_safety_output(const char *label, const safety_model_tiny_result_t *result)
{
    ESP_LOGI(
        TAG,
        "TINY_SAFETY_DEMO name=%s model_id=%s model_version=%s harness=%s label=%s class=%u confidence=%.3f raw=%.3f margin=%.3f synthetic_only=%s safety_rule_required=%s dry_run=true",
        label,
        safety_model_tiny_model_id(),
        safety_model_tiny_model_version(),
        safety_model_tiny_harness_version(),
        result->state_label,
        (unsigned)result->class_index,
        (double)result->confidence,
        (double)result->raw_score,
        (double)result->score_margin,
        json_bool(result->synthetic_only),
        json_bool(result->safety_rule_required));
}

static void configure_tiny_demo_input(const char *demo_name, ego_sc_model_input_t *input)
{
    input->activity = EGO_SC_ACTIVITY_WALKING;
    input->activity_confidence = 0.892f;
    input->impact_score = 0.058f;
    input->fall_score = 0.0f;
    input->stationary_seconds = 11.58f;
    input->device_worn = 1;
    input->speech_score = 0.0f;
    input->distress_score = 0.0f;
    input->impact_sound_score = 0.0f;
    input->unknown_loud_sound_score = 0.029f;
    input->audio_quality_score = 0.90f;
    input->gnss_fix_valid = true;
    input->speed_mps = 0.0f;
    input->outside_safe_zone = false;
    input->dwell_seconds = 174.8f;
    input->route_deviation_m = 0.0f;
    input->gnss_quality_score = 0.85f;
    input->connectivity_score = 0.807f;
    input->base_online = true;
    input->upload_available = true;
    input->signal_level = 3;
    input->offline_seconds = 0.0f;
    input->battery_percent = 89.1f;
    input->charging = false;
    input->privacy_mode = false;
    input->camera_available = true;
    input->microphone_available = true;
    input->recent_risk_count_5m = 0;
    input->last_user_response = EGO_SC_RESPONSE_NONE;
    input->seconds_since_last_contact = 0.0f;
    input->sos_pressed = false;
    input->cancel_pressed = false;
    input->audio_clip_available = false;
    input->single_image_available = false;
    input->fresh_gnss_available = true;
    input->imu_window_available = true;

    if (strcmp(demo_name, "uncertain") == 0) {
        input->impact_score = 0.307f;
        input->fall_score = 0.237f;
        input->stationary_seconds = 19.5f;
        input->activity_confidence = 0.564f;
        input->distress_score = 0.243f;
        input->impact_sound_score = 0.200f;
        input->unknown_loud_sound_score = 0.421f;
        input->dwell_seconds = 245.7f;
        input->connectivity_score = 0.688f;
        input->offline_seconds = 161.0f;
        input->battery_percent = 81.2f;
        input->recent_risk_count_5m = 1;
    } else if (strcmp(demo_name, "needs_check") == 0) {
        input->activity = EGO_SC_ACTIVITY_FALL_CANDIDATE;
        input->impact_score = 0.510f;
        input->fall_score = 0.597f;
        input->stationary_seconds = 32.5f;
        input->activity_confidence = 0.716f;
        input->distress_score = 0.272f;
        input->impact_sound_score = 0.440f;
        input->unknown_loud_sound_score = 0.201f;
        input->dwell_seconds = 276.2f;
        input->connectivity_score = 0.518f;
        input->offline_seconds = 245.8f;
        input->battery_percent = 78.5f;
        input->recent_risk_count_5m = 1;
    } else if (strcmp(demo_name, "possible_risk") == 0) {
        input->activity = EGO_SC_ACTIVITY_FALL_CANDIDATE;
        input->impact_score = 0.903f;
        input->fall_score = 0.806f;
        input->stationary_seconds = 90.6f;
        input->activity_confidence = 0.878f;
        input->distress_score = 0.601f;
        input->impact_sound_score = 0.757f;
        input->unknown_loud_sound_score = 0.319f;
        input->dwell_seconds = 429.1f;
        input->connectivity_score = 0.403f;
        input->offline_seconds = 404.2f;
        input->battery_percent = 63.5f;
        input->recent_risk_count_5m = 2;
    } else if (strcmp(demo_name, "sos") == 0) {
        input->sos_pressed = true;
    } else if (strcmp(demo_name, "cancel") == 0) {
        input->cancel_pressed = true;
    }
}

static void run_tiny_safety_self_test(void)
{
    safety_model_tiny_self_test_result_t result;
    bool ok = safety_model_tiny_self_test(&result);
    ESP_LOGI(
        TAG,
        "TINY_SAFETY_SELFTEST result=%s model_id=%s model_version=%s harness=%s vectors=%u passed=%u failed=%u first_failed=%u synthetic_only=true dry_run=true",
        ok ? "pass" : "fail",
        safety_model_tiny_model_id(),
        safety_model_tiny_model_version(),
        safety_model_tiny_harness_version(),
        (unsigned)result.vector_count,
        (unsigned)result.passed_count,
        (unsigned)result.failed_count,
        (unsigned)result.first_failed_index);
}

static void run_tiny_safety_demo(const char *demo_name)
{
    if (strcmp(demo_name, "normal") != 0 && strcmp(demo_name, "uncertain") != 0 &&
        strcmp(demo_name, "needs_check") != 0 && strcmp(demo_name, "possible_risk") != 0 &&
        strcmp(demo_name, "sos") != 0 && strcmp(demo_name, "cancel") != 0) {
        ESP_LOGW(TAG, "TINY_SAFETY_CLI_UNKNOWN_DEMO name=%s", demo_name);
        return;
    }

    safety_model_mock_state_t state = default_safety_mock_state();
    ego_sc_model_input_t input;
    safety_model_tiny_result_t result;

    if (!safety_model_input_from_mock_state(&state, &input)) {
        ESP_LOGE(TAG, "TINY_SAFETY_DEMO_INPUT_FAIL name=%s", demo_name);
        return;
    }
    configure_tiny_demo_input(demo_name, &input);
    if (!safety_model_tiny_predict_input(&input, &result)) {
        ESP_LOGE(TAG, "TINY_SAFETY_DEMO_FAIL name=%s", demo_name);
        return;
    }
    log_tiny_safety_output(demo_name, &result);
}

static void run_safety_demo(const char *demo_name)
{
    safety_model_mock_state_t state = default_safety_mock_state();
    ego_sc_model_input_t input;
    ego_sc_model_output_t output;

    if (strcmp(demo_name, "sos") == 0) {
        state.sos_pressed = true;
    } else if (strcmp(demo_name, "impact") == 0) {
        state.impact_detected = true;
    } else if (strcmp(demo_name, "normal") != 0) {
        ESP_LOGW(TAG, "SAFETY_MODEL_CLI_UNKNOWN_DEMO name=%s", demo_name);
        return;
    }

    if (!safety_model_input_from_mock_state(&state, &input) || !safety_model_evaluate(&input, &output)) {
        ESP_LOGE(TAG, "SAFETY_MODEL_DEMO_FAIL name=%s", demo_name);
        return;
    }
    log_safety_output(demo_name, &output);
}

static void handle_safety_cli_line(const char *line)
{
    if (strcmp(line, "safety status") == 0) {
        ESP_LOGI(TAG, "SAFETY_MODEL_STATUS version=%s mock=true", safety_model_version());
    } else if (strcmp(line, "safety tiny status") == 0) {
        ESP_LOGI(
            TAG,
            "TINY_SAFETY_STATUS model_id=%s model_version=%s harness=%s features=%u classes=%u synthetic_only=true dry_run=true external_actions=false",
            safety_model_tiny_model_id(),
            safety_model_tiny_model_version(),
            safety_model_tiny_harness_version(),
            (unsigned)safety_model_tiny_feature_count(),
            (unsigned)safety_model_tiny_class_count());
    } else if (strcmp(line, "safety tiny selftest") == 0) {
        run_tiny_safety_self_test();
    } else if (strncmp(line, "safety tiny demo ", 17) == 0) {
        run_tiny_safety_demo(line + 17);
    } else if (strcmp(line, "safety demo normal") == 0) {
        run_safety_demo("normal");
    } else if (strcmp(line, "safety demo sos") == 0) {
        run_safety_demo("sos");
    } else if (strcmp(line, "safety demo impact") == 0) {
        run_safety_demo("impact");
    } else if (strncmp(line, "safety", 6) == 0) {
        ESP_LOGW(TAG, "SAFETY_MODEL_CLI_UNKNOWN command=%s", line);
    }
}

static void safety_cli_task(void *arg)
{
    (void)arg;
    char line[64];
    size_t pos = 0;
    while (true) {
        int ch = getchar();
        if (ch < 0) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (ch == '\r' || ch == '\n') {
            if (pos > 0) {
                line[pos] = '\0';
                handle_safety_cli_line(line);
                pos = 0;
            }
        } else if ((ch == '\b' || ch == 127) && pos > 0) {
            pos--;
        } else if (pos + 1 < sizeof(line)) {
            line[pos++] = (char)ch;
        }
    }
}

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static uint32_t next_seq(void)
{
    portENTER_CRITICAL(&s_seq_mux);
    uint32_t seq = ++s_seq;
    portEXIT_CRITICAL(&s_seq_mux);
    return seq;
}

static void append_test_run_id_and_close_json(char *buffer, size_t buffer_size)
{
    const char *test_run_id = CONFIG_EGOLINK_TEST_RUN_ID;
    if (test_run_id[0] != '\0') {
        size_t len = strlen(buffer);
        if (len < buffer_size) {
            snprintf(buffer + len, buffer_size - len, ",\"test_run_id\":\"%s\"", test_run_id);
        }
    }
    size_t len = strlen(buffer);
    if (len < buffer_size) {
        snprintf(buffer + len, buffer_size - len, "}");
    }
}

static int refresh_wifi_rssi(void)
{
    wifi_ap_record_t ap_info;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        s_last_rssi = ap_info.rssi;
    }
    return s_last_rssi;
}

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
static bool message_hub_expected_host_is_valid(void)
{
    const char *host = CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST;
    size_t length = strlen(host);
    if (length == 0u || length > 253u || host[0] == '.' || host[length - 1u] == '.') {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        char ch = host[index];
        bool valid = (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '.' || ch == '-';
        if (!valid) {
            return false;
        }
    }
    return true;
}

static bool message_hub_bearer_token_is_valid(void)
{
    const char *token = CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN;
    size_t length = strlen(token);
    if (length == 0u || length > MESSAGE_HUB_BEARER_TOKEN_MAX_BYTES || token[0] == '<') {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        unsigned char ch = (unsigned char)token[index];
        bool valid = (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
                     (ch >= '0' && ch <= '9') || ch == '.' || ch == '_' || ch == '~' ||
                     ch == '+' || ch == '/' || ch == '-' || ch == '=';
        if (!valid) {
            return false;
        }
    }
    return true;
}

static const char *message_hub_transport_configuration_error(void)
{
    static const char https_prefix[] = "https://";
    const char *base_url = CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL;
    const char *expected_host = CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST;
    if (!message_hub_expected_host_is_valid()) {
        return "expected_tls_host_invalid";
    }
    if (strncmp(base_url, https_prefix, sizeof(https_prefix) - 1u) != 0) {
        return "plaintext_or_invalid_scheme";
    }
    const char *authority = base_url + sizeof(https_prefix) - 1u;
    size_t host_length = strlen(expected_host);
    if (strncmp(authority, expected_host, host_length) != 0) {
        return "unexpected_tls_host";
    }
    const char *suffix = authority + host_length;
    if (!(suffix[0] == '\0' || (suffix[0] == '/' && suffix[1] == '\0'))) {
        return "tls_base_url_must_be_host_only";
    }
    if (!message_hub_bearer_token_is_valid()) {
        return "bearer_token_missing_or_invalid";
    }
#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
    /*
     * The current SIM7670 AT HTTP component has no reviewed API for binding a
     * CA trust store and enforcing hostname verification. Do not send a
     * bearer token or payload through that path merely because its URL says
     * https. A later modem-specific slice must remove this stop only after it
     * implements and tests both checks.
     */
    return "sim7670_tls_peer_verification_unavailable";
#else
    return NULL;
#endif
}

static esp_err_t message_hub_http_event_handler(esp_http_client_event_t *event)
{
    if (event->event_id != HTTP_EVENT_ON_DATA || event->user_data == NULL || event->data == NULL) {
        return ESP_OK;
    }

    http_response_buffer_t *response = (http_response_buffer_t *)event->user_data;
    if (response->buffer == NULL || response->capacity == 0) {
        return ESP_OK;
    }
    if (response->length + (size_t)event->data_len >= response->capacity) {
        ESP_LOGW(TAG, "MESSAGE_HUB_RESPONSE_TRUNCATED len=%d capacity=%u", event->data_len, (unsigned)response->capacity);
        return ESP_OK;
    }
    memcpy(response->buffer + response->length, event->data, (size_t)event->data_len);
    response->length += (size_t)event->data_len;
    response->buffer[response->length] = '\0';
    return ESP_OK;
}

static bool build_message_hub_url(char *buffer, size_t buffer_size, const char *path)
{
    const char *base_url = CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL;
    size_t base_len = strlen(base_url);
    bool base_has_slash = base_len > 0 && base_url[base_len - 1] == '/';
    bool path_has_slash = path[0] == '/';
    const char *separator = (base_has_slash || path_has_slash) ? "" : "/";
    const char *normalized_path = (base_has_slash && path_has_slash) ? path + 1 : path;
    int written = snprintf(buffer, buffer_size, "%s%s%s", base_url, separator, normalized_path);
    return written >= 0 && (size_t)written < buffer_size;
}

static bool message_hub_request_with_content_type(
    esp_http_client_method_t method,
    const char *path,
    const char *payload,
    const char *content_type,
    char *response_buffer,
    size_t response_size,
    int *status_code)
{
    char url[256];
    if (!build_message_hub_url(url, sizeof(url), path)) {
        ESP_LOGE(TAG, "MESSAGE_HUB_HTTPS_URL_REJECTED path=%s", path);
        return false;
    }

    http_response_buffer_t response = {
        .buffer = response_buffer,
        .capacity = response_size,
        .length = 0,
    };
    if (response.buffer != NULL && response.capacity > 0) {
        response.buffer[0] = '\0';
    }

    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 8000,
        .event_handler = message_hub_http_event_handler,
        .user_data = &response,
        .transport_type = HTTP_TRANSPORT_OVER_SSL,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .skip_cert_common_name_check = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        ESP_LOGE(TAG, "MESSAGE_HUB_HTTP_INIT_FAIL path=%s", path);
        return false;
    }

    esp_http_client_set_method(client, method);
    char auth_header[MESSAGE_HUB_BEARER_TOKEN_MAX_BYTES + sizeof("Bearer ")];
    snprintf(auth_header, sizeof(auth_header), "Bearer %s", CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN);
    esp_err_t header_err = esp_http_client_set_header(client, "Authorization", auth_header);
    memset(auth_header, 0, sizeof(auth_header));
    if (header_err != ESP_OK) {
        ESP_LOGE(TAG, "MESSAGE_HUB_HTTPS_AUTH_HEADER_REJECTED path=%s", path);
        esp_http_client_cleanup(client);
        return false;
    }
    if (payload != NULL) {
        esp_http_client_set_header(client, "Content-Type", content_type ? content_type : "application/json");
        esp_http_client_set_post_field(client, payload, (int)strlen(payload));
    }

    esp_err_t err = esp_http_client_perform(client);
    int http_status = esp_http_client_get_status_code(client);
    if (status_code != NULL) {
        *status_code = http_status;
    }
    esp_http_client_cleanup(client);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MESSAGE_HUB_HTTP_FAIL path=%s err=%s", path, esp_err_to_name(err));
        return false;
    }
    if (http_status < 200 || http_status >= 300) {
        ESP_LOGW(TAG, "MESSAGE_HUB_HTTP_STATUS path=%s status=%d", path, http_status);
        return false;
    }
    return true;
}

static bool message_hub_request(
    esp_http_client_method_t method,
    const char *path,
    const char *payload,
    char *response_buffer,
    size_t response_size,
    int *status_code)
{
    return message_hub_request_with_content_type(
        method,
        path,
        payload,
        "application/json",
        response_buffer,
        response_size,
        status_code);
}

static bool message_hub_post_raw(const char *path, const char *frame, int *status_code)
{
    return message_hub_request_with_content_type(
        HTTP_METHOD_POST,
        path,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
        NULL,
        0,
        status_code);
}

static bool message_hub_post_json(const char *path, const char *payload, const char *label, uint32_t seq)
{
    int status = 0;
    bool ok = message_hub_request(HTTP_METHOD_POST, path, payload, NULL, 0, &status);
    if (ok) {
        ESP_LOGI(TAG, "MESSAGE_HUB_%s_OK seq=%" PRIu32 " status=%d path=%s", label, seq, status, path);
    } else {
        ESP_LOGE(TAG, "MESSAGE_HUB_%s_FAIL seq=%" PRIu32 " status=%d path=%s", label, seq, status, path);
    }
    return ok;
}

static void message_hub_register_device(void)
{
    char payload[256];
    snprintf(
        payload,
        sizeof(payload),
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"fw_version\":\"%s\","
        "\"hw_target\":\"waveshare_esp32s3_sim7670g_4g\","
        "\"uplink_transport\":\"http_message_hub\"}",
        CONFIG_EGOLINK_DEVICE_ID,
        CONFIG_EGOLINK_FW_VERSION);

    int status = 0;
    bool ok = message_hub_request(HTTP_METHOD_POST, "/api/v1/devices/register", payload, NULL, 0, &status);
    if (ok) {
        ESP_LOGI(TAG, "MESSAGE_HUB_REGISTER_OK status=%d", status);
    } else {
        ESP_LOGE(TAG, "MESSAGE_HUB_REGISTER_FAIL status=%d", status);
    }
}

static void build_ack_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
    const char *status,
    const char *message)
{
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"ack\","
        "\"fw_version\":\"%s\","
        "\"cmd_id\":\"%s\","
        "\"status\":\"%s\","
        "\"message\":\"%s\"",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        cmd_id,
        status,
        message);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static void message_hub_ack_command(const char *cmd_id, const char *status, const char *message)
{
    char path[192];
    char payload[512];
    uint32_t seq = next_seq();
    snprintf(
        path,
        sizeof(path),
        "/api/v1/devices/%s/commands/%s/ack",
        CONFIG_EGOLINK_DEVICE_ID,
        cmd_id);
    build_ack_payload(payload, sizeof(payload), seq, cmd_id, status, message);
    (void)message_hub_post_json(path, payload, "COMMAND_ACK", seq);
}

#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
static const char *message_hub_location_ack_message(void)
{
#if CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED
    return "firmware uploaded SIM7670G GNSS location_report and cell location_observation";
#elif CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    return "firmware uploaded SIM7670G GNSS location_report";
#else
    return "firmware uploaded location_report scaffold";
#endif
}

static const char *message_hub_wifi_location_ack_message(void)
{
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    return "firmware uploaded SIM7670G GNSS location_report over Wi-Fi";
#else
    return "firmware uploaded location_report scaffold over Wi-Fi";
#endif
}

static void build_location_report_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
    const sim7670_gnss_report_t *gnss,
    bool gnss_query_ok)
{
    char lat[32];
    char lon[32];
    char altitude[32];
    char speed[32];
    char course[32];
    char pdop[32];
    char hdop[32];
    char vdop[32];
    char satellites[16];
    char raw_command[SIM7670_GNSS_RAW_COMMAND_MAX * 2];
    char raw_response[SIM7670_GNSS_RAW_RESPONSE_MAX * 2];
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    sim7670_gnss_report_t fallback;
    if (gnss == NULL) {
        sim7670_gnss_report_init(&fallback);
        gnss = &fallback;
    }
    const char *source = "sim7670g_firmware_gnss";
    const char *gnss_source = "sim7670g_uart_at";
    const char *gnss_driver = "uart_at";
    const char *state = gnss->gnss_state;
    const char *source_status = gnss->source_status;
    bool fix = gnss->fix;
    bool lat_valid = gnss->lat_valid;
    bool lon_valid = gnss->lon_valid;
    bool altitude_valid = gnss->altitude_valid;
    bool speed_valid = gnss->speed_valid;
    bool course_valid = gnss->course_valid;
    bool pdop_valid = gnss->pdop_valid;
    bool hdop_valid = gnss->hdop_valid;
    bool vdop_valid = gnss->vdop_valid;
    bool satellites_valid = gnss->satellites_valid;
    double lat_value = gnss->lat;
    double lon_value = gnss->lon;
    double altitude_value = gnss->altitude_m;
    double speed_value = gnss->speed_mps;
    double course_value = gnss->course_deg;
    double pdop_value = gnss->pdop;
    double hdop_value = gnss->hdop;
    double vdop_value = gnss->vdop;
    int satellites_value = gnss->satellites;
    const char *utc_date = gnss->utc_date;
    const char *utc_time = gnss->utc_time;
    json_escape_summary(raw_command, sizeof(raw_command), gnss->raw_command);
    json_escape_summary(raw_response, sizeof(raw_response), gnss->raw_response);
#else
    (void)gnss;
    (void)gnss_query_ok;
    const char *source = "firmware_gnss_scaffold";
    const char *gnss_source = "sim7670g_scaffold";
    const char *gnss_driver = "not_integrated";
    const char *state = "driver_not_integrated";
    const char *source_status = "unverified";
    bool fix = false;
    bool lat_valid = false;
    bool lon_valid = false;
    bool altitude_valid = false;
    bool speed_valid = false;
    bool course_valid = false;
    bool pdop_valid = false;
    bool hdop_valid = false;
    bool vdop_valid = false;
    bool satellites_valid = true;
    double lat_value = 0.0;
    double lon_value = 0.0;
    double altitude_value = 0.0;
    double speed_value = 0.0;
    double course_value = 0.0;
    double pdop_value = 0.0;
    double hdop_value = 0.0;
    double vdop_value = 0.0;
    int satellites_value = 0;
    const char *utc_date = "";
    const char *utc_time = "";
    raw_command[0] = '\0';
    raw_response[0] = '\0';
#endif
    json_number_or_null(lat, sizeof(lat), lat_valid, lat_value, "%.7f");
    json_number_or_null(lon, sizeof(lon), lon_valid, lon_value, "%.7f");
    json_number_or_null(altitude, sizeof(altitude), altitude_valid, altitude_value, "%.2f");
    json_number_or_null(speed, sizeof(speed), speed_valid, speed_value, "%.3f");
    json_number_or_null(course, sizeof(course), course_valid, course_value, "%.2f");
    json_number_or_null(pdop, sizeof(pdop), pdop_valid, pdop_value, "%.2f");
    json_number_or_null(hdop, sizeof(hdop), hdop_valid, hdop_value, "%.2f");
    json_number_or_null(vdop, sizeof(vdop), vdop_valid, vdop_value, "%.2f");
    json_int_or_null(satellites, sizeof(satellites), satellites_valid, satellites_value);
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"boot_count\":%" PRIu32 ","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"event\","
        "\"event_type\":\"location_report\","
        "\"priority\":\"normal\","
        "\"fw_version\":\"%s\","
        "\"source\":\"%s\","
        "\"source_status\":\"%s\","
        "\"fix\":%s,"
        "\"gnss_state\":\"%s\","
        "\"gnss_source\":\"%s\","
        "\"gnss_driver\":\"%s\","
        "\"gnss_query_ok\":%s,"
        "\"lat\":%s,"
        "\"lon\":%s,"
        "\"altitude_m\":%s,"
        "\"speed_mps\":%s,"
        "\"course_deg\":%s,"
        "\"pdop\":%s,"
        "\"hdop\":%s,"
        "\"vdop\":%s,"
        "\"satellites\":%s,"
        "\"utc_date\":\"%s\","
        "\"utc_time\":\"%s\","
        "\"raw_command\":\"%s\","
        "\"raw_response\":\"%s\","
        "\"location_request_cmd_id\":\"%s\","
        "\"payload\":{\"gnss\":{\"fix\":%s,"
        "\"state\":\"%s\","
        "\"lat\":%s,"
        "\"lon\":%s,"
        "\"altitude_m\":%s,"
        "\"speed_mps\":%s,"
        "\"course_deg\":%s,"
        "\"pdop\":%s,"
        "\"hdop\":%s,"
        "\"vdop\":%s,"
        "\"satellites\":%s,"
        "\"utc_date\":\"%s\","
        "\"utc_time\":\"%s\","
        "\"source\":\"%s\","
        "\"source_status\":\"%s\"}}",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        s_boot_count,
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        source,
        source_status,
        json_bool(fix),
        state,
        gnss_source,
        gnss_driver,
        json_bool(gnss_query_ok),
        lat,
        lon,
        altitude,
        speed,
        course,
        pdop,
        hdop,
        vdop,
        satellites,
        utc_date,
        utc_time,
        raw_command,
        raw_response,
        cmd_id,
        json_bool(fix),
        state,
        lat,
        lon,
        altitude,
        speed,
        course,
        pdop,
        hdop,
        vdop,
        satellites,
        utc_date,
        utc_time,
        source,
        source_status);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static bool message_hub_publish_location_report(const char *cmd_id)
{
    char path[160];
    char payload[3072];
    uint32_t seq = next_seq();
    sim7670_gnss_report_t gnss;
    sim7670_gnss_report_init(&gnss);
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    bool gnss_query_ok = sim7670_gnss_request_location(&gnss);
#else
    bool gnss_query_ok = false;
#endif
    snprintf(path, sizeof(path), "/api/v1/devices/%s/telemetry", CONFIG_EGOLINK_DEVICE_ID);
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "location_report");
    platform_power_mark("UPLOAD_LOCATION", "message_hub_http");
    build_location_report_payload(payload, sizeof(payload), seq, cmd_id, &gnss, gnss_query_ok);
    bool ok = message_hub_post_json(path, payload, "LOCATION_REPORT", seq);
    platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, ok ? "location_http_ok" : "location_http_fail");
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "location_report_done");
    return ok;
}
#endif

static void message_hub_poll_commands(void)
{
    char path[160];
    char response[1536];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/commands/poll", CONFIG_EGOLINK_DEVICE_ID);

    int status = 0;
    if (!message_hub_request(HTTP_METHOD_GET, path, NULL, response, sizeof(response), &status)) {
        ESP_LOGW(TAG, "MESSAGE_HUB_COMMAND_POLL_FAIL status=%d", status);
        return;
    }

    cJSON *root = cJSON_Parse(response);
    if (root == NULL) {
        ESP_LOGW(TAG, "MESSAGE_HUB_COMMAND_POLL_PARSE_FAIL");
        return;
    }
    cJSON *commands = cJSON_GetObjectItemCaseSensitive(root, "commands");
    if (!cJSON_IsArray(commands)) {
        cJSON_Delete(root);
        return;
    }

    int ack_count = 0;
    cJSON *command = NULL;
    cJSON_ArrayForEach(command, commands)
    {
        cJSON *cmd_id = cJSON_GetObjectItemCaseSensitive(command, "cmd_id");
        if (!cJSON_IsString(cmd_id) || cmd_id->valuestring == NULL) {
            continue;
        }
        cJSON *cmd = cJSON_GetObjectItemCaseSensitive(command, "cmd");
        const char *cmd_name = cJSON_IsString(cmd) && cmd->valuestring != NULL ? cmd->valuestring : "unknown";
        ESP_LOGI(TAG, "MESSAGE_HUB_COMMAND_RECEIVED cmd_id=%s cmd=%s", cmd_id->valuestring, cmd_name);
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
        if (strcmp(cmd_name, "request_location") == 0) {
            bool location_ok = message_hub_publish_location_report(cmd_id->valuestring);
            message_hub_ack_command(
                cmd_id->valuestring,
                location_ok ? "ok" : "error",
                location_ok ? message_hub_wifi_location_ack_message() : "location_report upload failed");
            ack_count++;
            continue;
        }
#endif
        message_hub_ack_command(cmd_id->valuestring, "ok", "firmware acknowledged command");
        ack_count++;
    }
    ESP_LOGI(TAG, "MESSAGE_HUB_COMMAND_POLL_OK ack_count=%d", ack_count);
    cJSON_Delete(root);
}
#endif

static void build_lte_observation_fragment(char *buffer, size_t buffer_size)
{
    if (buffer == NULL || buffer_size == 0) {
        return;
    }
    buffer[0] = '\0';
#if CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
    sim7670_lte_report_t lte;
    sim7670_lte_report_init(&lte);
    bool lte_query_ok = sim7670_lte_query_status(&lte);

    char rssi[16];
    char rsrp[16];
    char rsrq[16];
    char sinr[16];
    char operator_name[SIM7670_LTE_OPERATOR_MAX * 2];
    char rat[SIM7670_LTE_RAT_MAX * 2];
    char mcc[SIM7670_LTE_ID_MAX * 2];
    char mnc[SIM7670_LTE_ID_MAX * 2];
    char tac[SIM7670_LTE_ID_MAX * 2];
    char cell_id[SIM7670_LTE_ID_MAX * 2];
    char sim_state[SIM7670_LTE_STATUS_MAX * 2];
    char registration_state[SIM7670_LTE_STATUS_MAX * 2];
    char pdp_state[SIM7670_LTE_STATUS_MAX * 2];
    char apn_state[SIM7670_LTE_STATUS_MAX * 2];
    char assigned_ip[SIM7670_LTE_IP_MAX * 2];
    char reason_code[SIM7670_LTE_STATUS_MAX * 2];
    char raw_command[SIM7670_LTE_RAW_COMMAND_MAX * 2];
    char raw_response[SIM7670_LTE_RAW_RESPONSE_MAX * 2];

    json_int_or_null(rssi, sizeof(rssi), lte.rssi_valid, lte.rssi);
    json_int_or_null(rsrp, sizeof(rsrp), lte.rsrp_valid, lte.rsrp);
    json_int_or_null(rsrq, sizeof(rsrq), lte.rsrq_valid, lte.rsrq);
    json_int_or_null(sinr, sizeof(sinr), lte.sinr_valid, lte.sinr);
    json_escape_summary(operator_name, sizeof(operator_name), lte.operator_name);
    json_escape_summary(rat, sizeof(rat), lte.rat);
    json_escape_summary(mcc, sizeof(mcc), lte.mcc);
    json_escape_summary(mnc, sizeof(mnc), lte.mnc);
    json_escape_summary(tac, sizeof(tac), lte.tac);
    json_escape_summary(cell_id, sizeof(cell_id), lte.cell_id);
    json_escape_summary(sim_state, sizeof(sim_state), lte.sim_state);
    json_escape_summary(registration_state, sizeof(registration_state), lte.registration_state);
    json_escape_summary(pdp_state, sizeof(pdp_state), lte.pdp_state);
    json_escape_summary(apn_state, sizeof(apn_state), lte.apn_state);
    json_escape_summary(assigned_ip, sizeof(assigned_ip), lte.assigned_ip);
    json_escape_summary(reason_code, sizeof(reason_code), lte.reason_code);
    json_escape_summary(raw_command, sizeof(raw_command), lte.raw_command);
    json_escape_summary(raw_response, sizeof(raw_response), lte.raw_response);

    snprintf(
        buffer,
        buffer_size,
        ",\"cell\":{\"rat\":\"%s\","
        "\"operator\":\"%s\","
        "\"mcc\":\"%s\","
        "\"mnc\":\"%s\","
        "\"tac\":\"%s\","
        "\"cell_id\":\"%s\","
        "\"rssi\":%s,"
        "\"rsrp\":%s,"
        "\"rsrq\":%s,"
        "\"sinr\":%s,"
        "\"sim_state\":\"%s\","
        "\"registration_state\":\"%s\","
        "\"pdp_state\":\"%s\","
        "\"reason_code\":\"%s\"},"
        "\"lte\":{\"driver\":\"%s\","
        "\"query_ok\":%s,"
        "\"uart_ready\":%s,"
        "\"at_ok\":%s,"
        "\"sim_ready\":%s,"
        "\"registered\":%s,"
        "\"attached\":%s,"
        "\"pdp_active\":%s,"
        "\"ip_valid\":%s,"
        "\"sim_state\":\"%s\","
        "\"registration_state\":\"%s\","
        "\"apn_state\":\"%s\","
        "\"pdp_state\":\"%s\","
        "\"assigned_ip\":\"%s\","
        "\"reason_code\":\"%s\","
        "\"raw_command\":\"%s\","
        "\"raw_response\":\"%s\"}",
        rat,
        operator_name,
        mcc,
        mnc,
        tac,
        cell_id,
        rssi,
        rsrp,
        rsrq,
        sinr,
        sim_state,
        registration_state,
        pdp_state,
        reason_code,
        sim7670_lte_backend_name(),
        json_bool(lte_query_ok),
        json_bool(lte.uart_ready),
        json_bool(lte.at_ok),
        json_bool(lte.sim_ready),
        json_bool(lte.registered),
        json_bool(lte.attached),
        json_bool(lte.pdp_active),
        json_bool(lte.ip_valid),
        sim_state,
        registration_state,
        apn_state,
        pdp_state,
        assigned_ip,
        reason_code,
        raw_command,
        raw_response);
#endif
}

static void build_lte_http_probe_lte_fragment(char *buffer, size_t buffer_size)
{
    if (buffer == NULL || buffer_size == 0) {
        return;
    }
    buffer[0] = '\0';
#if CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
    sim7670_lte_report_t lte;
    sim7670_lte_report_init(&lte);
    bool lte_query_ok = sim7670_lte_query_status(&lte);

    char rssi[16];
    char rsrp[16];
    char rsrq[16];
    char sinr[16];
    char rat[SIM7670_LTE_RAT_MAX * 2];
    char cell_id[SIM7670_LTE_ID_MAX * 2];
    char sim_state[SIM7670_LTE_STATUS_MAX * 2];
    char registration_state[SIM7670_LTE_STATUS_MAX * 2];
    char pdp_state[SIM7670_LTE_STATUS_MAX * 2];
    char apn_state[SIM7670_LTE_STATUS_MAX * 2];
    char assigned_ip[SIM7670_LTE_IP_MAX * 2];
    char reason_code[SIM7670_LTE_STATUS_MAX * 2];

    json_int_or_null(rssi, sizeof(rssi), lte.rssi_valid, lte.rssi);
    json_int_or_null(rsrp, sizeof(rsrp), lte.rsrp_valid, lte.rsrp);
    json_int_or_null(rsrq, sizeof(rsrq), lte.rsrq_valid, lte.rsrq);
    json_int_or_null(sinr, sizeof(sinr), lte.sinr_valid, lte.sinr);
    json_escape_summary(rat, sizeof(rat), lte.rat);
    json_escape_summary(cell_id, sizeof(cell_id), lte.cell_id);
    json_escape_summary(sim_state, sizeof(sim_state), lte.sim_state);
    json_escape_summary(registration_state, sizeof(registration_state), lte.registration_state);
    json_escape_summary(pdp_state, sizeof(pdp_state), lte.pdp_state);
    json_escape_summary(apn_state, sizeof(apn_state), lte.apn_state);
    json_escape_summary(assigned_ip, sizeof(assigned_ip), lte.assigned_ip);
    json_escape_summary(reason_code, sizeof(reason_code), lte.reason_code);

    snprintf(
        buffer,
        buffer_size,
        ",\"cell\":{\"rat\":\"%s\","
        "\"cell_id\":\"%s\","
        "\"rssi\":%s,"
        "\"rsrp\":%s,"
        "\"rsrq\":%s,"
        "\"sinr\":%s,"
        "\"registration_state\":\"%s\","
        "\"pdp_state\":\"%s\","
        "\"reason_code\":\"%s\"},"
        "\"lte\":{\"driver\":\"%s\","
        "\"query_ok\":%s,"
        "\"sim_state\":\"%s\","
        "\"registration_state\":\"%s\","
        "\"apn_state\":\"%s\","
        "\"pdp_state\":\"%s\","
        "\"assigned_ip\":\"%s\","
        "\"reason_code\":\"%s\"}",
        rat,
        cell_id,
        rssi,
        rsrp,
        rsrq,
        sinr,
        registration_state,
        pdp_state,
        reason_code,
        sim7670_lte_backend_name(),
        json_bool(lte_query_ok),
        sim_state,
        registration_state,
        apn_state,
        pdp_state,
        assigned_ip,
        reason_code);
#endif
}

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && \
    (CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || \
     CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED)
#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
static bool wait_for_lte_ready_for_http_probe(void)
{
    int waited_sec = 0;
    sim7670_lte_report_t lte;
    while (true) {
        sim7670_lte_report_init(&lte);
        bool query_ok = sim7670_lte_query_status(&lte);
        ESP_LOGI(
            TAG,
            "LTE_HTTP_PROBE_READY_CHECK query_ok=%s reason=%s registration=%s pdp=%s waited_sec=%d",
            query_ok ? "true" : "false",
            lte.reason_code,
            lte.registration_state,
            lte.pdp_state,
            waited_sec);
        if (query_ok && strcmp(lte.reason_code, "LTE_READY") == 0) {
            return true;
        }
        if (waited_sec >= CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC) {
            return false;
        }
        int delay_sec = CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_POLL_SEC;
        if (waited_sec + delay_sec > CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC) {
            delay_sec = CONFIG_EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC - waited_sec;
        }
        if (delay_sec <= 0) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(delay_sec * 1000));
        waited_sec += delay_sec;
    }
}
#endif

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED
static void build_lte_http_probe_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *phase,
    const sim7670_lte_http_probe_result_t *probe,
    bool include_result)
{
    sim7670_lte_http_probe_result_t fallback;
    if (probe == NULL) {
        sim7670_lte_http_probe_result_init(&fallback);
        probe = &fallback;
    }

    char status_code[16];
    char data_len[16];
    char action_elapsed_ms[16];
    char rtt_ms[16];
    char reason_code[SIM7670_LTE_HTTP_REASON_MAX * 2];
    char last_error_json[SIM7670_LTE_HTTP_REASON_MAX * 2 + 4];
    const char *effective_phase = phase ? phase : "unknown";
    const char *effective_reason = include_result ? probe->reason_code : "LTE_HTTP_ATTEMPTING";
    bool result_ok = include_result && strcmp(effective_reason, "LTE_HTTP_OK") == 0;

    json_int_or_null(status_code, sizeof(status_code), include_result && probe->status_code_valid, probe->status_code);
    json_int_or_null(data_len, sizeof(data_len), include_result && probe->data_len_valid, probe->data_len);
    json_int_or_null(
        action_elapsed_ms,
        sizeof(action_elapsed_ms),
        include_result && probe->action_elapsed_ms_valid,
        probe->action_elapsed_ms);
    json_int_or_null(rtt_ms, sizeof(rtt_ms), include_result && probe->action_elapsed_ms_valid, probe->action_elapsed_ms);
    json_escape_summary(reason_code, sizeof(reason_code), effective_reason);
    if (include_result && !result_ok) {
        snprintf(last_error_json, sizeof(last_error_json), "\"%s\"", reason_code);
    } else {
        snprintf(last_error_json, sizeof(last_error_json), "null");
    }

    build_lte_http_probe_lte_fragment(s_lte_http_probe_lte_fragment, sizeof(s_lte_http_probe_lte_fragment));
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"event\","
        "\"event_type\":\"lte_http_probe\","
        "\"priority\":\"normal\","
        "\"fw_version\":\"%s\","
        "\"source\":\"sim7670g_lte_http_probe\","
        "\"source_status\":\"%s\","
        "\"reset_reason\":\"%s\","
        "\"boot_count\":%" PRIu32 ","
        "\"boot_uptime_ms\":%" PRId64 ","
        "\"transport\":{\"type\":\"lte\","
        "\"rtt_ms\":%s,"
        "\"last_error\":%s},"
        "\"lte_http\":{\"phase\":\"%s\","
        "\"driver\":\"%s\","
        "\"reason_code\":\"%s\","
        "\"status_code\":%s,"
        "\"data_len\":%s,"
        "\"action_elapsed_ms\":%s}"
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        include_result ? (result_ok ? "observed" : "unverified") : "observed",
        s_reset_reason,
        s_boot_count,
        uptime_ms(),
        rtt_ms,
        last_error_json,
        effective_phase,
        sim7670_lte_http_backend_name(),
        reason_code,
        status_code,
        data_len,
        action_elapsed_ms,
        s_lte_http_probe_lte_fragment);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static bool publish_lte_http_probe_once(void)
{
    static char payload[4096];
    char path[160];
    char url[256];
    sim7670_lte_http_probe_result_t attempt_result;
    sim7670_lte_http_probe_result_t result_post_result;

    bool lte_ready = wait_for_lte_ready_for_http_probe();
    ESP_LOGI(TAG, "LTE_HTTP_PROBE_READY_RESULT ready=%s", lte_ready ? "true" : "false");

    snprintf(path, sizeof(path), "/api/v1/devices/%s/telemetry", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);

    uint32_t attempt_seq = next_seq();
    build_lte_http_probe_payload(payload, sizeof(payload), attempt_seq, "attempt", NULL, false);
    ESP_LOGI(TAG, "LTE_HTTP_PROBE_ATTEMPT_PAYLOAD_BYTES=%u", (unsigned)strlen(payload));
    bool attempt_ok =
        sim7670_lte_http_post_json(url, CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN, payload, &attempt_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_PROBE_ATTEMPT_DONE seq=%" PRIu32 " ok=%s reason=%s status=%d",
        attempt_seq,
        attempt_ok ? "true" : "false",
        attempt_result.reason_code,
        attempt_result.status_code);

    uint32_t result_seq = next_seq();
    build_lte_http_probe_payload(payload, sizeof(payload), result_seq, "result", &attempt_result, true);
    ESP_LOGI(TAG, "LTE_HTTP_PROBE_RESULT_PAYLOAD_BYTES=%u", (unsigned)strlen(payload));
    bool result_ok =
        sim7670_lte_http_post_json(url, CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN, payload, &result_post_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_PROBE_RESULT_DONE seq=%" PRIu32 " ok=%s first_reason=%s result_post_reason=%s status=%d",
        result_seq,
        result_ok ? "true" : "false",
        attempt_result.reason_code,
        result_post_result.reason_code,
        result_post_result.status_code);
    return attempt_ok && result_ok;
}

static bool publish_lte_http_probe_with_retries(void)
{
    int max_attempts = CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_MAX_ATTEMPTS;
    if (max_attempts < 1) {
        max_attempts = 1;
    }

    for (int attempt = 1; attempt <= max_attempts; ++attempt) {
        ESP_LOGI(
            TAG,
            "LTE_HTTP_PROBE_ROUND_START attempt=%d max_attempts=%d",
            attempt,
            max_attempts);
        bool ok = publish_lte_http_probe_once();
        ESP_LOGI(
            TAG,
            "LTE_HTTP_PROBE_ROUND_DONE attempt=%d ok=%s",
            attempt,
            ok ? "true" : "false");
        if (ok) {
            return true;
        }
        if (attempt < max_attempts && CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC > 0) {
            ESP_LOGI(
                TAG,
                "LTE_HTTP_PROBE_RETRY_DELAY attempt=%d delay_sec=%d",
                attempt,
                CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC);
            vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC * 1000));
        }
    }
    return false;
}

static void lte_http_probe_task(void *arg)
{
    (void)arg;
    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_probe");
    bool lte_probe_ok = publish_lte_http_probe_with_retries();
    platform_power_leave_state(
        PLATFORM_POWER_STATE_NETWORK_ATTACH,
        lte_probe_ok ? "lte_http_probe_ok" : "lte_http_probe_fail");
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_http_probe_done");
    vTaskDelete(NULL);
}
#endif

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED
static void set_lte_command_parse_status(const char *status)
{
    snprintf(s_lte_command_parse_status, sizeof(s_lte_command_parse_status), "%s", status ? status : "unknown");
}

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
static void lte_raw_outbox_copy_text(char *buffer, size_t buffer_size, const char *value, const char *fallback)
{
    if (buffer == NULL || buffer_size == 0) {
        return;
    }
    snprintf(buffer, buffer_size, "%s", value && value[0] != '\0' ? value : fallback);
}

static void lte_raw_outbox_record_drop(const char *reason)
{
    char reason_copy[64];
    lte_raw_outbox_copy_text(reason_copy, sizeof(reason_copy), reason, "unknown_drop");

    portENTER_CRITICAL(&s_lte_raw_outbox_mux);
    s_lte_raw_outbox.dropped_message_count += 1;
    memcpy(s_lte_raw_outbox.last_drop_reason, reason_copy, sizeof(s_lte_raw_outbox.last_drop_reason));
    portEXIT_CRITICAL(&s_lte_raw_outbox_mux);
}

static void lte_raw_outbox_record_post_result(bool ok, const sim7670_lte_http_probe_result_t *result)
{
    const char *reason = result ? result->reason_code : "unknown_http_result";
    char error_reason[SIM7670_LTE_HTTP_REASON_MAX];
    if (!ok) {
        lte_raw_outbox_copy_text(error_reason, sizeof(error_reason), reason, "unknown_http_result");
    }

    portENTER_CRITICAL(&s_lte_raw_outbox_mux);
    s_lte_raw_outbox.post_attempt_count += 1;
    if (ok) {
        s_lte_raw_outbox.post_success_count += 1;
    } else {
        s_lte_raw_outbox.post_failure_count += 1;
        memcpy(s_lte_raw_outbox.last_error, error_reason, sizeof(s_lte_raw_outbox.last_error));
    }
    portEXIT_CRITICAL(&s_lte_raw_outbox_mux);
}

static void lte_raw_outbox_record_retry_result(bool ok)
{
    portENTER_CRITICAL(&s_lte_raw_outbox_mux);
    s_lte_raw_outbox.retry_attempt_count += 1;
    if (ok) {
        s_lte_raw_outbox.retry_success_count += 1;
    } else {
        s_lte_raw_outbox.retry_failure_count += 1;
    }
    portEXIT_CRITICAL(&s_lte_raw_outbox_mux);
}

static void lte_raw_outbox_snapshot(lte_raw_outbox_counters_t *snapshot)
{
    if (snapshot == NULL) {
        return;
    }
    portENTER_CRITICAL(&s_lte_raw_outbox_mux);
    *snapshot = s_lte_raw_outbox;
    portEXIT_CRITICAL(&s_lte_raw_outbox_mux);
    if (snapshot->last_drop_reason[0] == '\0') {
        lte_raw_outbox_copy_text(snapshot->last_drop_reason, sizeof(snapshot->last_drop_reason), "none", "none");
    }
    if (snapshot->last_error[0] == '\0') {
        lte_raw_outbox_copy_text(snapshot->last_error, sizeof(snapshot->last_error), "none", "none");
    }
}

typedef struct {
    const char *network_state;
    const char *network_last_error;
    uint32_t network_reconnect_count;
    const char *network_last_reconnect_reason;
    const char *cache_state;
    const char *cache_source_status;
    uint32_t cache_queued_message_count;
    uint32_t cache_oldest_message_age_ms;
    uint32_t cache_flush_attempt_count;
    uint32_t cache_flush_success_count;
    uint32_t cache_flush_failure_count;
} lte_reliability_evidence_fields_t;

static lte_reliability_evidence_fields_t lte_reliability_evidence_fields_default(
    const char *network_state,
    const char *network_last_error)
{
    lte_reliability_evidence_fields_t fields = {
        .network_state = network_state ? network_state : "unknown",
        .network_last_error = network_last_error ? network_last_error : "unknown",
        .network_reconnect_count = 0,
        .network_last_reconnect_reason = "",
        .cache_state = "volatile_outbox",
        .cache_source_status = "observed",
        .cache_queued_message_count = 0,
        .cache_oldest_message_age_ms = 0,
        .cache_flush_attempt_count = 0,
        .cache_flush_success_count = 0,
        .cache_flush_failure_count = 0,
    };
    return fields;
}

static lte_reliability_evidence_fields_t lte_reliability_evidence_fields_for_observation(
    const char *network_state,
    const char *network_last_error)
{
    lte_reliability_evidence_fields_t fields =
        lte_reliability_evidence_fields_default(network_state, network_last_error);
#if CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST
    fields.network_state = "reconnecting";
    fields.network_last_error = "LTE_HTTP_ACTION_FAILED";
    fields.network_reconnect_count = 1;
    fields.network_last_reconnect_reason = "pdp_reactivate";
    fields.cache_state = "store_forward";
    fields.cache_source_status = "observed";
    fields.cache_queued_message_count = 1;
    fields.cache_oldest_message_age_ms = 12000;
#endif
    return fields;
}

static lte_reliability_evidence_fields_t lte_reliability_evidence_fields_for_ack(void)
{
    lte_reliability_evidence_fields_t fields =
        lte_reliability_evidence_fields_default("ready", "none");
#if CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST
    fields.network_state = "ready_after_reconnect";
    fields.network_last_error = "none";
    fields.network_reconnect_count = 1;
    fields.network_last_reconnect_reason = "pdp_reactivate";
    fields.cache_state = "store_forward";
    fields.cache_source_status = "observed";
    fields.cache_flush_attempt_count = 1;
    fields.cache_flush_success_count = 1;
    fields.cache_flush_failure_count = 0;
#endif
    return fields;
}

static bool lte_raw_outbox_post_raw_with_retry(
    const char *url,
    const char *bearer_token,
    const char *frame,
    const char *content_type,
    const char *label,
    const char *cmd_id,
    uint32_t seq,
    sim7670_lte_http_probe_result_t *final_result)
{
    sim7670_lte_http_probe_result_t attempt_result;
    bool ok = sim7670_lte_http_post_raw(url, bearer_token, frame, content_type, &attempt_result);
    lte_raw_outbox_record_post_result(ok, &attempt_result);
    if (final_result != NULL) {
        *final_result = attempt_result;
    }
    if (ok) {
        return true;
    }

    for (int retry_index = 1; retry_index <= CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX; ++retry_index) {
        ESP_LOGW(
            TAG,
            "LTE_HTTP_RAW_POST_RETRY label=%s cmd_id=%s seq=%" PRIu32 " retry=%d initial_reason=%s",
            label ? label : "raw",
            cmd_id ? cmd_id : "none",
            seq,
            retry_index,
            attempt_result.reason_code);
        sim7670_lte_http_probe_result_t retry_result;
        bool retry_ok = sim7670_lte_http_post_raw(url, bearer_token, frame, content_type, &retry_result);
        lte_raw_outbox_record_post_result(retry_ok, &retry_result);
        lte_raw_outbox_record_retry_result(retry_ok);
        if (final_result != NULL) {
            *final_result = retry_result;
        }
        if (retry_ok) {
            return true;
        }
    }

    lte_raw_outbox_record_drop(
        CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX > 0
            ? "lte_http_post_failed_after_retry"
            : "lte_http_post_failed");
    return false;
}
#endif

typedef struct {
    char cmd_id[64];
    char cmd[48];
    char test_run_id[33];
    uint32_t sample_count;
    uint32_t interval_ms;
    bool sample_count_present;
    bool interval_ms_present;
    bool test_run_id_present;
    bool parameters_valid;
} lte_raw_command_t;

static uint32_t egolink_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t index = 0; index < length; ++index) {
        crc ^= (uint32_t)data[index];
        for (int bit = 0; bit < 8; ++bit) {
            uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static bool build_lte_raw_frame(
    char *buffer,
    size_t buffer_size,
    const char *frame_type,
    const char *frame_id,
    uint32_t seq,
    const char *payload)
{
    if (buffer == NULL || buffer_size == 0 || frame_type == NULL || frame_id == NULL || payload == NULL) {
        return false;
    }
    size_t payload_len = strlen(payload);
    uint32_t crc = egolink_crc32((const uint8_t *)payload, payload_len);
    int written = snprintf(
        buffer,
        buffer_size,
        "EGLK/1 type=%s id=%s seq=%" PRIu32 " len=%u crc32=%08" PRIX32 "\n"
        "content-type=text/x-egolink-kv\n\n"
        "%s",
        frame_type,
        frame_id,
        seq,
        (unsigned)payload_len,
        crc,
        payload);
    return written > 0 && (size_t)written < buffer_size;
}

static void imu_window_set_error(const char *reason)
{
    snprintf(s_imu_window_last_error, sizeof(s_imu_window_last_error), "%s", reason ? reason : "unknown");
}

static void imu_window_write_u32_le(uint8_t *output, uint32_t value)
{
    output[0] = (uint8_t)(value & 0xFFu);
    output[1] = (uint8_t)((value >> 8) & 0xFFu);
    output[2] = (uint8_t)((value >> 16) & 0xFFu);
    output[3] = (uint8_t)((value >> 24) & 0xFFu);
}

static bool imu_window_base64_encode(
    const uint8_t *input,
    size_t input_len,
    char *output,
    size_t output_size)
{
    static const char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    if (input == NULL || output == NULL) {
        return false;
    }
    size_t required = ((input_len + 2u) / 3u) * 4u;
    if (output_size <= required) {
        return false;
    }

    size_t out = 0;
    for (size_t index = 0; index < input_len; index += 3u) {
        size_t remaining = input_len - index;
        uint32_t triple = (uint32_t)input[index] << 16;
        if (remaining > 1u) {
            triple |= (uint32_t)input[index + 1u] << 8;
        }
        if (remaining > 2u) {
            triple |= input[index + 2u];
        }
        output[out++] = alphabet[(triple >> 18) & 0x3Fu];
        output[out++] = alphabet[(triple >> 12) & 0x3Fu];
        output[out++] = remaining > 1u ? alphabet[(triple >> 6) & 0x3Fu] : '=';
        output[out++] = remaining > 2u ? alphabet[triple & 0x3Fu] : '=';
    }
    output[out] = '\0';
    return true;
}

static void imu_window_pack_sample(uint32_t index, uint32_t offset_us, const platform_imu_sample_t *sample)
{
    uint8_t *record = &s_imu_window_binary[index * IMU_WINDOW_RECORD_BYTES];
    const int32_t values[6] = {
        sample->accel_mg_x,
        sample->accel_mg_y,
        sample->accel_mg_z,
        sample->gyro_mdps_x,
        sample->gyro_mdps_y,
        sample->gyro_mdps_z,
    };
    imu_window_write_u32_le(record, offset_us);
    for (size_t axis = 0; axis < 6u; ++axis) {
        imu_window_write_u32_le(&record[4u + (axis * 4u)], (uint32_t)values[axis]);
    }
}

static void imu_window_record_read_failure(imu_window_capture_result_t *result, const char *fallback_status)
{
    if (result == NULL || result->first_read_status[0] != '\0') {
        return;
    }
    platform_imu_snapshot_t snapshot;
    platform_imu_get_snapshot(&snapshot);
    result->first_read_error = snapshot.last_error;
    snprintf(
        result->first_read_status,
        sizeof(result->first_read_status),
        "%s",
        snapshot.backend_status != NULL ? snapshot.backend_status : fallback_status);
}

static bool capture_real_imu_window(imu_window_capture_result_t *result)
{
    if (result == NULL) {
        imu_window_set_error("capture_result_missing");
        return false;
    }
    memset(result, 0, sizeof(*result));
    memset(s_imu_window_binary, 0, sizeof(s_imu_window_binary));
    result->min_interval_us = UINT32_MAX;

    platform_imu_snapshot_t snapshot;
    platform_imu_get_snapshot(&snapshot);
    if (snapshot.backend != PLATFORM_IMU_BACKEND_QMI8658 || !snapshot.hardware_present || !snapshot.driver_enabled) {
        imu_window_set_error("real_qmi8658_unavailable");
        result->min_interval_us = 0;
        return false;
    }
    if (!platform_imu_capture_begin()) {
        result->measurement_stop_ok = platform_imu_capture_end();
        if (!result->measurement_stop_ok) {
            s_imu_window_service_failed_closed = true;
        }
        imu_window_set_error("capture_begin_failed");
        result->min_interval_us = 0;
        return false;
    }

    ESP_LOGI(
        TAG,
        "IMU_WINDOW_CAPTURE_START samples=%u interval_ms=%u warmup_samples=%u",
        (unsigned)IMU_WINDOW_SAMPLE_COUNT,
        (unsigned)IMU_WINDOW_INTERVAL_MS,
        (unsigned)IMU_WINDOW_WARMUP_SAMPLE_COUNT);
    bool warmup_ok = true;
    TickType_t warmup_wake = xTaskGetTickCount();
    for (uint32_t index = 0; index < IMU_WINDOW_WARMUP_SAMPLE_COUNT; ++index) {
        vTaskDelayUntil(&warmup_wake, pdMS_TO_TICKS(IMU_WINDOW_WARMUP_INTERVAL_MS));
        platform_imu_sample_t warmup_sample;
        if (!platform_imu_sample_real(&warmup_sample) || warmup_sample.sample_is_mock ||
            strcmp(warmup_sample.source, "qmi8658_i2c") != 0) {
            result->read_failure_count += 1u;
            imu_window_record_read_failure(result, "warmup_sample_rejected");
            imu_window_set_error("real_warmup_sample_failed");
            warmup_ok = false;
            break;
        }
        result->warmup_sample_count += 1u;
    }

    TickType_t last_wake = xTaskGetTickCount();
    if (warmup_ok) {
        vTaskDelayUntil(&last_wake, 1u);
    }
    uint64_t interval_sum_us = 0;
    uint32_t interval_count = 0;
    uint32_t previous_offset_us = 0;
    int64_t start_us = esp_timer_get_time();
    result->capture_start_uptime_us = (uint64_t)start_us;

    for (uint32_t index = 0; warmup_ok && index < IMU_WINDOW_SAMPLE_COUNT; ++index) {
        if (index > 0u) {
            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(IMU_WINDOW_INTERVAL_MS));
        }
        int64_t before_read_us = esp_timer_get_time();
        int64_t scheduled_us = start_us + ((int64_t)index * IMU_WINDOW_INTERVAL_US);
        if (before_read_us > scheduled_us + 5000) {
            result->deadline_miss_count += 1u;
        }

        platform_imu_sample_t sample;
        if (!platform_imu_sample_real(&sample)) {
            result->read_failure_count += 1u;
            imu_window_record_read_failure(result, "real_sample_read_failed");
            imu_window_set_error("real_sample_read_failed");
            break;
        }
        if (sample.sample_is_mock || strcmp(sample.source, "qmi8658_i2c") != 0) {
            result->mock_sample_count += 1u;
            imu_window_record_read_failure(result, "mock_or_unexpected_source_rejected");
            imu_window_set_error("mock_or_unexpected_source_rejected");
            break;
        }

        int64_t captured_us = esp_timer_get_time();
        int64_t offset_value = captured_us - start_us;
        if (offset_value < 0 || offset_value > UINT32_MAX) {
            imu_window_set_error("sample_offset_out_of_range");
            break;
        }
        uint32_t offset_us = (uint32_t)offset_value;
        if (index > 0u) {
            uint32_t interval_us = offset_us - previous_offset_us;
            if (interval_us < result->min_interval_us) {
                result->min_interval_us = interval_us;
            }
            if (interval_us > result->max_interval_us) {
                result->max_interval_us = interval_us;
            }
            interval_sum_us += interval_us;
            interval_count += 1u;
        }
        previous_offset_us = offset_us;
        imu_window_pack_sample(index, offset_us, &sample);
        result->captured_samples += 1u;
    }

    result->capture_end_uptime_us = (uint64_t)esp_timer_get_time();
    result->measurement_stop_ok = platform_imu_capture_end();
    if (!result->measurement_stop_ok) {
        s_imu_window_service_failed_closed = true;
    }
    if (interval_count > 0u) {
        result->mean_interval_us = (uint32_t)(interval_sum_us / interval_count);
    } else {
        result->min_interval_us = 0;
    }
    if (!result->measurement_stop_ok) {
        imu_window_set_error("capture_end_failed");
    } else if (result->first_read_status[0] != '\0') {
        snprintf(
            s_imu_window_last_error,
            sizeof(s_imu_window_last_error),
            "sample_failed:%s:%d",
            result->first_read_status,
            result->first_read_error);
    }

    bool ok = result->warmup_sample_count == IMU_WINDOW_WARMUP_SAMPLE_COUNT &&
              result->captured_samples == IMU_WINDOW_SAMPLE_COUNT && result->read_failure_count == 0u &&
              result->mock_sample_count == 0u && result->measurement_stop_ok;
    if (ok) {
        imu_window_set_error("none");
    }
    ESP_LOGI(
        TAG,
        "IMU_WINDOW_CAPTURE_DONE ok=%s warmup_samples=%" PRIu32 " samples=%" PRIu32 " read_failures=%" PRIu32
        " mock=%" PRIu32 " deadline_miss=%" PRIu32 " interval_us_min=%" PRIu32
        " interval_us_mean=%" PRIu32 " interval_us_max=%" PRIu32 " stopped=%s first_read_status=%s first_read_error=%d",
        ok ? "true" : "false",
        result->warmup_sample_count,
        result->captured_samples,
        result->read_failure_count,
        result->mock_sample_count,
        result->deadline_miss_count,
        result->min_interval_us,
        result->mean_interval_us,
        result->max_interval_us,
        result->measurement_stop_ok ? "true" : "false",
        result->first_read_status[0] != '\0' ? result->first_read_status : "none",
        result->first_read_error);
    return ok;
}

static bool build_imu_window_manifest_frame(
    const char *cmd_id,
    const char *test_run_id,
    const char *transport_type,
    const char *window_id,
    const imu_window_capture_result_t *capture,
    uint32_t samples_crc,
    uint32_t seq,
    char *frame,
    size_t frame_size)
{
#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    int sensor_i2c_address = CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_ADDR;
#else
    int sensor_i2c_address = -1;
#endif
    int manifest_written = snprintf(
        s_imu_window_payload,
        sizeof(s_imu_window_payload),
        "event_type=imu_window_manifest\n"
        "priority=normal\n"
        "source=qmi8658_i2c\n"
        "source_status=observed\n"
        "fw_version=%s\n"
        "test_run_id=%s\n"
        "seq=%" PRIu32 "\n"
        "transport_type=%s\n"
        "boot_count=%" PRIu32 "\n"
        "contract_version=%s\n"
        "window_id=%s\n"
        "capture_cmd_id=%s\n"
        "sample_count=%" PRIu32 "\n"
        "requested_interval_us=%u\n"
        "capture_start_uptime_us=%" PRIu64 "\n"
        "capture_end_uptime_us=%" PRIu64 "\n"
        "min_interval_us=%" PRIu32 "\n"
        "mean_interval_us=%" PRIu32 "\n"
        "max_interval_us=%" PRIu32 "\n"
        "deadline_miss_count=%" PRIu32 "\n"
        "read_failure_count=%" PRIu32 "\n"
        "mock_sample_count=%" PRIu32 "\n"
        "warmup_sample_count=%" PRIu32 "\n"
        "warmup_interval_us=%u\n"
        "chunk_count=%u\n"
        "uploaded_chunk_count=%u\n"
        "samples_crc32=%08" PRIX32 "\n"
        "sensor_model=QMI8658A\n"
        "sensor_i2c_address=%d\n"
        "accel_unit=mg\n"
        "gyro_unit=mdps\n"
        "activity_label=unknown\n"
        "label_source=none\n"
        "collection_authorization=operator_command\n"
        "training_allowed=false\n"
        "mounting_profile_id=unrecorded\n"
        "axis_mapping_status=unrecorded\n"
        "calibration_profile_id=unrecorded\n",
        CONFIG_EGOLINK_FW_VERSION,
        test_run_id,
        seq,
        transport_type,
        s_boot_count,
        IMU_WINDOW_CONTRACT_VERSION,
        window_id,
        cmd_id,
        capture->captured_samples,
        (unsigned)IMU_WINDOW_INTERVAL_US,
        capture->capture_start_uptime_us,
        capture->capture_end_uptime_us,
        capture->min_interval_us,
        capture->mean_interval_us,
        capture->max_interval_us,
        capture->deadline_miss_count,
        capture->read_failure_count,
        capture->mock_sample_count,
        capture->warmup_sample_count,
        (unsigned)(IMU_WINDOW_WARMUP_INTERVAL_MS * 1000u),
        (unsigned)IMU_WINDOW_CHUNK_COUNT,
        (unsigned)IMU_WINDOW_CHUNK_COUNT,
        samples_crc,
        sensor_i2c_address);
    if (manifest_written <= 0 || (size_t)manifest_written >= sizeof(s_imu_window_payload)) {
        return false;
    }
    char manifest_id[96];
    snprintf(manifest_id, sizeof(manifest_id), "imu-%s-b%" PRIu32 "-manifest", cmd_id, s_boot_count);
    return build_lte_raw_frame(frame, frame_size, "event", manifest_id, seq, s_imu_window_payload) &&
           strlen(frame) <= IMU_WINDOW_RAW_FRAME_MAX_BYTES;
}

static bool imu_window_transport_valid(const char *transport_type)
{
    return transport_type != NULL &&
           (strcmp(transport_type, "lte") == 0 || strcmp(transport_type, "wifi") == 0);
}

static bool imu_window_post_raw(
    const char *transport_type,
    const char *path,
    const char *url,
    const char *frame,
    const char *label,
    const char *cmd_id,
    uint32_t seq,
    char *reason,
    size_t reason_size,
    int *status_code)
{
    if (strcmp(transport_type, "wifi") == 0) {
        int status = 0;
        bool ok = message_hub_post_raw(path, frame, &status);
        snprintf(reason, reason_size, "%s", ok ? "WIFI_HTTP_OK" : "WIFI_HTTP_FAILED");
        if (status_code != NULL) {
            *status_code = status;
        }
        return ok;
    }
#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
    if (strcmp(transport_type, "lte") == 0) {
        sim7670_lte_http_probe_result_t result;
        bool ok = lte_raw_outbox_post_raw_with_retry(
            url,
            CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
            frame,
            "text/x-egolink-frame; profile=raw-frame.p0.v1",
            label,
            cmd_id,
            seq,
            &result);
        snprintf(reason, reason_size, "%s", result.reason_code);
        if (status_code != NULL) {
            *status_code = result.status_code;
        }
        return ok;
    }
#else
    (void)url;
    (void)label;
    (void)cmd_id;
    (void)seq;
#endif
    snprintf(reason, reason_size, "UNSUPPORTED_TRANSPORT");
    if (status_code != NULL) {
        *status_code = 0;
    }
    return false;
}

static bool publish_imu_window(const char *cmd_id, const char *test_run_id, const char *transport_type)
{
    if (cmd_id == NULL || cmd_id[0] == '\0') {
        imu_window_set_error("command_id_missing");
        return false;
    }
    if (!s_boot_count_persisted || s_boot_count == 0u) {
        imu_window_set_error("persistent_boot_count_unavailable");
        return false;
    }
    if (!imu_window_test_run_id_valid(test_run_id)) {
        imu_window_set_error("test_run_id_invalid");
        return false;
    }
    if (!imu_window_transport_valid(transport_type)) {
        imu_window_set_error("transport_type_invalid");
        return false;
    }

    imu_window_capture_result_t capture;
    if (!capture_real_imu_window(&capture)) {
        return false;
    }

    char path[160];
    char url[256];
    char window_id[80];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/raw-ingest", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);
    snprintf(window_id, sizeof(window_id), "imuw-%s-b%" PRIu32, cmd_id, s_boot_count);
    uint32_t samples_crc = egolink_crc32(s_imu_window_binary, sizeof(s_imu_window_binary));
    if (!build_imu_window_manifest_frame(
            cmd_id,
            test_run_id,
            transport_type,
            window_id,
            &capture,
            samples_crc,
            UINT32_MAX,
            s_imu_window_frame,
            sizeof(s_imu_window_frame))) {
        imu_window_set_error("manifest_frame_preflight_over_1200_bytes");
        return false;
    }

    uint32_t uploaded_chunks = 0;
    for (uint32_t chunk_index = 0; chunk_index < IMU_WINDOW_CHUNK_COUNT; ++chunk_index) {
        uint32_t sample_start = chunk_index * IMU_WINDOW_SAMPLES_PER_CHUNK;
        uint32_t remaining = IMU_WINDOW_SAMPLE_COUNT - sample_start;
        uint32_t chunk_samples = remaining < IMU_WINDOW_SAMPLES_PER_CHUNK ? remaining : IMU_WINDOW_SAMPLES_PER_CHUNK;
        size_t chunk_bytes = (size_t)chunk_samples * IMU_WINDOW_RECORD_BYTES;
        const uint8_t *chunk_data = &s_imu_window_binary[sample_start * IMU_WINDOW_RECORD_BYTES];
        if (!imu_window_base64_encode(
                chunk_data,
                chunk_bytes,
                s_imu_window_chunk_base64,
                sizeof(s_imu_window_chunk_base64))) {
            imu_window_set_error("chunk_base64_failed");
            return false;
        }

        uint32_t seq = next_seq();
        uint32_t chunk_crc = egolink_crc32(chunk_data, chunk_bytes);
        int payload_written = snprintf(
            s_imu_window_payload,
            sizeof(s_imu_window_payload),
            "event_type=imu_window_chunk\n"
            "priority=normal\n"
            "source=qmi8658_i2c\n"
            "source_status=observed\n"
            "fw_version=%s\n"
            "test_run_id=%s\n"
            "seq=%" PRIu32 "\n"
            "transport_type=%s\n"
            "boot_count=%" PRIu32 "\n"
            "contract_version=%s\n"
            "window_id=%s\n"
            "capture_cmd_id=%s\n"
            "chunk_index=%" PRIu32 "\n"
            "chunk_count=%u\n"
            "sample_start_index=%" PRIu32 "\n"
            "sample_count=%" PRIu32 "\n"
            "total_sample_count=%u\n"
            "requested_interval_us=%u\n"
            "sample_record_bytes=%u\n"
            "sample_encoding=offset_us+six_i32le+base64-v1\n"
            "chunk_crc32=%08" PRIX32 "\n"
            "samples_b64=%s\n",
            CONFIG_EGOLINK_FW_VERSION,
            test_run_id,
            seq,
            transport_type,
            s_boot_count,
            IMU_WINDOW_CONTRACT_VERSION,
            window_id,
            cmd_id,
            chunk_index,
            (unsigned)IMU_WINDOW_CHUNK_COUNT,
            sample_start,
            chunk_samples,
            (unsigned)IMU_WINDOW_SAMPLE_COUNT,
            (unsigned)IMU_WINDOW_INTERVAL_US,
            (unsigned)IMU_WINDOW_RECORD_BYTES,
            chunk_crc,
            s_imu_window_chunk_base64);
        if (payload_written <= 0 || (size_t)payload_written >= sizeof(s_imu_window_payload)) {
            imu_window_set_error("chunk_payload_too_large");
            return false;
        }

        char frame_id[96];
        snprintf(frame_id, sizeof(frame_id), "imu-%s-b%" PRIu32 "-c%02" PRIu32, cmd_id, s_boot_count, chunk_index);
        if (!build_lte_raw_frame(
                s_imu_window_frame,
                sizeof(s_imu_window_frame),
                "event",
                frame_id,
                seq,
                s_imu_window_payload) ||
            strlen(s_imu_window_frame) > IMU_WINDOW_RAW_FRAME_MAX_BYTES) {
            imu_window_set_error("chunk_frame_over_1200_bytes");
            return false;
        }

        char post_reason[SIM7670_LTE_HTTP_REASON_MAX];
        int post_status = 0;
        bool posted = imu_window_post_raw(
            transport_type,
            path,
            url,
            s_imu_window_frame,
            "imu_window_chunk",
            cmd_id,
            seq,
            post_reason,
            sizeof(post_reason),
            &post_status);
        ESP_LOGI(
            TAG,
            "IMU_WINDOW_CHUNK_POST_DONE window_id=%s chunk=%" PRIu32 "/%u bytes=%u ok=%s reason=%s status=%d",
            window_id,
            chunk_index,
            (unsigned)IMU_WINDOW_CHUNK_COUNT,
            (unsigned)strlen(s_imu_window_frame),
            posted ? "true" : "false",
            post_reason,
            post_status);
        if (!posted) {
            snprintf(
                s_imu_window_last_error,
                sizeof(s_imu_window_last_error),
                "chunk_%" PRIu32 "_upload_failed",
                chunk_index);
            return false;
        }
        uploaded_chunks += 1u;
    }

    uint32_t seq = next_seq();
    if (!build_imu_window_manifest_frame(
            cmd_id,
            test_run_id,
            transport_type,
            window_id,
            &capture,
            samples_crc,
            seq,
            s_imu_window_frame,
            sizeof(s_imu_window_frame))) {
        imu_window_set_error("manifest_frame_over_1200_bytes");
        return false;
    }

    char manifest_reason[SIM7670_LTE_HTTP_REASON_MAX];
    int manifest_status = 0;
    bool manifest_posted = imu_window_post_raw(
        transport_type,
        path,
        url,
        s_imu_window_frame,
        "imu_window_manifest",
        cmd_id,
        seq,
        manifest_reason,
        sizeof(manifest_reason),
        &manifest_status);
    ESP_LOGI(
        TAG,
        "IMU_WINDOW_MANIFEST_POST_DONE window_id=%s bytes=%u ok=%s reason=%s status=%d",
        window_id,
        (unsigned)strlen(s_imu_window_frame),
        manifest_posted ? "true" : "false",
        manifest_reason,
        manifest_status);
    imu_window_set_error(manifest_posted ? "none" : "manifest_upload_failed");
    return manifest_posted;
}

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
static void build_lte_location_report_kv_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
    const sim7670_gnss_report_t *gnss,
    bool gnss_query_ok)
{
    char lat[32];
    char lon[32];
    char altitude[32];
    char speed[32];
    char course[32];
    char pdop[32];
    char hdop[32];
    char vdop[32];
    char satellites[16];
    char raw_command[SIM7670_GNSS_RAW_COMMAND_MAX * 2];
    char raw_response[SIM7670_GNSS_RAW_RESPONSE_MAX * 2];
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    sim7670_gnss_report_t fallback;
    if (gnss == NULL) {
        sim7670_gnss_report_init(&fallback);
        gnss = &fallback;
    }
    const char *source = "sim7670g_firmware_gnss";
    const char *gnss_source = "sim7670g_uart_at";
    const char *gnss_driver = "uart_at";
    const char *state = gnss->gnss_state;
    const char *source_status = gnss->source_status;
    bool fix = gnss->fix;
    bool lat_valid = gnss->lat_valid;
    bool lon_valid = gnss->lon_valid;
    bool altitude_valid = gnss->altitude_valid;
    bool speed_valid = gnss->speed_valid;
    bool course_valid = gnss->course_valid;
    bool pdop_valid = gnss->pdop_valid;
    bool hdop_valid = gnss->hdop_valid;
    bool vdop_valid = gnss->vdop_valid;
    bool satellites_valid = gnss->satellites_valid;
    double lat_value = gnss->lat;
    double lon_value = gnss->lon;
    double altitude_value = gnss->altitude_m;
    double speed_value = gnss->speed_mps;
    double course_value = gnss->course_deg;
    double pdop_value = gnss->pdop;
    double hdop_value = gnss->hdop;
    double vdop_value = gnss->vdop;
    int satellites_value = gnss->satellites;
    const char *utc_date = gnss->utc_date;
    const char *utc_time = gnss->utc_time;
    json_escape_summary(raw_command, sizeof(raw_command), gnss->raw_command);
    json_escape_summary(raw_response, sizeof(raw_response), gnss->raw_response);
#else
    (void)gnss;
    (void)gnss_query_ok;
    const char *source = "firmware_gnss_scaffold";
    const char *gnss_source = "sim7670g_scaffold";
    const char *gnss_driver = "not_integrated";
    const char *state = "driver_not_integrated";
    const char *source_status = "unverified";
    bool fix = false;
    bool lat_valid = false;
    bool lon_valid = false;
    bool altitude_valid = false;
    bool speed_valid = false;
    bool course_valid = false;
    bool pdop_valid = false;
    bool hdop_valid = false;
    bool vdop_valid = false;
    bool satellites_valid = true;
    double lat_value = 0.0;
    double lon_value = 0.0;
    double altitude_value = 0.0;
    double speed_value = 0.0;
    double course_value = 0.0;
    double pdop_value = 0.0;
    double hdop_value = 0.0;
    double vdop_value = 0.0;
    int satellites_value = 0;
    const char *utc_date = "";
    const char *utc_time = "";
    raw_command[0] = '\0';
    raw_response[0] = '\0';
#endif
    json_number_or_null(lat, sizeof(lat), lat_valid, lat_value, "%.7f");
    json_number_or_null(lon, sizeof(lon), lon_valid, lon_value, "%.7f");
    json_number_or_null(altitude, sizeof(altitude), altitude_valid, altitude_value, "%.2f");
    json_number_or_null(speed, sizeof(speed), speed_valid, speed_value, "%.3f");
    json_number_or_null(course, sizeof(course), course_valid, course_value, "%.2f");
    json_number_or_null(pdop, sizeof(pdop), pdop_valid, pdop_value, "%.2f");
    json_number_or_null(hdop, sizeof(hdop), hdop_valid, hdop_value, "%.2f");
    json_number_or_null(vdop, sizeof(vdop), vdop_valid, vdop_value, "%.2f");
    json_int_or_null(satellites, sizeof(satellites), satellites_valid, satellites_value);
    snprintf(
        buffer,
        buffer_size,
        "event_type=location_report\n"
        "priority=normal\n"
        "fw_version=%s\n"
        "test_run_id=%s\n"
        "seq=%" PRIu32 "\n"
        "boot_count=%" PRIu32 "\n"
        "ts=uptime_ms:%" PRId64 "\n"
        "source=%s\n"
        "source_status=%s\n"
        "fix=%s\n"
        "gnss_state=%s\n"
        "gnss_source=%s\n"
        "gnss_driver=%s\n"
        "gnss_query_ok=%s\n"
        "lat=%s\n"
        "lon=%s\n"
        "altitude_m=%s\n"
        "speed_mps=%s\n"
        "course_deg=%s\n"
        "pdop=%s\n"
        "hdop=%s\n"
        "vdop=%s\n"
        "satellites=%s\n"
        "utc_date=%s\n"
        "utc_time=%s\n"
        "raw_command=%s\n"
        "raw_response=%s\n"
        "location_request_cmd_id=%s\n"
        "transport_type=lte\n"
        "lte_http_phase=location_report\n"
        "lte_http_driver=%s\n",
        CONFIG_EGOLINK_FW_VERSION,
        CONFIG_EGOLINK_TEST_RUN_ID,
        seq,
        s_boot_count,
        uptime_ms(),
        source,
        source_status,
        json_bool(fix),
        state,
        gnss_source,
        gnss_driver,
        json_bool(gnss_query_ok),
        lat,
        lon,
        altitude,
        speed,
        course,
        pdop,
        hdop,
        vdop,
        satellites,
        utc_date,
        utc_time,
        raw_command,
        raw_response,
        cmd_id,
        sim7670_lte_http_backend_name());
#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST
    size_t used = strlen(buffer);
    if (used < buffer_size) {
        snprintf(buffer + used, buffer_size - used, "test_inject_raw_post_fail_once=true\n");
    }
#endif
}

static bool lte_http_publish_raw_location_report(const char *cmd_id)
{
    char path[160];
    char url[256];
    char frame_id[96];
    char payload[1280];
    char frame[1700];
    sim7670_lte_http_probe_result_t post_result;
    sim7670_gnss_report_t gnss;
    uint32_t seq = next_seq();

    sim7670_gnss_report_init(&gnss);
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    bool gnss_query_ok = sim7670_gnss_request_location(&gnss);
#else
    bool gnss_query_ok = false;
#endif
    snprintf(path, sizeof(path), "/api/v1/devices/%s/raw-ingest", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);
    snprintf(frame_id, sizeof(frame_id), "loc-%s", cmd_id);
    build_lte_location_report_kv_payload(payload, sizeof(payload), seq, cmd_id, &gnss, gnss_query_ok);
    if (!build_lte_raw_frame(frame, sizeof(frame), "event", frame_id, seq, payload)) {
        ESP_LOGW(TAG, "LTE_HTTP_LOCATION_RAW_FRAME_BUILD_FAILED cmd_id=%s", cmd_id);
        lte_raw_outbox_record_drop("location_report_frame_build_failed");
        return false;
    }
    ESP_LOGI(TAG, "LTE_HTTP_LOCATION_RAW_FRAME_BYTES=%u", (unsigned)strlen(frame));
    bool ok = lte_raw_outbox_post_raw_with_retry(
        url,
        CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
        "location_report",
        cmd_id,
        seq,
        &post_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_LOCATION_RAW_POST_DONE cmd_id=%s seq=%" PRIu32 " ok=%s reason=%s status=%d",
        cmd_id,
        seq,
        ok ? "true" : "false",
        post_result.reason_code,
        post_result.status_code);
    return ok;
}

#if CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED
static bool build_lte_location_observation_kv_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
    const sim7670_lte_report_t *lte,
    bool lte_query_ok)
{
    sim7670_lte_report_t fallback;
    if (lte == NULL) {
        sim7670_lte_report_init(&fallback);
        lte = &fallback;
    }

    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
    platform_imu_sample();
    platform_imu_snapshot_t imu;
    platform_imu_get_snapshot(&imu);
    lte_raw_outbox_counters_t outbox;
    lte_raw_outbox_snapshot(&outbox);

    const char *imu_source_status =
        (imu.hardware_present && imu.driver_enabled && !imu.data_is_mock) ? "observed" : "unverified";
    const char *imu_evidence_status = imu.data_is_mock ? "mock" : (imu.hardware_present ? "observed" : "missing");
    const char *power_source_status = power.battery_is_mock ? "mock" : "measured";
    const char *power_evidence_status = power.battery_is_mock ? "mock" : "measured";

    char rssi[16];
    char rsrp[16];
    char rsrq[16];
    char sinr[16];
    char rat[SIM7670_LTE_RAT_MAX * 2];
    char cell_id[SIM7670_LTE_ID_MAX * 2];
    char registration_state[SIM7670_LTE_STATUS_MAX * 2];
    char pdp_state[SIM7670_LTE_STATUS_MAX * 2];
    char assigned_ip[SIM7670_LTE_IP_MAX * 2];
    char reason_code[SIM7670_LTE_STATUS_MAX * 2];
    char imu_backend_status[64];
    char power_state[32];
    char battery_mv[16];

    json_int_or_null(rssi, sizeof(rssi), lte->rssi_valid, lte->rssi);
    json_int_or_null(rsrp, sizeof(rsrp), lte->rsrp_valid, lte->rsrp);
    json_int_or_null(rsrq, sizeof(rsrq), lte->rsrq_valid, lte->rsrq);
    json_int_or_null(sinr, sizeof(sinr), lte->sinr_valid, lte->sinr);
    json_escape_summary(rat, sizeof(rat), lte->rat);
    json_escape_summary(cell_id, sizeof(cell_id), lte->cell_id);
    json_escape_summary(registration_state, sizeof(registration_state), lte->registration_state);
    json_escape_summary(pdp_state, sizeof(pdp_state), lte->pdp_state);
    json_escape_summary(assigned_ip, sizeof(assigned_ip), lte->assigned_ip);
    json_escape_summary(reason_code, sizeof(reason_code), lte->reason_code);
    json_escape_summary(imu_backend_status, sizeof(imu_backend_status), imu.backend_status);
    json_escape_summary(power_state, sizeof(power_state), platform_power_state_name(power.state));
    json_int_or_null(battery_mv, sizeof(battery_mv), power.battery_voltage_valid, power.battery_millivolt);
    const char *network_state = "query_failed";
    const char *network_last_error = reason_code;
    if (lte_query_ok && lte->registered && lte->pdp_active) {
        network_state = "ready";
        network_last_error = "none";
    } else if (lte_query_ok) {
        network_state = "degraded";
    }
    lte_reliability_evidence_fields_t reliability =
        lte_reliability_evidence_fields_for_observation(network_state, network_last_error);

    int written = snprintf(
        buffer,
        buffer_size,
        "event_type=location_observation\n"
        "priority=normal\n"
        "fw_version=%s\n"
        "test_run_id=%s\n"
        "seq=%" PRIu32 "\n"
        "source=sim7670g_firmware_cell\n"
        "source_status=observed\n"
        "location_request_cmd_id=%s\n"
        "cell_rat=%s\n"
        "cell_id=%s\n"
        "cell_rssi=%s\n"
        "cell_rsrp=%s\n"
        "cell_rsrq=%s\n"
        "cell_sinr=%s\n"
        "cell_registration_state=%s\n"
        "cell_pdp_state=%s\n"
        "cell_reason_code=%s\n"
        "lte_driver=%s\n"
        "lte_query_ok=%s\n"
        "lte_registered=%s\n"
        "lte_pdp_active=%s\n"
        "lte_assigned_ip=%s\n"
        "lte_reason_code=%s\n"
        "wifi_source=esp_wifi_sta\n"
        "wifi_source_status=disabled\n"
        "wifi_evidence_status=missing\n"
        "wifi_scan_enabled=false\n"
        "wifi_ap_count=0\n"
        "wifi_privacy=raw_bssid_not_collected\n"
        "imu_source=platform_imu\n"
        "imu_source_status=%s\n"
        "imu_evidence_status=%s\n"
        "imu_data_is_mock=%s\n"
        "imu_backend_status=%s\n"
        "power_source=platform_power\n"
        "power_source_status=%s\n"
        "power_evidence_status=%s\n"
        "power_soc_pct=%d\n"
        "power_charging=%s\n"
        "power_state=%s\n"
        "power_battery_mv=%s\n"
        "location_belief_state=Unknown\n"
        "location_belief_source=cell,lte,wifi,imu,power\n"
        "location_belief_reason=cell_observation_without_position_fix\n"
        "transport_type=lte\n"
        "network_mode=LTE\n"
        "network_rssi=%s\n"
        "network_state=%s\n"
        "network_last_error=%s\n"
        "network_reconnect_count=%" PRIu32 "\n"
        "network_last_reconnect_reason=%s\n"
        "network_raw_post_attempt_count=%" PRIu32 "\n"
        "network_raw_post_success_count=%" PRIu32 "\n"
        "network_raw_post_failure_count=%" PRIu32 "\n"
        "cache_state=%s\n"
        "cache_source_status=%s\n"
        "cache_retry_policy=single_retry_current_boot\n"
        "cache_retry_attempt_count=%" PRIu32 "\n"
        "cache_retry_success_count=%" PRIu32 "\n"
        "cache_retry_failure_count=%" PRIu32 "\n"
        "cache_queued_message_count=%" PRIu32 "\n"
        "cache_dropped_message_count=%" PRIu32 "\n"
        "cache_oldest_message_age_ms=%" PRIu32 "\n"
        "cache_last_drop_reason=%s\n"
        "cache_flush_attempt_count=%" PRIu32 "\n"
        "cache_flush_success_count=%" PRIu32 "\n"
        "cache_flush_failure_count=%" PRIu32 "\n"
        "lte_http_phase=location_observation\n"
        "lte_http_driver=%s\n",
        CONFIG_EGOLINK_FW_VERSION,
        CONFIG_EGOLINK_TEST_RUN_ID,
        seq,
        cmd_id,
        rat,
        cell_id,
        rssi,
        rsrp,
        rsrq,
        sinr,
        registration_state,
        pdp_state,
        reason_code,
        sim7670_lte_backend_name(),
        json_bool(lte_query_ok),
        json_bool(lte->registered),
        json_bool(lte->pdp_active),
        assigned_ip,
        reason_code,
        imu_source_status,
        imu_evidence_status,
        json_bool(imu.data_is_mock),
        imu_backend_status,
        power_source_status,
        power_evidence_status,
        power.battery_percent,
        json_bool(power.charging),
        power_state,
        battery_mv,
        rssi,
        reliability.network_state,
        reliability.network_last_error,
        reliability.network_reconnect_count,
        reliability.network_last_reconnect_reason,
        outbox.post_attempt_count,
        outbox.post_success_count,
        outbox.post_failure_count,
        reliability.cache_state,
        reliability.cache_source_status,
        outbox.retry_attempt_count,
        outbox.retry_success_count,
        outbox.retry_failure_count,
        reliability.cache_queued_message_count,
        outbox.dropped_message_count,
        reliability.cache_oldest_message_age_ms,
        outbox.last_drop_reason,
        reliability.cache_flush_attempt_count,
        reliability.cache_flush_success_count,
        reliability.cache_flush_failure_count,
        sim7670_lte_http_backend_name());
    return written > 0 && (size_t)written < buffer_size;
}

static bool lte_http_publish_raw_location_observation(const char *cmd_id)
{
    char path[160];
    char url[256];
    char frame_id[96];
    char payload[2050];
    char frame[2400];
    sim7670_lte_http_probe_result_t post_result;
    sim7670_lte_report_t lte;
    uint32_t seq = next_seq();

    sim7670_lte_report_init(&lte);
    bool lte_query_ok = sim7670_lte_query_status(&lte);
    snprintf(path, sizeof(path), "/api/v1/devices/%s/raw-ingest", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);
    snprintf(frame_id, sizeof(frame_id), "obs-%s", cmd_id);
    if (!build_lte_location_observation_kv_payload(payload, sizeof(payload), seq, cmd_id, &lte, lte_query_ok)) {
        ESP_LOGW(TAG, "LTE_HTTP_LOCATION_OBSERVATION_PAYLOAD_TRUNCATED cmd_id=%s", cmd_id);
        lte_raw_outbox_record_drop("location_observation_payload_truncated");
        return false;
    }
    if (!build_lte_raw_frame(frame, sizeof(frame), "event", frame_id, seq, payload)) {
        ESP_LOGW(TAG, "LTE_HTTP_LOCATION_OBSERVATION_RAW_FRAME_BUILD_FAILED cmd_id=%s", cmd_id);
        lte_raw_outbox_record_drop("location_observation_frame_build_failed");
        return false;
    }
    ESP_LOGI(TAG, "LTE_HTTP_LOCATION_OBSERVATION_RAW_FRAME_BYTES=%u", (unsigned)strlen(frame));
    bool ok = lte_raw_outbox_post_raw_with_retry(
        url,
        CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
        "location_observation",
        cmd_id,
        seq,
        &post_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_LOCATION_OBSERVATION_RAW_POST_DONE cmd_id=%s seq=%" PRIu32 " ok=%s reason=%s status=%d",
        cmd_id,
        seq,
        ok ? "true" : "false",
        post_result.reason_code,
        post_result.status_code);
    return ok;
}
#endif

#if CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED
static bool lte_http_publish_d1_periodic_location_once(void)
{
    static uint32_t periodic_id = 0;
    char cmd_id[64];
    snprintf(cmd_id, sizeof(cmd_id), "d1-periodic-%" PRIu32, ++periodic_id);
    ESP_LOGI(TAG, "LTE_HTTP_D1_PERIODIC_LOCATION_START id=%s", cmd_id);
    bool location_ok = lte_http_publish_raw_location_report(cmd_id);
    bool observation_ok = false;
#if CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED
    observation_ok = location_ok ? lte_http_publish_raw_location_observation(cmd_id) : false;
#endif
    ESP_LOGI(
        TAG,
        "LTE_HTTP_D1_PERIODIC_LOCATION_DONE id=%s location_ok=%s observation_ok=%s",
        cmd_id,
        location_ok ? "true" : "false",
        observation_ok ? "true" : "false");
    return location_ok && observation_ok;
}
#endif
#endif

static void build_lte_command_ack_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
    const char *test_run_id,
    const char *status,
    const char *message,
    const sim7670_lte_http_probe_result_t *poll_result,
    bool duplicate_prevented)
{
    sim7670_lte_http_probe_result_t fallback;
    if (poll_result == NULL) {
        sim7670_lte_http_probe_result_init(&fallback);
        poll_result = &fallback;
    }

    char poll_status_code[16];
    char poll_action_elapsed_ms[16];
    lte_raw_outbox_counters_t outbox;
    lte_raw_outbox_snapshot(&outbox);
    lte_reliability_evidence_fields_t reliability = lte_reliability_evidence_fields_for_ack();
    snprintf(
        poll_status_code,
        sizeof(poll_status_code),
        "%d",
        poll_result->status_code_valid ? poll_result->status_code : -1);
    snprintf(
        poll_action_elapsed_ms,
        sizeof(poll_action_elapsed_ms),
        "%d",
        poll_result->action_elapsed_ms_valid ? poll_result->action_elapsed_ms : -1);

    snprintf(
        buffer,
        buffer_size,
        "cmd_id=%s\n"
        "status=%s\n"
        "message=%s\n"
        "fw_version=%s\n"
        "test_run_id=%s\n"
        "seq=%" PRIu32 "\n"
        "transport_type=lte\n"
        "lte_http_phase=command_ack\n"
        "lte_http_driver=%s\n"
        "lte_http_poll_reason_code=%s\n"
        "lte_http_poll_status_code=%s\n"
        "lte_http_poll_action_elapsed_ms=%s\n"
        "command_last_cmd_id=%s\n"
        "command_parse_status=%s\n"
        "command_count=%d\n"
        "duplicate_local_execution_prevented=%s\n"
        "network_state=%s\n"
        "network_last_error=%s\n"
        "network_reconnect_count=%" PRIu32 "\n"
        "network_last_reconnect_reason=%s\n"
        "network_raw_post_attempt_count=%" PRIu32 "\n"
        "network_raw_post_success_count=%" PRIu32 "\n"
        "network_raw_post_failure_count=%" PRIu32 "\n"
        "cache_state=%s\n"
        "cache_source_status=%s\n"
        "cache_retry_policy=single_retry_current_boot\n"
        "cache_retry_attempt_count=%" PRIu32 "\n"
        "cache_retry_success_count=%" PRIu32 "\n"
        "cache_retry_failure_count=%" PRIu32 "\n"
        "cache_queued_message_count=%" PRIu32 "\n"
        "cache_dropped_message_count=%" PRIu32 "\n"
        "cache_oldest_message_age_ms=%" PRIu32 "\n"
        "cache_last_drop_reason=%s\n"
        "cache_flush_attempt_count=%" PRIu32 "\n"
        "cache_flush_success_count=%" PRIu32 "\n"
        "cache_flush_failure_count=%" PRIu32 "\n",
        cmd_id,
        status,
        message,
        CONFIG_EGOLINK_FW_VERSION,
        test_run_id,
        seq,
        sim7670_lte_http_backend_name(),
        poll_result->reason_code,
        poll_status_code,
        poll_action_elapsed_ms,
        cmd_id,
        s_lte_command_parse_status,
        s_lte_command_last_command_count,
        json_bool(duplicate_prevented),
        reliability.network_state,
        reliability.network_last_error,
        reliability.network_reconnect_count,
        reliability.network_last_reconnect_reason,
        outbox.post_attempt_count,
        outbox.post_success_count,
        outbox.post_failure_count,
        reliability.cache_state,
        reliability.cache_source_status,
        outbox.retry_attempt_count,
        outbox.retry_success_count,
        outbox.retry_failure_count,
        reliability.cache_queued_message_count,
        outbox.dropped_message_count,
        reliability.cache_oldest_message_age_ms,
        outbox.last_drop_reason,
        reliability.cache_flush_attempt_count,
        reliability.cache_flush_success_count,
        reliability.cache_flush_failure_count);
}

static bool lte_http_ack_command(
    const char *cmd_id,
    const char *test_run_id,
    const char *status,
    const char *message,
    const sim7670_lte_http_probe_result_t *poll_result,
    bool duplicate_prevented)
{
    char path[192];
    char url[288];
    char payload[1200];
    char frame[1600];
    sim7670_lte_http_probe_result_t ack_result;
    uint32_t seq = next_seq();

    snprintf(
        path,
        sizeof(path),
        "/api/v1/devices/%s/commands/%s/ack.raw",
        CONFIG_EGOLINK_DEVICE_ID,
        cmd_id);
    build_message_hub_url(url, sizeof(url), path);
    build_lte_command_ack_payload(
        payload,
        sizeof(payload),
        seq,
        cmd_id,
        test_run_id,
        status,
        message,
        poll_result,
        duplicate_prevented);
    if (!build_lte_raw_frame(frame, sizeof(frame), "ack", cmd_id, seq, payload)) {
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_ACK_BUILD_FAILED cmd_id=%s", cmd_id);
        lte_raw_outbox_record_drop("command_ack_frame_build_failed");
        return false;
    }
    ESP_LOGI(TAG, "LTE_HTTP_COMMAND_RAW_ACK_FRAME_BYTES=%u", (unsigned)strlen(frame));
    bool ok = lte_raw_outbox_post_raw_with_retry(
        url,
        CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
        "command_ack",
        cmd_id,
        seq,
        &ack_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_COMMAND_RAW_ACK_DONE cmd_id=%s seq=%" PRIu32 " ok=%s reason=%s status=%d",
        cmd_id,
        seq,
        ok ? "true" : "false",
        ack_result.reason_code,
        ack_result.status_code);
    return ok;
}

static void build_lte_command_diag_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *phase,
    const sim7670_lte_http_probe_result_t *poll_result,
    bool include_poll_result,
    bool acked)
{
    sim7670_lte_http_probe_result_t fallback;
    if (poll_result == NULL) {
        sim7670_lte_http_probe_result_init(&fallback);
        poll_result = &fallback;
    }

    char escaped_phase[64];
    char escaped_reason[SIM7670_LTE_HTTP_REASON_MAX * 2];
    char escaped_cmd_id[96];
    char escaped_parse_status[96];
    char poll_status_code[16];
    char poll_data_len[16];
    char poll_action_elapsed_ms[16];
    char rtt_ms[16];
    char last_error_json[SIM7670_LTE_HTTP_REASON_MAX * 2 + 4];
    const char *effective_phase = phase ? phase : "unknown";
    const char *effective_reason = include_poll_result ? poll_result->reason_code : "LTE_HTTP_COMMAND_READY";
    bool poll_ok = include_poll_result && strcmp(effective_reason, "LTE_HTTP_OK") == 0;

    json_escape_summary(escaped_phase, sizeof(escaped_phase), effective_phase);
    json_escape_summary(escaped_reason, sizeof(escaped_reason), effective_reason);
    json_escape_summary(escaped_cmd_id, sizeof(escaped_cmd_id), s_lte_command_last_cmd_id);
    json_escape_summary(escaped_parse_status, sizeof(escaped_parse_status), s_lte_command_parse_status);
    json_int_or_null(
        poll_status_code,
        sizeof(poll_status_code),
        include_poll_result && poll_result->status_code_valid,
        poll_result->status_code);
    json_int_or_null(
        poll_data_len,
        sizeof(poll_data_len),
        include_poll_result && poll_result->data_len_valid,
        poll_result->data_len);
    json_int_or_null(
        poll_action_elapsed_ms,
        sizeof(poll_action_elapsed_ms),
        include_poll_result && poll_result->action_elapsed_ms_valid,
        poll_result->action_elapsed_ms);
    json_int_or_null(
        rtt_ms,
        sizeof(rtt_ms),
        include_poll_result && poll_result->action_elapsed_ms_valid,
        poll_result->action_elapsed_ms);
    if (include_poll_result && !poll_ok) {
        snprintf(last_error_json, sizeof(last_error_json), "\"%s\"", escaped_reason);
    } else {
        snprintf(last_error_json, sizeof(last_error_json), "null");
    }

    build_lte_http_probe_lte_fragment(s_lte_http_probe_lte_fragment, sizeof(s_lte_http_probe_lte_fragment));
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"event\","
        "\"event_type\":\"lte_http_command_diag\","
        "\"priority\":\"normal\","
        "\"fw_version\":\"%s\","
        "\"source\":\"sim7670g_lte_http_command_loop\","
        "\"source_status\":\"%s\","
        "\"reset_reason\":\"%s\","
        "\"boot_count\":%" PRIu32 ","
        "\"boot_uptime_ms\":%" PRId64 ","
        "\"transport\":{\"type\":\"lte\","
        "\"rtt_ms\":%s,"
        "\"last_error\":%s},"
        "\"lte_http\":{\"phase\":\"%s\","
        "\"driver\":\"%s\","
        "\"poll_reason_code\":\"%s\","
        "\"poll_status_code\":%s,"
        "\"poll_data_len\":%s,"
        "\"poll_action_elapsed_ms\":%s},"
        "\"command\":{\"last_cmd_id\":\"%s\","
        "\"parse_status\":\"%s\","
        "\"command_count\":%d,"
        "\"last_status\":\"%s\","
        "\"last_ack_status\":%s,"
        "\"ack_observed\":%s}"
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        include_poll_result ? (poll_ok ? "observed" : "unverified") : "observed",
        s_reset_reason,
        s_boot_count,
        uptime_ms(),
        rtt_ms,
        last_error_json,
        escaped_phase,
        sim7670_lte_http_backend_name(),
        escaped_reason,
        poll_status_code,
        poll_data_len,
        poll_action_elapsed_ms,
        escaped_cmd_id,
        escaped_parse_status,
        s_lte_command_last_command_count,
        acked ? "ok" : "pending",
        acked ? "\"ok\"" : "null",
        json_bool(acked),
        s_lte_http_probe_lte_fragment);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static bool lte_http_post_command_diag(
    const char *phase,
    const sim7670_lte_http_probe_result_t *poll_result,
    bool include_poll_result,
    bool acked)
{
    char path[160];
    char url[256];
    sim7670_lte_http_probe_result_t post_result;
    uint32_t seq = next_seq();

    snprintf(path, sizeof(path), "/api/v1/devices/%s/telemetry", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);
    build_lte_command_diag_payload(
        s_lte_command_diag_payload,
        sizeof(s_lte_command_diag_payload),
        seq,
        phase,
        poll_result,
        include_poll_result,
        acked);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_COMMAND_DIAG_PAYLOAD_BYTES phase=%s bytes=%u",
        phase ? phase : "unknown",
        (unsigned)strlen(s_lte_command_diag_payload));
    bool ok =
        sim7670_lte_http_post_json(url, CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN, s_lte_command_diag_payload, &post_result);
    ESP_LOGI(
        TAG,
        "LTE_HTTP_COMMAND_DIAG_POST_DONE phase=%s seq=%" PRIu32 " ok=%s reason=%s status=%d",
        phase ? phase : "unknown",
        seq,
        ok ? "true" : "false",
        post_result.reason_code,
        post_result.status_code);
    return ok;
}
#endif

static char *split_lte_raw_frame_payload(char *frame)
{
    char *separator = strstr(frame, "\r\n\r\n");
    if (separator != NULL) {
        separator[0] = '\0';
        return separator + 4;
    }
    separator = strstr(frame, "\n\n");
    if (separator != NULL) {
        separator[0] = '\0';
        return separator + 2;
    }
    return NULL;
}

static bool copy_lte_raw_token_value(const char *text, const char *key, char *buffer, size_t buffer_size)
{
    if (text == NULL || key == NULL || buffer == NULL || buffer_size == 0) {
        return false;
    }
    size_t key_len = strlen(key);
    const char *cursor = text;
    while ((cursor = strstr(cursor, key)) != NULL) {
        char previous = cursor == text ? ' ' : cursor[-1];
        if ((previous == ' ' || previous == '\t' || previous == '\r' || previous == '\n') &&
            cursor[key_len] == '=') {
            const char *value_start = cursor + key_len + 1;
            const char *value_end = value_start;
            while (*value_end != '\0' && *value_end != ' ' && *value_end != '\t' && *value_end != '\r' &&
                   *value_end != '\n') {
                value_end++;
            }
            size_t length = (size_t)(value_end - value_start);
            if (length >= buffer_size) {
                return false;
            }
            memcpy(buffer, value_start, length);
            buffer[length] = '\0';
            return length > 0;
        }
        cursor += key_len;
    }
    return false;
}

static bool copy_lte_raw_kv_value(const char *payload, const char *key, char *buffer, size_t buffer_size)
{
    if (payload == NULL || key == NULL || buffer == NULL || buffer_size == 0) {
        return false;
    }
    size_t key_len = strlen(key);
    const char *cursor = payload;
    while (*cursor != '\0') {
        const char *line_end = strpbrk(cursor, "\r\n");
        size_t line_len = line_end != NULL ? (size_t)(line_end - cursor) : strlen(cursor);
        if (line_len > key_len && strncmp(cursor, key, key_len) == 0 && cursor[key_len] == '=') {
            const char *value_start = cursor + key_len + 1;
            size_t value_len = line_len - key_len - 1;
            if (value_len >= buffer_size) {
                return false;
            }
            memcpy(buffer, value_start, value_len);
            buffer[value_len] = '\0';
            return value_len > 0;
        }
        if (line_end == NULL) {
            break;
        }
        cursor = line_end;
        while (*cursor == '\r' || *cursor == '\n') {
            cursor++;
        }
    }
    return false;
}

static bool parse_lte_raw_u32(const char *text, uint32_t *value, int base)
{
    if (text == NULL || value == NULL || text[0] == '\0') {
        return false;
    }
    char *end = NULL;
    unsigned long parsed = strtoul(text, &end, base);
    if (end == text || *end != '\0' || parsed > UINT32_MAX) {
        return false;
    }
    *value = (uint32_t)parsed;
    return true;
}

static bool imu_window_capture_cmd_id_valid(const char *cmd_id)
{
    if (cmd_id == NULL) {
        return false;
    }
    size_t length = strlen(cmd_id);
    if (length == 0u || length > IMU_WINDOW_CAPTURE_CMD_ID_MAX) {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        char value = cmd_id[index];
        bool allowed = (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z') ||
                       (value >= '0' && value <= '9') || value == '.' || value == '_' || value == ':' ||
                       value == '-';
        if (!allowed) {
            return false;
        }
    }
    return true;
}

static bool imu_window_test_run_id_valid(const char *test_run_id)
{
    if (test_run_id == NULL) {
        return false;
    }
    size_t length = strlen(test_run_id);
    if (length == 0u || length > 32u) {
        return false;
    }
    for (size_t index = 0; index < length; ++index) {
        char value = test_run_id[index];
        bool allowed = (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z') ||
                       (value >= '0' && value <= '9') || value == '.' || value == '_' || value == ':' ||
                       value == '-';
        if (!allowed) {
            return false;
        }
    }
    return true;
}

static bool capture_command_payload_shape_valid(const char *payload)
{
    const char *allowed[] = {"cmd", "cmd_id", "cmd-id", "sample_count", "sample-count",
                             "interval_ms", "interval-ms", "test_run_id", "test-run-id"};
    int cmd_count = 0;
    int cmd_id_count = 0;
    int sample_count = 0;
    int interval_count = 0;
    int test_run_count = 0;
    const char *cursor = payload;
    while (cursor != NULL && *cursor != '\0') {
        const char *line_end = strpbrk(cursor, "\r\n");
        size_t line_len = line_end != NULL ? (size_t)(line_end - cursor) : strlen(cursor);
        const char *separator = memchr(cursor, '=', line_len);
        if (line_len == 0u || separator == NULL) {
            return false;
        }
        size_t key_len = (size_t)(separator - cursor);
        int matched = -1;
        for (size_t index = 0; index < sizeof(allowed) / sizeof(allowed[0]); ++index) {
            if (strlen(allowed[index]) == key_len && strncmp(cursor, allowed[index], key_len) == 0) {
                matched = (int)index;
                break;
            }
        }
        if (matched < 0) {
            return false;
        }
        if (matched == 0) {
            cmd_count += 1;
        } else if (matched == 1 || matched == 2) {
            cmd_id_count += 1;
        } else if (matched == 3 || matched == 4) {
            sample_count += 1;
        } else if (matched == 5 || matched == 6) {
            interval_count += 1;
        } else {
            test_run_count += 1;
        }
        if (line_end == NULL) {
            break;
        }
        cursor = line_end;
        while (*cursor == '\r' || *cursor == '\n') {
            cursor++;
        }
    }
    return cmd_count == 1 && cmd_id_count == 1 && sample_count == 1 && interval_count == 1 &&
           test_run_count == 1;
}

static bool parse_lte_raw_command_frame(char *frame, lte_raw_command_t *command)
{
    if (frame == NULL || command == NULL) {
        set_lte_command_parse_status("raw_frame_missing");
        return false;
    }
    memset(command, 0, sizeof(*command));
    command->sample_count = IMU_WINDOW_SAMPLE_COUNT;
    command->interval_ms = IMU_WINDOW_INTERVAL_MS;
    command->parameters_valid = true;
    s_lte_command_last_command_count = 0;
    if (strncmp(frame, "EGLK/1", 6) != 0) {
        set_lte_command_parse_status("raw_unsupported_magic");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_UNSUPPORTED_MAGIC");
        return false;
    }

    char *payload = split_lte_raw_frame_payload(frame);
    if (payload == NULL) {
        set_lte_command_parse_status("raw_header_incomplete");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_HEADER_INCOMPLETE");
        return false;
    }

    char frame_type[24] = "";
    if (!copy_lte_raw_token_value(frame, "type", frame_type, sizeof(frame_type)) ||
        strcmp(frame_type, "command") != 0) {
        set_lte_command_parse_status("raw_unsupported_type");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_UNSUPPORTED_TYPE type=%s", frame_type);
        return false;
    }

    char len_text[16];
    char crc_text[16];
    uint32_t declared_len = 0;
    uint32_t declared_crc = 0;
    if (!copy_lte_raw_token_value(frame, "len", len_text, sizeof(len_text)) ||
        !copy_lte_raw_token_value(frame, "crc32", crc_text, sizeof(crc_text)) ||
        !parse_lte_raw_u32(len_text, &declared_len, 10) ||
        !parse_lte_raw_u32(crc_text, &declared_crc, 16)) {
        set_lte_command_parse_status("raw_len_crc_missing");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_LEN_CRC_MISSING");
        return false;
    }

    size_t actual_len = strlen(payload);
    if (actual_len != (size_t)declared_len) {
        set_lte_command_parse_status("raw_len_mismatch");
        ESP_LOGW(
            TAG,
            "LTE_HTTP_COMMAND_RAW_LEN_MISMATCH declared=%" PRIu32 " actual=%u",
            declared_len,
            (unsigned)actual_len);
        return false;
    }
    uint32_t actual_crc = egolink_crc32((const uint8_t *)payload, actual_len);
    if (actual_crc != declared_crc) {
        set_lte_command_parse_status("raw_crc_mismatch");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_CRC_MISMATCH declared=%08" PRIX32 " actual=%08" PRIX32, declared_crc, actual_crc);
        return false;
    }

    if (!copy_lte_raw_kv_value(payload, "cmd", command->cmd, sizeof(command->cmd))) {
        set_lte_command_parse_status("raw_missing_cmd");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_MISSING_CMD");
        return false;
    }
    if (strcmp(command->cmd, "none") == 0) {
        set_lte_command_parse_status("raw_no_command");
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_RAW_EMPTY");
        return false;
    }
    if (!copy_lte_raw_kv_value(payload, "cmd_id", command->cmd_id, sizeof(command->cmd_id)) &&
        !copy_lte_raw_kv_value(payload, "cmd-id", command->cmd_id, sizeof(command->cmd_id)) &&
        !copy_lte_raw_token_value(frame, "id", command->cmd_id, sizeof(command->cmd_id))) {
        set_lte_command_parse_status("raw_missing_cmd_id");
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_MISSING_CMD_ID");
        return false;
    }

    char sample_count_text[16] = "";
    char interval_ms_text[16] = "";
    command->sample_count_present =
        copy_lte_raw_kv_value(payload, "sample_count", sample_count_text, sizeof(sample_count_text)) ||
        copy_lte_raw_kv_value(payload, "sample-count", sample_count_text, sizeof(sample_count_text));
    if (command->sample_count_present && !parse_lte_raw_u32(sample_count_text, &command->sample_count, 10)) {
        command->parameters_valid = false;
    }
    command->interval_ms_present =
        copy_lte_raw_kv_value(payload, "interval_ms", interval_ms_text, sizeof(interval_ms_text)) ||
        copy_lte_raw_kv_value(payload, "interval-ms", interval_ms_text, sizeof(interval_ms_text));
    if (command->interval_ms_present && !parse_lte_raw_u32(interval_ms_text, &command->interval_ms, 10)) {
        command->parameters_valid = false;
    }
    command->test_run_id_present =
        copy_lte_raw_kv_value(payload, "test_run_id", command->test_run_id, sizeof(command->test_run_id)) ||
        copy_lte_raw_kv_value(payload, "test-run-id", command->test_run_id, sizeof(command->test_run_id));
    if (strcmp(command->cmd, "capture_imu_window") == 0 &&
        (!command->sample_count_present || !command->interval_ms_present || !command->test_run_id_present ||
         !capture_command_payload_shape_valid(payload) || !imu_window_test_run_id_valid(command->test_run_id))) {
        command->parameters_valid = false;
    }

    s_lte_command_last_command_count = 1;
    set_lte_command_parse_status("raw_command_selected");
    return true;
}

static const lte_executed_command_result_t *find_executed_command_result(const char *cmd_id)
{
    for (size_t index = 0; index < LTE_EXECUTED_COMMAND_CACHE_SIZE; ++index) {
        if (s_lte_executed_command_cache[index].valid &&
            strcmp(s_lte_executed_command_cache[index].cmd_id, cmd_id) == 0) {
            return &s_lte_executed_command_cache[index];
        }
    }
    return NULL;
}

static void remember_executed_command_result(const char *cmd_id, const char *status, const char *message)
{
    lte_executed_command_result_t *entry = &s_lte_executed_command_cache[s_lte_executed_command_cache_next];
    memset(entry, 0, sizeof(*entry));
    snprintf(entry->cmd_id, sizeof(entry->cmd_id), "%s", cmd_id);
    snprintf(entry->status, sizeof(entry->status), "%s", status);
    snprintf(entry->message, sizeof(entry->message), "%s", message);
    entry->valid = true;
    s_lte_executed_command_cache_next =
        (s_lte_executed_command_cache_next + 1u) % LTE_EXECUTED_COMMAND_CACHE_SIZE;
}

#if CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED || CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
static bool wifi_http_ack_raw_command(
    const lte_raw_command_t *command,
    const char *status,
    const char *message,
    bool duplicate_prevented)
{
    char path[192];
    char payload[768];
    char frame[1024];
    uint32_t seq = next_seq();
    const char *ack_test_run_id =
        command->test_run_id_present ? command->test_run_id : CONFIG_EGOLINK_TEST_RUN_ID;
    snprintf(
        payload,
        sizeof(payload),
        "cmd_id=%s\n"
        "status=%s\n"
        "message=%s\n"
        "fw_version=%s\n"
        "test_run_id=%s\n"
        "seq=%" PRIu32 "\n"
        "transport_type=wifi\n"
        "command_last_cmd_id=%s\n"
        "command_parse_status=%s\n"
        "command_count=%d\n"
        "duplicate_local_execution_prevented=%s\n",
        command->cmd_id,
        status,
        message,
        CONFIG_EGOLINK_FW_VERSION,
        ack_test_run_id,
        seq,
        command->cmd_id,
        s_lte_command_parse_status,
        s_lte_command_last_command_count,
        json_bool(duplicate_prevented));
    if (!build_lte_raw_frame(frame, sizeof(frame), "ack", command->cmd_id, seq, payload)) {
        ESP_LOGE(TAG, "WIFI_IMU_WINDOW_RAW_ACK_BUILD_FAILED cmd_id=%s", command->cmd_id);
        return false;
    }
    snprintf(
        path,
        sizeof(path),
        "/api/v1/devices/%s/commands/%s/ack.raw",
        CONFIG_EGOLINK_DEVICE_ID,
        command->cmd_id);
    int http_status = 0;
    bool ok = message_hub_post_raw(path, frame, &http_status);
    ESP_LOGI(
        TAG,
        "WIFI_IMU_WINDOW_RAW_ACK_DONE cmd_id=%s seq=%" PRIu32 " duplicate=%s ok=%s status=%d",
        command->cmd_id,
        seq,
        duplicate_prevented ? "true" : "false",
        ok ? "true" : "false",
        http_status);
    return ok;
}

typedef enum {
    WIFI_IMU_WINDOW_COMMAND_FAILED = 0,
    WIFI_IMU_WINDOW_COMMAND_OK,
    WIFI_IMU_WINDOW_COMMAND_DUPLICATE,
} wifi_imu_window_command_result_t;

static wifi_imu_window_command_result_t wifi_http_execute_and_ack_raw_command(
    const lte_raw_command_t *command)
{
    if (command == NULL || command->cmd_id[0] == '\0') {
        set_lte_command_parse_status("raw_missing_cmd_id");
        return WIFI_IMU_WINDOW_COMMAND_FAILED;
    }
    const lte_executed_command_result_t *cached_result = find_executed_command_result(command->cmd_id);
    bool duplicate = cached_result != NULL;
    const char *status = "rejected";
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
    const char *message =
        "Wi-Fi failover raw command accepts set_report_interval, request_location, or capture_imu_window";
#else
    const char *message = "Wi-Fi failover raw command accepts set_report_interval or capture_imu_window";
#endif
#else
    const char *message = "Wi-Fi IMU window profile accepts only capture_imu_window";
#endif

    ESP_LOGI(
        TAG,
        "WIFI_IMU_WINDOW_RAW_RECEIVED cmd_id=%s cmd=%s duplicate=%s",
        command->cmd_id,
        command->cmd,
        duplicate ? "true" : "false");
    if (!duplicate) {
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
        if (strcmp(command->cmd, "set_report_interval") == 0) {
            status = "ok";
            message = "Wi-Fi failover raw command acknowledged set_report_interval";
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
        } else if (strcmp(command->cmd, "request_location") == 0) {
            bool location_ok = message_hub_publish_location_report(command->cmd_id);
            status = location_ok ? "ok" : "error";
            message = location_ok ? message_hub_wifi_location_ack_message()
                                  : "Wi-Fi failover location_report upload failed";
#endif
        } else
#endif
        if (strcmp(command->cmd, "capture_imu_window") == 0) {
            if (!imu_window_capture_cmd_id_valid(command->cmd_id)) {
                message = "capture_imu_window cmd_id must be 1-16 safe characters";
            } else if (!command->parameters_valid || command->sample_count != IMU_WINDOW_SAMPLE_COUNT ||
                       command->interval_ms != IMU_WINDOW_INTERVAL_MS) {
                message = "capture_imu_window requires exact test_run_id, sample_count=100, and interval_ms=50";
            } else {
                bool window_ok = publish_imu_window(command->cmd_id, command->test_run_id, "wifi");
                status = window_ok ? "ok" : "error";
                if (window_ok) {
                    message = "bounded real IMU window chunks and manifest uploaded over Wi-Fi";
                } else {
                    snprintf(
                        s_lte_command_last_message,
                        sizeof(s_lte_command_last_message),
                        "bounded IMU window failed: %s",
                        s_imu_window_last_error);
                    message = s_lte_command_last_message;
                }
            }
        }
        snprintf(s_lte_command_last_cmd_id, sizeof(s_lte_command_last_cmd_id), "%s", command->cmd_id);
        snprintf(s_lte_command_last_status, sizeof(s_lte_command_last_status), "%s", status);
        if (message != s_lte_command_last_message) {
            snprintf(s_lte_command_last_message, sizeof(s_lte_command_last_message), "%s", message);
        }
        remember_executed_command_result(command->cmd_id, s_lte_command_last_status, s_lte_command_last_message);
    } else {
        status = cached_result->status;
        message = cached_result->message;
        snprintf(s_lte_command_last_cmd_id, sizeof(s_lte_command_last_cmd_id), "%s", command->cmd_id);
        snprintf(s_lte_command_last_status, sizeof(s_lte_command_last_status), "%s", status);
        snprintf(s_lte_command_last_message, sizeof(s_lte_command_last_message), "%s", message);
        ESP_LOGI(TAG, "WIFI_IMU_WINDOW_DUPLICATE_RESULT_REPLAY cmd_id=%s status=%s", command->cmd_id, status);
    }

    if (s_imu_window_service_failed_closed) {
        ESP_LOGE(TAG, "IMU_WINDOW_ACK_SUPPRESSED stop_not_confirmed=true");
        return WIFI_IMU_WINDOW_COMMAND_FAILED;
    }
    bool ack_ok = wifi_http_ack_raw_command(command, status, message, duplicate);
    if (duplicate) {
        return WIFI_IMU_WINDOW_COMMAND_DUPLICATE;
    }
    if (!ack_ok || strcmp(status, "ok") != 0) {
        return WIFI_IMU_WINDOW_COMMAND_FAILED;
    }
    return WIFI_IMU_WINDOW_COMMAND_OK;
}

typedef enum {
    WIFI_IMU_WINDOW_POLL_NO_COMMAND = 0,
    WIFI_IMU_WINDOW_POLL_PARSE_ERROR,
    WIFI_IMU_WINDOW_POLL_COMMAND_OK,
    WIFI_IMU_WINDOW_POLL_COMMAND_FAILED,
    WIFI_IMU_WINDOW_POLL_COMMAND_DUPLICATE,
} wifi_imu_window_poll_result_t;

static const char *wifi_imu_window_poll_result_name(wifi_imu_window_poll_result_t result)
{
    switch (result) {
        case WIFI_IMU_WINDOW_POLL_NO_COMMAND:
            return "no_command";
        case WIFI_IMU_WINDOW_POLL_PARSE_ERROR:
            return "parse_or_http_error";
        case WIFI_IMU_WINDOW_POLL_COMMAND_OK:
            return "command_ok";
        case WIFI_IMU_WINDOW_POLL_COMMAND_FAILED:
            return "command_failed";
        case WIFI_IMU_WINDOW_POLL_COMMAND_DUPLICATE:
            return "command_duplicate";
        default:
            return "unknown";
    }
}

static wifi_imu_window_poll_result_t wifi_http_poll_imu_window_command_once(void)
{
    char path[160];
    char response[2048];
    lte_raw_command_t command;
    snprintf(path, sizeof(path), "/api/v1/devices/%s/commands/poll.raw", CONFIG_EGOLINK_DEVICE_ID);
    int http_status = 0;
    bool poll_ok = message_hub_request(HTTP_METHOD_GET, path, NULL, response, sizeof(response), &http_status);
    s_lte_command_last_command_count = 0;
    set_lte_command_parse_status(poll_ok ? "raw_http_ok_body_received" : "http_poll_failed");
    ESP_LOGI(
        TAG,
        "WIFI_IMU_WINDOW_RAW_POLL_DONE ok=%s status=%d bytes=%u",
        poll_ok ? "true" : "false",
        http_status,
        (unsigned)strlen(response));
    if (!poll_ok) {
        return WIFI_IMU_WINDOW_POLL_PARSE_ERROR;
    }
    if (!parse_lte_raw_command_frame(response, &command)) {
        return strcmp(s_lte_command_parse_status, "raw_no_command") == 0
                   ? WIFI_IMU_WINDOW_POLL_NO_COMMAND
                   : WIFI_IMU_WINDOW_POLL_PARSE_ERROR;
    }
    wifi_imu_window_command_result_t command_result = wifi_http_execute_and_ack_raw_command(&command);
    if (command_result == WIFI_IMU_WINDOW_COMMAND_OK) {
        return WIFI_IMU_WINDOW_POLL_COMMAND_OK;
    }
    if (command_result == WIFI_IMU_WINDOW_COMMAND_DUPLICATE) {
        return WIFI_IMU_WINDOW_POLL_COMMAND_DUPLICATE;
    }
    return WIFI_IMU_WINDOW_POLL_COMMAND_FAILED;
}
#endif

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
static bool lte_http_execute_and_ack_raw_command(
    const lte_raw_command_t *command,
    const sim7670_lte_http_probe_result_t *poll_result)
{
    if (command == NULL || command->cmd_id[0] == '\0') {
        set_lte_command_parse_status("raw_missing_cmd_id");
        return false;
    }
    const lte_executed_command_result_t *cached_result = find_executed_command_result(command->cmd_id);
    bool duplicate = cached_result != NULL;
    const char *status = "ok";
    const char *message = "lte raw command loop acknowledged set_report_interval";

    ESP_LOGI(
        TAG,
        "LTE_HTTP_COMMAND_RAW_RECEIVED cmd_id=%s cmd=%s duplicate=%s",
        command->cmd_id,
        command->cmd,
        duplicate ? "true" : "false");

    if (!duplicate) {
        snprintf(s_lte_command_last_cmd_id, sizeof(s_lte_command_last_cmd_id), "%s", command->cmd_id);
        if (strcmp(command->cmd, "set_report_interval") == 0) {
            status = "ok";
            message = "lte raw command loop acknowledged set_report_interval";
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
        } else if (strcmp(command->cmd, "request_location") == 0) {
            bool location_ok = lte_http_publish_raw_location_report(command->cmd_id);
#if CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED
            bool observation_ok = location_ok ? lte_http_publish_raw_location_observation(command->cmd_id) : false;
            status = (location_ok && observation_ok) ? "ok" : "error";
            message = !location_ok ? "lte raw location_report upload failed"
                                   : (observation_ok ? message_hub_location_ack_message()
                                                     : "lte raw location_observation upload failed");
#else
            status = location_ok ? "ok" : "error";
            message = location_ok ? message_hub_location_ack_message() : "lte raw location_report upload failed";
#endif
#endif
        } else if (strcmp(command->cmd, "capture_imu_window") == 0) {
            if (!imu_window_capture_cmd_id_valid(command->cmd_id)) {
                status = "rejected";
                message = "capture_imu_window cmd_id must be 1-16 safe characters";
            } else if (!command->parameters_valid || command->sample_count != IMU_WINDOW_SAMPLE_COUNT ||
                command->interval_ms != IMU_WINDOW_INTERVAL_MS) {
                status = "rejected";
                message = "capture_imu_window requires exact test_run_id, sample_count=100, and interval_ms=50";
            } else {
                bool window_ok = publish_imu_window(command->cmd_id, command->test_run_id, "lte");
                status = window_ok ? "ok" : "error";
                if (window_ok) {
                    message = "bounded real IMU window chunks and manifest uploaded";
                } else {
                    snprintf(
                        s_lte_command_last_message,
                        sizeof(s_lte_command_last_message),
                        "bounded IMU window failed: %s",
                        s_imu_window_last_error);
                    message = s_lte_command_last_message;
                }
            }
        } else {
            status = "rejected";
            message = "lte raw command loop accepts set_report_interval, request_location, or capture_imu_window";
        }
        snprintf(s_lte_command_last_status, sizeof(s_lte_command_last_status), "%s", status);
        if (message != s_lte_command_last_message) {
            snprintf(s_lte_command_last_message, sizeof(s_lte_command_last_message), "%s", message);
        }
        remember_executed_command_result(command->cmd_id, s_lte_command_last_status, s_lte_command_last_message);
    } else {
        status = cached_result->status;
        message = cached_result->message;
        snprintf(s_lte_command_last_cmd_id, sizeof(s_lte_command_last_cmd_id), "%s", command->cmd_id);
        snprintf(s_lte_command_last_status, sizeof(s_lte_command_last_status), "%s", status);
        snprintf(s_lte_command_last_message, sizeof(s_lte_command_last_message), "%s", message);
        ESP_LOGI(
            TAG,
            "LTE_HTTP_COMMAND_DUPLICATE_RESULT_REPLAY cmd_id=%s status=%s",
            command->cmd_id,
            status);
    }

    if (s_imu_window_service_failed_closed) {
        ESP_LOGE(TAG, "IMU_WINDOW_ACK_SUPPRESSED stop_not_confirmed=true");
        return false;
    }

    const char *ack_test_run_id =
        command->test_run_id_present ? command->test_run_id : CONFIG_EGOLINK_TEST_RUN_ID;
    return lte_http_ack_command(command->cmd_id, ack_test_run_id, status, message, poll_result, duplicate);
}

static bool lte_http_poll_commands_once(
    sim7670_lte_http_probe_result_t *poll_result,
    bool *transport_ok)
{
    char path[160];
    char url[256];
    char response[2048];
    lte_raw_command_t command;
    sim7670_lte_http_probe_result_t local_poll_result;
    if (poll_result == NULL) {
        poll_result = &local_poll_result;
    }

    snprintf(path, sizeof(path), "/api/v1/devices/%s/commands/poll.raw", CONFIG_EGOLINK_DEVICE_ID);
    build_message_hub_url(url, sizeof(url), path);
    bool poll_ok =
        sim7670_lte_http_get_raw(url, CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN, response, sizeof(response), poll_result);
    if (transport_ok != NULL) {
        *transport_ok = poll_ok;
    }
    s_lte_command_last_command_count = 0;
    set_lte_command_parse_status(poll_ok ? "raw_http_ok_body_received" : "http_poll_failed");
    ESP_LOGI(
        TAG,
        "LTE_HTTP_COMMAND_RAW_POLL_DONE ok=%s reason=%s status=%d data_len=%d",
        poll_ok ? "true" : "false",
        poll_result->reason_code,
        poll_result->status_code,
        poll_result->data_len);
    if (!poll_ok) {
        return false;
    }
    if (!parse_lte_raw_command_frame(response, &command)) {
        return false;
    }
    return lte_http_execute_and_ack_raw_command(&command, poll_result);
}

#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
static bool lte_wifi_failover_transport_threshold_reached(bool transport_ok)
{
    if (transport_ok) {
        s_lte_transport_consecutive_failures = 0;
    } else if (s_lte_transport_consecutive_failures < CONFIG_EGOLINK_LTE_WIFI_FAILOVER_FAILURE_THRESHOLD) {
        s_lte_transport_consecutive_failures += 1;
    }
    ESP_LOGI(
        TAG,
        "LTE_WIFI_FAILOVER_HEALTH transport_ok=%s consecutive_failures=%d threshold=%d",
        transport_ok ? "true" : "false",
        s_lte_transport_consecutive_failures,
        CONFIG_EGOLINK_LTE_WIFI_FAILOVER_FAILURE_THRESHOLD);
    return !transport_ok &&
           s_lte_transport_consecutive_failures >= CONFIG_EGOLINK_LTE_WIFI_FAILOVER_FAILURE_THRESHOLD;
}
#endif

static void lte_http_command_task(void *arg)
{
    (void)arg;
    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_command_loop");
    bool lte_ready = wait_for_lte_ready_for_http_probe();
    ESP_LOGI(TAG, "LTE_HTTP_COMMAND_READY_RESULT ready=%s", lte_ready ? "true" : "false");
    if (!lte_ready) {
        platform_power_leave_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_command_lte_not_ready");
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
        (void)lte_wifi_failover_run_once("lte_attach_timeout");
#else
        platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_http_command_done");
#endif
        vTaskDelete(NULL);
        return;
    }
    platform_power_leave_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_command_lte_ready");
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "lte_http_command_poll");
    (void)lte_http_post_command_diag("ready", NULL, false, false);

    int max_attempts = CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS;
    if (max_attempts < 1) {
        max_attempts = 1;
    }
    bool acked = false;
#if CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED
    int64_t next_periodic_location_ms = 0;
    for (int attempt = 1;; ++attempt) {
        sim7670_lte_http_probe_result_t poll_result;
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_POLL_ROUND_START attempt=%d max_attempts=%d periodic_location=true", attempt, max_attempts);
        bool poll_transport_ok = false;
        bool round_acked = lte_http_poll_commands_once(&poll_result, &poll_transport_ok);
        acked = acked || round_acked;
        (void)lte_http_post_command_diag(round_acked ? "command_ack_observed" : "poll_no_ack", &poll_result, true, round_acked);
        ESP_LOGI(
            TAG,
            "LTE_HTTP_COMMAND_POLL_ROUND_DONE attempt=%d acked=%s cumulative_acked=%s",
            attempt,
            round_acked ? "true" : "false",
            acked ? "true" : "false");
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
        if (lte_wifi_failover_transport_threshold_reached(poll_transport_ok)) {
            platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "lte_wifi_failover_transport_threshold");
            (void)lte_wifi_failover_run_once("lte_http_poll_failures");
            vTaskDelete(NULL);
            return;
        }
#endif
        if (s_imu_window_service_failed_closed) {
            ESP_LOGE(TAG, "IMU_WINDOW_SERVICE_FAIL_CLOSED stop_not_confirmed=true");
            break;
        }

        int64_t now_ms = uptime_ms();
        if (now_ms >= next_periodic_location_ms) {
            bool location_ok = lte_http_publish_d1_periodic_location_once();
            ESP_LOGI(TAG, "LTE_HTTP_D1_PERIODIC_LOCATION_SCHEDULED ok=%s", location_ok ? "true" : "false");
            next_periodic_location_ms = uptime_ms() + (int64_t)CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_INTERVAL_SEC * 1000;
        }

        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_INTERVAL_SEC * 1000));
    }
#else
    for (int attempt = 1; attempt <= max_attempts; ++attempt) {
        sim7670_lte_http_probe_result_t poll_result;
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_POLL_ROUND_START attempt=%d max_attempts=%d", attempt, max_attempts);
        bool poll_transport_ok = false;
        acked = lte_http_poll_commands_once(&poll_result, &poll_transport_ok);
        (void)lte_http_post_command_diag(acked ? "command_ack_observed" : "poll_no_ack", &poll_result, true, acked);
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_POLL_ROUND_DONE attempt=%d acked=%s", attempt, acked ? "true" : "false");
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
        if (lte_wifi_failover_transport_threshold_reached(poll_transport_ok)) {
            platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "lte_wifi_failover_transport_threshold");
            (void)lte_wifi_failover_run_once("lte_http_poll_failures");
            vTaskDelete(NULL);
            return;
        }
#endif
        if (s_imu_window_service_failed_closed) {
            ESP_LOGE(TAG, "IMU_WINDOW_SERVICE_FAIL_CLOSED stop_not_confirmed=true");
            break;
        }
        if (acked) {
            break;
        }
        if (attempt < max_attempts) {
            vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_INTERVAL_SEC * 1000));
        }
    }

    platform_power_leave_state(
        PLATFORM_POWER_STATE_UPLOAD,
        acked ? "lte_http_command_ack_ok" : "lte_http_command_ack_missing");
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_http_command_done");
    vTaskDelete(NULL);
#endif
}
#endif
#endif
#endif

static bool wifi_failover_owner_active(void)
{
#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
    return s_lte_wifi_failover_state == LTE_WIFI_FAILOVER_WIFI_ACTIVE;
#else
    return false;
#endif
}

static const char *message_hub_runtime_link_type(void)
{
    return wifi_failover_owner_active() ? "wifi_failover" : "mock_4g_over_wifi";
}

static const char *message_hub_runtime_modem_state(void)
{
    return wifi_failover_owner_active() ? "lte_transport_failed_wifi_active" : "mock_data_ready";
}

static const char *message_hub_runtime_gnss_state(void)
{
    return wifi_failover_owner_active() ? "unknown" : "mock_fix";
}

static void build_status_payload(char *buffer, size_t buffer_size, uint32_t seq)
{
    int rssi = refresh_wifi_rssi();
    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
    char battery_mv[16];
    json_int_or_null(battery_mv, sizeof(battery_mv), power.battery_voltage_valid, power.battery_millivolt);
    build_lte_observation_fragment(s_status_lte_fragment, sizeof(s_status_lte_fragment));
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"status\","
        "\"fw_version\":\"%s\","
        "\"hw_target\":\"waveshare_esp32s3_sim7670g_4g\","
        "\"battery\":%d,"
        "\"battery_mv\":%s,"
        "\"charging\":%s,"
        "\"battery_source\":\"%s\","
        "\"charging_source\":\"%s\","
        "\"power_state\":\"%s\","
        "\"power_state_elapsed_ms\":%" PRId64 ","
        "\"power_state_cumulative_ms\":%" PRId64 ","
        "\"power_marker_seq\":%" PRIu32 ","
        "\"power_serial_marker_id\":\"%s\","
        "\"power_gpio_marker_id\":\"%s\","
        "\"power_gpio_marker_enabled\":%s,"
        "\"reset_reason\":\"%s\","
        "\"boot_count\":%" PRIu32 ","
        "\"boot_uptime_ms\":%" PRId64 ","
        "\"link_type\":\"%s\","
        "\"rssi\":%d,"
        "\"modem_state\":\"%s\","
        "\"gnss_state\":\"%s\","
        "\"guard_mode\":\"child_safety\","
        "\"queue_size\":0"
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        power.battery_percent,
        battery_mv,
        json_bool(power.charging),
        power.battery_source,
        power.charging_source,
        platform_power_state_name(power.state),
        power.state_elapsed_ms,
        power.state_cumulative_ms,
        power.marker.seq,
        power.marker.serial_marker_id,
        power.marker.gpio_marker_id,
        json_bool(power.marker.gpio_marker_enabled),
        s_reset_reason,
        s_boot_count,
        uptime_ms(),
        message_hub_runtime_link_type(),
        rssi,
        message_hub_runtime_modem_state(),
        message_hub_runtime_gnss_state(),
        s_status_lte_fragment);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static void build_sensor_payload(char *buffer, size_t buffer_size, uint32_t seq)
{
    int64_t now_ms = uptime_ms();
    int rssi = refresh_wifi_rssi();
    uint32_t free_heap = esp_get_free_heap_size();
    uint32_t min_free_heap = esp_get_minimum_free_heap_size();
    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
    char battery_mv[16];
    json_int_or_null(battery_mv, sizeof(battery_mv), power.battery_voltage_valid, power.battery_millivolt);
    platform_imu_snapshot_t imu;
    platform_imu_sample();
    platform_imu_get_snapshot(&imu);
    build_lte_observation_fragment(s_sensor_lte_fragment, sizeof(s_sensor_lte_fragment));
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"event\","
        "\"event_type\":\"sensor_sample\","
        "\"priority\":\"normal\","
        "\"source\":\"esp32_runtime\","
        "\"sensor_kind\":\"device_health\","
        "\"uptime_ms\":%" PRId64 ","
        "\"wifi_rssi\":%d,"
        "\"free_heap_bytes\":%" PRIu32 ","
        "\"min_free_heap_bytes\":%" PRIu32 ","
        "\"battery\":%d,"
        "\"battery_mv\":%s,"
        "\"charging\":%s,"
        "\"battery_source\":\"%s\","
        "\"charging_source\":\"%s\","
        "\"power_state\":\"%s\","
        "\"power_state_elapsed_ms\":%" PRId64 ","
        "\"power_state_cumulative_ms\":%" PRId64 ","
        "\"power_marker_seq\":%" PRIu32 ","
        "\"power_serial_marker_id\":\"%s\","
        "\"power_gpio_marker_id\":\"%s\","
        "\"power_gpio_marker_enabled\":%s,"
        "\"reset_reason\":\"%s\","
        "\"boot_count\":%" PRIu32 ","
        "\"imu_source\":\"%s\","
        "\"imu_hardware_present\":%s,"
        "\"imu_driver_enabled\":%s,"
        "\"imu_sample_mock\":%s,"
        "\"imu_ring_capacity\":%u,"
        "\"imu_ring_count\":%u,"
        "\"imu_dropped_samples\":%" PRIu32 ","
        "\"imu_latest_seq\":%" PRIu32 ","
        "\"imu_latest_uptime_ms\":%" PRId64 ","
        "\"imu_accel_mg_x\":%d,"
        "\"imu_accel_mg_y\":%d,"
        "\"imu_accel_mg_z\":%d,"
        "\"imu_gyro_mdps_x\":%d,"
        "\"imu_gyro_mdps_y\":%d,"
        "\"imu_gyro_mdps_z\":%d,"
        "\"link_type\":\"%s\","
        "\"modem_state\":\"%s\","
        "\"gnss_state\":\"%s\""
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        now_ms,
        seq,
        now_ms,
        rssi,
        free_heap,
        min_free_heap,
        power.battery_percent,
        battery_mv,
        json_bool(power.charging),
        power.battery_source,
        power.charging_source,
        platform_power_state_name(power.state),
        power.state_elapsed_ms,
        power.state_cumulative_ms,
        power.marker.seq,
        power.marker.serial_marker_id,
        power.marker.gpio_marker_id,
        json_bool(power.marker.gpio_marker_enabled),
        s_reset_reason,
        s_boot_count,
        imu.source,
        json_bool(imu.hardware_present),
        json_bool(imu.driver_enabled),
        json_bool(imu.data_is_mock || imu.latest.sample_is_mock),
        (unsigned)imu.ring_capacity,
        (unsigned)imu.ring_count,
        imu.dropped_samples,
        imu.latest.seq,
        imu.latest.uptime_ms,
        imu.latest.accel_mg_x,
        imu.latest.accel_mg_y,
        imu.latest.accel_mg_z,
        imu.latest.gyro_mdps_x,
        imu.latest.gyro_mdps_y,
        imu.latest.gyro_mdps_z,
        message_hub_runtime_link_type(),
        message_hub_runtime_modem_state(),
        message_hub_runtime_gnss_state(),
        s_sensor_lte_fragment);
    append_test_run_id_and_close_json(buffer, buffer_size);
}

static void publish_heartbeat(void)
{
    static char payload[3072];
    uint32_t seq = next_seq();
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "status_publish");
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
    char path[160];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/heartbeat", CONFIG_EGOLINK_DEVICE_ID);
    platform_power_mark("UPLOAD_STATUS", "message_hub_http");
    build_status_payload(payload, sizeof(payload), seq);
    bool ok = message_hub_post_json(path, payload, "HEARTBEAT", seq);
    platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, ok ? "status_http_ok" : "status_http_fail");
#else
    platform_power_mark("UPLOAD_STATUS", CONFIG_EGOLINK_STATUS_TOPIC);
    build_status_payload(payload, sizeof(payload), seq);

    int msg_id = esp_mqtt_client_publish(
        s_mqtt_client,
        CONFIG_EGOLINK_STATUS_TOPIC,
        payload,
        0,
        1,
        0);
    if (msg_id >= 0) {
        ESP_LOGI(
            TAG,
            "MQTT_HEARTBEAT_PUBLISH_OK seq=%" PRIu32 " msg_id=%d topic=%s payload=%s",
            seq,
            msg_id,
            CONFIG_EGOLINK_STATUS_TOPIC,
            payload);
        platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "status_publish_ok");
    } else {
        ESP_LOGE(TAG, "MQTT_HEARTBEAT_PUBLISH_FAIL seq=%" PRIu32 " rc=%d", seq, msg_id);
        platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "status_publish_fail");
    }
#endif
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "status_publish_done");
}

static void publish_sensor_sample(void)
{
    static char payload[4096];
    uint32_t seq = next_seq();
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "sensor_publish");
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
    char path[160];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/telemetry", CONFIG_EGOLINK_DEVICE_ID);
    platform_power_mark("UPLOAD_SENSOR", "message_hub_http");
    build_sensor_payload(payload, sizeof(payload), seq);
    bool ok = message_hub_post_json(path, payload, "TELEMETRY", seq);
    platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, ok ? "sensor_http_ok" : "sensor_http_fail");
#else
    platform_power_mark("UPLOAD_SENSOR", CONFIG_EGOLINK_EVENT_TOPIC);
    build_sensor_payload(payload, sizeof(payload), seq);

    int msg_id = esp_mqtt_client_publish(
        s_mqtt_client,
        CONFIG_EGOLINK_EVENT_TOPIC,
        payload,
        0,
        1,
        0);
    if (msg_id >= 0) {
        ESP_LOGI(
            TAG,
            "MQTT_SENSOR_PUBLISH_OK seq=%" PRIu32 " msg_id=%d topic=%s payload=%s",
            seq,
            msg_id,
            CONFIG_EGOLINK_EVENT_TOPIC,
            payload);
        platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "sensor_publish_ok");
    } else {
        ESP_LOGE(TAG, "MQTT_SENSOR_PUBLISH_FAIL seq=%" PRIu32 " rc=%d", seq, msg_id);
        platform_power_leave_state(PLATFORM_POWER_STATE_UPLOAD, "sensor_publish_fail");
    }
#endif
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "sensor_publish_done");
}

static void run_platform_imu_boot_capture(void)
{
#if CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT > 0
    ESP_LOGI(
        TAG,
        "PLATFORM_IMU_BOOT_CAPTURE_START count=%d interval_ms=%d",
        CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT,
        CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_INTERVAL_MS);
    for (int i = 0; i < CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT; ++i) {
        platform_imu_sample();
        platform_imu_snapshot_t imu;
        platform_imu_get_snapshot(&imu);
        ESP_LOGI(
            TAG,
            "PLATFORM_IMU_BOOT_CAPTURE_SAMPLE index=%d seq=%" PRIu32
            " source=%s hardware_present=%s driver_enabled=%s mock=%s"
            " accel_mg=%d,%d,%d gyro_mdps=%d,%d,%d",
            i,
            imu.latest.seq,
            imu.latest.source,
            json_bool(imu.hardware_present),
            json_bool(imu.driver_enabled),
            json_bool(imu.data_is_mock || imu.latest.sample_is_mock),
            imu.latest.accel_mg_x,
            imu.latest.accel_mg_y,
            imu.latest.accel_mg_z,
            imu.latest.gyro_mdps_x,
            imu.latest.gyro_mdps_y,
            imu.latest.gyro_mdps_z);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_INTERVAL_MS));
    }
    ESP_LOGI(TAG, "PLATFORM_IMU_BOOT_CAPTURE_DONE count=%d", CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT);
#endif
}

static void heartbeat_task(void *arg)
{
    (void)arg;
    while (true) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            UPLINK_READY_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        if (bits & UPLINK_READY_BIT) {
            publish_heartbeat();
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_HEARTBEAT_INTERVAL_SEC * 1000));
    }
}

static void sensor_task(void *arg)
{
    (void)arg;
    while (true) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            UPLINK_READY_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        if (bits & UPLINK_READY_BIT) {
            publish_sensor_sample();
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC * 1000));
    }
}

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
static void command_poll_task(void *arg)
{
    (void)arg;
#if CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED
    int successful_commands = 0;
    for (int attempt = 1; attempt <= CONFIG_EGOLINK_WIFI_IMU_WINDOW_POLL_MAX_ATTEMPTS; ++attempt) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            WIFI_CONNECTED_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        wifi_imu_window_poll_result_t result = WIFI_IMU_WINDOW_POLL_PARSE_ERROR;
        if (bits & WIFI_CONNECTED_BIT) {
            result = wifi_http_poll_imu_window_command_once();
        }
        if (result == WIFI_IMU_WINDOW_POLL_COMMAND_OK) {
            ++successful_commands;
        }
        ESP_LOGI(
            TAG,
            "WIFI_IMU_WINDOW_POLL_ROUND_DONE attempt=%d max_attempts=%d successful_commands=%d max_successful_commands=%d result=%s",
            attempt,
            CONFIG_EGOLINK_WIFI_IMU_WINDOW_POLL_MAX_ATTEMPTS,
            successful_commands,
            CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS,
            wifi_imu_window_poll_result_name(result));
        bool terminal_result = result != WIFI_IMU_WINDOW_POLL_NO_COMMAND &&
                               result != WIFI_IMU_WINDOW_POLL_COMMAND_OK;
        if (terminal_result || s_imu_window_service_failed_closed ||
            successful_commands >= CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS) {
            break;
        }
        if (attempt < CONFIG_EGOLINK_WIFI_IMU_WINDOW_POLL_MAX_ATTEMPTS) {
            vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_MESSAGE_HUB_COMMAND_POLL_INTERVAL_SEC * 1000));
        }
    }
    ESP_LOGI(
        TAG,
        "WIFI_IMU_WINDOW_COMMAND_TASK_DONE successful_commands=%d max_successful_commands=%d",
        successful_commands,
        CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS);
    vTaskDelete(NULL);
#else
    while (true) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            WIFI_CONNECTED_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        if (bits & WIFI_CONNECTED_BIT) {
            message_hub_poll_commands();
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_MESSAGE_HUB_COMMAND_POLL_INTERVAL_SEC * 1000));
    }
#endif
}
#endif

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_err_t connect_err = esp_wifi_connect();
        if (connect_err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_CONNECT_REQUEST_FAIL phase=sta_start err=%s", esp_err_to_name(connect_err));
            xEventGroupSetBits(s_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT | MQTT_CONNECTED_BIT);
        if (s_wifi_retry_count < WIFI_MAX_RETRY) {
            ESP_LOGW(TAG, "Wi-Fi disconnected; retry %d/%d", s_wifi_retry_count + 1, WIFI_MAX_RETRY);
            esp_err_t connect_err = esp_wifi_connect();
            if (connect_err == ESP_OK) {
                s_wifi_retry_count++;
            } else {
                ESP_LOGE(TAG, "WIFI_CONNECT_REQUEST_FAIL phase=retry err=%s", esp_err_to_name(connect_err));
                s_wifi_retry_count = WIFI_MAX_RETRY;
                xEventGroupSetBits(s_event_group, WIFI_FAIL_BIT);
            }
        } else {
            ESP_LOGE(TAG, "MQTT_HEARTBEAT_WIFI_FAIL");
            xEventGroupSetBits(s_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            s_last_rssi = ap_info.rssi;
        }
        ESP_LOGI(TAG, "MQTT_HEARTBEAT_WIFI_OK ip=" IPSTR " rssi=%d", IP2STR(&event->ip_info.ip), s_last_rssi);
        s_wifi_retry_count = 0;
        xEventGroupClearBits(s_event_group, WIFI_FAIL_BIT);
        xEventGroupSetBits(s_event_group, WIFI_CONNECTED_BIT);
    }
}

static esp_err_t start_wifi(void)
{
    EventBits_t existing_bits = xEventGroupGetBits(s_event_group);
    if (s_wifi_started && (existing_bits & WIFI_CONNECTED_BIT) != 0) {
        return ESP_OK;
    }

    s_wifi_retry_count = 0;
    xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT | WIFI_FAIL_BIT | MQTT_CONNECTED_BIT);

    esp_err_t err = ESP_OK;
    if (!s_wifi_initialized) {
        err = esp_netif_init();
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=netif err=%s", esp_err_to_name(err));
            return err;
        }
        err = esp_event_loop_create_default();
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=event_loop err=%s", esp_err_to_name(err));
            return err;
        }
        if (esp_netif_create_default_wifi_sta() == NULL) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=default_sta");
            return ESP_FAIL;
        }

        wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
        err = esp_wifi_init(&init_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=driver err=%s", esp_err_to_name(err));
            return err;
        }
        err = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=wifi_handler err=%s", esp_err_to_name(err));
            return err;
        }
        err = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=ip_handler err=%s", esp_err_to_name(err));
            return err;
        }

        wifi_config_t wifi_config = {0};
        strlcpy((char *)wifi_config.sta.ssid, CONFIG_EGOLINK_WIFI_SSID, sizeof(wifi_config.sta.ssid));
        strlcpy((char *)wifi_config.sta.password, CONFIG_EGOLINK_WIFI_PASSWORD, sizeof(wifi_config.sta.password));
        wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

        err = esp_wifi_set_mode(WIFI_MODE_STA);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=mode err=%s", esp_err_to_name(err));
            return err;
        }
        err = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=config err=%s", esp_err_to_name(err));
            return err;
        }
        s_wifi_initialized = true;
    }

    if (!s_wifi_started) {
        err = esp_wifi_start();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_INIT_FAIL phase=start err=%s", esp_err_to_name(err));
            return err;
        }
        s_wifi_started = true;
    } else {
        err = esp_wifi_connect();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WIFI_CONNECT_REQUEST_FAIL phase=restart err=%s", esp_err_to_name(err));
            return err;
        }
    }

    EventBits_t bits = xEventGroupWaitBits(
        s_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(20000));
    if ((bits & WIFI_CONNECTED_BIT) == 0) {
        ESP_LOGE(TAG, "WIFI_CONNECT_BOUNDED_FAIL timeout_ms=20000");
        esp_err_t stop_err = esp_wifi_stop();
        if (stop_err != ESP_OK) {
            ESP_LOGW(TAG, "WIFI_STOP_AFTER_FAIL err=%s", esp_err_to_name(stop_err));
        }
        s_wifi_started = false;
        return ESP_FAIL;
    }
    return ESP_OK;
}

#if CONFIG_EGOLINK_LTE_WIFI_FAILOVER_ENABLED
static const char *lte_wifi_failover_state_name(lte_wifi_failover_state_t state)
{
    switch (state) {
        case LTE_WIFI_FAILOVER_LTE_PRIMARY:
            return "lte_primary";
        case LTE_WIFI_FAILOVER_WIFI_CONNECTING:
            return "wifi_connecting";
        case LTE_WIFI_FAILOVER_WIFI_ACTIVE:
            return "wifi_active";
        case LTE_WIFI_FAILOVER_OFFLINE:
            return "offline";
        default:
            return "unknown";
    }
}

static void lte_wifi_failover_transition(lte_wifi_failover_state_t next_state, const char *reason)
{
    ESP_LOGW(
        TAG,
        "LTE_WIFI_FAILOVER_TRANSITION from=%s to=%s reason=%s one_way=true",
        lte_wifi_failover_state_name(s_lte_wifi_failover_state),
        lte_wifi_failover_state_name(next_state),
        reason ? reason : "unspecified");
    s_lte_wifi_failover_state = next_state;
}

static bool lte_wifi_failover_config_valid(void)
{
    return CONFIG_EGOLINK_WIFI_SSID[0] != '\0' && CONFIG_EGOLINK_WIFI_PASSWORD[0] != '\0';
}

static void lte_wifi_failover_run_wifi_owner(void)
{
    int64_t next_command_poll_ms = 0;
    int64_t next_heartbeat_ms = 0;
    int64_t next_sensor_ms = 0;
#if CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED && CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
    int64_t next_periodic_location_ms = 0;
    uint32_t periodic_location_index = 0;
#endif

    while (true) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            pdMS_TO_TICKS(1000));
        if ((bits & WIFI_FAIL_BIT) != 0 && (bits & WIFI_CONNECTED_BIT) == 0) {
            ESP_LOGE(TAG, "LTE_WIFI_FAILOVER_WIFI_OWNER_STOP reason=wifi_retry_exhausted");
            return;
        }
        if ((bits & WIFI_CONNECTED_BIT) == 0) {
            continue;
        }

        int64_t now_ms = uptime_ms();
        if (now_ms >= next_command_poll_ms) {
            wifi_imu_window_poll_result_t command_result = wifi_http_poll_imu_window_command_once();
            ESP_LOGI(
                TAG,
                "LTE_WIFI_FAILOVER_WIFI_RAW_COMMAND result=%s",
                wifi_imu_window_poll_result_name(command_result));
            if (s_imu_window_service_failed_closed) {
                ESP_LOGE(TAG, "LTE_WIFI_FAILOVER_WIFI_OWNER_STOP reason=imu_window_fail_closed");
                return;
            }
            next_command_poll_ms = uptime_ms() +
                                   (int64_t)CONFIG_EGOLINK_MESSAGE_HUB_COMMAND_POLL_INTERVAL_SEC * 1000;
        }
        now_ms = uptime_ms();
        if (now_ms >= next_heartbeat_ms) {
            publish_heartbeat();
            next_heartbeat_ms = uptime_ms() + (int64_t)CONFIG_EGOLINK_HEARTBEAT_INTERVAL_SEC * 1000;
        }
        now_ms = uptime_ms();
        if (now_ms >= next_sensor_ms) {
            publish_sensor_sample();
            next_sensor_ms = uptime_ms() + (int64_t)CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC * 1000;
        }
#if CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED && CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
        now_ms = uptime_ms();
        if (now_ms >= next_periodic_location_ms) {
            char cmd_id[64];
            periodic_location_index += 1;
            snprintf(cmd_id, sizeof(cmd_id), "d1-wifi-periodic-%" PRIu32, periodic_location_index);
            bool location_ok = message_hub_publish_location_report(cmd_id);
            ESP_LOGI(
                TAG,
                "LTE_WIFI_FAILOVER_WIFI_PERIODIC_LOCATION index=%" PRIu32 " ok=%s",
                periodic_location_index,
                location_ok ? "true" : "false");
            next_periodic_location_ms = uptime_ms() +
                                        (int64_t)CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_INTERVAL_SEC * 1000;
        }
#endif
        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

static bool lte_wifi_failover_run_once(const char *reason)
{
    if (s_lte_wifi_failover_latched) {
        ESP_LOGE(
            TAG,
            "LTE_WIFI_FAILOVER_REJECTED state=%s reason=already_latched",
            lte_wifi_failover_state_name(s_lte_wifi_failover_state));
        return false;
    }
    s_lte_wifi_failover_latched = true;

    if (!lte_wifi_failover_config_valid()) {
        lte_wifi_failover_transition(LTE_WIFI_FAILOVER_OFFLINE, "wifi_config_missing");
        platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_wifi_failover_config_missing");
        return false;
    }

    lte_wifi_failover_transition(LTE_WIFI_FAILOVER_WIFI_CONNECTING, reason);
    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_wifi_failover_wifi_connect");
    esp_err_t wifi_err = start_wifi();
    platform_power_leave_state(
        PLATFORM_POWER_STATE_NETWORK_ATTACH,
        wifi_err == ESP_OK ? "lte_wifi_failover_wifi_connected" : "lte_wifi_failover_wifi_failed");
    if (wifi_err != ESP_OK) {
        lte_wifi_failover_transition(LTE_WIFI_FAILOVER_OFFLINE, "wifi_connect_failed");
        platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_wifi_failover_offline");
        return false;
    }

    lte_wifi_failover_transition(LTE_WIFI_FAILOVER_WIFI_ACTIVE, reason);
    message_hub_register_device();
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_wifi_failover_wifi_active");
    lte_wifi_failover_run_wifi_owner();

    if (s_wifi_started) {
        esp_err_t stop_err = esp_wifi_stop();
        if (stop_err != ESP_OK) {
            ESP_LOGW(TAG, "WIFI_STOP_AFTER_FAILOVER_OWNER err=%s", esp_err_to_name(stop_err));
        }
        s_wifi_started = false;
    }
    lte_wifi_failover_transition(LTE_WIFI_FAILOVER_OFFLINE, "wifi_retry_exhausted");
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_wifi_failover_offline");
    return false;
}
#endif

#if !CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT_HEARTBEAT_MQTT_CONNECTED broker=%s", CONFIG_EGOLINK_MQTT_BROKER_URI);
        xEventGroupSetBits(s_event_group, MQTT_CONNECTED_BIT);
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT_HEARTBEAT_MQTT_DISCONNECTED");
        xEventGroupClearBits(s_event_group, MQTT_CONNECTED_BIT);
        break;
    case MQTT_EVENT_PUBLISHED:
        ESP_LOGI(TAG, "MQTT_HEARTBEAT_MQTT_PUBLISHED msg_id=%d", event->msg_id);
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT_HEARTBEAT_MQTT_ERROR");
        break;
    default:
        break;
    }
}

static void start_mqtt(void)
{
    const esp_mqtt_client_config_t mqtt_config = {
        .broker.address.uri = CONFIG_EGOLINK_MQTT_BROKER_URI,
    };
    s_mqtt_client = esp_mqtt_client_init(&mqtt_config);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(s_mqtt_client));
}
#endif

void app_main(void)
{
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
    const char *transport_configuration_error = message_hub_transport_configuration_error();
    if (transport_configuration_error != NULL) {
        ESP_LOGE(
            TAG,
            "MESSAGE_HUB_HTTPS_CONFIG_REJECTED reason=%s network_started=false payload_sent=false",
            transport_configuration_error);
        return;
    }
#endif
    ESP_LOGI(
        TAG,
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
        "MESSAGE_HUB_BOOT device_id=%s tls_host=%s tls_chain_verify=esp_crt_bundle tls_hostname_verify=true",
        CONFIG_EGOLINK_DEVICE_ID,
        CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST);
#else
        "MQTT_HEARTBEAT_BOOT device_id=%s status_topic=%s event_topic=%s",
        CONFIG_EGOLINK_DEVICE_ID,
        CONFIG_EGOLINK_STATUS_TOPIC,
        CONFIG_EGOLINK_EVENT_TOPIC);
#endif

    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_ret);
    init_boot_diagnostics();

    s_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(s_event_group == NULL ? ESP_ERR_NO_MEM : ESP_OK);
    ESP_ERROR_CHECK(platform_power_init() ? ESP_OK : ESP_FAIL);
    ESP_ERROR_CHECK(platform_imu_init() ? ESP_OK : ESP_FAIL);
    run_platform_imu_boot_capture();
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && \
    (CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED) && \
    CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    platform_imu_snapshot_t idle_imu;
    platform_imu_get_snapshot(&idle_imu);
    if (idle_imu.backend != PLATFORM_IMU_BACKEND_QMI8658 || !idle_imu.hardware_present || !idle_imu.driver_enabled) {
        ESP_LOGW(TAG, "IMU_WINDOW_IDLE_REAL_IMU_UNAVAILABLE command_will_reject_capture=true");
    } else if (platform_imu_capture_end()) {
        ESP_LOGI(TAG, "IMU_WINDOW_IDLE_MEASUREMENT_STOPPED");
    } else {
        s_imu_window_service_failed_closed = true;
        ESP_LOGE(TAG, "IMU_WINDOW_IDLE_MEASUREMENT_STOP_FAILED service_failed_closed=true");
    }
#endif
    platform_power_enter_state(PLATFORM_POWER_STATE_BOOT, "app_main");
    ESP_ERROR_CHECK(safety_model_init() ? ESP_OK : ESP_FAIL);
    ESP_LOGI(TAG, "SAFETY_MODEL_INIT_OK version=%s mock=true", safety_model_version());

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && \
    (CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED || CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED)
    if (s_imu_window_service_failed_closed) {
        ESP_LOGE(TAG, "IMU_WINDOW_COMMAND_SERVICE_NOT_STARTED stop_not_confirmed=true");
        return;
    }
#endif

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
    BaseType_t lte_command_task_created =
        xTaskCreate(lte_http_command_task, "lte_http_command_task", LTE_HTTP_COMMAND_TASK_STACK_SIZE, NULL, 5, NULL);
    ESP_ERROR_CHECK(lte_command_task_created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
#elif CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED
    BaseType_t lte_probe_task_created =
        xTaskCreate(lte_http_probe_task, "lte_http_probe_task", LTE_HTTP_PROBE_TASK_STACK_SIZE, NULL, 5, NULL);
    ESP_ERROR_CHECK(lte_probe_task_created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
#else
    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "wifi_connect");
    ESP_ERROR_CHECK(start_wifi());
    platform_power_leave_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "wifi_connected");
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
    message_hub_register_device();
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "message_hub_http_ready");
    xTaskCreate(command_poll_task, "command_poll_task", COMMAND_POLL_TASK_STACK_SIZE, NULL, 5, NULL);
#else
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "mqtt_smoke_ready");
    start_mqtt();
#endif
#if !CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED
    xTaskCreate(heartbeat_task, "heartbeat_task", HEARTBEAT_TASK_STACK_SIZE, NULL, 5, NULL);
    xTaskCreate(sensor_task, "sensor_task", SENSOR_TASK_STACK_SIZE, NULL, 5, NULL);
#endif
#endif
    xTaskCreate(safety_cli_task, "safety_cli_task", 4096, NULL, 3, NULL);
}
