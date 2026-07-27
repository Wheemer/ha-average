"""Tests for the Average Sensor config flow."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
)
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.average.const import (
    CONF_DURATION,
    CONF_END,
    CONF_MAX_SOURCE_AGE,
    CONF_PRECISION,
    CONF_START,
    DOMAIN,
)
from custom_components.average.sensor import (
    _yaml_import_issue_id,
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
            CONF_SCAN_INTERVAL: {"minutes": 5},
            CONF_PRECISION: 2,
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == TEST_NAME
    assert result["data"] == {}
    assert result["options"][CONF_NAME] == TEST_NAME
    assert result["options"][CONF_ENTITIES] == TEST_ENTITY_IDS
    assert result["options"][CONF_DURATION] == {"seconds": 30}
    assert result["options"][CONF_SCAN_INTERVAL] == {"minutes": 5}


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
            CONF_START: "{{ now() }}",
            CONF_END: "{{ now() }}",
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
            CONF_SCAN_INTERVAL: {"minutes": 10},
            CONF_PRECISION: 1,
            CONF_MAX_SOURCE_AGE: {"minutes": 15},
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_DURATION] == {"seconds": 60}
    assert result["data"][CONF_SCAN_INTERVAL] == {"minutes": 10}
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
            CONF_SCAN_INTERVAL: {"minutes": 5},
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
    assert sensor._update_interval == timedelta(minutes=5)


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
    """Test YAML setup imports config and asks the user to remove YAML."""
    yaml_config = deepcopy(MOCK_CONFIG[SENSOR_DOMAIN][0])
    async_add_entities = MagicMock()

    await async_setup_platform(hass, yaml_config, async_add_entities)
    await hass.async_block_till_done()

    async_add_entities.assert_not_called()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].options[CONF_NAME] == TEST_NAME

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(
        DOMAIN,
        _yaml_import_issue_id(yaml_config),
    )
    assert issue is not None
    assert issue.translation_key == "yaml_imported"
