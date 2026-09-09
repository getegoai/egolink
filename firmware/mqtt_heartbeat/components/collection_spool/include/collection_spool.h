#ifndef EGOLINK_COLLECTION_SPOOL_H
#define EGOLINK_COLLECTION_SPOOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Caller serializes all operations. No allocator, task, transport, or clock is
 * owned here. Callbacks must finish durable writes before returning true.
 * Use only a dedicated, checked region: init never formats foreign contents.
 * Entirely foreign media is rejected. Beside a valid spool generation, unknown
 * sectors are preserved in quarantine (e.g. a cut during ACKed-sector erase),
 * so unaffected committed records can still drain. Report quarantine as a
 * storage fault/capacity loss; it is never automatically erased/reclaimed. */
#ifndef COLLECTION_SPOOL_MAX_SECTORS
#define COLLECTION_SPOOL_MAX_SECTORS 256U
#endif
#define COLLECTION_SPOOL_MAX_SOURCES 16U
#define COLLECTION_SPOOL_SECTOR_HEADER_BYTES 48U
#define COLLECTION_SPOOL_RECORD_HEADER_BYTES 48U

typedef enum {
    COLLECTION_SPOOL_OK = 0,
    COLLECTION_SPOOL_EMPTY,
    COLLECTION_SPOOL_FULL,
    COLLECTION_SPOOL_PROTECTED_FULL,
    COLLECTION_SPOOL_TOO_LARGE,
    COLLECTION_SPOOL_BAD_ARGUMENT,
    COLLECTION_SPOOL_IO_ERROR,
    COLLECTION_SPOOL_FOREIGN_DATA,
    COLLECTION_SPOOL_CORRUPT,
    COLLECTION_SPOOL_ACK_MISMATCH,
    COLLECTION_SPOOL_BUFFER_TOO_SMALL
} collection_spool_result_t;

typedef enum {
    COLLECTION_SPOOL_DATA = 0,
    COLLECTION_SPOOL_METADATA = 1,
    /* Internal eviction intent, exposed to the uploader as a loss summary.
     * Its payload is obtained with collection_spool_decode_loss(). */
    COLLECTION_SPOOL_LOSS = 2
} collection_spool_kind_t;

typedef struct {
    void *context;
    bool (*read)(void *, size_t, void *, size_t);
    bool (*write)(void *, size_t, const void *, size_t);
    bool (*erase)(void *, size_t, size_t);
    size_t capacity_bytes;
    size_t erase_bytes;
    uint32_t protected_sectors; /* >= 2, with >= 2 ordinary sectors. */
    bool evict_oldest; /* false: capacity exhaustion returns FULL. */
} collection_spool_config_t;

typedef struct {
    uint64_t sector_generation;
    uint64_t ticket;
    uint32_t sector;
    uint32_t offset;
    uint32_t payload_bytes;
    uint32_t payload_crc32;
} collection_spool_token_t;

typedef struct {
    collection_spool_token_t token;
    collection_spool_kind_t kind;
    uint32_t source_id; /* Stable collector source enum, not a hash. */
    uint64_t source_seq;
} collection_spool_record_t;

typedef struct {
    uint32_t source_id;
    uint32_t records;
    uint64_t payload_bytes;
    uint64_t first_source_seq;
    uint64_t last_source_seq;
    uint64_t first_ticket;
    uint64_t last_ticket;
} collection_spool_loss_source_t;

typedef struct {
    uint32_t source_count;
    uint64_t evicted_records_total;
    uint64_t evicted_bytes_total;
    collection_spool_loss_source_t sources[COLLECTION_SPOOL_MAX_SOURCES];
} collection_spool_loss_t;

typedef struct {
    uint64_t pending_records;
    uint64_t pending_payload_bytes;
    uint64_t protected_pending_records;
    uint64_t protected_retained_bytes;
    uint64_t evicted_records;
    uint64_t evicted_payload_bytes;
    uint64_t acked_records_this_boot;
    uint64_t write_bytes_this_boot;
    uint64_t erased_bytes_this_boot;
    uint64_t io_errors_this_boot;
    uint32_t torn_tails;
    uint32_t quarantined_sectors;
    size_t capacity_bytes;
    size_t ordinary_capacity_bytes;
    size_t protected_capacity_bytes;
    size_t max_payload_bytes;
    size_t append_free_bytes; /* Available append bytes, excludes reclaim. */
} collection_spool_stats_t;

/* Public only to permit static allocation; callers must not inspect fields. */
typedef struct {
    uint64_t generation;
    uint32_t end;
    uint32_t records;
    uint32_t pending;
    uint32_t pending_bytes;
    uint8_t state;
    bool sealed;
    bool retired;
} collection_spool_sector_t;

typedef struct {
    collection_spool_config_t config;
    collection_spool_sector_t sectors[COLLECTION_SPOOL_MAX_SECTORS];
    collection_spool_stats_t stats;
    uint64_t generation;
    uint64_t ticket;
    uint32_t sector_count;
    collection_spool_token_t pinned;
    bool has_pin;
    bool initialized;
} collection_spool_t;

collection_spool_result_t collection_spool_init(
    collection_spool_t *, const collection_spool_config_t *);
collection_spool_result_t collection_spool_append(
    collection_spool_t *, collection_spool_kind_t, uint32_t source_id,
    uint64_t source_seq, const void *payload, size_t payload_bytes,
    collection_spool_record_t *written);
collection_spool_result_t collection_spool_peek(
    collection_spool_t *, collection_spool_record_t *, void *payload,
    size_t payload_capacity);
/* Opt-in priority selection without changing the default global FIFO. Finds
 * the oldest pending record with the exact kind/source pair, validates its
 * payload, and pins it before returning. A failed claim never installs a pin. */
collection_spool_result_t collection_spool_claim_matching(
    collection_spool_t *, collection_spool_kind_t, uint32_t source_id,
    collection_spool_record_t *, void *payload, size_t payload_capacity);
/* Finds and pins the oldest pending record other than the exact kind/source
 * pair. This lets an uploader make bounded progress on the complementary set
 * without weakening the default FIFO or acknowledging an unclaimed record. */
collection_spool_result_t collection_spool_claim_excluding(
    collection_spool_t *, collection_spool_kind_t, uint32_t source_id,
    collection_spool_record_t *, void *payload, size_t payload_capacity);
/* A stale token, a non-head token, or any changed field never reclaims data. */
collection_spool_result_t collection_spool_ack(
    collection_spool_t *, const collection_spool_token_t *);
/* ACK only the exact record installed by either filtered claim API. This is
 * the sole out-of-order ACK path; stale, unpinned, or changed tokens are
 * rejected without a flash mutation. */
collection_spool_result_t collection_spool_ack_claimed(
    collection_spool_t *, const collection_spool_token_t *);
/* Pin the current head while the sole uploader performs I/O outside the caller's
 * mutex. Capacity eviction skips its entire sector. ACK releases a matching pin;
 * an unsuccessful delivery must explicitly unpin before bounded retry/backoff. */
collection_spool_result_t collection_spool_pin(
    collection_spool_t *, const collection_spool_token_t *);
void collection_spool_unpin(collection_spool_t *);
void collection_spool_get_stats(
    const collection_spool_t *, collection_spool_stats_t *);
collection_spool_result_t collection_spool_decode_loss(
    const void *payload, size_t payload_bytes, collection_spool_loss_t *);
const char *collection_spool_result_name(collection_spool_result_t);

#endif
