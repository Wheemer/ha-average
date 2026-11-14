"""Validation of optional source weights shared by YAML and UI configuration."""

import math
from collections.abc import Mapping
from typing import Any


def normalize_weights(value: Any, sources: list[str]) -> dict[str, float]:
    """Validate explicit source weights without changing default equal weighting."""
    error = (
        "Weights must map configured source entity IDs to finite nonnegative numbers"
    )
    if not isinstance(value, Mapping) or set(value).difference(sources):
        raise ValueError(error)
    result = {}
    for entity_id, weight in value.items():
        if isinstance(weight, bool):
            raise TypeError(error)
        try:
            number = float(weight)
        except (TypeError, ValueError, OverflowError) as err:
            raise ValueError(error) from err
        if not math.isfinite(number) or number < 0:
            raise ValueError(error)
        result[entity_id] = number
    if not any(result.get(entity_id, 1) > 0 for entity_id in sources):
        error = "At least one configured source must have a positive weight"
        raise ValueError(error)
    return result
