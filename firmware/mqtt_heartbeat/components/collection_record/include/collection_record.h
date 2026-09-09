#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "cJSON.h"
#define COLLECTION_FRAME_CAPACITY 4000U
#define COLLECTION_RECORD_ASCII_XHH_ENCODING "ascii-xhh-v1"

/* Encode arbitrary octets as bounded ASCII text. Printable ASCII plus CR/LF/TAB
 * is retained, while every other byte (including '\\') becomes "\\xHH".
 * Escaping '\\' makes the representation unambiguous and reversible. */
bool collection_record_ascii_xhh(const uint8_t *input, size_t input_length,
    char *output, size_t output_capacity, size_t *output_length,
    bool *truncated);
/* Existing EGLK/1 framing, with additive JSON collection content profile. */
size_t collection_record_frame(const cJSON *observation, char *frame, size_t capacity);
bool collection_record_identity(const void *frame, size_t length, char *id, size_t capacity);
bool collection_record_ack_matches(const void *frame, size_t length,
    const char *device_id, const void *response, size_t response_length);
