"""Intégration Energy Breakdown : camembert + aires empilées de la conso du jour."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, HomeAssistant

from .const import DOMAIN
from .coordinator import EnergyCoordinator
from .views import EnergyChartView
from .websocket import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.IMAGE]
CARD_URL = "/ha_energy_graph_card.js"
FRONTEND_FILE = Path(__file__).parent / "frontend" / "ha-energy-graph-card.js"


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Enregistre automatiquement la ressource Lovelace si en mode storage."""
    lovelace = hass.data.get("lovelace")
    if not lovelace or not hasattr(lovelace, "resources"):
        return
    try:
        if not lovelace.resources.loaded:
            await lovelace.resources.async_load()
        url = f"{CARD_URL}?v=1.8.0"
        for resource in lovelace.resources.async_items():
            if resource.get("url", "").startswith(CARD_URL):
                if resource.get("url") != url:
                    await lovelace.resources.async_update_item(
                        resource["id"], {"res_type": "module", "url": url}
                    )
                return
        await lovelace.resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Ressource Lovelace enregistrée automatiquement : %s", url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Impossible d'enregistrer la ressource Lovelace : %s", err)


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

        async def _register_fe(_event=None) -> None:
            await _async_register_lovelace_resource(hass)

        if hass.state == CoreState.running:
            hass.async_create_task(_register_fe())
        else:
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_fe)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_schedule()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    hass.async_create_task(_async_register_lovelace_resource(hass))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
