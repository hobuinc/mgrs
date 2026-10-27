// Rust translation of NGA GEOTRANS 3.10 MGRS.cpp, WGS84 branch.
// Includes the Python adapter's complete-input validation and formatting fix.
use crate::projection::{Projection, EPS, RAD};
use crate::{Conversion, Error, Result, Utm, LATITUDE, STRING};
use std::f64::consts::PI;

const TOL: f64 = 4.99e-4;
const BANDS: &[u8; 20] = b"CDEFGHJKLMNPQRSTUVWX";
const MIN_NORTH: [f64; 20] = [
    1100000., 2000000., 2800000., 3700000., 4600000., 5500000., 6400000., 7300000., 8200000.,
    9100000., 0., 800000., 1700000., 2600000., 3500000., 4400000., 5300000., 6200000., 7000000.,
    7900000.,
];
const NORTH_OFFSET: [f64; 20] = [
    0., 2000000., 2000000., 2000000., 4000000., 4000000., 6000000., 6000000., 8000000., 8000000.,
    0., 0., 0., 2000000., 2000000., 4000000., 4000000., 6000000., 6000000., 6000000.,
];
// Low/high column, high row, false easting/northing for A, B, Y, Z.
const UPS: [(u8, u8, u8, f64, f64); 4] = [
    (b'J', b'Z', b'Z', 800000., 800000.),
    (b'A', b'R', b'Z', 2000000., 800000.),
    (b'J', b'Z', b'P', 800000., 1300000.),
    (b'A', b'J', b'P', 2000000., 1300000.),
];

pub(crate) fn scale(precision: i32) -> f64 {
    [100000., 10000., 1000., 100., 10., 1.][precision as usize]
}
pub(crate) fn non_polar(lat: f64) -> bool {
    (-80.0 * RAD - EPS..84.0 * RAD + EPS).contains(&lat)
}

pub(crate) struct Code {
    pub bytes: [u8; 15],
    pub len: usize,
}
impl Code {
    pub fn string(self) -> String {
        String::from_utf8(self.bytes[..self.len].to_vec()).expect("ASCII grid code")
    }
}

fn format(zone: i32, letters: [u8; 3], east: f64, north: f64, precision: i32) -> Result<Code> {
    if !letters.iter().all(u8::is_ascii_uppercase) {
        return Err(Error::new(STRING));
    }
    let mut code = Code {
        bytes: [0; 15],
        len: 0,
    };
    if zone != 0 {
        code.bytes[0] = b'0' + (zone / 10) as u8;
        code.bytes[1] = b'0' + (zone % 10) as u8;
        code.len = 2;
    }
    code.bytes[code.len..code.len + 3].copy_from_slice(&letters);
    code.len += 3;
    let p = precision as usize;
    for (offset, value) in [(0, east), (p, north)] {
        let mut reduced = value % 100000.0;
        if reduced >= 99999.5 {
            reduced = 99999.0;
        }
        let mut number = ((reduced + TOL) / scale(precision)) as i64;
        for j in (0..p).rev() {
            code.bytes[code.len + offset + j] = b'0' + (number % 10) as u8;
            number /= 10;
        }
    }
    code.len += 2 * p;
    Ok(code)
}

pub(crate) struct Parsed {
    zone: i32,
    letters: [u8; 3],
    east: f64,
    north: f64,
    precision: i32,
}
pub(crate) fn parse(input: &[u8]) -> Result<Parsed> {
    let mut text = [0u8; 15];
    let mut n = 0;
    for &ch in input {
        if matches!(ch, b' ' | b'\t' | b'\n' | b'\r' | 11 | 12) {
            continue;
        }
        if !ch.is_ascii_alphanumeric() || n == 15 {
            return Err(Error::new(STRING));
        }
        text[n] = ch.to_ascii_uppercase();
        n += 1;
    }
    let text = &text[..n];
    let mut i = 0;
    let mut zone = 0;
    while i < n && text[i].is_ascii_digit() {
        if i == 2 {
            return Err(Error::new(STRING));
        }
        zone = zone * 10 + (text[i] - b'0') as i32;
        i += 1;
    }
    if i > 2 || (i > 0 && !(1..=60).contains(&zone)) || n < i + 3 {
        return Err(Error::new(STRING));
    }
    let letters: [u8; 3] = text[i..i + 3].try_into().unwrap();
    i += 3;
    if !letters
        .iter()
        .all(|c| c.is_ascii_uppercase() && *c != b'I' && *c != b'O')
    {
        return Err(Error::new(STRING));
    }
    let digits = &text[i..];
    if digits.len() > 10 || digits.len() % 2 != 0 || !digits.iter().all(u8::is_ascii_digit) {
        return Err(Error::new(STRING));
    }
    let precision = (digits.len() / 2) as i32;
    let number = |s: &[u8]| s.iter().fold(0u32, |a, c| a * 10 + (c - b'0') as u32) as f64;
    let multiplier = scale(precision);
    let east = number(&digits[..precision as usize]) * multiplier + multiplier * 0.5;
    let north = number(&digits[precision as usize..]) * multiplier + multiplier * 0.5;
    Ok(Parsed {
        zone,
        letters,
        east,
        north,
        precision,
    })
}

fn grid_values(zone: i32) -> (u8, u8, f64) {
    let (low, high) = match zone % 3 {
        1 => (b'A', b'H'),
        2 => (b'J', b'R'),
        _ => (b'S', b'Z'),
    };
    (low, high, if zone % 2 == 0 { 500000. } else { 0. })
}

fn latitude_letter(lat: f64) -> Result<u8> {
    if (72.0 * RAD..84.5 * RAD).contains(&lat) {
        return Ok(b'X');
    }
    if lat > -80.5 * RAD && lat < 72.0 * RAD {
        let index = (((lat + 80.0 * RAD) / (8.0 * RAD) + 1e-12) as i32).max(0) as usize;
        return BANDS
            .get(index)
            .copied()
            .ok_or_else(|| Error::new(LATITUDE));
    }
    Err(Error::new(LATITUDE))
}

pub(crate) fn forward(proj: &Projection, lat: f64, lon: f64, precision: i32) -> Result<Code> {
    if non_polar(lat) {
        from_utm(proj, proj.utm_forward(lat, lon, 0)?, lat, lon, precision)
    } else {
        let (hemi, e, n) = proj.ups_forward(lat, lon)?;
        from_ups(hemi, e, n, precision)
    }
}

pub(crate) fn from_utm(
    proj: &Projection,
    mut p: Utm,
    lat: f64,
    lon: f64,
    precision: i32,
) -> Result<Code> {
    let band = latitude_letter(lat)?;
    let pad = TOL / 6378137.0;
    let mut natural = if lon < PI {
        (31.0 + (lon + pad) / (6.0 * RAD)) as i32
    } else {
        ((lon + pad) / (6.0 * RAD) - 29.0) as i32
    };
    if natural > 60 {
        natural = 1;
    }
    if p.zone != natural {
        p = proj.utm_forward(lat, lon, natural)?;
    }
    let override_zone = if band == b'V' && p.zone == 31 && p.easting >= 500000. {
        32
    } else if band == b'X' {
        match (p.zone, p.easting < 500000.) {
            (32, true) => 31,
            (32, false) | (34, true) => 33,
            (34, false) | (36, true) => 35,
            (36, false) => 37,
            _ => 0,
        }
    } else {
        0
    };
    if override_zone != 0 {
        p = proj.utm_forward(lat, lon, override_zone)?;
    }
    let divisor = scale(precision);
    let east = ((p.easting + TOL) / divisor) as i64 as f64 * divisor;
    let mut north = ((p.northing + TOL) / divisor) as i64 as f64 * divisor;
    if lat <= 0.0 && north == 1e7 {
        north = 0.0;
    }
    let (low, _, offset) = grid_values(p.zone);
    let mut grid_north = north;
    while grid_north >= 2000000. {
        grid_north -= 2000000.;
    }
    grid_north += offset;
    if grid_north >= 2000000. {
        grid_north -= 2000000.;
    }
    let mut row = b'A' + (grid_north / 100000.) as u8;
    if row > b'H' {
        row += 1;
    }
    if row > b'N' {
        row += 1;
    }
    let mut column = low as i32 + (east / 100000.) as i32 - 1;
    if low == b'J' && column > b'N' as i32 {
        column += 1;
    }
    format(p.zone, [band, column as u8, row], east, north, precision)
}

pub(crate) fn from_ups(hemi: char, east: f64, north: f64, precision: i32) -> Result<Code> {
    let divisor = scale(precision);
    let east = ((east + TOL) / divisor) as i64 as f64 * divisor;
    let north = ((north + TOL) / divisor) as i64 as f64 * divisor;
    let index = if hemi == 'N' { 2 } else { 0 } + usize::from(east >= 2000000.);
    let band = b"ABYZ"[index];
    let (low, _, _, false_e, false_n) = UPS[index];
    let mut row = b'A' as i32 + ((north - false_n) / 100000.) as i32;
    if row > b'H' as i32 {
        row += 1;
    }
    if row > b'N' as i32 {
        row += 1;
    }
    let mut col = low as i32 + ((east - false_e) / 100000.) as i32;
    if east < 2000000. {
        if col > b'L' as i32 {
            col += 3;
        }
        if col > b'U' as i32 {
            col += 2;
        }
    } else {
        if col > b'C' as i32 {
            col += 2;
        }
        if col > b'H' as i32 {
            col += 1;
        }
        if col > b'L' as i32 {
            col += 3;
        }
    }
    format(0, [band, col as u8, row as u8], east, north, precision)
}

fn in_band(index: usize, latitude: f64, border: f64) -> bool {
    let south = if index == 0 {
        -80.5
    } else {
        -80.0 + index as f64 * 8.0
    } * RAD;
    let north = if index == 19 {
        84.5
    } else {
        -72.0 + index as f64 * 8.0
    } * RAD;
    south - border <= latitude && latitude <= north + border
}

fn to_utm(proj: &Projection, p: &Parsed) -> Result<Conversion<Utm>> {
    let [band, col, row] = p.letters;
    if (band == b'X' && [32, 34, 36].contains(&p.zone))
        || (band == b'V' && p.zone == 31 && col > b'D')
    {
        return Err(Error::new(STRING));
    }
    let (low, high, offset) = grid_values(p.zone);
    if col < low || col > high || row > b'V' {
        return Err(Error::new(STRING));
    }
    let mut east = (col - low + 1) as f64 * 100000.;
    if low == b'J' && col > b'O' {
        east -= 100000.;
    }
    let mut row_north = (row - b'A') as f64 * 100000.;
    if row > b'O' {
        row_north -= 100000.;
    }
    if row > b'I' {
        row_north -= 100000.;
    }
    if row_north >= 2000000. {
        row_north -= 2000000.;
    }
    let index = BANDS
        .iter()
        .position(|x| *x == band)
        .ok_or_else(|| Error::new(STRING))?;
    let mut north = row_north - offset;
    if north < 0.0 {
        north += 2000000.;
    }
    north += NORTH_OFFSET[index];
    if north < MIN_NORTH[index] {
        north += 2000000.;
    }
    let utm = Utm {
        zone: p.zone,
        hemisphere: if band < b'N' { 'S' } else { 'N' },
        easting: east + p.east,
        northing: north + p.north,
    };
    let (latitude, _) = proj.utm_inverse(&utm)?;
    let border = RAD / (100000. / scale(p.precision));
    let warning = if in_band(index, latitude, border) {
        false
    } else if in_band(index.saturating_sub(1), latitude, border)
        || in_band((index + 1).min(19), latitude, border)
    {
        true
    } else {
        return Err(Error::new(STRING));
    };
    Ok(Conversion::new(utm, warning))
}

fn to_ups(p: &Parsed) -> Result<(char, f64, f64)> {
    let [band, col, row] = p.letters;
    let index = b"ABYZ"
        .iter()
        .position(|x| *x == band)
        .ok_or_else(|| Error::new(STRING))?;
    let (low, high, row_high, false_e, false_n) = UPS[index];
    if col < low || col > high || b"DEMNVW".contains(&col) || row > row_high {
        return Err(Error::new(STRING));
    }
    let mut north = (row - b'A') as f64 * 100000. + false_n;
    if row > b'I' {
        north -= 100000.;
    }
    if row > b'O' {
        north -= 100000.;
    }
    let mut east = (col - low) as f64 * 100000. + false_e;
    if low != b'A' {
        if col > b'L' {
            east -= 300000.;
        }
        if col > b'U' {
            east -= 200000.;
        }
    } else {
        if col > b'C' {
            east -= 200000.;
        }
        if col > b'I' {
            east -= 100000.;
        }
        if col > b'L' {
            east -= 300000.;
        }
    }
    Ok((
        if band >= b'Y' { 'N' } else { 'S' },
        east + p.east,
        north + p.north,
    ))
}

pub(crate) fn inverse(proj: &Projection, p: &Parsed) -> Result<Conversion<(f64, f64)>> {
    if p.zone != 0 {
        let result = to_utm(proj, p)?;
        Ok(Conversion {
            value: proj.utm_inverse(&result.value)?,
            warning: result.warning,
        })
    } else {
        let (h, e, n) = to_ups(p)?;
        Ok(Conversion::new(proj.ups_inverse(h, e, n)?, false))
    }
}

pub(crate) fn cell(proj: &Projection, p: &Parsed) -> Result<Conversion<crate::geometry::Cell>> {
    let (hemisphere, easting, northing, warning) = if p.zone != 0 {
        let center = to_utm(proj, p)?;
        let u = center.value;
        (u.hemisphere, u.easting, u.northing, center.warning)
    } else {
        let (h, e, n) = to_ups(p)?;
        proj.ups_inverse(h, e, n)?;
        (h, e, n, None)
    };
    let size = scale(p.precision);
    Ok(Conversion {
        value: crate::geometry::Cell {
            zone: p.zone,
            hemisphere,
            easting: easting - size / 2.0,
            northing: northing - size / 2.0,
            size,
        },
        warning,
    })
}

pub(crate) fn mgrs_to_utm(proj: &Projection, p: &Parsed) -> Result<Conversion<Utm>> {
    if p.zone != 0 {
        to_utm(proj, p)
    } else {
        let (h, e, n) = to_ups(p)?;
        let (lat, lon) = proj.ups_inverse(h, e, n)?;
        Ok(Conversion::new(proj.utm_forward(lat, lon, 0)?, false))
    }
}
