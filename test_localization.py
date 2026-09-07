import importlib.util
import unittest


class LocaleTests(unittest.TestCase):
    def test_catalog_parity_fallback_and_bilingual_charts(self):
        self.assertIsNotNone(
            importlib.util.find_spec("localization"), "localization missing"
        )
        from localization import CATALOG, translate
        from reports import render_report

        self.assertEqual(set(CATALOG["ru"]), set(CATALOG["en"]))
        self.assertEqual(translate("unknown", "help"), translate("ru", "help"))
        r = {
            "day": "2026-09-06",
            "devices": {},
            "covered_seconds": 0,
            "expected_seconds": 86400,
            "complete": False,
            "issues": ["counter reset"],
        }
        for lang, word in [("ru", "Неполное"), ("en", "Incomplete")]:
            png, caption = render_report(r, lang)
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertIn(word, caption)
        self.assertNotIn("counter reset", render_report(r, "ru")[1])


if __name__ == "__main__":
    unittest.main()
