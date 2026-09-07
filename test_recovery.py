"""Recovery deployment regression checks; no production authentication state."""
import unittest
from pathlib import Path

class RouterWrapperTests(unittest.TestCase):
    def test_neighbor_command_preserves_interface_and_exact_allowlist(self):
        source=(Path(__file__).parent/'deploy/home-network-read').read_text()
        self.assertIn("'/usr/libexec/home-network-read neighbors') set -- neighbors ;;",source)
        self.assertIn('exec ip -4 neigh show',source)
        self.assertNotIn('ip -4 neigh show dev br-lan',source)
