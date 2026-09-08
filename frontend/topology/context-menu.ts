import { element, button } from "../shared/dom";

export interface MenuItem {
  label: string;
  run(): void;
  disabled?: boolean;
}
let dismiss: (() => void) | null = null;
export function closeContextMenu() {
  dismiss?.();
}
/** A scoped, keyboard-operable menu. Global listeners exist only while open. */
export function contextMenu(
  scope: HTMLElement,
  x: number,
  y: number,
  items: MenuItem[],
) {
  closeContextMenu();
  const previous = document.activeElement;
  const menu = element("div", undefined, "map-context-menu");
  menu.setAttribute("role", "menu");
  const abort = new AbortController();
  const close = (restore = false) => {
    abort.abort();
    menu.remove();
    dismiss = null;
    if (restore && previous instanceof Element && previous.isConnected) {
      if (previous instanceof HTMLElement || previous instanceof SVGElement)
        previous.focus({ preventScroll: true });
    }
  };
  dismiss = () => close();
  for (const item of items) {
    const b = button(item.label, () => {
      if (!item.disabled) {
        close();
        item.run();
      }
    });
    b.setAttribute("role", "menuitem");
    b.disabled = !!item.disabled;
    menu.append(b);
  }
  document.body.append(menu);
  const rect = scope.getBoundingClientRect();
  const left = Math.max(4, rect.left),
    top = Math.max(4, rect.top);
  const right = Math.min(innerWidth - 4, rect.right),
    bottom = Math.min(innerHeight - 4, rect.bottom);
  menu.style.maxWidth = Math.max(100, right - left) + "px";
  menu.style.maxHeight = Math.max(48, bottom - top) + "px";
  menu.style.left =
    Math.max(left, Math.min(x, right - menu.offsetWidth)) + "px";
  menu.style.top =
    Math.max(top, Math.min(y, bottom - menu.offsetHeight)) + "px";
  const enabled = [
    ...menu.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
  ];
  enabled[0]?.focus({ preventScroll: true });
  document.addEventListener(
    "pointerdown",
    (e) => {
      if (!menu.contains(e.target as Node)) close();
    },
    { signal: abort.signal, capture: true },
  );
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close(true);
      } else if (e.key === "Tab") close();
      else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
        e.preventDefault();
        const i = enabled.indexOf(document.activeElement as HTMLButtonElement);
        const next =
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? enabled.length - 1
              : (i + (e.key === "ArrowDown" ? 1 : -1) + enabled.length) %
                enabled.length;
        enabled[next]?.focus();
      }
    },
    { signal: abort.signal, capture: true },
  );
  window.addEventListener("resize", () => close(), { signal: abort.signal });
  document.addEventListener(
    "scroll",
    (e) => {
      if (!menu.contains(e.target as Node)) close();
    },
    { signal: abort.signal, capture: true },
  );
}
