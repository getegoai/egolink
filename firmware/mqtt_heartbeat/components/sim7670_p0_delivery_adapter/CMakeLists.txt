idf_component_register(
    SRCS "sim7670_p0_delivery_adapter.c"
    INCLUDE_DIRS "include"
    REQUIRES p0_delivery_runtime sim7670_gnss
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
