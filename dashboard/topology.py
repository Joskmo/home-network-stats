"""Manual physical topology. No inferred cables; only explicit LAN literals."""
import fcntl
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

LAN = ipaddress.ip_network('192.168.1.0/24')
MAX_BYTES = 131072


class Conflict(ValueError):
    """Another editor saved first; caller must reload, not overwrite."""


def text(value, maximum=80, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid text')
    return value.strip()


def lan_ip(value):
    value = text(value, 15, empty=True)
    if value:
        address = ipaddress.IPv4Address(value)
        if address not in LAN or address in (LAN.network_address, LAN.broadcast_address):
            raise ValueError('IP must be a LAN unicast literal')
    return value


def validate(value):
    if not isinstance(value, dict) or not {'revision', 'nodes', 'links'} <= set(value) <= {'revision', 'nodes', 'links', 'routes'}:
        raise ValueError('Invalid topology')
    revision = value['revision']
    if type(revision) is not int or not 0 <= revision < 2**53: raise ValueError('Invalid revision')
    nodes, links = value['nodes'], value['links']
    if not isinstance(nodes, list) or len(nodes) > 64 or not isinstance(links, list) or len(links) > 128:
        raise ValueError('Topology too large')
    result = {'revision': revision, 'nodes': [], 'links': []}
    ids = set()
    def identifier(value):
        value = text(value, 64)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value): raise ValueError('Invalid ID')
        return value
    for node in nodes:
        required = {'id', 'name', 'type', 'ip', 'mac', 'x', 'y'}
        if not isinstance(node, dict) or not required <= set(node) <= required | {'discovery', 'ports'}:
            raise ValueError('Invalid node')
        n: dict = {k: text(node[k], 80, empty=k=='mac') for k in ('name', 'type', 'mac')}
        n['id'] = identifier(node['id'])
        if n['id'] in ids or n['type'] not in {'router', 'switch', 'ap', 'server', 'device', 'other', 'phone', 'laptop', 'desktop', 'tablet', 'tv', 'printer', 'iot'}: raise ValueError('Invalid node')
        if 'ports' in node:
            if not isinstance(node['ports'], list) or len(node['ports']) > 48:
                raise ValueError('Invalid ports')
            n['ports'] = [text(port, 32) for port in node['ports']]
            if len(set(n['ports'])) != len(n['ports']):
                raise ValueError('Duplicate port')
        if n['mac'] and not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', n['mac']): raise ValueError('Invalid MAC')
        n['ip'] = lan_ip(node['ip'])
        if 'discovery' in node:
            d = node['discovery']
            if not isinstance(d, dict) or set(d) != {'name','source','last_seen','attachment','confidence'}: raise ValueError('Invalid discovery')
            n['discovery'] = {k:text(d[k], 120, empty=True) for k in ('name','source','attachment','confidence')}
            seen = d['last_seen']
            if type(seen) not in (int,float) or not math.isfinite(seen) or seen < 0: raise ValueError('Invalid observation time')
            n['discovery']['last_seen'] = seen
        for k, bound in (('x', 32768), ('y', 32768)):
            if type(node[k]) not in (int, float) or not math.isfinite(node[k]) or not 0 <= node[k] <= bound: raise ValueError('Invalid coordinate')
            n[k] = node[k]
        if n['mac'] and any(old['mac'].lower()==n['mac'].lower() for old in result['nodes']): raise ValueError('Duplicate MAC')
        ids.add(n['id']); result['nodes'].append(n)
    link_ids = set()
    for link in links:
        required = {'id', 'source', 'target', 'source_port', 'target_port'}
        if not isinstance(link, dict) or not required <= set(link) <= required | {'medium'}:
            raise ValueError('Invalid link')
        item = {k: identifier(link[k]) for k in ('id', 'source', 'target')}
        if item['id'] in link_ids or item['source'] not in ids or item['target'] not in ids or item['source'] == item['target']: raise ValueError('Invalid endpoints')
        item.update({k: text(link[k], 32) for k in ('source_port', 'target_port')})
        if 'medium' in link:
            item['medium'] = text(link['medium'], 16)
            if item['medium'] not in {'ethernet', 'wifi'}:
                raise ValueError('Invalid connection medium')
        link_ids.add(item['id']); result['links'].append(item)
    if 'routes' in value:
        routes = value['routes']
        if not isinstance(routes, dict) or len(routes) > 128:
            raise ValueError('Invalid routes')
        result['routes'] = {}
        for key, points in routes.items():
            if not isinstance(key, str): raise ValueError('Invalid route key')
            try:
                parts = json.loads(key)
            except (ValueError, RecursionError) as exc:
                raise ValueError('Invalid route key') from exc
            if not isinstance(parts, list) or not parts or not all(isinstance(p, str) for p in parts):
                raise ValueError('Invalid route key')
            if parts[0] in ('manual', 'wan') and len(parts) == 2:
                route_ids = parts[1:]
            elif parts[0] == 'observed' and len(parts) == 5:
                route_ids = parts[1:3]
                for port in parts[3:]: text(port, 32, empty=True)
            else:
                raise ValueError('Invalid route key')
            for route_id in route_ids:
                if identifier(route_id) != route_id: raise ValueError('Invalid route ID')
            if not isinstance(points, list) or len(points) > 8:
                raise ValueError('Invalid route points')
            for point in points:
                if not isinstance(point, dict) or set(point) != {'x', 'y'}:
                    raise ValueError('Invalid route point')
                for coordinate in point.values():
                    if type(coordinate) not in (int, float) or not 0 <= coordinate <= 32768 or not math.isfinite(coordinate):
                        raise ValueError('Invalid route coordinate')
            # Display metadata only: stale IDs are safe; never infer links or evidence.
            # Preserve exact keys (including port strings), without normalization.
            result['routes'][key] = [dict(point) for point in points]
    return result


def atomic_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


class TopologyStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'topology.json'
        self.lock = threading.RLock()

    def read(self):
        try:
            if self.path.stat().st_size > MAX_BYTES: raise ValueError('Topology too large')
            return validate(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return {'revision': 0, 'nodes': [], 'links': []}

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        graph = self.read()
        try:
            path = self.directory / 'status.json'
            if path.stat().st_size > MAX_BYTES: raise ValueError('Status too large')
            samples = json.loads(path.read_text())
            if not isinstance(samples, dict): samples = {}
        except (OSError, ValueError): samples = {}
        status = {}
        for node in graph['nodes']:
            item = samples.get(node['id'], {})
            checked = item.get('checked_at') if isinstance(item, dict) else None
            valid = isinstance(item, dict) and node['ip'] and item.get('ip') == node['ip'] and type(checked) in (int, float) and math.isfinite(checked)
            fresh = valid and 0 <= now - checked <= 90
            state = item.get('state') if fresh else 'unknown'
            if state not in {'online', 'no_reply', 'unknown'}: state = 'unknown'
            status[node['id']] = {'state': state, 'checked_at': checked if valid else None}
        return graph | {'monitor': status}

    def save(self, value):
        value = validate(value)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.lock, open(self.directory / '.lock', 'a') as lock:
            os.chmod(self.directory / '.lock', 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.read()['revision'] != value['revision']: raise Conflict('Reload before saving')
            value['revision'] += 1
            atomic_json(self.path, value)
        return value


def ping(ip):
    ip = lan_ip(ip)
    if not ip: return 'unknown'
    try:
        result = subprocess.run(['/usr/bin/ping', '-n', '-c', '1', '-W', '1', ip], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
        return {0: 'online', 1: 'no_reply'}.get(result.returncode, 'unknown')
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'


def sample(store, probe=ping, now=None):
    graph = store.read()  # Revalidate the on-disk input before running any command.
    ips = sorted({n['ip'] for n in graph['nodes'] if n['ip']})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(zip(ips, pool.map(probe, ips)))
    checked = time.time() if now is None else now
    samples = {n['id']: {'ip': n['ip'], 'state': results[n['ip']], 'checked_at': checked}
               for n in graph['nodes'] if n['ip']}
    store.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_json(store.directory / 'status.json', samples)
    return samples


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Host-side LAN topology ICMP monitor')
    parser.add_argument('--directory', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    store = TopologyStore(args.directory)
    while True:
        start = time.monotonic()
        try: sample(store)
        except (OSError, ValueError):
            # Previous results expire after 90 seconds; never forge a no-reply result.
            print('Topology sample unavailable', flush=True)
            if args.once: raise
        if args.once: break
        time.sleep(max(1, 30 - (time.monotonic() - start)))


if __name__ == '__main__': main()
