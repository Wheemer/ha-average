"""The test for the average integration."""

# pylint: disable=redefined-outer-name
from __future__ import annotations

from unittest.mock import patch

from homeassistant import config as hass_config
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import SERVICE_RELOAD
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.average.const import DOMAIN

from . import get_fixture_path
from .const import MOCK_CONFIG, TEST_ENTITY_IDS, TEST_NAME


async def test_reload(hass):
    """Verify we can reload."""
    assert await async_setup_component(hass, SENSOR_DOMAIN, MOCK_CONFIG)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 1

    assert hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")

    yaml_path = get_fixture_path("configuration.yaml")

    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, {}, blocking=True)
        await hass.async_block_till_done()

    assert hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")


async def test_removing_yaml_preserves_imported_entry(hass):
    """Removing YAML must not delete an imported entry or its identity."""
    assert await async_setup_component(hass, SENSOR_DOMAIN, MOCK_CONFIG)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 1

    assert hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    original_entry_id = entries[0].entry_id

    original_unique_id = (
        er.async_get(hass).async_get(f"{SENSOR_DOMAIN}.{TEST_NAME}").unique_id
    )
    yaml_path = get_fixture_path("configuration_empty.yaml")

    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, {}, blocking=True)
        await hass.async_block_till_done()

    assert hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}") is not None
    assert [entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)] == [
        original_entry_id
    ]
    assert (
        er.async_get(hass).async_get(f"{SENSOR_DOMAIN}.{TEST_NAME}").unique_id
        == original_unique_id
    )


async def test_config_entry_reload_preserves_available_sensor(hass):
    """Reload an imported entry with valid readings and stable identity."""
    for entity_id in TEST_ENTITY_IDS:
        hass.states.async_set(entity_id, "20", {"unit_of_measurement": "°C"})
    assert await async_setup_component(hass, SENSOR_DOMAIN, MOCK_CONFIG)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entity_id = f"{SENSOR_DOMAIN}.{TEST_NAME}"
    unique_id = er.async_get(hass).async_get(entity_id).unique_id
    assert hass.states.get(entity_id).state == "20.0"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "20.0"
    assert er.async_get(hass).async_get(entity_id).unique_id == unique_id
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_yaml_reimport_reuses_entry_and_unique_id(hass):
    """Repeated import must not create a second entry or entity identity."""
    assert await async_setup_component(hass, SENSOR_DOMAIN, MOCK_CONFIG)
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    original_entry_id = entries[0].entry_id
    original_unique_id = (
        er.async_get(hass).async_get(f"{SENSOR_DOMAIN}.{TEST_NAME}").unique_id
    )
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data=MOCK_CONFIG[SENSOR_DOMAIN][0]
    )
    await hass.async_block_till_done()
    assert [e.entry_id for e in hass.config_entries.async_entries(DOMAIN)] == [
        original_entry_id
    ]
    assert (
        er.async_get(hass).async_get(f"{SENSOR_DOMAIN}.{TEST_NAME}").unique_id
        == original_unique_id
    )
