#  Copyright (c) 2019-2024, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
#  Creative Commons BY-NC-SA 4.0 International Public License
#  (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)

"""
The Average Sensor.

For more details about this sensor, please refer to the documentation at
https://github.com/Limych/ha-average/
"""

from __future__ import annotations

import logging
import math
import numbers
from asyncio import (
    CancelledError,
    Future,
    current_task,
    ensure_future,
    shield,
    sleep,
    timeout,
    wait,
)
from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
from hashlib import sha1
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import (
        AddConfigEntryEntitiesCallback,
        AddEntitiesCallback,
    )
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.recorder import get_instance, history
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    HomeAssistant,
    State,
    callback,
    split_entity_id,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import (
    PLATFORM_SCHEMA as BASE_PLATFORM_SCHEMA,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.group import expand_entity_ids
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.template import Template
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.util.unit_system import TEMPERATURE_UNITS

from .attributes import normalize_source_attributes
from .const import (
    ATTR_AVAILABLE_SOURCES,
    ATTR_COUNT,
    ATTR_COUNT_SOURCES,
    ATTR_END,
    ATTR_MAX_VALUE,
    ATTR_MIN_VALUE,
    ATTR_START,
    ATTR_TO_PROPERTY,
    ATTR_TRENDING_TOWARDS,
    CONF_CALCULATE_TO_NOW_UNDEF,
    CONF_DURATION,
    CONF_END,
    CONF_HISTORY_QUERY_TIMEOUT,
    CONF_IGNORE_UNDEF,
    CONF_MAX_HISTORY_PERIOD,
    CONF_MAX_SOURCE_AGE,
    CONF_PERIOD_KEYS,
    CONF_PRECISION,
    CONF_PROCESS_UNDEF_AS,
    CONF_REQUIRE_ALL_SOURCES,
    CONF_SOURCE_ATTRIBUTES,
    CONF_START,
    CONF_WEIGHTS,
    DEFAULT_HISTORY_QUERY_TIMEOUT,
    DEFAULT_MAX_HISTORY_PERIOD,
    DEFAULT_NAME,
    DEFAULT_PRECISION,
    DOMAIN,
    UPDATE_MIN_TIME,
)
from .validation import finite_number
from .weights import normalize_weights
from .yaml_import import LEGACY_UNIQUE_ID

_LOGGER = logging.getLogger(__name__)
YAML_IMPORT_ISSUE_ID = "yaml_imported"
HISTORY_PROCESSING_BATCH_SIZE = 512
DATA_PENDING_HISTORY = f"{DOMAIN}_pending_history"


class HistoryQueryError(HomeAssistantError):
    """A recorder refresh failed safely and can be retried."""


def _materialized_history(  # noqa: PLR0913
    hass: HomeAssistant,
    start: datetime,
    end: datetime,
    entity_id: str,
    *,
    uses_attributes: bool,
    needs_attributes: bool,
) -> dict[str, list[State]]:
    """Query and decode recorder's lazy states entirely in its executor."""
    if uses_attributes:
        # Default flags request complete State objects, not minimal/compressed dicts.
        result = cast(
            "dict[str, list[State]]",
            history.get_significant_states(
                hass, start, end, [entity_id], significant_changes_only=False
            ),
        )
    else:
        result = history.state_changes_during_period(
            hass, start, end, entity_id, no_attributes=not needs_attributes
        )
    for states in result.values():
        for state in states or ():
            if state is not None:
                # LazyState defers JSON decoding and datetime construction until
                # first access. Keep that work out of the averaging event loop.
                if needs_attributes:
                    _ = state.attributes
                _ = state.last_updated if uses_attributes else state.last_changed
    return result


def _stored_undefined_value(value: Any) -> int | float | None:
    """Defend against invalid values saved before finite-number validation."""
    if value is None:
        return None
    try:
        return finite_number(value)
    except TypeError, ValueError:
        _LOGGER.warning("Ignoring invalid stored process_undef_as value")
        return None


def check_period_keys(conf: ConfigType) -> ConfigType:
    """Ensure maximum 2 of CONF_PERIOD_KEYS are provided."""
    count = sum(param in conf for param in CONF_PERIOD_KEYS)
    if (count == 1 and CONF_DURATION not in conf) or count > 2:  # noqa: PLR2004
        raise vol.Invalid(
            "You must provide none, only "
            + CONF_DURATION
            + " or maximum 2 of the following: "
            + ", ".join(CONF_PERIOD_KEYS)
        )
    if conf.get(CONF_CALCULATE_TO_NOW_UNDEF) and not conf.get(CONF_IGNORE_UNDEF):
        msg = "calculate_to_now_undef requires ignore_undef"
        raise vol.Invalid(msg)
    if CONF_PROCESS_UNDEF_AS in conf:
        try:
            finite_number(conf[CONF_PROCESS_UNDEF_AS])
        except (TypeError, ValueError) as err:
            raise vol.Invalid(str(err)) from err
    for key in (CONF_MAX_HISTORY_PERIOD, CONF_HISTORY_QUERY_TIMEOUT):
        if key in conf and conf[key] <= timedelta(0):
            message = f"{key} must be greater than zero"
            raise vol.Invalid(message)
    if CONF_WEIGHTS in conf:
        try:
            conf[CONF_WEIGHTS] = normalize_weights(
                conf[CONF_WEIGHTS], conf[CONF_ENTITIES]
            )
        except (TypeError, ValueError) as err:
            raise vol.Invalid(str(err)) from err
    if CONF_SOURCE_ATTRIBUTES in conf:
        try:
            conf[CONF_SOURCE_ATTRIBUTES] = normalize_source_attributes(
                conf[CONF_SOURCE_ATTRIBUTES], conf[CONF_ENTITIES]
            )
        except (TypeError, ValueError) as err:
            raise vol.Invalid(str(err)) from err
    return conf


PLATFORM_SCHEMA = vol.All(
    BASE_PLATFORM_SCHEMA.extend(
        {
            vol.Required(CONF_ENTITIES): cv.entity_ids,
            vol.Optional(CONF_REQUIRE_ALL_SOURCES, default=False): cv.boolean,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            vol.Optional(CONF_START): cv.template,
            vol.Optional(CONF_END): cv.template,
            vol.Optional(CONF_DURATION): cv.positive_time_period,
            vol.Optional(CONF_MAX_HISTORY_PERIOD): cv.positive_time_period,
            vol.Optional(CONF_HISTORY_QUERY_TIMEOUT): cv.positive_time_period,
            vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): int,
            vol.Optional(CONF_PROCESS_UNDEF_AS): vol.Any(int, float),
            vol.Optional(CONF_IGNORE_UNDEF, default=False): cv.boolean,
            vol.Optional(CONF_CALCULATE_TO_NOW_UNDEF, default=False): cv.boolean,
            vol.Optional(CONF_MAX_SOURCE_AGE): cv.positive_time_period,
            vol.Optional(CONF_WEIGHTS): dict,
            vol.Optional(CONF_SOURCE_ATTRIBUTES): dict,
        }
    ),
    check_period_keys,
)


# pylint: disable=unused-argument
async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,  # noqa: ARG001
    discovery_info: DiscoveryInfoType | None = None,  # noqa: ARG001
) -> None:
    """Set up platform."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=config,
    )
    if result["type"] != FlowResultType.CREATE_ENTRY and not (
        result["type"] == FlowResultType.ABORT
        and result.get("reason") == "already_configured"
    ):
        return
    async_create_issue(
        hass,
        DOMAIN,
        YAML_IMPORT_ISSUE_ID,
        is_fixable=False,
        is_persistent=True,
        severity=IssueSeverity.WARNING,
        translation_key="yaml_imported",
    )


def _duration_from_selector(value: Any) -> timedelta | None:
    """Convert a duration selector value to a timedelta."""
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return value
    if isinstance(value, dict):
        return timedelta(
            days=value.get("days", 0) or 0,
            hours=value.get("hours", 0) or 0,
            minutes=value.get("minutes", 0) or 0,
            seconds=value.get("seconds", 0) or 0,
            milliseconds=value.get("milliseconds", 0) or 0,
        )
    return cv.positive_time_period(value)


def _entry_unique_id(
    hass: HomeAssistant, options: Mapping[str, Any], entry_id: str
) -> str:
    """Return the sensor unique ID for a config entry."""
    if unique_id := options.get(CONF_UNIQUE_ID):
        if unique_id == LEGACY_UNIQUE_ID:
            # A legacy hash identifies the existing entity, not its new sources.
            # Retain it when options or active YAML edits reload the entry.
            registry = er.async_get(hass)
            for entity in er.async_entries_for_config_entry(registry, entry_id):
                if entity.domain == SENSOR_DOMAIN and entity.platform == DOMAIN:
                    return entity.unique_id
        return unique_id

    legacy_unique_id = slugify(options[CONF_NAME])
    entity_id = er.async_get(hass).async_get_entity_id(
        SENSOR_DOMAIN,
        DOMAIN,
        legacy_unique_id,
    )
    if entity_id:
        return legacy_unique_id

    return entry_id


def _entry_config(hass: HomeAssistant, config_entry: ConfigEntry) -> ConfigType:
    """Convert a config entry into AverageSensor config."""
    options = {**config_entry.data, **config_entry.options}
    config: dict[str, Any] = {
        CONF_NAME: options[CONF_NAME],
        CONF_ENTITIES: options[CONF_ENTITIES],
        CONF_UNIQUE_ID: _entry_unique_id(hass, options, config_entry.entry_id),
        CONF_PRECISION: int(options.get(CONF_PRECISION, DEFAULT_PRECISION)),
        CONF_REQUIRE_ALL_SOURCES: options.get(CONF_REQUIRE_ALL_SOURCES, False),
    }

    for key in (CONF_WEIGHTS, CONF_SOURCE_ATTRIBUTES):
        if key in options:
            config[key] = options[key]

    for key in (CONF_IGNORE_UNDEF, CONF_CALCULATE_TO_NOW_UNDEF):
        config[key] = options.get(key, False)

    for key in (CONF_START, CONF_END):
        value = options.get(key)
        if value:
            config[key] = Template(value, hass)

    for key in (
        CONF_DURATION,
        CONF_MAX_SOURCE_AGE,
        CONF_SCAN_INTERVAL,
        CONF_MAX_HISTORY_PERIOD,
        CONF_HISTORY_QUERY_TIMEOUT,
    ):
        duration = _duration_from_selector(options.get(key))
        if duration is not None:
            config[key] = duration

    if (undef := options.get(CONF_PROCESS_UNDEF_AS)) is not None:
        config[CONF_PROCESS_UNDEF_AS] = undef

    return config


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Average Sensor from a config entry."""
    async_add_entities(
        [
            AverageSensor(
                hass, _entry_config(hass, config_entry), entry_id=config_entry.entry_id
            )
        ]
    )


# pylint: disable=too-many-instance-attributes
class AverageSensor(RestoreSensor):
    """Implementation of an Average sensor."""

    min_datetime: datetime | None
    max_datetime: datetime | None
    min_value: int | float | None
    max_value: int | float | None

    _unrecorded_attributes = frozenset(
        {
            ATTR_START,
            ATTR_END,
            ATTR_COUNT_SOURCES,
            ATTR_AVAILABLE_SOURCES,
            ATTR_COUNT,
            ATTR_MAX_VALUE,
            ATTR_MIN_VALUE,
            ATTR_TRENDING_TOWARDS,
        }
    )

    # pylint: disable=too-many-arguments
    def __init__(
        self, hass: HomeAssistant, config: ConfigType, *, entry_id: str | None = None
    ) -> None:
        """Initialize the sensor."""
        unique_id = config.get(CONF_UNIQUE_ID)
        start = config.get(CONF_START)
        end = config.get(CONF_END)
        duration = config.get(CONF_DURATION)

        for template in [start, end]:
            if template is not None:
                template.hass = hass

        self._start_template = start
        self._end_template = end
        self._duration = duration
        self._max_history_period = config.get(
            CONF_MAX_HISTORY_PERIOD, DEFAULT_MAX_HISTORY_PERIOD
        )
        self._history_query_timeout = config.get(
            CONF_HISTORY_QUERY_TIMEOUT, DEFAULT_HISTORY_QUERY_TIMEOUT
        )
        self._history_range_exceeded = False
        self._recorder_unavailable = False
        self._precision = config.get(CONF_PRECISION, DEFAULT_PRECISION)
        self._undef = _stored_undefined_value(config.get(CONF_PROCESS_UNDEF_AS))
        self._weights = config.get(CONF_WEIGHTS, {})
        self._source_attributes = config.get(CONF_SOURCE_ATTRIBUTES, {})
        self._ignore_undef = config.get(CONF_IGNORE_UNDEF, False)
        self._calculate_to_now_undef = config.get(CONF_CALCULATE_TO_NOW_UNDEF, False)
        self._require_all_sources = config.get(CONF_REQUIRE_ALL_SOURCES, False)
        self._max_source_age = config.get(CONF_MAX_SOURCE_AGE)
        self._update_interval = config.get(CONF_SCAN_INTERVAL, UPDATE_MIN_TIME)
        self._last_update: datetime | None = None
        self._update_in_progress = False
        self._initialize_refresh_tracking()
        self._pending_history_query: Future | None = None
        self._history_complete = False
        self._last_history_metadata: tuple[tuple[Any, ...], ...] | None = None
        self._stopping = False
        self._temperature_mode: bool | None = None
        self._temperature_conversion_errors: dict[str, int] = {}
        self._actual_end: datetime | None = None

        self.hass = hass
        self._entry_id = entry_id
        self.sources = expand_entity_ids(hass, config.get(CONF_ENTITIES, []))
        self.count_sources = len(self.sources)
        self.available_sources = 0
        self.count = 0
        self.trending_towards: int | float | None = None
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None

        self._attr_name = config.get(CONF_NAME, DEFAULT_NAME)
        self._attr_native_value: int | float | None = None
        self._attr_native_unit_of_measurement: str | None = None
        self._attr_icon = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = None
        #
        self._attr_unique_id = (
            str(
                sha1(
                    ";".join(
                        [str(start), str(duration), str(end), ",".join(self.sources)]
                    ).encode("utf-8"),
                    usedforsecurity=False,
                ).hexdigest()
            )
            if unique_id == "__legacy__"
            else unique_id
        )

    def _initialize_refresh_tracking(self) -> None:
        """Initialize task ownership and diagnostic deduplication state."""
        self._period: tuple[datetime, datetime] | None = None
        self.start: datetime | None = None
        self.end: datetime | None = None
        self._refresh_tasks: set[Task[Any]] = set()
        self._empty_history_sources: set[str] = set()
        self._temperature_failure_signatures: dict[str, tuple[str, str]] = {}
        self._period_boundary_errors: dict[str, str] = {}
        self._period_was_reversed = False

    @property
    def _has_period(self) -> bool:
        """Return True if sensor has any period setting."""
        return (
            self._start_template is not None
            or self._end_template is not None
            or self._duration is not None
        )

    @property
    def should_poll(self) -> bool:
        """Return the polling state."""
        return self._has_period or self._max_source_age is not None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self._require_all_sources:
            now = dt_util.utcnow()
            if not self.sources:
                return False
            for entity_id in self.sources:
                state = self.hass.states.get(entity_id)
                if state is None or self._is_source_stale(state, now):
                    return False
                value = self._get_source_value(state, log_errors=False)
                try:
                    if not math.isfinite(float(value)):
                        return False
                except TypeError, ValueError:
                    return False
            if self.available_sources != self.count_sources:
                return False
        return self.available_sources > 0 and self._has_state(self._attr_native_value)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            CONF_REQUIRE_ALL_SOURCES: self._require_all_sources,
            **{
                attr: getattr(self, attr)
                for attr in ATTR_TO_PROPERTY
                if getattr(self, attr) is not None
            },
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        startup_fired = False
        source_unsub = None
        self._stopping = False

        @callback
        def async_stop_updates(_event: Event | None = None) -> None:
            """Latch shutdown through CLOSE and remove the source listener."""
            nonlocal source_unsub
            self._stopping = True
            self._cancel_refresh_waiters()
            if source_unsub is not None:
                source_unsub()
                source_unsub = None

        self.async_on_remove(async_stop_updates)
        self.async_on_remove(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, async_stop_updates
            )
        )
        await self._async_restore_previous_state()

        # pylint: disable=unused-argument
        @callback
        async def async_sensor_state_listener(event: Event[Any]) -> None:  # noqa: ARG001
            """Handle device state changes."""
            if self._stopping or self.hass.is_stopping:
                return
            if self._require_all_sources:
                self.async_write_ha_state()
            last_state = self._attr_native_value
            if self._has_period:
                await self.async_update()
            else:
                await self._async_update_state()
            if self._stopping or self.hass.is_stopping:
                return
            if self._require_all_sources or last_state != self._attr_native_value:
                self.async_schedule_update_ha_state(force_refresh=True)

        # pylint: disable=unused-argument
        @callback
        async def async_sensor_startup(event: Event[Any]) -> None:  # noqa: ARG001
            """Update template on startup."""
            nonlocal startup_fired, source_unsub
            if self._stopping or self.hass.is_stopping:
                return
            startup_fired = True

            if self._require_all_sources or not self._has_period:
                source_unsub = async_track_state_change_event(
                    self.hass, self.sources, async_sensor_state_listener
                )
            if self._has_period:
                self.async_schedule_update_ha_state(force_refresh=True)
            else:
                await async_sensor_state_listener(Event("startup"))

        if self.hass.is_running:
            await async_sensor_startup(Event("reload"))
        else:
            remove_startup_listener = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_START, async_sensor_startup
            )

            @callback
            def async_remove_startup_listener() -> None:
                """Remove startup listener if it has not fired yet."""
                if not startup_fired:
                    remove_startup_listener()

            self.async_on_remove(async_remove_startup_listener)

    async def _async_restore_previous_state(self) -> None:
        """Restore the last known state until the next refresh completes."""
        last_sensor_data = await self.async_get_last_sensor_data()
        last_state = await self.async_get_last_state()

        if last_sensor_data is not None:
            native_value = last_sensor_data.native_value
            native_unit = last_sensor_data.native_unit_of_measurement
        elif last_state is not None:
            native_value = last_state.state
            native_unit = last_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        else:
            return

        if not self._has_state(str(native_value)):
            return

        if not isinstance(native_value, (str, int, float, Decimal)):
            return
        try:
            native_value = finite_number(float(native_value))
        except TypeError, ValueError, OverflowError:
            return

        self._attr_native_value = native_value
        self._attr_native_unit_of_measurement = native_unit

        if self._attr_native_unit_of_measurement in TEMPERATURE_UNITS:
            self._temperature_mode = True
            self._attr_device_class = SensorDeviceClass.TEMPERATURE

        if last_state is not None:
            self.available_sources = last_state.attributes.get(
                ATTR_AVAILABLE_SOURCES, self.count_sources
            )
            self.count = last_state.attributes.get(ATTR_COUNT, self.count)
            # Source count belongs to the current configuration, not restored data.
            # The old diagnostics may describe a different source list.
            self.min_value = last_state.attributes.get(ATTR_MIN_VALUE)
            self.max_value = last_state.attributes.get(ATTR_MAX_VALUE)
            self.trending_towards = last_state.attributes.get(ATTR_TRENDING_TOWARDS)
        else:
            self.available_sources = self.count_sources

        self.async_write_ha_state()

    @staticmethod
    def _has_state(state: Any) -> bool:
        """Return True if state has any value."""
        return state is not None and state not in [
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
            "None",
            "",
        ]

    @staticmethod
    def _is_temperature_device_class(device_class: Any) -> bool:
        """Return True if device class is temperature."""
        return device_class == SensorDeviceClass.TEMPERATURE

    def _get_temperature(
        self, state: State, *, log_errors: bool = True
    ) -> float | None:
        """Get temperature value from entity."""
        ha_unit = self.hass.config.units.temperature_unit
        domain = split_entity_id(state.entity_id)[0]
        if attribute := self._source_attributes.get(state.entity_id):
            temperature = state.attributes.get(attribute)
            source_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            entity_unit = (
                state.attributes.get(f"{attribute}_unit")
                or state.attributes.get("temperature_unit")
                or (source_unit if source_unit in TEMPERATURE_UNITS else ha_unit)
            )
        elif domain == WEATHER_DOMAIN:
            temperature = state.attributes.get("temperature")
            entity_unit = ha_unit
        elif domain in (CLIMATE_DOMAIN, WATER_HEATER_DOMAIN):
            temperature = state.attributes.get("current_temperature")
            entity_unit = ha_unit
        else:
            temperature = state.state
            # Without source metadata, retain the documented HA-unit assumption.
            entity_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or ha_unit

        if temperature is None or not self._has_state(temperature):
            return None

        try:
            temperature = TemperatureConverter.convert(
                float(temperature), entity_unit, ha_unit
            )
        except HomeAssistantError, TypeError, ValueError:
            if not log_errors:
                return None
            failures = self._temperature_conversion_errors.get(state.entity_id, 0) + 1
            self._temperature_conversion_errors[state.entity_id] = failures
            signature = (repr(temperature), str(entity_unit))
            if (
                failures == 1
                and self._temperature_failure_signatures.get(state.entity_id)
                != signature
            ):
                self._temperature_failure_signatures[state.entity_id] = signature
                _LOGGER.exception(
                    'Could not convert temperature for "%s"; further conversion '
                    "errors for this source are summarized for this calculation",
                    state.entity_id,
                )
            return None

        if log_errors:
            self._temperature_failure_signatures.pop(state.entity_id, None)
        return temperature

    def _uses_attribute_value(self, entity_id: str) -> bool:
        """Identify readings that can change without changing the entity state."""
        return bool(self._source_attributes.get(entity_id)) or split_entity_id(
            entity_id
        )[0] in (WEATHER_DOMAIN, CLIMATE_DOMAIN, WATER_HEATER_DOMAIN)

    def _get_source_value(self, state: State, *, log_errors: bool = True) -> Any:
        """Read a selected attribute, or preserve the default state/temperature path."""
        if not self._has_state(state.state):
            return None
        if attribute := self._source_attributes.get(state.entity_id):
            if attribute in (
                "temperature",
                "current_temperature",
                "dew_point",
                "apparent_temperature",
            ):
                return self._get_temperature(state, log_errors=log_errors)
            return state.attributes.get(attribute)
        return (
            self._get_temperature(state, log_errors=log_errors)
            if self._temperature_mode
            else state.state
        )

    def _get_state_value(
        self, state: State, *, uses_attributes: bool | None = None
    ) -> float | None:
        """Return value of given entity state and count some sensor attributes."""
        if uses_attributes is None:
            uses_attributes = self._uses_attribute_value(state.entity_id)
        state_dt_changed = state.last_updated if uses_attributes else state.last_changed
        raw_value = self._get_source_value(state)
        if not self._has_state(raw_value):
            raw_value = self._undef
        if raw_value is None:
            return None

        try:
            value = float(raw_value)
        except TypeError, ValueError:
            _LOGGER.debug('Ignoring nonnumeric source value "%s"', raw_value)
            return None
        if not math.isfinite(value):
            return None

        self.count += 1
        rstate = round(value, self._precision)
        if self.min_value is None:
            self.min_value = self.max_value = rstate
            if self._period:
                self.min_datetime = self.max_datetime = state_dt_changed
        else:
            if rstate < self.min_value:
                self.min_value = rstate
                if self._period:
                    self.min_datetime = state_dt_changed
            if self.max_value is None or rstate > self.max_value:
                self.max_value = rstate
                if self._period:
                    self.max_datetime = state_dt_changed
        return value

    def _is_source_stale(self, state: State, now: datetime) -> bool:
        """Return True if a source state is older than the configured age limit."""
        if self._max_source_age is None:
            return False

        source_age = now - state.last_updated
        if source_age <= self._max_source_age:
            return False

        _LOGGER.debug(
            'Skipping stale source entity "%s"; last updated %s ago',
            state.entity_id,
            source_age,
        )
        return True

    @property
    def _history_query_pending(self) -> bool:
        """Include an earlier entity instance's SQL job during an entry reload."""
        if (
            self._pending_history_query is not None
            and not self._pending_history_query.done()
        ):
            return True
        shared = self.hass.data.get(DATA_PENDING_HISTORY, {}).get(self._entry_id)
        return shared is not None and not shared.done()

    def _updates_blocked(self) -> bool:
        """Keep pending SQL and stopped entities from starting new calculations."""
        if self._stopping or self.hass.is_stopping:
            return True
        if self._history_query_pending:
            self._clear_history_result()
            return True
        return False

    async def async_update(self) -> None:
        """Update the sensor state if it needed."""
        if self._update_in_progress or self._updates_blocked():
            return

        if not self._has_period:
            if self._max_source_age is not None:
                self._update_state_no_period()
            return

        now = dt_util.utcnow()
        if (
            self._last_update is not None
            and now - self._last_update < self._update_interval
        ):
            return

        self._last_update = now
        self._update_in_progress = True
        try:
            await self._async_update_state()
        except Exception, CancelledError:
            self._clear_history_result()
            raise
        finally:
            self._update_in_progress = False

    @staticmethod
    def handle_template_exception(exc: Exception, field: str) -> None:
        """Log an error nicely if the template cannot be interpreted."""
        if (
            exc.args
            and isinstance(exc.args[0], str)
            and exc.args[0].startswith("UndefinedError: 'None' has no attribute")
        ):
            # Common during HA startup - so just a warning
            _LOGGER.warning(exc)

        else:
            _LOGGER.error('Error parsing template for field "%s": %s', field, exc)

    def _report_period_boundary_error(self, value: Any, field: str) -> None:
        """Log once per invalid output until a valid boundary is observed."""
        signature = repr(value)
        if self._period_boundary_errors.get(field) != signature:
            self._period_boundary_errors[field] = signature
            _LOGGER.error(
                'Parsing error: field "%s" must be a datetime or a timestamp, '
                "not a boolean or malformed value",
                field,
            )

    def _parse_period_boundary(self, value: Any, field: str) -> datetime | None:
        """Parse a boundary without raising on sources missing during startup."""
        if isinstance(value, bool):
            self._report_period_boundary_error(value, field)
            return None
        if not self._has_state(value):
            _LOGGER.debug('Period boundary "%s" is not available yet', field)
            return None
        parsed = value if isinstance(value, datetime) else None
        if isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
        if parsed is None:
            with suppress(TypeError, ValueError, OverflowError, OSError):
                parsed = dt_util.utc_from_timestamp(float(value))
        if parsed is None:
            self._report_period_boundary_error(value, field)
            return None
        self._period_boundary_errors.pop(field, None)
        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=dt_util.get_time_zone(self.hass.config.time_zone)
            )
        return dt_util.as_local(parsed)

    async def _async_update_period(self) -> None:  # noqa: PLR0911, PLR0912
        """Parse the templates and calculate a datetime tuples."""
        self._period = self.start = self.end = self._actual_end = None
        start = end = None
        now = dt_util.now()

        # Parse start
        if self._start_template is not None:
            _LOGGER.debug("Processing start time template")
            try:
                start_rendered = self._start_template.async_render()
            except (TemplateError, TypeError) as ex:
                self.handle_template_exception(ex, "start")
                return
            start = self._parse_period_boundary(start_rendered, "start")
            if start is None:
                return

        # Parse end
        if self._end_template is not None:
            _LOGGER.debug("Processing end time template")
            try:
                end_rendered = self._end_template.async_render()
            except (TemplateError, TypeError) as ex:
                self.handle_template_exception(ex, "end")
                return
            end = self._parse_period_boundary(end_rendered, "end")
            if end is None:
                return

        # Calculate start or end using the duration
        if self._duration is not None:
            _LOGGER.debug("Process duration: %s", self._duration)
            if start is None:
                if end is None:
                    end = now
                start = end - self._duration
            else:
                end = start + self._duration

        _LOGGER.debug("Calculation period: start=%s, end=%s", start, end)
        if start is None or end is None:
            return

        if start > end:
            if not self._period_was_reversed:
                _LOGGER.warning(
                    'Start/end boundaries for "%s" are reversed; retaining '
                    "legacy boundary swapping. Correct the YAML/UI templates",
                    self.name,
                )
            self._period_was_reversed = True
            start, end = end, start
        else:
            self._period_was_reversed = False

        self._actual_end = end

        if start > now:
            # History hasn't been written yet for this period
            return
        end = min(end, now)  # No point in making stats of the future
        if end <= start:
            return

        if end - start > self._max_history_period:
            if not self._history_range_exceeded:
                _LOGGER.error(
                    'History window for "%s" exceeds max_history_period (%s); '
                    "no query was issued. Correct the period or explicitly "
                    "increase the YAML/UI limit",
                    self.name,
                    self._max_history_period,
                )
            self._history_range_exceeded = True
            return
        self._history_range_exceeded = False
        self._period = start, end
        self.start = start
        self.end = end

    def _source_is_temperature(self, state: State) -> bool:
        """Classify the selected reading rather than an unrelated entity attribute."""
        if attribute := self._source_attributes.get(state.entity_id):
            return attribute in (
                "temperature",
                "current_temperature",
                "dew_point",
                "apparent_temperature",
            )
        return (
            self._is_temperature_device_class(state.attributes.get(ATTR_DEVICE_CLASS))
            or split_entity_id(state.entity_id)[0]
            in (WEATHER_DOMAIN, CLIMATE_DOMAIN, WATER_HEATER_DOMAIN)
            or state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) in TEMPERATURE_UNITS
        )

    def _prepare_source_mode(self) -> None:
        """Choose fresh, deterministic metadata before consuming any readings."""
        self._temperature_mode = None
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_icon = None
        states = [
            state
            for entity_id in self.sources
            if (state := self.hass.states.get(entity_id)) is not None
        ]
        # Explicit attributes take precedence over default metadata; temperature
        # takes precedence over unitless sources. Never depend on YAML/UI ordering.
        for state in sorted(
            states,
            key=lambda state: (
                self._source_is_temperature(state),
                bool(self._source_attributes.get(state.entity_id)),
                state.entity_id,
            ),
        ):
            self._init_mode(state)

    def _init_mode(self, state: State) -> None:
        """Initialize sensor mode."""
        if attribute := self._source_attributes.get(state.entity_id):
            self._temperature_mode = attribute in (
                "temperature",
                "current_temperature",
                "dew_point",
                "apparent_temperature",
            )
            if self._temperature_mode:
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
                self._attr_native_unit_of_measurement = (
                    self.hass.config.units.temperature_unit
                )
            elif attribute in ("humidity", "current_humidity"):
                self._attr_device_class = SensorDeviceClass.HUMIDITY
                self._attr_native_unit_of_measurement = "%"
            elif attribute == "pressure":
                self._attr_device_class = SensorDeviceClass.PRESSURE
                self._attr_native_unit_of_measurement = state.attributes.get(
                    "pressure_unit"
                )
            elif attribute == "wind_speed":
                self._attr_device_class = SensorDeviceClass.WIND_SPEED
                self._attr_native_unit_of_measurement = state.attributes.get(
                    "wind_speed_unit"
                )
            else:
                self._attr_device_class = None
                self._attr_native_unit_of_measurement = state.attributes.get(
                    f"{attribute}_unit"
                )
            self._attr_icon = None
            return
        if self._temperature_mode is True:
            self._attr_native_unit_of_measurement = (
                self.hass.config.units.temperature_unit
            )
            return

        domain = split_entity_id(state.entity_id)[0]
        device_class = state.attributes.get(ATTR_DEVICE_CLASS)
        unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        temperature_mode = (
            self._is_temperature_device_class(device_class)
            or domain in (WEATHER_DOMAIN, CLIMATE_DOMAIN, WATER_HEATER_DOMAIN)
            or unit_of_measurement in TEMPERATURE_UNITS
        )

        if self._temperature_mode is False and not temperature_mode:
            if (
                self._attr_native_unit_of_measurement is None
                and unit_of_measurement is not None
            ):
                self._attr_native_unit_of_measurement = unit_of_measurement
            if self._attr_device_class is None and device_class is not None:
                self._attr_device_class = device_class
            return

        self._temperature_mode = temperature_mode
        if temperature_mode:
            _LOGGER.debug("%s is a temperature entity.", state.entity_id)
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = (
                self.hass.config.units.temperature_unit
            )
        else:
            _LOGGER.debug("%s is NOT a temperature entity.", state.entity_id)
            self._attr_device_class = device_class
            self._attr_native_unit_of_measurement = unit_of_measurement
            self._attr_icon = state.attributes.get(ATTR_ICON)

    async def _async_query_history(
        self, start: datetime, end: datetime, entity_id: str, *, uses_attributes: bool
    ) -> dict[str, list[State]]:
        """Keep a cancelled refresh from queuing work over a still-running query."""
        query = partial(
            _materialized_history,
            uses_attributes=uses_attributes,
            needs_attributes=uses_attributes or bool(self._temperature_mode),
        )
        try:
            recorder = get_instance(self.hass)
        except KeyError as err:
            if not self._recorder_unavailable:
                _LOGGER.warning(
                    'Recorder is unavailable for "%s"; history averaging will '
                    "retry when Recorder is ready",
                    self.name,
                )
            self._recorder_unavailable = True
            raise HistoryQueryError from err
        self._recorder_unavailable = False
        pending = ensure_future(
            recorder.async_add_executor_job(query, self.hass, start, end, entity_id)
        )
        self._pending_history_query = pending
        shared = self.hass.data.setdefault(DATA_PENDING_HISTORY, {})
        if self._entry_id is not None:
            shared[self._entry_id] = pending

        timeout_reported = False

        @callback
        def warn_pending_query() -> None:
            nonlocal timeout_reported
            if timeout_reported or pending.done():
                return
            timeout_reported = True
            _LOGGER.warning(
                'Recorder query for "%s" timed out after %s; the sensor is '
                "unavailable until SQL finishes. No replacement query will overlap it",
                entity_id,
                self._history_query_timeout,
            )

        # Keep the deadline observable even if a reload cancels the waiter.
        timeout_handle = self.hass.loop.call_later(
            self._history_query_timeout.total_seconds(), warn_pending_query
        )

        @callback
        def query_done(future: Future) -> None:
            timeout_handle.cancel()
            if self._pending_history_query is future:
                self._pending_history_query = None
            if self._entry_id is not None and shared.get(self._entry_id) is future:
                del shared[self._entry_id]

        @callback
        def abandoned_query_done(future: Future) -> None:
            if not future.cancelled() and (error := future.exception()) is not None:
                _LOGGER.error(
                    "Recorder query failed after its refresh ended",
                    exc_info=(type(error), error, error.__traceback__),
                )

        pending.add_done_callback(query_done)
        query_timeout = timeout(self._history_query_timeout.total_seconds())
        try:
            # Cancelling an asyncio Future cannot stop an executing SQL query.
            # Retain its real completion state so the next poll cannot overlap it.
            async with query_timeout:
                return await shield(pending)
        except TimeoutError as err:
            if not query_timeout.expired():
                raise
            pending.add_done_callback(abandoned_query_done)
            warn_pending_query()
            raise HistoryQueryError from err
        except CancelledError:
            pending.add_done_callback(abandoned_query_done)
            raise

    async def _async_history_for_source(
        self, start: datetime, end: datetime, entity_id: str, *, uses_attributes: bool
    ) -> dict[str, list[State]] | None:
        """Discard partial results on a failed or cancelled refresh."""
        try:
            return await self._async_query_history(
                start, end, entity_id, uses_attributes=uses_attributes
            )
        except HistoryQueryError:
            self._clear_history_result()
            return None
        except CancelledError:
            self._clear_history_result()
            raise

    def _clear_history_result(self) -> None:
        """Never publish a stale value with partial diagnostics after a failure."""
        self._attr_native_value = None
        self.available_sources = self.count = 0
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = self.trending_towards = None
        self._history_complete = False
        self._last_history_metadata = None
        self._last_update = None

    def _cancel_refresh_waiters(self) -> set[Task[Any]]:
        """Release our refresh tasks on STOP/unload while SQL keeps its guard."""
        tasks = {
            task
            for task in self._refresh_tasks
            if not task.done() and task is not current_task()
        }
        for task in tasks:
            task.cancel()
        return tasks

    async def async_will_remove_from_hass(self) -> None:
        """Cancel refresh waiters on unload without cancelling their SQL jobs."""
        self._stopping = True
        tasks = self._cancel_refresh_waiters()
        if tasks:
            await wait(tasks, timeout=1)
        await super().async_will_remove_from_hass()

    async def _async_update_state(self) -> None:
        """Track refresh ownership and discard partial data on every failure."""
        task = current_task()
        if task is not None:
            self._refresh_tasks.add(task)
        try:
            await self._async_compute_average()
        except Exception, CancelledError:
            self._clear_history_result()
            raise
        finally:
            if task is not None:
                self._refresh_tasks.discard(task)

    async def _async_compute_average(self) -> None:  # noqa: PLR0911, PLR0912, PLR0915
        """Update the sensor state."""
        if self._updates_blocked():
            return
        _LOGGER.debug('Updating sensor "%s"', self.name)
        self._temperature_conversion_errors.clear()
        p_period = self._period

        # Parse templates
        await self._async_update_period()
        if self._stopping or self.hass.is_stopping:
            return

        if self._period is None:
            if self._has_period:
                self._clear_history_result()
            else:
                self._update_state_no_period()
            return

        self._prepare_source_mode()
        now = dt_util.now()
        start, end = self._period
        if p_period is None:
            p_start = p_end = now
        else:
            p_start, p_end = p_period

        # Convert times to UTC
        now = dt_util.as_utc(now)
        start = dt_util.as_utc(start)
        end = dt_util.as_utc(end)
        actual_end = dt_util.as_utc(self._actual_end or end)
        p_start = dt_util.as_utc(p_start)
        p_end = dt_util.as_utc(p_end)

        # Keep full timestamp precision, including sub-second history windows.
        now_ts = dt_util.as_timestamp(now)
        start_ts = dt_util.as_timestamp(start)
        end_ts = dt_util.as_timestamp(end)
        actual_end_ts = dt_util.as_timestamp(actual_end)
        p_start_ts = dt_util.as_timestamp(p_start)
        p_end_ts = dt_util.as_timestamp(p_end)

        metadata = self._history_metadata_signature()
        # A closed period can be cached only after a complete calculation.
        if (
            start_ts == p_start_ts
            and end_ts == p_end_ts
            and end_ts <= now_ts
            and self._history_complete
            and metadata == self._last_history_metadata
        ):
            # Reuse completed history until source metadata changes.
            return

        self._history_complete = False
        self._last_history_metadata = metadata
        self.available_sources = 0
        self.count = 0
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None
        self.trending_towards = None
        #
        values: list[tuple[float, float]] = []
        last_values: list[tuple[float, float]] = []
        history_complete = True

        # pylint: disable=too-many-nested-blocks
        for entity_id in self.sources:
            # A previous query/batch may have yielded through STOP or a reload.
            if self._updates_blocked():
                return
            _LOGGER.debug('Processing entity "%s"', entity_id)

            state = self.hass.states.get(entity_id)

            if state is None:
                _LOGGER.debug('Unable to find an entity "%s"', entity_id)
                history_complete = False
                continue
            if self._is_source_stale(state, now):
                history_complete = False
                continue

            value: float | None = 0.0
            elapsed = 0.0
            trending_last_state = None

            # Get history between start and now
            uses_attributes = self._uses_attribute_value(entity_id)
            history_list = await self._async_history_for_source(
                start, end, entity_id, uses_attributes=uses_attributes
            )
            if history_list is None:
                return

            if self._stopping or self.hass.is_stopping:
                return

            if (
                entity_id not in history_list
                or history_list[entity_id] is None
                or len(history_list[entity_id]) == 0
            ):
                history_complete = False
                value = self._get_state_value(state)
                if entity_id not in self._empty_history_sources:
                    _LOGGER.warning(
                        'Historical data not found for entity "%s". '
                        "Current state used: %s",
                        entity_id,
                        value,
                    )
                self._empty_history_sources.add(entity_id)
            else:
                self._empty_history_sources.discard(entity_id)
                integral = 0.0
                # Get the first state
                item = history_list[entity_id][0]
                _LOGGER.debug("Initial historical record for %s", entity_id)
                last_state = None
                last_time = start_ts
                if item is not None and self._has_state(item.state):
                    last_state = self._get_state_value(
                        item, uses_attributes=uses_attributes
                    )

                # Get the other states
                for index, item in enumerate(history_list[entity_id]):
                    if index and index % HISTORY_PROCESSING_BATCH_SIZE == 0:
                        # Keep HA state events and STOP callbacks responsive.
                        await sleep(0)
                        if self._stopping or self.hass.is_stopping:
                            return
                    _LOGGER.debug("Historical record for %s", entity_id)
                    current_state = self._get_state_value(
                        item, uses_attributes=uses_attributes
                    )
                    current_time = (
                        item.last_updated if uses_attributes else item.last_changed
                    ).timestamp()
                    current_time = min(end_ts, max(start_ts, current_time))

                    if last_state is not None:
                        last_elapsed = current_time - last_time
                        integral += last_state * last_elapsed
                        elapsed += last_elapsed

                    if current_state is not None or not self._calculate_to_now_undef:
                        last_state = current_state
                    last_time = current_time

                # Count time elapsed between last history state and now
                if last_state is None:
                    value = (
                        integral / elapsed
                        if self._ignore_undef and elapsed > 0
                        else None
                    )
                else:
                    last_elapsed = end_ts - last_time
                    integral += last_state * last_elapsed
                    elapsed += last_elapsed
                    value = integral / elapsed if elapsed > 0 else None
                    trending_last_state = last_state

                _LOGGER.debug("Historical average state: %s", value)

            # Do not retain this large result while the next source loads.
            del history_list

            if isinstance(value, numbers.Number):
                values.append((value, self._weights.get(entity_id, 1)))
                self.available_sources += 1

            if isinstance(trending_last_state, numbers.Number):
                last_values.append(
                    (trending_last_state, self._weights.get(entity_id, 1))
                )

        self._log_temperature_conversion_errors()
        self._attr_native_value = self._weighted_average(values)
        self._history_complete = (
            history_complete
            and self.available_sources == self.count_sources
            and self._attr_native_value is not None
        )

        current_average = self._weighted_average(last_values)
        if (
            current_average is not None
            and self._attr_native_value is not None
            and actual_end_ts > start_ts
        ):
            part_of_period = min(
                1, max(0, (now_ts - start_ts) / (actual_end_ts - start_ts))
            )
            to_now = self._attr_native_value * part_of_period
            to_end = current_average * (1 - part_of_period)
            self.trending_towards = self._weighted_average([(to_now + to_end, 1)])

        _LOGGER.debug(
            "Total average state: %s %s",
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
        )
        _LOGGER.debug(
            "Current trend: %s %s",
            self.trending_towards,
            self._attr_native_unit_of_measurement,
        )

    def _history_metadata_signature(self) -> tuple[tuple[Any, ...], ...]:
        """Detect source metadata and freshness changes before reusing history."""
        signature: list[tuple[Any, ...]] = [(self.hass.config.units.temperature_unit,)]
        now = dt_util.utcnow()
        keys = (
            ATTR_DEVICE_CLASS,
            ATTR_UNIT_OF_MEASUREMENT,
            "temperature_unit",
            "pressure_unit",
            "wind_speed_unit",
        )
        for entity_id in self.sources:
            state = self.hass.states.get(entity_id)
            if state is None:
                signature.append((entity_id, None))
                continue
            attribute = self._source_attributes.get(entity_id)
            signature.append(
                (
                    entity_id,
                    self._is_source_stale(state, now),
                    *(state.attributes.get(key) for key in keys),
                    state.attributes.get(f"{attribute}_unit") if attribute else None,
                )
            )
        return tuple(signature)

    def _weighted_average(self, values: list[tuple[float, float]]) -> float | None:
        """Combine source values, preserving equal weighting when unconfigured."""
        if not values or any(
            not math.isfinite(value) or not math.isfinite(weight) or weight < 0
            for value, weight in values
        ):
            return None
        if not (scale := max(weight for _, weight in values)):
            return None
        total_weight = sum(weight / scale for _, weight in values)
        # Normalize before multiplication/summing so finite large sources do not
        # overflow merely because multiple sources contribute to the mean.
        average = sum(
            value * ((weight / scale) / total_weight) for value, weight in values
        )
        if not math.isfinite(average):
            return None
        average = round(average, self._precision)
        return int(average) if self._precision < 1 else average

    def _log_temperature_conversion_errors(self) -> None:
        """Report repeated failures once per source, rather than per history point."""
        for entity_id, failures in self._temperature_conversion_errors.items():
            if failures > 1:
                _LOGGER.warning(
                    'Temperature conversion failed %s times for "%s" during this '
                    "calculation; see its first conversion error for details",
                    failures,
                    entity_id,
                )

    def _update_state_no_period(self) -> None:
        """Update the sensor state then period is not set."""
        self._temperature_conversion_errors.clear()
        self._prepare_source_mode()
        self.available_sources = 0
        values: list[tuple[float, float]] = []
        self.count = 0
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None
        self.trending_towards = None
        now = dt_util.utcnow()

        # pylint: disable=too-many-nested-blocks
        for entity_id in self.sources:
            _LOGGER.debug('Processing entity "%s"', entity_id)

            state = self.hass.states.get(entity_id)

            if state is None:
                _LOGGER.debug('Unable to find an entity "%s"', entity_id)
                continue
            if self._is_source_stale(state, now):
                continue

            # Get current state
            value = self._get_state_value(state)
            _LOGGER.debug("Current state: %s", value)

            if isinstance(value, numbers.Number):
                values.append((value, self._weights.get(entity_id, 1)))
                self.available_sources += 1

        self._attr_native_value = self._weighted_average(values)
        self._log_temperature_conversion_errors()

        _LOGGER.debug(
            "Total average state: %s %s",
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
        )
