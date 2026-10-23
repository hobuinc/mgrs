//! cargo run --release --example benchmark -- --points 1000000 --repeats 5
use mgrs::MGRS;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, error::Error, fs, hint::black_box, path::Path, time::Instant};

type BenchResult<T> = Result<T, Box<dyn Error>>;

fn generated(count: usize, seed: u32) -> Vec<f64> {
    let mut state = seed;
    let mut random = || {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        (state as f64 + 0.5) / 4294967296.0
    };
    let mut points = Vec::with_capacity(count * 2);
    for _ in 0..count {
        points.push((random() * 2.0 - 1.0).asin() * 180.0 / std::f64::consts::PI);
        points.push(random() * 360.0 - 180.0);
    }
    points
}
pub(crate) fn load(path: &str) -> BenchResult<(Vec<f64>, String)> {
    let bytes = fs::read(path)?;
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let manifest = Path::new(path).with_extension("json");
    let manifest: Option<Value> = if manifest.exists() {
        Some(serde_json::from_slice(&fs::read(manifest)?)?)
    } else {
        None
    };
    if let Some(m) = &manifest {
        if m["sha256"].as_str() != Some(&hash) {
            return Err("dataset checksum mismatch".into());
        }
    }
    let text = std::str::from_utf8(&bytes)?;
    let mut lines = text.lines();
    if lines.next() != Some("latitude,longitude") {
        return Err("invalid CSV header".into());
    }
    let mut points = Vec::new();
    for line in lines {
        let (lat, lon) = line.split_once(',').ok_or("invalid CSV row")?;
        let lat: f64 = lat.parse()?;
        let lon: f64 = lon.parse()?;
        if !(-90.0..=90.0).contains(&lat) || !(-180.0..=360.0).contains(&lon) {
            return Err("invalid dataset coordinates".into());
        }
        points.extend_from_slice(&[lat, lon]);
    }
    if let Some(m) = &manifest {
        if m["count"].as_u64() != Some((points.len() / 2) as u64) {
            return Err("dataset count mismatch".into());
        }
    }
    Ok((points, hash))
}
fn distance(a: &[f64], b: &[f64]) -> f64 {
    let rad = std::f64::consts::PI / 180.0;
    let dy = (b[0] - a[0]) * rad;
    let dx = (b[1] - a[1]) * rad;
    let h = (dy / 2.0).sin().powi(2)
        + (a[0] * rad).cos() * (b[0] * rad).cos() * (dx / 2.0).sin().powi(2);
    6371008.8 * 2.0 * h.clamp(0.0, 1.0).sqrt().asin()
}
fn median(values: &[f64]) -> BenchResult<f64> {
    if values.is_empty() || values.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err("invalid timing samples".into());
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let n = sorted.len();
    Ok(if n % 2 == 0 {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    } else {
        sorted[n / 2]
    })
}
fn compare(report: &Value, baseline: &Value, limit: f64) -> BenchResult<bool> {
    if !limit.is_finite() || limit < 0.0 {
        return Err("invalid regression limit".into());
    }
    for key in [
        "backend",
        "runtime",
        "platform",
        "dataset_sha256",
        "points",
        "precision",
        "repeats",
    ] {
        if report[key].is_null() || report[key] != baseline[key] {
            return Err(format!("incompatible baseline: {key}").into());
        }
    }
    let mut pass = true;
    for name in [
        "scalar_forward",
        "scalar_inverse",
        "batch_forward",
        "batch_inverse",
    ] {
        let old = baseline["timings"][name]["median_seconds"]
            .as_f64()
            .ok_or("missing baseline timing")?;
        let new = report["timings"][name]["median_seconds"]
            .as_f64()
            .ok_or("missing candidate timing")?;
        if old <= 0.0 || !old.is_finite() || new <= 0.0 || !new.is_finite() {
            return Err("invalid baseline timing".into());
        }
        if new > old * (1.0 + limit / 100.0) {
            pass = false;
        }
    }
    Ok(pass)
}

fn run() -> BenchResult<bool> {
    let mut args = BTreeMap::new();
    let mut input = std::env::args().skip(1);
    while let Some(key) = input.next() {
        if ![
            "--points",
            "--seed",
            "--dataset",
            "--repeats",
            "--output",
            "--baseline",
            "--max-regression",
        ]
        .contains(&key.as_str())
        {
            return Err(format!("unknown option {key}").into());
        }
        args.insert(key, input.next().ok_or("option requires a value")?);
    }
    let get = |key: &str, default: &str| args.get(key).cloned().unwrap_or_else(|| default.into());
    let count: usize = get("--points", "1000000").parse()?;
    let seed: u32 = get("--seed", "20261022").parse()?;
    let repeats: usize = get("--repeats", "5").parse()?;
    let limit: f64 = get("--max-regression", "10").parse()?;
    if count == 0 || repeats == 0 || seed == 0 || !limit.is_finite() || limit < 0.0 {
        return Err(
            "points, seed, repeats must be positive; regression limit must be nonnegative".into(),
        );
    }
    let (points, hash) = if let Some(path) = args.get("--dataset") {
        load(path)?
    } else {
        let points = generated(count, seed);
        let mut digest = Sha256::new();
        for p in &points {
            digest.update(p.to_le_bytes());
        }
        (points, format!("{:x}", digest.finalize()))
    };
    let count = points.len() / 2;
    if count == 0 {
        return Err("empty dataset".into());
    }
    let m = MGRS::new();
    let codes = m.to_mgrs_array(&points, true, 5)?.value;
    let decoded = m.to_lat_lon_array(&codes, true, 15)?.value;
    let strings: Vec<_> = codes
        .chunks_exact(15)
        .map(|r| std::str::from_utf8(r).unwrap().trim_end_matches('\0'))
        .collect();
    let mut max_error: f64 = 0.0;
    for (i, p) in points.chunks_exact(2).enumerate() {
        if m.to_mgrs(p[0], p[1], true, 5)?.value != strings[i] {
            return Err("scalar/batch forward mismatch".into());
        }
        let scalar = m.to_lat_lon(strings[i], true)?.value;
        if [scalar.0, scalar.1] != decoded[2 * i..2 * i + 2] {
            return Err("scalar/batch inverse mismatch".into());
        }
        max_error = max_error.max(distance(p, &decoded[2 * i..2 * i + 2]));
    }
    if max_error > 3.0 {
        return Err(format!("round-trip error {max_error} exceeds 3 m").into());
    }
    for (i, p) in points.chunks_exact(2).take(10000).enumerate() {
        black_box(m.to_mgrs(p[0], p[1], true, 5)?);
        black_box(m.to_lat_lon(strings[i], true)?);
    }
    let mut samples = [vec![], vec![], vec![], vec![]];
    for repeat in 0..repeats {
        for operation in if repeat % 2 == 0 {
            [0, 1, 2, 3]
        } else {
            [3, 2, 1, 0]
        } {
            let start = Instant::now();
            match operation {
                0 => {
                    for p in points.chunks_exact(2) {
                        black_box(m.to_mgrs(p[0], p[1], true, 5)?);
                    }
                }
                1 => {
                    for code in &strings {
                        black_box(m.to_lat_lon(code, true)?);
                    }
                }
                2 => {
                    black_box(m.to_mgrs_array(&points, true, 5)?);
                }
                _ => {
                    black_box(m.to_lat_lon_array(&codes, true, 15)?);
                }
            }
            samples[operation].push(start.elapsed().as_secs_f64());
        }
    }
    let mut timings = serde_json::Map::new();
    for (name, samples) in [
        "scalar_forward",
        "scalar_inverse",
        "batch_forward",
        "batch_inverse",
    ]
    .iter()
    .zip(&samples)
    {
        let med = median(samples)?;
        timings.insert(name.to_string(), json!({"samples_seconds": samples, "median_seconds": med, "points_per_second": count as f64 / med}));
    }
    let runtime = std::process::Command::new("rustc")
        .arg("--version")
        .output()?;
    if !runtime.status.success() {
        return Err("cannot determine Rust compiler".into());
    }
    let runtime = String::from_utf8(runtime.stdout)?.trim().to_string();
    let host = std::process::Command::new("hostname").output()?;
    if !host.status.success() {
        return Err("cannot determine benchmark host".into());
    }
    let platform = format!(
        "{}/{}/{}",
        std::env::consts::OS,
        std::env::consts::ARCH,
        String::from_utf8_lossy(&host.stdout).trim()
    );
    let mut report = json!({"backend": "Rust GEOTRANS 3.10", "runtime": runtime, "platform": platform, "repeats": repeats, "dataset_sha256": hash, "points": count,
        "precision": 5, "seed": seed, "max_roundtrip_metres": max_error, "timings": timings});
    let pass = if let Some(path) = args.get("--baseline") {
        compare(&report, &serde_json::from_slice(&fs::read(path)?)?, limit)?
    } else {
        true
    };
    report["regression_passed"] = json!(pass);
    let output = serde_json::to_string_pretty(&report)? + "\n";
    if let Some(path) = args.get("--output") {
        if let Some(parent) = Path::new(path)
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
        {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &output)?;
    }
    print!("{output}");
    Ok(pass)
}
fn main() {
    match run() {
        Ok(true) => {}
        Ok(false) => std::process::exit(1),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reproducible_global_coverage() {
        assert_eq!(generated(1000, 7), generated(1000, 7));
        assert_ne!(generated(1000, 7), generated(1000, 8));
        let p = generated(10000, 20261022);
        assert!(p.chunks_exact(2).any(|p| p[0] > 84.));
        assert!(p.chunks_exact(2).any(|p| p[0] < -80.));
        assert!(p.iter().all(|p| p.is_finite()));
        for count in [1, 3, 17, 1000] {
            assert_eq!(generated(count, 1).len(), count * 2);
        }
    }
    #[test]
    fn timing_and_roundtrip_validation() {
        assert_eq!(median(&[4., 1., 2., 3.]).unwrap(), 2.5);
        for values in [vec![], vec![0.], vec![f64::NAN], vec![-1.]] {
            assert!(median(&values).is_err());
        }
        assert!(distance(&[42., -93.], &[43., -93.]) > 100000.);
        assert!(distance(&[0., 180.], &[0., -180.]) < 1e-6);
    }
    #[test]
    fn independent_regression_gates() {
        let mut report = json!({"backend": "rust", "runtime": "test", "platform": "host", "repeats": 5, "dataset_sha256": "abc", "points": 1, "precision": 5, "timings": {}});
        for name in [
            "scalar_forward",
            "scalar_inverse",
            "batch_forward",
            "batch_inverse",
        ] {
            report["timings"][name] = json!({"median_seconds": 1.0});
        }
        for name in [
            "scalar_forward",
            "scalar_inverse",
            "batch_forward",
            "batch_inverse",
        ] {
            let mut candidate = report.clone();
            candidate["timings"][name]["median_seconds"] = json!(1.1);
            assert!(compare(&candidate, &report, 10.).unwrap());
            candidate["timings"][name]["median_seconds"] = json!(1.1001);
            assert!(!compare(&candidate, &report, 10.).unwrap());
        }
        for key in [
            "backend",
            "runtime",
            "platform",
            "dataset_sha256",
            "points",
            "precision",
            "repeats",
        ] {
            let mut other = report.clone();
            other[key] = json!("changed");
            assert!(compare(&report, &other, 10.).is_err());
        }
        report["timings"]["batch_inverse"]["median_seconds"] = json!(0);
        assert!(compare(&report, &report, 10.).is_err());
    }
}
