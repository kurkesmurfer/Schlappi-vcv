cmake_minimum_required(VERSION 3.22)

if(NOT "${METAMODULE_SDK_DIR}" STREQUAL "")
    message("METAMODULE_SDK_DIR set by CMake variable ${METAMODULE_SDK_DIR}")
elseif(DEFINED ENV{METAMODULE_SDK_DIR})
    set(METAMODULE_SDK_DIR "$ENV{METAMODULE_SDK_DIR}")
    message("METAMODULE_SDK_DIR set by environment variable ${METAMODULE_SDK_DIR}")
else()
    set(METAMODULE_SDK_DIR "${CMAKE_CURRENT_LIST_DIR}/../metamodule-plugin-sdk")
    message("METAMODULE_SDK_DIR set to default: ${METAMODULE_SDK_DIR}")
endif()

if(NOT DEFINED INSTALL_DIR)
    set(INSTALL_DIR ${CMAKE_CURRENT_LIST_DIR}/metamodule-plugins)
endif()

include(${METAMODULE_SDK_DIR}/plugin.cmake)

project(SchlappiEngineeringMetaModulePlugin
        VERSION 0.1
        DESCRIPTION "SchlappiEngineering Plugin for Metamodule"
        LANGUAGES   C CXX ASM
)

add_library(schlappiengineering STATIC)

set (SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/../src)

target_sources(schlappiengineering
        PRIVATE
        ${SOURCE_DIR}/btfld.cpp
        ${SOURCE_DIR}/btmx.cpp
        ${SOURCE_DIR}/plugin.cpp
        ${SOURCE_DIR}/nibbler.cpp
        ${SOURCE_DIR}/plugin.hpp
)

target_include_directories(schlappiengineering
        PRIVATE
        ${SOURCE_DIR}
)

set_property(TARGET schlappiengineering PROPERTY CXX_STANDARD 20)

create_plugin(
        SOURCE_LIB schlappiengineering
        PLUGIN_NAME schlappiengineering
        PLUGIN_JSON ${CMAKE_CURRENT_LIST_DIR}/../plugin.json
        SOURCE_ASSETS ${CMAKE_CURRENT_LIST_DIR}/assets
        DESTINATION ${INSTALL_DIR}
)
