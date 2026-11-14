"""Native YAML checking and Quick Reload regression coverage for #217/#243."""

import asyncio
import json
from pathlib import Path

import pytest
import yaml
from homeassistant import config as hass_config
from homeassistant.components.homeassistant.services import _async_handle_reload_all
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .const import MOCK_CONFIG, TEST_ENTITY_IDS, TEST_NAME


def write_config(hass, tmp_path, config):
    """Use an isolated configuration directory with the actual integration files."""
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text(
        yaml.safe_dump(json.loads(json.dumps(config)))
    )
    custom = tmp_path / "custom_components"
    if not custom.exists():
        custom.symlink_to(
            Path(__file__).parents[1] / "custom_components", target_is_directory=True
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"duration": {"minutes": 5}},
        {
            "start": "{{ now().replace(hour=0, minute=0, second=0) }}",
            "end": "{{ now() }}",
        },
    ],
)
async def test_native_configuration_check_finishes_without_import_side_effects(
    hass, tmp_path, overrides
):
    """Validate the reported YAML setup with the real Core checker, bounded in time."""
    config = json.loads(json.dumps(MOCK_CONFIG))
    config["sensor"][0].update(overrides)
    write_config(hass, tmp_path, config)
    before_entries = list(hass.config_entries.async_entries("average"))
    before_states = list(hass.states.async_all())
    errors = await asyncio.wait_for(
        hass_config.async_check_ha_config_file(hass), timeout=10
    )
    assert errors is None
    assert hass.config_entries.async_entries("average") == before_entries
    assert hass.states.async_all() == before_states


@pytest.mark.parametrize("keep_yaml", [False, True])
async def test_native_quick_reload_preserves_sensor_and_source_listener(
    hass, tmp_path, keep_yaml
):
    """Run Core's Quick Reload handler and the actual Average reload service."""
    write_config(hass, tmp_path, MOCK_CONFIG)
    for entity_id in TEST_ENTITY_IDS:
        hass.states.async_set(entity_id, "20", {"unit_of_measurement": "°C"})
    assert await async_setup_component(hass, "sensor", MOCK_CONFIG)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entity_id = f"sensor.{TEST_NAME}"
    entry = hass.config_entries.async_entries("average")[0]
    original_options = dict(entry.options)
    original_unique_id = er.async_get(hass).async_get(entity_id).unique_id
    assert hass.states.get(entity_id).state == "20.0"
    if not keep_yaml:
        (tmp_path / "configuration.yaml").write_text("sensor: []\n")

    async def unrelated_reload(_call) -> None:
        return

    # Keep unrelated Core/theme behavior outside this integration test.
    for domain, service in [
        ("homeassistant", "reload_core_config"),
        ("homeassistant", "reload_custom_templates"),
        ("frontend", "reload_themes"),
    ]:
        hass.services.async_register(domain, service, unrelated_reload)
    hass.services.async_register(
        "homeassistant", "reload_all", _async_handle_reload_all
    )
    await asyncio.wait_for(
        hass.services.async_call("homeassistant", "reload_all", {}, blocking=True),
        timeout=10,
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "20.0"
    assert er.async_get(hass).async_get(entity_id).unique_id == original_unique_id
    assert entry.options == original_options
    assert [e.entry_id for e in hass.config_entries.async_entries("average")] == [
        entry.entry_id
    ]
    for source in TEST_ENTITY_IDS:
        hass.states.async_set(source, "22", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "22.0"
