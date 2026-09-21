idf_component_register(
    SRCS "sim7670_cellular_call.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_timer
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
