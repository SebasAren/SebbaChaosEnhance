"""Session management for PoE API authentication.

Supports POESESSID cookie-based auth (simpler than OAuth2 for a
self-hosted tool). The session ID is sent as a cookie on every request.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

POESESSID_COOKIE_NAME = "POESESSID"


class SessionAuth:
    """Manages POESESSID cookie authentication."""

    def __init__(self, session_id: str = ""):
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value.strip()

    @property
    def is_configured(self) -> bool:
        return bool(self._session_id)

    def apply_to_client(self, client: httpx.AsyncClient) -> None:
        """Set the POESESSID cookie on the httpx client."""
        if not self._session_id:
            return

        client.cookies.set(
            POESESSID_COOKIE_NAME,
            self._session_id,
            domain="www.pathofexile.com",
        )

    async def validate(self, client: httpx.AsyncClient) -> bool:
        """Check if the current session ID is valid by hitting a health endpoint.

        Returns True if the session is valid, False otherwise.
        """
        if not self._session_id:
            return False

        try:
            resp = await client.get(
                "https://www.pathofexile.com/api/account-avatar?page=1&perPage=1&custom=false"
            )
            if resp.status_code == 200:
                logger.info("Session ID validation successful")
                return True
            else:
                logger.warning("Session ID validation failed: %s", resp.status_code)
                return False
        except httpx.HTTPError as e:
            logger.warning("Session ID validation error: %s", e)
            return False
