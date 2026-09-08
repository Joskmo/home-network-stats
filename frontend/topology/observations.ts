import type { Graph, Observation, NetworkNode } from "./types";
export function observations(graph: Graph): Observation[] {
  const routers = graph.nodes.filter((n) => n.type === "router");
  if (routers.length !== 1) return [];
  return graph.nodes.flatMap<Observation>((n) => {
    const d = n.discovery;
    if (
      n.id === routers[0].id ||
      !d?.attachment ||
      graph.links.some((l) => l.source === n.id || l.target === n.id)
    )
      return [];
    const source = String(d.source).toLowerCase();
    const medium = source.includes("iw")
      ? "wifi"
      : source.includes("fdb")
        ? "via"
        : null;
    return medium
      ? [
          {
            source: routers[0].id,
            target: n.id,
            medium,
            observation: true,
            label: d.attachment,
            ...(medium === "via" ? { source_port: d.attachment } : {}),
          },
        ]
      : [];
  });
}

export function knownPorts(graph: Graph, n: NetworkNode): string[] {
  return [
    ...new Set(
      [
        ...(n.ports || []),
        ...observations(graph)
          .filter((l) => l.source === n.id && l.medium === "via")
          .map((l) => l.source_port || ""),
        ...graph.links
          .filter((l) => l.medium !== "wifi")
          .flatMap((l) =>
            l.source === n.id
              ? [l.source_port]
              : l.target === n.id
                ? [l.target_port]
                : [],
          ),
      ].filter(Boolean),
    ),
  ];
}
