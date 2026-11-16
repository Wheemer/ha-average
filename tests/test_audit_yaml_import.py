"""Regression coverage for destructive YAML import collisions."""

from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.average.config_flow import _yaml_config_to_options
from custom_components.average.sensor import PLATFORM_SCHEMA, AverageSensor
from custom_components.average.yaml_import import (
    prepare_yaml_import,
    report_duplicate_id,
)


def yaml_sensor(name, source, unique_id):
    """Build one legacy-compatible YAML block."""
    return {
        "platform": "average",
        "name": name,
        "entities": [source],
        "unique_id": unique_id,
    }


async def test_legacy_marker_preserves_both_sensors_and_entity_ids(hass):
    """The marker is per-sensor behavior, never a shared import identity."""
    configs = [
        yaml_sensor("First", "sensor.a", "__legacy__"),
        yaml_sensor("Second", "sensor.b", "__legacy__"),
    ]
    registry = er.async_get(hass)
    existing = []
    for config in configs:
        unique_id = AverageSensor(hass, PLATFORM_SCHEMA(config)).unique_id
        existing.append(
            registry.async_get_or_create(
                "sensor",
                "average",
                unique_id,
                suggested_object_id=config["name"].lower(),
            )
        )
    assert await async_setup_component(hass, "sensor", {"sensor": configs})
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries("average")
    assert len(entries) == 2
    assert {entry.title for entry in entries} == {"First", "Second"}
    for entity in existing:
        assert registry.async_get(entity.entity_id).unique_id == entity.unique_id
        assert registry.async_get(entity.entity_id).config_entry_id in {
            entry.entry_id for entry in entries
        }


async def test_duplicate_explicit_yaml_ids_do_not_overwrite_existing_entry(hass):
    """Reject the entire ambiguous ID instead of letting the last block win."""
    config = yaml_sensor("Original", "sensor.original", "duplicate")
    options = _yaml_config_to_options(PLATFORM_SCHEMA(config))
    entry = MockConfigEntry(
        domain="average",
        title="Original",
        data={},
        options=options,
        unique_id="yaml_duplicate",
    )
    entry.add_to_hass(hass)
    duplicate = {
        "sensor": [
            yaml_sensor("First", "sensor.a", "duplicate"),
            yaml_sensor("Second", "sensor.b", "duplicate"),
        ]
    }
    with patch("custom_components.average.async_setup_entry", return_value=True):
        assert await async_setup_component(hass, "sensor", duplicate)
        await hass.async_block_till_done()
    assert any(
        issue.translation_key == "duplicate_yaml_id"
        for issue in ir.async_get(hass).issues.values()
    )
    assert entry.options == options
    assert entry.title == "Original"
    assert len(hass.config_entries.async_entries("average")) == 1


async def test_direct_conflicting_import_does_not_replace_first(hass):
    """A conflicting import flow must abort with a distinct reason."""
    with patch("custom_components.average.async_setup_entry", return_value=True):
        first = await hass.config_entries.flow.async_init(
            "average",
            context={"source": "import"},
            data=PLATFORM_SCHEMA(yaml_sensor("First", "sensor.a", "duplicate")),
        )
        second = await hass.config_entries.flow.async_init(
            "average",
            context={"source": "import"},
            data=PLATFORM_SCHEMA(yaml_sensor("Second", "sensor.b", "duplicate")),
        )
    assert first["type"] == "create_entry"
    assert second["type"] == "abort"
    assert second["reason"] == "duplicate_unique_id"
    entry = hass.config_entries.async_entries("average")[0]
    assert entry.title == "First"
    assert entry.options["entities"] == ["sensor.a"]


async def test_existing_collapsed_legacy_entry_is_reused_without_changing_its_id(hass):
    """Recover other legacy blocks while retaining an already-imported entry."""
    config = PLATFORM_SCHEMA(yaml_sensor("Existing", "sensor.a", "__legacy__"))
    entry = MockConfigEntry(
        domain="average",
        title="Existing",
        data={},
        options=_yaml_config_to_options(config),
        unique_id="yaml___legacy__",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.average.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            "average", context={"source": "import"}, data=config
        )
        other = await hass.config_entries.flow.async_init(
            "average",
            context={"source": "import"},
            data=PLATFORM_SCHEMA(yaml_sensor("Other", "sensor.b", "__legacy__")),
        )
    assert result["reason"] == "already_configured"
    assert other["type"] == "create_entry"
    assert entry.unique_id == "yaml___legacy__"
    assert entry.options["entities"] == ["sensor.a"]
    assert len(hass.config_entries.async_entries("average")) == 2


async def test_conflict_notice_clears_after_correcting_yaml(hass):
    """A resolved conflict must not leave a permanent Repairs error."""
    duplicate = {
        "sensor": [
            yaml_sensor("First", "sensor.a", "same"),
            yaml_sensor("Second", "sensor.b", "same"),
        ]
    }
    prepare_yaml_import(hass, duplicate)
    report_duplicate_id(hass, "same")
    assert any(
        issue.translation_key == "duplicate_yaml_id"
        for issue in ir.async_get(hass).issues.values()
    )
    prepare_yaml_import(hass, {"sensor": [yaml_sensor("First", "sensor.a", "same")]})
    assert not any(
        issue.translation_key == "duplicate_yaml_id"
        for issue in ir.async_get(hass).issues.values()
    )
