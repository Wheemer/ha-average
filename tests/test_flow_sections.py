"""Test section normalization against Home Assistant's actual schema helper."""
import asyncio
import importlib
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace
import unittest

from homeassistant.helpers.schema_config_entry_flow import (
    SchemaFlowError,
    SchemaCommonFlowHandler,
)


source = Path(__file__).with_name('config_flow.py')
if not source.exists():
    source = Path(__file__).parents[1] / 'custom_components/average/config_flow.py'
package = ModuleType('average_flow_test')
package.__path__ = [str(source.parent)]
sys.modules[package.__name__] = package
module = importlib.import_module('average_flow_test.config_flow')
namespace = vars(module)


class FlowSectionTests(unittest.TestCase):
    def test_actual_flow_flat_storage(self):
        old = {'name': 'Average', 'entities': ['sensor.a'],
               'scan_interval': {'seconds': 15}, 'max_source_age': {'minutes': 2}}
        parent = SimpleNamespace(async_create_entry=lambda **kw: kw)
        handler = SchemaCommonFlowHandler(parent, module.OPTIONS_FLOW, dict(old))
        result = asyncio.run(handler.async_step('init', {
            'entities': ['sensor.a'], 'require_all_sources': True,
            'advanced': {'scan_interval': {'seconds': 30}},
        }))
        self.assertEqual(result['data']['scan_interval'], {'seconds': 30})
        self.assertNotIn('max_source_age', result['data'])
        self.assertNotIn('advanced', result['data'])
        self.assertEqual(result['data']['name'], 'Average')

    def test_roundtrip_and_clear(self):
        old = {'name': 'Water average', 'entities': ['sensor.a', 'sensor.b'],
               'duration': {'seconds': 15}, 'scan_interval': {'seconds': 15},
               'max_source_age': {'minutes': 2}, 'precision': 2, 'require_all_sources': True}
        handler = SimpleNamespace(options=dict(old))
        form = asyncio.run(namespace['suggested_options'](handler))
        self.assertEqual(form['advanced']['scan_interval'], {'seconds': 15})
        self.assertEqual(handler.options, old)
        normalized = asyncio.run(namespace['validate_options'](handler, form))
        self.assertEqual(normalized, old)
        self.assertNotIn('advanced', normalized)
        form['advanced'].pop('max_source_age')
        normalized = asyncio.run(namespace['validate_options'](handler, form))
        self.assertNotIn('max_source_age', normalized)
        self.assertNotIn('max_source_age', handler.options)

    def test_collapsed_omission_preserves_options(self):
        handler = SimpleNamespace(options={'scan_interval': {'seconds': 15}})
        normalized = asyncio.run(namespace['validate_options'](handler, {'entities': ['sensor.a']}))
        self.assertEqual(normalized['scan_interval'], {'seconds': 15})

    def test_invalid_period_does_not_mutate_saved_values(self):
        old = {'start': 'saved', 'scan_interval': {'seconds': 15}}
        handler = SimpleNamespace(options=dict(old))
        with self.assertRaises(SchemaFlowError):
            asyncio.run(namespace['validate_options'](handler, {'advanced': {'start': 'invalid'}}))
        self.assertEqual(handler.options, old)


if __name__ == '__main__':
    unittest.main()
