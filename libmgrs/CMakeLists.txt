# Source provenance and local changes are documented in geotrans3.10/README.rst.
add_library(geotrans310 STATIC
    geotrans3.10/CoordinateSystemParameters/CoordinateSystemParameters.cpp
    geotrans3.10/CoordinateSystemParameters/EllipsoidParameters.cpp
    geotrans3.10/CoordinateSystemParameters/MapProjection5Parameters.cpp
    geotrans3.10/CoordinateSystemParameters/PolarStereographicScaleFactorParameters.cpp
    geotrans3.10/CoordinateSystemParameters/PolarStereographicStandardParallelParameters.cpp
    geotrans3.10/CoordinateSystemParameters/UTMParameters.cpp
    geotrans3.10/CoordinateSystems/mgrs/MGRS.cpp
    geotrans3.10/CoordinateSystems/misc/CoordinateSystem.cpp
    geotrans3.10/CoordinateSystems/polarst/PolarStereographic.cpp
    geotrans3.10/CoordinateSystems/tranmerc/TransverseMercator.cpp
    geotrans3.10/CoordinateSystems/ups/UPS.cpp
    geotrans3.10/CoordinateSystems/utm/UTM.cpp
    geotrans3.10/CoordinateTuples/CoordinateTuple.cpp
    geotrans3.10/CoordinateTuples/GeodeticCoordinates.cpp
    geotrans3.10/CoordinateTuples/MGRSorUSNGCoordinates.cpp
    geotrans3.10/CoordinateTuples/MapProjectionCoordinates.cpp
    geotrans3.10/CoordinateTuples/UPSCoordinates.cpp
    geotrans3.10/CoordinateTuples/UTMCoordinates.cpp
    geotrans3.10/Exception/ErrorMessages.cpp
    geotrans3.10/Exception/WarningMessages.cpp
)
target_include_directories(geotrans310 PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystemParameters
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/mgrs
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/misc
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/polarst
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/tranmerc
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/ups
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateSystems/utm
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/CoordinateTuples
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/Enumerations
    ${CMAKE_CURRENT_SOURCE_DIR}/geotrans3.10/Exception
)
target_compile_features(geotrans310 PRIVATE cxx_std_11)
set_target_properties(geotrans310 PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

add_library(mgrs_core STATIC batch.c mgrs.cpp)
target_include_directories(mgrs_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_definitions(mgrs_core PUBLIC MGRS_STATIC)
target_compile_features(mgrs_core PRIVATE cxx_std_17)
target_link_libraries(mgrs_core PRIVATE geotrans310)
set_target_properties(mgrs_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    C_VISIBILITY_PRESET hidden
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)
if(NOT MSVC)
    target_link_libraries(mgrs_core PUBLIC m)
endif()
