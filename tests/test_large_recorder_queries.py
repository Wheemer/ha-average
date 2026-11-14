"""Large real SQLite histories retain results without unnecessary attribute joins."""

import asyncio
from datetime import datetime, timedelta
from functools import partial

import pytest
from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.db_schema import States
from homeassistant.components.recorder.util import session_scope
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from sqlalchemy import event, insert, select

from custom_components.average.sensor import AverageSensor

from .test_attribute_recorder_history import commit_recording


def _seed_history(
    hass: HomeAssistant, start: datetime, size: int, entity_id: str
) -> None:
    """Seed isolated test data; production code only uses Core history APIs."""
    with session_scope(hass=hass) as session:
        metadata_id = get_instance(hass).states_meta_manager.get(
            entity_id, session, False
        )
        attribute_ids = dict(
            session.execute(
                select(States.state, States.attributes_id).where(
                    States.metadata_id == metadata_id
                )
            ).all()
        )
        rows = [
            {
                "metadata_id": metadata_id,
                "attributes_id": attribute_ids["20" if index % 2 == 0 else "40"],
                "state": "20" if index % 2 == 0 else "40",
                "last_updated_ts": start.timestamp() + index,
                "last_changed_ts": None,
            }
            for index in range(size)
        ]
        session.execute(insert(States), rows)


@pytest.mark.parametrize("temperature", [False, True])
async def test_large_query_preserves_values_and_only_joins_needed_attributes(
    hass, tmp_path, freezer, temperature
):
    """A large numeric query avoids the join; temperatures retain historic units."""
    freezer.move_to("2026-11-14 10:00:00+00:00")
    if "recorder" not in hass.data:
        async_initialize_recorder(hass)
    assert await async_setup_component(
        hass,
        "recorder",
        {"recorder": {"db_url": "sqlite:///" + str(tmp_path / "large.db")}},
    )
    await hass.async_start()
    recorder = get_instance(hass)
    entity_id = "sensor.large_source"
    start = dt_util.utcnow() + timedelta(seconds=1)
    size = 10000
    end = start + timedelta(seconds=size)
    unit = "°C" if temperature else "W"
    hass.states.async_set(
        entity_id, "20", {"unit_of_measurement": unit, "payload": "x" * 2048}
    )
    await commit_recording(hass, recorder)
    freezer.tick(timedelta(milliseconds=100))
    hass.states.async_set(
        entity_id,
        "40",
        {"unit_of_measurement": "°F" if temperature else unit, "payload": "x" * 2048},
    )
    await commit_recording(hass, recorder)
    freezer.tick(timedelta(milliseconds=100))
    hass.states.async_set(
        entity_id, "20", {"unit_of_measurement": unit, "payload": "x" * 2048}
    )
    await commit_recording(hass, recorder)

    await recorder.async_add_executor_job(_seed_history, hass, start, size, entity_id)
    freezer.move_to(end + timedelta(seconds=1))
    full = await recorder.async_add_executor_job(
        history.state_changes_during_period, hass, start, end, entity_id
    )
    expected_points = [(state.state, state.last_changed) for state in full[entity_id]]
    del full
    queries = []

    def capture(
        _connection: object, _cursor: object, statement: str, *_args: object
    ) -> None:
        queries.append(statement)

    event.listen(recorder.engine, "before_cursor_execute", capture)
    sensor = AverageSensor(
        hass,
        {
            "entities": [entity_id],
            "unique_id": "large_stable",
            "start": Template(start.isoformat(), hass),
            "end": Template(end.isoformat(), hass),
        },
    )
    try:
        await sensor._async_update_state()
        numeric_queries = [query for query in queries if "FROM states" in query]
        assert numeric_queries
        assert (
            any("state_attributes" in query for query in numeric_queries) is temperature
        )
        assert sensor.native_value == (12.22 if temperature else 30)
        assert sensor.min_value == (4.44 if temperature else 20)
        assert sensor.max_value == (20 if temperature else 40)
        assert sensor.native_unit_of_measurement == unit
        assert sensor.unique_id == "large_stable"
        assert sensor.available
        assert sensor.count == len(expected_points) + 1
        assert sensor.max_datetime == start + timedelta(seconds=0 if temperature else 1)
        query = partial(
            history.state_changes_during_period, no_attributes=not temperature
        )
        optimized = await recorder.async_add_executor_job(
            query, hass, start, end, entity_id
        )
        assert [
            (state.state, state.last_changed) for state in optimized[entity_id]
        ] == expected_points
    finally:
        event.remove(recorder.engine, "before_cursor_execute", capture)
    await asyncio.sleep(0)
