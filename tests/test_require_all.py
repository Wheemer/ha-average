"""Exercise the actual availability property without a Home Assistant runtime."""

import __future__

import ast
import asyncio
import math
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

source = Path(__file__).with_name("sensor.py")
if not source.exists():
    source = Path(__file__).parents[1] / "custom_components/average/sensor.py"
tree = ast.parse(source.read_text())
cls = next(
    n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AverageSensor"
)
method = next(
    n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "available"
)
method.decorator_list = []
ns = {"math": math, "dt_util": SimpleNamespace(utcnow=lambda: datetime.now(UTC))}
exec(
    compile(
        ast.Module(body=[method], type_ignores=[]),
        "sensor.py",
        "exec",
        flags=__future__.annotations.compiler_flag,
    ),
    ns,
)

added = next(
    n
    for n in cls.body
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_added_to_hass"
)
listeners = []


def track(hass, sources, listener):
    listeners.append(listener)
    return lambda: None


ns.update(
    callback=lambda func: func,
    Event=lambda name: name,
    EVENT_HOMEASSISTANT_STOP="homeassistant_stop",
    async_track_state_change_event=track,
)
exec(
    compile(
        ast.Module(body=[added], type_ignores=[]),
        "sensor.py",
        "exec",
        flags=__future__.annotations.compiler_flag,
    ),
    ns,
)


class RequireAllTests(unittest.TestCase):
    def test_history_window_subscribes_and_publishes_loss_before_recalculation(self):
        listeners.clear()
        calls = []

        async def update():
            calls.append("recalculate")

        sensor = SimpleNamespace(
            _require_all_sources=True,
            _has_period=True,
            sources=["top", "bottom"],
            hass=SimpleNamespace(
                is_running=True,
                is_stopping=False,
                bus=SimpleNamespace(async_listen_once=Mock(return_value=Mock())),
            ),
            _attr_native_value=35,
            _async_restore_previous_state=AsyncMock(),
            async_on_remove=Mock(),
            async_schedule_update_ha_state=Mock(),
            async_write_ha_state=lambda: calls.append("publish"),
            _async_update_state=update,
            async_update=update,
        )
        asyncio.run(ns["async_added_to_hass"](sensor))
        self.assertEqual(len(listeners), 1)
        asyncio.run(listeners[0](None))
        self.assertEqual(calls, ["publish", "recalculate"])

    def test_loss_nonfinite_stale_recovery_and_default(self):
        states = {
            "top": SimpleNamespace(state="40"),
            "bottom": SimpleNamespace(state="30"),
        }
        s = SimpleNamespace(
            _require_all_sources=True,
            sources=["top", "bottom"],
            count_sources=2,
            available_sources=2,
            _attr_native_value=35,
            _temperature_mode=False,
            _get_source_value=lambda state: state.state,
            _is_source_stale=lambda state, now: False,
            _has_state=lambda value: value is not None,
            hass=SimpleNamespace(states=SimpleNamespace(get=states.get)),
        )
        self.assertTrue(ns["available"](s))
        for bad in ["unknown", "unavailable", "nan", "inf", None]:
            states["bottom"].state = bad
            self.assertFalse(ns["available"](s))
        states["bottom"].state = "30"
        self.assertTrue(ns["available"](s))
        s._is_source_stale = lambda state, now: True
        self.assertFalse(ns["available"](s))
        s._require_all_sources = False
        s.available_sources = 1
        self.assertTrue(ns["available"](s))


if __name__ == "__main__":
    unittest.main()
