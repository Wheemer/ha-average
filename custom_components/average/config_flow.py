"""Config flow for Average Sensor."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha1
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
)
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
)

from .const import (
    CONF_DURATION,
    CONF_END,
    CONF_MAX_SOURCE_AGE,
    CONF_PRECISION,
    CONF_PROCESS_UNDEF_AS,
    CONF_START,
    DEFAULT_NAME,
    DEFAULT_PRECISION,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigFlowResult

ERR_PERIOD_START_OR_END_WITHOUT_DURATION = "period_start_or_end_without_duration"
ERR_TOO_MANY_PERIOD_OPTIONS = "too_many_period_options"
SECTION_ADVANCED = "advanced_options"

SOURCE_DOMAINS = [
    SENSOR_DOMAIN,
    NUMBER_DOMAIN,
    INPUT_NUMBER_DOMAIN,
    WEATHER_DOMAIN,
    CLIMATE_DOMAIN,
    WATER_HEATER_DOMAIN,
]


def _nested_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Convert flat saved options to sectioned form values."""
    advanced = {
        key: options[key]
        for key in (
            CONF_START,
            CONF_END,
            CONF_PROCESS_UNDEF_AS,
            CONF_MAX_SOURCE_AGE,
        )
        if key in options
    }
    nested = {
        key: value
        for key, value in options.items()
        if key
        not in (
            CONF_START,
            CONF_END,
            CONF_PROCESS_UNDEF_AS,
            CONF_MAX_SOURCE_AGE,
            CONF_SCAN_INTERVAL,
        )
    }
    if advanced:
        nested[SECTION_ADVANCED] = advanced
    return nested


def _flatten_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Convert sectioned form values to flat config entry options."""
    options = dict(user_input)
    advanced = options.pop(SECTION_ADVANCED, {}) or {}
    for key in (CONF_START, CONF_END, CONF_PROCESS_UNDEF_AS, CONF_MAX_SOURCE_AGE):
        if (value := advanced.get(key)) not in (None, ""):
            options[key] = value
    return options


def _validate_period(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate period fields."""
    user_input = _flatten_options(user_input)
    has_start = bool(user_input.get(CONF_START))
    has_end = bool(user_input.get(CONF_END))
    has_duration = user_input.get(CONF_DURATION) is not None
    period_count = sum((has_start, has_end, has_duration))

    if period_count == 1 and not has_duration:
        raise SchemaFlowError(ERR_PERIOD_START_OR_END_WITHOUT_DURATION)
    if period_count > 2:  # noqa: PLR2004
        raise SchemaFlowError(ERR_TOO_MANY_PERIOD_OPTIONS)

    return user_input


def _duration_to_selector(value: Any) -> dict[str, int] | None:
    """Convert YAML duration values to duration selector values."""
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        days = value.days
        seconds = value.seconds
        return {
            "days": days,
            "hours": seconds // 3600,
            "minutes": seconds % 3600 // 60,
            "seconds": seconds % 60,
        }
    return value


def _template_to_string(value: Any) -> str | None:
    """Convert YAML template values to strings."""
    if value in (None, ""):
        return None
    return cast("str", getattr(value, "template", str(value)))


def _yaml_config_to_options(config: dict[str, Any]) -> dict[str, Any]:
    """Convert YAML platform config to config entry options."""
    options: dict[str, Any] = {
        CONF_NAME: config[CONF_NAME],
        CONF_ENTITIES: config[CONF_ENTITIES],
        CONF_PRECISION: int(config.get(CONF_PRECISION, DEFAULT_PRECISION)),
    }

    if unique_id := config.get(CONF_UNIQUE_ID):
        options[CONF_UNIQUE_ID] = unique_id

    for key in (CONF_START, CONF_END):
        if value := _template_to_string(config.get(key)):
            options[key] = value

    for key in (CONF_DURATION, CONF_MAX_SOURCE_AGE, CONF_SCAN_INTERVAL):
        if value := _duration_to_selector(config.get(key)):
            options[key] = value

    if (undef := config.get(CONF_PROCESS_UNDEF_AS)) is not None:
        options[CONF_PROCESS_UNDEF_AS] = undef

    return options


def _import_unique_id(options: dict[str, Any]) -> str:
    """Return a stable unique ID for an imported YAML average sensor."""
    source = "|".join(
        [
            str(options.get(CONF_UNIQUE_ID)),
            options[CONF_NAME],
            ",".join(options[CONF_ENTITIES]),
            str(options.get(CONF_START)),
            str(options.get(CONF_END)),
            str(options.get(CONF_DURATION)),
        ]
    )
    return f"yaml_{sha1(source.encode(), usedforsecurity=False).hexdigest()}"


async def validate_options(
    _handler: SchemaConfigFlowHandler,
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Validate options selected."""
    return _validate_period(user_input)


async def suggested_options(handler: SchemaConfigFlowHandler) -> dict[str, Any]:
    """Return sectioned suggested values for the options flow."""
    return _nested_options(handler.options)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=SOURCE_DOMAINS,
                multiple=True,
                reorder=True,
            )
        ),
        vol.Optional(CONF_START): selector.TextSelector(),
        vol.Optional(CONF_END): selector.TextSelector(),
        vol.Optional(CONF_DURATION): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=6,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        ),
        vol.Optional(SECTION_ADVANCED): section(
            vol.Schema(
                {
                    vol.Optional(CONF_START): selector.TextSelector(),
                    vol.Optional(CONF_END): selector.TextSelector(),
                    vol.Optional(CONF_PROCESS_UNDEF_AS): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(CONF_MAX_SOURCE_AGE): selector.DurationSelector(
                        selector.DurationSelectorConfig(allow_negative=False)
                    ),
                }
            ),
            {"collapsed": True},
        ),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
    }
).extend(OPTIONS_SCHEMA.schema)

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        CONFIG_SCHEMA,
        validate_user_input=validate_options,
    ),
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        OPTIONS_SCHEMA,
        validate_user_input=validate_options,
        suggested_values=suggested_options,
    ),
}


class AverageConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config or options flow for Average Sensor."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast("str", options.get(CONF_NAME, DEFAULT_NAME))

    @staticmethod
    def async_options_flow_finished(_hass: Any, options: Mapping[str, Any]) -> None:
        """Clean up deprecated hidden options after the options flow."""
        if isinstance(options, dict):
            options.pop(CONF_SCAN_INTERVAL, None)

    async def async_step_import(
        self,
        import_config: dict[str, Any],
    ) -> ConfigFlowResult:
        """Import YAML configuration."""
        options = _yaml_config_to_options(import_config)
        _validate_period(options)

        await self.async_set_unique_id(_import_unique_id(options))
        self._abort_if_unique_id_configured()

        return self.async_create_entry(data=options)
