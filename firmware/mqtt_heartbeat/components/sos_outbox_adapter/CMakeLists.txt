idf_component_register(
    SRCS "sos_outbox_adapter.c"
    INCLUDE_DIRS "include"
    REQUIRES sos_orchestrator persistent_priority_outbox json mbedtls
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
