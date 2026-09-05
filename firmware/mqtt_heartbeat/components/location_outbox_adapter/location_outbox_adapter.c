#include "location_outbox_adapter.h"

#include <string.h>

#include "cJSON.h"
#include "mbedtls/sha256.h"

static size_t bounded_clear_length(size_t capacity)
{
    const size_t maximum = EGOLINK_LOCATION_STATE_ENVELOPE_MAX_BYTES + 1U;
    return capacity < maximum ? capacity : maximum;
}

static void clear_scratch(char *scratch, size_t capacity)
{
    volatile unsigned char *cursor = (volatile unsigned char *)scratch;
    const size_t length = bounded_clear_length(capacity);
    for (size_t index = 0U; cursor != NULL && index < length; ++index) {
        cursor[index] = 0U;
    }
}

static bool copy_text(
    char *destination,
    size_t destination_capacity,
    egolink_location_state_text_t source)
{
    if (destination == NULL || destination_capacity == 0U ||
        source.data == NULL || source.length == 0U ||
        source.length >= destination_capacity) {
        return false;
    }
    (void)memset(destination, 0, destination_capacity);
    (void)memcpy(destination, source.data, source.length);
    return true;
}

static bool exact_sha256(
    const void *data,
    size_t length,
    uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES])
{
    return data != NULL && length > 0U &&
           mbedtls_sha256(
               (const unsigned char *)data, length, digest, 0) == 0;
}

static void lowercase_hex(
    const uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES],
    char output[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY])
{
    static const char digits[] = "0123456789abcdef";
    for (size_t index = 0U; index < EGOLINK_OUTBOX_SHA256_BYTES; ++index) {
        output[index * 2U] = digits[digest[index] >> 4U];
        output[index * 2U + 1U] = digits[digest[index] & UINT8_C(0x0f)];
    }
    output[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U] = '\0';
}

static void prefixed_hash(
    const char *prefix,
    const char hash[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY],
    char output[EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY])
{
    const size_t prefix_length = strlen(prefix);
    (void)memset(output, 0, EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY);
    (void)memcpy(output, prefix, prefix_length);
    (void)memcpy(
        output + prefix_length,
        hash,
        EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U);
}

static bool enqueue_record_matches(
    const egolink_outbox_record_view_t *record,
    const char *event_id,
    const char *payload_sha256,
    egolink_outbox_priority_t priority,
    egolink_outbox_source_time_kind_t source_time_kind,
    const char *session_id,
    const egolink_location_state_emit_input_t *input,
    size_t payload_length)
{
    return strcmp(record->event_id, event_id) == 0 &&
           strcmp(record->event_type, EGOLINK_LOCATION_OUTBOX_EVENT_TYPE) == 0 &&
           strcmp(record->payload_sha256, payload_sha256) == 0 &&
           record->priority == priority &&
           record->source_time_kind == source_time_kind &&
           record->source_event_time_ms == input->event_time_ms &&
           record->boot_count == input->boot_count &&
           strcmp(record->session_id, session_id) == 0 &&
           record->source_sequence == input->sequence_id &&
           record->payload_length == payload_length;
}

static bool adapter_device_matches(
    const egolink_location_outbox_adapter_t *adapter,
    egolink_location_state_text_t device_id)
{
    if (adapter == NULL || !adapter->initialized || adapter->outbox == NULL ||
        device_id.data == NULL || device_id.length == 0U ||
        device_id.length >= EGOLINK_OUTBOX_ID_CAPACITY) {
        return false;
    }
    const size_t configured_length = strlen(adapter->device_id);
    return configured_length == device_id.length &&
           memcmp(adapter->device_id, device_id.data, device_id.length) == 0;
}

egolink_location_outbox_enqueue_status_t
egolink_location_outbox_emit_and_enqueue(
    egolink_location_outbox_adapter_t *adapter,
    const egolink_location_state_emit_input_t *input,
    egolink_location_outbox_urgency_t urgency,
    uint64_t now_ms,
    char *scratch,
    size_t scratch_capacity,
    egolink_location_outbox_enqueue_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->emit_status = EGOLINK_LOCATION_STATE_EMIT_INVALID_ARGUMENT;
        result->outbox_status = EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    if (adapter == NULL || input == NULL || scratch == NULL ||
        scratch_capacity == 0U || result == NULL ||
        (urgency != EGOLINK_LOCATION_OUTBOX_NORMAL &&
         urgency != EGOLINK_LOCATION_OUTBOX_SOS_ESCALATED)) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT;
    }
    if (!adapter->initialized || adapter->outbox == NULL) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_NOT_INITIALIZED;
    }
    if (!adapter_device_matches(adapter, input->device_id)) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_DEVICE_MISMATCH;
    }

    size_t payload_length = 0U;
    result->emit_status = egolink_location_state_emit(
        input, scratch, scratch_capacity, &payload_length);
    if (result->emit_status != EGOLINK_LOCATION_STATE_EMIT_OK) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_EMIT_FAILED;
    }
    if (payload_length == 0U ||
        payload_length > EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_PAYLOAD_TOO_LARGE;
    }

    uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES];
    char payload_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    char event_id[EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY];
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    (void)memset(digest, 0, sizeof(digest));
    (void)memset(payload_sha256, 0, sizeof(payload_sha256));
    (void)memset(event_id, 0, sizeof(event_id));
    (void)memset(session_id, 0, sizeof(session_id));
    if (!exact_sha256(scratch, payload_length, digest)) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_CRYPTO_FAILED;
    }
    lowercase_hex(digest, payload_sha256);
    prefixed_hash(EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX, payload_sha256, event_id);
    if (!copy_text(session_id, sizeof(session_id), input->session_id)) {
        clear_scratch(scratch, scratch_capacity);
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVARIANT_FAILED;
    }

    const egolink_outbox_priority_t priority =
        urgency == EGOLINK_LOCATION_OUTBOX_SOS_ESCALATED
            ? EGOLINK_OUTBOX_PRIORITY_CRITICAL
            : EGOLINK_OUTBOX_PRIORITY_NORMAL;
    const egolink_outbox_source_time_kind_t source_time_kind =
        input->event_time_source ==
                EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS
            ? EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS
            : EGOLINK_OUTBOX_SOURCE_TIME_UTC_MS;
    const egolink_outbox_enqueue_request_t request = {
        .event_id = event_id,
        .event_type = EGOLINK_LOCATION_OUTBOX_EVENT_TYPE,
        .priority = priority,
        .payload_kind = EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON,
        .payload = (const uint8_t *)scratch,
        .payload_length = payload_length,
        .source_time_kind = source_time_kind,
        .source_event_time_ms = input->event_time_ms,
        .boot_count = input->boot_count,
        .session_id = session_id,
        .source_sequence = input->sequence_id,
    };
    egolink_outbox_record_view_t record;
    (void)memset(&record, 0, sizeof(record));
    result->outbox_status = egolink_outbox_enqueue(
        adapter->outbox, &request, now_ms, &record);
    clear_scratch(scratch, scratch_capacity);

    if (result->outbox_status != EGOLINK_OUTBOX_OK &&
        result->outbox_status != EGOLINK_OUTBOX_DUPLICATE) {
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_OUTBOX_FAILED;
    }
    if (!enqueue_record_matches(
            &record,
            event_id,
            payload_sha256,
            priority,
            source_time_kind,
            session_id,
            input,
            payload_length)) {
        return EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVARIANT_FAILED;
    }

    result->priority = priority;
    result->payload_length = payload_length;
    (void)memcpy(
        result->payload_sha256, payload_sha256, sizeof(result->payload_sha256));
    (void)memcpy(result->event_id, event_id, sizeof(result->event_id));
    return result->outbox_status == EGOLINK_OUTBOX_DUPLICATE
        ? EGOLINK_LOCATION_OUTBOX_ENQUEUE_DUPLICATE
        : EGOLINK_LOCATION_OUTBOX_ENQUEUE_OK;
}

static size_t object_member_count(const cJSON *object, const char *name)
{
    size_t count = 0U;
    const cJSON *child = NULL;
    cJSON_ArrayForEach(child, object) {
        if (child->string != NULL && strcmp(child->string, name) == 0) {
            ++count;
        }
    }
    return count;
}

static bool ack_member_name(const char *name)
{
    static const char *const allowed[] = {
        "contract_version",
        "ack_id",
        "device_id",
        "event_id",
        "payload_sha256",
        "status",
        "ack_time_ms",
    };
    if (name == NULL) {
        return false;
    }
    for (size_t index = 0U; index < sizeof(allowed) / sizeof(allowed[0]); ++index) {
        if (strcmp(name, allowed[index]) == 0) {
            return true;
        }
    }
    return false;
}

static bool exact_ack_shape(const cJSON *ack)
{
    if (!cJSON_IsObject(ack) || cJSON_GetArraySize(ack) != 7) {
        return false;
    }
    static const char *const required[] = {
        "contract_version",
        "ack_id",
        "device_id",
        "event_id",
        "payload_sha256",
        "status",
        "ack_time_ms",
    };
    for (size_t index = 0U;
         index < sizeof(required) / sizeof(required[0]);
         ++index) {
        if (object_member_count(ack, required[index]) != 1U) {
            return false;
        }
    }
    const cJSON *child = NULL;
    cJSON_ArrayForEach(child, ack) {
        if (!ack_member_name(child->string)) {
            return false;
        }
    }
    return true;
}

static size_t bounded_string_length(const char *value, size_t capacity)
{
    size_t length = 0U;
    if (value == NULL) {
        return 0U;
    }
    while (length < capacity && value[length] != '\0') {
        ++length;
    }
    return length;
}

static bool ascii_id_first(char value)
{
    return (value >= 'A' && value <= 'Z') ||
           (value >= 'a' && value <= 'z') ||
           (value >= '0' && value <= '9');
}

static bool safe_identifier(const char *value)
{
    const size_t length = bounded_string_length(
        value, EGOLINK_OUTBOX_ID_CAPACITY);
    if (length == 0U || length >= EGOLINK_OUTBOX_ID_CAPACITY ||
        !ascii_id_first(value[0])) {
        return false;
    }
    for (size_t index = 1U; index < length; ++index) {
        const char character = value[index];
        if (!(ascii_id_first(character) || character == '.' ||
              character == '_' || character == ':' || character == '@' ||
              character == '-')) {
            return false;
        }
    }
    return true;
}

egolink_outbox_status_t egolink_location_outbox_adapter_init(
    egolink_location_outbox_adapter_t *adapter,
    egolink_outbox_t *outbox,
    const egolink_outbox_config_t *config,
    const egolink_outbox_storage_t *storage,
    uint64_t runtime_epoch,
    uint64_t now_ms,
    egolink_outbox_init_report_t *report)
{
    if (adapter == NULL || outbox == NULL || config == NULL ||
        config->device_id == NULL || storage == NULL || report == NULL) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    (void)memset(adapter, 0, sizeof(*adapter));
    const egolink_outbox_status_t status = egolink_outbox_init(
        outbox, config, storage, runtime_epoch, now_ms, report);
    if (status != EGOLINK_OUTBOX_OK) {
        return status;
    }
    if (!safe_identifier(config->device_id)) {
        egolink_outbox_deinit(outbox);
        return EGOLINK_OUTBOX_INVALID_IDENTITY;
    }
    const size_t device_id_length = strlen(config->device_id);
    (void)memcpy(adapter->device_id, config->device_id, device_id_length + 1U);
    adapter->outbox = outbox;
    adapter->initialized = true;
    return EGOLINK_OUTBOX_OK;
}

void egolink_location_outbox_adapter_deinit(
    egolink_location_outbox_adapter_t *adapter)
{
    if (adapter == NULL) {
        return;
    }
    if (adapter->initialized && adapter->outbox != NULL) {
        egolink_outbox_deinit(adapter->outbox);
    }
    (void)memset(adapter, 0, sizeof(*adapter));
}

static bool lowercase_sha256(const char *value)
{
    if (value == NULL ||
        bounded_string_length(value, EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) !=
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U) {
        return false;
    }
    for (size_t index = 0U;
         index < EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U;
         ++index) {
        const char character = value[index];
        if (!((character >= '0' && character <= '9') ||
              (character >= 'a' && character <= 'f'))) {
            return false;
        }
    }
    return true;
}

static bool string_item_equals(const cJSON *item, const char *expected)
{
    return cJSON_IsString(item) && item->valuestring != NULL &&
           strcmp(item->valuestring, expected) == 0;
}

static bool parse_safe_json_integer(const cJSON *item, uint64_t *output)
{
    if (!cJSON_IsNumber(item) || output == NULL) {
        return false;
    }
    const double value = item->valuedouble;
    if (value != value || value < 0.0 ||
        value > (double)EGOLINK_LOCATION_OUTBOX_JSON_SAFE_INTEGER_MAX) {
        return false;
    }
    const uint64_t integer = (uint64_t)value;
    if ((double)integer != value) {
        return false;
    }
    *output = integer;
    return true;
}

typedef enum {
    PARSE_ACK_OK = 0,
    PARSE_ACK_INVALID_RESPONSE,
    PARSE_ACK_INVALID_SCOPE,
    PARSE_ACK_INVALID_ACK,
} parse_ack_status_t;

static parse_ack_status_t parse_delivery_ack(
    const uint8_t *response_json,
    size_t response_length,
    egolink_outbox_ack_t *parsed,
    cJSON **owned_root)
{
    *owned_root = NULL;
    (void)memset(parsed, 0, sizeof(*parsed));
    if (response_json == NULL || response_length == 0U ||
        response_length > EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES ||
        memchr(response_json, 0, response_length) != NULL ||
        memchr(response_json, '\\', response_length) != NULL) {
        return PARSE_ACK_INVALID_RESPONSE;
    }

    const char *parse_end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(
        (const char *)response_json, response_length, &parse_end, false);
    if (root == NULL || !cJSON_IsObject(root) || parse_end == NULL) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_RESPONSE;
    }
    const char *response_end = (const char *)response_json + response_length;
    while (parse_end < response_end &&
           (*parse_end == ' ' || *parse_end == '\t' ||
            *parse_end == '\r' || *parse_end == '\n')) {
        ++parse_end;
    }
    if (parse_end != response_end || object_member_count(root, "ok") != 1U ||
        !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(root, "ok")) ||
        object_member_count(root, "delivery_scope") != 1U ||
        object_member_count(root, "delivery_ack") != 1U) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_RESPONSE;
    }

    const cJSON *scope = cJSON_GetObjectItemCaseSensitive(root, "delivery_scope");
    if (!string_item_equals(scope, EGOLINK_LOCATION_OUTBOX_DELIVERY_SCOPE)) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_SCOPE;
    }
    const cJSON *ack = cJSON_GetObjectItemCaseSensitive(root, "delivery_ack");
    if (!exact_ack_shape(ack)) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_ACK;
    }

    const cJSON *contract = cJSON_GetObjectItemCaseSensitive(
        ack, "contract_version");
    const cJSON *ack_id = cJSON_GetObjectItemCaseSensitive(ack, "ack_id");
    const cJSON *device_id = cJSON_GetObjectItemCaseSensitive(ack, "device_id");
    const cJSON *event_id = cJSON_GetObjectItemCaseSensitive(ack, "event_id");
    const cJSON *payload_sha256 = cJSON_GetObjectItemCaseSensitive(
        ack, "payload_sha256");
    const cJSON *status = cJSON_GetObjectItemCaseSensitive(ack, "status");
    const cJSON *ack_time = cJSON_GetObjectItemCaseSensitive(ack, "ack_time_ms");
    uint64_t ack_time_ms = 0U;
    if (!string_item_equals(contract, EGOLINK_OUTBOX_ACK_CONTRACT_VERSION) ||
        !cJSON_IsString(ack_id) || ack_id->valuestring == NULL ||
        !cJSON_IsString(device_id) || !safe_identifier(device_id->valuestring) ||
        !cJSON_IsString(event_id) || event_id->valuestring == NULL ||
        !cJSON_IsString(payload_sha256) ||
        !lowercase_sha256(payload_sha256->valuestring) ||
        !string_item_equals(status, "accepted") ||
        !parse_safe_json_integer(ack_time, &ack_time_ms)) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_ACK;
    }

    char expected_event_id[EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY];
    char expected_ack_id[EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY];
    prefixed_hash(
        EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX,
        payload_sha256->valuestring,
        expected_event_id);
    prefixed_hash(
        EGOLINK_LOCATION_OUTBOX_ACK_PREFIX,
        payload_sha256->valuestring,
        expected_ack_id);
    if (strcmp(event_id->valuestring, expected_event_id) != 0 ||
        strcmp(ack_id->valuestring, expected_ack_id) != 0) {
        cJSON_Delete(root);
        return PARSE_ACK_INVALID_ACK;
    }

    parsed->contract_version = contract->valuestring;
    parsed->ack_id = ack_id->valuestring;
    parsed->device_id = device_id->valuestring;
    parsed->event_id = event_id->valuestring;
    parsed->payload_sha256 = payload_sha256->valuestring;
    parsed->status = EGOLINK_OUTBOX_ACK_ACCEPTED;
    parsed->ack_time_ms = ack_time_ms;
    *owned_root = root;
    return PARSE_ACK_OK;
}

egolink_location_outbox_finish_status_t
egolink_location_outbox_finish_attempt(
    egolink_location_outbox_adapter_t *adapter,
    const char *attempt_token,
    bool accepted_by_transport,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_location_outbox_finish_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->transport_status = EGOLINK_OUTBOX_INVALID_ARGUMENT;
        result->ack_status = EGOLINK_OUTBOX_INVALID_ACK;
    }
    if (adapter == NULL || !adapter->initialized || adapter->outbox == NULL ||
        attempt_token == NULL || result == NULL) {
        return EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ARGUMENT;
    }

    result->transport_status = egolink_outbox_record_transport_result(
        adapter->outbox,
        attempt_token,
        accepted_by_transport,
        transport_error_code,
        now_ms);
    if (result->transport_status != EGOLINK_OUTBOX_OK &&
        result->transport_status != EGOLINK_OUTBOX_DUPLICATE) {
        return EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_STATE_FAILED;
    }
    if (!accepted_by_transport) {
        return EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_REJECTED_RETAINED;
    }

    egolink_outbox_ack_t parsed;
    cJSON *owned_root = NULL;
    const parse_ack_status_t parse_status = parse_delivery_ack(
        response_json, response_length, &parsed, &owned_root);
    if (parse_status != PARSE_ACK_OK) {
        switch (parse_status) {
        case PARSE_ACK_INVALID_SCOPE:
            return EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_SCOPE;
        case PARSE_ACK_INVALID_ACK:
            return EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ACK;
        case PARSE_ACK_INVALID_RESPONSE:
        default:
            return EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_RESPONSE;
        }
    }

    result->ack_handler_called = true;
    result->ack_status = egolink_outbox_handle_ack(
        adapter->outbox, &parsed, now_ms);
    cJSON_Delete(owned_root);
    if (result->ack_status == EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK) {
        return EGOLINK_LOCATION_OUTBOX_FINISH_ACK_DELETED;
    }
    if (result->ack_status == EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK) {
        return EGOLINK_LOCATION_OUTBOX_FINISH_ACK_ALREADY_APPLIED;
    }
    return EGOLINK_LOCATION_OUTBOX_FINISH_ACK_STATE_FAILED;
}

const char *egolink_location_outbox_enqueue_status_name(
    egolink_location_outbox_enqueue_status_t status)
{
    switch (status) {
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_OK: return "ok";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_DUPLICATE: return "duplicate";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_EMIT_FAILED: return "emit_failed";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_PAYLOAD_TOO_LARGE:
        return "payload_too_large";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_CRYPTO_FAILED:
        return "crypto_failed";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_OUTBOX_FAILED: return "outbox_failed";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVARIANT_FAILED:
        return "invariant_failed";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_LOCATION_OUTBOX_ENQUEUE_DEVICE_MISMATCH:
        return "device_mismatch";
    default: return "unknown";
    }
}

const char *egolink_location_outbox_finish_status_name(
    egolink_location_outbox_finish_status_t status)
{
    switch (status) {
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_DELETED: return "ack_deleted";
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_ALREADY_APPLIED:
        return "ack_already_applied";
    case EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_REJECTED_RETAINED:
        return "transport_rejected_retained";
    case EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_STATE_FAILED:
        return "transport_state_failed";
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_RESPONSE:
        return "invalid_response";
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_SCOPE: return "invalid_scope";
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ACK: return "invalid_ack";
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_STATE_FAILED:
        return "ack_state_failed";
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ARGUMENT:
        return "invalid_argument";
    default: return "unknown";
    }
}
