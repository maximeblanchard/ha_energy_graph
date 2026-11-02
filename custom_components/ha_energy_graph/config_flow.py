"""Config flow + options flow : même menu d'ajout d'appareils dans les deux."""
from __future__ import annotations

import secrets
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CATEGORIES,
    CONF_CATEGORY,
    CONF_DEVICES,
    CONF_ID,
    CONF_KIND,
    CONF_IMAGE_GROUP,
    CONF_IMAGE_SCALE,
    CONF_REMOVE,
    CONF_SMOOTH_HOURS,
    CONF_SPREAD_MIN,
    CONF_WATTS,
    CONF_STANDBY_WH,
    CONF_TOKEN,
    CONF_TOTAL_ENTITY,
    CONF_UPDATE_MINUTES,
    CONF_WH_PER_DAY,
    DEFAULT_IMAGE_SCALE,
    DEFAULT_SMOOTH_HOURS,
    DEFAULT_SPREAD_MIN,
    DEFAULT_STANDBY_WH,
    DEFAULT_UPDATE_MINUTES,
    DOMAIN,
    KIND_ENERGY,
    KIND_FIXED,
    KIND_LIGHT,
    KIND_POWER,
)

KIND_LABELS = {"energy": "énergie", "power": "puissance", "fixed": "fixe", "light": "lumière"}

ENERGY_FILTER = [{"domain": "sensor", "device_class": "energy"}]
POWER_FILTER = [{"domain": "sensor", "device_class": "power"}]


def _category_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=list(CATEGORIES),
            translation_key="category",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class _DeviceMenuMixin:
    """Menu d'ajout / suppression d'appareils, partagé par le config flow et l'options flow."""

    def _load(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._load()
        return self.async_show_menu(  # type: ignore[attr-defined]
            step_id="init",
            menu_options=[
                "add_energy",
                "add_power",
                "add_fixed",
                "add_light",
                "remove_device",
                "settings",
                "finish",
            ],
        )

    async def _add_sensor(
        self, step_id: str, kind: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        data = self._load()
        errors: dict[str, str] = {}
        if user_input is not None:
            eid = user_input[CONF_ENTITY_ID]
            state = self.hass.states.get(eid)  # type: ignore[attr-defined]
            if state is None:
                errors["base"] = "entity_not_found"
            elif any(d.get(CONF_ENTITY_ID) == eid for d in data[CONF_DEVICES]):
                errors["base"] = "already_configured"
            else:
                state_class = state.attributes.get("state_class")
                ok = (
                    state_class in ("total", "total_increasing")
                    if kind == KIND_ENERGY
                    else state_class == "measurement"
                )
                if not ok:
                    errors["base"] = (
                        "bad_state_class_energy" if kind == KIND_ENERGY else "bad_state_class_power"
                    )
                else:
                    data[CONF_DEVICES].append(
                        {
                            CONF_ID: uuid.uuid4().hex[:8],
                            CONF_NAME: user_input.get(CONF_NAME) or state.name,
                            CONF_KIND: kind,
                            CONF_ENTITY_ID: eid,
                            CONF_CATEGORY: user_input[CONF_CATEGORY],
                        }
                    )
                    return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID): EntitySelector(
                    EntitySelectorConfig(
                        filter=ENERGY_FILTER if kind == KIND_ENERGY else POWER_FILTER
                    )
                ),
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_CATEGORY, default="divers"): _category_selector(),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, user_input),  # type: ignore[attr-defined]
            errors=errors,
        )

    async def async_step_add_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Compteur d'énergie : cumulatif (Zigbee) ou remis à zéro chaque jour (Tapo)."""
        return await self._add_sensor("add_energy", KIND_ENERGY, user_input)

    async def async_step_add_power(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._add_sensor("add_power", KIND_POWER, user_input)

    async def async_step_add_fixed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        data = self._load()
        if user_input is not None:
            data[CONF_DEVICES].append(
                {
                    CONF_ID: uuid.uuid4().hex[:8],
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_KIND: KIND_FIXED,
                    CONF_WH_PER_DAY: float(user_input[CONF_WH_PER_DAY]),
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                }
            )
            return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_WH_PER_DAY, default=100): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=100000,
                        step=0.1,
                        unit_of_measurement="Wh",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_CATEGORY, default="divers"): _category_selector(),
            }
        )
        return self.async_show_form(step_id="add_fixed", data_schema=schema)  # type: ignore[attr-defined]

    async def async_step_add_light(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Lumières : on compte une puissance fixe (W à 100 %) modulée selon la luminosité."""
        data = self._load()
        errors: dict[str, str] = {}
        if user_input is not None:
            known = {d.get(CONF_ENTITY_ID) for d in data[CONF_DEVICES]}
            new = [e for e in user_input[CONF_ENTITY_ID] if e not in known]
            if not new:
                errors["base"] = "already_configured"
            else:
                for eid in new:
                    state = self.hass.states.get(eid)  # type: ignore[attr-defined]
                    data[CONF_DEVICES].append(
                        {
                            CONF_ID: uuid.uuid4().hex[:8],
                            CONF_NAME: state.name if state else eid,
                            CONF_KIND: KIND_LIGHT,
                            CONF_ENTITY_ID: eid,
                            CONF_WATTS: float(user_input[CONF_WATTS]),
                            CONF_CATEGORY: "eclairage",
                        }
                    )
                return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID): EntitySelector(
                    EntitySelectorConfig(domain="light", multiple=True)
                ),
                vol.Required(CONF_WATTS, default=9): NumberSelector(
                    NumberSelectorConfig(
                        min=0.1,
                        max=2000,
                        step=0.1,
                        unit_of_measurement="W",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="add_light",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),  # type: ignore[attr-defined]
            errors=errors,
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        data = self._load()
        if not data[CONF_DEVICES]:
            return await self.async_step_init()
        if user_input is not None:
            gone = set(user_input.get(CONF_REMOVE, []))
            data[CONF_DEVICES] = [d for d in data[CONF_DEVICES] if d[CONF_ID] not in gone]
            return await self.async_step_init()
        options = [
            SelectOptionDict(value=d[CONF_ID], label=f"{d[CONF_NAME]} ({KIND_LABELS.get(d[CONF_KIND], d[CONF_KIND])})")
            for d in data[CONF_DEVICES]
        ]
        schema = vol.Schema(
            {
                vol.Optional(CONF_REMOVE): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_device", data_schema=schema)  # type: ignore[attr-defined]

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        data = self._load()
        if user_input is not None:
            data[CONF_TOTAL_ENTITY] = user_input.get(CONF_TOTAL_ENTITY)
            data[CONF_UPDATE_MINUTES] = int(user_input[CONF_UPDATE_MINUTES])
            data[CONF_SMOOTH_HOURS] = float(user_input[CONF_SMOOTH_HOURS])
            data[CONF_IMAGE_SCALE] = user_input[CONF_IMAGE_SCALE]
            data[CONF_IMAGE_GROUP] = bool(user_input[CONF_IMAGE_GROUP])
            data[CONF_SPREAD_MIN] = float(user_input[CONF_SPREAD_MIN])
            data[CONF_STANDBY_WH] = float(user_input[CONF_STANDBY_WH])
            return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TOTAL_ENTITY,
                    description={"suggested_value": data.get(CONF_TOTAL_ENTITY)},
                ): EntitySelector(EntitySelectorConfig(filter=ENERGY_FILTER)),
                vol.Required(
                    CONF_UPDATE_MINUTES, default=max(5, int(data[CONF_UPDATE_MINUTES]))
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_IMAGE_SCALE, default=data[CONF_IMAGE_SCALE]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["lin", "sqrt"],
                        translation_key="image_scale",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_IMAGE_GROUP, default=bool(data[CONF_IMAGE_GROUP])
                ): BooleanSelector(),
                vol.Required(
                    CONF_STANDBY_WH, default=float(data[CONF_STANDBY_WH])
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=200,
                        step=1,
                        unit_of_measurement="Wh",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SPREAD_MIN, default=float(data[CONF_SPREAD_MIN])
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=180,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SMOOTH_HOURS, default=float(data[CONF_SMOOTH_HOURS])
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=12,
                        step=0.5,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)  # type: ignore[attr-defined]

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._finish()


class EnergyBreakdownConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_TOKEN: secrets.token_urlsafe(16)},
                options={
                    CONF_TOTAL_ENTITY: user_input.get(CONF_TOTAL_ENTITY),
                    CONF_UPDATE_MINUTES: DEFAULT_UPDATE_MINUTES,
                    CONF_SMOOTH_HOURS: DEFAULT_SMOOTH_HOURS,
                    CONF_IMAGE_SCALE: DEFAULT_IMAGE_SCALE,
                    CONF_IMAGE_GROUP: False,
                    CONF_SPREAD_MIN: DEFAULT_SPREAD_MIN,
                    CONF_STANDBY_WH: DEFAULT_STANDBY_WH,
                    CONF_DEVICES: [],
                },
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Graphique d'énergie"): str,
                vol.Optional(CONF_TOTAL_ENTITY): EntitySelector(
                    EntitySelectorConfig(filter=ENERGY_FILTER)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return EnergyBreakdownOptionsFlow()


class EnergyBreakdownOptionsFlow(_DeviceMenuMixin, OptionsFlow):
    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            o = self.config_entry.options
            self._data = {
                CONF_TOTAL_ENTITY: o.get(CONF_TOTAL_ENTITY),
                CONF_UPDATE_MINUTES: o.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES),
                CONF_SMOOTH_HOURS: o.get(CONF_SMOOTH_HOURS, DEFAULT_SMOOTH_HOURS),
                CONF_IMAGE_SCALE: o.get(CONF_IMAGE_SCALE, DEFAULT_IMAGE_SCALE),
                CONF_IMAGE_GROUP: bool(o.get(CONF_IMAGE_GROUP, False)),
                CONF_SPREAD_MIN: float(o.get(CONF_SPREAD_MIN, DEFAULT_SPREAD_MIN)),
                CONF_STANDBY_WH: float(o.get(CONF_STANDBY_WH, DEFAULT_STANDBY_WH)),
                CONF_DEVICES: [dict(d) for d in o.get(CONF_DEVICES, [])],
            }
        return self._data

    async def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self._load())
