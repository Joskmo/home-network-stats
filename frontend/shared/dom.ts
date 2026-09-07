interface Controls {
  password: HTMLInputElement;
  confirm: HTMLInputElement;
  submit: HTMLButtonElement;
  pie: HTMLCanvasElement;
  "map-save": HTMLButtonElement;
  "map-form": HTMLFormElement;
}
export function $<K extends keyof Controls>(id: K): Controls[K];
export function $(id: string): HTMLElement;
export function $(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Missing dashboard element: ${id}`);
  return node;
}
export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  cls?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
export function button(
  text: string,
  callback: (event: MouseEvent) => void,
): HTMLButtonElement {
  const node = element("button", text);
  node.type = "button";
  node.addEventListener("click", callback);
  return node;
}
export function control(
  id: string,
): HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement {
  const node = $(id);
  if (
    node instanceof HTMLInputElement ||
    node instanceof HTMLSelectElement ||
    node instanceof HTMLTextAreaElement
  )
    return node;
  throw new Error(`Not a form control: ${id}`);
}
