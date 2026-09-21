#include "platform_i2c_bus.h"
#include <stdbool.h>
#include <stdint.h>
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <sys/lock.h>
#include "driver/gpio.h"
#include "esp_rom_sys.h"

static _lock_t install_lock;
static _lock_t transaction_locks[I2C_NUM_MAX];
static struct {
    bool installed;
    i2c_config_t config;
} buses[I2C_NUM_MAX];

static bool same_config(const i2c_config_t *a, const i2c_config_t *b)
{
    return a->mode == b->mode && a->sda_io_num == b->sda_io_num &&
        a->scl_io_num == b->scl_io_num && a->sda_pullup_en == b->sda_pullup_en &&
        a->scl_pullup_en == b->scl_pullup_en &&
        a->master.clk_speed == b->master.clk_speed && a->clk_flags == b->clk_flags;
}

static void i2c_bus_clear_pins(gpio_num_t sda_pin, gpio_num_t scl_pin)
{
    if ((int)sda_pin < 0 || (int)scl_pin < 0) {
        return;
    }

    gpio_config_t conf = {
        .pin_bit_mask = (1ULL << (uint32_t)sda_pin) | (1ULL << (uint32_t)scl_pin),
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    (void)gpio_config(&conf);

    (void)gpio_set_level(scl_pin, 1);
    (void)gpio_set_level(sda_pin, 1);
    esp_rom_delay_us(10);

    for (int i = 0; i < 9; ++i) {
        (void)gpio_set_level(scl_pin, 0);
        esp_rom_delay_us(5);
        (void)gpio_set_level(scl_pin, 1);
        esp_rom_delay_us(5);
        if (gpio_get_level(sda_pin) == 1) {
            break;
        }
    }

    (void)gpio_set_level(scl_pin, 0);
    esp_rom_delay_us(5);
    (void)gpio_set_level(sda_pin, 0);
    esp_rom_delay_us(5);
    (void)gpio_set_level(scl_pin, 1);
    esp_rom_delay_us(5);
    (void)gpio_set_level(sda_pin, 1);
    esp_rom_delay_us(5);

    (void)gpio_reset_pin(sda_pin);
    (void)gpio_reset_pin(scl_pin);
}

esp_err_t platform_i2c_bus_ensure(i2c_port_t port, const i2c_config_t *config)
{
    if ((unsigned)port >= I2C_NUM_MAX || !config || config->mode != I2C_MODE_MASTER ||
        !config->master.clk_speed) return ESP_ERR_INVALID_ARG;
    _lock_acquire(&install_lock);
    esp_err_t result;
    if (buses[port].installed) {
        result = same_config(&buses[port].config, config) ? ESP_OK : ESP_ERR_INVALID_STATE;
    } else {
        i2c_bus_clear_pins(config->sda_io_num, config->scl_io_num);
        result = i2c_param_config(port, config);
        if (result == ESP_OK) result = i2c_driver_install(port, I2C_MODE_MASTER, 0, 0, 0);
        if (result == ESP_OK) {
            buses[port].config = *config;
            buses[port].installed = true;
        }
    }
    _lock_release(&install_lock);
    return result;
}

esp_err_t platform_i2c_bus_recover(i2c_port_t port)
{
    if ((unsigned)port >= I2C_NUM_MAX) return ESP_ERR_INVALID_ARG;

    _lock_acquire(&install_lock);
    if (!buses[port].installed) {
        _lock_release(&install_lock);
        return ESP_ERR_INVALID_STATE;
    }

    i2c_config_t saved_config = buses[port].config;
    (void)i2c_driver_delete(port);
    buses[port].installed = false;

    i2c_bus_clear_pins(saved_config.sda_io_num, saved_config.scl_io_num);

    esp_err_t result = i2c_param_config(port, &saved_config);
    if (result == ESP_OK) {
        result = i2c_driver_install(port, I2C_MODE_MASTER, 0, 0, 0);
    }
    if (result == ESP_OK) {
        buses[port].config = saved_config;
        buses[port].installed = true;
    }
    _lock_release(&install_lock);
    return result;
}

esp_err_t platform_i2c_bus_lease_acquire(i2c_port_t port, uint32_t timeout_ms)
{
    if ((unsigned)port >= I2C_NUM_MAX) return ESP_ERR_INVALID_ARG;

    _lock_acquire(&install_lock);
    const bool installed = buses[port].installed;
    _lock_release(&install_lock);
    if (!installed) return ESP_ERR_INVALID_STATE;

    const int64_t started_us = esp_timer_get_time();
    const int64_t timeout_us = (int64_t)timeout_ms * 1000LL;
    for (;;) {
        if (_lock_try_acquire(&transaction_locks[port]) == 0) return ESP_OK;
        if (timeout_ms == 0U || esp_timer_get_time() - started_us >= timeout_us)
            return ESP_ERR_TIMEOUT;
        /* One scheduler tick prevents a contending sensor from busy-spinning.
         * The esp_timer deadline, not the tick duration, owns the bound. */
        vTaskDelay(1);
    }
}

esp_err_t platform_i2c_bus_lease_release(i2c_port_t port)
{
    if ((unsigned)port >= I2C_NUM_MAX) return ESP_ERR_INVALID_ARG;

    _lock_acquire(&install_lock);
    const bool installed = buses[port].installed;
    _lock_release(&install_lock);
    if (!installed) return ESP_ERR_INVALID_STATE;

    _lock_release(&transaction_locks[port]);
    return ESP_OK;
}
