#ifndef EGOLINK_SOS_PENDING_EDGE_JOURNAL_H
#define EGOLINK_SOS_PENDING_EDGE_JOURNAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "persistent_priority_outbox.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_PENDING_EDGE_CONTRACT_VERSION \
    "egolink.sos_pending_edge_journal.v0.1"
#define EGOLINK_SOS_PENDING_EDGE_FORMAT_VERSION UINT16_C(1)
#define EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES 320U
#define EGOLINK_SOS_PENDING_EDGE_CONTEXT_BYTES 512U
#define EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX \
    UINT64_C(9007199254740991)

typedef enum {
    EGOLINK_SOS_PENDING_EDGE_STORAGE_OK = 0,
    EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND,
    EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR,
} egolink_sos_pending_edge_storage_result_t;

/*
 * The backend owns exactly one logical fixed-size record. store_record must atomically
 * replace it and may return OK only after all 320 bytes are durable. clear_record
 * may return OK only after durable absence; NOT_FOUND also means durable
 * absence. A failed callback is ambiguous, so the component always reads back
 * before deciding whether the requested state became durable.
 *
 * These callbacks are synchronous and must not re-enter the journal, runtime,
 * outbox or dispatcher. No NVS/partition implementation is supplied here.
 */
typedef egolink_sos_pending_edge_storage_result_t
(*egolink_sos_pending_edge_load_fn)(
    void *context,
    void *destination,
    size_t destination_capacity,
    size_t *actual_length);

typedef egolink_sos_pending_edge_storage_result_t
(*egolink_sos_pending_edge_store_fn)(
    void *context,
    const void *source,
    size_t source_length);

typedef egolink_sos_pending_edge_storage_result_t
(*egolink_sos_pending_edge_clear_fn)(void *context);

typedef struct {
    void *context;
    egolink_sos_pending_edge_load_fn load_record;
    egolink_sos_pending_edge_store_fn store_record;
    egolink_sos_pending_edge_clear_fn clear_record;
} egolink_sos_pending_edge_storage_t;

/* Pointer-free decoded lineage. It is not written as a raw C struct. */
typedef struct {
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint64_t boot_count;
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint64_t source_sequence;
    uint64_t edge_time_ms;
} egolink_sos_pending_edge_record_t;

typedef enum {
    EGOLINK_SOS_PENDING_EDGE_OK = 0,
    EGOLINK_SOS_PENDING_EDGE_NOT_FOUND,
    EGOLINK_SOS_PENDING_EDGE_DUPLICATE,
    EGOLINK_SOS_PENDING_EDGE_OCCUPIED,
    EGOLINK_SOS_PENDING_EDGE_INVALID_ARGUMENT,
    EGOLINK_SOS_PENDING_EDGE_INVALID_CONFIG,
    EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED,
    EGOLINK_SOS_PENDING_EDGE_STORAGE_ERROR,
    EGOLINK_SOS_PENDING_EDGE_SIZE_MISMATCH,
    EGOLINK_SOS_PENDING_EDGE_FORMAT_MISMATCH,
    EGOLINK_SOS_PENDING_EDGE_CORRUPT,
    EGOLINK_SOS_PENDING_EDGE_IDENTITY_MISMATCH,
    EGOLINK_SOS_PENDING_EDGE_INVALID_RECORD,
    EGOLINK_SOS_PENDING_EDGE_CLEAR_FAILED,
} egolink_sos_pending_edge_status_t;

/* Caller should allocate this opaque object statically, not on a task stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SOS_PENDING_EDGE_CONTEXT_BYTES];
} egolink_sos_pending_edge_journal_t;

/*
 * Init only binds callbacks/identity; it performs no load, store, clear or
 * erase. expected_device_id is copied and constrains every stored/recovered
 * record. The fixed wire encoding is explicit little-endian fields plus bounded ASCII
 * safe IDs and a CRC32. It contains no pointer, payload, coordinate or media.
 * CRC32 is accidental-corruption/tear detection, not authentication or
 * confidentiality. Exactly one external task or mutex must serialize this
 * lock-free journal with F, the orchestrator, outbox, dispatcher and ACK path.
 */
egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_init(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_storage_t *storage,
    const char *expected_device_id);

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_load(
    egolink_sos_pending_edge_journal_t *journal,
    egolink_sos_pending_edge_record_t *record);

/*
 * Existing exact bytes return DUPLICATE. A different valid pending record
 * returns OCCUPIED and is never overwritten. OK/DUPLICATE mean readback proved
 * the requested record durable, including after an ambiguous store error.
 * This one-record engineering seam cannot accept another physical edge until
 * the first is durably enqueued and cleared.
 */
egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_store(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_record_t *record);

/*
 * Clear is compare-before-delete: a different valid record is never erased.
 * OK/NOT_FOUND mean readback proved durable absence. Any other result must be
 * treated as retained/ambiguous and safely replayed later.
 */
egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_clear(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_record_t *expected_record);

bool egolink_sos_pending_edge_journal_is_initialized(
    const egolink_sos_pending_edge_journal_t *journal);

bool egolink_sos_pending_edge_journal_matches_device(
    const egolink_sos_pending_edge_journal_t *journal,
    const char *device_id);

size_t egolink_sos_pending_edge_record_bytes(void);

const char *egolink_sos_pending_edge_status_name(
    egolink_sos_pending_edge_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_PENDING_EDGE_JOURNAL_H */
