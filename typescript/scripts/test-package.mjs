// Exercise a packed artifact in an isolated consumer, with no checkout imports.
import {spawnSync} from "node:child_process";
import {mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {resolve, join} from "node:path";
import {fileURLToPath} from "node:url";

if (process.argv.length !== 3 || !process.env.npm_execpath) {
  throw new Error("Usage: npm run test:package -- /path/to/package.tgz");
}
const archive = resolve(process.argv[2]);
const consumer = mkdtempSync(join(tmpdir(), "mgrs-package-"));
function run(args) {
  const result = spawnSync(process.execPath, args, {cwd: consumer, stdio: "inherit"});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Consumer check failed (exit ${result.status})`);
}
try {
  writeFileSync(join(consumer, "package.json"), JSON.stringify({private: true, type: "module"}));
  run([process.env.npm_execpath, "install", "--ignore-scripts", "--no-package-lock", "--no-audit", "--no-fund", archive]);
  writeFileSync(join(consumer, "check.mjs"), `
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {MGRS} from "mgrs-geotrans";
import {init, MGRS as BrowserMGRS} from "mgrs-geotrans/browser";
await init(readFileSync(new URL(import.meta.resolve("mgrs-geotrans/wasm"))));
for (const Engine of [MGRS, BrowserMGRS]) {
  const warnings = [];
  const m = new Engine(w => warnings.push(w));
  try {
    assert.equal(m.toMGRS(42, -93), "15TWG0000049776");
    assert.ok(m.toWKT("15TWG0000049776").startsWith("POLYGON ((-93.000000000000 "));
    assert.equal(m.toGeoJSON("15TWG0000049776").type, "Polygon");
    assert.equal(m.toGeoJSON("01NAA").type, "MultiPolygon");
    assert.deepEqual(m.toLatLonArray(m.toMGRSArray(new Float64Array([42, -93]))), new Float64Array(m.toLatLon("15TWG0000049776")));
    assert.deepEqual(m.toLatLon(" 04QEJ 97987 90670 "), m.toLatLon("04QEJ9798790670"));
    m.toLatLon("50TMK5045027900");
    assert.equal(warnings.length, 1);
  } finally { m.free(); }
}
console.log("Packed Node and browser engines passed standalone checks");
`);
  run(["check.mjs"]);
  writeFileSync(join(consumer, "check.mts"), `
import {MGRS, type LatLon, type Warning, type CellGeometry} from "mgrs-geotrans";
import {init, MGRS as BrowserMGRS, type CellGeometry as BrowserGeometry} from "mgrs-geotrans/browser";
const warnings: Warning[] = [];
const m = new MGRS(w => warnings.push(w));
const point: LatLon = m.toLatLon(m.toMGRS(42, -93));
const polygon: string = m.toWKT("15TWG0000049776");
const polygonBytes: string = m.toWKT(new TextEncoder().encode("15TWG"));
const geometry: CellGeometry = m.toGeoJSON("15TWG0000049776");
const browserGeometry: BrowserGeometry = geometry;
if (geometry.type === "Polygon") {
  const point: [number, number] = geometry.coordinates[0][0];
} else {
  const point: [number, number] = geometry.coordinates[0][0][0];
}
// @ts-expect-error GeoJSON is an object, not serialized text.
const text: string = m.toGeoJSON("15TWG");
// @ts-expect-error WKT requires an MGRS string or bytes, not a point.
m.toWKT([42, -93]);
const codes: Uint8Array = m.toMGRSArray(new Float64Array(point));
const result: Float64Array = m.toLatLonArray(codes, true, {width: 15});
// @ts-expect-error The public API requires Float64Array, not number[].
m.toMGRSArray([42, -93]);
// @ts-expect-error The inverse result contains numbers, not strings.
const invalid: [string, string] = m.toLatLon("15TWG0000049776");
await init(new Uint8Array());
new BrowserMGRS().free();
m.free();
`);
  run([fileURLToPath(new URL("../node_modules/typescript/bin/tsc", import.meta.url)),
    "--strict", "--noEmit", "--module", "NodeNext", "--moduleResolution", "NodeNext",
    "--target", "ES2022", "check.mts"]);
  console.log("Packed TypeScript declarations passed consumer checks");
} finally {
  rmSync(consumer, {recursive: true, force: true});
}
