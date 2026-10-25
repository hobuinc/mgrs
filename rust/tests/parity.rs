use mgrs::{Conversion, MGRS};
use serde_json::Value;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/geotrans310.json")).unwrap()
}
fn near(a: f64, b: f64, tolerance: f64, context: &str) {
    assert!(
        (a - b).abs() <= tolerance,
        "{context}: {a} != {b} (difference {})",
        (a - b).abs()
    );
}
fn check<T>(result: mgrs::Result<Conversion<T>>, expected: &Value, context: &str) -> Option<T> {
    if let Some(error) = expected.get("error") {
        assert_eq!(
            result.err().expect(context).to_string(),
            error.as_str().unwrap(),
            "{context}"
        );
        None
    } else {
        let result = result.unwrap_or_else(|e| panic!("{context}: {e}"));
        assert_eq!(
            result.warning.is_some(),
            expected["warning"].as_bool().unwrap(),
            "{context}"
        );
        Some(result.value)
    }
}

#[test]
fn all_python_forward_and_batch_cases() {
    let fixture = fixture();
    let m = MGRS::new();
    for row in fixture["forward"].as_array().unwrap() {
        let lat = row["point"][0].as_f64().unwrap();
        let lon = row["point"][1].as_f64().unwrap();
        for precision in 0..6 {
            let expected = row["codes"][precision].as_str().unwrap();
            for degrees in [true, false] {
                let (y, x) = if degrees {
                    (lat, lon)
                } else {
                    (lat.to_radians(), lon.to_radians())
                };
                assert_eq!(
                    m.to_mgrs(y, x, degrees, precision as i32).unwrap().value,
                    expected,
                    "{lat},{lon} p={precision}"
                );
                let actual = m
                    .to_mgrs_array(&[y, x], degrees, precision as i32)
                    .unwrap()
                    .value;
                let mut padded = expected.as_bytes().to_vec();
                padded.resize(15, 0);
                assert_eq!(actual, padded);
            }
        }
    }
}

#[test]
fn all_python_inverse_and_utm_cases() {
    let fixture = fixture();
    let m = MGRS::new();
    for row in fixture["inverse"].as_array().unwrap() {
        let code = row["code"].as_str().unwrap();
        for (degrees, key) in [(true, "latlon"), (false, "radians")] {
            if let Some((lat, lon)) = check(m.to_lat_lon(code, degrees), &row[key], code) {
                near(lat, row[key]["value"][0].as_f64().unwrap(), 1e-9, code);
                near(lon, row[key]["value"][1].as_f64().unwrap(), 1e-9, code);
                let mut padded = code.as_bytes().to_vec();
                padded.resize(15, 0);
                let batch = m.to_lat_lon_array(&padded, degrees, 15).unwrap();
                assert_eq!(batch.value, vec![lat, lon]);
                assert_eq!(
                    batch.warning.is_some(),
                    row[key]["warning"].as_bool().unwrap()
                );
            }
        }
        if let Some(utm) = check(m.mgrs_to_utm(code), &row["utm"], code) {
            let values = &row["utm"]["value"];
            assert_eq!(utm.zone as i64, values[0].as_i64().unwrap(), "{code}");
            assert_eq!(
                utm.hemisphere.to_string(),
                values[1].as_str().unwrap(),
                "{code}"
            );
            near(utm.easting, values[2].as_f64().unwrap(), 1e-6, code);
            near(utm.northing, values[3].as_f64().unwrap(), 1e-6, code);
        }
    }
}

#[test]
fn upstream_utm_truncation_boundaries() {
    let fixture = fixture();
    for row in fixture["utm"].as_array().unwrap() {
        for precision in 0..6 {
            let result = MGRS::new()
                .utm_to_mgrs(
                    15,
                    'N',
                    row["point"][2].as_f64().unwrap(),
                    row["point"][3].as_f64().unwrap(),
                    precision,
                )
                .unwrap();
            assert_eq!(
                result.value,
                row["codes"][precision as usize].as_str().unwrap()
            );
        }
    }
}
