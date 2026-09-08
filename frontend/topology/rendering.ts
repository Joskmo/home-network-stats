import { $, element as el, button } from "../shared/dom";
import { layout, isWireless } from "./layout";
import { CARD_WIDTH, endpoint, portPlans } from "./geometry";
import type { Endpoint } from "./geometry";
import { inspection, resetInspection } from "./interactions";
import { pathData, routeKey, routeCable, throughWaypoints } from "./routing";
import { routeEditor } from "./route-editor";
import { observations } from "./observations";
import type {
  Graph,
  Monitor,
  Positions,
  ItemKind,
  NetworkNode,
  NodeType,
  Point,
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
  changeRoute(key: string, points?: Point[]): void;
  canEdit(): boolean;
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
  if (!graph) {
    resetInspection();
    document.getElementById("map-inspector")?.remove();
    return positions;
  }
  if (!graph.nodes.length) canvas.append(el("p", tr("empty"), "map-empty"));
  positions = autoView
    ? { ...layout(graph), ...viewOverrides }
    : Object.fromEntries(graph.nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
  const plans = portPlans(graph);
  const docks = new Map<string, Endpoint[]>();
  const width = Math.max(
      300,
      ...Object.values(positions).map(
        (p) => p.x + 248 + (graph.links.length + graph.nodes.length) * 10,
      ),
    ),
    height = Math.max(
      260,
      ...graph.nodes.map((n) => positions[n.id].y + plans[n.id].height + 64),
    );
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  const wires = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "map-wires",
    "aria-hidden": "true",
  });
  // Local socket-to-perimeter segments must paint above the card background.
  // The socket itself remains above this layer, and the SVG never eats clicks.
  wires.style.zIndex = "1";
  canvas.append(wires);
  graph.nodes
    .filter((n) => n.type === "router")
    .forEach((n) => {
      const p = positions[n.id];
      const internet = button("Internet", () => {});
      internet.className = "map-internet";
      internet.dataset.owner = n.id;
      internet.style.left = p.x + 46 + "px";
      internet.style.top = p.y - 44 + "px";
      internet.title = tr("uplinkHint");
      const globe = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
      globe.append(
        svg("circle", { cx: 12, cy: 12, r: 9 }),
        svg("path", { d: "M3 12h18 M12 3c-7 6-7 12 0 18 M12 3c7 6 7 12 0 18" }),
      );
      internet.prepend(globe);
      const wan = el("span", "WAN", "map-wan");
      wan.style.left = p.x + 154 + "px";
      wan.style.top = p.y - 12 + "px";
      wan.title = tr("uplinkHint");
      const line = svg("path", {
        d: `M${p.x + 100} ${p.y - 20} V${p.y - 17} H${p.x + 172} V${p.y}`,
        class: "map-upstream",
      });
      const key = JSON.stringify(["wan", n.id]);
      const points = graph.routes?.[key]
        ? throughWaypoints(
            { x: p.x + 100, y: p.y - 20 },
            { x: p.x + 172, y: p.y },
            graph.routes[key],
          )
        : [
            { x: p.x + 100, y: p.y - 20 },
            { x: p.x + 100, y: p.y - 17 },
            { x: p.x + 172, y: p.y - 17 },
            { x: p.x + 172, y: p.y },
          ];
      line.setAttribute("d", pathData(points));
      line.dataset.route = key;
      line.dataset.points = JSON.stringify(points);
      line.dataset.owner = n.id;
      wires.append(line);
      canvas.append(internet, wan);
    });
  const observed = observations(graph);
  const edges = [...graph.links, ...observed];
  const laneKeys = edges
    .filter((l) => l.medium !== "wifi")
    .map(routeKey)
    .sort();
  edges.forEach((l, edgeIndex) => {
    if (l.medium === "wifi" || !positions[l.source] || !positions[l.target])
      return;
    const medium = l.medium || "ethernet";
    const center = (id: string) => ({
      x: positions[id].x + CARD_WIDTH / 2,
      y: positions[id].y + plans[id].height / 2,
    });
    const downstreamSource = positions[l.source].y > positions[l.target].y;
    const upstream = downstreamSource ? l.target : l.source;
    const downstream = downstreamSource ? l.source : l.target;
    const upstreamPort = downstreamSource ? l.target_port : l.source_port;
    const socketOrder = plans[upstream].ports.findIndex(
      (p) => p.label === upstreamPort,
    );
    const ordinal =
      (socketOrder < 0 ? laneKeys.indexOf(routeKey(l)) : socketOrder) % 8;
    const lane =
      positions[downstream].x > positions[upstream].x ? 7 - ordinal : ordinal;
    const a = endpoint(
        positions[l.source],
        plans[l.source],
        l.source_port,
        center(l.target),
        lane,
      ),
      b = endpoint(
        positions[l.target],
        plans[l.target],
        l.target_port,
        center(l.source),
        lane,
      );
    for (const [id, dock] of [
      [l.source, a],
      [l.target, b],
    ] as const)
      if (dock.unknown) {
        const existing = docks.get(id) || [];
        if (
          !existing.some(
            (d) => d.point.x === dock.point.x && d.point.y === dock.point.y,
          )
        )
          existing.push(dock);
        docks.set(id, existing);
      }
    const obstacles = graph.nodes.map((n) => ({
      ...positions[n.id],
      width: CARD_WIDTH,
      height: plans[n.id].height,
    }));
    const key = routeKey(l),
      manual = graph.routes?.[key];
    const points = manual
      ? throughWaypoints(a.point, b.point, manual)
      : downstreamSource
        ? routeCable(b, a, obstacles, lane).reverse()
        : routeCable(a, b, obstacles, lane);
    const d = pathData(points);
    const path = svg("path", { d, class: "map-wire " + medium });
    path.dataset.edge = String(edgeIndex);
    path.dataset.route = key;
    path.dataset.points = JSON.stringify(points);
    path.dataset.source = l.source;
    path.dataset.target = l.target;
    path.dataset.sourcePort = l.source_port || "";
    path.dataset.targetPort = l.target_port || "";
    path.dataset.anchorSource = a.side;
    path.dataset.anchorTarget = b.side;
    wires.append(path);
  });
  if (autoView) {
    const wireless = graph.nodes.filter((n) => isWireless(graph, n.id));
    if (wireless.length) {
      const zone = el("div", tr("wirelessZone"), "map-wireless-zone");
      zone.style.top =
        Math.min(...wireless.map((n) => positions[n.id].y)) - 36 + "px";
      canvas.append(zone);
    }
  }
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
    b.style.height = plans[n.id].height + "px";
    b.style.paddingTop = plans[n.id].headerTop + 23 + "px";
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
    b.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "touch") startDrag(e, n, b);
    });
    canvas.append(b);
    if (plans[n.id].ports.some((p) => p.side === "bottom")) {
      const panel = el("span", undefined, "map-port-panel");
      panel.style.top = plans[n.id].bottomTop - 8 + "px";
      b.append(panel);
    }
    if (plans[n.id].headerTop) {
      const panel = el("span", undefined, "map-port-panel");
      Object.assign(panel.style, {
        top: "0px",
        bottom: "auto",
        height: plans[n.id].headerTop + "px",
        borderRadius: "10px 10px 0 0",
        borderTop: "0",
        borderBottom: "1px solid #52636b",
      });
      b.append(panel);
    }
    plans[n.id].ports.forEach((point) => {
      const { label } = point;
      const socket = el("span", label, "map-port");
      const detected =
        observed.some((l) => l.source === n.id && l.source_port === label) &&
        !(n.ports || []).includes(label) &&
        !graph.links.some(
          (l) =>
            (l.source === n.id && l.source_port === label) ||
            (l.target === n.id && l.target_port === label),
        );
      socket.classList.toggle("is-detected", detected);
      socket.title = n.name + " · " + label;
      socket.setAttribute(
        "aria-label",
        label + (detected ? " · " + tr("detected") : ""),
      );
      socket.dataset.owner = n.id;
      socket.dataset.port = label;
      socket.dataset.side = point.side;
      if (point.side === "top") {
        // Rotate the physical socket/notch, not its real interface label.
        socket.style.transform = "rotate(180deg)";
        const text = el("span", label);
        Object.assign(text.style, {
          display: "block",
          transform: "rotate(180deg)",
        });
        socket.replaceChildren(text);
      }
      socket.style.left = point.x + "px";
      socket.style.top = point.y + "px";
      b.append(socket);
    });
    for (const dock of docks.get(n.id) || []) {
      const socket = el("span", undefined, "map-dock");
      const vertical = dock.side === "top" || dock.side === "bottom";
      const w = vertical ? 6 : 3,
        h = vertical ? 3 : 6;
      socket.dataset.owner = n.id;
      socket.dataset.side = dock.side;
      socket.setAttribute("aria-hidden", "true");
      Object.assign(socket.style, {
        position: "absolute",
        boxSizing: "border-box",
        width: w + "px",
        height: h + "px",
        background: "#c3b781",
        borderRadius: "1px",
        left:
          dock.point.x -
          p.x -
          (vertical ? w / 2 : dock.side === "right" ? w : 0) +
          "px",
        top:
          dock.point.y -
          p.y -
          (!vertical ? h / 2 : dock.side === "bottom" ? h : 0) +
          "px",
      });
      b.append(socket);
    }
    const detectedPorts = [
      ...b.querySelectorAll<HTMLElement>(".map-port.is-detected"),
    ].map((socket) => socket.dataset.port);
    if (detectedPorts.length) {
      const note = el(
        "span",
        tr("detected") + ": " + detectedPorts.join(", "),
        "map-port-note",
      );
      note.style.top = plans[n.id].headerTop + 96 + "px";
      note.style.bottom = "auto";
      b.append(note);
    }
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
  // Include routed detours and user waypoints in the scrollable bounds.
  const allPoints = [
    ...canvas.querySelectorAll<SVGPathElement>("[data-points]"),
  ].flatMap((path) => JSON.parse(path.dataset.points!) as Point[]);
  const routedWidth = Math.max(width, ...allPoints.map((p) => p.x + 30));
  const routedHeight = Math.max(height, ...allPoints.map((p) => p.y + 30));
  canvas.style.width = routedWidth + "px";
  canvas.style.height = routedHeight + "px";
  wires.setAttribute("viewBox", `0 0 ${routedWidth} ${routedHeight}`);
  const editRoute = routeEditor(
    canvas,
    graph,
    tr,
    actions.changeRoute,
    actions.canEdit,
  );
  const interactions = inspection(canvas, graph, edges, tr, editRoute, actions);
  canvas
    .querySelectorAll<HTMLButtonElement>(".map-node")
    .forEach((node) => interactions.bind(node, node.dataset.node!));
  return positions;
}
