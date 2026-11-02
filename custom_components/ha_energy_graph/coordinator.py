"""Calcul de la consommation d'une journée à partir des statistiques du recorder."""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
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

from .calc import compute_other, despike, on_series, series_from_rows
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


class EnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Énergie (Wh) par appareil et par tranche de temps pour une journée donnée."""

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
        opts = self.config_entry.options
        devices_cfg: list[dict] = opts.get(CONF_DEVICES, [])
        total_id: str | None = opts.get(CONF_TOTAL_ENTITY)
        smooth_h = float(opts.get(CONF_SMOOTH_HOURS, DEFAULT_SMOOTH_HOURS))
        spread_min = float(opts.get(CONF_SPREAD_MIN, DEFAULT_SPREAD_MIN))
        standby_wh = float(opts.get(CONF_STANDBY_WH, DEFAULT_STANDBY_WH))

        now = dt_util.now()
        today = now.date()
        if day is None or day > today:
            day = today
        start = dt_util.start_of_local_day(day)
        next_start = dt_util.start_of_local_day(day + timedelta(days=1))
        start_ts = start.timestamp()
        day_seconds = int(next_start.timestamp() - start_ts)
        is_today = day == today

        bucket_s = BUCKET_SECONDS if (now.timestamp() - start_ts) < SHORT_TERM_DAYS * 86400 else 3600
        period = "5minute" if bucket_s == BUCKET_SECONDS else "hour"
        end_ts = min(math.floor(now.timestamp() / bucket_s) * bucket_s, next_start.timestamp())
        n = max(int((end_ts - start_ts) // bucket_s), 0)
        end = dt_util.utc_from_timestamp(end_ts)

        # Contexte lu avant minuit : permet de répartir les paliers des compteurs quantifiés.
        max_gap = int(smooth_h * 3600 // bucket_s)
        min_spread = max(1, int(spread_min * 60 // bucket_s))
        lead = max(max_gap, min_spread - 1) if max_gap > 0 else 0
        base_ts = start_ts - lead * bucket_s
        nn = n + lead
        fetch_start = dt_util.as_utc(start) - timedelta(seconds=lead * bucket_s)

        energy_ids = {d[CONF_ENTITY_ID] for d in devices_cfg if d[CONF_KIND] == KIND_ENERGY}
        power_ids = {d[CONF_ENTITY_ID] for d in devices_cfg if d[CONF_KIND] == KIND_POWER}
        if total_id:
            energy_ids.add(total_id)

        stats_e: dict[str, list[dict]] = {}
        stats_p: dict[str, list[dict]] = {}
        light_cfg = [d for d in devices_cfg if d[CONF_KIND] == KIND_LIGHT]
        hist: dict[str, list[Any]] = {}
        if n > 0:
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
                if light_cfg:
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
            raw = series_from_rows(stats_e.get(sid), "change", base_ts, nn, bucket_s)
            return (despike(raw, max_gap, min_spread, standby_wh, lead) if max_gap > 0 else raw)[lead:]

        def lights() -> tuple[list[float], list[dict[str, Any]]]:
            """Toutes les ampoules additionnées (watts x temps allumé), avec le détail par lumière."""
            total = [0.0] * n
            parts: list[dict[str, Any]] = []
            for d in light_cfg:
                changes = sorted(
                    (
                        (_state_ts(s), s.state, _brightness_factor(s))
                        for s in hist.get(d[CONF_ENTITY_ID], [])
                    ),
                    key=lambda x: x[0],
                )
                ser = on_series(changes, float(d[CONF_WATTS]), start_ts, end_ts, n, bucket_s)
                parts.append({"name": d[CONF_NAME], "wh": sum(ser)})
                for i, v in enumerate(ser):
                    total[i] += v
            return total, parts

        # appareils, triés par catégorie (ordre d'empilement) puis ordre d'ajout ;
        # toutes les lumières forment un seul appareil « Ampoules »
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
        for d in cfg_sorted:
            kind = d[CONF_KIND]
            parts: list[dict[str, Any]] | None = None
            if kind == KIND_ENERGY:
                series = energy_series(d[CONF_ENTITY_ID])
            elif kind == KIND_POWER:
                series = series_from_rows(
                    stats_p.get(d[CONF_ENTITY_ID]), "mean", base_ts, nn, bucket_s, bucket_s / 3600
                )[lead:]
            elif kind == KIND_LIGHT:
                series, parts = lights()
            else:  # KIND_FIXED : Wh/jour lissés sur 24 h
                series = [d[CONF_WH_PER_DAY] * bucket_s / day_seconds] * n
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
            error = sum_wh > total_wh * 1.02 + 1  # total < somme : pas de catégorie "Autre"
            if not error:
                net = max(total_wh - sum_wh, 0.0)
                other = {
                    "series": compute_other(total_series, [d["series"] for d in devices], net),
                    "wh": net,
                }

        grand_wh = total_wh if (total_id and not error) else sum_wh
        return {
            "start": start,
            "end": end,
            "day": day,
            "is_today": is_today,
            "day_seconds": day_seconds,
            "bucket_s": bucket_s,
            "n": n,
            "devices": devices,
            "other": other,
            "total_wh": total_wh,
            "grand_wh": grand_wh,
            "error": error,
        }
