"""Build a standalone Plotly dashboard for the anonymized apartment sample."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
from plotly.offline import get_plotlyjs

try:
    from .freshness import age_days, data_as_of
    from .metrics import add_value_score, prepare_dashboard_data
    from .transform import load_dataframe
except ImportError:
    from freshness import age_days, data_as_of
    from metrics import add_value_score, prepare_dashboard_data
    from transform import load_dataframe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "sample.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "dashboard.html"
SOURCE_URL = "https://www.restate.ru"
REPOSITORY_URL = "https://github.com/GavrikovAlex/live_data"
STALE_AFTER_DAYS = 7


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values into JSON-compatible values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def dashboard_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Select only fields approved for the browser-side dashboard payload."""
    fields = (
        "price",
        "price_per_m2",
        "rooms",
        "area_total",
        "area_living",
        "area_kitchen",
        "floor",
        "floors_total",
        "metro",
        "okrug",
        "district",
        "published_at",
        "listing_age_days",
        "value_score",
    )
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        rows.append({field: _json_value(record.get(field)) for field in fields})
    return rows


def _format_money(value: float | None) -> str:
    """Format a ruble value for a dashboard card."""
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн ₽"
    return f"{value:,.0f} ₽".replace(",", " ")


def _format_number(value: float | None, suffix: str = "") -> str:
    """Format a regular numeric card value."""
    if value is None:
        return "—"
    return f"{value:,.1f}{suffix}".replace(",", " ")


def build_dashboard(
    frame: pd.DataFrame,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    """Render the standalone dashboard and return its output path."""
    scored = add_value_score(frame)
    summary = prepare_dashboard_data(scored)
    snapshot_date = data_as_of()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_as_of": snapshot_date,
        "data_age_days": age_days(snapshot_date),
        "metrics": summary["metrics"],
        "rows": dashboard_rows(scored),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    plotly_js = get_plotlyjs()
    template = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Аналитика квартир Москвы</title>
<style>
:root {
  --bg: #f5f7fb;
  --surface: #ffffff;
  --ink: #172033;
  --muted: #6b7890;
  --line: #e5eaf2;
  --accent: #2f6fed;
  --accent-soft: #eaf1ff;
  --green: #159570;
  --shadow: 0 10px 30px rgba(28, 48, 84, .08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.shell { max-width: 1480px; margin: 0 auto; padding: 28px 24px 42px; }
.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}
.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}
h1 { margin: 0; font-size: clamp(28px, 4vw, 46px); letter-spacing: -.04em; }
.subtitle { margin: 10px 0 0; color: var(--muted); font-size: 15px; }
.meta-line { margin: 6px 0 0; color: var(--muted); font-size: 13px; }
.meta-line--stale { color: #b45309; font-weight: 600; }
.source-link { color: var(--accent); font-weight: 700; text-decoration: none; white-space: nowrap; }
.source-link:hover { text-decoration: underline; }
.cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.card, .panel {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow);
}
.card { padding: 18px; min-height: 112px; }
.card-label { color: var(--muted); font-size: 12px; font-weight: 700; line-height: 1.3; }
.card-value { margin-top: 12px; font-size: clamp(22px, 2.3vw, 32px); font-weight: 850; letter-spacing: -.04em; }
.card-note { margin-top: 5px; color: var(--muted); font-size: 11px; }
.filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px;
  margin-bottom: 18px;
}
.filter { min-width: 122px; flex: 1 1 122px; }
.filter.wide { flex: 1.5 1 180px; }
.filter label { display: block; margin-bottom: 6px; color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }
input, select, button {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fbfcff;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  padding: 8px 10px;
}
input:focus, select:focus, button:focus { outline: 3px solid var(--accent-soft); border-color: var(--accent); }
button { min-width: 92px; cursor: pointer; background: var(--accent-soft); color: var(--accent); font-weight: 800; }
button:hover { background: #dce8ff; }
.range { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.panel { min-width: 0; padding: 18px 18px 10px; }
.chart { width: 100%; height: 340px; }
.score-note { margin: 0 0 18px; color: var(--muted); font-size: 13px; }
.footer { display: flex; justify-content: space-between; gap: 18px; margin-top: 24px; color: var(--muted); font-size: 12px; }
.footer a { color: var(--accent); text-decoration: none; }
.footer a:hover { text-decoration: underline; }
.empty { color: var(--muted); font-size: 13px; padding: 20px 0; }
@media (max-width: 1150px) { .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .shell { padding: 20px 14px 30px; }
  .header, .footer { align-items: flex-start; flex-direction: column; }
  .cards, .grid { grid-template-columns: 1fr; }
  .filters { align-items: stretch; }
  .filter, .filter.wide { flex-basis: 100%; }
  .chart { height: 300px; }
}
</style>
</head>
<body>
<main class="shell">
  <header class="header">
    <div>
      <p class="eyebrow">Live market dashboard</p>
      <h1>Аналитика квартир Москвы</h1>
      <p class="subtitle">Срез вторичного рынка: цены, площади, этажность и метро.</p>
      <p class="meta-line__DATA_AS_OF_CLASS__">Данные на __DATA_AS_OF__ · сборка дашборда __GENERATED_AT____FRESHNESS_NOTE__</p>
    </div>
    <a class="source-link" href="__SOURCE_URL__" target="_blank" rel="noreferrer">Источник: restate.ru ↗</a>
  </header>

  <section class="cards" aria-label="Сводные показатели">
    <article class="card"><div class="card-label">Объявлений</div><div class="card-value" id="metric-count">—</div><div class="card-note">в выбранном срезе</div></article>
    <article class="card"><div class="card-label">Средняя цена</div><div class="card-value" id="metric-avg-price">—</div><div class="card-note">за объявление</div></article>
    <article class="card"><div class="card-label">Медиана цены</div><div class="card-value" id="metric-median-price">—</div><div class="card-note">устойчивая середина</div></article>
    <article class="card"><div class="card-label">Средний этаж</div><div class="card-value" id="metric-avg-floor">—</div><div class="card-note">из данных объявлений</div></article>
    <article class="card"><div class="card-label">Средняя площадь</div><div class="card-value" id="metric-avg-area">—</div><div class="card-note">м²</div></article>
    <article class="card"><div class="card-label">Средняя цена/м²</div><div class="card-value" id="metric-avg-meter">—</div><div class="card-note">по всем объектам</div></article>
  </section>

  <section class="filters" aria-label="Фильтры">
    <div class="filter"><label for="rooms-filter">Комнаты</label><select id="rooms-filter"><option value="">Все</option></select></div>
    <div class="filter wide"><label>Цена, млн ₽</label><div class="range"><input id="price-min" type="number" min="0" step="0.5" placeholder="от"><input id="price-max" type="number" min="0" step="0.5" placeholder="до"></div></div>
    <div class="filter wide"><label>Площадь, м²</label><div class="range"><input id="area-min" type="number" min="0" step="1" placeholder="от"><input id="area-max" type="number" min="0" step="1" placeholder="до"></div></div>
    <div class="filter wide"><label>Этаж</label><div class="range"><input id="floor-min" type="number" min="0" step="1" placeholder="от"><input id="floor-max" type="number" min="0" step="1" placeholder="до"></div></div>
    <div class="filter wide"><label for="metro-filter">Метро</label><select id="metro-filter"><option value="">Все</option></select></div>
    <button id="reset-filters" type="button">Сбросить</button>
  </section>

  <p class="score-note">Score выгодности считается как <strong>(средняя цена/м² по метро − цена/м² объекта) / средняя цена/м² по метро × 100%</strong>: выше — выгоднее относительно соседей по метро.</p>

  <section class="grid">
    <article class="panel"><div id="price-chart" class="chart" aria-label="Распределение цен"></div></article>
    <article class="panel"><div id="area-chart" class="chart" aria-label="Цена и площадь"></div></article>
    <article class="panel"><div id="metro-chart" class="chart" aria-label="Топ метро"></div></article>
    <article class="panel"><div id="trend-chart" class="chart" aria-label="Динамика или комнаты"></div></article>
  </section>

  <footer class="footer">
    <span>Данные обезличены. Только открытые источники.</span>
    <a href="__REPOSITORY_URL__" target="_blank" rel="noreferrer">Открыть репозиторий ↗</a>
  </footer>
</main>
<script>__PLOTLY_JS__</script>
<script>
window.__APARTMENTS_DATA__ = __DATA__;
(function () {
  "use strict";
  const payload = window.__APARTMENTS_DATA__;
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  const colors = { ink: "#172033", muted: "#6b7890", line: "#e5eaf2", blue: "#2f6fed", teal: "#159570", orange: "#f28e52", purple: "#8a6ff0" };
  const plotConfig = { displayModeBar: false, responsive: true };
  const plotLayout = (title) => ({
    title: { text: title, x: 0, xanchor: "left", font: { family: "system-ui, sans-serif", size: 16, color: colors.ink } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 48, r: 18, t: 48, b: 48 },
    font: { family: "system-ui, sans-serif", size: 12, color: colors.muted },
    hoverlabel: { bgcolor: "#172033", bordercolor: "#172033", font: { color: "#ffffff", family: "system-ui, sans-serif" } },
    xaxis: { gridcolor: colors.line, zerolinecolor: colors.line, linecolor: colors.line, tickfont: { color: colors.muted }, title: { font: { color: colors.muted } } },
    yaxis: { gridcolor: colors.line, zerolinecolor: colors.line, linecolor: colors.line, tickfont: { color: colors.muted }, title: { font: { color: colors.muted } } },
    showlegend: false
  });
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const numberOr = (value, fallback) => finite(Number(value)) && value !== "" ? Number(value) : fallback;
  const money = (value) => value === null || value === undefined ? "—" : (value >= 1000000 ? `${(value / 1000000).toFixed(1)} млн ₽` : `${Math.round(value).toLocaleString("ru-RU")} ₽`);
  const decimal = (value, digits) => value === null || value === undefined ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: digits });
  const unique = (values) => [...new Set(values.filter((value) => value !== null && value !== undefined && value !== ""))].sort((a, b) => String(a).localeCompare(String(b), "ru"));
  const valuesFor = (key) => rows.map((row) => row[key]).filter(finite);
  const setText = (id, value) => { document.getElementById(id).textContent = value; };
  const mean = (values) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const median = (values) => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  const groupMean = (items, key) => {
    const groups = new Map();
    items.forEach((item) => { const group = item[key] || "Не указан"; const bucket = groups.get(group) || []; bucket.push(item); groups.set(group, bucket); });
    return [...groups.entries()].map(([name, group]) => ({ name, value: mean(group.map((item) => item.price).filter(finite)), count: group.length })).filter((item) => finite(item.value));
  };
  function fillSelect(id, values, formatter) {
    const select = document.getElementById(id);
    select.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());
    values.forEach((value) => { const option = document.createElement("option"); option.value = String(value); option.textContent = formatter ? formatter(value) : String(value); select.appendChild(option); });
  }
  function setupFilters() {
    fillSelect("rooms-filter", unique(valuesFor("rooms")));
    fillSelect("metro-filter", unique(rows.map((row) => row.metro)));
    const prices = valuesFor("price");
    const areas = valuesFor("area_total");
    const floors = valuesFor("floor");
    document.getElementById("price-max").value = prices.length ? Math.ceil(Math.max(...prices) / 1000000) : 100;
    document.getElementById("area-max").value = areas.length ? Math.ceil(Math.max(...areas)) : 100;
    document.getElementById("floor-max").value = floors.length ? Math.ceil(Math.max(...floors)) : 30;
  }
  function filteredRows() {
    const rooms = document.getElementById("rooms-filter").value;
    const metro = document.getElementById("metro-filter").value;
    const priceMin = numberOr(document.getElementById("price-min").value, 0) * 1000000;
    const priceMaxInput = numberOr(document.getElementById("price-max").value, Infinity);
    const priceMax = priceMaxInput === Infinity ? Infinity : priceMaxInput * 1000000;
    const areaMin = numberOr(document.getElementById("area-min").value, 0);
    const areaMax = numberOr(document.getElementById("area-max").value, Infinity);
    const floorMin = numberOr(document.getElementById("floor-min").value, 0);
    const floorMax = numberOr(document.getElementById("floor-max").value, Infinity);
    return rows.filter((row) => {
      const price = Number(row.price);
      const area = Number(row.area_total);
      const floor = Number(row.floor);
      return (!rooms || String(row.rooms) === rooms) && (!metro || row.metro === metro) && (!finite(price) || (price >= priceMin && price <= priceMax)) && (!finite(area) || (area >= areaMin && area <= areaMax)) && (!finite(floor) || (floor >= floorMin && floor <= floorMax));
    });
  }
  function updateCards(items) {
    const prices = items.map((row) => Number(row.price)).filter(finite);
    const floors = items.map((row) => Number(row.floor)).filter(finite);
    const areas = items.map((row) => Number(row.area_total)).filter(finite);
    const meters = items.map((row) => Number(row.price_per_m2)).filter(finite);
    setText("metric-count", items.length.toLocaleString("ru-RU"));
    setText("metric-avg-price", money(mean(prices)));
    setText("metric-median-price", money(median(prices)));
    setText("metric-avg-floor", decimal(mean(floors), 1));
    setText("metric-avg-area", decimal(mean(areas), 1));
    setText("metric-avg-meter", money(mean(meters)));
  }
  function render(items) {
    const prices = items.map((row) => Number(row.price)).filter(finite);
    const points = items.filter((row) => finite(Number(row.price)) && finite(Number(row.area_total)));
    const metro = groupMean(items, "metro").sort((a, b) => b.value - a.value).slice(0, 10);
    Plotly.react("price-chart", [{ type: "histogram", x: prices, xbins: { size: 1000000 }, marker: { color: colors.blue, line: { color: "#ffffff", width: 1 } } }], { ...plotLayout("Распределение цен"), xaxis: { ...plotLayout("Распределение цен").xaxis, title: { text: "Цена, млн ₽" }, tickformat: ".0s" }, yaxis: { ...plotLayout("Распределение цен").yaxis, title: { text: "Объявлений" } } }, plotConfig);
    Plotly.react("area-chart", [{ type: "scatter", mode: "markers", x: points.map((row) => Number(row.area_total)), y: points.map((row) => Number(row.price)), marker: { color: points.map((row) => Number(row.value_score)), colorscale: [[0, colors.orange], [0.5, colors.blue], [1, colors.teal]], size: 9, opacity: .78, colorbar: { title: { text: "score" } } }, customdata: points.map((row) => [row.metro || "Метро не указан", row.okrug || "Округ не указан", Number(row.value_score || 0)]), hovertemplate: "%{customdata[0]}<br>%{customdata[1]}<br>Площадь: %{x:.1f} м²<br>Цена: %{y:,.0f} ₽<br>Score: %{customdata[2]:.1f}%<extra></extra>" }], { ...plotLayout("Цена vs площадь"), xaxis: { ...plotLayout("Цена vs площадь").xaxis, title: { text: "Площадь, м²" } }, yaxis: { ...plotLayout("Цена vs площадь").yaxis, title: { text: "Цена, ₽" }, tickformat: ".0s" } }, plotConfig);
    Plotly.react("metro-chart", [{ type: "bar", x: metro.map((row) => row.name), y: metro.map((row) => row.value), marker: { color: colors.purple, cornerradius: 5 }, customdata: metro.map((row) => row.count), hovertemplate: "%{x}<br>Средняя цена: %{y:,.0f} ₽<br>Объявлений: %{customdata}<extra></extra>" }], { ...plotLayout("Топ-10 метро по средней цене"), xaxis: { ...plotLayout("Топ-10 метро по средней цене").xaxis, type: "category", tickangle: -35 }, yaxis: { ...plotLayout("Топ-10 метро по средней цене").yaxis, title: { text: "Средняя цена, ₽" }, tickformat: ".0s" } }, plotConfig);
    const months = new Map();
    items.forEach((row) => { if (!row.published_at) return; const month = String(row.published_at).slice(0, 7); const bucket = months.get(month) || []; bucket.push(Number(row.price)); months.set(month, bucket); });
    const monthRows = [...months.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([month, values]) => ({ month, value: mean(values.filter(finite)), count: values.length })).filter((row) => finite(row.value));
    if (monthRows.length >= 2) {
      Plotly.react("trend-chart", [{ type: "scatter", mode: "lines+markers", x: monthRows.map((row) => row.month), y: monthRows.map((row) => row.value), line: { color: colors.teal, width: 3 }, marker: { size: 8 }, customdata: monthRows.map((row) => row.count), hovertemplate: "%{x}<br>Средняя цена: %{y:,.0f} ₽<br>Объявлений: %{customdata}<extra></extra>" }], { ...plotLayout("Динамика по месяцам"), xaxis: { ...plotLayout("Динамика по месяцам").xaxis, type: "category" }, yaxis: { ...plotLayout("Динамика по месяцам").yaxis, title: { text: "Средняя цена, ₽" }, tickformat: ".0s" } }, plotConfig);
    } else {
      const roomCounts = new Map();
      items.forEach((row) => { if (row.rooms === null || row.rooms === undefined) return; roomCounts.set(String(row.rooms), (roomCounts.get(String(row.rooms)) || 0) + 1); });
      const roomRows = [...roomCounts.entries()].sort((a, b) => Number(a[0]) - Number(b[0]));
      Plotly.react("trend-chart", [{ type: "bar", x: roomRows.map((row) => row[0]), y: roomRows.map((row) => row[1]), marker: { color: colors.orange, cornerradius: 5 }, hovertemplate: "%{x} комнат<br>Объявлений: %{y}<extra></extra>" }], { ...plotLayout("Распределение по комнатам"), xaxis: { ...plotLayout("Распределение по комнатам").xaxis, type: "category", title: { text: "Комнаты" } }, yaxis: { ...plotLayout("Распределение по комнатам").yaxis, title: { text: "Объявлений" } } }, plotConfig);
    }
  }
  function update() { const items = filteredRows(); updateCards(items); render(items); }
  function reset() { ["rooms-filter", "metro-filter", "price-min", "area-min", "floor-min"].forEach((id) => { document.getElementById(id).value = ""; }); setupFilters(); update(); }
  setupFilters();
  ["rooms-filter", "metro-filter", "price-min", "price-max", "area-min", "area-max", "floor-min", "floor-max"].forEach((id) => document.getElementById(id).addEventListener("input", update));
  document.getElementById("reset-filters").addEventListener("click", reset);
  update();
}());
</script>
</body>
</html>
"""
    snapshot_age = payload["data_age_days"]
    stale = snapshot_age is not None and snapshot_age > STALE_AFTER_DAYS
    freshness_note = (
        f" · ⚠ данные устарели ({snapshot_age} дн.)" if stale else ""
    )
    html = (
        template.replace("__SOURCE_URL__", escape(SOURCE_URL, quote=True))
        .replace("__REPOSITORY_URL__", escape(REPOSITORY_URL, quote=True))
        .replace("__PLOTLY_JS__", plotly_js.replace("</", "<\\/"))
        .replace("__DATA__", payload_json)
        .replace("__GENERATED_AT__", payload["generated_at"])
        .replace("__DATA_AS_OF__", snapshot_date or "неизвестно")
        .replace("__DATA_AS_OF_CLASS__", " meta-line--stale" if stale else "")
        .replace("__FRESHNESS_NOTE__", freshness_note)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    """Parse local dashboard build options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    """Build the dashboard from a local JSON input."""
    args = parse_args()
    frame = load_dataframe(args.input)
    output_path = build_dashboard(frame, args.output)
    print(f"Saved dashboard to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
