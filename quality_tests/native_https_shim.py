"""Exercise the real ESP HTTPS transfer logic with deterministic SDK I/O faults."""
HEADERS={
"sdkconfig.h":"#define CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT 1\n",
"esp_transport_ssl.h":'#include "esp_transport.h"\nesp_transport_handle_t esp_transport_ssl_init(void);\nvoid esp_transport_ssl_crt_bundle_attach(esp_transport_handle_t,esp_err_t(*)(void*));\n',
"esp_transport.h":r"""
#pragma once
#include "esp_err.h"
typedef struct transport *esp_transport_handle_t;
typedef int(*connect_func)(esp_transport_handle_t,const char*,int,int);
typedef int(*io_read_func)(esp_transport_handle_t,char*,int,int);
typedef int(*io_func)(esp_transport_handle_t,const char*,int,int);
typedef int(*trans_func)(esp_transport_handle_t);
typedef int(*poll_func)(esp_transport_handle_t,int);
esp_transport_handle_t esp_transport_init(void);
esp_err_t esp_transport_destroy(esp_transport_handle_t);
void *esp_transport_get_context_data(esp_transport_handle_t);
esp_err_t esp_transport_set_context_data(esp_transport_handle_t,void*);
esp_err_t esp_transport_set_default_port(esp_transport_handle_t,int);
esp_err_t esp_transport_set_func(esp_transport_handle_t,connect_func,io_read_func,io_func,trans_func,poll_func,poll_func,trans_func);
int esp_transport_connect(esp_transport_handle_t,const char*,int,int);
int esp_transport_read(esp_transport_handle_t,char*,int,int);
int esp_transport_write(esp_transport_handle_t,const char*,int,int);
int esp_transport_close(esp_transport_handle_t);
""",
"esp_timer.h":"#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
"esp_crt_bundle.h":"#include \"esp_err.h\"\nesp_err_t esp_crt_bundle_attach(void*);\n",
"esp_http_client.h":r"""
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
typedef void* esp_http_client_handle_t;
#define HTTP_METHOD_POST 1
#define HTTP_TRANSPORT_OVER_SSL 2
typedef struct {const char*url;int method;int transport_type;esp_err_t(*crt_bundle_attach)(void*);
bool skip_cert_common_name_check;bool disable_auto_redirect;int max_redirection_count;
int timeout_ms;bool keep_alive_enable;struct transport*transport;} esp_http_client_config_t;
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t*);
esp_err_t esp_http_client_set_timeout_ms(void*,int);
esp_err_t esp_http_client_set_header(void*,const char*,const char*);
esp_err_t esp_http_client_open(void*,int);
int esp_http_client_write(void*,const char*,int);
int64_t esp_http_client_fetch_headers(void*);
int esp_http_client_get_status_code(void*);
bool esp_http_client_is_chunked_response(void*);
int esp_http_client_read(void*,char*,int);
bool esp_http_client_is_complete_data_received(void*);
esp_err_t esp_http_client_close(void*);
esp_err_t esp_http_client_cleanup(void*);
"""}
HARNESS=r"""
#include "esp_p0_https.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_transport_ssl.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){printf("failed:%d\n",__LINE__);return 1;}}while(0)
static uint64_t clock_ms=1000;
static int mode,opens,writes,reads,closed;
static bool cancelled_now;
static char wire[16];
struct transport {void*context;connect_func connect;io_read_func read;io_func write;trans_func close;};
static struct transport outer,inner;
static bool bundle;
esp_transport_handle_t esp_transport_init(void){memset(&outer,0,sizeof(outer));return &outer;}
esp_transport_handle_t esp_transport_ssl_init(void){bundle=false;return &inner;}
void esp_transport_ssl_crt_bundle_attach(esp_transport_handle_t t,esp_err_t(*fn)(void*)){bundle=t==&inner && fn==esp_crt_bundle_attach;}
esp_err_t esp_transport_destroy(esp_transport_handle_t t){(void)t;return ESP_OK;}
void*esp_transport_get_context_data(esp_transport_handle_t t){return t->context;}
esp_err_t esp_transport_set_context_data(esp_transport_handle_t t,void*p){t->context=p;return ESP_OK;}
esp_err_t esp_transport_set_default_port(esp_transport_handle_t t,int port){(void)t;return port==443?ESP_OK:ESP_FAIL;}
esp_err_t esp_transport_set_func(esp_transport_handle_t t,connect_func a,io_read_func b,io_func c,trans_func d,poll_func e,poll_func f,trans_func g){(void)e;(void)f;(void)g;t->connect=a;t->read=b;t->write=c;t->close=d;return ESP_OK;}
int esp_transport_connect(esp_transport_handle_t t,const char*h,int p,int timeout){(void)h;(void)p;(void)timeout;return t==&inner?(bundle?0:-1):t->connect(t,h,p,timeout);}
int esp_transport_read(esp_transport_handle_t t,char*b,int n,int timeout){(void)n;(void)timeout;if(t!=&inner)return t->read(t,b,n,timeout);clock_ms+=mode==8?100:0;*b='x';return 1;}
int esp_transport_write(esp_transport_handle_t t,const char*b,int n,int timeout){return t==&inner?n:t->write(t,b,n,timeout);}
int esp_transport_close(esp_transport_handle_t t){return t==&inner?0:t->close(t);}
int64_t esp_timer_get_time(void){return (int64_t)clock_ms*1000;}
esp_err_t esp_crt_bundle_attach(void*p){(void)p;return ESP_OK;}
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t*c){
 if(c->transport_type!=HTTP_TRANSPORT_OVER_SSL || !c->crt_bundle_attach || c->skip_cert_common_name_check || !c->disable_auto_redirect || c->transport!=&outer || !bundle)return NULL;
 return (void*)1;
}
esp_err_t esp_http_client_set_timeout_ms(void*c,int ms){(void)c;return ms>0 && ms<=1000?ESP_OK:ESP_FAIL;}
esp_err_t esp_http_client_set_header(void*c,const char*k,const char*v){(void)c;(void)k;(void)v;return ESP_OK;}
esp_err_t esp_http_client_open(void*c,int count){(void)c;(void)count;++opens;return mode==1?ESP_FAIL:ESP_OK;}
int esp_http_client_write(void*c,const char*p,int count){(void)c;(void)count;wire[writes++]=*p;++clock_ms;return 1;}
int64_t esp_http_client_fetch_headers(void*c){(void)c;if(mode==2)return 9000;if(mode==3)return -1;
 if(mode==8 || mode==9){char byte;unsigned count=0;while(esp_transport_read(&outer,&byte,1,1000)>0){if(++count>17000)return 4;}return -1;}return 4;}
int esp_http_client_get_status_code(void*c){(void)c;return 202;}
bool esp_http_client_is_chunked_response(void*c){(void)c;return mode==4;}
int esp_http_client_read(void*c,char*p,int count){(void)c;(void)count;
 if(mode==5 && reads==2)return 0;
 if(mode==6)cancelled_now=true;
 if(mode==7)clock_ms+=16000;
 *p="A\0CK"[reads++];return 1;
}
bool esp_http_client_is_complete_data_received(void*c){(void)c;return reads==4;}
esp_err_t esp_http_client_close(void*c){(void)c;++closed;return ESP_OK;}
esp_err_t esp_http_client_cleanup(void*c){(void)c;return ESP_OK;}
static bool cancel(void*c,uint32_t generation){(void)c;return generation==7 && cancelled_now;}
int main(void){
 static uint8_t response[8192];const uint8_t payload[]={1,0,2};
 egolink_esp_p0_https_t c={.origin="https://ego.example",.expected_host="ego.example",.bearer="test_token",.deadline_ms=50000,.max_attempts=12,.transaction_timeout_ms=12000};
 egolink_p0_delivery_post_request_t r={.route=EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE,.path=EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH,.body=payload,.body_length=3,.response=response,.response_capacity=sizeof(response),.priority=EGOLINK_OUTBOX_PRIORITY_NORMAL,.cancel_requested=cancel,.transfer_generation=7};
 egolink_p0_delivery_post_result_t result;
 CHECK(egolink_esp_p0_https_post(&c,&r,&result)==EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE);
 CHECK(result.response_length==4 && memcmp(response,"A\0CK",4)==0 && memcmp(wire,payload,3)==0 && closed==1);
 for(mode=1;mode<=9;++mode){clock_ms=1000;reads=writes=0;cancelled_now=false;memset(response,0x41,sizeof(response));
  int status=egolink_esp_p0_https_post(&c,&r,&result);
  CHECK(status==(mode==6?EGOLINK_P0_DELIVERY_POST_CANCELLED:EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED));
  CHECK(result.response_length==0 && response[0]==0 && result.http_status_code==0);
  if(mode==1)CHECK(writes==0);
  if(mode==8)CHECK(clock_ms<=13103); /* slow headers stop at absolute deadline */
 }
 int previous=opens;c.origin="http://ego.example";cancelled_now=false;
 CHECK(egolink_esp_p0_https_post(&c,&r,&result)==EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED && opens==previous);
 c.origin="https://other.example";CHECK(!egolink_esp_p0_https_config_valid(&c));
 c.origin="https://ego.example";c.attempts=c.max_attempts;
 CHECK(egolink_esp_p0_https_post(&c,&r,&result)==EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED && opens==previous);
 return 0;
}
"""
