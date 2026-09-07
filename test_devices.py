"""Synthetic identity fixtures: never captured home network inventory."""

import unittest

from devices import display_names, parse_inventory


class DeviceTests(unittest.TestCase):
    def test_application_persists_names_and_passes_them_to_chart(self):
        import json
        import tempfile
        from datetime import datetime
        from pathlib import Path
        from unittest.mock import Mock, patch

        from app import Application
        from history import MSK, History

        with tempfile.TemporaryDirectory() as directory:
            history = History(Path(directory) / "traffic.sqlite3")
            telegram = Mock()
            telegram.send_photo.return_value = {"message_id": 1}
            app = Application(
                history,
                telegram,
                lambda: {"aa:00:00:00:00:01": (1, 2)},
                inventory=lambda: {"aa:00:00:00:00:01": "workstation"},
            )
            now = datetime(2026, 9, 7, 12, tzinfo=MSK)
            self.assertTrue(app.collect_once(now))
            self.assertEqual(
                json.loads(history.get_meta("device_names"))["aa:00:00:00:00:01"],
                "workstation",
            )
            with patch("app.render_report", return_value=(b"png", "caption")) as render:
                app.send_report(now.date(), now)
                self.assertEqual(
                    render.call_args.args[0]["device_names"]["aa:00:00:00:00:01"],
                    "workstation",
                )
            history.close()

    def test_static_name_beats_lease_and_unknown_falls_back_to_ip(self):
        inventory = parse_inventory(
            {
                "hosts": [
                    {
                        "name": "workstation",
                        "mac": "AA:00:00:00:00:01 aa:00:00:00:00:02",
                        "ip": "192.0.2.10",
                    }
                ],
                "leases": [
                    {
                        "name": "old-name",
                        "mac": "aa:00:00:00:00:01",
                        "ip": "192.0.2.11",
                    },
                    {"name": "phone", "mac": "aa:00:00:00:00:03", "ip": "192.0.2.12"},
                    {"name": "*", "mac": "aa:00:00:00:00:04", "ip": "192.0.2.13"},
                ],
            }
        )
        names = display_names(
            [
                "aa:00:00:00:00:01",
                "aa:00:00:00:00:02",
                "aa:00:00:00:00:03",
                "aa:00:00:00:00:04",
                "aa:00:00:00:00:05",
            ],
            inventory,
        )
        self.assertEqual(names["aa:00:00:00:00:01"], "workstation")
        self.assertEqual(names["aa:00:00:00:00:02"], "workstation")
        self.assertEqual(names["aa:00:00:00:00:03"], "phone")
        self.assertEqual(names["aa:00:00:00:00:04"], "192.0.2.13")
        self.assertIn("00:00:05", names["aa:00:00:00:00:05"])
