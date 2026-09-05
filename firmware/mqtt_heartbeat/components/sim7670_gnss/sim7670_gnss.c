#include "sim7670_gnss.h"
#include "sim7670_http_exact_parser.h"
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
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

/*
 * The legacy translation unit still compiles its private HTTP helpers when
 * only GNSS/LTE status is selected. Kconfig intentionally omits the HTTP
 * timeout in that build. Keep those unreachable helpers buildable without
 * enabling an HTTP mode; enabled HTTP builds continue to use the configured
 * value exactly as before.
 */
#if SIM7670_LTE_HTTP_ENABLED
#define SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS \
    CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS
#else
#define SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS UINT32_C(30000)
#endif

#if SIM7670_AT_BACKEND_ENABLED
static const char *TAG = "sim7670_gnss";

static bool s_initialized;
static SemaphoreHandle_t s_uart_mutex;
static TaskHandle_t s_exclusive_owner_task;

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

void sim7670_location_bounded_result_init(
    sim7670_location_bounded_result_t *result)
{
    if (result == NULL) {
        return;
    }
    memset(result, 0, sizeof(*result));
    result->outcome = SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
    result->reason = SIM7670_LOCATION_BOUNDED_REASON_INVALID_ARGUMENT;
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

void sim7670_lte_http_exact_result_init(
    sim7670_lte_http_exact_result_t *result)
{
    if (result == NULL) {
        return;
    }
    memset(result, 0, sizeof(*result));
    result->status = SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT;
}

static void sim7670_exact_secure_clear(void *buffer, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)buffer;
    while (cursor != NULL && length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

static void sim7670_exact_clear_caller_response(
    const sim7670_lte_http_exact_request_t *request)
{
    if (request == NULL || request->response_body == NULL) {
        return;
    }
    const size_t clear_length =
        request->response_capacity <=
                SIM7670_LTE_HTTP_EXACT_CALLER_RESPONSE_CAPACITY_MAX_BYTES
            ? request->response_capacity
            : SIM7670_LTE_HTTP_EXACT_CALLER_RESPONSE_CAPACITY_MAX_BYTES;
    sim7670_exact_secure_clear(request->response_body, clear_length);
}

static bool sim7670_exact_timeouts_are_valid(
    const sim7670_lte_http_exact_request_t *request)
{
    return request != NULL && request->command_timeout_ms > 0U &&
           request->command_timeout_ms <=
               SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS &&
           request->data_timeout_ms > 0U &&
           request->data_timeout_ms <=
               SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS &&
           request->action_timeout_ms > 0U &&
           request->action_timeout_ms <=
               SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS &&
           request->read_timeout_ms > 0U &&
           request->read_timeout_ms <=
               SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS;
}

sim7670_lte_http_exact_status_t sim7670_lte_http_post_bytes_exact(
    const sim7670_lte_http_exact_request_t *request,
    sim7670_lte_http_exact_result_t *result)
{
    sim7670_lte_http_exact_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_exact_clear_caller_response(request);
    sim7670_lte_http_exact_result_init(result);
    if (request == NULL || request->payload == NULL ||
        request->payload_length == 0U || request->response_body == NULL ||
        request->response_capacity == 0U ||
        request->response_capacity >
            SIM7670_LTE_HTTP_EXACT_CALLER_RESPONSE_CAPACITY_MAX_BYTES) {
        result->status = SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT;
        return result->status;
    }
    if (sim7670_http_exact_url_is_valid(request->url) == 0 ||
        sim7670_http_exact_bearer_is_valid(request->bearer_token) == 0 ||
        !sim7670_exact_timeouts_are_valid(request)) {
        result->status = SIM7670_LTE_HTTP_EXACT_INVALID_CONFIG;
        return result->status;
    }
    if (request->payload_length >
        SIM7670_LTE_HTTP_EXACT_PAYLOAD_MAX_BYTES) {
        result->status = SIM7670_LTE_HTTP_EXACT_PAYLOAD_TOO_LARGE;
        return result->status;
    }

    /*
     * OPS-004 has not integrated a reviewed modem CA store plus exact
     * hostname/SNI and clock verification. This boundary is intentionally
     * terminal before UART initialization, bearer setup or payload I/O; a
     * caller boolean or callback is not accepted as security evidence.
     */
    result->status = SIM7670_LTE_HTTP_EXACT_TLS_PROFILE_UNVERIFIED;
    return result->status;
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
bool sim7670_at_backend_is_initialized(void)
{
    return s_initialized;
}

bool sim7670_at_backend_current_task_is_exclusive_owner(void)
{
    return s_initialized && s_exclusive_owner_task != NULL &&
        xTaskGetCurrentTaskHandle() == s_exclusive_owner_task;
}

static bool sim7670_at_backend_current_task_is_allowed(void)
{
    return s_exclusive_owner_task == NULL ||
        xTaskGetCurrentTaskHandle() == s_exclusive_owner_task;
}

esp_err_t sim7670_at_backend_init_exclusive_current_task(void)
{
    const TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
    if (current_task == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (s_initialized) {
        return s_exclusive_owner_task == current_task
            ? ESP_OK
            : ESP_ERR_INVALID_STATE;
    }
    if (s_uart_mutex != NULL || s_exclusive_owner_task != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    const uart_config_t uart_config = {
        .baud_rate = CONFIG_EGOLINK_SIM7670_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    const uart_port_t uart_num = configured_uart_num();
    esp_err_t err = uart_driver_install(
        uart_num, AT_RESPONSE_BUFFER_SIZE * 2, 0, 0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(
            TAG, "SIM7670_EXCLUSIVE_UART_INSTALL_FAIL err=%s",
            esp_err_to_name(err));
        return err == ESP_ERR_INVALID_STATE ? ESP_ERR_INVALID_STATE : err;
    }
    err = uart_param_config(uart_num, &uart_config);
    if (err == ESP_OK) {
        err = uart_set_pin(
            uart_num,
            CONFIG_EGOLINK_SIM7670_UART_TX_GPIO,
            CONFIG_EGOLINK_SIM7670_UART_RX_GPIO,
            UART_PIN_NO_CHANGE,
            UART_PIN_NO_CHANGE);
    }
    if (err == ESP_OK) {
        err = uart_flush_input(uart_num);
    }
    if (err != ESP_OK) {
        (void)uart_driver_delete(uart_num);
        ESP_LOGE(
            TAG, "SIM7670_EXCLUSIVE_UART_CONFIG_FAIL err=%s",
            esp_err_to_name(err));
        return err;
    }

    SemaphoreHandle_t uart_mutex = xSemaphoreCreateMutex();
    if (uart_mutex == NULL) {
        (void)uart_driver_delete(uart_num);
        return ESP_ERR_NO_MEM;
    }
    s_uart_mutex = uart_mutex;
    s_exclusive_owner_task = current_task;
    s_initialized = true;
    ESP_LOGI(
        TAG,
        "SIM7670_EXCLUSIVE_UART_READY uart=%d tx_gpio=%d rx_gpio=%d baud=%d",
        (int)uart_num,
        CONFIG_EGOLINK_SIM7670_UART_TX_GPIO,
        CONFIG_EGOLINK_SIM7670_UART_RX_GPIO,
        CONFIG_EGOLINK_SIM7670_UART_BAUD);
    return ESP_OK;
}

esp_err_t sim7670_gnss_init(void)
{
    if (s_initialized) {
        return sim7670_at_backend_current_task_is_allowed()
            ? ESP_OK
            : ESP_ERR_INVALID_STATE;
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

static int prefixed_field_count(const char *line, const char *prefix)
{
    if (line == NULL || prefix == NULL) {
        return 0;
    }
    const char *payload = strstr(line, prefix);
    if (payload == NULL) {
        return 0;
    }
    payload += strlen(prefix);
    int count = 1;
    for (const char *cursor = payload; *cursor != '\0' && *cursor != '\r' && *cursor != '\n'; ++cursor) {
        if (*cursor == ',') {
            count++;
        }
    }
    return count;
}

static bool parse_double_field(const char *text, double *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL) {
        return false;
    }
    char *end = NULL;
    errno = 0;
    double parsed = strtod(text, &end);
    if (end == text || *end != '\0' || errno == ERANGE || !isfinite(parsed)) {
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
    errno = 0;
    long parsed = strtol(text, &end, 10);
    if (end == text || *end != '\0' || errno == ERANGE || parsed < INT_MIN || parsed > INT_MAX) {
        return false;
    }
    *value = (int)parsed;
    return true;
}

static bool apply_coordinate_hemisphere(double coordinate, const char *hemisphere, bool is_lat, double *out)
{
    if (hemisphere == NULL || hemisphere[0] == '\0' || hemisphere[1] != '\0' || out == NULL) {
        return false;
    }
    char direction = (char)toupper((unsigned char)hemisphere[0]);
    if ((is_lat && direction != 'N' && direction != 'S') ||
        (!is_lat && direction != 'E' && direction != 'W')) {
        return false;
    }
    if (coordinate < 0.0 || !isfinite(coordinate)) {
        return false;
    }
    *out = (direction == 'S' || direction == 'W') ? -coordinate : coordinate;
    return true;
}

static bool parse_decimal_coordinate(const char *raw, const char *hemisphere, bool is_lat, double *out)
{
    double coordinate = 0.0;
    double maximum = is_lat ? 90.0 : 180.0;
    if (!parse_double_field(raw, &coordinate) || coordinate < 0.0 || coordinate > maximum) {
        return false;
    }
    return apply_coordinate_hemisphere(coordinate, hemisphere, is_lat, out);
}

static bool parse_ddmm_coordinate(const char *raw, const char *hemisphere, bool is_lat, double *out)
{
    double ddmm = 0.0;
    double maximum = is_lat ? 90.0 : 180.0;
    if (!parse_double_field(raw, &ddmm) || ddmm < 0.0 || ddmm >= (maximum + 1.0) * 100.0) {
        return false;
    }
    int degrees = (int)(ddmm / 100.0);
    double minutes = ddmm - ((double)degrees * 100.0);
    if (minutes < 0.0 || minutes >= 60.0 || degrees < 0 || (double)degrees > maximum) {
        return false;
    }
    double coordinate = (double)degrees + minutes / 60.0;
    if (coordinate > maximum) {
        return false;
    }
    return apply_coordinate_hemisphere(coordinate, hemisphere, is_lat, out);
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

static bool response_has_complete_line(const char *response, const char *token, bool prefix_match)
{
    if (response == NULL || token == NULL || token[0] == '\0') {
        return false;
    }
    size_t token_length = strlen(token);
    const char *cursor = response;
    while (*cursor != '\0') {
        while (*cursor == '\r' || *cursor == '\n') {
            cursor++;
        }
        const char *line_start = cursor;
        while (*cursor != '\0' && *cursor != '\r' && *cursor != '\n') {
            cursor++;
        }
        if (*cursor == '\0') {
            return false;
        }
        const char *line_end = cursor;
        while (line_end > line_start && isspace((unsigned char)line_end[-1])) {
            line_end--;
        }
        size_t line_length = (size_t)(line_end - line_start);
        bool matches = prefix_match
            ? line_length >= token_length && memcmp(line_start, token, token_length) == 0
            : line_length == token_length && memcmp(line_start, token, token_length) == 0;
        if (matches) {
            return true;
        }
    }
    return false;
}

static bool response_has_terminal_error(const char *response)
{
    return response_has_complete_line(response, "ERROR", false) ||
           response_has_complete_line(response, "+CME ERROR:", true) ||
           response_has_complete_line(response, "+CMS ERROR:", true);
}

static bool response_is_complete(const char *response, const char *expect, bool *saw_error)
{
    bool error = response_has_terminal_error(response);
    if (saw_error != NULL) {
        *saw_error = error;
    }
    if (error) {
        return true;
    }
    bool saw_ok = response_has_complete_line(response, "OK", false);
    if (!saw_ok) {
        return false;
    }
    if (expect == NULL || expect[0] == '\0' || strcmp(expect, "OK") == 0) {
        return true;
    }
    return response_has_complete_line(response, expect, true);
}

static const char *find_line(const char *response, const char *prefix);

static bool sim7670_send_at_labeled_internal(
    const char *command,
    const char *log_label,
    const char *expect,
    uint32_t timeout_ms,
    char *response,
    size_t response_size,
    bool require_complete_response)
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
    bool buffer_full = false;
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
            if (require_complete_response && (size_t)read > available) {
                buffer_full = true;
                break;
            }
            saw_error = contains_token(response, "ERROR");
            bool complete = require_complete_response
                ? response_is_complete(response, expect, &saw_error)
                : ((expect != NULL && expect[0] != '\0' && contains_token(response, expect)) || saw_error);
            if (complete) {
                matched = true;
                break;
            }
            if (require_complete_response && length == response_size - 1) {
                buffer_full = true;
                break;
            }
        }
    }
    xSemaphoreGive(s_uart_mutex);
    ESP_LOGI(
        TAG,
        "SIM7670_AT command=%s matched=%s terminal_error=%s buffer_full=%s",
        log_label ? log_label : command,
        matched ? "true" : "false",
        saw_error ? "true" : "false",
        buffer_full ? "true" : "false");
    return require_complete_response
        ? matched && !saw_error && !buffer_full
        : !saw_error && (matched || (expect == NULL || expect[0] == '\0'));
}

static bool sim7670_send_at_labeled(
    const char *command,
    const char *log_label,
    const char *expect,
    uint32_t timeout_ms,
    char *response,
    size_t response_size)
{
    return sim7670_send_at_labeled_internal(
        command, log_label, expect, timeout_ms, response, response_size, false);
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

static bool sim7670_send_at_complete(
    const char *command,
    const char *expect,
    uint32_t timeout_ms,
    char *response,
    size_t response_size)
{
    return sim7670_send_at_labeled_internal(
        command, command, expect, timeout_ms, response, response_size, true);
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

static bool find_complete_json_object(const char *response, const char **start_out, const char **end_out)
{
    if (response == NULL || start_out == NULL || end_out == NULL) {
        return false;
    }
    const char *start = strchr(response, '{');
    if (start == NULL) {
        return false;
    }

    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (const char *cursor = start; *cursor != '\0'; ++cursor) {
        char ch = *cursor;
        if (in_string) {
            if (escaped) {
                escaped = false;
                continue;
            }
            if (ch == '\\') {
                escaped = true;
                continue;
            }
            if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
            continue;
        }
        if (ch == '{') {
            depth++;
        } else if (ch == '}') {
            if (depth <= 0) {
                return false;
            }
            depth--;
            if (depth == 0) {
                *start_out = start;
                *end_out = cursor;
                return true;
            }
        }
    }
    return false;
}

static bool copy_httpread_json_body(const char *response, char *body, size_t body_size)
{
    if (response == NULL || body == NULL || body_size == 0) {
        return false;
    }
    body[0] = '\0';
    const char *start = NULL;
    const char *end = NULL;
    if (!find_complete_json_object(response, &start, &end)) {
        return false;
    }
    if (end < start) {
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

static bool copy_httpread_raw_body(const char *response, char *body, size_t body_size, int expected_len)
{
    if (response == NULL || body == NULL || body_size == 0) {
        return false;
    }
    body[0] = '\0';
    const char *marker = strstr(response, "+HTTPREAD:");
    if (marker == NULL) {
        return false;
    }
    const char *body_start = strchr(marker, '\n');
    if (body_start == NULL) {
        return false;
    }
    body_start++;
    while (*body_start == '\r' || *body_start == '\n') {
        body_start++;
    }

    const char *body_end = strstr(body_start, "\r\nOK");
    if (body_end == NULL) {
        body_end = strstr(body_start, "\nOK");
    }
    size_t available = body_end != NULL ? (size_t)(body_end - body_start) : strlen(body_start);
    if (expected_len > 0 && available > (size_t)expected_len) {
        available = (size_t)expected_len;
    }
    if (expected_len > 0 && available < (size_t)expected_len && body_end == NULL) {
        return false;
    }
    if (available >= body_size) {
        available = body_size - 1;
    }
    memcpy(body, body_start, available);
    body[available] = '\0';
    return available > 0;
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

static bool sim7670_send_httpread_raw_labeled(
    const char *command,
    const char *log_label,
    uint32_t timeout_ms,
    char *response,
    size_t response_size,
    char *response_body,
    size_t response_body_size,
    int expected_len)
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
            body_ok = copy_httpread_raw_body(response, response_body, response_body_size, expected_len);
            if (saw_error || body_ok) {
                break;
            }
        } else if ((saw_httpread || saw_ok) &&
                   (xTaskGetTickCount() - last_read_tick) >= pdMS_TO_TICKS(1200)) {
            body_ok = copy_httpread_raw_body(response, response_body, response_body_size, expected_len);
            break;
        }
    }
    xSemaphoreGive(s_uart_mutex);
    ESP_LOGI(
        TAG,
        "SIM7670_AT_HTTPREAD_RAW command=%s body_ok=%s saw_httpread=%s saw_ok=%s",
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
                SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
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
            SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
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

static bool sim7670_lte_http_read_raw_body(
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
        if (sim7670_send_httpread_raw_labeled(
                command,
                "AT+HTTPREAD=0,<len>",
                SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
                response,
                response_size,
                response_body,
                response_body_size,
                data_len)) {
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

    if (sim7670_send_httpread_raw_labeled(
            "AT+HTTPREAD",
            "AT+HTTPREAD",
            SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
            response,
            response_size,
            response_body,
            response_body_size,
            data_len)) {
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

typedef enum {
    GNSS_PARSE_INVALID = 0,
    GNSS_PARSE_FIX,
    GNSS_PARSE_NO_FIX,
} gnss_parse_outcome_t;

static bool prefixed_fields_are_all_empty(
    const char *line,
    const char *prefix,
    int first_accepted_count,
    int second_accepted_count)
{
    const int count = prefixed_field_count(line, prefix);
    if (count != first_accepted_count && count != second_accepted_count) {
        return false;
    }
    for (int index = 0; index < count; ++index) {
        char field[2];
        if (field_at(line, prefix, index, field, sizeof(field))[0] != '\0') {
            return false;
        }
    }
    return true;
}

static gnss_parse_outcome_t parse_cgpsinfo(
    const char *line, sim7670_gnss_report_t *report)
{
    char lat_raw[24];
    char ns[4];
    char lon_raw[24];
    char ew[4];
    char field[24];
    double value = 0.0;
    double lat = 0.0;
    double lon = 0.0;
    if (report == NULL) {
        return GNSS_PARSE_INVALID;
    }
    if (prefixed_fields_are_all_empty(line, "+CGPSINFO:", 9, 9)) {
        return GNSS_PARSE_NO_FIX;
    }
    if (prefixed_field_count(line, "+CGPSINFO:") != 9) {
        return GNSS_PARSE_INVALID;
    }
    const bool lat_ok = parse_ddmm_coordinate(
        field_at(line, "+CGPSINFO:", 0, lat_raw, sizeof(lat_raw)),
        field_at(line, "+CGPSINFO:", 1, ns, sizeof(ns)),
        true,
        &lat);
    const bool lon_ok = parse_ddmm_coordinate(
        field_at(line, "+CGPSINFO:", 2, lon_raw, sizeof(lon_raw)),
        field_at(line, "+CGPSINFO:", 3, ew, sizeof(ew)),
        false,
        &lon);
    if (!lat_ok || !lon_ok) {
        return GNSS_PARSE_INVALID;
    }
    report->lat = lat;
    report->lon = lon;
    report->lat_valid = true;
    report->lon_valid = true;
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
    return GNSS_PARSE_FIX;
}

static bool cgnss_coordinate_candidate(
    const char *line,
    int lat_index,
    int ns_index,
    int lon_index,
    int ew_index,
    double *lat,
    double *lon,
    int *tail_index)
{
    char lat_raw[24];
    char ns[4];
    char lon_raw[24];
    char ew[4];
    const char *lat_text = field_at(line, "+CGNSSINFO:", lat_index, lat_raw, sizeof(lat_raw));
    const char *ns_text = field_at(line, "+CGNSSINFO:", ns_index, ns, sizeof(ns));
    const char *lon_text = field_at(line, "+CGNSSINFO:", lon_index, lon_raw, sizeof(lon_raw));
    const char *ew_text = field_at(line, "+CGNSSINFO:", ew_index, ew, sizeof(ew));
    double raw_lat = 0.0;
    double raw_lon = 0.0;
    if (!parse_double_field(lat_text, &raw_lat) || !parse_double_field(lon_text, &raw_lon)) {
        return false;
    }

    bool decimal_pair = raw_lat >= 0.0 && raw_lat <= 90.0 && raw_lon >= 0.0 && raw_lon <= 180.0;
    bool parsed = decimal_pair
        ? parse_decimal_coordinate(lat_text, ns_text, true, lat) &&
              parse_decimal_coordinate(lon_text, ew_text, false, lon)
        : parse_ddmm_coordinate(lat_text, ns_text, true, lat) &&
              parse_ddmm_coordinate(lon_text, ew_text, false, lon);
    if (parsed && tail_index != NULL) {
        *tail_index = ew_index + 1;
    }
    return parsed;
}

static gnss_parse_outcome_t parse_cgnssinfo(
    const char *line, sim7670_gnss_report_t *report)
{
    char field[24];
    double value = 0.0;
    int int_value = 0;
    int mode = 0;
    int tail_index = 0;
    double lat = 0.0;
    double lon = 0.0;
    if (report == NULL) {
        return GNSS_PARSE_INVALID;
    }
    /* Both layouts have been observed from this modem with every field empty. */
    if (prefixed_fields_are_all_empty(line, "+CGNSSINFO:", 9, 18)) {
        return GNSS_PARSE_NO_FIX;
    }
    if (!parse_int_field(field_at(line, "+CGNSSINFO:", 0, field, sizeof(field)), &mode) ||
        (mode != 2 && mode != 3)) {
        return GNSS_PARSE_INVALID;
    }
    const bool fix =
        cgnss_coordinate_candidate(
            line, 5, 6, 7, 8, &lat, &lon, &tail_index) ||
        cgnss_coordinate_candidate(
            line, 4, 5, 6, 7, &lat, &lon, &tail_index);
    if (!fix ||
        prefixed_field_count(line, "+CGNSSINFO:") != tail_index + 9) {
        return GNSS_PARSE_INVALID;
    }
    report->lat = lat;
    report->lon = lon;
    report->lat_valid = true;
    report->lon_valid = true;
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 2, field, sizeof(field)), &value)) {
        report->altitude_m = value;
        report->altitude_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 3, field, sizeof(field)), &value)) {
        report->speed_mps = value * KNOT_TO_MPS;
        report->speed_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 4, field, sizeof(field)), &value)) {
        report->course_deg = value;
        report->course_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 5, field, sizeof(field)), &value)) {
        report->pdop = value;
        report->pdop_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 6, field, sizeof(field)), &value)) {
        report->hdop = value;
        report->hdop_valid = true;
    }
    if (parse_double_field(field_at(line, "+CGNSSINFO:", tail_index + 7, field, sizeof(field)), &value)) {
        report->vdop = value;
        report->vdop_valid = true;
    }
    if (parse_int_field(field_at(line, "+CGNSSINFO:", tail_index + 8, field, sizeof(field)), &int_value) &&
        int_value >= 0) {
        report->satellites = int_value;
        report->satellites_valid = true;
    }
    copy_truncated(
        report->utc_date,
        sizeof(report->utc_date),
        field_at(line, "+CGNSSINFO:", tail_index, field, sizeof(field)));
    copy_truncated(
        report->utc_time,
        sizeof(report->utc_time),
        field_at(line, "+CGNSSINFO:", tail_index + 1, field, sizeof(field)));
    return GNSS_PARSE_FIX;
}

static const char *find_line(const char *response, const char *prefix)
{
    return response == NULL ? NULL : strstr(response, prefix);
}

static gnss_parse_outcome_t parse_gnss_query(
    const char *command,
    const char *expected_prefix,
    const char *response,
    sim7670_gnss_report_t *report)
{
    const char *line = find_line(response, expected_prefix);
    copy_truncated(report->raw_command, sizeof(report->raw_command), command);
    copy_truncated(
        report->raw_response,
        sizeof(report->raw_response),
        line != NULL ? line : response);
    if (line == NULL) {
        return GNSS_PARSE_INVALID;
    }
    if (strcmp(expected_prefix, "+CGNSSINFO:") == 0) {
        return parse_cgnssinfo(line, report);
    }
    if (strcmp(expected_prefix, "+CGPSINFO:") == 0) {
        return parse_cgpsinfo(line, report);
    }
    return GNSS_PARSE_INVALID;
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

static bool split_mcc_mnc(
    const char *combined, sim7670_lte_report_t *report)
{
    if (combined == NULL || combined[0] == '\0' || report == NULL) {
        return false;
    }
    char value[SIM7670_LTE_ID_MAX * 2];
    copy_truncated(value, sizeof(value), combined);
    strip_quotes(value);
    char *separator = strchr(value, '-');
    if (separator == NULL) {
        separator = strchr(value, ',');
    }
    if (separator == NULL) {
        return false;
    }
    *separator = '\0';
    if (value[0] == '\0' || separator[1] == '\0') {
        return false;
    }
    copy_truncated(report->mcc, sizeof(report->mcc), value);
    copy_truncated(report->mnc, sizeof(report->mnc), separator + 1);
    return true;
}

static bool parse_cpin(const char *response, sim7670_lte_report_t *report)
{
    char state[SIM7670_LTE_STATUS_MAX];
    const char *line = find_line(response, "+CPIN:");
    if (line == NULL || report == NULL) {
        return false;
    }
    copy_truncated(state, sizeof(state), line + strlen("+CPIN:"));
    char *line_end = strpbrk(state, "\r\n");
    if (line_end != NULL) {
        *line_end = '\0';
    }
    strip_quotes(state);
    const bool recognized =
        strcmp(state, "READY") == 0 || strcmp(state, "SIM PIN") == 0 ||
        strcmp(state, "SIM PUK") == 0 ||
        strcmp(state, "SIM PIN2") == 0 ||
        strcmp(state, "SIM PUK2") == 0 ||
        strcmp(state, "PH-NET PIN") == 0 ||
        strcmp(state, "NOT INSERTED") == 0 ||
        strcmp(state, "NOT READY") == 0;
    if (!recognized) {
        return false;
    }
    copy_truncated(report->sim_state, sizeof(report->sim_state), state);
    report->sim_ready = strcmp(state, "READY") == 0;
    return true;
}

static bool parse_cops(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+COPS:");
    char field[SIM7670_LTE_OPERATOR_MAX];
    int mode = 0;
    if (line == NULL || report == NULL) {
        return false;
    }
    if (!parse_int_field(
            field_at(line, "+COPS:", 0, field, sizeof(field)), &mode) ||
        mode < 0 || mode > 4) {
        return false;
    }
    copy_truncated(report->operator_name, sizeof(report->operator_name), field_at(line, "+COPS:", 2, field, sizeof(field)));
    strip_quotes(report->operator_name);
    (void)field_at(line, "+COPS:", 3, field, sizeof(field));
    strip_quotes(field);
    const char *rat = rat_from_cops_act(field);
    if (rat[0] != '\0') {
        copy_truncated(report->rat, sizeof(report->rat), rat);
    }
    return true;
}

static bool parse_cereg(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CEREG:");
    char field0[SIM7670_LTE_ID_MAX];
    char field1[SIM7670_LTE_ID_MAX];
    char field2[SIM7670_LTE_ID_MAX];
    char field3[SIM7670_LTE_ID_MAX];
    int stat_value = 0;
    if (line == NULL || report == NULL ||
        prefixed_field_count(line, "+CEREG:") < 2) {
        return false;
    }
    (void)field_at(line, "+CEREG:", 0, field0, sizeof(field0));
    (void)field_at(line, "+CEREG:", 1, field1, sizeof(field1));
    (void)field_at(line, "+CEREG:", 2, field2, sizeof(field2));
    (void)field_at(line, "+CEREG:", 3, field3, sizeof(field3));
    strip_quotes(field0);
    strip_quotes(field1);
    strip_quotes(field2);
    strip_quotes(field3);
    const char *stat = field1;
    if (!parse_int_field(stat, &stat_value) || stat_value < 0 ||
        stat_value > 5) {
        return false;
    }
    copy_truncated(report->registration_state, sizeof(report->registration_state), registration_state_from_stat(stat));
    report->registered = stat_value == 1 || stat_value == 5;
    if (field1[0] != '\0') {
        copy_truncated(report->tac, sizeof(report->tac), field2);
        copy_truncated(report->cell_id, sizeof(report->cell_id), field3);
    }
    return true;
}

static bool parse_cgatt(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGATT:");
    char field[SIM7670_LTE_STATUS_MAX];
    int attached = 0;
    if (line == NULL || report == NULL) {
        return false;
    }
    (void)field_at(line, "+CGATT:", 0, field, sizeof(field));
    if (!parse_int_field(field, &attached) ||
        (attached != 0 && attached != 1)) {
        return false;
    }
    report->attached = attached == 1;
    return true;
}

static bool parse_cgdcont(const char *response, sim7670_lte_report_t *report)
{
    if (response == NULL || report == NULL) {
        return false;
    }
    const char *cursor = response;
    const char *line = NULL;
    while ((line = find_line(cursor, "+CGDCONT:")) != NULL) {
        char apn[SIM7670_LTE_OPERATOR_MAX];
        char field[SIM7670_LTE_STATUS_MAX];
        int cid = 0;
        if (prefixed_field_count(line, "+CGDCONT:") >= 3 &&
            parse_int_field(
                field_at(line, "+CGDCONT:", 0, field, sizeof(field)),
                &cid) &&
            cid == 1 &&
            field_at(line, "+CGDCONT:", 1, field, sizeof(field))[0] !=
                '\0') {
            (void)field_at(
                line, "+CGDCONT:", 2, apn, sizeof(apn));
            strip_quotes(apn);
            copy_truncated(
                report->apn_state,
                sizeof(report->apn_state),
                apn[0] != '\0' ? "configured" : "missing");
            return true;
        }
        cursor = line + strlen("+CGDCONT:");
    }
    return false;
}

static bool parse_cgact(const char *response, sim7670_lte_report_t *report)
{
    if (response == NULL || report == NULL) {
        return false;
    }
    const char *cursor = response;
    const char *line = NULL;
    while ((line = find_line(cursor, "+CGACT:")) != NULL) {
        char field[SIM7670_LTE_STATUS_MAX];
        int cid = 0;
        int active = 0;
        if (parse_int_field(
                field_at(line, "+CGACT:", 0, field, sizeof(field)),
                &cid) &&
            cid == 1 &&
            parse_int_field(
                field_at(line, "+CGACT:", 1, field, sizeof(field)),
                &active) &&
            (active == 0 || active == 1)) {
            report->pdp_active = active == 1;
            copy_truncated(
                report->pdp_state,
                sizeof(report->pdp_state),
                report->pdp_active ? "active" : "inactive");
            return true;
        }
        cursor = line + strlen("+CGACT:");
    }
    return false;
}

static bool parse_cgpaddr(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CGPADDR:");
    char ip[SIM7670_LTE_IP_MAX];
    char field[SIM7670_LTE_STATUS_MAX];
    int cid = 0;
    if (line == NULL || report == NULL) {
        return false;
    }
    if (prefixed_field_count(line, "+CGPADDR:") < 2 ||
        !parse_int_field(
            field_at(line, "+CGPADDR:", 0, field, sizeof(field)), &cid) ||
        cid != 1) {
        return false;
    }
    (void)field_at(line, "+CGPADDR:", 1, ip, sizeof(ip));
    strip_quotes(ip);
    copy_truncated(report->assigned_ip, sizeof(report->assigned_ip), ip);
    report->ip_valid = ip[0] != '\0' && strcmp(ip, "0.0.0.0") != 0;
    return true;
}

static bool parse_csq(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CSQ:");
    char field[SIM7670_LTE_STATUS_MAX];
    int raw = 0;
    if (line == NULL || report == NULL) {
        return false;
    }
    if (!parse_int_field(
            field_at(line, "+CSQ:", 0, field, sizeof(field)), &raw) ||
        !((raw >= 0 && raw <= 31) || raw == 99)) {
        return false;
    }
    if (raw != 99) {
        report->rssi = -113 + (2 * raw);
        report->rssi_valid = true;
    }
    return true;
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

static bool parse_cpsi(const char *response, sim7670_lte_report_t *report)
{
    const char *line = find_line(response, "+CPSI:");
    char fields[20][SIM7670_LTE_ID_MAX];
    int value = 0;
    if (line == NULL || report == NULL) {
        return false;
    }
    int count = split_prefixed_fields(line, "+CPSI:", fields, 20);
    if (count <= 0) {
        return false;
    }
    copy_truncated(report->rat, sizeof(report->rat), fields[0]);
    if (strcmp(fields[0], "NO SERVICE") == 0) {
        return true;
    }
    if (count < 5) {
        return false;
    }
    const bool mcc_mnc_valid = split_mcc_mnc(fields[2], report);
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
    report->cell_identity_valid =
        mcc_mnc_valid && report->tac[0] != '\0' &&
        report->cell_id[0] != '\0';
    return true;
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
    } else if (!report->cpin_query.parse_valid) {
        set_lte_reason(report, "LTE_STATUS_UNKNOWN");
    } else if (!report->sim_ready) {
        set_lte_reason(report, "LTE_SIM_NOT_READY");
    } else if (!report->cereg_query.parse_valid) {
        set_lte_reason(report, "LTE_STATUS_UNKNOWN");
    } else if (!report->registered) {
        set_lte_reason(report, "LTE_NOT_REGISTERED");
    } else if (!report->cgatt_query.parse_valid) {
        set_lte_reason(report, "LTE_STATUS_UNKNOWN");
    } else if (!report->attached) {
        set_lte_reason(report, "LTE_NOT_ATTACHED");
    } else if (!report->cgact_query.parse_valid) {
        set_lte_reason(report, "LTE_STATUS_UNKNOWN");
    } else if (!report->pdp_active) {
        set_lte_reason(report, "LTE_PDP_INACTIVE");
    } else {
        set_lte_reason(report, "LTE_READY");
    }
}

static void record_gnss_query_outcome(
    sim7670_gnss_query_evidence_t *evidence,
    gnss_parse_outcome_t outcome)
{
    if (evidence == NULL) {
        return;
    }
    evidence->parse_valid = outcome != GNSS_PARSE_INVALID;
    evidence->fix_observed = outcome == GNSS_PARSE_FIX;
    evidence->no_fix_observed = outcome == GNSS_PARSE_NO_FIX;
}

typedef bool (*lte_response_parser_fn)(
    const char *response, sim7670_lte_report_t *report);

static void run_lte_status_query(
    sim7670_lte_report_t *report,
    sim7670_at_query_evidence_t *evidence,
    const char *command,
    const char *expected_prefix,
    char *response,
    size_t response_size,
    lte_response_parser_fn parser)
{
    if (report == NULL || evidence == NULL || command == NULL ||
        expected_prefix == NULL || response == NULL || response_size == 0U ||
        parser == NULL) {
        return;
    }
    evidence->attempted = true;
    evidence->response_observed = sim7670_send_at_complete(
        command,
        expected_prefix,
        CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
        response,
        response_size);
    if (!evidence->response_observed) {
        return;
    }
    update_lte_raw(report, command, response);
    evidence->parse_valid = parser(response, report);
}

typedef enum {
    SIM7670_BOUNDED_AT_OK = 0,
    SIM7670_BOUNDED_AT_DEADLINE,
    SIM7670_BOUNDED_AT_OWNER_BUSY,
    SIM7670_BOUNDED_AT_TX_INCOMPLETE,
    SIM7670_BOUNDED_AT_RESPONSE_TIMEOUT,
    SIM7670_BOUNDED_AT_IO_ERROR,
    SIM7670_BOUNDED_AT_TERMINAL_ERROR,
    SIM7670_BOUNDED_AT_RESPONSE_TRUNCATED,
} sim7670_bounded_at_status_t;

static bool bounded_request_valid(
    const sim7670_location_bounded_request_t *request)
{
    return request != NULL && request->timeout_ms > UINT32_C(0) &&
        request->timeout_ms <= SIM7670_LOCATION_BOUNDED_TIMEOUT_MAX_MS &&
        request->per_command_timeout_cap_ms > UINT32_C(0) &&
        request->per_command_timeout_cap_ms <=
            SIM7670_LOCATION_BOUNDED_COMMAND_CAP_MAX_MS &&
        request->cancel_requested != NULL &&
        request->operation_token != UINT32_C(0);
}

static int64_t bounded_now_us(void)
{
    return esp_timer_get_time();
}

/*
 * Deliberately rounds down. A wait may be shorter than remaining wall time but
 * can never be rounded up past the request/command deadline. Sub-tick tails
 * are polled non-blocking.
 */
static TickType_t bounded_wait_ticks_floor(
    int64_t now_us,
    int64_t deadline_us,
    uint32_t maximum_wait_ms)
{
    if (now_us < INT64_C(0) || deadline_us <= now_us) {
        return (TickType_t)0;
    }
    uint64_t remaining_ms =
        (uint64_t)(deadline_us - now_us) / UINT64_C(1000);
    if (remaining_ms > (uint64_t)maximum_wait_ms) {
        remaining_ms = (uint64_t)maximum_wait_ms;
    }
    const uint64_t tick_period_ms = (uint64_t)portTICK_PERIOD_MS;
    if (tick_period_ms == UINT64_C(0)) {
        return (TickType_t)0;
    }
    uint64_t ticks = remaining_ms / tick_period_ms;
    const uint64_t maximum_ticks = (uint64_t)portMAX_DELAY - UINT64_C(1);
    if (ticks > maximum_ticks) {
        ticks = maximum_ticks;
    }
    return (TickType_t)ticks;
}

static int64_t bounded_command_deadline_us(
    int64_t now_us,
    int64_t request_deadline_us,
    uint32_t command_cap_ms)
{
    const int64_t cap_us = (int64_t)command_cap_ms * INT64_C(1000);
    const int64_t cap_deadline =
        now_us <= INT64_MAX - cap_us ? now_us + cap_us : INT64_MAX;
    return cap_deadline < request_deadline_us
        ? cap_deadline
        : request_deadline_us;
}

static void bounded_increment_u16(uint16_t *value)
{
    if (*value != UINT16_MAX) {
        ++(*value);
    }
}

static sim7670_bounded_at_status_t sim7670_send_at_complete_bounded(
    const char *command,
    const char *expect,
    int64_t request_deadline_us,
    uint32_t command_cap_ms,
    char *response,
    size_t response_size,
    sim7670_location_bounded_result_t *result)
{
    if (command == NULL || expect == NULL || response == NULL ||
        response_size == 0U || result == NULL) {
        return SIM7670_BOUNDED_AT_IO_ERROR;
    }
    response[0] = '\0';
    int64_t now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us >= request_deadline_us) {
        return SIM7670_BOUNDED_AT_DEADLINE;
    }
    const int64_t command_deadline_us = bounded_command_deadline_us(
        now_us, request_deadline_us, command_cap_ms);
    const TickType_t owner_wait = bounded_wait_ticks_floor(
        now_us, command_deadline_us, command_cap_ms);
    if (xSemaphoreTake(s_uart_mutex, owner_wait) != pdTRUE) {
        return SIM7670_BOUNDED_AT_OWNER_BUSY;
    }
    now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us >= command_deadline_us) {
        xSemaphoreGive(s_uart_mutex);
        return SIM7670_BOUNDED_AT_OWNER_BUSY;
    }

    sim7670_bounded_at_status_t status = SIM7670_BOUNDED_AT_IO_ERROR;
    result->io_started = true;
    bounded_increment_u16(&result->commands_attempted);
    if (uart_flush_input(configured_uart_num()) != ESP_OK) {
        xSemaphoreGive(s_uart_mutex);
        return status;
    }
    now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us >= command_deadline_us) {
        xSemaphoreGive(s_uart_mutex);
        return SIM7670_BOUNDED_AT_DEADLINE;
    }

    char transmit[SIM7670_LTE_HTTP_RAW_COMMAND_MAX];
    const size_t command_length = strlen(command);
    if (command_length > sizeof(transmit) - 3U) {
        xSemaphoreGive(s_uart_mutex);
        return SIM7670_BOUNDED_AT_TX_INCOMPLETE;
    }
    (void)memcpy(transmit, command, command_length);
    transmit[command_length] = '\r';
    transmit[command_length + 1U] = '\n';
    const size_t transmit_length = command_length + 2U;
    size_t transmitted = 0U;
    while (transmitted < transmit_length) {
        now_us = bounded_now_us();
        if (now_us < INT64_C(0) || now_us >= command_deadline_us) {
            status = SIM7670_BOUNDED_AT_TX_INCOMPLETE;
            break;
        }
        const size_t remaining = transmit_length - transmitted;
        const uint32_t offered = remaining <= UINT32_MAX
            ? (uint32_t)remaining
            : UINT32_MAX;
        const int written = uart_tx_chars(
            configured_uart_num(), transmit + transmitted, offered);
        if (written < 0 || (uint32_t)written > offered) {
            status = SIM7670_BOUNDED_AT_IO_ERROR;
            break;
        }
        if (written == 0) {
            taskYIELD();
            continue;
        }
        transmitted += (size_t)written;
    }
    if (transmitted != transmit_length) {
        xSemaphoreGive(s_uart_mutex);
        return status;
    }
    now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us > command_deadline_us) {
        xSemaphoreGive(s_uart_mutex);
        return SIM7670_BOUNDED_AT_DEADLINE;
    }
    bounded_increment_u16(&result->commands_tx_complete);

    uint8_t chunk[AT_READ_CHUNK_SIZE];
    size_t length = 0U;
    while (true) {
        now_us = bounded_now_us();
        if (now_us < INT64_C(0)) {
            status = SIM7670_BOUNDED_AT_IO_ERROR;
            break;
        }
        if (now_us >= command_deadline_us) {
            status = SIM7670_BOUNDED_AT_RESPONSE_TIMEOUT;
            break;
        }
        const TickType_t read_wait = bounded_wait_ticks_floor(
            now_us, command_deadline_us, UINT32_C(100));
        const int read = uart_read_bytes(
            configured_uart_num(), chunk, sizeof(chunk), read_wait);
        now_us = bounded_now_us();
        if (now_us < INT64_C(0) || now_us > command_deadline_us) {
            status = SIM7670_BOUNDED_AT_RESPONSE_TIMEOUT;
            break;
        }
        if (read < 0) {
            status = SIM7670_BOUNDED_AT_IO_ERROR;
            break;
        }
        if (read == 0) {
            taskYIELD();
            continue;
        }
        const size_t read_size = (size_t)read;
        const size_t available = response_size - 1U - length;
        if (read_size > available) {
            if (available > 0U) {
                (void)memcpy(response + length, chunk, available);
                length += available;
                response[length] = '\0';
            }
            status = SIM7670_BOUNDED_AT_RESPONSE_TRUNCATED;
            break;
        }
        (void)memcpy(response + length, chunk, read_size);
        length += read_size;
        response[length] = '\0';
        bool terminal_error = false;
        if (response_is_complete(response, expect, &terminal_error)) {
            status = terminal_error
                ? SIM7670_BOUNDED_AT_TERMINAL_ERROR
                : SIM7670_BOUNDED_AT_OK;
            break;
        }
        if (length == response_size - 1U) {
            status = SIM7670_BOUNDED_AT_RESPONSE_TRUNCATED;
            break;
        }
    }
    xSemaphoreGive(s_uart_mutex);
    now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us > request_deadline_us) {
        return SIM7670_BOUNDED_AT_DEADLINE;
    }
    if (now_us > command_deadline_us) {
        return SIM7670_BOUNDED_AT_RESPONSE_TIMEOUT;
    }
    if (status == SIM7670_BOUNDED_AT_OK) {
        bounded_increment_u16(&result->commands_completed);
    }
    return status;
}

static sim7670_location_bounded_reason_t bounded_reason_from_at(
    sim7670_bounded_at_status_t status)
{
    switch (status) {
    case SIM7670_BOUNDED_AT_DEADLINE:
        return SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED;
    case SIM7670_BOUNDED_AT_OWNER_BUSY:
        return SIM7670_LOCATION_BOUNDED_REASON_MODEM_OWNER_BUSY;
    case SIM7670_BOUNDED_AT_TX_INCOMPLETE:
        return SIM7670_LOCATION_BOUNDED_REASON_TX_INCOMPLETE;
    case SIM7670_BOUNDED_AT_RESPONSE_TIMEOUT:
        return SIM7670_LOCATION_BOUNDED_REASON_AT_RESPONSE_TIMEOUT;
    case SIM7670_BOUNDED_AT_TERMINAL_ERROR:
        return SIM7670_LOCATION_BOUNDED_REASON_AT_TERMINAL_ERROR;
    case SIM7670_BOUNDED_AT_RESPONSE_TRUNCATED:
        return SIM7670_LOCATION_BOUNDED_REASON_RESPONSE_TRUNCATED;
    case SIM7670_BOUNDED_AT_IO_ERROR:
    case SIM7670_BOUNDED_AT_OK:
    default:
        return SIM7670_LOCATION_BOUNDED_REASON_AT_IO_ERROR;
    }
}

static void bounded_finish(
    sim7670_location_bounded_result_t *result,
    int64_t start_us,
    int64_t deadline_us,
    sim7670_location_bounded_outcome_t outcome,
    sim7670_location_bounded_reason_t reason)
{
    int64_t finish_us = bounded_now_us();
    if (finish_us < start_us) {
        finish_us = start_us;
        outcome = SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
        reason = SIM7670_LOCATION_BOUNDED_REASON_AT_IO_ERROR;
    } else if (finish_us > deadline_us) {
        outcome = SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
        reason = SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED;
    }
    result->outcome = outcome;
    result->reason = reason;
    result->partial_or_unknown =
        outcome == SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN ||
        (outcome == SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED &&
         result->io_started);
    result->elapsed_ms =
        (uint64_t)(finish_us - start_us) / UINT64_C(1000);
}

static bool bounded_cancel_requested(
    const sim7670_location_bounded_request_t *request)
{
    return request->cancel_requested(
        request->cancel_context, request->operation_token);
}

static bool bounded_begin(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result,
    int64_t *start_us,
    int64_t *deadline_us)
{
    if (!bounded_request_valid(request) || result == NULL || start_us == NULL ||
        deadline_us == NULL) {
        return false;
    }
    *start_us = bounded_now_us();
    const int64_t timeout_us = (int64_t)request->timeout_ms * INT64_C(1000);
    if (*start_us < INT64_C(0) || *start_us > INT64_MAX - timeout_us) {
        return false;
    }
    *deadline_us = *start_us + timeout_us;
    if (bounded_cancel_requested(request)) {
        result->cancel_before_io = true;
        bounded_finish(
            result, *start_us, *deadline_us,
            SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED,
            SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BEFORE_IO);
        return false;
    }
    return true;
}

static bool bounded_cancel_at_boundary(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result,
    int64_t start_us,
    int64_t deadline_us)
{
    const int64_t now_us = bounded_now_us();
    if (now_us < INT64_C(0) || now_us >= deadline_us) {
        bounded_finish(
            result, start_us, deadline_us,
            SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
            SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED);
        return true;
    }
    if (!bounded_cancel_requested(request)) {
        return false;
    }
    result->cancelled_between_commands = result->io_started;
    result->cancel_before_io = !result->io_started;
    bounded_finish(
        result, start_us, deadline_us,
        SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED,
        result->io_started
            ? SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BETWEEN_AT
            : SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BEFORE_IO);
    return true;
}

static bool bounded_at_or_finish_unknown(
    sim7670_bounded_at_status_t status,
    sim7670_location_bounded_result_t *result,
    int64_t start_us,
    int64_t deadline_us)
{
    if (status == SIM7670_BOUNDED_AT_OK) {
        return true;
    }
    bounded_finish(
        result, start_us, deadline_us,
        SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
        bounded_reason_from_at(status));
    return false;
}

static bool bounded_lte_query_one(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result,
    int64_t start_us,
    int64_t deadline_us,
    sim7670_lte_report_t *report,
    sim7670_at_query_evidence_t *evidence,
    const char *command,
    const char *expected_prefix,
    char *response,
    size_t response_size,
    lte_response_parser_fn parser)
{
    if (bounded_cancel_at_boundary(
            request, result, start_us, deadline_us)) {
        return false;
    }
    evidence->attempted = true;
    const sim7670_bounded_at_status_t at_status =
        sim7670_send_at_complete_bounded(
            command, expected_prefix, deadline_us,
            request->per_command_timeout_cap_ms, response, response_size,
            result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us)) {
        return false;
    }
    evidence->response_observed = true;
    update_lte_raw(report, command, response);
    evidence->parse_valid = parser(response, report);
    if (!evidence->parse_valid) {
        bounded_finish(
            result, start_us, deadline_us,
            SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
            SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID);
        return false;
    }
    return true;
}

sim7670_location_bounded_outcome_t
sim7670_gnss_request_location_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_gnss_report_t *report,
    sim7670_location_bounded_result_t *result)
{
    sim7670_location_bounded_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_location_bounded_result_init(result);
    sim7670_gnss_report_init(report);
    if (report == NULL || !bounded_request_valid(request)) {
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        return result->outcome;
    }
#if !CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
    result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    return result->outcome;
#else
    report->driver_enabled = true;
    if (!sim7670_at_backend_is_initialized()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_UART_NOT_INITIALIZED;
        return result->outcome;
    }
    if (!sim7670_at_backend_current_task_is_allowed()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH;
        return result->outcome;
    }
    report->uart_ready = true;
    int64_t start_us = INT64_C(0);
    int64_t deadline_us = INT64_C(0);
    if (!bounded_begin(request, result, &start_us, &deadline_us)) {
        return result->outcome;
    }

    char response[AT_RESPONSE_BUFFER_SIZE];
    sim7670_bounded_at_status_t at_status =
        sim7670_send_at_complete_bounded(
            "AT", "OK", deadline_us,
            request->per_command_timeout_cap_ms, response, sizeof(response),
            result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us)) {
        return result->outcome;
    }
    report->at_ok = true;
    if (bounded_cancel_at_boundary(
            request, result, start_us, deadline_us)) {
        return result->outcome;
    }

#if CONFIG_EGOLINK_SIM7670_GNSS_POWER_ON_BEFORE_QUERY
    at_status = sim7670_send_at_complete_bounded(
        "AT+CGNSSPWR=1", "OK", deadline_us,
        request->per_command_timeout_cap_ms, response, sizeof(response),
        result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us) ||
        bounded_cancel_at_boundary(
            request, result, start_us, deadline_us)) {
        return result->outcome;
    }
#endif

    report->cgnssinfo_query.attempted = true;
    at_status = sim7670_send_at_complete_bounded(
        "AT+CGNSSINFO", "+CGNSSINFO:", deadline_us,
        request->per_command_timeout_cap_ms, response, sizeof(response),
        result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us)) {
        return result->outcome;
    }
    report->cgnssinfo_query.response_observed = true;
    gnss_parse_outcome_t parse_outcome = parse_gnss_query(
        "AT+CGNSSINFO", "+CGNSSINFO:", response, report);
    record_gnss_query_outcome(&report->cgnssinfo_query, parse_outcome);
    if (parse_outcome == GNSS_PARSE_INVALID) {
        bounded_finish(
            result, start_us, deadline_us,
            SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
            SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID);
        return result->outcome;
    }
    bool fix = parse_outcome == GNSS_PARSE_FIX;
    if (!fix) {
        if (bounded_cancel_at_boundary(
                request, result, start_us, deadline_us)) {
            return result->outcome;
        }
        report->cgpsinfo_query.attempted = true;
        at_status = sim7670_send_at_complete_bounded(
            "AT+CGPSINFO", "+CGPSINFO:", deadline_us,
            request->per_command_timeout_cap_ms, response, sizeof(response),
            result);
        if (!bounded_at_or_finish_unknown(
                at_status, result, start_us, deadline_us)) {
            return result->outcome;
        }
        report->cgpsinfo_query.response_observed = true;
        parse_outcome = parse_gnss_query(
            "AT+CGPSINFO", "+CGPSINFO:", response, report);
        record_gnss_query_outcome(&report->cgpsinfo_query, parse_outcome);
        if (parse_outcome == GNSS_PARSE_INVALID) {
            bounded_finish(
                result, start_us, deadline_us,
                SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
                SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID);
            return result->outcome;
        }
        fix = parse_outcome == GNSS_PARSE_FIX;
    }

    report->fix = fix && report->lat_valid && report->lon_valid;
    report->location_result_valid = true;
    report->no_fix_observed =
        !report->fix &&
        (report->cgnssinfo_query.no_fix_observed ||
         report->cgpsinfo_query.no_fix_observed);
    if (report->fix) {
        set_status(report, "fix", "observed");
    } else if (report->no_fix_observed) {
        set_status(report, "no_fix", "observed");
    } else {
        bounded_finish(
            result, start_us, deadline_us,
            SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
            SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID);
        return result->outcome;
    }
    if (bounded_cancel_at_boundary(
            request, result, start_us, deadline_us)) {
        return result->outcome;
    }
    bounded_finish(
        result, start_us, deadline_us,
        SIM7670_LOCATION_BOUNDED_REPORT_READY,
        SIM7670_LOCATION_BOUNDED_REASON_NONE);
    return result->outcome;
#endif
}

sim7670_location_bounded_outcome_t sim7670_gnss_power_off_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result)
{
    sim7670_location_bounded_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_location_bounded_result_init(result);
    if (!bounded_request_valid(request)) {
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        return result->outcome;
    }
#if !CONFIG_EGOLINK_SIM7670_GNSS_ENABLED
    result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
    result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    return result->outcome;
#else
    if (!sim7670_at_backend_is_initialized()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_UART_NOT_INITIALIZED;
        return result->outcome;
    }
    if (!sim7670_at_backend_current_task_is_allowed()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH;
        return result->outcome;
    }
    int64_t start_us = INT64_C(0);
    int64_t deadline_us = INT64_C(0);
    if (!bounded_begin(request, result, &start_us, &deadline_us)) {
        return result->outcome;
    }
    char response[AT_RESPONSE_BUFFER_SIZE];
    const sim7670_bounded_at_status_t at_status =
        sim7670_send_at_complete_bounded(
            "AT+CGNSSPWR=0", "OK", deadline_us,
            request->per_command_timeout_cap_ms, response, sizeof(response),
            result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us)) {
        return result->outcome;
    }
    /* A terminal OK completes cleanup even if cancellation arrives after it. */
    bounded_finish(
        result, start_us, deadline_us,
        SIM7670_LOCATION_BOUNDED_REPORT_READY,
        SIM7670_LOCATION_BOUNDED_REASON_NONE);
    return result->outcome;
#endif
}

sim7670_location_bounded_outcome_t sim7670_lte_query_status_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_lte_report_t *report,
    sim7670_location_bounded_result_t *result)
{
    sim7670_location_bounded_result_t local_result;
    if (result == NULL) {
        result = &local_result;
    }
    sim7670_location_bounded_result_init(result);
    sim7670_lte_report_init(report);
    if (report == NULL || !bounded_request_valid(request)) {
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        return result->outcome;
    }
#if !CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED
    result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
    result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    return result->outcome;
#else
    report->driver_enabled = true;
    if (!sim7670_at_backend_is_initialized()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_UART_NOT_INITIALIZED;
        return result->outcome;
    }
    if (!sim7670_at_backend_current_task_is_allowed()) {
        result->outcome = SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason =
            SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH;
        return result->outcome;
    }
    report->uart_ready = true;
    int64_t start_us = INT64_C(0);
    int64_t deadline_us = INT64_C(0);
    if (!bounded_begin(request, result, &start_us, &deadline_us)) {
        return result->outcome;
    }

    char response[AT_RESPONSE_BUFFER_SIZE];
    const sim7670_bounded_at_status_t at_status =
        sim7670_send_at_complete_bounded(
            "AT", "OK", deadline_us,
            request->per_command_timeout_cap_ms, response, sizeof(response),
            result);
    if (!bounded_at_or_finish_unknown(
            at_status, result, start_us, deadline_us)) {
        return result->outcome;
    }
    report->at_ok = true;
    update_lte_raw(report, "AT", response);

    if (!bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cpin_query, "AT+CPIN?", "+CPIN:", response,
            sizeof(response), parse_cpin) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cops_query, "AT+COPS?", "+COPS:", response,
            sizeof(response), parse_cops) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cereg_query, "AT+CEREG?", "+CEREG:", response,
            sizeof(response), parse_cereg) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cgatt_query, "AT+CGATT?", "+CGATT:", response,
            sizeof(response), parse_cgatt) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cgdcont_query, "AT+CGDCONT?", "+CGDCONT:", response,
            sizeof(response), parse_cgdcont) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cgact_query, "AT+CGACT?", "+CGACT:", response,
            sizeof(response), parse_cgact) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cgpaddr_query, "AT+CGPADDR=1", "+CGPADDR:", response,
            sizeof(response), parse_cgpaddr) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->csq_query, "AT+CSQ", "+CSQ:", response,
            sizeof(response), parse_csq) ||
        !bounded_lte_query_one(
            request, result, start_us, deadline_us, report,
            &report->cpsi_query, "AT+CPSI?", "+CPSI:", response,
            sizeof(response), parse_cpsi)) {
        return result->outcome;
    }
    classify_lte_status(report);
    if (bounded_cancel_at_boundary(
            request, result, start_us, deadline_us)) {
        return result->outcome;
    }
    bounded_finish(
        result, start_us, deadline_us,
        SIM7670_LOCATION_BOUNDED_REPORT_READY,
        SIM7670_LOCATION_BOUNDED_REASON_NONE);
    return result->outcome;
#endif
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

    report->cgnssinfo_query.attempted = true;
    const bool got_gnss_line = sim7670_send_at_complete(
        "AT+CGNSSINFO",
        "+CGNSSINFO:",
        CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
        response,
        sizeof(response));
    report->cgnssinfo_query.response_observed = got_gnss_line;
    bool fix = false;
    if (got_gnss_line) {
        const gnss_parse_outcome_t outcome = parse_gnss_query(
            "AT+CGNSSINFO", "+CGNSSINFO:", response, report);
        record_gnss_query_outcome(&report->cgnssinfo_query, outcome);
        fix = outcome == GNSS_PARSE_FIX;
    }
    if (!fix) {
        report->cgpsinfo_query.attempted = true;
        const bool got_gps_line = sim7670_send_at_complete(
            "AT+CGPSINFO",
            "+CGPSINFO:",
            CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS,
            response,
            sizeof(response));
        report->cgpsinfo_query.response_observed = got_gps_line;
        if (got_gps_line) {
            const gnss_parse_outcome_t outcome = parse_gnss_query(
                "AT+CGPSINFO", "+CGPSINFO:", response, report);
            record_gnss_query_outcome(&report->cgpsinfo_query, outcome);
            fix = outcome == GNSS_PARSE_FIX;
        }
    }

    report->fix = fix && report->lat_valid && report->lon_valid;
    report->location_result_valid =
        report->cgnssinfo_query.parse_valid ||
        report->cgpsinfo_query.parse_valid;
    report->no_fix_observed =
        !report->fix &&
        (report->cgnssinfo_query.no_fix_observed ||
         report->cgpsinfo_query.no_fix_observed);
    if (report->fix) {
        set_status(report, "fix", "observed");
    } else if (report->no_fix_observed) {
        set_status(report, "no_fix", "observed");
    } else {
        set_status(report, "query_unverified", "unverified");
    }
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

    run_lte_status_query(
        report, &report->cpin_query, "AT+CPIN?", "+CPIN:", response,
        sizeof(response), parse_cpin);
    run_lte_status_query(
        report, &report->cops_query, "AT+COPS?", "+COPS:", response,
        sizeof(response), parse_cops);
    run_lte_status_query(
        report, &report->cereg_query, "AT+CEREG?", "+CEREG:", response,
        sizeof(response), parse_cereg);
    run_lte_status_query(
        report, &report->cgatt_query, "AT+CGATT?", "+CGATT:", response,
        sizeof(response), parse_cgatt);
    run_lte_status_query(
        report, &report->cgdcont_query, "AT+CGDCONT?", "+CGDCONT:",
        response, sizeof(response), parse_cgdcont);
    run_lte_status_query(
        report, &report->cgact_query, "AT+CGACT?", "+CGACT:", response,
        sizeof(response), parse_cgact);
    run_lte_status_query(
        report, &report->cgpaddr_query, "AT+CGPADDR=1", "+CGPADDR:",
        response, sizeof(response), parse_cgpaddr);
    run_lte_status_query(
        report, &report->csq_query, "AT+CSQ", "+CSQ:", response,
        sizeof(response), parse_csq);
    run_lte_status_query(
        report, &report->cpsi_query, "AT+CPSI?", "+CPSI:", response,
        sizeof(response), parse_cpsi);
    classify_lte_status(report);
    return true;
#endif
}

static bool sim7670_lte_http_post_payload(
    const char *url,
    const char *bearer_token,
    const char *payload,
    const char *content_type,
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
    (void)content_type;
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
    if (content_type == NULL || content_type[0] == '\0') {
        set_lte_http_reason(result, "LTE_HTTP_CONTENT_MISSING");
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

    written = snprintf(command, sizeof(command), "AT+HTTPPARA=\"CONTENT\",\"%s\"", content_type);
    if (written < 0 || (size_t)written >= sizeof(command)) {
        set_lte_http_reason(result, "LTE_HTTP_CONTENT_TOO_LONG");
        (void)sim7670_send_at("AT+HTTPTERM", "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response));
        return false;
    }
    if (!sim7670_send_at(command, "OK", CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS, response, sizeof(response))) {
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
            SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
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

bool sim7670_lte_http_post_json(
    const char *url,
    const char *bearer_token,
    const char *payload,
    sim7670_lte_http_probe_result_t *result)
{
    return sim7670_lte_http_post_payload(url, bearer_token, payload, "application/json", result);
}

bool sim7670_lte_http_post_raw(
    const char *url,
    const char *bearer_token,
    const char *payload,
    const char *content_type,
    sim7670_lte_http_probe_result_t *result)
{
    return sim7670_lte_http_post_payload(url, bearer_token, payload, content_type, result);
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
            SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
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

bool sim7670_lte_http_get_raw(
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
            SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS,
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
    read_body_ok = sim7670_lte_http_read_raw_body(
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
bool sim7670_at_backend_is_initialized(void)
{
    return false;
}

bool sim7670_at_backend_current_task_is_exclusive_owner(void)
{
    return false;
}

esp_err_t sim7670_at_backend_init_exclusive_current_task(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t sim7670_gnss_init(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

bool sim7670_gnss_request_location(sim7670_gnss_report_t *report)
{
    sim7670_gnss_report_init(report);
    return false;
}

sim7670_location_bounded_outcome_t
sim7670_gnss_request_location_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_gnss_report_t *report,
    sim7670_location_bounded_result_t *result)
{
    (void)request;
    sim7670_gnss_report_init(report);
    if (result != NULL) {
        sim7670_location_bounded_result_init(result);
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    }
    return SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
}

sim7670_location_bounded_outcome_t sim7670_gnss_power_off_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result)
{
    (void)request;
    if (result != NULL) {
        sim7670_location_bounded_result_init(result);
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    }
    return SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
}

bool sim7670_lte_query_status(sim7670_lte_report_t *report)
{
    sim7670_lte_report_init(report);
    return false;
}

sim7670_location_bounded_outcome_t sim7670_lte_query_status_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_lte_report_t *report,
    sim7670_location_bounded_result_t *result)
{
    (void)request;
    sim7670_lte_report_init(report);
    if (result != NULL) {
        sim7670_location_bounded_result_init(result);
        result->outcome =
            SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
        result->reason = SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED;
    }
    return SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE;
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

bool sim7670_lte_http_post_raw(
    const char *url,
    const char *bearer_token,
    const char *payload,
    const char *content_type,
    sim7670_lte_http_probe_result_t *result)
{
    (void)url;
    (void)bearer_token;
    (void)payload;
    (void)content_type;
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

bool sim7670_lte_http_get_raw(
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
