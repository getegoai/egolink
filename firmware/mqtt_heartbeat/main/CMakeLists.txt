# ESP-IDF expands the component dependency graph before project Kconfig values
# are available. Keep the exact union stable here; only the application source
# is selected later. The LOC-021S source still has no legacy runtime caller.
set(EGOLINK_MAIN_REQUIREMENTS
    esp_common
    esp_event
    esp_http_client
    esp_netif
    esp_system
    esp_timer
    esp_wifi
    freertos
    json
    location_outbox_adapter
    log
    mqtt
    nvs_flash
    p0_delivery_runtime
    p0_outbox_dispatcher
    persistent_priority_outbox
    persistent_priority_outbox_partition
    platform_imu
    platform_power
    safety_model
    sim7670_gnss
    sim7670_location_modem_owner
    sos_outbox_adapter
)

if(CONFIG_EGOLINK_LOC021S_MODEM_OWNER_SMOKE_PROFILE)
    set(EGOLINK_MAIN_SOURCES "loc021s_modem_owner_main.c")
else()
    set(EGOLINK_MAIN_SOURCES "app_main.c")
endif()

idf_component_register(
    SRCS ${EGOLINK_MAIN_SOURCES}
    INCLUDE_DIRS "."
    REQUIRES ${EGOLINK_MAIN_REQUIREMENTS}
)
