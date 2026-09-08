import { canvasScale } from "./route-editor";

/** One persistent zoom value; listeners and pointer capture belong to a shell. */
export function createViewport() {
  let zoom = 1;
  let dispose = () => {};
  let scroll: HTMLElement | null = null;
  let canvas: HTMLElement | null = null;
  let panning = false;
  let wheelUntil = 0;
  // Bounded virtual padding permits native panning even when the map fits.
  const padding = 4096;
  let sizePlane = () => {};
  function setZoom(value: number, x?: number, y?: number) {
    if (!scroll || !canvas) return;
    const viewport = scroll.getBoundingClientRect();
    x ??= viewport.left + scroll.clientWidth / 2;
    y ??= viewport.top + scroll.clientHeight / 2;
    const before = canvas.getBoundingClientRect();
    const scale = canvasScale(canvas);
    const world = { x: (x - before.left) / scale, y: (y - before.top) / scale };
    zoom = Math.max(0.25, Math.min(1.5, value));
    canvas.style.zoom = String(zoom);
    canvas.style.setProperty("--map-zoom", String(zoom));
    sizePlane();
    const after = canvas.getBoundingClientRect();
    scroll.scrollLeft += after.left + world.x * canvasScale(canvas) - x;
    scroll.scrollTop += after.top + world.y * canvasScale(canvas) - y;
  }
  return {
    get interacting() {
      return panning || performance.now() < wheelUntil;
    },
    zoomBy(delta: number) {
      setZoom(zoom + delta);
    },
    fit() {
      if (!canvas || !scroll) return;
      setZoom(
        Math.min(
          1,
          (scroll.clientWidth - 16) / canvas.offsetWidth,
          (scroll.clientHeight - 44) / canvas.offsetHeight,
        ),
      );
      scroll.scrollTo(
        padding - (scroll.clientWidth - canvas.offsetWidth * zoom) / 2,
        padding +
          44 * zoom -
          (scroll.clientHeight - canvas.offsetHeight * zoom) / 2,
      );
    },
    dispose() {
      dispose();
      scroll = null;
      canvas = null;
    },
    attach(host: HTMLElement, field: HTMLElement) {
      dispose();
      scroll = host;
      canvas = field;
      field.style.zoom = String(zoom);
      field.style.setProperty("--map-zoom", String(zoom));
      const plane = document.createElement("div");
      plane.className = "map-pan-plane";
      field.before(plane);
      plane.append(field);
      plane.style.padding = padding + "px";
      sizePlane = () => {
        plane.style.width = field.offsetWidth * zoom + "px";
        plane.style.height = (field.offsetHeight + 44) * zoom + "px";
      };
      sizePlane();
      host.scrollTo(padding, padding);
      const observer = new ResizeObserver(sizePlane);
      observer.observe(field);
      host.tabIndex = 0;
      const abort = new AbortController();
      const options = { signal: abort.signal };
      let space = false;
      let pan: {
        id: number;
        x: number;
        y: number;
        left: number;
        top: number;
      } | null = null;
      let suppressClick = false;
      const stop = () => {
        const id = pan?.id;
        pan = null;
        panning = false;
        if (id !== undefined && host.hasPointerCapture(id))
          host.releasePointerCapture(id);
        host.classList.remove("is-panning");
      };
      host.addEventListener(
        "wheel",
        (e) => {
          wheelUntil = performance.now() + 400;
          if (!e.ctrlKey) return;
          e.preventDefault();
          const delta =
            e.deltaY *
            (e.deltaMode === 1
              ? 16
              : e.deltaMode === 2
                ? host.clientHeight
                : 1);
          setZoom(zoom * Math.exp(-delta * 0.002), e.clientX, e.clientY);
        },
        { ...options, passive: false },
      );
      host.addEventListener(
        "keydown",
        (e) => {
          if (
            e.code === "Space" &&
            !(
              e.target instanceof Element &&
              e.target.closest("input,textarea,select,[contenteditable]")
            )
          ) {
            e.preventDefault();
            space = true;
          }
          if (e.key === "Escape") {
            space = false;
            stop();
          }
        },
        options,
      );
      window.addEventListener(
        "keyup",
        (e) => {
          if (e.code === "Space") {
            space = false;
            stop();
          }
        },
        options,
      );
      window.addEventListener(
        "blur",
        () => {
          space = false;
          stop();
        },
        options,
      );
      host.addEventListener(
        "pointerdown",
        (e) => {
          if (e.button !== 1 && !(e.button === 0 && space)) return;
          e.preventDefault();
          e.stopImmediatePropagation();
          host.focus({ preventScroll: true });
          pan = {
            id: e.pointerId,
            x: e.clientX,
            y: e.clientY,
            left: host.scrollLeft,
            top: host.scrollTop,
          };
          panning = true;
          suppressClick = true;
          host.setPointerCapture(e.pointerId);
          host.classList.add("is-panning");
        },
        { ...options, capture: true },
      );
      host.addEventListener(
        "pointermove",
        (e) => {
          if (!pan || pan.id !== e.pointerId) return;
          host.scrollTo(
            pan.left + pan.x - e.clientX,
            pan.top + pan.y - e.clientY,
          );
        },
        options,
      );
      host.addEventListener("pointerup", stop, options);
      host.addEventListener("pointercancel", stop, options);
      host.addEventListener("lostpointercapture", stop, options);
      host.addEventListener(
        "click",
        (e) => {
          if (!suppressClick) return;
          suppressClick = false;
          e.preventDefault();
          e.stopImmediatePropagation();
        },
        { ...options, capture: true },
      );
      host.addEventListener(
        "pointerdown",
        (e) => {
          if (!space && e.button === 0) suppressClick = false;
        },
        options,
      );
      dispose = () => {
        stop();
        abort.abort();
        observer.disconnect();
        sizePlane = () => {};
      };
    },
  };
}
