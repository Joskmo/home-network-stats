"""Host-side sampler: SSH key stays outside the web container, router runs only ash."""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Native OpenWrt ash/ubus/jsonfilter and sysfs only. No router Python or installs.
NATIVE_COMMAND = '''s=$(ubus call network.interface.wan status) || exit 1
d=$(printf '%s' "$s" | jsonfilter -e '@.l3_device')
u=$(printf '%s' "$s" | jsonfilter -e '@.uptime')
case "$d" in ''|*[!a-zA-Z0-9_.:-]*) exit 1;; esac
read -r rx < "/sys/class/net/$d/statistics/rx_bytes" || exit 1
read -r tx < "/sys/class/net/$d/statistics/tx_bytes" || exit 1
printf '{"device":"%s","rx_bytes":%s,"tx_bytes":%s,"uptime":%s}\\n' "$d" "$rx" "$tx" "$u"
'''


def speed_delta(before, after, elapsed):
    if not before or not 0 < elapsed <= 20 or before['device'] != after['device'] or after['uptime'] <= before['uptime']:
        return None
    if any(after[k] < before[k] for k in ('rx_bytes','tx_bytes')): return None
    return {'download_bps':(after['rx_bytes']-before['rx_bytes'])*8/elapsed,
            'upload_bps':(after['tx_bytes']-before['tx_bytes'])*8/elapsed}


def collect(router, key, command=NATIVE_COMMAND):
    if router.startswith('-') or any(c.isspace() for c in router): raise ValueError('Invalid router')
    raw = subprocess.run(['ssh','-i',str(key),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        '-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1',router,command],
        check=True,capture_output=True,text=True,timeout=12).stdout
    value = json.loads(raw)
    for name in ('rx_bytes','tx_bytes','uptime'):
        value[name] = int(value[name])
        if value[name]<0: raise ValueError('Negative counter')
    return value


def main():
    router, key = os.environ['TRAFFIC_ROUTER'], os.environ['TRAFFIC_SSH_KEY']
    target = Path(os.environ['DASHBOARD_SPEED_FILE'])
    target.parent.mkdir(parents=True,exist_ok=True)
    before, previous, wall_previous = None, None, None
    while True:
        started = time.monotonic()
        try:
            after = collect(router,key,os.environ.get('DASHBOARD_ROUTER_COMMAND',NATIVE_COMMAND))
            sampled = time.monotonic()
            delta = speed_delta(before,after,sampled-previous) if previous is not None else None
            wall = time.time()
            record_wan(target.with_name('wan.sqlite3'),before,after,wall_previous or wall,wall,sampled-previous if previous is not None else 0)
            wall_previous = wall
            before, previous = after, sampled
            value = (delta or {'download_bps':None,'upload_bps':None}) | {'sampled_at':time.time()}
        except (OSError,ValueError,KeyError,sqlite3.Error,subprocess.SubprocessError):
            before, previous, wall_previous = None, None, None
            value = {'download_bps':None,'upload_bps':None,'sampled_at':time.time(),'error':'sample_failed'}
        temp = target.with_suffix('.tmp')
        fd = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o640)
        with os.fdopen(fd,'w') as stream: json.dump(value,stream)
        os.replace(temp,target)
        time.sleep(max(0.1,5-(time.monotonic()-started)))


def record_wan(path, before, after, start, end, elapsed):
    """Persist only observed link deltas; baseline/reset/gap never invent bytes."""
    delta = speed_delta(before,after,elapsed)
    same_month = datetime.fromtimestamp(start,ZoneInfo('Europe/Moscow')).strftime('%Y-%m') == datetime.fromtimestamp(end,ZoneInfo('Europe/Moscow')).strftime('%Y-%m')
    valid = delta is not None and same_month and 0 < end-start <= 20
    usage = {'download':after['rx_bytes']-before['rx_bytes'],'upload':after['tx_bytes']-before['tx_bytes']} if valid else {}
    db = sqlite3.connect(path,timeout=2)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS intervals(start REAL,end REAL,usage TEXT,covered REAL,issues TEXT)')
            db.execute('INSERT INTO intervals VALUES(?,?,?,?,?)',(start,end,json.dumps(usage),end-start if valid else 0,json.dumps([] if valid else ['baseline, reset or gap'])))
    finally: db.close()


if __name__ == '__main__': main()
