import type { Graph, NetworkNode, Positions } from "./types";
import { observations } from "./observations";
import { naturalOrder, portPlans, topologyDepths } from "./geometry";
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
  const depth = topologyDepths(graph),
    plans = portPlans(graph);
  const edges = [...graph.links, ...observations(graph)].filter(
    (l) => l.medium !== "wifi",
  );

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
      const parent = (id: string) =>
        edges
          .flatMap((l) => {
            const other =
              l.source === id
                ? l.target
                : l.target === id
                  ? l.source
                  : undefined;
            return other && (depth.get(other) ?? Infinity) < d
              ? [
                  {
                    id: other,
                    port:
                      (l.source === other ? l.source_port : l.target_port) ||
                      "",
                  },
                ]
              : [];
          })
          .sort(
            (a, b) =>
              (result[a.id]?.x ?? 0) - (result[b.id]?.x ?? 0) ||
              naturalOrder(a.port, b.port),
          )[0];
      group.sort((a, b) => {
        const pa = parent(a.id),
          pb = parent(b.id);
        return (
          (pa && pb
            ? (result[pa.id]?.x ?? 0) - (result[pb.id]?.x ?? 0) ||
              naturalOrder(pa.port, pb.port)
            : 0) || naturalOrder(a.id, b.id)
        );
      });
      if (d === 100) y += 40;
      for (let offset = 0; offset < group.length; offset += 4) {
        const row = group.slice(offset, offset + 4);
        row.forEach((n, i) => {
          result[n.id] = { x: 48 + (columns - row.length) * 126 + i * 252, y };
        });
        y += Math.max(220, ...row.map((n) => plans[n.id].height + 112));
      }
    });
  return result;
}
