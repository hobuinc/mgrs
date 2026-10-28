import {createRequire} from "node:module";
import {BaseMGRS, type EngineInterface, type WarningHandler} from "./common.js";
export {MGRSError} from "./common.js";
export type {LatLon, UTM, DMS, Warning, WarningHandler, MGRSInput, CellGeometry} from "./common.js";
const require = createRequire(import.meta.url);
const {Engine} = require("../wasm/node/mgrs.cjs") as {Engine: new () => EngineInterface};

/** Synchronous Node.js interface, backed by the Rust WebAssembly engine. */
export class MGRS extends BaseMGRS {
  constructor(onWarning?: WarningHandler) { super(new Engine(), onWarning); }
}
