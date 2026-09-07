"""Host-only read-only router identity exporter; no scans or router Python.

Run once via systemd timer: python -m dashboard.inventory --router root@... \
    --key /private/collector-key --output /private/inventory/devices.json
Only kernel REACHABLE neighbors corroborated by DHCP are accepted.
"""
import argparse
import ipaddress
import json
import os
import subprocess
import time
from pathlib import Path
from .access import MAC
from devices import parse_inventory


def build_inventory(inventory, neighbors, sampled_at):
    names = parse_inventory(inventory)
    configured = {}
    for section in ('hosts','leases'):
        for row in inventory.get(section,[]):
            macs = row.get('mac','')
            if isinstance(macs,str): macs = macs.split()
            for mac in macs:
                mac = str(mac).lower()
                if MAC.fullmatch(mac): configured.setdefault(row.get('ip'),set()).add(mac)
    observed = {}
    for line in neighbors.splitlines():
        fields = line.split()
        if len(fields) < 6: continue
        try:
            ip = str(ipaddress.ip_address(fields[0]))
            if ipaddress.ip_address(ip) not in ipaddress.ip_network('192.168.1.0/24'): continue
            interface = fields[fields.index('dev')+1]
            mac = fields[fields.index('lladdr')+1].lower()
            if interface != 'br-lan' or not MAC.fullmatch(mac): continue
            observed.setdefault(ip,[]).append((mac, fields[-1]))
        except (ValueError,IndexError): continue
    devices = []
    for ip, bindings in observed.items():
        if len(bindings) != 1: continue
        mac, state = bindings[0]
        if state != 'REACHABLE' or configured.get(ip) != {mac}: continue
        devices.append({'ip':ip,'mac':mac,'name':names.get(mac,ip),'state':state,
                        'interface':'br-lan','observed_at':sampled_at})
    return {'source':'router-native','sampled_at':sampled_at,'devices':devices}


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(data,out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp,path)


def collect(router, key, output, run=subprocess.run, now=time.time):
    command = ['ssh','-F','/dev/null','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
               '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',router]
    started = now()
    try:
        inventory = run(command+['/usr/libexec/home-network-read inventory'],capture_output=True,text=True,check=True,timeout=10)
        neighbors = run(command+['/usr/libexec/home-network-read neighbors'],capture_output=True,text=True,check=True,timeout=10)
        data = build_inventory(json.loads(inventory.stdout),neighbors.stdout,started)
        _write(output,data)
        return data
    except Exception:
        _write(output,{'source':'router-native','sampled_at':now(),'devices':[]})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--router',required=True)
    parser.add_argument('--key',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    try:
        data = collect(args.router,args.key,args.output)
    except Exception:
        parser.exit(1,'Inventory unavailable; trust disabled.\n')
    print('Fresh verified devices:',len(data['devices']))


if __name__ == '__main__': main()
