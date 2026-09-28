#!/usr/bin/env node
// Execute the actual BE UNLIMITED TypeScript scene sources in an isolated
// CommonJS compilation directory. Never consume stale public build output.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const beRoot = path.resolve(process.argv[2] ?? "../BE-UNLIMITED/be-unlimited");
const sourceDir = path.join(beRoot, "src", "simulator");
const require = createRequire(path.join(beRoot, "package.json"));
const ts = require("typescript");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "be-map-ts-"));
try {
  for (const stem of ["bedroom-data", "soft-props", "scene"]) {
    const input = fs.readFileSync(path.join(sourceDir, `${stem}.ts`), "utf8");
    const output = ts.transpileModule(input, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      fileName: `${stem}.ts`,
      reportDiagnostics: true,
    });
    if (output.diagnostics?.length) throw new Error(`${stem}: TypeScript transpilation failed`);
    fs.writeFileSync(path.join(temp, `${stem}.js`), output.outputText);
  }
  const scene = createRequire(path.join(temp, "entry.js"))(path.join(temp, "scene.js"));
  const bedroom = createRequire(path.join(temp, "entry.js"))(path.join(temp, "bedroom-data.js"));
  const records = scene.SIMULATOR_ENVIRONMENTS.map((id) => ({
    id,
    xmlFragment: id === "bedroom" ? null : scene.sceneXml(id),
    geometry: id === "bedroom" ? [] : scene.sceneGeometry(id),
    props: id === "bedroom" ? [] : scene.sceneProps(id),
    spawn: id === "bedroom" ? bedroom.bedroomData.spawn : null,
  }));
  process.stdout.write(JSON.stringify(records));
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
