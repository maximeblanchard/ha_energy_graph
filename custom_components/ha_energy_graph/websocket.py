"""Points de terminaison WebSocket pour la carte Lovelace interactive."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, OTHER_COLOR, OTHER_LABEL
from .page import area_payload

_LOGGER = logging.getLogger(__name__)

MOIS_FR = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


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

    slices.sort(key=lambda s: s["wh"], reverse=True)

    total = sum(s["wh"] for s in slices)
    for s in slices:
        s["percent"] = round(s["wh"] / total * 100, 2) if total > 0 else 0.0

    pt = data.get("period_type", "day")
    start = dt_util.as_local(data["start"])
    end = dt_util.as_local(data["end"])
    grand_kwh = data.get("grand_wh", 0.0) / 1000

    if pt == "day":
        title = f"Énergie du {start.day} {MOIS_FR[start.month]} {start.year} — {grand_kwh:.2f} kWh"
        if data.get("is_today", True):
            title += f" à {end:%H}h{end:%M}"
    elif pt == "7d":
        ed = data.get("end_date") or end.date()
        title = f"Énergie du {start.day} {MOIS_FR[start.month]} au {ed.day} {MOIS_FR[ed.month]} {ed.year} (7 jours) — {grand_kwh:.2f} kWh"
    elif pt == "month":
        title = f"Énergie de {MOIS_FR[start.month]} {start.year} — {grand_kwh:.2f} kWh"
    elif pt == "year":
        title = f"Énergie de l'année {start.year} — {grand_kwh:.2f} kWh"
    elif pt == "custom":
        ed = data.get("end_date") or end.date()
        title = f"Énergie du {start.day}/{start.month}/{start.year} au {ed.day}/{ed.month}/{ed.year} — {grand_kwh:.2f} kWh"
    else:
        title = f"Énergie — {grand_kwh:.2f} kWh"

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
        vol.Optional("period"): str,
        vol.Optional("date"): str,
        vol.Optional("end"): str,
        vol.Optional("month"): str,
        vol.Optional("year"): vol.Any(int, str),
        vol.Optional("start"): str,
    }
)
@websocket_api.async_response
async def ws_get_energy_data(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Renvoie les données calculées du graphique d'énergie pour une date ou période donnée."""
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
    period = msg.get("period") or "day"
    if period not in ("day", "7d", "month", "year", "custom"):
        period = "day"

    if period == "7d":
        end_parsed = dt_util.parse_date(msg.get("end", "") or msg.get("date", ""))
        end_val = end_parsed if end_parsed and end_parsed <= today else today
        data = await coordinator.async_compute_period("7d", end_date=end_val)

    elif period == "month":
        m_str = str(msg.get("month", "") or msg.get("date", ""))
        try:
            if len(m_str) >= 7 and m_str[:4].isdigit() and m_str[5:7].isdigit():
                m_date = date(int(m_str[:4]), int(m_str[5:7]), 1)
            else:
                p = dt_util.parse_date(m_str)
                m_date = date(p.year, p.month, 1) if p else date(today.year, today.month, 1)
        except Exception:
            m_date = date(today.year, today.month, 1)
        if m_date > date(today.year, today.month, 1):
            m_date = date(today.year, today.month, 1)
        data = await coordinator.async_compute_period("month", target_date=m_date)

    elif period == "year":
        y_val = msg.get("year")
        try:
            year_num = int(y_val) if y_val else today.year
        except Exception:
            year_num = today.year
        if year_num > today.year:
            year_num = today.year
        data = await coordinator.async_compute_period("year", target_date=date(year_num, 1, 1))

    elif period == "custom":
        s_date = dt_util.parse_date(msg.get("start", "")) or (today - timedelta(days=6))
        e_date = dt_util.parse_date(msg.get("end", "")) or today
        if s_date > e_date:
            s_date, e_date = e_date, s_date
        if e_date > today:
            e_date = today
        data = await coordinator.async_compute_period("custom", start_date=s_date, end_date=e_date)

    else:  # "day"
        date_str = msg.get("date")
        day = dt_util.parse_date(date_str) if date_str else today
        if day is None or day > today:
            day = today
        is_today = (day == today)
        data = (
            coordinator.data
            if is_today and coordinator.data
            else await coordinator.async_compute_period("day", target_date=day)
        )

    entries = [
        {"entry_id": eid, "title": coord.config_entry.title}
        for eid, coord in coordinators.items()
    ]

    result = {
        "entry_id": coordinator.config_entry.entry_id,
        "title": coordinator.config_entry.title,
        "period": period,
        "date": (data.get("day") or today).isoformat(),
        "start_date": data.get("start_date", today).isoformat(),
        "end_date": data.get("end_date", today).isoformat(),
        "today": today.isoformat(),
        "is_today": data.get("is_today", False),
        "is_current": data.get("is_current", False),
        "bucket_labels": data.get("bucket_labels", []),
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
