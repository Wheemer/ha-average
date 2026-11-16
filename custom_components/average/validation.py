"""Numeric validation shared by YAML, UI and stored configuration."""

import math
from typing import Any


def finite_number(value: Any) -> int | float:
    """Require a finite numeric value, excluding boolean substitutes."""
    message = "Use a finite number, not a boolean or infinity/NaN"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(message)
    try:
        finite = math.isfinite(value)
    except OverflowError as err:
        raise ValueError(message) from err
    if not finite:
        raise ValueError(message)
    return value
