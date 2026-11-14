"""Real SQLite recorder coverage for attribute-only reading changes."""

import asyncio
from datetime import timedelta
from functools import partial

import pytest
from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


async def commit_recording(hass, recorder):
    """Wait for a FIFO commit barrier, including an event already being processed."""
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    recorder.queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, timeout=10)


@pytest.mark.parametrize(
    ("domain", "selected"),
    [
        ("weather", False),
        ("weather", True),
        ("climate", False),
        ("water_heater", False),
        ("sensor", True),
        ("sensor", False),
    ],
)
async def test_real_recorder_attribute_changes_are_included(
    hass, tmp_path, freezer, domain, selected
):
    """Attribute sources retain updates; numeric-state sources retain their path."""
    freezer.move_to("2026-11-14 10:00:00+00:00")
    if "recorder" not in hass.data:
        async_initialize_recorder(hass)
    assert await async_setup_component(
        hass,
        "recorder",
        {"recorder": {"db_url": "sqlite:///" + str(tmp_path / "history.db")}},
    )
    await hass.async_start()
    recorder = get_instance(hass)
    entity_id = f"{domain}.source"
    field = "temperature" if domain == "weather" else "current_temperature"
    initial = {field: 10, "humidity": 40}
    changed = {field: 20, "humidity": 80}
    state = "sunny" if domain == "weather" else "active"
    changed_state = state
    attribute = "humidity" if selected else None
    expected, unit = (60, "%") if selected else (15, "°C")
    if domain == "sensor" and selected:
        initial = {"level": 40, "level_unit": "cm"}
        changed = {"level": 80, "level_unit": "cm"}
        attribute, expected, unit = "level", 60, "cm"
    elif domain == "sensor":
        initial = changed = {"unit_of_measurement": "°C"}
        state, changed_state = "10", "20"
    hass.states.async_set(entity_id, state, initial)
    await commit_recording(hass, recorder)
    start = dt_util.utcnow() + timedelta(seconds=1)
    freezer.tick(timedelta(seconds=21))
    changed_at = dt_util.utcnow()
    hass.states.async_set(entity_id, changed_state, changed)
    await commit_recording(hass, recorder)
    freezer.tick(timedelta(seconds=20))
    end = dt_util.utcnow()
    records = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            [entity_id],
            significant_changes_only=False,
        )
    )
    assert len(records[entity_id]) == 2
    assert records[entity_id][-1].last_updated == changed_at
    config = {
        "entities": [entity_id],
        "unique_id": "stable",
        "start": Template(start.isoformat(), hass),
        "end": Template(end.isoformat(), hass),
    }
    if attribute:
        config["source_attributes"] = {entity_id: attribute}
    sensor = AverageSensor(hass, config)
    await sensor._async_update_state()
    assert sensor.native_value == expected
    assert sensor.max_datetime == changed_at
    assert sensor.native_unit_of_measurement == unit
    assert sensor.unique_id == "stable"
