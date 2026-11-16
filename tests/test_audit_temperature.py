"""Temperature calculations must be independent of source listing order."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("history", [False, True])
@pytest.mark.parametrize("attribute", [False, True])
async def test_temperature_mode_chosen_before_values(hass, reverse, history, attribute):
    """Unitless values use HA units consistently alongside temperature sources."""
    hass.states.async_set("sensor.unitless", "68")
    hass.states.async_set(
        "sensor.temperature",
        "20",
        {"unit_of_measurement": "°C", "temperature": 20, "temperature_unit": "°C"},
    )
    sources = ["sensor.unitless", "sensor.temperature"]
    if reverse:
        sources.reverse()
    config = {"entities": sources}
    if attribute:
        config["source_attributes"] = {"sensor.temperature": "temperature"}
    if history:
        config["duration"] = timedelta(seconds=30)
    sensor = AverageSensor(hass, config)
    start = dt_util.utcnow() - timedelta(seconds=30)
    rows = {
        entity_id: [
            State(
                entity_id,
                hass.states.get(entity_id).state,
                hass.states.get(entity_id).attributes,
                last_changed=start,
                last_updated=start,
            )
        ]
        for entity_id in sources
    }
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=rows))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == 44
    assert sensor.available_sources == 2
    assert sensor.native_unit_of_measurement == "°C"
    assert sensor.device_class == "temperature"


async def test_temperature_metadata_removal_matches_fresh_sensor(hass):
    """A previous calculation must not permanently latch temperature mode."""
    hass.states.async_set("sensor.source", "68", {"unit_of_measurement": "°F"})
    config = {"entities": ["sensor.source"]}
    sensor = AverageSensor(hass, config)
    await sensor._async_update_state()
    assert sensor.native_value == 20
    hass.states.async_set("sensor.source", "68")
    await sensor._async_update_state()
    fresh = AverageSensor(hass, config)
    await fresh._async_update_state()
    assert sensor.native_value == fresh.native_value == 68
    assert sensor.native_unit_of_measurement is fresh.native_unit_of_measurement is None
    assert sensor.device_class is fresh.device_class is None
