"""Explicit, secret-safe configuration; no owner or router inventory in source."""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    allowed_user_id: int
    router: str
    ssh_key: Path
    data_dir: Path


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    required = [
        "TRAFFIC_TOKEN_FILE",
        "TRAFFIC_ALLOWED_USER_ID",
        "TRAFFIC_ROUTER",
        "TRAFFIC_SSH_KEY",
        "TRAFFIC_DATA_DIR",
    ]
    if any(not env.get(name) for name in required):
        raise ValueError("Missing required TRAFFIC_* configuration; see README")
    path = Path(env["TRAFFIC_TOKEN_FILE"]).expanduser()
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_mode & 0o077
        or info.st_uid != os.getuid()
    ):
        raise ValueError("Token file must be owner-only and owned by the service user")
    token = path.read_text().strip()
    if not token or ":" not in token or any(c.isspace() for c in token):
        raise ValueError("Invalid token file")
    owner = int(env["TRAFFIC_ALLOWED_USER_ID"])
    if owner <= 0:
        raise ValueError("Owner must be a positive private Telegram user ID")
    router = env["TRAFFIC_ROUTER"]
    if router.startswith("-") or any(c.isspace() for c in router):
        raise ValueError("Invalid SSH target")
    return Config(
        token,
        owner,
        router,
        Path(env["TRAFFIC_SSH_KEY"]).expanduser(),
        Path(env["TRAFFIC_DATA_DIR"]).expanduser(),
    )
