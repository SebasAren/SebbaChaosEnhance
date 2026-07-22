"""PoE API client - fetches stash tab data from the Path of Exile API.

Uses the legacy session-ID authenticated endpoints:
    https://www.pathofexile.com/character-window/get-stash-items

Handles rate limiting by respecting X-Rate-Limit-* response headers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from urllib.parse import quote

import httpx

from poecraft import __version__
from poecraft.api.auth import SessionAuth
from poecraft.api.models import (
    StashItem,
    StashTabContents,
    StashTabMetadataResponse,
    StashTabProps,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.pathofexile.com"
USER_AGENT = f"poecraft/{__version__} (linux-native; github.com/poecraft)"


class RateLimitState:
    """Tracks rate limit state from API response headers."""

    def __init__(self):
        self.remaining: int = 999
        self.reset_at: float = 0  # timestamp when limit resets

    def update_from_headers(self, headers: dict) -> None:
        """Parse X-Rate-Limit-* headers."""
        if "x-ratelimit-remaining" in headers:
            try:
                self.remaining = int(headers["x-ratelimit-remaining"])
            except ValueError:
                pass

        if "x-ratelimit-reset" in headers:
            try:
                self.reset_at = float(headers["x-ratelimit-reset"])
            except ValueError:
                pass

        if self.remaining <= 0:
            wait_time = max(0, self.reset_at - time.time())
            logger.warning(
                "Rate limit reached! Remaining: %d, resets in %.1fs",
                self.remaining,
                wait_time,
            )

    def wait_if_needed(self) -> float:
        """Returns seconds to wait if rate limited, 0 otherwise."""
        if self.remaining <= 0:
            return max(0, self.reset_at - time.time())
        return 0


class PoeApiClient:
    """Client for the Path of Exile stash tab API."""

    def __init__(
        self,
        account_name: str,
        league: str,
        auth: SessionAuth,
    ):
        self.account_name = account_name
        self.league = league
        self.auth = auth
        self._rate_limit = RateLimitState()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client with auth cookies."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
            self._client.headers["User-Agent"] = USER_AGENT
            self.auth.apply_to_client(self._client)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(
        self,
        url: str,
        params: Optional[dict] = None,
        *,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """Authenticated GET with rate-limit handling and 429 backoff/retry.

        Retries up to ``max_retries`` times on 429 Too Many Requests, honoring
        the Retry-After header. Other non-200 responses (and HTTP errors)
        return None immediately without retrying.
        """
        for attempt in range(max_retries + 1):
            # Wait if a prior response put us under the rate limit.
            wait = self._rate_limit.wait_if_needed()
            if wait > 0:
                logger.info("Rate limited, waiting %.1fs...", wait)
                await asyncio.sleep(wait)

            client = await self._get_client()
            try:
                resp = await client.get(url, params=params)
                self._rate_limit.update_from_headers(dict(resp.headers))

                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", "10"))
                    self._rate_limit.remaining = 0
                    self._rate_limit.reset_at = time.time() + retry_after
                    if attempt < max_retries:
                        logger.warning(
                            "429 Too Many Requests, backing off %ds (attempt %d/%d)",
                            retry_after,
                            attempt + 1,
                            max_retries,
                        )
                        continue  # top-of-loop wait_if_needed() sleeps once
                    logger.warning(
                        "429 Too Many Requests, giving up after %d retries",
                        max_retries,
                    )
                    return None
                if resp.status_code in (401, 403):
                    logger.error(
                        "Auth error %d - check your POESESSID", resp.status_code
                    )
                    return None
                logger.warning("API returned %d: %s", resp.status_code, resp.text[:200])
                return None
            except httpx.HTTPError as e:
                logger.error("HTTP error: %s", e)
                return None
        return None

    def _stash_props_url(self, personal: bool = True) -> str:
        """URL for fetching stash tab metadata."""
        escaped_name = quote(self.account_name, safe="")
        if personal:
            return (
                f"{BASE_URL}/character-window/get-stash-items"
                f"?accountName={escaped_name}&league={quote(self.league, safe='')}"
                f"&tabs=1&tabIndex="
            )
        # Guild stash - not implementing for v1
        raise NotImplementedError("Guild stash not supported in v1")

    def _stash_contents_url(self, tab_index: int, personal: bool = True) -> str:
        """URL for fetching individual tab contents."""
        escaped_name = quote(self.account_name, safe="")
        if personal:
            return (
                f"{BASE_URL}/character-window/get-stash-items"
                f"?accountName={escaped_name}&league={quote(self.league, safe='')}"
                f"&tabIndex={tab_index}"
            )
        raise NotImplementedError("Guild stash not supported in v1")

    async def get_stash_tabs(self) -> list[StashTabProps]:
        """Fetch the list of all stash tabs (metadata only, no items).

        Returns:
            List of StashTabProps with tab names, types, and indices.
        """
        url = self._stash_props_url(personal=True)
        data = await self._get(url)

        if data is None:
            return []

        try:
            response = StashTabMetadataResponse(**data)
            return response.tabs
        except Exception as e:
            logger.error("Failed to parse stash tab metadata: %s", e)
            return []

    async def get_stash_tab_contents(self, tab_index: int) -> StashTabContents:
        """Fetch the contents of a single stash tab.

        Args:
            tab_index: 0-based index of the stash tab.

        Returns:
            StashTabContents with the items in the tab.
        """
        url = self._stash_contents_url(tab_index, personal=True)
        data = await self._get(url)

        if data is None:
            return StashTabContents()

        try:
            return StashTabContents(**data)
        except Exception as e:
            logger.error("Failed to parse tab %d contents: %s", tab_index, e)
            return StashTabContents()

    async def get_all_selected_tabs(
        self, tab_indices: list[int]
    ) -> dict[int, list[StashItem]]:
        """Fetch contents for multiple stash tabs with rate limit handling.

        Args:
            tab_indices: List of 0-based tab indices to fetch.

        Returns:
            Dict mapping tab_index -> list of items in that tab.
        """
        result: dict[int, list[StashItem]] = {}

        for idx in tab_indices:
            contents = await self.get_stash_tab_contents(idx)
            result[idx] = contents.items
            logger.info("Fetched tab %d: %d items", idx, len(contents.items))
            # Small delay between requests to be nice to the API.
            await asyncio.sleep(0.5)

        return result

    async def get_leagues(self) -> list[str]:
        """Fetch the list of active main leagues (public, no auth required).

        Returns:
            List of league name strings.
        """
        url = "https://api.pathofexile.com/leagues?type=main&realm=pc"
        data = await self._get(url)
        if data is None:
            return []
        try:
            return [league["id"] for league in data]
        except (KeyError, TypeError) as e:
            logger.error("Failed to parse leagues response: %s", e)
            return []
