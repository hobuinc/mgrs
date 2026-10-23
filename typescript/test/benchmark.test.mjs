import test from "node:test";
import assert from "node:assert/strict";
import {generated, parseCSV, median, compare, operations, benchmark} from "../bench-core.mjs";
import {MGRS} from "../dist/node.js";
test("reproducible global benchmark inputs and CSV validation", () => {
  assert.deepEqual(generated(1000, 7), generated(1000, 7));
  assert.notDeepEqual(generated(1000, 7), generated(1000, 8));
  const points = generated(10000);
  assert(points.some((v, i) => i % 2 === 0 && v > 84));
  assert(points.some((v, i) => i % 2 === 0 && v < -80));
  for (const count of [1, 3, 17, 1000]) assert.equal(generated(count).length, 2 * count);
  for (const count of [0, -1, NaN, 1.5]) assert.throws(() => generated(count));
  assert.deepEqual(parseCSV("latitude,longitude\r\n42,-93\r\n"), new Float64Array([42, -93]));
  for (const data of ["", "latitude,longitude\n", "latitude,longitude\nNaN,0", "latitude,longitude\n91,0", "latitude,longitude\n,0", "latitude,longitude\n0,0,0"]) assert.throws(() => parseCSV(data));
});
test("timing validation and independent regression gates", () => {
  assert.equal(median([4, 1, 2, 3]), 2.5);
  for (const values of [[], [0], [NaN], [-1], [Infinity]]) assert.throws(() => median(values));
  const report = {backend: "wasm", runtime: "test", platform: "host", dataset_sha256: "abc", points: 1, precision: 5, repeats: 5, timings: Object.fromEntries(operations.map(n => [n, {median_seconds: 1}]))};
  for (const name of operations) {
    const candidate = structuredClone(report); candidate.timings[name].median_seconds = 1.1;
    assert(compare(candidate, report)); candidate.timings[name].median_seconds = 1.1001; assert(!compare(candidate, report));
  }
  for (const key of ["backend", "runtime", "platform", "dataset_sha256", "points", "precision", "repeats"]) assert.throws(() => compare({...report, [key]: "changed"}, report));
  const broken = structuredClone(report); delete broken.timings.batch_inverse;
  assert.throws(() => compare(report, broken));
  for (const limit of [NaN, -1, Infinity]) assert.throws(() => compare(report, report, limit));
});
test("benchmark validates scalar/batch results and rejects excessive round trips", () => {
  const m = new MGRS();
  try {
    const report = benchmark(m, generated(100), 1);
    assert.equal(report.points, 100); assert(report.max_roundtrip_metres < 3);
    for (const name of operations) assert(report.timings[name].median_seconds > 0);
    const broken = Object.create(m); broken.toLatLonArray = () => new Float64Array([0, 0]);
    assert.throws(() => benchmark(broken, new Float64Array([42, -93]), 1), /inverse mismatch/);
    broken.toLatLon = () => [0, 0];
    assert.throws(() => benchmark(broken, new Float64Array([42, -93]), 1), /round-trip error/);
  } finally { m.free(); }
});
