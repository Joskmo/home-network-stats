import { $, element as el, button } from "../shared/dom";
import { layout } from "./layout";
import { observations, knownPorts } from "./observations";
import type {
  Graph,
  Monitor,
  Positions,
  ItemKind,
  NetworkNode,
  NodeType,
} from "./types";
export interface RenderActions {
  tr(key: string): string;
  stamp(value: number | null): string;
  editor(kind: ItemKind, id?: string): void;
  startDrag(
    event: PointerEvent,
    node: NetworkNode,
    button: HTMLButtonElement,
  ): void;
  splitCable(id: string): void;
}
function svg<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number>,
  text?: string,
): SVGElementTagNameMap[K] {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, String(v)));
  if (text !== undefined) e.textContent = text;
  return e;
}
function icon(type: NodeType) {
  const paths = {
    router: "M3 13h26v13H3z M7 13V4m18 9V4 M7 21h2m4 0h2m4 0h2",
    switch: "M2 9h28v17H2z M6 15h3v5H6z M14 15h3v5h-3z M22 15h3v5h-3z",
    ap: "M4 10q12-12 24 0 M8 15q8-8 16 0 M12 20q4-4 8 0 M16 26h.1",
    phone: "M9 2h14v28H9z M14 26h4",
    tablet: "M5 2h22v28H5z M14 26h4",
    desktop: "M2 3h28v20H2z M16 23v6 M9 29h14",
    laptop: "M6 3h20v19H6z M2 27l4-5h20l4 5z",
    tv: "M2 4h28v21H2z M8 29l3-4m13 4-3-4",
    server: "M6 2h20v28H6z M6 11h20M6 21h20 M10 6h3m-3 10h3m-3 9h3",
    printer: "M8 11V2h16v9 M8 24H3V11h26v13h-5 M8 20h16v10H8z",
    iot: "M10 7h12v18H10z M3 12h7m12 0h7M3 20h7m12 0h7M14 2v5m5-5v5m-5 18v5m5-5v5",
    device: "M5 6h22v20H5z M10 12h12m-12 7h8",
    other: "M16 2l14 14-14 14L2 16z",
  };
  const image = svg("svg", {
    viewBox: "0 0 32 32",
    class: "map-icon",
    "aria-hidden": "true",
  });
  image.append(svg("path", { d: paths[type] || paths.device }));
  return image;
}
export function renderGraph(
  graph: Graph | null,
  monitor: Monitor,
  autoView: boolean,
  viewOverrides: Positions,
  isDragging: () => boolean,
  actions: RenderActions,
): Positions {
  const { tr, stamp, editor, startDrag, splitCable } = actions;
  let positions: Positions = {};
  const canvas = $("map-canvas"),
    lists = $("map-lists");
  if (!canvas) return positions;
  canvas.replaceChildren();
  lists.replaceChildren();
  if (!graph) return positions;
  if (!graph.nodes.length) canvas.append(el("p", tr("empty"), "map-empty"));
  positions = autoView
    ? { ...layout(graph), ...viewOverrides }
    : Object.fromEntries(graph.nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
  const ports = Object.fromEntries(
    graph.nodes.map((n) => [n.id, knownPorts(graph, n)]),
  );
  const width = Math.max(
      1600,
      ...Object.values(positions).map(
        (p) => p.x + 260 + graph.links.length * 10,
      ),
    ),
    height = Math.max(
      920,
      ...graph.nodes.map(
        (n) => positions[n.id].y + 160 + Math.ceil(ports[n.id].length / 4) * 30,
      ),
    );
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  const wires = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "map-wires",
    "aria-hidden": "true",
  });
  canvas.append(wires);
  const observed = observations(graph);
  const anchor = (id: string, port: string | undefined, physical: boolean) => {
    const p = positions[id];
    const i = ports[id].indexOf(port ?? "");
    return physical && i >= 0
      ? { x: p.x + 25 + (i % 4) * 52, y: p.y + 142 + Math.floor(i / 4) * 30 }
      : { x: p.x + 104, y: p.y + 50 };
  };
  [...graph.links, ...observed].forEach((l, edgeIndex) => {
    if (l.medium === "wifi" || !positions[l.source] || !positions[l.target])
      return;
    const medium = l.medium || "ethernet",
      physical = medium === "ethernet" && !l.observation;
    const a = anchor(l.source, l.source_port, physical),
      b = anchor(l.target, l.target_port, physical);
    const bend = (a.y + b.y) / 2;
    const leftLane =
      Math.min(positions[l.source].x, positions[l.target].x) -
      24 -
      edgeIndex * 10;
    const corridor =
      leftLane >= 8
        ? leftLane
        : Math.max(...Object.values(positions).map((p) => p.x)) +
          232 +
          edgeIndex * 10;
    const lead = 150 + (edgeIndex % 3) * 5;
    const ay =
        positions[l.source].y +
        lead +
        Math.ceil(ports[l.source].length / 4) * 30,
      by =
        positions[l.target].y +
        lead +
        Math.ceil(ports[l.target].length / 4) * 30;
    const d = physical
      ? `M${a.x} ${a.y} V${ay} H${corridor} V${by} H${b.x} V${b.y}`
      : `M${a.x} ${a.y} C${a.x} ${bend},${b.x} ${bend},${b.x} ${b.y}`;
    const path = svg("path", { d, class: "map-wire " + medium });
    wires.append(path);
    if (l.observation)
      wires.append(
        svg(
          "text",
          { x: (a.x + b.x) / 2, y: bend - 8, class: "map-edge-label" },
          (l.observation ? tr("evidence") + " · " : "") +
            tr(medium) +
            (l.label ? " · " + l.label : ""),
        ),
      );
  });
  const nodeList = el("div");
  nodeList.append(el("h3", tr("nodes")));
  graph.nodes.forEach((n) => {
    const p = positions[n.id],
      status = monitor[n.id] || { state: "unknown", checked_at: null };
    const b = button("", () => {
      if (!isDragging()) editor("nodes", n.id);
    });
    b.className = "map-node " + status.state + " type-" + n.type;
    b.style.left = p.x + "px";
    b.style.top = p.y + "px";
    b.dataset.node = n.id;
    b.append(
      icon(n.type),
      el("strong", n.name),
      el("small", tr(n.type) + " · " + (n.ip || "—")),
      el("small", tr(status.state), "map-status"),
    );
    const association = observed.find((l) => l.target === n.id);
    if (
      association?.medium === "wifi" ||
      String(n.discovery?.source || "")
        .toLowerCase()
        .includes("iw") ||
      graph.links.some(
        (l) => l.medium === "wifi" && (l.source === n.id || l.target === n.id),
      )
    ) {
      const badge = el("span", "Wi-Fi", "map-wifi-badge");
      badge.prepend(icon("ap"));
      b.append(badge);
    }
    if (
      !graph.links.some((l) => l.source === n.id || l.target === n.id) &&
      !association &&
      n.type !== "router"
    )
      b.append(el("small", tr("unmapped"), "map-unknown"));
    b.title = tr("checked") + ": " + stamp(status.checked_at);
    b.addEventListener("pointerdown", (e) => startDrag(e, n, b));
    canvas.append(b);
    ports[n.id].forEach((label, i) => {
      const socket = button(label, () => editor("nodes", n.id));
      socket.className = "map-port";
      socket.title = n.name + " · " + label;
      socket.style.left = p.x + (i % 4) * 52 + "px";
      socket.style.top = p.y + 120 + Math.floor(i / 4) * 30 + "px";
      canvas.append(socket);
    });
    const row = el("div", undefined, "map-row");
    row.append(
      el("span", n.name + " · " + (n.ip || "—") + " · " + tr(status.state)),
      button(tr("edit"), () => editor("nodes", n.id)),
    );
    nodeList.append(row);
    if (n.discovery) {
      const d = n.discovery;
      nodeList.append(
        el(
          "p",
          tr("evidence") +
            ": " +
            d.source +
            " · " +
            (d.attachment || tr("unmapped")) +
            " · " +
            d.confidence +
            " · " +
            tr("observed") +
            ": " +
            stamp(d.last_seen),
          "muted",
        ),
      );
    }
  });
  lists.append(nodeList);
  const linkList = el("div");
  linkList.append(el("h3", tr("links")));
  graph.links.forEach((l) => {
    const a = graph.nodes.find((n) => n.id === l.source),
      b = graph.nodes.find((n) => n.id === l.target);
    if (!a || !b) return;
    const row = el("div", undefined, "map-row");
    row.append(
      el(
        "span",
        `${a.name} [${l.source_port}] ↔ ${b.name} [${l.target_port}] · ${tr(l.medium || "ethernet")}`,
      ),
      button(tr("edit"), () => editor("links", l.id)),
    );
    if (l.medium !== "wifi") {
      const insert = button(tr("insert"), () => splitCable(l.id));
      insert.dataset.replacesGraph = "";
      row.append(insert);
    }
    linkList.append(row);
  });
  lists.append(linkList);
  return positions;
}
