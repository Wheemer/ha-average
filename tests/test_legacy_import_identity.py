"""Golden YAML identities from the fork before fractional-duration support."""

from datetime import timedelta

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.average.config_flow import (
    _import_unique_id,
    _yaml_config_to_options,
)
from custom_components.average.sensor import PLATFORM_SCHEMA


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (timedelta(seconds=15), "yaml_ced366437f8f57afff2b0906a5febd327f0ec8a4"),
        (timedelta(minutes=5), "yaml_cb52bdfc21e82e289e3238041d0275bc74a9cc1a"),
        (timedelta(days=1), "yaml_f52aed839aa30457634490ccb43767255c19569e"),
    ],
)
async def test_whole_duration_retains_original_import_identity(duration, expected):
    """An int-to-float formatting change must not regenerate a legacy entry ID."""
    options = _yaml_config_to_options(
        {"name": "Legacy", "entities": ["sensor.a"], "duration": duration}
    )
    assert _import_unique_id(options) == expected


@pytest.mark.parametrize("interim", [False, True])
async def test_existing_legacy_duration_entry_is_reused_on_import(hass, interim):
    """Reimport real normalized YAML without creating a second config entry."""
    options = {
        "name": "Legacy",
        "entities": ["sensor.a"],
        "precision": 2,
        "require_all_sources": False,
        "duration": {"days": 0, "hours": 0, "minutes": 5, "seconds": 0},
    }
    identity = "yaml_cb52bdfc21e82e289e3238041d0275bc74a9cc1a"
    if interim:
        options["duration"]["seconds"] = 0.0
        identity = "yaml_38193afe61916640c10d8d3e0e7370b0a0920235"
    entry = MockConfigEntry(
        domain="average",
        title="Legacy",
        data={},
        options=options,
        unique_id=identity,
    )
    entry.add_to_hass(hass)
    config = PLATFORM_SCHEMA(
        {
            "platform": "average",
            "name": "Legacy",
            "entities": ["sensor.a"],
            "duration": {"minutes": 5},
        }
    )
    result = await hass.config_entries.flow.async_init(
        "average", context={"source": "import"}, data=config
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert [e.entry_id for e in hass.config_entries.async_entries("average")] == [
        entry.entry_id
    ]

    assert entry.unique_id == identity
