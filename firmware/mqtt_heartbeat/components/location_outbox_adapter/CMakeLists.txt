idf_component_register(
    SRCS "location_outbox_adapter.c"
    INCLUDE_DIRS "include"
    REQUIRES location_state_emitter persistent_priority_outbox json mbedtls
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
