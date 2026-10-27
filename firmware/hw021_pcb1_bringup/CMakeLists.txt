cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../mqtt_heartbeat/components/ego_state_engine"
    "${CMAKE_CURRENT_LIST_DIR}/../mqtt_heartbeat/components/sim7670_cellular_call"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(hw021_pcb1_bringup)
