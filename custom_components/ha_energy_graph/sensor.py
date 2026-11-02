"""Capteurs : énergie du jour par appareil, total, et "Autre"."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergyCoordinator
from .views import view_path


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [TotalSensor(coordinator, entry)]
    for dev in coordinator.data["devices"]:
        entities.append(DeviceSensor(coordinator, entry, dev["id"], dev["name"]))
    if entry.options.get("total_entity"):
        entities.append(OtherSensor(coordinator, entry))
    async_add_entities(entities)


class _Base(CoordinatorEntity[EnergyCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: EnergyCoordinator, entry: ConfigEntry, key: str, name: str):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )


class TotalSensor(_Base):
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "total", "Total aujourd'hui")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data["grand_wh"] / 1000, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "somme_appareils_superieure_au_total": self.coordinator.data["error"],
            "url_interactive": view_path(self._entry.entry_id, self.coordinator.token),
        }


class DeviceSensor(_Base):
    def __init__(self, coordinator, entry, dev_id: str, name: str) -> None:
        super().__init__(coordinator, entry, dev_id, f"{name} aujourd'hui")
        self._dev_id = dev_id

    @property
    def native_value(self) -> float | None:
        for d in self.coordinator.data["devices"]:
            if d["id"] == self._dev_id:
                return round(d["wh"] / 1000, 3)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for d in self.coordinator.data["devices"]:
            if d["id"] == self._dev_id:
                attrs = {"categorie": d["category"], "couleur": d["color"], "type": d["kind"]}
                if d.get("parts"):
                    attrs["detail_kwh"] = {p["name"]: round(p["wh"] / 1000, 3) for p in d["parts"]}
                return attrs
        return {}


class OtherSensor(_Base):
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "other", "Autre aujourd'hui")

    @property
    def native_value(self) -> float | None:
        other = self.coordinator.data["other"]
        return None if other is None else round(other["wh"] / 1000, 3)
