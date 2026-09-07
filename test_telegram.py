import importlib.util
import tempfile
import unittest
from pathlib import Path


class TelegramTests(unittest.TestCase):
    def test_strict_private_authorization_fixed_destination_and_proxy(self):
        self.assertIsNotNone(
            importlib.util.find_spec("telegram_client"), "client missing"
        )
        from telegram_client import TelegramClient

        class Session:
            def post(self, url, **kw):
                self.last = (url, kw)

                class Response:
                    status_code = 200

                    def json(self):
                        return {
                            "ok": True,
                            "result": {
                                "message_id": 7,
                                "chat": {"id": 123, "type": "private"},
                            },
                        }

                return Response()

        session = Session()
        bot = TelegramClient("123:synthetic-not-a-secret", 123, session=session)
        good = {
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123},
            "text": "/today",
        }
        self.assertTrue(bot.authorized(good))
        for change in [
            {"chat": {"id": 123, "type": "group"}},
            {"chat": {"id": 999, "type": "private"}},
            {"from": {"id": 999}},
            {"from": {}},
            {"sender_chat": {"id": 123}},
        ]:
            self.assertFalse(bot.authorized(good | change))
        self.assertFalse(bot.authorized({}))
        self.assertEqual(bot.send_text("hello")["message_id"], 7)
        self.assertFalse(session.trust_env)
        self.assertEqual(
            session.last[1]["proxies"],
            {"http": "http://127.0.0.1:10818", "https": "http://127.0.0.1:10818"},
        )
        self.assertEqual(session.last[1]["data"]["chat_id"], 123)
        bot.send_photo(b"png", "caption")
        self.assertEqual(session.last[1]["data"]["chat_id"], 123)
        self.assertIn("files", session.last[1])

    def test_protected_token_file_and_required_config(self):
        self.assertIsNotNone(importlib.util.find_spec("config"), "config missing")
        from config import load_config

        with tempfile.TemporaryDirectory() as d:
            token = Path(d) / "token"
            token.write_text("123:synthetic-not-a-secret")
            token.chmod(0o600)
            env = {
                "TRAFFIC_TOKEN_FILE": str(token),
                "TRAFFIC_ALLOWED_USER_ID": "123",
                "TRAFFIC_ROUTER": "root@192.0.2.1",
                "TRAFFIC_SSH_KEY": str(Path(d) / "key"),
                "TRAFFIC_DATA_DIR": str(Path(d) / "data"),
            }
            cfg = load_config(env)
            self.assertEqual(cfg.allowed_user_id, 123)
            self.assertNotIn("synthetic", repr(cfg))
            token.chmod(0o644)
            with self.assertRaises(ValueError):
                load_config(env)
            with self.assertRaises(ValueError):
                load_config({})


if __name__ == "__main__":
    unittest.main()
