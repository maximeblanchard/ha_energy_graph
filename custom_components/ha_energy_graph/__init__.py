"""Intégration Energy Breakdown : camembert + aires empilées de la conso du jour."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EnergyCoordinator
from .views import EnergyChartView
from .websocket import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.IMAGE]
CARD_URL = "/ha_energy_graph_card.js"
FRONTEND_FILE = Path(__file__).parent / "frontend" / "ha-energy-graph-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.http.register_view(EnergyChartView(hass))
    async_register_websocket_commands(hass)

    if FRONTEND_FILE.is_file():
        if hasattr(hass.http, "async_register_static_paths"):
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL, str(FRONTEND_FILE), cache_headers=False)]
            )
        else:
            hass.http.register_static_path(CARD_URL, str(FRONTEND_FILE), cache_headers=False)

        add_extra_js_url(hass, f"{CARD_URL}?v=1.8.0")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_schedule()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
