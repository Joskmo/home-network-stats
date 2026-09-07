import { $, element as el, button, control } from "../shared/dom";
import { getBridge } from "../shared/contracts";
import { asError } from "../shared/http";
import { dict } from "./i18n";
import { layout, insertSwitch } from "./domain";
import { openEditor } from "./editor";
import { renderGraph } from "./rendering";
import type {
  Graph,
  Monitor,
  Positions,
  Drag,
  ItemKind,
  NetworkNode,
  Cable,
  NodeType,
} from "./types";
const bridge = getBridge(),
  api = bridge.api,
  root = $("topology");
let autoView = false,
  positions: Positions = {},
  viewOverrides: Positions = {};
const tr = (k: string) => dict[bridge.language][k] || k;
let graph: Graph | null = null,
  monitor: Monitor = {},
  dirty = false,
  busy = false,
  editing: { kind: ItemKind; id?: string } | null = null,
  drag: Drag | null = null,
  epoch = 0;
const say = (key: string) => {
  $("map-message").textContent = tr(key);
};
const uuid = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
        b.toString(16).padStart(2, "0"),
      ).join("");
const stamp = (v: number | null) =>
  v
    ? new Date(v * 1000).toLocaleString(
        bridge.language === "ru" ? "ru-RU" : "en-GB",
      )
    : tr("never");
function syncReplacementControls() {
  root
    .querySelectorAll<HTMLButtonElement>("[data-replaces-graph]")
    .forEach((b) => {
      b.disabled = busy || !!editing;
    });
  $("map-save").disabled = busy || !!editing || !dirty;
}
function setDirty() {
  $("map-preview")?.replaceChildren();
  if ($("map-preview")) $("map-preview").hidden = true;
  dirty = true;
  say("dirty");
  syncReplacementControls();
}
function shell() {
  root.replaceChildren();
  root.append(el("h2", tr("title")), el("p", tr("hint"), "muted"));
  const details = el("details");
  details.append(
    el("summary", tr("evidence")),
    el("p", tr("monitor"), "muted"),
    el("p", tr("discoveryHint"), "muted"),
  );
  root.append(details);
  const preview = el("section");
  preview.id = "map-preview";
  preview.hidden = true;
  root.append(preview);
  const tools = el("div", undefined, "map-tools");
  const refresh = button(tr("refresh"), refreshDiscovered);
  refresh.dataset.replacesGraph = "";
  tools.append(refresh);
  tools.append(
    button(tr("add"), () => editor("nodes")),
    button(tr("link"), () => editor("links")),
    button(tr("arrange"), () => {
      if (!graph || busy) return;
      viewOverrides = {};
      autoView = true;
      positions = layout(graph);
      for (const n of graph.nodes) {
        const p = positions[n.id];
        n.x = Math.min(1400, p.x);
        n.y = Math.min(800, p.y);
      }
      setDirty();
      draw();
    }),
  );
  const legend = el("div", undefined, "map-legend");
  ["ethernet", "via", "unmapped"].forEach((k) =>
    legend.append(el("span", tr(k), k)),
  );
  root.append(legend, el("p", tr("layoutHint"), "muted"));
  const save = button(tr("save"), saveMap);
  save.id = "map-save";
  save.disabled = !dirty;
  const reload = button(tr("reload"), () => {
    if (editing || busy) return;
    if (!dirty || confirm(tr("discard"))) load(true);
  });
  reload.dataset.replacesGraph = "";
  tools.append(save, reload);
  root.append(tools);
  const message = el(
    "p",
    tr(graph ? (dirty ? "dirty" : "saved") : "wait"),
    "muted",
  );
  message.id = "map-message";
  message.setAttribute("role", "status");
  root.append(message);
  const scroll = el("div", undefined, "map-scroll");
  const canvas = el("div", undefined, "map-canvas");
  canvas.id = "map-canvas";
  scroll.append(canvas);
  root.append(scroll);
  const lists = el("div", undefined, "map-lists");
  lists.id = "map-lists";
  root.append(lists);
  const form = el("form");
  form.id = "map-form";
  form.hidden = true;
  root.append(form);
  draw();
}
function draw() {
  positions = renderGraph(
    graph,
    monitor,
    autoView,
    viewOverrides,
    () => !!drag?.moved,
    {
      tr,
      stamp,
      editor,
      startDrag,
      splitCable,
    },
  );
  syncReplacementControls();
}
function splitCable(id: string) {
  if (!graph || busy || editing) return;
  try {
    graph = insertSwitch(graph, id, uuid, tr("switch"));
    autoView = true;
    const arranged = layout(graph);
    for (const node of graph.nodes) {
      const p = arranged[node.id];
      node.x = Math.min(1400, p.x);
      node.y = Math.min(800, p.y);
    }
    setDirty();
    draw();
  } catch {
    say("limit");
  }
}
function startDrag(e: PointerEvent, n: NetworkNode, b: HTMLButtonElement) {
  if (e.button !== 0 || busy || !graph) return;
  drag = {
    id: n.id,
    startX: e.clientX,
    startY: e.clientY,
    x: positions[n.id].x,
    y: positions[n.id].y,
    moved: false,
  };
  b.setPointerCapture(e.pointerId);
  b.onpointermove = (event) => {
    if (!drag || !graph) return;
    const dx = event.clientX - drag.startX,
      dy = event.clientY - drag.startY;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (drag.moved) {
      if (autoView && !Object.values(positions).some((p) => p.y > 800)) {
        for (const node of graph.nodes) {
          node.x = positions[node.id].x;
          node.y = positions[node.id].y;
        }
        autoView = false;
      }
      if (autoView)
        viewOverrides[n.id] = {
          x: Math.max(0, Math.round(drag.x + dx)),
          y: Math.max(0, Math.round(drag.y + dy)),
        };
      n.x = Math.max(0, Math.min(1400, Math.round(drag.x + dx)));
      n.y = Math.max(0, Math.min(800, Math.round(drag.y + dy)));
      b.style.left = (viewOverrides[n.id]?.x ?? n.x) + "px";
      b.style.top = (viewOverrides[n.id]?.y ?? n.y) + "px";
    }
  };
  const finish = () => {
    if (drag?.moved) {
      setDirty();
      setTimeout(() => {
        drag = null;
        draw();
      }, 0);
    } else drag = null;
  };
  b.onpointerup = finish;
  b.onpointercancel = finish;
}
function editor(kind: ItemKind, id?: string) {
  if (!graph || busy) return;
  if (!id && graph[kind].length >= (kind === "nodes" ? 64 : 128)) {
    say("limit");
    return;
  }
  if (kind === "links" && graph.nodes.length < 2) {
    say("invalid");
    return;
  }
  editing = { kind, id };
  syncReplacementControls();
  openEditor(graph, kind, id, {
    tr,
    say,
    uuid,
    close() {
      editing = null;
      syncReplacementControls();
    },
    changed(id) {
      delete monitor[id];
      setDirty();
      draw();
    },
  });
}
async function refreshDiscovered() {
  if (!graph || busy || editing) return;
  busy = true;
  const generation = epoch;
  const original = JSON.stringify(graph);
  try {
    const candidate = await api("/api/topology/preview", { topology: graph });
    if (generation !== epoch || original !== JSON.stringify(graph)) return;
    const box = $("map-preview");
    box.replaceChildren(el("h3", tr("preview")));
    box.hidden = false;
    candidate.nodes.forEach((n) => {
      const old = graph?.nodes.find((o) => o.id === n.id);
      if (JSON.stringify(old) !== JSON.stringify(n)) {
        const d = n.discovery;
        box.append(
          el(
            "p",
            (old ? "↻ " : "+ ") +
              n.name +
              " · " +
              (n.ip || "—") +
              " · " +
              n.mac +
              " · " +
              (d
                ? d.source +
                  " · " +
                  (d.attachment || "—") +
                  " · " +
                  d.confidence +
                  " · " +
                  stamp(d.last_seen)
                : ""),
          ),
        );
      }
    });
    box.append(
      button(tr("apply"), () => {
        if (editing || busy) return;
        if (original !== JSON.stringify(graph)) {
          box.hidden = true;
          return;
        }
        graph = candidate;
        autoView = !graph.links.length || autoView;
        monitor = {};
        setDirty();
        draw();
      }),
      button(tr("cancel"), () => {
        box.hidden = true;
        box.replaceChildren();
      }),
    );
    box.querySelector("button")!.dataset.replacesGraph = "";
    box.scrollIntoView({ block: "nearest" });
  } catch (caught) {
    const e = asError(caught);
    if (generation === epoch) say(e.status === 400 ? "invalid" : "unavailable");
  } finally {
    busy = false;
    syncReplacementControls();
  }
}
async function load(force = false) {
  if (busy || (force && editing) || $("dashboard").hidden) return;
  busy = true;
  const generation = epoch;
  try {
    const data = await api("/api/topology");
    if (generation !== epoch || $("dashboard").hidden) return;
    monitor = data.monitor || {};
    if (graph && !force) {
      for (const n of graph.nodes) {
        if (data.nodes.find((i) => i.id === n.id)?.ip !== n.ip)
          delete monitor[n.id];
      }
    }
    if (!graph || force || (!dirty && !editing)) {
      if (force) viewOverrides = {};
      graph = { revision: data.revision, nodes: data.nodes, links: data.links };
      autoView =
        !graph.links.length ||
        Object.values(layout(graph)).some((p) => p.y > 800);
      dirty = false;
    }
    draw();
    if (!dirty) say("saved");
    syncReplacementControls();
  } catch (caught) {
    const e = asError(caught);
    if (generation === epoch) say("failure");
  } finally {
    busy = false;
    syncReplacementControls();
  }
}
async function saveMap() {
  if (!graph || busy || editing) return;
  busy = true;
  const generation = epoch;
  root.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    const data = await api("/api/topology", { topology: graph });
    if (generation !== epoch) return;
    graph = data;
    dirty = false;
    draw();
    say("saved");
  } catch (caught) {
    const e = asError(caught);
    if (generation === epoch)
      say(
        e.status === 409
          ? "conflict"
          : e.status === 400
            ? "invalid"
            : "failure",
      );
  } finally {
    busy = false;
    root.querySelectorAll("button").forEach((b) => (b.disabled = false));
    syncReplacementControls();
  }
}
new MutationObserver(() => {
  if ($("dashboard").hidden) {
    epoch++;
    graph = null;
    monitor = {};
    dirty = false;
    editing = null;
    autoView = false;
    positions = {};
    viewOverrides = {};
    shell();
  } else load();
}).observe($("dashboard"), { attributes: true, attributeFilter: ["hidden"] });
new MutationObserver(() => {
  editing = null;
  shell();
}).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ["lang"],
});
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
shell();
load();
setInterval(() => load(), 15000);
