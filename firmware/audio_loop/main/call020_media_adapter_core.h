/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020D framing/queue core only. This is not a USB CDC endpoint and it
 * does not own an audio device, task, pin, codec, console or transport.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_MEDIA_ADAPTER_CORE_VERSION "call020-media-adapter-core-v1"
#define CALL020_MEDIA_SAMPLE_RATE_HZ UINT32_C(16000)
#define CALL020_MEDIA_FRAME_MS UINT32_C(20)
#define CALL020_MEDIA_MONO_SAMPLES UINT32_C(320)
#define CALL020_MEDIA_MONO_BYTES UINT32_C(640)
#define CALL020_MEDIA_STEREO_VALUES UINT32_C(640)
#define CALL020_MEDIA_STEREO_BYTES UINT32_C(1280)
#define CALL020_MEDIA_IDENTIFIER_MAX_BYTES UINT32_C(128)
#define CALL020_MEDIA_WIRE_HEADER_BYTES UINT32_C(34)
#define CALL020_MEDIA_WIRE_CRC_BYTES UINT32_C(4)
#define CALL020_MEDIA_WIRE_MAX_BYTES UINT32_C(1190)
#define CALL020_MEDIA_QUEUE_MAX_FRAMES UINT32_C(8)
#define CALL020_MEDIA_MAX_RUNTIME_US UINT64_C(600000000)

typedef enum {
    CALL020_MEDIA_CORE_UNINITIALIZED = 0,
    CALL020_MEDIA_CORE_READY,
    CALL020_MEDIA_CORE_RUNNING,
    CALL020_MEDIA_CORE_STOPPED,
    CALL020_MEDIA_CORE_TERMINAL,
} call020_media_core_state_t;

typedef enum {
    CALL020_MEDIA_TERMINAL_NONE = 0,
    CALL020_MEDIA_TERMINAL_CLOCK_REGRESSION,
    CALL020_MEDIA_TERMINAL_RUNTIME_DEADLINE,
    CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
    CALL020_MEDIA_TERMINAL_QUEUE_OVERFLOW,
    CALL020_MEDIA_TERMINAL_PROTOCOL,
    CALL020_MEDIA_TERMINAL_PARTIAL_TIMEOUT,
    CALL020_MEDIA_TERMINAL_UNKNOWN_TIMEOUT,
    CALL020_MEDIA_TERMINAL_TRANSPORT,
    CALL020_MEDIA_TERMINAL_AUDIO_OUTPUT,
    CALL020_MEDIA_TERMINAL_PA_OFF,
} call020_media_terminal_reason_t;

/*
 * Ordered-stream retries are safe only when the transport proves zero-byte
 * progress. Partial and unknown progress are terminal because retrying could
 * duplicate bytes or lose framing.
 */
typedef enum {
    CALL020_MEDIA_TRANSFER_OK = 0,
    CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS,
    CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL,
    CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN,
    CALL020_MEDIA_TRANSFER_ERROR,
} call020_media_transfer_result_t;

typedef esp_err_t (*call020_media_force_pa_off_fn)(void *user_context);

typedef call020_media_transfer_result_t (*call020_media_wire_write_fn)(
    void *user_context,
    const uint8_t *wire,
    size_t wire_bytes,
    uint64_t absolute_deadline_us);

typedef esp_err_t (*call020_media_stereo_write_fn)(
    void *user_context,
    const int16_t *stereo_values,
    size_t stereo_value_count,
    uint64_t absolute_deadline_us);

typedef struct {
    const char *session_id;
    const char *device_id;
    const char *guardian_id;
    const char *uplink_clock_id;
    const char *downlink_clock_id;
    size_t queue_capacity_frames;
    uint64_t frame_deadline_slack_us;
    uint64_t downlink_playout_delay_us;
    uint64_t max_runtime_us;
    call020_media_force_pa_off_fn force_pa_off;
    void *pa_user_context;
} call020_media_adapter_config_t;

typedef struct {
    uint64_t sequence;
    uint64_t source_time_ns;
    uint64_t due_us;
    uint64_t deadline_us;
    uint8_t media[CALL020_MEDIA_MONO_BYTES];
} call020_media_slot_t;

typedef struct {
    call020_media_slot_t slots[CALL020_MEDIA_QUEUE_MAX_FRAMES];
    size_t head;
    size_t count;
} call020_media_queue_t;

typedef struct {
    call020_media_core_state_t state;
    call020_media_terminal_reason_t terminal_reason;
    uint64_t uplink_frames_accepted;
    uint64_t uplink_frames_sent;
    uint64_t downlink_frames_accepted;
    uint64_t downlink_frames_rendered;
    uint64_t zero_progress_timeouts;
    uint64_t terminal_timeouts;
    uint64_t queue_overflows;
    uint64_t protocol_failures;
    uint64_t deadline_failures;
    uint64_t cleanup_drops;
    size_t uplink_queue_depth;
    size_t downlink_queue_depth;
} call020_media_adapter_metadata_t;

typedef struct {
    bool initialized;
    call020_media_core_state_t state;
    call020_media_terminal_reason_t terminal_reason;
    size_t queue_capacity_frames;
    uint64_t frame_deadline_slack_us;
    uint64_t downlink_playout_delay_us;
    uint64_t max_runtime_us;
    uint64_t started_us;
    uint64_t runtime_deadline_us;
    uint64_t last_now_us;
    uint64_t next_uplink_due_us;
    uint64_t next_uplink_sequence;
    uint64_t last_uplink_source_time_ns;
    bool has_uplink_source_time;
    uint64_t expected_downlink_sequence;
    uint64_t last_downlink_source_time_ns;
    bool has_downlink_source_time;
    bool has_downlink_playout_epoch;
    uint64_t next_downlink_due_us;
    char session_id[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U];
    char device_id[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U];
    char guardian_id[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U];
    char uplink_clock_id[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U];
    char downlink_clock_id[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U];
    call020_media_force_pa_off_fn force_pa_off;
    void *pa_user_context;
    call020_media_queue_t uplink_queue;
    call020_media_queue_t downlink_queue;
    uint8_t wire_scratch[CALL020_MEDIA_WIRE_MAX_BYTES];
    int16_t stereo_scratch[CALL020_MEDIA_STEREO_VALUES];
    call020_media_adapter_metadata_t metadata;
} call020_media_adapter_core_t;

const char *call020_media_adapter_core_version(void);

esp_err_t call020_media_adapter_core_init(
    call020_media_adapter_core_t *core,
    const call020_media_adapter_config_t *config);

esp_err_t call020_media_adapter_core_start(
    call020_media_adapter_core_t *core, uint64_t monotonic_now_us);

/*
 * Takes ownership only when stereo_value_count is exactly 640. Every such
 * input buffer is cleared before return on success and all failure branches.
 */
esp_err_t call020_media_adapter_core_offer_uplink_stereo(
    call020_media_adapter_core_t *core,
    int16_t *stereo_values,
    size_t stereo_value_count,
    uint64_t source_time_ns,
    uint64_t monotonic_now_us);

/*
 * Encodes and offers the head uplink frame to one ordered-stream write. The
 * encoded scratch is always cleared. A zero-progress timeout is retryable;
 * partial/unknown progress and all other transport failures are terminal.
 */
esp_err_t call020_media_adapter_core_flush_uplink(
    call020_media_adapter_core_t *core,
    uint64_t monotonic_now_us,
    call020_media_wire_write_fn write_wire,
    void *write_user_context);

/*
 * Consumes a complete CALL-020B wire frame. The supplied mutable wire buffer
 * is cleared before return on every success and rejection branch.
 */
esp_err_t call020_media_adapter_core_offer_downlink_wire(
    call020_media_adapter_core_t *core,
    uint8_t *wire,
    size_t wire_bytes,
    uint64_t monotonic_now_us);

/* Expands mono to dual-channel samples only for the duration of the callback. */
esp_err_t call020_media_adapter_core_render_downlink(
    call020_media_adapter_core_t *core,
    uint64_t monotonic_now_us,
    call020_media_stereo_write_fn write_stereo,
    void *write_user_context);

esp_err_t call020_media_adapter_core_note_stream_timeout(
    call020_media_adapter_core_t *core,
    call020_media_transfer_result_t timeout_progress);

esp_err_t call020_media_adapter_core_tick(
    call020_media_adapter_core_t *core, uint64_t monotonic_now_us);

esp_err_t call020_media_adapter_core_stop(call020_media_adapter_core_t *core);

esp_err_t call020_media_adapter_core_deinit(call020_media_adapter_core_t *core);

esp_err_t call020_media_adapter_core_get_metadata(
    const call020_media_adapter_core_t *core,
    call020_media_adapter_metadata_t *metadata);

#ifdef __cplusplus
}
#endif
