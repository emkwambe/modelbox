/**
 * Loads an emitted Cube.js schema file and dumps its real structure as JSON.
 *
 * The harness asserts on Cube *semantics* (does a measure aggregate a key
 * column? is a BOOLEAN typed as boolean?), and regex-matching generated
 * JavaScript is the kind of string assertion this whole harness exists to
 * replace. Instead the file is executed with a `cube()` shim, so the assertions
 * run against the object Cube itself would receive.
 *
 * Executing the file is also the parse check: a syntax error throws here.
 *
 * Usage:  node _cube_inspect.mjs <file.js> [<file.js> ...]
 * Output: JSON array of { file, name, ...definition } on stdout.
 */
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import { createContext, runInContext } from 'node:vm';

/**
 * Cube evaluates a join's `sql` as a template literal at load time, against
 * globals it injects: `CUBE` for the current cube and one per referenced cube
 * (`${CUBE}.customer_sk = ${DimCustomer}.customer_sk`). A plain sandbox throws
 * `ReferenceError: CUBE is not defined`, so unknown identifiers resolve to a
 * token that stringifies to their own name — which is what Cube substitutes.
 */
function withCubeGlobals(base) {
  return new Proxy(base, {
    has: () => true,
    get(target, key) {
      if (key in target) return target[key];
      if (typeof key === 'symbol') return undefined;
      return { toString: () => String(key) };
    },
  });
}

const results = [];
for (const file of process.argv.slice(2)) {
  const captured = [];
  // `cube(name, def)` is a Cube.js global. Shim it and run the file in a
  // sandbox so the emitted code needs no Cube runtime and cannot touch us.
  const sandbox = withCubeGlobals({
    cube: (name, definition) => captured.push({ name, ...definition }),
  });
  createContext(sandbox);
  try {
    runInContext(readFileSync(file, 'utf8'), sandbox, { filename: basename(file) });
  } catch (err) {
    results.push({ file: basename(file), error: `${err.name}: ${err.message}` });
    continue;
  }
  for (const c of captured) results.push({ file: basename(file), ...c });
}
process.stdout.write(JSON.stringify(results, null, 2));
