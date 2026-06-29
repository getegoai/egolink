#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cJSON.h"
#include "esp_check.h"
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

static EventGroupHandle_t s_event_group;
#if !CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
static esp_mqtt_client_handle_t s_mqtt_client;
#endif
static int s_wifi_retry_count;
static uint32_t s_seq;
static portMUX_TYPE s_seq_mux = portMUX_INITIALIZER_UNLOCKED;
static int s_last_rssi = -127;
static const char *s_reset_reason = "unknown";
static uint32_t s_boot_count;
static char s_status_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
static char s_sensor_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
static char s_lte_http_probe_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
static char s_lte_command_last_cmd_id[64];
static char s_lte_command_parse_status[64] = "not_polled";
static char s_lte_command_diag_payload[1536];
static bool s_lte_command_last_executed;
static int s_lte_command_last_command_count;
#endif

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
typedef struct {
    char *buffer;
    size_t capacity;
    size_t length;
} http_response_buffer_t;
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
    }
    boot_count += 1;
    if (nvs_set_u32(handle, "boot_count", boot_count) == ESP_OK && nvs_commit(handle) == ESP_OK) {
        s_boot_count = boot_count;
    } else {
        s_boot_count = boot_count;
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
static esp_err_t message_hub_http_event_handler(esp_http_client_event_t *event)
{
    if (event->event_id != HTTP_EVENT_ON_DATA || event->user_data == NULL || event->data == NULL) {
        return ESP_OK;
    }

    http_response_buffer_t *response = (http_response_buffer_t *)event->user_data;
    if (response->length + (size_t)event->data_len >= response->capacity) {
        ESP_LOGW(TAG, "MESSAGE_HUB_RESPONSE_TRUNCATED len=%d capacity=%u", event->data_len, (unsigned)response->capacity);
        return ESP_OK;
    }
    memcpy(response->buffer + response->length, event->data, (size_t)event->data_len);
    response->length += (size_t)event->data_len;
    response->buffer[response->length] = '\0';
    return ESP_OK;
}

static void build_message_hub_url(char *buffer, size_t buffer_size, const char *path)
{
    const char *base_url = CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL;
    size_t base_len = strlen(base_url);
    bool base_has_slash = base_len > 0 && base_url[base_len - 1] == '/';
    bool path_has_slash = path[0] == '/';
    const char *separator = (base_has_slash || path_has_slash) ? "" : "/";
    const char *normalized_path = (base_has_slash && path_has_slash) ? path + 1 : path;
    snprintf(buffer, buffer_size, "%s%s%s", base_url, separator, normalized_path);
}

static bool message_hub_request(
    esp_http_client_method_t method,
    const char *path,
    const char *payload,
    char *response_buffer,
    size_t response_size,
    int *status_code)
{
    char url[256];
    build_message_hub_url(url, sizeof(url), path);

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
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        ESP_LOGE(TAG, "MESSAGE_HUB_HTTP_INIT_FAIL path=%s", path);
        return false;
    }

    esp_http_client_set_method(client, method);
    if (strlen(CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN) > 0) {
        char auth_header[192];
        snprintf(auth_header, sizeof(auth_header), "Bearer %s", CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN);
        esp_http_client_set_header(client, "Authorization", auth_header);
    }
    if (payload != NULL) {
        esp_http_client_set_header(client, "Content-Type", "application/json");
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
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    return "firmware uploaded SIM7670G GNSS location_report";
#else
    return "firmware uploaded location_report scaffold";
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
                location_ok ? message_hub_location_ack_message() : "location_report upload failed");
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

#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && (CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED)
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

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED
static void set_lte_command_parse_status(const char *status)
{
    snprintf(s_lte_command_parse_status, sizeof(s_lte_command_parse_status), "%s", status ? status : "unknown");
}

typedef struct {
    char cmd_id[64];
    char cmd[48];
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
        return false;
    }
    ESP_LOGI(TAG, "LTE_HTTP_LOCATION_RAW_FRAME_BYTES=%u", (unsigned)strlen(frame));
    bool ok = sim7670_lte_http_post_raw(
        url,
        CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
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
#endif

static void build_lte_command_ack_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq,
    const char *cmd_id,
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
        "duplicate_local_execution_prevented=%s\n",
        cmd_id,
        status,
        message,
        CONFIG_EGOLINK_FW_VERSION,
        CONFIG_EGOLINK_TEST_RUN_ID,
        seq,
        sim7670_lte_http_backend_name(),
        poll_result->reason_code,
        poll_status_code,
        poll_action_elapsed_ms,
        cmd_id,
        s_lte_command_parse_status,
        s_lte_command_last_command_count,
        json_bool(duplicate_prevented));
}

static bool lte_http_ack_command(
    const char *cmd_id,
    const char *status,
    const char *message,
    const sim7670_lte_http_probe_result_t *poll_result,
    bool duplicate_prevented)
{
    char path[192];
    char url[288];
    char payload[1024];
    char frame[1400];
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
        status,
        message,
        poll_result,
        duplicate_prevented);
    if (!build_lte_raw_frame(frame, sizeof(frame), "ack", cmd_id, seq, payload)) {
        ESP_LOGW(TAG, "LTE_HTTP_COMMAND_RAW_ACK_BUILD_FAILED cmd_id=%s", cmd_id);
        return false;
    }
    ESP_LOGI(TAG, "LTE_HTTP_COMMAND_RAW_ACK_FRAME_BYTES=%u", (unsigned)strlen(frame));
    bool ok = sim7670_lte_http_post_raw(
        url,
        CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,
        frame,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",
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
                length = buffer_size - 1;
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
                value_len = buffer_size - 1;
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

static bool parse_lte_raw_command_frame(char *frame, lte_raw_command_t *command)
{
    if (frame == NULL || command == NULL) {
        set_lte_command_parse_status("raw_frame_missing");
        return false;
    }
    memset(command, 0, sizeof(*command));
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

    s_lte_command_last_command_count = 1;
    set_lte_command_parse_status("raw_command_selected");
    return true;
}

static bool lte_http_execute_and_ack_raw_command(
    const lte_raw_command_t *command,
    const sim7670_lte_http_probe_result_t *poll_result)
{
    if (command == NULL || command->cmd_id[0] == '\0') {
        set_lte_command_parse_status("raw_missing_cmd_id");
        return false;
    }
    bool duplicate = s_lte_command_last_executed && strcmp(s_lte_command_last_cmd_id, command->cmd_id) == 0;
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
        s_lte_command_last_executed = true;
        if (strcmp(command->cmd, "set_report_interval") == 0) {
            status = "ok";
            message = "lte raw command loop acknowledged set_report_interval";
#if CONFIG_EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED
        } else if (strcmp(command->cmd, "request_location") == 0) {
            bool location_ok = lte_http_publish_raw_location_report(command->cmd_id);
            status = location_ok ? "ok" : "error";
            message = location_ok ? message_hub_location_ack_message() : "lte raw location_report upload failed";
#endif
        } else {
            status = "rejected";
            message = "lte raw command loop only accepts set_report_interval or request_location";
        }
    } else {
        message = "lte raw command duplicate ignored after local execution";
    }

    return lte_http_ack_command(command->cmd_id, status, message, poll_result, duplicate);
}

static bool lte_http_poll_commands_once(sim7670_lte_http_probe_result_t *poll_result)
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

static void lte_http_command_task(void *arg)
{
    (void)arg;
    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_command_loop");
    bool lte_ready = wait_for_lte_ready_for_http_probe();
    ESP_LOGI(TAG, "LTE_HTTP_COMMAND_READY_RESULT ready=%s", lte_ready ? "true" : "false");
    if (!lte_ready) {
        platform_power_leave_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "lte_http_command_lte_not_ready");
        platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "lte_http_command_done");
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
    for (int attempt = 1; attempt <= max_attempts; ++attempt) {
        sim7670_lte_http_probe_result_t poll_result;
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_POLL_ROUND_START attempt=%d max_attempts=%d", attempt, max_attempts);
        acked = lte_http_poll_commands_once(&poll_result);
        (void)lte_http_post_command_diag(acked ? "command_ack_observed" : "poll_no_ack", &poll_result, true, acked);
        ESP_LOGI(TAG, "LTE_HTTP_COMMAND_POLL_ROUND_DONE attempt=%d acked=%s", attempt, acked ? "true" : "false");
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
}
#endif
#endif

static void build_status_payload(char *buffer, size_t buffer_size, uint32_t seq)
{
    int rssi = refresh_wifi_rssi();
    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
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
        "\"link_type\":\"mock_4g_over_wifi\","
        "\"rssi\":%d,"
        "\"modem_state\":\"mock_data_ready\","
        "\"gnss_state\":\"mock_fix\","
        "\"guard_mode\":\"child_safety\","
        "\"queue_size\":0"
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        CONFIG_EGOLINK_FW_VERSION,
        power.battery_percent,
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
        rssi,
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
        "\"link_type\":\"mock_4g_over_wifi\","
        "\"modem_state\":\"mock_data_ready\","
        "\"gnss_state\":\"mock_fix\""
        "%s",
        CONFIG_EGOLINK_DEVICE_ID,
        now_ms,
        seq,
        now_ms,
        rssi,
        free_heap,
        min_free_heap,
        power.battery_percent,
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
}
#endif

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT | MQTT_CONNECTED_BIT);
        if (s_wifi_retry_count < WIFI_MAX_RETRY) {
            ESP_LOGW(TAG, "Wi-Fi disconnected; retry %d/%d", s_wifi_retry_count + 1, WIFI_MAX_RETRY);
            ESP_ERROR_CHECK(esp_wifi_connect());
            s_wifi_retry_count++;
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
        xEventGroupSetBits(s_event_group, WIFI_CONNECTED_BIT);
    }
}

static esp_err_t start_wifi(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, CONFIG_EGOLINK_WIFI_SSID, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, CONFIG_EGOLINK_WIFI_PASSWORD, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(
        s_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(20000));
    ESP_RETURN_ON_FALSE((bits & WIFI_CONNECTED_BIT) != 0, ESP_FAIL, TAG, "Wi-Fi connection timed out");
    return ESP_OK;
}

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
    ESP_LOGI(
        TAG,
#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED
        "MESSAGE_HUB_BOOT device_id=%s hub=%s",
        CONFIG_EGOLINK_DEVICE_ID,
        CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL);
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
    platform_power_enter_state(PLATFORM_POWER_STATE_BOOT, "app_main");
    ESP_ERROR_CHECK(safety_model_init() ? ESP_OK : ESP_FAIL);
    ESP_LOGI(TAG, "SAFETY_MODEL_INIT_OK version=%s mock=true", safety_model_version());

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
    xTaskCreate(heartbeat_task, "heartbeat_task", HEARTBEAT_TASK_STACK_SIZE, NULL, 5, NULL);
    xTaskCreate(sensor_task, "sensor_task", SENSOR_TASK_STACK_SIZE, NULL, 5, NULL);
#endif
    xTaskCreate(safety_cli_task, "safety_cli_task", 4096, NULL, 3, NULL);
}
