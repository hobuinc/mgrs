//! Private ABI for src/bindings.cpp. The projection crate remains safe Rust.
//! Inputs belong to C++ and cannot change during a call. Outputs are exclusive,
//! aligned allocations owned by the binding and unpublished until success.
//! No Rust allocation or exception crosses this boundary.
#![deny(unsafe_op_in_unsafe_fn)]

use mgrs::{Conversion, MGRS};
use std::{panic::catch_unwind, slice, sync::OnceLock};

const WARNING: u32 = 0x400;
const PANIC: u32 = 0x8000;
static ENGINE: OnceLock<MGRS> = OnceLock::new();

fn engine() -> &'static MGRS {
    ENGINE.get_or_init(MGRS::new)
}

fn boundary(f: impl FnOnce() -> u32 + std::panic::UnwindSafe) -> u32 {
    catch_unwind(f).unwrap_or(PANIC)
}

fn status<T>(result: &mgrs::Result<Conversion<T>>) -> (u32, usize) {
    match result {
        Err(e) => (e.code, e.row.unwrap_or(0)),
        Ok(value) => value
            .warning
            .map_or((0, 0), |w| (WARNING, w.row.unwrap_or(0))),
    }
}

// Empty Python buffers may have null storage; Rust slices may not.
unsafe fn input<'a, T>(ptr: *const T, len: usize) -> &'a [T] {
    if len == 0 {
        &[]
    } else {
        unsafe { slice::from_raw_parts(ptr, len) }
    }
}
unsafe fn output<'a, T>(ptr: *mut T, len: usize) -> &'a mut [T] {
    if len == 0 {
        &mut []
    } else {
        unsafe { slice::from_raw_parts_mut(ptr, len) }
    }
}

/// # Safety
/// Valid, disjoint buffers: count*2 input doubles, count*15 output bytes, one
/// writable index. Length products must fit isize; input must remain immutable.
#[no_mangle]
pub unsafe extern "C" fn mgrs_rust_forward(
    points: *const f64,
    count: usize,
    degrees: bool,
    precision: i32,
    target: *mut u8,
    index: *mut usize,
) -> u32 {
    boundary(|| {
        let result = unsafe {
            engine().to_mgrs_array_into(
                input(points, count * 2),
                degrees,
                precision,
                output(target, count * mgrs::WIDTH),
            )
        };
        let (bits, row) = status(&result);
        unsafe {
            *index = row;
        }
        bits
    })
}

/// # Safety
/// Valid, disjoint buffers: count*width input bytes, count*2 output doubles,
/// one writable index. Products fit isize; input must remain immutable.
#[no_mangle]
pub unsafe extern "C" fn mgrs_rust_inverse_array(
    codes: *const u8,
    count: usize,
    width: usize,
    degrees: bool,
    target: *mut f64,
    index: *mut usize,
) -> u32 {
    boundary(|| {
        let result = unsafe {
            engine().to_lat_lon_array_into(
                input(codes, count * width),
                degrees,
                width,
                output(target, count * 2),
            )
        };
        let (bits, row) = status(&result);
        unsafe {
            *index = row;
        }
        bits
    })
}

/// # Safety
/// code points to len immutable bytes. latitude/longitude are distinct writable
/// doubles, disjoint from code. len fits isize.
#[no_mangle]
pub unsafe extern "C" fn mgrs_rust_inverse(
    code: *const u8,
    len: usize,
    latitude: *mut f64,
    longitude: *mut f64,
) -> u32 {
    boundary(|| {
        let result = engine().to_lat_lon(unsafe { input(code, len) }, false);
        let bits = status(&result).0;
        if let Ok(point) = result {
            unsafe {
                *latitude = point.value.0;
                *longitude = point.value.1;
            }
        }
        bits
    })
}

/// # Safety
/// code points to len immutable bytes; len fits isize. All output pointers are
/// valid, aligned, writable and disjoint from one another and code.
#[no_mangle]
pub unsafe extern "C" fn mgrs_rust_to_utm(
    code: *const u8,
    len: usize,
    zone: *mut i32,
    hemisphere: *mut u8,
    easting: *mut f64,
    northing: *mut f64,
) -> u32 {
    boundary(|| {
        let result = engine().mgrs_to_utm(unsafe { input(code, len) });
        let bits = status(&result).0;
        if let Ok(point) = result {
            unsafe {
                *zone = point.value.zone;
                *hemisphere = point.value.hemisphere as u8;
                *easting = point.value.easting;
                *northing = point.value.northing;
            }
        }
        bits
    })
}

/// # Safety
/// target points to at least 16 writable bytes, exclusively owned by the caller.
#[no_mangle]
pub unsafe extern "C" fn mgrs_rust_from_utm(
    zone: i64,
    hemisphere: u8,
    easting: f64,
    northing: f64,
    precision: i32,
    target: *mut u8,
) -> u32 {
    boundary(|| {
        let zone = if (1..=60).contains(&zone) {
            zone as i32
        } else {
            0
        };
        let result = engine().utm_to_mgrs(zone, hemisphere as char, easting, northing, precision);
        let bits = status(&result).0;
        if let Ok(code) = result {
            unsafe {
                let buffer = output(target, 16);
                buffer.fill(0);
                buffer[..code.value.len()].copy_from_slice(code.value.as_bytes());
            }
        }
        bits
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn panics_are_contained() {
        assert_eq!(boundary(|| panic!("boundary test")), PANIC);
    }

    #[test]
    fn empty_buffers_may_be_null() {
        let mut row = 99;
        unsafe {
            assert_eq!(
                mgrs_rust_forward(std::ptr::null(), 0, true, 5, std::ptr::null_mut(), &mut row),
                0
            );
            assert_eq!(row, 0);
            assert_eq!(
                mgrs_rust_inverse_array(
                    std::ptr::null(),
                    0,
                    15,
                    true,
                    std::ptr::null_mut(),
                    &mut row
                ),
                0
            );
        }
    }
}
