"""Config flow tests."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.selected_with_trust.const import DOMAIN

from .conftest import BID, INFO, INFO_URL, LIST_URL

OTHER = "11111111-2222-3333-4444-555555555555"
RESULTS = {"businesses": [
    {"publicId": BID, "name": "Example Kitchens", "city": "Utrecht"},
    {"publicId": OTHER, "name": "Other Bakery", "city": ""},
    {"name": "no id"},
]}


async def test_search_and_pick(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(LIST_URL, json=RESULTS)
    aioclient_mock.get(INFO_URL, json=INFO)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": "kitchens"})
    assert r["step_id"] == "pick"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"business": BID})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Example Kitchens"
    assert r["data"]["business_id"] == BID
    assert r["result"].unique_id == BID


async def test_pasted_url(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(INFO_URL, json=INFO)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"query": f"https://selectedwithtrust.com/business/{BID.upper()}"}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("status", "error"), [(404, "not_found"), (429, "rate_limited"), (500, "cannot_connect")]
)
async def test_errors_then_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int, error: str
) -> None:
    aioclient_mock.get(INFO_URL, status=status)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": BID})
    assert r["errors"] == {"base": error}
    aioclient_mock.clear_requests()
    aioclient_mock.get(INFO_URL, json=INFO)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": BID})
    assert r["type"] is FlowResultType.CREATE_ENTRY


async def test_no_results(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(LIST_URL, json={"businesses": []})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": "zzz"})
    assert r["errors"] == {"base": "no_results"}


async def test_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(INFO_URL, json=INFO)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": BID})
    assert r["type"] is FlowResultType.ABORT
    assert r["reason"] == "already_configured"


async def test_reconfigure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    other_url = INFO_URL.replace(BID, OTHER)
    aioclient_mock.get(other_url, json={**INFO, "id": OTHER, "name": "Other Bakery"})
    aioclient_mock.get(INFO_URL, json=INFO)
    r = await entry.start_reconfigure_flow(hass)
    assert r["step_id"] == "reconfigure"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": OTHER})
    assert r["type"] is FlowResultType.ABORT
    assert r["reason"] == "reconfigure_successful"
    assert entry.unique_id == OTHER
    assert entry.title == "Other Bakery"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
