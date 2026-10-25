"""Setup, entities, errors, repairs, diagnostics."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.selected_with_trust.const import DOMAIN, UPDATE_INTERVAL

from .conftest import BID, INFO, INFO_URL


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_entities(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-10-12 08:00:00+00:00")  # Monday 10:00 Amsterdam
    aioclient_mock.get(INFO_URL, json=INFO, headers={"ETag": 'W/"a"'})
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("binary_sensor.example_kitchens_open_now").state == "on"
    assert hass.states.get("sensor.example_kitchens_latest_announcement").state == "Sale"
    assert hass.states.get("sensor.example_kitchens_next_opening_or_closing").state.startswith("2026-10-12T15:00")
    assert hass.states.get("image.example_kitchens_logo") is not None


async def test_flips_at_boundary_without_polling(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-10-12 14:59:00+00:00")  # 16:59 local, closes 17:00
    aioclient_mock.get(INFO_URL, json=INFO)
    await _setup(hass, entry)
    assert hass.states.get("binary_sensor.example_kitchens_open_now").state == "on"
    calls = aioclient_mock.call_count

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.example_kitchens_open_now").state == "off"
    assert aioclient_mock.call_count == calls  # no extra HTTP


async def test_no_logo_no_post(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    info = deepcopy(INFO)
    info["logoUrl"] = None
    info["latestPost"] = None
    aioclient_mock.get(INFO_URL, json=info)
    await _setup(hass, entry)
    assert hass.states.get("image.example_kitchens_logo") is None
    assert hass.states.get("sensor.example_kitchens_latest_announcement").state == "unknown"


async def test_not_found_retries_and_raises_issue(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INFO_URL, status=404)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"business_gone_{BID}")


async def test_rate_limit_and_connection_errors(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INFO_URL, status=429)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_server_error_retries(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INFO_URL, status=500)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_then_recovers_and_issue_clears(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    aioclient_mock.get(INFO_URL, json=INFO)
    await _setup(hass, entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(INFO_URL, status=404)
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.example_kitchens_open_now").state == "unavailable"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"business_gone_{BID}")

    aioclient_mock.clear_requests()
    aioclient_mock.get(INFO_URL, json=INFO)
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.example_kitchens_open_now").state != "unavailable"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"business_gone_{BID}") is None


async def test_etag_304_uses_cache(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    aioclient_mock.get(INFO_URL, json=INFO, headers={"ETag": 'W/"a"'})
    await _setup(hass, entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(INFO_URL, status=304)
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert aioclient_mock.mock_calls[-1][3]["If-None-Match"] == 'W/"a"'
    assert hass.states.get("binary_sensor.example_kitchens_open_now").state != "unavailable"


async def test_unsupported_version(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INFO_URL, json={**INFO, "version": 2})
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INFO_URL, json=INFO)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    hass_client,
) -> None:
    aioclient_mock.get(INFO_URL, json=INFO)
    await _setup(hass, entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diag["entry"]["business_id"] == BID
    assert diag["data"]["name"] == "Example Kitchens"
    assert diag["evaluated"]["is_open"] in (True, False)


async def test_hours_and_text_sensors(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-10-12 08:00:00+00:00")
    info = deepcopy(INFO)
    info["holidayHours"] = [{"date": "2026-10-14", "names": {"nl": "Feestdag"}, "overrideType": "closed"}]
    aioclient_mock.get(INFO_URL, json=info)
    await _setup(hass, entry)
    st = hass.states.get("sensor.example_kitchens_opening_hours_today")
    assert st.state == "09:00-17:00"
    assert st.attributes["week"]["monday"] == "09:00-17:00"
    assert st.attributes["holidays"][0] == {"date": "2026-10-14", "name": "Feestdag", "hours": "Closed"}
    text = hass.states.get("sensor.example_kitchens_latest_announcement_text")
    assert text.state == "Big sale"

    # Rolls over at local midnight without any polling.
    freezer.move_to("2026-10-13 22:30:00+00:00")  # Wed 00:30 local -> holiday, closed
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.example_kitchens_opening_hours_today").state == "Closed"


async def test_text_sensor_without_post(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    info = deepcopy(INFO)
    info["latestPost"] = None
    aioclient_mock.get(INFO_URL, json=info)
    await _setup(hass, entry)
    assert hass.states.get("sensor.example_kitchens_latest_announcement_text").state == "unknown"


async def test_rating_reviews_closing_soon_and_options(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-10-12 14:00:00+00:00")  # 16:00 local, closes 17:00
    aioclient_mock.get(INFO_URL, json=INFO)
    await _setup(hass, entry)
    assert hass.states.get("sensor.example_kitchens_rating").state == "4.6"
    assert hass.states.get("sensor.example_kitchens_reviews").state == "38"
    assert hass.states.get("binary_sensor.example_kitchens_closing_soon").state == "off"

    freezer.move_to("2026-10-12 14:31:00+00:00")  # 16:31 -> within 30 min
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.example_kitchens_closing_soon").state == "on"

    # Options flow changes the lead time and reloads.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"closing_soon_minutes": 5}
    )
    await hass.async_block_till_done()
    assert entry.options["closing_soon_minutes"] == 5
    assert hass.states.get("binary_sensor.example_kitchens_closing_soon").state == "off"

    freezer.move_to("2026-10-12 15:00:00+00:00")  # after close
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.example_kitchens_closing_soon").state == "off"


async def test_no_rating_when_no_reviews(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    info = deepcopy(INFO)
    info.pop("rating"), info.pop("reviewCount")
    aioclient_mock.get(INFO_URL, json=info)
    await _setup(hass, entry)
    assert hass.states.get("sensor.example_kitchens_rating").state == "unknown"
    assert hass.states.get("sensor.example_kitchens_reviews").state == "unknown"


@pytest.mark.parametrize(
    ("tz", "expected"),
    [
        ("America/New_York", "America/New_York"),
        ("Nope/Zone", "Europe/Amsterdam"),  # unknown -> platform default
        ("/etc/passwd", "Europe/Amsterdam"),  # malformed key -> ValueError path
        (None, "Europe/Amsterdam"),
    ],
)
async def test_zone_resolved_once_off_loop(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
    tz: str | None, expected: str,
) -> None:
    info = deepcopy(INFO)
    info["timezone"] = tz
    aioclient_mock.get(INFO_URL, json=info)
    await _setup(hass, entry)
    assert entry.runtime_data.zone.key == expected


async def test_zone_falls_back_to_ha_default_when_lookup_fails(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(INFO_URL, json=INFO)
    with patch(
        "custom_components.selected_with_trust.coordinator.dt_util.async_get_time_zone",
        return_value=None,
    ):
        await _setup(hass, entry)
    assert entry.runtime_data.zone is dt_util.get_default_time_zone()
