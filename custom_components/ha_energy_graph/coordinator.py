"""Calcul de la consommation d'une période à partir des statistiques du recorder."""
from __future__ import annotations

import calendar
import logging
import math
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .calc import compute_other, despike, on_series, series_from_rows, ts_of
from .charts import category_color
from .const import (
    BUCKET_SECONDS,
    CATEGORIES,
    CONF_CATEGORY,
    CONF_DEVICES,
    CONF_ID,
    CONF_KIND,
    CONF_SMOOTH_HOURS,
    CONF_SPREAD_MIN,
    CONF_STANDBY_WH,
    CONF_TOKEN,
    CONF_TOTAL_ENTITY,
    CONF_UPDATE_MINUTES,
    CONF_WATTS,
    CONF_WH_PER_DAY,
    DEFAULT_SMOOTH_HOURS,
    DEFAULT_SPREAD_MIN,
    DEFAULT_STANDBY_WH,
    DEFAULT_UPDATE_MINUTES,
    DOMAIN,
    KIND_ENERGY,
    KIND_LIGHT,
    KIND_POWER,
    LIGHTS_ID,
    LIGHTS_NAME,
)

_LOGGER = logging.getLogger(__name__)

# Au-delà, le recorder n'a plus de statistiques 5 min : on passe en pas horaire.
SHORT_TERM_DAYS = 9
# Le recorder compile ses statistiques toutes les 5 min (à hh:mm:10). On lit juste après.
REFRESH_SECOND = 40
ALLOWED_STEPS = (5, 10, 15, 20, 30, 60)


def _state_ts(state: Any) -> float:
    ts = getattr(state, "last_updated_timestamp", None)
    return ts if ts is not None else state.last_updated.timestamp()


def _brightness_factor(state: Any) -> float:
    """Fraction de puissance selon la luminosité (1.0 si non précisée ou 100 %)."""
    attrs = getattr(state, "attributes", None) or {}
    b = attrs.get("brightness")
    if b is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(b) / 255.0))
    except (ValueError, TypeError):
        return 1.0


def _series_months(
    rows: list[dict] | None, key: str, year: int, scale: float = 1.0
) -> list[float]:
    arr = [0.0] * 12
    for row in rows or []:
        val = row.get(key)
        if val is None:
            continue
        ts_val = ts_of(row["start"])
        row_dt = dt_util.as_local(dt_util.utc_from_timestamp(ts_val))
        if row_dt.year == year:
            m = row_dt.month - 1
            if 0 <= m < 12:
                arr[m] += val * scale
    return arr


class EnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Énergie (Wh) par appareil et par tranche de temps pour une période donnée."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=None,  # rafraîchissement calé sur le recorder, voir async_schedule
        )
        self.token: str = entry.data[CONF_TOKEN]

    def async_schedule(self) -> None:
        """Rafraîchit juste après chaque compilation de statistiques (toutes les 5 min par défaut)."""
        minutes = self.config_entry.options.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES)
        step = min(ALLOWED_STEPS, key=lambda s: abs(s - minutes))

        async def _tick(_now) -> None:
            await self.async_refresh()

        self.config_entry.async_on_unload(
            async_track_utc_time_change(
                self.hass, _tick, minute=list(range(0, 60, step)), second=REFRESH_SECOND
            )
        )

    async def _async_update_data(self) -> dict[str, Any]:
        return await self.async_compute_day(None)

    async def async_compute_day(self, day: date | None) -> dict[str, Any]:
        """Calcule la journée `day` (aujourd'hui si None)."""
        return await self.async_compute_period("day", target_date=day)

    async def async_compute_period(
        self,
        period_type: str = "day",
        target_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Calcule la consommation pour différentes périodes (day, 7d, month, year, custom)."""
        opts = self.config_entry.options
        devices_cfg: list[dict] = opts.get(CONF_DEVICES, [])
        total_id: str | None = opts.get(CONF_TOTAL_ENTITY)
        smooth_h = float(opts.get(CONF_SMOOTH_HOURS, DEFAULT_SMOOTH_HOURS))
        spread_min = float(opts.get(CONF_SPREAD_MIN, DEFAULT_SPREAD_MIN))
        standby_wh = float(opts.get(CONF_STANDBY_WH, DEFAULT_STANDBY_WH))

        now = dt_util.now()
        today = now.date()

        day: date | None = None
        end_day: date | None = None
        start: datetime
        next_start: datetime
        bucket_s: int
        period: str
        n: int
        is_current: bool
        bucket_labels: list[str] = []

        if period_type == "7d":
            end_day = end_date or target_date or today
            if end_day > today:
                end_day = today
            start_day = end_day - timedelta(days=6)
            start = dt_util.start_of_local_day(start_day)
            next_start = dt_util.start_of_local_day(end_day + timedelta(days=1))
            start_ts = start.timestamp()
            day_seconds = int(next_start.timestamp() - start_ts)
            is_current = (end_day == today)
            bucket_s = 86400
            period = "hour"
            end_ts = min(now.timestamp(), next_start.timestamp())
            n = 7
            end = dt_util.utc_from_timestamp(end_ts)
            jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
            bucket_labels = [
                f"{jours[(start_day + timedelta(days=i)).weekday()]} {(start_day + timedelta(days=i)).day}/{(start_day + timedelta(days=i)).month}"
                for i in range(7)
            ]

        elif period_type == "month":
            t_date = target_date or today
            if t_date > today:
                t_date = today
            num_days = calendar.monthrange(t_date.year, t_date.month)[1]
            start_day = date(t_date.year, t_date.month, 1)
            end_day = date(t_date.year, t_date.month, num_days)
            start = dt_util.start_of_local_day(start_day)
            next_start = dt_util.start_of_local_day(end_day + timedelta(days=1))
            start_ts = start.timestamp()
            day_seconds = int(next_start.timestamp() - start_ts)
            is_current = (t_date.year == today.year and t_date.month == today.month)
            bucket_s = 86400
            period = "hour"
            end_ts = min(now.timestamp(), next_start.timestamp())
            n = num_days
            end = dt_util.utc_from_timestamp(end_ts)
            bucket_labels = [str(i + 1) for i in range(num_days)]

        elif period_type == "year":
            year = target_date.year if target_date else today.year
            if year > today.year:
                year = today.year
            start = dt_util.start_of_local_day(date(year, 1, 1))
            next_start = dt_util.start_of_local_day(date(year + 1, 1, 1))
            start_ts = start.timestamp()
            day_seconds = int(next_start.timestamp() - start_ts)
            is_current = (year == today.year)
            bucket_s = 0  # ventilation par mois
            period = "hour"
            end_ts = min(now.timestamp(), next_start.timestamp())
            n = 12
            end = dt_util.utc_from_timestamp(end_ts)
            bucket_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]

        elif period_type == "custom":
            s_day = start_date or (today - timedelta(days=7))
            e_day = end_date or today
            if s_day > e_day:
                s_day, e_day = e_day, s_day
            if e_day > today:
                e_day = today
            start_day = s_day
            end_day = e_day
            num_days = (end_day - start_day).days + 1
            start = dt_util.start_of_local_day(start_day)
            next_start = dt_util.start_of_local_day(end_day + timedelta(days=1))
            start_ts = start.timestamp()
            day_seconds = int(next_start.timestamp() - start_ts)
            is_current = (end_day == today)
            bucket_s = 86400
            period = "hour"
            end_ts = min(now.timestamp(), next_start.timestamp())
            n = num_days
            end = dt_util.utc_from_timestamp(end_ts)
            bucket_labels = [
                f"{(start_day + timedelta(days=i)).day}/{(start_day + timedelta(days=i)).month}"
                for i in range(num_days)
            ]

        else:  # "day" (par défaut)
            period_type = "day"
            day = target_date or today
            if day > today:
                day = today
            start = dt_util.start_of_local_day(day)
            next_start = dt_util.start_of_local_day(day + timedelta(days=1))
            start_ts = start.timestamp()
            day_seconds = int(next_start.timestamp() - start_ts)
            is_current = (day == today)
            bucket_s = BUCKET_SECONDS if (now.timestamp() - start_ts) < SHORT_TERM_DAYS * 86400 else 3600
            period = "5minute" if bucket_s == BUCKET_SECONDS else "hour"
            end_ts = min(math.floor(now.timestamp() / bucket_s) * bucket_s, next_start.timestamp())
            n = max(int((end_ts - start_ts) // bucket_s), 0)
            end = dt_util.utc_from_timestamp(end_ts)
            bucket_labels = [f"{h} h" for h in range(24)]

        # Contexte lu avant début : utile pour les paliers des compteurs quantifiés en mode jour
        if period_type == "day":
            max_gap = int(smooth_h * 3600 // bucket_s)
            min_spread = max(1, int(spread_min * 60 // bucket_s))
            lead = max(max_gap, min_spread - 1) if max_gap > 0 else 0
            base_ts = start_ts - lead * bucket_s
            nn = n + lead
            fetch_start = dt_util.as_utc(start) - timedelta(seconds=lead * bucket_s)
        else:
            lead = 0
            base_ts = start_ts
            nn = n
            fetch_start = dt_util.as_utc(start)

        energy_ids = {d[CONF_ENTITY_ID] for d in devices_cfg if d[CONF_KIND] == KIND_ENERGY}
        power_ids = {d[CONF_ENTITY_ID] for d in devices_cfg if d[CONF_KIND] == KIND_POWER}
        if total_id:
            energy_ids.add(total_id)

        stats_e: dict[str, list[dict]] = {}
        stats_p: dict[str, list[dict]] = {}
        light_cfg = [d for d in devices_cfg if d[CONF_KIND] == KIND_LIGHT]
        hist: dict[str, list[Any]] = {}

        if n > 0 and end_ts > start_ts:
            instance = get_instance(self.hass)
            try:
                if energy_ids:
                    stats_e = await instance.async_add_executor_job(
                        statistics_during_period, self.hass, fetch_start, end,
                        energy_ids, period, {"energy": "Wh"}, {"change"},
                    )
                if power_ids:
                    stats_p = await instance.async_add_executor_job(
                        statistics_during_period, self.hass, fetch_start, end,
                        power_ids, period, {"power": "W"}, {"mean"},
                    )
                if light_cfg and (now.timestamp() - start_ts) < 12 * 86400:
                    hist = await instance.async_add_executor_job(
                        partial(
                            get_significant_states,
                            self.hass,
                            dt_util.as_utc(start),
                            end,
                            [d[CONF_ENTITY_ID] for d in light_cfg],
                            include_start_time_state=True,
                            significant_changes_only=False,
                            minimal_response=False,
                            no_attributes=False,
                        )
                    )
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"Lecture des statistiques impossible : {err}") from err

        def energy_series(sid: str) -> list[float]:
            if period_type == "year":
                return _series_months(stats_e.get(sid), "change", target_date.year if target_date else today.year, 1.0)
            elif period_type == "day":
                raw = series_from_rows(stats_e.get(sid), "change", base_ts, nn, bucket_s)
                return (despike(raw, max_gap, min_spread, standby_wh, lead) if max_gap > 0 else raw)[lead:]
            else:
                return series_from_rows(stats_e.get(sid), "change", start_ts, n, bucket_s)

        def lights() -> tuple[list[float], list[dict[str, Any]]]:
            total = [0.0] * n
            parts: list[dict[str, Any]] = []
            if not hist:
                return total, parts
            bs = bucket_s if bucket_s > 0 else 86400
            for d in light_cfg:
                changes = sorted(
                    (
                        (_state_ts(s), s.state, _brightness_factor(s))
                        for s in hist.get(d[CONF_ENTITY_ID], [])
                    ),
                    key=lambda x: x[0],
                )
                ser = on_series(changes, float(d[CONF_WATTS]), start_ts, end_ts, n, bs)
                parts.append({"name": d[CONF_NAME], "wh": sum(ser)})
                for i, v in enumerate(ser):
                    if i < n:
                        total[i] += v
            return total, parts

        cfg_eff = [d for d in devices_cfg if d[CONF_KIND] != KIND_LIGHT]
        if light_cfg:
            cfg_eff.append(
                {
                    CONF_ID: LIGHTS_ID,
                    CONF_NAME: LIGHTS_NAME,
                    CONF_KIND: KIND_LIGHT,
                    CONF_CATEGORY: "eclairage",
                }
            )
        order = list(CATEGORIES)
        cfg_sorted = sorted(
            cfg_eff,
            key=lambda d: order.index(d[CONF_CATEGORY]) if d[CONF_CATEGORY] in order else 99,
        )
        per_cat: dict[str, int] = {}
        for d in cfg_sorted:
            per_cat[d[CONF_CATEGORY]] = per_cat.get(d[CONF_CATEGORY], 0) + 1
        seen: dict[str, int] = {}

        devices: list[dict[str, Any]] = []
        if period_type == "year":
            year_val = target_date.year if target_date else today.year
            for d in cfg_sorted:
                kind = d[CONF_KIND]
                parts = None
                if kind == KIND_ENERGY:
                    series = _series_months(stats_e.get(d[CONF_ENTITY_ID]), "change", year_val, 1.0)
                elif kind == KIND_POWER:
                    series = _series_months(stats_p.get(d[CONF_ENTITY_ID]), "mean", year_val, 1.0)
                elif kind == KIND_LIGHT:
                    series, parts = lights()
                else:  # KIND_FIXED
                    series = [calendar.monthrange(year_val, m + 1)[1] * d[CONF_WH_PER_DAY] for m in range(12)]
                    if is_current:
                        series[today.month - 1] = today.day * d[CONF_WH_PER_DAY]
                        for m in range(today.month, 12):
                            series[m] = 0.0

                cat = d[CONF_CATEGORY]
                idx = seen.get(cat, 0)
                seen[cat] = idx + 1
                devices.append(
                    {
                        "id": d[CONF_ID],
                        "name": d[CONF_NAME],
                        "category": cat,
                        "kind": kind,
                        "color": category_color(cat, idx, per_cat[cat]),
                        "series": series,
                        "wh": sum(series),
                        "parts": parts,
                    }
                )

            sum_wh = sum(d["wh"] for d in devices)
            other = None
            error = False
            total_wh = sum_wh
            if total_id:
                total_series = _series_months(stats_e.get(total_id), "change", year_val, 1.0)
                total_wh = sum(total_series)
                error = sum_wh > total_wh * 1.02 + 1
                if not error:
                    net = max(total_wh - sum_wh, 0.0)
                    other = {
                        "series": compute_other(total_series, [d["series"] for d in devices], net),
                        "wh": net,
                    }

        else:
            power_scale = (bucket_s / 3600) if period_type == "day" and bucket_s == BUCKET_SECONDS else 1.0
            for d in cfg_sorted:
                kind = d[CONF_KIND]
                parts = None
                if kind == KIND_ENERGY:
                    series = energy_series(d[CONF_ENTITY_ID])
                elif kind == KIND_POWER:
                    if period_type == "day":
                        series = series_from_rows(
                            stats_p.get(d[CONF_ENTITY_ID]), "mean", base_ts, nn, bucket_s, power_scale
                        )[lead:]
                    else:
                        series = series_from_rows(
                            stats_p.get(d[CONF_ENTITY_ID]), "mean", start_ts, n, bucket_s, power_scale
                        )
                elif kind == KIND_LIGHT:
                    series, parts = lights()
                else:  # KIND_FIXED
                    if period_type == "day":
                        series = [d[CONF_WH_PER_DAY] * bucket_s / day_seconds] * n
                    else:
                        series = [d[CONF_WH_PER_DAY]] * n
                        if is_current and n > 0:
                            start_of_today_ts = dt_util.start_of_local_day(today).timestamp()
                            frac = min(max((now.timestamp() - start_of_today_ts) / 86400, 0.0), 1.0)
                            series[-1] = d[CONF_WH_PER_DAY] * frac

                cat = d[CONF_CATEGORY]
                idx = seen.get(cat, 0)
                seen[cat] = idx + 1
                devices.append(
                    {
                        "id": d[CONF_ID],
                        "name": d[CONF_NAME],
                        "category": cat,
                        "kind": kind,
                        "color": category_color(cat, idx, per_cat[cat]),
                        "series": series,
                        "wh": sum(series),
                        "parts": parts,
                    }
                )

            sum_wh = sum(d["wh"] for d in devices)
            other = None
            error = False
            total_wh = sum_wh
            if total_id:
                total_series = energy_series(total_id)
                total_wh = sum(total_series)
                error = sum_wh > total_wh * 1.02 + 1
                if not error:
                    net = max(total_wh - sum_wh, 0.0)
                    other = {
                        "series": compute_other(total_series, [d["series"] for d in devices], net),
                        "wh": net,
                    }

        grand_wh = total_wh if (total_id and not error) else sum_wh
        return {
            "period_type": period_type,
            "start": start,
            "end": end,
            "start_date": start.date(),
            "end_date": end_day or (start.date() if period_type == "day" else (date(target_date.year if target_date else today.year, 12, 31) if period_type == "year" else today)),
            "day": day,
            "is_today": (period_type == "day" and is_current),
            "is_current": is_current,
            "day_seconds": day_seconds,
            "bucket_s": bucket_s,
            "n": n,
            "bucket_labels": bucket_labels,
            "devices": devices,
            "other": other,
            "total_wh": total_wh,
            "grand_wh": grand_wh,
            "error": error,
        }
