/** Public Python-compatible interface. Rust owns all conversion mathematics. */
export type LatLon = [number, number];
export type UTM = [number, string, number, number];
export type DMS = [number, number, number];
export type Warning = {message: string; row?: number};
export type WarningHandler = (warning: Warning) => void;
export type MGRSInput = string | Uint8Array;

export interface EngineInterface {
  free(): void;
  warning_row(): number;
  to_mgrs(lat: number, lon: number, degrees: boolean, precision: number): string;
  to_lat_lon(code: Uint8Array, degrees: boolean): Float64Array;
  to_wkt(code: Uint8Array): string;
  mgrs_to_utm(code: Uint8Array): Float64Array;
  utm_to_mgrs(zone: number, hemisphere: string, e: number, n: number, precision: number): string;
  to_mgrs_array(points: Float64Array, degrees: boolean, precision: number): Uint8Array;
  to_lat_lon_array(codes: Uint8Array, degrees: boolean, width: number): Float64Array;
  ddtodms(dd: number): Float64Array;
  dmstodd(dms: string): number;
}

export class MGRSError extends Error {
  readonly row?: number;
  constructor(message: string) {
    super(message);
    this.name = "MGRSError";
    const row = /failed at row (\d+):/.exec(message);
    if (row) this.row = Number(row[1]);
  }
}

const encoder = new TextEncoder();
function bytes(value: MGRSInput): Uint8Array {
  if (typeof value === "string") return encoder.encode(value);
  if (value instanceof Uint8Array) return value;
  throw new TypeError("MGRS must be string or Uint8Array");
}
function precision(value: number): void {
  if (!Number.isInteger(value)) throw new TypeError("MGRSPrecision must be an integer");
  if (value < 0 || value > 5) throw new MGRSError("Precision Error: expected 0 through 5");
}
function numeric(...values: number[]): void {
  if (values.some(v => typeof v !== "number")) throw new TypeError("coordinates must be numbers");
}
function boolean(value: boolean): void {
  if (typeof value !== "boolean") throw new TypeError("inDegrees must be boolean");
}

export class BaseMGRS {
  private disposed = false;
  constructor(private readonly engine: EngineInterface,
              private readonly onWarning: WarningHandler = w => console.warn(w.message)) {}

  /** Release Wasm state explicitly. Calls after free() throw. */
  free(): void {
    if (!this.disposed) { this.engine.free(); this.disposed = true; }
  }
  private invoke<T>(operation: (engine: EngineInterface) => T, warnings = true): T {
    if (this.disposed) throw new Error("MGRS instance has been freed");
    let result: T;
    try { result = operation(this.engine); }
    catch (error) {
      if (typeof error === "string") throw new MGRSError(error);
      throw error;
    }
    const row = warnings ? this.engine.warning_row() : -1;
    if (row !== -1) this.onWarning({message: row < 0 ? "Latitude Warning" : `Latitude Warning; first affected row ${row}`, ...(row >= 0 ? {row} : {})});
    return result;
  }
  toMGRS(latitude: number, longitude: number, inDegrees = true, MGRSPrecision = 5): string {
    numeric(latitude, longitude); boolean(inDegrees); precision(MGRSPrecision);
    return this.invoke(e => e.to_mgrs(latitude, longitude, inDegrees, MGRSPrecision));
  }
  toLatLon(MGRS: MGRSInput, inDegrees = true): LatLon {
    boolean(inDegrees);
    const input = bytes(MGRS);
    const p = this.invoke(e => e.to_lat_lon(input, inDegrees));
    return [p[0]!, p[1]!];
  }
  /** Full cell as a WGS84 longitude/latitude WKT POLYGON. Curved edges are
   * sampled; antimeridian longitudes may exceed ±180. No embedded SRID. */
  toWKT(MGRS: MGRSInput): string {
    const input = bytes(MGRS);
    return this.invoke(e => e.to_wkt(input));
  }
  MGRSToUTM(MGRS: MGRSInput, encoding = "utf-8"): UTM {
    if (typeof MGRS === "string" && !["utf-8", "utf8", "ascii", "us-ascii"].includes(encoding.toLowerCase())) {
      throw new RangeError("MGRS supports UTF-8 and ASCII input encodings");
    }
    const input = bytes(MGRS);
    const p = this.invoke(e => e.mgrs_to_utm(input));
    return [p[0]!, String.fromCharCode(p[1]!), p[2]!, p[3]!];
  }
  UTMToMGRS(zone: number, hemisphere: string | Uint8Array, easting: number, northing: number, MGRSPrecision = 5): string {
    numeric(zone, easting, northing); precision(MGRSPrecision);
    if (!Number.isInteger(zone)) throw new TypeError("zone must be an integer");
    if (zone < 1 || zone > 60) throw new MGRSError("Zone Error");
    const b = bytes(hemisphere);
    if (b.length !== 1) throw new TypeError("hemisphere must be one character");
    return this.invoke(e => e.utm_to_mgrs(zone, String.fromCharCode(b[0]!), easting, northing, MGRSPrecision));
  }
  toMGRSArray(points: Float64Array, inDegrees = true, MGRSPrecision = 5): Uint8Array {
    if (!(points instanceof Float64Array)) throw new TypeError("points must be a Float64Array");
    if (points.length % 2) throw new RangeError("points must have interleaved latitude,longitude pairs");
    boolean(inDegrees); precision(MGRSPrecision);
    return this.invoke(e => e.to_mgrs_array(points, inDegrees, MGRSPrecision));
  }
  toLatLonArray(codes: Uint8Array, inDegrees = true, {width = 15}: {width?: number} = {}): Float64Array {
    if (!(codes instanceof Uint8Array)) throw new TypeError("codes must be a Uint8Array");
    if (!Number.isInteger(width)) throw new TypeError("width must be an integer");
    if (width < 1 || width > 15) throw new RangeError("width must be from 1 through 15 bytes");
    if (codes.length % width) throw new RangeError("codes length must be a multiple of width");
    boolean(inDegrees);
    return this.invoke(e => e.to_lat_lon_array(codes, inDegrees, width));
  }
  ddtodms(dd: number): DMS {
    numeric(dd);
    const p = this.invoke(e => e.ddtodms(dd), false);
    return [p[0]!, p[1]!, p[2]!];
  }
  dmstodd(dms: string): number {
    if (typeof dms !== "string") throw new TypeError("DMS must be a string");
    return this.invoke(e => e.dmstodd(dms), false);
  }
}
