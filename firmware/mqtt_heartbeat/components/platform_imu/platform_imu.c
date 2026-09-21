#include "platform_imu.h"

#include <inttypes.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "sdkconfig.h"

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
#include "driver/i2c.h"
#include "platform_i2c_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

static const char *TAG = "egolink_platform_imu";
static const char *PLATFORM_IMU_SOURCE_MOCK = "mock_stationary";
static const char *PLATFORM_IMU_BACKEND_NAME_MOCK = "mock";
static const char *PLATFORM_IMU_SENSOR_MODEL_NONE = "none";

static bool s_initialized;
static platform_imu_backend_t s_backend = PLATFORM_IMU_BACKEND_MOCK;
static bool s_hardware_present;
static bool s_driver_enabled;
static bool s_data_is_mock = true;
static const char *s_source = "mock_stationary";
static const char *s_backend_name = "mock";
static const char *s_backend_status = "mock_default";
static const char *s_sensor_model = "none";
static uint32_t s_sample_interval_ms;
static int s_last_error;
static platform_imu_sample_t s_ring[PLATFORM_IMU_RING_CAPACITY];
static size_t s_write_index;
static size_t s_count;
static uint32_t s_next_seq;
static uint32_t s_dropped_samples;
static platform_imu_sample_t s_latest;
#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
static bool s_measurement_enabled;
#endif

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static const char *safe_source(const char *source)
{
    return source ? source : "unknown";
}

static void platform_imu_set_mock_backend(const char *status)
{
    s_backend = PLATFORM_IMU_BACKEND_MOCK;
    s_hardware_present = false;
    s_driver_enabled = false;
    s_data_is_mock = true;
    s_source = PLATFORM_IMU_SOURCE_MOCK;
    s_backend_name = PLATFORM_IMU_BACKEND_NAME_MOCK;
    s_backend_status = status ? status : "mock_default";
    s_sensor_model = PLATFORM_IMU_SENSOR_MODEL_NONE;
    s_sample_interval_ms = 0;
    s_last_error = 0;
#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    s_measurement_enabled = false;
#endif
}

static platform_imu_sample_t platform_imu_stationary_sample(void)
{
    return (platform_imu_sample_t){
        .seq = 0,
        .uptime_ms = uptime_ms(),
        .accel_mg_x = 0,
        .accel_mg_y = 0,
        .accel_mg_z = 1000,
        .gyro_mdps_x = 0,
        .gyro_mdps_y = 0,
        .gyro_mdps_z = 0,
        .sample_is_mock = true,
        .source = PLATFORM_IMU_SOURCE_MOCK,
    };
}

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
static const char *PLATFORM_IMU_SOURCE_QMI8658 = "qmi8658_i2c";
static const char *PLATFORM_IMU_BACKEND_NAME_QMI8658 = "qmi8658";
static const char *PLATFORM_IMU_SENSOR_MODEL_QMI8658 = "QMI8658";

#define QMI8658_I2C_ADDR ((uint8_t)CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_ADDR)
#define QMI8658_I2C_PORT ((i2c_port_t)CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_PORT)
#define QMI8658_I2C_TIMEOUT_MS CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_TIMEOUT_MS
#define QMI8658_WHOAMI_EXPECTED CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_WHOAMI_EXPECTED
#define QMI8658_SAMPLE_INTERVAL_MS CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SAMPLE_INTERVAL_MS

#define QMI8658_REG_WHOAMI 0x00
#define QMI8658_REG_REVISION 0x01
#define QMI8658_REG_CTRL1 0x02
#define QMI8658_REG_CTRL2 0x03
#define QMI8658_REG_CTRL3 0x04
#define QMI8658_REG_CTRL5 0x06
#define QMI8658_REG_CTRL7 0x08
#define QMI8658_REG_CTRL8 0x09
#define QMI8658_REG_TEMPERATURE_L 0x33
#define QMI8658_REG_RESET 0x60
#define QMI8658_REG_RST_RESULT 0x4D
#define QMI8658_RESET_VALUE 0xB0
#define QMI8658_RST_RESULT_VALUE 0x80
#define QMI8658_CTRL1_ADDR_AUTO_INCREMENT 0x40
#define QMI8658_CTRL2_ACCEL_4G_1000HZ 0x13
#define QMI8658_CTRL3_GYRO_512DPS_224HZ 0x55
#define QMI8658_CTRL5_ACCEL_GYRO_LPF_MODE0 0x11
#define QMI8658_CTRL7_ENABLE_ACCEL_GYRO 0x03
#define QMI8658_CTRL8_CTRL9_HANDSHAKE_STATUS_INT 0x80

#if CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS
#define AXP2101_ADDR 0x34
#define AXP2101_CHIP_ID_REG 0x03
#define AXP2101_EXPECTED_CHIP_ID 0x4A
#define AXP2101_DC_ONOFF_DVM_CTRL 0x80
#define AXP2101_DC_VOL0_CTRL 0x82
#define AXP2101_LDO_ONOFF_CTRL0 0x90
#define AXP2101_LDO_VOL0_CTRL 0x92
#define AXP2101_DC1_3300MV_VALUE ((3300 - 1500) / 100)
#define AXP2101_ALDO1_3300MV_VALUE ((3300 - 500) / 100)
#endif

static esp_err_t platform_imu_i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len)
{
    esp_err_t err = platform_i2c_bus_lease_acquire(
        QMI8658_I2C_PORT,
        QMI8658_I2C_TIMEOUT_MS);
    if (err != ESP_OK) {
        return err;
    }
    err = i2c_master_write_read_device(
        QMI8658_I2C_PORT,
        addr,
        &reg,
        1,
        data,
        len,
        pdMS_TO_TICKS(QMI8658_I2C_TIMEOUT_MS));
    esp_err_t release_err = platform_i2c_bus_lease_release(QMI8658_I2C_PORT);
    return err != ESP_OK ? err : release_err;
}

static esp_err_t platform_imu_i2c_read_u8(uint8_t addr, uint8_t reg, uint8_t *value)
{
    return platform_imu_i2c_read(addr, reg, value, 1);
}

static esp_err_t platform_imu_i2c_write_u8(uint8_t addr, uint8_t reg, uint8_t value)
{
    uint8_t payload[2] = {reg, value};
    esp_err_t err = platform_i2c_bus_lease_acquire(
        QMI8658_I2C_PORT,
        QMI8658_I2C_TIMEOUT_MS);
    if (err != ESP_OK) {
        return err;
    }
    err = i2c_master_write_to_device(
        QMI8658_I2C_PORT,
        addr,
        payload,
        sizeof(payload),
        pdMS_TO_TICKS(QMI8658_I2C_TIMEOUT_MS));
    esp_err_t release_err = platform_i2c_bus_lease_release(QMI8658_I2C_PORT);
    return err != ESP_OK ? err : release_err;
}

static esp_err_t platform_imu_i2c_update_bits(uint8_t addr, uint8_t reg, uint8_t mask, uint8_t value)
{
    uint8_t current = 0;
    esp_err_t err = platform_imu_i2c_read_u8(addr, reg, &current);
    if (err != ESP_OK) {
        return err;
    }
    current = (uint8_t)((current & (uint8_t)(~mask)) | (value & mask));
    return platform_imu_i2c_write_u8(addr, reg, current);
}

static esp_err_t qmi8658_i2c_read(uint8_t reg, uint8_t *data, size_t len)
{
    return platform_imu_i2c_read(QMI8658_I2C_ADDR, reg, data, len);
}

static esp_err_t qmi8658_i2c_read_u8(uint8_t reg, uint8_t *value)
{
    return platform_imu_i2c_read_u8(QMI8658_I2C_ADDR, reg, value);
}

static esp_err_t qmi8658_i2c_write_u8(uint8_t reg, uint8_t value)
{
    return platform_imu_i2c_write_u8(QMI8658_I2C_ADDR, reg, value);
}

static esp_err_t qmi8658_i2c_update_bits(uint8_t reg, uint8_t mask, uint8_t value)
{
    return platform_imu_i2c_update_bits(QMI8658_I2C_ADDR, reg, mask, value);
}

static esp_err_t qmi8658_i2c_init(void)
{
    i2c_config_t config = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SDA_GPIO,
        .scl_io_num = CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SCL_GPIO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_FREQ_HZ,
        .clk_flags = 0,
    };

    return platform_i2c_bus_ensure(QMI8658_I2C_PORT, &config);
}

#if CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS
static esp_err_t axp2101_enable_minimal_rails(void)
{
    uint8_t chip_id = 0;
    esp_err_t err = platform_imu_i2c_read_u8(AXP2101_ADDR, AXP2101_CHIP_ID_REG, &chip_id);
    if (err != ESP_OK) {
        return err;
    }
    if (chip_id != AXP2101_EXPECTED_CHIP_ID) {
        s_last_error = (int)chip_id;
        return ESP_ERR_INVALID_RESPONSE;
    }

    err = platform_imu_i2c_write_u8(AXP2101_ADDR, AXP2101_DC_VOL0_CTRL, AXP2101_DC1_3300MV_VALUE);
    if (err != ESP_OK) {
        return err;
    }
    err = platform_imu_i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_VOL0_CTRL, 0x1F, AXP2101_ALDO1_3300MV_VALUE);
    if (err != ESP_OK) {
        return err;
    }
    err = platform_imu_i2c_update_bits(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, 0x01, 0x01);
    if (err != ESP_OK) {
        return err;
    }
    err = platform_imu_i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, 0x01, 0x01);
    if (err != ESP_OK) {
        return err;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
    ESP_LOGI(TAG, "PLATFORM_IMU_AXP2101_RAILS_OK chip_id=0x%02x", chip_id);
    return ESP_OK;
}
#endif

static esp_err_t qmi8658_wait_reset(uint8_t *reset_result)
{
    esp_err_t last = ESP_FAIL;
    for (int retry = 0; retry < 50; ++retry) {
        last = qmi8658_i2c_read_u8(QMI8658_REG_RST_RESULT, reset_result);
        if (last == ESP_OK && *reset_result == QMI8658_RST_RESULT_VALUE) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return last;
}

static esp_err_t qmi8658_configure_measurement(void)
{
    esp_err_t err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL8, QMI8658_CTRL8_CTRL9_HANDSHAKE_STATUS_INT);
    if (err != ESP_OK) {
        return err;
    }
    err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL2, QMI8658_CTRL2_ACCEL_4G_1000HZ);
    if (err != ESP_OK) {
        return err;
    }
    err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL3, QMI8658_CTRL3_GYRO_512DPS_224HZ);
    if (err != ESP_OK) {
        return err;
    }
    err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL5, QMI8658_CTRL5_ACCEL_GYRO_LPF_MODE0);
    if (err != ESP_OK) {
        return err;
    }
    err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL7, QMI8658_CTRL7_ENABLE_ACCEL_GYRO);
    if (err != ESP_OK) {
        return err;
    }
    for (int retry = 0; retry < 3; ++retry) {
        uint8_t ctrl7 = 0;
        err = qmi8658_i2c_read_u8(QMI8658_REG_CTRL7, &ctrl7);
        if (err == ESP_OK &&
            (ctrl7 & QMI8658_CTRL7_ENABLE_ACCEL_GYRO) == QMI8658_CTRL7_ENABLE_ACCEL_GYRO) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return err == ESP_OK ? ESP_ERR_INVALID_RESPONSE : err;
}

static esp_err_t qmi8658_stop_measurement(void)
{
    esp_err_t err = qmi8658_i2c_write_u8(QMI8658_REG_CTRL7, 0x00);
    if (err != ESP_OK) {
        return err;
    }
    for (int retry = 0; retry < 3; ++retry) {
        uint8_t ctrl7 = QMI8658_CTRL7_ENABLE_ACCEL_GYRO;
        err = qmi8658_i2c_read_u8(QMI8658_REG_CTRL7, &ctrl7);
        if (err == ESP_OK && (ctrl7 & QMI8658_CTRL7_ENABLE_ACCEL_GYRO) == 0u) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return err == ESP_OK ? ESP_ERR_INVALID_RESPONSE : err;
}

static bool platform_imu_probe_qmi8658_single_attempt(void)
{
    uint8_t whoami = 0;
    uint8_t revision = 0;
    uint8_t reset_result = 0;

    esp_err_t err = qmi8658_i2c_write_u8(QMI8658_REG_RESET, QMI8658_RESET_VALUE);
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_reset_failed";
        return false;
    }

    err = qmi8658_wait_reset(&reset_result);
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_reset_wait_failed";
        return false;
    }

    err = qmi8658_i2c_update_bits(
        QMI8658_REG_CTRL1,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT);
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_ctrl1_failed";
        return false;
    }

    err = qmi8658_i2c_read_u8(QMI8658_REG_WHOAMI, &whoami);
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_whoami_read_failed";
        return false;
    }
    if (whoami != QMI8658_WHOAMI_EXPECTED) {
        s_last_error = (int)whoami;
        s_backend_status = "qmi8658_whoami_mismatch";
        return false;
    }

    (void)qmi8658_i2c_read_u8(QMI8658_REG_REVISION, &revision);
    err = qmi8658_configure_measurement();
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_configure_failed";
        esp_err_t stop_err = qmi8658_stop_measurement();
        if (stop_err != ESP_OK) {
            s_backend = PLATFORM_IMU_BACKEND_QMI8658;
            s_hardware_present = true;
            s_driver_enabled = true;
            s_source = PLATFORM_IMU_SOURCE_QMI8658;
            s_backend_name = PLATFORM_IMU_BACKEND_NAME_QMI8658;
            s_sensor_model = PLATFORM_IMU_SENSOR_MODEL_QMI8658;
            s_measurement_enabled = true;
            s_last_error = (int)stop_err;
            s_backend_status = "qmi8658_init_configure_stop_failed";
        }
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(50));

    s_backend = PLATFORM_IMU_BACKEND_QMI8658;
    s_hardware_present = true;
    s_driver_enabled = true;
    s_data_is_mock = true;
    s_source = PLATFORM_IMU_SOURCE_QMI8658;
    s_backend_name = PLATFORM_IMU_BACKEND_NAME_QMI8658;
    s_backend_status = "qmi8658_probe_ok";
    s_sensor_model = PLATFORM_IMU_SENSOR_MODEL_QMI8658;
    s_sample_interval_ms = QMI8658_SAMPLE_INTERVAL_MS;
    s_last_error = 0;
    s_measurement_enabled = true;

    ESP_LOGI(
        TAG,
        "PLATFORM_IMU_QMI8658_PROBE_OK whoami=0x%02x expected=0x%02x revision=0x%02x reset_result=0x%02x",
        whoami,
        QMI8658_WHOAMI_EXPECTED,
        revision,
        reset_result);
    return true;
}

static bool platform_imu_init_qmi8658(void)
{
    esp_err_t err = qmi8658_i2c_init();
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_i2c_init_failed";
        return false;
    }

#if CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS
    err = axp2101_enable_minimal_rails();
    if (err != ESP_OK) {
        if (s_last_error == 0) {
            s_last_error = (int)err;
        }
        s_backend_status = "qmi8658_axp2101_rails_failed";
        return false;
    }
#endif

    const int max_retries = 3;
    for (int attempt = 1; attempt <= max_retries; ++attempt) {
        if (platform_imu_probe_qmi8658_single_attempt()) {
            if (attempt > 1) {
                ESP_LOGI(TAG, "PLATFORM_IMU_QMI8658_RETRY_RECOVERED attempt=%d", attempt);
            }
            return true;
        }

        ESP_LOGW(
            TAG,
            "PLATFORM_IMU_QMI8658_PROBE_RETRY attempt=%d/%d status=%s last_error=%d; recovering i2c bus",
            attempt,
            max_retries,
            s_backend_status,
            s_last_error);

        if (attempt < max_retries) {
            platform_i2c_bus_recover(QMI8658_I2C_PORT);
            vTaskDelay(pdMS_TO_TICKS(50));
        }
    }

    ESP_LOGE(
        TAG,
        "PLATFORM_IMU_QMI8658_PROBE_FAILED attempts=%d status=%s last_error=%d",
        max_retries,
        s_backend_status,
        s_last_error);
    return false;
}

static int16_t qmi8658_le16(const uint8_t *data)
{
    return (int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8));
}

static int qmi8658_accel_raw_to_mg(int16_t raw)
{
    return (int)((int64_t)raw * 4000 / 32768);
}

static int qmi8658_gyro_raw_to_mdps(int16_t raw)
{
    return (int)((int64_t)raw * 512000 / 32768);
}

static bool platform_imu_read_qmi8658(platform_imu_sample_t *sample)
{
    if (sample == NULL) {
        return false;
    }
    uint8_t raw[14] = {0};
    esp_err_t err = qmi8658_i2c_read(QMI8658_REG_TEMPERATURE_L, raw, sizeof(raw));
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_read_failed";
        return false;
    }

    int16_t ax = qmi8658_le16(&raw[2]);
    int16_t ay = qmi8658_le16(&raw[4]);
    int16_t az = qmi8658_le16(&raw[6]);
    int16_t gx = qmi8658_le16(&raw[8]);
    int16_t gy = qmi8658_le16(&raw[10]);
    int16_t gz = qmi8658_le16(&raw[12]);

    *sample = (platform_imu_sample_t){
        .seq = 0,
        .uptime_ms = uptime_ms(),
        .accel_mg_x = qmi8658_accel_raw_to_mg(ax),
        .accel_mg_y = qmi8658_accel_raw_to_mg(ay),
        .accel_mg_z = qmi8658_accel_raw_to_mg(az),
        .gyro_mdps_x = qmi8658_gyro_raw_to_mdps(gx),
        .gyro_mdps_y = qmi8658_gyro_raw_to_mdps(gy),
        .gyro_mdps_z = qmi8658_gyro_raw_to_mdps(gz),
        .sample_is_mock = false,
        .source = PLATFORM_IMU_SOURCE_QMI8658,
        .raw_axes = {ax, ay, az, gx, gy, gz},
        .raw_axes_valid = true,
        .read_completed_us = esp_timer_get_time(),
    };
    return true;
}

static bool platform_imu_sample_qmi8658(void)
{
    platform_imu_sample_t sample;
    if (!platform_imu_read_qmi8658(&sample)) {
        ESP_LOGW(TAG, "PLATFORM_IMU_QMI8658_SAMPLE_FAIL err=%s", esp_err_to_name((esp_err_t)s_last_error));
        return false;
    }
    bool pushed = platform_imu_push_sample(&sample);
    if (pushed) {
        s_data_is_mock = false;
        s_source = PLATFORM_IMU_SOURCE_QMI8658;
        s_backend_status = "qmi8658_sample_ok";
        s_last_error = 0;
    }
    return pushed;
}
#endif

bool platform_imu_init(void)
{
    if (!s_initialized) {
        s_write_index = 0;
        s_count = 0;
        s_next_seq = 0;
        s_dropped_samples = 0;
        platform_imu_set_mock_backend("mock_default");
        s_latest = platform_imu_stationary_sample();

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
        if (!platform_imu_init_qmi8658()) {
            ESP_LOGW(
                TAG,
                "PLATFORM_IMU_QMI8658_PROBE_UNAVAILABLE status=%s last_error=%d; falling back to mock",
                s_backend_status,
                s_last_error);
            if (s_backend != PLATFORM_IMU_BACKEND_QMI8658 || !s_measurement_enabled) {
                platform_imu_set_mock_backend("qmi8658_unavailable_mock_fallback");
            } else {
                ESP_LOGE(TAG, "PLATFORM_IMU_QMI8658_UNCONFIRMED_STOP; hardware service must fail closed");
            }
        }
#endif

        s_initialized = true;
        ESP_LOGI(
            TAG,
            "PLATFORM_IMU_INIT source=%s backend=%s ring_capacity=%d hardware_present=%s driver_enabled=%s mock=%s",
            s_source,
            s_backend_name,
            PLATFORM_IMU_RING_CAPACITY,
            s_hardware_present ? "true" : "false",
            s_driver_enabled ? "true" : "false",
            s_data_is_mock ? "true" : "false");
    }
    return true;
}

bool platform_imu_push_sample(const platform_imu_sample_t *sample)
{
    if (!sample) {
        return false;
    }
    if (!s_initialized) {
        platform_imu_init();
    }

    platform_imu_sample_t stored = *sample;
    if (stored.seq == 0) {
        stored.seq = ++s_next_seq;
    } else if (stored.seq > s_next_seq) {
        s_next_seq = stored.seq;
    }
    if (stored.uptime_ms <= 0) {
        stored.uptime_ms = uptime_ms();
    }
    if (!stored.source) {
        stored.source = "unspecified";
    }

    if (s_count == PLATFORM_IMU_RING_CAPACITY) {
        s_dropped_samples++;
    } else {
        s_count++;
    }

    s_ring[s_write_index] = stored;
    s_write_index = (s_write_index + 1) % PLATFORM_IMU_RING_CAPACITY;
    s_latest = stored;
    s_source = stored.source;
    if (stored.sample_is_mock) {
        s_data_is_mock = true;
    } else {
        s_data_is_mock = false;
    }

    ESP_LOGI(
        TAG,
        "PLATFORM_IMU_SAMPLE seq=%" PRIu32 " source=%s mock=%s ring_count=%u dropped=%" PRIu32
        " accel_mg=%d,%d,%d gyro_mdps=%d,%d,%d",
        stored.seq,
        safe_source(stored.source),
        stored.sample_is_mock ? "true" : "false",
        (unsigned)s_count,
        s_dropped_samples,
        stored.accel_mg_x,
        stored.accel_mg_y,
        stored.accel_mg_z,
        stored.gyro_mdps_x,
        stored.gyro_mdps_y,
        stored.gyro_mdps_z);
    return true;
}

bool platform_imu_sample_mock(void)
{
    if (!s_initialized) {
        platform_imu_init();
    }
    uint32_t next_seq = s_next_seq + 1;
    int wobble_mg = (int)(next_seq % 5) - 2;
    platform_imu_sample_t sample = {
        .seq = 0,
        .uptime_ms = uptime_ms(),
        .accel_mg_x = wobble_mg,
        .accel_mg_y = -wobble_mg,
        .accel_mg_z = 1000 + wobble_mg,
        .gyro_mdps_x = 0,
        .gyro_mdps_y = 0,
        .gyro_mdps_z = 0,
        .sample_is_mock = true,
        .source = PLATFORM_IMU_SOURCE_MOCK,
    };
    return platform_imu_push_sample(&sample);
}

bool platform_imu_sample(void)
{
    if (!s_initialized) {
        platform_imu_init();
    }

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    if (s_backend == PLATFORM_IMU_BACKEND_QMI8658 && s_driver_enabled) {
        bool one_shot = !s_measurement_enabled;
        if (one_shot && !platform_imu_capture_begin()) {
            if (s_measurement_enabled) {
                return false;
            }
            s_backend_status = "qmi8658_one_shot_begin_failed_mock_fallback";
            return platform_imu_sample_mock();
        }
        if (one_shot) {
            bool warmup_ok = true;
            for (int index = 0; index < 10; ++index) {
                vTaskDelay(pdMS_TO_TICKS(50));
                platform_imu_sample_t discarded;
                if (!platform_imu_read_qmi8658(&discarded)) {
                    warmup_ok = false;
                    break;
                }
            }
            if (!warmup_ok) {
                bool stopped = platform_imu_capture_end();
                s_backend_status = stopped ? "qmi8658_one_shot_warmup_failed_mock_fallback"
                                           : "qmi8658_one_shot_warmup_stop_failed";
                return stopped ? platform_imu_sample_mock() : false;
            }
        }
        bool sampled = platform_imu_sample_qmi8658();
        bool stopped = !one_shot || platform_imu_capture_end();
        if (!stopped) {
            ESP_LOGW(TAG, "PLATFORM_IMU_QMI8658_ONE_SHOT_STOP_FAIL err=%s", esp_err_to_name((esp_err_t)s_last_error));
            return false;
        }
        if (sampled) {
            return true;
        }
        s_backend_status = "qmi8658_read_failed_mock_fallback";
    }
#endif

    return platform_imu_sample_mock();
}

bool platform_imu_capture_begin(void)
{
    if (!s_initialized) {
        platform_imu_init();
    }

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    if (s_backend != PLATFORM_IMU_BACKEND_QMI8658 || !s_hardware_present || !s_driver_enabled) {
        return false;
    }
    esp_err_t err = qmi8658_configure_measurement();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "PLATFORM_IMU_CAPTURE_BEGIN_RETRY err=%d; recovering i2c bus", (int)err);
        platform_i2c_bus_recover(QMI8658_I2C_PORT);
        vTaskDelay(pdMS_TO_TICKS(20));
        err = qmi8658_configure_measurement();
    }
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_capture_begin_failed";
        esp_err_t stop_err = qmi8658_stop_measurement();
        if (stop_err == ESP_OK) {
            s_measurement_enabled = false;
        } else {
            s_measurement_enabled = true;
            s_last_error = (int)stop_err;
            s_backend_status = "qmi8658_capture_begin_stop_failed";
        }
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
    s_measurement_enabled = true;
    s_backend_status = "qmi8658_capture_ready";
    s_last_error = 0;
    return true;
#else
    return false;
#endif
}

bool platform_imu_sample_real(platform_imu_sample_t *sample)
{
    if (sample == NULL) {
        return false;
    }
    if (!s_initialized) {
        platform_imu_init();
    }

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    if (s_backend != PLATFORM_IMU_BACKEND_QMI8658 || !s_hardware_present || !s_driver_enabled ||
        !s_measurement_enabled) {
        return false;
    }
    platform_imu_sample_t captured;
    if (!platform_imu_read_qmi8658(&captured)) {
        return false;
    }
    captured.seq = ++s_next_seq;
    *sample = captured;
    s_latest = captured;
    s_data_is_mock = false;
    s_source = PLATFORM_IMU_SOURCE_QMI8658;
    s_backend_status = "qmi8658_capture_sample_ok";
    s_last_error = 0;
    return true;
#else
    return false;
#endif
}

bool platform_imu_capture_end(void)
{
    if (!s_initialized) {
        platform_imu_init();
    }

#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658
    if (s_backend != PLATFORM_IMU_BACKEND_QMI8658 || !s_hardware_present || !s_driver_enabled) {
        return false;
    }
    esp_err_t err = qmi8658_stop_measurement();
    if (err != ESP_OK) {
        s_last_error = (int)err;
        s_backend_status = "qmi8658_capture_end_failed";
        return false;
    }
    s_measurement_enabled = false;
    s_backend_status = "qmi8658_measurement_stopped";
    s_last_error = 0;
    return true;
#else
    return false;
#endif
}

void platform_imu_get_snapshot(platform_imu_snapshot_t *snapshot)
{
    if (!snapshot) {
        return;
    }
    if (!s_initialized) {
        platform_imu_init();
    }
    *snapshot = (platform_imu_snapshot_t){
        .initialized = s_initialized,
        .backend = s_backend,
        .hardware_present = s_hardware_present,
        .driver_enabled = s_driver_enabled,
        .data_is_mock = s_data_is_mock,
        .source = s_source,
        .backend_name = s_backend_name,
        .backend_status = s_backend_status,
        .sensor_model = s_sensor_model,
        .sample_interval_ms = s_sample_interval_ms,
        .last_error = s_last_error,
        .ring_capacity = PLATFORM_IMU_RING_CAPACITY,
        .ring_count = s_count,
        .dropped_samples = s_dropped_samples,
        .latest = s_latest,
    };
}

size_t platform_imu_read_recent(platform_imu_sample_t *samples, size_t max_samples)
{
    if (!samples || max_samples == 0) {
        return 0;
    }
    if (!s_initialized) {
        platform_imu_init();
    }

    size_t read_count = s_count < max_samples ? s_count : max_samples;
    size_t oldest_index = (s_write_index + PLATFORM_IMU_RING_CAPACITY - s_count) % PLATFORM_IMU_RING_CAPACITY;
    size_t start_offset = s_count - read_count;

    for (size_t i = 0; i < read_count; ++i) {
        size_t ring_index = (oldest_index + start_offset + i) % PLATFORM_IMU_RING_CAPACITY;
        samples[i] = s_ring[ring_index];
    }
    return read_count;
}
