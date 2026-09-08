import type { Graph, NetworkNode, Positions } from "./types";
import { knownPorts, observations } from "./observations";
import { cardHeight } from "./geometry";
const rank = (n: NetworkNode): number =>
  n.type === "router" ? 0 : n.type === "switch" || n.type === "ap" ? 1 : 2;
export function isWireless(graph: Graph, id: string): boolean {
  return [...graph.links, ...observations(graph)].some(
    (l) => l.medium === "wifi" && l.target === id,
  );
}
export function layout(graph: Graph): Positions {
  const nodes = [...graph.nodes].sort(
    (a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id),
  );
  const depth = new Map<string, number>(),
    queue: string[] = [];
  nodes
    .filter((n) => n.type === "router")
    .forEach((n) => {
      depth.set(n.id, 0);
      queue.push(n.id);
    });
  if (!queue.length && nodes.length) {
    depth.set(nodes[0].id, 0);
    queue.push(nodes[0].id);
  }
  const edges = [...graph.links, ...observations(graph)].filter(
    (l) => l.medium !== "wifi",
  );
  for (let i = 0; i < queue.length; i++)
    for (const l of edges) {
      const id =
        l.source === queue[i]
          ? l.target
          : l.target === queue[i]
            ? l.source
            : null;
      if (id && !depth.has(id)) {
        depth.set(id, (depth.get(queue[i]) ?? 0) + 1);
        queue.push(id);
      }
    }
  const groups = new Map<number, NetworkNode[]>();
  nodes.forEach((n) => {
    const d = isWireless(graph, n.id) ? 100 : (depth.get(n.id) ?? rank(n));
    if (!groups.has(d)) groups.set(d, []);
    groups.get(d)!.push(n);
  });
  const columns = Math.min(
    4,
    Math.max(1, ...[...groups.values()].map((g) => g.length)),
  );
  const result: Positions = {};
  let y = 64;
  [...groups.keys()]
    .sort((a, b) => a - b)
    .forEach((d) => {
      const group = groups.get(d)!;
      if (d === 100) y += 40;
      for (let offset = 0; offset < group.length; offset += 4) {
        const row = group.slice(offset, offset + 4);
        row.forEach((n, i) => {
          result[n.id] = { x: 48 + (columns - row.length) * 126 + i * 252, y };
        });
        y += Math.max(
          220,
          ...row.map((n) => cardHeight(knownPorts(graph, n).length) + 72),
        );
      }
    });
  return result;
}
