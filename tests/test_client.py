"""Tests for poecraft.api.client — rate-limit parsing, _get status handling,
inter-tab delay, and league parsing. Uses httpx.MockTransport so no network."""

from __future__ import annotations

import asyncio

import httpx

from poecraft.api.auth import SessionAuth
from poecraft.api.client import PoeApiClient, RateLimitState
from poecraft.api.models import StashItem, StashTabContents


def _client_with(handler) -> PoeApiClient:
    """Build a PoeApiClient backed by a MockTransport handler (no network)."""
    c = PoeApiClient("acc", "Standard", SessionAuth("sid"))
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return c


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RateLimitState — pure header parsing
# ---------------------------------------------------------------------------


def test_rate_limit_state_parses_headers() -> None:
    rl = RateLimitState()
    rl.update_from_headers({"x-ratelimit-remaining": "3", "x-ratelimit-reset": "100"})
    assert rl.remaining == 3
    assert rl.reset_at == 100


def test_rate_limit_state_bad_headers_ignored() -> None:
    rl = RateLimitState()
    rl.update_from_headers({"x-ratelimit-remaining": "oops", "x-ratelimit-reset": ""})
    # unparseable values leave the defaults untouched
    assert rl.remaining == 999
    assert rl.reset_at == 0


def test_rate_limit_wait_when_exhausted() -> None:
    rl = RateLimitState()
    rl.remaining = 0
    rl.reset_at = 0  # in the past -> nothing to wait
    assert rl.wait_if_needed() == 0


# ---------------------------------------------------------------------------
# _get — status-code handling and 429 retry/backoff
# ---------------------------------------------------------------------------


def test_get_returns_json_on_200() -> None:
    def handler(req):
        return httpx.Response(200, json={"hello": "world"})

    async def run():
        c = _client_with(handler)
        try:
            return await c._get("https://example/")
        finally:
            await c.close()

    assert _run(run()) == {"hello": "world"}


def test_get_returns_none_on_auth_error() -> None:
    def handler(req):
        return httpx.Response(401)

    async def run():
        c = _client_with(handler)
        try:
            return await c._get("https://example/")
        finally:
            await c.close()

    assert _run(run()) is None


def test_get_retries_on_429_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"ok": True})

    async def run():
        c = _client_with(handler)
        try:
            return await c._get("https://example/", max_retries=3)
        finally:
            await c.close()

    assert _run(run()) == {"ok": True}
    assert calls["n"] == 2  # one 429, then one 200
    # one backoff sleep, bounded by retry-after (float from wait_if_needed)
    assert len(sleeps) == 1
    assert sleeps[0] <= 1.0


def test_get_gives_up_after_max_retries(monkeypatch) -> None:
    async def fake_sleep(d):
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "1"})

    async def run():
        c = _client_with(handler)
        try:
            return await c._get("https://example/", max_retries=2)
        finally:
            await c.close()

    assert _run(run()) is None
    # initial attempt + 2 retries = 3 total
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# get_all_selected_tabs — aggregation + inter-request delay
# ---------------------------------------------------------------------------


def test_get_all_selected_tabs_aggregates_with_delay(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    c = PoeApiClient("acc", "Standard", SessionAuth("sid"))
    fetched: list[int] = []

    async def fake_contents(idx):
        fetched.append(idx)
        return StashTabContents(
            items=[
                StashItem(
                    id=f"i{idx}",
                    typeLine="Gold Ring",
                    frameType=2,
                    ilvl=70,
                    identified=False,
                    category={"ring": []},
                )
            ]
        )

    monkeypatch.setattr(c, "get_stash_tab_contents", fake_contents)

    result = _run(c.get_all_selected_tabs([0, 2, 5]))

    assert set(result.keys()) == {0, 2, 5}
    assert fetched == [0, 2, 5]  # fetched in order
    assert len(result[2]) == 1
    # one politeness sleep per tab (delay now applies after every fetch)
    assert sleeps == [0.5, 0.5, 0.5]


# ---------------------------------------------------------------------------
# get_leagues — routed through _get, parsed to ids
# ---------------------------------------------------------------------------


def test_get_leagues_parses_ids() -> None:
    def handler(req):
        assert "api.pathofexile.com/leagues" in str(req.url)
        return httpx.Response(200, json=[{"id": "Standard"}, {"id": "Hardcore"}])

    async def run():
        c = _client_with(handler)
        try:
            return await c.get_leagues()
        finally:
            await c.close()

    assert _run(run()) == ["Standard", "Hardcore"]


def test_get_leagues_empty_on_failure() -> None:
    def handler(req):
        return httpx.Response(500)

    async def run():
        c = _client_with(handler)
        try:
            return await c.get_leagues()
        finally:
            await c.close()

    assert _run(run()) == []
