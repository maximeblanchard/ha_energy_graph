"""Rendu SVG (sans dépendance) du camembert et du graphique en aires empilées."""
from __future__ import annotations

import colorsys
import math
from datetime import timedelta
from html import escape
from typing import Any

from homeassistant.util import dt as dt_util

from .calc import monotone_samples, smooth
from .const import CATEGORIES, OTHER_COLOR, OTHER_LABEL

STYLE = """<style>
.t{fill:var(--c-text,#222);font-family:Arial,Helvetica,sans-serif}
.s{stroke:var(--c-bg,#fff);stroke-width:1.5;transition:opacity .15s}
.s:hover{opacity:.78;stroke-width:3}
.g{stroke:var(--c-grid,#ddd);stroke-width:1}
.a{stroke:var(--c-bg,#fff);stroke-width:.6}
.a:hover{opacity:.8}
.h{fill:transparent}
.h:hover{fill:rgba(128,128,128,.22)}
</style>"""


# Luminosités en dents de scie : deux appareils consécutifs d'une même catégorie sont toujours bien contrastés
_LIGHT_STEPS = (0.32, 0.64, 0.45, 0.74, 0.38, 0.58)


def category_color(category: str, index: int, count: int) -> str:
    """Couleur d'un appareil : une famille de teinte par catégorie, avec un net écart entre voisins.

    Dans une catégorie, la teinte se décale légèrement et la luminosité alterne (dents de scie),
    ce qui évite les dégradés quasi identiques d'une part à l'autre du camembert.
    """
    _, hue, sat = CATEGORIES.get(category, CATEGORIES["divers"])
    if count <= 1:
        h, light = float(hue), 0.50
    else:
        spread = min(14.0 * (count - 1), 40.0)  # étendue totale de teinte autour de la catégorie (°)
        h = hue + spread * (index / (count - 1) - 0.5)
        light = _LIGHT_STEPS[index % len(_LIGHT_STEPS)]
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, light, sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _open(w: float, h: float, inline: bool) -> str:
    if inline:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
            f'style="width:100%;height:auto;max-width:{w:.0f}px">'
        )
    else:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.0f} {h:.0f}"><rect width="{w:.0f}" height="{h:.0f}" fill="#fff"/>'
        )
    return head + STYLE


def _legend(
    items: list[tuple[str, str]], width: float, y0: float, font: int = 20
) -> tuple[str, float]:
    """Légende centrée sur plusieurs lignes. Retourne (svg, y du bas)."""
    rows: list[list[tuple[str, str, float]]] = [[]]
    widths = [0.0]
    for label, color in items:
        w = font + 14 + len(label) * font * 0.56 + 22
        if rows[-1] and widths[-1] + w > width - 40:
            rows.append([])
            widths.append(0.0)
        rows[-1].append((label, color, w))
        widths[-1] += w
    out: list[str] = []
    y = y0
    for row, total in zip(rows, widths):
        x = (width - total) / 2
        for label, color, w in row:
            out.append(
                f'<rect x="{x:.0f}" y="{y - font + 4:.0f}" width="{font + 4}" '
                f'height="{font}" fill="{color}"/>'
            )
            out.append(
                f'<text class="t" x="{x + font + 10:.0f}" y="{y:.0f}" '
                f'font-size="{font}">{escape(label)}</text>'
            )
            x += w
        y += font + 14
    return "".join(out), y


def _title(data: dict[str, Any]) -> str:
    end = dt_util.as_local(data["end"])
    start = dt_util.as_local(data["start"])
    text = (
        f"Energie du {start.day} / {start.month} / {start.year} "
        f"consommation totale : {data['grand_wh'] / 1000:.2f} kWh"
    )
    if data.get("is_today", True):
        text += f" à {end:%H}h{end:%M}"
    return text


def _slices(data: dict[str, Any]) -> list[tuple[str, float, str]]:
    sl = [(d["name"], d["wh"], d["color"]) for d in data["devices"] if d["wh"] > 0]
    other = data.get("other")
    if other and other["wh"] > 0:
        sl.append((OTHER_LABEL, other["wh"], OTHER_COLOR))
    sl.sort(key=lambda s: s[1], reverse=True)
    return sl


def render_pie(data: dict[str, Any], inline: bool = False) -> str:
    """Camembert de la consommation du jour."""
    width = 1000
    slices = _slices(data)
    total = sum(s[1] for s in slices)
    legend_items = [
        (f"{n} {wh / total * 100:.2f}%" if total else n, c) for n, wh, c in slices
    ]
    legend, y = _legend(legend_items, width, 85)
    radius = 330
    cx = width / 2
    cy = y + radius + 30
    height = cy + radius + 50
    parts = [
        _open(width, height, inline),
        f'<text class="t" x="{cx:.0f}" y="40" font-size="26" font-weight="bold" '
        f'text-anchor="middle">{escape(_title(data))}</text>',
        legend,
    ]
    if total <= 0:
        parts.append(
            f'<text class="t" x="{cx:.0f}" y="{cy:.0f}" font-size="26" '
            'text-anchor="middle">Pas encore de données</text>'
        )
        parts.append("</svg>")
        return "".join(parts)

    angle = -math.pi / 2
    last_label_y: dict[str, float] = {}
    labels: list[str] = []
    for name, wh, color in slices:
        frac = wh / total
        tip = f"{escape(name)} : {wh / 1000:.2f} kWh ({frac * 100:.2f} %)"
        if frac >= 0.9999:
            parts.append(
                f'<circle class="s" cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" '
                f'fill="{color}"><title>{tip}</title></circle>'
            )
        else:
            a1 = angle + frac * 2 * math.pi
            x0 = cx + radius * math.cos(angle)
            y0 = cy + radius * math.sin(angle)
            x1 = cx + radius * math.cos(a1)
            y1 = cy + radius * math.sin(a1)
            large = 1 if a1 - angle > math.pi else 0
            parts.append(
                f'<path class="s" d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f} '
                f'A{radius},{radius} 0 {large} 1 {x1:.1f},{y1:.1f} Z" '
                f'fill="{color}"><title>{tip}</title></path>'
            )
        mid = angle + frac * math.pi
        side = "r" if math.cos(mid) >= 0 else "l"
        lx = cx + (radius + 14) * math.cos(mid)
        ly = cy + (radius + 14) * math.sin(mid) + 7
        if side not in last_label_y or abs(ly - last_label_y[side]) >= 24:
            anchor = "start" if side == "r" else "end"
            labels.append(
                f'<text class="t" x="{lx:.1f}" y="{ly:.1f}" font-size="20" '
                f'text-anchor="{anchor}" pointer-events="none">{wh / 1000:.2f} kWh</text>'
            )
            last_label_y[side] = ly
        angle += frac * 2 * math.pi
    parts.extend(labels)
    parts.append("</svg>")
    return "".join(parts)


def _nice_scale(maxv: float) -> tuple[float, float]:
    """(sommet, pas) d'axe : pas rond, au plus ~6 graduations."""
    if maxv <= 0:
        return 100.0, 20.0
    exp = 10 ** math.floor(math.log10(maxv))
    for m in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10):
        step = m * exp
        if maxv / step <= 6:
            return math.ceil(maxv / step - 1e-9) * step, step
    return 10 * exp, 2 * exp


def render_area(
    data: dict[str, Any], inline: bool = False, scale: str = "sqrt", group: bool = False
) -> str:
    """Aires empilées lissées de la puissance moyenne au fil de la journée (image du jour)."""
    width = 1100
    n: int = data["n"]
    bucket_s: int = data.get("bucket_s", 300)
    day_s: int = data.get("day_seconds", 86400)
    layers: list[tuple[str, str, list[float]]] = []
    if group:  # une couche par catégorie : moins de couches, plus lisible
        acc: dict[str, list[float]] = {}
        for d in data["devices"]:
            cur = acc.setdefault(d["category"], [0.0] * n)
            for i, v in enumerate(d["series"]):
                cur[i] += v
        layers = [
            (CATEGORIES.get(cat, CATEGORIES["divers"])[0], category_color(cat, 0, 1), ser)
            for cat, ser in acc.items()
        ]
    else:
        layers = [(d["name"], d["color"], d["series"]) for d in data["devices"]]
    if data.get("other"):
        layers.append((OTHER_LABEL, OTHER_COLOR, data["other"]["series"]))
    layers = [layer for layer in layers if sum(layer[2]) > 0]

    start = dt_util.as_local(data["start"])
    title = f"Puissance moyenne — {start.day}/{start.month}/{start.year}"
    legend, y = _legend([(name, color) for name, color, _ in layers], width, 85, 17)
    ml, mr, mb, ph = 80, 25, 55, 380
    mt = y + 10
    pw = width - ml - mr
    height = mt + ph + mb
    parts = [
        _open(width, height, inline),
        f'<text class="t" x="{width / 2:.0f}" y="36" font-size="24" font-weight="bold" '
        f'text-anchor="middle">{escape(title)}</text>',
        legend,
    ]
    if n <= 0 or not layers:
        parts.append(
            f'<text class="t" x="{width / 2:.0f}" y="{mt + ph / 2:.0f}" font-size="24" '
            'text-anchor="middle">Pas encore de données</text></svg>'
        )
        return "".join(parts)

    k = 3600 / bucket_s
    hw = 2 if bucket_s <= 300 else 0  # lissage léger (~10 min) puis interpolation monotone
    xs = [0.0, float(bucket_s)] if n == 1 else [(i + 0.5) * bucket_s for i in range(n)]
    samples: list[list[float]] = []
    sx: list[float] = xs
    for _, _, ser in layers:
        w = smooth([v * k for v in ser], hw)
        if n == 1:
            w = [w[0], w[0]]
        sx, sy = monotone_samples(xs, w, 2)
        samples.append(sy)
    npts = len(sx)
    cums: list[list[float]] = [[0.0] * npts]
    for sy in samples:
        prev = cums[-1]
        cums.append([prev[j] + sy[j] for j in range(npts)])

    top, step = _nice_scale(max(cums[-1]) * 1.03)

    def px(t: float) -> float:
        return ml + t / day_s * pw

    sqrt_scale = scale == "sqrt"

    def py(v: float) -> float:
        f = max(v, 0.0) / top
        return mt + ph - (math.sqrt(f) if sqrt_scale else f) * ph

    if sqrt_scale:
        ticks = [0.0]
        e = 1.0
        while e <= top:
            ticks += [m * e for m in (1, 2, 5) if m * e <= top]
            e *= 10
        kept: list[float] = []
        last_y = 1e9
        for tv in ticks:
            if tv == 0 or last_y - py(tv) >= 22:
                kept.append(tv)
                last_y = py(tv)
        ticks = kept
    else:
        ticks = []
        v = 0.0
        while v <= top + 1e-9:
            ticks.append(v)
            v += step
    for v in ticks:
        parts.append(
            f'<line class="g" x1="{ml}" x2="{ml + pw}" y1="{py(v):.1f}" y2="{py(v):.1f}"/>'
        )
        parts.append(
            f'<text class="t" x="{ml - 8}" y="{py(v) + 5:.1f}" font-size="15" '
            f'text-anchor="end">{v:g} W</text>'
        )
    if sqrt_scale:
        parts.append(
            f'<text class="t" x="{width - mr}" y="{mt + ph + 46}" font-size="14" '
            'font-style="italic" text-anchor="end" opacity="0.7">'
            "Échelle compressée (√) : les faibles consommations sont agrandies</text>"
        )
    for h in range(0, day_s // 3600 + 1, 3):
        parts.append(
            f'<text class="t" x="{px(h * 3600):.1f}" y="{mt + ph + 24}" font-size="15" '
            f'text-anchor="middle">{h} h</text>'
        )

    for li, (name, color, _) in enumerate(layers):
        if max(samples[li]) < 0.5:
            continue
        up = [f"{px(sx[j]):.1f},{py(cums[li + 1][j]):.1f}" for j in range(npts)]
        dn = [f"{px(sx[j]):.1f},{py(cums[li][j]):.1f}" for j in range(npts - 1, -1, -1)]
        parts.append(
            f'<path class="a" d="M{"L".join(up + dn)}Z" fill="{color}" fill-opacity="0.93"/>'
        )
    parts.append("</svg>")
    return "".join(parts)
