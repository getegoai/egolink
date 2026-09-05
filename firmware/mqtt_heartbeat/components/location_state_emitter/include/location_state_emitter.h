#ifndef EGOLINK_LOCATION_STATE_EMITTER_H
#define EGOLINK_LOCATION_STATE_EMITTER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_STATE_ENVELOPE_CONTRACT_VERSION \
    "egolink.location_state_envelope.v0.1"
#define EGOLINK_LOCATION_ENGINE_CONTRACT_VERSION \
    "egolink.location_engine.v0.1"
#define EGOLINK_SENSOR_POLICY_CONTRACT_VERSION \
    "egolink.sensor_policy_config.v0.1"
#define EGOLINK_SENSOR_POLICY_SEMANTIC_VERSION \
    "egolink.sensor_policy.semantic.v0.1"
#define EGOLINK_SENSOR_POLICY_CONFIG_ID \
    "p0-sprint1-engineering-default-20260823"
#define EGOLINK_SENSOR_POLICY_CONFIG_HASH \
    "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"

/* Device/session IDs also serve as durable-outbox identity fields. */
#define EGOLINK_LOCATION_STATE_OUTBOX_ID_MAX_BYTES 128U
#define EGOLINK_LOCATION_STATE_ID_MAX_BYTES 256U
#define EGOLINK_LOCATION_STATE_JSON_MAX_BYTES 4096U
#define EGOLINK_LOCATION_STATE_ENVELOPE_MAX_BYTES 12288U
#define EGOLINK_LOCATION_STATE_CONFIG_HASH_BYTES 64U

typedef struct {
    const char *data;
    size_t length;
} egolink_location_state_text_t;

typedef enum {
    EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS = 0,
    EGOLINK_LOCATION_TIME_GNSS_SOURCE_UTC_NS,
    EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS,
} egolink_location_event_time_source_t;

typedef struct {
    egolink_location_state_text_t contract_version;
    egolink_location_state_text_t semantic_validation;
    egolink_location_state_text_t config_id;
    egolink_location_state_text_t config_hash;
} egolink_location_policy_identity_t;

/*
 * location_state_json is an already-evaluated, compact Location Engine v0
 * state object.  This component checks only its root object, contract version,
 * event-time binding and absence of server_receive_time_ms. It deliberately
 * does not duplicate the full Location Engine reducer or semantic validator;
 * the receiving server remains the complete state-contract oracle.
 */
typedef struct {
    egolink_location_state_text_t device_id;
    uint64_t boot_count;
    egolink_location_state_text_t session_id;
    uint64_t event_time_ms;
    egolink_location_event_time_source_t event_time_source;
    uint64_t event_time_ns;
    egolink_location_state_text_t monotonic_clock_domain_id;
    uint64_t sequence_id;
    egolink_location_state_text_t observation_id;
    egolink_location_policy_identity_t policy_identity;
    egolink_location_state_text_t location_state_json;
} egolink_location_state_emit_input_t;

typedef enum {
    EGOLINK_LOCATION_STATE_EMIT_OK = 0,
    EGOLINK_LOCATION_STATE_EMIT_INVALID_ARGUMENT,
    EGOLINK_LOCATION_STATE_EMIT_INVALID_IDENTITY,
    EGOLINK_LOCATION_STATE_EMIT_INVALID_CLOCK,
    EGOLINK_LOCATION_STATE_EMIT_INVALID_POLICY_IDENTITY,
    EGOLINK_LOCATION_STATE_EMIT_INVALID_LOCATION_STATE,
    EGOLINK_LOCATION_STATE_EMIT_OVERFLOW,
} egolink_location_state_emit_result_t;

/*
 * Emits a NUL-terminated JSON envelope. output_length excludes the NUL.
 * No server_receive_time_ms is generated. On every failure, output_length is
 * zero and all bytes the function could have written are cleared.
 */
egolink_location_state_emit_result_t egolink_location_state_emit(
    const egolink_location_state_emit_input_t *input,
    char *output,
    size_t output_capacity,
    size_t *output_length);

const char *egolink_location_state_emit_result_name(
    egolink_location_state_emit_result_t result);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_STATE_EMITTER_H */
