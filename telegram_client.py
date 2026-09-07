"""Telegram transport with a fixed private recipient and mandatory local proxy."""

import requests

PROXY = "http://127.0.0.1:10818"


class TelegramError(RuntimeError):
    """Never include request URLs (which contain the token) in errors."""


class TelegramClient:
    def __init__(self, token, owner, session=None):
        self._base = f"https://api.telegram.org/bot{token}/"
        self.owner = owner
        self.session = session or requests.Session()
        self.session.trust_env = False

    def authorized(self, message):
        return (
            isinstance(message, dict)
            and not message.get("sender_chat")
            and message.get("chat", {}).get("type") == "private"
            and message.get("chat", {}).get("id") == self.owner
            and message.get("from", {}).get("id") == self.owner
        )

    def _call(self, method, data=None, files=None):
        try:
            response = self.session.post(
                self._base + method,
                data=data or {},
                files=files,
                proxies={"http": PROXY, "https": PROXY},
                timeout=(10, 40),
            )
            if response.status_code != 200:
                raise TelegramError(f"Telegram HTTP {response.status_code}")
            payload = response.json()
            if not payload.get("ok"):
                raise TelegramError("Telegram rejected request")
            return payload["result"]
        except TelegramError:
            raise
        except Exception:
            raise TelegramError(
                "Telegram transport failure (details suppressed for token safety)"
            ) from None

    def verify(self):
        identity = self._call("getMe")
        chat = self._call("getChat", {"chat_id": self.owner})
        if (
            not identity.get("is_bot")
            or chat.get("id") != self.owner
            or chat.get("type") != "private"
        ):
            raise TelegramError("Bot/recipient verification failed")
        return identity

    def updates(self, offset):
        return self._call(
            "getUpdates",
            {"offset": offset, "timeout": 20, "allowed_updates": '["message"]'},
        )

    def _sent(self, result):
        if (
            result.get("chat", {}).get("id") != self.owner
            or result.get("chat", {}).get("type") != "private"
        ):
            raise TelegramError("Unexpected outbound recipient")
        return result

    def send_text(self, text):
        return self._sent(
            self._call("sendMessage", {"chat_id": self.owner, "text": text})
        )

    def send_photo(self, png, caption):
        return self._sent(
            self._call(
                "sendPhoto",
                {"chat_id": self.owner, "caption": caption},
                {"photo": ("traffic.png", png, "image/png")},
            )
        )
