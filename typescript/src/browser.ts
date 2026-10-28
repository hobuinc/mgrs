import initWasm, {Engine} from "../wasm/web/mgrs.js";
import {BaseMGRS, type WarningHandler} from "./common.js";
export {MGRSError} from "./common.js";
export type {LatLon, UTM, DMS, Warning, WarningHandler, MGRSInput, CellGeometry} from "./common.js";
let initialized = false;
// Keep the public declarations independent of the generated Engine and its
// optional Symbol.dispose support. Browser consumers need only standard DOM types.
export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

/** Initialize once before constructing MGRS. Accepts a URL, bytes, or module. */
export async function init(input?: InitInput | Promise<InitInput>): Promise<void> {
  await initWasm(input === undefined ? undefined : {module_or_path: input});
  initialized = true;
}
export default init;
export class MGRS extends BaseMGRS {
  constructor(onWarning?: WarningHandler) {
    if (!initialized) throw new Error("Call and await init() before creating MGRS");
    super(new Engine(), onWarning);
  }
}
