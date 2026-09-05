idf_component_register(
    SRCS "sim7670_location_modem_owner.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_timer
        freertos
        location_modem_executor
        sim7670_gnss
        sim7670_location_modem_adapter
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wall
    -Wextra
    -Werror
    -Wconversion
    -Wformat=2
    -Wshadow
    -Wsign-conversion
)
