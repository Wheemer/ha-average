"""Protect YAML imports from ambiguous explicit sensor identities."""

from __future__ import annotations

import logging
from hashlib import sha1
from typing import TYPE_CHECKING

from homeassistant.config import config_per_platform
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import callback
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

DATA_YAML_IDS = f"{DOMAIN}_yaml_ids"
LEGACY_UNIQUE_ID = "__legacy__"
_LOGGER = logging.getLogger(__name__)


@callback
def prepare_yaml_import(hass: HomeAssistant, config: ConfigType) -> None:
    """Inspect all blocks before any import can change a saved entry."""
    identities: dict[str, list[str]] = {}
    for platform, options in config_per_platform(config, "sensor"):
        if platform != DOMAIN:
            continue
        unique_id = options.get(CONF_UNIQUE_ID)
        if unique_id:
            identities.setdefault(unique_id, []).append(
                options.get(CONF_NAME, "Average")
            )
    for unique_id in hass.data.get(DATA_YAML_IDS, {}):
        if len(identities.get(unique_id, [])) <= 1:
            async_delete_issue(hass, DOMAIN, _duplicate_issue_id(unique_id))
    hass.data[DATA_YAML_IDS] = identities


def _duplicate_issue_id(unique_id: str) -> str:
    """Keep user-provided IDs out of repair identifiers."""
    return (
        "duplicate_yaml_id_"
        + sha1(unique_id.encode(), usedforsecurity=False).hexdigest()
    )


@callback
def report_duplicate_id(hass: HomeAssistant, unique_id: str) -> None:
    """Explain a refused import without exposing or replacing saved options."""
    _LOGGER.error(
        "Average Sensor YAML unique_id %s is used by conflicting sensor "
        "definitions; no existing entry was overwritten. Give each sensor "
        "a distinct unique_id",
        unique_id,
    )
    async_create_issue(
        hass,
        DOMAIN,
        _duplicate_issue_id(unique_id),
        is_fixable=False,
        is_persistent=False,
        severity=IssueSeverity.ERROR,
        translation_key="duplicate_yaml_id",
        translation_placeholders={"unique_id": unique_id},
    )
