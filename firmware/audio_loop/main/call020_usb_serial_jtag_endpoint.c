/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020E dedicated USB Serial/JTAG ordered-byte endpoint. It is compiled
 * for review but remains default-disabled and uninstantiated by app_main.
 */

#include "call020_usb_serial_jtag_endpoint.h"

#include <limits.h>
#include <string.h>

#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#if defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) && \
    CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT
#if !defined(CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE) || \
    !CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE
#error "CALL-020E requires the CALL-020D media adapter core"
#endif
#if !defined(CONFIG_ESP_CONSOLE_NONE) || !CONFIG_ESP_CONSOLE_NONE
#error "CALL-020E requires CONFIG_ESP_CONSOLE_NONE"
#endif
#if !defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) || \
    !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "CALL-020E requires CONFIG_ESP_CONSOLE_SECONDARY_NONE"
#endif
#if !defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) || \
    !CONFIG_LOG_DEFAULT_LEVEL_NONE
#error "CALL-020E requires CONFIG_LOG_DEFAULT_LEVEL_NONE"
#endif
#if !defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) || \
    !CONFIG_BOOTLOADER_LOG_LEVEL_NONE
#error "CALL-020E requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE"
#endif
#endif

typedef enum {
    OPERATION_READ = 0,
    OPERATION_WRITE,
} operation_direction_t;

typedef enum {
    DRIVER_OWNER_NONE = 0,
    DRIVER_OWNER_ENDPOINT_INSTALLING,
    DRIVER_OWNER_ENDPOINT_ACTIVE,
    DRIVER_OWNER_LEASE_INSTALLING,
    DRIVER_OWNER_LEASE_ACTIVE,
} driver_owner_kind_t;

/*
 * ESP-IDF exposes one process-wide USB Serial/JTAG driver instance. This
 * registry is deliberately private: public lease fields alone never prove
 * ownership of an arbitrary already-installed driver.
 */
static portMUX_TYPE s_driver_registry_lock = portMUX_INITIALIZER_UNLOCKED;
static driver_owner_kind_t s_driver_owner_kind = DRIVER_OWNER_NONE;
static void *s_driver_owner_context;
static uint64_t s_driver_owner_generation;
static call020_usb_endpoint_config_t s_driver_owner_config;
static bool s_driver_owner_config_bound;
static uint64_t s_next_driver_generation;
#if defined(CALL020_USB_ENDPOINT_TEST_HOOKS)
/* Native fake only; no Kconfig path enables this in an ESP-IDF image. */
static bool s_test_reject_next_owner_activation;
#endif

static void secure_zero(void *memory, size_t bytes)
{
    volatile uint8_t *cursor = (volatile uint8_t *)memory;
    while (bytes > 0U) {
        *cursor++ = 0U;
        --bytes;
    }
}

static bool dedicated_build_enabled(void)
{
#if defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) && \
    CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT && \
    defined(CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE) && \
    CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE && \
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

static bool config_valid(const call020_usb_endpoint_config_t *config)
{
    if (config == NULL) {
        return false;
    }
    uint64_t slice_us = (uint64_t)config->io_wait_slice_ms * UINT64_C(1000);
    return config->tx_buffer_bytes >=
            CALL020_USB_ENDPOINT_MIN_DRIVER_BUFFER_BYTES &&
        config->tx_buffer_bytes <=
            CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES &&
        config->rx_buffer_bytes >=
            CALL020_USB_ENDPOINT_MIN_DRIVER_BUFFER_BYTES &&
        config->rx_buffer_bytes <=
            CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES &&
        config->io_wait_slice_ms > 0U &&
        config->io_wait_slice_ms <= CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS &&
        config->max_operation_us >= slice_us &&
        config->max_operation_us <= CALL020_USB_ENDPOINT_MAX_OPERATION_US &&
        config->close_timeout_us >= slice_us &&
        config->close_timeout_us <=
            CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US;
}

static bool config_equal(
    const call020_usb_endpoint_config_t *left,
    const call020_usb_endpoint_config_t *right)
{
    return left != NULL && right != NULL &&
        left->tx_buffer_bytes == right->tx_buffer_bytes &&
        left->rx_buffer_bytes == right->rx_buffer_bytes &&
        left->io_wait_slice_ms == right->io_wait_slice_ms &&
        left->max_operation_us == right->max_operation_us &&
        left->close_timeout_us == right->close_timeout_us;
}

static bool reserve_driver_owner(
    driver_owner_kind_t installing_kind,
    void *owner_context,
    const call020_usb_endpoint_config_t *config,
    uint64_t *generation)
{
    if ((installing_kind != DRIVER_OWNER_ENDPOINT_INSTALLING &&
         installing_kind != DRIVER_OWNER_LEASE_INSTALLING) ||
        owner_context == NULL || config == NULL || generation == NULL) {
        return false;
    }
    bool reserved = false;
    portENTER_CRITICAL(&s_driver_registry_lock);
    if (s_driver_owner_kind == DRIVER_OWNER_NONE &&
        s_driver_owner_context == NULL &&
        !s_driver_owner_config_bound &&
        s_next_driver_generation != UINT64_MAX) {
        ++s_next_driver_generation;
        s_driver_owner_kind = installing_kind;
        s_driver_owner_context = owner_context;
        s_driver_owner_generation = s_next_driver_generation;
        s_driver_owner_config = *config;
        s_driver_owner_config_bound = true;
        *generation = s_driver_owner_generation;
        reserved = true;
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return reserved;
}

static bool activate_driver_owner(
    driver_owner_kind_t installing_kind,
    driver_owner_kind_t active_kind,
    void *owner_context,
    uint64_t generation)
{
    bool activated = false;
    portENTER_CRITICAL(&s_driver_registry_lock);
    bool reject_for_test = false;
#if defined(CALL020_USB_ENDPOINT_TEST_HOOKS)
    reject_for_test = s_test_reject_next_owner_activation;
    s_test_reject_next_owner_activation = false;
#endif
    if (!reject_for_test && s_driver_owner_kind == installing_kind &&
        s_driver_owner_context == owner_context &&
        s_driver_owner_generation == generation && generation != 0U) {
        s_driver_owner_kind = active_kind;
        activated = true;
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return activated;
}

static bool release_driver_owner(
    driver_owner_kind_t expected_kind,
    void *owner_context,
    uint64_t generation)
{
    bool released = false;
    portENTER_CRITICAL(&s_driver_registry_lock);
    if (s_driver_owner_kind == expected_kind &&
        s_driver_owner_context == owner_context &&
        s_driver_owner_generation == generation && generation != 0U) {
        s_driver_owner_kind = DRIVER_OWNER_NONE;
        s_driver_owner_context = NULL;
        s_driver_owner_generation = 0U;
        s_driver_owner_config = (call020_usb_endpoint_config_t){0};
        s_driver_owner_config_bound = false;
        released = true;
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return released;
}

static void sync_lease_metadata(call020_usb_driver_lease_t *lease)
{
    lease->metadata.state = lease->state;
    lease->metadata.terminal_reason = lease->terminal_reason;
    lease->metadata.generation = lease->generation;
    lease->metadata.owner_core_id = lease->owner_core_id;
    lease->metadata.config_bound = lease->initialized;
    lease->metadata.media_binding_returned =
        lease->metadata.media_returns > 0U;
    lease->metadata.result_owned =
        lease->state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED;
}

static bool endpoint_registry_binding_valid(
    const call020_usb_serial_jtag_endpoint_t *endpoint)
{
    if (endpoint == NULL || endpoint->driver_generation == 0U) {
        return false;
    }
    bool matched = false;
    portENTER_CRITICAL(&s_driver_registry_lock);
    if (endpoint->driver_ownership ==
            CALL020_USB_ENDPOINT_DRIVER_SELF_OWNED) {
        matched = s_driver_owner_config_bound &&
            (s_driver_owner_kind == DRIVER_OWNER_ENDPOINT_ACTIVE ||
             (s_driver_owner_kind == DRIVER_OWNER_ENDPOINT_INSTALLING &&
              endpoint->state == CALL020_USB_ENDPOINT_TERMINAL)) &&
            s_driver_owner_context == endpoint &&
            s_driver_owner_generation == endpoint->driver_generation &&
            config_equal(&s_driver_owner_config, &endpoint->bound_config);
    } else if (endpoint->driver_ownership ==
            CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED &&
        endpoint->borrowed_lease != NULL) {
        const call020_usb_driver_lease_t *lease = endpoint->borrowed_lease;
        matched = s_driver_owner_config_bound &&
            s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
            s_driver_owner_context == lease &&
            s_driver_owner_generation == endpoint->driver_generation &&
            lease->initialized &&
            lease->generation == endpoint->driver_generation &&
            lease->state == CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED &&
            config_equal(&s_driver_owner_config, &endpoint->bound_config);
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return matched;
}

static bool endpoint_driver_binding_valid(
    const call020_usb_serial_jtag_endpoint_t *endpoint)
{
    return endpoint_registry_binding_valid(endpoint) &&
        usb_serial_jtag_is_driver_installed();
}

static bool get_now_us(uint64_t *now_us)
{
    int64_t value = esp_timer_get_time();
    if (now_us == NULL || value < 0) {
        return false;
    }
    *now_us = (uint64_t)value;
    return true;
}

static bool checked_add_u64(uint64_t left, uint64_t right, uint64_t *sum)
{
    if (sum == NULL || UINT64_MAX - left < right) {
        return false;
    }
    *sum = left + right;
    return true;
}

static TickType_t bounded_wait_ticks(
    const call020_usb_serial_jtag_endpoint_t *endpoint,
    uint64_t now_us,
    uint64_t deadline_us)
{
    if (deadline_us <= now_us) {
        return 0;
    }
    uint64_t remaining_us = deadline_us - now_us;
    uint64_t slice_us =
        (uint64_t)endpoint->io_wait_slice_ms * UINT64_C(1000);
    uint64_t wait_us = remaining_us < slice_us ? remaining_us : slice_us;
    uint64_t ticks =
        (wait_us * (uint64_t)configTICK_RATE_HZ) / UINT64_C(1000000);
    if (ticks > (uint64_t)portMAX_DELAY) {
        ticks = (uint64_t)portMAX_DELAY;
    }
    return (TickType_t)ticks;
}

static void sync_activity_metadata(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    endpoint->metadata.state = endpoint->state;
    endpoint->metadata.terminal_reason = endpoint->terminal_reason;
    endpoint->metadata.read_active = endpoint->read_active;
    endpoint->metadata.write_active = endpoint->write_active;
    endpoint->metadata.driver_installed = endpoint->driver_installed;
    endpoint->metadata.driver_ownership = endpoint->driver_ownership;
    endpoint->metadata.driver_generation = endpoint->driver_generation;
    endpoint->metadata.binding_closed = endpoint->binding_closed;
    endpoint->metadata.driver_uninstalled_by_endpoint =
        endpoint->driver_uninstalled_by_endpoint;
    endpoint->metadata.lease_returned = endpoint->lease_returned;
}

static void latch_terminal(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    call020_usb_endpoint_terminal_reason_t reason)
{
    portENTER_CRITICAL(&endpoint->lock);
    if (endpoint->terminal_reason == CALL020_USB_ENDPOINT_TERMINAL_NONE) {
        endpoint->terminal_reason = reason;
    }
    endpoint->state = CALL020_USB_ENDPOINT_TERMINAL;
    endpoint->cancel_requested = true;
    sync_activity_metadata(endpoint);
    portEXIT_CRITICAL(&endpoint->lock);
}

static bool cancellation_requested(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    portENTER_CRITICAL(&endpoint->lock);
    bool requested = endpoint->cancel_requested;
    portEXIT_CRITICAL(&endpoint->lock);
    return requested;
}

static call020_usb_endpoint_transfer_result_t begin_operation(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    operation_direction_t direction)
{
    if (!endpoint_driver_binding_valid(endpoint)) {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
        return CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR;
    }
    portENTER_CRITICAL(&endpoint->lock);
    call020_usb_endpoint_transfer_result_t result =
        CALL020_USB_ENDPOINT_TRANSFER_INVALID_STATE;
    bool *active = direction == OPERATION_READ
        ? &endpoint->read_active
        : &endpoint->write_active;
    if (endpoint->initialized && endpoint->driver_installed &&
        endpoint->state == CALL020_USB_ENDPOINT_READY &&
        !endpoint->cancel_requested && !*active) {
        *active = true;
        result = CALL020_USB_ENDPOINT_TRANSFER_OK;
    } else if (endpoint->initialized && endpoint->cancel_requested) {
        result = CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS;
    }
    sync_activity_metadata(endpoint);
    portEXIT_CRITICAL(&endpoint->lock);
    return result;
}

static void end_operation(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    operation_direction_t direction)
{
    portENTER_CRITICAL(&endpoint->lock);
    if (direction == OPERATION_READ) {
        endpoint->read_active = false;
    } else {
        endpoint->write_active = false;
    }
    sync_activity_metadata(endpoint);
    portEXIT_CRITICAL(&endpoint->lock);
}

static void note_zero_timeout(call020_usb_serial_jtag_endpoint_t *endpoint)
{
    portENTER_CRITICAL(&endpoint->lock);
    endpoint->metadata.zero_progress_timeouts++;
    portEXIT_CRITICAL(&endpoint->lock);
}

static void note_partial_terminal(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    call020_usb_endpoint_terminal_reason_t reason)
{
    portENTER_CRITICAL(&endpoint->lock);
    endpoint->metadata.partial_progress_terminals++;
    portEXIT_CRITICAL(&endpoint->lock);
    latch_terminal(endpoint, reason);
}

static void note_unknown_terminal(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    call020_usb_endpoint_terminal_reason_t reason)
{
    portENTER_CRITICAL(&endpoint->lock);
    endpoint->metadata.unknown_progress_terminals++;
    portEXIT_CRITICAL(&endpoint->lock);
    latch_terminal(endpoint, reason);
}

static call020_usb_endpoint_transfer_result_t validate_transfer(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const void *buffer,
    size_t requested_bytes,
    uint64_t absolute_deadline_us,
    uint64_t *now_us)
{
    if (endpoint == NULL || buffer == NULL || now_us == NULL ||
        requested_bytes == 0U ||
        requested_bytes > CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES) {
        return CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT;
    }
    if (!endpoint->initialized || !endpoint->driver_installed) {
        return CALL020_USB_ENDPOINT_TRANSFER_INVALID_STATE;
    }
    if (!get_now_us(now_us)) {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
        return CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
    }
    if (absolute_deadline_us <= *now_us) {
        note_zero_timeout(endpoint);
        return CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS;
    }
    if (absolute_deadline_us - *now_us > endpoint->max_operation_us) {
        return CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT;
    }
    return CALL020_USB_ENDPOINT_TRANSFER_OK;
}

static call020_usb_endpoint_transfer_result_t classify_read_stop(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    size_t transferred,
    bool cancelled)
{
    if (transferred == 0U) {
        if (cancelled) {
            return CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS;
        }
        note_zero_timeout(endpoint);
        return CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS;
    }
    note_partial_terminal(
        endpoint, CALL020_USB_ENDPOINT_TERMINAL_RX_PARTIAL);
    return cancelled
        ? CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_PARTIAL
        : CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL;
}

static call020_usb_endpoint_transfer_result_t classify_write_unknown(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    bool cancelled)
{
    note_unknown_terminal(
        endpoint, CALL020_USB_ENDPOINT_TERMINAL_TX_UNKNOWN);
    return cancelled
        ? CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_UNKNOWN
        : CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
}

const char *call020_usb_serial_jtag_endpoint_version(void)
{
    return CALL020_USB_SERIAL_JTAG_ENDPOINT_VERSION;
}

const char *call020_usb_driver_lease_version(void)
{
    return CALL020_USB_DRIVER_LEASE_VERSION;
}

esp_err_t call020_usb_driver_lease_install(
    call020_usb_driver_lease_t *lease,
    const call020_usb_endpoint_config_t *config)
{
    if (lease == NULL || !config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (lease->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    secure_zero(lease, sizeof(*lease));
    if (!dedicated_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }

    uint64_t generation = 0U;
    if (!reserve_driver_owner(
            DRIVER_OWNER_LEASE_INSTALLING, lease, config, &generation)) {
        return ESP_ERR_INVALID_STATE;
    }
    if (usb_serial_jtag_is_driver_installed()) {
        release_driver_owner(
            DRIVER_OWNER_LEASE_INSTALLING, lease, generation);
        secure_zero(lease, sizeof(*lease));
        return ESP_ERR_INVALID_STATE;
    }

    usb_serial_jtag_driver_config_t driver_config = {
        .tx_buffer_size = config->tx_buffer_bytes,
        .rx_buffer_size = config->rx_buffer_bytes,
    };
    esp_err_t result = usb_serial_jtag_driver_install(&driver_config);
    if (result != ESP_OK) {
        release_driver_owner(
            DRIVER_OWNER_LEASE_INSTALLING, lease, generation);
        secure_zero(lease, sizeof(*lease));
        return result;
    }

    lease->initialized = true;
    lease->generation = generation;
    lease->owner_core_id = (int)xPortGetCoreID();
    lease->bound_config = *config;
    lease->state = CALL020_USB_DRIVER_LEASE_CONTROL_OWNED;
    lease->terminal_reason = CALL020_USB_DRIVER_LEASE_TERMINAL_NONE;
    lease->metadata.install_calls = 1U;
    lease->metadata.driver_installed = true;
    sync_lease_metadata(lease);
    if (!activate_driver_owner(
            DRIVER_OWNER_LEASE_INSTALLING,
            DRIVER_OWNER_LEASE_ACTIVE,
            lease,
            generation)) {
        lease->metadata.uninstall_attempts++;
        esp_err_t uninstall_result = usb_serial_jtag_driver_uninstall();
        if (uninstall_result == ESP_OK) {
            lease->metadata.uninstall_successes++;
            lease->metadata.driver_installed = false;
            if (release_driver_owner(
                    DRIVER_OWNER_LEASE_INSTALLING, lease, generation)) {
                secure_zero(lease, sizeof(*lease));
            } else {
                lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
                lease->terminal_reason =
                    CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
                sync_lease_metadata(lease);
            }
        } else {
            lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
            lease->terminal_reason =
                CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER;
            sync_lease_metadata(lease);
        }
        return uninstall_result == ESP_OK
            ? ESP_ERR_INVALID_STATE
            : uninstall_result;
    }
    return ESP_OK;
}

esp_err_t call020_usb_driver_lease_begin_media_handoff(
    call020_usb_driver_lease_t *lease)
{
    if (lease == NULL || !lease->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    if ((int)xPortGetCoreID() != lease->owner_core_id) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->metadata.wrong_core_rejections++;
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (lease->state == CALL020_USB_DRIVER_LEASE_CLOSED) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!usb_serial_jtag_is_driver_installed()) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        bool registered =
            s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
            s_driver_owner_context == lease &&
            s_driver_owner_generation == lease->generation;
        if (registered) {
            s_driver_owner_kind = DRIVER_OWNER_NONE;
            s_driver_owner_context = NULL;
            s_driver_owner_generation = 0U;
            s_driver_owner_config =
                (call020_usb_endpoint_config_t){0};
            s_driver_owner_config_bound = false;
        }
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER;
        lease->metadata.driver_installed = false;
        sync_lease_metadata(lease);
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t result = ESP_ERR_INVALID_STATE;
    portENTER_CRITICAL(&s_driver_registry_lock);
    bool registered =
        s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
        s_driver_owner_context == lease &&
        s_driver_owner_generation == lease->generation &&
        lease->generation != 0U &&
        s_driver_owner_config_bound;
    if (registered &&
        lease->state == CALL020_USB_DRIVER_LEASE_CONTROL_OWNED) {
        lease->state = CALL020_USB_DRIVER_LEASE_HANDOFF_READY;
        lease->metadata.handoff_calls++;
        sync_lease_metadata(lease);
        result = ESP_OK;
    } else if (!registered) {
        lease->metadata.binding_rejections++;
        if (lease->state != CALL020_USB_DRIVER_LEASE_CLOSED) {
            lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
            lease->terminal_reason =
                CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        }
        sync_lease_metadata(lease);
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return result;
}

esp_err_t call020_usb_driver_lease_reclaim_for_result(
    call020_usb_driver_lease_t *lease,
    const call020_usb_endpoint_config_t *config)
{
    if (lease == NULL || !lease->initialized || !config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    if ((int)xPortGetCoreID() != lease->owner_core_id) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->metadata.wrong_core_rejections++;
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (lease->state == CALL020_USB_DRIVER_LEASE_CLOSED) {
        return ESP_ERR_INVALID_STATE;
    }
    bool driver_installed = usb_serial_jtag_is_driver_installed();

    esp_err_t result = ESP_ERR_INVALID_STATE;
    portENTER_CRITICAL(&s_driver_registry_lock);
    bool registered =
        s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
        s_driver_owner_context == lease &&
        s_driver_owner_generation == lease->generation &&
        lease->generation != 0U && s_driver_owner_config_bound;
    bool config_bound = registered &&
        config_equal(&s_driver_owner_config, config);
    if (!registered) {
        lease->metadata.binding_rejections++;
        if (lease->state != CALL020_USB_DRIVER_LEASE_CLOSED) {
            lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
            lease->terminal_reason =
                CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        }
    } else if (!driver_installed) {
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER;
        lease->metadata.driver_installed = false;
    } else if (lease->state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED &&
        config_bound) {
        lease->state = CALL020_USB_DRIVER_LEASE_RESULT_OWNED;
        lease->metadata.result_reclaims++;
        result = ESP_OK;
    } else {
        lease->metadata.binding_rejections++;
        /* Never poison an active MEDIA or RESULT owner into a closable state. */
        if (lease->state != CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED &&
            lease->state != CALL020_USB_DRIVER_LEASE_RESULT_OWNED) {
            lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
            lease->terminal_reason =
                CALL020_USB_DRIVER_LEASE_TERMINAL_BINDING;
        }
    }
    sync_lease_metadata(lease);
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return result;
}

esp_err_t call020_usb_driver_lease_close(
    call020_usb_driver_lease_t *lease)
{
    if (lease == NULL || !lease->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_driver_registry_lock);
    lease->metadata.close_calls++;
    portEXIT_CRITICAL(&s_driver_registry_lock);
    if ((int)xPortGetCoreID() != lease->owner_core_id) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->metadata.wrong_core_rejections++;
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (lease->state == CALL020_USB_DRIVER_LEASE_CLOSED) {
        return ESP_OK;
    }

    portENTER_CRITICAL(&s_driver_registry_lock);
    driver_owner_kind_t registered_kind = DRIVER_OWNER_NONE;
    if ((s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE ||
         (s_driver_owner_kind == DRIVER_OWNER_LEASE_INSTALLING &&
          lease->state == CALL020_USB_DRIVER_LEASE_TERMINAL)) &&
        s_driver_owner_context == lease &&
        s_driver_owner_generation == lease->generation &&
        lease->generation != 0U && s_driver_owner_config_bound) {
        registered_kind = s_driver_owner_kind;
    }
    bool registered = registered_kind != DRIVER_OWNER_NONE;
    bool closable =
        lease->state == CALL020_USB_DRIVER_LEASE_CONTROL_OWNED ||
        lease->state == CALL020_USB_DRIVER_LEASE_HANDOFF_READY ||
        lease->state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED ||
        lease->state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED ||
        lease->state == CALL020_USB_DRIVER_LEASE_TERMINAL;
    if (!registered) {
        lease->metadata.binding_rejections++;
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        sync_lease_metadata(lease);
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    if (!registered || !closable) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!usb_serial_jtag_is_driver_installed()) {
        bool owner_released = release_driver_owner(
            registered_kind, lease, lease->generation);
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason = owner_released
            ? CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER
            : CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        lease->metadata.driver_installed = false;
        sync_lease_metadata(lease);
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }

    portENTER_CRITICAL(&s_driver_registry_lock);
    lease->metadata.uninstall_attempts++;
    portEXIT_CRITICAL(&s_driver_registry_lock);
    esp_err_t result = usb_serial_jtag_driver_uninstall();
    if (result != ESP_OK) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER;
        sync_lease_metadata(lease);
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return result;
    }
    portENTER_CRITICAL(&s_driver_registry_lock);
    lease->metadata.uninstall_successes++;
    lease->metadata.driver_installed = false;
    portEXIT_CRITICAL(&s_driver_registry_lock);
    if (!release_driver_owner(
            registered_kind, lease, lease->generation)) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        sync_lease_metadata(lease);
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }

    portENTER_CRITICAL(&s_driver_registry_lock);
    lease->state = CALL020_USB_DRIVER_LEASE_CLOSED;
    lease->terminal_reason = CALL020_USB_DRIVER_LEASE_TERMINAL_NONE;
    lease->metadata.driver_installed = false;
    sync_lease_metadata(lease);
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return ESP_OK;
}

esp_err_t call020_usb_driver_lease_get_metadata(
    call020_usb_driver_lease_t *lease,
    call020_usb_driver_lease_metadata_t *metadata)
{
    if (lease == NULL || metadata == NULL || !lease->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_driver_registry_lock);
    sync_lease_metadata(lease);
    *metadata = lease->metadata;
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return ESP_OK;
}

static esp_err_t claim_lease_for_media(
    call020_usb_driver_lease_t *lease,
    const call020_usb_endpoint_config_t *config,
    uint64_t *generation,
    int *owner_core_id)
{
    if (lease == NULL || config == NULL || generation == NULL ||
        owner_core_id == NULL || !lease->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    if ((int)xPortGetCoreID() != lease->owner_core_id) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->metadata.wrong_core_rejections++;
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }
    if (lease->state == CALL020_USB_DRIVER_LEASE_CLOSED) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!usb_serial_jtag_is_driver_installed()) {
        portENTER_CRITICAL(&s_driver_registry_lock);
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER;
        lease->metadata.driver_installed = false;
        sync_lease_metadata(lease);
        portEXIT_CRITICAL(&s_driver_registry_lock);
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t result = ESP_ERR_INVALID_STATE;
    portENTER_CRITICAL(&s_driver_registry_lock);
    bool registered =
        s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
        s_driver_owner_context == lease &&
        s_driver_owner_generation == lease->generation &&
        lease->generation != 0U && s_driver_owner_config_bound;
    bool bound = registered &&
        lease->state == CALL020_USB_DRIVER_LEASE_HANDOFF_READY &&
        config_equal(&s_driver_owner_config, config);
    if (bound) {
        lease->state = CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED;
        lease->metadata.media_adoptions++;
        sync_lease_metadata(lease);
        *generation = lease->generation;
        *owner_core_id = lease->owner_core_id;
        result = ESP_OK;
    } else if (registered) {
        lease->metadata.binding_rejections++;
        /*
         * A duplicate adopter must not turn an actively borrowed lease into
         * a closable state. The first endpoint remains the only media owner.
         */
        if (lease->state != CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED &&
            lease->state != CALL020_USB_DRIVER_LEASE_RESULT_OWNED) {
            lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
            lease->terminal_reason =
                CALL020_USB_DRIVER_LEASE_TERMINAL_BINDING;
        }
        sync_lease_metadata(lease);
    } else {
        lease->metadata.binding_rejections++;
        lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL;
        lease->terminal_reason =
            CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY;
        sync_lease_metadata(lease);
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    return result;
}

static esp_err_t return_lease_from_media(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    if (endpoint == NULL || endpoint->borrowed_lease == NULL ||
        endpoint->driver_generation == 0U) {
        return ESP_ERR_INVALID_STATE;
    }
    call020_usb_driver_lease_t *lease = endpoint->borrowed_lease;
    esp_err_t result = ESP_ERR_INVALID_STATE;
    portENTER_CRITICAL(&s_driver_registry_lock);
    bool bound =
        s_driver_owner_config_bound &&
        s_driver_owner_kind == DRIVER_OWNER_LEASE_ACTIVE &&
        s_driver_owner_context == lease &&
        s_driver_owner_generation == endpoint->driver_generation &&
        lease->initialized &&
        lease->generation == endpoint->driver_generation &&
        lease->state == CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED &&
        config_equal(&s_driver_owner_config, &endpoint->bound_config);
    if (bound) {
        lease->state = CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED;
        lease->metadata.media_returns++;
        sync_lease_metadata(lease);
        result = ESP_OK;
    }
    portEXIT_CRITICAL(&s_driver_registry_lock);
    if (result == ESP_OK) {
        portENTER_CRITICAL(&endpoint->lock);
        endpoint->lease_returned = true;
        sync_activity_metadata(endpoint);
        portEXIT_CRITICAL(&endpoint->lock);
    }
    return result;
}

static bool release_self_owned_endpoint_registry(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    bool released = release_driver_owner(
        DRIVER_OWNER_ENDPOINT_ACTIVE,
        endpoint,
        endpoint->driver_generation);
    if (!released) {
        released = release_driver_owner(
            DRIVER_OWNER_ENDPOINT_INSTALLING,
            endpoint,
            endpoint->driver_generation);
    }
    return released;
}

static void initialize_endpoint_context(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const call020_usb_endpoint_config_t *config,
    call020_usb_endpoint_driver_ownership_t ownership,
    uint64_t generation,
    int install_core_id,
    call020_usb_driver_lease_t *borrowed_lease)
{
    endpoint->initialized = true;
    endpoint->driver_installed = true;
    endpoint->install_core_id = install_core_id;
    endpoint->driver_generation = generation;
    endpoint->driver_ownership = ownership;
    endpoint->borrowed_lease = borrowed_lease;
    endpoint->bound_config = *config;
    endpoint->io_wait_slice_ms = config->io_wait_slice_ms;
    endpoint->max_operation_us = config->max_operation_us;
    endpoint->close_timeout_us = config->close_timeout_us;
    endpoint->state = CALL020_USB_ENDPOINT_READY;
    endpoint->terminal_reason = CALL020_USB_ENDPOINT_TERMINAL_NONE;
    sync_activity_metadata(endpoint);
}

esp_err_t call020_usb_serial_jtag_endpoint_install(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const call020_usb_endpoint_config_t *config)
{
    if (endpoint == NULL || !config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (endpoint->initialized || endpoint->driver_installed) {
        return ESP_ERR_INVALID_STATE;
    }
    secure_zero(endpoint, sizeof(*endpoint));
    endpoint->lock = (portMUX_TYPE)portMUX_INITIALIZER_UNLOCKED;
    if (!dedicated_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }

    uint64_t generation = 0U;
    if (!reserve_driver_owner(
            DRIVER_OWNER_ENDPOINT_INSTALLING,
            endpoint,
            config,
            &generation)) {
        secure_zero(endpoint, sizeof(*endpoint));
        return ESP_ERR_INVALID_STATE;
    }
    if (usb_serial_jtag_is_driver_installed()) {
        release_driver_owner(
            DRIVER_OWNER_ENDPOINT_INSTALLING, endpoint, generation);
        secure_zero(endpoint, sizeof(*endpoint));
        return ESP_ERR_INVALID_STATE;
    }

    usb_serial_jtag_driver_config_t driver_config = {
        .tx_buffer_size = config->tx_buffer_bytes,
        .rx_buffer_size = config->rx_buffer_bytes,
    };
    esp_err_t result = usb_serial_jtag_driver_install(&driver_config);
    if (result != ESP_OK) {
        release_driver_owner(
            DRIVER_OWNER_ENDPOINT_INSTALLING, endpoint, generation);
        secure_zero(endpoint, sizeof(*endpoint));
        return result;
    }

    initialize_endpoint_context(
        endpoint,
        config,
        CALL020_USB_ENDPOINT_DRIVER_SELF_OWNED,
        generation,
        (int)xPortGetCoreID(),
        NULL);
    if (!activate_driver_owner(
            DRIVER_OWNER_ENDPOINT_INSTALLING,
            DRIVER_OWNER_ENDPOINT_ACTIVE,
            endpoint,
            generation)) {
        endpoint->metadata.driver_uninstall_attempts++;
        esp_err_t uninstall_result = usb_serial_jtag_driver_uninstall();
        if (uninstall_result == ESP_OK) {
            endpoint->metadata.driver_uninstall_successes++;
            endpoint->driver_installed = false;
            if (release_driver_owner(
                    DRIVER_OWNER_ENDPOINT_INSTALLING,
                    endpoint,
                    generation)) {
                secure_zero(endpoint, sizeof(*endpoint));
                return ESP_ERR_INVALID_STATE;
            }
        }
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
        return uninstall_result == ESP_OK
            ? ESP_ERR_INVALID_STATE
            : uninstall_result;
    }
    return ESP_OK;
}

esp_err_t call020_usb_serial_jtag_endpoint_adopt_lease(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const call020_usb_endpoint_config_t *config,
    call020_usb_driver_lease_t *lease)
{
    if (endpoint == NULL || lease == NULL || !config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (endpoint->initialized || endpoint->driver_installed) {
        return ESP_ERR_INVALID_STATE;
    }
    secure_zero(endpoint, sizeof(*endpoint));
    endpoint->lock = (portMUX_TYPE)portMUX_INITIALIZER_UNLOCKED;
    if (!dedicated_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }

    uint64_t generation = 0U;
    int owner_core_id = -1;
    esp_err_t result = claim_lease_for_media(
        lease, config, &generation, &owner_core_id);
    if (result != ESP_OK) {
        secure_zero(endpoint, sizeof(*endpoint));
        return result;
    }
    initialize_endpoint_context(
        endpoint,
        config,
        CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED,
        generation,
        owner_core_id,
        lease);
    return ESP_OK;
}

call020_usb_endpoint_transfer_result_t
call020_usb_serial_jtag_endpoint_read_exact(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    uint8_t *destination,
    size_t requested_bytes,
    uint64_t absolute_deadline_us,
    size_t *bytes_transferred)
{
    if (bytes_transferred == NULL) {
        if (destination != NULL && requested_bytes > 0U &&
            requested_bytes <= CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES) {
            secure_zero(destination, requested_bytes);
        }
        return CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT;
    }
    *bytes_transferred = 0U;
    uint64_t now_us = 0U;
    call020_usb_endpoint_transfer_result_t result = validate_transfer(
        endpoint, destination, requested_bytes, absolute_deadline_us, &now_us);
    if (result != CALL020_USB_ENDPOINT_TRANSFER_OK) {
        if (destination != NULL && requested_bytes > 0U &&
            requested_bytes <= CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES) {
            secure_zero(destination, requested_bytes);
        }
        return result;
    }
    result = begin_operation(endpoint, OPERATION_READ);
    if (result != CALL020_USB_ENDPOINT_TRANSFER_OK) {
        secure_zero(destination, requested_bytes);
        return result;
    }

    size_t transferred = 0U;
    uint64_t previous_now_us = now_us;
    while (transferred < requested_bytes) {
        if (cancellation_requested(endpoint)) {
            result = classify_read_stop(endpoint, transferred, true);
            break;
        }
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        previous_now_us = now_us;
        if (now_us >= absolute_deadline_us) {
            result = classify_read_stop(endpoint, transferred, false);
            break;
        }

        size_t remaining = requested_bytes - transferred;
        TickType_t wait_ticks = bounded_wait_ticks(
            endpoint, now_us, absolute_deadline_us);
        int received = usb_serial_jtag_read_bytes(
            destination + transferred, (uint32_t)remaining, wait_ticks);
        if (received < 0 || (size_t)received > remaining) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_RX_UNKNOWN);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        transferred += (size_t)received;
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        previous_now_us = now_us;
        if (transferred == requested_bytes) {
            if (cancellation_requested(endpoint)) {
                note_unknown_terminal(
                    endpoint, CALL020_USB_ENDPOINT_TERMINAL_RX_UNKNOWN);
                result = CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_UNKNOWN;
            } else if (now_us > absolute_deadline_us) {
                note_unknown_terminal(
                    endpoint, CALL020_USB_ENDPOINT_TERMINAL_RX_UNKNOWN);
                result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            } else {
                portENTER_CRITICAL(&endpoint->lock);
                endpoint->metadata.reads_completed++;
                portEXIT_CRITICAL(&endpoint->lock);
                result = CALL020_USB_ENDPOINT_TRANSFER_OK;
            }
            break;
        }
        if (now_us >= absolute_deadline_us) {
            result = classify_read_stop(endpoint, transferred, false);
            break;
        }
        if (received == 0 && wait_ticks == 0) {
            taskYIELD();
        }
    }

    *bytes_transferred = transferred;
    if (result != CALL020_USB_ENDPOINT_TRANSFER_OK) {
        secure_zero(destination, requested_bytes);
    }
    end_operation(endpoint, OPERATION_READ);
    return result;
}

call020_usb_endpoint_transfer_result_t
call020_usb_serial_jtag_endpoint_write_exact(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const uint8_t *source,
    size_t requested_bytes,
    uint64_t absolute_deadline_us,
    size_t *bytes_transferred)
{
    if (bytes_transferred == NULL) {
        return CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT;
    }
    *bytes_transferred = 0U;
    uint64_t now_us = 0U;
    call020_usb_endpoint_transfer_result_t result = validate_transfer(
        endpoint, source, requested_bytes, absolute_deadline_us, &now_us);
    if (result != CALL020_USB_ENDPOINT_TRANSFER_OK) {
        return result;
    }
    result = begin_operation(endpoint, OPERATION_WRITE);
    if (result != CALL020_USB_ENDPOINT_TRANSFER_OK) {
        return result;
    }

    uint64_t previous_now_us = now_us;
    bool enqueued = false;
    while (!enqueued) {
        if (cancellation_requested(endpoint)) {
            result = CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS;
            break;
        }
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        previous_now_us = now_us;
        if (now_us >= absolute_deadline_us) {
            note_zero_timeout(endpoint);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS;
            break;
        }
        if (!usb_serial_jtag_is_driver_installed()) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
            result = CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR;
            break;
        }

        TickType_t wait_ticks = bounded_wait_ticks(
            endpoint, now_us, absolute_deadline_us);
        int accepted = usb_serial_jtag_write_bytes(
            source, requested_bytes, wait_ticks);
        if (accepted < 0 || (size_t)accepted > requested_bytes) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_TX_UNKNOWN);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        if (accepted > 0 && (size_t)accepted < requested_bytes) {
            *bytes_transferred = (size_t)accepted;
            note_partial_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_TX_PARTIAL);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL;
            break;
        }
        if ((size_t)accepted == requested_bytes) {
            *bytes_transferred = requested_bytes;
            enqueued = true;
            break;
        }
        if (wait_ticks == 0) {
            taskYIELD();
        }
    }

    while (enqueued) {
        if (cancellation_requested(endpoint)) {
            result = classify_write_unknown(endpoint, true);
            break;
        }
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            note_unknown_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
            result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            break;
        }
        previous_now_us = now_us;
        if (now_us >= absolute_deadline_us) {
            result = classify_write_unknown(endpoint, false);
            break;
        }

        TickType_t wait_ticks = bounded_wait_ticks(
            endpoint, now_us, absolute_deadline_us);
        esp_err_t wait_result = usb_serial_jtag_wait_tx_done(wait_ticks);
        if (wait_result == ESP_OK) {
            if (!get_now_us(&now_us) || now_us < previous_now_us) {
                note_unknown_terminal(
                    endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
                result = CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN;
            } else if (cancellation_requested(endpoint)) {
                result = classify_write_unknown(endpoint, true);
            } else if (now_us > absolute_deadline_us) {
                result = classify_write_unknown(endpoint, false);
            } else {
                portENTER_CRITICAL(&endpoint->lock);
                endpoint->metadata.writes_completed++;
                portEXIT_CRITICAL(&endpoint->lock);
                result = CALL020_USB_ENDPOINT_TRANSFER_OK;
            }
            break;
        }
        if (wait_result != ESP_ERR_TIMEOUT) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
            result = CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR;
            break;
        }
        if (wait_ticks == 0) {
            taskYIELD();
        }
    }

    end_operation(endpoint, OPERATION_WRITE);
    return result;
}

call020_media_transfer_result_t
call020_usb_serial_jtag_endpoint_write_wire(
    void *user_context,
    const uint8_t *wire,
    size_t wire_bytes,
    uint64_t absolute_deadline_us)
{
    size_t bytes_transferred = 0U;
    call020_usb_endpoint_transfer_result_t result =
        call020_usb_serial_jtag_endpoint_write_exact(
            (call020_usb_serial_jtag_endpoint_t *)user_context,
            wire,
            wire_bytes,
            absolute_deadline_us,
            &bytes_transferred);
    (void)bytes_transferred;
    switch (result) {
    case CALL020_USB_ENDPOINT_TRANSFER_OK:
        return CALL020_MEDIA_TRANSFER_OK;
    case CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS:
        return CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS;
    case CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL:
    case CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_PARTIAL:
        return CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL;
    case CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN:
    case CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_UNKNOWN:
        return CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN;
    case CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS:
    case CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT:
    case CALL020_USB_ENDPOINT_TRANSFER_INVALID_STATE:
    case CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR:
    default:
        return CALL020_MEDIA_TRANSFER_ERROR;
    }
}

esp_err_t call020_usb_serial_jtag_endpoint_request_cancel(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    if (endpoint == NULL || !endpoint->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&endpoint->lock);
    if (!endpoint->cancel_requested) {
        endpoint->metadata.cancel_requests++;
    }
    endpoint->cancel_requested = true;
    if (endpoint->state == CALL020_USB_ENDPOINT_READY) {
        endpoint->state = CALL020_USB_ENDPOINT_CLOSING;
    }
    sync_activity_metadata(endpoint);
    portEXIT_CRITICAL(&endpoint->lock);
    return ESP_OK;
}

esp_err_t call020_usb_serial_jtag_endpoint_close(
    call020_usb_serial_jtag_endpoint_t *endpoint)
{
    if (endpoint == NULL || !endpoint->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    if (endpoint->state == CALL020_USB_ENDPOINT_CLOSED) {
        return ESP_OK;
    }
    esp_err_t result =
        call020_usb_serial_jtag_endpoint_request_cancel(endpoint);
    if (result != ESP_OK) {
        return result;
    }

    uint64_t now_us = 0U;
    uint64_t deadline_us = 0U;
    if (!get_now_us(&now_us) ||
        !checked_add_u64(now_us, endpoint->close_timeout_us, &deadline_us)) {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
        return ESP_ERR_INVALID_STATE;
    }
    uint64_t previous_now_us = now_us;
    while (true) {
        portENTER_CRITICAL(&endpoint->lock);
        bool active = endpoint->read_active || endpoint->write_active;
        portEXIT_CRITICAL(&endpoint->lock);
        if (!active) {
            break;
        }
        if (!get_now_us(&now_us) || now_us < previous_now_us) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOCK);
            return ESP_ERR_INVALID_STATE;
        }
        previous_now_us = now_us;
        if (now_us >= deadline_us) {
            portENTER_CRITICAL(&endpoint->lock);
            endpoint->metadata.close_timeouts++;
            portEXIT_CRITICAL(&endpoint->lock);
            latch_terminal(
                endpoint, CALL020_USB_ENDPOINT_TERMINAL_CLOSE_TIMEOUT);
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(1);
    }

    if ((int)xPortGetCoreID() != endpoint->install_core_id) {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_WRONG_CORE);
        return ESP_ERR_INVALID_STATE;
    }
    if (!endpoint_registry_binding_valid(endpoint)) {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
        return ESP_ERR_INVALID_STATE;
    }
    if (!usb_serial_jtag_is_driver_installed()) {
        bool binding_released = false;
        if (endpoint->driver_ownership ==
                CALL020_USB_ENDPOINT_DRIVER_SELF_OWNED) {
            binding_released =
                release_self_owned_endpoint_registry(endpoint);
        } else if (endpoint->driver_ownership ==
                CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED) {
            result = return_lease_from_media(endpoint);
            if (result == ESP_OK) {
                portENTER_CRITICAL(&s_driver_registry_lock);
                endpoint->borrowed_lease->metadata.driver_installed = false;
                sync_lease_metadata(endpoint->borrowed_lease);
                portEXIT_CRITICAL(&s_driver_registry_lock);
                binding_released = true;
            }
        }
        portENTER_CRITICAL(&endpoint->lock);
        endpoint->driver_installed = false;
        endpoint->binding_closed = binding_released;
        sync_activity_metadata(endpoint);
        portEXIT_CRITICAL(&endpoint->lock);
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
        return ESP_ERR_INVALID_STATE;
    }
    if (endpoint->driver_ownership ==
            CALL020_USB_ENDPOINT_DRIVER_SELF_OWNED) {
        portENTER_CRITICAL(&endpoint->lock);
        endpoint->metadata.driver_uninstall_attempts++;
        portEXIT_CRITICAL(&endpoint->lock);
        result = usb_serial_jtag_driver_uninstall();
        if (result != ESP_OK) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
            return result;
        }
        portENTER_CRITICAL(&endpoint->lock);
        endpoint->driver_installed = false;
        endpoint->metadata.driver_uninstall_successes++;
        sync_activity_metadata(endpoint);
        portEXIT_CRITICAL(&endpoint->lock);
        bool owner_released =
            release_self_owned_endpoint_registry(endpoint);
        if (!owner_released) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
            return ESP_ERR_INVALID_STATE;
        }
        endpoint->driver_uninstalled_by_endpoint = true;
    } else if (endpoint->driver_ownership ==
            CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED) {
        result = return_lease_from_media(endpoint);
        if (result != ESP_OK) {
            latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
            return result;
        }
    } else {
        latch_terminal(endpoint, CALL020_USB_ENDPOINT_TERMINAL_DRIVER);
        return ESP_ERR_INVALID_STATE;
    }

    portENTER_CRITICAL(&endpoint->lock);
    endpoint->binding_closed = true;
    endpoint->read_active = false;
    endpoint->write_active = false;
    endpoint->state = CALL020_USB_ENDPOINT_CLOSED;
    sync_activity_metadata(endpoint);
    portEXIT_CRITICAL(&endpoint->lock);
    return ESP_OK;
}

esp_err_t call020_usb_serial_jtag_endpoint_get_metadata(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    call020_usb_endpoint_metadata_t *metadata)
{
    if (endpoint == NULL || metadata == NULL || !endpoint->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&endpoint->lock);
    sync_activity_metadata(endpoint);
    *metadata = endpoint->metadata;
    portEXIT_CRITICAL(&endpoint->lock);
    return ESP_OK;
}
