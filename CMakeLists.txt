cmake_minimum_required(VERSION 3.20...4.4)
project(mgrs LANGUAGES CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)
find_package(Threads REQUIRED)

include(cmake/rust.cmake)

# Keep the Python interface unchanged; all projection code is now Rust.
pybind11_add_module(_native MODULE NO_EXTRAS src/bindings.cpp)
target_compile_features(_native PRIVATE cxx_std_17)
target_link_libraries(_native PRIVATE mgrs_rust Threads::Threads)
# Do not export Rust's standard library or private ABI from the Python module.
if(APPLE)
    target_link_options(_native PRIVATE "LINKER:-exported_symbol,_PyInit__native" "LINKER:-dead_strip")
elseif(UNIX)
    target_link_options(_native PRIVATE "LINKER:--exclude-libs,ALL")
endif()
install(TARGETS _native LIBRARY DESTINATION mgrs RUNTIME DESTINATION mgrs)
