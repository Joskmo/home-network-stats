"""Dashboard labels use persisted authoritative inventory, not invented names."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from dashboard.data import monthly


class DashboardNamesTests(unittest.TestCase):
    def test_names_are_read_without_merging_distinct_macs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript(
                    "CREATE TABLE intervals(start REAL,end REAL,usage TEXT,covered REAL,issues TEXT); CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);"
                )
                db.execute(
                    "INSERT INTO intervals VALUES(?,?,?,?,?)",
                    (
                        100,
                        200,
                        json.dumps({"aa:00:00:00:00:01": 10, "aa:00:00:00:00:02": 20}),
                        100,
                        "[]",
                    ),
                )
                db.execute(
                    "INSERT INTO meta VALUES(?,?)",
                    (
                        "device_names",
                        json.dumps(
                            {
                                "aa:00:00:00:00:01": "Laptop",
                                "aa:00:00:00:00:02": "Laptop",
                            }
                        ),
                    ),
                )
            result = monthly(path, now=300)
            self.assertTrue(result["available"])
            self.assertEqual(
                [x["name"] for x in result["devices"]], ["Laptop", "Laptop"]
            )
            self.assertEqual(len({x["mac"] for x in result["devices"]}), 2)
            self.assertEqual(result["total_bytes"], 30)
