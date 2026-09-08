import { button } from "../shared/dom";
import { pathData, throughWaypoints } from "./routing";
import type { Graph, Point } from "./types";
let editingKey: string | null = null;
export function canvasScale(canvas: HTMLElement): number {
  return canvas.getBoundingClientRect().width / canvas.offsetWidth || 1;
}
export function resetRouteEditor(): void {
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
  canEdit: () => boolean,
) {
  const show = (key: string) => {
    editingKey = key;
    canvas.querySelectorAll(".map-route-handle").forEach((e) => e.remove());
    const path = [
      ...canvas.querySelectorAll<SVGPathElement>("[data-route]"),
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
          path.setAttribute("d", pathData(points));
        };
        handle.addEventListener("routecancel", cancel);
        handle.onpointermove = (event) => {
          if (!canEdit()) {
            cancel();
            return;
          }
          moved = true;
          waypoints[i] = bounded({
            x: original.x + (event.clientX - start.x) / scale,
            y: original.y + (event.clientY - start.y) / scale,
          });
          place();
          path.setAttribute("d", pathData(throughWaypoints(a, b, waypoints)));
        };
        handle.onpointerup = () => {
          if (!canEdit()) {
            cancel();
            return;
          }
          handle.onpointermove = null;
          handle.onpointerup = null;
          handle.onpointercancel = null;
          handle.removeEventListener("routecancel", cancel);
          if (moved) changed(key, waypoints);
        };
        handle.onpointercancel = cancel;
      });
      handle.addEventListener("keydown", (e) => {
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
