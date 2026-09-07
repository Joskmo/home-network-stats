"""Isolated headless QA against real HTTP/auth/storage; fixture is NOT LAN data.

Run: uv run --with playwright python tests/topology-integration-qa.py
"""
import json
from pathlib import Path
import sys
import tempfile
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.auth import Auth
from dashboard.access import TrustedDevices
from dashboard.data import snapshot
from dashboard.topology import TopologyStore
from dashboard.web import Application


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def run():
    with tempfile.TemporaryDirectory(prefix='topology-http-qa-') as directory:
        path = Path(directory)
        auth = Auth(path / 'auth.json', 'isolated-topology-bootstrap')
        store = TopologyStore(path / 'map')
        store.save({'revision': 0, 'nodes': [
            dict(id='router', name='QA Router', type='router', ip='192.168.1.1',
                 mac='', x=40, y=40, ports=['WAN', 'LAN 1', 'LAN 2']),
            dict(id='desktop', name='QA Desktop', type='desktop', ip='192.168.1.20',
                 mac='', x=360, y=320, ports=['NIC']),
            dict(id='phone', name='QA Phone', type='phone', ip='192.168.1.21',
                 mac='', x=720, y=320),
        ], 'links': [
            dict(id='ethernet', source='router', target='desktop', source_port='LAN 1',
                 target_port='NIC', medium='ethernet'),
            dict(id='wifi', source='router', target='phone', source_port='5 GHz',
                 target_port='Wi-Fi', medium='wifi'),
        ]})
        app = Application(auth, lambda: snapshot(path/'missing.sqlite', path/'speed.json'),
                          topology=store, access=TrustedDevices(path/'trusted.json', path/'inventory.json'))
        server = make_server('127.0.0.1', 0, app, handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1100}, locale='en-GB')
                errors = []
                failed_responses = []
                page.on('response', lambda r: failed_responses.append((r.url, r.status)) if r.status >= 400 else None)
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda m: errors.append(m.text) if m.type in ('error', 'warning') else None)
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#password').fill('isolated-topology-bootstrap')
                page.locator('#submit').click()
                page.locator('#confirm').wait_for(state='visible')
                page.locator('#password').fill('isolated-topology-new-password')
                page.locator('#confirm').fill('isolated-topology-new-password')
                page.locator('#submit').click()
                page.locator('[data-node="router"]').wait_for()
                assert page.locator('.map-node').count() == 3
                page.locator('[data-node="desktop"]').click()
                page.locator('#map-name').fill('QA Workstation')
                page.locator('#map-type').select_option('laptop')
                page.locator('#map-form button[type="submit"]').click()
                page.locator('#map-save').click()
                expect(page.locator('#map-message')).to_have_text('Map saved')
                expect(page.locator('#map-save')).to_be_disabled()
                saved = store.read()
                desktop = next(n for n in saved['nodes'] if n['id'] == 'desktop')
                assert desktop['name'] == 'QA Workstation' and desktop['type'] == 'laptop'
                assert saved['links'][1]['medium'] == 'wifi'
                assert saved['nodes'][0]['ports'] == ['WAN', 'LAN 1', 'LAN 2']
                page.reload()
                page.locator('[data-node="desktop"]').wait_for()
                assert 'QA Workstation' in page.locator('[data-node="desktop"]').inner_text()
                assert 'Laptop' in page.locator('[data-node="desktop"]').inner_text()
                page.get_by_role('button', name='Insert switch', exact=True).click()
                expect(page.locator('.map-node')).to_have_count(4)
                positions = page.locator('.map-node').evaluate_all('(nodes) => Object.fromEntries(nodes.map(n => [n.dataset.node, [n.style.left, n.style.top]]))')
                page.locator('#map-save').click()
                expect(page.locator('#map-message')).to_have_text('Map saved')
                split = store.read()
                switch = next(n for n in split['nodes'] if n['type'] == 'switch')
                assert not switch['ip'] and not switch['mac']
                assert len(split['links']) == 3
                first = next(l for l in split['links'] if l['target'] == switch['id'])
                second = next(l for l in split['links'] if l['source'] == switch['id'])
                assert (first['source'], first['source_port']) == ('router', 'LAN 1')
                assert (second['target'], second['target_port']) == ('desktop', 'NIC')
                assert next(l for l in split['links'] if l['id'] == 'wifi') == saved['links'][1]
                page.reload()
                expect(page.locator('.map-node')).to_have_count(4)
                restored = page.locator('.map-node').evaluate_all('(nodes) => Object.fromEntries(nodes.map(n => [n.dataset.node, [n.style.left, n.style.top]]))')
                assert restored == positions, (positions, restored)
                expect(page.get_by_role('button', name='Insert switch', exact=True)).to_have_count(2)
                output = Path('output/playwright'); output.mkdir(parents=True, exist_ok=True)
                page.locator('#topology').screenshot(path=str(output/'topology-http-desktop.png'))
                page.locator('#language').click()
                assert page.locator('html').get_attribute('lang') == 'ru'
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('#topology').scroll_into_view_if_needed()
                width = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
                assert width['width'] == width['scroll'], width
                page.screenshot(path=str(output/'topology-http-mobile.png'))
                assert not errors, (errors, failed_responses)
                browser.close()
                print(json.dumps({'real_http': True, 'auth_rotation': True,
                                  'saved_revision': saved['revision'], 'reload_preserved_type': True,
                                  'ports_and_wifi_preserved': True, 'mobile': width,
                                  'switch_split_persisted': True,
                                  'console_errors_warnings': errors}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    run()
