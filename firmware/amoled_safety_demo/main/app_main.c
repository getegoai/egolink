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

#define DEMO_DEVICE_ID "wearable-node-001"
#define DEMO_ROLE "wearable_node"
#define DEMO_PROTOCOL_VERSION "0.2"
#define DEMO_FIRMWARE "egolink_amoled_safety_demo"
#define DEMO_BOARD "ESP32-S3-Touch-AMOLED-2.06"
#define COMMAND_LINE_MAX 512
#define COMMAND_ID_MAX 96

static uint32_t s_seq = 1;
static lv_obj_t *s_status_label;
static char s_active_cmd_id[COMMAND_ID_MAX];
static bool s_response_sent;

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
        cmd_id == NULL ? "" : cmd_id);
    json_flush();
}

static void print_command_ack(const char *cmd, const char *cmd_id, const char *ack_status)
{
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
        cmd,
        cmd_id == NULL ? "" : cmd_id,
        ack_status);
    json_flush();
}

static void set_status(const char *text)
{
    if (s_status_label == NULL) {
        return;
    }
    lv_label_set_text(s_status_label, text);
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

static void build_safety_prompt_ui(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101418), 0);

    lv_obj_t *title = lv_label_create(screen);
    lv_label_set_text(title, "Impact detected");
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 44);

    lv_obj_t *question = lv_label_create(screen);
    lv_label_set_text(question, "Are you safe?");
    lv_obj_set_style_text_color(question, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(question, &lv_font_montserrat_22, 0);
    lv_obj_align(question, LV_ALIGN_TOP_MID, 0, 96);

    lv_obj_t *safe_button = make_button(screen, "SAFE", lv_color_hex(0x1D9A5B), "safe");
    lv_obj_align(safe_button, LV_ALIGN_CENTER, -96, 28);

    lv_obj_t *help_button = make_button(screen, "HELP", lv_color_hex(0xB53737), "help");
    lv_obj_align(help_button, LV_ALIGN_CENTER, 96, 28);

    s_status_label = lv_label_create(screen);
    lv_label_set_text(s_status_label, "Tap a button to reply");
    lv_obj_set_style_text_color(s_status_label, lv_color_hex(0xB8C2CC), 0);
    lv_obj_align(s_status_label, LV_ALIGN_BOTTOM_MID, 0, -42);
}

static void build_idle_ui(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101418), 0);

    lv_obj_t *title = lv_label_create(screen);
    lv_label_set_text(title, "Ego Link");
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 68);

    lv_obj_t *status = lv_label_create(screen);
    lv_label_set_text(status, "Waiting for PC Bridge");
    lv_obj_set_style_text_color(status, lv_color_hex(0xB8C2CC), 0);
    lv_obj_set_style_text_font(status, &lv_font_montserrat_22, 0);
    lv_obj_align(status, LV_ALIGN_CENTER, 0, -4);

    s_status_label = lv_label_create(screen);
    lv_label_set_text(s_status_label, "Send ask_user");
    lv_obj_set_style_text_color(s_status_label, lv_color_hex(0x7A8794), 0);
    lv_obj_align(s_status_label, LV_ALIGN_BOTTOM_MID, 0, -42);
}

static bool extract_json_string(const char *line, const char *key, char *out, size_t out_size)
{
    if (line == NULL || key == NULL || out == NULL || out_size == 0) {
        return false;
    }

    char pattern[32];
    int written = snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    if (written <= 0 || written >= (int)sizeof(pattern)) {
        return false;
    }

    const char *key_pos = strstr(line, pattern);
    if (key_pos == NULL) {
        return false;
    }
    const char *colon = strchr(key_pos + strlen(pattern), ':');
    if (colon == NULL) {
        return false;
    }
    const char *quote = strchr(colon, '"');
    if (quote == NULL) {
        return false;
    }
    quote++;

    size_t index = 0;
    while (quote[index] != '\0' && quote[index] != '"' && index + 1 < out_size) {
        out[index] = quote[index];
        index++;
    }
    out[index] = '\0';
    return quote[index] == '"';
}

static bool command_is_ask_user(const char *line)
{
    char value[32] = {0};
    if (extract_json_string(line, "type", value, sizeof(value)) && strcmp(value, "ask_user") == 0) {
        return true;
    }
    if (extract_json_string(line, "cmd", value, sizeof(value)) && strcmp(value, "ask_user") == 0) {
        return true;
    }
    return false;
}

static void render_ask_user_command(const char *cmd_id)
{
    strncpy(s_active_cmd_id, cmd_id == NULL ? "" : cmd_id, sizeof(s_active_cmd_id) - 1);
    s_active_cmd_id[sizeof(s_active_cmd_id) - 1] = '\0';
    s_response_sent = false;

    bsp_display_lock(0);
    build_safety_prompt_ui();
    bsp_display_unlock();

    print_command_ack("ask_user", s_active_cmd_id, "ok");
    print_ui_event("ask_user_rendered", "pending", s_active_cmd_id);
}

static void handle_command_line(const char *line)
{
    if (!command_is_ask_user(line)) {
        return;
    }

    char cmd_id[COMMAND_ID_MAX] = {0};
    extract_json_string(line, "cmd_id", cmd_id, sizeof(cmd_id));
    render_ask_user_command(cmd_id);
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
    xTaskCreate(command_reader_task, "command_reader", 4096, NULL, 5, NULL);

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
