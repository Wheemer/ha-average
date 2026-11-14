"""Explicit source attributes preserve defaults, identity and availability."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.core import CoreState, State
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.util import dt as dt_util

from custom_components.average.config_flow import (
    OPTIONS_SCHEMA,
    _yaml_config_to_options,
    suggested_options,
    validate_options,
)
from custom_components.average.sensor import (
    PLATFORM_SCHEMA,
    AverageSensor,
    _entry_config,
)


@pytest.mark.parametrize("reverse", [False, True])
async def test_weather_humidity_combines_with_sensor_humidity(hass, reverse):
    """Upstream #56: humidity can be selected without changing unmapped sources."""
    hass.states.async_set("weather.home", "sunny", {"temperature": 10, "humidity": 60})
    hass.states.async_set(
        "sensor.humidity",
        "40",
        {"unit_of_measurement": "%", "device_class": "humidity"},
    )
    sources = ["weather.home", "sensor.humidity"]
    if reverse:
        sources.reverse()
    sensor = AverageSensor(
        hass,
        {
            "entities": sources,
            "unique_id": "stable",
            "source_attributes": {"weather.home": "humidity"},
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 50
    assert sensor.native_unit_of_measurement == "%"
    assert sensor.device_class == "humidity"
    assert sensor.unique_id == "stable"


async def test_unmapped_weather_keeps_temperature_default(hass):
    """Existing YAML and UI entries still read current weather temperature."""
    hass.states.async_set("weather.home", "sunny", {"temperature": 12, "humidity": 60})
    sensor = AverageSensor(hass, {"entities": ["weather.home"]})
    await sensor._async_update_state()
    assert sensor.native_value == 12
    assert sensor.native_unit_of_measurement == "°C"
    assert sensor.device_class == "temperature"


@pytest.mark.parametrize("value", [None, "nan", "inf", "bad", [], {}])
async def test_strict_selected_attribute_loss_and_recovery(hass, value):
    """Strict availability follows the chosen reading, not the entity's state label."""
    hass.states.async_set("weather.home", "sunny", {"temperature": 12, "humidity": 60})
    sensor = AverageSensor(
        hass,
        {
            "entities": ["weather.home"],
            "require_all_sources": True,
            "source_attributes": {"weather.home": "humidity"},
        },
    )
    await sensor._async_update_state()
    assert sensor.available
    attrs = {"temperature": 12}
    if value is not None:
        attrs["humidity"] = value
    hass.states.async_set("weather.home", "sunny", attrs)
    assert not sensor.available
    await sensor._async_update_state()
    assert not sensor.available
    hass.states.async_set("weather.home", "sunny", {"humidity": 70})
    await sensor._async_update_state()
    assert sensor.available
    assert sensor.native_value == 70


@pytest.mark.parametrize("selected", [False, True])
async def test_unavailable_weather_cannot_retain_valid_availability_from_attributes(
    hass, selected
):
    """Carried attributes do not make an unavailable required entity valid."""
    hass.states.async_set("weather.home", "sunny", {"temperature": 12, "humidity": 60})
    config = {"entities": ["weather.home"], "require_all_sources": True}
    if selected:
        config["source_attributes"] = {"weather.home": "humidity"}
    sensor = AverageSensor(hass, config)
    await sensor._async_update_state()
    assert sensor.available
    hass.states.async_set(
        "weather.home", "unavailable", {"temperature": 12, "humidity": 60}
    )
    assert not sensor.available
    await sensor._async_update_state()
    assert not sensor.available


async def test_attribute_history_is_time_weighted_and_supports_source_weights(hass):
    """History uses the selected attribute at each recorded state change."""
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=30)
    hass.states.async_set("weather.home", "sunny", {"humidity": 80})
    hass.states.async_set(
        "sensor.humidity",
        "20",
        {"unit_of_measurement": "%", "device_class": "humidity"},
    )
    sensor = AverageSensor(
        hass,
        {
            "entities": ["weather.home", "sensor.humidity"],
            "duration": timedelta(seconds=30),
            "weights": {"weather.home": 2},
            "source_attributes": {"weather.home": "humidity"},
        },
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    history = {
        "weather.home": [
            State(
                "weather.home",
                "sunny",
                {"humidity": 40},
                last_changed=start,
                last_updated=start,
            ),
            State(
                "weather.home",
                "cloudy",
                {"humidity": 80},
                last_changed=start + timedelta(seconds=15),
                last_updated=start + timedelta(seconds=15),
            ),
        ],
        "sensor.humidity": [
            State(
                "sensor.humidity",
                "20",
                {"unit_of_measurement": "%"},
                last_changed=start,
            )
        ],
    }
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=history))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == 46.67
    assert sensor.min_value == 20
    assert sensor.max_value == 80
    assert sensor.available_sources == 2


async def test_numeric_sensor_attribute_and_explicit_temperature_conversion(hass):
    """Attribute selection works for numeric entities and known temperatures."""
    hass.states.async_set(
        "sensor.custom", "999", {"tank_depth": 12, "tank_depth_unit": "cm"}
    )
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.custom"],
            "source_attributes": {"sensor.custom": "tank_depth"},
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 12
    assert sensor.native_unit_of_measurement == "cm"
    assert sensor.device_class is None
    hass.states.async_set(
        "weather.home", "sunny", {"temperature": 68, "temperature_unit": "°F"}
    )
    sensor = AverageSensor(
        hass,
        {
            "entities": ["weather.home"],
            "source_attributes": {"weather.home": "temperature"},
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 20
    assert sensor.native_unit_of_measurement == "°C"


async def test_attribute_mapping_roundtrip_and_clear_in_ui(hass):
    """YAML-imported mappings remain flat and editable without identity changes."""
    old = _yaml_config_to_options(
        {
            "name": "Humidity",
            "unique_id": "stable",
            "entities": ["weather.home"],
            "source_attributes": {"weather.home": "humidity"},
        }
    )
    handler = SimpleNamespace(options=dict(old))
    form = await suggested_options(handler)
    form.pop("name")
    form.pop("unique_id")
    saved = await validate_options(handler, OPTIONS_SCHEMA(form))
    runtime = _entry_config(
        hass, SimpleNamespace(data={}, options={**old, **saved}, entry_id="same")
    )
    assert runtime["source_attributes"] == old["source_attributes"]
    assert runtime["unique_id"] == "stable"
    cleared = await validate_options(
        SimpleNamespace(options=dict(old)),
        {"entities": old["entities"], "advanced": {"source_attributes": {}}},
    )
    assert cleared["source_attributes"] == {}


@pytest.mark.parametrize(
    "mapping",
    [
        None,
        [],
        {"weather.other": "humidity"},
        {"weather.home": ""},
        {"weather.home": "   "},
        {"weather.home": 1},
    ],
)
async def test_invalid_attribute_mapping_rejected_by_yaml_and_ui(mapping):
    """Unknown sources and empty or nonstring attribute names fail validation."""
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(
            {
                "platform": "average",
                "entities": ["weather.home"],
                "source_attributes": mapping,
            }
        )
    with pytest.raises(SchemaFlowError):
        await validate_options(
            SimpleNamespace(options={}),
            {"entities": ["weather.home"], "advanced": {"source_attributes": mapping}},
        )


async def test_attribute_only_events_invalidate_strict_history_and_recover(
    hass, freezer
):
    """An unchanged weather condition still emits usable attribute-only updates."""
    hass.set_state(CoreState.running)
    hass.states.async_set("weather.home", "sunny", {"humidity": 60})
    sensor = AverageSensor(
        hass,
        {
            "entities": ["weather.home"],
            "duration": timedelta(minutes=5),
            "require_all_sources": True,
            "source_attributes": {"weather.home": "humidity"},
        },
    )
    sensor._async_restore_previous_state = AsyncMock()
    sensor.async_schedule_update_ha_state = Mock()
    observed = []
    sensor.async_write_ha_state = lambda: observed.append(sensor.available)
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_added_to_hass()
        await sensor._async_update_state()
        assert sensor.available
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set("weather.home", "sunny", {"temperature": 12})
        await hass.async_block_till_done()
        assert observed
        assert observed[0] is False
        assert not sensor.available
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set("weather.home", "sunny", {"humidity": 70})
        await hass.async_block_till_done()
        assert sensor.available
        assert sensor.native_value == 70
    await sensor.async_will_remove_from_hass()


async def test_late_non_temperature_metadata_recovers_without_reload(hass):
    """A numeric source can publish its unit after its first startup reading."""
    hass.states.async_set("sensor.humidity", "40")
    sensor = AverageSensor(hass, {"entities": ["sensor.humidity"]})
    await sensor._async_update_state()
    assert sensor.native_unit_of_measurement is None
    hass.states.async_set("sensor.humidity", "42", {"unit_of_measurement": "%"})
    await sensor._async_update_state()
    assert sensor.native_unit_of_measurement == "%"
    assert sensor.device_class is None
    hass.states.async_set(
        "sensor.humidity",
        "45",
        {"unit_of_measurement": "%", "device_class": "humidity"},
    )
    await sensor._async_update_state()
    assert sensor.device_class == "humidity"
    assert sensor.native_value == 45


@pytest.mark.parametrize(
    "case",
    [
        (
            "weather.home",
            "sunny",
            {"pressure": 1013, "pressure_unit": "hPa"},
            "pressure",
            1013,
            "hPa",
            "pressure",
        ),
        (
            "weather.home",
            "sunny",
            {"wind_speed": 12, "wind_speed_unit": "km/h"},
            "wind_speed",
            12,
            "km/h",
            "wind_speed",
        ),
        (
            "climate.room",
            "heat",
            {"current_humidity": 45},
            "current_humidity",
            45,
            "%",
            "humidity",
        ),
        ("sensor.custom", "0", {"level": 2}, "level", 2, None, None),
        (
            "sensor.custom",
            "0",
            {"temperature": 68, "unit_of_measurement": "°F"},
            "temperature",
            20,
            "°C",
            "temperature",
        ),
    ],
)
async def test_selected_attribute_metadata(hass, case):
    """Selected attributes must not inherit an unrelated entity's temperature type."""
    entity_id, state, attributes, attribute, expected, unit, device_class = case
    hass.states.async_set(entity_id, state, attributes)
    sensor = AverageSensor(
        hass, {"entities": [entity_id], "source_attributes": {entity_id: attribute}}
    )
    await sensor._async_update_state()
    assert sensor.native_value == expected
    assert sensor.native_unit_of_measurement == unit
    assert sensor.device_class == device_class
