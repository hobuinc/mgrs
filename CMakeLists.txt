cmake_minimum_required(VERSION 3.20...4.4)
project(mgrs LANGUAGES C CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)
find_package(Threads REQUIRED)

add_library(mgrs_core STATIC
    libmgrs/batch.c
    libmgrs/mgrs.c
    libmgrs/utm.c
    libmgrs/ups.c
    libmgrs/tranmerc.c
    libmgrs/polarst.c
)
target_include_directories(mgrs_core PUBLIC libmgrs)
target_compile_definitions(mgrs_core PUBLIC MGRS_STATIC)
set_target_properties(mgrs_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    C_VISIBILITY_PRESET hidden
)
if(NOT MSVC)
    target_link_libraries(mgrs_core PUBLIC m)
endif()

# Keep the same optimization policy for the C kernels in baseline comparisons;
# pybind11's optional LTO/stripping flags are deliberately disabled.
pybind11_add_module(_native MODULE NO_EXTRAS src/bindings.cpp)
target_compile_features(_native PRIVATE cxx_std_17)
target_link_libraries(_native PRIVATE mgrs_core Threads::Threads)
install(TARGETS _native LIBRARY DESTINATION mgrs RUNTIME DESTINATION mgrs)
