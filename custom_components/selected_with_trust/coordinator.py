"""Data update coordinator."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SwtClient, SwtConnectionError, SwtNotFoundError, SwtRateLimitError
from .const import (
    CONF_BUSINESS_ID,
    CONF_CLOSING_SOON_MINUTES,
    DEFAULT_CLOSING_SOON_MINUTES,
    DEFAULT_TIMEZONE,
    DOMAIN,
    ISSUE_BUSINESS_GONE,
    SCHEDULE_HORIZON_DAYS,
    UPDATE_INTERVAL,
)
from .schedule import Status, evaluate, next_local_midnight

_LOGGER = logging.getLogger(__name__)

type SwtConfigEntry = ConfigEntry[SwtCoordinator]


_UNRESOLVED = object()


class SwtCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch opening info and re-evaluate "open now" exactly at each boundary."""

    config_entry: SwtConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SwtConfigEntry, client: SwtClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_BUSINESS_ID]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.business_id: str = entry.data[CONF_BUSINESS_ID]
        self._unsub_boundary: CALLBACK_TYPE | None = None
        # Business timezone, resolved off the event loop after each fetch.
        self.zone: tzinfo = dt_util.get_default_time_zone()
        self._zone_name: str | None | object = _UNRESOLVED

    async def _async_resolve_zone(self, name: str | None) -> tzinfo:
        """Look up an IANA zone without blocking the loop (tzdata is read from disk)."""
        for candidate in (name, DEFAULT_TIMEZONE):
            if not candidate:
                continue
            try:
                zone = await dt_util.async_get_time_zone(candidate)
            except ValueError:  # malformed key, e.g. an absolute path
                continue
            if zone is not None:
                return zone
        return dt_util.get_default_time_zone()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.get_opening_info(self.business_id)
        except SwtNotFoundError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_BUSINESS_GONE}_{self.business_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_BUSINESS_GONE,
                translation_placeholders={
                    "name": self.config_entry.title,
                },
            )
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="business_gone"
            ) from err
        except SwtRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except SwtConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

        ir.async_delete_issue(
            self.hass, DOMAIN, f"{ISSUE_BUSINESS_GONE}_{self.business_id}"
        )
        if (name := data.get("timezone")) != self._zone_name:
            self.zone = await self._async_resolve_zone(name)
            self._zone_name = name
        return data

    @property
    def status(self) -> Status | None:
        """Current open/closed evaluation (computed, never stale)."""
        if not self.data:
            return None
        return evaluate(self.data, self.zone, dt_util.utcnow(), SCHEDULE_HORIZON_DAYS)

    @callback
    def schedule_boundary(self) -> None:
        """Wake listeners at the next open/close moment."""
        self.cancel_boundary()
        if (status := self.status) is None:
            return
        # Also wake at local midnight so "today's hours" rolls over.
        wake = next_local_midnight(self.zone, dt_util.utcnow())
        if status.next_change is not None:
            wake = min(wake, status.next_change)
            if status.is_open:
                lead = timedelta(
                    minutes=self.config_entry.options.get(
                        CONF_CLOSING_SOON_MINUTES, DEFAULT_CLOSING_SOON_MINUTES
                    )
                )
                soon = status.next_change - lead
                if soon > dt_util.utcnow():
                    wake = min(wake, soon)

        @callback
        def _fire(_now: datetime) -> None:
            self._unsub_boundary = None
            self.async_update_listeners()
            self.schedule_boundary()

        self._unsub_boundary = async_track_point_in_utc_time(
            self.hass, _fire, wake
        )

    @callback
    def cancel_boundary(self) -> None:
        """Cancel the pending boundary timer."""
        if self._unsub_boundary is not None:
            self._unsub_boundary()
            self._unsub_boundary = None

    @callback
    def _async_refresh_finished(self) -> None:
        """Re-arm the boundary timer after each (re)fetch."""
        super()._async_refresh_finished()
        self.schedule_boundary()
