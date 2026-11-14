"""Reproduce unavailable fixed-window averages behind the rounded-end reports."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers.template import Template
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.average.sensor import AverageSensor


def fixed_sensor(hass, sources, *, strict=False):
    """Use the rounded end-time binding reported in upstream #243."""
    return AverageSensor(
        hass,
        {
            "entities": sources,
            "unique_id": "stable",
            "duration": timedelta(hours=1),
            "end": Template(
                "{{ now().replace(minute=0, second=0, microsecond=0) }}", hass
            ),
            "require_all_sources": strict,
        },
    )


@pytest.mark.parametrize("strict", [False, True])
async def test_completed_window_recovers_after_source_and_history_arrive(
    hass, freezer, strict
):
    """A failed first calculation must not permanently cache an unavailable result."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "unavailable")
    sensor = fixed_sensor(hass, ["sensor.a"], strict=strict)
    ready = False

    async def query(*args: object) -> dict:
        if not ready:
            return {}
        return {"sensor.a": [State("sensor.a", "20", last_changed=args[2])]}

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert not sensor.available
        assert sensor.native_value is None
        ready = True
        hass.states.async_set("sensor.a", "20")
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.available
        assert sensor.native_value == 20
        assert sensor.unique_id == "stable"
        assert recorder.async_add_executor_job.await_count == 2
        # Successful, complete closed periods should still avoid redundant queries.
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert recorder.async_add_executor_job.await_count == 2


async def test_completed_partial_window_includes_late_source_without_reload(
    hass, freezer
):
    """A partial first result cannot prevent a second source from ever contributing."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "30")
    hass.states.async_set("sensor.b", "unavailable")
    sensor = fixed_sensor(hass, ["sensor.a", "sensor.b"])
    ready = False

    async def query(*args: object) -> dict:
        entity_id = args[-1]
        if entity_id == "sensor.b" and not ready:
            return {}
        value = "30" if entity_id == "sensor.a" else "50"
        return {entity_id: [State(entity_id, value, last_changed=args[2])]}

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 30
        assert sensor.available_sources == 1
        ready = True
        hass.states.async_set("sensor.b", "50")
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_value == 40
        assert sensor.available_sources == 2


async def test_current_value_fallback_is_not_cached_as_completed_history(hass, freezer):
    """The documented current-value fallback must yield to recorded data later."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "40")
    sensor = fixed_sensor(hass, ["sensor.a"])
    ready = False

    async def query(*args: object) -> dict:
        if not ready:
            return {}
        return {"sensor.a": [State("sensor.a", "10", last_changed=args[2])]}

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 40
        ready = True
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_value == 10


async def test_new_closed_window_retries_after_transient_recorder_error(hass, freezer):
    """A previous successful window must not mark a failed new window complete."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "20")
    sensor = fixed_sensor(hass, ["sensor.a"])
    fail = False
    value = "20"

    async def query(*args: object) -> dict:
        if fail:
            error = "temporary recorder failure"
            raise RuntimeError(error)
        return {"sensor.a": [State("sensor.a", value, last_changed=args[2])]}

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 20
        freezer.tick(timedelta(hours=1))
        fail = True
        with pytest.raises(RuntimeError, match="temporary recorder failure"):
            await sensor.async_update()
        fail = False
        value = "30"
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_value == 30
        assert sensor.available
        assert recorder.async_add_executor_job.await_count == 3


async def test_completed_window_recovers_temperature_metadata_after_startup(
    hass, freezer
):
    """Upstream #267: late source metadata must not be blocked by period caching."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set("sensor.a", "20")
    sensor = fixed_sensor(hass, ["sensor.a"])

    async def query(*args: object) -> dict:
        return {
            "sensor.a": [
                State(
                    "sensor.a",
                    "20",
                    {"device_class": "temperature", "unit_of_measurement": "°C"},
                    last_changed=args[2],
                )
            ]
        }

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 20
        assert sensor.native_unit_of_measurement is None
        hass.states.async_set(
            "sensor.a",
            "20",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_unit_of_measurement == "°C"
        assert sensor.device_class == "temperature"
        assert sensor.native_value == 20
        assert sensor.unique_id == "stable"


async def test_closed_window_recalculates_and_labels_changed_temperature_units(
    hass, freezer
):
    """A configured temperature-unit change invalidates a cached result consistently."""
    freezer.move_to("2026-11-14 10:30:00+00:00")
    hass.states.async_set(
        "sensor.a", "20", {"device_class": "temperature", "unit_of_measurement": "°C"}
    )
    sensor = fixed_sensor(hass, ["sensor.a"])

    async def query(*args: object) -> dict:
        return {
            "sensor.a": [
                State(
                    "sensor.a",
                    "20",
                    {"device_class": "temperature", "unit_of_measurement": "°C"},
                    last_changed=args[2],
                )
            ]
        }

    recorder = Mock(async_add_executor_job=AsyncMock(side_effect=query))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
        assert sensor.native_value == 20
        assert sensor.native_unit_of_measurement == "°C"
        hass.config.units = US_CUSTOMARY_SYSTEM
        freezer.tick(timedelta(seconds=30))
        await sensor.async_update()
        assert sensor.native_value == 68
        assert sensor.native_unit_of_measurement == "°F"
        assert sensor.unique_id == "stable"
        assert recorder.async_add_executor_job.await_count == 2
