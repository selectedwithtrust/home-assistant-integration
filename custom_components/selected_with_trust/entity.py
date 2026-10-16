"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BASE_URL, DOMAIN
from .coordinator import SwtCoordinator


class SwtEntity(CoordinatorEntity[SwtCoordinator]):
    """Base class: one device per business."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SwtCoordinator, key: str) -> None:
        """Initialise with a stable unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.business_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.business_id)},
            name=coordinator.config_entry.title,
            manufacturer="Selected With Trust",
            configuration_url=f"{BASE_URL}/business/{coordinator.business_id}",
        )
