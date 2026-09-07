import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from history import MSK, History


class RuntimeTests(unittest.TestCase):
    def test_cycle_collects_handles_updates_and_schedules(self):
        self.assertIsNotNone(importlib.util.find_spec("main"), "runtime missing")
        from main import run_iteration

        calls = []

        class FakeHistory:
            def get_meta(self, key, default=None):
                return default

            def set_meta(self, *args):
                calls.append(("meta", args))

        class FakeTelegram:
            def updates(self, offset):
                calls.append(("updates", offset))
                return [{"update_id": 4}]

        class FakeApp:
            history = FakeHistory()
            telegram = FakeTelegram()

            def collect_once(self):
                calls.append("collect")

            def handle_update(self, update, now):
                calls.append("handle")

            def daily(self, now):
                calls.append("daily")

        next_due = run_iteration(
            FakeApp(),
            0,
            monotonic=lambda: 100,
            now=lambda: datetime(2026, 9, 7, 8, tzinfo=MSK),
        )
        self.assertEqual(next_due, 400)
        self.assertEqual(calls, ["collect", ("updates", 0), "handle", "daily"])
        calls.clear()
        self.assertEqual(run_iteration(FakeApp(), 400, monotonic=lambda: 101), 400)
        self.assertNotIn("collect", calls)

    def test_telegram_failure_does_not_reset_collection_schedule(self):
        from unittest.mock import Mock

        from main import run_iteration

        app = Mock()
        app.history.get_meta.return_value = "0"
        app.telegram.updates.side_effect = RuntimeError("network unavailable")
        with self.assertLogs("main", level="WARNING"):
            due = run_iteration(app, 0, monotonic=lambda: 100)
        self.assertEqual(due, 400)
        app.collect_once.assert_called_once()
        app.daily.assert_called_once()

    def test_readonly_api_does_not_create_missing_database(self):
        import history

        self.assertTrue(hasattr(history, "read_report"), "read-only API missing")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "existing.sqlite"
            h = History(path)
            now = datetime(2026, 9, 7, 8, tzinfo=MSK)
            h.record(now.timestamp(), {"a": (1, 2)})
            h.close()
            self.assertEqual(history.read_report(path, now.date())["devices"], {})
            missing = Path(d) / "missing.sqlite"
            with self.assertRaises(Exception):
                history.read_report(missing, now.date())
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
