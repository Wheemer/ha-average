"""Config flow for Average Sensor."""

from __future__ import annotations

import logging
from datetime import timedelta
from hashlib import sha1
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntryState
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
)

from .attributes import normalize_source_attributes
from .const import (
    CONF_CALCULATE_TO_NOW_UNDEF,
    CONF_DURATION,
    CONF_END,
    CONF_HISTORY_QUERY_TIMEOUT,
    CONF_IGNORE_UNDEF,
    CONF_MAX_HISTORY_PERIOD,
    CONF_MAX_SOURCE_AGE,
    CONF_PRECISION,
    CONF_PROCESS_UNDEF_AS,
    CONF_REQUIRE_ALL_SOURCES,
    CONF_SOURCE_ATTRIBUTES,
    CONF_START,
    CONF_WEIGHTS,
    DEFAULT_NAME,
    DEFAULT_PRECISION,
    DOMAIN,
)
from .validation import finite_number
from .weights import normalize_weights
from .yaml_import import (
    DATA_YAML_IDS,
    DATA_YAML_NAMES,
    LEGACY_UNIQUE_ID,
    clear_identity_change,
    report_duplicate_id,
    report_identity_change,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigEntry, ConfigFlowResult

# Use the schema library expected by this Core version's public form API.
# Newer Core uses probatio; earlier supported Core versions use voluptuous.
schema_lib = import_module(
    get_type_hints(section.__init__)["schema"].__module__.split(".", 1)[0]
)

_LOGGER = logging.getLogger(__name__)

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
        CONF_SOURCE_ATTRIBUTES,
        CONF_MAX_SOURCE_AGE,
        CONF_PROCESS_UNDEF_AS,
        CONF_IGNORE_UNDEF,
        CONF_MAX_HISTORY_PERIOD,
        CONF_HISTORY_QUERY_TIMEOUT,
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
    if CONF_NAME in user_input and not user_input[CONF_NAME].strip():
        error = "invalid_name"
        raise SchemaFlowError(error)
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
    for key in (
        CONF_DURATION,
        CONF_SCAN_INTERVAL,
        CONF_MAX_SOURCE_AGE,
        CONF_MAX_HISTORY_PERIOD,
        CONF_HISTORY_QUERY_TIMEOUT,
    ):
        if user_input.get(key) is not None:
            error = "invalid_duration"
            try:
                seconds = cv.time_period(user_input[key]).total_seconds()
            except (ValueError, TypeError, schema_lib.Invalid) as err:
                raise SchemaFlowError(error) from err
            if seconds <= 0:
                raise SchemaFlowError(error)

    if CONF_PROCESS_UNDEF_AS in user_input:
        try:
            finite_number(user_input[CONF_PROCESS_UNDEF_AS])
        except (TypeError, ValueError) as err:
            error = "invalid_undefined_value"
            raise SchemaFlowError(error) from err
    _validate_source_mappings(user_input)
    return user_input


def _validate_source_mappings(user_input: dict[str, Any]) -> None:
    """Apply the shared YAML/UI validators to optional source mappings."""
    for key, normalize, error in (
        (CONF_WEIGHTS, normalize_weights, "invalid_weights"),
        (
            CONF_SOURCE_ATTRIBUTES,
            normalize_source_attributes,
            "invalid_source_attributes",
        ),
    ):
        if key in user_input:
            try:
                user_input[key] = normalize(user_input[key], user_input[CONF_ENTITIES])
            except (TypeError, ValueError) as err:
                raise SchemaFlowError(error) from err


def _duration_to_selector(value: Any) -> dict[str, int | float] | None:
    """Convert YAML duration values to duration selector values."""
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        days = value.days
        seconds = value.seconds
        selector_seconds: int | float = seconds % 60
        if value.microseconds:
            selector_seconds += value.microseconds / 1_000_000
        return {
            "days": days,
            "hours": seconds // 3600,
            "minutes": seconds % 3600 // 60,
            "seconds": selector_seconds,
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

    for key in (CONF_WEIGHTS, CONF_SOURCE_ATTRIBUTES):
        if key in config:
            options[key] = config[key]

    if unique_id := config.get(CONF_UNIQUE_ID):
        options[CONF_UNIQUE_ID] = unique_id

    for key in (CONF_START, CONF_END):
        if value := _template_to_string(config.get(key)):
            options[key] = value

    for key in (
        CONF_DURATION,
        CONF_MAX_SOURCE_AGE,
        CONF_SCAN_INTERVAL,
        CONF_MAX_HISTORY_PERIOD,
        CONF_HISTORY_QUERY_TIMEOUT,
    ):
        if selector_value := _duration_to_selector(config.get(key)):
            options[key] = selector_value

    for key in (CONF_IGNORE_UNDEF, CONF_CALCULATE_TO_NOW_UNDEF):
        if key in config:
            options[key] = config[key]

    if (undef := config.get(CONF_PROCESS_UNDEF_AS)) is not None:
        options[CONF_PROCESS_UNDEF_AS] = undef

    return options


def _import_unique_id(options: dict[str, Any]) -> str:
    """Return a stable unique ID for an imported YAML average sensor."""
    if (unique_id := options.get(CONF_UNIQUE_ID)) and unique_id != LEGACY_UNIQUE_ID:
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


ADVANCED_SCHEMA = schema_lib.Schema(
    {
        schema_lib.Optional(CONF_DURATION): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        schema_lib.Optional(CONF_MAX_HISTORY_PERIOD): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        schema_lib.Optional(CONF_HISTORY_QUERY_TIMEOUT): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        schema_lib.Optional(CONF_START): selector.TemplateSelector(),
        schema_lib.Optional(CONF_END): selector.TemplateSelector(),
        schema_lib.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_SELECTOR
        ): (
            selector.DurationSelector(
                selector.DurationSelectorConfig(
                    enable_day=False,
                    allow_negative=False,
                )
            )
        ),
        schema_lib.Optional(
            CONF_PRECISION, default=DEFAULT_PRECISION
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(step=1, mode=selector.NumberSelectorMode.BOX)
        ),
        schema_lib.Optional(CONF_WEIGHTS): selector.ObjectSelector(),
        schema_lib.Optional(CONF_SOURCE_ATTRIBUTES): selector.ObjectSelector(),
        schema_lib.Optional(CONF_MAX_SOURCE_AGE): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        schema_lib.Optional(CONF_PROCESS_UNDEF_AS): selector.NumberSelector(
            selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
        ),
        schema_lib.Optional(CONF_IGNORE_UNDEF): selector.BooleanSelector(),
        schema_lib.Optional(CONF_CALCULATE_TO_NOW_UNDEF): selector.BooleanSelector(),
    }
)

OPTIONS_SCHEMA = schema_lib.Schema(
    {
        schema_lib.Required(CONF_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=SOURCE_DOMAINS,
                multiple=True,
                **(
                    {"reorder": True}
                    if "reorder" in selector.EntitySelectorConfig.__annotations__
                    else {}
                ),
            )
        ),
        schema_lib.Optional(
            CONF_REQUIRE_ALL_SOURCES, default=False
        ): selector.BooleanSelector(),
        schema_lib.Optional("advanced"): section(ADVANCED_SCHEMA, {"collapsed": True}),
    }
)

CONFIG_SCHEMA = schema_lib.Schema(
    {
        schema_lib.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
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


# Core registers flows through a dynamic __init_subclass__ domain keyword.
class AverageConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):  # type: ignore[call-arg]
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
        try:
            _validate_period(options)
        except SchemaFlowError as err:
            _LOGGER.warning(
                'Invalid Average Sensor YAML for "%s": %s', options[CONF_NAME], err
            )
            return self.async_abort(reason="invalid_config")

        if (unique_id := options.get(CONF_UNIQUE_ID)) and unique_id != LEGACY_UNIQUE_ID:
            result = self._async_import_explicit_id(options)
            if result is not None:
                return result

        await self.async_set_unique_id(_import_unique_id(options))
        identities = [self.unique_id]
        duration = options.get(CONF_DURATION)
        if isinstance(duration, dict) and isinstance(duration.get("seconds"), int):
            # Recognize the interim float-seconds format without changing saved IDs.
            interim = {
                **options,
                CONF_DURATION: {**duration, "seconds": float(duration["seconds"])},
            }
            identities.append(_import_unique_id(interim))
        for identity in identities:
            for entry in self._async_current_entries():
                entry_options = _entry_options(entry)
                legacy_match = (
                    options.get(CONF_UNIQUE_ID) == LEGACY_UNIQUE_ID
                    and entry_options.get(CONF_UNIQUE_ID) == LEGACY_UNIQUE_ID
                    and _import_unique_id(entry_options) == identity
                )
                if entry.unique_id == identity or legacy_match:
                    self._async_update_imported_entry(entry, options)
                    return self.async_abort(reason="already_configured")

        # The legacy marker is per-sensor, not an explicit global ID. A single
        # named YAML definition can update its own entry after source edits.
        if options.get(CONF_UNIQUE_ID) == LEGACY_UNIQUE_ID:
            names = self.hass.data.get(DATA_YAML_IDS, {}).get(LEGACY_UNIQUE_ID, [])
            matches = [
                entry
                for entry in self._async_current_entries()
                if _entry_options(entry).get(CONF_UNIQUE_ID) == LEGACY_UNIQUE_ID
                and _entry_options(entry).get(CONF_NAME) == options[CONF_NAME]
            ]
            if names.count(options[CONF_NAME]) == 1 and len(matches) == 1:
                self._async_update_imported_entry(matches[0], options)
                return self.async_abort(reason="already_configured")

        if self._async_identity_change_requires_id(options):
            return self.async_abort(reason="yaml_identity_changed")

        return self.async_create_entry(data=options)

    @callback
    def _async_import_explicit_id(
        self, options: dict[str, Any]
    ) -> ConfigFlowResult | None:
        """Update a verified explicit identity or refuse conflicting definitions."""
        unique_id = options[CONF_UNIQUE_ID]
        yaml_names = self.hass.data.get(DATA_YAML_IDS, {}).get(unique_id, [])
        if len(yaml_names) > 1 or (yaml_names and yaml_names[0] != options[CONF_NAME]):
            report_duplicate_id(self.hass, unique_id)
            return self.async_abort(reason="duplicate_unique_id")
        for entry in self._async_current_entries():
            entry_options = _entry_options(entry)
            if entry_options.get(CONF_UNIQUE_ID) == unique_id:
                if (
                    not yaml_names
                    and entry_options.get(CONF_NAME) != options[CONF_NAME]
                ):
                    report_duplicate_id(self.hass, unique_id)
                    return self.async_abort(reason="duplicate_unique_id")
                self._async_update_imported_entry(entry, options)
                return self.async_abort(reason="already_configured")

        if entry := self._async_entry_for_entity_id(unique_id):
            self._async_update_imported_entry(entry, options)
            return self.async_abort(reason="already_configured")

        return None

    @callback
    def _async_entry_for_entity_id(self, unique_id: str) -> ConfigEntry | None:
        """Adopt a no-ID entry using the existing registry identity explicitly."""
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)
        if entity_id is None:
            return None
        owner = registry.async_get(entity_id).config_entry_id
        return next(
            (
                entry
                for entry in self._async_current_entries()
                if entry.entry_id == owner
                and not _entry_options(entry).get(CONF_UNIQUE_ID)
            ),
            None,
        )

    @callback
    def _async_identity_change_requires_id(self, options: dict[str, Any]) -> bool:
        """Refuse ambiguous no-ID edits instead of spawning hidden duplicates."""
        if options.get(CONF_UNIQUE_ID):
            return False
        candidates = [
            entry
            for entry in self._async_current_entries()
            if entry.source == SOURCE_IMPORT
            and not _entry_options(entry).get(CONF_UNIQUE_ID)
            and (
                _entry_options(entry).get(CONF_NAME) == options[CONF_NAME]
                or _import_unique_id({**_entry_options(entry), CONF_NAME: ""})
                == _import_unique_id({**options, CONF_NAME: ""})
            )
        ]
        if candidates:
            registry = er.async_get(self.hass)
            choices: list[str] = []
            for entry in candidates:
                entities = [
                    entity
                    for entity in er.async_entries_for_config_entry(
                        registry, entry.entry_id
                    )
                    if entity.platform == DOMAIN and entity.domain == SENSOR_DOMAIN
                ]
                if entities:
                    choices.extend(
                        f'- `{entity.entity_id}`: `unique_id: "{entity.unique_id}"`'
                        for entity in entities
                    )
                else:
                    choices.append(f'- {entry.title}: `unique_id: "{entry.entry_id}"`')
            report_identity_change(self.hass, options[CONF_NAME], "\n".join(choices))
            # Preserve valid multiple-same-name YAML definitions. For a
            # single definition an ambiguous edit must not spawn a duplicate.
            if self.hass.data.get(DATA_YAML_NAMES, {}).get(options[CONF_NAME], 0) <= 1:
                return True

        return False

    @callback
    def _async_update_imported_entry(
        self, entry: ConfigEntry, options: dict[str, Any]
    ) -> None:
        """Apply changed YAML to a loaded entry, without duplicate or no-op reloads."""
        current = _entry_options(entry)
        if options.get(CONF_UNIQUE_ID):
            clear_identity_change(self.hass, current[CONF_NAME])
            clear_identity_change(self.hass, options[CONF_NAME])
        # Active YAML is the source of truth, including removed optional keys.
        merged = dict(options)
        if merged == current:
            return
        self.hass.config_entries.async_update_entry(
            entry, data={}, options=merged, title=self.async_config_entry_title(merged)
        )
        if entry.state is ConfigEntryState.LOADED and hasattr(
            SchemaConfigFlowHandler, "options_flow_reloads"
        ):
            # Older Core uses the integration's entry update listener instead.
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
