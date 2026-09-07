export type NodeType =
  | "router"
  | "switch"
  | "ap"
  | "server"
  | "phone"
  | "laptop"
  | "desktop"
  | "tablet"
  | "tv"
  | "printer"
  | "iot"
  | "device"
  | "other";
export interface Point {
  x: number;
  y: number;
}
export interface Discovery {
  source: string;
  attachment: string | null;
  confidence: string;
  last_seen: number | null;
}
export interface NetworkNode extends Point {
  id: string;
  name: string;
  type: NodeType;
  ip: string;
  mac: string;
  ports?: string[];
  discovery?: Discovery;
}
export interface Cable {
  id: string;
  source: string;
  target: string;
  source_port: string;
  target_port: string;
  medium?: "ethernet" | "wifi";
  observation?: false;
  label?: never;
}
export interface Observation {
  source: string;
  target: string;
  medium: "wifi" | "via";
  observation: true;
  label: string;
  source_port?: never;
  target_port?: never;
}
export interface Graph {
  revision: number;
  nodes: NetworkNode[];
  links: Cable[];
}
export interface MonitorStatus {
  state: "online" | "no_reply" | "unknown";
  checked_at: number | null;
}
export type Monitor = Record<string, MonitorStatus>;
export type Positions = Record<string, Point>;
export type ItemKind = "nodes" | "links";
export interface Drag extends Point {
  id: string;
  startX: number;
  startY: number;
  moved: boolean;
}
export interface TopologyResponse extends Graph {
  monitor?: Monitor;
}
