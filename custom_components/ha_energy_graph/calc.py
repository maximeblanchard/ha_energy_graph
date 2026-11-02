"""Calculs purs (sans dépendance Home Assistant) : lissage, catégorie « Autre »."""
from __future__ import annotations

import math
from typing import Any


def ts_of(value: Any) -> float:
    return value if isinstance(value, (int, float)) else value.timestamp()


def series_from_rows(
    rows: list[dict] | None, key: str, base_ts: float, n: int, bucket_s: int, scale: float = 1.0
) -> list[float]:
    """Place les lignes de statistiques dans un tableau de n tranches commençant à base_ts."""
    arr = [0.0] * n
    for row in rows or []:
        val = row.get(key)
        if val is None:
            continue
        i = int((ts_of(row["start"]) - base_ts) // bucket_s)
        if 0 <= i < n:
            arr[i] += val * scale
    return arr


def despike(
    arr: list[float],
    max_gap: int,
    min_spread: int = 1,
    standby: float = 0.0,
    floor: int = 0,
) -> list[float]:
    """Corrige la quantification d'un compteur (0 -> 0,02 kWh -> 0 -> 0,02 kWh ...).

    Un compteur ne s'incrémente que par paliers : l'énergie d'un palier a été consommée
    avant qu'il n'apparaisse, jamais après. On la répartit donc vers l'arrière :
    - palier <= standby (Wh, inclus) : c'est de la veille ou le seuil du capteur, pas un
      événement. Étalé depuis le palier précédent, ou depuis `floor` (minuit) s'il n'y en a pas ;
    - sinon, sur l'écart depuis le palier précédent si celui-ci est <= max_gap ;
    - sinon (palier isolé), sur les min_spread tranches qui précèdent.
    L'énergie totale est conservée.
    """
    out = [0.0] * len(arr)
    prev: int | None = None
    for i, v in enumerate(arr):
        if v <= 0:
            continue
        lo = floor if i >= floor else 0
        if standby > 0 and v <= standby * 1.001 + 1e-6:
            first = max(prev + 1 if prev is not None else lo, lo)
        elif prev is None or i - prev > max_gap:
            first = i - max(1, min_spread) + 1
        else:
            first = prev + 1
        first = min(max(first, 0), i)
        share = v / (i - first + 1)
        for j in range(first, i + 1):
            out[j] += share
        prev = i
    return out


def compute_other(
    total: list[float], devices: list[list[float]], net_wh: float
) -> list[float]:
    """Série « Autre » : total - appareils, lissée, jamais négative, recalée sur net_wh.

    Le recalage garantit que l'énergie « Autre » des aires est identique à celle du camembert
    (sans lui, écrêter chaque tranche à 0 gonflerait « Autre »).
    """
    n = len(total)
    diff = [total[i] - sum(s[i] for s in devices) for i in range(n)]
    sm: list[float] = []
    for i in range(n):
        lo, hi = max(0, i - 1), min(n, i + 2)
        sm.append(sum(diff[lo:hi]) / (hi - lo))
    clipped = [max(x, 0.0) for x in sm]
    raw = sum(clipped)
    if raw <= 0 or net_wh <= 0:
        return [0.0] * n
    f = net_wh / raw
    return [x * f for x in clipped]


def smooth(arr: list[float], hw: int) -> list[float]:
    """Moyenne glissante triangulaire de demi-largeur hw (conserve l'énergie, bords renormalisés)."""
    n = len(arr)
    if hw <= 0 or n < 2:
        return list(arr)
    out: list[float] = []
    for i in range(n):
        num = den = 0.0
        for k in range(-hw, hw + 1):
            j = i + k
            if 0 <= j < n:
                w = hw + 1 - abs(k)
                num += w * arr[j]
                den += w
        out.append(num / den)
    return out


def monotone_samples(
    xs: list[float], ys: list[float], sub: int
) -> tuple[list[float], list[float]]:
    """Échantillonne une interpolation cubique monotone (Fritsch-Carlson), sans dépassement."""
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    d = [
        (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] != xs[i] else 0.0
        for i in range(n - 1)
    ]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / math.sqrt(s)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    ox: list[float] = []
    oy: list[float] = []
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        for j in range(sub):
            t = j / sub
            t2, t3 = t * t, t * t * t
            y = (
                (2 * t3 - 3 * t2 + 1) * ys[i]
                + (t3 - 2 * t2 + t) * h * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1]
                + (t3 - t2) * h * m[i + 1]
            )
            ox.append(xs[i] + t * h)
            oy.append(max(0.0, y))
    ox.append(xs[-1])
    oy.append(ys[-1])
    return ox, oy


def on_series(
    changes: list[tuple[float, str]] | list[tuple[float, str, float]],
    watts: float,
    start_ts: float,
    end_ts: float,
    n: int,
    bucket_s: int,
) -> list[float]:
    """Wh par tranche d'une lumière qui consomme `watts` (à 100 %) tant que son état vaut "on".

    changes : [(horodatage, état, facteur_puissance)] triés ; chaque état vaut jusqu'au changement suivant
    (le dernier jusqu'à end_ts). "unavailable"/"unknown" comptent comme éteint.
    """
    out = [0.0] * n
    for k, item in enumerate(changes):
        if len(item) == 3:
            t, st, factor = item
        else:
            t, st = item
            factor = 1.0
        if st != "on" or factor <= 0:
            continue
        t0 = max(t, start_ts)
        t1 = min(changes[k + 1][0] if k + 1 < len(changes) else end_ts, end_ts)
        if t1 <= t0:
            continue
        i0 = max(int((t0 - start_ts) // bucket_s), 0)
        i1 = min(int((t1 - start_ts - 1e-9) // bucket_s), n - 1)
        eff_watts = watts * factor
        for i in range(i0, i1 + 1):
            b0 = start_ts + i * bucket_s
            ov = min(t1, b0 + bucket_s) - max(t0, b0)
            if ov > 0:
                out[i] += eff_watts * ov / 3600
    return out
