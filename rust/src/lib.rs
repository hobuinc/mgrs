//! WGS84 MGRS conversions translated from the bundled NGA GEOTRANS 3.10.
//! Inverse coordinates represent cell centers. No C/C++ code is linked.
//!
//! ```
//! use mgrs::MGRS;
//! let m = MGRS::new();
//! let code = m.to_mgrs(42.0, -93.0, true, 5)?;
//! assert_eq!(code.value, "15TWG0000049776");
//! let point = m.to_lat_lon(&code.value, true)?;
//! assert!((point.value.0 - 42.0).abs() < 0.00001);
//! let polygon = m.to_wkt(&code.value)?;
//! assert!(polygon.value.starts_with("POLYGON (("));
//! let geometry = m.to_geojson(&code.value)?;
//! assert!(geometry.value.starts_with("{\"type\":\"Polygon\""));
//! let codes = m.to_mgrs_array(&[42.0, -93.0, 90.0, 0.0], true, 5)?;
//! assert_eq!(codes.value.len(), 30);
//! assert_eq!(m.to_lat_lon_array(&codes.value, true, 15)?.value.len(), 4);
//! # Ok::<(), mgrs::Error>(())
//! ```
#![forbid(unsafe_code)]
mod geometry;
mod grid;
mod projection;
#[cfg(feature = "wasm")]
mod wasm;

use std::f64::consts::PI;
use std::fmt;

pub const LATITUDE: u32 = 0x0001;
pub const LONGITUDE: u32 = 0x0002;
pub const STRING: u32 = 0x0004;
pub const PRECISION: u32 = 0x0008;
pub const EASTING: u32 = 0x0040;
pub const NORTHING: u32 = 0x0080;
pub const ZONE: u32 = 0x0100;
pub const HEMISPHERE: u32 = 0x0200;
pub const LAYOUT: u32 = 0x1000;
pub const WIDTH: usize = 15;
pub type Result<T> = std::result::Result<T, Error>;

/// Conversion error with the same status bits as the Python backend.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    pub code: u32,
    pub row: Option<usize>,
}
impl Error {
    pub fn new(code: u32) -> Self {
        Self { code, row: None }
    }
    fn at_row(mut self, row: usize) -> Self {
        self.row = Some(row);
        self
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(row) = self.row {
            write!(f, "array conversion failed at row {row}: ")?;
        }
        let mut separator = "";
        for (bit, name) in [
            (LATITUDE, "Latitude Error"),
            (LONGITUDE, "Longitude Error"),
            (STRING, "String Error"),
            (PRECISION, "Precision Error"),
            (EASTING, "Easting Error"),
            (NORTHING, "Northing Error"),
            (ZONE, "Zone Error"),
            (HEMISPHERE, "Hemisphere Error"),
            (LAYOUT, "Layout Error"),
        ] {
            if self.code & bit != 0 {
                write!(f, "{separator}{name}")?;
                separator = " & ";
            }
        }
        Ok(())
    }
}
impl std::error::Error for Error {}
pub type MGRSError = Error;

/// A latitude-band warning preserves the computed value. Batch warnings
/// identify the first affected row, just like the Python API.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Warning {
    pub row: Option<usize>,
}
impl fmt::Display for Warning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Latitude Warning")?;
        if let Some(row) = self.row {
            write!(f, "; first affected row {row}")?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Conversion<T> {
    pub value: T,
    pub warning: Option<Warning>,
}
impl<T> Conversion<T> {
    fn new(value: T, warning: bool) -> Self {
        Self {
            value,
            warning: warning.then_some(Warning { row: None }),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Utm {
    pub zone: i32,
    pub hemisphere: char,
    pub easting: f64,
    pub northing: f64,
}

/// Independent immutable projection state; safely shareable between threads.
#[derive(Debug, Clone, Default)]
pub struct Mgrs {
    projection: projection::Projection,
}
pub type MGRS = Mgrs;

fn precision(value: i32) -> Result<()> {
    if (0..=5).contains(&value) {
        Ok(())
    } else {
        Err(Error::new(PRECISION))
    }
}
fn radians(lat: f64, lon: f64, degrees: bool) -> Result<(f64, f64)> {
    let (lat, lon) = if degrees {
        (lat * PI / 180.0, lon * PI / 180.0)
    } else {
        (lat, lon)
    };
    let mut bits = 0;
    if !(-PI / 2.0..=PI / 2.0).contains(&lat) {
        bits |= LATITUDE;
    }
    if !(-PI..=2.0 * PI).contains(&lon) {
        bits |= LONGITUDE;
    }
    if bits != 0 {
        Err(Error::new(bits))
    } else {
        Ok((lat, lon))
    }
}

impl Mgrs {
    pub fn new() -> Self {
        Self::default()
    }

    /// Convert latitude/longitude to MGRS; Python defaults are `true, 5`.
    pub fn to_mgrs(
        &self,
        latitude: f64,
        longitude: f64,
        in_degrees: bool,
        mgrs_precision: i32,
    ) -> Result<Conversion<String>> {
        precision(mgrs_precision)?;
        let (lat, lon) = radians(latitude, longitude, in_degrees)?;
        Ok(Conversion::new(
            grid::forward(&self.projection, lat, lon, mgrs_precision)?.string(),
            false,
        ))
    }

    /// Accept UTF-8 strings or raw ASCII bytes. Reject embedded NULs and junk.
    pub fn to_lat_lon(
        &self,
        code: impl AsRef<[u8]>,
        in_degrees: bool,
    ) -> Result<Conversion<(f64, f64)>> {
        let mut result = grid::inverse(&self.projection, &grid::parse(code.as_ref())?)?;
        if in_degrees {
            result.value.0 = result.value.0 * 180.0 / PI;
            result.value.1 = result.value.1 * 180.0 / PI;
        }
        Ok(result)
    }

    /// The full grid cell as a WGS84 `POLYGON ((longitude latitude, ...))`.
    /// Precision comes from the ID (100 km through 1 m). The closed,
    /// counterclockwise ring samples curved UTM/UPS edges adaptively, targeting
    /// 0.1 m midpoint error. It is not clipped to zone or latitude-band limits.
    /// Longitudes are unwrapped across the antimeridian and may exceed ±180°;
    /// pole corners have two longitudes to preserve the cell's wedge. WKT has
    /// no embedded SRID. Input validation and warnings match `to_lat_lon`.
    pub fn to_wkt(&self, code: impl AsRef<[u8]>) -> Result<Conversion<String>> {
        let cell = grid::cell(&self.projection, &grid::parse(code.as_ref())?)?;
        Ok(Conversion {
            value: cell.value.wkt(&self.projection)?,
            warning: cell.warning,
        })
    }

    /// The full cell as GeoJSON geometry text, using the same sampled boundary
    /// as `to_wkt`. Returns a Polygon or, across the antimeridian, a MultiPolygon
    /// with longitudes in [-180, 180]. Coordinates are longitude, latitude in
    /// WGS84 degrees. No serialization dependency is required.
    pub fn to_geojson(&self, code: impl AsRef<[u8]>) -> Result<Conversion<String>> {
        let cell = grid::cell(&self.projection, &grid::parse(code.as_ref())?)?;
        Ok(Conversion {
            value: cell.value.geojson(&self.projection)?,
            warning: cell.warning,
        })
    }

    pub fn mgrs_to_utm(&self, code: impl AsRef<[u8]>) -> Result<Conversion<Utm>> {
        grid::mgrs_to_utm(&self.projection, &grid::parse(code.as_ref())?)
    }

    pub fn utm_to_mgrs(
        &self,
        zone: i32,
        hemisphere: char,
        easting: f64,
        northing: f64,
        mgrs_precision: i32,
    ) -> Result<Conversion<String>> {
        precision(mgrs_precision)?;
        let p = Utm {
            zone,
            hemisphere,
            easting,
            northing,
        };
        let (lat, lon) = self.projection.utm_inverse(&p)?;
        let code = if grid::non_polar(lat) {
            grid::from_utm(&self.projection, p, lat, lon, mgrs_precision)?
        } else {
            let (h, e, n) = self.projection.ups_forward(lat, lon)?;
            grid::from_ups(h, e, n, mgrs_precision)?
        };
        Ok(Conversion::new(code.string(), false))
    }

    /// Interleaved latitude/longitude doubles to NUL-padded 15-byte records.
    /// Inputs are borrowed and never mutated. Errors return no partial output.
    pub fn to_mgrs_array(
        &self,
        points: &[f64],
        in_degrees: bool,
        mgrs_precision: i32,
    ) -> Result<Conversion<Vec<u8>>> {
        precision(mgrs_precision)?;
        if points.len() % 2 != 0 {
            return Err(Error::new(LAYOUT));
        }
        let len = (points.len() / 2)
            .checked_mul(WIDTH)
            .ok_or_else(|| Error::new(LAYOUT))?;
        let mut output = vec![0; len];
        let result = self.to_mgrs_array_into(points, in_degrees, mgrs_precision, &mut output)?;
        Ok(Conversion {
            value: output,
            warning: result.warning,
        })
    }

    /// Fill caller-owned 15-byte records. On error, output may be partially
    /// written; bindings must discard it rather than expose partial results.
    pub fn to_mgrs_array_into(
        &self,
        points: &[f64],
        in_degrees: bool,
        mgrs_precision: i32,
        output: &mut [u8],
    ) -> Result<Conversion<()>> {
        precision(mgrs_precision)?;
        if points.len() % 2 != 0 || (points.len() / 2).checked_mul(WIDTH) != Some(output.len()) {
            return Err(Error::new(LAYOUT));
        }
        for (i, p) in points.chunks_exact(2).enumerate() {
            let (lat, lon) = radians(p[0], p[1], in_degrees).map_err(|e| e.at_row(i))?;
            let code = grid::forward(&self.projection, lat, lon, mgrs_precision)
                .map_err(|e| e.at_row(i))?;
            output[i * WIDTH..(i + 1) * WIDTH].copy_from_slice(&code.bytes);
        }
        Ok(Conversion::new((), false))
    }

    /// Fixed-width ASCII byte records to interleaved latitude/longitude doubles.
    pub fn to_lat_lon_array(
        &self,
        codes: &[u8],
        in_degrees: bool,
        width: usize,
    ) -> Result<Conversion<Vec<f64>>> {
        if !(1..=WIDTH).contains(&width) || codes.len() % width != 0 {
            return Err(Error::new(LAYOUT));
        }
        let count = codes.len() / width;
        let capacity = count.checked_mul(2).ok_or_else(|| Error::new(LAYOUT))?;
        let mut output = vec![0.0; capacity];
        let result = self.to_lat_lon_array_into(codes, in_degrees, width, &mut output)?;
        Ok(Conversion {
            value: output,
            warning: result.warning,
        })
    }

    /// Fill caller-owned interleaved doubles. Discard output on error.
    pub fn to_lat_lon_array_into(
        &self,
        codes: &[u8],
        in_degrees: bool,
        width: usize,
        output: &mut [f64],
    ) -> Result<Conversion<()>> {
        if !(1..=WIDTH).contains(&width)
            || codes.len() % width != 0
            || (codes.len() / width).checked_mul(2) != Some(output.len())
        {
            return Err(Error::new(LAYOUT));
        }
        let mut result = Conversion::new((), false);
        for (i, record) in codes.chunks_exact(width).enumerate() {
            let len = record.iter().position(|b| *b == 0).unwrap_or(width);
            if record[len..].iter().any(|b| *b != 0) {
                return Err(Error::new(STRING).at_row(i));
            }
            let point = self
                .to_lat_lon(&record[..len], in_degrees)
                .map_err(|e| e.at_row(i))?;
            if point.warning.is_some() && result.warning.is_none() {
                result.warning = Some(Warning { row: Some(i) });
            }
            output[i * 2..i * 2 + 2].copy_from_slice(&[point.value.0, point.value.1]);
        }
        Ok(result)
    }

    /// Decimal degrees to signed degrees, minutes and seconds, matching Python.
    pub fn ddtodms(&self, dd: f64) -> Result<(f64, f64, f64)> {
        if !dd.is_finite() {
            return Err(Error::new(LATITUDE));
        }
        let total = dd.abs() * 3600.0;
        let mut seconds = total % 60.0;
        let total_minutes = (total / 60.0).floor();
        let mut minutes = total_minutes % 60.0;
        let mut degrees = (total_minutes / 60.0).floor();
        if dd < 0.0 {
            if degrees > 0.0 {
                degrees = -degrees;
            } else if minutes > 0.0 {
                minutes = -minutes;
            } else {
                seconds = -seconds;
            }
        }
        Ok((degrees, minutes, seconds))
    }

    /// Compact DMS such as `321942.29N` or `671328.35W` to decimal degrees.
    pub fn dmstodd(&self, dms: &str) -> Result<f64> {
        if !dms.is_ascii() {
            return Err(Error::new(STRING));
        }
        let upper = dms.trim().to_ascii_uppercase();
        let negative = upper.contains(['W', 'S']) || upper.starts_with('-');
        let number: String = upper.chars().filter(|c| !"WENS+-".contains(*c)).collect();
        let (integer, fraction) = number.split_once('.').unwrap_or((&number, ""));
        if integer.len() < 5
            || !integer.bytes().all(|b| b.is_ascii_digit())
            || !fraction.bytes().all(|b| b.is_ascii_digit())
        {
            return Err(Error::new(STRING));
        }
        let split = integer.len() - 4;
        let d: f64 = integer[..split].parse().map_err(|_| Error::new(STRING))?;
        let m: f64 = integer[split..split + 2]
            .parse()
            .map_err(|_| Error::new(STRING))?;
        let s: f64 = format!("{}.{}", &integer[split + 2..], fraction)
            .parse()
            .map_err(|_| Error::new(STRING))?;
        let result = d + m / 60.0 + s / 3600.0;
        Ok(if negative { -result } else { result })
    }
}
