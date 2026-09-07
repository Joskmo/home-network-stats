import type { Graph, NetworkNode } from "./types";
export { layout } from "./layout";
export { observations } from "./observations";
export function insertSwitch(
  graph: Graph,
  id: string,
  uuid: () => string,
  name: string,
): Graph {
  const cable = graph.links.find((l) => l.id === id);
  if (
    !cable ||
    cable.medium === "wifi" ||
    graph.nodes.length >= 64 ||
    graph.links.length >= 128
  )
    throw new Error("Cannot split cable");
  const a = graph.nodes.find((n) => n.id === cable.source),
    b = graph.nodes.find((n) => n.id === cable.target);
  if (!a || !b) throw new Error("Missing cable endpoint");
  const node: NetworkNode = {
    id: uuid(),
    name,
    type: "switch",
    ip: "",
    mac: "",
    ports: ["1", "2"],
    x: Math.round((a.x + b.x) / 2),
    y: Math.round((a.y + b.y) / 2),
  };
  return {
    ...graph,
    nodes: [...graph.nodes, node],
    links: [
      ...graph.links.filter((l) => l.id !== id),
      {
        id: uuid(),
        source: cable.source,
        source_port: cable.source_port,
        target: node.id,
        target_port: "1",
        medium: "ethernet",
      },
      {
        id: uuid(),
        source: node.id,
        source_port: "2",
        target: cable.target,
        target_port: cable.target_port,
        medium: "ethernet",
      },
    ],
  };
}
