idf_component_register(
    SRCS "p0_delivery_runtime.c"
    INCLUDE_DIRS "include"
    REQUIRES
        p0_outbox_dispatcher
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
