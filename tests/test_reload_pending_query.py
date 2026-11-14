"""UI and YAML reloads cannot queue SQL over a blocked original query."""

import asyncio
import threading
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize("method", ["options", "yaml"])
async def test_edit_during_blocked_sql_preserves_identity_and_backpressure(  # noqa: PLR0915
    hass, tmp_path, method
):
    """Repeated edits can replace entities without duplicating the blocked SQL."""
    hass.states.async_set("sensor.a", "20", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.b", "40", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.c", "60", {"unit_of_measurement": "°C"})
    config = {
        "sensor": [
            {
                "platform": "average",
                "name": "Blocked Average",
                "unique_id": "stable_blocked",
                "entities": ["sensor.a"],
                "duration": {"minutes": 5},
            }
        ]
    }
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).parents[1] / "custom_components", target_is_directory=True
    )
    config_path = tmp_path / "configuration.yaml"
    config_path.write_text(yaml.safe_dump(config))
    started = asyncio.Event()
    replacement_added = asyncio.Event()
    release = threading.Event()
    release.set()
    loop = asyncio.get_running_loop()
    created = []

    def create(*args: object, **kwargs: object) -> AverageSensor:
        sensor = AverageSensor(*args, **kwargs)
        created.append(sensor)
        original_added = sensor.async_added_to_hass

        async def added() -> None:
            await original_added()
            if len(created) > 1:
                replacement_added.set()

        sensor.async_added_to_hass = added
        return sensor

    def blocked_query(*args: object, **kwargs: object) -> dict:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=10)
        return {}

    submit = Mock(side_effect=hass.async_add_executor_job)
    recorder = Mock(async_add_executor_job=submit)
    task = None
    with (
        patch("custom_components.average.sensor.AverageSensor", side_effect=create),
        patch("custom_components.average.sensor.get_instance", return_value=recorder),
        patch(
            "custom_components.average.sensor.history.state_changes_during_period",
            new=blocked_query,
        ),
    ):
        try:
            assert await async_setup_component(hass, "sensor", config)
            await hass.async_block_till_done()
            release.set()
            await hass.async_start()
            await hass.async_block_till_done()
            assert hass.states.get("sensor.blocked_average").state == "20.0"
            release.clear()
            started.clear()
            submit.reset_mock()
            created[0]._last_update = None
            task = asyncio.create_task(
                created[0].async_update_ha_state(force_refresh=True)
            )
            await asyncio.wait_for(started.wait(), timeout=3)
            entry = hass.config_entries.async_entries("average")[0]
            entity_id = "sensor.blocked_average"
            identity = er.async_get(hass).async_get(entity_id).unique_id
            for source in ("sensor.b", "sensor.c"):
                replacement_added.clear()
                if method == "options":
                    form = await hass.config_entries.options.async_init(entry.entry_id)
                    result = await hass.config_entries.options.async_configure(
                        form["flow_id"], user_input={"entities": [source]}
                    )
                    assert result["type"] == "create_entry"
                else:
                    changed = deepcopy(config)
                    changed["sensor"][0]["entities"] = [source]
                    config_path.write_text(yaml.safe_dump(changed))
                    await hass.services.async_call(
                        "average", "reload", {}, blocking=True
                    )
                await asyncio.wait_for(replacement_added.wait(), timeout=3)
                await asyncio.sleep(0.05)
                assert entry.state is ConfigEntryState.LOADED
                assert created[0]._stopping
                assert submit.call_count == 1
        finally:
            release.set()
            if task is not None:
                await task
            await hass.async_block_till_done()
        assert len(created) == 3
        await created[-1].async_update_ha_state(force_refresh=True)
        assert hass.states.get(entity_id).state == "60.0"
        assert er.async_get(hass).async_get(entity_id).unique_id == identity
        assert [
            item.entry_id for item in hass.config_entries.async_entries("average")
        ] == [entry.entry_id]
        assert submit.call_count == 2
        assert created[-1].sources == ["sensor.c"]
        assert created[-1]._duration == timedelta(minutes=5)
