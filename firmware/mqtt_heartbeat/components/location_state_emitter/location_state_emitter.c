#include "location_state_emitter.h"

#include <stdbool.h>
#include <string.h>

#include "cJSON.h"

typedef struct {
    char *data;
    size_t capacity;
    size_t length;
    bool overflow;
} json_writer_t;

static size_t bounded_output_capacity(size_t capacity)
{
    const size_t maximum = EGOLINK_LOCATION_STATE_ENVELOPE_MAX_BYTES + 1U;
    return capacity < maximum ? capacity : maximum;
}

static void clear_output(char *output, size_t capacity)
{
    volatile unsigned char *cursor = (volatile unsigned char *)output;
    const size_t clear_length = bounded_output_capacity(capacity);
    for (size_t index = 0; cursor != NULL && index < clear_length; ++index) {
        cursor[index] = 0U;
    }
}

static bool writer_append(json_writer_t *writer, const char *value, size_t length)
{
    if (writer->overflow) {
        return false;
    }
    if (length > writer->capacity - writer->length) {
        writer->overflow = true;
        return false;
    }
    if (length > 0U) {
        memcpy(writer->data + writer->length, value, length);
        writer->length += length;
    }
    return true;
}

static bool writer_literal(json_writer_t *writer, const char *value)
{
    return writer_append(writer, value, strlen(value));
}

static bool writer_u64(json_writer_t *writer, uint64_t value)
{
    char digits[20];
    size_t count = 0U;
    do {
        digits[count++] = (char)('0' + (value % 10U));
        value /= 10U;
    } while (value != 0U);
    while (count > 0U) {
        --count;
        if (!writer_append(writer, &digits[count], 1U)) {
            return false;
        }
    }
    return true;
}

static bool valid_utf8(const char *data, size_t length)
{
    size_t index = 0U;
    while (index < length) {
        const unsigned char first = (unsigned char)data[index];
        if (first <= 0x7fU) {
            ++index;
            continue;
        }
        size_t continuation_count = 0U;
        uint32_t code_point = 0U;
        uint32_t minimum = 0U;
        if (first >= 0xc2U && first <= 0xdfU) {
            continuation_count = 1U;
            code_point = first & 0x1fU;
            minimum = 0x80U;
        } else if (first >= 0xe0U && first <= 0xefU) {
            continuation_count = 2U;
            code_point = first & 0x0fU;
            minimum = 0x800U;
        } else if (first >= 0xf0U && first <= 0xf4U) {
            continuation_count = 3U;
            code_point = first & 0x07U;
            minimum = 0x10000U;
        } else {
            return false;
        }
        if (continuation_count > length - index - 1U) {
            return false;
        }
        for (size_t offset = 1U; offset <= continuation_count; ++offset) {
            const unsigned char next = (unsigned char)data[index + offset];
            if ((next & 0xc0U) != 0x80U) {
                return false;
            }
            code_point = (code_point << 6U) | (next & 0x3fU);
        }
        if (code_point < minimum || code_point > 0x10ffffU ||
            (code_point >= 0xd800U && code_point <= 0xdfffU)) {
            return false;
        }
        index += continuation_count + 1U;
    }
    return true;
}

static bool valid_text(egolink_location_state_text_t value, size_t maximum)
{
    return value.data != NULL && value.length > 0U && value.length <= maximum &&
           valid_utf8(value.data, value.length);
}

static bool safe_id_first_byte(unsigned char byte)
{
    return (byte >= (unsigned char)'A' && byte <= (unsigned char)'Z') ||
           (byte >= (unsigned char)'a' && byte <= (unsigned char)'z') ||
           (byte >= (unsigned char)'0' && byte <= (unsigned char)'9');
}

static bool safe_id_byte(unsigned char byte)
{
    return safe_id_first_byte(byte) || byte == (unsigned char)'.' ||
           byte == (unsigned char)'_' || byte == (unsigned char)':' ||
           byte == (unsigned char)'@' || byte == (unsigned char)'-';
}

static bool valid_outbox_id(egolink_location_state_text_t value)
{
    if (value.data == NULL || value.length == 0U ||
        value.length > EGOLINK_LOCATION_STATE_OUTBOX_ID_MAX_BYTES ||
        !safe_id_first_byte((unsigned char)value.data[0])) {
        return false;
    }
    for (size_t index = 1U; index < value.length; ++index) {
        if (!safe_id_byte((unsigned char)value.data[index])) {
            return false;
        }
    }
    return true;
}

static bool text_equals_literal(
    egolink_location_state_text_t value, const char *literal)
{
    const size_t literal_length = strlen(literal);
    return value.data != NULL && value.length == literal_length &&
           memcmp(value.data, literal, literal_length) == 0;
}

static bool writer_json_string(
    json_writer_t *writer, egolink_location_state_text_t value)
{
    static const char hex[] = "0123456789abcdef";
    if (!writer_literal(writer, "\"")) {
        return false;
    }
    for (size_t index = 0U; index < value.length; ++index) {
        const unsigned char byte = (unsigned char)value.data[index];
        if (byte == '"' || byte == '\\') {
            const char escaped[2] = {'\\', (char)byte};
            if (!writer_append(writer, escaped, sizeof(escaped))) {
                return false;
            }
        } else if (byte < 0x20U) {
            const char escaped[6] = {
                '\\', 'u', '0', '0', hex[byte >> 4U], hex[byte & 0x0fU]};
            if (!writer_append(writer, escaped, sizeof(escaped))) {
                return false;
            }
        } else if (!writer_append(writer, (const char *)&value.data[index], 1U)) {
            return false;
        }
    }
    return writer_literal(writer, "\"");
}

static bool compact_json_object_bytes(egolink_location_state_text_t value)
{
    if (!valid_text(value, EGOLINK_LOCATION_STATE_JSON_MAX_BYTES) ||
        value.data[0] != '{' || value.data[value.length - 1U] != '}') {
        return false;
    }
    bool in_string = false;
    bool escaped = false;
    for (size_t index = 0U; index < value.length; ++index) {
        const unsigned char byte = (unsigned char)value.data[index];
        if (in_string) {
            if (byte < 0x20U) {
                return false;
            }
            if (escaped) {
                escaped = false;
            } else if (byte == '\\') {
                escaped = true;
            } else if (byte == '"') {
                in_string = false;
            }
        } else if (byte == '"') {
            in_string = true;
        } else if (byte == ' ' || byte == '\t' || byte == '\r' || byte == '\n') {
            return false;
        }
    }
    return !in_string && !escaped;
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

static bool top_level_u64_member(
    egolink_location_state_text_t object,
    const char *member_name,
    uint64_t *value)
{
    const size_t member_length = strlen(member_name);
    size_t index = 0U;
    unsigned int object_depth = 0U;
    unsigned int array_depth = 0U;
    while (index < object.length) {
        const char byte = object.data[index];
        if (byte == '{') {
            ++object_depth;
            ++index;
            continue;
        }
        if (byte == '}') {
            if (object_depth == 0U) {
                return false;
            }
            --object_depth;
            ++index;
            continue;
        }
        if (byte == '[') {
            ++array_depth;
            ++index;
            continue;
        }
        if (byte == ']') {
            if (array_depth == 0U) {
                return false;
            }
            --array_depth;
            ++index;
            continue;
        }
        if (byte != '"') {
            ++index;
            continue;
        }

        const size_t quoted_start = ++index;
        bool escaped = false;
        while (index < object.length) {
            const char quoted_byte = object.data[index];
            if (escaped) {
                escaped = false;
            } else if (quoted_byte == '\\') {
                escaped = true;
            } else if (quoted_byte == '"') {
                break;
            }
            ++index;
        }
        if (index >= object.length) {
            return false;
        }
        const size_t quoted_length = index - quoted_start;
        ++index;
        if (object_depth != 1U || array_depth != 0U ||
            index >= object.length || object.data[index] != ':' ||
            quoted_length != member_length ||
            memcmp(object.data + quoted_start, member_name, member_length) != 0) {
            continue;
        }

        ++index;
        const size_t digit_start = index;
        uint64_t parsed = 0U;
        while (index < object.length && object.data[index] >= '0' &&
               object.data[index] <= '9') {
            const uint64_t digit = (uint64_t)(object.data[index] - '0');
            if (parsed > (UINT64_MAX - digit) / 10U) {
                return false;
            }
            parsed = parsed * 10U + digit;
            ++index;
        }
        if (index == digit_start ||
            (index - digit_start > 1U && object.data[digit_start] == '0') ||
            index >= object.length ||
            (object.data[index] != ',' && object.data[index] != '}')) {
            return false;
        }
        *value = parsed;
        return true;
    }
    return false;
}

static bool validate_location_state(
    egolink_location_state_text_t state_json, uint64_t event_time_ms)
{
    if (!compact_json_object_bytes(state_json)) {
        return false;
    }

    const char *parse_end = NULL;
    cJSON *state = cJSON_ParseWithLengthOpts(
        state_json.data, state_json.length, &parse_end, false);
    if (state == NULL || !cJSON_IsObject(state) ||
        parse_end != state_json.data + state_json.length) {
        cJSON_Delete(state);
        return false;
    }

    const size_t contract_count = object_member_count(state, "contract_version");
    const size_t event_time_count = object_member_count(state, "event_time_ms");
    const size_t receive_time_count = object_member_count(state, "server_receive_time_ms");
    const cJSON *contract = cJSON_GetObjectItemCaseSensitive(state, "contract_version");
    const cJSON *state_time = cJSON_GetObjectItemCaseSensitive(state, "event_time_ms");
    uint64_t parsed_state_time = 0U;
    const bool integer_token = top_level_u64_member(
        state_json, "event_time_ms", &parsed_state_time);
    const bool valid = contract_count == 1U && event_time_count == 1U &&
                       receive_time_count == 0U && cJSON_IsString(contract) &&
                       contract->valuestring != NULL &&
                       strcmp(contract->valuestring,
                              EGOLINK_LOCATION_ENGINE_CONTRACT_VERSION) == 0 &&
                       cJSON_IsNumber(state_time) && integer_token &&
                       parsed_state_time == event_time_ms;
    cJSON_Delete(state);
    return valid;
}

static const char *event_time_source_name(
    egolink_location_event_time_source_t source)
{
    switch (source) {
    case EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS:
        return "timestamp_utc_ns";
    case EGOLINK_LOCATION_TIME_GNSS_SOURCE_UTC_NS:
        return "gnss_source_utc_ns";
    case EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS:
        return "timestamp_monotonic_ns";
    default:
        return NULL;
    }
}

static bool valid_policy_identity(const egolink_location_policy_identity_t *identity)
{
    if (identity == NULL ||
        !text_equals_literal(identity->contract_version,
                             EGOLINK_SENSOR_POLICY_CONTRACT_VERSION) ||
        !text_equals_literal(identity->semantic_validation,
                             EGOLINK_SENSOR_POLICY_SEMANTIC_VERSION) ||
        !text_equals_literal(identity->config_id,
                             EGOLINK_SENSOR_POLICY_CONFIG_ID) ||
        !text_equals_literal(identity->config_hash,
                             EGOLINK_SENSOR_POLICY_CONFIG_HASH)) {
        return false;
    }
    for (size_t index = 0U; index < identity->config_hash.length; ++index) {
        const char digit = identity->config_hash.data[index];
        if (!((digit >= '0' && digit <= '9') || (digit >= 'a' && digit <= 'f'))) {
            return false;
        }
    }
    return true;
}

static bool valid_clock(const egolink_location_state_emit_input_t *input)
{
    const char *source = event_time_source_name(input->event_time_source);
    if (source == NULL || input->event_time_ns > (uint64_t)INT64_MAX ||
        input->event_time_ns / 1000000U != input->event_time_ms) {
        return false;
    }
    if (input->event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS) {
        return valid_text(input->monotonic_clock_domain_id,
                          EGOLINK_LOCATION_STATE_ID_MAX_BYTES);
    }
    return input->monotonic_clock_domain_id.data == NULL &&
           input->monotonic_clock_domain_id.length == 0U;
}

static bool write_text_member(
    json_writer_t *writer,
    const char *prefix,
    egolink_location_state_text_t value)
{
    return writer_literal(writer, prefix) && writer_json_string(writer, value);
}

egolink_location_state_emit_result_t egolink_location_state_emit(
    const egolink_location_state_emit_input_t *input,
    char *output,
    size_t output_capacity,
    size_t *output_length)
{
    if (output_length != NULL) {
        *output_length = 0U;
    }
    if (input == NULL || output == NULL || output_length == NULL ||
        output_capacity == 0U) {
        clear_output(output, output_capacity);
        return EGOLINK_LOCATION_STATE_EMIT_INVALID_ARGUMENT;
    }
    clear_output(output, output_capacity);

    if (!valid_outbox_id(input->device_id) ||
        !valid_outbox_id(input->session_id) ||
        !valid_text(input->observation_id, EGOLINK_LOCATION_STATE_ID_MAX_BYTES) ||
        input->boot_count > (uint64_t)INT64_MAX ||
        input->sequence_id > (uint64_t)INT64_MAX) {
        return EGOLINK_LOCATION_STATE_EMIT_INVALID_IDENTITY;
    }
    if (!valid_clock(input)) {
        return EGOLINK_LOCATION_STATE_EMIT_INVALID_CLOCK;
    }
    if (!valid_policy_identity(&input->policy_identity)) {
        return EGOLINK_LOCATION_STATE_EMIT_INVALID_POLICY_IDENTITY;
    }
    if (!validate_location_state(input->location_state_json, input->event_time_ms)) {
        return EGOLINK_LOCATION_STATE_EMIT_INVALID_LOCATION_STATE;
    }

    json_writer_t writer = {
        .data = output,
        .capacity = bounded_output_capacity(output_capacity),
        .length = 0U,
        .overflow = false,
    };
    const egolink_location_state_text_t envelope_version = {
        .data = EGOLINK_LOCATION_STATE_ENVELOPE_CONTRACT_VERSION,
        .length = sizeof(EGOLINK_LOCATION_STATE_ENVELOPE_CONTRACT_VERSION) - 1U,
    };
    const char *source_name = event_time_source_name(input->event_time_source);
    const egolink_location_state_text_t source = {
        .data = source_name,
        .length = strlen(source_name),
    };

    writer_literal(&writer, "{\"envelope_contract_version\":");
    writer_json_string(&writer, envelope_version);
    write_text_member(&writer, ",\"device_id\":", input->device_id);
    writer_literal(&writer, ",\"boot_count\":");
    writer_u64(&writer, input->boot_count);
    write_text_member(&writer, ",\"session_id\":", input->session_id);
    writer_literal(&writer, ",\"event_time_ms\":");
    writer_u64(&writer, input->event_time_ms);
    write_text_member(&writer, ",\"event_time_source\":", source);
    writer_literal(&writer, ",\"event_time_ns\":");
    writer_u64(&writer, input->event_time_ns);
    writer_literal(&writer, ",\"monotonic_clock_domain_id\":");
    if (input->event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS) {
        writer_json_string(&writer, input->monotonic_clock_domain_id);
    } else {
        writer_literal(&writer, "null");
    }
    writer_literal(&writer, ",\"sequence_id\":");
    writer_u64(&writer, input->sequence_id);
    write_text_member(&writer, ",\"observation_id\":", input->observation_id);
    writer_literal(&writer, ",\"policy_identity\":{");
    write_text_member(&writer, "\"contract_version\":",
                      input->policy_identity.contract_version);
    write_text_member(&writer, ",\"semantic_validation\":",
                      input->policy_identity.semantic_validation);
    write_text_member(&writer, ",\"config_id\":",
                      input->policy_identity.config_id);
    write_text_member(&writer, ",\"config_hash\":",
                      input->policy_identity.config_hash);
    writer_literal(&writer, "},\"location_state\":");
    writer_append(&writer, input->location_state_json.data,
                  input->location_state_json.length);
    writer_literal(&writer, "}");

    if (writer.overflow || writer.length > EGOLINK_LOCATION_STATE_ENVELOPE_MAX_BYTES ||
        writer.length >= writer.capacity) {
        clear_output(output, output_capacity);
        return EGOLINK_LOCATION_STATE_EMIT_OVERFLOW;
    }
    output[writer.length] = '\0';
    *output_length = writer.length;
    return EGOLINK_LOCATION_STATE_EMIT_OK;
}

const char *egolink_location_state_emit_result_name(
    egolink_location_state_emit_result_t result)
{
    switch (result) {
    case EGOLINK_LOCATION_STATE_EMIT_OK:
        return "ok";
    case EGOLINK_LOCATION_STATE_EMIT_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_STATE_EMIT_INVALID_IDENTITY:
        return "invalid_identity";
    case EGOLINK_LOCATION_STATE_EMIT_INVALID_CLOCK:
        return "invalid_clock";
    case EGOLINK_LOCATION_STATE_EMIT_INVALID_POLICY_IDENTITY:
        return "invalid_policy_identity";
    case EGOLINK_LOCATION_STATE_EMIT_INVALID_LOCATION_STATE:
        return "invalid_location_state";
    case EGOLINK_LOCATION_STATE_EMIT_OVERFLOW:
        return "overflow";
    default:
        return "unknown";
    }
}
