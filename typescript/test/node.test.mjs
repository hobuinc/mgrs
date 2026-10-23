import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Worker} from "node:worker_threads";
import * as api from "../dist/node.js";
import {scenarios} from "./conformance.mjs";
const fixture = JSON.parse(readFileSync(new URL("../../rust/tests/fixtures/geotrans310.json", import.meta.url)));
for (const [name, run] of Object.entries(scenarios(api, fixture))) test(name, run);
test("Node workers independently instantiate the Wasm engine", async () => {
  const results = await Promise.all(Array.from({length: 4}, () => new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./worker.mjs", import.meta.url));
    worker.on("message", resolve); worker.on("error", reject);
    worker.on("exit", code => { if (code !== 0) reject(new Error(`worker exit ${code}`)); });
  })));
  assert.deepEqual(results, Array(4).fill("15TWG0000049776"));
});
