"""Read-only discovery evidence, never physical wiring or authentication proof."""
import time
import re
from .topology import lan_ip

MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')


def parse(inventory, native, sampled_at):
    devices, ports, fdb, wifi = {}, {}, {}, {}
    def device(mac):
        mac = mac.lower()
        if not MAC.fullmatch(mac) or int(mac[:2],16) & 1 or mac == '00:00:00:00:00:00': return None
        return devices.setdefault(mac, dict(mac=mac,ip='',name=mac,source='DHCP lease',last_seen=sampled_at,attachment='',confidence='Lease only; connection unknown'))
    # Active lease inventory is not reachability proof. Reservations alone are not discoveries.
    for row in inventory.get('leases',[]):
        d = device(str(row.get('mac','')))
        if d is None: continue
        try: ip = lan_ip(row.get('ip',''))
        except ValueError: continue
        d['ip'] = ip
        name = str(row.get('name','')).strip()
        if name and name != '*' and len(name)<=80 and not any(ord(c)<32 for c in name): d['name']=name
    mode = ''
    for line in native.splitlines():
        fields = line.split()
        if not fields: continue
        if fields[0]=='ROUTER' and len(fields)==3:
            try: ip = lan_ip(fields[1])
            except ValueError: continue
            d = device(fields[2])
            if d is not None:
                d.update(ip=ip, name='Router', source='router interface',
                         attachment='br-lan', confidence='Observed router LAN interface')
        elif fields[0]=='PORT' and len(fields)==3:
            try: ports[int(fields[2],0)] = fields[1]
            except ValueError: pass
        elif fields[0]=='FDB': mode='fdb'
        elif fields[0]=='WIFI' and len(fields)==2: mode=fields[1]
        elif mode=='fdb' and len(fields)==4 and fields[2]=='no':
            try:
                port, age = int(fields[0]),float(fields[3])
                if 0 <= age <= 300: fdb.setdefault(fields[1].lower(),set()).add(port)
            except ValueError: pass
        elif mode not in ('','fdb') and fields[0]=='Station' and len(fields)>=2:
            wifi.setdefault(fields[1].lower(),set()).add(mode)
    for mac, numbers in fdb.items():
        d=device(mac)
        if d is None: continue
        if len(numbers)==1 and next(iter(numbers)) in ports:
            d.update(attachment=ports[next(iter(numbers))],source='brctl FDB + sysfs',confidence='Reachable via; intermediate topology unknown')
    for mac, interfaces in wifi.items():
        d=device(mac)
        if d is not None and len(interfaces)==1:
            d.update(attachment=next(iter(interfaces)),source='iw station',confidence='Observed Wi-Fi association')
    return {'sampled_at':sampled_at,'devices':list(devices.values())}

from .topology import validate, atomic_json, MAX_BYTES
import json
import subprocess
from pathlib import Path

# Fixed read-only ash; no user input, scans, packages or configuration reads.
NATIVE = r"""set -e
if [ -r /sys/class/net/br-lan/address ]; then
    read -r router_mac < /sys/class/net/br-lan/address
    ip -4 -o addr show dev br-lan | while read -r index iface family address rest; do
        [ "$family" = inet ] || continue
        printf 'ROUTER %s %s\n' "${address%/*}" "$router_mac"
    done
fi
for p in /sys/class/net/br-lan/brif/*; do
    [ -r "$p/port_no" ] || continue
    read -r port < "$p/port_no"
    printf 'PORT %s %s\n' "${p##*/}" "$port"
done
printf 'FDB\n'
brctl showmacs br-lan
for p in /sys/class/net/br-lan/brif/*; do
    i=${p##*/}
    if [ -d "/sys/class/net/$i/phy80211" ]; then
        printf 'WIFI %s\n' "$i"
        iw dev "$i" station dump
    fi
done
"""


def collect(router, key, output, run=subprocess.run, now=time.time):
    command=['ssh','-F','/dev/null','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
             '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',router]
    sampled_at=now()
    inventory=run(command+['/usr/libexec/home-network-read inventory'],capture_output=True,text=True,check=True,timeout=10)
    native=run(command+[NATIVE],capture_output=True,text=True,check=True,timeout=10)
    result=parse(json.loads(inventory.stdout),native.stdout,sampled_at)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    atomic_json(output,result)  # On failure previous evidence ages out; never mark history absent.
    return result


def preview(store, graph):
    path=store.directory/'discovery.json'
    if path.stat().st_size > MAX_BYTES: raise ValueError('Discovery too large')
    return merge(graph,json.loads(path.read_text()))



def merge(graph, snapshot, now=None):
    now = time.time() if now is None else now
    graph = validate(graph)
    if not 0 <= now - snapshot['sampled_at'] <= 90:
        raise ValueError('Discovery expired; try again')
    by_mac = {n['mac'].lower(): n for n in graph['nodes'] if n['mac']}
    for row in snapshot['devices']:
        mac = row['mac'].lower()
        node = by_mac.get(mac)
        if node is None:
            i = len(graph['nodes'])
            node = dict(id='mac-'+mac.replace(':',''), name=row['name'] or mac,
                        type='router' if row['source']=='router interface' else 'device',
                        ip='',mac=mac,x=40+(i%8)*190,y=40+(i//8)*100)
            graph['nodes'].append(node)
            by_mac[mac] = node
        elif node.get('discovery',{}).get('name') == node['name']:
            node['name'] = row['name'] or mac
        if row['ip']: node['ip'] = row['ip']
        if row['source']=='router interface' and node['type']=='device':
            node['type'] = 'router'
        node['discovery'] = {k: row[k] for k in ('name','source','last_seen','attachment','confidence')}
    return validate(graph)


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--router',required=True)
    p.add_argument('--key',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    result=collect(args.router,args.key,args.output)
    print('Discovered devices:',len(result['devices']))


if __name__=='__main__': main()
