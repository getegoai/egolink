#ifndef SIM7670_CELLULAR_CALL_H
#define SIM7670_CELLULAR_CALL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SIM7670_CALL_PHONE_NUMBER_MAX_LEN 32
#define SIM7670_CALL_DEFAULT_DIAL_TIMEOUT_MS 45000
#define SIM7670_CALL_MAX_DIAL_DURATION_US (60LL * 1000LL * 1000LL)

typedef enum {
    SIM7670_CALL_STATE_IDLE = 0,
    SIM7670_CALL_STATE_DIALING,
    SIM7670_CALL_STATE_ALERTING,
    SIM7670_CALL_STATE_INCOMING,
    SIM7670_CALL_STATE_ACTIVE,
    SIM7670_CALL_STATE_DISCONNECTING,
    SIM7670_CALL_STATE_ERROR
} sim7670_call_state_t;

typedef enum {
    SIM7670_CALL_DIR_NONE = 0,
    SIM7670_CALL_DIR_OUTGOING,
    SIM7670_CALL_DIR_INCOMING
} sim7670_call_direction_t;

typedef enum {
    SIM7670_CALL_DISCONNECT_NONE = 0,
    SIM7670_CALL_DISCONNECT_LOCAL_HANGUP,
    SIM7670_CALL_DISCONNECT_REMOTE_HANGUP,
    SIM7670_CALL_DISCONNECT_BUSY,
    SIM7670_CALL_DISCONNECT_NO_ANSWER,
    SIM7670_CALL_DISCONNECT_NETWORK_REJECT,
    SIM7670_CALL_DISCONNECT_TIMEOUT,
    SIM7670_CALL_DISCONNECT_ERROR
} sim7670_call_disconnect_reason_t;

typedef struct {
    sim7670_call_state_t state;
    sim7670_call_direction_t direction;
    char phone_number[SIM7670_CALL_PHONE_NUMBER_MAX_LEN];
    uint32_t call_id;
    int64_t state_start_time_us;
    int64_t call_connected_time_us;
    uint32_t call_duration_sec;
    sim7670_call_disconnect_reason_t last_disconnect_reason;
} sim7670_call_status_t;

/**
 * @brief AT command transport send function pointer.
 * @param cmd Null-terminated AT command string.
 * @param resp Output buffer for response (can be NULL if response not needed).
 * @param resp_size Capacity of response buffer.
 * @param timeout_ms Execution deadline in milliseconds.
 * @return ESP_OK on command success (OK received), or error code.
 */
typedef esp_err_t (*sim7670_call_at_send_fn)(
    void *user_ctx,
    const char *cmd,
    char *resp,
    size_t resp_size,
    uint32_t timeout_ms
);

/**
 * @brief Monotonic clock provider function pointer (returns microseconds).
 */
typedef int64_t (*sim7670_call_clock_fn)(void);

typedef struct {
    sim7670_call_at_send_fn at_send;
    void *user_ctx;
    sim7670_call_clock_fn clock_fn;
} sim7670_cellular_call_config_t;

typedef struct sim7670_cellular_call_ctx {
    sim7670_call_status_t status;
    sim7670_call_at_send_fn at_send;
    void *user_ctx;
    sim7670_call_clock_fn clock_fn;
    bool initialized;
} sim7670_cellular_call_ctx_t;

/**
 * @brief Initialize the cellular call manager context.
 */
esp_err_t sim7670_cellular_call_init(
    sim7670_cellular_call_ctx_t *ctx,
    const sim7670_cellular_call_config_t *config
);

/**
 * @brief Configure call parameters (e.g. caller ID presentation +CLIP=1).
 */
esp_err_t sim7670_cellular_call_configure(
    sim7670_cellular_call_ctx_t *ctx,
    uint8_t volume_percent
);

/**
 * @brief Dial an outgoing cellular voice call (ATD<number>;).
 * @param ctx Call context.
 * @param phone_number Target phone number string.
 * @return ESP_OK if dial command accepted by modem.
 */
esp_err_t sim7670_cellular_call_dial(
    sim7670_cellular_call_ctx_t *ctx,
    const char *phone_number
);

/**
 * @brief Answer an incoming voice call (ATA).
 */
esp_err_t sim7670_cellular_call_answer(
    sim7670_cellular_call_ctx_t *ctx
);

/**
 * @brief Hang up an active, dialing, or incoming voice call (ATH).
 */
esp_err_t sim7670_cellular_call_hangup(
    sim7670_cellular_call_ctx_t *ctx
);

/**
 * @brief Poll call status from modem via AT+CLCC.
 */
esp_err_t sim7670_cellular_call_poll_status(
    sim7670_cellular_call_ctx_t *ctx,
    sim7670_call_status_t *out_status
);

/**
 * @brief Parse and process unsolicited result code (URC) line.
 * @param ctx Call context.
 * @param urc_line Single line received from modem.
 * @return ESP_OK if URC was recognized and processed.
 */
esp_err_t sim7670_cellular_call_handle_urc(
    sim7670_cellular_call_ctx_t *ctx,
    const char *urc_line
);

/**
 * @brief Get snapshot of current call status.
 */
esp_err_t sim7670_cellular_call_get_status(
    const sim7670_cellular_call_ctx_t *ctx,
    sim7670_call_status_t *out_status
);

/**
 * @brief String representation of call state.
 */
const char *sim7670_call_state_to_str(sim7670_call_state_t state);

/**
 * @brief String representation of disconnect reason.
 */
const char *sim7670_call_disconnect_reason_to_str(
    sim7670_call_disconnect_reason_t reason
);

#ifdef __cplusplus
}
#endif

#endif /* SIM7670_CELLULAR_CALL_H */
