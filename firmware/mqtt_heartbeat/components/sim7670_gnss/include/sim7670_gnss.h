#pragma once

#include <stdbool.h>
#include <stddef.h>

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
} sim7670_lte_report_t;

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

esp_err_t sim7670_gnss_init(void);
bool sim7670_gnss_request_location(sim7670_gnss_report_t *report);
void sim7670_gnss_report_init(sim7670_gnss_report_t *report);
const char *sim7670_gnss_backend_name(void);
bool sim7670_lte_query_status(sim7670_lte_report_t *report);
void sim7670_lte_report_init(sim7670_lte_report_t *report);
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
