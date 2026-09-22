"""Execute the real C engine and production DEVICE serializer through storage.

This deliberately exercises the source block used by health(), not a second
Python imitation of the state payload. It is offline schema/transport evidence.
"""
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from quality_tests.native_convergence import IDF, ROOT, run_c
from quality_tests.test_collection_ingest import DEVICE, envelope, raw_record
from server.message_hub import MessageHubStore


def production_health_capacity_probe(camera_profile):
    """Execute production health/envelope/engine/framing with offline snapshots.

    The hardware, RTOS, flash and emission sink are stubs. JSON field assembly,
    ego evaluation, sensor policy, enum strings, envelope and EGLK framing execute
    the production C. The final scenario fills the reason array to its declared
    bound; these synthetic strings are a capacity stress, not emitted rule IDs.
    """
    source = (ROOT / "firmware/mqtt_heartbeat/main/collection_main.c").read_text(encoding="utf-8")
    profile_start = source.index("#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE\n#if CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL")
    profile_end = source.index("#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE\n_Static_assert", profile_start)
    envelope_start = source.index("static cJSON *envelope(")
    envelope_end = source.index("static unsigned emit(", envelope_start)
    health_start = source.index("static void health(void)\n{")
    health_end = source.index("static void uploader_task(void *unused);", health_start)
    harness = r'''
#include "ego_state_engine.h"
#include "collection_record.h"
#include "collection_spool.h"
#include "collection_sensor_policy.h"
#include "collection_network_policy.h"
#include "platform_power.h"
#include "platform_camera.h"
#include "photo_media_store.h"
#include "photo_control_runtime.h"
#include "sim7670_cellular_call.h"
#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define CONFIG_EGOLINK_DEVICE_ID "ego-link-001"
#define CONFIG_EGOLINK_FW_VERSION "0.1.0-sensor-policy-call-022"
#define CONFIG_EGOLINK_TEST_RUN_ID "offline-health-capacity-probe"
#define CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED 1
#define CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL 1
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define portMAX_DELAY 0
#define pdMS_TO_TICKS(x) (x)
#define pdTRUE 1
#define ESP_LOGI(...) ((void)0)
''' + source[profile_start:profile_end] + r'''
unsigned scenario;
const char *scenario_names[]={"short_run","grown_counters","all_sources_dropped","max_reason_capacity"};
uint32_t boot=1;
char clock_domain[64],session_id[64],firmware_elf_sha256[65];
int clock_mux,loss_mux,spool_mutex,sensor_policy_mutex,s_ego_state_mutex,ram_fallback;
int64_t utc_offset_us;
bool spool_ready=true;
void *s_cellular_call_mutex=(void *)1;
atomic_bool sensor_policy_ready=true,s_ego_state_ready=true,s_cellular_call_ready=false;
atomic_bool media_store_ready=true,photo_control_state_ready=true;
atomic_uint acked,generated_bytes[SOURCE_COUNT],dropped[SOURCE_COUNT];
atomic_uint photo_capture_attempts,photo_capture_saved,photo_capture_failures;
atomic_uint photo_upload_acked,photo_upload_failures,photo_main_stack_hwm_bytes;
struct {uint32_t first_seq,last_seq,bytes,unknown_bytes,reasons;} ram_loss[SOURCE_COUNT];
collection_spool_t spool;
collection_sensor_policy_t sensor_policy;
ego_state_engine_ctx_t s_ego_state_engine;
ego_state_estimation_t s_health_ego_est;
ego_evidence_chain_t s_health_ego_ev;
sim7670_call_status_t s_cellular_call_status;
typedef struct {
    collection_network_state_t state;
    collection_network_route_t route;
    uint32_t generation;
} network_runtime_snapshot_t;
int64_t now_us(void) {return scenario?INT64_C(864000000000):INT64_C(10000000);}
network_runtime_snapshot_t read_network(void) {
    return (network_runtime_snapshot_t){COLLECTION_NETWORK_WIFI_READY,COLLECTION_NETWORK_ROUTE_WIFI,scenario?1234567890:1};
}
int probe_take(uintptr_t p,int t) {(void)p;(void)t;return pdTRUE;}
#define xSemaphoreTake(p,t) probe_take((uintptr_t)(p),(t))
#define xSemaphoreGive(p) ((void)(p))
struct tm *probe_gmtime_r(const time_t *t,struct tm *out) {
    struct tm *result=gmtime(t);if(result)*out=*result;return result?out:NULL;
}
#define gmtime_r probe_gmtime_r
unsigned uxQueueMessagesWaiting(int p) {(void)p;return scenario?16:0;}
unsigned esp_reset_reason(void) {return 1;}
unsigned esp_get_free_heap_size(void) {return 123456;}
void collection_spool_get_stats(const collection_spool_t *p,collection_spool_stats_t *s) {
    (void)p;
    *s=(collection_spool_stats_t){.capacity_bytes=1048576,.append_free_bytes=999000};
    if(scenario){
        s->pending_records=1000;s->pending_payload_bytes=900000;
        s->protected_pending_records=100;s->protected_retained_bytes=90000;
        s->evicted_records=1234567890;s->evicted_payload_bytes=UINT64_C(1234567890123);
        s->write_bytes_this_boot=UINT64_C(1234567890123);
        s->erased_bytes_this_boot=UINT64_C(1234567890123);
        s->io_errors_this_boot=1234567890;s->torn_tails=1234567890;s->quarantined_sectors=200;
    }
}
void platform_power_get_snapshot(platform_power_snapshot_t *s) {
    *s=(platform_power_snapshot_t){.battery_percent=75,.battery_millivolt=3900,
        .battery_voltage_valid=true,.charging=false,.battery_is_mock=false,
        .charging_is_mock=false,.battery_source="offline_stub",.charging_source="offline_stub"};
}
void add_nullable_number(cJSON *p,const char *key,bool valid,double value) {
    if(valid)cJSON_AddNumberToObject(p,key,value);else cJSON_AddNullToObject(p,key);
}
void loss_summary(void) {}
bool photo_media_stats_locked(photo_media_store_stats_t *s) {
    *s=(photo_media_store_stats_t){.committed_slots=scenario?24:0,
        .committed_payload_bytes=scenario?8000000:0,.reconciled_owned_slots=scenario?24:0};return true;
}
void photo_store_observe_result(photo_media_store_result_t result) {(void)result;}
void photo_stack_hwm_observe(atomic_uint *p) {(void)p;}
void photo_timer_snapshot(photo_control_timer_t *t) {
    memset(t,0,sizeof(*t));
    if(scenario){
        strcpy(t->config_version,"offline-timer-config-20260922");
        t->enabled=true;t->interval_seconds=3600;t->session_expires_at_unix_ms=UINT64_C(1790000000000);
        t->max_photos=1000;t->captured_photos=999;strcpy(t->state_reason,"waiting_for_trusted_utc");
    }
}
bool photo_wall_clock(uint64_t *p) {*p=0;return false;}
platform_camera_shared_i2c_state_t platform_camera_shared_i2c_state(void) {
    return PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED;
}
bool platform_camera_unverified_trial_attempt_consumed(void) {return false;}
platform_camera_status_t platform_camera_preflight(const char **p) {
    *p="camera_unverified_trial_manual_once_ready";return PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED;
}
const char *platform_camera_shared_i2c_state_name(platform_camera_shared_i2c_state_t p) {
    (void)p;return "trial_unverified";
}
const char *platform_camera_status_name(platform_camera_status_t p) {
    (void)p;return "trial_ready_unverified";
}
bool photo_camera_manual_capture_ready(platform_camera_status_t p) {(void)p;return true;}
bool platform_camera_timed_capture_allowed(void) {return false;}
esp_err_t probe_evaluate(ego_state_engine_ctx_t *ctx,int64_t ns,uint32_t window,
    ego_state_estimation_t *state,ego_evidence_chain_t *evidence) {
    esp_err_t result=ego_state_engine_evaluate(ctx,ns,window,state,evidence);
    if(result==ESP_OK&&scenario==3){
        state->reason_code_count=EGO_STATE_MAX_REASON_CODES;
        for(unsigned i=0;i<EGO_STATE_MAX_REASON_CODES;i++){
            memset(state->reason_codes[i],'a'+i,EGO_STATE_REASON_CODE_MAX_LEN-1);
            state->reason_codes[i][EGO_STATE_REASON_CODE_MAX_LEN-1]='\0';
        }
    }
    return result;
}
#define ego_state_engine_evaluate probe_evaluate
''' + source[envelope_start:envelope_end] + r'''
unsigned emit(unsigned source,int64_t mono,const char *status,const char *reason,cJSON *payload,bool metadata) {
    (void)metadata;
    if(source!=DEVICE){cJSON_Delete(payload);return 1;}
    static unsigned emitted=0;
    unsigned seq=(scenario?1234567890U:1U)+(emitted++%2U);
    cJSON *o=envelope(source,seq,mono,status,reason,payload);
    char measured[32000],bounded[COLLECTION_FRAME_CAPACITY];
    size_t full=collection_record_frame(o,measured,sizeof(measured));
    size_t admitted=collection_record_frame(o,bounded,sizeof(bounded));
    cJSON *ego=cJSON_GetObjectItemCaseSensitive(payload,"ego_state");
    bool has_ego=ego!=NULL;
    unsigned reason_count=(unsigned)cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(ego,"reason_codes"));
    unsigned source_count=(unsigned)cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(payload,"sources"));
    cJSON_DeleteItemFromObjectCaseSensitive(ego,"evidence_summary");
    size_t no_summary=collection_record_frame(o,measured,sizeof(measured));
    cJSON_DeleteItemFromObjectCaseSensitive(payload,"ego_state");
    size_t no_ego=collection_record_frame(o,measured,sizeof(measured));
    cJSON *frame_string=cJSON_CreateString(admitted?bounded:"");
    char *encoded_frame=cJSON_PrintUnformatted(frame_string);
    printf("{\"scenario\":\"%s\",\"camera\":%d,\"full\":%zu,\"admitted\":%zu,"
           "\"without_summary\":%zu,\"without_ego\":%zu,"
           "\"kind\":\"%s\",\"reason_count\":%u,\"source_count\":%u,\"frame\":%s}\n",
        scenario_names[scenario],CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE,full,admitted,no_summary,no_ego,
        has_ego?"ego":"health",reason_count,source_count,encoded_frame);
    free(encoded_frame);cJSON_Delete(frame_string);
    cJSON_Delete(o);return 1;
}
''' + source[health_start:health_end] + r'''
int main(void) {
    memset(firmware_elf_sha256,'a',64);firmware_elf_sha256[64]='\0';
    for(scenario=0;scenario<4;scenario++){
        boot=scenario?1234567890:1;
        snprintf(clock_domain,sizeof(clock_domain),"collection-esp-timer-b%"PRIu32,boot);
        snprintf(session_id,sizeof(session_id),"%s-b%"PRIu32,CONFIG_EGOLINK_DEVICE_ID,boot);
        if(ego_state_engine_init(&s_ego_state_engine,CONFIG_EGOLINK_DEVICE_ID,boot,"offline-capacity",firmware_elf_sha256)!=ESP_OK)return 1;
        if(!collection_sensor_policy_init(&sensor_policy))return 2;
        for(unsigned i=0;i<20;i++){
            int64_t ns=now_us()*1000-INT64_C(950000000)+(int64_t)i*50000000;
            if(ego_state_engine_feed_imu(&s_ego_state_engine,0,0,1000,0,0,0,ns,false)!=ESP_OK)return 3;
            collection_sensor_policy_feed_imu_sample(&sensor_policy,0,0,1000,(uint64_t)(ns/1000000));
        }
        atomic_store(&acked,scenario?1234567890:10);
        atomic_store(&photo_capture_attempts,scenario?1234567890:0);
        atomic_store(&photo_capture_saved,scenario?1234567890:0);
        atomic_store(&photo_capture_failures,scenario?1234567890:0);
        atomic_store(&photo_upload_acked,scenario?1234567890:0);
        atomic_store(&photo_upload_failures,scenario?1234567890:0);
        for(unsigned i=0;i<SOURCE_COUNT;i++){
            atomic_store(&generated_bytes[i],scenario?UINT32_MAX:1000);
            atomic_store(&dropped[i],scenario>=2?UINT32_MAX:0);
            ram_loss[i].first_seq=scenario>=2?1234567890:0;
            ram_loss[i].last_seq=scenario>=2?UINT32_MAX:0;
            ram_loss[i].bytes=scenario>=2?UINT32_MAX:0;
            ram_loss[i].unknown_bytes=scenario>=2?UINT32_MAX:0;
            ram_loss[i].reasons=scenario>=2?15:0;
        }
        health();
    }
    return 0;
}
'''
    output = run_c(harness, ["ego_state_engine", "collection_record", "collection_sensor_policy",
                            "location_policy_core", "collection_network_policy", "sim7670_cellular_call"],
                   extra_sources=[IDF / "components/json/cJSON/cJSON.c",
                                  IDF / "components/mbedtls/mbedtls/library/sha256.c",
                                  IDF / "components/mbedtls/mbedtls/library/platform_util.c"],
                   defines=[f"CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE={int(camera_profile)}"],
                   headers={"esp_err.h": "#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n#define ESP_ERR_INVALID_ARG 258\n#define ESP_ERR_INVALID_STATE 259\n#define ESP_ERR_TIMEOUT 263\n"})
    return [json.loads(line) for line in output.splitlines()]


class EgoStatePipelineTests(unittest.TestCase):
    def test_complete_production_health_frame_capacity(self):
        schema = json.loads((ROOT / "shared/contracts/ego_state_estimation_v0.schema.json").read_text(encoding="utf-8"))
        for camera in (False, True):
            rows = production_health_capacity_probe(camera)
            self.assertEqual(len(rows), 8)
            print("health_capacity=" + json.dumps([{k: v for k, v in row.items() if k != "frame"}
                                                  for row in rows], sort_keys=True))
            for offset in range(0, len(rows), 2):
                ego_row, health_row = rows[offset:offset + 2]
                self.assertEqual((ego_row["kind"], health_row["kind"]), ("ego", "health"))
                self.assertEqual(ego_row["scenario"], health_row["scenario"])
                for row in (ego_row, health_row):
                    self.assertEqual(row["admitted"], row["full"] if row["full"] < 4000 else 0)
                with self.subTest(camera=camera, scenario=ego_row["scenario"]):
                    self.assertEqual(ego_row["source_count"], 0)
                    self.assertLess(ego_row["full"], 4000)
                    self.assertGreater(ego_row["full"], ego_row["without_summary"])
                    self.assertGreater(ego_row["without_summary"], ego_row["without_ego"])
                    self.assertEqual(health_row["source_count"], 13 if camera else 12)
                    self.assertEqual(health_row["full"], health_row["without_ego"])
                    if health_row["scenario"] in ("short_run", "grown_counters"):
                        self.assertLess(health_row["full"], 4000)
                    else:
                        # Existing all-source loss detail already exceeds the
                        # legacy health frame. Do not describe this as fixed by
                        # splitting ego, or hide its real DROP_FRAME outcome.
                        self.assertGreaterEqual(health_row["full"], 4000)
                        self.assertEqual(health_row["admitted"], 0)
                    with tempfile.TemporaryDirectory() as directory:
                        hub = MessageHubStore(Path(directory) / "hub.db")
                        for row in (ego_row, health_row):
                            if row["admitted"]:
                                frame = row["frame"].encode()
                                self.assertEqual(len(frame), row["full"])
                                ack = hub.collection.ingest(frame, raw_record(frame, device="ego-link-001"), transport="wifi")
                                self.assertEqual(ack["delivery_ack"]["status"], "accepted")
                        view = hub.collection.latest_ego_state("ego-link-001")
                        self.assertIsNotNone(view)
                        Draft202012Validator(schema).validate(view["state"])
                        self.assertEqual(len(hub.collection.ego_state_timeline("ego-link-001")), 1)
                        if ego_row["scenario"] == "max_reason_capacity":
                            self.assertEqual(ego_row["reason_count"], 8)
                            self.assertEqual(len(view["state"]["reason_codes"]), 8)

    def test_c_engine_production_payload_and_frame_reach_canonical_view(self):
        source = (ROOT / "firmware/mqtt_heartbeat/main/collection_main.c").read_text(encoding="utf-8")
        start = source.index('    cJSON *es = cJSON_AddObjectToObject(ego_payload, "ego_state");')
        end = source.index('    emit(DEVICE, now_us(), "observed", NULL, ego_payload, false);', start)
        serializer = source[start:end].replace("ego_payload", "p")
        value = envelope(source="device", status="observed", missing_reason=None, payload={},
                         timestamp_monotonic_ns=2_000_000_000)
        harness = r'''
#include "ego_state_engine.h"
#include "collection_record.h"
#include <stdio.h>
#include <stdlib.h>
static void add_nullable_number(cJSON *p,const char *key,bool valid,double value) {
    if(valid)cJSON_AddNumberToObject(p,key,value);else cJSON_AddNullToObject(p,key);
}
int main(void) {
    ego_state_engine_ctx_t ctx;
    ego_state_estimation_t s_health_ego_est;
    ego_evidence_chain_t s_health_ego_ev;
    if(ego_state_engine_init(&ctx, DEVICE_ID, 1, "offline-pipeline", ELF_HASH)!=ESP_OK)return 1;
    for(unsigned sample=0;sample<20;sample++) {
        if(ego_state_engine_feed_imu(&ctx,0,0,1000,0,0,0,
            1000000000LL + (int64_t)sample*50000000LL,false)!=ESP_OK)return 2;
    }
    /* Fresh real IMU + missing auxiliary sources is intentionally partial. */
    bool ego_eval_ok=ego_state_engine_evaluate(&ctx,2000000000LL,1000,
        &s_health_ego_est,&s_health_ego_ev)==ESP_OK;
    cJSON *o=cJSON_Parse(ENVELOPE_JSON);
    cJSON *p=cJSON_GetObjectItemCaseSensitive(o,"payload");
''' + serializer + r'''
    char frame[COLLECTION_FRAME_CAPACITY];
    size_t size=collection_record_frame(o,frame,sizeof(frame));
    if(!size)return 3;
    fwrite(frame,1,size,stdout);
    cJSON_Delete(o);
    return 0;
}
'''
        harness = harness.replace("DEVICE_ID", json.dumps(DEVICE)).replace("ELF_HASH", json.dumps("a" * 64))
        harness = harness.replace("ENVELOPE_JSON", json.dumps(json.dumps(value, separators=(",", ":"))))
        frame = run_c(harness, ["ego_state_engine", "collection_record"], extra_sources=[
            IDF / "components/json/cJSON/cJSON.c",
            IDF / "components/mbedtls/mbedtls/library/sha256.c",
            IDF / "components/mbedtls/mbedtls/library/platform_util.c",
        ]).encode()
        # This checks the canonical state frame only, not the complete health
        # telemetry budget (spool/camera/counters have separate consumers).
        self.assertLess(len(frame), 4000)
        with tempfile.TemporaryDirectory() as directory:
            hub = MessageHubStore(Path(directory) / "hub.db")
            ack = hub.collection.ingest(frame, raw_record(frame), transport="wifi")
            self.assertEqual(ack["delivery_ack"]["status"], "accepted")
            view = hub.collection.latest_ego_state(DEVICE)
            self.assertIsNotNone(view)
            self.assertEqual(view["contract_version"], "egolink.ego_state_view.v0.1")
            state = view["state"]
            schema = json.loads((ROOT / "shared/contracts/ego_state_estimation_v0.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(state)
            self.assertEqual(state["timestamp_monotonic_ns"], 2_000_000_000)
            self.assertEqual(state["device_id"], DEVICE)
            self.assertIsNone(state["timestamp_utc"])
            self.assertFalse(state["is_mock"])
            self.assertLessEqual(state["confidence"], 0.5)
            self.assertIsNone(view["evidence_summary"]["is_charging"])
            self.assertIsNone(view["evidence_summary"]["battery_soc_percent"])
            self.assertIsNone(view["evidence_summary"]["network_type"])
            # Retrying the same C-produced bytes preserves their durable identity.
            retry = hub.collection.ingest(frame, raw_record(frame), transport="lte")
            self.assertEqual(retry["delivery_ack"]["payload_sha256"], ack["delivery_ack"]["payload_sha256"])
            self.assertEqual(len(hub.collection.ego_state_timeline(DEVICE)), 1)


if __name__ == "__main__":
    unittest.main()
