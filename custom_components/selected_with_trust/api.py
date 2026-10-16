"""Async client for the Selected With Trust public API."""

from __future__ import annotations

import re
from typing import Any, TypedDict

import aiohttp

from .const import BASE_URL

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_TIMEOUT = aiohttp.ClientTimeout(total=20)


class SwtError(Exception):
    """Base error for the client."""


class SwtConnectionError(SwtError):
    """Network problem or unexpected server response."""


class SwtRateLimitError(SwtError):
    """The server answered 429."""


class SwtNotFoundError(SwtError):
    """The business does not exist (any more) or is no longer public."""


class BusinessSummary(TypedDict):
    """A search result."""

    id: str
    name: str
    city: str


def extract_business_id(text: str) -> str | None:
    """Return a public business UUID found in free text (e.g. a pasted URL)."""
    match = _UUID_RE.search(text)
    return match.group(0).lower() if match else None


class SwtClient:
    """Thin wrapper; the aiohttp session is injected by Home Assistant."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client."""
        self._session = session
        self._etags: dict[str, str] = {}
        self._cache: dict[str, dict[str, Any]] = {}

    async def _get(self, url: str, params: dict[str, str] | None = None) -> Any:
        headers: dict[str, str] = {"Accept": "application/json"}
        if (etag := self._etags.get(url)) and url in self._cache:
            headers["If-None-Match"] = etag
        try:
            async with self._session.get(
                url, params=params, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status == 304 and url in self._cache:
                    return self._cache[url]
                if resp.status == 404:
                    raise SwtNotFoundError(url)
                if resp.status == 429:
                    raise SwtRateLimitError(url)
                if resp.status != 200:
                    raise SwtConnectionError(f"HTTP {resp.status}")
                payload = await resp.json()
                if etag := resp.headers.get("ETag"):
                    self._etags[url] = etag
                    if isinstance(payload, dict):
                        self._cache[url] = payload
                return payload
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise SwtConnectionError(str(err)) from err

    async def get_opening_info(self, business_id: str) -> dict[str, Any]:
        """Fetch the versioned opening-info document."""
        data = await self._get(f"{BASE_URL}/api/v1/businesses/{business_id}/opening-info")
        if not isinstance(data, dict) or data.get("version") != 1:
            raise SwtConnectionError("Unsupported opening-info version")
        return data

    async def search(self, query: str) -> list[BusinessSummary]:
        """Search public businesses by name."""
        data = await self._get(
            f"{BASE_URL}/api/v1/businesses", {"q": query, "limit": "10"}
        )
        results: list[BusinessSummary] = []
        for item in data.get("businesses", []) if isinstance(data, dict) else []:
            if item.get("publicId") and item.get("name"):
                results.append(
                    BusinessSummary(
                        id=item["publicId"],
                        name=item["name"],
                        city=item.get("city") or "",
                    )
                )
        return results
