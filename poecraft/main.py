"""PoECraft — Main entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from poecraft.api.auth import SessionAuth
from poecraft.api.client import PoeApiClient
from poecraft.config import get_config, load_config
from poecraft.filter import writer as filter_writer
from poecraft.logwatch import ClientLogWatcher, resolve_log_path
from poecraft.state import get_state
from poecraft.web.routes import resolve_client
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
    logger.info("PoECraft starting — league=%s, tabs=%s", config.league, config.stash_tabs)

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
                # Resolve the live config + client each fire. The closure must
                # not capture the startup values: after the user changes the
                # selected tab (or credentials) and saves, get_config() / the
                # app-state client reflect that, while a captured snapshot
                # would keep fetching the old — often empty — tab.
                await state.refresh(
                    await resolve_client(app.state),
                    get_config(),
                    filter_writer,
                )
            except Exception as exc:
                logger.warning("Refresh on zone change failed: %s", exc)

        watcher = ClientLogWatcher(log_path, on_zone_change=on_zone_change)
        app.state.watcher = watcher
        watcher_task = asyncio.create_task(watcher.start())
        logger.info("Watching Client.txt: %s", log_path)
    else:
        app.state.watcher = None
        logger.info("No Client.txt resolved; logwatch disabled")

    # Periodic refresh fallback: fires every refresh_interval seconds. This is
    # the only auto-refresh when logwatch is disabled (no Client.txt), and a
    # safety net otherwise — RecipeState._refresh_lock serializes overlaps so
    # it can run alongside the zone-change watcher without double-fetching.
    # 0 disables it (manual refresh only).
    periodic_task: asyncio.Task | None = None
    if config.refresh_interval > 0:

        async def periodic_refresh() -> None:
            while True:
                interval = get_config().refresh_interval
                await asyncio.sleep(interval if interval > 0 else 30)
                try:
                    await state.refresh(
                        await resolve_client(app.state),
                        get_config(),
                        filter_writer,
                    )
                except Exception as exc:
                    logger.warning("Periodic refresh failed: %s", exc)

        periodic_task = asyncio.create_task(periodic_refresh())
        logger.info("Periodic refresh every %ds", config.refresh_interval)
    else:
        logger.info("Periodic refresh disabled (refresh_interval=0)")

    # Initial refresh on startup (defensive: never crash the app on API/filter errors).
    try:
        await state.refresh(client, config, filter_writer)
        logger.info("Initial refresh complete")
    except Exception as exc:
        logger.warning("Initial refresh failed: %s", exc)

    yield

    if periodic_task is not None:
        periodic_task.cancel()
        try:
            await periodic_task
        except asyncio.CancelledError:
            pass
    if watcher is not None and watcher_task is not None:
        await watcher.stop()
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass
    # Close the *live* client — resolve_client may have replaced the startup
    # one mid-session (on credential change), so app.state.client is authoritative.
    # Guard for the duck-typed fakes used in tests (and any client without close).
    live_client = app.state.client
    if isinstance(live_client, PoeApiClient):
        await live_client.close()
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
    # `or` would reject an explicit --port 0 / --host "" (both falsy).
    host = args.host if args.host is not None else config.host
    port = args.port if args.port is not None else config.port

    logger.info("Starting server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
