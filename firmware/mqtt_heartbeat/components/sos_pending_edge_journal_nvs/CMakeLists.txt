idf_component_register(
    SRCS "sos_pending_edge_journal_nvs.c"
    INCLUDE_DIRS "include"
    REQUIRES sos_pending_edge_journal nvs_flash
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
