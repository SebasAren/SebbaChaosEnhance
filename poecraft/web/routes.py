"""Web UI routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from poecraft.api.auth import SessionAuth
from poecraft.api.client import PoeApiClient
from poecraft.config import Config, get_config, save_config
from poecraft.state import get_state

router = APIRouter()
# Resolve relative to this module so it works regardless of the process CWD
# (the installed tool runs from $HOME under systemd, not the project root).
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    config = get_config()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "config": config,
            "version": "0.1.0",
        },
    )


@router.get("/overlay")
async def overlay():
    """Overlay folded into the dashboard; redirect there."""
    return RedirectResponse(url="/", status_code=302)


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/api/status")
async def api_status():
    """Current recipe status as JSON: counts, missing classes, grid, last_refresh."""
    return _status_payload()


@router.post("/api/refresh")
async def api_refresh(request: Request):
    """Trigger a refresh cycle and return the updated status."""
    state = get_state()
    client = await _ensure_client(request)
    await state.refresh(
        client,
        get_config(),
        request.app.state.filter_writer,
    )
    return _status_payload()


@router.post("/api/config")
async def api_config(config: Config):
    """Validate and persist the posted config (writes to the active config path)."""
    save_config(config)
    return {"status": "saved"}


@router.get("/api/browse")
async def api_browse(path: str | None = None, ext: str | None = None):
    """List a directory's contents for the config-page file pickers.

    Browsers' <input type="file"> deliberately hide real filesystem paths, so
    the pickers use this endpoint to navigate the local filesystem. Always
    returns directories (for navigation) and files optionally filtered by
    extension (`ext`, e.g. ".filter" or ".txt").
    """
    target = Path(path).expanduser() if path else Path.home()
    # A file path (e.g. the field's current value) -> browse its parent.
    if target.is_file():
        target = target.parent
    # Anything unreadable / non-existent falls back to the home directory.
    if not target.is_dir():
        target = Path.home()

    entries: list[dict] = []
    try:
        children = sorted(
            target.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except (PermissionError, OSError):
        children = []
    for child in children:
        try:
            if child.is_dir():
                entries.append({"name": child.name, "type": "dir", "path": str(child)})
            elif child.is_file():
                if ext is None or child.suffix.lower() == ext.lower():
                    entries.append({"name": child.name, "type": "file", "path": str(child)})
        except (PermissionError, OSError):
            continue  # unreadable entry — skip, don't abort the listing

    parent = target.parent if target.parent != target else None
    return {"path": str(target), "parent": str(parent) if parent else None, "entries": entries}


async def _ensure_client(request: Request) -> PoeApiClient:
    """Return an API client reflecting the *current saved* config.

    The app-state client is built once at startup from the initial config, so
    when the user saves different credentials we must rebuild it — otherwise
    tab listings and refreshes would keep using the old account/league/session.
    Test stand-ins (duck-typed fakes) are passed through unchanged.
    """
    client = request.app.state.client
    if isinstance(client, PoeApiClient):
        config = get_config()
        if (
            client.account_name != config.account_name
            or client.league != config.league
            or client.auth.session_id != config.session_id
        ):
            new_client = PoeApiClient(
                config.account_name,
                config.league,
                SessionAuth(config.session_id),
            )
            request.app.state.client = new_client
            try:
                await client.close()
            except Exception:
                pass
            return new_client
    return client


@router.get("/api/leagues")
async def api_leagues(request: Request):
    """Proxy the active client's league list."""
    client = await _ensure_client(request)
    leagues = await client.get_leagues()
    return {"leagues": leagues}


@router.get("/api/tabs")
async def api_tabs(request: Request):
    """Proxy the active client's stash tab metadata.

    Returns a human-readable ``error`` when tabs can't be fetched (missing
    credentials or an auth failure) so the picker can guide the user instead
    of silently showing an empty list.
    """
    config = get_config()
    missing = [
        label
        for label, value in (
            ("account name", config.account_name),
            ("POESESSID", config.session_id),
        )
        if not value
    ]
    if missing:
        return {
            "tabs": [],
            "error": (
                "Missing " + " and ".join(missing)
                + " — fill these in, click Save Config, then reopen the tab picker."
            ),
        }

    client = await _ensure_client(request)
    tabs = await client.get_stash_tabs()
    if not tabs:
        # A valid account always has stash tabs, so an empty result almost
        # always means an expired/invalid POESESSID or a league mismatch.
        return {
            "tabs": [],
            "error": (
                "The API returned no tabs — usually an expired or invalid "
                "POESESSID, or the league/account doesn't match. Re-enter "
                "your POESESSID, save, and click ↻ Reload."
            ),
        }
    return {"tabs": [tab.model_dump() for tab in tabs]}


def _status_payload() -> dict:
    """Build the JSON-serializable status payload from the current RecipeState."""
    state = get_state()
    status = state.current
    if status is None:
        return {
            "completed_sets": 0,
            "item_counts": {},
            "missing_classes": [],
            "grid": {"items": []},
            "last_refresh": None,
        }
    return {
        "completed_sets": status.completed_sets,
        "item_counts": {cls.value: n for cls, n in status.item_counts.items()},
        "missing_classes": sorted(cls.value for cls in status.missing_classes),
        "grid": status.to_grid(),
        "last_refresh": state.last_refresh.isoformat() if state.last_refresh else None,
    }
