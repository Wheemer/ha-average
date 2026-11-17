"""Remaining audit regressions must preserve calculation and identity contracts."""

import asyncio
import logging
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, State
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor, _duration_from_selector


async def test_substitute_contributes_to_diagnostic_extrema_and_count(hass):
    """Processed fallback values must be represented by count/min/max too."""
    hass.states.async_set("sensor.a", "10")
    hass.states.async_set("sensor.b", "unavailable")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a", "sensor.b"], "process_undef_as": 100}
    )
    await sensor._async_update_state()
    assert sensor.native_value == 55
    assert sensor.count == 2
    assert sensor.min_value == 10
    assert sensor.max_value == 100


async def test_unexpected_recorder_failure_clears_partial_results_and_can_retry(hass):
    """Keep failures visible without publishing stale values or delaying retry."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    sensor._attr_native_value = 99
    recorder = Mock(
        async_add_executor_job=AsyncMock(side_effect=RuntimeError("database failed"))
    )
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        pytest.raises(RuntimeError, match="database failed"),
    ):
        await sensor.async_update()
    assert sensor.native_value is None
    assert sensor.count == sensor.available_sources == 0
    assert sensor._last_update is None
    assert not sensor.available
    recorder.async_add_executor_job = AsyncMock(return_value={})
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
    assert sensor.native_value == 20


async def test_available_temperature_check_does_not_log_or_mutate_error_budget(
    hass, caplog
):
    """Repeated HA availability reads cannot consume calculation error counters."""
    hass.states.async_set(
        "sensor.a",
        "bad",
        {"unit_of_measurement": "°C", "private_attribute": "DO_NOT_LOG_THIS"},
    )
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "require_all_sources": True}
    )
    sensor._prepare_source_mode()
    caplog.clear()
    for _ in range(3):
        assert not sensor.available
    assert not sensor._temperature_conversion_errors
    assert "DO_NOT_LOG_THIS" not in caplog.text
    assert not caplog.records


async def test_bad_temperature_log_does_not_include_unrelated_attributes(hass, caplog):
    """Conversion diagnostics need a source ID, never the entire State object."""
    hass.states.async_set(
        "sensor.a",
        "bad",
        {"unit_of_measurement": "°C", "private_attribute": "DO_NOT_LOG_THIS"},
    )
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    await sensor._async_update_state()
    assert "sensor.a" in caplog.text
    assert "DO_NOT_LOG_THIS" not in caplog.text


async def test_template_error_handler_accepts_nonstring_exception_args():
    """An error handler cannot raise while formatting an unusual exception."""
    AverageSensor.handle_template_exception(Exception(123), "start")


async def test_repeated_malformed_boundaries_log_once_until_recovery(hass, caplog):
    """Malformed template outputs must not emit an error on every poll."""
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    for _ in range(3):
        assert sensor._parse_period_boundary([], "start") is None
    assert len(caplog.records) == 1
    assert sensor._parse_period_boundary(dt_util.utcnow(), "start") is not None
    assert sensor._parse_period_boundary([], "start") is None
    assert len(caplog.records) == 2


async def test_empty_history_warning_is_deduplicated_without_stopping_retries(
    hass, caplog
):
    """An excluded source must remain retryable without repeated warning spam."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
        await sensor._async_update_state()
    assert recorder.async_add_executor_job.await_count == 2
    assert (
        sum("Historical data not found" in record.message for record in caplog.records)
        == 1
    )


async def test_unload_cancels_waiter_but_not_pending_sql(hass):
    """Removing the entity cannot retain an unbounded refresh task."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass,
        {"entities": ["sensor.a"], "duration": timedelta(minutes=5)},
        entry_id="stable",
    )
    sql = hass.loop.create_future()
    recorder = Mock(async_add_executor_job=Mock(return_value=sql))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        task = asyncio.create_task(sensor.async_update())
        try:
            await asyncio.sleep(0)
            await sensor.async_will_remove_from_hass()
            assert task.done()
            assert task.cancelled()
            assert not sql.cancelled()
            assert not sql.done()
            replacement = AverageSensor(
                hass,
                {"entities": ["sensor.a"], "duration": timedelta(minutes=5)},
                entry_id="stable",
            )
            await replacement.async_update()
            recorder.async_add_executor_job.assert_called_once()
        finally:
            sql.set_result({})
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_pre_start_rows_are_clamped_to_window_boundary(hass):
    """Defensive weighting must not assign negative time to pre-start rows."""
    end = dt_util.utcnow() - timedelta(seconds=1)
    start = end - timedelta(seconds=30)
    hass.states.async_set("sensor.a", "100")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(seconds=30)}
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    rows = [
        State("sensor.a", "200", last_changed=start - timedelta(seconds=20)),
        State("sensor.a", "100", last_changed=start - timedelta(seconds=10)),
    ]
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={"sensor.a": rows}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == 100


@pytest.mark.parametrize("value", [30, "00:00:30"])
async def test_legacy_scalar_durations_are_normalized(value):
    """Older scalar entry formats remain usable instead of reaching arithmetic raw."""
    assert _duration_from_selector(value) == timedelta(seconds=30)


@pytest.mark.parametrize("value", [[], "bad", object()])
async def test_corrupt_scalar_duration_is_rejected_at_setup(value):
    """Reject corrupt stored values before they can crash every polling update."""
    with pytest.raises(vol.Invalid):
        _duration_from_selector(value)


@pytest.mark.parametrize(("precision", "expected"), [(2, 15.55), (0, 15), (-1, 10)])
async def test_projection_uses_the_sensor_precision(hass, precision, expected):
    """Trend precision includes the existing zero and negative precision behavior."""
    end = dt_util.utcnow() - timedelta(seconds=20)
    start = end - timedelta(seconds=30)
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(seconds=30),
            "precision": precision,
        },
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end + timedelta(seconds=30)

    sensor._async_update_period = period
    rows = [
        State("sensor.a", "10", last_changed=start),
        State("sensor.a", "20", last_changed=end - timedelta(seconds=10)),
    ]
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={"sensor.a": rows}))
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch(
            "custom_components.average.sensor.dt_util.now",
            return_value=end + timedelta(seconds=10),
        ),
    ):
        await sensor._async_update_state()
    assert sensor.trending_towards == expected


async def test_strict_recovery_waits_for_a_complete_recalculation(hass):
    """Recovering live sources do not make an old partial average complete."""
    hass.states.async_set("sensor.a", "10")
    hass.states.async_set("sensor.b", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a", "sensor.b"], "require_all_sources": True}
    )
    sensor._attr_native_value = 10
    sensor.available_sources = 1
    assert not sensor.available
    await sensor._async_update_state()
    assert sensor.available
    assert sensor.native_value == 15


async def test_reversed_period_keeps_legacy_result_and_warns_once(hass, caplog):
    """Warn about reversed templates without changing a supported legacy result."""
    late = dt_util.utcnow() - timedelta(minutes=1)
    early = late - timedelta(minutes=1)
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "start": Template(late.isoformat(), hass),
            "end": Template(early.isoformat(), hass),
        },
    )
    await sensor._async_update_period()
    await sensor._async_update_period()
    assert sensor._period == (early, late)
    assert sum("reversed" in record.message for record in caplog.records) == 1


async def test_debug_logging_does_not_dump_template_contents(hass, caplog):
    """Template text can contain private configuration and is unnecessary in logs."""
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "start": Template("PRIVATE_TEMPLATE_CONTENT", hass),
            "duration": timedelta(minutes=5),
        },
    )
    await sensor._async_update_period()
    assert sensor._period is None
    assert "PRIVATE_TEMPLATE_CONTENT" not in caplog.text


async def test_repeated_instantaneous_conversion_errors_wait_for_change_or_recovery(
    hass, caplog
):
    """A persistently bad current source must not emit a traceback per event."""
    hass.states.async_set("sensor.a", "bad", {"unit_of_measurement": "°C"})
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    await sensor._async_update_state()
    await sensor._async_update_state()
    assert sum(record.levelno == logging.ERROR for record in caplog.records) == 1
    hass.states.async_set("sensor.a", "20", {"unit_of_measurement": "°C"})
    await sensor._async_update_state()
    hass.states.async_set("sensor.a", "bad", {"unit_of_measurement": "°C"})
    await sensor._async_update_state()
    assert sum(record.levelno == logging.ERROR for record in caplog.records) == 2


async def test_stop_cancels_a_waiting_refresh_without_cancelling_sql(hass):
    """An in-flight waiter must not keep running after Home Assistant STOP."""
    hass.set_state(CoreState.running)
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    sensor._async_restore_previous_state = AsyncMock()
    sensor.async_schedule_update_ha_state = Mock()
    await sensor.async_added_to_hass()
    sql = hass.loop.create_future()
    recorder = Mock(async_add_executor_job=Mock(return_value=sql))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        task = asyncio.create_task(sensor.async_update())
        try:
            await asyncio.sleep(0)
            hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sensor._stopping
            assert not sql.cancelled()
            assert not sql.done()
        finally:
            sql.set_result({})
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    await sensor.async_will_remove_from_hass()
