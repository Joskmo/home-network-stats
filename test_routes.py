"""Display-only cable route metadata; no connectivity or evidence inference."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from dashboard import discovery, topology
from test_topology import graph


def key(*parts):
    return json.dumps(parts, separators=(',', ':'))


def routes():
    return {
        key('manual', 'cable'): [{'x': 0, 'y': 32768}, {'x': 1.25, 'y': 2}],
        key('observed', 'router', 'switch', '', 'Port 8'): [{'x': 300, 'y': 100}],
        key('wan', 'router'): [],
        key('manual', 'deleted-link'): [{'x': 50, 'y': 75}],
    }


class RouteTests(unittest.TestCase):
    def test_round_trip_snapshot_and_reset_without_connectivity_changes(self):
        value = graph() | {'routes': routes()}
        original = copy.deepcopy(value)
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            saved = store.save(value)
            self.assertEqual(saved, original | {'revision': 1})
            self.assertEqual(value, original)
            self.assertEqual(store.read(), saved)
            self.assertEqual(store.snapshot(now=100)['routes'], value['routes'])
            self.assertEqual(saved['nodes'], original['nodes'])
            self.assertEqual(saved['links'], original['links'])
            saved['routes'].pop(key('manual', 'cable'))
            store.save(saved)
            self.assertNotIn(key('manual', 'cable'), store.read()['routes'])
            cleared = store.read() | {'routes': {}}
            store.save(cleared)
            self.assertEqual(store.read()['routes'], {})

    def test_preview_import_preserves_routes_and_does_not_create_wiring(self):
        value = graph() | {'routes': routes()}
        original = copy.deepcopy(value)
        evidence = discovery.parse({'leases': [
            {'mac': '02:11:22:33:44:55', 'ip': '192.168.1.22', 'name': 'Discovered'}
        ]}, '', 100)
        baseline = discovery.merge(graph(), evidence, now=101)
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            topology.atomic_json(store.directory / 'discovery.json', evidence)
            with patch('dashboard.discovery.time.time', return_value=101):
                merged = discovery.preview(store, value)
            self.assertEqual(merged, baseline | {'routes': value['routes']})
            self.assertEqual(merged['links'], value['links'])
            self.assertEqual(value, original)
            self.assertFalse(store.path.exists())  # Preview never saves implicitly.
            saved = store.save(merged)
            self.assertEqual(store.read(), saved)
            merged['routes'][key('manual', 'cable')][0]['x'] = 7
            self.assertEqual(value, original)  # Graph copying must not alias metadata.

    def test_legacy_graph_stays_unchanged(self):
        value = graph()
        self.assertEqual(topology.validate(value), value)
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            self.assertEqual(store.read(), {'revision': 0, 'nodes': [], 'links': []})
            self.assertEqual(store.save(value), value | {'revision': 1})
            self.assertNotIn('routes', store.read())
            self.assertNotIn('routes', store.snapshot(now=100))
        merged = discovery.merge(value, {'sampled_at': 100, 'devices': []}, now=101)
        self.assertEqual(merged, value)
        with self.assertRaises(ValueError):
            topology.validate(value | {'unrecognized': {}})

    def test_limits_and_exact_port_keys_are_preserved(self):
        metadata = {key('manual', str(i)): [{'x': 32768, 'y': 0}] * 8 for i in range(127)}
        metadata[key('observed', 'r' * 64, 'n' * 64, 'p' * 32, ' padded ')] = []
        value = {'revision': 0, 'nodes': [], 'links': [], 'routes': metadata}
        self.assertEqual(topology.validate(value), value)
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            store.save(value)
            calls = []
            self.assertEqual(topology.sample(store, probe=lambda ip: calls.append(ip), now=100), {})
            self.assertEqual(calls, [])  # Route IDs never authorize probing devices.
            self.assertEqual(store.read()['routes'], metadata)

    def test_invalid_routes_are_rejected(self):
        valid_key = key('manual', 'cable')
        invalid_keys = [
            '', 'not json', '{}', 'null', 'true', '123', '"manual"', '[]',
            key('unknown', 'router'), key('manual'), key('manual', 'cable', 'extra'),
            key('wan'), key('wan', 'router', 'extra'), key('observed', 'router', 'switch', ''),
            key('observed', 'router', 'switch', '', '', 'extra'),
            key('manual', ''), key('manual', 'bad/id'), key('manual', 'x' * 65),
            key('manual', ' cable '), key('wan', None), key('wan', True),
            key('manual', {}), key('manual', []), key(['manual'], 'cable'),
            key('observed', 'router', 3, '', ''),
            key('observed', 'router', 'switch', 0, ''),
            key('observed', 'router', 'switch', '', 'p' * 33),
            key('observed', 'router', 'switch', '\n', ''),
            4,
        ]
        cases = [None, [], 'routes', {key('manual', str(i)): [] for i in range(129)}]
        cases += [{bad: []} for bad in invalid_keys]
        cases += [{valid_key: bad} for bad in (None, {}, 'points', [{'x': 1, 'y': 2}] * 9)]
        cases += [{valid_key: [point]} for point in (
            None, [], [1, 2], {'x': 1}, {'x': 1, 'y': 2, 'z': 3},
        )]
        for coordinate in (float('nan'), float('inf'), -float('inf'), True, False,
                           -1, 32769, '1', None, [], {}, 10 ** 1000):
            for axis in ('x', 'y'):
                cases.append({valid_key: [dict(x=1, y=2) | {axis: coordinate}]})
        for bad in cases:
            with self.subTest(routes=bad), self.assertRaises(ValueError):
                topology.validate(graph() | {'routes': bad})


if __name__ == '__main__':
    unittest.main()
