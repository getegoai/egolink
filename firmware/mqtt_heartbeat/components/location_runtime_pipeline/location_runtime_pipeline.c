#include "location_runtime_pipeline.h"

#include <string.h>

#include "mbedtls/sha256.h"

typedef struct {
    char data[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    size_t length;
} owned_id_t;

typedef struct {
    uint64_t sequence_id;
    owned_id_t observation_id;
    uint64_t event_time_ms;
    egolink_location_event_time_source_t event_time_source;
    uint64_t event_time_ns;
} variable_identity_t;

typedef struct {
    bool initialized;
    bool local_progress_on_publish_failure;
    egolink_location_outbox_adapter_t *adapter;
    owned_id_t device_id;
    uint64_t boot_count;
    owned_id_t session_id;
    owned_id_t stream_id;
    egolink_location_runtime_clock_domain_t clock_domain;
    owned_id_t monotonic_clock_domain_id;

    egolink_location_engine_core_t engine;
    egolink_location_policy_core_t policy;
    egolink_location_engine_core_t staged_engine;
    egolink_location_policy_core_t staged_policy;
    egolink_location_engine_snapshot_t staged_snapshot;
    egolink_location_policy_decision_t staged_decision;

    bool last_identity_present;
    variable_identity_t last_identity;
    uint8_t last_fingerprint[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES];

    bool retry_required;
    variable_identity_t retry_identity;
    uint8_t retry_fingerprint[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES];
} pipeline_internal_t;

typedef struct {
    mbedtls_sha256_context context;
    bool ok;
} fingerprint_writer_t;

_Static_assert(sizeof(double) == sizeof(uint64_t),
               "pipeline fingerprint requires 64-bit double");
_Static_assert(EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES <=
                   EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES,
               "pipeline identity exceeds engine text ceiling");
_Static_assert(EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES <=
                   EGOLINK_LOCATION_STATE_OUTBOX_ID_MAX_BYTES,
               "pipeline identity exceeds emitter/outbox ID ceiling");
_Static_assert(EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT == 8U,
               "state-size proof requires eight native reasons");
_Static_assert(EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_BYTES == 128U,
               "state-size proof requires 128-byte reason ceiling");
_Static_assert(sizeof(pipeline_internal_t) <=
                   EGOLINK_LOCATION_RUNTIME_CONTEXT_BYTES,
               "pipeline opaque context is too small");
_Static_assert(EGOLINK_LOCATION_RUNTIME_STATE_JSON_PROVEN_MAX_BYTES <=
                   EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES,
               "proved native state ceiling exceeds pipeline scratch");
_Static_assert(EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES <=
                   EGOLINK_LOCATION_STATE_JSON_MAX_BYTES,
               "pipeline state scratch exceeds emitter input ceiling");
_Static_assert(
    EGOLINK_LOCATION_RUNTIME_STATE_JSON_MAX_BYTES +
            EGOLINK_LOCATION_RUNTIME_ENVELOPE_OVERHEAD_MAX_BYTES <=
        EGOLINK_LOCATION_RUNTIME_ENVELOPE_MAX_BYTES,
    "bounded state plus emitter overhead exceeds the outbox payload ceiling");
_Static_assert(EGOLINK_LOCATION_RUNTIME_ENVELOPE_MAX_BYTES ==
                   EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
               "pipeline/outbox payload ceilings drifted");
_Static_assert(EGOLINK_LOCATION_RUNTIME_ENVELOPE_MAX_BYTES <=
                   EGOLINK_LOCATION_STATE_ENVELOPE_MAX_BYTES,
               "pipeline envelope exceeds emitter output ceiling");

static pipeline_internal_t *pipeline_internal(
    egolink_location_runtime_pipeline_t *pipeline)
{
    return (pipeline_internal_t *)(void *)pipeline->opaque;
}

static void secure_clear(void *data, size_t length)
{
    volatile unsigned char *cursor = (volatile unsigned char *)data;
    for (size_t index = 0U; cursor != NULL && index < length; ++index) {
        cursor[index] = 0U;
    }
}

static void clear_scratch(egolink_location_runtime_scratch_t *scratch)
{
    if (scratch != NULL) {
        secure_clear(scratch, sizeof(*scratch));
    }
}

static void initialize_result(egolink_location_runtime_result_t *result)
{
    if (result == NULL) {
        return;
    }
    memset(result, 0, sizeof(*result));
    result->status = EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->engine_status = EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->policy_status = EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    result->serializer_status = EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->enqueue_status = EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT;
}

static bool safe_id_first(unsigned char value)
{
    return (value >= (unsigned char)'A' && value <= (unsigned char)'Z') ||
           (value >= (unsigned char)'a' && value <= (unsigned char)'z') ||
           (value >= (unsigned char)'0' && value <= (unsigned char)'9');
}

static bool safe_id_byte(unsigned char value)
{
    return safe_id_first(value) || value == (unsigned char)'.' ||
           value == (unsigned char)'_' || value == (unsigned char)':' ||
           value == (unsigned char)'@' || value == (unsigned char)'-';
}

static bool safe_runtime_text(egolink_location_runtime_text_t text)
{
    if (text.data == NULL || text.length == 0U ||
        text.length > EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES ||
        !safe_id_first((unsigned char)text.data[0])) {
        return false;
    }
    for (size_t index = 1U; index < text.length; ++index) {
        if (!safe_id_byte((unsigned char)text.data[index])) {
            return false;
        }
    }
    return true;
}

static bool safe_engine_text(egolink_location_engine_text_t text)
{
    const egolink_location_runtime_text_t converted = {
        .data = text.data,
        .length = text.length,
    };
    return safe_runtime_text(converted);
}

static bool absent_runtime_text(egolink_location_runtime_text_t text)
{
    return text.data == NULL && text.length == 0U;
}

static bool copy_runtime_id(
    owned_id_t *output, egolink_location_runtime_text_t input)
{
    if (output == NULL || !safe_runtime_text(input)) {
        return false;
    }
    memset(output, 0, sizeof(*output));
    memcpy(output->data, input.data, input.length);
    output->length = input.length;
    return true;
}

static bool owned_equals_runtime(
    const owned_id_t *owned, egolink_location_runtime_text_t input)
{
    return owned != NULL && input.data != NULL &&
           owned->length == input.length &&
           memcmp(owned->data, input.data, input.length) == 0;
}

static bool owned_equals_engine(
    const owned_id_t *owned, egolink_location_engine_text_t input)
{
    const egolink_location_runtime_text_t converted = {
        .data = input.data,
        .length = input.length,
    };
    return owned_equals_runtime(owned, converted);
}

static bool runtime_text_equals_engine(
    egolink_location_runtime_text_t runtime,
    egolink_location_engine_text_t engine)
{
    return runtime.data != NULL && engine.data != NULL &&
           runtime.length == engine.length &&
           memcmp(runtime.data, engine.data, runtime.length) == 0;
}

static bool engine_text_equal(
    egolink_location_engine_text_t left,
    egolink_location_engine_text_t right)
{
    return left.data != NULL && right.data != NULL &&
           left.length == right.length &&
           memcmp(left.data, right.data, left.length) == 0;
}

static egolink_location_state_text_t state_text(
    egolink_location_runtime_text_t text)
{
    const egolink_location_state_text_t result = {
        .data = text.data,
        .length = text.length,
    };
    return result;
}

static bool valid_engine_event(egolink_location_engine_event_type_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_EVENT_TICK &&
           value < EGOLINK_LOCATION_ENGINE_EVENT_COUNT;
}

static bool valid_engine_mobility(egolink_location_engine_mobility_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_MOBILITY_STABLE &&
           value < EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT;
}

static bool valid_engine_lte(egolink_location_engine_lte_state_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_LTE_OFFLINE &&
           value < EGOLINK_LOCATION_ENGINE_LTE_COUNT;
}

static bool valid_engine_battery(
    egolink_location_engine_battery_state_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_BATTERY_NORMAL &&
           value < EGOLINK_LOCATION_ENGINE_BATTERY_COUNT;
}

static bool valid_engine_source(egolink_location_engine_source_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_SOURCE_GNSS &&
           value < EGOLINK_LOCATION_ENGINE_SOURCE_COUNT;
}

static bool valid_source_status(
    egolink_location_engine_source_status_t value)
{
    return value >= EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED &&
           value < EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_COUNT;
}

static bool valid_derived_time_source(
    egolink_location_engine_time_source_t value)
{
    return value == EGOLINK_LOCATION_ENGINE_TIME_POLICY_RULE_V0 ||
           value == EGOLINK_LOCATION_ENGINE_TIME_POLICY_TIMER_V0 ||
           value == EGOLINK_LOCATION_ENGINE_TIME_POLICY_ACTION_V0;
}

static bool valid_publish_intent(
    egolink_location_runtime_publish_intent_t value)
{
    return value >= EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE &&
           value <= EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;
}

static bool valid_event_time_source(
    egolink_location_event_time_source_t value)
{
    return value >= EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS &&
           value <= EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS;
}

static bool adapter_device_matches(
    const egolink_location_outbox_adapter_t *adapter,
    egolink_location_runtime_text_t device_id)
{
    if (adapter == NULL || !adapter->initialized || adapter->outbox == NULL ||
        !safe_runtime_text(device_id)) {
        return false;
    }
    const size_t configured_length = strlen(adapter->device_id);
    return configured_length == device_id.length &&
           memcmp(adapter->device_id, device_id.data, device_id.length) == 0;
}

static bool trusted_lineage_clock_matches(
    const egolink_location_engine_lineage_t *lineage,
    const egolink_location_runtime_identity_t *identity)
{
    if (identity->event_time_source ==
        EGOLINK_LOCATION_TIME_GNSS_SOURCE_UTC_NS) {
        return lineage->gnss_source_utc_ns_present &&
               lineage->gnss_source_utc_ns == identity->event_time_ns &&
               !lineage->timestamp_utc_ns_present &&
               !lineage->timestamp_monotonic_ns_present &&
               !lineage->monotonic_clock_domain_id_present;
    }
    if (identity->event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS) {
        return !lineage->gnss_source_utc_ns_present &&
               lineage->timestamp_utc_ns_present &&
               lineage->timestamp_utc_ns == identity->event_time_ns &&
               !lineage->timestamp_monotonic_ns_present &&
               !lineage->monotonic_clock_domain_id_present;
    }
    return !lineage->gnss_source_utc_ns_present &&
           !lineage->timestamp_utc_ns_present &&
           lineage->timestamp_monotonic_ns_present &&
           lineage->timestamp_monotonic_ns == identity->event_time_ns &&
           lineage->monotonic_clock_domain_id_present &&
           safe_engine_text(lineage->monotonic_clock_domain_id) &&
           runtime_text_equals_engine(identity->monotonic_clock_domain_id,
                                      lineage->monotonic_clock_domain_id);
}

static bool rule_lineage_valid(
    const egolink_location_engine_lineage_t *lineage)
{
    if (!lineage->derived_time_source_present ||
        !valid_derived_time_source(lineage->derived_time_source) ||
        lineage->basis_count == 0U ||
        lineage->basis_count >
            EGOLINK_LOCATION_ENGINE_CORE_RULE_BASIS_MAX_COUNT ||
        lineage->gnss_source_utc_ns_present ||
        lineage->timestamp_utc_ns_present ||
        lineage->timestamp_monotonic_ns_present ||
        lineage->monotonic_clock_domain_id_present) {
        return false;
    }
    for (size_t index = 0U; index < lineage->basis_count; ++index) {
        if (!safe_engine_text(lineage->basis_observation_ids[index])) {
            return false;
        }
        for (size_t prior = 0U; prior < index; ++prior) {
            if (engine_text_equal(lineage->basis_observation_ids[index],
                                  lineage->basis_observation_ids[prior])) {
                return false;
            }
        }
    }
    return true;
}

static bool lineage_identity_valid(
    const pipeline_internal_t *internal,
    const egolink_location_runtime_input_t *input)
{
    const egolink_location_engine_lineage_t *lineage =
        &input->observation.lineage;
    if (!lineage->present) {
        return true;
    }
    if (!valid_source_status(lineage->source_status) ||
        !safe_engine_text(lineage->observation_id) ||
        !runtime_text_equals_engine(input->identity.observation_id,
                                   lineage->observation_id) ||
        !lineage->stream_id_present || !safe_engine_text(lineage->stream_id) ||
        !owned_equals_engine(&internal->stream_id, lineage->stream_id) ||
        !lineage->sequence_id_present ||
        lineage->sequence_id != input->identity.sequence_id ||
        !lineage->device_run_id_present ||
        !safe_engine_text(lineage->device_run_id) ||
        !owned_equals_engine(&internal->session_id, lineage->device_run_id) ||
        !lineage->boot_count_present ||
        lineage->boot_count != input->identity.boot_count ||
        (lineage->outer_evidence_source_status_present &&
         lineage->outer_evidence_source_status != lineage->source_status)) {
        return false;
    }
    if (lineage->source_status ==
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_RULE_DERIVED) {
        return rule_lineage_valid(lineage);
    }
    return !lineage->derived_time_source_present &&
           lineage->basis_count == 0U &&
           trusted_lineage_clock_matches(lineage, &input->identity);
}

static egolink_location_runtime_status_t validate_input(
    const pipeline_internal_t *internal,
    const egolink_location_runtime_input_t *input)
{
    if (internal == NULL || input == NULL ||
        !safe_runtime_text(input->identity.device_id) ||
        !safe_runtime_text(input->identity.session_id) ||
        !safe_runtime_text(input->identity.stream_id) ||
        !safe_runtime_text(input->identity.observation_id) ||
        !owned_equals_runtime(&internal->device_id,
                              input->identity.device_id) ||
        internal->boot_count != input->identity.boot_count ||
        !owned_equals_runtime(&internal->session_id,
                              input->identity.session_id) ||
        !owned_equals_runtime(&internal->stream_id,
                              input->identity.stream_id)) {
        return EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH;
    }
    if (input->identity.boot_count > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        input->identity.sequence_id > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        input->identity.event_time_ms > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        input->identity.event_time_ns > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        input->identity.event_time_ns / UINT64_C(1000000) !=
            input->identity.event_time_ms ||
        !valid_event_time_source(input->identity.event_time_source) ||
        !valid_publish_intent(input->publish_intent) ||
        !valid_engine_event(input->observation.type) ||
        input->observation.event_time_ms != input->identity.event_time_ms) {
        return EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY;
    }
    if (internal->clock_domain == EGOLINK_LOCATION_RUNTIME_CLOCK_UTC) {
        if (input->identity.event_time_source ==
                EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS ||
            !absent_runtime_text(
                input->identity.monotonic_clock_domain_id)) {
            return EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH;
        }
    } else if (input->identity.event_time_source !=
                   EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS ||
               !safe_runtime_text(
                   input->identity.monotonic_clock_domain_id) ||
               !owned_equals_runtime(
                   &internal->monotonic_clock_domain_id,
                   input->identity.monotonic_clock_domain_id)) {
        return EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH;
    }
    if ((input->observation.mobility_state_present &&
         !valid_engine_mobility(input->observation.mobility_state)) ||
        (input->observation.lte_state_present &&
         !valid_engine_lte(input->observation.lte_state)) ||
        (input->observation.battery_state_present &&
         !valid_engine_battery(input->observation.battery_state)) ||
        (input->observation.coarse_source_present &&
         !valid_engine_source(input->observation.coarse_source)) ||
        (input->observation.reference_id_present &&
         !safe_engine_text(input->observation.reference_id)) ||
        !lineage_identity_valid(internal, input)) {
        return EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY;
    }
    return EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH;
}

static bool fingerprint_update(
    fingerprint_writer_t *writer, const void *data, size_t length)
{
    if (!writer->ok) {
        return false;
    }
    if (length == 0U) {
        return true;
    }
    if (data == NULL ||
        mbedtls_sha256_update(
            &writer->context, (const unsigned char *)data, length) != 0) {
        writer->ok = false;
    }
    return writer->ok;
}

static bool fingerprint_u64(fingerprint_writer_t *writer, uint64_t value)
{
    unsigned char encoded[8];
    for (size_t index = 0U; index < sizeof(encoded); ++index) {
        const size_t shift = (sizeof(encoded) - index - 1U) * 8U;
        encoded[index] = (unsigned char)((value >> shift) & UINT64_C(0xff));
    }
    return fingerprint_update(writer, encoded, sizeof(encoded));
}

static bool fingerprint_bool(fingerprint_writer_t *writer, bool value)
{
    const unsigned char encoded = value ? 1U : 0U;
    return fingerprint_update(writer, &encoded, sizeof(encoded));
}

static bool fingerprint_runtime_text(
    fingerprint_writer_t *writer, egolink_location_runtime_text_t text)
{
    return fingerprint_u64(writer, (uint64_t)text.length) &&
           fingerprint_update(writer, text.data, text.length);
}

static bool fingerprint_engine_text(
    fingerprint_writer_t *writer, egolink_location_engine_text_t text)
{
    const egolink_location_runtime_text_t converted = {
        .data = text.data,
        .length = text.length,
    };
    return fingerprint_runtime_text(writer, converted);
}

static bool fingerprint_double(fingerprint_writer_t *writer, double value)
{
    uint64_t bits = 0U;
    memcpy(&bits, &value, sizeof(bits));
    return fingerprint_u64(writer, bits);
}

static bool fingerprint_optional_u64(
    fingerprint_writer_t *writer, bool present, uint64_t value)
{
    return fingerprint_bool(writer, present) &&
           (!present || fingerprint_u64(writer, value));
}

static bool fingerprint_optional_double(
    fingerprint_writer_t *writer, bool present, double value)
{
    return fingerprint_bool(writer, present) &&
           (!present || fingerprint_double(writer, value));
}

static bool fingerprint_optional_engine_text(
    fingerprint_writer_t *writer,
    bool present,
    egolink_location_engine_text_t text)
{
    return fingerprint_bool(writer, present) &&
           (!present || fingerprint_engine_text(writer, text));
}

static bool fingerprint_lineage(
    fingerprint_writer_t *writer,
    const egolink_location_engine_lineage_t *lineage)
{
    if (!fingerprint_bool(writer, lineage->present)) {
        return false;
    }
    if (!lineage->present) {
        return true;
    }
    if (!fingerprint_engine_text(writer, lineage->observation_id) ||
        !fingerprint_u64(writer, (uint64_t)lineage->source_status) ||
        !fingerprint_optional_engine_text(
            writer, lineage->stream_id_present, lineage->stream_id) ||
        !fingerprint_optional_u64(
            writer, lineage->sequence_id_present, lineage->sequence_id) ||
        !fingerprint_optional_engine_text(
            writer, lineage->device_run_id_present, lineage->device_run_id) ||
        !fingerprint_optional_u64(
            writer, lineage->boot_count_present, lineage->boot_count) ||
        !fingerprint_optional_u64(
            writer, lineage->gnss_source_utc_ns_present,
            lineage->gnss_source_utc_ns) ||
        !fingerprint_optional_u64(
            writer, lineage->timestamp_utc_ns_present,
            lineage->timestamp_utc_ns) ||
        !fingerprint_optional_u64(
            writer, lineage->timestamp_monotonic_ns_present,
            lineage->timestamp_monotonic_ns) ||
        !fingerprint_optional_engine_text(
            writer, lineage->monotonic_clock_domain_id_present,
            lineage->monotonic_clock_domain_id) ||
        !fingerprint_bool(writer, lineage->derived_time_source_present) ||
        (lineage->derived_time_source_present &&
         !fingerprint_u64(writer,
                          (uint64_t)lineage->derived_time_source)) ||
        !fingerprint_u64(writer, (uint64_t)lineage->basis_count)) {
        return false;
    }
    for (size_t index = 0U; index < lineage->basis_count; ++index) {
        if (!fingerprint_engine_text(
                writer, lineage->basis_observation_ids[index])) {
            return false;
        }
    }
    return fingerprint_bool(
               writer, lineage->outer_evidence_source_status_present) &&
           (!lineage->outer_evidence_source_status_present ||
            fingerprint_u64(
                writer,
                (uint64_t)lineage->outer_evidence_source_status));
}

static bool input_fingerprint(
    const egolink_location_runtime_input_t *input,
    uint8_t output[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES])
{
    static const char domain[] = "egolink.location_runtime_pipeline.input.v0.1";
    fingerprint_writer_t writer;
    mbedtls_sha256_init(&writer.context);
    writer.ok = mbedtls_sha256_starts(&writer.context, 0) == 0;
    const egolink_location_engine_observation_t *observation =
        &input->observation;
    bool ok =
        fingerprint_update(&writer, domain, sizeof(domain) - 1U) &&
        fingerprint_runtime_text(&writer, input->identity.device_id) &&
        fingerprint_u64(&writer, input->identity.boot_count) &&
        fingerprint_runtime_text(&writer, input->identity.session_id) &&
        fingerprint_runtime_text(&writer, input->identity.stream_id) &&
        fingerprint_u64(&writer, input->identity.sequence_id) &&
        fingerprint_runtime_text(&writer, input->identity.observation_id) &&
        fingerprint_u64(&writer, input->identity.event_time_ms) &&
        fingerprint_u64(&writer,
                        (uint64_t)input->identity.event_time_source) &&
        fingerprint_u64(&writer, input->identity.event_time_ns) &&
        fingerprint_runtime_text(
            &writer, input->identity.monotonic_clock_domain_id) &&
        fingerprint_u64(&writer, (uint64_t)input->publish_intent) &&
        fingerprint_u64(&writer, (uint64_t)observation->type) &&
        fingerprint_u64(&writer, observation->event_time_ms) &&
        fingerprint_lineage(&writer, &observation->lineage) &&
        fingerprint_bool(&writer, observation->mobility_state_present) &&
        (!observation->mobility_state_present ||
         fingerprint_u64(&writer,
                         (uint64_t)observation->mobility_state)) &&
        fingerprint_bool(&writer, observation->lte_state_present) &&
        (!observation->lte_state_present ||
         fingerprint_u64(&writer, (uint64_t)observation->lte_state)) &&
        fingerprint_bool(&writer, observation->battery_state_present) &&
        (!observation->battery_state_present ||
         fingerprint_u64(&writer,
                         (uint64_t)observation->battery_state)) &&
        fingerprint_optional_double(
            &writer, observation->battery_percent_present,
            observation->battery_percent) &&
        fingerprint_bool(&writer, observation->sos_active_present) &&
        (!observation->sos_active_present ||
         fingerprint_bool(&writer, observation->sos_active)) &&
        fingerprint_optional_double(
            &writer, observation->latitude_deg_present,
            observation->latitude_deg) &&
        fingerprint_optional_double(
            &writer, observation->longitude_deg_present,
            observation->longitude_deg) &&
        fingerprint_optional_double(
            &writer, observation->accuracy_m_present,
            observation->accuracy_m) &&
        fingerprint_optional_double(
            &writer, observation->hdop_present, observation->hdop) &&
        fingerprint_optional_double(
            &writer, observation->uncertainty_m_present,
            observation->uncertainty_m) &&
        fingerprint_bool(&writer, observation->coarse_source_present) &&
        (!observation->coarse_source_present ||
         fingerprint_u64(&writer,
                         (uint64_t)observation->coarse_source)) &&
        fingerprint_optional_engine_text(
            &writer, observation->reference_id_present,
            observation->reference_id);
    if (ok) {
        ok = mbedtls_sha256_finish(&writer.context, output) == 0;
    }
    mbedtls_sha256_free(&writer.context);
    return ok && writer.ok;
}

static bool variable_identity_from_input(
    variable_identity_t *output,
    const egolink_location_runtime_input_t *input)
{
    variable_identity_t staged = {0};
    staged.sequence_id = input->identity.sequence_id;
    staged.event_time_ms = input->identity.event_time_ms;
    staged.event_time_source = input->identity.event_time_source;
    staged.event_time_ns = input->identity.event_time_ns;
    if (!copy_runtime_id(&staged.observation_id,
                         input->identity.observation_id)) {
        return false;
    }
    *output = staged;
    return true;
}

static bool variable_identity_exact(
    const variable_identity_t *stored,
    const egolink_location_runtime_input_t *input)
{
    return stored->sequence_id == input->identity.sequence_id &&
           owned_equals_runtime(&stored->observation_id,
                                input->identity.observation_id) &&
           stored->event_time_ms == input->identity.event_time_ms &&
           stored->event_time_source == input->identity.event_time_source &&
           stored->event_time_ns == input->identity.event_time_ns;
}

static bool same_fingerprint(
    const uint8_t left[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES],
    const uint8_t right[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES])
{
    unsigned int difference = 0U;
    for (size_t index = 0U;
         index < EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES; ++index) {
        difference |= (unsigned int)(left[index] ^ right[index]);
    }
    return difference == 0U;
}

static bool map_mobility(
    egolink_location_engine_mobility_t input,
    egolink_location_policy_mobility_t *output)
{
    switch (input) {
    case EGOLINK_LOCATION_ENGINE_MOBILITY_STABLE:
        *output = EGOLINK_LOCATION_POLICY_MOBILITY_STABLE;
        return true;
    case EGOLINK_LOCATION_ENGINE_MOBILITY_MOVING:
        *output = EGOLINK_LOCATION_POLICY_MOBILITY_MOVING;
        return true;
    case EGOLINK_LOCATION_ENGINE_MOBILITY_UNKNOWN:
        *output = EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
        return true;
    case EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT:
    default:
        return false;
    }
}

static bool map_gnss(
    egolink_location_engine_gnss_state_t input,
    egolink_location_policy_gnss_state_t *output)
{
    switch (input) {
    case EGOLINK_LOCATION_ENGINE_GNSS_IDLE:
        *output = EGOLINK_LOCATION_POLICY_GNSS_IDLE;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_ACQUIRING:
        *output = EGOLINK_LOCATION_POLICY_GNSS_ACQUIRING;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_FIX:
        *output = EGOLINK_LOCATION_POLICY_GNSS_FIX;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX:
        *output = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED:
        *output = EGOLINK_LOCATION_POLICY_GNSS_FIX_REJECTED;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_ERROR:
        *output = EGOLINK_LOCATION_POLICY_GNSS_ERROR;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_UNAVAILABLE:
        *output = EGOLINK_LOCATION_POLICY_GNSS_UNAVAILABLE;
        return true;
    case EGOLINK_LOCATION_ENGINE_GNSS_COUNT:
    default:
        return false;
    }
}

static bool map_battery(
    egolink_location_engine_battery_state_t input,
    egolink_location_policy_battery_state_t *output)
{
    switch (input) {
    case EGOLINK_LOCATION_ENGINE_BATTERY_NORMAL:
        *output = EGOLINK_LOCATION_POLICY_BATTERY_NORMAL;
        return true;
    case EGOLINK_LOCATION_ENGINE_BATTERY_LOW:
        *output = EGOLINK_LOCATION_POLICY_BATTERY_LOW;
        return true;
    case EGOLINK_LOCATION_ENGINE_BATTERY_CRITICAL:
        *output = EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL;
        return true;
    case EGOLINK_LOCATION_ENGINE_BATTERY_CHARGING:
        *output = EGOLINK_LOCATION_POLICY_BATTERY_CHARGING;
        return true;
    case EGOLINK_LOCATION_ENGINE_BATTERY_UNKNOWN:
        *output = EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN;
        return true;
    case EGOLINK_LOCATION_ENGINE_BATTERY_COUNT:
    default:
        return false;
    }
}

static bool map_belief(
    egolink_location_engine_belief_t input,
    egolink_location_policy_belief_t *output)
{
    switch (input) {
    case EGOLINK_LOCATION_ENGINE_BELIEF_FINE:
        *output = EGOLINK_LOCATION_POLICY_BELIEF_FINE;
        return true;
    case EGOLINK_LOCATION_ENGINE_BELIEF_COARSE:
        *output = EGOLINK_LOCATION_POLICY_BELIEF_COARSE;
        return true;
    case EGOLINK_LOCATION_ENGINE_BELIEF_PREDICTED:
        *output = EGOLINK_LOCATION_POLICY_BELIEF_PREDICTED;
        return true;
    case EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN:
        *output = EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN;
        return true;
    case EGOLINK_LOCATION_ENGINE_BELIEF_COUNT:
    default:
        return false;
    }
}

static bool policy_snapshot_from_engine(
    const egolink_location_engine_snapshot_t *input,
    egolink_location_policy_snapshot_t *output)
{
    egolink_location_policy_snapshot_t staged = {0};
    staged.event_time_ms = input->event_time_ms;
    if (!map_mobility(input->mobility_state, &staged.mobility_state) ||
        !map_gnss(input->gnss_state, &staged.gnss_state) ||
        !map_battery(input->battery_state, &staged.battery_state) ||
        !map_belief(input->location_belief, &staged.location_belief)) {
        return false;
    }
    staged.battery_percent_available = input->battery_percent_present;
    staged.battery_percent = input->battery_percent;
    staged.sos_active = input->sos_active;
    staged.location_uncertainty_available =
        input->location_uncertainty_m_present;
    staged.location_uncertainty_m = input->location_uncertainty_m;
    staged.last_trusted_time_available = input->last_trusted_time_present;
    staged.last_trusted_time_ms = input->last_trusted_time_ms;
    *output = staged;
    return true;
}

static bool policy_event_from_engine(
    const egolink_location_runtime_input_t *input,
    egolink_location_policy_event_t *output)
{
    egolink_location_policy_event_type_t mapped;
    switch (input->observation.type) {
    case EGOLINK_LOCATION_ENGINE_EVENT_TICK:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_TICK;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE:
        return false;
    case EGOLINK_LOCATION_ENGINE_EVENT_MOBILITY:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_MOBILITY;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STARTED:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_GNSS_STARTED;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STOPPED:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_GNSS_STOPPED;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_COARSE_LOCATION;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_LTE_STATE:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_LTE_STATE;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_CELL_OBSERVATION:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_CELL_OBSERVATION;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_BATTERY:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_BATTERY;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_SOS:
        mapped = EGOLINK_LOCATION_POLICY_EVENT_SOS;
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_COUNT:
    default:
        return false;
    }
    *output = (egolink_location_policy_event_t){
        .type = mapped,
        .event_time_ms = input->identity.event_time_ms,
        .attributable_lineage = input->observation.lineage.present,
    };
    return true;
}

static bool engine_policy_mode(
    egolink_location_policy_mode_t input,
    egolink_location_engine_policy_state_t *output)
{
    switch (input) {
    case EGOLINK_LOCATION_POLICY_STABLE:
        *output = EGOLINK_LOCATION_ENGINE_POLICY_STABLE;
        return true;
    case EGOLINK_LOCATION_POLICY_MOVING:
        *output = EGOLINK_LOCATION_ENGINE_POLICY_MOVING;
        return true;
    case EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN:
        *output = EGOLINK_LOCATION_ENGINE_POLICY_LOCATION_UNCERTAIN;
        return true;
    case EGOLINK_LOCATION_POLICY_SOS:
        *output = EGOLINK_LOCATION_ENGINE_POLICY_SOS;
        return true;
    case EGOLINK_LOCATION_POLICY_LOW_BATTERY:
        *output = EGOLINK_LOCATION_ENGINE_POLICY_LOW_BATTERY;
        return true;
    default:
        return false;
    }
}

static bool trusted_clock_matches_identity(
    const egolink_location_engine_snapshot_t *snapshot,
    const egolink_location_runtime_identity_t *identity)
{
    if (!snapshot->last_trusted_location_present ||
        !snapshot->last_trusted_time_present ||
        snapshot->last_trusted_time_ms != identity->event_time_ms) {
        return false;
    }
    const egolink_location_engine_evidence_ref_t *evidence =
        &snapshot->last_trusted_location.evidence_ref;
    egolink_location_engine_time_source_t expected;
    switch (identity->event_time_source) {
    case EGOLINK_LOCATION_TIME_GNSS_SOURCE_UTC_NS:
        expected = EGOLINK_LOCATION_ENGINE_TIME_GNSS_SOURCE_UTC_NS;
        break;
    case EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS:
        expected = EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_UTC_NS;
        break;
    case EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS:
        expected = EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS;
        break;
    default:
        return false;
    }
    return evidence->event_time_source == expected &&
           evidence->capture_time_ns == identity->event_time_ns;
}

static bool trusted_update_accepted(
    const egolink_location_runtime_input_t *input,
    const egolink_location_engine_snapshot_t *snapshot)
{
    if (input->observation.type ==
        EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX) {
        return snapshot->gnss_state == EGOLINK_LOCATION_ENGINE_GNSS_FIX &&
               snapshot->location_belief ==
                   EGOLINK_LOCATION_ENGINE_BELIEF_FINE &&
               trusted_clock_matches_identity(snapshot, &input->identity);
    }
    if (input->observation.type ==
        EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION) {
        return snapshot->location_belief ==
                   EGOLINK_LOCATION_ENGINE_BELIEF_COARSE &&
               trusted_clock_matches_identity(snapshot, &input->identity);
    }
    return false;
}

static uint32_t publish_reasons(
    const pipeline_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    bool policy_evaluated)
{
    uint32_t reasons = EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_NONE;
    if (policy_evaluated && internal->staged_decision.upload_location_now) {
        reasons |= EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_POLICY_ACTION;
    }
    if (trusted_update_accepted(input, &internal->staged_snapshot)) {
        reasons |= EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_TRUSTED_UPDATE;
    }
    if (input->observation.type == EGOLINK_LOCATION_ENGINE_EVENT_SOS) {
        reasons |= EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_SOS_EVENT;
    }
    if (input->publish_intent ==
        EGOLINK_LOCATION_RUNTIME_PUBLISH_INITIAL_CURRENT) {
        reasons |= EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_EXPLICIT_INITIAL;
    } else if (input->publish_intent ==
               EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT) {
        reasons |= EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_EXPLICIT_CURRENT;
    }
    return reasons;
}

static void clear_staging(pipeline_internal_t *internal)
{
    secure_clear(&internal->staged_engine, sizeof(internal->staged_engine));
    secure_clear(&internal->staged_policy, sizeof(internal->staged_policy));
    secure_clear(&internal->staged_snapshot, sizeof(internal->staged_snapshot));
    secure_clear(&internal->staged_decision, sizeof(internal->staged_decision));
}

static void latch_retry(
    pipeline_internal_t *internal,
    const variable_identity_t *identity,
    const uint8_t fingerprint[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES])
{
    internal->retry_required = true;
    internal->retry_identity = *identity;
    memcpy(internal->retry_fingerprint, fingerprint,
           sizeof(internal->retry_fingerprint));
}

static void clear_retry(pipeline_internal_t *internal)
{
    internal->retry_required = false;
    secure_clear(&internal->retry_identity, sizeof(internal->retry_identity));
    secure_clear(internal->retry_fingerprint,
                 sizeof(internal->retry_fingerprint));
}

static void commit_identity(
    pipeline_internal_t *internal,
    const variable_identity_t *identity,
    const uint8_t fingerprint[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES])
{
    internal->last_identity_present = true;
    internal->last_identity = *identity;
    memcpy(internal->last_fingerprint, fingerprint,
           sizeof(internal->last_fingerprint));
}

egolink_location_runtime_status_t egolink_location_runtime_pipeline_init(
    egolink_location_runtime_pipeline_t *pipeline,
    egolink_location_outbox_adapter_t *adapter,
    const egolink_location_runtime_owner_t *owner)
{
    if (pipeline == NULL || adapter == NULL || owner == NULL) {
        return EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    secure_clear(pipeline, sizeof(*pipeline));
    if (!safe_runtime_text(owner->device_id) ||
        !safe_runtime_text(owner->session_id) ||
        !safe_runtime_text(owner->stream_id) ||
        owner->boot_count > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        (owner->clock_domain != EGOLINK_LOCATION_RUNTIME_CLOCK_UTC &&
         owner->clock_domain !=
             EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC) ||
        (owner->clock_domain == EGOLINK_LOCATION_RUNTIME_CLOCK_UTC &&
         !absent_runtime_text(owner->monotonic_clock_domain_id)) ||
        (owner->clock_domain ==
             EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC &&
         !safe_runtime_text(owner->monotonic_clock_domain_id)) ||
        !adapter_device_matches(adapter, owner->device_id)) {
        return EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH;
    }

    pipeline_internal_t *internal = pipeline_internal(pipeline);
    if (!copy_runtime_id(&internal->device_id, owner->device_id) ||
        !copy_runtime_id(&internal->session_id, owner->session_id) ||
        !copy_runtime_id(&internal->stream_id, owner->stream_id) ||
        (owner->clock_domain ==
             EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC &&
         !copy_runtime_id(&internal->monotonic_clock_domain_id,
                          owner->monotonic_clock_domain_id))) {
        secure_clear(pipeline, sizeof(*pipeline));
        return EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY;
    }
    internal->local_progress_on_publish_failure = owner->local_progress_on_publish_failure;
    internal->adapter = adapter;
    internal->boot_count = owner->boot_count;
    internal->clock_domain = owner->clock_domain;

    egolink_location_engine_config_t engine_config;
    egolink_location_policy_config_t policy_config;
    egolink_location_engine_default_config(&engine_config);
    egolink_location_policy_default_config(&policy_config);
    if (strcmp(engine_config.profile_id, policy_config.config_id) != 0 ||
        strcmp(engine_config.profile_hash, policy_config.config_hash) != 0 ||
        egolink_location_engine_init(&internal->engine, &engine_config) !=
            EGOLINK_LOCATION_ENGINE_OK ||
        egolink_location_policy_init(&internal->policy, &policy_config) !=
            EGOLINK_LOCATION_POLICY_OK) {
        secure_clear(pipeline, sizeof(*pipeline));
        return EGOLINK_LOCATION_RUNTIME_INTERNAL_INVARIANT_FAILED;
    }
    internal->initialized = true;
    return EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH;
}

egolink_location_runtime_status_t egolink_location_runtime_pipeline_process(
    egolink_location_runtime_pipeline_t *pipeline,
    const egolink_location_runtime_input_t *input,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_runtime_result_t *result)
{
    initialize_result(result);
    clear_scratch(scratch);
    if (pipeline == NULL || input == NULL || scratch == NULL || result == NULL) {
        return EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    pipeline_internal_t *internal = pipeline_internal(pipeline);
    if (!internal->initialized || internal->adapter == NULL) {
        result->status = EGOLINK_LOCATION_RUNTIME_NOT_INITIALIZED;
        return result->status;
    }

    egolink_location_runtime_status_t status = validate_input(internal, input);
    if (status != EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH) {
        result->status = internal->retry_required
                             ? EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED
                             : status;
        result->retry_latched = internal->retry_required;
        return result->status;
    }
    if (input->publish_intent ==
            EGOLINK_LOCATION_RUNTIME_PUBLISH_INITIAL_CURRENT &&
        internal->last_identity_present) {
        result->status = internal->retry_required
                             ? EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED
                             : EGOLINK_LOCATION_RUNTIME_INVALID_PUBLISH_INTENT;
        result->retry_latched = internal->retry_required;
        return result->status;
    }

    /*
     * Materialize the already-validated commit identity before either reducer
     * or any durable enqueue. The post-enqueue commit is then an infallible
     * bounded assignment; it never reparses caller memory after durability.
     */
    variable_identity_t candidate_identity = {0};
    if (!variable_identity_from_input(&candidate_identity, input)) {
        result->status = internal->retry_required
                             ? EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED
                             : EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY;
        result->retry_latched = internal->retry_required;
        return result->status;
    }

    uint8_t fingerprint[EGOLINK_LOCATION_RUNTIME_FINGERPRINT_BYTES];
    memset(fingerprint, 0, sizeof(fingerprint));
    if (!input_fingerprint(input, fingerprint)) {
        result->status = internal->retry_required
                             ? EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED
                             : EGOLINK_LOCATION_RUNTIME_FINGERPRINT_FAILED;
        result->retry_latched = internal->retry_required;
        return result->status;
    }
    if (internal->retry_required &&
        (!variable_identity_exact(&internal->retry_identity, input) ||
         !same_fingerprint(internal->retry_fingerprint, fingerprint))) {
        secure_clear(fingerprint, sizeof(fingerprint));
        result->status = EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED;
        result->retry_latched = true;
        return result->status;
    }

    if (internal->last_identity_present) {
        if (input->identity.sequence_id ==
            internal->last_identity.sequence_id) {
            const bool exact_identity =
                variable_identity_exact(&internal->last_identity, input);
            const bool exact_content =
                same_fingerprint(internal->last_fingerprint, fingerprint);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = exact_identity && exact_content
                                 ? EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT
                                 : EGOLINK_LOCATION_RUNTIME_IDENTITY_CONFLICT;
            return result->status;
        }
        if (input->identity.sequence_id <
            internal->last_identity.sequence_id) {
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_SEQUENCE_REGRESSION;
            return result->status;
        }
        if (owned_equals_runtime(&internal->last_identity.observation_id,
                                 input->identity.observation_id)) {
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_IDENTITY_CONFLICT;
            return result->status;
        }
        if (input->identity.event_time_ns <
            internal->last_identity.event_time_ns) {
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_TIME_REGRESSION;
            return result->status;
        }
    }

    internal->staged_engine = internal->engine;
    internal->staged_policy = internal->policy;
    memset(&internal->staged_snapshot, 0,
           sizeof(internal->staged_snapshot));
    memset(&internal->staged_decision, 0,
           sizeof(internal->staged_decision));
    result->engine_status = egolink_location_engine_process(
        &internal->staged_engine, &input->observation,
        &internal->staged_snapshot);
    if (result->engine_status != EGOLINK_LOCATION_ENGINE_OK) {
        clear_staging(internal);
        secure_clear(fingerprint, sizeof(fingerprint));
        result->status = EGOLINK_LOCATION_RUNTIME_ENGINE_FAILED;
        return result->status;
    }

    bool policy_evaluated = false;
    if (input->observation.type !=
        EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE) {
        egolink_location_policy_snapshot_t policy_snapshot;
        egolink_location_policy_event_t policy_event;
        memset(&policy_snapshot, 0, sizeof(policy_snapshot));
        memset(&policy_event, 0, sizeof(policy_event));
        if (!policy_snapshot_from_engine(&internal->staged_snapshot,
                                         &policy_snapshot) ||
            !policy_event_from_engine(input, &policy_event)) {
            clear_staging(internal);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status =
                EGOLINK_LOCATION_RUNTIME_POLICY_MAPPING_FAILED;
            return result->status;
        }
        result->policy_status = egolink_location_policy_evaluate(
            &internal->staged_policy, &policy_snapshot, &policy_event,
            &internal->staged_decision);
        if (result->policy_status != EGOLINK_LOCATION_POLICY_OK) {
            clear_staging(internal);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_POLICY_FAILED;
            return result->status;
        }
        egolink_location_engine_policy_state_t engine_mode;
        if (!engine_policy_mode(internal->staged_decision.policy_mode,
                                &engine_mode) ||
            egolink_location_engine_set_policy_context(
                &internal->staged_engine, engine_mode) !=
                EGOLINK_LOCATION_ENGINE_OK) {
            clear_staging(internal);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status =
                EGOLINK_LOCATION_RUNTIME_POLICY_MAPPING_FAILED;
            return result->status;
        }
        result->engine_status = egolink_location_engine_snapshot(
            &internal->staged_engine, true, input->identity.event_time_ms,
            &internal->staged_snapshot);
        if (result->engine_status != EGOLINK_LOCATION_ENGINE_OK) {
            clear_staging(internal);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_ENGINE_FAILED;
            return result->status;
        }
        policy_evaluated = true;
    } else {
        result->policy_status = EGOLINK_LOCATION_POLICY_OK;
    }

    const uint32_t reasons = publish_reasons(internal, input, policy_evaluated);
    const bool publish =
        reasons != EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_NONE;
    if (internal->retry_required && !publish) {
        clear_staging(internal);
        secure_clear(fingerprint, sizeof(fingerprint));
        result->status = EGOLINK_LOCATION_RUNTIME_INTERNAL_INVARIANT_FAILED;
        result->retry_latched = true;
        return result->status;
    }

    if (publish) {
        size_t state_length = 0U;
        result->serializer_status =
            egolink_location_engine_serialize_snapshot(
                &internal->staged_snapshot, scratch->state_json,
                sizeof(scratch->state_json), &state_length);
        if (result->serializer_status != EGOLINK_LOCATION_ENGINE_OK) {
            if (internal->local_progress_on_publish_failure) {
                result->persistence_degraded = true;
                goto commit_local;
            }
            latch_retry(internal, &candidate_identity, fingerprint);
            clear_staging(internal);
            clear_scratch(scratch);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED;
            result->publish_required = true;
            result->publish_reasons = reasons;
            result->retry_latched = true;
            return result->status;
        }

        const egolink_location_state_text_t policy_contract = {
            .data = EGOLINK_LOCATION_POLICY_CONFIG_CONTRACT_VERSION,
            .length = sizeof(EGOLINK_LOCATION_POLICY_CONFIG_CONTRACT_VERSION) -
                      1U,
        };
        const egolink_location_state_text_t policy_semantic = {
            .data = EGOLINK_LOCATION_POLICY_SEMANTIC_VERSION,
            .length = sizeof(EGOLINK_LOCATION_POLICY_SEMANTIC_VERSION) - 1U,
        };
        const egolink_location_state_text_t policy_id = {
            .data = EGOLINK_LOCATION_POLICY_CONFIG_ID,
            .length = sizeof(EGOLINK_LOCATION_POLICY_CONFIG_ID) - 1U,
        };
        const egolink_location_state_text_t policy_hash = {
            .data = EGOLINK_LOCATION_POLICY_CONFIG_HASH,
            .length = sizeof(EGOLINK_LOCATION_POLICY_CONFIG_HASH) - 1U,
        };
        const egolink_location_state_emit_input_t emit = {
            .device_id = state_text(input->identity.device_id),
            .boot_count = input->identity.boot_count,
            .session_id = state_text(input->identity.session_id),
            .event_time_ms = input->identity.event_time_ms,
            .event_time_source = input->identity.event_time_source,
            .event_time_ns = input->identity.event_time_ns,
            .monotonic_clock_domain_id =
                state_text(input->identity.monotonic_clock_domain_id),
            .sequence_id = input->identity.sequence_id,
            .observation_id = state_text(input->identity.observation_id),
            .policy_identity = {
                .contract_version = policy_contract,
                .semantic_validation = policy_semantic,
                .config_id = policy_id,
                .config_hash = policy_hash,
            },
            .location_state_json = {
                .data = scratch->state_json,
                .length = state_length,
            },
        };
        const egolink_location_outbox_urgency_t urgency =
            internal->staged_snapshot.sos_active
                ? EGOLINK_LOCATION_OUTBOX_SOS_ESCALATED
                : EGOLINK_LOCATION_OUTBOX_NORMAL;
        result->enqueue_status = egolink_location_outbox_emit_and_enqueue(
            internal->adapter, &emit, urgency, outbox_now_ms,
            scratch->envelope, sizeof(scratch->envelope),
            &result->enqueue_result);
        clear_scratch(scratch);
        if (result->enqueue_status != EGOLINK_LOCATION_OUTBOX_ENQUEUE_OK &&
            result->enqueue_status !=
                EGOLINK_LOCATION_OUTBOX_ENQUEUE_DUPLICATE) {
            if (internal->local_progress_on_publish_failure) {
                result->persistence_degraded = true;
                goto commit_local;
            }
            latch_retry(internal, &candidate_identity, fingerprint);
            clear_staging(internal);
            secure_clear(fingerprint, sizeof(fingerprint));
            result->status = EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED;
            result->publish_required = true;
            result->publish_reasons = reasons;
            result->retry_latched = true;
            return result->status;
        }
    } else {
        result->serializer_status = EGOLINK_LOCATION_ENGINE_OK;
    }

commit_local:
    result->local_committed = true;
    result->gnss_state = internal->staged_snapshot.gnss_state;
    result->location_belief = internal->staged_snapshot.location_belief;
    const egolink_location_engine_snapshot_t *snapshot = &internal->staged_snapshot;
    result->quality = (egolink_location_runtime_quality_t){
        .trusted_present = snapshot->last_trusted_time_present,
        .trusted_time_ms = snapshot->last_trusted_time_ms,
        .trusted_sequence = snapshot->last_trusted_location_present
            ? snapshot->last_trusted_location.evidence_ref.sequence_id : 0U,
        .source = snapshot->location_source,
        .accuracy_present = snapshot->location_accuracy_m_present,
        .accuracy_m = snapshot->location_accuracy_m,
        .uncertainty_present = snapshot->location_uncertainty_m_present,
        .uncertainty_m = snapshot->location_uncertainty_m,
        .uncertainty_basis = snapshot->location_uncertainty_basis,
    };
    commit_identity(internal, &candidate_identity, fingerprint);
    internal->engine = internal->staged_engine;
    internal->policy = internal->staged_policy;
    clear_retry(internal);
    result->policy_evaluated = policy_evaluated;
    result->publish_required = publish;
    result->published = publish && !result->persistence_degraded;
    result->publish_reasons = reasons;
    if (policy_evaluated) {
        result->policy_decision = internal->staged_decision;
    }
    result->retry_latched = false;
    result->status = result->persistence_degraded
        ? EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED
        : publish ? EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED
                             : EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH;
    clear_staging(internal);
    clear_scratch(scratch);
    secure_clear(fingerprint, sizeof(fingerprint));
    return result->status;
}

const char *egolink_location_runtime_status_name(
    egolink_location_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED:
        return "local_committed_persistence_failed";
    case EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH:
        return "ok_no_publish";
    case EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED:
        return "ok_published";
    case EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT:
        return "duplicate_input";
    case EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_RUNTIME_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_LOCATION_RUNTIME_OWNER_MISMATCH:
        return "owner_mismatch";
    case EGOLINK_LOCATION_RUNTIME_INVALID_IDENTITY:
        return "invalid_identity";
    case EGOLINK_LOCATION_RUNTIME_IDENTITY_CONFLICT:
        return "identity_conflict";
    case EGOLINK_LOCATION_RUNTIME_SEQUENCE_REGRESSION:
        return "sequence_regression";
    case EGOLINK_LOCATION_RUNTIME_TIME_REGRESSION:
        return "time_regression";
    case EGOLINK_LOCATION_RUNTIME_INVALID_PUBLISH_INTENT:
        return "invalid_publish_intent";
    case EGOLINK_LOCATION_RUNTIME_FINGERPRINT_FAILED:
        return "fingerprint_failed";
    case EGOLINK_LOCATION_RUNTIME_ENGINE_FAILED:
        return "engine_failed";
    case EGOLINK_LOCATION_RUNTIME_POLICY_MAPPING_FAILED:
        return "policy_mapping_failed";
    case EGOLINK_LOCATION_RUNTIME_POLICY_FAILED:
        return "policy_failed";
    case EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED:
        return "retry_required";
    case EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED:
        return "blocked_retry_required";
    case EGOLINK_LOCATION_RUNTIME_INTERNAL_INVARIANT_FAILED:
        return "internal_invariant_failed";
    default:
        return "unknown";
    }
}
