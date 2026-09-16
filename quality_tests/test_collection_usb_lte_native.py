"""Execute the production connector/state on native threads with a USB/IDF boundary.

This verifies owner, command, deadline, cancellation and PPP routing behavior;
it does not simulate a passing modem registration, TLS handshake or hardware.
"""
import unittest
from pathlib import Path
from quality_tests.native_convergence import run_c, COMP

ERRORS = """#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 257
#define ESP_ERR_INVALID_ARG 258
#define ESP_ERR_INVALID_STATE 259
#define ESP_ERR_NOT_SUPPORTED 262
#define ESP_ERR_TIMEOUT 263
"""
NETIF = """#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
typedef struct esp_netif_obj { int unused; } esp_netif_t;
typedef struct {const char *if_key,*if_desc; int route_prio;} esp_netif_inherent_config_t;
typedef struct {const esp_netif_inherent_config_t *base; const void *stack;} esp_netif_config_t;
typedef struct {esp_netif_t *esp_netif;} ip_event_got_ip_t;
#define ESP_NETIF_INHERENT_DEFAULT_PPP() (esp_netif_inherent_config_t){0}
#define ESP_NETIF_NETSTACK_DEFAULT_PPP ((void*)1)
esp_netif_t *esp_netif_new(const esp_netif_config_t*);
esp_err_t esp_netif_attach(esp_netif_t*,void*);
"""
FREERTOS = """#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <windows.h>
typedef HANDLE SemaphoreHandle_t;
typedef uintptr_t TaskHandle_t;
typedef unsigned TickType_t;
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY INFINITE
static inline HANDLE xSemaphoreCreateMutex(void) {return CreateMutex(NULL,FALSE,NULL);}
void test_before_mutex_take(HANDLE h);
static inline int xSemaphoreTake(HANDLE h,unsigned ms){test_before_mutex_take(h);return WaitForSingleObject(h,ms)==WAIT_OBJECT_0;}
static inline void xSemaphoreGive(HANDLE h){ReleaseMutex(h);}
static inline uintptr_t xTaskGetCurrentTaskHandle(void){return GetCurrentThreadId();}
"""
EVENT = """#pragma once
#include "esp_err.h"
typedef int esp_event_base_t;
typedef void *esp_event_handler_instance_t;
typedef void (*test_event_fn)(void*,int,int32_t,void*);
#define IP_EVENT 1
#define IP_EVENT_PPP_GOT_IP 2
#define IP_EVENT_PPP_LOST_IP 3
#define ESP_EVENT_ANY_ID -1
esp_err_t esp_event_handler_instance_register(int,int,test_event_fn,void*,void**);
"""
PPP = """#pragma once
#include "esp_netif.h"
#define NETIF_PPP_STATUS 10
#define NETIF_PP_PHASE_OFFSET 256
#define NETIF_PPP_PHASE_DEAD 256
typedef struct {bool ppp_error_event_enabled,ppp_phase_event_enabled;} esp_netif_ppp_config_t;
esp_err_t esp_netif_ppp_set_params(esp_netif_t*,const esp_netif_ppp_config_t*);
"""
CDC = """#pragma once
#include "freertos/FreeRTOS.h"
#include "esp_err.h"
#include <stddef.h>
typedef void *usbh_cdc_port_handle_t;
typedef struct {unsigned match_flags;uint16_t idVendor,idProduct;} usb_device_match_id_t;
typedef struct {uint16_t idVendor,idProduct;} usb_device_desc_t;
#define USB_DEVICE_ID_MATCH_VID_PID 3
#define CDC_HOST_DEVICE_EVENT_CONNECTED 0
#define CDC_HOST_DEVICE_EVENT_DISCONNECTED 1
typedef int usbh_cdc_device_event_t;
typedef union {
 struct {uint8_t dev_addr;const usb_device_desc_t *device_desc;} new_dev;
 struct {uint8_t dev_addr;} dev_gone;
} usbh_cdc_device_event_data_t;
typedef void (*test_usb_event_fn)(int,usbh_cdc_device_event_data_t*,void*);
typedef struct {size_t task_stack_size;unsigned task_priority;int task_coreid;bool skip_init_usb_host_driver;} usbh_cdc_driver_config_t;
typedef struct {uint8_t dev_addr,itf_num;size_t in_transfer_buffer_size,out_transfer_buffer_size;
 struct {void (*recv_data)(void*,void*);} cbs;} usbh_cdc_port_config_t;
esp_err_t usbh_cdc_driver_install(const usbh_cdc_driver_config_t*);
esp_err_t usbh_cdc_register_dev_event_cb(const usb_device_match_id_t*,test_usb_event_fn,void*);
esp_err_t usbh_cdc_port_open(const usbh_cdc_port_config_t*,void**);
esp_err_t usbh_cdc_write_bytes(void*,const uint8_t*,size_t,unsigned);
esp_err_t usbh_cdc_read_bytes(void*,uint8_t*,size_t*,unsigned);
esp_err_t usbh_cdc_get_rx_buffer_size(void*,size_t*);
"""
ETH = """#pragma once
#include "esp_err.h"
#include <stdint.h>
#include <stddef.h>
typedef struct iot_eth_driver_s iot_eth_driver_t;
typedef struct iot_eth_mediator_s iot_eth_mediator_t;
typedef int iot_eth_link_t;
#define IOT_ETH_LINK_UP 1
#define IOT_ETH_STAGE_LINK 2
struct iot_eth_mediator_s {
 esp_err_t (*stack_input)(iot_eth_mediator_t*,uint8_t*,size_t);
 esp_err_t (*on_stage_changed)(iot_eth_mediator_t*,int,void*);
};
struct iot_eth_driver_s {
 const char *name;
 esp_err_t (*set_mediator)(iot_eth_driver_t*,iot_eth_mediator_t*);
 esp_err_t (*init)(iot_eth_driver_t*);
 esp_err_t (*deinit)(iot_eth_driver_t*);
 esp_err_t (*transmit)(iot_eth_driver_t*,uint8_t*,size_t);
};
typedef void *iot_eth_handle_t;
typedef void *iot_eth_netif_glue_handle_t;
typedef struct {iot_eth_driver_t *driver;} iot_eth_config_t;
esp_err_t iot_eth_install(const iot_eth_config_t*,void**);
esp_err_t iot_eth_start(void*);
esp_err_t iot_eth_stop(void*);
void *iot_eth_new_netif_glue(void*);
"""
HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>
#include "collection_usb_lte.h"
#include "freertos/FreeRTOS.h"
#include "esp_event.h"
#include "esp_netif_ppp.h"
#include "iot_usbh_cdc.h"
#include "iot_eth.h"
static atomic_uint_fast64_t clock_ms;
int64_t esp_timer_get_time(void) {return (int64_t)atomic_load(&clock_ms)*1000;}
static test_usb_event_fn event_cb;
static void (*rx_cb)(void*,void*);
static test_event_fn handlers[3];
static esp_netif_t netif;
static iot_eth_driver_t *eth_driver;
static unsigned writes, starts, stops, opened_itf;
static char last_write[32];
static uint8_t incoming[2048], ppp[2048];
static size_t incoming_size, ppp_size;
static esp_err_t next_write, next_stop;
static HANDLE in_write, release_write, before_callback_gate, release_callback_gate;
static DWORD owner_thread;
static atomic_bool intercept_callback_gate;
void test_before_mutex_take(HANDLE h)
{(void)h;if(atomic_load(&intercept_callback_gate)&&GetCurrentThreadId()!=owner_thread){
 SetEvent(before_callback_gate);assert(WaitForSingleObject(release_callback_gate,500)==WAIT_OBJECT_0);}}
esp_err_t usbh_cdc_driver_install(const usbh_cdc_driver_config_t *c){assert(c->task_stack_size==4096);return ESP_OK;}
esp_err_t usbh_cdc_register_dev_event_cb(const usb_device_match_id_t *m,test_usb_event_fn cb,void *u)
{(void)u;assert(m[0].idVendor==0x05c6 && m[0].idProduct==0x9330 && !m[1].match_flags);event_cb=cb;return ESP_OK;}
esp_err_t usbh_cdc_port_open(const usbh_cdc_port_config_t *c,void **p)
{opened_itf=c->itf_num;rx_cb=c->cbs.recv_data;*p=(void*)1;return ESP_OK;}
esp_err_t usbh_cdc_write_bytes(void *p,const uint8_t *b,size_t n,unsigned wait)
{assert(p==(void*)1 && (wait==25 || wait==1000));assert(n<sizeof(last_write));memcpy(last_write,b,n);last_write[n]=0;++writes;
 if(in_write){SetEvent(in_write);assert(WaitForSingleObject(release_write,500)==WAIT_OBJECT_0);}
 esp_err_t e=next_write;next_write=ESP_OK;return e;}
esp_err_t usbh_cdc_get_rx_buffer_size(void *p,size_t *n){assert(p==(void*)1);*n=incoming_size;return ESP_OK;}
esp_err_t usbh_cdc_read_bytes(void *p,uint8_t *b,size_t *n,unsigned wait)
{assert(p==(void*)1 && !wait && *n==incoming_size);memcpy(b,incoming,*n);incoming_size=0;return ESP_OK;}
esp_err_t esp_event_handler_instance_register(int b,int id,test_event_fn cb,void *a,void **h)
{(void)a;unsigned index=b==NETIF_PPP_STATUS?2:(id==IP_EVENT_PPP_GOT_IP?0:1);handlers[index]=cb;*h=(void*)1;return ESP_OK;}
esp_netif_t *esp_netif_new(const esp_netif_config_t *c){assert(!strcmp(c->base->if_key,"EGO_USB_PPP"));return &netif;}
esp_err_t esp_netif_attach(esp_netif_t *n,void *g){assert(n==&netif && g);return ESP_OK;}
esp_err_t esp_netif_ppp_set_params(esp_netif_t *n,const esp_netif_ppp_config_t *c)
{assert(n==&netif && c->ppp_phase_event_enabled && c->ppp_error_event_enabled);return ESP_OK;}
static esp_err_t input(iot_eth_mediator_t *m,uint8_t *b,size_t n)
{(void)m;assert(ppp_size+n<=sizeof(ppp));memcpy(ppp+ppp_size,b,n);ppp_size+=n;return ESP_OK;}
static esp_err_t stage(iot_eth_mediator_t *m,int s,void *v)
{(void)m;assert(s==IOT_ETH_STAGE_LINK && *(int*)v==IOT_ETH_LINK_UP);return ESP_OK;}
esp_err_t iot_eth_install(const iot_eth_config_t *c,void **h)
{static iot_eth_mediator_t m={input,stage};eth_driver=c->driver;assert(eth_driver->set_mediator(eth_driver,&m)==ESP_OK);*h=(void*)1;return eth_driver->init(eth_driver);}
esp_err_t iot_eth_start(void *h){assert(h);++starts;return ESP_OK;}
esp_err_t iot_eth_stop(void *h){assert(h);++stops;esp_err_t e=next_stop;next_stop=ESP_OK;return e;}
void *iot_eth_new_netif_glue(void *h){return h;}
static void feed(const void *b,size_t n){assert(n<=sizeof(incoming));memcpy(incoming,b,n);incoming_size=n;rx_cb((void*)1,NULL);}
static void line(const char *s){feed(s,strlen(s));}
static collection_usb_lte_status_t status(void){collection_usb_lte_status_t s;assert(collection_usb_lte_get_status(&s));return s;}
static void usb_connection(bool connected){usb_device_desc_t d={0x05c6,0x9330};usbh_cdc_device_event_data_t e={0};
 if(connected){e.new_dev.dev_addr=7;e.new_dev.device_desc=&d;}else e.dev_gone.dev_addr=7;
 event_cb(connected?0:1,&e,NULL);}
static DWORD WINAPI gated_disconnect(void *u)
{(void)u;usb_connection(false);return 0;}
static DWORD WINAPI cancellation(void *u)
{(void)u;assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_BAD_STATE);
 collection_usb_lte_cancel();return 0;}
static DWORD WINAPI delayed_disconnect(void *u)
{(void)u;assert(WaitForSingleObject(in_write,500)==WAIT_OBJECT_0);SetEvent(release_write);usb_connection(false);return 0;}
static DWORD WINAPI ppp_transmit(void *u)
{(void)u;uint8_t packet[]={0x7e,9,8};assert(eth_driver->transmit(eth_driver,packet,sizeof(packet))==ESP_OK);return 0;}
static DWORD WINAPI delayed_release(void *u)
{(void)u;Sleep(50);SetEvent(release_write);return 0;}
int main(void)
{
 owner_thread=GetCurrentThreadId();
 collection_usb_lte_config_t c={.vendor_id=0x05c6,.product_id=0x9330,.modem_interface=-1};
 assert(collection_usb_lte_init(&c)==ESP_ERR_INVALID_ARG && !writes);
 c.modem_interface=8;c.descriptor_verified=true;
 assert(collection_usb_lte_init(&c)==ESP_OK);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_BAD_STATE);
 usb_device_desc_t other={0x05c6,0x9999};
 usbh_cdc_device_event_data_t wrong={.new_dev={7,&other}};
 event_cb(CDC_HOST_DEVICE_EVENT_CONNECTED,&wrong,NULL);
 assert(!opened_itf && !status().usb_connected);
 usb_connection(true);assert(opened_itf==8 && !writes);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_BAD_STATE);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_PENDING);
 atomic_store(&clock_ms,100);assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_TIMEOUT);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_PENDING);
 assert(!strcmp(last_write,"AT\r\n"));line("\r\nBROKENOK\r\n");
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_PENDING);line("\r\nO");
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_PENDING);line("K\r\n");
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_OK && status().command_mode);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_PENDING);
 assert(!strcmp(last_write,"ATD*99***1#\r\n"));line("\r\nOK\r\n");
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_PENDING && starts==0);
 const unsigned char reply[]={13,10,'C','O','N','N','E','C','T',13,10,0x7e,0xff,0x03};
 feed(reply,sizeof(reply));assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_PENDING && starts==0);
 const unsigned char early[]={0x7e,0x21};feed(early,sizeof(early));
 atomic_store(&clock_ms,199);assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_PENDING && starts==0);
 atomic_store(&clock_ms,200);assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_OK && starts==1);
 assert(ppp_size==5 && ppp[0]==0x7e && ppp[3]==0x7e && !status().ppp_has_ip);
 ip_event_got_ip_t got={&netif};handlers[0](NULL,IP_EVENT,IP_EVENT_PPP_GOT_IP,&got);
 assert(status().ppp_has_ip && !status().ppp_stopped);
 uint8_t packet[]={0x7e,1,2};unsigned before=writes;
 assert(eth_driver->transmit(eth_driver,packet,sizeof(packet))==ESP_OK && writes==before+1);
 feed(packet,sizeof(packet));assert(ppp_size==8 && writes==before+1);
 uint32_t online_epoch=status().connection_epoch;
 in_write=CreateEvent(NULL,TRUE,FALSE,NULL);release_write=CreateEvent(NULL,TRUE,FALSE,NULL);
 HANDLE tx=CreateThread(NULL,0,ppp_transmit,NULL,0,NULL);assert(tx);
 assert(WaitForSingleObject(in_write,500)==WAIT_OBJECT_0);
 collection_usb_lte_status_t busy_status,busy_before;
 memset(&busy_status,0xa5,sizeof(busy_status));busy_before=busy_status;
 assert(!collection_usb_lte_get_status(&busy_status));
 assert(!memcmp(&busy_status,&busy_before,sizeof(busy_status)));
 assert(collection_usb_lte_poll_for_epoch(online_epoch)==COLLECTION_USB_LTE_BUSY);
 SetEvent(release_write);
 assert(WaitForSingleObject(tx,1000)==WAIT_OBJECT_0);CloseHandle(tx);
 CloseHandle(in_write);CloseHandle(release_write);in_write=NULL;release_write=NULL;
 assert(collection_usb_lte_get_status(&busy_status) && busy_status.usb_connected &&
     busy_status.ppp_has_ip && busy_status.connection_epoch==online_epoch);
 unsigned before_disconnect_writes=writes,before_disconnect_starts=starts;
 usb_connection(false);usb_connection(true);
 uint32_t reconnected_epoch=status().connection_epoch;
 assert(reconnected_epoch!=online_epoch && status().usb_connected && !status().ppp_stopped);
 next_stop=ESP_FAIL;unsigned before_disconnect_stops=stops;
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_IO_ERROR);
 assert(stops==before_disconnect_stops+1 && writes==before_disconnect_writes &&
     starts==before_disconnect_starts && status().last_io_error==ESP_FAIL);
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_PENDING);
 assert(stops==before_disconnect_stops+2 && writes==before_disconnect_writes &&
     starts==before_disconnect_starts);
 assert(collection_usb_lte_poll_for_epoch(online_epoch)==COLLECTION_USB_LTE_STALE_EPOCH);
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,reconnected_epoch)==COLLECTION_USB_LTE_BAD_STATE);
 assert(stops==before_disconnect_stops+2 && writes==before_disconnect_writes &&
     starts==before_disconnect_starts);
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_PENDING);
 esp_netif_t *np=&netif;handlers[2](NULL,NETIF_PPP_STATUS,NETIF_PPP_PHASE_DEAD,&np);
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_OK);
 assert(collection_usb_lte_poll_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_IDLE);
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,reconnected_epoch)==COLLECTION_USB_LTE_PENDING);
 line("\r\nOK\r\n");
 assert(collection_usb_lte_poll_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_OK);
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_DIAL,100,reconnected_epoch)==COLLECTION_USB_LTE_PENDING);
 line("\r\nCONNECT\r\n");
 assert(collection_usb_lte_poll_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_PENDING);
 atomic_store(&clock_ms,300);
 assert(collection_usb_lte_poll_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_OK);
 assert(starts==before_disconnect_starts+1);
 in_write=CreateEvent(NULL,TRUE,FALSE,NULL);release_write=CreateEvent(NULL,TRUE,FALSE,NULL);
 tx=CreateThread(NULL,0,ppp_transmit,NULL,0,NULL);assert(tx);
 assert(WaitForSingleObject(in_write,500)==WAIT_OBJECT_0);
 assert(collection_usb_lte_cancel_poll_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_BUSY);
 HANDLE release=CreateThread(NULL,0,delayed_release,NULL,0,NULL);assert(release);
 assert(collection_usb_lte_quiesce_for_epoch(reconnected_epoch)==COLLECTION_USB_LTE_OK &&
     stops==before_disconnect_stops+3 && !status().hangup_confirmed);
 assert(WaitForSingleObject(tx,1000)==WAIT_OBJECT_0);CloseHandle(tx);
 assert(WaitForSingleObject(release,1000)==WAIT_OBJECT_0);CloseHandle(release);
 CloseHandle(in_write);CloseHandle(release_write);in_write=NULL;release_write=NULL;
 assert(eth_driver->transmit(eth_driver,packet,sizeof(packet))!=ESP_OK);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_ESCAPE,100)==COLLECTION_USB_LTE_BAD_STATE);
 atomic_store(&clock_ms,1300);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_ESCAPE,100)==COLLECTION_USB_LTE_PENDING);
 assert(!strcmp(last_write,"+++"));line("\r\nOK\r\n");assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_OK);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_HANGUP,100)==COLLECTION_USB_LTE_PENDING);
 line("\r\nOK\r\n");assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_OK && status().hangup_confirmed);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_BAD_STATE);
 handlers[2](NULL,NETIF_PPP_STATUS,NETIF_PPP_PHASE_DEAD,&np);
 assert(status().ppp_stopped);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_PENDING);
 unsigned starts_before_timeout=starts;
 atomic_store(&clock_ms,1400);assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_TIMEOUT);
 line("\r\nCONNECT\r\n");assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_TIMEOUT && starts==starts_before_timeout);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_BAD_STATE);
 unsigned writes_before_plain_reconnect=writes;
 usb_connection(false);usb_connection(true);assert(writes==writes_before_plain_reconnect);
 uint32_t stale_epoch=status().connection_epoch;
 usb_connection(false);usb_connection(true);
 unsigned scoped_writes=writes,scoped_starts=starts,scoped_stops=stops;
 collection_usb_lte_status_t scoped_before=status();
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,stale_epoch)==COLLECTION_USB_LTE_STALE_EPOCH);
 assert(collection_usb_lte_poll_for_epoch(stale_epoch)==COLLECTION_USB_LTE_STALE_EPOCH);
 assert(collection_usb_lte_cancel_poll_for_epoch(stale_epoch)==COLLECTION_USB_LTE_STALE_EPOCH);
 assert(collection_usb_lte_quiesce_for_epoch(stale_epoch)==COLLECTION_USB_LTE_STALE_EPOCH);
 collection_usb_lte_status_t scoped_after=status();
 assert(scoped_after.connection_epoch==scoped_before.connection_epoch &&
     scoped_after.result==scoped_before.result && writes==scoped_writes &&
     starts==scoped_starts && stops==scoped_stops);
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,scoped_after.connection_epoch)==
     COLLECTION_USB_LTE_PENDING);
 assert(collection_usb_lte_cancel_poll_for_epoch(
     scoped_after.connection_epoch)==COLLECTION_USB_LTE_CANCELLED);
 usb_connection(false);usb_connection(true);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_PENDING);
 HANDLE t=CreateThread(NULL,0,cancellation,NULL,0,NULL);assert(t);
 assert(WaitForSingleObject(t,1000)==WAIT_OBJECT_0);CloseHandle(t);
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_CANCELLED);
 usb_connection(false);usb_connection(true);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_PENDING);
 unsigned char big[1536];memset(big,'x',sizeof(big));feed(big,sizeof(big));feed(big,600);
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_OVERFLOW && status().rx_overflows==1);
 usb_connection(false);usb_connection(true);next_write=ESP_ERR_TIMEOUT;
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_IO_ERROR);
 assert(status().last_io_error==ESP_ERR_TIMEOUT);
 usb_connection(false);usb_connection(true);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_PROBE,100)==COLLECTION_USB_LTE_PENDING);
 line("\r\n+CME ERROR: 10\r\n");
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_MODEM_ERROR);
 assert(!strcmp(status().last_modem_result,"+CME ERROR: 10"));
 usb_connection(false);usb_connection(true);
 uint32_t precommit_epoch=status().connection_epoch;
 assert(collection_usb_lte_poll_for_epoch(precommit_epoch)==COLLECTION_USB_LTE_IDLE);
 before_callback_gate=CreateEvent(NULL,TRUE,FALSE,NULL);
 release_callback_gate=CreateEvent(NULL,TRUE,FALSE,NULL);
 unsigned precommit_writes=writes;
 atomic_store(&intercept_callback_gate,true);
 t=CreateThread(NULL,0,gated_disconnect,NULL,0,NULL);assert(t);
 assert(WaitForSingleObject(before_callback_gate,500)==WAIT_OBJECT_0);
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_PENDING);
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,precommit_epoch)==COLLECTION_USB_LTE_BAD_STATE);
 assert(writes==precommit_writes);
 SetEvent(release_callback_gate);
 assert(WaitForSingleObject(t,1000)==WAIT_OBJECT_0);CloseHandle(t);
 atomic_store(&intercept_callback_gate,false);
 assert(!status().usb_connected);
 usb_connection(true);
 in_write=CreateEvent(NULL,TRUE,FALSE,NULL);release_write=CreateEvent(NULL,TRUE,FALSE,NULL);
 t=CreateThread(NULL,0,delayed_disconnect,NULL,0,NULL);assert(t);
 uint32_t submission_epoch=status().connection_epoch;
 assert(collection_usb_lte_begin_for_epoch(
     COLLECTION_USB_LTE_PROBE,100,submission_epoch)==COLLECTION_USB_LTE_PENDING);
 assert(WaitForSingleObject(t,1000)==WAIT_OBJECT_0);CloseHandle(t);
 assert(collection_usb_lte_poll_for_epoch(submission_epoch)==
     COLLECTION_USB_LTE_STALE_EPOCH);
 assert(!status().usb_connected && status().driver_objects_retained);
 assert(eth_driver->deinit(eth_driver)==ESP_ERR_NOT_SUPPORTED);
 puts("native actual connector: explicit descriptor, one owner, exact AT, split CONNECT/PPP suffix, IP gate, bounded deadline, late reply, cancellation thread, overflow, I/O failure, generation-safe online disconnect/reconnect redial, disconnect during submission, retained shutdown PASS");
 return 0;
}
"""


class CollectionUsbLteNative(unittest.TestCase):
    def test_enabled_real_connector_behavior(self):
        headers = {
            "esp_err.h": ERRORS, "esp_netif.h": NETIF,
            "sdkconfig.h": "#define CONFIG_EGOLINK_COLLECTION_USB_LTE 1\n",
            "freertos/FreeRTOS.h": FREERTOS,
            "freertos/task.h": '#include "freertos/FreeRTOS.h"\n',
            "freertos/semphr.h": '#include "freertos/FreeRTOS.h"\n',
            "esp_event.h": EVENT, "esp_netif_ppp.h": PPP,
            "esp_timer.h": "#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
            "iot_usbh_cdc.h": CDC, "iot_eth.h": ETH,
            "iot_eth_types.h": '#include "iot_eth.h"\n',
            "iot_eth_interface.h": '#include "iot_eth.h"\n',
            "iot_eth_netif_glue.h": '#include "iot_eth.h"\n',
        }
        output = run_c(HARNESS, components=("collection_usb_lte",), headers=headers,
                       extra_sources=[COMP/"collection_usb_lte/collection_usb_lte_state.c"])
        self.assertIn("retained shutdown PASS", output)

    def test_disabled_profile_has_no_transport_claim(self):
        output = run_c('''#include <assert.h>
#include <stdio.h>
#include "collection_usb_lte.h"
int main(void) { collection_usb_lte_status_t s;
 assert(collection_usb_lte_get_status(&s)); assert(!s.enabled && !s.ppp_has_ip);
 assert(collection_usb_lte_init(NULL)==ESP_ERR_NOT_SUPPORTED);
 assert(collection_usb_lte_begin(COLLECTION_USB_LTE_DIAL,100)==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_poll()==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_service()==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_begin_for_epoch(COLLECTION_USB_LTE_DIAL,100,1)==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_poll_for_epoch(1)==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_cancel_poll_for_epoch(1)==COLLECTION_USB_LTE_DISABLED);
 assert(collection_usb_lte_quiesce_for_epoch(1)==COLLECTION_USB_LTE_DISABLED);
 assert(!collection_usb_lte_netif());puts("disabled PASS");return 0;}''',
            components=("collection_usb_lte",),
            headers={"esp_err.h": ERRORS, "esp_netif.h": NETIF, "sdkconfig.h": ""})
        self.assertIn("disabled PASS", output)


if __name__ == "__main__":
    unittest.main()
