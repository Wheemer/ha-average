"""Validation for explicit per-source attribute selection."""

from collections.abc import Mapping
from typing import Any


def normalize_source_attributes(value: Any, sources: list[str]) -> dict[str, str]:
    """Accept nonempty attribute names only for explicitly configured sources."""
    error = (
        "Source attributes must map configured entity IDs to nonempty attribute names"
    )
    if not isinstance(value, Mapping) or set(value).difference(sources):
        raise ValueError(error)
    result = {}
    for entity_id, attribute in value.items():
        if not isinstance(attribute, str):
            raise TypeError(error)
        if not attribute.strip():
            raise ValueError(error)
        result[entity_id] = attribute.strip()
    return result
