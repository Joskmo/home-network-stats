"""Synthetic counters only; never used by the live database."""

import importlib.util
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class HistoryTests(unittest.TestCase):
    def test_interval_date_query_has_index(self):
        from history import History

        with tempfile.TemporaryDirectory() as directory:
            history = History(Path(directory) / "test.sqlite")
            indices = history.db.execute("PRAGMA index_list(intervals)").fetchall()
            self.assertTrue(any(row[1] == "intervals_end_start" for row in indices))
            history.close()

    def test_baseline_deltas_restart_resets_gaps_and_midnight(self):
        self.assertIsNotNone(
            importlib.util.find_spec("history"), "history not implemented"
        )
        from history import History

        tz = ZoneInfo("Europe/Moscow")
        t = datetime(2026, 9, 6, 12, tzinfo=tz).timestamp()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.sqlite"
            h = History(path)
            h.record(t, {"a": (1000, 100)})
            self.assertEqual(h.report(date(2026, 9, 6))["devices"], {})
            h.record(t + 300, {"a": (1100, 120)})
            h.close()
            h = History(path)
            self.assertEqual(h.report(date(2026, 9, 6))["devices"], {"a": 120})
            h.record(t + 600, {"a": (1, 1)})
            h.record(t + 900, {"a": (11, 11)})
            h.record(t + 1800, {"a": (100, 100)})
            report = h.report(date(2026, 9, 6))
            self.assertEqual(report["devices"], {"a": 140})
            self.assertEqual(report["covered_seconds"], 600)
            self.assertIn("counter reset", report["issues"])
            self.assertIn("collection gap", report["issues"])
            self.assertFalse(report["complete"])
            before = datetime(2026, 9, 6, 23, 59, tzinfo=tz).timestamp()
            h.record(before, {"a": (110, 110)})
            h.record(before + 120, {"a": (120, 120)})
            self.assertEqual(h.report(date(2026, 9, 7))["devices"], {})
            self.assertIn("midnight boundary", h.report(date(2026, 9, 7))["issues"])
            h.record(before + 420, {"a": (130, 130), "b": (99999, 99999)})
            self.assertEqual(h.report(date(2026, 9, 7))["devices"], {"a": 20})
            h.set_meta("offset", "42")
            self.assertEqual(h.get_meta("offset"), "42")
            h.close()


if __name__ == "__main__":
    unittest.main()
