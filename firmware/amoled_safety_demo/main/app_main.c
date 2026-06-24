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

static uint32_t s_seq = 1;
static lv_obj_t *s_status_label;

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

static void print_ui_event(const char *event_type, const char *response)
{
    printf(
        "{\"type\":\"%s\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"device_monotonic_ms\":%" PRId64 ","
        "\"source\":\"amoled_touch_demo\",\"response\":\"%s\"}\n",
        event_type,
        DEMO_DEVICE_ID,
        DEMO_ROLE,
        DEMO_PROTOCOL_VERSION,
        next_seq(),
        monotonic_ms(),
        response);
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

    if (strcmp(response, "safe") == 0) {
        set_status("Marked safe. Event logged.");
    } else {
        set_status("Help requested. Event logged.");
    }
    print_ui_event("user_confirmation", response);
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

void app_main(void)
{
    print_hello();

    bsp_display_start();
    bsp_display_lock(0);
    build_safety_prompt_ui();
    bsp_display_unlock();

    print_ui_event("ask_user_rendered", "pending");

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
