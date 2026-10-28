import {createServer} from "node:http";
import {readFile} from "node:fs/promises";
import {resolve, extname} from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";
const measure = process.argv.includes("--benchmark");
const options = {};
for (let i = 2; i < process.argv.length; i++) {
  const key = process.argv[i];
  if (key === "--benchmark") continue;
  if (!["--points", "--seed", "--repeats"].includes(key) || !process.argv[i + 1]) throw new Error(`invalid option ${key}`);
  options[key.slice(2)] = Number(process.argv[++i]);
}
const root = fileURLToPath(new URL("../../", import.meta.url));
const server = createServer(async (req, res) => {
  const file = resolve(root, "." + new URL(req.url, "http://localhost").pathname);
  if (!file.startsWith(root)) { res.writeHead(403).end(); return; }
  try {
    res.setHeader("Content-Type", {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".json": "application/json"}[extname(file)] ?? "text/html");
    res.end(file === resolve(root, "index.html") ? "<!doctype html><title>MGRS browser tests</title>" : await readFile(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({headless: true});
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}/index.html`);
  const results = await page.evaluate(async ({measure, options}) => {
    const api = await import("/typescript/dist/browser.js");
    let rejected = false; try { new api.MGRS(); } catch { rejected = true; }
    if (!rejected) throw new Error("construction before init must fail");
    await api.init();
    const {scenarios} = await import("/typescript/test/conformance.mjs");
    const fixtures = await (await fetch("/rust/tests/fixtures/geotrans310.json")).json();
    const wktFixture = await (await fetch("/rust/tests/fixtures/wkt.json")).json();
    const passed = [];
    for (const [name, run] of Object.entries(scenarios(api, fixtures, wktFixture))) { run(); passed.push(name); }
    await Promise.all(Array.from({length: 4}, () => new Promise((resolve, reject) => {
      const worker = new Worker("/typescript/test/browser-worker.mjs", {type: "module"});
      worker.onmessage = ({data}) => { worker.terminate(); data === "15TWG0000049776" ? resolve() : reject(new Error(String(data))); };
      worker.onerror = error => { worker.terminate(); reject(new Error(error.message)); };
      worker.postMessage("run");
    })));
    passed.push("browser workers independently initialize and convert");
    const report = {browser: navigator.userAgent, passed: passed.length, tests: passed};
    if (measure) {
      const {benchmark, generated} = await import("/typescript/bench-core.mjs");
      const points = generated(options.points ?? 1000000, options.seed ?? 20261022);
      const bytes = new Uint8Array(points.length * 8), view = new DataView(bytes.buffer);
      points.forEach((value, i) => view.setFloat64(i * 8, value, true));
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(v => v.toString(16).padStart(2, "0")).join("");
      const m = new api.MGRS(w => { throw new Error(w.message); });
      try { report.benchmark = {...benchmark(m, points, options.repeats ?? 5), dataset_sha256: hash, backend: "Browser WebAssembly GEOTRANS 3.10", seed: options.seed ?? 20261022}; }
      finally { m.free(); }
    }
    return report;
  }, {measure, options});
  console.log(JSON.stringify(results, null, 2));
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
