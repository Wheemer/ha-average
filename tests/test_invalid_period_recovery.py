"""Source-dependent period templates must fail unavailable and recover safely."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


def dependent_sensor(hass):
    """Use a period boundary supplied by an entity that can be missing at startup."""
    return AverageSensor(
        hass,
        {
            "entities": ["sensor.reading"],
            "unique_id": "stable",
            "duration": timedelta(minutes=5),
            "end": Template("{{ state_attr('sensor.period', 'end') }}", hass),
        },
    )


async def test_missing_template_attribute_does_not_raise_or_use_instantaneous_average(
    hass, caplog
):
    """A missing boundary is not permission to change a history sensor's meaning."""
    hass.states.async_set("sensor.reading", "20")
    sensor = dependent_sensor(hass)
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert not sensor.available
    assert sensor.native_value is None
    recorder.async_add_executor_job.assert_not_awaited()
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


async def test_invalid_boundary_invalidates_previous_period_then_recovers(
    hass, freezer
):
    """Old boundaries and a cached value cannot survive a newly invalid template."""
    hass.states.async_set("sensor.reading", "20")
    end = dt_util.utcnow().isoformat()
    hass.states.async_set("sensor.period", "ready", {"end": end})
    sensor = dependent_sensor(hass)
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
        assert sensor.available
        hass.states.async_set("sensor.period", "ready", {"end": "invalid"})
        await sensor._async_update_state()
        assert not sensor.available
        assert sensor.native_value is None
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(
            "sensor.period", "ready", {"end": dt_util.utcnow().isoformat()}
        )
        await sensor._async_update_state()
        assert sensor.available
        assert sensor.native_value == 20
        assert sensor.unique_id == "stable"


async def test_future_period_does_not_publish_current_value(hass):
    """A range entirely in the future has no historical average yet."""
    hass.states.async_set("sensor.reading", "20")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.reading"],
            "start": Template("{{ (now() + timedelta(hours=1)).isoformat() }}", hass),
            "duration": timedelta(minutes=5),
        },
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert not sensor.available
    assert sensor.native_value is None
    recorder.async_add_executor_job.assert_not_awaited()


@pytest.mark.parametrize(
    "boundary",
    ["unknown", "unavailable", "", "invalid", float("inf"), float("nan"), [], {}],
)
async def test_malformed_template_boundary_cannot_escape_as_runtime_error(
    hass, boundary
):
    """Malformed external boundary data leaves the history sensor unavailable."""
    hass.states.async_set("sensor.reading", "20")
    hass.states.async_set("sensor.period", "ready", {"end": boundary})
    sensor = dependent_sensor(hass)
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert not sensor.available
    assert sensor.native_value is None
    recorder.async_add_executor_job.assert_not_awaited()


async def test_zero_length_period_has_no_average(hass, freezer):
    """At a period's initial boundary, do not invent a current-value history mean."""
    freezer.move_to("2026-11-14 10:00:00+00:00")
    hass.states.async_set("sensor.reading", "20")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.reading"],
            "start": Template("{{ now() }}", hass),
            "end": Template("{{ now() }}", hass),
        },
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert not sensor.available
    assert sensor.native_value is None
    recorder.async_add_executor_job.assert_not_awaited()


@pytest.mark.parametrize("naive", [False, True])
async def test_native_datetime_boundaries_are_accepted(hass, naive):
    """Already rendered datetime boundaries must not be coerced through float()."""
    hass.states.async_set("sensor.reading", "20")
    end = dt_util.now() - timedelta(minutes=1)
    if naive:
        end = end.replace(tzinfo=None)
    template = Mock()
    template.async_render.return_value = end
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.reading"],
            "duration": timedelta(minutes=5),
            "end": template,
        },
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.available
    assert sensor.native_value == 20
    assert sensor.end.tzinfo is not None
