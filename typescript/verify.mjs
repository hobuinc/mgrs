import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import assert from "node:assert/strict";
import {parseCSV} from "./bench-core.mjs";
import {MGRS} from "./dist/node.js";
const [dataset, root] = process.argv.slice(2);
if (!dataset || !root) throw new Error("usage: node verify.mjs DATASET.csv ORACLE_DIRECTORY");
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const bytes = readFileSync(dataset), points = parseCSV(bytes.toString()), manifest = JSON.parse(readFileSync(join(root, "manifest.json")));
assert.equal(sha(bytes), manifest.sha256); assert.equal(points.length / 2, manifest.count);
const read = name => { const bytes = readFileSync(join(root, name)); assert.equal(sha(bytes), manifest.files[name]); return bytes; };
const m = new MGRS(w => { throw new Error(w.message); });
try {
  let last;
  for (let p = 0; p <= 5; p++) {
    const expected = read(`upstream-precision-${p}.bin`), actual = m.toMGRSArray(points, true, p);
    assert.equal(Buffer.compare(actual, expected), 0, `batch precision ${p}`);
    for (let i = 0; i < points.length / 2; i++) {
      const code = expected.toString("ascii", i * 15, (i + 1) * 15).replace(/\0+$/, "");
      assert.equal(m.toMGRS(points[2 * i], points[2 * i + 1], true, p), code, `scalar precision ${p} row ${i}`);
    }
    last = expected;
  }
  const expected = read("upstream-inverse-precision-5.bin"), batch = m.toLatLonArray(last);
  assert.equal(expected.length, batch.length * 8);
  let max = 0;
  for (let i = 0; i < batch.length; i++) {
    const error = Math.abs(expected.readDoubleLE(i * 8) - batch[i]);
    assert(Number.isFinite(error) && error <= 1e-9, `inverse element ${i}: ${error}`); max = Math.max(max, error);
  }
  for (let i = 0; i < batch.length / 2; i++) {
    const code = last.toString("ascii", i * 15, (i + 1) * 15).replace(/\0+$/, "");
    const point = m.toLatLon(code); assert.equal(point[0], batch[2 * i]); assert.equal(point[1], batch[2 * i + 1]);
  }
  console.log(JSON.stringify({points: points.length / 2, dataset_sha256: manifest.sha256, forward_precisions_exact: 6, inverse_max_degrees: max}));
} finally { m.free(); }
