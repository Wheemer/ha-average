"""Configuration owns source count, not restored diagnostics from an older setup."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import State

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize(
    ("old_count", "sources"), [(2, ["sensor.a"]), (1, ["sensor.a", "sensor.b"])]
)
async def test_strict_sensor_recovers_after_restoring_different_source_count(
    hass, old_count, sources
):
    """Changed YAML/UI source lists must not become permanently unavailable."""
    hass.states.async_set("sensor.a", "20", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.b", "40", {"unit_of_measurement": "°C"})
    sensor = AverageSensor(
        hass, {"entities": sources, "unique_id": "stable", "require_all_sources": True}
    )
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(
        return_value=State(
            "sensor.average",
            "30",
            {
                "count_sources": old_count,
                "available_sources": old_count,
                "unit_of_measurement": "°C",
            },
        )
    )
    sensor.async_write_ha_state = Mock()
    await sensor._async_restore_previous_state()
    await sensor._async_update_state()
    assert sensor.count_sources == len(sources)
    assert sensor.available
    assert sensor.native_value == (20 if len(sources) == 1 else 30)
    assert sensor.unique_id == "stable"
