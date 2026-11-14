"""Active YAML edits must reach a loaded entry when Average is reloaded."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import yaml
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component


def config_for(source):
    """Keep identity fixed while editing the YAML source selection."""
    return {
        "sensor": [
            {
                "platform": "average",
                "name": "Reload Average",
                "unique_id": "stable_yaml_id",
                "entities": [source],
            }
        ]
    }


async def test_yaml_reload_applies_source_edit_without_restart(hass, tmp_path):
    """Reloading YAML must update the running entity, not only saved options."""
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).parents[1] / "custom_components", target_is_directory=True
    )
    initial = config_for("sensor.a")
    (tmp_path / "configuration.yaml").write_text(yaml.safe_dump(initial))
    hass.states.async_set("sensor.a", "20", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.b", "40", {"unit_of_measurement": "°C"})
    assert await async_setup_component(hass, "sensor", initial)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entity_id = "sensor.reload_average"
    entry = hass.config_entries.async_entries("average")[0]
    unique_id = er.async_get(hass).async_get(entity_id).unique_id
    assert hass.states.get(entity_id).state == "20.0"
    (tmp_path / "configuration.yaml").write_text(yaml.safe_dump(config_for("sensor.b")))
    await asyncio.wait_for(
        hass.services.async_call("average", "reload", {}, blocking=True), timeout=10
    )
    await hass.async_block_till_done()
    assert entry.options["entities"] == ["sensor.b"]
    assert hass.states.get(entity_id).state == "40.0"
    assert er.async_get(hass).async_get(entity_id).unique_id == unique_id
    assert [e.entry_id for e in hass.config_entries.async_entries("average")] == [
        entry.entry_id
    ]
    hass.states.async_set("sensor.a", "99", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "40.0"
    hass.states.async_set("sensor.b", "42", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "42.0"


async def test_yaml_without_explicit_id_updates_precision_and_skips_unchanged_reload(
    hass, tmp_path
):
    """Stable import fingerprints must still apply non-identity YAML options."""
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).parents[1] / "custom_components", target_is_directory=True
    )
    config = config_for("sensor.a")
    config["sensor"][0].pop("unique_id")
    (tmp_path / "configuration.yaml").write_text(yaml.safe_dump(config))
    hass.states.async_set("sensor.a", "20.12345", {"unit_of_measurement": "°C"})
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries("average")[0]
    entity_id = "sensor.reload_average"
    unique_id = er.async_get(hass).async_get(entity_id).unique_id
    assert hass.states.get(entity_id).state == "20.12"
    config["sensor"][0]["precision"] = 3
    (tmp_path / "configuration.yaml").write_text(yaml.safe_dump(config))
    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
        wraps=hass.config_entries.async_schedule_reload,
    ) as scheduled:
        await hass.services.async_call("average", "reload", {}, blocking=True)
        await hass.async_block_till_done()
        scheduled.assert_called_once_with(entry.entry_id)
    assert hass.states.get(entity_id).state == "20.123"
    assert er.async_get(hass).async_get(entity_id).unique_id == unique_id
    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
        wraps=hass.config_entries.async_schedule_reload,
    ) as scheduled:
        await hass.services.async_call("average", "reload", {}, blocking=True)
        await hass.async_block_till_done()
        scheduled.assert_not_called()
    assert len(hass.config_entries.async_entries("average")) == 1


async def test_ui_source_count_edit_remains_available_in_strict_mode(hass):
    """Restoring old diagnostics cannot override a newly configured source count."""
    initial = config_for("sensor.a")
    initial["sensor"][0]["entities"] = ["sensor.a", "sensor.b"]
    initial["sensor"][0]["require_all_sources"] = True
    hass.states.async_set("sensor.a", "20", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.b", "40", {"unit_of_measurement": "°C"})
    assert await async_setup_component(hass, "sensor", initial)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries("average")[0]
    entity_id = "sensor.reload_average"
    unique_id = er.async_get(hass).async_get(entity_id).unique_id
    assert hass.states.get(entity_id).state == "30.0"
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={"entities": ["sensor.a"], "require_all_sources": True},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "20.0"
    assert state.attributes["count_sources"] == 1
    assert state.attributes["available_sources"] == 1
    assert er.async_get(hass).async_get(entity_id).unique_id == unique_id
