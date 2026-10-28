//! Thin WebAssembly exports; all numerical work stays in the Rust engine.
use crate::{Conversion, Error, MGRS};
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub struct Engine {
    core: MGRS,
    warning: i32,
}

impl Engine {
    fn finish<T>(
        &mut self,
        result: crate::Result<Conversion<T>>,
    ) -> std::result::Result<T, JsValue> {
        self.warning = -1;
        match result {
            Ok(value) => {
                self.warning = value
                    .warning
                    .map(|w| w.row.map(|r| r as i32).unwrap_or(-2))
                    .unwrap_or(-1);
                Ok(value.value)
            }
            Err(error) => Err(JsValue::from_str(&error.to_string())),
        }
    }
}

#[wasm_bindgen]
// Preserve the Python API names while recording the warning for the JS facade.
#[allow(clippy::wrong_self_convention)]
impl Engine {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            core: MGRS::new(),
            warning: -1,
        }
    }
    pub fn warning_row(&self) -> i32 {
        self.warning
    }
    pub fn to_mgrs(
        &mut self,
        lat: f64,
        lon: f64,
        degrees: bool,
        precision: i32,
    ) -> std::result::Result<String, JsValue> {
        self.finish(self.core.to_mgrs(lat, lon, degrees, precision))
    }
    pub fn to_lat_lon(
        &mut self,
        code: &[u8],
        degrees: bool,
    ) -> std::result::Result<Vec<f64>, JsValue> {
        let p = self.finish(self.core.to_lat_lon(code, degrees))?;
        Ok(vec![p.0, p.1])
    }
    pub fn to_wkt(&mut self, code: &[u8]) -> std::result::Result<String, JsValue> {
        self.finish(self.core.to_wkt(code))
    }
    pub fn to_geojson(&mut self, code: &[u8]) -> std::result::Result<String, JsValue> {
        self.finish(self.core.to_geojson(code))
    }
    pub fn mgrs_to_utm(&mut self, code: &[u8]) -> std::result::Result<Vec<f64>, JsValue> {
        let p = self.finish(self.core.mgrs_to_utm(code))?;
        Ok(vec![
            p.zone as f64,
            p.hemisphere as u32 as f64,
            p.easting,
            p.northing,
        ])
    }
    pub fn utm_to_mgrs(
        &mut self,
        zone: i32,
        hemi: &str,
        e: f64,
        n: f64,
        precision: i32,
    ) -> std::result::Result<String, JsValue> {
        if hemi.len() != 1 {
            return Err(JsValue::from_str("Hemisphere Error"));
        }
        self.finish(
            self.core
                .utm_to_mgrs(zone, hemi.chars().next().unwrap(), e, n, precision),
        )
    }
    pub fn to_mgrs_array(
        &mut self,
        points: &[f64],
        degrees: bool,
        precision: i32,
    ) -> std::result::Result<Vec<u8>, JsValue> {
        self.finish(self.core.to_mgrs_array(points, degrees, precision))
    }
    pub fn to_lat_lon_array(
        &mut self,
        codes: &[u8],
        degrees: bool,
        width: usize,
    ) -> std::result::Result<Vec<f64>, JsValue> {
        self.finish(self.core.to_lat_lon_array(codes, degrees, width))
    }
    pub fn ddtodms(&self, dd: f64) -> std::result::Result<Vec<f64>, JsValue> {
        self.core
            .ddtodms(dd)
            .map(|v| vec![v.0, v.1, v.2])
            .map_err(js_error)
    }
    pub fn dmstodd(&self, dms: &str) -> std::result::Result<f64, JsValue> {
        self.core.dmstodd(dms).map_err(js_error)
    }
}
fn js_error(e: Error) -> JsValue {
    JsValue::from_str(&e.to_string())
}

impl Default for Engine {
    fn default() -> Self {
        Self::new()
    }
}
