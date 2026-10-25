import {readFileSync, existsSync, writeFileSync, mkdirSync} from "node:fs";
import {createHash} from "node:crypto";
import {dirname, extname} from "node:path";
import {hostname} from "node:os";
import {MGRS} from "./dist/node.js";
import {generated, parseCSV, benchmark, compare} from "./bench-core.mjs";
try {
  const args = {};
  for (let i = 2; i < process.argv.length; i += 2) {
    const key = process.argv[i];
    if (!["--points", "--seed", "--dataset", "--repeats", "--output", "--baseline", "--max-regression"].includes(key) || process.argv[i + 1] === undefined) throw new Error(`invalid option ${key}`);
    args[key] = process.argv[i + 1];
  }
  const count = Number(args["--points"] ?? 1000000), seed = Number(args["--seed"] ?? 20261022), repeats = Number(args["--repeats"] ?? 5), limit = Number(args["--max-regression"] ?? 10);
  if (!Number.isFinite(limit) || limit < 0) throw new Error("invalid regression limit");
  let bytes, points;
  if (args["--dataset"]) { bytes = readFileSync(args["--dataset"]); points = parseCSV(bytes.toString("utf8")); }
  else { points = generated(count, seed); bytes = new Uint8Array(points.length * 8); const view = new DataView(bytes.buffer); points.forEach((v, i) => view.setFloat64(i * 8, v, true)); }
  const hash = createHash("sha256").update(bytes).digest("hex");
  if (args["--dataset"]) {
    const path = args["--dataset"], manifest = path.slice(0, path.length - extname(path).length) + ".json";
    if (existsSync(manifest)) { const m = JSON.parse(readFileSync(manifest)); if (m.sha256 !== hash || m.count !== points.length / 2) throw new Error("dataset manifest mismatch"); }
  }
  const m = new MGRS(warning => { throw new Error(warning.message); });
  let report; try { report = {...benchmark(m, points, repeats), backend: "TypeScript WebAssembly GEOTRANS 3.10", runtime: process.version, platform: `${process.platform}/${process.arch}/${hostname()}`, dataset_sha256: hash, seed}; } finally { m.free(); }
  report.regression_passed = !args["--baseline"] || compare(report, JSON.parse(readFileSync(args["--baseline"])), limit);
  const output = JSON.stringify(report, null, 2) + "\n";
  if (args["--output"]) { mkdirSync(dirname(args["--output"]), {recursive: true}); writeFileSync(args["--output"], output); }
  process.stdout.write(output);
  if (!report.regression_passed) process.exitCode = 1;
} catch (error) { console.error(error.message); process.exitCode = 2; }
