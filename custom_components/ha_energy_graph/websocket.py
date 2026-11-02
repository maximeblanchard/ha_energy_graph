"""Points de terminaison WebSocket pour la carte Lovelace interactive."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, OTHER_COLOR, OTHER_LABEL
from .page import area_payload

_LOGGER = logging.getLogger(__name__)


def pie_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Construit la structure de données pour le camembert."""
    devices = data.get("devices", [])
    slices: list[dict[str, Any]] = [
        {"name": d["name"], "wh": round(d["wh"], 1), "color": d["color"]}
        for d in devices
        if d.get("wh", 0) > 0
    ]
    other = data.get("other")
    if other and other.get("wh", 0) > 0:
        slices.append({"name": OTHER_LABEL, "wh": round(other["wh"], 1), "color": OTHER_COLOR})

    total = sum(s["wh"] for s in slices)
    for s in slices:
        s["percent"] = round(s["wh"] / total * 100, 2) if total > 0 else 0.0

    start = dt_util.as_local(data["start"])
    end = dt_util.as_local(data["end"])
    title = f"Énergie du {start.day} / {start.month} / {start.year} — {data.get('grand_wh', 0.0) / 1000:.2f} kWh"
    if data.get("is_today", True):
        title += f" à {end:%H}h{end:%M}"

    return {
        "title": title,
        "grand_wh": data.get("grand_wh", 0.0),
        "total_wh": data.get("total_wh", 0.0),
        "total": total,
        "slices": slices,
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_energy_graph/data",
        vol.Optional("entry_id"): str,
        vol.Optional("date"): str,
    }
)
@websocket_api.async_response
async def ws_get_energy_data(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Renvoie les données calculées du graphique d'énergie pour une date donnée."""
    coordinators = hass.data.get(DOMAIN, {})
    if not coordinators:
        connection.send_error(
            msg["id"], "not_found", "Aucune intégration Graphique d'énergie configurée."
        )
        return

    entry_id = msg.get("entry_id")
    if entry_id and entry_id in coordinators:
        coordinator = coordinators[entry_id]
    else:
        coordinator = next(iter(coordinators.values()))

    today = dt_util.now().date()
    date_str = msg.get("date")
    day = dt_util.parse_date(date_str) if date_str else today
    if day is None or day > today:
        day = today

    is_today = day == today
    data = (
        coordinator.data
        if is_today and coordinator.data
        else await coordinator.async_compute_day(day)
    )

    entries = [
        {"entry_id": eid, "title": coord.config_entry.title}
        for eid, coord in coordinators.items()
    ]

    result = {
        "entry_id": coordinator.config_entry.entry_id,
        "title": coordinator.config_entry.title,
        "date": day.isoformat(),
        "today": today.isoformat(),
        "is_today": is_today,
        "error": data.get("error", False),
        "area": area_payload(data),
        "pie": pie_payload(data),
        "entries": entries,
    }
    connection.send_result(msg["id"], result)


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Enregistre la commande WebSocket."""
    websocket_api.async_register_command(hass, ws_get_energy_data)
