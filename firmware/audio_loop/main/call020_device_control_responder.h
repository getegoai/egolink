/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020Q default-off same-USB CONTROL responder. This API is never called
 * by app_main. The caller must serialize every mutating call on one CPU core.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "call020_operator_runner.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_DEVICE_CONTROL_RESPONDER_VERSION \
    "call020-device-control-responder-v1"
#define CALL020_DEVICE_CONTROL_MAX_IO_CALLS UINT32_C(64)
#define CALL020_DEVICE_CONTROL_MAX_OPERATION_CACHE UINT32_C(16)
#define CALL020_DEVICE_CONTROL_CONTEXT_BYTES UINT32_C(16384)

typedef enum {
    CALL020_DEVICE_CONTROL_UNINITIALIZED = 0,
    CALL020_DEVICE_CONTROL_DORMANT,
    CALL020_DEVICE_CONTROL_OWNED,
    CALL020_DEVICE_CONTROL_PREPARED,
    CALL020_DEVICE_CONTROL_STOPPING,
    CALL020_DEVICE_CONTROL_JOINED,
    CALL020_DEVICE_CONTROL_START_ACK_PENDING,
    CALL020_DEVICE_CONTROL_CLOSE_ACK_PENDING,
    CALL020_DEVICE_CONTROL_MEDIA,
    CALL020_DEVICE_CONTROL_CLOSED,
    CALL020_DEVICE_CONTROL_START_UNKNOWN,
    CALL020_DEVICE_CONTROL_TERMINAL,
} call020_device_control_state_t;

typedef enum {
    CALL020_DEVICE_CONTROL_SERVE_IDLE = 0,
    CALL020_DEVICE_CONTROL_SERVE_RESPONSE_SENT,
    CALL020_DEVICE_CONTROL_SERVE_RETRYABLE_ZERO_PROGRESS,
    CALL020_DEVICE_CONTROL_SERVE_MEDIA_STARTED,
    CALL020_DEVICE_CONTROL_SERVE_CLOSE_COMPLETE,
    CALL020_DEVICE_CONTROL_SERVE_TERMINAL,
} call020_device_control_serve_result_t;

typedef enum {
    CALL020_DEVICE_CONTROL_TERMINAL_NONE = 0,
    CALL020_DEVICE_CONTROL_TERMINAL_WRONG_CORE,
    CALL020_DEVICE_CONTROL_TERMINAL_READ_PARTIAL_OR_UNKNOWN,
    CALL020_DEVICE_CONTROL_TERMINAL_WRITE_PARTIAL_OR_UNKNOWN,
    CALL020_DEVICE_CONTROL_TERMINAL_FRAME,
    CALL020_DEVICE_CONTROL_TERMINAL_IDEMPOTENCY,
    CALL020_DEVICE_CONTROL_TERMINAL_RUN_BINDING,
    CALL020_DEVICE_CONTROL_TERMINAL_OPERATION_DEADLINE,
    CALL020_DEVICE_CONTROL_TERMINAL_RUNNER,
    CALL020_DEVICE_CONTROL_TERMINAL_HANDOFF,
    CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
    CALL020_DEVICE_CONTROL_TERMINAL_POST_STOP_TELEMETRY_UNAVAILABLE,
} call020_device_control_terminal_reason_t;

typedef struct {
    bool enabled;
    uint32_t frame_wait_timeout_ms;
    uint32_t io_wait_slice_ms;
    uint32_t max_io_calls;
    uint32_t max_operation_timeout_ms;
    bool result_phase_enabled;
    call020_operator_runner_config_t runner;
} call020_device_control_responder_config_t;

typedef struct {
    call020_device_control_state_t state;
    call020_device_control_terminal_reason_t terminal_reason;
    esp_err_t first_error;
    int owner_core_id;
    uint32_t open_calls;
    uint32_t serve_calls;
    uint32_t complete_requests;
    uint32_t complete_responses;
    uint32_t duplicate_requests;
    uint32_t operation_identity_rejections;
    uint32_t run_binding_rejections;
    uint32_t zero_progress_timeouts;
    uint32_t partial_or_unknown_transfers;
    uint32_t malformed_frames;
    uint32_t runner_prepare_calls;
    uint32_t runner_start_calls;
    uint32_t runner_cancel_calls;
    uint32_t runner_join_calls;
    uint32_t runner_close_calls;
    uint32_t lease_handoff_calls;
    uint32_t media_finalize_calls;
    uint32_t local_cleanup_attempts;
    uint32_t local_cleanup_failures;
    uint32_t request_buffers_cleared;
    uint32_t response_buffers_cleared;
    bool enabled_by_config;
    bool dedicated_build_enabled;
    bool run_id_bound;
    bool lease_installed;
    bool start_ack_fully_transmitted;
    bool control_writes_permanently_disabled;
    bool media_started;
    bool media_workers_quiescent;
    bool media_output_safe_verified;
    bool media_runner_resources_closed;
    bool media_driver_lease_returned;
    bool physical_driver_close_confirmed;
    bool result_phase_enabled;
    bool post_stop_telemetry_supported;
    bool raw_audio_logged_or_persisted;
    bool identifiers_or_payload_logged;
    bool device_runtime_termination_proven;
    bool remote_cleanup_acknowledged_after_media;
    /* Local-only close-boundary data; RESULT and wire support remain false. */
    call020_operator_close_boundary_runtime_measurement_t
        close_boundary_measurement;
} call020_device_control_responder_metadata_t;

/* Opaque caller-owned storage; no heap allocation and no global singleton. */
typedef union {
    uint64_t alignment;
    uint8_t bytes[CALL020_DEVICE_CONTROL_CONTEXT_BYTES];
} call020_device_control_responder_t;

const char *call020_device_control_responder_version(void);

/* Pure initialization. It performs no USB, audio, GPIO, timer or network I/O. */
esp_err_t call020_device_control_responder_init(
    call020_device_control_responder_t *responder,
    const call020_device_control_responder_config_t *config);

/*
 * First hardware-affecting boundary. Installs one registry-backed USB
 * Serial/JTAG driver lease; it never adopts an unregistered existing driver.
 */
esp_err_t call020_device_control_responder_open_control(
    call020_device_control_responder_t *responder);

/*
 * Consume at most one complete request and emit at most one complete response.
 * Reads/writes/wait_tx_done are finite and bounded. A fully transmitted START
 * ACK is the final CONTROL byte: the function then irreversibly hands the same
 * lease to call020_operator_runner_start_with_usb_driver_lease().
 */
call020_device_control_serve_result_t
call020_device_control_responder_serve_once(
    call020_device_control_responder_t *responder);

/*
 * Local-only pre-MEDIA disposal/retry seam. It emits no bytes. START_UNKNOWN
 * cleanup is best effort and never reports remote termination as proven.
 */
esp_err_t call020_device_control_responder_abort_local(
    call020_device_control_responder_t *responder);

/*
 * Local-only post-MEDIA disposition. It emits no CONTROL or RESULT bytes.
 * The same-core lifecycle owner must first request cancellation and wait for
 * all four workers to become terminal. This seam repeats force-safe/cancel,
 * performs the bounded join, closes the runner (returning its borrowed lease),
 * and only then physically closes the returned driver lease. Cleanup success
 * is based on observed resource state, not on a historical media error.
 */
esp_err_t call020_device_control_responder_finish_media_local(
    call020_device_control_responder_t *responder);

esp_err_t call020_device_control_responder_get_metadata(
    const call020_device_control_responder_t *responder,
    call020_device_control_responder_metadata_t *metadata);

typedef struct {
    uint32_t api_version;
    esp_err_t (*init)(
        call020_device_control_responder_t *,
        const call020_device_control_responder_config_t *);
    esp_err_t (*open_control)(call020_device_control_responder_t *);
    call020_device_control_serve_result_t (*serve_once)(
        call020_device_control_responder_t *);
    esp_err_t (*abort_local)(call020_device_control_responder_t *);
    esp_err_t (*get_metadata)(
        const call020_device_control_responder_t *,
        call020_device_control_responder_metadata_t *);
} call020_device_control_responder_api_t;

/* Link retention only; obtaining the table has no hardware side effect. */
const call020_device_control_responder_api_t *
call020_device_control_responder_retained_entry(void);

#ifdef __cplusplus
}
#endif
