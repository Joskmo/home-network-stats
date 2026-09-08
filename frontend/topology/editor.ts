import { $, element as el, button, control } from "../shared/dom";
import { knownPorts } from "./observations";
import type { Graph, ItemKind, NetworkNode, Cable, NodeType } from "./types";

const nodeTypes: NodeType[] = [
  "router",
  "switch",
  "ap",
  "server",
  "phone",
  "laptop",
  "desktop",
  "tablet",
  "tv",
  "printer",
  "iot",
  "device",
  "other",
];
interface EditorActions {
  tr(key: string): string;
  say(key: string): void;
  uuid(): string;
  changed(id: string): void;
  close(): void;
}
/** Form operates on a captured draft; controller owns lifecycle and dirty state. */
export function openEditor(
  graph: Graph,
  kind: ItemKind,
  id: string | undefined,
  actions: EditorActions,
): void {
  const { tr, say, uuid } = actions;
  const original =
    kind === "nodes"
      ? graph.nodes.find((n) => n.id === id)
      : graph.links.find((l) => l.id === id);
  const values: Record<string, string> = {};
  if (original) {
    for (const [key, value] of Object.entries(original)) {
      if (typeof value === "string" || typeof value === "number")
        values[key] = String(value);
    }
    if ("ports" in original) values.ports = original.ports?.join("\n") ?? "";
  } else if (kind === "nodes") {
    Object.assign(values, {
      name: "",
      type: "device",
      ip: "",
      mac: "",
      x: String(40 + (graph.nodes.length % 6) * 210),
      y: String(40 + Math.floor(graph.nodes.length / 6) * 100),
    });
  } else {
    values.source = graph.nodes[0].id;
    values.target = graph.nodes[1].id;
  }
  values.medium ||= "ethernet";
  const form = $("map-form");
  form.replaceChildren();
  form.hidden = false;
  form.append(el("h3", tr("form")));
  const fields =
    kind === "nodes"
      ? ["name", "type", "ip", "mac", "ports", "x", "y"]
      : ["medium", "source", "source_port", "target", "target_port"];
  for (const key of fields) {
    const label = el("label", tr(key));
    label.htmlFor = "map-" + key;
    let input: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
    if (["type", "source", "target", "medium"].includes(key)) {
      const select = el("select");
      const options =
        key === "type"
          ? nodeTypes.map((id) => ({ id, name: tr(id) }))
          : key === "medium"
            ? ["ethernet", "wifi"].map((id) => ({ id, name: tr(id) }))
            : graph.nodes;
      for (const option of options) {
        const opt = el("option", option.name);
        opt.value = option.id;
        select.append(opt);
      }
      input = select;
    } else if (key === "ports") {
      const area = el("textarea");
      area.rows = 4;
      input = area;
    } else {
      const field = el("input");
      field.type = ["x", "y"].includes(key) ? "number" : "text";
      field.maxLength = key.endsWith("_port") ? 32 : 80;
      if (field.type === "number") {
        field.min = "0";
        field.max = "32768";
        field.step = "1";
      }
      input = field;
    }
    input.id = "map-" + key;
    input.name = key;
    input.value = values[key] ?? "";
    input.required = !["ip", "mac", "ports"].includes(key);
    form.append(label, input);
  }
  if (kind === "links") {
    const updatePorts = () => {
      for (const end of ["source", "target"]) {
        const input = control("map-" + end + "_port"),
          node = graph.nodes.find((n) => n.id === control("map-" + end).value);
        const listId = "map-" + end + "-options";
        let list = document.getElementById(listId);
        if (!list) {
          list = el("datalist");
          list.id = listId;
          form.append(list);
        }
        list.replaceChildren();
        for (const port of node ? knownPorts(graph, node) : []) {
          const option = el("option");
          option.value = port;
          list.append(option);
        }
        input.setAttribute("list", list.id);
        input.required = control("map-medium").value !== "wifi";
      }
    };
    for (const key of ["source", "target", "medium"])
      control("map-" + key).addEventListener("change", updatePorts);
    updatePorts();
  }
  const close = () => {
    form.hidden = true;
    actions.close();
  };
  const apply = el("button", tr("apply"));
  apply.type = "submit";
  form.append(apply, button(tr("cancel"), close));
  if (id)
    form.append(
      button(tr("remove"), () => {
        if (!confirm(tr("delete"))) return;
        if (kind === "nodes") {
          graph.nodes = graph.nodes.filter((n) => n.id !== id);
          graph.links = graph.links.filter(
            (l) => l.source !== id && l.target !== id,
          );
        } else graph.links = graph.links.filter((l) => l.id !== id);
        close();
        actions.changed(id);
      }),
    );
  const value = (key: string) => control("map-" + key).value.trim();
  form.onsubmit = (event) => {
    event.preventDefault();
    const itemId = id || uuid();
    if (kind === "nodes") {
      const type = nodeTypes.find((type) => type === value("type"));
      const ports = value("ports")
        .split(/\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const ip = value("ip"),
        mac = value("mac");
      if (
        !type ||
        ports.length > 48 ||
        new Set(ports).size !== ports.length ||
        ports.some((p) => p.length > 32) ||
        (ip &&
          !/^192\.168\.1\.(?:[1-9]|[1-9]\d|1\d\d|2[0-4]\d|25[0-4])$/.test(
            ip,
          )) ||
        (mac && !/^(?:[a-f\d]{2}:){5}[a-f\d]{2}$/i.test(mac))
      ) {
        say("invalid");
        return;
      }
      const item: NetworkNode = {
        id: itemId,
        name: value("name"),
        type,
        ip,
        mac,
        ports,
        x: Number(value("x")),
        y: Number(value("y")),
      };
      const node = graph.nodes.find((n) => n.id === id);
      if (node) Object.assign(node, item);
      else graph.nodes.push(item);
    } else {
      const source = value("source"),
        target = value("target"),
        medium = value("medium");
      if (source === target || (medium !== "wifi" && medium !== "ethernet")) {
        say("invalid");
        return;
      }
      const item: Cable = {
        id: itemId,
        source,
        target,
        source_port: value("source_port"),
        target_port: value("target_port"),
        medium,
      };
      const link = graph.links.find((l) => l.id === id);
      if (link) Object.assign(link, item);
      else graph.links.push(item);
    }
    close();
    actions.changed(itemId);
  };
  form.scrollIntoView({ block: "nearest" });
  form.querySelector<HTMLElement>("input,select")?.focus();
}
