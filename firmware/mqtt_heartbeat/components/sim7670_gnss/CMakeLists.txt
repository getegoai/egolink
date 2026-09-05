idf_component_register(
    SRCS "sim7670_gnss.c" "sim7670_http_exact_parser.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_common esp_timer log
)

set_source_files_properties(
    "sim7670_http_exact_parser.c"
    PROPERTIES COMPILE_OPTIONS
    "-Wall;-Wextra;-Werror;-Wconversion;-Wformat=2;-Wshadow;-Wsign-conversion"
)
