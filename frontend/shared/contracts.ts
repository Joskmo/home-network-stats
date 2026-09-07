import type { Graph, TopologyResponse } from "../topology/types";
export type Language = "en" | "ru";
export interface Session {
  authenticated?: boolean;
  must_change?: boolean;
  csrf?: string;
  password_authenticated?: boolean;
  trusted_device?: boolean;
}
export interface TrafficDevice {
  name: string;
  mac?: string;
  bytes: number;
}
export interface Stats {
  generated_at: number;
  speed: {
    download_bps: number | null;
    upload_bps: number | null;
    stale: boolean;
  };
  monthly: {
    available: boolean;
    total_bytes: number;
    month: string;
    partial: boolean;
    collection_started: number | null;
    covered_seconds: number;
    devices: TrafficDevice[];
  };
}
export interface TrustedDevice {
  id: string;
  name: string;
  ip?: string;
  trusted?: boolean;
}
export interface Trusted {
  devices: TrustedDevice[];
  trusted: TrustedDevice[];
}
export interface Responses {
  "/api/session": Session;
  "/api/login": Session;
  "/api/password": Session;
  "/api/logout": Session;
  "/api/recover": Session;
  "/api/stats": Stats;
  "/api/trusted": Trusted;
  "/api/topology": TopologyResponse;
  "/api/topology/preview": Graph;
}
export interface Payloads {
  "/api/session": undefined;
  "/api/login": { password: string };
  "/api/password": { password: string };
  "/api/logout": Record<string, never>;
  "/api/recover": { password: string };
  "/api/stats": undefined;
  "/api/trusted": { action: "add" | "remove"; device_id: string };
  "/api/topology": { topology: Graph };
  "/api/topology/preview": { topology: Graph };
}
export type ApiResponse<P extends keyof Responses, B> = P extends "/api/trusted"
  ? B extends undefined
    ? Trusted
    : { ok: true }
  : Responses[P];
export type Api = <
  P extends keyof Responses,
  B extends Payloads[P] | undefined = undefined,
>(
  path: P,
  payload?: B,
) => Promise<ApiResponse<P, B>>;
/** The only cross-bundle capability. Consumers do not own auth or language. */
export interface DashboardBridge {
  readonly version: 1;
  readonly session: Readonly<Session>;
  readonly language: Language;
  api: Api;
  translate(key: string): string;
  replaceSession(session: Session): void;
}
declare global {
  interface Window {
    dashboardBridge?: DashboardBridge;
  }
}
export function getBridge(): DashboardBridge {
  const bridge = window.dashboardBridge;
  if (!bridge || bridge.version !== 1)
    throw new Error("Dashboard bridge v1 must be initialized by app.js");
  return bridge;
}
