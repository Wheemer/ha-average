"""Large-history responsiveness and shutdown regression tests."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, State
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


def history_sensor(hass, size=10000):
    """Build a deterministic alternating history with a known time-weighted mean."""
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=size)
    hass.states.async_set("sensor.a", "40")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a"], "duration": timedelta(seconds=size)}
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    records = [
        State(
            "sensor.a",
            str(20 if index % 2 == 0 else 40),
            last_changed=start + timedelta(seconds=index),
        )
        for index in range(size)
    ]
    recorder = Mock(
        async_add_executor_job=AsyncMock(return_value={"sensor.a": records})
    )
    return sensor, recorder


async def test_large_history_yields_before_finishing_and_keeps_mean(hass):
    """Other HA callbacks can run before all historical points are processed."""
    sensor, recorder = history_sensor(hass)
    observed = []
    asyncio.get_running_loop().call_soon(lambda: observed.append(sensor.count))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    await asyncio.sleep(0)
    assert observed
    assert 0 < observed[0] < 10000
    assert sensor.native_value == 30
    assert sensor.count == 10001
    assert sensor.min_value == 20
    assert sensor.max_value == 40
    assert sensor.trending_towards == 30
    assert sensor.available_sources == 1


async def test_shutdown_during_large_history_stops_without_publishing_result(hass):
    """A cooperative refresh must respect a STOP received while processing history."""
    hass.set_state(CoreState.running)
    sensor, recorder = history_sensor(hass)
    sensor._attr_native_value = 99
    sensor._async_restore_previous_state = AsyncMock()
    sensor.async_schedule_update_ha_state = Mock()
    await sensor.async_added_to_hass()

    def stop() -> None:
        hass.set_state(CoreState.stopping)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)

    asyncio.get_running_loop().call_soon(stop)
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    await hass.async_block_till_done()
    assert sensor._stopping
    assert sensor.count < 10000
    assert sensor.native_value == 99
    recorder.async_add_executor_job.assert_awaited_once()
    await sensor.async_will_remove_from_hass()


async def test_history_refreshes_do_not_overlap_even_after_interval(hass):
    """A slow query does not allow later polls to start another history refresh."""
    sensor, recorder = history_sensor(hass, size=2)
    started = asyncio.Event()
    release = asyncio.Event()

    async def query(*_args: object) -> dict:
        started.set()
        await release.wait()
        return {}

    recorder.async_add_executor_job.side_effect = query
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        task = asyncio.create_task(sensor.async_update())
        try:
            await started.wait()
            sensor._last_update = dt_util.utcnow() - timedelta(minutes=1)
            await asyncio.wait_for(sensor.async_update(), timeout=1)
            recorder.async_add_executor_job.assert_awaited_once()
        finally:
            release.set()
            await task
    assert not sensor._update_in_progress


async def test_failed_refresh_releases_in_progress_guard(hass):
    """Normal-operation errors still propagate and do not block future refreshes."""
    sensor, _ = history_sensor(hass, size=2)
    sensor._async_update_state = AsyncMock(side_effect=RuntimeError("unexpected"))
    with pytest.raises(RuntimeError, match="unexpected"):
        await sensor.async_update()
    assert not sensor._update_in_progress
    sensor._last_update = None
    sensor._async_update_state = AsyncMock()
    await sensor.async_update()
    sensor._async_update_state.assert_awaited_once()
