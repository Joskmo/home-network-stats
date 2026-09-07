"""Service entry point. No web server, router mutation, or proxy management."""

import argparse
import fcntl
import logging
import os
import time
from datetime import datetime

from app import Application
from collector import collect
from config import load_config
from devices import collect_inventory
from history import MSK, History
from telegram_client import TelegramClient

LOG = logging.getLogger(__name__)


def run_iteration(
    application,
    next_collection,
    monotonic=time.monotonic,
    now=lambda: datetime.now(MSK),
):
    tick = monotonic()
    if tick >= next_collection:
        application.collect_once()
        next_collection = monotonic() + 300
    try:
        updates = application.telegram.updates(
            int(application.history.get_meta("offset", "0"))
        )
    except Exception as error:
        LOG.warning("Telegram polling failed: %s", type(error).__name__)
        updates = []
        time.sleep(5)
    for update in updates:
        try:
            application.handle_update(update, now())
        except Exception as error:
            LOG.warning("Command failed: %s", type(error).__name__)
            message = update.get("message", {})
            if application.telegram.authorized(message):
                try:
                    application.telegram.send_text(application.text("error"))
                except Exception:
                    pass
            application.history.set_meta("offset", int(update["update_id"]) + 1)
    try:
        application.daily(now())
    except Exception as error:
        LOG.warning("Daily report failed; will retry: %s", type(error).__name__)
        time.sleep(5)
    return next_collection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["run", "verify", "collect-once", "send-today"]
    )
    args = parser.parse_args()
    os.umask(0o077)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Avoid a second long-poller or concurrent counter writer.
    with (config.data_dir / "bot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        history = History(config.data_dir / "traffic.sqlite3")
        telegram = TelegramClient(config.token, config.allowed_user_id)
        application = Application(
            history,
            telegram,
            lambda: collect(config),
            inventory=lambda: collect_inventory(config),
        )
        try:
            if args.action == "verify":
                identity = telegram.verify()
                counters = collect(config)
                print(
                    f"Verified bot @{identity.get('username', '(unnamed)')}; private recipient verified; {len(counters)} router devices; explicit local proxy."
                )
            elif args.action == "collect-once":
                if not application.collect_once():
                    return 1
            elif args.action == "send-today":
                telegram.verify()
                result = application.send_report(
                    datetime.now(MSK).date(), datetime.now(MSK)
                )
                print(f"Telegram accepted photo message_id={result['message_id']}")
            else:
                telegram.verify()
                next_collection = 0
                while True:
                    try:
                        next_collection = run_iteration(application, next_collection)
                    except Exception as error:
                        # Never print exception URLs or private request payloads.
                        LOG.warning("Loop failure: %s", type(error).__name__)
                        time.sleep(10)
        finally:
            history.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as error:
        logging.error(
            "Startup/action failed: %s (check protected configuration and connectivity)",
            type(error).__name__,
        )
        raise SystemExit(1) from None
