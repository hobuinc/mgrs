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

    pub fn wkt(&self, proj: &Projection) -> Result<String> {
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
        let origin = ring[0];
        let area: f64 = ring
            .windows(2)
            .map(|p| {
                (p[0].0 - origin.0) * (p[1].1 - origin.1)
                    - (p[1].0 - origin.0) * (p[0].1 - origin.1)
            })
            .sum();
        if area < 0.0 {
            ring.reverse();
        }
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
