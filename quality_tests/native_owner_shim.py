"""OS threads/mutexes for executing Q's real FreeRTOS-facing C on the host."""
FREE_RTOS = r"""
#pragma once
#include <windows.h>
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t StackType_t;
typedef unsigned UBaseType_t;
typedef int BaseType_t;
typedef uint32_t TickType_t;
typedef CRITICAL_SECTION portMUX_TYPE;
#define portMUX_INITIALIZE(x) InitializeCriticalSection(x)
#define taskENTER_CRITICAL(x) EnterCriticalSection(x)
#define taskEXIT_CRITICAL(x) LeaveCriticalSection(x)
#define pdMS_TO_TICKS(x) ((TickType_t)(x))
#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY INFINITE
#define configMAX_PRIORITIES 25
#define portNUM_PROCESSORS 2
#define tskNO_AFFINITY -1
"""
TASK = r"""
#pragma once
#include "FreeRTOS.h"
typedef struct {HANDLE thread,notify;void (*fn)(void*);void*arg;} StaticTask_t;
typedef StaticTask_t *TaskHandle_t;
extern __thread TaskHandle_t native_task;
extern volatile LONG native_created_tasks;
static inline DWORD WINAPI native_thread(void *arg){native_task=arg;native_task->fn(native_task->arg);return 0;}
static inline TaskHandle_t xTaskCreateStaticPinnedToCore(void(*fn)(void*),const char*name,uint32_t count,void*arg,UBaseType_t priority,StackType_t*stack,StaticTask_t*task,BaseType_t core){
 (void)name;(void)count;(void)priority;(void)stack;(void)core;
 task->fn=fn;task->arg=arg;task->notify=CreateSemaphore(NULL,0,65535,NULL);
 task->thread=CreateThread(NULL,0,native_thread,task,0,NULL);
 if(task->thread)InterlockedIncrement(&native_created_tasks);
 return task->thread?task:NULL;
}
static inline TaskHandle_t xTaskGetCurrentTaskHandle(void){return native_task;}
static inline BaseType_t xTaskGetCoreID(void){return 0;}
static inline BaseType_t xPortGetCoreID(void){return 0;}
static inline void xTaskNotifyGive(TaskHandle_t task){ReleaseSemaphore(task->notify,1,NULL);}
static inline uint32_t ulTaskNotifyTake(BaseType_t clear,TickType_t timeout){(void)clear;return WaitForSingleObject(native_task->notify,timeout)==WAIT_OBJECT_0;}
static inline void vTaskDelay(TickType_t ticks){Sleep(ticks);}
"""
SEM = r"""
#pragma once
#include "FreeRTOS.h"
typedef struct {HANDLE handle;bool mutex;} StaticSemaphore_t;
typedef StaticSemaphore_t* SemaphoreHandle_t;
extern HANDLE native_startup_release;
static inline SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t*s){s->mutex=true;s->handle=CreateMutex(NULL,FALSE,NULL);return s;}
static inline SemaphoreHandle_t xSemaphoreCreateBinaryStatic(StaticSemaphore_t*s){s->mutex=false;s->handle=CreateSemaphore(NULL,0,1,NULL);return s;}
static inline BaseType_t xSemaphoreTake(SemaphoreHandle_t s,TickType_t timeout){return WaitForSingleObject(s->handle,timeout)==WAIT_OBJECT_0;}
static inline BaseType_t xSemaphoreGive(SemaphoreHandle_t s){
 BaseType_t released=s->mutex?ReleaseMutex(s->handle):ReleaseSemaphore(s->handle,1,NULL);
 /* Test scheduling barrier after publishing Q's startup result. */
 if(!s->mutex && native_startup_release)WaitForSingleObject(native_startup_release,2000);
 return released;
}
"""
HEADERS={"freertos/FreeRTOS.h":FREE_RTOS,"freertos/task.h":TASK,"freertos/semphr.h":SEM,
"esp_timer.h":"#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
"sdkconfig.h":"#define CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED 1\n"}
DRIVER = r"""
#include "sim7670_location_modem_owner.h"
#include "sos_outbox_adapter.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <inttypes.h>
#if OWNER_DELIVERY_TEST
#include "mbedtls/sha256.h"
#endif
#ifndef OWNER_BOOT_COUNT
#define OWNER_BOOT_COUNT 1
#endif
__thread TaskHandle_t native_task;
volatile LONG native_created_tasks;
HANDLE native_startup_release;
static TaskHandle_t modem_task;
static atomic_uint init_calls,foreign_calls;
static atomic_uint io_active,concurrent_io_calls,power_off_calls,sensor_calls,lte_calls,http_calls;
static HANDLE acquisition_entered,acquisition_release;
static HANDLE power_off_entered,power_off_release;
#if OWNER_DWELL_STOP
static atomic_bool dwell_cancel_observed,dwell_config_observed;
#endif
#if OWNER_DELIVERY_TEST
static HANDLE post_entered,post_release;
static uint64_t post_completion_ms;
static char posted_payload[EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES+1];
static char returned_response[2048];
#endif
int64_t esp_timer_get_time(void){return (int64_t)GetTickCount64()*1000;}
esp_err_t sim7670_at_backend_init_exclusive_current_task(void){
 if(modem_task && modem_task!=native_task)return ESP_ERR_INVALID_STATE;
 modem_task=native_task;atomic_fetch_add(&init_calls,1);return ESP_OK;
}
bool sim7670_at_backend_current_task_is_exclusive_owner(void){return native_task && native_task==modem_task;}
bool sim7670_at_backend_is_initialized(void){return modem_task!=NULL;}
void sim7670_gnss_report_init(sim7670_gnss_report_t*r){memset(r,0,sizeof(*r));}
void sim7670_lte_report_init(sim7670_lte_report_t*r){memset(r,0,sizeof(*r));}
void sim7670_location_bounded_result_init(sim7670_location_bounded_result_t*r){memset(r,0,sizeof(*r));}
static sim7670_location_bounded_outcome_t ready(sim7670_location_bounded_result_t*r){
 if(!sim7670_at_backend_current_task_is_exclusive_owner())atomic_fetch_add(&foreign_calls,1);
 memset(r,0,sizeof(*r));r->outcome=SIM7670_LOCATION_BOUNDED_REPORT_READY;r->io_started=true;
 r->commands_attempted=r->commands_tx_complete=r->commands_completed=1;return r->outcome;
}
static void begin_io(void){
 if(!sim7670_at_backend_current_task_is_exclusive_owner())atomic_fetch_add(&foreign_calls,1);
 if(atomic_fetch_add(&io_active,1)!=0)atomic_fetch_add(&concurrent_io_calls,1);
}
static void end_io(void){atomic_fetch_sub(&io_active,1);}
sim7670_location_bounded_outcome_t sim7670_gnss_power_off_bounded(const sim7670_location_bounded_request_t*q,sim7670_location_bounded_result_t*r){
 (void)q;begin_io();unsigned call=atomic_fetch_add(&power_off_calls,1)+1;
#if OWNER_DWELL_STOP
 if(q->power_on_settle_ms!=0 || q->cancel_requested(q->cancel_context,q->operation_token))abort();
#endif
 if(call>1 && power_off_entered){SetEvent(power_off_entered);WaitForSingleObject(power_off_release,2000);}
 Sleep(5);ready(r);
#if OWNER_STARTUP_OFF_FAULT
 if(call==1 || OWNER_STARTUP_OFF_FAULT==2){
  r->outcome=SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
  r->reason=SIM7670_LOCATION_BOUNDED_REASON_AT_RESPONSE_TIMEOUT;
  r->partial_or_unknown=true;r->commands_completed=0;
 }
#elif OWNER_RECOVERY_WAIT
 if(call==1 || OWNER_RECOVERY_WAIT==2){
  r->outcome=SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
  r->reason=SIM7670_LOCATION_BOUNDED_REASON_AT_TERMINAL_ERROR;
  r->partial_or_unknown=true;r->commands_completed=0;
 }
#endif
 end_io();return r->outcome;
}
sim7670_location_bounded_outcome_t sim7670_gnss_request_location_bounded(const sim7670_location_bounded_request_t*q,sim7670_gnss_report_t*r,sim7670_location_bounded_result_t*result){
 (void)q;begin_io();atomic_fetch_add(&sensor_calls,1);
#if OWNER_DWELL_STOP
 atomic_store(&dwell_config_observed,q->power_on_settle_ms==300);
 SetEvent(acquisition_entered);
 uint64_t wait_deadline=GetTickCount64()+2000;
 bool cancelled=false;
 do{cancelled=q->cancel_requested(q->cancel_context,q->operation_token);if(cancelled)break;Sleep(2);}while(GetTickCount64()<wait_deadline);
 atomic_store(&dwell_cancel_observed,cancelled);
 memset(r,0,sizeof(*r));ready(result);
 result->outcome=cancelled?SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED:SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
 result->reason=cancelled?SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BETWEEN_AT:SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED;
 result->cancelled_between_commands=cancelled;result->partial_or_unknown=true;
 end_io();return result->outcome;
#else
 SetEvent(acquisition_entered);WaitForSingleObject(acquisition_release,2000);
 memset(r,0,sizeof(*r));r->driver_enabled=true;r->uart_ready=true;r->at_ok=true;
 r->location_result_valid=true;r->no_fix_observed=true;strcpy(r->gnss_state,"no_fix");strcpy(r->source_status,"observed");
 r->cgnssinfo_query=(sim7670_gnss_query_evidence_t){.attempted=true,.response_observed=true,.parse_valid=true,.no_fix_observed=true};
 r->cgpsinfo_query=r->cgnssinfo_query;ready(result);end_io();return result->outcome;
#endif
}
sim7670_location_bounded_outcome_t sim7670_lte_query_status_bounded(const sim7670_location_bounded_request_t*q,sim7670_lte_report_t*r,sim7670_location_bounded_result_t*result){
 (void)q;begin_io();atomic_fetch_add(&sensor_calls,1);atomic_fetch_add(&lte_calls,1);memset(r,0,sizeof(*r));memset(result,0,sizeof(*result));result->outcome=SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;end_io();return result->outcome;
}
static egolink_sim7670_location_modem_owner_t modem;
static egolink_p0_delivery_runtime_t delivery;
static egolink_sos_outbox_adapter_t sos_adapter;
static egolink_p0_outbox_dispatcher_t dispatcher;
static atomic_uint started;
static DWORD WINAPI start_race(void*arg){(void)arg;DWORD status=egolink_sim7670_location_modem_owner_start(&modem);if(status==EGOLINK_SIM7670_MODEM_OWNER_STARTED)atomic_fetch_add(&started,1);return status;}
static egolink_p0_delivery_post_outcome_t post(void*c,const egolink_p0_delivery_post_request_t*r,egolink_p0_delivery_post_result_t*v){
 (void)c;(void)r;begin_io();atomic_fetch_add(&http_calls,1);memset(v,0,sizeof(*v));
#if OWNER_DELIVERY_TEST
 if(r->body_length>=sizeof(posted_payload)){end_io();return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;}
 memcpy(posted_payload,r->body,r->body_length);posted_payload[r->body_length]='\0';
 SetEvent(post_entered);WaitForSingleObject(post_release,2000);
 post_completion_ms=GetTickCount64();v->completion_time_ms=post_completion_ms;
#if OWNER_DELIVERY_TEST == 1
 /* Fault fixture binds the exact transmitted bytes; Python checks these
  * fields against the existing server ACK builder after real SQLite ingest. */
 unsigned char digest[32];char hex[65];
 if(mbedtls_sha256(r->body,r->body_length,digest,0)!=0){end_io();return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;}
 for(unsigned i=0;i<32;++i)snprintf(hex+i*2,3,"%02x",digest[i]);
 int length=snprintf(returned_response,sizeof(returned_response),
  "{\"ok\":true,\"delivery_scope\":\"server_durable_ingest_only\",\"delivery_ack\":{"
  "\"contract_version\":\"egolink.persistent_priority_outbox.ack.v0.1\","
  "\"ack_id\":\"ack-%s\",\"device_id\":\"test-device\",\"event_id\":\"loc-%s\","
  "\"payload_sha256\":\"%s\",\"status\":\"accepted\",\"ack_time_ms\":%" PRIu64 "}}",
  hex,hex,hex,post_completion_ms);
 if(length<0 || (size_t)length>=sizeof(returned_response) || (size_t)length>r->response_capacity){end_io();return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;}
 memcpy(r->response,returned_response,(size_t)length);v->response_length=(size_t)length;
 v->http_status_code=200;end_io();return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
#endif
#else
 v->completion_time_ms=GetTickCount64();
#endif
 v->transport_error=EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE;end_io();return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
}
int main(void){
 CHECK(pipeline_test()==0);CHECK(initialize()==0);
 acquisition_entered=CreateEvent(NULL,TRUE,FALSE,NULL);acquisition_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 CHECK(egolink_sos_outbox_adapter_bind(&sos_adapter,&outbox,"test-device")==EGOLINK_OUTBOX_OK);
 egolink_p0_outbox_dispatcher_config_t dc;egolink_p0_outbox_dispatcher_default_config(&dc);dc.enabled=true;
 CHECK(egolink_p0_outbox_dispatcher_init(&dispatcher,&dc,&outbox,&adapter,&sos_adapter)==EGOLINK_P0_OUTBOX_OK);
 egolink_p0_delivery_runtime_config_t pc;egolink_p0_delivery_runtime_default_config(&pc);pc.enabled=true;pc.http_post=post;
 CHECK(egolink_p0_delivery_runtime_init(&delivery,&pc,&dispatcher)==EGOLINK_P0_DELIVERY_OK);
 egolink_sim7670_location_modem_owner_config_t cfg;egolink_sim7670_location_modem_owner_default_config(&cfg);
 cfg.utc_epoch_at_boot_ms=1767225600000ULL;cfg.enabled=true;cfg.owner_core_id=0;cfg.first_sequence_id=1;cfg.max_commands_per_wake=1;cfg.max_sensor_commands=1;
#if OWNER_RECOVERY_WAIT
 cfg.recovery_retry_backoff_ms=20;cfg.idle_poll_ms=20;
#endif
#if OWNER_DELIVERY_TEST
 cfg.idle_poll_ms=20;
 post_entered=CreateEvent(NULL,TRUE,FALSE,NULL);post_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 CHECK(post_entered && post_release);
#endif
#if OWNER_DWELL_STOP
 cfg.gnss_power_on_settle_ms=300;
#endif
 cfg.pipeline_owner=(egolink_location_runtime_owner_t){.device_id=T("test-device"),.boot_count=OWNER_BOOT_COUNT,.session_id=T("test-run"),.stream_id=T("location"),.clock_domain=EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC,.monotonic_clock_domain_id=T("boot-1"),.local_progress_on_publish_failure=true};
 CHECK(egolink_sim7670_location_modem_owner_init(&modem,&cfg,&outbox,&adapter,&delivery)==EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS);
#if OWNER_RECOVERY_WAIT
 native_startup_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 power_off_entered=CreateEvent(NULL,TRUE,FALSE,NULL);power_off_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 CHECK(native_startup_release && power_off_entered && power_off_release);
 CHECK(egolink_sim7670_location_modem_owner_start(&modem)==EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED);
 TaskHandle_t original_owner=modem_task;
 egolink_sim7670_location_modem_owner_snapshot_t state;
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.last_status==23 && state.last_power_off_outcome==3 && state.last_power_off_reason==11);
 CHECK(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED && state.power_off_attempts==1);
 CHECK(!state.gnss_off_confirmed && !state.quiesced && !state.stop_requested);
 CHECK(atomic_load(&sensor_calls)==0 && atomic_load(&http_calls)==0);
 /* Let the existing Q recovery loop retry, without starting another owner. */
 SetEvent(native_startup_release);
 CHECK(WaitForSingleObject(power_off_entered,2000)==WAIT_OBJECT_0);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED && !state.gnss_off_confirmed);
 CHECK(state.sensor_commands==0 && state.delivery_attempts==0 && atomic_load(&sensor_calls)==0 && atomic_load(&http_calls)==0);
 SetEvent(power_off_release);
 const uint64_t wait_deadline=GetTickCount64()+150;
 bool became_active=false;
 do {
  CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
  CHECK(atomic_load(&sensor_calls)==0 && atomic_load(&http_calls)==0 && !state.execution_active);
  if(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_ACTIVE){
   CHECK(state.gnss_off_confirmed && state.exclusive_owner_confirmed && !state.cleanup_recovery_required);
   CHECK(!state.fatal_recovery_required && !state.stop_requested && !state.quiesced);
   became_active=true;break;
  }
  CHECK(!state.quiesced && state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED);
  Sleep(5);
 } while(GetTickCount64()<wait_deadline);
#if OWNER_RECOVERY_WAIT == 1
 CHECK(became_active && state.power_off_attempts==2 && state.power_off_confirmed==1 && state.recovery_attempts==1);
 egolink_location_modem_enqueue_result_t queued;
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
 CHECK(WaitForSingleObject(acquisition_entered,2000)==WAIT_OBJECT_0);
 CHECK(atomic_load(&sensor_calls)==1 && atomic_load(&http_calls)==0);
 SetEvent(acquisition_release);
 for(unsigned i=0;i<200;++i){
  egolink_sim7670_location_modem_owner_current_status(&modem,&state);
  if(state.settled_commands==1)break;
  Sleep(10);
 }
 CHECK(state.settled_commands==1 && state.local_sequence==1 && state.persistence_failures==0);
 CHECK(state.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX && state.sensor_commands==1);
 CHECK(state.source_event_time_ms>=cfg.utc_epoch_at_boot_ms && state.source_event_time_ms-cfg.utc_epoch_at_boot_ms<=GetTickCount64());
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 for(unsigned i=0;i<200;++i){egolink_sim7670_location_modem_owner_current_status(&modem,&state);if(state.quiesced)break;Sleep(10);}
 CHECK(state.quiesced && state.gnss_off_confirmed && !state.execution_active);
 CHECK(egolink_outbox_begin_send_attempt(&outbox,GetTickCount64(),&send_item)==EGOLINK_OUTBOX_OK);
 printf("%.*s\n",(int)send_item.payload_length,send_item.payload);
#else
 CHECK(!became_active && GetTickCount64()>=wait_deadline);
 CHECK(state.power_off_confirmed==0 && state.power_off_attempts>=2 && !state.quiesced);
 unsigned attempts_at_stop=atomic_load(&power_off_calls);
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 Sleep(200);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 /* At most one recovery call was already awake/in flight, then three stop attempts. */
 CHECK(state.power_off_attempts>=attempts_at_stop+3 && state.power_off_attempts<=attempts_at_stop+4);
 CHECK(!state.quiesced && !state.gnss_off_confirmed && state.cleanup_recovery_required);
 CHECK(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED && state.last_status==23);
 CHECK(state.last_power_off_outcome==3 && state.last_power_off_reason==11);
 CHECK(state.sensor_commands==0 && state.delivery_attempts==0 && state.settled_commands==0);
 CHECK(atomic_load(&sensor_calls)==0 && atomic_load(&http_calls)==0);
#endif
 unsigned final_off_calls=atomic_load(&power_off_calls);
 CHECK(start_race(NULL)==EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED);
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 Sleep(60);
 CHECK(atomic_load(&power_off_calls)==final_off_calls);
 CHECK(modem_task==original_owner && native_created_tasks==1 && atomic_load(&init_calls)==1);
 CHECK(atomic_load(&io_active)==0 && atomic_load(&concurrent_io_calls)==0 && atomic_load(&foreign_calls)==0);
 printf("{\"recovered_active\":%s,\"quiesced\":%s,\"sensor_calls\":%u,\"owner_tasks\":1,\"concurrent_io_calls\":0}\n",became_active?"true":"false",state.quiesced?"true":"false",atomic_load(&sensor_calls));
 return 0;
#elif OWNER_DWELL_STOP
 CHECK(start_race(NULL)==EGOLINK_SIM7670_MODEM_OWNER_STARTED);
 egolink_location_modem_enqueue_result_t queued;
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
 CHECK(WaitForSingleObject(acquisition_entered,2000)==WAIT_OBJECT_0);
 egolink_sim7670_location_modem_owner_snapshot_t state;
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.execution_active && !state.stop_requested && state.local_sequence==0);
 CHECK(atomic_load(&dwell_config_observed) && !atomic_load(&dwell_cancel_observed));
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 for(unsigned i=0;i<200;++i){egolink_sim7670_location_modem_owner_current_status(&modem,&state);if(state.quiesced)break;Sleep(10);}
 CHECK(atomic_load(&dwell_cancel_observed));
 CHECK(state.quiesced && state.gnss_off_confirmed && state.stop_requested && !state.execution_active);
 CHECK(state.settled_commands==1 && state.local_sequence==0 && state.delivery_attempts==0);
 CHECK(egolink_outbox_snapshot(&outbox,GetTickCount64(),&snapshot)==EGOLINK_OUTBOX_OK && snapshot.queued_count==0);
 /* Startup off plus the never-cancelled acquisition compensation; stop
  * sees confirmed off and must not issue another modem command. */
 CHECK(atomic_load(&http_calls)==0 && atomic_load(&sensor_calls)==1 && atomic_load(&power_off_calls)==2);
 CHECK(start_race(NULL)==EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED);
 Sleep(60);
 CHECK(native_created_tasks==1 && atomic_load(&init_calls)==1 && atomic_load(&power_off_calls)==2);
 CHECK(atomic_load(&io_active)==0 && atomic_load(&concurrent_io_calls)==0 && atomic_load(&foreign_calls)==0);
 puts("{\"dwell_cancel_observed\":true,\"quiesced\":true,\"http_calls\":0,\"local_sequence\":0,\"owner_tasks\":1}");
 return 0;
#elif OWNER_DELIVERY_TEST
 CHECK(start_race(NULL)==EGOLINK_SIM7670_MODEM_OWNER_STARTED);
 egolink_sim7670_location_modem_owner_snapshot_t state;
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.delivery_attempts==0 && state.last_delivery_time_ms==0 && state.last_delivery_status==0);
 CHECK(atomic_load(&http_calls)==0);
 egolink_location_modem_enqueue_result_t queued;
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
 CHECK(WaitForSingleObject(acquisition_entered,2000)==WAIT_OBJECT_0);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.delivery_attempts==0 && state.last_delivery_time_ms==0 && atomic_load(&http_calls)==0);
 SetEvent(acquisition_release);
 CHECK(WaitForSingleObject(post_entered,2000)==WAIT_OBJECT_0);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 /* GNSS capture (including power-off), then policy-requested LTE status. */
 CHECK(state.execution_active && state.settled_commands==2 && state.local_sequence==1);
 CHECK(atomic_load(&power_off_calls)==2);
 CHECK(state.delivery_attempts==0 && state.last_delivery_time_ms==0 && state.last_delivery_status==0);
 CHECK(atomic_load(&http_calls)==1);
 /* Stop during the actual P0 callback: its result must still settle once. */
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 SetEvent(post_release);
 for(unsigned i=0;i<200;++i){egolink_sim7670_location_modem_owner_current_status(&modem,&state);if(state.quiesced)break;Sleep(10);}
 CHECK(state.quiesced && state.gnss_off_confirmed && !state.execution_active);
 CHECK(state.settled_commands==3 && state.delivery_attempts==1 && state.sensor_commands==1);
 CHECK(state.last_delivery_time_ms>=post_completion_ms && state.last_delivery_time_ms<=GetTickCount64());
 egolink_p0_delivery_runtime_snapshot_t delivered;
 CHECK(egolink_p0_delivery_runtime_current_status(&delivery,&delivered)==EGOLINK_P0_DELIVERY_OK);
 CHECK(delivered.post_calls==1 && atomic_load(&http_calls)==1);
 CHECK(egolink_outbox_snapshot(&outbox,GetTickCount64(),&snapshot)==EGOLINK_OUTBOX_OK);
#if OWNER_DELIVERY_TEST == 1
 CHECK(state.last_delivery_status==EGOLINK_P0_DELIVERY_ACK_DELETED);
 CHECK(state.matched_ack_deletes==1 && delivered.ack_deletes==1 && snapshot.queued_count==0);
#else
 CHECK(state.last_delivery_status==EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED);
 CHECK(state.matched_ack_deletes==0 && delivered.ack_deletes==0 && snapshot.queued_count==1);
#endif
 CHECK(native_created_tasks==1 && atomic_load(&init_calls)==1);
 CHECK(atomic_load(&sensor_calls)==2 && atomic_load(&lte_calls)==1);
 CHECK(atomic_load(&io_active)==0 && atomic_load(&concurrent_io_calls)==0 && atomic_load(&foreign_calls)==0);
 printf("%s\n",posted_payload);
 printf("%s\n",returned_response[0]?returned_response:"null");
 printf("{\"delivery_attempts\":%" PRIu64 ",\"http_calls\":%u,\"last_delivery_time_ms\":%" PRIu64 ",\"post_completion_ms\":%" PRIu64 ",\"last_delivery_status\":%d,\"matched_ack_deletes\":%" PRIu64 ",\"queued\":%u}\n",state.delivery_attempts,atomic_load(&http_calls),state.last_delivery_time_ms,post_completion_ms,state.last_delivery_status,state.matched_ack_deletes,(unsigned)snapshot.queued_count);
 return 0;
#elif OWNER_STARTUP_OFF_FAULT
 native_startup_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 power_off_entered=CreateEvent(NULL,TRUE,FALSE,NULL);power_off_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 CHECK(native_startup_release && power_off_entered && power_off_release);
 egolink_sim7670_modem_owner_status_t startup=egolink_sim7670_location_modem_owner_start(&modem);
 CHECK(startup==EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED && startup==23);
 egolink_sim7670_location_modem_owner_snapshot_t state;
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.power_off_attempts==1 && state.power_off_unconfirmed==1 && !state.quiesced && !state.gnss_off_confirmed);
 CHECK(state.cleanup_recovery_required && state.last_power_off_reason==SIM7670_LOCATION_BOUNDED_REASON_AT_RESPONSE_TIMEOUT);
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 SetEvent(native_startup_release);
 CHECK(WaitForSingleObject(power_off_entered,2000)==WAIT_OBJECT_0);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.stop_requested && !state.quiesced && !state.gnss_off_confirmed);
 CHECK(atomic_load(&io_active)==1 && atomic_load(&power_off_calls)==2);
 SetEvent(power_off_release);
 const unsigned expected_attempts=OWNER_STARTUP_OFF_FAULT==2?4:2;
 for(unsigned i=0;i<200;++i){
  egolink_sim7670_location_modem_owner_current_status(&modem,&state);
  if(state.power_off_attempts==expected_attempts && (OWNER_STARTUP_OFF_FAULT==2 || state.quiesced))break;
  Sleep(10);
 }
 CHECK(state.power_off_attempts==expected_attempts && state.recovery_attempts==expected_attempts-1);
#if OWNER_STARTUP_OFF_FAULT == 2
 CHECK(!state.quiesced && !state.gnss_off_confirmed && state.cleanup_recovery_required);
 CHECK(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED && state.last_status==startup);
 CHECK(state.power_off_unconfirmed==4 && state.power_off_confirmed==0);
#else
 CHECK(state.quiesced && state.gnss_off_confirmed && !state.cleanup_recovery_required);
 CHECK(state.lifecycle==EGOLINK_SIM7670_MODEM_OWNER_QUIESCED && state.last_status==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(state.power_off_unconfirmed==1 && state.power_off_confirmed==1);
#endif
 HANDLE restarts[2]={CreateThread(NULL,0,start_race,NULL,0,NULL),CreateThread(NULL,0,start_race,NULL,0,NULL)};
 CHECK(WaitForMultipleObjects(2,restarts,TRUE,2000)==WAIT_OBJECT_0);
 for(unsigned i=0;i<2;++i){DWORD code;CHECK(GetExitCodeThread(restarts[i],&code));CHECK(code==EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED);CloseHandle(restarts[i]);}
 egolink_location_modem_enqueue_result_t queued;
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED);
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 /* Repeated stop/notifications cannot resume cleanup or a stopped owner. */
 Sleep(100);
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(atomic_load(&power_off_calls)==expected_attempts && state.power_off_attempts==expected_attempts);
 CHECK(state.stop_requested && !state.execution_active && state.sensor_commands==0 && state.delivery_attempts==0);
 CHECK(state.prepared_commands==0 && state.executed_commands==0 && state.settled_commands==0 && state.local_sequence==0);
 CHECK(native_created_tasks==1 && atomic_load(&init_calls)==1 && atomic_load(&started)==0);
 CHECK(atomic_load(&sensor_calls)==0 && atomic_load(&http_calls)==0 && atomic_load(&foreign_calls)==0);
 CHECK(atomic_load(&io_active)==0 && atomic_load(&concurrent_io_calls)==0);
 printf("{\"startup_status\":%d,\"power_off_attempts\":%u,\"stop_cleanup_attempts\":%u,\"quiesced\":%s,\"sensor_calls\":0,\"http_calls\":0,\"owner_tasks\":1,\"concurrent_io_calls\":0}\n",startup,expected_attempts,expected_attempts-1,state.quiesced?"true":"false");
 return 0;
#else
#if OWNER_STORAGE_FAULT
 fail_write=true;
#endif
 HANDLE threads[2]={CreateThread(NULL,0,start_race,NULL,0,NULL),CreateThread(NULL,0,start_race,NULL,0,NULL)};
 CHECK(WaitForMultipleObjects(2,threads,TRUE,5000)==WAIT_OBJECT_0);
 CHECK(atomic_load(&started)==1 && atomic_load(&init_calls)==1 && native_created_tasks==1);
 egolink_location_modem_enqueue_result_t queued;
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
 CHECK(WaitForSingleObject(acquisition_entered,2000)==WAIT_OBJECT_0);
 egolink_sim7670_location_modem_owner_snapshot_t state;
 CHECK(egolink_sim7670_location_modem_owner_current_status(&modem,&state)==EGOLINK_SIM7670_MODEM_OWNER_OK && state.execution_active);
 CHECK(egolink_sim7670_location_modem_owner_request_stop(&modem)==EGOLINK_SIM7670_MODEM_OWNER_OK);
 CHECK(egolink_sim7670_location_modem_owner_request_gnss_status(&modem,12000,&queued)==EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED);
 SetEvent(acquisition_release);
 for(unsigned i=0;i<200;++i){egolink_sim7670_location_modem_owner_current_status(&modem,&state);if(state.quiesced)break;Sleep(10);}
 CHECK(state.quiesced && state.gnss_off_confirmed && !state.execution_active);
 CHECK(state.settled_commands==1 && state.local_sequence==1 && state.sensor_commands==1 && atomic_load(&foreign_calls)==0);
 CHECK(state.delivery_attempts==0 && state.last_delivery_time_ms==0 && state.last_delivery_status==0 && atomic_load(&http_calls)==0);
 CHECK(atomic_load(&io_active)==0 && atomic_load(&concurrent_io_calls)==0);
 CHECK(state.source_event_time_ms>=cfg.utc_epoch_at_boot_ms && state.source_event_time_ms-cfg.utc_epoch_at_boot_ms<=GetTickCount64());
#if OWNER_STORAGE_FAULT
 CHECK(state.persistence_failures==1 && state.gnss_state==EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX);
#else
 /* Q is parked and cannot mutate storage: export its real UTC envelope. */
 CHECK(egolink_outbox_begin_send_attempt(&outbox,GetTickCount64(),&send_item)==EGOLINK_OUTBOX_OK);
 printf("%.*s\n",(int)send_item.payload_length,send_item.payload);
#endif
 return 0;
#endif
}
"""
