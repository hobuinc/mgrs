// Rust translation of NGA GEOTRANS 3.10 TransverseMercator, UTM, UPS and
// PolarStereographic. See NOTICE and libmgrs/geotrans3.10/SOURCE.json.
// Only WGS84, the Python public API's ellipsoid, is exposed.
use crate::{Error, Result, Utm, EASTING, HEMISPHERE, LATITUDE, LONGITUDE, NORTHING, ZONE};
use std::f64::consts::{FRAC_PI_2, FRAC_PI_4, PI};

pub(crate) const RAD: f64 = PI / 180.0;
pub(crate) const EPS: f64 = 1.75e-7;
const F: f64 = 1.0 / 298.257223563;
const A: f64 = 6378137.0;
#[allow(clippy::excessive_precision)]
const FORWARD: [f64; 6] = [
    8.3773182062446983032e-04,
    7.608527773572489156e-07,
    1.19764550324249210e-09,
    2.4291706803973131e-12,
    5.711818369154105e-15,
    1.47999802705262e-17,
];
#[allow(clippy::excessive_precision)]
const INVERSE: [f64; 6] = [
    -8.3773216405794867707e-04,
    -5.905870152220365181e-08,
    -1.67348266534382493e-10,
    -2.1647981104903862e-13,
    -3.787930968839601e-16,
    -7.23676928796690e-19,
];

#[derive(Clone, Debug)]
pub(crate) struct Projection {
    eccentricity: f64,
    radius: f64,
    polar_a_mc: f64,
    polar_tc: f64,
}

fn atanh(x: f64) -> f64 {
    0.5 * ((1.0 + x) / (1.0 - x)).ln()
}

// Preserve NGA's recurrence and accumulation order instead of substituting
// six independently evaluated transcendental functions.
fn series(x: f64, hyperbolic: bool) -> ([f64; 6], [f64; 6]) {
    let mut c = [0.0; 6];
    let mut s = [0.0; 6];
    if hyperbolic {
        c[0] = x.cosh();
        s[0] = x.sinh();
    } else {
        c[0] = x.cos();
        s[0] = x.sin();
    }
    c[1] = 2.0 * c[0] * c[0] - 1.0;
    s[1] = 2.0 * c[0] * s[0];
    if hyperbolic {
        c[2] = c[0] * c[1] + s[0] * s[1];
    } else {
        c[2] = c[1] * c[0] - s[1] * s[0];
    }
    s[2] = c[1] * s[0] + c[0] * s[1];
    c[3] = 2.0 * c[1] * c[1] - 1.0;
    s[3] = 2.0 * c[1] * s[1];
    if hyperbolic {
        c[4] = c[0] * c[3] + s[0] * s[3];
    } else {
        c[4] = c[3] * c[0] - s[3] * s[0];
    }
    s[4] = c[3] * s[0] + c[0] * s[3];
    c[5] = 2.0 * c[2] * c[2] - 1.0;
    s[5] = 2.0 * c[2] * s[2];
    (c, s)
}

impl Default for Projection {
    fn default() -> Self {
        let eccentricity = (2.0 * F - F * F).sqrt();
        let n = 1.0 / (2.0 * (1.0 / F) - 1.0);
        let n2 = n * n;
        let n4 = n2 * n * n;
        let n6 = n4 * n * n;
        let n8 = n6 * n * n;
        let n10 = n8 * n * n;
        let mut coeff = 0.0;
        coeff += 49.0 * n10 / 65536.0;
        coeff += 25.0 * n8 / 16384.0;
        coeff += n6 / 256.0;
        coeff += n4 / 64.0;
        coeff += n2 / 4.0;
        coeff += 1.0;
        let radius = (coeff / (1.0 + n)) * 0.9996 * A;
        let plus = 1.0 + eccentricity;
        let minus = 1.0 - eccentricity;
        let k90 = (plus.powf(plus) * minus.powf(minus)).sqrt();
        let mut sk: f64 = 0.0;
        let mut next: f64 = -1.0 + 2.0 * 0.994;
        for _ in 0..30 {
            if (next - sk).abs() <= 1e-15 {
                break;
            }
            sk = next;
            next = (2.0
                * 0.994
                * ((1.0 + eccentricity * sk).powf(plus) * (1.0 - eccentricity * sk).powf(minus))
                    .sqrt())
                / k90
                - 1.0;
        }
        let parallel = next.asin();
        let es_sin = eccentricity * parallel.sin();
        let pow = ((1.0 - es_sin) / (1.0 + es_sin)).powf(eccentricity / 2.0);
        Self {
            eccentricity,
            radius,
            polar_a_mc: A * (parallel.cos() / (1.0 - es_sin * es_sin).sqrt()),
            polar_tc: (FRAC_PI_4 - parallel / 2.0).tan() / pow,
        }
    }
}

fn meridian(zone: i32) -> f64 {
    let mut lon = if zone >= 31 {
        (6 * zone - 183) as f64 * RAD
    } else {
        (6 * zone + 177) as f64 * RAD
    };
    if lon > PI {
        lon -= 2.0 * PI;
    }
    lon
}

pub(crate) fn validate_utm(p: &Utm) -> Result<()> {
    let mut bits = 0;
    if !(1..=60).contains(&p.zone) {
        bits |= ZONE;
    }
    if p.hemisphere != 'N' && p.hemisphere != 'S' {
        bits |= HEMISPHERE;
    }
    if !(100000.0..=900000.0).contains(&p.easting) {
        bits |= EASTING;
    }
    if !(0.0..=10000000.0).contains(&p.northing) {
        bits |= NORTHING;
    }
    if bits != 0 {
        Err(Error::new(bits))
    } else {
        Ok(())
    }
}

impl Projection {
    pub fn utm_forward(&self, mut lat: f64, mut lon: f64, override_zone: i32) -> Result<Utm> {
        if !(-80.5 * RAD - EPS..84.5 * RAD + EPS).contains(&lat) {
            return Err(Error::new(LATITUDE));
        }
        if !(-PI - EPS..=2.0 * PI + EPS).contains(&lon) {
            return Err(Error::new(LONGITUDE));
        }
        if lat > -1e-9 && lat < 0.0 {
            lat = 0.0;
        }
        if lon < 0.0 {
            lon += 2.0 * PI;
        }
        let lat_degrees = (lat * 180.0 / PI) as i32;
        let lon_degrees = (lon * 180.0 / PI) as i32;
        let mut zone = if lon < PI {
            (31.0 + ((lon + 1e-10) * 180.0 / PI) / 6.0) as i32
        } else {
            (((lon + 1e-10) * 180.0 / PI) / 6.0 - 29.0) as i32
        };
        if zone > 60 {
            zone = 1;
        }
        if override_zone != 0 {
            if !((zone - override_zone).abs() <= 1
                || (zone == 1 && override_zone == 60)
                || (zone == 60 && override_zone == 1))
            {
                return Err(Error::new(ZONE));
            }
            zone = override_zone;
        } else {
            if lat_degrees > 55 && lat_degrees < 64 {
                if (0..3).contains(&lon_degrees) {
                    zone = 31;
                }
                if (3..12).contains(&lon_degrees) {
                    zone = 32;
                }
            }
            if lat_degrees > 71 {
                if (0..9).contains(&lon_degrees) {
                    zone = 31;
                }
                if (9..21).contains(&lon_degrees) {
                    zone = 33;
                }
                if (21..33).contains(&lon_degrees) {
                    zone = 35;
                }
                if (33..42).contains(&lon_degrees) {
                    zone = 37;
                }
            }
        }
        if lon > PI {
            lon -= 2.0 * PI;
        }
        if lon < -PI {
            lon += 2.0 * PI;
        }
        let mut lambda = lon - meridian(zone);
        if lambda > PI {
            lambda -= 2.0 * PI;
        }
        if lambda < -PI {
            lambda += 2.0 * PI;
        }
        let test = lambda
            .abs()
            .min((lambda - PI).abs())
            .min((lambda + PI).abs())
            .min(FRAC_PI_2 - lat)
            .min(FRAC_PI_2 + lat);
        if test > 70.0 * RAD {
            return Err(Error::new(LONGITUDE));
        }
        let p = (self.eccentricity * atanh(self.eccentricity * lat.sin())).exp();
        let part1 = (1.0 + lat.sin()) / p;
        let part2 = (1.0 - lat.sin()) * p;
        let cos_chi = 2.0 * lat.cos() / (part1 + part2);
        let sin_chi = (part1 - part2) / (part1 + part2);
        let u = atanh(cos_chi * lambda.sin());
        let v = sin_chi.atan2(cos_chi * lambda.cos());
        let (cu, su) = series(2.0 * u, true);
        let (cv, sv) = series(2.0 * v, false);
        let (mut x, mut y) = (0.0, 0.0);
        for k in (0..6).rev() {
            x += FORWARD[k] * su[k] * cv[k];
            y += FORWARD[k] * cu[k] * sv[k];
        }
        x += u;
        y += v;
        let result = Utm {
            zone,
            hemisphere: if lat < 0.0 { 'S' } else { 'N' },
            easting: self.radius * x + 500000.0,
            northing: self.radius * y + if lat < 0.0 { 10000000.0 } else { 0.0 },
        };
        validate_utm(&result)?;
        Ok(result)
    }

    pub fn utm_inverse(&self, p: &Utm) -> Result<(f64, f64)> {
        let (lat, lon) = self.utm_inverse_cell(p)?;
        if !(-80.5 * RAD - EPS..84.5 * RAD + EPS).contains(&lat) {
            return Err(Error::new(NORTHING));
        }
        Ok((lat, lon))
    }

    // A valid cell's boundary can extend beyond the projection's normal
    // latitude domain. Only geometry uses this variant; validate its center
    // with the ordinary inverse before projecting any boundary vertices.
    pub(crate) fn utm_inverse_cell(&self, p: &Utm) -> Result<(f64, f64)> {
        validate_utm(p)?;
        let x = (1.0 / self.radius) * (p.easting - 500000.0);
        let y =
            (1.0 / self.radius) * (p.northing - if p.hemisphere == 'S' { 10000000.0 } else { 0.0 });
        let (cx, sx) = series(2.0 * x, true);
        let (cy, sy) = series(2.0 * y, false);
        let (mut u, mut v) = (0.0, 0.0);
        for k in (0..6).rev() {
            u += INVERSE[k] * sx[k] * cy[k];
            v += INVERSE[k] * cx[k] * sy[k];
        }
        u += x;
        v += y;
        let cosh_u = u.cosh();
        let lambda = if v.cos().abs() < 1e-11 && cosh_u.abs() < 1e-11 {
            0.0
        } else {
            u.sinh().atan2(v.cos())
        };
        let sin_chi = v.sin() / cosh_u;
        let mut s = sin_chi;
        let mut old = 1e99;
        for _ in 0..30 {
            let p = (self.eccentricity * atanh(self.eccentricity * s)).exp();
            let p_sq = p * p;
            s = ((1.0 + sin_chi) * p_sq - (1.0 - sin_chi))
                / ((1.0 + sin_chi) * p_sq + (1.0 - sin_chi));
            if (s - old).abs() < 1e-12 {
                break;
            }
            old = s;
        }
        let lat = s.asin();
        let mut lon = meridian(p.zone) + lambda;
        if lon > PI {
            lon -= 2.0 * PI;
        }
        if lon <= -PI {
            lon += 2.0 * PI;
        }
        if !lat.is_finite() || !lon.is_finite() {
            return Err(Error::new(NORTHING));
        }
        Ok((lat, lon))
    }

    pub fn ups_forward(&self, mut lat: f64, mut lon: f64) -> Result<(char, f64, f64)> {
        if (-79.5 * RAD + EPS..0.0).contains(&lat) || (0.0..83.5 * RAD - EPS).contains(&lat) {
            return Err(Error::new(LATITUDE));
        }
        let south = lat < 0.0;
        let hemi = if south { 'S' } else { 'N' };
        if (lat.abs() - FRAC_PI_2).abs() < 1e-10 {
            return Ok((hemi, 2000000.0, 2000000.0));
        }
        if south {
            lat *= -1.0;
            lon *= -1.0;
        }
        if lon > PI {
            lon -= 2.0 * PI;
        }
        if lon < -PI {
            lon += 2.0 * PI;
        }
        let es_sin = self.eccentricity * lat.sin();
        let pow = ((1.0 - es_sin) / (1.0 + es_sin)).powf(self.eccentricity / 2.0);
        let t = (FRAC_PI_4 - lat / 2.0).tan() / pow;
        let rho = self.polar_a_mc * t / self.polar_tc;
        Ok(if south {
            (
                hemi,
                -(rho * lon.sin() - 2000000.0),
                rho * lon.cos() + 2000000.0,
            )
        } else {
            (
                hemi,
                rho * lon.sin() + 2000000.0,
                -rho * lon.cos() + 2000000.0,
            )
        })
    }

    pub fn ups_inverse(&self, hemi: char, easting: f64, northing: f64) -> Result<(f64, f64)> {
        let (lat, lon) = self.ups_inverse_cell(hemi, easting, northing)?;
        if (-79.5 * RAD + EPS..0.0).contains(&lat) || (0.0..83.5 * RAD - EPS).contains(&lat) {
            return Err(Error::new(LATITUDE));
        }
        Ok((lat, lon))
    }

    pub(crate) fn ups_inverse_cell(
        &self,
        hemi: char,
        easting: f64,
        northing: f64,
    ) -> Result<(f64, f64)> {
        if !(0.0..=4000000.0).contains(&easting) {
            return Err(Error::new(EASTING));
        }
        if !(0.0..=4000000.0).contains(&northing) {
            return Err(Error::new(NORTHING));
        }
        let (mut dx, mut dy) = (easting - 2000000.0, northing - 2000000.0);
        let rho = (dx * dx + dy * dy).sqrt();
        let (mut lat, mut lon) = (FRAC_PI_2, 0.0);
        if dx != 0.0 || dy != 0.0 {
            if hemi == 'S' {
                dx *= -1.0;
                dy *= -1.0;
            }
            let t = rho * self.polar_tc / self.polar_a_mc;
            lat = FRAC_PI_2 - 2.0 * t.atan();
            let mut old = 0.0;
            for _ in 0..30 {
                if (lat - old).abs() <= 1e-10 {
                    break;
                }
                old = lat;
                let es_sin = self.eccentricity * lat.sin();
                let pow = ((1.0 - es_sin) / (1.0 + es_sin)).powf(self.eccentricity / 2.0);
                lat = FRAC_PI_2 - 2.0 * (t * pow).atan();
            }
            lon = dx.atan2(-dy);
            if lon > PI {
                lon -= 2.0 * PI;
            }
            if lon < -PI {
                lon += 2.0 * PI;
            }
            lat = lat.clamp(-FRAC_PI_2, FRAC_PI_2);
            lon = lon.clamp(-PI, PI);
        }
        if hemi == 'S' {
            lat *= -1.0;
            lon *= -1.0;
        }
        Ok((lat, lon))
    }
}
