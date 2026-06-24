#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
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
#include "nvs_flash.h"
#include "platform_imu.h"
#include "platform_power.h"
#include "safety_model.h"

static const char *TAG = "egolink_mqtt_heartbeat";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define MQTT_CONNECTED_BIT BIT2
#define WIFI_MAX_RETRY 8

static EventGroupHandle_t s_event_group;
static esp_mqtt_client_handle_t s_mqtt_client;
static int s_wifi_retry_count;
static uint32_t s_seq;
static portMUX_TYPE s_seq_mux = portMUX_INITIALIZER_UNLOCKED;
static int s_last_rssi = -127;

static const char *json_bool(bool value)
{
    return value ? "true" : "false";
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

static int refresh_wifi_rssi(void)
{
    wifi_ap_record_t ap_info;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        s_last_rssi = ap_info.rssi;
    }
    return s_last_rssi;
}

static void build_status_payload(char *buffer, size_t buffer_size, uint32_t seq)
{
    int rssi = refresh_wifi_rssi();
    platform_power_snapshot_t power;
    platform_power_get_snapshot(&power);
    snprintf(
        buffer,
        buffer_size,
        "{\"protocol_version\":\"egolink.p0.v1\","
        "\"device_id\":\"%s\","
        "\"ts\":\"uptime_ms:%" PRId64 "\","
        "\"seq\":%" PRIu32 ","
        "\"message_type\":\"status\","
        "\"fw_version\":\"0.1.0-mqtt-smoke\","
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
        "\"link_type\":\"mock_4g_over_wifi\","
        "\"rssi\":%d,"
        "\"modem_state\":\"mock_data_ready\","
        "\"gnss_state\":\"mock_fix\","
        "\"guard_mode\":\"child_safety\","
        "\"queue_size\":0}",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
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
        rssi);
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
        "\"gnss_state\":\"mock_fix\"}",
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
        imu.latest.gyro_mdps_z);
}

static void publish_heartbeat(void)
{
    char payload[768];
    uint32_t seq = next_seq();
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "status_publish");
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
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "status_publish_done");
}

static void publish_sensor_sample(void)
{
    static char payload[1536];
    uint32_t seq = next_seq();
    platform_power_enter_state(PLATFORM_POWER_STATE_UPLOAD, "sensor_publish");
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
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "sensor_publish_done");
}

static void heartbeat_task(void *arg)
{
    (void)arg;
    while (true) {
        EventBits_t bits = xEventGroupWaitBits(
            s_event_group,
            MQTT_CONNECTED_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        if (bits & MQTT_CONNECTED_BIT) {
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
            MQTT_CONNECTED_BIT,
            pdFALSE,
            pdTRUE,
            portMAX_DELAY);
        if (bits & MQTT_CONNECTED_BIT) {
            publish_sensor_sample();
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC * 1000));
    }
}

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

void app_main(void)
{
    ESP_LOGI(
        TAG,
        "MQTT_HEARTBEAT_BOOT device_id=%s status_topic=%s event_topic=%s",
        CONFIG_EGOLINK_DEVICE_ID,
        CONFIG_EGOLINK_STATUS_TOPIC,
        CONFIG_EGOLINK_EVENT_TOPIC);

    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_ret);

    s_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(s_event_group == NULL ? ESP_ERR_NO_MEM : ESP_OK);
    ESP_ERROR_CHECK(platform_power_init() ? ESP_OK : ESP_FAIL);
    ESP_ERROR_CHECK(platform_imu_init() ? ESP_OK : ESP_FAIL);
    platform_power_enter_state(PLATFORM_POWER_STATE_BOOT, "app_main");
    ESP_ERROR_CHECK(safety_model_init() ? ESP_OK : ESP_FAIL);
    ESP_LOGI(TAG, "SAFETY_MODEL_INIT_OK version=%s mock=true", safety_model_version());

    platform_power_enter_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "wifi_connect");
    ESP_ERROR_CHECK(start_wifi());
    platform_power_leave_state(PLATFORM_POWER_STATE_NETWORK_ATTACH, "wifi_connected");
    platform_power_enter_state(PLATFORM_POWER_STATE_GUARDING, "mqtt_smoke_ready");
    start_mqtt();
    xTaskCreate(heartbeat_task, "heartbeat_task", 4096, NULL, 5, NULL);
    xTaskCreate(sensor_task, "sensor_task", 6144, NULL, 5, NULL);
    xTaskCreate(safety_cli_task, "safety_cli_task", 4096, NULL, 3, NULL);
}
