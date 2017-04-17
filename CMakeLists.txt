########################################################################
# Project setup
########################################################################
cmake_minimum_required(VERSION 2.8.9)
project(PothosLiquidDSP CXX)

########################################################################
# Pothos library
########################################################################
find_package(Pothos "0.4.0" CONFIG REQUIRED)

########################################################################
# Find liquid DSP
########################################################################
list(APPEND CMAKE_MODULE_PATH ${PROJECT_SOURCE_DIR})
find_package(LIQUIDDSP REQUIRED)

message(STATUS "LIQUIDDSP_INCLUDE_DIRS: ${LIQUIDDSP_INCLUDE_DIRS}")
message(STATUS "LIQUIDDSP_LIBRARIES: ${LIQUIDDSP_LIBRARIES}")

########################################################################
# Find the python interpreter
########################################################################
find_package(PythonInterp)
if (NOT ${PYTHONINTERP_FOUND})
    message(FATAL_ERROR "Cant find PYTHON_EXECUTABLE")
endif()

message(STATUS "PYTHON_EXECUTABLE: ${PYTHON_EXECUTABLE}")

########################################################################
# Documentation blubs
########################################################################
set(LIQUID_SITE_JSON "${CMAKE_BINARY_DIR}/site.json")
if (NOT EXISTS "${LIQUID_SITE_JSON}")
    file(DOWNLOAD "http://liquidsdr.org/site.json" "${LIQUID_SITE_JSON}")
endif()

########################################################################
# Resources
########################################################################
set(LIQUID_BLOCKS_GEN_PY "${PROJECT_SOURCE_DIR}/LiquidBlocksGen.py")
file(GLOB BLOCKS_YAML "${PROJECT_SOURCE_DIR}/blocks/*.yaml")
file(GLOB BLOCKS_TMPL "${PROJECT_SOURCE_DIR}/tmpl/*.tmpl.*")

########################################################################
# Preprocess the header
########################################################################
set(LIQUID_H_SOURCE "${LIQUIDDSP_INCLUDE_DIRS}/liquid/liquid.h")
set(LIQUID_H_PROCESSED "${CMAKE_BINARY_DIR}/liquid.h")
add_custom_command(
    OUTPUT "${LIQUID_H_PROCESSED}"
    DEPENDS "${LIQUID_H_SOURCE}"
    COMMAND ${CMAKE_CXX_COMPILER}
        -E #preprocessor
        -CC #leave comments
        -P #no line markers
        "${LIQUID_H_SOURCE}" > "${LIQUID_H_PROCESSED}")

########################################################################
# wrap enums
########################################################################
set(ENUMS_OUTPUT "${CMAKE_BINARY_DIR}/enums.cpp")
add_custom_command(
    OUTPUT "${ENUMS_OUTPUT}"
    DEPENDS "${LIQUID_H_PROCESSED}"
    DEPENDS "${LIQUID_BLOCKS_GEN_PY}"
    DEPENDS "${BLOCKS_TMPL}"
    COMMAND ${PYTHON_EXECUTABLE} -B "${LIQUID_BLOCKS_GEN_PY}" "${LIQUID_H_PROCESSED}" "ENUMS" "${ENUMS_OUTPUT}")
list(APPEND BLOCK_SOURCES "${ENUMS_OUTPUT}")

########################################################################
# build rules for the blocks
########################################################################
foreach(block_yaml ${BLOCKS_YAML})
    get_filename_component(name "${block_yaml}" NAME_WE)
    set(OUTPUT_FILE "${CMAKE_BINARY_DIR}/${name}.cpp")
    add_custom_command(
        OUTPUT "${OUTPUT_FILE}"
        DEPENDS "${LIQUID_H_PROCESSED}"
        DEPENDS "${LIQUID_BLOCKS_GEN_PY}"
        DEPENDS "${BLOCKS_TMPL}"
        DEPENDS "${block_yaml}"
        COMMAND ${PYTHON_EXECUTABLE} -B "${LIQUID_BLOCKS_GEN_PY}" "${LIQUID_H_PROCESSED}" "${block_yaml}" "${OUTPUT_FILE}")
    list(APPEND BLOCK_SOURCES "${OUTPUT_FILE}")
endforeach(block_yaml)

########################################################################
# Build the module
########################################################################
include_directories(${LIQUIDDSP_INCLUDE_DIRS})

POTHOS_MODULE_UTIL(
    TARGET LiquidBlocks
    SOURCES ${BLOCK_SOURCES}
    DESTINATION liquid
    LIBRARIES ${LIQUIDDSP_LIBRARIES}
)
