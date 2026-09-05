/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020F build-only wearable composition. No raw media is logged or
 * persisted. Ordinary app_main does not instantiate this component.
 */

#include "call020_wearable_composition.h"

#include <limits.h>
#include <string.h>

#include "bsp/esp-bsp.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "esp_codec_dev.h"
#include "esp_timer.h"
#include "sdkconfig.h"

#ifndef CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME
#define CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME 55
#endif

#if defined(CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION) && \
    CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION
#if !defined(CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE) || \
    !CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE
#error "CALL-020F requires the CALL-020D media adapter core"
#endif
#if !defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) || \
    !CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT
#error "CALL-020F requires the CALL-020E USB Serial/JTAG endpoint"
#endif
#if !defined(CONFIG_ESP_CONSOLE_NONE) || !CONFIG_ESP_CONSOLE_NONE
#error "CALL-020F requires CONFIG_ESP_CONSOLE_NONE"
#endif
#if !defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) || \
    !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "CALL-020F requires CONFIG_ESP_CONSOLE_SECONDARY_NONE"
#endif
#if !defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) || \
    !CONFIG_LOG_DEFAULT_LEVEL_NONE
#error "CALL-020F requires CONFIG_LOG_DEFAULT_LEVEL_NONE"
#endif
#if !defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) || \
    !CONFIG_BOOTLOADER_LOG_LEVEL_NONE
#error "CALL-020F requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE"
#endif
#if defined(CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) && \
    CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN
#error "CALL-020F cannot share the CALL-010 autorun owner"
#endif
#endif

#define WORKER_START_BIT BIT0
#define WORKER_CANCEL_BIT BIT1
#define AUDIO_CAPTURE_DONE_BIT BIT2
#define USB_UPLINK_DONE_BIT BIT3
#define USB_DOWNLINK_DONE_BIT BIT4
#define AUDIO_OUTPUT_DONE_BIT BIT5
#define ALL_WORKER_DONE_BITS \
    (AUDIO_CAPTURE_DONE_BIT | USB_UPLINK_DONE_BIT | \
     USB_DOWNLINK_DONE_BIT | AUDIO_OUTPUT_DONE_BIT)
#define WORKER_QUEUE_POLL_MS UINT32_C(20)
#define ES8311_DAC_MUTE_REGISTER 0x31
#define ES8311_DAC_MUTE_MASK 0x60
#define ES8311_DAC_VOLUME_REGISTER 0x32
#define ES8311_VOLUME_REGISTER_BASE 98
#define CALL020_OUTPUT_VOLUME_MAX 85
#define MUTE_VERIFY_ATTEMPTS UINT32_C(3)
#define MUTE_VERIFY_DELAY_MS UINT32_C(2)
#define CALL020_INPUT_GAIN_DB 24.0f

_Static_assert(
    CALL020_MEDIA_FRAME_MS == 20U &&
        CALL020_MEDIA_STEREO_BYTES == 1280U &&
        CALL020_MEDIA_MONO_BYTES == 640U &&
        CALL020_WEARABLE_FRAME_INTERVAL_US ==
            (uint64_t)CALL020_MEDIA_FRAME_MS * UINT64_C(1000),
    "CALL-020F requires the frozen 20 ms / 640-byte mono profile");
_Static_assert(
    CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME >= 1 &&
        CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME <= CALL020_OUTPUT_VOLUME_MAX,
    "CALL-020F output volume must remain within the reviewed 1..85 bound");

static void secure_zero(void *memory, size_t bytes)
{
    if (memory == NULL) {
        return;
    }
    volatile uint8_t *cursor = (volatile uint8_t *)memory;
    while (bytes > 0U) {
        *cursor++ = 0U;
        --bytes;
    }
}

static esp_err_t preserve_first_error(esp_err_t current, esp_err_t candidate)
{
    return current == ESP_OK && candidate != ESP_OK ? candidate : current;
}

static bool checked_add_u64(uint64_t left, uint64_t right, uint64_t *sum)
{
    if (sum == NULL || UINT64_MAX - left < right) {
        return false;
    }
    *sum = left + right;
    return true;
}

static bool get_now_us(uint64_t *now_us)
{
    int64_t now = esp_timer_get_time();
    if (now_us == NULL || now < 0) {
        return false;
    }
    *now_us = (uint64_t)now;
    return true;
}

static bool dedicated_build_enabled(void)
{
#if defined(CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION) && \
    CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION && \
    defined(CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE) && \
    CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE && \
    defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) && \
    CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT && \
    defined(CONFIG_ESP_CONSOLE_NONE) && CONFIG_ESP_CONSOLE_NONE && \
    defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) && \
    CONFIG_ESP_CONSOLE_SECONDARY_NONE && \
    defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) && \
    CONFIG_LOG_DEFAULT_LEVEL_NONE && \
    defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) && \
    CONFIG_BOOTLOADER_LOG_LEVEL_NONE && \
    (!defined(CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) || \
     !CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN)
    return true;
#else
    return false;
#endif
}

static bool identifier_length(const char *value, size_t *length)
{
    if (value == NULL || length == NULL) {
        return false;
    }
    size_t cursor = 0U;
    while (cursor <= CALL020_MEDIA_IDENTIFIER_MAX_BYTES &&
           value[cursor] != '\0') {
        uint8_t character = (uint8_t)value[cursor];
        bool allowed =
            (character >= (uint8_t)'A' && character <= (uint8_t)'Z') ||
            (character >= (uint8_t)'a' && character <= (uint8_t)'z') ||
            (character >= (uint8_t)'0' && character <= (uint8_t)'9') ||
            character == (uint8_t)'.' || character == (uint8_t)'_' ||
            character == (uint8_t)':' || character == (uint8_t)'-';
        if (!allowed) {
            return false;
        }
        ++cursor;
    }
    if (cursor == 0U || cursor > CALL020_MEDIA_IDENTIFIER_MAX_BYTES ||
        value[cursor] != '\0') {
        return false;
    }
    *length = cursor;
    return true;
}

static bool expected_wire_bytes(
    const call020_wearable_composition_config_t *config,
    bool uplink,
    size_t *wire_bytes)
{
    if (config == NULL || wire_bytes == NULL) {
        return false;
    }
    const char *identifiers[4] = {
        config->session_id,
        uplink ? config->device_id : config->guardian_id,
        uplink ? config->guardian_id : config->device_id,
        uplink ? config->uplink_clock_id : config->downlink_clock_id,
    };
    size_t total = CALL020_MEDIA_WIRE_HEADER_BYTES +
        CALL020_MEDIA_MONO_BYTES + CALL020_MEDIA_WIRE_CRC_BYTES;
    for (size_t index = 0U; index < 4U; ++index) {
        size_t length = 0U;
        if (!identifier_length(identifiers[index], &length) ||
            SIZE_MAX - total < length) {
            return false;
        }
        total += length;
    }
    if (total > CALL020_MEDIA_WIRE_MAX_BYTES) {
        return false;
    }
    *wire_bytes = total;
    return true;
}

static bool config_valid(
    const call020_wearable_composition_config_t *config,
    size_t expected_uplink_wire_size,
    size_t expected_downlink_wire_size)
{
    if (config == NULL) {
        return false;
    }
    size_t ignored = 0U;
    if (!identifier_length(config->session_id, &ignored) ||
        !identifier_length(config->device_id, &ignored) ||
        !identifier_length(config->guardian_id, &ignored) ||
        !identifier_length(config->uplink_clock_id, &ignored) ||
        !identifier_length(config->downlink_clock_id, &ignored)) {
        return false;
    }
    uint64_t endpoint_slice_us =
        (uint64_t)config->usb_endpoint.io_wait_slice_ms * UINT64_C(1000);
    if (
        (config->identity_provenance !=
             CALL020_WEARABLE_IDENTITY_OPERATOR_SUPPLIED &&
         config->identity_provenance !=
             CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL) ||
        config->handoff_queue_frames == 0U ||
        config->handoff_queue_frames >
            CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES ||
        config->frame_deadline_slack_us < UINT64_C(20000) ||
        config->frame_deadline_slack_us > UINT64_C(1000000) ||
        config->downlink_playout_delay_us > UINT64_C(1000000) ||
        config->max_runtime_us < UINT64_C(20000) ||
        config->max_runtime_us > CALL020_MEDIA_MAX_RUNTIME_US ||
        config->audio_io_timeout_us < UINT64_C(20000) ||
        config->audio_io_timeout_us >
            CALL020_WEARABLE_AUDIO_IO_TIMEOUT_MAX_US ||
        config->usb_read_poll_us == 0U ||
        config->usb_read_poll_us >
            CALL020_WEARABLE_USB_READ_POLL_MAX_US ||
        config->join_timeout_us < UINT64_C(200000) ||
        config->join_timeout_us > CALL020_WEARABLE_JOIN_TIMEOUT_MAX_US ||
        config->usb_endpoint.io_wait_slice_ms == 0U ||
        config->usb_endpoint.io_wait_slice_ms >
            CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS ||
        config->usb_endpoint.max_operation_us <
            config->frame_deadline_slack_us ||
        config->usb_endpoint.max_operation_us < config->usb_read_poll_us ||
        config->usb_endpoint.max_operation_us >
            CALL020_USB_ENDPOINT_MAX_OPERATION_US ||
        config->usb_endpoint.close_timeout_us < endpoint_slice_us ||
        config->usb_endpoint.close_timeout_us >
            CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US ||
        config->usb_endpoint.tx_buffer_bytes <
            expected_uplink_wire_size * 2U ||
        config->usb_endpoint.rx_buffer_bytes <
            expected_downlink_wire_size * 2U ||
        config->usb_endpoint.tx_buffer_bytes >
            CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES ||
        config->usb_endpoint.rx_buffer_bytes >
            CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES ||
        strcmp(config->device_id, config->guardian_id) == 0 ||
        strcmp(config->uplink_clock_id, config->downlink_clock_id) == 0) {
        return false;
    }
    return true;
}

static void sync_metadata_locked(call020_wearable_composition_t *composition)
{
    composition->metadata.state = composition->state;
    composition->metadata.terminal_reason = composition->terminal_reason;
    composition->metadata.first_error = composition->first_error;
    composition->metadata.identity_provenance =
        composition->identity_provenance;
    composition->metadata.endpoint_installed =
        composition->endpoint_installed;
    composition->metadata.usb_driver_ownership =
        composition->endpoint.driver_ownership;
    composition->metadata.usb_driver_lease_generation =
        composition->endpoint.driver_generation;
    composition->metadata.usb_driver_binding_closed =
        composition->endpoint.binding_closed;
    composition->metadata.usb_driver_uninstalled_by_composition =
        composition->endpoint.driver_uninstalled_by_endpoint;
    composition->metadata.usb_driver_lease_returned =
        composition->endpoint.lease_returned;
    composition->metadata.usb_driver_lifetime_owned_by_caller =
        composition->endpoint_borrowed_from_lease;
}

static bool cancellation_requested(
    call020_wearable_composition_t *composition)
{
    portENTER_CRITICAL(&composition->lock);
    bool requested = composition->cancel_requested;
    portEXIT_CRITICAL(&composition->lock);
    return requested;
}

static esp_err_t pa_force_off(void *user_context)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)user_context;
    esp_err_t result = gpio_set_level(BSP_POWER_AMP_IO, 0);
    bool verified = result == ESP_OK &&
        gpio_get_level(BSP_POWER_AMP_IO) == 0;
    if (composition != NULL) {
        portENTER_CRITICAL(&composition->lock);
        composition->output_enabled = false;
        composition->metadata.pa_off_verified = verified;
        portEXIT_CRITICAL(&composition->lock);
    }
    return verified ? ESP_OK : (result == ESP_OK ? ESP_FAIL : result);
}

static esp_err_t pa_prepare_off(call020_wearable_composition_t *composition)
{
    esp_err_t result = gpio_set_level(BSP_POWER_AMP_IO, 0);
    if (result != ESP_OK) {
        return result;
    }
    const gpio_config_t config = {
        .pin_bit_mask = UINT64_C(1) << BSP_POWER_AMP_IO,
        .mode = GPIO_MODE_INPUT_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    result = gpio_config(&config);
    return result == ESP_OK ? pa_force_off(composition) : result;
}

static esp_err_t codec_set_muted_verified(
    call020_wearable_composition_t *composition, bool muted)
{
    if (composition == NULL || !composition->speaker_opened ||
        composition->audio.speaker == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    esp_err_t result = esp_codec_dev_set_out_mute(
        composition->audio.speaker, muted);
    bool verified = false;
    int register_value = 0;
    for (uint32_t attempt = 0U;
         result == ESP_OK && attempt < MUTE_VERIFY_ATTEMPTS;
         ++attempt) {
        result = esp_codec_dev_read_reg(
            composition->audio.speaker,
            ES8311_DAC_MUTE_REGISTER,
            &register_value);
        if (result == ESP_OK) {
            int mute_bits = register_value & ES8311_DAC_MUTE_MASK;
            verified = muted
                ? mute_bits == ES8311_DAC_MUTE_MASK
                : mute_bits == 0;
            if (verified) {
                break;
            }
            if (attempt + 1U < MUTE_VERIFY_ATTEMPTS) {
                vTaskDelay(pdMS_TO_TICKS(MUTE_VERIFY_DELAY_MS));
            }
        }
    }
    if (result == ESP_OK && !verified) {
        int requested_value = muted
            ? register_value | ES8311_DAC_MUTE_MASK
            : register_value & ~ES8311_DAC_MUTE_MASK;
        result = esp_codec_dev_write_reg(
            composition->audio.speaker,
            ES8311_DAC_MUTE_REGISTER,
            requested_value);
        for (uint32_t attempt = 0U;
             result == ESP_OK && attempt < MUTE_VERIFY_ATTEMPTS;
             ++attempt) {
            result = esp_codec_dev_read_reg(
                composition->audio.speaker,
                ES8311_DAC_MUTE_REGISTER,
                &register_value);
            if (result == ESP_OK) {
                int mute_bits = register_value & ES8311_DAC_MUTE_MASK;
                verified = muted
                    ? mute_bits == ES8311_DAC_MUTE_MASK
                    : mute_bits == 0;
                if (verified) {
                    break;
                }
                if (attempt + 1U < MUTE_VERIFY_ATTEMPTS) {
                    vTaskDelay(pdMS_TO_TICKS(MUTE_VERIFY_DELAY_MS));
                }
            }
        }
    }
    portENTER_CRITICAL(&composition->lock);
    composition->metadata.codec_muted_verified = muted && verified;
    portEXIT_CRITICAL(&composition->lock);
    return result == ESP_OK && verified ? ESP_OK :
        (result == ESP_OK ? ESP_FAIL : result);
}

static esp_err_t force_output_safe(
    call020_wearable_composition_t *composition)
{
    esp_err_t result = pa_force_off(composition);
    if (composition->speaker_opened) {
        result = preserve_first_error(
            result, codec_set_muted_verified(composition, true));
    }
    result = preserve_first_error(result, pa_force_off(composition));
    return result;
}

static esp_err_t set_output_volume_verified(
    call020_wearable_composition_t *composition)
{
    esp_err_t result = force_output_safe(composition);
    int register_value = -1;
    if (result == ESP_OK) {
        result = esp_codec_dev_set_out_vol(
            composition->audio.speaker,
            CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME);
    }
    if (result == ESP_OK) {
        result = esp_codec_dev_read_reg(
            composition->audio.speaker,
            ES8311_DAC_VOLUME_REGISTER,
            &register_value);
    }
    bool verified = result == ESP_OK &&
        (register_value & 0xff) ==
            ES8311_VOLUME_REGISTER_BASE +
                CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME;
    portENTER_CRITICAL(&composition->lock);
    composition->metadata.output_volume =
        CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME;
    composition->metadata.output_volume_verified = verified;
    portEXIT_CRITICAL(&composition->lock);
    if (!verified) {
        force_output_safe(composition);
        return result == ESP_OK ? ESP_FAIL : result;
    }
    return ESP_OK;
}

static esp_err_t enable_output(
    call020_wearable_composition_t *composition)
{
    if (cancellation_requested(composition)) {
        return ESP_ERR_INVALID_STATE;
    }
    esp_err_t result = codec_set_muted_verified(composition, false);
    if (result != ESP_OK) {
        force_output_safe(composition);
        return result;
    }

    portENTER_CRITICAL(&composition->lock);
    if (composition->cancel_requested ||
        composition->state != CALL020_WEARABLE_RUNNING) {
        result = ESP_ERR_INVALID_STATE;
    } else {
        result = gpio_set_level(BSP_POWER_AMP_IO, 1);
        if (result == ESP_OK && gpio_get_level(BSP_POWER_AMP_IO) != 1) {
            result = ESP_FAIL;
        }
        if (result == ESP_OK) {
            composition->output_enabled = true;
            composition->metadata.pa_off_verified = false;
        }
    }
    portEXIT_CRITICAL(&composition->lock);
    if (result != ESP_OK) {
        force_output_safe(composition);
    }
    return result;
}

static void set_cancel_and_wake(
    call020_wearable_composition_t *composition,
    bool run_limit_reached)
{
    bool first_request = false;
    portENTER_CRITICAL(&composition->lock);
    if (!composition->cancel_requested) {
        first_request = true;
        composition->cancel_requested = true;
        composition->metadata.cancellation_requests++;
    }
    if (run_limit_reached) {
        composition->metadata.run_limit_reached = true;
    }
    if (composition->state == CALL020_WEARABLE_RUNNING ||
        composition->state == CALL020_WEARABLE_READY) {
        composition->state = CALL020_WEARABLE_STOPPING;
    }
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);

    if (composition->worker_events != NULL) {
        xEventGroupSetBits(
            composition->worker_events,
            WORKER_START_BIT | WORKER_CANCEL_BIT);
    }
    if (composition->endpoint_installed) {
        call020_usb_serial_jtag_endpoint_request_cancel(
            &composition->endpoint);
    }
    if (first_request || run_limit_reached) {
        pa_force_off(composition);
    }
}

static void fail_composition(
    call020_wearable_composition_t *composition,
    call020_wearable_terminal_reason_t reason,
    esp_err_t error)
{
    portENTER_CRITICAL(&composition->lock);
    if (composition->terminal_reason == CALL020_WEARABLE_TERMINAL_NONE) {
        composition->terminal_reason = reason;
        composition->first_error = error == ESP_OK ? ESP_FAIL : error;
    }
    composition->state = CALL020_WEARABLE_TERMINAL;
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);
    set_cancel_and_wake(composition, false);
    pa_force_off(composition);
}

static void fail_run_limit(call020_wearable_composition_t *composition)
{
    portENTER_CRITICAL(&composition->lock);
    composition->metadata.run_limit_reached = true;
    portEXIT_CRITICAL(&composition->lock);
    fail_composition(
        composition, CALL020_WEARABLE_TERMINAL_RUNTIME, ESP_ERR_TIMEOUT);
}

static bool worker_can_continue(
    call020_wearable_composition_t *composition, uint64_t *now_us)
{
    if (cancellation_requested(composition)) {
        return false;
    }
    if (!get_now_us(now_us)) {
        fail_composition(
            composition, CALL020_WEARABLE_TERMINAL_CLOCK,
            ESP_ERR_INVALID_STATE);
        return false;
    }
    if (*now_us >= composition->runtime_deadline_us) {
        fail_run_limit(composition);
        return false;
    }
    return true;
}

static TickType_t bounded_ticks(
    uint64_t now_us, uint64_t deadline_us, uint64_t maximum_wait_us)
{
    if (deadline_us <= now_us || maximum_wait_us == 0U) {
        return 0;
    }
    uint64_t remaining_us = deadline_us - now_us;
    uint64_t wait_us = remaining_us < maximum_wait_us
        ? remaining_us
        : maximum_wait_us;
    uint64_t ticks =
        (wait_us * (uint64_t)configTICK_RATE_HZ) / UINT64_C(1000000);
    if (ticks > (uint64_t)portMAX_DELAY) {
        ticks = (uint64_t)portMAX_DELAY;
    }
    return (TickType_t)ticks;
}

static TickType_t queue_poll_ticks(void)
{
    TickType_t ticks = pdMS_TO_TICKS(WORKER_QUEUE_POLL_MS);
    return ticks == 0 ? 1 : ticks;
}

static void finish_worker(
    call020_wearable_composition_t *composition, EventBits_t done_bit)
{
    portENTER_CRITICAL(&composition->lock);
    composition->metadata.workers_finished++;
    portEXIT_CRITICAL(&composition->lock);
    xEventGroupSetBits(composition->worker_events, done_bit);
    vTaskDelete(NULL);
}

static void wait_for_start(call020_wearable_composition_t *composition)
{
    xEventGroupWaitBits(
        composition->worker_events,
        WORKER_START_BIT,
        pdFALSE,
        pdTRUE,
        portMAX_DELAY);
}

static void audio_capture_worker(void *argument)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)argument;
    wait_for_start(composition);
    secure_zero(
        &composition->capture_scratch,
        sizeof(composition->capture_scratch));

    uint64_t last_source_time_ns = 0U;
    bool has_source_time = false;
    while (true) {
        uint64_t started_us = 0U;
        if (!worker_can_continue(composition, &started_us)) {
            break;
        }
        if (started_us < composition->next_capture_due_us) {
            TickType_t ticks = bounded_ticks(
                started_us,
                composition->next_capture_due_us,
                CALL020_WEARABLE_FRAME_INTERVAL_US);
            if (ticks == 0) {
                taskYIELD();
            } else {
                vTaskDelay(ticks);
            }
            continue;
        }
        uint64_t frame_due_us = composition->next_capture_due_us;
        if (!checked_add_u64(
                composition->next_capture_due_us,
                CALL020_WEARABLE_FRAME_INTERVAL_US,
                &composition->next_capture_due_us)) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        uint64_t io_deadline_us = 0U;
        if (!checked_add_u64(
                started_us, composition->audio_io_timeout_us,
                &io_deadline_us)) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        if (io_deadline_us > composition->runtime_deadline_us) {
            io_deadline_us = composition->runtime_deadline_us;
        }
        size_t bytes_read = 0U;
        esp_err_t result = i2s_channel_read(
            composition->audio.rx_channel,
            composition->capture_scratch.stereo,
            CALL020_MEDIA_STEREO_BYTES,
            &bytes_read,
            bounded_ticks(
                started_us, io_deadline_us,
                composition->audio_io_timeout_us));
        uint64_t completed_us = 0U;
        if (cancellation_requested(composition)) {
            secure_zero(
                &composition->capture_scratch,
                sizeof(composition->capture_scratch));
            break;
        }
        if (!get_now_us(&completed_us) || completed_us < started_us) {
            result = ESP_ERR_INVALID_STATE;
        } else if (completed_us > io_deadline_us && result == ESP_OK) {
            result = ESP_ERR_TIMEOUT;
        }
        if (result != ESP_OK ||
            bytes_read != CALL020_MEDIA_STEREO_BYTES) {
            secure_zero(
                &composition->capture_scratch,
                sizeof(composition->capture_scratch));
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_AUDIO_CAPTURE,
                result == ESP_OK ? ESP_ERR_INVALID_SIZE : result);
            break;
        }
        if (frame_due_us > (uint64_t)INT64_MAX / UINT64_C(1000)) {
            secure_zero(
                &composition->capture_scratch,
                sizeof(composition->capture_scratch));
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        uint64_t source_time_ns = frame_due_us * UINT64_C(1000);
        if (has_source_time && source_time_ns <= last_source_time_ns) {
            secure_zero(
                &composition->capture_scratch,
                sizeof(composition->capture_scratch));
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        composition->capture_scratch.source_time_ns = source_time_ns;
        if (xQueueSend(
                composition->uplink_handoff_queue,
                &composition->capture_scratch,
                0) != pdTRUE) {
            secure_zero(
                &composition->capture_scratch,
                sizeof(composition->capture_scratch));
            portENTER_CRITICAL(&composition->lock);
            composition->metadata.handoff_overflows++;
            portEXIT_CRITICAL(&composition->lock);
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_HANDOFF_OVERFLOW,
                ESP_ERR_NO_MEM);
            break;
        }
        secure_zero(
            &composition->capture_scratch,
            sizeof(composition->capture_scratch));
        last_source_time_ns = source_time_ns;
        has_source_time = true;
        portENTER_CRITICAL(&composition->lock);
        composition->metadata.captured_frames++;
        portEXIT_CRITICAL(&composition->lock);
    }
    secure_zero(
        &composition->capture_scratch,
        sizeof(composition->capture_scratch));
    finish_worker(composition, AUDIO_CAPTURE_DONE_BIT);
}

static void usb_uplink_worker(void *argument)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)argument;
    wait_for_start(composition);
    secure_zero(
        &composition->uplink_scratch,
        sizeof(composition->uplink_scratch));

    while (true) {
        uint64_t now_us = 0U;
        if (!worker_can_continue(composition, &now_us)) {
            break;
        }
        if (xQueueReceive(
                composition->uplink_handoff_queue,
                &composition->uplink_scratch,
                queue_poll_ticks()) != pdTRUE) {
            continue;
        }
        if (cancellation_requested(composition)) {
            secure_zero(
                &composition->uplink_scratch,
                sizeof(composition->uplink_scratch));
            break;
        }
        if (!get_now_us(&now_us)) {
            secure_zero(
                &composition->uplink_scratch,
                sizeof(composition->uplink_scratch));
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        esp_err_t result = call020_media_adapter_core_offer_uplink_stereo(
            &composition->uplink_core,
            composition->uplink_scratch.stereo,
            CALL020_MEDIA_STEREO_VALUES,
            composition->uplink_scratch.source_time_ns,
            now_us);
        secure_zero(
            &composition->uplink_scratch,
            sizeof(composition->uplink_scratch));
        if (result != ESP_OK) {
            if (!cancellation_requested(composition)) {
                fail_composition(
                    composition, CALL020_WEARABLE_TERMINAL_UPLINK_CORE,
                    result);
            }
            break;
        }

        while (!cancellation_requested(composition)) {
            if (!get_now_us(&now_us)) {
                result = ESP_ERR_INVALID_STATE;
                break;
            }
            result = call020_media_adapter_core_flush_uplink(
                &composition->uplink_core,
                now_us,
                call020_usb_serial_jtag_endpoint_write_wire,
                &composition->endpoint);
            if (result == ESP_OK) {
                portENTER_CRITICAL(&composition->lock);
                composition->metadata.uplink_frames_sent++;
                portEXIT_CRITICAL(&composition->lock);
                break;
            }
            if (result == ESP_ERR_TIMEOUT &&
                composition->uplink_core.state ==
                    CALL020_MEDIA_CORE_RUNNING) {
                portENTER_CRITICAL(&composition->lock);
                composition->metadata.zero_progress_write_timeouts++;
                portEXIT_CRITICAL(&composition->lock);
                continue;
            }
            break;
        }
        if (result != ESP_OK) {
            if (!cancellation_requested(composition)) {
                fail_composition(
                    composition,
                    composition->uplink_core.state ==
                            CALL020_MEDIA_CORE_TERMINAL
                        ? CALL020_WEARABLE_TERMINAL_UPLINK_CORE
                        : CALL020_WEARABLE_TERMINAL_USB_UPLINK,
                    result);
            }
            break;
        }
    }
    secure_zero(
        &composition->uplink_scratch,
        sizeof(composition->uplink_scratch));
    finish_worker(composition, USB_UPLINK_DONE_BIT);
}

static void usb_downlink_worker(void *argument)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)argument;
    wait_for_start(composition);
    secure_zero(
        &composition->usb_rx_scratch,
        sizeof(composition->usb_rx_scratch));

    while (true) {
        uint64_t now_us = 0U;
        if (!worker_can_continue(composition, &now_us)) {
            break;
        }
        uint64_t deadline_us = 0U;
        if (!checked_add_u64(
                now_us, composition->usb_read_poll_us, &deadline_us)) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        if (deadline_us > composition->runtime_deadline_us) {
            deadline_us = composition->runtime_deadline_us;
        }
        size_t transferred = 0U;
        call020_usb_endpoint_transfer_result_t transfer =
            call020_usb_serial_jtag_endpoint_read_exact(
                &composition->endpoint,
                composition->usb_rx_scratch.wire,
                composition->expected_downlink_wire_bytes,
                deadline_us,
                &transferred);
        if (transfer == CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS) {
            portENTER_CRITICAL(&composition->lock);
            composition->metadata.zero_progress_read_timeouts++;
            portEXIT_CRITICAL(&composition->lock);
            continue;
        }
        if (transfer ==
                CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS &&
            cancellation_requested(composition)) {
            break;
        }
        if (transfer != CALL020_USB_ENDPOINT_TRANSFER_OK ||
            transferred != composition->expected_downlink_wire_bytes) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_USB_DOWNLINK,
                ESP_ERR_INVALID_RESPONSE);
            break;
        }
        if (cancellation_requested(composition)) {
            secure_zero(
                &composition->usb_rx_scratch,
                sizeof(composition->usb_rx_scratch));
            break;
        }
        composition->usb_rx_scratch.wire_bytes = transferred;
        if (xQueueSend(
                composition->downlink_handoff_queue,
                &composition->usb_rx_scratch,
                0) != pdTRUE) {
            secure_zero(
                &composition->usb_rx_scratch,
                sizeof(composition->usb_rx_scratch));
            portENTER_CRITICAL(&composition->lock);
            composition->metadata.handoff_overflows++;
            portEXIT_CRITICAL(&composition->lock);
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_HANDOFF_OVERFLOW,
                ESP_ERR_NO_MEM);
            break;
        }
        secure_zero(
            &composition->usb_rx_scratch,
            sizeof(composition->usb_rx_scratch));
        portENTER_CRITICAL(&composition->lock);
        composition->metadata.downlink_wires_received++;
        portEXIT_CRITICAL(&composition->lock);
    }
    secure_zero(
        &composition->usb_rx_scratch,
        sizeof(composition->usb_rx_scratch));
    finish_worker(composition, USB_DOWNLINK_DONE_BIT);
}

static esp_err_t bounded_audio_write(
    void *user_context,
    const int16_t *stereo_values,
    size_t stereo_value_count,
    uint64_t absolute_deadline_us)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)user_context;
    if (composition == NULL || stereo_values == NULL ||
        stereo_value_count != CALL020_MEDIA_STEREO_VALUES ||
        cancellation_requested(composition)) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&composition->lock);
    bool enabled = composition->output_enabled;
    portEXIT_CRITICAL(&composition->lock);
    esp_err_t result = enabled ? ESP_OK : enable_output(composition);
    uint64_t now_us = 0U;
    if (result != ESP_OK || !get_now_us(&now_us) ||
        now_us >= absolute_deadline_us) {
        return result == ESP_OK ? ESP_ERR_TIMEOUT : result;
    }
    size_t bytes_written = 0U;
    result = i2s_channel_write(
        composition->audio.tx_channel,
        stereo_values,
        CALL020_MEDIA_STEREO_BYTES,
        &bytes_written,
        bounded_ticks(
            now_us, absolute_deadline_us,
            composition->audio_io_timeout_us));
    uint64_t completed_us = 0U;
    if (result == ESP_OK &&
        (!get_now_us(&completed_us) || completed_us < now_us ||
         completed_us > absolute_deadline_us)) {
        result = ESP_ERR_TIMEOUT;
    }
    if (result == ESP_OK && bytes_written != CALL020_MEDIA_STEREO_BYTES) {
        result = ESP_ERR_INVALID_SIZE;
    }
    if (result != ESP_OK) {
        pa_force_off(composition);
    }
    return result;
}

static void audio_output_worker(void *argument)
{
    call020_wearable_composition_t *composition =
        (call020_wearable_composition_t *)argument;
    wait_for_start(composition);
    secure_zero(
        &composition->downlink_scratch,
        sizeof(composition->downlink_scratch));

    while (true) {
        uint64_t now_us = 0U;
        if (!worker_can_continue(composition, &now_us)) {
            break;
        }
        if (xQueueReceive(
                composition->downlink_handoff_queue,
                &composition->downlink_scratch,
                queue_poll_ticks()) != pdTRUE) {
            continue;
        }
        if (cancellation_requested(composition)) {
            secure_zero(
                &composition->downlink_scratch,
                sizeof(composition->downlink_scratch));
            break;
        }
        if (!get_now_us(&now_us)) {
            secure_zero(
                &composition->downlink_scratch,
                sizeof(composition->downlink_scratch));
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            break;
        }
        esp_err_t result = call020_media_adapter_core_offer_downlink_wire(
            &composition->downlink_core,
            composition->downlink_scratch.wire,
            composition->downlink_scratch.wire_bytes,
            now_us);
        secure_zero(
            &composition->downlink_scratch,
            sizeof(composition->downlink_scratch));
        if (result != ESP_OK) {
            if (!cancellation_requested(composition)) {
                fail_composition(
                    composition, CALL020_WEARABLE_TERMINAL_DOWNLINK_CORE,
                    result);
            }
            break;
        }

        while (!cancellation_requested(composition)) {
            if (!get_now_us(&now_us)) {
                result = ESP_ERR_INVALID_STATE;
                break;
            }
            result = call020_media_adapter_core_render_downlink(
                &composition->downlink_core,
                now_us,
                bounded_audio_write,
                composition);
            if (result == ESP_OK) {
                portENTER_CRITICAL(&composition->lock);
                composition->metadata.rendered_frames++;
                portEXIT_CRITICAL(&composition->lock);
                break;
            }
            if (result == ESP_ERR_INVALID_STATE &&
                composition->downlink_core.state ==
                    CALL020_MEDIA_CORE_RUNNING &&
                composition->downlink_core.downlink_queue.count > 0U) {
                vTaskDelay(1);
                continue;
            }
            break;
        }
        if (result != ESP_OK) {
            if (!cancellation_requested(composition)) {
                fail_composition(
                    composition,
                    composition->downlink_core.terminal_reason ==
                            CALL020_MEDIA_TERMINAL_AUDIO_OUTPUT
                        ? CALL020_WEARABLE_TERMINAL_AUDIO_OUTPUT
                        : CALL020_WEARABLE_TERMINAL_DOWNLINK_CORE,
                    result);
            }
            break;
        }
    }
    secure_zero(
        &composition->downlink_scratch,
        sizeof(composition->downlink_scratch));
    esp_err_t safe_result = force_output_safe(composition);
    if (safe_result != ESP_OK) {
        fail_composition(
            composition,
            CALL020_WEARABLE_TERMINAL_OUTPUT_SAFETY,
            safe_result);
    }
    finish_worker(composition, AUDIO_OUTPUT_DONE_BIT);
}

static bool create_worker(
    call020_wearable_composition_t *composition,
    TaskFunction_t worker,
    const char *name,
    TaskHandle_t *handle,
    uint32_t done_bit)
{
    portENTER_CRITICAL(&composition->lock);
    composition->created_worker_bits |= done_bit;
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);
    BaseType_t created = xTaskCreate(
        worker,
        name,
        CALL020_WEARABLE_TASK_STACK_BYTES,
        composition,
        CALL020_WEARABLE_TASK_PRIORITY,
        handle);
    if (created != pdPASS) {
        portENTER_CRITICAL(&composition->lock);
        composition->created_worker_bits &= ~done_bit;
        portEXIT_CRITICAL(&composition->lock);
        return false;
    }
    portENTER_CRITICAL(&composition->lock);
    composition->metadata.workers_created++;
    portEXIT_CRITICAL(&composition->lock);
    return true;
}

static void clear_owned_buffers(
    call020_wearable_composition_t *composition)
{
    secure_zero(
        composition->uplink_handoff_queue_storage,
        sizeof(composition->uplink_handoff_queue_storage));
    secure_zero(
        composition->downlink_handoff_queue_storage,
        sizeof(composition->downlink_handoff_queue_storage));
    secure_zero(
        &composition->capture_scratch,
        sizeof(composition->capture_scratch));
    secure_zero(
        &composition->uplink_scratch,
        sizeof(composition->uplink_scratch));
    secure_zero(
        &composition->usb_rx_scratch,
        sizeof(composition->usb_rx_scratch));
    secure_zero(
        &composition->downlink_scratch,
        sizeof(composition->downlink_scratch));
}

const char *call020_wearable_composition_version(void)
{
    return CALL020_WEARABLE_COMPOSITION_VERSION;
}

static esp_err_t composition_install_internal(
    call020_wearable_composition_t *composition,
    const call020_wearable_composition_config_t *config,
    call020_usb_driver_lease_t *usb_driver_lease)
{
    if (composition == NULL || config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (composition->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    size_t uplink_wire_bytes = 0U;
    size_t downlink_wire_bytes = 0U;
    if (!expected_wire_bytes(config, true, &uplink_wire_bytes) ||
        !expected_wire_bytes(config, false, &downlink_wire_bytes) ||
        !config_valid(
            config, uplink_wire_bytes, downlink_wire_bytes)) {
        return config->identity_provenance ==
                CALL020_WEARABLE_IDENTITY_NONPRODUCTION_BUILD_FIXTURE
            ? ESP_ERR_NOT_SUPPORTED
            : ESP_ERR_INVALID_ARG;
    }
    secure_zero(composition, sizeof(*composition));
    composition->lock = (portMUX_TYPE)portMUX_INITIALIZER_UNLOCKED;
    if (!dedicated_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    composition->state = CALL020_WEARABLE_UNINITIALIZED;
    composition->identity_provenance = config->identity_provenance;
    composition->audio_io_timeout_us = config->audio_io_timeout_us;
    composition->usb_read_poll_us = config->usb_read_poll_us;
    composition->join_timeout_us = config->join_timeout_us;
    composition->expected_downlink_wire_bytes = downlink_wire_bytes;
    composition->handoff_queue_frames = config->handoff_queue_frames;
    composition->terminal_reason = CALL020_WEARABLE_TERMINAL_NONE;
    composition->first_error = ESP_OK;
    composition->endpoint_borrowed_from_lease =
        usb_driver_lease != NULL;

    composition->worker_events = xEventGroupCreateStatic(
        &composition->worker_events_storage);
    composition->uplink_handoff_queue = xQueueCreateStatic(
        config->handoff_queue_frames,
        sizeof(call020_wearable_uplink_handoff_t),
        composition->uplink_handoff_queue_storage,
        &composition->uplink_handoff_queue_control);
    composition->downlink_handoff_queue = xQueueCreateStatic(
        config->handoff_queue_frames,
        sizeof(call020_wearable_downlink_handoff_t),
        composition->downlink_handoff_queue_storage,
        &composition->downlink_handoff_queue_control);
    if (composition->worker_events == NULL ||
        composition->uplink_handoff_queue == NULL ||
        composition->downlink_handoff_queue == NULL) {
        if (composition->uplink_handoff_queue != NULL) {
            vQueueDelete(composition->uplink_handoff_queue);
        }
        if (composition->downlink_handoff_queue != NULL) {
            vQueueDelete(composition->downlink_handoff_queue);
        }
        if (composition->worker_events != NULL) {
            vEventGroupDelete(composition->worker_events);
        }
        secure_zero(composition, sizeof(*composition));
        return ESP_ERR_NO_MEM;
    }

    esp_err_t result = pa_prepare_off(composition);
    if (result != ESP_OK) {
        goto fail;
    }
    result = call010_safe_audio_v1_init(
        &composition->audio, CALL020_MEDIA_SAMPLE_RATE_HZ);
    if (result != ESP_OK) {
        goto fail;
    }
    composition->audio_initialized = true;

    esp_codec_dev_sample_info_t format = {
        .sample_rate = CALL020_MEDIA_SAMPLE_RATE_HZ,
        .channel = 2,
        .bits_per_sample = 16,
    };
    result = esp_codec_dev_open(composition->audio.speaker, &format);
    if (result != ESP_OK) {
        goto fail;
    }
    composition->speaker_opened = true;
    result = force_output_safe(composition);
    if (result != ESP_OK) {
        goto fail;
    }
    result = esp_codec_dev_open(composition->audio.microphone, &format);
    if (result != ESP_OK) {
        goto fail;
    }
    composition->microphone_opened = true;
    result = set_output_volume_verified(composition);
    if (result == ESP_OK) {
        result = esp_codec_dev_set_in_gain(
            composition->audio.microphone, CALL020_INPUT_GAIN_DB);
    }
    if (result != ESP_OK) {
        goto fail;
    }

    const call020_media_adapter_config_t core_config = {
        .session_id = config->session_id,
        .device_id = config->device_id,
        .guardian_id = config->guardian_id,
        .uplink_clock_id = config->uplink_clock_id,
        .downlink_clock_id = config->downlink_clock_id,
        .queue_capacity_frames = 1U,
        .frame_deadline_slack_us = config->frame_deadline_slack_us,
        .downlink_playout_delay_us = config->downlink_playout_delay_us,
        .max_runtime_us = config->max_runtime_us,
        .force_pa_off = pa_force_off,
        .pa_user_context = composition,
    };
    result = call020_media_adapter_core_init(
        &composition->uplink_core, &core_config);
    if (result == ESP_OK) {
        result = call020_media_adapter_core_init(
            &composition->downlink_core, &core_config);
    }
    if (result != ESP_OK) {
        goto fail;
    }

    /*
     * Endpoint installation/adoption is deliberately last. Lease adoption is
     * then an atomic final resource step: there is no fallible core/audio
     * setup after the lease enters MEDIA_BORROWED.
     */
    result = usb_driver_lease == NULL
        ? call020_usb_serial_jtag_endpoint_install(
            &composition->endpoint, &config->usb_endpoint)
        : call020_usb_serial_jtag_endpoint_adopt_lease(
            &composition->endpoint,
            &config->usb_endpoint,
            usb_driver_lease);
    if (result != ESP_OK) {
        goto fail;
    }
    composition->endpoint_installed = true;

    composition->initialized = true;
    composition->state = CALL020_WEARABLE_READY;
    portENTER_CRITICAL(&composition->lock);
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);
    return ESP_OK;

fail:
    force_output_safe(composition);
    if (composition->uplink_core.initialized) {
        call020_media_adapter_core_deinit(&composition->uplink_core);
    }
    if (composition->downlink_core.initialized) {
        call020_media_adapter_core_deinit(&composition->downlink_core);
    }
    if (composition->endpoint_installed) {
        result = preserve_first_error(
            result,
            call020_usb_serial_jtag_endpoint_close(&composition->endpoint));
    }
    if (composition->audio_initialized) {
        result = preserve_first_error(
            result, call010_safe_audio_v1_deinit(&composition->audio));
    }
    pa_force_off(composition);
    clear_owned_buffers(composition);
    if (composition->uplink_handoff_queue != NULL) {
        vQueueDelete(composition->uplink_handoff_queue);
    }
    if (composition->downlink_handoff_queue != NULL) {
        vQueueDelete(composition->downlink_handoff_queue);
    }
    if (composition->worker_events != NULL) {
        vEventGroupDelete(composition->worker_events);
    }
    secure_zero(composition, sizeof(*composition));
    return result;
}

esp_err_t call020_wearable_composition_install(
    call020_wearable_composition_t *composition,
    const call020_wearable_composition_config_t *config)
{
    return composition_install_internal(composition, config, NULL);
}

esp_err_t call020_wearable_composition_install_with_usb_driver_lease(
    call020_wearable_composition_t *composition,
    const call020_wearable_composition_config_t *config,
    call020_usb_driver_lease_t *lease)
{
    if (lease == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    return composition_install_internal(composition, config, lease);
}

esp_err_t call020_wearable_composition_start(
    call020_wearable_composition_t *composition)
{
    if (composition == NULL || !composition->initialized ||
        composition->state != CALL020_WEARABLE_READY ||
        (composition->identity_provenance !=
             CALL020_WEARABLE_IDENTITY_OPERATOR_SUPPLIED &&
         composition->identity_provenance !=
             CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL)) {
        return ESP_ERR_INVALID_STATE;
    }
    uint64_t now_us = 0U;
    if (!get_now_us(&now_us) ||
        !checked_add_u64(
            now_us, composition->uplink_core.max_runtime_us,
            &composition->runtime_deadline_us)) {
        return ESP_ERR_INVALID_STATE;
    }
    composition->next_capture_due_us = now_us;
    esp_err_t result = call020_media_adapter_core_start(
        &composition->uplink_core, now_us);
    if (result == ESP_OK) {
        result = call020_media_adapter_core_start(
            &composition->downlink_core, now_us);
    }
    if (result != ESP_OK) {
        fail_composition(
            composition, CALL020_WEARABLE_TERMINAL_CLOCK, result);
        force_output_safe(composition);
        return result;
    }
    portENTER_CRITICAL(&composition->lock);
    composition->state = CALL020_WEARABLE_RUNNING;
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);

    bool created = create_worker(
        composition, audio_capture_worker, "c20f_cap",
        &composition->audio_capture_task, AUDIO_CAPTURE_DONE_BIT);
    created = created && create_worker(
        composition, usb_uplink_worker, "c20f_utx",
        &composition->usb_uplink_task, USB_UPLINK_DONE_BIT);
    created = created && create_worker(
        composition, usb_downlink_worker, "c20f_urx",
        &composition->usb_downlink_task, USB_DOWNLINK_DONE_BIT);
    created = created && create_worker(
        composition, audio_output_worker, "c20f_play",
        &composition->audio_output_task, AUDIO_OUTPUT_DONE_BIT);
    if (!created) {
        fail_composition(
            composition, CALL020_WEARABLE_TERMINAL_WORKER_CREATE,
            ESP_ERR_NO_MEM);
        force_output_safe(composition);
        return ESP_ERR_NO_MEM;
    }
    xEventGroupSetBits(composition->worker_events, WORKER_START_BIT);
    return ESP_OK;
}

esp_err_t call020_wearable_composition_request_cancel(
    call020_wearable_composition_t *composition)
{
    if (composition == NULL || !composition->initialized ||
        composition->state == CALL020_WEARABLE_CLOSED) {
        return ESP_ERR_INVALID_ARG;
    }
    set_cancel_and_wake(composition, false);
    return ESP_OK;
}

esp_err_t call020_wearable_composition_force_safe(
    call020_wearable_composition_t *composition)
{
    if (composition == NULL || !composition->initialized ||
        composition->state == CALL020_WEARABLE_CLOSED) {
        return ESP_ERR_INVALID_ARG;
    }
    set_cancel_and_wake(composition, false);
    return force_output_safe(composition);
}

esp_err_t call020_wearable_composition_join(
    call020_wearable_composition_t *composition)
{
    if (composition == NULL || !composition->initialized ||
        composition->worker_events == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&composition->lock);
    uint32_t expected_bits = composition->created_worker_bits;
    portEXIT_CRITICAL(&composition->lock);
    if (expected_bits == 0U) {
        portENTER_CRITICAL(&composition->lock);
        if (composition->state == CALL020_WEARABLE_STOPPING) {
            composition->state = CALL020_WEARABLE_STOPPED;
        }
        sync_metadata_locked(composition);
        portEXIT_CRITICAL(&composition->lock);
        return ESP_OK;
    }

    uint64_t now_us = 0U;
    uint64_t deadline_us = 0U;
    if (!get_now_us(&now_us) ||
        !checked_add_u64(
            now_us, composition->join_timeout_us, &deadline_us)) {
        fail_composition(
            composition, CALL020_WEARABLE_TERMINAL_CLOCK,
            ESP_ERR_INVALID_STATE);
        return ESP_ERR_INVALID_STATE;
    }
    uint64_t previous_now_us = now_us;
    while (true) {
        EventBits_t completed = xEventGroupGetBits(
            composition->worker_events);
        if ((completed & expected_bits) == expected_bits) {
            break;
        }
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_CLOCK,
                ESP_ERR_INVALID_STATE);
            force_output_safe(composition);
            return ESP_ERR_INVALID_STATE;
        }
        previous_now_us = now_us;
        if (now_us >= deadline_us) {
            portENTER_CRITICAL(&composition->lock);
            composition->metadata.join_timeouts++;
            portEXIT_CRITICAL(&composition->lock);
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_JOIN_TIMEOUT,
                ESP_ERR_TIMEOUT);
            force_output_safe(composition);
            return ESP_ERR_TIMEOUT;
        }
        TickType_t ticks = bounded_ticks(
            now_us, deadline_us, UINT64_C(20000));
        xEventGroupWaitBits(
            composition->worker_events,
            expected_bits,
            pdFALSE,
            pdTRUE,
            ticks);
        if (ticks == 0) {
            taskYIELD();
        }
    }

    composition->audio_capture_task = NULL;
    composition->usb_uplink_task = NULL;
    composition->usb_downlink_task = NULL;
    composition->audio_output_task = NULL;
    portENTER_CRITICAL(&composition->lock);
    if (composition->state == CALL020_WEARABLE_STOPPING ||
        composition->state == CALL020_WEARABLE_RUNNING) {
        composition->state = CALL020_WEARABLE_STOPPED;
    }
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);
    return ESP_OK;
}

esp_err_t call020_wearable_composition_close(
    call020_wearable_composition_t *composition)
{
    if (composition == NULL || !composition->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    if (composition->state == CALL020_WEARABLE_CLOSED) {
        return ESP_OK;
    }
    esp_err_t result = call020_wearable_composition_request_cancel(
        composition);
    esp_err_t join_result = call020_wearable_composition_join(composition);
    result = preserve_first_error(result, join_result);
    esp_err_t safe_result = force_output_safe(composition);
    result = preserve_first_error(result, safe_result);
    if (safe_result != ESP_OK &&
        composition->terminal_reason == CALL020_WEARABLE_TERMINAL_NONE) {
        fail_composition(
            composition,
            CALL020_WEARABLE_TERMINAL_OUTPUT_SAFETY,
            safe_result);
    }
    if (join_result != ESP_OK) {
        return result;
    }

    portENTER_CRITICAL(&composition->lock);
    esp_err_t terminal_error = composition->first_error;
    portEXIT_CRITICAL(&composition->lock);
    result = preserve_first_error(terminal_error, result);

    if (composition->endpoint_installed) {
        esp_err_t endpoint_result =
            call020_usb_serial_jtag_endpoint_close(&composition->endpoint);
        if (endpoint_result != ESP_OK) {
            fail_composition(
                composition, CALL020_WEARABLE_TERMINAL_ENDPOINT_CLOSE,
                endpoint_result);
            force_output_safe(composition);
            return preserve_first_error(result, endpoint_result);
        }
        composition->endpoint_installed = false;
    }

    if (composition->uplink_core.initialized) {
        result = preserve_first_error(
            result,
            call020_media_adapter_core_stop(&composition->uplink_core));
        result = preserve_first_error(
            result,
            call020_media_adapter_core_deinit(&composition->uplink_core));
    }
    if (composition->downlink_core.initialized) {
        result = preserve_first_error(
            result,
            call020_media_adapter_core_stop(&composition->downlink_core));
        result = preserve_first_error(
            result,
            call020_media_adapter_core_deinit(&composition->downlink_core));
    }
    safe_result = force_output_safe(composition);
    result = preserve_first_error(result, safe_result);
    if (safe_result != ESP_OK &&
        composition->terminal_reason == CALL020_WEARABLE_TERMINAL_NONE) {
        composition->terminal_reason =
            CALL020_WEARABLE_TERMINAL_OUTPUT_SAFETY;
        composition->first_error = safe_result;
    }
    if (composition->audio_initialized) {
        esp_err_t audio_result = call010_safe_audio_v1_deinit(
            &composition->audio);
        result = preserve_first_error(result, audio_result);
        composition->audio_initialized = false;
        composition->speaker_opened = false;
        composition->microphone_opened = false;
        if (audio_result != ESP_OK &&
            composition->terminal_reason ==
                CALL020_WEARABLE_TERMINAL_NONE) {
            composition->terminal_reason =
                CALL020_WEARABLE_TERMINAL_AUDIO_CLOSE;
            composition->first_error = audio_result;
        }
    }
    result = preserve_first_error(result, pa_force_off(composition));

    if (composition->uplink_handoff_queue != NULL) {
        vQueueDelete(composition->uplink_handoff_queue);
        composition->uplink_handoff_queue = NULL;
    }
    if (composition->downlink_handoff_queue != NULL) {
        vQueueDelete(composition->downlink_handoff_queue);
        composition->downlink_handoff_queue = NULL;
    }
    if (composition->worker_events != NULL) {
        vEventGroupDelete(composition->worker_events);
        composition->worker_events = NULL;
    }
    clear_owned_buffers(composition);

    portENTER_CRITICAL(&composition->lock);
    composition->state = CALL020_WEARABLE_CLOSED;
    composition->metadata.endpoint_installed = false;
    sync_metadata_locked(composition);
    portEXIT_CRITICAL(&composition->lock);
    return result;
}

esp_err_t call020_wearable_composition_get_metadata(
    call020_wearable_composition_t *composition,
    call020_wearable_composition_metadata_t *metadata)
{
    if (composition == NULL || metadata == NULL ||
        !composition->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&composition->lock);
    sync_metadata_locked(composition);
    *metadata = composition->metadata;
    portEXIT_CRITICAL(&composition->lock);
    return ESP_OK;
}
