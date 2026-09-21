idf_component_register(
    SRCS "collection_sensor_policy.c"
    INCLUDE_DIRS "include"
    REQUIRES location_policy_core
)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
