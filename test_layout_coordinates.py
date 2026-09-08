"""Large saved layouts must not be limited to the original viewport."""
import tempfile
import unittest
from dashboard.topology import TopologyStore
from test_topology import graph


class LayoutCoordinates(unittest.TestCase):
    def test_large_coordinates_round_trip(self):
        value = graph()
        value['nodes'][0].update(x=2400, y=32768)
        with tempfile.TemporaryDirectory() as directory:
            store = TopologyStore(directory)
            saved = store.save(value)
            self.assertEqual(store.read()['nodes'], value['nodes'])
            self.assertEqual(saved['nodes'][0]['y'], 32768)

    def test_coordinates_remain_bounded_and_finite(self):
        for coordinate in (-1, 32769, True, float('nan'), float('inf')):
            with self.subTest(coordinate=coordinate), tempfile.TemporaryDirectory() as directory:
                value = graph()
                value['nodes'][0]['y'] = coordinate
                with self.assertRaises(ValueError):
                    TopologyStore(directory).save(value)
