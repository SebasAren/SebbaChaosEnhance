"""Web UI routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
    await state.refresh(
        request.app.state.client,
        get_config(),
        request.app.state.filter_writer,
    )
    return _status_payload()


@router.post("/api/config")
async def api_config(config: Config):
    """Validate and persist the posted config (writes to the active config path)."""
    save_config(config)
    return {"status": "saved"}


@router.get("/api/leagues")
async def api_leagues(request: Request):
    """Proxy the active client's league list."""
    leagues = await request.app.state.client.get_leagues()
    return {"leagues": leagues}


@router.get("/api/tabs")
async def api_tabs(request: Request):
    """Proxy the active client's stash tab metadata."""
    tabs = await request.app.state.client.get_stash_tabs()
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
