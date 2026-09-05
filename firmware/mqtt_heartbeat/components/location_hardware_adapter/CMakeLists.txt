idf_component_register(
    SRCS "location_hardware_adapter.c"
    INCLUDE_DIRS "include"
    REQUIRES
        device_location_runtime
        location_runtime_pipeline
        platform_imu
        sim7670_gnss
        mbedtls
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
