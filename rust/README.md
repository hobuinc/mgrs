# MGRS for Rust

A native Rust translation of the WGS84 MGRS, UTM, UPS, Transverse Mercator and Polar Stereographic algorithms in this repository's GEOTRANS 3.10 backend. No C/C++, FFI, Python runtime, or native runtime dependency is required. The same Rust engine builds to WebAssembly for the [TypeScript package](../typescript/README.md).

The crate is `mgrs-geotrans`; its Rust library name is `mgrs`. GitHub releases include a `mgrs-geotrans-<version>.crate` source archive. Extract it with `tar -xzf mgrs-geotrans-<version>.crate`, then add a path dependency pointing to the extracted directory. The release workflow does not publish to crates.io.

To use this checkout instead, add a path dependency:

```toml
[dependencies]
mgrs-geotrans = { path = "/path/to/mgrs/rust" }
```

```rust
use mgrs::MGRS;

fn main() -> Result<(), mgrs::Error> {
    let m = MGRS::new();
    let code = m.to_mgrs(42.0, -93.0, true, 5)?;
    assert_eq!(code.value, "15TWG0000049776");
    let point = m.to_lat_lon(&code.value, true)?;
    assert_eq!(format!("{:.5}, {:.5}", point.value.0, point.value.1),
               "42.00000, -92.99999");
    Ok(())
}
```

## Python API correspondence

Rust uses snake_case and explicit parameters in place of Python defaults. `Mgrs` and `MGRS` name the same type. All conversion methods borrow `&self`.

| Python | Rust | Successful `Conversion.value` |
| --- | --- | --- |
| `toMGRS(lat, lon, inDegrees=True, MGRSPrecision=5)` | `to_mgrs(lat, lon, true, 5)` | `String` |
| `toLatLon(code, inDegrees=True)` | `to_lat_lon(code, true)` | `(f64, f64)` latitude, longitude |
| `toWKT(code)` | `to_wkt(code)` | `String` WKT polygon, longitude latitude |
| `toGeoJSON(code)` | `to_geojson(code)` | `String` GeoJSON geometry text |
| `MGRSToUTM(code)` | `mgrs_to_utm(code)` | `Utm { zone, hemisphere, easting, northing }` |
| `UTMToMGRS(zone, hemisphere, easting, northing, MGRSPrecision=5)` | `utm_to_mgrs(zone, hemisphere, easting, northing, 5)` | `String` |
| `toMGRSArray(points, inDegrees=True, MGRSPrecision=5)` | `to_mgrs_array(points, true, 5)` | `Vec<u8>` |
| `toLatLonArray(codes, inDegrees=True, width=15)` | `to_lat_lon_array(codes, true, 15)` | `Vec<f64>` |
| `ddtodms(dd)` | `ddtodms(dd)` | `Result<(f64, f64, f64)>` directly |
| `dmstodd(dms)` | `dmstodd(dms)` | `Result<f64>` directly |

Use `false` for radians. Precision is an integer from 0 through 5: cell widths are 100 km, 10 km, 1 km, 100 m, 10 m, and 1 m. Coordinates must be finite, latitude within ±90°, and longitude between −180° and 360° (equivalent limits in radians). UTM uses zone 1–60 and hemisphere `'N'` or `'S'`; `mgrs_to_utm` can reject UPS references outside the supported UTM latitude range. WGS84 is the only supported ellipsoid, matching the Python public interface.

**Inverse conversions return the center of the grid cell**, including `mgrs_to_utm`. At precision 5 this adds 0.5 m to both projected grid axes; at precision 0 it adds 50 km. Forward conversions truncate to the containing cell. Norway, Svalbard, polar and latitude-band boundary behavior follows GEOTRANS 3.10. Inverse floating-point values are compared to Python within 1e-9 degrees, not promised bit-identical across native and WebAssembly math implementations.

`to_lat_lon`, `to_wkt`, `to_geojson` and `mgrs_to_utm` accept strings or byte slices. They remove leading, trailing and internal **ASCII whitespace**, accept lowercase letters, and reject non-ASCII characters, trailing junk, invalid layouts and embedded NUL bytes. Only trailing NUL padding in batch records is accepted.

`ddtodms(32.328414)` returns approximately `(32.0, 19.0, 42.2904)`. For negative coordinates, only the first nonzero component carries the sign. `dmstodd("321942.29N")` returns approximately `32.328414`; `dmstodd("671328.35W")` returns approximately `-67.224542`. Compact DMS supports N/S/E/W suffixes or a leading sign; arbitrary formatted degree/minute/second text is not supported.

## Cell polygons

```rust
fn main() -> Result<(), mgrs::Error> {
let m = mgrs::MGRS::new();
let polygon = m.to_wkt("15TWG0000049776")?.value;
assert!(polygon.starts_with("POLYGON (("));
let geometry = m.to_geojson("15TWG0000049776")?.value;
assert!(geometry.starts_with("{\"type\":\"Polygon\""));
Ok(())
}
```

`to_wkt` returns the full UTM/UPS square at the ID's precision (100 km through 1 m), in WGS84 **longitude latitude degrees**, without an embedded SRID. It preserves the existing inverse decoder's validation and `Conversion.warning`. The footprint is not clipped to zone or latitude-band limits. The closed counterclockwise ring samples curved grid edges adaptively, targeting 0.1 m midpoint error, and writes coordinates to 12 decimal places. It is an approximation; vertex count varies with cell size and location.

Antimeridian longitudes are unwrapped and may exceed ±180° to keep one continuous polygon. Consumers requiring normalized longitudes should split the polygon at the antimeridian instead of wrapping individual vertices. At a pole, two vertices with different longitudes at ±90° close the cell's wedge. See the [Python geometry documentation](../README.rst#cell-polygons) for the shared conventions.

`to_geojson` returns GeoJSON geometry text without adding a serialization dependency. It shares WKT's full-cell geometry, precision, edge sampling and warnings. Antimeridian crossings are cut into a `MultiPolygon` with longitudes in [-180, 180]; other cells produce a `Polygon`. Rings are closed and counterclockwise, with WGS84 longitude/latitude coordinates. Python and TypeScript decode this text using their built-in JSON facilities and return plain geometry mappings/objects. Python's mapping is suitable as a `__geo_interface__` value.

## Arrays and ownership

```rust
fn main() -> Result<(), mgrs::Error> {
let m = mgrs::MGRS::new();
let points = [42.0, -93.0, 90.0, 0.0];
let codes = m.to_mgrs_array(&points, true, 5)?.value;
assert_eq!(codes.len(), 2 * mgrs::WIDTH);
let decoded = m.to_lat_lon_array(&codes, true, mgrs::WIDTH)?.value;
assert_eq!(decoded.len(), 4);
Ok(())
}
```

Inputs are flat, contiguous borrowed slices: `[latitude, longitude, …]` or fixed-width ASCII records. Forward output always uses **15 bytes per record**, NUL-padded on the right. Inverse width must be 1–15; length must be divisible by width. Empty arrays are supported. Inputs are never modified or retained; outputs own their storage. Rust's type system excludes wrong element types, misalignment, byte order reinterpretation and noncontiguous views. Use a slice of a larger allocation for a contiguous view.

All conversions return `Result<Conversion<T>, Error>`. `Error.code` retains Python's backend status bits; `Error.row` is the zero-based first failing batch row. A failure returns no partial output. Latitude-band warnings preserve coordinates in `Conversion.value` and appear in `Conversion.warning`; batch warnings identify the first affected row. Check this field if warnings should be treated as errors.

`to_mgrs_array_into` and `to_lat_lon_array_into` also accept a final mutable output slice of the exact required size. These allocation-free variants support the Python binding: on error, they can leave partial writes in that slice, which the caller must discard. The Python extension uses the private `mgrs-python` static-library crate and retains its pybind11 interface; the public `mgrs-geotrans` crate remains safe Rust without an FFI dependency.

```rust
fn main() -> Result<(), mgrs::Error> {
let result = mgrs::MGRS::new().to_lat_lon("50TMK5045027900", true)?;
assert!(result.warning.is_some());
Ok(())
}
```

Instances are immutable and `Send + Sync`. Share an `Arc<MGRS>` or create independent instances for concurrent work; there is no process-global projection lock. Python's deprecated `RTreeError`, `ctypes` symbols, buffer-protocol internals and wheel machinery have no Rust equivalents.

## Build, test, document and benchmark

Rust 1.85 or later is required. CI checks that minimum version and runs tests, linting, package verification and performance smoke tests with Rust 1.90.0 on Linux, macOS and Windows. From the repository root:

```sh
cargo test --workspace --all-features --locked
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo doc --no-deps --open
cargo run --release --example benchmark -- --points 1000000 --repeats 5
```

See [test coverage and oracle generation](tests/fixtures/README.md) and [performance paths](../benchmarks/rust-typescript.md) for fixed CSV workloads, Python equivalence checks, baseline comparisons and browser measurements. Ordinary tests have no timing thresholds. `cargo package -p mgrs-geotrans` packages the Rust sources, tests and fixtures independently of Python/C++.

See [NOTICE](NOTICE) for GEOTRANS provenance and [LICENSE](LICENSE) for the repository license.
