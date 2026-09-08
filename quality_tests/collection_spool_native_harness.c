#include "collection_spool.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#define FLASH_MAX (1024U * 1024U)
#define SMALL (48U * 1024U)
typedef struct {
    unsigned char data[FLASH_MAX];
    size_t capacity;
    unsigned mutations;
    unsigned fail_mutation;
    size_t fail_prefix;
    bool fail_read;
    uint64_t written;
    uint64_t erased;
} flash_t;
static flash_t flash;
static unsigned char checkpoint[FLASH_MAX];
static collection_spool_t spool, recovered;
static unsigned char payload[4000], output[4000];

static bool rd(void *context, size_t offset, void *out, size_t length)
{
    flash_t *f = context;
    assert(offset + length <= f->capacity);
    if (f->fail_read) return false;
    memcpy(out, f->data + offset, length);
    return true;
}

static bool wr(void *context, size_t offset, const void *data, size_t length)
{
    flash_t *f = context;
    const unsigned char *p = data;
    assert(offset + length <= f->capacity && offset % 4U == 0U && length % 4U == 0U);
    bool fail = ++f->mutations == f->fail_mutation;
    size_t actual = fail && f->fail_prefix < length ? f->fail_prefix : length;
    for (size_t i = 0U; i < actual; ++i) {
        assert((f->data[offset + i] & p[i]) == p[i]);
        f->data[offset + i] &= p[i];
    }
    f->written += actual;
    return !fail;
}

static bool er(void *context, size_t offset, size_t length)
{
    flash_t *f = context;
    assert(offset + length <= f->capacity && offset % 4096U == 0U && length == 4096U);
    bool fail = ++f->mutations == f->fail_mutation;
    size_t actual = fail && f->fail_prefix < length ? f->fail_prefix : length;
    memset(f->data + offset, 0xff, actual);
    f->erased += actual;
    return !fail;
}

static collection_spool_config_t cfg(size_t capacity, uint32_t protected_count)
{
    collection_spool_config_t c = {
        .context = &flash, .read = rd, .write = wr, .erase = er,
        .capacity_bytes = capacity, .erase_bytes = 4096U,
        .protected_sectors = protected_count, .evict_oldest = true,
    };
    return c;
}

static void reset(size_t capacity, uint32_t protected_count)
{
    memset(&flash, 0, sizeof(flash));
    memset(flash.data, 0xff, sizeof(flash.data));
    flash.capacity = capacity;
    memset(payload, 0x5a, sizeof(payload));
    collection_spool_config_t c = cfg(capacity, protected_count);
    assert(collection_spool_init(&spool, &c) == COLLECTION_SPOOL_OK);
    assert(flash.mutations == 0U);
}

static collection_spool_record_t append(uint64_t seq, size_t bytes, collection_spool_kind_t kind)
{
    collection_spool_record_t r;
    payload[0] = (unsigned char)seq;
    collection_spool_result_t result = collection_spool_append(&spool, kind, 7U, seq, payload, bytes, &r);
    if (result != COLLECTION_SPOOL_OK)
        fprintf(stderr, "append seq=%" PRIu64 " result=%s\n", seq, collection_spool_result_name(result));
    assert(result == COLLECTION_SPOOL_OK);
    return r;
}

static collection_spool_record_t peek(collection_spool_t *s)
{
    collection_spool_record_t r;
    assert(collection_spool_peek(s, &r, output, sizeof(output)) == COLLECTION_SPOOL_OK);
    return r;
}

static void restore_fault(unsigned mutation, size_t prefix)
{
    memcpy(flash.data, checkpoint, flash.capacity);
    flash.fail_mutation = 0U;
    flash.fail_read = false;
    flash.mutations = 0U;
    collection_spool_config_t c = cfg(flash.capacity, 2U);
    assert(collection_spool_init(&spool, &c) == COLLECTION_SPOOL_OK);
    flash.fail_mutation = mutation;
    flash.fail_prefix = prefix;
}

static void reboot(void)
{
    flash.fail_mutation = 0U;
    flash.fail_read = false;
    collection_spool_config_t c = cfg(flash.capacity, spool.config.protected_sectors);
    collection_spool_result_t result = collection_spool_init(&recovered, &c);
    if (result != COLLECTION_SPOOL_OK)
        fprintf(stderr, "recovery result=%s\n", collection_spool_result_name(result));
    assert(result == COLLECTION_SPOOL_OK);
    spool = recovered;
}

static unsigned drain(uint64_t *data_count, uint64_t *loss_count)
{
    collection_spool_record_t r;
    unsigned count = 0U;
    while (collection_spool_peek(&spool, &r, output, sizeof(output)) == COLLECTION_SPOOL_OK) {
        if (r.kind == COLLECTION_SPOOL_DATA) {
            if (data_count) ++*data_count;
            assert(output[0] == (unsigned char)r.source_seq);
        }
        if (r.kind == COLLECTION_SPOOL_LOSS) {
            collection_spool_loss_t loss;
            assert(collection_spool_decode_loss(output, r.token.payload_bytes, &loss) == COLLECTION_SPOOL_OK);
            if (loss_count) ++*loss_count;
        }
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
        ++count;
    }
    return count;
}

static void case_roundtrip(void)
{
    reset(SMALL, 2U);
    for (uint64_t i = 1U; i <= 100U; ++i) append(i, 253U, COLLECTION_SPOOL_DATA);
    collection_spool_stats_t stats;
    collection_spool_get_stats(&spool, &stats);
    assert(stats.pending_records == 100U && stats.pending_payload_bytes == 25300U);
    assert(stats.erased_bytes_this_boot == 0U);
    assert(stats.write_bytes_this_boot < 32000U);
    uint64_t written = stats.write_bytes_this_boot;
    reboot();
    for (uint64_t i = 1U; i <= 100U; ++i) {
        collection_spool_record_t r = peek(&spool);
        assert(r.source_seq == i && r.token.payload_bytes == 253U && output[0] == (unsigned char)i);
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    }
    reboot();
    collection_spool_record_t r;
    assert(collection_spool_peek(&spool, &r, output, sizeof(output)) == COLLECTION_SPOOL_EMPTY);
    printf("{\"case\":\"roundtrip\",\"records\":100,\"payload_bytes\":25300,\"write_bytes\":%" PRIu64 ",\"erase_bytes\":0}\n", written);
}

static void case_exact_ack(void)
{
    reset(SMALL, 2U);
    collection_spool_record_t first = append(1U, 100U, COLLECTION_SPOOL_DATA);
    collection_spool_record_t second = append(2U, 100U, COLLECTION_SPOOL_DATA);
    unsigned before = flash.mutations;
    assert(collection_spool_ack(&spool, &second.token) == COLLECTION_SPOOL_ACK_MISMATCH);
    for (unsigned field = 0U; field < 6U; ++field) {
        collection_spool_token_t bad = first.token;
        switch (field) {
        case 0U: ++bad.sector_generation; break;
        case 1U: ++bad.ticket; break;
        case 2U: ++bad.sector; break;
        case 3U: ++bad.offset; break;
        case 4U: ++bad.payload_bytes; break;
        default: ++bad.payload_crc32; break;
        }
        assert(collection_spool_ack(&spool, &bad) == COLLECTION_SPOOL_ACK_MISMATCH);
    }
    assert(flash.mutations == before);
    collection_spool_record_t small;
    assert(collection_spool_peek(&spool, &small, output, 1U) == COLLECTION_SPOOL_BUFFER_TOO_SMALL);
    assert(small.token.payload_bytes == 100U);
    assert(collection_spool_ack(&spool, &first.token) == COLLECTION_SPOOL_OK);
    assert(collection_spool_ack(&spool, &first.token) == COLLECTION_SPOOL_ACK_MISMATCH);
    reboot();
    assert(peek(&spool).source_seq == 2U);
    printf("{\"case\":\"exact_ack\",\"rejected_tokens\":8}\n");
}

static void case_append_cuts(void)
{
    reset(SMALL, 2U);
    append(1U, 129U, COLLECTION_SPOOL_DATA);
    memcpy(checkpoint, flash.data, SMALL);
    unsigned cases = 0U;
    const size_t lengths[] = {40U, 128U, 4U, 4U};
    for (unsigned mutation = 1U; mutation <= 4U; ++mutation) {
        for (size_t prefix = 0U; prefix <= lengths[mutation - 1U]; ++prefix) {
            restore_fault(mutation, prefix);
            payload[0] = 2U;
            assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 2U,
                payload, 129U, NULL) == COLLECTION_SPOOL_IO_ERROR);
            assert(!spool.initialized);
            reboot();
            append(3U, 129U, COLLECTION_SPOOL_DATA);
            collection_spool_record_t r = peek(&spool);
            assert(r.source_seq == 1U);
            assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
            r = peek(&spool);
            if (mutation == 4U && prefix == 4U) {
                assert(r.source_seq == 2U);
                assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
                r = peek(&spool);
            }
            assert(r.source_seq == 3U);
            assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
            assert(collection_spool_peek(&spool, &r, output, sizeof(output)) == COLLECTION_SPOOL_EMPTY);
            ++cases;
        }
    }
    printf("{\"case\":\"append_power_cuts\",\"cuts\":%u}\n", cases);
}

static void case_header_and_ack_cuts(void)
{
    unsigned headers = 0U;
    for (unsigned mutation = 1U; mutation <= 2U; ++mutation) {
        size_t length = mutation == 1U ? 40U : 4U;
        for (size_t prefix = 0U; prefix <= length; ++prefix) {
            reset(SMALL, 2U);
            flash.fail_mutation = mutation;
            flash.fail_prefix = prefix;
            assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 1U,
                payload, 128U, NULL) == COLLECTION_SPOOL_IO_ERROR);
            reboot();
            append(2U, 128U, COLLECTION_SPOOL_DATA);
            assert(peek(&spool).source_seq == 2U);
            ++headers;
        }
    }
    for (size_t prefix = 0U; prefix <= 4U; ++prefix) {
        reset(SMALL, 2U);
        collection_spool_record_t r = append(1U, 128U, COLLECTION_SPOOL_DATA);
        flash.fail_mutation = flash.mutations + 1U;
        flash.fail_prefix = prefix;
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_IO_ERROR);
        reboot();
        collection_spool_result_t result = collection_spool_peek(&spool, &r, output, sizeof(output));
        assert(result == (prefix == 4U ? COLLECTION_SPOOL_EMPTY : COLLECTION_SPOOL_OK));
    }
    printf("{\"case\":\"header_ack_power_cuts\",\"header_cuts\":%u,\"ack_cuts\":5}\n", headers);
}

static void full_fixture(void)
{
    reset(SMALL, 2U);
    append(99U, 64U, COLLECTION_SPOOL_METADATA);
    for (uint64_t i = 1U; i <= 10U; ++i) append(i, 3000U, COLLECTION_SPOOL_DATA);
}

static void case_eviction(void)
{
    full_fixture();
    append(11U, 3000U, COLLECTION_SPOOL_DATA);
    reboot();
    collection_spool_stats_t stats;
    collection_spool_get_stats(&spool, &stats);
    assert(stats.evicted_records == 1U && stats.evicted_payload_bytes == 3000U);
    assert(stats.pending_records == 12U && stats.acked_records_this_boot == 0U);
    collection_spool_record_t r = peek(&spool);
    assert(r.kind == COLLECTION_SPOOL_METADATA);
    assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    for (uint64_t i = 2U; i <= 10U; ++i) {
        r = peek(&spool);
        assert(r.kind == COLLECTION_SPOOL_DATA && r.source_seq == i);
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    }
    r = peek(&spool);
    assert(r.kind == COLLECTION_SPOOL_LOSS);
    collection_spool_loss_t loss;
    assert(collection_spool_decode_loss(output, r.token.payload_bytes, &loss) == COLLECTION_SPOOL_OK);
    assert(loss.source_count == 1U && loss.sources[0].source_id == 7U);
    assert(loss.sources[0].records == 1U && loss.sources[0].payload_bytes == 3000U);
    assert(loss.sources[0].first_source_seq == 1U && loss.sources[0].last_source_seq == 1U);
    assert(loss.sources[0].first_ticket == 2U && loss.sources[0].last_ticket == 2U);
    assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    r = peek(&spool);
    assert(r.source_seq == 11U);
    assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    for (unsigned i = 0U; i < 20U; ++i) {
        r = append(200U + i, 3000U, COLLECTION_SPOOL_METADATA);
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
        reboot();
    }
    collection_spool_get_stats(&spool, &stats);
    assert(stats.evicted_records == 1U && stats.evicted_payload_bytes == 3000U);
    printf("{\"case\":\"durable_eviction\",\"evicted_records\":1,\"evicted_bytes\":3000,\"checkpoint_reboots\":20}\n");
}

static void case_eviction_cuts(void)
{
    full_fixture();
    memcpy(checkpoint, flash.data, SMALL);
    /* Existing protected segment: loss header/payload/commit, target erase,
     * replacement segment header/commit, new record header/payload/commit. */
    const size_t lengths[] = {40U, 88U, 4U, 4096U, 40U, 4U, 40U, 3000U, 4U};
    unsigned cuts = 0U;
    for (unsigned mutation = 1U; mutation <= 9U; ++mutation) {
        size_t length = lengths[mutation - 1U];
        size_t prefixes[] = {0U, 1U, length / 2U, length - 1U, length};
        for (unsigned k = 0U; k < 5U; ++k) {
            restore_fault(mutation, prefixes[k]);
            payload[0] = 11U;
            collection_spool_result_t result = collection_spool_append(&spool,
                COLLECTION_SPOOL_DATA, 7U, 11U, payload, 3000U, NULL);
            assert(result == COLLECTION_SPOOL_IO_ERROR);
            reboot();
            bool lost = mutation > 3U || (mutation == 3U && prefixes[k] == length);
            bool appended = mutation == 9U && prefixes[k] == length;
            collection_spool_stats_t stats;
            collection_spool_get_stats(&spool, &stats);
            assert(stats.evicted_records == (lost ? 1U : 0U));
            uint64_t count = 0U, losses = 0U;
            drain(&count, &losses);
            assert(count == 10U - (lost ? 1U : 0U) + (appended ? 1U : 0U));
            assert(losses == (lost ? 1U : 0U));
            /* A retained intent allows safe retry after an interrupted erase. */
            append(12U, 3000U, COLLECTION_SPOOL_DATA);
            assert(peek(&spool).source_seq == 12U);
            ++cuts;
        }
    }
    printf("{\"case\":\"eviction_power_cuts\",\"cuts\":%u}\n", cuts);
}

static void case_protection_and_full(void)
{
    reset(SMALL, 2U);
    collection_spool_record_t m1 = append(91U, 4000U, COLLECTION_SPOOL_METADATA);
    collection_spool_record_t m2 = append(92U, 4000U, COLLECTION_SPOOL_METADATA);
    for (uint64_t i = 1U; i <= 10U; ++i) append(i, 3000U, COLLECTION_SPOOL_DATA);
    assert(collection_spool_ack(&spool, &m1.token) == COLLECTION_SPOOL_OK);
    assert(collection_spool_ack(&spool, &m2.token) == COLLECTION_SPOOL_OK);
    memcpy(checkpoint, flash.data, SMALL);
    unsigned before = flash.mutations;
    assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 11U,
        payload, 3000U, NULL) == COLLECTION_SPOOL_PROTECTED_FULL);
    assert(flash.mutations == before && memcmp(checkpoint, flash.data, SMALL) == 0);
    collection_spool_stats_t stats;
    collection_spool_get_stats(&spool, &stats);
    assert(stats.protected_retained_bytes == 8096U && stats.evicted_records == 0U);
    uint64_t count = 0U;
    drain(&count, NULL);
    assert(count == 10U);
    append(93U, 3000U, COLLECTION_SPOOL_METADATA);
    reset(SMALL, 2U);
    spool.config.evict_oldest = false;
    for (uint64_t i = 1U; i <= 10U; ++i) append(i, 3000U, COLLECTION_SPOOL_DATA);
    assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 11U,
        payload, 3000U, NULL) == COLLECTION_SPOOL_FULL);
    assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 11U,
        payload, 4001U, NULL) == COLLECTION_SPOOL_TOO_LARGE);
    printf("{\"case\":\"protected_full\",\"retained_metadata_bytes\":8096,\"silent_evictions\":0}\n");
}

static void case_pinning(void)
{
    reset(4U * 4096U, 2U);
    collection_spool_record_t first = append(1U, 3000U, COLLECTION_SPOOL_DATA);
    collection_spool_record_t second = append(2U, 3000U, COLLECTION_SPOOL_DATA);
    assert(collection_spool_pin(&spool, &second.token) == COLLECTION_SPOOL_ACK_MISMATCH);
    assert(collection_spool_pin(&spool, &first.token) == COLLECTION_SPOOL_OK);
    assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA, 7U, 3U,
        payload, 3000U, NULL) == COLLECTION_SPOOL_FULL);
    assert(peek(&spool).source_seq == 1U);
    collection_spool_unpin(&spool);
    append(3U, 3000U, COLLECTION_SPOOL_DATA);
    assert(collection_spool_ack(&spool, &first.token) == COLLECTION_SPOOL_ACK_MISMATCH);
    assert(peek(&spool).source_seq == 2U);
    assert(collection_spool_pin(&spool, &second.token) == COLLECTION_SPOOL_OK);
    assert(collection_spool_ack(&spool, &second.token) == COLLECTION_SPOOL_OK && !spool.has_pin);
    printf("{\"case\":\"inflight_pin\",\"protected_head\":true}\n");
}

static void case_corrupt_and_foreign(void)
{
    reset(SMALL, 2U);
    collection_spool_config_t malformed = cfg(SMALL, UINT32_MAX);
    assert(collection_spool_init(&recovered, &malformed) == COLLECTION_SPOOL_BAD_ARGUMENT);
    assert(flash.mutations == 0U);
    flash.data[10U] = 0U;
    memcpy(checkpoint, flash.data, SMALL);
    collection_spool_config_t c = cfg(SMALL, 2U);
    assert(collection_spool_init(&spool, &c) == COLLECTION_SPOOL_FOREIGN_DATA);
    assert(flash.mutations == 0U && memcmp(checkpoint, flash.data, SMALL) == 0);
    reset(SMALL, 2U);
    collection_spool_record_t r = append(1U, 100U, COLLECTION_SPOOL_DATA);
    flash.data[r.token.sector * 4096U + r.token.offset + COLLECTION_SPOOL_RECORD_HEADER_BYTES + 2U] ^= 1U;
    memcpy(checkpoint, flash.data, SMALL);
    unsigned before = flash.mutations;
    assert(collection_spool_init(&spool, &c) == COLLECTION_SPOOL_CORRUPT);
    assert(flash.mutations == before && memcmp(checkpoint, flash.data, SMALL) == 0);
    reset(SMALL, 2U);
    flash.fail_read = true;
    assert(collection_spool_init(&spool, &c) == COLLECTION_SPOOL_IO_ERROR);
    assert(!spool.initialized && flash.mutations == 0U);
    printf("{\"case\":\"foreign_and_corrupt\",\"destructive_recovery\":false}\n");
}

static void case_large_geometry(void)
{
    reset(0xd2000U, 8U);
    for (uint64_t i = 1U; i <= 203U; ++i) append(i, 4000U, COLLECTION_SPOOL_DATA);
    reboot();
    collection_spool_stats_t stats;
    collection_spool_get_stats(&spool, &stats);
    assert(stats.capacity_bytes == 860160U && stats.ordinary_capacity_bytes == 827392U);
    assert(stats.evicted_records == 1U && stats.pending_records == 203U);
    printf("{\"case\":\"large_geometry\",\"capacity_bytes\":860160,\"ordinary_bytes\":827392,\"spool_ram_bytes\":%zu}\n", sizeof(collection_spool_t));
}

static void case_multisource_loss(void)
{
    reset(SMALL, 2U);
    for (uint64_t i = 1U; i <= 141U; ++i) {
        payload[0] = (unsigned char)i;
        assert(collection_spool_append(&spool, COLLECTION_SPOOL_DATA,
            (uint32_t)((i - 1U) % 3U) + 1U, i, payload, 240U, NULL) == COLLECTION_SPOOL_OK);
    }
    reboot();
    bool saw_loss = false;
    collection_spool_record_t r;
    while (collection_spool_peek(&spool, &r, output, sizeof(output)) == COLLECTION_SPOOL_OK) {
        if (r.kind == COLLECTION_SPOOL_LOSS) {
            collection_spool_loss_t loss;
            assert(collection_spool_decode_loss(output, r.token.payload_bytes, &loss) == COLLECTION_SPOOL_OK);
            assert(loss.source_count == 3U && loss.evicted_records_total == 14U && loss.evicted_bytes_total == 3360U);
            for (uint32_t source = 1U; source <= 3U; ++source) {
                const collection_spool_loss_source_t *part = &loss.sources[source - 1U];
                assert(part->source_id == source);
                assert(part->records == (source < 3U ? 5U : 4U));
                assert(part->payload_bytes == part->records * 240U);
                assert(part->first_source_seq == source && part->first_ticket == source);
                assert(part->last_source_seq == (source < 3U ? source + 12U : 12U));
                assert(part->last_ticket == part->last_source_seq);
            }
            saw_loss = true;
        }
        assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    }
    assert(saw_loss);
    printf("{\"case\":\"multisource_loss\",\"sources\":3,\"evicted_records\":14,\"evicted_bytes\":3360}\n");
}

static void case_acked_recycle_cuts(void)
{
    const size_t prefixes[] = {0U, 1U, 2048U, 4095U, 4096U};
    unsigned cases = 0U;
    for (unsigned metadata = 0U; metadata < 2U; ++metadata) {
        for (unsigned k = 0U; k < 5U; ++k) {
            reset(SMALL, 2U);
            unsigned records = metadata ? 2U : 10U;
            collection_spool_kind_t kind = metadata ? COLLECTION_SPOOL_METADATA : COLLECTION_SPOOL_DATA;
            for (unsigned i = 1U; i <= records; ++i) append(i, 4000U, kind);
            assert(drain(NULL, NULL) == records);
            flash.fail_mutation = flash.mutations + 1U;
            flash.fail_prefix = prefixes[k];
            assert(collection_spool_append(&spool, kind, 7U, 11U, payload, 4000U, NULL) == COLLECTION_SPOOL_IO_ERROR);
            reboot();
            collection_spool_stats_t stats;
            collection_spool_get_stats(&spool, &stats);
            assert(stats.pending_records == 0U && stats.evicted_records == 0U);
            assert(stats.quarantined_sectors == (k > 0U && k < 4U ? 1U : 0U));
            /* Quarantine is never erased to regain space. Unaffected ordinary
             * capacity remains usable even when one metadata sector is lost. */
            unsigned char damaged[4096];
            uint32_t target = metadata ? 0U : 2U;
            memcpy(damaged, flash.data + target * 4096U, sizeof(damaged));
            append(12U, 128U, COLLECTION_SPOOL_DATA);
            assert(peek(&spool).source_seq == 12U);
            if (stats.quarantined_sectors)
                assert(memcmp(damaged, flash.data + target * 4096U, sizeof(damaged)) == 0);
            ++cases;
        }
    }
    printf("{\"case\":\"acked_recycle_power_cuts\",\"cuts\":%u,\"unknown_sector_policy\":\"preserve_and_quarantine\"}\n", cases);
}

/* Actual host threads model the documented caller-owned mutex while the
 * uploader's network operation is blocked. The production C is unchanged. */
#ifdef _WIN32
static CRITICAL_SECTION guard;
static HANDLE pinned_event, produced_event;
static void lock_spool(void) { EnterCriticalSection(&guard); }
static void unlock_spool(void) { LeaveCriticalSection(&guard); }
static void signal_pinned(void) { assert(SetEvent(pinned_event)); }
static void wait_pinned(void) { assert(WaitForSingleObject(pinned_event, 5000U) == WAIT_OBJECT_0); }
static void signal_produced(void) { assert(SetEvent(produced_event)); }
static void wait_produced(void) { assert(WaitForSingleObject(produced_event, 5000U) == WAIT_OBJECT_0); }
#define THREAD_RESULT DWORD WINAPI
#define THREAD_RETURN return 0U
#else
static pthread_mutex_t guard = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t event_guard = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t event_changed = PTHREAD_COND_INITIALIZER;
static bool pinned_flag, produced_flag;
static void lock_spool(void) { assert(pthread_mutex_lock(&guard) == 0); }
static void unlock_spool(void) { assert(pthread_mutex_unlock(&guard) == 0); }
static void set_flag(bool *flag) {
    assert(pthread_mutex_lock(&event_guard) == 0); *flag = true;
    assert(pthread_cond_broadcast(&event_changed) == 0);
    assert(pthread_mutex_unlock(&event_guard) == 0);
}
static void wait_flag(bool *flag) {
    assert(pthread_mutex_lock(&event_guard) == 0);
    while (!*flag) assert(pthread_cond_wait(&event_changed, &event_guard) == 0);
    assert(pthread_mutex_unlock(&event_guard) == 0);
}
static void signal_pinned(void) { set_flag(&pinned_flag); }
static void wait_pinned(void) { wait_flag(&pinned_flag); }
static void signal_produced(void) { set_flag(&produced_flag); }
static void wait_produced(void) { wait_flag(&produced_flag); }
#define THREAD_RESULT void *
#define THREAD_RETURN return NULL
#endif

static THREAD_RESULT producer_thread(void *unused)
{
    (void)unused;
    wait_pinned();
    for (uint64_t i = 2U; i <= 21U; ++i) {
        lock_spool();
        append(i, 3000U, COLLECTION_SPOOL_DATA);
        unlock_spool();
    }
    signal_produced();
    THREAD_RETURN;
}

static THREAD_RESULT uploader_thread(void *unused)
{
    (void)unused;
    collection_spool_record_t r;
    unsigned char body[4000];
    lock_spool();
    assert(collection_spool_peek(&spool, &r, body, sizeof(body)) == COLLECTION_SPOOL_OK);
    assert(r.source_seq == 1U && body[0] == 1U);
    assert(collection_spool_pin(&spool, &r.token) == COLLECTION_SPOOL_OK);
    unlock_spool();
    signal_pinned();
    wait_produced(); /* No spool mutex held during this simulated network wait. */
    lock_spool();
    assert(collection_spool_ack(&spool, &r.token) == COLLECTION_SPOOL_OK);
    unlock_spool();
    THREAD_RETURN;
}

static void case_concurrent_uploader_and_producer(void)
{
    reset(SMALL, 2U);
    append(1U, 3000U, COLLECTION_SPOOL_DATA);
#ifdef _WIN32
    InitializeCriticalSection(&guard);
    pinned_event = CreateEvent(NULL, TRUE, FALSE, NULL);
    produced_event = CreateEvent(NULL, TRUE, FALSE, NULL);
    assert(pinned_event && produced_event);
    HANDLE threads[2] = {
        CreateThread(NULL, 0U, producer_thread, NULL, 0U, NULL),
        CreateThread(NULL, 0U, uploader_thread, NULL, 0U, NULL),
    };
    assert(threads[0] && threads[1]);
    assert(WaitForMultipleObjects(2U, threads, TRUE, 10000U) == WAIT_OBJECT_0);
    CloseHandle(threads[0]); CloseHandle(threads[1]);
    CloseHandle(pinned_event); CloseHandle(produced_event);
    DeleteCriticalSection(&guard);
#else
    pthread_t producer, uploader;
    assert(pthread_create(&producer, NULL, producer_thread, NULL) == 0);
    assert(pthread_create(&uploader, NULL, uploader_thread, NULL) == 0);
    assert(pthread_join(producer, NULL) == 0 && pthread_join(uploader, NULL) == 0);
#endif
    collection_spool_stats_t stats;
    collection_spool_get_stats(&spool, &stats);
    assert(stats.evicted_records == 11U && stats.acked_records_this_boot == 1U);
    reboot();
    uint64_t count = 0U, losses = 0U;
    drain(&count, &losses);
    assert(count == 9U && losses == 11U);
    printf("{\"case\":\"concurrent_uploader_producer\",\"producer_records_during_io\":20,\"pinned_record_ack\":true,\"evicted_other_records\":11}\n");
}

int main(void)
{
    case_roundtrip();
    case_exact_ack();
    case_append_cuts();
    case_header_and_ack_cuts();
    case_eviction();
    case_eviction_cuts();
    case_protection_and_full();
    case_pinning();
    case_corrupt_and_foreign();
    case_large_geometry();
    case_multisource_loss();
    case_acked_recycle_cuts();
    case_concurrent_uploader_and_producer();
    return 0;
}
