import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from history import MSK, History


class AppTests(unittest.TestCase):
    def test_daily_failure_retry_restart_and_language_roundtrip(self):
        from unittest.mock import Mock

        from app import Application
        from telegram_client import TelegramClient

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            history = History(path)
            telegram = Mock()
            telegram.authorized = TelegramClient("123:synthetic", 123).authorized
            telegram.send_photo.side_effect = RuntimeError("offline")
            app = Application(history, telegram, dict)
            before = datetime(2026, 9, 7, 8, 59, tzinfo=MSK)
            due = datetime(2026, 9, 7, 9, tzinfo=MSK)
            app.daily(before)
            telegram.send_photo.assert_not_called()
            with self.assertRaises(RuntimeError):
                app.daily(due)
            self.assertIsNone(history.get_meta("daily_sent"))
            telegram.send_photo.side_effect = None
            telegram.send_photo.return_value = {"message_id": 42}
            app.daily(due)
            self.assertEqual(history.get_meta("daily_sent"), "2026-09-06")
            self.assertEqual(history.get_meta("last_report_message_id"), "42")
            message = {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}}
            for language in ("en", "ru"):
                app.handle_update(
                    {
                        "update_id": 1,
                        "message": message | {"text": "/language " + language},
                    },
                    due,
                )
                history.close()
                history = History(path)
                app = Application(history, telegram, dict)
                self.assertEqual(app.language, language)
            count = telegram.send_photo.call_count
            app.daily(due)
            self.assertEqual(telegram.send_photo.call_count, count)
            history.close()

    def test_collection_ssh_is_readonly_strict_and_parser_is_real(self):
        self.assertIsNotNone(importlib.util.find_spec("collector"), "collector missing")
        from collector import collect

        calls = []

        def run(args, **kw):
            calls.append((args, kw))
            return SimpleNamespace(
                stdout='{"columns":["mac","rx_bytes","tx_bytes"],"data":[["aa:bb:cc:dd:ee:01",1,2]]}'
            )

        cfg = SimpleNamespace(
            router="root@192.0.2.1", ssh_key=Path("/tmp/synthetic-key")
        )
        self.assertEqual(collect(cfg, run=run), {"aa:bb:cc:dd:ee:01": (1, 2)})
        args, kw = calls[0]
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("IdentitiesOnly=yes", args)
        self.assertIn("/tmp/synthetic-key", args)
        self.assertEqual(args[-1], "nlbw -c json -g mac")
        self.assertTrue(kw["check"])
        self.assertEqual(kw["timeout"], 30)

    def test_commands_locale_persistence_daily_once_and_unauthorized_silence(self):
        self.assertIsNotNone(importlib.util.find_spec("app"), "app missing")
        from app import Application
        from telegram_client import TelegramClient

        class FakeTelegram:
            owner = 123
            authorized = TelegramClient.authorized

            def __init__(self):
                self.texts = []
                self.photos = []

            def send_text(self, text):
                self.texts.append(text)
                return {"message_id": 1}

            def send_photo(self, png, caption):
                self.photos.append(caption)
                return {"message_id": 2}

        now = datetime(2026, 9, 7, 9, 1, tzinfo=MSK)
        with tempfile.TemporaryDirectory() as d:
            h = History(Path(d) / "test.sqlite")
            tg = FakeTelegram()
            app = Application(h, tg, lambda: {"a": (10, 10)})
            msg = {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}}
            app.handle_update(
                {"update_id": 1, "message": msg | {"text": "/start"}}, now
            )
            self.assertIn("/language", tg.texts[-1])
            app.handle_update(
                {"update_id": 2, "message": msg | {"text": "/language en"}}, now
            )
            self.assertEqual(h.get_meta("language"), "en")
            app = Application(h, tg, lambda: {"a": (10, 10)})
            app.handle_update(
                {"update_id": 3, "message": msg | {"text": "/status"}}, now
            )
            self.assertIn("Last successful", tg.texts[-1])
            app.handle_update(
                {"update_id": 4, "message": msg | {"text": "/today"}}, now
            )
            self.assertIn("Incomplete", tg.photos[-1])
            app.handle_update(
                {"update_id": 5, "message": msg | {"text": "/yesterday"}}, now
            )
            self.assertIn("2026-09-06", tg.photos[-1])
            count = len(tg.texts)
            app.handle_update(
                {
                    "update_id": 6,
                    "message": msg | {"text": "/language ru", "from": {"id": 999}},
                },
                now,
            )
            self.assertEqual(len(tg.texts), count)
            self.assertEqual(h.get_meta("offset"), "7")
            app.handle_update(
                {"update_id": 7, "message": msg | {"text": "/language zz"}}, now
            )
            self.assertEqual(h.get_meta("language"), "en")
            app.collect_once(now)
            self.assertIsNotNone(h.get_meta("last_success"))
            before = len(tg.photos)
            app.daily(now)
            app.daily(now)
            self.assertEqual(len(tg.photos), before + 1)
            self.assertIn("Incomplete", tg.photos[-1])
            self.assertEqual(h.get_meta("daily_sent"), "2026-09-06")
            h.close()


if __name__ == "__main__":
    unittest.main()
