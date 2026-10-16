"""Shared fixtures."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.selected_with_trust.const import (
    BASE_URL,
    CONF_BUSINESS_ID,
    CONF_BUSINESS_NAME,
    DOMAIN,
)

BID = "550e8400-e29b-41d4-a716-446655440000"
INFO_URL = f"{BASE_URL}/api/v1/businesses/{BID}/opening-info"
LIST_URL = f"{BASE_URL}/api/v1/businesses"

INFO = {
    "version": 1,
    "id": BID,
    "name": "Example Kitchens",
    "timezone": "Europe/Amsterdam",
    "logoUrl": f"{BASE_URL}/uploads/logo.webp",
    "rating": 4.6,
    "reviewCount": 38,
    "openingHours": [
        {"dayOfWeek": d, "isClosed": False, "openTime": "09:00", "closeTime": "17:00",
         "breakStart": None, "breakEnd": None}
        for d in range(1, 8)
    ],
    "holidayHours": [],
    "latestPost": {"title": "Sale", "body": "Big sale", "createdAt": "2026-10-10T08:00:00.000Z"},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in tests."""


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Example Kitchens",
        unique_id=BID,
        data={CONF_BUSINESS_ID: BID, CONF_BUSINESS_NAME: "Example Kitchens"},
    )
