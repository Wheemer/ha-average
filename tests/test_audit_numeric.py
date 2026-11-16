"""Reject unsafe substitute values and preserve sub-second history precision."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.core import State
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.util import dt as dt_util

from custom_components.average.config_flow import validate_options
from custom_components.average.sensor import PLATFORM_SCHEMA, AverageSensor


@pytest.mark.parametrize("value", [float("inf"), float("nan"), float("-inf"), True])
async def test_nonfinite_undefined_substitute_rejected_by_yaml_and_ui(value):
    """Both public configuration paths must reject the same unsafe values."""
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "average", "entities": ["sensor.a"], "process_undef_as": value}
        )
    with pytest.raises(SchemaFlowError):
        await validate_options(
            SimpleNamespace(options={}),
            {"entities": ["sensor.a"], "advanced": {"process_undef_as": value}},
        )


@pytest.mark.parametrize("precision", [0, 2])
@pytest.mark.parametrize("value", [float("inf"), float("nan"), True])
async def test_corrupt_stored_substitute_cannot_publish_nonfinite_or_crash(
    hass, precision, value
):
    """Defend existing stored options as well as newly validated input."""
    hass.states.async_set("sensor.a", "unavailable")
    sensor = AverageSensor(
        hass,
        {"entities": ["sensor.a"], "process_undef_as": value, "precision": precision},
    )
    await sensor._async_update_state()
    assert sensor.native_value is None
    assert not sensor.available


async def test_weighted_mean_of_large_finite_values_does_not_overflow(hass):
    """Scale the contributions before summing, keeping a finite convex mean."""
    sensor = AverageSensor(hass, {"entities": ["sensor.a", "sensor.b"]})
    assert sensor._weighted_average([(1e308, 1), (1e308, 1)]) == 1e308


async def test_subsecond_history_average_retains_full_boundary_precision(hass):
    """A valid 400 ms window cannot collapse into a zero-second integral."""
    start = dt_util.utcnow().replace(microsecond=100000) - timedelta(seconds=2)
    end = start + timedelta(milliseconds=400)
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(milliseconds=400)}
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    recorder = Mock(
        async_add_executor_job=AsyncMock(
            return_value={"sensor.a": [State("sensor.a", "20", last_changed=start)]}
        )
    )
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == 20


async def test_fractional_timestamp_boundary_is_preserved(hass):
    """Numeric timestamp templates retain their sub-second precision too."""
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    assert sensor._parse_period_boundary(1234.5, "start").timestamp() == 1234.5
