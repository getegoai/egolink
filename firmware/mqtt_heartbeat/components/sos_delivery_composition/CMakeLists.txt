idf_component_register(
    SRCS "sos_delivery_composition.c"
    INCLUDE_DIRS "include"
    REQUIRES
        location_outbox_adapter
        location_policy_core
        p0_delivery_runtime
        p0_outbox_dispatcher
        persistent_priority_outbox
        sos_device_runtime
        sos_outbox_adapter
        sos_pending_edge_journal
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
