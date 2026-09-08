import { button } from "../shared/dom";
import { pathData, throughWaypoints } from "./routing";
import type { Graph, Point } from "./types";
let editingKey: string | null = null;
let cancelDrag: (() => void) | null = null;
let renderGeneration = 0;
export function isRouteDragging() {
  return cancelDrag !== null;
}
export function canvasScale(canvas: HTMLElement): number {
  return canvas.getBoundingClientRect().width / canvas.offsetWidth || 1;
}
export function resetRouteEditor(): void {
  cancelDrag?.();
  editingKey = null;
}
export function syncRouteControls(
  root: HTMLElement,
  canEdit: () => boolean,
): void {
  root
    .querySelectorAll<HTMLButtonElement>(
      ".map-route-handle, .map-route-actions button",
    )
    .forEach((button) => {
      button.disabled = !canEdit();
      if (button.disabled) button.dispatchEvent(new Event("routecancel"));
    });
}
export function routeEditor(
  canvas: HTMLElement,
  graph: Graph,
  tr: (key: string) => string,
  changed: (key: string, points?: Point[]) => void,
  allowed: () => boolean,
) {
  cancelDrag?.();
  const generation = ++renderGeneration;
  const canEdit = () =>
    generation === renderGeneration && canvas.isConnected && allowed();
  const paths = (key: string) =>
    [...canvas.querySelectorAll<SVGPathElement>("path[data-route]")].filter(
      (p) => p.dataset.route === key,
    );
  const data = (key: string) => {
    const path = paths(key).find((p) => !p.classList.contains("map-wire-hit"));
    if (!path) return null;
    const points = JSON.parse(path.dataset.points!) as Point[];
    const waypoints = (
      graph.routes?.[key] || points.slice(1, -1).slice(0, 8)
    ).map((p) => ({ ...p }));
    return { points, waypoints };
  };
  const remove = (key: string, i: number) => {
    if (!canEdit()) return;
    const route = data(key);
    if (!route) return;
    route.waypoints.splice(i, 1);
    if (!route.waypoints.length) editingKey = null;
    changed(key, route.waypoints.length ? route.waypoints : undefined);
  };
  const show = (key: string) => {
    cancelDrag?.();
    editingKey = key;
    canvas.querySelectorAll(".map-route-handle").forEach((e) => e.remove());
    const path = [
      ...canvas.querySelectorAll<SVGPathElement>(
        ".map-wire[data-route], .map-upstream[data-route]",
      ),
    ].find((p) => p.dataset.route === key);
    if (!path) return;
    const points = JSON.parse(path.dataset.points!) as Point[];
    const a = points[0],
      b = points[points.length - 1];
    const waypoints = (
      graph.routes?.[key] || points.slice(1, -1).slice(0, 8)
    ).map((p) => ({ x: Math.max(0, p.x), y: Math.max(0, p.y) }));
    if (!waypoints.length)
      waypoints.push({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    const bounded = (p: Point) => ({
      x: Math.max(0, Math.min(32768, Math.round(p.x))),
      y: Math.max(0, Math.min(32768, Math.round(p.y))),
    });
    waypoints.forEach((point, i) => {
      const handle = button("", () => {});
      handle.className = "map-route-handle";
      handle.dataset.route = key;
      handle.dataset.bend = String(i);
      handle.disabled = !canEdit();
      handle.setAttribute("aria-label", `${tr("routeBend")} ${i + 1}`);
      handle.title = tr("routeDragHint");
      const place = () => {
        handle.style.left = waypoints[i].x - 9 + "px";
        handle.style.top = waypoints[i].y - 9 + "px";
      };
      place();
      canvas.append(handle);
      handle.addEventListener("pointerdown", (e) => {
        if (e.button !== 0 || !canEdit()) return;
        e.preventDefault();
        handle.setPointerCapture(e.pointerId);
        const original = { ...waypoints[i] },
          scale = canvasScale(canvas),
          start = { x: e.clientX, y: e.clientY };
        let moved = false;
        const cancel = () => {
          handle.onpointermove = null;
          handle.onpointerup = null;
          handle.onpointercancel = null;
          handle.removeEventListener("routecancel", cancel);
          waypoints[i] = original;
          place();
          if (canvas.contains(path))
            paths(key).forEach((p) => p.setAttribute("d", pathData(points)));
          cancelDrag = null;
        };
        cancelDrag = cancel;
        handle.addEventListener("routecancel", cancel);
        handle.onpointermove = (event) => {
          if (!canEdit() || !canvas.contains(path) || !handle.isConnected) {
            cancel();
            return;
          }
          moved = true;
          waypoints[i] = bounded({
            x: original.x + (event.clientX - start.x) / scale,
            y: original.y + (event.clientY - start.y) / scale,
          });
          place();
          paths(key).forEach((p) =>
            p.setAttribute("d", pathData(throughWaypoints(a, b, waypoints))),
          );
        };
        handle.onpointerup = () => {
          if (!canEdit() || !canvas.contains(path) || !handle.isConnected) {
            cancel();
            return;
          }
          handle.onpointermove = null;
          handle.onpointerup = null;
          handle.onpointercancel = null;
          handle.removeEventListener("routecancel", cancel);
          cancelDrag = null;
          if (moved) changed(key, waypoints);
        };
        handle.onpointercancel = cancel;
      });
      handle.addEventListener("keydown", (e) => {
        if ((e.key === "Delete" || e.key === "Backspace") && canEdit()) {
          e.preventDefault();
          remove(key, i);
          return;
        }
        const step = e.shiftKey ? 1 : 10,
          delta: Record<string, Point> = {
            ArrowLeft: { x: -step, y: 0 },
            ArrowRight: { x: step, y: 0 },
            ArrowUp: { x: 0, y: -step },
            ArrowDown: { x: 0, y: step },
          };
        if (!delta[e.key] || !canEdit()) return;
        e.preventDefault();
        waypoints[i] = bounded({
          x: point.x + delta[e.key].x,
          y: point.y + delta[e.key].y,
        });
        changed(key, waypoints);
        canvas
          .querySelectorAll<HTMLButtonElement>(".map-route-handle")
          [i]?.focus();
      });
    });
  };
  if (editingKey) show(editingKey);
  return {
    canEdit,
    remove,
    canAdd(key: string) {
      return canEdit() && (data(key)?.waypoints.length ?? 8) < 8;
    },
    add(key: string, clientX: number, clientY: number) {
      if (!canEdit()) return;
      const route = data(key);
      if (!route || route.waypoints.length >= 8) return;
      const rect = canvas.getBoundingClientRect(),
        scale = canvasScale(canvas);
      const at = {
        x: (clientX - rect.left) / scale,
        y: (clientY - rect.top) / scale,
      };
      // Project onto the clicked rendered segment, preserving waypoint order.
      const project = (p: Point) => {
        let distance = Infinity,
          length = 0,
          bestLength = 0,
          point = p;
        for (let j = 1; j < route.points.length; j++) {
          const a = route.points[j - 1],
            b = route.points[j];
          const q = {
            x: Math.max(Math.min(a.x, b.x), Math.min(Math.max(a.x, b.x), p.x)),
            y: Math.max(Math.min(a.y, b.y), Math.min(Math.max(a.y, b.y), p.y)),
          };
          const d = Math.hypot(q.x - p.x, q.y - p.y);
          if (d < distance) {
            distance = d;
            point = q;
            bestLength = length + Math.hypot(q.x - a.x, q.y - a.y);
          }
          length += Math.hypot(b.x - a.x, b.y - a.y);
        }
        return { point, length: bestLength };
      };
      const projected = project(at);
      const index = route.waypoints.findIndex(
        (p) => project(p).length > projected.length,
      );
      route.waypoints.splice(index < 0 ? route.waypoints.length : index, 0, {
        x: Math.max(0, Math.min(32768, Math.round(projected.point.x))),
        y: Math.max(0, Math.min(32768, Math.round(projected.point.y))),
      });
      editingKey = key;
      changed(key, route.waypoints);
    },
    show(key: string) {
      if (canEdit()) show(key);
    },
    reset(key: string) {
      if (!canEdit()) return;
      editingKey = null;
      changed(key);
    },
  };
}
