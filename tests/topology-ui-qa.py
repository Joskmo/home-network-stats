"""Isolated browser QA: synthetic fixture, no live network/auth state touched.
Run: uv run --with playwright python tests/topology-ui-qa.py
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('http://localhost/qa',lambda route:route.fulfill(content_type='text/html',body='<html></html>'))
    page.goto('http://localhost/qa')
    page.set_content('<html lang="en"><style>body{margin:0;background:#101920;color:white;font:14px sans-serif}button{font:inherit}</style><main id="dashboard"><section id="topology"></section></main></html>')
    page.add_style_tag(path=str(ROOT/'dashboard/static/style.css'))
    page.add_style_tag(path=str(ROOT/'dashboard/static/topology.css'))
    page.evaluate('''() => {window.fixture={revision:1,nodes:[{id:'r',name:'Router',type:'router',ip:'192.168.1.1',mac:'',x:40,y:40,ports:['LAN 1','LAN 2']},{id:'p',name:'Phone',type:'phone',ip:'',mac:'',x:300,y:300,discovery:{source:'iw station',attachment:'phy0-ap0',last_seen:1,confidence:'Observed'}},{id:'d',name:'Desktop',type:'desktop',ip:'',mac:'',x:600,y:300,ports:['eth0']}],links:[{id:'c',source:'r',target:'d',source_port:'LAN 1',target_port:'eth0'}]};window.api=async (url,body)=>{if(url==='/api/topology/preview')return structuredClone(body.topology);if(window.failSave&&body){const error=new Error('conflict');error.status=409;throw error;}if(body){window.saved=JSON.parse(JSON.stringify(body.topology));return window.saved;}return window.fixture;};window.dashboardBridge={version:1,session:{authenticated:true},language:'en',translate:key=>key,replaceSession(session){this.session=session},api:window.api};}''')
    page.add_script_tag(path=str(ROOT/'dashboard/static/topology.js'))
    page.wait_for_selector('.map-node')
    assert page.locator('.map-node > svg').count()==3,'device SVG icons missing'
    assert page.locator('.map-port').count()>=3,'labeled port sockets missing'
    assert page.locator('.map-wire.wifi').count()==0,'WiFi observations must not draw lines'
    assert page.locator('[data-node="p"] .map-wifi-badge').count()==1,'WiFi badge must remain'
    assert page.evaluate('''() => {const wire=document.querySelector('.map-wire.ethernet'),canvas=document.getElementById('map-canvas').getBoundingClientRect();return ['Router · LAN 1','Desktop · eth0'].every((title,i)=>{const r=[...document.querySelectorAll('.map-port')].find(p=>p.title===title).getBoundingClientRect(),a=wire.getPointAtLength(i?wire.getTotalLength():0);return Math.abs(a.x-(r.x-canvas.x+r.width/2))<1&&Math.abs(a.y-(r.bottom-canvas.y))<1&&r.height===22;});}'''),'wire endpoint must match actual socket bottom-center'
    page.evaluate('Object.defineProperty(crypto,"randomUUID",{value:undefined,configurable:true})')
    page.get_by_role('button',name='Insert switch',exact=True).click()
    page.get_by_role('button',name='Save map',exact=True).click()
    saved=page.evaluate('window.saved')
    assert len(saved['nodes'])==4 and len(saved['links'])==2
    assert saved['links'][0]['source_port']=='LAN 1' and saved['links'][1]['target_port']=='eth0'
    assert saved['nodes'][-1]['ip']==''
    assert page.evaluate('''() => {const paths=[...document.querySelectorAll('.map-wire.ethernet')].map(p=>p.getAttribute('d'));const lanes=paths.map(d=>d.match(/H([\\d.]+)/)[1]);return new Set(lanes).size===lanes.length;}'''),'serial cables must not share a bus lane'
    page.get_by_role('button',name='Auto arrange',exact=True).click()
    page.locator('[data-node="p"]').click()
    page.locator('#map-type').select_option('laptop')
    page.locator('#map-ports').fill('USB-C\nDock')
    page.get_by_role('button',name='Apply to draft',exact=True).click()
    page.get_by_role('button',name='Save map',exact=True).click()
    assert page.evaluate('window.saved.nodes.find(n=>n.id==="p").ports')==['USB-C','Dock']
    page.screenshot(path='/tmp/topology-desktop.png',full_page=True)
    page.get_by_role('button',name='Add connection',exact=True).click()
    page.locator('#map-medium').select_option('wifi')
    page.locator('#map-source').select_option('r')
    page.locator('#map-target').select_option('p')
    page.get_by_role('button',name='Apply to draft',exact=True).click()
    page.get_by_role('button',name='Save map',exact=True).click()
    assert page.evaluate('window.saved.links.filter(l=>l.medium==="wifi").length')==1
    assert page.locator('.map-wire.wifi').count()==0,'Manual WiFi connections must not draw lines'
    assert page.locator('[data-node="p"] .map-wifi-badge').count()==1
    assert page.get_by_role('button',name='Insert switch',exact=True).count()==2,'WiFi cannot be split by a switch'
    # Preview remains a draft and a conflict never discards the local edit.
    page.evaluate("""() => {window.fixture=structuredClone(window.saved);} """)
    page.get_by_role('button',name='Refresh discovered devices',exact=True).click()
    page.get_by_role('heading',name='Discovery preview — nothing saved',exact=True).wait_for()
    page.locator('#map-preview').get_by_role('button',name='Cancel',exact=True).click()
    assert page.locator('#map-preview').is_hidden()
    page.get_by_role('button',name='Auto arrange',exact=True).click()
    page.evaluate('window.failSave=true')
    page.get_by_role('button',name='Save map',exact=True).click()
    page.wait_for_function("document.getElementById('map-message').textContent.startsWith('Another editor saved first')")
    assert page.locator('.map-node').count()==4
    assert page.locator('#map-save').is_enabled()
    page.evaluate('window.failSave=false')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'mobile overflow'
    page.evaluate('dashboardBridge.language="ru";document.documentElement.lang="ru"')
    page.get_by_role('button',name='Разместить автоматически',exact=True).wait_for()
    page.screenshot(path='/tmp/topology-mobile.png',full_page=True)
    assert not errors,errors
    print(json.dumps({'result':'PASS','saved_nodes':len(saved['nodes']),'saved_links':len(saved['links']),'console_errors':errors,'mobile_width':390}))
    security=browser.new_page()
    security.on('pageerror',lambda e:errors.append(str(e)))
    security.set_content('<section id="security"></section>')
    security.evaluate("""() => {
      window.calls=[];
      window.dashboardBridge={version:1,language:'en',session:{password_authenticated:true,trusted_device:true},translate:key=>key,replaceSession(value){this.session=value;},
        api:async(path,payload)=>{if(payload){calls.push({path,payload});return {};}
          return {devices:[{id:'synthetic',name:'QA Device',ip:'192.168.1.2',trusted:false}],trusted:[]};}};
    }""")
    security.add_script_tag(path=str(ROOT/'dashboard/static/security.js'))
    security.locator('#trusted-select').wait_for()
    assert security.locator('#trusted-select option').inner_text()=='QA Device · 192.168.1.2'
    security.get_by_role('button',name='Trust selected device',exact=True).click()
    security.wait_for_function('calls.length===1')
    assert security.evaluate('calls[0]')=={'path':'/api/trusted','payload':{'action':'add','device_id':'synthetic'}}
    security.get_by_text('Reset password from this trusted LAN device',exact=True).click()
    security.locator('#recover-password').fill('synthetic-password-a')
    security.locator('#recover-confirm').fill('synthetic-password-b')
    security.get_by_role('button',name='Reset password and clear all sessions',exact=True).click()
    assert security.locator('#security-message').inner_text()=='mismatch'
    assert security.evaluate('calls.length')==1
    assert not errors,errors
    browser.close()
