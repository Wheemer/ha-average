"""Import notices must describe verified migration without editing YAML."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.average.sensor import async_setup_platform

from .const import MOCK_CONFIG


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"type": FlowResultType.CREATE_ENTRY}, True),
        ({"type": FlowResultType.ABORT, "reason": "already_configured"}, True),
        ({"type": FlowResultType.ABORT, "reason": "invalid_config"}, False),
        ({"type": FlowResultType.FORM}, False),
    ],
)
async def test_notice_only_follows_completed_import(hass, result, expected):
    """Failed or unfinished flows must not claim that YAML was imported."""
    config = {"platform": "average", "name": "test", "entities": ["sensor.a"]}
    with (
        patch.object(
            hass.config_entries.flow, "async_init", AsyncMock(return_value=result)
        ),
        patch("custom_components.average.sensor.async_create_issue") as notice,
    ):
        await async_setup_platform(hass, config, Mock())
    assert notice.called is expected
    if expected:
        assert notice.call_args.args[:3] == (hass, "average", "yaml_imported")


async def test_actual_yaml_import_creates_repair_notice(hass):
    """A real platform import exposes the notice in HA's issue registry."""
    assert await async_setup_component(hass, "sensor", MOCK_CONFIG)
    await hass.async_block_till_done()
    notice = ir.async_get(hass).async_get_issue("average", "yaml_imported")
    assert notice is not None
    assert notice.translation_key == "yaml_imported"
    assert notice.is_persistent
    assert len(hass.config_entries.async_entries("average")) == 1
