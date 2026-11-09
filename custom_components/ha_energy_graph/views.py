"""Page web interactive (infobulles, zoom, navigation par date)."""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .page import build_page


def view_path(entry_id: str, token: str) -> str:
    return f"/api/{DOMAIN}/{entry_id}/{token}"


class EnergyChartView(HomeAssistantView):
    """GET /api/ha_energy_graph/<entry_id>/<token>?v=pie|area|both&p=day|7d|month|year|custom

    L'accès est protégé par le token secret de l'entrée (utilisable dans une carte iframe).
    """

    url = "/api/" + DOMAIN + "/{entry_id}/{token}"
    name = "api:ha_energy_graph:chart"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str, token: str) -> web.Response:
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None or not secrets.compare_digest(token, coordinator.token):
            raise web.HTTPNotFound

        view = request.query.get("v", "both")
        if view not in ("pie", "area", "both"):
            view = "both"

        period = request.query.get("p") or request.query.get("period") or "day"
        if period not in ("day", "7d", "month", "year", "custom"):
            period = "day"

        today = dt_util.now().date()

        if period == "7d":
            end_parsed = dt_util.parse_date(request.query.get("end", "") or request.query.get("date", ""))
            end_val = end_parsed if end_parsed and end_parsed <= today else today
            data = await coordinator.async_compute_period("7d", end_date=end_val)
            day = end_val
        elif period == "month":
            m_str = str(request.query.get("month", "") or request.query.get("date", ""))
            try:
                if len(m_str) >= 7 and m_str[:4].isdigit() and m_str[5:7].isdigit():
                    m_date = date(int(m_str[:4]), int(m_str[5:7]), 1)
                else:
                    p = dt_util.parse_date(m_str)
                    m_date = date(p.year, p.month, 1) if p else date(today.year, today.month, 1)
            except Exception:
                m_date = date(today.year, today.month, 1)
            data = await coordinator.async_compute_period("month", target_date=m_date)
            day = m_date
        elif period == "year":
            y_val = request.query.get("year")
            try:
                year_num = int(y_val) if y_val else today.year
            except Exception:
                year_num = today.year
            data = await coordinator.async_compute_period("year", target_date=date(year_num, 1, 1))
            day = date(year_num, 1, 1)
        elif period == "custom":
            s_date = dt_util.parse_date(request.query.get("start", "")) or (today - timedelta(days=6))
            e_date = dt_util.parse_date(request.query.get("end", "")) or today
            data = await coordinator.async_compute_period("custom", start_date=s_date, end_date=e_date)
            day = e_date
        else:
            day = dt_util.parse_date(request.query.get("date", "")) or today
            if day > today:
                day = today
            data = coordinator.data if day == today and coordinator.data else await coordinator.async_compute_period("day", target_date=day)

        page = build_page(data, view, day, today, coordinator.config_entry.title)
        return web.Response(
            text=page,
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )
