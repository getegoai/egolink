idf_component_register(
    SRCS "collection_network_coordinator.c"
    INCLUDE_DIRS "include"
    REQUIRES collection_network_policy
)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
