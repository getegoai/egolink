#include "collection_spool.h"

#include <limits.h>
#include <string.h>

/* Explicit little-endian disk format, independent of ABI/struct padding.
 * Headers and payload are written/read back before the final commit word.
 * ACK is an independent 1->0 write and is outside the header CRC.
 * The underlying region must be unencrypted NOR supporting 4-byte writes. */
#define SECTOR_MAGIC UINT32_C(0x31534345)
#define RECORD_MAGIC UINT32_C(0x31524345)
#define LOSS_MAGIC UINT32_C(0x3153534c)
#define COMMIT UINT32_C(0x51c04d17)
#define BLANK UINT32_MAX
#define SECTOR_FREE 0U
#define SECTOR_VALID 1U
#define SECTOR_QUARANTINED 2U
#define SECTOR_FOREIGN 3U
#define SECTOR_CORRUPT 4U
#define SH COLLECTION_SPOOL_SECTOR_HEADER_BYTES
#define RH COLLECTION_SPOOL_RECORD_HEADER_BYTES
#define LOSS_HEAD 40U
#define LOSS_ENTRY 48U
#define LOSS_MAX (LOSS_HEAD + COLLECTION_SPOOL_MAX_SOURCES * LOSS_ENTRY)

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8U |
           (uint32_t)p[2] << 16U | (uint32_t)p[3] << 24U;
}

static uint64_t get64(const uint8_t *p)
{
    return (uint64_t)get32(p) | (uint64_t)get32(p + 4) << 32U;
}

static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0U; i < 4U; ++i) p[i] = (uint8_t)(v >> (8U * i));
}

static void put64(uint8_t *p, uint64_t v)
{
    put32(p, (uint32_t)v);
    put32(p + 4, (uint32_t)(v >> 32U));
}

static uint32_t crc_update(uint32_t crc, const void *data, size_t length)
{
    const uint8_t *p = data;
    for (size_t i = 0U; i < length; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0U; bit < 8U; ++bit)
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) & (0U - (crc & 1U)));
    }
    return crc;
}

static uint32_t crc32(const void *data, size_t length)
{
    return ~crc_update(UINT32_MAX, data, length);
}

static size_t aligned(size_t n) { return (n + 3U) & ~(size_t)3U; }
static size_t base(const collection_spool_t *s, uint32_t n)
{ return (size_t)n * s->config.erase_bytes; }

static bool read_at(collection_spool_t *s, size_t at, void *out, size_t bytes)
{
    if (s->config.read(s->config.context, at, out, bytes)) return true;
    ++s->stats.io_errors_this_boot;
    return false;
}

static bool write_at(collection_spool_t *s, size_t at, const void *in, size_t bytes)
{
    uint8_t check[128];
    const uint8_t *p = in;
    /* Requested bytes are an upper bound if the callback fails partway. */
    s->stats.write_bytes_this_boot += bytes;
    if (!s->config.write(s->config.context, at, in, bytes)) goto failed;
    for (size_t done = 0U; done < bytes;) {
        size_t n = bytes - done;
        if (n > sizeof(check)) n = sizeof(check);
        if (!s->config.read(s->config.context, at + done, check, n) ||
            memcmp(check, p + done, n) != 0) goto failed;
        done += n;
    }
    return true;
failed:
    ++s->stats.io_errors_this_boot;
    s->initialized = false; /* Mutation outcome uncertain: recover before reuse. */
    return false;
}

static int erased_range(collection_spool_t *s, size_t at, size_t length)
{
    uint8_t data[128];
    for (size_t done = 0U; done < length;) {
        size_t n = length - done;
        if (n > sizeof(data)) n = sizeof(data);
        if (!read_at(s, at + done, data, n)) return -1;
        for (size_t i = 0U; i < n; ++i) if (data[i] != 0xffU) return 0;
        done += n;
    }
    return 1;
}

static bool payload_crc(collection_spool_t *s, size_t at, size_t length,
                        uint32_t expected)
{
    uint8_t data[128];
    uint32_t crc = UINT32_MAX;
    for (size_t done = 0U; done < length;) {
        size_t n = length - done;
        if (n > sizeof(data)) n = sizeof(data);
        if (!read_at(s, at + done, data, n)) return false;
        crc = crc_update(crc, data, n);
        done += n;
    }
    return ~crc == expected;
}

static void decode_record(const uint8_t *h, uint32_t sector, uint32_t at,
                          uint64_t generation, collection_spool_record_t *r)
{
    memset(r, 0, sizeof(*r));
    r->token.sector_generation = generation;
    r->token.ticket = get64(h + 8);
    r->token.sector = sector;
    r->token.offset = at;
    r->token.payload_bytes = get32(h + 4);
    r->token.payload_crc32 = get32(h + 32);
    r->source_id = get32(h + 16);
    r->kind = (collection_spool_kind_t)get32(h + 20);
    r->source_seq = get64(h + 24);
}

static void update_totals(collection_spool_t *s, uint64_t count, uint64_t bytes)
{
    if (count > s->stats.evicted_records) s->stats.evicted_records = count;
    if (bytes > s->stats.evicted_payload_bytes) s->stats.evicted_payload_bytes = bytes;
}

static collection_spool_result_t scan_records(collection_spool_t *s, uint32_t n)
{
    collection_spool_sector_t *sector = &s->sectors[n];
    uint32_t at = SH;
    uint8_t h[RH];
    while ((size_t)at + RH <= s->config.erase_bytes) {
        if (!read_at(s, base(s, n) + at, h, sizeof(h))) return COLLECTION_SPOOL_IO_ERROR;
        if (get32(h) == BLANK) {
            int erased = erased_range(s, base(s, n) + at, s->config.erase_bytes - at);
            if (erased < 0) return COLLECTION_SPOOL_IO_ERROR;
            if (erased) break;
        }
        if (get32(h + 40) != COMMIT) {
            /* An incomplete append seals only the unused tail, never the
             * previously committed records in this sector. */
            sector->sealed = true;
            ++s->stats.torn_tails;
            break;
        }
        uint32_t bytes = get32(h + 4);
        uint32_t kind = get32(h + 20);
        if (get32(h) != RECORD_MAGIC || crc32(h, 36U) != get32(h + 36) ||
            bytes == 0U || bytes > s->config.erase_bytes - at - RH ||
            kind > COLLECTION_SPOOL_LOSS ||
            (n < s->config.protected_sectors) != (kind != COLLECTION_SPOOL_DATA))
            return COLLECTION_SPOOL_CORRUPT;
        if (!payload_crc(s, base(s, n) + at + RH, bytes, get32(h + 32)))
            return s->stats.io_errors_this_boot ? COLLECTION_SPOOL_IO_ERROR : COLLECTION_SPOOL_CORRUPT;
        uint64_t ticket = get64(h + 8);
        if (!ticket || ticket == UINT64_MAX) return COLLECTION_SPOOL_CORRUPT;
        if (ticket > s->ticket) s->ticket = ticket;
        ++sector->records;
        if (get32(h + 44) != 0U) {
            ++sector->pending;
            sector->pending_bytes += bytes;
        }
        if (kind == COLLECTION_SPOOL_LOSS) {
            uint8_t loss[LOSS_MAX];
            collection_spool_loss_t decoded;
            if (bytes > sizeof(loss) ||
                !read_at(s, base(s, n) + at + RH, loss, bytes))
                return bytes > sizeof(loss) ? COLLECTION_SPOOL_CORRUPT : COLLECTION_SPOOL_IO_ERROR;
            if (collection_spool_decode_loss(loss, bytes, &decoded) != COLLECTION_SPOOL_OK)
                return COLLECTION_SPOOL_CORRUPT;
            update_totals(s, decoded.evicted_records_total, decoded.evicted_bytes_total);
        }
        at += RH + (uint32_t)aligned(bytes);
    }
    sector->end = at;
    return COLLECTION_SPOOL_OK;
}

static bool has_retired(const collection_spool_t *s)
{
    for (uint32_t i = 0U; i < s->sector_count; ++i)
        if (s->sectors[i].retired) return true;
    return false;
}

/* Apply committed eviction intents even when erase was interrupted. Protected
 * sectors are scanned first. A target with a newer committed generation is
 * already reused; an invalid/old target remains retired and may be re-erased. */
static collection_spool_result_t apply_losses(collection_spool_t *s)
{
    uint8_t h[RH], p[LOSS_MAX];
    for (uint32_t n = 0U; n < s->config.protected_sectors; ++n) {
        collection_spool_sector_t *sector = &s->sectors[n];
        if (sector->state != SECTOR_VALID) continue;
        for (uint32_t at = SH; at < sector->end;) {
            if (!read_at(s, base(s, n) + at, h, RH)) return COLLECTION_SPOOL_IO_ERROR;
            uint32_t bytes = get32(h + 4);
            if (get32(h + 20) == COLLECTION_SPOOL_LOSS) {
                if (bytes > sizeof(p) || !read_at(s, base(s, n) + at + RH, p, bytes))
                    return COLLECTION_SPOOL_IO_ERROR;
                uint32_t target = get32(p + 8);
                uint64_t generation = get64(p + 16);
                if (target < s->config.protected_sectors || target >= s->sector_count)
                    return COLLECTION_SPOOL_CORRUPT;
                collection_spool_sector_t *old = &s->sectors[target];
                if (old->state != SECTOR_FREE &&
                    (old->state != SECTOR_VALID || old->generation <= generation)) {
                    old->retired = true;
                    old->pending = old->pending_bytes = 0U;
                    /* Keep the generation watermark after a partial erase. */
                    if (old->generation < generation) old->generation = generation;
                }
            }
            at += RH + (uint32_t)aligned(bytes);
        }
    }
    return COLLECTION_SPOOL_OK;
}

collection_spool_result_t collection_spool_init(
    collection_spool_t *s, const collection_spool_config_t *config)
{
    if (!s || !config || !config->read || !config->write || !config->erase ||
        config->erase_bytes < 1024U || config->erase_bytes > UINT32_MAX ||
        config->erase_bytes % 4U || config->capacity_bytes % config->erase_bytes ||
        config->capacity_bytes / config->erase_bytes > COLLECTION_SPOOL_MAX_SECTORS ||
        config->protected_sectors < 2U ||
        config->capacity_bytes / config->erase_bytes < 4U ||
        config->protected_sectors > config->capacity_bytes / config->erase_bytes - 2U)
        return COLLECTION_SPOOL_BAD_ARGUMENT;
    collection_spool_config_t saved = *config;
    config = &saved;
    memset(s, 0, sizeof(*s));
    s->config = saved;
    s->sector_count = (uint32_t)(config->capacity_bytes / config->erase_bytes);
    s->stats.capacity_bytes = config->capacity_bytes;
    s->stats.protected_capacity_bytes = config->protected_sectors * config->erase_bytes;
    s->stats.ordinary_capacity_bytes = config->capacity_bytes - s->stats.protected_capacity_bytes;
    s->stats.max_payload_bytes = config->erase_bytes - SH - RH;
    /* First inspect headers without erasing or trusting ordinary record tails. */
    for (uint32_t n = 0U; n < s->sector_count; ++n) {
        uint8_t h[SH];
        if (!read_at(s, base(s, n), h, SH)) return COLLECTION_SPOOL_IO_ERROR;
        collection_spool_sector_t *sector = &s->sectors[n];
        if (get32(h) == BLANK) {
            int erased = erased_range(s, base(s, n), config->erase_bytes);
            if (erased < 0) return COLLECTION_SPOOL_IO_ERROR;
            if (erased) { sector->end = SH; continue; }
        }
        if (get32(h) != SECTOR_MAGIC) {
            /* A cut in the first magic write is recognizable only when all
             * following bytes are erased. Never reclaim such quarantine. */
            uint8_t magic[4];
            put32(magic, SECTOR_MAGIC);
            unsigned prefix = 0U;
            while (prefix < 4U && h[prefix] == magic[prefix]) ++prefix;
            bool partial = prefix > 0U && prefix < 4U;
            for (unsigned k = prefix; k < SH; ++k) if (h[k] != 0xffU) partial = false;
            int rest = partial ? erased_range(s, base(s, n) + SH, config->erase_bytes - SH) : 0;
            if (rest < 0) return COLLECTION_SPOOL_IO_ERROR;
            sector->state = partial && rest ? SECTOR_QUARANTINED : SECTOR_FOREIGN;
            continue;
        }
        if (get32(h + 40) != COMMIT) {
            sector->state = SECTOR_QUARANTINED;
            continue;
        }
        if (get32(h + 4) != 1U || crc32(h, 36U) != get32(h + 36) ||
            get32(h + 16) != (n < config->protected_sectors ? 1U : 0U) ||
            !get64(h + 8) || get64(h + 8) == UINT64_MAX)
        {
            sector->state = SECTOR_CORRUPT;
            continue;
        }
        sector->generation = get64(h + 8);
        sector->state = SECTOR_VALID;
        sector->end = SH;
        if (sector->generation > s->generation) s->generation = sector->generation;
        update_totals(s, get64(h + 20), get64(h + 28));
    }
    for (uint32_t n = 0U; n < config->protected_sectors; ++n) {
        if (s->sectors[n].state == SECTOR_FOREIGN) {
            if (!s->generation) return COLLECTION_SPOOL_FOREIGN_DATA;
            s->sectors[n].state = SECTOR_QUARANTINED;
        }
        if (s->sectors[n].state == SECTOR_CORRUPT) return COLLECTION_SPOOL_CORRUPT;
        if (s->sectors[n].state == SECTOR_VALID) {
            collection_spool_result_t result = scan_records(s, n);
            if (result != COLLECTION_SPOOL_OK) return result;
        }
    }
    collection_spool_result_t result = apply_losses(s);
    if (result != COLLECTION_SPOOL_OK) return result;
    for (uint32_t n = config->protected_sectors; n < s->sector_count; ++n) {
        collection_spool_sector_t *sector = &s->sectors[n];
        if (sector->retired) continue;
        if (sector->state == SECTOR_FOREIGN) {
            if (!s->generation) return COLLECTION_SPOOL_FOREIGN_DATA;
            sector->state = SECTOR_QUARANTINED;
        }
        if (sector->state == SECTOR_CORRUPT) return COLLECTION_SPOOL_CORRUPT;
        if (sector->state == SECTOR_VALID) {
            result = scan_records(s, n);
            if (result != COLLECTION_SPOOL_OK) return result;
        }
    }
    for (uint32_t n = 0U; n < s->sector_count; ++n)
        if (s->sectors[n].state == SECTOR_QUARANTINED && !s->sectors[n].retired)
            ++s->stats.quarantined_sectors;
    s->initialized = true;
    return COLLECTION_SPOOL_OK;
}

static int latest_sector(const collection_spool_t *s, bool metadata)
{
    int found = -1;
    for (uint32_t n = 0U; n < s->sector_count; ++n) {
        if ((n < s->config.protected_sectors) != metadata) continue;
        if (s->sectors[n].state != SECTOR_VALID || s->sectors[n].retired) continue;
        if (found < 0 || s->sectors[n].generation > s->sectors[found].generation) found = (int)n;
    }
    return found;
}

static collection_spool_result_t create_sector(collection_spool_t *s, uint32_t n)
{
    collection_spool_sector_t *sector = &s->sectors[n];
    if (sector->state != SECTOR_FREE) {
        s->stats.erased_bytes_this_boot += s->config.erase_bytes;
        if (!s->config.erase(s->config.context, base(s, n), s->config.erase_bytes) ||
            erased_range(s, base(s, n), s->config.erase_bytes) != 1) {
            ++s->stats.io_errors_this_boot;
            s->initialized = false;
            return COLLECTION_SPOOL_IO_ERROR;
        }
    }
    uint8_t h[SH];
    memset(h, 0xff, sizeof(h));
    put32(h, SECTOR_MAGIC);
    put32(h + 4, 1U);
    put64(h + 8, ++s->generation);
    put32(h + 16, n < s->config.protected_sectors ? 1U : 0U);
    put64(h + 20, s->stats.evicted_records);
    put64(h + 28, s->stats.evicted_payload_bytes);
    put32(h + 36, crc32(h, 36U));
    if (!write_at(s, base(s, n), h, 40U)) return COLLECTION_SPOOL_IO_ERROR;
    put32(h + 40, COMMIT);
    if (!write_at(s, base(s, n) + 40U, h + 40U, 4U)) return COLLECTION_SPOOL_IO_ERROR;
    memset(sector, 0, sizeof(*sector));
    sector->state = SECTOR_VALID;
    sector->generation = s->generation;
    sector->end = SH;
    return COLLECTION_SPOOL_OK;
}

static collection_spool_result_t append_internal(collection_spool_t *,
    collection_spool_kind_t, uint32_t, uint64_t, const void *, size_t,
    collection_spool_record_t *);

static collection_spool_result_t retire_sector(collection_spool_t *s, uint32_t n)
{
    uint8_t h[RH], p[LOSS_MAX];
    collection_spool_loss_t loss;
    memset(&loss, 0, sizeof(loss));
    collection_spool_sector_t *sector = &s->sectors[n];
    for (uint32_t at = SH; at < sector->end;) {
        if (!read_at(s, base(s, n) + at, h, RH)) return COLLECTION_SPOOL_IO_ERROR;
        uint32_t bytes = get32(h + 4);
        if (get32(h + 44) != 0U) {
            uint32_t source = get32(h + 16), i = 0U;
            for (; i < loss.source_count; ++i) if (loss.sources[i].source_id == source) break;
            if (i == loss.source_count) {
                if (i == COLLECTION_SPOOL_MAX_SOURCES) return COLLECTION_SPOOL_FULL;
                ++loss.source_count;
                loss.sources[i].source_id = source;
                loss.sources[i].first_source_seq = get64(h + 24);
                loss.sources[i].first_ticket = get64(h + 8);
            }
            ++loss.sources[i].records;
            loss.sources[i].payload_bytes += bytes;
            loss.sources[i].last_source_seq = get64(h + 24);
            loss.sources[i].last_ticket = get64(h + 8);
        }
        at += RH + (uint32_t)aligned(bytes);
    }
    memset(p, 0, sizeof(p));
    put32(p, LOSS_MAGIC);
    put32(p + 4, loss.source_count);
    put32(p + 8, n);
    put32(p + 12, 1U);
    put64(p + 16, sector->generation);
    put64(p + 24, s->stats.evicted_records + sector->pending);
    put64(p + 32, s->stats.evicted_payload_bytes + sector->pending_bytes);
    for (uint32_t i = 0U; i < loss.source_count; ++i) {
        uint8_t *entry = p + LOSS_HEAD + i * LOSS_ENTRY;
        const collection_spool_loss_source_t *from = &loss.sources[i];
        put32(entry, from->source_id);
        put32(entry + 4, from->records);
        put64(entry + 8, from->payload_bytes);
        put64(entry + 16, from->first_source_seq);
        put64(entry + 24, from->last_source_seq);
        put64(entry + 32, from->first_ticket);
        put64(entry + 40, from->last_ticket);
    }
    collection_spool_result_t result = append_internal(s, COLLECTION_SPOOL_LOSS,
        0U, s->stats.evicted_records + sector->pending, p,
        LOSS_HEAD + loss.source_count * LOSS_ENTRY, NULL);
    if (result != COLLECTION_SPOOL_OK) return result;
    update_totals(s, get64(p + 24), get64(p + 32));
    sector->retired = true;
    sector->pending = sector->pending_bytes = 0U;
    return COLLECTION_SPOOL_OK;
}

static collection_spool_result_t reserve_sector(collection_spool_t *s,
    bool metadata, size_t need, uint32_t *selected)
{
    int latest = latest_sector(s, metadata);
    if (latest >= 0 && !s->sectors[latest].sealed &&
        (size_t)s->sectors[latest].end + need <= s->config.erase_bytes) {
        *selected = (uint32_t)latest;
        return COLLECTION_SPOOL_OK;
    }
    uint32_t begin = metadata ? 0U : s->config.protected_sectors;
    uint32_t end = metadata ? s->config.protected_sectors : s->sector_count;
    int candidate = -1;
    for (uint32_t n = begin; n < end; ++n) {
        if (s->sectors[n].state == SECTOR_FREE || s->sectors[n].retired) {
            candidate = (int)n;
            break;
        }
    }
    bool can_reclaim = !metadata || !has_retired(s);
    if (candidate < 0 && can_reclaim) {
        for (uint32_t n = begin; n < end; ++n) {
            /* Preserve the newest lane as the durable generation/counter
             * checkpoint while recycling an older fully ACKed sector. */
            if ((int)n == latest || s->sectors[n].state != SECTOR_VALID ||
                s->sectors[n].pending != 0U) continue;
            if (candidate < 0 || s->sectors[n].generation < s->sectors[candidate].generation)
                candidate = (int)n;
        }
    }
    if (candidate < 0 && !metadata && s->config.evict_oldest) {
        for (uint32_t n = begin; n < end; ++n) {
            if ((int)n == latest || s->sectors[n].state != SECTOR_VALID) continue;
            if (s->has_pin && s->pinned.sector == n &&
                s->pinned.sector_generation == s->sectors[n].generation) continue;
            if (candidate < 0 || s->sectors[n].generation < s->sectors[candidate].generation)
                candidate = (int)n;
        }
        if (candidate >= 0) {
            collection_spool_result_t result = retire_sector(s, (uint32_t)candidate);
            if (result != COLLECTION_SPOOL_OK) return result;
        }
    }
    if (candidate < 0) return metadata ? COLLECTION_SPOOL_PROTECTED_FULL : COLLECTION_SPOOL_FULL;
    collection_spool_result_t result = create_sector(s, (uint32_t)candidate);
    if (result == COLLECTION_SPOOL_OK) *selected = (uint32_t)candidate;
    return result;
}

static collection_spool_result_t append_internal(collection_spool_t *s,
    collection_spool_kind_t kind, uint32_t source_id, uint64_t source_seq,
    const void *payload, size_t bytes, collection_spool_record_t *written)
{
    uint32_t n;
    if (s->ticket >= UINT64_MAX - 1U || s->generation >= UINT64_MAX - 1U)
        return COLLECTION_SPOOL_FULL;
    collection_spool_result_t result = reserve_sector(s, kind != COLLECTION_SPOOL_DATA,
        RH + aligned(bytes), &n);
    if (result != COLLECTION_SPOOL_OK) return result;
    collection_spool_sector_t *sector = &s->sectors[n];
    uint32_t at = sector->end;
    uint8_t h[RH];
    memset(h, 0xff, sizeof(h));
    put32(h, RECORD_MAGIC);
    put32(h + 4, (uint32_t)bytes);
    put64(h + 8, ++s->ticket);
    put32(h + 16, source_id);
    put32(h + 20, (uint32_t)kind);
    put64(h + 24, source_seq);
    put32(h + 32, crc32(payload, bytes));
    put32(h + 36, crc32(h, 36U));
    if (!write_at(s, base(s, n) + at, h, 40U)) return COLLECTION_SPOOL_IO_ERROR;
    size_t whole = bytes & ~(size_t)3U;
    if (whole && !write_at(s, base(s, n) + at + RH, payload, whole))
        return COLLECTION_SPOOL_IO_ERROR;
    if (whole != bytes) {
        uint8_t tail[4] = {0xffU, 0xffU, 0xffU, 0xffU};
        memcpy(tail, (const uint8_t *)payload + whole, bytes - whole);
        if (!write_at(s, base(s, n) + at + RH + whole, tail, 4U))
            return COLLECTION_SPOOL_IO_ERROR;
    }
    put32(h + 40, COMMIT);
    if (!write_at(s, base(s, n) + at + 40U, h + 40U, 4U))
        return COLLECTION_SPOOL_IO_ERROR;
    sector->end += RH + (uint32_t)aligned(bytes);
    ++sector->records;
    ++sector->pending;
    sector->pending_bytes += (uint32_t)bytes;
    if (written) decode_record(h, n, at, sector->generation, written);
    return COLLECTION_SPOOL_OK;
}

collection_spool_result_t collection_spool_append(collection_spool_t *s,
    collection_spool_kind_t kind, uint32_t source_id, uint64_t source_seq,
    const void *payload, size_t bytes, collection_spool_record_t *written)
{
    if (!s || !s->initialized || !payload || !bytes ||
        (kind != COLLECTION_SPOOL_DATA && kind != COLLECTION_SPOOL_METADATA))
        return COLLECTION_SPOOL_BAD_ARGUMENT;
    if (bytes > s->stats.max_payload_bytes) return COLLECTION_SPOOL_TOO_LARGE;
    return append_internal(s, kind, source_id, source_seq, payload, bytes, written);
}

static collection_spool_result_t head(collection_spool_t *s,
    collection_spool_record_t *out)
{
    bool found = false;
    uint8_t h[RH];
    for (uint32_t n = 0U; n < s->sector_count; ++n) {
        collection_spool_sector_t *sector = &s->sectors[n];
        if (sector->state != SECTOR_VALID || sector->retired || !sector->pending) continue;
        for (uint32_t at = SH; at < sector->end;) {
            if (!read_at(s, base(s, n) + at, h, RH)) return COLLECTION_SPOOL_IO_ERROR;
            uint32_t bytes = get32(h + 4);
            if (!bytes || bytes > s->config.erase_bytes - at - RH ||
                get32(h) != RECORD_MAGIC || get32(h + 40) != COMMIT ||
                get32(h + 36) != crc32(h, 36U)) return COLLECTION_SPOOL_CORRUPT;
            if (get32(h + 44) != 0U) {
                if (!found || get64(h + 8) < out->token.ticket) {
                    decode_record(h, n, at, sector->generation, out);
                    found = true;
                }
                break;
            }
            at += RH + (uint32_t)aligned(bytes);
        }
    }
    return found ? COLLECTION_SPOOL_OK : COLLECTION_SPOOL_EMPTY;
}

collection_spool_result_t collection_spool_peek(collection_spool_t *s,
    collection_spool_record_t *out, void *payload, size_t capacity)
{
    if (!s || !s->initialized || !out || !payload) return COLLECTION_SPOOL_BAD_ARGUMENT;
    collection_spool_result_t result = head(s, out);
    if (result != COLLECTION_SPOOL_OK) return result;
    if (capacity < out->token.payload_bytes) return COLLECTION_SPOOL_BUFFER_TOO_SMALL;
    if (!read_at(s, base(s, out->token.sector) + out->token.offset + RH,
                 payload, out->token.payload_bytes)) return COLLECTION_SPOOL_IO_ERROR;
    if (crc32(payload, out->token.payload_bytes) != out->token.payload_crc32)
        return COLLECTION_SPOOL_CORRUPT;
    return COLLECTION_SPOOL_OK;
}

static bool same_token(const collection_spool_token_t *a, const collection_spool_token_t *b)
{
    return a->sector_generation == b->sector_generation && a->ticket == b->ticket &&
           a->sector == b->sector && a->offset == b->offset &&
           a->payload_bytes == b->payload_bytes && a->payload_crc32 == b->payload_crc32;
}

collection_spool_result_t collection_spool_pin(collection_spool_t *s,
    const collection_spool_token_t *token)
{
    if (!s || !s->initialized || !token) return COLLECTION_SPOOL_BAD_ARGUMENT;
    collection_spool_record_t current;
    collection_spool_result_t result = head(s, &current);
    if (result != COLLECTION_SPOOL_OK) return result;
    if (!same_token(token, &current.token)) return COLLECTION_SPOOL_ACK_MISMATCH;
    s->pinned = *token;
    s->has_pin = true;
    return COLLECTION_SPOOL_OK;
}

void collection_spool_unpin(collection_spool_t *s)
{
    if (s) s->has_pin = false;
}

collection_spool_result_t collection_spool_ack(collection_spool_t *s,
    const collection_spool_token_t *token)
{
    if (!s || !s->initialized || !token) return COLLECTION_SPOOL_BAD_ARGUMENT;
    collection_spool_record_t current;
    collection_spool_result_t result = head(s, &current);
    if (result != COLLECTION_SPOOL_OK) return result == COLLECTION_SPOOL_EMPTY
        ? COLLECTION_SPOOL_ACK_MISMATCH : result;
    const collection_spool_token_t *now = &current.token;
    if (!same_token(token, now))
        return COLLECTION_SPOOL_ACK_MISMATCH;
    uint8_t ack[4] = {0U, 0U, 0U, 0U};
    if (!write_at(s, base(s, now->sector) + now->offset + 44U, ack, sizeof(ack)))
        return COLLECTION_SPOOL_IO_ERROR;
    collection_spool_sector_t *sector = &s->sectors[now->sector];
    --sector->pending;
    sector->pending_bytes -= now->payload_bytes;
    if (s->has_pin && same_token(&s->pinned, now)) s->has_pin = false;
    ++s->stats.acked_records_this_boot;
    return COLLECTION_SPOOL_OK;
}

void collection_spool_get_stats(const collection_spool_t *s,
    collection_spool_stats_t *out)
{
    if (!s || !out) return;
    *out = s->stats;
    int newest_data = latest_sector(s, false), newest_meta = latest_sector(s, true);
    for (uint32_t n = 0U; n < s->sector_count; ++n) {
        const collection_spool_sector_t *sector = &s->sectors[n];
        if (sector->retired || sector->state == SECTOR_QUARANTINED ||
            sector->state == SECTOR_FOREIGN || sector->state == SECTOR_CORRUPT) continue;
        out->pending_records += sector->pending;
        out->pending_payload_bytes += sector->pending_bytes;
        if (n < s->config.protected_sectors) {
            out->protected_pending_records += sector->pending;
            out->protected_retained_bytes += sector->end > SH ? sector->end - SH : 0U;
        }
        if (!sector->sealed && (sector->state == SECTOR_FREE ||
            (int)n == newest_data || (int)n == newest_meta))
            out->append_free_bytes += s->config.erase_bytes - sector->end;
    }
}

collection_spool_result_t collection_spool_decode_loss(const void *payload,
    size_t bytes, collection_spool_loss_t *out)
{
    const uint8_t *p = payload;
    if (!p || !out || bytes < LOSS_HEAD || get32(p) != LOSS_MAGIC || get32(p + 12) != 1U)
        return COLLECTION_SPOOL_BAD_ARGUMENT;
    uint32_t count = get32(p + 4);
    if (!count || count > COLLECTION_SPOOL_MAX_SOURCES || bytes != LOSS_HEAD + count * LOSS_ENTRY)
        return COLLECTION_SPOOL_CORRUPT;
    memset(out, 0, sizeof(*out));
    out->source_count = count;
    out->evicted_records_total = get64(p + 24);
    out->evicted_bytes_total = get64(p + 32);
    for (uint32_t i = 0U; i < count; ++i) {
        const uint8_t *entry = p + LOSS_HEAD + i * LOSS_ENTRY;
        collection_spool_loss_source_t *to = &out->sources[i];
        to->source_id = get32(entry);
        to->records = get32(entry + 4);
        to->payload_bytes = get64(entry + 8);
        to->first_source_seq = get64(entry + 16);
        to->last_source_seq = get64(entry + 24);
        to->first_ticket = get64(entry + 32);
        to->last_ticket = get64(entry + 40);
        if (!to->records || to->last_ticket < to->first_ticket) return COLLECTION_SPOOL_CORRUPT;
    }
    return COLLECTION_SPOOL_OK;
}

const char *collection_spool_result_name(collection_spool_result_t result)
{
    switch (result) {
    case COLLECTION_SPOOL_OK: return "ok";
    case COLLECTION_SPOOL_EMPTY: return "empty";
    case COLLECTION_SPOOL_FULL: return "full";
    case COLLECTION_SPOOL_PROTECTED_FULL: return "protected_full";
    case COLLECTION_SPOOL_TOO_LARGE: return "too_large";
    case COLLECTION_SPOOL_BAD_ARGUMENT: return "bad_argument";
    case COLLECTION_SPOOL_IO_ERROR: return "io_error";
    case COLLECTION_SPOOL_FOREIGN_DATA: return "foreign_data";
    case COLLECTION_SPOOL_CORRUPT: return "corrupt";
    case COLLECTION_SPOOL_ACK_MISMATCH: return "ack_mismatch";
    case COLLECTION_SPOOL_BUFFER_TOO_SMALL: return "buffer_too_small";
    default: return "unknown";
    }
}
