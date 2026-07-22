"""Tests for poecraft.web dashboard + endpoints, and poecraft.state.

Endpoint contracts are exercised via FastAPI TestClient with the PoeApiClient
and filter writer mocked; grid data prep is validated structurally.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from poecraft.api.models import StashItem, StashTabProps
from poecraft.config import Config, load_config
from poecraft.filter import writer as filter_writer_mod
from poecraft.recipe.sets import EnhancedItem, RecipeSet, RecipeStatus
from poecraft.recipe.types import FrameType, ItemClass
from poecraft.state import RecipeState, get_state
from poecraft.web.routes import router


def _item(
    id: str,
    cls: ItemClass,
    *,
    x: int = 0,
    y: int = 0,
    w: int = 1,
    h: int = 1,
) -> EnhancedItem:
    return EnhancedItem(
        id=id,
        name="",
        type_line="",
        item_level=70,
        frame_type=FrameType.RARE,
        identified=False,
        icon="",
        derived_item_class=cls,
        stash_tab_index=0,
        x=x,
        y=y,
        w=w,
        h=h,
        influences={},
    )


def test_to_grid_assigns_set_index_per_item_and_none_for_unassigned() -> None:
    set0 = RecipeSet(
        items={ItemClass.RINGS: [_item("ring-1", ItemClass.RINGS, x=2, y=3, w=1, h=1)]}
    )
    set1 = RecipeSet(
        items={ItemClass.HELMETS: [_item("helm-1", ItemClass.HELMETS, x=0, y=0, w=2, h=2)]}
    )
    unassigned = [_item("surplus-ring", ItemClass.RINGS, x=10, y=11, w=1, h=1)]

    status = RecipeStatus(
        completed_sets=0,
        in_progress=[set0, set1],
        missing_classes={ItemClass.HELMETS, ItemClass.RINGS},
        item_counts={ItemClass.RINGS: 2, ItemClass.HELMETS: 1},
        unassigned_items=unassigned,
        needs_lower_level=False,
    )

    grid = status.to_grid()
    items = grid["items"]

    by_id = {it["id"]: it for it in items}
    assert set(by_id) == {"ring-1", "helm-1", "surplus-ring"}

    # set 0 holds the ring; set 1 holds the helmet; surplus is unassigned.
    assert by_id["ring-1"]["set_index"] == 0
    assert by_id["helm-1"]["set_index"] == 1
    assert by_id["surplus-ring"]["set_index"] is None

    # each item carries its geometry + class string.
    assert by_id["ring-1"]["x"] == 2 and by_id["ring-1"]["y"] == 3
    assert by_id["ring-1"]["w"] == 1 and by_id["ring-1"]["h"] == 1
    assert by_id["ring-1"]["class"] == ItemClass.RINGS.value
    assert by_id["helm-1"]["class"] == ItemClass.HELMETS.value


# ---------------------------------------------------------------------------
# RecipeState.refresh
# ---------------------------------------------------------------------------


def _raw_ring(item_id: str, *, ilvl: int = 70) -> StashItem:
    return StashItem(
        id=item_id,
        name="",
        typeLine="Gold Ring",
        ilvl=ilvl,
        frameType=2,  # rare
        identified=False,
        icon="",
        category={"ring": []},
        x=0,
        y=0,
        w=1,
        h=1,
    )


class FakeClient:
    """Stand-in for PoeApiClient: returns canned tab contents."""

    def __init__(self, tabs: dict[int, list[StashItem]]) -> None:
        self._tabs = tabs
        self.requested_indices: list[int] | None = None

    async def get_all_selected_tabs(self, tab_indices: list[int]) -> dict[int, list[StashItem]]:
        self.requested_indices = list(tab_indices)
        return self._tabs


class FakeFilterWriter:
    """Stand-in for the filter writer module; records update_filter calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def update_filter(
        self,
        *,
        path: str,
        missing_classes: set[ItemClass],
        recipe_type,
        include_identified: bool,
        needs_lower_level: bool = True,
    ) -> bool:
        self.calls.append(
            {
                "path": path,
                "missing_classes": set(missing_classes),
                "recipe_type": recipe_type,
                "include_identified": include_identified,
                "needs_lower_level": needs_lower_level,
            }
        )
        return True


class ProxyClient:
    """Stand-in client exposing get_leagues / get_stash_tabs for proxy tests."""

    def __init__(
        self,
        *,
        leagues: list[str] | None = None,
        tabs: list[StashTabProps] | None = None,
    ) -> None:
        self._leagues = leagues or []
        self._tabs = tabs or []

    async def get_leagues(self) -> list[str]:
        return self._leagues

    async def get_stash_tabs(self) -> list[StashTabProps]:
        return self._tabs


def test_state_refresh_stores_status_and_calls_update_filter() -> None:
    state = RecipeState()
    client = FakeClient({0: [_raw_ring("r1"), _raw_ring("r2")]})
    writer = FakeFilterWriter()
    config = Config(
        recipe_type="chaos",
        set_threshold=1,
        loot_filter_path="/tmp/x.filter",
    )

    status = asyncio.run(state.refresh(client, config, writer))

    # current + last_refresh populated
    assert state.current is status
    assert isinstance(state.last_refresh, datetime)

    # client asked for the configured tabs
    assert client.requested_indices == config.stash_tabs

    # update_filter called once with the status's missing_classes
    assert len(writer.calls) == 1
    call = writer.calls[0]
    assert call["path"] == "/tmp/x.filter"
    assert call["missing_classes"] == status.missing_classes
    assert call["recipe_type"].value == "chaos"
    # sanity: 2 rings and nothing else -> helmets still missing
    assert ItemClass.HELMETS in call["missing_classes"]


def test_state_refresh_skips_filter_when_loot_filter_path_empty() -> None:
    """An unset loot_filter_path means no filter to touch — refresh must not crash."""
    state = RecipeState()
    client = FakeClient({0: [_raw_ring("r1"), _raw_ring("r2")]})
    writer = FakeFilterWriter()
    config = Config(
        recipe_type="chaos",
        set_threshold=1,
        loot_filter_path="",  # empty => no filter configured
    )

    status = asyncio.run(state.refresh(client, config, writer))

    # refresh still succeeds and stores status
    assert state.current is status
    # update_filter was NOT called (no path to write to)
    assert writer.calls == []


def test_state_refresh_preserves_tab_index() -> None:
    """Items carry the tab index they were fetched from, not always 0.

    The PoE API embeds no per-item tab index; refresh must inject it from the
    fetch loop so EnhancedItem.stash_tab_index reflects reality.
    """
    state = RecipeState()
    # ring in tab 0, ring in tab 3 -> both eligible, both end up in set 0.
    client = FakeClient({0: [_raw_ring("r0")], 3: [_raw_ring("r3")]})
    writer = FakeFilterWriter()
    config = Config(recipe_type="chaos", set_threshold=1, loot_filter_path="")

    status = asyncio.run(state.refresh(client, config, writer))

    by_id = {it.id: it for s in status.in_progress for arr in s.items.values() for it in arr}
    assert by_id["r0"].stash_tab_index == 0
    assert by_id["r3"].stash_tab_index == 3


# ---------------------------------------------------------------------------
# RecipeState payload + subscriber pub/sub
# ---------------------------------------------------------------------------


def _refresh(
    state: RecipeState,
    items: dict[int, list[StashItem]] | None = None,
) -> RecipeStatus:
    client = FakeClient(items or {0: [_raw_ring("r1"), _raw_ring("r2")]})
    writer = FakeFilterWriter()
    config = Config(recipe_type="chaos", set_threshold=1, loot_filter_path="/tmp/x.filter")
    return asyncio.run(state.refresh(client, config, writer))


def test_state_to_payload_matches_status_contract() -> None:
    """RecipeState.to_payload() mirrors the /api/status JSON shape."""
    state = RecipeState()
    _refresh(state)

    payload = state.to_payload()
    assert payload["completed_sets"] == 0
    assert payload["item_counts"] == {"Rings": 2}
    assert "Helmets" in payload["missing_classes"]
    assert payload["grid"]["items"]
    assert payload["last_refresh"] == state.last_refresh.isoformat()


def test_state_to_payload_empty_when_no_refresh_yet() -> None:
    """A fresh state yields the same empty shape as the /api/status default."""
    payload = RecipeState().to_payload()
    assert payload == {
        "completed_sets": 0,
        "item_counts": {},
        "missing_classes": [],
        "grid": {"items": []},
        "last_refresh": None,
    }


def test_state_refresh_notifies_subscribers() -> None:
    """Each subscribe() queue receives the updated payload on refresh."""
    state = RecipeState()
    q = state.subscribe()
    _refresh(state)

    payload = q.get_nowait()  # would raise if nothing was pushed
    assert payload["item_counts"] == {"Rings": 2}
    assert payload["last_refresh"] is not None
    assert q.empty()


def test_state_refresh_notifies_all_subscribers() -> None:
    state = RecipeState()
    q1 = state.subscribe()
    q2 = state.subscribe()
    _refresh(state)

    assert q1.get_nowait()["item_counts"] == {"Rings": 2}
    assert q2.get_nowait()["item_counts"] == {"Rings": 2}


def test_unsubscribed_queue_receives_nothing() -> None:
    state = RecipeState()
    q = state.subscribe()
    state.unsubscribe(q)
    _refresh(state)

    assert q.empty()


# ---------------------------------------------------------------------------
# HTTP endpoints (FastAPI TestClient)
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    """Fresh app with just the web router (no lifespan wiring)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _reset_state() -> RecipeState:
    state = get_state()
    state.current = None
    state.last_refresh = None
    return state


def test_api_status_empty_state_returns_empty_shape() -> None:
    _reset_state()
    client = _client()

    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed_sets"] == 0
    assert body["item_counts"] == {}
    assert body["missing_classes"] == []
    assert body["grid"] == {"items": []}
    assert body["last_refresh"] is None


def test_api_refresh_updates_status() -> None:
    import poecraft.config as cfg_mod

    _reset_state()
    cfg_mod._config = Config(
        recipe_type="chaos",
        set_threshold=1,
        stash_tabs=[0],
        loot_filter_path="/tmp/x.filter",
    )
    client = _client()
    client.app.state.client = FakeClient({0: [_raw_ring("r1"), _raw_ring("r2")]})
    client.app.state.filter_writer = FakeFilterWriter()

    resp = client.post("/api/refresh")
    assert resp.status_code == 200

    # subsequent /api/status reflects the refreshed data
    status = client.get("/api/status").json()
    assert status["item_counts"] == {"Rings": 2}
    assert status["last_refresh"] is not None
    # both rings landed in set 0
    assert [it["set_index"] for it in status["grid"]["items"]] == [0, 0]


class _FakeRequest:
    """Minimal Request stand-in: the SSE loop only calls is_disconnected()."""

    async def is_disconnected(self) -> bool:
        return False


def _sse_data(frame) -> str:
    """Extract the JSON payload from an SSE ``data:`` line."""
    text = frame.decode() if isinstance(frame, (bytes, bytearray)) else frame
    for line in text.splitlines():
        if line.startswith("data: "):
            return line[len("data: ") :]
    raise AssertionError("no data line in SSE frame")


def test_api_events_catch_up_and_push() -> None:
    """GET /api/events yields current status on connect, then a frame per refresh.

    Driven by calling the handler directly against its streaming response
    iterator (rather than TestClient, which can't cleanly cancel an infinite
    SSE generator), so the push-through-stream path is exercised
    deterministically without a long-lived connection.
    """
    import poecraft.config as cfg_mod
    from poecraft.web.routes import api_events

    _reset_state()
    config = Config(
        recipe_type="chaos",
        set_threshold=1,
        stash_tabs=[0],
        loot_filter_path="/tmp/x.filter",
    )
    cfg_mod._config = config
    client = FakeClient({0: [_raw_ring("r1"), _raw_ring("r2")]})
    writer = FakeFilterWriter()

    async def drive() -> None:
        state = get_state()
        # initial refresh → the catch-up frame carries this data
        await state.refresh(client, config, writer)

        response = await api_events(_FakeRequest())
        assert response.media_type.startswith("text/event-stream")
        assert "X-Accel-Buffering" in response.headers
        agen = response.body_iterator

        first = await agen.__anext__()  # catch-up
        payload0 = json.loads(_sse_data(first))
        assert payload0["item_counts"] == {"Rings": 2}
        assert payload0["last_refresh"] is not None

        # the next pull blocks until a refresh pushes a new payload
        pending = asyncio.create_task(agen.__anext__())
        await state.refresh(client, config, writer)
        payload1 = json.loads(_sse_data(await pending))
        assert payload1["item_counts"] == {"Rings": 2}

        await agen.aclose()

    asyncio.run(drive())


def test_api_config_valid_body_is_saved(monkeypatch, tmp_path) -> None:
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setenv("POECRAFT_CONFIG", str(cfg_path))
    client = _client()

    body = {"league": "Hardcore", "stash_tabs": [0, 1], "recipe_type": "chaos"}
    resp = client.post("/api/config", json=body)

    assert resp.status_code == 200
    assert cfg_path.exists()
    saved = load_config(cfg_path)
    assert saved.league == "Hardcore"
    assert saved.stash_tabs == [0, 1]


def test_api_config_invalid_body_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("POECRAFT_CONFIG", str(tmp_path / "config.yaml"))
    client = _client()

    resp = client.post("/api/config", json={"recipe_type": "bogus"})

    assert resp.status_code == 422


def test_api_leagues_proxies_client() -> None:
    client = _client()
    client.app.state.client = ProxyClient(leagues=["Standard", "Hardcore"])

    resp = client.get("/api/leagues")

    assert resp.status_code == 200
    assert resp.json() == {"leagues": ["Standard", "Hardcore"]}


def test_api_tabs_proxies_client() -> None:
    import poecraft.config as cfg_mod

    cfg_mod._config = Config(account_name="acc", session_id="sess", league="Standard")
    client = _client()
    client.app.state.client = ProxyClient(
        tabs=[StashTabProps(name="Quad", index=0, type="NormalStash")]
    )

    resp = client.get("/api/tabs")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tabs"]) == 1
    assert body["tabs"][0]["name"] == "Quad"
    assert body["tabs"][0]["index"] == 0
    assert "error" not in body


def test_api_tabs_missing_account_name_returns_error() -> None:
    """With no account name saved, the picker should tell the user, not return []."""
    import poecraft.config as cfg_mod

    cfg_mod._config = Config(account_name="", session_id="sess")
    client = _client()
    client.app.state.client = ProxyClient(
        tabs=[StashTabProps(name="X", index=0)]  # would succeed, but never reached
    )

    body = client.get("/api/tabs").json()

    assert body["tabs"] == []
    assert "account name" in body["error"]


def test_api_tabs_missing_session_returns_error() -> None:
    import poecraft.config as cfg_mod

    cfg_mod._config = Config(account_name="acc", session_id="")
    client = _client()
    client.app.state.client = ProxyClient(tabs=[StashTabProps(name="X", index=0)])

    body = client.get("/api/tabs").json()

    assert body["tabs"] == []
    assert "POESESSID" in body["error"]


def test_api_tabs_auth_failure_reports_error() -> None:
    """Complete credentials but the API yields no tabs -> auth-failure guidance.

    A real account always has stash tabs, so an empty result almost always
    means an expired/invalid POESESSID; the endpoint surfaces that rather than
    an empty list.
    """
    import poecraft.config as cfg_mod

    cfg_mod._config = Config(account_name="acc", session_id="sess", league="Standard")
    client = _client()
    client.app.state.client = ProxyClient(tabs=[])  # simulates a 403 / empty reply

    body = client.get("/api/tabs").json()

    assert body["tabs"] == []
    assert body["error"]
    assert "POESESSID" in body["error"]


def test_lifespan_wires_client_state_and_watcher(tmp_path) -> None:
    """Startup builds the client + state + logwatch watcher; shutdown stops them.

    Empty stash_tabs means the initial refresh issues no network calls; the
    filter + log files are pre-created so refresh/update_filter succeed.
    """
    import poecraft.config as cfg_mod
    from poecraft.main import app

    log_file = tmp_path / "Client.txt"
    log_file.write_text("")
    filter_file = tmp_path / "x.filter"
    filter_file.write_text("")

    cfg_mod._config = Config(
        account_name="acc",
        league="Standard",
        session_id="",
        stash_tabs=[],
        loot_filter_path=str(filter_file),
        client_log_path=str(log_file),
    )

    client = TestClient(app)
    with client:
        assert client.app.state.client is not None
        assert client.app.state.filter_writer is filter_writer_mod
        watcher = client.app.state.watcher
        assert watcher is not None
        assert watcher._running is True
        # initial refresh populated the state without network
        assert client.app.state.recipe_state.current is not None

    # shutdown stopped the watcher
    assert watcher._running is False


def test_dashboard_renders_grid_and_endpoint_wiring() -> None:
    _reset_state()
    client = _client()

    resp = client.get("/")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="grid"' in html
    assert "/api/status" in html
    assert "/api/refresh" in html
    assert "/api/config" in html
    # grid renderer references the set_index coloring contract
    assert "set_index" in html


def test_dashboard_injects_per_slot_highlight_colors() -> None:
    """The dashboard's class lists are colored to match the loot filter, so what
    the player sees highlighted on the ground matches the dashboard."""
    from poecraft.filter.generator import CLASS_COLORS

    _reset_state()
    client = _client()

    html = client.get("/").text
    # every class name and its filter bg color are injected as a JS mapping
    for cls, style in CLASS_COLORS.items():
        assert cls.value in html
        assert style["bg"].lower() in html.lower()
    # jewelry (rings/amulets/belts) shares one color -> it repeats >= 3x
    jewelry_color = CLASS_COLORS[ItemClass.RINGS]["bg"].lower()
    assert html.lower().count(jewelry_color) >= 3


def test_dashboard_renders_regardless_of_cwd(tmp_path, monkeypatch) -> None:
    """Template lookup must not depend on process CWD.

    The installed tool runs from $HOME (e.g. under systemd), so a relative
    templates directory would fail. Reproduce by chdir-ing away from the
    project root before rendering the dashboard.
    """
    monkeypatch.chdir(tmp_path)
    _reset_state()
    client = _client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert 'id="grid"' in resp.text


def test_api_browse_lists_dirs_and_filters_files(tmp_path, monkeypatch) -> None:
    """The file picker needs directories (to navigate) plus files filtered by ext.

    <input type="file"> can't expose real paths in a browser, so the config
    pickers drive this endpoint instead. It must: always show directories,
    show only matching files when `ext` is given, expose an absolute path and
    a parent for navigation, and fall back to home on a bad path.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # build a little tree: a dir, a matching file, and a non-matching file
    (tmp_path / "subdir").mkdir()
    (tmp_path / "my.filter").write_text("")
    (tmp_path / "notes.txt").write_text("")

    client = _client()

    # .filter filtering: subdir shows, my.filter shows, notes.txt is hidden
    resp = client.get("/api/browse", params={"path": str(tmp_path), "ext": ".filter"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(tmp_path)
    assert body["parent"] == str(tmp_path.parent)
    names = {e["name"]: e["type"] for e in body["entries"]}
    assert names["subdir"] == "dir"
    assert names["my.filter"] == "file"
    assert "notes.txt" not in names  # filtered out

    # no ext filter: every file shows
    resp = client.get("/api/browse", params={"path": str(tmp_path)})
    names = {e["name"] for e in resp.json()["entries"]}
    assert {"subdir", "my.filter", "notes.txt"} <= names

    # a file path (e.g. a field's current value) -> browse its parent dir
    resp = client.get("/api/browse", params={"path": str(tmp_path / "my.filter"), "ext": ".filter"})
    assert resp.json()["path"] == str(tmp_path)

    # an unreadable / non-existent path falls back to home
    resp = client.get("/api/browse", params={"path": "/no/such/dir/here"})
    assert resp.json()["path"] == str(tmp_path)


def test_api_browse_default_path_is_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    client = _client()

    resp = client.get("/api/browse")

    assert resp.status_code == 200
    assert resp.json()["path"] == str(tmp_path)


def test_overlay_redirects_to_dashboard() -> None:
    client = _client()

    resp = client.get("/overlay", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Client resolution (shared by manual refresh + zone-change refresh)
# ---------------------------------------------------------------------------


def test_resolve_client_rebuilds_when_credentials_change() -> None:
    """resolve_client rebuilds the client when the saved config's creds change.

    Keeps automated refreshes honest after the user re-enters their POESESSID
    or switches account/league without restarting the server.
    """
    import poecraft.config as cfg_mod
    from poecraft.api.auth import SessionAuth
    from poecraft.api.client import PoeApiClient
    from poecraft.web.routes import resolve_client

    cfg_mod._config = Config(account_name="new", league="NewLeague", session_id="new-sess")
    old = PoeApiClient("old", "OldLeague", SessionAuth("old-sess"))
    app_state = SimpleNamespace(client=old)

    resolved = asyncio.run(resolve_client(app_state))

    assert resolved is not old
    assert resolved.account_name == "new"
    assert resolved.league == "NewLeague"
    assert resolved.auth.session_id == "new-sess"
    # the new client is published back onto app state for later callers
    assert app_state.client is resolved


def test_resolve_client_passes_through_test_doubles() -> None:
    """Duck-typed stand-ins (not PoeApiClient instances) are returned unchanged."""
    from poecraft.web.routes import resolve_client

    fake = FakeClient({0: []})
    app_state = SimpleNamespace(client=fake)

    assert asyncio.run(resolve_client(app_state)) is fake


def test_zone_change_refresh_uses_live_config_not_startup_capture(tmp_path) -> None:
    """Regression: a zone-change refresh must use the *current* saved config.

    The logwatch callback used to close over the startup config + client, so
    after the user changed their selected stash tab (and saved), automated
    refreshes kept fetching the old tab — often an empty one — and blanked the
    dashboard. It must instead resolve the live config + client every fire.
    """
    import poecraft.config as cfg_mod
    from poecraft.main import app

    log_file = tmp_path / "Client.txt"
    log_file.write_text("")
    filter_file = tmp_path / "x.filter"
    filter_file.write_text("")

    # Empty tabs at startup so the initial refresh issues no network calls.
    cfg_mod._config = Config(
        account_name="acc",
        league="Standard",
        session_id="sess",
        stash_tabs=[],
        loot_filter_path=str(filter_file),
        client_log_path=str(log_file),
    )

    with TestClient(app) as client:
        # User picks a different tab and saves — get_config() now reflects it.
        cfg_mod._config = cfg_mod._config.model_copy(update={"stash_tabs": [29]})
        # Observing client records which tabs the refresh actually fetches.
        fake = FakeClient({29: [_raw_ring("r1")]})
        client.app.state.client = fake

        asyncio.run(client.app.state.watcher.on_zone_change("Aspirants' Plaza"))

        # Live config (tab 29) must drive the fetch, not the startup config.
        assert fake.requested_indices == [29]
        # ...and the grid reflects the fetched items, not a stale/empty tab.
        payload = client.app.state.recipe_state.to_payload()
        assert payload["item_counts"] == {"Rings": 1}
