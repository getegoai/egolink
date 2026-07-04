#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"

#include "driver/i2c_master.h"
#include "esp_err.h"
#include "cJSON.h"

#define AMOLED_I2C_FREQ_HZ 100000
#define AMOLED_I2C_TIMEOUT_MS 1000

#define AXP2101_ADDR 0x34
#define AXP2101_CHIP_ID_REG 0x03
#define AXP2101_EXPECTED_CHIP_ID 0x4A
#define AXP2101_DC_ONOFF_DVM_CTRL 0x80
#define AXP2101_DC_VOL0_CTRL 0x82
#define AXP2101_LDO_ONOFF_CTRL0 0x90
#define AXP2101_LDO_VOL0_CTRL 0x92
#define AXP2101_DC1_3300MV_VALUE ((3300 - 1500) / 100)
#define AXP2101_ALDO1_3300MV_VALUE ((3300 - 500) / 100)

#define QMI8658_ADDR 0x6B
#define QMI8658_WHOAMI_EXPECTED 0x05
#define QMI8658_REG_WHOAMI 0x00
#define QMI8658_REG_REVISION 0x01
#define QMI8658_REG_CTRL1 0x02
#define QMI8658_REG_CTRL2 0x03
#define QMI8658_REG_CTRL3 0x04
#define QMI8658_REG_CTRL5 0x06
#define QMI8658_REG_CTRL7 0x08
#define QMI8658_REG_CTRL8 0x09
#define QMI8658_REG_STATUS_INT 0x2D
#define QMI8658_REG_STATUS0 0x2E
#define QMI8658_REG_TIMESTAMP_L 0x30
#define QMI8658_REG_TEMPERATURE_L 0x33
#define QMI8658_REG_RESET 0x60
#define QMI8658_REG_RST_RESULT 0x4D
#define QMI8658_RESET_VALUE 0xB0
#define QMI8658_RST_RESULT_VALUE 0x80
#define QMI8658_CTRL1_ADDR_AUTO_INCREMENT 0x40
#define QMI8658_CTRL2_ACCEL_4G_1000HZ 0x13
#define QMI8658_CTRL3_GYRO_512DPS_224HZ 0x55
#define QMI8658_CTRL5_ACCEL_GYRO_LPF_MODE0 0x11
#define QMI8658_CTRL7_ENABLE_ACCEL_GYRO 0x03
#define QMI8658_CTRL8_CTRL9_HANDSHAKE_STATUS_INT 0x80

typedef struct {
    bool present;
    uint8_t chip_id;
    uint8_t dc_onoff_before;
    uint8_t dc_onoff_after;
    uint8_t ldo_onoff_before;
    uint8_t ldo_onoff_after;
    esp_err_t status;
} pmu_probe_t;

typedef struct {
    bool present;
    uint8_t whoami;
    uint8_t revision;
    uint8_t reset_result;
    esp_err_t status;
} qmi_probe_t;


#define DEMO_DEVICE_ID "wearable-node-001"
#define DEMO_ROLE "wearable_node"
#define DEMO_PROTOCOL_VERSION "0.2"
#define DEMO_FIRMWARE "egolink_amoled_safety_demo"
#define DEMO_BOARD "ESP32-S3-Touch-AMOLED-2.06"
#define COMMAND_LINE_MAX 512
#define COMMAND_ID_MAX 96
#define DISPLAY_TEXT_MAX 160
#define STATUS_TEXT_MAX 96
#define SCREEN_TEXT_WIDTH 372

typedef struct {
    char cmd_id[COMMAND_ID_MAX];
    char title[DISPLAY_TEXT_MAX];
    char prompt[DISPLAY_TEXT_MAX];
    char severity[32];
} ask_user_command_t;

typedef struct {
    char cmd_id[COMMAND_ID_MAX];
    char line1[STATUS_TEXT_MAX];
    char line2[STATUS_TEXT_MAX];
    char line3[STATUS_TEXT_MAX];
    char footer[STATUS_TEXT_MAX];
} display_status_t;

static uint32_t s_seq = 1;
static lv_obj_t *s_status_label;
static char s_active_cmd_id[COMMAND_ID_MAX];
static bool s_response_sent;
static bool s_prompt_active;

static i2c_master_bus_handle_t s_i2c_bus;
static i2c_master_dev_handle_t s_axp2101_dev;
static i2c_master_dev_handle_t s_qmi8658_dev;

static i2c_master_dev_handle_t *device_slot_for_addr(uint8_t addr)
{
    if (addr == AXP2101_ADDR) {
        return &s_axp2101_dev;
    }
    if (addr == QMI8658_ADDR) {
        return &s_qmi8658_dev;
    }
    return NULL;
}

static esp_err_t i2c_device_for_addr(uint8_t addr, i2c_master_dev_handle_t *out_dev)
{
    i2c_master_dev_handle_t *slot = device_slot_for_addr(addr);
    if (slot == NULL || out_dev == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (*slot != NULL) {
        *out_dev = *slot;
        return ESP_OK;
    }
    if (s_i2c_bus == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = AMOLED_I2C_FREQ_HZ,
    };
    esp_err_t err = i2c_master_bus_add_device(s_i2c_bus, &dev_cfg, slot);
    if (err == ESP_OK) {
        *out_dev = *slot;
    }
    return err;
}

static esp_err_t i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len)
{
    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_device_for_addr(addr, &dev);
    if (err != ESP_OK) {
        return err;
    }
    return i2c_master_transmit_receive(
        dev,
        &reg,
        1,
        data,
        len,
        AMOLED_I2C_TIMEOUT_MS);
}

static esp_err_t i2c_read_u8(uint8_t addr, uint8_t reg, uint8_t *value)
{
    return i2c_read(addr, reg, value, 1);
}

static esp_err_t i2c_write_u8(uint8_t addr, uint8_t reg, uint8_t value)
{
    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_device_for_addr(addr, &dev);
    if (err != ESP_OK) {
        return err;
    }
    uint8_t payload[2] = {reg, value};
    return i2c_master_transmit(
        dev,
        payload,
        sizeof(payload),
        AMOLED_I2C_TIMEOUT_MS);
}

static esp_err_t i2c_update_bits(uint8_t addr, uint8_t reg, uint8_t mask, uint8_t value)
{
    uint8_t current = 0;
    esp_err_t err = i2c_read_u8(addr, reg, &current);
    if (err != ESP_OK) {
        return err;
    }
    current = (uint8_t)((current & (uint8_t)(~mask)) | (value & mask));
    return i2c_write_u8(addr, reg, current);
}

static esp_err_t amoled_i2c_init(void)
{
    esp_err_t err = bsp_i2c_init();
    if (err != ESP_OK) {
        return err;
    }
    s_i2c_bus = bsp_i2c_get_handle();
    if (s_i2c_bus == NULL) {
        return ESP_FAIL;
    }
    return ESP_OK;
}

static pmu_probe_t axp2101_enable_minimal_rails(void)
{
    pmu_probe_t probe = {0};
    probe.status = i2c_read_u8(AXP2101_ADDR, AXP2101_CHIP_ID_REG, &probe.chip_id);
    if (probe.status != ESP_OK) {
        return probe;
    }
    probe.present = true;

    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, &probe.dc_onoff_before);
    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, &probe.ldo_onoff_before);

    if (probe.chip_id == AXP2101_EXPECTED_CHIP_ID) {
        (void)i2c_write_u8(AXP2101_ADDR, AXP2101_DC_VOL0_CTRL, AXP2101_DC1_3300MV_VALUE);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_VOL0_CTRL, 0x1F, AXP2101_ALDO1_3300MV_VALUE);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, 0x01, 0x01);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, 0x01, 0x01);
        vTaskDelay(pdMS_TO_TICKS(20));
    }

    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, &probe.dc_onoff_after);
    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, &probe.ldo_onoff_after);
    return probe;
}

static esp_err_t qmi_wait_reset(uint8_t *reset_result)
{
    esp_err_t last = ESP_FAIL;
    for (int retry = 0; retry < 50; retry++) {
        last = i2c_read_u8(QMI8658_ADDR, QMI8658_REG_RST_RESULT, reset_result);
        if (last == ESP_OK && *reset_result == QMI8658_RST_RESULT_VALUE) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return last;
}

static qmi_probe_t qmi8658_init(void)
{
    qmi_probe_t probe = {0};
    probe.status = i2c_write_u8(QMI8658_ADDR, QMI8658_REG_RESET, QMI8658_RESET_VALUE);
    if (probe.status != ESP_OK) {
        return probe;
    }

    probe.status = qmi_wait_reset(&probe.reset_result);
    (void)i2c_update_bits(
        QMI8658_ADDR,
        QMI8658_REG_CTRL1,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT);

    probe.status = i2c_read_u8(QMI8658_ADDR, QMI8658_REG_WHOAMI, &probe.whoami);
    if (probe.status != ESP_OK) {
        return probe;
    }
    probe.present = probe.whoami == QMI8658_WHOAMI_EXPECTED;
    (void)i2c_read_u8(QMI8658_ADDR, QMI8658_REG_REVISION, &probe.revision);
    if (!probe.present) {
        return probe;
    }

    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL8, QMI8658_CTRL8_CTRL9_HANDSHAKE_STATUS_INT);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL2, QMI8658_CTRL2_ACCEL_4G_1000HZ);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL3, QMI8658_CTRL3_GYRO_512DPS_224HZ);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL5, QMI8658_CTRL5_ACCEL_GYRO_LPF_MODE0);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL7, QMI8658_CTRL7_ENABLE_ACCEL_GYRO);
    vTaskDelay(pdMS_TO_TICKS(50));
    return probe;
}

static int16_t le16(const uint8_t *data)
{
    return (int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8));
}

static int32_t accel_raw_to_mg(int16_t raw)
{
    return (int32_t)((int64_t)raw * 4000 / 32768);
}

static int32_t gyro_raw_to_mdps(int16_t raw)
{
    return (int32_t)((int64_t)raw * 512000 / 32768);
}


static uint32_t next_seq(void)
{
    return s_seq++;
}

static int64_t monotonic_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static void json_flush(void)
{
    fflush(stdout);
}

static void copy_text(char *out, size_t out_size, const char *text, const char *fallback)
{
    if (out == NULL || out_size == 0) {
        return;
    }
    const char *value = (text != NULL && text[0] != '\0') ? text : fallback;
    if (value == NULL) {
        value = "";
    }
    snprintf(out, out_size, "%s", value);
}

static void json_escape_into(const char *text, char *out, size_t out_size)
{
    if (out == NULL || out_size == 0) {
        return;
    }
    if (text == NULL) {
        out[0] = '\0';
        return;
    }

    size_t index = 0;
    for (const char *cursor = text; *cursor != '\0' && index + 1 < out_size; cursor++) {
        unsigned char ch = (unsigned char)*cursor;
        if ((ch == '"' || ch == '\\') && index + 2 < out_size) {
            out[index++] = '\\';
            out[index++] = (char)ch;
        } else if (ch >= 0x20) {
            out[index++] = (char)ch;
        }
    }
    out[index] = '\0';
}

static void print_hello(void)
{
    printf(
        "{\"type\":\"hello\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"firmware\":\"%s\",\"board\":\"%s\"}\n",
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        DEMO_FIRMWARE,
        DEMO_BOARD);
    json_flush();
}

static void print_ui_event(const char *event_type, const char *response, const char *cmd_id)
{
    char escaped_cmd_id[COMMAND_ID_MAX * 2];
    json_escape_into(cmd_id == NULL ? "" : cmd_id, escaped_cmd_id, sizeof(escaped_cmd_id));

    printf(
        "{\"type\":\"%s\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"device_monotonic_ms\":%" PRId64 ","
        "\"source\":\"amoled_touch_demo\",\"response\":\"%s\","
        "\"cmd_id\":\"%s\"}\n",
        event_type,
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        monotonic_ms(),
        response,
        escaped_cmd_id);
    json_flush();
}

static void print_command_ack(const char *cmd, const char *cmd_id, const char *ack_status)
{
    char escaped_cmd[64];
    char escaped_cmd_id[COMMAND_ID_MAX * 2];
    char escaped_status[64];
    json_escape_into(cmd == NULL ? "" : cmd, escaped_cmd, sizeof(escaped_cmd));
    json_escape_into(cmd_id == NULL ? "" : cmd_id, escaped_cmd_id, sizeof(escaped_cmd_id));
    json_escape_into(ack_status == NULL ? "" : ack_status, escaped_status, sizeof(escaped_status));

    printf(
        "{\"type\":\"command_ack\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"device_monotonic_ms\":%" PRId64 ","
        "\"source\":\"amoled_touch_demo\",\"cmd\":\"%s\","
        "\"cmd_id\":\"%s\",\"ack_status\":\"%s\"}\n",
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        monotonic_ms(),
        escaped_cmd,
        escaped_cmd_id,
        escaped_status);
    json_flush();
}

static void print_command_error(const char *reason)
{
    char escaped_reason[96];
    json_escape_into(reason == NULL ? "unknown" : reason, escaped_reason, sizeof(escaped_reason));

    printf(
        "{\"type\":\"command_error\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"device_monotonic_ms\":%" PRId64 ","
        "\"source\":\"amoled_touch_demo\",\"reason\":\"%s\"}\n",
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        monotonic_ms(),
        escaped_reason);
    json_flush();
}

static void set_status(const char *text)
{
    if (s_status_label == NULL) {
        return;
    }
    lv_label_set_text(s_status_label, text);
}

static void style_wrapped_label(lv_obj_t *label, int32_t width, lv_text_align_t align)
{
    lv_obj_set_width(label, width);
    lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(label, align, 0);
}

static lv_color_t severity_accent_color(const char *severity)
{
    if (severity != NULL && strcmp(severity, "emergency") == 0) {
        return lv_color_hex(0xD64545);
    }
    if (severity != NULL && strcmp(severity, "info") == 0) {
        return lv_color_hex(0x2D7DD2);
    }
    return lv_color_hex(0xE0A336);
}

static void response_button_cb(lv_event_t *event)
{
    const char *response = (const char *)lv_event_get_user_data(event);
    if (response == NULL) {
        response = "unknown";
    }
    if (s_response_sent) {
        return;
    }
    s_response_sent = true;
    s_prompt_active = false;

    if (strcmp(response, "safe") == 0) {
        set_status("Marked safe. Event logged.");
    } else {
        set_status("Help requested. Event logged.");
    }
    print_ui_event("user_confirmation", response, s_active_cmd_id);
}

static lv_obj_t *make_button(lv_obj_t *parent, const char *label, lv_color_t color, const char *response)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_set_size(button, 170, 72);
    lv_obj_set_style_radius(button, 14, 0);
    lv_obj_set_style_bg_color(button, color, 0);
    lv_obj_add_event_cb(button, response_button_cb, LV_EVENT_CLICKED, (void *)response);

    lv_obj_t *text = lv_label_create(button);
    lv_label_set_text(text, label);
    lv_obj_center(text);
    return button;
}

static void build_safety_prompt_ui(const char *title_text, const char *prompt_text, const char *severity)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101418), 0);

    lv_obj_t *accent = lv_obj_create(screen);
    lv_obj_remove_style_all(accent);
    lv_obj_set_size(accent, 412, 8);
    lv_obj_set_style_bg_color(accent, severity_accent_color(severity), 0);
    lv_obj_align(accent, LV_ALIGN_TOP_MID, 0, 0);

    lv_obj_t *title = lv_label_create(screen);
    lv_label_set_text(title, title_text == NULL || title_text[0] == '\0' ? "Impact detected" : title_text);
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
    style_wrapped_label(title, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 36);

    lv_obj_t *question = lv_label_create(screen);
    lv_label_set_text(question, prompt_text == NULL || prompt_text[0] == '\0' ? "Are you safe?" : prompt_text);
    lv_obj_set_style_text_color(question, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(question, &lv_font_montserrat_22, 0);
    style_wrapped_label(question, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(question, LV_ALIGN_TOP_MID, 0, 92);

    lv_obj_t *safe_button = make_button(screen, "SAFE", lv_color_hex(0x1D9A5B), "safe");
    lv_obj_align(safe_button, LV_ALIGN_CENTER, -96, 28);

    lv_obj_t *help_button = make_button(screen, "HELP", lv_color_hex(0xB53737), "help");
    lv_obj_align(help_button, LV_ALIGN_CENTER, 96, 28);

    s_status_label = lv_label_create(screen);
    lv_label_set_text(s_status_label, "Tap a button to reply");
    lv_obj_set_style_text_color(s_status_label, lv_color_hex(0xB8C2CC), 0);
    style_wrapped_label(s_status_label, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(s_status_label, LV_ALIGN_BOTTOM_MID, 0, -42);
}

static void build_status_ui(const display_status_t *status)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101418), 0);

    lv_obj_t *title = lv_label_create(screen);
    lv_label_set_text(title, "Ego Link");
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 40);

    lv_obj_t *line1 = lv_label_create(screen);
    lv_label_set_text(line1, status->line1);
    lv_obj_set_style_text_color(line1, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(line1, &lv_font_montserrat_22, 0);
    style_wrapped_label(line1, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(line1, LV_ALIGN_TOP_MID, 0, 104);

    lv_obj_t *line2 = lv_label_create(screen);
    lv_label_set_text(line2, status->line2);
    lv_obj_set_style_text_color(line2, lv_color_hex(0xB8C2CC), 0);
    style_wrapped_label(line2, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(line2, LV_ALIGN_TOP_MID, 0, 150);

    lv_obj_t *line3 = lv_label_create(screen);
    lv_label_set_text(line3, status->line3);
    lv_obj_set_style_text_color(line3, lv_color_hex(0xB8C2CC), 0);
    style_wrapped_label(line3, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(line3, LV_ALIGN_TOP_MID, 0, 188);

    s_status_label = lv_label_create(screen);
    lv_label_set_text(s_status_label, status->footer);
    lv_obj_set_style_text_color(s_status_label, lv_color_hex(0x7A8794), 0);
    style_wrapped_label(s_status_label, SCREEN_TEXT_WIDTH, LV_TEXT_ALIGN_CENTER);
    lv_obj_align(s_status_label, LV_ALIGN_BOTTOM_MID, 0, -42);
}

static void build_idle_ui(void)
{
    display_status_t status = {0};
    copy_text(status.line1, sizeof(status.line1), "Waiting for PC Bridge", "");
    copy_text(status.line2, sizeof(status.line2), "D1 status not linked", "");
    copy_text(status.line3, sizeof(status.line3), "Battery: unknown", "");
    copy_text(status.footer, sizeof(status.footer), "Send ask_user or status_update", "");
    s_prompt_active = false;
    build_status_ui(&status);
}

static const cJSON *json_payload_object(const cJSON *root)
{
    const cJSON *payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    return cJSON_IsObject(payload) ? payload : NULL;
}

static bool json_string_from_object(const cJSON *object, const char *key, char *out, size_t out_size)
{
    if (!cJSON_IsObject(object) || key == NULL || out == NULL || out_size == 0) {
        return false;
    }
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, key);
    if (!cJSON_IsString(item) || item->valuestring == NULL) {
        return false;
    }
    copy_text(out, out_size, item->valuestring, "");
    return true;
}

static bool json_string_from_root_or_payload(const cJSON *root, const char *key, char *out, size_t out_size)
{
    if (json_string_from_object(root, key, out, out_size)) {
        return true;
    }
    return json_string_from_object(json_payload_object(root), key, out, out_size);
}

static bool json_number_from_object(const cJSON *object, const char *key, double *out)
{
    if (!cJSON_IsObject(object) || key == NULL || out == NULL) {
        return false;
    }
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, key);
    if (!cJSON_IsNumber(item)) {
        return false;
    }
    *out = item->valuedouble;
    return true;
}

static bool json_number_from_root_or_payload(const cJSON *root, const char *key, double *out)
{
    if (json_number_from_object(root, key, out)) {
        return true;
    }
    return json_number_from_object(json_payload_object(root), key, out);
}

static bool json_command_name(const cJSON *root, char *out, size_t out_size)
{
    if (json_string_from_object(root, "cmd", out, out_size)) {
        return true;
    }
    return json_string_from_object(root, "type", out, out_size);
}

static bool command_is_ask_user(const cJSON *root)
{
    char value[32] = {0};
    return json_command_name(root, value, sizeof(value)) && strcmp(value, "ask_user") == 0;
}

static bool command_is_status_update(const cJSON *root)
{
    char value[32] = {0};
    if (!json_command_name(root, value, sizeof(value))) {
        return false;
    }
    return strcmp(value, "status_update") == 0 || strcmp(value, "display_status") == 0;
}

static void parse_ask_user_command(const cJSON *root, ask_user_command_t *command)
{
    memset(command, 0, sizeof(*command));
    copy_text(command->title, sizeof(command->title), "Impact detected", "");
    copy_text(command->prompt, sizeof(command->prompt), "Are you safe?", "");
    copy_text(command->severity, sizeof(command->severity), "warning", "");

    (void)json_string_from_root_or_payload(root, "cmd_id", command->cmd_id, sizeof(command->cmd_id));
    (void)json_string_from_root_or_payload(root, "title", command->title, sizeof(command->title));
    if (!json_string_from_root_or_payload(root, "prompt", command->prompt, sizeof(command->prompt))) {
        (void)json_string_from_root_or_payload(root, "text", command->prompt, sizeof(command->prompt));
    }
    (void)json_string_from_root_or_payload(root, "severity", command->severity, sizeof(command->severity));
}

static void parse_status_update_command(const cJSON *root, display_status_t *status)
{
    memset(status, 0, sizeof(*status));
    (void)json_string_from_root_or_payload(root, "cmd_id", status->cmd_id, sizeof(status->cmd_id));

    char value[STATUS_TEXT_MAX] = {0};
    if (json_string_from_root_or_payload(root, "summary", value, sizeof(value))) {
        copy_text(status->line1, sizeof(status->line1), value, "D1 status update");
    } else if (json_string_from_root_or_payload(root, "lte", value, sizeof(value))) {
        snprintf(status->line1, sizeof(status->line1), "LTE: %s", value);
    } else {
        copy_text(status->line1, sizeof(status->line1), "LTE: waiting", "");
    }

    double lat = 0;
    double lon = 0;
    if (json_number_from_root_or_payload(root, "lat", &lat) && json_number_from_root_or_payload(root, "lon", &lon)) {
        snprintf(status->line2, sizeof(status->line2), "Loc: %.5f, %.5f", lat, lon);
    } else if (json_string_from_root_or_payload(root, "location", value, sizeof(value))) {
        snprintf(status->line2, sizeof(status->line2), "Loc: %s", value);
    } else if (json_string_from_root_or_payload(root, "map_mode", value, sizeof(value))) {
        snprintf(status->line2, sizeof(status->line2), "Map: %s", value);
    } else {
        copy_text(status->line2, sizeof(status->line2), "Loc: waiting", "");
    }

    double battery = 0;
    if (json_number_from_root_or_payload(root, "battery_percent", &battery)
        || json_number_from_root_or_payload(root, "battery_pct", &battery)) {
        snprintf(status->line3, sizeof(status->line3), "Battery: %.0f%%", battery);
    } else if (json_string_from_root_or_payload(root, "battery", value, sizeof(value))) {
        snprintf(status->line3, sizeof(status->line3), "Battery: %s", value);
    } else {
        copy_text(status->line3, sizeof(status->line3), "Battery: unknown", "");
    }

    if (json_string_from_root_or_payload(root, "footer", value, sizeof(value))) {
        copy_text(status->footer, sizeof(status->footer), value, "Waiting for ask_user");
    } else {
        copy_text(status->footer, sizeof(status->footer), "Waiting for ask_user", "");
    }
}

static void render_ask_user_command(const ask_user_command_t *command)
{
    copy_text(s_active_cmd_id, sizeof(s_active_cmd_id), command->cmd_id, "");
    s_response_sent = false;
    s_prompt_active = true;

    bsp_display_lock(0);
    build_safety_prompt_ui(command->title, command->prompt, command->severity);
    bsp_display_unlock();

    print_command_ack("ask_user", s_active_cmd_id, "ok");
    print_ui_event("ask_user_rendered", "pending", s_active_cmd_id);
}

static void render_status_update_command(const display_status_t *status)
{
    bsp_display_lock(0);
    if (s_prompt_active) {
        set_status(status->line1);
    } else {
        build_status_ui(status);
    }
    bsp_display_unlock();

    print_command_ack("status_update", status->cmd_id, "ok");
    print_ui_event("status_rendered", "updated", status->cmd_id);
}

static void handle_command_line(const char *line)
{
    cJSON *root = cJSON_Parse(line);
    if (root == NULL) {
        print_command_error("invalid_json");
        return;
    }

    if (command_is_ask_user(root)) {
        ask_user_command_t command = {0};
        parse_ask_user_command(root, &command);
        render_ask_user_command(&command);
    } else if (command_is_status_update(root)) {
        display_status_t status = {0};
        parse_status_update_command(root, &status);
        render_status_update_command(&status);
    } else {
        char command_name[32] = {0};
        char cmd_id[COMMAND_ID_MAX] = {0};
        (void)json_command_name(root, command_name, sizeof(command_name));
        (void)json_string_from_root_or_payload(root, "cmd_id", cmd_id, sizeof(cmd_id));
        print_command_ack(command_name, cmd_id, "ignored_unsupported");
    }
    cJSON_Delete(root);
}

static void command_reader_task(void *arg)
{
    (void)arg;
    char line[COMMAND_LINE_MAX];
    size_t length = 0;

    while (true) {
        int ch = fgetc(stdin);
        if (ch == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        if (ch == '\r') {
            continue;
        }
        if (ch == '\n') {
            line[length] = '\0';
            if (length > 0) {
                handle_command_line(line);
            }
            length = 0;
            continue;
        }
        if (length + 1 < sizeof(line)) {
            line[length] = (char)ch;
            length++;
        } else {
            length = 0;
        }
    }
}

static void imu_sampler_task(void *arg)
{
    (void)arg;
    esp_err_t err = amoled_i2c_init();
    bool qmi_present = false;
    uint8_t whoami = 0;
    if (err == ESP_OK) {
        pmu_probe_t pmu = axp2101_enable_minimal_rails();
        (void)pmu;
        qmi_probe_t qmi = qmi8658_init();
        whoami = qmi.whoami;
        qmi_present = qmi.present;
    }
    printf(
        "{\"type\":\"imu_whoami\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"device_monotonic_ms\":%" PRId64 ","
        "\"source\":\"qmi8658_demo\",\"whoami\":%d,\"present\":%s}\n",
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        monotonic_ms(),
        whoami,
        qmi_present ? "true" : "false");
    json_flush();

    int64_t last_motion_event_ms = 0;
    const int64_t cooldown_ms = 5000;

    int32_t last_ax_mg = 0;
    int32_t last_ay_mg = 0;
    int32_t last_az_mg = 0;
    bool has_last_sample = false;
    int64_t last_sample_print_ms = 0;

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(100));
        if (!qmi_present) {
            continue;
        }
        uint8_t raw[14] = {0};
        esp_err_t r_err = i2c_read(QMI8658_ADDR, QMI8658_REG_TEMPERATURE_L, raw, sizeof(raw));
        if (r_err != ESP_OK) {
            continue;
        }
        int16_t ax = le16(&raw[2]);
        int16_t ay = le16(&raw[4]);
        int16_t az = le16(&raw[6]);
        int16_t gx = le16(&raw[8]);
        int16_t gy = le16(&raw[10]);
        int16_t gz = le16(&raw[12]);
        int32_t ax_mg = accel_raw_to_mg(ax);
        int32_t ay_mg = accel_raw_to_mg(ay);
        int32_t az_mg = accel_raw_to_mg(az);
        int32_t gx_mdps = gyro_raw_to_mdps(gx);
        int32_t gy_mdps = gyro_raw_to_mdps(gy);
        int32_t gz_mdps = gyro_raw_to_mdps(gz);

        int32_t abs_ax = ax_mg < 0 ? -ax_mg : ax_mg;
        int32_t abs_ay = ay_mg < 0 ? -ay_mg : ay_mg;
        int32_t abs_az = az_mg < 0 ? -az_mg : az_mg;

        int32_t abs_gx = gx_mdps < 0 ? -gx_mdps : gx_mdps;
        int32_t abs_gy = gy_mdps < 0 ? -gy_mdps : gy_mdps;
        int32_t abs_gz = gz_mdps < 0 ? -gz_mdps : gz_mdps;

        int32_t diff_x = has_last_sample ? (ax_mg - last_ax_mg) : 0;
        int32_t diff_y = has_last_sample ? (ay_mg - last_ay_mg) : 0;
        int32_t diff_z = has_last_sample ? (az_mg - last_az_mg) : 0;

        int32_t abs_diff_x = diff_x < 0 ? -diff_x : diff_x;
        int32_t abs_diff_y = diff_y < 0 ? -diff_y : diff_y;
        int32_t abs_diff_z = diff_z < 0 ? -diff_z : diff_z;

        last_ax_mg = ax_mg;
        last_ay_mg = ay_mg;
        last_az_mg = az_mg;
        has_last_sample = true;

        int64_t now_ms = monotonic_ms();

        // Sparse 1Hz low-rate JSON imu_sample output
        if (now_ms - last_sample_print_ms >= 1000) {
            last_sample_print_ms = now_ms;
            printf(
                "{\"type\":\"imu_sample\",\"device_id\":\"%s\",\"role\":\"%s\","
                "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
                "\"device_monotonic_ms\":%" PRId64 ","
                "\"payload\":{"
                "\"accel_mg\":[%ld,%ld,%ld],"
                "\"gyro_mdps\":[%ld,%ld,%ld]"
                "}}\n",
                DEMO_DEVICE_ID,
                DEMO_ROLE,
                DEMO_PROTOCOL_VERSION,
                next_seq(),
                now_ms,
                (long)ax_mg, (long)ay_mg, (long)az_mg,
                (long)gx_mdps, (long)gy_mdps, (long)gz_mdps);
            json_flush();
        }

        bool trigger = false;
        char trigger_reason[128] = "";

        if (abs_diff_x > 300 || abs_diff_y > 300 || abs_diff_z > 300) {
            trigger = true;
            snprintf(trigger_reason, sizeof(trigger_reason), "accel_delta [dx:%ld,dy:%ld,dz:%ld]", (long)abs_diff_x, (long)abs_diff_y, (long)abs_diff_z);
        } else if (abs_gx > 50000 || abs_gy > 50000 || abs_gz > 50000) {
            trigger = true;
            snprintf(trigger_reason, sizeof(trigger_reason), "gyro_peak [gx:%ld,gy:%ld,gz:%ld]", (long)abs_gx, (long)abs_gy, (long)abs_gz);
        } else if (abs_ax > 2500 || abs_ay > 2500 || abs_az > 2500) {
            trigger = true;
            snprintf(trigger_reason, sizeof(trigger_reason), "accel_peak [ax:%ld,ay:%ld,az:%ld]", (long)abs_ax, (long)abs_ay, (long)abs_az);
        }

        if (trigger) {
            if (now_ms - last_motion_event_ms >= cooldown_ms) {
                last_motion_event_ms = now_ms;
                printf(
                    "{\"type\":\"motion_event\",\"device_id\":\"%s\",\"role\":\"%s\","
                    "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
                    "\"device_monotonic_ms\":%" PRId64 ","
                    "\"source\":\"qmi8658_demo\",\"source_status\":\"demo_unverified_heuristic\","
                    "\"sensor_kind\":\"imu\",\"sensor_model\":\"QMI8658\","
                    "\"imu_source\":\"qmi8658_i2c\",\"source_availability\":\"bridge_uplink\","
                    "\"payload\":{"
                    "\"accel_mg\":[%ld,%ld,%ld],"
                    "\"gyro_mdps\":[%ld,%ld,%ld],"
                    "\"impact_score\":0.95,"
                    "\"fall_score\":0.85,"
                    "\"trigger_reason\":\"%s\","
                    "\"accel_peak_mg\":[%ld,%ld,%ld],"
                    "\"gyro_peak_mdps\":[%ld,%ld,%ld],"
                    "\"accel_delta_mg\":[%ld,%ld,%ld],"
                    "\"demo_boundary\":\"unverified_demo_only\""
                    "}}\n",
                    DEMO_DEVICE_ID,
                    DEMO_ROLE,
                    DEMO_PROTOCOL_VERSION,
                    next_seq(),
                    now_ms,
                    (long)ax_mg, (long)ay_mg, (long)az_mg,
                    (long)gx_mdps, (long)gy_mdps, (long)gz_mdps,
                    trigger_reason,
                    (long)abs_ax, (long)abs_ay, (long)abs_az,
                    (long)abs_gx, (long)abs_gy, (long)abs_gz,
                    (long)abs_diff_x, (long)abs_diff_y, (long)abs_diff_z);
                json_flush();
            }
        }
    }
}


void app_main(void)
{
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    print_hello();

    bsp_display_start();
    bsp_display_lock(0);
    build_idle_ui();
    bsp_display_unlock();

    print_ui_event("display_ready", "waiting", "");
    xTaskCreate(command_reader_task, "command_reader", 8192, NULL, 5, NULL);
    xTaskCreate(imu_sampler_task, "imu_sampler", 4096, NULL, 4, NULL);

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
