"""Authoritative DHCP display names; accounting continues to use stable MAC keys."""

import json
import re
import subprocess

from config import Config

MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z")


def parse_inventory(payload: dict) -> dict[str, str]:
    """Prefer configured static names, then lease names, then observed IP addresses."""
    result: dict[str, str] = {}
    for collection in ("leases", "hosts"):
        for host in payload.get(collection, []):
            name = str(host.get("name", "")).strip()
            address = str(host.get("ip", "")).strip()
            label = name if name and name != "*" else address
            if not label:
                continue
            label = " ".join(label.split())[:64]
            macs = host.get("mac", "")
            if isinstance(macs, str):
                macs = macs.split()
            for mac in macs:
                mac = str(mac).lower()
                if MAC.fullmatch(mac):
                    # A nameless static reservation must not replace a lease hostname.
                    if collection == "hosts" and (not name or name == "*"):
                        result.setdefault(mac, label)
                    else:
                        result[mac] = label
    return result


def display_names(devices, inventory: dict[str, str]) -> dict[str, str]:
    return {mac: inventory.get(mac.lower(), f"…{mac[-8:]}") for mac in devices}


def collect_inventory(config: Config, run=subprocess.run) -> dict[str, str]:
    response = run(
        [
            "ssh",
            "-i",
            str(config.ssh_key),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            config.router,
            "/usr/libexec/home-network-read inventory",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return parse_inventory(json.loads(response.stdout))
