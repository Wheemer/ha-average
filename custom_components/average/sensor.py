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
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import (
        AddConfigEntryEntitiesCallback,
        AddEntitiesCallback,
    )
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from _sha1 import sha1

import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.recorder import get_instance, history
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
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
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.group import expand_entity_ids
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.template import Template
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.util.unit_system import TEMPERATURE_UNITS

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
    CONF_DURATION,
    CONF_END,
    CONF_MAX_SOURCE_AGE,
    CONF_PERIOD_KEYS,
    CONF_PRECISION,
    CONF_PROCESS_UNDEF_AS,
    CONF_START,
    DEFAULT_NAME,
    DEFAULT_PRECISION,
    DOMAIN,
    UPDATE_MIN_TIME,
)

_LOGGER = logging.getLogger(__name__)
YAML_IMPORT_ISSUE_ID = "yaml_imported"


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
    return conf


PLATFORM_SCHEMA = vol.All(
    PLATFORM_SCHEMA.extend(
        {
            vol.Required(CONF_ENTITIES): cv.entity_ids,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            vol.Optional(CONF_START): cv.template,
            vol.Optional(CONF_END): cv.template,
            vol.Optional(CONF_DURATION): cv.positive_time_period,
            vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): int,
            vol.Optional(CONF_PROCESS_UNDEF_AS): vol.Any(int, float),
            vol.Optional(CONF_MAX_SOURCE_AGE): cv.positive_time_period,
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
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=config,
    )
    async_create_issue(
        hass,
        DOMAIN,
        YAML_IMPORT_ISSUE_ID,
        is_fixable=False,
        is_persistent=True,
        severity=IssueSeverity.WARNING,
        translation_key="yaml_imported",
        translation_placeholders={"name": "Average Sensor YAML configuration"},
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
    return value


def _entry_unique_id(
    hass: HomeAssistant, options: Mapping[str, Any], entry_id: str
) -> str:
    """Return the sensor unique ID for a config entry."""
    if unique_id := options.get(CONF_UNIQUE_ID):
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
    }

    for key in (CONF_START, CONF_END):
        value = options.get(key)
        if value:
            config[key] = Template(value, hass)

    for key in (CONF_DURATION, CONF_MAX_SOURCE_AGE, CONF_SCAN_INTERVAL):
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
    async_add_entities([AverageSensor(hass, _entry_config(hass, config_entry))])


# pylint: disable=too-many-instance-attributes
class AverageSensor(SensorEntity):
    """Implementation of an Average sensor."""

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
    def __init__(self, hass: HomeAssistant, config: ConfigType) -> None:
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
        self._period = self.start = self.end = None
        self._precision = config.get(CONF_PRECISION, DEFAULT_PRECISION)
        self._undef = config.get(CONF_PROCESS_UNDEF_AS)
        self._max_source_age = config.get(CONF_MAX_SOURCE_AGE)
        self._update_interval = config.get(CONF_SCAN_INTERVAL, UPDATE_MIN_TIME)
        self._last_update = None
        self._temperature_mode = None
        self._actual_end = None

        self.hass = hass
        self.sources = expand_entity_ids(hass, config.get(CONF_ENTITIES, []))
        self.count_sources = len(self.sources)
        self.available_sources = 0
        self.count = 0
        self.trending_towards = None
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None

        self._attr_name = config.get(CONF_NAME, DEFAULT_NAME)
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = None
        self._attr_icon = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = None
        #
        self._attr_unique_id = (
            str(
                sha1(
                    ";".join(
                        [str(start), str(duration), str(end), ",".join(self.sources)]
                    ).encode("utf-8")
                ).hexdigest()
            )
            if unique_id == "__legacy__"
            else unique_id
        )

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
        return self._has_period

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.available_sources > 0 and self._has_state(self._attr_native_value)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            attr: getattr(self, attr)
            for attr in ATTR_TO_PROPERTY
            if getattr(self, attr) is not None
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        startup_fired = False

        # pylint: disable=unused-argument
        @callback
        async def async_sensor_state_listener(event: Event) -> None:  # noqa: ARG001
            """Handle device state changes."""
            last_state = self._attr_native_value
            await self._async_update_state()
            if last_state != self._attr_native_value:
                self.async_schedule_update_ha_state(force_refresh=True)

        # pylint: disable=unused-argument
        @callback
        async def async_sensor_startup(event: Event) -> None:  # noqa: ARG001
            """Update template on startup."""
            nonlocal startup_fired
            startup_fired = True

            if self._has_period:
                self.async_schedule_update_ha_state(force_refresh=True)
            else:
                self.async_on_remove(
                    async_track_state_change_event(
                        self.hass, self.sources, async_sensor_state_listener
                    )
                )
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

    @staticmethod
    def _has_state(state: str | None) -> bool:
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

    def _get_temperature(self, state: State) -> float | None:
        """Get temperature value from entity."""
        ha_unit = self.hass.config.units.temperature_unit
        domain = split_entity_id(state.entity_id)[0]
        if domain == WEATHER_DOMAIN:
            temperature = state.attributes.get("temperature")
            entity_unit = ha_unit
        elif domain in (CLIMATE_DOMAIN, WATER_HEATER_DOMAIN):
            temperature = state.attributes.get("current_temperature")
            entity_unit = ha_unit
        else:
            temperature = state.state
            entity_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if entity_unit is None and self._is_temperature_device_class(
                state.attributes.get(ATTR_DEVICE_CLASS)
            ):
                entity_unit = ha_unit

        if not self._has_state(temperature):
            return None

        try:
            temperature = TemperatureConverter.convert(
                float(temperature), entity_unit, ha_unit
            )
        except (HomeAssistantError, ValueError):
            _LOGGER.exception('Could not convert value "%s" to float', state)
            return None

        return temperature

    def _get_state_value(self, state: State) -> float | None:
        """Return value of given entity state and count some sensor attributes."""
        state_dt_changed = state.last_changed
        state = self._get_temperature(state) if self._temperature_mode else state.state
        if not self._has_state(state):
            return self._undef

        try:
            state = float(state)
        except ValueError:
            _LOGGER.exception('Could not convert value "%s" to float', state)
            return None

        self.count += 1
        rstate = round(state, self._precision)
        if self.min_value is None:
            self.min_value = self.max_value = rstate
            if self._period:
                self.min_datetime = self.max_datetime = state_dt_changed
        else:
            if rstate < self.min_value:
                self.min_value = rstate
                if self._period:
                    self.min_datetime = state_dt_changed
            if rstate > self.max_value:
                self.max_value = rstate
                if self._period:
                    self.max_datetime = state_dt_changed
        return state

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

    async def async_update(self) -> None:
        """Update the sensor state if it needed."""
        if not self._has_period:
            return

        now = dt_util.utcnow()
        if (
            self._last_update is not None
            and now - self._last_update < self._update_interval
        ):
            return

        self._last_update = now
        await self._async_update_state()

    @staticmethod
    def handle_template_exception(exc: Exception, field: str) -> None:
        """Log an error nicely if the template cannot be interpreted."""
        if exc.args and exc.args[0].startswith(
            "UndefinedError: 'None' has no attribute"
        ):
            # Common during HA startup - so just a warning
            _LOGGER.warning(exc)

        else:
            _LOGGER.error('Error parsing template for field "%s": %s', field, exc)

    async def _async_update_period(self) -> None:  # noqa: PLR0912
        """Parse the templates and calculate a datetime tuples."""
        start = end = None
        now = dt_util.now()

        # Parse start
        if self._start_template is not None:
            _LOGGER.debug("Process start template: %s", self._start_template)
            try:
                start_rendered = self._start_template.async_render()
            except (TemplateError, TypeError) as ex:
                self.handle_template_exception(ex, "start")
                return
            if isinstance(start_rendered, str):
                start = dt_util.parse_datetime(start_rendered)
            if start is None:
                try:
                    start = dt_util.as_local(
                        dt_util.utc_from_timestamp(math.floor(float(start_rendered)))
                    )
                except ValueError:
                    _LOGGER.exception(
                        'Parsing error: field "start" must be a datetime or a timestamp'
                    )
                    return

        # Parse end
        if self._end_template is not None:
            _LOGGER.debug("Process end template: %s", self._end_template)
            try:
                end_rendered = self._end_template.async_render()
            except (TemplateError, TypeError) as ex:
                self.handle_template_exception(ex, "end")
                return
            if isinstance(end_rendered, str):
                end = dt_util.parse_datetime(end_rendered)
            if end is None:
                try:
                    end = dt_util.as_local(
                        dt_util.utc_from_timestamp(math.floor(float(end_rendered)))
                    )
                except ValueError:
                    _LOGGER.exception(
                        'Parsing error: field "end" must be a datetime or a timestamp'
                    )
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
            start, end = end, start

        self._actual_end = end

        if start > now:
            # History hasn't been written yet for this period
            return
        end = min(end, now)  # No point in making stats of the future

        self._period = start, end
        self.start = start
        self.end = end

    def _init_mode(self, state: State) -> None:
        """Initialize sensor mode."""
        if self._temperature_mode is True:
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

    async def _async_update_state(self) -> None:  # noqa: PLR0912, PLR0915
        """Update the sensor state."""
        _LOGGER.debug('Updating sensor "%s"', self.name)
        p_period = self._period

        # Parse templates
        await self._async_update_period()

        if self._period is None:
            self._update_state_no_period()
            return

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
        actual_end = dt_util.as_utc(self._actual_end)
        p_start = dt_util.as_utc(p_start)
        p_end = dt_util.as_utc(p_end)

        # Compute integer timestamps
        now_ts = math.floor(dt_util.as_timestamp(now))
        start_ts = math.floor(dt_util.as_timestamp(start))
        end_ts = math.floor(dt_util.as_timestamp(end))
        actual_end_ts = math.floor(dt_util.as_timestamp(actual_end))
        p_start_ts = math.floor(dt_util.as_timestamp(p_start))
        p_end_ts = math.floor(dt_util.as_timestamp(p_end))

        # If period has not changed and current time after the period end..
        if start_ts == p_start_ts and end_ts == p_end_ts and end_ts <= now_ts:
            # Don't compute anything as the value cannot have changed
            return

        self.available_sources = 0
        self.count = 0
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None
        self.trending_towards = None
        #
        values = []
        last_values = []

        # pylint: disable=too-many-nested-blocks
        for entity_id in self.sources:
            _LOGGER.debug('Processing entity "%s"', entity_id)

            state = self.hass.states.get(entity_id)  # type: State

            if state is None:
                _LOGGER.debug('Unable to find an entity "%s"', entity_id)
                continue
            if self._is_source_stale(state, now):
                continue

            self._init_mode(state)

            value = 0
            elapsed = 0
            trending_last_state = None

            # Get history between start and now
            history_list = await get_instance(self.hass).async_add_executor_job(
                history.state_changes_during_period,
                self.hass,
                start,
                end,
                str(entity_id),
            )

            if (
                entity_id not in history_list
                or history_list[entity_id] is None
                or len(history_list[entity_id]) == 0
            ):
                value = self._get_state_value(state)
                _LOGGER.warning(
                    'Historical data not found for entity "%s". Current state used: %s',
                    entity_id,
                    value,
                )
            else:
                # Get the first state
                item = history_list[entity_id][0]
                _LOGGER.debug("Initial historical state: %s", item)
                last_state = None
                last_time = start_ts
                if item is not None and self._has_state(item.state):
                    last_state = self._get_state_value(item)

                # Get the other states
                for item in history_list.get(entity_id):
                    _LOGGER.debug("Historical state: %s", item)
                    current_state = self._get_state_value(item)
                    current_time = item.last_changed.timestamp()

                    if last_state is not None:
                        last_elapsed = current_time - last_time
                        value += last_state * last_elapsed
                        elapsed += last_elapsed

                    last_state = current_state
                    last_time = current_time

                # Count time elapsed between last history state and now
                if last_state is None:
                    value = None
                else:
                    last_elapsed = end_ts - last_time
                    value += last_state * last_elapsed
                    elapsed += last_elapsed
                    if elapsed:
                        value /= elapsed
                    trending_last_state = last_state

                _LOGGER.debug("Historical average state: %s", value)

            if isinstance(value, numbers.Number):
                values.append(value)
                self.available_sources += 1

            if isinstance(trending_last_state, numbers.Number):
                last_values.append(trending_last_state)

        if values:
            self._attr_native_value = round(sum(values) / len(values), self._precision)
            if self._precision < 1:
                self._attr_native_value = int(self._attr_native_value)
        else:
            self._attr_native_value = None

        if last_values:
            current_average = round(
                sum(last_values) / len(last_values), self._precision
            )
            if self._precision < 1:
                current_average = int(current_average)
            part_of_period = (now_ts - start_ts) / (actual_end_ts - start_ts)
            to_now = self._attr_native_value * part_of_period
            to_end = current_average * (1 - part_of_period)
            self.trending_towards = to_now + to_end

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

    def _update_state_no_period(self) -> None:
        """Update the sensor state then period is not set."""
        self.available_sources = 0
        values = []
        self.count = 0
        self.min_value = self.max_value = None
        self.min_datetime = self.max_datetime = None
        self.trending_towards = None
        now = dt_util.utcnow()

        # pylint: disable=too-many-nested-blocks
        for entity_id in self.sources:
            _LOGGER.debug('Processing entity "%s"', entity_id)

            state = self.hass.states.get(entity_id)  # type: State

            if state is None:
                _LOGGER.debug('Unable to find an entity "%s"', entity_id)
                continue
            if self._is_source_stale(state, now):
                continue

            self._init_mode(state)

            # Get current state
            value = self._get_state_value(state)
            _LOGGER.debug("Current state: %s", value)

            if isinstance(value, numbers.Number):
                values.append(value)
                self.available_sources += 1

        if values:
            self._attr_native_value = round(sum(values) / len(values), self._precision)
            if self._precision < 1:
                self._attr_native_value = int(self._attr_native_value)
        else:
            self._attr_native_value = None

        _LOGGER.debug(
            "Total average state: %s %s",
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
        )
