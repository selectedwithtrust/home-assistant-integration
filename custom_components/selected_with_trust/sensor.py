"""Sensors: next change and latest post."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SwtConfigEntry, SwtCoordinator
from .entity import SwtEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities([SwtNextChangeSensor(coordinator), SwtLatestPostSensor(coordinator)])


class SwtNextChangeSensor(SwtEntity, SensorEntity):
    """When the business next opens or closes."""

    _attr_translation_key = "next_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "next_change")

    @property
    def native_value(self) -> datetime | None:
        """Return the next open/close moment."""
        status = self.coordinator.status
        return None if status is None else status.next_change


class SwtLatestPostSensor(SwtEntity, SensorEntity):
    """Title of the latest announcement (special closures are announced here)."""

    _attr_translation_key = "latest_post"

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "latest_post")

    @property
    def _post(self) -> dict[str, Any] | None:
        post = (self.coordinator.data or {}).get("latestPost")
        return post if isinstance(post, dict) else None

    @property
    def native_value(self) -> str | None:
        """Return the post title (HA states are capped at 255 chars)."""
        return (self._post or {}).get("title", "")[:255] or None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the body and publication time."""
        if (post := self._post) is None:
            return None
        return {"body": post.get("body"), "published": post.get("createdAt")}
