/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-020D framing/queue core only. No USB, TinyUSB, serial, audio-device,
 * task, storage, network, codec, volume or pin API is used here.
 */

#include "call020_media_adapter_core.h"

#include <limits.h>
#include <string.h>

#define CALL020_WIRE_VERSION UINT8_C(1)
#define CALL020_DIRECTION_UPLINK UINT8_C(1)
#define CALL020_DIRECTION_DOWNLINK UINT8_C(2)
#define CALL020_ROLE_DEVICE UINT8_C(1)
#define CALL020_ROLE_GUARDIAN UINT8_C(2)
#define CALL020_FRAME_INTERVAL_US UINT64_C(20000)
#define CALL020_MIN_WIRE_BYTES \
    (CALL020_MEDIA_WIRE_HEADER_BYTES + UINT32_C(4) + \
     CALL020_MEDIA_MONO_BYTES + CALL020_MEDIA_WIRE_CRC_BYTES)

static const uint8_t CALL020_WIRE_MAGIC[4] = {'E', 'G', 'L', 'M'};

_Static_assert(
    CALL020_MEDIA_MONO_SAMPLES * sizeof(int16_t) ==
        CALL020_MEDIA_MONO_BYTES,
    "CALL-020B mono payload must be exactly 640 bytes");
_Static_assert(
    CALL020_MEDIA_STEREO_VALUES * sizeof(int16_t) ==
        CALL020_MEDIA_STEREO_BYTES,
    "CALL-010 compatibility frame must be exactly 1280 bytes");
_Static_assert(
    CALL020_MEDIA_WIRE_MAX_BYTES ==
        CALL020_MEDIA_WIRE_HEADER_BYTES +
        (UINT32_C(4) * CALL020_MEDIA_IDENTIFIER_MAX_BYTES) +
        CALL020_MEDIA_MONO_BYTES + CALL020_MEDIA_WIRE_CRC_BYTES,
    "CALL-020B maximum wire size changed");

static void secure_zero(void *memory, size_t size)
{
    if (memory == NULL) {
        return;
    }
    volatile uint8_t *cursor = (volatile uint8_t *)memory;
    while (size > 0U) {
        *cursor++ = 0U;
        --size;
    }
}

static bool checked_add_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (result == NULL || UINT64_MAX - left < right) {
        return false;
    }
    *result = left + right;
    return true;
}

static bool identifier_character(uint8_t value)
{
    return (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
           (value >= (uint8_t)'a' && value <= (uint8_t)'z') ||
           (value >= (uint8_t)'0' && value <= (uint8_t)'9') ||
           value == (uint8_t)'.' || value == (uint8_t)'_' ||
           value == (uint8_t)':' || value == (uint8_t)'-';
}

static bool identifier_valid(const char *value, size_t *length)
{
    if (value == NULL || length == NULL) {
        return false;
    }
    size_t cursor = 0U;
    while (cursor <= CALL020_MEDIA_IDENTIFIER_MAX_BYTES &&
           value[cursor] != '\0') {
        if (!identifier_character((uint8_t)value[cursor])) {
            return false;
        }
        ++cursor;
    }
    if (cursor == 0U || cursor > CALL020_MEDIA_IDENTIFIER_MAX_BYTES ||
        value[cursor] != '\0') {
        return false;
    }
    *length = cursor;
    return true;
}

static bool copy_identifier(
    char destination[CALL020_MEDIA_IDENTIFIER_MAX_BYTES + 1U],
    const char *source)
{
    size_t length = 0U;
    if (!identifier_valid(source, &length)) {
        return false;
    }
    memcpy(destination, source, length + 1U);
    return true;
}

static void put_be16(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value >> 8U);
    destination[1] = (uint8_t)value;
}

static void put_be32(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24U);
    destination[1] = (uint8_t)(value >> 16U);
    destination[2] = (uint8_t)(value >> 8U);
    destination[3] = (uint8_t)value;
}

static void put_be64(uint8_t *destination, uint64_t value)
{
    for (size_t index = 0U; index < 8U; ++index) {
        destination[index] = (uint8_t)(value >> (56U - (index * 8U)));
    }
}

static uint16_t get_be16(const uint8_t *source)
{
    return (uint16_t)(((uint16_t)source[0] << 8U) | source[1]);
}

static uint32_t get_be32(const uint8_t *source)
{
    return ((uint32_t)source[0] << 24U) |
           ((uint32_t)source[1] << 16U) |
           ((uint32_t)source[2] << 8U) |
           (uint32_t)source[3];
}

static uint64_t get_be64(const uint8_t *source)
{
    uint64_t value = 0U;
    for (size_t index = 0U; index < 8U; ++index) {
        value = (value << 8U) | source[index];
    }
    return value;
}

static uint32_t crc32(const uint8_t *data, size_t size)
{
    uint32_t value = UINT32_MAX;
    for (size_t index = 0U; index < size; ++index) {
        value ^= data[index];
        for (uint32_t bit = 0U; bit < 8U; ++bit) {
            uint32_t mask = (uint32_t)-(int32_t)(value & 1U);
            value = (value >> 1U) ^ (UINT32_C(0xEDB88320) & mask);
        }
    }
    return ~value;
}

static call020_media_slot_t *queue_tail(
    call020_media_queue_t *queue, size_t capacity)
{
    size_t index = (queue->head + queue->count) % capacity;
    return &queue->slots[index];
}

static call020_media_slot_t *queue_head(call020_media_queue_t *queue)
{
    return &queue->slots[queue->head];
}

static void queue_pop(call020_media_queue_t *queue, size_t capacity)
{
    secure_zero(queue_head(queue), sizeof(call020_media_slot_t));
    queue->head = (queue->head + 1U) % capacity;
    --queue->count;
}

static uint64_t clear_queue(call020_media_queue_t *queue)
{
    uint64_t dropped = queue->count;
    secure_zero(queue, sizeof(*queue));
    return dropped;
}

static void sync_metadata_depths(call020_media_adapter_core_t *core)
{
    core->metadata.state = core->state;
    core->metadata.terminal_reason = core->terminal_reason;
    core->metadata.uplink_queue_depth = core->uplink_queue.count;
    core->metadata.downlink_queue_depth = core->downlink_queue.count;
}

static void clear_owned_media(call020_media_adapter_core_t *core)
{
    core->metadata.cleanup_drops += clear_queue(&core->uplink_queue);
    core->metadata.cleanup_drops += clear_queue(&core->downlink_queue);
    secure_zero(core->wire_scratch, sizeof(core->wire_scratch));
    secure_zero(core->stereo_scratch, sizeof(core->stereo_scratch));
    sync_metadata_depths(core);
}

static esp_err_t force_pa_off(call020_media_adapter_core_t *core)
{
    if (core == NULL || core->force_pa_off == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    return core->force_pa_off(core->pa_user_context);
}

static esp_err_t terminate(
    call020_media_adapter_core_t *core,
    call020_media_terminal_reason_t reason,
    esp_err_t result)
{
    if (core == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    core->state = CALL020_MEDIA_CORE_TERMINAL;
    core->terminal_reason = reason;
    clear_owned_media(core);
    esp_err_t pa_result = force_pa_off(core);
    if (pa_result != ESP_OK) {
        core->terminal_reason = CALL020_MEDIA_TERMINAL_PA_OFF;
        result = pa_result;
    }
    sync_metadata_depths(core);
    return result;
}

static esp_err_t check_running_time(
    call020_media_adapter_core_t *core, uint64_t now_us)
{
    if (core == NULL || !core->initialized ||
        core->state != CALL020_MEDIA_CORE_RUNNING) {
        return ESP_ERR_INVALID_STATE;
    }
    if (now_us < core->last_now_us) {
        return terminate(
            core, CALL020_MEDIA_TERMINAL_CLOCK_REGRESSION,
            ESP_ERR_INVALID_STATE);
    }
    core->last_now_us = now_us;
    if (now_us > core->runtime_deadline_us) {
        core->metadata.deadline_failures++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_RUNTIME_DEADLINE,
            ESP_ERR_TIMEOUT);
    }
    return ESP_OK;
}

static bool bytes_equal_string(
    const uint8_t *bytes, size_t byte_count, const char *expected)
{
    size_t expected_count = strlen(expected);
    return byte_count == expected_count &&
        memcmp(bytes, expected, byte_count) == 0;
}

static void downmix_stereo_to_mono(
    const int16_t *stereo, uint8_t mono[CALL020_MEDIA_MONO_BYTES])
{
    for (size_t sample = 0U; sample < CALL020_MEDIA_MONO_SAMPLES; ++sample) {
        int32_t sum = (int32_t)stereo[sample * 2U] +
            (int32_t)stereo[sample * 2U + 1U];
        int16_t value = (int16_t)(sum / 2);
        uint16_t encoded = (uint16_t)value;
        mono[sample * 2U] = (uint8_t)encoded;
        mono[sample * 2U + 1U] = (uint8_t)(encoded >> 8U);
    }
}

static void expand_mono_to_stereo(
    const uint8_t mono[CALL020_MEDIA_MONO_BYTES],
    int16_t stereo[CALL020_MEDIA_STEREO_VALUES])
{
    for (size_t sample = 0U; sample < CALL020_MEDIA_MONO_SAMPLES; ++sample) {
        uint16_t encoded = (uint16_t)(
            (uint16_t)mono[sample * 2U] |
            ((uint16_t)mono[sample * 2U + 1U] << 8U));
        int16_t value = (int16_t)encoded;
        stereo[sample * 2U] = value;
        stereo[sample * 2U + 1U] = value;
    }
}

static esp_err_t encode_uplink(
    call020_media_adapter_core_t *core,
    const call020_media_slot_t *slot,
    size_t *wire_bytes)
{
    const char *identifiers[4] = {
        core->session_id,
        core->device_id,
        core->guardian_id,
        core->uplink_clock_id,
    };
    uint16_t lengths[4];
    size_t total = CALL020_MEDIA_WIRE_HEADER_BYTES +
        CALL020_MEDIA_MONO_BYTES + CALL020_MEDIA_WIRE_CRC_BYTES;
    for (size_t index = 0U; index < 4U; ++index) {
        size_t length = strlen(identifiers[index]);
        if (length == 0U || length > CALL020_MEDIA_IDENTIFIER_MAX_BYTES) {
            return ESP_ERR_INVALID_STATE;
        }
        lengths[index] = (uint16_t)length;
        total += length;
    }
    if (total > sizeof(core->wire_scratch)) {
        return ESP_ERR_INVALID_SIZE;
    }

    uint8_t *wire = core->wire_scratch;
    memcpy(wire, CALL020_WIRE_MAGIC, sizeof(CALL020_WIRE_MAGIC));
    wire[4] = CALL020_WIRE_VERSION;
    wire[5] = CALL020_DIRECTION_UPLINK;
    wire[6] = CALL020_ROLE_DEVICE;
    wire[7] = CALL020_ROLE_GUARDIAN;
    put_be64(&wire[8], slot->sequence);
    put_be64(&wire[16], slot->source_time_ns);
    for (size_t index = 0U; index < 4U; ++index) {
        put_be16(&wire[24U + index * 2U], lengths[index]);
    }
    put_be16(&wire[32], (uint16_t)CALL020_MEDIA_MONO_BYTES);

    size_t cursor = CALL020_MEDIA_WIRE_HEADER_BYTES;
    for (size_t index = 0U; index < 4U; ++index) {
        memcpy(&wire[cursor], identifiers[index], lengths[index]);
        cursor += lengths[index];
    }
    memcpy(&wire[cursor], slot->media, CALL020_MEDIA_MONO_BYTES);
    cursor += CALL020_MEDIA_MONO_BYTES;
    put_be32(&wire[cursor], crc32(wire, cursor));
    cursor += CALL020_MEDIA_WIRE_CRC_BYTES;
    *wire_bytes = cursor;
    return ESP_OK;
}

static esp_err_t protocol_failure(call020_media_adapter_core_t *core)
{
    core->metadata.protocol_failures++;
    return terminate(
        core, CALL020_MEDIA_TERMINAL_PROTOCOL, ESP_ERR_INVALID_RESPONSE);
}

const char *call020_media_adapter_core_version(void)
{
    return CALL020_MEDIA_ADAPTER_CORE_VERSION;
}

esp_err_t call020_media_adapter_core_init(
    call020_media_adapter_core_t *core,
    const call020_media_adapter_config_t *config)
{
    if (core == NULL || config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    secure_zero(core, sizeof(*core));
    core->force_pa_off = config->force_pa_off;
    core->pa_user_context = config->pa_user_context;

    size_t ignored = 0U;
    bool valid = config->force_pa_off != NULL &&
        config->queue_capacity_frames > 0U &&
        config->queue_capacity_frames <= CALL020_MEDIA_QUEUE_MAX_FRAMES &&
        config->frame_deadline_slack_us <= UINT64_C(1000000) &&
        config->downlink_playout_delay_us <= UINT64_C(1000000) &&
        config->max_runtime_us >= CALL020_FRAME_INTERVAL_US &&
        config->max_runtime_us <= CALL020_MEDIA_MAX_RUNTIME_US &&
        identifier_valid(config->session_id, &ignored) &&
        identifier_valid(config->device_id, &ignored) &&
        identifier_valid(config->guardian_id, &ignored) &&
        identifier_valid(config->uplink_clock_id, &ignored) &&
        identifier_valid(config->downlink_clock_id, &ignored) &&
        strcmp(config->device_id, config->guardian_id) != 0 &&
        strcmp(config->uplink_clock_id, config->downlink_clock_id) != 0;
    if (!valid) {
        esp_err_t pa_result = ESP_OK;
        if (config->force_pa_off != NULL) {
            pa_result = force_pa_off(core);
        }
        secure_zero(core, sizeof(*core));
        return pa_result == ESP_OK ? ESP_ERR_INVALID_ARG : pa_result;
    }

    if (!copy_identifier(core->session_id, config->session_id) ||
        !copy_identifier(core->device_id, config->device_id) ||
        !copy_identifier(core->guardian_id, config->guardian_id) ||
        !copy_identifier(core->uplink_clock_id, config->uplink_clock_id) ||
        !copy_identifier(core->downlink_clock_id, config->downlink_clock_id)) {
        esp_err_t pa_result = force_pa_off(core);
        secure_zero(core, sizeof(*core));
        return pa_result == ESP_OK ? ESP_ERR_INVALID_ARG : pa_result;
    }
    core->queue_capacity_frames = config->queue_capacity_frames;
    core->frame_deadline_slack_us = config->frame_deadline_slack_us;
    core->downlink_playout_delay_us = config->downlink_playout_delay_us;
    core->max_runtime_us = config->max_runtime_us;
    core->state = CALL020_MEDIA_CORE_READY;
    core->metadata.state = core->state;
    esp_err_t result = force_pa_off(core);
    if (result != ESP_OK) {
        core->state = CALL020_MEDIA_CORE_TERMINAL;
        core->terminal_reason = CALL020_MEDIA_TERMINAL_PA_OFF;
        sync_metadata_depths(core);
        return result;
    }
    core->initialized = true;
    return ESP_OK;
}

esp_err_t call020_media_adapter_core_start(
    call020_media_adapter_core_t *core, uint64_t monotonic_now_us)
{
    if (core == NULL || !core->initialized ||
        core->state != CALL020_MEDIA_CORE_READY) {
        return ESP_ERR_INVALID_STATE;
    }
    clear_owned_media(core);
    core->terminal_reason = CALL020_MEDIA_TERMINAL_NONE;
    core->metadata.terminal_reason = CALL020_MEDIA_TERMINAL_NONE;
    core->next_uplink_sequence = 0U;
    core->has_uplink_source_time = false;
    core->expected_downlink_sequence = 0U;
    core->has_downlink_source_time = false;
    core->has_downlink_playout_epoch = false;
    core->started_us = monotonic_now_us;
    core->last_now_us = monotonic_now_us;
    core->next_uplink_due_us = monotonic_now_us;
    if (!checked_add_u64(
            monotonic_now_us, core->max_runtime_us,
            &core->runtime_deadline_us)) {
        return terminate(
            core, CALL020_MEDIA_TERMINAL_RUNTIME_DEADLINE,
            ESP_ERR_INVALID_ARG);
    }
    esp_err_t result = force_pa_off(core);
    if (result != ESP_OK) {
        return terminate(core, CALL020_MEDIA_TERMINAL_PA_OFF, result);
    }
    core->state = CALL020_MEDIA_CORE_RUNNING;
    sync_metadata_depths(core);
    return ESP_OK;
}

esp_err_t call020_media_adapter_core_offer_uplink_stereo(
    call020_media_adapter_core_t *core,
    int16_t *stereo_values,
    size_t stereo_value_count,
    uint64_t source_time_ns,
    uint64_t monotonic_now_us)
{
    bool owns_input = stereo_values != NULL &&
        stereo_value_count == CALL020_MEDIA_STEREO_VALUES;
    esp_err_t result = ESP_ERR_INVALID_ARG;
    if (!owns_input) {
        return result;
    }
    if (core == NULL) {
        goto cleanup;
    }
    result = check_running_time(core, monotonic_now_us);
    if (result != ESP_OK) {
        goto cleanup;
    }
    if (monotonic_now_us < core->next_uplink_due_us) {
        result = ESP_ERR_INVALID_STATE;
        goto cleanup;
    }
    if (source_time_ns > INT64_MAX ||
        (core->has_uplink_source_time &&
         source_time_ns <= core->last_uplink_source_time_ns)) {
        result = protocol_failure(core);
        goto cleanup;
    }
    uint64_t deadline_us = 0U;
    if (!checked_add_u64(
            core->next_uplink_due_us, core->frame_deadline_slack_us,
            &deadline_us) || monotonic_now_us > deadline_us) {
        core->metadata.deadline_failures++;
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
        goto cleanup;
    }
    if (core->uplink_queue.count >= core->queue_capacity_frames) {
        core->metadata.queue_overflows++;
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_QUEUE_OVERFLOW,
            ESP_ERR_NO_MEM);
        goto cleanup;
    }
    call020_media_slot_t *slot = queue_tail(
        &core->uplink_queue, core->queue_capacity_frames);
    secure_zero(slot, sizeof(*slot));
    slot->sequence = core->next_uplink_sequence;
    slot->source_time_ns = source_time_ns;
    slot->due_us = core->next_uplink_due_us;
    slot->deadline_us = deadline_us;
    downmix_stereo_to_mono(stereo_values, slot->media);
    core->uplink_queue.count++;
    core->metadata.uplink_frames_accepted++;
    core->next_uplink_sequence++;
    core->last_uplink_source_time_ns = source_time_ns;
    core->has_uplink_source_time = true;
    if (!checked_add_u64(
            core->next_uplink_due_us, CALL020_FRAME_INTERVAL_US,
            &core->next_uplink_due_us)) {
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_INVALID_STATE);
        goto cleanup;
    }
    sync_metadata_depths(core);
    result = ESP_OK;

cleanup:
    secure_zero(stereo_values, CALL020_MEDIA_STEREO_BYTES);
    return result;
}

esp_err_t call020_media_adapter_core_flush_uplink(
    call020_media_adapter_core_t *core,
    uint64_t monotonic_now_us,
    call020_media_wire_write_fn write_wire,
    void *write_user_context)
{
    if (core == NULL || write_wire == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = check_running_time(core, monotonic_now_us);
    if (result != ESP_OK) {
        return result;
    }
    if (core->uplink_queue.count == 0U) {
        return ESP_ERR_NOT_FOUND;
    }
    call020_media_slot_t *slot = queue_head(&core->uplink_queue);
    if (monotonic_now_us > slot->deadline_us) {
        core->metadata.deadline_failures++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
    }

    size_t wire_bytes = 0U;
    result = encode_uplink(core, slot, &wire_bytes);
    if (result != ESP_OK) {
        secure_zero(core->wire_scratch, sizeof(core->wire_scratch));
        return terminate(
            core, CALL020_MEDIA_TERMINAL_PROTOCOL, result);
    }
    call020_media_transfer_result_t transfer = write_wire(
        write_user_context, core->wire_scratch, wire_bytes,
        slot->deadline_us);
    secure_zero(core->wire_scratch, sizeof(core->wire_scratch));

    switch (transfer) {
    case CALL020_MEDIA_TRANSFER_OK:
        queue_pop(&core->uplink_queue, core->queue_capacity_frames);
        core->metadata.uplink_frames_sent++;
        sync_metadata_depths(core);
        return ESP_OK;
    case CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS:
        core->metadata.zero_progress_timeouts++;
        return ESP_ERR_TIMEOUT;
    case CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL:
        core->metadata.terminal_timeouts++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_PARTIAL_TIMEOUT,
            ESP_ERR_INVALID_RESPONSE);
    case CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN:
        core->metadata.terminal_timeouts++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_UNKNOWN_TIMEOUT,
            ESP_ERR_INVALID_RESPONSE);
    case CALL020_MEDIA_TRANSFER_ERROR:
    default:
        return terminate(
            core, CALL020_MEDIA_TERMINAL_TRANSPORT, ESP_FAIL);
    }
}

esp_err_t call020_media_adapter_core_offer_downlink_wire(
    call020_media_adapter_core_t *core,
    uint8_t *wire,
    size_t wire_bytes,
    uint64_t monotonic_now_us)
{
    if (wire == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = ESP_ERR_INVALID_ARG;
    if (core == NULL) {
        goto cleanup;
    }
    result = check_running_time(core, monotonic_now_us);
    if (result != ESP_OK) {
        goto cleanup;
    }
    if (wire_bytes < CALL020_MIN_WIRE_BYTES ||
        wire_bytes > CALL020_MEDIA_WIRE_MAX_BYTES) {
        result = protocol_failure(core);
        goto cleanup;
    }
    if (memcmp(wire, CALL020_WIRE_MAGIC, sizeof(CALL020_WIRE_MAGIC)) != 0 ||
        wire[4] != CALL020_WIRE_VERSION ||
        wire[5] != CALL020_DIRECTION_DOWNLINK ||
        wire[6] != CALL020_ROLE_GUARDIAN ||
        wire[7] != CALL020_ROLE_DEVICE) {
        result = protocol_failure(core);
        goto cleanup;
    }

    uint64_t sequence = get_be64(&wire[8]);
    uint64_t source_time_ns = get_be64(&wire[16]);
    uint16_t lengths[4];
    size_t expected_size = CALL020_MEDIA_WIRE_HEADER_BYTES +
        CALL020_MEDIA_MONO_BYTES + CALL020_MEDIA_WIRE_CRC_BYTES;
    for (size_t index = 0U; index < 4U; ++index) {
        lengths[index] = get_be16(&wire[24U + index * 2U]);
        if (lengths[index] == 0U ||
            lengths[index] > CALL020_MEDIA_IDENTIFIER_MAX_BYTES) {
            result = protocol_failure(core);
            goto cleanup;
        }
        expected_size += lengths[index];
    }
    if (get_be16(&wire[32]) != CALL020_MEDIA_MONO_BYTES ||
        expected_size != wire_bytes) {
        result = protocol_failure(core);
        goto cleanup;
    }
    uint32_t expected_crc = get_be32(
        &wire[wire_bytes - CALL020_MEDIA_WIRE_CRC_BYTES]);
    if (crc32(wire, wire_bytes - CALL020_MEDIA_WIRE_CRC_BYTES) !=
        expected_crc) {
        result = protocol_failure(core);
        goto cleanup;
    }

    const char *expected_identifiers[4] = {
        core->session_id,
        core->guardian_id,
        core->device_id,
        core->downlink_clock_id,
    };
    size_t cursor = CALL020_MEDIA_WIRE_HEADER_BYTES;
    for (size_t index = 0U; index < 4U; ++index) {
        if (!bytes_equal_string(
                &wire[cursor], lengths[index], expected_identifiers[index])) {
            result = protocol_failure(core);
            goto cleanup;
        }
        cursor += lengths[index];
    }
    if (sequence > INT64_MAX || source_time_ns > INT64_MAX ||
        sequence != core->expected_downlink_sequence ||
        (core->has_downlink_source_time &&
         source_time_ns <= core->last_downlink_source_time_ns)) {
        result = protocol_failure(core);
        goto cleanup;
    }
    if (core->downlink_queue.count >= core->queue_capacity_frames) {
        core->metadata.queue_overflows++;
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_QUEUE_OVERFLOW,
            ESP_ERR_NO_MEM);
        goto cleanup;
    }

    if (!core->has_downlink_playout_epoch) {
        if (!checked_add_u64(
                monotonic_now_us, core->downlink_playout_delay_us,
                &core->next_downlink_due_us)) {
            result = terminate(
                core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
                ESP_ERR_INVALID_STATE);
            goto cleanup;
        }
        core->has_downlink_playout_epoch = true;
    }
    uint64_t deadline_us = 0U;
    if (!checked_add_u64(
            core->next_downlink_due_us, core->frame_deadline_slack_us,
            &deadline_us) || monotonic_now_us > deadline_us) {
        core->metadata.deadline_failures++;
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
        goto cleanup;
    }

    call020_media_slot_t *slot = queue_tail(
        &core->downlink_queue, core->queue_capacity_frames);
    secure_zero(slot, sizeof(*slot));
    slot->sequence = sequence;
    slot->source_time_ns = source_time_ns;
    slot->due_us = core->next_downlink_due_us;
    slot->deadline_us = deadline_us;
    memcpy(slot->media, &wire[cursor], CALL020_MEDIA_MONO_BYTES);
    core->downlink_queue.count++;
    core->expected_downlink_sequence++;
    core->last_downlink_source_time_ns = source_time_ns;
    core->has_downlink_source_time = true;
    core->metadata.downlink_frames_accepted++;
    if (!checked_add_u64(
            core->next_downlink_due_us, CALL020_FRAME_INTERVAL_US,
            &core->next_downlink_due_us)) {
        result = terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_INVALID_STATE);
        goto cleanup;
    }
    sync_metadata_depths(core);
    result = ESP_OK;

cleanup:
    secure_zero(wire, wire_bytes);
    return result;
}

esp_err_t call020_media_adapter_core_render_downlink(
    call020_media_adapter_core_t *core,
    uint64_t monotonic_now_us,
    call020_media_stereo_write_fn write_stereo,
    void *write_user_context)
{
    if (core == NULL || write_stereo == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = check_running_time(core, monotonic_now_us);
    if (result != ESP_OK) {
        return result;
    }
    if (core->downlink_queue.count == 0U) {
        return ESP_ERR_NOT_FOUND;
    }
    call020_media_slot_t *slot = queue_head(&core->downlink_queue);
    if (monotonic_now_us < slot->due_us) {
        return ESP_ERR_INVALID_STATE;
    }
    if (monotonic_now_us > slot->deadline_us) {
        core->metadata.deadline_failures++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
    }

    expand_mono_to_stereo(slot->media, core->stereo_scratch);
    result = write_stereo(
        write_user_context, core->stereo_scratch,
        CALL020_MEDIA_STEREO_VALUES, slot->deadline_us);
    secure_zero(core->stereo_scratch, sizeof(core->stereo_scratch));
    if (result != ESP_OK) {
        return terminate(
            core, CALL020_MEDIA_TERMINAL_AUDIO_OUTPUT, result);
    }
    queue_pop(&core->downlink_queue, core->queue_capacity_frames);
    core->metadata.downlink_frames_rendered++;
    sync_metadata_depths(core);
    return ESP_OK;
}

esp_err_t call020_media_adapter_core_note_stream_timeout(
    call020_media_adapter_core_t *core,
    call020_media_transfer_result_t timeout_progress)
{
    if (core == NULL || !core->initialized ||
        core->state != CALL020_MEDIA_CORE_RUNNING) {
        return ESP_ERR_INVALID_STATE;
    }
    switch (timeout_progress) {
    case CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS:
        core->metadata.zero_progress_timeouts++;
        return ESP_ERR_TIMEOUT;
    case CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL:
        core->metadata.terminal_timeouts++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_PARTIAL_TIMEOUT,
            ESP_ERR_INVALID_RESPONSE);
    case CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN:
        core->metadata.terminal_timeouts++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_UNKNOWN_TIMEOUT,
            ESP_ERR_INVALID_RESPONSE);
    case CALL020_MEDIA_TRANSFER_OK:
    case CALL020_MEDIA_TRANSFER_ERROR:
    default:
        return ESP_ERR_INVALID_ARG;
    }
}

esp_err_t call020_media_adapter_core_tick(
    call020_media_adapter_core_t *core, uint64_t monotonic_now_us)
{
    esp_err_t result = check_running_time(core, monotonic_now_us);
    if (result != ESP_OK) {
        return result;
    }
    if (core->uplink_queue.count > 0U &&
        monotonic_now_us > queue_head(&core->uplink_queue)->deadline_us) {
        core->metadata.deadline_failures++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
    }
    if (core->downlink_queue.count > 0U &&
        monotonic_now_us > queue_head(&core->downlink_queue)->deadline_us) {
        core->metadata.deadline_failures++;
        return terminate(
            core, CALL020_MEDIA_TERMINAL_FRAME_DEADLINE,
            ESP_ERR_TIMEOUT);
    }
    return ESP_OK;
}

esp_err_t call020_media_adapter_core_stop(call020_media_adapter_core_t *core)
{
    if (core == NULL || !core->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    bool was_terminal = core->state == CALL020_MEDIA_CORE_TERMINAL;
    call020_media_terminal_reason_t prior_reason = core->terminal_reason;
    clear_owned_media(core);
    core->state = was_terminal
        ? CALL020_MEDIA_CORE_TERMINAL
        : CALL020_MEDIA_CORE_STOPPED;
    core->terminal_reason = was_terminal
        ? prior_reason
        : CALL020_MEDIA_TERMINAL_NONE;
    esp_err_t result = force_pa_off(core);
    if (result != ESP_OK) {
        core->state = CALL020_MEDIA_CORE_TERMINAL;
        core->terminal_reason = CALL020_MEDIA_TERMINAL_PA_OFF;
    }
    sync_metadata_depths(core);
    return result;
}

esp_err_t call020_media_adapter_core_deinit(call020_media_adapter_core_t *core)
{
    if (core == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = ESP_OK;
    if (core->initialized && core->force_pa_off != NULL) {
        clear_owned_media(core);
        result = force_pa_off(core);
    }
    secure_zero(core, sizeof(*core));
    return result;
}

esp_err_t call020_media_adapter_core_get_metadata(
    const call020_media_adapter_core_t *core,
    call020_media_adapter_metadata_t *metadata)
{
    if (core == NULL || metadata == NULL || !core->initialized) {
        return ESP_ERR_INVALID_ARG;
    }
    *metadata = core->metadata;
    metadata->state = core->state;
    metadata->terminal_reason = core->terminal_reason;
    metadata->uplink_queue_depth = core->uplink_queue.count;
    metadata->downlink_queue_depth = core->downlink_queue.count;
    return ESP_OK;
}
