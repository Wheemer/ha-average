"""Run directly inside the native HA image; no live system or database."""

import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant

import custom_components.average.sensor as module


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.folder.name)
        self.hass.set_state(CoreState.running)
        self.hass.states.async_set("sensor.source_a", "30")
        self.hass.states.async_set("sensor.source_b", "40")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.recorder = SimpleNamespace(
            async_add_executor_job=AsyncMock(return_value={})
        )

    async def asyncTearDown(self):
        self.executor.shutdown(wait=True)
        self.folder.cleanup()

    def sensor(self, cls=module.AverageSensor):
        return cls(
            self.hass,
            {
                "unique_id": "unchanged_id",
                "entities": ["sensor.source_a", "sensor.source_b"],
                "duration": timedelta(minutes=5),
                "require_all_sources": True,
            },
        )

    async def test_old_code_reproduces_closed_executor_error(self):
        # Remove only lifecycle guards from the real refresh method to reproduce
        # the original failure without shipping a private installation snapshot.
        import ast
        import inspect
        import textwrap

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(module.AverageSensor._async_update_state))
        )

        class RemoveStopGuards(ast.NodeTransformer):
            def visit_If(self, node):
                if "_stopping" in ast.unparse(
                    node.test
                ) or "is_stopping" in ast.unparse(node.test):
                    return None
                return self.generic_visit(node)

        tree = ast.fix_missing_locations(RemoveStopGuards().visit(tree))
        namespace = dict(vars(module))
        exec(compile(tree, "unguarded_refresh", "exec"), namespace)

        class OldSensor(module.AverageSensor):
            _async_update_state = namespace["_async_update_state"]

        self.executor.shutdown(wait=True)

        async def submit(*args):
            return await asyncio.get_running_loop().run_in_executor(self.executor, dict)

        self.recorder.async_add_executor_job = submit
        self.hass.set_state(CoreState.stopping)
        with (
            patch.dict(namespace, get_instance=lambda hass: self.recorder),
            self.assertRaisesRegex(
                RuntimeError, "cannot schedule new futures after shutdown"
            ),
        ):
            await self.sensor(OldSensor)._async_update_state()

    async def test_stop_blocks_direct_and_polled_updates_without_changing_value(self):
        sensor = self.sensor()
        sensor._attr_native_value = 35
        self.hass.set_state(CoreState.stopping)
        with patch.object(module, "get_instance", return_value=self.recorder):
            await sensor._async_update_state()
            await sensor.async_update()
        self.recorder.async_add_executor_job.assert_not_awaited()
        self.assertEqual(sensor.native_value, 35)
        self.assertIsNone(sensor._last_update)

    async def test_stop_during_period_update_prevents_history_query(self):
        sensor = self.sensor()

        async def stop():
            self.hass.set_state(CoreState.stopping)

        sensor._async_update_period = stop
        with patch.object(module, "get_instance", return_value=self.recorder):
            await sensor._async_update_state()
        self.recorder.async_add_executor_job.assert_not_awaited()

    async def test_running_recorder_errors_are_not_hidden(self):
        self.recorder.async_add_executor_job.side_effect = RuntimeError(
            "unexpected recorder failure"
        )
        with (
            patch.object(module, "get_instance", return_value=self.recorder),
            self.assertRaisesRegex(RuntimeError, "unexpected recorder failure"),
        ):
            await self.sensor()._async_update_state()

    async def test_instantaneous_average_is_unchanged_and_stops_cleanly(self):
        sensor = module.AverageSensor(
            self.hass, {"entities": ["sensor.source_a", "sensor.source_b"]}
        )
        await sensor._async_update_state()
        self.assertEqual(sensor.native_value, 35)
        self.hass.set_state(CoreState.stopping)
        self.hass.states.async_set("sensor.source_a", "100")
        await sensor._async_update_state()
        self.assertEqual(sensor.native_value, 35)

    async def test_stop_during_first_query_prevents_second_query(self):
        sensor = self.sensor()

        async def query(*args):
            self.hass.set_state(CoreState.stopping)
            return {}

        self.recorder.async_add_executor_job.side_effect = query
        with patch.object(module, "get_instance", return_value=self.recorder):
            await sensor._async_update_state()
        self.assertEqual(self.recorder.async_add_executor_job.await_count, 1)

    async def test_normal_averaging_and_require_all_are_preserved(self):
        sensor = self.sensor()
        with patch.object(module, "get_instance", return_value=self.recorder):
            await sensor._async_update_state()
        self.assertEqual(self.recorder.async_add_executor_job.await_count, 2)
        self.assertEqual(sensor.native_value, 35)
        self.assertTrue(sensor.available)
        self.hass.states.async_set("sensor.source_b", "unavailable")
        self.assertFalse(sensor.available)
        self.assertEqual(sensor.unique_id, "unchanged_id")

    async def test_source_listener_does_not_update_or_publish_during_stop(self):
        sensor = self.sensor()
        sensor._async_restore_previous_state = AsyncMock()
        sensor._async_update_state = AsyncMock()
        sensor.async_write_ha_state = Mock()
        sensor.async_schedule_update_ha_state = Mock()
        unsub = Mock()
        captured = []

        def track(hass, sources, listener):
            captured.append(listener)
            return unsub

        with patch.object(module, "async_track_state_change_event", side_effect=track):
            await sensor.async_added_to_hass()
        self.hass.set_state(CoreState.stopping)
        await captured[0](None)
        sensor._async_update_state.assert_not_awaited()
        sensor.async_write_ha_state.assert_not_called()
        sensor.async_schedule_update_ha_state.reset_mock()
        self.hass.set_state(CoreState.running)

        async def stop():
            self.hass.set_state(CoreState.stopping)

        sensor._async_update_state.side_effect = stop
        await captured[0](None)
        sensor.async_schedule_update_ha_state.assert_not_called()

    async def test_stop_latch_survives_close_and_unsubscribes_source(self):
        sensor = self.sensor()
        sensor._async_restore_previous_state = AsyncMock()
        sensor.async_schedule_update_ha_state = Mock()
        unsub = Mock()
        captured = []

        def track(hass, sources, listener):
            captured.append(listener)
            return unsub

        with patch.object(module, "async_track_state_change_event", side_effect=track):
            await sensor.async_added_to_hass()
        self.hass.set_state(CoreState.stopping)
        self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await self.hass.async_block_till_done()
        self.assertTrue(sensor._stopping)
        unsub.assert_called_once()
        for stage in [CoreState.final_write, CoreState.not_running]:
            self.hass.set_state(stage)
            with patch.object(module, "get_instance", return_value=self.recorder):
                await sensor._async_update_state()
                await sensor.async_update()
                await captured[0](None)
        self.recorder.async_add_executor_job.assert_not_awaited()
        await sensor.async_will_remove_from_hass()
        unsub.assert_called_once()

    async def test_unload_latches_and_cleans_listener_without_affecting_reload(self):
        sensor = self.sensor()
        removals = []
        sensor.async_on_remove = removals.append
        sensor._async_restore_previous_state = AsyncMock()
        sensor.async_schedule_update_ha_state = Mock()
        unsub = Mock()
        with patch.object(module, "async_track_state_change_event", return_value=unsub):
            await sensor.async_added_to_hass()
        for remove in removals:
            remove()
        self.assertTrue(sensor._stopping)
        unsub.assert_called_once()
        with patch.object(
            module, "async_track_state_change_event", return_value=Mock()
        ):
            await sensor.async_added_to_hass()
        self.assertFalse(sensor._stopping)

    async def test_shutdown_during_restore_prevents_startup_subscription(self):
        sensor = self.sensor()
        sensor.async_schedule_update_ha_state = Mock()

        async def restore_then_stop():
            self.hass.set_state(CoreState.stopping)
            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
            await self.hass.async_block_till_done()
            self.hass.set_state(CoreState.not_running)

        sensor._async_restore_previous_state = restore_then_stop
        with patch.object(module, "async_track_state_change_event") as track:
            await sensor.async_added_to_hass()
            from homeassistant.const import EVENT_HOMEASSISTANT_START

            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
            await self.hass.async_block_till_done()
            track.assert_not_called()
        self.assertTrue(sensor._stopping)
        sensor.async_schedule_update_ha_state.assert_not_called()
        await sensor.async_will_remove_from_hass()

    async def test_strict_source_loss_recovers_without_identity_change(self):
        sensor = self.sensor()
        with patch.object(module, "get_instance", return_value=self.recorder):
            await sensor._async_update_state()
            self.hass.states.async_set("sensor.source_b", "unavailable")
            self.assertFalse(sensor.available)
            self.hass.states.async_set("sensor.source_b", "40")
            await sensor._async_update_state()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 35)
        self.assertEqual(sensor.unique_id, "unchanged_id")


if __name__ == "__main__":
    unittest.main(verbosity=2)
