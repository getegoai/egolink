"""Run the real bus installer with two competing native sensor threads."""
import unittest
from quality_tests.native_convergence import run_c

HEADERS = {
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
''',
    "sys/lock.h": '''#pragma once
typedef int _lock_t;
void _lock_acquire(_lock_t*);
void _lock_release(_lock_t*);
''',
}
HARNESS = r'''
#include "platform_i2c_bus.h"
#include <pthread.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/lock.h>
static pthread_mutex_t bus_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t start_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t start_cv=PTHREAD_COND_INITIALIZER;
static unsigned ready,go,configs,installs;
static esp_err_t config_error,install_error;
static i2c_config_t applied;
void _lock_acquire(_lock_t *l){(void)l;assert(!pthread_mutex_lock(&bus_lock));}
void _lock_release(_lock_t *l){(void)l;assert(!pthread_mutex_unlock(&bus_lock));}
esp_err_t i2c_param_config(i2c_port_t p,const i2c_config_t *c)
{assert(p>=0 && p<2);++configs;applied=*c;esp_err_t e=config_error;config_error=ESP_OK;return e;}
esp_err_t i2c_driver_install(i2c_port_t p,int mode,size_t rx,size_t tx,int flags)
{assert(p>=0 && p<2 && mode==I2C_MODE_MASTER && !rx && !tx && !flags);++installs;
 esp_err_t e=install_error;install_error=ESP_OK;return e;}
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
 puts("native pthread: concurrent sensors install once; config conflict leaves pins unchanged; exact failure and retry PASS");
 return 0;
}
'''


class PlatformI2cBusNative(unittest.TestCase):
    def test_shared_install_conflict_failure_retry(self):
        output = run_c(HARNESS, components=("platform_i2c_bus",), headers=HEADERS)
        self.assertIn("exact failure and retry PASS", output)


if __name__ == "__main__":
    unittest.main()
