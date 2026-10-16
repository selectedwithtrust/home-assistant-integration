"""Image entity for the business logo."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SwtConfigEntry, SwtCoordinator
from .entity import SwtEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the logo, only if the business has one."""
    coordinator = entry.runtime_data
    if (coordinator.data or {}).get("logoUrl"):
        async_add_entities([SwtLogoImage(hass, coordinator)])


class SwtLogoImage(SwtEntity, ImageEntity):
    """The business logo."""

    _attr_translation_key = "logo"

    def __init__(self, hass: HomeAssistant, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        SwtEntity.__init__(self, coordinator, "logo")
        ImageEntity.__init__(self, hass)
        self._attr_image_url = coordinator.data.get("logoUrl")
        self._attr_image_last_updated: datetime | None = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the cached image only when the URL changed."""
        url = self.coordinator.data.get("logoUrl")
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._attr_image_last_updated = dt_util.utcnow()
            self._cached_image = None
        super()._handle_coordinator_update()
