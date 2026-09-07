import { $ } from "../shared/dom";
import type { Language, Stats } from "../shared/contracts";
function canvasContext(): CanvasRenderingContext2D {
  const ctx = $("pie").getContext("2d");
  if (!ctx) throw new Error("Canvas 2D unavailable");
  return ctx;
}

export function createStatsRenderer(
  t: (key: string) => string,
  getLanguage: () => Language,
) {
  const locale = () => (getLanguage() === "ru" ? "ru-RU" : "en-GB");
  const date = (stamp: number | null) =>
    stamp
      ? new Date(stamp * 1000).toLocaleString(locale(), {
          timeZone: "Europe/Moscow",
          dateStyle: "medium",
          timeStyle: "short",
        })
      : t("waiting");
  function size(bytes: number) {
    let value = bytes,
      unit = 0;
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    while (value >= 1024 && unit < 4) {
      value /= 1024;
      unit++;
    }
    return (
      value.toLocaleString(locale(), { maximumFractionDigits: unit ? 2 : 0 }) +
      " " +
      units[unit]
    );
  }
  function number(id: string, value: string, unit: string) {
    const el = $(id);
    el.replaceChildren(document.createTextNode(value + " "));
    const small = document.createElement("small");
    small.textContent = unit;
    el.append(small);
  }
  function render(data: Stats) {
    const s = data.speed,
      m = data.monthly;
    number(
      "download",
      s.download_bps === null
        ? "—"
        : (s.download_bps / 1e6).toLocaleString(locale(), {
            maximumFractionDigits: 2,
          }),
      getLanguage() === "ru" ? "Мбит/с" : "Mbps",
    );
    number(
      "upload",
      s.upload_bps === null
        ? "—"
        : (s.upload_bps / 1e6).toLocaleString(locale(), {
            maximumFractionDigits: 2,
          }),
      getLanguage() === "ru" ? "Мбит/с" : "Mbps",
    );
    $("live-state").textContent = t(s.stale ? "stale" : "live");
    $("live-state").classList.toggle("amber", s.stale);
    $("total").textContent = m.available ? size(m.total_bytes) : "—";
    $("month-label").textContent =
      m.month + " · " + t(m.partial ? "partial" : "complete");
    $("partial").textContent = t(m.partial ? "partial" : "complete");
    $("coverage").textContent =
      t("since") +
      ": " +
      date(m.collection_started) +
      " · " +
      t("covered") +
      ": " +
      (m.covered_seconds / 3600).toLocaleString(locale(), {
        maximumFractionDigits: 2,
      }) +
      " " +
      t("hours");
    $("updated").textContent = t("updated") + " " + date(data.generated_at);
    const colors = [
      "#c5f27e",
      "#80b9f1",
      "#c19af3",
      "#f1bc7d",
      "#7ee0ca",
      "#f392a9",
      "#8797e5",
      "#d0ca8e",
      "#71b6bc",
      "#acafba",
    ];
    const entries = m.devices.slice(0, 9).map((x) => ({ ...x }));
    if (m.devices.length > 9)
      entries.push({
        name: t("other"),
        bytes: m.devices.slice(9).reduce((a, b) => a + b.bytes, 0),
      });
    const ctx = canvasContext();
    ctx.clearRect(0, 0, 600, 600);
    let start = -Math.PI / 2;
    $("empty").hidden = m.available && m.total_bytes > 0;
    $("legend").replaceChildren();
    entries.forEach((entry, i) => {
      const angle = (entry.bytes / m.total_bytes) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(300, 300);
      ctx.arc(300, 300, 260, start, start + angle);
      ctx.closePath();
      ctx.fillStyle = colors[i];
      ctx.fill();
      ctx.strokeStyle = "#151e25";
      ctx.lineWidth = 6;
      ctx.stroke();
      start += angle;
    });
    // Every device remains in the accessible table even when small slices are grouped.
    m.devices.forEach((entry, i) => {
      const tr = document.createElement("tr");
      const label = document.createElement("td");
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.backgroundColor = colors[Math.min(i, 9)];
      label.title = entry.mac || "";
      label.append(swatch, document.createTextNode(entry.name || t("unnamed")));
      tr.append(label);
      [
        size(entry.bytes),
        ((entry.bytes / m.total_bytes) * 100).toLocaleString(locale(), {
          maximumFractionDigits: 1,
        }) + "%",
      ].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.append(td);
      });
      $("legend").append(tr);
    });
  }
  return {
    render,
    number,
    clearChart: () => canvasContext().clearRect(0, 0, 600, 600),
  };
}
