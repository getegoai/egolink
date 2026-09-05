#include "sos_outbox_adapter.h"

#include <limits.h>
#include <string.h>

#include "cJSON.h"
#include "mbedtls/sha256.h"
#include "sos_orchestrator.h"

#define SOS_RECORD_INVALID_ERROR_CODE "SOS_RECORD_INVALID"
#define SOS_RESPONSE_INVALID_ERROR_CODE "SOS_RESPONSE_INVALID"
#define SOS_RESULT_INVALID_ERROR_CODE "SOS_RESULT_INVALID"
#define SOS_SCOPE_INVALID_ERROR_CODE "SOS_SCOPE_INVALID"
#define SOS_ACK_INVALID_ERROR_CODE "SOS_ACK_INVALID"
#define SOS_ACK_MISMATCH_ERROR_CODE "SOS_ACK_MISMATCH"
#define ACK_PREFIX "ack-"

_Static_assert(
    EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES <=
        EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
    "SOS payload must fit one outbox send item");
_Static_assert(
    EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY <=
        EGOLINK_OUTBOX_ID_CAPACITY,
    "SOS event identity must fit the outbox record view");

typedef enum {
    PARSE_RESPONSE_OK = 0,
    PARSE_RESPONSE_INVALID,
    PARSE_RESPONSE_INVALID_RESULT,
    PARSE_RESPONSE_INVALID_SCOPE,
    PARSE_RESPONSE_INVALID_ACK,
    PARSE_RESPONSE_IDENTITY_MISMATCH,
} parse_response_status_t;

static bool manual_sos_payload_matches(
    const egolink_sos_outbox_adapter_t *adapter,
    const egolink_outbox_send_item_t *send_item);

static void secure_zero(void *buffer, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)buffer;
    while (cursor != NULL && length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

void egolink_sos_outbox_clear_send_item(
    egolink_outbox_send_item_t *send_item)
{
    if (send_item != NULL) {
        secure_zero(send_item, sizeof(*send_item));
    }
}

static size_t bounded_string_length(const char *value, size_t capacity)
{
    size_t length = 0U;
    if (value == NULL) {
        return capacity;
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

static bool exact_bounded_text(
    const char *left,
    const char *right,
    size_t capacity)
{
    const size_t left_length = bounded_string_length(left, capacity);
    const size_t right_length = bounded_string_length(right, capacity);
    return left_length < capacity && left_length == right_length &&
        memcmp(left, right, left_length) == 0;
}

static bool lowercase_sha256(const char *value)
{
    if (bounded_string_length(
            value, EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) !=
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

static bool exact_payload_hash(
    const uint8_t *payload,
    size_t payload_length,
    const char *expected_hex)
{
    uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES];
    char digest_hex[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    (void)memset(digest, 0, sizeof(digest));
    (void)memset(digest_hex, 0, sizeof(digest_hex));
    const bool hashed = payload != NULL && payload_length > 0U &&
        mbedtls_sha256(payload, payload_length, digest, 0) == 0;
    if (hashed) {
        lowercase_hex(digest, digest_hex);
    }
    const bool matches = hashed && lowercase_sha256(expected_hex) &&
        exact_bounded_text(
            digest_hex, expected_hex, EGOLINK_OUTBOX_SHA256_HEX_CAPACITY);
    secure_zero(digest, sizeof(digest));
    secure_zero(digest_hex, sizeof(digest_hex));
    return matches;
}

static bool parse_decimal_segment(
    const char **cursor,
    char terminator,
    uint64_t *output)
{
    if (cursor == NULL || *cursor == NULL || output == NULL ||
        **cursor < '0' || **cursor > '9') {
        return false;
    }
    const char *position = *cursor;
    if (*position == '0' && position[1] >= '0' && position[1] <= '9') {
        return false;
    }
    uint64_t value = 0U;
    while (*position >= '0' && *position <= '9') {
        const uint64_t digit = (uint64_t)(*position - '0');
        if (value > (UINT64_MAX - digit) / UINT64_C(10)) {
            return false;
        }
        value = value * UINT64_C(10) + digit;
        ++position;
    }
    if (*position != terminator) {
        return false;
    }
    *output = value;
    *cursor = terminator == '\0' ? position : position + 1;
    return true;
}

static bool event_id_matches_lineage(
    const egolink_outbox_record_view_t *record)
{
    static const char prefix[] = "sos-b";
    const size_t event_length = bounded_string_length(
        record->event_id, EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY);
    if (event_length == 0U ||
        event_length >= EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY ||
        memcmp(record->event_id, prefix, sizeof(prefix) - 1U) != 0) {
        return false;
    }
    const char *cursor = record->event_id + sizeof(prefix) - 1U;
    uint64_t boot_count = 0U;
    uint64_t source_sequence = 0U;
    uint64_t source_time_ms = 0U;
    if (!parse_decimal_segment(&cursor, '-', &boot_count) ||
        cursor[0] != 'q') {
        return false;
    }
    ++cursor;
    if (!parse_decimal_segment(&cursor, '-', &source_sequence) ||
        cursor[0] != 't') {
        return false;
    }
    ++cursor;
    if (!parse_decimal_segment(&cursor, '\0', &source_time_ms)) {
        return false;
    }
    return boot_count == record->boot_count &&
        source_sequence == record->source_sequence &&
        source_time_ms == record->source_event_time_ms;
}

static bool manual_sos_send_item_valid(
    const egolink_sos_outbox_adapter_t *adapter,
    const egolink_outbox_send_item_t *send_item)
{
    const egolink_outbox_record_view_t *record = &send_item->record;
    return strcmp(
               record->event_type,
               EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE) == 0 &&
        record->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL &&
        record->source_time_kind ==
            EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS &&
        record->send_state == EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED &&
        record->last_attempt_result == EGOLINK_OUTBOX_ATTEMPT_PENDING &&
        record->attempt_count > 0U &&
        send_item->payload_length > 0U &&
        send_item->payload_length == record->payload_length &&
        send_item->payload_length <=
            EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES &&
        lowercase_sha256(record->last_attempt_token) &&
        event_id_matches_lineage(record) &&
        exact_payload_hash(
            send_item->payload,
            send_item->payload_length,
            record->payload_sha256) &&
        manual_sos_payload_matches(adapter, send_item);
}

static void clear_active(egolink_sos_outbox_adapter_t *adapter)
{
    adapter->attempt_active = false;
    secure_zero(
        adapter->active_attempt_token,
        sizeof(adapter->active_attempt_token));
    secure_zero(adapter->active_event_id, sizeof(adapter->active_event_id));
    secure_zero(
        adapter->active_payload_sha256,
        sizeof(adapter->active_payload_sha256));
    adapter->active_payload_length = 0U;
}

static void clear_send_view(egolink_sos_outbox_send_view_t *view)
{
    if (view != NULL) {
        (void)memset(view, 0, sizeof(*view));
    }
}

static void clear_begin_result(egolink_sos_outbox_begin_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->outbox_status = EGOLINK_OUTBOX_INVALID_ARGUMENT;
        result->invalid_sos_settlement_status =
            EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
}

static void clear_finish_result(egolink_sos_outbox_finish_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->transport_status = EGOLINK_OUTBOX_INVALID_ARGUMENT;
        result->ack_status = EGOLINK_OUTBOX_INVALID_ACK;
    }
}

egolink_outbox_status_t egolink_sos_outbox_adapter_bind(
    egolink_sos_outbox_adapter_t *adapter,
    egolink_outbox_t *already_initialized_outbox,
    const char *device_id)
{
    if (adapter == NULL || already_initialized_outbox == NULL ||
        device_id == NULL) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    if (!safe_identifier(device_id)) {
        return EGOLINK_OUTBOX_INVALID_IDENTITY;
    }
    (void)memset(adapter, 0, sizeof(*adapter));
    const size_t length = strlen(device_id);
    (void)memcpy(adapter->device_id, device_id, length + 1U);
    adapter->outbox = already_initialized_outbox;
    adapter->initialized = true;
    return EGOLINK_OUTBOX_OK;
}

void egolink_sos_outbox_adapter_unbind(
    egolink_sos_outbox_adapter_t *adapter)
{
    if (adapter != NULL) {
        secure_zero(adapter, sizeof(*adapter));
    }
}

static void copy_active_identity(
    egolink_sos_outbox_adapter_t *adapter,
    const egolink_outbox_send_item_t *send_item)
{
    const egolink_outbox_record_view_t *record = &send_item->record;
    (void)memcpy(
        adapter->active_attempt_token,
        record->last_attempt_token,
        sizeof(adapter->active_attempt_token));
    (void)memcpy(
        adapter->active_event_id,
        record->event_id,
        sizeof(adapter->active_event_id));
    (void)memcpy(
        adapter->active_payload_sha256,
        record->payload_sha256,
        sizeof(adapter->active_payload_sha256));
    adapter->active_payload_length = send_item->payload_length;
    adapter->attempt_active = true;
}

egolink_sos_outbox_begin_status_t egolink_sos_outbox_begin_attempt(
    egolink_sos_outbox_adapter_t *adapter,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item,
    egolink_sos_outbox_send_view_t *send_view,
    egolink_sos_outbox_begin_result_t *result)
{
    clear_send_view(send_view);
    clear_begin_result(result);
    if (adapter == NULL || send_item == NULL || send_view == NULL ||
        result == NULL) {
        return EGOLINK_SOS_OUTBOX_BEGIN_INVALID_ARGUMENT;
    }
    if (!adapter->initialized || adapter->outbox == NULL) {
        return EGOLINK_SOS_OUTBOX_BEGIN_NOT_INITIALIZED;
    }
    if (adapter->attempt_active) {
        return EGOLINK_SOS_OUTBOX_BEGIN_ATTEMPT_ALREADY_ACTIVE;
    }

    egolink_sos_outbox_clear_send_item(send_item);
    result->outbox_status = egolink_outbox_begin_send_attempt(
        adapter->outbox, now_ms, send_item);
    if (result->outbox_status == EGOLINK_OUTBOX_NO_DUE_RECORD) {
        return EGOLINK_SOS_OUTBOX_BEGIN_NO_DUE_RECORD;
    }
    if (result->outbox_status != EGOLINK_OUTBOX_OK) {
        return EGOLINK_SOS_OUTBOX_BEGIN_OUTBOX_STATE_FAILED;
    }
    if (strcmp(
            send_item->record.event_type,
            EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE) != 0) {
        return EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD;
    }
    if (!manual_sos_send_item_valid(adapter, send_item)) {
        result->invalid_sos_settlement_attempted = true;
        result->invalid_sos_settlement_status =
            egolink_outbox_record_transport_result(
                adapter->outbox,
                send_item->record.last_attempt_token,
                false,
                SOS_RECORD_INVALID_ERROR_CODE,
                now_ms);
        egolink_sos_outbox_clear_send_item(send_item);
        return result->invalid_sos_settlement_status == EGOLINK_OUTBOX_OK ||
                result->invalid_sos_settlement_status == EGOLINK_OUTBOX_DUPLICATE
            ? EGOLINK_SOS_OUTBOX_BEGIN_INVALID_SOS_RETAINED
            : EGOLINK_SOS_OUTBOX_BEGIN_OUTBOX_STATE_FAILED;
    }

    copy_active_identity(adapter, send_item);
    send_view->payload = send_item->payload;
    send_view->payload_length = send_item->payload_length;
    send_view->device_id = adapter->device_id;
    send_view->event_id = send_item->record.event_id;
    send_view->payload_sha256 = send_item->record.payload_sha256;
    send_view->attempt_token = send_item->record.last_attempt_token;
    return EGOLINK_SOS_OUTBOX_BEGIN_READY;
}

static bool active_item_matches(
    const egolink_sos_outbox_adapter_t *adapter,
    const egolink_outbox_send_item_t *send_item)
{
    return manual_sos_send_item_valid(adapter, send_item) &&
        send_item->payload_length == adapter->active_payload_length &&
        exact_bounded_text(
            send_item->record.last_attempt_token,
            adapter->active_attempt_token,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) &&
        exact_bounded_text(
            send_item->record.event_id,
            adapter->active_event_id,
            EGOLINK_OUTBOX_ID_CAPACITY) &&
        exact_bounded_text(
            send_item->record.payload_sha256,
            adapter->active_payload_sha256,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY);
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

static bool exact_object_shape(
    const cJSON *object,
    const char *const *required,
    size_t required_count)
{
    if (!cJSON_IsObject(object) || required == NULL ||
        required_count > (size_t)INT_MAX ||
        cJSON_GetArraySize(object) != (int)required_count) {
        return false;
    }
    for (size_t index = 0U; index < required_count; ++index) {
        if (object_member_count(object, required[index]) != 1U) {
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
        value > (double)EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX) {
        return false;
    }
    const uint64_t integer = (uint64_t)value;
    if ((double)integer != value) {
        return false;
    }
    *output = integer;
    return true;
}

static bool bounded_ascii_json_bytes(
    const uint8_t *json_bytes,
    size_t json_length,
    size_t maximum_length)
{
    if (json_bytes == NULL || json_length == 0U ||
        json_length > maximum_length) {
        return false;
    }
    for (size_t index = 0U; index < json_length; ++index) {
        const uint8_t value = json_bytes[index];
        const bool whitespace = value == (uint8_t)'\t' ||
            value == (uint8_t)'\r' || value == (uint8_t)'\n';
        if (value == UINT8_C(0) || value == (uint8_t)'\\' ||
            (!whitespace &&
             (value < UINT8_C(0x20) || value > UINT8_C(0x7e)))) {
            return false;
        }
    }
    return true;
}

static bool json_u64_equals(const cJSON *item, uint64_t expected)
{
    uint64_t parsed = 0U;
    return parse_safe_json_integer(item, &parsed) && parsed == expected;
}

static bool generated_battery_value(const cJSON *item)
{
    if (cJSON_IsNull(item)) {
        return true;
    }
    uint64_t value = 0U;
    return parse_safe_json_integer(item, &value) && value <= UINT64_C(100);
}

static bool manual_sos_payload_matches(
    const egolink_sos_outbox_adapter_t *adapter,
    const egolink_outbox_send_item_t *send_item)
{
    static const char *const root_fields[] = {
        "contract_version", "event_id", "device_id", "timestamp_ms",
        "sequence", "event_type", "priority", "source", "model_result",
        "context", "evidence", "privacy",
    };
    static const char *const model_fields[] = {
        "manual_input", "qualified_long_press", "time_source", "boot_count",
        "session_id", "source_sequence",
    };
    static const char *const context_fields[] = {
        "mode", "battery_percent", "base_online", "upload_available",
    };
    static const char *const evidence_fields[] = {
        "audio_clip_ref", "image_ref", "imu_window_ref", "location_fresh",
    };
    static const char *const privacy_fields[] = {
        "privacy_mode", "raw_evidence_allowed", "retention_seconds",
    };
    if (!bounded_ascii_json_bytes(
            send_item->payload,
            send_item->payload_length,
            EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES)) {
        return false;
    }

    const char *parse_end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(
        (const char *)send_item->payload,
        send_item->payload_length,
        &parse_end,
        false);
    const char *payload_end =
        (const char *)send_item->payload + send_item->payload_length;
    if (root == NULL || parse_end == NULL ||
        !exact_object_shape(
            root, root_fields, sizeof(root_fields) / sizeof(root_fields[0]))) {
        cJSON_Delete(root);
        return false;
    }
    while (parse_end < payload_end &&
           (*parse_end == ' ' || *parse_end == '\t' ||
            *parse_end == '\r' || *parse_end == '\n')) {
        ++parse_end;
    }
    if (parse_end != payload_end) {
        cJSON_Delete(root);
        return false;
    }

    const egolink_outbox_record_view_t *record = &send_item->record;
    const cJSON *model = cJSON_GetObjectItemCaseSensitive(root, "model_result");
    const cJSON *context = cJSON_GetObjectItemCaseSensitive(root, "context");
    const cJSON *evidence = cJSON_GetObjectItemCaseSensitive(root, "evidence");
    const cJSON *privacy = cJSON_GetObjectItemCaseSensitive(root, "privacy");
    const bool shapes = exact_object_shape(
            model,
            model_fields,
            sizeof(model_fields) / sizeof(model_fields[0])) &&
        exact_object_shape(
            context,
            context_fields,
            sizeof(context_fields) / sizeof(context_fields[0])) &&
        exact_object_shape(
            evidence,
            evidence_fields,
            sizeof(evidence_fields) / sizeof(evidence_fields[0])) &&
        exact_object_shape(
            privacy,
            privacy_fields,
            sizeof(privacy_fields) / sizeof(privacy_fields[0]));
    const bool root_identity =
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "contract_version"),
            "1.0.0") &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "event_id"),
            record->event_id) &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "device_id"),
            adapter->device_id) &&
        json_u64_equals(
            cJSON_GetObjectItemCaseSensitive(root, "timestamp_ms"),
            record->source_event_time_ms) &&
        json_u64_equals(
            cJSON_GetObjectItemCaseSensitive(root, "sequence"),
            record->source_sequence) &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "event_type"),
            EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE) &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "priority"),
            "critical") &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(root, "source"),
            "device_rule");
    const bool model_identity = shapes &&
        cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(model, "manual_input")) &&
        cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(
            model, "qualified_long_press")) &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(model, "time_source"),
            "boot_monotonic_ms") &&
        json_u64_equals(
            cJSON_GetObjectItemCaseSensitive(model, "boot_count"),
            record->boot_count) &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(model, "session_id"),
            record->session_id) &&
        json_u64_equals(
            cJSON_GetObjectItemCaseSensitive(model, "source_sequence"),
            record->source_sequence);
    const bool context_valid = shapes &&
        string_item_equals(
            cJSON_GetObjectItemCaseSensitive(context, "mode"),
            "manual_sos") &&
        generated_battery_value(cJSON_GetObjectItemCaseSensitive(
            context, "battery_percent")) &&
        (cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(
             context, "base_online")) ||
         cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(
             context, "base_online"))) &&
        (cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(
             context, "upload_available")) ||
         cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(
             context, "upload_available")));
    const bool evidence_valid = shapes &&
        cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(
            evidence, "audio_clip_ref")) &&
        cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(evidence, "image_ref")) &&
        cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(
            evidence, "imu_window_ref")) &&
        cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(
            evidence, "location_fresh"));
    const bool privacy_valid = shapes &&
        cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(
            privacy, "privacy_mode")) &&
        cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(
            privacy, "raw_evidence_allowed")) &&
        json_u64_equals(
            cJSON_GetObjectItemCaseSensitive(privacy, "retention_seconds"),
            UINT64_C(86400));
    const bool valid = shapes && root_identity && model_identity &&
        context_valid && evidence_valid && privacy_valid;
    cJSON_Delete(root);
    return valid;
}

static bool exact_ack_shape(const cJSON *ack)
{
    static const char *const fields[] = {
        "contract_version",
        "ack_id",
        "device_id",
        "event_id",
        "payload_sha256",
        "status",
        "ack_time_ms",
    };
    return exact_object_shape(ack, fields, sizeof(fields) / sizeof(fields[0]));
}

static parse_response_status_t parse_delivery_response(
    const uint8_t *response_json,
    size_t response_length,
    const egolink_sos_outbox_adapter_t *adapter,
    egolink_outbox_ack_t *parsed,
    egolink_sos_outbox_server_result_t *server_result,
    cJSON **owned_root)
{
    static const char *const response_fields[] = {
        "ok", "result", "delivery_ack", "delivery_scope",
    };
    static const char *const result_fields[] = {"status"};
    *owned_root = NULL;
    (void)memset(parsed, 0, sizeof(*parsed));
    *server_result = EGOLINK_SOS_OUTBOX_SERVER_RESULT_NONE;
    if (!bounded_ascii_json_bytes(
            response_json,
            response_length,
            EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES)) {
        return PARSE_RESPONSE_INVALID;
    }

    const char *parse_end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(
        (const char *)response_json, response_length, &parse_end, false);
    if (root == NULL || parse_end == NULL ||
        !exact_object_shape(
            root,
            response_fields,
            sizeof(response_fields) / sizeof(response_fields[0])) ||
        !cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(root, "ok"))) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID;
    }
    const char *response_end = (const char *)response_json + response_length;
    while (parse_end < response_end &&
           (*parse_end == ' ' || *parse_end == '\t' ||
            *parse_end == '\r' || *parse_end == '\n')) {
        ++parse_end;
    }
    if (parse_end != response_end) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID;
    }

    const cJSON *result = cJSON_GetObjectItemCaseSensitive(root, "result");
    if (!exact_object_shape(
            result,
            result_fields,
            sizeof(result_fields) / sizeof(result_fields[0]))) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID_RESULT;
    }
    const cJSON *result_status = cJSON_GetObjectItemCaseSensitive(
        result, "status");
    if (string_item_equals(result_status, "accepted")) {
        *server_result = EGOLINK_SOS_OUTBOX_SERVER_RESULT_ACCEPTED;
    } else if (string_item_equals(result_status, "duplicate")) {
        *server_result = EGOLINK_SOS_OUTBOX_SERVER_RESULT_DUPLICATE;
    } else {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID_RESULT;
    }

    const cJSON *scope = cJSON_GetObjectItemCaseSensitive(
        root, "delivery_scope");
    if (!string_item_equals(scope, EGOLINK_SOS_OUTBOX_DELIVERY_SCOPE)) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID_SCOPE;
    }
    const cJSON *ack = cJSON_GetObjectItemCaseSensitive(root, "delivery_ack");
    if (!exact_ack_shape(ack)) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID_ACK;
    }

    const cJSON *contract = cJSON_GetObjectItemCaseSensitive(
        ack, "contract_version");
    const cJSON *ack_id = cJSON_GetObjectItemCaseSensitive(ack, "ack_id");
    const cJSON *device_id = cJSON_GetObjectItemCaseSensitive(ack, "device_id");
    const cJSON *event_id = cJSON_GetObjectItemCaseSensitive(ack, "event_id");
    const cJSON *payload_sha256 = cJSON_GetObjectItemCaseSensitive(
        ack, "payload_sha256");
    const cJSON *status = cJSON_GetObjectItemCaseSensitive(ack, "status");
    const cJSON *ack_time = cJSON_GetObjectItemCaseSensitive(
        ack, "ack_time_ms");
    uint64_t ack_time_ms = 0U;
    if (!string_item_equals(contract, EGOLINK_OUTBOX_ACK_CONTRACT_VERSION) ||
        !cJSON_IsString(ack_id) || ack_id->valuestring == NULL ||
        !cJSON_IsString(device_id) || !safe_identifier(device_id->valuestring) ||
        !cJSON_IsString(event_id) || !safe_identifier(event_id->valuestring) ||
        !cJSON_IsString(payload_sha256) ||
        !lowercase_sha256(payload_sha256->valuestring) ||
        !string_item_equals(status, "accepted") ||
        !parse_safe_json_integer(ack_time, &ack_time_ms)) {
        cJSON_Delete(root);
        return PARSE_RESPONSE_INVALID_ACK;
    }

    char expected_ack_id[sizeof(ACK_PREFIX) - 1U +
        EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    (void)memset(expected_ack_id, 0, sizeof(expected_ack_id));
    (void)memcpy(expected_ack_id, ACK_PREFIX, sizeof(ACK_PREFIX) - 1U);
    (void)memcpy(
        expected_ack_id + sizeof(ACK_PREFIX) - 1U,
        adapter->active_payload_sha256,
        EGOLINK_OUTBOX_SHA256_HEX_CAPACITY);
    if (!exact_bounded_text(
            ack_id->valuestring,
            expected_ack_id,
            sizeof(expected_ack_id)) ||
        !exact_bounded_text(
            device_id->valuestring,
            adapter->device_id,
            EGOLINK_OUTBOX_ID_CAPACITY) ||
        !exact_bounded_text(
            event_id->valuestring,
            adapter->active_event_id,
            EGOLINK_OUTBOX_ID_CAPACITY) ||
        !exact_bounded_text(
            payload_sha256->valuestring,
            adapter->active_payload_sha256,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY)) {
        secure_zero(expected_ack_id, sizeof(expected_ack_id));
        cJSON_Delete(root);
        return PARSE_RESPONSE_IDENTITY_MISMATCH;
    }
    secure_zero(expected_ack_id, sizeof(expected_ack_id));

    parsed->contract_version = contract->valuestring;
    parsed->ack_id = ack_id->valuestring;
    parsed->device_id = device_id->valuestring;
    parsed->event_id = event_id->valuestring;
    parsed->payload_sha256 = payload_sha256->valuestring;
    parsed->status = EGOLINK_OUTBOX_ACK_ACCEPTED;
    parsed->ack_time_ms = ack_time_ms;
    *owned_root = root;
    return PARSE_RESPONSE_OK;
}

static void consume_active_attempt(
    egolink_sos_outbox_adapter_t *adapter,
    egolink_outbox_send_item_t *send_item)
{
    egolink_sos_outbox_clear_send_item(send_item);
    clear_active(adapter);
}

static const char *parse_failure_error_code(parse_response_status_t status)
{
    switch (status) {
    case PARSE_RESPONSE_INVALID_RESULT:
        return SOS_RESULT_INVALID_ERROR_CODE;
    case PARSE_RESPONSE_INVALID_SCOPE:
        return SOS_SCOPE_INVALID_ERROR_CODE;
    case PARSE_RESPONSE_INVALID_ACK:
        return SOS_ACK_INVALID_ERROR_CODE;
    case PARSE_RESPONSE_IDENTITY_MISMATCH:
        return SOS_ACK_MISMATCH_ERROR_CODE;
    case PARSE_RESPONSE_INVALID:
    default:
        return SOS_RESPONSE_INVALID_ERROR_CODE;
    }
}

static egolink_sos_outbox_finish_status_t parse_failure_finish_status(
    parse_response_status_t status)
{
    switch (status) {
    case PARSE_RESPONSE_INVALID_RESULT:
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESULT_RETAINED;
    case PARSE_RESPONSE_INVALID_SCOPE:
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_SCOPE_RETAINED;
    case PARSE_RESPONSE_INVALID_ACK:
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_ACK_RETAINED;
    case PARSE_RESPONSE_IDENTITY_MISMATCH:
        return EGOLINK_SOS_OUTBOX_FINISH_IDENTITY_MISMATCH_RETAINED;
    case PARSE_RESPONSE_INVALID:
    default:
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESPONSE_RETAINED;
    }
}

egolink_sos_outbox_finish_status_t egolink_sos_outbox_finish_attempt(
    egolink_sos_outbox_adapter_t *adapter,
    const char *attempt_token,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item,
    egolink_sos_outbox_finish_result_t *result)
{
    clear_finish_result(result);
    if (adapter == NULL || attempt_token == NULL || send_item == NULL ||
        result == NULL) {
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT;
    }
    if (!adapter->initialized || adapter->outbox == NULL) {
        return EGOLINK_SOS_OUTBOX_FINISH_NOT_INITIALIZED;
    }
    if (!adapter->attempt_active) {
        return EGOLINK_SOS_OUTBOX_FINISH_NO_ACTIVE_ATTEMPT;
    }
    if (!exact_bounded_text(
            attempt_token,
            adapter->active_attempt_token,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) ||
        !active_item_matches(adapter, send_item)) {
        return EGOLINK_SOS_OUTBOX_FINISH_ATTEMPT_MISMATCH;
    }

    const bool http_success = http_status_code >= UINT16_C(200) &&
        http_status_code <= UINT16_C(299);
    if (http_success && transport_error_code != NULL) {
        return EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT;
    }
    if (!http_success) {
        result->transport_status = egolink_outbox_record_transport_result(
            adapter->outbox,
            adapter->active_attempt_token,
            false,
            transport_error_code,
            now_ms);
        if (result->transport_status != EGOLINK_OUTBOX_OK &&
            result->transport_status != EGOLINK_OUTBOX_DUPLICATE) {
            return EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED;
        }
        consume_active_attempt(adapter, send_item);
        return EGOLINK_SOS_OUTBOX_FINISH_HTTP_REJECTED_RETAINED;
    }

    egolink_outbox_ack_t parsed;
    cJSON *owned_root = NULL;
    const parse_response_status_t parse_status = parse_delivery_response(
        response_json,
        response_length,
        adapter,
        &parsed,
        &result->server_result,
        &owned_root);
    if (parse_status != PARSE_RESPONSE_OK) {
        result->server_result = EGOLINK_SOS_OUTBOX_SERVER_RESULT_NONE;
        result->transport_status = egolink_outbox_record_transport_result(
            adapter->outbox,
            adapter->active_attempt_token,
            false,
            parse_failure_error_code(parse_status),
            now_ms);
        if (result->transport_status != EGOLINK_OUTBOX_OK &&
            result->transport_status != EGOLINK_OUTBOX_DUPLICATE) {
            return EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED;
        }
        consume_active_attempt(adapter, send_item);
        return parse_failure_finish_status(parse_status);
    }

    result->transport_status = egolink_outbox_record_transport_result(
        adapter->outbox,
        adapter->active_attempt_token,
        true,
        NULL,
        now_ms);
    if (result->transport_status != EGOLINK_OUTBOX_OK &&
        result->transport_status != EGOLINK_OUTBOX_DUPLICATE) {
        cJSON_Delete(owned_root);
        return EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED;
    }

    result->ack_handler_called = true;
    result->ack_status = egolink_outbox_handle_ack(
        adapter->outbox, &parsed, now_ms);
    cJSON_Delete(owned_root);
    if (result->ack_status == EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK) {
        consume_active_attempt(adapter, send_item);
        return EGOLINK_SOS_OUTBOX_FINISH_ACK_DELETED;
    }
    if (result->ack_status == EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK) {
        consume_active_attempt(adapter, send_item);
        return EGOLINK_SOS_OUTBOX_FINISH_ACK_ALREADY_APPLIED;
    }
    return EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED;
}

const char *egolink_sos_outbox_begin_status_name(
    egolink_sos_outbox_begin_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_OUTBOX_BEGIN_READY: return "ready";
    case EGOLINK_SOS_OUTBOX_BEGIN_NO_DUE_RECORD: return "no_due_record";
    case EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD: return "non_sos_head";
    case EGOLINK_SOS_OUTBOX_BEGIN_ATTEMPT_ALREADY_ACTIVE:
        return "attempt_already_active";
    case EGOLINK_SOS_OUTBOX_BEGIN_INVALID_SOS_RETAINED:
        return "invalid_sos_retained";
    case EGOLINK_SOS_OUTBOX_BEGIN_OUTBOX_STATE_FAILED:
        return "outbox_state_failed";
    case EGOLINK_SOS_OUTBOX_BEGIN_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_SOS_OUTBOX_BEGIN_NOT_INITIALIZED: return "not_initialized";
    default: return "unknown";
    }
}

const char *egolink_sos_outbox_finish_status_name(
    egolink_sos_outbox_finish_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_DELETED: return "ack_deleted";
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_ALREADY_APPLIED:
        return "ack_already_applied";
    case EGOLINK_SOS_OUTBOX_FINISH_HTTP_REJECTED_RETAINED:
        return "http_rejected_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESPONSE_RETAINED:
        return "invalid_response_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESULT_RETAINED:
        return "invalid_result_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_SCOPE_RETAINED:
        return "invalid_scope_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_ACK_RETAINED:
        return "invalid_ack_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_IDENTITY_MISMATCH_RETAINED:
        return "identity_mismatch_retained";
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED:
        return "ack_state_failed";
    case EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED:
        return "transport_state_failed";
    case EGOLINK_SOS_OUTBOX_FINISH_ATTEMPT_MISMATCH:
        return "attempt_mismatch";
    case EGOLINK_SOS_OUTBOX_FINISH_NO_ACTIVE_ATTEMPT:
        return "no_active_attempt";
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SOS_OUTBOX_FINISH_NOT_INITIALIZED:
        return "not_initialized";
    default: return "unknown";
    }
}
