cmake_minimum_required(VERSION 3.14)
project(pfun-cma-engine-c VERSION 0.1.0 LANGUAGES C)

# # #
# LLVM configuration
# # #
find_package(LLVM REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

include_directories(${LLVM_INCLUDE_DIRS})
separate_arguments(LLVM_DEFINITIONS_LIST NATIVE_COMMAND ${LLVM_DEFINITIONS})
add_definitions(${LLVM_DEFINITIONS_LIST})

# # #
# Other project settings
# # #

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(SOURCES src/pfun_cma_engine.c)
set(HEADERS src/pfun_cma_engine.h)
set(INCLUDE_DIRS src)

# # #
# build targets
# # #

add_library(pfun_cma_engine_shared SHARED ${SOURCES})
target_include_directories(pfun_cma_engine_shared PUBLIC ${INCLUDE_DIRS})
target_link_libraries(pfun_cma_engine_shared PRIVATE m)
target_compile_options(pfun_cma_engine_shared PRIVATE -Wall -Wextra -O2)
set_target_properties(pfun_cma_engine_shared PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/pfun_cma_engine"
    OUTPUT_NAME "pfun_cma_engine"
)

add_library(pfun_cma_engine_static STATIC ${SOURCES})
target_include_directories(pfun_cma_engine_static PUBLIC ${INCLUDE_DIRS})
target_compile_options(pfun_cma_engine_static PRIVATE -Wall -Wextra -O2)
set_target_properties(pfun_cma_engine_static PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/pfun_cma_engine"
    OUTPUT_NAME "pfun_cma_engine"
)


# # #
# Linking with LLVM
# # #

# Find the libraries that correspond to the LLVM components
# that we wish to use
llvm_map_components_to_libnames(llvm_libs support core irreader)

# Link against LLVM libraries
target_link_libraries(pfun_cma_engine_shared ${llvm_libs})
target_link_libraries(pfun_cma_engine_static ${llvm_libs})
