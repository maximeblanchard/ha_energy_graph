"""Page web interactive (infobulles, zoom, navigation par date)."""
from __future__ import annotations

import secrets

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .page import build_page


def view_path(entry_id: str, token: str) -> str:
    return f"/api/{DOMAIN}/{entry_id}/{token}"


class EnergyChartView(HomeAssistantView):
    """GET /api/ha_energy_graph/<entry_id>/<token>?v=pie|area|both&date=AAAA-MM-JJ

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
        today = dt_util.now().date()
        day = dt_util.parse_date(request.query.get("date", "")) or today
        if day > today:
            day = today

        data = coordinator.data if day == today else await coordinator.async_compute_day(day)
        page = build_page(data, view, day, today, coordinator.config_entry.title)
        return web.Response(
            text=page,
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )
