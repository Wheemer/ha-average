"""Exercise the actual availability property without a Home Assistant runtime."""
import ast
from datetime import datetime, timezone
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

source = Path(__file__).with_name('sensor.py')
if not source.exists():
    source = Path(__file__).parents[1] / 'custom_components/average/sensor.py'
tree = ast.parse(source.read_text())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AverageSensor')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'available')
method.decorator_list = []
ns = {'math': math, 'dt_util': SimpleNamespace(utcnow=lambda: datetime.now(timezone.utc))}
exec(compile(ast.Module(body=[method], type_ignores=[]), 'sensor.py', 'exec'), ns)


class RequireAllTests(unittest.TestCase):
    def test_loss_nonfinite_stale_recovery_and_default(self):
        states = {'top': SimpleNamespace(state='40'), 'bottom': SimpleNamespace(state='30')}
        s = SimpleNamespace(
            _require_all_sources=True, sources=['top', 'bottom'],
            count_sources=2, available_sources=2, _attr_native_value=35,
            _temperature_mode=False, _is_source_stale=lambda state, now: False,
            _has_state=lambda value: value is not None,
            hass=SimpleNamespace(states=SimpleNamespace(get=states.get)))
        self.assertTrue(ns['available'](s))
        for bad in ['unknown', 'unavailable', 'nan', 'inf', None]:
            states['bottom'].state = bad
            self.assertFalse(ns['available'](s))
        states['bottom'].state = '30'
        self.assertTrue(ns['available'](s))
        s._is_source_stale = lambda state, now: True
        self.assertFalse(ns['available'](s))
        s._require_all_sources = False
        s.available_sources = 1
        self.assertTrue(ns['available'](s))


if __name__ == '__main__':
    unittest.main()
