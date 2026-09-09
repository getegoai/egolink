#include "platform_power.h"

#include <inttypes.h>
#include <stdio.h>

#include "esp_log.h"
#include "esp_timer.h"

#if CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048
#include "freertos/FreeRTOS.h"
#include "driver/i2c.h"
#include "platform_i2c_bus.h"
#endif

#define PLATFORM_POWER_MOCK_BATTERY_PERCENT 87

static const char *TAG = "egolink_platform_power";

#if CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048

#define MAX17048_I2C_ADDR 0x36
#define MAX17048_REG_VCELL 0x02
#define MAX17048_REG_SOC 0x04
#define MAX17048_REG_VERSION 0x08
#define MAX17048_I2C_PORT ((i2c_port_t)CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_PORT)

static bool s_max17048_ready;

static esp_err_t max17048_read_u16(uint8_t reg, uint16_t *value)
{
    uint8_t raw[2] = {0, 0};
    esp_err_t err = platform_i2c_bus_lease_acquire(
        MAX17048_I2C_PORT,
        CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_TIMEOUT_MS);
    if (err != ESP_OK) {
        return err;
    }
    err = i2c_master_write_read_device(
        MAX17048_I2C_PORT,
        MAX17048_I2C_ADDR,
        &reg,
        1,
        raw,
        sizeof(raw),
        pdMS_TO_TICKS(CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_TIMEOUT_MS));
    esp_err_t release_err = platform_i2c_bus_lease_release(MAX17048_I2C_PORT);
    if (err == ESP_OK) {
        *value = ((uint16_t)raw[0] << 8) | raw[1];
    }
    return err != ESP_OK ? err : release_err;
}

static void max17048_init(void)
{
    i2c_config_t config = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SDA_GPIO,
        .scl_io_num = CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SCL_GPIO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_FREQ_HZ,
    };
    esp_err_t err = platform_i2c_bus_ensure(MAX17048_I2C_PORT, &config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "MAX17048_I2C_BUS_FAIL err=%d", (int)err);
        return;
    }
    uint16_t version = 0;
    err = max17048_read_u16(MAX17048_REG_VERSION, &version);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "MAX17048_PROBE_FAIL err=%d (check SDA/SCL Kconfig pins)", (int)err);
        return;
    }
    s_max17048_ready = true;
    ESP_LOGI(TAG, "MAX17048_PROBE_OK version=0x%04x", (unsigned)version);
}

static bool max17048_sample(int *battery_percent, int *battery_millivolt)
{
    if (!s_max17048_ready) {
        return false;
    }
    uint16_t soc_raw = 0;
    uint16_t vcell_raw = 0;
    if (max17048_read_u16(MAX17048_REG_SOC, &soc_raw) != ESP_OK) {
        return false;
    }
    if (max17048_read_u16(MAX17048_REG_VCELL, &vcell_raw) != ESP_OK) {
        return false;
    }
    int percent = (int)(soc_raw / 256U);
    if (percent < 0) {
        percent = 0;
    }
    if (percent > 100) {
        percent = 100;
    }
    *battery_percent = percent;
    /* VCELL LSB = 78.125 uV -> mv = raw * 5 / 64 */
    *battery_millivolt = (int)(((uint32_t)vcell_raw * 5U) / 64U);
    return true;
}

#endif /* CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048 */

static bool s_initialized;
static platform_power_state_t s_state = PLATFORM_POWER_STATE_BOOT;
static uint32_t s_marker_seq;
static int64_t s_state_entered_uptime_ms;
static int64_t s_state_cumulative_ms[PLATFORM_POWER_STATE_COUNT];
static char s_serial_marker_id[32] = "POWER_MARKER_000000";
static const char *s_gpio_marker_id = "disabled";
static bool s_gpio_marker_enabled;

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static const char *safe_text(const char *value)
{
    return value ? value : "";
}

static bool valid_state(platform_power_state_t state)
{
    return state >= 0 && state < PLATFORM_POWER_STATE_COUNT;
}

static int64_t elapsed_ms(int64_t now_ms)
{
    if (now_ms <= s_state_entered_uptime_ms) {
        return 0;
    }
    return now_ms - s_state_entered_uptime_ms;
}

static void refresh_serial_marker_id(void)
{
    snprintf(s_serial_marker_id, sizeof(s_serial_marker_id), "POWER_MARKER_%06" PRIu32, s_marker_seq);
}

static void credit_current_state(int64_t now_ms)
{
    if (valid_state(s_state)) {
        s_state_cumulative_ms[s_state] += elapsed_ms(now_ms);
    }
    s_state_entered_uptime_ms = now_ms;
}

static int64_t state_total_ms(platform_power_state_t state, int64_t now_ms)
{
    if (!valid_state(state)) {
        return 0;
    }
    int64_t total_ms = s_state_cumulative_ms[state];
    if (state == s_state) {
        total_ms += elapsed_ms(now_ms);
    }
    return total_ms;
}

static void log_structured_event(
    platform_power_event_kind_t kind,
    platform_power_state_t state,
    platform_power_state_t previous_state,
    int64_t uptime,
    int64_t duration,
    const char *detail)
{
    ESP_LOGI(
        TAG,
        "PLATFORM_POWER_EVENT kind=%s seq=%" PRIu32 " state=%s previous_state=%s uptime_ms=%" PRId64
        " duration_ms=%" PRId64 " state_total_ms=%" PRId64
        " serial_marker_id=%s gpio_marker_id=%s gpio_marker_enabled=%s mock=true detail=%s",
        platform_power_event_kind_name(kind),
        s_marker_seq,
        platform_power_state_name(state),
        platform_power_state_name(previous_state),
        uptime,
        duration,
        state_total_ms(state, uptime),
        s_serial_marker_id,
        s_gpio_marker_id,
        s_gpio_marker_enabled ? "true" : "false",
        safe_text(detail));
}

bool platform_power_init(void)
{
    if (!s_initialized) {
        s_state = PLATFORM_POWER_STATE_BOOT;
        s_marker_seq = 0;
        s_state_entered_uptime_ms = uptime_ms();
        for (int state = 0; state < PLATFORM_POWER_STATE_COUNT; ++state) {
            s_state_cumulative_ms[state] = 0;
        }
        s_gpio_marker_enabled = false;
        refresh_serial_marker_id();
        s_initialized = true;
#if CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048
        max17048_init();
        ESP_LOGI(
            TAG,
            "PLATFORM_POWER_INIT backend=max17048 ready=%s charging_detection=mock state=%s",
            s_max17048_ready ? "true" : "false",
            platform_power_state_name(s_state));
#else
        ESP_LOGI(
            TAG,
            "PLATFORM_POWER_INIT mock=true battery_percent=%d charging=false state=%s",
            PLATFORM_POWER_MOCK_BATTERY_PERCENT,
            platform_power_state_name(s_state));
#endif
        log_structured_event(
            PLATFORM_POWER_EVENT_INIT,
            s_state,
            s_state,
            s_state_entered_uptime_ms,
            0,
            "platform_power_init");
    }
    return true;
}

void platform_power_enter_state(platform_power_state_t state, const char *reason)
{
    if (!s_initialized) {
        platform_power_init();
    }
    if (!valid_state(state)) {
        ESP_LOGW(TAG, "PLATFORM_POWER_ENTER_INVALID state=%d reason=%s", (int)state, safe_text(reason));
        return;
    }
    platform_power_state_t previous_state = s_state;
    int64_t now_ms = uptime_ms();
    int64_t previous_duration_ms = elapsed_ms(now_ms);
    credit_current_state(now_ms);
    s_state = state;
    s_state_entered_uptime_ms = now_ms;
    s_marker_seq++;
    refresh_serial_marker_id();
    ESP_LOGI(
        TAG,
        "PLATFORM_POWER_ENTER seq=%" PRIu32 " state=%s reason=%s mock=true",
        s_marker_seq,
        platform_power_state_name(state),
        safe_text(reason));
    log_structured_event(
        PLATFORM_POWER_EVENT_ENTER,
        state,
        previous_state,
        now_ms,
        previous_duration_ms,
        reason);
}

void platform_power_leave_state(platform_power_state_t state, const char *reason)
{
    if (!s_initialized) {
        platform_power_init();
    }
    int64_t now_ms = uptime_ms();
    int64_t duration_ms = (state == s_state) ? elapsed_ms(now_ms) : 0;
    if (state == s_state) {
        credit_current_state(now_ms);
    }
    s_marker_seq++;
    refresh_serial_marker_id();
    ESP_LOGI(
        TAG,
        "PLATFORM_POWER_LEAVE seq=%" PRIu32 " state=%s duration_ms=%" PRId64 " reason=%s mock=true",
        s_marker_seq,
        platform_power_state_name(state),
        duration_ms,
        safe_text(reason));
    log_structured_event(
        PLATFORM_POWER_EVENT_LEAVE,
        state,
        s_state,
        now_ms,
        duration_ms,
        reason);
}

void platform_power_mark(const char *marker, const char *detail)
{
    if (!s_initialized) {
        platform_power_init();
    }
    int64_t now_ms = uptime_ms();
    int64_t current_duration_ms = elapsed_ms(now_ms);
    s_marker_seq++;
    refresh_serial_marker_id();
    ESP_LOGI(
        TAG,
        "PLATFORM_POWER_MARK seq=%" PRIu32 " marker=%s detail=%s state=%s serial_marker_id=%s gpio_marker_id=%s mock=true",
        s_marker_seq,
        safe_text(marker),
        safe_text(detail),
        platform_power_state_name(s_state),
        s_serial_marker_id,
        s_gpio_marker_id);
    log_structured_event(
        PLATFORM_POWER_EVENT_MARK,
        s_state,
        s_state,
        now_ms,
        current_duration_ms,
        marker);
}

void platform_power_get_snapshot(platform_power_snapshot_t *snapshot)
{
    if (!snapshot) {
        return;
    }
    if (!s_initialized) {
        platform_power_init();
    }
    int64_t now_ms = uptime_ms();
    int battery_percent = PLATFORM_POWER_MOCK_BATTERY_PERCENT;
    int battery_millivolt = 0;
    bool battery_voltage_valid = false;
    bool battery_is_mock = true;
    const char *battery_source = "mock";
#if CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048
    if (max17048_sample(&battery_percent, &battery_millivolt)) {
        battery_voltage_valid = true;
        battery_is_mock = false;
        battery_source = "max17048_i2c";
    } else {
        /* Explainable fallback: keep mock values and say why. */
        battery_percent = PLATFORM_POWER_MOCK_BATTERY_PERCENT;
        battery_source = "max17048_read_failed";
    }
#endif
    *snapshot = (platform_power_snapshot_t){
        .battery_percent = battery_percent,
        .battery_millivolt = battery_millivolt,
        .battery_voltage_valid = battery_voltage_valid,
        .charging = false,
        .battery_is_mock = battery_is_mock,
        .charging_is_mock = true,
        .battery_source = battery_source,
        .charging_source = "mock",
        .state = s_state,
        .marker_seq = s_marker_seq,
        .state_entered_uptime_ms = s_state_entered_uptime_ms,
        .state_elapsed_ms = elapsed_ms(now_ms),
        .state_cumulative_ms = state_total_ms(s_state, now_ms),
        .marker = {
            .seq = s_marker_seq,
            .serial_marker_id = s_serial_marker_id,
            .gpio_marker_id = s_gpio_marker_id,
            .gpio_marker_enabled = s_gpio_marker_enabled,
        },
    };
}

const char *platform_power_state_name(platform_power_state_t state)
{
    switch (state) {
    case PLATFORM_POWER_STATE_BOOT:
        return "BOOT";
    case PLATFORM_POWER_STATE_ACTIVE:
        return "ACTIVE";
    case PLATFORM_POWER_STATE_GUARDING:
        return "GUARDING";
    case PLATFORM_POWER_STATE_LIGHT_SLEEP:
        return "LIGHT_SLEEP";
    case PLATFORM_POWER_STATE_DEEP_SLEEP:
        return "DEEP_SLEEP";
    case PLATFORM_POWER_STATE_NETWORK_ATTACH:
        return "NETWORK_ATTACH";
    case PLATFORM_POWER_STATE_GNSS_FIX:
        return "GNSS_FIX";
    case PLATFORM_POWER_STATE_CAPTURE_AUDIO:
        return "CAPTURE_AUDIO";
    case PLATFORM_POWER_STATE_CAPTURE_IMAGE:
        return "CAPTURE_IMAGE";
    case PLATFORM_POWER_STATE_STORAGE_WRITE:
        return "STORAGE_WRITE";
    case PLATFORM_POWER_STATE_UPLOAD:
        return "UPLOAD";
    case PLATFORM_POWER_STATE_EMERGENCY:
        return "EMERGENCY";
    case PLATFORM_POWER_STATE_COUNT:
        return "COUNT";
    default:
        return "UNKNOWN";
    }
}

const char *platform_power_event_kind_name(platform_power_event_kind_t kind)
{
    switch (kind) {
    case PLATFORM_POWER_EVENT_INIT:
        return "INIT";
    case PLATFORM_POWER_EVENT_ENTER:
        return "ENTER";
    case PLATFORM_POWER_EVENT_LEAVE:
        return "LEAVE";
    case PLATFORM_POWER_EVENT_MARK:
        return "MARK";
    default:
        return "UNKNOWN";
    }
}
