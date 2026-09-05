#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SIM7670_GNSS_RAW_RESPONSE_MAX 240
#define SIM7670_GNSS_RAW_COMMAND_MAX 24
#define SIM7670_GNSS_STATUS_MAX 32
#define SIM7670_GNSS_UTC_MAX 20
#define SIM7670_LTE_RAW_RESPONSE_MAX 240
#define SIM7670_LTE_RAW_COMMAND_MAX 24
#define SIM7670_LTE_STATUS_MAX 32
#define SIM7670_LTE_OPERATOR_MAX 32
#define SIM7670_LTE_RAT_MAX 16
#define SIM7670_LTE_ID_MAX 24
#define SIM7670_LTE_IP_MAX 48
#define SIM7670_LTE_HTTP_REASON_MAX 48
#define SIM7670_LTE_HTTP_RAW_COMMAND_MAX 48
#define SIM7670_LTE_HTTP_RAW_RESPONSE_MAX 240
#define SIM7670_LTE_HTTP_EXACT_PAYLOAD_MAX_BYTES 4096U
#define SIM7670_LTE_HTTP_EXACT_RESPONSE_MAX_BYTES 8192U
#define SIM7670_LTE_HTTP_EXACT_CALLER_RESPONSE_CAPACITY_MAX_BYTES 8192U
#define SIM7670_LTE_HTTP_EXACT_URL_MAX_BYTES 320U
#define SIM7670_LTE_HTTP_EXACT_BEARER_MAX_BYTES 160U
#define SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS UINT32_C(60000)
#define SIM7670_LOCATION_BOUNDED_TIMEOUT_MAX_MS UINT32_C(120000)
#define SIM7670_LOCATION_BOUNDED_COMMAND_CAP_MAX_MS UINT32_C(30000)

/*
 * Evidence for one bounded AT query. `response_observed` means the expected
 * response line and a successful terminal result were both received;
 * `parse_valid` means that response matched the command's accepted grammar.
 * A false value is absence of evidence, not evidence for a negative state.
 */
typedef struct {
    bool attempted;
    bool response_observed;
    bool parse_valid;
} sim7670_at_query_evidence_t;

typedef struct {
    bool attempted;
    bool response_observed;
    bool parse_valid;
    bool fix_observed;
    bool no_fix_observed;
} sim7670_gnss_query_evidence_t;

typedef struct {
    bool driver_enabled;
    bool uart_ready;
    bool at_ok;
    bool fix;
    bool lat_valid;
    bool lon_valid;
    bool altitude_valid;
    bool speed_valid;
    bool course_valid;
    bool pdop_valid;
    bool hdop_valid;
    bool vdop_valid;
    bool satellites_valid;
    double lat;
    double lon;
    double altitude_m;
    double speed_mps;
    double course_deg;
    double pdop;
    double hdop;
    double vdop;
    int satellites;
    char gnss_state[SIM7670_GNSS_STATUS_MAX];
    char source_status[SIM7670_GNSS_STATUS_MAX];
    char raw_command[SIM7670_GNSS_RAW_COMMAND_MAX];
    char raw_response[SIM7670_GNSS_RAW_RESPONSE_MAX];
    char utc_date[SIM7670_GNSS_UTC_MAX];
    char utc_time[SIM7670_GNSS_UTC_MAX];
    /* Additive evidence tail; all legacy fields above retain their meaning. */
    bool location_result_valid;
    /* Terminal aggregate: true only when no fix won and a query proved no-fix. */
    bool no_fix_observed;
    sim7670_gnss_query_evidence_t cgnssinfo_query;
    sim7670_gnss_query_evidence_t cgpsinfo_query;
} sim7670_gnss_report_t;

typedef struct {
    bool driver_enabled;
    bool uart_ready;
    bool at_ok;
    bool sim_ready;
    bool registered;
    bool attached;
    bool pdp_active;
    bool ip_valid;
    bool rssi_valid;
    bool rsrp_valid;
    bool rsrq_valid;
    bool sinr_valid;
    int rssi;
    int rsrp;
    int rsrq;
    int sinr;
    char sim_state[SIM7670_LTE_STATUS_MAX];
    char registration_state[SIM7670_LTE_STATUS_MAX];
    char pdp_state[SIM7670_LTE_STATUS_MAX];
    char apn_state[SIM7670_LTE_STATUS_MAX];
    char operator_name[SIM7670_LTE_OPERATOR_MAX];
    char rat[SIM7670_LTE_RAT_MAX];
    char mcc[SIM7670_LTE_ID_MAX];
    char mnc[SIM7670_LTE_ID_MAX];
    char tac[SIM7670_LTE_ID_MAX];
    char cell_id[SIM7670_LTE_ID_MAX];
    char assigned_ip[SIM7670_LTE_IP_MAX];
    char reason_code[SIM7670_LTE_STATUS_MAX];
    char raw_command[SIM7670_LTE_RAW_COMMAND_MAX];
    char raw_response[SIM7670_LTE_RAW_RESPONSE_MAX];
    /* Additive evidence tail; false content bits need matching parse proof. */
    bool cell_identity_valid;
    sim7670_at_query_evidence_t cpin_query;
    sim7670_at_query_evidence_t cops_query;
    sim7670_at_query_evidence_t cereg_query;
    sim7670_at_query_evidence_t cgatt_query;
    sim7670_at_query_evidence_t cgdcont_query;
    sim7670_at_query_evidence_t cgact_query;
    sim7670_at_query_evidence_t cgpaddr_query;
    sim7670_at_query_evidence_t csq_query;
    sim7670_at_query_evidence_t cpsi_query;
} sim7670_lte_report_t;

/*
 * Additive request-wide bounded sensor-query boundary. Legacy GNSS/LTE entry
 * points remain unchanged. Cancellation is cooperative and sampled only at
 * reviewed boundaries between AT commands; an AT command already in progress
 * is never represented as hard-cancelled. The per-command cap bounds that
 * latency inside the request-wide deadline.
 *
 * This is bounded software accounting, not hard real-time preemption. Mutex
 * and UART read waits are rounded down to whole ticks; TX submission is
 * non-blocking. Synchronous local driver primitives are checked immediately
 * after return. If scheduling or a platform call returns after a deadline, the
 * result is OUTCOME_UNKNOWN and never REPORT_READY.
 */
typedef bool (*sim7670_location_cancel_probe_fn)(
    void *context,
    uint32_t operation_token);

typedef struct {
    uint32_t timeout_ms;
    uint32_t per_command_timeout_cap_ms;
    sim7670_location_cancel_probe_fn cancel_requested;
    void *cancel_context;
    uint32_t operation_token;
} sim7670_location_bounded_request_t;

typedef enum {
    SIM7670_LOCATION_BOUNDED_REPORT_READY = 0,
    SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE,
    SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED,
    SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN,
} sim7670_location_bounded_outcome_t;

typedef enum {
    SIM7670_LOCATION_BOUNDED_REASON_NONE = 0,
    SIM7670_LOCATION_BOUNDED_REASON_INVALID_ARGUMENT,
    SIM7670_LOCATION_BOUNDED_REASON_DRIVER_DISABLED,
    SIM7670_LOCATION_BOUNDED_REASON_UART_NOT_INITIALIZED,
    SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BEFORE_IO,
    SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BETWEEN_AT,
    SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED,
    SIM7670_LOCATION_BOUNDED_REASON_MODEM_OWNER_BUSY,
    SIM7670_LOCATION_BOUNDED_REASON_TX_INCOMPLETE,
    SIM7670_LOCATION_BOUNDED_REASON_AT_RESPONSE_TIMEOUT,
    SIM7670_LOCATION_BOUNDED_REASON_AT_IO_ERROR,
    SIM7670_LOCATION_BOUNDED_REASON_AT_TERMINAL_ERROR,
    SIM7670_LOCATION_BOUNDED_REASON_RESPONSE_TRUNCATED,
    SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID,
    /* Appended to preserve every previously published local reason value. */
    SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH,
} sim7670_location_bounded_reason_t;

/* No command text, response bytes, coordinate, cell identity or credential. */
typedef struct {
    sim7670_location_bounded_outcome_t outcome;
    sim7670_location_bounded_reason_t reason;
    bool io_started;
    bool cancel_before_io;
    bool cancelled_between_commands;
    bool partial_or_unknown;
    uint16_t commands_attempted;
    uint16_t commands_tx_complete;
    uint16_t commands_completed;
    uint64_t elapsed_ms;
} sim7670_location_bounded_result_t;

typedef struct {
    bool driver_enabled;
    bool uart_ready;
    bool at_ok;
    bool http_init_ok;
    bool http_url_ok;
    bool http_content_ok;
    bool http_header_ok;
    bool http_data_ok;
    bool http_action_ok;
    bool http_read_ok;
    bool status_code_valid;
    bool data_len_valid;
    bool action_elapsed_ms_valid;
    int status_code;
    int data_len;
    int action_elapsed_ms;
    char reason_code[SIM7670_LTE_HTTP_REASON_MAX];
    char raw_command[SIM7670_LTE_HTTP_RAW_COMMAND_MAX];
    char raw_response[SIM7670_LTE_HTTP_RAW_RESPONSE_MAX];
} sim7670_lte_http_probe_result_t;

/*
 * Additive exact-byte HTTP boundary for durable P0 delivery. It leaves the
 * legacy NUL-terminated probe APIs unchanged. payload and response_body are
 * explicit byte ranges: embedded NUL bytes are not terminators. Caller
 * response storage and a complete exact body are both bounded by 8,192
 * caller-owned bytes. Any future UART implementation must reject a larger
 * declared body before HTTPREAD; the parser never completes a truncated body.
 *
 * Only HTTPS URLs are accepted. The real exact entry point deliberately
 * returns TLS_PROFILE_UNVERIFIED before UART initialization, bearer setup or
 * payload transmission until OPS-004 supplies and reviews actual CA,
 * hostname/SNI and clock verification. There is no caller boolean that can
 * bypass this fail-closed boundary. Disabled/error returns clear the bounded
 * caller response range before returning. The existing legacy probe APIs are
 * not strengthened or enabled by this additive function.
 */
typedef enum {
    SIM7670_LTE_HTTP_EXACT_HTTP_RESPONSE = 0,
    SIM7670_LTE_HTTP_EXACT_DRIVER_DISABLED,
    SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT,
    SIM7670_LTE_HTTP_EXACT_INVALID_CONFIG,
    SIM7670_LTE_HTTP_EXACT_UART_INIT_FAILED,
    SIM7670_LTE_HTTP_EXACT_AT_FAILED,
    SIM7670_LTE_HTTP_EXACT_SETUP_FAILED,
    SIM7670_LTE_HTTP_EXACT_PAYLOAD_TOO_LARGE,
    SIM7670_LTE_HTTP_EXACT_PAYLOAD_WRITE_FAILED,
    SIM7670_LTE_HTTP_EXACT_ACTION_TIMEOUT,
    SIM7670_LTE_HTTP_EXACT_ACTION_INVALID,
    SIM7670_LTE_HTTP_EXACT_RESPONSE_TOO_LARGE,
    SIM7670_LTE_HTTP_EXACT_READ_TIMEOUT,
    SIM7670_LTE_HTTP_EXACT_READ_INVALID,
    SIM7670_LTE_HTTP_EXACT_IO_FAILED,
    SIM7670_LTE_HTTP_EXACT_TLS_PROFILE_UNVERIFIED,
} sim7670_lte_http_exact_status_t;

/* Borrowed cooperative probe; it is not permission to force-stop modem I/O. */
typedef bool (*sim7670_lte_http_exact_cancel_probe_fn)(
    void *context,
    uint32_t transfer_generation);

typedef struct {
    const char *url;
    const char *bearer_token;
    const uint8_t *payload;
    size_t payload_length;
    uint8_t *response_body;
    size_t response_capacity;
    uint32_t command_timeout_ms;
    uint32_t data_timeout_ms;
    uint32_t action_timeout_ms;
    uint32_t read_timeout_ms;
    sim7670_lte_http_exact_cancel_probe_fn cancel_requested;
    void *cancel_context;
    uint32_t transfer_generation;
} sim7670_lte_http_exact_request_t;

/* No URL, credential, payload or response bytes are exposed here. */
typedef struct {
    sim7670_lte_http_exact_status_t status;
    uint16_t http_status_code;
    size_t declared_response_length;
    size_t response_length;
    size_t payload_bytes_written;
    bool payload_write_complete;
    bool response_complete;
} sim7670_lte_http_exact_result_t;

esp_err_t sim7670_gnss_init(void);
/*
 * Claims the AT backend for the current boot-long task. The claim must happen
 * before any legacy initializer installs or configures the UART. Repeating it
 * from the same task is idempotent; a different task or a pre-existing legacy
 * backend fails closed with ESP_ERR_INVALID_STATE. There is deliberately no
 * task-handoff or deinit API in this slice.
 */
esp_err_t sim7670_at_backend_init_exclusive_current_task(void);
/* Read-only; bounded queries never initialize or reconfigure UART themselves. */
bool sim7670_at_backend_is_initialized(void);
/* True only for the exact TaskHandle_t that made the exclusive claim. */
bool sim7670_at_backend_current_task_is_exclusive_owner(void);
bool sim7670_gnss_request_location(sim7670_gnss_report_t *report);
sim7670_location_bounded_outcome_t
sim7670_gnss_request_location_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_gnss_report_t *report,
    sim7670_location_bounded_result_t *result);
/*
 * Sends one bounded AT+CGNSSPWR=0 transaction. REPORT_READY means a complete
 * terminal OK was observed for that command; it is command acceptance
 * evidence, not proof of antenna/RF power. Product owners must use a
 * non-cancelling probe for compensating cleanup and enter recovery when the
 * result is anything other than REPORT_READY.
 */
sim7670_location_bounded_outcome_t sim7670_gnss_power_off_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_location_bounded_result_t *result);
void sim7670_gnss_report_init(sim7670_gnss_report_t *report);
const char *sim7670_gnss_backend_name(void);
bool sim7670_lte_query_status(sim7670_lte_report_t *report);
sim7670_location_bounded_outcome_t sim7670_lte_query_status_bounded(
    const sim7670_location_bounded_request_t *request,
    sim7670_lte_report_t *report,
    sim7670_location_bounded_result_t *result);
void sim7670_lte_report_init(sim7670_lte_report_t *report);
void sim7670_location_bounded_result_init(
    sim7670_location_bounded_result_t *result);
const char *sim7670_lte_backend_name(void);
bool sim7670_lte_http_post_json(
    const char *url,
    const char *bearer_token,
    const char *payload,
    sim7670_lte_http_probe_result_t *result);
bool sim7670_lte_http_post_raw(
    const char *url,
    const char *bearer_token,
    const char *payload,
    const char *content_type,
    sim7670_lte_http_probe_result_t *result);
sim7670_lte_http_exact_status_t sim7670_lte_http_post_bytes_exact(
    const sim7670_lte_http_exact_request_t *request,
    sim7670_lte_http_exact_result_t *result);
void sim7670_lte_http_exact_result_init(
    sim7670_lte_http_exact_result_t *result);
/* Pure validator; requires one exact lowercase DNS host-only HTTPS origin. */
int sim7670_http_exact_https_origin_matches_dns_host(
    const char *origin,
    const char *expected_host);
bool sim7670_lte_http_get_json(
    const char *url,
    const char *bearer_token,
    char *response_body,
    size_t response_body_size,
    sim7670_lte_http_probe_result_t *result);
bool sim7670_lte_http_get_raw(
    const char *url,
    const char *bearer_token,
    char *response_body,
    size_t response_body_size,
    sim7670_lte_http_probe_result_t *result);
void sim7670_lte_http_probe_result_init(sim7670_lte_http_probe_result_t *result);
const char *sim7670_lte_http_backend_name(void);

#ifdef __cplusplus
}
#endif
