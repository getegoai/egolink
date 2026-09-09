#include "photo_media_store.h"

#include <limits.h>
#include <string.h>

#define MEDIA_VERSION UINT32_C(3)
#define MEDIA_COMMIT UINT32_C(0x50484f54)
#define MEDIA_HEADER_CRC_OFFSET 28U
#define MEDIA_COMMIT_OFFSET 184U
#define MEDIA_CRC_BYTES MEDIA_COMMIT_OFFSET
#define SLOT_EMPTY 0U
#define SLOT_PREPARED 1U
#define SLOT_COMMITTED 2U
#define SLOT_TORN 3U
#define SLOT_CORRUPT 4U

static const uint8_t s_magic[8] = {
    UINT8_C(0x45), UINT8_C(0x47), UINT8_C(0x4f), UINT8_C(0x49),
    UINT8_C(0x4d), UINT8_C(0x47), UINT8_C(0x31), UINT8_C(0x00),
};

typedef struct {
    uint32_t state[8];
    uint64_t bits;
    uint8_t block[64];
    size_t used;
} sha256_t;

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8U) |
           ((uint32_t)p[2] << 16U) | ((uint32_t)p[3] << 24U);
}

static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0U; i < 4U; ++i) p[i] = (uint8_t)(v >> (8U * i));
}

static uint32_t rotr(uint32_t v, unsigned n)
{
    return (v >> n) | (v << (32U - n));
}

static void sha_transform(sha256_t *c, const uint8_t *block)
{
    static const uint32_t k[64] = {
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U,
    };
    uint32_t w[64];
    for (unsigned i = 0U; i < 16U; ++i) {
        const uint8_t *p = block + (i * 4U);
        w[i] = ((uint32_t)p[0] << 24U) | ((uint32_t)p[1] << 16U) |
               ((uint32_t)p[2] << 8U) | (uint32_t)p[3];
    }
    for (unsigned i = 16U; i < 64U; ++i) {
        uint32_t s0 = rotr(w[i - 15U], 7U) ^ rotr(w[i - 15U], 18U) ^ (w[i - 15U] >> 3U);
        uint32_t s1 = rotr(w[i - 2U], 17U) ^ rotr(w[i - 2U], 19U) ^ (w[i - 2U] >> 10U);
        w[i] = w[i - 16U] + s0 + w[i - 7U] + s1;
    }
    uint32_t a=c->state[0],b=c->state[1],d=c->state[3],e=c->state[4];
    uint32_t f=c->state[5],g=c->state[6],h=c->state[7],cc=c->state[2];
    for (unsigned i = 0U; i < 64U; ++i) {
        uint32_t s1=rotr(e,6U)^rotr(e,11U)^rotr(e,25U);
        uint32_t ch=(e&f)^((~e)&g);
        uint32_t t1=h+s1+ch+k[i]+w[i];
        uint32_t s0=rotr(a,2U)^rotr(a,13U)^rotr(a,22U);
        uint32_t maj=(a&b)^(a&cc)^(b&cc);
        uint32_t t2=s0+maj;
        h=g;g=f;f=e;e=d+t1;d=cc;cc=b;b=a;a=t1+t2;
    }
    c->state[0]+=a;c->state[1]+=b;c->state[2]+=cc;c->state[3]+=d;
    c->state[4]+=e;c->state[5]+=f;c->state[6]+=g;c->state[7]+=h;
}

static void sha_init(sha256_t *c)
{
    static const uint32_t initial[8] = {
        0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
        0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U,
    };
    memset(c, 0, sizeof(*c));
    memcpy(c->state, initial, sizeof(initial));
}

static void sha_update(sha256_t *c, const uint8_t *data, size_t bytes)
{
    c->bits += (uint64_t)bytes * UINT64_C(8);
    while (bytes) {
        size_t n = sizeof(c->block) - c->used;
        if (n > bytes) n = bytes;
        memcpy(c->block + c->used, data, n);
        c->used += n; data += n; bytes -= n;
        if (c->used == sizeof(c->block)) {
            sha_transform(c, c->block);
            c->used = 0U;
        }
    }
}

static void sha_finish(sha256_t *c, uint8_t out[PHOTO_MEDIA_STORE_SHA256_BYTES])
{
    uint64_t bits = c->bits;
    c->block[c->used++] = UINT8_C(0x80);
    if (c->used > 56U) {
        memset(c->block + c->used, 0, sizeof(c->block) - c->used);
        sha_transform(c, c->block); c->used = 0U;
    }
    memset(c->block + c->used, 0, 56U - c->used);
    for (unsigned i = 0U; i < 8U; ++i)
        c->block[63U - i] = (uint8_t)(bits >> (8U * i));
    sha_transform(c, c->block);
    for (unsigned i = 0U; i < 8U; ++i) {
        out[i*4U]=(uint8_t)(c->state[i]>>24U);
        out[i*4U+1U]=(uint8_t)(c->state[i]>>16U);
        out[i*4U+2U]=(uint8_t)(c->state[i]>>8U);
        out[i*4U+3U]=(uint8_t)c->state[i];
    }
}

static uint32_t crc_update(uint32_t crc, const void *data, size_t bytes)
{
    const uint8_t *p = data;
    for (size_t i = 0U; i < bytes; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0U; bit < 8U; ++bit)
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) & (0U - (crc & 1U)));
    }
    return crc;
}

static uint32_t header_crc(uint8_t header[PHOTO_MEDIA_STORE_HEADER_BYTES])
{
    uint8_t saved[4]; memcpy(saved, header + MEDIA_HEADER_CRC_OFFSET, 4U);
    memset(header + MEDIA_HEADER_CRC_OFFSET, 0, 4U);
    uint32_t crc = ~crc_update(UINT32_MAX, header, MEDIA_CRC_BYTES);
    memcpy(header + MEDIA_HEADER_CRC_OFFSET, saved, 4U);
    return crc;
}

static size_t slot_base(const photo_media_store_t *s, uint32_t slot)
{ return (size_t)slot * s->config.slot_bytes; }

static bool read_at(photo_media_store_t *s, size_t at, void *out, size_t bytes)
{
    if (s->config.read(s->config.context, at, out, bytes)) return true;
    ++s->stats.io_errors_this_boot; return false;
}

static bool write_at(photo_media_store_t *s, size_t at, const void *data, size_t bytes)
{
    uint8_t check[128]; const uint8_t *p = data;
    if (!s->config.write(s->config.context, at, data, bytes)) goto failed;
    for (size_t done=0U; done<bytes;) {
        size_t n=bytes-done; if(n>sizeof(check))n=sizeof(check);
        if(!s->config.read(s->config.context,at+done,check,n)||memcmp(check,p+done,n)!=0)goto failed;
        done+=n;
    }
    return true;
failed:
    ++s->stats.io_errors_this_boot; return false;
}

static bool all_erased(photo_media_store_t *s, size_t at, size_t bytes)
{
    uint8_t data[1024];
    for(size_t done=0U;done<bytes;){
        size_t n=bytes-done;if(n>sizeof(data))n=sizeof(data);
        if(!read_at(s,at+done,data,n))return false;
        for(size_t i=0U;i<n;++i)if(data[i]!=UINT8_MAX)return false;
        done+=n;
    }
    return true;
}

static bool erase_owned_slot(photo_media_store_t *s,uint32_t slot)
{
    const size_t at=slot_base(s,slot);
    if(!s->config.erase(s->config.context,at,s->config.slot_bytes)){
        ++s->stats.io_errors_this_boot;return false;
    }
    s->stats.erased_bytes_this_boot+=s->config.slot_bytes;
    return all_erased(s,at,s->config.slot_bytes);
}

static bool hash_payload(photo_media_store_t *s, uint32_t slot, size_t bytes,
                         uint8_t digest[PHOTO_MEDIA_STORE_SHA256_BYTES])
{
    uint8_t data[256]; sha256_t hash; sha_init(&hash);
    size_t at=slot_base(s,slot)+PHOTO_MEDIA_STORE_HEADER_BYTES;
    for(size_t done=0U;done<bytes;){
        size_t n=bytes-done;if(n>sizeof(data))n=sizeof(data);
        if(!read_at(s,at+done,data,n))return false;
        sha_update(&hash,data,n);done+=n;
    }
    sha_finish(&hash,digest);return true;
}

static bool decode_header(const uint8_t *h, uint32_t slot,
                          photo_media_store_record_t *record)
{
    uint32_t id_bytes=get32(h+20U);
    if(memcmp(h,s_magic,sizeof(s_magic))!=0||get32(h+8U)!=MEDIA_VERSION||
       get32(h+12U)!=PHOTO_MEDIA_STORE_HEADER_BYTES||
       id_bytes==0U||id_bytes>=PHOTO_MEDIA_STORE_ID_CAPACITY)return false;
    uint8_t copy[PHOTO_MEDIA_STORE_HEADER_BYTES];memcpy(copy,h,sizeof(copy));
    if(header_crc(copy)!=get32(h+MEDIA_HEADER_CRC_OFFSET))return false;
    memset(record,0,sizeof(*record));record->slot=slot;
    record->payload_bytes=get32(h+16U);record->identity_tag=get32(h+24U);
    memcpy(record->sha256,h+32U,PHOTO_MEDIA_STORE_SHA256_BYTES);
    memcpy(record->photo_id,h+64U,id_bytes);record->photo_id[id_bytes]='\0';
    record->capture_sequence_id=get32(h+148U);
    record->capture_monotonic_ns=
        (uint64_t)get32(h+152U)|((uint64_t)get32(h+156U)<<32U);
    record->retention_expires_at_unix_ms=
        (uint64_t)get32(h+160U)|((uint64_t)get32(h+164U)<<32U);
    record->capture_unix_ms=(uint64_t)get32(h+168U)|((uint64_t)get32(h+172U)<<32U);
    record->capture_boot_count=get32(h+176U);
    uint32_t dimensions=get32(h+180U);
    record->width=(uint16_t)dimensions;record->height=(uint16_t)(dimensions>>16U);
    if(!record->retention_expires_at_unix_ms||!record->capture_unix_ms||
       !record->capture_monotonic_ns||!record->capture_boot_count||
       !record->capture_sequence_id||!record->width||!record->height)return false;
    return true;
}

static bool record_matches(const photo_media_store_record_t *a,
                           const photo_media_store_record_t *b)
{
    return a&&b&&a->slot==b->slot&&a->payload_bytes==b->payload_bytes&&
           a->identity_tag==b->identity_tag&&
           a->retention_expires_at_unix_ms==b->retention_expires_at_unix_ms&&
           a->capture_unix_ms==b->capture_unix_ms&&
           a->capture_monotonic_ns==b->capture_monotonic_ns&&
           a->capture_boot_count==b->capture_boot_count&&
           a->capture_sequence_id==b->capture_sequence_id&&
           a->width==b->width&&a->height==b->height&&
           strcmp(a->photo_id,b->photo_id)==0&&
           memcmp(a->sha256,b->sha256,PHOTO_MEDIA_STORE_SHA256_BYTES)==0;
}

static photo_media_store_result_t read_record(photo_media_store_t *s,
    uint32_t slot, photo_media_store_record_t *record, bool require_commit)
{
    uint8_t header[PHOTO_MEDIA_STORE_HEADER_BYTES];
    if(!read_at(s,slot_base(s,slot),header,sizeof(header)))return PHOTO_MEDIA_STORE_IO_ERROR;
    if(!decode_header(header,slot,record))return PHOTO_MEDIA_STORE_CORRUPT;
    if(record->payload_bytes==0U||record->payload_bytes>s->config.max_payload_bytes||
       (size_t)record->payload_bytes+PHOTO_MEDIA_STORE_HEADER_BYTES>s->config.slot_bytes)
        return PHOTO_MEDIA_STORE_CORRUPT;
    if(require_commit&&get32(header+MEDIA_COMMIT_OFFSET)!=MEDIA_COMMIT)
        return PHOTO_MEDIA_STORE_INCOMPLETE;
    return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_init(photo_media_store_t *s,
    const photo_media_store_config_t *config)
{
    if(!s||!config||!config->read||!config->write||!config->erase||
       !config->erase_bytes||!config->slot_bytes||
       config->slot_bytes%config->erase_bytes||
       config->capacity_bytes%config->slot_bytes||
       config->slot_bytes<=PHOTO_MEDIA_STORE_HEADER_BYTES||
       !config->max_payload_bytes||
       config->max_payload_bytes>config->slot_bytes-PHOTO_MEDIA_STORE_HEADER_BYTES)
        return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    size_t count=config->capacity_bytes/config->slot_bytes;
    if(!count||count>PHOTO_MEDIA_STORE_MAX_SLOTS)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    memset(s,0,sizeof(*s));s->config=*config;s->slot_count=(uint32_t)count;
    s->stats.capacity_bytes=config->capacity_bytes;s->stats.slot_bytes=config->slot_bytes;
    s->stats.max_payload_bytes=config->max_payload_bytes;
    for(uint32_t slot=0U;slot<s->slot_count;++slot){
        uint8_t header[PHOTO_MEDIA_STORE_HEADER_BYTES];
        if(!read_at(s,slot_base(s,slot),header,sizeof(header)))return PHOTO_MEDIA_STORE_IO_ERROR;
        if(get32(header)==UINT32_MAX){
            if(all_erased(s,slot_base(s,slot),s->config.slot_bytes)){
                s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
            }else{
                if(!erase_owned_slot(s,slot))return PHOTO_MEDIA_STORE_IO_ERROR;
                s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
                ++s->stats.reconciled_owned_slots;
                ++s->stats.reconciled_torn_slots;
            }
            continue;
        }
        if(memcmp(header,s_magic,sizeof(s_magic))!=0){
            if(!erase_owned_slot(s,slot))return PHOTO_MEDIA_STORE_IO_ERROR;
            s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_unrecognized_slots;
            continue;
        }
        photo_media_store_record_t record;
        if(!decode_header(header,slot,&record)||record.payload_bytes==0U||
           record.payload_bytes>s->config.max_payload_bytes){
            if(!erase_owned_slot(s,slot))return PHOTO_MEDIA_STORE_IO_ERROR;
            s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_corrupt_slots;continue;
        }
        if(get32(header+MEDIA_COMMIT_OFFSET)!=MEDIA_COMMIT){
            if(!erase_owned_slot(s,slot))return PHOTO_MEDIA_STORE_IO_ERROR;
            s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_torn_slots;continue;
        }
        uint8_t digest[PHOTO_MEDIA_STORE_SHA256_BYTES];
        if(!hash_payload(s,slot,record.payload_bytes,digest))return PHOTO_MEDIA_STORE_IO_ERROR;
        if(memcmp(digest,record.sha256,sizeof(digest))!=0){
            if(!erase_owned_slot(s,slot))return PHOTO_MEDIA_STORE_IO_ERROR;
            s->slot_states[slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_corrupt_slots;continue;
        }
        s->slot_states[slot]=SLOT_COMMITTED;++s->stats.committed_slots;
        s->stats.committed_payload_bytes+=record.payload_bytes;
    }
    s->initialized=true;return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_find(photo_media_store_t *s,
    const char *photo_id, photo_media_store_record_t *record)
{
    if(!s||!s->initialized||!photo_id||!record)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    for(uint32_t slot=0U;slot<s->slot_count;++slot)
        if(s->slot_states[slot]==SLOT_COMMITTED){
        photo_media_store_record_t found;
        photo_media_store_result_t r=read_record(s,slot,&found,true);
        if(r!=PHOTO_MEDIA_STORE_OK)return r;
        if(strcmp(found.photo_id,photo_id)==0){*record=found;return PHOTO_MEDIA_STORE_OK;}
    }
    return PHOTO_MEDIA_STORE_NOT_FOUND;
}

photo_media_store_result_t photo_media_store_peek_committed(
    photo_media_store_t *s, uint32_t start_slot,
    photo_media_store_record_t *record)
{
    if(!s||!s->initialized||!record||start_slot>s->slot_count)
        return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    for(uint32_t slot=start_slot;slot<s->slot_count;++slot){
        if(s->slot_states[slot]!=SLOT_COMMITTED)continue;
        photo_media_store_record_t found;
        photo_media_store_result_t r=read_record(s,slot,&found,true);
        if(r!=PHOTO_MEDIA_STORE_OK)return r;
        uint8_t digest[PHOTO_MEDIA_STORE_SHA256_BYTES];
        if(!hash_payload(s,slot,found.payload_bytes,digest))
            return PHOTO_MEDIA_STORE_IO_ERROR;
        if(memcmp(digest,found.sha256,sizeof(digest))!=0)
            return PHOTO_MEDIA_STORE_CORRUPT;
        *record=found;return PHOTO_MEDIA_STORE_OK;
    }
    return PHOTO_MEDIA_STORE_NOT_FOUND;
}

photo_media_store_result_t photo_media_store_prepare_with_expiry(photo_media_store_t *s,
    const char *photo_id,size_t payload_bytes,
    const uint8_t sha256[PHOTO_MEDIA_STORE_SHA256_BYTES],
    uint64_t retention_expires_at_unix_ms,
    uint64_t capture_unix_ms,uint64_t capture_monotonic_ns,
    uint32_t capture_boot_count,uint32_t capture_sequence_id,
    uint16_t width,uint16_t height,
    photo_media_store_record_t *prepared)
{
    if(!s||!s->initialized||!photo_id||!sha256||!prepared||
       !retention_expires_at_unix_ms||!capture_unix_ms||!capture_boot_count||
       !capture_monotonic_ns||!capture_sequence_id||!width||!height)
        return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    size_t id_bytes=strlen(photo_id);
    if(!id_bytes||id_bytes>=PHOTO_MEDIA_STORE_ID_CAPACITY)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(!payload_bytes||payload_bytes>s->config.max_payload_bytes||payload_bytes>UINT32_MAX)
        return PHOTO_MEDIA_STORE_TOO_LARGE;
    if(s->active_valid)return PHOTO_MEDIA_STORE_BUSY;
    photo_media_store_record_t old;
    photo_media_store_result_t found=photo_media_store_find(s,photo_id,&old);
    if(found==PHOTO_MEDIA_STORE_OK){
        if(old.payload_bytes==(uint32_t)payload_bytes&&
           old.retention_expires_at_unix_ms==retention_expires_at_unix_ms&&
           old.capture_unix_ms==capture_unix_ms&&
           old.capture_monotonic_ns==capture_monotonic_ns&&
           old.capture_boot_count==capture_boot_count&&
           old.capture_sequence_id==capture_sequence_id&&
           old.width==width&&old.height==height&&
           memcmp(old.sha256,sha256,PHOTO_MEDIA_STORE_SHA256_BYTES)==0){
            *prepared=old;return PHOTO_MEDIA_STORE_ALREADY_COMMITTED;
        }
        return PHOTO_MEDIA_STORE_IDENTITY_CONFLICT;
    }
    if(found!=PHOTO_MEDIA_STORE_NOT_FOUND)return found;
    if((s->config.max_committed_photos&&s->stats.committed_slots>=s->config.max_committed_photos)||
       (s->config.max_committed_payload_bytes&&
        s->stats.committed_payload_bytes+payload_bytes>s->config.max_committed_payload_bytes))
        return PHOTO_MEDIA_STORE_FULL;
    uint32_t slot=s->slot_count;
    for(uint32_t i=0U;i<s->slot_count;++i)if(s->slot_states[i]==SLOT_EMPTY){slot=i;break;}
    if(slot==s->slot_count)return PHOTO_MEDIA_STORE_FULL;
    uint8_t header[PHOTO_MEDIA_STORE_HEADER_BYTES];memset(header,0,sizeof(header));
    memcpy(header,s_magic,sizeof(s_magic));put32(header+8U,MEDIA_VERSION);
    put32(header+12U,PHOTO_MEDIA_STORE_HEADER_BYTES);put32(header+16U,(uint32_t)payload_bytes);
    put32(header+20U,(uint32_t)id_bytes);
    uint32_t identity=~crc_update(UINT32_MAX,photo_id,id_bytes);
    identity=~crc_update(~identity,sha256,PHOTO_MEDIA_STORE_SHA256_BYTES);
    put32(header+24U,identity);memcpy(header+32U,sha256,PHOTO_MEDIA_STORE_SHA256_BYTES);
    memcpy(header+64U,photo_id,id_bytes);memset(header+MEDIA_COMMIT_OFFSET,UINT8_MAX,8U);
    put32(header+148U,capture_sequence_id);
    put32(header+152U,(uint32_t)capture_monotonic_ns);
    put32(header+156U,(uint32_t)(capture_monotonic_ns>>32U));
    put32(header+160U,(uint32_t)retention_expires_at_unix_ms);
    put32(header+164U,(uint32_t)(retention_expires_at_unix_ms>>32U));
    put32(header+168U,(uint32_t)capture_unix_ms);
    put32(header+172U,(uint32_t)(capture_unix_ms>>32U));
    put32(header+176U,capture_boot_count);
    put32(header+180U,(uint32_t)width|((uint32_t)height<<16U));
    put32(header+MEDIA_HEADER_CRC_OFFSET,header_crc(header));
    if(!write_at(s,slot_base(s,slot),header,sizeof(header))){
        if(erase_owned_slot(s,slot)){
            s->slot_states[slot]=SLOT_EMPTY;++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_torn_slots;
        }else{
            s->slot_states[slot]=SLOT_TORN;--s->stats.empty_slots;
            ++s->stats.torn_slots;s->initialized=false;
        }
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    memset(&s->active,0,sizeof(s->active));s->active.slot=slot;
    s->active.payload_bytes=(uint32_t)payload_bytes;s->active.identity_tag=identity;
    s->active.retention_expires_at_unix_ms=retention_expires_at_unix_ms;
    s->active.capture_unix_ms=capture_unix_ms;
    s->active.capture_monotonic_ns=capture_monotonic_ns;
    s->active.capture_boot_count=capture_boot_count;
    s->active.capture_sequence_id=capture_sequence_id;
    s->active.width=width;s->active.height=height;
    memcpy(s->active.photo_id,photo_id,id_bytes+1U);
    memcpy(s->active.sha256,sha256,PHOTO_MEDIA_STORE_SHA256_BYTES);
    s->active_written=0U;s->active_valid=true;s->slot_states[slot]=SLOT_PREPARED;
    --s->stats.empty_slots;*prepared=s->active;return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_prepare(photo_media_store_t *s,
    const char *photo_id,size_t payload_bytes,
    const uint8_t sha256[PHOTO_MEDIA_STORE_SHA256_BYTES],
    photo_media_store_record_t *prepared)
{
    return photo_media_store_prepare_with_expiry(
        s,photo_id,payload_bytes,sha256,UINT64_MAX,UINT64_MAX,UINT64_MAX,
        UINT32_MAX,UINT32_MAX,1U,1U,prepared);
}

photo_media_store_result_t photo_media_store_write(photo_media_store_t *s,
    const photo_media_store_record_t *record,size_t offset,const void *data,size_t bytes)
{
    if(!s||!s->initialized||!record||(!data&&bytes))return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(!s->active_valid||!record_matches(record,&s->active))return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(offset!=s->active_written||bytes>(size_t)s->active.payload_bytes-offset)
        return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(!bytes)return PHOTO_MEDIA_STORE_OK;
    if(!write_at(s,slot_base(s,record->slot)+PHOTO_MEDIA_STORE_HEADER_BYTES+offset,data,bytes)){
        s->active_valid=false;
        if(erase_owned_slot(s,record->slot)){
            s->slot_states[record->slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_torn_slots;
        }else{
            s->slot_states[record->slot]=SLOT_TORN;++s->stats.torn_slots;
            s->initialized=false;
        }
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    s->active_written+=bytes;s->stats.written_payload_bytes_this_boot+=bytes;
    return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_commit(photo_media_store_t *s,
    const photo_media_store_record_t *record)
{
    if(!s||!s->initialized||!record)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(!s->active_valid||!record_matches(record,&s->active))return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(s->active_written!=s->active.payload_bytes)return PHOTO_MEDIA_STORE_INCOMPLETE;
    uint8_t digest[PHOTO_MEDIA_STORE_SHA256_BYTES];
    if(!hash_payload(s,record->slot,record->payload_bytes,digest)){
        s->active_valid=false;
        if(erase_owned_slot(s,record->slot)){
            s->slot_states[record->slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_torn_slots;
        }else{
            s->slot_states[record->slot]=SLOT_TORN;++s->stats.torn_slots;
            s->initialized=false;
        }
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    if(memcmp(digest,record->sha256,sizeof(digest))!=0){
        s->active_valid=false;
        if(erase_owned_slot(s,record->slot)){
            s->slot_states[record->slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_corrupt_slots;
        }else{
            s->slot_states[record->slot]=SLOT_CORRUPT;++s->stats.corrupt_slots;
            s->initialized=false;
        }
        return PHOTO_MEDIA_STORE_CORRUPT;
    }
    uint8_t commit[4];put32(commit,MEDIA_COMMIT);
    if(!write_at(s,slot_base(s,record->slot)+MEDIA_COMMIT_OFFSET,commit,sizeof(commit))){
        /* A NOR callback can report failure after all commit bytes reached
         * flash. Reconcile before classifying the slot, otherwise retrying
         * the same photo_id could create a second committed copy. */
        photo_media_store_record_t stored;
        photo_media_store_result_t probe=read_record(s,record->slot,&stored,true);
        if(probe==PHOTO_MEDIA_STORE_OK&&record_matches(record,&stored)&&
           hash_payload(s,record->slot,record->payload_bytes,digest)&&
           memcmp(digest,record->sha256,sizeof(digest))==0){
            s->slot_states[record->slot]=SLOT_COMMITTED;s->active_valid=false;
            ++s->stats.committed_slots;s->stats.committed_payload_bytes+=record->payload_bytes;
            return PHOTO_MEDIA_STORE_OK;
        }
        s->active_valid=false;
        if(probe==PHOTO_MEDIA_STORE_INCOMPLETE){
            if(erase_owned_slot(s,record->slot)){
                s->slot_states[record->slot]=SLOT_EMPTY;++s->stats.empty_slots;
                ++s->stats.reconciled_owned_slots;
                ++s->stats.reconciled_torn_slots;
            }else{
                s->slot_states[record->slot]=SLOT_TORN;++s->stats.torn_slots;
                s->initialized=false;
            }
        }else if(erase_owned_slot(s,record->slot)){
            s->slot_states[record->slot]=SLOT_EMPTY;++s->stats.empty_slots;
            ++s->stats.reconciled_owned_slots;
            ++s->stats.reconciled_corrupt_slots;
        }else{
            /* Ownership is certain but erase/readback is not. Freeze the
             * medium; boot-time reconciliation will retry the exact slot. */
            s->slot_states[record->slot]=SLOT_CORRUPT;
            ++s->stats.corrupt_slots;s->initialized=false;
        }
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    s->slot_states[record->slot]=SLOT_COMMITTED;s->active_valid=false;
    ++s->stats.committed_slots;s->stats.committed_payload_bytes+=record->payload_bytes;
    return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_read(photo_media_store_t *s,
    const photo_media_store_record_t *record,size_t offset,void *out,size_t bytes)
{
    if(!s||!s->initialized||!record||(!out&&bytes)||record->slot>=s->slot_count||
       s->slot_states[record->slot]!=SLOT_COMMITTED)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    photo_media_store_record_t stored;photo_media_store_result_t r=read_record(s,record->slot,&stored,true);
    if(r!=PHOTO_MEDIA_STORE_OK)return r;
    if(!record_matches(record,&stored))return PHOTO_MEDIA_STORE_IDENTITY_CONFLICT;
    if(offset>stored.payload_bytes||bytes>(size_t)stored.payload_bytes-offset)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    if(!read_at(s,slot_base(s,stored.slot)+PHOTO_MEDIA_STORE_HEADER_BYTES+offset,out,bytes))return PHOTO_MEDIA_STORE_IO_ERROR;
    return PHOTO_MEDIA_STORE_OK;
}

photo_media_store_result_t photo_media_store_release(photo_media_store_t *s,
    const photo_media_store_record_t *record)
{
    if(!s||!s->initialized||!record||record->slot>=s->slot_count||
       s->slot_states[record->slot]!=SLOT_COMMITTED)return PHOTO_MEDIA_STORE_BAD_ARGUMENT;
    photo_media_store_record_t stored;photo_media_store_result_t r=read_record(s,record->slot,&stored,true);
    if(r!=PHOTO_MEDIA_STORE_OK)return r;
    if(!record_matches(record,&stored))return PHOTO_MEDIA_STORE_IDENTITY_CONFLICT;
    size_t at=slot_base(s,stored.slot);
    if(!s->config.erase(s->config.context,at,s->config.slot_bytes)){
        ++s->stats.io_errors_this_boot;
        /* The erase outcome is unknown. Refuse further mutations until init
         * rescans the medium instead of trusting stale in-memory counters. */
        s->initialized=false;
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    s->stats.erased_bytes_this_boot+=s->config.slot_bytes;
    if(!all_erased(s,at,s->config.slot_bytes)){
        s->initialized=false;
        return PHOTO_MEDIA_STORE_IO_ERROR;
    }
    s->slot_states[stored.slot]=SLOT_EMPTY;++s->stats.empty_slots;
    --s->stats.committed_slots;s->stats.committed_payload_bytes-=stored.payload_bytes;
    return PHOTO_MEDIA_STORE_OK;
}

void photo_media_store_get_stats(const photo_media_store_t *s,
                                 photo_media_store_stats_t *stats)
{ if(s&&stats)*stats=s->stats; }

const char *photo_media_store_result_name(photo_media_store_result_t result)
{
    switch(result){
    case PHOTO_MEDIA_STORE_OK:return "ok";
    case PHOTO_MEDIA_STORE_ALREADY_COMMITTED:return "already_committed";
    case PHOTO_MEDIA_STORE_NOT_FOUND:return "not_found";
    case PHOTO_MEDIA_STORE_FULL:return "full";
    case PHOTO_MEDIA_STORE_TOO_LARGE:return "too_large";
    case PHOTO_MEDIA_STORE_BAD_ARGUMENT:return "bad_argument";
    case PHOTO_MEDIA_STORE_BUSY:return "busy";
    case PHOTO_MEDIA_STORE_IDENTITY_CONFLICT:return "identity_conflict";
    case PHOTO_MEDIA_STORE_INCOMPLETE:return "incomplete";
    case PHOTO_MEDIA_STORE_IO_ERROR:return "io_error";
    case PHOTO_MEDIA_STORE_CORRUPT:return "corrupt";
    default:return "unknown";
    }
}
