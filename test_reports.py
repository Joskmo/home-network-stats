import importlib.util
import unittest


class ReportTests(unittest.TestCase):
    def test_pie_uses_bottom_right_legend_without_wedge_labels(self):
        from unittest.mock import patch

        from matplotlib.axes import Axes

        from reports import render_report

        report = {
            "day": "2026-09-07",
            "devices": {"device A": 1024, "device B": 2048},
            "covered_seconds": 300,
            "expected_seconds": 3600,
            "complete": False,
            "issues": [],
        }
        original_pie = Axes.pie
        original_legend = Axes.legend
        pie_calls = []
        legend_calls = []

        def pie(axis, *args, **kwargs):
            pie_calls.append(kwargs)
            return original_pie(axis, *args, **kwargs)

        def legend(axis, *args, **kwargs):
            legend_calls.append(kwargs)
            return original_legend(axis, *args, **kwargs)

        with patch.object(Axes, "pie", pie), patch.object(Axes, "legend", legend):
            for language in ("ru", "en"):
                render_report(report, language)
        self.assertEqual(len(legend_calls), 2)
        self.assertTrue(all(call.get("loc") == "lower right" for call in legend_calls))
        self.assertTrue(
            all(
                not call.get("labels") and not call.get("autopct") for call in pie_calls
            )
        )

    def test_empty_and_real_delta_pie_render_png_with_honest_caption(self):
        self.assertIsNotNone(
            importlib.util.find_spec("reports"), "reports not implemented"
        )
        from reports import render_report

        r = {
            "day": "2026-09-06",
            "devices": {},
            "covered_seconds": 0,
            "expected_seconds": 86400,
            "complete": False,
            "issues": ["initial baseline"],
        }
        png, caption = render_report(r)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn("Неполное", caption)
        self.assertIn("0.0", caption)
        r["devices"] = {"aa:bb:cc:dd:ee:01": 1024, "aa:bb:cc:dd:ee:02": 2048}
        png, caption = render_report(r)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn("RX + TX", caption)
        self.assertLessEqual(len(caption), 1024)


if __name__ == "__main__":
    unittest.main()
