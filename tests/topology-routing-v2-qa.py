"""Isolated real-browser routing geometry regression; no LAN/API access."""
import json
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/playwright'
OUT.mkdir(parents=True, exist_ok=True)
phase = sys.argv[1] if len(sys.argv) > 1 else 'green'
subprocess.run(['node', '-e', "require('esbuild').buildSync({entryPoints:['frontend/topology.ts'],bundle:true,format:'iife',outfile:'output/playwright/router-v2.js'})"], cwd=ROOT, check=True)
result = {'phase': phase, 'checks': {}, 'screenshots': [], 'errors': []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda e: result['errors'].append(str(e)))
    page.route('**/*', lambda r: r.fulfill(content_type='text/html', body='<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><main id="dashboard"><section id="topology"></section></main></html>'))
    page.goto('http://localhost/router-v2-qa')
    for f in ['style.css', 'topology.css']:
        page.add_style_tag(path=str(ROOT / 'dashboard/static' / f))
    page.evaluate('''() => {
      const n=(id,type='desktop',ports=[])=>({id,name:id,type,ports,x:40,y:40,ip:'192.0.2.1',mac:''});
      window.fixture={revision:1,nodes:[n('r','router',['lan1','lan2','lan3','lan4']),...['z','a','y','b'].map((id,i)=>({...n(id),discovery:{source:'fdb',attachment:'lan'+(i+1),confidence:'Observed',last_seen:1}}))],links:[]};
      window.setInterval=()=>1;
      window.dashboardBridge={version:1,session:{authenticated:true},language:'en',translate:k=>k,replaceSession(s){this.session=s},api:async(u,body)=>{if(body)fixture=structuredClone(body.topology);return structuredClone(fixture)}};
    }''')
    page.add_script_tag(path=str(OUT / 'router-v2.js'))
    page.wait_for_selector('.map-node')
    page.get_by_role('button', name='Auto arrange', exact=True).click()
    screenshot = OUT / ('router-v2-four-clients-' + phase + '.png')
    page.locator('#topology').screenshot(path=str(screenshot))
    result['screenshots'].append(str(screenshot.relative_to(ROOT)))
    result['geometry'] = page.evaluate('''() => {
      const c=document.querySelector('#map-canvas').getBoundingClientRect();
      return [...document.querySelectorAll('.map-wire')].map(w=>{
        const points=JSON.parse(w.dataset.points),node=document.querySelector('[data-node="'+w.dataset.target+'"]'),r=node.getBoundingClientRect();
        const actual=w.getPointAtLength(w.getTotalLength());
        const socket=[...document.querySelectorAll('.map-port')].find(s=>s.dataset.owner===w.dataset.source&&s.dataset.port===w.dataset.sourcePort),sr=socket.getBoundingClientRect(),start=w.getPointAtLength(0);
        const dock=[...document.querySelectorAll('.map-dock')].find(d=>d.dataset.owner===w.dataset.target);
        const dr=dock?.getBoundingClientRect();
        return {target:w.dataset.target,points,anchor:w.dataset.anchorTarget,top:r.top-c.top,actual:{x:actual.x,y:actual.y},sourceError:Math.max(Math.abs(start.x-(sr.left-c.left+sr.width/2)),Math.abs(start.y-(sr.bottom-c.top))),dockError:dr?Math.max(Math.abs(actual.x-(dr.left-c.left+dr.width/2)),Math.abs(actual.y-(dr.top-c.top))):null};
      });
    }''')
    rows = result['geometry']
    crossings = 0
    for i, route in enumerate(rows):
        for other in rows[i+1:]:
            for a,b in zip(route['points'],route['points'][1:]):
                for c,d in zip(other['points'],other['points'][1:]):
                    if a['y'] == b['y'] and c['x'] == d['x']:
                        crossings += min(a['x'],b['x']) < c['x'] < max(a['x'],b['x']) and min(c['y'],d['y']) < a['y'] < max(c['y'],d['y'])
                    elif a['x'] == b['x'] and c['y'] == d['y']:
                        crossings += min(c['x'],d['x']) < a['x'] < max(c['x'],d['x']) and min(a['y'],b['y']) < c['y'] < max(a['y'],b['y'])
    result['crossings'] = crossings
    result['checks']['zeroCrossings'] = crossings == 0
    result['checks']['fourEdges'] = len(rows) == 4
    result['checks']['targetTop'] = all(abs(r['actual']['y'] - r['top']) < 1 for r in rows)
    result['checks']['noBelowClients'] = all(max(p['y'] for p in r['points']) <= r['top'] + 1 for r in rows)
    result['checks']['actualSocketAnchors'] = all(r['sourceError'] < 1 for r in rows)
    result['checks']['unlabeledDocks'] = all(r['dockError'] is not None and r['dockError'] < 1 for r in rows)
    result['checks']['noRetracing'] = all(not ((b['x']-a['x'])*(c['x']-b['x'])+(b['y']-a['y'])*(c['y']-b['y']) < 0) for r in rows for a,b,c in zip(r['points'],r['points'][1:],r['points'][2:]))
    result['checks']['noWifiWires'] = page.locator('.map-wire.wifi').count() == 0
    result['checks']['wanPresent'] = page.locator('.map-upstream').count() == 1
    page.get_by_role('button', name='Fit map', exact=True).click()
    page.locator('#topology').screenshot(path=str(screenshot))
    page.set_viewport_size({'width': 390, 'height': 900})
    page.get_by_role('button', name='Fit map', exact=True).click()
    result['checks']['mobileNoOverflow'] = page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    mobile = OUT / ('router-v2-mobile-' + phase + '.png')
    page.screenshot(path=str(mobile), full_page=True)
    result['screenshots'].append(str(mobile.relative_to(ROOT)))
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.get_by_role('button', name='Save map', exact=True).click()
    page.wait_for_function('document.querySelector("#map-save").disabled')
    page.evaluate('''() => {
      const n=(id,type,ports,y)=>({id,name:id,type,ports,x:300,y,ip:'',mac:''});
      fixture={revision:1,nodes:[n('router','router',['LAN 1'],64),n('switch','switch',Array.from({length:48},(_,i)=>String(i+1)),350)],links:[{id:'reverse',source:'switch',target:'router',source_port:'1',target_port:'LAN 1'}]};
    }''')
    page.get_by_role('button', name='Reload saved map', exact=True).click()
    page.wait_for_selector('[data-node="switch"]')
    page.get_by_role('button', name='Auto arrange', exact=True).click()
    page.get_by_role('button', name='Fit map', exact=True).click()
    result['namedGeometry'] = page.evaluate('''() => {
      const w=document.querySelector('.map-wire'),n=document.querySelector('[data-node="switch"]'),r=n.getBoundingClientRect(),ports=[...n.querySelectorAll('.map-port')];
      const s=ports.find(s=>s.dataset.port==='1'),b=s.getBoundingClientRect(),a=w.getPointAtLength(0).matrixTransform(w.getScreenCTM());
      const header=n.querySelector('strong').getBoundingClientRect();
      return {count:ports.length,side:s.dataset.side,anchorError:Math.max(Math.abs(a.x-(b.left+b.width/2)),Math.abs(a.y-b.top)),headerBelowTop:header.top>=b.bottom,allWithin:ports.every(p=>{const b=p.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1&&b.top>=r.top-1&&b.bottom<=r.bottom+1})};
    }''')
    ng = result['namedGeometry']
    result['checks']['namedReverseTopSocket'] = ng['side']=='top' and ng['anchorError']<1
    result['checks']['all48WithinCard'] = ng['count']==48 and ng['allWithin'] and ng['headerBelowTop']
    named = OUT / ('router-v2-48ports-' + phase + '.png')
    page.locator('#topology').screenshot(path=str(named))
    result['screenshots'].append(str(named.relative_to(ROOT)))
    result['checks']['noPageErrors'] = not result['errors']
    browser.close()
summary_path = ROOT / 'output/router-v2-summary.json'
summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
summary[phase] = result
summary_path.write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(result, indent=2))
assert all(result['checks'].values()), result['checks']
