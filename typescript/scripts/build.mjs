import {spawnSync} from "node:child_process";
import {copyFileSync, mkdirSync, renameSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {resolve} from "node:path";

const root = fileURLToPath(new URL("../../", import.meta.url));
function run(command, args) {
  const result = spawnSync(command, args, {cwd: root, stdio: "inherit"});
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
run("cargo", ["build", "--locked", "--release", "--target", "wasm32-unknown-unknown", "--features", "wasm", "--lib"]);
const target = process.env.CARGO_TARGET_DIR ? resolve(root, process.env.CARGO_TARGET_DIR) : resolve(root, "target");
for (const [targetName, directory] of [["web", "web"], ["nodejs", "node"]]) {
  const out = resolve(root, "typescript/wasm", directory);
  mkdirSync(out, {recursive: true});
  run("wasm-bindgen", ["--target", targetName, "--out-name", "mgrs", "--out-dir", out,
    resolve(target, "wasm32-unknown-unknown/release/mgrs.wasm")]);
  if (directory === "node") renameSync(resolve(out, "mgrs.js"), resolve(out, "mgrs.cjs"));
}
for (const file of ["LICENSE", "NOTICE"]) copyFileSync(resolve(root, file === "NOTICE" ? "rust/NOTICE" : file), resolve(root, "typescript", file));
run(process.execPath, [resolve(root, "typescript/node_modules/typescript/bin/tsc"), "--project", resolve(root, "typescript/tsconfig.json")]);
