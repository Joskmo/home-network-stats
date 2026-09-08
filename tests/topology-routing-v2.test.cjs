const { test } = require("node:test");
const assert = require("node:assert/strict");
const { buildSync } = require("esbuild");
const path = require("node:path");
function load(file) {
  const text = buildSync({
    entryPoints: [
      path.resolve(__dirname, "../frontend/topology/" + file + ".ts"),
    ],
    bundle: true,
    platform: "node",
    format: "cjs",
    write: false,
  }).outputFiles[0].text;
  const module = { exports: {} };
  new Function("module", "exports", text)(module, module.exports);
  return module.exports;
}
const geometry = load("geometry"),
  routing = load("routing"),
  { layout } = load("layout");
const node = (id, type = "desktop", ports = []) => ({
  id,
  name: id,
  type,
  ports,
  x: 0,
  y: 0,
  ip: "",
  mac: "",
});
const fixture = () => ({
  revision: 1,
  nodes: [
    node("r", "router", ["lan1", "lan2", "lan3", "lan4"]),
    ...["z", "a", "y", "b"].map((id) => node(id)),
  ],
  links: ["z", "a", "y", "b"].map((id, i) => ({
    id: "c" + i,
    source: "r",
    target: id,
    source_port: "lan" + (i + 1),
    target_port: "",
  })),
});
test("four-client regression: unknown endpoints face their upstream router, never the client bottom", () => {
  const graph = fixture(),
    positions = layout(graph);
  for (const link of graph.links) {
    const p = geometry.anchor(
      positions[link.target],
      [],
      undefined,
      positions[link.source],
    );
    assert.equal(
      p.y,
      positions[link.target].y,
      "unknown client must receive its cable on TOP",
    );
  }
});
test("auto layout orders siblings by natural parent socket order, not client IDs", () => {
  const graph = fixture(),
    p = layout(graph);
  assert.deepEqual(
    graph.nodes
      .filter((n) => n.id !== "r")
      .sort((a, b) => p[a.id].x - p[b.id].x)
      .map((n) => n.id),
    ["z", "a", "y", "b"],
  );
});
test("named incoming bank is TOP even when a downstream node is the cable source", () => {
  assert.equal(
    typeof geometry.portPlans,
    "function",
    "shared typed geometry plan is available",
  );
  const graph = {
    revision: 1,
    nodes: [
      node("r", "router", ["lan2"]),
      node(
        "s",
        "switch",
        Array.from({ length: 48 }, (_, i) => String(i + 1)),
      ),
    ],
    links: [
      {
        id: "reverse",
        source: "s",
        target: "r",
        source_port: "1",
        target_port: "lan2",
      },
    ],
  };
  const plans = geometry.portPlans(graph);
  assert.equal(plans.s.ports.find((p) => p.label === "1").side, "top");
  assert.equal(plans.r.ports[0].side, "bottom");
  assert.equal(plans.s.ports.length, 48);
  for (const p of plans.s.ports)
    assert.ok(
      p.x >= 0 && p.x + 50 <= 208 && p.y >= 0 && p.y + 22 <= plans.s.height,
    );
  assert.ok(plans.s.headerTop >= 30);
});
test("full automatic polyline avoids obstacles and has no retracing tails", () => {
  const graph = {
    revision: 1,
    nodes: [node("r", "router", ["lan1"]), node("c"), node("obstacle")],
    links: [
      {
        id: "cable",
        source: "r",
        target: "c",
        source_port: "lan1",
        target_port: "",
      },
    ],
  };
  const plans = geometry.portPlans(graph),
    positions = {
      r: { x: 100, y: 100 },
      c: { x: 100, y: 700 },
      obstacle: { x: 100, y: 400 },
    };
  const a = geometry.endpoint(positions.r, plans.r, "lan1", { x: 204, y: 757 });
  const b = geometry.endpoint(positions.c, plans.c, undefined, {
    x: 204,
    y: 183,
  });
  const obstacles = graph.nodes.map((n) => ({
    ...positions[n.id],
    width: 208,
    height: plans[n.id].height,
  }));
  const points = routing.routeCable(a, b, obstacles, 0);
  assert.deepEqual(points[0], a.point);
  assert.deepEqual(points.at(-1), b.point);
  for (let i = 1; i < points.length; i++) {
    const p = points[i - 1],
      q = points[i];
    assert.ok(p.x === q.x || p.y === q.y);
    assert.ok(
      !(p.x === q.x
        ? p.x > 100 &&
          p.x < 308 &&
          Math.max(p.y, q.y) > 400 &&
          Math.min(p.y, q.y) < 514
        : p.y > 400 &&
          p.y < 514 &&
          Math.max(p.x, q.x) > 100 &&
          Math.min(p.x, q.x) < 308),
      "no obstacle crossing",
    );
    if (i > 1) {
      const a = points[i - 2];
      assert.ok(
        (p.x - a.x) * (q.x - p.x) + (p.y - a.y) * (q.y - p.y) >= 0,
        "no opposite collinear tails",
      );
    }
  }
  assert.deepEqual(
    points,
    routing.routeCable(a, b, obstacles, 0),
    "deterministic",
  );
});
test("unknown endpoints face all four card boundaries without inventing port names", () => {
  const plan = geometry.portPlans({
    revision: 1,
    nodes: [node("c")],
    links: [],
  }).c;
  for (const [side, toward] of Object.entries({
    top: { x: 204, y: 0 },
    bottom: { x: 204, y: 500 },
    left: { x: 0, y: 157 },
    right: { x: 500, y: 157 },
  })) {
    const e = geometry.endpoint({ x: 100, y: 100 }, plan, undefined, toward);
    assert.equal(e.side, side);
    assert.equal(e.unknown, true);
    assert.equal(plan.ports.length, 0);
  }
});
test("route keys and saved waypoint data retain their original contract", () => {
  assert.equal(routing.routeKey({ id: "c" }), '["manual","c"]');
  assert.equal(
    routing.routeKey({
      observation: true,
      source: "r",
      target: "c",
      source_port: "lan2",
    }),
    '["observed","r","c","lan2",""]',
  );
  const waypoints = [
      { x: 0, y: 0 },
      { x: 32768, y: 0 },
      { x: 32768, y: 32768 },
    ],
    before = JSON.stringify(waypoints);
  const points = routing.throughWaypoints(
    { x: 0, y: 20 },
    { x: 300, y: 32768 },
    waypoints,
  );
  assert.equal(JSON.stringify(waypoints), before);
  assert.ok(
    points.every((p) => p.x >= 0 && p.x <= 32768 && p.y >= 0 && p.y <= 32768),
  );
});
