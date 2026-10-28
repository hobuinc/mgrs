//! Cell footprints in longitude/latitude. Grid decoding stays in grid.rs so
//! cell-center validation, northing cycles and warning behavior remain shared.
use crate::projection::{Projection, RAD};
use crate::{Result, Utm};
use std::fmt::Write;

// Approximate local distance for the adaptive chord error, in metres.
const METRES_PER_DEGREE: f64 = 6378137.0 * RAD;
const TOLERANCE: f64 = 0.1;
const MAX_DEPTH: u32 = 16;
type Point = (f64, f64);

pub(crate) struct Cell {
    pub zone: i32, // zero denotes UPS
    pub hemisphere: char,
    pub easting: f64,
    pub northing: f64,
    pub size: f64,
}

fn unwrap(lon: f64, reference: f64) -> f64 {
    lon + 360.0 * ((reference - lon) / 360.0).round()
}

fn midpoint(a: Point, b: Point) -> Point {
    ((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0)
}

fn signed_area(ring: &[Point]) -> f64 {
    let origin = ring[0];
    ring.windows(2)
        .map(|p| {
            (p[0].0 - origin.0) * (p[1].1 - origin.1) - (p[1].0 - origin.0) * (p[0].1 - origin.1)
        })
        .sum()
}

// Clip an open ring against one longitude boundary. The cell crosses each
// antimeridian at most twice, so each resulting half is a single exterior.
fn clip(ring: &[Point], longitude: f64, keep_east: bool) -> Vec<Point> {
    let mut result = Vec::new();
    let Some(&last) = ring.last() else {
        return result;
    };
    let inside = |p: Point| {
        if keep_east {
            p.0 >= longitude
        } else {
            p.0 <= longitude
        }
    };
    let mut previous = last;
    for &current in ring {
        if inside(previous) != inside(current) {
            let t = (longitude - previous.0) / (current.0 - previous.0);
            result.push((longitude, previous.1 + t * (current.1 - previous.1)));
        }
        if inside(current) {
            result.push(current);
        }
        previous = current;
    }
    result.dedup();
    if result.len() > 1 && result.first() == result.last() {
        result.pop();
    }
    result
}

fn geojson(ring: &[Point]) -> String {
    let min_lon = ring.iter().map(|p| p.0).fold(f64::INFINITY, f64::min);
    let max_lon = ring.iter().map(|p| p.0).fold(f64::NEG_INFINITY, f64::max);
    let first = ((min_lon + 180.0) / 360.0).floor() as i32;
    let last = ((max_lon + 180.0) / 360.0).floor() as i32;
    let mut polygons = Vec::new();
    for strip in first..=last {
        let offset = f64::from(strip) * 360.0;
        let part = clip(&ring[..ring.len() - 1], offset - 180.0, true);
        let mut part = clip(&part, offset + 180.0, false);
        if part.len() < 3 {
            continue;
        }
        part.push(part[0]);
        if signed_area(&part) <= 0.0 {
            continue; // A cell merely touching the seam has no second polygon.
        }
        for point in &mut part {
            point.0 = (point.0 - offset).clamp(-180.0, 180.0);
        }
        polygons.push(part);
    }
    let multi = polygons.len() > 1;
    let kind = if multi { "MultiPolygon" } else { "Polygon" };
    let mut json = format!("{{\"type\":\"{kind}\",\"coordinates\":[");
    for (i, polygon) in polygons.iter().enumerate() {
        if i != 0 {
            json.push(',');
        }
        if multi {
            json.push('[');
        }
        json.push('[');
        for (j, (lon, lat)) in polygon.iter().enumerate() {
            if j != 0 {
                json.push(',');
            }
            write!(json, "[{lon:.12},{lat:.12}]").expect("writing to String");
        }
        json.push(']');
        if multi {
            json.push(']');
        }
    }
    json.push_str("]}");
    json
}

impl Cell {
    fn project(&self, proj: &Projection, p: Point) -> Result<Point> {
        let (lat, lon) = if self.zone == 0 {
            proj.ups_inverse_cell(self.hemisphere, p.0, p.1)?
        } else {
            proj.utm_inverse_cell(&Utm {
                zone: self.zone,
                hemisphere: self.hemisphere,
                easting: p.0,
                northing: p.1,
            })?
        };
        Ok((lon / RAD, lat / RAD))
    }

    fn pole(&self, p: Point) -> bool {
        self.zone == 0 && p == (2000000.0, 2000000.0)
    }

    // Append the endpoint, subdividing until the geographic chord's midpoint
    // follows the projected grid edge. Bounded recursion also bounds work.
    fn edge(
        &self,
        proj: &Projection,
        grid: [Point; 2],
        geo: [Point; 2],
        depth: u32,
        ring: &mut Vec<Point>,
    ) -> Result<()> {
        let mid = midpoint(grid[0], grid[1]);
        let chord = midpoint(geo[0], geo[1]);
        let mut actual = self.project(proj, mid)?;
        actual.0 = unwrap(actual.0, chord.0);
        let dx = (actual.0 - chord.0) * (actual.1 * RAD).cos();
        let dy = actual.1 - chord.1;
        let error = dx.hypot(dy) * METRES_PER_DEGREE;
        if error > TOLERANCE && depth < MAX_DEPTH {
            self.edge(proj, [grid[0], mid], [geo[0], actual], depth + 1, ring)?;
            self.edge(proj, [mid, grid[1]], [actual, geo[1]], depth + 1, ring)?;
        } else {
            ring.push(geo[1]);
        }
        Ok(())
    }

    fn ring(&self, proj: &Projection) -> Result<Vec<Point>> {
        let (e, n, s) = (self.easting, self.northing, self.size);
        let corners = [(e, n), (e + s, n), (e + s, n + s), (e, n + s)];
        let center = self.project(proj, (e + s / 2.0, n + s / 2.0))?;
        let mut ring = Vec::new();
        for i in 0..4 {
            let a = corners[i];
            let b = corners[(i + 1) % 4];
            let mut start = self.project(proj, a)?;
            let mut end = self.project(proj, b)?;
            // Longitude at a pole is indeterminate. Each incident radial edge
            // keeps its own longitude; the two pole vertices close the wedge.
            if self.pole(a) {
                start.0 = end.0;
            }
            if self.pole(b) {
                end.0 = start.0;
            }
            start.0 = unwrap(start.0, center.0);
            end.0 = unwrap(end.0, start.0);
            if ring.last() != Some(&start) {
                ring.push(start);
            }
            self.edge(proj, [a, b], [start, end], 0, &mut ring)?;
        }
        if ring.last() != ring.first() {
            ring.push(ring[0]);
        }
        // Translate before taking the area to avoid cancellation for 1 m cells.
        if signed_area(&ring) < 0.0 {
            ring.reverse();
        }
        Ok(ring)
    }

    pub fn geojson(&self, proj: &Projection) -> Result<String> {
        Ok(geojson(&self.ring(proj)?))
    }

    pub fn wkt(&self, proj: &Projection) -> Result<String> {
        let ring = self.ring(proj)?;
        let mut wkt = String::from("POLYGON ((");
        for (i, (lon, lat)) in ring.into_iter().enumerate() {
            if i != 0 {
                wkt.push_str(", ");
            }
            write!(wkt, "{lon:.12} {lat:.12}").expect("writing to String");
        }
        wkt.push_str("))");
        Ok(wkt)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    #[test]
    fn antimeridian_cutting_preserves_parts_and_ignores_zero_area_touches() {
        let ring = [(179., 1.), (181., 1.), (181., 2.), (179., 2.), (179., 1.)];
        let actual: Value = serde_json::from_str(&geojson(&ring)).unwrap();
        assert_eq!(
            actual,
            json!({"type": "MultiPolygon", "coordinates": [
                [[[179.,1.],[180.,1.],[180.,2.],[179.,2.],[179.,1.]]],
                [[[-180.,1.],[-179.,1.],[-179.,2.],[-180.,2.],[-180.,1.]]]
            ]})
        );
        for (west, east) in [(179., 180.), (-180., -179.), (180., 181.)] {
            let ring = [(west, 1.), (east, 1.), (east, 2.), (west, 2.), (west, 1.)];
            let value: Value = serde_json::from_str(&geojson(&ring)).unwrap();
            assert_eq!(value["type"], "Polygon");
            assert_eq!(value["coordinates"].as_array().unwrap().len(), 1);
            assert_eq!(value["coordinates"][0].as_array().unwrap().len(), 5);
        }
    }
}
