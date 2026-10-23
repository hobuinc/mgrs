// Shared Node/browser workload. Input creation and validation are outside timing.
export const operations = ["scalar_forward", "scalar_inverse", "batch_forward", "batch_inverse"];
export function generated(count, seed = 20261022) {
  if (!Number.isSafeInteger(count) || count < 1 || !Number.isInteger(seed) || seed < 1 || seed > 0xffffffff) throw new Error("invalid points or seed");
  let state = seed;
  const random = () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return ((state >>> 0) + 0.5) / 4294967296; };
  const points = new Float64Array(count * 2);
  for (let i = 0; i < count; i++) { points[2 * i] = Math.asin(random() * 2 - 1) * 180 / Math.PI; points[2 * i + 1] = random() * 360 - 180; }
  return points;
}
export function parseCSV(text) {
  const lines = text.trimEnd().split(/\r?\n/);
  if (lines.shift() !== "latitude,longitude" || !lines.length) throw new Error("invalid or empty CSV");
  const points = new Float64Array(lines.length * 2);
  lines.forEach((line, i) => {
    const values = line.split(",");
    if (values.length !== 2 || values.some(v => !v.trim())) throw new Error("invalid CSV row");
    const [lat, lon] = values.map(Number);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 360) throw new Error("invalid dataset coordinates");
    points[2 * i] = lat; points[2 * i + 1] = lon;
  });
  return points;
}
export function median(values) {
  if (!values.length || values.some(v => !Number.isFinite(v) || v <= 0)) throw new Error("invalid timing samples");
  const sorted = [...values].sort((a, b) => a - b), n = sorted.length;
  return n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
}
export function compare(report, baseline, limit = 10) {
  if (!Number.isFinite(limit) || limit < 0) throw new Error("invalid regression limit");
  for (const key of ["backend", "runtime", "platform", "dataset_sha256", "points", "precision", "repeats"]) {
    if (report[key] === undefined || report[key] !== baseline[key]) throw new Error(`incompatible baseline: ${key}`);
  }
  return operations.map(name => {
    const old = baseline.timings?.[name]?.median_seconds, current = report.timings?.[name]?.median_seconds;
    if (![old, current].every(v => Number.isFinite(v) && v > 0)) throw new Error("invalid baseline timing");
    return current <= old * (1 + limit / 100);
  }).every(Boolean);
}
export function distance(a, b) {
  const rad = Math.PI / 180, dy = (b[0] - a[0]) * rad, dx = (b[1] - a[1]) * rad;
  const h = Math.sin(dy / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dx / 2) ** 2;
  return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}
export function benchmark(m, points, repeats = 5) {
  if (!Number.isInteger(repeats) || repeats < 1 || !points.length || points.length % 2) throw new Error("invalid benchmark size");
  const count = points.length / 2, codes = m.toMGRSArray(points), decoded = m.toLatLonArray(codes);
  const strings = Array.from({length: count}, (_, i) => new TextDecoder().decode(codes.subarray(i * 15, (i + 1) * 15)).replace(/\0+$/, ""));
  let maxError = 0;
  for (let i = 0; i < count; i++) {
    if (m.toMGRS(points[2 * i], points[2 * i + 1]) !== strings[i]) throw new Error("scalar/batch forward mismatch");
    const scalar = m.toLatLon(strings[i]);
    if (scalar[0] !== decoded[2 * i] || scalar[1] !== decoded[2 * i + 1]) throw new Error("scalar/batch inverse mismatch");
    maxError = Math.max(maxError, distance(points.subarray(2 * i, 2 * i + 2), scalar));
  }
  if (maxError > 3) throw new Error(`round-trip error ${maxError} exceeds 3 m`);
  for (let i = 0; i < Math.min(count, 10000); i++) { m.toMGRS(points[2 * i], points[2 * i + 1]); m.toLatLon(strings[i]); }
  let sink;
  const calls = [() => { for (let i = 0; i < count; i++) sink = m.toMGRS(points[2 * i], points[2 * i + 1]); },
    () => { for (const code of strings) sink = m.toLatLon(code); },
    () => { sink = m.toMGRSArray(points); }, () => { sink = m.toLatLonArray(codes); }];
  const samples = [[], [], [], []];
  for (let repeat = 0; repeat < repeats; repeat++) {
    for (const op of repeat % 2 ? [3, 2, 1, 0] : [0, 1, 2, 3]) {
      const start = performance.now(); calls[op](); samples[op].push((performance.now() - start) / 1000);
    }
  }
  if (sink === undefined) throw new Error("no benchmark result");
  return {points: count, precision: 5, repeats, max_roundtrip_metres: maxError, timings: Object.fromEntries(operations.map((name, i) => {
    const elapsed = median(samples[i]); return [name, {samples_seconds: samples[i], median_seconds: elapsed, points_per_second: count / elapsed}];
  }))};
}
