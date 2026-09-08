/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020R default-off single-task lifecycle owner.
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "call020_device_control_responder.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_DEVICE_CONTROL_OWNER_VERSION \
    "call020-device-control-owner-v1"
#define CALL020_DEVICE_CONTROL_OWNER_MAX_POLL_MS UINT32_C(100)
#define CALL020_DEVICE_CONTROL_OWNER_MAX_CONTROL_TIMEOUT_US \
    UINT64_C(300000000)
#define CALL020_DEVICE_CONTROL_OWNER_MAX_QUIESCE_GRACE_US \
    UINT64_C(5000000)
#define CALL020_DEVICE_CONTROL_OWNER_MAX_RECOVERY_BACKOFF_MS \
    UINT32_C(5000)

typedef enum {
    CALL020_DEVICE_OWNER_UNINITIALIZED = 0,
    CALL020_DEVICE_OWNER_DORMANT,
    CALL020_DEVICE_OWNER_CONTROL,
    CALL020_DEVICE_OWNER_MEDIA,
    CALL020_DEVICE_OWNER_QUIESCING,
    CALL020_DEVICE_OWNER_RECOVERING,
    CALL020_DEVICE_OWNER_CLOSED,
    CALL020_DEVICE_OWNER_TERMINAL,
} call020_device_control_owner_state_t;

typedef struct {
    bool enabled;
    uint64_t control_total_timeout_us;
    uint32_t poll_slice_ms;
    uint64_t media_quiesce_grace_us;
    call020_device_control_responder_config_t responder;
} call020_device_control_owner_config_t;

typedef struct {
    call020_device_control_owner_state_t state;
    esp_err_t first_error;
    int owner_core_id;
    uint32_t run_calls;
    uint32_t control_serve_calls;
    uint32_t runner_metadata_polls;
    uint32_t local_cancel_calls;
    uint32_t media_finalize_calls;
    uint32_t cleanup_recovery_attempts;
    uint32_t cleanup_backoff_waits;
    bool enabled_by_config;
    bool dedicated_build_enabled;
    bool control_total_deadline_reached;
    bool media_deadline_reached;
    bool media_run_limit_reached;
    bool media_failure_observed;
    bool all_four_workers_terminal;
    bool cleanup_complete;
    bool device_runtime_termination_proven;
    bool physical_driver_close_confirmed;
    esp_err_t responder_first_error;
    call020_device_control_terminal_reason_t responder_terminal_reason;
    bool emitted_post_start_control;
    bool result_phase_enabled;
    bool raw_audio_logged_or_persisted;
    /* Local-only close-boundary data; no post-MEDIA wire write is implied. */
    call020_operator_close_boundary_runtime_measurement_t
        close_boundary_measurement;
} call020_device_control_owner_metadata_t;

const char *call020_device_control_owner_version(void);

/* Pure, global-singleton initialization; opens no driver or audio resource. */
esp_err_t call020_device_control_owner_init(
    const call020_device_control_owner_config_t *config);

/*
 * Blocking one-shot lifecycle. The caller is the only mutating owner and all
 * responder/runner/lease operations remain on the caller's CPU core. Once a
 * resource may have been acquired, incomplete local cleanup proof enters an
 * indefinite fail-closed retry loop with bounded backoff: this function will
 * not return, and the caller must not release the owner task, until complete
 * worker/runner/lease/physical-close proof has been observed.
 */
esp_err_t call020_device_control_owner_run(void);

/* Read after run returns; concurrent polling is intentionally unsupported. */
esp_err_t call020_device_control_owner_get_metadata(
    call020_device_control_owner_metadata_t *metadata);

#ifdef __cplusplus
}
#endif
