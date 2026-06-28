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

esp_err_t sim7670_gnss_init(void);
bool sim7670_gnss_request_location(sim7670_gnss_report_t *report);
void sim7670_gnss_report_init(sim7670_gnss_report_t *report);
const char *sim7670_gnss_backend_name(void);

#ifdef __cplusplus
}
#endif
