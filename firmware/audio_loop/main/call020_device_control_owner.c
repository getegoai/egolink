/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 */

#include "call020_device_control_owner.h"

#include <limits.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#if defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER) && \
    CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER
#if !defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER) || \
    !CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER
#error "CALL-020R requires CALL-020Q device CONTROL responder"
#endif
#if !defined(CONFIG_ESP_CONSOLE_NONE) || !CONFIG_ESP_CONSOLE_NONE
#error "CALL-020R requires CONFIG_ESP_CONSOLE_NONE"
#endif
#if !defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) || \
    !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "CALL-020R requires CONFIG_ESP_CONSOLE_SECONDARY_NONE"
#endif
#if !defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) || \
    !CONFIG_LOG_DEFAULT_LEVEL_NONE
#error "CALL-020R requires CONFIG_LOG_DEFAULT_LEVEL_NONE"
#endif
#if !defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) || \
    !CONFIG_BOOTLOADER_LOG_LEVEL_NONE
#error "CALL-020R requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE"
#endif
#endif

typedef struct {
    bool initialized;
    call020_device_control_owner_config_t config;
    call020_device_control_owner_metadata_t metadata;
    call020_device_control_responder_t responder;
} call020_device_control_owner_context_t;

/* One global context makes a second lifecycle owner impossible in this image. */
static call020_device_control_owner_context_t s_owner;
static portMUX_TYPE s_owner_init_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_owner_init_claimed;

static esp_err_t preserve_first_error(esp_err_t current, esp_err_t candidate)
{
    return current == ESP_OK && candidate != ESP_OK ? candidate : current;
}

static bool dedicated_owner_build_enabled(void)
{
#if defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER) && \
    CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER && \
    defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER) && \
    CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER && \
    defined(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER) && \
    CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER && \
    defined(CONFIG_ESP_CONSOLE_NONE) && CONFIG_ESP_CONSOLE_NONE && \
    defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) && \
    CONFIG_ESP_CONSOLE_SECONDARY_NONE && \
    defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) && \
    CONFIG_LOG_DEFAULT_LEVEL_NONE && \
    defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) && \
    CONFIG_BOOTLOADER_LOG_LEVEL_NONE
    return true;
#else
    return false;
#endif
}

static bool checked_add_u64(uint64_t base, uint64_t delta, uint64_t *result)
{
    if (result == NULL || UINT64_MAX - base < delta) {
        return false;
    }
    *result = base + delta;
    return true;
}

static bool now_us(uint64_t *value)
{
    if (value == NULL) {
        return false;
    }
    int64_t observed = esp_timer_get_time();
    if (observed < 0) {
        return false;
    }
    *value = (uint64_t)observed;
    return true;
}

static void bounded_wait(uint64_t now, uint64_t deadline)
{
    if (now >= deadline) {
        return;
    }
    uint64_t remaining_us = deadline - now;
    uint64_t slice_us =
        (uint64_t)s_owner.config.poll_slice_ms * UINT64_C(1000);
    uint64_t wait_us = remaining_us < slice_us ? remaining_us : slice_us;
    uint64_t ticks =
        (wait_us * (uint64_t)configTICK_RATE_HZ) / UINT64_C(1000000);
    if (ticks == 0U) {
        taskYIELD();
    } else {
        vTaskDelay((TickType_t)ticks);
    }
}

static bool config_valid(const call020_device_control_owner_config_t *config)
{
    if (config == NULL ||
        config->control_total_timeout_us == 0U ||
        config->control_total_timeout_us >
            CALL020_DEVICE_CONTROL_OWNER_MAX_CONTROL_TIMEOUT_US ||
        config->poll_slice_ms == 0U ||
        config->poll_slice_ms > CALL020_DEVICE_CONTROL_OWNER_MAX_POLL_MS ||
        config->media_quiesce_grace_us < UINT64_C(200000) ||
        config->media_quiesce_grace_us >
            CALL020_DEVICE_CONTROL_OWNER_MAX_QUIESCE_GRACE_US ||
        config->responder.result_phase_enabled ||
        config->enabled != config->responder.enabled) {
        return false;
    }
    uint64_t frame_wait_us =
        (uint64_t)config->responder.frame_wait_timeout_ms * UINT64_C(1000);
    uint64_t operation_wait_us =
        (uint64_t)config->responder.max_operation_timeout_ms * UINT64_C(1000);
    uint64_t complete_serve_budget_us = 0U;
    return frame_wait_us > 0U && operation_wait_us > 0U &&
        checked_add_u64(
            frame_wait_us,
            operation_wait_us,
            &complete_serve_budget_us) &&
        complete_serve_budget_us <= config->control_total_timeout_us;
}

static bool four_workers_finished(
    const call020_operator_runner_metadata_t *runner)
{
    return runner != NULL &&
        runner->composition.workers_created == UINT32_C(4) &&
        runner->composition.workers_finished == UINT32_C(4);
}

static bool media_terminal_observed(
    const call020_operator_runner_metadata_t *runner)
{
    return runner->state == CALL020_OPERATOR_TERMINAL ||
        runner->state == CALL020_OPERATOR_STOPPING ||
        runner->state == CALL020_OPERATOR_JOINED ||
        runner->composition.state == CALL020_WEARABLE_STOPPING ||
        runner->composition.state == CALL020_WEARABLE_STOPPED ||
        runner->composition.state == CALL020_WEARABLE_TERMINAL;
}

static esp_err_t runner_reported_failure(
    const call020_operator_runner_metadata_t *runner)
{
    if (runner == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    bool expected_run_limit =
        runner->composition.run_limit_reached &&
        runner->composition.terminal_reason ==
            CALL020_WEARABLE_TERMINAL_RUNTIME &&
        runner->composition.first_error == ESP_ERR_TIMEOUT &&
        (runner->first_error == ESP_OK ||
         runner->first_error == ESP_ERR_TIMEOUT);
    if (expected_run_limit) {
        s_owner.metadata.media_run_limit_reached = true;
        return ESP_OK;
    }
    esp_err_t result = preserve_first_error(
        runner->first_error,
        runner->composition.first_error);
    if (result != ESP_OK) {
        s_owner.metadata.media_failure_observed = true;
    }
    return result;
}

static bool copy_responder_state(bool require_media_termination)
{
    call020_device_control_responder_metadata_t responder = {0};
    esp_err_t metadata_result = call020_device_control_responder_get_metadata(
        &s_owner.responder, &responder);
    if (metadata_result != ESP_OK) {
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error, metadata_result);
        return false;
    }
    s_owner.metadata.responder_first_error = responder.first_error;
    if (s_owner.metadata.responder_terminal_reason ==
            CALL020_DEVICE_CONTROL_TERMINAL_NONE &&
        responder.terminal_reason != CALL020_DEVICE_CONTROL_TERMINAL_NONE) {
        s_owner.metadata.responder_terminal_reason =
            responder.terminal_reason;
    }
    s_owner.metadata.device_runtime_termination_proven =
        responder.device_runtime_termination_proven;
    s_owner.metadata.physical_driver_close_confirmed =
        responder.physical_driver_close_confirmed;
    if (responder.media_workers_quiescent) {
        s_owner.metadata.all_four_workers_terminal = true;
    }
    bool responder_closed =
        responder.state == CALL020_DEVICE_CONTROL_CLOSED &&
        !responder.lease_installed;
    bool complete = responder_closed &&
        (!require_media_termination ||
         (responder.device_runtime_termination_proven &&
          responder.physical_driver_close_confirmed &&
          responder.media_workers_quiescent &&
          responder.media_output_safe_verified &&
          responder.media_runner_resources_closed &&
          responder.media_driver_lease_returned));
    if (complete) {
        s_owner.metadata.cleanup_complete = true;
    }
    return complete;
}

static void cleanup_recovery_backoff(void)
{
    uint32_t exponent = s_owner.metadata.cleanup_recovery_attempts;
    if (exponent > UINT32_C(6)) {
        exponent = UINT32_C(6);
    }
    uint64_t delay_ms = (uint64_t)s_owner.config.poll_slice_ms << exponent;
    if (delay_ms > CALL020_DEVICE_CONTROL_OWNER_MAX_RECOVERY_BACKOFF_MS) {
        delay_ms = CALL020_DEVICE_CONTROL_OWNER_MAX_RECOVERY_BACKOFF_MS;
    }
    TickType_t ticks = pdMS_TO_TICKS((uint32_t)delay_ms);
    if (ticks == 0U) {
        ticks = 1U;
    }
    s_owner.metadata.cleanup_backoff_waits++;
    vTaskDelay(ticks);
}

static esp_err_t dispose_before_media(esp_err_t reason)
{
    for (;;) {
        esp_err_t cleanup = call020_device_control_responder_abort_local(
            &s_owner.responder);
        bool complete = copy_responder_state(false);
        esp_err_t precise_reason =
            s_owner.metadata.responder_first_error != ESP_OK
            ? s_owner.metadata.responder_first_error
            : reason;
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error, precise_reason);
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error, cleanup);
        if (complete) {
            s_owner.metadata.state = CALL020_DEVICE_OWNER_CLOSED;
            return s_owner.metadata.first_error;
        }
        s_owner.metadata.cleanup_recovery_attempts++;
        s_owner.metadata.state = CALL020_DEVICE_OWNER_RECOVERING;
        cleanup_recovery_backoff();
    }
}

static esp_err_t finalize_media_and_close(void)
{
    for (;;) {
        /* No wire function is reachable after MEDIA_STARTED. */
        s_owner.metadata.media_finalize_calls++;
        esp_err_t finalize =
            call020_device_control_responder_finish_media_local(
                &s_owner.responder);
        bool cleanup_proven = copy_responder_state(true);

        call020_operator_runner_metadata_t runner = {0};
        esp_err_t metadata_result = call020_operator_runner_get_metadata(
            &runner);
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error, metadata_result);
        if (metadata_result == ESP_OK) {
            s_owner.metadata.first_error = preserve_first_error(
                s_owner.metadata.first_error,
                runner_reported_failure(&runner));
        }
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error, finalize);

        if (cleanup_proven) {
            s_owner.metadata.state = CALL020_DEVICE_OWNER_CLOSED;
            return s_owner.metadata.first_error;
        }
        s_owner.metadata.cleanup_recovery_attempts++;
        s_owner.metadata.state = CALL020_DEVICE_OWNER_RECOVERING;
        cleanup_recovery_backoff();
    }
}

static esp_err_t finish_media(uint64_t media_started_us)
{
    uint64_t media_deadline_us = 0U;
    if (!checked_add_u64(
            media_started_us,
            s_owner.config.responder.runner.max_runtime_us,
            &media_deadline_us)) {
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error,
            ESP_ERR_INVALID_STATE);
        s_owner.metadata.local_cancel_calls++;
        esp_err_t cancel = call020_operator_runner_cancel();
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error,
            cancel);
        s_owner.metadata.state = CALL020_DEVICE_OWNER_QUIESCING;
        return finalize_media_and_close();
    }

    bool cancel_requested = false;
    uint64_t quiesce_deadline_us = 0U;
    for (;;) {
        call020_operator_runner_metadata_t runner = {0};
        s_owner.metadata.runner_metadata_polls++;
        esp_err_t metadata_result = call020_operator_runner_get_metadata(
            &runner);
        s_owner.metadata.first_error = preserve_first_error(
            s_owner.metadata.first_error,
            metadata_result);
        if (metadata_result == ESP_OK) {
            s_owner.metadata.first_error = preserve_first_error(
                s_owner.metadata.first_error,
                runner_reported_failure(&runner));
        }

        uint64_t current_us = 0U;
        bool clock_valid = now_us(&current_us);
        if (!clock_valid) {
            s_owner.metadata.media_failure_observed = true;
            s_owner.metadata.first_error = preserve_first_error(
                s_owner.metadata.first_error,
                ESP_ERR_INVALID_STATE);
        }
        bool deadline_reached = !clock_valid || current_us >= media_deadline_us;
        bool terminal = metadata_result != ESP_OK ||
            media_terminal_observed(&runner) ||
            four_workers_finished(&runner);
        if (deadline_reached) {
            s_owner.metadata.media_deadline_reached = true;
        }
        if (!cancel_requested && (deadline_reached || terminal)) {
            /* runner_cancel first forces mute/PA safe, then requests cancel. */
            s_owner.metadata.local_cancel_calls++;
            esp_err_t cancel = call020_operator_runner_cancel();
            s_owner.metadata.first_error = preserve_first_error(
                s_owner.metadata.first_error, cancel);
            cancel_requested = true;
            s_owner.metadata.state = CALL020_DEVICE_OWNER_QUIESCING;
            if (!clock_valid || !checked_add_u64(
                    current_us,
                    s_owner.config.media_quiesce_grace_us,
                    &quiesce_deadline_us)) {
                quiesce_deadline_us = current_us;
            }
        }

        if (cancel_requested && metadata_result == ESP_OK &&
            four_workers_finished(&runner)) {
            s_owner.metadata.all_four_workers_terminal = true;
            break;
        }
        if (!clock_valid || (cancel_requested &&
            current_us >= quiesce_deadline_us)) {
            break;
        }
        bounded_wait(
            current_us,
            cancel_requested ? quiesce_deadline_us : media_deadline_us);
    }

    return finalize_media_and_close();
}

const char *call020_device_control_owner_version(void)
{
    return CALL020_DEVICE_CONTROL_OWNER_VERSION;
}

esp_err_t call020_device_control_owner_init(
    const call020_device_control_owner_config_t *config)
{
    if (!config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_owner_init_lock);
    if (s_owner_init_claimed || s_owner.initialized) {
        portEXIT_CRITICAL(&s_owner_init_lock);
        return ESP_ERR_INVALID_STATE;
    }
    s_owner_init_claimed = true;
    portEXIT_CRITICAL(&s_owner_init_lock);

    memset(&s_owner, 0, sizeof(s_owner));
    s_owner.config = *config;
    s_owner.metadata.state = CALL020_DEVICE_OWNER_DORMANT;
    s_owner.metadata.first_error = ESP_OK;
    s_owner.metadata.owner_core_id = -1;
    s_owner.metadata.enabled_by_config = config->enabled;
    s_owner.metadata.dedicated_build_enabled =
        dedicated_owner_build_enabled();
    s_owner.metadata.emitted_post_start_control = false;
    s_owner.metadata.result_phase_enabled = false;
    s_owner.metadata.raw_audio_logged_or_persisted = false;
    esp_err_t result = call020_device_control_responder_init(
        &s_owner.responder, &config->responder);
    if (result != ESP_OK) {
        memset(&s_owner, 0, sizeof(s_owner));
        portENTER_CRITICAL(&s_owner_init_lock);
        s_owner_init_claimed = false;
        portEXIT_CRITICAL(&s_owner_init_lock);
        return result;
    }
    s_owner.initialized = true;
    return ESP_OK;
}

esp_err_t call020_device_control_owner_run(void)
{
    if (!s_owner.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    s_owner.metadata.run_calls++;
    if (!s_owner.config.enabled || !dedicated_owner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (s_owner.metadata.state != CALL020_DEVICE_OWNER_DORMANT) {
        return ESP_ERR_INVALID_STATE;
    }
    s_owner.metadata.owner_core_id = (int)xPortGetCoreID();

    uint64_t started_us = 0U;
    uint64_t control_deadline_us = 0U;
    if (!now_us(&started_us) || !checked_add_u64(
            started_us,
            s_owner.config.control_total_timeout_us,
            &control_deadline_us)) {
        s_owner.metadata.first_error = ESP_ERR_INVALID_STATE;
        s_owner.metadata.cleanup_complete = true;
        s_owner.metadata.state = CALL020_DEVICE_OWNER_CLOSED;
        return s_owner.metadata.first_error;
    }
    s_owner.metadata.state = CALL020_DEVICE_OWNER_CONTROL;
    esp_err_t result = call020_device_control_responder_open_control(
        &s_owner.responder);
    if (result != ESP_OK) {
        return dispose_before_media(result);
    }

    const uint64_t frame_wait_us =
        (uint64_t)s_owner.config.responder.frame_wait_timeout_ms *
        UINT64_C(1000);
    const uint64_t operation_wait_us =
        (uint64_t)s_owner.config.responder.max_operation_timeout_ms *
        UINT64_C(1000);
    uint64_t complete_serve_budget_us = 0U;
    if (!checked_add_u64(
            frame_wait_us, operation_wait_us, &complete_serve_budget_us)) {
        return dispose_before_media(ESP_ERR_INVALID_STATE);
    }
    for (;;) {
        uint64_t current_us = 0U;
        if (!now_us(&current_us) || current_us >= control_deadline_us ||
            control_deadline_us - current_us < complete_serve_budget_us) {
            s_owner.metadata.control_total_deadline_reached = true;
            return dispose_before_media(ESP_ERR_TIMEOUT);
        }
        s_owner.metadata.control_serve_calls++;
        call020_device_control_serve_result_t served =
            call020_device_control_responder_serve_once(&s_owner.responder);
        bool post_serve_clock_valid = now_us(&current_us);
        if (served == CALL020_DEVICE_CONTROL_SERVE_MEDIA_STARTED) {
            s_owner.metadata.state = CALL020_DEVICE_OWNER_MEDIA;
            if (!post_serve_clock_valid || current_us >= control_deadline_us) {
                s_owner.metadata.control_total_deadline_reached = true;
                s_owner.metadata.media_failure_observed = true;
                s_owner.metadata.first_error = preserve_first_error(
                    s_owner.metadata.first_error,
                    post_serve_clock_valid
                        ? ESP_ERR_TIMEOUT
                        : ESP_ERR_INVALID_STATE);
                s_owner.metadata.local_cancel_calls++;
                esp_err_t cancel = call020_operator_runner_cancel();
                s_owner.metadata.first_error = preserve_first_error(
                    s_owner.metadata.first_error, cancel);
                s_owner.metadata.state = CALL020_DEVICE_OWNER_QUIESCING;
                return finalize_media_and_close();
            }
            return finish_media(current_us);
        }
        if (!post_serve_clock_valid || current_us >= control_deadline_us) {
            s_owner.metadata.control_total_deadline_reached = true;
            return dispose_before_media(ESP_ERR_TIMEOUT);
        }
        if (served == CALL020_DEVICE_CONTROL_SERVE_CLOSE_COMPLETE) {
            if (copy_responder_state(false)) {
                s_owner.metadata.state = CALL020_DEVICE_OWNER_CLOSED;
                return s_owner.metadata.first_error;
            }
            return dispose_before_media(ESP_ERR_INVALID_STATE);
        }
        if (served == CALL020_DEVICE_CONTROL_SERVE_TERMINAL) {
            return dispose_before_media(ESP_FAIL);
        }
    }
}

esp_err_t call020_device_control_owner_get_metadata(
    call020_device_control_owner_metadata_t *metadata)
{
    if (metadata == NULL || !s_owner.initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    *metadata = s_owner.metadata;
    return ESP_OK;
}
