idf_component_register(
    SRCS "p0_outbox_dispatcher.c"
    INCLUDE_DIRS "include"
    REQUIRES
        location_outbox_adapter
        mbedtls
        persistent_priority_outbox
        sos_outbox_adapter
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
