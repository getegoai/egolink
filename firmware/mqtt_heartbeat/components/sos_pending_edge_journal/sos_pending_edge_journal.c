#include "sos_pending_edge_journal.h"

#include <string.h>

#define SOS_PENDING_JOURNAL_MAGIC UINT32_C(0x534f534a)
#define SOS_PENDING_WIRE_MAGIC UINT32_C(0x45534f53)
#define SOS_PENDING_WIRE_HEADER_BYTES UINT16_C(48)
#define SOS_PENDING_WIRE_CRC_OFFSET 316U
#define SOS_PENDING_WIRE_DEVICE_OFFSET 48U
#define SOS_PENDING_WIRE_SESSION_OFFSET \
    (SOS_PENDING_WIRE_DEVICE_OFFSET + EGOLINK_OUTBOX_ID_CAPACITY)
#define SOS_PENDING_WIRE_RESERVED_OFFSET \
    (SOS_PENDING_WIRE_SESSION_OFFSET + EGOLINK_OUTBOX_ID_CAPACITY)

typedef struct {
    uint32_t magic;
    egolink_sos_pending_edge_storage_t storage;
    char expected_device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint8_t wire[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
} sos_pending_journal_internal_t;

_Static_assert(
    SOS_PENDING_WIRE_SESSION_OFFSET == 177U,
    "pending-edge session wire offset changed");
_Static_assert(
    SOS_PENDING_WIRE_RESERVED_OFFSET == 306U,
    "pending-edge reserved wire offset changed");
_Static_assert(
    SOS_PENDING_WIRE_CRC_OFFSET + sizeof(uint32_t) ==
        EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES,
    "pending-edge wire size changed");
_Static_assert(
    sizeof(sos_pending_journal_internal_t) <=
        EGOLINK_SOS_PENDING_EDGE_CONTEXT_BYTES,
    "pending-edge journal context is too small");

static sos_pending_journal_internal_t *journal_internal(
    egolink_sos_pending_edge_journal_t *journal)
{
    return (sos_pending_journal_internal_t *)(void *)journal->opaque;
}

static const sos_pending_journal_internal_t *journal_internal_const(
    const egolink_sos_pending_edge_journal_t *journal)
{
    return (const sos_pending_journal_internal_t *)(const void *)
        journal->opaque;
}

static void secure_clear(void *data, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)data;
    while (cursor != NULL && length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
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

static bool safe_identifier(const char *value)
{
    const size_t length = bounded_string_length(
        value, EGOLINK_OUTBOX_ID_CAPACITY);
    if (length == 0U || length >= EGOLINK_OUTBOX_ID_CAPACITY) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        const char character = value[index];
        const bool alphanumeric =
            (character >= 'A' && character <= 'Z') ||
            (character >= 'a' && character <= 'z') ||
            (character >= '0' && character <= '9');
        if ((!alphanumeric && index == 0U) ||
            (!alphanumeric && character != '.' && character != '_' &&
             character != ':' && character != '@' && character != '-')) {
            return false;
        }
    }
    return true;
}

static bool valid_internal(const sos_pending_journal_internal_t *internal)
{
    return internal != NULL && internal->magic == SOS_PENDING_JOURNAL_MAGIC &&
        internal->storage.load_record != NULL &&
        internal->storage.store_record != NULL &&
        internal->storage.clear_record != NULL &&
        safe_identifier(internal->expected_device_id);
}

static bool valid_record(
    const sos_pending_journal_internal_t *internal,
    const egolink_sos_pending_edge_record_t *record)
{
    return record != NULL && safe_identifier(record->device_id) &&
        safe_identifier(record->session_id) &&
        strcmp(record->device_id, internal->expected_device_id) == 0 &&
        record->boot_count <= EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX &&
        record->source_sequence <=
            EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX &&
        record->edge_time_ms <=
            EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX;
}

static bool record_equal(
    const egolink_sos_pending_edge_record_t *left,
    const egolink_sos_pending_edge_record_t *right)
{
    return left->boot_count == right->boot_count &&
        left->source_sequence == right->source_sequence &&
        left->edge_time_ms == right->edge_time_ms &&
        strcmp(left->device_id, right->device_id) == 0 &&
        strcmp(left->session_id, right->session_id) == 0;
}

static void put_u16_le(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value & UINT16_C(0xff));
    destination[1] = (uint8_t)((value >> 8U) & UINT16_C(0xff));
}

static void put_u32_le(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value & UINT32_C(0xff));
    destination[1] = (uint8_t)((value >> 8U) & UINT32_C(0xff));
    destination[2] = (uint8_t)((value >> 16U) & UINT32_C(0xff));
    destination[3] = (uint8_t)((value >> 24U) & UINT32_C(0xff));
}

static void put_u64_le(uint8_t *destination, uint64_t value)
{
    for (uint32_t shift = 0U; shift < 64U; shift += 8U) {
        destination[shift / 8U] =
            (uint8_t)((value >> shift) & UINT64_C(0xff));
    }
}

static uint16_t get_u16_le(const uint8_t *source)
{
    return (uint16_t)((uint16_t)source[0] |
        (uint16_t)((uint16_t)source[1] << 8U));
}

static uint32_t get_u32_le(const uint8_t *source)
{
    return (uint32_t)source[0] |
        ((uint32_t)source[1] << 8U) |
        ((uint32_t)source[2] << 16U) |
        ((uint32_t)source[3] << 24U);
}

static uint64_t get_u64_le(const uint8_t *source)
{
    uint64_t value = UINT64_C(0);
    for (uint32_t shift = 0U; shift < 64U; shift += 8U) {
        value |= (uint64_t)source[shift / 8U] << shift;
    }
    return value;
}

static uint32_t crc32_bytes(const uint8_t *data, size_t length)
{
    uint32_t crc = UINT32_C(0xffffffff);
    for (size_t index = 0U; index < length; ++index) {
        crc ^= (uint32_t)data[index];
        for (uint32_t bit = 0U; bit < 8U; ++bit) {
            const uint32_t mask = (uint32_t)(0U - (crc & UINT32_C(1)));
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) & mask);
        }
    }
    return ~crc;
}

static void encode_record(
    const egolink_sos_pending_edge_record_t *record,
    uint8_t wire[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES])
{
    (void)memset(wire, 0, EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES);
    const size_t device_length = bounded_string_length(
        record->device_id, EGOLINK_OUTBOX_ID_CAPACITY);
    const size_t session_length = bounded_string_length(
        record->session_id, EGOLINK_OUTBOX_ID_CAPACITY);
    put_u32_le(&wire[0], SOS_PENDING_WIRE_MAGIC);
    put_u16_le(&wire[4], EGOLINK_SOS_PENDING_EDGE_FORMAT_VERSION);
    put_u16_le(&wire[6], SOS_PENDING_WIRE_HEADER_BYTES);
    put_u32_le(&wire[8], (uint32_t)EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES);
    put_u32_le(&wire[12], UINT32_C(0));
    put_u64_le(&wire[16], record->boot_count);
    put_u64_le(&wire[24], record->source_sequence);
    put_u64_le(&wire[32], record->edge_time_ms);
    put_u16_le(&wire[40], (uint16_t)device_length);
    put_u16_le(&wire[42], (uint16_t)session_length);
    put_u32_le(&wire[44], UINT32_C(0));
    (void)memcpy(
        &wire[SOS_PENDING_WIRE_DEVICE_OFFSET],
        record->device_id,
        device_length);
    (void)memcpy(
        &wire[SOS_PENDING_WIRE_SESSION_OFFSET],
        record->session_id,
        session_length);
    put_u32_le(
        &wire[SOS_PENDING_WIRE_CRC_OFFSET],
        crc32_bytes(wire, SOS_PENDING_WIRE_CRC_OFFSET));
}

static egolink_sos_pending_edge_status_t decode_record(
    const sos_pending_journal_internal_t *internal,
    const uint8_t wire[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES],
    egolink_sos_pending_edge_record_t *record)
{
    if (get_u32_le(&wire[0]) != SOS_PENDING_WIRE_MAGIC ||
        get_u16_le(&wire[4]) !=
            EGOLINK_SOS_PENDING_EDGE_FORMAT_VERSION ||
        get_u16_le(&wire[6]) != SOS_PENDING_WIRE_HEADER_BYTES ||
        get_u32_le(&wire[8]) !=
            (uint32_t)EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        return EGOLINK_SOS_PENDING_EDGE_FORMAT_MISMATCH;
    }
    if (get_u32_le(&wire[12]) != UINT32_C(0) ||
        get_u32_le(&wire[44]) != UINT32_C(0)) {
        return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
    }
    for (size_t index = SOS_PENDING_WIRE_RESERVED_OFFSET;
         index < SOS_PENDING_WIRE_CRC_OFFSET;
         ++index) {
        if (wire[index] != 0U) {
            return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
        }
    }
    const uint32_t stored_crc = get_u32_le(
        &wire[SOS_PENDING_WIRE_CRC_OFFSET]);
    if (stored_crc != crc32_bytes(wire, SOS_PENDING_WIRE_CRC_OFFSET)) {
        return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
    }
    const uint16_t device_length = get_u16_le(&wire[40]);
    const uint16_t session_length = get_u16_le(&wire[42]);
    if (device_length == 0U ||
        device_length >= (uint16_t)EGOLINK_OUTBOX_ID_CAPACITY ||
        session_length == 0U ||
        session_length >= (uint16_t)EGOLINK_OUTBOX_ID_CAPACITY) {
        return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
    }
    for (size_t index = (size_t)device_length;
         index < EGOLINK_OUTBOX_ID_CAPACITY;
         ++index) {
        if (wire[SOS_PENDING_WIRE_DEVICE_OFFSET + index] != 0U) {
            return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
        }
    }
    for (size_t index = (size_t)session_length;
         index < EGOLINK_OUTBOX_ID_CAPACITY;
         ++index) {
        if (wire[SOS_PENDING_WIRE_SESSION_OFFSET + index] != 0U) {
            return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
        }
    }

    (void)memset(record, 0, sizeof(*record));
    (void)memcpy(
        record->device_id,
        &wire[SOS_PENDING_WIRE_DEVICE_OFFSET],
        (size_t)device_length);
    (void)memcpy(
        record->session_id,
        &wire[SOS_PENDING_WIRE_SESSION_OFFSET],
        (size_t)session_length);
    record->boot_count = get_u64_le(&wire[16]);
    record->source_sequence = get_u64_le(&wire[24]);
    record->edge_time_ms = get_u64_le(&wire[32]);
    if (bounded_string_length(
            record->device_id, sizeof(record->device_id)) !=
            (size_t)device_length ||
        bounded_string_length(
            record->session_id, sizeof(record->session_id)) !=
            (size_t)session_length) {
        secure_clear(record, sizeof(*record));
        return EGOLINK_SOS_PENDING_EDGE_CORRUPT;
    }
    if (!valid_record(internal, record)) {
        const bool wrong_device = safe_identifier(record->device_id) &&
            strcmp(record->device_id, internal->expected_device_id) != 0;
        secure_clear(record, sizeof(*record));
        return wrong_device
            ? EGOLINK_SOS_PENDING_EDGE_IDENTITY_MISMATCH
            : EGOLINK_SOS_PENDING_EDGE_INVALID_RECORD;
    }
    return EGOLINK_SOS_PENDING_EDGE_OK;
}

static egolink_sos_pending_edge_status_t load_internal(
    sos_pending_journal_internal_t *internal,
    egolink_sos_pending_edge_record_t *record)
{
    size_t actual_length = 0U;
    (void)memset(internal->wire, 0, sizeof(internal->wire));
    const egolink_sos_pending_edge_storage_result_t storage_status =
        internal->storage.load_record(
            internal->storage.context,
            internal->wire,
            sizeof(internal->wire),
            &actual_length);
    if (storage_status == EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND) {
        secure_clear(internal->wire, sizeof(internal->wire));
        return EGOLINK_SOS_PENDING_EDGE_NOT_FOUND;
    }
    if (storage_status != EGOLINK_SOS_PENDING_EDGE_STORAGE_OK) {
        secure_clear(internal->wire, sizeof(internal->wire));
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_ERROR;
    }
    if (actual_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        secure_clear(internal->wire, sizeof(internal->wire));
        return EGOLINK_SOS_PENDING_EDGE_SIZE_MISMATCH;
    }
    const egolink_sos_pending_edge_status_t status =
        decode_record(internal, internal->wire, record);
    secure_clear(internal->wire, sizeof(internal->wire));
    return status;
}

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_init(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_storage_t *storage,
    const char *expected_device_id)
{
    if (journal == NULL || storage == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT;
    }
    if (storage->load_record == NULL || storage->store_record == NULL ||
        storage->clear_record == NULL || !safe_identifier(expected_device_id)) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_CONFIG;
    }
    secure_clear(journal, sizeof(*journal));
    sos_pending_journal_internal_t *internal = journal_internal(journal);
    internal->storage = *storage;
    const size_t device_length = bounded_string_length(
        expected_device_id, sizeof(internal->expected_device_id));
    (void)memcpy(
        internal->expected_device_id, expected_device_id, device_length + 1U);
    internal->magic = SOS_PENDING_JOURNAL_MAGIC;
    return EGOLINK_SOS_PENDING_EDGE_OK;
}

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_load(
    egolink_sos_pending_edge_journal_t *journal,
    egolink_sos_pending_edge_record_t *record)
{
    if (journal == NULL || record == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT;
    }
    (void)memset(record, 0, sizeof(*record));
    sos_pending_journal_internal_t *internal = journal_internal(journal);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED;
    }
    return load_internal(internal, record);
}

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_store(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_record_t *record)
{
    if (journal == NULL || record == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT;
    }
    sos_pending_journal_internal_t *internal = journal_internal(journal);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED;
    }
    if (!valid_record(internal, record)) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_RECORD;
    }

    egolink_sos_pending_edge_record_t existing;
    egolink_sos_pending_edge_status_t status =
        load_internal(internal, &existing);
    if (status == EGOLINK_SOS_PENDING_EDGE_OK) {
        const bool duplicate = record_equal(&existing, record);
        secure_clear(&existing, sizeof(existing));
        return duplicate
            ? EGOLINK_SOS_PENDING_EDGE_DUPLICATE
            : EGOLINK_SOS_PENDING_EDGE_OCCUPIED;
    }
    secure_clear(&existing, sizeof(existing));
    if (status != EGOLINK_SOS_PENDING_EDGE_NOT_FOUND) {
        return status;
    }

    encode_record(record, internal->wire);
    const egolink_sos_pending_edge_storage_result_t store_status =
        internal->storage.store_record(
            internal->storage.context,
            internal->wire,
            sizeof(internal->wire));

    status = load_internal(internal, &existing);
    const bool exact_readback =
        status == EGOLINK_SOS_PENDING_EDGE_OK &&
        record_equal(&existing, record);
    const bool different_readback =
        status == EGOLINK_SOS_PENDING_EDGE_OK && !exact_readback;
    secure_clear(&existing, sizeof(existing));
    if (exact_readback) {
        return EGOLINK_SOS_PENDING_EDGE_OK;
    }
    if (different_readback) {
        return EGOLINK_SOS_PENDING_EDGE_OCCUPIED;
    }
    if (store_status == EGOLINK_SOS_PENDING_EDGE_STORAGE_OK &&
        status == EGOLINK_SOS_PENDING_EDGE_NOT_FOUND) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_ERROR;
    }
    return status == EGOLINK_SOS_PENDING_EDGE_NOT_FOUND
        ? EGOLINK_SOS_PENDING_EDGE_STORAGE_ERROR
        : status;
}

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_clear(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_record_t *expected_record)
{
    if (journal == NULL || expected_record == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT;
    }
    sos_pending_journal_internal_t *internal = journal_internal(journal);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED;
    }
    if (!valid_record(internal, expected_record)) {
        return EGOLINK_SOS_PENDING_EDGE_INVALID_RECORD;
    }

    egolink_sos_pending_edge_record_t existing;
    egolink_sos_pending_edge_status_t status =
        load_internal(internal, &existing);
    if (status == EGOLINK_SOS_PENDING_EDGE_NOT_FOUND) {
        return status;
    }
    if (status != EGOLINK_SOS_PENDING_EDGE_OK) {
        secure_clear(&existing, sizeof(existing));
        return status;
    }
    if (!record_equal(&existing, expected_record)) {
        secure_clear(&existing, sizeof(existing));
        return EGOLINK_SOS_PENDING_EDGE_OCCUPIED;
    }
    secure_clear(&existing, sizeof(existing));

    (void)internal->storage.clear_record(internal->storage.context);
    status = load_internal(internal, &existing);
    if (status == EGOLINK_SOS_PENDING_EDGE_NOT_FOUND) {
        return EGOLINK_SOS_PENDING_EDGE_OK;
    }
    const bool same_record = status == EGOLINK_SOS_PENDING_EDGE_OK &&
        record_equal(&existing, expected_record);
    secure_clear(&existing, sizeof(existing));
    if (status == EGOLINK_SOS_PENDING_EDGE_OK) {
        return same_record
            ? EGOLINK_SOS_PENDING_EDGE_CLEAR_FAILED
            : EGOLINK_SOS_PENDING_EDGE_OCCUPIED;
    }
    return status;
}

bool egolink_sos_pending_edge_journal_is_initialized(
    const egolink_sos_pending_edge_journal_t *journal)
{
    return journal != NULL && valid_internal(journal_internal_const(journal));
}

bool egolink_sos_pending_edge_journal_matches_device(
    const egolink_sos_pending_edge_journal_t *journal,
    const char *device_id)
{
    if (!egolink_sos_pending_edge_journal_is_initialized(journal) ||
        !safe_identifier(device_id)) {
        return false;
    }
    return strcmp(
        journal_internal_const(journal)->expected_device_id,
        device_id) == 0;
}

size_t egolink_sos_pending_edge_record_bytes(void)
{
    return EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES;
}

const char *egolink_sos_pending_edge_status_name(
    egolink_sos_pending_edge_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_PENDING_EDGE_OK: return "ok";
    case EGOLINK_SOS_PENDING_EDGE_NOT_FOUND: return "not_found";
    case EGOLINK_SOS_PENDING_EDGE_DUPLICATE: return "duplicate";
    case EGOLINK_SOS_PENDING_EDGE_OCCUPIED: return "occupied";
    case EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_SOS_PENDING_EDGE_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_SOS_PENDING_EDGE_STORAGE_ERROR: return "storage_error";
    case EGOLINK_SOS_PENDING_EDGE_SIZE_MISMATCH: return "size_mismatch";
    case EGOLINK_SOS_PENDING_EDGE_FORMAT_MISMATCH: return "format_mismatch";
    case EGOLINK_SOS_PENDING_EDGE_CORRUPT: return "corrupt";
    case EGOLINK_SOS_PENDING_EDGE_IDENTITY_MISMATCH:
        return "identity_mismatch";
    case EGOLINK_SOS_PENDING_EDGE_INVALID_RECORD: return "invalid_record";
    case EGOLINK_SOS_PENDING_EDGE_CLEAR_FAILED: return "clear_failed";
    default: return "unknown";
    }
}
