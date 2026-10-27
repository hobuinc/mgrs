# Cargo owns the Rust build. Keep its artifacts inside this CMake build tree
# so parallel wheel builds cannot reuse an archive for a different target.
find_program(CARGO_EXECUTABLE cargo REQUIRED)
find_program(RUSTC_EXECUTABLE rustc REQUIRED)
execute_process(COMMAND "${RUSTC_EXECUTABLE}" -vV
    OUTPUT_VARIABLE rust_version COMMAND_ERROR_IS_FATAL ANY)
string(REGEX MATCH "host: ([^\n\r]+)" _ "${rust_version}")
set(MGRS_RUST_TARGET "${CMAKE_MATCH_1}" CACHE STRING "Rust target triple (install with rustup target add)")

# CMake's wheel architecture can differ from the host compiler architecture.
if(APPLE AND CMAKE_OSX_ARCHITECTURES)
    if(CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
        set(MGRS_RUST_TARGET aarch64-apple-darwin)
    elseif(CMAKE_OSX_ARCHITECTURES STREQUAL "x86_64")
        set(MGRS_RUST_TARGET x86_64-apple-darwin)
    else()
        message(FATAL_ERROR "Build separate arm64 and x86_64 wheels; universal2 is not supported")
    endif()
elseif(MSVC)
    if(CMAKE_CXX_COMPILER_ARCHITECTURE_ID STREQUAL "ARM64" OR CMAKE_GENERATOR_PLATFORM STREQUAL "ARM64")
        set(MGRS_RUST_TARGET aarch64-pc-windows-msvc)
    elseif(CMAKE_SIZEOF_VOID_P EQUAL 4)
        set(MGRS_RUST_TARGET i686-pc-windows-msvc)
    else()
        set(MGRS_RUST_TARGET x86_64-pc-windows-msvc)
    endif()
endif()
message(STATUS "Rust conversion backend: ${MGRS_RUST_TARGET}")

set(cargo_target_dir "${CMAKE_CURRENT_BINARY_DIR}/cargo")
if(MSVC)
    set(rust_archive "${cargo_target_dir}/${MGRS_RUST_TARGET}/release/mgrs_python.lib")
else()
    set(rust_archive "${cargo_target_dir}/${MGRS_RUST_TARGET}/release/libmgrs_python.a")
endif()
file(GLOB_RECURSE rust_sources CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/rust/*.rs" "${PROJECT_SOURCE_DIR}/rust/*/Cargo.toml")
add_custom_command(OUTPUT "${rust_archive}"
    COMMAND "${CARGO_EXECUTABLE}" rustc --manifest-path "${PROJECT_SOURCE_DIR}/Cargo.toml"
        --package mgrs-python --release --locked --target "${MGRS_RUST_TARGET}"
        --target-dir "${cargo_target_dir}" -- -Crelocation-model=pic
    DEPENDS ${rust_sources} "${PROJECT_SOURCE_DIR}/Cargo.toml"
        "${PROJECT_SOURCE_DIR}/Cargo.lock" "${PROJECT_SOURCE_DIR}/rust/Cargo.toml"
    WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}"
    COMMENT "Building the Rust GEOTRANS 3.10 backend" VERBATIM)
add_custom_target(mgrs_rust_build DEPENDS "${rust_archive}")
add_library(mgrs_rust STATIC IMPORTED)
set_target_properties(mgrs_rust PROPERTIES IMPORTED_LOCATION "${rust_archive}")
add_dependencies(mgrs_rust mgrs_rust_build)
if(MSVC)
    set_property(TARGET mgrs_rust PROPERTY INTERFACE_LINK_LIBRARIES
        "ws2_32;userenv;bcrypt;ntdll;advapi32")
elseif(UNIX)
    set_property(TARGET mgrs_rust PROPERTY INTERFACE_LINK_LIBRARIES "${CMAKE_DL_LIBS};m")
    if(NOT APPLE)
        set_property(TARGET mgrs_rust APPEND PROPERTY INTERFACE_LINK_LIBRARIES "rt;util")
    endif()
endif()
