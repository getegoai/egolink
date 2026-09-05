idf_component_register(
    SRCS "device_location_runtime.c"
    INCLUDE_DIRS "include"
    REQUIRES
        location_runtime_pipeline
        location_outbox_adapter
        persistent_priority_outbox
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
