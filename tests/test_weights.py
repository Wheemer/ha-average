"""Optional per-source weighting without changes to existing sensor identities."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.core import State
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.util import dt as dt_util

from custom_components.average.config_flow import (
    OPTIONS_SCHEMA,
    _yaml_config_to_options,
    suggested_options,
    validate_options,
)
from custom_components.average.sensor import (
    PLATFORM_SCHEMA,
    AverageSensor,
    _entry_config,
)
from custom_components.average.weights import normalize_weights


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ({}, 25),
        ({"sensor.a": 2}, 20),
        ({"sensor.a": 0, "sensor.b": 1}, 40),
        ({"sensor.a": 0.5, "sensor.b": 0.5}, 25),
        ({"sensor.a": 1e308, "sensor.b": 1e308}, 25),
    ],
)
async def test_instantaneous_weights_and_unchanged_identity(hass, weights, expected):
    """Weights are relative, with default weight one and stable explicit identity."""
    hass.states.async_set("sensor.a", "10")
    hass.states.async_set("sensor.b", "40")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "unique_id": "preserved",
            "weights": weights,
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == expected
    assert sensor.unique_id == "preserved"
    assert sensor.count_sources == sensor.available_sources == 2


@pytest.mark.parametrize("strict", [False, True])
async def test_zero_weight_does_not_bypass_strict_source_requirement(hass, strict):
    """All configured sources remain required in strict mode, even at zero weight."""
    hass.states.async_set("sensor.a", "10")
    hass.states.async_set("sensor.b", "unavailable")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "weights": {"sensor.b": 0},
            "require_all_sources": strict,
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 10
    assert sensor.available is not strict
    hass.states.async_set("sensor.b", "40")
    await sensor._async_update_state()
    assert sensor.available
    assert sensor.native_value == 10


async def test_only_zero_weight_sources_available_gives_no_result(hass):
    """A valid zero-weight source cannot create a weighted result on its own."""
    hass.states.async_set("sensor.a", "unavailable")
    hass.states.async_set("sensor.b", "40")
    sensor = AverageSensor(
        hass, {"entities": ["sensor.a", "sensor.b"], "weights": {"sensor.b": 0}}
    )
    await sensor._async_update_state()
    assert sensor.native_value is None
    assert not sensor.available


async def test_history_weights_apply_after_per_source_time_weighting(hass):
    """Weight source means equally in time before applying source contributions."""
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=30)
    hass.states.async_set("sensor.a", "40")
    hass.states.async_set("sensor.b", "90")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "duration": timedelta(seconds=30),
            "weights": {"sensor.a": 2, "sensor.b": 1},
        },
    )

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end + timedelta(seconds=30)

    sensor._async_update_period = period
    history = {
        "sensor.a": [
            State("sensor.a", "10", last_changed=start),
            State("sensor.a", "40", last_changed=start + timedelta(seconds=20)),
        ],
        "sensor.b": [State("sensor.b", "90", last_changed=start)],
    }
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=history))
    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
    assert sensor.native_value == 43.33
    assert sensor.trending_towards == pytest.approx((43.33 + 56.67) / 2)
    assert sensor.min_value == 10
    assert sensor.max_value == 90


@pytest.mark.parametrize(
    "weights",
    [
        {"sensor.a": -1},
        {"sensor.a": "nan"},
        {"sensor.a": "inf"},
        {"sensor.a": True},
        {"sensor.a": "bad"},
        {"sensor.other": 1},
        {"sensor.a": 0, "sensor.b": 0},
        None,
        [],
    ],
)
async def test_invalid_weights_rejected_in_yaml_and_ui(weights):
    """Reject invalid or irrelevant mappings before an entity is created."""
    config = {
        "platform": "average",
        "entities": ["sensor.a", "sensor.b"],
        "weights": weights,
    }
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(config)
    with pytest.raises(SchemaFlowError):
        await validate_options(
            SimpleNamespace(options={}),
            {"entities": config["entities"], "advanced": {"weights": weights}},
        )


async def test_weight_import_ui_preservation_and_explicit_clear():
    """The Advanced form keeps flat stored weights, and an empty map clears them."""
    old = _yaml_config_to_options(
        {
            "name": "Average",
            "entities": ["sensor.a", "sensor.b"],
            "unique_id": "stable",
            "weights": {"sensor.a": 2},
        }
    )
    handler = SimpleNamespace(options=old)
    result = await validate_options(handler, {"entities": old["entities"]})
    assert result["weights"] == {"sensor.a": 2}
    cleared = await validate_options(
        SimpleNamespace(options=old),
        {"entities": old["entities"], "advanced": {"weights": {}}},
    )
    assert cleared["weights"] == {}
    assert "advanced" not in cleared
    assert normalize_weights({}, ["sensor.a", "sensor.b"]) == {}


async def test_partial_weighted_average_renormalizes_remaining_sources(hass):
    """Unavailable inputs do not retain phantom contributions in partial mode."""
    hass.states.async_set("sensor.a", "10")
    hass.states.async_set("sensor.b", "unavailable")
    sensor = AverageSensor(
        hass,
        {
            "entities": ["sensor.a", "sensor.b"],
            "weights": {"sensor.a": 2, "sensor.b": 8},
        },
    )
    await sensor._async_update_state()
    assert sensor.native_value == 10
    assert sensor.available
    hass.states.async_set("sensor.b", "40")
    await sensor._async_update_state()
    assert sensor.native_value == 34


@pytest.mark.parametrize("precision", [-1, 9])
async def test_ui_accepts_legacy_yaml_precision(hass, precision):
    """UI controls must not impose a smaller precision range than existing YAML."""
    old = _yaml_config_to_options(
        {
            "name": "Legacy",
            "entities": ["sensor.a"],
            "unique_id": "stable",
            "precision": precision,
            "duration": timedelta(milliseconds=500),
            "max_source_age": timedelta(milliseconds=750),
        }
    )
    handler = SimpleNamespace(options=dict(old))
    form = await suggested_options(handler)
    form.pop("name")
    form.pop("unique_id")
    saved = await validate_options(handler, OPTIONS_SCHEMA(form))
    combined = {**old, **saved}
    runtime = _entry_config(
        hass, SimpleNamespace(data={}, options=combined, entry_id="same")
    )
    assert runtime["precision"] == precision
    assert runtime["duration"] == timedelta(milliseconds=500)
    assert runtime["max_source_age"] == timedelta(milliseconds=750)
    assert runtime["unique_id"] == "stable"
