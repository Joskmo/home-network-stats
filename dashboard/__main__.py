"""Run with python -m dashboard. Loopback and private setup are the defaults."""
import os
import stat
from pathlib import Path
from .auth import Auth
from .access import TrustedDevices
from .data import snapshot
from .web import Application
from .topology import TopologyStore, MAX_BYTES


def build_app(env=None):
    env = os.environ if env is None else env
    state_path = Path(env['DASHBOARD_AUTH_FILE'])
    bootstrap = None
    if not state_path.exists():
        secret = Path(env['DASHBOARD_BOOTSTRAP_FILE'])
        info = secret.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('Bootstrap file must be owner-only and owned by the service user')
        bootstrap = secret.read_text().strip()
    auth = Auth(state_path,bootstrap)
    return Application(auth,lambda:snapshot(env['DASHBOARD_HISTORY_FILE'],env['DASHBOARD_SPEED_FILE']),
        access=TrustedDevices(state_path.parent/'trusted.json',env['DASHBOARD_INVENTORY_FILE'],
            host=env.get('DASHBOARD_PUBLIC_HOST','home-lan.jos-dev.ru')) if env.get('DASHBOARD_INVENTORY_FILE') else None,
        topology=TopologyStore(env.get('DASHBOARD_TOPOLOGY_DIR', str(state_path.parent.parent / 'topology'))),
        public_enabled=env.get('DASHBOARD_PUBLIC_ENABLED','false')=='true',
        public_host=env.get('DASHBOARD_PUBLIC_HOST','home-lan.jos-dev.ru'),
        trusted_lan_proxy=env.get('DASHBOARD_TRUSTED_LAN_PROXY',''),
        lan_network=env.get('DASHBOARD_LAN_NETWORK','192.168.1.0/24'))


def main():
    from waitress import serve
    app = build_app()
    serve(app,host=os.environ.get('DASHBOARD_BIND','127.0.0.1'),port=int(os.environ.get('DASHBOARD_PORT','18080')),
        threads=4,channel_timeout=30,connection_limit=50,max_request_body_size=MAX_BYTES,max_request_header_size=16384,
        clear_untrusted_proxy_headers=False,ident='Private Network')


if __name__ == '__main__': main()
