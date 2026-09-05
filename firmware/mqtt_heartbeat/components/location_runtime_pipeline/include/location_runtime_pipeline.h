#ifndef EGOLINK_LOCATION_RUNTIME_PIPELINE_H
#define EGOLINK_LOCATION_RUNTIME_PIPELINE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_engine_core.h"
#include "location_outbox_adapter.h"
#include "location_policy_core.h"
#include "location_state_emitter.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The narrower P0 pipeline identity profile makes the complete emitted
 * envelope provably fit the current 4096-byte persistent-outbox ceiling.
 * Every dynamic identifier is safe ASCII, so JSON escaping cannot expand it.
 */
#define EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES 48U
#define EGOLINK_LOCATION_RUNTIME_ID_CAPACITY \
    (EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES + 1U)
/*
 * Mechanical upper bound for the native serializer under this pipeline's
 * 48-byte identity profile: every field present, five maximum IDs, every
 * uint64/double writer at its lexical ceiling, and eight 128-byte reasons.
 * The native enums are shorter, so 2750 is deliberately conservative.
 */
#define EGOLINK_LOCATION_RUNTIME_STATE_JSON_PROVEN_MAX_BYTES 2750U
#define EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES 3072U
#define EGOLINK_LOCATION_RUNTIME_ENVELOPE_OVERHEAD_MAX_BYTES 814U
#define EGOLINK_LOCATION_RUNTIME_ENVELOPE_MAX_BYTES \
    EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES
#define EGOLINK_LOCATION_RUNTIME_CONTEXT_BYTES (8U * 1024U)
#define EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES 32U
#define EGOLINK_LOCATION_RUNTIME_INT64_MAX UINT64_C(9223372036854775807)

typedef struct {
    const char *data;
    size_t length;
} egolink_location_runtime_text_t;

typedef enum {
    EGOLINK_LOCATION_RUNTIME_CLOCK_UTC = 0,
    EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC,
} egolink_location_runtime_clock_domain_t;

typedef enum {
    EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE = 0,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_INITIAL_CURRENT,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT,
} egolink_location_runtime_publish_intent_t;

typedef enum {
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_NONE = 0U,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_POLICY_ACTION = 1U << 0,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_TRUSTED_UPDATE = 1U << 1,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_SOS_EVENT = 1U << 2,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_EXPLICIT_INITIAL = 1U << 3,
    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_EXPLICIT_CURRENT = 1U << 4,
} egolink_location_runtime_publish_reason_t;

typedef enum {
    EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH = 0,
    EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED,
    EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT,
    EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT,
    EGOLINK_LOCATION_RUNTIME_NOT_INITIALIZED,
    EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH,
    EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY,
    EGOLINK_LOCATION_RUNTIME_IDENTITY_CONFLICT,
    EGOLINK_LOCATION_RUNTIME_SEQUENCE_REGRESSION,
    EGOLINK_LOCATION_RUNTIME_TIME_REGRESSION,
    EGOLINK_LOCATION_RUNTIME_INVALID_PUBLISH_INTENT,
    EGOLINK_LOCATION_RUNTIME_FINGERPRINT_FAILED,
    EGOLINK_LOCATION_RUNTIME_ENGINE_FAILED,
    EGOLINK_LOCATION_RUNTIME_POLICY_MAPPING_FAILED,
    EGOLINK_LOCATION_RUNTIME_POLICY_FAILED,
    EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED,
    EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED,
    EGOLINK_LOCATION_RUNTIME_INTERNAL_INVARIANT_FAILED,
} egolink_location_runtime_status_t;

typedef struct {
    egolink_location_runtime_text_t device_id;
    uint64_t boot_count;
    egolink_location_runtime_text_t session_id;
    egolink_location_runtime_text_t stream_id;
    egolink_location_runtime_clock_domain_t clock_domain;
    egolink_location_runtime_text_t monotonic_clock_domain_id;
} egolink_location_runtime_owner_t;

typedef struct {
    egolink_location_runtime_text_t device_id;
    uint64_t boot_count;
    egolink_location_runtime_text_t session_id;
    egolink_location_runtime_text_t stream_id;
    uint64_t sequence_id;
    egolink_location_runtime_text_t observation_id;
    uint64_t event_time_ms;
    egolink_location_event_time_source_t event_time_source;
    uint64_t event_time_ns;
    egolink_location_runtime_text_t monotonic_clock_domain_id;
} egolink_location_runtime_identity_t;

typedef struct {
    egolink_location_runtime_identity_t identity;
    egolink_location_engine_observation_t observation;
    egolink_location_runtime_publish_intent_t publish_intent;
} egolink_location_runtime_input_t;

/*
 * Both buffers are caller-owned and cleared before every return. Keep this
 * object in static/integration-owned memory, not on a normal task stack.
 */
typedef struct {
    char state_json[EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES + 1U];
    char envelope[EGOLINK_LOCATION_RUNTIME_ENVELOPE_MAX_BYTES + 1U];
} egolink_location_runtime_scratch_t;

/* No location state or coordinate is returned through this result. */
typedef struct {
    egolink_location_runtime_status_t status;
    egolink_location_engine_result_t engine_status;
    egolink_location_policy_result_t policy_status;
    egolink_location_engine_result_t serializer_status;
    egolink_location_outbox_enqueue_status_t enqueue_status;
    bool policy_evaluated;
    bool publish_required;
    bool published;
    bool retry_latched;
    uint32_t publish_reasons;
    egolink_location_policy_decision_t policy_decision;
    egolink_location_outbox_enqueue_result_t enqueue_result;
} egolink_location_runtime_result_t;

/* Opaque, caller-owned, statically allocated single-owner context. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_LOCATION_RUNTIME_CONTEXT_BYTES];
} egolink_location_runtime_pipeline_t;

/*
 * Initializes only the pipeline's frozen engine/policy cores. The adapter and
 * outbox must already be initialized by their owner; this function neither
 * initializes nor closes either object.
 */
egolink_location_runtime_status_t egolink_location_runtime_pipeline_init(
    egolink_location_runtime_pipeline_t *pipeline,
    egolink_location_outbox_adapter_t *adapter,
    const egolink_location_runtime_owner_t *owner);

/*
 * This API is intentionally non-reentrant: exactly one owner must serialize
 * it with adapter/outbox send and ACK calls. Complete identity/order checks
 * occur before either reducer. Only the immediately adjacent exact replay is
 * reported DUPLICATE_INPUT without advancing engine, policy or outbox.
 * Reused identity with different content and old sequence/time fail closed.
 *
 * A publish failure latches RETRY_REQUIRED without committing either reducer
 * or the input identity. Until that exact input succeeds (enqueue OK or
 * durable DUPLICATE), every different input returns BLOCKED_RETRY_REQUIRED.
 * This is a temporary backpressure boundary, not a persistent observation
 * journal. Restart recovery/replay of uncommitted observations remains caller
 * work and reboot equivalence is not claimed.
 *
 * Fixed publish rule: enqueue only for a frozen-policy upload action, an
 * accepted trusted GNSS/coarse update, every SOS event, or explicit initial/
 * current-state intent. IMU_SAMPLE updates only the engine and never aliases
 * another policy event. Routine ticks do not enqueue by default.
 */
egolink_location_runtime_status_t egolink_location_runtime_pipeline_process(
    egolink_location_runtime_pipeline_t *pipeline,
    const egolink_location_runtime_input_t *input,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_runtime_result_t *result);

const char *egolink_location_runtime_status_name(
    egolink_location_runtime_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_RUNTIME_PIPELINE_H */
