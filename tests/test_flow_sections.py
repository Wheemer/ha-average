"""Test section normalization against Home Assistant's actual schema helper."""

import asyncio
import importlib
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaFlowError,
)

source = Path(__file__).with_name("config_flow.py")
if not source.exists():
    source = Path(__file__).parents[1] / "custom_components/average/config_flow.py"
package = ModuleType("average_flow_test")
package.__path__ = [str(source.parent)]
sys.modules[package.__name__] = package
module = importlib.import_module("average_flow_test.config_flow")
namespace = vars(module)


class FlowSectionTests(unittest.TestCase):
    def test_actual_flow_flat_storage(self):
        old = {
            "name": "Average",
            "entities": ["sensor.a"],
            "scan_interval": {"seconds": 15},
            "max_source_age": {"minutes": 2},
        }
        parent = SimpleNamespace(
            show_advanced_options=True, async_create_entry=lambda **kw: kw
        )
        handler = SchemaCommonFlowHandler(parent, module.OPTIONS_FLOW, dict(old))
        result = asyncio.run(
            handler.async_step(
                "init",
                {
                    "entities": ["sensor.a"],
                    "require_all_sources": True,
                    "advanced": {
                        "scan_interval": {"seconds": 30},
                        "max_source_age": {"minutes": 2},
                    },
                },
            )
        )
        self.assertEqual(result["data"]["scan_interval"], {"seconds": 30})
        self.assertEqual(result["data"]["max_source_age"], {"minutes": 2})
        self.assertNotIn("advanced", result["data"])
        self.assertEqual(result["data"]["name"], "Average")

    def test_roundtrip_and_clear(self):
        old = {
            "name": "Water average",
            "entities": ["sensor.a", "sensor.b"],
            "duration": {"seconds": 15},
            "scan_interval": {"seconds": 15},
            "max_source_age": {"minutes": 2},
            "precision": 2,
            "require_all_sources": True,
        }
        handler = SimpleNamespace(options=dict(old))
        form = asyncio.run(namespace["suggested_options"](handler))
        self.assertEqual(form["advanced"]["scan_interval"], {"seconds": 15})
        self.assertEqual(handler.options, old)
        normalized = asyncio.run(namespace["validate_options"](handler, form))
        self.assertEqual(normalized, old)
        self.assertNotIn("advanced", normalized)
        self.assertNotIn("max_source_age", form)
        form["require_all_sources"] = False
        normalized = asyncio.run(namespace["validate_options"](handler, form))
        self.assertEqual(normalized["max_source_age"], {"minutes": 2})
        self.assertFalse(normalized["require_all_sources"])

    def test_collapsed_omission_preserves_options(self):
        handler = SimpleNamespace(options={"scan_interval": {"seconds": 15}})
        normalized = asyncio.run(
            namespace["validate_options"](handler, {"entities": ["sensor.a"]})
        )
        self.assertEqual(normalized["scan_interval"], {"seconds": 15})

    def test_invalid_period_does_not_mutate_saved_values(self):
        old = {"start": "saved", "scan_interval": {"seconds": 15}}
        handler = SimpleNamespace(options=dict(old))
        with self.assertRaises(SchemaFlowError):
            asyncio.run(
                namespace["validate_options"](
                    handler, {"advanced": {"start": "invalid"}}
                )
            )
        self.assertEqual(handler.options, old)

    def test_native_sections_selectors_and_integration_listing(self):
        probatio = module.schema_lib
        from homeassistant.helpers import selector

        self.assertIsInstance(module.OPTIONS_SCHEMA, probatio.Schema)
        self.assertNotIn("precision", module.OPTIONS_SCHEMA.schema)
        self.assertNotIn("duration", module.OPTIONS_SCHEMA.schema)
        self.assertIsInstance(
            module.OPTIONS_SCHEMA.schema["require_all_sources"],
            selector.BooleanSelector,
        )
        for field in ("source_availability", "max_source_age", "process_undef_as"):
            self.assertNotIn(field, module.OPTIONS_SCHEMA.schema)
        for name in module.SECTIONS:
            self.assertTrue(module.OPTIONS_SCHEMA.schema[name].options["collapsed"])
        advanced = module.OPTIONS_SCHEMA.schema["advanced"].schema.schema
        self.assertIsInstance(advanced["duration"], selector.DurationSelector)
        self.assertIsInstance(advanced["start"], selector.TemplateSelector)
        self.assertIsInstance(advanced["end"], selector.TemplateSelector)
        self.assertIsInstance(advanced["max_source_age"], selector.DurationSelector)
        self.assertIsInstance(advanced["process_undef_as"], selector.NumberSelector)
        self.assertIsInstance(advanced["ignore_undef"], selector.BooleanSelector)
        self.assertIsInstance(
            advanced["calculate_to_now_undef"], selector.BooleanSelector
        )
        self.assertNotEqual(
            json.loads((source.parent / "manifest.json").read_text()).get(
                "integration_type"
            ),
            "helper",
        )

    def test_invalid_template_is_rejected_by_native_selector(self):
        probatio = module.schema_lib

        with self.assertRaises(probatio.Invalid):
            module.ADVANCED_SCHEMA({"start": "{{"})

    def test_water_settings_survive_actual_flow_submission(self):
        original = {
            "name": "Water Average Temperature",
            "entities": [
                "sensor.waterheater_temperature",
                "sensor.water_temp_bottom_temperature",
            ],
            "duration": {"seconds": 15},
            "scan_interval": {"seconds": 15},
            "precision": 2,
            "require_all_sources": True,
        }
        parent = SimpleNamespace(
            show_advanced_options=True, async_create_entry=lambda **kw: kw
        )
        handler = SchemaCommonFlowHandler(parent, module.OPTIONS_FLOW, dict(original))
        form = asyncio.run(module.suggested_options(handler))
        form.pop("name")
        validated = module.OPTIONS_SCHEMA(form)
        saved = asyncio.run(handler.async_step("init", validated))["data"]
        self.assertEqual(saved, original)
        self.assertTrue(saved["require_all_sources"])

    def test_sections_omitted_independently_retain_saved_values(self):
        old = {
            "require_all_sources": True,
            "max_source_age": {"minutes": 2},
            "precision": 3,
            "scan_interval": {"seconds": 15},
        }
        for selected in (
            {"advanced": {"precision": 4, "max_source_age": {"minutes": 2}}},
            {"require_all_sources": False},
        ):
            handler = SimpleNamespace(options=dict(old))
            normalized = asyncio.run(
                module.validate_options(handler, {"entities": ["sensor.a"], **selected})
            )
            if "advanced" in selected:
                self.assertTrue(normalized["require_all_sources"])
                self.assertEqual(normalized["max_source_age"], {"minutes": 2})
            else:
                self.assertEqual(normalized["precision"], 3)
                self.assertEqual(normalized["scan_interval"], {"seconds": 15})

    def test_all_form_fields_have_matching_section_translations(self):
        data = json.loads((source.parent / "translations/en.json").read_text())
        for group, step in (("config", "user"), ("options", "init")):
            flow = data[group]["step"][step]
            schema = (
                module.CONFIG_SCHEMA if group == "config" else module.OPTIONS_SCHEMA
            )
            for marker in schema.schema:
                key = marker.schema
                if key in module.SECTIONS:
                    fields = schema.schema[marker].schema.schema
                    self.assertTrue(flow["sections"][key]["name"])
                    self.assertEqual(
                        {field.schema for field in fields},
                        set(flow["sections"][key]["data"]),
                    )
                else:
                    self.assertIn(key, flow["data"])

    def test_empty_sources_and_zero_durations_fail_without_mutating_options(self):
        for submitted in (
            {"entities": []},
            {"entities": ["sensor.a"], "duration": {"seconds": 0}},
            {"entities": ["sensor.a"], "advanced": {"scan_interval": {"seconds": 0}}},
        ):
            original = {"require_all_sources": True}
            handler = SimpleNamespace(options=dict(original))
            with self.assertRaises(SchemaFlowError):
                asyncio.run(module.validate_options(handler, submitted))
            self.assertEqual(handler.options, original)

    def test_all_yaml_calculation_options_roundtrip_and_clear_in_ui(self):
        original = {
            "name": "Legacy average",
            "entities": ["sensor.a"],
            "unique_id": "stable",
            "duration": {"minutes": 5},
            "scan_interval": {"seconds": 30},
            "precision": 3,
            "require_all_sources": True,
            "max_source_age": {"minutes": 2},
            "process_undef_as": 0,
            "ignore_undef": True,
            "calculate_to_now_undef": True,
            "weights": {"sensor.a": 2},
        }
        parent = SimpleNamespace(
            show_advanced_options=True, async_create_entry=lambda **kw: kw
        )
        handler = SchemaCommonFlowHandler(parent, module.OPTIONS_FLOW, dict(original))
        form = asyncio.run(module.suggested_options(handler))
        form.pop("name")
        form.pop("unique_id")
        result = asyncio.run(handler.async_step("init", module.OPTIONS_SCHEMA(form)))[
            "data"
        ]
        self.assertEqual(result, original)
        # Clearing optional controls in the expanded section removes old values.
        form["advanced"] = {"scan_interval": {"seconds": 30}, "precision": 3}
        result = asyncio.run(handler.async_step("init", module.OPTIONS_SCHEMA(form)))[
            "data"
        ]
        for key in (
            "duration",
            "max_source_age",
            "process_undef_as",
            "ignore_undef",
            "calculate_to_now_undef",
            "weights",
        ):
            self.assertNotIn(key, result)
        self.assertEqual(result["unique_id"], "stable")
        self.assertTrue(result["require_all_sources"])


if __name__ == "__main__":
    unittest.main()
