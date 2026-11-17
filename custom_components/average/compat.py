"""Use the form/schema backend provided by the supported Core version."""

from importlib import import_module
from typing import get_type_hints

from homeassistant.data_entry_flow import section

schema_lib = import_module(
    get_type_hints(section.__init__)["schema"].__module__.split(".", 1)[0]
)
