#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>

#include "driver/i2c.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define AMOLED_BRIDGE_DEVICE_ID "wearable-node-001"
#define AMOLED_BRIDGE_ROLE "wearable_node"
#define AMOLED_BRIDGE_PROTOCOL_VERSION "0.1"
#define AMOLED_BRIDGE_FIRMWARE "egolink_amoled_bridge"
#define AMOLED_BRIDGE_BOARD "ESP32-S3-Touch-AMOLED-2.06"

#define AMOLED_I2C_PORT I2C_NUM_0
#define AMOLED_I2C_SDA_GPIO 15
#define AMOLED_I2C_SCL_GPIO 14
#define AMOLED_I2C_FREQ_HZ 100000
#define AMOLED_I2C_TIMEOUT_MS 1000

#define AMOLED_BOOT_JSON_DELAY_MS 5000
#define AMOLED_SAMPLE_COUNT 40
#define AMOLED_SAMPLE_INTERVAL_MS 50
#define AMOLED_SAMPLE_HZ 20

#define AXP2101_ADDR 0x34
#define AXP2101_CHIP_ID_REG 0x03
#define AXP2101_EXPECTED_CHIP_ID 0x4A
#define AXP2101_DC_ONOFF_DVM_CTRL 0x80
#define AXP2101_DC_VOL0_CTRL 0x82
#define AXP2101_LDO_ONOFF_CTRL0 0x90
#define AXP2101_LDO_VOL0_CTRL 0x92
#define AXP2101_DC1_3300MV_VALUE ((3300 - 1500) / 100)
#define AXP2101_ALDO1_3300MV_VALUE ((3300 - 500) / 100)

#define QMI8658_ADDR 0x6B
#define QMI8658_WHOAMI_EXPECTED 0x05
#define QMI8658_REG_WHOAMI 0x00
#define QMI8658_REG_REVISION 0x01
#define QMI8658_REG_CTRL1 0x02
#define QMI8658_REG_CTRL2 0x03
#define QMI8658_REG_CTRL3 0x04
#define QMI8658_REG_CTRL5 0x06
#define QMI8658_REG_CTRL7 0x08
#define QMI8658_REG_CTRL8 0x09
#define QMI8658_REG_STATUS_INT 0x2D
#define QMI8658_REG_STATUS0 0x2E
#define QMI8658_REG_TIMESTAMP_L 0x30
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

typedef struct {
    bool present;
    uint8_t chip_id;
    uint8_t dc_onoff_before;
    uint8_t dc_onoff_after;
    uint8_t ldo_onoff_before;
    uint8_t ldo_onoff_after;
    esp_err_t status;
} pmu_probe_t;

typedef struct {
    bool present;
    uint8_t whoami;
    uint8_t revision;
    uint8_t reset_result;
    esp_err_t status;
} qmi_probe_t;

static uint32_t s_seq = 1;

static uint32_t next_seq(void)
{
    return s_seq++;
}

static int64_t monotonic_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static void json_flush(void)
{
    fflush(stdout);
}

static esp_err_t i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len)
{
    return i2c_master_write_read_device(
        AMOLED_I2C_PORT,
        addr,
        &reg,
        1,
        data,
        len,
        pdMS_TO_TICKS(AMOLED_I2C_TIMEOUT_MS));
}

static esp_err_t i2c_read_u8(uint8_t addr, uint8_t reg, uint8_t *value)
{
    return i2c_read(addr, reg, value, 1);
}

static esp_err_t i2c_write_u8(uint8_t addr, uint8_t reg, uint8_t value)
{
    uint8_t payload[2] = {reg, value};
    return i2c_master_write_to_device(
        AMOLED_I2C_PORT,
        addr,
        payload,
        sizeof(payload),
        pdMS_TO_TICKS(AMOLED_I2C_TIMEOUT_MS));
}

static esp_err_t i2c_update_bits(uint8_t addr, uint8_t reg, uint8_t mask, uint8_t value)
{
    uint8_t current = 0;
    esp_err_t err = i2c_read_u8(addr, reg, &current);
    if (err != ESP_OK) {
        return err;
    }
    current = (uint8_t)((current & (uint8_t)(~mask)) | (value & mask));
    return i2c_write_u8(addr, reg, current);
}

static esp_err_t amoled_i2c_init(void)
{
    i2c_config_t config = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = AMOLED_I2C_SDA_GPIO,
        .scl_io_num = AMOLED_I2C_SCL_GPIO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = AMOLED_I2C_FREQ_HZ,
        .clk_flags = 0,
    };

    esp_err_t err = i2c_param_config(AMOLED_I2C_PORT, &config);
    if (err != ESP_OK) {
        return err;
    }
    return i2c_driver_install(AMOLED_I2C_PORT, I2C_MODE_MASTER, 0, 0, 0);
}

static pmu_probe_t axp2101_enable_minimal_rails(void)
{
    pmu_probe_t probe = {0};
    probe.status = i2c_read_u8(AXP2101_ADDR, AXP2101_CHIP_ID_REG, &probe.chip_id);
    if (probe.status != ESP_OK) {
        return probe;
    }
    probe.present = true;

    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, &probe.dc_onoff_before);
    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, &probe.ldo_onoff_before);

    if (probe.chip_id == AXP2101_EXPECTED_CHIP_ID) {
        (void)i2c_write_u8(AXP2101_ADDR, AXP2101_DC_VOL0_CTRL, AXP2101_DC1_3300MV_VALUE);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_VOL0_CTRL, 0x1F, AXP2101_ALDO1_3300MV_VALUE);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, 0x01, 0x01);
        (void)i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, 0x01, 0x01);
        vTaskDelay(pdMS_TO_TICKS(20));
    }

    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, &probe.dc_onoff_after);
    (void)i2c_read_u8(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, &probe.ldo_onoff_after);
    return probe;
}

static esp_err_t qmi_wait_reset(uint8_t *reset_result)
{
    esp_err_t last = ESP_FAIL;
    for (int retry = 0; retry < 50; retry++) {
        last = i2c_read_u8(QMI8658_ADDR, QMI8658_REG_RST_RESULT, reset_result);
        if (last == ESP_OK && *reset_result == QMI8658_RST_RESULT_VALUE) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return last;
}

static qmi_probe_t qmi8658_init(void)
{
    qmi_probe_t probe = {0};
    probe.status = i2c_write_u8(QMI8658_ADDR, QMI8658_REG_RESET, QMI8658_RESET_VALUE);
    if (probe.status != ESP_OK) {
        return probe;
    }

    probe.status = qmi_wait_reset(&probe.reset_result);
    (void)i2c_update_bits(
        QMI8658_ADDR,
        QMI8658_REG_CTRL1,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT,
        QMI8658_CTRL1_ADDR_AUTO_INCREMENT);

    probe.status = i2c_read_u8(QMI8658_ADDR, QMI8658_REG_WHOAMI, &probe.whoami);
    if (probe.status != ESP_OK) {
        return probe;
    }
    probe.present = probe.whoami == QMI8658_WHOAMI_EXPECTED;
    (void)i2c_read_u8(QMI8658_ADDR, QMI8658_REG_REVISION, &probe.revision);
    if (!probe.present) {
        return probe;
    }

    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL8, QMI8658_CTRL8_CTRL9_HANDSHAKE_STATUS_INT);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL2, QMI8658_CTRL2_ACCEL_4G_1000HZ);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL3, QMI8658_CTRL3_GYRO_512DPS_224HZ);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL5, QMI8658_CTRL5_ACCEL_GYRO_LPF_MODE0);
    (void)i2c_write_u8(QMI8658_ADDR, QMI8658_REG_CTRL7, QMI8658_CTRL7_ENABLE_ACCEL_GYRO);
    vTaskDelay(pdMS_TO_TICKS(50));
    return probe;
}

static int16_t le16(const uint8_t *data)
{
    return (int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8));
}

static int32_t accel_raw_to_mg(int16_t raw)
{
    return (int32_t)((int64_t)raw * 4000 / 32768);
}

static int32_t gyro_raw_to_mdps(int16_t raw)
{
    return (int32_t)((int64_t)raw * 512000 / 32768);
}

static void print_hello(void)
{
    printf(
        "{\"type\":\"hello\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"protocol_version\":\"%s\",\"seq\":%" PRIu32 ","
        "\"firmware\":\"%s\",\"board\":\"%s\"}\n",
        AMOLED_BRIDGE_DEVICE_ID,
        AMOLED_BRIDGE_ROLE,
        AMOLED_BRIDGE_PROTOCOL_VERSION,
        next_seq(),
        AMOLED_BRIDGE_FIRMWARE,
        AMOLED_BRIDGE_BOARD);
    json_flush();
}

static void print_probe(const pmu_probe_t *pmu, const qmi_probe_t *qmi)
{
    printf(
        "{\"type\":\"imu_whoami\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"seq\":%" PRIu32 ",\"device_monotonic_ms\":%" PRId64 ","
        "\"sensor_kind\":\"imu\",\"sensor_model\":\"QMI8658\","
        "\"source_availability\":\"bridge_uplink\",\"source_status\":\"unverified\","
        "\"imu_source\":\"qmi8658_i2c\",\"sample_hz\":%d,"
        "\"payload\":{\"board\":\"%s\",\"i2c_sda_gpio\":%d,\"i2c_scl_gpio\":%d,"
        "\"axp2101_addr\":%d,\"axp2101_present\":%s,\"axp2101_chip_id\":%u,"
        "\"axp2101_dc_onoff_before\":%u,\"axp2101_dc_onoff_after\":%u,"
        "\"axp2101_ldo_onoff_before\":%u,\"axp2101_ldo_onoff_after\":%u,"
        "\"qmi8658_addr\":%d,\"whoami\":%u,\"whoami_expected\":%u,"
        "\"revision\":%u,\"reset_result\":%u,"
        "\"configured_accel_range_g\":4,\"configured_accel_odr_hz\":1000,"
        "\"configured_gyro_range_dps\":512,\"configured_gyro_odr_hz\":224,"
        "\"validation_boundary\":\"identity_and_short_window_only\"}}\n",
        AMOLED_BRIDGE_DEVICE_ID,
        AMOLED_BRIDGE_ROLE,
        next_seq(),
        monotonic_ms(),
        AMOLED_SAMPLE_HZ,
        AMOLED_BRIDGE_BOARD,
        AMOLED_I2C_SDA_GPIO,
        AMOLED_I2C_SCL_GPIO,
        AXP2101_ADDR,
        pmu->present ? "true" : "false",
        pmu->chip_id,
        pmu->dc_onoff_before,
        pmu->dc_onoff_after,
        pmu->ldo_onoff_before,
        pmu->ldo_onoff_after,
        QMI8658_ADDR,
        qmi->whoami,
        QMI8658_WHOAMI_EXPECTED,
        qmi->revision,
        qmi->reset_result);
    json_flush();
}

static void print_sample(
    uint32_t sample_index,
    uint8_t status0,
    uint8_t status_int,
    uint32_t qmi_timestamp,
    int16_t ax,
    int16_t ay,
    int16_t az,
    int16_t gx,
    int16_t gy,
    int16_t gz,
    int16_t temp_raw)
{
    printf(
        "{\"type\":\"imu_sample\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"seq\":%" PRIu32 ",\"device_monotonic_ms\":%" PRId64 ","
        "\"sensor_kind\":\"imu\",\"sensor_model\":\"QMI8658\","
        "\"source_availability\":\"bridge_uplink\",\"source_status\":\"unverified\","
        "\"imu_source\":\"qmi8658_i2c\",\"sample_hz\":%d,"
        "\"payload\":{\"sample_index\":%" PRIu32 ",\"qmi_timestamp\":%" PRIu32 ","
        "\"status0\":%u,\"status_int\":%u,"
        "\"accel_mg\":[%" PRId32 ",%" PRId32 ",%" PRId32 "],"
        "\"gyro_mdps\":[%" PRId32 ",%" PRId32 ",%" PRId32 "],"
        "\"raw_accel\":[%" PRId16 ",%" PRId16 ",%" PRId16 "],"
        "\"raw_gyro\":[%" PRId16 ",%" PRId16 ",%" PRId16 "],"
        "\"temp_raw\":%" PRId16 "}}\n",
        AMOLED_BRIDGE_DEVICE_ID,
        AMOLED_BRIDGE_ROLE,
        next_seq(),
        monotonic_ms(),
        AMOLED_SAMPLE_HZ,
        sample_index,
        qmi_timestamp,
        status0,
        status_int,
        accel_raw_to_mg(ax),
        accel_raw_to_mg(ay),
        accel_raw_to_mg(az),
        gyro_raw_to_mdps(gx),
        gyro_raw_to_mdps(gy),
        gyro_raw_to_mdps(gz),
        ax,
        ay,
        az,
        gx,
        gy,
        gz,
        temp_raw);
    json_flush();
}

static void print_done(uint32_t emitted, uint32_t read_errors, uint32_t not_ready)
{
    printf(
        "{\"type\":\"amoled_bridge_done\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"seq\":%" PRIu32 ",\"device_monotonic_ms\":%" PRId64 ","
        "\"payload\":{\"samples_requested\":%d,\"samples_emitted\":%" PRIu32 ","
        "\"read_errors\":%" PRIu32 ",\"not_ready_count\":%" PRIu32 ","
        "\"sample_interval_ms\":%d}}\n",
        AMOLED_BRIDGE_DEVICE_ID,
        AMOLED_BRIDGE_ROLE,
        next_seq(),
        monotonic_ms(),
        AMOLED_SAMPLE_COUNT,
        emitted,
        read_errors,
        not_ready,
        AMOLED_SAMPLE_INTERVAL_MS);
    json_flush();
}

static void print_error(const char *stage, esp_err_t status)
{
    printf(
        "{\"type\":\"amoled_bridge_error\",\"device_id\":\"%s\",\"role\":\"%s\","
        "\"seq\":%" PRIu32 ",\"device_monotonic_ms\":%" PRId64 ","
        "\"payload\":{\"stage\":\"%s\",\"esp_err\":%d,\"esp_err_name\":\"%s\"}}\n",
        AMOLED_BRIDGE_DEVICE_ID,
        AMOLED_BRIDGE_ROLE,
        next_seq(),
        monotonic_ms(),
        stage,
        (int)status,
        esp_err_to_name(status));
    json_flush();
}

static uint32_t read_qmi_timestamp(void)
{
    uint8_t raw[3] = {0};
    if (i2c_read(QMI8658_ADDR, QMI8658_REG_TIMESTAMP_L, raw, sizeof(raw)) != ESP_OK) {
        return 0;
    }
    return (uint32_t)raw[0] | ((uint32_t)raw[1] << 8) | ((uint32_t)raw[2] << 16);
}

static void capture_sample_window(void)
{
    uint32_t emitted = 0;
    uint32_t read_errors = 0;
    uint32_t not_ready = 0;

    for (uint32_t i = 0; i < AMOLED_SAMPLE_COUNT; i++) {
        uint8_t status0 = 0;
        uint8_t status_int = 0;
        uint8_t raw[14] = {0};

        (void)i2c_read_u8(QMI8658_ADDR, QMI8658_REG_STATUS0, &status0);
        (void)i2c_read_u8(QMI8658_ADDR, QMI8658_REG_STATUS_INT, &status_int);

        esp_err_t err = i2c_read(QMI8658_ADDR, QMI8658_REG_TEMPERATURE_L, raw, sizeof(raw));
        if (err == ESP_OK) {
            int16_t temp = le16(&raw[0]);
            int16_t ax = le16(&raw[2]);
            int16_t ay = le16(&raw[4]);
            int16_t az = le16(&raw[6]);
            int16_t gx = le16(&raw[8]);
            int16_t gy = le16(&raw[10]);
            int16_t gz = le16(&raw[12]);
            if ((status0 & QMI8658_CTRL7_ENABLE_ACCEL_GYRO) == 0) {
                not_ready++;
            }
            print_sample(i, status0, status_int, read_qmi_timestamp(), ax, ay, az, gx, gy, gz, temp);
            emitted++;
        } else {
            read_errors++;
        }
        vTaskDelay(pdMS_TO_TICKS(AMOLED_SAMPLE_INTERVAL_MS));
    }

    print_done(emitted, read_errors, not_ready);
}

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(AMOLED_BOOT_JSON_DELAY_MS));
    print_hello();

    esp_err_t err = amoled_i2c_init();
    if (err != ESP_OK) {
        print_error("i2c_init", err);
        return;
    }

    pmu_probe_t pmu = axp2101_enable_minimal_rails();
    qmi_probe_t qmi = qmi8658_init();
    print_probe(&pmu, &qmi);

    if (!pmu.present) {
        print_error("axp2101_probe", pmu.status);
    }
    if (!qmi.present) {
        print_error("qmi8658_whoami", qmi.status);
        return;
    }

    capture_sample_window();
}
