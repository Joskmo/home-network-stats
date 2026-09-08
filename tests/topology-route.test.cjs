const assert = require("node:assert/strict");
const { test } = require("node:test");
const { buildSync } = require("esbuild");
const { resolve } = require("node:path");
const compiled = buildSync({
  entryPoints: [resolve(__dirname, "../frontend/topology/routing.ts")],
  bundle: true,
  platform: "node",
  format: "cjs",
  write: false,
}).outputFiles[0].text;
const routing = { exports: {} };
new Function("module", "exports", compiled)(routing, routing.exports);
const { throughWaypoints, pathData } = routing.exports;
test("duplicate consecutive waypoints preserve the orthogonal corner and SVG path", () => {
  const points = throughWaypoints({ x: 0, y: 0 }, { x: 10, y: 20 }, [
    { x: 0, y: 10 },
    { x: 0, y: 10 },
  ]);
  assert.ok(
    points.slice(1).every((p, i) => p.x === points[i].x || p.y === points[i].y),
    "no diagonal segments",
  );
  assert.deepEqual(points, [
    { x: 0, y: 0 },
    { x: 0, y: 10 },
    { x: 10, y: 10 },
    { x: 10, y: 20 },
  ]);
  assert.equal(pathData(points), "M0 0 V10 H10 V20");
});
