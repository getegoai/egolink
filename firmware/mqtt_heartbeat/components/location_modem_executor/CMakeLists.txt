idf_component_register(
    SRCS "location_modem_executor.c"
    INCLUDE_DIRS "include"
    REQUIRES
        device_location_runtime
        location_hardware_adapter
        location_modem_arbiter
        p0_delivery_runtime
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
