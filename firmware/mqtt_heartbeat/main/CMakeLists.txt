idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES safety_model platform_power platform_imu sim7670_gnss
        esp_common
        esp_event
        esp_http_client
        esp_netif
        esp_system
        esp_timer
        esp_wifi
        freertos
        json
        log
        mqtt
        nvs_flash
)
