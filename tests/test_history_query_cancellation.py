"""Cancellation cannot stop a SQL thread or permit overlapping replacement work."""

import asyncio
import threading
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize("attribute", [False, True])
async def test_cancelled_refresh_waits_for_real_executor_completion(hass, attribute):
    """A timeout must not queue another query over a still-running executor job."""
    entity_id = "weather.a" if attribute else "sensor.a"
    hass.states.async_set(
        entity_id, "sunny" if attribute else "20", {"temperature": 20}
    )
    sensor = AverageSensor(
        hass, {"entities": [entity_id], "duration": timedelta(minutes=5)}
    )
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []

    def query(*args: object, **kwargs: object) -> dict:
        calls.append(threading.get_ident())
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return {}

    recorder = Mock(async_add_executor_job=hass.async_add_executor_job)
    name = "get_significant_states" if attribute else "state_changes_during_period"
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch("custom_components.average.sensor.history." + name, new=query),
    ):
        task = asyncio.create_task(sensor.async_update())
        release_timer = None
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            sensor._last_update = dt_util.utcnow() - timedelta(minutes=1)
            release_timer = loop.call_later(0.05, release.set)
            await sensor.async_update()
            await sensor._async_update_state()
            assert len(calls) == 1
        finally:
            if release_timer is not None:
                release_timer.cancel()
            release.set()
            if (pending := getattr(sensor, "_pending_history_query", None)) is not None:
                await asyncio.wait_for(asyncio.shield(pending), timeout=3)
            await asyncio.sleep(0)
            await hass.async_block_till_done()
        sensor._last_update = None
        await sensor.async_update()
    assert len(calls) == 2
    assert sensor.native_value == 20
    assert sensor.available
    assert not sensor._update_in_progress


async def test_detached_query_failure_is_logged_and_allows_recovery(hass, caplog):
    """A late SQL exception must be retrieved, reported and release backpressure."""
    hass.states.async_set("sensor.a", "20")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(minutes=5)}
    )
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def fail(*args: object, **kwargs: object) -> None:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        message = "late SQL failure"
        raise RuntimeError(message)

    recorder = Mock(async_add_executor_job=hass.async_add_executor_job)
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch(
            "custom_components.average.sensor.history.state_changes_during_period",
            new=fail,
        ),
    ):
        task = asyncio.create_task(sensor.async_update())
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            if (pending := sensor._pending_history_query) is not None:
                with pytest.raises(RuntimeError, match="late SQL failure"):
                    await asyncio.wait_for(asyncio.shield(pending), timeout=3)
            await asyncio.sleep(0)
            await hass.async_block_till_done()
    assert "late SQL failure" in caplog.text
    assert sensor._pending_history_query is None
    recorder.async_add_executor_job = Mock(side_effect=hass.async_add_executor_job)
    with (
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch(
            "custom_components.average.sensor.history.state_changes_during_period",
            return_value={},
        ),
    ):
        sensor._last_update = None
        await sensor.async_update()
    assert sensor.native_value == 20
