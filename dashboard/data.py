"""Read-only adapter for the bot's interval schema. No invented history."""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def monthly(path, now=None):
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, MSK)
    start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    result = {
        "available": False,
        "month": today.strftime("%Y-%m"),
        "timezone": "Europe/Moscow",
        "devices": [],
        "total_bytes": 0,
        "covered_seconds": 0,
        "expected_seconds": now - start,
        "collection_started": None,
        "last_sample": None,
        "partial": True,
        "issues": [],
    }
    path = Path(path)
    if not path.is_file():
        return result
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            result["collection_started"], result["last_sample"] = db.execute(
                "SELECT MIN(start),MAX(end) FROM intervals"
            ).fetchone()
            devices, issues = {}, set()
            for a, b, usage, covered, flags in db.execute(
                "SELECT start,end,usage,covered,issues FROM intervals WHERE end>=? AND start<=?",
                (start, now),
            ):
                issues.update(json.loads(flags))
                if a >= start and b <= now:
                    result["covered_seconds"] += covered
                    for device, value in json.loads(usage).items():
                        devices[device] = devices.get(device, 0) + max(0, int(value))
            names = {}
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
            ).fetchone():
                row = db.execute(
                    "SELECT value FROM meta WHERE key='device_names'"
                ).fetchone()
                if row:
                    names = json.loads(row[0])
            result.update(
                available=True,
                devices=[
                    {"mac": k, "name": names.get(k, ""), "bytes": v}
                    for k, v in sorted(
                        devices.items(), key=lambda x: x[1], reverse=True
                    )
                ],
                total_bytes=sum(devices.values()),
                issues=sorted(issues),
            )
            result["partial"] = bool(
                issues or result["covered_seconds"] < result["expected_seconds"]
            )
        finally:
            db.close()
    except (sqlite3.Error, ValueError, TypeError):
        result["available"] = False
    return result


def speed(path):
    result = {
        "download_bps": None,
        "upload_bps": None,
        "sampled_at": None,
        "stale": True,
    }
    try:
        data = json.loads(Path(path).read_text())
        stamp = float(data["sampled_at"])
        result["sampled_at"] = stamp
        if 0 <= time.time() - stamp <= 20 and data.get("download_bps") is not None:
            result.update(
                download_bps=max(0, float(data["download_bps"])),
                upload_bps=max(0, float(data["upload_bps"])),
                stale=False,
            )
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return result


def snapshot(history_path, speed_path):
    return {
        "monthly": monthly(history_path),
        "wan_monthly": monthly(Path(speed_path).with_name("wan.sqlite3")),
        "speed": speed(speed_path),
        "generated_at": time.time(),
    }
