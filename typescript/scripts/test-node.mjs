// Expand test paths here so npm test also works in Windows cmd.exe.
import {readdirSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
const tests = readdirSync(new URL("../test/", import.meta.url))
  .filter(name => name.endsWith(".test.mjs")).sort().map(name => `test/${name}`);
if (!tests.length) throw new Error("No Node tests found");
const result = spawnSync(process.execPath, ["--test", ...tests], {cwd: root, stdio: "inherit"});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
