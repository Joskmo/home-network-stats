[English](ARCHITECTURE.md) | [Русский](ARCHITECTURE.ru.md)

# Architecture

This is a small, single-owner application, not a distributed platform. Its runtime
boundaries are the browser, the dashboard HTTP process, host-side collectors, and
the Telegram reporting process. No Python or JavaScript runtime is installed on
the router. The frontend is authored in strict TypeScript; browser JavaScript is
a generated build artifact, not a second source tree.

## Components and ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| `frontend/shared/` | Typed HTTP/session contracts and DOM utilities | Router access or persistent credentials |
| `frontend/topology/` | Topology model, layout, evidence presentation, editor and rendering | Authentication policy, SSH, authoritative persistence |
| Browser dashboard/security entrypoints | Traffic presentation, authentication and trusted-device forms | Password verification or identity proof |
| `dashboard/web.py` | HTTP routing, request limits, auth/CSRF gates, static asset allowlist | Discovery parsing or chart calculations |
| `dashboard/auth.py`, `dashboard/access.py` | Password sessions, cooldowns, request-scoped LAN identity | Topology-based authorization |
| `dashboard/topology.py` | Validated graph persistence, revision checks, ICMP snapshots | Inferring physical cables |
| `dashboard/discovery.py` | Read-only native collection, MAC-based identity merge | Replacing manual wiring or trusting clients |
| `dashboard/inventory.py`, `dashboard/sampler.py` | Host-side identity and WAN sampling | Browser-provided identity claims |
| `dashboard/data.py` | Read-only history/speed projection | Counter writes or historical backfills |
| `main.py`, `app.py` | Bot composition, collection loop, commands and daily scheduling | Dashboard HTTP state |
| `collector.py`, `nlbw.py`, `devices.py` | Native counters, parsing and DHCP names | Router configuration changes |
| `history.py`, `reports.py`, `telegram_client.py` | Measured deltas, charts and owner-only delivery | Invented traffic or arbitrary recipients |

## Topology data flow

The browser map is split by responsibility, not just by file size:
`types.ts` defines the graph contract; `domain.ts` owns graph transformations;
`layout.ts` computes geometry; `observations.ts` interprets attachment evidence;
`rendering.ts` paints the graph; `editor.ts` builds forms; `controller.ts` owns the
active draft and request lifecycle; `i18n.ts` contains the two language catalogs.
Pure modules have no DOM or HTTP dependency. The renderer/editor communicate
with the controller through typed callbacks. The shared `DashboardBridge` exposes
the current session/language and typed HTTP capability to the three entry bundles.

1. Host collectors read DHCP identity, forwarding evidence and Wi-Fi associations
   using existing SSH access and native router commands.
2. Discovery snapshots are evidence, not physical wiring and not authorization.
3. Import validates the draft, merges identities by MAC, and preserves manual
   names, port inventories, connections and absent historical nodes.
4. The browser edits a draft. Applying discovery is not saving the map.
5. Save submits the complete graph with its revision; the backend validates it and
   atomically persists only if the revision is still current.
6. ICMP results are joined by node ID **and matching IP** and expire independently.

Device types and connection media are explicit domain values. Wi-Fi is shown as
a badge without connecting lines. An observed LAN port means reachability through
that interface; it does not assert that a switch exists or that a cable is direct.
An unmanaged switch and its internal port mapping remain explicit user input.

## Map presentation principles

The map is a monitoring/inspection surface, not an always-labelled wiring report.
Keep connections quiet until the user inspects a device or port. Draw identifiable
port sockets on devices and attach each connection to its corresponding socket.
Show large endpoint names and port labels in an inspector, not repeated SVG text
over the cables. Hover, keyboard focus and touch must all expose this information.
An observed interface is not a verified chassis socket: mark the evidence and
leave an unknown remote port unknown. Never invent port numbers or Wi-Fi cables.

References inspected for these general interaction principles (not dependencies):
- [yFiles Network Monitoring](https://www.yfiles.com/demos/showcase/networkmonitoring/):
  distinct device symbols, unobtrusive connections, contextual details.
- [React Flow handles](https://reactflow.dev/learn/customization/handles):
  multiple individually identified connection points on a node.

## Build and delivery

- `frontend/` is the browser source of truth. `tsconfig.json` enforces strict typing.
- `package-lock.json` pins frontend dependencies; install with `npm ci`.
- `npm run typecheck` checks contracts; `npm run build` emits browser bundles to
  `dashboard/static/`; `npm test` exercises frontend model behavior.
- Generated `app.js`, `topology.js` and `security.js` are ignored by Git.
- Docker builds the frontend in a Node stage and copies only its output into the
  Python runtime. Node/npm do not run in the serving container.
- GitHub Actions builds before Python static-asset tests and runs isolated browser
  tests against both the UI fixture and real HTTP/auth/storage path.

## State and trust boundaries

The serving container runs read-only except its existing auth/topology mounts.
History, speed and inventory mounts remain read-only. SSH keys stay on the host;
no router key is mounted into the web application. Runtime `.env`, tokens,
password state, discovered inventory and browser artifacts are not Git content.

LAN convenience access requires the exact trusted ingress and fresh independent
inventory. A node on the network map grants no access. Physical topology, DHCP
identity, neighbor reachability and ICMP response are different observations.

## Scope of this refactor

The TypeScript migration separates browser responsibilities and makes the build
reproducible. It does not change the Python HTTP API, introduce a frontend
framework, move runtime data, broaden LAN access, or rewrite the bot into a new
package hierarchy. Backend modules retain their existing tested responsibilities;
future changes should follow these boundaries rather than adding another parallel
implementation.
