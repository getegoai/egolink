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
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

static const char *TAG = "egolink_mqtt_heartbeat";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define MQTT_CONNECTED_BIT BIT2
#define WIFI_MAX_RETRY 8

static EventGroupHandle_t s_event_group;
static esp_mqtt_client_handle_t s_mqtt_client;
static int s_wifi_retry_count;
static uint32_t s_seq;
static int s_last_rssi = -127;

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static void build_status_payload(char *buffer, size_t buffer_size, uint32_t seq)
{
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
        "\"battery\":87,"
        "\"charging\":false,"
        "\"link_type\":\"mock_4g_over_wifi\","
        "\"rssi\":%d,"
        "\"modem_state\":\"mock_data_ready\","
        "\"gnss_state\":\"mock_fix\","
        "\"guard_mode\":\"child_safety\","
        "\"queue_size\":0}",
        CONFIG_EGOLINK_DEVICE_ID,
        uptime_ms(),
        seq,
        s_last_rssi);
}

static void publish_heartbeat(void)
{
    char payload[512];
    uint32_t seq = ++s_seq;
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
    } else {
        ESP_LOGE(TAG, "MQTT_HEARTBEAT_PUBLISH_FAIL seq=%" PRIu32 " rc=%d", seq, msg_id);
    }
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
    ESP_LOGI(TAG, "MQTT_HEARTBEAT_BOOT device_id=%s topic=%s", CONFIG_EGOLINK_DEVICE_ID, CONFIG_EGOLINK_STATUS_TOPIC);

    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_ret);

    s_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(s_event_group == NULL ? ESP_ERR_NO_MEM : ESP_OK);

    ESP_ERROR_CHECK(start_wifi());
    start_mqtt();
    xTaskCreate(heartbeat_task, "heartbeat_task", 4096, NULL, 5, NULL);
}
