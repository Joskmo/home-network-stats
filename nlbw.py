"""Private nlbwmon traffic reports; never imports historical counters as usage."""

import re


def parse_nlbw(payload: object) -> dict[str, tuple[int, int]]:
    """Upstream client.c handle_json(): {columns:[...],data:[[...],...]}."""
    if not isinstance(payload, dict):
        raise ValueError("Expected nlbw JSON object")
    columns, rows = payload.get("columns"), payload.get("data")
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise ValueError("Missing columns")
    if (
        len(set(columns)) != len(columns)
        or not {"mac", "rx_bytes", "tx_bytes"} <= set(columns)
        or not isinstance(rows, list)
    ):
        raise ValueError("Invalid columns/data")
    totals = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("Invalid row length")
        record = dict(zip(columns, row))
        mac = record["mac"]
        if not isinstance(mac, str) or not re.fullmatch(
            r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac
        ):
            raise ValueError("Invalid MAC")
        rx, tx = record["rx_bytes"], record["tx_bytes"]
        if any(type(v) is not int or v < 0 for v in (rx, tx)):
            raise ValueError("Invalid byte counter")
        mac = mac.lower()
        old = totals.get(mac, (0, 0))
        totals[mac] = (old[0] + rx, old[1] + tx)
    return totals
