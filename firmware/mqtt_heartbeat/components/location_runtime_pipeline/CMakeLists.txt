idf_component_register(
    SRCS "location_runtime_pipeline.c"
    INCLUDE_DIRS "include"
    REQUIRES
        location_engine_core
        location_policy_core
        location_state_emitter
        location_outbox_adapter
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
