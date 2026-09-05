/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020Q dependency-free EGLC v1 wire codec. CRC32 protects framing
 * integrity only; it is deliberately not authentication.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CALL020_CONTROL_WIRE_VERSION "call020-device-control-wire-v1"
#define CALL020_CONTROL_MAGIC_BYTES UINT32_C(4)
#define CALL020_CONTROL_HEADER_BYTES UINT32_C(8)
#define CALL020_CONTROL_CRC_BYTES UINT32_C(4)
#define CALL020_CONTROL_MAX_PAYLOAD_BYTES UINT32_C(2048)
#define CALL020_CONTROL_MAX_FRAME_BYTES \
    (CALL020_CONTROL_HEADER_BYTES + CALL020_CONTROL_MAX_PAYLOAD_BYTES + \
     CALL020_CONTROL_CRC_BYTES)
#define CALL020_CONTROL_RUN_ID_CAPACITY UINT32_C(65)
#define CALL020_CONTROL_OPERATION_ID_CAPACITY UINT32_C(129)
#define CALL020_CONTROL_ACTION_CAPACITY UINT32_C(10)

typedef enum {
    CALL020_CONTROL_ACTION_INVALID = 0,
    CALL020_CONTROL_ACTION_PREPARE,
    CALL020_CONTROL_ACTION_START,
    CALL020_CONTROL_ACTION_CANCEL,
    CALL020_CONTROL_ACTION_JOIN,
    CALL020_CONTROL_ACTION_CLOSE,
    CALL020_CONTROL_ACTION_TELEMETRY,
} call020_control_action_t;

typedef enum {
    CALL020_CONTROL_WIRE_OK = 0,
    CALL020_CONTROL_WIRE_INVALID_ARGUMENT,
    CALL020_CONTROL_WIRE_INVALID_LENGTH,
    CALL020_CONTROL_WIRE_INVALID_HEADER,
    CALL020_CONTROL_WIRE_INVALID_CRC,
    CALL020_CONTROL_WIRE_INVALID_SCHEMA,
    CALL020_CONTROL_WIRE_OUTPUT_TOO_SMALL,
} call020_control_wire_result_t;

typedef struct {
    call020_control_action_t action;
    char action_text[CALL020_CONTROL_ACTION_CAPACITY];
    char operation_id[CALL020_CONTROL_OPERATION_ID_CAPACITY];
    char run_id[CALL020_CONTROL_RUN_ID_CAPACITY];
    uint32_t timeout_ms;
} call020_control_request_t;

typedef struct {
    const char *session_id;
    const char *device_id;
    const char *guardian_id;
    const char *uplink_clock_id;
    const char *downlink_clock_id;
    uint32_t nonce_bits;
} call020_control_prepare_descriptor_t;

typedef struct {
    uint64_t captured_at_monotonic_ns;
    uint32_t free_internal_heap_bytes;
    uint32_t minimum_free_internal_heap_bytes;
} call020_control_pre_start_telemetry_t;

const char *call020_device_control_wire_version(void);

/* Validate the exact 8-byte header before its declared remainder is read. */
call020_control_wire_result_t
call020_control_wire_request_frame_bytes_from_header(
    const uint8_t *header,
    size_t header_bytes,
    size_t *frame_bytes);

/*
 * Decode one exact, complete, canonical host request. The accepted JSON is
 * deliberately narrower than general JSON and matches CALL-020P exactly:
 * ASCII identifiers, sorted fixed keys, no escapes, no whitespace and one
 * base-10 timeout in [1, 10000]. No resynchronization is attempted.
 */
call020_control_wire_result_t call020_control_wire_decode_request(
    const uint8_t *frame,
    size_t frame_bytes,
    call020_control_request_t *request);

call020_control_wire_result_t call020_control_wire_encode_prepare_ack(
    const call020_control_request_t *request,
    const call020_control_prepare_descriptor_t *descriptor,
    const call020_control_pre_start_telemetry_t *telemetry,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes);

call020_control_wire_result_t call020_control_wire_encode_ack(
    const call020_control_request_t *request,
    const char *state,
    bool accepted,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes);

/* Honest rejection used until real four-worker post-stop watermarks exist. */
call020_control_wire_result_t
call020_control_wire_encode_telemetry_unavailable_ack(
    const call020_control_request_t *request,
    const call020_control_pre_start_telemetry_t *telemetry,
    bool duplicate,
    uint8_t *frame,
    size_t frame_capacity,
    size_t *frame_bytes);

uint8_t call020_control_wire_request_type(call020_control_action_t action);
uint8_t call020_control_wire_ack_type(call020_control_action_t action);

void call020_control_wire_clear(void *memory, size_t bytes);

#ifdef __cplusplus
}
#endif
