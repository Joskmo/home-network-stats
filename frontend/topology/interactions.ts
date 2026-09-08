import { element as el, button } from "../shared/dom";
import type { Cable, Graph, Observation } from "./types";
import { routeKey } from "./routing";
import { resetRouteEditor } from "./route-editor";

type Edge = Cable | Observation;
type Selection = { node: string; port?: string };
// Identity only: each draw resolves the current graph, never retains old nodes.
let selected: Selection | null = null;
let pinned = false;
let renderEpoch = 0;
export function resetInspection(): void {
  selected = null;
  pinned = false;
  resetRouteEditor();
}

export function inspection(
  canvas: HTMLElement,
  graph: Graph,
  edges: Edge[],
  tr: (key: string) => string,
  editRoute: {
    show(key: string): void;
    reset(key: string): void;
    canEdit(): boolean;
  },
) {
  const epoch = ++renderEpoch;
  let inspector = document.getElementById("map-inspector");
  if (!inspector) {
    inspector = el("section", undefined, "map-inspector");
    inspector.id = "map-inspector";
    inspector.setAttribute("aria-live", "polite");
    canvas.parentElement!.before(inspector);
  }
  const panel = inspector;
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;
  const cancelLeave = () => {
    if (leaveTimer) clearTimeout(leaveTimer);
  };
  const leave = () => {
    cancelLeave();
    if (!pinned)
      leaveTimer = setTimeout(() => {
        if (!pinned && epoch === renderEpoch) clear();
      }, 220);
  };
  panel.onpointerenter = cancelLeave;
  panel.onpointerleave = leave;
  panel.onpointerdown = () => {
    cancelLeave();
    pinned = true;
  };
  function routeButtons(key: string) {
    const controls = el("div", undefined, "map-route-actions");
    controls.append(
      button(tr("adjustRoute"), () => {
        cancelLeave();
        pinned = true;
        editRoute.show(key);
      }),
      button(tr("resetRoute"), () => {
        cancelLeave();
        pinned = true;
        editRoute.reset(key);
      }),
    );
    controls.querySelectorAll("button").forEach((button) => {
      button.disabled = !editRoute.canEdit();
    });
    return controls;
  }
  const matches = (edge: Edge) =>
    selected &&
    ((edge.source === selected.node &&
      (!selected.port || edge.source_port === selected.port)) ||
      (edge.target === selected.node &&
        (!selected.port || edge.target_port === selected.port)));
  function update() {
    if (selected && !graph.nodes.some((n) => n.id === selected!.node))
      resetInspection();
    const active = edges.filter((e) => e.medium !== "wifi" && matches(e));
    canvas.classList.toggle("is-inspecting", !!selected);
    canvas.querySelectorAll<SVGPathElement>(".map-wire").forEach((path) => {
      path.classList.toggle(
        "is-active",
        active.includes(edges[Number(path.dataset.edge)]),
      );
    });
    canvas.querySelectorAll<HTMLElement>(".map-node").forEach((node) => {
      node.classList.toggle(
        "is-active",
        node.dataset.node === selected?.node ||
          active.some(
            (e) =>
              e.source === node.dataset.node || e.target === node.dataset.node,
          ),
      );
    });
    canvas.querySelectorAll<HTMLElement>(".map-port").forEach((socket) => {
      socket.classList.toggle(
        "is-active",
        active.some(
          (e) =>
            (e.source === socket.dataset.owner &&
              e.source_port === socket.dataset.port) ||
            (e.target === socket.dataset.owner &&
              e.target_port === socket.dataset.port),
        ),
      );
    });
    canvas
      .querySelectorAll<SVGPathElement>(".map-upstream")
      .forEach((line) =>
        line.classList.toggle(
          "is-active",
          line.dataset.owner === selected?.node,
        ),
      );
    panel.replaceChildren();
    const heading = el("div", undefined, "map-inspector-heading");
    heading.append(
      el(
        "strong",
        selected
          ? graph.nodes.find((n) => n.id === selected!.node)!.name
          : tr("inspect"),
      ),
    );
    if (selected) heading.append(button(tr("clearInspection"), clear));
    panel.append(heading);
    if (!selected) {
      panel.append(el("p", tr("inspectHint")));
      return;
    }
    if (selected.port === "@wan") {
      const row = el("div", undefined, "map-inspector-connection");
      const endpoint = el("div", undefined, "map-endpoint");
      endpoint.append(
        el("span", "Internet"),
        el("strong", "WAN", "map-endpoint-port"),
      );
      const certainty = el("div", undefined, "map-certainty");
      certainty.append(
        el("strong", tr("uplink")),
        el("span", tr("uplinkHint")),
      );
      row.append(endpoint, certainty);
      panel.append(row, routeButtons(JSON.stringify(["wan", selected.node])));
      return;
    }
    if (!active.length) {
      const wireless = edges.some(
        (e) =>
          e.medium === "wifi" &&
          (e.source === selected!.node || e.target === selected!.node),
      );
      panel.append(el("p", wireless ? tr("wirelessZone") : tr("noConnection")));
    }
    active.forEach((edge) => {
      const row = el("div", undefined, "map-inspector-connection");
      for (const side of ["source", "target"] as const) {
        const endpoint = el("div", undefined, "map-endpoint");
        endpoint.append(
          el(
            "span",
            graph.nodes.find((n) => n.id === edge[side])?.name || edge[side],
          ),
          el(
            "strong",
            edge[`${side}_port`] || tr("unknownPort"),
            "map-endpoint-port",
          ),
        );
        row.append(endpoint);
      }
      const certainty = el("div", undefined, "map-certainty");
      certainty.append(
        el("strong", tr(edge.observation ? "detected" : "manual")),
        el("span", tr(edge.observation ? "detectedHint" : "manualHint")),
      );
      row.append(certainty);
      panel.append(row, routeButtons(routeKey(edge)));
    });
  }
  function clear() {
    resetInspection();
    canvas.querySelectorAll(".map-route-handle").forEach((e) => e.remove());
    update();
  }
  function select(node: string, port?: string, pin = false) {
    cancelLeave();
    selected = { node, port };
    pinned = pin;
    update();
  }
  function bind(node: HTMLButtonElement, id: string) {
    let touch = false;
    const portAt = (target: EventTarget | null) =>
      target instanceof Element
        ? target.closest<HTMLElement>(".map-port")?.dataset.port
        : undefined;
    node.addEventListener("pointerover", (e) => {
      if (e.pointerType !== "touch" && !pinned) select(id, portAt(e.target));
    });
    node.addEventListener("pointerleave", leave);
    node.addEventListener("focus", () => {
      if (!pinned) select(id);
    });
    node.addEventListener("blur", () => {
      if (!pinned) clear();
    });
    node.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        clear();
      }
    });
    node.addEventListener("pointerdown", (e) => {
      touch = e.pointerType === "touch";
    });
    node.addEventListener(
      "click",
      (e) => {
        if (touch) {
          e.stopImmediatePropagation();
          select(id, portAt(e.target), true);
          touch = false;
        }
      },
      true,
    );
  }
  canvas
    .querySelectorAll<HTMLButtonElement>(".map-internet")
    .forEach((marker) => {
      marker.addEventListener("pointerenter", (e) => {
        if (e.pointerType !== "touch" && !pinned)
          select(marker.dataset.owner!, "@wan");
      });
      marker.addEventListener("pointerleave", leave);
      marker.addEventListener("focus", () =>
        select(marker.dataset.owner!, "@wan"),
      );
      marker.addEventListener("blur", () => {
        if (!pinned) clear();
      });
      marker.addEventListener("click", () =>
        select(marker.dataset.owner!, "@wan", true),
      );
      marker.addEventListener("keydown", (e) => {
        if (e.key === "Escape") clear();
      });
    });
  update();
  return { bind };
}
