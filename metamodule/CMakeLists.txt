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

file(READ "${CMAKE_CURRENT_LIST_DIR}/plugin.json" _plugin_json)
string(JSON _plugin_version GET "${_plugin_json}" "version")
string(REGEX MATCH "^([0-9]+)\\.([0-9]+)\\.([0-9]+)$" _ "${_plugin_version}")
math(EXPR _patch "${CMAKE_MATCH_3} + 1")
set(_plugin_version "${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${_patch}")
string(REPLACE "\"version\": \"${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.${CMAKE_MATCH_3}\""
               "\"version\": \"${_plugin_version}\""
               _plugin_json_new "${_plugin_json}")
file(WRITE "${CMAKE_CURRENT_LIST_DIR}/plugin.json" "${_plugin_json_new}")
message("Plugin version: ${_plugin_version}")

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
        PLUGIN_NAME SchlappiEngineering
        PLUGIN_JSON ${CMAKE_CURRENT_LIST_DIR}/plugin.json
        SOURCE_ASSETS ${CMAKE_CURRENT_LIST_DIR}/assets
        DESTINATION ${INSTALL_DIR}
)

# Rename output file to include version — internal archive dir stays SchlappiEngineering/ to match slug
add_custom_command(TARGET plugin POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E rename
                ${INSTALL_DIR}/SchlappiEngineering.mmplugin
                ${INSTALL_DIR}/SchlappiEngineering-v${_plugin_version}.mmplugin
        COMMENT "Versioning plugin: SchlappiEngineering-v${_plugin_version}.mmplugin"
        VERBATIM
)
