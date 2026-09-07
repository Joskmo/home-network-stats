"""Headless pie charts of measured per-device RX+TX deltas."""

from io import BytesIO

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from history import TrafficReport
from localization import translate


def render_report(report: TrafficReport, language: str = "ru") -> tuple[bytes, str]:
    def text(key, **values):
        return translate(language, key, **values)

    items = sorted(report["devices"].items(), key=lambda item: item[1], reverse=True)
    if len(items) > 12:
        items = items[:11] + [(text("other"), sum(v for _, v in items[11:]))]
    figure = plt.figure(figsize=(12, 7), facecolor="#f8fafc")
    axis = figure.add_axes((0.035, 0.08, 0.52, 0.67))
    legend_axis = figure.add_axes((0.58, 0.08, 0.39, 0.67))
    legend_axis.axis("off")
    total = sum(value for _, value in items)
    if items and total > 0:
        palette = plt.get_cmap("tab20")
        colors = [
            palette(index * 2 if index < 10 else (index - 10) * 2 + 1)
            for index in range(len(items))
        ]
        wedges, _ = axis.pie(
            [value for _, value in items],
            colors=colors,
            startangle=90,
            counterclock=False,
            wedgeprops={"edgecolor": "#f8fafc", "linewidth": 2},
        )
        # Full identifiers remain readable; no overlapping wedge labels.
        names = report.get("device_names", {})
        labels = [
            f"{names.get(device, device)}\n{value / 1048576:,.2f} MiB  ·  {value / total:.1%}"
            for device, value in items
        ]
        legend_axis.legend(
            wedges,
            labels,
            loc="lower right",
            bbox_to_anchor=(1, 0),
            frameon=False,
            fontsize=11 if len(items) <= 8 else 9,
            labelspacing=1.15,
            handlelength=1.2,
            handleheight=1.2,
            borderaxespad=0,
        )
    else:
        axis.text(
            0.5, 0.5, text("empty"), ha="center", va="center", transform=axis.transAxes
        )
        axis.axis("off")
    figure.suptitle(
        text("title", day=report["day"]),
        x=0.06,
        y=0.95,
        ha="left",
        fontsize=21,
        fontweight="bold",
        color="#0f172a",
    )
    figure.text(
        0.06,
        0.80,
        text("complete" if report["complete"] else "incomplete"),
        fontsize=12,
        color="#64748b",
    )
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=140)
    plt.close(figure)
    caption = text(
        "caption",
        day=report["day"],
        total=sum(report["devices"].values()) / 1048576,
        count=len(report["devices"]),
        state=text("complete" if report["complete"] else "incomplete"),
        covered=report["covered_seconds"] / 3600,
        expected=report["expected_seconds"] / 3600,
        issues=", ".join(text(issue) for issue in report["issues"]) or text("none"),
    )
    return buffer.getvalue(), caption[:1024]
