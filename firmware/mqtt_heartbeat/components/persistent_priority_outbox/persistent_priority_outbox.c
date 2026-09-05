#include "persistent_priority_outbox.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>

#include "cJSON.h"
#include "mbedtls/sha256.h"

#define OUTBOX_IMAGE_FORMAT_VERSION UINT32_C(1)
#define OUTBOX_RECORD_FORMAT_VERSION UINT16_C(1)
#define OUTBOX_NO_SLOT INT8_C(-1)

static const uint8_t s_image_magic[8] = {
    UINT8_C(0x45), UINT8_C(0x47), UINT8_C(0x4f), UINT8_C(0x42),
    UINT8_C(0x58), UINT8_C(0x30), UINT8_C(0x31), UINT8_C(0x00),
};

typedef struct {
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint16_t max_records;
    uint16_t reserved_critical_records;
    uint32_t max_total_payload_bytes;
    uint32_t reserved_critical_payload_bytes;
    uint16_t max_payload_bytes;
    uint16_t tombstone_capacity;
    uint64_t base_retry_ms;
    uint64_t max_retry_ms;
    uint8_t configuration_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
} stored_config_t;

typedef struct {
    uint16_t record_format_version;
    uint8_t priority;
    uint8_t payload_kind;
    uint8_t source_time_kind;
    uint8_t send_state;
    uint8_t last_attempt_result;
    uint8_t reserved_zero;
    char event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char event_type[EGOLINK_OUTBOX_EVENT_TYPE_CAPACITY];
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint64_t source_event_time_ms;
    uint64_t boot_count;
    uint64_t source_sequence;
    uint16_t payload_length;
    uint8_t payload[EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES];
    uint8_t payload_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
    uint8_t identity_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
    uint64_t enqueue_runtime_epoch;
    uint64_t enqueue_time_ms;
    uint32_t attempt_count;
    uint32_t attempt_reserved_zero;
    uint64_t last_attempt_runtime_epoch;
    uint64_t last_attempt_time_ms;
    uint64_t next_retry_runtime_epoch;
    uint64_t next_retry_time_ms;
    uint8_t last_attempt_token[EGOLINK_OUTBOX_SHA256_BYTES];
    uint64_t last_result_runtime_epoch;
    uint64_t last_result_time_ms;
    char last_error_code[EGOLINK_OUTBOX_ERROR_CODE_CAPACITY];
} stored_record_t;

typedef struct {
    char ack_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint8_t payload_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
    uint64_t ack_time_ms;
    uint64_t recorded_runtime_epoch;
    uint64_t recorded_time_ms;
} stored_tombstone_t;

typedef struct {
    uint8_t magic[sizeof(s_image_magic)];
    uint32_t format_version;
    uint32_t image_size;
    uint64_t generation;
    stored_config_t configuration;
    uint16_t record_count;
    uint16_t tombstone_count;
    stored_record_t records[EGOLINK_OUTBOX_MAX_RECORDS];
    stored_tombstone_t tombstones[EGOLINK_OUTBOX_MAX_TOMBSTONES];
    egolink_outbox_metrics_t metrics;
    egolink_outbox_failure_t last_failure;
    uint8_t storage_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
} storage_image_t;

typedef struct {
    storage_image_t state;
    storage_image_t scratch;
    egolink_outbox_storage_t storage;
    uint64_t runtime_epoch;
    uint64_t last_now_ms;
    uint64_t volatile_storage_failure_count;
    egolink_outbox_recovery_state_t recovery_state;
    uint8_t active_slot;
    bool initialized;
    bool fault_latched;
} outbox_impl_t;

typedef struct {
    mbedtls_sha256_context context;
    bool usable;
} hash_builder_t;

_Static_assert(
    sizeof(outbox_impl_t) <= EGOLINK_OUTBOX_CORE_STORAGE_BYTES,
    "EGOLINK_OUTBOX_CORE_STORAGE_BYTES is too small");
_Static_assert(
    sizeof(storage_image_t) == EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES,
    "storage format v1 layout changed; version and migration are required");
_Static_assert(
    _Alignof(egolink_outbox_t) >= _Alignof(outbox_impl_t),
    "egolink_outbox_t does not satisfy the implementation alignment");
_Static_assert(
    offsetof(storage_image_t, storage_sha256) + EGOLINK_OUTBOX_SHA256_BYTES ==
        sizeof(storage_image_t),
    "storage_sha256 must be the final storage-image bytes");
_Static_assert(EGOLINK_OUTBOX_SLOT_COUNT == 2U, "the core requires two slots");

static outbox_impl_t *impl_of(egolink_outbox_t *outbox)
{
    return (outbox_impl_t *)(void *)outbox->opaque;
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

static bool ascii_is_id_first(char value)
{
    return (value >= 'A' && value <= 'Z') ||
        (value >= 'a' && value <= 'z') ||
        (value >= '0' && value <= '9');
}

static bool ascii_is_id_rest(char value)
{
    return ascii_is_id_first(value) || value == '.' || value == '_' ||
        value == ':' || value == '@' || value == '-';
}

static bool safe_identifier(const char *value, size_t capacity)
{
    size_t length = bounded_string_length(value, capacity);
    if (length == 0U || length >= capacity || !ascii_is_id_first(value[0])) {
        return false;
    }
    for (size_t index = 1U; index < length; ++index) {
        if (!ascii_is_id_rest(value[index])) {
            return false;
        }
    }
    return true;
}

static bool safe_error_code(const char *value)
{
    size_t length = bounded_string_length(
        value, EGOLINK_OUTBOX_ERROR_CODE_CAPACITY);
    if (length == 0U || length >= EGOLINK_OUTBOX_ERROR_CODE_CAPACITY ||
        value[0] < 'A' || value[0] > 'Z') {
        return false;
    }
    for (size_t index = 1U; index < length; ++index) {
        char character = value[index];
        if (!((character >= 'A' && character <= 'Z') ||
              (character >= '0' && character <= '9') || character == '_')) {
            return false;
        }
    }
    return true;
}

static bool copy_checked_text(
    char *destination,
    size_t destination_capacity,
    const char *source)
{
    if (!safe_identifier(source, destination_capacity)) {
        return false;
    }
    size_t length = bounded_string_length(source, destination_capacity);
    (void)memset(destination, 0, destination_capacity);
    (void)memcpy(destination, source, length);
    return true;
}

static bool ascii_equal_casefold(const char *left, const char *right)
{
    if (left == NULL || right == NULL) {
        return false;
    }
    while (*left != '\0' && *right != '\0') {
        char left_value = *left;
        char right_value = *right;
        if (left_value >= 'A' && left_value <= 'Z') {
            left_value = (char)(left_value - 'A' + 'a');
        }
        if (right_value >= 'A' && right_value <= 'Z') {
            right_value = (char)(right_value - 'A' + 'a');
        }
        if (left_value != right_value) {
            return false;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

static bool ascii_starts_with_casefold(const char *value, const char *prefix)
{
    if (value == NULL || prefix == NULL) {
        return false;
    }
    while (*prefix != '\0') {
        if (*value == '\0') {
            return false;
        }
        char value_character = *value;
        char prefix_character = *prefix;
        if (value_character >= 'A' && value_character <= 'Z') {
            value_character = (char)(value_character - 'A' + 'a');
        }
        if (prefix_character >= 'A' && prefix_character <= 'Z') {
            prefix_character = (char)(prefix_character - 'A' + 'a');
        }
        if (value_character != prefix_character) {
            return false;
        }
        ++value;
        ++prefix;
    }
    return true;
}

static bool media_key(const char *key)
{
    static const char *const keys[] = {
        "audio", "audio_bytes", "audio_data", "blob", "data_uri",
        "image", "image_bytes", "jpeg", "media", "media_bytes",
        "opus", "pcm", "raw_audio", "recording", "video",
    };
    for (size_t index = 0U; index < sizeof(keys) / sizeof(keys[0]); ++index) {
        if (ascii_equal_casefold(key, keys[index])) {
            return true;
        }
    }
    return false;
}

static bool media_event_type(const char *event_type)
{
    static const char *const event_types[] = {
        "audio", "audio_frame", "image", "rtc_media", "recording", "video",
    };
    for (size_t index = 0U;
         index < sizeof(event_types) / sizeof(event_types[0]);
         ++index) {
        if (ascii_equal_casefold(event_type, event_types[index])) {
            return true;
        }
    }
    return false;
}

static bool json_contains_media(const cJSON *node)
{
    const cJSON *child = NULL;
    cJSON_ArrayForEach(child, node) {
        if (child->string != NULL && media_key(child->string)) {
            return true;
        }
        if (cJSON_IsString(child) && child->valuestring != NULL &&
            (ascii_starts_with_casefold(child->valuestring, "data:audio/") ||
             ascii_starts_with_casefold(child->valuestring, "data:image/") ||
             ascii_starts_with_casefold(child->valuestring, "data:video/"))) {
            return true;
        }
        if ((cJSON_IsObject(child) || cJSON_IsArray(child)) &&
            json_contains_media(child)) {
            return true;
        }
    }
    return false;
}

static egolink_outbox_status_t validate_payload(
    const uint8_t *payload,
    size_t payload_length)
{
    if (payload == NULL || payload_length == 0U ||
        payload_length > EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES) {
        return EGOLINK_OUTBOX_INVALID_PAYLOAD;
    }
    if (memchr(payload, 0, payload_length) != NULL) {
        return EGOLINK_OUTBOX_INVALID_PAYLOAD;
    }

    const char *parse_end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(
        (const char *)payload, payload_length, &parse_end, 0);
    if (root == NULL || !cJSON_IsObject(root) || parse_end == NULL) {
        cJSON_Delete(root);
        return EGOLINK_OUTBOX_INVALID_PAYLOAD;
    }

    const char *payload_end = (const char *)payload + payload_length;
    while (parse_end < payload_end &&
           (*parse_end == ' ' || *parse_end == '\t' ||
            *parse_end == '\r' || *parse_end == '\n')) {
        ++parse_end;
    }
    if (parse_end != payload_end) {
        cJSON_Delete(root);
        return EGOLINK_OUTBOX_INVALID_PAYLOAD;
    }
    bool forbidden = json_contains_media(root);
    cJSON_Delete(root);
    return forbidden ? EGOLINK_OUTBOX_MEDIA_FORBIDDEN : EGOLINK_OUTBOX_OK;
}

static void hash_builder_begin(hash_builder_t *builder)
{
    mbedtls_sha256_init(&builder->context);
    builder->usable = mbedtls_sha256_starts(&builder->context, 0) == 0;
}

static void hash_builder_update(
    hash_builder_t *builder,
    const void *data,
    size_t length)
{
    if (builder->usable &&
        mbedtls_sha256_update(
            &builder->context, (const unsigned char *)data, length) != 0) {
        builder->usable = false;
    }
}

static void hash_builder_u8(hash_builder_t *builder, uint8_t value)
{
    hash_builder_update(builder, &value, sizeof(value));
}

static void hash_builder_u16(hash_builder_t *builder, uint16_t value)
{
    uint8_t encoded[2] = {
        (uint8_t)(value >> 8U),
        (uint8_t)value,
    };
    hash_builder_update(builder, encoded, sizeof(encoded));
}

static void hash_builder_u32(hash_builder_t *builder, uint32_t value)
{
    uint8_t encoded[4] = {
        (uint8_t)(value >> 24U),
        (uint8_t)(value >> 16U),
        (uint8_t)(value >> 8U),
        (uint8_t)value,
    };
    hash_builder_update(builder, encoded, sizeof(encoded));
}

static void hash_builder_u64(hash_builder_t *builder, uint64_t value)
{
    uint8_t encoded[8];
    for (size_t index = 0U; index < sizeof(encoded); ++index) {
        unsigned int shift = (unsigned int)((sizeof(encoded) - 1U - index) * 8U);
        encoded[index] = (uint8_t)(value >> shift);
    }
    hash_builder_update(builder, encoded, sizeof(encoded));
}

static void hash_builder_text(hash_builder_t *builder, const char *value)
{
    size_t length = strlen(value);
    hash_builder_u16(builder, (uint16_t)length);
    hash_builder_update(builder, value, length);
}

static bool hash_builder_finish(
    hash_builder_t *builder,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    bool usable = builder->usable &&
        mbedtls_sha256_finish(&builder->context, output) == 0;
    mbedtls_sha256_free(&builder->context);
    if (!usable) {
        (void)memset(output, 0, EGOLINK_OUTBOX_SHA256_BYTES);
    }
    return usable;
}

static bool sha256_bytes(
    const void *data,
    size_t length,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    return mbedtls_sha256(
        (const unsigned char *)data, length, output, 0) == 0;
}

static bool configuration_hash(
    const stored_config_t *configuration,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    static const char tag[] = "egolink-outbox-device-config-v1";
    hash_builder_t builder;
    hash_builder_begin(&builder);
    hash_builder_update(&builder, tag, sizeof(tag) - 1U);
    hash_builder_text(&builder, configuration->device_id);
    hash_builder_u16(&builder, configuration->max_records);
    hash_builder_u16(&builder, configuration->reserved_critical_records);
    hash_builder_u32(&builder, configuration->max_total_payload_bytes);
    hash_builder_u32(&builder, configuration->reserved_critical_payload_bytes);
    hash_builder_u16(&builder, configuration->max_payload_bytes);
    hash_builder_u16(&builder, configuration->tombstone_capacity);
    hash_builder_u64(&builder, configuration->base_retry_ms);
    hash_builder_u64(&builder, configuration->max_retry_ms);
    hash_builder_u16(&builder, (uint16_t)EGOLINK_OUTBOX_MAX_RECORDS);
    hash_builder_u16(&builder, (uint16_t)EGOLINK_OUTBOX_MAX_TOMBSTONES);
    hash_builder_u16(&builder, (uint16_t)EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES);
    return hash_builder_finish(&builder, output);
}

static bool identity_hash(
    const stored_config_t *configuration,
    const char *event_id,
    const char *event_type,
    uint8_t priority,
    uint8_t source_time_kind,
    uint64_t source_event_time_ms,
    uint64_t boot_count,
    const char *session_id,
    uint64_t source_sequence,
    const uint8_t payload_sha256[EGOLINK_OUTBOX_SHA256_BYTES],
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    static const char tag[] = "egolink-outbox-record-identity-v1";
    hash_builder_t builder;
    hash_builder_begin(&builder);
    hash_builder_update(&builder, tag, sizeof(tag) - 1U);
    hash_builder_text(&builder, configuration->device_id);
    hash_builder_text(&builder, event_id);
    hash_builder_text(&builder, event_type);
    hash_builder_u8(&builder, priority);
    hash_builder_u8(&builder, source_time_kind);
    hash_builder_u64(&builder, source_event_time_ms);
    hash_builder_u64(&builder, boot_count);
    hash_builder_text(&builder, session_id);
    hash_builder_u64(&builder, source_sequence);
    hash_builder_update(
        &builder, payload_sha256, EGOLINK_OUTBOX_SHA256_BYTES);
    return hash_builder_finish(&builder, output);
}

static bool record_identity_hash(
    const stored_config_t *configuration,
    const stored_record_t *record,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    return identity_hash(
        configuration,
        record->event_id,
        record->event_type,
        record->priority,
        record->source_time_kind,
        record->source_event_time_ms,
        record->boot_count,
        record->session_id,
        record->source_sequence,
        record->payload_sha256,
        output);
}

static bool attempt_token_hash(
    const stored_record_t *record,
    uint32_t attempt_count,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    static const char tag[] = "egolink-outbox-attempt-v1";
    hash_builder_t builder;
    hash_builder_begin(&builder);
    hash_builder_update(&builder, tag, sizeof(tag) - 1U);
    hash_builder_update(
        &builder, record->identity_sha256, EGOLINK_OUTBOX_SHA256_BYTES);
    hash_builder_u32(&builder, attempt_count);
    return hash_builder_finish(&builder, output);
}

static bool image_hash(
    const storage_image_t *image,
    uint8_t output[EGOLINK_OUTBOX_SHA256_BYTES])
{
    return sha256_bytes(image, offsetof(storage_image_t, storage_sha256), output);
}

static bool valid_priority(uint8_t priority)
{
    return priority <= (uint8_t)EGOLINK_OUTBOX_PRIORITY_CRITICAL;
}

static bool valid_source_time_kind(uint8_t kind)
{
    return kind <= (uint8_t)EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS;
}

static bool valid_failure_reason(egolink_outbox_failure_reason_t reason)
{
    return reason >= EGOLINK_OUTBOX_FAILURE_NONE &&
        reason <= EGOLINK_OUTBOX_FAILURE_TRANSPORT;
}

static bool event_requires_critical(const char *event_type)
{
    return strcmp(event_type, "manual_sos") == 0 ||
        strcmp(event_type, "sos") == 0;
}

static bool bytes_are_zero(const void *data, size_t length)
{
    const uint8_t *bytes = (const uint8_t *)data;
    for (size_t index = 0U; index < length; ++index) {
        if (bytes[index] != 0U) {
            return false;
        }
    }
    return true;
}

static bool config_is_valid(const egolink_outbox_config_t *configuration)
{
    if (configuration == NULL ||
        !safe_identifier(configuration->device_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        configuration->max_records == 0U ||
        configuration->max_records > EGOLINK_OUTBOX_MAX_RECORDS ||
        configuration->reserved_critical_records > configuration->max_records ||
        configuration->max_payload_bytes == 0U ||
        configuration->max_payload_bytes > EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES ||
        configuration->max_total_payload_bytes == 0U ||
        configuration->max_total_payload_bytes >
            (uint32_t)configuration->max_records *
                (uint32_t)configuration->max_payload_bytes ||
        configuration->max_payload_bytes >
            configuration->max_total_payload_bytes ||
        configuration->base_retry_ms == 0U ||
        configuration->max_retry_ms == 0U ||
        configuration->base_retry_ms > configuration->max_retry_ms ||
        configuration->tombstone_capacity == 0U ||
        configuration->tombstone_capacity > EGOLINK_OUTBOX_MAX_TOMBSTONES) {
        return false;
    }
    return true;
}

static bool make_stored_config(
    const egolink_outbox_config_t *source,
    stored_config_t *destination)
{
    (void)memset(destination, 0, sizeof(*destination));
    if (!config_is_valid(source) ||
        !copy_checked_text(
            destination->device_id,
            sizeof(destination->device_id),
            source->device_id)) {
        return false;
    }
    destination->max_records = source->max_records;
    destination->reserved_critical_records = source->reserved_critical_records;
    destination->max_total_payload_bytes = source->max_total_payload_bytes;
    destination->max_payload_bytes = source->max_payload_bytes;
    destination->base_retry_ms = source->base_retry_ms;
    destination->max_retry_ms = source->max_retry_ms;
    destination->tombstone_capacity = source->tombstone_capacity;
    uint64_t reserved_bytes =
        (uint64_t)source->reserved_critical_records * source->max_payload_bytes;
    if (reserved_bytes > source->max_total_payload_bytes) {
        reserved_bytes = source->max_total_payload_bytes;
    }
    destination->reserved_critical_payload_bytes = (uint32_t)reserved_bytes;
    return configuration_hash(destination, destination->configuration_sha256);
}

static bool same_configuration(
    const stored_config_t *left,
    const stored_config_t *right)
{
    return strcmp(left->device_id, right->device_id) == 0 &&
        left->max_records == right->max_records &&
        left->reserved_critical_records == right->reserved_critical_records &&
        left->max_total_payload_bytes == right->max_total_payload_bytes &&
        left->reserved_critical_payload_bytes ==
            right->reserved_critical_payload_bytes &&
        left->max_payload_bytes == right->max_payload_bytes &&
        left->tombstone_capacity == right->tombstone_capacity &&
        left->base_retry_ms == right->base_retry_ms &&
        left->max_retry_ms == right->max_retry_ms &&
        memcmp(
            left->configuration_sha256,
            right->configuration_sha256,
            EGOLINK_OUTBOX_SHA256_BYTES) == 0;
}

static egolink_outbox_status_t validate_stored_record(
    const stored_config_t *configuration,
    const stored_record_t *record)
{
    if (record->record_format_version != OUTBOX_RECORD_FORMAT_VERSION ||
        !valid_priority(record->priority) ||
        record->payload_kind != (uint8_t)EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON ||
        !valid_source_time_kind(record->source_time_kind) ||
        !safe_identifier(record->event_id, sizeof(record->event_id)) ||
        !safe_identifier(record->event_type, sizeof(record->event_type)) ||
        !safe_identifier(record->session_id, sizeof(record->session_id)) ||
        record->payload_length == 0U ||
        record->payload_length > configuration->max_payload_bytes ||
        record->payload_length > EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES ||
        record->reserved_zero != 0U || record->attempt_reserved_zero != 0U ||
        record->enqueue_runtime_epoch == 0U ||
        record->next_retry_runtime_epoch == 0U ||
        media_event_type(record->event_type) ||
        (event_requires_critical(record->event_type) &&
         record->priority != (uint8_t)EGOLINK_OUTBOX_PRIORITY_CRITICAL)) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    if (validate_payload(record->payload, record->payload_length) !=
        EGOLINK_OUTBOX_OK) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    uint8_t expected[EGOLINK_OUTBOX_SHA256_BYTES];
    if (!sha256_bytes(record->payload, record->payload_length, expected) ||
        memcmp(expected, record->payload_sha256, sizeof(expected)) != 0 ||
        !record_identity_hash(configuration, record, expected) ||
        memcmp(expected, record->identity_sha256, sizeof(expected)) != 0) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    if (!bytes_are_zero(
            &record->payload[record->payload_length],
            EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES - record->payload_length)) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }

    if (record->attempt_count == 0U) {
        if (record->last_attempt_result !=
                (uint8_t)EGOLINK_OUTBOX_ATTEMPT_NOT_ATTEMPTED ||
            record->send_state != (uint8_t)EGOLINK_OUTBOX_SEND_QUEUED ||
            record->next_retry_runtime_epoch !=
                record->enqueue_runtime_epoch ||
            record->next_retry_time_ms != record->enqueue_time_ms ||
            record->last_attempt_runtime_epoch != 0U ||
            record->last_attempt_time_ms != 0U ||
            record->last_result_runtime_epoch != 0U ||
            record->last_result_time_ms != 0U ||
            !bytes_are_zero(
                record->last_attempt_token,
                sizeof(record->last_attempt_token)) ||
            !bytes_are_zero(
                record->last_error_code,
                sizeof(record->last_error_code))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        return EGOLINK_OUTBOX_OK;
    }

    uint8_t token[EGOLINK_OUTBOX_SHA256_BYTES];
    if (record->last_attempt_runtime_epoch == 0U ||
        record->next_retry_runtime_epoch !=
            record->last_attempt_runtime_epoch ||
        record->next_retry_time_ms <= record->last_attempt_time_ms ||
        !attempt_token_hash(record, record->attempt_count, token) ||
        memcmp(token, record->last_attempt_token, sizeof(token)) != 0) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    switch ((egolink_outbox_attempt_result_t)record->last_attempt_result) {
    case EGOLINK_OUTBOX_ATTEMPT_PENDING:
        if (record->send_state !=
                (uint8_t)EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED ||
            record->last_result_runtime_epoch != 0U ||
            record->last_result_time_ms != 0U ||
            !bytes_are_zero(
                record->last_error_code,
                sizeof(record->last_error_code))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        break;
    case EGOLINK_OUTBOX_ATTEMPT_FAILED:
        if (record->send_state != (uint8_t)EGOLINK_OUTBOX_SEND_RETRY_WAIT ||
            record->last_result_runtime_epoch !=
                record->last_attempt_runtime_epoch ||
            record->last_result_time_ms < record->last_attempt_time_ms ||
            !safe_error_code(record->last_error_code)) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        break;
    case EGOLINK_OUTBOX_ATTEMPT_TRANSPORT_ACCEPTED:
        if (record->send_state !=
                (uint8_t)EGOLINK_OUTBOX_SEND_AWAITING_POSITIVE_ACK ||
            record->last_result_runtime_epoch !=
                record->last_attempt_runtime_epoch ||
            record->last_result_time_ms < record->last_attempt_time_ms ||
            !bytes_are_zero(
                record->last_error_code,
                sizeof(record->last_error_code))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        break;
    default:
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    return EGOLINK_OUTBOX_OK;
}

static bool valid_tombstone(const stored_tombstone_t *tombstone)
{
    return safe_identifier(tombstone->ack_id, sizeof(tombstone->ack_id)) &&
        safe_identifier(tombstone->event_id, sizeof(tombstone->event_id)) &&
        tombstone->recorded_runtime_epoch != 0U;
}

static egolink_outbox_status_t validate_image(
    const storage_image_t *image,
    const stored_config_t *expected_configuration)
{
    if (memcmp(image->magic, s_image_magic, sizeof(s_image_magic)) != 0 ||
        image->format_version != OUTBOX_IMAGE_FORMAT_VERSION ||
        image->image_size != sizeof(*image) || image->generation == 0U) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    uint8_t expected_hash[EGOLINK_OUTBOX_SHA256_BYTES];
    if (!image_hash(image, expected_hash)) {
        return EGOLINK_OUTBOX_CRYPTO_ERROR;
    }
    if (memcmp(
            expected_hash,
            image->storage_sha256,
            EGOLINK_OUTBOX_SHA256_BYTES) != 0) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    if (!same_configuration(
            &image->configuration, expected_configuration)) {
        return EGOLINK_OUTBOX_CONFIGURATION_MISMATCH;
    }
    if (image->record_count > image->configuration.max_records ||
        image->record_count > EGOLINK_OUTBOX_MAX_RECORDS ||
        image->tombstone_count > image->configuration.tombstone_capacity ||
        image->tombstone_count > EGOLINK_OUTBOX_MAX_TOMBSTONES ||
        !valid_failure_reason(image->last_failure.reason)) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }

    uint32_t total_payload_bytes = 0U;
    uint32_t noncritical_payload_bytes = 0U;
    uint16_t noncritical_count = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        const stored_record_t *record = &image->records[index];
        if (validate_stored_record(&image->configuration, record) !=
            EGOLINK_OUTBOX_OK) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        if (total_payload_bytes > UINT32_MAX - record->payload_length) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        total_payload_bytes += record->payload_length;
        if (record->priority != (uint8_t)EGOLINK_OUTBOX_PRIORITY_CRITICAL) {
            if (noncritical_payload_bytes > UINT32_MAX - record->payload_length) {
                return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
            }
            noncritical_payload_bytes += record->payload_length;
            ++noncritical_count;
        }
        for (uint16_t previous = 0U; previous < index; ++previous) {
            if (strcmp(record->event_id, image->records[previous].event_id) == 0) {
                return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
            }
        }
    }
    uint16_t noncritical_limit = (uint16_t)(
        image->configuration.max_records -
        image->configuration.reserved_critical_records);
    uint32_t noncritical_payload_limit =
        image->configuration.max_total_payload_bytes -
        image->configuration.reserved_critical_payload_bytes;
    if (total_payload_bytes > image->configuration.max_total_payload_bytes ||
        noncritical_count > noncritical_limit ||
        noncritical_payload_bytes > noncritical_payload_limit) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    for (uint16_t index = image->record_count;
         index < EGOLINK_OUTBOX_MAX_RECORDS;
         ++index) {
        if (!bytes_are_zero(&image->records[index], sizeof(image->records[index]))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
    }
    for (uint16_t index = 0U; index < image->tombstone_count; ++index) {
        if (!valid_tombstone(&image->tombstones[index])) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
        for (uint16_t previous = 0U; previous < index; ++previous) {
            if (strcmp(
                    image->tombstones[index].event_id,
                    image->tombstones[previous].event_id) == 0) {
                return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
            }
        }
        for (uint16_t record_index = 0U;
             record_index < image->record_count;
             ++record_index) {
            if (strcmp(
                    image->tombstones[index].event_id,
                    image->records[record_index].event_id) == 0) {
                return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
            }
        }
    }
    for (uint16_t index = image->tombstone_count;
         index < EGOLINK_OUTBOX_MAX_TOMBSTONES;
         ++index) {
        if (!bytes_are_zero(
                &image->tombstones[index], sizeof(image->tombstones[index]))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
    }
    if (image->last_failure.reason == EGOLINK_OUTBOX_FAILURE_NONE) {
        if (!bytes_are_zero(
                &image->last_failure, sizeof(image->last_failure))) {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
    } else if (!safe_identifier(
                   image->last_failure.event_id,
                   sizeof(image->last_failure.event_id)) ||
               !valid_priority((uint8_t)image->last_failure.priority) ||
               image->last_failure.runtime_epoch == 0U ||
               (image->last_failure.reason == EGOLINK_OUTBOX_FAILURE_TRANSPORT &&
                !safe_error_code(
                    image->last_failure.transport_error_code))) {
        return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
    }
    return EGOLINK_OUTBOX_OK;
}

static egolink_outbox_slot_state_t read_and_assess_slot(
    outbox_impl_t *implementation,
    uint8_t slot,
    storage_image_t *destination,
    const stored_config_t *expected_configuration)
{
    (void)memset(destination, 0, sizeof(*destination));
    size_t actual_length = 0U;
    egolink_outbox_storage_result_t result = implementation->storage.read_slot(
        implementation->storage.context,
        slot,
        destination,
        sizeof(*destination),
        &actual_length);
    if (result == EGOLINK_OUTBOX_STORAGE_NOT_FOUND) {
        return EGOLINK_OUTBOX_SLOT_NOT_FOUND;
    }
    if (result != EGOLINK_OUTBOX_STORAGE_OK) {
        return EGOLINK_OUTBOX_SLOT_IO_ERROR;
    }
    if (actual_length != sizeof(*destination)) {
        return EGOLINK_OUTBOX_SLOT_SIZE_MISMATCH;
    }
    egolink_outbox_status_t validation = validate_image(
        destination, expected_configuration);
    if (validation == EGOLINK_OUTBOX_OK) {
        return EGOLINK_OUTBOX_SLOT_VALID;
    }
    if (validation == EGOLINK_OUTBOX_CONFIGURATION_MISMATCH) {
        return EGOLINK_OUTBOX_SLOT_CONFIG_MISMATCH;
    }
    return EGOLINK_OUTBOX_SLOT_CORRUPT;
}

static bool refresh_image_hash(storage_image_t *image)
{
    (void)memset(image->storage_sha256, 0, sizeof(image->storage_sha256));
    return image_hash(image, image->storage_sha256);
}

static bool initialize_empty_image(
    storage_image_t *image,
    const stored_config_t *configuration)
{
    (void)memset(image, 0, sizeof(*image));
    (void)memcpy(image->magic, s_image_magic, sizeof(s_image_magic));
    image->format_version = OUTBOX_IMAGE_FORMAT_VERSION;
    image->image_size = (uint32_t)sizeof(*image);
    image->generation = UINT64_C(1);
    image->configuration = *configuration;
    return refresh_image_hash(image);
}

static bool slot_is_valid(egolink_outbox_slot_state_t state)
{
    return state == EGOLINK_OUTBOX_SLOT_VALID;
}

static uint64_t maximum_runtime_epoch(const storage_image_t *image)
{
    uint64_t maximum = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        const stored_record_t *record = &image->records[index];
        if (record->enqueue_runtime_epoch > maximum) {
            maximum = record->enqueue_runtime_epoch;
        }
        if (record->last_attempt_runtime_epoch > maximum) {
            maximum = record->last_attempt_runtime_epoch;
        }
        if (record->last_result_runtime_epoch > maximum) {
            maximum = record->last_result_runtime_epoch;
        }
    }
    for (uint16_t index = 0U; index < image->tombstone_count; ++index) {
        if (image->tombstones[index].recorded_runtime_epoch > maximum) {
            maximum = image->tombstones[index].recorded_runtime_epoch;
        }
    }
    if (image->last_failure.runtime_epoch > maximum) {
        maximum = image->last_failure.runtime_epoch;
    }
    return maximum;
}

static uint64_t maximum_action_time_for_epoch(
    const storage_image_t *image,
    uint64_t runtime_epoch)
{
    uint64_t maximum = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        const stored_record_t *record = &image->records[index];
        if (record->enqueue_runtime_epoch == runtime_epoch &&
            record->enqueue_time_ms > maximum) {
            maximum = record->enqueue_time_ms;
        }
        if (record->last_attempt_runtime_epoch == runtime_epoch &&
            record->last_attempt_time_ms > maximum) {
            maximum = record->last_attempt_time_ms;
        }
        if (record->last_result_runtime_epoch == runtime_epoch &&
            record->last_result_time_ms > maximum) {
            maximum = record->last_result_time_ms;
        }
    }
    for (uint16_t index = 0U; index < image->tombstone_count; ++index) {
        if (image->tombstones[index].recorded_runtime_epoch == runtime_epoch &&
            image->tombstones[index].recorded_time_ms > maximum) {
            maximum = image->tombstones[index].recorded_time_ms;
        }
    }
    if (image->last_failure.runtime_epoch == runtime_epoch &&
        image->last_failure.at_ms > maximum) {
        maximum = image->last_failure.at_ms;
    }
    return maximum;
}

static egolink_outbox_status_t validate_runtime_clock(
    const storage_image_t *image,
    uint64_t runtime_epoch,
    uint64_t now_ms)
{
    uint64_t maximum_epoch = maximum_runtime_epoch(image);
    if (runtime_epoch == 0U || runtime_epoch < maximum_epoch) {
        return EGOLINK_OUTBOX_TIME_ROLLBACK;
    }
    if (runtime_epoch == maximum_epoch &&
        now_ms < maximum_action_time_for_epoch(image, runtime_epoch)) {
        return EGOLINK_OUTBOX_TIME_ROLLBACK;
    }
    return EGOLINK_OUTBOX_OK;
}

static egolink_outbox_status_t require_ready(
    egolink_outbox_t *outbox,
    uint64_t now_ms,
    outbox_impl_t **implementation)
{
    if (outbox == NULL || implementation == NULL) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    outbox_impl_t *candidate = impl_of(outbox);
    if (!candidate->initialized) {
        return EGOLINK_OUTBOX_NOT_INITIALIZED;
    }
    if (candidate->fault_latched) {
        return EGOLINK_OUTBOX_FAULT_LATCHED;
    }
    if (now_ms < candidate->last_now_ms) {
        return EGOLINK_OUTBOX_TIME_ROLLBACK;
    }
    candidate->last_now_ms = now_ms;
    *implementation = candidate;
    return EGOLINK_OUTBOX_OK;
}

static void begin_mutation(outbox_impl_t *implementation)
{
    implementation->scratch = implementation->state;
}

static void abort_mutation(outbox_impl_t *implementation)
{
    implementation->state = implementation->scratch;
}

static egolink_outbox_status_t commit_mutation(
    outbox_impl_t *implementation)
{
    if (implementation->scratch.generation == UINT64_MAX) {
        abort_mutation(implementation);
        return EGOLINK_OUTBOX_GENERATION_OVERFLOW;
    }
    implementation->state.generation = implementation->scratch.generation + 1U;
    if (!refresh_image_hash(&implementation->state)) {
        abort_mutation(implementation);
        implementation->fault_latched = true;
        return EGOLINK_OUTBOX_CRYPTO_ERROR;
    }
    uint8_t target_slot = (uint8_t)(1U - implementation->active_slot);
    egolink_outbox_storage_result_t result = implementation->storage.write_slot(
        implementation->storage.context,
        target_slot,
        &implementation->state,
        sizeof(implementation->state));
    if (result != EGOLINK_OUTBOX_STORAGE_OK) {
        abort_mutation(implementation);
        implementation->fault_latched = true;
        if (implementation->volatile_storage_failure_count != UINT64_MAX) {
            ++implementation->volatile_storage_failure_count;
        }
        return EGOLINK_OUTBOX_STORAGE_ERROR;
    }
    implementation->active_slot = target_slot;
    return EGOLINK_OUTBOX_OK;
}

static bool can_increment(uint64_t value)
{
    return value != UINT64_MAX;
}

static stored_record_t *find_record(storage_image_t *image, const char *event_id)
{
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        if (strcmp(image->records[index].event_id, event_id) == 0) {
            return &image->records[index];
        }
    }
    return NULL;
}

static const stored_tombstone_t *find_tombstone(
    const storage_image_t *image,
    const char *event_id)
{
    for (uint16_t index = 0U; index < image->tombstone_count; ++index) {
        if (strcmp(image->tombstones[index].event_id, event_id) == 0) {
            return &image->tombstones[index];
        }
    }
    return NULL;
}

static uint32_t queued_payload_bytes(const storage_image_t *image)
{
    uint32_t total = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        total += image->records[index].payload_length;
    }
    return total;
}

static uint32_t noncritical_payload_bytes(const storage_image_t *image)
{
    uint32_t total = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        if (image->records[index].priority !=
            (uint8_t)EGOLINK_OUTBOX_PRIORITY_CRITICAL) {
            total += image->records[index].payload_length;
        }
    }
    return total;
}

static uint16_t noncritical_record_count(const storage_image_t *image)
{
    uint16_t count = 0U;
    for (uint16_t index = 0U; index < image->record_count; ++index) {
        if (image->records[index].priority !=
            (uint8_t)EGOLINK_OUTBOX_PRIORITY_CRITICAL) {
            ++count;
        }
    }
    return count;
}

static void set_last_failure(
    storage_image_t *image,
    egolink_outbox_failure_reason_t reason,
    const char *event_id,
    egolink_outbox_priority_t priority,
    uint64_t runtime_epoch,
    uint64_t now_ms,
    const char *transport_error_code)
{
    (void)memset(&image->last_failure, 0, sizeof(image->last_failure));
    image->last_failure.reason = reason;
    (void)copy_checked_text(
        image->last_failure.event_id,
        sizeof(image->last_failure.event_id),
        event_id);
    image->last_failure.priority = priority;
    image->last_failure.runtime_epoch = runtime_epoch;
    image->last_failure.at_ms = now_ms;
    if (transport_error_code != NULL) {
        size_t length = bounded_string_length(
            transport_error_code,
            sizeof(image->last_failure.transport_error_code));
        (void)memcpy(
            image->last_failure.transport_error_code,
            transport_error_code,
            length);
    }
}

static egolink_outbox_status_t persist_capacity_rejection(
    outbox_impl_t *implementation,
    const char *event_id,
    egolink_outbox_priority_t priority,
    uint64_t now_ms,
    egolink_outbox_failure_reason_t reason,
    bool payload_overflow)
{
    egolink_outbox_metrics_t *metrics = &implementation->state.metrics;
    if (!can_increment(metrics->rejected_enqueue_count) ||
        !can_increment(metrics->full_count) ||
        (payload_overflow && !can_increment(metrics->payload_overflow_count)) ||
        ((priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL ||
          reason == EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED ||
          reason ==
              EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED) &&
         !can_increment(metrics->priority_overflow_count))) {
        return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
    }
    begin_mutation(implementation);
    ++metrics->rejected_enqueue_count;
    ++metrics->full_count;
    if (payload_overflow) {
        ++metrics->payload_overflow_count;
    }
    if (priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL ||
        reason == EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED ||
        reason == EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED) {
        ++metrics->priority_overflow_count;
    }
    set_last_failure(
        &implementation->state,
        reason,
        event_id,
        priority,
        implementation->runtime_epoch,
        now_ms,
        NULL);
    return commit_mutation(implementation);
}

static void sha256_to_hex(
    const uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES],
    char output[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY])
{
    static const char hex[] = "0123456789abcdef";
    for (size_t index = 0U; index < EGOLINK_OUTBOX_SHA256_BYTES; ++index) {
        output[index * 2U] = hex[digest[index] >> 4U];
        output[index * 2U + 1U] = hex[digest[index] & UINT8_C(0x0f)];
    }
    output[EGOLINK_OUTBOX_SHA256_BYTES * 2U] = '\0';
}

static bool hex_to_sha256(
    const char *text,
    uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES])
{
    if (text == NULL ||
        bounded_string_length(text, EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) !=
            EGOLINK_OUTBOX_SHA256_BYTES * 2U) {
        return false;
    }
    for (size_t index = 0U; index < EGOLINK_OUTBOX_SHA256_BYTES; ++index) {
        char high_character = text[index * 2U];
        char low_character = text[index * 2U + 1U];
        uint8_t high;
        uint8_t low;
        if (high_character >= '0' && high_character <= '9') {
            high = (uint8_t)(high_character - '0');
        } else if (high_character >= 'a' && high_character <= 'f') {
            high = (uint8_t)(high_character - 'a' + 10);
        } else {
            return false;
        }
        if (low_character >= '0' && low_character <= '9') {
            low = (uint8_t)(low_character - '0');
        } else if (low_character >= 'a' && low_character <= 'f') {
            low = (uint8_t)(low_character - 'a' + 10);
        } else {
            return false;
        }
        digest[index] = (uint8_t)((high << 4U) | low);
    }
    return true;
}

static void fill_record_view(
    const stored_record_t *record,
    egolink_outbox_record_view_t *view)
{
    (void)memset(view, 0, sizeof(*view));
    (void)memcpy(view->event_id, record->event_id, sizeof(view->event_id));
    (void)memcpy(view->event_type, record->event_type, sizeof(view->event_type));
    view->priority = (egolink_outbox_priority_t)record->priority;
    view->source_time_kind =
        (egolink_outbox_source_time_kind_t)record->source_time_kind;
    view->source_event_time_ms = record->source_event_time_ms;
    view->boot_count = record->boot_count;
    (void)memcpy(view->session_id, record->session_id, sizeof(view->session_id));
    view->source_sequence = record->source_sequence;
    sha256_to_hex(record->payload_sha256, view->payload_sha256);
    view->payload_length = record->payload_length;
    sha256_to_hex(record->identity_sha256, view->identity_sha256);
    view->attempt_count = record->attempt_count;
    view->next_retry_runtime_epoch = record->next_retry_runtime_epoch;
    view->next_retry_time_ms = record->next_retry_time_ms;
    if (record->attempt_count != 0U) {
        sha256_to_hex(record->last_attempt_token, view->last_attempt_token);
    }
    view->last_attempt_result =
        (egolink_outbox_attempt_result_t)record->last_attempt_result;
    view->send_state = (egolink_outbox_send_state_t)record->send_state;
}

static uint64_t retry_delay_ms(
    const stored_config_t *configuration,
    uint32_t attempt_count)
{
    uint64_t delay = configuration->base_retry_ms;
    uint32_t doublings = attempt_count > 0U ? attempt_count - 1U : 0U;
    while (doublings > 0U && delay < configuration->max_retry_ms) {
        if (delay > configuration->max_retry_ms / 2U) {
            delay = configuration->max_retry_ms;
        } else {
            delay *= 2U;
        }
        --doublings;
    }
    return delay;
}

static bool record_is_due(
    const stored_record_t *record,
    uint64_t runtime_epoch,
    uint64_t now_ms)
{
    return record->next_retry_runtime_epoch < runtime_epoch ||
        (record->next_retry_runtime_epoch == runtime_epoch &&
         record->next_retry_time_ms <= now_ms);
}

static bool record_precedes(
    const stored_record_t *candidate,
    const stored_record_t *selected)
{
    if (candidate->priority != selected->priority) {
        return candidate->priority > selected->priority;
    }
    if (candidate->source_event_time_ms != selected->source_event_time_ms) {
        return candidate->source_event_time_ms < selected->source_event_time_ms;
    }
    if (candidate->enqueue_runtime_epoch != selected->enqueue_runtime_epoch) {
        return candidate->enqueue_runtime_epoch < selected->enqueue_runtime_epoch;
    }
    if (candidate->enqueue_time_ms != selected->enqueue_time_ms) {
        return candidate->enqueue_time_ms < selected->enqueue_time_ms;
    }
    return strcmp(candidate->event_id, selected->event_id) < 0;
}

size_t egolink_outbox_storage_image_bytes(void)
{
    return sizeof(storage_image_t);
}

egolink_outbox_status_t egolink_outbox_init(
    egolink_outbox_t *outbox,
    const egolink_outbox_config_t *config,
    const egolink_outbox_storage_t *storage,
    uint64_t runtime_epoch,
    uint64_t now_ms,
    egolink_outbox_init_report_t *report)
{
    if (report != NULL) {
        (void)memset(report, 0, sizeof(*report));
        report->selected_slot = OUTBOX_NO_SLOT;
        report->recovery_state = EGOLINK_OUTBOX_RECOVERY_FAILED;
        report->storage_image_bytes = sizeof(storage_image_t);
    }
    if (outbox == NULL || config == NULL || storage == NULL ||
        storage->read_slot == NULL || storage->write_slot == NULL ||
        report == NULL || runtime_epoch == 0U) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    (void)memset(outbox, 0, sizeof(*outbox));
    outbox_impl_t *implementation = impl_of(outbox);
    implementation->storage = *storage;

    stored_config_t expected_configuration;
    if (!make_stored_config(config, &expected_configuration)) {
        return EGOLINK_OUTBOX_INVALID_CONFIG;
    }
    report->slot_state[0] = read_and_assess_slot(
        implementation, 0U, &implementation->state, &expected_configuration);
    report->slot_state[1] = read_and_assess_slot(
        implementation, 1U, &implementation->scratch, &expected_configuration);

    if (report->slot_state[0] == EGOLINK_OUTBOX_SLOT_CONFIG_MISMATCH ||
        report->slot_state[1] == EGOLINK_OUTBOX_SLOT_CONFIG_MISMATCH) {
        return EGOLINK_OUTBOX_CONFIGURATION_MISMATCH;
    }

    bool valid_zero = slot_is_valid(report->slot_state[0]);
    bool valid_one = slot_is_valid(report->slot_state[1]);
    if (!valid_zero && !valid_one) {
        if (report->slot_state[0] == EGOLINK_OUTBOX_SLOT_NOT_FOUND &&
            report->slot_state[1] == EGOLINK_OUTBOX_SLOT_NOT_FOUND) {
            if (!initialize_empty_image(
                    &implementation->state, &expected_configuration)) {
                return EGOLINK_OUTBOX_CRYPTO_ERROR;
            }
            if (implementation->storage.write_slot(
                    implementation->storage.context,
                    0U,
                    &implementation->state,
                    sizeof(implementation->state)) !=
                EGOLINK_OUTBOX_STORAGE_OK) {
                return EGOLINK_OUTBOX_STORAGE_ERROR;
            }
            if (implementation->storage.write_slot(
                    implementation->storage.context,
                    1U,
                    &implementation->state,
                    sizeof(implementation->state)) !=
                EGOLINK_OUTBOX_STORAGE_OK) {
                return EGOLINK_OUTBOX_STORAGE_ERROR;
            }
            implementation->active_slot = 1U;
            implementation->recovery_state = EGOLINK_OUTBOX_RECOVERY_NEW_MIRRORS;
            report->slot_state[0] = EGOLINK_OUTBOX_SLOT_VALID;
            report->slot_state[1] = EGOLINK_OUTBOX_SLOT_VALID;
        } else if (report->slot_state[0] == EGOLINK_OUTBOX_SLOT_IO_ERROR ||
                   report->slot_state[1] == EGOLINK_OUTBOX_SLOT_IO_ERROR) {
            return EGOLINK_OUTBOX_STORAGE_ERROR;
        } else {
            return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
        }
    } else if (valid_zero && valid_one) {
        if (implementation->state.generation ==
            implementation->scratch.generation) {
            if (memcmp(
                    &implementation->state,
                    &implementation->scratch,
                    sizeof(implementation->state)) != 0) {
                return EGOLINK_OUTBOX_STORAGE_CORRUPTION;
            }
            implementation->active_slot = 1U;
            implementation->recovery_state =
                EGOLINK_OUTBOX_RECOVERY_EQUAL_MIRRORS;
        } else {
            uint64_t lower_generation;
            uint64_t higher_generation;
            if (implementation->scratch.generation >
                implementation->state.generation) {
                lower_generation = implementation->state.generation;
                higher_generation = implementation->scratch.generation;
                implementation->state = implementation->scratch;
                implementation->active_slot = 1U;
            } else {
                lower_generation = implementation->scratch.generation;
                higher_generation = implementation->state.generation;
                implementation->active_slot = 0U;
            }
            implementation->recovery_state =
                higher_generation - lower_generation == 1U
                ? EGOLINK_OUTBOX_RECOVERY_LATEST_GENERATION_SELECTED
                : EGOLINK_OUTBOX_RECOVERY_GENERATION_GAP;
        }
    } else {
        if (valid_one) {
            implementation->state = implementation->scratch;
            implementation->active_slot = 1U;
        } else {
            implementation->active_slot = 0U;
        }
        implementation->recovery_state =
            EGOLINK_OUTBOX_RECOVERY_SINGLE_VALID_SLOT;
    }

    egolink_outbox_status_t clock_status = validate_runtime_clock(
        &implementation->state, runtime_epoch, now_ms);
    if (clock_status != EGOLINK_OUTBOX_OK) {
        return clock_status;
    }
    implementation->runtime_epoch = runtime_epoch;
    implementation->last_now_ms = now_ms;
    implementation->initialized = true;
    report->recovery_state = implementation->recovery_state;
    report->selected_slot = (int8_t)implementation->active_slot;
    report->selected_generation = implementation->state.generation;
    return EGOLINK_OUTBOX_OK;
}

void egolink_outbox_deinit(egolink_outbox_t *outbox)
{
    if (outbox != NULL) {
        (void)memset(outbox, 0, sizeof(*outbox));
    }
}

egolink_outbox_status_t egolink_outbox_enqueue(
    egolink_outbox_t *outbox,
    const egolink_outbox_enqueue_request_t *request,
    uint64_t now_ms,
    egolink_outbox_record_view_t *record_view)
{
    if (record_view != NULL) {
        (void)memset(record_view, 0, sizeof(*record_view));
    }
    outbox_impl_t *implementation = NULL;
    egolink_outbox_status_t ready = require_ready(
        outbox, now_ms, &implementation);
    if (ready != EGOLINK_OUTBOX_OK) {
        return ready;
    }
    if (request == NULL || record_view == NULL ||
        !safe_identifier(request->event_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        !safe_identifier(
            request->event_type, EGOLINK_OUTBOX_EVENT_TYPE_CAPACITY) ||
        !safe_identifier(request->session_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        request->priority < EGOLINK_OUTBOX_PRIORITY_INFO ||
        request->priority > EGOLINK_OUTBOX_PRIORITY_CRITICAL ||
        request->source_time_kind < EGOLINK_OUTBOX_SOURCE_TIME_UTC_MS ||
        request->source_time_kind >
            EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS) {
        return EGOLINK_OUTBOX_INVALID_IDENTITY;
    }
    if (request->payload_kind != EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON ||
        media_event_type(request->event_type)) {
        return EGOLINK_OUTBOX_MEDIA_FORBIDDEN;
    }
    if (event_requires_critical(request->event_type) &&
        request->priority != EGOLINK_OUTBOX_PRIORITY_CRITICAL) {
        return EGOLINK_OUTBOX_INVALID_IDENTITY;
    }
    if (request->payload_length > implementation->state.configuration.max_payload_bytes ||
        request->payload_length > EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES) {
        egolink_outbox_status_t persisted = persist_capacity_rejection(
            implementation,
            request->event_id,
            request->priority,
            now_ms,
            EGOLINK_OUTBOX_FAILURE_PAYLOAD_EXCEEDS_RECORD_LIMIT,
            true);
        return persisted == EGOLINK_OUTBOX_OK
            ? EGOLINK_OUTBOX_PAYLOAD_OVERFLOW
            : persisted;
    }
    egolink_outbox_status_t payload_status = validate_payload(
        request->payload, request->payload_length);
    if (payload_status != EGOLINK_OUTBOX_OK) {
        return payload_status;
    }

    uint8_t payload_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
    uint8_t identity_sha256[EGOLINK_OUTBOX_SHA256_BYTES];
    if (!sha256_bytes(
            request->payload,
            request->payload_length,
            payload_sha256) ||
        !identity_hash(
            &implementation->state.configuration,
            request->event_id,
            request->event_type,
            (uint8_t)request->priority,
            (uint8_t)request->source_time_kind,
            request->source_event_time_ms,
            request->boot_count,
            request->session_id,
            request->source_sequence,
            payload_sha256,
            identity_sha256)) {
        return EGOLINK_OUTBOX_CRYPTO_ERROR;
    }

    stored_record_t *existing = find_record(
        &implementation->state, request->event_id);
    if (existing != NULL) {
        if (memcmp(
                existing->identity_sha256,
                identity_sha256,
                EGOLINK_OUTBOX_SHA256_BYTES) != 0) {
            return EGOLINK_OUTBOX_IDENTITY_CONFLICT;
        }
        if (!can_increment(
                implementation->state.metrics.duplicate_enqueue_count)) {
            return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
        }
        begin_mutation(implementation);
        ++implementation->state.metrics.duplicate_enqueue_count;
        egolink_outbox_status_t committed = commit_mutation(implementation);
        if (committed != EGOLINK_OUTBOX_OK) {
            return committed;
        }
        existing = find_record(&implementation->state, request->event_id);
        fill_record_view(existing, record_view);
        return EGOLINK_OUTBOX_DUPLICATE;
    }
    if (find_tombstone(&implementation->state, request->event_id) != NULL) {
        return EGOLINK_OUTBOX_IDENTITY_CONFLICT;
    }

    uint32_t total_payload = queued_payload_bytes(&implementation->state);
    uint32_t noncritical_payload = noncritical_payload_bytes(
        &implementation->state);
    uint32_t noncritical_payload_limit =
        implementation->state.configuration.max_total_payload_bytes -
        implementation->state.configuration.reserved_critical_payload_bytes;
    uint16_t noncritical_limit = (uint16_t)(
        implementation->state.configuration.max_records -
        implementation->state.configuration.reserved_critical_records);
    if (request->priority != EGOLINK_OUTBOX_PRIORITY_CRITICAL &&
        (uint32_t)request->payload_length >
            noncritical_payload_limit - noncritical_payload) {
        egolink_outbox_status_t persisted = persist_capacity_rejection(
            implementation,
            request->event_id,
            request->priority,
            now_ms,
            EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED,
            true);
        return persisted == EGOLINK_OUTBOX_OK
            ? EGOLINK_OUTBOX_PAYLOAD_OVERFLOW
            : persisted;
    }
    if ((uint32_t)request->payload_length >
        implementation->state.configuration.max_total_payload_bytes -
            total_payload) {
        egolink_outbox_status_t persisted = persist_capacity_rejection(
            implementation,
            request->event_id,
            request->priority,
            now_ms,
            EGOLINK_OUTBOX_FAILURE_TOTAL_PAYLOAD_CAPACITY_EXHAUSTED,
            true);
        return persisted == EGOLINK_OUTBOX_OK
            ? EGOLINK_OUTBOX_PAYLOAD_OVERFLOW
            : persisted;
    }
    if (request->priority != EGOLINK_OUTBOX_PRIORITY_CRITICAL &&
        noncritical_record_count(&implementation->state) >= noncritical_limit) {
        egolink_outbox_status_t persisted = persist_capacity_rejection(
            implementation,
            request->event_id,
            request->priority,
            now_ms,
            EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED,
            false);
        return persisted == EGOLINK_OUTBOX_OK ? EGOLINK_OUTBOX_FULL : persisted;
    }
    if (implementation->state.record_count >=
        implementation->state.configuration.max_records) {
        egolink_outbox_failure_reason_t reason =
            request->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL
            ? EGOLINK_OUTBOX_FAILURE_CRITICAL_CAPACITY_EXHAUSTED
            : EGOLINK_OUTBOX_FAILURE_RECORD_CAPACITY_EXHAUSTED;
        egolink_outbox_status_t persisted = persist_capacity_rejection(
            implementation,
            request->event_id,
            request->priority,
            now_ms,
            reason,
            false);
        return persisted == EGOLINK_OUTBOX_OK ? EGOLINK_OUTBOX_FULL : persisted;
    }
    if (!can_increment(implementation->state.metrics.enqueue_count)) {
        return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
    }

    begin_mutation(implementation);
    stored_record_t *proposed =
        &implementation->state.records[implementation->state.record_count];
    (void)memset(proposed, 0, sizeof(*proposed));
    proposed->record_format_version = OUTBOX_RECORD_FORMAT_VERSION;
    proposed->priority = (uint8_t)request->priority;
    proposed->payload_kind = (uint8_t)request->payload_kind;
    proposed->source_time_kind = (uint8_t)request->source_time_kind;
    proposed->send_state = (uint8_t)EGOLINK_OUTBOX_SEND_QUEUED;
    proposed->last_attempt_result =
        (uint8_t)EGOLINK_OUTBOX_ATTEMPT_NOT_ATTEMPTED;
    (void)copy_checked_text(
        proposed->event_id, sizeof(proposed->event_id), request->event_id);
    (void)copy_checked_text(
        proposed->event_type, sizeof(proposed->event_type), request->event_type);
    (void)copy_checked_text(
        proposed->session_id, sizeof(proposed->session_id), request->session_id);
    proposed->source_event_time_ms = request->source_event_time_ms;
    proposed->boot_count = request->boot_count;
    proposed->source_sequence = request->source_sequence;
    proposed->payload_length = (uint16_t)request->payload_length;
    (void)memcpy(proposed->payload, request->payload, request->payload_length);
    (void)memcpy(
        proposed->payload_sha256,
        payload_sha256,
        sizeof(proposed->payload_sha256));
    (void)memcpy(
        proposed->identity_sha256,
        identity_sha256,
        sizeof(proposed->identity_sha256));
    proposed->enqueue_runtime_epoch = implementation->runtime_epoch;
    proposed->enqueue_time_ms = now_ms;
    proposed->next_retry_runtime_epoch = implementation->runtime_epoch;
    proposed->next_retry_time_ms = now_ms;
    ++implementation->state.record_count;
    ++implementation->state.metrics.enqueue_count;
    (void)memset(
        &implementation->state.last_failure,
        0,
        sizeof(implementation->state.last_failure));
    egolink_outbox_status_t committed = commit_mutation(implementation);
    if (committed != EGOLINK_OUTBOX_OK) {
        return committed;
    }
    existing = find_record(&implementation->state, request->event_id);
    fill_record_view(existing, record_view);
    return EGOLINK_OUTBOX_OK;
}

egolink_outbox_status_t egolink_outbox_begin_send_attempt(
    egolink_outbox_t *outbox,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item)
{
    if (send_item != NULL) {
        (void)memset(send_item, 0, sizeof(*send_item));
    }
    outbox_impl_t *implementation = NULL;
    egolink_outbox_status_t ready = require_ready(
        outbox, now_ms, &implementation);
    if (ready != EGOLINK_OUTBOX_OK) {
        return ready;
    }
    if (send_item == NULL) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    stored_record_t *selected = NULL;
    for (uint16_t index = 0U; index < implementation->state.record_count; ++index) {
        stored_record_t *candidate = &implementation->state.records[index];
        if (record_is_due(candidate, implementation->runtime_epoch, now_ms) &&
            (selected == NULL || record_precedes(candidate, selected))) {
            selected = candidate;
        }
    }
    if (selected == NULL) {
        return EGOLINK_OUTBOX_NO_DUE_RECORD;
    }
    if (selected->attempt_count == UINT32_MAX ||
        !can_increment(implementation->state.metrics.send_attempt_count)) {
        return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
    }
    uint32_t next_attempt_count = selected->attempt_count + 1U;
    uint64_t delay = retry_delay_ms(
        &implementation->state.configuration, next_attempt_count);
    if (now_ms > UINT64_MAX - delay) {
        return EGOLINK_OUTBOX_TIME_OVERFLOW;
    }

    size_t selected_index = (size_t)(selected - implementation->state.records);
    begin_mutation(implementation);
    selected = &implementation->state.records[selected_index];
    selected->attempt_count = next_attempt_count;
    selected->last_attempt_runtime_epoch = implementation->runtime_epoch;
    selected->last_attempt_time_ms = now_ms;
    selected->next_retry_runtime_epoch = implementation->runtime_epoch;
    selected->next_retry_time_ms = now_ms + delay;
    selected->last_attempt_result = (uint8_t)EGOLINK_OUTBOX_ATTEMPT_PENDING;
    selected->send_state = (uint8_t)EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED;
    selected->last_result_runtime_epoch = 0U;
    selected->last_result_time_ms = 0U;
    (void)memset(selected->last_error_code, 0, sizeof(selected->last_error_code));
    if (!attempt_token_hash(
            selected,
            selected->attempt_count,
            selected->last_attempt_token)) {
        abort_mutation(implementation);
        return EGOLINK_OUTBOX_CRYPTO_ERROR;
    }
    ++implementation->state.metrics.send_attempt_count;
    egolink_outbox_status_t committed = commit_mutation(implementation);
    if (committed != EGOLINK_OUTBOX_OK) {
        return committed;
    }

    selected = &implementation->state.records[selected_index];
    fill_record_view(selected, &send_item->record);
    send_item->payload_length = selected->payload_length;
    (void)memcpy(
        send_item->payload, selected->payload, selected->payload_length);
    return EGOLINK_OUTBOX_OK;
}

egolink_outbox_status_t egolink_outbox_record_transport_result(
    egolink_outbox_t *outbox,
    const char *attempt_token,
    bool accepted_by_transport,
    const char *error_code,
    uint64_t now_ms)
{
    outbox_impl_t *implementation = NULL;
    egolink_outbox_status_t ready = require_ready(
        outbox, now_ms, &implementation);
    if (ready != EGOLINK_OUTBOX_OK) {
        return ready;
    }
    uint8_t token[EGOLINK_OUTBOX_SHA256_BYTES];
    if (!hex_to_sha256(attempt_token, token) ||
        (accepted_by_transport && error_code != NULL) ||
        (!accepted_by_transport && !safe_error_code(error_code))) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    stored_record_t *matching = NULL;
    for (uint16_t index = 0U; index < implementation->state.record_count; ++index) {
        if (memcmp(
                implementation->state.records[index].last_attempt_token,
                token,
                sizeof(token)) == 0 &&
            implementation->state.records[index].attempt_count != 0U) {
            matching = &implementation->state.records[index];
            break;
        }
    }
    if (matching == NULL) {
        return EGOLINK_OUTBOX_STALE_ATTEMPT;
    }
    egolink_outbox_attempt_result_t desired = accepted_by_transport
        ? EGOLINK_OUTBOX_ATTEMPT_TRANSPORT_ACCEPTED
        : EGOLINK_OUTBOX_ATTEMPT_FAILED;
    if (matching->last_attempt_result == (uint8_t)desired) {
        return EGOLINK_OUTBOX_DUPLICATE;
    }
    if (matching->last_attempt_result !=
        (uint8_t)EGOLINK_OUTBOX_ATTEMPT_PENDING) {
        return EGOLINK_OUTBOX_ATTEMPT_CONFLICT;
    }
    if ((accepted_by_transport &&
         !can_increment(implementation->state.metrics.transport_accept_count)) ||
        (!accepted_by_transport &&
         !can_increment(implementation->state.metrics.send_failure_count))) {
        return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
    }
    size_t matching_index = (size_t)(matching - implementation->state.records);
    begin_mutation(implementation);
    matching = &implementation->state.records[matching_index];
    matching->last_attempt_result = (uint8_t)desired;
    matching->last_result_runtime_epoch = implementation->runtime_epoch;
    matching->last_result_time_ms = now_ms;
    if (accepted_by_transport) {
        matching->send_state =
            (uint8_t)EGOLINK_OUTBOX_SEND_AWAITING_POSITIVE_ACK;
        ++implementation->state.metrics.transport_accept_count;
    } else {
        matching->send_state = (uint8_t)EGOLINK_OUTBOX_SEND_RETRY_WAIT;
        size_t error_length = bounded_string_length(
            error_code, sizeof(matching->last_error_code));
        (void)memcpy(matching->last_error_code, error_code, error_length);
        ++implementation->state.metrics.send_failure_count;
        set_last_failure(
            &implementation->state,
            EGOLINK_OUTBOX_FAILURE_TRANSPORT,
            matching->event_id,
            (egolink_outbox_priority_t)matching->priority,
            implementation->runtime_epoch,
            now_ms,
            error_code);
    }
    return commit_mutation(implementation);
}

static egolink_outbox_status_t persist_ack_rejection(
    outbox_impl_t *implementation,
    const char *event_id,
    egolink_outbox_priority_t priority,
    uint64_t now_ms,
    egolink_outbox_failure_reason_t reason,
    egolink_outbox_status_t result)
{
    if (!can_increment(implementation->state.metrics.ack_mismatch_count)) {
        return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
    }
    begin_mutation(implementation);
    ++implementation->state.metrics.ack_mismatch_count;
    set_last_failure(
        &implementation->state,
        reason,
        event_id,
        priority,
        implementation->runtime_epoch,
        now_ms,
        NULL);
    egolink_outbox_status_t committed = commit_mutation(implementation);
    return committed == EGOLINK_OUTBOX_OK ? result : committed;
}

egolink_outbox_status_t egolink_outbox_handle_ack(
    egolink_outbox_t *outbox,
    const egolink_outbox_ack_t *ack,
    uint64_t now_ms)
{
    outbox_impl_t *implementation = NULL;
    egolink_outbox_status_t ready = require_ready(
        outbox, now_ms, &implementation);
    if (ready != EGOLINK_OUTBOX_OK) {
        return ready;
    }
    uint8_t acknowledged_payload_hash[EGOLINK_OUTBOX_SHA256_BYTES];
    if (ack == NULL || ack->contract_version == NULL ||
        strcmp(ack->contract_version, EGOLINK_OUTBOX_ACK_CONTRACT_VERSION) != 0 ||
        !safe_identifier(ack->ack_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        !safe_identifier(ack->device_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        !safe_identifier(ack->event_id, EGOLINK_OUTBOX_ID_CAPACITY) ||
        !hex_to_sha256(ack->payload_sha256, acknowledged_payload_hash) ||
        (ack->status != EGOLINK_OUTBOX_ACK_ACCEPTED &&
         ack->status != EGOLINK_OUTBOX_ACK_REJECTED)) {
        return EGOLINK_OUTBOX_INVALID_ACK;
    }
    stored_record_t *record = find_record(
        &implementation->state, ack->event_id);
    const stored_tombstone_t *tombstone = find_tombstone(
        &implementation->state, ack->event_id);
    egolink_outbox_priority_t priority = record != NULL
        ? (egolink_outbox_priority_t)record->priority
        : EGOLINK_OUTBOX_PRIORITY_INFO;

    if (ack->status != EGOLINK_OUTBOX_ACK_ACCEPTED) {
        return persist_ack_rejection(
            implementation,
            ack->event_id,
            priority,
            now_ms,
            EGOLINK_OUTBOX_FAILURE_NEGATIVE_ACK,
            EGOLINK_OUTBOX_NEGATIVE_ACK);
    }
    if (record != NULL) {
        bool identity_matches =
            strcmp(
                ack->device_id,
                implementation->state.configuration.device_id) == 0 &&
            strcmp(ack->event_id, record->event_id) == 0 &&
            memcmp(
                acknowledged_payload_hash,
                record->payload_sha256,
                sizeof(acknowledged_payload_hash)) == 0;
        if (!identity_matches) {
            return persist_ack_rejection(
                implementation,
                ack->event_id,
                priority,
                now_ms,
                EGOLINK_OUTBOX_FAILURE_ACK_IDENTITY_MISMATCH,
                EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH);
        }
        bool prune_tombstone = implementation->state.tombstone_count >=
            implementation->state.configuration.tombstone_capacity;
        if (!can_increment(implementation->state.metrics.ack_delete_count) ||
            (prune_tombstone &&
             !can_increment(
                 implementation->state.metrics.tombstone_pruned_count))) {
            return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
        }
        size_t record_index = (size_t)(record - implementation->state.records);
        begin_mutation(implementation);
        if (record_index + 1U < implementation->state.record_count) {
            (void)memmove(
                &implementation->state.records[record_index],
                &implementation->state.records[record_index + 1U],
                ((size_t)implementation->state.record_count - record_index - 1U) *
                    sizeof(implementation->state.records[0]));
        }
        --implementation->state.record_count;
        (void)memset(
            &implementation->state.records[implementation->state.record_count],
            0,
            sizeof(implementation->state.records[0]));
        if (prune_tombstone) {
            if (implementation->state.tombstone_count > 1U) {
                (void)memmove(
                    &implementation->state.tombstones[0],
                    &implementation->state.tombstones[1],
                    ((size_t)implementation->state.tombstone_count - 1U) *
                        sizeof(implementation->state.tombstones[0]));
            }
            --implementation->state.tombstone_count;
            ++implementation->state.metrics.tombstone_pruned_count;
        }
        stored_tombstone_t *new_tombstone =
            &implementation->state.tombstones[
                implementation->state.tombstone_count];
        (void)memset(new_tombstone, 0, sizeof(*new_tombstone));
        (void)copy_checked_text(
            new_tombstone->ack_id,
            sizeof(new_tombstone->ack_id),
            ack->ack_id);
        (void)copy_checked_text(
            new_tombstone->event_id,
            sizeof(new_tombstone->event_id),
            ack->event_id);
        (void)memcpy(
            new_tombstone->payload_sha256,
            acknowledged_payload_hash,
            sizeof(new_tombstone->payload_sha256));
        new_tombstone->ack_time_ms = ack->ack_time_ms;
        new_tombstone->recorded_runtime_epoch = implementation->runtime_epoch;
        new_tombstone->recorded_time_ms = now_ms;
        ++implementation->state.tombstone_count;
        ++implementation->state.metrics.ack_delete_count;
        (void)memset(
            &implementation->state.last_failure,
            0,
            sizeof(implementation->state.last_failure));
        egolink_outbox_status_t committed = commit_mutation(implementation);
        return committed == EGOLINK_OUTBOX_OK
            ? EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK
            : committed;
    }

    if (tombstone != NULL &&
        strcmp(
            ack->device_id, implementation->state.configuration.device_id) == 0 &&
        memcmp(
            acknowledged_payload_hash,
            tombstone->payload_sha256,
            sizeof(acknowledged_payload_hash)) == 0) {
        if (!can_increment(implementation->state.metrics.duplicate_ack_count)) {
            return EGOLINK_OUTBOX_COUNTER_OVERFLOW;
        }
        begin_mutation(implementation);
        ++implementation->state.metrics.duplicate_ack_count;
        egolink_outbox_status_t committed = commit_mutation(implementation);
        return committed == EGOLINK_OUTBOX_OK
            ? EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK
            : committed;
    }
    return persist_ack_rejection(
        implementation,
        ack->event_id,
        priority,
        now_ms,
        tombstone != NULL
            ? EGOLINK_OUTBOX_FAILURE_ACK_IDENTITY_MISMATCH
            : EGOLINK_OUTBOX_FAILURE_ACK_STALE_OR_UNKNOWN,
        tombstone != NULL
            ? EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH
            : EGOLINK_OUTBOX_STALE_OR_UNKNOWN_ACK);
}

egolink_outbox_status_t egolink_outbox_snapshot(
    egolink_outbox_t *outbox,
    uint64_t now_ms,
    egolink_outbox_snapshot_t *snapshot)
{
    if (outbox == NULL || snapshot == NULL) {
        return EGOLINK_OUTBOX_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    outbox_impl_t *implementation = impl_of(outbox);
    if (!implementation->initialized) {
        return EGOLINK_OUTBOX_NOT_INITIALIZED;
    }
    if (now_ms < implementation->last_now_ms) {
        return EGOLINK_OUTBOX_TIME_ROLLBACK;
    }
    implementation->last_now_ms = now_ms;
    snapshot->initialized = true;
    snapshot->fault_latched = implementation->fault_latched;
    snapshot->storage_backend = "injected_atomic_dual_slot_blob";
    snapshot->durability_claim = "adapter_unverified_not_product_nvs";
    snapshot->generation = implementation->state.generation;
    snapshot->active_slot = implementation->active_slot;
    snapshot->recovery_state = implementation->recovery_state;
    snapshot->queued_count = implementation->state.record_count;
    snapshot->max_records = implementation->state.configuration.max_records;
    snapshot->reserved_critical_records =
        implementation->state.configuration.reserved_critical_records;
    snapshot->payload_bytes = queued_payload_bytes(&implementation->state);
    snapshot->max_total_payload_bytes =
        implementation->state.configuration.max_total_payload_bytes;
    snapshot->reserved_critical_payload_bytes =
        implementation->state.configuration.reserved_critical_payload_bytes;
    snapshot->ack_tombstone_count = implementation->state.tombstone_count;
    snapshot->metrics = implementation->state.metrics;
    if (UINT64_MAX - snapshot->metrics.storage_failure_count >=
        implementation->volatile_storage_failure_count) {
        snapshot->metrics.storage_failure_count +=
            implementation->volatile_storage_failure_count;
    } else {
        snapshot->metrics.storage_failure_count = UINT64_MAX;
    }
    snapshot->last_failure = implementation->state.last_failure;

    bool all_age_comparable = implementation->state.record_count > 0U;
    uint64_t oldest_enqueue_time = UINT64_MAX;
    for (uint16_t index = 0U; index < implementation->state.record_count; ++index) {
        const stored_record_t *record = &implementation->state.records[index];
        ++snapshot->queued_by_priority[record->priority];
        if (record->send_state ==
            (uint8_t)EGOLINK_OUTBOX_SEND_AWAITING_POSITIVE_ACK) {
            ++snapshot->awaiting_positive_ack_count;
        }
        if (record->enqueue_runtime_epoch != implementation->runtime_epoch ||
            record->enqueue_time_ms > now_ms) {
            all_age_comparable = false;
        } else if (record->enqueue_time_ms < oldest_enqueue_time) {
            oldest_enqueue_time = record->enqueue_time_ms;
        }
        uint64_t retry_epoch = record->next_retry_runtime_epoch;
        uint64_t retry_time = record->next_retry_time_ms;
        if (retry_epoch < implementation->runtime_epoch) {
            retry_epoch = implementation->runtime_epoch;
            retry_time = now_ms;
        }
        if (!snapshot->next_retry_available ||
            retry_epoch < snapshot->next_retry_runtime_epoch ||
            (retry_epoch == snapshot->next_retry_runtime_epoch &&
             retry_time < snapshot->next_retry_time_ms)) {
            snapshot->next_retry_available = true;
            snapshot->next_retry_runtime_epoch = retry_epoch;
            snapshot->next_retry_time_ms = retry_time;
        }
        fill_record_view(record, &snapshot->records[index]);
    }
    snapshot->oldest_age_available = all_age_comparable;
    if (all_age_comparable) {
        snapshot->oldest_age_ms = now_ms - oldest_enqueue_time;
    }
    return EGOLINK_OUTBOX_OK;
}

const char *egolink_outbox_status_name(egolink_outbox_status_t status)
{
    switch (status) {
    case EGOLINK_OUTBOX_OK: return "ok";
    case EGOLINK_OUTBOX_NO_DUE_RECORD: return "no_due_record";
    case EGOLINK_OUTBOX_DUPLICATE: return "duplicate";
    case EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK:
        return "deleted_after_positive_ack";
    case EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK:
        return "duplicate_positive_ack";
    case EGOLINK_OUTBOX_NEGATIVE_ACK: return "negative_ack";
    case EGOLINK_OUTBOX_STALE_OR_UNKNOWN_ACK: return "stale_or_unknown_ack";
    case EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH: return "ack_identity_mismatch";
    case EGOLINK_OUTBOX_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_OUTBOX_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_OUTBOX_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_OUTBOX_FAULT_LATCHED: return "fault_latched";
    case EGOLINK_OUTBOX_INVALID_IDENTITY: return "invalid_identity";
    case EGOLINK_OUTBOX_INVALID_PAYLOAD: return "invalid_payload";
    case EGOLINK_OUTBOX_MEDIA_FORBIDDEN: return "media_forbidden";
    case EGOLINK_OUTBOX_IDENTITY_CONFLICT: return "identity_conflict";
    case EGOLINK_OUTBOX_FULL: return "full";
    case EGOLINK_OUTBOX_PAYLOAD_OVERFLOW: return "payload_overflow";
    case EGOLINK_OUTBOX_COUNTER_OVERFLOW: return "counter_overflow";
    case EGOLINK_OUTBOX_TIME_ROLLBACK: return "time_rollback";
    case EGOLINK_OUTBOX_TIME_OVERFLOW: return "time_overflow";
    case EGOLINK_OUTBOX_GENERATION_OVERFLOW: return "generation_overflow";
    case EGOLINK_OUTBOX_STORAGE_ERROR: return "storage_error";
    case EGOLINK_OUTBOX_STORAGE_CORRUPTION: return "storage_corruption";
    case EGOLINK_OUTBOX_CONFIGURATION_MISMATCH:
        return "configuration_mismatch";
    case EGOLINK_OUTBOX_INVALID_ACK: return "invalid_ack";
    case EGOLINK_OUTBOX_STALE_ATTEMPT: return "stale_attempt";
    case EGOLINK_OUTBOX_ATTEMPT_CONFLICT: return "attempt_conflict";
    case EGOLINK_OUTBOX_CRYPTO_ERROR: return "crypto_error";
    default: return "unknown";
    }
}

const char *egolink_outbox_slot_state_name(egolink_outbox_slot_state_t state)
{
    switch (state) {
    case EGOLINK_OUTBOX_SLOT_NOT_READ: return "not_read";
    case EGOLINK_OUTBOX_SLOT_NOT_FOUND: return "not_found";
    case EGOLINK_OUTBOX_SLOT_VALID: return "valid";
    case EGOLINK_OUTBOX_SLOT_IO_ERROR: return "io_error";
    case EGOLINK_OUTBOX_SLOT_SIZE_MISMATCH: return "size_mismatch";
    case EGOLINK_OUTBOX_SLOT_CORRUPT: return "corrupt";
    case EGOLINK_OUTBOX_SLOT_CONFIG_MISMATCH: return "config_mismatch";
    default: return "unknown";
    }
}

const char *egolink_outbox_recovery_state_name(
    egolink_outbox_recovery_state_t state)
{
    switch (state) {
    case EGOLINK_OUTBOX_RECOVERY_NONE: return "none";
    case EGOLINK_OUTBOX_RECOVERY_NEW_MIRRORS: return "new_mirrors";
    case EGOLINK_OUTBOX_RECOVERY_EQUAL_MIRRORS: return "equal_mirrors";
    case EGOLINK_OUTBOX_RECOVERY_LATEST_GENERATION_SELECTED:
        return "latest_generation_selected";
    case EGOLINK_OUTBOX_RECOVERY_GENERATION_GAP: return "generation_gap";
    case EGOLINK_OUTBOX_RECOVERY_SINGLE_VALID_SLOT:
        return "single_valid_slot";
    case EGOLINK_OUTBOX_RECOVERY_FAILED: return "failed";
    default: return "unknown";
    }
}

const char *egolink_outbox_failure_reason_name(
    egolink_outbox_failure_reason_t reason)
{
    switch (reason) {
    case EGOLINK_OUTBOX_FAILURE_NONE: return "none";
    case EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED:
        return "critical_reserve_protected";
    case EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED:
        return "critical_payload_reserve_protected";
    case EGOLINK_OUTBOX_FAILURE_RECORD_CAPACITY_EXHAUSTED:
        return "record_capacity_exhausted";
    case EGOLINK_OUTBOX_FAILURE_CRITICAL_CAPACITY_EXHAUSTED:
        return "critical_capacity_exhausted";
    case EGOLINK_OUTBOX_FAILURE_PAYLOAD_EXCEEDS_RECORD_LIMIT:
        return "payload_exceeds_record_limit";
    case EGOLINK_OUTBOX_FAILURE_TOTAL_PAYLOAD_CAPACITY_EXHAUSTED:
        return "total_payload_capacity_exhausted";
    case EGOLINK_OUTBOX_FAILURE_NEGATIVE_ACK: return "negative_ack";
    case EGOLINK_OUTBOX_FAILURE_ACK_IDENTITY_MISMATCH:
        return "ack_identity_mismatch";
    case EGOLINK_OUTBOX_FAILURE_ACK_STALE_OR_UNKNOWN:
        return "ack_stale_or_unknown";
    case EGOLINK_OUTBOX_FAILURE_TRANSPORT: return "transport_failure";
    default: return "unknown";
    }
}
