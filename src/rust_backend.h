#ifndef MGRS_RUST_BACKEND_H
#define MGRS_RUST_BACKEND_H

#include <cstddef>
#include <cstdint>

// Private ABI. Rust owns immutable projection state. Callers own all buffers;
// inputs must remain immutable and outputs exclusive for the entire call.
// Errors/warnings use the historical GEOTRANS status bits.
enum : std::uint32_t {
    MGRS_LAT_ERROR = 1, MGRS_LON_ERROR = 2, MGRS_STRING_ERROR = 4,
    MGRS_PRECISION_ERROR = 8, MGRS_A_ERROR = 0x10,
    MGRS_INV_F_ERROR = 0x20, MGRS_EASTING_ERROR = 0x40,
    MGRS_NORTHING_ERROR = 0x80, MGRS_ZONE_ERROR = 0x100,
    MGRS_HEMISPHERE_ERROR = 0x200, MGRS_LAT_WARNING = 0x400,
    MGRS_LAYOUT_ERROR = 0x1000, MGRS_PANIC = 0x8000,
};

extern "C" {
std::uint32_t mgrs_rust_forward(const double *, std::size_t, bool, std::int32_t,
                                std::uint8_t *, std::size_t *);
std::uint32_t mgrs_rust_inverse_array(const std::uint8_t *, std::size_t,
                                      std::size_t, bool, double *, std::size_t *);
std::uint32_t mgrs_rust_inverse(const std::uint8_t *, std::size_t, double *, double *);
// UTF-8 WKT, no terminator: reports required length and writes only if capacity
// suffices. A null target with zero capacity may be used to query the size.
std::uint32_t mgrs_rust_to_wkt(const std::uint8_t *, std::size_t, std::uint8_t *,
                             std::size_t, std::size_t *);
// Same buffer contract, producing GeoJSON geometry text.
std::uint32_t mgrs_rust_to_geojson(const std::uint8_t *, std::size_t, std::uint8_t *,
                                 std::size_t, std::size_t *);
std::uint32_t mgrs_rust_to_utm(const std::uint8_t *, std::size_t, std::int32_t *,
                             std::uint8_t *, double *, double *);
std::uint32_t mgrs_rust_from_utm(std::int64_t, std::uint8_t, double, double,
                               std::int32_t, std::uint8_t *);
}
#endif
