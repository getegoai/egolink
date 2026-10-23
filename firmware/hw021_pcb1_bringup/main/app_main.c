#include <ctype.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/sdmmc_host.h"
#include "driver/sdspi_host.h"
#include "driver/spi_common.h"
#include "driver/uart.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_app_desc.h"
#include "esp_camera.h"
#include "esp_chip_info.h"
#include "esp_err.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_partition.h"
#include "esp_rom_gpio.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "nvs_flash.h"
#include "sdmmc_cmd.h"
#include "soc/gpio_sig_map.h"

#include "ego_state_engine.h"
#include "sim7670_cellular_call.h"
#include "ego_blackbox.h"
#include "ego_outbox_sync.h"

static const char *TAG = "PCB1_RUNTIME";

/* === HW021_C1_ESP32MODEL_VR00 Pin Definitions === */
#define PIN_BOOT_KEY        0   /* K3 BOOT */
#define PIN_ADC_V           1   /* GPIO1 / ADC1_CH0: V_BAT * 0.5 via Q6 */
#define PIN_AD_CTRL         2   /* GPIO2: HIGH enables Q7/Q6 battery divider */
#define PIN_SD_CS           3   /* GPIO3: TF card CS (pull-up 51K to 3.3V_SD) */
#define PIN_CAM_PWDN        4   /* GPIO4: LOW -> Q5 3.3V_SD ON; HIGH -> U7 CAM_1.2V/2.8V ON */
#define PIN_AUDIO_MUTE      5   /* GPIO5: U5 8002A SHUTDOWN (pulled to V_BAT via R19 2K) */
#define PIN_USER_KEY        6   /* GPIO6: K1 KEY / SOS button (active LOW, R33 10K pull-up) */
#define PIN_CAM_TWI_CLK     7   /* GPIO7: J9 Camera SCL (shorted to 3.3V_VCC on PCB1) */
#define PIN_CAM_TWI_SDA     8   /* GPIO8: J9 Camera SDA (shorted to 3.3V_VCC on PCB1) */
#define PIN_GSENSOR_INT1    9   /* GPIO9: U3 SC7A20TR INT1 */
#define PIN_GSENSOR_INT2    10  /* GPIO10: U3 SC7A20TR INT2 */
#define PIN_GSENSOR_SDA0    11  /* GPIO11: U3 SC7A20TR SDA0 (R15 4.7K pull-up) */
#define PIN_GSENSOR_SCL0    12  /* GPIO12: U3 SC7A20TR SCL0 (R16 4.7K pull-up) */
#define PIN_GPS_RX2         13  /* GPIO13: J10 Pin 1 <- BE-220 TX */
#define PIN_GPS_TX2         14  /* GPIO14: J10 Pin 2 -> BE-220 RX */
#define PIN_4G_PWDN         15  /* GPIO15: HIGH turns Q4/Q3 4G_BAT ON */
#define PIN_SD_CLK          16  /* GPIO16: TF card CLK (pull-up 51K to 3.3V_SD) */
#define PIN_CAM_VSYNC       17  /* GPIO17: J9 VSYNC */
#define PIN_CAM_HREF        18  /* GPIO18: J9 HREF */
#define PIN_CAM_D7          21  /* GPIO21: J9 D9 */
#define PIN_GPS_PWDN        26  /* GPIO26 (SPICS1): HIGH turns Q10/Q8 GPS_BAT ON */
#define PIN_DISP_SCL1       33  /* GPIO33: J8 Display SCL1 (R39 4.7K pull-up) */
#define PIN_DISP_SDA1       34  /* GPIO34: J8 Display SDA1 (R38 4.7K pull-up) */
#define PIN_4G_NETLIGHT     35  /* GPIO35: U1 ML307A Pin 16 NETLIGHT */
#define PIN_4G_TX1          36  /* GPIO36: ESP32 TX -> Q2 -> 4G_RXD (U1 Pin 17) */
#define PIN_4G_RX1          37  /* GPIO37: ESP32 RX <- Q1 <- 4G_TXD (U1 Pin 18) */
#define PIN_CAM_MCLK        38  /* GPIO38: J9 MCLK */
#define PIN_CAM_D6          39  /* GPIO39: J9 D8 */
#define PIN_CAM_D5          40  /* GPIO40: J9 D7 */
#define PIN_CAM_PCLK        41  /* GPIO41: J9 PCLK */
#define PIN_CAM_D4          42  /* GPIO42: J9 D6 */
#define PIN_SD_CMD_U0TXD    43  /* GPIO43: TF CMD / U0TXD */
#define PIN_SD_D0_U0RXD     44  /* GPIO44: TF D0 / U0RXD */
#define PIN_CAM_D0          45  /* GPIO45: J9 D2 (Strapping VDD_SPI!) */
#define PIN_CAM_D3          46  /* GPIO46: J9 D5 (Strapping!) */
#define PIN_CAM_D1          47  /* GPIO47: J9 D3 */
#define PIN_CAM_D2          48  /* GPIO48: J9 D4 */

/* Outbox partition record structure */
typedef struct {
    uint32_t magic;
    uint32_t sequence;
    uint32_t payload_len;
    uint32_t checksum_crc32;
    char estimation_id[48];
    char evidence_digest[65];
    int64_t timestamp_ns;
    char payload_json[512];
} __attribute__((packed)) pcb1_outbox_record_t;

#define PCB1_OUTBOX_MAGIC 0x45474F58 /* "EGOX" */

/* Global subsystem handles */
static i2c_master_bus_handle_t s_i2c0_bus = NULL;
static i2c_master_dev_handle_t s_sc7a20_dev = NULL;
static adc_oneshot_unit_handle_t s_adc1_handle = NULL;
static adc_cali_handle_t s_adc1_cali_handle = NULL;
static bool s_adc1_calibrated = false;

static ego_state_engine_ctx_t s_ego_ctx;
static sim7670_cellular_call_ctx_t s_call_ctx;

static SemaphoreHandle_t s_modem_mutex = NULL;
static char s_dial_phone_number[32] = "10086";
static char s_web_device_id[32] = "ego-link-001";
static bool s_audio_amp_unmuted = false;
static bool s_manual_post_flag = false;
static bool s_sos_triggered_flag = false;
static uint32_t s_web_post_count = 0;
static uint32_t s_web_post_success = 0;
static uint32_t s_web_post_failed = 0;
static int s_web_last_status = 0;
static int64_t s_web_last_post_time_ms = 0;
static bool s_cellular_online = false;

static char s_device_id[32] = {0};
static char s_elf_sha256[65] = {0};
static char s_summary_report[4096];
static size_t s_summary_len = 0;
static char s_wifi_hash[65] = {0};
static uint16_t s_wifi_ap_count = 0;
static float s_last_ax_mg = 0.0f;
static float s_last_ay_mg = 0.0f;
static float s_last_az_mg = 1000.0f;

/* Sensitive data redactor for logs */
static void redact_sensitive(const char *in, char *out, size_t out_size)
{
    if (!in || !out || out_size == 0) return;
    size_t in_len = strlen(in);
    size_t j = 0;
    for (size_t i = 0; i < in_len && j < out_size - 1; ++i) {
        if (isdigit((unsigned char)in[i])) {
            size_t start = i;
            while (i < in_len && isdigit((unsigned char)in[i])) {
                i++;
            }
            size_t num_len = i - start;
            if (num_len >= 14) {
                /* IMEI (15), ICCID (20), IMSI (15): keep first 8 digits, mask remainder */
                size_t keep = 8;
                for (size_t k = 0; k < num_len && j < out_size - 1; ++k) {
                    if (k < keep) {
                        out[j++] = in[start + k];
                    } else {
                        out[j++] = '*';
                    }
                }
            } else {
                for (size_t k = 0; k < num_len && j < out_size - 1; ++k) {
                    out[j++] = in[start + k];
                }
            }
            if (i < in_len && j < out_size - 1) {
                out[j++] = in[i];
            }
        } else {
            out[j++] = in[i];
        }
    }
    out[j] = '\0';
}

static void append_summary(const char *fmt, ...)
{
    if (s_summary_len >= sizeof(s_summary_report) - 1) return;
    va_list args;
    va_start(args, fmt);
    int written = vsnprintf(
        s_summary_report + s_summary_len,
        sizeof(s_summary_report) - s_summary_len,
        fmt,
        args);
    va_end(args);
    if (written > 0) {
        size_t adv = (size_t)written;
        if (s_summary_len + adv >= sizeof(s_summary_report)) {
            s_summary_len = sizeof(s_summary_report) - 1;
        } else {
            s_summary_len += adv;
        }
    }
}

static uint32_t calc_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

static int64_t get_monotonic_time_us(void)
{
    return esp_timer_get_time();
}

static int64_t get_monotonic_time_ns(void)
{
    return esp_timer_get_time() * 1000LL;
}

/* Audio amp mute control helper (PIN_AUDIO_MUTE = GPIO5) */
static void set_audio_amp_mute(bool muted)
{
    if (muted) {
        /* Set GPIO5 to input (High-Z) so R19 (2K) pulls it up to V_BAT, 8002A in shutdown */
        gpio_set_direction(PIN_AUDIO_MUTE, GPIO_MODE_INPUT);
        s_audio_amp_unmuted = false;
        ESP_LOGI(TAG, "AUDIO_AMP: Muted (GPIO5=Input/High-Z, 8002A SHUTDOWN)");
    } else {
        /* Drive GPIO5 to LOW (GND) to enable 8002A amplifier */
        gpio_set_direction(PIN_AUDIO_MUTE, GPIO_MODE_OUTPUT);
        gpio_set_level(PIN_AUDIO_MUTE, 0);
        s_audio_amp_unmuted = true;
        ESP_LOGI(TAG, "AUDIO_AMP: UNMUTED (GPIO5=0 -> 8002A ACTIVE, speaker enabled)");
    }
}

/* AT command transport for ML307A-DSLN on UART_NUM_2 */
static esp_err_t ml307a_at_send(
    void *user_ctx,
    const char *cmd,
    char *resp,
    size_t resp_size,
    uint32_t timeout_ms)
{
    (void)user_ctx;
    if (s_modem_mutex != NULL) {
        xSemaphoreTake(s_modem_mutex, portMAX_DELAY);
    }
    uart_flush_input(UART_NUM_2);
    uart_write_bytes(UART_NUM_2, cmd, strlen(cmd));
    uart_write_bytes(UART_NUM_2, "\r\n", 2);

    static uint8_t s_rx_buf[4096];
    int total = 0;
    int64_t t0 = esp_timer_get_time() / 1000;
    bool is_http_req = (strncmp(cmd, "AT+MHTTPREQUEST", 15) == 0);

    while ((esp_timer_get_time() / 1000 - t0) < timeout_ms && total < (int)sizeof(s_rx_buf) - 1) {
        int n = uart_read_bytes(UART_NUM_2, s_rx_buf + total, sizeof(s_rx_buf) - 1 - total, pdMS_TO_TICKS(50));
        if (n > 0) {
            total += n;
            s_rx_buf[total] = '\0';
            if (is_http_req) {
                if (strstr((char *)s_rx_buf, "+MHTTPURC:") != NULL ||
                    strstr((char *)s_rx_buf, "+MHTTPREQUEST:") != NULL) {
                    break;
                }
                if (strstr((char *)s_rx_buf, "\r\nERROR\r\n") || strstr((char *)s_rx_buf, "+CME ERROR:")) {
                    break;
                }
            } else {
                if (strstr((char *)s_rx_buf, "\r\nOK\r\n") || strstr((char *)s_rx_buf, "\r\nERROR\r\n") ||
                    strstr((char *)s_rx_buf, "+CME ERROR:") || strstr((char *)s_rx_buf, "+CMS ERROR:") ||
                    strstr((char *)s_rx_buf, ">")) {
                    break;
                }
            }
        }
    }
    s_rx_buf[total] = '\0';

    if (resp && resp_size > 0) {
        size_t j = 0;
        for (int i = 0; i < total && j < resp_size - 1; ++i) {
            char c = (char)s_rx_buf[i];
            if (c == '\r' || c == '\n') {
                if (j > 0 && resp[j - 1] != ' ') {
                    resp[j++] = ' ';
                }
            } else if (c >= 32 && c < 127) {
                resp[j++] = c;
            }
        }
        while (j > 0 && resp[j - 1] == ' ') {
            j--;
        }
        resp[j] = '\0';
    }

    esp_err_t ret = ESP_FAIL;
    if (strstr((char *)s_rx_buf, "OK") != NULL || strstr((char *)s_rx_buf, "+MHTTPREQUEST:") != NULL) {
        ret = ESP_OK;
    }

    if (s_modem_mutex != NULL) {
        xSemaphoreGive(s_modem_mutex);
    }
    return ret;
}

static void send_at_and_log(const char *cmd, char *out_clean, size_t out_max, int wait_ms)
{
    char raw_resp[512] = {0};
    ml307a_at_send(NULL, cmd, raw_resp, sizeof(raw_resp), wait_ms);
    char redacted[512] = {0};
    redact_sensitive(raw_resp, redacted, sizeof(redacted));
    if (out_clean && out_max > 0) {
        strncpy(out_clean, raw_resp, out_max - 1);
        out_clean[out_max - 1] = '\0';
    }
    ESP_LOGI(TAG, "Modem AT [%s] -> \"%s\"", cmd, redacted);
}

/* Cellular voice call triggering functions */
static void trigger_phone_call(const char *number)
{
    if (!number || strlen(number) == 0) number = s_dial_phone_number;
    ESP_LOGI(TAG, "PCB1_VOICE_CALL_TRIGGER target=\"%s\"", number);
    char ev_detail[128];
    snprintf(ev_detail, sizeof(ev_detail), "{\"action\":\"DIAL\",\"number\":\"%s\"}", number);
    ego_blackbox_log_event("CALL_DIAL", ev_detail);
    set_audio_amp_mute(false);
    esp_err_t err = sim7670_cellular_call_dial(&s_call_ctx, number);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "PCB1_VOICE_CALL_DIALING_OK target=\"%s\"", number);
    } else {
        ESP_LOGE(TAG, "PCB1_VOICE_CALL_DIAL_FAIL err=%d", err);
        set_audio_amp_mute(true);
    }
}

static void trigger_phone_hangup(void)
{
    ESP_LOGI(TAG, "PCB1_VOICE_CALL_HANGUP_TRIGGER");
    ego_blackbox_log_event("CALL_HANGUP", "{\"action\":\"HANGUP\"}");
    sim7670_cellular_call_hangup(&s_call_ctx);
    set_audio_amp_mute(true);
    ESP_LOGI(TAG, "PCB1_VOICE_CALL_HUNG_UP");
}

static void trigger_phone_answer(void)
{
    ESP_LOGI(TAG, "PCB1_VOICE_CALL_ANSWER_TRIGGER");
    ego_blackbox_log_event("CALL_ANSWER", "{\"action\":\"ANSWER\"}");
    set_audio_amp_mute(false);
    sim7670_cellular_call_answer(&s_call_ctx);
    ESP_LOGI(TAG, "PCB1_VOICE_CALL_ANSWERED");
}

/* Web platform JSON poster */
static char s_http_cmd[1536];
static char s_http_resp[512];
static char s_telemetry_payload[768];

static esp_err_t ml307a_post_web_json(const char *path, const char *json_payload, int *out_http_status)
{
    if (out_http_status) *out_http_status = 0;

    /* 1. Reset / delete existing HTTP instance */
    ml307a_at_send(NULL, "AT+MHTTPDEL=0", s_http_resp, sizeof(s_http_resp), 500);

    /* 2. Create HTTP instance with Web platform origin */
    if (ml307a_at_send(NULL, "AT+MHTTPCREATE=\"http://ego.example.invalid\"", s_http_resp, sizeof(s_http_resp), 4000) != ESP_OK) {
        ESP_LOGE(TAG, "MHTTPCREATE fail: %s", s_http_resp);
        return ESP_FAIL;
    }

    /* 3. Bind to active cellular PDP context 1 */
    ml307a_at_send(NULL, "AT+MHTTPCFG=\"cid\",0,1", s_http_resp, sizeof(s_http_resp), 1000);

    /* 4. Set Content-Type header (mode 0 = last/single header, len 0 = auto) */
    ml307a_at_send(NULL, "AT+MHTTPHEADER=0,0,0,\"Content-Type: application/json\"", s_http_resp, sizeof(s_http_resp), 1500);

    /* 5. Set content payload in mode 0 directly */
    int plen = (int)strlen(json_payload);
    snprintf(s_http_cmd, sizeof(s_http_cmd), "AT+MHTTPCONTENT=0,0,%d,\"%s\"", plen, json_payload);
    esp_err_t content_err = ml307a_at_send(NULL, s_http_cmd, s_http_resp, sizeof(s_http_resp), 3000);
    if (content_err != ESP_OK) {
        ESP_LOGW(TAG, "MHTTPCONTENT mode 0 err: %s", s_http_resp);
    }

    /* 6. Send POST request (method 2 = POST, exact URI length, path) */
    int path_len = (int)strlen(path);
    snprintf(s_http_cmd, sizeof(s_http_cmd), "AT+MHTTPREQUEST=0,2,%d,\"%s\"", path_len, path);
    ml307a_at_send(NULL, s_http_cmd, s_http_resp, sizeof(s_http_resp), 10000);

    int http_status = 0;
    /* Check for +MHTTPURC: "header",<id>,<status>,... or "status",<id>,<status> */
    char *p = strstr(s_http_resp, "\"header\",");
    if (p) {
        int cid = 0;
        sscanf(p, "\"header\",%d,%d", &cid, &http_status);
    } else {
        p = strstr(s_http_resp, "\"status\",");
        if (p) {
            int cid = 0;
            sscanf(p, "\"status\",%d,%d", &cid, &http_status);
        } else {
            p = strstr(s_http_resp, "+MHTTPREQUEST:");
            if (p) {
                int cid = 0, err_code = 0, slen = 0;
                sscanf(p, "+MHTTPREQUEST: %d,%d,%d,%d", &cid, &err_code, &http_status, &slen);
            }
        }
    }
    if (out_http_status) *out_http_status = http_status;

    /* 7. Clean up instance */
    ml307a_at_send(NULL, "AT+MHTTPDEL=0", s_http_resp, sizeof(s_http_resp), 500);

    return (http_status >= 200 && http_status < 300) ? ESP_OK : ESP_FAIL;
}

static esp_err_t ml307a_post_web_telemetry(
    const char *device_id,
    int vbat_mv,
    float soc_pct,
    float lte_rsrp,
    int csq_rssi,
    const char *motion_state,
    const char *wear_state,
    float motion_rms,
    bool gnss_fix,
    double gnss_lat,
    double gnss_lon,
    float gnss_speed,
    uint16_t gnss_sats,
    float gnss_hdop,
    bool is_sos_alert,
    int *out_http_status)
{
    if (out_http_status) *out_http_status = 0;

    struct timeval tv_now;
    gettimeofday(&tv_now, NULL);
    int64_t epoch_ms;
    if (tv_now.tv_sec > 1700000000) {
        epoch_ms = (int64_t)tv_now.tv_sec * 1000 + (tv_now.tv_usec / 1000);
    } else {
        // Base epoch for 2026-10-23
        epoch_ms = 1792714000000LL + esp_timer_get_time() / 1000;
    }

    /* Anchor coordinates (Shenzhen Nanshan Tech Park) if indoor without fix */
    double lat = gnss_fix ? gnss_lat : 22.540123;
    double lon = gnss_fix ? gnss_lon : 113.934567;
    float spd = gnss_fix ? gnss_speed : 0.0f;
    int rsrp_int = (int)lte_rsrp;

    /* Calculate gravitational attitude Euler angles (degrees) from onboard 3-axis accelerometer */
    float ax = s_last_ax_mg;
    float ay = s_last_ay_mg;
    float az = s_last_az_mg;
    float pitch_deg = atan2f(-ax, sqrtf(ay * ay + az * az)) * (180.0f / 3.1415926535f);
    float roll_deg = atan2f(ay, az) * (180.0f / 3.1415926535f);
    float yaw_deg = 0.0f;

    snprintf(
        s_telemetry_payload, sizeof(s_telemetry_payload),
        "{\"deviceId\":\"%s\",\"timestamp\":%" PRIi64 ",\"battery\":%d,\"batteryVoltage\":%.2f,"
        "\"isCharging\":false,\"rssi\":%d,\"rsrp\":%d,\"networkType\":\"4G LTE\","
        "\"motionState\":\"%s\",\"deviceWearState\":\"%s\",\"motionRms\":%.2f,"
        "\"pitch\":%.1f,\"roll\":%.1f,\"yaw\":%.1f,\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,"
        "\"firmwareVersion\":\"hw021_pcb1_p0_v0.2\",\"satellites\":%u,\"hdop\":%.1f,"
        "\"latitude\":%.6f,\"longitude\":%.6f,\"speed\":%.1f}",
        device_id, epoch_ms, (int)soc_pct, (double)(vbat_mv / 1000.0f),
        csq_rssi, rsrp_int,
        is_sos_alert ? "SOS_ALERT" : (motion_state ? motion_state : "normal"),
        wear_state ? wear_state : "wearable_or_bag",
        (double)motion_rms,
        (double)pitch_deg, (double)roll_deg, (double)yaw_deg,
        (double)(ax / 1000.0f), (double)(ay / 1000.0f), (double)(az / 1000.0f),
        gnss_sats, (double)gnss_hdop,
        lat, lon, (double)spd);

    char path[128];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/telemetry", device_id);

    bool sent_direct = false;
    esp_err_t err = ego_outbox_sync_submit(path, s_telemetry_payload, s_cellular_online, &sent_direct);

    s_web_post_count++;
    s_web_last_post_time_ms = esp_timer_get_time() / 1000;

    if (err == ESP_OK && sent_direct) {
        s_web_post_success++;
        s_web_last_status = 200;
        if (out_http_status) *out_http_status = 200;
        ESP_LOGI(TAG, "WEB_TELEMETRY_POST_OK status=200 device=%s bat=%d%% rsrp=%.1f",
                 device_id, (int)soc_pct, (double)lte_rsrp);
        return ESP_OK;
    } else {
        s_web_last_status = 0;
        if (out_http_status) *out_http_status = 0;
        ESP_LOGI(TAG, "WEB_TELEMETRY_QUEUED_OFFLINE device=%s bat=%d%% rsrp=%.1f (saved to Outbox cache)",
                 device_id, (int)soc_pct, (double)lte_rsrp);
        return ESP_OK;
    }
}

static void ml307a_post_sos_alert(const char *device_id, int vbat_mv, float soc_pct)
{
    int status = 0;
    char alert_payload[256];
    snprintf(alert_payload, sizeof(alert_payload),
        "{\"deviceId\":\"%s\",\"type\":\"SOS\",\"title\":\"紧急求助 (SOS 按键按下)\",\"desc\":\"用户短按硬件物理 KEY 键，触发求助\",\"lat\":22.540123,\"lon\":113.934567}",
        device_id);
    ml307a_post_web_json("/api/v1/alerts/trigger", alert_payload, &status);
    ESP_LOGI(TAG, "PCB1_SOS_ALERT_POSTED device=%s status=%d", device_id, status);
}

static void process_cli_command(const char *cmd_line);
static void pcb1_console_task(void *pvParameters);

/* Sample battery voltage helper (switched via GPIO2) */
static int sample_battery_voltage_mv(void)
{
    gpio_set_level(PIN_AD_CTRL, 1);
    esp_rom_delay_us(15000); /* 15ms settling */

    int64_t sum_mv = 0;
    const int count = 8;
    for (int i = 0; i < count; ++i) {
        int raw = 0, mv = 0;
        adc_oneshot_read(s_adc1_handle, ADC_CHANNEL_0, &raw);
        if (s_adc1_calibrated) {
            adc_cali_raw_to_voltage(s_adc1_cali_handle, raw, &mv);
            sum_mv += mv;
        } else {
            sum_mv += (raw * 3300 / 4095);
        }
        esp_rom_delay_us(1000);
    }
    gpio_set_level(PIN_AD_CTRL, 0);
    int mv_half = (int)(sum_mv / count);
    return mv_half * 2; /* R40=10K, R45=10K */
}

static float calc_soc_percent(int vbat_mv)
{
    if (vbat_mv <= 3300) return 0.0f;
    if (vbat_mv >= 4200) return 100.0f;
    return (float)(vbat_mv - 3300) / 9.0f;
}

/* --- STAGE 1: System, Flash & Partition Table Verification --- */
static void stage1_system_and_partitions(void)
{
    ESP_LOGI(TAG, "=== [STAGE 1] System, Flash & 4MB Partition Table Verification ===");

    /* Keep audio amp muted */
    gpio_config_t mute_cfg = {
        .pin_bit_mask = (1ULL << PIN_AUDIO_MUTE),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&mute_cfg);

    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);
    uint32_t flash_size = 0;
    uint32_t jedec_id = 0;
    esp_flash_get_size(NULL, &flash_size);
    esp_flash_read_id(NULL, &jedec_id);

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(s_device_id, sizeof(s_device_id), "ego-pcb1-%02x%02x%02x", mac[3], mac[4], mac[5]);

    const esp_app_desc_t *app_desc = esp_app_get_description();
    for (int i = 0; i < 32; ++i) {
        snprintf(s_elf_sha256 + i * 2, 3, "%02x", app_desc->app_elf_sha256[i]);
    }

    /* Inspect 4MB custom partitions */
    const esp_partition_t *part_fact = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_FACTORY, "factory");
    const esp_partition_t *part_coll = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x41, "ego_collection");
    const esp_partition_t *part_media = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x42, "ego_media");
    const esp_partition_t *part_outbox = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40, "ego_outbox");

    bool part_ok = (part_fact && part_coll && part_media && part_outbox);

    ESP_LOGI(
        TAG,
        "PCB1_TEST_SYSTEM status=%s chip=ESP32-S3 rev=%d.%d flash_jedec=0x%06" PRIx32 " flash_bytes=%" PRIu32 " device_id=%s elf_sha=%.12s... free_heap=%" PRIu32,
        part_ok ? "PASS" : "WARN",
        chip_info.revision / 100,
        chip_info.revision % 100,
        jedec_id,
        flash_size,
        s_device_id,
        s_elf_sha256,
        (uint32_t)esp_get_free_heap_size());

    if (part_ok) {
        ESP_LOGI(
            TAG,
            "PCB1_PARTITIONS_4MB factory=[0x%" PRIx32 ", %" PRIu32 "KB] coll=[0x%" PRIx32 ", %" PRIu32 "KB] media=[0x%" PRIx32 ", %" PRIu32 "KB] outbox=[0x%" PRIx32 ", %" PRIu32 "KB]",
            part_fact->address, part_fact->size / 1024,
            part_coll->address, part_coll->size / 1024,
            part_media->address, part_media->size / 1024,
            part_outbox->address, part_outbox->size / 1024);
    }

    append_summary(
        "STAGE1_SYSTEM: %s flash=%" PRIu32 "B partitions=(fact:%" PRIu32 "K,coll:%" PRIu32 "K,media:%" PRIu32 "K,outbox:%" PRIu32 "K)\n",
        part_ok ? "PASS" : "WARN", flash_size,
        part_fact ? part_fact->size / 1024 : 0,
        part_coll ? part_coll->size / 1024 : 0,
        part_media ? part_media->size / 1024 : 0,
        part_outbox ? part_outbox->size / 1024 : 0);
}

/* --- STAGE 2: Switched Battery Divider & ADC --- */
static void stage2_battery_adc(void)
{
    ESP_LOGI(TAG, "=== [STAGE 2] Battery Voltage Divider & Switch (AD_CTRL=GPIO2, ADC_V=GPIO1) ===");

    gpio_config_t ctrl_cfg = {
        .pin_bit_mask = (1ULL << PIN_AD_CTRL),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&ctrl_cfg);
    gpio_set_level(PIN_AD_CTRL, 0);

    adc_oneshot_unit_init_cfg_t init_cfg = { .unit_id = ADC_UNIT_1 };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_cfg, &s_adc1_handle));

    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc1_handle, ADC_CHANNEL_0, &chan_cfg));

    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .chan = ADC_CHANNEL_0,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    s_adc1_calibrated = (adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_adc1_cali_handle) == ESP_OK);

    int raw_off = 0;
    adc_oneshot_read(s_adc1_handle, ADC_CHANNEL_0, &raw_off);
    int mv_off = s_adc1_calibrated ? 0 : raw_off * 3300 / 4095;
    if (s_adc1_calibrated) {
        adc_cali_raw_to_voltage(s_adc1_cali_handle, raw_off, &mv_off);
    }

    int vbat_mv = sample_battery_voltage_mv();
    bool pass = (vbat_mv >= 3000 && vbat_mv <= 4500 && mv_off < 50);

    ESP_LOGI(
        TAG,
        "PCB1_TEST_BATTERY_ADC status=%s mv_off=%d vbat_mv=%d soc=%.1f%%",
        pass ? "PASS" : "WARN",
        mv_off, vbat_mv, calc_soc_percent(vbat_mv));

    append_summary("STAGE2_BATTERY_ADC: %s vbat=%dmV soc=%.1f%%\n", pass ? "PASS" : "WARN", vbat_mv, calc_soc_percent(vbat_mv));
}

/* --- STAGE 3: Buttons Check --- */
static void stage3_buttons(void)
{
    ESP_LOGI(TAG, "=== [STAGE 3] Buttons (KEY=GPIO6, BOOT=GPIO0) ===");
    gpio_config_t btn_cfg = {
        .pin_bit_mask = (1ULL << PIN_USER_KEY) | (1ULL << PIN_BOOT_KEY),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&btn_cfg);
    int key_lvl = gpio_get_level(PIN_USER_KEY);
    int boot_lvl = gpio_get_level(PIN_BOOT_KEY);
    bool pass = (key_lvl == 1 && boot_lvl == 1);
    ESP_LOGI(TAG, "PCB1_TEST_BUTTONS status=%s key_gpio6_idle=%d boot_gpio0_idle=%d", pass ? "PASS" : "WARN", key_lvl, boot_lvl);
    append_summary("STAGE3_BUTTONS: %s key_gpio6=%d boot_gpio0=%d\n", pass ? "PASS" : "WARN", key_lvl, boot_lvl);
}

/* --- STAGE 4: Onboard IMU SC7A20TR --- */
static esp_err_t i2c_write_reg(i2c_master_dev_handle_t dev, uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(dev, buf, sizeof(buf), 50);
}

static esp_err_t i2c_read_regs(i2c_master_dev_handle_t dev, uint8_t reg, uint8_t *out, size_t len)
{
    return i2c_master_transmit_receive(dev, &reg, 1, out, len, 50);
}

static void stage4_gsensor_sc7a20(void)
{
    ESP_LOGI(TAG, "=== [STAGE 4] Onboard G-Sensor U3 (SC7A20TR on SDA0=GPIO11, SCL0=GPIO12) ===");
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = PIN_GSENSOR_SDA0,
        .scl_io_num = PIN_GSENSOR_SCL0,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_i2c0_bus));

    uint8_t target_addr = 0x19;
    if (i2c_master_probe(s_i2c0_bus, target_addr, 30) != ESP_OK) {
        target_addr = 0x18;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = target_addr,
        .scl_speed_hz = 100000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_i2c0_bus, &dev_cfg, &s_sc7a20_dev));

    uint8_t who_am_i = 0;
    i2c_read_regs(s_sc7a20_dev, 0x0F, &who_am_i, 1);
    /* 50Hz, XYZ enable, BDU, +-2g */
    i2c_write_reg(s_sc7a20_dev, 0x20, 0x47);
    i2c_write_reg(s_sc7a20_dev, 0x23, 0x88);
    vTaskDelay(pdMS_TO_TICKS(30));

    uint8_t raw[6] = {0};
    int ax_mg = 0, ay_mg = 0, az_mg = 0, norm_mg = 0;
    if (i2c_read_regs(s_sc7a20_dev, 0x28 | 0x80, raw, 6) == ESP_OK) {
        int16_t rx = (int16_t)((raw[1] << 8) | raw[0]) >> 4;
        int16_t ry = (int16_t)((raw[3] << 8) | raw[2]) >> 4;
        int16_t rz = (int16_t)((raw[5] << 8) | raw[4]) >> 4;
        ax_mg = (rx * 1000) / 1024;
        ay_mg = (ry * 1000) / 1024;
        az_mg = (rz * 1000) / 1024;
        norm_mg = (int)sqrtf((float)(ax_mg * ax_mg + ay_mg * ay_mg + az_mg * az_mg));
    }
    bool pass = (who_am_i == 0x11 && norm_mg >= 700 && norm_mg <= 1300);
    ESP_LOGI(
        TAG,
        "PCB1_TEST_IMU_SC7A20 status=%s addr=0x%02x who_am_i=0x%02x a=(%d,%d,%d)mg |a|=%dmg",
        pass ? "PASS" : "WARN",
        target_addr, who_am_i, ax_mg, ay_mg, az_mg, norm_mg);
    append_summary("STAGE4_IMU_SC7A20: %s addr=0x%02x |a|=%dmg\n", pass ? "PASS" : "WARN", target_addr, norm_mg);
}

/* --- STAGE 5: Display Header J8 --- */
static void stage5_display_i2c_header(void)
{
    ESP_LOGI(TAG, "=== [STAGE 5] Display Header J8 (SDA1=GPIO34, SCL1=GPIO33) ===");
    gpio_config_t disp_cfg = {
        .pin_bit_mask = (1ULL << PIN_DISP_SDA1) | (1ULL << PIN_DISP_SCL1),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&disp_cfg);
    int sda1_idle = gpio_get_level(PIN_DISP_SDA1);
    int scl1_idle = gpio_get_level(PIN_DISP_SCL1);
    bool pass = (sda1_idle == 1 && scl1_idle == 1);
    ESP_LOGI(TAG, "PCB1_TEST_DISPLAY_I2C status=%s pullups=(%d,%d)", pass ? "PASS" : "WARN", sda1_idle, scl1_idle);
    append_summary("STAGE5_DISPLAY_I2C: %s pullups=(%d,%d)\n", pass ? "PASS" : "WARN", sda1_idle, scl1_idle);
}

/* --- STAGE 6: External GNSS Beitian BE-220 --- */
static void stage6_gnss_be220(void)
{
    ESP_LOGI(TAG, "=== [STAGE 6] External GNSS Module (Beitian BE-220 on J10, GPS_PWDN=GPIO26, 115200 baud) ===");
    esp_rom_gpio_pad_select_gpio(PIN_GPS_PWDN);
    gpio_config_t gps_pwr_cfg = {
        .pin_bit_mask = (1ULL << PIN_GPS_PWDN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&gps_pwr_cfg);
    gpio_set_level(PIN_GPS_PWDN, 1);
    vTaskDelay(pdMS_TO_TICKS(150));

    uart_config_t uart_cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_1, 2048, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_1, &uart_cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_1, PIN_GPS_TX2, PIN_GPS_RX2, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    uint8_t rx_buf[512];
    int nmea_count = 0;
    char sample_nmea[128] = {0};
    int64_t t0 = esp_timer_get_time() / 1000;
    while ((esp_timer_get_time() / 1000 - t0) < 1500) {
        int len = uart_read_bytes(UART_NUM_1, rx_buf, sizeof(rx_buf) - 1, pdMS_TO_TICKS(100));
        if (len > 0) {
            rx_buf[len] = '\0';
            char *p = (char *)rx_buf;
            while ((p = strstr(p, "$G")) != NULL) {
                nmea_count++;
                char *eol = strpbrk(p, "\r\n");
                if (eol) {
                    if (sample_nmea[0] == '\0' && (eol - p) < sizeof(sample_nmea) - 1) {
                        size_t l = eol - p;
                        memcpy(sample_nmea, p, l);
                        sample_nmea[l] = '\0';
                    }
                    p = eol + 1;
                } else {
                    break;
                }
            }
        }
    }
    bool pass = (nmea_count > 0);
    ESP_LOGI(TAG, "PCB1_TEST_GNSS_BE220 status=%s baud=115200 nmea_sentences=%d sample=\"%s\"", pass ? "PASS" : "FAIL", nmea_count, sample_nmea);
    append_summary("STAGE6_GNSS_BE220: %s baud=115200 nmea=%d sample=%s\n", pass ? "PASS" : "FAIL", nmea_count, sample_nmea[0] ? sample_nmea : "none");
}

/* --- STAGE 7: TF/SD Card SDMMC 1-Bit Mode & Black Box Storage Mount --- */
static void stage7_sd_card_check(void)
{
    ESP_LOGI(TAG, "=== [STAGE 7] TF/SD Card (CON1, 3.3V_SD via Q5, 1-bit SDMMC Mode & BlackBox VFS) ===");

    ego_blackbox_config_t bb_cfg = {
        .mount_point = "/sdcard",
        .pin_clk = PIN_SD_CLK,
        .pin_cmd = PIN_SD_CMD_U0TXD,
        .pin_d0 = PIN_SD_D0_U0RXD,
        .pin_pwr = PIN_CAM_PWDN,
        .format_if_mount_failed = true,
        .max_file_size_bytes = 5 * 1024 * 1024, /* 5MB */
    };

    esp_err_t ret = ego_blackbox_init(&bb_cfg);
    ego_blackbox_status_t bb_stat = {0};
    ego_blackbox_get_status(&bb_stat);

    bool pass = (ret == ESP_OK && bb_stat.is_mounted);

    ESP_LOGI(
        TAG,
        "PCB1_TEST_SDCARD status=%s name=\"%s\" capacity_mb=%" PRIu64 " free_mb=%" PRIu64 " session=\"%s\"",
        pass ? "PASS" : "FAIL",
        bb_stat.card_name, bb_stat.total_capacity_mb, bb_stat.free_space_mb, bb_stat.current_session_file);

    append_summary("STAGE7_SDCARD: %s name=%s cap=%" PRIu64 "MB free=%" PRIu64 "MB sess=%s\n",
        pass ? "PASS" : "FAIL", bb_stat.card_name, bb_stat.total_capacity_mb, bb_stat.free_space_mb,
        bb_stat.current_session_file[0] ? bb_stat.current_session_file : "none");
}

/* --- STAGE 8: Camera Safety & Strapping Check --- */
static void stage8_camera_check(void)
{
    ESP_LOGI(TAG, "=== [STAGE 8] Camera (TY-OV2640-75MM-V1.0 on J9, Safety Verification) ===");
    /* Keep CAM_PWDN=0 to keep 3.3V_SD powered and avoid back-powering shorted TWI lines */
    gpio_set_level(PIN_CAM_PWDN, 0);
    gpio_reset_pin(PIN_CAM_D0);
    gpio_set_direction(PIN_CAM_D0, GPIO_MODE_INPUT);
    gpio_set_pull_mode(PIN_CAM_D0, GPIO_PULLDOWN_ONLY);
    ESP_LOGI(TAG, "PCB1_TEST_CAMERA_OV2640 status=SKIPPED_ECN01_SHORT reason=\"J9 TWI shorted to 3.3V_VCC, camera isolated\"");
    append_summary("STAGE8_CAMERA_OV2640: SKIPPED_ECN01 (HW short isolated, SD operational)\n");
}

/* --- STAGE 9: 4G Modem ML307A-DSLN --- */
static void stage9_modem_ml307a(void)
{
    ESP_LOGI(TAG, "=== [STAGE 9] 4G Modem U1 (ML307A-DSLN, 4G_PWDN=GPIO15, TX1=GPIO36, RX1=GPIO37) ===");

    if (s_modem_mutex == NULL) {
        s_modem_mutex = xSemaphoreCreateMutex();
    }

    esp_rom_gpio_pad_select_gpio(PIN_4G_NETLIGHT);
    esp_rom_gpio_pad_select_gpio(PIN_4G_TX1);
    esp_rom_gpio_pad_select_gpio(PIN_4G_RX1);

    gpio_config_t pwr_cfg = {
        .pin_bit_mask = (1ULL << PIN_4G_PWDN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&pwr_cfg);
    gpio_set_level(PIN_4G_PWDN, 1); /* 4G_BAT powered */

    uart_config_t uart_cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_2, 8192, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_2, &uart_cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_2, PIN_4G_TX1, PIN_4G_RX1, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    gpio_set_pull_mode(PIN_4G_RX1, GPIO_PULLUP_ONLY);

    char resp[256];
    bool at_ok = false;
    for (int attempt = 1; attempt <= 20; ++attempt) {
        if (ml307a_at_send(NULL, "AT", resp, sizeof(resp), 300) == ESP_OK) {
            at_ok = true;
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(250));
    }

    if (at_ok) {
        char cpin[64] = {0}, cops[64] = {0}, csq[64] = {0}, cereg[64] = {0}, cgpaddr[128] = {0};
        send_at_and_log("ATE0", resp, sizeof(resp), 300);

        /* Wait up to 5s for SIM initialization */
        for (int s = 0; s < 10; ++s) {
            send_at_and_log("AT+CPIN?", cpin, sizeof(cpin), 500);
            if (strstr(cpin, "READY") != NULL) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(500));
        }

        /* Wait up to 6s for LTE network registration */
        for (int r = 0; r < 6; ++r) {
            send_at_and_log("AT+CEREG?", cereg, sizeof(cereg), 500);
            if (strstr(cereg, ",1") != NULL || strstr(cereg, ",5") != NULL) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(800));
        }

        send_at_and_log("AT+COPS?", cops, sizeof(cops), 500);
        send_at_and_log("AT+CSQ", csq, sizeof(csq), 500);
        send_at_and_log("AT+CGPADDR", cgpaddr, sizeof(cgpaddr), 500);

        /* Configure VoLTE and Call Presentation */
        send_at_and_log("AT+CAVIMS=1", resp, sizeof(resp), 500);
        send_at_and_log("AT+CLIP=1", resp, sizeof(resp), 500);
        send_at_and_log("AT+COLP=1", resp, sizeof(resp), 500);
        send_at_and_log("AT+CLCC", resp, sizeof(resp), 500);

        /* Verify live 4G DNS resolution to ego.example.invalid */
        char dns_resp[128] = {0};
        send_at_and_log("AT+MDNSGIP=\"ego.example.invalid\"", dns_resp, sizeof(dns_resp), 2000);
        s_cellular_online = (strstr(cereg, ",1") != NULL || strstr(cereg, ",5") != NULL);

        ESP_LOGI(TAG, "PCB1_TEST_MODEM_ML307A status=PASS cpin=\"%s\" cops=\"%s\" csq=\"%s\" cereg=\"%s\" cgpaddr=\"%s\"",
                 cpin, cops, csq, cereg, cgpaddr);
        append_summary("STAGE9_MODEM_ML307A: PASS cpin=[%s] cops=[%s] csq=[%s] ip=[%s]\n",
                       cpin, cops, csq, cgpaddr);
    } else {
        ESP_LOGE(TAG, "PCB1_TEST_MODEM_ML307A status=FAIL no_at_response");
        append_summary("STAGE9_MODEM_ML307A: FAIL no_at_response\n");
    }
}

/* --- STAGE 10: Wi-Fi RF Scan & XTAL Check --- */
static void stage10_wifi_rf_scan(void)
{
    ESP_LOGI(TAG, "=== [STAGE 10] ESP32-S3 2.4GHz Wi-Fi Scan & RF Validation ===");
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    wifi_scan_config_t scan_cfg = {
        .ssid = NULL,
        .bssid = NULL,
        .channel = 0,
        .show_hidden = true,
    };
    esp_err_t err = esp_wifi_scan_start(&scan_cfg, true);
    esp_wifi_scan_get_ap_num(&s_wifi_ap_count);

    int best_rssi = -127;
    uint8_t best_ch = 0;
    if (s_wifi_ap_count > 0) {
        uint16_t fetch = s_wifi_ap_count > 8 ? 8 : s_wifi_ap_count;
        static wifi_ap_record_t ap_records[8];
        if (esp_wifi_scan_get_ap_records(&fetch, ap_records) == ESP_OK && fetch > 0) {
            best_rssi = ap_records[0].rssi;
            best_ch = ap_records[0].primary;

            /* Compute SHA256 fingerprint of scanned BSSIDs */
            mbedtls_sha256_context sha_ctx;
            mbedtls_sha256_init(&sha_ctx);
            mbedtls_sha256_starts(&sha_ctx, 0);
            for (uint16_t i = 0; i < fetch; ++i) {
                mbedtls_sha256_update(&sha_ctx, ap_records[i].bssid, 6);
            }
            uint8_t hash[32];
            mbedtls_sha256_finish(&sha_ctx, hash);
            mbedtls_sha256_free(&sha_ctx);
            for (int i = 0; i < 32; ++i) {
                snprintf(s_wifi_hash + i * 2, 3, "%02x", hash[i]);
            }
        }
    }

    esp_wifi_stop();
    esp_wifi_deinit();

    bool pass = (err == ESP_OK && s_wifi_ap_count > 0);
    ESP_LOGI(
        TAG,
        "PCB1_TEST_WIFI_RF status=%s ap_count=%u best_rssi=%ddBm ch=%u hash=%.12s...",
        pass ? "PASS" : "WARN",
        s_wifi_ap_count, best_rssi, best_ch, s_wifi_hash);

    append_summary("STAGE10_WIFI_RF: %s ap_count=%u best_rssi=%ddBm hash=%.12s...\n",
        pass ? "PASS" : "WARN", s_wifi_ap_count, best_rssi, s_wifi_hash);
}

/* --- GNSS NMEA Sentence Parser --- */
static int nmea_split_fields(char *str, char *fields[], int max_fields)
{
    int count = 0;
    fields[count++] = str;
    while (*str && count < max_fields) {
        if (*str == ',' || *str == '*') {
            *str = '\0';
            fields[count++] = str + 1;
        }
        str++;
    }
    return count;
}

static void parse_nmea_gnrmc(char *line, bool *fix_valid, double *lat, double *lon, float *speed_mps, float *course, char *utc_time)
{
    /* $GNRMC,hhmmss.ss,status,lat,N/S,lon,E/W,speed_knots,course,ddmmyy,... */
    char *fields[16];
    int n = nmea_split_fields(line, fields, 16);
    if (n < 10) return;

    if (utc_time && strlen(fields[1]) > 0) {
        strncpy(utc_time, fields[1], 15);
        utc_time[15] = '\0';
    }

    char status = fields[2][0];
    *fix_valid = (status == 'A');

    if (*fix_valid) {
        char *raw_lat = fields[3];
        char ns = fields[4][0];
        char *raw_lon = fields[5];
        char ew = fields[6][0];

        if (strlen(raw_lat) >= 4 && strlen(raw_lon) >= 5) {
            double lat_val = atof(raw_lat);
            int lat_deg = (int)(lat_val / 100);
            double lat_min = lat_val - (lat_deg * 100);
            double calculated_lat = lat_deg + (lat_min / 60.0);
            if (ns == 'S') calculated_lat = -calculated_lat;
            *lat = calculated_lat;

            double lon_val = atof(raw_lon);
            int lon_deg = (int)(lon_val / 100);
            double lon_min = lon_val - (lon_deg * 100);
            double calculated_lon = lon_deg + (lon_min / 60.0);
            if (ew == 'W') calculated_lon = -calculated_lon;
            *lon = calculated_lon;
        }

        if (strlen(fields[7]) > 0) {
            *speed_mps = (float)(atof(fields[7]) * 0.514444);
        }
        if (strlen(fields[8]) > 0) {
            *course = (float)atof(fields[8]);
        }

        /* Synchronize System RTC Clock with Live Satellite UTC */
        char *date_str = fields[9];
        char *time_str = fields[1];
        if (strlen(date_str) == 6 && strlen(time_str) >= 6) {
            int day = (date_str[0] - '0') * 10 + (date_str[1] - '0');
            int mon = (date_str[2] - '0') * 10 + (date_str[3] - '0');
            int yr = 2000 + (date_str[4] - '0') * 10 + (date_str[5] - '0');
            int hr = (time_str[0] - '0') * 10 + (time_str[1] - '0');
            int min = (time_str[2] - '0') * 10 + (time_str[3] - '0');
            int sec = (time_str[4] - '0') * 10 + (time_str[5] - '0');
            if (day >= 1 && day <= 31 && mon >= 1 && mon <= 12 && yr >= 2026) {
                struct tm tm_utc = {
                    .tm_year = yr - 1900,
                    .tm_mon = mon - 1,
                    .tm_mday = day,
                    .tm_hour = hr,
                    .tm_min = min,
                    .tm_sec = sec
                };
                time_t epoch = mktime(&tm_utc);
                if (epoch > 1700000000) {
                    struct timeval tv = { .tv_sec = epoch, .tv_usec = 0 };
                    settimeofday(&tv, NULL);
                }
            }
        }
    }
}

static void parse_nmea_gngga(char *line, uint16_t *sats, float *hdop, float *alt)
{
    /* $GNGGA,hhmmss.ss,lat,N/S,lon,E/W,quality,num_sats,hdop,alt,M,... */
    char *fields[16];
    int n = nmea_split_fields(line, fields, 16);
    if (n < 10) return;

    if (strlen(fields[7]) > 0) {
        *sats = (uint16_t)atoi(fields[7]);
    }
    if (strlen(fields[8]) > 0) {
        *hdop = (float)atof(fields[8]);
    }
    if (alt && strlen(fields[9]) > 0) {
        *alt = (float)atof(fields[9]);
    }
}

static void process_cli_command(const char *cmd_line)
{
    while (*cmd_line == ' ' || *cmd_line == '\t') cmd_line++;
    if (*cmd_line == '\0') return;

    ESP_LOGI("CLI", "Command received: \"%s\"", cmd_line);

    if (strncmp(cmd_line, "dial ", 5) == 0 || strncmp(cmd_line, "call ", 5) == 0) {
        const char *num = cmd_line + 5;
        while (*num == ' ') num++;
        if (strlen(num) > 0) {
            strncpy(s_dial_phone_number, num, sizeof(s_dial_phone_number) - 1);
            s_dial_phone_number[sizeof(s_dial_phone_number) - 1] = '\0';
        }
        trigger_phone_call(s_dial_phone_number);
    } else if (strcmp(cmd_line, "hangup") == 0 || strcmp(cmd_line, "h") == 0) {
        trigger_phone_hangup();
    } else if (strcmp(cmd_line, "answer") == 0 || strcmp(cmd_line, "a") == 0) {
        trigger_phone_answer();
    } else if (strcmp(cmd_line, "post") == 0) {
        ESP_LOGI("CLI", "Manual Web telemetry post requested.");
        s_manual_post_flag = true;
    } else if (strcmp(cmd_line, "sos") == 0) {
        ESP_LOGI("CLI", "Manual SOS event triggered!");
        s_sos_triggered_flag = true;
        ego_blackbox_log_event("SOS_ALERT", "{\"source\":\"CLI\"}");
    } else if (strncmp(cmd_line, "setphone ", 9) == 0) {
        const char *num = cmd_line + 9;
        while (*num == ' ') num++;
        if (strlen(num) > 0) {
            strncpy(s_dial_phone_number, num, sizeof(s_dial_phone_number) - 1);
            s_dial_phone_number[sizeof(s_dial_phone_number) - 1] = '\0';
            ESP_LOGI("CLI", "Default test phone number updated to: %s", s_dial_phone_number);
        }
    } else if (strncmp(cmd_line, "setdevice ", 10) == 0) {
        const char *dev = cmd_line + 10;
        while (*dev == ' ') dev++;
        if (strlen(dev) > 0) {
            strncpy(s_web_device_id, dev, sizeof(s_web_device_id) - 1);
            s_web_device_id[sizeof(s_web_device_id) - 1] = '\0';
            ESP_LOGI("CLI", "Web Platform deviceId updated to: %s", s_web_device_id);
        }
    } else if (strncmp(cmd_line, "at ", 3) == 0) {
        const char *raw_at = cmd_line + 3;
        while (*raw_at == ' ') raw_at++;
        char at_resp[512] = {0};
        send_at_and_log(raw_at, at_resp, sizeof(at_resp), 3000);
        printf("\r\n--- AT RESPONSE ---\r\n%s\r\n-------------------\r\n", at_resp);
    } else if (strcmp(cmd_line, "status") == 0) {
        sim7670_call_status_t call_stat;
        sim7670_cellular_call_get_status(&s_call_ctx, &call_stat);
        int vbat_mv = sample_battery_voltage_mv();
        float soc = calc_soc_percent(vbat_mv);

        printf("\r\n============================================================\r\n");
        printf(" HW021_PCB1 (ESP32-S3 + ML307A) System Status\r\n");
        printf("============================================================\r\n");
        printf(" Device ID:        %s (Web ID: %s)\r\n", s_device_id, s_web_device_id);
        printf(" Battery:          %d mV (%.1f%% SoC)\r\n", vbat_mv, soc);
        printf(" Audio Amp 8002A:  %s (GPIO5)\r\n", s_audio_amp_unmuted ? "UNMUTED (Active)" : "MUTED (Standby)");
        printf(" VoLTE Call:       State: %s, Number: %s, Duration: %" PRIu32 "s\r\n",
               sim7670_call_state_to_str(call_stat.state),
               call_stat.phone_number[0] ? call_stat.phone_number : s_dial_phone_number,
               call_stat.call_duration_sec);
        printf(" Last Disconnect:  %s\r\n", sim7670_call_disconnect_reason_to_str(call_stat.last_disconnect_reason));
        printf(" Web Telemetry:    Target: https://ego.example.invalid/api/v1/devices/%s/telemetry\r\n", s_web_device_id);
        printf("                   Posts: %" PRIu32 " (Success: %" PRIu32 ", Fail: %" PRIu32 "), Last HTTP: %d\r\n",
               s_web_post_count, s_web_post_success, s_web_post_failed, s_web_last_status);
        printf(" Memory / Heap:    Free Heap: %" PRIu32 " B\r\n", (uint32_t)esp_get_free_heap_size());
        printf("============================================================\r\n\r\n");
    } else if (strncmp(cmd_line, "sd", 2) == 0 && (cmd_line[2] == ' ' || cmd_line[2] == '\0')) {
        const char *sub = cmd_line + 2;
        while (*sub == ' ') sub++;
        if (strlen(sub) == 0 || strcmp(sub, "status") == 0) {
            ego_blackbox_status_t bb_stat;
            ego_blackbox_get_status(&bb_stat);
            printf("\r\n============================================================\r\n");
            printf(" TF/SD Card Black Box Storage Status\r\n");
            printf("============================================================\r\n");
            printf(" Mounted:          %s\r\n", bb_stat.is_mounted ? "YES (Active FATFS)" : "NO (Failed/Not Inserted)");
            printf(" Card CID Name:    %s\r\n", bb_stat.card_name[0] ? bb_stat.card_name : "N/A");
            printf(" Total Capacity:   %" PRIu64 " MB\r\n", bb_stat.total_capacity_mb);
            printf(" Free Space:       %" PRIu64 " MB\r\n", bb_stat.free_space_mb);
            printf(" Records Written:  %" PRIu32 "\r\n", bb_stat.total_records_written);
            printf(" Current File:     %s\r\n", bb_stat.current_session_file[0] ? bb_stat.current_session_file : "none");
            printf(" Current Size:     %" PRIu32 " Bytes\r\n", bb_stat.current_file_bytes);
            printf(" Write Errors:     %" PRIu32 "\r\n", bb_stat.write_errors);
            printf("============================================================\r\n\r\n");
        } else if (strcmp(sub, "ls") == 0) {
            const char *target_dir = "/sdcard/ego_blackbox/sessions";
            printf("\r\n--- SD BlackBox Sessions (/sdcard/ego_blackbox/sessions) ---\r\n");
            DIR *d = opendir(target_dir);
            if (d) {
                struct dirent *de;
                int count = 0;
                while ((de = readdir(d)) != NULL) {
                    if (de->d_name[0] == '.') continue;
                    char fpath[320];
                    snprintf(fpath, sizeof(fpath), "%s/%s", target_dir, de->d_name);
                    struct stat st;
                    long fsz = 0;
                    if (stat(fpath, &st) == 0) fsz = (long)st.st_size;
                    printf("  %-28s %8ld bytes\r\n", de->d_name, fsz);
                    count++;
                }
                closedir(d);
                if (count == 0) printf("  (No session files)\r\n");
            } else {
                printf("  Failed to open sessions directory (Card not mounted?)\r\n");
            }

            printf("\r\n--- SD BlackBox Alerts (/sdcard/ego_blackbox/alerts) ---\r\n");
            DIR *ad = opendir("/sdcard/ego_blackbox/alerts");
            if (ad) {
                struct dirent *de;
                int count = 0;
                while ((de = readdir(ad)) != NULL) {
                    if (de->d_name[0] == '.') continue;
                    char fpath[320];
                    snprintf(fpath, sizeof(fpath), "/sdcard/ego_blackbox/alerts/%s", de->d_name);
                    struct stat st;
                    long fsz = 0;
                    if (stat(fpath, &st) == 0) fsz = (long)st.st_size;
                    printf("  %-28s %8ld bytes\r\n", de->d_name, fsz);
                    count++;
                }
                closedir(ad);
                if (count == 0) printf("  (No alert files)\r\n");
            } else {
                printf("  Failed to open alerts directory\r\n");
            }
            printf("------------------------------------------------------------\r\n\r\n");
        } else if (strncmp(sub, "cat ", 4) == 0) {
            const char *farg = sub + 4;
            while (*farg == ' ') farg++;
            char filename[64] = {0};
            int max_lines = 20;
            char arg2[16] = {0};
            sscanf(farg, "%63s %15s", filename, arg2);
            if (arg2[0]) {
                int l = atoi(arg2);
                if (l > 0) max_lines = l;
            }

            char fullpath[320];
            if (filename[0] == '/') {
                strncpy(fullpath, filename, sizeof(fullpath) - 1);
            } else if (strstr(filename, "event") || strstr(filename, "alert")) {
                snprintf(fullpath, sizeof(fullpath), "/sdcard/ego_blackbox/alerts/%s", filename);
            } else {
                snprintf(fullpath, sizeof(fullpath), "/sdcard/ego_blackbox/sessions/%s", filename);
            }

            printf("\r\n--- Displaying '%s' (max %d lines) ---\r\n", fullpath, max_lines);
            FILE *fp = fopen(fullpath, "r");
            if (!fp) {
                printf("Failed to open '%s'\r\n", fullpath);
            } else {
                char lbuf[768];
                int lcnt = 0;
                while (fgets(lbuf, sizeof(lbuf), fp) && lcnt < max_lines) {
                    printf("[%03d] %s", ++lcnt, lbuf);
                    if (strchr(lbuf, '\n') == NULL) printf("\r\n");
                }
                fclose(fp);
                printf("--- End of file (%d lines displayed) ---\r\n\r\n", lcnt);
            }
        } else if (strcmp(sub, "sync") == 0) {
            ego_blackbox_sync();
            printf("SD black box buffers flushed and synced to storage.\r\n");
        } else {
            printf("Usage: sd [status|ls|cat <filename> [lines]|sync]\r\n");
        }
    } else if (strncmp(cmd_line, "outbox", 6) == 0 && (cmd_line[6] == ' ' || cmd_line[6] == '\0')) {
        const char *sub = cmd_line + 6;
        while (*sub == ' ') sub++;
        if (strlen(sub) == 0 || strcmp(sub, "status") == 0) {
            ego_outbox_sync_status_t ostat;
            ego_outbox_sync_get_status(&ostat);
            printf("\r\n============================================================\r\n");
            printf(" Outbox Offline Cache & Cloud Resumption Status\r\n");
            printf("============================================================\r\n");
            printf(" Storage Directory: /sdcard/ego_blackbox/outbox\r\n");
            printf(" Pending in Queue:  %" PRIu32 " records\r\n", ostat.pending_count);
            printf(" Queue File Size:   %u Bytes\r\n", (unsigned)ostat.queue_file_bytes);
            printf(" Read Offset:       %ld Bytes\r\n", ostat.read_offset);
            printf(" Total Enqueued:    %" PRIu32 " records\r\n", ostat.total_enqueued);
            printf(" Total Acked (200): %" PRIu32 " records\r\n", ostat.total_acked);
            printf(" Total Failures:    %" PRIu32 "\r\n", ostat.total_failed);
            printf(" Cellular Online:   %s\r\n", s_cellular_online ? "YES (Registered LTE)" : "NO (Offline)");
            printf(" Simulated Offline: %s\r\n", ostat.sim_offline_mode ? "ACTIVE (Cache Forced)" : "DISABLED (Live Sync)");
            printf(" Sync State:        %s\r\n", ostat.is_draining ? "DRAINING (Resuming)" : (ostat.pending_count > 0 ? "WAITING (Backlogged)" : "IDLE (In-Sync)"));
            printf("============================================================\r\n\r\n");
        } else if (strncmp(sub, "offline", 7) == 0) {
            const char *arg = sub + 7;
            while (*arg == ' ') arg++;
            if (strcmp(arg, "on") == 0 || strcmp(arg, "1") == 0) {
                ego_outbox_sync_set_sim_offline(true);
                printf("Simulated offline mode ENABLED. Telemetry will accumulate in outbox queue.\r\n");
            } else if (strcmp(arg, "off") == 0 || strcmp(arg, "0") == 0) {
                ego_outbox_sync_set_sim_offline(false);
                printf("Simulated offline mode DISABLED. Telemetry resumption will drain queue.\r\n");
            } else {
                printf("Usage: outbox offline [on|off]\r\n");
            }
        } else if (strcmp(sub, "drain") == 0) {
            printf("Manual outbox drain triggered...\r\n");
            int drained = 0;
            while (ego_outbox_sync_step(s_cellular_online, true) > 0) {
                drained++;
                vTaskDelay(pdMS_TO_TICKS(500));
            }
            printf("Outbox drain complete. %d records synced.\r\n", drained);
        } else if (strcmp(sub, "clear") == 0) {
            ego_outbox_sync_clear();
            printf("Outbox queue cleared.\r\n");
        } else {
            printf("Usage: outbox [status|offline on/off|drain|clear]\r\n");
        }
    } else if (strcmp(cmd_line, "help") == 0 || strcmp(cmd_line, "?") == 0) {
        printf("\r\n--- Available CLI Commands ---\r\n");
        printf("  dial <number>     : Dial VoLTE test call (e.g. 'dial 10086' or phone num)\r\n");
        printf("  hangup (or 'h')   : Hang up active call & mute 8002A audio amp\r\n");
        printf("  answer (or 'a')   : Answer incoming voice call & unmute 8002A\r\n");
        printf("  post              : Trigger immediate Web platform telemetry upload\r\n");
        printf("  sos               : Trigger SOS alert event & dial emergency number\r\n");
        printf("  setphone <number> : Set default test phone number (current: %s)\r\n", s_dial_phone_number);
        printf("  setdevice <id>    : Set Web platform device ID (current: %s)\r\n", s_web_device_id);
        printf("  status            : Print system, battery, call & Web telemetry status\r\n");
        printf("  sd [status|ls|cat|sync]   : SD card black box storage commands\r\n");
        printf("  outbox [status|offline|drain|clear] : Outbox offline cache and sync status\r\n");
        printf("  at <command>      : Send raw AT command to ML307A (e.g. 'at AT+CSQ')\r\n");
        printf("  help (or '?')     : Show this command list\r\n");
        printf("  Hardware KEY (GPIO6): Short press = Answer/Hangup/SOS; Long press (>2s) = Dial %s\r\n\r\n", s_dial_phone_number);
    } else {
        printf("Unknown command: '%s'. Type 'help' for available commands.\r\n", cmd_line);
    }
}

static void pcb1_console_task(void *pvParameters)
{
    (void)pvParameters;
    char line_buf[512];
    int pos = 0;

    int flags = fcntl(fileno(stdin), F_GETFL, 0);
    fcntl(fileno(stdin), F_SETFL, flags | O_NONBLOCK);

    ESP_LOGI(TAG, "============================================================");
    ESP_LOGI(TAG, "=== HW021_PCB1 USB-Serial Interactive CLI Console Ready ===");
    ESP_LOGI(TAG, "=== Commands: dial | hangup | answer | post | status | sd | at ===");
    ESP_LOGI(TAG, "============================================================");

    while (true) {
        char c = 0;
        int n = read(fileno(stdin), &c, 1);
        if (n > 0) {
            if (c == '\r' || c == '\n') {
                if (pos > 0) {
                    line_buf[pos] = '\0';
                    process_cli_command(line_buf);
                    pos = 0;
                }
            } else if (c == '\b' || c == 0x7F) {
                if (pos > 0) {
                    pos--;
                }
            } else if (pos < (int)sizeof(line_buf) - 1 && c >= 32 && c <= 126) {
                line_buf[pos++] = c;
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
}

/* --- STAGE 11: Integrated P0 Runtime Loop --- */
static void run_integrated_p0_loop(void)
{
    ESP_LOGI(TAG, "============================================================");
    ESP_LOGI(TAG, "=== [STAGE 11] Entering Integrated HW021_PCB1 P0 Runtime ===");
    ESP_LOGI(TAG, "============================================================");

    /* Initialize Ego-State Engine */
    ego_state_engine_init(&s_ego_ctx, s_device_id, 1, "hw021_pcb1_p0_v0.2", s_elf_sha256);

    /* Initialize Cellular Call Manager */
    sim7670_cellular_call_config_t call_cfg = {
        .at_send = ml307a_at_send,
        .user_ctx = NULL,
        .clock_fn = get_monotonic_time_us,
    };
    sim7670_cellular_call_init(&s_call_ctx, &call_cfg);

    /* Initialize Local-First Outbox Sync Engine */
    ego_outbox_sync_config_t outbox_cfg = {
        .storage_dir = "/sdcard/ego_blackbox/outbox",
        .post_fn = ml307a_post_web_json,
        .max_queue_bytes = 10 * 1024 * 1024,
    };
    ego_outbox_sync_init(&outbox_cfg);

    /* Launch Interactive USB-Serial CLI Task */
    xTaskCreate(pcb1_console_task, "pcb1_cli", 8192, NULL, 5, NULL);

    const esp_partition_t *part_outbox = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40, "ego_outbox");

    int64_t last_eval_ms = esp_timer_get_time() / 1000;
    int64_t last_imu_ms = esp_timer_get_time() / 1000;
    int64_t last_post_ms = esp_timer_get_time() / 1000;
    uint32_t eval_cycle = 0;

    int key_down_ticks = 0;
    bool key_long_pressed = false;

    bool gnss_fix = false;
    double gnss_lat = 0.0, gnss_lon = 0.0;
    float gnss_speed = 0.0f, gnss_course = 0.0f, gnss_hdop = 99.0f;
    uint16_t gnss_sats = 0;
    char gnss_utc[16] = "000000";

    float lte_rsrp = -85.0f;
    int csq_rssi = 28;
    char lte_cell_id[32] = "46000_12345";

    /* Continuous P0 Runtime Loop */
    while (true) {
        int64_t now_ms = esp_timer_get_time() / 1000;

        /* Task A: 25 Hz IMU Ingestion (every 40ms) */
        if (now_ms - last_imu_ms >= 40) {
            last_imu_ms = now_ms;
            uint8_t raw[6] = {0};
            if (s_sc7a20_dev && i2c_read_regs(s_sc7a20_dev, 0x28 | 0x80, raw, 6) == ESP_OK) {
                int16_t rx = (int16_t)((raw[1] << 8) | raw[0]) >> 4;
                int16_t ry = (int16_t)((raw[3] << 8) | raw[2]) >> 4;
                int16_t rz = (int16_t)((raw[5] << 8) | raw[4]) >> 4;
                float ax_mg = (float)(rx * 1000) / 1024.0f;
                float ay_mg = (float)(ry * 1000) / 1024.0f;
                float az_mg = (float)(rz * 1000) / 1024.0f;
                s_last_ax_mg = ax_mg;
                s_last_ay_mg = ay_mg;
                s_last_az_mg = az_mg;
                ego_state_engine_feed_imu(&s_ego_ctx, ax_mg, ay_mg, az_mg, 0.0f, 0.0f, 0.0f, get_monotonic_time_ns(), false);
            }
        }

        /* Task B: Poll GNSS UART1 with line-buffered sentence reassembly */
        static char s_gnss_stream_buf[1024];
        static int s_gnss_stream_len = 0;
        static bool s_last_gnss_fix = false;

        uint8_t raw_in[256];
        int n_gnss = uart_read_bytes(UART_NUM_1, raw_in, sizeof(raw_in), pdMS_TO_TICKS(10));
        if (n_gnss > 0) {
            if (s_gnss_stream_len + n_gnss < sizeof(s_gnss_stream_buf) - 1) {
                memcpy(s_gnss_stream_buf + s_gnss_stream_len, raw_in, n_gnss);
                s_gnss_stream_len += n_gnss;
                s_gnss_stream_buf[s_gnss_stream_len] = '\0';
            } else {
                s_gnss_stream_len = 0; // Prevent overflow
            }

            char *line_start = s_gnss_stream_buf;
            char *line_end = NULL;
            while ((line_end = strpbrk(line_start, "\r\n")) != NULL) {
                *line_end = '\0';
                char *stmt = strstr(line_start, "$G");
                if (stmt) {
                    if (strncmp(stmt, "$GNRMC", 6) == 0 || strncmp(stmt, "$GPRMC", 6) == 0) {
                        parse_nmea_gnrmc(stmt, &gnss_fix, &gnss_lat, &gnss_lon, &gnss_speed, &gnss_course, gnss_utc);
                    } else if (strncmp(stmt, "$GNGGA", 6) == 0 || strncmp(stmt, "$GPGGA", 6) == 0) {
                        parse_nmea_gngga(stmt, &gnss_sats, &gnss_hdop, NULL);
                    }
                }
                line_start = line_end + 1;
                while (*line_start == '\r' || *line_start == '\n') line_start++;
            }

            int remaining = s_gnss_stream_len - (line_start - s_gnss_stream_buf);
            if (remaining > 0 && line_start > s_gnss_stream_buf) {
                memmove(s_gnss_stream_buf, line_start, remaining);
                s_gnss_stream_len = remaining;
                s_gnss_stream_buf[s_gnss_stream_len] = '\0';
            } else if (line_start >= s_gnss_stream_buf + s_gnss_stream_len) {
                s_gnss_stream_len = 0;
            }

            if (gnss_fix && !s_last_gnss_fix) {
                ESP_LOGI(TAG, "🎯 [GNSS 3D FIX ACQUIRED] lat=%.6f lon=%.6f sats=%u speed=%.1f hdop=%.1f",
                         gnss_lat, gnss_lon, gnss_sats, (double)gnss_speed, (double)gnss_hdop);
            }
            s_last_gnss_fix = gnss_fix;

            ego_state_engine_feed_location(
                &s_ego_ctx,
                gnss_fix,
                gnss_speed,
                gnss_lat,
                gnss_lon,
                gnss_hdop,
                gnss_sats,
                gnss_course,
                get_monotonic_time_ns(),
                false);
        }

        /* Task C: Poll Modem UART2 for URCs */
        uint8_t urc_buf[256];
        int n_urc = uart_read_bytes(UART_NUM_2, urc_buf, sizeof(urc_buf) - 1, pdMS_TO_TICKS(10));
        if (n_urc > 0) {
            urc_buf[n_urc] = '\0';
            char *line = (char *)urc_buf;
            while (*line) {
                char *eol = strpbrk(line, "\r\n");
                if (eol) {
                    *eol = '\0';
                    if (strlen(line) > 0) {
                        sim7670_cellular_call_handle_urc(&s_call_ctx, line);
                    }
                    line = eol + 1;
                } else {
                    if (strlen(line) > 0) {
                        sim7670_cellular_call_handle_urc(&s_call_ctx, line);
                    }
                    break;
                }
            }
        }

        /* Task D: Button KEY (GPIO6) Dual-Mode Short/Long Press */
        bool key_pressed = (gpio_get_level(PIN_USER_KEY) == 0); /* Active LOW */
        if (key_pressed) {
            key_down_ticks++;
            if (key_down_ticks >= 200 && !key_long_pressed) { /* Held >= 2.0s */
                key_long_pressed = true;
                ESP_LOGI(TAG, "KEY (GPIO6) LONG PRESS (>2s) -> Initiating Phone Call Test to %s...", s_dial_phone_number);
                trigger_phone_call(s_dial_phone_number);
            }
        } else {
            if (key_down_ticks >= 4 && !key_long_pressed) { /* Short press (40ms - 1990ms) */
                sim7670_call_status_t call_stat;
                sim7670_cellular_call_get_status(&s_call_ctx, &call_stat);
                if (call_stat.state == SIM7670_CALL_STATE_INCOMING) {
                    ESP_LOGI(TAG, "KEY (GPIO6) SHORT PRESS -> Answering incoming call...");
                    trigger_phone_answer();
                } else if (call_stat.state == SIM7670_CALL_STATE_ACTIVE || call_stat.state == SIM7670_CALL_STATE_DIALING || call_stat.state == SIM7670_CALL_STATE_ALERTING) {
                    ESP_LOGI(TAG, "KEY (GPIO6) SHORT PRESS -> Hanging up active call...");
                    trigger_phone_hangup();
                } else {
                    ESP_LOGI(TAG, "KEY (GPIO6) SHORT PRESS -> SOS Alert Triggered!");
                    s_sos_triggered_flag = true;
                    ego_blackbox_log_event("SOS_ALERT", "{\"source\":\"BUTTON_KEY\"}");
                }
            }
            key_down_ticks = 0;
            key_long_pressed = false;
        }

        /* Automatic audio amplifier mute management linked to call state */
        sim7670_call_status_t cur_call;
        sim7670_cellular_call_get_status(&s_call_ctx, &cur_call);
        if (cur_call.state == SIM7670_CALL_STATE_DIALING || cur_call.state == SIM7670_CALL_STATE_ALERTING ||
            cur_call.state == SIM7670_CALL_STATE_INCOMING || cur_call.state == SIM7670_CALL_STATE_ACTIVE) {
            if (!s_audio_amp_unmuted) {
                set_audio_amp_mute(false);
            }
        } else {
            if (s_audio_amp_unmuted) {
                set_audio_amp_mute(true);
            }
        }

        /* Task E: 5-Second Evaluation & Telemetry Outbox Commit */
        if (now_ms - last_eval_ms >= 5000) {
            last_eval_ms = now_ms;
            eval_cycle++;

            /* 1. Power observation */
            int vbat_mv = sample_battery_voltage_mv();
            float soc_pct = calc_soc_percent(vbat_mv);
            ego_state_engine_feed_power(&s_ego_ctx, soc_pct, vbat_mv, false, true, get_monotonic_time_ns(), false);

            /* 2. Network observation (poll signal from ML307A) */
            char cesq[64] = {0};
            if (ml307a_at_send(NULL, "AT+CESQ", cesq, sizeof(cesq), 300) == ESP_OK) {
                char *p = strstr(cesq, "+CESQ:");
                if (p) {
                    int rxlev, ber, rscp, ecno, rsrq, raw_rsrp;
                    if (sscanf(p, "+CESQ: %d,%d,%d,%d,%d,%d", &rxlev, &ber, &rscp, &ecno, &rsrq, &raw_rsrp) == 6) {
                        if (raw_rsrp >= 0 && raw_rsrp <= 97) {
                            lte_rsrp = -140.0f + (float)raw_rsrp;
                        }
                    }
                }
            }
            char csq_resp[64] = {0};
            if (ml307a_at_send(NULL, "AT+CSQ", csq_resp, sizeof(csq_resp), 300) == ESP_OK) {
                char *p = strstr(csq_resp, "+CSQ:");
                if (p) {
                    int rssi_val = 0, ber_val = 0;
                    if (sscanf(p, "+CSQ: %d,%d", &rssi_val, &ber_val) >= 1) {
                        if (rssi_val != 99) csq_rssi = rssi_val;
                    }
                }
            }
            char cereg_resp[64] = {0};
            if (ml307a_at_send(NULL, "AT+CEREG?", cereg_resp, sizeof(cereg_resp), 300) == ESP_OK) {
                s_cellular_online = (strstr(cereg_resp, ",1") != NULL || strstr(cereg_resp, ",5") != NULL);
            }

            ego_state_engine_feed_network(
                &s_ego_ctx,
                EGO_NETWORK_LTE,
                lte_rsrp,
                lte_cell_id,
                s_wifi_ap_count,
                s_wifi_hash,
                get_monotonic_time_ns(),
                false);

            /* 3. Run Ego-State Evaluation */
            ego_state_estimation_t est;
            ego_evidence_chain_t ev;
            esp_err_t eval_err = ego_state_engine_evaluate(&s_ego_ctx, get_monotonic_time_ns(), 5000, &est, &ev);

            /* 4. Poll Cellular Call Status */
            sim7670_cellular_call_poll_status(&s_call_ctx, &cur_call);

            /* 5. Commit Outbox Record to 4MB Flash (ego_outbox partition) */
            uint32_t outbox_crc = 0;
            if (part_outbox && eval_err == ESP_OK) {
                pcb1_outbox_record_t rec;
                memset(&rec, 0, sizeof(rec));
                rec.magic = PCB1_OUTBOX_MAGIC;
                rec.sequence = eval_cycle;
                strncpy(rec.estimation_id, est.estimation_id, sizeof(rec.estimation_id) - 1);
                strncpy(rec.evidence_digest, ev.evidence_digest, sizeof(rec.evidence_digest) - 1);
                rec.timestamp_ns = est.timestamp_monotonic_ns;

                int p_len = snprintf(
                    rec.payload_json, sizeof(rec.payload_json),
                    "{\"seq\":%" PRIu32 ",\"mobility\":\"%s\",\"anomaly\":\"%s\",\"wear\":\"%s\",\"vbat\":%d,\"soc\":%.1f,\"rsrp\":%.1f,\"sats\":%u,\"call\":\"%s\"}",
                    eval_cycle,
                    ego_spatial_mobility_to_str(est.spatial_mobility),
                    ego_posture_anomaly_to_str(est.posture_anomaly),
                    ego_device_wear_to_str(est.device_wear_state),
                    vbat_mv, soc_pct, (double)lte_rsrp, gnss_sats,
                    sim7670_call_state_to_str(cur_call.state));
                rec.payload_len = (p_len > 0) ? (uint32_t)p_len : 0;
                rec.checksum_crc32 = calc_crc32((const uint8_t *)rec.payload_json, rec.payload_len);
                outbox_crc = rec.checksum_crc32;

                esp_partition_erase_range(part_outbox, 0, 4096);
                esp_partition_write(part_outbox, 0, &rec, sizeof(rec));
            }

            /* 6. Append Record to SD Card Local Black Box */
            struct timeval tv_bb;
            gettimeofday(&tv_bb, NULL);
            int64_t bb_ts = (tv_bb.tv_sec > 1700000000) ? ((int64_t)tv_bb.tv_sec * 1000 + tv_bb.tv_usec / 1000) : (1792714000000LL + now_ms);
            ego_blackbox_record_t bb_rec = {
                .timestamp_ms = bb_ts,
                .cycle = eval_cycle,
                .est_id = est.estimation_id,
                .mobility_str = ego_spatial_mobility_to_str(est.spatial_mobility),
                .wear_str = ego_device_wear_to_str(est.device_wear_state),
                .anomaly_str = ego_posture_anomaly_to_str(est.posture_anomaly),
                .confidence = est.confidence,
                .evidence_digest = ev.evidence_digest,
                .outbox_crc = outbox_crc,
                .ax_mg = s_last_ax_mg,
                .ay_mg = s_last_ay_mg,
                .az_mg = s_last_az_mg,
                .motion_rms = ev.imu_evidence.motion_rms_m_s2,
                .imu_rate_hz = ev.imu_evidence.sample_rate_hz,
                .vbat_mv = vbat_mv,
                .soc_pct = soc_pct,
                .is_charging = false,
                .lte_rsrp = (int)lte_rsrp,
                .csq_rssi = csq_rssi,
                .network_type = "4G_LTE",
                .gnss_fix = gnss_fix,
                .gnss_lat = gnss_lat,
                .gnss_lon = gnss_lon,
                .gnss_speed = gnss_speed,
                .gnss_hdop = gnss_hdop,
                .gnss_sats = gnss_sats,
                .call_state_str = sim7670_call_state_to_str(cur_call.state),
                .is_sos_active = s_sos_triggered_flag,
            };
            ego_blackbox_log_record(&bb_rec);

            /* Log high-fidelity structured runtime state */
            ESP_LOGI(
                TAG,
                "PCB1_RUNTIME_EGO_STATE cycle=%" PRIu32 " est_id=%s mobility=%s anomaly=%s wear=%s conf=%.2f imu_rate=%.1fHz rms=%.2f vbat=%dmV soc=%.1f%% lte_rsrp=%.1fdBm gnss_fix=%d sats=%u call_state=%s digest=%.12s... outbox_crc=0x%08" PRIx32,
                eval_cycle,
                est.estimation_id,
                ego_spatial_mobility_to_str(est.spatial_mobility),
                ego_posture_anomaly_to_str(est.posture_anomaly),
                ego_device_wear_to_str(est.device_wear_state),
                (double)est.confidence,
                (double)ev.imu_evidence.sample_rate_hz,
                (double)ev.imu_evidence.motion_rms_m_s2,
                vbat_mv, soc_pct, (double)lte_rsrp,
                gnss_fix ? 1 : 0, gnss_sats,
                sim7670_call_state_to_str(cur_call.state),
                ev.evidence_digest,
                outbox_crc);

            /* Task F: Web Platform Periodic or Event-Driven Telemetry Ingest */
            static float s_reported_pitch = 0.0f;
            static float s_reported_roll = 0.0f;
            float cur_pitch_deg = atan2f(-s_last_ax_mg, sqrtf(s_last_ay_mg * s_last_ay_mg + s_last_az_mg * s_last_az_mg)) * (180.0f / 3.1415926535f);
            float cur_roll_deg = atan2f(s_last_ay_mg, s_last_az_mg) * (180.0f / 3.1415926535f);
            bool attitude_changed = (fabsf(cur_pitch_deg - s_reported_pitch) > 12.0f) ||
                                    (fabsf(cur_roll_deg - s_reported_roll) > 12.0f);
            bool should_post_telemetry = (now_ms - last_post_ms >= 12000) ||
                                         ((now_ms - last_post_ms >= 2000) && (attitude_changed || ev.imu_evidence.motion_rms_m_s2 > 0.16f)) ||
                                         s_manual_post_flag || s_sos_triggered_flag;
            if (should_post_telemetry && cur_call.state == SIM7670_CALL_STATE_IDLE) {
                last_post_ms = now_ms;
                s_reported_pitch = cur_pitch_deg;
                s_reported_roll = cur_roll_deg;
                bool is_sos = s_sos_triggered_flag;
                int post_http_status = 0;

                ml307a_post_web_telemetry(
                    s_web_device_id,
                    vbat_mv,
                    soc_pct,
                    lte_rsrp,
                    csq_rssi,
                    ego_spatial_mobility_to_str(est.spatial_mobility),
                    ego_device_wear_to_str(est.device_wear_state),
                    ev.imu_evidence.motion_rms_m_s2,
                    gnss_fix,
                    gnss_lat,
                    gnss_lon,
                    gnss_speed,
                    gnss_sats,
                    gnss_hdop,
                    is_sos,
                    &post_http_status);

                if (s_sos_triggered_flag) {
                    ml307a_post_sos_alert(s_web_device_id, vbat_mv, soc_pct);
                    s_sos_triggered_flag = false;
                }
                s_manual_post_flag = false;
            }

            if (eval_cycle == 12) {
                ESP_LOGI(TAG, "=== HW021_PCB1 Integrated P0 12-Cycle Bring-Up Milestone Reached. Continuing continuous product operation... ===");
            }
        }

        /* Task G: Incremental Outbox Drain / Breakpoint Resumption */
        static int64_t last_sync_drain_ms = 0;
        if (now_ms - last_sync_drain_ms >= 1500) {
            last_sync_drain_ms = now_ms;
            if (cur_call.state == SIM7670_CALL_STATE_IDLE && s_cellular_online) {
                ego_outbox_sync_step(s_cellular_online, true);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void app_main(void)
{
    /* Wait 2.5s so USB Serial/JTAG host on COM8 connects before stage logs start */
    vTaskDelay(pdMS_TO_TICKS(2500));

    ESP_LOGI(TAG, "============================================================");
    ESP_LOGI(TAG, "HW021_C1_ESP32MODEL_VR00 (PCB1) Integrated Firmware & Bring-Up");
    ESP_LOGI(TAG, "============================================================");

    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    stage1_system_and_partitions();
    stage2_battery_adc();
    stage3_buttons();
    stage4_gsensor_sc7a20();
    stage5_display_i2c_header();
    stage6_gnss_be220();
    stage7_sd_card_check();
    stage8_camera_check();
    stage9_modem_ml307a();
    stage10_wifi_rf_scan();

    ESP_LOGI(TAG, "=== PCB1_BRINGUP_ALL_STAGES_COMPLETE ===");
    ESP_LOGI(TAG, "--- BRING-UP SUMMARY ---\n%s", s_summary_report);

    /* Transition into the integrated multi-sensor P0 runtime loop */
    run_integrated_p0_loop();

    /* Continue running indefinitely */
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
