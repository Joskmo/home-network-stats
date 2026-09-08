const { test } = require("node:test");
const assert = require("node:assert/strict");
// Exercise authored domain modules, never scrape generated browser source.
const ui = require("../.build/topology-domain.cjs");
test("switch insertion preserves endpoint ports and never needs an IP", () => {
  const g = {
    nodes: [
      { id: "r", x: 0, y: 0 },
      { id: "p", x: 400, y: 400 },
    ],
    links: [
      {
        id: "c",
        source: "r",
        target: "p",
        source_port: "LAN 4",
        target_port: "eth0",
      },
    ],
  };
  let i = 0;
  const out = ui.insertSwitch(g, "c", () => `new${++i}`, "Switch");
  assert.equal(out.nodes[2].ip, "");
  assert.equal(out.links.length, 2);
  assert.equal(out.links[0].source_port, "LAN 4");
  assert.equal(out.links[1].target_port, "eth0");
  assert.equal(g.links.length, 1);
  assert.throws(() =>
    ui.insertSwitch(
      { ...g, links: [{ ...g.links[0], medium: "wifi" }] },
      "c",
      () => "",
      "Switch",
    ),
  );
});
test("observations distinguish iw WiFi from forwarding paths and unknowns", () => {
  const g = {
    nodes: [
      { id: "r", type: "router" },
      { id: "w", discovery: { source: "iw", attachment: "phy0-ap0" } },
      { id: "f", discovery: { source: "fdb", attachment: "lan1" } },
      { id: "u", discovery: { source: "dhcp", attachment: null } },
    ],
    links: [],
  };
  const o = ui.observations(g);
  assert.equal(o.length, 2);
  assert.equal(o.find((l) => l.target === "w").medium, "wifi");
  assert.equal(o.find((l) => l.target === "f").medium, "via");
  assert.equal(
    ui.observations({ ...g, nodes: [...g.nodes, { id: "r2", type: "router" }] })
      .length,
    0,
  );
  assert.equal(
    ui.observations({ ...g, links: [{ source: "r", target: "w" }] }).length,
    1,
  );
});
test("layout leaves room for all explicitly configured ports", () => {
  const g = {
    nodes: [
      {
        id: "r",
        type: "router",
        ports: Array.from({ length: 48 }, (_, i) => String(i)),
      },
      { id: "p", type: "phone" },
    ],
    links: [{ source: "r", target: "p" }],
  };
  const p = ui.layout(g);
  assert.ok(p.p.y >= p.r.y + 510);
});
test("layout places router above clients deterministically without mutating stored positions", () => {
  const g = {
    nodes: [
      { id: "p", type: "phone", x: 99, y: 22 },
      { id: "r", type: "router", x: 9, y: 2 },
    ],
    links: [],
  };
  const before = JSON.stringify(g);
  const a = ui.layout(g);
  assert.ok(a.p.y > a.r.y);
  assert.deepEqual(a, ui.layout({ ...g, nodes: [...g.nodes].reverse() }));
  assert.equal(JSON.stringify(g), before);
});

test("typed transport sends latest CSRF and preserves HTTP conflict/retry metadata", async () => {
  const { createApi, HttpError } = require("../.build/http.cjs");
  const original = global.fetch;
  let request;
  let session = { csrf: "first" };
  global.fetch = async (path, options) => {
    request = { path, options };
    return new Response(JSON.stringify({ error: "conflict" }), {
      status: 409,
      headers: { "Retry-After": "12" },
    });
  };
  try {
    const api = createApi(
      () => session,
      () => "en",
      (key) => key,
    );
    session = { csrf: "rotated" };
    await assert.rejects(
      api("/api/topology", { topology: { revision: 1, nodes: [], links: [] } }),
      (error) =>
        error instanceof HttpError &&
        error.status === 409 &&
        error.code === "conflict" &&
        error.retryAfter === 12 &&
        error.message === "Retry in 12 seconds.",
    );
    assert.equal(JSON.parse(request.options.body).csrf, "rotated");
    assert.equal(request.options.method, "POST");
    global.fetch = async (path, options) => {
      request = { path, options };
      return new Response(JSON.stringify({ authenticated: false }));
    };
    assert.deepEqual(await api("/api/session"), { authenticated: false });
    assert.equal(request.options.cache, "no-store");
    assert.equal(request.options.body, undefined);
  } finally {
    global.fetch = original;
  }
});

test("orthogonal routing avoids an intervening device and keeps endpoints", () => {
  const a = { x: 30, y: 20 },
    b = { x: 300, y: 200 };
  const obstacles = [{ x: 80, y: 0, width: 120, height: 180 }];
  const points = ui.routeOrthogonal(a, b, obstacles, 0);
  assert.deepEqual(points[0], a);
  assert.deepEqual(points.at(-1), b);
  for (let i = 1; i < points.length; i++) {
    const p = points[i - 1],
      q = points[i];
    assert.ok(p.x === q.x || p.y === q.y, "orthogonal segments only");
    assert.ok(
      !(p.x === q.x
        ? p.x > 80 &&
          p.x < 200 &&
          Math.max(p.y, q.y) > 0 &&
          Math.min(p.y, q.y) < 180
        : p.y > 0 &&
          p.y < 180 &&
          Math.max(p.x, q.x) > 80 &&
          Math.min(p.x, q.x) < 200),
      "does not cross a card",
    );
  }
  assert.equal(
    ui.routeKey({ id: "c", source: "a", target: "b" }),
    '["manual","c"]',
  );
  assert.equal(
    ui.routeKey({
      source: "a",
      target: "b",
      source_port: "lan2",
      observation: true,
    }),
    '["observed","a","b","lan2",""]',
  );
});
