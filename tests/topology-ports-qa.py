"""Synthetic port inspection QA; never reads LAN inventory."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def mount(browser, mobile=False):
    page = browser.new_page(viewport={"width": 390 if mobile else 1440, "height": 900}, has_touch=mobile, is_mobile=mobile)
    page.route("**/*", lambda route: route.fulfill(content_type="text/html", body='<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><main id="dashboard"><section id="topology"></section></main></html>'))
    page.goto("http://localhost/ports-qa")
    for file in ("style.css", "topology.css"):
        page.add_style_tag(path=str(ROOT / "dashboard/static" / file))
    page.evaluate("""() => {
      window.setInterval=callback=>{window.pollTopology=callback;return 1;};
      window.fixture={revision:1,nodes:[
        {id:'r',name:'Gateway',type:'router',ip:'192.0.2.1',mac:'',x:40,y:40,ports:['LAN 1']},
        {id:'a',name:'Studio workstation',type:'desktop',ip:'192.0.2.20',mac:'',x:40,y:300,discovery:{source:'fdb',attachment:'lan2',confidence:'Observed',last_seen:1}},
        {id:'b',name:'Media server',type:'server',ip:'192.0.2.21',mac:'',x:300,y:300,discovery:{source:'fdb',attachment:'lan2',confidence:'Observed',last_seen:1}},
        {id:'s',name:'Office switch',type:'switch',ip:'',mac:'',x:560,y:300,ports:['1','2','3','4']},
        {id:'w',name:'Phone',type:'phone',ip:'',mac:'',x:800,y:300,discovery:{source:'iw',attachment:'phy0-ap0',confidence:'Observed',last_seen:1}}
      ],links:[{id:'c',source:'r',target:'s',source_port:'LAN 1',target_port:'1'}]};
      window.dashboardBridge={version:1,session:{authenticated:true},language:'en',translate:k=>k,replaceSession(s){this.session=s},api:async(url,body)=>{if(body)window.fixture=structuredClone(body.topology);return structuredClone(fixture)}};
    }""")
    page.add_script_tag(path=str(ROOT / "dashboard/static/topology.js"))
    page.wait_for_selector(".map-node")
    return page


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = mount(browser)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    assert page.locator(".map-wires text").count() == 0, "Permanent edge text must be absent"
    assert page.locator('.map-internet').inner_text() == 'Internet'
    assert page.locator('.map-wan').inner_text() == 'WAN'
    assert page.locator('.map-upstream').count() == 1
    assert page.evaluate('fixture.nodes.every(n=>n.name!=="Internet")')
    page.locator('[data-node="a"]').hover()
    assert page.locator(".map-wire.is-active").count() == 1
    assert page.locator('.map-port.is-active[data-port="lan2"]').count() == 1
    inspector = page.locator("#map-inspector")
    text = inspector.inner_text()
    assert all(t in text for t in ("Studio workstation", "Gateway", "lan2", "port unknown", "Detected")), text
    assert inspector.locator(".map-endpoint-port").evaluate_all("els=>els.every(e=>parseFloat(getComputedStyle(e).fontSize)>=20)")
    assert page.locator('.map-port[data-port="lan2"]').count() == 1, "Shared detected LAN interface is one socket"
    assert page.locator('.map-wire.via').count() == 2
    assert page.locator('.map-wire.wifi').count() == 0
    assert page.locator('[data-node="w"] .map-wifi-badge').count() == 1
    assert page.evaluate("""() => {const c=document.querySelector('.map-canvas').getBoundingClientRect();return [...document.querySelectorAll('.map-wire')].every(w=>['source','target'].every((side,i)=>{const id=w.dataset[side],port=w.dataset[side+'Port'];const socket=[...document.querySelectorAll('.map-port')].find(s=>s.dataset.owner===id&&s.dataset.port===port);if(!socket)return !port;const b=socket.getBoundingClientRect(),p=w.getPointAtLength(i?w.getTotalLength():0);return Math.abs(p.x-(b.x-c.x+b.width/2))<1&&Math.abs(p.y-(b.bottom-c.y))<1;}));}"""), "Edges must attach to actual on-screen sockets"
    page.mouse.move(0, 0)
    page.wait_for_timeout(300)
    assert page.locator(".map-wire.is-active").count() == 0
    page.locator('[data-node="s"]').focus()
    assert "Manual" in inspector.inner_text()
    page.keyboard.press("Escape")
    assert page.locator(".map-wire.is-active").count() == 0
    page.locator('[data-node="s"]').hover()
    page.get_by_role('button', name='Adjust route', exact=True).click()
    handle = page.locator('.map-route-handle').first
    handle.focus()
    page.keyboard.press('ArrowRight')
    assert page.locator('#map-save').is_enabled()
    page.get_by_role('button', name='Save map', exact=True).click()
    page.wait_for_function("fixture.routes && fixture.routes[JSON.stringify(['manual','c'])]")
    assert page.evaluate('fixture.nodes.every(n=>n.name!=="Internet")')
    # Node/link forms must gate even synthetic events before route preview.
    for editor_name in ('Add device', 'Add connection'):
        before_path = page.locator('.map-wire.is-active').get_attribute('d')
        before_routes = page.evaluate('JSON.stringify(fixture.routes)')
        page.get_by_role('button', name=editor_name, exact=True).click()
        handle = page.locator('.map-route-handle').first
        assert handle.is_disabled(), 'Route handles must be disabled while a form is open'
        assert page.get_by_role('button', name='Adjust route', exact=True).is_disabled()
        assert page.get_by_role('button', name='Reset route to automatic', exact=True).is_disabled()
        handle.evaluate("""h => {
          h.setPointerCapture=()=>{};
          h.dispatchEvent(new PointerEvent('pointerdown',{button:0,pointerId:1,clientX:10,clientY:10}));
          h.dispatchEvent(new PointerEvent('pointermove',{pointerId:1,clientX:60,clientY:40}));
          h.dispatchEvent(new PointerEvent('pointerup',{pointerId:1}));
          h.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}));
        }""")
        assert page.locator('.map-wire.is-active').get_attribute('d') == before_path
        assert page.evaluate('JSON.stringify(fixture.routes)') == before_routes
        page.locator('#map-form').get_by_role('button', name='Cancel', exact=True).click()
        assert handle.is_enabled()
        assert page.get_by_role('button', name='Reset route to automatic', exact=True).is_enabled()
    # Physical pointer drag at 50% zoom persists unscaled canvas coordinates.
    page.locator('#map-canvas').evaluate("c=>c.style.zoom='0.5'")
    handle = page.locator('.map-route-handle').first
    handle.scroll_into_view_if_needed()
    original = page.evaluate("fixture.routes[JSON.stringify(['manual','c'])][0]")
    box = handle.bounding_box()
    x,y = box['x']+box['width']/2,box['y']+box['height']/2
    page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+20,y+15,steps=5); page.mouse.up()
    page.get_by_role('button', name='Save map', exact=True).click()
    assert page.evaluate("fixture.routes[JSON.stringify(['manual','c'])][0]") == {'x':original['x']+40,'y':original['y']+30}
    saved_routes = page.evaluate('JSON.stringify(fixture.routes)')
    page.get_by_role('button', name='Reload saved map', exact=True).click()
    assert page.evaluate('JSON.stringify(fixture.routes)') == saved_routes
    page.get_by_role('button', name='Refresh discovered devices', exact=True).click()
    page.locator('#map-preview').get_by_role('button', name='Apply to draft', exact=True).click()
    page.get_by_role('button', name='Save map', exact=True).click()
    assert page.evaluate('JSON.stringify(fixture.routes)') == saved_routes
    page.locator('#map-canvas').evaluate("c=>c.style.zoom='1'")
    page.get_by_role('button', name='Reset route to automatic', exact=True).click()
    assert page.locator('.map-route-handle').count() == 0, 'Reset removes handles'
    page.get_by_role('button', name='Save map', exact=True).click()
    assert page.evaluate("!fixture.routes || !fixture.routes[JSON.stringify(['manual','c'])]")
    before = page.locator('[data-node="r"]').bounding_box()['width']
    page.get_by_role('button', name='Zoom out', exact=True).click()
    assert page.locator('[data-node="r"]').bounding_box()['width'] < before
    # Drag uses canvas coordinates, not zoomed CSS pixels.
    node=page.locator('[data-node="r"]')
    node.scroll_into_view_if_needed()
    box=node.bounding_box()
    x,y=box['x']+30,box['y']+30
    page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+34,y+17,steps=5); page.mouse.up()
    page.wait_for_timeout(50)
    assert node.evaluate('n=>parseInt(n.style.left)')==80
    assert node.evaluate('n=>parseInt(n.style.top)')==60
    page.get_by_role('button', name='Save map', exact=True).click()
    page.get_by_role('button', name='Zoom in', exact=True).click()
    # Observation and WAN bends persist as presentation metadata only.
    for selector,key in [('[data-node="a"]','["observed","r","a","lan2",""]'),('.map-internet','["wan","r"]')]:
        page.get_by_role('button', name='Clear inspection', exact=True).click()
        page.locator(selector).hover()
        page.get_by_role('button', name='Adjust route', exact=True).click()
        page.locator('.map-route-handle').first.focus()
        page.keyboard.press('ArrowDown')
        page.get_by_role('button', name='Save map', exact=True).click()
        assert page.evaluate('(key)=>!!fixture.routes[key]',key)
        page.get_by_role('button', name='Reload saved map', exact=True).click()
        assert page.locator('.map-route-handle').count()>0
        assert page.evaluate('(key)=>!!fixture.routes[key]',key)
        assert page.evaluate('fixture.nodes.length===5&&fixture.links.length===1')
    # Default-routing screenshots, not the deliberately edited waypoint fixture.
    page.evaluate('fixture.routes={}')
    page.get_by_role('button', name='Reload saved map', exact=True).click()
    page.get_by_role('button', name='Auto arrange', exact=True).click()
    page.locator('[data-node="a"]').hover()
    output = ROOT / 'output/playwright'
    output.mkdir(parents=True, exist_ok=True)
    page.get_by_role('button', name='Clear inspection', exact=True).click()
    page.locator('[data-node="a"]').hover()
    page.locator('#topology').screenshot(path=str(output/'ports-desktop.png'))
    mobile = mount(browser, True)
    mobile.locator('[data-node="a"]').tap()
    assert mobile.locator('#map-form').is_hidden(), 'Touch selects, not edits'
    assert 'Studio workstation' in mobile.locator('#map-inspector').inner_text()
    assert mobile.locator('.map-wire.is-active').count() == 1
    mobile.evaluate("fixture.nodes.find(n=>n.id==='a').name='Renamed workstation';pollTopology()")
    mobile.wait_for_function("document.querySelector('#map-inspector').textContent.includes('Renamed workstation')")
    assert mobile.locator('.map-wire.is-active').count() == 1
    assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
    mobile.locator('#map-inspector').scroll_into_view_if_needed()
    mobile.screenshot(path=str(output/'ports-mobile.png'))
    assert not errors, errors
    browser.close()
    print('PASS: quiet edges, inspection, shared detected port, socket anchors, keyboard reset, touch selection, mobile overflow, screenshots')
