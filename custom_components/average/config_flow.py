"""Config flow for Average Sensor."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha1
from typing import TYPE_CHECKING, Any, cast

import probatio
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
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
)

from .const import (
    CONF_CALCULATE_TO_NOW_UNDEF,
    CONF_DURATION,
    CONF_END,
    CONF_IGNORE_UNDEF,
    CONF_MAX_SOURCE_AGE,
    CONF_PRECISION,
    CONF_PROCESS_UNDEF_AS,
    CONF_REQUIRE_ALL_SOURCES,
    CONF_START,
    CONF_WEIGHTS,
    DEFAULT_NAME,
    DEFAULT_PRECISION,
    DOMAIN,
)
from .weights import normalize_weights

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigEntry, ConfigFlowResult

ERR_PERIOD_START_OR_END_WITHOUT_DURATION = "period_start_or_end_without_duration"
ERR_TOO_MANY_PERIOD_OPTIONS = "too_many_period_options"
DEFAULT_SCAN_INTERVAL_SELECTOR = {"seconds": 20}
SECTIONS = {
    "advanced": (
        CONF_DURATION,
        CONF_START,
        CONF_END,
        CONF_SCAN_INTERVAL,
        CONF_PRECISION,
        CONF_WEIGHTS,
        CONF_MAX_SOURCE_AGE,
        CONF_PROCESS_UNDEF_AS,
        CONF_IGNORE_UNDEF,
        CONF_CALCULATE_TO_NOW_UNDEF,
    ),
}


async def suggested_options(handler: SchemaCommonFlowHandler) -> dict[str, Any]:
    """Present flat stored options in the collapsible form section."""
    options = dict(handler.options)
    for section_name, keys in SECTIONS.items():
        options[section_name] = {
            key: options.pop(key) for key in keys if key in options
        }
    return options


SOURCE_DOMAINS = [
    SENSOR_DOMAIN,
    NUMBER_DOMAIN,
    INPUT_NUMBER_DOMAIN,
    WEATHER_DOMAIN,
    CLIMATE_DOMAIN,
    WATER_HEATER_DOMAIN,
]


def _validate_period(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate period fields."""
    has_start = bool(user_input.get(CONF_START))
    has_end = bool(user_input.get(CONF_END))
    has_duration = user_input.get(CONF_DURATION) is not None
    period_count = sum((has_start, has_end, has_duration))

    if period_count == 1 and not has_duration:
        raise SchemaFlowError(ERR_PERIOD_START_OR_END_WITHOUT_DURATION)
    if period_count > 2:  # noqa: PLR2004
        raise SchemaFlowError(ERR_TOO_MANY_PERIOD_OPTIONS)

    if user_input.get(CONF_CALCULATE_TO_NOW_UNDEF) and not user_input.get(
        CONF_IGNORE_UNDEF
    ):
        error = "invalid_undefined_options"
        raise SchemaFlowError(error)
    if not user_input.get(CONF_ENTITIES):
        error = "no_sources"
        raise SchemaFlowError(error)
    for key in (CONF_DURATION, CONF_SCAN_INTERVAL, CONF_MAX_SOURCE_AGE):
        if user_input.get(key) is not None:
            error = "invalid_duration"
            try:
                seconds = cv.time_period(user_input[key]).total_seconds()
            except (ValueError, TypeError, probatio.Invalid) as err:
                raise SchemaFlowError(error) from err
            if seconds <= 0:
                raise SchemaFlowError(error)

    if CONF_WEIGHTS in user_input:
        try:
            user_input[CONF_WEIGHTS] = normalize_weights(
                user_input[CONF_WEIGHTS], user_input[CONF_ENTITIES]
            )
        except (TypeError, ValueError) as err:
            error = "invalid_weights"
            raise SchemaFlowError(error) from err
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
            "seconds": seconds % 60 + value.microseconds / 1_000_000,
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
        CONF_REQUIRE_ALL_SOURCES: config.get(CONF_REQUIRE_ALL_SOURCES, False),
    }

    if CONF_WEIGHTS in config:
        options[CONF_WEIGHTS] = config[CONF_WEIGHTS]

    if unique_id := config.get(CONF_UNIQUE_ID):
        options[CONF_UNIQUE_ID] = unique_id

    for key in (CONF_START, CONF_END):
        if value := _template_to_string(config.get(key)):
            options[key] = value

    for key in (CONF_DURATION, CONF_MAX_SOURCE_AGE, CONF_SCAN_INTERVAL):
        if value := _duration_to_selector(config.get(key)):
            options[key] = value

    for key in (CONF_IGNORE_UNDEF, CONF_CALCULATE_TO_NOW_UNDEF):
        if key in config:
            options[key] = config[key]

    if (undef := config.get(CONF_PROCESS_UNDEF_AS)) is not None:
        options[CONF_PROCESS_UNDEF_AS] = undef

    return options


def _import_unique_id(options: dict[str, Any]) -> str:
    """Return a stable unique ID for an imported YAML average sensor."""
    if unique_id := options.get(CONF_UNIQUE_ID):
        return f"yaml_{unique_id}"

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


def _entry_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the combined config entry options."""
    return {**entry.data, **entry.options}


async def validate_options(
    _handler: SchemaConfigFlowHandler,
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Validate the form while retaining the flat storage contract."""
    options = dict(user_input)
    if CONF_REQUIRE_ALL_SOURCES in _handler.options:
        options.setdefault(
            CONF_REQUIRE_ALL_SOURCES, _handler.options[CONF_REQUIRE_ALL_SOURCES]
        )
    for section_name, keys in SECTIONS.items():
        selected = options.pop(section_name, None)
        if selected is None:
            for key in keys:
                if key in _handler.options:
                    options.setdefault(key, _handler.options[key])
        else:
            options.update(selected)
    _validate_period(options)
    # Clearing an advanced field must also clear its previously saved value.
    for keys in SECTIONS.values():
        for key in keys:
            _handler.options.pop(key, None)
    return options


ADVANCED_SCHEMA = probatio.Schema(
    {
        probatio.Optional(CONF_DURATION): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        probatio.Optional(CONF_START): selector.TemplateSelector(),
        probatio.Optional(CONF_END): selector.TemplateSelector(),
        probatio.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_SELECTOR): (
            selector.DurationSelector(
                selector.DurationSelectorConfig(
                    enable_day=False,
                    allow_negative=False,
                )
            )
        ),
        probatio.Optional(
            CONF_PRECISION, default=DEFAULT_PRECISION
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(step=1, mode=selector.NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_WEIGHTS): selector.ObjectSelector(),
        probatio.Optional(CONF_MAX_SOURCE_AGE): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        probatio.Optional(CONF_PROCESS_UNDEF_AS): selector.NumberSelector(
            selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_IGNORE_UNDEF): selector.BooleanSelector(),
        probatio.Optional(CONF_CALCULATE_TO_NOW_UNDEF): selector.BooleanSelector(),
    }
)

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=SOURCE_DOMAINS, multiple=True, reorder=True
            )
        ),
        probatio.Optional(
            CONF_REQUIRE_ALL_SOURCES, default=False
        ): selector.BooleanSelector(),
        probatio.Optional("advanced"): section(ADVANCED_SCHEMA, {"collapsed": True}),
    }
)

CONFIG_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
    }
).extend(OPTIONS_SCHEMA.schema)

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        CONFIG_SCHEMA,
        suggested_values=suggested_options,
        validate_user_input=validate_options,
    ),
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        OPTIONS_SCHEMA,
        suggested_values=suggested_options,
        validate_user_input=validate_options,
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

    async def async_step_import(
        self,
        import_config: dict[str, Any],
    ) -> ConfigFlowResult:
        """Import YAML configuration."""
        options = _yaml_config_to_options(import_config)
        _validate_period(options)

        if unique_id := options.get(CONF_UNIQUE_ID):
            for entry in self._async_current_entries():
                entry_options = _entry_options(entry)
                if entry_options.get(CONF_UNIQUE_ID) == unique_id:
                    merged_options = {**entry_options, **options}
                    self.hass.config_entries.async_update_entry(
                        entry,
                        options=merged_options,
                        title=self.async_config_entry_title(merged_options),
                    )
                    return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(_import_unique_id(options))
        self._abort_if_unique_id_configured()

        return self.async_create_entry(data=options)
