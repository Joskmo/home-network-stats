"""Read native nlbwmon's in-memory database; no router-side Python or commits."""

import json
import subprocess

from config import Config
from nlbw import parse_nlbw


def collect(config: Config, run=subprocess.run) -> dict[str, tuple[int, int]]:
    result = run(
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
            "nlbw -c json -g mac",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return parse_nlbw(json.loads(result.stdout))
