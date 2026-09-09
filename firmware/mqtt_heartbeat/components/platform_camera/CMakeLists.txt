idf_component_register(
    SRCS "platform_camera.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_timer log mbedtls platform_i2c_bus
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
