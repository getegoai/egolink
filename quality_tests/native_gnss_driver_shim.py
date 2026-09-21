"""UART transcripts and a controlled clock around the complete native driver.

Only SDK/OS boundaries are supplied here. GNSS transactions, waiting, parsing,
ownership and cancellation execute firmware/mqtt_heartbeat's real C source.
"""
from quality_tests.native_owner_shim import FREE_RTOS, TASK, SEM

HEADERS = {
 "freertos/FreeRTOS.h": FREE_RTOS + "\n#define portTICK_PERIOD_MS 1\n",
 "freertos/task.h": (
  "#include <stdint.h>\nvoid native_delay(uint32_t);\nuint32_t native_ticks(void);\n"
  + TASK.replace("Sleep(ticks);", "native_delay(ticks);")
  + "\n#define taskYIELD() native_delay(1)\n"
    "static inline TickType_t xTaskGetTickCount(void){return native_ticks();}\n"
 ),
 "freertos/semphr.h": SEM + r"""
static inline SemaphoreHandle_t xSemaphoreCreateMutex(void){
 StaticSemaphore_t *s=calloc(1,sizeof(*s));return s?xSemaphoreCreateMutexStatic(s):NULL;
}
""",
 "esp_err.h": r"""
#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 257
#define ESP_ERR_INVALID_ARG 258
#define ESP_ERR_INVALID_STATE 259
#define ESP_ERR_NOT_SUPPORTED 262
#define ESP_ERR_TIMEOUT 263
static inline const char *esp_err_to_name(esp_err_t e){(void)e;return "native_error";}
""",
 "esp_check.h": '#define ESP_RETURN_ON_ERROR(x,tag,...) do{esp_err_t e=(x);(void)(tag);if(e!=ESP_OK)return e;}while(0)\n',
 "esp_log.h": r"""
#include <stdio.h>
#define ESP_LOGI(tag,...) do{(void)(tag);if(0)fprintf(stderr,__VA_ARGS__);}while(0)
#define ESP_LOGE ESP_LOGI
#define ESP_LOGW ESP_LOGI
""",
 "esp_timer.h": "#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
 "driver/gpio.h": "#pragma once\n",
 "driver/uart.h": r"""
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
typedef int uart_port_t;
typedef struct {int baud_rate,data_bits,parity,stop_bits,flow_ctrl,source_clk;} uart_config_t;
#define UART_DATA_8_BITS 8
#define UART_PARITY_DISABLE 0
#define UART_STOP_BITS_1 1
#define UART_HW_FLOWCTRL_DISABLE 0
#define UART_SCLK_DEFAULT 0
#define UART_PIN_NO_CHANGE -1
esp_err_t uart_driver_install(uart_port_t,int,int,int,void*,int);
esp_err_t uart_driver_delete(uart_port_t);
esp_err_t uart_param_config(uart_port_t,const uart_config_t*);
esp_err_t uart_set_pin(uart_port_t,int,int,int,int);
esp_err_t uart_flush_input(uart_port_t);
int uart_tx_chars(uart_port_t,const char*,uint32_t);
int uart_write_bytes(uart_port_t,const void*,size_t);
int uart_read_bytes(uart_port_t,void*,uint32_t,TickType_t);
""",
}

# The whole legacy translation unit is linked too; no HTTP entry point is run.
DEFINES = [
 "CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=1",
 "CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=1",
 "CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED=1",
 "CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=0",
 "CONFIG_EGOLINK_SIM7670_GNSS_POWER_ON_BEFORE_QUERY=1",
 "CONFIG_EGOLINK_SIM7670_AT_TIMEOUT_MS=1000",
 "CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS=1000",
 "CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM=0",
 "CONFIG_EGOLINK_SIM7670_UART_BAUD=115200",
 "CONFIG_EGOLINK_SIM7670_UART_NUM=1",
 "CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=17",
 "CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=18",
]

HARNESS = r"""
#include "sim7670_gnss.h"
#include "driver/uart.h"
#include "freertos/task.h"
#include <inttypes.h>
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed:%d: %s\n",__LINE__,#x);return 1;}}while(0)
__thread TaskHandle_t native_task;
volatile LONG native_created_tasks;
HANDLE native_startup_release;
static TaskHandle_t uart_owner;
static atomic_llong clock_us;
static atomic_bool cancelled;
static HANDLE delay_entered,delay_release;
static unsigned mode,commands,queries,power_ons,delay_calls,max_delay_ms,foreign_io,installs;
static int64_t power_completed_us,first_query_us;
static bool gate_used;
static char transmit[256];
static size_t transmit_length,read_offset;
static const char *response;
static const char *fix_response="\r\n+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10\r\nOK\r\n";
static const char *no_fix_response="\r\n+CGNSSINFO:,,,,,,,,,,,,,,,,,\r\nOK\r\n";
static int worker_status;
int64_t esp_timer_get_time(void){return atomic_load(&clock_us);}
uint32_t native_ticks(void){return (uint32_t)(esp_timer_get_time()/1000);}
void native_delay(uint32_t ms){
 ++delay_calls;if(ms>max_delay_ms)max_delay_ms=ms;
 if(mode==3 && !gate_used){
  gate_used=true;SetEvent(delay_entered);WaitForSingleObject(delay_release,5000);
 }
 if(mode==4){atomic_fetch_add(&clock_us,2000000);}
 else if(mode==5){atomic_fetch_sub(&clock_us,1000);}
 else if(mode==10){atomic_fetch_sub(&clock_us,5000);}
 else atomic_fetch_add(&clock_us,(int64_t)ms*1000);
 Sleep(1);
}
static void check_owner(void){if(native_task!=uart_owner)++foreign_io;}
esp_err_t uart_driver_install(uart_port_t p,int a,int b,int c,void*d,int e){
 (void)p;(void)a;(void)b;(void)c;(void)d;(void)e;
 ++installs;uart_owner=native_task;return ESP_OK;
}
esp_err_t uart_driver_delete(uart_port_t p){(void)p;check_owner();return ESP_OK;}
esp_err_t uart_param_config(uart_port_t p,const uart_config_t*c){(void)p;(void)c;check_owner();return ESP_OK;}
esp_err_t uart_set_pin(uart_port_t p,int a,int b,int c,int d){(void)p;(void)a;(void)b;(void)c;(void)d;check_owner();return ESP_OK;}
esp_err_t uart_flush_input(uart_port_t p){(void)p;check_owner();read_offset=0;response=NULL;return ESP_OK;}
static int transmit_bytes(const char *bytes,size_t count){
 check_owner();
 if(count>=sizeof(transmit)-transmit_length)return -1;
 memcpy(transmit+transmit_length,bytes,count);transmit_length+=count;transmit[transmit_length]=0;
 if(transmit_length>=2 && !strcmp(transmit+transmit_length-2,"\r\n")){
  transmit[transmit_length-2]=0;++commands;read_offset=0;
  if(!strcmp(transmit,"AT"))response="\r\nOK\r\n";
  else if(!strcmp(transmit,"AT+CGNSSPWR=1")){
   ++power_ons;response=mode==9?"\r\nERROR\r\n":"\r\nOK\r\n";
  }else if(!strcmp(transmit,"AT+CGNSSINFO")){
   ++queries;if(!first_query_us)first_query_us=esp_timer_get_time();
   response=mode==1 || mode==8?fix_response:mode==7?"\r\n+CGNSSINFO:malformed\r\nOK\r\n":no_fix_response;
  }else if(!strcmp(transmit,"AT+CGPSINFO")){
   ++queries;response="\r\n+CGPSINFO:,,,,,,,,\r\nOK\r\n";
  }else if(!strcmp(transmit,"AT+CGNSSPWR=0"))response="\r\nOK\r\n";
  else if(mode==11 && !strcmp(transmit,"AT+CSQ"))response="\r\n+CSQ: 18,99\r\nOK\r\n";
  else response="\r\nERROR\r\n";
  transmit_length=0;
 }
 return (int)count;
}
int uart_tx_chars(uart_port_t p,const char*b,uint32_t n){(void)p;return transmit_bytes(b,n);}
int uart_write_bytes(uart_port_t p,const void*b,size_t n){(void)p;return transmit_bytes(b,n);}
int uart_read_bytes(uart_port_t p,void*b,uint32_t cap,TickType_t ticks){
 (void)p;check_owner();
 if(!response || !response[read_offset]){atomic_fetch_add(&clock_us,(int64_t)ticks*1000);return 0;}
 size_t n=strlen(response+read_offset);if(n>cap)n=cap;
 /* Fragment the GNSS response: the real parser must await its terminal OK. */
 if(n>17)n=17;
 memcpy(b,response+read_offset,n);read_offset+=n;
 atomic_fetch_add(&clock_us,mode==6?30000:1000);
 if(power_ons && queries==0 && !response[read_offset])power_completed_us=esp_timer_get_time();
 return (int)n;
}
static bool cancel(void*c,uint32_t token){(void)c;return token==7 && atomic_load(&cancelled);}
static void reset(unsigned selected){
 mode=selected;commands=queries=power_ons=delay_calls=max_delay_ms=0;
 power_completed_us=first_query_us=0;transmit_length=read_offset=0;response=NULL;gate_used=false;
 atomic_store(&clock_us,1000000);atomic_store(&cancelled,false);
}
static sim7670_location_bounded_request_t request(uint32_t timeout,uint32_t settle){
 sim7670_location_bounded_request_t r={.timeout_ms=timeout,.per_command_timeout_cap_ms=100,
  .cancel_requested=cancel,.operation_token=7,.power_on_settle_ms=settle};return r;
}
static unsigned traces;static int trace_outcome;static char trace_response[1024];
static void raw_trace(void *ctx,const char *command,const char *raw,size_t raw_bytes,int outcome,uint64_t elapsed){
 (void)ctx;(void)command;(void)elapsed;++traces;trace_outcome=outcome;
 size_t n=raw_bytes<sizeof(trace_response)-1?raw_bytes:sizeof(trace_response)-1;
 memcpy(trace_response,raw,n);trace_response[n]='\0';
}
static int run_cases(void){
 CHECK(sim7670_at_backend_init_exclusive_current_task()==ESP_OK);
 CHECK(sim7670_at_backend_current_task_is_exclusive_owner());
 sim7670_gnss_report_t report;sim7670_location_bounded_result_t result;
 /* The default request remains a single immediate status transaction. */
 reset(0);sim7670_location_bounded_request_t r=request(1000,0);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_REPORT_READY);
 CHECK(report.no_fix_observed && !report.fix && !report.lat_valid && !report.lon_valid);
 CHECK(queries==2 && power_ons==1 && commands==4 && delay_calls==0);
 CHECK(report.cgnssinfo_query.no_fix_observed && report.cgpsinfo_query.no_fix_observed);
 printf("{\"case\":\"default_status\",\"queries\":2,\"delay_calls\":0}\n");
 reset(0);r=request(1000,0);r.trace_at=raw_trace;traces=0;
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_REPORT_READY);
 CHECK(traces==4 && power_ons==1 && strstr(trace_response,"+CGPSINFO:") && strstr(trace_response,"OK"));
 r.receiver_already_powered=true;
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_REPORT_READY);
 CHECK(traces==7 && commands==7 && power_ons==1 && delay_calls==0 && report.no_fix_observed);
 puts("{\"case\":\"session_query_and_raw_trace\",\"power_ons\":1,\"raw_attempts\":7}");
 reset(9);r=request(1000,0);r.trace_at=raw_trace;traces=0;
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 CHECK(traces==2 && trace_outcome!=0 && strstr(trace_response,"ERROR") && !report.no_fix_observed);
 puts("{\"case\":\"raw_error_not_nofix\",\"raw_attempts\":2}");
 reset(11);r=request(3000,0);r.trace_at=raw_trace;r.continue_on_status_error=true;traces=0;
 sim7670_lte_report_t cell;
 CHECK(sim7670_lte_query_status_bounded(&r,&cell,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 CHECK(traces==10 && commands==10 && cell.cpin_query.attempted && !cell.cpin_query.parse_valid);
 CHECK(cell.csq_query.parse_valid && cell.rssi_valid && cell.cpsi_query.attempted);
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_AT_TERMINAL_ERROR);
 puts("{\"case\":\"cell_partial_after_no_sim_error\",\"raw_attempts\":10}");
 reset(0);r=request(1000,0);r.trace_at=raw_trace;traces=0;
 CHECK(sim7670_gnss_power_off_bounded(&r,&result)==SIM7670_LOCATION_BOUNDED_REPORT_READY);
 CHECK(commands==1 && traces==1 && trace_outcome==0 && result.commands_completed==1 && strstr(trace_response,"OK"));
 puts("{\"case\":\"power_off_trace_one_command\",\"raw_attempts\":1}");
 for(unsigned selected=1;selected<=2;++selected){
  reset(selected);r=request(1000,300);
  CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_REPORT_READY);
  CHECK(first_query_us-power_completed_us>=300000 && first_query_us-power_completed_us<=301000);
  CHECK(delay_calls==3 && max_delay_ms<=100 && power_ons==1);
  CHECK(result.commands_attempted==commands && result.commands_completed==commands);
  CHECK(result.elapsed_ms>=300 && result.elapsed_ms<=1000 && !result.partial_or_unknown);
  if(selected==1){
   CHECK(report.fix && !report.no_fix_observed && queries==1);
   CHECK(fabs(report.lat-35.123456)<0.0000001 && fabs(report.lon-110.654321)<0.0000001);
   CHECK(report.hdop_valid && fabs(report.hdop-0.9)<0.0000001 && report.satellites==10);
   CHECK(!report.cgpsinfo_query.attempted);
  }else CHECK(!report.fix && report.no_fix_observed && queries==2 && !report.lat_valid && !report.lon_valid);
  printf("{\"case\":\"%s\",\"delay_ms\":%" PRId64 ",\"queries\":%u}\n",selected==1?"settled_fix":"settled_no_fix",(first_query_us-power_completed_us)/1000,queries);
 }
 for(unsigned selected=3;selected<=5;++selected){
  reset(selected);r=request(1000,300);
  sim7670_location_bounded_outcome_t outcome=sim7670_gnss_request_location_bounded(&r,&report,&result);
  CHECK(queries==0 && commands==2 && power_ons==1 && max_delay_ms<=100);
  CHECK(!report.location_result_valid && !report.no_fix_observed && !report.fix);
  if(selected==3){CHECK(outcome==SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED);CHECK(result.cancelled_between_commands && result.reason==SIM7670_LOCATION_BOUNDED_REASON_CANCEL_BETWEEN_AT);}
  else{CHECK(outcome==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED);}
  printf("{\"case\":\"%s\",\"outcome\":%d,\"queries\":0}\n",selected==3?"cancel_wait":selected==4?"deadline_wait":"clock_regression",outcome);
 }
 reset(6);r=request(100,90);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_DEADLINE_EXPIRED && queries==0 && commands==2 && delay_calls==0);
 printf("{\"case\":\"remaining_budget\",\"queries\":0,\"delay_calls\":0}\n");
 for(unsigned settle=1000;settle<=60001;settle+=59001){
  reset(0);r=request(1000,settle);
  CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE);
  CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_INVALID_ARGUMENT && !result.io_started && commands==0 && delay_calls==0);
 }
 printf("{\"case\":\"invalid_budget\",\"commands\":0}\n");
 reset(7);r=request(1000,300);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID && queries==1 && delay_calls==3);
 CHECK(!report.location_result_valid && !report.no_fix_observed && !report.fix);
 printf("{\"case\":\"malformed_after_wait\",\"queries\":1,\"no_fix\":false}\n");
 reset(8);
 CHECK(sim7670_gnss_request_location(&report));
 CHECK(report.fix && queries==1 && delay_calls==0 && power_ons==1);
 printf("{\"case\":\"legacy_unchanged\",\"queries\":1,\"delay_calls\":0}\n");
 reset(9);r=request(1000,300);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_AT_TERMINAL_ERROR && queries==0 && delay_calls==0);
 printf("{\"case\":\"power_on_error\",\"queries\":0,\"delay_calls\":0}\n");
 reset(10);r=request(1000,300);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN);
 /* Existing bounded_finish marks a clock before request start as I/O error. */
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_AT_IO_ERROR && queries==0 && delay_calls==1);
 CHECK(!report.no_fix_observed && !report.location_result_valid);
 printf("{\"case\":\"clock_before_request\",\"queries\":0,\"outcome\":3}\n");
 CHECK(installs==1 && foreign_io==0);
 return 0;
}
static void worker(void*c){(void)c;worker_status=run_cases();}
int main(void){
 static StaticTask_t task;static StackType_t stack[4096];
 delay_entered=CreateEvent(NULL,TRUE,FALSE,NULL);delay_release=CreateEvent(NULL,TRUE,FALSE,NULL);
 CHECK(delay_entered && delay_release);
 TaskHandle_t owner=xTaskCreateStaticPinnedToCore(worker,"native-gnss",sizeof(stack),NULL,1,stack,&task,0);
 CHECK(owner && WaitForSingleObject(delay_entered,5000)==WAIT_OBJECT_0);
 /* Real concurrent caller during dwell cannot touch the exclusive UART. */
 sim7670_gnss_report_t report;sim7670_location_bounded_result_t result;
 sim7670_location_bounded_request_t r=request(1000,300);
 CHECK(sim7670_gnss_request_location_bounded(&r,&report,&result)==SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE);
 CHECK(result.reason==SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH && !result.io_started);
 CHECK(sim7670_at_backend_init_exclusive_current_task()==ESP_ERR_INVALID_STATE);
 atomic_store(&cancelled,true);SetEvent(delay_release);
 CHECK(WaitForSingleObject(owner->thread,5000)==WAIT_OBJECT_0 && worker_status==0);
 CHECK(native_created_tasks==1 && installs==1 && foreign_io==0);
 puts("{\"case\":\"exclusive_owner\",\"tasks\":1,\"uart_installs\":1,\"foreign_io\":0}");
 return 0;
}
"""
