#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "cJSON.h"
#define COLLECTION_FRAME_CAPACITY 4000U
/* Existing EGLK/1 framing, with additive JSON collection content profile. */
size_t collection_record_frame(const cJSON *observation, char *frame, size_t capacity);
bool collection_record_identity(const void *frame, size_t length, char *id, size_t capacity);
bool collection_record_ack_matches(const void *frame, size_t length,
    const char *device_id, const void *response, size_t response_length);
