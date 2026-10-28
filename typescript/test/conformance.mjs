// Portable suite runs unchanged in Node and a real browser.
function equal(actual, expected, context = "") {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${context}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
}
function near(actual, expected, tolerance = 1e-9) {
  if (!(Math.abs(actual - expected) <= tolerance)) throw new Error(`${actual} != ${expected}`);
}
function throws(fn, text) {
  try { fn(); } catch (e) {
    if (!String(e).includes(text)) throw e;
    return e;
  }
  throw new Error(`Expected ${text}`);
}
const encoder = new TextEncoder();
function pack(codes, width = 15) {
  const output = new Uint8Array(codes.length * width);
  codes.forEach((code, i) => output.set(typeof code === "string" ? encoder.encode(code) : code, i * width));
  return output;
}

export function scenarios({MGRS, MGRSError}, fixture, wktFixture) {
  return {
    "GeoJSON objects preserve cell footprints and split the antimeridian"() {
      const warnings = [];
      const m = new MGRS(w => warnings.push(w));
      const area = ring => {
        const [ox, oy] = ring[0];
        return ring.slice(1).reduce((sum, b, i) => {
          const a = ring[i];
          return sum + (a[0] - ox) * (b[1] - oy) - (b[0] - ox) * (a[1] - oy);
        }, 0) / 2;
      };
      try {
        for (const {code, corners} of wktFixture.cases) {
          const geometry = m.toGeoJSON(code);
          equal(Object.keys(geometry).sort(), ["coordinates", "type"]);
          equal(JSON.parse(JSON.stringify(geometry)), geometry);
          if (!["Polygon", "MultiPolygon"].includes(geometry.type)) throw new Error(code);
          const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
          if (!polygons.length) throw new Error("Empty geometry");
          for (const polygon of polygons) {
            equal(polygon.length, 1);
            const ring = polygon[0];
            equal(ring[0], ring.at(-1));
            if (ring.length < 4 || area(ring) <= 0) throw new Error("Invalid ring");
            for (const p of ring) {
              equal(p.length, 2);
              if (!p.every(Number.isFinite) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90) throw new Error(code);
            }
            if (ring.slice(1).some((p, i) => Math.abs(p[0] - ring[i][0]) > 180)) throw new Error("Unsplit edge");
          }
          const wkt = m.toWKT(code).slice(10, -2).split(", ").map(p => p.split(" ").map(Number));
          if (wkt.every(([x]) => Math.abs(x) <= 180)) equal(geometry, {type: "Polygon", coordinates: [wkt]});
          near(polygons.reduce((sum, p) => sum + area(p[0]), 0), area(wkt), Math.max(1e-15, area(wkt) * 1e-6));
          const points = polygons.flat(2);
          for (const [lon, lat] of corners) {
            if (!points.some(([x, y]) => Math.abs(y - lat) < 1e-9 &&
              (Math.abs(lat) === 90 || Math.abs(x - lon - 360 * Math.round((x - lon) / 360)) < 1e-9))) throw new Error(`Missing corner: ${code}`);
          }
        }
        for (const code of ["01NAA", "60NZF", "01NAA6602100000"]) {
          equal(m.toGeoJSON(code).type, "MultiPolygon");
        }
        for (const code of ["ZAH", "ZAG", "YZH", "YZG", "BAN", "BAM", "AZN", "AZM"]) {
          equal(m.toGeoJSON(code).type, "Polygon");
        }
        equal(m.toGeoJSON(encoder.encode(" 15twg 00000 49776 ")), m.toGeoJSON("15TWG0000049776"));
        for (const code of ["", "invalid", "15TWG1", "32XJA", "15TWG\0", new Uint8Array([255])]) {
          if (!(throws(() => m.toGeoJSON(code), "String Error") instanceof MGRSError)) throw new Error("Wrong error type");
        }
        throws(() => m.toGeoJSON(123), "string or Uint8Array");
        const result = m.toGeoJSON("15TWG0000049776");
        result.coordinates[0][0][0] = 0;
        equal(m.toGeoJSON("15TWG0000049776").coordinates[0][0][0], -93);
        m.toGeoJSON("50TMK5045027900"); equal(warnings.length, 1);
      } finally { m.free(); }
      throws(() => m.toGeoJSON("15TWG"), "freed");
      const strict = new MGRS(() => { throw new Error("warning promoted"); });
      try {
        throws(() => strict.toGeoJSON("50TMK5045027900"), "warning promoted");
        equal(strict.toGeoJSON("15TWG").type, "Polygon");
      } finally { strict.free(); }
    },
    "WKT full cells, independent PROJ corners, poles and antimeridian"() {
      const warnings = [];
      const m = new MGRS(w => warnings.push(w));
      function ring(code) {
        const wkt = m.toWKT(code);
        if (!wkt.startsWith("POLYGON ((") || !wkt.endsWith("))")) throw new Error(wkt);
        const points = wkt.slice(10, -2).split(", ").map(p => p.split(" ").map(Number));
        equal(points[0], points.at(-1));
        const [ox, oy] = points[0];
        let area = 0;
        for (let i = 0; i < points.length - 1; i++) {
          const [x, y] = points[i], [xx, yy] = points[i + 1];
          if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(y) > 90 || Math.abs(x - xx) > 180) throw new Error(code);
          area += (x - ox) * (yy - oy) - (xx - ox) * (y - oy);
        }
        if (points.length < 5 || area <= 0) throw new Error(`Invalid ring: ${code}`);
        return points;
      }
      try {
        for (const {code, corners} of wktFixture.cases) {
          const points = ring(code);
          for (const [lon, lat] of corners) {
            if (!points.some(([x, y]) => Math.abs(y - lat) < 1e-9 &&
              (Math.abs(lat) === 90 || Math.abs(x - lon - 360 * Math.round((x - lon) / 360)) < 1e-9))) {
              throw new Error(`Missing PROJ corner: ${code} ${lon},${lat}`);
            }
          }
        }
        equal(ring("15TWG0000049776").length, 5);
        for (const code of ["01NAA", "60NZF", "01NAA6602100000"]) {
          if (!ring(code).some(([x]) => Math.abs(x) > 180)) throw new Error("Expected unwrapped longitudes");
        }
        for (const code of ["ZAH", "ZAG", "YZH", "YZG", "BAN", "BAM", "AZN", "AZM"]) {
          const lons = [...new Set(ring(code).filter(([, y]) => Math.abs(y) === 90).map(([x]) => x))];
          equal(lons.length, 2); near(Math.abs(lons[0] - lons[1]), 90);
        }
        equal(m.toWKT(encoder.encode(" \t04qej 97987\n90670\r ")), m.toWKT("04QEJ9798790670"));
        for (const code of ["", "invalid", "15TWG1", "32XJA", "15TWG\0", "15TWG\u00a0", new Uint8Array([255])]) {
          if (!(throws(() => m.toWKT(code), "String Error") instanceof MGRSError)) throw new Error("Wrong error type");
        }
        throws(() => m.toWKT(123), "string or Uint8Array");
        ring("50TMK5045027900"); equal(warnings.length, 1);
      } finally { m.free(); }
      throws(() => m.toWKT("15TWG"), "freed");
    },
    "all upstream forward strings, precisions, units and batch equivalents"() {
      const m = new MGRS();
      for (const {point: [lat, lon], codes} of fixture.forward) {
        for (let p = 0; p <= 5; ++p) for (const degrees of [true, false]) {
          const y = degrees ? lat : lat * (Math.PI / 180);
          const x = degrees ? lon : lon * (Math.PI / 180);
          equal(m.toMGRS(y, x, degrees, p), codes[p], `${lat},${lon} p=${p}`);
          equal([...m.toMGRSArray(new Float64Array([y, x]), degrees, p)], [...pack([codes[p]])]);
        }
      }
      m.free();
    },
    "all Python inverse coordinates, UTM outputs, errors and warnings"() {
      let warnings = [];
      const m = new MGRS(w => warnings.push(w));
      for (const {code, latlon, radians, utm} of fixture.inverse) {
        for (const [expected, call, tolerance] of [
          [latlon, () => m.toLatLon(code), 1e-9],
          [radians, () => m.toLatLon(code, false), 1e-9],
          [utm, () => m.MGRSToUTM(code), 1e-6]]) {
          warnings = [];
          if (expected.error) {
            const error = throws(call, expected.error);
            if (!(error instanceof MGRSError)) throw new Error("exception identity");
          } else {
            const actual = call();
            expected.value.forEach((v, i) => typeof v === "number" ? near(actual[i], v, tolerance) : equal(actual[i], v));
            equal(warnings.length, expected.warning ? 1 : 0, code);
          }
        }
      }
      m.free();
    },
    "UTM truncation boundaries"() {
      const m = new MGRS();
      for (const {point, codes} of fixture.utm) codes.forEach((code, p) => equal(m.UTMToMGRS(...point, p), code));
      m.free();
    },
    "Python doctests and DMS helpers"() {
      const m = new MGRS(() => {});
      equal(m.toMGRS(42, -93), "15TWG0000049776");
      equal(m.toLatLon("15TWG0000049776").map(v => v.toFixed(5)), ["42.00000", "-92.99999"]);
      equal(m.toLatLon("15SWC8081751205").map(v => v.toFixed(5)), ["38.40543", "-92.07439"]);
      equal(m.MGRSToUTM("15SWC8081751205"), [15, "N", 580817.5, 4251205.5]);
      equal(m.UTMToMGRS(15, "N", 580817, 4251205), "15SWC8081751205");
      for (const [code, expected] of [["50TMK5045027900", ["39.99984", "116.41952"]], ["32TNK0000000000", ["39.74991", "9.00001"]]])
        equal(m.toLatLon(code).map(v => v.toFixed(5)), expected);
      for (const [dms, dd] of [["321942N", "32.32833"], ["321942.29N", "32.32841"], ["671328.35W", "-67.22454"], ["321942.29S", "-32.32841"]])
        equal(m.dmstodd(dms).toFixed(5), dd);
      const dms = m.ddtodms(32.328414); equal([dms[0], dms[1], dms[2].toFixed(2)], [32, 19, "42.29"]);
      for (const dd of [-32.328414, -0.5, -0.001, 0, 180]) {
        const [d, mi, s] = m.ddtodms(dd);
        const sign = d < 0 || mi < 0 || s < 0 ? -1 : 1;
        near(sign * (Math.abs(d) + Math.abs(mi) / 60 + Math.abs(s) / 3600), dd);
      }
      m.free();
    },
    "issue 40 whitespace normalization across scalar and batch APIs"() {
      const m = new MGRS();
      const expected = m.toLatLon("04QEJ9798790670");
      near(expected[0], 21.61643, 1e-5); near(expected[1], -158.05325, 1e-5);
      for (const text of ["04QEJ 97987 90670", " 04QEJ9798790670", "04QEJ9798790670 ", "  04QEJ  97987  90670  ",
        "\t04QEJ\t97987\r\n90670\v\f", " ".repeat(100) + "04qej 97987 90670" + " ".repeat(100)]) {
        for (const code of [text, encoder.encode(text)]) {
          equal(m.toLatLon(code), expected);
          equal(m.MGRSToUTM(code, "ascii"), m.MGRSToUTM("04QEJ9798790670"));
        }
      }
      for (const point of [[21.61643, -158.05325], [90, 0], [-90, 0]]) for (let p = 0; p <= 5; ++p) {
        const code = m.toMGRS(...point, true, p);
        equal(m.toLatLon(" " + [...code].join(" ") + " "), m.toLatLon(code));
      }
      for (const code of [" 04QEJ ", "04QEJ 97 90", "\t04QEJ\t97\n90\r", " ZAH 00 00 "]) for (const degrees of [true, false]) {
        const expected = m.toLatLon(code, degrees);
        equal([...m.toLatLonArray(encoder.encode(code), degrees, {width: code.length})], expected);
        equal([...m.toLatLonArray(pack([code]), degrees)], expected);
      }
      m.free();
    },
    "invalid scalar inputs and numerical ranges"() {
      const m = new MGRS();
      for (const code of ["", "nonsense", new Uint8Array([255]), "é", "999999999999999", "2147483648AAA", "123NEA", "000NEA"]) {
        throws(() => m.toLatLon(code), "String Error");
        throws(() => m.MGRSToUTM(code), "String Error");
      }
      for (const lat of [NaN, Infinity, -91, 91]) throws(() => m.toMGRS(lat, 0), "Latitude Error");
      for (const lon of [NaN, Infinity, -181, 361]) throws(() => m.toMGRS(0, lon), "Longitude Error");
      for (const p of [-1, 6, 2 ** 100]) throws(() => m.toMGRS(42, -93, true, p), "Precision Error");
      throws(() => m.toMGRS(42, -93, true, 1.5), "integer");
      throws(() => m.UTMToMGRS(15, "N", NaN, 4000000), "Easting Error");
      throws(() => m.UTMToMGRS(15, "X", 500000, 4000000), "Hemisphere Error");
      throws(() => m.UTMToMGRS(15, "North", 500000, 4000000), "one character");
      throws(() => m.UTMToMGRS(2 ** 40, "N", 500000, 4000000), "Zone Error");
      throws(() => m.toLatLon(5), "string or Uint8Array");
      throws(() => m.toMGRS("42", -93), "numbers");
      throws(() => m.toMGRS(42, -93, "yes"), "boolean");
      m.free();
    },
    "typed buffers, views, ownership, width, layout and empty input"() {
      const m = new MGRS();
      const owner = new Float64Array([0, 0, 42, -93]);
      const codes = m.toMGRSArray(owner.subarray(2));
      equal([...codes], [...pack(["15TWG0000049776"])]);
      owner.fill(NaN); equal([...codes], [...pack(["15TWG0000049776"])]);
      const backing = encoder.encode("x15TWG0000049776y");
      equal([...m.toLatLonArray(backing.subarray(1, -1))], m.toLatLon("15TWG0000049776"));
      for (const code of ["15TWG", "15TWG0000049776", "31NEA0000000000"])
        equal([...m.toLatLonArray(encoder.encode(code), true, {width: code.length})], m.toLatLon(code));
      equal([...m.toMGRSArray(new Float64Array())], []); equal([...m.toLatLonArray(new Uint8Array())], []);
      for (const bad of [[], new Float32Array(), new Uint8Array(), new DataView(new ArrayBuffer(8))]) throws(() => m.toMGRSArray(bad), "Float64Array");
      for (const bad of ["15TWG", [], new Float64Array()]) throws(() => m.toLatLonArray(bad), "Uint8Array");
      throws(() => m.toMGRSArray(new Float64Array([42])), "pairs");
      throws(() => m.toLatLonArray(encoder.encode("15TWG")), "multiple of width");
      for (const width of [0, 16, 2 ** 100]) throws(() => m.toLatLonArray(new Uint8Array(), true, {width}), "width");
      throws(() => m.toLatLonArray(new Uint8Array(), true, {width: 1.5}), "integer");
      m.free();
    },
    "batch failures identify the first row and preserve inputs"() {
      const m = new MGRS();
      for (const code of ["", "nonsense", new Uint8Array([255, 65]), "04QEJ12garbage", "04QEJ12\0junk", "04QEJ12\0 34", " \t\n "]) {
        const input = pack(["15TWG0000049776", code]); const saved = input.slice();
        const error = throws(() => m.toLatLonArray(input), "row 1: String Error"); equal(error.row, 1); equal([...input], [...saved]);
      }
      for (const bad of [NaN, Infinity, -91, 91]) throws(() => m.toMGRSArray(new Float64Array([42, -93, bad, 0])), "row 1: Latitude Error");
      for (const bad of [NaN, Infinity, -181, 361]) throws(() => m.toMGRSArray(new Float64Array([42, -93, 0, bad])), "row 1: Longitude Error");
      m.free();
    },
    "warning callbacks preserve values and may throw"() {
      const warnings = []; const m = new MGRS(w => warnings.push(w));
      const input = pack(["15TWG0000049776", "50TMK5045027900"]);
      const points = m.toLatLonArray(input);
      equal(warnings.length, 1); equal(warnings[0].row, 1);
      equal([...points], [...m.toLatLon("15TWG0000049776"), ...m.toLatLon("50TMK5045027900")]);
      const throwing = new MGRS(() => { throw new Error("warning as error"); });
      throws(() => throwing.toLatLonArray(input), "warning as error");
      equal(throwing.toMGRS(42, -93), "15TWG0000049776");
      m.free(); throwing.free();
    },
    "multiple instances and explicit disposal"() {
      const a = new MGRS(), b = new MGRS();
      for (let i = 0; i < 100; ++i) equal(a.toMGRS(42, -93), b.toMGRS(42, -93));
      a.free(); a.free(); throws(() => a.toMGRS(42, -93), "freed");
      equal(b.toMGRS(42, -93), "15TWG0000049776"); b.free();
    },
  };
}
