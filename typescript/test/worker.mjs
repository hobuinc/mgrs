import {parentPort} from "node:worker_threads";
import {MGRS} from "../dist/node.js";
const m = new MGRS();
for (let i = 0; i < 1000; ++i) m.toMGRS(42, -93);
parentPort.postMessage(m.toMGRS(42, -93));
m.free();
