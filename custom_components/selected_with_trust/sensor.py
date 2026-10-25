"""Sensors: next change and latest post."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SwtConfigEntry, SwtCoordinator
from .entity import SwtEntity
from .schedule import describe_day

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SwtNextChangeSensor(coordinator),
            SwtOpeningHoursSensor(coordinator),
            SwtLatestPostSensor(coordinator),
            SwtLatestPostTextSensor(coordinator),
            SwtRatingSensor(coordinator),
            SwtReviewCountSensor(coordinator),
        ]
    )


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


class SwtLatestPostTextSensor(SwtLatestPostSensor):
    """Body of the latest announcement (shortened to the 255-char state limit)."""

    _attr_translation_key = "latest_post_text"

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        SwtEntity.__init__(self, coordinator, "latest_post_text")

    @property
    def native_value(self) -> str | None:
        """Return the post text."""
        body = (self._post or {}).get("body") or ""
        return body[:255] or None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Keep the full text available."""
        if (post := self._post) is None:
            return None
        return {"full_text": post.get("body")}


_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class SwtOpeningHoursSensor(SwtEntity, SensorEntity):
    """Today's opening hours; the whole week and holidays as attributes."""

    _attr_translation_key = "opening_hours"

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "opening_hours")

    def _today(self) -> Any:
        return dt_util.utcnow().astimezone(self.coordinator.zone).date()

    @property
    def native_value(self) -> str | None:
        """Return today's hours."""
        if not self.coordinator.data:
            return None
        return describe_day(self.coordinator.data, self.coordinator.zone, self._today())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the week (next 7 days, starting today) and upcoming holidays."""
        data = self.coordinator.data
        if not data:
            return None
        today = self._today()
        week = {}
        for offset in range(7):
            day = today + timedelta(days=offset)
            week[_DAYS[day.weekday()]] = describe_day(data, self.coordinator.zone, day)
        holidays = [
            {
                "date": h["date"],
                "name": next(iter((h.get("names") or {}).values()), None),
                "hours": describe_day(
                    data, self.coordinator.zone, datetime.fromisoformat(h["date"]).date()
                ),
            }
            for h in data.get("holidayHours", [])
            if h.get("date")
        ]
        return {"timezone": data.get("timezone"), "week": week, "holidays": holidays}


class SwtRatingSensor(SwtEntity, SensorEntity):
    """Average review rating (0-5)."""

    _attr_translation_key = "rating"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "rating")

    @property
    def native_value(self) -> float | None:
        """Return the rating, or None when there are no reviews."""
        value = (self.coordinator.data or {}).get("rating")
        return float(value) if value is not None else None


class SwtReviewCountSensor(SwtEntity, SensorEntity):
    """Number of reviews."""

    _attr_translation_key = "review_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SwtCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "review_count")

    @property
    def native_value(self) -> int | None:
        """Return the review count."""
        value = (self.coordinator.data or {}).get("reviewCount")
        return int(value) if value is not None else None
