"""Opt-in LAN convenience identity, NOT protection from LAN IP/MAC spoofing.

The pinned Traefik must strip client forwarding headers and append its real peer;
its LAN router must apply direct-peer ipAllowList, never forwarded ipStrategy.
The inventory is host-owned and mounted read-only, never populated from HTTP.
"""
import ipaddress
import json
import os
import re
import stat
import threading
import time
from pathlib import Path

MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z')
MAX_AGE = 45


class AccessDenied(Exception):
    pass


class TrustedDevices:
    def __init__(self, path, inventory, host='home-lan.jos-dev.ru'):
        self.path, self.inventory_path = Path(path), Path(inventory)
        self.host = host
        self.lock = threading.RLock()

    def macs(self):
        try:
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                return set()
            data = json.loads(self.path.read_text())['macs']
            if not isinstance(data, list) or not all(isinstance(x,str) and MAC.fullmatch(x) for x in data):
                return set()
            return set(data)
        except (OSError, ValueError, KeyError, TypeError):
            return set()

    def devices(self):
        """Drop all ambiguous IP/MAC bindings; fail closed on malformed exports."""
        try:
            if self.inventory_path.stat().st_size > 1024*1024: return []
            data = json.loads(self.inventory_path.read_text())
            now = time.time()
            if data['source'] != 'router-native' or not 0 <= now-data['sampled_at'] <= MAX_AGE: return []
            rows = data['devices']
            if not isinstance(rows,list): return []
            ips, macs = {}, {}
            for row in rows:
                ips[row['ip']] = ips.get(row['ip'],0)+1
                macs[row['mac']] = macs.get(row['mac'],0)+1
            result = []
            for row in rows:
                ip, mac = row['ip'], row['mac']
                if ips[ip] != 1 or macs[mac] != 1: continue
                if not MAC.fullmatch(mac) or ipaddress.ip_address(ip) not in ipaddress.ip_network('192.168.1.0/24'): continue
                if row['state'] != 'REACHABLE' or row['interface'] != 'br-lan': continue
                if not 0 <= now-row['observed_at'] <= MAX_AGE: continue
                result.append({'id':mac,'mac':mac,'ip':ip,'name':str(row.get('name') or ip)[:64]})
            return sorted(result, key=lambda row:(row['name'],row['ip']))
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def can_manage(self, auth, session, env):
        return bool(auth.allowed(session) or self.identity(env))

    def _rate(self, auth, key):
        from .auth import RateLimited
        with auth.lock:
            now = time.time()
            remaining = auth.state.get(key,0)-now
            if remaining > 0: raise RateLimited(remaining)
            auth.state[key] = now+10
            auth._save()

    def update(self, auth, session, env, action, device_id):
        with self.lock:
            if not self.can_manage(auth, session, env): raise AccessDenied('Forbidden')
            if not isinstance(device_id,str) or not MAC.fullmatch(device_id): raise ValueError('Invalid device')
            macs = self.macs()
            if action == 'add':
                if device_id not in {row['id'] for row in self.devices()}: raise ValueError('Device unavailable')
                macs.add(device_id)
            elif action == 'remove':
                if device_id not in macs: raise ValueError('Unknown device')
                macs.remove(device_id)
            else: raise ValueError('Invalid action')
            self._rate(auth, 'trust_mutation_until')
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temp = self.path.with_suffix('.tmp')
            fd = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as out:
                json.dump({'macs':sorted(macs)},out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp,self.path)

    def recover(self, auth, session, env, password):
        # A password admin alone is NOT sufficient; verify live LAN binding anew.
        with self.lock, auth.lock:
            if not self.identity(env): raise AccessDenied('Trusted LAN device required')
            self._rate(auth, 'recovery_until')
            if not isinstance(password,str) or not 12 <= len(password) <= 256 or auth.verify(password):
                raise ValueError('Choose a different password of 12–256 characters')
            auth.state = auth.state | auth._hash(password) | {'must_change':False,'failures':0,'blocked_until':0}
            auth._save()
            auth.sessions.clear()
            # Recovery does not create a reusable password-authenticated session.
            token, _ = auth.session()
            return token

    def identity(self, env):
        # Exact deployment peer, not an operator-supplied CIDR of "trusted proxies".
        if env.get('REMOTE_ADDR') != '172.22.0.2': return None
        if env.get('HTTP_HOST','').lower() != self.host or env.get('HTTP_X_FORWARDED_PROTO') != 'https': return None
        try:
            client = env.get('HTTP_X_FORWARDED_FOR','').split(',')[-1].strip()
            if ipaddress.ip_address(client) not in ipaddress.ip_network('192.168.1.0/24'): return None
        except ValueError: return None
        trusted = self.macs()
        return next((row for row in self.devices() if row['ip'] == client and row['mac'] in trusted), None)
