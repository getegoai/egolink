idf_component_register(
    SRCS "sos_pending_edge_journal.c"
    INCLUDE_DIRS "include"
    REQUIRES persistent_priority_outbox
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
