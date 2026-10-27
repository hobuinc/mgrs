use mgrs::MGRS;
use serde_json::Value;

fn ring(text: &str) -> Vec<(f64, f64)> {
    let points: Vec<_> = text
        .strip_prefix("POLYGON ((")
        .unwrap()
        .strip_suffix("))")
        .unwrap()
        .split(", ")
        .map(|p| {
            let (x, y) = p.split_once(' ').unwrap();
            (x.parse::<f64>().unwrap(), y.parse::<f64>().unwrap())
        })
        .collect();
    assert!(points.len() >= 5);
    assert_eq!(points.first(), points.last());
    assert!(points
        .iter()
        .all(|p| p.0.is_finite() && (-90.0..=90.0).contains(&p.1)));
    assert!(points.windows(2).all(|p| (p[0].0 - p[1].0).abs() <= 180.0));
    let o = points[0];
    let area: f64 = points
        .windows(2)
        .map(|p| (p[0].0 - o.0) * (p[1].1 - o.1) - (p[1].0 - o.0) * (p[0].1 - o.1))
        .sum();
    assert!(area > 0.0, "counterclockwise, nondegenerate ring");
    points
}

#[test]
fn independent_proj_corners_at_every_precision() {
    let m = MGRS::new();
    let fixture: Value = serde_json::from_str(include_str!("fixtures/wkt.json")).unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let code = case["code"].as_str().unwrap();
        let points = ring(&m.to_wkt(code).unwrap().value);
        for corner in case["corners"].as_array().unwrap() {
            let lon = corner[0].as_f64().unwrap();
            let lat = corner[1].as_f64().unwrap();
            assert!(
                points.iter().any(|p| {
                    let dx = (p.0 - lon + 180.0).rem_euclid(360.0) - 180.0;
                    (p.1 - lat).abs() < 1e-9 && (lat.abs() == 90.0 || dx.abs() < 1e-9)
                }),
                "{code}: missing PROJ corner {lon}, {lat}"
            );
        }
    }
}

#[test]
fn complete_cells_curved_edges_and_longitude_wrap() {
    let m = MGRS::new();
    let ordinary = ring(&m.to_wkt("15TWG0000049776").unwrap().value);
    assert_eq!(ordinary.len(), 5);
    assert!((ordinary[0].1 - 41.999997975128).abs() < 1e-12);
    assert!(ring(&m.to_wkt("15TWG").unwrap().value).len() > 5);
    assert!(ring(&m.to_wkt("31XDP").unwrap().value)
        .iter()
        .any(|p| p.1 > 84.5));
    assert!(ring(&m.to_wkt("BAZ").unwrap().value)
        .iter()
        .any(|p| p.1 > -79.5));
    for code in ["01NAA", "60NZF", "01NAA6602100000"] {
        assert!(ring(&m.to_wkt(code).unwrap().value)
            .iter()
            .any(|p| p.0.abs() > 180.0));
    }
    for code in ["ZAH", "ZAG", "YZH", "YZG", "BAN", "BAM", "AZN", "AZM"] {
        let points = ring(&m.to_wkt(code).unwrap().value);
        let pole: Vec<_> = points.iter().filter(|p| p.1.abs() == 90.0).collect();
        assert!(pole.len() >= 2);
        assert!(pole.iter().any(|p| (p.0 - pole[0].0).abs() == 90.0));
    }
}

#[test]
fn input_validation_and_warnings_match_point_decoding() {
    let m = MGRS::new();
    let canonical = m.to_wkt("04QEJ9798790670").unwrap();
    assert_eq!(m.to_wkt(b" \t04qej 97987\n90670\r ").unwrap(), canonical);
    for invalid in [
        b"".as_slice(),
        b"invalid",
        b"15TWG1",
        b"32XJA",
        b"15TWG\0",
        b"\xff",
    ] {
        assert_eq!(
            m.to_wkt(invalid).unwrap_err(),
            m.to_lat_lon(invalid, true).unwrap_err()
        );
    }
    let fixture: Value = serde_json::from_str(include_str!("fixtures/geotrans310.json")).unwrap();
    for case in fixture["inverse"].as_array().unwrap() {
        let code = case["code"].as_str().unwrap();
        match m.to_lat_lon(code, true) {
            Ok(point) => {
                let polygon = m.to_wkt(code).unwrap();
                assert_eq!(point.warning, polygon.warning, "{code}");
                ring(&polygon.value);
            }
            Err(error) => assert_eq!(m.to_wkt(code).unwrap_err(), error, "{code}"),
        }
    }
}
