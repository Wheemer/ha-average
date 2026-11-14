"""Malformed large temperature histories cannot generate a traceback per point."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.average.sensor import AverageSensor


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("bad_kind", ["value", "unit"])
async def test_large_bad_history_bounds_logging_and_recovers(
    hass, caplog, selected, bad_kind
):
    """Keep the first traceback and a source summary, retaining valid intervals."""
    size = 1000
    end = dt_util.utcnow().replace(microsecond=0)
    start = end - timedelta(seconds=size)
    sources = ["sensor.a", "sensor.b"]
    config = {
        "entities": sources,
        "duration": timedelta(seconds=size),
        "require_all_sources": True,
        "unique_id": "stable_errors",
    }
    if selected:
        config["source_attributes"] = dict.fromkeys(sources, "temperature")
    records = {}
    for source, value in zip(sources, [20, 40], strict=True):
        live = (
            {"temperature": value, "temperature_unit": "°C"}
            if selected
            else {"unit_of_measurement": "°C"}
        )
        hass.states.async_set(source, "ready" if selected else str(value), live)
        records[source] = []
        for index in range(size):
            broken = index < size // 2
            reading = "broken" if broken and bad_kind == "value" else value
            unit = "invalid_unit" if broken and bad_kind == "unit" else "°C"
            attrs = (
                {"temperature": reading, "temperature_unit": unit}
                if selected
                else {"unit_of_measurement": unit}
            )
            timestamp = start + timedelta(seconds=index)
            records[source].append(
                State(
                    source,
                    "ready" if selected else str(reading),
                    attrs,
                    last_changed=timestamp,
                    last_updated=timestamp,
                )
            )
    sensor = AverageSensor(hass, config)

    async def period() -> None:
        sensor._period = start, end
        sensor._actual_end = end

    sensor._async_update_period = period
    recorder = Mock(async_add_executor_job=AsyncMock(return_value=records))

    def conversion_errors() -> list:
        return [
            record
            for record in caplog.records
            if record.name == "custom_components.average.sensor"
            and record.levelno == logging.ERROR
        ]

    with patch("custom_components.average.sensor.get_instance", return_value=recorder):
        await sensor._async_update_state()
        errors = conversion_errors()
        assert len(errors) == 2
        assert all(record.exc_info for record in errors)
        for source in sources:
            assert sum(source in record.getMessage() for record in errors) == 1
            assert any(
                source in record.getMessage() and "501 times" in record.getMessage()
                for record in caplog.records
            )
        assert sensor.native_value == 30
        assert sensor.available_sources == 2
        assert sensor.available
        assert sensor.native_unit_of_measurement == "°C"
        assert sensor.unique_id == "stable_errors"
        # The error budget resets on the next real calculation, rather than
        # hiding persistent problems for the entity's entire lifetime.
        sensor._period = None
        await sensor._async_update_state()
        assert len(conversion_errors()) == 4
        # Good data arriving after failures still contributes normally.
        for source, value in zip(sources, [20, 40], strict=True):
            attrs = (
                {"temperature": value, "temperature_unit": "°C"}
                if selected
                else {"unit_of_measurement": "°C"}
            )
            records[source] = [
                State(
                    source,
                    "ready" if selected else str(value),
                    attrs,
                    last_changed=start,
                    last_updated=start,
                )
            ]
        sensor._period = None
        await sensor._async_update_state()
        assert len(conversion_errors()) == 4
        assert sensor.native_value == 30
        assert sensor.min_value == 20
        assert sensor.max_value == 40
        assert sensor.available
