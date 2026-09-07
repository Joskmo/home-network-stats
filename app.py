"""Small command handler and persistent daily-report scheduler."""

import json
import logging
from datetime import date, datetime, timedelta

from devices import display_names
from history import MSK
from localization import translate
from reports import render_report

LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, history, telegram, collector, inventory=None):
        self.history = history
        self.telegram = telegram
        self.collector = collector
        self.inventory = inventory

    @property
    def language(self):
        return self.history.get_meta("language", "ru")

    def text(self, key, **values):
        return translate(self.language, key, **values)

    def collect_once(self, now: datetime | None = None) -> bool:
        try:
            counters = self.collector()
            stamp = (now or datetime.now(MSK)).timestamp()
            self.history.record(stamp, counters)
            if self.inventory is not None:
                try:
                    names = json.loads(self.history.get_meta("device_names", "{}"))
                    names.update(self.inventory())
                    self.history.set_meta("device_names", json.dumps(names))
                except Exception as error:
                    LOG.warning("Inventory refresh failed: %s", type(error).__name__)
            LOG.info("Collection succeeded: %d devices", len(counters))
            return True
        except Exception as error:
            # Do not log raw exception text: it can contain private inventory.
            self.history.set_meta("last_error", type(error).__name__)
            LOG.warning("Collection failed: %s", type(error).__name__)
            return False

    def send_report(self, day: date, now: datetime) -> dict:
        report = self.history.report(day, now.timestamp())
        names = json.loads(self.history.get_meta("device_names", "{}"))
        report["device_names"] = names | display_names(report["devices"], names)
        png, caption = render_report(report, self.language)
        result = self.telegram.send_photo(png, caption)
        self.history.set_meta("last_report_message_id", result["message_id"])
        LOG.info("Report accepted by Telegram: message_id=%s", result["message_id"])
        return result

    def handle_update(self, update: dict, now: datetime) -> None:
        message = update.get("message", {})
        if self.telegram.authorized(message):
            parts = message.get("text", "").strip().split()
            if parts:
                command = parts[0].split("@", 1)[0].lower()
                if command == "/language":
                    if len(parts) == 2 and parts[1] in ("ru", "en"):
                        self.history.set_meta("language", parts[1])
                        self.telegram.send_text(self.text("language"))
                    else:
                        self.telegram.send_text(self.text("language_help"))
                elif command in ("/start", "/help"):
                    self.telegram.send_text(self.text("help"))
                elif command == "/status":
                    last = self.history.get_meta("last_success")
                    last = (
                        datetime.fromtimestamp(float(last), MSK).strftime(
                            "%Y-%m-%d %H:%M:%S MSK"
                        )
                        if last
                        else self.text("never")
                    )
                    health = self.text(
                        "failed" if self.history.get_meta("last_error") else "healthy"
                    )
                    self.telegram.send_text(
                        self.text("status", last=last, health=health)
                    )
                elif command in ("/today", "/yesterday"):
                    day = now.date() - timedelta(days=command == "/yesterday")
                    self.send_report(day, now)
                else:
                    self.telegram.send_text(self.text("unknown"))
        self.history.set_meta("offset", int(update["update_id"]) + 1)

    def daily(self, now: datetime) -> None:
        day = now.date() - timedelta(days=1)
        if now.hour >= 9 and self.history.get_meta("daily_sent") != str(day):
            self.send_report(day, now)
            self.history.set_meta("daily_sent", str(day))
