import copy
import tempfile
import unittest
from pathlib import Path


def graph():
    return {'revision': 0, 'nodes': [dict(id='router', name='Router', type='router', ip='192.168.1.1', mac='', x=100, y=100), dict(id='switch', name='Switch', type='switch', ip='', mac='', x=400, y=100)], 'links': [dict(id='cable', source='router', target='switch', source_port='LAN 1', target_port='Port 8')]}


class TopologyTests(unittest.TestCase):
    def test_device_kinds_and_physical_port_inventory_round_trip(self):
        from dashboard.topology import TopologyStore, validate
        for kind in ('phone', 'laptop', 'desktop', 'tablet', 'tv', 'printer', 'iot'):
            value = graph()
            value['nodes'][1]['type'] = kind
            value['nodes'][0]['ports'] = ['WAN', 'LAN 1', 'LAN 2']
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                store = TopologyStore(tmp)
                saved = store.save(value)
                self.assertEqual(store.read(), saved)
                self.assertEqual(saved['nodes'][0]['ports'], value['nodes'][0]['ports'])
                self.assertEqual(saved['nodes'][1]['type'], kind)
        for ports in ('LAN 1', [''], ['LAN 1', 'LAN 1'], [' LAN 1 ', 'LAN 1'],
                      ['x' * 33], list(map(str, range(49))), [1]):
            value = graph(); value['nodes'][0]['ports'] = ports
            with self.subTest(ports=ports), self.assertRaises(ValueError):
                validate(value)

    def test_connection_medium_round_trip_and_legacy_default(self):
        from dashboard.topology import TopologyStore, validate
        legacy = graph()
        self.assertEqual(validate(legacy), legacy)
        for medium in ('ethernet', 'wifi'):
            value = graph(); value['links'][0]['medium'] = medium
            with self.subTest(medium=medium), tempfile.TemporaryDirectory() as tmp:
                store = TopologyStore(tmp)
                saved = store.save(value)
                self.assertEqual(store.read(), saved)
                self.assertEqual(saved['links'][0]['medium'], medium)
        for medium in ('', 'bluetooth', None, 12, []):
            value = graph(); value['links'][0]['medium'] = medium
            with self.subTest(medium=medium), self.assertRaises(ValueError):
                validate(value)

    def test_editor_shell_is_present_without_embedded_inventory(self):
        html = Path('dashboard/static/index.html').read_text()
        self.assertIn('id="topology"', html)
        self.assertIn('/topology.js', html)
        self.assertIn('/topology.css', html)
        self.assertNotIn('192.168.1.1', html)

    def test_atomic_persistence_validation_and_revision_conflict(self):
        import dashboard.topology as topology
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            self.assertEqual(store.read()['nodes'], [])
            saved = store.save(graph())
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(topology.TopologyStore(tmp).read()['links'], graph()['links'])
            with self.assertRaises(topology.Conflict): store.save(graph())
            for ip in ['127.0.0.1', '192.168.1.0', '192.168.1.255', '8.8.8.8', 'router.lan', '::1', '192.168.1.2;id']:
                bad = graph(); bad['nodes'][0]['ip'] = ip; bad['revision'] = 1
                with self.subTest(ip=ip), self.assertRaises(ValueError): store.save(bad)
            for mutate in [lambda g:g['nodes'].append(g['nodes'][0]), lambda g:g['links'][0].update(target='missing'), lambda g:g['nodes'][0].update(x=float('nan')), lambda g:g['links'][0].update(source_port=''), lambda g:g.update(nodes=g['nodes']*33)]:
                bad = copy.deepcopy(graph()); bad['revision'] = 1; mutate(bad)
                with self.assertRaises(ValueError): store.save(bad)
            self.assertEqual(store.read()['revision'], 1)

    def test_api_gate_csrf_and_save(self):
        import io, json
        from dashboard.auth import Auth
        from dashboard.web import Application
        from dashboard.topology import TopologyStore
        with tempfile.TemporaryDirectory() as tmp:
            auth = Auth(Path(tmp)/'auth.json', 'bootstrap')
            app = Application(auth, lambda: {}, topology=TopologyStore(Path(tmp)/'map'))
            token, session = auth.session()
            def req(method='GET', payload=None, origin='http://localhost'):
                raw = json.dumps(payload or {}).encode(); status = []
                body = app({'HTTP_HOST':'localhost', 'REMOTE_ADDR':'127.0.0.1', 'PATH_INFO':'/api/topology', 'REQUEST_METHOD':method, 'HTTP_COOKIE':'hn_session='+token, 'HTTP_ORIGIN':origin, 'CONTENT_TYPE':'application/json', 'CONTENT_LENGTH':str(len(raw)), 'wsgi.input':io.BytesIO(raw)}, lambda s,h:status.append(int(s.split()[0])))
                return status[0], json.loads(b''.join(body))
            self.assertEqual(req()[0], 401)
            auth.login(session, 'bootstrap', '127.0.0.1')
            self.assertEqual(req()[0], 403)
            self.assertEqual(req('POST', {'csrf':session['csrf'], 'topology':graph()})[0], 403)
            token = auth.change(session, 'new-password-for-qa'); session = auth.sessions[token]
            self.assertEqual(req()[0], 200)
            self.assertEqual(req('POST', {'csrf':'wrong', 'topology':graph()})[0], 403)
            self.assertEqual(req('POST', {'csrf':session['csrf'], 'topology':graph()}, 'https://evil.invalid')[0], 403)
            self.assertEqual(req('POST', {'csrf':session['csrf'], 'topology':graph()})[0], 200)
            self.assertEqual(req()[1]['nodes'], graph()['nodes'])
            self.assertEqual(req('POST', {'csrf':session['csrf'], 'topology':graph()})[0], 409)

    def test_monitor_status_matches_ip_and_expires(self):
        from dashboard.topology import TopologyStore, sample, atomic_json
        with tempfile.TemporaryDirectory() as tmp:
            store = TopologyStore(tmp); store.save(graph())
            calls = []
            def probe(ip): calls.append(ip); return 'online'
            sample(store, probe=probe, now=100)
            self.assertEqual(calls, ['192.168.1.1'])
            status = store.snapshot(now=110)['monitor']
            self.assertEqual(status['router']['state'], 'online')
            self.assertEqual(status['switch']['state'], 'unknown')
            self.assertEqual(store.snapshot(now=200)['monitor']['router']['state'], 'unknown')
            changed = store.read(); changed['nodes'][0]['ip']='192.168.1.2'; store.save(changed)
            self.assertEqual(store.snapshot(now=110)['monitor']['router']['state'], 'unknown')
            sample(store, probe=lambda ip:'no_reply', now=210)
            self.assertEqual(store.snapshot(now=211)['monitor']['router']['state'], 'no_reply')
