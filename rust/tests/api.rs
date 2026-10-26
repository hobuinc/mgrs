use mgrs::{LATITUDE, LAYOUT, LONGITUDE, MGRS, PRECISION, STRING};
use std::sync::Arc;

#[test]
fn caller_owned_output_buffers() {
    let m = MGRS::new();
    let points = [42.0, -93.0, 90.0, 0.0];
    let mut codes = [255; 30];
    m.to_mgrs_array_into(&points, true, 5, &mut codes).unwrap();
    assert_eq!(
        codes.as_slice(),
        m.to_mgrs_array(&points, true, 5).unwrap().value
    );
    let mut decoded = [0.0; 4];
    m.to_lat_lon_array_into(&codes, true, 15, &mut decoded)
        .unwrap();
    assert_eq!(
        decoded.as_slice(),
        m.to_lat_lon_array(&codes, true, 15).unwrap().value
    );
    assert_eq!(
        m.to_mgrs_array_into(&points, true, 5, &mut codes[..15])
            .unwrap_err()
            .code,
        LAYOUT
    );
    assert_eq!(
        m.to_lat_lon_array_into(&codes, true, 0, &mut decoded)
            .unwrap_err()
            .code,
        LAYOUT
    );
    assert_eq!(
        m.to_lat_lon_array_into(&codes, true, 15, &mut decoded[..2])
            .unwrap_err()
            .code,
        LAYOUT
    );
    let warning = m
        .to_lat_lon_array_into(b"50TMK5045027900", true, 15, &mut decoded[..2])
        .unwrap();
    assert_eq!(warning.warning.unwrap().row, Some(0));
    let error = m
        .to_lat_lon_array_into(b"50TMK5045027900invalidxxxxxxxx", true, 15, &mut decoded)
        .unwrap_err();
    assert_eq!(error.code, STRING);
    assert_eq!(error.row, Some(1));
}

#[test]
fn python_doctests_and_cell_centers() {
    let m = MGRS::new();
    for (lat, lon, code) in [
        (42., -93., "15TWG0000049776"),
        (38.9072, -77.0369, "18SUJ2338308450"),
        (39.9526, -75.1652, "18SVK8588822509"),
    ] {
        assert_eq!(m.to_mgrs(lat, lon, true, 5).unwrap().value, code);
    }
    let p = m.to_lat_lon("15TWG0000049776", true).unwrap().value;
    assert_eq!(format!("{:.5}, {:.5}", p.0, p.1), "42.00000, -92.99999");
    let p = m.to_lat_lon("15SWC8081751205", true).unwrap().value;
    assert_eq!(format!("{:.5}, {:.5}", p.0, p.1), "38.40543, -92.07439");
    let u = m.mgrs_to_utm("15SWC8081751205").unwrap().value;
    assert_eq!(
        (u.zone, u.hemisphere, u.easting, u.northing),
        (15, 'N', 580817.5, 4251205.5)
    );
    assert_eq!(
        m.utm_to_mgrs(15, 'N', 580817., 4251205., 5).unwrap().value,
        "15SWC8081751205"
    );
    for (code, expected) in [
        ("50TMK5045027900", "39.99984, 116.41952"),
        ("32TNK0000000000", "39.74991, 9.00001"),
    ] {
        let p = m.to_lat_lon(code, true).unwrap();
        assert!(p.warning.is_some());
        assert_eq!(format!("{:.5}, {:.5}", p.value.0, p.value.1), expected);
    }
    for (input, expected) in [
        ("321942N", "32.32833"),
        ("321942.29N", "32.32841"),
        ("671328.35W", "-67.22454"),
        ("321942.29S", "-32.32841"),
    ] {
        assert_eq!(format!("{:.5}", m.dmstodd(input).unwrap()), expected);
    }
    let p = m.ddtodms(32.328414).unwrap();
    assert_eq!(
        (p.0, p.1, format!("{:.2}", p.2)),
        (32., 19., "42.29".into())
    );
    for dd in [-32.328414, -0.5, -0.001, 0.0, 180.0] {
        let (d, mi, s) = m.ddtodms(dd).unwrap();
        let sign = if d < 0.0 || mi < 0.0 || s < 0.0 {
            -1.0
        } else {
            1.0
        };
        assert!((sign * (d.abs() + mi.abs() / 60. + s.abs() / 3600.) - dd).abs() < 1e-10);
    }
}

#[test]
fn scalar_input_hardening() {
    let m = MGRS::new();
    let expected = m.to_lat_lon("04QEJ9798790670", true).unwrap();
    assert!((expected.value.0 - 21.61643).abs() < 1e-5);
    assert!((expected.value.1 + 158.05325).abs() < 1e-5);
    for input in [
        "04QEJ 97987 90670".into(),
        "  04QEJ  97987  90670  ".into(),
        "\t04QEJ\t97987\r\n90670\x0b\x0c".into(),
        format!("{}04qej 97987 90670{}", " ".repeat(100), " ".repeat(100)),
    ] {
        assert_eq!(m.to_lat_lon(input.as_bytes(), true).unwrap(), expected);
        assert_eq!(
            m.mgrs_to_utm(&input).unwrap(),
            m.mgrs_to_utm("04QEJ9798790670").unwrap()
        );
    }
    for p in 0..6 {
        for (lat, lon) in [(21.61643, -158.05325), (90., 0.), (-90., 0.)] {
            let compact = m.to_mgrs(lat, lon, true, p).unwrap().value;
            let spaced = compact.chars().map(|c| format!(" {c}")).collect::<String>();
            assert_eq!(
                m.to_lat_lon(&spaced, true).unwrap(),
                m.to_lat_lon(&compact, true).unwrap()
            );
        }
    }
    assert_eq!(m.to_lat_lon([255], true).unwrap_err().code, STRING);
    for code in ["999999999999999", "2147483648AAA", "123NEA", "000NEA"] {
        assert_eq!(m.to_lat_lon(code, true).unwrap_err().code, STRING);
        assert_eq!(m.mgrs_to_utm(code).unwrap_err().code, STRING);
    }
}

#[test]
fn arbitrary_bytes_and_grid_letters_never_panic() {
    let m = MGRS::new();
    let mut state = 20261022_u32;
    for len in 0..=40 {
        for _ in 0..1000 {
            let code: Vec<u8> = (0..len)
                .map(|_| {
                    state ^= state << 13;
                    state ^= state >> 17;
                    state ^= state << 5;
                    state as u8
                })
                .collect();
            let _ = m.to_lat_lon(&code, true);
            let _ = m.mgrs_to_utm(&code);
        }
    }
    for a in b'A'..=b'Z' {
        for b in b'A'..=b'Z' {
            for c in b'A'..=b'Z' {
                for prefix in ["", "01", "31", "32", "60"] {
                    let code = format!("{prefix}{}{}{}0000000000", a as char, b as char, c as char);
                    if let Ok(result) = m.to_lat_lon(&code, true) {
                        assert!(result.value.0.is_finite() && result.value.1.is_finite());
                    }
                }
            }
        }
    }
}

#[test]
fn invalid_numbers_and_layouts() {
    let m = MGRS::new();
    for bad in [f64::NAN, f64::INFINITY, -91., 91.] {
        assert_eq!(m.to_mgrs(bad, 0., true, 5).unwrap_err().code, LATITUDE);
        let error = m.to_mgrs_array(&[42., -93., bad, 0.], true, 5).unwrap_err();
        assert_eq!((error.code, error.row), (LATITUDE, Some(1)));
    }
    for bad in [f64::NAN, f64::INFINITY, -181., 361.] {
        let error = m.to_mgrs_array(&[42., -93., 0., bad], true, 5).unwrap_err();
        assert_eq!((error.code, error.row), (LONGITUDE, Some(1)));
    }
    for p in [-1, 6, i32::MAX] {
        assert_eq!(m.to_mgrs(42., -93., true, p).unwrap_err().code, PRECISION);
        assert_eq!(m.to_mgrs_array(&[], true, p).unwrap_err().code, PRECISION);
    }
    assert_eq!(m.to_mgrs_array(&[42.], true, 5).unwrap_err().code, LAYOUT);
    for width in [0, 16, usize::MAX] {
        assert_eq!(
            m.to_lat_lon_array(&[], true, width).unwrap_err().code,
            LAYOUT
        );
    }
    assert_eq!(
        m.to_lat_lon_array(b"15TWG", true, 15).unwrap_err().code,
        LAYOUT
    );
    for (zone, hemi, e, n, text) in [
        (0, 'N', 500000., 4000000., "Zone Error"),
        (15, 'X', 500000., 4000000., "Hemisphere Error"),
        (15, 'N', f64::NAN, 4000000., "Easting Error"),
        (15, 'N', 500000., f64::INFINITY, "Northing Error"),
    ] {
        assert_eq!(
            m.utm_to_mgrs(zone, hemi, e, n, 5).unwrap_err().to_string(),
            text
        );
    }
}

#[test]
fn buffer_views_padding_and_ownership() {
    let m = MGRS::new();
    let mut points = [0., 0., 42., -93., 90., 0.];
    let result = m.to_mgrs_array(&points[2..], true, 5).unwrap().value;
    points.fill(f64::NAN);
    assert_eq!(&result[..15], b"15TWG0000049776");
    let decoded = m.to_lat_lon_array(&result, true, 15).unwrap().value;
    assert_eq!(decoded.len(), 4);
    assert!(m.to_mgrs_array(&[], true, 5).unwrap().value.is_empty());
    assert!(m.to_lat_lon_array(&[], true, 15).unwrap().value.is_empty());
    for code in [
        b"15TWG".as_slice(),
        b"15TWG0000049776",
        b"31NEA0000000000",
        b"\t04QEJ\t97\n90\r",
        b" ZAH 00 00 ",
    ] {
        let p = m.to_lat_lon(code, true).unwrap().value;
        assert_eq!(
            m.to_lat_lon_array(code, true, code.len()).unwrap().value,
            vec![p.0, p.1]
        );
        let mut padded = code.to_vec();
        padded.resize(15, 0);
        assert_eq!(
            m.to_lat_lon_array(&padded, true, 15).unwrap().value,
            vec![p.0, p.1]
        );
    }
    for bad in [
        b"".as_slice(),
        b"nonsense",
        b"\xffABC",
        b"04QEJ12garbage",
        b"04QEJ12\0junk",
        b"04QEJ12\0\xff",
        b" \t\n ",
    ] {
        let mut codes = b"15TWG0000049776".to_vec();
        codes.extend_from_slice(bad);
        codes.resize(30, 0);
        let error = m.to_lat_lon_array(&codes, true, 15).unwrap_err();
        assert_eq!((error.code, error.row), (STRING, Some(1)));
    }
    let codes = b"15TWG000004977650TMK5045027900";
    let result = m.to_lat_lon_array(codes, true, 15).unwrap();
    assert_eq!(result.warning.unwrap().row, Some(1));
    assert_eq!(&result.value[2..], &{
        let p = m.to_lat_lon("50TMK5045027900", true).unwrap().value;
        [p.0, p.1]
    });
}

#[test]
fn concurrent_instances_and_shared_instance() {
    let m = Arc::new(MGRS::new());
    let threads: Vec<_> = (0..8)
        .map(|_| {
            let m = Arc::clone(&m);
            std::thread::spawn(move || {
                for _ in 0..100 {
                    for (lat, lon) in [(42., -93.), (-42., 93.), (60., 6.), (78., 20.)] {
                        let code = m.to_mgrs(lat, lon, true, 5).unwrap().value;
                        assert_eq!(code, MGRS::new().to_mgrs(lat, lon, true, 5).unwrap().value);
                        let p = m.to_lat_lon(&code, true).unwrap().value;
                        assert_eq!(m.to_mgrs(p.0, p.1, true, 5).unwrap().value, code);
                        let u = m.mgrs_to_utm(&code).unwrap().value;
                        assert_eq!(
                            m.utm_to_mgrs(u.zone, u.hemisphere, u.easting, u.northing, 5)
                                .unwrap()
                                .value,
                            code
                        );
                    }
                }
            })
        })
        .collect();
    for thread in threads {
        thread.join().unwrap();
    }
}
