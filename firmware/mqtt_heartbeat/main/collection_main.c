/* Portable engineering acquisition, selected within the existing target.
 * Sensor tasks never perform network I/O. Only modem_task owns the AT backend.
 * The spool mutex is never held during HTTP. No Location acceptance prerequisite. */
#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include "sdkconfig.h"
#include "cJSON.h"
#include "driver/gpio.h"
#include "collection_record.h"
#include "collection_spool.h"
#include "esp_app_desc.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_partition.h"
#include "esp_p0_https.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "mbedtls/base64.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "platform_imu.h"
#include "platform_power.h"
#include "sim7670_gnss.h"

#if !CONFIG_EGOLINK_COLLECTION_PROFILE
#error "Dedicated collector source requires its profile"
#endif
#define CONFIG_ID "collector-v1-20hz-gnss5s-cell10s"
#define SOURCE_COUNT 12
enum { GNSS, LTE, IMU, WIFI, POWER, DEVICE, ANCHOR, SOURCE_STATUS, SESSION, LOSS, DELIVERY };
static const char *const sources[SOURCE_COUNT]={"gnss","lte","imu","wifi","power","device","time_anchor","source_status","session","loss","delivery","unknown"};
static const char *TAG="collection";
typedef struct { size_t length; unsigned source,seq,loss_version; bool metadata; char bytes[COLLECTION_FRAME_CAPACITY]; } queued_t;
static QueueHandle_t ingress, ram_fallback;
static SemaphoreHandle_t spool_mutex;
static collection_spool_t spool;
static const esp_partition_t *partition;
static atomic_bool spool_ready;
static atomic_bool stopping, imu_stopped, modem_stopped, writer_stopped, wifi_ready;
static atomic_bool imu_finished,modem_finished,uploader_finished;
static atomic_bool main_finished;
static atomic_uint sequences[SOURCE_COUNT], generated_bytes[SOURCE_COUNT], dropped[SOURCE_COUNT];
enum { DROP_ALLOC=1, DROP_FRAME=2, DROP_INGRESS=4, DROP_RAM_FULL=8 };
static portMUX_TYPE loss_mux=portMUX_INITIALIZER_UNLOCKED;
static struct { uint32_t first_seq,last_seq,bytes,unknown_bytes,reasons; } ram_loss[SOURCE_COUNT];
static atomic_uint loss_version,loss_stored_version;
static atomic_uint persisted, acked, send_errors, ram_records, wifi_reason;
static atomic_uint wifi_generation;
static uint32_t boot;
static char clock_domain[64],session_id[64];
static char firmware_elf_sha256[65];
static esp_netif_t *wifi_netif;
static int64_t session_start_us;
static portMUX_TYPE clock_mux=portMUX_INITIALIZER_UNLOCKED;
static int64_t utc_offset_us;

static int64_t now_us(void) { return esp_timer_get_time(); }
static bool cancel(void *ctx,uint32_t token) { (void)ctx;(void)token; return atomic_load(&stopping); }
/* Cleanup must finish after stop is requested, still within its own deadline. */
static bool cleanup_cancel(void *ctx,uint32_t token) { (void)ctx;(void)token;return false; }
static void note_drop(unsigned source,unsigned seq,size_t bytes,unsigned reason)
{
    portENTER_CRITICAL(&loss_mux);
    if(!ram_loss[source].first_seq||seq<ram_loss[source].first_seq)ram_loss[source].first_seq=seq;
    if(seq>ram_loss[source].last_seq)ram_loss[source].last_seq=seq;
    ram_loss[source].bytes+=(uint32_t)bytes;
    if(!bytes)++ram_loss[source].unknown_bytes;
    ram_loss[source].reasons|=reason;
    atomic_fetch_add(&dropped[source],1);
    atomic_fetch_add(&loss_version,1);
    portEXIT_CRITICAL(&loss_mux);
}
static void add_nullable_number(cJSON *o,const char *key,bool valid,double v)
{ if(valid) cJSON_AddNumberToObject(o,key,v); else cJSON_AddNullToObject(o,key); }
static cJSON *envelope(unsigned source,unsigned seq,int64_t mono,const char *status,const char *reason,cJSON *payload)
{
    cJSON *o=cJSON_CreateObject(); if(!o) { cJSON_Delete(payload);return NULL; }
    char id[96],utc[40];
    snprintf(id,sizeof(id),"col-b%" PRIu32 "-%s-%u",boot,sources[source],seq);
    cJSON_AddStringToObject(o,"contract_version","egolink.collection.v1");
    cJSON_AddStringToObject(o,"observation_id",id);
    cJSON_AddStringToObject(o,"device_id",CONFIG_EGOLINK_DEVICE_ID);
    cJSON_AddStringToObject(o,"source",sources[source]);
    cJSON_AddStringToObject(o,"stream_id",sources[source]);
    cJSON_AddNumberToObject(o,"sequence_id",seq);
    cJSON_AddNumberToObject(o,"boot_count",boot);
    cJSON_AddStringToObject(o,"monotonic_clock_domain_id",clock_domain);
    cJSON_AddNumberToObject(o,"timestamp_monotonic_ns",(double)mono*1000.0);
    portENTER_CRITICAL(&clock_mux); int64_t offset=utc_offset_us; portEXIT_CRITICAL(&clock_mux);
    if(offset) {
        int64_t absolute=mono+offset; time_t sec=absolute/1000000; struct tm t;
        gmtime_r(&sec,&t); strftime(utc,sizeof(utc),"%Y-%m-%dT%H:%M:%S",&t);
        size_t n=strlen(utc);snprintf(utc+n,sizeof(utc)-n,".%03uZ",(unsigned)(absolute%1000000/1000));
        cJSON_AddStringToObject(o,"timestamp_utc",utc);
    } else cJSON_AddNullToObject(o,"timestamp_utc");
    cJSON_AddStringToObject(o,"timestamp_source",offset?"sntp_anchor":"esp_timer");
    cJSON_AddStringToObject(o,"timestamp_quality",offset?"network_time_unverified_accuracy":"utc_unknown");
    cJSON_AddStringToObject(o,"fw_version",CONFIG_EGOLINK_FW_VERSION);
    cJSON_AddStringToObject(o,"firmware_elf_sha256",firmware_elf_sha256);
    cJSON_AddStringToObject(o,"config_id",CONFIG_ID);
    cJSON_AddStringToObject(o,"session_id",session_id);
    cJSON_AddStringToObject(o,"status",status);
    if(reason) cJSON_AddStringToObject(o,"missing_reason",reason); else cJSON_AddNullToObject(o,"missing_reason");
    cJSON_AddItemToObject(o,"payload",payload?payload:cJSON_CreateObject());
    return o;
}
static void emit(unsigned source,int64_t mono,const char *status,const char *reason,cJSON *payload,bool metadata)
{
    unsigned seq=atomic_fetch_add(&sequences[source],1)+1;
    queued_t *q=malloc(sizeof(*q)); cJSON *o=envelope(source,seq,mono,status,reason,payload);
    unsigned failure=DROP_ALLOC;size_t bytes=0;
    if(q && o) {
        q->source=source;q->seq=seq;q->metadata=metadata;q->loss_version=0;
        if(source==LOSS){const cJSON *v=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(o,"payload"),"loss_version");if(cJSON_IsNumber(v))q->loss_version=(unsigned)v->valuedouble;}
        q->length=collection_record_frame(o,q->bytes,sizeof(q->bytes));
        bytes=q->length;failure=q->length?DROP_INGRESS:DROP_FRAME;
        if(q->length) atomic_fetch_add(&generated_bytes[source],q->length);
        if(q->length && xQueueSend(ingress,&q,0)==pdTRUE) { cJSON_Delete(o);return; }
    }
    free(q);cJSON_Delete(o);note_drop(source,seq,bytes,failure);
}
static bool flash_read(void *ctx,size_t offset,void *out,size_t length)
{ return esp_partition_read(ctx,offset,out,length)==ESP_OK; }
static bool flash_write(void *ctx,size_t offset,const void *data,size_t length)
{ return esp_partition_write(ctx,offset,data,length)==ESP_OK; }
static bool flash_erase(void *ctx,size_t offset,size_t length)
{ return esp_partition_erase_range(ctx,offset,length)==ESP_OK; }
static void storage_task(void *unused)
{
    (void)unused;queued_t *q;
    while(!atomic_load(&stopping)||!atomic_load(&main_finished)||!atomic_load(&imu_finished)||!atomic_load(&modem_finished)||!atomic_load(&uploader_finished)||uxQueueMessagesWaiting(ingress)) {
        if(xQueueReceive(ingress,&q,pdMS_TO_TICKS(100))!=pdTRUE) continue;
        collection_spool_result_t result=COLLECTION_SPOOL_IO_ERROR;
        xSemaphoreTake(spool_mutex,portMAX_DELAY);
        if(spool_ready) result=collection_spool_append(&spool,q->metadata?COLLECTION_SPOOL_METADATA:COLLECTION_SPOOL_DATA,q->source,((uint64_t)boot<<32)|q->seq,q->bytes,q->length,NULL);
        if(result==COLLECTION_SPOOL_IO_ERROR||result==COLLECTION_SPOOL_CORRUPT||result==COLLECTION_SPOOL_FOREIGN_DATA)spool_ready=false;
        xSemaphoreGive(spool_mutex);
        if(result==COLLECTION_SPOOL_OK) { atomic_fetch_add(&persisted,1);if(q->loss_version)atomic_store(&loss_stored_version,q->loss_version);free(q); }
        else {
            ESP_LOGW(TAG,"STORE result=%s durable=false source=%s seq=%u",collection_spool_result_name(result),sources[q->source],q->seq);
            if(xQueueSend(ram_fallback,&q,0)==pdTRUE) atomic_fetch_add(&ram_records,1);
            else { note_drop(q->source,q->seq,q->length,DROP_RAM_FULL);free(q); }
        }
    }
    atomic_store(&writer_stopped,true);vTaskDelete(NULL);
}
static void source_status(unsigned source,const char *status,const char *reason)
{
    cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"source",sources[source]);
    cJSON_AddBoolToObject(p,"enabled",true);cJSON_AddStringToObject(p,"state",status);
    emit(SOURCE_STATUS,now_us(),status,reason,p,true);
}
static void loss_summary(void)
{
    if(atomic_load(&loss_version)<=atomic_load(&loss_stored_version))return;
    struct {uint32_t count,first,last,bytes,unknown,reasons;} snapshot[SOURCE_COUNT];
    portENTER_CRITICAL(&loss_mux);unsigned version=atomic_load(&loss_version);
    for(unsigned i=0;i<SOURCE_COUNT;i++)snapshot[i]=(typeof(snapshot[i])){atomic_load(&dropped[i]),ram_loss[i].first_seq,ram_loss[i].last_seq,ram_loss[i].bytes,ram_loss[i].unknown_bytes,ram_loss[i].reasons};
    portEXIT_CRITICAL(&loss_mux);
    cJSON *p=cJSON_CreateObject(),*array=cJSON_AddArrayToObject(p,"sources");
    cJSON_AddNumberToObject(p,"loss_version",version);cJSON_AddStringToObject(p,"scope","cumulative_this_boot");
    cJSON_AddStringToObject(p,"reason","bounded_ram_or_record_failure");cJSON_AddBoolToObject(p,"durable_storage_ready_at_capture",spool_ready);
    for(unsigned i=0;i<SOURCE_COUNT;i++)if(snapshot[i].count){
        cJSON *s=cJSON_CreateObject();cJSON_AddStringToObject(s,"source",sources[i]);cJSON_AddNumberToObject(s,"records",snapshot[i].count);
        cJSON_AddNumberToObject(s,"first_source_seq",snapshot[i].first);cJSON_AddNumberToObject(s,"last_source_seq",snapshot[i].last);
        cJSON_AddNumberToObject(s,"bytes_known",snapshot[i].bytes);cJSON_AddNumberToObject(s,"size_unknown_records",snapshot[i].unknown);cJSON_AddNumberToObject(s,"reason_bits",snapshot[i].reasons);cJSON_AddItemToArray(array,s);
    }
    emit(LOSS,now_us(),"lost","see_source_ranges_and_reason_bits",p,true);
}
static void imu_task(void *unused)
{
    (void)unused;
    bool running=platform_imu_init() && platform_imu_capture_begin();
    source_status(IMU,running?"running":"unavailable",running?NULL:"qmi8658_probe_or_start_failed");
    uint8_t binary[20*16];unsigned count=0,failures=0,missed=0;int64_t first=0;
    TickType_t tick=xTaskGetTickCount();
    while(running && !atomic_load(&stopping)) {
        platform_imu_sample_t sample;
        if(platform_imu_sample_real(&sample) && !sample.sample_is_mock && sample.raw_axes_valid) {
            if(!count) first=sample.read_completed_us;
            uint32_t offset=(uint32_t)(sample.read_completed_us-first);uint8_t *b=binary+count*16;
            for(unsigned i=0;i<4;i++) b[i]=(uint8_t)(offset>>(i*8));
            for(unsigned i=0;i<6;i++) {uint16_t v=(uint16_t)sample.raw_axes[i];b[4+i*2]=(uint8_t)v;b[5+i*2]=(uint8_t)(v>>8);}
            ++count;
        } else ++failures;
        if(count==20 || failures>=20 || (atomic_load(&stopping)&&count)) {
            char base64[432];size_t bytes=0;
            mbedtls_base64_encode((unsigned char*)base64,sizeof(base64),&bytes,binary,count*16);base64[bytes]=0;
            cJSON *p=cJSON_CreateObject();
            cJSON_AddStringToObject(p,"encoding","offset_us+six_i16le+base64-v1");
            cJSON_AddStringToObject(p,"samples_b64",base64);
            cJSON_AddNumberToObject(p,"sample_count",count);
            cJSON_AddNumberToObject(p,"sample_record_bytes",16);
            cJSON_AddNumberToObject(p,"requested_interval_us",50000);
            cJSON_AddNumberToObject(p,"accel_full_scale_mg",4000);
            cJSON_AddNumberToObject(p,"gyro_full_scale_mdps",512000);
            cJSON_AddNumberToObject(p,"raw_divisor",32768);
            cJSON_AddNumberToObject(p,"ctrl2",0x13);cJSON_AddNumberToObject(p,"ctrl3",0x55);
            cJSON_AddStringToObject(p,"axis_mount","unverified");
            cJSON_AddStringToObject(p,"sample_time_semantics","host_i2c_read_completed");
            cJSON_AddNumberToObject(p,"read_errors",failures);cJSON_AddNumberToObject(p,"missed_deadlines",missed);
            emit(IMU,count?first:now_us(),failures?"partial":"observed",failures?"i2c_read_failure":NULL,p,false);
            count=failures=missed=0;
        }
        if(xTaskDelayUntil(&tick,pdMS_TO_TICKS(50))!=pdTRUE) {++missed;tick=xTaskGetTickCount();}
    }
    /* Preserve the final short block with the same raw encoding. */
    if(count) {
        char b64[432];size_t n=0;mbedtls_base64_encode((unsigned char*)b64,sizeof(b64),&n,binary,count*16);b64[n]=0;
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"encoding","offset_us+six_i16le+base64-v1");
        cJSON_AddStringToObject(p,"samples_b64",b64);cJSON_AddNumberToObject(p,"sample_count",count);
        cJSON_AddNumberToObject(p,"sample_record_bytes",16);cJSON_AddNumberToObject(p,"requested_interval_us",50000);
        cJSON_AddNumberToObject(p,"accel_full_scale_mg",4000);cJSON_AddNumberToObject(p,"gyro_full_scale_mdps",512000);cJSON_AddNumberToObject(p,"raw_divisor",32768);
        cJSON_AddNumberToObject(p,"ctrl2",0x13);cJSON_AddNumberToObject(p,"ctrl3",0x55);
        cJSON_AddStringToObject(p,"axis_mount","unverified");
        cJSON_AddStringToObject(p,"sample_time_semantics","host_i2c_read_completed");
        cJSON_AddNumberToObject(p,"read_errors",failures);cJSON_AddNumberToObject(p,"missed_deadlines",missed);
        emit(IMU,first,failures?"partial":"observed",failures?"i2c_read_failure":NULL,p,false);
    }
    platform_imu_snapshot_t last;platform_imu_get_snapshot(&last);
    /* A failed begin can leave the real measurement circuit enabled. */
    bool stopped=last.backend!=PLATFORM_IMU_BACKEND_QMI8658 || platform_imu_capture_end();
    source_status(IMU,stopped?"stopped":"error",stopped?NULL:"stop_failed");
    atomic_store(&imu_stopped,stopped);atomic_store(&imu_finished,true);ESP_LOGI(TAG,"IMU stopped=%d",stopped);vTaskDelete(NULL);
}
typedef struct { cJSON *at; bool powered; } trace_t;
static void trace_at(void *context,const char *command,const char *response,int outcome,uint64_t elapsed)
{
    trace_t *t=context;cJSON *a=cJSON_CreateObject();
    cJSON_AddStringToObject(a,"command",command);cJSON_AddStringToObject(a,"response",response);
    cJSON_AddNumberToObject(a,"outcome",outcome);cJSON_AddNumberToObject(a,"elapsed_ms",elapsed);
    cJSON_AddItemToArray(t->at,a);
    if(!strcmp(command,"AT+CGNSSPWR=1") && outcome==0) t->powered=true;
}
static const char *query_status(const sim7670_location_bounded_result_t *r)
{
    if(r->outcome==SIM7670_LOCATION_BOUNDED_REPORT_READY) return "observed";
    if(r->reason==SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID) return "parse_error";
    if(r->reason==SIM7670_LOCATION_BOUNDED_REASON_AT_RESPONSE_TIMEOUT||r->reason==SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED) return "timeout";
    return "error";
}
static void modem_task(void *unused)
{
    (void)unused;esp_err_t init=sim7670_at_backend_init_exclusive_current_task();
    if(init!=ESP_OK) { source_status(GNSS,"error","exclusive_modem_init_failed");source_status(LTE,"error","exclusive_modem_init_failed");atomic_store(&modem_finished,true);vTaskDelete(NULL);return; }
    /* MCU reset does not reset the modem. Reuse the bounded cleanup seam once
     * at session entry, recording the actual response before starting GNSS. */
    trace_t initial={.at=cJSON_CreateArray()};sim7670_location_bounded_result_t initial_result;
    uint32_t operation=1;
    sim7670_location_bounded_request_t initial_request={.timeout_ms=2000,.per_command_timeout_cap_ms=1500,.operation_token=operation++,.cancel_requested=cleanup_cancel,.trace_at=trace_at,.trace_context=&initial};
    sim7670_gnss_power_off_bounded(&initial_request,&initial_result);
    cJSON *initial_payload=cJSON_CreateObject();cJSON_AddItemToObject(initial_payload,"at",initial.at);
    cJSON_AddStringToObject(initial_payload,"phase","session_start_cleanup");
    cJSON_AddNumberToObject(initial_payload,"reason",initial_result.reason);
    emit(GNSS,now_us(),query_status(&initial_result),initial_result.reason?"initial_power_state_unconfirmed":NULL,initial_payload,false);
    bool powered=false;int64_t next_gnss=0,next_cell=0;
    while(!atomic_load(&stopping)) {
        int64_t now=now_us();
        if(now>=next_gnss) {
            trace_t trace={.at=cJSON_CreateArray(),.powered=powered};
            sim7670_location_bounded_request_t req={.timeout_ms=4000,.per_command_timeout_cap_ms=1000,.operation_token=operation++,.receiver_already_powered=powered,.cancel_requested=cancel,.trace_at=trace_at,.trace_context=&trace};
            sim7670_gnss_report_t g;sim7670_location_bounded_result_t r;
            sim7670_gnss_request_location_bounded(&req,&g,&r);powered=trace.powered;
            cJSON *p=cJSON_CreateObject();cJSON_AddItemToObject(p,"at",trace.at);
            cJSON_AddStringToObject(p,"phase","acquisition");
            cJSON_AddBoolToObject(p,"fix",g.fix);cJSON_AddBoolToObject(p,"no_fix",g.no_fix_observed);
            cJSON_AddBoolToObject(p,"receiver_powered_confirmed",powered);
            cJSON_AddNumberToObject(p,"elapsed_ms",r.elapsed_ms);cJSON_AddNumberToObject(p,"reason",r.reason);
            add_nullable_number(p,"latitude",g.lat_valid,g.lat);add_nullable_number(p,"longitude",g.lon_valid,g.lon);
            add_nullable_number(p,"altitude_m",g.altitude_valid,g.altitude_m);add_nullable_number(p,"speed_mps",g.speed_valid,g.speed_mps);
            add_nullable_number(p,"course_deg",g.course_valid,g.course_deg);add_nullable_number(p,"hdop",g.hdop_valid,g.hdop);
            add_nullable_number(p,"pdop",g.pdop_valid,g.pdop);add_nullable_number(p,"vdop",g.vdop_valid,g.vdop);
            add_nullable_number(p,"satellites",g.satellites_valid,g.satellites);
            cJSON_AddStringToObject(p,"receiver_date",g.utc_date);cJSON_AddStringToObject(p,"receiver_time",g.utc_time);
            const char *status=query_status(&r); if(r.outcome==SIM7670_LOCATION_BOUNDED_REPORT_READY&&!g.fix&&g.no_fix_observed) status="no_fix";
            emit(GNSS,now,status,r.reason?"see_at_outcome_and_reason":NULL,p,false);
            next_gnss=now+CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS*1000LL;
        }
        now=now_us();
        if(now>=next_cell&&!atomic_load(&stopping)) {
            trace_t trace={.at=cJSON_CreateArray()};
            sim7670_location_bounded_request_t req={.timeout_ms=5000,.per_command_timeout_cap_ms=500,.operation_token=operation++,.cancel_requested=cancel,.trace_at=trace_at,.trace_context=&trace,.continue_on_status_error=true};
            sim7670_lte_report_t l;sim7670_location_bounded_result_t r;
            sim7670_lte_query_status_bounded(&req,&l,&r);
            cJSON *p=cJSON_CreateObject();cJSON_AddItemToObject(p,"at",trace.at);
            cJSON_AddNumberToObject(p,"elapsed_ms",r.elapsed_ms);cJSON_AddNumberToObject(p,"reason",r.reason);
            cJSON_AddStringToObject(p,"operator",l.operator_name);cJSON_AddStringToObject(p,"rat",l.rat);
            cJSON_AddStringToObject(p,"mcc",l.mcc);cJSON_AddStringToObject(p,"mnc",l.mnc);cJSON_AddStringToObject(p,"tac",l.tac);cJSON_AddStringToObject(p,"cell_id",l.cell_id);
            add_nullable_number(p,"rssi",l.rssi_valid,l.rssi);add_nullable_number(p,"rsrp",l.rsrp_valid,l.rsrp);
            add_nullable_number(p,"rsrq",l.rsrq_valid,l.rsrq);add_nullable_number(p,"sinr",l.sinr_valid,l.sinr);
            cJSON_AddStringToObject(p,"sim_state",l.sim_state);cJSON_AddStringToObject(p,"registration_state",l.registration_state);
            cJSON_AddStringToObject(p,"pdp_state",l.pdp_state);cJSON_AddStringToObject(p,"failure_reason",l.reason_code);
            cJSON_AddBoolToObject(p,"registered",l.registered);cJSON_AddBoolToObject(p,"attached",l.attached);
            cJSON_AddBoolToObject(p,"cell_identity_queried",l.cpsi_query.attempted);
            cJSON_AddBoolToObject(p,"sim_state_queried",l.cpin_query.attempted);cJSON_AddBoolToObject(p,"sim_state_valid",l.cpin_query.parse_valid);
            cJSON_AddBoolToObject(p,"registration_valid",l.cereg_query.parse_valid);cJSON_AddBoolToObject(p,"attachment_valid",l.cgatt_query.parse_valid);
            emit(LTE,now,r.reason&&r.commands_completed>1?"partial":query_status(&r),r.reason?"see_at_outcome_and_reason":NULL,p,false);
            next_cell=now+10000000;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    bool stopped=false;
    for(unsigned i=0;i<3&&!stopped;i++) {
        trace_t trace={.at=cJSON_CreateArray()};sim7670_location_bounded_result_t r;
        sim7670_location_bounded_request_t req={.timeout_ms=2000,.per_command_timeout_cap_ms=1500,.operation_token=operation++,.cancel_requested=cleanup_cancel,.trace_at=trace_at,.trace_context=&trace};
        stopped=sim7670_gnss_power_off_bounded(&req,&r)==SIM7670_LOCATION_BOUNDED_REPORT_READY;
        cJSON *p=cJSON_CreateObject();cJSON_AddItemToObject(p,"at",trace.at);cJSON_AddBoolToObject(p,"stopped",stopped);
        cJSON_AddStringToObject(p,"phase","session_stop_cleanup");
        emit(GNSS,now_us(),stopped?"stopped":"error",stopped?NULL:"power_off_unconfirmed",p,false);
        if(!stopped)vTaskDelay(pdMS_TO_TICKS(500));
    }
    atomic_store(&modem_stopped,stopped);atomic_store(&modem_finished,true);ESP_LOGI(TAG,"MODEM stopped=%d exclusive_owner=true",stopped);vTaskDelete(NULL);
}
static void network_event(void *ctx,esp_event_base_t base,int32_t id,void *data)
{
    (void)ctx;
    if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP) {
        atomic_store(&wifi_ready,true);atomic_fetch_add(&wifi_generation,1);
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"phase","link_event");cJSON_AddBoolToObject(p,"connected",true);
        emit(WIFI,now_us(),"connected",NULL,p,false);
    }
    if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED) {
        atomic_store(&wifi_ready,false);wifi_event_sta_disconnected_t *e=data;atomic_store(&wifi_reason,e?e->reason:0);
        atomic_fetch_add(&wifi_generation,1);
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"phase","link_event");cJSON_AddBoolToObject(p,"connected",false);cJSON_AddNumberToObject(p,"disconnect_reason",e?e->reason:0);
        emit(WIFI,now_us(),"disconnected","wifi_disconnect_event",p,false);
    }
}
static bool network_init(void)
{
    if(esp_netif_init()!=ESP_OK||esp_event_loop_create_default()!=ESP_OK)return false;
    wifi_netif=esp_netif_create_default_wifi_sta();wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    if(!wifi_netif||esp_wifi_init(&init)!=ESP_OK||esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK)return false;
    esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL);
    esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event,NULL);
    wifi_config_t cfg={0};
    if(strlen(CONFIG_EGOLINK_WIFI_SSID)>32||strlen(CONFIG_EGOLINK_WIFI_PASSWORD)>63)return false;
    memcpy(cfg.sta.ssid,CONFIG_EGOLINK_WIFI_SSID,strlen(CONFIG_EGOLINK_WIFI_SSID));
    memcpy(cfg.sta.password,CONFIG_EGOLINK_WIFI_PASSWORD,strlen(CONFIG_EGOLINK_WIFI_PASSWORD));
    cfg.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;
    if(esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK||esp_wifi_set_config(WIFI_IF_STA,&cfg)!=ESP_OK||esp_wifi_start()!=ESP_OK)return false;
    esp_wifi_connect();esp_sntp_config_t clock=ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    return esp_netif_sntp_init(&clock)==ESP_OK;
}
static void scan_wifi(void)
{
    int64_t capture=now_us();wifi_scan_config_t cfg={0};
    esp_err_t result=esp_wifi_scan_start(&cfg,true);uint16_t count=16,total=0;wifi_ap_record_t aps[16];
    cJSON *p=cJSON_CreateObject(),*array=cJSON_AddArrayToObject(p,"aps");
    if(result==ESP_OK) { esp_wifi_scan_get_ap_num(&total);result=esp_wifi_scan_get_ap_records(&count,aps); }
    if(result==ESP_OK)for(unsigned i=0;i<count;i++) {
        cJSON *a=cJSON_CreateObject();char id[18];snprintf(id,sizeof(id),"%02x:%02x:%02x:%02x:%02x:%02x",aps[i].bssid[0],aps[i].bssid[1],aps[i].bssid[2],aps[i].bssid[3],aps[i].bssid[4],aps[i].bssid[5]);
        cJSON_AddStringToObject(a,"bssid",id);cJSON_AddNumberToObject(a,"rssi",aps[i].rssi);cJSON_AddNumberToObject(a,"channel",aps[i].primary);cJSON_AddItemToArray(array,a);
    }
    cJSON_AddNumberToObject(p,"scan_result",result);cJSON_AddNumberToObject(p,"total_seen",total);cJSON_AddBoolToObject(p,"truncated",total>16);
    cJSON_AddBoolToObject(p,"connected",atomic_load(&wifi_ready));cJSON_AddNumberToObject(p,"disconnect_reason",atomic_load(&wifi_reason));
    emit(WIFI,capture,result==ESP_OK?"observed":"error",result==ESP_OK?NULL:"scan_failed",p,false);
}
static bool boot_identity(void)
{
    if(nvs_flash_init()!=ESP_OK)return false;
    nvs_handle_t n;
    if(nvs_open("ego_collection",NVS_READWRITE,&n)!=ESP_OK)return false;
    uint32_t previous=0;esp_err_t r=nvs_get_u32(n,"boot",&previous);
    if(r!=ESP_OK&&r!=ESP_ERR_NVS_NOT_FOUND){nvs_close(n);return false;}
    if(previous==UINT32_MAX){nvs_close(n);return false;}boot=previous+1;
    r=nvs_set_u32(n,"boot",boot);if(r==ESP_OK)r=nvs_commit(n);
    uint32_t check=0;if(r==ESP_OK)r=nvs_get_u32(n,"boot",&check);nvs_close(n);
    snprintf(clock_domain,sizeof(clock_domain),"collection-esp-timer-b%" PRIu32,boot);
    snprintf(session_id,sizeof(session_id),"collection-b%" PRIu32,boot);
    return r==ESP_OK&&check==boot;
}
static void health(void)
{
    collection_spool_stats_t stats={0};xSemaphoreTake(spool_mutex,portMAX_DELAY);
    bool stats_valid=spool_ready;
    if(stats_valid)collection_spool_get_stats(&spool,&stats);
    xSemaphoreGive(spool_mutex);
    platform_power_snapshot_t power;platform_power_get_snapshot(&power);
    cJSON *p=cJSON_CreateObject();
    add_nullable_number(p,"battery_millivolt",power.battery_voltage_valid&&!power.battery_is_mock,power.battery_millivolt);
    add_nullable_number(p,"fuel_gauge_soc_percent",!power.battery_is_mock,power.battery_percent);
    if(!power.charging_is_mock)cJSON_AddBoolToObject(p,"charging",power.charging);else cJSON_AddNullToObject(p,"charging");
    cJSON_AddStringToObject(p,"battery_source",power.battery_is_mock?"unavailable":power.battery_source);
    cJSON_AddStringToObject(p,"charging_source",power.charging_is_mock?"unavailable":power.charging_source);
    emit(POWER,now_us(),power.battery_is_mock?"unavailable":"observed",power.battery_is_mock?"gauge_not_available":NULL,p,false);
    p=cJSON_CreateObject();cJSON_AddNumberToObject(p,"uptime_ms",now_us()/1000);
    cJSON_AddNumberToObject(p,"reset_reason",esp_reset_reason());cJSON_AddNumberToObject(p,"heap_free",esp_get_free_heap_size());
    cJSON_AddBoolToObject(p,"durable_storage_ready",spool_ready);
    cJSON_AddNumberToObject(p,"cache_capacity_bytes",stats.capacity_bytes);cJSON_AddNumberToObject(p,"cache_append_free_bytes",stats.append_free_bytes);
    cJSON_AddNumberToObject(p,"queue_bytes",stats.pending_payload_bytes);cJSON_AddNumberToObject(p,"pending_records",stats.pending_records);
    cJSON_AddNumberToObject(p,"evicted_records",stats.evicted_records);cJSON_AddNumberToObject(p,"evicted_bytes",stats.evicted_payload_bytes);
    cJSON_AddNumberToObject(p,"flash_written_bytes",stats.write_bytes_this_boot);cJSON_AddNumberToObject(p,"flash_erased_bytes",stats.erased_bytes_this_boot);
    cJSON_AddNumberToObject(p,"quarantined_sectors",stats.quarantined_sectors);cJSON_AddNumberToObject(p,"torn_tails",stats.torn_tails);cJSON_AddNumberToObject(p,"storage_io_errors",stats.io_errors_this_boot);
    cJSON_AddBoolToObject(p,"storage_stats_valid",stats_valid);
    if(!stats_valid){const char *fields[]={"cache_capacity_bytes","cache_append_free_bytes","queue_bytes","pending_records","evicted_records","evicted_bytes","flash_written_bytes","flash_erased_bytes","quarantined_sectors","torn_tails","storage_io_errors"};for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++)cJSON_ReplaceItemInObjectCaseSensitive(p,fields[i],cJSON_CreateNull());}
    cJSON_AddNumberToObject(p,"ram_pending",uxQueueMessagesWaiting(ram_fallback));cJSON_AddNumberToObject(p,"acked_this_boot",atomic_load(&acked));
    cJSON *rates=cJSON_AddObjectToObject(p,"sources");
    for(unsigned i=0;i<SOURCE_COUNT;i++){
        cJSON *s=cJSON_AddObjectToObject(rates,sources[i]);cJSON_AddNumberToObject(s,"generated_bytes",atomic_load(&generated_bytes[i]));
        portENTER_CRITICAL(&loss_mux);
        uint32_t n=atomic_load(&dropped[i]),first=ram_loss[i].first_seq,last=ram_loss[i].last_seq,bytes=ram_loss[i].bytes,unknown=ram_loss[i].unknown_bytes,reasons=ram_loss[i].reasons;
        portEXIT_CRITICAL(&loss_mux);
        cJSON_AddNumberToObject(s,"ram_dropped",n);
        if(n){cJSON_AddNumberToObject(s,"first_lost_seq",first);cJSON_AddNumberToObject(s,"last_lost_seq",last);cJSON_AddNumberToObject(s,"lost_bytes_known",bytes);cJSON_AddNumberToObject(s,"lost_size_unknown_records",unknown);cJSON_AddNumberToObject(s,"loss_reason_bits",reasons);}
    }
    cJSON_AddStringToObject(p,"loss_reason_bits","1=allocation,2=frame_capacity_or_encoding,4=ingress_full,8=storage_failed_ram_full");
    emit(DEVICE,now_us(),"observed",NULL,p,false);
    loss_summary();
    ESP_LOGI(TAG,"HEALTH boot=%" PRIu32 " durable=%d persisted=%u acked=%u queued_bytes=%" PRIu64 " evicted=%" PRIu64 " ram_pending=%u errors=%u",boot,spool_ready,atomic_load(&persisted),atomic_load(&acked),stats.pending_payload_bytes,stats.evicted_records,(unsigned)uxQueueMessagesWaiting(ram_fallback),atomic_load(&send_errors));
}
static void uploader_task(void *unused);
static size_t loss_frame(const collection_spool_record_t *record,const void *data,char *frame)
{
    collection_spool_loss_t loss;
    if(collection_spool_decode_loss(data,record->token.payload_bytes,&loss)!=COLLECTION_SPOOL_OK)return 0;
    cJSON *p=cJSON_CreateObject(),*a=cJSON_AddArrayToObject(p,"sources");
    cJSON_AddStringToObject(p,"reason","capacity_eviction");
    cJSON_AddNumberToObject(p,"evicted_records_total",loss.evicted_records_total);
    cJSON_AddNumberToObject(p,"evicted_bytes_total",loss.evicted_bytes_total);
    for(unsigned i=0;i<loss.source_count;i++) {
        cJSON *s=cJSON_CreateObject();unsigned source=loss.sources[i].source_id;
        cJSON_AddStringToObject(s,"source",source<SOURCE_COUNT?sources[source]:"unknown");
        cJSON_AddNumberToObject(s,"records",loss.sources[i].records);cJSON_AddNumberToObject(s,"bytes",loss.sources[i].payload_bytes);
        uint64_t first=loss.sources[i].first_source_seq,last=loss.sources[i].last_source_seq;
        cJSON_AddNumberToObject(s,"first_source_seq",(uint32_t)first);cJSON_AddNumberToObject(s,"last_source_seq",(uint32_t)last);cJSON_AddItemToArray(a,s);
        cJSON_AddNumberToObject(s,"first_ticket",loss.sources[i].first_ticket);cJSON_AddNumberToObject(s,"last_ticket",loss.sources[i].last_ticket);
        /* The existing u64 spool sequence now carries boot:u32 + sequence:u32.
         * Keep old unqualified loss frames byte-identical across retries. */
        if((first>>32)||(last>>32)){
            add_nullable_number(s,"first_boot_count",first>>32,(uint32_t)(first>>32));
            add_nullable_number(s,"last_boot_count",last>>32,(uint32_t)(last>>32));
        }
    }
    /* Loss intents originate in the persistent spool. They have no capture
     * clock. Use only persisted token fields so reboot never changes bytes. */
    cJSON *o=envelope(LOSS,(unsigned)record->token.ticket,0,"lost","eviction_clock_unavailable",p);
    char id[96];snprintf(id,sizeof(id),"col-loss-g%" PRIu64 "-t%" PRIu64,record->token.sector_generation,record->token.ticket);
    cJSON_ReplaceItemInObjectCaseSensitive(o,"observation_id",cJSON_CreateString(id));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"boot_count",cJSON_CreateNumber(0));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"monotonic_clock_domain_id",cJSON_CreateString("spool-loss-no-capture-clock"));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"timestamp_utc",cJSON_CreateNull());
    cJSON_ReplaceItemInObjectCaseSensitive(o,"timestamp_source",cJSON_CreateString("unavailable"));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"timestamp_quality",cJSON_CreateString("unknown"));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"fw_version",cJSON_CreateString("spool-v1"));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"config_id",cJSON_CreateString("spool-v1"));
    cJSON_ReplaceItemInObjectCaseSensitive(o,"session_id",cJSON_CreateNull());
    /* Eviction intents do not retain the firmware identity of the uploader. */
    cJSON_DeleteItemFromObjectCaseSensitive(o,"firmware_elf_sha256");
    size_t n=collection_record_frame(o,frame,COLLECTION_FRAME_CAPACITY);cJSON_Delete(o);return n;
}
static void uploader_task(void *unused)
{
    (void)unused;bool network=network_init(),anchored=false;
    int64_t next_connect=0,next_scan=3000000,next_send=0;unsigned backoff=1000,durable_streak=0,connection_generation=atomic_load(&wifi_generation);
    static char buffer[COLLECTION_FRAME_CAPACITY],loss_buffer[COLLECTION_FRAME_CAPACITY];
    static uint8_t response[8192];
    egolink_esp_p0_https_t https={.origin=CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL,.expected_host=CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST,
        .bearer=CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,.max_attempts=1,.transaction_timeout_ms=12000,.reuse_connection=true};
    while(!atomic_load(&stopping)) {
        int64_t now=now_us();
        if(connection_generation!=atomic_load(&wifi_generation)||!atomic_load(&wifi_ready)){
            egolink_esp_p0_https_close(&https);connection_generation=atomic_load(&wifi_generation);
        }
        if(network&&!atomic_load(&wifi_ready)&&now>=next_connect) {esp_wifi_connect();next_connect=now+10000000;}
        if(network&&now>=next_scan) {scan_wifi();next_scan=now_us()+45000000;}
        if(network&&atomic_load(&wifi_ready)&&!anchored) {
            struct timeval t;if(gettimeofday(&t,NULL)==0&&t.tv_sec>=1767225600&&t.tv_sec<4102444800LL) {
                int64_t mono=now_us(),utc=(int64_t)t.tv_sec*1000000+t.tv_usec;
                cJSON *p=cJSON_CreateObject();cJSON_AddNumberToObject(p,"timestamp_monotonic_ns",(double)mono*1000);
                cJSON_AddNumberToObject(p,"utc_ms",utc/1000);cJSON_AddStringToObject(p,"source","sntp");
                cJSON_AddNullToObject(p,"uncertainty_ms");cJSON_AddStringToObject(p,"uncertainty_reason","not_measured");
                emit(ANCHOR,mono,"observed",NULL,p,true);
                portENTER_CRITICAL(&clock_mux);utc_offset_us=utc-mono;portEXIT_CRITICAL(&clock_mux);anchored=true;
            }
        }
        if(!atomic_load(&wifi_ready)||!anchored||now<next_send) {vTaskDelay(pdMS_TO_TICKS(100));continue;}
        collection_spool_record_t record={0};collection_spool_result_t result=COLLECTION_SPOOL_EMPTY;
        xSemaphoreTake(spool_mutex,portMAX_DELAY);
        if(spool_ready)result=collection_spool_peek(&spool,&record,buffer,sizeof(buffer));
        if(result==COLLECTION_SPOOL_OK)result=collection_spool_pin(&spool,&record.token);
        if(result==COLLECTION_SPOOL_IO_ERROR||result==COLLECTION_SPOOL_CORRUPT)spool_ready=false;
        xSemaphoreGive(spool_mutex);
        queued_t *ram=NULL;char *body=buffer;size_t length=record.token.payload_bytes;
        bool durable=result==COLLECTION_SPOOL_OK;
        if(durable&&durable_streak>=4&&xQueuePeek(ram_fallback,&ram,0)==pdTRUE){
            xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);
            durable=false;durable_streak=0;
        }
        if(durable&&record.kind==COLLECTION_SPOOL_LOSS){length=loss_frame(&record,buffer,loss_buffer);body=loss_buffer;}
        if(!durable) {
            if(!ram&&xQueuePeek(ram_fallback,&ram,0)!=pdTRUE){vTaskDelay(pdMS_TO_TICKS(100));continue;}
            body=ram->bytes;length=ram->length;
        }
        if(!length){
            xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);
            atomic_fetch_add(&send_errors,1);next_send=now+60000000;continue;
        }
        char interface_name[8]={0};
        if(esp_netif_get_netif_impl_name(wifi_netif,interface_name)!=ESP_OK){
            xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);
            next_send=now+5000000;continue;
        }
        https.attempts=0;https.deadline_ms=(uint64_t)now_us()/1000+13000;
        egolink_p0_delivery_post_request_t request={.body=(uint8_t*)body,.body_length=length,.response=response,.response_capacity=sizeof(response),.cancel_requested=cancel};
        egolink_p0_delivery_post_result_t posted={0};
        egolink_p0_delivery_post_outcome_t outcome=egolink_esp_p0_https_post_collection(&https,CONFIG_EGOLINK_DEVICE_ID,interface_name,&request,&posted);
        bool matched=outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE&&posted.http_status_code>=200&&posted.http_status_code<300&&
            collection_record_ack_matches(body,length,CONFIG_EGOLINK_DEVICE_ID,response,posted.response_length);
        if(matched) {
            if(durable) {
                xSemaphoreTake(spool_mutex,portMAX_DELAY);result=collection_spool_ack(&spool,&record.token);
                if(result==COLLECTION_SPOOL_IO_ERROR||result==COLLECTION_SPOOL_CORRUPT)spool_ready=false;
                xSemaphoreGive(spool_mutex);
                if(result==COLLECTION_SPOOL_OK){atomic_fetch_add(&acked,1);++durable_streak;}
            } else if(xQueueReceive(ram_fallback,&ram,0)==pdTRUE){atomic_fetch_add(&acked,1);free(ram);}
            backoff=1000;next_send=now_us()+50000;
        } else {
            egolink_esp_p0_https_close(&https);
            atomic_fetch_add(&send_errors,1);
            bool permanent=posted.http_status_code==401||posted.http_status_code==403||posted.http_status_code==400||posted.http_status_code==409||posted.http_status_code==422||posted.transport_error==EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS;
            next_send=now_us()+(permanent?300000000LL:(int64_t)backoff*1000);
            if(backoff<60000)backoff=backoff>30000?60000:backoff*2;
        }
        xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);
        ESP_LOGI(TAG,"UPLOAD interface=wifi http=%u matched=%d durable=%d bytes=%u",posted.http_status_code,matched,durable,(unsigned)length);
    }
    egolink_esp_p0_https_close(&https);
    if(network) {
        esp_netif_sntp_deinit();esp_wifi_disconnect();esp_wifi_stop();
        esp_event_handler_unregister(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event);
        esp_event_handler_unregister(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event);
    }
    atomic_store(&uploader_finished,true);
    ESP_LOGI(TAG,"UPLOADER stopped=true durable_cache_preserved=true volatile_ram_pending=%u",(unsigned)uxQueueMessagesWaiting(ram_fallback));vTaskDelete(NULL);
}
void app_main(void)
{
    session_start_us=now_us();
    const esp_app_desc_t *application=esp_app_get_description();
    for(unsigned i=0;i<32;i++)snprintf(firmware_elf_sha256+i*2,3,"%02x",application->app_elf_sha256[i]);
    if(!boot_identity()) {ESP_LOGE(TAG,"STOP identity_persistence_failed nvs_preserved=true");return;}
    ingress=xQueueCreate(16,sizeof(queued_t*));ram_fallback=xQueueCreate(4,sizeof(queued_t*));spool_mutex=xSemaphoreCreateMutex();
    if(!ingress||!ram_fallback||!spool_mutex){ESP_LOGE(TAG,"STOP allocation_failed");return;}
    partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x41,"ego_collection");
    if(partition && !partition->encrypted && partition->erase_size==4096 && partition->address==0x122000 && partition->size==0xD2000) {
        collection_spool_config_t config={.context=(void*)partition,.read=flash_read,.write=flash_write,.erase=flash_erase,.capacity_bytes=partition->size,.erase_bytes=4096,.protected_sectors=8,.evict_oldest=true};
        collection_spool_result_t r=collection_spool_init(&spool,&config);spool_ready=r==COLLECTION_SPOOL_OK;
        ESP_LOGI(TAG,"STORAGE init=%s capacity=%u foreign_data_preserved=true",collection_spool_result_name(r),(unsigned)partition->size);
    }
    platform_power_init();
    ESP_LOGI(TAG,"START boot=%" PRIu32 " firmware=%s no_sim_profile=%d run_seconds=%d media=false",boot,CONFIG_EGOLINK_FW_VERSION,CONFIG_EGOLINK_COLLECTION_NO_SIM,CONFIG_EGOLINK_COLLECTION_RUN_SECONDS);
    /* Both reviewed Waveshare V1/V2 schematics connect BOOT to GPIO0/GND.
     * Input only: a one-second press requests cooperative collection stop. */
    gpio_config_t button={.pin_bit_mask=1ULL<<0,.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    bool button_ready=gpio_config(&button)==ESP_OK;
    ESP_LOGI(TAG,"LOCAL_STOP gpio=0 input_ready=%d initial_level=%d hold_ms=1000",button_ready,button_ready?gpio_get_level(0):-1);
    cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"state","started");cJSON_AddStringToObject(p,"config_id",CONFIG_ID);
    cJSON_AddNumberToObject(p,"imu_sample_interval_us",50000);cJSON_AddNumberToObject(p,"imu_chunk_samples",20);cJSON_AddNumberToObject(p,"gnss_interval_ms",CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS);
    cJSON_AddBoolToObject(p,"camera_enabled",false);cJSON_AddBoolToObject(p,"audio_enabled",false);
    cJSON_AddNumberToObject(p,"run_seconds",CONFIG_EGOLINK_COLLECTION_RUN_SECONDS);
    cJSON_AddStringToObject(p,"stop_method",button_ready?"hold_BOOT_1_second_or_configured_deadline":"configured_deadline_only_button_init_failed");
    cJSON_AddStringToObject(p,"media_reason","assembly_and_capture_scope_not_confirmed");
    emit(SESSION,session_start_us,"started",NULL,p,true);
    BaseType_t store_created=xTaskCreate(storage_task,"collection_store",6144,NULL,4,NULL);
    BaseType_t imu_created=xTaskCreatePinnedToCore(imu_task,"collection_imu",6144,NULL,6,NULL,1);
    BaseType_t modem_created=xTaskCreate(modem_task,"collection_modem",12288,NULL,4,NULL);
    BaseType_t upload_created=xTaskCreate(uploader_task,"collection_upload",12288,NULL,3,NULL);
    if(store_created!=pdPASS)atomic_store(&writer_stopped,true);
    if(imu_created!=pdPASS)atomic_store(&imu_finished,true);
    if(modem_created!=pdPASS)atomic_store(&modem_finished,true);
    if(upload_created!=pdPASS)atomic_store(&uploader_finished,true);
    if(store_created!=pdPASS||imu_created!=pdPASS||modem_created!=pdPASS||upload_created!=pdPASS) {
        atomic_store(&stopping,true);ESP_LOGE(TAG,"STOP task_creation_failed");
    }
    int64_t next_health=0,button_down=0;
    while(!atomic_load(&stopping)) {
        if(now_us()>=next_health){health();next_health=now_us()+10000000;}
        if(CONFIG_EGOLINK_COLLECTION_RUN_SECONDS && now_us()-session_start_us>=CONFIG_EGOLINK_COLLECTION_RUN_SECONDS*1000000LL) atomic_store(&stopping,true);
        if(button_ready&&gpio_get_level(0)==0) {
            if(!button_down)button_down=now_us();
            if(now_us()-button_down>=1000000){ESP_LOGI(TAG,"LOCAL_STOP recognized=true");atomic_store(&stopping,true);}
        }else button_down=0;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    for(unsigned i=0;i<200 && !(atomic_load(&imu_finished)&&atomic_load(&modem_finished)&&atomic_load(&uploader_finished));i++)vTaskDelay(pdMS_TO_TICKS(100));
    bool sources_stopped=atomic_load(&imu_stopped)&&atomic_load(&modem_stopped)&&atomic_load(&uploader_finished);
    p=cJSON_CreateObject();cJSON_AddStringToObject(p,"state",sources_stopped?"stopped":"stop_failed");
    cJSON_AddBoolToObject(p,"imu_stop_confirmed",atomic_load(&imu_stopped));
    cJSON_AddBoolToObject(p,"modem_stop_confirmed",atomic_load(&modem_stopped));
    cJSON_AddBoolToObject(p,"uploader_finished",atomic_load(&uploader_finished));
    cJSON_AddNumberToObject(p,"volatile_ram_pending",uxQueueMessagesWaiting(ram_fallback));
    loss_summary();
    emit(SESSION,now_us(),sources_stopped?"stopped":"error",sources_stopped?NULL:"source_stop_unconfirmed",p,true);
    atomic_store(&main_finished,true);
    for(unsigned i=0;i<50 && !atomic_load(&writer_stopped);i++)vTaskDelay(pdMS_TO_TICKS(100));
    ESP_LOGI(TAG,"STOP complete=%d imu=%d modem=%d writer=%d cache_preserved=true",sources_stopped&&atomic_load(&writer_stopped),atomic_load(&imu_stopped),atomic_load(&modem_stopped),atomic_load(&writer_stopped));
}
