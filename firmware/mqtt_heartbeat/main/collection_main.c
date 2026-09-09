/* Portable engineering acquisition, selected within the existing target.
 * Sensor tasks never perform network I/O. Only modem_task owns the AT backend.
 * The spool mutex is never held during HTTP. No Location acceptance prerequisite. */
#include <inttypes.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include "sdkconfig.h"
#include "cJSON.h"
#include "driver/gpio.h"
#include "collection_network_coordinator.h"
#include "collection_network_policy.h"
#include "collection_record.h"
#include "collection_spool.h"
#include "collection_usb_lte.h"
#include "esp_app_desc.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
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
#include "mbedtls/sha256.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "photo_media_store.h"
#include "photo_control_runtime.h"
#include "photo_delivery_runtime.h"
#include "platform_camera.h"
#include "platform_imu.h"
#include "platform_power.h"
#include "sim7670_gnss.h"

#ifndef CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
#define CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED 0
#endif
#ifndef CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
#define CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE 0
#endif

#if !CONFIG_EGOLINK_COLLECTION_PROFILE
#error "Dedicated collector source requires its profile"
#endif
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
#if CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_INITIAL_MS > CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_MAX_MS
#error "Photo upload initial backoff must not exceed its maximum"
#endif
#if !CONFIG_ESPTOOLPY_FLASHSIZE_16MB
#error "Camera collection profile requires the explicit 16 MiB flash image size"
#endif
#if CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES % 4096 != 0
#error "Photo media slots must be whole 4 KiB erase sectors"
#endif
#if CONFIG_EGOLINK_PHOTO_MEDIA_MAX_PAYLOAD_BYTES + PHOTO_MEDIA_STORE_HEADER_BYTES > CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES
#error "Photo payload plus header exceeds its dedicated slot"
#endif
#if 0x900000 % CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES != 0
#error "Photo media partition must contain whole fixed-size slots"
#endif
#if 0x900000 / CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES > PHOTO_MEDIA_STORE_MAX_SLOTS
#error "Photo media partition slot count exceeds static recovery index capacity"
#endif
#if CONFIG_EGOLINK_PHOTO_MEDIA_MAX_COMMITTED_PHOTOS > 0x900000 / CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES
#error "Photo count quota exceeds available media slots"
#endif
#if CONFIG_EGOLINK_PHOTO_MEDIA_MAX_TOTAL_PAYLOAD_BYTES > CONFIG_EGOLINK_PHOTO_MEDIA_MAX_COMMITTED_PHOTOS * CONFIG_EGOLINK_PHOTO_MEDIA_MAX_PAYLOAD_BYTES
#error "Photo byte quota cannot be reached within the configured photo count quota"
#endif
#endif
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
#if !CONFIG_EGOLINK_COLLECTION_LTE_USB_DESCRIPTOR_VERIFIED
#error "LTE/PPP requires an operator-verified exact USB descriptor"
#endif
#if CONFIG_EGOLINK_COLLECTION_LTE_USB_VENDOR_ID == 0 || CONFIG_EGOLINK_COLLECTION_LTE_USB_PRODUCT_ID == 0 || CONFIG_EGOLINK_COLLECTION_LTE_USB_MODEM_INTERFACE < 0
#error "LTE/PPP requires nonzero VID/PID and an explicit modem interface"
#endif
#if CONFIG_EGOLINK_COLLECTION_LTE_RETRY_INITIAL_MS > CONFIG_EGOLINK_COLLECTION_LTE_RETRY_MAX_MS
#error "LTE retry initial backoff must not exceed its maximum"
#endif
#endif
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
#if CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
#define CONFIG_ID "collector-v1-camera-shared-i2c-trial_unverified"
#elif CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED
#define CONFIG_ID "collector-v1-camera-shared-i2c-verified"
#else
#define CONFIG_ID "collector-v1-camera-shared-i2c-blocked"
#endif
#define COLLECTION_PARTITION_ADDRESS 0x500000U
#define COLLECTION_PARTITION_SIZE 0x100000U
#define SOURCE_COUNT 13
enum { GNSS, LTE, IMU, WIFI, POWER, DEVICE, ANCHOR, SOURCE_STATUS, SESSION, LOSS, DELIVERY, CAMERA, UNKNOWN_SOURCE };
static const char *const sources[SOURCE_COUNT]={"gnss","lte","imu","wifi","power","device","time_anchor","source_status","session","loss","delivery","camera","unknown"};
#else
#define CONFIG_ID "collector-v1-20hz-gnss5s-cell10s"
#define COLLECTION_PARTITION_ADDRESS 0x122000U
#define COLLECTION_PARTITION_SIZE 0xD2000U
#define SOURCE_COUNT 12
enum { GNSS, LTE, IMU, WIFI, POWER, DEVICE, ANCHOR, SOURCE_STATUS, SESSION, LOSS, DELIVERY };
static const char *const sources[SOURCE_COUNT]={"gnss","lte","imu","wifi","power","device","time_anchor","source_status","session","loss","delivery","unknown"};
#endif
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
_Static_assert(sizeof(CONFIG_ID)<=PHOTO_CONTROL_CAPTURE_RUNTIME_CONFIG_BYTES,
    "camera runtime config id exceeds capture journal provenance bound");
_Static_assert(sizeof(CONFIG_EGOLINK_FW_VERSION)<=
    PHOTO_CONTROL_CAPTURE_FW_VERSION_BYTES,
    "camera firmware version exceeds capture journal provenance bound");
#endif
#define MEDIA_PARTITION_ADDRESS 0x600000U
#define MEDIA_PARTITION_SIZE 0x900000U
#define PHOTO_ORDINARY_UPLOAD_BUDGET 8U
#define PHOTO_FAIR_UPLOAD_INTERVAL_US 30000000LL
#define PHOTO_CAPTURE_SETTLE_RETRY_INITIAL_MS 1000U
#define PHOTO_CAPTURE_SETTLE_RETRY_MAX_MS 60000U
static const char *TAG="collection";
typedef struct { size_t length; unsigned source,seq,loss_version; bool metadata; char bytes[COLLECTION_FRAME_CAPACITY]; } queued_t;
static QueueHandle_t ingress, ram_fallback;
static SemaphoreHandle_t spool_mutex;
static collection_spool_t spool;
static const esp_partition_t *partition;
static atomic_bool spool_ready;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
static photo_media_store_t media_store;
static const esp_partition_t *media_partition;
static SemaphoreHandle_t media_store_mutex;
static atomic_bool media_store_ready;
static atomic_bool photo_control_state_ready;
static atomic_uint photo_capture_attempts,photo_capture_saved,photo_capture_failures;
static atomic_uint photo_upload_acked,photo_upload_failures,photo_expired_released;
static atomic_uint photo_command_polls,photo_command_parse_failures,photo_command_acks;
static atomic_uint photo_metadata_persist_retries;
static atomic_uint photo_command_ack_sequence;
static uint64_t photo_metadata_ack_watermark;
static photo_control_timer_t photo_timer;
static photo_control_journal_t photo_journal;
static photo_control_capture_journal_t photo_capture_journal;
static portMUX_TYPE photo_state_mux=portMUX_INITIALIZER_UNLOCKED;
static atomic_uint photo_main_stack_hwm_bytes;
static atomic_uint photo_store_stack_hwm_bytes;
static atomic_uint photo_imu_stack_hwm_bytes;
static atomic_uint photo_modem_stack_hwm_bytes;
static atomic_uint photo_upload_stack_hwm_bytes;
static atomic_uint photo_wifi_stack_hwm_bytes;
#endif
static atomic_bool stopping, imu_stopped, modem_stopped, writer_stopped, wifi_ready;
static atomic_bool imu_finished,modem_finished,uploader_finished,wifi_finished,wifi_cleanup_confirmed;
static atomic_bool gnss_stopped,lte_ppp_stopped,lte_hangup_required,lte_hangup_confirmed,lte_cleanup_confirmed;
static atomic_bool main_finished;
static atomic_uint sequences[SOURCE_COUNT], generated_bytes[SOURCE_COUNT], dropped[SOURCE_COUNT];
enum { DROP_ALLOC=1, DROP_FRAME=2, DROP_INGRESS=4, DROP_RAM_FULL=8 };
static portMUX_TYPE loss_mux=portMUX_INITIALIZER_UNLOCKED;
static struct { uint32_t first_seq,last_seq,bytes,unknown_bytes,reasons; } ram_loss[SOURCE_COUNT];
static atomic_uint loss_version,loss_stored_version;
static atomic_uint persisted, acked, send_errors, ram_records, wifi_reason;
static atomic_uint network_route_generation;
static atomic_uint uploader_active_generation,uploader_retired_generation;
static uint32_t boot;
static char clock_domain[64],session_id[64];
static char firmware_elf_sha256[65];
static esp_netif_t *wifi_netif;
static bool network_stack_ready,sntp_ready;
static bool wifi_driver_ready,wifi_runtime_started;
static bool wifi_ip_handler_registered,wifi_lost_ip_handler_registered;
static bool wifi_disconnect_handler_registered;
static int64_t session_start_us;
static portMUX_TYPE clock_mux=portMUX_INITIALIZER_UNLOCKED;
static int64_t utc_offset_us;
static portMUX_TYPE location_ref_mux=portMUX_INITIALIZER_UNLOCKED;
static struct {
    bool valid;
    char observation_id[96];
    char event_utc[40];
    char timestamp_quality[64];
} last_trusted_location_ref;
static portMUX_TYPE network_mux=portMUX_INITIALIZER_UNLOCKED;
typedef struct {
    collection_network_state_t state;
    collection_network_route_t route;
    uint32_t generation;
    uint32_t lte_attempt_id;
    esp_netif_t *netif;
} network_runtime_snapshot_t;
static network_runtime_snapshot_t network_runtime={
    .state=COLLECTION_NETWORK_NO_ROUTE,
    .route=COLLECTION_NETWORK_ROUTE_NONE,
};

static int64_t now_us(void) { return esp_timer_get_time(); }
static bool cancel(void *ctx,uint32_t token) { (void)ctx;(void)token; return atomic_load(&stopping); }
static bool upload_cancel(void *ctx,uint32_t generation)
{
    (void)ctx;
    return atomic_load(&stopping)||atomic_load(&network_route_generation)!=generation;
}
/* Cleanup must finish after stop is requested, still within its own deadline. */
static bool cleanup_cancel(void *ctx,uint32_t token) { (void)ctx;(void)token;return false; }
static void publish_network(const collection_network_policy_snapshot_t *snapshot)
{
    network_runtime_snapshot_t next={
        .state=snapshot->state,
        .route=snapshot->route,
        .generation=snapshot->route_generation,
        .lte_attempt_id=snapshot->active_lte_attempt_id,
        .netif=snapshot->route==COLLECTION_NETWORK_ROUTE_WIFI?wifi_netif:
            snapshot->route==COLLECTION_NETWORK_ROUTE_LTE?collection_usb_lte_netif():NULL,
    };
    portENTER_CRITICAL(&network_mux);
    network_runtime=next;
    atomic_store(&network_route_generation,next.generation);
    portEXIT_CRITICAL(&network_mux);
}
static network_runtime_snapshot_t read_network(void)
{
    portENTER_CRITICAL(&network_mux);
    network_runtime_snapshot_t snapshot=network_runtime;
    portEXIT_CRITICAL(&network_mux);
    return snapshot;
}
static bool interface_matches_route(collection_network_route_t route,const char *name)
{
    if(!name)return false;
    size_t length=strlen(name);
    const char *prefix=route==COLLECTION_NETWORK_ROUTE_WIFI?"st":
        route==COLLECTION_NETWORK_ROUTE_LTE?"pp":NULL;
    if(!prefix||length<3||length>5||name[0]!=prefix[0]||name[1]!=prefix[1])return false;
    for(size_t i=2;i<length;i++)if(name[i]<'0'||name[i]>'9')return false;
    return true;
}
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
static bool format_utc_from_monotonic(int64_t mono,char out[40])
{
    portENTER_CRITICAL(&clock_mux);int64_t offset=utc_offset_us;portEXIT_CRITICAL(&clock_mux);
    if(!offset||mono<0)return false;
    int64_t absolute=mono+offset;if(absolute<0)return false;
    time_t sec=absolute/1000000;struct tm value;
    if(!gmtime_r(&sec,&value)||!strftime(out,40,"%Y-%m-%dT%H:%M:%S",&value))return false;
    size_t n=strlen(out);
    return snprintf(out+n,40-n,".%03uZ",(unsigned)(absolute%1000000/1000))>0;
}
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
static unsigned emit(unsigned source,int64_t mono,const char *status,const char *reason,cJSON *payload,bool metadata)
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
        if(q->length && xQueueSend(ingress,&q,0)==pdTRUE) { cJSON_Delete(o);return seq; }
    }
    free(q);cJSON_Delete(o);note_drop(source,seq,bytes,failure);
    return 0U;
}
static bool flash_read(void *ctx,size_t offset,void *out,size_t length)
{ return esp_partition_read(ctx,offset,out,length)==ESP_OK; }
static bool flash_write(void *ctx,size_t offset,const void *data,size_t length)
{ return esp_partition_write(ctx,offset,data,length)==ESP_OK; }
static bool flash_erase(void *ctx,size_t offset,size_t length)
{ return esp_partition_erase_range(ctx,offset,length)==ESP_OK; }
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
#define PHOTO_TIMER_NVS_KEY "photo_timer_v1"
#define PHOTO_JOURNAL_NVS_KEY "photo_cmd_v1"
#define PHOTO_CAPTURE_JOURNAL_NVS_KEY "photo_cap_v1"
#define PHOTO_ACK_SEQUENCE_NVS_KEY "photo_ack_v1"
#define PHOTO_METADATA_ACK_NVS_KEY "photo_meta_v1"
_Static_assert(sizeof(PHOTO_TIMER_NVS_KEY)<=NVS_KEY_NAME_MAX_SIZE,
    "photo timer NVS key exceeds the IDF limit");
_Static_assert(sizeof(PHOTO_JOURNAL_NVS_KEY)<=NVS_KEY_NAME_MAX_SIZE,
    "photo command NVS key exceeds the IDF limit");
_Static_assert(sizeof(PHOTO_CAPTURE_JOURNAL_NVS_KEY)<=NVS_KEY_NAME_MAX_SIZE,
    "photo capture NVS key exceeds the IDF limit");
_Static_assert(sizeof(PHOTO_ACK_SEQUENCE_NVS_KEY)<=NVS_KEY_NAME_MAX_SIZE,
    "photo ACK sequence NVS key exceeds the IDF limit");
_Static_assert(sizeof(PHOTO_METADATA_ACK_NVS_KEY)<=NVS_KEY_NAME_MAX_SIZE,
    "photo metadata ACK NVS key exceeds the IDF limit");
static bool photo_nvs_load(const char *key,uint8_t *blob,size_t capacity,
                           size_t *bytes,bool *missing)
{
    if(!key||!blob||!capacity||!bytes||!missing)return false;
    *bytes=0U;
    *missing=false;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READONLY,&handle);
    if(result!=ESP_OK)return false;
    size_t required=0U;result=nvs_get_blob(handle,key,NULL,&required);
    if(result==ESP_ERR_NVS_NOT_FOUND){*missing=true;nvs_close(handle);return true;}
    if(result!=ESP_OK||!required||required>capacity){nvs_close(handle);return false;}
    result=nvs_get_blob(handle,key,blob,&required);
    nvs_close(handle);
    if(result!=ESP_OK)return false;
    *bytes=required;
    return true;
}
static bool photo_nvs_save(const char *key,const uint8_t *blob,size_t bytes)
{
    if(!key||!blob||!bytes)return false;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READWRITE,&handle);
    if(result!=ESP_OK)return false;
    result=nvs_set_blob(handle,key,blob,bytes);if(result==ESP_OK)result=nvs_commit(handle);
    size_t check_bytes=bytes;
    uint8_t check[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES];
    if(bytes>sizeof(check))result=ESP_ERR_INVALID_SIZE;
    if(result==ESP_OK)result=nvs_get_blob(handle,key,check,&check_bytes);
    nvs_close(handle);
    return result==ESP_OK&&check_bytes==bytes&&memcmp(check,blob,bytes)==0;
}
static bool photo_nvs_load_u32(const char *key,uint32_t *value,bool *missing)
{
    if(!key||!value||!missing)return false;
    *value=0U;*missing=false;nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READONLY,&handle);
    if(result!=ESP_OK)return false;
    result=nvs_get_u32(handle,key,value);nvs_close(handle);
    if(result==ESP_ERR_NVS_NOT_FOUND){*missing=true;*value=0U;return true;}
    return result==ESP_OK;
}
static bool photo_nvs_save_u32(const char *key,uint32_t value)
{
    if(!key)return false;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READWRITE,&handle);
    if(result!=ESP_OK)return false;
    result=nvs_set_u32(handle,key,value);if(result==ESP_OK)result=nvs_commit(handle);
    uint32_t check=0U;if(result==ESP_OK)result=nvs_get_u32(handle,key,&check);
    nvs_close(handle);return result==ESP_OK&&check==value;
}
static bool photo_nvs_load_u64(const char *key,uint64_t *value,bool *missing)
{
    if(!key||!value||!missing)return false;
    *value=0U;*missing=false;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READONLY,&handle);
    if(result!=ESP_OK)return false;
    result=nvs_get_u64(handle,key,value);nvs_close(handle);
    if(result==ESP_ERR_NVS_NOT_FOUND){*missing=true;*value=0U;return true;}
    return result==ESP_OK;
}
static bool photo_nvs_save_u64(const char *key,uint64_t value)
{
    if(!key)return false;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("ego_collection",NVS_READWRITE,&handle);
    if(result!=ESP_OK)return false;
    result=nvs_set_u64(handle,key,value);if(result==ESP_OK)result=nvs_commit(handle);
    uint64_t check=0U;if(result==ESP_OK)result=nvs_get_u64(handle,key,&check);
    nvs_close(handle);return result==ESP_OK&&check==value;
}
static bool save_photo_timer(const photo_control_timer_t *timer)
{
    uint8_t blob[PHOTO_CONTROL_TIMER_BLOB_BYTES];size_t bytes=0U;
    return photo_control_timer_encode(timer,blob,&bytes)&&
        photo_nvs_save(PHOTO_TIMER_NVS_KEY,blob,bytes);
}
static bool save_photo_journal(const photo_control_journal_t *journal)
{
    uint8_t blob[PHOTO_CONTROL_JOURNAL_BLOB_BYTES];size_t bytes=0U;
    return photo_control_journal_encode(journal,blob,&bytes)&&
        photo_nvs_save(PHOTO_JOURNAL_NVS_KEY,blob,bytes);
}
static bool save_photo_capture_journal(
    const photo_control_capture_journal_t *journal)
{
    uint8_t blob[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES];size_t bytes=0U;
    return photo_control_capture_journal_encode(journal,blob,&bytes)&&
        photo_nvs_save(PHOTO_CAPTURE_JOURNAL_NVS_KEY,blob,bytes);
}
static const char *photo_timer_camera_policy_state_reason(void);
static const char *photo_timer_camera_policy_message(void);
static bool photo_timer_camera_policy_rejected(const char *state_reason);
static bool photo_control_state_init(void)
{
    uint8_t blob[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES];size_t bytes=0U;bool missing=false;
    uint32_t ack_sequence=0U;
    uint64_t metadata_ack_watermark=0U;
    photo_control_timer_default(&photo_timer);photo_control_journal_default(&photo_journal);
    photo_control_capture_journal_default(&photo_capture_journal);
    if(!photo_nvs_load(PHOTO_TIMER_NVS_KEY,blob,sizeof(blob),&bytes,&missing)||
       (!missing&&!photo_control_timer_decode(blob,bytes,&photo_timer)))return false;
    if(!photo_nvs_load(PHOTO_JOURNAL_NVS_KEY,blob,sizeof(blob),&bytes,&missing)||
       (!missing&&!photo_control_journal_decode(blob,bytes,&photo_journal)))return false;
    if(!photo_nvs_load(PHOTO_CAPTURE_JOURNAL_NVS_KEY,blob,sizeof(blob),&bytes,&missing)||
       (!missing&&!photo_control_capture_journal_decode(blob,bytes,
           &photo_capture_journal)))return false;
    if(!photo_nvs_load_u32(PHOTO_ACK_SEQUENCE_NVS_KEY,&ack_sequence,&missing))
        return false;
    if(!photo_nvs_load_u64(PHOTO_METADATA_ACK_NVS_KEY,
        &metadata_ack_watermark,&missing))return false;
    /* A gate-policy image may inherit an enabled or terminal-but-unreported
     * enable command from verified firmware. Persistently reject it before
     * publishing control readiness. An explicit disable command remains a
     * valid applied state. Recovery may settle an already-started transaction
     * but cannot take a new frame. */
    const bool inherited_timer_enable=photo_timer.command_id[0]&&
        !photo_timer_camera_policy_rejected(photo_timer.state_reason)&&
        (photo_timer.enabled||(photo_timer.status_report_pending&&
        strcmp(photo_timer.state_reason,"disabled_by_command")));
    if(!platform_camera_timed_capture_allowed()&&inherited_timer_enable){
        photo_timer.enabled=false;photo_timer.schedule_armed=false;
        photo_timer.status_report_pending=true;
        snprintf(photo_timer.state_reason,sizeof(photo_timer.state_reason),
            "%s",photo_timer_camera_policy_state_reason());
        if(!save_photo_timer(&photo_timer))return false;
        if(photo_journal.kind==PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER&&
           !strcmp(photo_journal.cmd_id,photo_timer.command_id)){
            photo_journal.phase=PHOTO_CONTROL_JOURNAL_COMPLETE;
            snprintf(photo_journal.status,sizeof(photo_journal.status),
                "%s","error");
            snprintf(photo_journal.message,sizeof(photo_journal.message),
                "%s",photo_timer_camera_policy_message());
            if(!save_photo_journal(&photo_journal))return false;
        }
    }
    atomic_store(&photo_command_ack_sequence,ack_sequence);
    photo_metadata_ack_watermark=metadata_ack_watermark;
    return true;
}
static void photo_timer_snapshot(photo_control_timer_t *out)
{
    portENTER_CRITICAL(&photo_state_mux);*out=photo_timer;portEXIT_CRITICAL(&photo_state_mux);
}
static void photo_timer_publish(const photo_control_timer_t *value)
{
    portENTER_CRITICAL(&photo_state_mux);photo_timer=*value;portEXIT_CRITICAL(&photo_state_mux);
}
static void photo_journal_snapshot(photo_control_journal_t *out)
{
    portENTER_CRITICAL(&photo_state_mux);*out=photo_journal;portEXIT_CRITICAL(&photo_state_mux);
}
static void photo_journal_publish(const photo_control_journal_t *value)
{
    portENTER_CRITICAL(&photo_state_mux);photo_journal=*value;portEXIT_CRITICAL(&photo_state_mux);
}
static void photo_capture_journal_snapshot(photo_control_capture_journal_t *out)
{
    portENTER_CRITICAL(&photo_state_mux);*out=photo_capture_journal;
    portEXIT_CRITICAL(&photo_state_mux);
}
static void photo_capture_journal_publish(
    const photo_control_capture_journal_t *value)
{
    portENTER_CRITICAL(&photo_state_mux);photo_capture_journal=*value;
    portEXIT_CRITICAL(&photo_state_mux);
}
static bool photo_next_ack_sequence(uint32_t *sequence)
{
    if(!sequence)return false;
    uint32_t current=atomic_load(&photo_command_ack_sequence);
    if(current==UINT32_MAX)return false;
    uint32_t next=current+1U;
    if(!photo_nvs_save_u32(PHOTO_ACK_SEQUENCE_NVS_KEY,next))return false;
    atomic_store(&photo_command_ack_sequence,next);*sequence=next;return true;
}
static bool photo_record_metadata_acked(uint64_t source_sequence)
{
    if(!source_sequence||source_sequence<=photo_metadata_ack_watermark)return true;
    if(!photo_nvs_save_u64(PHOTO_METADATA_ACK_NVS_KEY,source_sequence))return false;
    photo_metadata_ack_watermark=source_sequence;
    return true;
}
static bool photo_wall_clock(uint64_t *utc_ms)
{
    if(!utc_ms)return false;
    portENTER_CRITICAL(&clock_mux);bool anchored=utc_offset_us!=0;portEXIT_CRITICAL(&clock_mux);
    struct timeval value;
    if(!anchored||gettimeofday(&value,NULL)!=0||value.tv_sec<1767225600||
       value.tv_sec>=4102444800LL)return false;
    *utc_ms=(uint64_t)value.tv_sec*1000U+(uint64_t)value.tv_usec/1000U;return true;
}
static bool photo_format_utc_ms(uint64_t utc_ms,char out[40])
{
    time_t seconds=(time_t)(utc_ms/1000U);struct tm value;
    if(!gmtime_r(&seconds,&value)||!strftime(out,40,"%Y-%m-%dT%H:%M:%S",&value))return false;
    size_t n=strlen(out);
    return snprintf(out+n,40-n,".%03uZ",(unsigned)(utc_ms%1000U))>0;
}
static void photo_digest_hex(const uint8_t digest[PHOTO_MEDIA_STORE_SHA256_BYTES],char out[65])
{
    static const char digits[]="0123456789abcdef";
    for(size_t i=0U;i<PHOTO_MEDIA_STORE_SHA256_BYTES;++i){
        out[i*2U]=digits[digest[i]>>4U];out[i*2U+1U]=digits[digest[i]&15U];
    }
    out[64]='\0';
}
static bool photo_make_id(const char *prefix,const char *identity,uint32_t ordinal,
                          char out[96])
{
    if(!prefix||!identity||!out)return false;
    uint8_t digest[32];
    char material[320];
    int n=snprintf(material,sizeof(material),"%s|%s|%" PRIu32,prefix,identity,ordinal);
    if(n<=0||(size_t)n>=sizeof(material)||mbedtls_sha256((const unsigned char*)material,
        (size_t)n,digest,0)!=0)return false;
    char hex[65];photo_digest_hex(digest,hex);
    n=snprintf(out,96,"%s-%.32s-n%" PRIu32,prefix,hex,ordinal);
    return n>0&&(size_t)n<96U;
}

typedef struct {
    photo_control_command_kind_t kind;
    char photo_id[96];
    char trigger_reason[24];
    char command_id[PHOTO_CONTROL_ID_BYTES];
    char config_version[PHOTO_CONTROL_ID_BYTES];
    char authorization_session_id[PHOTO_CONTROL_ID_BYTES];
    char retention_expires_at[PHOTO_CONTROL_TIME_TEXT_BYTES];
    char camera_shared_i2c_state[PHOTO_CONTROL_CAPTURE_CAMERA_STATE_BYTES];
    char camera_driver_profile[PHOTO_CONTROL_CAPTURE_DRIVER_PROFILE_BYTES];
    char runtime_config_id[PHOTO_CONTROL_CAPTURE_RUNTIME_CONFIG_BYTES];
    char capture_fw_version[PHOTO_CONTROL_CAPTURE_FW_VERSION_BYTES];
    char capture_firmware_elf_sha256[
        PHOTO_CONTROL_CAPTURE_ELF_SHA256_BYTES];
    uint64_t execution_expires_at_unix_ms;
    uint64_t retention_expires_at_unix_ms;
    uint64_t source_event_utc_ms;
    uint64_t source_event_monotonic_ns;
    uint32_t capture_boot_count;
    uint32_t capture_sequence_id;
    uint32_t timer_captured_count_before;
} photo_capture_intent_t;

typedef struct {
    photo_capture_intent_t intent;
    photo_media_store_record_t record;
    platform_camera_capture_result_t camera;
    uint64_t anchor_utc_ms;
    int64_t anchor_monotonic_us;
    uint64_t event_utc_ms;
    uint64_t event_monotonic_ns;
    bool media_saved;
    bool existing_media;
    bool outcome_ambiguous;
    photo_media_store_result_t store_result;
    const char *failure_reason;
} photo_capture_outcome_t;

static bool photo_camera_manual_capture_ready(
    platform_camera_status_t status)
{
    return status==PLATFORM_CAMERA_OK||
        status==PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED;
}

static const char *photo_camera_driver_profile(
    platform_camera_shared_i2c_state_t state,const char *persisted_profile)
{
    if(persisted_profile&&persisted_profile[0])return persisted_profile;
    switch(state){
    case PLATFORM_CAMERA_SHARED_I2C_UNKNOWN_LEGACY:
        return "qvga-jpeg-q12-v1-shared-i2c-unknown_legacy";
    case PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED:
        return "qvga-jpeg-q12-v1-shared-i2c-trial_unverified";
    case PLATFORM_CAMERA_SHARED_I2C_VERIFIED:
        return "qvga-jpeg-q12-v1-shared-i2c-verified";
    case PLATFORM_CAMERA_SHARED_I2C_BLOCKED:
    default:
        return "qvga-jpeg-q12-v1-shared-i2c-blocked";
    }
}

static platform_camera_shared_i2c_state_t
photo_camera_shared_i2c_state_from_name(const char *state)
{
    if(state&&!strcmp(state,"verified"))
        return PLATFORM_CAMERA_SHARED_I2C_VERIFIED;
    if(state&&!strcmp(state,"trial_unverified"))
        return PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED;
    if(state&&!strcmp(state,"blocked"))
        return PLATFORM_CAMERA_SHARED_I2C_BLOCKED;
    return PLATFORM_CAMERA_SHARED_I2C_UNKNOWN_LEGACY;
}

static const char *photo_timer_camera_policy_state_reason(void)
{
    switch(platform_camera_shared_i2c_state()){
    case PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED:
        return "camera_trial_manual_only";
    case PLATFORM_CAMERA_SHARED_I2C_BLOCKED:
        return "camera_shared_i2c_blocked";
    default:
        return "camera_runtime_unavailable";
    }
}

static const char *photo_timer_camera_policy_message(void)
{
    return platform_camera_shared_i2c_state()==
        PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED?
        "camera_unverified_trial_manual_only":"camera_shared_i2c_blocked";
}

static bool photo_timer_camera_policy_rejected(const char *state_reason)
{
    return state_reason&&
        (!strcmp(state_reason,"camera_trial_manual_only")||
         !strcmp(state_reason,"camera_shared_i2c_blocked"));
}

static const char *photo_timer_camera_policy_message_for_reason(
    const char *state_reason)
{
    return state_reason&&!strcmp(state_reason,"camera_trial_manual_only")?
        "camera_unverified_trial_manual_only":"camera_shared_i2c_blocked";
}

static bool photo_timer_enforce_camera_policy(
    photo_control_timer_t *timer)
{
    if(!timer||platform_camera_timed_capture_allowed())return false;
    timer->enabled=false;timer->schedule_armed=false;
    timer->status_report_pending=true;
    snprintf(timer->state_reason,sizeof(timer->state_reason),"%s",
        photo_timer_camera_policy_state_reason());
    return true;
}

static bool photo_store_result_fatal(photo_media_store_result_t result)
{
    return result==PHOTO_MEDIA_STORE_IO_ERROR||
        result==PHOTO_MEDIA_STORE_CORRUPT;
}

static void photo_store_observe_result(photo_media_store_result_t result)
{
    if(photo_store_result_fatal(result))atomic_store(&media_store_ready,false);
}

/* photo_media_store deliberately has no internal synchronization.  Keep every
 * call behind this one owner-layer mutex; in particular, health() runs on the
 * main task while capture/recovery/delivery run on the uploader task. */
static bool photo_media_lock(void)
{
    return media_store_mutex&&
        xSemaphoreTake(media_store_mutex,portMAX_DELAY)==pdTRUE;
}

static void photo_media_unlock(void)
{
    xSemaphoreGive(media_store_mutex);
}

static photo_media_store_result_t photo_media_init_locked(
    const photo_media_store_config_t *config,photo_media_store_stats_t *stats)
{
    if(!photo_media_lock())return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_init(&media_store,config);
    if(stats)photo_media_store_get_stats(&media_store,stats);
    photo_media_unlock();
    return result;
}

static bool photo_media_stats_locked(photo_media_store_stats_t *stats)
{
    if(!stats||!photo_media_lock())return false;
    photo_media_store_get_stats(&media_store,stats);
    photo_media_unlock();
    return true;
}

static photo_media_store_result_t photo_media_find_locked(
    const char *photo_id,photo_media_store_record_t *record)
{
    if(!photo_media_lock())return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_find(&media_store,
        photo_id,record);
    photo_media_unlock();
    return result;
}

static photo_media_store_result_t photo_media_peek_locked(
    uint32_t start_slot,photo_media_store_record_t *record)
{
    if(!photo_media_lock())return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_peek_committed(
        &media_store,start_slot,record);
    photo_media_unlock();
    return result;
}

static photo_media_store_result_t photo_media_read_locked(
    const photo_media_store_record_t *record,size_t offset,void *output,
    size_t length)
{
    if(!photo_media_lock())return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_read(&media_store,
        record,offset,output,length);
    photo_media_unlock();
    return result;
}

static photo_media_store_result_t photo_media_release_locked(
    const photo_media_store_record_t *record)
{
    if(!photo_media_lock())return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_release(&media_store,
        record);
    photo_media_unlock();
    return result;
}

static photo_media_store_result_t photo_media_capture_store_locked(
    photo_capture_outcome_t *outcome,const uint8_t *jpeg,size_t jpeg_bytes,
    const platform_camera_capture_result_t *metadata,bool *prepared)
{
    if(prepared)*prepared=false;
    if(!outcome||!jpeg||!metadata||!photo_media_lock())
        return PHOTO_MEDIA_STORE_IO_ERROR;
    photo_media_store_result_t result=photo_media_store_prepare_with_expiry(
        &media_store,outcome->intent.photo_id,jpeg_bytes,metadata->sha256,
        outcome->intent.retention_expires_at_unix_ms,outcome->event_utc_ms,
        outcome->event_monotonic_ns,outcome->intent.capture_boot_count,
        outcome->intent.capture_sequence_id,metadata->width,metadata->height,
        &outcome->record);
    if(result==PHOTO_MEDIA_STORE_OK){
        if(prepared)*prepared=true;
        result=photo_media_store_write(&media_store,&outcome->record,0U,jpeg,
            jpeg_bytes);
        if(result==PHOTO_MEDIA_STORE_OK)
            result=photo_media_store_commit(&media_store,&outcome->record);
    }
    photo_media_unlock();
    return result;
}

static void photo_stack_hwm_observe(atomic_uint *minimum_bytes)
{
    if(!minimum_bytes)return;
    const unsigned current=(unsigned)uxTaskGetStackHighWaterMark2(NULL)*
        (unsigned)sizeof(StackType_t);
    unsigned previous=atomic_load(minimum_bytes);
    while(current<previous&&
          !atomic_compare_exchange_weak(minimum_bytes,&previous,current)){}
}

static void photo_add_stack_hwm(cJSON *object,const char *name,
                                const atomic_uint *minimum_bytes)
{
    const unsigned value=atomic_load(minimum_bytes);
    if(value==UINT_MAX)cJSON_AddNullToObject(object,name);
    else cJSON_AddNumberToObject(object,name,value);
}

static bool photo_append_direct_frame(unsigned source,const char *frame,
                                      size_t length,uint32_t capture_boot_count,
                                      uint32_t capture_sequence_id)
{
    if(!frame||!length||length>COLLECTION_FRAME_CAPACITY||
       !capture_boot_count||!capture_sequence_id||source>=SOURCE_COUNT)return false;
    collection_spool_result_t result=COLLECTION_SPOOL_IO_ERROR;
    xSemaphoreTake(spool_mutex,portMAX_DELAY);
    if(atomic_load(&spool_ready)){
        result=collection_spool_append(&spool,COLLECTION_SPOOL_METADATA,source,
            ((uint64_t)capture_boot_count<<32U)|capture_sequence_id,
            frame,length,NULL);
    }
    if(result==COLLECTION_SPOOL_IO_ERROR||result==COLLECTION_SPOOL_CORRUPT||
       result==COLLECTION_SPOOL_FOREIGN_DATA)atomic_store(&spool_ready,false);
    xSemaphoreGive(spool_mutex);
    if(result==COLLECTION_SPOOL_OK){
        atomic_fetch_add(&generated_bytes[source],(unsigned)length);
        atomic_fetch_add(&persisted,1U);
        return true;
    }
    /* The capture RESULT journal remains the durable source for this exact
     * observation, so a failed append is pending work rather than a dropped
     * record.  Counting every recovery attempt as loss creates false gaps and
     * can itself flood the protected lane with loss summaries. */
    atomic_fetch_add(&photo_metadata_persist_retries,1U);
    ESP_LOGE(TAG,"PHOTO_DIRECT_RECORD source=%s durable=false result=%s retry_pending=true",
        sources[source],collection_spool_result_name(result));
    return false;
}

static bool photo_append_metadata_frame(const char *frame,size_t length,
                                        uint32_t capture_boot_count,
                                        uint32_t capture_sequence_id)
{
    return photo_append_direct_frame(CAMERA,frame,length,capture_boot_count,
        capture_sequence_id);
}

static cJSON *photo_source_status_payload(const char *event_reason,
                                          bool *runtime_ready,
                                          const char **missing_reason)
{
    photo_control_timer_t timer;photo_timer_snapshot(&timer);
    uint64_t utc_ms=0U;const bool trusted_utc=photo_wall_clock(&utc_ms);
    char utc[40]={0};
    const bool utc_formatted=trusted_utc&&photo_format_utc_ms(utc_ms,utc);
    const char *camera_reason=NULL;
    const platform_camera_status_t camera_status=platform_camera_preflight(&camera_reason);
    const bool manual_chain_ready=atomic_load(&photo_control_state_ready)&&
        atomic_load(&media_store_ready)&&
        photo_camera_manual_capture_ready(camera_status);
    const bool verified_ready=atomic_load(&photo_control_state_ready)&&
        atomic_load(&media_store_ready)&&camera_status==PLATFORM_CAMERA_OK;
    cJSON *payload=cJSON_CreateObject();
    if(!payload)return NULL;
    cJSON_AddStringToObject(payload,"source","camera");
    cJSON_AddStringToObject(payload,"component","photo_control");
    cJSON_AddBoolToObject(payload,"camera_runtime_compiled",true);
    cJSON_AddBoolToObject(payload,"driver_preflight_ready",
        camera_status==PLATFORM_CAMERA_OK);
    cJSON_AddBoolToObject(payload,"capture_trigger_wired",manual_chain_ready);
    cJSON_AddBoolToObject(payload,"media_store_ready",atomic_load(&media_store_ready));
    if(timer.command_id[0])cJSON_AddStringToObject(payload,"command_id",timer.command_id);
    else cJSON_AddNullToObject(payload,"command_id");
    if(timer.authorization_session_id[0])
        cJSON_AddStringToObject(payload,"authorization_session_id",timer.authorization_session_id);
    else cJSON_AddNullToObject(payload,"authorization_session_id");
    if(utc_formatted)cJSON_AddStringToObject(payload,"source_event_utc",utc);
    else cJSON_AddNullToObject(payload,"source_event_utc");
    cJSON_AddNumberToObject(payload,"source_event_monotonic_ms",now_us()/1000);
    cJSON_AddStringToObject(payload,"event_reason",event_reason?event_reason:"periodic_state");
    cJSON *state=cJSON_AddObjectToObject(payload,"timer_state");
    if(timer.config_version[0])cJSON_AddStringToObject(state,"config_version",timer.config_version);
    else cJSON_AddNullToObject(state,"config_version");
    cJSON_AddBoolToObject(state,"enabled",timer.enabled);
    cJSON_AddNumberToObject(state,"interval_seconds",timer.interval_seconds);
    cJSON_AddNumberToObject(state,"session_expires_at_unix_ms",
        (double)timer.session_expires_at_unix_ms);
    cJSON_AddNumberToObject(state,"max_photos",timer.max_photos);
    cJSON_AddNumberToObject(state,"captured_count",timer.captured_photos);
    cJSON_AddStringToObject(state,"state_reason",
        timer.state_reason[0]?timer.state_reason:"not_configured");
    cJSON_AddBoolToObject(state,"trusted_utc",trusted_utc);
    if(runtime_ready)*runtime_ready=verified_ready;
    if(missing_reason)*missing_reason=
        !atomic_load(&photo_control_state_ready)?"photo_control_state_unavailable":
        !atomic_load(&media_store_ready)?"photo_media_store_unavailable":camera_reason;
    return payload;
}

static void photo_emit_source_status(const char *event_reason)
{
    bool ready=false;const char *reason=NULL;
    cJSON *payload=photo_source_status_payload(event_reason,&ready,&reason);
    emit(SOURCE_STATUS,now_us(),ready?"observed":"unavailable",ready?NULL:reason,
        payload,true);
}

static bool photo_frame_to_media(void *opaque,const uint8_t *jpeg,size_t jpeg_bytes,
                                 const platform_camera_capture_result_t *metadata)
{
    photo_capture_outcome_t *outcome=opaque;
    if(!outcome||!jpeg||!metadata)return false;
    if(!atomic_load(&media_store_ready)){
        outcome->failure_reason="photo_media_store_unavailable";
        return false;
    }
    if(metadata->width==0U||metadata->height==0U){
        outcome->store_result=PHOTO_MEDIA_STORE_BAD_ARGUMENT;
        outcome->failure_reason="camera_frame_dimensions_invalid";
        return false;
    }
    if(jpeg_bytes>CONFIG_EGOLINK_PHOTO_MEDIA_MAX_PAYLOAD_BYTES){
        outcome->store_result=PHOTO_MEDIA_STORE_TOO_LARGE;
        outcome->failure_reason="jpeg_exceeds_configured_media_payload_limit";
        return false;
    }
    /* The consumer is invoked only after esp_camera_fb_get returned a real
     * frame. Anchor authorization to that point, not to driver init start. */
    int64_t delta_us=now_us()-outcome->anchor_monotonic_us;
    outcome->event_utc_ms=outcome->anchor_utc_ms+
        (uint64_t)(delta_us>0?delta_us/1000LL:0LL);
    outcome->event_monotonic_ns=(uint64_t)now_us()*1000U;
    if(outcome->event_utc_ms>=outcome->intent.execution_expires_at_unix_ms){
        outcome->store_result=PHOTO_MEDIA_STORE_BAD_ARGUMENT;
        outcome->failure_reason="capture_started_after_authorized_window";
        return false;
    }
    if(outcome->event_utc_ms>=outcome->intent.retention_expires_at_unix_ms){
        outcome->store_result=PHOTO_MEDIA_STORE_BAD_ARGUMENT;
        outcome->failure_reason="capture_started_after_retention_expiry";
        return false;
    }
    bool prepared=false;
    outcome->store_result=photo_media_capture_store_locked(outcome,jpeg,
        jpeg_bytes,metadata,&prepared);
    photo_store_observe_result(outcome->store_result);
    if(!prepared){
        outcome->failure_reason=photo_media_store_result_name(outcome->store_result);
        return false;
    }
    outcome->media_saved=outcome->store_result==PHOTO_MEDIA_STORE_OK||
        outcome->store_result==PHOTO_MEDIA_STORE_ALREADY_COMMITTED;
    if(!outcome->media_saved)
        outcome->failure_reason=photo_media_store_result_name(outcome->store_result);
    return outcome->media_saved;
}

static bool photo_append_capture_metadata(photo_capture_outcome_t *outcome,
                                          const char *failure_reason)
{
    char event_utc[40],digest[65],capture_clock_domain[64];
    char frame[COLLECTION_FRAME_CAPACITY];
    if(!outcome||!outcome->event_utc_ms||
       !photo_format_utc_ms(outcome->event_utc_ms,event_utc))return false;
    const bool saved=outcome->media_saved;
    if(saved)photo_digest_hex(outcome->record.sha256,digest);
    const uint32_t capture_boot_count=saved?outcome->record.capture_boot_count:
        outcome->intent.capture_boot_count;
    if(snprintf(capture_clock_domain,sizeof(capture_clock_domain),
        "collection-esp-timer-b%" PRIu32,capture_boot_count)<=0)return false;
    photo_delivery_metadata_t metadata={
        .device_id=CONFIG_EGOLINK_DEVICE_ID,.photo_id=outcome->intent.photo_id,
        .trigger_reason=outcome->intent.trigger_reason,
        .command_id=outcome->intent.command_id,
        .config_version=outcome->intent.config_version,
        .capture_result=saved?"captured":
            (outcome->outcome_ambiguous?"outcome_unknown":
            (outcome->camera.frame_acquired?"captured":
             (outcome->camera.attempted?"capture_failed":"not_attempted"))),
        .local_save_status=saved?"saved":
            (outcome->outcome_ambiguous?"unknown":
             (outcome->camera.frame_acquired?"save_failed":"not_attempted")),
        .device_upload_status=saved?"pending":"not_ready",
        .media_type=saved?"image/jpeg":NULL,
        .width=saved?outcome->record.width:0U,
        .height=saved?outcome->record.height:0U,
        .byte_length=saved?outcome->record.payload_bytes:0U,
        .sha256_hex=saved?digest:NULL,
        .storage_kind=saved?"persistent":"none",
        .camera_model=saved?"OV5640":"unknown",
        .driver_profile=photo_camera_driver_profile(
            outcome->camera.shared_i2c_state,
            outcome->intent.camera_driver_profile),
        .authorization_session_id=outcome->intent.authorization_session_id,
        .retention_expires_at=outcome->intent.retention_expires_at,
        .failure_reason=saved?NULL:(outcome->outcome_ambiguous?
            "capture_outcome_unknown_after_reboot":
            (failure_reason?failure_reason:"capture_failed")),
        .capture_boot_count=capture_boot_count,
        .capture_sequence_id=saved?outcome->record.capture_sequence_id:
            outcome->intent.capture_sequence_id,
        .capture_monotonic_ns=saved?outcome->record.capture_monotonic_ns:
            outcome->event_monotonic_ns,
        .capture_event_utc=event_utc,
        .timestamp_source="sntp_anchor",
        .timestamp_quality="network_time_unverified_accuracy",
        .monotonic_clock_domain_id=capture_clock_domain,
        .fw_version=outcome->intent.capture_fw_version,
        .firmware_elf_sha256=outcome->intent.capture_firmware_elf_sha256,
        .runtime_config_id=outcome->intent.runtime_config_id,
    };
    size_t frame_bytes=0U;
    return photo_delivery_build_metadata_frame(&metadata,frame,sizeof(frame),
        &frame_bytes)&&photo_append_metadata_frame(frame,frame_bytes,
            metadata.capture_boot_count,metadata.capture_sequence_id);
}

static bool photo_execute_capture(const photo_capture_intent_t *intent,
                                  bool allow_new_capture,
                                  photo_capture_outcome_t *outcome)
{
    if(!intent||!outcome)return false;
    memset(outcome,0,sizeof(*outcome));outcome->intent=*intent;
    outcome->camera.shared_i2c_state=platform_camera_shared_i2c_state();
    if(!photo_wall_clock(&outcome->anchor_utc_ms)){
        outcome->failure_reason="trusted_utc_unavailable";
        return false;
    }
    outcome->anchor_monotonic_us=now_us();
    outcome->event_utc_ms=intent->source_event_utc_ms;
    outcome->event_monotonic_ns=intent->source_event_monotonic_ns;
    if(!atomic_load(&media_store_ready)){
        outcome->failure_reason="photo_media_store_unavailable";
        return false;
    }
    outcome->store_result=photo_media_find_locked(intent->photo_id,
        &outcome->record);
    photo_store_observe_result(outcome->store_result);
    if(outcome->store_result==PHOTO_MEDIA_STORE_OK){
        if(outcome->record.capture_unix_ms>=intent->execution_expires_at_unix_ms||
           outcome->record.capture_unix_ms>=intent->retention_expires_at_unix_ms){
            outcome->failure_reason="persisted_capture_outside_authorized_window";
            return false;
        }
        outcome->media_saved=true;outcome->existing_media=true;
        outcome->event_utc_ms=outcome->record.capture_unix_ms;
        outcome->event_monotonic_ns=outcome->record.capture_monotonic_ns;
        return true;
    }
    if(outcome->store_result!=PHOTO_MEDIA_STORE_NOT_FOUND){
        outcome->failure_reason=photo_media_store_result_name(outcome->store_result);
        return false;
    }
    if(!allow_new_capture){
        outcome->failure_reason="capture_outcome_unknown_after_restart";
        return false;
    }
    if(outcome->anchor_utc_ms>=intent->execution_expires_at_unix_ms){
        outcome->failure_reason="capture_authorization_expired_before_start";
        return false;
    }
    if(outcome->anchor_utc_ms>=intent->retention_expires_at_unix_ms){
        outcome->failure_reason="photo_retention_expired_before_start";
        return false;
    }
    atomic_fetch_add(&photo_capture_attempts,1U);
    const platform_camera_status_t result=platform_camera_capture_single(
        photo_frame_to_media,outcome,&outcome->camera);
    if(outcome->media_saved){
        atomic_fetch_add(&photo_capture_saved,1U);
        if(result!=PLATFORM_CAMERA_OK)
            ESP_LOGW(TAG,"PHOTO_CAPTURE media_saved=true lifecycle=%s reason=%s",
                platform_camera_status_name(result),
                outcome->camera.reason?outcome->camera.reason:"none");
        return true;
    }
    atomic_fetch_add(&photo_capture_failures,1U);
    if(!outcome->event_utc_ms)outcome->event_utc_ms=outcome->anchor_utc_ms;
    if(outcome->camera.capture_started_us>0)
        outcome->event_monotonic_ns=(uint64_t)outcome->camera.capture_started_us*1000U;
    if(!outcome->failure_reason)outcome->failure_reason=outcome->camera.reason;
    return false;
}

static void photo_journal_fill(photo_control_journal_t *journal,
                               photo_control_journal_phase_t phase,
                               photo_control_command_kind_t kind,
                               const char *cmd_id,const char *status,
                               const char *message,const char *photo_id)
{
    memset(journal,0,sizeof(*journal));journal->phase=phase;journal->kind=kind;
    snprintf(journal->cmd_id,sizeof(journal->cmd_id),"%s",cmd_id);
    snprintf(journal->status,sizeof(journal->status),"%s",status);
    snprintf(journal->message,sizeof(journal->message),"%s",message);
    snprintf(journal->photo_id,sizeof(journal->photo_id),"%s",
        photo_id&&*photo_id?photo_id:"none");
}
#endif
static void storage_task(void *unused)
{
    (void)unused;queued_t *q;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_store_stack_hwm_bytes);
#endif
    while(!atomic_load(&stopping)||!atomic_load(&main_finished)||!atomic_load(&imu_finished)||!atomic_load(&modem_finished)||!atomic_load(&uploader_finished)||uxQueueMessagesWaiting(ingress)) {
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_stack_hwm_observe(&photo_store_stack_hwm_bytes);
#endif
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
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_store_stack_hwm_bytes);
#endif
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
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_imu_stack_hwm_bytes);
#endif
    bool running=platform_imu_init() && platform_imu_capture_begin();
    source_status(IMU,running?"running":"unavailable",running?NULL:"qmi8658_probe_or_start_failed");
    uint8_t binary[20*16];unsigned count=0,failures=0,missed=0;int64_t first=0;
    TickType_t tick=xTaskGetTickCount();
    while(running && !atomic_load(&stopping)) {
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_stack_hwm_observe(&photo_imu_stack_hwm_bytes);
#endif
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
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_imu_stack_hwm_bytes);
#endif
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

static collection_network_policy_snapshot_t policy_event(
    collection_network_policy_t *policy,collection_network_event_type_t type,
    uint64_t now,uint32_t attempt)
{
    collection_network_policy_event_t event={.type=type,.now_ms=now,.lte_attempt_id=attempt};
    collection_network_policy_snapshot_t snapshot=collection_network_policy_handle(policy,&event);
    publish_network(&snapshot);
    return snapshot;
}

#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
static collection_network_connector_result_t lte_connector_result(
    collection_usb_lte_result_t result)
{
    if(result==COLLECTION_USB_LTE_PENDING)return COLLECTION_NETWORK_CONNECTOR_PENDING;
    if(result==COLLECTION_USB_LTE_OK)return COLLECTION_NETWORK_CONNECTOR_OK;
    if(result==COLLECTION_USB_LTE_DISCONNECTED)return COLLECTION_NETWORK_CONNECTOR_DISCONNECTED;
    if(result==COLLECTION_USB_LTE_TIMEOUT)return COLLECTION_NETWORK_CONNECTOR_TIMEOUT;
    if(result==COLLECTION_USB_LTE_IO_ERROR)return COLLECTION_NETWORK_CONNECTOR_IO_ERROR;
    if(result==COLLECTION_USB_LTE_OVERFLOW)return COLLECTION_NETWORK_CONNECTOR_OVERFLOW;
    if(result==COLLECTION_USB_LTE_STALE_EPOCH)return COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH;
    return COLLECTION_NETWORK_CONNECTOR_FAILED;
}
static collection_usb_lte_operation_t lte_connector_operation(
    collection_network_connector_operation_t operation)
{
    switch(operation) {
        case COLLECTION_NETWORK_CONNECTOR_PROBE:return COLLECTION_USB_LTE_PROBE;
        case COLLECTION_NETWORK_CONNECTOR_ECHO_OFF:return COLLECTION_USB_LTE_ECHO_OFF;
        case COLLECTION_NETWORK_CONNECTOR_DIAL:return COLLECTION_USB_LTE_DIAL;
        case COLLECTION_NETWORK_CONNECTOR_ESCAPE:return COLLECTION_USB_LTE_ESCAPE;
        case COLLECTION_NETWORK_CONNECTOR_HANGUP:return COLLECTION_USB_LTE_HANGUP;
    }
    return COLLECTION_USB_LTE_PROBE;
}
static collection_network_connector_result_t lte_connector_begin(
    void *context,collection_network_connector_operation_t operation,
    uint32_t timeout_ms,uint32_t expected_epoch)
{
    (void)context;
    return lte_connector_result(collection_usb_lte_begin_for_epoch(
        lte_connector_operation(operation),timeout_ms,expected_epoch));
}
static collection_network_connector_result_t lte_connector_poll(
    void *context,uint32_t expected_epoch)
{
    (void)context;return lte_connector_result(
        collection_usb_lte_poll_for_epoch(expected_epoch));
}
static collection_network_connector_result_t lte_connector_cancel_poll(
    void *context,uint32_t expected_epoch)
{
    (void)context;return lte_connector_result(
        collection_usb_lte_cancel_poll_for_epoch(expected_epoch));
}
static collection_network_connector_result_t lte_connector_quiesce(
    void *context,uint32_t expected_epoch)
{
    (void)context;return lte_connector_result(
        collection_usb_lte_quiesce_for_epoch(expected_epoch));
}
static void lte_connector_status(
    void *context,collection_network_connector_status_t *out)
{
    (void)context;collection_usb_lte_status_t status;collection_usb_lte_get_status(&status);
    *out=(collection_network_connector_status_t){
        .usb_connected=status.usb_connected,.data_mode=status.data_mode,
        .ppp_has_ip=status.ppp_has_ip,.ppp_stopped=status.ppp_stopped,
        .hangup_confirmed=status.hangup_confirmed,
        .connection_epoch=status.connection_epoch,
        .result=lte_connector_result(status.result),
    };
}
static collection_network_retirement_facts_t lte_retirement(void)
{
    return (collection_network_retirement_facts_t){
        .published_generation=atomic_load(&network_route_generation),
        .uploader_active_generation=atomic_load(&uploader_active_generation),
        .uploader_retired_generation=atomic_load(&uploader_retired_generation),
    };
}
static void sync_lte_facts(const collection_network_coordinator_t *control)
{
    collection_network_coordinator_snapshot_t facts=collection_network_coordinator_snapshot(control);
    atomic_store(&lte_ppp_stopped,facts.ppp_stopped);
    atomic_store(&lte_hangup_required,facts.hangup_required);
    atomic_store(&lte_hangup_confirmed,facts.hangup_confirmed);
    atomic_store(&lte_cleanup_confirmed,facts.cleanup_confirmed);
}
static void lte_apply_policy_result(
    collection_network_policy_t *policy,collection_network_coordinator_t *control,
    collection_network_policy_snapshot_t snapshot,uint64_t now)
{
    collection_network_retirement_facts_t retirement=lte_retirement();
    collection_network_coordinator_notice_t notice=collection_network_coordinator_apply_policy(
        control,&snapshot,&retirement,now);
    sync_lte_facts(control);
    for(unsigned i=0;notice.valid&&i<3;i++) {
        snapshot=policy_event(policy,notice.type,now,notice.attempt_id);
        retirement=lte_retirement();
        notice=collection_network_coordinator_apply_policy(control,&snapshot,&retirement,now);
        sync_lte_facts(control);
    }
}
#endif
static void modem_task(void *unused)
{
    (void)unused;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_modem_stack_hwm_bytes);
#endif
    bool uart_ready=sim7670_at_backend_init_exclusive_current_task()==ESP_OK;
    if(!uart_ready){source_status(GNSS,"error","exclusive_modem_init_failed");source_status(LTE,"error","exclusive_modem_init_failed");}
    uint32_t operation=1;bool powered=false;
    if(uart_ready) {
        /* MCU reset does not reset the modem. Record actual GNSS cleanup before
         * acquisition; this is independent from the USB PPP data interface. */
        trace_t initial={.at=cJSON_CreateArray()};sim7670_location_bounded_result_t initial_result;
        sim7670_location_bounded_request_t initial_request={.timeout_ms=2000,.per_command_timeout_cap_ms=1500,.operation_token=operation++,.cancel_requested=cleanup_cancel,.trace_at=trace_at,.trace_context=&initial};
        sim7670_gnss_power_off_bounded(&initial_request,&initial_result);
        cJSON *initial_payload=cJSON_CreateObject();cJSON_AddItemToObject(initial_payload,"at",initial.at);
        cJSON_AddStringToObject(initial_payload,"phase","session_start_cleanup");
        cJSON_AddNumberToObject(initial_payload,"reason",initial_result.reason);
        emit(GNSS,now_us(),query_status(&initial_result),initial_result.reason?"initial_power_state_unconfirmed":NULL,initial_payload,false);
    }

    bool usb_ready=false;
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
    collection_network_coordinator_t lte_control={0};
    collection_network_connector_ops_t lte_connector={
        .begin=lte_connector_begin,.poll=lte_connector_poll,
        .cancel_poll=lte_connector_cancel_poll,.quiesce=lte_connector_quiesce,
        .get_status=lte_connector_status,
    };
    collection_network_coordinator_config_t lte_coordinator_config={
        .command_timeout_ms=CONFIG_EGOLINK_COLLECTION_LTE_COMMAND_TIMEOUT_MS,
        .cleanup_timeout_ms=CONFIG_EGOLINK_COLLECTION_LTE_CLEANUP_TIMEOUT_MS,
    };
    bool lte_coordinator_ready=collection_network_coordinator_init(
        &lte_control,&lte_coordinator_config,&lte_connector);
    if(lte_coordinator_ready&&uart_ready&&network_stack_ready) {
        collection_usb_lte_config_t config={
            .vendor_id=CONFIG_EGOLINK_COLLECTION_LTE_USB_VENDOR_ID,
            .product_id=CONFIG_EGOLINK_COLLECTION_LTE_USB_PRODUCT_ID,
            .modem_interface=CONFIG_EGOLINK_COLLECTION_LTE_USB_MODEM_INTERFACE,
            .descriptor_verified=CONFIG_EGOLINK_COLLECTION_LTE_USB_DESCRIPTOR_VERIFIED,
            .usb_host_already_installed=CONFIG_EGOLINK_COLLECTION_LTE_USB_HOST_ALREADY_INSTALLED,
        };
        usb_ready=collection_usb_lte_init(&config)==ESP_OK;
    }
    if(usb_ready)collection_network_coordinator_refresh_status(&lte_control);
    sync_lte_facts(&lte_control);
#else
    atomic_store(&lte_ppp_stopped,true);atomic_store(&lte_cleanup_confirmed,true);
#endif
    collection_network_policy_config_t policy_config={
        .lte_enabled=usb_ready,
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
        .lte_attempt_timeout_ms=CONFIG_EGOLINK_COLLECTION_LTE_ATTEMPT_TIMEOUT_MS,
        .retry_initial_ms=CONFIG_EGOLINK_COLLECTION_LTE_RETRY_INITIAL_MS,
        .retry_max_ms=CONFIG_EGOLINK_COLLECTION_LTE_RETRY_MAX_MS,
#else
        .lte_attempt_timeout_ms=45000,.retry_initial_ms=5000,.retry_max_ms=60000,
#endif
    };
    collection_network_policy_t policy;
    if(!collection_network_policy_init(&policy,&policy_config)) {
        policy_config=(collection_network_policy_config_t){.lte_enabled=false,.lte_attempt_timeout_ms=45000,.retry_initial_ms=5000,.retry_max_ms=60000};
        (void)collection_network_policy_init(&policy,&policy_config);
    }
    bool previous_wifi=atomic_load(&wifi_ready);
    collection_network_policy_snapshot_t policy_result=policy_event(&policy,
        previous_wifi?COLLECTION_NETWORK_EVENT_WIFI_READY:COLLECTION_NETWORK_EVENT_WIFI_LOST,
        (uint64_t)now_us()/1000U,0);
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
    lte_apply_policy_result(&policy,&lte_control,policy_result,(uint64_t)now_us()/1000U);
#endif
    ESP_LOGI(TAG,"NETWORK policy=%s route=%s lte_opt_in=%d usb_init=%d",
        collection_network_state_name(policy_result.state),collection_network_route_name(policy_result.route),
        CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED,usb_ready);

    int64_t next_gnss=0,next_cell=0;
    while(!atomic_load(&stopping)) {
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_stack_hwm_observe(&photo_modem_stack_hwm_bytes);
#endif
        int64_t now=now_us();uint64_t now_ms=(uint64_t)now/1000U;
        bool current_wifi=atomic_load(&wifi_ready);
        if(current_wifi!=previous_wifi) {
            previous_wifi=current_wifi;
            policy_result=policy_event(&policy,current_wifi?COLLECTION_NETWORK_EVENT_WIFI_READY:
                COLLECTION_NETWORK_EVENT_WIFI_LOST,now_ms,0);
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
            lte_apply_policy_result(&policy,&lte_control,policy_result,now_ms);
#endif
        }
        policy_result=policy_event(&policy,COLLECTION_NETWORK_EVENT_TICK,now_ms,0);
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
        if(usb_ready)(void)collection_usb_lte_service();
        lte_apply_policy_result(&policy,&lte_control,policy_result,now_ms);
        collection_network_retirement_facts_t retirement=lte_retirement();
        collection_network_coordinator_notice_t notice=collection_network_coordinator_poll(
            &lte_control,&retirement,now_ms);
        sync_lte_facts(&lte_control);
        if(notice.valid) {
            policy_result=policy_event(&policy,notice.type,now_ms,notice.attempt_id);
            lte_apply_policy_result(&policy,&lte_control,policy_result,now_ms);
        }
        /* A pending USB command is polled every 20 ms. Never enter a bounded
         * 4-5 second UART sensor request while its reply deadline is active. */
        if(collection_network_coordinator_blocks_uart_work(&lte_control)) {vTaskDelay(pdMS_TO_TICKS(20));continue;}
#endif

        if(uart_ready&&now>=next_cell) {
            trace_t trace={.at=cJSON_CreateArray()};
            sim7670_location_bounded_request_t req={.timeout_ms=5000,.per_command_timeout_cap_ms=500,.operation_token=operation++,.cancel_requested=cancel,.trace_at=trace_at,.trace_context=&trace,.continue_on_status_error=true};
            sim7670_lte_report_t l;sim7670_location_bounded_result_t r;
            sim7670_lte_query_status_bounded(&req,&l,&r);
            bool dial_admitted=r.outcome==SIM7670_LOCATION_BOUNDED_REPORT_READY&&
                l.cpin_query.parse_valid&&l.sim_ready&&l.cereg_query.parse_valid&&l.registered&&
                l.cgatt_query.parse_valid&&l.attached&&l.cgdcont_query.parse_valid&&
                strcmp(l.apn_state,"configured")==0;
            cJSON *p=cJSON_CreateObject();cJSON_AddItemToObject(p,"at",trace.at);
            cJSON_AddNumberToObject(p,"elapsed_ms",r.elapsed_ms);cJSON_AddNumberToObject(p,"reason",r.reason);
            cJSON_AddStringToObject(p,"operator",l.operator_name);cJSON_AddStringToObject(p,"rat",l.rat);
            cJSON_AddStringToObject(p,"mcc",l.mcc);cJSON_AddStringToObject(p,"mnc",l.mnc);cJSON_AddStringToObject(p,"tac",l.tac);cJSON_AddStringToObject(p,"cell_id",l.cell_id);
            add_nullable_number(p,"rssi",l.rssi_valid,l.rssi);add_nullable_number(p,"rsrp",l.rsrp_valid,l.rsrp);
            add_nullable_number(p,"rsrq",l.rsrq_valid,l.rsrq);add_nullable_number(p,"sinr",l.sinr_valid,l.sinr);
            cJSON_AddStringToObject(p,"sim_state",l.sim_state);cJSON_AddStringToObject(p,"registration_state",l.registration_state);
            cJSON_AddStringToObject(p,"pdp_state",l.pdp_state);cJSON_AddStringToObject(p,"apn_state",l.apn_state);cJSON_AddStringToObject(p,"failure_reason",l.reason_code);
            cJSON_AddBoolToObject(p,"registered",l.registered);cJSON_AddBoolToObject(p,"attached",l.attached);
            cJSON_AddBoolToObject(p,"cell_identity_queried",l.cpsi_query.attempted);
            cJSON_AddBoolToObject(p,"sim_state_queried",l.cpin_query.attempted);cJSON_AddBoolToObject(p,"sim_state_valid",l.cpin_query.parse_valid);
            cJSON_AddBoolToObject(p,"registration_valid",l.cereg_query.parse_valid);cJSON_AddBoolToObject(p,"attachment_valid",l.cgatt_query.parse_valid);
            cJSON_AddBoolToObject(p,"apn_query_valid",l.cgdcont_query.parse_valid);cJSON_AddBoolToObject(p,"ppp_dial_admitted",dial_admitted);
            emit(LTE,now,r.reason&&r.commands_completed>1?"partial":query_status(&r),r.reason?"see_at_outcome_and_reason":NULL,p,false);
            next_cell=now+10000000;
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
            notice=collection_network_coordinator_admit(
                &lte_control,policy_result.active_lte_attempt_id,
                dial_admitted,(uint64_t)now_us()/1000U);
            sync_lte_facts(&lte_control);
            if(notice.valid) {
                policy_result=policy_event(&policy,notice.type,(uint64_t)now_us()/1000U,notice.attempt_id);
                lte_apply_policy_result(&policy,&lte_control,policy_result,(uint64_t)now_us()/1000U);
            }
            if(collection_network_coordinator_blocks_uart_work(&lte_control)){vTaskDelay(pdMS_TO_TICKS(20));continue;}
#endif
        }
        now=now_us();
        if(uart_ready&&now>=next_gnss) {
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
            const char *status=query_status(&r);if(r.outcome==SIM7670_LOCATION_BOUNDED_REPORT_READY&&!g.fix&&g.no_fix_observed)status="no_fix";
            unsigned gnss_seq=emit(GNSS,now,status,r.reason?"see_at_outcome_and_reason":NULL,p,false);
            if(gnss_seq&&g.fix&&g.lat_valid&&g.lon_valid){
                char event_utc[40];
                if(format_utc_from_monotonic(now,event_utc)){
                    portENTER_CRITICAL(&location_ref_mux);
                    last_trusted_location_ref.valid=true;
                    snprintf(last_trusted_location_ref.observation_id,
                        sizeof(last_trusted_location_ref.observation_id),
                        "col-b%" PRIu32 "-gnss-%u",boot,gnss_seq);
                    memcpy(last_trusted_location_ref.event_utc,event_utc,strlen(event_utc)+1U);
                    memcpy(last_trusted_location_ref.timestamp_quality,
                        "network_time_unverified_accuracy",33U);
                    portEXIT_CRITICAL(&location_ref_mux);
                }
            }
            next_gnss=now+CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS*1000LL;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }

    /* Retire the synchronous uploader before changing or quiescing its netif. */
    int64_t uploader_deadline=now_us()+15000000;
    while(!atomic_load(&uploader_finished)&&now_us()<uploader_deadline) {
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
        if(usb_ready)(void)collection_usb_lte_service();
        collection_network_coordinator_notice_t cancel_notice=
            collection_network_coordinator_cancel_setup(&lte_control);
        sync_lte_facts(&lte_control);
        if(cancel_notice.valid) {
            uint64_t cancel_now=(uint64_t)now_us()/1000U;
            policy_result=policy_event(
                &policy,cancel_notice.type,cancel_now,cancel_notice.attempt_id);
            lte_apply_policy_result(
                &policy,&lte_control,policy_result,cancel_now);
        }
#endif
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    bool uploader_stopped_first=atomic_load(&uploader_finished);
    uint64_t stop_now=(uint64_t)now_us()/1000U;
    policy_result=policy_event(&policy,COLLECTION_NETWORK_EVENT_STOP,stop_now,0);
    if(uploader_stopped_first) {
        /* The exited uploader has already closed TLS and cannot observe the
         * STOP publication itself. Retire that final offline generation here. */
        atomic_store(&uploader_retired_generation,policy_result.route_generation);
    }
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
    lte_apply_policy_result(&policy,&lte_control,policy_result,stop_now);
    uint64_t policy_deadline=stop_now+CONFIG_EGOLINK_COLLECTION_LTE_CLEANUP_TIMEOUT_MS+2000U;
    while(collection_network_policy_snapshot(&policy).state!=COLLECTION_NETWORK_STOPPED&&
          (uint64_t)now_us()/1000U<policy_deadline) {
        uint64_t tick=(uint64_t)now_us()/1000U;
        if(usb_ready)(void)collection_usb_lte_service();
        collection_network_retirement_facts_t retirement=lte_retirement();
        collection_network_coordinator_notice_t notice=collection_network_coordinator_poll(
            &lte_control,&retirement,tick);
        sync_lte_facts(&lte_control);
        if(notice.valid) {
            policy_result=policy_event(&policy,notice.type,tick,notice.attempt_id);
            lte_apply_policy_result(&policy,&lte_control,policy_result,tick);
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    if(usb_ready) {
        (void)collection_usb_lte_service();
        collection_network_coordinator_refresh_status(&lte_control);
    }
    sync_lte_facts(&lte_control);
#endif

    bool stopped=false;
    bool uart_cleanup_allowed=uart_ready;
#if CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED
    uart_cleanup_allowed=uart_cleanup_allowed&&
        !collection_network_coordinator_blocks_uart_work(&lte_control);
#endif
    if(uart_cleanup_allowed)for(unsigned i=0;i<3&&!stopped;i++) {
        trace_t trace={.at=cJSON_CreateArray()};sim7670_location_bounded_result_t r;
        sim7670_location_bounded_request_t req={.timeout_ms=2000,.per_command_timeout_cap_ms=1500,.operation_token=operation++,.cancel_requested=cleanup_cancel,.trace_at=trace_at,.trace_context=&trace};
        stopped=sim7670_gnss_power_off_bounded(&req,&r)==SIM7670_LOCATION_BOUNDED_REPORT_READY;
        cJSON *p=cJSON_CreateObject();cJSON_AddItemToObject(p,"at",trace.at);cJSON_AddBoolToObject(p,"stopped",stopped);
        cJSON_AddStringToObject(p,"phase","session_stop_cleanup");
        emit(GNSS,now_us(),stopped?"stopped":"error",stopped?NULL:"power_off_unconfirmed",p,false);
        if(!stopped)vTaskDelay(pdMS_TO_TICKS(500));
    }
    atomic_store(&gnss_stopped,stopped);
    bool lte_stopped=atomic_load(&lte_ppp_stopped)&&atomic_load(&lte_cleanup_confirmed)&&
        (!atomic_load(&lte_hangup_required)||atomic_load(&lte_hangup_confirmed));
    bool all_stopped=stopped&&lte_stopped&&uploader_stopped_first;
    atomic_store(&modem_stopped,all_stopped);atomic_store(&modem_finished,true);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_modem_stack_hwm_bytes);
#endif
    ESP_LOGI(TAG,"MODEM stopped=%d exclusive_owner=%d uploader_first=%d gnss_off=%d ppp_dead=%d hangup_required=%d hangup_ok=%d cleanup_ok=%d",
        all_stopped,uart_ready,uploader_stopped_first,stopped,atomic_load(&lte_ppp_stopped),
        atomic_load(&lte_hangup_required),atomic_load(&lte_hangup_confirmed),atomic_load(&lte_cleanup_confirmed));
    vTaskDelete(NULL);
}
static void network_event(void *ctx,esp_event_base_t base,int32_t id,void *data)
{
    (void)ctx;
    if(atomic_load(&stopping)) {
        if((base==IP_EVENT&&(id==IP_EVENT_STA_GOT_IP||id==IP_EVENT_STA_LOST_IP))||
           (base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED))
            atomic_store(&wifi_ready,false);
        return;
    }
    if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP) {
        atomic_store(&wifi_ready,true);
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"phase","link_event");cJSON_AddBoolToObject(p,"connected",true);
        emit(WIFI,now_us(),"connected",NULL,p,false);
    }
    if(base==IP_EVENT&&id==IP_EVENT_STA_LOST_IP) {
        atomic_store(&wifi_ready,false);atomic_store(&wifi_reason,0);
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"phase","link_event");
        cJSON_AddBoolToObject(p,"connected",false);cJSON_AddNumberToObject(p,"disconnect_reason",0);
        emit(WIFI,now_us(),"disconnected","wifi_lost_ip_event",p,false);
    }
    if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED) {
        atomic_store(&wifi_ready,false);wifi_event_sta_disconnected_t *e=data;atomic_store(&wifi_reason,e?e->reason:0);
        cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"phase","link_event");cJSON_AddBoolToObject(p,"connected",false);cJSON_AddNumberToObject(p,"disconnect_reason",e?e->reason:0);
        emit(WIFI,now_us(),"disconnected","wifi_disconnect_event",p,false);
    }
}
static bool wifi_cleanup(void)
{
    bool clean=true;
    if(wifi_ip_handler_registered) {
        if(esp_event_handler_unregister(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event)==ESP_OK)
            wifi_ip_handler_registered=false;
        else clean=false;
    }
    if(wifi_lost_ip_handler_registered) {
        if(esp_event_handler_unregister(IP_EVENT,IP_EVENT_STA_LOST_IP,network_event)==ESP_OK)
            wifi_lost_ip_handler_registered=false;
        else clean=false;
    }
    if(wifi_disconnect_handler_registered) {
        if(esp_event_handler_unregister(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event)==ESP_OK)
            wifi_disconnect_handler_registered=false;
        else clean=false;
    }
    if(wifi_runtime_started) {
        (void)esp_wifi_disconnect();
        if(esp_wifi_stop()==ESP_OK)wifi_runtime_started=false;
        else clean=false;
    }
    if(wifi_driver_ready&&!wifi_runtime_started) {
        if(esp_wifi_deinit()==ESP_OK)wifi_driver_ready=false;
        else clean=false;
    }
    if(wifi_netif&&!wifi_driver_ready&&!wifi_ip_handler_registered&&
       !wifi_lost_ip_handler_registered&&!wifi_disconnect_handler_registered) {
        esp_netif_destroy_default_wifi(wifi_netif);
        wifi_netif=NULL;
    }
    atomic_store(&wifi_ready,false);
    return clean&&!wifi_runtime_started&&!wifi_driver_ready&&!wifi_netif&&
        !wifi_ip_handler_registered&&!wifi_lost_ip_handler_registered&&
        !wifi_disconnect_handler_registered;
}
static bool network_init(void)
{
    if(esp_netif_init()!=ESP_OK||esp_event_loop_create_default()!=ESP_OK) {
        atomic_store(&wifi_cleanup_confirmed,true);
        return false;
    }
    network_stack_ready=true;
    esp_sntp_config_t clock=ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    sntp_ready=esp_netif_sntp_init(&clock)==ESP_OK;
    /* Wi-Fi configuration failure must not prevent an explicitly enabled LTE
     * route from using the already initialized TCP/IP stack and SNTP client. */
    if(strlen(CONFIG_EGOLINK_WIFI_SSID)>32||strlen(CONFIG_EGOLINK_WIFI_PASSWORD)>63) {
        atomic_store(&wifi_cleanup_confirmed,true);
        return false;
    }
    wifi_netif=esp_netif_create_default_wifi_sta();wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    if(!wifi_netif||esp_wifi_init(&init)!=ESP_OK)goto fail;
    wifi_driver_ready=true;
    if(esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK)goto fail;
    if(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL)!=ESP_OK)goto fail;
    wifi_ip_handler_registered=true;
    if(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_LOST_IP,network_event,NULL)!=ESP_OK)goto fail;
    wifi_lost_ip_handler_registered=true;
    if(esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event,NULL)!=ESP_OK)goto fail;
    wifi_disconnect_handler_registered=true;
    wifi_config_t cfg={0};
    memcpy(cfg.sta.ssid,CONFIG_EGOLINK_WIFI_SSID,strlen(CONFIG_EGOLINK_WIFI_SSID));
    memcpy(cfg.sta.password,CONFIG_EGOLINK_WIFI_PASSWORD,strlen(CONFIG_EGOLINK_WIFI_PASSWORD));
    cfg.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;
    if(esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK||esp_wifi_set_config(WIFI_IF_STA,&cfg)!=ESP_OK||esp_wifi_start()!=ESP_OK)goto fail;
    wifi_runtime_started=true;
    atomic_store(&wifi_cleanup_confirmed,false);
    (void)esp_wifi_connect();
    return true;
fail:
    atomic_store(&wifi_cleanup_confirmed,wifi_cleanup());
    return false;
}
static void scan_wifi(void)
{
    int64_t capture=now_us();wifi_scan_config_t cfg={0};
    esp_err_t result=esp_wifi_scan_start(&cfg,true);uint16_t count=16,total=0;wifi_ap_record_t aps[16];
    typedef struct {uint8_t channel;uint16_t count;int strongest;} channel_t;
    channel_t channels[14]={0};unsigned channel_count=0,sampled=0;
    cJSON *p=cJSON_CreateObject(),*array=cJSON_AddArrayToObject(p,"channel_summary");
    if(result==ESP_OK) { esp_wifi_scan_get_ap_num(&total);result=esp_wifi_scan_get_ap_records(&count,aps); }
    if(result==ESP_OK)for(unsigned i=0;i<count;i++) {
        if(aps[i].primary<1||aps[i].primary>14)continue;
        int rssi=aps[i].rssi< -127?-127:aps[i].rssi>0?0:aps[i].rssi;
        unsigned j=0;for(;j<channel_count;j++)if(channels[j].channel==aps[i].primary)break;
        if(j==channel_count){channels[j].channel=aps[i].primary;channels[j].strongest=rssi;++channel_count;}
        ++channels[j].count;++sampled;if(rssi>channels[j].strongest)channels[j].strongest=rssi;
    }
    for(unsigned i=0;i<channel_count;i++){cJSON *a=cJSON_CreateObject();cJSON_AddNumberToObject(a,"channel",channels[i].channel);cJSON_AddNumberToObject(a,"ap_count",channels[i].count);cJSON_AddNumberToObject(a,"strongest_rssi",channels[i].strongest);cJSON_AddItemToArray(array,a);}
    uint16_t reported_total=total<sampled?sampled:total;
    cJSON_AddNumberToObject(p,"scan_result",result);cJSON_AddNumberToObject(p,"total_seen",reported_total);cJSON_AddBoolToObject(p,"truncated",reported_total>sampled);
    cJSON_AddNumberToObject(p,"sampled_ap_count",sampled);cJSON_AddBoolToObject(p,"identifiers_retained",false);
    cJSON_AddStringToObject(p,"privacy_reason","raw_wifi_identifiers_disabled");
    cJSON_AddBoolToObject(p,"connected",atomic_load(&wifi_ready));cJSON_AddNumberToObject(p,"disconnect_reason",atomic_load(&wifi_reason));
    emit(WIFI,capture,result==ESP_OK?"observed":"error",result==ESP_OK?NULL:"scan_failed",p,false);
}
static void wifi_task(void *unused)
{
    (void)unused;int64_t next_connect=0,next_scan=3000000;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_wifi_stack_hwm_bytes);
#endif
    while(!atomic_load(&stopping)) {
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_stack_hwm_observe(&photo_wifi_stack_hwm_bytes);
#endif
        int64_t now=now_us();
        if(!atomic_load(&wifi_ready)&&now>=next_connect){(void)esp_wifi_connect();next_connect=now+10000000;}
        if(now>=next_scan){scan_wifi();next_scan=now_us()+45000000;}
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    int64_t deadline=now_us()+15000000;
    while(!atomic_load(&uploader_finished)&&now_us()<deadline)vTaskDelay(pdMS_TO_TICKS(20));
    if(atomic_load(&uploader_finished))
        atomic_store(&wifi_cleanup_confirmed,wifi_cleanup());
    else
        atomic_store(&wifi_cleanup_confirmed,false);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_wifi_stack_hwm_bytes);
#endif
    atomic_store(&wifi_finished,true);vTaskDelete(NULL);
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
    network_runtime_snapshot_t network=read_network();
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
    cJSON_AddNumberToObject(p,"protected_pending_records",stats.protected_pending_records);
    cJSON_AddNumberToObject(p,"protected_retained_bytes",stats.protected_retained_bytes);
    cJSON_AddNumberToObject(p,"evicted_records",stats.evicted_records);cJSON_AddNumberToObject(p,"evicted_bytes",stats.evicted_payload_bytes);
    cJSON_AddNumberToObject(p,"flash_written_bytes",stats.write_bytes_this_boot);cJSON_AddNumberToObject(p,"flash_erased_bytes",stats.erased_bytes_this_boot);
    cJSON_AddNumberToObject(p,"quarantined_sectors",stats.quarantined_sectors);cJSON_AddNumberToObject(p,"torn_tails",stats.torn_tails);cJSON_AddNumberToObject(p,"storage_io_errors",stats.io_errors_this_boot);
    cJSON_AddBoolToObject(p,"storage_stats_valid",stats_valid);
    if(!stats_valid){const char *fields[]={"cache_capacity_bytes","cache_append_free_bytes","queue_bytes","pending_records","protected_pending_records","protected_retained_bytes","evicted_records","evicted_bytes","flash_written_bytes","flash_erased_bytes","quarantined_sectors","torn_tails","storage_io_errors"};for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++)cJSON_ReplaceItemInObjectCaseSensitive(p,fields[i],cJSON_CreateNull());}
    cJSON_AddNumberToObject(p,"ram_pending",uxQueueMessagesWaiting(ram_fallback));cJSON_AddNumberToObject(p,"acked_this_boot",atomic_load(&acked));
    cJSON_AddStringToObject(p,"network_policy_state",collection_network_state_name(network.state));
    cJSON_AddStringToObject(p,"selected_route",collection_network_route_name(network.route));
    cJSON_AddNumberToObject(p,"route_generation",network.generation);
    cJSON_AddBoolToObject(p,"lte_ppp_opt_in",CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_media_store_stats_t media={0};
    bool media_stats_valid=false;
    if(atomic_load(&media_store_ready)){
        media_stats_valid=photo_media_stats_locked(&media);
        if(!media_stats_valid)
            photo_store_observe_result(PHOTO_MEDIA_STORE_IO_ERROR);
    }
    photo_stack_hwm_observe(&photo_main_stack_hwm_bytes);
    photo_control_timer_t timer;photo_timer_snapshot(&timer);
    uint64_t ignored_utc=0U;const bool photo_utc_trusted=photo_wall_clock(&ignored_utc);
    cJSON *camera=cJSON_AddObjectToObject(p,"camera_runtime");
    const platform_camera_shared_i2c_state_t shared_i2c_state=
        platform_camera_shared_i2c_state();
    const bool trial_consumed=
        platform_camera_unverified_trial_attempt_consumed();
    const char *camera_preflight_reason=NULL;
    const platform_camera_status_t camera_preflight=
        platform_camera_preflight(&camera_preflight_reason);
    cJSON_AddStringToObject(camera,"shared_i2c_state",
        platform_camera_shared_i2c_state_name(shared_i2c_state));
    cJSON_AddBoolToObject(camera,"shared_i2c_verified",
        shared_i2c_state==PLATFORM_CAMERA_SHARED_I2C_VERIFIED);
    cJSON_AddStringToObject(camera,"driver_preflight",
        platform_camera_status_name(camera_preflight));
    if(camera_preflight_reason)cJSON_AddStringToObject(camera,
        "driver_preflight_reason",camera_preflight_reason);
    else cJSON_AddNullToObject(camera,"driver_preflight_reason");
    cJSON_AddBoolToObject(camera,"manual_capture_ready",
        photo_camera_manual_capture_ready(camera_preflight));
    cJSON_AddBoolToObject(camera,"timed_capture_allowed",
        platform_camera_timed_capture_allowed());
    cJSON_AddBoolToObject(camera,"unverified_trial_attempt_consumed",
        trial_consumed);
    cJSON_AddBoolToObject(camera,"unverified_trial_attempt_remaining",
        shared_i2c_state==PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED&&
        !trial_consumed);
    cJSON_AddBoolToObject(camera,"control_state_ready",atomic_load(&photo_control_state_ready));
    cJSON_AddBoolToObject(camera,"media_store_ready",atomic_load(&media_store_ready));
    cJSON_AddBoolToObject(camera,"media_store_stats_valid",media_stats_valid);
    cJSON_AddNumberToObject(camera,"committed_photos",media.committed_slots);
    cJSON_AddNumberToObject(camera,"committed_payload_bytes",(double)media.committed_payload_bytes);
    cJSON_AddNumberToObject(camera,"reconciled_owned_slots",
        media.reconciled_owned_slots);
    cJSON_AddNumberToObject(camera,"capture_attempts",atomic_load(&photo_capture_attempts));
    cJSON_AddNumberToObject(camera,"capture_saved",atomic_load(&photo_capture_saved));
    cJSON_AddNumberToObject(camera,"capture_failures",atomic_load(&photo_capture_failures));
    cJSON_AddNumberToObject(camera,"upload_server_verified",atomic_load(&photo_upload_acked));
    cJSON_AddNumberToObject(camera,"upload_failures",atomic_load(&photo_upload_failures));
    cJSON_AddNumberToObject(camera,"expired_local_releases",atomic_load(&photo_expired_released));
    cJSON_AddNumberToObject(camera,"command_polls",atomic_load(&photo_command_polls));
    cJSON_AddNumberToObject(camera,"command_parse_failures",atomic_load(&photo_command_parse_failures));
    cJSON_AddNumberToObject(camera,"command_acks",atomic_load(&photo_command_acks));
    cJSON_AddNumberToObject(camera,"metadata_persist_retries",
        atomic_load(&photo_metadata_persist_retries));
    cJSON *resources=cJSON_AddObjectToObject(camera,"resources");
    cJSON_AddNumberToObject(resources,"internal_free_bytes",
        (double)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    cJSON_AddNumberToObject(resources,"internal_min_free_bytes",
        (double)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
    cJSON_AddNumberToObject(resources,"dma_free_bytes",
        (double)heap_caps_get_free_size(MALLOC_CAP_DMA));
    cJSON_AddNumberToObject(resources,"dma_largest_free_block_bytes",
        (double)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
    cJSON *stack_hwm=cJSON_AddObjectToObject(resources,
        "task_stack_high_watermark_bytes");
    photo_add_stack_hwm(stack_hwm,"main",&photo_main_stack_hwm_bytes);
    photo_add_stack_hwm(stack_hwm,"store",&photo_store_stack_hwm_bytes);
    photo_add_stack_hwm(stack_hwm,"imu",&photo_imu_stack_hwm_bytes);
    photo_add_stack_hwm(stack_hwm,"modem",&photo_modem_stack_hwm_bytes);
    photo_add_stack_hwm(stack_hwm,"upload",&photo_upload_stack_hwm_bytes);
    photo_add_stack_hwm(stack_hwm,"wifi",&photo_wifi_stack_hwm_bytes);
    cJSON *timer_state=cJSON_AddObjectToObject(camera,"timer_state");
    if(timer.config_version[0])cJSON_AddStringToObject(timer_state,"config_version",timer.config_version);
    else cJSON_AddNullToObject(timer_state,"config_version");
    cJSON_AddBoolToObject(timer_state,"enabled",timer.enabled);
    cJSON_AddNumberToObject(timer_state,"interval_seconds",timer.interval_seconds);
    cJSON_AddNumberToObject(timer_state,"session_expires_at_unix_ms",(double)timer.session_expires_at_unix_ms);
    cJSON_AddNumberToObject(timer_state,"max_photos",timer.max_photos);
    cJSON_AddNumberToObject(timer_state,"captured_count",timer.captured_photos);
    cJSON_AddStringToObject(timer_state,"state_reason",timer.state_reason[0]?timer.state_reason:"not_configured");
    cJSON_AddBoolToObject(timer_state,"trusted_utc",photo_utc_trusted);
#endif
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
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
static const char *photo_transport(collection_network_route_t route)
{ return route==COLLECTION_NETWORK_ROUTE_LTE?"lte":"wifi"; }

static bool photo_post_command_ack(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    const photo_control_journal_t *journal,const photo_control_timer_t *timer,
    const char *timer_status,bool duplicate_prevented,uint8_t *response,
    size_t response_capacity)
{
    if(!https||!route||!interface_name||!journal||!response)return false;
    char frame[2048];size_t frame_bytes=0U;
    uint32_t seq=0U;if(!photo_next_ack_sequence(&seq)){
        atomic_store(&photo_control_state_ready,false);return false;
    }
    uint64_t ignored_utc=0U;const bool trusted_utc=photo_wall_clock(&ignored_utc);
    bool built=timer?
        photo_control_build_timer_state_ack_frame(journal->cmd_id,
            timer_status?timer_status:"applied",journal->message,
            CONFIG_EGOLINK_FW_VERSION,photo_transport(route->route),seq,
            duplicate_prevented,timer,trusted_utc,frame,sizeof(frame),&frame_bytes):
        photo_control_build_ack_frame(journal->cmd_id,journal->status,
            journal->message,CONFIG_EGOLINK_FW_VERSION,
            photo_transport(route->route),seq,duplicate_prevented,frame,
            sizeof(frame),&frame_bytes);
    if(!built)return false;
    uint8_t ack_digest[32];char ack_digest_hex[65];
    if(mbedtls_sha256((const unsigned char *)frame,frame_bytes,ack_digest,0)!=0)
        return false;
    photo_digest_hex(ack_digest,ack_digest_hex);
    https->attempts=0U;https->deadline_ms=(uint64_t)now_us()/1000U+13000U;
    egolink_p0_delivery_post_result_t posted={0};
    atomic_store(&uploader_active_generation,route->generation);
    const egolink_p0_delivery_post_outcome_t outcome=
        egolink_esp_p0_https_ack_collection_command(https,
            CONFIG_EGOLINK_DEVICE_ID,journal->cmd_id,interface_name,
            (const uint8_t *)frame,frame_bytes,response,response_capacity,
            upload_cancel,NULL,route->generation,&posted);
    atomic_store(&uploader_active_generation,0U);
    bool matched=outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE&&
        posted.http_status_code>=200U&&posted.http_status_code<300U&&
        atomic_load(&network_route_generation)==route->generation&&
        photo_delivery_command_ack_response_matches(response,
            posted.response_length,journal->cmd_id,
            timer?(timer_status?timer_status:"applied"):journal->status,
            ack_digest_hex);
    if(matched)atomic_fetch_add(&photo_command_acks,1U);
    else egolink_esp_p0_https_close(https);
    ESP_LOGI(TAG,"PHOTO_COMMAND_ACK cmd=%s status=%s http=%u matched=%d duplicate=%d",
        journal->cmd_id,timer?timer_status:journal->status,
        (unsigned)posted.http_status_code,matched,duplicate_prevented);
    return matched;
}

static bool photo_finish_journal(photo_control_journal_t *journal,
                                 const char *status,const char *message)
{
    journal->phase=PHOTO_CONTROL_JOURNAL_COMPLETE;
    snprintf(journal->status,sizeof(journal->status),"%s",status);
    snprintf(journal->message,sizeof(journal->message),"%s",message);
    if(!save_photo_journal(journal))return false;
    photo_journal_publish(journal);return true;
}

static bool photo_stamp_intent(photo_capture_intent_t *intent,uint64_t utc_ms,
                               uint32_t timer_captured_count_before)
{
    if(!intent||!utc_ms||!boot)return false;
    const int64_t monotonic_us=now_us();
    const uint32_t sequence=atomic_fetch_add(&sequences[CAMERA],1U)+1U;
    if(monotonic_us<=0||!sequence)return false;
    intent->source_event_utc_ms=utc_ms;
    intent->source_event_monotonic_ns=(uint64_t)monotonic_us*1000U;
    intent->capture_boot_count=boot;
    intent->capture_sequence_id=sequence;
    intent->timer_captured_count_before=timer_captured_count_before;
    const platform_camera_shared_i2c_state_t shared_i2c_state=
        platform_camera_shared_i2c_state();
    snprintf(intent->camera_shared_i2c_state,
        sizeof(intent->camera_shared_i2c_state),"%s",
        platform_camera_shared_i2c_state_name(shared_i2c_state));
    snprintf(intent->camera_driver_profile,
        sizeof(intent->camera_driver_profile),"%s",
        photo_camera_driver_profile(shared_i2c_state,NULL));
    snprintf(intent->runtime_config_id,sizeof(intent->runtime_config_id),"%s",
        CONFIG_ID);
    snprintf(intent->capture_fw_version,sizeof(intent->capture_fw_version),"%s",
        CONFIG_EGOLINK_FW_VERSION);
    snprintf(intent->capture_firmware_elf_sha256,
        sizeof(intent->capture_firmware_elf_sha256),"%s",
        firmware_elf_sha256);
    return true;
}

static bool photo_intent_from_command(const photo_control_command_t *command,
                                      uint64_t utc_ms,
                                      photo_capture_intent_t *intent)
{
    memset(intent,0,sizeof(*intent));intent->kind=command->kind;
    snprintf(intent->trigger_reason,sizeof(intent->trigger_reason),"web_manual");
    snprintf(intent->command_id,sizeof(intent->command_id),"%s",command->cmd_id);
    snprintf(intent->config_version,sizeof(intent->config_version),"manual-single-v1");
    snprintf(intent->authorization_session_id,sizeof(intent->authorization_session_id),
        "%s",command->authorization_session_id);
    snprintf(intent->retention_expires_at,sizeof(intent->retention_expires_at),
        "%s",command->retention_expires_at);
    intent->execution_expires_at_unix_ms=command->expires_at_unix_ms;
    intent->retention_expires_at_unix_ms=command->retention_expires_at_unix_ms;
    return photo_make_id("manual",command->cmd_id,0U,intent->photo_id)&&
        photo_stamp_intent(intent,utc_ms,0U);
}

static bool photo_intent_from_timer(const photo_control_timer_t *timer,
                                    uint64_t scheduled_utc_ms,
                                    photo_capture_intent_t *intent)
{
    memset(intent,0,sizeof(*intent));intent->kind=PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER;
    snprintf(intent->trigger_reason,sizeof(intent->trigger_reason),"device_timer");
    snprintf(intent->command_id,sizeof(intent->command_id),"%s",timer->command_id);
    snprintf(intent->config_version,sizeof(intent->config_version),"%s",timer->config_version);
    snprintf(intent->authorization_session_id,sizeof(intent->authorization_session_id),
        "%s",timer->authorization_session_id);
    snprintf(intent->retention_expires_at,sizeof(intent->retention_expires_at),
        "%s",timer->retention_expires_at);
    intent->execution_expires_at_unix_ms=timer->session_expires_at_unix_ms;
    intent->retention_expires_at_unix_ms=timer->retention_expires_at_unix_ms;
    /* Failure observations must not reuse the previous observation/photo ID.
     * Include this due instant even when captured_count does not advance. */
    char identity[192];
    int n=snprintf(identity,sizeof(identity),"%s|%" PRIu64,
        timer->command_id,scheduled_utc_ms);
    return n>0&&(size_t)n<sizeof(identity)&&
        photo_make_id("timer",identity,(uint32_t)(scheduled_utc_ms&UINT32_MAX),
            intent->photo_id)&&
        photo_stamp_intent(intent,scheduled_utc_ms,timer->captured_photos);
}

static const char *photo_outcome_reason(const photo_capture_outcome_t *outcome);

static void photo_capture_journal_from_intent(
    const photo_capture_intent_t *intent,
    photo_control_capture_journal_t *journal)
{
    memset(journal,0,sizeof(*journal));
    journal->phase=PHOTO_CONTROL_CAPTURE_STARTED;journal->kind=intent->kind;
    snprintf(journal->photo_id,sizeof(journal->photo_id),"%s",intent->photo_id);
    snprintf(journal->trigger_reason,sizeof(journal->trigger_reason),"%s",
        intent->trigger_reason);
    snprintf(journal->command_id,sizeof(journal->command_id),"%s",
        intent->command_id);
    snprintf(journal->config_version,sizeof(journal->config_version),"%s",
        intent->config_version);
    snprintf(journal->authorization_session_id,
        sizeof(journal->authorization_session_id),"%s",
        intent->authorization_session_id);
    snprintf(journal->retention_expires_at,
        sizeof(journal->retention_expires_at),"%s",intent->retention_expires_at);
    snprintf(journal->failure_reason,sizeof(journal->failure_reason),"pending");
    snprintf(journal->camera_shared_i2c_state,
        sizeof(journal->camera_shared_i2c_state),"%s",
        intent->camera_shared_i2c_state);
    snprintf(journal->camera_driver_profile,
        sizeof(journal->camera_driver_profile),"%s",
        intent->camera_driver_profile);
    snprintf(journal->runtime_config_id,sizeof(journal->runtime_config_id),"%s",
        intent->runtime_config_id);
    snprintf(journal->capture_fw_version,
        sizeof(journal->capture_fw_version),"%s",intent->capture_fw_version);
    snprintf(journal->capture_firmware_elf_sha256,
        sizeof(journal->capture_firmware_elf_sha256),"%s",
        intent->capture_firmware_elf_sha256);
    journal->execution_expires_at_unix_ms=intent->execution_expires_at_unix_ms;
    journal->retention_expires_at_unix_ms=intent->retention_expires_at_unix_ms;
    journal->source_event_utc_ms=intent->source_event_utc_ms;
    journal->source_event_monotonic_ns=intent->source_event_monotonic_ns;
    journal->capture_boot_count=intent->capture_boot_count;
    journal->capture_sequence_id=intent->capture_sequence_id;
    journal->timer_captured_count_before=intent->timer_captured_count_before;
}

static void photo_intent_from_capture_journal(
    const photo_control_capture_journal_t *journal,
    photo_capture_intent_t *intent)
{
    memset(intent,0,sizeof(*intent));intent->kind=journal->kind;
    snprintf(intent->photo_id,sizeof(intent->photo_id),"%s",journal->photo_id);
    snprintf(intent->trigger_reason,sizeof(intent->trigger_reason),"%s",
        journal->trigger_reason);
    snprintf(intent->command_id,sizeof(intent->command_id),"%s",journal->command_id);
    snprintf(intent->config_version,sizeof(intent->config_version),"%s",
        journal->config_version);
    snprintf(intent->authorization_session_id,
        sizeof(intent->authorization_session_id),"%s",
        journal->authorization_session_id);
    snprintf(intent->retention_expires_at,sizeof(intent->retention_expires_at),"%s",
        journal->retention_expires_at);
    snprintf(intent->camera_shared_i2c_state,
        sizeof(intent->camera_shared_i2c_state),"%s",
        journal->camera_shared_i2c_state);
    snprintf(intent->camera_driver_profile,
        sizeof(intent->camera_driver_profile),"%s",
        journal->camera_driver_profile);
    snprintf(intent->runtime_config_id,sizeof(intent->runtime_config_id),"%s",
        journal->runtime_config_id);
    snprintf(intent->capture_fw_version,sizeof(intent->capture_fw_version),"%s",
        journal->capture_fw_version);
    snprintf(intent->capture_firmware_elf_sha256,
        sizeof(intent->capture_firmware_elf_sha256),"%s",
        journal->capture_firmware_elf_sha256);
    intent->execution_expires_at_unix_ms=journal->execution_expires_at_unix_ms;
    intent->retention_expires_at_unix_ms=journal->retention_expires_at_unix_ms;
    intent->source_event_utc_ms=journal->source_event_utc_ms;
    intent->source_event_monotonic_ns=journal->source_event_monotonic_ns;
    intent->capture_boot_count=journal->capture_boot_count;
    intent->capture_sequence_id=journal->capture_sequence_id;
    intent->timer_captured_count_before=journal->timer_captured_count_before;
}

static bool photo_capture_journal_matches_intent(
    const photo_control_capture_journal_t *journal,
    const photo_capture_intent_t *intent)
{
    return journal&&intent&&journal->phase!=PHOTO_CONTROL_CAPTURE_NONE&&
        journal->kind==intent->kind&&
        !strcmp(journal->photo_id,intent->photo_id)&&
        !strcmp(journal->trigger_reason,intent->trigger_reason)&&
        !strcmp(journal->command_id,intent->command_id)&&
        !strcmp(journal->config_version,intent->config_version)&&
        !strcmp(journal->authorization_session_id,intent->authorization_session_id)&&
        !strcmp(journal->retention_expires_at,intent->retention_expires_at)&&
        !strcmp(journal->camera_shared_i2c_state,
            intent->camera_shared_i2c_state)&&
        !strcmp(journal->camera_driver_profile,intent->camera_driver_profile)&&
        !strcmp(journal->runtime_config_id,intent->runtime_config_id)&&
        !strcmp(journal->capture_fw_version,intent->capture_fw_version)&&
        !strcmp(journal->capture_firmware_elf_sha256,
            intent->capture_firmware_elf_sha256)&&
        journal->execution_expires_at_unix_ms==intent->execution_expires_at_unix_ms&&
        journal->retention_expires_at_unix_ms==intent->retention_expires_at_unix_ms;
}

static bool photo_capture_begin(const photo_capture_intent_t *intent,
                                photo_control_capture_journal_t *journal,
                                bool *newly_started)
{
    if(!newly_started)return false;
    *newly_started=false;
    photo_capture_journal_snapshot(journal);
    if(journal->phase!=PHOTO_CONTROL_CAPTURE_NONE)
        return photo_capture_journal_matches_intent(journal,intent);
    photo_capture_journal_from_intent(intent,journal);
    if(!save_photo_capture_journal(journal))return false;
    photo_capture_journal_publish(journal);*newly_started=true;return true;
}

static bool photo_capture_record_result(photo_control_capture_journal_t *journal,
                                        const photo_capture_outcome_t *outcome)
{
    if(!journal||!outcome||journal->phase!=PHOTO_CONTROL_CAPTURE_STARTED||
       !photo_capture_journal_matches_intent(journal,&outcome->intent))return false;
    journal->phase=PHOTO_CONTROL_CAPTURE_RESULT;
    journal->attempted=outcome->camera.attempted;
    journal->frame_acquired=outcome->camera.frame_acquired;
    journal->media_saved=outcome->media_saved;
    journal->source_event_utc_ms=outcome->media_saved?
        outcome->record.capture_unix_ms:outcome->event_utc_ms;
    journal->source_event_monotonic_ns=outcome->media_saved?
        outcome->record.capture_monotonic_ns:outcome->event_monotonic_ns;
    snprintf(journal->failure_reason,sizeof(journal->failure_reason),"%s",
        outcome->media_saved?"none":photo_outcome_reason(outcome));
    if(!save_photo_capture_journal(journal))return false;
    photo_capture_journal_publish(journal);return true;
}

static bool photo_capture_restore_outcome(
    photo_control_capture_journal_t *journal,photo_capture_outcome_t *outcome)
{
    if(!journal||!outcome||journal->phase==PHOTO_CONTROL_CAPTURE_NONE)return false;
    memset(outcome,0,sizeof(*outcome));
    photo_intent_from_capture_journal(journal,&outcome->intent);
    outcome->camera.shared_i2c_state=photo_camera_shared_i2c_state_from_name(
        outcome->intent.camera_shared_i2c_state);
    outcome->event_utc_ms=journal->source_event_utc_ms;
    outcome->event_monotonic_ns=journal->source_event_monotonic_ns;
    outcome->camera.attempted=journal->attempted;
    outcome->camera.frame_acquired=journal->frame_acquired;
    outcome->failure_reason=journal->failure_reason;
    outcome->store_result=photo_media_find_locked(journal->photo_id,
        &outcome->record);
    photo_store_observe_result(outcome->store_result);
    if(outcome->store_result==PHOTO_MEDIA_STORE_OK){
        if(journal->phase==PHOTO_CONTROL_CAPTURE_RESULT&&!journal->media_saved)
            return false;
        if(outcome->record.retention_expires_at_unix_ms!=
               journal->retention_expires_at_unix_ms||
           outcome->record.capture_boot_count!=journal->capture_boot_count||
           outcome->record.capture_sequence_id!=journal->capture_sequence_id)
            return false;
        outcome->media_saved=true;outcome->existing_media=true;
        outcome->camera.attempted=true;outcome->camera.frame_acquired=true;
        outcome->event_utc_ms=outcome->record.capture_unix_ms;
        outcome->event_monotonic_ns=outcome->record.capture_monotonic_ns;
    }else if(outcome->store_result==PHOTO_MEDIA_STORE_NOT_FOUND){
        if(journal->phase==PHOTO_CONTROL_CAPTURE_RESULT&&journal->media_saved)
            return false;
        outcome->store_result=PHOTO_MEDIA_STORE_NOT_FOUND;
        if(journal->phase==PHOTO_CONTROL_CAPTURE_STARTED){
            outcome->outcome_ambiguous=true;
            outcome->failure_reason="capture_outcome_unknown_after_restart";
        }
    }else return false;
    if(journal->phase==PHOTO_CONTROL_CAPTURE_STARTED&&!outcome->outcome_ambiguous&&
       !photo_capture_record_result(journal,outcome))return false;
    return true;
}

static bool photo_capture_clear(void)
{
    photo_control_capture_journal_t empty;
    photo_control_capture_journal_default(&empty);
    if(!save_photo_capture_journal(&empty))return false;
    photo_capture_journal_publish(&empty);return true;
}

static bool photo_capture_run_or_restore(const photo_capture_intent_t *intent,
    photo_capture_outcome_t *outcome,photo_control_capture_journal_t *journal)
{
    bool newly_started=false;
    if(!photo_capture_begin(intent,journal,&newly_started))return false;
    if(!newly_started)return photo_capture_restore_outcome(journal,outcome);
    (void)photo_execute_capture(intent,true,outcome);
    return photo_capture_record_result(journal,outcome);
}

/* Retention is a privacy boundary, not a delivery state.  Delete authorized
 * media before publishing any diagnostic and tolerate the reboot window after
 * erase: an absent record at/after expiry is already privacy-safe and lets the
 * durable capture transaction finish without inventing a server ACK. */
static bool photo_release_capture_for_retention(
    const photo_control_capture_journal_t *journal,const char *released_reason,
    const char *failure_reason)
{
    if(!journal||!atomic_load(&media_store_ready))return false;
    photo_media_store_record_t record;
    photo_media_store_result_t result=photo_media_find_locked(journal->photo_id,
        &record);
    photo_store_observe_result(result);
    if(result==PHOTO_MEDIA_STORE_NOT_FOUND){
        photo_emit_source_status("photo_retention_media_already_absent");
        return true;
    }
    if(result!=PHOTO_MEDIA_STORE_OK||
       record.retention_expires_at_unix_ms!=
            journal->retention_expires_at_unix_ms||
       record.capture_boot_count!=journal->capture_boot_count||
       record.capture_sequence_id!=journal->capture_sequence_id){
        photo_emit_source_status(failure_reason);
        return false;
    }
    result=photo_media_release_locked(&record);
    photo_store_observe_result(result);
    if(result!=PHOTO_MEDIA_STORE_OK){
        photo_emit_source_status(failure_reason);
        return false;
    }
    atomic_fetch_add(&photo_expired_released,1U);
    photo_emit_source_status(released_reason);
    return true;
}

static const char *photo_outcome_reason(const photo_capture_outcome_t *outcome)
{
    if(outcome->failure_reason)return outcome->failure_reason;
    if(outcome->camera.reason)return outcome->camera.reason;
    if(outcome->store_result!=PHOTO_MEDIA_STORE_OK&&
       outcome->store_result!=PHOTO_MEDIA_STORE_ALREADY_COMMITTED)
        return photo_media_store_result_name(outcome->store_result);
    return "capture_or_save_failed";
}

static bool photo_handle_capture_command(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    const photo_control_command_t *command,uint8_t *response,size_t response_capacity)
{
    photo_control_journal_t journal;photo_journal_snapshot(&journal);
    photo_control_capture_journal_t capture_journal;
    photo_capture_journal_snapshot(&capture_journal);
    const bool duplicate_id=journal.phase!=PHOTO_CONTROL_JOURNAL_NONE&&
        strcmp(journal.cmd_id,command->cmd_id)==0;
    if(duplicate_id&&journal.kind!=PHOTO_CONTROL_COMMAND_CAPTURE_ONCE){
        ESP_LOGE(TAG,"PHOTO_COMMAND id_reused_with_different_kind cmd=%s",command->cmd_id);
        return false;
    }
    const bool duplicate=duplicate_id;
    const bool pending_capture=capture_journal.phase!=PHOTO_CONTROL_CAPTURE_NONE&&
        capture_journal.kind==PHOTO_CONTROL_COMMAND_CAPTURE_ONCE&&
        !strcmp(capture_journal.command_id,command->cmd_id);
    if(capture_journal.phase!=PHOTO_CONTROL_CAPTURE_NONE&&!pending_capture)
        return false;
    if(duplicate&&journal.phase==PHOTO_CONTROL_JOURNAL_COMPLETE&&!pending_capture)
        return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
            true,response,response_capacity);
    uint64_t utc_ms=0U;const bool trusted_utc=photo_wall_clock(&utc_ms);
    photo_capture_intent_t intent;
    if(pending_capture)photo_intent_from_capture_journal(&capture_journal,&intent);
    else if(!trusted_utc||!photo_control_command_is_live(command,true,utc_ms)){
        photo_journal_fill(&journal,PHOTO_CONTROL_JOURNAL_COMPLETE,
            PHOTO_CONTROL_COMMAND_CAPTURE_ONCE,command->cmd_id,"error",
            trusted_utc?"capture_command_expired":"trusted_utc_unavailable",
            "none");
        if(!save_photo_journal(&journal))return false;
        photo_journal_publish(&journal);
        return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
            duplicate,response,response_capacity);
    }else if(!photo_intent_from_command(command,utc_ms,&intent))return false;
    if(!trusted_utc)return false;
    if(utc_ms>=intent.retention_expires_at_unix_ms){
        if(pending_capture){
            if(!photo_release_capture_for_retention(&capture_journal,
                "manual_capture_retention_expired_before_metadata",
                "photo_retention_release_failed"))return false;
            if(!photo_capture_clear())return false;
        }
        if(!photo_finish_journal(&journal,"error",
            "capture_retention_expired_before_metadata"))return false;
        return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
            true,response,response_capacity);
    }
    if(!duplicate){
        photo_journal_fill(&journal,PHOTO_CONTROL_JOURNAL_EXECUTING,
            PHOTO_CONTROL_COMMAND_CAPTURE_ONCE,command->cmd_id,"pending",
            "capture_started",intent.photo_id);
        if(!save_photo_journal(&journal))return false;
        photo_journal_publish(&journal);
    }else if(journal.phase==PHOTO_CONTROL_JOURNAL_EXECUTING&&
             strcmp(journal.photo_id,intent.photo_id)!=0)return false;

    photo_capture_outcome_t captured={0};
    if(!photo_capture_run_or_restore(&intent,&captured,&capture_journal))return false;
    if(captured.outcome_ambiguous){
        if(!photo_append_capture_metadata(&captured,
            "capture_outcome_unknown_after_reboot"))return false;
        if(!photo_finish_journal(&journal,"error",
            "capture_outcome_unknown_after_reboot"))return false;
        if(!photo_capture_clear())return false;
        photo_emit_source_status("manual_capture_outcome_unknown_after_reboot");
        return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
            true,response,response_capacity);
    }
    const bool media_saved=captured.media_saved;
    const bool metadata_saved=photo_append_capture_metadata(&captured,
        photo_outcome_reason(&captured));
    if(!metadata_saved)return false;
    const char *status=media_saved?"ok":"error";
    const char *message=media_saved?"photo_saved_metadata_queued":
        photo_outcome_reason(&captured);
    if(!photo_finish_journal(&journal,status,message))return false;
    if(!photo_capture_clear())return false;
    photo_emit_source_status(media_saved?"manual_capture_saved":"manual_capture_failed");
    return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
        duplicate,response,response_capacity);
}

static bool photo_timer_matches_command(const photo_control_timer_t *timer,
                                        const photo_control_command_t *command)
{
    return timer&&command&&strcmp(timer->command_id,command->cmd_id)==0&&
        strcmp(timer->authorization_session_id,command->authorization_session_id)==0&&
        strcmp(timer->config_version,command->config_version)==0&&
        strcmp(timer->retention_expires_at,command->retention_expires_at)==0&&
        timer->interval_seconds==command->interval_seconds&&
        timer->session_expires_at_unix_ms==command->session_expires_at_unix_ms&&
        timer->max_photos==command->max_photos;
}

static bool photo_handle_timer_command(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    const photo_control_command_t *command,uint8_t *response,size_t response_capacity)
{
    photo_control_journal_t journal;photo_journal_snapshot(&journal);
    const bool duplicate_id=journal.phase!=PHOTO_CONTROL_JOURNAL_NONE&&
        strcmp(journal.cmd_id,command->cmd_id)==0;
    if(duplicate_id&&journal.kind!=PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER){
        ESP_LOGE(TAG,"PHOTO_COMMAND id_reused_with_different_kind cmd=%s",command->cmd_id);
        return false;
    }
    const bool duplicate=duplicate_id;
    photo_control_timer_t timer;photo_timer_snapshot(&timer);
    if(duplicate&&journal.phase==PHOTO_CONTROL_JOURNAL_COMPLETE){
        if(command->timer_enabled&&
           !platform_camera_timed_capture_allowed()){
            if(!photo_finish_journal(&journal,"error",
                photo_timer_camera_policy_message()))return false;
            photo_emit_source_status(photo_timer_camera_policy_message());
            return photo_post_command_ack(https,route,interface_name,&journal,
                NULL,NULL,true,response,response_capacity);
        }
        /* A previously applied timer may now be disabled by its session
         * deadline or max-photo limit. That is an effective-state refresh,
         * not a rejected configuration. Keep `applied` and let timer_state
         * carry the truthful terminal state. A command that never applied
         * has no timer_state and repeats its durable error ACK. */
        const bool applied=strcmp(journal.status,"applied")==0&&
            photo_timer_matches_command(&timer,command);
        return photo_post_command_ack(https,route,interface_name,&journal,
            applied?&timer:NULL,applied?"applied":NULL,true,response,
            response_capacity);
    }
    uint64_t utc_ms=0U;const bool trusted=photo_wall_clock(&utc_ms);
    const char *camera_reason=NULL;
    const bool capture_ready=atomic_load(&media_store_ready)&&
        platform_camera_preflight(&camera_reason)==PLATFORM_CAMERA_OK;
    const bool timed_capture_allowed=platform_camera_timed_capture_allowed();
    if(!trusted||!photo_control_command_is_live(command,trusted,utc_ms)||
       (command->timer_enabled&&(!timed_capture_allowed||!capture_ready))){
        photo_journal_fill(&journal,PHOTO_CONTROL_JOURNAL_COMPLETE,
            PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER,command->cmd_id,"error",
            !trusted?"trusted_utc_unavailable":
            (!photo_control_command_is_live(command,trusted,utc_ms)?
             "timer_command_expired":(!timed_capture_allowed?
             photo_timer_camera_policy_message():
             "camera_runtime_unavailable")),"none");
        if(!save_photo_journal(&journal))return false;
        photo_journal_publish(&journal);
        photo_emit_source_status("timer_configuration_rejected");
        return photo_post_command_ack(https,route,interface_name,&journal,NULL,NULL,
            duplicate,response,response_capacity);
    }
    if(!duplicate){
        photo_journal_fill(&journal,PHOTO_CONTROL_JOURNAL_EXECUTING,
            PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER,command->cmd_id,"pending",
            "timer_configuration_started","none");
        if(!save_photo_journal(&journal))return false;
        photo_journal_publish(&journal);
    }
    if(!photo_control_timer_apply(&timer,command,true,utc_ms,(uint64_t)now_us()/1000U))
        return false;
    timer.status_report_pending=true;
    if(!save_photo_timer(&timer))return false;
    photo_timer_publish(&timer);
    if(!photo_finish_journal(&journal,"applied","timer_configuration_applied"))return false;
    photo_emit_source_status("timer_configuration_applied");
    const bool accepted=photo_post_command_ack(https,route,interface_name,&journal,
        &timer,"applied",duplicate,response,response_capacity);
    if(!accepted)return false;
    timer.status_report_pending=false;
    if(!save_photo_timer(&timer)){
        atomic_store(&photo_control_state_ready,false);return false;
    }
    photo_timer_publish(&timer);return true;
}

static bool photo_poll_and_handle_command(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    uint8_t *command_response,size_t command_capacity,
    uint8_t *ack_response,size_t ack_capacity)
{
    https->attempts=0U;https->deadline_ms=(uint64_t)now_us()/1000U+13000U;
    egolink_p0_delivery_post_result_t received={0};
    atomic_store(&uploader_active_generation,route->generation);
    const egolink_p0_delivery_post_outcome_t outcome=
        egolink_esp_p0_https_poll_collection_command(https,
            CONFIG_EGOLINK_DEVICE_ID,interface_name,command_response,command_capacity,
            upload_cancel,NULL,route->generation,&received);
    atomic_store(&uploader_active_generation,0U);
    atomic_fetch_add(&photo_command_polls,1U);
    if(outcome!=EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE||
       received.http_status_code<200U||received.http_status_code>=300U||
       atomic_load(&network_route_generation)!=route->generation){
        egolink_esp_p0_https_close(https);return false;
    }
    if(received.response_length==0U)return true;
    photo_control_command_t command;
    const photo_control_parse_result_t parsed=photo_control_parse_raw_command(
        command_response,received.response_length,&command);
    if(parsed==PHOTO_CONTROL_PARSE_EMPTY)return true;
    if(parsed!=PHOTO_CONTROL_PARSE_OK){
        atomic_fetch_add(&photo_command_parse_failures,1U);
        ESP_LOGE(TAG,"PHOTO_COMMAND parse=%s ack=false",
            photo_control_parse_result_name(parsed));
        return false;
    }
    return command.kind==PHOTO_CONTROL_COMMAND_CAPTURE_ONCE?
        photo_handle_capture_command(https,route,interface_name,&command,
            ack_response,ack_capacity):
        photo_handle_timer_command(https,route,interface_name,&command,
            ack_response,ack_capacity);
}

static bool photo_timer_matches_capture_journal(
    const photo_control_timer_t *timer,
    const photo_control_capture_journal_t *journal)
{
    return timer&&journal&&journal->kind==PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER&&
        !strcmp(timer->command_id,journal->command_id)&&
        !strcmp(timer->config_version,journal->config_version)&&
        !strcmp(timer->authorization_session_id,
            journal->authorization_session_id)&&
        !strcmp(timer->retention_expires_at,journal->retention_expires_at)&&
        timer->session_expires_at_unix_ms==journal->execution_expires_at_unix_ms&&
        timer->retention_expires_at_unix_ms==journal->retention_expires_at_unix_ms;
}

static bool photo_settle_timer_capture(photo_control_timer_t *timer,
    photo_control_capture_journal_t *capture_journal,
    photo_capture_outcome_t *captured,uint64_t now_utc_ms)
{
    if(!photo_timer_matches_capture_journal(timer,capture_journal)||
       !now_utc_ms)return false;
    if(now_utc_ms>=capture_journal->retention_expires_at_unix_ms){
        if(!photo_release_capture_for_retention(capture_journal,
            "timer_capture_retention_expired_before_metadata",
            "photo_retention_release_failed"))return false;
        const uint32_t before=capture_journal->timer_captured_count_before;
        if(capture_journal->phase==PHOTO_CONTROL_CAPTURE_RESULT&&
           capture_journal->media_saved&&timer->captured_photos==before)
            ++timer->captured_photos;
        else if(timer->captured_photos!=before&&
                timer->captured_photos!=before+1U)return false;
        timer->enabled=false;timer->schedule_armed=false;
        timer->status_report_pending=true;
        snprintf(timer->state_reason,sizeof(timer->state_reason),
            "capture_retention_expired");
        (void)photo_timer_enforce_camera_policy(timer);
        if(!save_photo_timer(timer))return false;
        photo_timer_publish(timer);
        return photo_capture_clear();
    }
    if(!captured)return false;
    if(captured->outcome_ambiguous){
        if(!photo_append_capture_metadata(captured,
            "capture_outcome_unknown_after_reboot"))return false;
        photo_control_timer_complete_attempt(timer,false,(uint64_t)now_us()/1000U);
        timer->status_report_pending=true;
        snprintf(timer->state_reason,sizeof(timer->state_reason),
            "capture_outcome_ambiguous");
        (void)photo_timer_enforce_camera_policy(timer);
        if(!save_photo_timer(timer))return false;
        photo_timer_publish(timer);
        if(!photo_capture_clear())return false;
        photo_emit_source_status("timer_capture_outcome_unknown_after_reboot");
        return true;
    }
    if(!photo_append_capture_metadata(captured,
        photo_outcome_reason(captured)))return false;
    const uint32_t before=capture_journal->timer_captured_count_before;
    if(captured->media_saved){
        if(timer->captured_photos==before)
            photo_control_timer_complete_attempt(timer,true,
                (uint64_t)now_us()/1000U);
        else if(timer->captured_photos!=before+1U)return false;
    }else{
        if(timer->captured_photos!=before)return false;
        photo_control_timer_complete_attempt(timer,false,(uint64_t)now_us()/1000U);
        if(captured->store_result==PHOTO_MEDIA_STORE_FULL||
           captured->store_result==PHOTO_MEDIA_STORE_TOO_LARGE||
           captured->store_result==PHOTO_MEDIA_STORE_IDENTITY_CONFLICT||
           photo_store_result_fatal(captured->store_result)){
            timer->enabled=false;timer->schedule_armed=false;
            timer->status_report_pending=true;
            snprintf(timer->state_reason,sizeof(timer->state_reason),"%s",
                captured->store_result==PHOTO_MEDIA_STORE_FULL?"media_store_full":
                captured->store_result==PHOTO_MEDIA_STORE_TOO_LARGE?"jpeg_too_large":
                captured->store_result==PHOTO_MEDIA_STORE_IDENTITY_CONFLICT?
                    "photo_identity_conflict":"media_store_unavailable");
        }
    }
    (void)photo_timer_enforce_camera_policy(timer);
    if(!save_photo_timer(timer))return false;
    photo_timer_publish(timer);
    if(!photo_capture_clear())return false;
    photo_emit_source_status(captured->media_saved?
        "timer_capture_saved":"timer_capture_failed");
    return true;
}

static bool photo_settle_pending_manual_capture(
    photo_control_capture_journal_t *capture_journal)
{
    if(!capture_journal||
       capture_journal->kind!=PHOTO_CONTROL_COMMAND_CAPTURE_ONCE)return false;
    uint64_t utc_ms=0U;if(!photo_wall_clock(&utc_ms))return false;
    photo_control_journal_t command_journal;photo_journal_snapshot(&command_journal);
    if(command_journal.kind!=PHOTO_CONTROL_COMMAND_CAPTURE_ONCE||
       command_journal.phase==PHOTO_CONTROL_JOURNAL_NONE||
       strcmp(command_journal.cmd_id,capture_journal->command_id))return false;
    if(utc_ms>=capture_journal->retention_expires_at_unix_ms){
        if(!photo_release_capture_for_retention(capture_journal,
            "manual_capture_retention_expired_before_metadata",
            "photo_retention_release_failed"))return false;
        if(!photo_finish_journal(&command_journal,"error",
            "capture_retention_expired_before_metadata")||
           !photo_capture_clear())return false;
        return true;
    }
    photo_capture_outcome_t recovered;
    if(!photo_capture_restore_outcome(capture_journal,&recovered))return false;
    if(!photo_append_capture_metadata(&recovered,
        recovered.outcome_ambiguous?"capture_outcome_unknown_after_reboot":
            photo_outcome_reason(&recovered)))return false;
    if(!photo_finish_journal(&command_journal,
        recovered.media_saved?"ok":"error",
        recovered.media_saved?"photo_saved_metadata_queued":
        (recovered.outcome_ambiguous?"capture_outcome_unknown_after_reboot":
            photo_outcome_reason(&recovered))))return false;
    if(!photo_capture_clear())return false;
    photo_emit_source_status(recovered.media_saved?"manual_capture_recovered":
        (recovered.outcome_ambiguous?
            "manual_capture_outcome_unknown_after_reboot":
            "manual_capture_failure_recovered"));
    return true;
}

static void photo_capture_settle_retry_reset(unsigned *backoff_ms,
                                             int64_t *next_retry_us)
{
    if(backoff_ms)*backoff_ms=PHOTO_CAPTURE_SETTLE_RETRY_INITIAL_MS;
    if(next_retry_us)*next_retry_us=0;
}

static void photo_capture_settle_retry_schedule(unsigned *backoff_ms,
                                                int64_t *next_retry_us)
{
    if(!backoff_ms||!next_retry_us)return;
    const unsigned delay=*backoff_ms;
    *next_retry_us=now_us()+(int64_t)delay*1000LL;
    if(*backoff_ms<PHOTO_CAPTURE_SETTLE_RETRY_MAX_MS)
        *backoff_ms=*backoff_ms>PHOTO_CAPTURE_SETTLE_RETRY_MAX_MS/2U?
            PHOTO_CAPTURE_SETTLE_RETRY_MAX_MS:*backoff_ms*2U;
    ESP_LOGW(TAG,"PHOTO_CAPTURE_SETTLE_RETRY delay_ms=%u durable_journal=true",
        delay);
}

static bool photo_capture_settle_retry_due(
    const photo_control_capture_journal_t *capture_journal,int64_t now,
    int64_t next_retry_us)
{
    if(now>=next_retry_us)return true;
    uint64_t utc_ms=0U;
    return capture_journal&&photo_wall_clock(&utc_ms)&&
        utc_ms>=capture_journal->retention_expires_at_unix_ms;
}

static void photo_service_local_timer(unsigned *capture_settle_backoff_ms,
                                      int64_t *next_capture_settle_us)
{
    if(!capture_settle_backoff_ms||!next_capture_settle_us||
       !atomic_load(&photo_control_state_ready))return;
    photo_control_timer_t timer;photo_timer_snapshot(&timer);
    photo_control_capture_journal_t capture_journal;
    photo_capture_journal_snapshot(&capture_journal);
    if(capture_journal.phase!=PHOTO_CONTROL_CAPTURE_NONE){
        if(!photo_capture_settle_retry_due(&capture_journal,now_us(),
                                           *next_capture_settle_us))return;
        bool settled=false;
        if(capture_journal.kind==PHOTO_CONTROL_COMMAND_CAPTURE_ONCE){
            settled=photo_settle_pending_manual_capture(&capture_journal);
            if(settled)photo_capture_settle_retry_reset(
                capture_settle_backoff_ms,next_capture_settle_us);
            else photo_capture_settle_retry_schedule(
                capture_settle_backoff_ms,next_capture_settle_us);
            return;
        }
        if(capture_journal.kind!=PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER||
           !photo_timer_matches_capture_journal(&timer,&capture_journal)){
            photo_capture_settle_retry_schedule(capture_settle_backoff_ms,
                next_capture_settle_us);
            return;
        }
        uint64_t recovery_utc_ms=0U;
        if(!photo_wall_clock(&recovery_utc_ms)){
            photo_capture_settle_retry_schedule(capture_settle_backoff_ms,
                next_capture_settle_us);
            return;
        }
        if(recovery_utc_ms>=capture_journal.retention_expires_at_unix_ms){
            settled=photo_settle_timer_capture(&timer,&capture_journal,NULL,
                recovery_utc_ms);
        }else{
            photo_capture_outcome_t recovered;
            if(photo_capture_restore_outcome(&capture_journal,&recovered))
                settled=photo_settle_timer_capture(&timer,&capture_journal,
                    &recovered,recovery_utc_ms);
        }
        if(settled)photo_capture_settle_retry_reset(capture_settle_backoff_ms,
            next_capture_settle_us);
        else photo_capture_settle_retry_schedule(capture_settle_backoff_ms,
            next_capture_settle_us);
        return;
    }
    photo_capture_settle_retry_reset(capture_settle_backoff_ms,
        next_capture_settle_us);
    const char *preflight_reason=NULL;
    const bool timer_policy_rejected=
        !platform_camera_timed_capture_allowed();
    if(timer.enabled&&(timer_policy_rejected||
       !atomic_load(&media_store_ready)||
       platform_camera_preflight(&preflight_reason)!=PLATFORM_CAMERA_OK)){
        timer.enabled=false;timer.schedule_armed=false;timer.status_report_pending=true;
        snprintf(timer.state_reason,sizeof(timer.state_reason),"%s",
            timer_policy_rejected?photo_timer_camera_policy_state_reason():
            (atomic_load(&media_store_ready)?"camera_runtime_unavailable":
            "media_store_unavailable"));
        if(!save_photo_timer(&timer)){
            atomic_store(&photo_control_state_ready,false);
            return;
        }
        photo_timer_publish(&timer);
        photo_emit_source_status(timer_policy_rejected?
            photo_timer_camera_policy_message():
            (preflight_reason?preflight_reason:
            "timer_disabled_runtime_unavailable"));
        return;
    }
    uint64_t utc_ms=0U;const bool trusted=photo_wall_clock(&utc_ms);
    const bool was_armed=timer.schedule_armed;
    const photo_control_timer_decision_t decision=photo_control_timer_tick(&timer,
        trusted,utc_ms,(uint64_t)now_us()/1000U);
    if(decision==PHOTO_CONTROL_TIMER_WAITING_FOR_TRUSTED_UTC){
        if(was_armed)photo_timer_publish(&timer);
        return;
    }
    if(decision==PHOTO_CONTROL_TIMER_EXPIRED||
       decision==PHOTO_CONTROL_TIMER_LIMIT_REACHED){
        if(!save_photo_timer(&timer)){atomic_store(&photo_control_state_ready,false);return;}
        photo_timer_publish(&timer);
        photo_emit_source_status(decision==PHOTO_CONTROL_TIMER_EXPIRED?
            "timer_session_expired":"timer_max_photos_reached");
        return;
    }
    if(decision==PHOTO_CONTROL_TIMER_WAITING){
        if(!was_armed){photo_timer_publish(&timer);photo_emit_source_status("timer_interval_armed");}
        return;
    }
    if(decision!=PHOTO_CONTROL_TIMER_DUE)return;
    photo_capture_intent_t intent;
    if(!photo_intent_from_timer(&timer,utc_ms,&intent))return;
    photo_capture_outcome_t captured={0};
    if(!photo_capture_run_or_restore(&intent,&captured,&capture_journal)||
       !photo_settle_timer_capture(&timer,&capture_journal,&captured,utc_ms)){
        photo_capture_settle_retry_schedule(capture_settle_backoff_ms,
            next_capture_settle_us);
        return;
    }
    photo_capture_settle_retry_reset(capture_settle_backoff_ms,
        next_capture_settle_us);
}

static bool photo_post_pending_timer_state(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    uint8_t *response,size_t response_capacity)
{
    photo_control_timer_t timer;photo_timer_snapshot(&timer);
    if(!timer.status_report_pending||!timer.command_id[0])return false;
    const bool camera_policy_rejected=
        photo_timer_camera_policy_rejected(timer.state_reason);
    photo_control_journal_t report;
    photo_journal_fill(&report,PHOTO_CONTROL_JOURNAL_COMPLETE,
        PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER,timer.command_id,
        camera_policy_rejected?"error":"applied",
        camera_policy_rejected?
            photo_timer_camera_policy_message_for_reason(timer.state_reason):
            timer.state_reason,"none");
    if(!photo_post_command_ack(https,route,interface_name,&report,
        camera_policy_rejected?NULL:&timer,
        camera_policy_rejected?NULL:"applied",
        true,response,response_capacity))return true;
    timer.status_report_pending=false;
    if(!save_photo_timer(&timer)){atomic_store(&photo_control_state_ready,false);return true;}
    photo_timer_publish(&timer);return true;
}

static bool photo_release_one_expired(uint32_t *scan_cursor)
{
    if(!scan_cursor||!atomic_load(&media_store_ready))return false;
    uint64_t utc_ms=0U;if(!photo_wall_clock(&utc_ms))return false;
    photo_media_store_record_t record;
    photo_media_store_result_t store=photo_media_peek_locked(*scan_cursor,
        &record);
    photo_store_observe_result(store);
    if(store==PHOTO_MEDIA_STORE_NOT_FOUND){*scan_cursor=0U;return false;}
    if(store!=PHOTO_MEDIA_STORE_OK)return false;
    photo_media_store_stats_t stats={0};
    if(!photo_media_stats_locked(&stats)){
        photo_store_observe_result(PHOTO_MEDIA_STORE_IO_ERROR);
        return false;
    }
    const uint32_t slot_count=(uint32_t)(stats.capacity_bytes/stats.slot_bytes);
    *scan_cursor=record.slot+1U>=slot_count?0U:record.slot+1U;
    if(utc_ms<record.retention_expires_at_unix_ms)return false;
    store=photo_media_release_locked(&record);
    photo_store_observe_result(store);
    if(store!=PHOTO_MEDIA_STORE_OK){
        photo_emit_source_status("photo_retention_release_failed");
        return false;
    }
    atomic_fetch_add(&photo_expired_released,1U);
    photo_emit_source_status("photo_retention_expired_local_release");
    return true;
}

static bool photo_upload_one(egolink_esp_p0_https_t *https,
    const network_runtime_snapshot_t *route,const char *interface_name,
    uint8_t *response,size_t response_capacity,uint32_t *scan_cursor,
    uint32_t *http_status,bool *server_verified_out)
{
    if(http_status)*http_status=0U;
    if(server_verified_out)*server_verified_out=false;
    if(!scan_cursor||!atomic_load(&media_store_ready))return false;
    photo_media_store_record_t record;
    photo_media_store_result_t store=photo_media_peek_locked(*scan_cursor,
        &record);
    photo_store_observe_result(store);
    if(store==PHOTO_MEDIA_STORE_NOT_FOUND){*scan_cursor=0U;return false;}
    if(store!=PHOTO_MEDIA_STORE_OK){
        atomic_fetch_add(&photo_upload_failures,1U);
        if(!atomic_load(&media_store_ready))
            photo_emit_source_status("photo_media_store_runtime_failure");
        return true;
    }
    photo_media_store_stats_t stats={0};
    if(!photo_media_stats_locked(&stats)){
        photo_store_observe_result(PHOTO_MEDIA_STORE_IO_ERROR);
        atomic_fetch_add(&photo_upload_failures,1U);
        return true;
    }
    const uint32_t slot_count=(uint32_t)(stats.capacity_bytes/stats.slot_bytes);
    *scan_cursor=record.slot+1U>=slot_count?0U:record.slot+1U;
    uint64_t utc_ms=0U;if(!photo_wall_clock(&utc_ms))return true;
    if(utc_ms>=record.retention_expires_at_unix_ms){
        store=photo_media_release_locked(&record);
        photo_store_observe_result(store);
        if(store==PHOTO_MEDIA_STORE_OK){
            atomic_fetch_add(&photo_expired_released,1U);
            photo_emit_source_status("photo_retention_expired_local_release");
        }else{
            atomic_fetch_add(&photo_upload_failures,1U);
            photo_emit_source_status("photo_retention_release_failed");
        }
        return true;
    }
    const uint64_t metadata_identity=
        ((uint64_t)record.capture_boot_count<<32U)|record.capture_sequence_id;
    if(metadata_identity>photo_metadata_ack_watermark)return false;
    static uint8_t jpeg[CONFIG_EGOLINK_PHOTO_MEDIA_MAX_PAYLOAD_BYTES];
    if(record.payload_bytes>sizeof(jpeg)){
        atomic_fetch_add(&photo_upload_failures,1U);return true;
    }
    store=photo_media_read_locked(&record,0U,jpeg,record.payload_bytes);
    photo_store_observe_result(store);
    if(store!=PHOTO_MEDIA_STORE_OK){
        atomic_fetch_add(&photo_upload_failures,1U);
        if(!atomic_load(&media_store_ready))
            photo_emit_source_status("photo_media_store_runtime_failure");
        return true;
    }
    char digest[65];photo_digest_hex(record.sha256,digest);
    https->attempts=0U;https->deadline_ms=(uint64_t)now_us()/1000U+13000U;
    egolink_p0_delivery_post_result_t posted={0};
    atomic_store(&uploader_active_generation,route->generation);
    const egolink_p0_delivery_post_outcome_t outcome=
        egolink_esp_p0_https_upload_collection_photo(https,
            CONFIG_EGOLINK_DEVICE_ID,record.photo_id,digest,interface_name,
            jpeg,record.payload_bytes,response,response_capacity,upload_cancel,NULL,
            route->generation,&posted);
    atomic_store(&uploader_active_generation,0U);
    if(http_status)*http_status=posted.http_status_code;
    const bool server_verified=outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE&&
        posted.http_status_code>=200U&&posted.http_status_code<300U&&
        atomic_load(&network_route_generation)==route->generation&&
        photo_delivery_content_ack_response_matches(response,posted.response_length,
            CONFIG_EGOLINK_DEVICE_ID,record.photo_id,digest,record.payload_bytes);
    if(server_verified_out)*server_verified_out=server_verified;
    bool released=false;
    if(server_verified){
        store=photo_media_release_locked(&record);
        photo_store_observe_result(store);
        released=store==PHOTO_MEDIA_STORE_OK;
        if(released)atomic_fetch_add(&photo_upload_acked,1U);
        else{
            atomic_fetch_add(&photo_upload_failures,1U);
            if(!atomic_load(&media_store_ready))
                photo_emit_source_status("photo_release_failed_after_server_verified");
            egolink_esp_p0_https_close(https);
        }
    }else{
        atomic_fetch_add(&photo_upload_failures,1U);
        egolink_esp_p0_https_close(https);
    }
    ESP_LOGI(TAG,"PHOTO_UPLOAD photo=%s http=%u server_verified=%d released=%d bytes=%u",
        record.photo_id,(unsigned)posted.http_status_code,server_verified,released,
        (unsigned)record.payload_bytes);
    return true;
}

static void photo_schedule_upload_retry(bool server_verified,uint32_t http_status,
    unsigned *backoff_ms,int64_t *next_upload_us)
{
    if(!backoff_ms||!next_upload_us)return;
    if(server_verified){
        *backoff_ms=CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_INITIAL_MS;
        *next_upload_us=now_us()+50000LL;
        return;
    }
    const unsigned delay=*backoff_ms;
    *next_upload_us=now_us()+(int64_t)delay*1000LL;
    if(*backoff_ms<CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_MAX_MS)
        *backoff_ms=*backoff_ms>CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_MAX_MS/2U?
            CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_MAX_MS:*backoff_ms*2U;
    ESP_LOGW(TAG,"PHOTO_UPLOAD_RETRY http=%u delay_ms=%u exact_ack=false",
        (unsigned)http_status,delay);
}
#endif
static void uploader_task(void *unused)
{
    (void)unused;bool anchored=false;
    int64_t next_send=0;unsigned backoff=1000,durable_streak=0,connection_generation=0;
    static char buffer[COLLECTION_FRAME_CAPACITY],loss_buffer[COLLECTION_FRAME_CAPACITY];
    static uint8_t response[8192];
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    int64_t next_command_poll=0,next_photo_upload=0,next_timer_report=0;
    int64_t next_retention_scan=0,next_photo_fair_deadline=0;
    int64_t next_capture_settle=0;
    unsigned photo_backoff=CONFIG_EGOLINK_PHOTO_UPLOAD_RETRY_INITIAL_MS;
    unsigned capture_settle_backoff=PHOTO_CAPTURE_SETTLE_RETRY_INITIAL_MS;
    unsigned ordinary_uploads_since_photo=0U;
    uint32_t photo_upload_cursor=0U,photo_retention_cursor=0U;
    static uint8_t command_response[2048],command_ack_response[8192];
    photo_stack_hwm_observe(&photo_upload_stack_hwm_bytes);
#endif
    egolink_esp_p0_https_t https={.origin=CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL,.expected_host=CONFIG_EGOLINK_MESSAGE_HUB_EXPECTED_TLS_HOST,
        .bearer=CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN,.max_attempts=1,.transaction_timeout_ms=12000,.reuse_connection=true};
    while(!atomic_load(&stopping)) {
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_stack_hwm_observe(&photo_upload_stack_hwm_bytes);
#endif
        int64_t now=now_us();network_runtime_snapshot_t route=read_network();
        if(connection_generation!=route.generation||route.route==COLLECTION_NETWORK_ROUTE_NONE){
            egolink_esp_p0_https_close(&https);connection_generation=route.generation;
            atomic_store(&uploader_retired_generation,route.generation);
        }
        if(route.route!=COLLECTION_NETWORK_ROUTE_NONE&&!anchored) {
            struct timeval t;if(gettimeofday(&t,NULL)==0&&t.tv_sec>=1767225600&&t.tv_sec<4102444800LL) {
                int64_t mono=now_us(),utc=(int64_t)t.tv_sec*1000000+t.tv_usec;
                cJSON *p=cJSON_CreateObject();cJSON_AddNumberToObject(p,"timestamp_monotonic_ns",(double)mono*1000);
                cJSON_AddNumberToObject(p,"utc_ms",utc/1000);cJSON_AddStringToObject(p,"source","sntp");
                cJSON_AddNullToObject(p,"uncertainty_ms");cJSON_AddStringToObject(p,"uncertainty_reason","not_measured");
                emit(ANCHOR,mono,"observed",NULL,p,true);
                portENTER_CRITICAL(&clock_mux);utc_offset_us=utc-mono;portEXIT_CRITICAL(&clock_mux);anchored=true;
            }
        }
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        photo_service_local_timer(&capture_settle_backoff,&next_capture_settle);
        if(now>=next_retention_scan){
            (void)photo_release_one_expired(&photo_retention_cursor);
            next_retention_scan=now_us()+1000000LL;
        }
#endif
        if(route.route==COLLECTION_NETWORK_ROUTE_NONE||!route.netif||!anchored) {
            vTaskDelay(pdMS_TO_TICKS(100));continue;
        }
        char interface_name[16]={0};
        if(esp_netif_get_netif_impl_name(route.netif,interface_name)!=ESP_OK||
           !interface_matches_route(route.route,interface_name)){
            next_send=now+5000000;vTaskDelay(pdMS_TO_TICKS(100));continue;
        }
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        if(now>=next_timer_report){
            if(photo_post_pending_timer_state(&https,&route,interface_name,
                command_ack_response,sizeof(command_ack_response))){
                next_timer_report=now_us()+5000000LL;continue;
            }
            next_timer_report=now+5000000LL;
        }
        photo_control_capture_journal_t pending_capture;
        photo_capture_journal_snapshot(&pending_capture);
        if(atomic_load(&photo_control_state_ready)&&
           photo_control_capture_journal_allows_new_command(&pending_capture)&&
           now>=next_command_poll){
            const bool command_ok=photo_poll_and_handle_command(&https,&route,
                interface_name,command_response,sizeof(command_response),
                command_ack_response,sizeof(command_ack_response));
            if(!command_ok){
                photo_control_capture_journal_t capture_after_command;
                photo_capture_journal_snapshot(&capture_after_command);
                if(capture_after_command.phase!=PHOTO_CONTROL_CAPTURE_NONE)
                    photo_capture_settle_retry_schedule(&capture_settle_backoff,
                        &next_capture_settle);
            }
            next_command_poll=now_us()+(command_ok?
                CONFIG_EGOLINK_PHOTO_COMMAND_POLL_INTERVAL_MS:5000)*1000LL;
            continue;
        }
        if(now>=next_photo_upload&&
           (ordinary_uploads_since_photo>=PHOTO_ORDINARY_UPLOAD_BUDGET||
            now>=next_photo_fair_deadline)){
            uint32_t photo_http=0U;bool server_verified=false;
            const bool attempted=photo_upload_one(&https,&route,interface_name,
                response,sizeof(response),&photo_upload_cursor,&photo_http,
                &server_verified);
            next_photo_fair_deadline=now_us()+PHOTO_FAIR_UPLOAD_INTERVAL_US;
            ordinary_uploads_since_photo=0U;
            if(attempted){
                photo_schedule_upload_retry(server_verified,photo_http,
                    &photo_backoff,&next_photo_upload);
                continue;
            }
        }
#endif
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
            if(!ram&&xQueuePeek(ram_fallback,&ram,0)!=pdTRUE){
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
                if(atomic_load(&spool_ready)&&now>=next_photo_upload){
                    uint32_t photo_http=0U;
                    bool server_verified=false;
                    const bool attempted=photo_upload_one(&https,&route,interface_name,
                        response,sizeof(response),&photo_upload_cursor,&photo_http,
                        &server_verified);
                    if(attempted){
                        ordinary_uploads_since_photo=0U;
                        next_photo_fair_deadline=now_us()+
                            PHOTO_FAIR_UPLOAD_INTERVAL_US;
                        photo_schedule_upload_retry(server_verified,photo_http,
                            &photo_backoff,&next_photo_upload);
                        continue;
                    }
                }
#endif
                vTaskDelay(pdMS_TO_TICKS(100));continue;
            }
            body=ram->bytes;length=ram->length;
        }
        if(now<next_send){
            if(durable){xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);}
            vTaskDelay(pdMS_TO_TICKS(100));continue;
        }
        if(!length){
            if(durable){xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);}
            atomic_fetch_add(&send_errors,1);next_send=now+60000000;continue;
        }
        https.attempts=0;https.deadline_ms=(uint64_t)now_us()/1000+13000;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        ++ordinary_uploads_since_photo;
#endif
        egolink_p0_delivery_post_request_t request={.body=(uint8_t*)body,.body_length=length,.response=response,.response_capacity=sizeof(response),
            .cancel_requested=upload_cancel,.transfer_generation=route.generation};
        egolink_p0_delivery_post_result_t posted={0};
        atomic_store(&uploader_active_generation,route.generation);
        egolink_p0_delivery_post_outcome_t outcome=egolink_esp_p0_https_post_collection(&https,CONFIG_EGOLINK_DEVICE_ID,interface_name,&request,&posted);
        atomic_store(&uploader_active_generation,0);
        uint32_t latest_generation=atomic_load(&network_route_generation);
        if(latest_generation!=route.generation){egolink_esp_p0_https_close(&https);atomic_store(&uploader_retired_generation,latest_generation);}
        bool matched=outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE&&posted.http_status_code>=200&&posted.http_status_code<300&&
            latest_generation==route.generation&&collection_record_ack_matches(body,length,CONFIG_EGOLINK_DEVICE_ID,response,posted.response_length);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        if(matched&&durable&&record.kind==COLLECTION_SPOOL_METADATA&&
           record.source_id==CAMERA&&!photo_record_metadata_acked(record.source_seq))
            matched=false;
#endif
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
        if(durable){xSemaphoreTake(spool_mutex,portMAX_DELAY);collection_spool_unpin(&spool);xSemaphoreGive(spool_mutex);}
        ESP_LOGI(TAG,"UPLOAD interface=%s route=%s generation=%" PRIu32 " http=%u matched=%d durable=%d bytes=%u",
            interface_name,collection_network_route_name(route.route),route.generation,
            (unsigned)posted.http_status_code,matched,durable,(unsigned)length);
    }
    egolink_esp_p0_https_close(&https);
    atomic_store(&uploader_active_generation,0);
    atomic_store(&uploader_retired_generation,atomic_load(&network_route_generation));
    atomic_store(&uploader_finished,true);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_stack_hwm_observe(&photo_upload_stack_hwm_bytes);
#endif
    ESP_LOGI(TAG,"UPLOADER stopped=true durable_cache_preserved=true volatile_ram_pending=%u",(unsigned)uxQueueMessagesWaiting(ram_fallback));vTaskDelete(NULL);
}
void app_main(void)
{
    session_start_us=now_us();
    const esp_app_desc_t *application=esp_app_get_description();
    for(unsigned i=0;i<32;i++)snprintf(firmware_elf_sha256+i*2,3,"%02x",application->app_elf_sha256[i]);
    if(!boot_identity()) {ESP_LOGE(TAG,"STOP identity_persistence_failed nvs_preserved=true");return;}
    ingress=xQueueCreate(16,sizeof(queued_t*));
    ram_fallback=xQueueCreate(4,sizeof(queued_t*));
    spool_mutex=xSemaphoreCreateMutex();
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    media_store_mutex=xSemaphoreCreateMutex();
    atomic_store(&photo_main_stack_hwm_bytes,UINT_MAX);
    atomic_store(&photo_store_stack_hwm_bytes,UINT_MAX);
    atomic_store(&photo_imu_stack_hwm_bytes,UINT_MAX);
    atomic_store(&photo_modem_stack_hwm_bytes,UINT_MAX);
    atomic_store(&photo_upload_stack_hwm_bytes,UINT_MAX);
    atomic_store(&photo_wifi_stack_hwm_bytes,UINT_MAX);
#endif
    bool allocation_failed=!ingress||!ram_fallback||!spool_mutex;
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    allocation_failed=allocation_failed||!media_store_mutex;
#endif
    if(allocation_failed){
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
        if(media_store_mutex){vSemaphoreDelete(media_store_mutex);media_store_mutex=NULL;}
#endif
        if(spool_mutex){vSemaphoreDelete(spool_mutex);spool_mutex=NULL;}
        if(ram_fallback){vQueueDelete(ram_fallback);ram_fallback=NULL;}
        if(ingress){vQueueDelete(ingress);ingress=NULL;}
        ESP_LOGE(TAG,"STOP allocation_failed queues_and_mutexes_released=true");
        return;
    }
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    const bool photo_state_initialized=photo_control_state_init();
    atomic_store(&photo_control_state_ready,photo_state_initialized);
    if(!photo_state_initialized)
        ESP_LOGE(TAG,"PHOTO_CONTROL init=blocked reason=nvs_state_missing_or_corrupt fail_closed=true");
#endif
    partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x41,"ego_collection");
    if(partition && !partition->encrypted && partition->erase_size==4096 && partition->address==COLLECTION_PARTITION_ADDRESS && partition->size==COLLECTION_PARTITION_SIZE) {
        collection_spool_config_t config={.context=(void*)partition,.read=flash_read,.write=flash_write,.erase=flash_erase,.capacity_bytes=partition->size,.erase_bytes=4096,.protected_sectors=8,.evict_oldest=true};
        collection_spool_result_t r=collection_spool_init(&spool,&config);spool_ready=r==COLLECTION_SPOOL_OK;
        ESP_LOGI(TAG,"STORAGE init=%s capacity=%u foreign_data_preserved=true",collection_spool_result_name(r),(unsigned)partition->size);
    } else ESP_LOGE(TAG,"STORAGE init=blocked reason=partition_guard_failed expected_address=0x%x expected_size=0x%x",
        (unsigned)COLLECTION_PARTITION_ADDRESS,(unsigned)COLLECTION_PARTITION_SIZE);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    media_partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x42,"ego_media");
    if(media_partition&&!media_partition->encrypted&&media_partition->erase_size==4096&&
       media_partition->address==MEDIA_PARTITION_ADDRESS&&media_partition->size==MEDIA_PARTITION_SIZE){
        photo_media_store_config_t config={.context=(void*)media_partition,.read=flash_read,.write=flash_write,.erase=flash_erase,
            .capacity_bytes=media_partition->size,.erase_bytes=4096,.slot_bytes=CONFIG_EGOLINK_PHOTO_MEDIA_SLOT_BYTES,
            .max_payload_bytes=CONFIG_EGOLINK_PHOTO_MEDIA_MAX_PAYLOAD_BYTES,
            .max_committed_photos=CONFIG_EGOLINK_PHOTO_MEDIA_MAX_COMMITTED_PHOTOS,
            .max_committed_payload_bytes=CONFIG_EGOLINK_PHOTO_MEDIA_MAX_TOTAL_PAYLOAD_BYTES};
        photo_media_store_stats_t stats={0};
        photo_media_store_result_t r=photo_media_init_locked(&config,&stats);
        atomic_store(&media_store_ready,r==PHOTO_MEDIA_STORE_OK);
        ESP_LOGI(TAG,"MEDIA_STORE init=%s ready=%d dedicated_partition=true capacity=%u slot_bytes=%u committed=%u torn=%u corrupt=%u reconciled=%u residual_torn=%u residual_corrupt=%u residual_unrecognized=%u",
            photo_media_store_result_name(r),media_store_ready,(unsigned)media_partition->size,(unsigned)config.slot_bytes,
            (unsigned)stats.committed_slots,(unsigned)stats.torn_slots,
            (unsigned)stats.corrupt_slots,(unsigned)stats.reconciled_owned_slots,
            (unsigned)stats.reconciled_torn_slots,
            (unsigned)stats.reconciled_corrupt_slots,
            (unsigned)stats.reconciled_unrecognized_slots);
    }else ESP_LOGE(TAG,"MEDIA_STORE init=blocked reason=partition_guard_failed expected_address=0x%x expected_size=0x%x",
        (unsigned)MEDIA_PARTITION_ADDRESS,(unsigned)MEDIA_PARTITION_SIZE);
#endif
    platform_power_init();
    bool wifi_started=network_init();
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    const char *camera_reason=NULL;platform_camera_status_t camera_preflight=platform_camera_preflight(&camera_reason);
    const platform_camera_shared_i2c_state_t camera_shared_i2c_state=
        platform_camera_shared_i2c_state();
    const bool camera_runtime_ready=photo_camera_manual_capture_ready(
        camera_preflight)&&
        atomic_load(&media_store_ready)&&atomic_load(&photo_control_state_ready);
    ESP_LOGI(TAG,"START boot=%" PRIu32 " firmware=%s no_sim_profile=%d run_seconds=%d camera_profile=%d camera_shared_i2c_state=%s camera_preflight=%s camera_reason=%s trial_attempt_consumed=%d timer_capture_allowed=%d wifi_stack=%d lte_ppp_opt_in=%d",boot,CONFIG_EGOLINK_FW_VERSION,CONFIG_EGOLINK_COLLECTION_NO_SIM,CONFIG_EGOLINK_COLLECTION_RUN_SECONDS,CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE,platform_camera_shared_i2c_state_name(camera_shared_i2c_state),platform_camera_status_name(camera_preflight),camera_reason?camera_reason:"none",platform_camera_unverified_trial_attempt_consumed(),platform_camera_timed_capture_allowed(),network_stack_ready,CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED);
#else
    ESP_LOGI(TAG,"START boot=%" PRIu32 " firmware=%s no_sim_profile=%d run_seconds=%d media=false wifi_stack=%d lte_ppp_opt_in=%d",boot,CONFIG_EGOLINK_FW_VERSION,CONFIG_EGOLINK_COLLECTION_NO_SIM,CONFIG_EGOLINK_COLLECTION_RUN_SECONDS,network_stack_ready,CONFIG_EGOLINK_COLLECTION_LTE_PPP_ENABLED);
#endif
    /* Both reviewed Waveshare V1/V2 schematics connect BOOT to GPIO0/GND.
     * Input only: a one-second press requests cooperative collection stop. */
    gpio_config_t button={.pin_bit_mask=1ULL<<0,.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    bool button_ready=gpio_config(&button)==ESP_OK;
    ESP_LOGI(TAG,"LOCAL_STOP gpio=0 input_ready=%d initial_level=%d hold_ms=1000",button_ready,button_ready?gpio_get_level(0):-1);
    cJSON *p=cJSON_CreateObject();cJSON_AddStringToObject(p,"state","started");cJSON_AddStringToObject(p,"config_id",CONFIG_ID);
    cJSON_AddNumberToObject(p,"imu_sample_interval_us",50000);cJSON_AddNumberToObject(p,"imu_chunk_samples",20);cJSON_AddNumberToObject(p,"gnss_interval_ms",CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    cJSON_AddBoolToObject(p,"camera_profile_requested",true);
    cJSON_AddBoolToObject(p,"camera_runtime_compiled",true);
    cJSON_AddStringToObject(p,"camera_shared_i2c_state",
        platform_camera_shared_i2c_state_name(camera_shared_i2c_state));
    cJSON_AddBoolToObject(p,"camera_shared_i2c_verified",
        camera_shared_i2c_state==PLATFORM_CAMERA_SHARED_I2C_VERIFIED);
    cJSON_AddBoolToObject(p,"camera_driver_preflight_ready",
        camera_preflight==PLATFORM_CAMERA_OK);
    cJSON_AddBoolToObject(p,"camera_manual_capture_ready",
        camera_runtime_ready);
    cJSON_AddBoolToObject(p,"camera_enabled",camera_runtime_ready);
    cJSON_AddBoolToObject(p,"camera_capture_trigger_wired",camera_runtime_ready);
    cJSON_AddBoolToObject(p,"camera_timed_capture_allowed",
        platform_camera_timed_capture_allowed());
    cJSON_AddBoolToObject(p,"camera_unverified_trial_attempt_consumed",
        platform_camera_unverified_trial_attempt_consumed());
    cJSON_AddBoolToObject(p,"photo_media_store_ready",atomic_load(&media_store_ready));
    cJSON_AddBoolToObject(p,"photo_control_state_ready",atomic_load(&photo_control_state_ready));
#else
    cJSON_AddBoolToObject(p,"camera_enabled",false);
#endif
    cJSON_AddBoolToObject(p,"audio_enabled",false);
    cJSON_AddNumberToObject(p,"run_seconds",CONFIG_EGOLINK_COLLECTION_RUN_SECONDS);
    cJSON_AddStringToObject(p,"stop_method",button_ready?"hold_BOOT_1_second_or_configured_deadline":"configured_deadline_only_button_init_failed");
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    cJSON_AddStringToObject(p,"media_reason",camera_runtime_ready?
        (camera_shared_i2c_state==PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED?
        "camera_manual_capture_trial_unverified_ready":"camera_runtime_ready"):
        (camera_reason?camera_reason:"photo_runtime_storage_or_state_unavailable"));
#else
    cJSON_AddStringToObject(p,"media_reason","assembly_and_capture_scope_not_confirmed");
#endif
    emit(SESSION,session_start_us,"started",NULL,p,true);
#if CONFIG_EGOLINK_COLLECTION_CAMERA_PROFILE
    photo_emit_source_status("runtime_start_or_reboot_restore");
#endif
    BaseType_t store_created=xTaskCreate(storage_task,"collection_store",6144,NULL,4,NULL);
    BaseType_t imu_created=xTaskCreatePinnedToCore(imu_task,"collection_imu",6144,NULL,6,NULL,1);
    BaseType_t modem_created=xTaskCreate(modem_task,"collection_modem",12288,NULL,4,NULL);
    BaseType_t upload_created=xTaskCreate(uploader_task,"collection_upload",12288,NULL,3,NULL);
    BaseType_t wifi_created=wifi_started?xTaskCreate(wifi_task,"collection_wifi",6144,NULL,3,NULL):pdFAIL;
    if(store_created!=pdPASS)atomic_store(&writer_stopped,true);
    if(imu_created!=pdPASS)atomic_store(&imu_finished,true);
    if(modem_created!=pdPASS)atomic_store(&modem_finished,true);
    if(upload_created!=pdPASS)atomic_store(&uploader_finished,true);
    bool wifi_task_missing=wifi_started&&wifi_created!=pdPASS;
    if(!wifi_started||wifi_task_missing)atomic_store(&wifi_finished,true);
    if(store_created!=pdPASS||imu_created!=pdPASS||modem_created!=pdPASS||upload_created!=pdPASS||
       (wifi_started&&wifi_created!=pdPASS)) {
        atomic_store(&stopping,true);ESP_LOGE(TAG,"STOP task_creation_failed");
    }
    if(wifi_task_missing) {
        int64_t deadline=now_us()+15000000;
        while(!atomic_load(&uploader_finished)&&now_us()<deadline)
            vTaskDelay(pdMS_TO_TICKS(20));
        if(atomic_load(&uploader_finished))
            atomic_store(&wifi_cleanup_confirmed,wifi_cleanup());
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
    for(unsigned i=0;i<500 && !(atomic_load(&imu_finished)&&atomic_load(&modem_finished)&&atomic_load(&uploader_finished)&&atomic_load(&wifi_finished));i++)vTaskDelay(pdMS_TO_TICKS(100));
    if(atomic_load(&wifi_finished)&&atomic_load(&uploader_finished)&&
       !atomic_load(&wifi_cleanup_confirmed))
        atomic_store(&wifi_cleanup_confirmed,wifi_cleanup());
    bool sources_stopped=atomic_load(&imu_stopped)&&atomic_load(&modem_stopped)&&
        atomic_load(&uploader_finished)&&atomic_load(&wifi_finished)&&
        atomic_load(&wifi_cleanup_confirmed);
    p=cJSON_CreateObject();cJSON_AddStringToObject(p,"state",sources_stopped?"stopped":"stop_failed");
    cJSON_AddBoolToObject(p,"imu_stop_confirmed",atomic_load(&imu_stopped));
    cJSON_AddBoolToObject(p,"modem_stop_confirmed",atomic_load(&modem_stopped));
    cJSON_AddBoolToObject(p,"uploader_finished",atomic_load(&uploader_finished));
    cJSON_AddBoolToObject(p,"wifi_finished",atomic_load(&wifi_finished));
    cJSON_AddBoolToObject(p,"wifi_cleanup_confirmed",atomic_load(&wifi_cleanup_confirmed));
    cJSON_AddBoolToObject(p,"gnss_power_off_confirmed",atomic_load(&gnss_stopped));
    cJSON_AddBoolToObject(p,"lte_ppp_dead",atomic_load(&lte_ppp_stopped));
    cJSON_AddBoolToObject(p,"lte_hangup_required",atomic_load(&lte_hangup_required));
    cJSON_AddBoolToObject(p,"lte_hangup_confirmed",atomic_load(&lte_hangup_confirmed));
    cJSON_AddBoolToObject(p,"lte_cleanup_confirmed",atomic_load(&lte_cleanup_confirmed));
    cJSON_AddNumberToObject(p,"volatile_ram_pending",uxQueueMessagesWaiting(ram_fallback));
    loss_summary();
    emit(SESSION,now_us(),sources_stopped?"stopped":"error",sources_stopped?NULL:"source_stop_unconfirmed",p,true);
    atomic_store(&main_finished,true);
    for(unsigned i=0;i<50 && !atomic_load(&writer_stopped);i++)vTaskDelay(pdMS_TO_TICKS(100));
    if(sntp_ready)esp_netif_sntp_deinit();
    ESP_LOGI(TAG,"STOP complete=%d imu=%d modem=%d writer=%d cache_preserved=true",sources_stopped&&atomic_load(&writer_stopped),atomic_load(&imu_stopped),atomic_load(&modem_stopped),atomic_load(&writer_stopped));
}
