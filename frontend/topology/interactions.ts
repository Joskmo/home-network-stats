import { element as el, button } from "../shared/dom";
import type { Cable, Graph, Observation, ItemKind } from "./types";
import { routeKey } from "./routing";
import { resetRouteEditor } from "./route-editor";
import { contextMenu, closeContextMenu, type MenuItem } from "./context-menu";

type Edge = Cable | Observation;
type Selection = { node: string; port?: string; route?: string };
export interface InspectionActions {
  editor(kind: ItemKind, id?: string): void;
  splitCable(id: string): void;
  canEdit(): boolean;
}
// Identity only: each draw resolves the current graph, never retains old nodes.
let selected: Selection | null = null;
let pinned = false;
let renderEpoch = 0;
let cleanup = () => {};
export function disposeInspection() {
  cleanup();
  closeContextMenu();
}
export function resetInspection(): void {
  disposeInspection();
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
    add(key: string, x: number, y: number): void;
    canAdd(key: string): boolean;
    remove(key: string, index: number): void;
  },
  actions?: InspectionActions,
) {
  disposeInspection();
  const abort = new AbortController();
  cleanup = () => abort.abort();
  const epoch = ++renderEpoch;
  let lastWireClick: {
    key: string;
    x: number;
    y: number;
    time: number;
  } | null = null;
  let inspector = document.getElementById("map-inspector");
  if (!inspector) {
    inspector = el("section", undefined, "map-inspector");
    inspector.id = "map-inspector";
    inspector.setAttribute("aria-live", "polite");
    canvas.closest(".map-workspace")!.append(inspector);
  }
  const panel = inspector;
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;
  const cancelLeave = () => {
    if (leaveTimer) clearTimeout(leaveTimer);
  };
  const leave = (event?: PointerEvent) => {
    const workspace = canvas.closest(".map-workspace");
    if (
      event?.relatedTarget instanceof Node &&
      workspace?.contains(event.relatedTarget)
    )
      return;
    cancelLeave();
    if (!pinned)
      leaveTimer = setTimeout(() => {
        if (!pinned && epoch === renderEpoch) clear();
      }, 600);
  };
  canvas
    .closest<HTMLElement>(".map-workspace")
    ?.addEventListener("pointerleave", leave, { signal: abort.signal });
  abort.signal.addEventListener("abort", cancelLeave);
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
    (selected.route
      ? routeKey(edge) === selected.route
      : (edge.source === selected.node &&
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
    const toggle = button(tr("details"), () => {
      panel.classList.toggle("is-collapsed");
      toggle.setAttribute(
        "aria-expanded",
        String(!panel.classList.contains("is-collapsed")),
      );
    });
    toggle.className = "map-inspector-toggle";
    toggle.setAttribute(
      "aria-expanded",
      String(!panel.classList.contains("is-collapsed")),
    );
    heading.append(toggle);
    panel.append(heading);
    if (!selected) {
      panel.append(el("p", tr("inspectHint")));
      return;
    }
    if (actions && !selected.route && selected.port !== "@wan") {
      const edit = button(tr("edit"), () => {
        if (actions.canEdit() && selected)
          actions.editor("nodes", selected.node);
      });
      edit.disabled = !actions.canEdit();
      panel.append(edit);
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
    selected = null;
    pinned = false;
    resetRouteEditor();
    canvas.querySelectorAll(".map-route-handle").forEach((e) => e.remove());
    update();
  }
  function select(node: string, port?: string, pin = false) {
    cancelLeave();
    selected = { node, port };
    pinned = pin;
    update();
  }
  canvas
    .querySelectorAll<SVGPathElement>(
      ".map-wire[data-route], .map-upstream[data-route]",
    )
    .forEach((path) => {
      const key = path.dataset.route!;
      const hit = path.cloneNode(false) as SVGPathElement;
      hit.setAttribute("class", "map-wire-hit");
      hit.setAttribute("vector-effect", "non-scaling-stroke");
      hit.setAttribute("tabindex", "0");
      hit.setAttribute("role", "button");
      const edge = edges.find((e) => routeKey(e) === key);
      hit.setAttribute(
        "aria-label",
        `${tr("adjustRoute")} · ${edge ? `${graph.nodes.find((n) => n.id === edge.source)?.name} → ${graph.nodes.find((n) => n.id === edge.target)?.name}` : tr("uplink")}`,
      );
      path.parentElement?.removeAttribute("aria-hidden");
      path.after(hit);
      const choose = () => {
        cancelLeave();
        const edge = edges.find((e) => routeKey(e) === key);
        selected = {
          node: edge?.source || path.dataset.owner!,
          route: key,
          port: edge ? undefined : "@wan",
        };
        pinned = true;
        update();
        editRoute.show(key);
      };
      hit.addEventListener("click", (e) => {
        e.stopPropagation();
        lastWireClick = {
          key,
          x: e.clientX,
          y: e.clientY,
          time: performance.now(),
        };
        choose();
      });
      hit.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        choose();
        editRoute.add(key, e.clientX, e.clientY);
      });
      hit.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        choose();
        const edge = edges.find((e) => routeKey(e) === key);
        const items: MenuItem[] = [
          {
            label: tr("addBend"),
            disabled: !editRoute.canAdd(key),
            run: () => editRoute.add(key, e.clientX, e.clientY),
          },
          {
            label: tr("resetRoute"),
            disabled: !editRoute.canEdit(),
            run: () => editRoute.reset(key),
          },
        ];
        if (edge && !edge.observation && actions)
          items.push({
            label: tr("editCable"),
            disabled: !actions.canEdit(),
            run: () => {
              if (actions.canEdit()) actions.editor("links", edge.id);
            },
          });
        contextMenu(
          canvas.closest<HTMLElement>(".map-scroll")!,
          e.clientX,
          e.clientY,
          items,
        );
      });
      hit.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          choose();
        }
        if (e.key === "Escape") clear();
      });
    });
  const scope = canvas.closest<HTMLElement>(".map-scroll")!;
  scope.addEventListener(
    "dblclick",
    (e) => {
      // The first click may put a newly exposed handle under the second click.
      if (
        !(e.target instanceof Element) ||
        !e.target.closest(".map-route-handle") ||
        !lastWireClick
      )
        return;
      if (
        performance.now() - lastWireClick.time > 600 ||
        Math.hypot(e.clientX - lastWireClick.x, e.clientY - lastWireClick.y) > 5
      )
        return;
      e.preventDefault();
      editRoute.add(lastWireClick.key, e.clientX, e.clientY);
      lastWireClick = null;
    },
    { signal: abort.signal },
  );
  scope.addEventListener(
    "contextmenu",
    (e) => {
      if (!(e.target instanceof Element)) return;
      e.preventDefault();
      const handle = e.target.closest<HTMLElement>(".map-route-handle");
      const node = e.target.closest<HTMLElement>(".map-node");
      let items: MenuItem[];
      if (handle)
        items = [
          {
            label: tr("removeBend"),
            disabled: !editRoute.canEdit(),
            run: () =>
              editRoute.remove(
                handle.dataset.route!,
                Number(handle.dataset.bend),
              ),
          },
        ];
      else if (node && actions) {
        select(node.dataset.node!, undefined, true);
        items = [
          {
            label: tr("edit"),
            disabled: !actions.canEdit(),
            run: () => {
              if (actions.canEdit()) actions.editor("nodes", node.dataset.node);
            },
          },
        ];
      } else
        items = ["fitMap", "arrange", "add"].map((action) => ({
          label: tr(action),
          disabled: action !== "fitMap" && !editRoute.canEdit(),
          run: () =>
            scope.dispatchEvent(
              new CustomEvent("mapaction", { detail: action }),
            ),
        }));
      contextMenu(scope, e.clientX, e.clientY, items);
    },
    { signal: abort.signal },
  );
  scope.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape") clear();
      if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
        e.preventDefault();
        const target = e.target instanceof Element ? e.target : scope;
        const r = target.getBoundingClientRect();
        let x = r.left + 20,
          y = r.top + 20;
        if (target instanceof SVGPathElement) {
          const p = target.getPointAtLength(target.getTotalLength() / 2);
          const q = new DOMPoint(p.x, p.y).matrixTransform(
            target.getScreenCTM()!,
          );
          x = q.x;
          y = q.y;
        }
        target.dispatchEvent(
          new MouseEvent("contextmenu", {
            bubbles: true,
            cancelable: true,
            clientX: x,
            clientY: y,
          }),
        );
      }
    },
    { signal: abort.signal },
  );
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
