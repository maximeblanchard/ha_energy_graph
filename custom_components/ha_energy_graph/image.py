"""Entités image (SVG) : drop-in pour remplacer les caméras MQTT."""
from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .charts import render_area, render_pie
from .const import CONF_IMAGE_GROUP, CONF_IMAGE_SCALE, DEFAULT_IMAGE_SCALE, DOMAIN
from .coordinator import EnergyCoordinator
from .views import view_path


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            EnergyChartImage(coordinator, entry, "pie", "Camembert", render_pie),
            EnergyChartImage(coordinator, entry, "area", "Aires empilées", render_area),
        ]
    )


class EnergyChartImage(CoordinatorEntity[EnergyCoordinator], ImageEntity):
    _attr_has_entity_name = True
    _attr_content_type = "image/svg+xml"

    def __init__(self, coordinator, entry, key, name, renderer) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._renderer = renderer
        self._key = key
        self._options = entry.options
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_img_{key}"
        self._attr_name = name
        self._attr_image_last_updated = dt_util.now()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_image_last_updated = dt_util.now()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if not self.coordinator.data:
            return None
        kwargs: dict[str, Any] = {}
        if self._key == "area":
            kwargs = {
                "scale": self._options.get(CONF_IMAGE_SCALE, DEFAULT_IMAGE_SCALE),
                "group": bool(self._options.get(CONF_IMAGE_GROUP, False)),
            }
        return self._renderer(self.coordinator.data, inline=False, **kwargs).encode("utf-8")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"url_interactive": view_path(self._entry_id, self.coordinator.token)}
