"""Diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import SwtConfigEntry

TO_REDACT: set[str] = set()  # the API is public; nothing personal is stored


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SwtConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    status = coordinator.status
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": coordinator.data,
        "evaluated": None
        if status is None
        else {
            "is_open": status.is_open,
            "next_change": status.next_change.isoformat() if status.next_change else None,
        },
        "last_update_success": coordinator.last_update_success,
    }
