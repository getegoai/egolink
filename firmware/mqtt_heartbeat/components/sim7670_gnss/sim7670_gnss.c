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
#define AT_RESPONSE_BUFFER_SIZE 1536
#define AT_READ_CHUNK_SIZE 96
#define SIM7670_AT_BACKEND_ENABLED \
    (CONFIG_EGOLINK_SIM7670_GNSS_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED)
#define SIM7670_LTE_HTTP_ENABLED \
    (CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED)

#if SIM7670_AT_BACKEND_ENABLED
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

void sim7670_lte_report_init(sim7670_lte_report_t *report)
{
    if (report == NULL) {
        return;
    }
    memset(report, 0, sizeof(*report));
    report->driver_enabled = false;
    report->uart_ready = false;
    report->at_ok = false;
    snprintf(report->sim_state, sizeof(report->sim_state), "%s", "driver_disabled");
    snprintf(report->registration_state, sizeof(report->registration_state), "%s", "unknown");
    snprintf(report->pdp_state, sizeof(report->pdp_state), "%s", "unknown");
    snprintf(report->apn_state, sizeof(report->apn_state), "%s", "unknown");
    snprintf(report->reason_code, sizeof(report->reason_code), "%s", "LTE_STATUS_DISABLED");
}

const char *sim7670_lte_backend_name(void)
{
#if CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
    return "sim7670g_uart_at";
#else
    return "disabled";
#endif
}

void sim7670_lte_http_probe_result_init(sim7670_lte_http_probe_result_t *result)
{
    if (result == NULL) {
        return;
    }
    memset(result, 0, sizeof(*result));
    result->driver_enabled = false;
    result->uart_ready = false;
    result->at_ok = false;
    snprintf(result->reason_code, sizeof(result->reason_code), "%s", "LTE_HTTP_DISABLED");
}

const char *sim7670_lte_http_backend_name(void)
{
#if SIM7670_LTE_HTTP_ENABLED
    return "sim7670g_uart_at_http";
#else
    return "disabled";
#endif
}

#if SIM7670_AT_BACKEND_ENABLED
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

static const char *find_line(const char *response, const char *prefix);

static bool sim7670_send_at_labeled(
    const char *command,
    const char *log_label,
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
    ESP_LOGI(TAG, "SIM7670_AT command=%s matched=%s", log_label ? log_label : command, matched ? "true" : "false");
    return !saw_error && (matched || (expect == NULL || expect[0] == '\0'));
}

static bool sim7670_send_at(
    const char *command,
    const char *expect,
    uint32_t timeout_ms,
    char *response,
    size_t response_size)
{
    return sim7670_send_at_labeled(command, command, expect, timeout_ms, response, response_size);
}

static void append_at_response(char *response, size_t response_size, size_t *length, const uint8_t *chunk, size_t chunk_len)
{
    if (response == NULL || response_size == 0 || length == NULL || chunk == NULL || chunk_len == 0) {
        return;
    }
    size_t available = response_size - 1 - *length;
    size_t copy = chunk_len < available ? chunk_len : available;
    if (copy > 0) {
        memcpy(response + *length, chunk, copy);
        *length += copy;
        response[*length] = '\0';
    }
}

static bool sim7670_send_http_data(
    const char *command,
    const char *payload,
    uint32_t timeout_ms,
    char *response,
    size_t response_size)
{
    if (command == NULL || payload == NULL || response == NULL || response_size == 0) {
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
    bool saw_download = false;
    bool saw_error = false;
    int64_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    while ((int64_t)xTaskGetTickCount() < deadline) {
        int read = uart_read_bytes(uart_num, chunk, sizeof(chunk), pdMS_TO_TICKS(100));
        if (read > 0) {
            append_at_response(response, response_size, &length, chunk, (size_t)read);
            saw_error = contains_token(response, "ERROR");
            if (contains_token(response, "DOWNLOAD") || saw_error) {
                saw_download = !saw_error;
                break;
            }
        }
    }

    bool saw_ok = false;
    if (saw_download) {
        uart_write_bytes(uart_num, payload, strlen(payload));
        deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
        while ((int64_t)xTaskGetTickCount() < deadline) {
            int read = uart_read_bytes(uart_num, chunk, sizeof(chunk), pdMS_TO_TICKS(100));
            if (read > 0) {
                append_at_response(response, response_size, &length, chunk, (size_t)read);
                saw_error = contains_token(response, "ERROR");
                if (contains_token(response, "OK") || saw_error) {
                    saw_ok = !saw_error;
                    break;
                }
            }
        }
    }
    xSemaphoreGive(s_uart_mutex);
    ESP_LOGI(TAG, "SIM7670_AT command=AT+HTTPDATA matched=%s", saw_ok ? "true" : "false");
    return saw_download && saw_ok;
}

static bool parse_httpaction(const char *response, int *status_code, int *data_len)
{
    const char *line = find_line(response, "+HTTPACTION:");
    char field[SIM7670_LTE_STATUS_MAX];
    int parsed_status = 0;
    int parsed_len = 0;
    if (line == NULL) {
        return false;
    }
    bool status_ok = parse_int_field(field_at(line, "+HTTPACTION:", 1, field, sizeof(field)), &parsed_status);
    bool len_ok = parse_int_field(field_at(line, "+HTTPACTION:", 2, field, sizeof(field)), &parsed_len);
    if (status_ok && status_code != NULL) {
        *status_code = parsed_status;
    }
    if (len_ok && data_len != NULL) {
        *data_len = parsed_len;
    }
    return status_ok;
}

static bool copy_httpread_json_body(const char *response, char *body, size_t body_size)
{
    if (response == NULL || body == NULL || body_size == 0) {
        return false;
    }
    body[0] = '\0';
    const char *start = strchr(response, '{');
    const char *end = strrchr(response, '}');
    if (start == NULL || end == NULL || end < start) {
        return false;
    }
    size_t length = (size_t)(end - start + 1);
    if (length >= body_size) {
        length = body_size - 1;
    }
    memcpy(body, start, length);
    body[length] = '\0';
    return length > 0;
}

static void update_lte_http_raw(sim7670_lte_http_probe_result_t *result, const char *command, const char *response);

static bool sim7670_send_httpread_json_labeled(
    const char *command,
    const char *log_label,
    uint32_t timeout_ms,
    char *response,
    size_t response_size,
    char *response_body,
    size_t response_body_size)
{
    if (command == NULL || response == NULL || response_size == 0) {
        return false;
    }
    response[0] = '\0';
    if (response_body != NULL && response_body_size > 0) {
        response_body[0] = '\0';
    }
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
    bool body_ok = false;
    bool saw_error = false;
    bool saw_httpread = false;
    bool saw_ok = false;
    TickType_t last_read_tick = xTaskGetTickCount();
    int64_t deadline = (int64_t)xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    while ((int64_t)xTaskGetTickCount() < deadline) {
        int read = uart_read_bytes(uart_num, chunk, sizeof(chunk), pdMS_TO_TICKS(100));
        if (read > 0) {
            append_at_response(response, response_size, &length, chunk, (size_t)read);
            last_read_tick = xTaskGetTickCount();
            saw_error = contains_token(response, "ERROR");
            saw_httpread = contains_token(response, "+HTTPREAD");
            saw_ok = contains_token(response, "OK");
            body_ok = copy_httpread_json_body(response, response_body, response_body_size);
            if (saw_error || body_ok) {
                break;
            }
        } else if ((saw_httpread || saw_ok) &&
                   (xTaskGetTickCount() - last_read_tick) >= pdMS_TO_TICKS(1200)) {
            break;
        }
    }
    xSemaphoreGive(s_uart_mutex);
    ESP_LOGI(
        TAG,
        "SIM7670_AT_HTTPREAD command=%s body_ok=%s saw_httpread=%s saw_ok=%s",
        log_label ? log_label : command,
        body_ok ? "true" : "false",
        saw_httpread ? "true" : "false",
        saw_ok ? "true" : "false");
    return !saw_error && (body_ok || saw_httpread || saw_ok);
}

static bool sim7670_lte_http_read_json_body(
    int data_len,
    char *response,
    size_t response_size,
    char *response_body,
    size_t response_body_size,
    sim7670_lte_http_probe_result_t *result,
    bool *saw_error)
{
    if (saw_error != NULL) {
        *saw_error = false;
    }
    if (data_len <= 0 || response == NULL || response_size == 0) {
        return false;
    }

    char command[48];
    int written = snprintf(command, sizeof(command), "AT+HTTPREAD=0,%d", data_len);
    if (written > 0 && (size_t)written < sizeof(command)) {
        if (sim7670_send_httpread_json_labeled(
                command,
                "AT+HTTPREAD=0,<len>",
                CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
                response,
                response_size,
                response_body,
                response_body_size)) {
            result->http_read_ok = true;
            update_lte_http_raw(result, "AT+HTTPREAD=0,<len>", response);
            if (response_body != NULL && response_body[0] != '\0') {
                return true;
            }
        }
        update_lte_http_raw(result, "AT+HTTPREAD=0,<len>", response);
        if (saw_error != NULL && contains_token(response, "ERROR")) {
            *saw_error = true;
        }
    }

    if (sim7670_send_httpread_json_labeled(
            "AT+HTTPREAD",
            "AT+HTTPREAD",
            CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
            response,
            response_size,
            response_body,
            response_body_size)) {
        result->http_read_ok = true;
        update_lte_http_raw(result, "AT+HTTPREAD", response);
        return response_body != NULL && response_body[0] != '\0';
    }
    update_lte_http_raw(result, "AT+HTTPREAD", response);
    if (saw_error != NULL && contains_token(response, "ERROR")) {
        *saw_error = true;
    }
    return false;
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

static void strip_quotes(char *text)
{
    if (text == NULL) {
        return;
    }
    trim(text);
    size_t len = strlen(text);
    if (len >= 2 && text[0] == '"' && text[len - 1] == '"') {
        memmove(text, text + 1, len - 2);
        text[len - 2] = '\0';
        trim(text);
    }
}

static const char *registration_state_from_stat(const char *stat)
{
    if (stat == NULL || stat[0] == '\0') {
        return "unknown";
    }
    switch (stat[0]) {
    case '0':
        return "not_registered";
    case '1':
        return "registered_home";
    case '2':
        return "searching";
    case '3':
        return "registration_denied";
    case '4':
        return "unknown";
    case '5':
        return "registered_roaming";
    default:
        return "unknown";
    }
}

static const char *rat_from_cops_act(const char *act)
{
    if (act == NULL || act[0] == '\0') {
        return "";
    }
    if (strcmp(act, "0") == 0 || strcmp(act, "1") == 0 || strcmp(act, "3") == 0) {
        return "GSM";
    }
    if (strcmp(act, "7") == 0 || strcmp(act, "9") == 0) {
        return "LTE";
    }
    return act;
}

static void set_lte_reason(sim7670_lte_report_t *report, const char *reason)
{
    if (report == NULL) {
        return;
    }
    copy_truncated(report->reason_code, sizeof(report->reason_code), reason ? reason : "LTE_UNKNOWN");
}

static void update_lte_raw(sim7670_lte_report_t *report, const char *command, const char *response)
{
    if (report == NULL) {
        return;
    }
    copy_truncated(report->raw_command, sizeof(report->raw_command), command);
    copy_truncated(report->raw_response, sizeof(report->raw_response), response);
}

static void set_lte_http_reason(sim7670_lte_http_probe_result_t *result, const char *reason)
{
    if (result == NULL) {
        return;
    }
    copy_truncated(result->reason_code, sizeof(result->reason_code), reason ? reason : "LTE_HTTP_UNKNOWN");
}

static void update_lte_http_raw(sim7670_lte_http_probe_result_t *result, const char *command, const char *response)
{
    if (result == NULL) {
        return;
    }
    copy_truncated(result->raw_command, sizeof(result->raw_command), command);
    copy_truncated(result->raw_response, sizeof(result->raw_response), response);
}

static void split_mcc_mnc(const char *combined, sim7670_lte_report_t *report)
{
    if (combined == NULL || combined[0] == '\0' || report == NULL) {
        return;
    }
    char value[SIM7670_LTE_ID_MAX * 2];
    copy_truncated(value, sizeof(value), combined);
    strip_quotes(value);
    char *separator = strchr(value, '-');
    if (separator == NULL) {
        separator = strchr(value, ',');
    }
    if (separator == NULL) {
        return;
    }
    *separator = '\0';
    copy_truncated(report->mcc, sizeof(report->mcc), value);
    copy_truncated(report->mnc, sizeof(report->mnc), separator + 1);
}

static void parse_cpin(const char *response, sim7670_lte_report_t *report)
{
    char state[SIM7670_LTE_STATUS_MAX];
    const char *line = find_line(response, "+CPIN:");
    if (line == NULL || report == NULL) {
        return;
    }
    copy_truncated(state, sizeof(state), line + strlen("+CPIN:"));
    char *line_end = strpbrk(state, "\r\n");
    if (line_end != NULL) {
        *line_end = '\0';
    }
    strip_quotes(state);
    copy_truncated(report->sim_state, sizeof(report->sim_state), state);
    report->sim_ready = strcmp(state, "READY") == 0;
}

static void parse_cops(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+COPS:");
    char field[SIM7670_LTE_OPERATOR_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    copy_truncated(report->operator_name, sizeof(report->operator_name), field_at(line, "+COPS:", 2, field, sizeof(field)));
    strip_quotes(report->operator_name);
    (void)field_at(line, "+COPS:", 3, field, sizeof(field));
    strip_quotes(field);
    const char *rat = rat_from_cops_act(field);
    if (rat[0] != '\0') {
        copy_truncated(report->rat, sizeof(report->rat), rat);
    }
}

static void parse_cereg(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CEREG:");
    char field0[SIM7670_LTE_ID_MAX];
    char field1[SIM7670_LTE_ID_MAX];
    char field2[SIM7670_LTE_ID_MAX];
    char field3[SIM7670_LTE_ID_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    (void)field_at(line, "+CEREG:", 0, field0, sizeof(field0));
    (void)field_at(line, "+CEREG:", 1, field1, sizeof(field1));
    (void)field_at(line, "+CEREG:", 2, field2, sizeof(field2));
    (void)field_at(line, "+CEREG:", 3, field3, sizeof(field3));
    strip_quotes(field0);
    strip_quotes(field1);
    strip_quotes(field2);
    strip_quotes(field3);
    const char *stat = field1[0] != '\0' ? field1 : field0;
    copy_truncated(report->registration_state, sizeof(report->registration_state), registration_state_from_stat(stat));
    report->registered = stat[0] == '1' || stat[0] == '5';
    if (field1[0] != '\0') {
        copy_truncated(report->tac, sizeof(report->tac), field2);
        copy_truncated(report->cell_id, sizeof(report->cell_id), field3);
    }
}

static void parse_cgatt(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGATT:");
    char field[SIM7670_LTE_STATUS_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    (void)field_at(line, "+CGATT:", 0, field, sizeof(field));
    report->attached = strcmp(field, "1") == 0;
}

static void parse_cgdcont(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGDCONT:");
    char apn[SIM7670_LTE_OPERATOR_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    (void)field_at(line, "+CGDCONT:", 2, apn, sizeof(apn));
    strip_quotes(apn);
    copy_truncated(report->apn_state, sizeof(report->apn_state), apn[0] != '\0' ? "configured" : "missing");
}

static void parse_cgact(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGACT:");
    char field[SIM7670_LTE_STATUS_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    (void)field_at(line, "+CGACT:", 1, field, sizeof(field));
    report->pdp_active = strcmp(field, "1") == 0;
    copy_truncated(report->pdp_state, sizeof(report->pdp_state), report->pdp_active ? "active" : "inactive");
}

static void parse_cgpaddr(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGPADDR:");
    char ip[SIM7670_LTE_IP_MAX];
    if (line == NULL || report == NULL) {
        return;
    }
    (void)field_at(line, "+CGPADDR:", 1, ip, sizeof(ip));
    strip_quotes(ip);
    copy_truncated(report->assigned_ip, sizeof(report->assigned_ip), ip);
    report->ip_valid = ip[0] != '\0' && strcmp(ip, "0.0.0.0") != 0;
}

static void parse_csq(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CSQ:");
    char field[SIM7670_LTE_STATUS_MAX];
    int raw = 0;
    if (line == NULL || report == NULL) {
        return;
    }
    if (parse_int_field(field_at(line, "+CSQ:", 0, field, sizeof(field)), &raw) && raw >= 0 && raw <= 31) {
        report->rssi = -113 + (2 * raw);
        report->rssi_valid = true;
    }
}

static int split_prefixed_fields(
    const char *line,
    const char *prefix,
    char fields[][SIM7670_LTE_ID_MAX],
    int max_fields)
{
    int count = 0;
    for (int i = 0; i < max_fields; ++i) {
        char value[SIM7670_LTE_ID_MAX];
        const char *parsed = field_at(line, prefix, i, value, sizeof(value));
        if (parsed[0] == '\0') {
            break;
        }
        copy_truncated(fields[count], SIM7670_LTE_ID_MAX, parsed);
        strip_quotes(fields[count]);
        count++;
    }
    return count;
}

static void parse_cpsi(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CPSI:");
    char fields[20][SIM7670_LTE_ID_MAX];
    int value = 0;
    if (line == NULL || report == NULL) {
        return;
    }
    int count = split_prefixed_fields(line, "+CPSI:", fields, 20);
    if (count <= 0) {
        return;
    }
    copy_truncated(report->rat, sizeof(report->rat), fields[0]);
    if (count > 2) {
        split_mcc_mnc(fields[2], report);
    }
    if (count > 3) {
        copy_truncated(report->tac, sizeof(report->tac), fields[3]);
    }
    if (count > 4) {
        copy_truncated(report->cell_id, sizeof(report->cell_id), fields[4]);
    }
    if (count >= 4 && parse_int_field(fields[count - 4], &value)) {
        report->rsrq = value;
        report->rsrq_valid = true;
    }
    if (count >= 3 && parse_int_field(fields[count - 3], &value)) {
        report->rsrp = value;
        report->rsrp_valid = true;
    }
    if (count >= 2 && parse_int_field(fields[count - 2], &value)) {
        report->rssi = value;
        report->rssi_valid = true;
    }
    if (count >= 1 && parse_int_field(fields[count - 1], &value)) {
        report->sinr = value;
        report->sinr_valid = true;
    }
}

static void classify_lte_status(sim7670_lte_report_t *report)
{
    if (report == NULL) {
        return;
    }
    if (!report->driver_enabled) {
        set_lte_reason(report, "LTE_STATUS_DISABLED");
    } else if (!report->uart_ready) {
        set_lte_reason(report, "LTE_UART_INIT_FAILED");
    } else if (!report->at_ok) {
        set_lte_reason(report, "LTE_AT_UNREACHABLE");
    } else if (!report->sim_ready) {
        set_lte_reason(report, "LTE_SIM_NOT_READY");
    } else if (!report->registered) {
        set_lte_reason(report, "LTE_NOT_REGISTERED");
    } else if (!report->attached) {
        set_lte_reason(report, "LTE_NOT_ATTACHED");
    } else if (!report->pdp_active) {
        set_lte_reason(report, "LTE_PDP_INACTIVE");
    } else {
        set_lte_reason(report, "LTE_READY");
    }
}

bool sim7670_gnss_request_location(sim7670_gnss_report_t *report)
{
    if (report == NULL) {
        return false;
    }
    sim7670_gnss_report_init(report);
#if !CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    return false;
#else
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
#endif
}

bool sim7670_lte_query_status(sim7670_lte_report_t *report)
{
    if (report == NULL) {
        return false;
    }
    sim7670_lte_report_init(report);
#if !CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
    return false;
#else
    report->driver_enabled = true;
    if (sim7670_gnss_init() != ESP_OK) {
        set_lte_reason(report, "LTE_UART_INIT_FAILED");
        return false;
    }
    report->uart_ready = true;

    char response[AT_RESPONSE_BUFFER_SIZE];
    if (!sim7670_send_at("AT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT", response);
        set_lte_reason(report, "LTE_AT_UNREACHABLE");
        return false;
    }
    report->at_ok = true;
    update_lte_raw(report, "AT", response);

    if (sim7670_send_at("AT+CPIN?", "+CPIN:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CPIN?", response);
        parse_cpin(response, report);
    }
    if (sim7670_send_at("AT+COPS?", "+COPS:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+COPS?", response);
        parse_cops(response, report);
    }
    if (sim7670_send_at("AT+CEREG?", "+CEREG:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CEREG?", response);
        parse_cereg(response, report);
    }
    if (sim7670_send_at("AT+CGATT?", "+CGATT:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CGATT?", response);
        parse_cgatt(response, report);
    }
    if (sim7670_send_at("AT+CGDCONT?", "+CGDCONT:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CGDCONT?", response);
        parse_cgdcont(response, report);
    }
    if (sim7670_send_at("AT+CGACT?", "+CGACT:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CGACT?", response);
        parse_cgact(response, report);
    }
    if (sim7670_send_at("AT+CGPADDR=1", "+CGPADDR:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CGPADDR=1", response);
        parse_cgpaddr(response, report);
    }
    if (sim7670_send_at("AT+CSQ", "+CSQ:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CSQ", response);
        parse_csq(response, report);
    }
    if (sim7670_send_at("AT+CPSI?", "+CPSI:", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_raw(report, "AT+CPSI?", response);
        parse_cpsi(response, report);
    }
    classify_lte_status(report);
    return true;
#endif
}

bool sim7670_lte_http_post_json(
    const char *url,
    const char *bearer_token,
    const char *payload,
    sim7670_lte_http_probe_result_t *result)
{
    sim7670_lte_http_probe_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_lte_http_probe_result_init(result);
#if !SIM7670_LTE_HTTP_ENABLED
    (void)url;
    (void)bearer_token;
    (void)payload;
    return false;
#else
    result->driver_enabled = true;
    if (url == NULL || url[0] == '\0') {
        set_lte_http_reason(result, "LTE_HTTP_URL_MISSING");
        return false;
    }
    if (payload == NULL || payload[0] == '\0') {
        set_lte_http_reason(result, "LTE_HTTP_PAYLOAD_MISSING");
        return false;
    }
    if (sim7670_gnss_init() != ESP_OK) {
        set_lte_http_reason(result, "LTE_HTTP_UART_INIT_FAILED");
        return false;
    }
    result->uart_ready = true;

    char response[AT_RESPONSE_BUFFER_SIZE];
    if (!sim7670_send_at("AT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT", response);
        set_lte_http_reason(result, "LTE_HTTP_AT_UNREACHABLE");
        return false;
    }
    result->at_ok = true;
    update_lte_http_raw(result, "AT", response);

    (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));

    if (!sim7670_send_at("AT+HTTPINIT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPINIT", response);
        set_lte_http_reason(result, "LTE_HTTP_INIT_FAILED");
        return false;
    }
    result->http_init_ok = true;

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM
    if (!sim7670_send_at("AT+HTTPPARA=\"CID\",1", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPPARA=CID", response);
        set_lte_http_reason(result, "LTE_HTTP_CID_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
#endif

    char command[384];
    int written = snprintf(command, sizeof(command), "AT+HTTPPARA=\"URL\",\"%s\"", url);
    if (written < 0 || (size_t)written >= sizeof(command)) {
        set_lte_http_reason(result, "LTE_HTTP_URL_TOO_LONG");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    if (!sim7670_send_at(command, "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPPARA=URL", response);
        set_lte_http_reason(result, "LTE_HTTP_URL_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_url_ok = true;

    if (!sim7670_send_at(
            "AT+HTTPPARA=\"CONTENT\",\"application/json\"",
            "OK",
            CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
            response,
            sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPPARA=CONTENT", response);
        set_lte_http_reason(result, "LTE_HTTP_CONTENT_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_content_ok = true;

    if (bearer_token != NULL && bearer_token[0] != '\0') {
        written = snprintf(command, sizeof(command), "AT+HTTPPARA=\"USERDATA\",\"Authorization: Bearer %s\"", bearer_token);
        if (written < 0 || (size_t)written >= sizeof(command)) {
            set_lte_http_reason(result, "LTE_HTTP_HEADER_TOO_LONG");
            (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
            return false;
        }
        if (!sim7670_send_at_labeled(
                command,
                "AT+HTTPPARA=USERDATA",
                "OK",
                CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
                response,
                sizeof(response))) {
            update_lte_http_raw(result, "AT+HTTPPARA=USERDATA", response);
            set_lte_http_reason(result, "LTE_HTTP_HEADER_FAILED");
            (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
            return false;
        }
    }
    result->http_header_ok = true;

    size_t payload_len = strlen(payload);
    written = snprintf(command, sizeof(command), "AT+HTTPDATA=%u,10000", (unsigned)payload_len);
    if (written < 0 || (size_t)written >= sizeof(command)) {
        set_lte_http_reason(result, "LTE_HTTP_DATA_COMMAND_TOO_LONG");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    if (!sim7670_send_http_data(command, payload, 10000, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPDATA", response);
        set_lte_http_reason(result, "LTE_HTTP_DATA_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_data_ok = true;

    TickType_t action_start = xTaskGetTickCount();
    if (!sim7670_send_at(
            "AT+HTTPACTION=1",
            "+HTTPACTION:",
            CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
            response,
            sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPACTION=1", response);
        set_lte_http_reason(result, "LTE_HTTP_ACTION_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_action_ok = true;
    result->action_elapsed_ms = (int)((xTaskGetTickCount() - action_start) * portTICK_PERIOD_MS);
    result->action_elapsed_ms_valid = true;
    update_lte_http_raw(result, "AT+HTTPACTION=1", response);

    int status_code = 0;
    int data_len = 0;
    if (parse_httpaction(response, &status_code, &data_len)) {
        result->status_code = status_code;
        result->status_code_valid = true;
        result->data_len = data_len;
        result->data_len_valid = true;
    } else {
        set_lte_http_reason(result, "LTE_HTTP_STATUS_INVALID");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }

    if (data_len > 0 && sim7670_send_at("AT+HTTPREAD", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        result->http_read_ok = true;
        update_lte_http_raw(result, "AT+HTTPREAD", response);
    }
    (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));

    if (status_code >= 200 && status_code < 300) {
        set_lte_http_reason(result, "LTE_HTTP_OK");
        return true;
    }
    if (status_code >= 400 && status_code < 500) {
        set_lte_http_reason(result, "LTE_HTTP_CLIENT_ERROR");
    } else if (status_code >= 500 && status_code < 600) {
        set_lte_http_reason(result, "LTE_HTTP_SERVER_ERROR");
    } else {
        set_lte_http_reason(result, "LTE_HTTP_STATUS_ERROR");
    }
    return false;
#endif
}

bool sim7670_lte_http_get_json(
    const char *url,
    const char *bearer_token,
    char *response_body,
    size_t response_body_size,
    sim7670_lte_http_probe_result_t *result)
{
    sim7670_lte_http_probe_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_lte_http_probe_result_init(result);
    if (response_body != NULL && response_body_size > 0) {
        response_body[0] = '\0';
    }
#if !SIM7670_LTE_HTTP_ENABLED
    (void)url;
    (void)bearer_token;
    (void)response_body;
    (void)response_body_size;
    return false;
#else
    result->driver_enabled = true;
    if (url == NULL || url[0] == '\0') {
        set_lte_http_reason(result, "LTE_HTTP_URL_MISSING");
        return false;
    }
    if (response_body == NULL || response_body_size == 0) {
        set_lte_http_reason(result, "LTE_HTTP_RESPONSE_BUFFER_MISSING");
        return false;
    }
    if (sim7670_gnss_init() != ESP_OK) {
        set_lte_http_reason(result, "LTE_HTTP_UART_INIT_FAILED");
        return false;
    }
    result->uart_ready = true;

    char response[AT_RESPONSE_BUFFER_SIZE];
    if (!sim7670_send_at("AT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT", response);
        set_lte_http_reason(result, "LTE_HTTP_AT_UNREACHABLE");
        return false;
    }
    result->at_ok = true;
    update_lte_http_raw(result, "AT", response);

    (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));

    if (!sim7670_send_at("AT+HTTPINIT", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPINIT", response);
        set_lte_http_reason(result, "LTE_HTTP_INIT_FAILED");
        return false;
    }
    result->http_init_ok = true;

#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM
    if (!sim7670_send_at("AT+HTTPPARA=\"CID\",1", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPPARA=CID", response);
        set_lte_http_reason(result, "LTE_HTTP_CID_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
#endif

    char command[384];
    int written = snprintf(command, sizeof(command), "AT+HTTPPARA=\"URL\",\"%s\"", url);
    if (written < 0 || (size_t)written >= sizeof(command)) {
        set_lte_http_reason(result, "LTE_HTTP_URL_TOO_LONG");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    if (!sim7670_send_at(command, "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPPARA=URL", response);
        set_lte_http_reason(result, "LTE_HTTP_URL_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_url_ok = true;

    if (bearer_token != NULL && bearer_token[0] != '\0') {
        written = snprintf(command, sizeof(command), "AT+HTTPPARA=\"USERDATA\",\"Authorization: Bearer %s\"", bearer_token);
        if (written < 0 || (size_t)written >= sizeof(command)) {
            set_lte_http_reason(result, "LTE_HTTP_HEADER_TOO_LONG");
            (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
            return false;
        }
        if (!sim7670_send_at_labeled(
                command,
                "AT+HTTPPARA=USERDATA",
                "OK",
                CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
                response,
                sizeof(response))) {
            update_lte_http_raw(result, "AT+HTTPPARA=USERDATA", response);
            set_lte_http_reason(result, "LTE_HTTP_HEADER_FAILED");
            (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
            return false;
        }
    }
    result->http_header_ok = true;

    TickType_t action_start = xTaskGetTickCount();
    if (!sim7670_send_at(
            "AT+HTTPACTION=0",
            "+HTTPACTION:",
            CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
            response,
            sizeof(response))) {
        update_lte_http_raw(result, "AT+HTTPACTION=0", response);
        set_lte_http_reason(result, "LTE_HTTP_ACTION_FAILED");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    result->http_action_ok = true;
    result->action_elapsed_ms = (int)((xTaskGetTickCount() - action_start) * portTICK_PERIOD_MS);
    result->action_elapsed_ms_valid = true;
    update_lte_http_raw(result, "AT+HTTPACTION=0", response);

    int status_code = 0;
    int data_len = 0;
    if (parse_httpaction(response, &status_code, &data_len)) {
        result->status_code = status_code;
        result->status_code_valid = true;
        result->data_len = data_len;
        result->data_len_valid = true;
    } else {
        set_lte_http_reason(result, "LTE_HTTP_STATUS_INVALID");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }

    bool read_error = false;
    bool read_body_ok = false;
    read_body_ok = sim7670_lte_http_read_json_body(
        data_len,
        response,
        sizeof(response),
        response_body,
        response_body_size,
        result,
        &read_error);
    (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));

    if (status_code >= 200 && status_code < 300 && read_body_ok) {
        set_lte_http_reason(result, "LTE_HTTP_OK");
        return true;
    }
    if (status_code >= 200 && status_code < 300) {
        if (result->http_read_ok) {
            set_lte_http_reason(result, "LTE_HTTP_READ_BODY_PARSE_FAILED");
        } else {
            set_lte_http_reason(result, read_error ? "LTE_HTTP_READ_AT_ERROR" : "LTE_HTTP_READ_AT_TIMEOUT");
        }
        return false;
    }
    if (status_code >= 400 && status_code < 500) {
        set_lte_http_reason(result, "LTE_HTTP_CLIENT_ERROR");
    } else if (status_code >= 500 && status_code < 600) {
        set_lte_http_reason(result, "LTE_HTTP_SERVER_ERROR");
    } else {
        set_lte_http_reason(result, "LTE_HTTP_STATUS_ERROR");
    }
    return false;
#endif
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

bool sim7670_lte_query_status(sim7670_lte_report_t *report)
{
    sim7670_lte_report_init(report);
    return false;
}

bool sim7670_lte_http_post_json(
    const char *url,
    const char *bearer_token,
    const char *payload,
    sim7670_lte_http_probe_result_t *result)
{
    (void)url;
    (void)bearer_token;
    (void)payload;
    sim7670_lte_http_probe_result_init(result);
    return false;
}

bool sim7670_lte_http_get_json(
    const char *url,
    const char *bearer_token,
    char *response_body,
    size_t response_body_size,
    sim7670_lte_http_probe_result_t *result)
{
    (void)url;
    (void)bearer_token;
    if (response_body != NULL && response_body_size > 0) {
        response_body[0] = '\0';
    }
    sim7670_lte_http_probe_result_init(result);
    return false;
}
#endif
