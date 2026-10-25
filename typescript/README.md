# MGRS for TypeScript and JavaScript

The [Rust translation](../rust/README.md) of this repository's GEOTRANS 3.10 backend, compiled to WebAssembly. Node.js and browsers use the same numerical engine. Python and C++ are not needed at runtime. This ESM package includes TypeScript declarations, generated JavaScript bindings and `.wasm` binaries when built and packed.

## Build from this checkout

Install Node.js 22 or later, Rust 1.85 or later (tested with 1.90.0), and the matching WebAssembly binding tools:

```sh
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version 0.2.105 --locked
cd typescript
npm ci
npm run build
npm pack
```

Install the resulting `mgrs-geotrans-1.6.0.tgz` into an application with `npm install /path/to/mgrs-geotrans-1.6.0.tgz`. The package is not published by this change. `npm pack` must follow `npm run build`; no compiler is needed when installing a built package.

## Node.js

```ts
import {MGRS} from "mgrs-geotrans";
const m = new MGRS();
try {
  const code = m.toMGRS(42, -93); // "15TWG0000049776"
  const [lat, lon] = m.toLatLon(code);
  console.log(lat.toFixed(5), lon.toFixed(5)); // 42.00000 -92.99999
} finally {
  m.free();
}
```

Construction is synchronous in Node.js. Use ESM `import`, or dynamic `import()` from CommonJS.

## Browsers

```ts
import {init, MGRS} from "mgrs-geotrans/browser";
await init();
const m = new MGRS();
try {
  console.log(m.toMGRS(42, -93));
} finally {
  m.free();
}
```

Call and await `init()` once before creating instances. It loads `wasm/web/mgrs_bg.wasm` relative to the generated binding module. Serve the package files over HTTP(S), with `application/wasm` for `.wasm`. Bundlers must preserve or emit that asset; alternatively pass its URL, fetched bytes or a `WebAssembly.Module` to `init`. The package export `mgrs-geotrans/wasm` identifies the web binary. For direct browser use without a bundler, import `./dist/browser.js` and preserve `dist/` and `wasm/web/` relative paths. The `browser` package condition also selects this entry in compatible bundlers.

Each worker must initialize its own module and `MGRS` instance. The API does synchronous CPU work; use a worker for large arrays to keep the page responsive. No shared WebAssembly memory or cross-origin isolation is required.

## API

Names, positional arguments and defaults follow Python. All latitude/longitude tuples use latitude first. `inDegrees=false` selects radians.

| Method | Result |
| --- | --- |
| `toMGRS(lat, lon, inDegrees=true, MGRSPrecision=5)` | `string` |
| `toLatLon(code, inDegrees=true)` | `[latitude, longitude]` |
| `MGRSToUTM(code, encoding="utf-8")` | `[zone, hemisphere, easting, northing]` |
| `UTMToMGRS(zone, hemisphere, easting, northing, MGRSPrecision=5)` | `string` |
| `toMGRSArray(points, inDegrees=true, MGRSPrecision=5)` | `Uint8Array` |
| `toLatLonArray(codes, inDegrees=true, {width=15}={})` | `Float64Array` |
| `ddtodms(decimalDegrees)` | `[degrees, minutes, seconds]` |
| `dmstodd(compactDMS)` | `number` |

MGRS inputs accept `string` or `Uint8Array` (including Node `Buffer`); hemisphere accepts a one-character string or ASCII bytes. The encoding argument accepts `utf-8`, `utf8` and `ascii` for string inputs. Arbitrary Python codecs are not provided. Compact DMS examples: `"321942.29N"` → about `32.328414`, `"671328.35W"` → about `-67.224542`. A leading sign is also supported. `ddtodms` places a negative sign on the first nonzero component only.

Precision is an integer 0–5, corresponding to 100 km, 10 km, 1 km, 100 m, 10 m and 1 m cells. Forward conversions truncate. **Inverse conversions return the cell center**, including `MGRSToUTM`: +0.5 m on each projected grid axis at precision 5 and +50 km at precision 0. WGS84, Norway/Svalbard exceptions and polar UPS behavior match Python GEOTRANS 3.10. `MGRSToUTM` can reject UPS references outside the supported UTM latitude range. Native and WebAssembly inverse floating-point results are checked within 1e-9 degrees; exact floating-point equality across runtimes is not guaranteed.

ASCII whitespace before, after and between MGRS groups is removed; lowercase is accepted. Invalid characters, non-ASCII whitespace, trailing junk and embedded scalar NULs are rejected. Coordinates must be finite, latitude within ±90°, longitude from −180° through 360°, or corresponding radian limits. UTM zones are integers 1–60 and hemisphere must be `"N"` or `"S"`.

## Typed arrays

```ts
const points = new Float64Array([42, -93, 90, 0]);
const codes = m.toMGRSArray(points);
console.assert(codes.length === 30);
const coordinates = m.toLatLonArray(codes);
console.assert(coordinates.length === 4);
```

Forward input is flat interleaved Float64 latitude/longitude pairs. Forward output contains **15-byte records**, padded with NUL bytes on the right. Inverse accepts fixed-width Uint8 records, width 1–15, and returns interleaved Float64 pairs. Example compact records: `m.toLatLonArray(new TextEncoder().encode("15TWG"), true, {width: 5})`.

Input lengths must match the record layout; empty arrays are supported. Plain JS arrays, other typed-array element types and DataView are rejected. Contiguous `subarray` views and nonzero byte offsets work. Inputs are copied into Wasm and never mutated or retained; returned arrays own their JS storage and remain valid after subsequent conversions or `free()`. Typed arrays handle native alignment and endianness; use DataView to decode externally serialized numbers before conversion.

## Errors, warnings and lifetime

Invalid conversions throw `MGRSError`; `.row` is the zero-based first failing row for batch conversion errors. Layout/type errors throw `TypeError`, `RangeError` or `MGRSError`. A failing batch returns no partial results.

Latitude-band warnings keep the computed coordinates and call a handler. The default is `console.warn`:

```ts
const warnings = [];
const m = new MGRS(warning => warnings.push(warning));
const point = m.toLatLon("50TMK5045027900");
console.assert(warnings.length === 1);
m.free();
```

A warning has `message` and an optional first affected batch `row`. A handler may throw to treat warnings as errors. The instance remains usable afterward. Python's deprecated `RTreeError` and low-level `ctypes` APIs are not exported.

Call `free()` to release the Rust instance promptly; repeated calls are harmless and subsequent conversions fail. The generated bindings also support garbage collection, but explicit release avoids relying on GC timing. Instances do not share mutable projection state.

## Tests and performance

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run check
npm pack
npm run test:package -- ./mgrs-geotrans-1.6.0.tgz
npm run bench -- --points 1000000 --repeats 5
npm run bench:browser -- --points 1000000 --repeats 5
```

The browser runner uses headless Chromium; it executes the same conformance cases as Node. Other browser engines are not yet tested. `npm run test:node` tests an existing build without rebuilding Rust. `test:package` installs the tarball in a temporary consumer, checks both engines and compiles the public TypeScript declarations without Node type dependencies.

CI builds the Wasm package once, then tests that artifact on Node 22 and 24 on Linux, macOS and Windows. It also runs browser worker and performance smoke tests. See the [coverage map](../rust/tests/fixtures/README.md) and [performance guide](../benchmarks/rust-typescript.md) for the fixed million-point workload and independent scalar/batch forward/inverse baselines.

See [NOTICE](NOTICE) for the GEOTRANS source attribution and [LICENSE](LICENSE) for licensing.
