"""Tests for the Average Sensor config flow."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    UnitOfTemperature,
)
from homeassistant.core import CoreState, State
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.average.config_flow import SECTION_ADVANCED
from custom_components.average.const import (
    CONF_DURATION,
    CONF_END,
    CONF_MAX_SOURCE_AGE,
    CONF_PRECISION,
    CONF_START,
    DOMAIN,
)
from custom_components.average.sensor import (
    YAML_IMPORT_ISSUE_ID,
    async_setup_entry,
    async_setup_platform,
)

from .const import MOCK_CONFIG, TEST_ENTITY_IDS, TEST_NAME


async def test_user_flow_creates_entry(hass):
    """Test creating an average sensor from the UI."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: TEST_ENTITY_IDS,
            CONF_DURATION: {"seconds": 30},
            CONF_PRECISION: 2,
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == TEST_NAME
    assert result["data"] == {}
    assert result["options"][CONF_NAME] == TEST_NAME
    assert result["options"][CONF_ENTITIES] == TEST_ENTITY_IDS
    assert result["options"][CONF_DURATION] == {"seconds": 30}
    assert CONF_SCAN_INTERVAL not in result["options"]


async def test_user_flow_rejects_invalid_period(hass):
    """Test invalid period choices are rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: TEST_ENTITY_IDS,
            SECTION_ADVANCED: {
                CONF_START: "{{ now() }}",
                CONF_END: "{{ now() }}",
            },
            CONF_DURATION: {"seconds": 30},
            CONF_PRECISION: 2,
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "too_many_period_options"}


async def test_options_flow_updates_entry(hass):
    """Test updating an average sensor from the options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={},
        options={
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: TEST_ENTITY_IDS,
            CONF_PRECISION: 2,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENTITIES: TEST_ENTITY_IDS,
            CONF_DURATION: {"seconds": 60},
            CONF_PRECISION: 1,
            SECTION_ADVANCED: {
                CONF_MAX_SOURCE_AGE: {"minutes": 15},
            },
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_DURATION] == {"seconds": 60}
    assert CONF_SCAN_INTERVAL not in result["data"]
    assert result["data"][CONF_MAX_SOURCE_AGE] == {"minutes": 15}


async def test_setup_entry_adds_sensor(hass):
    """Test sensor setup from a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={},
        options={
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: TEST_ENTITY_IDS,
            CONF_DURATION: {"seconds": 30},
            CONF_PRECISION: 2,
        },
    )
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    sensor = async_add_entities.call_args.args[0][0]
    assert sensor.name == TEST_NAME
    assert sensor.sources == TEST_ENTITY_IDS
    assert sensor._duration == timedelta(seconds=30)
    assert sensor._update_interval == timedelta(seconds=30)


async def test_config_entry_unloads_and_reloads(hass):
    """Test config entry setup, unload, and reload."""
    hass.states.async_set(TEST_ENTITY_IDS[0], "4")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={},
        options={
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: [TEST_ENTITY_IDS[0]],
            CONF_UNIQUE_ID: TEST_NAME,
            CONF_PRECISION: 2,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    unloaded_state = hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")
    assert unloaded_state is not None
    assert unloaded_state.attributes["restored"] is True

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    reloaded_state = hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")
    assert reloaded_state
    assert "restored" not in reloaded_state.attributes


async def test_config_entry_restores_state_before_period_refresh(hass):
    """Test a period sensor restores its previous state while waiting to refresh."""
    mock_restore_cache(
        hass,
        [
            State(
                f"{SENSOR_DOMAIN}.{TEST_NAME}",
                "21.25",
                {
                    "available_sources": 1,
                    "count": 1,
                    "count_sources": 1,
                    "unit_of_measurement": UnitOfTemperature.CELSIUS,
                },
            )
        ],
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={},
        options={
            CONF_NAME: TEST_NAME,
            CONF_ENTITIES: [TEST_ENTITY_IDS[0]],
            CONF_UNIQUE_ID: TEST_NAME,
            CONF_DURATION: {"seconds": 30},
            CONF_PRECISION: 2,
        },
    )
    entry.add_to_hass(hass)

    hass.set_state(CoreState.not_running)
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
    finally:
        hass.set_state(CoreState.running)

    state = hass.states.get(f"{SENSOR_DOMAIN}.{TEST_NAME}")
    assert state is not None
    assert state.state == "21.25"
    assert state.attributes["available_sources"] == 1


async def test_yaml_import_creates_config_entry(hass):
    """Test importing YAML as a config entry."""
    yaml_config = deepcopy(MOCK_CONFIG[SENSOR_DOMAIN][0])
    yaml_config[CONF_UNIQUE_ID] = "test_name"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data=yaml_config,
    )

    assert result["type"] == "create_entry"
    assert result["title"] == TEST_NAME
    assert result["data"] == {}
    assert result["options"][CONF_NAME] == TEST_NAME
    assert result["options"][CONF_ENTITIES] == TEST_ENTITY_IDS
    assert result["options"][CONF_UNIQUE_ID] == "test_name"


async def test_yaml_setup_imports_and_creates_repair(hass):
    """Test YAML setup imports config and creates one repair issue."""
    yaml_config = deepcopy(MOCK_CONFIG[SENSOR_DOMAIN][0])
    second_yaml_config = deepcopy(yaml_config)
    second_yaml_config[CONF_NAME] = "another_test_name"
    second_yaml_config[CONF_UNIQUE_ID] = "another_test_name"
    async_add_entities = MagicMock()

    await async_setup_platform(hass, yaml_config, async_add_entities)
    await async_setup_platform(hass, second_yaml_config, async_add_entities)
    await hass.async_block_till_done()

    async_add_entities.assert_not_called()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 2
    assert entries[0].options[CONF_NAME] == TEST_NAME

    issue_registry = ir.async_get(hass)
    issues = [
        issue
        for issue in issue_registry.issues.values()
        if issue.domain == DOMAIN and issue.issue_id == YAML_IMPORT_ISSUE_ID
    ]

    assert len(issues) == 1
    issue = issue_registry.async_get_issue(DOMAIN, YAML_IMPORT_ISSUE_ID)
    assert issue is not None
    assert issue.translation_key == "yaml_imported"
    assert issue.translation_placeholders == {
        "name": "Average Sensor YAML configuration"
    }
