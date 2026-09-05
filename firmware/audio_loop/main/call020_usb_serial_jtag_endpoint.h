/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020E caller-owned USB Serial/JTAG ordered-byte endpoint. This layer
 * owns no audio device, media framing, task, console, log sink or storage.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "call020_media_adapter_core.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_USB_SERIAL_JTAG_ENDPOINT_VERSION \
    "call020-usb-serial-jtag-endpoint-v1"
#define CALL020_USB_DRIVER_LEASE_VERSION \
    "call020-usb-driver-lease-v1"
#define CALL020_USB_ENDPOINT_MIN_DRIVER_BUFFER_BYTES UINT32_C(128)
#define CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES UINT32_C(16384)
#define CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES \
    CALL020_MEDIA_WIRE_MAX_BYTES
#define CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS UINT32_C(20)
#define CALL020_USB_ENDPOINT_MAX_OPERATION_US UINT64_C(1000000)
#define CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US UINT64_C(1000000)

typedef enum {
    CALL020_USB_ENDPOINT_UNINITIALIZED = 0,
    CALL020_USB_ENDPOINT_READY,
    CALL020_USB_ENDPOINT_CLOSING,
    CALL020_USB_ENDPOINT_CLOSED,
    CALL020_USB_ENDPOINT_TERMINAL,
} call020_usb_endpoint_state_t;

typedef enum {
    CALL020_USB_ENDPOINT_TERMINAL_NONE = 0,
    CALL020_USB_ENDPOINT_TERMINAL_CLOCK,
    CALL020_USB_ENDPOINT_TERMINAL_RX_PARTIAL,
    CALL020_USB_ENDPOINT_TERMINAL_RX_UNKNOWN,
    CALL020_USB_ENDPOINT_TERMINAL_TX_PARTIAL,
    CALL020_USB_ENDPOINT_TERMINAL_TX_UNKNOWN,
    CALL020_USB_ENDPOINT_TERMINAL_DRIVER,
    CALL020_USB_ENDPOINT_TERMINAL_CLOSE_TIMEOUT,
    CALL020_USB_ENDPOINT_TERMINAL_WRONG_CORE,
} call020_usb_endpoint_terminal_reason_t;

/*
 * Ordered-stream progress is explicit. Only TIMEOUT_ZERO_PROGRESS says that
 * retrying the same complete transfer can be safe. Partial and unknown
 * progress latch the endpoint terminal. Cancellation never authorizes retry.
 */
typedef enum {
    CALL020_USB_ENDPOINT_TRANSFER_OK = 0,
    CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS,
    CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL,
    CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_UNKNOWN,
    CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS,
    CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_PARTIAL,
    CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_UNKNOWN,
    CALL020_USB_ENDPOINT_TRANSFER_INVALID_ARGUMENT,
    CALL020_USB_ENDPOINT_TRANSFER_INVALID_STATE,
    CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR,
} call020_usb_endpoint_transfer_result_t;

typedef struct {
    uint32_t tx_buffer_bytes;
    uint32_t rx_buffer_bytes;
    uint32_t io_wait_slice_ms;
    uint64_t max_operation_us;
    uint64_t close_timeout_us;
} call020_usb_endpoint_config_t;

/*
 * A driver lease is an explicit one-lifetime CONTROL -> MEDIA capability.
 * The public fields are observability, not authority: adoption also requires
 * an exact pointer/generation/config match in this module's private registry.
 */
typedef enum {
    CALL020_USB_DRIVER_LEASE_UNINITIALIZED = 0,
    CALL020_USB_DRIVER_LEASE_CONTROL_OWNED,
    CALL020_USB_DRIVER_LEASE_HANDOFF_READY,
    CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED,
    CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED,
    CALL020_USB_DRIVER_LEASE_RESULT_OWNED,
    CALL020_USB_DRIVER_LEASE_CLOSED,
    CALL020_USB_DRIVER_LEASE_TERMINAL,
} call020_usb_driver_lease_state_t;

typedef enum {
    CALL020_USB_DRIVER_LEASE_TERMINAL_NONE = 0,
    CALL020_USB_DRIVER_LEASE_TERMINAL_DRIVER,
    CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY,
    CALL020_USB_DRIVER_LEASE_TERMINAL_BINDING,
} call020_usb_driver_lease_terminal_reason_t;

typedef struct {
    call020_usb_driver_lease_state_t state;
    call020_usb_driver_lease_terminal_reason_t terminal_reason;
    uint64_t generation;
    int owner_core_id;
    uint32_t install_calls;
    uint32_t handoff_calls;
    uint32_t media_adoptions;
    uint32_t media_returns;
    uint32_t result_reclaims;
    uint32_t close_calls;
    uint32_t uninstall_attempts;
    uint32_t uninstall_successes;
    uint32_t wrong_core_rejections;
    uint32_t binding_rejections;
    bool config_bound;
    /* Physical-driver state observed at the last lease transition. */
    bool driver_installed;
    bool media_binding_returned;
    bool result_owned;
} call020_usb_driver_lease_metadata_t;

/*
 * Caller-owned and initially all-zero. It cannot authorize adoption by field
 * values alone; the module-private owner registry is the source of truth.
 * Mutating calls are caller-serialized and must stay on owner_core_id.
 */
typedef struct call020_usb_driver_lease {
    bool initialized;
    uint64_t generation;
    int owner_core_id;
    call020_usb_endpoint_config_t bound_config;
    call020_usb_driver_lease_state_t state;
    call020_usb_driver_lease_terminal_reason_t terminal_reason;
    call020_usb_driver_lease_metadata_t metadata;
} call020_usb_driver_lease_t;

typedef enum {
    CALL020_USB_ENDPOINT_DRIVER_NONE = 0,
    CALL020_USB_ENDPOINT_DRIVER_SELF_OWNED,
    CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED,
} call020_usb_endpoint_driver_ownership_t;

typedef struct {
    call020_usb_endpoint_state_t state;
    call020_usb_endpoint_terminal_reason_t terminal_reason;
    uint64_t reads_completed;
    uint64_t writes_completed;
    uint64_t zero_progress_timeouts;
    uint64_t partial_progress_terminals;
    uint64_t unknown_progress_terminals;
    uint64_t cancel_requests;
    uint64_t close_timeouts;
    uint32_t driver_uninstall_attempts;
    uint32_t driver_uninstall_successes;
    bool read_active;
    bool write_active;
    /* Physical driver state at this endpoint's last binding transition. */
    bool driver_installed;
    call020_usb_endpoint_driver_ownership_t driver_ownership;
    uint64_t driver_generation;
    /* Binding close is distinct from physical driver removal. */
    bool binding_closed;
    bool driver_uninstalled_by_endpoint;
    bool lease_returned;
} call020_usb_endpoint_metadata_t;

/*
 * Caller owns this object and must provide it zero-initialized. The ESP-IDF
 * driver owns its internal ring buffers after install; those buffers and any
 * host-side copies are outside this object's secure-erasure boundary.
 */
typedef struct {
    portMUX_TYPE lock;
    bool initialized;
    bool driver_installed;
    bool cancel_requested;
    bool read_active;
    bool write_active;
    int install_core_id;
    uint64_t driver_generation;
    call020_usb_endpoint_driver_ownership_t driver_ownership;
    call020_usb_driver_lease_t *borrowed_lease;
    call020_usb_endpoint_config_t bound_config;
    bool binding_closed;
    bool driver_uninstalled_by_endpoint;
    bool lease_returned;
    uint32_t io_wait_slice_ms;
    uint64_t max_operation_us;
    uint64_t close_timeout_us;
    call020_usb_endpoint_state_t state;
    call020_usb_endpoint_terminal_reason_t terminal_reason;
    call020_usb_endpoint_metadata_t metadata;
} call020_usb_serial_jtag_endpoint_t;

const char *call020_usb_serial_jtag_endpoint_version(void);

const char *call020_usb_driver_lease_version(void);

/*
 * Install exactly one USB Serial/JTAG driver lifetime for a future CONTROL
 * bootstrap. A pre-existing/unregistered driver is never adopted. This call
 * is synchronous because the ESP-IDF install API has no timeout parameter.
 */
esp_err_t call020_usb_driver_lease_install(
    call020_usb_driver_lease_t *lease,
    const call020_usb_endpoint_config_t *config);

/*
 * Irreversibly ends CONTROL ownership for this generation. Future control
 * code calls this only after the complete START/ACK exchange and quiescence.
 */
esp_err_t call020_usb_driver_lease_begin_media_handoff(
    call020_usb_driver_lease_t *lease);

/*
 * Reclaim the returned physical driver for an optional RESULT phase. This is
 * same-core, exact-generation and full-config bound. It never permits another
 * MEDIA adoption or a transition back to CONTROL.
 */
esp_err_t call020_usb_driver_lease_reclaim_for_result(
    call020_usb_driver_lease_t *lease,
    const call020_usb_endpoint_config_t *config);

/*
 * Uninstall is allowed before handoff, after media returned the lease, or from
 * RESULT_OWNED. It must run on the install core. MEDIA_BORROWED can never be
 * uninstalled.
 */
esp_err_t call020_usb_driver_lease_close(
    call020_usb_driver_lease_t *lease);

esp_err_t call020_usb_driver_lease_get_metadata(
    call020_usb_driver_lease_t *lease,
    call020_usb_driver_lease_metadata_t *metadata);

/*
 * Install is enabled only in a dedicated build with the CALL-020D core on,
 * all ESP-IDF consoles disabled, and app/bootloader logging disabled. The
 * driver must not already have another owner. Install and close must execute
 * on the same CPU core, as required by the ESP-IDF driver.
 */
esp_err_t call020_usb_serial_jtag_endpoint_install(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const call020_usb_endpoint_config_t *config);

/*
 * Adopt one registry-backed HANDOFF_READY lease generation. This path never
 * installs the driver. Endpoint close returns it exactly once to the caller
 * and never uninstalls it; the caller then closes the lease explicitly.
 */
esp_err_t call020_usb_serial_jtag_endpoint_adopt_lease(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const call020_usb_endpoint_config_t *config,
    call020_usb_driver_lease_t *lease);

/*
 * Read exactly one caller-known ordered transfer. A future stream worker must
 * request the complete expected EGLM wire size in one call; splitting a frame
 * across calls would move cross-call progress accounting outside this layer.
 * On every non-OK result, the bounded destination range is cleared.
 */
call020_usb_endpoint_transfer_result_t
call020_usb_serial_jtag_endpoint_read_exact(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    uint8_t *destination,
    size_t requested_bytes,
    uint64_t absolute_deadline_us,
    size_t *bytes_transferred);

/*
 * Write exactly one ordered transfer. Success means ESP-IDF accepted the
 * bytes and wait_tx_done completed before the deadline; it is not proof that
 * a PC application consumed them. A post-enqueue timeout is unknown progress.
 */
call020_usb_endpoint_transfer_result_t
call020_usb_serial_jtag_endpoint_write_exact(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    const uint8_t *source,
    size_t requested_bytes,
    uint64_t absolute_deadline_us,
    size_t *bytes_transferred);

/* Exact callback shape used by call020_media_adapter_core_flush_uplink(). */
call020_media_transfer_result_t
call020_usb_serial_jtag_endpoint_write_wire(
    void *user_context,
    const uint8_t *wire,
    size_t wire_bytes,
    uint64_t absolute_deadline_us);

/*
 * Cancel is non-blocking. Active driver calls use at most io_wait_slice_ms,
 * then observe cancellation. Close requests cancel, waits only for the
 * configured close_timeout_us, and uninstalls only after both directions are
 * inactive. ESP-IDF offers no asynchronous in-call cancel primitive.
 */
esp_err_t call020_usb_serial_jtag_endpoint_request_cancel(
    call020_usb_serial_jtag_endpoint_t *endpoint);

esp_err_t call020_usb_serial_jtag_endpoint_close(
    call020_usb_serial_jtag_endpoint_t *endpoint);

esp_err_t call020_usb_serial_jtag_endpoint_get_metadata(
    call020_usb_serial_jtag_endpoint_t *endpoint,
    call020_usb_endpoint_metadata_t *metadata);

#ifdef __cplusplus
}
#endif
