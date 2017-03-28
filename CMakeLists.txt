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
# Build the module
########################################################################
include_directories(${LIQUIDDSP_INCLUDE_DIRS})

POTHOS_MODULE_UTIL(
    TARGET LiquidBlocks
    SOURCES
        FOO
    DESTINATION liquid
    LIBRARIES ${LIQUIDDSP_LIBRARIES}
    ENABLE_DOCS
)
