import type { Graph, NetworkNode, Point } from "./types";
import { knownPorts, observations } from "./observations";

export const CARD_WIDTH = 208;
export const PORT_COLUMNS = 4;
export const PORT_STEP = 52;
export const PORT_TOP = 120;
export const PORT_ROW = 30;
export const PORT_HEIGHT = 22;
export type Side = "top" | "bottom" | "left" | "right";
export interface PortGeometry extends Point {
  label: string;
  side: "top" | "bottom";
}
export interface CardGeometry {
  ports: PortGeometry[];
  height: number;
  headerTop: number;
  bottomTop: number;
}
export interface Endpoint {
  point: Point;
  side: Side;
  /** Local socket escape, including the visual anchor and exterior point. */
  escape: Point[];
  unknown: boolean;
}
export const naturalOrder = (a: string, b: string): number =>
  a.localeCompare(b, "en", { numeric: true }) || a.localeCompare(b);
export const nodeRank = (n: NetworkNode): number =>
  n.type === "router" ? 0 : n.type === "switch" || n.type === "ap" ? 1 : 2;
/** Cables are undirected physical connections; source is not upstream. */
export function topologyDepths(graph: Graph): Map<string, number> {
  const nodes = [...graph.nodes].sort(
    (a, b) => nodeRank(a) - nodeRank(b) || naturalOrder(a.id, b.id),
  );
  const roots = nodes.filter((n) => n.type === "router");
  const queue = (roots.length ? roots : nodes.slice(0, 1)).map((n) => n.id);
  const depth = new Map(queue.map((id) => [id, 0]));
  const edges = [...graph.links, ...observations(graph)].filter(
    (l) => l.medium !== "wifi",
  );
  for (let i = 0; i < queue.length; i++) {
    const current = queue[i];
    const neighbors = edges
      .flatMap((l) =>
        l.source === current
          ? [l.target]
          : l.target === current
            ? [l.source]
            : [],
      )
      .sort(naturalOrder);
    for (const id of neighbors)
      if (!depth.has(id)) {
        depth.set(id, depth.get(current)! + 1);
        queue.push(id);
      }
  }
  return depth;
}
export function portPlans(graph: Graph): Record<string, CardGeometry> {
  const depths = topologyDepths(graph);
  const edges = [...graph.links, ...observations(graph)].filter(
    (l) => l.medium !== "wifi",
  );
  return Object.fromEntries(
    graph.nodes.map((n) => {
      const incoming = new Set<string>();
      for (const l of edges) {
        const other =
          l.source === n.id
            ? l.target
            : l.target === n.id
              ? l.source
              : undefined;
        if (
          other &&
          (depths.get(other) ?? Infinity) < (depths.get(n.id) ?? Infinity)
        ) {
          const port = l.source === n.id ? l.source_port : l.target_port;
          if (port) incoming.add(port);
        }
      }
      const labels = knownPorts(graph, n).sort(naturalOrder);
      const top = labels.filter((p) => incoming.has(p));
      const bottom = labels.filter((p) => !incoming.has(p));
      const headerTop = Math.ceil(top.length / PORT_COLUMNS) * PORT_ROW;
      const bottomTop = headerTop + PORT_TOP;
      const ports: PortGeometry[] = [
        ...top.map((label, i) => ({
          label,
          side: "top" as const,
          x: (i % PORT_COLUMNS) * PORT_STEP,
          y: Math.floor(i / PORT_COLUMNS) * PORT_ROW,
        })),
        ...bottom.map((label, i) => ({
          label,
          side: "bottom" as const,
          x: (i % PORT_COLUMNS) * PORT_STEP,
          y: bottomTop + Math.floor(i / PORT_COLUMNS) * PORT_ROW,
        })),
      ];
      return [
        n.id,
        {
          ports,
          headerTop,
          bottomTop,
          height: bottom.length
            ? bottomTop +
              Math.ceil(bottom.length / PORT_COLUMNS) * PORT_ROW +
              16
            : headerTop + 114,
        },
      ];
    }),
  );
}
export function endpoint(
  position: Point,
  plan: CardGeometry,
  port: string | undefined,
  toward: Point,
  lane = 0,
): Endpoint {
  const socket = plan.ports.find((p) => p.label === port);
  const dx = toward.x - (position.x + CARD_WIDTH / 2);
  const dy = toward.y - (position.y + plan.height / 2);
  const side: Side =
    socket?.side ??
    (Math.abs(dx) / CARD_WIDTH > Math.abs(dy) / plan.height
      ? dx < 0
        ? "left"
        : "right"
      : dy < 0
        ? "top"
        : "bottom");
  const point = socket
    ? {
        x: position.x + socket.x + 25,
        y: position.y + socket.y + (side === "bottom" ? PORT_HEIGHT : 0),
      }
    : {
        x:
          position.x +
          (side === "left"
            ? 0
            : side === "right"
              ? CARD_WIDTH
              : CARD_WIDTH / 2),
        y:
          position.y +
          (side === "top"
            ? 0
            : side === "bottom"
              ? plan.height
              : plan.height / 2),
      };
  const gap = 28 + (lane % 8) * 4;
  const exit = {
    x:
      side === "left"
        ? position.x - gap
        : side === "right"
          ? position.x + CARD_WIDTH + gap
          : point.x,
    y:
      side === "top"
        ? position.y - gap
        : side === "bottom"
          ? position.y + plan.height + gap
          : point.y,
  };
  const escape = [point];
  // Inner rows use the row gutter, never run through another socket's label.
  if (
    socket &&
    plan.ports.some(
      (p) =>
        p.side === side &&
        p.x === socket.x &&
        (side === "top" ? p.y < socket.y : p.y > socket.y),
    )
  ) {
    const y = point.y + (side === "top" ? -4 : 4);
    exit.x = position.x + (socket.x < CARD_WIDTH / 2 ? -gap : CARD_WIDTH + gap);
    escape.push({ x: point.x, y }, { x: exit.x, y });
  }
  escape.push(exit);
  return {
    point,
    side,
    escape: escape.map((p) => ({
      x: Math.max(0, Math.min(32768, p.x)),
      y: Math.max(0, Math.min(32768, p.y)),
    })),
    unknown: !socket,
  };
}
export function cardHeight(count: number): number {
  return count
    ? PORT_TOP + Math.ceil(count / PORT_COLUMNS) * PORT_ROW + 16
    : 114;
}
export function socketPosition(index: number): Point {
  return {
    x: (index % PORT_COLUMNS) * PORT_STEP,
    y: PORT_TOP + Math.floor(index / PORT_COLUMNS) * PORT_ROW,
  };
}
export function anchor(
  position: Point,
  ports: string[],
  port?: string,
  toward?: Point,
): Point {
  const index = ports.indexOf(port ?? "");
  if (index < 0) {
    const dx = toward ? toward.x - position.x : 0;
    const dy = toward ? toward.y - position.y : 1;
    if (Math.abs(dx) / CARD_WIDTH > Math.abs(dy) / 114)
      return { x: position.x + (dx < 0 ? 0 : CARD_WIDTH), y: position.y + 57 };
    return {
      x: position.x + CARD_WIDTH / 2,
      y: position.y + (dy < 0 ? 0 : 114),
    };
  }
  const p = socketPosition(index);
  return { x: position.x + p.x + 25, y: position.y + p.y + PORT_HEIGHT };
}
