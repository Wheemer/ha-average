"""Regression cases from the upstream backlog, without live HA access."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.core import CoreState, State
from homeassistant.util import dt as dt_util

from custom_components.average.config_flow import (
    _yaml_config_to_options,
    validate_options,
)
from custom_components.average.sensor import PLATFORM_SCHEMA, AverageSensor


@pytest.mark.parametrize(
    "bad", ["nan", "inf", "-inf", "unavailable", "unknown", "broken"]
)
@pytest.mark.parametrize("precision", [0, 2])
async def test_partial_average_ignores_invalid_source(hass, bad, precision):
    """One invalid reading must not poison the remaining valid sources."""
    hass.states.async_set("sensor.a", "20")
    hass.states.async_set("sensor.b", bad)
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a", "sensor.b"], "precision": precision}
    )
    await sensor._async_update_state()
    assert sensor.native_value == 20
    assert sensor.available_sources == 1
    assert sensor.available
    hass.states.async_set("sensor.b", "30")
    await sensor._async_update_state()
    assert sensor.native_value == 25
    assert sensor.available_sources == 2


async def test_strict_history_events_respect_interval_and_invalidate_immediately(hass):
    """Frequent source changes must not bypass the configured history interval."""
    hass.set_state(CoreState.running)
    hass.states.async_set("sensor.a", "20")
    hass.states.async_set("sensor.b", "30")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "require_all_sources": True,
            "duration": timedelta(minutes=5),
            "scan_interval": timedelta(minutes=1),
        },
    )
    sensor._async_restore_previous_state = AsyncMock()
    sensor.async_schedule_update_ha_state = Mock()
    sensor.async_write_ha_state = Mock()
    listener = []

    def track(hass, sources, cb) -> Mock:
        listener.append(cb)
        return Mock()

    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch(
        "custom_components.average.sensor.async_track_state_change_event",
        side_effect=track,
    ):
        await sensor.async_added_to_hass()
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await listener[0](None)
        assert sensor.native_value == 25
        for value in range(21, 31):
            hass.states.async_set("sensor.a", str(value))
            await listener[0](None)
        assert recorder.async_add_executor_job.await_count == 2
        hass.states.async_set("sensor.b", "unavailable")
        await listener[0](None)
        assert not sensor.available
        assert sensor.async_write_ha_state.call_count == 12
        assert recorder.async_add_executor_job.await_count == 2
        hass.states.async_set("sensor.b", "30")
        await listener[0](None)
        assert sensor.available
    await sensor.async_will_remove_from_hass()


async def test_stacked_temperature_and_statistics_metadata(hass):
    """Upstream #143/#185/#267 retain temperature metadata after startup."""
    hass.states.async_set("sensor.stacked", "20")
    sensor = AverageSensor(hass, {"entities": ["sensor.stacked"]})
    await sensor._async_update_state()
    hass.states.async_set(
        "sensor.stacked",
        "21",
        {"unit_of_measurement": "°C", "device_class": "temperature"},
    )
    await sensor._async_update_state()
    assert sensor.native_value == 21
    assert sensor.native_unit_of_measurement == "°C"
    assert sensor.device_class == "temperature"


@pytest.mark.parametrize(
    ("ignore", "extend", "strict", "expected"),
    [
        (False, False, False, None),
        (True, False, False, 20),
        (True, True, False, 20),
        (True, False, True, 20),
        (True, True, True, 20),
    ],
)
async def test_history_gap_options_never_override_strict_availability(
    hass, ignore, extend, strict, expected
):
    """Trailing gaps are opt-in and cannot fabricate strict availability."""
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=30)
    hass.states.async_set("sensor.a", "unavailable")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(seconds=30),
            "ignore_undef": ignore,
            "calculate_to_now_undef": extend,
            "require_all_sources": strict,
        },
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    history = {
        "sensor.a": [
            State("sensor.a", "20", last_changed=start),
            State(
                "sensor.a", "unavailable", last_changed=start + timedelta(seconds=10)
            ),
        ]
    }
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=history))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == expected
    assert sensor.available is (expected is not None and not strict)


@pytest.mark.parametrize(("extend", "expected"), [(False, 30), (True, 26.67)])
async def test_gap_then_recovery_keeps_correct_time_weighting(hass, extend, expected):
    """Unknown gaps and explicit carry-forward produce distinct documented results."""
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=30)
    hass.states.async_set("sensor.a", "40")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(seconds=30),
            "ignore_undef": True,
            "calculate_to_now_undef": extend,
        },
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    history = {
        "sensor.a": [
            State("sensor.a", "20", last_changed=start),
            State(
                "sensor.a", "unavailable", last_changed=start + timedelta(seconds=10)
            ),
            State("sensor.a", "40", last_changed=start + timedelta(seconds=20)),
        ]
    }
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=history))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == expected
    assert sensor.available


async def test_no_history_and_no_valid_value_remains_unavailable(hass):
    """The upstream PR must not advertise availability with no usable data."""
    hass.states.async_set("sensor.a", "unavailable")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(seconds=30),
            "ignore_undef": True,
            "calculate_to_now_undef": True,
        },
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value is None
    assert not sensor.available


async def test_invalid_history_gap_combination_is_rejected(hass):
    """Carry-forward requires explicit consent to ignore undefined readings."""
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(
            {
                "platform": "average",
                "entities": ["sensor.a"],
                "calculate_to_now_undef": True,
            }
        )


async def test_undefined_options_survive_yaml_and_ui_edits():
    """Gap controls must retain their stored values when Advanced is omitted."""
    old = _yaml_config_to_options(
        {
            "name": "test",
            "entities": ["sensor.a"],
            "ignore_undef": True,
            "calculate_to_now_undef": True,
        }
    )
    options = await validate_options(
        SimpleNamespace(options=old), {"entities": ["sensor.a"]}
    )
    assert options["ignore_undef"] is True
    assert options["calculate_to_now_undef"] is True
