idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES safety_model platform_power platform_imu
        esp_common
        esp_event
        esp_netif
        esp_system
        esp_timer
        esp_wifi
        freertos
        log
        mqtt
        nvs_flash
)
