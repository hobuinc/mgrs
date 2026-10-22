cmake_minimum_required(VERSION 3.20...4.4)
project(mgrs LANGUAGES C CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)
find_package(Threads REQUIRED)

add_subdirectory(libmgrs)

# Keep the same optimization policy for the kernels in baseline comparisons;
# pybind11's optional LTO/stripping flags are deliberately disabled.
pybind11_add_module(_native MODULE NO_EXTRAS src/bindings.cpp)
target_compile_features(_native PRIVATE cxx_std_17)
target_link_libraries(_native PRIVATE mgrs_core Threads::Threads)
install(TARGETS _native LIBRARY DESTINATION mgrs RUNTIME DESTINATION mgrs)
