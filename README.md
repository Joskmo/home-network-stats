[English](README.md) | [Русский](README.ru.md)

# Home network stats

Owner-only Telegram bot for OpenWrt `nlbwmon` traffic accounting. A Linux server reads native cumulative counters over SSH every five minutes, stores conservative per-device RX + TX deltas in SQLite, and sends **pie charts**. No Python runs on the router. Existing proxy services are reused, never reconfigured.

## Commands

- `/start`, `/help`: help
- `/today`, `/yesterday`: measured traffic pie and coverage summary
- `/status`: last successful collection and collector health
- `/language ru` or `/language en`: persistent language choice (Russian default)

After 09:00 **Europe/Moscow**, the bot sends the previous day's report. Successful delivery is persisted across restarts; failed delivery is retried. This is not an exactly-once delivery guarantee: a crash after Telegram accepts a photo but before the SQLite marker commits can duplicate it. Missed older days are not automatically backfilled; startup after 09:00 sends yesterday only.

## Honest accounting

The first sample establishes a baseline; existing router counters are **not historical usage**. New-device baselines and reset counters are excluded. Intervals over 450 seconds and intervals crossing Moscow midnight are discarded rather than divided using invented estimates. Disappearing devices are flagged. Unaffected devices can still contribute measured bytes within an otherwise incomplete interval.

**Daily reports are generally partial**, even with a healthy collector, because the midnight-crossing interval is intentionally excluded. Monthly aggregates likewise represent measured lower bounds, not complete billed usage. Collection begins at installation; no earlier history is fabricated. Empty reports render safely without a pie. Traffic visible to `nlbwmon` depends on router accounting, topology and offloading; LAN switching and ISP billing are not guaranteed to match. Device history and charts are private data.

### Device names

The native `deploy/home-network-read` script exports only DHCP host identity fields. Install it as `/usr/libexec/home-network-read` on OpenWrt with executable permissions. The bot refreshes the inventory with each collection and persists labels in SQLite. Static DHCP names take priority over lease names; nameless leases fall back to their IP. The dashboard uses the same labels as the bot, retaining separate MAC-based accounting for devices with identical names. Unknown devices are not assigned invented names; their MAC remains available in the table tooltip. Rename a static DHCP reservation in OpenWrt to change its display label after the next collection.

### Network map

The authenticated dashboard includes a bilingual topology editor: device-type
icons, router/switch port labels, distinct Ethernet and Wi-Fi connections, automatic
layout, and unmanaged-switch insertion into a cable. Read-only router discovery
provides observation paths, not invented physical wiring. Edit uncertain device
types and physical port mappings manually, then save the map.
See [topology usage, discovery limits and deployment](deploy/TOPOLOGY.md).

### Frontend development

Browser source lives in `frontend/` and uses strict TypeScript. Do not edit the
generated `dashboard/static/*.js` bundles. See [architecture and component
boundaries](docs/ARCHITECTURE.md).

```sh
npm ci
npm run build
npm test
python -m unittest discover -v
```

Node 22 is used in CI and the Docker build stage. The serving container remains
Python-only; Docker builds the browser bundles automatically. Local Python tests
that inspect static assets require `npm run build` first.

## Requirements and setup

Python 3.11+ on Linux, OpenSSH client, systemd user services, an existing OpenWrt `nlbwmon` installation, and an existing HTTP proxy at `http://127.0.0.1:10818` (Mihomo in the reference deployment). Telegram explicitly uses this proxy with environment proxy inheritance disabled. The proxy address currently lives in `telegram_client.py`, not a runtime setting.

1. Create a Telegram bot with BotFather, send `/start` to it from the intended owner's private account, and obtain that account's positive numeric user ID.
2. Install this source on the Linux server. The reference path is `/srv/self-hosted-music/traffic-telegram-bot`; change both service paths if using another directory.
3. Create the virtual environment and install dependencies:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -m unittest test_bot test_history test_reports test_localization test_telegram test_app test_runtime -v
   ```
4. Give the service user a dedicated SSH key and independently verify the router host key in `~/.ssh/known_hosts`. The collector uses strict host verification, batch mode and only the configured identity. Permit only `nlbw -c json -g mac` through a restricted router-side key/command wrapper where possible. This command reads memory; do not add `commit` or router-side scripts in Python. Preserve other authorized keys.
5. Create `~/.config/home-network-stats/` as mode 0700. Put the real token in a separate `telegram-token` file, owned by the service user and mode 0600. Copy `deploy/runtime.env.example` to `~/.config/home-network-stats/runtime.env`, replace every placeholder, and set mode 0600. Never commit either runtime file. `TRAFFIC_DATA_DIR` must be a writable dedicated directory (0700); the database is `traffic.sqlite3` inside it.
6. Before starting the service, load the protected environment and verify the real connection:

   ```sh
   set -a
   . "$HOME/.config/home-network-stats/runtime.env"
   set +a
   .venv/bin/python main.py verify
   .venv/bin/python main.py collect-once
   # Wait for a real second sample; first sample is only a baseline.
   .venv/bin/python main.py send-today
   ```

   `verify` calls Telegram `getMe` and `getChat` through the proxy and reads native router counters. `send-today` sends a real photo to the configured owner. A process lock prevents these CLI actions from running while the service is active.
7. Install and enable the user unit:

   ```sh
   mkdir -p ~/.config/systemd/user
   cp deploy/home-network-stats.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now home-network-stats.service
   systemctl --user is-active home-network-stats.service
   journalctl --user -u home-network-stats.service -n 20 --no-pager
   loginctl show-user "$USER" -p Linger
   ```

   An administrator may need `loginctl enable-linger SERVICE_USER` for boot/login-independent operation. Verify repeated `Collection succeeded` entries, not just an active process. The service restarts on failure, uses a private umask and does not modify proxy/router services.

## Security and maintenance

Inbound commands require **both** matching sender ID and matching private chat ID. Groups, forwarded channel identities and other users cannot choose an outbound recipient; every send targets the configured owner. The owner language, polling offset, daily-send date and last photo message ID persist in SQLite. No bot token, real owner ID, private inventory or captured traffic belongs in this repository.

Stop the service before manual sends, updates or database migration, then start it again. For backup/migration, acquire the same `data/bot.lock`, checkpoint WAL and use SQLite's backup API; copying just the main `.sqlite3` file while writers run can lose committed data. Compare rows and run `PRAGMA integrity_check`, update only the protected runtime environment, and retain a protected backup until verified. For live read-only dashboard access, mount the data directory read-only (including any WAL/SHM files), match the service UID and call `history.read_report(path, date, now)`; do not create an empty fallback database.

There is no retention pruning yet; monitor data disk growth. Polling/Telegram failures do not reset the collection schedule, but synchronous long polling/network timeouts may delay individual samples. Automated tests use synthetic counters only and never insert them into the live database. Dashboard code and deployment are separate; see its documentation where present.
