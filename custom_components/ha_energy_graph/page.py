"""Construction de la page HTML interactive (Python pur, testable sans Home Assistant)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from html import escape
from typing import Any

from .chart_js import CHART_JS
from .charts import category_color, render_pie
from .const import CATEGORIES, OTHER_COLOR, OTHER_LABEL

CSS = """
:root{--c-text:#222;--c-bg:#fff;--c-grid:#ddd;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--c-text:#e8e8e8;--c-bg:#1c1c1c;--c-grid:#444}}
body{margin:0;padding:8px;background:var(--c-bg);color:var(--c-text);font-family:Arial,sans-serif}
svg{display:block}
.pie svg{margin:0 auto 24px}
.nav{display:flex;gap:12px;align-items:center;justify-content:center;margin:4px 0 12px;flex-wrap:wrap}
.nav a,.nav .off{font-size:22px;text-decoration:none;color:var(--c-text);padding:4px 12px;
  border:1px solid var(--c-grid);border-radius:8px}
.nav .off{opacity:.3}
.nav .today{font-size:16px}
.nav input{font-size:18px;padding:4px 8px;border:1px solid var(--c-grid);border-radius:8px;
  background:var(--c-bg);color:var(--c-text)}
.ac{max-width:1100px;margin:0 auto 24px}
.ac h3{text-align:center;margin:8px 0}
.ctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:center;margin:6px 0;font-size:14px}
.ctl button,.ctl select{font-size:14px;padding:4px 10px;border:1px solid var(--c-grid);border-radius:8px;
  background:var(--c-bg);color:var(--c-text);cursor:pointer}
.ctl button.on{background:var(--c-text);color:var(--c-bg)}
.leg{display:flex;flex-wrap:wrap;gap:6px 14px;justify-content:center;margin:6px 0;font-size:14px}
.leg span{cursor:pointer;display:inline-flex;align-items:center;gap:6px;user-select:none}
.leg i{width:14px;height:14px;display:inline-block;border-radius:3px}
.leg .off{opacity:.35;text-decoration:line-through}
.wrap{position:relative}
.tip{position:absolute;top:10px;left:0;pointer-events:none;display:none;background:var(--c-bg);
  color:var(--c-text);border:1px solid var(--c-grid);border-radius:8px;padding:8px 10px;font-size:13px;
  box-shadow:0 2px 8px rgba(0,0,0,.35);z-index:3;min-width:170px}
.tip div{display:flex;justify-content:space-between;gap:14px}
.hint{opacity:.6;font-size:12px;text-align:center;margin-top:4px}
.ax{fill:var(--c-text);font-size:12px;font-family:Arial,sans-serif}
.gl{stroke:var(--c-grid);stroke-width:1}
.sel{fill:rgba(100,150,255,.25);stroke:rgba(100,150,255,.8)}
"""


def area_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Données du graphique en aires / colonnes envoyées au navigateur."""
    bucket_s = data.get("bucket_s", 300)
    k = (3600 / bucket_s) if bucket_s > 0 else 1.0
    layers = [
        {
            "name": d["name"],
            "color": d["color"],
            "cat": d["category"],
            "w": [round(x * k, 1) for x in d["series"]],
            "wh": [round(x, 1) for x in d["series"]],
        }
        for d in data["devices"]
    ]
    if data.get("other"):
        layers.append(
            {
                "name": OTHER_LABEL,
                "color": OTHER_COLOR,
                "cat": "_other",
                "w": [round(x * k, 1) for x in data["other"]["series"]],
                "wh": [round(x, 1) for x in data["other"]["series"]],
            }
        )
    start = data["start"]
    pt = data.get("period_type", "day")
    if pt == "year":
        title = f"Consommation mensuelle — Année {start.year}"
    elif pt == "month":
        title = f"Consommation journalière — {start.month}/{start.year}"
    elif pt == "7d":
        title = "Consommation journalière — 7 derniers jours"
    elif pt == "custom":
        title = "Consommation journalière"
    else:
        title = f"Puissance moyenne — {start.day}/{start.month}/{start.year}"

    return {
        "period_type": pt,
        "bucket_labels": data.get("bucket_labels", []),
        "bucket_s": bucket_s,
        "day_seconds": data.get("day_seconds", 86400),
        "n": data.get("n", 0),
        "title": title,
        "layers": [layer for layer in layers if any(layer["wh"]) or any(layer["w"])],
        "cats": {
            **{
                key: [CATEGORIES[key][0], category_color(key, 0, 1)]
                for key in {d["category"] for d in data["devices"]}
                if key in CATEGORIES
            },
            "_other": [OTHER_LABEL, OTHER_COLOR],
        },
    }


def build_page(
    data: dict[str, Any], view: str, day: date, today: date, title: str
) -> str:
    def link(d: date) -> str:
        return f"?v={view}&amp;date={d.isoformat()}"

    next_html = (
        f'<a href="{link(day + timedelta(days=1))}" title="Jour suivant">&#9654;</a>'
        if day < today
        else '<span class="off">&#9654;</span>'
    )
    today_html = (
        f'<a href="{link(today)}" class="today">Aujourd\'hui</a>' if day < today else ""
    )
    body = ""
    if view in ("pie", "both"):
        body += '<div class="pie">' + render_pie(data, inline=True) + "</div>"
    if view in ("area", "both"):
        payload = json.dumps(area_payload(data), ensure_ascii=False).replace("</", "<\\/")
        body += (
            '<div id="area-root"></div>'
            f"<script>var D={payload};</script><script>{CHART_JS}</script>"
        )
    reload_js = (
        "<script>(function s(){var ms=300000-(Date.now()%300000)+50000;"
        "setTimeout(function(){if(!window.__zoomed){location.reload();}else{s();}},ms);})();</script>"
        if day == today
        else ""
    )
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{CSS}</style></head><body>"
        '<div class="nav">'
        f'<a href="{link(day - timedelta(days=1))}" title="Jour précédent">&#9664;</a>'
        f'<input type="date" value="{day.isoformat()}" max="{today.isoformat()}" '
        f"onchange=\"if(this.value)location.search='?v={view}&amp;date='+this.value\">"
        f"{next_html}{today_html}</div>"
        f"{body}{reload_js}</body></html>"
    )
