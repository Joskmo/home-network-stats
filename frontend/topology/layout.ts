import type { Graph, NetworkNode, Positions } from "./types";
const rank = (n: NetworkNode): number =>
  n.type === "router" ? 0 : n.type === "switch" || n.type === "ap" ? 1 : 2;
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
  for (let i = 0; i < queue.length; i++)
    for (const l of graph.links) {
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
    const d = depth.get(n.id) ?? rank(n);
    if (!groups.has(d)) groups.set(d, []);
    groups.get(d)!.push(n);
  });
  const result: Positions = {};
  let y = 40;
  [...groups.keys()]
    .sort((a, b) => a - b)
    .forEach((d) => {
      const group = groups.get(d)!;
      for (let offset = 0; offset < group.length; offset += 6) {
        const row = group.slice(offset, offset + 6);
        row.forEach((n, i) => {
          result[n.id] = { x: 40 + i * 250, y };
        });
        y += Math.max(
          210,
          ...row.map(
            (n) =>
              180 +
              30 *
                Math.ceil(
                  new Set(
                    [
                      ...(n.ports || []),
                      ...graph.links.flatMap((l) =>
                        l.source === n.id
                          ? [l.source_port]
                          : l.target === n.id
                            ? [l.target_port]
                            : [],
                      ),
                    ].filter(Boolean),
                  ).size / 4,
                ),
          ),
        );
      }
    });
  return result;
}
