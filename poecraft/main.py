"""PoECraft — Main entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from poecraft.api.auth import SessionAuth
from poecraft.api.client import PoeApiClient
from poecraft.config import get_config, load_config
from poecraft.filter import writer as filter_writer
from poecraft.logwatch import ClientLogWatcher, resolve_log_path
from poecraft.state import get_state
from poecraft.web.routes import router as web_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("poecraft")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: wire client + state + logwatch, initial refresh, graceful stop."""
    config = get_config()
    logger.info(
        "PoECraft starting — league=%s, tabs=%s", config.league, config.stash_tabs
    )

    auth = SessionAuth(config.session_id)
    client = PoeApiClient(config.account_name, config.league, auth)
    app.state.client = client
    app.state.filter_writer = filter_writer
    state = get_state()
    app.state.recipe_state = state

    # Zone-change-driven refresh via Client.txt logwatch.
    watcher: ClientLogWatcher | None = None
    watcher_task: asyncio.Task | None = None
    log_path = resolve_log_path(config)
    if log_path is not None:
        async def on_zone_change(area: str) -> None:
            logger.info("Zone change to %s — refreshing", area)
            try:
                await state.refresh(client, config, filter_writer)
            except Exception as exc:  # noqa: BLE001 — don't kill the watcher
                logger.warning("Refresh on zone change failed: %s", exc)

        watcher = ClientLogWatcher(log_path, on_zone_change=on_zone_change)
        app.state.watcher = watcher
        watcher_task = asyncio.create_task(watcher.start())
        logger.info("Watching Client.txt: %s", log_path)
    else:
        app.state.watcher = None
        logger.info("No Client.txt resolved; logwatch disabled")

    # Initial refresh on startup (defensive: never crash the app on API/filter errors).
    try:
        await state.refresh(client, config, filter_writer)
        logger.info("Initial refresh complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Initial refresh failed: %s", exc)

    yield

    if watcher is not None and watcher_task is not None:
        await watcher.stop()
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass
    await client.close()
    logger.info("PoECraft shutting down")


app = FastAPI(title="PoECraft", lifespan=lifespan)
app.include_router(web_router)


def cli():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="PoECraft — Chaos Recipe Filter Tool")
    parser.add_argument("--config", "-c", help="Path to config.yaml")
    parser.add_argument("--host", help="Bind host (default: from config)")
    parser.add_argument("--port", type=int, help="Bind port (default: from config)")
    args = parser.parse_args()

    config = load_config(args.config)
    host = args.host or config.host
    port = args.port or config.port

    logger.info("Starting server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
