import type { Point } from "./types";

export const CARD_WIDTH = 208;
export const PORT_COLUMNS = 4;
export const PORT_STEP = 52;
export const PORT_TOP = 120;
export const PORT_ROW = 30;
export const PORT_HEIGHT = 22;
export function cardHeight(count: number): number {
  return count
    ? PORT_TOP + Math.ceil(count / PORT_COLUMNS) * PORT_ROW + 16
    : 114;
}
export function socketPosition(index: number): Point {
  return {
    x: (index % PORT_COLUMNS) * PORT_STEP,
    y: PORT_TOP + Math.floor(index / PORT_COLUMNS) * PORT_ROW,
  };
}
export function anchor(position: Point, ports: string[], port?: string): Point {
  const index = ports.indexOf(port ?? "");
  if (index < 0) return { x: position.x + CARD_WIDTH / 2, y: position.y + 114 };
  const p = socketPosition(index);
  return { x: position.x + p.x + 25, y: position.y + p.y + PORT_HEIGHT };
}
