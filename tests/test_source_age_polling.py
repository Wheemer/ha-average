"""Configured source-age limits must affect published instantaneous readings."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize("strict", [False, True])
async def test_instantaneous_source_age_is_polled_and_recovers(hass, freezer, strict):
    """Quiet sources expire without waiting for a source-change event."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "20")
    hass.states.async_set("sensor.b", "40")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "max_source_age": timedelta(seconds=60),
            "require_all_sources": strict,
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 30
    assert sensor.available
    assert sensor.should_poll
    freezer.tick(timedelta(seconds=80))
    hass.states.async_set("sensor.a", "21")
    await sensor.async_update()
    assert sensor.native_value == 21
    assert sensor.available_sources == 1
    assert sensor.available is not strict
    hass.states.async_set("sensor.b", "41")
    await sensor.async_update()
    assert sensor.available
    assert sensor.native_value == 31
    freezer.tick(timedelta(seconds=80))
    await sensor.async_update()
    assert not sensor.available
    assert sensor.native_value is None


async def test_completed_partial_history_cache_respects_source_expiry(hass, freezer):
    """A cached closed-window mean cannot keep an expired source contributing."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "20")
    hass.states.async_set("sensor.b", "40")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "duration": timedelta(hours=1),
            "max_source_age": timedelta(seconds=60),
            "end": Template(
                "{{ now().replace(minute=0, second=0, microsecond=0) }}", hass
            ),
        },
    )

    async def query(*args: object) -> dict:
        entity_id = args[-1]
        value = "10" if entity_id == "sensor.a" else "30"
        return {entity_id: [State(entity_id, value, last_changed=args[2])]}

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 20
        freezer.tick(timedelta(seconds=80))
        hass.states.async_set("sensor.a", "21")
        await sensor.async_update()
        assert sensor.native_value == 10
        assert sensor.available_sources == 1
        assert sensor.available
        hass.states.async_set("sensor.b", "41")
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_value == 20
        assert sensor.available_sources == 2
        assert sensor.available


async def test_default_instantaneous_sensor_remains_event_driven(hass):
    """The default must not enable polling or change existing instantaneous behavior."""
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    assert not sensor.should_poll


async def test_native_poll_publishes_expiry_without_source_events(hass, freezer):
    """HA's scheduled entity poll must publish expiry of an otherwise quiet source."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.source", "20", {"unit_of_measurement": "°C"})
    config = {
        "sensor": [
            {
                "platform": "average",
                "name": "Age Average",
                "unique_id": "age_stable",
                "entities": ["sensor.source"],
                "max_source_age": {"seconds": 60},
            }
        ]
    }
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.age_average").state == "20.0"
    freezer.tick(timedelta(seconds=90))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.age_average").state == "unavailable"
    hass.states.async_set("sensor.source", "21", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.age_average").state == "21.0"
