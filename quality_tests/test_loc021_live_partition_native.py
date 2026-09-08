"""Execute the actual partition adapter + durable core, with bounded flash I/O.

No hardware claim: the shim enforces partition ranges and NOR write semantics.
The same harness can diagnose an operator-approved, private saved flash readback.
"""
import csv
import json
import unittest

from quality_tests.native_convergence import IDF, ROOT, run_c

HEADERS = {
    "esp_err.h": """typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 258
#define ESP_ERR_INVALID_STATE 259
#define ESP_ERR_INVALID_SIZE 260
#define ESP_ERR_NOT_FOUND 261
""",
    "esp_partition.h": """#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
typedef int esp_partition_subtype_t;
#define ESP_PARTITION_TYPE_DATA 1
typedef struct { int type, subtype; uint32_t address, size, erase_size; char label[17]; } esp_partition_t;
const esp_partition_t *esp_partition_find_first(int,esp_partition_subtype_t,const char*);
esp_err_t esp_partition_read(const esp_partition_t*,size_t,void*,size_t);
esp_err_t esp_partition_write(const esp_partition_t*,size_t,const void*,size_t);
esp_err_t esp_partition_erase_range(const esp_partition_t*,size_t,size_t);
""",
}
HARNESS = r'''
#include "persistent_priority_outbox_partition.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"failed:%d\n",__LINE__); return 1; } } while(0)
static unsigned char flash[0x200000], before[0x200000];
static unsigned erases, writes;
static int fail_write, corrupt_verify;
static esp_partition_t partition={.type=1,.subtype=0x40,.address=TEST_OFFSET,.size=0xc000,.erase_size=4096,.label="ego_outbox"};
static egolink_outbox_partition_t adapter;
static egolink_outbox_storage_t storage;
static egolink_outbox_t outbox;
static egolink_outbox_init_report_t report;
const esp_partition_t *esp_partition_find_first(int type,esp_partition_subtype_t sub,const char*label) {
 return type==1 && sub==0x40 && strcmp(label,"ego_outbox")==0 ? &partition : NULL;
}
static int range(const esp_partition_t*p,size_t off,size_t n) {
 return p==&partition && off<=p->size && n<=p->size-off && p->address+p->size<=sizeof(flash);
}
esp_err_t esp_partition_read(const esp_partition_t*p,size_t off,void*dst,size_t n) {
 if(!range(p,off,n))return ESP_FAIL;
 memcpy(dst,flash+p->address+off,n);
 if(corrupt_verify && writes && n) ((unsigned char*)dst)[0]^=1;
 return ESP_OK;
}
esp_err_t esp_partition_erase_range(const esp_partition_t*p,size_t off,size_t n) {
 if(!range(p,off,n) || off%4096 || n!=24576)return ESP_FAIL;
 ++erases;memset(flash+p->address+off,255,n);return ESP_OK;
}
esp_err_t esp_partition_write(const esp_partition_t*p,size_t off,const void*src,size_t n) {
 if(!range(p,off,n) || n!=22240)return ESP_FAIL;
 ++writes;if(fail_write)return ESP_FAIL;
 const unsigned char *b=src;
 for(size_t i=0;i<n;++i){ if((flash[p->address+off+i]&b[i])!=b[i])return ESP_FAIL;flash[p->address+off+i]=b[i]; }
 return ESP_OK;
}
static egolink_outbox_status_t initialize(void) {
 const egolink_outbox_config_t cfg={.device_id="ego-link-001",.max_records=4,.reserved_critical_records=1,
 .max_total_payload_bytes=16384,.max_payload_bytes=4096,.base_retry_ms=1000,.max_retry_ms=60000,.tombstone_capacity=8};
 return egolink_outbox_init(&outbox,&cfg,&storage,1,0,&report);
}
int main(void) {
 memset(flash,255,sizeof(flash));
#ifdef READBACK_PATH
 FILE *f=fopen(READBACK_PATH,"rb");CHECK(f);
 CHECK(fread(flash,1,sizeof(flash),f)==sizeof(flash));CHECK(fgetc(f)==EOF);CHECK(fclose(f)==0);
#else
 /* Occupied old range, unknown provenance: never provision over these bytes. */
 memset(flash+0x110000,0x5a,0xc000);
#endif
 memcpy(before,flash,sizeof(flash));
 CHECK(egolink_outbox_partition_init(&adapter)==ESP_OK);
 CHECK(egolink_outbox_partition_storage(&adapter,&storage)==ESP_OK);
 egolink_outbox_status_t status=initialize();
 if(TEST_OFFSET==0x110000) {
  CHECK(status==EGOLINK_OUTBOX_STORAGE_CORRUPTION);
  CHECK(report.slot_state[0]==EGOLINK_OUTBOX_SLOT_CORRUPT && report.slot_state[1]==EGOLINK_OUTBOX_SLOT_CORRUPT);
  CHECK(erases==0 && writes==0 && memcmp(before,flash,sizeof(flash))==0);
 } else {
  CHECK(status==EGOLINK_OUTBOX_OK && report.recovery_state==EGOLINK_OUTBOX_RECOVERY_NEW_MIRRORS);
  CHECK(erases==2 && writes==2);
  CHECK(memcmp(before,flash,TEST_OFFSET)==0);
  CHECK(memcmp(before+TEST_OFFSET+0xc000,flash+TEST_OFFSET+0xc000,sizeof(flash)-TEST_OFFSET-0xc000)==0);
  CHECK(initialize()==EGOLINK_OUTBOX_OK && report.recovery_state==EGOLINK_OUTBOX_RECOVERY_EQUAL_MIRRORS);
  CHECK(erases==2 && writes==2);
 }
 printf("{\"status\":\"%s\",\"slot0\":\"%s\",\"slot1\":\"%s\",\"erases\":%u,\"writes\":%u}\n",
  egolink_outbox_status_name(status),egolink_outbox_slot_state_name(report.slot_state[0]),egolink_outbox_slot_state_name(report.slot_state[1]),erases,writes);
#ifndef READBACK_PATH
 /* A first-write failure / readback mismatch cannot be called durable. */
 if(TEST_OFFSET!=0x110000) {
  memset(flash+TEST_OFFSET,255,0xc000);erases=0;writes=0;fail_write=1;
  CHECK(initialize()==EGOLINK_OUTBOX_STORAGE_ERROR && erases==1 && writes==1);
  fail_write=0;corrupt_verify=1;
  CHECK(initialize()==EGOLINK_OUTBOX_STORAGE_CORRUPTION); /* read failure remains unformatted */
  corrupt_verify=0;memset(flash+TEST_OFFSET,255,0xc000);erases=0;writes=0;corrupt_verify=1;
  CHECK(initialize()==EGOLINK_OUTBOX_STORAGE_ERROR && erases==1 && writes==1);
  corrupt_verify=0;CHECK(initialize()==EGOLINK_OUTBOX_OK);
 }
#endif
 return 0;
}
'''


def execute_partition(offset, readback=None):
    defines = [f"TEST_OFFSET={offset}"]
    if readback is not None:
        defines.append(f'READBACK_PATH="{readback.as_posix()}"')
    output = run_c(
        HARNESS,
        ["persistent_priority_outbox", "persistent_priority_outbox_partition"],
        extra_sources=[IDF / "components/json/cJSON/cJSON.c", *[
            IDF / "components/mbedtls/mbedtls/library" / name
            for name in ("sha256.c", "platform_util.c", "platform.c")]],
        headers=HEADERS, defines=defines,
    )
    return json.loads(output)


class LivePartitionNativeTests(unittest.TestCase):
    def test_occupied_old_slots_are_rejected_without_erase(self):
        self.assertEqual(execute_partition(0x110000)["erases"], 0)

    def test_live_csv_selected_region_initializes_recovers_and_fails_writes_honestly(self):
        path = ROOT / "firmware/mqtt_heartbeat/partitions_loc021_live.csv"
        rows = [row for row in csv.reader(path.read_text().splitlines())
                if row and not row[0].lstrip().startswith("#")]
        regions = {row[0].strip(): (int(row[3], 0), int(row[4], 0)) for row in rows}
        self.assertEqual(regions["nvs"], (0x9000, 0x6000))
        self.assertEqual(regions["factory"], (0x10000, 0x100000))
        offset, length = regions["ego_outbox"]
        self.assertEqual(length, 0xc000)
        self.assertGreaterEqual(offset, 0x11c000)
        self.assertLessEqual(offset + length, 0x200000)
        self.assertEqual(execute_partition(offset)["status"], "ok")
