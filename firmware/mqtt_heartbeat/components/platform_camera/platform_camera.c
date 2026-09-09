#include "platform_camera.h"

#include <stdatomic.h>
#include <string.h>

#include "sdkconfig.h"

#ifndef CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
#define CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED 0
#endif
#ifndef CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED
#define CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED 0
#endif
#ifndef CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
#define CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL 0
#endif

#if CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED && \
    CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
#error "shared-I2C verified and unverified-trial camera states are mutually exclusive"
#endif

#define CAMERA_PIN_D0 7
#define CAMERA_PIN_D1 8
#define CAMERA_PIN_D2 9
#define CAMERA_PIN_D3 10
#define CAMERA_PIN_D4 11
#define CAMERA_PIN_D5 12
#define CAMERA_PIN_D6 13
#define CAMERA_PIN_D7 14
#define CAMERA_PIN_SDA 15
#define CAMERA_PIN_SCL 16
#define CAMERA_PIN_XCLK 39
#define CAMERA_PIN_HREF 41
#define CAMERA_PIN_VSYNC 42
#define CAMERA_PIN_PCLK 46
#define CAMERA_MODEM_UART_RX 17
#define CAMERA_MODEM_UART_TX 18
#define CAMERA_LOCAL_STOP_GPIO 0
#define CAMERA_I2C_PORT I2C_NUM_0
#define CAMERA_I2C_FREQ_HZ 100000U
#define PIN_BIT(pin) (UINT64_C(1) << (pin))
#define CAMERA_DATA_MASK (PIN_BIT(CAMERA_PIN_D0)|PIN_BIT(CAMERA_PIN_D1)|PIN_BIT(CAMERA_PIN_D2)|PIN_BIT(CAMERA_PIN_D3)|PIN_BIT(CAMERA_PIN_D4)|PIN_BIT(CAMERA_PIN_D5)|PIN_BIT(CAMERA_PIN_D6)|PIN_BIT(CAMERA_PIN_D7))
#define CAMERA_CONTROL_MASK (PIN_BIT(CAMERA_PIN_SDA)|PIN_BIT(CAMERA_PIN_SCL)|PIN_BIT(CAMERA_PIN_XCLK)|PIN_BIT(CAMERA_PIN_HREF)|PIN_BIT(CAMERA_PIN_VSYNC)|PIN_BIT(CAMERA_PIN_PCLK))

_Static_assert((CAMERA_DATA_MASK & CAMERA_CONTROL_MASK) == 0U,
               "camera data and control pins overlap");
_Static_assert(((CAMERA_DATA_MASK|CAMERA_CONTROL_MASK) &
                (PIN_BIT(CAMERA_MODEM_UART_RX)|PIN_BIT(CAMERA_MODEM_UART_TX)|PIN_BIT(CAMERA_LOCAL_STOP_GPIO))) == 0U,
               "camera pins overlap modem UART or local stop input");

#if CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
#if !CONFIG_SCCB_HARDWARE_I2C_DRIVER_LEGACY || !CONFIG_SCCB_HARDWARE_I2C_PORT0 || CONFIG_SCCB_CLK_FREQ != CAMERA_I2C_FREQ_HZ
#error "camera profile requires esp32-camera legacy SCCB existing I2C0 at 100 kHz"
#endif
#if defined(CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658) && CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
#if CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SDA_GPIO != CAMERA_PIN_SDA || CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SCL_GPIO != CAMERA_PIN_SCL || CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_PORT != 0 || CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_FREQ_HZ != CAMERA_I2C_FREQ_HZ
#error "camera profile requires QMI8658 on the shared I2C0 GPIO15/16 at 100 kHz"
#endif
#endif
#if defined(CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048) && CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048
#if CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SDA_GPIO != CAMERA_PIN_SDA || CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SCL_GPIO != CAMERA_PIN_SCL || CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_PORT != 0 || CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_FREQ_HZ != CAMERA_I2C_FREQ_HZ
#error "camera profile requires MAX17048 on the shared I2C0 GPIO15/16 at 100 kHz"
#endif
#endif
#endif

static const char *const s_profile = "waveshare_esp32s3_sim7670g_4g_ov5640";
#if CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
static atomic_bool s_lifecycle_blocked;
#if CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
static atomic_bool s_unverified_trial_attempt_consumed;
#endif
#endif

platform_camera_shared_i2c_state_t platform_camera_shared_i2c_state(void)
{
#if !CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
    return PLATFORM_CAMERA_SHARED_I2C_BLOCKED;
#elif CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED
    return PLATFORM_CAMERA_SHARED_I2C_VERIFIED;
#elif CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
    return PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED;
#else
    return PLATFORM_CAMERA_SHARED_I2C_BLOCKED;
#endif
}

const char *platform_camera_shared_i2c_state_name(
    platform_camera_shared_i2c_state_t state)
{
    switch(state){
    case PLATFORM_CAMERA_SHARED_I2C_UNKNOWN_LEGACY:return "unknown_legacy";
    case PLATFORM_CAMERA_SHARED_I2C_BLOCKED:return "blocked";
    case PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED:return "trial_unverified";
    case PLATFORM_CAMERA_SHARED_I2C_VERIFIED:return "verified";
    default:return "unknown";
    }
}

bool platform_camera_unverified_trial_attempt_consumed(void)
{
#if CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED && \
    CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
    return atomic_load(&s_unverified_trial_attempt_consumed);
#else
    return false;
#endif
}

bool platform_camera_timed_capture_allowed(void)
{
    return platform_camera_shared_i2c_state()==
        PLATFORM_CAMERA_SHARED_I2C_VERIFIED;
}

platform_camera_status_t platform_camera_preflight(const char **reason)
{
#if !CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
    if(reason)*reason="camera_profile_disabled";
    return PLATFORM_CAMERA_DISABLED;
#else
    const platform_camera_shared_i2c_state_t state=
        platform_camera_shared_i2c_state();
    if(state==PLATFORM_CAMERA_SHARED_I2C_BLOCKED){
        if(reason)*reason="blocked_shared_i2c_hardware_coexistence_unverified_gpio15_16_i2c0";
        return PLATFORM_CAMERA_BLOCKED_SHARED_I2C_UNVERIFIED;
    }
    if(atomic_load(&s_lifecycle_blocked)){
        if(reason)*reason="camera_driver_cleanup_failed_reboot_required";
        return PLATFORM_CAMERA_DEINIT_FAILED;
    }
    if(state==PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED){
        if(platform_camera_unverified_trial_attempt_consumed()){
            if(reason)*reason="camera_unverified_trial_attempt_consumed_this_boot";
            return PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED;
        }
        if(reason)*reason="camera_unverified_trial_manual_once_ready";
        return PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED;
    }
    if(reason)*reason=NULL;
    return PLATFORM_CAMERA_OK;
#endif
}

#if CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
#include "esp_camera.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "driver/i2c.h"
#include "mbedtls/sha256.h"
#include "platform_i2c_bus.h"
#include <sys/lock.h>

static _lock_t s_capture_lock;

static void digest_hex(const uint8_t digest[PLATFORM_CAMERA_SHA256_BYTES],
                       char hex[PLATFORM_CAMERA_SHA256_HEX_BYTES])
{
    static const char digits[]="0123456789abcdef";
    for(size_t i=0U;i<PLATFORM_CAMERA_SHA256_BYTES;++i){
        hex[i*2U]=digits[digest[i]>>4U];hex[i*2U+1U]=digits[digest[i]&0x0fU];
    }
    hex[PLATFORM_CAMERA_SHA256_HEX_BYTES-1U]='\0';
}

static camera_config_t camera_config(void)
{
    camera_config_t c={
        .pin_pwdn=-1,.pin_reset=-1,.pin_xclk=CAMERA_PIN_XCLK,
        .pin_sccb_sda=-1,.pin_sccb_scl=-1,.sccb_i2c_port=CAMERA_I2C_PORT,
        .pin_d7=CAMERA_PIN_D7,.pin_d6=CAMERA_PIN_D6,
        .pin_d5=CAMERA_PIN_D5,.pin_d4=CAMERA_PIN_D4,
        .pin_d3=CAMERA_PIN_D3,.pin_d2=CAMERA_PIN_D2,
        .pin_d1=CAMERA_PIN_D1,.pin_d0=CAMERA_PIN_D0,
        .pin_vsync=CAMERA_PIN_VSYNC,.pin_href=CAMERA_PIN_HREF,.pin_pclk=CAMERA_PIN_PCLK,
        .xclk_freq_hz=20000000,.ledc_timer=LEDC_TIMER_0,.ledc_channel=LEDC_CHANNEL_0,
        .pixel_format=PIXFORMAT_JPEG,.frame_size=FRAMESIZE_QVGA,.jpeg_quality=12,
        .fb_count=1,.fb_location=CAMERA_FB_IN_DRAM,.grab_mode=CAMERA_GRAB_WHEN_EMPTY,
    };
    return c;
}
#endif

platform_camera_status_t platform_camera_capture_single(
    platform_camera_frame_consumer_t consumer,void *context,
    platform_camera_capture_result_t *result)
{
    if(!result)return PLATFORM_CAMERA_CAPTURE_FAILED;
    memset(result,0,sizeof(*result));result->pin_profile=s_profile;
    result->camera_model="unknown";
    result->shared_i2c_state=platform_camera_shared_i2c_state();
    result->status=platform_camera_preflight(&result->reason);
    if(result->status!=PLATFORM_CAMERA_OK&&
       result->status!=PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED)
        return result->status;
#if CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED
    if(_lock_try_acquire(&s_capture_lock)!=0){
        result->status=PLATFORM_CAMERA_BUSY;result->reason="camera_single_frame_already_in_progress";
        return result->status;
    }
#if CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL
    bool trial_available=false;
    if(!atomic_compare_exchange_strong(&s_unverified_trial_attempt_consumed,
        &trial_available,true)){
        result->status=PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED;
        result->reason="camera_unverified_trial_attempt_consumed_this_boot";
        _lock_release(&s_capture_lock);
        return result->status;
    }
#endif
    result->status=PLATFORM_CAMERA_OK;result->reason=NULL;
    result->attempted=true;result->capture_started_us=esp_timer_get_time();
    i2c_config_t bus={.mode=I2C_MODE_MASTER,.sda_io_num=CAMERA_PIN_SDA,.scl_io_num=CAMERA_PIN_SCL,
        .sda_pullup_en=GPIO_PULLUP_ENABLE,.scl_pullup_en=GPIO_PULLUP_ENABLE,
        .master.clk_speed=CAMERA_I2C_FREQ_HZ,.clk_flags=0};
    esp_err_t bus_result=platform_i2c_bus_ensure(CAMERA_I2C_PORT,&bus);
    if(bus_result!=ESP_OK){
        result->status=PLATFORM_CAMERA_I2C_BUS_UNAVAILABLE;result->reason="platform_i2c0_gpio15_16_100khz_unavailable";
        result->capture_completed_us=esp_timer_get_time();_lock_release(&s_capture_lock);
        return result->status;
    }
    camera_config_t config=camera_config();
    esp_err_t init=esp_camera_init(&config);
    if(init!=ESP_OK){
        /* The upstream driver cleans most probe/config failures itself. Keep
         * the historical smoke's explicit cleanup attempt for early cam_init
         * failures too; do not claim cleanup success without its return. */
        esp_err_t cleanup=esp_camera_deinit();
        result->driver_deinitialized=cleanup==ESP_OK;
        if(cleanup!=ESP_OK)atomic_store(&s_lifecycle_blocked,true);
        result->status=PLATFORM_CAMERA_INIT_FAILED;
        result->reason=cleanup==ESP_OK?"esp_camera_init_failed_driver_cleaned":
            "esp_camera_init_failed_cleanup_unverified";
        result->capture_completed_us=esp_timer_get_time();
        _lock_release(&s_capture_lock);
        return result->status;
    }
    sensor_t *sensor=esp_camera_sensor_get();
    if(!sensor){
        result->status=PLATFORM_CAMERA_INIT_FAILED;
        result->reason="esp_camera_sensor_identity_unavailable";
    }else{
        result->sensor_pid=sensor->id.PID;
        if(sensor->id.PID!=OV5640_PID){
            result->status=PLATFORM_CAMERA_UNSUPPORTED_SENSOR;
            result->reason="camera_sensor_pid_not_ov5640";
        }else result->camera_model="OV5640";
    }
    if(result->status!=PLATFORM_CAMERA_OK){
        result->capture_completed_us=esp_timer_get_time();
        esp_err_t deinit=esp_camera_deinit();
        result->driver_deinitialized=deinit==ESP_OK;
        if(deinit!=ESP_OK)atomic_store(&s_lifecycle_blocked,true);
        _lock_release(&s_capture_lock);return result->status;
    }
    camera_fb_t *frame=esp_camera_fb_get();
    if(!frame){
        result->status=PLATFORM_CAMERA_CAPTURE_FAILED;result->reason="esp_camera_fb_get_failed";
    }else{
        result->frame_acquired=true;result->jpeg_bytes=frame->len;
        result->width=(uint16_t)frame->width;result->height=(uint16_t)frame->height;
        result->pixel_format=(uint8_t)frame->format;
        result->jpeg_markers_valid=frame->len>=4U&&frame->buf[0]==0xffU&&frame->buf[1]==0xd8U&&
            frame->buf[frame->len-2U]==0xffU&&frame->buf[frame->len-1U]==0xd9U;
        if(!result->jpeg_markers_valid){
            result->status=PLATFORM_CAMERA_INVALID_JPEG;result->reason="jpeg_soi_or_eoi_invalid";
        }else if(mbedtls_sha256(frame->buf,frame->len,result->sha256,0)!=0){
            result->status=PLATFORM_CAMERA_CAPTURE_FAILED;result->reason="sha256_failed";
        }else{
            digest_hex(result->sha256,result->sha256_hex);
            if(!consumer||!consumer(context,frame->buf,frame->len,result)){
                result->status=PLATFORM_CAMERA_CONSUMER_FAILED;result->reason="bounded_consumer_failed";
            }else{result->status=PLATFORM_CAMERA_OK;result->reason=NULL;}
        }
        esp_camera_fb_return(frame);result->framebuffer_returned=true;
    }
    result->capture_completed_us=esp_timer_get_time();
    esp_err_t deinit=esp_camera_deinit();result->driver_deinitialized=deinit==ESP_OK;
    if(deinit!=ESP_OK&&result->status==PLATFORM_CAMERA_OK){
        atomic_store(&s_lifecycle_blocked,true);
        result->status=PLATFORM_CAMERA_DEINIT_FAILED;
        result->reason="esp_camera_deinit_failed_reboot_required_no_physical_power_claim";
    }else if(deinit!=ESP_OK){
        atomic_store(&s_lifecycle_blocked,true);
    }
    _lock_release(&s_capture_lock);
    return result->status;
#else
    (void)consumer;(void)context;
    return result->status;
#endif
}

const char *platform_camera_status_name(platform_camera_status_t status)
{
    switch(status){
    case PLATFORM_CAMERA_OK:return "ok";
    case PLATFORM_CAMERA_DISABLED:return "disabled";
    case PLATFORM_CAMERA_BLOCKED_SHARED_I2C_UNVERIFIED:return "blocked_shared_i2c_unverified";
    case PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED:return "trial_ready_unverified";
    case PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED:return "trial_attempt_consumed";
    case PLATFORM_CAMERA_BUSY:return "busy";
    case PLATFORM_CAMERA_I2C_BUS_UNAVAILABLE:return "i2c_bus_unavailable";
    case PLATFORM_CAMERA_INIT_FAILED:return "init_failed";
    case PLATFORM_CAMERA_UNSUPPORTED_SENSOR:return "unsupported_sensor";
    case PLATFORM_CAMERA_CAPTURE_FAILED:return "capture_failed";
    case PLATFORM_CAMERA_INVALID_JPEG:return "invalid_jpeg";
    case PLATFORM_CAMERA_CONSUMER_FAILED:return "consumer_failed";
    case PLATFORM_CAMERA_DEINIT_FAILED:return "deinit_failed";
    default:return "unknown";
    }
}
