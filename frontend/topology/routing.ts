import type { Cable, Observation, Point } from "./types";
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
  points = points.filter(
    (p, i) => i === 0 || p.x !== points[i - 1].x || p.y !== points[i - 1].y,
  );
  return points.filter(
    (p, i) =>
      i === 0 ||
      i === points.length - 1 ||
      !(
        (points[i - 1].x === p.x && points[i + 1].x === p.x) ||
        (points[i - 1].y === p.y && points[i + 1].y === p.y)
      ),
  );
}
/** Rectilinear visibility-grid search. Inflated card boundaries provide lanes.
 * Endpoints must already be outside their own card's inflated boundary. */
export function routeOrthogonal(
  a: Point,
  b: Point,
  obstacles: Obstacle[],
  lane: number,
): Point[] {
  const gap = 12 + (lane % 4) * 4;
  const boxes = obstacles.map((o) => ({
    left: Math.max(0, o.x - gap),
    right: o.x + o.width + gap,
    top: Math.max(0, o.y - gap),
    bottom: o.y + o.height + gap,
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
  const start = index(a),
    goal = index(b),
    cost = new Map<number, number>([[start, 0]]),
    previous = new Map<number, number>();
  const open = [start],
    closed = new Set<number>();
  while (open.length) {
    let best = 0;
    const score = (id: number) => {
      const p = point(id);
      return cost.get(id)! + Math.abs(p.x - b.x) + Math.abs(p.y - b.y);
    };
    for (let i = 1; i < open.length; i++)
      if (score(open[i]) < score(open[best])) best = i;
    const current = open.splice(best, 1)[0];
    if (current === goal) {
      const out: Point[] = [];
      let id: number | undefined = goal;
      while (id !== undefined) {
        out.push(point(id));
        id = previous.get(id);
      }
      return simplify(out.reverse());
    }
    closed.add(current);
    const x = current % xs.length,
      y = Math.floor(current / xs.length),
      p = point(current);
    const neighbors = [
      x > 0 ? current - 1 : -1,
      x < xs.length - 1 ? current + 1 : -1,
      y > 0 ? current - xs.length : -1,
      y < ys.length - 1 ? current + xs.length : -1,
    ];
    for (const next of neighbors) {
      if (next < 0 || closed.has(next)) continue;
      const q = point(next);
      if (blocked(p, q)) continue;
      const candidate =
        cost.get(current)! + Math.abs(p.x - q.x) + Math.abs(p.y - q.y);
      if (candidate < (cost.get(next) ?? Infinity)) {
        cost.set(next, candidate);
        previous.set(next, current);
        if (!open.includes(next)) open.push(next);
      }
    }
  }
  // Overlapping saved cards can enclose an endpoint. Preserve those positions;
  // a deterministic exterior lane is preferable to silently moving a device.
  const x = Math.max(a.x, b.x, ...boxes.map((o) => o.right)) + gap;
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
