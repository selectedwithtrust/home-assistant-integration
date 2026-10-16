"""Constants for the Selected With Trust integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "selected_with_trust"
BASE_URL: Final = "https://selectedwithtrust.com"

CONF_BUSINESS_ID: Final = "business_id"
CONF_BUSINESS_NAME: Final = "business_name"

# Opening hours rarely change and the API rate limit is 30 requests/hour/IP.
# The server also sends ETags, so unchanged polls are cheap 304s.
UPDATE_INTERVAL: Final = timedelta(hours=6)

# How many days ahead the schedule is expanded when looking for the next change.
SCHEDULE_HORIZON_DAYS: Final = 14

ISSUE_BUSINESS_GONE: Final = "business_gone"

CONF_CLOSING_SOON_MINUTES: Final = "closing_soon_minutes"
DEFAULT_CLOSING_SOON_MINUTES: Final = 30
