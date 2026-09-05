idf_component_register(
    SRCS "sos_device_runtime.c"
    INCLUDE_DIRS "include"
    REQUIRES
        sos_input
        sos_orchestrator
        sos_outbox_adapter
        sos_pending_edge_journal
        persistent_priority_outbox
        location_policy_core
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
