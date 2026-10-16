"""Binary sensor: is the business open right now."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.util import dt as dt_util

from .const import CONF_CLOSING_SOON_MINUTES, DEFAULT_CLOSING_SOON_MINUTES
from .coordinator import SwtConfigEntry, SwtCoordinator
from .entity import SwtEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor."""
    async_add_entities(
        [SwtOpenNowSensor(entry.runtime_data), SwtClosingSoonSensor(entry.runtime_data)]
    )


class SwtOpenNowSensor(SwtEntity, BinarySensorEntity):
    """On while the business is open."""

    _attr_translation_key = "open_now"

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "open_now")

    @property
    def is_on(self) -> bool | None:
        """Return whether the business is open."""
        status = self.coordinator.status
        return None if status is None else status.is_open


class SwtClosingSoonSensor(SwtEntity, BinarySensorEntity):
    """On while the business is open but closes within the configured lead time."""

    _attr_translation_key = "closing_soon"

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "closing_soon")

    @property
    def is_on(self) -> bool | None:
        """Return whether closing time is near."""
        status = self.coordinator.status
        if status is None:
            return None
        if not status.is_open or status.next_change is None:
            return False
        minutes = self.coordinator.config_entry.options.get(
            CONF_CLOSING_SOON_MINUTES, DEFAULT_CLOSING_SOON_MINUTES
        )
        return bool(status.next_change - dt_util.utcnow() <= timedelta(minutes=minutes))
