#include "sim7670_cellular_call.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int64_t default_clock(void)
{
    /* Fallback monotonic counter in microseconds if none supplied */
    static int64_t dummy_clock = 1000000;
    dummy_clock += 10000;
    return dummy_clock;
}

static int64_t get_time_us(const sim7670_cellular_call_ctx_t *ctx)
{
    if (ctx != NULL && ctx->clock_fn != NULL) {
        return ctx->clock_fn();
    }
    return default_clock();
}

static bool is_valid_phone_number(const char *number)
{
    if (number == NULL) {
        return false;
    }
    size_t len = strlen(number);
    if (len < 3 || len >= SIM7670_CALL_PHONE_NUMBER_MAX_LEN) {
        return false;
    }
    size_t i = 0;
    if (number[0] == '+') {
        i = 1;
    }
    for (; i < len; ++i) {
        if (!isdigit((unsigned char)number[i])) {
            return false;
        }
    }
    return true;
}

static void copy_string(char *dest, size_t dest_size, const char *src)
{
    if (dest == NULL || dest_size == 0) {
        return;
    }
    if (src == NULL) {
        dest[0] = '\0';
        return;
    }
    size_t src_len = strlen(src);
    size_t copy_len = src_len < (dest_size - 1) ? src_len : (dest_size - 1);
    memcpy(dest, src, copy_len);
    dest[copy_len] = '\0';
}

esp_err_t sim7670_cellular_call_init(
    sim7670_cellular_call_ctx_t *ctx,
    const sim7670_cellular_call_config_t *config)
{
    if (ctx == NULL || config == NULL || config->at_send == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(ctx, 0, sizeof(*ctx));
    ctx->at_send = config->at_send;
    ctx->user_ctx = config->user_ctx;
    ctx->clock_fn = config->clock_fn != NULL ? config->clock_fn : default_clock;
    ctx->status.state = SIM7670_CALL_STATE_IDLE;
    ctx->status.direction = SIM7670_CALL_DIR_NONE;
    ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_NONE;
    ctx->initialized = true;
    return ESP_OK;
}

esp_err_t sim7670_cellular_call_configure(
    sim7670_cellular_call_ctx_t *ctx,
    uint8_t volume_percent)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    /* 1. Enable Verbose Error Reporting FIRST so any subsequent error is informative */
    (void)ctx->at_send(ctx->user_ctx, "AT+CMEE=2", NULL, 0, 2000);

    /* 2. Hardware and network diagnostic probes */
    (void)ctx->at_send(ctx->user_ctx, "ATI", NULL, 0, 2000);
    (void)ctx->at_send(ctx->user_ctx, "AT+CGMR", NULL, 0, 2000);
    (void)ctx->at_send(ctx->user_ctx, "AT+CPIN?", NULL, 0, 2000);
    (void)ctx->at_send(ctx->user_ctx, "AT+COPS?", NULL, 0, 2000);
    (void)ctx->at_send(ctx->user_ctx, "AT+CPSI?", NULL, 0, 2000);
    (void)ctx->at_send(ctx->user_ctx, "AT+CREG?", NULL, 0, 2000);

    /* 3. Hangup control / voice mode */
    (void)ctx->at_send(ctx->user_ctx, "AT+CVHU=0", NULL, 0, 2000);

    /* 4. Enable VoLTE for LTE carrier voice calling */
    (void)ctx->at_send(ctx->user_ctx, "AT+CEVOLTE=1", NULL, 0, 2000);

    /* 5. Enable Call Listing */
    (void)ctx->at_send(ctx->user_ctx, "AT+CLCC=1", NULL, 0, 2000);

    /* 6. Enable Calling Line Identification Presentation */
    (void)ctx->at_send(ctx->user_ctx, "AT+CLIP=1", NULL, 0, 2000);

    /* 7. Enable Connected Line Identification */
    (void)ctx->at_send(ctx->user_ctx, "AT+COLP=1", NULL, 0, 2000);

    /* 8. Best-effort volume level setting (may not be supported on all Cat-1 firmware) */
    char cmd[32];
    uint8_t vol = volume_percent > 100 ? 100 : volume_percent;
    (void)snprintf(cmd, sizeof(cmd), "AT+CLVL=%u", (unsigned int)vol);
    (void)ctx->at_send(ctx->user_ctx, cmd, NULL, 0, 2000);

    return ESP_OK;
}

esp_err_t sim7670_cellular_call_dial(
    sim7670_cellular_call_ctx_t *ctx,
    const char *phone_number)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!is_valid_phone_number(phone_number)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (ctx->status.state != SIM7670_CALL_STATE_IDLE) {
        return ESP_ERR_INVALID_STATE;
    }

    char cmd[64];
    (void)snprintf(cmd, sizeof(cmd), "ATD%s;", phone_number);
    esp_err_t err = ctx->at_send(ctx->user_ctx, cmd, NULL, 0, 10000);
    if (err != ESP_OK) {
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_ERROR;
        return err;
    }

    int64_t now = get_time_us(ctx);
    ctx->status.state = SIM7670_CALL_STATE_DIALING;
    ctx->status.direction = SIM7670_CALL_DIR_OUTGOING;
    copy_string(ctx->status.phone_number, sizeof(ctx->status.phone_number), phone_number);
    ctx->status.state_start_time_us = now;
    ctx->status.call_connected_time_us = 0;
    ctx->status.call_duration_sec = 0;
    ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_NONE;
    return ESP_OK;
}

esp_err_t sim7670_cellular_call_answer(sim7670_cellular_call_ctx_t *ctx)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    if (ctx->status.state != SIM7670_CALL_STATE_INCOMING) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = ctx->at_send(ctx->user_ctx, "ATA", NULL, 0, 5000);
    if (err != ESP_OK) {
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_ERROR;
        return err;
    }

    int64_t now = get_time_us(ctx);
    ctx->status.state = SIM7670_CALL_STATE_ACTIVE;
    ctx->status.call_connected_time_us = now;
    return ESP_OK;
}

esp_err_t sim7670_cellular_call_hangup(sim7670_cellular_call_ctx_t *ctx)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    if (ctx->status.state == SIM7670_CALL_STATE_IDLE) {
        return ESP_OK;
    }

    ctx->status.state = SIM7670_CALL_STATE_DISCONNECTING;
    (void)ctx->at_send(ctx->user_ctx, "ATH", NULL, 0, 5000);

    int64_t now = get_time_us(ctx);
    if (ctx->status.call_connected_time_us > 0 && now >= ctx->status.call_connected_time_us) {
        ctx->status.call_duration_sec = (uint32_t)((now - ctx->status.call_connected_time_us) / 1000000LL);
    }
    ctx->status.state = SIM7670_CALL_STATE_IDLE;
    ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_LOCAL_HANGUP;
    return ESP_OK;
}

esp_err_t sim7670_cellular_call_poll_status(
    sim7670_cellular_call_ctx_t *ctx,
    sim7670_call_status_t *out_status)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    int64_t now = get_time_us(ctx);

    /* Watchdog for dialing timeout */
    if ((ctx->status.state == SIM7670_CALL_STATE_DIALING || ctx->status.state == SIM7670_CALL_STATE_ALERTING) &&
        (now - ctx->status.state_start_time_us) > SIM7670_CALL_MAX_DIAL_DURATION_US) {
        (void)ctx->at_send(ctx->user_ctx, "ATH", NULL, 0, 2000);
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_TIMEOUT;
        if (out_status != NULL) {
            *out_status = ctx->status;
        }
        return ESP_OK;
    }

    char resp[256];
    memset(resp, 0, sizeof(resp));
    esp_err_t err = ctx->at_send(ctx->user_ctx, "AT+CLCC", resp, sizeof(resp) - 1, 3000);
    if (err != ESP_OK) {
        if (out_status != NULL) {
            *out_status = ctx->status;
        }
        return err;
    }

    /* Parse +CLCC: <id>,<dir>,<stat>,<mode>,<mpty>[,<number>,<type>] */
    const char *clcc = strstr(resp, "+CLCC:");
    if (clcc == NULL) {
        /* No active calls listed */
        if (ctx->status.state != SIM7670_CALL_STATE_IDLE) {
            if (ctx->status.call_connected_time_us > 0 && now >= ctx->status.call_connected_time_us) {
                ctx->status.call_duration_sec = (uint32_t)((now - ctx->status.call_connected_time_us) / 1000000LL);
            }
            ctx->status.state = SIM7670_CALL_STATE_IDLE;
            if (ctx->status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_NONE) {
                ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_REMOTE_HANGUP;
            }
        }
    } else {
        int call_id = 0;
        int dir = 0;
        int stat = 0;
        int mode = 0;
        int mpty = 0;
        char num[SIM7670_CALL_PHONE_NUMBER_MAX_LEN] = {0};
        int parsed = sscanf(
            clcc,
            "+CLCC: %d,%d,%d,%d,%d,\"%31[^\"]\"",
            &call_id, &dir, &stat, &mode, &mpty, num
        );
        if (parsed >= 3) {
            ctx->status.call_id = (uint32_t)call_id;
            ctx->status.direction = (dir == 0) ? SIM7670_CALL_DIR_OUTGOING : SIM7670_CALL_DIR_INCOMING;
            if (num[0] != '\0') {
                copy_string(ctx->status.phone_number, sizeof(ctx->status.phone_number), num);
            }
            switch (stat) {
                case 0: /* Active */
                    if (ctx->status.state != SIM7670_CALL_STATE_ACTIVE) {
                        ctx->status.state = SIM7670_CALL_STATE_ACTIVE;
                        ctx->status.call_connected_time_us = now;
                    } else if (ctx->status.call_connected_time_us > 0 && now >= ctx->status.call_connected_time_us) {
                        ctx->status.call_duration_sec = (uint32_t)((now - ctx->status.call_connected_time_us) / 1000000LL);
                    }
                    break;
                case 2: /* Dialing (MO) */
                    ctx->status.state = SIM7670_CALL_STATE_DIALING;
                    break;
                case 3: /* Alerting (MO) */
                    ctx->status.state = SIM7670_CALL_STATE_ALERTING;
                    break;
                case 4: /* Incoming (MT) */
                    ctx->status.state = SIM7670_CALL_STATE_INCOMING;
                    break;
                case 6: /* Disconnected */
                    ctx->status.state = SIM7670_CALL_STATE_IDLE;
                    ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_REMOTE_HANGUP;
                    break;
                default:
                    break;
            }
        }
    }

    if (out_status != NULL) {
        *out_status = ctx->status;
    }
    return ESP_OK;
}

esp_err_t sim7670_cellular_call_handle_urc(
    sim7670_cellular_call_ctx_t *ctx,
    const char *urc_line)
{
    if (ctx == NULL || !ctx->initialized || urc_line == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    int64_t now = get_time_us(ctx);

    if (strstr(urc_line, "RING") != NULL) {
        if (ctx->status.state == SIM7670_CALL_STATE_IDLE) {
            ctx->status.state = SIM7670_CALL_STATE_INCOMING;
            ctx->status.direction = SIM7670_CALL_DIR_INCOMING;
            ctx->status.state_start_time_us = now;
            ctx->status.call_connected_time_us = 0;
            ctx->status.call_duration_sec = 0;
            ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_NONE;
        }
        return ESP_OK;
    }

    if (strstr(urc_line, "+CLIP:") != NULL) {
        /* Example: +CLIP: "13800138000",129,"",0,"",0 */
        const char *quote1 = strchr(urc_line, '"');
        if (quote1 != NULL) {
            const char *quote2 = strchr(quote1 + 1, '"');
            if (quote2 != NULL) {
                size_t len = (size_t)(quote2 - (quote1 + 1));
                if (len >= sizeof(ctx->status.phone_number)) {
                    len = sizeof(ctx->status.phone_number) - 1;
                }
                memcpy(ctx->status.phone_number, quote1 + 1, len);
                ctx->status.phone_number[len] = '\0';
            }
        }
        return ESP_OK;
    }

    if (strstr(urc_line, "VOICE CALL: BEGIN") != NULL || strstr(urc_line, "MO CONNECT") != NULL) {
        ctx->status.state = SIM7670_CALL_STATE_ACTIVE;
        ctx->status.call_connected_time_us = now;
        return ESP_OK;
    }

    if (strstr(urc_line, "VOICE CALL: END") != NULL || strstr(urc_line, "NO CARRIER") != NULL) {
        if (ctx->status.call_connected_time_us > 0 && now >= ctx->status.call_connected_time_us) {
            ctx->status.call_duration_sec = (uint32_t)((now - ctx->status.call_connected_time_us) / 1000000LL);
        }
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        if (ctx->status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_NONE) {
            ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_REMOTE_HANGUP;
        }
        return ESP_OK;
    }

    if (strstr(urc_line, "BUSY") != NULL) {
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_BUSY;
        return ESP_OK;
    }

    if (strstr(urc_line, "NO ANSWER") != NULL) {
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_NO_ANSWER;
        return ESP_OK;
    }

    if (strstr(urc_line, "NO DIALTONE") != NULL) {
        ctx->status.state = SIM7670_CALL_STATE_IDLE;
        ctx->status.last_disconnect_reason = SIM7670_CALL_DISCONNECT_NETWORK_REJECT;
        return ESP_OK;
    }

    return ESP_FAIL;
}

esp_err_t sim7670_cellular_call_get_status(
    const sim7670_cellular_call_ctx_t *ctx,
    sim7670_call_status_t *out_status)
{
    if (ctx == NULL || !ctx->initialized || out_status == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    *out_status = ctx->status;
    return ESP_OK;
}

const char *sim7670_call_state_to_str(sim7670_call_state_t state)
{
    switch (state) {
        case SIM7670_CALL_STATE_IDLE:
            return "IDLE";
        case SIM7670_CALL_STATE_DIALING:
            return "DIALING";
        case SIM7670_CALL_STATE_ALERTING:
            return "ALERTING";
        case SIM7670_CALL_STATE_INCOMING:
            return "INCOMING";
        case SIM7670_CALL_STATE_ACTIVE:
            return "ACTIVE";
        case SIM7670_CALL_STATE_DISCONNECTING:
            return "DISCONNECTING";
        case SIM7670_CALL_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

const char *sim7670_call_disconnect_reason_to_str(sim7670_call_disconnect_reason_t reason)
{
    switch (reason) {
        case SIM7670_CALL_DISCONNECT_NONE:
            return "NONE";
        case SIM7670_CALL_DISCONNECT_LOCAL_HANGUP:
            return "LOCAL_HANGUP";
        case SIM7670_CALL_DISCONNECT_REMOTE_HANGUP:
            return "REMOTE_HANGUP";
        case SIM7670_CALL_DISCONNECT_BUSY:
            return "BUSY";
        case SIM7670_CALL_DISCONNECT_NO_ANSWER:
            return "NO_ANSWER";
        case SIM7670_CALL_DISCONNECT_NETWORK_REJECT:
            return "NETWORK_REJECT";
        case SIM7670_CALL_DISCONNECT_TIMEOUT:
            return "TIMEOUT";
        case SIM7670_CALL_DISCONNECT_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}
