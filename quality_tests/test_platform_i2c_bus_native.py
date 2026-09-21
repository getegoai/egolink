"""Run the real bus installer with two competing native sensor threads."""
import unittest
from quality_tests.native_convergence import run_c

HEADERS = {
    "esp_err.h": '''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 258
#define ESP_ERR_INVALID_STATE 259
#define ESP_ERR_TIMEOUT 263
''',
    "driver/i2c.h": '''#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
typedef int i2c_port_t;
#define I2C_NUM_MAX 2
#define I2C_MODE_MASTER 1
typedef struct {int mode,sda_io_num,scl_io_num,sda_pullup_en,scl_pullup_en;
 struct {uint32_t clk_speed;} master;uint32_t clk_flags;} i2c_config_t;
esp_err_t i2c_param_config(i2c_port_t,const i2c_config_t*);
esp_err_t i2c_driver_install(i2c_port_t,int,size_t,size_t,int);
esp_err_t i2c_driver_delete(i2c_port_t);
''',
    "sys/lock.h": '''#pragma once
typedef int _lock_t;
void _lock_acquire(_lock_t*);
int _lock_try_acquire(_lock_t*);
void _lock_release(_lock_t*);
''',
    "esp_timer.h": '''#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);
''',
    "freertos/FreeRTOS.h": '''#pragma once
#include <stdint.h>
typedef uint32_t TickType_t;
''',
    "freertos/task.h": '''#pragma once
#include "freertos/FreeRTOS.h"
void vTaskDelay(TickType_t);
''',
    "driver/gpio.h": '''#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef int gpio_num_t;
typedef enum { GPIO_MODE_INPUT_OUTPUT_OD = 0 } gpio_mode_t;
typedef enum { GPIO_PULLUP_ENABLE = 0 } gpio_pullup_t;
typedef enum { GPIO_PULLDOWN_DISABLE = 0 } gpio_pulldown_t;
typedef enum { GPIO_INTR_DISABLE = 0 } gpio_int_type_t;
typedef struct { uint64_t pin_bit_mask; gpio_mode_t mode; gpio_pullup_t pull_up_en; gpio_pulldown_t pull_down_en; gpio_int_type_t intr_type; } gpio_config_t;
static inline esp_err_t gpio_config(const gpio_config_t *c) { (void)c; return 0; }
static inline esp_err_t gpio_set_level(gpio_num_t g, uint32_t l) { (void)g; (void)l; return 0; }
static inline int gpio_get_level(gpio_num_t g) { (void)g; return 1; }
static inline esp_err_t gpio_reset_pin(gpio_num_t g) { (void)g; return 0; }
''',
    "esp_rom_sys.h": '''#pragma once
#include <stdint.h>
static inline void esp_rom_delay_us(uint32_t us) { (void)us; }
''',
}
HARNESS = r'''
#include "platform_i2c_bus.h"
#include <pthread.h>
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "freertos/task.h"
#include <sys/lock.h>
static pthread_mutex_t bus_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t start_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t start_cv=PTHREAD_COND_INITIALIZER;
static unsigned ready,go,configs,installs,lease_tries,lease_releases,delay_calls;
static esp_err_t config_error,install_error;
static i2c_config_t applied;
static _lock_t *install_lock_address,*held_transaction;
static bool force_transaction_busy;
static int64_t clock_us;
void _lock_acquire(_lock_t *l)
{if(!install_lock_address)install_lock_address=l;assert(l==install_lock_address);
 assert(!pthread_mutex_lock(&bus_lock));}
int _lock_try_acquire(_lock_t *l)
{assert(l!=install_lock_address);++lease_tries;
 if(force_transaction_busy||held_transaction==l){return 1;}
 held_transaction=l;return 0;}
void _lock_release(_lock_t *l)
{if(l==install_lock_address){assert(!pthread_mutex_unlock(&bus_lock));return;}
 assert(held_transaction==l);held_transaction=NULL;++lease_releases;}
int64_t esp_timer_get_time(void){return clock_us;}
void vTaskDelay(TickType_t ticks){++delay_calls;clock_us+=(int64_t)ticks*1000;}
esp_err_t i2c_param_config(i2c_port_t p,const i2c_config_t *c)
{assert(p>=0 && p<2);++configs;applied=*c;esp_err_t e=config_error;config_error=ESP_OK;return e;}
esp_err_t i2c_driver_install(i2c_port_t p,int mode,size_t rx,size_t tx,int flags)
{assert(p>=0 && p<2 && mode==I2C_MODE_MASTER && !rx && !tx && !flags);++installs;
 esp_err_t e=install_error;install_error=ESP_OK;return e;}
esp_err_t i2c_driver_delete(i2c_port_t p)
{assert(p>=0 && p<2); return ESP_OK;}
static i2c_config_t config(void)
{return (i2c_config_t){.mode=I2C_MODE_MASTER,.sda_io_num=15,.scl_io_num=16,
 .sda_pullup_en=1,.scl_pullup_en=1,.master={100000}};}
static void *sensor(void *arg)
{
 (void)arg;pthread_mutex_lock(&start_lock);++ready;pthread_cond_broadcast(&start_cv);
 while(!go)pthread_cond_wait(&start_cv,&start_lock);
 pthread_mutex_unlock(&start_lock);
 i2c_config_t c=config();assert(platform_i2c_bus_ensure(0,&c)==ESP_OK);return NULL;
}
int main(void)
{
 i2c_config_t c=config();
 assert(platform_i2c_bus_ensure(-1,&c)==ESP_ERR_INVALID_ARG);
 assert(platform_i2c_bus_ensure(2,&c)==ESP_ERR_INVALID_ARG);
 assert(platform_i2c_bus_ensure(0,NULL)==ESP_ERR_INVALID_ARG);
 assert(!configs && !installs);
 pthread_t a,b;assert(!pthread_create(&a,NULL,sensor,NULL));assert(!pthread_create(&b,NULL,sensor,NULL));
 pthread_mutex_lock(&start_lock);while(ready<2)pthread_cond_wait(&start_cv,&start_lock);
 go=1;pthread_cond_broadcast(&start_cv);pthread_mutex_unlock(&start_lock);
 assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
 assert(configs==1 && installs==1);
 assert(platform_i2c_bus_lease_acquire(-1,1)==ESP_ERR_INVALID_ARG);
 assert(platform_i2c_bus_lease_acquire(2,1)==ESP_ERR_INVALID_ARG);
 assert(platform_i2c_bus_lease_acquire(1,1)==ESP_ERR_INVALID_STATE);
 assert(platform_i2c_bus_lease_release(1)==ESP_ERR_INVALID_STATE);
 force_transaction_busy=true;
 assert(platform_i2c_bus_lease_acquire(0,3)==ESP_ERR_TIMEOUT);
 assert(delay_calls==3&&!held_transaction&&!lease_releases);
 force_transaction_busy=false;
 assert(platform_i2c_bus_lease_acquire(0,0)==ESP_OK);
 assert(held_transaction&&platform_i2c_bus_lease_release(0)==ESP_OK);
 assert(!held_transaction&&lease_releases==1);
 assert(platform_i2c_bus_lease_release(-1)==ESP_ERR_INVALID_ARG);
 assert(platform_i2c_bus_lease_release(2)==ESP_ERR_INVALID_ARG);
 i2c_config_t conflict=c;conflict.sda_io_num=8;
 assert(platform_i2c_bus_ensure(0,&conflict)==ESP_ERR_INVALID_STATE);
 conflict=c;conflict.master.clk_speed=400000;
 assert(platform_i2c_bus_ensure(0,&conflict)==ESP_ERR_INVALID_STATE);
 conflict=c;conflict.clk_flags=1;
 assert(platform_i2c_bus_ensure(0,&conflict)==ESP_ERR_INVALID_STATE);
 assert(configs==1 && installs==1 && applied.sda_io_num==15 && applied.master.clk_speed==100000);
 config_error=0x701;assert(platform_i2c_bus_ensure(1,&c)==0x701);assert(configs==2 && installs==1);
 install_error=ESP_FAIL;assert(platform_i2c_bus_ensure(1,&c)==ESP_FAIL);assert(installs==2);
 install_error=ESP_ERR_INVALID_STATE;assert(platform_i2c_bus_ensure(1,&c)==ESP_ERR_INVALID_STATE);assert(installs==3);
 assert(platform_i2c_bus_ensure(1,&c)==ESP_OK);assert(installs==4);
 unsigned old=configs;assert(platform_i2c_bus_ensure(1,&c)==ESP_OK);assert(configs==old && installs==4);
 puts("native pthread: install once; lease timeout/acquire/release; exact failure and retry PASS");
 return 0;
}
'''


class PlatformI2cBusNative(unittest.TestCase):
    def test_shared_install_conflict_failure_retry(self):
        output = run_c(HARNESS, components=("platform_i2c_bus",), headers=HEADERS)
        self.assertIn("lease timeout/acquire/release", output)


if __name__ == "__main__":
    unittest.main()
