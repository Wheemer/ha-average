"""History limits must fail visibly without overlapping uncancellable SQL."""

import asyncio
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

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


@pytest.mark.parametrize("configured", [False, True])
async def test_excessive_history_window_is_not_queried(hass, caplog, configured):
    """Reject oversized windows instead of returning a truncated average."""
    hass.states.async_set("sensor.a", "20")
    config = {"entities": ["sensor.a"], "duration": timedelta(days=60)}
    if configured:
        config["max_history_period"] = timedelta(days=7)
    sensor = AverageSensor(hass, config)
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    recorder.async_add_executor_job.assert_not_called()
    assert sensor.native_value is None
    assert not sensor.available
    assert "max_history_period" in caplog.text


async def test_deliberately_longer_history_window_can_be_configured(hass):
    """Existing long-window configurations remain supported with an explicit limit."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(days=60),
            "max_history_period": timedelta(days=90),
        },
    )
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    recorder.async_add_executor_job.assert_called_once()
    assert sensor.native_value == 20


@pytest.mark.parametrize("entry_id", [None, "same-entry"])
async def test_timeout_does_not_cancel_sql_or_allow_overlap_and_recovers(
    hass, caplog, entry_id
):
    """Bound the waiter while retaining real SQL completion across a reload."""
    hass.states.async_set("sensor.a", "20")
    config = {
        "entities": ["sensor.a"],
        "duration": timedelta(minutes=5),
        "history_query_timeout": timedelta(milliseconds=20),
    }
    sensor = AverageSensor(hass, config, entry_id=entry_id)
    release = threading.Event()
    calls = []

    def query(*args: object, **kwargs: object) -> dict:
        calls.append(True)
        assert release.wait(timeout=5)
        return {}

    recorder = Mock(async_add_executor_job=hass.async_add_executor_job)
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch(
            "custom_components.average.sensor.history.state_changes_during_period",
            side_effect=query,
        ),
    ):
        try:
            await asyncio.wait_for(sensor.async_update(), timeout=1)
            assert not sensor.available
            assert sensor.native_value is None
            assert not sensor._update_in_progress
            pending = sensor._pending_history_query
            assert pending is not None
            assert not pending.done()
            assert "timed out" in caplog.text
            await sensor.async_update()
            if entry_id:
                replacement = AverageSensor(hass, config, entry_id=entry_id)
                await replacement.async_update()
                assert not replacement.available
            assert len(calls) == 1
        finally:
            release.set()
            if sensor._pending_history_query is not None:
                await asyncio.wait_for(
                    asyncio.shield(sensor._pending_history_query), timeout=2
                )
            await asyncio.sleep(0)
        await sensor.async_update()
    assert len(calls) == 2
    assert sensor.native_value == 20
    assert sensor.available


async def test_missing_recorder_is_unavailable_and_recovers(hass, caplog):
    """Core's real get_instance raises KeyError when Recorder is absent."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    await sensor.async_update()
    assert not sensor.available
    assert "Recorder" in caplog.text
    recorder = Mock(async_add_executor_job=AsyncMock(return_value={}))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor.async_update()
    assert sensor.available


@pytest.mark.parametrize("value", [True, False])
async def test_boolean_boundary_is_not_an_epoch_timestamp(hass, value):
    """A boolean template result is malformed, never a date in 1970."""
    sensor = AverageSensor(hass, {"entities": ["sensor.a"]})
    assert sensor._parse_period_boundary(value, "start") is None


async def test_history_safety_controls_roundtrip_yaml_ui_and_runtime(hass):
    """Both configuration methods expose the same limits without ID changes."""
    yaml = PLATFORM_SCHEMA(
        {
            "platform": "average",
            "name": "Safe",
            "entities": ["sensor.a"],
            "unique_id": "stable",
            "duration": {"days": 60},
            "max_history_period": {"days": 90},
            "history_query_timeout": {"seconds": 120},
        }
    )
    options = _yaml_config_to_options(yaml)
    handler = SimpleNamespace(options=dict(options))
    form = await suggested_options(handler)
    form.pop("name")
    form.pop("unique_id")
    saved = await validate_options(handler, OPTIONS_SCHEMA(form))
    runtime = _entry_config(
        hass, SimpleNamespace(data={}, options={**options, **saved}, entry_id="same")
    )
    assert runtime["max_history_period"] == timedelta(days=90)
    assert runtime["history_query_timeout"] == timedelta(seconds=120)
    assert runtime["unique_id"] == "stable"


async def test_cancelled_waiter_does_not_hide_the_pending_query_deadline(hass, caplog):
    """Reload cancellation must not remove observability of a stuck SQL job."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a"],
            "duration": timedelta(minutes=5),
            "history_query_timeout": timedelta(milliseconds=20),
        },
        entry_id="same",
    )
    sql = hass.loop.create_future()
    recorder = Mock(async_add_executor_job=Mock(return_value=sql))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        task = asyncio.create_task(sensor.async_update())
        try:
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)
            assert "timed out" in caplog.text
            assert not sql.cancelled()
            assert not sql.done()
            replacement = AverageSensor(
                hass,
                {"entities": ["sensor.a"], "duration": timedelta(minutes=5)},
                entry_id="same",
            )
            await replacement.async_update()
            recorder.async_add_executor_job.assert_called_once()
            assert not replacement.available
        finally:
            sql.set_result({})
            await asyncio.sleep(0)


@pytest.mark.parametrize("key", ["max_history_period", "history_query_timeout"])
@pytest.mark.parametrize("duration", [{"seconds": 0}, {"seconds": -1}])
async def test_invalid_safety_durations_rejected_by_yaml_and_ui(key, duration):
    """Safety limits cannot be disabled accidentally with zero or negative values."""
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "average", "entities": ["sensor.a"], key: duration}
        )
    with pytest.raises(SchemaFlowError):
        await validate_options(
            SimpleNamespace(options={}),
            {"entities": ["sensor.a"], "advanced": {key: duration}},
        )


async def test_recorder_timeout_exception_is_not_misreported_as_waiter_deadline(hass):
    """Distinguish a database error from expiry of our own timeout context."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    recorder = Mock(
        async_add_executor_job=AsyncMock(side_effect=TimeoutError("database timeout"))
    )
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        pytest.raises(TimeoutError, match="database timeout"),
    ):
        await sensor.async_update()
    assert not sensor._update_in_progress
