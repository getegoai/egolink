idf_component_register(
    SRCS "app_main.c" "ego_blackbox.c" "ego_outbox_sync.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_driver_i2c esp_driver_uart esp_driver_spi esp_driver_sdmmc esp_driver_sdspi sdmmc fatfs esp_adc esp_hw_support esp_partition spi_flash nvs_flash esp_timer esp_netif esp_wifi esp_event esp_app_format mbedtls esp32-camera ego_state_engine sim7670_cellular_call
)
