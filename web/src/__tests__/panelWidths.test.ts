// Tailwind only builds classes written out in the source. A panel width given as "w-[24rem]" and turned into
// "md:w-[24rem]" at run time has no CSS, so on a desk screen the panel takes the full width and hides the map.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : files(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

describe("panel widths", () => {
  it("are written as md:w-[...] classes Tailwind can find", () => {
    const bare: string[] = [];
    for (const path of files(join(__dirname, ".."))) {
      const text = readFileSync(path, "utf8");
      for (const m of text.matchAll(/width\s*=\s*"(w-\[[^"]*)"/g)) bare.push(`${path}: ${m[1]}`);
    }
    expect(bare).toEqual([]);
  });
});
