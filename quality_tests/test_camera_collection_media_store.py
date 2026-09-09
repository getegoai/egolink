import hashlib
import unittest

from quality_tests.native_convergence import run_c


HARNESS = r'''
#include "photo_media_store.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define SLOT 4096U
#define ERASE 1024U
#define SLOTS 4U
static uint8_t flash_bytes[SLOT*SLOTS];
static unsigned write_calls;
static unsigned fail_write_call;
static size_t fail_after;
static bool fail_erase;

static bool flash_read(void *context,size_t at,void *out,size_t bytes){
    (void)context;if(at+bytes>sizeof(flash_bytes))return false;
    memcpy(out,flash_bytes+at,bytes);return true;
}
static bool flash_write(void *context,size_t at,const void *data,size_t bytes){
    (void)context;if(at+bytes>sizeof(flash_bytes))return false;
    ++write_calls;size_t allowed=bytes;
    bool success=true;
    if(fail_write_call==write_calls){allowed=fail_after<bytes?fail_after:bytes;success=false;}
    const uint8_t *p=data;
    for(size_t i=0;i<allowed;++i){
        if((flash_bytes[at+i]&p[i])!=p[i])return false;
        flash_bytes[at+i]&=p[i];
    }
    return success;
}
static bool flash_erase(void *context,size_t at,size_t bytes){
    (void)context;if(at+bytes>sizeof(flash_bytes)||at%ERASE||bytes%ERASE)return false;
    if(fail_erase)return false;
    memset(flash_bytes+at,0xff,bytes);return true;
}
static photo_media_store_config_t config(uint32_t max_photos){
    photo_media_store_config_t c={0};c.read=flash_read;c.write=flash_write;c.erase=flash_erase;
    c.capacity_bytes=sizeof(flash_bytes);c.erase_bytes=ERASE;c.slot_bytes=SLOT;
    c.max_payload_bytes=SLOT-PHOTO_MEDIA_STORE_HEADER_BYTES;c.max_committed_photos=max_photos;
    c.max_committed_payload_bytes=(uint64_t)c.max_payload_bytes*max_photos;return c;
}
static void digest_of(const void *data,size_t bytes,uint8_t out[32]){
    /* Test vectors are injected by Python; this helper selects the known ones. */
    static const uint8_t abc[32]={
      0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
      0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};
    static const uint8_t xyz[32]={
      0x36,0x08,0xbc,0xa1,0xe4,0x4e,0xa6,0xc4,0xd2,0x68,0xeb,0x6d,0xb0,0x22,0x60,0x26,
      0x98,0x92,0xc0,0xb4,0x2b,0x86,0xbb,0xf1,0xe7,0x7a,0x6f,0xa1,0x6c,0x3c,0x92,0x82};
    if(bytes==3U&&memcmp(data,"abc",3U)==0)memcpy(out,abc,32U);
    else if(bytes==3U&&memcmp(data,"xyz",3U)==0)memcpy(out,xyz,32U);
    else assert(!"missing SHA-256 test vector");
}
static photo_media_store_record_t put(photo_media_store_t *s,const char *id,const char *payload){
    uint8_t sha[32];size_t n=strlen(payload);digest_of(payload,n,sha);
    photo_media_store_record_t r;assert(photo_media_store_prepare(s,id,n,sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(s,&r,0U,payload,n)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_commit(s,&r)==PHOTO_MEDIA_STORE_OK);return r;
}

static void roundtrip_reboot_same_id(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);
    assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t r=put(&a,"photo-001","abc");
    char out[4]={0};assert(photo_media_store_read(&a,&r,0U,out,3U)==PHOTO_MEDIA_STORE_OK);
    assert(strcmp(out,"abc")==0);
    photo_media_store_t b;assert(photo_media_store_init(&b,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t found;assert(photo_media_store_find(&b,"photo-001",&found)==PHOTO_MEDIA_STORE_OK);
    assert(found.slot==r.slot&&found.payload_bytes==3U);
    uint8_t sha[32];digest_of("abc",3U,sha);
    photo_media_store_record_t duplicate;
    assert(photo_media_store_prepare(&b,"photo-001",3U,sha,&duplicate)==PHOTO_MEDIA_STORE_ALREADY_COMMITTED);
    assert(duplicate.slot==r.slot);
    digest_of("xyz",3U,sha);
    assert(photo_media_store_prepare(&b,"photo-001",3U,sha,&duplicate)==PHOTO_MEDIA_STORE_IDENTITY_CONFLICT);
}

static void torn_and_retry_same_id(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    uint8_t sha[32];digest_of("abc",3U,sha);photo_media_store_record_t r;
    assert(photo_media_store_prepare(&a,"photo-torn",3U,sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&r,0U,"ab",2U)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_t b;assert(photo_media_store_init(&b,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_stats_t stats;photo_media_store_get_stats(&b,&stats);
    assert(stats.torn_slots==0U&&stats.reconciled_torn_slots==1U);
    assert(photo_media_store_find(&b,"photo-torn",&r)==PHOTO_MEDIA_STORE_NOT_FOUND);
    assert(photo_media_store_prepare(&b,"photo-torn",3U,sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(r.slot==0U);assert(photo_media_store_write(&b,&r,0U,"abc",3U)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_commit(&b,&r)==PHOTO_MEDIA_STORE_OK);
}

static void cut_write_and_cut_commit(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    uint8_t sha[32];digest_of("abc",3U,sha);photo_media_store_record_t r;
    assert(photo_media_store_prepare(&a,"cut-write",3U,sha,&r)==PHOTO_MEDIA_STORE_OK);
    fail_write_call=write_calls+1U;fail_after=1U;
    assert(photo_media_store_write(&a,&r,0U,"abc",3U)==PHOTO_MEDIA_STORE_IO_ERROR);
    photo_media_store_stats_t stats;photo_media_store_get_stats(&a,&stats);
    assert(stats.reconciled_torn_slots==1U&&stats.empty_slots==SLOTS);
    photo_media_store_t b;fail_write_call=0U;assert(photo_media_store_init(&b,&c)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_prepare(&b,"cut-commit",3U,sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&b,&r,0U,"abc",3U)==PHOTO_MEDIA_STORE_OK);
    fail_write_call=write_calls+1U;fail_after=2U;
    assert(photo_media_store_commit(&b,&r)==PHOTO_MEDIA_STORE_IO_ERROR);
    photo_media_store_get_stats(&b,&stats);
    assert(stats.reconciled_torn_slots==1U&&stats.empty_slots==SLOTS);
    photo_media_store_t reboot;fail_write_call=0U;assert(photo_media_store_init(&reboot,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_get_stats(&reboot,&stats);assert(stats.reconciled_owned_slots==0U);
}

static void committed_despite_callback_error_is_reconciled(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    uint8_t sha[32];digest_of("abc",3U,sha);photo_media_store_record_t r;
    assert(photo_media_store_prepare(&a,"commit-uncertain",3U,sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&r,0U,"abc",3U)==PHOTO_MEDIA_STORE_OK);
    fail_write_call=write_calls+1U;fail_after=4U;
    assert(photo_media_store_commit(&a,&r)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t duplicate;fail_write_call=0U;
    assert(photo_media_store_prepare(&a,"commit-uncertain",3U,sha,&duplicate)==PHOTO_MEDIA_STORE_ALREADY_COMMITTED);
    assert(duplicate.slot==r.slot);
}

static void corruption_full_release(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(2U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t first=put(&a,"first","abc");(void)put(&a,"second","xyz");
    uint8_t sha[32];digest_of("abc",3U,sha);photo_media_store_record_t third;
    assert(photo_media_store_prepare(&a,"third",3U,sha,&third)==PHOTO_MEDIA_STORE_FULL);
    assert(photo_media_store_release(&a,&first)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_prepare(&a,"third",3U,sha,&third)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&third,0U,"abc",3U)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_commit(&a,&third)==PHOTO_MEDIA_STORE_OK);
    flash_bytes[(size_t)third.slot*SLOT+PHOTO_MEDIA_STORE_HEADER_BYTES]&=0xfeU;
    photo_media_store_t b;assert(photo_media_store_init(&b,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_stats_t stats;photo_media_store_get_stats(&b,&stats);
    assert(stats.reconciled_corrupt_slots==1U&&stats.committed_slots==1U);
    assert(photo_media_store_find(&b,"third",&third)==PHOTO_MEDIA_STORE_NOT_FOUND);
}

static void large_multichunk_sha(void){
    static const uint8_t sha[32]={
      0x41,0xed,0xec,0xe4,0x2d,0x63,0xe8,0xd9,0xbf,0x51,0x5a,0x9b,0xa6,0x93,0x2e,0x1c,
      0x20,0xcb,0xc9,0xf5,0xa5,0xd1,0x34,0x64,0x5a,0xdb,0x5d,0xb1,0xb9,0x73,0x7e,0xa3};
    uint8_t payload[1000];memset(payload,'a',sizeof(payload));
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t r;assert(photo_media_store_prepare(&a,"large",sizeof(payload),sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&r,0U,payload,333U)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&r,333U,payload+333U,sizeof(payload)-333U)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_commit(&a,&r)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_t b;assert(photo_media_store_init(&b,&c)==PHOTO_MEDIA_STORE_OK);
    uint8_t tail[17];assert(photo_media_store_read(&b,&r,983U,tail,sizeof(tail))==PHOTO_MEDIA_STORE_OK);
    for(size_t i=0U;i<sizeof(tail);++i)assert(tail[i]=='a');
}

static void uncertain_release_requires_reinit(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;fail_erase=false;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t r=put(&a,"release-fault","abc");
    fail_erase=true;assert(photo_media_store_release(&a,&r)==PHOTO_MEDIA_STORE_IO_ERROR);
    assert(photo_media_store_find(&a,"release-fault",&r)==PHOTO_MEDIA_STORE_BAD_ARGUMENT);
    fail_erase=false;assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_find(&a,"release-fault",&r)==PHOTO_MEDIA_STORE_OK);
}

static void deterministic_verified_reboot_enumeration(void){
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;fail_erase=false;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    (void)put(&a,"enumerate-first","abc");(void)put(&a,"enumerate-second","xyz");
    photo_media_store_t reboot;assert(photo_media_store_init(&reboot,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t first,second;
    assert(photo_media_store_peek_committed(&reboot,0U,&first)==PHOTO_MEDIA_STORE_OK);
    assert(strcmp(first.photo_id,"enumerate-first")==0);
    assert(photo_media_store_peek_committed(&reboot,first.slot+1U,&second)==PHOTO_MEDIA_STORE_OK);
    assert(strcmp(second.photo_id,"enumerate-second")==0);
    assert(photo_media_store_peek_committed(&reboot,second.slot+1U,&second)==PHOTO_MEDIA_STORE_NOT_FOUND);
    flash_bytes[(size_t)first.slot*SLOT+PHOTO_MEDIA_STORE_HEADER_BYTES]&=0xfeU;
    assert(photo_media_store_peek_committed(&reboot,0U,&first)==PHOTO_MEDIA_STORE_CORRUPT);
}

static void torn_release_header_erased_payload_residue_is_scrubbed(void){
    static const uint8_t sha[32]={
      0x41,0xed,0xec,0xe4,0x2d,0x63,0xe8,0xd9,0xbf,0x51,0x5a,0x9b,0xa6,0x93,0x2e,0x1c,
      0x20,0xcb,0xc9,0xf5,0xa5,0xd1,0x34,0x64,0x5a,0xdb,0x5d,0xb1,0xb9,0x73,0x7e,0xa3};
    uint8_t payload[1000];memset(payload,'a',sizeof(payload));
    memset(flash_bytes,0xff,sizeof(flash_bytes));write_calls=fail_write_call=0U;
    photo_media_store_t a;photo_media_store_config_t c=config(4U);
    assert(photo_media_store_init(&a,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_record_t r;
    assert(photo_media_store_prepare(&a,"release-cut",sizeof(payload),sha,&r)==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_write(&a,&r,0U,payload,sizeof(payload))==PHOTO_MEDIA_STORE_OK);
    assert(photo_media_store_commit(&a,&r)==PHOTO_MEDIA_STORE_OK);
    memset(flash_bytes+(size_t)r.slot*SLOT,0xff,ERASE);
    assert(flash_bytes[(size_t)r.slot*SLOT+ERASE]=='a');
    photo_media_store_t reboot;assert(photo_media_store_init(&reboot,&c)==PHOTO_MEDIA_STORE_OK);
    photo_media_store_stats_t stats;photo_media_store_get_stats(&reboot,&stats);
    assert(stats.reconciled_torn_slots==1U&&stats.empty_slots==SLOTS);
    for(size_t i=(size_t)r.slot*SLOT;i<(size_t)(r.slot+1U)*SLOT;++i)
        assert(flash_bytes[i]==0xffU);
}

int main(void){
    roundtrip_reboot_same_id();torn_and_retry_same_id();cut_write_and_cut_commit();committed_despite_callback_error_is_reconciled();corruption_full_release();large_multichunk_sha();uncertain_release_requires_reinit();deterministic_verified_reboot_enumeration();torn_release_header_erased_payload_residue_is_scrubbed();
    puts("photo_media_store: ok");return 0;
}
'''


class CameraCollectionMediaStoreTests(unittest.TestCase):
    def test_photo_media_store_power_cut_integrity_quota_and_identity(self):
        self.assertEqual(
            hashlib.sha256(b"abc").hexdigest(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )
        self.assertEqual(
            hashlib.sha256(b"xyz").hexdigest(),
            "3608bca1e44ea6c4d268eb6db02260269892c0b42b86bbf1e77a6fa16c3c9282",
        )
        self.assertEqual(
            hashlib.sha256(b"a" * 1000).hexdigest(),
            "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3",
        )
        output = run_c(HARNESS, components=("photo_media_store",))
        self.assertEqual(output.strip(), "photo_media_store: ok")
