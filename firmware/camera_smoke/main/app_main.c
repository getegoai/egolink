#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_camera.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs_flash.h"

static const char *TAG = "egolink_camera_smoke";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define WIFI_MAX_RETRY 8
#define CAMERA_SMOKE_BOOT_CAPTURE_DELAY_MS 5000
#define CAMERA_SMOKE_CAPTURE_COUNT 3
#define CAMERA_SMOKE_CAPTURE_INTERVAL_MS 3000

typedef struct {
    const char *name;
    int pin_pwdn;
    int pin_reset;
    int pin_xclk;
    int pin_sccb_sda;
    int pin_sccb_scl;
    int pin_d7;
    int pin_d6;
    int pin_d5;
    int pin_d4;
    int pin_d3;
    int pin_d2;
    int pin_d1;
    int pin_d0;
    int pin_vsync;
    int pin_href;
    int pin_pclk;
} camera_pin_profile_t;

/*
 * Waveshare ESP32-S3-SIM7670G-4G camera connector pinout.
 * ESP camera data pins map D0-D7 to the module signals Y2-Y9.
 */
static const camera_pin_profile_t CAMERA_PROFILES[] = {
    {
        .name = "waveshare_esp32s3_sim7670g_4g",
        .pin_pwdn = -1,
        .pin_reset = -1,
        .pin_xclk = 39,
        .pin_sccb_sda = 15,
        .pin_sccb_scl = 16,
        .pin_d7 = 14,
        .pin_d6 = 13,
        .pin_d5 = 12,
        .pin_d4 = 11,
        .pin_d3 = 10,
        .pin_d2 = 9,
        .pin_d1 = 8,
        .pin_d0 = 7,
        .pin_vsync = 42,
        .pin_href = 41,
        .pin_pclk = 46,
    },
};

static EventGroupHandle_t s_wifi_event_group;
static int s_wifi_retry_count;
static const camera_pin_profile_t *s_active_profile;

static uint32_t fnv1a32(const uint8_t *data, size_t len)
{
    uint32_t hash = 2166136261u;
    for (size_t i = 0; i < len; ++i) {
        hash ^= data[i];
        hash *= 16777619u;
    }
    return hash;
}

static camera_config_t make_camera_config(const camera_pin_profile_t *profile)
{
    camera_config_t config = {
        .pin_pwdn = profile->pin_pwdn,
        .pin_reset = profile->pin_reset,
        .pin_xclk = profile->pin_xclk,
        .pin_sccb_sda = profile->pin_sccb_sda,
        .pin_sccb_scl = profile->pin_sccb_scl,
        .pin_d7 = profile->pin_d7,
        .pin_d6 = profile->pin_d6,
        .pin_d5 = profile->pin_d5,
        .pin_d4 = profile->pin_d4,
        .pin_d3 = profile->pin_d3,
        .pin_d2 = profile->pin_d2,
        .pin_d1 = profile->pin_d1,
        .pin_d0 = profile->pin_d0,
        .pin_vsync = profile->pin_vsync,
        .pin_href = profile->pin_href,
        .pin_pclk = profile->pin_pclk,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = FRAMESIZE_QVGA,
        .jpeg_quality = 12,
        .fb_count = 1,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
    };
    return config;
}

static esp_err_t init_camera(void)
{
    for (size_t i = 0; i < sizeof(CAMERA_PROFILES) / sizeof(CAMERA_PROFILES[0]); ++i) {
        const camera_pin_profile_t *profile = &CAMERA_PROFILES[i];
        ESP_LOGI(TAG, "Trying camera profile: %s", profile->name);
        camera_config_t config = make_camera_config(profile);
        esp_err_t err = esp_camera_init(&config);
        if (err == ESP_OK) {
            s_active_profile = profile;
            sensor_t *sensor = esp_camera_sensor_get();
            if (sensor) {
                sensor->set_framesize(sensor, FRAMESIZE_QVGA);
            }
            ESP_LOGI(TAG, "CAMERA_SMOKE_INIT_OK profile=%s", profile->name);
            return ESP_OK;
        }
        ESP_LOGW(TAG, "Camera profile %s failed: %s", profile->name, esp_err_to_name(err));
        esp_camera_deinit();
        vTaskDelay(pdMS_TO_TICKS(300));
    }
    ESP_LOGE(TAG, "CAMERA_SMOKE_INIT_FAIL");
    return ESP_FAIL;
}

static esp_err_t capture_once(uint32_t capture_index)
{
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        ESP_LOGE(TAG, "CAMERA_SMOKE_CAPTURE_FAIL capture_index=%" PRIu32, capture_index);
        return ESP_FAIL;
    }

    uint32_t checksum = fnv1a32(fb->buf, fb->len);
    ESP_LOGI(
        TAG,
        "CAMERA_SMOKE_CAPTURE_OK capture_index=%" PRIu32 " profile=%s bytes=%u checksum=%08" PRIx32 " width=%u height=%u format=%u jpeg_soi=%02x%02x jpeg_eoi=%02x%02x",
        capture_index,
        s_active_profile ? s_active_profile->name : "unknown",
        (unsigned)fb->len,
        checksum,
        (unsigned)fb->width,
        (unsigned)fb->height,
        (unsigned)fb->format,
        fb->len >= 2 ? fb->buf[0] : 0,
        fb->len >= 2 ? fb->buf[1] : 0,
        fb->len >= 2 ? fb->buf[fb->len - 2] : 0,
        fb->len >= 2 ? fb->buf[fb->len - 1] : 0);
    esp_camera_fb_return(fb);
    return ESP_OK;
}

static void capture_startup_sequence(void)
{
    ESP_LOGI(
        TAG,
        "CAMERA_SMOKE_CAPTURE_SEQUENCE delay_ms=%u count=%u interval_ms=%u",
        CAMERA_SMOKE_BOOT_CAPTURE_DELAY_MS,
        CAMERA_SMOKE_CAPTURE_COUNT,
        CAMERA_SMOKE_CAPTURE_INTERVAL_MS);
    vTaskDelay(pdMS_TO_TICKS(CAMERA_SMOKE_BOOT_CAPTURE_DELAY_MS));

    for (uint32_t i = 1; i <= CAMERA_SMOKE_CAPTURE_COUNT; ++i) {
        esp_err_t ret = capture_once(i);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "CAMERA_SMOKE_CAPTURE_SEQUENCE_STOP capture_index=%" PRIu32 " error=%s", i, esp_err_to_name(ret));
            return;
        }
        if (i < CAMERA_SMOKE_CAPTURE_COUNT) {
            vTaskDelay(pdMS_TO_TICKS(CAMERA_SMOKE_CAPTURE_INTERVAL_MS));
        }
    }
}

static esp_err_t root_handler(httpd_req_t *req)
{
    const char *html =
        "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Ego Link Camera Smoke</title></head><body>"
        "<h1>Ego Link Camera Smoke</h1>"
        "<p>Open <a href='/capture'>/capture</a> to fetch the latest JPEG frame.</p>"
        "<img src='/capture' style='max-width:100%;height:auto;border:1px solid #ccc'>"
        "</body></html>";
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, html, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t capture_handler(httpd_req_t *req)
{
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "camera capture failed");
        return ESP_FAIL;
    }
    httpd_resp_set_type(req, "image/jpeg");
    esp_err_t ret = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    return ret;
}

static void start_camera_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    httpd_handle_t server = NULL;
    ESP_ERROR_CHECK(httpd_start(&server, &config));

    httpd_uri_t root_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = root_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t capture_uri = {
        .uri = "/capture",
        .method = HTTP_GET,
        .handler = capture_handler,
        .user_ctx = NULL,
    };
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &root_uri));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &capture_uri));
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_wifi_retry_count < WIFI_MAX_RETRY) {
            esp_wifi_connect();
            s_wifi_retry_count++;
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "CAMERA_SMOKE_HTTP_READY ip=" IPSTR, IP2STR(&event->ip_info.ip));
        s_wifi_retry_count = 0;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static bool wifi_configured(void)
{
    return strlen(CONFIG_EGOLINK_WIFI_SSID) > 0;
}

static esp_err_t start_wifi(void)
{
    if (!wifi_configured()) {
        ESP_LOGW(TAG, "Wi-Fi not configured; skipping HTTP camera endpoint.");
        return ESP_ERR_INVALID_STATE;
    }

    s_wifi_event_group = xEventGroupCreate();
    ESP_RETURN_ON_FALSE(s_wifi_event_group != NULL, ESP_ERR_NO_MEM, TAG, "wifi event group allocation failed");

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, CONFIG_EGOLINK_WIFI_SSID, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, CONFIG_EGOLINK_WIFI_PASSWORD, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(
        s_wifi_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(15000));
    if (bits & WIFI_CONNECTED_BIT) {
        start_camera_server();
        return ESP_OK;
    }
    ESP_LOGW(TAG, "Wi-Fi connection failed; HTTP endpoint unavailable.");
    return ESP_FAIL;
}

void app_main(void)
{
    ESP_LOGI(TAG, "Ego Link camera smoke test booting");
    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_ret);

    if (init_camera() == ESP_OK) {
        capture_startup_sequence();
    }
    start_wifi();

    ESP_LOGI(TAG, "CAMERA_SMOKE_DONE startup capture sequence attempted; HTTP /capture remains available if Wi-Fi is configured.");
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(60000));
    }
}
