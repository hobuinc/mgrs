//! Compare every scalar/batch result against a frozen Python oracle.
#[allow(dead_code)]
#[path = "benchmark.rs"]
mod workload;
use mgrs::MGRS;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{error::Error, fs, path::Path};
fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: verify DATASET.csv ORACLE_DIRECTORY".into());
    }
    let (points, hash) = workload::load(&args[0])?;
    let root = Path::new(&args[1]);
    let manifest: Value = serde_json::from_slice(&fs::read(root.join("manifest.json"))?)?;
    if manifest["sha256"] != hash || manifest["count"].as_u64() != Some((points.len() / 2) as u64) {
        return Err("oracle dataset mismatch".into());
    }
    let read = |name: &str| -> Result<Vec<u8>, Box<dyn Error>> {
        let bytes = fs::read(root.join(name))?;
        if manifest["files"][name] != format!("{:x}", Sha256::digest(&bytes)) {
            return Err("oracle checksum mismatch".into());
        }
        Ok(bytes)
    };
    let m = MGRS::new();
    let mut last = Vec::new();
    for precision in 0..=5 {
        let expected = read(&format!("upstream-precision-{precision}.bin"))?;
        let batch = m.to_mgrs_array(&points, true, precision)?;
        if batch.warning.is_some() || batch.value != expected {
            return Err(format!("batch mismatch at precision {precision}").into());
        }
        for (i, p) in points.chunks_exact(2).enumerate() {
            let record = &expected[i * 15..(i + 1) * 15];
            let len = record.iter().position(|b| *b == 0).unwrap_or(15);
            if m.to_mgrs(p[0], p[1], true, precision)?.value.as_bytes() != &record[..len] {
                return Err(format!("scalar mismatch at row {i}, precision {precision}").into());
            }
        }
        last = expected;
    }
    let expected = read("upstream-inverse-precision-5.bin")?;
    let batch = m.to_lat_lon_array(&last, true, 15)?;
    if batch.warning.is_some() || expected.len() != batch.value.len() * 8 {
        return Err("inverse layout or warning mismatch".into());
    }
    let mut max: f64 = 0.0;
    for (i, bytes) in expected.chunks_exact(8).enumerate() {
        let old = f64::from_le_bytes(bytes.try_into()?);
        let error = (old - batch.value[i]).abs();
        if !error.is_finite() || error > 1e-9 {
            return Err(format!("inverse mismatch at element {i}: {error}").into());
        }
        max = max.max(error);
    }
    for (i, record) in last.chunks_exact(15).enumerate() {
        let len = record.iter().position(|b| *b == 0).unwrap_or(15);
        let scalar = m.to_lat_lon(&record[..len], true)?;
        if scalar.warning.is_some()
            || [scalar.value.0, scalar.value.1] != batch.value[2 * i..2 * i + 2]
        {
            return Err(format!("scalar inverse mismatch at row {i}").into());
        }
    }
    println!(
        "{}",
        json!({"points": points.len() / 2, "dataset_sha256": hash, "forward_precisions_exact": 6, "inverse_max_degrees": max})
    );
    Ok(())
}
