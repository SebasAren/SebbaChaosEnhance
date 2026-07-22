"""Web UI routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from poecraft.config import get_config

router = APIRouter()
templates = Jinja2Templates(directory="poecraft/web/templates")


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


@router.get("/overlay", response_class=HTMLResponse)
async def overlay(request: Request):
    """Minimal overlay page for browser-based overlays."""
    config = get_config()
    return templates.TemplateResponse(
        request=request,
        name="overlay.html",
        context={"config": config},
    )


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
