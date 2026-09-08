"""Runs the changed native C boundaries; no target, flash or network claims."""
import json
import unittest
from quality_tests.native_convergence import run_c, IDF, COMP

PIPELINE = r"""
#include "location_runtime_pipeline.h"
#include "location_hardware_adapter.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { printf("failed:%d\n",__LINE__); return 1; } } while(0)
static unsigned char slots[2][EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES];
static bool stored[2], fail_write;
static egolink_outbox_t outbox;
static egolink_location_outbox_adapter_t adapter;
static egolink_location_runtime_pipeline_t pipeline;
static egolink_location_runtime_scratch_t scratch;
static egolink_location_runtime_result_t result;
static egolink_outbox_snapshot_t snapshot;
static egolink_outbox_send_item_t send_item;
static egolink_outbox_storage_result_t read_slot(void*c,uint8_t slot,void*dst,size_t cap,size_t*length) {
 (void)c; if (!stored[slot]) { *length=0;return EGOLINK_OUTBOX_STORAGE_NOT_FOUND; }
 if(cap<sizeof(slots[slot]))return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
 memcpy(dst,slots[slot],sizeof(slots[slot]));*length=sizeof(slots[slot]);return EGOLINK_OUTBOX_STORAGE_OK;
}
static egolink_outbox_storage_result_t write_slot(void*c,uint8_t slot,const void*src,size_t length) {
 (void)c;if(fail_write)return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
 memcpy(slots[slot],src,length);stored[slot]=true;return EGOLINK_OUTBOX_STORAGE_OK;
}
#define T(x) (egolink_location_runtime_text_t){x,sizeof(x)-1}
static int initialize(void) {
 memset(&outbox,0,sizeof(outbox));memset(&adapter,0,sizeof(adapter));memset(stored,0,sizeof(stored));fail_write=false;
 egolink_outbox_config_t cfg={.device_id="test-device",.max_records=3,.reserved_critical_records=1,
 .max_total_payload_bytes=3*EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,.max_payload_bytes=EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
 .base_retry_ms=100,.max_retry_ms=1000,.tombstone_capacity=4};
 egolink_outbox_storage_t storage={.read_slot=read_slot,.write_slot=write_slot};
 egolink_outbox_init_report_t report;
 CHECK(egolink_location_outbox_adapter_init(&adapter,&outbox,&cfg,&storage,1,0,&report)==EGOLINK_OUTBOX_OK);
 egolink_location_runtime_owner_t owner={.device_id=T("test-device"),.boot_count=1,.session_id=T("test-run"),
 .stream_id=T("location"),.clock_domain=EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC,
 .monotonic_clock_domain_id=T("boot-1"),.local_progress_on_publish_failure=true};
 CHECK(egolink_location_runtime_pipeline_init(&pipeline,&adapter,&owner)==EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH);
 return 0;
}
static int observe(unsigned sequence,unsigned ms,const char *id,egolink_location_engine_event_type_t type) {
 egolink_location_runtime_input_t in={0};
 in.identity.device_id=T("test-device");in.identity.boot_count=1;in.identity.session_id=T("test-run");
 in.identity.stream_id=T("location");in.identity.sequence_id=sequence;
 in.identity.observation_id=(egolink_location_runtime_text_t){id,strlen(id)};
 in.identity.event_time_ms=ms;in.identity.event_time_ns=(uint64_t)ms*1000000;
 in.identity.event_time_source=EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS;
 in.identity.monotonic_clock_domain_id=T("boot-1");in.observation.type=type;in.observation.event_time_ms=ms;
 in.observation.lineage.present=true;
 in.observation.lineage.observation_id=(egolink_location_engine_text_t){id,strlen(id)};
 in.observation.lineage.source_status=EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;
 in.observation.lineage.stream_id_present=true;
 in.observation.lineage.stream_id=(egolink_location_engine_text_t){"location",8};
 in.observation.lineage.sequence_id_present=true;in.observation.lineage.sequence_id=sequence;
 in.observation.lineage.device_run_id_present=true;
 in.observation.lineage.device_run_id=(egolink_location_engine_text_t){"test-run",8};
 in.observation.lineage.boot_count_present=true;in.observation.lineage.boot_count=1;
 in.observation.lineage.timestamp_monotonic_ns_present=true;
 in.observation.lineage.timestamp_monotonic_ns=in.identity.event_time_ns;
 in.observation.lineage.monotonic_clock_domain_id_present=true;
 in.observation.lineage.monotonic_clock_domain_id=(egolink_location_engine_text_t){"boot-1",6};
 in.publish_intent=EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;
 int value=egolink_location_runtime_pipeline_process(&pipeline,&in,ms,&scratch,&result);
 fprintf(stderr,"seq=%u status=%d engine=%d emit=%d enqueue=%d outbox=%d\n",sequence,value,result.engine_status,result.enqueue_result.emit_status,result.enqueue_status,result.enqueue_result.outbox_status);
 return value;
}
int main(void) {
 CHECK(initialize()==0);
 CHECK(observe(1,100,"obs1",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX)==EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED);
 CHECK(result.local_committed && result.published && result.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX);
 CHECK(observe(2,200,"obs2",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR)==EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED);
 CHECK(observe(3,300,"obs3",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX)==EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED);
 CHECK(result.local_committed && !result.published && result.persistence_degraded && !result.retry_latched);
 CHECK(observe(4,400,"obs4",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR)==EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED);
 CHECK(result.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_ERROR);
 CHECK(observe(5,399,"late",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX)==EGOLINK_LOCATION_RUNTIME_TIME_REGRESSION);
 CHECK(observe(4,400,"obs4",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR)==EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT);
 CHECK(egolink_outbox_snapshot(&outbox,400,&snapshot)==EGOLINK_OUTBOX_OK);
 CHECK(snapshot.queued_count==2 && snapshot.metrics.full_count>=2);
 CHECK(egolink_outbox_begin_send_attempt(&outbox,400,&send_item)==EGOLINK_OUTBOX_OK);
 /* Export the real native emitter bytes for the Python/server contract check. */
 printf("%.*s\n",(int)send_item.payload_length,send_item.payload);
 egolink_location_outbox_finish_result_t finished;
 CHECK(egolink_location_outbox_finish_attempt(&adapter,send_item.record.last_attempt_token,true,NULL,
 (const uint8_t*)"{\"ok\":true}",11,401,&finished)!=EGOLINK_LOCATION_OUTBOX_FINISH_ACK_DELETED);
 CHECK(egolink_outbox_snapshot(&outbox,402,&snapshot)==EGOLINK_OUTBOX_OK && snapshot.queued_count==2);
 CHECK(initialize()==0);fail_write=true;
 CHECK(observe(1,100,"error1",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR)==EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED);
 CHECK(observe(2,200,"error2",EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX)==EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED);
 CHECK(result.local_committed && !result.published && result.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX);
 /* Quality absent/zero is a receiver fix candidate, never a fabricated no-fix. */
 egolink_location_hardware_identity_t identity={.device_id=T("test-device"),.boot_count=1,.session_id=T("test-run"),
 .stream_id=T("location"),.sequence_id=3,.observation_id=T("quality3"),.source_event_time_ms=300,
 .source_event_time_ns=300000000,.source_event_time_source=EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS,
 .monotonic_clock_domain_id=T("boot-1"),.publish_intent=EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT};
 sim7670_gnss_report_t gnss={0};gnss.driver_enabled=true;gnss.uart_ready=true;gnss.at_ok=true;
 gnss.fix=true;gnss.lat_valid=true;gnss.lon_valid=true;gnss.lat=22.5;gnss.lon=114;
 gnss.location_result_valid=true;strcpy(gnss.gnss_state,"fix");strcpy(gnss.source_status,"observed");
 gnss.cgnssinfo_query=(sim7670_gnss_query_evidence_t){.attempted=true,.response_observed=true,.parse_valid=true,.fix_observed=true};
 egolink_location_hardware_mapped_input_t mapped;
 CHECK(egolink_location_hardware_map_gnss(&identity,&gnss,&mapped)==EGOLINK_LOCATION_HARDWARE_MAP_OK);
 CHECK(mapped.input.observation.type==EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX && !mapped.input.observation.hdop_present);
 CHECK(egolink_location_runtime_pipeline_process(&pipeline,&mapped.input,300,&scratch,&result)==EGOLINK_LOCATION_RUNTIME_LOCAL_COMMITTED_PERSISTENCE_FAILED);
 CHECK(result.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED);
 gnss.hdop_valid=true;gnss.hdop=0;
 CHECK(egolink_location_hardware_map_gnss(&identity,&gnss,&mapped)==EGOLINK_LOCATION_HARDWARE_MAP_OK);
 CHECK(!mapped.input.observation.hdop_present);
 return 0;
}
"""

class RuntimeConvergenceNativeTests(unittest.TestCase):
 def test_real_mapper_reducers_emitter_outbox_capacity_storage_failure_and_late_input(self):
  output=run_c(PIPELINE, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter'],
   extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'])
  envelope=json.loads(output.strip())
  from server.location_state_runtime import LocationStateRuntimeMirror
  mirror=LocationStateRuntimeMirror()
  # Ingest the actual native bytes through the existing stdlib contract validator.
  mirror.ingest(envelope)
  self.assertEqual(envelope['event_time_ms'],100)

 def test_q_single_owner_start_race_stop_during_execution_and_settle(self):
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
   extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS)
  # Exercise fault progress through Q's copied configuration and O/K, not just
  # the reducer API: the live owner's opt-in must survive every composition seam.
  run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
   extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=['OWNER_STORAGE_FAULT=1'])
  import hashlib,tempfile
  from pathlib import Path
  from server.location_state_store import LocationStateStore
  from server.location_delivery_ack import build_location_state_delivery_ack
  from server.guardian_device_authorization import GuardianDeviceAuthorizer,CONTRACT_VERSION,token_sha256
  raw=output.splitlines()[-1].encode()
  event=json.loads(raw)
  self.assertEqual(event['event_time_source'],'timestamp_utc_ns')
  auth=GuardianDeviceAuthorizer({'contract_version':CONTRACT_VERSION,'bindings':[{
   'guardian_id':'native-guardian','token_sha256':token_sha256('native-test-guardian-token'),
   'device_ids':[event['device_id']]}]})
  decision=auth.authorize('Bearer native-test-guardian-token',event['device_id'])
  self.assertTrue(decision.authorized)
  self.assertFalse(auth.authorize('Bearer native-test-guardian-token','another-device').authorized)
  with tempfile.TemporaryDirectory() as directory:
   store=LocationStateStore(Path(directory)/'native.db')
   receipt_time=event['event_time_ms']+4000
   accepted=store.ingest(event,server_receive_time_ms=receipt_time)
   ack=build_location_state_delivery_ack(raw,event,accepted,ack_time_ms=receipt_time)
   self.assertEqual(ack['payload_sha256'],hashlib.sha256(raw).hexdigest())
   restored=LocationStateStore(store.db_path)
   current=restored.authenticated_current(event['device_id'],utc_now_ns=(receipt_time+1000)*1000000,
     location_access_authorized=decision.authorized,authorization_subject=decision.guardian_id)
   self.assertEqual(current['state_age_ms'],5000) # source time, not receive time
   self.assertIsNone(current['position']) # observed no-fix cannot invent coordinates
   self.assertEqual(current['authorization_subject'],'native-guardian')

 def test_q_startup_power_off_failure_stops_with_bounded_cleanup_and_no_restart(self):
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  for mode, attempts, quiesced in ((1,2,True),(2,4,False)):
   with self.subTest(fault='initial_only' if mode==1 else 'persistent'):
    output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
     extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=[f'OWNER_STARTUP_OFF_FAULT={mode}'])
    evidence=json.loads(output.splitlines()[-1])
    self.assertEqual(evidence,{'startup_status':23,'power_off_attempts':attempts,
     'stop_cleanup_attempts':attempts-1,'quiesced':quiesced,'sensor_calls':0,
     'http_calls':0,'owner_tasks':1,'concurrent_io_calls':0})

 def test_q_distinct_process_boots_same_sequence_ingest_without_observation_collision(self):
  import tempfile
  from pathlib import Path
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  from server.location_state_store import LocationStateStore
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  events=[]
  for boot in (41,42):
   # run_c starts a fresh native executable process, including Q's static owner.
   output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
    extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=[f'OWNER_BOOT_COUNT={boot}'])
   event=json.loads(output.splitlines()[-1])
   self.assertEqual(event['boot_count'],boot)
   self.assertEqual(event['sequence_id'],1)
   self.assertEqual(event['event_time_source'],'timestamp_utc_ns')
   events.append(event)
  self.assertNotEqual(events[0]['observation_id'],events[1]['observation_id'])
  with tempfile.TemporaryDirectory() as directory:
   store=LocationStateStore(Path(directory)/'two-boots.db')
   for event in events:
    result=store.ingest(event,server_receive_time_ms=event['event_time_ms']+100)
    self.assertEqual(result['status'],'accepted')
   self.assertEqual(store.timeline_length('test-device'),2)
   self.assertEqual(LocationStateStore(store.db_path).timeline_length('test-device'),2)

 def test_q_real_p0_post_counts_settled_ack_and_transport_failure(self):
  import tempfile
  from pathlib import Path
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  from server.location_state_store import LocationStateStore
  from server.location_delivery_ack import build_location_state_delivery_ack
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  for mode in (1,2):
   with self.subTest(post='matching_ack' if mode==1 else 'transport_failure'):
    output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
     extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=[f'OWNER_DELIVERY_TEST={mode}'])
    lines=output.splitlines()
    raw=lines[-3].encode()
    event=json.loads(raw)
    response=json.loads(lines[-2])
    evidence=json.loads(lines[-1])
    self.assertEqual(evidence['delivery_attempts'],1)
    self.assertEqual(evidence['http_calls'],1)
    self.assertGreaterEqual(evidence['last_delivery_time_ms'],evidence['post_completion_ms'])
    self.assertGreater(evidence['last_delivery_time_ms'],0)
    self.assertEqual(evidence['last_delivery_status'],2 if mode==1 else 4)
    self.assertEqual(evidence['matched_ack_deletes'],1 if mode==1 else 0)
    self.assertEqual(evidence['queued'],0 if mode==1 else 1)
    if mode==1:
     # The native callback is a transport fault fixture, not a network server.
     # Verify its successful ACK against the production builder over these
     # exact transmitted bytes after actual durable server-store ingestion.
     with tempfile.TemporaryDirectory() as directory:
      store=LocationStateStore(Path(directory)/'native-post.db')
      accepted=store.ingest(event,server_receive_time_ms=event['event_time_ms']+100)
      self.assertEqual(accepted['status'],'accepted')
      ack=build_location_state_delivery_ack(raw,event,accepted,ack_time_ms=evidence['post_completion_ms'])
      self.assertEqual(response,{'ok':True,'delivery_scope':'server_durable_ingest_only','delivery_ack':ack})
    else:
     self.assertIsNone(response)

 def test_q_stop_cancels_driver_dwell_through_adapter_and_finishes_power_off(self):
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
   extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=['OWNER_DWELL_STOP=1'])
  self.assertEqual(json.loads(output.splitlines()[-1]),{'dwell_cancel_observed':True,
   'quiesced':True,'http_calls':0,'local_sequence':0,'owner_tasks':1})

 def test_existing_exact_parser_adapter_and_split_delivery_harnesses_on_native_gcc(self):
  from quality_tests.test_sim7670_p0_delivery_adapter import PARSER_HARNESS, ADAPTER_HARNESS
  from quality_tests.test_p0_delivery_runtime import HARNESS
  parser=COMP/'sim7670_gnss/sim7670_http_exact_parser.c'
  run_c(PARSER_HARNESS, extra_sources=[parser], defines=['mainCRTStartup=main'])
  run_c(ADAPTER_HARNESS, ['sim7670_p0_delivery_adapter'], extra_sources=[parser],
        defines=['mainCRTStartup=main','CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED=1'])
  run_c(HARNESS, ['p0_delivery_runtime'], defines=['mainCRTStartup=main'])

 def test_q_terminal_error_recovers_same_owner_before_capture_or_stops_after_wait_deadline(self):
  from quality_tests.native_owner_shim import HEADERS, DRIVER
  harness=PIPELINE.replace('int main(void)', 'static int pipeline_test(void)')+DRIVER
  for mode in (1,2):
   with self.subTest(fault='initial_terminal_error' if mode==1 else 'persistent_terminal_error'):
    output=run_c(harness, ['location_runtime_pipeline','location_engine_core','location_policy_core','location_state_emitter','location_outbox_adapter','persistent_priority_outbox','location_hardware_adapter','sim7670_location_modem_owner','sim7670_location_modem_adapter','location_modem_executor','location_modem_arbiter','device_location_runtime','p0_delivery_runtime','p0_outbox_dispatcher','sos_outbox_adapter'],
     extra_sources=[IDF/'components/json/cJSON/cJSON.c',IDF/'components/mbedtls/mbedtls/library/sha256.c',IDF/'components/mbedtls/mbedtls/library/platform_util.c',IDF/'components/mbedtls/mbedtls/library/platform.c'], headers=HEADERS,defines=[f'OWNER_RECOVERY_WAIT={mode}'])
    lines=output.splitlines()
    self.assertEqual(json.loads(lines[-1]),{'recovered_active':mode==1,'quiesced':mode==1,
     'sensor_calls':1 if mode==1 else 0,'owner_tasks':1,'concurrent_io_calls':0})
    if mode==1:
     event=json.loads(lines[-2])
     from server.location_state_runtime import LocationStateRuntimeMirror
     LocationStateRuntimeMirror().ingest(event)
     self.assertEqual(event['event_time_source'],'timestamp_utc_ns')
     self.assertGreaterEqual(event['event_time_ms'],1767225600000)

 def test_concrete_https_transfer_exact_bytes_tls_failure_truncation_cancel_and_budget(self):
  from quality_tests.native_https_shim import HEADERS, HARNESS
  run_c(HARNESS, ['esp_p0_https'],extra_sources=[COMP/'sim7670_gnss/sim7670_http_exact_parser.c'],headers=HEADERS)

if __name__=='__main__': unittest.main()
