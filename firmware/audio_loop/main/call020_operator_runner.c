/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020G link-retained operator API. Linking has no device-side effect.
 * Only an explicit call to start may install audio or USB resources.
 */

#include "call020_operator_runner.h"

#include <string.h>

#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "sdkconfig.h"

#if defined(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER) && \
    CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER
#if !defined(CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION) || \
    !CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION
#error "CALL-020G requires CALL-020F wearable composition"
#endif
#if !defined(CONFIG_ESP_CONSOLE_NONE) || !CONFIG_ESP_CONSOLE_NONE
#error "CALL-020G requires CONFIG_ESP_CONSOLE_NONE"
#endif
#if !defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) || \
    !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "CALL-020G requires CONFIG_ESP_CONSOLE_SECONDARY_NONE"
#endif
#if !defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) || \
    !CONFIG_LOG_DEFAULT_LEVEL_NONE
#error "CALL-020G requires CONFIG_LOG_DEFAULT_LEVEL_NONE"
#endif
#if !defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) || \
    !CONFIG_BOOTLOADER_LOG_LEVEL_NONE
#error "CALL-020G requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE"
#endif
#if defined(CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) && \
    CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN
#error "CALL-020G cannot coexist with CALL-010 autorun"
#endif
#if !defined(CONFIG_FREERTOS_PLACE_FUNCTIONS_INTO_FLASH) || \
    !CONFIG_FREERTOS_PLACE_FUNCTIONS_INTO_FLASH
#error "CALL-020G requires selected non-ISR FreeRTOS functions in flash"
#endif
#if !defined(CONFIG_RINGBUF_PLACE_FUNCTIONS_INTO_FLASH) || \
    !CONFIG_RINGBUF_PLACE_FUNCTIONS_INTO_FLASH
#error "CALL-020G requires non-ISR ring-buffer functions in flash"
#endif
#if defined(CONFIG_RINGBUF_PLACE_ISR_FUNCTIONS_INTO_FLASH) && \
    CONFIG_RINGBUF_PLACE_ISR_FUNCTIONS_INTO_FLASH
#error "CALL-020G must retain ISR ring-buffer functions in internal RAM"
#endif
#endif

#define CALL020_OPERATOR_IDENTITY_TEXT_BYTES \
    (UINT32_C(2) + CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES * UINT32_C(2))
#define CALL020_OPERATOR_EXPECTED_WIRE_BYTES \
    (CALL020_MEDIA_WIRE_HEADER_BYTES + CALL020_MEDIA_MONO_BYTES + \
     CALL020_MEDIA_WIRE_CRC_BYTES + \
     UINT32_C(4) * CALL020_OPERATOR_IDENTITY_TEXT_BYTES)

_Static_assert(
    CALL020_OPERATOR_IDENTITY_CAPACITY >
        CALL020_OPERATOR_IDENTITY_TEXT_BYTES,
    "ephemeral identity buffer must include its NUL terminator");
_Static_assert(
    CALL020_OPERATOR_EXPECTED_WIRE_BYTES <=
        CALL020_MEDIA_WIRE_MAX_BYTES,
    "runner identity must fit the frozen EGLM wire bound");
_Static_assert(
    UINT32_C(2) * CALL020_OPERATOR_EXPECTED_WIRE_BYTES <=
        CALL020_OPERATOR_USB_BUFFER_MAX_BYTES,
    "runner USB cap must hold at least two complete wires");
_Static_assert(
    CALL020_OPERATOR_USB_BUFFER_MAX_BYTES <=
        CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES,
    "runner cap must remain inside the endpoint contract");

typedef struct {
    call020_wearable_composition_t composition;
    call020_operator_runner_config_t config;
    call020_operator_session_descriptor_t descriptor;
    call020_operator_runner_metadata_t metadata;
    bool composition_initialized;
} call020_operator_runner_context_t;

/*
 * This object is intentionally global/internal DRAM. In particular, the
 * 43 KiB-plus composition is never an automatic variable or task-stack local.
 */
static call020_operator_runner_context_t s_runner;
static portMUX_TYPE s_runner_lock = portMUX_INITIALIZER_UNLOCKED;

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

static bool dedicated_runner_build_enabled(void)
{
#if defined(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER) && \
    CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER && \
    defined(CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION) && \
    CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION && \
    defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) && \
    CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT && \
    defined(CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE) && \
    CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE && \
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

static bool runner_config_valid(
    const call020_operator_runner_config_t *config)
{
    if (config == NULL) {
        return false;
    }
    uint64_t endpoint_slice_us =
        (uint64_t)config->usb_endpoint.io_wait_slice_ms * UINT64_C(1000);
    return config->handoff_queue_frames > 0U &&
        config->handoff_queue_frames <=
            CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES &&
        config->frame_deadline_slack_us >= UINT64_C(20000) &&
        config->frame_deadline_slack_us <= UINT64_C(1000000) &&
        config->downlink_playout_delay_us <= UINT64_C(1000000) &&
        config->max_runtime_us >= UINT64_C(20000) &&
        config->max_runtime_us <= CALL020_MEDIA_MAX_RUNTIME_US &&
        config->audio_io_timeout_us >= UINT64_C(20000) &&
        config->audio_io_timeout_us <=
            CALL020_WEARABLE_AUDIO_IO_TIMEOUT_MAX_US &&
        config->usb_read_poll_us > 0U &&
        config->usb_read_poll_us <=
            CALL020_WEARABLE_USB_READ_POLL_MAX_US &&
        config->join_timeout_us >= UINT64_C(200000) &&
        config->join_timeout_us <= CALL020_WEARABLE_JOIN_TIMEOUT_MAX_US &&
        config->usb_endpoint.io_wait_slice_ms > 0U &&
        config->usb_endpoint.io_wait_slice_ms <=
            CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS &&
        config->usb_endpoint.max_operation_us >=
            config->frame_deadline_slack_us &&
        config->usb_endpoint.max_operation_us >=
            config->usb_read_poll_us &&
        config->usb_endpoint.max_operation_us <=
            CALL020_USB_ENDPOINT_MAX_OPERATION_US &&
        config->usb_endpoint.close_timeout_us >= endpoint_slice_us &&
        config->usb_endpoint.close_timeout_us <=
            CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US &&
        config->usb_endpoint.tx_buffer_bytes >=
            UINT32_C(2) * CALL020_OPERATOR_EXPECTED_WIRE_BYTES &&
        config->usb_endpoint.tx_buffer_bytes <=
            CALL020_OPERATOR_USB_BUFFER_MAX_BYTES &&
        config->usb_endpoint.rx_buffer_bytes >=
            UINT32_C(2) * CALL020_OPERATOR_EXPECTED_WIRE_BYTES &&
        config->usb_endpoint.rx_buffer_bytes <=
            CALL020_OPERATOR_USB_BUFFER_MAX_BYTES;
}

static bool nonce_is_nonzero(
    const uint8_t nonce[CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES])
{
    uint8_t combined = 0U;
    for (size_t index = 0U;
         index < CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES;
         ++index) {
        combined |= nonce[index];
    }
    return combined != 0U;
}

static void format_identity(
    char role,
    const uint8_t nonce[CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES],
    char output[CALL020_OPERATOR_IDENTITY_CAPACITY])
{
    static const char hex[] = "0123456789abcdef";
    output[0] = role;
    output[1] = ':';
    for (size_t index = 0U;
         index < CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES;
         ++index) {
        output[2U + index * 2U] = hex[nonce[index] >> 4U];
        output[3U + index * 2U] = hex[nonce[index] & UINT8_C(0x0f)];
    }
    output[CALL020_OPERATOR_IDENTITY_TEXT_BYTES] = '\0';
}

static bool generate_descriptor(
    call020_operator_session_descriptor_t *descriptor,
    uint32_t *attempts)
{
    if (descriptor == NULL || attempts == NULL) {
        return false;
    }
    uint8_t nonce[CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES] = {0};
    bool generated = false;
    *attempts = 0U;
    for (uint32_t attempt = 0U;
         attempt < CALL020_OPERATOR_RANDOM_ATTEMPTS;
         ++attempt) {
        ++*attempts;
        esp_fill_random(nonce, sizeof(nonce));
        if (nonce_is_nonzero(nonce)) {
            generated = true;
            break;
        }
    }
    if (generated) {
        secure_zero(descriptor, sizeof(*descriptor));
        format_identity('s', nonce, descriptor->session_id);
        format_identity('d', nonce, descriptor->device_id);
        format_identity('g', nonce, descriptor->guardian_id);
        format_identity('u', nonce, descriptor->uplink_clock_id);
        format_identity('v', nonce, descriptor->downlink_clock_id);
        descriptor->nonce_bits =
            CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES * UINT32_C(8);
        descriptor->random_source =
            CALL020_OPERATOR_RANDOM_SOURCE_ESP_FILL_RANDOM;
        descriptor->random_quality =
            CALL020_OPERATOR_RANDOM_QUALITY_UNVERIFIED;
        descriptor->correlated_routing_ids = true;
        descriptor->provenance =
            CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL;
    }
    secure_zero(nonce, sizeof(nonce));
    return generated;
}

static bool state_has_resources(void)
{
    portENTER_CRITICAL(&s_runner_lock);
    bool initialized = s_runner.composition_initialized;
    portEXIT_CRITICAL(&s_runner_lock);
    return initialized;
}

static void latch_failure(esp_err_t error)
{
    portENTER_CRITICAL(&s_runner_lock);
    if (s_runner.metadata.first_error == ESP_OK && error != ESP_OK) {
        s_runner.metadata.first_error = error;
    }
    s_runner.metadata.state = CALL020_OPERATOR_TERMINAL;
    portEXIT_CRITICAL(&s_runner_lock);
}

static esp_err_t force_safe_if_installed(void)
{
    if (!state_has_resources()) {
        return ESP_OK;
    }
    esp_err_t result = call020_wearable_composition_force_safe(
        &s_runner.composition);
    portENTER_CRITICAL(&s_runner_lock);
    s_runner.metadata.safety_forced = result == ESP_OK;
    portEXIT_CRITICAL(&s_runner_lock);
    return result;
}

static bool on_owner_core(void)
{
    portENTER_CRITICAL(&s_runner_lock);
    int owner_core_id = s_runner.metadata.owner_core_id;
    portEXIT_CRITICAL(&s_runner_lock);
    return owner_core_id >= 0 && (int)xPortGetCoreID() == owner_core_id;
}

static esp_err_t reject_wrong_core(void)
{
    esp_err_t safe_result = force_safe_if_installed();
    esp_err_t result = preserve_first_error(
        ESP_ERR_INVALID_STATE, safe_result);
    latch_failure(result);
    return result;
}

static void copy_composition_metadata(void)
{
    if (!state_has_resources()) {
        return;
    }
    call020_wearable_composition_metadata_t metadata = {0};
    if (call020_wearable_composition_get_metadata(
            &s_runner.composition, &metadata) == ESP_OK) {
        portENTER_CRITICAL(&s_runner_lock);
        s_runner.metadata.composition = metadata;
        s_runner.metadata.usb_driver_lease_borrowed =
            metadata.usb_driver_ownership ==
                CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED;
        s_runner.metadata.usb_driver_binding_closed =
            metadata.usb_driver_binding_closed;
        s_runner.metadata.usb_driver_lease_returned =
            metadata.usb_driver_lease_returned;
        s_runner.metadata.usb_driver_lease_generation =
            metadata.usb_driver_lease_generation;
        s_runner.metadata.usb_driver_uninstalled_by_runner =
            metadata.usb_driver_uninstalled_by_composition;
        portEXIT_CRITICAL(&s_runner_lock);
    }
}

const char *call020_operator_runner_version(void)
{
    return CALL020_OPERATOR_RUNNER_VERSION;
}

esp_err_t call020_operator_runner_prepare(
    const call020_operator_runner_config_t *config,
    call020_operator_session_descriptor_t *descriptor)
{
    if (!dedicated_runner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (config == NULL || descriptor == NULL ||
        !runner_config_valid(config)) {
        esp_err_t safe_result = force_safe_if_installed();
        esp_err_t result = preserve_first_error(
            ESP_ERR_INVALID_ARG, safe_result);
        if (state_has_resources()) {
            latch_failure(result);
        }
        return result;
    }

    portENTER_CRITICAL(&s_runner_lock);
    call020_operator_runner_state_t prior_state = s_runner.metadata.state;
    bool resources = s_runner.composition_initialized;
    portEXIT_CRITICAL(&s_runner_lock);
    if (resources ||
        (prior_state != CALL020_OPERATOR_DORMANT &&
         prior_state != CALL020_OPERATOR_CLOSED &&
         prior_state != CALL020_OPERATOR_TERMINAL)) {
        esp_err_t safe_result = force_safe_if_installed();
        esp_err_t result = preserve_first_error(
            ESP_ERR_INVALID_STATE, safe_result);
        latch_failure(result);
        return result;
    }

    secure_zero(&s_runner, sizeof(s_runner));
    s_runner.metadata.owner_core_id = (int)xPortGetCoreID();
    s_runner.metadata.prepare_calls = 1U;
    uint32_t attempts = 0U;
    if (!generate_descriptor(&s_runner.descriptor, &attempts)) {
        s_runner.metadata.random_attempts = attempts;
        latch_failure(ESP_FAIL);
        return ESP_FAIL;
    }
    s_runner.config = *config;
    s_runner.metadata.random_attempts = attempts;
    s_runner.metadata.identities_generated = true;
    s_runner.metadata.first_error = ESP_OK;
    s_runner.metadata.state = CALL020_OPERATOR_PREPARED;
    *descriptor = s_runner.descriptor;
    return ESP_OK;
}

static esp_err_t runner_start_internal(
    call020_usb_driver_lease_t *usb_driver_lease)
{
    if (!dedicated_runner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (!on_owner_core()) {
        return reject_wrong_core();
    }
    portENTER_CRITICAL(&s_runner_lock);
    bool prepared =
        s_runner.metadata.state == CALL020_OPERATOR_PREPARED &&
        s_runner.metadata.identities_generated &&
        !s_runner.composition_initialized;
    if (prepared) {
        s_runner.metadata.state = CALL020_OPERATOR_STARTING;
        s_runner.metadata.start_calls++;
        s_runner.metadata.start_requested = true;
        s_runner.metadata.usb_driver_lease_supplied =
            usb_driver_lease != NULL;
    }
    portEXIT_CRITICAL(&s_runner_lock);
    if (!prepared) {
        esp_err_t safe_result = force_safe_if_installed();
        esp_err_t result = preserve_first_error(
            ESP_ERR_INVALID_STATE, safe_result);
        latch_failure(result);
        return result;
    }

    const call020_wearable_composition_config_t composition_config = {
        .session_id = s_runner.descriptor.session_id,
        .device_id = s_runner.descriptor.device_id,
        .guardian_id = s_runner.descriptor.guardian_id,
        .uplink_clock_id = s_runner.descriptor.uplink_clock_id,
        .downlink_clock_id = s_runner.descriptor.downlink_clock_id,
        .identity_provenance =
            CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL,
        .handoff_queue_frames = s_runner.config.handoff_queue_frames,
        .frame_deadline_slack_us =
            s_runner.config.frame_deadline_slack_us,
        .downlink_playout_delay_us =
            s_runner.config.downlink_playout_delay_us,
        .max_runtime_us = s_runner.config.max_runtime_us,
        .audio_io_timeout_us = s_runner.config.audio_io_timeout_us,
        .usb_read_poll_us = s_runner.config.usb_read_poll_us,
        .join_timeout_us = s_runner.config.join_timeout_us,
        .usb_endpoint = s_runner.config.usb_endpoint,
    };
    esp_err_t result = usb_driver_lease == NULL
        ? call020_wearable_composition_install(
            &s_runner.composition, &composition_config)
        : call020_wearable_composition_install_with_usb_driver_lease(
            &s_runner.composition,
            &composition_config,
            usb_driver_lease);
    if (result == ESP_OK) {
        portENTER_CRITICAL(&s_runner_lock);
        s_runner.composition_initialized = true;
        s_runner.metadata.composition_installed = true;
        portEXIT_CRITICAL(&s_runner_lock);
        result = call020_wearable_composition_start(
            &s_runner.composition);
    }
    if (result != ESP_OK) {
        esp_err_t safe_result = force_safe_if_installed();
        result = preserve_first_error(result, safe_result);
        if (state_has_resources()) {
            result = preserve_first_error(
                result,
                call020_wearable_composition_close(
                    &s_runner.composition));
            copy_composition_metadata();
        }
        latch_failure(result);
        return result;
    }

    portENTER_CRITICAL(&s_runner_lock);
    s_runner.metadata.state = CALL020_OPERATOR_RUNNING;
    portEXIT_CRITICAL(&s_runner_lock);
    copy_composition_metadata();
    return ESP_OK;
}

esp_err_t call020_operator_runner_start(void)
{
    return runner_start_internal(NULL);
}

esp_err_t call020_operator_runner_start_with_usb_driver_lease(
    call020_usb_driver_lease_t *lease)
{
    if (lease == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    return runner_start_internal(lease);
}

esp_err_t call020_operator_runner_cancel(void)
{
    if (!dedicated_runner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (!on_owner_core()) {
        return reject_wrong_core();
    }
    portENTER_CRITICAL(&s_runner_lock);
    s_runner.metadata.cancel_calls++;
    bool resources = s_runner.composition_initialized;
    if (!resources &&
        s_runner.metadata.state == CALL020_OPERATOR_PREPARED) {
        s_runner.metadata.state = CALL020_OPERATOR_JOINED;
    } else if (resources) {
        s_runner.metadata.state = CALL020_OPERATOR_STOPPING;
    }
    portEXIT_CRITICAL(&s_runner_lock);
    if (!resources) {
        return ESP_OK;
    }
    esp_err_t result = force_safe_if_installed();
    copy_composition_metadata();
    if (result != ESP_OK) {
        latch_failure(result);
    }
    return result;
}

esp_err_t call020_operator_runner_join(void)
{
    if (!dedicated_runner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (!on_owner_core()) {
        return reject_wrong_core();
    }
    portENTER_CRITICAL(&s_runner_lock);
    s_runner.metadata.join_calls++;
    bool resources = s_runner.composition_initialized;
    call020_operator_runner_state_t state = s_runner.metadata.state;
    portEXIT_CRITICAL(&s_runner_lock);
    if (!resources) {
        if (state == CALL020_OPERATOR_PREPARED ||
            state == CALL020_OPERATOR_JOINED) {
            portENTER_CRITICAL(&s_runner_lock);
            s_runner.metadata.state = CALL020_OPERATOR_JOINED;
            portEXIT_CRITICAL(&s_runner_lock);
            return ESP_OK;
        }
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t result = call020_wearable_composition_join(
        &s_runner.composition);
    if (result != ESP_OK) {
        result = preserve_first_error(
            result, force_safe_if_installed());
        latch_failure(result);
    } else {
        portENTER_CRITICAL(&s_runner_lock);
        if (s_runner.metadata.state != CALL020_OPERATOR_TERMINAL) {
            s_runner.metadata.state = CALL020_OPERATOR_JOINED;
        }
        portEXIT_CRITICAL(&s_runner_lock);
    }
    copy_composition_metadata();
    return result;
}

esp_err_t call020_operator_runner_close(void)
{
    if (!dedicated_runner_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (!on_owner_core()) {
        return reject_wrong_core();
    }
    portENTER_CRITICAL(&s_runner_lock);
    s_runner.metadata.close_calls++;
    bool resources = s_runner.composition_initialized;
    call020_operator_runner_metadata_t final_metadata = s_runner.metadata;
    portEXIT_CRITICAL(&s_runner_lock);

    esp_err_t result = ESP_OK;
    if (resources) {
        result = force_safe_if_installed();
        result = preserve_first_error(
            result,
            call020_wearable_composition_close(
                &s_runner.composition));
        copy_composition_metadata();
        final_metadata = s_runner.metadata;
        final_metadata.composition = s_runner.metadata.composition;
        if (s_runner.composition.state != CALL020_WEARABLE_CLOSED) {
            latch_failure(result == ESP_OK ? ESP_FAIL : result);
            return result == ESP_OK ? ESP_FAIL : result;
        }
    }

    final_metadata.state = CALL020_OPERATOR_CLOSED;
    final_metadata.resources_closed = true;
    final_metadata.composition_installed = false;
    final_metadata.first_error = preserve_first_error(
        final_metadata.first_error, result);
    secure_zero(&s_runner, sizeof(s_runner));
    s_runner.metadata = final_metadata;
    return result;
}

esp_err_t call020_operator_runner_get_descriptor(
    call020_operator_session_descriptor_t *descriptor)
{
    if (descriptor == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_runner_lock);
    bool available = s_runner.metadata.identities_generated &&
        s_runner.metadata.state != CALL020_OPERATOR_CLOSED &&
        s_runner.metadata.state != CALL020_OPERATOR_DORMANT;
    if (available) {
        *descriptor = s_runner.descriptor;
    }
    portEXIT_CRITICAL(&s_runner_lock);
    if (!available) {
        secure_zero(descriptor, sizeof(*descriptor));
        return ESP_ERR_INVALID_STATE;
    }
    return ESP_OK;
}

esp_err_t call020_operator_runner_get_metadata(
    call020_operator_runner_metadata_t *metadata)
{
    if (metadata == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    copy_composition_metadata();
    portENTER_CRITICAL(&s_runner_lock);
    *metadata = s_runner.metadata;
    portEXIT_CRITICAL(&s_runner_lock);
    return ESP_OK;
}

static const call020_operator_runner_api_t s_retained_api = {
    .api_version = CALL020_OPERATOR_RUNNER_API_VERSION,
    .prepare = call020_operator_runner_prepare,
    .start = call020_operator_runner_start,
    .cancel = call020_operator_runner_cancel,
    .join = call020_operator_runner_join,
    .close = call020_operator_runner_close,
    .get_descriptor = call020_operator_runner_get_descriptor,
    .get_metadata = call020_operator_runner_get_metadata,
};

const call020_operator_runner_api_t *
call020_operator_runner_retained_entry(void)
{
    return &s_retained_api;
}
