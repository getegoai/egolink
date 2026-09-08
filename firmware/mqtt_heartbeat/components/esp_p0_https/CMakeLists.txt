idf_component_register(SRCS "esp_p0_https.c" INCLUDE_DIRS "include"
    REQUIRES esp_http_client tcp_transport mbedtls esp_timer p0_delivery_runtime sim7670_gnss)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
