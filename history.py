"""Conservative cumulative-counter deltas, persisted atomically in SQLite.

No backfill: first samples and new devices establish baselines. Intervals crossing
midnight or >7.5 minutes are discarded instead of inventing temporal allocation.
"""

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict
from zoneinfo import ZoneInfo


class TrafficReport(TypedDict):
    day: str
    devices: dict[str, int]
    device_names: NotRequired[dict[str, str]]
    covered_seconds: float
    expected_seconds: float
    complete: bool
    issues: list[str]


MSK = ZoneInfo("Europe/Moscow")
MAX_INTERVAL = 450


def day_bounds(day: date) -> tuple[float, float]:
    return (
        datetime.combine(day, time(), MSK).timestamp(),
        datetime.combine(day + timedelta(days=1), time(), MSK).timestamp(),
    )


class History:
    def __init__(self, path: str | Path, readonly: bool = False) -> None:
        if readonly:
            from pathlib import Path

            self.db = sqlite3.connect(
                Path(path).resolve().as_uri() + "?mode=ro", uri=True
            )
            return
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intervals(
                start REAL NOT NULL,end REAL NOT NULL,usage TEXT NOT NULL,
                covered REAL NOT NULL,issues TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS intervals_end_start ON intervals(end, start);
        """)

    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES(?,?)", (key, str(value))
            )

    def record(self, stamp: float, counters: dict[str, tuple[int, int]]) -> None:
        previous = json.loads(self.get_meta("snapshot", "null"))
        usage, issues, covered = {}, [], 0
        if previous:
            start, old = previous
            if stamp <= start:
                raise ValueError("Sample time must increase")
            if (
                datetime.fromtimestamp(start, MSK).date()
                != datetime.fromtimestamp(stamp, MSK).date()
            ):
                issues.append("midnight boundary")
            if stamp - start > MAX_INTERVAL:
                issues.append("collection gap")
            if not issues:
                for device, current in counters.items():
                    before = old.get(device)
                    if before is None:
                        issues.append("new device baseline")
                    elif any(a < b for a, b in zip(current, before)):
                        issues.append("counter reset")
                    else:
                        delta = sum(current) - sum(before)
                        if delta:
                            usage[device] = delta
                if set(old) - set(counters):
                    issues.append("device disappeared")
                if not issues:
                    covered = stamp - start
        else:
            start = stamp
            issues.append("initial baseline")
        with self.db:
            self.db.execute(
                "INSERT INTO intervals VALUES(?,?,?,?,?)",
                (start, stamp, json.dumps(usage), covered, json.dumps(issues)),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES(?,?)",
                ("snapshot", json.dumps([stamp, counters])),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES(?,?)", ("last_success", str(stamp))
            )
            self.db.execute("DELETE FROM meta WHERE key=?", ("last_error",))

    def report(self, day: date, now: float | None = None) -> TrafficReport:
        start, end = day_bounds(day)
        devices, issues, covered = {}, set(), 0
        for a, b, usage, seconds, flags in self.db.execute(
            "SELECT * FROM intervals WHERE end>=? AND start<?", (start, end)
        ):
            issues.update(json.loads(flags))
            if a >= start and b <= end:
                covered += seconds
                for device, value in json.loads(usage).items():
                    devices[device] = devices.get(device, 0) + value
        expected = max(0, min(end, now if now is not None else end) - start)
        return {
            "day": str(day),
            "devices": devices,
            "covered_seconds": covered,
            "expected_seconds": expected,
            "complete": expected > 0 and covered >= expected and not issues,
            "issues": sorted(issues),
        }

    def close(self):
        self.db.close()


def read_report(path: str | Path, day: date, now: float | None = None) -> TrafficReport:
    """Dashboard integration: read-only connection; no writes or implicit DB creation.

    `day` is datetime.date in Europe/Moscow; `now` is optional Unix seconds.
    Returned device keys and byte deltas are private data: authenticate before serving.
    """
    history = History(path, readonly=True)
    try:
        return history.report(day, now)
    finally:
        history.close()
