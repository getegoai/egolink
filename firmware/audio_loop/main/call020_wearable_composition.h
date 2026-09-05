/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020F caller-owned wearable media composition. This header declares a
 * bounded operator seam; ordinary app_main does not instantiate it.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "call020_media_adapter_core.h"
#include "call020_usb_serial_jtag_endpoint.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/portmacro.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "safe_audio_initializer_v1.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_WEARABLE_COMPOSITION_VERSION \
    "call020-wearable-composition-v1"
#define CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES UINT32_C(4)
#define CALL020_WEARABLE_AUDIO_IO_TIMEOUT_MAX_US UINT64_C(100000)
#define CALL020_WEARABLE_USB_READ_POLL_MAX_US UINT64_C(100000)
#define CALL020_WEARABLE_JOIN_TIMEOUT_MAX_US UINT64_C(5000000)
#define CALL020_WEARABLE_TASK_STACK_BYTES UINT32_C(4096)
#define CALL020_WEARABLE_TASK_PRIORITY UINT32_C(5)
#define CALL020_WEARABLE_FRAME_INTERVAL_US UINT64_C(20000)

typedef enum {
    CALL020_WEARABLE_IDENTITY_UNSPECIFIED = 0,
    CALL020_WEARABLE_IDENTITY_OPERATOR_SUPPLIED,
    CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL,
    CALL020_WEARABLE_IDENTITY_NONPRODUCTION_BUILD_FIXTURE,
} call020_wearable_identity_provenance_t;

typedef enum {
    CALL020_WEARABLE_UNINITIALIZED = 0,
    CALL020_WEARABLE_READY,
    CALL020_WEARABLE_RUNNING,
    CALL020_WEARABLE_STOPPING,
    CALL020_WEARABLE_STOPPED,
    CALL020_WEARABLE_TERMINAL,
    CALL020_WEARABLE_CLOSED,
} call020_wearable_state_t;

typedef enum {
    CALL020_WEARABLE_TERMINAL_NONE = 0,
    CALL020_WEARABLE_TERMINAL_CLOCK,
    CALL020_WEARABLE_TERMINAL_RUNTIME,
    CALL020_WEARABLE_TERMINAL_WORKER_CREATE,
    CALL020_WEARABLE_TERMINAL_HANDOFF_OVERFLOW,
    CALL020_WEARABLE_TERMINAL_AUDIO_CAPTURE,
    CALL020_WEARABLE_TERMINAL_AUDIO_OUTPUT,
    CALL020_WEARABLE_TERMINAL_USB_UPLINK,
    CALL020_WEARABLE_TERMINAL_USB_DOWNLINK,
    CALL020_WEARABLE_TERMINAL_UPLINK_CORE,
    CALL020_WEARABLE_TERMINAL_DOWNLINK_CORE,
    CALL020_WEARABLE_TERMINAL_OUTPUT_SAFETY,
    CALL020_WEARABLE_TERMINAL_JOIN_TIMEOUT,
    CALL020_WEARABLE_TERMINAL_ENDPOINT_CLOSE,
    CALL020_WEARABLE_TERMINAL_AUDIO_CLOSE,
} call020_wearable_terminal_reason_t;

typedef struct {
    const char *session_id;
    const char *device_id;
    const char *guardian_id;
    const char *uplink_clock_id;
    const char *downlink_clock_id;
    call020_wearable_identity_provenance_t identity_provenance;
    size_t handoff_queue_frames;
    uint64_t frame_deadline_slack_us;
    uint64_t downlink_playout_delay_us;
    uint64_t max_runtime_us;
    uint64_t audio_io_timeout_us;
    uint64_t usb_read_poll_us;
    uint64_t join_timeout_us;
    call020_usb_endpoint_config_t usb_endpoint;
} call020_wearable_composition_config_t;

typedef struct {
    uint64_t source_time_ns;
    int16_t stereo[CALL020_MEDIA_STEREO_VALUES];
} call020_wearable_uplink_handoff_t;

typedef struct {
    size_t wire_bytes;
    uint8_t wire[CALL020_MEDIA_WIRE_MAX_BYTES];
} call020_wearable_downlink_handoff_t;

typedef struct {
    call020_wearable_state_t state;
    call020_wearable_terminal_reason_t terminal_reason;
    call020_wearable_identity_provenance_t identity_provenance;
    esp_err_t first_error;
    uint64_t captured_frames;
    uint64_t uplink_frames_sent;
    uint64_t downlink_wires_received;
    uint64_t rendered_frames;
    uint64_t zero_progress_read_timeouts;
    uint64_t zero_progress_write_timeouts;
    uint64_t handoff_overflows;
    uint64_t cancellation_requests;
    uint64_t join_timeouts;
    bool run_limit_reached;
    bool pa_off_verified;
    bool codec_muted_verified;
    bool output_volume_verified;
    uint32_t output_volume;
    bool endpoint_installed;
    call020_usb_endpoint_driver_ownership_t usb_driver_ownership;
    uint64_t usb_driver_lease_generation;
    bool usb_driver_binding_closed;
    bool usb_driver_uninstalled_by_composition;
    bool usb_driver_lease_returned;
    bool usb_driver_lifetime_owned_by_caller;
    uint32_t workers_created;
    uint32_t workers_finished;
} call020_wearable_composition_metadata_t;

/*
 * Caller owns this context and must provide it zero-initialized. The two core
 * instances intentionally have one worker owner each: uplink transport owns
 * uplink_core; downlink audio owns downlink_core. No core mutex is held over
 * USB or I2S calls. Queue backing storage and named scratch are cleared during
 * disposition and close; external driver/DMA/host copies are out of scope.
 */
typedef struct {
    portMUX_TYPE lock;
    bool initialized;
    bool cancel_requested;
    bool output_enabled;
    bool audio_initialized;
    bool speaker_opened;
    bool microphone_opened;
    bool endpoint_installed;
    bool endpoint_borrowed_from_lease;
    uint32_t created_worker_bits;
    uint64_t runtime_deadline_us;
    uint64_t next_capture_due_us;
    uint64_t audio_io_timeout_us;
    uint64_t usb_read_poll_us;
    uint64_t join_timeout_us;
    size_t expected_downlink_wire_bytes;
    size_t handoff_queue_frames;
    call020_wearable_state_t state;
    call020_wearable_terminal_reason_t terminal_reason;
    esp_err_t first_error;
    call020_wearable_identity_provenance_t identity_provenance;
    call010_safe_audio_v1_t audio;
    call020_usb_serial_jtag_endpoint_t endpoint;
    call020_media_adapter_core_t uplink_core;
    call020_media_adapter_core_t downlink_core;
    EventGroupHandle_t worker_events;
    StaticEventGroup_t worker_events_storage;
    QueueHandle_t uplink_handoff_queue;
    StaticQueue_t uplink_handoff_queue_control;
    uint8_t uplink_handoff_queue_storage[
        CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES *
        sizeof(call020_wearable_uplink_handoff_t)];
    QueueHandle_t downlink_handoff_queue;
    StaticQueue_t downlink_handoff_queue_control;
    uint8_t downlink_handoff_queue_storage[
        CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES *
        sizeof(call020_wearable_downlink_handoff_t)];
    call020_wearable_uplink_handoff_t capture_scratch;
    call020_wearable_uplink_handoff_t uplink_scratch;
    call020_wearable_downlink_handoff_t usb_rx_scratch;
    call020_wearable_downlink_handoff_t downlink_scratch;
    TaskHandle_t audio_capture_task;
    TaskHandle_t usb_uplink_task;
    TaskHandle_t usb_downlink_task;
    TaskHandle_t audio_output_task;
    call020_wearable_composition_metadata_t metadata;
} call020_wearable_composition_t;

const char *call020_wearable_composition_version(void);

/*
 * Install constructs and opens the actual safe_audio_initializer_v1
 * codec/I2S path and installs CALL-020E. It is fail-closed unless the dedicated
 * console-free build is selected and identity provenance is operator-supplied.
 * Install and close must be called on the same CPU core because CALL-020E does.
 */
esp_err_t call020_wearable_composition_install(
    call020_wearable_composition_t *composition,
    const call020_wearable_composition_config_t *config);

/*
 * Same composition with a pre-installed, registry-backed USB driver lease.
 * Adoption is same-core and single-generation. Close returns the driver to
 * the lease owner and never uninstalls it. The ordinary install API is
 * unchanged and continues to own its driver installation and removal.
 */
esp_err_t call020_wearable_composition_install_with_usb_driver_lease(
    call020_wearable_composition_t *composition,
    const call020_wearable_composition_config_t *config,
    call020_usb_driver_lease_t *lease);

/* One start per installed identity. Four workers begin only after all exist. */
esp_err_t call020_wearable_composition_start(
    call020_wearable_composition_t *composition);

/* Non-blocking request: latches cancel, disables PA, and interrupts USB waits. */
esp_err_t call020_wearable_composition_request_cancel(
    call020_wearable_composition_t *composition);

/*
 * Fail-safe control for an installed composition. It requests cancellation,
 * drives PA low and verifies codec mute without uninstalling the endpoint.
 * This is the runner's error path when full same-core close cannot yet occur.
 */
esp_err_t call020_wearable_composition_force_safe(
    call020_wearable_composition_t *composition);

/* Waits at most the configured join budget; it never uninstalls the endpoint. */
esp_err_t call020_wearable_composition_join(
    call020_wearable_composition_t *composition);

/*
 * Cancel -> bounded join -> verified mute/PA-off -> endpoint close -> audio
 * cleanup. A join timeout leaves endpoint/audio installed for a later retry.
 */
esp_err_t call020_wearable_composition_close(
    call020_wearable_composition_t *composition);

esp_err_t call020_wearable_composition_get_metadata(
    call020_wearable_composition_t *composition,
    call020_wearable_composition_metadata_t *metadata);

#ifdef __cplusplus
}
#endif
