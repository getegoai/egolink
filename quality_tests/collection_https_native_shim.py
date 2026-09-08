"""SDK boundaries for executing the complete collection HTTPS implementation."""
from quality_tests.native_https_shim import HEADERS as LEGACY_HEADERS

HEADERS = {
    **LEGACY_HEADERS,
    "sdkconfig.h": "#define CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT 1\n#define CONFIG_EGOLINK_COLLECTION_PROFILE 1\n",
    "time.h": "#pragma once\n#include <stdint.h>\ntypedef int64_t time_t;\ntime_t time(time_t*);\n",
    "net/if.h": "#pragma once\n#define IFNAMSIZ 16\nstruct ifreq {char ifr_name[IFNAMSIZ];};\n",
    "esp_tls.h": '#pragma once\n#include "esp_err.h"\ntypedef struct fake_tls_error *esp_tls_error_handle_t;\nesp_err_t esp_tls_get_and_clear_last_error(esp_tls_error_handle_t,int*,int*);\n',
    "esp_transport.h": LEGACY_HEADERS["esp_transport.h"] + '#include "esp_tls.h"\nesp_tls_error_handle_t esp_transport_get_error_handle(esp_transport_handle_t);\n',
    "esp_transport_ssl.h": LEGACY_HEADERS["esp_transport_ssl.h"] + '#include "net/if.h"\nvoid esp_transport_ssl_set_interface_name(esp_transport_handle_t,struct ifreq*);\n',
}
HEADERS["esp_http_client.h"] = LEGACY_HEADERS["esp_http_client.h"].replace(
    "typedef struct {const char*url;",
    "typedef enum {HTTP_EVENT_ERROR, HTTP_EVENT_ON_CONNECTED, HTTP_EVENT_HEADERS_SENT, "
    "HTTP_EVENT_ON_HEADER, HTTP_EVENT_ON_DATA, HTTP_EVENT_ON_FINISH, HTTP_EVENT_DISCONNECTED} esp_http_client_event_id_t;\n"
    "typedef struct {esp_http_client_event_id_t event_id; esp_http_client_handle_t client; "
    "void *data; int data_len; void *user_data; char *header_key; char *header_value;} esp_http_client_event_t;\n"
    "typedef struct {esp_err_t (*event_handler)(esp_http_client_event_t*);void *user_data;const char*url;",
)

HARNESS = r"""
#include "esp_p0_https.h"
#include "collection_record.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_transport_ssl.h"
#include "time.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do {if(!(x)){fprintf(stderr,"case=%d line=%d assertion=%s\n",mode,__LINE__,#x);return 1;}}while(0)
/* Entire frame and ACK below are produced by the real Message Hub store in the
 * Python test. They are synthetic fixture data, not a replacement C protocol. */
static const unsigned char REQUEST_FRAME[] = {__REQUEST_FRAME_BYTES__};
static const unsigned char SERVER_ACK[] = {__SERVER_ACK_BYTES__};
enum {GOOD,CERT_REJECT,WRONG_HOST,WRONG_PORT,HEADER_FAIL,PARTIAL_BODY,CANCEL_BODY,
      DEADLINE_BODY,DECLARED_TOO_LARGE,CHUNKED_BODY,SLOW_HEADERS,OVERSIZE_HEADERS,
      WRITE_INTERRUPTED,INCOMPLETE_FLAG,WRONG_ACK,DISCONNECTED,CONNECTION_CLOSE,
      NON_SUCCESS,REUSE_HEADERS,EVENT_DISCONNECT,EVENT_ERROR};
static int mode,step,init_step,bind_step,authorization_step,content_step,network_step,open_step;
static int opens,client_inits,client_closes,client_cleanups,destroys,inner_connects,inner_reads;
static int tls_error_reads;
static bool error_read_before_cleanup;
static size_t write_count,response_offset;
static uint64_t clock_ms;
static time_t wall_time;
static bool bundle_attached,cancel_now,security_config_ok;
static bool expected_reuse,client_connected,request_active;
static esp_err_t (*event_handler)(esp_http_client_event_t*);
static void *event_user_data;
static const char *borrowed_url;
static struct ifreq *borrowed_interface;
static char bound_interface[32],seen_url[256],content_type[80],network[16],authorization[180];
static char desired_host[254];
static unsigned char sent[4096];
static int client_value;
struct transport {void*context;connect_func connect;io_read_func read;io_func write;trans_func close;};
static struct transport outer,inner;
struct fake_tls_error {int code;int flags;};
static struct fake_tls_error tls_error;
static void event(esp_http_client_event_id_t id,char *key,char *value){
    if(event_handler){esp_http_client_event_t e={.event_id=id,.client=&client_value,
        .user_data=event_user_data,.header_key=key,.header_value=value};(void)event_handler(&e);}
}

time_t time(time_t *result){if(result)*result=wall_time;return wall_time;}
int64_t esp_timer_get_time(void){return (int64_t)clock_ms*1000;}
esp_err_t esp_crt_bundle_attach(void *value){(void)value;return ESP_OK;}
esp_transport_handle_t esp_transport_init(void){memset(&outer,0,sizeof(outer));return &outer;}
esp_transport_handle_t esp_transport_ssl_init(void){memset(&inner,0,sizeof(inner));return &inner;}
void esp_transport_ssl_crt_bundle_attach(esp_transport_handle_t t,esp_err_t(*callback)(void*)){
    bundle_attached=t==&inner && callback==esp_crt_bundle_attach;
}
void esp_transport_ssl_set_interface_name(esp_transport_handle_t t,struct ifreq *iface){
    if(t!=&inner)return;
    borrowed_interface=iface;
    snprintf(bound_interface,sizeof(bound_interface),"%s",iface->ifr_name);bind_step=++step;
}
esp_err_t esp_transport_destroy(esp_transport_handle_t t){if(t!=&outer&&t!=&inner)return ESP_FAIL;++destroys;return ESP_OK;}
esp_tls_error_handle_t esp_transport_get_error_handle(esp_transport_handle_t t){return t==&inner?&tls_error:NULL;}
esp_err_t esp_tls_get_and_clear_last_error(esp_tls_error_handle_t handle,int *code,int *flags){
    if(handle!=&tls_error)return ESP_FAIL;
    ++tls_error_reads;
    error_read_before_cleanup=destroys==0 && client_closes==0 && client_cleanups==0;
    *code=handle->code;*flags=handle->flags;
    bool failed=handle->code!=0;
    handle->code=handle->flags=0;
    return failed?ESP_FAIL:ESP_OK;
}
void *esp_transport_get_context_data(esp_transport_handle_t t){return t->context;}
esp_err_t esp_transport_set_context_data(esp_transport_handle_t t,void *value){t->context=value;return ESP_OK;}
esp_err_t esp_transport_set_default_port(esp_transport_handle_t t,int port){(void)t;return port==443?ESP_OK:ESP_FAIL;}
esp_err_t esp_transport_set_func(esp_transport_handle_t t,connect_func a,io_read_func b,io_func c,trans_func d,poll_func e,poll_func f,trans_func g){
    (void)e;(void)f;(void)g;t->connect=a;t->read=b;t->write=c;t->close=d;return ESP_OK;
}
int esp_transport_connect(esp_transport_handle_t t,const char *host,int port,int timeout){
    if(t!=&inner)return t->connect(t,host,port,timeout);
    ++inner_connects;
    if(!bundle_attached || strcmp(host,desired_host) || port!=443 || timeout<=0 || timeout>1000)return -1;
    if(mode==CERT_REJECT){tls_error.code=-9984;tls_error.flags=8;return -1;}
    if(mode==DISCONNECTED){tls_error.code=-1234;tls_error.flags=0;return -1;}
    return 0;
}
int esp_transport_read(esp_transport_handle_t t,char *buffer,int count,int timeout){
    if(t!=&inner)return t->read(t,buffer,count,timeout);
    if(count<=0||timeout<=0||timeout>1000)return -1;
    ++inner_reads;if(mode==SLOW_HEADERS)clock_ms+=100;
    *buffer='x';return 1;
}
int esp_transport_write(esp_transport_handle_t t,const char *buffer,int count,int timeout){
    return t==&inner?count:t->write(t,buffer,count,timeout);
}
int esp_transport_close(esp_transport_handle_t t){return t==&inner?0:t->close(t);}
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg){
    ++client_inits;init_step=++step;snprintf(seen_url,sizeof(seen_url),"%s",cfg->url);
    borrowed_url=cfg->url;event_handler=cfg->event_handler;event_user_data=cfg->user_data;
    client_connected=request_active=false;
    security_config_ok=cfg->method==HTTP_METHOD_POST && cfg->transport_type==HTTP_TRANSPORT_OVER_SSL &&
        cfg->crt_bundle_attach==esp_crt_bundle_attach && !cfg->skip_cert_common_name_check &&
        cfg->disable_auto_redirect && cfg->max_redirection_count==0 && cfg->keep_alive_enable==expected_reuse &&
        cfg->transport==&outer && bundle_attached && (!!cfg->event_handler==expected_reuse) &&
        (!!cfg->user_data==expected_reuse);
    return security_config_ok?&client_value:NULL;
}
esp_err_t esp_http_client_set_timeout_ms(void *client,int timeout){
    return client==&client_value && timeout>0 && timeout<=1000?ESP_OK:ESP_FAIL;
}
esp_err_t esp_http_client_set_header(void *client,const char *name,const char *value){
    if(client!=&client_value||request_active)return ESP_FAIL;
    if(!strcmp(name,"Authorization")){snprintf(authorization,sizeof(authorization),"%s",value);authorization_step=++step;}
    else if(!strcmp(name,"Content-Type")){snprintf(content_type,sizeof(content_type),"%s",value);content_step=++step;}
    else if(!strcmp(name,"X-EgoLink-Transport")){snprintf(network,sizeof(network),"%s",value);network_step=++step;if(mode==HEADER_FAIL)return ESP_FAIL;}
    return ESP_OK;
}
esp_err_t esp_http_client_open(void *client,int size){
    if(client!=&client_value||size!=(int)sizeof(REQUEST_FRAME))return ESP_FAIL;
    ++opens;open_step=++step;
    /* SDK 5.4.2 open -> connect always prepares/reset parser state, then skips
     * esp_transport_connect when the client already is connected. */
    write_count=response_offset=0;request_active=true;memset(sent,0,sizeof(sent));
    if(!client_connected){
        if(esp_transport_connect(&outer,mode==WRONG_HOST?"attacker.example":desired_host,mode==WRONG_PORT?80:443,1000)!=0)return ESP_FAIL;
        client_connected=true;event(HTTP_EVENT_ON_CONNECTED,NULL,NULL);
    }
    return ESP_OK;
}
int esp_http_client_write(void *client,const char *data,int remaining){
    (void)client;
    if(mode==WRITE_INTERRUPTED && write_count>0)return -1;
    int count=remaining>7?7:remaining;
    if(write_count+(size_t)count>sizeof(sent))return -1;
    if(esp_transport_write(&outer,data,count,1000)!=count)return -1;
    memcpy(sent+write_count,data,(size_t)count);write_count+=(size_t)count;return count;
}
int64_t esp_http_client_fetch_headers(void *client){
    (void)client;
    if(mode==DECLARED_TOO_LARGE)return 8193;
    if(mode==SLOW_HEADERS||mode==OVERSIZE_HEADERS){char byte;while(esp_transport_read(&outer,&byte,1,1000)>0){}return -1;}
    if(mode==REUSE_HEADERS){char byte;for(int i=0;i<9000;i++)if(esp_transport_read(&outer,&byte,1,1000)!=1)return -1;}
    if(mode==CONNECTION_CLOSE)event(HTTP_EVENT_ON_HEADER,"cOnNeCtIoN","keep-alive, \tClOsE \t");
    if(mode==EVENT_DISCONNECT)event(HTTP_EVENT_DISCONNECTED,NULL,NULL);
    if(mode==EVENT_ERROR)event(HTTP_EVENT_ERROR,NULL,NULL);
    return (int64_t)sizeof(SERVER_ACK);
}
int esp_http_client_get_status_code(void *client){(void)client;return mode==NON_SUCCESS?503:200;}
bool esp_http_client_is_chunked_response(void *client){(void)client;return mode==CHUNKED_BODY;}
int esp_http_client_read(void *client,char *buffer,int remaining){
    (void)client;
    if(mode==PARTIAL_BODY&&response_offset>=sizeof(SERVER_ACK)/2)return 0;
    int count=remaining>11?11:remaining;
    char boundary_byte;if(esp_transport_read(&outer,&boundary_byte,1,1000)!=1)return -1;
    memcpy(buffer,SERVER_ACK+response_offset,(size_t)count);
    if(mode==WRONG_ACK && response_offset==0)buffer[0]='[';
    response_offset+=(size_t)count;
    if(mode==CANCEL_BODY)cancel_now=true;
    if(mode==DEADLINE_BODY)clock_ms+=13000;
    return count;
}
bool esp_http_client_is_complete_data_received(void *client){(void)client;request_active=false;return mode!=INCOMPLETE_FLAG&&response_offset==sizeof(SERVER_ACK);}
esp_err_t esp_http_client_close(void *client){(void)client;++client_closes;client_connected=request_active=false;event(HTTP_EVENT_DISCONNECTED,NULL,NULL);return esp_transport_close(&outer);}
esp_err_t esp_http_client_cleanup(void *client){(void)client;++client_cleanups;event_handler=NULL;event_user_data=NULL;borrowed_url=NULL;borrowed_interface=NULL;return ESP_OK;}
static bool cancelled(void *context,uint32_t generation){(void)context;return generation==73&&cancel_now;}
static void reset(int selected){
    mode=selected;step=init_step=bind_step=authorization_step=content_step=network_step=open_step=0;
    opens=client_inits=client_closes=client_cleanups=destroys=inner_connects=inner_reads=0;
    tls_error_reads=0;error_read_before_cleanup=false;tls_error.code=tls_error.flags=0;
    write_count=response_offset=0;clock_ms=1000;wall_time=1788650000;
    bundle_attached=cancel_now=security_config_ok=false;
    expected_reuse=client_connected=request_active=false;event_handler=NULL;event_user_data=NULL;
    borrowed_url=NULL;borrowed_interface=NULL;snprintf(desired_host,sizeof(desired_host),"ego.example");
    memset(bound_interface,0,sizeof(bound_interface));memset(seen_url,0,sizeof(seen_url));
    memset(content_type,0,sizeof(content_type));memset(network,0,sizeof(network));memset(sent,0,sizeof(sent));
}
static egolink_esp_p0_https_t configuration(void){
    return (egolink_esp_p0_https_t){.origin="https://ego.example",.expected_host="ego.example",.bearer="test-token",
        .deadline_ms=50000,.max_attempts=12,.transaction_timeout_ms=12000};
}
typedef struct {bool alive;uint32_t generation;unsigned calls;} cancel_context_t;
static unsigned stale_probe_calls;
static bool scoped_cancel(void *context,uint32_t generation){
    cancel_context_t *value=context;
    if(!value || !value->alive || generation!=value->generation){++stale_probe_calls;return true;}
    ++value->calls;return cancel_now;
}
static void renew(egolink_esp_p0_https_t *config){
    config->attempts=0;config->deadline_ms=clock_ms+15000;
}
static int short_lived_post(egolink_esp_p0_https_t *config,cancel_context_t *cancel){
    unsigned char body[sizeof(REQUEST_FRAME)],response[8192];
    memcpy(body,REQUEST_FRAME,sizeof(body));
    char device[]="collector_test-001",interface_name[]="st1";
    egolink_p0_delivery_post_request_t request={.path="unused",.body=body,.body_length=sizeof(body),
        .response=response,.response_capacity=sizeof(response),.cancel_requested=scoped_cancel,
        .cancel_context=cancel,.transfer_generation=cancel->generation};
    egolink_p0_delivery_post_result_t result;
    renew(config);
    CHECK(egolink_esp_p0_https_post_collection(config,device,interface_name,&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(collection_record_ack_matches(body,sizeof(body),device,response,result.response_length));
    /* These borrowed inputs cease to be valid after return. The SDK must retain
     * only the connection's own URL/interface and never this request or buffers. */
    memset(&request,0xA5,sizeof(request));memset(body,0xA5,sizeof(body));memset(response,0xA5,sizeof(response));
    memset(device,'?',sizeof(device)-1);memset(interface_name,'?',sizeof(interface_name)-1);
    return 0;
}
static int reuse_cases(void){
    unsigned char response[8192];
    egolink_p0_delivery_post_request_t request={.path="unused",.body=REQUEST_FRAME,.body_length=sizeof(REQUEST_FRAME),
        .response=response,.response_capacity=sizeof(response),.cancel_requested=cancelled,.transfer_generation=73};
    egolink_p0_delivery_post_result_t result;
    egolink_esp_p0_https_t config;
    reset(REUSE_HEADERS);config=configuration();config.reuse_connection=expected_reuse=true;
    cancel_context_t old={.alive=true,.generation=75},current={.alive=true,.generation=76};
    CHECK(short_lived_post(&config,&old)==0);
    CHECK(config.connection_state && inner_connects==1 && client_inits==1 && client_closes==0);
    CHECK(borrowed_url && !strcmp(borrowed_url,"https://ego.example/api/v1/devices/collector_test-001/raw-ingest"));
    CHECK(borrowed_interface && !strcmp(borrowed_interface->ifr_name,"st1"));
    old.alive=false;unsigned calls=old.calls;char byte;
    CHECK(esp_transport_read(&outer,&byte,1,1000)==-1);
    CHECK(esp_transport_write(&outer,"x",1,1000)==-1);
    CHECK(esp_transport_connect(&outer,"ego.example",443,1000)==-1);
    CHECK(old.calls==calls && stale_probe_calls==0);
    clock_ms+=13000; /* Expired first request deadline, still within 60s reuse age. */
    CHECK(short_lived_post(&config,&current)==0);
    CHECK(config.connection_state && opens==2 && inner_connects==1 && client_inits==1 && client_closes==0);
    CHECK(inner_reads>18000 && current.calls>0 && stale_probe_calls==0);
    CHECK(authorization_step<open_step && content_step<open_step && network_step<open_step);
    CHECK(write_count==sizeof(REQUEST_FRAME) && !memcmp(sent,REQUEST_FRAME,sizeof(REQUEST_FRAME)));
    current.alive=false;CHECK(esp_transport_read(&outer,&byte,1,1000)==-1 && stale_probe_calls==0);
    egolink_esp_p0_https_close(&config);
    CHECK(!config.connection_state && client_closes==1 && client_cleanups==1 && destroys==2);
    egolink_esp_p0_https_close(&config);egolink_esp_p0_https_close(NULL);
    CHECK(client_closes==1 && client_cleanups==1 && destroys==2);

    /* An uncertain partial write retires the socket. Caller retries identical
     * record bytes on a new verified connection, never an automatically new ID. */
    reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
    CHECK(short_lived_post(&config,&(cancel_context_t){.alive=true,.generation=77})==0);
    mode=WRITE_INTERRUPTED;renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED);
    CHECK(!config.connection_state && inner_connects==1 && result.response_length==0 && write_count==7);
    CHECK(!memcmp(sent,REQUEST_FRAME,write_count));
    mode=GOOD;renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==2 && client_inits==2 && write_count==sizeof(REQUEST_FRAME) && !memcmp(sent,REQUEST_FRAME,sizeof(REQUEST_FRAME)));
    CHECK(collection_record_ack_matches(REQUEST_FRAME,sizeof(REQUEST_FRAME),"collector_test-001",response,result.response_length));
    egolink_esp_p0_https_close(&config);

    const int retire_modes[]={PARTIAL_BODY,CANCEL_BODY,DEADLINE_BODY,DECLARED_TOO_LARGE,CHUNKED_BODY,
        INCOMPLETE_FLAG,CONNECTION_CLOSE,NON_SUCCESS,EVENT_DISCONNECT,EVENT_ERROR};
    for(unsigned i=0;i<sizeof(retire_modes)/sizeof(retire_modes[0]);i++){
        reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
        CHECK(short_lived_post(&config,&(cancel_context_t){.alive=true,.generation=77})==0);
        mode=retire_modes[i];renew(&config);
        egolink_p0_delivery_post_outcome_t outcome=egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result);
        CHECK(!config.connection_state && inner_connects==1 && client_closes==1 && client_cleanups==1 && destroys==2);
        if(mode==CONNECTION_CLOSE||mode==NON_SUCCESS||mode==EVENT_DISCONNECT||mode==EVENT_ERROR){
            CHECK(outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE && result.response_length==sizeof(SERVER_ACK));
            CHECK(result.http_status_code==(mode==NON_SUCCESS?503:200));
        } else {
            CHECK(outcome==(mode==CANCEL_BODY?EGOLINK_P0_DELIVERY_POST_CANCELLED:EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED));
            CHECK(result.response_length==0 && response[0]==0);
        }
        mode=GOOD;cancel_now=false;renew(&config);
        CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
        CHECK(inner_connects==2 && client_inits==2 && config.connection_state);
        egolink_esp_p0_https_close(&config);
    }
    /* Identity and interface are owned copies. Mutable caller strings changing
     * in place must also retire the old authenticated connection. */
    reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
    char bearer[32]="test-token";config.bearer=bearer;
    CHECK(short_lived_post(&config,&(cancel_context_t){.alive=true,.generation=77})==0);
    strcpy(bearer,"second-token");renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==2 && client_cleanups==1 && !strcmp(authorization,"Bearer second-token"));
    renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"other-device","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==3 && client_cleanups==2 && !strcmp(seen_url,"https://ego.example/api/v1/devices/other-device/raw-ingest"));
    renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"other-device","st2",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==4 && client_cleanups==3 && !strcmp(bound_interface,"st2"));
    config.origin="https://other.example";config.expected_host="other.example";strcpy(desired_host,"other.example");renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"other-device","st2",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==5 && client_cleanups==4 && !strcmp(seen_url,"https://other.example/api/v1/devices/other-device/raw-ingest"));
    config.origin="https://other.example:443";renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"other-device","st2",&request,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED);
    CHECK(inner_connects==5 && client_cleanups==5 && !config.connection_state);
    egolink_esp_p0_https_close(&config);

    /* Revalidate credentials/network conditions after a fixed age or count. */
    reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
    for(unsigned i=0;i<25;i++){
        renew(&config);
        CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
        CHECK(inner_connects==(i<24?1:2));
        CHECK((config.connection_state!=NULL)==(i!=23));
    }
    CHECK(client_cleanups==1 && opens==25);egolink_esp_p0_https_close(&config);
    reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
    CHECK(short_lived_post(&config,&(cancel_context_t){.alive=true,.generation=77})==0);
    clock_ms+=60000;renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==2 && client_cleanups==1);
    clock_ms=500;renew(&config);
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(inner_connects==3 && client_cleanups==2);egolink_esp_p0_https_close(&config);

    /* Preflight refusal cannot leave a previously authenticated socket alive. */
    for(int reason=0;reason<7;reason++){
        reset(GOOD);config=configuration();config.reuse_connection=expected_reuse=true;
        CHECK(short_lived_post(&config,&(cancel_context_t){.alive=true,.generation=77})==0);
        renew(&config);
        if(reason==0)cancel_now=true;
        if(reason==1)config.deadline_ms=clock_ms;
        if(reason==2)wall_time=0;
        if(reason==3)config.attempts=config.max_attempts;
        if(reason==4)config.origin="http://ego.example";
        egolink_p0_delivery_post_outcome_t outcome=egolink_esp_p0_https_post_collection(&config,
            reason==5?"../bad":"collector_test-001",reason==6?"pp1":"st1",&request,&result);
        CHECK(outcome!=EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE && !config.connection_state);
        CHECK(opens==1 && inner_connects==1 && client_cleanups==1 && destroys==2 && result.response_length==0);
    }
    return 0;
}
int main(void){
    static unsigned char response[8192];
    egolink_p0_delivery_post_request_t request={.route=EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS,
        .path="https://attacker.example/untrusted/path",.body=REQUEST_FRAME,.body_length=sizeof(REQUEST_FRAME),
        .response=response,.response_capacity=sizeof(response),.priority=EGOLINK_OUTBOX_PRIORITY_NORMAL,
        .cancel_requested=cancelled,.transfer_generation=73};
    egolink_p0_delivery_post_result_t result;
    egolink_esp_p0_https_t config;
    reset(GOOD);config=configuration();
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    CHECK(!strcmp(seen_url,"https://ego.example/api/v1/devices/collector_test-001/raw-ingest"));
    CHECK(!strcmp(request.path,"https://attacker.example/untrusted/path"));
    CHECK(!strcmp(bound_interface,"st1") && bind_step>0 && bind_step<init_step && init_step<open_step);
    CHECK(!strcmp(content_type,"application/octet-stream") && !strcmp(network,"wifi") && !strcmp(authorization,"Bearer test-token"));
    CHECK(authorization_step<open_step && content_step<open_step && network_step<open_step);
    CHECK(security_config_ok && inner_connects==1 && write_count==sizeof(REQUEST_FRAME) && !memcmp(sent,REQUEST_FRAME,sizeof(REQUEST_FRAME)));
    CHECK(result.http_status_code==200 && result.response_length==sizeof(SERVER_ACK) && !memcmp(response,SERVER_ACK,sizeof(SERVER_ACK)));
    CHECK(collection_record_ack_matches(REQUEST_FRAME,sizeof(REQUEST_FRAME),"collector_test-001",response,result.response_length));
    CHECK(config.attempts==1 && config.complete_responses==1 && client_closes==1 && client_cleanups==1 && destroys==2);
    for(int selected=CERT_REJECT;selected<=DISCONNECTED;selected++){
        reset(selected);config=configuration();memset(response,0x41,sizeof(response));
        egolink_p0_delivery_post_outcome_t outcome=egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result);
        if(selected==WRONG_ACK){
            CHECK(outcome==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE && result.response_length==sizeof(SERVER_ACK));
            CHECK(!collection_record_ack_matches(REQUEST_FRAME,sizeof(REQUEST_FRAME),"collector_test-001",response,result.response_length));
        } else {
            CHECK(outcome==(selected==CANCEL_BODY?EGOLINK_P0_DELIVERY_POST_CANCELLED:EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED));
            CHECK(result.response_length==0 && result.http_status_code==0 && response[0]==0 && response[sizeof(response)-1]==0);
            CHECK(config.complete_responses==0);
            CHECK(tls_error_reads==1 && error_read_before_cleanup && tls_error.code==0 && tls_error.flags==0);
            if(selected!=CANCEL_BODY)CHECK(result.transport_error==(selected==CERT_REJECT?EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS:EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO));
        }
        CHECK(client_closes==1 && client_cleanups==1 && destroys==2 && security_config_ok);
        if(selected==CERT_REJECT||selected==WRONG_HOST||selected==WRONG_PORT||selected==DISCONNECTED)CHECK(write_count==0);
        if(selected==WRONG_HOST||selected==WRONG_PORT)CHECK(inner_connects==0);
        if(selected==HEADER_FAIL)CHECK(opens==0);
        if(selected==SLOW_HEADERS)CHECK(clock_ms<=13000 && inner_reads<=120);
        if(selected==OVERSIZE_HEADERS)CHECK(inner_reads==16384);
    }
    const char *invalid_ids[]={NULL,"","../other","a/b","a?b","a#b","a%b","a.b","a:b","a@b","a b","a\nb","\xc3\xa9","12345678901234567890123456789012345678901234567890123456789012345"};
    for(unsigned i=0;i<sizeof(invalid_ids)/sizeof(invalid_ids[0]);i++){
        reset(GOOD);config=configuration();
        memset(&result,0x41,sizeof(result));
        CHECK(egolink_esp_p0_https_post_collection(&config,invalid_ids[i],"st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED);
        CHECK(opens==0 && client_inits==0 && config.attempts==0 && result.response_length==0 && result.http_status_code==0);
    }
    char maximum_id[65],expected_url[256];memset(maximum_id,'a',64);maximum_id[64]=0;
    reset(GOOD);config=configuration();
    CHECK(egolink_esp_p0_https_post_collection(&config,maximum_id,"st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
    snprintf(expected_url,sizeof(expected_url),"https://ego.example/api/v1/devices/%s/raw-ingest",maximum_id);
    CHECK(!strcmp(seen_url,expected_url));
    reset(GOOD);config=configuration();wall_time=0;
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED);
    CHECK(result.transport_error==EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS && result.response_length==0 && opens==0 && config.attempts==0);
    const char *origins[]={"http://ego.example","https://other.example","https://ego.example:80","https://ego.example/base","https://ego.example@attacker.example"};
    for(unsigned i=0;i<sizeof(origins)/sizeof(origins[0]);i++){
        reset(GOOD);config=configuration();config.origin=origins[i];
        CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED);
        CHECK(opens==0 && client_inits==0);
    }
    reset(GOOD);config=configuration();config.attempts=config.max_attempts;
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001","st1",&request,&result)==EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED && opens==0);
    reset(GOOD);config=configuration();
    egolink_p0_delivery_post_outcome_t empty_interface=egolink_esp_p0_https_post_collection(&config,"collector_test-001","",&request,&result);
    bool empty_interface_rejected=empty_interface!=EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE && opens==0 && bind_step==0;
    const char *invalid_interfaces[]={"st","pp1","ap1","eth0","st1x","st1234","st-1","st1\n"};
    for(unsigned i=0;i<sizeof(invalid_interfaces)/sizeof(invalid_interfaces[0]);i++){
        reset(GOOD);config=configuration();memset(&result,0x41,sizeof(result));
        CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001",invalid_interfaces[i],&request,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED);
        CHECK(opens==0 && bind_step==0 && config.attempts==0 && result.response_length==0 && result.http_status_code==0);
    }
    reset(GOOD);config=configuration();
    CHECK(egolink_esp_p0_https_post_collection(&config,"collector_test-001",NULL,&request,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED && opens==0);
    CHECK(reuse_cases()==0);
    printf("{\"reuse_two_requests_one_tls\":true,\"reuse_request_bounds_and_lifetimes\":true,\"reuse_uncertain_write_exact_retry\":true,\"reuse_fault_retirements\":10,\"reuse_identity_changes\":5,\"reuse_age_and_count_limits\":true,\"reuse_preflight_retirements\":7,\"fixed_route_headers_interface\":true,\"complete_server_ack\":true,\"fault_cases\":15,\"ascii_id_rejections\":%u,\"clock_tls_guard\":true,\"tls_origin_and_hostname_guards\":true,\"tls_failure_classification\":true,\"interface_rejections\":8,\"early_rejection_clears_result\":true,\"empty_interface_rejected\":%s}\n",
        (unsigned)(sizeof(invalid_ids)/sizeof(invalid_ids[0])),empty_interface_rejected?"true":"false");
    return 0;
}
"""
