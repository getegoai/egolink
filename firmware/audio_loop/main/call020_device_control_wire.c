/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 */

#include "call020_device_control_wire.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define EGLC_VERSION UINT8_C(1)
#define EGLC_PREPARE_REQUEST UINT8_C(1)
#define EGLC_PREPARE_ACK UINT8_C(2)
#define EGLC_START_REQUEST UINT8_C(3)
#define EGLC_START_ACK UINT8_C(4)
#define EGLC_CANCEL_REQUEST UINT8_C(5)
#define EGLC_CANCEL_ACK UINT8_C(6)
#define EGLC_JOIN_REQUEST UINT8_C(7)
#define EGLC_JOIN_ACK UINT8_C(8)
#define EGLC_CLOSE_REQUEST UINT8_C(9)
#define EGLC_CLOSE_ACK UINT8_C(10)
#define EGLC_TELEMETRY_REQUEST UINT8_C(11)
#define EGLC_TELEMETRY_ACK UINT8_C(12)

static const uint8_t s_magic[CALL020_CONTROL_MAGIC_BYTES] = {
    UINT8_C('E'), UINT8_C('G'), UINT8_C('L'), UINT8_C('C')};

void call020_control_wire_clear(void *memory, size_t bytes)
{
    volatile uint8_t *cursor = (volatile uint8_t *)memory;
    while (cursor != NULL && bytes > 0U) {
        *cursor++ = 0U;
        --bytes;
    }
}

const char *call020_device_control_wire_version(void)
{
    return CALL020_CONTROL_WIRE_VERSION;
}

static uint32_t crc32_bytes(const uint8_t *bytes, size_t count)
{
    uint32_t crc = UINT32_C(0xffffffff);
    for (size_t index = 0U; index < count; ++index) {
        crc ^= bytes[index];
        for (uint32_t bit = 0U; bit < UINT32_C(8); ++bit) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & UINT32_C(1)));
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) & mask);
        }
    }
    return crc ^ UINT32_C(0xffffffff);
}

static uint32_t read_be32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0] << 24U) |
        ((uint32_t)bytes[1] << 16U) |
        ((uint32_t)bytes[2] << 8U) |
        (uint32_t)bytes[3];
}

static void write_be32(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)(value >> 24U);
    bytes[1] = (uint8_t)(value >> 16U);
    bytes[2] = (uint8_t)(value >> 8U);
    bytes[3] = (uint8_t)value;
}

static bool identifier_character(uint8_t value)
{
    return (value >= UINT8_C('A') && value <= UINT8_C('Z')) ||
        (value >= UINT8_C('a') && value <= UINT8_C('z')) ||
        (value >= UINT8_C('0') && value <= UINT8_C('9')) ||
        value == UINT8_C('.') || value == UINT8_C('_') ||
        value == UINT8_C(':') || value == UINT8_C('-');
}

static bool valid_identifier(const char *value, size_t capacity)
{
    if (value == NULL || capacity < 2U) {
        return false;
    }
    size_t length = strnlen(value, capacity);
    if (length == 0U || length >= capacity) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        if (!identifier_character((uint8_t)value[index])) {
            return false;
        }
    }
    return true;
}

static call020_control_action_t action_from_text(
    const char *action,
    size_t action_bytes)
{
    if (action_bytes == 7U && memcmp(action, "prepare", 7U) == 0) {
        return CALL020_CONTROL_ACTION_PREPARE;
    }
    if (action_bytes == 5U && memcmp(action, "start", 5U) == 0) {
        return CALL020_CONTROL_ACTION_START;
    }
    if (action_bytes == 6U && memcmp(action, "cancel", 6U) == 0) {
        return CALL020_CONTROL_ACTION_CANCEL;
    }
    if (action_bytes == 4U && memcmp(action, "join", 4U) == 0) {
        return CALL020_CONTROL_ACTION_JOIN;
    }
    if (action_bytes == 5U && memcmp(action, "close", 5U) == 0) {
        return CALL020_CONTROL_ACTION_CLOSE;
    }
    if (action_bytes == 9U && memcmp(action, "telemetry", 9U) == 0) {
        return CALL020_CONTROL_ACTION_TELEMETRY;
    }
    return CALL020_CONTROL_ACTION_INVALID;
}

uint8_t call020_control_wire_request_type(call020_control_action_t action)
{
    switch (action) {
    case CALL020_CONTROL_ACTION_PREPARE:
        return EGLC_PREPARE_REQUEST;
    case CALL020_CONTROL_ACTION_START:
        return EGLC_START_REQUEST;
    case CALL020_CONTROL_ACTION_CANCEL:
        return EGLC_CANCEL_REQUEST;
    case CALL020_CONTROL_ACTION_JOIN:
        return EGLC_JOIN_REQUEST;
    case CALL020_CONTROL_ACTION_CLOSE:
        return EGLC_CLOSE_REQUEST;
    case CALL020_CONTROL_ACTION_TELEMETRY:
        return EGLC_TELEMETRY_REQUEST;
    default:
        return UINT8_C(0);
    }
}

uint8_t call020_control_wire_ack_type(call020_control_action_t action)
{
    switch (action) {
    case CALL020_CONTROL_ACTION_PREPARE:
        return EGLC_PREPARE_ACK;
    case CALL020_CONTROL_ACTION_START:
        return EGLC_START_ACK;
    case CALL020_CONTROL_ACTION_CANCEL:
        return EGLC_CANCEL_ACK;
    case CALL020_CONTROL_ACTION_JOIN:
        return EGLC_JOIN_ACK;
    case CALL020_CONTROL_ACTION_CLOSE:
        return EGLC_CLOSE_ACK;
    case CALL020_CONTROL_ACTION_TELEMETRY:
        return EGLC_TELEMETRY_ACK;
    default:
        return UINT8_C(0);
    }
}

static bool known_request_type(uint8_t type)
{
    return type == EGLC_PREPARE_REQUEST || type == EGLC_START_REQUEST ||
        type == EGLC_CANCEL_REQUEST || type == EGLC_JOIN_REQUEST ||
        type == EGLC_CLOSE_REQUEST || type == EGLC_TELEMETRY_REQUEST;
}

call020_control_wire_result_t
call020_control_wire_request_frame_bytes_from_header(
    const uint8_t *header,
    size_t header_bytes,
    size_t *frame_bytes)
{
    if (header == NULL || frame_bytes == NULL) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    *frame_bytes = 0U;
    if (header_bytes != CALL020_CONTROL_HEADER_BYTES) {
        return CALL020_CONTROL_WIRE_INVALID_LENGTH;
    }
    if (memcmp(header, s_magic, sizeof(s_magic)) != 0 ||
        header[4] != EGLC_VERSION || !known_request_type(header[5])) {
        return CALL020_CONTROL_WIRE_INVALID_HEADER;
    }
    size_t payload_bytes = ((size_t)header[6] << 8U) | (size_t)header[7];
    if (payload_bytes < 2U ||
        payload_bytes > CALL020_CONTROL_MAX_PAYLOAD_BYTES) {
        return CALL020_CONTROL_WIRE_INVALID_LENGTH;
    }
    *frame_bytes = CALL020_CONTROL_HEADER_BYTES + payload_bytes +
        CALL020_CONTROL_CRC_BYTES;
    return CALL020_CONTROL_WIRE_OK;
}

static bool consume_literal(
    const uint8_t **cursor,
    const uint8_t *end,
    const char *literal)
{
    size_t bytes = strlen(literal);
    if ((size_t)(end - *cursor) < bytes ||
        memcmp(*cursor, literal, bytes) != 0) {
        return false;
    }
    *cursor += bytes;
    return true;
}

static bool consume_identifier(
    const uint8_t **cursor,
    const uint8_t *end,
    char *output,
    size_t capacity)
{
    if (*cursor >= end || **cursor != UINT8_C('"')) {
        return false;
    }
    ++*cursor;
    size_t length = 0U;
    while (*cursor < end && **cursor != UINT8_C('"')) {
        if (length + 1U >= capacity || !identifier_character(**cursor)) {
            return false;
        }
        output[length++] = (char)**cursor;
        ++*cursor;
    }
    if (*cursor >= end || **cursor != UINT8_C('"') || length == 0U) {
        return false;
    }
    ++*cursor;
    output[length] = '\0';
    return true;
}

static bool consume_timeout(
    const uint8_t **cursor,
    const uint8_t *end,
    uint32_t *timeout_ms)
{
    if (*cursor >= end || **cursor < UINT8_C('1') ||
        **cursor > UINT8_C('9')) {
        return false;
    }
    uint32_t value = 0U;
    while (*cursor < end && **cursor >= UINT8_C('0') &&
           **cursor <= UINT8_C('9')) {
        uint32_t digit = (uint32_t)(**cursor - UINT8_C('0'));
        if (value > UINT32_C(10000) / UINT32_C(10)) {
            return false;
        }
        value = value * UINT32_C(10) + digit;
        ++*cursor;
    }
    if (value == 0U || value > UINT32_C(10000)) {
        return false;
    }
    *timeout_ms = value;
    return true;
}

static bool parse_payload(
    const uint8_t *payload,
    size_t payload_bytes,
    call020_control_request_t *request)
{
    const uint8_t *cursor = payload;
    const uint8_t *end = payload + payload_bytes;
    char action[CALL020_CONTROL_ACTION_CAPACITY] = {0};
    bool valid = consume_literal(&cursor, end, "{\"action\":") &&
        consume_identifier(&cursor, end, action, sizeof(action)) &&
        consume_literal(&cursor, end, ",\"operation_id\":") &&
        consume_identifier(
            &cursor, end, request->operation_id,
            sizeof(request->operation_id)) &&
        consume_literal(&cursor, end, ",\"run_id\":") &&
        consume_identifier(
            &cursor, end, request->run_id, sizeof(request->run_id)) &&
        consume_literal(&cursor, end, ",\"timeout_ms\":") &&
        consume_timeout(&cursor, end, &request->timeout_ms) &&
        consume_literal(&cursor, end, "}") && cursor == end;
    size_t action_bytes = strnlen(action, sizeof(action));
    request->action = action_from_text(action, action_bytes);
    if (!valid || request->action == CALL020_CONTROL_ACTION_INVALID) {
        call020_control_wire_clear(action, sizeof(action));
        return false;
    }
    memcpy(request->action_text, action, action_bytes + 1U);
    call020_control_wire_clear(action, sizeof(action));
    return true;
}

call020_control_wire_result_t call020_control_wire_decode_request(
    const uint8_t *frame,
    size_t frame_bytes,
    call020_control_request_t *request)
{
    if (frame == NULL || request == NULL) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    call020_control_wire_clear(request, sizeof(*request));
    if (frame_bytes < CALL020_CONTROL_HEADER_BYTES + UINT32_C(2) +
            CALL020_CONTROL_CRC_BYTES ||
        frame_bytes > CALL020_CONTROL_MAX_FRAME_BYTES) {
        return CALL020_CONTROL_WIRE_INVALID_LENGTH;
    }
    size_t declared_frame_bytes = 0U;
    call020_control_wire_result_t header_result =
        call020_control_wire_request_frame_bytes_from_header(
            frame, CALL020_CONTROL_HEADER_BYTES, &declared_frame_bytes);
    if (header_result != CALL020_CONTROL_WIRE_OK) {
        return header_result;
    }
    size_t payload_bytes = declared_frame_bytes -
        CALL020_CONTROL_HEADER_BYTES - CALL020_CONTROL_CRC_BYTES;
    if (frame_bytes != declared_frame_bytes) {
        return CALL020_CONTROL_WIRE_INVALID_LENGTH;
    }
    uint32_t expected_crc = read_be32(
        frame + frame_bytes - CALL020_CONTROL_CRC_BYTES);
    if (crc32_bytes(
            frame, frame_bytes - CALL020_CONTROL_CRC_BYTES) != expected_crc) {
        return CALL020_CONTROL_WIRE_INVALID_CRC;
    }
    if (!parse_payload(
            frame + CALL020_CONTROL_HEADER_BYTES, payload_bytes, request) ||
        frame[5] != call020_control_wire_request_type(request->action)) {
        call020_control_wire_clear(request, sizeof(*request));
        return CALL020_CONTROL_WIRE_INVALID_SCHEMA;
    }
    return CALL020_CONTROL_WIRE_OK;
}

static call020_control_wire_result_t encode_payload(
    uint8_t message_type,
    const char *payload,
    int payload_bytes,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes)
{
    if (message_type == UINT8_C(0) || payload == NULL || payload_bytes < 2 ||
        payload_bytes > (int)CALL020_CONTROL_MAX_PAYLOAD_BYTES ||
        frame == NULL || frame_bytes == NULL) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    size_t total = CALL020_CONTROL_HEADER_BYTES + (size_t)payload_bytes +
        CALL020_CONTROL_CRC_BYTES;
    if (frame_capacity < total) {
        return CALL020_CONTROL_WIRE_OUTPUT_TOO_SMALL;
    }
    memcpy(frame, s_magic, sizeof(s_magic));
    frame[4] = EGLC_VERSION;
    frame[5] = message_type;
    frame[6] = (uint8_t)((uint32_t)payload_bytes >> 8U);
    frame[7] = (uint8_t)payload_bytes;
    memcpy(frame + CALL020_CONTROL_HEADER_BYTES, payload, (size_t)payload_bytes);
    write_be32(
        frame + CALL020_CONTROL_HEADER_BYTES + (size_t)payload_bytes,
        crc32_bytes(
            frame, CALL020_CONTROL_HEADER_BYTES + (size_t)payload_bytes));
    *frame_bytes = total;
    return CALL020_CONTROL_WIRE_OK;
}

call020_control_wire_result_t call020_control_wire_encode_prepare_ack(
    const call020_control_request_t *request,
    const call020_control_prepare_descriptor_t *descriptor,
    const call020_control_pre_start_telemetry_t *telemetry,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes)
{
    if (request == NULL || descriptor == NULL || telemetry == NULL ||
        request->action != CALL020_CONTROL_ACTION_PREPARE ||
        !valid_identifier(
            request->run_id, sizeof(request->run_id)) ||
        !valid_identifier(
            request->operation_id, sizeof(request->operation_id)) ||
        !valid_identifier(descriptor->session_id, UINT32_C(40)) ||
        !valid_identifier(descriptor->device_id, UINT32_C(40)) ||
        !valid_identifier(descriptor->guardian_id, UINT32_C(40)) ||
        !valid_identifier(descriptor->uplink_clock_id, UINT32_C(40)) ||
        !valid_identifier(descriptor->downlink_clock_id, UINT32_C(40)) ||
        descriptor->nonce_bits < UINT32_C(128) ||
        telemetry->captured_at_monotonic_ns > INT64_MAX ||
        telemetry->free_internal_heap_bytes == 0U ||
        telemetry->minimum_free_internal_heap_bytes == 0U ||
        telemetry->minimum_free_internal_heap_bytes >
            telemetry->free_internal_heap_bytes) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    char payload[CALL020_CONTROL_MAX_PAYLOAD_BYTES + 1U] = {0};
    int bytes = snprintf(
        payload,
        sizeof(payload),
        "{\"correlated_routing_ids\":true,\"device_id\":\"%s\","
        "\"downlink_clock_id\":\"%s\",\"duplicate\":%s,"
        "\"guardian_id\":\"%s\",\"nonce_bits\":%" PRIu32 ","
        "\"operation_id\":\"%s\",\"pre_start_telemetry\":{"
        "\"captured_at_monotonic_ns\":%" PRIu64 ","
        "\"externally_attested_runtime_measurement\":true,"
        "\"free_internal_heap_bytes\":%" PRIu32 ","
        "\"minimum_free_internal_heap_bytes\":%" PRIu32 ","
        "\"phase\":\"pre_start\","
        "\"worker_stack_high_watermark_bytes\":[]},"
        "\"provenance\":\"runtime_ephemeral_generated\","
        "\"random_quality\":\"unverified\",\"run_id\":\"%s\","
        "\"runner_api_version\":1,"
        "\"runner_version\":\"call020-operator-runner-v1\","
        "\"session_id\":\"%s\",\"state\":\"PREPARED\","
        "\"uplink_clock_id\":\"%s\"}",
        descriptor->device_id,
        descriptor->downlink_clock_id,
        duplicate ? "true" : "false",
        descriptor->guardian_id,
        descriptor->nonce_bits,
        request->operation_id,
        telemetry->captured_at_monotonic_ns,
        telemetry->free_internal_heap_bytes,
        telemetry->minimum_free_internal_heap_bytes,
        request->run_id,
        descriptor->session_id,
        descriptor->uplink_clock_id);
    call020_control_wire_result_t result = encode_payload(
        EGLC_PREPARE_ACK, payload, bytes, frame, frame_capacity, frame_bytes);
    call020_control_wire_clear(payload, sizeof(payload));
    return result;
}

call020_control_wire_result_t call020_control_wire_encode_ack(
    const call020_control_request_t *request,
    const char *state,
    bool accepted,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes)
{
    if (request == NULL || state == NULL ||
        request->action == CALL020_CONTROL_ACTION_INVALID ||
        request->action == CALL020_CONTROL_ACTION_PREPARE ||
        request->action == CALL020_CONTROL_ACTION_TELEMETRY ||
        !valid_identifier(request->run_id, sizeof(request->run_id)) ||
        !valid_identifier(
            request->operation_id, sizeof(request->operation_id)) ||
        !valid_identifier(state, UINT32_C(16))) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    char payload[CALL020_CONTROL_MAX_PAYLOAD_BYTES + 1U] = {0};
    int bytes = snprintf(
        payload,
        sizeof(payload),
        "{\"accepted\":%s,\"action\":\"%s\",\"duplicate\":%s,"
        "\"operation_id\":\"%s\",\"run_id\":\"%s\","
        "\"state\":\"%s\"}",
        accepted ? "true" : "false",
        request->action_text,
        duplicate ? "true" : "false",
        request->operation_id,
        request->run_id,
        state);
    call020_control_wire_result_t result = encode_payload(
        call020_control_wire_ack_type(request->action), payload, bytes,
        frame, frame_capacity, frame_bytes);
    call020_control_wire_clear(payload, sizeof(payload));
    return result;
}

call020_control_wire_result_t
call020_control_wire_encode_telemetry_unavailable_ack(
    const call020_control_request_t *request,
    const call020_control_pre_start_telemetry_t *telemetry,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes)
{
    if (request == NULL || telemetry == NULL ||
        request->action != CALL020_CONTROL_ACTION_TELEMETRY ||
        !valid_identifier(request->run_id, sizeof(request->run_id)) ||
        !valid_identifier(
            request->operation_id, sizeof(request->operation_id)) ||
        telemetry->captured_at_monotonic_ns > INT64_MAX ||
        telemetry->free_internal_heap_bytes == 0U ||
        telemetry->minimum_free_internal_heap_bytes == 0U ||
        telemetry->minimum_free_internal_heap_bytes >
            telemetry->free_internal_heap_bytes) {
        return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
    }
    char payload[CALL020_CONTROL_MAX_PAYLOAD_BYTES + 1U] = {0};
    int bytes = snprintf(
        payload,
        sizeof(payload),
        "{\"accepted\":false,\"action\":\"telemetry\","
        "\"duplicate\":%s,\"operation_id\":\"%s\","
        "\"run_id\":\"%s\",\"snapshot\":{"
        "\"captured_at_monotonic_ns\":%" PRIu64 ","
        "\"externally_attested_runtime_measurement\":true,"
        "\"free_internal_heap_bytes\":%" PRIu32 ","
        "\"minimum_free_internal_heap_bytes\":%" PRIu32 ","
        "\"phase\":\"post_stop\","
        "\"worker_stack_high_watermark_bytes\":[]}}",
        duplicate ? "true" : "false",
        request->operation_id,
        request->run_id,
        telemetry->captured_at_monotonic_ns,
        telemetry->free_internal_heap_bytes,
        telemetry->minimum_free_internal_heap_bytes);
    call020_control_wire_result_t result = encode_payload(
        EGLC_TELEMETRY_ACK, payload, bytes, frame, frame_capacity, frame_bytes);
    call020_control_wire_clear(payload, sizeof(payload));
    return result;
}
