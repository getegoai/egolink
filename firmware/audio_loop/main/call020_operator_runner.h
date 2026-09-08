/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020G retained, non-autorun operator control seam.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "call020_wearable_composition.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_OPERATOR_RUNNER_VERSION "call020-operator-runner-v1"
#define CALL020_OPERATOR_RUNNER_API_VERSION UINT32_C(1)
#define CALL020_OPERATOR_EPHEMERAL_NONCE_BYTES UINT32_C(16)
#define CALL020_OPERATOR_IDENTITY_CAPACITY UINT32_C(40)
#define CALL020_OPERATOR_RANDOM_ATTEMPTS UINT32_C(3)
/* Keep each USB driver ring bounded to five complete 814-byte wires. */
#define CALL020_OPERATOR_USB_BUFFER_MAX_BYTES UINT32_C(4096)

typedef enum {
    CALL020_OPERATOR_DORMANT = 0,
    CALL020_OPERATOR_PREPARED,
    CALL020_OPERATOR_STARTING,
    CALL020_OPERATOR_RUNNING,
    CALL020_OPERATOR_STOPPING,
    CALL020_OPERATOR_JOINED,
    CALL020_OPERATOR_TERMINAL,
    CALL020_OPERATOR_CLOSED,
} call020_operator_runner_state_t;

typedef enum {
    CALL020_OPERATOR_RANDOM_SOURCE_UNSPECIFIED = 0,
    CALL020_OPERATOR_RANDOM_SOURCE_ESP_FILL_RANDOM,
} call020_operator_random_source_t;

typedef enum {
    CALL020_OPERATOR_RANDOM_QUALITY_UNSPECIFIED = 0,
    /* No RF entropy-source state or cryptographic quality is attested here. */
    CALL020_OPERATOR_RANDOM_QUALITY_UNVERIFIED,
} call020_operator_random_quality_t;

/*
 * Numeric/session-budget inputs only. All endpoint identities are generated
 * at prepare time; this API accepts no fixture or production identity string.
 */
typedef struct {
    size_t handoff_queue_frames;
    uint64_t frame_deadline_slack_us;
    uint64_t downlink_playout_delay_us;
    uint64_t max_runtime_us;
    uint64_t audio_io_timeout_us;
    uint64_t usb_read_poll_us;
    uint64_t join_timeout_us;
    call020_usb_endpoint_config_t usb_endpoint;
} call020_operator_runner_config_t;

/*
 * Ephemeral routing identifiers are non-secret, correlated role labels made
 * from one random nonce plus distinct prefixes. They are not authentication
 * credentials. They must be transferred to the matching host control plane
 * without logging media and remain valid until close or the next prepare.
 */
typedef struct {
    char session_id[CALL020_OPERATOR_IDENTITY_CAPACITY];
    char device_id[CALL020_OPERATOR_IDENTITY_CAPACITY];
    char guardian_id[CALL020_OPERATOR_IDENTITY_CAPACITY];
    char uplink_clock_id[CALL020_OPERATOR_IDENTITY_CAPACITY];
    char downlink_clock_id[CALL020_OPERATOR_IDENTITY_CAPACITY];
    uint32_t nonce_bits;
    call020_operator_random_source_t random_source;
    call020_operator_random_quality_t random_quality;
    bool correlated_routing_ids;
    call020_wearable_identity_provenance_t provenance;
} call020_operator_session_descriptor_t;

/*
 * Local-only close-boundary measurement. The current heap sample is taken
 * after runner/composition resources report CLOSED, but before the Idle task
 * is guaranteed to reclaim storage for self-deleted workers. It is therefore
 * explicitly pre-Idle-reclamation, not a final post-stop heap measurement.
 * The boot-minimum heap remains the allocator's lifetime minimum. This is not
 * a wire RESULT and does not attest remote cleanup or physical driver closure.
 */
typedef struct {
    bool valid;
    uint64_t captured_at_monotonic_ns;
    uint32_t close_boundary_pre_idle_reclamation_free_internal_heap_bytes;
    uint32_t boot_minimum_free_internal_heap_bytes;
    uint32_t worker_terminal_boundary_sampled_mask;
    uint32_t worker_terminal_boundary_stack_high_watermark_bytes[
        CALL020_WEARABLE_WORKER_COUNT];
} call020_operator_close_boundary_runtime_measurement_t;

typedef struct {
    call020_operator_runner_state_t state;
    esp_err_t first_error;
    int owner_core_id;
    uint32_t prepare_calls;
    uint32_t start_calls;
    uint32_t cancel_calls;
    uint32_t join_calls;
    uint32_t close_calls;
    uint32_t random_attempts;
    bool identities_generated;
    bool composition_installed;
    bool start_requested;
    bool safety_forced;
    bool resources_closed;
    bool usb_driver_lease_supplied;
    bool usb_driver_lease_borrowed;
    bool usb_driver_binding_closed;
    bool usb_driver_lease_returned;
    bool usb_driver_uninstalled_by_runner;
    uint64_t usb_driver_lease_generation;
    call020_wearable_composition_metadata_t composition;
    call020_operator_close_boundary_runtime_measurement_t
        close_boundary_measurement;
} call020_operator_runner_metadata_t;

const char *call020_operator_runner_version(void);

/*
 * All mutating calls are serialized by the caller and must execute on the CPU
 * core captured by prepare. Prepare only validates budgets and requests a
 * runtime nonce through esp_fill_random; its entropy quality is explicitly
 * unverified. Prepare opens no codec, GPIO, I2S or USB driver.
 */
esp_err_t call020_operator_runner_prepare(
    const call020_operator_runner_config_t *config,
    call020_operator_session_descriptor_t *descriptor);

/* The first hardware-affecting operation; never called automatically. */
esp_err_t call020_operator_runner_start(void);

/*
 * Additive CALL-020O entry for a local CONTROL bootstrap that already owns a
 * HANDOFF_READY driver lease. The v1 retained remote table remains unchanged;
 * a future control-protocol revision may bind this direct local seam.
 */
esp_err_t call020_operator_runner_start_with_usb_driver_lease(
    call020_usb_driver_lease_t *lease);

/* Requests cancel and verified mute/PA-safe disposition. */
esp_err_t call020_operator_runner_cancel(void);

/* Bounded by the prepared join budget; cancel should normally precede join. */
esp_err_t call020_operator_runner_join(void);

/* Same-core cancel -> safe -> bounded join -> close; safe to retry. */
esp_err_t call020_operator_runner_close(void);

esp_err_t call020_operator_runner_get_descriptor(
    call020_operator_session_descriptor_t *descriptor);

esp_err_t call020_operator_runner_get_metadata(
    call020_operator_runner_metadata_t *metadata);

/*
 * The dedicated link profile retains this table and its transitive D/E/F
 * references. Nothing invokes it at boot, and obtaining the pointer is inert.
 */
typedef struct {
    uint32_t api_version;
    esp_err_t (*prepare)(
        const call020_operator_runner_config_t *,
        call020_operator_session_descriptor_t *);
    esp_err_t (*start)(void);
    esp_err_t (*cancel)(void);
    esp_err_t (*join)(void);
    esp_err_t (*close)(void);
    esp_err_t (*get_descriptor)(call020_operator_session_descriptor_t *);
    esp_err_t (*get_metadata)(call020_operator_runner_metadata_t *);
} call020_operator_runner_api_t;

const call020_operator_runner_api_t *
call020_operator_runner_retained_entry(void);

#ifdef __cplusplus
}
#endif
