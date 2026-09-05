idf_component_register(
    SRCS "sos_orchestrator.c"
    INCLUDE_DIRS "include"
    REQUIRES sos_input persistent_priority_outbox location_policy_core
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
