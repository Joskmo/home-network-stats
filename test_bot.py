"""All counter fixtures are SYNTHETIC, not captured router/user data.
Schema follows jow-/nlbwmon client.c handle_json().
"""

import importlib.util
import unittest


class ParserTests(unittest.TestCase):
    def test_upstream_columns_data_and_reordered_columns(self):
        self.assertIsNotNone(
            importlib.util.find_spec("nlbw"), "parser module not implemented"
        )
        import nlbw as b

        sample = {
            "columns": ["tx_bytes", "mac", "rx_bytes", "ip"],
            "data": [
                [5, "AA:BB:CC:DD:EE:01", 10, "192.0.2.1"],
                [7, "aa:bb:cc:dd:ee:01", 20, "2001:db8::1"],
            ],
        }
        self.assertEqual(b.parse_nlbw(sample), {"aa:bb:cc:dd:ee:01": (30, 12)})
        self.assertEqual(
            b.parse_nlbw({"columns": ["mac", "rx_bytes", "tx_bytes"], "data": []}), {}
        )
        for bad in [
            {},
            {"columns": ["mac", "rx_bytes", "tx_bytes"], "data": [["x", -1, 2]]},
            {"columns": ["mac", "rx_bytes", "tx_bytes"], "data": [["x", True, 2]]},
            {"columns": ["mac", "rx_bytes", "tx_bytes"], "data": [["x", 1]]},
        ]:
            with self.assertRaises(ValueError):
                b.parse_nlbw(bad)


if __name__ == "__main__":
    unittest.main()
