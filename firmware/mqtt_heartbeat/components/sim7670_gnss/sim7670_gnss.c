#include "sim7670_gnss.h"

#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define KNOT_TO_MPS 0.514444
#define AT_RESPONSE_BUFFER_SIZE 512
#define AT_READ_CHUNK_SIZE 96

#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
static const char *TAG = "sim7670_gnss";

static bool s_initialized;
static SemaphoreHandle_t s_uart_mutex;

static uart_port_t configured_uart_num(void)
{
    return (uart_port_t)CONFIG_EGOLINK_SIM7670_UART_NUM;
}
#endif

void sim7670_gnss_report_init(sim7670_gnss_report_t *report)
{
    if (report == NULL) {
        return;
    }
    memset(report, 0, sizeof(*report));
    report->driver_enabled = false;
    report->uart_ready = false;
    report->at_ok = false;
    report->fix = false;
    snprintf(report->gnss_state, sizeof(report->gnss_state), "%s", "driver_disabled");
    snprintf(report->source_status, sizeof(report->source_status), "%s", "unverified");
}

const char *sim7670_gnss_backend_name(void)
{
#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    return "sim7670g_uart_at";
#else
    return "disabled";
#endif
}

#if CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
esp_err_t sim7670_gnss_init(void)
{
    if (s_initialized) {
        return ESP_OK;
    }
    if (s_uart_mutex == NULL) {
        s_uart_mutex = xSemaphoreCreateMutex();
        if (s_uart_mutex == NULL) {
            return ESP_ERR_NO_MEM;
        }
    }

    uart_config_t uart_config = {
        .baud_rate = CONFIG_EGOLINK_SIM7670_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_port_t uart_num = configured_uart_num();
    esp_err_t err = uart_driver_install(uart_num, AT_RESPONSE_BUFFER_SIZE * 2, 0, 0, NULL, 0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "SIM7670_UART_DRIVER_INSTALL_FAIL err=%s", esp_err_to_name(err));
        return err;
    }
    ESP_RETURN_ON_ERROR(uart_param_config(uart_num, &uart_config), TAG, "uart_param_config failed");
    ESP_RETURN_ON_ERROR(
        uart_set_pin(
            uart_num,
            CONFIG_EGOLINK_SIM7670_UART_TX_GPIO,
            CONFIG_EGOLINK_SIM7670_UART_RX_GPIO,
            UART_PIN_NO_CHANGE,
            UART_PIN_NO_CHANGE),
        TAG,
        "uart_set_pin failed");
    uart_flush_input(uart_num);
    s_initialized = true;
    ESP_LOGI(
        TAG,
        "SIM7670_GNSS_UART_READY uart=%d tx_gpio=%d rx_gpio=%d baud=%d",
        (int)uart_num,
        CONFIG_EGOLINK_SIM7670_UART_TX_GPIO,
        CONFIG_EGOLINK_SIM7670_UART_RX_GPIO,
        CONFIG_EGOLINK_SIM7670_UART_BAUD);
    return ESP_OK;
}

static void set_status(sim7670_gnss_report_t *report, const char *state, const char *source_status)
{
    if (report == NULL) {
        return;
    }
    snprintf(report->gnss_state, sizeof(report->gnss_state), "%s", state ? state : "unknown");
    snprintf(report->source_status, sizeof(report->source_status), "%s", source_status ? source_status : "unverified");
}

static void trim(char *text)
{
    if (text == NULL) {
        return;
    }
    char *start = text;
    while (*start && isspace((unsigned char)*start)) {
        start++;
    }
    if (start != text) {
        memmove(text, start, strlen(start) + 1);
    }
    size_t len = strlen(text);
    while (len > 0 && isspace((unsigned char)text[len - 1])) {
        text[--len] = '\0';
    }
}

static const char *field_at(const char *line, const char *prefix, int index, char *buffer, size_t buffer_size)
{
    if (line == NULL || prefix == NULL || buffer == NULL || buffer_size == 0) {
        return "";
    }
    buffer[0] = '\0';
    const char *payload = strstr(line, prefix);
    if (payload == NULL) {
        return "";
    }
    payload += strlen(prefix);
    while (*payload == ' ') {
        payload++;
    }

    int current = 0;
    const char *start = payload;
    for (const char *p = payload;; ++p) {
        if (*p == ',' || *p == '\r' || *p == '\n' || *p == '\0') {
            if (current == index) {
                size_t len = (size_t)(p - start);
                if (len >= buffer_size) {
                    len = buffer_size - 1;
                }
                memcpy(buffer, start, len);
                buffer[len] = '\0';
                trim(buffer);
                return buffer;
            }
            if (*p == '\0' || *p == '\r' || *p == '\n') {
                return "";
            }
            current++;
            start = p + 1;
        }
    }
}

static bool parse_double_field(const char *text, double *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL) {
        return false;
    }
    char *end = NULL;
    double parsed = strtod(text, &end);
    if (end == text) {
        return false;
    }
    *value = parsed;
    return true;
}

static bool parse_int_field(const char *text, int *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL) {
        return false;
    }
    char *end = NULL;
    long parsed = strtol(text, &end, 10);
    if (end == text) {
        return false;
    }
    *value = (int)parsed;
    return true;
}

static bool parse_coordinate(const char *raw, const char *hemisphere, bool is_lat, double *out)
{
    double ddmm = 0.0;
    if (!parse_double_field(raw, &ddmm) || out == NULL) {
        return false;
    }
    int degrees = (int)(ddmm / 100.0);
    double minutes = ddmm - ((double)degrees * 100.0);
    double decimal = (double)degrees + minutes / 60.0;
    if (hemisphere != NULL && (hemisphere[0] == 'S' || hemisphere[0] == 'W')) {
        decimal = -decimal;
    }
    if ((is_lat && fabs(decimal) > 90.0) || (!is_lat && fabs(decimal) > 180.0)) {
        return false;
    }
    *out = decimal;
    return true;
}

static void copy_truncated(char *target, size_t target_size, const char *source)
{
    if (target == NULL || target_size == 0) {
        return;
    }
    snprintf(target, target_size, "%s", source ? source : "");
}

static bool contains_token(const char *text, const char *token)
{
    return text != NULL && token != NULL && strstr(text, token) != NULL;
}

static bool sim7670_send_at(
    const char *command,
    const char *expect,
    uint32_t timeout_ms,
    char *response,
    size_t response_size)
{
    if (command == NULL || response == NULL || response_size == 0) {
        return false;
    }
    response[0] = '\0';
    if (sim7670_gnss_init() != ESP_OK) {
        return false;
    }

    uart_port_t uart_num = configured_uart_num();
    if (xSemaphoreTake(s_uart_mutex, pdMS_TO_TICKS(timeout_ms + 500)) != pdTRUE) {
        return false;
    }
    uart_flush_input(uart_num);
    uart_write_bytes(uart_num, command, strlen(command));
    uart_write_bytes(uart_num, "\r\n", 2);

    uint8_t chunk[AT_READ_CHUNK_SIZE];
    size_t length = 0;
    bool matched = false;
    bool saw_error = false;
    int64_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    while ((int64_t)xTaskGetTickCount() < deadline) {
        int read = uart_read_bytes(uart_num, chunk, sizeof(chunk), pdMS_TO_TICKS(100));
        if (read > 0) {
            size_t available = response_size - 1 - length;
            size_t copy = (size_t)read < available ? (size_t)read : available;
            if (copy > 0) {
                memcpy(response + length, chunk, copy);
                length += copy;
                response[length] = '\0';
            }
            saw_error = contains_token(response, "ERROR");
            if ((expect != NULL && expect[0] != '\0' && contains_token(response, expect)) || saw_error) {
                matched = true;
                break;
            }
        }
    }
    xSemaphoreGive(s_uart_mutex);
    ESP_LOGI(TAG, "SIM7670_AT command=%s matched=%s", command, matched ? "true" : "false");
    return !saw_error && (matched || (expect == NULL || expect[0] == '\0'));
}

static bool parse_cgpsinfo(const char *line, sim7670_gnss_report_t *report)
{
    char lat_raw[24];
    char ns[4];
    char lon_raw[24];
    char ew[4];
    char field[24];
    double value = 0.0;
    bool lat_ok = parse_coordinate(field_at(line, "+CGPSINFO:", 0, lat_raw, sizeof(lat_raw)), field_at(line, "+CGPSINFO:", 1, ns, sizeof(ns)), true, &report->lat);
    bool lon_ok = parse_coordinate(field_at(line, "+CGPSINFO:", 2, lon_raw, sizeof(lon_raw)), field_at(line, "+CGPSINFO:", 3, ew, sizeof(ew)), false, &report->lon);
    report->lat_valid = lat_ok;
    report->lon_valid = lon_ok;
    if (parse_double_field(field_at(line, "+CGPSINFO:", 6, field, sizeof(field)), &value)) {
        report->altitude_m = value;
        report->altitude_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGPSINFO:", 7, field, sizeof(field)), &value)) {
        report->speed_mps = value * KNOT_TO_MPS;
        report->speed_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGPSINFO:", 8, field, sizeof(field)), &value)) {
        report->course_deg = value;
        report->course_valid = true;
    }
    copy_truncated(report->utc_date, sizeof(report->utc_date), field_at(line, "+CGPSINFO:", 4, field, sizeof(field)));
    copy_truncated(report->utc_time, sizeof(report->utc_time), field_at(line, "+CGPSINFO:", 5, field, sizeof(field)));
    return lat_ok && lon_ok;
}

static bool cgnss_coordinate_candidate(
    const char *line,
    int lat_index,
    int ns_index,
    int lon_index,
    int ew_index,
    double *lat,
    double *lon)
{
    char lat_raw[24];
    char ns[4];
    char lon_raw[24];
    char ew[4];
    return parse_coordinate(field_at(line, "+CGNSSINFO:", lat_index, lat_raw, sizeof(lat_raw)), field_at(line, "+CGNSSINFO:", ns_index, ns, sizeof(ns)), true, lat) &&
           parse_coordinate(field_at(line, "+CGNSSINFO:", lon_index, lon_raw, sizeof(lon_raw)), field_at(line, "+CGNSSINFO:", ew_index, ew, sizeof(ew)), false, lon);
}

static bool parse_cgnssinfo(const char *line, sim7670_gnss_report_t *report)
{
    char field[24];
    double value = 0.0;
    int int_value = 0;
    double lat = 0.0;
    double lon = 0.0;
    bool fix = cgnss_coordinate_candidate(line, 5, 6, 7, 8, &lat, &lon) ||
               cgnss_coordinate_candidate(line, 4, 5, 6, 7, &lat, &lon);
    if (fix) {
        report->lat = lat;
        report->lon = lon;
        report->lat_valid = true;
        report->lon_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 11, field, sizeof(field)), &value)) {
        report->altitude_m = value;
        report->altitude_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 12, field, sizeof(field)), &value)) {
        report->speed_mps = value * KNOT_TO_MPS;
        report->speed_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 13, field, sizeof(field)), &value)) {
        report->course_deg = value;
        report->course_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 14, field, sizeof(field)), &value)) {
        report->pdop = value;
        report->pdop_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 15, field, sizeof(field)), &value)) {
        report->hdop = value;
        report->hdop_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", 16, field, sizeof(field)), &value)) {
        report->vdop = value;
        report->vdop_valid = true;
    }
    if (parse_int_field(field_at(line, "+CGNSSINFO:", 17, field, sizeof(field)), &int_value)) {
        report->satellites = int_value;
        report->satellites_valid = true;
    }
    copy_truncated(report->utc_date, sizeof(report->utc_date), field_at(line, "+CGNSSINFO:", 9, field, sizeof(field)));
    copy_truncated(report->utc_time, sizeof(report->utc_time), field_at(line, "+CGNSSINFO:", 10, field, sizeof(field)));
    return fix;
}

static const char *find_line(const char *response, const char *prefix)
{
    return response == NULL ? NULL : strstr(response, prefix);
}

static bool parse_best_fix(const char *command, const char *response, sim7670_gnss_report_t *report)
{
    const char *line = find_line(response, "+CGNSSINFO:");
    if (line != NULL) {
        copy_truncated(report->raw_command, sizeof(report->raw_command), command);
        copy_truncated(report->raw_response, sizeof(report->raw_response), line);
        return parse_cgnssinfo(line, report);
    }
    line = find_line(response, "+CGPSINFO:");
    if (line != NULL) {
        copy_truncated(report->raw_command, sizeof(report->raw_command), command);
        copy_truncated(report->raw_response, sizeof(report->raw_response), line);
        return parse_cgpsinfo(line, report);
    }
    copy_truncated(report->raw_command, sizeof(report->raw_command), command);
    copy_truncated(report->raw_response, sizeof(report->raw_response), response);
    return false;
}

bool sim7670_gnss_request_location(sim7670_gnss_report_t *report)
{
    if (report == NULL) {
        return false;
    }
    sim7670_gnss_report_init(report);
    report->driver_enabled = true;
    if (sim7670_gnss_init() != ESP_OK) {
        set_status(report, "uart_init_failed", "unverified");
        return false;
    }
    report->uart_ready = true;

    char response[AT_RESPONSE_BUFFER_SIZE];
    if (!sim7670_send_at("AT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        copy_truncated(report->raw_command, sizeof(report->raw_command), "AT");
        copy_truncated(report->raw_response, sizeof(report->raw_response), response);
        set_status(report, "at_unreachable", "unverified");
        return false;
    }
    report->at_ok = true;

#if CONFIG_EGOLINK_SIM7670_GNSS_POWER_ON_BEFORE_QUERY
    (void)sim7670_send_at("AT+CGNSSPWR=1", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
#endif

    bool got_gnss_line = sim7670_send_at("AT+CGNSSINFO", "+CGNSSINFO:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
    bool fix = false;
    if (got_gnss_line) {
        fix = parse_best_fix("AT+CGNSSINFO", response, report);
    }
    if (!fix) {
        bool got_gps_line = sim7670_send_at("AT+CGPSINFO", "+CGPSINFO:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        if (got_gps_line) {
            bool gps_fix = parse_best_fix("AT+CGPSINFO", response, report);
            fix = gps_fix;
        }
    }

    report->fix = fix && report->lat_valid && report->lon_valid;
    set_status(report, report->fix ? "fix" : "no_fix", report->fix ? "observed" : "unverified");
    return true;
}
#else
esp_err_t sim7670_gnss_init(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

bool sim7670_gnss_request_location(sim7670_gnss_report_t *report)
{
    sim7670_gnss_report_init(report);
    return false;
}
#endif
