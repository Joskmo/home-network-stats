# Network topology / Карта сети

Add devices and physical cables in the authenticated dashboard. Every cable has
labels for BOTH physical ports. Editing / dragging changes only the draft;
**Save map** persists it. Reload discards the draft after confirmation. Revision
conflicts refuse stale writes. Delete a device also deletes attached cables.
No physical topology is invented. Unmanaged switches can be drawn without IPs.
RU/EN follows the existing language switch. Positions can also be edited numerically.

## Device identity, ports and connections / Устройства, порты и связи

Device types include router, switch, access point, server, phone, laptop, desktop,
tablet, TV, printer and IoT. Choose the client type manually when discovery cannot
establish it: a DHCP name or MAC vendor alone is not proof of device class.
Each node may have an editable `ports` list (up to 48 unique labels, 32 characters
each). It describes your physical port inventory; the application does not invent
the router's port count or translate a Linux interface into a chassis label.

Connections may explicitly use `medium: ethernet` or `medium: wifi`. Old saved
connections without `medium` remain Ethernet. Endpoint labels remain mandatory;
for Wi-Fi they identify radio/interface labels rather than RJ45 sockets.
Wi-Fi is displayed with a device badge, never a connecting line. Observed LAN
ports use the neutral label "Observed LAN port", not "not direct". A manual
connection is your physical-layout declaration, not live link-state telemetry.
An unmanaged switch needs neither IP nor MAC; inserting one into an Ethernet
cable preserves the two original endpoint labels and adds two switch-side ports.
Edit its actual port labels to match the hardware, then save the draft.

На карте можно указать тип клиента: телефон, ноутбук, компьютер, планшет,
телевизор, принтер или IoT. Если тип неизвестен, выберите его вручную — имя DHCP
не доказывает, что это за устройство. Список портов редактируется отдельно:
укажите маркировку на корпусе роутера/коммутатора. Имена Linux-интерфейсов и
физическая нумерация портов не считаются автоматически эквивалентными.

Кабель Ethernet и Wi-Fi различаются типом связи. Wi-Fi показан значком без линий.
Подпись «Обнаруженный LAN-порт» не утверждает, что подключение не прямое.
В разрыв кабеля можно добавить
неуправляемый коммутатор без IP/MAC; исходные порты на концах сохраняются.
Уточните номера портов коммутатора и сохраните карту. Отсутствие IP у него
означает отсутствие ICMP-проверки, а не неисправность.

## Inspect, route and zoom / Просмотр, линии и масштаб

Manual cables and detected LAN paths use the same orthogonal routing, with
obstacle avoidance and separated lanes. Hover/focus a device or port, or tap its
port on touch screens, to inspect large endpoint labels without permanent text
on the wires. The inspector distinguishes declared cables from forwarding
observations. `Internet` and `WAN` are a schematic upstream marker, not a newly
discovered host or an Internet availability measurement.

Select **Adjust route** in the inspector and drag the bend handles (arrow keys
also work); **Reset route to automatic** removes that adjustment. **Save map**
persists device positions and route metadata. Discovery preview preserves routes;
route geometry never changes physical connectivity. Zoom out/in and **Fit map**
affect only the view. Editing and dragging account for the current scale.
Saved coordinates allow `0..32768` on both axes; large maps no longer substitute
a session-only layout for saved positions. Route metadata is optional, bounded
to 128 routes with up to 8 points each, and backward-compatible with old maps.

Наведите курсор на устройство/порт или выберите порт касанием: в панели появятся
крупные подписи концов подключения. Постоянных надписей поверх линий нет.
Ручные кабели и обнаруженные пути прокладываются одинаково, прямоугольными
участками; происхождение данных указано в панели. `Internet → WAN` — обозначение
внешнего подключения, не отдельное обнаруженное устройство и не проверка интернета.

В панели подключения выберите правку маршрута и перетащите точки перегиба.
Сброс возвращает автоматическую прокладку. **Сохранить карту** записывает и позиции
устройств, и поправки линий; изменение трассы не меняет порты/соединения.
Уменьшение масштаба и **Вместить карту** позволяют работать с большой схемой.
Автоматическое обновление больше не заменяет сохранённые позиции большой карты.

If saving is rejected specifically because its CSRF token expired, the client
refreshes the session and retries the captured topology once without reloading
the draft. Expired authorization still requires login; conflicts and network
failures are not automatically retried. Finish or cancel an open device/cable
editor before saving the map. An unsuccessful save does not mean the draft is
stored: do not reload the page until it has been saved or otherwise backed up.

При устаревшем CSRF-токене сессия обновляется, а сохранение повторяется один раз
без перезагрузки черновика. Авторизация не обходится; конфликт ревизий и сетевой
сбой не вызывают автоматического повтора. Перед сохранением примените или
отмените открытое редактирование устройства/кабеля. При ошибке не обновляйте
вкладку, пока черновик не сохранён или не скопирован отдельно.

## Discovery evidence / Данные обнаружения

The collector reads the router's own `br-lan` address/MAC using native `ip` and
sysfs, so the gateway can appear as a router rather than being absent from DHCP
client discovery. This is read-only; no new router packages or configuration.
An `iw station` observation identifies Wi-Fi association. An FDB observation
identifies reachability **via** an interface, not a direct Ethernet cable. Neither
source reveals the physical internals of an unmanaged switch. Discovery import
remains explicit preview → apply to draft → save; manual names, wiring, port
inventories and device types survive refresh (a generic device representing the
router's own interface is upgraded to router).

Автосбор читает собственные IP/MAC интерфейса `br-lan`, чтобы показать роутер.
Wi-Fi определяется по `iw station`; FDB показывает путь **через** интерфейс,
но не доказывает прямой кабель. Неуправляемый коммутатор и его внутренние
соединения автоматически не видны. Обновление: предпросмотр → применить →
сохранить. Ручная схема и список портов не затираются наблюдениями.

Добавьте устройства и кабели вручную; укажите физический порт с каждой стороны.
После правок или перетаскивания нажмите «Сохранить карту». Удаление устройства
удаляет его кабели. Без IP состояние остаётся неизвестным.

## Storage and limits

`DASHBOARD_TOPOLOGY_DIR=/topology` in the container; separate owner-only bind
folder `/srv/self-hosted-music/home-network-dashboard/topology` on the host,
override source via `DASHBOARD_TOPOLOGY_DIR` when invoking Compose. Files
`topology.json` and `status.json` are atomic JSON snapshots (0600), directory 0700.
64 nodes / 128 links; bounded strings and coordinates; cross-process flock plus
revision compare-and-swap protects concurrent editors. Both topology endpoints
use existing auth/password-rotation gate, and POST also requires CSRF + Origin.

## Host monitor deployment (no Python or changes on router)

As service user uid1000 on the server:

```sh
install -d -m 700 /srv/self-hosted-music/home-network-dashboard/topology
install -m 644 deploy/home-network-topology-monitor.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now home-network-topology-monitor.service
systemctl --user is-active home-network-topology-monitor.service
```

Service uses host `/usr/bin/python3` and `/usr/bin/ping`. Standard Linux ping
sockets must permit the service user's group (`net.ipv4.ping_group_range`). Do
not give the dashboard container ICMP capabilities. Probe errors yield UNKNOWN,
not false no-reply. 8 workers, 2-second process deadline, one ping per unique IP,
30-second cadence; only literal unicast `192.168.1.1` through `192.168.1.254`.
Router is allowed. No hostnames, URLs, shell commands, custom commands or TCP
ports accepted. Current deployment's LAN is deliberately fixed; changing ingress
`DASHBOARD_LAN_NETWORK` does not broaden probe permissions.

`online` means ICMP reply, `no_reply` means ping returned no reply (NOT proof of
offline), `unknown` means absent/no IP/error/stale >90 seconds. Last checked is
shown. Editing an IP invalidates previous-IP status. Initial map is empty.

Rebuild using BOTH existing Compose files and existing runtime environment:

```sh
docker compose --env-file ../dashboard.env -f compose.dashboard.yml -f compose.dashboard.lan.yml up -d --build
```

Verify exact live Compose environment path before use; keep existing
DASHBOARD_TRUSTED_LAN_PROXY and LAN override. Never replace auth/state.json,
bootstrap, proxy configuration, or router collector setup. Host monitor shares
only topology directory with the container; existing speed/history mounts remain
read-only. Auth changes can be deployed in the same rebuild by the parent agent.

Build frontend first: `npm ci && npm run build` (TypeScript is the source).
Docker performs this build in its Node stage; no Node runtime is needed on the
router or in the serving container.
Tests: `uv run --python 3.13 python -m unittest test_topology test_dashboard -v`.
Isolated headless Playwright QA uses a temporary auth state, never production.

Frontend regression checks: `npm test`.
Browser checks: `uv run --with playwright python tests/topology-ui-qa.py` and
`uv run --with playwright python tests/topology-integration-qa.py` (install the
headless browser once with `uv run --with playwright playwright install chromium`).
The latter starts the real application on an ephemeral loopback port, exercises
password rotation and map persistence, and deletes its isolated test state on exit.
All QA device names and connections are fixtures, not discovered LAN inventory.
