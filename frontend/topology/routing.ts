import type { Cable, Observation, Point } from "./types";
import type { Endpoint } from "./geometry";
export interface Obstacle extends Point {
  width: number;
  height: number;
}
export function routeKey(edge: Cable | Observation): string {
  return JSON.stringify(
    edge.observation
      ? [
          "observed",
          edge.source,
          edge.target,
          edge.source_port || "",
          edge.target_port || "",
        ]
      : ["manual", edge.id],
  );
}
export function pathData(points: Point[]): string {
  return points
    .map((p, i) =>
      i ? (points[i - 1].x === p.x ? `V${p.y}` : `H${p.x}`) : `M${p.x} ${p.y}`,
    )
    .join(" ");
}
export function simplify(points: Point[]): Point[] {
  const out: Point[] = [];
  for (const p of points) {
    while (out.length > 1) {
      const a = out[out.length - 2],
        b = out[out.length - 1];
      if ((a.x === b.x && b.x === p.x) || (a.y === b.y && b.y === p.y))
        out.pop();
      else break;
    }
    const last = out[out.length - 1];
    if (!last || last.x !== p.x || last.y !== p.y) out.push(p);
  }
  return out;
}
const direction = (a: Point, b: Point): number =>
  a.x === b.x ? (b.y > a.y ? 3 : 2) : b.x > a.x ? 1 : 0;
const opposite = (a: number, b: number): boolean => (a ^ 1) === b;
function crosses(p: Point, q: Point, o: Obstacle, gap = 0): boolean {
  return p.x === q.x
    ? p.x > o.x - gap &&
        p.x < o.x + o.width + gap &&
        Math.max(p.y, q.y) > o.y - gap &&
        Math.min(p.y, q.y) < o.y + o.height + gap
    : p.y > o.y - gap &&
        p.y < o.y + o.height + gap &&
        Math.max(p.x, q.x) > o.x - gap &&
        Math.min(p.x, q.x) < o.x + o.width + gap;
}
/** One complete polyline, including the socket escapes, is normalized once. */
export function routeCable(
  a: Endpoint,
  b: Endpoint,
  obstacles: Obstacle[],
  lane: number,
): Point[] {
  const start = a.escape[a.escape.length - 1],
    end = b.escape[b.escape.length - 1];
  const startDir = direction(a.escape[a.escape.length - 2], start);
  const endDir = direction(end, b.escape[b.escape.length - 2]);
  const join = (middle: Point[]) =>
    simplify([...a.escape, ...middle, ...[...b.escape].reverse()]);
  const candidates = [
    simplify([start, { x: end.x, y: start.y }, end]),
    simplify([start, { x: start.x, y: end.y }, end]),
  ];
  for (const points of candidates) {
    if (points.length < 2) return join(points);
    if (
      opposite(startDir, direction(points[0], points[1])) ||
      opposite(direction(points[points.length - 2], end), endDir)
    )
      continue;
    if (
      points
        .slice(1)
        .every((p, i) => !obstacles.some((o) => crosses(points[i], p, o, 12)))
    )
      return join(points);
  }
  return join(routeOrthogonal(start, end, obstacles, lane, startDir, endDir));
}
/** Rectilinear visibility-grid search. Inflated card boundaries provide lanes.
 * Endpoints must already be outside their own card's inflated boundary. */
export function routeOrthogonal(
  a: Point,
  b: Point,
  obstacles: Obstacle[],
  lane: number,
  startDirection = -1,
  endDirection = -1,
): Point[] {
  const gap = 12 + (lane % 4) * 4;
  const boxes = obstacles.map((o) => ({
    left: Math.max(0, o.x - gap),
    right: Math.min(32768, o.x + o.width + gap),
    top: Math.max(0, o.y - gap),
    bottom: Math.min(32768, o.y + o.height + gap),
  }));
  const xs = [
    ...new Set([a.x, b.x, 0, ...boxes.flatMap((o) => [o.left, o.right])]),
  ].sort((x, y) => x - y);
  const ys = [
    ...new Set([a.y, b.y, 0, ...boxes.flatMap((o) => [o.top, o.bottom])]),
  ].sort((x, y) => x - y);
  const point = (id: number): Point => ({
    x: xs[id % xs.length],
    y: ys[Math.floor(id / xs.length)],
  });
  const index = (p: Point) => ys.indexOf(p.y) * xs.length + xs.indexOf(p.x);
  const blocked = (p: Point, q: Point) =>
    boxes.some((o) =>
      p.x === q.x
        ? p.x > o.left &&
          p.x < o.right &&
          Math.max(p.y, q.y) > o.top &&
          Math.min(p.y, q.y) < o.bottom
        : p.y > o.top &&
          p.y < o.bottom &&
          Math.max(p.x, q.x) > o.left &&
          Math.min(p.x, q.x) < o.right,
    );
  const start = index(a) * 5 + (startDirection < 0 ? 4 : startDirection),
    goal = index(b),
    cost = new Map<number, number>([[start, 0]]),
    previous = new Map<number, number>();
  const open = [start],
    closed = new Set<number>();
  while (open.length) {
    let best = 0;
    const score = (id: number) => {
      const p = point(Math.floor(id / 5));
      return cost.get(id)! + Math.abs(p.x - b.x) + Math.abs(p.y - b.y);
    };
    for (let i = 1; i < open.length; i++)
      if (score(open[i]) < score(open[best])) best = i;
    const current = open.splice(best, 1)[0];
    const cell = Math.floor(current / 5),
      incoming = current % 5;
    if (
      cell === goal &&
      (endDirection < 0 || !opposite(incoming, endDirection))
    ) {
      const out: Point[] = [];
      let id: number | undefined = current;
      while (id !== undefined) {
        out.push(point(Math.floor(id / 5)));
        id = previous.get(id);
      }
      return simplify(out.reverse());
    }
    closed.add(current);
    const x = cell % xs.length,
      y = Math.floor(cell / xs.length),
      p = point(cell);
    const neighbors = [
      x > 0 ? cell - 1 : -1,
      x < xs.length - 1 ? cell + 1 : -1,
      y > 0 ? cell - xs.length : -1,
      y < ys.length - 1 ? cell + xs.length : -1,
    ];
    for (const neighbor of neighbors) {
      if (neighbor < 0) continue;
      const q = point(neighbor),
        dir = direction(p, q),
        next = neighbor * 5 + dir;
      if (closed.has(next) || opposite(incoming, dir)) continue;
      if (blocked(p, q)) continue;
      const candidate =
        cost.get(current)! +
        Math.abs(p.x - q.x) +
        Math.abs(p.y - q.y) +
        (incoming < 4 && incoming !== dir ? 24 : 0);
      if (candidate < (cost.get(next) ?? Infinity)) {
        cost.set(next, candidate);
        previous.set(next, current);
        if (!open.includes(next)) open.push(next);
      }
    }
  }
  // Overlapping saved cards can enclose an endpoint. Preserve those positions;
  // a deterministic exterior lane is preferable to silently moving a device.
  const x = Math.min(
    32768,
    Math.max(a.x, b.x, ...boxes.map((o) => o.right)) + gap,
  );
  return [a, { x, y: a.y }, { x, y: b.y }, b];
}
export function throughWaypoints(
  a: Point,
  b: Point,
  waypoints: Point[],
): Point[] {
  const out: Point[] = [a];
  for (const p of [...waypoints, b]) {
    const last = out[out.length - 1];
    if (last.x !== p.x && last.y !== p.y) out.push({ x: p.x, y: last.y });
    out.push(p);
  }
  return simplify(out);
}
