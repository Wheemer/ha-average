"""Full native Core/recorder shutdown, isolated from the live installation."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import loader
from homeassistant.components.recorder import get_instance
from homeassistant.config_entries import ConfigEntries
from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.setup import async_setup_component

import custom_components.average.sensor as module


class RecorderShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_recorder_close_and_late_source_event(self):
        with tempfile.TemporaryDirectory() as folder:
            hass = HomeAssistant(folder)
            loader.async_setup(hass)
            async_initialize_recorder(hass)
            hass.config_entries = ConfigEntries(hass, {})
            await hass.config_entries.async_initialize()
            self.assertTrue(
                await async_setup_component(
                    hass,
                    "recorder",
                    {
                        "recorder": {
                            "db_url": "sqlite:///" + str(Path(folder) / "test.db")
                        }
                    },
                )
            )
            await hass.async_start()
            recorder = get_instance(hass)
            await recorder.async_block_till_done()
            hass.states.async_set("sensor.source_a", "30")
            hass.states.async_set("sensor.source_b", "40")
            sensor = module.AverageSensor(
                hass,
                {
                    "entities": ["sensor.source_a", "sensor.source_b"],
                    "duration": timedelta(minutes=5),
                    "require_all_sources": True,
                },
            )
            sensor._async_restore_previous_state = AsyncMock()
            sensor.async_schedule_update_ha_state = Mock()
            sensor.async_write_ha_state = Mock()
            captured = []
            listener_calls = []
            real_track = module.async_track_state_change_event

            def track(hass, sources, listener):
                captured.append(listener)

                async def counted(event):
                    listener_calls.append(event)
                    await listener(event)

                return real_track(hass, sources, counted)

            with patch.object(
                module, "async_track_state_change_event", side_effect=track
            ):
                await sensor.async_added_to_hass()
            # Establish that normal updates use the real recorder executor.
            await sensor._async_update_state()
            self.assertEqual(sensor.native_value, 35)
            late_events = []
            listener_calls.clear()

            @callback
            def late_source(event):
                late_events.append(hass.state)
                hass.states.async_set("sensor.source_a", "unavailable")

            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, late_source)
            await hass.async_stop()
            self.assertEqual(late_events, [CoreState.not_running])
            self.assertTrue(sensor._stopping)
            self.assertEqual(listener_calls, [])
            # Prove the actual recorder executor has closed, rather than assuming it.
            with self.assertRaisesRegex(
                RuntimeError, "cannot schedule new futures after shutdown"
            ):
                await recorder.async_add_executor_job(lambda: None)
            # A callback queued before unsubscription must also be harmless after CLOSE.
            with patch.object(
                module, "get_instance", wraps=module.get_instance
            ) as access:
                await captured[0](None)
                await sensor._async_update_state()
                await sensor.async_update()
                access.assert_not_called()
            self.assertEqual(sensor.native_value, 35)
            await sensor.async_will_remove_from_hass()


if __name__ == "__main__":
    unittest.main(verbosity=2)
